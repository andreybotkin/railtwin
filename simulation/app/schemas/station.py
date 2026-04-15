"""Pydantic schemas for Station models.

This module defines request and response schemas for station-related
API endpoints with proper validation and serialization.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GeoJSONPoint(BaseModel):
    """GeoJSON Point geometry schema.

    Attributes:
        type: Geometry type (always "Point").
        coordinates: [longitude, latitude] coordinates.
    """

    type: str = "Point"
    coordinates: list[float] = Field(
        ...,
        min_length=2,
        max_length=2,
        description="[longitude, latitude] coordinates",
    )


class StationFacilities(BaseModel):
    """Station facilities schema.

    Attributes:
        parking: Parking availability.
        restaurant: Restaurant availability.
        atm: ATM availability.
        toilet: Toilet availability.
        wifi: WiFi availability.
    """

    parking: bool = False
    restaurant: bool = False
    atm: bool = False
    toilet: bool = True
    wifi: bool = False


class StationBase(BaseModel):
    """Base schema for Station.

    Attributes:
        name: Station name in English.
        name_th: Station name in Thai.
        code: Unique station code.
        city: City where station is located.
        province: Province where station is located.
        facilities: Available facilities at the station.
    """

    name: str = Field(..., min_length=1, max_length=255)
    name_th: str | None = Field(None, max_length=255)
    code: str = Field(..., min_length=1, max_length=10)
    city: str | None = Field(None, max_length=100)
    province: str | None = Field(None, max_length=100)
    facilities: StationFacilities | None = None


class StationCreate(StationBase):
    """Schema for creating a new station.

    Attributes:
        location: Geographic coordinates as [longitude, latitude].
    """

    location: GeoJSONPoint


class StationUpdate(BaseModel):
    """Schema for updating an existing station.

    All fields are optional for partial updates.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    name_th: str | None = Field(None, max_length=255)
    code: str | None = Field(None, min_length=1, max_length=10)
    city: str | None = Field(None, max_length=100)
    province: str | None = Field(None, max_length=100)
    facilities: StationFacilities | None = None
    location: GeoJSONPoint | None = None


class StationResponse(StationBase):
    """Schema for station response.

    Includes all station fields plus computed fields.

    Attributes:
        id: Station ID.
        location: Geographic coordinates.
        created_at: Creation timestamp.
        updated_at: Last update timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    location: GeoJSONPoint
    created_at: datetime
    updated_at: datetime


class StationListResponse(BaseModel):
    """Schema for paginated station list response.

    Attributes:
        items: List of stations.
        total: Total number of stations.
        page: Current page number.
        size: Page size.
        pages: Total number of pages.
    """

    items: list[StationResponse]
    total: int
    page: int
    size: int
    pages: int


class StationSummary(BaseModel):
    """Minimal station info for use in other responses.

    Attributes:
        id: Station ID.
        name: Station name.
        code: Station code.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
