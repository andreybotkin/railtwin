"""SQLAlchemy database models for Thailand Railway Digital Twin.

This module defines all database models using SQLAlchemy ORM with
PostGIS geometry types for geospatial data.
"""

from datetime import datetime, time
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
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
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    facilities: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
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
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule",
        back_populates="station",
        lazy="selectin",
    )
    route_stations: Mapped[list["RouteStation"]] = relationship(
        "RouteStation",
        back_populates="station",
        lazy="selectin",
    )
    aliases: Mapped[list["StationAlias"]] = relationship(
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
    station: Mapped["Station"] = relationship("Station", back_populates="aliases")


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
    trains: Mapped[list["Train"]] = relationship(
        "Train",
        back_populates="current_route",
        lazy="selectin",
    )
    route_stations: Mapped[list["RouteStation"]] = relationship(
        "RouteStation",
        back_populates="route",
        lazy="selectin",
        order_by="RouteStation.sequence",
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
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    distance_from_start: Mapped[float | None] = mapped_column(
        Numeric(10, 2),
        nullable=True,
    )

    # Relationships
    route: Mapped["Route"] = relationship("Route", back_populates="route_stations")
    station: Mapped["Station"] = relationship(
        "Station", back_populates="route_stations"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
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
    current_route: Mapped["Route | None"] = relationship(
        "Route",
        back_populates="trains",
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule",
        back_populates="train",
        lazy="selectin",
    )
    positions: Mapped[list["TrainPosition"]] = relationship(
        "TrainPosition",
        back_populates="train",
        lazy="selectin",
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
    train: Mapped["Train"] = relationship("Train", back_populates="schedules")
    station: Mapped["Station | None"] = relationship(
        "Station",
        back_populates="schedules",
    )
    route_station: Mapped["RouteStation | None"] = relationship(
        "RouteStation",
        back_populates="schedules",
    )


class TrainPosition(Base):
    """Real-time train position model.

    Represents the current or historical position of a train.

    Attributes:
        id: Primary key.
        train_id: Foreign key to train.
        location: Geographic point location (PostGIS).
        speed: Current speed in km/h.
        heading: Direction of travel in degrees.
        status: Train status (moving, stopped, delayed).
        delay_minutes: Delay in minutes if any.
        timestamp: Timestamp of this position record.
    """

    __tablename__ = "train_positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    train_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("trains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location: Mapped[Any] = mapped_column(
        Geometry("POINT", srid=4326),
        nullable=False,
    )
    speed: Mapped[float | None] = mapped_column(Numeric(6, 2), nullable=True)
    heading: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="moving",
    )
    delay_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    # Relationships
    train: Mapped["Train"] = relationship("Train", back_populates="positions")


# Create spatial indexes
(
    Station.__table__.append_constraint(
        type("", (), {"__visit_name__": "index", "name": "idx_stations_location"})
    )
    if False
    else None
)
