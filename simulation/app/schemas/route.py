"""Pydantic schemas for Route models.

This module defines request and response schemas for route-related
API endpoints with proper validation and serialization.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class GeoJSONLineString(BaseModel):
    """GeoJSON LineString geometry schema.

    Attributes:
        type: Geometry type (always "LineString").
        coordinates: List of [longitude, latitude] coordinates.
    """

    type: str = "LineString"
    coordinates: list[list[float]] = Field(
        ...,
        min_length=2,
        description="List of [longitude, latitude] coordinate pairs",
    )


class RouteStationInfo(BaseModel):
    """Station info within a route context.

    Attributes:
        id: Station ID.
        name: Station name.
        code: Station code.
        sequence: Order in the route.
        distance_from_start: Distance from route start in km.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    sequence: int
    distance_from_start: float | None = None


class RouteBase(BaseModel):
    """Base schema for Route.

    Attributes:
        name: Route name in English.
        name_th: Route name in Thai.
        route_type: Type of route (northern, northeastern, southern, eastern).
        distance_km: Total distance in kilometers.
        color: Display color in hex format.
    """

    name: str = Field(..., min_length=1, max_length=255)
    name_th: str | None = Field(None, max_length=255)
    route_type: str = Field(..., min_length=1, max_length=50)
    distance_km: float | None = Field(None, ge=0)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")


class RouteCreate(RouteBase):
    """Schema for creating a new route.

    Attributes:
        line_geometry: Geographic line geometry as GeoJSON.
    """

    line_geometry: GeoJSONLineString | None = None


class RouteUpdate(BaseModel):
    """Schema for updating an existing route.

    All fields are optional for partial updates.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    name_th: str | None = Field(None, max_length=255)
    route_type: str | None = Field(None, min_length=1, max_length=50)
    distance_km: float | None = Field(None, ge=0)
    color: str | None = Field(None, pattern=r"^#[0-9A-Fa-f]{6}$")
    line_geometry: GeoJSONLineString | None = None


class RouteResponse(RouteBase):
    """Schema for route response.

    Includes all route fields plus computed fields.

    Attributes:
        id: Route ID.
        line_geometry: Geographic line geometry.
        stations: List of stations on this route.
        created_at: Creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    line_geometry: GeoJSONLineString | None = None
    stations: list[RouteStationInfo] = []
    created_at: datetime


class RouteListResponse(BaseModel):
    """Schema for paginated route list response.

    Attributes:
        items: List of routes.
        total: Total number of routes.
        page: Current page number.
        size: Page size.
        pages: Total number of pages.
    """

    items: list[RouteResponse]
    total: int
    page: int
    size: int
    pages: int


class RouteSummary(BaseModel):
    """Minimal route info for use in other responses.

    Attributes:
        id: Route ID.
        name: Route name.
        route_type: Route type.
        color: Route color.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    route_type: str
    color: str | None = None
