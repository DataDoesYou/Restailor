from __future__ import annotations

import json
import uuid
from typing import Annotated, Any
from datetime import datetime, timezone
from urllib.parse import unquote
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import sqlalchemy as sa

from restailor import auth as auth_dep
from restailor.models import User, Application, Job
from services.analytics_job_snapshot import ensure_snapshot_state
from restailor.privacy import should_persist_user_content
from backend.hash_utils import compute_applied_key, normalize_text, sha256_hex
# Use the same normalization as the jobs input gate to compute the exact
# Job.input_hash so History can find the corresponding Job row.
try:
    from restailor.input_gate import _normalize as gate_normalize  # type: ignore
except Exception:  # pragma: no cover
    # Fallback to a simpler normalization (should be rare); keeps behavior sane in tests
    def gate_normalize(s: str) -> str:  # type: ignore
        return normalize_text(s or "")
from backend.crypto_utils import encrypt_json, decrypt_json
from restailor.app_config import CONFIG
from restailor import crud
import random

logger = logging.getLogger(__name__)

applications_router = APIRouter(prefix="/applications", tags=["applications"])


JD_TEXT_NORM_LIMIT = 800


_STAGE_ORDER = {
    "applied": 0,
    "interviewing": 1,
    "offer": 2,
    "hired": 3,
}


class ApplicationSnapshot(BaseModel):
    resumeInput: str | None = None
    jdInput: str | None = None
    fitOutput: dict | list | str | None = None
    tailoredOutput: dict | list | str | None = None
    judgeOutput: dict | list | str | None = None
    knobs: dict | None = None
    modelInfo: dict | None = None
    statsMd: str | None = None  # added to persist timing/stats markdown


class ApplicationUpsertBody(BaseModel):
    company: str | None = None
    role: str | None = None
    jd_url: str | None = Field(None, alias="jdUrl")
    jd_text: str = Field(..., alias="jdText")
    base_text: str = Field(..., alias="baseText")
    snapshot: ApplicationSnapshot
    consent: bool | None = None


class ApplicationByKeyResponse(BaseModel):
    found: bool
    row: dict | None = None
    # Include applied flag so client can avoid optimistic mislabel flicker
    # (kept for backward compatibility; existing consumers ignore extra field in row)


class ApplicationListItem(BaseModel):
    appliedKey: str
    company: str | None = None
    role: str | None = None
    jdUrl: str | None = None
    jdHash: str
    baseHash: str
    createdAt: str
    updatedAt: str
    jdSnippet: str | None = None
    isApplied: bool
    # Optional job metadata for stage/archive UI
    jobId: str | None = None
    jobToken: str | None = None
    isArchived: bool | None = None
    isStaged: bool | None = None
    # Independent flags (present when a Job exists; None otherwise)
    interviewing: bool | None = None
    offer: bool | None = None
    hired: bool | None = None
    stageLabel: str | None = None
    jobInputHashes: list[str] | None = None


class ApplicationListResponse(BaseModel):
    page: int
    pageSize: int
    total: int
    items: list[ApplicationListItem]


class ApplicationStageFlagsPatchBody(BaseModel):
    applied_key: str = Field(..., alias="appliedKey")
    interviewing: bool | None = None
    offer: bool | None = None
    hired: bool | None = None

from restailor.stage_utils import (
    StagePresentation,
    application_stage_state,
    resolve_stage_for_application,
    present_stage_state,
    present_application_stage,
    stage_payload,
    stage_label_from_flags,
)


# --- New JD-hash centric (single-snapshot-per-JD) API models ---
class JdApplyBody(BaseModel):
    jd_text: str | None = Field(None, alias="jdText")
    base_text: str | None = Field(None, alias="baseText")  # current base resume (stored in snapshot; NOT auto-restored on passive lookup)
    snapshot: ApplicationSnapshot | None = None  # same payload shape as existing upsert
    applied_key: str | None = Field(None, alias="appliedKey")  # new fast-path: target exact row
    consent: bool | None = None  # reuse consent gate


class JdApplyResponse(BaseModel):
    ok: bool
    jdHash: str
    appliedKey: str  # retained for history views (still base-hash specific)
    updatedAt: str
    isApplied: bool  # STEAM: Return actual DB state for verification


class JdLookupResponse(BaseModel):
    found: bool
    jdHash: str | None = None
    row: dict | None = None  # mirrors existing lookup structure (appliedKey, snapshot, updatedAt, isApplied)


class JdSaveBody(BaseModel):
    jd_text: str = Field(..., alias="jdText")
    base_text: str = Field(..., alias="baseText")
    snapshot: ApplicationSnapshot


class JdSaveResponse(BaseModel):
    ok: bool
    jdHash: str
    appliedKey: str
    isApplied: bool
    updatedAt: str


class LatestSnapshotResponse(BaseModel):
    found: bool
    snapshot: dict | None = None
    appliedKey: str | None = None
    jdHash: str | None = None
    isApplied: bool = False
    updatedAt: str | None = None


def _compute_jd_hash(jd_text: str) -> str:
    """Canonicalize and hash JD text for JD-scoped snapshot operations.

    Mirrors normalization used inside compute_applied_key but ignores base resume.
    """
    return sha256_hex(normalize_text(jd_text))


def _derive_jd_projection(primary_text: str | None, snapshot: dict | None) -> tuple[str | None, str | None]:
    """Return (snippet, normalized) tuple for JD text."""
    text = primary_text
    if not text and isinstance(snapshot, dict):
        cand = snapshot.get("jdInput")
        if isinstance(cand, str):
            text = cand
    if not isinstance(text, str) or not text.strip():
        return None, None
    snippet_raw = " ".join(text.split())
    snippet = snippet_raw[:500] if snippet_raw else None
    norm_raw = normalize_text(text)
    norm = norm_raw.lower()[:JD_TEXT_NORM_LIMIT] if norm_raw else None
    return snippet, norm


def _derive_job_input_hashes(
    base_text: str | None,
    jd_text: str | None,
    snapshot: dict | None,
) -> list[str]:
    """Return preferred Job.input_hash candidates derived from resume/JD/candidate text.

    The order matches job creation precedence: FIT (resume+jd+marker), Tailor (resume+jd),
    Judge (resume+jd+candidate+marker).
    """

    resume_val = base_text
    jd_val = jd_text
    cand_text: str | None = None

    if isinstance(snapshot, dict):
        if not resume_val:
            snap_resume = snapshot.get("resumeInput")
            if isinstance(snap_resume, str) and snap_resume.strip():
                resume_val = snap_resume
        if not jd_val:
            snap_jd = snapshot.get("jdInput")
            if isinstance(snap_jd, str) and snap_jd.strip():
                jd_val = snap_jd
        cand = snapshot.get("tailoredOutput")
        if isinstance(cand, str):
            cand_text = cand
        elif cand is not None:
            try:
                cand_text = json.dumps(cand, ensure_ascii=False)
            except Exception:
                cand_text = str(cand)

    if not isinstance(resume_val, str) or not resume_val.strip():
        return []
    if not isinstance(jd_val, str) or not jd_val.strip():
        return []

    try:
        r_norm = gate_normalize(resume_val)
        j_norm = gate_normalize(jd_val)
    except Exception:
        return []

    hashes: list[str] = []

    def _push(candidate: str | None) -> None:
        if candidate and candidate not in hashes:
            hashes.append(candidate)

    try:
        _push(sha256_hex(r_norm + "\n" + j_norm + "\nFIT"))
    except Exception:
        pass
    try:
        _push(sha256_hex(r_norm + "\n" + j_norm))
    except Exception:
        pass

    if isinstance(cand_text, str) and cand_text.strip():
        try:
            c_norm = gate_normalize(cand_text)
            _push(sha256_hex(r_norm + "\n" + j_norm + "\n" + c_norm + "\nJUDGE"))
        except Exception:
            pass

    return hashes


@applications_router.post("/upsert")
def upsert_application(
    body: ApplicationUpsertBody,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    if not should_persist_user_content(current_user):
        if not body.consent:
            raise HTTPException(status_code=409, detail="consent_required_to_store_snapshot")
    jd_hash, base_hash, applied_key = compute_applied_key(current_user.id, body.jd_text, body.base_text)
    snapshot_dict = json.loads(body.snapshot.model_dump_json(by_alias=True, exclude_none=True))
    jd_snippet, jd_text_norm = _derive_jd_projection(body.jd_text, snapshot_dict)
    job_input_hashes = _derive_job_input_hashes(body.base_text, body.jd_text, snapshot_dict)
    job_input_hashes = _derive_job_input_hashes(body.base_text, body.jd_text, snapshot_dict)
    job_input_hashes = _derive_job_input_hashes(body.base_text, body.jd_text, snapshot_dict)
    try:
        snapshot_enc = encrypt_json(snapshot_dict, session=db)
    except Exception as ex:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"encrypt_failed: {ex}")

    user_id = int(getattr(current_user, "id", 0) or 0)
    include_tests = bool(getattr(current_user, "is_test", False))

    try:
        row = Application.upsert(
            db,
            user_id=current_user.id,
            jd_hash=jd_hash,
            base_hash=base_hash,
            snapshot_enc=snapshot_enc,
            company=body.company,
            role=body.role,
            jd_url=body.jd_url,
            jd_snippet=jd_snippet,
            jd_text_norm=jd_text_norm,
            is_test=getattr(current_user, "is_test", False),
            job_input_hashes=job_input_hashes,
        )
        db.flush()
        if user_id:
            ensure_snapshot_state(
                db,
                user_id,
                include_test_rows=include_tests,
                force=True,
                reason="applications.upsert",
                logger=logger,
                commit=False,
            )
        db.commit()
    except HTTPException:
        raise
    except Exception as ex:  # pragma: no cover
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"upsert_failed: {ex}")
    return {"ok": True, "appliedKey": row.applied_key, "updatedAt": row.updated_at.isoformat()}


@applications_router.get("/demo/random", response_model=ApplicationByKeyResponse)
def get_random_demo_application(
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    demo_email = CONFIG.get("app", {}).get("demo_user_email")
    if not demo_email:
        return {"found": False, "row": None}

    user = crud.get_user_by_username(db, username=demo_email)
    if not user:
        return {"found": False, "row": None}

    JobAlias = sa.orm.aliased(Job)
    query = (
        db.query(Application.applied_key)
        .join(JobAlias, Application.job_id == JobAlias.id)
        .filter(Application.user_id == user.id)
        .filter(
            JobAlias.is_archived.is_(False),
            JobAlias.status == "completed",
        )
    )
    keys = [r[0] for r in query.all()]

    if not keys:
         return {"found": False, "row": None}

    chosen_key = random.choice(keys)
    row = Application.get_by_key(db, chosen_key)

    if not row:
         return {"found": False, "row": None}

    try:
        snapshot = decrypt_json(row.snapshot_enc, session=db)
    except Exception:
        snapshot = None

    job_id = None
    chosen_job = None
    if row.job_id:
        chosen_job = db.query(Job).filter(Job.id == row.job_id).first()
        if chosen_job:
            job_id = str(chosen_job.id)

    app_stage_state = application_stage_state(row)
    stage_view = present_stage_state(
        app_stage_state,
        is_applied=bool(row.is_applied),
        job=chosen_job,
    )
    interviewing = stage_view.output_flags["interviewing"]
    offer = stage_view.output_flags["offer"]
    hired = stage_view.output_flags["hired"]

    return {
        "found": True,
        "row": {
            "company": row.company,
            "role": row.role,
            "jdUrl": row.jd_url,
            "snapshot": snapshot,
            "updatedAt": row.updated_at.isoformat(),
            "isApplied": row.is_applied,
            "jobId": job_id,
            "jobToken": None,
            "interviewing": interviewing,
            "offer": offer,
            "hired": hired,
            "stageLabel": stage_view.label,
        },
    }


@applications_router.get("/by-key", response_model=ApplicationByKeyResponse)
def get_application_by_key(
    appliedKey: str,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    row = Application.get_by_key(db, appliedKey)
    if not row or row.user_id != current_user.id:
        return {"found": False, "row": None}
    try:
        snapshot = decrypt_json(row.snapshot_enc, session=db)
    except Exception:  # pragma: no cover
        snapshot = None
    # Try to locate the corresponding Job leveraging stored hash candidates
    job_id: str | None = None
    job_token: str | None = None
    chosen: Job | None = None
    try:
        job_hash_candidates = [
            h for h in getattr(row, "job_input_hashes", None) or [] if isinstance(h, str)
        ]
        if not job_hash_candidates and isinstance(snapshot, dict):
            job_hash_candidates = _derive_job_input_hashes(None, None, snapshot)
        if job_hash_candidates:
            job_rows: list[Job] = (
                db.query(Job)
                .filter(
                    Job.user_id == current_user.id,
                    Job.deleted_at.is_(None),
                    Job.input_hash.in_(job_hash_candidates),
                )
                .order_by(Job.input_hash.asc(), Job.created_at.desc())
                .all()
            )
            # Pick by same preference as list: first with stage set, else first by order (FIT->TAILOR->JUDGE)
            def _pick(js: list[Job]) -> Job | None:
                if not js:
                    return None
                for j in js:
                    st = getattr(j, "stage", None)
                    if isinstance(st, str) and st.strip():
                        return j
                return js[0]
            # Bucket by input_hash to ensure order of candidates respected
            if job_rows:
                # Keep only the latest per input_hash
                latest_by: dict[str, Job] = {}
                for j in job_rows:
                    if j.input_hash not in latest_by:
                        latest_by[j.input_hash] = j
                ordered = [latest_by[ih] for ih in job_hash_candidates if ih in latest_by]
                chosen = _pick(ordered)
            if chosen is not None:
                job_id = str(getattr(chosen, "id"))
                job_token = str(getattr(chosen, "access_token", "") or "") or None
    except Exception:
        # If any error occurs while mapping to Job, proceed without job metadata
        job_id = None
        job_token = None
        chosen = None

    app_stage_state = application_stage_state(row)
    stage_view = present_stage_state(
        app_stage_state,
        is_applied=bool(row.is_applied),
        job=chosen,
    )
    interviewing = stage_view.output_flags["interviewing"]
    offer = stage_view.output_flags["offer"]
    hired = stage_view.output_flags["hired"]
    return {
        "found": True,
        "row": {
            "company": row.company,
            "role": row.role,
            "jdUrl": row.jd_url,
            "snapshot": snapshot,
            "updatedAt": row.updated_at.isoformat(),
            "isApplied": row.is_applied,
            # Include job metadata for History actions (stage/archive toggles)
            "jobId": job_id,
            "jobToken": job_token,
            "interviewing": interviewing,
            "offer": offer,
            "hired": hired,
            "stageLabel": stage_view.label,
        },
    }


@applications_router.get("/lookup", response_model=ApplicationByKeyResponse)
def lookup_application(
    jdHash: str,
    baseHash: str,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    applied_key = f"{current_user.id}:{jdHash}:{baseHash}"
    row = Application.get_by_key(db, applied_key)
    if not row or row.user_id != current_user.id:
        return {"found": False, "row": None}
    try:
        snapshot = decrypt_json(row.snapshot_enc, session=db)
    except Exception:  # pragma: no cover
        snapshot = None
    return {
        "found": True,
        "row": {
            "company": row.company,
            "role": row.role,
            "jdUrl": row.jd_url,
            "snapshot": snapshot,
            "updatedAt": row.updated_at.isoformat(),
        },
    }


@applications_router.get("/list", response_model=ApplicationListResponse)
def list_applications(
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
    request: Request,
    page: int = 1,
    pageSize: int = 50,
    search: str | None = None,
    showAppliedOnly: bool | None = None,
    stages: str | None = None,
    applied: bool | None = None,
    archived: bool | None = None,
    sort: str | None = None,
    dir: str | None = None,
):
    # FEATURE FLAG: Single Source of Truth - simplified endpoint without runtime merging
    try:
        from restailor.app_config import CONFIG
        use_simplified = bool(((CONFIG.get("features", {}) or {}).get("single_source_of_truth", False)))
        if use_simplified:
            from restailor.applications_list_simple import list_applications_simple
            return list_applications_simple(
                current_user=current_user,
                db=db,
                request=request,
                page=page,
                pageSize=pageSize,
                search=search,
                showAppliedOnly=showAppliedOnly,
                stages=stages,
                applied=applied,
                archived=archived,
                sort=sort,
                dir=dir,
            )
    except Exception as ex:
        logger.warning("single_source_of_truth: feature flag check failed, using legacy endpoint", exc_info=ex)
    
    # Read a small map of appliedKey->jobId to keep mapping stable across refresh
    # Prefer an explicit header (supports cross-origin clients) and fall back to Cookie.
    preferred_job_map: dict[str, str] = {}
    try:
        hdr_map = request.headers.get("x-rt-jobmap")
        if hdr_map:
            try:
                preferred_job_map = json.loads(unquote(hdr_map)) if hdr_map else {}
                if not isinstance(preferred_job_map, dict):
                    preferred_job_map = {}
            except Exception:
                preferred_job_map = {}
        if not preferred_job_map:
            raw_cookie = request.headers.get("cookie") or request.headers.get("Cookie") or ""
            if "rt_jobid_map=" in raw_cookie:
                # naive parse of the cookie value
                for part in raw_cookie.split(";"):
                    p = part.strip()
                    if p.startswith("rt_jobid_map="):
                        val = p.split("=", 1)[1]
                        try:
                            preferred_job_map = json.loads(unquote(val)) if val else {}
                            if not isinstance(preferred_job_map, dict):
                                preferred_job_map = {}
                        except Exception:
                            preferred_job_map = {}
                        break
    except Exception:
        preferred_job_map = {}

    if page < 1:
        page = 1
    if pageSize < 1:
        pageSize = 1
    if pageSize > 500:
        pageSize = 500
    search_norm = search.strip().lower() if search else None

    # Fetch all rows for user (ordered) so we can decrypt & filter before pagination
    q = db.query(Application).filter(Application.user_id == current_user.id)
    # 'Applied' filter: accept either legacy or new param
    # FastAPI converts query param "false" to Python bool False, so we need explicit True check
    applied_only = showAppliedOnly is True or applied is True
    
    logger.info(f"[list_applications] PARAMS: showAppliedOnly={showAppliedOnly!r} (type={type(showAppliedOnly).__name__}), applied={applied!r} (type={type(applied).__name__}), applied_only={applied_only}")
    
    if applied_only:
        logger.info("[list_applications] Applying is_applied=True filter")
        q = q.filter(Application.is_applied.is_(True))
    # Stable ordering: most recent created first, so toggling is_applied or stage doesn't reshuffle rows
    rows = q.order_by(Application.created_at.desc()).all()
    
    logger.info(f"[list_applications] Query returned {len(rows)} rows from database")

    records: list[dict[str, Any]] = []
    job_ids_needed: set[uuid.UUID] = set()
    job_hashes_needed: set[str] = set()

    def _register_job_id(rec: dict[str, Any], value: str | uuid.UUID | None, *, preferred: bool = False) -> None:
        if not value:
            return
        try:
            uuid_val = value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
        except Exception:
            return
        job_id_str = str(uuid_val)
        order = rec.setdefault("job_id_order", [])
        if job_id_str in order:
            if preferred and order[0] != job_id_str:
                order.remove(job_id_str)
                order.insert(0, job_id_str)
            return
        if preferred:
            order.insert(0, job_id_str)
        else:
            order.append(job_id_str)
        job_ids_needed.add(uuid_val)

    seen_jd_hashes: set[str] = set()

    for row in rows:
        jd_hash_val = getattr(row, "jd_hash", None)
        if isinstance(jd_hash_val, str):
            if jd_hash_val in seen_jd_hashes:
                logger.info(f"[list_applications] SKIPPING duplicate jd_hash: {jd_hash_val[:16]}... (applied_key={row.applied_key})")
                continue
            seen_jd_hashes.add(jd_hash_val)
        if search_norm:
            jd_norm = getattr(row, "jd_text_norm", None)
            if not jd_norm or search_norm not in jd_norm:
                logger.info(f"[list_applications] SKIPPING search filter: {row.applied_key}")
                continue
        app_stage_state = application_stage_state(row)
        job_hashes = [h for h in (getattr(row, "job_input_hashes", None) or []) if isinstance(h, str)]
        for h in job_hashes:
            job_hashes_needed.add(h)

        rec: dict[str, Any] = {
            "applied_key": row.applied_key,
            "company": row.company,
            "role": row.role,
            "jd_url": row.jd_url,
            "jd_hash": row.jd_hash,
            "base_hash": row.base_hash,
            "created_at": row.created_at.isoformat(),
            "updated_at": row.updated_at.isoformat(),
            "jd_snippet": row.jd_snippet,
            "jd_text_norm": row.jd_text_norm,
            "is_applied": row.is_applied,
            "app_stage_state": app_stage_state,
            "job_hashes": job_hashes,
        }
        rec["job_id_order"] = []
        _register_job_id(rec, getattr(row, "job_id", None))
        mapped_job = preferred_job_map.get(row.applied_key)
        _register_job_id(rec, mapped_job, preferred=True)
        records.append(rec)
    
    logger.info(f"[list_applications] After dedup/search filtering: {len(records)} records remain")

    jobs_by_id: dict[str, Job] = {}
    jobs_by_hash: dict[str, Job] = {}
    if job_ids_needed:
        job_rows: list[Job] = (
            db.query(Job)
            .filter(Job.user_id == current_user.id, Job.deleted_at.is_(None), Job.id.in_(list(job_ids_needed)))
            .order_by(Job.created_at.desc())
            .all()
        )
        for job in job_rows:
            jobs_by_id[str(getattr(job, "id"))] = job
            if job.input_hash and job.input_hash not in jobs_by_hash:
                jobs_by_hash[job.input_hash] = job

    if job_hashes_needed:
        job_rows_by_hash: list[Job] = (
            db.query(Job)
            .filter(
                Job.user_id == current_user.id,
                Job.deleted_at.is_(None),
                Job.input_hash.in_(list(job_hashes_needed)),
            )
            .order_by(Job.input_hash.asc(), Job.created_at.desc())
            .all()
        )
        for job in job_rows_by_hash:
            if job.input_hash and job.input_hash not in jobs_by_hash:
                jobs_by_hash[job.input_hash] = job
            try:
                jobs_by_id.setdefault(str(getattr(job, "id")), job)
            except Exception:
                pass

    def _pick_job_for_rec(rec: dict[str, Any]) -> Job | None:
        for job_id_str in rec.get("job_id_order", []):
            job_obj = jobs_by_id.get(job_id_str)
            if job_obj is not None:
                return job_obj
        hashes = rec.get("job_hashes") or []
        # Try cached hashes first
        for h in hashes:
            job_obj = jobs_by_hash.get(h)
            if job_obj is not None:
                return job_obj
        remaining = [h for h in hashes if h not in jobs_by_hash]
        if remaining:
            fetched = (
                db.query(Job)
                .filter(
                    Job.user_id == current_user.id,
                    Job.deleted_at.is_(None),
                    Job.input_hash.in_(remaining),
                )
                .order_by(Job.input_hash.asc(), Job.created_at.desc())
                .all()
            )
            for job in fetched:
                if job.input_hash and job.input_hash not in jobs_by_hash:
                    jobs_by_hash[job.input_hash] = job
                try:
                    jobs_by_id.setdefault(str(getattr(job, "id")), job)
                except Exception:
                    pass
            for h in hashes:
                job_obj = jobs_by_hash.get(h)
                if job_obj is not None:
                    return job_obj
        return None

    def _rebuild_job_stage_maps() -> tuple[
        dict[str, Job | None],
        dict[str, StagePresentation],
    ]:
        job_map: dict[str, Job | None] = {}
        stage_view_map: dict[str, StagePresentation] = {}
        for rec in records:
            ak = rec["applied_key"]
            job_obj = _pick_job_for_rec(rec)
            job_map[ak] = job_obj
            stage_view_map[ak] = present_stage_state(
                rec["app_stage_state"],
                is_applied=bool(rec.get("is_applied")),
                job=job_obj,
            )
        return job_map, stage_view_map

    job_for_rec, stage_view_for_rec = _rebuild_job_stage_maps()

    # When archived is None (not specified), show all non-archived items INCLUDING those with no job
    # When archived is explicitly True/False, filter by that status
    if archived is not None:
        filtered_records: list[dict[str, Any]] = []
        for rec in records:
            job_obj = job_for_rec.get(rec["applied_key"])
            # If no job exists, treat as non-archived
            is_archived = bool(getattr(job_obj, "is_archived", False)) if job_obj else False
            if is_archived == bool(archived):
                filtered_records.append(rec)

        if len(filtered_records) != len(records):
            logger.info(f"[list_applications] ARCHIVED FILTER (archived={archived}): Filtered from {len(records)} to {len(filtered_records)} records")
            records = filtered_records
            job_for_rec, stage_view_for_rec = _rebuild_job_stage_maps()
    else:
        # archived=None: exclude only explicitly archived items
        filtered_records: list[dict[str, Any]] = []
        for rec in records:
            job_obj = job_for_rec.get(rec["applied_key"])
            # Skip if job is missing (ghost application)
            if job_obj is None:
                continue
            # Skip if job exists AND is archived
            if bool(getattr(job_obj, "is_archived", False)):
                continue
            filtered_records.append(rec)

        if len(filtered_records) != len(records):
            logger.info(f"[list_applications] ARCHIVED FILTER (default): Excluded {len(records) - len(filtered_records)} archived records")
            records = filtered_records
            job_for_rec, stage_view_for_rec = _rebuild_job_stage_maps()

    stage_filter_set: set[str] = set()
    if isinstance(stages, str) and stages.strip():
        try:
            stage_filter_set = {s.strip().lower() for s in stages.split(',') if s.strip()}
        except Exception:
            stage_filter_set = set()

    if applied_only:
        records = [rec for rec in records if rec.get("is_applied")]
        job_for_rec, stage_view_for_rec = _rebuild_job_stage_maps()

    if stage_filter_set:
        filtered: list[dict[str, Any]] = []
        for rec in records:
            ak = rec["applied_key"]
            stage_view = stage_view_for_rec.get(ak)
            if stage_view is None:
                stage_view = present_stage_state(
                    rec["app_stage_state"],
                    is_applied=bool(rec.get("is_applied")),
                    job=job_for_rec.get(ak),
                )
                stage_view_for_rec[ak] = stage_view
            stage_meta = stage_view.state
            stage_label = stage_view.label
            stage_val, flags, has_source = stage_meta
            actual_rank = _STAGE_ORDER.get(stage_label or "")
            match = False
            for k in stage_filter_set:
                required_rank = _STAGE_ORDER.get(k)
                if k == "applied":
                    if (stage_label == "applied") or (stage_label is None and rec.get("is_applied")):
                        match = True
                        break
                    continue
                if required_rank is not None:
                    if actual_rank is not None and actual_rank >= required_rank:
                        match = True
                        break
                    if actual_rank is None and flags.get(k):
                        match = True
                        break
                    continue
                if stage_val == k:
                    match = True
                    break
            if match or (not has_source and "applied" in stage_filter_set and rec.get("is_applied")):
                filtered.append(rec)
        records = filtered
        job_for_rec, stage_view_for_rec = _rebuild_job_stage_maps()

    if archived is not None:
        filtered: list[dict[str, Any]] = []
        for rec in records:
            job_obj = job_for_rec.get(rec["applied_key"])
            if job_obj is None:
                if archived is False:
                    filtered.append(rec)
                continue
            if bool(getattr(job_obj, "is_archived", False)) == bool(archived):
                filtered.append(rec)
        records = filtered
        job_for_rec, stage_view_for_rec = _rebuild_job_stage_maps()

    # Optional sorting before pagination. Use stable sort so tiebreaker is always newest first.
    # Build a helper map of latest Job per record to compute stage for A/I/O/H ranking.
    def _action_rank(rec: dict) -> int:
        applied_flag = bool(rec.get("is_applied"))
        ak = str(rec.get("applied_key") or "")
        stage_view = stage_view_for_rec.get(ak) if stage_view_for_rec else None
        if stage_view is None:
            stage_view = present_stage_state(
                rec["app_stage_state"],
                is_applied=bool(rec.get("is_applied")),
                job=job_for_rec.get(ak),
            )
            if stage_view_for_rec is not None:
                stage_view_for_rec[ak] = stage_view
        stage_meta = stage_view.state
        stage_label = stage_view.label
        stage_val, stage_flags, _ = stage_meta
        flags = dict(stage_flags)
        st_norm = stage_label or stage_val
        # Ordering function using flags; fallback to stage when all flags false
        if not any(flags.values()) and st_norm in ("interviewing", "offer", "hired"):
            flags = {k: (k == st_norm) for k in ("interviewing", "offer", "hired")}
        def _rank(applied: bool, f: dict[str, bool]) -> int:
            if not any(f.values()):
                return 1 if applied else 0
            if f.get("hired"):
                return 4 if applied else 7
            if f.get("offer"):
                return 3 if applied else 6
            if f.get("interviewing"):
                return 2 if applied else 5
            return 1 if applied else 0
        return _rank(applied_flag, flags)

    # Preserve the original created_at-desc order gathered above unless an explicit sort is requested.
    # Python's sort is stable, so this original order will act as the tiebreaker for subsequent sorts.

    sort_lc = (sort or "").strip()
    dir_lc = (dir or "asc").strip().lower()
    reverse = (dir_lc == "desc")
    if sort_lc in ("actions", "createdAt", "updatedAt", "jdSnippet"):
        if sort_lc == "actions":
            records.sort(key=lambda r: _action_rank(r), reverse=reverse)
        elif sort_lc == "createdAt" or sort_lc == "updatedAt":
            # createdAt (and legacy updatedAt alias) sorting
            try:
                records.sort(key=lambda r: datetime.fromisoformat(str(r.get("created_at") or "")), reverse=reverse)
            except Exception:
                records.sort(key=lambda r: str(r.get("created_at") or ""), reverse=reverse)
        elif sort_lc == "jdSnippet":
            records.sort(key=lambda r: str(r.get("jd_snippet") or "").lower(), reverse=reverse)

    # Pagination after filtering/sorting
    total = len(records)
    start = (page - 1) * pageSize
    end = start + pageSize
    page_slice = records[start:end]

    # Build final items with job metadata where available
    items: list[ApplicationListItem] = []
    for rec in page_slice:
        ak = str(rec.get("applied_key") or "")
        j: Job | None = job_for_rec.get(ak) if job_for_rec else None
        stage_view = stage_view_for_rec.get(ak) if stage_view_for_rec else None
        if stage_view is None:
            stage_view = present_stage_state(
                rec["app_stage_state"],
                is_applied=bool(rec.get("is_applied")),
                job=j,
            )
            if stage_view_for_rec is not None:
                stage_view_for_rec[ak] = stage_view
        interviewing = stage_view.output_flags["interviewing"]
        offer = stage_view.output_flags["offer"]
        hired = stage_view.output_flags["hired"]
        job_id_str: str | None = None
        if j is not None:
            try:
                job_id_str = str(getattr(j, "id"))
            except Exception:
                job_id_str = None
        else:
            job_candidates = rec.get("job_id_order") or []
            if job_candidates:
                job_id_str = job_candidates[0]
        items.append(ApplicationListItem(
            appliedKey=rec["applied_key"],
            company=rec["company"],
            role=rec["role"],
            jdUrl=rec["jd_url"],
            jdHash=rec["jd_hash"],
            baseHash=rec["base_hash"],
            createdAt=rec["created_at"],
            updatedAt=rec["updated_at"],
            jdSnippet=rec["jd_snippet"],
            isApplied=rec["is_applied"],
            jobId=job_id_str,
            jobToken=(str(j.access_token) if j else None),
            isArchived=(bool(getattr(j, "is_archived", False)) if j else None),
            isStaged=(bool(getattr(j, "is_staged", False)) if j else None),
            interviewing=interviewing,
            offer=offer,
            hired=hired,
            stageLabel=stage_view.label,
            jobInputHashes=rec.get("job_hashes"),
        ))

    return ApplicationListResponse(page=page, pageSize=pageSize, total=total, items=items)


# ---------------- JD-hash based simplified applied snapshot semantics ----------------
# These endpoints keep exactly one active snapshot per (user, jd_hash). The schema now
# enforces that uniqueness, so calling ``jd_apply`` will update the lone row for the JD
# while ensuring flags like ``is_applied`` remain consistent for the user experience.


@applications_router.post("/jd/apply", response_model=JdApplyResponse)
def jd_apply(
    body: JdApplyBody,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    user_id = int(getattr(current_user, "id", 0) or 0)
    include_tests = bool(getattr(current_user, "is_test", False))
    # Fast path: apply by appliedKey only (no updated_at bump)
    if body.applied_key:
        # Find the row
        row = db.query(Application).filter(Application.applied_key == body.applied_key, Application.user_id == current_user.id).first()
        if not row:
            raise HTTPException(status_code=404, detail="not_found")
        # Ensure only one applied per jd_hash: clear others, then set target true
        logger.info(f"[APPLY FAST] appliedKey={body.applied_key[:20]}... BEFORE: is_applied={row.is_applied}")
        try:
            from sqlalchemy import text as _sqltext
            db.execute(_sqltext("UPDATE applications SET is_applied=false WHERE user_id=:uid AND jd_hash=:jd"), {"uid": current_user.id, "jd": row.jd_hash})
            logger.info(f"[APPLY FAST] Cleared other applied rows for jdHash")
            db.execute(_sqltext("UPDATE applications SET is_applied=true WHERE applied_key=:ak AND user_id=:uid"), {"ak": body.applied_key, "uid": current_user.id})
            logger.info(f"[APPLY FAST] Set is_applied=true for target row")
            db.flush()
            logger.info(f"[APPLY FAST] Flushed to database")
            if user_id:
                ensure_snapshot_state(
                    db,
                    user_id,
                    include_test_rows=include_tests,
                    force=True,
                    reason="applications.jd_apply_fast",
                    logger=logger,
                    commit=False,
                )
            db.commit()
            logger.info(f"[APPLY FAST] Transaction committed")
        except Exception as ex:
            logger.error(f"[APPLY FAST] Error during UPDATE: {ex}")
            try: db.rollback()
            except Exception: pass
            raise HTTPException(status_code=500, detail=f"apply_failed: {ex}")
        # Reload updated_at from DB (unchanged) for response
        row2 = db.query(Application).filter(Application.applied_key == body.applied_key).first() or row
        logger.info(f"[APPLY FAST] Refreshed from DB, AFTER: is_applied={row2.is_applied}, returning isApplied={bool(row2.is_applied)}")
        return JdApplyResponse(ok=True, jdHash=row.jd_hash, appliedKey=row.applied_key, updatedAt=row2.updated_at.isoformat(), isApplied=bool(row2.is_applied))
    # Legacy path: full snapshot upsert (may bump updated_at)
    # Consent gate identical to original upsert
    if not should_persist_user_content(current_user):
        if not body.consent:
            raise HTTPException(status_code=409, detail="consent_required_to_store_snapshot")
    if not body.jd_text or not body.base_text or not body.snapshot:
        raise HTTPException(status_code=400, detail="missing_fields")
    jd_hash, base_hash, applied_key = compute_applied_key(current_user.id, body.jd_text, body.base_text)
    snapshot_dict = json.loads(body.snapshot.model_dump_json(by_alias=True, exclude_none=True))
    jd_snippet, jd_text_norm = _derive_jd_projection(body.jd_text, snapshot_dict)
    job_input_hashes = _derive_job_input_hashes(body.base_text, body.jd_text, snapshot_dict)
    try:
        snapshot_enc = encrypt_json(snapshot_dict, session=db)
    except Exception as ex:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"encrypt_failed: {ex}")
    logger.info(f"[APPLY LEGACY] Starting for jdHash={jd_hash[:16]}...")
    try:
        row = Application.upsert(
            db,
            user_id=current_user.id,
            jd_hash=jd_hash,
            base_hash=base_hash,
            snapshot_enc=snapshot_enc,
            company=None,
            role=None,
            jd_url=None,
            jd_snippet=jd_snippet,
            jd_text_norm=jd_text_norm,
            is_test=getattr(current_user, "is_test", False),
            is_applied=True,
            job_input_hashes=job_input_hashes,
        )
        logger.info(f"[APPLY LEGACY] Upsert complete, appliedKey={row.applied_key[:20]}...")
        db.flush()
        logger.info(f"[APPLY LEGACY] Flushed to database")
        if user_id:
            ensure_snapshot_state(
                db,
                user_id,
                include_test_rows=include_tests,
                force=True,
                reason="applications.jd_apply_legacy",
                logger=logger,
                commit=False,
            )
        db.commit()
        logger.info(f"[APPLY LEGACY] Transaction committed, is_applied={row.is_applied}, returning isApplied={bool(row.is_applied)}")
    except Exception as ex:  # pragma: no cover
        logger.error(f"[APPLY LEGACY] Error during upsert: {ex}")
        try:
            db.rollback()
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"apply_failed: {ex}")
    return JdApplyResponse(ok=True, jdHash=jd_hash, appliedKey=row.applied_key, updatedAt=row.updated_at.isoformat(), isApplied=bool(row.is_applied))


@applications_router.get("/jd/apply", response_model=JdLookupResponse)
def jd_lookup(
    jdHash: str,  # already hashed client-side OR from stored state
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    # Fetch latest row for this jdHash
    row = (
        db.query(Application)
        .filter(Application.user_id == current_user.id, Application.jd_hash == jdHash)
        .order_by(
            Application.job_id.is_(None).desc(),
            Application.is_applied.desc(),
            Application.updated_at.desc(),
            Application.id.desc(),
        )
        .first()
    )
    if not row:
        return JdLookupResponse(found=False, jdHash=jdHash, row=None)
    try:
        snapshot = decrypt_json(row.snapshot_enc, session=db)
    except Exception:  # pragma: no cover
        snapshot = None
    return JdLookupResponse(found=True, jdHash=jdHash, row={
        "appliedKey": row.applied_key,
        "snapshot": snapshot,
        "updatedAt": row.updated_at.isoformat(),
        "isApplied": row.is_applied,
    })


@applications_router.delete("/jd/apply", response_model=dict)
def jd_delete(
    jdHash: str,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
    appliedKey: str | None = None,
):
    """Toggle off: set is_applied false and cascade to clear I/O/H flags.

    Cascading logic: Unchecking Applied clears Interviewing, Offer, and Hired flags
    because you can't be in any of those stages without having applied first.
    
    If appliedKey is provided, unapply that exact row. Otherwise, fall back to
    the latest row for the given jdHash.
    """
    row = None
    if appliedKey:
        row = db.query(Application).filter(Application.applied_key == appliedKey, Application.user_id == current_user.id).first()
    if row is None:
        row = (
            db.query(Application)
            .filter(Application.user_id == current_user.id, Application.jd_hash == jdHash)
            .order_by(Application.updated_at.desc())
            .first()
        )
    if not row:
        return {"ok": True, "jdHash": jdHash, "changed": False}
    user_id = int(getattr(current_user, "id", 0) or 0)
    include_tests = bool(getattr(current_user, "is_test", False))
    logger.info(f"[UNAPPLY] Starting DELETE for jdHash={jdHash[:16]}... appliedKey={row.applied_key[:20]}... BEFORE: is_applied={row.is_applied}")
    try:
        from sqlalchemy import text as _sqltext
        # CASCADING LOGIC: Unchecking Applied should clear all I/O/H flags
        # You can't be interviewing, have an offer, or be hired if you haven't applied
        db.execute(
            _sqltext("UPDATE applications SET is_applied=false, is_interviewing=false, is_offer=false, is_hired=false WHERE id=:id"),
            {"id": str(row.id)}
        )
        logger.info(f"[UNAPPLY] UPDATE executed")
        db.flush()
        logger.info(f"[UNAPPLY] Flushed to database")
        if user_id:
            ensure_snapshot_state(
                db,
                user_id,
                include_test_rows=include_tests,
                force=True,
                reason="applications.jd_delete",
                logger=logger,
                commit=False,
            )
        db.commit()
        logger.info(f"[UNAPPLY] Transaction committed")
    except Exception as ex:
        logger.error(f"[UNAPPLY] Error during UPDATE: {ex}")
        try: db.rollback()
        except Exception: pass
        raise HTTPException(status_code=500, detail=f"unapply_failed: {ex}")
    # STEAM: Return actual DB state for verification
    db.refresh(row)
    logger.info(f"[UNAPPLY] Refreshed from DB, AFTER: is_applied={row.is_applied}, returning isApplied={bool(row.is_applied)}")
    return {"ok": True, "jdHash": jdHash, "appliedKey": row.applied_key, "changed": True, "isApplied": bool(row.is_applied)}


@applications_router.get("/jd/check-applied", response_model=dict)
def jd_check_applied(
    jdHash: str,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    """Check if a JD is currently marked as applied in the database.
    
    Returns the current is_applied state for verification after mutations.
    This ensures Resume Tailor page reflects actual database state.
    """
    row = (
        db.query(Application)
        .filter(Application.user_id == current_user.id, Application.jd_hash == jdHash)
        .order_by(Application.updated_at.desc())
        .first()
    )
    if not row:
        return {"isApplied": False, "jdHash": jdHash}
    return {"isApplied": bool(row.is_applied), "jdHash": jdHash, "appliedKey": row.applied_key}


@applications_router.patch("/stage-flags", response_model=dict)
def patch_application_stage_flags(
    body: ApplicationStageFlagsPatchBody,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    row = Application.get_by_key(db, body.applied_key)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="not_found")

    current_state = stage_payload(
        getattr(row, "stage", None),
        row.is_interviewing,
        row.is_offer,
        row.is_hired,
    )
    _, current_flags, _ = current_state

    # Apply flag updates with downward cascade:
    # Unchecking a lower flag should uncheck higher flags too
    if body.interviewing is not None:
        current_flags["interviewing"] = bool(body.interviewing)
        if not body.interviewing:
            # Unchecking I should uncheck O and H
            current_flags["offer"] = False
            current_flags["hired"] = False
    if body.offer is not None:
        current_flags["offer"] = bool(body.offer)
        if not body.offer:
            # Unchecking O should uncheck H
            current_flags["hired"] = False
    if body.hired is not None:
        current_flags["hired"] = bool(body.hired)

    normalized_state = stage_payload(
        None,
        current_flags.get("interviewing"),
        current_flags.get("offer"),
        current_flags.get("hired"),
    )
    _, normalized_flags, _ = normalized_state

    row.is_interviewing = bool(normalized_flags.get("interviewing"))
    row.is_offer = bool(normalized_flags.get("offer"))
    row.is_hired = bool(normalized_flags.get("hired"))
    if not bool(getattr(row, "is_applied", False)):
        row.is_applied = True

    stage_label = stage_label_from_flags(bool(row.is_applied), normalized_state)
    try:
        row.stage = stage_label
    except Exception:
        pass
    try:
        row.updated_at = datetime.now(timezone.utc)
    except Exception:
        pass

    db.add(row)

    user_id = int(getattr(current_user, "id", 0) or 0)
    include_tests = bool(getattr(current_user, "is_test", False))

    try:
        db.flush()
        if user_id:
            ensure_snapshot_state(
                db,
                user_id,
                include_test_rows=include_tests,
                force=True,
                reason="applications.stage_flags_patch",
                logger=logger,
                commit=False,
            )
        db.commit()
        db.refresh(row)
    except Exception as ex:
        try:
            db.rollback()
        except Exception:
            pass
        logger.error(f"applications.stage_flags_patch_failed err_type={type(ex).__name__} err_msg={str(ex)[:200]}")
        raise HTTPException(status_code=500, detail="stage_flags_failed")

    return {
        "ok": True,
        "appliedKey": row.applied_key,
        "stage": stage_label,
        "interviewing": bool(row.is_interviewing),
        "offer": bool(row.is_offer),
        "hired": bool(row.is_hired),
    }


@applications_router.post("/jd/save", response_model=JdSaveResponse)
def jd_save(
    body: JdSaveBody,
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    # Compute hashes
    jd_hash, base_hash, applied_key = compute_applied_key(current_user.id, body.jd_text, body.base_text)
    # Determine existing applied state
    existing = db.query(Application).filter(Application.user_id == current_user.id, Application.jd_hash == jd_hash).first()
    is_applied_cur = existing.is_applied if existing else False
    # Encrypt snapshot
    snapshot_dict = json.loads(body.snapshot.model_dump_json(by_alias=True, exclude_none=True))
    jd_snippet, jd_text_norm = _derive_jd_projection(body.jd_text, snapshot_dict)
    job_input_hashes = _derive_job_input_hashes(body.base_text, body.jd_text, snapshot_dict)
    try:
        snapshot_enc = encrypt_json(snapshot_dict, session=db)
    except Exception as ex:  # pragma: no cover
        raise HTTPException(status_code=500, detail=f"encrypt_failed: {ex}")
    user_id = int(getattr(current_user, "id", 0) or 0)
    include_tests = bool(getattr(current_user, "is_test", False))
    try:
        row = Application.upsert(
            db,
            user_id=current_user.id,
            jd_hash=jd_hash,
            base_hash=base_hash,
            snapshot_enc=snapshot_enc,
            company=None,
            role=None,
            jd_url=None,
            jd_snippet=jd_snippet,
            jd_text_norm=jd_text_norm,
            is_test=getattr(current_user, "is_test", False),
            is_applied=is_applied_cur,
            job_input_hashes=job_input_hashes,
        )
        db.flush()
        if user_id:
            ensure_snapshot_state(
                db,
                user_id,
                include_test_rows=include_tests,
                force=True,
                reason="applications.jd_save",
                logger=logger,
                commit=False,
            )
        db.commit()
    except Exception as ex:  # pragma: no cover
        try: db.rollback()
        except Exception: pass
        raise HTTPException(status_code=500, detail=f"save_failed: {ex}")
    return JdSaveResponse(ok=True, jdHash=jd_hash, appliedKey=row.applied_key, isApplied=row.is_applied, updatedAt=row.updated_at.isoformat())


@applications_router.get("/latest", response_model=LatestSnapshotResponse)
def get_latest_snapshot(
    current_user: Annotated[User, Depends(auth_dep.get_current_user)],
    db: Annotated[Session, Depends(auth_dep.get_db)],
):
    """Get the most recent application snapshot for the logged-in user.
    
    Used to restore session state when user logs back in - loads the last JD
    they were working on along with all outputs and model selections.
    """
    user_id = current_user.id
    include_tests = bool(getattr(current_user, "is_test", False))
    
    # Query for most recent application (by created_at)
    q = db.query(Application).filter(Application.user_id == user_id)
    if not include_tests:
        q = q.filter(sa.or_(Application.is_test.is_(False), Application.is_test.is_(None)))
    
    row = q.order_by(Application.created_at.desc()).first()
    
    if not row:
        return LatestSnapshotResponse(found=False)
    
    # Decrypt snapshot
    try:
        snapshot_dict = decrypt_json(bytes(row.snapshot_enc), session=db)
        if not isinstance(snapshot_dict, dict):
            snapshot_dict = {}
    except Exception as ex:
        logger.warning(f"Failed to decrypt snapshot for latest application: {ex}")
        snapshot_dict = {}
    
    return LatestSnapshotResponse(
        found=True,
        snapshot=snapshot_dict,
        appliedKey=row.applied_key,
        jdHash=row.jd_hash,
        isApplied=bool(row.is_applied),
        updatedAt=row.updated_at.isoformat() if row.updated_at else None,
    )


# Helper (optional) endpoint: client can compute hash server-side if desired
@applications_router.post("/jd/hash", response_model=dict)
def jd_hash(body: dict):
    jd_text = body.get("jdText") or ""
    return {"jdHash": _compute_jd_hash(jd_text)}


# ---------------- History (auto-latest per JD) endpoints ----------------
## History endpoints removed (kind collapsed into is_applied). Legacy routes intentionally gone.
