"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp, settle, clickCell, setValue } = require("./harness");
const fx = require("./fixtures");

async function galeWithShelter(shelterHandler) {
  const mapData = fx.molaMap(true);
  const app = await loadApp({
    mapData,
    routes: (body) => [200, fx.routeResponse(mapData, body)],
    shelter: shelterHandler || ((body) => [200, fx.shelterResponse(mapData, body)])
  });
  return Object.assign(app, { mapData });
}

function shelterPost(app) {
  return app.requests.filter((r) => r.url.endsWith("/routes/shelter")).pop();
}

function text(document, id) {
  return document.getElementById(id).textContent;
}

test("Gale: la alerta solar exige origen y envía solo campos del contrato", async () => {
  const app = await galeWithShelter();
  const { document, window, mapData } = app;
  const button = document.getElementById("btn-shelter");
  assert.equal(document.getElementById("shelter-card").hidden, false);
  assert.equal(button.disabled, true, "sin origen, deshabilitado");

  clickCell(window, mapData, 0, 0);
  assert.equal(button.disabled, false);
  button.click();
  await settle(window);

  const o = mapData.cells[0];
  assert.equal(shelterPost(app).rawBody, JSON.stringify({
    origin: { latitude: o.latitude, longitude: o.longitude },
    allow_diagonal: true,
    slope_weight: 0.05,
    radiation_weight: 0
  }));
});

test("Gale: dibuja la ruta y muestra distancia, criterio y aviso educativo", async () => {
  const app = await galeWithShelter();
  const { document, window, mapData } = app;
  clickCell(window, mapData, 0, 0);
  setValue(window, document.getElementById("shelter-max-km"), "2.5");
  document.getElementById("btn-shelter").click();
  await settle(window);

  assert.equal(shelterPost(app).body.max_distance_km, 2.5);
  const routePaths = document.querySelectorAll(".leaflet-route-pane path");
  assert.equal(routePaths.length, 2, "línea + marcador de la zona");
  assert.equal(routePaths[0].getAttribute("stroke"), "#ffb347");
  assert.equal(routePaths[0].getAttribute("stroke-dasharray"), "9 6");
  assert.match(document.querySelector(".shelter-label").textContent, /Zona candidata de espera/);

  assert.equal(document.getElementById("shelter-result").hidden, false);
  assert.equal(text(document, "shelter-distance"), "1,20 km (límite 2,5 km)");
  assert.match(text(document, "shelter-criterion"), /slope_deg <= 10/);
  assert.equal(text(document, "shelter-label"), "ÍNDICE DEL PROYECTO");
  assert.equal(text(document, "shelter-candidates"), "64");
  assert.match(text(document, "shelter-note"), /^Planificación educativa/);
  assert.match(document.querySelector(".edu-warning").textContent, /Planificación educativa/);
  assert.equal(document.getElementById("results-card").hidden, false);
  assert.equal(document.getElementById("status").className, "status status-success");
  assert.match(text(document, "status"), /zona candidata de espera: 1,20 km/);
  assert.equal(text(document, "dest-label"), "sin seleccionar");
});

test("Gale: NO_SHELTER es un mensaje informativo y honesto, no un error", async () => {
  const app = await galeWithShelter((body) => [404, fx.noShelterError(body)]);
  const { document, window, mapData } = app;
  clickCell(window, mapData, 0, 0);
  setValue(window, document.getElementById("shelter-max-km"), "0.5");
  document.getElementById("btn-shelter").click();
  await settle(window);

  assert.equal(document.getElementById("status").className, "status status-info");
  assert.doesNotMatch(text(document, "status"), /NO_SHELTER|Error/);
  const empty = document.getElementById("shelter-empty");
  assert.equal(empty.hidden, false);
  assert.match(empty.textContent, /No hay ninguna zona candidata de espera/);
  assert.match(empty.textContent, /0,5 km o menos/);
  assert.match(empty.textContent, /64 celdas que cumplen el criterio/);
  assert.match(empty.textContent, /resultado del modelo, no un fallo/);
  assert.equal(document.getElementById("shelter-result").hidden, true);
  assert.equal(document.querySelectorAll(".leaflet-route-pane path").length, 0);
});

test("Gale: origen fuera de la zona de detalle (respuesta del backend)", async () => {
  const app = await galeWithShelter(() => [400, fx.OUTSIDE_REGION_ERROR]);
  const { document, window, mapData } = app;
  clickCell(window, mapData, 0, 0);
  document.getElementById("btn-shelter").click();
  await settle(window);
  assert.equal(document.getElementById("status").className, "status status-info");
  assert.match(text(document, "shelter-empty"), /fuera de la zona de detalle/);
});

test("Gale: distancia máxima no válida deshabilita la alerta", async () => {
  const app = await galeWithShelter();
  const { document, window, mapData } = app;
  clickCell(window, mapData, 0, 0);
  setValue(window, document.getElementById("shelter-max-km"), "-3");
  assert.equal(document.getElementById("btn-shelter").disabled, true);
  assert.equal(document.getElementById("shelter-max-error").hidden, false);
  setValue(window, document.getElementById("shelter-max-km"), "");
  assert.equal(document.getElementById("btn-shelter").disabled, false);
});

test("vocabulario: nunca «refugio» ni «protección» salvo la negación del backend", async () => {
  const app = await galeWithShelter();
  const { document, window, mapData } = app;
  clickCell(window, mapData, 0, 0);
  document.getElementById("btn-shelter").click();
  await settle(window);
  const note = document.getElementById("shelter-note");
  assert.match(note.textContent, /No es una protección garantizada/);
  const clone = document.body.cloneNode(true);
  clone.querySelector("#shelter-note").remove();
  const all = clone.textContent;
  assert.doesNotMatch(all, /refugio/i);
  assert.doesNotMatch(all, /protecci[oó]n/i);
  assert.doesNotMatch(all, /zona segura|ruta segura|lugar seguro/i);
});

test("sin capa de radiación la alerta solar no aparece", async () => {
  for (const mapData of [fx.molaMap(false), fx.syntheticMap()]) {
    const { document } = await loadApp({ mapData });
    assert.equal(document.getElementById("shelter-card").hidden, true);
    assert.equal(document.getElementById("btn-shelter").disabled, true);
  }
});
