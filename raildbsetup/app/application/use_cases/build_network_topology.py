"""Use case: build (or rebuild) the railway network topology graph.

Prerequisites:
  - Alembic migration 005_network_topology must have been applied.
  - The ``routes`` and ``stations`` tables must already be populated
    (i.e. ``InitRailroadUseCase`` must have completed successfully).

This use case is idempotent: calling it again with ``force=True``
clears the existing topology and re-derives it from the current
routes / stations data.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.railroad.network_service import NetworkDomainService
from app.infrastructure.database.repositories.network import SqlNetworkRepository

if TYPE_CHECKING:
    from app.domain.railroad.network_entities import NetworkTopologyResult

logger = get_logger(__name__)


@dataclass
class TopologyBuildResult:
    skipped: bool = False
    success: bool = False
    nodes_built: int = 0
    edges_built: int = 0
    snapped_count: int = 0
    physical_component_count: int = 0
    station_component_count: int = 0
    operational_links_count: int = 0
    main_component_station_count: int = 0
    disconnected_station_count: int = 0
    max_snap_distance_m: float | None = None
    topology_version: str | None = None
    unsnapped_stations: list[str] | None = None
    error: str | None = None


class BuildNetworkTopologyUseCase:
    def __init__(self, repository: SqlNetworkRepository) -> None:
        self._svc = NetworkDomainService(repository)

    async def execute(self, force: bool = False) -> TopologyBuildResult:
        if not force and await self._svc.is_built():
            logger.info("Network topology already present, skipping")
            return TopologyBuildResult(skipped=True, success=True)

        result: NetworkTopologyResult = await self._svc.build(
            snap_distance_m=settings.topology_snap_distance_m,
        )

        if not result.success:
            return TopologyBuildResult(error=result.error)

        if result.edges_count == 0:
            logger.warning(
                "Topology build produced 0 edges – routes may have no stations "
                "within snap_distance_m; check KML data quality"
            )

        return TopologyBuildResult(
            success=True,
            nodes_built=result.nodes_count,
            edges_built=result.edges_count,
            snapped_count=result.snapped_count,
            physical_component_count=result.physical_component_count,
            station_component_count=result.station_component_count,
            operational_links_count=result.operational_links_count,
            main_component_station_count=result.main_component_station_count,
            disconnected_station_count=result.disconnected_station_count,
            max_snap_distance_m=result.max_snap_distance_m,
            topology_version=result.topology_version,
            unsnapped_stations=result.unsnapped_stations,
        )
