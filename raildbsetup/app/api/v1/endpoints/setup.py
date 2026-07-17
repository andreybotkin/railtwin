"""Setup endpoints for manual re-triggering of initialization steps."""

from fastapi import APIRouter, BackgroundTasks, Request

router = APIRouter()


@router.post(
    "/railroad",
    summary="Re-initialize railroad network",
    description=(
        "Reloads routes and stations from the local KML file (or downloads it) "
        "and writes them to the database. "
        "Use ``force=true`` to replace existing data."
    ),
)
async def trigger_railroad(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    runner = request.app.state.runner
    background_tasks.add_task(runner.run_railroad, force)
    return {"message": "Railroad initialization triggered", "force": force}


@router.post(
    "/schedules",
    summary="Re-initialize train schedules",
    description=(
        "Loads train schedules from raw JSON files (or seed file) "
        "and writes them to the database. Skipped if DB already has data "
        "and force is not set."
    ),
)
async def trigger_schedules(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    runner = request.app.state.runner
    background_tasks.add_task(runner.run_schedules)
    return {"message": "Schedule initialization triggered"}


@router.post(
    "/topology",
    summary="Re-build network topology graph",
    description=(
        "Re-derives the railway network graph (network_nodes, network_edges, "
        "route_edges) from the existing routes & stations data. "
        "Use ``force=true`` to rebuild even if a graph already exists."
    ),
)
async def trigger_topology(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    runner = request.app.state.runner
    background_tasks.add_task(runner.run_network_topology, force)
    return {"message": "Network topology build triggered", "force": force}


@router.post(
    "/movement-plans",
    summary="Re-build precomputed movement plans",
    description=(
        "Clears and rebuilds planned_train_runs and planned_movement_segments "
        "from the current schedules and route geometry metadata. "
        "Safe to run at any time; does not affect runtime trajectory generation. "
        "Use ``force=true`` (currently a no-op, included for forward compatibility)."
    ),
)
async def trigger_movement_plans(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    runner = request.app.state.runner
    background_tasks.add_task(runner.run_movement_plans, force)
    return {"message": "Movement plan build triggered", "force": force}


@router.post(
    "/all",
    summary="Re-run full initialization",
    description="Re-runs the complete initialization sequence (railroad + topology + schedules).",
)
async def trigger_all(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    runner = request.app.state.runner
    background_tasks.add_task(runner.run_all, force)
    return {"message": "Full initialization triggered", "force": force}


@router.get(
    "/status",
    summary="Initialization status",
    description="Returns the current state and results of each initialization step.",
)
async def get_status(request: Request) -> dict:
    runner = request.app.state.runner
    return {
        "ready": runner.is_ready,
        "failed": runner.is_failed,
        "current_step": runner.current_step,
        "error": runner.error,
        "results": runner.status,
    }
