"""Small, deterministic five-field cron parser with timezone support."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def next_cron_fire(expression: str, timezone: str, after: datetime | None = None) -> datetime:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron must have five fields: minute hour day month weekday")
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown cron timezone") from exc
    minute, hour, day, month, weekday = (
        _parse(field, low, high)
        for field, low, high in zip(fields, (0, 0, 1, 1, 0), (59, 23, 31, 12, 6), strict=True)
    )
    origin = after or datetime.now(UTC)
    if origin.tzinfo is None:
        origin = origin.replace(tzinfo=UTC)
    candidate = origin.astimezone(zone).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(60 * 24 * 366 * 2):
        cron_weekday = (candidate.weekday() + 1) % 7
        if candidate.minute in minute and candidate.hour in hour and candidate.day in day and candidate.month in month and cron_weekday in weekday:
            return candidate.astimezone(UTC).replace(tzinfo=None)
        candidate += timedelta(minutes=1)
    raise ValueError("Cron has no fire time in the next two years")


def _parse(field: str, low: int, high: int) -> set[int]:
    values: set[int] = set()
    for chunk in field.split(","):
        base, slash, step_text = chunk.partition("/")
        step = int(step_text) if slash else 1
        if step < 1:
            raise ValueError("Cron step must be positive")
        if base == "*":
            start, end = low, high
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start, end = int(start_text), int(end_text)
        else:
            start = end = int(base)
        if start < low or end > high or start > end:
            raise ValueError(f"Cron value must be between {low} and {high}")
        values.update(range(start, end + 1, step))
    return values
