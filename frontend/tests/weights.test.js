"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp, settle, clickCell, setValue } = require("./harness");
const fx = require("./fixtures");

async function galeApp() {
  const mapData = fx.molaMap(true);
  const app = await loadApp({
    mapData,
    routes: (body) => [200, fx.routeResponse(mapData, body)]
  });
  clickCell(app.window, mapData, 0, 0);
  clickCell(app.window, mapData, 0, 2);
  return Object.assign(app, { mapData });
}

function lastPost(app) {
  return app.requests.filter((r) => r.method === "POST").pop();
}

test("Gale: los pesos por defecto (0,05 y 0) viajan en POST /routes", async () => {
  const app = await galeApp();
  const { document, window } = app;
  assert.equal(document.getElementById("weights-card").hidden, false);
  assert.match(document.getElementById("weights-formula").textContent, /2·riesgo/);
  document.getElementById("btn-route").click();
  await settle(window);
  const body = lastPost(app).body;
  assert.equal(body.slope_weight, 0.05);
  assert.equal(body.radiation_weight, 0);
  assert.equal(document.getElementById("res-weights").hidden, false);
  assert.equal(document.getElementById("res-weights").textContent,
    "pendiente 0,05 · riesgo 2 · radiación 0");
});

test("Gale: el deslizador y el campo numérico se sincronizan y se envían", async () => {
  const app = await galeApp();
  const { document, window } = app;
  setValue(window, document.getElementById("radiation-weight-range"), "12.5");
  assert.equal(document.getElementById("radiation-weight-number").value, "12.5");
  setValue(window, document.getElementById("slope-weight-number"), "0.2");
  assert.equal(document.getElementById("slope-weight-range").value, "0.2");
  document.getElementById("btn-route").click();
  await settle(window);
  const body = lastPost(app).body;
  assert.equal(body.slope_weight, 0.2);
  assert.equal(body.radiation_weight, 12.5);
  assert.match(document.getElementById("res-weights").textContent, /radiación 12,5/);
});

test("Gale: un peso fuera de 0–100 bloquea el cálculo y lo explica", async () => {
  const app = await galeApp();
  const { document, window } = app;
  setValue(window, document.getElementById("slope-weight-number"), "150");
  assert.equal(document.getElementById("btn-route").disabled, true);
  assert.equal(document.getElementById("weights-error").hidden, false);
  assert.match(document.getElementById("weights-error").textContent, /pendiente/);
  document.getElementById("btn-weights-reset").click();
  assert.equal(document.getElementById("slope-weight-number").value, "0.05");
  assert.equal(document.getElementById("radiation-weight-number").value, "0");
  assert.equal(document.getElementById("btn-route").disabled, false);
  assert.equal(document.getElementById("weights-error").hidden, true);
});

test("sin capa de radiación no hay controles de pesos ni fila de pesos aplicados", async () => {
  const mapData = fx.molaMap(false);
  const app = await loadApp({ mapData, routes: (body) => [200, fx.routeResponse(mapData, body)] });
  const { document, window } = app;
  assert.equal(document.getElementById("weights-card").hidden, true);
  clickCell(window, mapData, 0, 0);
  clickCell(window, mapData, 0, 2);
  document.getElementById("btn-route").click();
  await settle(window);
  assert.equal("slope_weight" in lastPost(app).body, false);
  assert.equal(document.getElementById("res-weights").hidden, true);
});
