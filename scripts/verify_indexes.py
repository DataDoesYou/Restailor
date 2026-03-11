from __future__ import annotations

from sqlalchemy import text
from restailor.db import engine

with engine.begin() as conn:
    rows = conn.execute(
        text(
            """
            SELECT indexname, tablename, indexdef
            FROM pg_indexes
            WHERE schemaname = 'public'
              AND indexname IN ('ix_jobs_user_created_at_desc','ix_job_outputs_job_created_at_desc')
            ORDER BY indexname
            """
        )
    ).fetchall()
    for r in rows:
        print(r)
