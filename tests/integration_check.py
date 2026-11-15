"""Comprobación de integración contra un backend EN EJECUCIÓN (solo biblioteca estándar).

Dos modos, según cómo se inició el backend:

  Modo sintético (predeterminado):
      uvicorn app.main:app --host 127.0.0.1 --port 8000
      python3 tests/integration_check.py

  Modo MOLA (topografía real, región predeterminada Valles Marineris):
      MARS_DATA_SOURCE=mola uvicorn app.main:app --host 127.0.0.1 --port 8000
      python3 tests/integration_check.py --mola

  Modo Gale (MOLA con capa de radiación MODELADA y alerta solar):
      MARS_DATA_SOURCE=mola MARS_MOLA_REGION=gale uvicorn app.main:app --host 127.0.0.1 --port 8000
      python3 tests/integration_check.py --gale

Opciones (en cualquier orden):
  --mola          comprueba el modo MOLA en lugar del sintético
  --gale          comprueba MOLA en la región Gale (implica --mola): procedencia,
                  capa de radiación MODELADA y POST /routes/shelter
  --api URL       URL de la API         (por defecto http://127.0.0.1:8000)
  --front URL     URL del frontend      (por defecto http://127.0.0.1:5500)
  --no-front      omite la comprobación del servidor del frontend

Compatibilidad: también se aceptan las URL como argumentos posicionales
(API primero y frontend después), como en la versión anterior.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("urls", nargs="*", help="URL de la API y, opcionalmente, del frontend")
parser.add_argument("--mola", action="store_true", help="comprueba el modo MOLA")
parser.add_argument("--gale", action="store_true", help="comprueba la región Gale (implica --mola)")
parser.add_argument("--api", default=None)
parser.add_argument("--front", default=None)
parser.add_argument("--no-front", action="store_true")
args = parser.parse_args()
if args.gale:
    args.mola = True

API = args.api or (args.urls[0] if len(args.urls) > 0 else "http://127.0.0.1:8000")
FRONT = args.front or (args.urls[1] if len(args.urls) > 1 else "http://127.0.0.1:5500")
results = []


def call(method, path, body=None, origin=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read()), resp.headers
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read()), err.headers


def check(name, condition, detail=""):
    results.append(bool(condition))
    print(("[OK]    " if condition else "[FALLO] ") + name + (f"  -> {detail}" if detail and not condition else ""))


def pt(row, col):
    return {"row": row, "col": col}


SUMMARY_FIELDS = {"steps", "distance_m", "total_cost", "max_slope_deg",
                  "mean_risk", "max_risk", "nodes_expanded"}
ROUTE_FIELDS = {"status", "data_source", "is_simulated", "disclaimer", "origin",
                "destination", "allow_diagonal", "path", "summary"}

expected_source = "mola" if args.mola else "synthetic"
mode_name = "GALE (MOLA)" if args.gale else expected_source.upper()
print(f"Modo comprobado: {mode_name}  |  API: {API}\n")

# Etiquetas de procedencia que el contrato fija para todas las regiones MOLA.
MOLA_PROVENANCE = {"elevation_m": "MEDIDO", "slope_deg": "DERIVADO", "risk": "DERIVADO",
                   "blocked": "ÍNDICE DEL PROYECTO", "total_cost": "ÍNDICE DEL PROYECTO"}
GALE_PROVENANCE = {"sky_view_factor": "DERIVADO", "radiation_modeled": "MODELADO"}

# ---------------------------------------------------------------- health
status, body, headers = call("GET", "/api/v1/health", origin=FRONT)
check("GET /health devuelve 200 y status ok", status == 200 and body.get("status") == "ok", body)
check(f"/health declara data_source = {expected_source}", body.get("data_source") == expected_source, body)
check("CORS permite el origen del frontend",
      headers.get("Access-Control-Allow-Origin") == FRONT, dict(headers))

# ------------------------------------------------------------------- map
status, map_body, _ = call("GET", "/api/v1/map")
check("GET /map devuelve 200", status == 200, map_body)
grid = map_body.get("grid", {})
cells = map_body.get("cells", [])
check("El número de celdas coincide con rows x cols",
      len(cells) == grid.get("rows", 0) * grid.get("cols", -1) > 0, grid)
check(f"/map declara data_source = {expected_source}", map_body.get("data_source") == expected_source)
by_pos = {(c["row"], c["col"]): c for c in cells}
free = [pos for pos, c in sorted(by_pos.items()) if not c["blocked"]]
blocked = [pos for pos, c in sorted(by_pos.items()) if c["blocked"]]

if args.mola:
    check("MOLA: is_simulated es false (topografía real)", map_body.get("is_simulated") is False)
    # Desde F4, MOLA publica un proxy de pendiente (no un modelo de peligros).
    check("MOLA: risk_available es true con el proxy min(slope_deg / 20, 1)",
          map_body.get("risk_available") is True
          and map_body.get("risk_model", {}).get("method") == "min(slope_deg / 20, 1)",
          map_body.get("risk_model"))
    check("MOLA: la región declara sus límites geográficos",
          set(map_body.get("region", {})) >= {"south", "north", "west", "east"}, map_body.get("region"))
    check("MOLA: cada celda trae latitude, longitude y valid",
          all({"latitude", "longitude", "valid"} <= set(c) for c in cells))
    check("MOLA: el disclaimer aclara que no es una recomendación de seguridad",
          "seguridad" in map_body.get("disclaimer", ""))
    provenance = map_body.get("provenance") or {}
    check("MOLA: provenance trae la etiqueta del contrato para cada capa",
          all(provenance.get(k, {}).get("label") == v for k, v in MOLA_PROVENANCE.items()),
          {k: provenance.get(k, {}).get("label") for k in MOLA_PROVENANCE})
    check("MOLA: cada entrada de provenance trae label, source e in_cost",
          bool(provenance) and all({"label", "source", "in_cost"} <= set(v) for v in provenance.values()))
    if args.gale:
        check("Gale: radiation_available es true y radiation_model se etiqueta MODELADO",
              map_body.get("radiation_available") is True
              and map_body.get("radiation_model", {}).get("label") == "MODELADO")
        check("Gale: provenance etiqueta sky_view_factor DERIVADO y radiation_modeled MODELADO",
              all(provenance.get(k, {}).get("label") == v for k, v in GALE_PROVENANCE.items()),
              {k: provenance.get(k) for k in GALE_PROVENANCE})
        rad = [c.get("radiation_modeled") for c in cells if c.get("valid")]
        check("Gale: cada celda válida trae radiation_modeled y sky_view_factor entre 0 y 1",
              bool(rad) and all(isinstance(v, (int, float)) and 0 <= v <= 1 for v in rad)
              and all(0 <= c.get("sky_view_factor", -1) <= 1 for c in cells if c.get("valid")))
    else:
        check("MOLA sin --gale: la región no trae capa de radiación (¿backend en Gale? usa --gale)",
              "radiation_available" not in map_body and "sky_view_factor" not in provenance)
else:
    check("Sintético: el mapa tiene 140 celdas (10 x 14)", len(cells) == 140)
    check("Sintético: is_simulated es true", map_body.get("is_simulated") is True)
    check("Sintético: /map no publica provenance ni capa de radiación",
          "provenance" not in map_body and "radiation_available" not in map_body)

# ----------------------------------------------------------------- rutas
# Origen y destino: primeras y últimas celdas libres de la misma fila central, o un par fijo
# conocido en el modo sintético (el mismo de la documentación).
if args.mola:
    rows = grid.get("rows", 0)
    mid = rows // 2
    row_free = [pos for pos in free if pos[0] == mid]
    origin, destination = (row_free[0], row_free[-1]) if len(row_free) >= 2 else (free[0], free[-1])
else:
    origin, destination = (2, 1), (2, 12)

status, route, _ = call("POST", "/api/v1/routes", {"origin": pt(*origin), "destination": pt(*destination)})
check(f"POST /routes {origin}->{destination} devuelve 200", status == 200, route)
check("La respuesta de ruta tiene exactamente los campos del contrato", set(route) == ROUTE_FIELDS, set(route))
check("La ruta empieza en el origen y termina en el destino",
      route.get("path", [{}])[0] == pt(*origin) and route.get("path", [{}])[-1] == pt(*destination))
check("summary contiene todos los campos", set(route.get("summary", {})) == SUMMARY_FIELDS)
check("Ninguna celda de la ruta está bloqueada",
      all(not by_pos[(p["row"], p["col"])]["blocked"] for p in route.get("path", [])))
check(f"La ruta declara data_source = {expected_source}", route.get("data_source") == expected_source)

# ------------------------------------------------------- pesos por solicitud
DEFAULT_WEIGHTS = {"slope_weight": 0.05, "risk_weight": 2.0, "radiation_weight": 0.0}
status, weighted, _ = call("POST", "/api/v1/routes", {"origin": pt(*origin), "destination": pt(*destination),
                                                      "slope_weight": 0.05, "radiation_weight": 0})
check("Ruta con los pesos por defecto: 200 y cost_weights aplicados",
      status == 200 and weighted.get("cost_weights") == DEFAULT_WEIGHTS, weighted.get("cost_weights", weighted))
check("Pesos por defecto explícitos: mismo camino y mismo costo que sin pesos",
      weighted.get("path") == route.get("path")
      and weighted.get("summary", {}).get("total_cost") == route.get("summary", {}).get("total_cost"))
check("Sin pesos en la solicitud no aparece cost_weights", "cost_weights" not in route)
status, err, _ = call("POST", "/api/v1/routes", {"origin": pt(*origin), "destination": pt(*destination),
                                                 "slope_weight": 101})
check("Peso fuera de 0–100 -> 422 VALIDATION_ERROR",
      status == 422 and err["error"]["code"] == "VALIDATION_ERROR", err)
if args.gale:
    status, rad_route, _ = call("POST", "/api/v1/routes", {"origin": pt(*origin), "destination": pt(*destination),
                                                           "radiation_weight": 5})
    check("Gale: radiation_weight = 5 encarece la ruta respecto a 0",
          status == 200 and rad_route["summary"]["total_cost"] > route["summary"]["total_cost"]
          and rad_route.get("cost_weights", {}).get("radiation_weight") == 5,
          (rad_route.get("summary"), route.get("summary")))

# --------------------------------------------------------- alerta solar
if args.gale:
    def is_candidate(c):
        return (c.get("valid") and not c["blocked"] and c["slope_deg"] <= 10
                and c.get("sky_view_factor", 1) <= 0.90)

    # Origen libre que NO cumple el criterio, para que la ruta tenga pasos.
    non_candidates = [pos for pos in free if not is_candidate(by_pos[pos])]
    shelter_origin = next((pos for pos in non_candidates if pos[0] == origin[0]), non_candidates[0])
    status, shelter, _ = call("POST", "/api/v1/routes/shelter", {"origin": pt(*shelter_origin)})
    info = shelter.get("shelter", {})
    check(f"Gale: POST /routes/shelter desde {shelter_origin} devuelve 200", status == 200, shelter)
    check("Gale: shelter usa el término «zona candidata de espera» y la etiqueta ÍNDICE DEL PROYECTO",
          info.get("term") == "zona candidata de espera" and info.get("label") == "ÍNDICE DEL PROYECTO", info)
    check("Gale: shelter.distance_km coincide con summary.distance_m / 1000",
          abs(info.get("distance_km", -1) - shelter.get("summary", {}).get("distance_m", 0) / 1000) < 0.001)
    dest = shelter.get("destination", {})
    dest_cell = by_pos.get((dest.get("row"), dest.get("col")), {})
    check("Gale: la ruta empieza en el origen y la zona elegida cumple el criterio",
          shelter.get("path", [{}])[0] == pt(*shelter_origin) and is_candidate(dest_cell)
          and info.get("destination_slope_deg") == dest_cell.get("slope_deg"), dest_cell)
    check("Gale: la nota declara planificación educativa",
          "educativa" in info.get("note", ""), info.get("note"))
    status, err, _ = call("POST", "/api/v1/routes/shelter", {"origin": pt(*shelter_origin), "max_distance_km": 0.001})
    check("Gale: max_distance_km diminuto -> 404 NO_SHELTER con el límite en details",
          status == 404 and err["error"]["code"] == "NO_SHELTER"
          and err["error"]["details"].get("max_distance_km") == 0.001, err)
    status, err, _ = call("POST", "/api/v1/routes/shelter", {"origin": {"latitude": 10.0, "longitude": 20.0}})
    check("Gale: origen fuera de la región -> 400 SHELTER_LAYER_UNAVAILABLE (outside_detail_region)",
          status == 400 and err["error"]["code"] == "SHELTER_LAYER_UNAVAILABLE"
          and err["error"]["details"].get("reason") == "outside_detail_region", err)
else:
    status, err, _ = call("POST", "/api/v1/routes/shelter", {"origin": pt(*free[0])})
    check("Sin capa de cielo visible: /routes/shelter -> 400 SHELTER_LAYER_UNAVAILABLE (no_sky_view_layer)",
          status == 400 and err["error"]["code"] == "SHELTER_LAYER_UNAVAILABLE"
          and err["error"]["details"].get("reason") == "no_sky_view_layer", err)

# --------------------------------------------------------------- errores
if blocked:
    status, err, _ = call("POST", "/api/v1/routes", {"origin": pt(*blocked[0]), "destination": pt(*free[0])})
    check("Celda bloqueada -> 400 CELL_BLOCKED", status == 400 and err["error"]["code"] == "CELL_BLOCKED", err)
else:
    check("Hay al menos una celda bloqueada para probar CELL_BLOCKED", False, "ninguna celda bloqueada")

status, err, _ = call("POST", "/api/v1/routes", {"origin": pt(-1, 0), "destination": pt(*free[0])})
check("Fuera de la cuadrícula -> 400 OUT_OF_BOUNDS", status == 400 and err["error"]["code"] == "OUT_OF_BOUNDS", err)

if not args.mola:
    status, err, _ = call("POST", "/api/v1/routes", {"origin": pt(2, 1), "destination": pt(8, 11)})
    check("Destino inalcanzable -> 404 NO_ROUTE", status == 404 and err["error"]["code"] == "NO_ROUTE", err)

status, err, _ = call("POST", "/api/v1/routes", {"origin": pt(*free[0])})
check("Cuerpo incompleto -> 422 VALIDATION_ERROR", status == 422 and err["error"]["code"] == "VALIDATION_ERROR", err)

# -------------------------------------------------------------- frontend
if not args.no_front:
    try:
        with urllib.request.urlopen(FRONT + "/index.html", timeout=5) as resp:
            html = resp.read().decode("utf-8")
        check("El frontend responde y enlaza js/app.js", "js/app.js" in html)
        check("El frontend incluye las tarjetas de pesos y de alerta solar",
              'id="weights-card"' in html and 'id="shelter-card"' in html)
    except OSError as exc:
        check("El frontend responde (¿está iniciado el servidor en %s?)" % FRONT, False, exc)

passed = sum(results)
print(f"\nResultado: {passed}/{len(results)} comprobaciones correctas.")
sys.exit(0 if passed == len(results) else 1)
