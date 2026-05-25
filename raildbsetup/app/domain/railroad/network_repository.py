"""Abstract repository interface for railway network topology."""

from abc import ABC, abstractmethod

from app.domain.railroad.network_entities import NetworkTopologyResult


class NetworkRepository(ABC):
    """Persistence interface for the station-only railway graph."""

    @abstractmethod
    async def build_topology(
        self, snap_distance_m: float = 500.0
    ) -> NetworkTopologyResult:
        """Build the full station-only network graph from routes and stations.

        This method is idempotent: it clears any existing topology data and
        re-derives it from the ``routes`` / ``stations`` tables that were
        populated by the canonical KML and station JSON loaders.

        Args:
            snap_distance_m: Maximum distance (metres) between a station point
                and a route LineString for the station to be considered part of
                that route and for station-to-station edges to be derived.

        Returns:
            ``NetworkTopologyResult`` with counts and a list of station names
            that could not be snapped to any edge (likely data quality issues).
        """
        ...

    @abstractmethod
    async def count_nodes(self) -> int:
        """Return the number of station nodes currently stored."""
        ...

    @abstractmethod
    async def count_edges(self) -> int:
        """Return the number of directed station-to-station edges currently stored."""
        ...

    @abstractmethod
    async def count_route_stations(self) -> int:
        """Return the number of route_stations derived from the graph."""
        ...
