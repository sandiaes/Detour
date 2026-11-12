"""Daily call budget shared by external providers (architecture, section 6, rule 3).

The counter is ``app.provider_usage``; a call is reserved atomically *before* it is made, so a
crash or a timeout still counts. The UTC date is the day boundary.
"""

from sqlalchemy import Engine, text


def reserve_call(engine: Engine, provider: str, daily_budget: int) -> bool:
    """Count one call for today unless the budget is used up. Raises ``SQLAlchemyError`` if the
    database cannot be reached: the caller must then not make the call."""
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "INSERT INTO app.provider_usage (provider, usage_date, calls)"
                " VALUES (:p, (now() AT TIME ZONE 'UTC')::date, 1)"
                " ON CONFLICT (provider, usage_date) DO UPDATE SET calls = provider_usage.calls + 1"
                " WHERE provider_usage.calls < :budget RETURNING calls"
            ),
            {"p": provider, "budget": daily_budget},
        ).first()
    return row is not None
