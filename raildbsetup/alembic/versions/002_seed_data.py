"""Schema adjustment: station_id on schedules is nullable for external sources.

Data is no longer seeded here — the raildatacollector microservice is
responsible for loading real stations (from KML) and trains (from raw
timetable JSON files) on first startup.

Revision ID: 002
Revises: 001
Create Date: 2024-01-01 00:01:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make schedules.station_id nullable (station may not match KML on import)."""
    op.alter_column("schedules", "station_id", nullable=True)


def downgrade() -> None:
    op.alter_column("schedules", "station_id", nullable=False)
