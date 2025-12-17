"""Train simulation service.

This module provides real-time train position simulation based on
actual schedules, calculating train positions along routes.
"""

import asyncio
import json
import random
from datetime import datetime, time, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.database.models import Route, Schedule, Train
from app.repositories.route import RouteRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.train import TrainRepository

logger = get_logger(__name__)


class TrainSimulationService:
    """Service for simulating train movements.

    Calculates train positions based on schedules and route geometry,
    providing real-time position updates.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize simulation service.

        Args:
            session: Async database session.
        """
        self.train_repo = TrainRepository(session)
        self.schedule_repo = ScheduleRepository(session)
        self.route_repo = RouteRepository(session)
        self.session = session
        self._delays: dict[int, int] = {}  # train_id -> delay in minutes

    def _time_to_minutes(self, t: time) -> int:
        """Convert time to minutes since midnight.

        Args:
            t: Time object.

        Returns:
            Minutes since midnight.
        """
        return t.hour * 60 + t.minute

    def _get_current_time_minutes(self) -> int:
        """Get current time as minutes since midnight.

        Returns:
            Current time in minutes since midnight.
        """
        now = datetime.now()
        return now.hour * 60 + now.minute

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
            return coords[0] if coords else (0, 0)
        if progress >= 1:
            return coords[-1] if coords else (0, 0)

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
            return tuple(coords[0])

        target_distance = progress * total_length
        current_distance = 0.0

        for i, length in enumerate(segment_lengths):
            if current_distance + length >= target_distance:
                # Found the segment - interpolate within it
                segment_progress = (target_distance - current_distance) / length if length > 0 else 0
                lon = coords[i][0] + segment_progress * (coords[i + 1][0] - coords[i][0])
                lat = coords[i][1] + segment_progress * (coords[i + 1][1] - coords[i][1])
                return (lon, lat)
            current_distance += length

        return tuple(coords[-1])

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

    async def get_train_position(
        self,
        train: Train,
        schedules: list[Schedule],
        route_coords: list[list[float]] | None,
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

        current_minutes = self._get_current_time_minutes()

        # Add random delay if not already set
        if train.id not in self._delays:
            self._delays[train.id] = random.randint(0, 15)  # 0-15 min delay
        delay = self._delays[train.id]

        # Find current segment (between which stations)
        prev_stop = None
        next_stop = None

        for i, schedule in enumerate(schedules):
            dep_time = schedule.departure_time or schedule.arrival_time
            if not dep_time:
                continue

            dep_minutes = self._time_to_minutes(dep_time) + delay

            if dep_minutes > current_minutes:
                next_stop = schedule
                if i > 0:
                    prev_stop = schedules[i - 1]
                break
            prev_stop = schedule

        # Handle cases where train hasn't started or has finished
        if not prev_stop and next_stop:
            # Train hasn't started yet
            return None

        if prev_stop and not next_stop:
            # Train has finished for today
            return None

        # Calculate progress between stations
        prev_dep = prev_stop.departure_time or prev_stop.arrival_time
        next_arr = next_stop.arrival_time or next_stop.departure_time

        if not prev_dep or not next_arr:
            return None

        prev_minutes = self._time_to_minutes(prev_dep) + delay
        next_minutes = self._time_to_minutes(next_arr) + delay

        # Handle overnight trains
        if next_minutes < prev_minutes:
            next_minutes += 24 * 60

        segment_duration = next_minutes - prev_minutes
        if segment_duration <= 0:
            progress = 1.0
        else:
            elapsed = current_minutes - prev_minutes
            progress = max(0.0, min(1.0, elapsed / segment_duration))

        # Calculate position based on route geometry or station coordinates
        if route_coords and len(route_coords) >= 2:
            # Calculate overall progress along route
            total_stops = len(schedules)
            prev_index = schedules.index(prev_stop)
            overall_progress = (prev_index + progress) / (total_stops - 1)
            lon, lat = self._interpolate_position(route_coords, overall_progress)

            # Calculate heading
            next_progress = min(1.0, overall_progress + 0.01)
            next_lon, next_lat = self._interpolate_position(route_coords, next_progress)
            heading = self._calculate_heading((lon, lat), (next_lon, next_lat))
        else:
            # Fallback: interpolate between station locations (if available)
            # For now, return None if no route geometry
            return None

        # Estimate speed based on distance and time
        avg_speed = 60.0  # Default 60 km/h
        if route_coords and segment_duration > 0:
            # Simple distance calculation
            segment_distance_km = 50  # Placeholder
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
            "speed": round(avg_speed * random.uniform(0.8, 1.2), 1),
            "heading": round(heading, 1),
            "status": status,
            "delay_minutes": delay,
            "next_station": next_stop.station.name if next_stop.station else None,
            "prev_station": prev_stop.station.name if prev_stop.station else None,
            "progress": round(progress * 100, 1),
        }

    async def get_all_active_trains(self) -> list[dict[str, Any]]:
        """Get current positions for all active trains.

        Returns:
            List of position data for active trains.
        """
        # Get current day of week (0=Monday, 6=Sunday)
        current_day = datetime.now().weekday()

        # Get all trains with routes
        trains = await self.train_repo.get_all_with_route(skip=0, limit=100)

        positions = []
        for train in trains:
            # Get schedule for this train
            schedules = await self.schedule_repo.get_by_train(
                train.id, day_of_week=current_day
            )

            if not schedules:
                continue

            # Get route geometry
            route_coords = None
            if train.current_route_id:
                route = await self.route_repo.get_by_id_with_geometry(
                    train.current_route_id
                )
                if route and hasattr(route, "_geojson") and route._geojson:
                    geojson = json.loads(route._geojson)
                    route_coords = geojson.get("coordinates", [])

            # Calculate position
            position = await self.get_train_position(train, schedules, route_coords)
            if position:
                positions.append(position)

        return positions

    def reset_delays(self) -> None:
        """Reset all train delays (for testing or daily reset)."""
        self._delays.clear()
        logger.info("Train delays reset")
