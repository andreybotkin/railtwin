"""Add physical train parameters and DEM/speed profiles.

Revision ID: 011_physics_profiles
Revises: 010_planned_movement_plan
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "011_physics_profiles"
down_revision: str | None = "010_planned_movement_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trains", sa.Column("locomotive_mass_t", sa.Numeric(8, 2)))
    op.add_column("trains", sa.Column("rolling_stock_mass_t", sa.Numeric(9, 2)))
    op.add_column("trains", sa.Column("horsepower", sa.Numeric(8, 1)))
    op.add_column("trains", sa.Column("max_tractive_effort_kn", sa.Numeric(8, 2)))
    op.add_column(
        "trains", sa.Column("max_brake_deceleration_mps2", sa.Numeric(5, 3))
    )
    op.add_column("trains", sa.Column("max_speed_kmh", sa.Numeric(6, 2)))
    op.add_column("trains", sa.Column("passenger_load", sa.Integer()))
    op.add_column("trains", sa.Column("passenger_mass_kg", sa.Numeric(6, 2)))
    op.add_column(
        "network_edges",
        sa.Column("elevation_profile", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "network_edges",
        sa.Column("speed_limit_zones", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("network_edges", "speed_limit_zones")
    op.drop_column("network_edges", "elevation_profile")
    for column in (
        "passenger_mass_kg",
        "passenger_load",
        "max_speed_kmh",
        "max_brake_deceleration_mps2",
        "max_tractive_effort_kn",
        "horsepower",
        "rolling_stock_mass_t",
        "locomotive_mass_t",
    ):
        op.drop_column("trains", column)
