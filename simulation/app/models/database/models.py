"""SQLAlchemy database models for Thailand Railway Digital Twin.

This module defines all database models using SQLAlchemy ORM with
PostGIS geometry types for geospatial data.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.database import Base


class Station(Base):
    """Railway station model.

    Represents a train station with geographic location and facilities.

    Attributes:
        id: Primary key.
        name: Station name (Thai and English).
        name_th: Station name in Thai.
        code: Unique station code.
        location: Geographic point location (PostGIS).
        city: City where station is located.
        province: Province where station is located.
        facilities: JSON object with available facilities.
        created_at: Timestamp when record was created.
        updated_at: Timestamp when record was last updated.
    """

    __tablename__ = "stations"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_th: Mapped[str | None] = mapped_column(String(255), nullable=True)
    code: Mapped[str] = mapped_column(
        String(10), unique=True, nullable=False, index=True
    )
    location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
    )
    _geojson: str | None = None
    source_route_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    facilities: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Network topology columns (added by migration 005)
    snapped_location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=True,
    )
    snap_distance_m: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    node_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("network_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    schedules: Mapped[list[Schedule]] = relationship(
        "Schedule",
        back_populates="station",
        lazy="selectin",
    )
    route_stations: Mapped[list[RouteStation]] = relationship(
        "RouteStation",
        back_populates="station",
        lazy="selectin",
    )
    aliases: Mapped[list[StationAlias]] = relationship(
        "StationAlias",
        back_populates="station",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class StationAlias(Base):
    """Alternative station names from external timetable sources.

    Allows external schedules to be stored even when the provider naming does
    not exactly match the canonical station record used by the map geometry.
    """

    __tablename__ = "station_aliases"
    __table_args__ = (
        UniqueConstraint("source", "alias", name="uq_station_alias_source_alias"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    station_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    alias: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    station: Mapped[Station] = relationship("Station", back_populates="aliases")


class Route(Base):
    """Railway route model.

    Represents a railway line/route with its geographic geometry.

    Attributes:
        id: Primary key.
        name: Route name.
        name_th: Route name in Thai.
        line_geometry: Geographic line geometry (PostGIS).
        distance_km: Total route distance in kilometers.
        route_type: Type of route (northern, northeastern, southern, eastern).
        color: Route display color (hex).
        created_at: Timestamp when record was created.
    """

    __tablename__ = "routes"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_th: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line_geometry: Mapped[Any] = mapped_column(
        Geometry("LINESTRING", srid=4326),
        nullable=True,
    )
    _geojson: str | None = None
    distance_km: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    route_type: Mapped[str] = mapped_column(String(50), nullable=False)
    color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    trains: Mapped[list[Train]] = relationship(
        "Train",
        back_populates="current_route",
        lazy="selectin",
    )
    route_stations: Mapped[list[RouteStation]] = relationship(
        "RouteStation",
        back_populates="route",
        lazy="selectin",
        order_by="RouteStation.sequence",
    )
    planned_runs: Mapped[list[PlannedTrainRun]] = relationship(
        "PlannedTrainRun",
        back_populates="route",
        lazy="noload",
    )


class RouteStation(Base):
    """Junction table for routes and stations with ordering.

    Represents the stations on a route in order.

    Attributes:
        id: Primary key.
        route_id: Foreign key to route.
        station_id: Foreign key to station.
        sequence: Order of station on the route.
        distance_from_start: Distance from route start in km.
    """

    __tablename__ = "route_stations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    station_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    node_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("network_nodes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_from_start: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    # Network topology columns (added by migration 005)
    edge_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("network_edges.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    snapped_location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=True,
    )
    snap_distance_m: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Relationships
    route: Mapped[Route] = relationship("Route", back_populates="route_stations")
    station: Mapped[Station] = relationship("Station", back_populates="route_stations")
    schedules: Mapped[list[Schedule]] = relationship(
        "Schedule",
        back_populates="route_station",
        lazy="selectin",
    )


class Train(Base):
    """Train model.

    Represents a train with its specifications.

    Attributes:
        id: Primary key.
        train_number: Unique train number/identifier.
        train_type: Type of train (express, rapid, ordinary, etc.).
        name: Train name (if any).
        capacity: Passenger capacity.
        operator: Operating company.
        current_route_id: Current route the train is on.
        created_at: Timestamp when record was created.
    """

    __tablename__ = "trains"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    train_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        nullable=False,
        index=True,
    )
    train_type: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locomotive_mass_t: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    rolling_stock_mass_t: Mapped[float | None] = mapped_column(Numeric(9, 2), nullable=True)
    horsepower: Mapped[float | None] = mapped_column(Numeric(8, 1), nullable=True)
    max_tractive_effort_kn: Mapped[float | None] = mapped_column(
        Numeric(8, 2), nullable=True
    )
    max_brake_deceleration_mps2: Mapped[float | None] = mapped_column(
        Numeric(5, 3), nullable=True
    )
    max_speed_kmh: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    passenger_load: Mapped[int | None] = mapped_column(Integer, nullable=True)
    passenger_mass_kg: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    operator: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="State Railway of Thailand",
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    service_notes: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    current_route_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    current_route: Mapped[Route | None] = relationship(
        "Route",
        back_populates="trains",
    )
    schedules: Mapped[list[Schedule]] = relationship(
        "Schedule",
        back_populates="train",
        lazy="selectin",
    )
    planned_runs: Mapped[list[PlannedTrainRun]] = relationship(
        "PlannedTrainRun",
        back_populates="train",
        lazy="noload",
    )


class Schedule(Base):
    """Train schedule model.

    Represents a scheduled stop for a train at a station.

    Attributes:
        id: Primary key.
        train_id: Foreign key to train.
        station_id: Foreign key to station.
        arrival_time: Scheduled arrival time.
        departure_time: Scheduled departure time.
        day_of_week: Days when this schedule is active (0=Monday, 6=Sunday).
        platform: Platform number/name.
        sequence: Order of this stop in the train's schedule.
    """

    __tablename__ = "schedules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    train_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    station_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    route_station_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("route_stations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    station_name: Mapped[str] = mapped_column(String(255), nullable=False)
    arrival_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    departure_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    arrival_day_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    departure_day_offset: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    day_of_week: Mapped[list[int] | None] = mapped_column(
        JSON,
        nullable=True,
    )
    platform: Mapped[str | None] = mapped_column(String(10), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    distance_from_origin_km: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )
    route_progress: Mapped[float | None] = mapped_column(
        Numeric(8, 6),
        nullable=True,
    )

    # Relationships
    train: Mapped[Train] = relationship("Train", back_populates="schedules")
    station: Mapped[Station | None] = relationship(
        "Station",
        back_populates="schedules",
    )
    route_station: Mapped[RouteStation | None] = relationship(
        "RouteStation",
        back_populates="schedules",
    )


class NetworkNode(Base):
    """A vertex in the railway topology graph.

    Graph nodes are station-only. The ``station_id`` foreign key links each
    node to exactly one station record, while ``location`` stores the canonical
    graph position used for station-to-station edges.
    """

    __tablename__ = "network_nodes"
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
    )
    node_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="station",
    )
    station_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
        index=True,
    )
    component_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    outgoing_edges: Mapped[list[NetworkEdge]] = relationship(
        "NetworkEdge",
        foreign_keys="NetworkEdge.from_node_id",
        back_populates="from_node",
        lazy="noload",
    )
    incoming_edges: Mapped[list[NetworkEdge]] = relationship(
        "NetworkEdge",
        foreign_keys="NetworkEdge.to_node_id",
        back_populates="to_node",
        lazy="noload",
    )


class NetworkEdge(Base):
    """A directed station-to-station arc.

    The ``geometry`` stores the actual track geometry extracted from the KML
    route LineString via ST_LineSubstring.  Both the forward edge (A→B) and
    reverse edge (B→A) are stored as separate rows.

    ``length_m`` is computed by PostGIS from the geography cast of the
    sub-LineString during topology build.
    """

    __tablename__ = "network_edges"
    __table_args__ = (
        UniqueConstraint(
            "from_station_id",
            "to_station_id",
            name="uq_network_edges_station_ids_directed",
        ),
    )
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("network_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("network_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_station_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_station_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    geometry: Mapped[Any] = mapped_column(
        Geometry("LINESTRING", srid=4326),
        nullable=False,
    )
    length_m: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    edge_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="track")
    component_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    route_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    line_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    max_speed_kmh: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elevation_profile: Mapped[list[dict[str, float]] | None] = mapped_column(
        JSON, nullable=True
    )
    speed_limit_zones: Mapped[list[dict[str, float]] | None] = mapped_column(
        JSON, nullable=True
    )
    track_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    from_node: Mapped[NetworkNode] = relationship(
        "NetworkNode",
        foreign_keys=[from_node_id],
        back_populates="outgoing_edges",
    )
    to_node: Mapped[NetworkNode] = relationship(
        "NetworkNode",
        foreign_keys=[to_node_id],
        back_populates="incoming_edges",
    )
    route_edges: Mapped[list[RouteEdge]] = relationship(
        "RouteEdge",
        back_populates="edge",
        lazy="noload",
    )
    edge_routes: Mapped[list[NetworkEdgeRoute]] = relationship(
        "NetworkEdgeRoute",
        back_populates="edge",
        lazy="noload",
        cascade="all, delete-orphan",
    )


class NetworkLink(Base):
    """Operational bridge between disconnected station-bearing components.

    These links are not part of the physical railway geometry. They are stored
    separately so the map-facing track graph remains strictly KML-backed.
    """

    __tablename__ = "network_links"
    __table_args__ = (
        UniqueConstraint(
            "from_node_id",
            "to_node_id",
            "link_kind",
            name="uq_network_links_directed_kind",
        ),
    )
    __allow_unmapped__ = True

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    from_node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("network_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    to_node_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("network_nodes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    geometry: Mapped[Any] = mapped_column(
        Geometry("LINESTRING", srid=4326),
        nullable=False,
    )
    length_m: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    link_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_component_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    to_component_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class TopologyMetadata(Base):
    """Singleton snapshot of the last successful topology build."""

    __tablename__ = "topology_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    topology_version: Mapped[str] = mapped_column(String(64), nullable=False)
    physical_nodes_count: Mapped[int] = mapped_column(Integer, nullable=False)
    physical_edges_count: Mapped[int] = mapped_column(Integer, nullable=False)
    station_nodes_count: Mapped[int] = mapped_column(Integer, nullable=False)
    physical_components_count: Mapped[int] = mapped_column(Integer, nullable=False)
    station_components_count: Mapped[int] = mapped_column(Integer, nullable=False)
    operational_links_count: Mapped[int] = mapped_column(Integer, nullable=False)
    main_component_station_count: Mapped[int] = mapped_column(Integer, nullable=False)
    disconnected_station_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unsnapped_station_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_snap_distance_m: Mapped[float | None] = mapped_column(
        Numeric(10, 2), nullable=True
    )
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )


class NetworkEdgeRoute(Base):
    """Maps physical graph edges back to the KML source routes they belong to."""

    __tablename__ = "network_edge_routes"
    __table_args__ = (
        UniqueConstraint(
            "edge_id", "route_id", name="uq_network_edge_routes_edge_route"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    edge_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("network_edges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route_fraction: Mapped[float | None] = mapped_column(Numeric(8, 6), nullable=True)

    edge: Mapped[NetworkEdge] = relationship(
        "NetworkEdge", back_populates="edge_routes"
    )
    route: Mapped[Route] = relationship("Route", lazy="noload")


class RouteEdge(Base):
    """Maps a route to its ordered sequence of directed network edges.

    A route is fully described by the ordered list of edges whose
    from_node / to_node station pairs match consecutive scheduled stops.
    """

    __tablename__ = "route_edges"
    __table_args__ = (
        UniqueConstraint("route_id", "sequence", name="uq_route_edges_route_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    edge_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("network_edges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    direction: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="forward",
    )

    # Relationships
    route: Mapped[Route] = relationship("Route", lazy="noload")
    edge: Mapped[NetworkEdge] = relationship(
        "NetworkEdge",
        back_populates="route_edges",
    )


class PlannedTrainRun(Base):
    """Precomputed movement plan header for one train+route pair.

    Stores plan metadata and links to the ordered movement segments.  No
    route geometry is stored here — all coordinate data is accessed via
    ``route_id`` and the existing ``route_edges`` / ``network_edges`` tables.

    Uniqueness is enforced by two partial indexes instead of a single
    UNIQUE constraint because ``service_date`` is nullable.  In PostgreSQL
    a UNIQUE constraint treats NULL values as non-equal, which would allow
    duplicate rows when ``service_date IS NULL``.  The partial indexes in
    migration 010 encode the correct semantic:
      - ``uq_planned_runs_no_date``  : (train_id, route_id, plan_version)
                                       WHERE service_date IS NULL
      - ``uq_planned_runs_with_date``: (train_id, route_id, service_date,
                                       plan_version) WHERE service_date
                                       IS NOT NULL

    See docs/precomputed-movement-plan.md §3.1 for details.
    """

    __tablename__ = "planned_train_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    train_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    route_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("routes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # NULL means the plan applies to every operating day (typical).
    service_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    # Optional human-readable tag for within-week variation.
    service_pattern: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Opaque version string; incremented on each rebuild for the same key.
    plan_version: Mapped[str] = mapped_column(String(64), nullable=False)
    # topology_metadata.topology_version at build time; NULL means unknown.
    topology_version: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    # Allowed values: 'ready' | 'degraded' | 'invalid'
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="ready", index=True
    )
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    train: Mapped[Train] = relationship(
        "Train",
        back_populates="planned_runs",
        lazy="noload",
    )
    route: Mapped[Route] = relationship(
        "Route",
        back_populates="planned_runs",
        lazy="noload",
    )
    segments: Mapped[list[PlannedMovementSegment]] = relationship(
        "PlannedMovementSegment",
        back_populates="planned_run",
        lazy="selectin",
        order_by="PlannedMovementSegment.sequence",
        cascade="all, delete-orphan",
    )


class PlannedMovementSegment(Base):
    """Single contiguous movement or dwell period within a planned train run.

    Time bounds are stored as integer minutes-since-midnight per calendar day
    (mirroring ``schedule.arrival/departure_day_offset``).  Absolute minutes
    (spanning midnight crossings) are stored as denormalised columns for
    efficient range queries — the plan builder computes them as:

        absolute_*_minutes = *_time_minutes + *_day_offset * 1440

    **No geometry is duplicated.**  The route polyline is accessed via the
    parent ``PlannedTrainRun.route_id`` and the existing ``route_edges`` /
    ``network_edges`` tables.  ``start_geom_fraction`` / ``end_geom_fraction``
    are precomputed fractions [0, 1] along that polyline, resolved once at
    plan-build time so runtime interpolation needs no PostGIS calls.

    See docs/precomputed-movement-plan.md §3.2 for the full field spec.
    """

    __tablename__ = "planned_movement_segments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    planned_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("planned_train_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    # Allowed values: 'move' | 'dwell'
    segment_type: Mapped[str] = mapped_column(String(8), nullable=False)

    from_station_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    to_station_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("stations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    from_schedule_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("schedules.id", ondelete="SET NULL"),
        nullable=True,
    )
    to_schedule_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("schedules.id", ondelete="SET NULL"),
        nullable=True,
    )

    start_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    end_time_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    start_day_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    end_day_offset: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Denormalised absolute minutes for range queries; see class docstring.
    absolute_start_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    absolute_end_minutes: Mapped[int] = mapped_column(Integer, nullable=False)

    start_distance_m: Mapped[float | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    end_distance_m: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    start_geom_fraction: Mapped[float | None] = mapped_column(
        Numeric(10, 8), nullable=True
    )
    end_geom_fraction: Mapped[float | None] = mapped_column(
        Numeric(10, 8), nullable=True
    )

    start_edge_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("network_edges.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    end_edge_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("network_edges.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    planned_speed_kmh: Mapped[float | None] = mapped_column(
        Numeric(7, 2), nullable=True
    )
    quality_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    planned_run: Mapped[PlannedTrainRun] = relationship(
        "PlannedTrainRun",
        back_populates="segments",
        lazy="noload",
    )
