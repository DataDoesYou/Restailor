from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List
import logging

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restailor.models import AnalyticsJobSnapshotState, Application, Job


SnapshotRecord = Dict[str, Any]


def _normalize_dt(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    dt = value
    if dt.tzinfo is None:
        try:
            dt = datetime(
                dt.year,
                dt.month,
                dt.day,
                dt.hour,
                dt.minute,
                dt.second,
                dt.microsecond,
                tzinfo=timezone.utc,
            )
        except Exception:
            try:
                dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                return None
    try:
        return dt.astimezone(timezone.utc)
    except Exception:
        return datetime(
            dt.year,
            dt.month,
            dt.day,
            dt.hour,
            dt.minute,
            dt.second,
            dt.microsecond,
            tzinfo=timezone.utc,
        )


def compute_snapshot_state(session: Session, user_id: int, include_test_rows: bool = False) -> list[SnapshotRecord]:
    app_query = (
        session.query(Application)
        .filter(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
    )
    if not include_test_rows:
        app_query = app_query.filter(
            sa.or_(Application.is_test.is_(False), Application.is_test.is_(None))
        )

    app_rows: list[Application] = app_query.all()
    if not app_rows:
        return []

    latest_by_jd: dict[str, Application] = {}
    ordered_apps: list[Application] = []
    for app in app_rows:
        jd_hash_val = getattr(app, "jd_hash", None)
        if not isinstance(jd_hash_val, str) or not jd_hash_val:
            continue
        group_key = f"{user_id}:{jd_hash_val}"
        if group_key in latest_by_jd:
            continue
        latest_by_jd[group_key] = app
        ordered_apps.append(app)

    if not ordered_apps:
        return []

    job_ids: list[Any] = []
    hash_candidates: set[str] = set()
    for app in ordered_apps:
        job_id_val = getattr(app, "job_id", None)
        if job_id_val is not None:
            job_ids.append(job_id_val)
        job_hashes = getattr(app, "job_input_hashes", None)
        if job_hashes:
            for h_val in job_hashes:
                if isinstance(h_val, str) and h_val:
                    hash_candidates.add(h_val)

    jobs_by_id: dict[str, Job] = {}
    if job_ids:
        jobs = (
            session.query(Job)
            .filter(Job.id.in_(job_ids))
            .all()
        )
        for job in jobs:
            try:
                jobs_by_id[str(getattr(job, "id"))] = job
            except Exception:
                continue

    jobs_by_input_hash: dict[str, list[Job]] = {}
    if hash_candidates:
        hash_jobs = (
            session.query(Job)
            .filter(Job.input_hash.in_(hash_candidates))
            .all()
        )
        for job in hash_jobs:
            try:
                key = str(getattr(job, "input_hash"))
            except Exception:
                continue
            if not key:
                continue
            bucket = jobs_by_input_hash.setdefault(key, [])
            bucket.append(job)

    records: list[SnapshotRecord] = []
    now = datetime.now(timezone.utc)

    for app in ordered_apps:
        job_lookup_key = None
        job_obj: Job | None = None
        job_id_val = getattr(app, "job_id", None)
        has_linked_job = job_id_val is not None
        if has_linked_job:
            try:
                job_lookup_key = str(job_id_val)
            except Exception:
                job_lookup_key = None
        if job_lookup_key:
            job_obj = jobs_by_id.get(job_lookup_key)

        job_hash_matches: list[Job] = []
        job_input_hashes = getattr(app, "job_input_hashes", None)
        if job_input_hashes:
            for hash_val in job_input_hashes:
                if not isinstance(hash_val, str) or not hash_val:
                    continue
                matches = jobs_by_input_hash.get(hash_val)
                if matches:
                    job_hash_matches.extend(matches)

        # SINGLE SOURCE OF TRUTH: Read flags directly from application (no runtime merging)
        # The applications table is now the authoritative source after migration
        app_flags = {
            "interviewing": bool(getattr(app, "is_interviewing", False)),
            "offer": bool(getattr(app, "is_offer", False)),
            "hired": bool(getattr(app, "is_hired", False)),
        }

        is_active_flag = True
        if job_obj is not None:
            if getattr(job_obj, "deleted_at", None) is not None or bool(getattr(job_obj, "is_archived", False)):
                is_active_flag = False
        else:
            if job_hash_matches:
                for candidate in job_hash_matches:
                    if not include_test_rows and bool(getattr(candidate, "is_test", False)):
                        continue
                    if getattr(candidate, "deleted_at", None) is not None or bool(getattr(candidate, "is_archived", False)):
                        is_active_flag = False
                        break

        record_is_test = bool(
            getattr(app, "is_test", False)
            or (job_obj and getattr(job_obj, "is_test", False))
            or any(bool(getattr(candidate, "is_test", False)) for candidate in job_hash_matches)
        )

        created_ts = _normalize_dt(getattr(app, "created_at", None)) or now
        updated_ts = _normalize_dt(getattr(app, "updated_at", None)) or created_ts
        job_updated_ts = _normalize_dt(getattr(job_obj, "updated_at", None)) if job_obj is not None else None
        if isinstance(job_updated_ts, datetime) and job_updated_ts > updated_ts:
            updated_ts = job_updated_ts

        records.append(
            {
                "snapshot_id": getattr(app, "id"),
                "user_id": user_id,
                "job_id": getattr(job_obj, "id", None),
                "created_at": created_ts,
                "updated_at": updated_ts,
                "is_applied": bool(getattr(app, "is_applied", False)),
                "is_active": is_active_flag,
                "is_interviewing": bool(app_flags.get("interviewing")),
                "is_offer": bool(app_flags.get("offer")),
                "is_hired": bool(app_flags.get("hired")),
                "is_test": record_is_test,
            }
        )

    return records


def replace_snapshot_state(session: Session, user_id: int, records: List[SnapshotRecord]) -> None:
    table = AnalyticsJobSnapshotState.__table__
    session.execute(sa.delete(table).where(table.c.user_id == user_id))
    if records:
        payload = []
        for rec in records:
            payload.append(
                {
                    "snapshot_id": rec["snapshot_id"],
                    "user_id": rec["user_id"],
                    "job_id": rec.get("job_id"),
                    "created_at": rec["created_at"],
                    "updated_at": rec.get("updated_at", datetime.now(timezone.utc)),
                    "is_applied": bool(rec.get("is_applied", False)),
                    "is_active": bool(rec.get("is_active", True)),
                    "is_interviewing": bool(rec.get("is_interviewing", False)),
                    "is_offer": bool(rec.get("is_offer", False)),
                    "is_hired": bool(rec.get("is_hired", False)),
                    "is_test": bool(rec.get("is_test", False)),
                }
            )
        session.execute(table.insert(), payload)


def rebuild_snapshot_state(
    session: Session,
    user_id: int,
    *,
    include_test_rows: bool | None = None,
    commit: bool = True,
) -> list[SnapshotRecord]:
    include = bool(include_test_rows) if include_test_rows is not None else False
    records = compute_snapshot_state(session, user_id, include_test_rows=include)
    replace_snapshot_state(session, user_id, records)
    if commit:
        session.commit()
    else:
        session.flush()
    return records


def snapshot_is_stale(session: Session, user_id: int, *, include_test_rows: bool = False) -> bool:
    if not user_id:
        return False

    state_tbl = AnalyticsJobSnapshotState.__table__
    state_filters = [state_tbl.c.user_id == user_id]
    if not include_test_rows:
        state_filters.append(sa.or_(state_tbl.c.is_test.is_(False), state_tbl.c.is_test.is_(None)))

    state_row = session.execute(
        sa.select(
            sa.func.count().label("row_count"),
            sa.func.max(state_tbl.c.updated_at).label("latest_updated"),
            sa.func.max(state_tbl.c.created_at).label("latest_created"),
        ).where(sa.and_(*state_filters))
    ).one()

    state_count = int(getattr(state_row, "row_count", 0) or 0)
    latest_state = _normalize_dt(getattr(state_row, "latest_updated", None)) or _normalize_dt(
        getattr(state_row, "latest_created", None)
    )

    app_filters = [Application.user_id == user_id]
    if not include_test_rows:
        app_filters.append(sa.or_(Application.is_test.is_(False), Application.is_test.is_(None)))

    app_row = session.execute(
        sa.select(
            sa.func.count().label("row_count"),
            sa.func.max(Application.updated_at).label("latest_updated"),
            sa.func.max(Application.created_at).label("latest_created"),
        ).where(sa.and_(*app_filters))
    ).one()

    app_count = int(getattr(app_row, "row_count", 0) or 0)
    latest_app = _normalize_dt(getattr(app_row, "latest_updated", None)) or _normalize_dt(
        getattr(app_row, "latest_created", None)
    )

    job_filters = [Job.user_id == user_id]
    if not include_test_rows:
        job_filters.append(sa.or_(Job.is_test.is_(False), Job.is_test.is_(None)))

    job_row = session.execute(
        sa.select(
            sa.func.max(Job.updated_at).label("latest_updated"),
            sa.func.max(Job.deleted_at).label("latest_deleted"),
            sa.func.max(Job.created_at).label("latest_created"),
        ).where(sa.and_(*job_filters))
    ).one()

    job_candidates: list[datetime] = []
    for attr in ("latest_updated", "latest_deleted", "latest_created"):
        norm = _normalize_dt(getattr(job_row, attr, None))
        if isinstance(norm, datetime):
            job_candidates.append(norm)
    latest_job = max(job_candidates) if job_candidates else None

    if app_count == 0:
        return state_count > 0

    if state_count == 0 or state_count < app_count:
        return True

    latest_change_candidates = [dt for dt in (latest_app, latest_job) if isinstance(dt, datetime)]
    if latest_change_candidates:
        latest_change = max(latest_change_candidates)
        if not isinstance(latest_state, datetime) or latest_state < latest_change:
            return True

    return False


def ensure_snapshot_state(
    session: Session,
    user_id: int,
    *,
    include_test_rows: bool | None = None,
    force: bool = False,
    reason: str | None = None,
    logger: logging.Logger | None = None,
    commit: bool = False,
) -> bool:
    include = bool(include_test_rows) if include_test_rows is not None else False
    if not user_id:
        return False

    needs_refresh = force
    if not needs_refresh:
        try:
            needs_refresh = snapshot_is_stale(session, user_id, include_test_rows=include)
        except Exception as ex:
            needs_refresh = True
            if logger is not None:
                logger.debug("analytics.snapshot_stale_check_failed", exc_info=ex)

    if not needs_refresh:
        return False

    records = rebuild_snapshot_state(
        session,
        user_id,
        include_test_rows=include,
        commit=commit,
    )

    # Reduced logging noise: only log on debug level unless forced/error
    if logger is not None and force:
        try:
            logger.info(
                "analytics.snapshot_refreshed",
                extra={
                    "user_id": user_id,
                    "force": force,
                    "reason": reason,
                    "refreshed_rows": len(records),
                },
            )
        except Exception:
            logger.info(
                "analytics.snapshot_refreshed",
                extra={"user_id": user_id, "force": force, "reason": reason},
            )

    return True
