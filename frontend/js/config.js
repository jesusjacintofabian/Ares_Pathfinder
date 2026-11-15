/*
 * Configuración del frontend de Ares Pathfinder.
 * Para cambiar la URL de la API edita API_BASE_URL, o bien abre la página con
 * ?api=http://127.0.0.1:8000 (útil para pruebas sin editar archivos).
 */
(function () {
  "use strict";

  var DEFAULT_API = "http://127.0.0.1:8000";
  var apiBase = DEFAULT_API;
  var perf = false;

  try {
    var fromQuery = new URLSearchParams(window.location.search).get("api");
    if (fromQuery && /^https?:\/\/[^\s]+$/i.test(fromQuery)) {
      apiBase = fromQuery.replace(/\/+$/, "");
    }
    // ?perf=1 mide cuánto tarda en construirse el mapa (solo diagnóstico).
    perf = new URLSearchParams(window.location.search).get("perf") === "1";
  } catch (e) {
    /* Si falla la lectura de la URL se usa el valor por defecto. */
  }

  window.MarsConfig = {
    API_BASE_URL: apiBase,
    API_PREFIX: "/api/v1",
    REQUEST_TIMEOUT_MS: 10000,
    PERF: perf
  };
})();
