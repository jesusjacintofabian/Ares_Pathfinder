"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp } = require("./harness");
const fx = require("./fixtures");

/** Cuadrícula MOLA con radiación del tamaño real de Gale (80 × 70 = 5 600). */
function galeSized() {
  const base = fx.molaMap(true);
  const rows = 80;
  const cols = 70;
  const region = { south: -5.3088, north: -4.499, west: 137.2989, east: 138.0075 };
  const dLat = (region.north - region.south) / rows;
  const dLon = (region.east - region.west) / cols;
  const cells = [];
  for (let row = 0; row < rows; row += 1) {
    for (let col = 0; col < cols; col += 1) {
      const svf = 0.74 + 0.25 * ((row * cols + col) % 97) / 96;
      cells.push({
        row, col,
        latitude: region.north - (row + 0.5) * dLat,
        longitude: region.west + (col + 0.5) * dLon,
        elevation_m: -4500 + row * 10, slope_deg: (row + col) % 30,
        risk: Math.min(((row + col) % 30) / 20, 1), blocked: (row * col) % 373 === 1,
        valid: true, sky_view_factor: svf, radiation_modeled: svf
      });
    }
  }
  return Object.assign(base, { grid: { rows, cols, cell_size_m: 600 }, region, cells });
}

test("?perf=1 publica la medición; sin el parámetro no se mide", async () => {
  const mapData = fx.molaMap(true);
  const withPerf = await loadApp({ mapData, query: "?perf=1" });
  const perf = withPerf.window.__marsPerf;
  assert.ok(perf, "window.__marsPerf existe");
  assert.equal(perf.cells, 9);
  assert.ok(Number.isFinite(perf.build_ms));
  assert.ok(perf.svg_paths > 0);
  assert.match(withPerf.document.getElementById("perf-output").textContent, /^PERF cells=9/);

  const without = await loadApp({ mapData });
  assert.equal(without.window.__marsPerf, undefined);
  assert.equal(without.document.getElementById("perf-output"), null);
});

test("tamaño Gale: capas de celdas en canvas, sin paths SVG por celda", async () => {
  const mapData = galeSized();
  const { document, window } = await loadApp({ mapData, query: "?perf=1" });
  const stats = window.MarsMap.getLayerStats();
  const n = mapData.cells.length;
  // Visibles por defecto: elevación, riesgo y la capa de clics (más las bloqueadas, en SVG).
  assert.equal(stats.elevation, n);
  assert.equal(stats.risk >= n, true);
  assert.equal(stats.hit, n);
  assert.equal(stats.slope, 0, "pendiente apagada por defecto");
  assert.equal(stats.shielding, 0, "apantallamiento apagado por defecto");
  assert.equal(stats.grid, 0, "cuadrícula apagada por defecto");
  // Las celdas no generan paths SVG: solo quedan las bloqueadas (pocas) en SVG.
  const blocked = mapData.cells.filter((c) => c.blocked).length;
  assert.equal(document.querySelectorAll("#map path").length, blocked);
  ["elevation", "slope", "shielding", "risk", "grid", "hit"].forEach((pane) => {
    assert.ok(document.querySelector(".leaflet-" + pane + "-pane canvas"), pane + " en canvas");
  });
  assert.equal(window.__marsPerf.canvases >= 6, true);
  // Medición en jsdom: NO representa el pintado real de un navegador.
  console.log("[jsdom tamaño Gale]", JSON.stringify({
    cells: n, svg_paths: window.__marsPerf.svg_paths, canvases: window.__marsPerf.canvases,
    build_ms: window.__marsPerf.build_ms
  }));
});
