/*
 * Lógica de la interfaz: selección de puntos, solicitud de ruta y mensajes.
 * NO implementa A*: el cálculo lo hace el backend (POST /api/v1/routes).
 */
(function () {
  "use strict";

  var state = {
    mapData: null,
    origin: null,        // { row, col } o null
    destination: null,
    mode: "origin",      // "origin" | "destination"
    loading: false,
    basemapErrorShown: false
  };

  var el = {};

  function $(id) { return document.getElementById(id); }

  function cacheElements() {
    [
      "status", "btn-retry", "zone-name", "mode-origin", "mode-dest", "origin-label",
      "dest-label", "opt-diagonal", "btn-route", "btn-clear", "results-card",
      "res-distance", "res-cost", "res-steps", "res-slope", "res-risk-mean",
      "res-risk-max", "res-nodes", "res-risk-text", "risk-mean-label", "risk-max-label",
      "elevation-legend", "slope-legend", "risk-legend", "disclaimer", "cell-info",
      "sim-banner", "risk-layer-label", "risk-layer-toggle", "elevation-layer-label",
      "slope-layer-label", "map-view-controls", "map-attribution", "btn-mars-global",
      "btn-mola-region", "place-names-label", "place-names-note", "place-names-toggle",
      "viking-layer-toggle", "weights-card", "slope-weight-range", "slope-weight-number",
      "radiation-weight-range", "radiation-weight-number", "weights-error", "weights-formula",
      "btn-weights-reset", "res-weights-label", "res-weights", "shelter-card", "shelter-max-km",
      "shelter-max-error", "btn-shelter", "shelter-empty", "shelter-result", "shelter-distance",
      "shelter-dest-slope", "shelter-dest-sky", "shelter-candidates", "shelter-label",
      "shelter-criterion", "shelter-role", "shelter-note"
    ].forEach(function (id) { el[id] = $(id); });
  }

  /* ---------------------------------------------------------- mensajes */
  function setStatus(type, message) {
    el.status.className = "status status-" + type;
    el.status.textContent = message;
  }

  function fmt(value, decimals) { return Number(value).toFixed(decimals); }

  function cellText(c) {
    if (Number.isFinite(c.latitude) && Number.isFinite(c.longitude) &&
        state.mapData && state.mapData.data_source === "mola") {
      return "lat " + fmt(c.latitude, 2) + "°, lon E " + fmt(c.longitude, 2) + "°";
    }
    return "fila " + c.row + ", col " + c.col;
  }

  /* ------------------------------------------------------------ estado */
  function updateButtons() {
    el["btn-route"].disabled = state.loading || !state.origin || !state.destination ||
      !state.mapData || weightsInvalid();
    el["btn-clear"].disabled = state.loading;
    el["btn-shelter"].disabled = state.loading || !state.origin || !weightsEnabled() ||
      weightsInvalid() || Number.isNaN(shelterMaxKm());
  }

  function setMode(mode) {
    state.mode = mode;
    el["mode-origin"].classList.toggle("active", mode === "origin");
    el["mode-dest"].classList.toggle("active", mode === "destination");
  }

  function refreshPoints() {
    el["origin-label"].textContent = state.origin ? cellText(state.origin) : "sin seleccionar";
    el["dest-label"].textContent = state.destination ? cellText(state.destination) : "sin seleccionar";
    MarsMap.setPin("origin", state.origin);
    MarsMap.setPin("dest", state.destination);
    updateButtons();
  }

  function clearResults() {
    MarsMap.clearRoute();
    el["results-card"].hidden = true;
    el["shelter-result"].hidden = true;
    el["shelter-empty"].hidden = true;
  }

  /* ------------------------------------------------------- interacción */
  function onCellClick(cell) {
    if (state.loading) { return; }
    if (cell.blocked) {
      setStatus("error", "La celda (" + cell.row + ", " + cell.col +
        ") está bloqueada (" + (state.mapData.is_simulated ? "dato simulado" : "pendiente MOLA") +
        "). Elige otra celda.");
      return;
    }
    clearResults();
    var point = {
      row: cell.row,
      col: cell.col,
      latitude: cell.latitude,
      longitude: cell.longitude
    };
    if (state.mode === "origin") {
      state.origin = point;
      setMode("destination");
      setStatus("info", "Origen: " + cellText(point) + ". Ahora elige el destino.");
    } else {
      state.destination = point;
      setStatus("info", "Destino: " + cellText(point) +
        (state.origin ? ". Pulsa «Calcular ruta»." : ". Falta elegir el origen."));
    }
    refreshPoints();
  }

  function onCellHover(cell) {
    var riskText = state.mapData && state.mapData.risk_available
      ? (state.mapData.data_source === "mola"
        ? (cell.valid === false
          ? "proxy de pendiente no disponible"
          : "proxy de riesgo topográfico " + fmt(cell.risk, 2))
        : "riesgo " + fmt(cell.risk, 2))
      : "riesgo no modelado";
    var shieldingText = Number.isFinite(cell.radiation_modeled)
      ? " · apantallamiento " + fmt(1 - cell.radiation_modeled, 3) + " (MODELADO)"
      : "";
    var location = !state.mapData || state.mapData.is_simulated
      ? ""
      : " · lat " + fmt(cell.latitude, 4) + "°, lon E " + fmt(cell.longitude, 4) + "°";
      el["cell-info"].textContent =
      "Celda (" + cell.row + ", " + cell.col + ") · elevación " + fmt(cell.elevation_m, 1) +
        " m · pendiente " + fmt(cell.slope_deg, 1) + "° · " + riskText +
        shieldingText +
        (cell.blocked ? " · BLOQUEADA" : "") +
        (state.mapData && state.mapData.is_simulated ? " (simulado)" : location);
  }

  function riskLabel(maxRisk) {
    // Solo presentación: clasifica el puntaje mostrado, no estima probabilidad.
    if (maxRisk < 0.3) { return "bajo"; }
    if (maxRisk < 0.6) { return "moderado"; }
    return "alto";
  }

  /* ------------------------------------------------------------- pesos */
  var DEFAULT_WEIGHTS = { slope_weight: 0.05, radiation_weight: 0 };
  var WEIGHT_FIELDS = [
    { key: "slope_weight", range: "slope-weight-range", number: "slope-weight-number",
      name: "pendiente" },
    { key: "radiation_weight", range: "radiation-weight-range", number: "radiation-weight-number",
      name: "radiación" }
  ];

  /** Los controles de pesos solo existen en regiones con capa de radiación (Gale). */
  function weightsEnabled() {
    return Boolean(state.mapData && state.mapData.radiation_available === true);
  }

  function parseWeight(text) {
    if (typeof text !== "string" || !/^\s*\d+(?:[.,]\d+)?\s*$/.test(text)) { return NaN; }
    var value = Number(text.trim().replace(",", "."));
    return Number.isFinite(value) && value >= 0 && value <= 100 ? value : NaN;
  }

  function weightsInvalid() {
    return weightsEnabled() && currentWeights() === null;
  }

  /**
   * Pesos para la solicitud, o `undefined` si la región no los usa (así el
   * cuerpo de POST /routes queda igual que antes). `null` si algún valor no es válido.
   */
  function currentWeights() {
    if (!weightsEnabled()) { return undefined; }
    var weights = {};
    for (var i = 0; i < WEIGHT_FIELDS.length; i += 1) {
      var value = parseWeight(el[WEIGHT_FIELDS[i].number].value);
      if (Number.isNaN(value)) { return null; }
      weights[WEIGHT_FIELDS[i].key] = value;
    }
    return weights;
  }

  function refreshWeightsError() {
    var bad = WEIGHT_FIELDS.filter(function (field) {
      return Number.isNaN(parseWeight(el[field.number].value));
    }).map(function (field) { return field.name; });
    el["weights-error"].hidden = bad.length === 0;
    el["weights-error"].textContent = bad.length
      ? "Peso de " + bad.join(" y ") + " no válido: escribe un número entre 0 y 100."
      : "";
  }

  function onWeightInput(field, source) {
    if (source === "range") {
      el[field.number].value = el[field.range].value;
    } else {
      var value = parseWeight(el[field.number].value);
      if (!Number.isNaN(value)) { el[field.range].value = String(value); }
    }
    refreshWeightsError();
    clearResults();
    updateButtons();
  }

  function resetWeights() {
    WEIGHT_FIELDS.forEach(function (field) {
      var value = String(DEFAULT_WEIGHTS[field.key]);
      el[field.range].value = value;
      el[field.number].value = value;
    });
    refreshWeightsError();
    clearResults();
    updateButtons();
  }

  function weightText(value) {
    return Number.isFinite(Number(value)) ? String(Number(value)).replace(".", ",") : "—";
  }

  function showResults(route) {
    var s = route.summary;
    el["res-distance"].textContent = fmt(s.distance_m, 1) + " m";
    el["res-cost"].textContent = fmt(s.total_cost, 2) + " unidades de costo";
    el["res-steps"].textContent = String(s.steps);
    el["res-slope"].textContent = fmt(s.max_slope_deg, 1) + "°";
    var riskAvailable = state.mapData && state.mapData.risk_available;
    el["res-risk-mean"].textContent = riskAvailable ? fmt(s.mean_risk, 2) : "No modelado";
    el["res-risk-max"].textContent = riskAvailable ? fmt(s.max_risk, 2) : "No modelado";
    el["res-nodes"].textContent = String(s.nodes_expanded);
    var w = route.cost_weights;
    var hasWeights = Boolean(w && typeof w === "object");
    el["res-weights-label"].hidden = !hasWeights;
    el["res-weights"].hidden = !hasWeights;
    el["res-weights"].textContent = hasWeights
      ? "pendiente " + weightText(w.slope_weight) + " · riesgo " + weightText(w.risk_weight) +
        " · radiación " + weightText(w.radiation_weight)
      : "—";
    el["res-risk-text"].textContent = riskAvailable
      ? "Nivel de riesgo máximo en la ruta: " + riskLabel(s.max_risk) +
        (state.mapData.data_source === "mola"
          ? " (proxy educativo: min(pendiente / 20°, 1); no estima peligros geológicos ni seguridad)."
          : " (valor simulado, no es un riesgo real de Marte).")
      : "Riesgo no modelado por esta fuente de datos; 0 no significa ausencia de peligros.";
    el["results-card"].hidden = false;
  }

  function requestRoute() {
    if (!state.origin || !state.destination || state.loading) { return; }
    var weights = currentWeights();
    if (weights === null) {
      refreshWeightsError();
      setStatus("error", "Revisa los pesos del costo antes de calcular la ruta.");
      return;
    }
    state.loading = true;
    updateButtons();
    clearResults();
    setStatus("loading", "Calculando ruta…");

    MarsApi.postRoute(state.origin, state.destination, el["opt-diagonal"].checked, weights)
      .then(function (route) {
        MarsMap.drawRoute(route.path);
        showResults(route);
        var sourceNote = state.mapData.is_simulated
          ? "datos simulados"
          : route.resolution === "mola-global-1deg"
            ? "MOLA global aproximada, celdas de ~59 km"
            : route.resolution === "mola-detail"
              ? "MOLA de detalle"
              : "topografía MOLA";
        setStatus("success", route.summary.steps === 0
          ? "Origen y destino coinciden: la ruta tiene 0 pasos."
          : "Ruta calculada: " + route.summary.steps + " pasos, " +
            fmt(route.summary.distance_m, 1) + " m (" +
            sourceNote + ").");
      })
      .catch(function (err) {
        var message = err.message || "Error desconocido.";
        setStatus("error", message + (err.code ? " [" + err.code + "]" : ""));
      })
      .finally(function () {
        state.loading = false;
        updateButtons();
      });
  }

  /* ------------------------------------------------------ alerta solar */
  function decimal(value, decimals) {
    return fmt(value, decimals).replace(".", ",");
  }

  /** km opcional: undefined si está vacío, NaN si no es un número > 0. */
  function shelterMaxKm() {
    var text = el["shelter-max-km"].value;
    if (text === "" || text === undefined) {
      // type=number devuelve "" también ante texto no numérico.
      return el["shelter-max-km"].validity && el["shelter-max-km"].validity.badInput ? NaN : undefined;
    }
    var value = Number(text);
    return Number.isFinite(value) && value > 0 ? value : NaN;
  }

  function refreshShelterMaxError() {
    var bad = Number.isNaN(shelterMaxKm());
    el["shelter-max-error"].hidden = !bad;
    el["shelter-max-error"].textContent = bad
      ? "La distancia máxima debe ser un número mayor que 0, o quedar vacía (sin límite)."
      : "";
  }

  function originInsideRegion() {
    var region = state.mapData && state.mapData.region;
    var o = state.origin;
    if (!region || !o || !Number.isFinite(o.latitude) || !Number.isFinite(o.longitude)) {
      return Boolean(o);
    }
    return o.latitude >= region.south && o.latitude <= region.north &&
      o.longitude >= region.west && o.longitude <= region.east;
  }

  function showShelterEmpty(message) {
    el["shelter-result"].hidden = true;
    el["shelter-empty"].textContent = message;
    el["shelter-empty"].hidden = false;
  }

  function noShelterMessage(details) {
    var d = details || {};
    var count = Number.isFinite(d.candidates_count) ? d.candidates_count : null;
    return "No hay ninguna zona candidata de espera que cumpla el criterio y sea alcanzable" +
      (Number.isFinite(d.max_distance_km)
        ? " con una ruta de menor costo de " + decimal(d.max_distance_km, 1) + " km o menos"
        : "") +
      " desde este origen." +
      (count !== null
        ? " En la región hay " + count + (count === 1 ? " celda" : " celdas") +
          " que cumplen el criterio, pero ninguna sirve con estas condiciones."
        : "") +
      " Es un resultado del modelo, no un fallo: prueba otro origen" +
      (Number.isFinite(d.max_distance_km) ? " o una distancia máxima mayor." : ".");
  }

  function showShelterResult(route) {
    var sh = route.shelter || {};
    el["shelter-empty"].hidden = true;
    el["shelter-distance"].textContent = Number.isFinite(sh.distance_km)
      ? decimal(sh.distance_km, 2) + " km" +
        (Number.isFinite(sh.max_distance_km) ? " (límite " + decimal(sh.max_distance_km, 1) + " km)" : "")
      : "—";
    el["shelter-dest-slope"].textContent = Number.isFinite(sh.destination_slope_deg)
      ? decimal(sh.destination_slope_deg, 1) + "°" : "—";
    el["shelter-dest-sky"].textContent = Number.isFinite(sh.destination_sky_view_factor)
      ? decimal(sh.destination_sky_view_factor, 2) : "—";
    el["shelter-candidates"].textContent = Number.isFinite(sh.candidates_count)
      ? String(sh.candidates_count) : "—";
    el["shelter-label"].textContent = sh.label || "ÍNDICE DEL PROYECTO";
    el["shelter-criterion"].textContent = sh.criterion || "—";
    el["shelter-role"].textContent = sh.sky_view_factor_role || "";
    el["shelter-note"].textContent = sh.note || "";
    el["shelter-result"].hidden = false;
  }

  function requestShelter() {
    if (state.loading) { return; }
    if (!state.origin) {
      setStatus("info", "Elige primero un origen en el mapa para buscar la zona candidata de espera.");
      return;
    }
    if (!originInsideRegion()) {
      clearResults();
      showShelterEmpty("El origen está fuera de la zona de detalle de " + state.mapData.name +
        ". La alerta solar solo funciona dentro de esa zona, que es la única con la capa de cielo visible.");
      setStatus("info", "Elige un origen dentro de la zona de detalle para la alerta solar.");
      return;
    }
    var weights = currentWeights();
    var maxKm = shelterMaxKm();
    if (weights === null || Number.isNaN(maxKm)) {
      refreshWeightsError();
      refreshShelterMaxError();
      setStatus("error", "Revisa los pesos y la distancia máxima antes de la alerta solar.");
      return;
    }
    state.loading = true;
    updateButtons();
    clearResults();
    setStatus("loading", "Buscando la zona candidata de espera más cercana por costo…");

    MarsApi.postShelter(state.origin, el["opt-diagonal"].checked, weights, maxKm)
      .then(function (route) {
        // La zona elegida sustituye al destino manual para no mostrar dos destinos.
        state.destination = null;
        refreshPoints();
        MarsMap.drawRoute(route.path, { variant: "shelter" });
        showResults(route);
        showShelterResult(route);
        var km = route.shelter && Number.isFinite(route.shelter.distance_km)
          ? decimal(route.shelter.distance_km, 2) + " km" : fmt(route.summary.distance_m, 1) + " m";
        setStatus("success", route.summary.steps === 0
          ? "El origen ya cumple el criterio de zona candidata de espera (0 pasos). Planificación educativa."
          : "Ruta a la zona candidata de espera: " + km + ", " + route.summary.steps +
            " pasos. Planificación educativa, no una recomendación operacional.");
      })
      .catch(function (err) {
        if (err.code === "NO_SHELTER") {
          var message = noShelterMessage(err.details);
          showShelterEmpty(message);
          setStatus("info", "Sin zona candidata de espera con estas condiciones (detalle en «Alerta solar»).");
          return;
        }
        if (err.code === "SHELTER_LAYER_UNAVAILABLE") {
          showShelterEmpty(err.details && err.details.reason === "outside_detail_region"
            ? "El origen está fuera de la zona de detalle: la alerta solar solo funciona dentro de ella, " +
              "porque la malla global no trae la capa de cielo visible."
            : "Esta fuente de datos no trae la capa de cielo visible; la alerta solar no está disponible.");
          setStatus("info", "Alerta solar no disponible para este origen.");
          return;
        }
        setStatus("error", (err.message || "Error desconocido.") + (err.code ? " [" + err.code + "]" : ""));
      })
      .finally(function () {
        state.loading = false;
        updateButtons();
      });
  }

  function clearAll() {
    state.origin = null;
    state.destination = null;
    setMode("origin");
    clearResults();
    refreshPoints();
    setStatus("info", "Selección borrada. Elige un origen en el mapa.");
  }

  function refreshShieldingLegend() {
    var range = weightsEnabled() ? MarsMap.getShieldingRange() : null;
    $("shielding-legend-item").hidden = !range;
    $("shielding-legend").textContent = range
      ? "Apantallamiento MODELADO (1 − radiation_modeled): oscuro = menos, violeta claro = más. " +
        "Escala relativa a esta región: " + fmt(range.min, 3).replace(".", ",") + " a " +
        fmt(range.max, 3).replace(".", ",") +
        ". No incluye la atenuación atmosférica, así que exagera el blindaje del relieve."
      : "";
  }

  /* ------------------------------------------------- rendimiento (?perf=1) */
  /**
   * Mide la construcción del mapa: init + capas visibles (síncrono) y el primer
   * fotograma pintado después (dos requestAnimationFrame). Lo deja en
   * window.__marsPerf, en la consola y en un recuadro visible.
   */
  function reportPerf(mapData, start) {
    var buildMs = performance.now() - start;
    var result = {
      cells: mapData.cells.length,
      build_ms: Math.round(buildMs),
      paint_ms: null,
      svg_paths: document.querySelectorAll("#map path").length,
      canvases: document.querySelectorAll("#map canvas").length,
      layers: MarsMap.getLayerStats ? MarsMap.getLayerStats() : null,
      user_agent: navigator.userAgent
    };
    window.__marsPerf = result;
    function publish() {
      var box = $("perf-output");
      if (!box) {
        box = document.createElement("pre");
        box.id = "perf-output";
        box.className = "perf-output";
        document.body.appendChild(box);
      }
      box.textContent = "PERF cells=" + result.cells + " build_ms=" + result.build_ms +
        " paint_ms=" + result.paint_ms + " svg_paths=" + result.svg_paths + " canvases=" + result.canvases;
      if (window.console && console.info) { console.info("[MarsPerf]", JSON.stringify(result)); }
    }
    if (typeof window.requestAnimationFrame !== "function") { publish(); return; }
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(function () {
        result.paint_ms = Math.round(performance.now() - start);
        publish();
      });
    });
  }

  /* ------------------------------------------------------- procedencia */
  var PROVENANCE_CLASSES = {
    "MEDIDO": "prov-measured",
    "DERIVADO": "prov-derived",
    "MODELADO": "prov-modeled",
    "ÍNDICE DEL PROYECTO": "prov-index"
  };

  /**
   * Rellena las etiquetas de procedencia con lo que publica /map (campo
   * opcional `provenance`, solo en fuentes reales). Sin el campo, se ocultan.
   */
  function applyProvenance(mapData) {
    var provenance = mapData && mapData.provenance && typeof mapData.provenance === "object"
      ? mapData.provenance
      : null;
    var shown = 0;
    document.querySelectorAll(".prov-badge[data-prov]").forEach(function (badge) {
      var info = provenance && provenance[badge.getAttribute("data-prov")];
      badge.className = "prov-badge";
      if (!info || typeof info.label !== "string" || !info.label) {
        badge.textContent = "";
        badge.removeAttribute("title");
        badge.removeAttribute("tabindex");
        badge.removeAttribute("aria-label");
        badge.hidden = true;
        return;
      }
      badge.textContent = info.label;
      badge.classList.add(PROVENANCE_CLASSES[info.label] || "prov-other");
      var detail = (info.source ? "Fuente: " + info.source + ". " : "") +
        (info.in_cost === true
          ? "Entra directamente al costo de A*."
          : info.in_cost === false ? "No entra directamente al costo de A*." : "") +
        (info.note ? " " + info.note : "");
      badge.title = detail.trim();
      badge.setAttribute("aria-label", info.label + ". " + detail.trim());
      badge.tabIndex = 0;
      badge.hidden = false;
      shown += 1;
    });
    var note = $("prov-note");
    if (note) { note.hidden = shown === 0; }
  }

  /* ----------------------------------------------------------- arranque */
  function loadMap() {
    el["btn-retry"].hidden = true;
    setStatus("loading", "Conectando con la API…");
    return MarsApi.getHealth()
      .then(function () { return MarsApi.getMap(); })
      .then(function (mapData) {
        state.mapData = mapData;
        var sourceLabel = mapData.data_source === "mola"
          ? "TOPOGRAFÍA REAL (MOLA / HRSC)"
          : "DATOS SIMULADOS";
        el["sim-banner"].textContent = sourceLabel +
          " — Proyecto de participantes de NASA Space Apps 2026; no es un producto oficial " +
          "de la NASA. La ruta no es una recomendación de seguridad.";
        el["zone-name"].textContent = mapData.name + " · " + mapData.grid.rows + "×" +
          mapData.grid.cols + " celdas de " + mapData.grid.cell_size_m + " m" +
          (mapData.is_simulated
            ? " (simuladas)"
            : " (detalle local; rutas globales MOLA a 1° ≈ 59 km/celda) ");
        el["risk-layer-toggle"].disabled = !mapData.risk_available;
        el["risk-layer-toggle"].checked = mapData.risk_available;
        el["elevation-layer-label"].textContent = mapData.is_simulated
          ? "Elevación (simulada)"
          : "Elevación MOLA";
        el["slope-layer-label"].textContent = mapData.is_simulated
          ? "Pendiente (simulada)"
          : "Pendiente MOLA";
        $("risk-layer-text").textContent = mapData.risk_available
          ? (mapData.data_source === "mola"
            ? "Riesgo topográfico (proxy)"
            : "Riesgo (simulado)")
          : "Riesgo (no modelado)";
        applyProvenance(mapData);
        el["weights-card"].hidden = !weightsEnabled();
        el["shelter-card"].hidden = !weightsEnabled();
        $("shielding-layer-label").hidden = !weightsEnabled();
        $("shielding-layer-note").hidden = !weightsEnabled();
        $("shielding-layer-toggle").checked = false;
        if (mapData.cost_model && Number.isFinite(mapData.cost_model.risk_weight)) {
          el["weights-formula"].textContent =
            "costo_paso = longitud × (1 + w_pendiente·pendiente + " +
            weightText(mapData.cost_model.risk_weight) +
            "·riesgo + w_radiación·radiación_modelada). El peso del riesgo no se ajusta por solicitud.";
        }
        el["risk-mean-label"].textContent = mapData.risk_available
          ? (mapData.data_source === "mola"
            ? "Proxy medio en la ruta"
            : "Riesgo medio (simulado)")
          : "Riesgo medio";
        el["risk-max-label"].textContent = mapData.risk_available
          ? (mapData.data_source === "mola"
            ? "Proxy máximo en la ruta"
            : "Riesgo máximo (simulado)")
          : "Riesgo máximo";
        el["elevation-legend"].textContent = mapData.is_simulated
          ? "Elevación simulada: violeta/azul = baja, amarillo/blanco = alta"
          : "MOLA: violeta/azul = baja, amarillo/rojo/blanco = alta";
        el["slope-legend"].textContent = mapData.is_simulated
          ? "Pendiente simulada: más rojo = más inclinada"
          : "Pendiente MOLA: más rojo = más inclinada";
        el["risk-legend"].textContent = mapData.risk_available
          ? (mapData.data_source === "mola"
            ? "Proxy de pendiente: verde bajo · amarillo moderado · rojo alto; 1 = 20° o más. No es probabilidad."
            : "Riesgo simulado: círculo mayor = más riesgo")
          : "Riesgo no modelado";
        el.disclaimer.textContent = mapData.disclaimer;
        el["map-view-controls"].hidden = mapData.data_source !== "mola";
        var roverCard = $("rover-layers-card");
        if (roverCard) { roverCard.hidden = mapData.data_source !== "mola"; }
        el["map-attribution"].hidden = mapData.data_source !== "mola";
        el["place-names-label"].hidden = mapData.data_source !== "mola";
        el["place-names-note"].hidden = mapData.data_source !== "mola";
        $("global-mola-label").hidden = mapData.data_source !== "mola";
        $("local-mola-label").hidden = mapData.data_source !== "mola";
        $("viking-layer-label").hidden = mapData.data_source !== "mola";
        $("synthetic-elevation-label").hidden = mapData.data_source === "mola";
        $("map").setAttribute(
          "aria-label",
          mapData.data_source === "mola"
            ? "Relieve topográfico MOLA global con detalle local para explorar rutas"
            : "Mapa interactivo de la zona sintética"
        );
        state.basemapErrorShown = false;
        var perfStart = window.MarsConfig.PERF ? performance.now() : 0;
        MarsMap.init("map", mapData, {
          onCellClick: onCellClick,
          onCellHover: onCellHover,
          onNoDataClick: function () {
            setStatus("info", "No hay una celda MOLA global válida en esta ubicación. Prueba otra zona.");
          },
          onBaseMapError: function (error) {
            if (state.basemapErrorShown) { return; }
            state.basemapErrorShown = true;
            var message = error && error.message ? error.message : "No se pudo cargar una capa del mapa.";
            var hint = message.indexOf("Viking") !== -1
              ? " Verifica tu conexión a Internet."
              : " Comprueba que frontend/assets/mola-global.png esté disponible.";
            setStatus("error", message + hint);
          },
          onPlaceNamesError: function (error) {
            setStatus("error", "No se pudieron cargar los nombres de NASA/JPL: " + error.message);
          }
        });
        MarsMap.setPlaceNamesVisible(el["place-names-toggle"].checked);
        refreshShieldingLegend();
        applyLayerCheckboxes();
        if (window.MarsConfig.PERF) { reportPerf(mapData, perfStart); }
        refreshPoints();
        setStatus("success", "Conectado. Mapa cargado. Elige un origen haciendo clic en una celda.");
      })
      .catch(function (err) {
        state.mapData = null;
        setStatus("error", err.message + (err.code ? " [" + err.code + "]" : ""));
        el["btn-retry"].hidden = false;
        updateButtons();
      });
  }

  function applyLayerCheckboxes() {
    document.querySelectorAll("input[data-layer]").forEach(function (box) {
      MarsMap.setLayerVisible(box.getAttribute("data-layer"), box.checked);
    });
  }

  function bindEvents() {
    el["mode-origin"].addEventListener("click", function () { setMode("origin"); });
    el["mode-dest"].addEventListener("click", function () { setMode("destination"); });
    el["btn-route"].addEventListener("click", requestRoute);
    el["btn-clear"].addEventListener("click", clearAll);
    el["btn-retry"].addEventListener("click", loadMap);
    el["btn-mars-global"].addEventListener("click", MarsMap.viewMarsGlobal);
    el["btn-mola-region"].addEventListener("click", MarsMap.viewMolaRegion);
    el["viking-layer-toggle"].addEventListener("change", function () {
      MarsMap.setVikingVisible(el["viking-layer-toggle"].checked);
    });
    el["place-names-toggle"].addEventListener("change", function () {
      MarsMap.setPlaceNamesVisible(el["place-names-toggle"].checked);
    });
    el["opt-diagonal"].addEventListener("change", clearResults);
    WEIGHT_FIELDS.forEach(function (field) {
      el[field.range].addEventListener("input", function () { onWeightInput(field, "range"); });
      el[field.number].addEventListener("input", function () { onWeightInput(field, "number"); });
    });
    el["btn-weights-reset"].addEventListener("click", resetWeights);
    el["btn-shelter"].addEventListener("click", requestShelter);
    el["shelter-max-km"].addEventListener("input", function () {
      refreshShelterMaxError();
      updateButtons();
    });
    document.querySelectorAll("input[data-layer]").forEach(function (box) {
      box.addEventListener("change", function () {
        MarsMap.setLayerVisible(box.getAttribute("data-layer"), box.checked);
      });
    });
    window.addEventListener("resize", MarsMap.invalidate);
  }

  document.addEventListener("DOMContentLoaded", function () {
    cacheElements();
    bindEvents();
    updateButtons();
    loadMap();
  });
})();
