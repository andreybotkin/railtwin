"""Normalize topology storage for physical track graph and operational links.

Revision ID: 007_topology_links
Revises: 006_graph_topology_refactor
Create Date: 2026-04-12 00:00:02.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "007_topology_links"
down_revision: Union[str, None] = "006_graph_topology_refactor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "network_links",
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
        sa.UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "link_kind",
            name="uq_network_links_directed_kind",
        ),
    )
    op.create_index(
        "idx_network_links_geometry",
        "network_links",
        ["geometry"],
        postgresql_using="gist",
    )
    op.create_index("idx_network_links_from_node", "network_links", ["from_node_id"])
    op.create_index("idx_network_links_to_node", "network_links", ["to_node_id"])
    op.create_index(
        "idx_network_links_from_component",
        "network_links",
        ["from_component_id"],
    )
    op.create_index(
        "idx_network_links_to_component",
        "network_links",
        ["to_component_id"],
    )

    op.create_table(
        "topology_metadata",
        sa.Column("id", sa.Integer(), primary_key=True),
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
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "idx_topology_metadata_built_at",
        "topology_metadata",
        ["built_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_topology_metadata_built_at", table_name="topology_metadata")
    op.drop_table("topology_metadata")

    op.drop_index("idx_network_links_to_component", table_name="network_links")
    op.drop_index("idx_network_links_from_component", table_name="network_links")
    op.drop_index("idx_network_links_to_node", table_name="network_links")
    op.drop_index("idx_network_links_from_node", table_name="network_links")
    op.drop_index("idx_network_links_geometry", table_name="network_links")
    op.drop_table("network_links")