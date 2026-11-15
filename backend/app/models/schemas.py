"""Modelos Pydantic: definen y validan el contrato JSON de la API."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    model_validator,
)


# ---------------------------------------------------------------- Comunes
class CellCoordinate(BaseModel):
    """Celda de la cuadrícula. Índices que empiezan en 0.

    `row` crece hacia abajo (fila 0 = borde superior).
    `col` crece hacia la derecha (columna 0 = borde izquierdo).
    NO son latitud ni longitud.
    """

    model_config = ConfigDict(extra="forbid")

    row: StrictInt = Field(description="Fila (0 = borde superior).", examples=[2])
    col: StrictInt = Field(description="Columna (0 = borde izquierdo).", examples=[3])


# ----------------------------------------------------------------- Health
class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str
    version: str
    api_version: str
    data_source: Literal["synthetic", "mola"] = "synthetic"


# -------------------------------------------------------------------- Map
class GridInfo(BaseModel):
    rows: int = Field(description="Número de filas.")
    cols: int = Field(description="Número de columnas.")
    cell_size_m: float = Field(description="Tamaño nominal de celda, en metros.")


class CoordinateSystem(BaseModel):
    type: Literal["grid_index"] = "grid_index"
    index_base: int = 0
    row_axis: Literal["down"] = "down"
    col_axis: Literal["right"] = "right"
    description: str


class CostModelInfo(BaseModel):
    formula: str
    slope_weight: float
    risk_weight: float
    radiation_weight: Optional[float] = Field(
        default=None, ge=0.0,
        description="Peso del índice de radiación MODELADO (opcional; 0 por defecto).",
    )
    diagonal_length_factor: float
    cost_unit: Literal["cost_units"] = "cost_units"


class MapCell(BaseModel):
    row: int
    col: int
    elevation_m: float = Field(description="Elevación en metros.")
    slope_deg: float = Field(description="Pendiente en grados.")
    risk: float = Field(
        ge=0.0,
        le=1.0,
        description="Riesgo 0.0–1.0 cuando está disponible; consulte risk_available.",
    )
    blocked: bool = Field(description="true = celda no transitable.")
    valid: Optional[bool] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    sky_view_factor: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Fracción del cielo no tapada por el relieve (derivada del DEM).",
    )
    radiation_modeled: Optional[float] = Field(
        default=None, ge=0.0, le=1.0,
        description="Índice relativo de radiación MODELADO 0–1; no es una dosis medida.",
    )


class GlobalGridCell(BaseModel):
    """Compact one-degree cell; row and column are implied by array order."""

    elevation_m: float
    slope_deg: float
    risk: float = Field(ge=0.0, le=1.0)
    blocked: bool
    valid: bool


class GlobalGridResponse(BaseModel):
    rows: int
    cols: int
    cell_size_m: float
    region: Dict[str, Any]
    cells: List[GlobalGridCell]


ProvenanceLabel = Literal[
    "MEDIDO", "DERIVADO", "INDICADOR", "MODELADO", "INTERPRETADO", "REFERENCIA",
    "ÍNDICE DEL PROYECTO",
]


class LayerProvenance(BaseModel):
    label: ProvenanceLabel
    source: str
    in_cost: bool = Field(description="Si la capa entra directamente al costo de A*.")
    note: Optional[str] = None


class MapResponse(BaseModel):
    name: str
    data_source: Literal["synthetic", "mola"] = "synthetic"
    is_simulated: bool = True
    disclaimer: str
    grid: GridInfo
    coordinate_system: CoordinateSystem
    cost_model: CostModelInfo
    cells: List[MapCell]
    risk_available: bool = True
    risk_model: Optional[Dict[str, Any]] = None
    radiation_available: Optional[bool] = None
    radiation_model: Optional[Dict[str, Any]] = None
    region: Optional[Dict[str, Any]] = None
    global_grid: Optional[GlobalGridResponse] = None
    provenance: Optional[Dict[str, LayerProvenance]] = Field(
        default=None,
        description="Procedencia por capa (solo fuentes reales y capas presentes).",
    )


# ----------------------------------------------------------------- Routes
class RouteLocation(BaseModel):
    """A legacy grid index or a geographic point for MOLA routing."""

    model_config = ConfigDict(extra="forbid")

    row: Optional[StrictInt] = None
    col: Optional[StrictInt] = None
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0, allow_inf_nan=False)
    longitude: Optional[float] = Field(default=None, ge=0.0, le=360.0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_coordinate_pair(self) -> "RouteLocation":
        has_row = self.row is not None
        has_col = self.col is not None
        has_latitude = self.latitude is not None
        has_longitude = self.longitude is not None
        if has_row != has_col or has_latitude != has_longitude:
            raise ValueError("Cada ubicación requiere ambos índices o latitud y longitud.")
        if has_row == has_latitude:
            raise ValueError("Use índices row/col o coordenadas latitude/longitude, no ambos.")
        return self


MAX_REQUEST_WEIGHT = 100.0


def _weight_field(description: str) -> Any:
    return Field(
        default=None, ge=0.0, le=MAX_REQUEST_WEIGHT, strict=True, allow_inf_nan=False,
        description=description,
    )


class CostWeightsRequest(BaseModel):
    """Pesos opcionales por solicitud. Ausentes = pesos por defecto del servidor."""

    model_config = ConfigDict(extra="forbid")

    slope_weight: Optional[float] = _weight_field(
        "Peso de la pendiente (0–100). Por defecto, el de cost_model en /map (0.05)."
    )
    radiation_weight: Optional[float] = _weight_field(
        "Peso del índice de radiación MODELADO (0–100). Por defecto 0."
    )


class RouteRequest(CostWeightsRequest):
    """Solicitud de ruta por índices o coordenadas MOLA."""

    model_config = ConfigDict(extra="forbid")

    origin: RouteLocation
    destination: RouteLocation
    allow_diagonal: StrictBool = Field(
        default=True, description="Permite movimientos diagonales."
    )

    @model_validator(mode="after")
    def use_consistent_location_formats(self) -> "RouteRequest":
        if (self.origin.latitude is None) != (self.destination.latitude is None):
            raise ValueError(
                "Origen y destino deben usar ambos índices o ambas coordenadas geográficas."
            )
        return self


class ShelterRequest(CostWeightsRequest):
    """Modo «alerta solar»: ruta desde un origen a la zona candidata de espera más cercana."""

    model_config = ConfigDict(extra="forbid")

    origin: RouteLocation
    allow_diagonal: StrictBool = Field(
        default=True, description="Permite movimientos diagonales."
    )
    max_slope_deg: Optional[float] = Field(
        default=None, ge=0.0, le=90.0, strict=True, allow_inf_nan=False,
        description="Pendiente máxima de la zona candidata, en grados (por defecto 10).",
    )
    max_sky_view_factor: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, strict=True, allow_inf_nan=False,
        description="Fracción de cielo visible máxima de la zona candidata (por defecto 0.90).",
    )
    max_distance_km: Optional[float] = Field(
        default=None, gt=0.0, strict=True, allow_inf_nan=False,
        description="Distancia máxima (km) de la ruta de menor costo hasta la zona "
                    "candidata. Sin valor por defecto: ausente = sin límite.",
    )


class RoutePointResult(BaseModel):
    row: int
    col: int
    latitude: Optional[float] = None
    longitude: Optional[float] = None


class RouteSummary(BaseModel):
    steps: int = Field(description="Número de movimientos (len(path) - 1).")
    distance_m: float = Field(
        description="Distancia en metros; aproximada con el tamaño nominal de celda."
    )
    total_cost: float = Field(description="Costo total en cost_units (adimensional).")
    max_slope_deg: float
    mean_risk: float
    max_risk: float
    nodes_expanded: int = Field(description="Nodos expandidos por A* (informativo).")


class AppliedCostWeights(BaseModel):
    slope_weight: float
    risk_weight: float
    radiation_weight: float


class RouteResponse(BaseModel):
    status: Literal["ok"] = "ok"
    data_source: Literal["synthetic", "mola"] = "synthetic"
    is_simulated: bool = True
    disclaimer: str
    origin: RoutePointResult
    destination: RoutePointResult
    allow_diagonal: bool
    path: List[RoutePointResult] = Field(
        description="Celdas de la ruta en orden, incluyendo origen y destino."
    )
    summary: RouteSummary
    resolution: Optional[Literal["mola-detail", "mola-global-1deg"]] = None
    cost_weights: Optional[AppliedCostWeights] = Field(
        default=None,
        description="Pesos aplicados; solo aparece si la solicitud trae algún peso.",
    )


class ShelterInfo(BaseModel):
    term: Literal["zona candidata de espera"] = "zona candidata de espera"
    label: Literal["ÍNDICE DEL PROYECTO"] = "ÍNDICE DEL PROYECTO"
    criterion: str
    max_slope_deg: float
    max_sky_view_factor: float
    candidates_count: int = Field(description="Celdas libres que cumplen el criterio.")
    distance_km: float = Field(
        description="Distancia recorrida hasta la zona, en km (aproximada, tamaño nominal de celda)."
    )
    max_distance_km: Optional[float] = None
    destination_slope_deg: float
    destination_sky_view_factor: float
    sky_view_factor_role: str
    note: str


class ShelterRouteResponse(RouteResponse):
    shelter: ShelterInfo


# ----------------------------------------------------------------- Errores
class ErrorBody(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorBody
