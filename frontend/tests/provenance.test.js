"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { loadApp } = require("./harness");
const fx = require("./fixtures");

function badge(document, layer) {
  return document.querySelector('.prov-badge[data-prov="' + layer + '"]');
}

test("MOLA: cada capa muestra la etiqueta que publica provenance", async () => {
  const mapData = fx.molaMap(true);
  const { document } = await loadApp({ mapData });
  const expected = {
    elevation_m: "MEDIDO",
    slope_deg: "DERIVADO",
    risk: "DERIVADO",
    blocked: "ÍNDICE DEL PROYECTO",
    total_cost: "ÍNDICE DEL PROYECTO"
  };
  Object.keys(expected).forEach((layer) => {
    const b = badge(document, layer);
    assert.equal(b.hidden, false, layer + " visible");
    assert.equal(b.textContent, expected[layer]);
  });
  assert.match(badge(document, "elevation_m").title, /Fergason, Hare y Laura/);
  assert.match(badge(document, "elevation_m").title, /No entra directamente al costo/);
  assert.match(badge(document, "slope_deg").title, /Entra directamente al costo/);
  assert.ok(badge(document, "risk").classList.contains("prov-derived"));
  assert.ok(badge(document, "blocked").classList.contains("prov-index"));
  assert.equal(document.getElementById("prov-note").hidden, false);
  // El texto de la capa de riesgo sigue intacto al lado de su etiqueta.
  assert.equal(document.getElementById("risk-layer-text").textContent, "Riesgo topográfico (proxy)");
});

test("sintético: sin provenance no aparece ninguna etiqueta", async () => {
  const { document } = await loadApp({ mapData: fx.syntheticMap() });
  document.querySelectorAll(".prov-badge[data-prov]").forEach((b) => {
    assert.equal(b.hidden, true);
    assert.equal(b.textContent, "");
  });
  assert.equal(document.getElementById("prov-note").hidden, true);
  assert.equal(document.getElementById("risk-layer-text").textContent, "Riesgo (simulado)");
});

test("una etiqueta desconocida se muestra tal cual, sin interpretar HTML", async () => {
  const mapData = fx.molaMap(false);
  mapData.provenance.slope_deg = { label: "<b>NUEVA</b>", source: "x", in_cost: true };
  const { document } = await loadApp({ mapData });
  const b = badge(document, "slope_deg");
  assert.equal(b.textContent, "<b>NUEVA</b>");
  assert.equal(b.querySelector("b"), null);
  assert.ok(b.classList.contains("prov-other"));
});
