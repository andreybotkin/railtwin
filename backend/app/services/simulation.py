"""Train simulation service.

This module provides real-time train position simulation based on
actual schedules, calculating train positions along routes.
"""

import json
from datetime import datetime, time, timedelta, timezone
from typing import Any

from geoalchemy2.shape import to_shape
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Schedule, Train
from app.repositories.route import RouteRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.train import TrainRepository
from app.services.tts_scraper import get_delays_from_redis

# Bangkok timezone offset (UTC+7)
_BANGKOK_OFFSET = timedelta(hours=7)

logger = get_logger(__name__)


class TrainSimulationService:
    """Service for simulating train movements.

    Calculates train positions based on schedules and route geometry,
    providing real-time position updates.
    """

    def __init__(
        self, session: AsyncSession, redis_client: Redis | None = None
    ) -> None:
        """Initialize simulation service.

        Args:
            session: Async database session.
            redis_client: Optional Redis client for reading TTS delay data.
        """
        self.train_repo = TrainRepository(session)
        self.schedule_repo = ScheduleRepository(session)
        self.route_repo = RouteRepository(session)
        self.session = session
        self._redis = redis_client
        # Cache of tts delays: {train_number: delay_minutes}
        self._tts_delays: dict[str, int] = {}

    def _time_to_minutes(self, t: time) -> int:
        """Convert time to minutes since midnight.

        Args:
            t: Time object.

        Returns:
            Minutes since midnight.
        """
        return t.hour * 60 + t.minute

    def _get_current_time_minutes(self) -> float:
        """Get current time as fractional minutes since midnight (Bangkok time, UTC+7).

        Returns fractional minutes so positions update every second, not every minute.
        """
        now = datetime.now(timezone.utc) + _BANGKOK_OFFSET  # noqa: UP017
        return now.hour * 60 + now.minute + now.second / 60.0

    def _get_schedule_minutes(
        self,
        schedule: Schedule,
        *,
        prefer_departure: bool,
    ) -> int | None:
        """Return absolute schedule minutes including overnight day offsets."""
        if prefer_departure:
            if schedule.departure_time is not None:
                return (
                    self._time_to_minutes(schedule.departure_time)
                    + int(schedule.departure_day_offset) * 24 * 60
                )
            if schedule.arrival_time is not None:
                return (
                    self._time_to_minutes(schedule.arrival_time)
                    + int(schedule.arrival_day_offset) * 24 * 60
                )
            return None

        if schedule.arrival_time is not None:
            return (
                self._time_to_minutes(schedule.arrival_time)
                + int(schedule.arrival_day_offset) * 24 * 60
            )
        if schedule.departure_time is not None:
            return (
                self._time_to_minutes(schedule.departure_time)
                + int(schedule.departure_day_offset) * 24 * 60
            )
        return None

    def _get_candidate_current_minutes(
        self,
        schedules: list[Schedule],
    ) -> float | None:
        """Match current time against today or yesterday service start for overnight runs."""
        first_departure = self._get_schedule_minutes(
            schedules[0], prefer_departure=True
        )
        last_arrival = self._get_schedule_minutes(schedules[-1], prefer_departure=False)
        if first_departure is None or last_arrival is None:
            return None

        current_minutes = self._get_current_time_minutes()
        current_weekday = (
            datetime.now(timezone.utc) + _BANGKOK_OFFSET  # noqa: UP017
        ).weekday()
        overnight = any(
            schedule.arrival_day_offset > 0 or schedule.departure_day_offset > 0
            for schedule in schedules
        )
        service_days = schedules[0].day_of_week

        candidates = [(current_weekday, current_minutes)]
        if overnight:
            candidates.insert(0, ((current_weekday - 1) % 7, current_minutes + 24 * 60))

        for service_weekday, absolute_minutes in candidates:
            if service_days and service_weekday not in service_days:
                continue
            if first_departure <= absolute_minutes <= last_arrival:
                return absolute_minutes
        return None

    def _get_stop_progress(
        self,
        schedule: Schedule,
        index: int,
        total_stops: int,
        route_distance_km: float | None,
    ) -> float:
        """Resolve stop progress along the route using stored timetable metadata."""
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

    def _interpolate_position(
        self,
        coords: list[list[float]],
        progress: float,
    ) -> tuple[float, float]:
        """Interpolate position along a line at given progress.

        Args:
            coords: List of [lon, lat] coordinates.
            progress: Progress along line (0.0 to 1.0).

        Returns:
            Tuple of (longitude, latitude).
        """
        if not coords or progress <= 0:
            return (coords[0][0], coords[0][1]) if coords else (0.0, 0.0)
        if progress >= 1:
            return (coords[-1][0], coords[-1][1]) if coords else (0.0, 0.0)

        # Calculate total length and find segment
        total_length = 0.0
        segment_lengths = []

        for i in range(len(coords) - 1):
            dx = coords[i + 1][0] - coords[i][0]
            dy = coords[i + 1][1] - coords[i][1]
            length = (dx * dx + dy * dy) ** 0.5
            segment_lengths.append(length)
            total_length += length

        if total_length == 0:
            return (coords[0][0], coords[0][1])

        target_distance = progress * total_length
        current_distance = 0.0

        for i, length in enumerate(segment_lengths):
            if current_distance + length >= target_distance:
                # Found the segment - interpolate within it
                segment_progress = (
                    (target_distance - current_distance) / length if length > 0 else 0
                )
                lon = coords[i][0] + segment_progress * (
                    coords[i + 1][0] - coords[i][0]
                )
                lat = coords[i][1] + segment_progress * (
                    coords[i + 1][1] - coords[i][1]
                )
                return (lon, lat)
            current_distance += length

        return (coords[-1][0], coords[-1][1])

    def _calculate_heading(
        self,
        from_coord: tuple[float, float],
        to_coord: tuple[float, float],
    ) -> float:
        """Calculate heading between two points.

        Args:
            from_coord: Starting coordinate (lon, lat).
            to_coord: Ending coordinate (lon, lat).

        Returns:
            Heading in degrees (0-360).
        """
        import math

        dx = to_coord[0] - from_coord[0]
        dy = to_coord[1] - from_coord[1]

        if dx == 0 and dy == 0:
            return 0.0

        heading = math.degrees(math.atan2(dx, dy))
        return (heading + 360) % 360

    def _calculate_segment_distance(
        self,
        coords: list[list[float]],
        start_progress: float,
        end_progress: float,
    ) -> float:
        """Calculate distance along route between two progress points.

        Uses Haversine formula for accurate distance calculation.

        Args:
            coords: List of [lon, lat] coordinates.
            start_progress: Starting progress (0.0 to 1.0).
            end_progress: Ending progress (0.0 to 1.0).

        Returns:
            Distance in kilometers.
        """
        import math

        def haversine_distance(
            lon1: float, lat1: float, lon2: float, lat2: float
        ) -> float:
            """Calculate distance between two points using Haversine formula."""
            R = 6371  # Earth's radius in kilometers

            lat1_rad = math.radians(lat1)
            lat2_rad = math.radians(lat2)
            delta_lat = math.radians(lat2 - lat1)
            delta_lon = math.radians(lon2 - lon1)

            a = (
                math.sin(delta_lat / 2) ** 2
                + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
            )
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

            return R * c

        if not coords or len(coords) < 2:
            return 0.0

        # Calculate total length of route
        total_length = 0.0
        segment_lengths = []

        for i in range(len(coords) - 1):
            length = haversine_distance(
                coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]
            )
            segment_lengths.append(length)
            total_length += length

        if total_length == 0:
            return 0.0

        # Calculate distance between progress points
        start_distance = start_progress * total_length
        end_distance = end_progress * total_length

        return end_distance - start_distance

    async def get_train_position(
        self,
        train: Train,
        schedules: list[Schedule],
        route_coords: list[list[float]] | None,
        route_distance_km: float | None = None,
    ) -> dict[str, Any] | None:
        """Calculate current position for a train.

        Args:
            train: Train object.
            schedules: Train's schedule entries in order.
            route_coords: Route coordinates as list of [lon, lat].

        Returns:
            Position data dict or None if train is not active.
        """
        if not schedules or len(schedules) < 2:
            return None

        current_minutes = self._get_candidate_current_minutes(schedules)
        if current_minutes is None:
            return None

        # Look up delay from TTS data or fall back to 0
        delay = self._tts_delays.get(train.train_number, 0)

        # Find current segment (between which stations)
        prev_stop = None
        next_stop = None

        for i, schedule in enumerate(schedules):
            dep_minutes = self._get_schedule_minutes(schedule, prefer_departure=True)
            if dep_minutes is None:
                continue
            dep_minutes += delay

            if dep_minutes > current_minutes:
                next_stop = schedule
                if i > 0:
                    prev_stop = schedules[i - 1]
                break
            prev_stop = schedule

        # Handle cases where train hasn't started or has finished
        if prev_stop is None or next_stop is None:
            return None

        # Calculate progress between stations
        prev_minutes = self._get_schedule_minutes(prev_stop, prefer_departure=True)
        next_minutes = self._get_schedule_minutes(next_stop, prefer_departure=False)

        if prev_minutes is None or next_minutes is None:
            return None

        prev_minutes += delay
        next_minutes += delay

        segment_duration = next_minutes - prev_minutes
        if segment_duration <= 0:
            progress = 1.0
        else:
            elapsed = current_minutes - prev_minutes
            progress = max(0.0, min(1.0, elapsed / segment_duration))

        # Calculate position based on route geometry or station coordinates
        if route_coords and len(route_coords) >= 2:
            total_stops = len(schedules)
            prev_index = schedules.index(prev_stop)
            next_index = schedules.index(next_stop)
            start_progress = self._get_stop_progress(
                prev_stop,
                prev_index,
                total_stops,
                route_distance_km,
            )
            end_progress = self._get_stop_progress(
                next_stop,
                next_index,
                total_stops,
                route_distance_km,
            )
            overall_progress = start_progress + (
                (end_progress - start_progress) * progress
            )
            lon, lat = self._interpolate_position(route_coords, overall_progress)

            # Calculate heading
            heading_progress = min(1.0, max(overall_progress + 0.01, end_progress))
            next_lon, next_lat = self._interpolate_position(
                route_coords, heading_progress
            )
            heading = self._calculate_heading((lon, lat), (next_lon, next_lat))
        else:
            # Fallback: interpolate between station locations when route geometry is unavailable.
            if prev_stop.station is None or next_stop.station is None:
                return None

            prev_point = to_shape(prev_stop.station.location)
            next_point = to_shape(next_stop.station.location)
            prev_coords = (float(prev_point.x), float(prev_point.y))
            next_coords = (float(next_point.x), float(next_point.y))

            lon = prev_coords[0] + ((next_coords[0] - prev_coords[0]) * progress)
            lat = prev_coords[1] + ((next_coords[1] - prev_coords[1]) * progress)
            heading = self._calculate_heading(prev_coords, next_coords)

        # Estimate speed based on distance and time
        avg_speed = 60.0  # Default 60 km/h
        if route_coords and segment_duration > 0:
            segment_distance_km = self._calculate_segment_distance(
                route_coords,
                start_progress,
                end_progress,
            )

            if segment_distance_km > 0:
                avg_speed = segment_distance_km / (segment_duration / 60)

        status = "moving"
        if progress < 0.05 or progress > 0.95:
            status = "at_station"

        return {
            "train_id": train.id,
            "train_number": train.train_number,
            "train_type": train.train_type,
            "location": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "speed": round(avg_speed, 1),
            "heading": round(heading, 1),
            "status": status,
            "delay_minutes": delay,
            "next_station": (
                next_stop.station.name if next_stop.station else next_stop.station_name
            ),
            "prev_station": (
                prev_stop.station.name if prev_stop.station else prev_stop.station_name
            ),
            "progress": round(progress * 100, 1),
        }

    async def get_all_active_trains(self) -> list[dict[str, Any]]:
        """Get current positions for all active trains.

        Returns:
            List of position data for active trains.
        """
        # Load latest TTS delay corrections from Redis
        if self._redis is not None:
            try:
                self._tts_delays = await get_delays_from_redis(self._redis)
            except Exception as exc:
                logger.warning("Could not load TTS delays from Redis", error=str(exc))

        positions = []
        batch_size = 100
        skip = 0

        while True:
            trains = await self.train_repo.get_all_with_route(skip=skip, limit=batch_size)
            if not trains:
                break

            for train in trains:
                schedules = await self.schedule_repo.get_by_train(train.id)

                if not schedules:
                    continue

                route_coords = None
                route_distance_km = None
                if train.current_route_id:
                    route = await self.route_repo.get_by_id_with_geometry(
                        train.current_route_id
                    )
                    if route and hasattr(route, "_geojson") and route._geojson:
                        geojson = json.loads(route._geojson)
                        route_coords = geojson.get("coordinates", [])
                        route_distance_km = (
                            float(route.distance_km) if route.distance_km else None
                        )

                position = await self.get_train_position(
                    train,
                    schedules,
                    route_coords,
                    route_distance_km=route_distance_km,
                )
                if position:
                    positions.append(position)

            if len(trains) < batch_size:
                break

            skip += batch_size

        return positions

    def reset_delays(self) -> None:
        """Reset cached TTS delay corrections."""
        self._tts_delays.clear()
        logger.info("Train delays reset")
