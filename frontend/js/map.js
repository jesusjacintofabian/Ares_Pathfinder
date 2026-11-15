/*
 * Mapa Leaflet con relieve MOLA global y cuadrícula de detalle local.
 *
 * En MOLA, Leaflet usa grados en L.CRS.Simple para ubicar el relieve global,
 * la cuadrícula local y las capas opcionales. El modo sintético conserva su
 * plano local fila/columna.
 * La API recibe índices locales o coordenadas geográficas en modo MOLA.
 */
(function () {
  "use strict";

  var map = null;
  var rows = 0;
  var cols = 0;
  var cellsByKey = {};
  var globalCellsByKey = {};
  var globalGridRows = 0;
  var globalGridCols = 0;
  var layers = {};
  var routeLine = null;
  var pins = { origin: null, dest: null };
  var onCellClickCb = null;
  var onCellHoverCb = null;
  var onNoDataClickCb = null;
  var onBaseMapErrorCb = null;
  var geographic = false;
  var region = null;
  var latitudeStep = 0;
  var longitudeStep = 0;
  var basemapLayer = null;
  var globalElevationLayer = null;
  var placeNamesLayer = null;
  var missionLayers = {};
  var placeNamesEnabled = false;
  var placeRequestId = 0;
  var placeRequestAbort = null;
  var onPlaceNamesErrorCb = null;
  var shieldingRange = null;

  /*
   * Orden de los panes. La capa de clics (hit) se dibuja en canvas: un <canvas>
   * capta el puntero en toda su superficie, así que va POR DEBAJO de los panes
   * interactivos en SVG/DOM (topónimos, ruta, pines y misiones) para no
   * bloquear sus clics y tooltips. Si el puntero no cae sobre ninguno de ellos,
   * el canvas resuelve la celda o reenvía el clic al mapa (malla global).
   */
  var PANES = {
    globalElevation: 390, elevation: 410, slope: 420, shielding: 425, blocked: 430, risk: 440,
    grid: 450, hit: 452, placeNames: 455, route: 460,
    roverRoutes: 465, markers: 470, roverSites: 475
  };

  /** Capas de celdas que se dibujan con L.canvas() (un renderizador por pane). */
  var CANVAS_PANES = ["elevation", "slope", "shielding", "risk", "grid", "hit"];
  var cellRenderers = {};

  function key(row, col) { return row + "," + col; }

  function cellBounds(cell) {
    if (geographic) {
      var center = cellCenter(cell.row, cell.col);
      return [
        [center[0] - latitudeStep / 2, center[1] - longitudeStep / 2],
        [center[0] + latitudeStep / 2, center[1] + longitudeStep / 2]
      ];
    }
    var row = cell.row;
    var col = cell.col;
    return [[rows - row - 1, col], [rows - row, col + 1]];
  }

  function setPlaceNamesVisible(visible) {
    placeNamesEnabled = Boolean(visible && geographic);
    if (placeNamesLayer) { placeNamesLayer.clearLayers(); }
    if (placeNamesEnabled) { refreshPlaceNames(); }
    if (placeRequestAbort && !placeNamesEnabled) { placeRequestAbort.abort(); }
  }

  function cellCenter(row, col) {
    var cell = cellsByKey[key(row, col)];
    if (geographic && cell && Number.isFinite(cell.latitude) && Number.isFinite(cell.longitude)) {
      return [cell.latitude, cell.longitude];
    }
    return [rows - row - 0.5, col + 0.5];
  }

  function createMarsBasemap() {
    var tileSize = 256;
    var imageService =
      "https://trek.nasa.gov/mars/trekarcgis/rest/services/" +
      "Mars_Viking_MDIM21_ClrMosaic_global_232m/ImageServer/exportImage";
    var MarsImageLayer = L.GridLayer.extend({
      createTile: function (coords, done) {
        var tile = document.createElement("canvas");
        var context = tile.getContext("2d");
        tile.width = tileSize;
        tile.height = tileSize;
        if (!context) {
          // Entornos sin canvas 2D (p. ej. jsdom o navegadores restringidos):
          // la tesela queda vacía, pero la cuadrícula MOLA y A* siguen funcionando.
          done(new Error("Canvas 2D no disponible"), tile);
          return tile;
        }
        context.fillStyle = "#100b09";
        context.fillRect(0, 0, tileSize, tileSize);

        var scale = Math.pow(2, coords.z);
        var west = coords.x * tileSize / scale;
        var east = (coords.x + 1) * tileSize / scale;
        var north = -coords.y * tileSize / scale;
        var south = -(coords.y + 1) * tileSize / scale;
        var validSouth = Math.max(south, -90);
        var validNorth = Math.min(north, 90);
        if (validSouth >= validNorth) {
          done(null, tile);
          return tile;
        }

        var seams = [west, east];
        var firstSeam = Math.floor(west / 180) + 1;
        for (var seam = firstSeam * 180; seam < east; seam += 180) {
          seams.push(seam);
        }
        seams.sort(function (a, b) { return a - b; });
        var segments = [];
        for (var i = 0; i < seams.length - 1; i += 1) {
          if (seams[i + 1] > seams[i]) {
            segments.push([seams[i], seams[i + 1]]);
          }
        }

        var pending = segments.length;
        var tileError = null;
        segments.forEach(function (segment) {
          var segmentWest = segment[0];
          var segmentEast = segment[1];
          var offset = Math.floor((segmentWest + segmentEast) / 360) * 360;
          var imageWest = segmentWest - offset;
          var imageEast = segmentEast - offset;
          if (imageWest >= 180) {
            imageWest -= 360;
            imageEast -= 360;
          }
          var width = Math.max(1, Math.round((segmentEast - segmentWest) * scale));
          var height = Math.max(1, Math.round((validNorth - validSouth) * scale));
          var query = [
            "bbox=" + [imageWest, validSouth, imageEast, validNorth].join(","),
            "bboxSR=104905",
            "size=" + width + "," + height,
            "imageSR=104905",
            "format=jpg",
            "f=image"
          ].join("&");
          var image = new Image();
          image.onload = function () {
            var x = Math.round((segmentWest - west) * scale);
            var y = Math.round((north - validNorth) * scale);
            context.drawImage(image, x, y, width, height);
            pending -= 1;
            if (!pending) { done(tileError, tile); }
          };
          image.onerror = function () {
            tileError = new Error("No se pudo cargar una tesela del mosaico orbital.");
            pending -= 1;
            if (!pending) { done(tileError, tile); }
          };
          image.src = imageService + "?" + query;
        });
        return tile;
      }
    });

    return new MarsImageLayer({
      tileSize: tileSize,
      minZoom: 0,
      maxNativeZoom: 8,
      maxZoom: 12,
      bounds: [[-90, 0], [90, 360]],
      noWrap: true,
      attribution: "Mosaico Viking MDIM 2.1 · NASA/JPL Mars Trek"
    });
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        "\"": "&quot;",
        "'": "&#39;"
      }[character];
    });
  }

  function featureCategory(featureType) {
    var type = String(featureType || "").toLowerCase();
    if (/mons|montes|patera|tholus|volcano/.test(type)) { return "volcano"; }
    if (/crater/.test(type)) { return "crater"; }
    return "other";
  }

  function addPlaceFeature(feature) {
    var attributes = feature.attributes || {};
    var longitude = Number(attributes.center_lon);
    var latitude = Number(attributes.center_lat);
    if (!attributes.name || !Number.isFinite(longitude) || !Number.isFinite(latitude)) {
      return;
    }

    longitude = ((longitude % 360) + 360) % 360;
    var category = featureCategory(attributes.type);
    var marker = L.marker([latitude, longitude], {
      pane: "placeNames",
      keyboard: false,
      bubblingMouseEvents: false,
      icon: L.divIcon({
        className: "",
        html: '<span class="place-marker place-marker-' + category + '"></span>',
        iconSize: [10, 10],
        iconAnchor: [5, 5]
      })
    });
    var popup = document.createElement("div");
    var title = document.createElement("strong");
    title.textContent = attributes.name;
    popup.appendChild(title);
    var detail = document.createElement("div");
    detail.textContent = attributes.type || "Accidente geográfico";
    popup.appendChild(detail);
    if (Number.isFinite(Number(attributes.diameter)) && Number(attributes.diameter) > 0) {
      var diameter = document.createElement("div");
      diameter.textContent = "Diámetro publicado: " + Number(attributes.diameter).toFixed(1) + " km";
      popup.appendChild(diameter);
    }
    marker.bindPopup(popup);
    marker.bindTooltip(escapeHtml(attributes.name), {
      permanent: false,
      direction: "right",
      offset: [6, 0],
      className: "place-label"
    });
    marker.placeName = String(attributes.name);
    marker.placeDiameter = Number.isFinite(Number(attributes.diameter))
      ? Number(attributes.diameter)
      : 0;
    marker.placeCategory = category;
    marker.addTo(placeNamesLayer);
  }

  function placeNameQuery(zoom) {
    if (zoom < 1) { return "diameter >= 1000"; }
    if (zoom < 2) { return "diameter >= 500"; }
    if (zoom < 3) { return "diameter >= 200"; }
    if (zoom < 4) { return "diameter >= 50"; }
    return "1=1";
  }

  function updatePlaceLabels() {
    if (!map || !placeNamesLayer) { return; }
    var zoom = map.getZoom();
    var spacing = zoom < 1 ? 100 : zoom < 2 ? 82 : zoom < 3 ? 64 : zoom < 4 ? 48 : 34;
    var viewport = map.getSize();
    var occupied = [];
    var markers = [];

    placeNamesLayer.eachLayer(function (marker) {
      markers.push(marker);
    });
    markers.sort(function (a, b) {
      return b.placeDiameter - a.placeDiameter ||
        (a.placeCategory === "volcano" ? -1 : 0) -
        (b.placeCategory === "volcano" ? -1 : 0) ||
        a.placeName.localeCompare(b.placeName);
    });

    markers.forEach(function (marker) {
      var point = map.latLngToContainerPoint(marker.getLatLng());
      var tooltip = marker.getTooltip();
      var width = Math.min(220, marker.placeName.length * 6 + 16);
      var box = {
        left: point.x + 7,
        right: point.x + 7 + width,
        top: point.y - 10,
        bottom: point.y + 10
      };
      var showLabel = box.left >= 0 && box.right <= viewport.x &&
        box.top >= 0 && box.bottom <= viewport.y &&
        !occupied.some(function (other) {
          return box.left < other.right + 4 && box.right + 4 > other.left &&
            box.top < other.bottom + 4 && box.bottom + 4 > other.top;
        });

      tooltip.options.permanent = showLabel;
      if (showLabel) {
        occupied.push(box);
        marker.openTooltip();
      } else {
        marker.closeTooltip();
      }
    });
  }

  function featureQuery(south, north, segment, where, signal) {
    var baseUrl =
      "https://trek.nasa.gov/mars/trekarcgis/rest/services/" +
      "combinedNom/MapServer/0/query";
    var west = segment.west > 180 ? segment.west - 360 : segment.west;
    var east = segment.east > 180 ? segment.east - 360 : segment.east;
    var params = new URLSearchParams({
      where: where,
      geometry: [west, south, east, north].join(","),
      geometryType: "esriGeometryEnvelope",
      inSR: "104905",
      spatialRel: "esriSpatialRelIntersects",
      outFields: "name,type,diameter,center_lon,center_lat",
      returnGeometry: "true",
      outSR: "104905",
      f: "json"
    });
    return fetch(baseUrl + "?" + params.toString(), { signal: signal })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("NASA/JPL respondió HTTP " + response.status + " al consultar topónimos.");
        }
        return response.json();
      })
      .then(function (data) {
        if (data.error) {
          throw new Error(data.error.message || "NASA/JPL no pudo consultar los topónimos.");
        }
        if (!Array.isArray(data.features)) {
          throw new Error("La respuesta de topónimos de NASA/JPL no tiene el formato esperado.");
        }
        return data.features;
      });
  }

  function refreshPlaceNames() {
    if (!map || !geographic || !placeNamesEnabled) { return; }
    if (placeRequestAbort) { placeRequestAbort.abort(); }
    placeRequestAbort = new AbortController();
    var requestId = ++placeRequestId;
    var bounds = map.getBounds();
    var west = Math.max(0, bounds.getWest());
    var east = Math.min(360, bounds.getEast());
    var south = Math.max(-90, bounds.getSouth());
    var north = Math.min(90, bounds.getNorth());
    if (east <= west || north <= south) { return; }

    var segments = [];
    if (west < 180) { segments.push({ west: west, east: Math.min(east, 180) }); }
    if (east > 180) { segments.push({ west: Math.max(west, 180), east: east }); }
    var where = placeNameQuery(map.getZoom());
    placeNamesLayer.clearLayers();
    Promise.all(segments.map(function (segment) {
      return featureQuery(south, north, segment, where, placeRequestAbort.signal);
    }))
      .then(function (responses) {
        if (requestId !== placeRequestId) { return; }
        var featuresByName = {};
        responses.forEach(function (features) {
          features.forEach(function (feature) {
            var name = feature.attributes && feature.attributes.name;
            if (name) { featuresByName[name] = feature; }
          });
        });
        Object.keys(featuresByName).forEach(function (name) {
          addPlaceFeature(featuresByName[name]);
        });
        updatePlaceLabels();
      })
      .catch(function (error) {
        if (error.name === "AbortError" || requestId !== placeRequestId) { return; }
        if (onPlaceNamesErrorCb) { onPlaceNamesErrorCb(error); }
      });
  }

  function elevationColor(t) {
    var stops = [
      [75, 0, 190], [32, 54, 255], [0, 174, 255], [0, 220, 165],
      [154, 231, 40], [255, 218, 0], [255, 111, 20], [235, 35, 25], [255, 245, 226]
    ];
    var scaled = Math.max(0, Math.min(1, t)) * (stops.length - 1);
    var index = Math.min(stops.length - 2, Math.floor(scaled));
    var fraction = scaled - index;
    var color = stops[index].map(function (value, channel) {
      return Math.round(value + (stops[index + 1][channel] - value) * fraction);
    });
    return "rgb(" + color.join(",") + ")";
  }

  function riskColor(risk) {
    var stops = [
      [37, 196, 126],
      [255, 203, 61],
      [242, 72, 76]
    ];
    var scaled = Math.max(0, Math.min(1, risk)) * (stops.length - 1);
    var index = Math.min(stops.length - 2, Math.floor(scaled));
    var fraction = scaled - index;
    var color = stops[index].map(function (value, channel) {
      return Math.round(value + (stops[index + 1][channel] - value) * fraction);
    });
    return "rgb(" + color.join(",") + ")";
  }

  /** Rampa secuencial para el índice de apantallamiento (0 = poco, 1 = mucho). */
  function shieldingColor(t) {
    var low = [52, 40, 110];
    var high = [196, 150, 255];
    var k = Math.max(0, Math.min(1, t));
    return "rgb(" + low.map(function (value, channel) {
      return Math.round(value + (high[channel] - value) * k);
    }).join(",") + ")";
  }

  /**
   * Índice de apantallamiento MODELADO = 1 − radiation_modeled. La API publica
   * radiation_modeled (más alto = más cielo visible = más exposición relativa);
   * la inversión se hace aquí, solo para pintar.
   */
  function shieldingValue(cell) {
    return Number.isFinite(cell.radiation_modeled) ? 1 - cell.radiation_modeled : null;
  }

  function init(elementId, mapData, handlers) {
    if (map) { map.remove(); map = null; }
    layers = {};
    rows = mapData.grid.rows;
    cols = mapData.grid.cols;
    onCellClickCb = handlers.onCellClick;
    onCellHoverCb = handlers.onCellHover;
    onNoDataClickCb = handlers.onNoDataClick;
    onBaseMapErrorCb = handlers.onBaseMapError;
    onPlaceNamesErrorCb = handlers.onPlaceNamesError;
    cellsByKey = {};
    globalCellsByKey = {};
    missionLayers = {};
    instrumentLayers = {};
    geographic = mapData.data_source === "mola" && Boolean(mapData.region);
    region = geographic ? mapData.region : null;
    globalGridRows = geographic && mapData.global_grid ? mapData.global_grid.rows : 0;
    globalGridCols = geographic && mapData.global_grid ? mapData.global_grid.cols : 0;
    if (geographic && mapData.global_grid) {
      mapData.global_grid.cells.forEach(function (cell, index) {
        var row = Math.floor(index / globalGridCols);
        var col = index % globalGridCols;
        globalCellsByKey[key(row, col)] = {
          row: row,
          col: col,
          elevation_m: cell.elevation_m,
          slope_deg: cell.slope_deg,
          risk: cell.risk,
          blocked: cell.blocked,
          valid: cell.valid,
          latitude: mapData.global_grid.region.north -
            (row + 0.5) * (mapData.global_grid.region.north - mapData.global_grid.region.south) /
              globalGridRows,
          longitude: mapData.global_grid.region.west +
            (col + 0.5) * (mapData.global_grid.region.east - mapData.global_grid.region.west) /
              globalGridCols
        };
      });
    }
    latitudeStep = geographic ? (region.north - region.south) / rows : 0;
    longitudeStep = geographic ? (region.east - region.west) / cols : 0;

    map = L.map(elementId, {
      crs: L.CRS.Simple,
      minZoom: geographic ? 0 : -2,
      maxZoom: geographic ? 12 : 6,
      zoomSnap: 0.25,
      attributionControl: false
    });

    Object.keys(PANES).forEach(function (name) {
      map.createPane(name);
      map.getPane(name).style.zIndex = PANES[name];
    });
    // Un renderizador canvas por pane conserva el orden visual entre capas.
    // Ruta, pines, celdas bloqueadas y misiones siguen en SVG/DOM.
    cellRenderers = {};
    CANVAS_PANES.forEach(function (name) {
      cellRenderers[name] = L.canvas({ pane: name, padding: 0.1 });
    });

    var bounds = geographic ? [[-90, 0], [90, 360]] : [[0, 0], [rows, cols]];
    if (geographic) {
      basemapLayer = null;
      map.fitBounds(bounds, { padding: [10, 10] });
      map.setMaxBounds(bounds);
      map.on("click", function (event) {
        var latitude = event.latlng.lat;
        var longitude = ((event.latlng.lng % 360) + 360) % 360;
        if (latitude >= region.south && latitude <= region.north &&
            longitude >= region.west && longitude <= region.east) {
          return;
        }
        var globalRow = Math.max(0, Math.min(
          globalGridRows - 1, Math.floor((90 - latitude) * globalGridRows / 180)
        ));
        var globalCol = Math.max(0, Math.min(
          globalGridCols - 1, Math.floor(longitude * globalGridCols / 360)
        ));
        var globalCell = globalCellsByKey[key(globalRow, globalCol)];
        if (globalCell) {
          if (onCellClickCb) { onCellClickCb(globalCell); }
          if (onCellHoverCb) { onCellHoverCb(globalCell); }
        } else if (onNoDataClickCb) {
          onNoDataClickCb();
        }
      });
      map.on("moveend zoomend", function () {
        if (placeNamesEnabled) { refreshPlaceNames(); }
      });
    } else {
      basemapLayer = null;
      map.fitBounds(bounds, { padding: [10, 10] });
      map.setMaxBounds([[-2, -2], [rows + 2, cols + 2]]);
    }

    var elevations = mapData.cells.map(function (c) { return c.elevation_m; });
    var minE = Math.min.apply(null, elevations);
    var maxE = Math.max.apply(null, elevations);
    var slopes = mapData.cells.map(function (c) { return c.slope_deg; });
    var maxS = Math.max.apply(null, slopes) || 1;

    var withShielding = mapData.radiation_available === true;
    shieldingRange = null;
    if (withShielding) {
      mapData.cells.forEach(function (c) {
        var v = shieldingValue(c);
        if (v === null) { return; }
        if (!shieldingRange) { shieldingRange = { min: v, max: v }; }
        shieldingRange.min = Math.min(shieldingRange.min, v);
        shieldingRange.max = Math.max(shieldingRange.max, v);
      });
    }

    ["elevation", "slope", "shielding", "blocked", "risk", "grid", "route", "markers"].forEach(function (n) {
      layers[n] = L.layerGroup().addTo(map);
    });
    placeNamesLayer = L.layerGroup().addTo(map);

    // Capa invisible de clics (siempre activa; no tiene casilla).
    layers.hit = L.layerGroup().addTo(map);

    if (geographic) {
      globalElevationLayer = L.imageOverlay(
        "assets/mola-global.png",
        [[-90, 0], [90, 360]],
        {
          pane: "globalElevation",
          opacity: 0.94,
          alt: "Relieve topográfico global MOLA, vista previa de 0,5 grados"
        }
      ).addTo(map);
      layers["global-elevation"] = globalElevationLayer;
      L.imageOverlay(
        "assets/mola-global-risk.png",
        [[-90, 0], [90, 360]],
        {
          pane: "risk",
          interactive: false,
          alt: "Indicador topográfico aproximado derivado de pendientes MOLA"
        }
      ).addTo(layers.risk);
      globalElevationLayer.on("error", function () {
        if (onBaseMapErrorCb) {
          onBaseMapErrorCb(new Error("No se pudo cargar la vista global MOLA."));
        }
      });
      L.imageOverlay(
        "assets/mola-global-blocked.png",
        [[-90, 0], [90, 360]],
        {
          pane: "blocked",
          interactive: false,
          alt: "Celdas globales bloqueadas por pendiente en la malla de 1 grado"
        }
      ).addTo(layers.blocked);
    } else {
      globalElevationLayer = null;
    }

    mapData.cells.forEach(function (cell) {
      cellsByKey[key(cell.row, cell.col)] = cell;
      var b = cellBounds(cell);

      // Capa de elevación
      var t = maxE === minE ? 0 : (cell.elevation_m - minE) / (maxE - minE);
      L.rectangle(b, {
        pane: "elevation", renderer: cellRenderers.elevation, interactive: false, stroke: false,
        fillColor: elevationColor(t), fillOpacity: geographic ? 0.45 : 0.92
      }).addTo(layers.elevation);

      // Capa de pendiente
      L.rectangle(b, {
        pane: "slope", renderer: cellRenderers.slope, interactive: false, stroke: false,
        fillColor: "#ff3c1e", fillOpacity: 0.85 * (cell.slope_deg / maxS)
      }).addTo(layers.slope);

      // Índice de apantallamiento MODELADO (solo regiones con radiation_modeled)
      var shield = withShielding ? shieldingValue(cell) : null;
      if (shield !== null && shieldingRange) {
        var span = shieldingRange.max - shieldingRange.min;
        var ts = span > 0 ? (shield - shieldingRange.min) / span : 0;
        L.rectangle(b, {
          pane: "shielding", renderer: cellRenderers.shielding, interactive: false, stroke: false,
          fillColor: shieldingColor(ts), fillOpacity: 0.2 + 0.6 * ts
        }).addTo(layers.shielding);
      }

      // Capa de celdas bloqueadas
      if (cell.blocked) {
        L.rectangle(b, {
          pane: "blocked", interactive: false, color: "#777", weight: 1,
          fillColor: "#0c0c0c", fillOpacity: 0.92
        }).addTo(layers.blocked);
      }

      // Risk shading is a simulation in synthetic mode and a slope proxy in MOLA.
      if (cell.valid !== false) {
        L.rectangle(b, {
          pane: "risk", renderer: cellRenderers.risk, interactive: false, stroke: false,
          fillColor: geographic ? riskColor(cell.risk) : "#ff3b3b",
          fillOpacity: geographic ? 0.18 + 0.52 * cell.risk : 0.55 * cell.risk
        }).addTo(layers.risk);
      }

      // Cuadrícula visible
      L.rectangle(b, {
        pane: "grid", renderer: cellRenderers.grid, interactive: false, color: "#000", weight: 1,
        opacity: 0.35, fill: false
      }).addTo(layers.grid);

      // Capa invisible que recibe clics (siempre activa)
      var hit = L.rectangle(b, {
        pane: "hit", renderer: cellRenderers.hit, stroke: false, fillColor: "#fff", fillOpacity: 0,
        bubblingMouseEvents: false
      }).addTo(layers.hit);
      hit.on("click", function () { onCellClickCb(cell); });
      hit.on("mouseover", function () {
        hit.setStyle({ fillOpacity: 0.18 });
        if (onCellHoverCb) { onCellHoverCb(cell); }
      });
      hit.on("mouseout", function () { hit.setStyle({ fillOpacity: 0 }); });
    });

    if (!geographic) {
      L.rectangle(bounds, {
        pane: "grid", interactive: false, color: "#e2703a", weight: 2, fill: false
      }).addTo(map);
    }
  }


  // Trazados de referencia de las misiones rover. Coordenadas en latitud y
  // longitud este (0–360), compatibles con el mosaico global de Mars Trek.
  var ROVER_MISSIONS = {
    perseverance: {
      name: "Perseverance · cráter Jezero", color: "#ffcf4a",
      route: [[18.4447,282.5490],[18.4460,282.5520],[18.4480,282.5570],[18.4510,282.5630],[18.4550,282.5700],[18.4590,282.5780],[18.4630,282.5850],[18.4680,282.5920],[18.4730,282.6000]],
      sites: [
        {name:"Octavia E. Butler (aterrizaje)",lat:18.4447,lon:282.5490,type:"Aterrizaje"},
        {name:"Crater floor / Séítah",lat:18.4550,lon:282.5700,type:"Zona de exploración"},
        {name:"Delta de Jezero",lat:18.4730,lon:282.6000,type:"Objetivo geológico"},
        {name:" unidad Margin / borde del delta",lat:18.4800,lon:282.6100,type:"Zona de exploración"},{name:"Witch Hazel Hill (región) ",lat:18.50,lon:282.63,type:"Objetivo geológico"}
      ],
      bounds:[[18.425,282.525],[18.495,282.625]]
    },
    curiosity: {
      name:"Curiosity · cráter Gale",color:"#ff8a65",
      route:[[-4.5895,137.4417],[-4.5905,137.4450],[-4.5920,137.4500],[-4.5950,137.4560],[-4.5980,137.4620],[-4.6010,137.4680],[-4.6040,137.4740],[-4.6070,137.4800]],
      sites:[
        {name:"Bradbury Landing (aterrizaje)",lat:-4.5895,lon:137.4417,type:"Aterrizaje"},
        {name:"Yellowknife Bay",lat:-4.5920,lon:137.4500,type:"Lugar de interés"},
        {name:"Monte Sharp (flanco norte)",lat:-4.6070,lon:137.4800,type:"Objetivo geológico"},
        {name:"Pahrump Hills (región)",lat:-4.65,lon:137.42,type:"Zona de exploración"},{name:"Murray Buttes (región)",lat:-4.68,lon:137.39,type:"Zona de exploración"},{name:"Glen Torridon (región)",lat:-4.70,lon:137.36,type:"Zona de exploración"}
      ],
      bounds:[[-4.63,137.42],[-4.56,137.51]]
    },
    opportunity: {
      name:"Opportunity · Meridiani Planum",color:"#73d6ff",
      route:[[-1.9462,354.4734],[-1.9470,354.4780],[-1.9490,354.4840],[-1.9520,354.4900],[-1.9550,354.4970],[-1.9580,354.5040],[-1.9610,354.5110]],
      sites:[
        {name:"Eagle Crater (aterrizaje)",lat:-1.9462,lon:354.4734,type:"Aterrizaje"},
        {name:"Endurance Crater",lat:-1.9520,lon:354.4900,type:"Cráter de interés"},
        {name:"Victoria Crater",lat:-1.9610,lon:354.5110,type:"Cráter de interés"},
        {name:"Cape York",lat:-1.95,lon:354.49,type:"Zona de exploración"},{name:"Cape Tribulation",lat:-2.00,lon:354.52,type:"Zona de exploración"},{name:"Endeavour Crater",lat:-2.28,lon:354.77,type:"Cráter de interés"}
      ],
      bounds:[[-1.98,354.44],[-1.92,354.54]]
    },
    spirit: {
      name:"Spirit · cráter Gusev",color:"#c79bff",
      route:[[-14.5684,175.4729],[-14.5700,175.4770],[-14.5730,175.4820],[-14.5770,175.4880],[-14.5810,175.4940],[-14.5850,175.5000],[-14.5890,175.5060]],
      sites:[
        {name:"Columbia Memorial Station (aterrizaje)",lat:-14.5684,lon:175.4729,type:"Aterrizaje"},
        {name:"Bonneville Crater",lat:-14.5770,lon:175.4880,type:"Cráter de interés"},
        {name:"Columbia Hills",lat:-14.5890,lon:175.5060,type:"Zona de exploración"},
        {name:"Husband Hill",lat:-14.57,lon:175.48,type:"Objetivo geológico"},{name:"Home Plate",lat:-14.60,lon:175.51,type:"Zona de exploración"},{name:"Tyrone (región)",lat:-14.62,lon:175.52,type:"Zona de exploración"}
      ],
      bounds:[[-14.62,175.44],[-14.54,175.53]]
    },
    zhurong: {
      name:"Zhurong · Utopia Planitia",color:"#a6e27a",
      route:[[25.0660,109.9250],[25.0670,109.9300],[25.0690,109.9360],[25.0710,109.9420],[25.0730,109.9480],[25.0750,109.9540]],
      sites:[
        {name:"Tianwen-1 / Zhurong (aterrizaje)",lat:25.0660,lon:109.9250,type:"Aterrizaje"},
        {name:"Utopia Planitia — zona de recorrido",lat:25.0710,lon:109.9420,type:"Zona de exploración"},
        {name:"Frente de dunas observado",lat:25.0750,lon:109.9540,type:"Objetivo geológico"},
        {name:"Campo de dunas de Utopia",lat:25.08,lon:109.96,type:"Zona de exploración"},{name:"Terreno de aterrizaje Tianwen-1",lat:25.06,lon:109.92,type:"Zona de exploración"}
      ],
      bounds:[[25.04,109.89],[25.10,109.98]]
    }
  };

  // Zonas marcadas como referencias de cobertura/observación de cada instrumento.
  // No representan la huella exacta de cada fotografía del catálogo NASA.
  var INSTRUMENT_ZONES = {
    hirise: { name:"HiRISE · MRO", color:"#ff6b9d", sites:[
      {name:"Cráter Gale",lat:-4.59,lon:137.44},{name:"Cráter Jezero",lat:18.44,lon:282.55},
      {name:"Valles Marineris",lat:-13.0,lon:300.0},{name:"Olympus Mons",lat:18.65,lon:226.2},
      {name:"Polo norte",lat:85.0,lon:0.0}], bounds:[[-90,0],[90,360]] },
    themis: { name:"THEMIS · Mars Odyssey", color:"#ffd166", sites:[
      {name:"Syrtis Major",lat:8.4,lon:69.5},{name:"Elysium Planitia",lat:3.0,lon:147.0},
      {name:"Valles Marineris",lat:-13.0,lon:300.0},{name:"Olympus Mons",lat:18.65,lon:226.2},
      {name:"Terra Meridiani",lat:-2.0,lon:0.0}], bounds:[[-90,0],[90,360]] },
    ctx: { name:"CTX · MRO", color:"#70d6ff", sites:[
      {name:"Cráter Gale",lat:-4.59,lon:137.44},{name:"Cráter Jezero",lat:18.44,lon:282.55},
      {name:"Noctis Labyrinthus",lat:-7.0,lon:265.0},{name:"Hellas Planitia",lat:-42.4,lon:70.5},
      {name:"Arcadia Planitia",lat:46.0,lon:180.0}], bounds:[[-90,0],[90,360]] },
    hrsc: { name:"HRSC · Mars Express", color:"#b8a1ff", sites:[
      {name:"Olympus Mons",lat:18.65,lon:226.2},{name:"Valles Marineris",lat:-13.0,lon:300.0},
      {name:"Hellas Planitia",lat:-42.4,lon:70.5},{name:"Arabia Terra",lat:10.0,lon:20.0},
      {name:"Elysium Planitia",lat:3.0,lon:147.0}], bounds:[[-90,0],[90,360]] }
  };
  var instrumentLayers = {};
  var nextExplorationIndex = 0;

  function setInstrumentVisible(id, visible) {
    if (!map || !geographic || !INSTRUMENT_ZONES[id]) { return; }
    if (!instrumentLayers[id]) {
      var data = INSTRUMENT_ZONES[id], group = L.layerGroup();
      group._explorationPoints = [];
      data.sites.forEach(function(site) {
        var marker = L.circleMarker([site.lat,site.lon], {pane:"roverSites",radius:6,color:"#fff",weight:2,fillColor:data.color,fillOpacity:0.95});
        marker.bindTooltip(site.name + " · " + data.name).bindPopup("<strong>" + site.name + "</strong><br>Zona de referencia de " + data.name + ". No es la huella exacta de una imagen.");
        marker.addTo(group);
        group._explorationPoints.push({marker:marker, name:site.name, lat:site.lat, lon:site.lon});
      });
      if (group._explorationPoints.length > 1) {
        L.polyline(group._explorationPoints.map(function(p){return [p.lat,p.lon];}), {pane:"roverRoutes",color:data.color,weight:2,opacity:0.65,dashArray:"4 7",interactive:false}).addTo(group);
      }
      instrumentLayers[id] = group;
    }
    if (visible) { instrumentLayers[id].addTo(map); }
    else if (map.hasLayer(instrumentLayers[id])) { map.removeLayer(instrumentLayers[id]); }
  }

  function focusInstrument(id, visible) {
    if (!map || !geographic || !INSTRUMENT_ZONES[id]) { return false; }
    // La visibilidad depende exclusivamente de su casilla; enfocar no activa capas.
    setInstrumentVisible(id, Boolean(visible));
    var sites = INSTRUMENT_ZONES[id].sites;
    // El primer sitio es la zona principal de referencia del instrumento.
    // Un encuadre local evita el zoom planetario que ocultaba los puntos.
    var anchor = sites[0];
    var latPad = 3.5;
    var lonPad = 5.0;
    map.fitBounds([[Math.max(-90,anchor.lat-latPad),Math.max(0,anchor.lon-lonPad)],[Math.min(90,anchor.lat+latPad),Math.min(360,anchor.lon+lonPad)]], {padding:[45,45], maxZoom:7});
    return true;
  }

  function addMissionLayer(id) {
    if (!map || !geographic || !ROVER_MISSIONS[id]) { return; }
    if (missionLayers[id]) { return; }
    var mission = ROVER_MISSIONS[id];
    var group = L.layerGroup();
    group._explorationPoints = [];
    L.polyline(mission.route, {
      pane:"roverRoutes", color:mission.color, weight:4, opacity:0.95,
      dashArray:"8 5", lineCap:"round", lineJoin:"round"
    }).bindTooltip(mission.name + " · trayectoria de referencia").addTo(group);
    mission.sites.forEach(function(site) {
      var marker = L.circleMarker([site.lat,site.lon], {
        pane:"roverSites", radius:site.type === "Aterrizaje" ? 7 : 5,
        color:"#fff", weight:2, fillColor:mission.color, fillOpacity:1
      });
      var popup = document.createElement("div");
      var strong = document.createElement("strong");
      strong.textContent = site.name;
      var detail = document.createElement("div");
      detail.textContent = mission.name + " · " + site.type;
      popup.appendChild(strong); popup.appendChild(detail);
      marker.bindPopup(popup).addTo(group);
      group._explorationPoints.push({marker:marker,name:site.name,lat:site.lat,lon:site.lon});
    });
    missionLayers[id] = group;
  }

  function setMissionVisible(id, visible) {
    if (!map || !geographic || !ROVER_MISSIONS[id]) { return; }
    addMissionLayer(id);
    if (visible) { missionLayers[id].addTo(map); }
    else { map.removeLayer(missionLayers[id]); }
  }

  function focusMission(id, visible) {
    if (!map || !geographic || !ROVER_MISSIONS[id]) { return false; }
    var mission = ROVER_MISSIONS[id];
    setMissionVisible(id, Boolean(visible));
    map.fitBounds(mission.bounds, {padding:[45,45], maxZoom:13});
    return true;
  }

  function goToNextExplorationPoint() {
    if (!map || !geographic) { return false; }
    var points = [];
    Object.keys(missionLayers).forEach(function(id) {
      var group = missionLayers[id];
      if (group && map.hasLayer(group)) { points = points.concat(group._explorationPoints || []); }
    });
    Object.keys(instrumentLayers).forEach(function(id) {
      var group = instrumentLayers[id];
      if (group && map.hasLayer(group)) { points = points.concat(group._explorationPoints || []); }
    });
    if (!points.length) { return false; }
    nextExplorationIndex = nextExplorationIndex % points.length;
    var point = points[nextExplorationIndex++];
    // Recalcular el tamaño evita que Leaflet centre respecto a un contenedor
    // desplazado/redimensionado. flyTo recibe siempre el centro exacto del punto.
    if (map.invalidateSize) { map.invalidateSize({ pan: false, animate: false }); }
    map.stop();
    map.flyTo([point.lat, point.lon], 11, {
      animate: true,
      duration: 0.9,
      easeLinearity: 0.25
    });
    if (point.marker && point.marker.openPopup) {
      map.once("moveend", function() {
        // Reafirmar el centro tras terminar la animación para evitar deriva
        // acumulada al navegar por puntos muy separados.
        map.panTo([point.lat, point.lon], { animate: false });
        point.marker.openPopup();
      });
    }
    return point.name || true;
  }

  function viewMarsGlobal() {
    if (map && geographic) {
      map.fitBounds([[-90, 0], [90, 360]], { padding: [10, 10] });
    }
  }

  function viewMolaRegion() {
    if (!map || !geographic || !region) { return; }
    map.fitBounds(
      [[region.south, region.west], [region.north, region.east]],
      { padding: [24, 24] }
    );
  }

  function setLayerVisible(name, visible) {
    var group = layers[name];
    if (!group || !map) { return; }
    if (visible) { group.addTo(map); } else { map.removeLayer(group); }
  }

  function setVikingVisible(visible) {
    if (!map || !geographic) { return; }
    if (!basemapLayer) {
      basemapLayer = createMarsBasemap();
      basemapLayer.on("tileerror", function () {
        if (onBaseMapErrorCb) {
          onBaseMapErrorCb(new Error("No se pudo cargar una tesela Viking de NASA Mars Trek."));
        }
      });
    }
    if (visible) {
      basemapLayer.addTo(map);
      if (globalElevationLayer) { globalElevationLayer.setOpacity(0.7); }
    } else {
      map.removeLayer(basemapLayer);
      if (globalElevationLayer) { globalElevationLayer.setOpacity(0.94); }
    }
  }

  function pinIcon(kind) {
    return L.divIcon({
      className: "",
      html: '<div class="pin pin-' + kind + '">' + (kind === "origin" ? "O" : "D") + "</div>",
      iconSize: [26, 26],
      iconAnchor: [13, 13]
    });
  }

  function setPin(kind, cell) {
    if (pins[kind]) { layers.markers.removeLayer(pins[kind]); pins[kind] = null; }
    if (!cell) { return; }
    var position = Number.isFinite(cell.latitude) && Number.isFinite(cell.longitude)
      ? [cell.latitude, cell.longitude]
      : cellCenter(cell.row, cell.col);
    pins[kind] = L.marker(position, {
      pane: "markers", icon: pinIcon(kind), interactive: false, keyboard: false
    }).addTo(layers.markers);
  }

  /**
   * Dibuja la ruta tal como la devolvió la API (lista de { row, col }).
   * opts.variant === "shelter": ruta de alerta solar (ámbar, discontinua) con
   * un marcador en la zona candidata de espera.
   */
  function drawRoute(path, opts) {
    clearRoute();
    var shelter = Boolean(opts && opts.variant === "shelter");
    var color = shelter ? "#ffb347" : "#39e6d0";
    var latlngs = path.map(function (p) {
      return Number.isFinite(p.latitude) && Number.isFinite(p.longitude)
        ? [p.latitude, p.longitude]
        : cellCenter(p.row, p.col);
    });
    var lineOptions = {
      pane: "route", color: color, weight: 4, opacity: 0.95,
      lineJoin: "round", interactive: false
    };
    if (shelter) { lineOptions.dashArray = "9 6"; }
    routeLine = L.polyline(latlngs, lineOptions).addTo(layers.route);
    if (latlngs.length === 1 && !shelter) {
      L.circleMarker(latlngs[0], {
        pane: "route", radius: 6, color: color, fillOpacity: 1, interactive: false
      }).addTo(layers.route);
    }
    if (shelter && latlngs.length) {
      L.circleMarker(latlngs[latlngs.length - 1], {
        pane: "route", radius: 8, color: "#fff", weight: 2, fillColor: color,
        fillOpacity: 1, interactive: false
      }).bindTooltip("Zona candidata de espera", {
        permanent: true, direction: "top", offset: [0, -8], className: "shelter-label"
      }).addTo(layers.route);
    }
  }

  function clearRoute() {
    if (layers.route) { layers.route.clearLayers(); }
    routeLine = null;
  }

  function getCell(row, col) { return cellsByKey[key(row, col)] || null; }

  /**
   * Número de elementos visibles por capa (0 si la capa está apagada). Sirve
   * para el diagnóstico ?perf=1 y para las pruebas, porque el canvas no deja
   * elementos en el DOM que contar.
   */
  function getLayerStats() {
    var stats = {};
    Object.keys(layers).forEach(function (name) {
      var group = layers[name];
      stats[name] = map && group && group.getLayers && map.hasLayer(group)
        ? group.getLayers().length
        : 0;
    });
    return stats;
  }

  /** Punto del contenedor del mapa (px) en el centro de una celda de detalle. */
  function cellToContainerPoint(row, col) {
    if (!map || !getCell(row, col)) { return null; }
    var point = map.latLngToContainerPoint(cellCenter(row, col));
    return { x: point.x, y: point.y };
  }

  /** Rango real {min, max} del índice de apantallamiento pintado, o null. */
  function getShieldingRange() {
    return shieldingRange ? { min: shieldingRange.min, max: shieldingRange.max } : null;
  }

  function invalidate() { if (map) { map.invalidateSize(); } }

  window.MarsMap = {
    init: init,
    setLayerVisible: setLayerVisible,
    setPin: setPin,
    drawRoute: drawRoute,
    clearRoute: clearRoute,
    getCell: getCell,
    getShieldingRange: getShieldingRange,
    getLayerStats: getLayerStats,
    cellToContainerPoint: cellToContainerPoint,
    viewMarsGlobal: viewMarsGlobal,
    viewMolaRegion: viewMolaRegion,
    setPlaceNamesVisible: setPlaceNamesVisible,
    setVikingVisible: setVikingVisible,
    setMissionVisible: setMissionVisible,
    focusMission: focusMission,
    setInstrumentVisible: setInstrumentVisible,
    focusInstrument: focusInstrument,
    goToNextExplorationPoint: goToNextExplorationPoint,
    invalidate: invalidate
  };
})();
