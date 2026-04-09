"""Pydantic schemas for Schedule models.

This module defines request and response schemas for schedule-related
API endpoints with proper validation and serialization.
"""

from datetime import time

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.station import StationSummary
from app.schemas.train import TrainSummary


class ScheduleBase(BaseModel):
    """Base schema for Schedule.

    Attributes:
        arrival_time: Scheduled arrival time (HH:MM:SS format).
        departure_time: Scheduled departure time (HH:MM:SS format).
        day_of_week: Days when schedule is active (0=Monday, 6=Sunday).
        platform: Platform number/name.
        sequence: Order of stop in train's schedule.
    """

    station_name: str | None = Field(None, max_length=255)
    arrival_time: time | None = None
    departure_time: time | None = None
    arrival_day_offset: int = Field(default=0, ge=0)
    departure_day_offset: int = Field(default=0, ge=0)
    day_of_week: list[int] | None = Field(
        default=[0, 1, 2, 3, 4, 5, 6],
        description="Days when active: 0=Monday, 6=Sunday",
    )
    platform: str | None = Field(None, max_length=10)
    sequence: int = Field(default=0, ge=0)
    route_station_id: int | None = Field(None, ge=1)
    distance_from_origin_km: float | None = Field(None, ge=0)
    route_progress: float | None = Field(None, ge=0, le=1)

    @field_validator("day_of_week", mode="before")
    @classmethod
    def validate_day_of_week(cls, v: list[int] | None) -> list[int] | None:
        """Validate day_of_week values are in range 0-6."""
        if v is None:
            return v
        for day in v:
            if not 0 <= day <= 6:
                raise ValueError("day_of_week values must be between 0 and 6")
        return v

    @model_validator(mode="after")
    def validate_day_offsets(self) -> "ScheduleBase":
        """Ensure departure offset cannot precede arrival offset."""
        if self.departure_day_offset < self.arrival_day_offset:
            raise ValueError(
                "departure_day_offset must be greater than or equal to arrival_day_offset"
            )
        return self


class ScheduleCreate(ScheduleBase):
    """Schema for creating a new schedule.

    Attributes:
        train_id: ID of the train.
        station_id: ID of the station.
    """

    train_id: int
    station_id: int | None = None

    @model_validator(mode="after")
    def validate_station_reference(self) -> "ScheduleCreate":
        """Require either canonical station mapping or raw station name."""
        if self.station_id is None and not self.station_name:
            raise ValueError("station_id or station_name is required")
        return self


class ScheduleUpdate(BaseModel):
    """Schema for updating an existing schedule.

    All fields are optional for partial updates.
    """

    station_id: int | None = None
    station_name: str | None = Field(None, max_length=255)
    arrival_time: time | None = None
    departure_time: time | None = None
    arrival_day_offset: int | None = Field(None, ge=0)
    departure_day_offset: int | None = Field(None, ge=0)
    day_of_week: list[int] | None = None
    platform: str | None = None
    sequence: int | None = None
    route_station_id: int | None = Field(None, ge=1)
    distance_from_origin_km: float | None = Field(None, ge=0)
    route_progress: float | None = Field(None, ge=0, le=1)


class ScheduleResponse(ScheduleBase):
    """Schema for schedule response.

    Includes all schedule fields plus related data.

    Attributes:
        id: Schedule ID.
        train_id: Train ID.
        station_id: Station ID.
        train: Train information.
        station: Station information.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    train_id: int
    station_id: int | None
    train: TrainSummary | None = None
    station: StationSummary | None = None


class ScheduleListResponse(BaseModel):
    """Schema for paginated schedule list response.

    Attributes:
        items: List of schedules.
        total: Total number of schedules.
        page: Current page number.
        size: Page size.
        pages: Total number of pages.
    """

    items: list[ScheduleResponse]
    total: int
    page: int
    size: int
    pages: int


class TrainScheduleResponse(BaseModel):
    """Schema for a train's complete schedule.

    Attributes:
        train: Train information.
        stops: List of scheduled stops in order.
    """

    train: TrainSummary
    stops: list[ScheduleResponse]


class StationScheduleResponse(BaseModel):
    """Schema for a station's departures/arrivals.

    Attributes:
        station: Station information.
        schedules: List of schedules at this station.
    """

    station: StationSummary
    schedules: list[ScheduleResponse]
