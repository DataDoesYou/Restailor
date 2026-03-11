from __future__ import annotations

"""Quick analysis of real token completeness and potential under/over charge.

Outputs:
- total charges
- counts: real_complete, real_partial, no_real
- percentage completeness
- estimated vs real aggregate deltas (only where real_complete)
- average estimation error % (prompt+completion separately when both real)
- top 10 largest absolute price delta rows (if any)

Run via: doppler run -- poetry run python scripts/analyze_token_billing.py
"""
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from restailor.db import SessionLocal
from restailor.models import Charge


def quantize(x: Decimal | None) -> Decimal | None:
    if x is None:
        return None
    return x.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def main() -> None:
    with SessionLocal() as session:
        total = session.execute(select(func.count(Charge.id))).scalar_one()
        real_complete = session.execute(
            select(func.count(Charge.id)).where(Charge.cost_usd_real.isnot(None))
        ).scalar_one()
        # partial real tokens: either flag set or one side null XOR other non-null
        partial = session.execute(
            select(func.count(Charge.id)).where(
                (Charge.is_partial_real_tokens.is_(True))
            )
        ).scalar_one()
        no_real = total - real_complete - partial
        pct_complete = (real_complete / total * 100.0) if total else 0.0
        pct_partial = (partial / total * 100.0) if total else 0.0

        # Aggregate deltas for complete rows
        agg = session.execute(
            select(
                func.coalesce(func.sum(Charge.price_to_user_usd_real - Charge.price_to_user_usd), 0),
                func.coalesce(func.sum(Charge.cost_usd_real - Charge.cost_usd), 0),
                func.count(Charge.id),
            ).where(Charge.cost_usd_real.isnot(None))
        ).first()
        price_delta_sum, cost_delta_sum, real_rows = agg if agg else (0, 0, 0)

        # Estimation error percentages (prompt & completion) only for rows with both sides
        # Avoid division by zero
        est_err_prompt = session.execute(
            select(func.avg(((Charge.prompt_tokens - Charge.prompt_tokens_real) * 100.0) / func.nullif(Charge.prompt_tokens_real, 0)))
            .where(Charge.prompt_tokens_real.isnot(None), Charge.completion_tokens_real.isnot(None))
        ).scalar()
        est_err_completion = session.execute(
            select(func.avg(((Charge.completion_tokens - Charge.completion_tokens_real) * 100.0) / func.nullif(Charge.completion_tokens_real, 0)))
            .where(Charge.prompt_tokens_real.isnot(None), Charge.completion_tokens_real.isnot(None))
        ).scalar()

        # Largest absolute price delta examples
        top_rows = session.execute(
            select(
                Charge.id,
                Charge.job_id,
                Charge.model,
                Charge.prompt_tokens,
                Charge.completion_tokens,
                Charge.prompt_tokens_real,
                Charge.completion_tokens_real,
                Charge.price_to_user_usd,
                Charge.price_to_user_usd_real,
                (Charge.price_to_user_usd_real - Charge.price_to_user_usd).label("price_diff"),
            )
            .where(Charge.price_to_user_usd_real.isnot(None))
            .order_by(func.abs(Charge.price_to_user_usd_real - Charge.price_to_user_usd).desc())
            .limit(10)
        ).all()

        print("Total charges:", total)
        print("Real complete rows:", real_complete)
        print("Partial real rows:", partial)
        print("No real rows:", no_real)
        print(f"Completeness: {pct_complete:.2f}% complete, {pct_partial:.2f}% partial")
        print("Sum price delta (real - est):", price_delta_sum)
        print("Sum cost delta (real - est):", cost_delta_sum)
        if real_rows:
            print("Avg prompt est error %:", f"{est_err_prompt:.2f}" if est_err_prompt is not None else "n/a")
            print("Avg completion est error %:", f"{est_err_completion:.2f}" if est_err_completion is not None else "n/a")
        print("Top 10 absolute price deltas (if any):")
        for r in top_rows:
            print(
                str(r.id),
                str(r.job_id),
                r.model,
                f"p_est={r.prompt_tokens} p_real={r.prompt_tokens_real}",
                f"c_est={r.completion_tokens} c_real={r.completion_tokens_real}",
                f"price_est={r.price_to_user_usd} price_real={r.price_to_user_usd_real}",
                f"diff={r.price_diff}",
            )

        # Undercharge detection: any row where real price > estimate
        undercharge_rows = session.execute(
            select(func.count(Charge.id)).where(
                Charge.price_to_user_usd_real.isnot(None),
                Charge.price_to_user_usd_real > Charge.price_to_user_usd,
            )
        ).scalar_one()
        overcharge_rows = session.execute(
            select(func.count(Charge.id)).where(
                Charge.price_to_user_usd_real.isnot(None),
                Charge.price_to_user_usd_real < Charge.price_to_user_usd,
            )
        ).scalar_one()
        print(f"Rows undercharged (real>est): {undercharge_rows}")
        print(f"Rows overcharged (real<est): {overcharge_rows}")


if __name__ == "__main__":
    main()
