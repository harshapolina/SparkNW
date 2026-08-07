"""SPARK cohort date window — scrapes and rankings start on this day."""

from __future__ import annotations

import os
from datetime import date, datetime, time


# Programme floor (inclusive). Scrapes stop here; scoring ignores older posts.
# Override with SPARK_COHORT_START=YYYY-MM-DD only if the programme start moves.
_DEFAULT_COHORT_START = "2026-07-15"


def cohort_start_date() -> date:
    raw = (os.getenv("SPARK_COHORT_START") or _DEFAULT_COHORT_START).strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return datetime.strptime(_DEFAULT_COHORT_START, "%Y-%m-%d").date()


def cohort_start_ymd() -> str:
    return cohort_start_date().isoformat()


def cohort_start_dt() -> datetime:
    return datetime.combine(cohort_start_date(), time.min)


def utc_today() -> date:
    return datetime.utcnow().date()


def clamp_scoring_window(
    from_date: datetime | date | None = None,
    to_date: datetime | date | None = None,
) -> tuple[datetime, datetime]:
    """Return inclusive [start, end] for SPARK scoring / Insights.

    Always floors at the cohort start (15 Jul 2026 by default) and caps at
    end-of-today (UTC) unless ``to_date`` is earlier. Missing ends default to
    cohort → today. Never raises on bad inputs.
    """
    start_day = cohort_start_date()
    today = utc_today()

    def _as_day(value: datetime | date | None) -> date | None:
        if value is None:
            return None
        try:
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, date):
                return value
        except Exception:
            return None
        return None

    from_day = _as_day(from_date)
    to_day = _as_day(to_date)

    if from_day is not None:
        start_day = max(start_day, from_day)
    if to_day is not None:
        end_day = min(today, to_day)
    else:
        end_day = today

    if end_day < start_day:
        end_day = start_day

    return (
        datetime.combine(start_day, time.min),
        datetime.combine(end_day, time(23, 59, 59)),
    )


def snapshot_floor_ymd() -> str:
    """Oldest snapshot_date to include in charts / overview."""
    return cohort_start_ymd()
