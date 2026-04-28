"""Add precomputed movement plan tables.

Revision ID: 010_planned_movement_plan
Revises: 009_station_only_topology_graph
Create Date: 2026-04-29 00:00:00.000000

This migration is strictly additive — no existing tables or columns are
touched.  The two new tables store the precomputed movement plan built
after topology initialisation; runtime trajectory generation continues to
use the existing path until Phase 6.

See docs/precomputed-movement-plan.md for the full design.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "010_planned_movement_plan"
down_revision: str | None = "009_station_only_topology_graph"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # planned_train_runs                                                   #
    # ------------------------------------------------------------------ #

    op.create_table(
        "planned_train_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("train_id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        # NULL means "applies to every operating day" (typical for fixed
        # Thai railway timetables).  A non-NULL value scopes the plan to a
        # specific calendar date (e.g. a special service).
        sa.Column("service_date", sa.Date(), nullable=True),
        # Optional human-readable service pattern tag (e.g. "weekday",
        # "weekend") for schedules that vary within a week.
        sa.Column("service_pattern", sa.String(length=64), nullable=True),
        # Opaque version string incremented whenever the plan is rebuilt for
        # the same (train, route, service_date) combination.
        sa.Column("plan_version", sa.String(length=64), nullable=False),
        # topology_version from topology_metadata at build time.
        # A NULL value means the plan was built before topology_metadata
        # existed; treat it as potentially stale.
        sa.Column("topology_version", sa.String(length=64), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        # ready | degraded | invalid
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default="ready",
        ),
        sa.Column("warnings", postgresql.JSONB(), nullable=True),
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
        sa.ForeignKeyConstraint(["train_id"], ["trains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_planned_runs_train_id", "planned_train_runs", ["train_id"])
    op.create_index("ix_planned_runs_route_id", "planned_train_runs", ["route_id"])
    op.create_index(
        "ix_planned_runs_service_date", "planned_train_runs", ["service_date"]
    )
    op.create_index("ix_planned_runs_status", "planned_train_runs", ["status"])
    op.create_index(
        "ix_planned_runs_topology_version",
        "planned_train_runs",
        ["topology_version"],
    )

    # Uniqueness on (train_id, route_id, plan_version) must handle a nullable
    # service_date.  In PostgreSQL a standard UNIQUE constraint treats NULL
    # values as non-equal, so UNIQUE (train_id, route_id, service_date,
    # plan_version) would allow duplicate rows when service_date IS NULL.
    # Two partial unique indexes enforce the intended semantic correctly:
    #   — when service_date IS NULL, uniqueness is on the three non-null cols
    #   — when service_date IS NOT NULL, all four columns must be unique
    op.execute("""
        CREATE UNIQUE INDEX uq_planned_runs_no_date
            ON planned_train_runs (train_id, route_id, plan_version)
            WHERE service_date IS NULL
        """)
    op.execute("""
        CREATE UNIQUE INDEX uq_planned_runs_with_date
            ON planned_train_runs (train_id, route_id, service_date, plan_version)
            WHERE service_date IS NOT NULL
        """)

    # ------------------------------------------------------------------ #
    # planned_movement_segments                                            #
    # ------------------------------------------------------------------ #

    op.create_table(
        "planned_movement_segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("planned_run_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        # 'move' | 'dwell'
        sa.Column("segment_type", sa.String(length=8), nullable=False),
        # Station references — nullable because intermediate synthetic-connector
        # segments may not correspond to a canonical station row.
        sa.Column("from_station_id", sa.Integer(), nullable=True),
        sa.Column("to_station_id", sa.Integer(), nullable=True),
        # Schedule rows that bound this segment's timing.
        sa.Column("from_schedule_id", sa.Integer(), nullable=True),
        sa.Column("to_schedule_id", sa.Integer(), nullable=True),
        # Time bounds in integer minutes-since-midnight on their respective
        # calendar day.  Mirrors schedule.arrival/departure_day_offset.
        sa.Column("start_time_minutes", sa.Integer(), nullable=False),
        sa.Column("end_time_minutes", sa.Integer(), nullable=False),
        sa.Column("start_day_offset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("end_day_offset", sa.Integer(), nullable=False, server_default="0"),
        # Denormalised absolute minutes for efficient range queries:
        #   absolute_*_minutes = *_time_minutes + *_day_offset * 1440
        # Computed by the plan builder and stored so runtime never needs to
        # multiply; also avoids a generated-column dependency on PG version.
        sa.Column("absolute_start_minutes", sa.Integer(), nullable=False),
        sa.Column("absolute_end_minutes", sa.Integer(), nullable=False),
        # Route distance bounds in metres.  Derived from
        # route_stations.distance_from_start at plan-build time.
        # Geometry is NOT duplicated — these are scalar offsets into the
        # existing route/network_edges geometry.
        sa.Column("start_distance_m", sa.Numeric(12, 2), nullable=True),
        sa.Column("end_distance_m", sa.Numeric(12, 2), nullable=True),
        # Precomputed fractions [0, 1] along the route polyline (same
        # coordinate space as Trajectory.route_coords already in Redis).
        # NULL means the plan builder could not resolve a reliable fraction
        # for this stop; the resolver will fall back to build_trajectory().
        sa.Column("start_geom_fraction", sa.Numeric(10, 8), nullable=True),
        sa.Column("end_geom_fraction", sa.Numeric(10, 8), nullable=True),
        # Optional edge references for edge-aligned admin queries.
        sa.Column("start_edge_id", sa.Integer(), nullable=True),
        sa.Column("end_edge_id", sa.Integer(), nullable=True),
        # Planned average speed for move segments; NULL for dwell.
        sa.Column("planned_speed_kmh", sa.Numeric(7, 2), nullable=True),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("warnings", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["planned_run_id"], ["planned_train_runs.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["from_station_id"], ["stations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["to_station_id"], ["stations.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["from_schedule_id"], ["schedules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["to_schedule_id"], ["schedules.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["start_edge_id"], ["network_edges.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["end_edge_id"], ["network_edges.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_pms_run_id", "planned_movement_segments", ["planned_run_id"])
    # Unique ordered sequence within a run
    op.create_index(
        "uq_pms_run_sequence",
        "planned_movement_segments",
        ["planned_run_id", "sequence"],
        unique=True,
    )
    # Composite index for binary-search-style time range lookups at runtime
    op.create_index(
        "ix_pms_run_time",
        "planned_movement_segments",
        ["planned_run_id", "absolute_start_minutes", "absolute_end_minutes"],
    )
    op.create_index(
        "ix_pms_from_station", "planned_movement_segments", ["from_station_id"]
    )
    op.create_index("ix_pms_to_station", "planned_movement_segments", ["to_station_id"])
    op.create_index("ix_pms_start_edge", "planned_movement_segments", ["start_edge_id"])
    op.create_index("ix_pms_end_edge", "planned_movement_segments", ["end_edge_id"])


def downgrade() -> None:
    op.drop_table("planned_movement_segments")
    op.drop_table("planned_train_runs")
