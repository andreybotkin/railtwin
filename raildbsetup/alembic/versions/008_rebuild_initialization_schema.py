"""Rebuild rail initialization schema around canonical sources.

Revision ID: 008
Revises: 007
Create Date: 2026-04-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008"
down_revision: str | None = "007_topology_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_fk_if_present(
    inspector: sa.Inspector,
    *,
    table_name: str,
    referred_table: str,
    constrained_column: str,
) -> None:
    for fk in inspector.get_foreign_keys(table_name):
        if fk.get("referred_table") != referred_table:
            continue
        if constrained_column not in (fk.get("constrained_columns") or []):
            continue
        if fk.get("name"):
            op.drop_constraint(fk["name"], table_name, type_="foreignkey")


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    existing_tables = set(inspector.get_table_names())
    if "stations" in existing_tables and "network_nodes" in existing_tables:
        _drop_fk_if_present(
            inspector,
            table_name="stations",
            referred_table="network_nodes",
            constrained_column="node_id",
        )
        _drop_fk_if_present(
            inspector,
            table_name="network_nodes",
            referred_table="stations",
            constrained_column="station_id",
        )

    for table_name in [
        "route_edges",
        "network_edge_routes",
        "network_links",
        "topology_metadata",
        "train_positions",
        "schedules",
        "station_aliases",
        "route_stations",
        "trains",
        "stations",
        "network_edges",
        "network_nodes",
        "routes",
    ]:
        if table_name in existing_tables:
            op.drop_table(table_name)

    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_th", sa.String(length=255), nullable=True),
        sa.Column("code", sa.String(length=10), nullable=False),
        sa.Column("station_class", sa.String(length=32), nullable=True),
        sa.Column("source_line", sa.String(length=255), nullable=True),
        sa.Column("source_route_type", sa.String(length=50), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("province", sa.String(length=100), nullable=True),
        sa.Column("facilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "location",
            Geometry("POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column(
            "snapped_location",
            Geometry("POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=True,
        ),
        sa.Column("snap_distance_m", sa.Numeric(10, 2), nullable=True),
        sa.Column("node_id", sa.Integer(), nullable=True),
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
        sa.UniqueConstraint("code", name="uq_stations_code"),
    )
    op.create_index("ix_stations_code", "stations", ["code"])
    op.create_index("ix_stations_name", "stations", ["name"])

    op.create_table(
        "routes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("name_th", sa.String(length=255), nullable=True),
        sa.Column("route_type", sa.String(length=50), nullable=False),
        sa.Column("source_folder", sa.String(length=255), nullable=True),
        sa.Column("color", sa.String(length=7), nullable=True),
        sa.Column(
            "line_geometry",
            Geometry(
                "LINESTRING", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"
            ),
            nullable=True,
        ),
        sa.Column("distance_km", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_routes_route_type", "routes", ["route_type"])

    op.create_table(
        "network_nodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "location",
            Geometry("POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=False,
        ),
        sa.Column(
            "node_type", sa.String(length=20), nullable=False, server_default="graph"
        ),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("station_id", name="uq_network_nodes_station_id"),
    )
    op.create_index("ix_network_nodes_station_id", "network_nodes", ["station_id"])
    op.create_index("ix_network_nodes_component_id", "network_nodes", ["component_id"])

    op.create_table(
        "network_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column(
            "geometry",
            Geometry(
                "LINESTRING", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"
            ),
            nullable=False,
        ),
        sa.Column("length_m", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "edge_kind", sa.String(length=32), nullable=False, server_default="track"
        ),
        sa.Column("component_id", sa.Integer(), nullable=True),
        sa.Column("route_type", sa.String(length=50), nullable=True),
        sa.Column("line_name", sa.String(length=255), nullable=True),
        sa.Column("max_speed_kmh", sa.Integer(), nullable=True),
        sa.Column("track_class", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["from_node_id"], ["network_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["to_node_id"], ["network_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_node_id", "to_node_id", name="uq_network_edges_directed"
        ),
    )
    op.create_index("ix_network_edges_from_node_id", "network_edges", ["from_node_id"])
    op.create_index("ix_network_edges_to_node_id", "network_edges", ["to_node_id"])
    op.create_index("ix_network_edges_route_type", "network_edges", ["route_type"])

    op.create_table(
        "route_edges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("edge_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["edge_id"], ["network_edges.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "route_id",
            "sequence",
            "direction",
            name="uq_route_edges_route_sequence_direction",
        ),
    )
    op.create_index("ix_route_edges_route_id", "route_edges", ["route_id"])
    op.create_index("ix_route_edges_edge_id", "route_edges", ["edge_id"])

    op.create_table(
        "network_links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("from_node_id", sa.Integer(), nullable=False),
        sa.Column("to_node_id", sa.Integer(), nullable=False),
        sa.Column(
            "geometry",
            Geometry(
                "LINESTRING", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"
            ),
            nullable=False,
        ),
        sa.Column("length_m", sa.Numeric(12, 2), nullable=True),
        sa.Column("link_kind", sa.String(length=32), nullable=False),
        sa.Column("from_component_id", sa.Integer(), nullable=True),
        sa.Column("to_component_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["from_node_id"], ["network_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["to_node_id"], ["network_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "link_kind",
            name="uq_network_links_directed_kind",
        ),
    )
    op.create_index("ix_network_links_from_node_id", "network_links", ["from_node_id"])
    op.create_index("ix_network_links_to_node_id", "network_links", ["to_node_id"])

    op.create_table(
        "topology_metadata",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topology_version", sa.String(length=64), nullable=False),
        sa.Column("physical_nodes_count", sa.Integer(), nullable=False),
        sa.Column("physical_edges_count", sa.Integer(), nullable=False),
        sa.Column("station_nodes_count", sa.Integer(), nullable=False),
        sa.Column("physical_components_count", sa.Integer(), nullable=False),
        sa.Column("station_components_count", sa.Integer(), nullable=False),
        sa.Column("operational_links_count", sa.Integer(), nullable=False),
        sa.Column("main_component_station_count", sa.Integer(), nullable=False),
        sa.Column("disconnected_station_count", sa.Integer(), nullable=False),
        sa.Column("unsnapped_station_count", sa.Integer(), nullable=False),
        sa.Column("max_snap_distance_m", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_topology_metadata_built_at", "topology_metadata", ["built_at"])

    op.create_table(
        "route_stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.Integer(), nullable=True),
        sa.Column("edge_id", sa.Integer(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("distance_from_start", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "snapped_location",
            Geometry("POINT", srid=4326, from_text="ST_GeomFromEWKT", name="geometry"),
            nullable=True,
        ),
        sa.Column("snap_distance_m", sa.Numeric(10, 2), nullable=True),
        sa.ForeignKeyConstraint(["route_id"], ["routes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["network_nodes.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["edge_id"], ["network_edges.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "route_id", "sequence", name="uq_route_stations_route_sequence"
        ),
    )
    op.create_index("ix_route_stations_route_id", "route_stations", ["route_id"])
    op.create_index("ix_route_stations_station_id", "route_stations", ["station_id"])
    op.create_index("ix_route_stations_node_id", "route_stations", ["node_id"])

    op.create_table(
        "trains",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("train_number", sa.String(length=20), nullable=False),
        sa.Column("train_type", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=True),
        sa.Column(
            "operator",
            sa.String(length=100),
            nullable=False,
            server_default="State Railway of Thailand",
        ),
        sa.Column(
            "source",
            sa.String(length=50),
            nullable=False,
            server_default="raildbsetup_raw",
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column(
            "service_notes", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("current_route_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["current_route_id"], ["routes.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("train_number", name="uq_trains_train_number"),
    )
    op.create_index("ix_trains_train_number", "trains", ["train_number"])
    op.create_index("ix_trains_current_route_id", "trains", ["current_route_id"])

    op.create_table(
        "station_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source",
            "normalized_alias",
            name="uq_station_aliases_source_normalized_alias",
        ),
    )
    op.create_index("ix_station_aliases_station_id", "station_aliases", ["station_id"])
    op.create_index("ix_station_aliases_source", "station_aliases", ["source"])

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("train_id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=True),
        sa.Column("route_station_id", sa.Integer(), nullable=True),
        sa.Column("station_name", sa.String(length=255), nullable=False),
        sa.Column("arrival_time", sa.Time(), nullable=True),
        sa.Column("departure_time", sa.Time(), nullable=True),
        sa.Column(
            "arrival_day_offset", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "departure_day_offset", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column(
            "day_of_week", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("platform", sa.String(length=10), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("distance_from_origin_km", sa.Numeric(10, 2), nullable=True),
        sa.Column("route_progress", sa.Numeric(8, 6), nullable=True),
        sa.ForeignKeyConstraint(["train_id"], ["trains.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["route_station_id"], ["route_stations.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_schedules_train_id", "schedules", ["train_id"])
    op.create_index("ix_schedules_station_id", "schedules", ["station_id"])
    op.create_index("ix_schedules_route_station_id", "schedules", ["route_station_id"])
    op.create_index("ix_schedules_departure_time", "schedules", ["departure_time"])

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
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="moving"
        ),
        sa.Column("delay_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["train_id"], ["trains.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_train_positions_train_id", "train_positions", ["train_id"])
    op.create_index("ix_train_positions_timestamp", "train_positions", ["timestamp"])


def downgrade() -> None:
    raise NotImplementedError("Migration 008 is irreversible")
