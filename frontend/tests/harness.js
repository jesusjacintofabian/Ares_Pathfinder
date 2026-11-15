/*
 * Arnés de pruebas: carga index.html, Leaflet local y los scripts del frontend
 * en jsdom, con un fetch falso que responde a la API según las reglas dadas.
 * No hay red: cualquier URL no prevista responde 404.
 */
"use strict";

const fs = require("node:fs");
const path = require("node:path");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..");

function read(relative) {
  return fs.readFileSync(path.join(ROOT, relative), "utf8");
}

/** Respuesta mínima compatible con lo que usa js/api.js (ok, status, text()). */
function jsonResponse(status, body) {
  const text = JSON.stringify(body);
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status: status,
    text: () => Promise.resolve(text),
    json: () => Promise.resolve(JSON.parse(text))
  });
}

/**
 * Crea la página.
 * @param {object} options
 *   mapData: respuesta de GET /map
 *   routes: función (body) => [status, json] para POST /routes
 *   shelter: función (body) => [status, json] para POST /routes/shelter
 *   query: cadena de búsqueda de la URL (p. ej. "?perf=1")
 */
async function loadApp(options) {
  const html = read("index.html").replace(/<script[^>]*src="[^"]*"[^>]*><\/script>/g, "");
  const requests = [];
  const dom = new JSDOM(html, {
    url: "http://127.0.0.1:5500/" + (options.query || ""),
    runScripts: "outside-only",
    pretendToBeVisual: true
  });
  const { window } = dom;

  // jsdom no hace layout: se da un tamaño fijo al contenedor del mapa para
  // que Leaflet pueda calcular el zoom.
  Object.defineProperty(window.HTMLElement.prototype, "clientWidth", { get: () => 800 });
  Object.defineProperty(window.HTMLElement.prototype, "clientHeight", { get: () => 600 });
  // Leaflet detecta SVG con createSVGRect, que jsdom no implementa.
  if (window.SVGSVGElement && !window.SVGSVGElement.prototype.createSVGRect) {
    window.SVGSVGElement.prototype.createSVGRect = function () { return {}; };
  }
  // jsdom no implementa canvas 2D. Las capas de celdas usan L.canvas(), así que se
  // da un contexto falso que acepta cualquier llamada sin pintar nada. Leaflet
  // resuelve clics y hover con geometría (no lee píxeles), así que siguen funcionando.
  window.HTMLCanvasElement.prototype.getContext = function () {
    if (!this.__fakeContext) {
      const calls = { fill: 0, stroke: 0 };
      this.__fakeContext = new Proxy({ canvas: this, __calls: calls }, {
        get(target, prop) {
          if (prop in target) { return target[prop]; }
          if (prop === "fill" || prop === "stroke") { return () => { calls[prop] += 1; }; }
          return () => {};
        },
        set(target, prop, value) { target[prop] = value; return true; }
      });
    }
    return this.__fakeContext;
  };

  window.fetch = function (url, init) {
    const method = (init && init.method) || "GET";
    const body = init && init.body ? JSON.parse(init.body) : null;
    requests.push({ url: String(url), method: method, body: body, rawBody: init && init.body });
    const u = String(url);
    if (u.endsWith("/api/v1/health")) {
      return jsonResponse(200, { status: "ok", data_source: options.mapData.data_source });
    }
    if (u.endsWith("/api/v1/map")) { return jsonResponse(200, options.mapData); }
    if (u.endsWith("/api/v1/routes/shelter") && options.shelter) {
      return jsonResponse.apply(null, options.shelter(body));
    }
    if (u.endsWith("/api/v1/routes") && options.routes) {
      return jsonResponse.apply(null, options.routes(body));
    }
    return jsonResponse(404, { error: { code: "NOT_FOUND", message: "No encontrado", details: {} } });
  };

  [
    "vendor/leaflet/leaflet.js",
    "js/config.js",
    "js/api.js",
    "js/map.js",
    "js/app.js",
    "js/missions.js"
  ].forEach((file) => window.eval(read(file) + "\n//# sourceURL=" + file));

  window.document.dispatchEvent(new window.Event("DOMContentLoaded"));
  await settle(window);
  return { window, document: window.document, requests, dom };
}

/** Deja correr las promesas pendientes (fetch falso y cadenas .then). */
async function settle(window) {
  for (let i = 0; i < 20; i += 1) {
    await new Promise((resolve) => window.setTimeout(resolve, 0));
  }
}

/** Canvas de la capa de clics (pane "hit"). */
function hitCanvas(window) {
  const canvas = window.document.querySelector(".leaflet-hit-pane canvas");
  if (!canvas) { throw new Error("No hay canvas en la capa de clics"); }
  return canvas;
}

/** Evento de ratón con coordenadas de pantalla. jsdom pone el mapa en (0, 0). */
function mouseAt(window, target, type, x, y) {
  target.dispatchEvent(new window.MouseEvent(type, {
    bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0
  }));
}

function cellPoint(window, row, col) {
  // Como haría una persona: acercarse a la zona de detalle antes de elegir una
  // celda (en la vista global cada celda MOLA mide menos de un píxel).
  // En modo sintético no hace nada: el mapa ya encuadra la cuadrícula.
  window.MarsMap.viewMolaRegion();
  const point = window.MarsMap.cellToContainerPoint(row, col);
  if (!point) { throw new Error("No existe la celda " + row + "," + col); }
  return point;
}

/**
 * Simula un clic real del ratón sobre el centro de la celda (row, col): el
 * evento llega al canvas de la capa de clics, que busca la celda por geometría.
 */
function clickCell(window, mapData, row, col) {
  const p = cellPoint(window, row, col);
  mouseAt(window, hitCanvas(window), "click", p.x, p.y);
}

/** Mueve el ratón sobre la celda (hover). Leaflet limita el hover a uno cada 32 ms. */
async function hoverCell(window, row, col) {
  const p = cellPoint(window, row, col);
  mouseAt(window, hitCanvas(window), "mousemove", p.x, p.y);
  await new Promise((resolve) => window.setTimeout(resolve, 40));
}

/** Cambia el valor de un input y lanza input + change. */
function setValue(window, element, value) {
  element.value = String(value);
  element.dispatchEvent(new window.Event("input", { bubbles: true }));
  element.dispatchEvent(new window.Event("change", { bubbles: true }));
}

module.exports = {
  loadApp, settle, clickCell, hoverCell, hitCanvas, mouseAt, setValue, jsonResponse
};
