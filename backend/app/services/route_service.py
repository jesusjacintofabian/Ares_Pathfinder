"""Servicio de rutas: conecta la API con el algoritmo A*."""

from dataclasses import replace
from typing import Any, Dict, Optional, Tuple

from algorithms.astar import (
    BlockedCellError,
    CostModel,
    InvalidCellError,
    NoRouteError,
    find_path,
)

from app.errors import ApiError
from app.models.schemas import CostWeightsRequest, RouteRequest
from app.services.map_service import get_active_dataset


def compute_route(request: RouteRequest) -> Dict[str, Any]:
    """Valida la solicitud, ejecuta A* y devuelve un dict compatible con RouteResponse."""
    dataset = get_active_dataset()
    coordinate_route = request.origin.latitude is not None
    resolution = None
    route_region: Dict[str, Any] | None = None
    grid = dataset.grid

    if coordinate_route and dataset.data_source != "mola":
        raise ApiError(
            400,
            "GEOGRAPHIC_ROUTE_UNAVAILABLE",
            "Las coordenadas geográficas solo están disponibles con datos MOLA.",
        )

    if coordinate_route:
        if (
            request.origin.latitude is None
            or request.origin.longitude is None
            or request.destination.latitude is None
            or request.destination.longitude is None
        ):
            raise ApiError(
                422,
                "INVALID_GEOGRAPHIC_COORDINATES",
                "El origen y el destino requieren latitud y longitud.",
            )
        origin_geo = (float(request.origin.latitude), float(request.origin.longitude))
        destination_geo = (
            float(request.destination.latitude),
            float(request.destination.longitude),
        )
        detail_region: Dict[str, Any] | None = dataset.payload.get("region")
        if detail_region is not None and all(
            _inside_region(latitude, longitude, detail_region)
            for latitude, longitude in (origin_geo, destination_geo)
        ):
            resolution = "mola-detail"
            route_region = detail_region
        else:
            global_grid = dataset.global_grid
            global_region = dataset.global_grid_region
            if global_grid is None or global_region is None:
                raise ApiError(
                    503,
                    "GLOBAL_MOLA_UNAVAILABLE",
                    "La cuadrícula MOLA global no está disponible.",
                )
            resolution = "mola-global-1deg"
            grid = global_grid
            route_region = global_region
        origin = _coordinate_to_index(origin_geo, route_region, grid.rows, grid.cols)
        destination = _coordinate_to_index(
            destination_geo, route_region, grid.rows, grid.cols
        )
    else:
        if (
            request.origin.row is None
            or request.origin.col is None
            or request.destination.row is None
            or request.destination.col is None
        ):
            raise ApiError(
                422,
                "INVALID_GRID_COORDINATES",
                "El origen y el destino requieren fila y columna.",
            )
        origin = (request.origin.row, request.origin.col)
        destination = (request.destination.row, request.destination.col)

    cost_model, applied_weights = request_cost_model(request, dataset.cost_model)
    try:
        result = find_path(
            grid,
            origin,
            destination,
            cost_model=cost_model,
            allow_diagonal=request.allow_diagonal,
        )
    except InvalidCellError as exc:
        which = "origin" if exc.cell == origin else "destination"
        details: Dict[str, Any] = {"field": which}
        if isinstance(exc.cell, (tuple, list)) and len(exc.cell) == 2:
            details.update({"row": exc.cell[0], "col": exc.cell[1]})
        raise ApiError(
            400,
            "OUT_OF_BOUNDS",
            f"La celda de {'origen' if which == 'origin' else 'destino'} está fuera "
            f"de la cuadrícula ({grid.rows} filas x {grid.cols} columnas).",
            {**details, "rows": grid.rows, "cols": grid.cols},
        ) from exc
    except BlockedCellError as exc:
        which = "origin" if exc.cell == origin else "destination"
        raise ApiError(
            400,
            "CELL_BLOCKED",
            f"La celda de {'origen' if which == 'origin' else 'destino'} "
            f"({exc.cell[0]}, {exc.cell[1]}) está bloqueada.",
            {"field": which, "row": exc.cell[0], "col": exc.cell[1]},
        ) from exc
    except NoRouteError as exc:
        raise ApiError(
            404,
            "NO_ROUTE",
            "No existe una ruta transitable entre el origen y el destino.",
            {"origin": {"row": origin[0], "col": origin[1]},
             "destination": {"row": destination[0], "col": destination[1]},
             "nodes_expanded": exc.nodes_expanded},
        ) from exc

    origin_point: Dict[str, Any] = {"row": origin[0], "col": origin[1]}
    destination_point: Dict[str, Any] = {
        "row": destination[0],
        "col": destination[1],
    }
    path_points: list[Dict[str, Any]] = [
        {"row": row, "col": col} for row, col in result.path
    ]
    response: Dict[str, Any] = {
        "status": "ok",
        "data_source": dataset.data_source,
        "is_simulated": dataset.is_simulated,
        "disclaimer": dataset.disclaimer,
        "origin": origin_point,
        "destination": destination_point,
        "allow_diagonal": request.allow_diagonal,
        "path": path_points,
        "summary": {
            "steps": len(result.path) - 1,
            "distance_m": round(result.distance_m, 2),
            "total_cost": round(result.total_cost, 4),
            "max_slope_deg": result.max_slope_deg,
            "mean_risk": round(result.mean_risk, 4),
            "max_risk": result.max_risk,
            "nodes_expanded": result.nodes_expanded,
        },
    }
    if applied_weights is not None:
        response["cost_weights"] = applied_weights
    if coordinate_route:
        if resolution is None or route_region is None:
            raise ApiError(
                503,
                "GLOBAL_MOLA_UNAVAILABLE",
                "No se pudo determinar la cuadrícula MOLA para la ruta.",
            )
        response["resolution"] = resolution
        origin_point.update(_index_to_coordinates(origin, route_region, grid))
        destination_point.update(_index_to_coordinates(destination, route_region, grid))
        for point, cell in zip(path_points, result.path):
            point.update(_index_to_coordinates(cell, route_region, grid))
        if resolution == "mola-global-1deg":
            response["disclaimer"] = (
                "Ruta aproximada sobre una malla MOLA de 1° (unos 59 km por celda "
                "en el ecuador). No es adecuada para navegación operacional; no "
                "modela todos los riesgos ni condiciones de misión."
            )
    return response


def request_cost_model(
    request: CostWeightsRequest, default: CostModel
) -> Tuple[CostModel, Optional[Dict[str, float]]]:
    """Pesos de la solicitud sobre los del servidor.

    Devuelve también los pesos aplicados, o None si la solicitud no trae ninguno
    (así una solicitud antigua produce exactamente la misma respuesta que antes).
    """
    overrides = {
        name: value
        for name, value in (
            ("slope_weight", request.slope_weight),
            ("radiation_weight", request.radiation_weight),
        )
        if value is not None
    }
    if not overrides:
        return default, None
    model = replace(default, **overrides)
    return model, {
        "slope_weight": model.slope_weight,
        "risk_weight": model.risk_weight,
        "radiation_weight": model.radiation_weight,
    }


def _inside_region(latitude: float, longitude: float, region: Dict[str, Any]) -> bool:
    longitude = longitude % 360.0
    return (
        region["south"] <= latitude <= region["north"]
        and region["west"] <= longitude <= region["east"]
    )


def _coordinate_to_index(
    coordinate: tuple[float, float],
    region: Dict[str, Any],
    rows: int,
    cols: int,
) -> tuple[int, int]:
    latitude, longitude = coordinate
    longitude = longitude % 360.0
    row = int((region["north"] - latitude) * rows / (region["north"] - region["south"]))
    col = int((longitude - region["west"]) * cols / (region["east"] - region["west"]))
    return min(rows - 1, max(0, row)), min(cols - 1, max(0, col))


def _index_to_coordinates(
    cell: tuple[int, int], region: Dict[str, Any], grid: Any
) -> Dict[str, float]:
    row, col = cell
    latitude = region["north"] - (row + 0.5) * (
        region["north"] - region["south"]
    ) / grid.rows
    longitude = region["west"] + (col + 0.5) * (
        region["east"] - region["west"]
    ) / grid.cols
    return {"latitude": round(latitude, 6), "longitude": round(longitude, 6)}
