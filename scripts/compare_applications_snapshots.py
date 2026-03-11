from __future__ import annotations

import json
from typing import Dict, Iterable, Tuple

import sqlalchemy as sa
from sqlalchemy.orm import Session

from restailor.models import Application, AnalyticsJobSnapshotState
from services.analytics_job_snapshot import compute_snapshot_state

Aggregate = Dict[str, int]
DiffMap = Dict[int, Tuple[Aggregate, Aggregate]]
AggregateResults = Dict[int, Dict[str, Aggregate]]


def _empty_aggregate() -> Aggregate:
    return {
        "snapshot_count": 0,
        "is_applied": 0,
        "is_interviewing": 0,
        "is_offer": 0,
        "is_hired": 0,
    }


def _aggregate_from_records(records: Iterable[dict]) -> Aggregate:
    agg = _empty_aggregate()
    for rec in records:
        if not rec.get("is_active"):
            continue
        agg["snapshot_count"] += 1
        if rec.get("is_applied"):
            agg["is_applied"] += 1
        if rec.get("is_interviewing"):
            agg["is_interviewing"] += 1
        if rec.get("is_offer"):
            agg["is_offer"] += 1
        if rec.get("is_hired"):
            agg["is_hired"] += 1
    return agg


def _aggregate_from_snapshot_rows(rows: Iterable[AnalyticsJobSnapshotState]) -> Aggregate:
    agg = _empty_aggregate()
    for row in rows:
        if not bool(getattr(row, "is_active", False)):
            continue
        agg["snapshot_count"] += 1
        if bool(getattr(row, "is_applied", False)):
            agg["is_applied"] += 1
        if bool(getattr(row, "is_interviewing", False)):
            agg["is_interviewing"] += 1
        if bool(getattr(row, "is_offer", False)):
            agg["is_offer"] += 1
        if bool(getattr(row, "is_hired", False)):
            agg["is_hired"] += 1
    return agg
def _aggregate_from_application_rows(rows: Iterable[Application]) -> Aggregate:
    agg = _empty_aggregate()
    for row in rows:
        agg["snapshot_count"] += 1
        if bool(getattr(row, "is_applied", False)):
            agg["is_applied"] += 1
        if bool(getattr(row, "is_interviewing", False)):
            agg["is_interviewing"] += 1
        if bool(getattr(row, "is_offer", False)):
            agg["is_offer"] += 1
        if bool(getattr(row, "is_hired", False)):
            agg["is_hired"] += 1
    return agg


def collect_application_snapshot_aggregates(
    session: Session,
    *,
    include_test_rows: bool = False,
) -> AggregateResults:
    """Return per-user aggregates of expected vs. actual analytics snapshot state."""

    # Build user set from both tables so we examine every candidate.
    app_query = sa.select(Application.user_id).distinct()
    if not include_test_rows:
        app_query = app_query.where(sa.or_(Application.is_test.is_(False), Application.is_test.is_(None)))
    app_users = {row[0] for row in session.execute(app_query)}

    state_query = sa.select(AnalyticsJobSnapshotState.user_id).distinct()
    if not include_test_rows:
        state_query = state_query.where(sa.or_(AnalyticsJobSnapshotState.is_test.is_(False), AnalyticsJobSnapshotState.is_test.is_(None)))
    snapshot_users = {row[0] for row in session.execute(state_query)}

    user_ids = sorted(app_users.union(snapshot_users))

    aggregates: AggregateResults = {}

    for user_id in user_ids:
        app_filters = [Application.user_id == user_id]
        if not include_test_rows:
            app_filters.append(sa.or_(Application.is_test.is_(False), Application.is_test.is_(None)))
        app_rows = (
            session.query(Application)
            .filter(sa.and_(*app_filters))
            .order_by(Application.created_at.desc())
            .all()
        )
        raw_apps = _aggregate_from_application_rows(app_rows)

        expected_records = compute_snapshot_state(
            session,
            user_id,
            include_test_rows=include_test_rows,
        )
        expected = _aggregate_from_records(expected_records)

        state_filters = [AnalyticsJobSnapshotState.user_id == user_id]
        if not include_test_rows:
            state_filters.append(sa.or_(AnalyticsJobSnapshotState.is_test.is_(False), AnalyticsJobSnapshotState.is_test.is_(None)))
        rows = (
            session.query(AnalyticsJobSnapshotState)
            .filter(sa.and_(*state_filters))
            .all()
        )
        actual = _aggregate_from_snapshot_rows(rows)

        aggregates[user_id] = {
            "raw_applications": raw_apps,
            "expected": expected,
            "actual": actual,
        }

    return aggregates


def compare_applications_and_snapshots(
    session: Session,
    *,
    include_test_rows: bool = False,
) -> DiffMap:
    """Return per-user aggregate differences between Applications and analytics snapshot state."""

    aggregates = collect_application_snapshot_aggregates(session, include_test_rows=include_test_rows)

    diffs: DiffMap = {}
    for user_id, payload in aggregates.items():
        if payload["expected"] != payload["actual"]:
            diffs[user_id] = (payload["expected"], payload["actual"])

    return diffs

def main() -> int:
    from restailor.db import SessionLocal

    with SessionLocal() as session:
        aggregates = collect_application_snapshot_aggregates(session)

    print("Per-user application vs. analytics aggregates:")
    print(json.dumps(aggregates, indent=2, sort_keys=True))

    diffs = {
        uid: (payload["expected"], payload["actual"])
        for uid, payload in aggregates.items()
        if payload["expected"] != payload["actual"]
    }

    if diffs:
        print("Found analytics snapshot mismatches (by user_id):")
        print(json.dumps({uid: {"expected": exp, "actual": act} for uid, (exp, act) in diffs.items()}, indent=2))
        return 1

    print("Applications and analytics_job_snapshot_state aggregates match.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
