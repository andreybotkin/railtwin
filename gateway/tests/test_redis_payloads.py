from app.redis_payloads import filter_trajectories_by_bbox


def _traj(train_id: int, lon: float, lat: float) -> dict:
    return {
        "train_id": train_id,
        "generated_at_ms": 1,
        "valid_until_ms": 2,
        "route_coords": [[lon, lat], [lon + 0.1, lat + 0.1]],
        "route_length_m": 1000,
        "frames": [
            {
                "t_ms": 1,
                "lon": lon,
                "lat": lat,
                "geom_fraction": 0,
                "rotation_deg": 0,
                "speed_kmh": 20,
                "status": "moving",
            }
        ],
        "anchors": [],
        "consist": {"locomotive_length_m": 20, "car_count": 8, "car_length_m": 20},
        "meta": {"train_id": train_id, "train_number": str(train_id), "color": "#fff"},
    }


def test_filter_trajectories_by_bbox_uses_first_frame_head_point() -> None:
    trajectories = [_traj(1, 100.0, 13.0), _traj(2, 110.0, 20.0)]
    filtered = filter_trajectories_by_bbox(trajectories, "99.9,12.9,100.2,13.2", buffer_ratio=0, min_buffer_degrees=0)
    assert [item["train_id"] for item in filtered] == [1]


def test_filter_trajectories_by_bbox_with_buffer_keeps_nearby_heads() -> None:
    trajectories = [_traj(3, 100.29, 13.29)]
    filtered = filter_trajectories_by_bbox(trajectories, "100,13,100.2,13.2", buffer_ratio=0.5, min_buffer_degrees=0)
    assert [item["train_id"] for item in filtered] == [3]
