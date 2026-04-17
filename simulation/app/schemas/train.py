"""Pydantic schemas for Train models.

This module defines request and response schemas for train-related
API endpoints with proper validation and serialization.
"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.route import RouteSummary


class TrainBase(BaseModel):
    """Base schema for Train.

    Attributes:
        train_number: Unique train identifier.
        train_type: Type of train (express, rapid, ordinary, special_express).
        name: Train name/service name.
        capacity: Passenger capacity.
        operator: Operating company.
    """

    train_number: str = Field(..., min_length=1, max_length=20)
    train_type: str = Field(..., min_length=1, max_length=50)
    name: str | None = Field(None, max_length=100)
    capacity: int | None = Field(None, ge=0)
    operator: str = Field(default="State Railway of Thailand", max_length=100)
    source: str = Field(default="manual", min_length=1, max_length=50)
    source_url: str | None = None
    service_notes: dict | list[str] | None = None


class TrainCreate(TrainBase):
    """Schema for creating a new train.

    Attributes:
        current_route_id: ID of the current route.
    """

    current_route_id: int | None = None


class TrainUpdate(BaseModel):
    """Schema for updating an existing train.

    All fields are optional for partial updates.
    """

    train_number: str | None = Field(None, min_length=1, max_length=20)
    train_type: str | None = Field(None, min_length=1, max_length=50)
    name: str | None = Field(None, max_length=100)
    capacity: int | None = Field(None, ge=0)
    operator: str | None = Field(None, max_length=100)
    source: str | None = Field(None, min_length=1, max_length=50)
    source_url: str | None = None
    service_notes: dict | list[str] | None = None
    current_route_id: int | None = None


class TrainResponse(TrainBase):
    """Schema for train response.

    Includes all train fields plus computed fields.

    Attributes:
        id: Train ID.
        current_route: Current route information.
        created_at: Creation timestamp.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    current_route_id: int | None = None
    current_route: RouteSummary | None = None
    created_at: datetime


class TrainListResponse(BaseModel):
    """Schema for paginated train list response.

    Attributes:
        items: List of trains.
        total: Total number of trains.
        page: Current page number.
        size: Page size.
        pages: Total number of pages.
    """

    items: list[TrainResponse]
    total: int
    page: int
    size: int
    pages: int


class TrainSummary(BaseModel):
    """Minimal train info for use in other responses.

    Attributes:
        id: Train ID.
        train_number: Train number.
        train_type: Train type.
        name: Train name.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    train_number: str
    train_type: str
    name: str | None = None
