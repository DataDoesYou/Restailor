from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Tuple, cast

StageFlags = dict[str, bool]
StageState = Tuple[str | None, StageFlags, bool]


def _saturate_flags(flags: StageFlags) -> StageFlags:
    """Ensure stage flags are monotonic (hired ⇒ offer ⇒ interviewing)."""
    interviewing = bool(flags.get("interviewing"))
    offer = bool(flags.get("offer"))
    hired = bool(flags.get("hired"))
    if hired:
        offer = True
        interviewing = True
    elif offer:
        interviewing = True
    return {
        "interviewing": interviewing,
        "offer": offer,
        "hired": hired,
    }


def _normalize_stage_value(value: Any) -> str | None:
    if isinstance(value, str):
        stage = value.strip().lower()
        if stage:
            return stage
    return None


def stage_payload(stage_value: Any, interviewing_flag: Any, offer_flag: Any, hired_flag: Any) -> StageState:
    stage_norm = _normalize_stage_value(stage_value)
    flags: StageFlags = _saturate_flags(
        {
            "interviewing": bool(interviewing_flag),
            "offer": bool(offer_flag),
            "hired": bool(hired_flag),
        }
    )
    has_source = stage_norm is not None or any(flags.values())
    if stage_norm is None:
        if flags["hired"]:
            stage_norm = "hired"
        elif flags["offer"]:
            stage_norm = "offer"
        elif flags["interviewing"]:
            stage_norm = "interviewing"
    else:
        # If a legacy stage string exists without explicit flag values, mirror it.
        if not any(flags.values()) and stage_norm in ("interviewing", "offer", "hired"):
            flags[stage_norm] = True
            flags = _saturate_flags(flags)
    if stage_norm is not None or any(flags.values()):
        has_source = True
    flags = _saturate_flags(flags)
    return stage_norm, flags, has_source


def merge_stage_states(*states: StageState) -> StageState:
    stage_val: str | None = None
    merged_flags: StageFlags = {"interviewing": False, "offer": False, "hired": False}
    has_source = False
    for candidate_stage, candidate_flags, candidate_has_source in states:
        candidate_norm = _normalize_stage_value(candidate_stage)
        if stage_val is None and candidate_norm:
            stage_val = candidate_norm
        has_source = has_source or bool(candidate_has_source) or bool(candidate_norm)
        for key in merged_flags:
            merged_flags[key] = merged_flags[key] or bool(candidate_flags.get(key))
    merged_flags = _saturate_flags(merged_flags)
    if stage_val is None:
        if merged_flags["hired"]:
            stage_val = "hired"
        elif merged_flags["offer"]:
            stage_val = "offer"
        elif merged_flags["interviewing"]:
            stage_val = "interviewing"
    has_source = has_source or stage_val is not None or any(merged_flags.values())
    return stage_val, merged_flags, has_source


def job_stage_state(job: Any) -> StageState:
    if job is None:
        return (None, {"interviewing": False, "offer": False, "hired": False}, False)
    return stage_payload(
        getattr(job, "stage", None),
        getattr(job, "is_interviewing", None),
        getattr(job, "is_offer", None),
        getattr(job, "is_hired", None),
    )


def application_stage_state(application: Any) -> StageState:
    return stage_payload(
        getattr(application, "stage", None),
        getattr(application, "is_interviewing", None),
        getattr(application, "is_offer", None),
        getattr(application, "is_hired", None),
    )


def stage_label_from_flags(is_applied: bool, state: StageState) -> str | None:
    stage_val, flags, has_source = state
    if stage_val:
        return stage_val
    if not has_source and not is_applied:
        return None
    if flags.get("hired"):
        return "hired"
    if flags.get("offer"):
        return "offer"
    if flags.get("interviewing"):
        return "interviewing"
    return "applied" if is_applied else None


def stage_has_signal(state: StageState) -> bool:
    stage_val, flags, has_source = state
    return bool(has_source or stage_val or any(flags.values()))


def resolve_stage_for_application(
    app_state: StageState,
    is_applied: bool,
    job: Any | None = None,
    job_state: StageState | None = None,
) -> tuple[StageState, str | None]:
    effective_job_state = job_state if job_state is not None else job_stage_state(job)
    merged = merge_stage_states(app_state, effective_job_state)
    label = stage_label_from_flags(is_applied, merged)
    return merged, label


@dataclass
class StagePresentation:
    state: StageState
    label: str | None
    has_signal: bool
    monotonic_flags: StageFlags
    output_flags: dict[str, bool | None]


def present_stage_state(
    state: StageState,
    *,
    is_applied: bool,
    job: Any | None = None,
    job_state: StageState | None = None,
) -> StagePresentation:
    merged_state, label = resolve_stage_for_application(state, is_applied, job, job_state)
    monotonic_flags = dict(merged_state[1])
    has_signal = stage_has_signal(merged_state)
    if has_signal:
        output_flags = cast(
            dict[str, bool | None],
            {
                "interviewing": bool(monotonic_flags.get("interviewing")),
                "offer": bool(monotonic_flags.get("offer")),
                "hired": bool(monotonic_flags.get("hired")),
            },
        )
    else:
        default_flag = False if is_applied else None
        output_flags = {
            "interviewing": default_flag,
            "offer": default_flag,
            "hired": default_flag,
        }
    return StagePresentation(
        state=merged_state,
        label=label,
        has_signal=has_signal,
        monotonic_flags=monotonic_flags,
        output_flags=output_flags,
    )


def present_application_stage(
    application: Any,
    *,
    job: Any | None = None,
    job_state: StageState | None = None,
) -> StagePresentation:
    app_state = application_stage_state(application)
    return present_stage_state(
        app_state,
        is_applied=bool(getattr(application, "is_applied", False)),
        job=job,
        job_state=job_state,
    )
