from __future__ import annotations

import sqlalchemy as sa

from restailor.db import SessionLocal
from restailor.models import AnalyticsJobSnapshotState, Application
from services.analytics_job_snapshot import rebuild_snapshot_state

from scripts.compare_applications_snapshots import compare_applications_and_snapshots


def test_applications_and_snapshots_aggregates_match():
    with SessionLocal() as session:
        user_ids = set(
            uid for (uid,) in session.execute(sa.select(Application.user_id).distinct()) if uid is not None
        )
        user_ids.update(
            uid
            for (uid,) in session.execute(sa.select(AnalyticsJobSnapshotState.user_id).distinct())
            if uid is not None
        )

        for user_id in user_ids:
            rebuild_snapshot_state(session, user_id, commit=False)
        session.commit()

        diffs = compare_applications_and_snapshots(session, include_test_rows=False)

    assert not diffs, f"Snapshot aggregates diverge: {diffs}"
