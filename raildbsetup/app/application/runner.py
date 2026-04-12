"""SetupRunner — orchestrates the full database initialization sequence.

Provides:
  - ``run_all()``         run migrations, then railroad init, then schedule init
  - ``run_migrations()``  run Alembic migrations only (for manual re-trigger)
  - ``run_railroad()``    run only railroad init (for manual re-trigger)
  - ``run_schedules()``   run only schedule init (for manual re-trigger)
  - Status properties for the health/ready endpoint
"""

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from app.application.use_cases.build_network_topology import (
    BuildNetworkTopologyUseCase,
    TopologyBuildResult,
)
from app.application.use_cases.init_railroad import InitRailroadUseCase, RailroadInitResult
from app.application.use_cases.init_schedules import InitSchedulesUseCase, ScheduleInitResult
from app.core.logging import get_logger
from app.infrastructure.database.repositories.network import SqlNetworkRepository
from app.infrastructure.database.repositories.railroad import SqlRailroadRepository
from app.infrastructure.database.session import get_session_factory

# Project root: raildbsetup/ (3 levels up from app/application/runner.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

logger = get_logger(__name__)


class SetupRunner:
    """Stateful runner that tracks initialization progress."""

    def __init__(self) -> None:
        self._is_ready = False
        self._is_failed = False
        self._error: str | None = None
        self._current_step = "idle"
        self._status: dict[str, Any] = {}
        self._lock = asyncio.Lock()

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def is_failed(self) -> bool:
        return self._is_failed

    @property
    def error(self) -> str | None:
        return self._error

    @property
    def current_step(self) -> str:
        return self._current_step

    @property
    def status(self) -> dict[str, Any]:
        return self._status

    def mark_failed(self, error: str) -> None:
        self._is_failed = True
        self._error = error

    async def run_all(self) -> dict[str, Any]:
        """Run complete initialization: migrations → railroad → topology → schedules."""
        async with self._lock:
            self._is_ready = False
            self._is_failed = False
            self._error = None

        migration_result = await self.run_migrations()
        if not migration_result.get("success"):
            self._is_failed = True
            self._error = migration_result.get("error", "Migration failed")
            logger.error("Alembic migrations failed, aborting", error=self._error)
            return {"migrations": migration_result}

        railroad_result = await self.run_railroad()
        if railroad_result.get("error") and not railroad_result.get("skipped"):
            self._is_failed = True
            self._error = railroad_result["error"]
            logger.error("Railroad initialization failed, aborting", error=self._error)
            return {"migrations": migration_result, "railroad": railroad_result}

        topology_result = await self.run_network_topology()
        if topology_result.get("error"):
            # Topology failure is non-fatal: log and continue to schedules.
            logger.warning(
                "Network topology build failed – continuing without graph",
                error=topology_result["error"],
            )

        schedule_result = await self.run_schedules()

        self._status = {
            "migrations": migration_result,
            "railroad": railroad_result,
            "topology": topology_result,
            "schedules": schedule_result,
        }
        self._is_ready = True
        self._current_step = "done"
        logger.info("Full database initialization complete", status=self._status)
        return self._status

    async def run_migrations(self) -> dict[str, Any]:
        """Run Alembic migrations via subprocess."""
        self._current_step = "migrations"
        logger.info("Running Alembic migrations", cwd=str(_PROJECT_ROOT))
        try:
            proc = await asyncio.create_subprocess_exec(
                "alembic", "upgrade", "head",
                cwd=str(_PROJECT_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            out = stdout.decode().strip()
            err = stderr.decode().strip()
            if proc.returncode != 0:
                logger.error("Alembic migrations failed", stderr=err)
                return {"success": False, "error": err}
            logger.info("Alembic migrations applied", output=out)
            return {"success": True, "output": out}
        except Exception as exc:
            logger.error("Failed to run Alembic migrations", error=str(exc))
            return {"success": False, "error": str(exc)}

    async def run_railroad(self, force: bool = False) -> dict[str, Any]:
        self._current_step = "railroad"
        try:
            async with get_session_factory()() as session:
                async with session.begin():
                    result: RailroadInitResult = await InitRailroadUseCase(
                        SqlRailroadRepository(session)
                    ).execute(force=force)
            d = _result_to_dict(result)
            self._status["railroad"] = d
            return d
        except Exception as exc:
            logger.error("Railroad init raised unexpected exception", error=str(exc))
            d = {"success": False, "error": str(exc)}
            self._status["railroad"] = d
            return d

    async def run_network_topology(self, force: bool = False) -> dict[str, Any]:
        self._current_step = "network_topology"
        try:
            async with get_session_factory()() as session:
                async with session.begin():
                    result: TopologyBuildResult = await BuildNetworkTopologyUseCase(
                        SqlNetworkRepository(session)
                    ).execute(force=force)
            d = _result_to_dict(result)
            self._status["topology"] = d
            return d
        except Exception as exc:
            logger.error("Network topology raised unexpected exception", error=str(exc))
            d = {"success": False, "error": str(exc)}
            self._status["topology"] = d
            return d

    async def run_schedules(self) -> dict[str, Any]:
        self._current_step = "schedules"
        try:
            result: ScheduleInitResult = await InitSchedulesUseCase.run(
                get_session_factory()
            )
            d = _result_to_dict(result)
            self._status["schedules"] = d
            return d
        except Exception as exc:
            logger.error("Schedule init raised unexpected exception", error=str(exc))
            d = {"success": False, "error": str(exc)}
            self._status["schedules"] = d
            return d


def _result_to_dict(
    result: RailroadInitResult | ScheduleInitResult | TopologyBuildResult,
) -> dict[str, Any]:
    d = asdict(result)
    # Remove None values for clean JSON output
    return {k: v for k, v in d.items() if v is not None}
