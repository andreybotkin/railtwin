"""Tests for viewport-filtering helpers.

The gateway filters trajectories by the head frame (first element of
``frames``) so they only ship to the frontend when the locomotive is near
the client's viewport.
"""

from __future__ import annotations

from app.redis_payloads import (
    filter_feature_collection_by_bbox,
    filter_stations_by_bbox,
    filter_trajectories_by_bbox,
)


def _make_trajectory(
    *,
    train_id: int,
    head_lon: float,
    head_lat: float,
    generated_at_ms: int = 1,
) -> dict:
    return {
        "train_id": train_id,
        "generated_at_ms": generated_at_ms,
        "valid_until_ms": generated_at_ms + 120_000,
        "route_coords": [[head_lon, head_lat], [head_lon + 0.2, head_lat]],
        "route_length_m": 20000.0,
        "frames": [
            {
                "t_ms": generated_at_ms,
                "lon": head_lon,
                "lat": head_lat,
                "geom_fraction": 0.0,
                "head_distance_m": 0.0,
                "rotation_deg": 90.0,
                "speed_kmh": 60.0,
                "status": "moving",
            }
        ],
        "anchors": [],
        "consist": {
            "locomotive_length_m": 20.0,
            "car_count": 8,
            "car_length_m": 20.0,
            "total_length_m": 180.0,
        },
        "meta": {
            "train_id": train_id,
            "train_number": str(train_id),
            "train_type": "ordinary",
            "color": "#43A047",
            "operator": "State Railway of Thailand",
            "route_progress_pct": 0.0,
            "segment_progress_pct": 0.0,
        },
        "bounds": [head_lon, head_lat, head_lon + 0.2, head_lat],
    }


def test_filter_trajectories_by_bbox_uses_head_frame_for_position() -> None:
    trajectories = [
        _make_trajectory(train_id=11, head_lon=100.0, head_lat=13.0),
        _make_trajectory(train_id=22, head_lon=100.2, head_lat=13.0),
    ]

    filtered = filter_trajectories_by_bbox(
        trajectories,
        "99.95,12.95,100.05,13.05",
        buffer_ratio=0.1,
        min_buffer_degrees=0.0,
    )
    assert [t["train_id"] for t in filtered] == [11]


def test_filter_trajectories_by_bbox_passes_through_when_bbox_is_none() -> None:
    trajectories = [
        _make_trajectory(train_id=1, head_lon=100.0, head_lat=13.0),
        _make_trajectory(train_id=2, head_lon=101.0, head_lat=14.0),
    ]
    assert filter_trajectories_by_bbox(trajectories, None) == trajectories


def test_filter_trajectories_by_bbox_skips_entries_with_no_head_frame() -> None:
    trajectories = [
        {"train_id": 99, "frames": [], "route_coords": []},
        _make_trajectory(train_id=7, head_lon=100.0, head_lat=13.0),
    ]

    filtered = filter_trajectories_by_bbox(
        trajectories,
        "99.9,12.9,100.1,13.1",
        buffer_ratio=0.0,
        min_buffer_degrees=0.0,
    )
    assert [t["train_id"] for t in filtered] == [7]


def test_filter_trajectories_by_bbox_falls_back_to_route_coords() -> None:
    trajectory = {
        "train_id": 77,
        "frames": [],
        "route_coords": [[100.0, 13.0], [100.5, 13.0]],
    }
    filtered = filter_trajectories_by_bbox(
        [trajectory],
        "99.95,12.95,100.05,13.05",
        buffer_ratio=0.0,
        min_buffer_degrees=0.0,
    )
    assert [t["train_id"] for t in filtered] == [77]


def test_filter_stations_by_bbox_returns_only_visible_stations() -> None:
    stations = [
        {
            "id": 1,
            "code": "A",
            "location": {"type": "Point", "coordinates": [100.01, 13.01]},
        },
        {
            "id": 2,
            "code": "B",
            "location": {"type": "Point", "coordinates": [101.01, 13.01]},
        },
    ]

    filtered = filter_stations_by_bbox(
        stations,
        "99.95,12.95,100.05,13.05",
        buffer_ratio=0.0,
        min_buffer_degrees=0.0,
    )

    assert [station["id"] for station in filtered] == [1]


def test_filter_feature_collection_by_bbox_keeps_crossing_line_segments() -> None:
    collection = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[99.8, 13.0], [100.2, 13.0]],
                },
                "properties": {"route_type": "northern"},
            },
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[101.0, 13.0], [101.2, 13.0]],
                },
                "properties": {"route_type": "southern"},
            },
        ],
    }

    filtered = filter_feature_collection_by_bbox(
        collection,
        "99.95,12.95,100.05,13.05",
        buffer_ratio=0.0,
        min_buffer_degrees=0.0,
    )

    assert len(filtered["features"]) == 1
    assert filtered["features"][0]["properties"]["route_type"] == "northern"
