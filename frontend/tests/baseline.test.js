/*
 * Comportamiento existente que F6b no debe cambiar: modo sintético y una
 * región MOLA sin capa de radiación (como Valles Marineris).
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp, settle, clickCell } = require("./harness");
const fx = require("./fixtures");

async function routeBodyFor(mapData) {
  const app = await loadApp({
    mapData,
    routes: (body) => [200, fx.routeResponse(mapData, body)]
  });
  const { window, document } = app;
  clickCell(window, mapData, 0, 0);
  clickCell(window, mapData, 0, 2);
  document.getElementById("btn-route").click();
  await settle(window);
  const post = app.requests.find((r) => r.method === "POST");
  return { app, post };
}

test("sintético: carga el mapa y la solicitud de ruta no lleva pesos", async () => {
  const mapData = fx.syntheticMap();
  const { app, post } = await routeBodyFor(mapData);
  const { document } = app;
  assert.match(document.getElementById("sim-banner").textContent, /DATOS SIMULADOS/);
  assert.ok(post, "se envió POST /routes");
  assert.ok(post.url.endsWith("/api/v1/routes"));
  assert.equal(post.rawBody,
    JSON.stringify({ origin: { row: 0, col: 0 }, destination: { row: 0, col: 2 }, allow_diagonal: true }));
  assert.equal(document.getElementById("results-card").hidden, false);
  assert.equal(document.getElementById("res-steps").textContent, "2");
  assert.equal(document.querySelectorAll(".leaflet-route-pane path").length, 1);
});

test("MOLA sin radiación (Valles): solicitud geográfica sin pesos", async () => {
  const mapData = fx.molaMap(false);
  const { app, post } = await routeBodyFor(mapData);
  const o = mapData.cells[0];
  const d = mapData.cells[2];
  assert.equal(post.rawBody, JSON.stringify({
    origin: { latitude: o.latitude, longitude: o.longitude },
    destination: { latitude: d.latitude, longitude: d.longitude },
    allow_diagonal: true
  }));
  assert.match(app.document.getElementById("status").textContent, /MOLA de detalle/);
});

test("celda bloqueada: se rechaza en la interfaz sin llamar a la API", async () => {
  const mapData = fx.syntheticMap();
  const app = await loadApp({ mapData });
  clickCell(app.window, mapData, 1, 2);
  assert.match(app.document.getElementById("status").textContent, /bloqueada/);
  assert.equal(app.requests.filter((r) => r.method === "POST").length, 0);
});
