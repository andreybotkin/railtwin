"""Use case: one-time initialization of train schedules from raw timetable files.

On first startup the database is empty. This use case reads every JSON file in
``schedule/raw/``, builds the full train+schedule records and writes them to
the database one train at a time (each in its own transaction), so a bad file
does not roll back the entire dataset.

On subsequent restarts (DB already has >= as many trains as raw files) the use
case exits early without writing anything.
"""

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.logging import get_logger
from app.domain.schedule.repository import ScheduleRepository
from app.domain.schedule.service import ScheduleDomainService
from app.infrastructure.database.repositories.schedule import SqlScheduleRepository
from app.infrastructure.scrapers.raw_schedule_reader import read_all_raw_schedules

logger = get_logger(__name__)


class InitSchedulesUseCase:
    """Initialization use case. Use the ``run`` class-method entry point."""

    def __init__(self, repository: ScheduleRepository) -> None:
        self._svc = ScheduleDomainService(repository)

    # ------------------------------------------------------------------ #
    # Class-method entry point (manages its own sessions)                 #
    # ------------------------------------------------------------------ #

    @classmethod
    async def run(cls, session_factory: async_sessionmaker) -> dict:
        """Load all raw files into the database, one train per transaction.

        Args:
            session_factory: SQLAlchemy async session factory.

        Returns:
            Status dict with ``skipped``, ``trains_loaded``, and ``errors`` keys.
        """
        trains = read_all_raw_schedules()
        if not trains:
            logger.warning("No raw schedule files found; schedule not initialized")
            return {"success": False, "reason": "no_raw_files"}

        seed_count = len(trains)

        # Check DB count using a short-lived read session
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
            return {"skipped": True, "reason": "already_initialized"}

        logger.info(
            "Initializing schedules from raw files",
            trains_to_load=seed_count,
        )

        loaded = 0
        errors = 0

        for train in trains:
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
            total_raw=seed_count,
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

        return {
            "success": True,
            "trains_loaded": loaded,
            "errors": errors,
            "routes_assigned": routes_assigned,
        }
