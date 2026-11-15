"""Endpoints REST de la versión 1 de la API."""

from fastapi import APIRouter

from app.models.schemas import (
    ErrorResponse,
    HealthResponse,
    MapResponse,
    RouteRequest,
    RouteResponse,
    ShelterRequest,
    ShelterRouteResponse,
)
from app.services import map_service, route_service, shelter_service

router = APIRouter()

API_VERSION = "v1"
APP_VERSION = "1.0.0"


@router.get("/health", response_model=HealthResponse, summary="Estado del servicio")
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="mars-explorer-lab-api",
        version=APP_VERSION,
        api_version=API_VERSION,
        data_source=map_service.get_configured_data_source(),
    )


@router.get(
    "/map",
    response_model=MapResponse,
    response_model_exclude_none=True,
    summary="Datos de la zona de estudio",
)
def get_map() -> MapResponse:
    return MapResponse(**map_service.build_map_payload())


@router.post(
    "/routes",
    response_model=RouteResponse,
    response_model_exclude_none=True,
    summary="Calcula una ruta con A*",
    responses={
        400: {"model": ErrorResponse, "description": "Celda fuera de la cuadrícula o bloqueada."},
        404: {"model": ErrorResponse, "description": "No existe ruta."},
        422: {"model": ErrorResponse, "description": "Solicitud con formato inválido."},
    },
)
def post_route(request: RouteRequest) -> RouteResponse:
    return RouteResponse(**route_service.compute_route(request))


@router.post(
    "/routes/shelter",
    response_model=ShelterRouteResponse,
    response_model_exclude_none=True,
    summary="Modo alerta solar: ruta a la zona candidata de espera más cercana",
    responses={
        400: {"model": ErrorResponse,
              "description": "Origen fuera de la cuadrícula, bloqueado o sin capa sky_view_factor."},
        404: {"model": ErrorResponse, "description": "Ninguna zona candidata alcanzable."},
        422: {"model": ErrorResponse, "description": "Solicitud con formato inválido."},
    },
)
def post_shelter_route(request: ShelterRequest) -> ShelterRouteResponse:
    return ShelterRouteResponse(**shelter_service.compute_shelter_route(request))
