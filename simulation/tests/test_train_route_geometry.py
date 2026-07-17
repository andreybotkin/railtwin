from app.services.train_route_geometry import build_train_route_geometry


def _edge(edge_id: int, start: int, end: int, length: float):
    return {
        "type": "Feature",
        "id": edge_id,
        "geometry": {"type": "LineString", "coordinates": [[start, 0], [end, 0]]},
        "properties": {
            "from_station_id": start,
            "to_station_id": end,
            "length_m": length,
            "max_speed_kmh": 80,
        },
    }


def test_builds_composite_route_across_branch() -> None:
    edges = [
        _edge(1, 1, 2, 1000),
        _edge(2, 2, 3, 1000),
        _edge(3, 2, 4, 500),
        _edge(4, 4, 3, 5000),
    ]
    schedules = [
        {"sequence": 1, "station_id": 1, "station_name": "A"},
        {"sequence": 2, "station_id": 3, "station_name": "C"},
    ]
    result = build_train_route_geometry(schedules, edges)
    assert result["valid"] is True
    assert result["distance_km"] == 2.0
    assert [segment["edge_id"] for segment in result["segments"]] == [1, 2]
    assert [position["distance_m"] for position in result["stop_positions"]] == [
        0.0,
        2000.0,
    ]


def test_rejects_disconnected_stops() -> None:
    result = build_train_route_geometry(
        [
            {"sequence": 1, "station_id": 1, "station_name": "A"},
            {"sequence": 2, "station_id": 9, "station_name": "Z"},
        ],
        [_edge(1, 1, 2, 1000)],
    )
    assert result["valid"] is False
    assert result["coords"] == []
    assert result["issues"][0]["code"] == "disconnected_stops"


def test_rejects_two_names_resolved_to_same_station() -> None:
    result = build_train_route_geometry(
        [
            {"sequence": 1, "station_id": 1, "station_name": "Alpha"},
            {"sequence": 2, "station_id": 1, "station_name": "Beta"},
        ],
        [],
    )
    assert result["valid"] is False
    assert result["issues"][0]["code"] == "distinct_stops_share_station"
