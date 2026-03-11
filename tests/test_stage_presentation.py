from __future__ import annotations

from dataclasses import dataclass

import pytest

from restailor.stage_utils import (
    StagePresentation,
    present_application_stage,
    present_stage_state,
    stage_payload,
)


@dataclass
class DummyApp:
    stage: str | None = None
    is_interviewing: bool | None = None
    is_offer: bool | None = None
    is_hired: bool | None = None
    is_applied: bool = False


@dataclass
class DummyJob:
    stage: str | None = None
    is_interviewing: bool | None = None
    is_offer: bool | None = None
    is_hired: bool | None = None


def test_present_stage_state_defaults_for_unapplied() -> None:
    state = stage_payload(None, False, False, False)
    view = present_stage_state(state, is_applied=False)
    assert isinstance(view, StagePresentation)
    assert view.has_signal is False
    assert view.output_flags == {
        "interviewing": None,
        "offer": None,
        "hired": None,
    }


def test_present_stage_state_defaults_for_applied() -> None:
    state = stage_payload(None, False, False, False)
    view = present_stage_state(state, is_applied=True)
    assert view.has_signal is False
    assert view.output_flags == {
        "interviewing": False,
        "offer": False,
        "hired": False,
    }


def test_present_stage_state_promotes_flags() -> None:
    state = stage_payload("offer", False, True, False)
    view = present_stage_state(state, is_applied=True)
    assert view.has_signal is True
    assert view.output_flags == {
        "interviewing": True,
        "offer": True,
        "hired": False,
    }


@pytest.mark.parametrize(
    "app_stage, job_stage, expected",
    [
        ("interviewing", None, {"interviewing": True, "offer": False, "hired": False}),
        (None, "offer", {"interviewing": True, "offer": True, "hired": False}),
        (None, "hired", {"interviewing": True, "offer": True, "hired": True}),
    ],
)
def test_present_application_stage_merges_job_and_app(app_stage, job_stage, expected) -> None:
    application = DummyApp(stage=app_stage, is_applied=True)
    job = DummyJob(stage=job_stage)
    view = present_application_stage(application, job=job)
    assert view.has_signal is True
    assert view.output_flags == expected
