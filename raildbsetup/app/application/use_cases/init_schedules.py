"""Use case: one-time initialization of train schedules from raw timetable files.

Strategy:
  1. Read all raw JSON files from schedule/raw/ directory.
  2. Fallback to schedule/schedules_seed.json if raw dir is empty.
  3. Validate all trains before writing to database.
  4. If the DB already has >= as many trains as raw files provide → skip.
  5. Write each train in its own transaction so one bad record doesn't block all.
  6. Assign routes to trains based on station overlap.
"""

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import settings
from app.core.logging import get_logger
from app.domain.schedule.entities import TrainData
from app.domain.schedule.repository import ScheduleRepository
from app.domain.schedule.service import ScheduleDomainService
from app.infrastructure.database.repositories.schedule import SqlScheduleRepository
from app.infrastructure.parsers.raw_schedule_reader import (
    read_all_raw_schedules,
    read_seed_schedules,
)

logger = get_logger(__name__)


@dataclass
class ScheduleInitResult:
    skipped: bool = False
    success: bool = False
    trains_loaded: int = 0
    errors: int = 0
    routes_assigned: int = 0
    validation_errors: list[str] = field(default_factory=list)
    error: str | None = None


class InitSchedulesUseCase:
    """Initialization use case for train schedules.

    Use the class-method ``run`` entry point.
    """

    def __init__(self, repository: ScheduleRepository) -> None:
        self._svc = ScheduleDomainService(repository)

    @classmethod
    async def run(cls, session_factory: async_sessionmaker) -> ScheduleInitResult:
        """Load all raw files into the database, one train per transaction."""
        trains = _load_all_trains()
        if not trains:
            logger.warning(
                "No schedule data found (raw files and seed file both missing)"
            )
            return ScheduleInitResult(
                error="No schedule data found; "
                      "provide raw JSON files in schedule/raw/ or a schedules_seed.json"
            )

        # Validate all trains before touching the database
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

        seed_count = len(valid_trains)

        # Check if DB already has data
        async with session_factory() as session:
            async with session.begin():
                repo = SqlScheduleRepository(session)
                svc = ScheduleDomainService(repo)
                needs = await svc.needs_seeding(seed_count)

        if not needs:
            logger.info(
                "Schedules already present in DB, skipping initial load",
                seed_count=seed_count,
            )
            return ScheduleInitResult(skipped=True)

        logger.info("Initializing schedules from data files", trains_to_load=seed_count)

        loaded = 0
        errors = 0

        for train in valid_trains:
            try:
                async with session_factory() as session:
                    async with session.begin():
                        repo = SqlScheduleRepository(session)
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
                logger.error(
                    "Failed to save train schedule",
                    train_number=train.train_number,
                    error=str(exc),
                )

        logger.info(
            "Schedule initialization complete",
            trains_loaded=loaded,
            errors=errors,
            total=seed_count,
        )

        # Assign routes to trains based on station overlap
        routes_assigned = 0
        try:
            async with session_factory() as session:
                async with session.begin():
                    repo = SqlScheduleRepository(session)
                    svc = ScheduleDomainService(repo)
                    routes_assigned = await svc.assign_routes()
            logger.info("Route assignment complete", trains_updated=routes_assigned)
        except Exception as exc:
            logger.error("Route assignment failed", error=str(exc))

        return ScheduleInitResult(
            success=True,
            trains_loaded=loaded,
            errors=errors,
            routes_assigned=routes_assigned,
            validation_errors=all_validation_errors,
        )


def _load_all_trains() -> list[TrainData]:
    """Load trains from raw files, falling back to the seed file."""
    trains = read_all_raw_schedules()
    if trains:
        logger.info("Using raw schedule files", count=len(trains))
        return trains

    logger.info("Raw schedule directory empty, trying seed file")
    trains = read_seed_schedules()
    if trains:
        logger.info("Using seed schedule file", count=len(trains))
    return trains
