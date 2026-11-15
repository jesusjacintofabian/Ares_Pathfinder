/*
 * Respuestas de la API reducidas para las pruebas. Los textos y la forma de
 * provenance, cost_weights y shelter se copiaron de respuestas reales del
 * backend (Gale) el 2026-11-14; las celdas son una cuadrícula diminuta.
 */
"use strict";

const COST_MODEL = {
  formula: "costo_paso = factor_longitud * (1 + slope_weight * slope_deg + risk_weight * risk + radiation_weight * radiation_modeled)",
  slope_weight: 0.05,
  risk_weight: 2.0,
  radiation_weight: 0.0,
  diagonal_length_factor: 1.4142,
  cost_unit: "cost_units"
};

const COORDS = {
  type: "grid_index", index_base: 0, row_axis: "down", col_axis: "right", description: "x"
};

function syntheticMap() {
  const cells = [];
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 4; col += 1) {
      cells.push({
        row, col, elevation_m: 1000 + row * 10 + col, slope_deg: 5 + col,
        risk: 0.1 * col, blocked: row === 1 && col === 2
      });
    }
  }
  return {
    name: "Zona sintética Mars Explorer Lab",
    data_source: "synthetic",
    is_simulated: true,
    disclaimer: "DATOS SIMULADOS: prueba.",
    grid: { rows: 3, cols: 4, cell_size_m: 100.0 },
    coordinate_system: COORDS,
    cost_model: COST_MODEL,
    risk_available: true,
    cells
  };
}

const BASE_PROVENANCE = {
  elevation_m: {
    label: "MEDIDO",
    source: "Mars MGS MOLA - MEX HRSC Blended DEM Global 200m v2 (USGS Astrogeology) (Fergason, Hare y Laura (2018))",
    in_cost: false,
    note: "Entra al costo solo a través de la pendiente derivada."
  },
  slope_deg: { label: "DERIVADO", source: "Calculada desde la elevación de la región.", in_cost: true },
  risk: {
    label: "DERIVADO", source: "Proxy topográfico min(slope_deg / 20, 1).", in_cost: true,
    note: "No es una probabilidad de peligro."
  },
  blocked: {
    label: "ÍNDICE DEL PROYECTO",
    source: "Regla del laboratorio: celda inválida o pendiente >= 30° (umbral demostrativo del procesado).",
    in_cost: false
  },
  total_cost: {
    label: "ÍNDICE DEL PROYECTO",
    source: "Combinación ponderada de las capas con in_cost = true (cost_model).",
    in_cost: false,
    note: "Es el resultado del costo: una puntuación de planificación educativa, no una probabilidad."
  }
};

/** Cuadrícula MOLA 3 × 3 con centros geográficos dentro de region. */
function molaMap(withRadiation, customRegion) {
  const region = customRegion || { south: -5.0, north: -4.7, west: 137.6, east: 137.9 };
  const step = (region.north - region.south) / 3;
  const lonStep = (region.east - region.west) / 3;
  const cells = [];
  for (let row = 0; row < 3; row += 1) {
    for (let col = 0; col < 3; col += 1) {
      const cell = {
        row, col,
        latitude: region.north - (row + 0.5) * step,
        longitude: region.west + (col + 0.5) * lonStep,
        elevation_m: -4400 + row * 50, slope_deg: 4 + row + col,
        risk: (4 + row + col) / 20, blocked: row === 2 && col === 2, valid: true
      };
      if (withRadiation) {
        cell.sky_view_factor = 0.75 + 0.03 * (row * 3 + col);
        cell.radiation_modeled = cell.sky_view_factor;
      }
      cells.push(cell);
    }
  }
  const provenance = Object.assign({}, BASE_PROVENANCE);
  const map = {
    name: withRadiation ? "Gale — prueba" : "Valles Marineris — prueba",
    data_source: "mola",
    is_simulated: false,
    disclaimer: "MOLA de prueba. No es una recomendación de seguridad.",
    grid: { rows: 3, cols: 3, cell_size_m: 600 },
    coordinate_system: COORDS,
    cost_model: COST_MODEL,
    risk_available: true,
    region,
    cells,
    global_grid: {
      rows: 2, cols: 2, cell_size_m: 59000,
      region: { south: -90, north: 90, west: 0, east: 360 },
      cells: [
        { elevation_m: 0, slope_deg: 1, risk: 0.05, blocked: false, valid: true },
        { elevation_m: 0, slope_deg: 1, risk: 0.05, blocked: false, valid: true },
        { elevation_m: 0, slope_deg: 1, risk: 0.05, blocked: false, valid: true },
        { elevation_m: 0, slope_deg: 1, risk: 0.05, blocked: false, valid: true }
      ]
    },
    provenance
  };
  if (withRadiation) {
    map.radiation_available = true;
    map.radiation_model = { label: "MODELADO", index_formula: "radiation_modeled = sky_view_factor" };
    provenance.sky_view_factor = {
      label: "DERIVADO", source: "Fracción de cielo visible calculada desde el DEM (data/sky_view.py).",
      in_cost: false
    };
    provenance.radiation_modeled = {
      label: "MODELADO",
      source: "Índice relativo desde sky_view_factor con supuestos declarados en radiation_model; ancla RAD (Hassler et al., 2014).",
      in_cost: true,
      note: "radiation_weight vale 0 por defecto; ajustable por solicitud."
    };
  }
  return map;
}

function point(map, row, col) {
  const c = map.cells.find((x) => x.row === row && x.col === col);
  return c.latitude === undefined
    ? { row, col }
    : { row, col, latitude: c.latitude, longitude: c.longitude };
}

function routeResponse(map, body, extra) {
  const origin = point(map, 0, 0);
  const destination = point(map, 0, 2);
  return Object.assign({
    status: "ok",
    data_source: map.data_source,
    is_simulated: map.is_simulated,
    disclaimer: map.disclaimer,
    origin, destination,
    allow_diagonal: true,
    path: [origin, point(map, 0, 1), destination],
    summary: {
      steps: 2, distance_m: 1200, total_cost: 5.5, max_slope_deg: 6,
      mean_risk: 0.25, max_risk: 0.3, nodes_expanded: 4
    }
  }, map.data_source === "mola" ? { resolution: "mola-detail" } : {},
  body && (body.slope_weight !== undefined || body.radiation_weight !== undefined)
    ? {
      cost_weights: {
        slope_weight: body.slope_weight === undefined ? 0.05 : body.slope_weight,
        risk_weight: 2.0,
        radiation_weight: body.radiation_weight === undefined ? 0.0 : body.radiation_weight
      }
    }
    : {}, extra || {});
}

const SHELTER_NOTE =
  "Planificación educativa: es la zona candidata de espera más cercana por costo según el criterio declarado. " +
  "Según el modelo, el relieve tapa una parte del cielo, pero el índice no incluye la atenuación atmosférica y " +
  "exagera el blindaje del relieve; la diferencia modelada con una celda típica es pequeña. " +
  "No es una protección garantizada ni una recomendación operacional.";

function shelterResponse(map, body) {
  const route = routeResponse(map, body);
  const shelter = {
    term: "zona candidata de espera",
    label: "ÍNDICE DEL PROYECTO",
    criterion: "celda libre con slope_deg <= 10 y sky_view_factor <= 0.9",
    max_slope_deg: 10.0,
    max_sky_view_factor: 0.9,
    candidates_count: 64,
    distance_km: 1.2,
    destination_slope_deg: 6,
    destination_sky_view_factor: 0.81,
    sky_view_factor_role: "sky_view_factor (DERIVADO del DEM) solo se usa para elegir la zona candidata; no entra al costo de la ruta.",
    note: SHELTER_NOTE
  };
  if (body && body.max_distance_km !== undefined) { shelter.max_distance_km = body.max_distance_km; }
  route.shelter = shelter;
  return route;
}

function noShelterError(body) {
  const details = {
    origin: { row: 0, col: 0 },
    criterion: "celda libre con slope_deg <= 10 y sky_view_factor <= 0.9" +
      (body && body.max_distance_km !== undefined
        ? "; ruta de menor costo hasta ella de " + body.max_distance_km + " km como máximo"
        : ""),
    candidates_count: 64,
    nodes_expanded: 5585
  };
  if (body && body.max_distance_km !== undefined) { details.max_distance_km = body.max_distance_km; }
  return {
    error: {
      code: "NO_SHELTER",
      message: "No hay ninguna zona candidata de espera alcanzable con el criterio indicado.",
      details
    }
  };
}

const OUTSIDE_REGION_ERROR = {
  error: {
    code: "SHELTER_LAYER_UNAVAILABLE",
    message: "El origen está fuera de la región de detalle; la malla global no trae la capa sky_view_factor.",
    details: { reason: "outside_detail_region", data_source: "mola" }
  }
};

module.exports = {
  syntheticMap, molaMap, routeResponse, shelterResponse, noShelterError, OUTSIDE_REGION_ERROR
};
