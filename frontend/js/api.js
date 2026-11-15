/*
 * Cliente HTTP/JSON para la API FastAPI de Ares Pathfinder.
 * Solo comunica; NO calcula rutas (eso lo hace el backend con A*).
 */
(function () {
  "use strict";

  var cfg = window.MarsConfig;

  function ApiError(message, info) {
    this.name = "ApiError";
    this.message = message;
    this.code = (info && info.code) || "UNKNOWN";
    this.status = (info && info.status) || 0;
    this.details = (info && info.details) || {};
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  function request(path, options) {
    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, cfg.REQUEST_TIMEOUT_MS);
    var url = cfg.API_BASE_URL + cfg.API_PREFIX + path;
    var init = Object.assign({ signal: controller.signal }, options || {});

    return fetch(url, init)
      .catch(function (err) {
        if (err && err.name === "AbortError") {
          throw new ApiError("La API tardó demasiado en responder (más de " +
            (cfg.REQUEST_TIMEOUT_MS / 1000) + " s).", { code: "TIMEOUT" });
        }
        throw new ApiError("No se pudo conectar con la API en " + cfg.API_BASE_URL +
          ". Comprueba que el backend esté en ejecución y que CORS permita este origen.",
          { code: "NETWORK_ERROR" });
      })
      .then(function (response) {
        return response.text().then(function (text) {
          var body = null;
          try { body = text ? JSON.parse(text) : null; } catch (e) { body = null; }

          if (!response.ok) {
            var err = body && body.error;
            throw new ApiError(
              (err && err.message) || ("Error HTTP " + response.status),
              { code: (err && err.code) || "HTTP_ERROR", status: response.status,
                details: (err && err.details) || {} }
            );
          }
          if (body === null) {
            throw new ApiError("La API devolvió una respuesta que no es JSON.",
              { code: "INVALID_RESPONSE", status: response.status });
          }
          return body;
        });
      })
      .finally(function () { clearTimeout(timer); });
  }

  /** Un punto se envía por coordenadas (MOLA) o por índices, nunca ambos. */
  function routeLocation(point) {
    return Number.isFinite(point.latitude) && Number.isFinite(point.longitude)
      ? { latitude: point.latitude, longitude: point.longitude }
      : { row: point.row, col: point.col };
  }

  /** Añade los pesos opcionales solo si se pasan (sin ellos el cuerpo no cambia). */
  function addWeights(body, weights) {
    if (weights) {
      body.slope_weight = weights.slope_weight;
      body.radiation_weight = weights.radiation_weight;
    }
    return body;
  }

  function postJson(path, body) {
    return request(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
  }

  window.MarsApi = {
    ApiError: ApiError,

    getHealth: function () {
      return request("/health");
    },

    getMap: function () {
      return request("/map");
    },

    /**
     * Acepta puntos con { row, col } o con { latitude, longitude }.
     * `weights` es opcional: { slope_weight, radiation_weight } (0–100).
     */
    postRoute: function (origin, destination, allowDiagonal, weights) {
      return postJson("/routes", addWeights({
        origin: routeLocation(origin),
        destination: routeLocation(destination),
        allow_diagonal: allowDiagonal
      }, weights));
    },

    /**
     * Modo «alerta solar»: ruta a la zona candidata de espera más cercana por
     * costo. `maxDistanceKm` solo se envía si es un número finito mayor que 0.
     */
    postShelter: function (origin, allowDiagonal, weights, maxDistanceKm) {
      var body = addWeights({
        origin: routeLocation(origin),
        allow_diagonal: allowDiagonal
      }, weights);
      if (Number.isFinite(maxDistanceKm) && maxDistanceKm > 0) {
        body.max_distance_km = maxDistanceKm;
      }
      return postJson("/routes/shelter", body);
    }
  };
})();
