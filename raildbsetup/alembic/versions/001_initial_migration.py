"""Initial migration - create all tables

Revision ID: 001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Apply migration - create all tables and indexes."""
    # Enable PostGIS extension
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    # Create stations table
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_th", sa.String(255), nullable=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column(
            "location",
            Geometry("POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("province", sa.String(100), nullable=True),
        sa.Column("facilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("idx_stations_code", "stations", ["code"])

    # Create routes table
    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_th", sa.String(255), nullable=True),
        sa.Column(
            "line_geometry",
            Geometry(
                "LINESTRING", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"
            ),
            nullable=True,
        ),
        sa.Column("distance_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("route_type", sa.String(50), nullable=False),
        sa.Column("color", sa.String(7), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Create route_stations junction table
    op.create_table(
        "route_stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("distance_from_start", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(
            ["route_id"],
            ["routes.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_route_stations_route", "route_stations", ["route_id"])
    op.create_index("idx_route_stations_station", "route_stations", ["station_id"])

    # Create trains table
    op.create_table(
        "trains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("train_number", sa.String(20), nullable=False),
        sa.Column("train_type", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column(
            "operator",
            sa.String(100),
            nullable=False,
            server_default="State Railway of Thailand",
        ),
        sa.Column("current_route_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["current_route_id"],
            ["routes.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("train_number"),
    )
    op.create_index("idx_trains_number", "trains", ["train_number"])

    # Create schedules table
    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("train_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("arrival_time", sa.Time(), nullable=True),
        sa.Column("departure_time", sa.Time(), nullable=True),
        sa.Column("day_of_week", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column("platform", sa.String(10), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["train_id"],
            ["trains.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["station_id"],
            ["stations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_schedules_train", "schedules", ["train_id"])
    op.create_index("idx_schedules_station", "schedules", ["station_id"])
    op.create_index("idx_schedules_departure", "schedules", ["departure_time"])

    # Create train_positions table
    op.create_table(
        "train_positions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("train_id", sa.Integer(), nullable=False),
        sa.Column(
            "location",
            Geometry("POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column("speed", sa.Numeric(6, 2), nullable=True),
        sa.Column("heading", sa.Numeric(5, 2), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="moving"),
        sa.Column("delay_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["train_id"],
            ["trains.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_train_positions_train", "train_positions", ["train_id"])
    op.create_index("idx_train_positions_timestamp", "train_positions", ["timestamp"])


def downgrade() -> None:
    """Revert migration - drop all tables."""
    op.drop_table("train_positions")
    op.drop_table("schedules")
    op.drop_table("trains")
    op.drop_table("route_stations")
    op.drop_table("routes")
    op.drop_table("stations")
    op.execute("DROP EXTENSION IF EXISTS postgis")
