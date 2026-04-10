from dataclasses import dataclass, field


@dataclass
class StationData:
    """Domain entity representing a railway station parsed from a data source."""

    name: str
    lon: float
    lat: float
    folder: str = ""
    route_type: str = "other"


@dataclass
class RouteData:
    """Domain entity representing a railway route/line."""

    name: str
    route_type: str
    color: str
    coords: list[tuple[float, float]] = field(default_factory=list)
    folder: str = ""
