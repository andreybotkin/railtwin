"""Build a train-specific track polyline from the station graph.

A timetable is not necessarily contained by one canonical KML LineString: many
services enter or leave a branch.  This module resolves every consecutive stop
pair through the directed physical graph and concatenates the resulting edges.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class _Arc:
    to_station_id: int
    length_m: float
    feature: dict[str, Any]


def _merge_coords(target: list[list[float]], source: list[list[float]]) -> None:
    if not source:
        return
    cleaned = [[float(value) for value in point[:3]] for point in source]
    if not target:
        target.extend(cleaned)
    elif target[-1][:2] == cleaned[0][:2]:
        target.extend(cleaned[1:])
    else:
        target.extend(cleaned)


def _graph(
    network_edges: list[dict[str, Any]],
) -> dict[int, list[_Arc]]:
    result: dict[int, list[_Arc]] = {}
    for feature in network_edges:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        from_id = props.get("from_station_id")
        to_id = props.get("to_station_id")
        coords = geometry.get("coordinates")
        if from_id is None or to_id is None or not coords:
            continue
        length_m = float(props.get("length_m") or 0.0)
        if length_m <= 0:
            continue
        result.setdefault(int(from_id), []).append(_Arc(int(to_id), length_m, feature))
    return result


def _shortest_path(
    graph: dict[int, list[_Arc]],
    start: int,
    end: int,
) -> list[_Arc] | None:
    if start == end:
        return []
    queue: list[tuple[float, int]] = [(0.0, start)]
    distances = {start: 0.0}
    previous: dict[int, tuple[int, _Arc]] = {}
    while queue:
        distance, station_id = heapq.heappop(queue)
        if distance != distances.get(station_id):
            continue
        if station_id == end:
            break
        for arc in graph.get(station_id, []):
            candidate = distance + arc.length_m
            if candidate < distances.get(arc.to_station_id, float("inf")):
                distances[arc.to_station_id] = candidate
                previous[arc.to_station_id] = (station_id, arc)
                heapq.heappush(queue, (candidate, arc.to_station_id))
    if end not in previous:
        return None
    path: list[_Arc] = []
    cursor = end
    while cursor != start:
        parent, arc = previous[cursor]
        path.append(arc)
        cursor = parent
    path.reverse()
    return path


def build_train_route_geometry(
    schedules: list[dict[str, Any]],
    network_edges: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a validated route payload for one ordered timetable.

    Invalid payloads deliberately contain no coordinates, preventing the
    simulation from silently falling back to an unrelated whole-line route.
    """

    ordered = sorted(schedules, key=lambda item: int(item.get("sequence") or 0))
    issues: list[dict[str, Any]] = []
    if len(ordered) < 2:
        return {"valid": False, "issues": [{"code": "insufficient_stops"}]}
    graph = _graph(network_edges)
    coords: list[list[float]] = []
    segments: list[dict[str, Any]] = []
    stop_positions: list[dict[str, Any]] = [
        {
            "schedule_id": ordered[0].get("id"),
            "sequence": ordered[0].get("sequence"),
            "station_id": ordered[0].get("station_id"),
            "distance_m": 0.0,
        }
    ]
    cumulative_m = 0.0
    path_cache: dict[tuple[int, int], list[_Arc] | None] = {}

    def _event_minutes(item: dict[str, Any], *, departure: bool) -> int | None:
        primary = "departure_time" if departure else "arrival_time"
        fallback = "arrival_time" if departure else "departure_time"
        key = primary if item.get(primary) else fallback
        value = item.get(key)
        if not value:
            return None
        parts = str(value).split(":")
        offset_key = (
            "departure_day_offset" if key == "departure_time" else "arrival_day_offset"
        )
        return (
            int(parts[0]) * 60 + int(parts[1]) + int(item.get(offset_key) or 0) * 1440
        )

    for left, right in zip(ordered, ordered[1:], strict=False):
        departure = _event_minutes(left, departure=True)
        arrival = _event_minutes(right, departure=False)
        if departure is not None and arrival is not None and arrival <= departure:
            issues.append(
                {
                    "code": "non_positive_travel_time",
                    "from": left.get("station_name"),
                    "to": right.get("station_name"),
                    "duration_minutes": arrival - departure,
                }
            )
            continue
        from_id = left.get("station_id")
        to_id = right.get("station_id")
        if from_id is None or to_id is None:
            issues.append(
                {
                    "code": "unresolved_station",
                    "from": left.get("station_name"),
                    "to": right.get("station_name"),
                }
            )
            continue
        from_id, to_id = int(from_id), int(to_id)
        if from_id == to_id:
            if left.get("station_name") != right.get("station_name"):
                issues.append(
                    {
                        "code": "distinct_stops_share_station",
                        "from": left.get("station_name"),
                        "to": right.get("station_name"),
                    }
                )
            stop_positions.append(
                {
                    "schedule_id": right.get("id"),
                    "sequence": right.get("sequence"),
                    "station_id": right.get("station_id"),
                    "distance_m": cumulative_m,
                }
            )
            continue
        key = (from_id, to_id)
        if key not in path_cache:
            path_cache[key] = _shortest_path(graph, from_id, to_id)
        path = path_cache[key]
        if path is None:
            issues.append(
                {
                    "code": "disconnected_stops",
                    "from_station_id": from_id,
                    "to_station_id": to_id,
                    "from": left.get("station_name"),
                    "to": right.get("station_name"),
                }
            )
            continue
        for arc in path:
            feature = arc.feature
            props = feature.get("properties") or {}
            edge_coords = (feature.get("geometry") or {}).get("coordinates") or []
            _merge_coords(coords, edge_coords)
            start_m = cumulative_m
            cumulative_m += arc.length_m
            segments.append(
                {
                    "edge_id": feature.get("id"),
                    "from_station_id": props.get("from_station_id"),
                    "to_station_id": props.get("to_station_id"),
                    "start_km": start_m / 1000.0,
                    "end_km": cumulative_m / 1000.0,
                    "length_km": arc.length_m / 1000.0,
                    "max_speed_kmh": props.get("max_speed_kmh"),
                    "elevation_profile": props.get("elevation_profile") or [],
                    "speed_limit_zones": props.get("speed_limit_zones") or [],
                }
            )
        stop_positions.append(
            {
                "schedule_id": right.get("id"),
                "sequence": right.get("sequence"),
                "station_id": right.get("station_id"),
                "distance_m": cumulative_m,
            }
        )

    valid = not issues and len(coords) >= 2 and cumulative_m > 0
    return {
        "valid": valid,
        "coords": coords if valid else [],
        "distance_km": cumulative_m / 1000.0 if valid else None,
        "segments": segments if valid else [],
        "stop_positions": stop_positions if valid else [],
        "issues": issues,
        "source": "station_graph",
    }
