"""Modo «alerta solar»: ruta a la zona candidata de espera más cercana por costo.

Zona candidata de espera (criterio del proyecto, configurable por solicitud):
celda válida y libre con slope_deg <= max_slope_deg y
sky_view_factor <= max_sky_view_factor.

* 10° es la mediana de pendiente de las celdas libres de Gale (10,05°): la zona
  está en la mitad más llana y su proxy de riesgo topográfico es <= 0,5.
* 0,90 es aproximadamente el percentil 25 de sky_view_factor en las celdas libres
  de Gale (0,895). Por la correlación de -0,90 entre cielo visible y pendiente,
  umbrales más estrictos dejan sin candidatas (con 0,85 y 10° no queda ninguna).

El sky_view_factor solo ELIGE la zona; no penaliza el costo de la ruta, porque
repite en gran parte la pendiente (que ya entra al costo) y sería un doble castigo.
El resultado es una ayuda de planificación educativa, no una protección garantizada.
"""

from typing import Any, Dict

from algorithms.astar import (
    BlockedCellError,
    Cell,
    GridCell,
    InvalidCellError,
    NoTargetReachableError,
    find_nearest_target,
)

from app.errors import ApiError
from app.models.schemas import ShelterRequest
from app.services.map_service import get_active_dataset
from app.services.route_service import (
    _coordinate_to_index,
    _index_to_coordinates,
    _inside_region,
    request_cost_model,
)

DEFAULT_SHELTER_MAX_SLOPE_DEG = 10.0
DEFAULT_SHELTER_MAX_SKY_VIEW_FACTOR = 0.90

SKY_VIEW_FACTOR_ROLE = (
    "sky_view_factor (DERIVADO del DEM) solo se usa para elegir la zona candidata; "
    "no entra al costo de la ruta, porque repite en gran parte la pendiente "
    "(correlación -0,90 en Gale) y se castigaría dos veces."
)
SHELTER_NOTE = (
    "Planificación educativa: es la zona candidata de espera más cercana por costo "
    "según el criterio declarado. Según el modelo, el relieve tapa una parte del cielo, "
    "pero el índice no incluye la atenuación atmosférica y exagera el blindaje del "
    "relieve; la diferencia modelada con una celda típica es pequeña. No es una "
    "protección garantizada ni una recomendación operacional."
)


def compute_shelter_route(request: ShelterRequest) -> Dict[str, Any]:
    dataset = get_active_dataset()
    grid = dataset.grid
    if not any(
        grid.cell(r, c).sky_view_factor is not None
        for r in range(grid.rows) for c in range(grid.cols)
    ):
        raise ApiError(
            400,
            "SHELTER_LAYER_UNAVAILABLE",
            "La fuente activa no trae la capa sky_view_factor; el modo alerta solar "
            "solo está disponible en regiones con esa capa (hoy, Gale).",
            {"reason": "no_sky_view_layer", "data_source": dataset.data_source},
        )

    region: Dict[str, Any] | None = dataset.payload.get("region")
    coordinate_request = request.origin.latitude is not None
    if coordinate_request:
        latitude = float(request.origin.latitude)  # type: ignore[arg-type]
        longitude = float(request.origin.longitude)  # type: ignore[arg-type]
        if region is None or not _inside_region(latitude, longitude, region):
            raise ApiError(
                400,
                "SHELTER_LAYER_UNAVAILABLE",
                "El origen está fuera de la región de detalle; la malla global no trae "
                "la capa sky_view_factor.",
                {"reason": "outside_detail_region", "data_source": dataset.data_source},
            )
        origin = _coordinate_to_index((latitude, longitude), region, grid.rows, grid.cols)
    else:
        origin = (request.origin.row, request.origin.col)  # type: ignore[assignment]

    max_slope = (
        DEFAULT_SHELTER_MAX_SLOPE_DEG if request.max_slope_deg is None
        else float(request.max_slope_deg)
    )
    max_svf = (
        DEFAULT_SHELTER_MAX_SKY_VIEW_FACTOR if request.max_sky_view_factor is None
        else float(request.max_sky_view_factor)
    )

    def is_candidate(_: Cell, cell: GridCell) -> bool:
        return (
            not cell.blocked
            and cell.sky_view_factor is not None
            and cell.slope_deg <= max_slope
            and cell.sky_view_factor <= max_svf
        )

    candidates = sum(
        1 for r in range(grid.rows) for c in range(grid.cols)
        if is_candidate((r, c), grid.cell(r, c))
    )
    max_distance_km = request.max_distance_km
    criterion = (
        f"celda libre con slope_deg <= {max_slope:g} y sky_view_factor <= {max_svf:g}"
    )
    if max_distance_km is not None:
        criterion += (
            f"; ruta de menor costo hasta ella de {max_distance_km:g} km como máximo"
        )
    max_length = (
        None if max_distance_km is None
        else max_distance_km * 1000.0 / grid.cell_size_m
    )
    cost_model, applied_weights = request_cost_model(request, dataset.cost_model)

    try:
        result = find_nearest_target(
            grid, origin, is_candidate, cost_model=cost_model,
            allow_diagonal=request.allow_diagonal, max_length=max_length,
        )
    except InvalidCellError as exc:
        raise ApiError(
            400,
            "OUT_OF_BOUNDS",
            f"La celda de origen está fuera de la cuadrícula "
            f"({grid.rows} filas x {grid.cols} columnas).",
            {"field": "origin", "row": origin[0], "col": origin[1],
             "rows": grid.rows, "cols": grid.cols},
        ) from exc
    except BlockedCellError as exc:
        raise ApiError(
            400,
            "CELL_BLOCKED",
            f"La celda de origen ({exc.cell[0]}, {exc.cell[1]}) está bloqueada.",
            {"field": "origin", "row": exc.cell[0], "col": exc.cell[1]},
        ) from exc
    except NoTargetReachableError as exc:
        details: Dict[str, Any] = {
            "origin": {"row": origin[0], "col": origin[1]}, "criterion": criterion,
            "candidates_count": candidates, "nodes_expanded": exc.nodes_expanded,
        }
        if max_distance_km is not None:
            details["max_distance_km"] = max_distance_km
        raise ApiError(
            404,
            "NO_SHELTER",
            "No hay ninguna zona candidata de espera alcanzable con el criterio indicado.",
            details,
        ) from exc

    goal = result.path[-1]
    goal_cell = grid.cell(*goal)
    origin_point: Dict[str, Any] = {"row": origin[0], "col": origin[1]}
    destination_point: Dict[str, Any] = {"row": goal[0], "col": goal[1]}
    path_points = [{"row": r, "col": c} for r, c in result.path]
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
        "shelter": {
            "criterion": criterion,
            "max_slope_deg": max_slope,
            "max_sky_view_factor": max_svf,
            "candidates_count": candidates,
            "distance_km": round(result.distance_m / 1000.0, 3),
            "max_distance_km": max_distance_km,
            "destination_slope_deg": goal_cell.slope_deg,
            "destination_sky_view_factor": goal_cell.sky_view_factor,
            "sky_view_factor_role": SKY_VIEW_FACTOR_ROLE,
            "note": SHELTER_NOTE,
        },
    }
    if applied_weights is not None:
        response["cost_weights"] = applied_weights
    if coordinate_request and region is not None:
        response["resolution"] = "mola-detail"
        origin_point.update(_index_to_coordinates(origin, region, grid))
        destination_point.update(_index_to_coordinates(goal, region, grid))
        for point, cell in zip(path_points, result.path):
            point.update(_index_to_coordinates(cell, region, grid))
    return response
