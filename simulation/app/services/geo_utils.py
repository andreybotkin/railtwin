"""Pure geometry utilities for train position simulation.

No database or domain-model dependencies — all functions are stateless
and depend only on the standard library (``math``).

All polyline arithmetic uses :func:`haversine_km` for segment lengths so that
"fraction along the route" consistently means "fraction of the geodesic
distance from start to end" — this is the contract the trajectory builder
relies on when it converts ``geom_fraction`` into ``head_distance_m``.
"""

import math

__all__ = [
    "interpolate_position",
    "great_circle_bearing",
    "normalize_bearing",
    "haversine_km",
    "segment_distance_km",
    "cumulative_haversine_km",
    "project_onto_polyline",
]


def normalize_bearing(bearing: float, precision: int = 2) -> float:
    """Round a compass bearing while preserving the half-open ``[0, 360)`` range.

    Applying modulo before rounding is insufficient: values such as
    ``359.999`` round to ``360.0`` and violate the trajectory schema.
    """
    normalized = round(bearing % 360.0, precision) % 360.0
    return 0.0 if normalized == 0.0 else normalized


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


def cumulative_haversine_km(coords: list[list[float]]) -> list[float]:
    """Return running Haversine distance along a polyline in km.

    The output has the same length as ``coords``; ``[0]`` is always ``0.0``
    and ``[-1]`` is the total route length.
    """
    if not coords:
        return []
    running = 0.0
    cum = [0.0]
    for i in range(len(coords) - 1):
        running += haversine_km(
            coords[i][0], coords[i][1], coords[i + 1][0], coords[i + 1][1]
        )
        cum.append(running)
    return cum


def interpolate_position(
    coords: list[list[float]],
    progress: float,
) -> tuple[float, float]:
    """Interpolate position along a polyline at a given progress fraction.

    Segment lengths are measured with Haversine so that a given ``progress``
    lines up with :func:`segment_distance_km` / :func:`cumulative_haversine_km`
    — i.e. if ``progress = d / total_km``, the result is the point that sits
    exactly ``d`` kilometres from the polyline start along the geodesic.

    Args:
        coords: List of ``[lon, lat]`` coordinate pairs.
        progress: Progress fraction along the line (0.0 = start, 1.0 = end).

    Returns:
        ``(longitude, latitude)`` tuple.
    """
    if not coords:
        return (0.0, 0.0)
    if len(coords) == 1 or progress <= 0:
        return (coords[0][0], coords[0][1])
    if progress >= 1:
        return (coords[-1][0], coords[-1][1])

    cum = cumulative_haversine_km(coords)
    total = cum[-1]
    if total <= 0:
        return (coords[0][0], coords[0][1])

    target = progress * total
    for i in range(len(coords) - 1):
        segment_length = cum[i + 1] - cum[i]
        if cum[i + 1] >= target:
            t = (target - cum[i]) / segment_length if segment_length > 0 else 0.0
            lon = coords[i][0] + t * (coords[i + 1][0] - coords[i][0])
            lat = coords[i][1] + t * (coords[i + 1][1] - coords[i][1])
            return (lon, lat)

    return (coords[-1][0], coords[-1][1])


def great_circle_bearing(
    from_coord: tuple[float, float],
    to_coord: tuple[float, float],
) -> float:
    """Calculate Great Circle bearing between two WGS84 points.

    Returns degrees 0–360 (0 = North, clockwise).

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
    cum = cumulative_haversine_km(coords)
    total_length = cum[-1]
    if total_length == 0:
        return 0.0
    return abs(end_progress - start_progress) * total_length


def project_onto_polyline(
    coords: list[list[float]],
    point_lon: float,
    point_lat: float,
) -> tuple[float, float]:
    """Project a lon/lat point onto the closest position on a polyline.

    The projection is done per-segment in local tangent-plane coordinates
    (scaled equirectangular), which is accurate over the scales of a single
    polyline segment (sub-kilometre to tens of km) and far cheaper than a full
    spherical projection. Cumulative **distance from start** is then measured
    with Haversine so it matches :func:`cumulative_haversine_km` exactly.

    Args:
        coords: Polyline as ``[[lon, lat], ...]``.
        point_lon: Longitude of the point to project.
        point_lat: Latitude of the point to project.

    Returns:
        ``(distance_from_start_km, fraction_along_polyline)``. ``fraction`` is
        clamped to ``[0, 1]``. When the polyline is degenerate, ``(0.0, 0.0)``
        is returned.
    """
    if not coords or len(coords) < 2:
        return (0.0, 0.0)

    # Scale longitude by cos(latitude) so lon/lat deltas become comparable in a
    # flat tangent plane. Using the polyline midpoint's latitude keeps the
    # scaling stable for segments that all sit in the same region.
    lat_ref = sum(c[1] for c in coords) / len(coords)
    lon_scale = math.cos(math.radians(lat_ref))

    best_dist_sq = math.inf
    best_segment_idx = 0
    best_t = 0.0
    px = point_lon * lon_scale
    py = point_lat

    for i in range(len(coords) - 1):
        ax = coords[i][0] * lon_scale
        ay = coords[i][1]
        bx = coords[i + 1][0] * lon_scale
        by = coords[i + 1][1]
        dx = bx - ax
        dy = by - ay
        seg_len_sq = dx * dx + dy * dy
        if seg_len_sq <= 0:
            t = 0.0
        else:
            t = ((px - ax) * dx + (py - ay) * dy) / seg_len_sq
            t = max(0.0, min(1.0, t))
        proj_x = ax + t * dx
        proj_y = ay + t * dy
        dist_sq = (proj_x - px) ** 2 + (proj_y - py) ** 2
        if dist_sq < best_dist_sq:
            best_dist_sq = dist_sq
            best_segment_idx = i
            best_t = t

    cum = cumulative_haversine_km(coords)
    total_km = cum[-1]
    if total_km <= 0:
        return (0.0, 0.0)

    # Haversine distance for the partial segment we projected onto.
    a_lon, a_lat = coords[best_segment_idx]
    b_lon, b_lat = coords[best_segment_idx + 1]
    partial_lon = a_lon + best_t * (b_lon - a_lon)
    partial_lat = a_lat + best_t * (b_lat - a_lat)
    partial_km = haversine_km(a_lon, a_lat, partial_lon, partial_lat)

    dist_from_start = cum[best_segment_idx] + partial_km
    fraction = max(0.0, min(1.0, dist_from_start / total_km))
    return (dist_from_start, fraction)
