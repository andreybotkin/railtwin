"""Use case: initialize train schedules from the canonical raw timetable files.

Strategy:
    1. Read every raw JSON file from schedule/raw/.
    2. Validate all trains before writing to the database.
    3. Replace source-managed train/schedule records from those files.
    4. Assign routes and route_stations after the load completes.
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.schedule.service import ScheduleDomainService
from app.infrastructure.database.repositories.schedule import SqlScheduleRepository
from app.infrastructure.parsers.raw_schedule_reader import read_all_raw_schedules

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.domain.schedule.entities import TrainData
    from app.domain.schedule.repository import ScheduleRepository

logger = get_logger(__name__)


@dataclass
class ScheduleInitResult:
    skipped: bool = False
    success: bool = False
    trains_loaded: int = 0
    errors: int = 0
    routes_assigned: int = 0
    route_stations_bound: int = 0
    validation_errors: list[str] = field(default_factory=list)
    unresolved_stations: list[dict[str, str | None]] = field(default_factory=list)
    failed_trains: list[dict[str, str]] = field(default_factory=list)
    error: str | None = None


class InitSchedulesUseCase:
    """Initialization use case for train schedules.

    Use the class-method ``run`` entry point.
    """

    def __init__(self, repository: ScheduleRepository) -> None:
        self._svc = ScheduleDomainService(repository)

    @classmethod
    async def run(cls, session_factory: async_sessionmaker) -> ScheduleInitResult:
        """Load all raw files into the database, replacing source-managed timetables."""
        trains = read_all_raw_schedules()
        if not trains:
            return ScheduleInitResult(
                error=f"No raw schedule data found in {settings.schedule_raw_dir}"
            )

        all_validation_errors: list[str] = []
        valid_trains: list[TrainData] = []
        for train in trains:
            errs = train.validate()
            if errs:
                all_validation_errors.extend(errs)
                logger.warning(
                    "Train failed validation, skipping",
                    train_number=train.train_number,
                    errors=errs,
                )
            else:
                valid_trains.append(train)

        if not valid_trains:
            return ScheduleInitResult(
                validation_errors=all_validation_errors,
                error="All trains failed validation; nothing to load",
            )

        if all_validation_errors:
            logger.warning(
                "Some trains had validation errors and were skipped",
                skipped=len(trains) - len(valid_trains),
                valid=len(valid_trains),
            )

        logger.info(
            "Replacing schedules from canonical raw files",
            trains_to_load=len(valid_trains),
        )

        async with session_factory() as session, session.begin():
            repo = SqlScheduleRepository(session)
            await repo.reset_source_timetable()

        loaded = 0
        errors = 0
        unresolved: list[dict[str, str | None]] = []
        failed_trains: list[dict[str, str]] = []

        for train in valid_trains:
            try:
                async with session_factory() as session, session.begin():
                    repo = SqlScheduleRepository(session, issues=unresolved)
                    repo.set_current_train(train.train_number)
                    svc = ScheduleDomainService(repo)
                    await svc.upsert_single_train(train)
                loaded += 1
                logger.debug(
                    "Train schedule saved",
                    train_number=train.train_number,
                    stops=len(train.stops),
                )
            except Exception as exc:
                errors += 1
                failed_trains.append(
                    {
                        "train_number": train.train_number,
                        "error": str(exc),
                    }
                )
                logger.error(
                    "Failed to save train schedule",
                    train_number=train.train_number,
                    error=str(exc),
                )

        logger.info(
            "Schedule replacement complete",
            trains_loaded=loaded,
            errors=errors,
            total=len(valid_trains),
        )

        routes_assigned = 0
        route_stations_bound = 0
        try:
            async with session_factory() as session, session.begin():
                repo = SqlScheduleRepository(session)
                svc = ScheduleDomainService(repo)
                routes_assigned = await svc.assign_routes()
                route_stations_bound = await svc.bind_route_stations()
            logger.info("Route assignment complete", trains_updated=routes_assigned)
        except Exception as exc:
            logger.error("Route assignment failed", error=str(exc))

        return ScheduleInitResult(
            success=loaded > 0,
            trains_loaded=loaded,
            errors=errors,
            routes_assigned=routes_assigned,
            route_stations_bound=route_stations_bound,
            validation_errors=all_validation_errors,
            unresolved_stations=unresolved,
            failed_trains=failed_trains,
        )
