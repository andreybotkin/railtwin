"""Domain entities for the railway network topology graph."""

from dataclasses import dataclass, field


@dataclass
class NetworkNodeData:
    """A vertex in the railway graph.

    Graph nodes are station-only. One node corresponds to one station.
    """

    station_id: int
    lon: float
    lat: float
    node_type: str = "station"


@dataclass
class NetworkEdgeData:
    """A directed station-to-station arc along a route segment.

    The geometry stores the actual track geometry extracted from the KML route
    LineString via ST_LineSubstring.  Forward and reverse arcs are stored as
    separate rows so routing queries can scan in one direction only.
    """

    from_station_id: int
    to_station_id: int
    route_type: str
    line_name: str
    coords: list[tuple[float, float]] = field(default_factory=list)
    length_m: float = 0.0


@dataclass
class NetworkTopologyResult:
    """Summary returned after building / rebuilding the network graph."""

    nodes_count: int = 0
    edges_count: int = 0
    snapped_count: int = 0
    physical_component_count: int = 0
    station_component_count: int = 0
    operational_links_count: int = 0
    main_component_station_count: int = 0
    disconnected_station_count: int = 0
    max_snap_distance_m: float | None = None
    topology_version: str | None = None
    unsnapped_stations: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.error is None
