"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp } = require("./harness");
const fx = require("./fixtures");

// La capa se dibuja en canvas: se cuentan los rectángulos visibles con getLayerStats().
function shieldingPaths(document) {
  return document.defaultView.MarsMap.getLayerStats().shielding || 0;
}

test("Gale: la capa de apantallamiento existe, empieza apagada y se activa", async () => {
  const mapData = fx.molaMap(true);
  const { document, window } = await loadApp({ mapData });
  assert.ok(document.querySelector(".leaflet-shielding-pane canvas"), "se dibuja en canvas");
  assert.equal(document.querySelectorAll(".leaflet-shielding-pane path").length, 0, "sin SVG");
  const toggle = document.getElementById("shielding-layer-toggle");
  assert.equal(document.getElementById("shielding-layer-label").hidden, false);
  assert.equal(toggle.checked, false);
  assert.equal(shieldingPaths(document), 0, "apagada por defecto");

  toggle.checked = true;
  toggle.dispatchEvent(new window.Event("change"));
  assert.equal(shieldingPaths(document), mapData.cells.length, "una celda por valor");

  toggle.checked = false;
  toggle.dispatchEvent(new window.Event("change"));
  assert.equal(shieldingPaths(document), 0);
});

test("Gale: etiqueta MODELADO, rango invertido (1 − radiation_modeled) en la leyenda", async () => {
  const mapData = fx.molaMap(true);
  const { document, window } = await loadApp({ mapData });
  const badge = document.querySelector('.prov-badge[data-prov="radiation_modeled"]');
  assert.equal(badge.textContent, "MODELADO");
  assert.equal(badge.hidden, false);

  const values = mapData.cells.map((c) => c.radiation_modeled);
  const range = window.MarsMap.getShieldingRange();
  assert.ok(Math.abs(range.min - (1 - Math.max(...values))) < 1e-9);
  assert.ok(Math.abs(range.max - (1 - Math.min(...values))) < 1e-9);

  assert.equal(document.getElementById("shielding-legend-item").hidden, false);
  const legend = document.getElementById("shielding-legend").textContent;
  assert.match(legend, /1 − radiation_modeled/);
  assert.match(legend, /exagera el blindaje/);
  assert.match(document.getElementById("shielding-layer-note").textContent, /no una dosis/);
});

test("sin capa de radiación: ni casilla, ni leyenda, ni rectángulos", async () => {
  for (const mapData of [fx.molaMap(false), fx.syntheticMap()]) {
    const { document, window } = await loadApp({ mapData });
    assert.equal(document.getElementById("shielding-layer-label").hidden, true);
    assert.equal(document.getElementById("shielding-legend-item").hidden, true);
    assert.equal(window.MarsMap.getShieldingRange(), null);
    window.MarsMap.setLayerVisible("shielding", true);
    assert.equal(shieldingPaths(document), 0);
  }
});
