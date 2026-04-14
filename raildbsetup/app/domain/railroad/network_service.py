"""Domain service for railway network topology operations."""

from app.core.logging import get_logger
from app.domain.railroad.network_entities import NetworkTopologyResult
from app.domain.railroad.network_repository import NetworkRepository

logger = get_logger(__name__)


class NetworkDomainService:
    """Business-logic layer for the station-only railway graph."""

    def __init__(self, repository: NetworkRepository) -> None:
        self._repo = repository

    async def build(self, snap_distance_m: float = 500.0) -> NetworkTopologyResult:
        """Build or rebuild the network topology.

        Logs results at INFO level; delegates persistence to the repository.
        """
        logger.info("Building network topology", snap_distance_m=snap_distance_m)
        result = await self._repo.build_topology(snap_distance_m=snap_distance_m)
        if result.success:
            logger.info(
                "Network topology built",
                nodes=result.nodes_count,
                edges=result.edges_count,
                snapped=result.snapped_count,
                unsnapped_count=len(result.unsnapped_stations),
            )
            if result.unsnapped_stations:
                logger.warning(
                    "Some stations could not be matched to any route geometry",
                    stations=result.unsnapped_stations,
                )
        else:
            logger.error("Network topology build failed", error=result.error)
        return result

    async def is_built(self) -> bool:
        """Return True if the graph and derived route_stations are present."""
        return (
            await self._repo.count_edges() > 0
            and await self._repo.count_route_stations() > 0
        )
