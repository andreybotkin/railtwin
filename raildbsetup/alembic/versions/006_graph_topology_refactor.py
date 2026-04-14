"""Refine railway graph topology schema.

Revision ID: 006_graph_topology_refactor
Revises: 005_network_topology
Create Date: 2026-04-12 00:00:01.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006_graph_topology_refactor"
down_revision: Union[str, None] = "005_network_topology"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stations",
        sa.Column("source_route_type", sa.String(length=50), nullable=True),
    )

    op.add_column(
        "network_nodes",
        sa.Column("component_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_network_nodes_component_id",
        "network_nodes",
        ["component_id"],
    )

    op.add_column(
        "network_edges",
        sa.Column(
            "edge_kind",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'track'"),
        ),
    )
    op.add_column(
        "network_edges",
        sa.Column("component_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "idx_network_edges_edge_kind",
        "network_edges",
        ["edge_kind"],
    )
    op.create_index(
        "idx_network_edges_component_id",
        "network_edges",
        ["component_id"],
    )

    op.create_table(
        "network_edge_routes",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "edge_id",
            sa.Integer(),
            sa.ForeignKey("network_edges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "route_id",
            sa.Integer(),
            sa.ForeignKey("routes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("route_fraction", sa.Numeric(8, 6), nullable=True),
        sa.UniqueConstraint(
            "edge_id",
            "route_id",
            name="uq_network_edge_routes_edge_route",
        ),
    )
    op.create_index(
        "idx_network_edge_routes_edge_id",
        "network_edge_routes",
        ["edge_id"],
    )
    op.create_index(
        "idx_network_edge_routes_route_id",
        "network_edge_routes",
        ["route_id"],
    )

    op.add_column(
        "route_stations",
        sa.Column(
            "node_id",
            sa.Integer(),
            sa.ForeignKey("network_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_route_stations_node_id",
        "route_stations",
        ["node_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_route_stations_node_id", table_name="route_stations")
    op.drop_column("route_stations", "node_id")

    op.drop_index(
        "idx_network_edge_routes_route_id",
        table_name="network_edge_routes",
    )
    op.drop_index(
        "idx_network_edge_routes_edge_id",
        table_name="network_edge_routes",
    )
    op.drop_table("network_edge_routes")

    op.drop_index("idx_network_edges_component_id", table_name="network_edges")
    op.drop_index("idx_network_edges_edge_kind", table_name="network_edges")
    op.drop_column("network_edges", "component_id")
    op.drop_column("network_edges", "edge_kind")

    op.drop_index(
        "idx_network_nodes_component_id",
        table_name="network_nodes",
    )
    op.drop_column("network_nodes", "component_id")

    op.drop_column("stations", "source_route_type")