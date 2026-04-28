"""No-op migration: schedule seeding moved to raildatacollector.

Revision ID: 004_reseed_schedules
Revises: 003_support_external_timetables
Create Date: 2026-04-10 00:00:00.000000
"""

from collections.abc import Sequence

revision = "004_reseed_schedules"
down_revision = "003_support_external_timetables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """No-op: real data is loaded by raildatacollector on first startup."""
    pass


def downgrade() -> None:
    pass
