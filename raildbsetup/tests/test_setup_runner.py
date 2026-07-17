from unittest.mock import AsyncMock

import pytest

from app.application.runner import SetupRunner


@pytest.mark.asyncio
async def test_run_all_propagates_force_to_derived_data_builds() -> None:
    runner = SetupRunner()
    runner.run_migrations = AsyncMock(return_value={"success": True})
    runner.run_railroad = AsyncMock(return_value={"success": True})
    runner.run_network_topology = AsyncMock(return_value={"success": True})
    runner.run_schedules = AsyncMock(return_value={"success": True})
    runner.run_movement_plans = AsyncMock(return_value={"success": True})

    result = await runner.run_all(force=True)

    runner.run_railroad.assert_awaited_once_with(force=True)
    runner.run_network_topology.assert_awaited_once_with(force=True)
    runner.run_movement_plans.assert_awaited_once_with(force=True)
    assert result["railroad"]["success"] is True
    assert runner.is_ready is True
    assert runner.current_step == "done"
