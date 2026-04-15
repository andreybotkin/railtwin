"""Pure geometry utilities for train position simulation.

No database or domain-model dependencies — all functions are stateless
and depend only on the standard library (``math``).
"""

import math

__all__ = [
    "interpolate_position",
    "great_circle_bearing",
    "haversine_km",
    "segment_distance_km",
]


def interpolate_position(
    coords: list[list[float]],
    progress: float,
) -> tuple[float, float]:
    """Interpolate position along a polyline at a given progress fraction.

    Args:
        coords: List of [lon, lat] coordinate pairs.
        progress: Progress fraction along the line (0.0 = start, 1.0 = end).

    Returns:
        ``(longitude, latitude)`` tuple.
    """
    if not coords:
        return (0.0, 0.0)
    if progress <= 0:
        return (coords[0][0], coords[0][1])
    if progress >= 1:
        return (coords[-1][0], coords[-1][1])

    total_length = 0.0
    segment_lengths: list[float] = []
    for i in range(len(coords) - 1):
        dx = coords[i + 1][0] - coords[i][0]
        dy = coords[i + 1][1] - coords[i][1]
        length = (dx * dx + dy * dy) ** 0.5
        segment_lengths.append(length)
        total_length += length

    if total_length == 0:
        return (coords[0][0], coords[0][1])

    target = progress * total_length
    current = 0.0
    for i, length in enumerate(segment_lengths):
        if current + length >= target:
            t = (target - current) / length if length > 0 else 0.0
            lon = coords[i][0] + t * (coords[i + 1][0] - coords[i][0])
            lat = coords[i][1] + t * (coords[i + 1][1] - coords[i][1])
            return (lon, lat)
        current += length

    return (coords[-1][0], coords[-1][1])


def great_circle_bearing(
    from_coord: tuple[float, float],
    to_coord: tuple[float, float],
) -> float:
    """Calculate Great Circle bearing between two WGS84 points.

    Returns degrees 0–360 (0 = North, clockwise).

    NOTE: intentionally returns **degrees**, not radians.
    WGS84/Leaflet adaptation: ``CanvasTrainLayer.tsx`` converts with
    ``(rotation - 90) * (Math.PI / 180)`` before drawing on canvas.
    geops mobility-toolbox-js uses radians on EPSG:3857; we stay in
    degrees because our map is WGS84 (Leaflet).

    Args:
        from_coord: Starting coordinate ``(lon, lat)``.
        to_coord: Ending coordinate ``(lon, lat)``.

    Returns:
        Bearing in degrees (0–360).
    """
    lon1, lat1 = from_coord
    lon2, lat2 = to_coord
    if lon1 == lon2 and lat1 == lat2:
        return 0.0
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon_r = math.radians(lon2 - lon1)
    y = math.sin(dlon_r) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(
        lat2_r
    ) * math.cos(dlon_r)
    bearing = math.degrees(math.atan2(y, x))
    return (bearing + 360) % 360


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distance between two WGS84 points using the Haversine formula.

    Args:
        lon1, lat1: First point coordinates (degrees).
        lon2, lat2: Second point coordinates (degrees).

    Returns:
        Distance in kilometres.
    """
    R = 6371.0  # Earth radius in km
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def segment_distance_km(
    coords: list[list[float]],
    start_progress: float,
    end_progress: float,
) -> float:
    """Distance along a route between two progress fractions.

    Uses :func:`haversine_km` for accuracy.

    Args:
        coords: List of [lon, lat] coordinate pairs.
        start_progress: Starting progress fraction (0.0–1.0).
        end_progress: Ending progress fraction (0.0–1.0).

    Returns:
        Distance in kilometres.
    """
    if not coords or len(coords) < 2:
        return 0.0
    total_length = sum(
        haversine_km(coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1])
        for i in range(len(coords) - 1)
    )
    if total_length == 0:
        return 0.0
    return abs(end_progress - start_progress) * total_length
