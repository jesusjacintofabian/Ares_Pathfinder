/*
 * Interacción con las capas de celdas dibujadas con L.canvas(): clics y hover
 * resueltos por geometría en el canvas de la capa de clics, clics que pasan al
 * mapa fuera de la región, misiones (SVG) por encima de las celdas y casillas.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp, settle, clickCell, hoverCell, hitCanvas, mouseAt } = require("./harness");
const fx = require("./fixtures");

const text = (document, id) => document.getElementById(id).textContent;

test("sintético: un clic en cada celda libre selecciona exactamente esa celda", async () => {
  const mapData = fx.syntheticMap();
  const { document, window } = await loadApp({ mapData });
  for (const cell of mapData.cells.filter((c) => !c.blocked)) {
    document.getElementById("mode-origin").click();
    clickCell(window, mapData, cell.row, cell.col);
    assert.equal(text(document, "origin-label"), "fila " + cell.row + ", col " + cell.col);
  }
});

test("MOLA: un clic en cada celda libre selecciona su centro geográfico", async () => {
  const mapData = fx.molaMap(true);
  const app = await loadApp({ mapData, shelter: (body) => [200, fx.shelterResponse(mapData, body)] });
  const { document, window } = app;
  for (const cell of mapData.cells.filter((c) => !c.blocked)) {
    document.getElementById("mode-origin").click();
    clickCell(window, mapData, cell.row, cell.col);
    document.getElementById("btn-shelter").click();
    await settle(window);
    const body = app.requests.filter((r) => r.url.endsWith("/routes/shelter")).pop().body;
    assert.deepEqual(body.origin, { latitude: cell.latitude, longitude: cell.longitude },
      "celda " + cell.row + "," + cell.col);
  }
});

test("hover: el detalle de celda sigue al ratón y marca el canvas como interactivo", async () => {
  const mapData = fx.molaMap(true);
  const { document, window } = await loadApp({ mapData });
  await hoverCell(window, 0, 1);
  assert.match(text(document, "cell-info"), /^Celda \(0, 1\) · elevación -4400\.0 m/);
  assert.match(text(document, "cell-info"), /apantallamiento 0\.220 \(MODELADO\)/);
  assert.ok(hitCanvas(window).classList.contains("leaflet-interactive"));
  await hoverCell(window, 2, 2);
  assert.match(text(document, "cell-info"), /^Celda \(2, 2\).*BLOQUEADA/);
});

test("celda bloqueada en canvas: se rechaza sin llamar a la API", async () => {
  const mapData = fx.molaMap(false);
  const app = await loadApp({ mapData });
  clickCell(app.window, mapData, 2, 2);
  assert.match(text(app.document, "status"), /bloqueada/);
  assert.equal(text(app.document, "origin-label"), "sin seleccionar");
});

test("MOLA: un clic fuera de la región atraviesa el canvas y elige la malla global", async () => {
  const mapData = fx.molaMap(false);
  const { document, window } = await loadApp({ mapData });
  window.MarsMap.viewMolaRegion();
  // Esquina del mapa: fuera de la región (fitBounds deja 24 px de margen).
  mouseAt(window, hitCanvas(window), "click", 3, 3);
  assert.match(text(document, "origin-label"), /^lat -?\d+\.\d\d°, lon E \d+\.\d\d°$/);
  assert.doesNotMatch(text(document, "origin-label"), /-4\.\d\d°, lon E 137/);
  assert.match(text(document, "status"), /^Origen: lat /);
});

test("misiones (SVG) quedan por encima del canvas: popup y tooltip sin elegir celda", async () => {
  // Región que contiene sitios de Curiosity (Yellowknife Bay, Bradbury Landing).
  const region = { south: -4.75, north: -4.45, west: 137.3, east: 137.6 };
  const mapData = fx.molaMap(false, region);
  const { document, window } = await loadApp({ mapData });
  window.MarsMap.focusMission("curiosity", true);

  const panes = [...document.querySelectorAll(".leaflet-pane")]
    .reduce((acc, p) => Object.assign(acc, { [p.className.match(/leaflet-(\w+)-pane/)[1]]: Number(p.style.zIndex) }), {});
  assert.ok(panes.hit < panes.roverSites && panes.hit < panes.roverRoutes && panes.hit < panes.placeNames,
    "la capa de clics queda por debajo de misiones y topónimos");
  assert.ok(panes.hit > panes.grid && panes.hit > panes.risk, "y por encima de las capas de celdas");

  const site = document.querySelector(".leaflet-roverSites-pane path.leaflet-interactive");
  assert.ok(site, "marcador de sitio en SVG");
  site.dispatchEvent(new window.MouseEvent("click", { bubbles: true, cancelable: true }));
  assert.match(document.querySelector(".leaflet-popup-content").textContent, /Curiosity/);
  assert.equal(text(document, "origin-label"), "sin seleccionar", "no se eligió una celda");

  const route = document.querySelector(".leaflet-roverRoutes-pane path.leaflet-interactive");
  route.dispatchEvent(new window.MouseEvent("mouseover", { bubbles: true }));
  assert.match(document.querySelector(".leaflet-tooltip").textContent, /trayectoria de referencia/);
});

test("casillas: cada capa de celdas se activa y desactiva; los clics siguen sin elevación", async () => {
  const mapData = fx.molaMap(true);
  const { document, window } = await loadApp({ mapData });
  const stats = () => window.MarsMap.getLayerStats();
  const n = mapData.cells.length;
  const box = (layer) => document.querySelector('input[data-layer="' + layer + '"]');
  const toggle = (input, on) => { input.checked = on; input.dispatchEvent(new window.Event("change")); };

  const elevation = document.querySelector('#local-mola-label input[data-layer="elevation"]');
  for (const [layer, input, expected] of [
    ["elevation", elevation, n],
    ["slope", box("slope"), n],
    ["risk", box("risk"), n],
    ["grid", box("grid"), n],
    ["shielding", box("shielding"), n]
  ]) {
    toggle(input, true);
    assert.equal(stats()[layer] >= expected, true, layer + " encendida");
    toggle(input, false);
    assert.equal(stats()[layer], 0, layer + " apagada");
  }
  toggle(box("blocked"), false);
  assert.equal(stats().blocked, 0);
  toggle(box("blocked"), true);
  assert.equal(stats().blocked >= 1, true);

  // Con la elevación apagada, la capa de clics (siempre activa) sigue funcionando.
  assert.equal(stats().hit, n);
  clickCell(window, mapData, 1, 1);
  assert.match(text(document, "origin-label"), /^lat -4\.85°/);
});
