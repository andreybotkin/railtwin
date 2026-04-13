from app.redis_payloads import (
    filter_feature_collection_by_bbox,
    filter_positions_by_bbox,
    filter_stations_by_bbox,
    filter_trajectories_by_bbox,
)


def test_filter_positions_by_bbox_applies_buffer() -> None:
    positions = [
        {
            "train_id": 1,
            "location": {"type": "Point", "coordinates": [100.05, 13.05]},
        },
        {
            "train_id": 2,
            "location": {"type": "Point", "coordinates": [100.14, 13.05]},
        },
        {
            "train_id": 3,
            "location": {"type": "Point", "coordinates": [100.35, 13.05]},
        },
    ]

    filtered = filter_positions_by_bbox(
        positions,
        "100.0,13.0,100.1,13.1",
        buffer_ratio=0.5,
        min_buffer_degrees=0.0,
    )

    assert [position["train_id"] for position in filtered] == [1, 2]


def test_filter_trajectories_by_bbox_uses_current_position_not_route_bounds() -> None:
    trajectories = [
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [99.8, 13.0],
                    [100.0, 13.0],
                    [100.2, 13.0],
                ],
            },
            "properties": {
                "train_id": 11,
                "timestamp": 1,
                "time_intervals": [[1, 0.5, 0.0]],
                "bounds": [99.8, 13.0, 100.2, 13.0],
            },
        },
        {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [99.8, 13.0],
                    [100.0, 13.0],
                    [100.2, 13.0],
                ],
            },
            "properties": {
                "train_id": 22,
                "timestamp": 1,
                "time_intervals": [[1, 0.95, 0.0]],
                "bounds": [99.8, 13.0, 100.2, 13.0],
            },
        },
    ]

    filtered = filter_trajectories_by_bbox(
        trajectories,
        "99.95,12.95,100.05,13.05",
        buffer_ratio=0.1,
        min_buffer_degrees=0.0,
    )

    assert [trajectory["properties"]["train_id"] for trajectory in filtered] == [11]


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