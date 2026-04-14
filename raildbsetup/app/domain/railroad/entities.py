from dataclasses import dataclass, field


@dataclass
class StationData:
    """Domain entity: railway station parsed from a data source."""

    name: str
    lon: float
    lat: float
    folder: str = ""
    source_line: str = ""
    route_type: str = "other"
    # Enriched fields from thai_railway_stations_full.json
    name_th: str = ""
    code: str = ""
    station_class: str = ""
    district: str = ""

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if not self.name or not self.name.strip():
            errors.append("Station name is empty")
        if not (-90.0 <= self.lat <= 90.0):
            errors.append(f"Station '{self.name}': latitude {self.lat} out of range [-90, 90]")
        if not (-180.0 <= self.lon <= 180.0):
            errors.append(f"Station '{self.name}': longitude {self.lon} out of range [-180, 180]")
        return errors


@dataclass
class RouteData:
    """Domain entity: railway route / line."""

    name: str
    route_type: str
    color: str
    coords: list[tuple[float, float]] = field(default_factory=list)
    folder: str = ""

    VALID_ROUTE_TYPES = frozenset({
        "northern", "northeastern", "western", "southern",
        "eastern", "urban", "other",
    })

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if not self.name or not self.name.strip():
            errors.append("Route name is empty")
        if len(self.coords) < 2:
            errors.append(f"Route '{self.name}': fewer than 2 coordinates ({len(self.coords)})")
        if self.route_type not in self.VALID_ROUTE_TYPES:
            errors.append(
                f"Route '{self.name}': unknown route_type '{self.route_type}'; "
                f"expected one of {sorted(self.VALID_ROUTE_TYPES)}"
            )
        return errors
