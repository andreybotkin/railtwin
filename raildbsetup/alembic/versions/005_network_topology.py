"""Add network topology tables: network_nodes, network_edges, route_edges.

Also extends stations and route_stations with topology-binding columns:
  - stations.snapped_location  – closest point on the nearest network edge
  - stations.snap_distance_m   – metres between the raw KML point and snapped_location
  - stations.node_id           – FK to network_nodes (NULL if station not in graph)
  - route_stations.edge_id     – FK to the network_edge connecting prev→this stop
  - route_stations.snapped_location
  - route_stations.snap_distance_m

Schema design:
  network_nodes  – graph vertices, one per station (node_type='station') or
                   per junction / terminus when no station record exists
  network_edges  – directed graph edges; one pair (A→B) and its reverse (B→A)
                   are stored separately so routing queries are simple forward-only scans
  route_edges    – mapping of a route to the ordered list of edges that compose it

Revision ID: 005_network_topology
Revises: 004_reseed_schedules
Create Date: 2026-04-12 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from geoalchemy2 import Geometry

from alembic import op

revision: str = "005_network_topology"
down_revision: str | None = "004_reseed_schedules"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── network_nodes ──────────────────────────────────────────────────────────
    op.create_table(
        "network_nodes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "location",
            Geometry("POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column(
            "node_type",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'station'"),
        ),
        sa.Column(
            "station_id",
            sa.Integer(),
            sa.ForeignKey("stations.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("idx_network_nodes_station_id", "network_nodes", ["station_id"])
    op.create_index(
        "idx_network_nodes_location",
        "network_nodes",
        ["location"],
        postgresql_using="gist",
    )

    # ── network_edges ──────────────────────────────────────────────────────────
    op.create_table(
        "network_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "from_node_id",
            sa.Integer(),
            sa.ForeignKey("network_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_node_id",
            sa.Integer(),
            sa.ForeignKey("network_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "geometry",
            Geometry("LINESTRING", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("length_m", sa.Numeric(12, 2), nullable=True),
        sa.Column("route_type", sa.String(50), nullable=True),
        sa.Column("line_name", sa.String(255), nullable=True),
        sa.Column("max_speed_kmh", sa.Integer(), nullable=True),
        sa.Column("track_class", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "from_node_id", "to_node_id", name="uq_network_edges_directed"
        ),
    )
    op.create_index(
        "idx_network_edges_geometry",
        "network_edges",
        ["geometry"],
        postgresql_using="gist",
    )
    op.create_index("idx_network_edges_from_node", "network_edges", ["from_node_id"])
    op.create_index("idx_network_edges_to_node", "network_edges", ["to_node_id"])

    # ── route_edges ────────────────────────────────────────────────────────────
    op.create_table(
        "route_edges",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "route_id",
            sa.Integer(),
            sa.ForeignKey("routes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "edge_id",
            sa.Integer(),
            sa.ForeignKey("network_edges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "direction",
            sa.String(10),
            nullable=False,
            server_default=sa.text("'forward'"),
        ),
        sa.UniqueConstraint("route_id", "sequence", name="uq_route_edges_route_seq"),
    )

    # ── stations: topology columns ─────────────────────────────────────────────
    op.add_column(
        "stations",
        sa.Column(
            "snapped_location",
            Geometry("POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
    )
    op.add_column(
        "stations",
        sa.Column("snap_distance_m", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "stations",
        sa.Column(
            "node_id",
            sa.Integer(),
            sa.ForeignKey("network_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_stations_node_id", "stations", ["node_id"])
    op.create_index(
        "idx_stations_snapped_location",
        "stations",
        ["snapped_location"],
        postgresql_using="gist",
    )

    # ── route_stations: topology columns ───────────────────────────────────────
    op.add_column(
        "route_stations",
        sa.Column(
            "edge_id",
            sa.Integer(),
            sa.ForeignKey("network_edges.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "route_stations",
        sa.Column(
            "snapped_location",
            Geometry("POINT", srid=4326, spatial_index=False),
            nullable=True,
        ),
    )
    op.add_column(
        "route_stations",
        sa.Column("snap_distance_m", sa.Numeric(10, 2), nullable=True),
    )
    op.create_index("idx_route_stations_edge_id", "route_stations", ["edge_id"])


def downgrade() -> None:
    # Remove indexes and columns on route_stations
    op.drop_index("idx_route_stations_edge_id", table_name="route_stations")
    op.drop_column("route_stations", "snap_distance_m")
    op.drop_column("route_stations", "snapped_location")
    op.drop_column("route_stations", "edge_id")

    # Remove indexes and columns on stations
    op.drop_index("idx_stations_snapped_location", table_name="stations")
    op.drop_index("idx_stations_node_id", table_name="stations")
    op.drop_column("stations", "node_id")
    op.drop_column("stations", "snap_distance_m")
    op.drop_column("stations", "snapped_location")

    # Drop new tables (in reverse FK order)
    op.drop_table("route_edges")
    op.drop_index("idx_network_edges_to_node", table_name="network_edges")
    op.drop_index("idx_network_edges_from_node", table_name="network_edges")
    op.drop_index("idx_network_edges_geometry", table_name="network_edges")
    op.drop_table("network_edges")
    op.drop_index("idx_network_nodes_location", table_name="network_nodes")
    op.drop_index("idx_network_nodes_station_id", table_name="network_nodes")
    op.drop_table("network_nodes")
