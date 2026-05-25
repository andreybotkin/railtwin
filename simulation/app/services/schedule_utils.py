"""Pure schedule/time helpers for train simulation.

Depends only on the ``Schedule`` domain model; zero database I/O.
All functions are module-level so they can be used without instantiating
a service object—and easily tested without any mocking.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.database.models import Schedule

__all__ = [
    "BANGKOK_OFFSET",
    "time_to_minutes",
    "get_current_time_minutes",
    "get_schedule_minutes",
    "get_arrival_departure_minutes",
    "candidate_current_minutes",
    "get_stop_progress",
]

# Bangkok standard time offset (UTC+7, no DST)
BANGKOK_OFFSET = timedelta(hours=7)


def time_to_minutes(t: time) -> int:
    """Convert a :class:`datetime.time` to minutes since midnight."""
    return t.hour * 60 + t.minute


def get_current_time_minutes() -> float:
    """Return current Bangkok time as fractional minutes since midnight.

    Uses ``now.second / 60`` so sub-minute movement is visible.
    """
    now = datetime.now(timezone.utc) + BANGKOK_OFFSET  # noqa: UP017
    return now.hour * 60 + now.minute + now.second / 60.0


def get_schedule_minutes(
    schedule: Schedule,
    *,
    prefer_departure: bool,
) -> int | None:
    """Return the absolute minutes for a schedule entry, including day offsets.

    Absolute minutes means minutes-since-midnight *of the service start day*
    plus ``day_offset * 24 * 60`` for overnight trains.

    Args:
        schedule: A single :class:`Schedule` row.
        prefer_departure: When ``True``, return departure time if available,
            falling back to arrival.  When ``False``, prefer arrival.

    Returns:
        Absolute minutes, or ``None`` if neither time is set.
    """
    if prefer_departure:
        if schedule.departure_time is not None:
            return (
                time_to_minutes(schedule.departure_time)
                + int(schedule.departure_day_offset) * 24 * 60
            )
        if schedule.arrival_time is not None:
            return (
                time_to_minutes(schedule.arrival_time)
                + int(schedule.arrival_day_offset) * 24 * 60
            )
        return None

    if schedule.arrival_time is not None:
        return (
            time_to_minutes(schedule.arrival_time)
            + int(schedule.arrival_day_offset) * 24 * 60
        )
    if schedule.departure_time is not None:
        return (
            time_to_minutes(schedule.departure_time)
            + int(schedule.departure_day_offset) * 24 * 60
        )
    return None


def get_arrival_departure_minutes(
    schedule: Schedule,
) -> tuple[int | None, int | None]:
    """Return absolute arrival/departure minutes for a stop, if available."""
    arrival_minutes = None
    departure_minutes = None

    if schedule.arrival_time is not None:
        arrival_minutes = (
            time_to_minutes(schedule.arrival_time)
            + int(schedule.arrival_day_offset) * 24 * 60
        )

    if schedule.departure_time is not None:
        departure_minutes = (
            time_to_minutes(schedule.departure_time)
            + int(schedule.departure_day_offset) * 24 * 60
        )

    return arrival_minutes, departure_minutes


def candidate_current_minutes(
    schedules: list[Schedule],
    current_minutes: float,
    delay: int = 0,
) -> float | None:
    """Match *current_minutes* against today's or yesterday's service window.

    Overnight trains (day_offset > 0) are matched against the *previous*
    calendar day as well, so a train departing at 23:50 and arriving at
    02:10 (+1) is still tracked after midnight.

    Args:
        schedules: Train schedule entries in sequence order.
        current_minutes: Current Bangkok time as fractional minutes since
            midnight (pre-computed by the caller so that tests can inject a
            fixed value via ``monkeypatch``).

    Returns:
        The absolute-minutes value to compare against schedule times, or
        ``None`` if the train is not currently running.
    """
    first_departure = get_schedule_minutes(schedules[0], prefer_departure=True)
    last_arrival = get_schedule_minutes(schedules[-1], prefer_departure=False)
    if first_departure is None or last_arrival is None:
        return None

    # Expand the service window bounds to include the delay.
    # Note: If delay is negative (early), it expands the window earlier.
    # If delay is positive (late), it expands the window later.
    # We want to ensure the train is visible early and stays visible late.
    if delay > 0:
        last_arrival += delay
    elif delay < 0:
        first_departure += delay

    now_dt = datetime.now(timezone.utc) + BANGKOK_OFFSET  # noqa: UP017
    current_weekday = now_dt.weekday()

    overnight = any(
        s.arrival_day_offset > 0 or s.departure_day_offset > 0 for s in schedules
    )
    service_days = schedules[0].day_of_week

    # Check today first; then yesterday for overnight services.
    candidates: list[tuple[int, float]] = [(current_weekday, current_minutes)]
    if overnight:
        candidates.insert(0, ((current_weekday - 1) % 7, current_minutes + 24 * 60))

    for service_weekday, absolute_minutes in candidates:
        if service_days and service_weekday not in service_days:
            continue
        if first_departure <= absolute_minutes <= last_arrival:
            return absolute_minutes
    return None


def get_stop_progress(
    schedule: Schedule,
    index: int,
    total_stops: int,
    route_distance_km: float | None,
) -> float:
    """Resolve a stop's progress fraction (0.0–1.0) along the route.

    Priority order:
    1. ``schedule.route_station.distance_from_start / route_distance_km``.
    1. ``schedule.route_progress`` (stored explicitly).
    2. ``schedule.distance_from_origin_km / route_distance_km``.
    3. Linear interpolation by stop index.
    """
    route_station = getattr(schedule, "route_station", None)
    if (
        route_station is not None
        and route_station.distance_from_start is not None
        and route_distance_km
    ):
        return min(
            1.0,
            max(0.0, float(route_station.distance_from_start) / route_distance_km),
        )
    if schedule.route_progress is not None:
        return float(schedule.route_progress)
    if schedule.distance_from_origin_km is not None and route_distance_km:
        return min(
            1.0,
            max(0.0, float(schedule.distance_from_origin_km) / route_distance_km),
        )
    if total_stops <= 1:
        return 0.0
    return index / (total_stops - 1)
