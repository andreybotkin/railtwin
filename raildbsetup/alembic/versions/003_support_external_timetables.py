"""Support external timetables and overnight stop metadata.

Revision ID: 003_support_external_timetables
Revises: 002_seed_data
Create Date: 2026-04-10 00:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "003_support_external_timetables"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add metadata required for importing external timetable sources."""
    op.create_table(
        "station_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source", "alias", name="uq_station_alias_source_alias"),
    )
    op.create_index("ix_station_aliases_station_id", "station_aliases", ["station_id"])
    op.create_index("ix_station_aliases_source", "station_aliases", ["source"])

    op.add_column(
        "trains",
        sa.Column(
            "source", sa.String(length=50), server_default="manual", nullable=False
        ),
    )
    op.add_column("trains", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column(
        "trains",
        sa.Column(
            "service_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    op.add_column(
        "schedules", sa.Column("station_name", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "schedules", sa.Column("route_station_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "schedules",
        sa.Column(
            "arrival_day_offset", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "schedules",
        sa.Column(
            "departure_day_offset", sa.Integer(), server_default="0", nullable=False
        ),
    )
    op.add_column(
        "schedules",
        sa.Column("distance_from_origin_km", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "schedules", sa.Column("route_progress", sa.Numeric(8, 6), nullable=True)
    )

    op.execute("""
        UPDATE schedules
        SET station_name = stations.name
        FROM stations
        WHERE schedules.station_id = stations.id
        """)

    op.alter_column("schedules", "station_name", nullable=False)
    op.alter_column(
        "schedules", "station_id", existing_type=sa.Integer(), nullable=True
    )

    op.create_foreign_key(
        "fk_schedules_route_station_id_route_stations",
        "schedules",
        "route_stations",
        ["route_station_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_schedules_route_station_id", "schedules", ["route_station_id"])


def downgrade() -> None:
    """Remove external timetable support columns and tables."""
    op.drop_index("ix_schedules_route_station_id", table_name="schedules")
    op.drop_constraint(
        "fk_schedules_route_station_id_route_stations", "schedules", type_="foreignkey"
    )
    op.drop_column("schedules", "route_progress")
    op.drop_column("schedules", "distance_from_origin_km")
    op.drop_column("schedules", "departure_day_offset")
    op.drop_column("schedules", "arrival_day_offset")
    op.drop_column("schedules", "route_station_id")
    op.drop_column("schedules", "station_name")

    op.drop_column("trains", "service_notes")
    op.drop_column("trains", "source_url")
    op.drop_column("trains", "source")

    op.drop_index("ix_station_aliases_source", table_name="station_aliases")
    op.drop_index("ix_station_aliases_station_id", table_name="station_aliases")
    op.drop_table("station_aliases")
