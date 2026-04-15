"""SQLAlchemy Core table definitions for raildbsetup.

These lightweight Table objects are used exclusively by the repository layer to
build type-safe SQLAlchemy 2 / GeoAlchemy2 queries without raw SQL strings.
They mirror the schema defined in the Alembic migrations but do NOT own the
schema – Alembic remains the single source of truth for DDL.
"""

import sqlalchemy as sa
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()

t_stations = sa.Table(
    "stations",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("name_th", sa.String(255), nullable=True),
    sa.Column("code", sa.String(10), nullable=False),
    sa.Column("station_class", sa.String(32), nullable=True),
    sa.Column("source_line", sa.String(255), nullable=True),
    sa.Column(
        "location", Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    ),
    sa.Column("source_route_type", sa.String(50), nullable=True),
    sa.Column("city", sa.String(100), nullable=True),
    sa.Column("province", sa.String(100), nullable=True),
    sa.Column("facilities", postgresql.JSONB(), nullable=True),
    # topology columns (added by migration 005)
    sa.Column(
        "snapped_location",
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=True,
    ),
    sa.Column("snap_distance_m", sa.Numeric(10, 2), nullable=True),
    sa.Column("node_id", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)

t_routes = sa.Table(
    "routes",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("name", sa.String(255), nullable=False),
    sa.Column("name_th", sa.String(255), nullable=True),
    sa.Column("source_folder", sa.String(255), nullable=True),
    sa.Column(
        "line_geometry",
        Geometry("LINESTRING", srid=4326, spatial_index=False),
        nullable=True,
    ),
    sa.Column("distance_km", sa.Numeric(10, 2), nullable=True),
    sa.Column("route_type", sa.String(50), nullable=False),
    sa.Column("color", sa.String(7), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

t_route_stations = sa.Table(
    "route_stations",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("route_id", sa.Integer(), nullable=False),
    sa.Column("station_id", sa.Integer(), nullable=False),
    sa.Column("node_id", sa.Integer(), nullable=True),
    sa.Column("sequence", sa.Integer(), nullable=False),
    sa.Column("distance_from_start", sa.Numeric(10, 2), nullable=True),
    # topology columns (added by migration 005)
    sa.Column("edge_id", sa.Integer(), nullable=True),
    sa.Column(
        "snapped_location",
        Geometry("POINT", srid=4326, spatial_index=False),
        nullable=True,
    ),
    sa.Column("snap_distance_m", sa.Numeric(10, 2), nullable=True),
)

t_trains = sa.Table(
    "trains",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("train_number", sa.String(20), nullable=False),
    sa.Column("train_type", sa.String(50), nullable=False),
    sa.Column("name", sa.String(100), nullable=True),
    sa.Column("capacity", sa.Integer(), nullable=True),
    sa.Column("operator", sa.String(100), nullable=False),
    sa.Column("source", sa.String(50), nullable=False),
    sa.Column("source_url", sa.Text(), nullable=True),
    sa.Column("service_notes", postgresql.JSONB(), nullable=True),
    sa.Column("current_route_id", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

t_schedules = sa.Table(
    "schedules",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("train_id", sa.Integer(), nullable=False),
    sa.Column("station_id", sa.Integer(), nullable=True),
    sa.Column("route_station_id", sa.Integer(), nullable=True),
    sa.Column("station_name", sa.String(255), nullable=False),
    sa.Column("arrival_time", sa.Time(), nullable=True),
    sa.Column("departure_time", sa.Time(), nullable=True),
    sa.Column("arrival_day_offset", sa.Integer(), nullable=False),
    sa.Column("departure_day_offset", sa.Integer(), nullable=False),
    sa.Column("day_of_week", postgresql.JSONB(), nullable=True),
    sa.Column("platform", sa.String(10), nullable=True),
    sa.Column("sequence", sa.Integer(), nullable=False),
    sa.Column("distance_from_origin_km", sa.Numeric(10, 2), nullable=True),
    sa.Column("route_progress", sa.Numeric(8, 6), nullable=True),
)

t_station_aliases = sa.Table(
    "station_aliases",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("station_id", sa.Integer(), nullable=False),
    sa.Column("source", sa.String(50), nullable=False),
    sa.Column("alias", sa.String(255), nullable=False),
    sa.Column("normalized_alias", sa.String(255), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

t_network_nodes = sa.Table(
    "network_nodes",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column(
        "location", Geometry("POINT", srid=4326, spatial_index=False), nullable=False
    ),
    sa.Column("node_type", sa.String(20), nullable=False),
    sa.Column("station_id", sa.Integer(), nullable=True),
    sa.Column("component_id", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

t_network_edges = sa.Table(
    "network_edges",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("from_node_id", sa.Integer(), nullable=False),
    sa.Column("to_node_id", sa.Integer(), nullable=False),
    sa.Column("from_station_id", sa.Integer(), nullable=False),
    sa.Column("to_station_id", sa.Integer(), nullable=False),
    sa.Column(
        "geometry",
        Geometry("LINESTRING", srid=4326, spatial_index=False),
        nullable=False,
    ),
    sa.Column("length_m", sa.Numeric(12, 2), nullable=True),
    sa.Column("edge_kind", sa.String(32), nullable=False),
    sa.Column("component_id", sa.Integer(), nullable=True),
    sa.Column("route_type", sa.String(50), nullable=True),
    sa.Column("line_name", sa.String(255), nullable=True),
    sa.Column("max_speed_kmh", sa.Integer(), nullable=True),
    sa.Column("track_class", sa.Integer(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

t_route_edges = sa.Table(
    "route_edges",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("route_id", sa.Integer(), nullable=False),
    sa.Column("edge_id", sa.Integer(), nullable=False),
    sa.Column("sequence", sa.Integer(), nullable=False),
    sa.Column("direction", sa.String(10), nullable=False),
)

t_network_links = sa.Table(
    "network_links",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("from_node_id", sa.Integer(), nullable=False),
    sa.Column("to_node_id", sa.Integer(), nullable=False),
    sa.Column(
        "geometry",
        Geometry("LINESTRING", srid=4326, spatial_index=False),
        nullable=False,
    ),
    sa.Column("length_m", sa.Numeric(12, 2), nullable=True),
    sa.Column("link_kind", sa.String(32), nullable=False),
    sa.Column("from_component_id", sa.Integer(), nullable=True),
    sa.Column("to_component_id", sa.Integer(), nullable=True),
    sa.Column("notes", sa.Text(), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True)),
)

t_topology_metadata = sa.Table(
    "topology_metadata",
    metadata,
    sa.Column("id", sa.Integer(), primary_key=True),
    sa.Column("topology_version", sa.String(64), nullable=False),
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
    sa.Column("built_at", sa.DateTime(timezone=True), nullable=False),
)
