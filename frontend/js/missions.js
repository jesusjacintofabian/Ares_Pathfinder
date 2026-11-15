/*
 * Catálogo de imágenes reales de Marte desde NASA Image and Video Library.
 * La galería es visual e independiente de la cuadrícula MOLA y del algoritmo A*.
 */
(function () {
  "use strict";

  var API = "https://images-api.nasa.gov/search";
  var missions = {
    perseverance: { query: "Mars Perseverance rover surface", label: "Perseverance" },
    curiosity: { query: "Mars Curiosity rover Gale crater", label: "Curiosity" },
    opportunity: { query: "Mars Opportunity rover Meridiani Planum", label: "Opportunity" },
    spirit: { query: "Mars Spirit rover Gusev crater", label: "Spirit" },
    zhurong: { query: "Zhurong rover Mars Utopia Planitia", label: "Zhurong" },
    hirise: { query: "Mars HiRISE Mars Reconnaissance Orbiter", label: "HiRISE / MRO" },
    themis: { query: "Mars THEMIS Mars Odyssey", label: "THEMIS / Mars Odyssey" },
    ctx: { query: "Mars CTX Context Camera Mars Reconnaissance Orbiter", label: "CTX / MRO" },
    hrsc: { query: "Mars Express HRSC camera", label: "HRSC / Mars Express" }
  };

  function byId(id) { return document.getElementById(id); }

  function setStatus(message) {
    var node = byId("mission-status");
    if (node) { node.textContent = message; }
  }

  function makeCard(item, missionLabel) {
    var data = item.data && item.data[0] ? item.data[0] : {};
    var preview = item.links && item.links.find(function (link) {
      return link.render === "image" || link.rel === "preview";
    });
    if (!preview || !preview.href) { return null; }

    var article = document.createElement("article");
    article.className = "mission-item";
    var link = document.createElement("a");
    link.href = preview.href;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.title = "Abrir imagen del catálogo NASA";
    var image = document.createElement("img");
    image.src = preview.href;
    image.alt = data.title || ("Imagen de Marte: " + missionLabel);
    image.loading = "lazy";
    image.referrerPolicy = "no-referrer";
    image.onerror = function () { article.hidden = true; };
    var title = document.createElement("span");
    title.className = "mission-item-title";
    title.textContent = data.title || "Imagen de Marte";
    var date = document.createElement("span");
    date.className = "mission-item-date";
    var dateText = data.date_created ? data.date_created.slice(0, 10) : "Fecha no indicada";
    date.textContent = missionLabel + " · " + dateText;
    link.appendChild(image);
    link.appendChild(title);
    article.appendChild(link);
    article.appendChild(date);
    return article;
  }

  function loadMission() {
    var select = byId("mission-select");
    var gallery = byId("mission-gallery");
    var button = byId("btn-load-mission");
    if (!select || !gallery || !button) { return; }

    var mission = missions[select.value] || missions.perseverance;
    if (window.MarsMap) {
      if (["hirise", "themis", "ctx", "hrsc"].indexOf(select.value) !== -1) {
        var instrumentToggle = document.querySelector('[data-instrument-layer="' + select.value + '"]');
        MarsMap.focusInstrument(select.value, Boolean(instrumentToggle && instrumentToggle.checked));
      } else {
        var roverToggle = document.querySelector('[data-mission-layer="' + select.value + '"]');
        MarsMap.focusMission(select.value, Boolean(roverToggle && roverToggle.checked));
      }
    }
    gallery.replaceChildren();
    button.disabled = true;
    setStatus("Consultando el catálogo público de NASA para " + mission.label + "…");

    var params = new URLSearchParams({ q: mission.query, media_type: "image", page_size: "12" });
    fetch(API + "?" + params.toString(), { headers: { Accept: "application/json" } })
      .then(function (response) {
        if (!response.ok) { throw new Error("NASA respondió con HTTP " + response.status); }
        return response.json();
      })
      .then(function (payload) {
        var items = payload && payload.collection && Array.isArray(payload.collection.items)
          ? payload.collection.items : [];
        var added = 0;
        items.forEach(function (item) {
          var card = makeCard(item, mission.label);
          if (card) { gallery.appendChild(card); added += 1; }
        });
        if (!added) {
          setStatus("No se encontraron imágenes con vista previa para esta búsqueda. Prueba otra misión o abre el catálogo NASA.");
        } else {
          setStatus(added + " imágenes encontradas en NASA Image and Video Library. Selecciona una imagen para abrirla en tamaño completo. Créditos: NASA / JPL-Caltech y equipos de las misiones, según cada registro.");
        }
      })
      .catch(function (error) {
        setStatus("No se pudo consultar NASA: " + error.message + ". Verifica tu conexión o abre images.nasa.gov.");
      })
      .finally(function () { button.disabled = false; });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var button = byId("btn-load-mission");
    if (button) { button.addEventListener("click", loadMission); }
    var nextPointButton = byId("btn-next-exploration-point");
    if (nextPointButton) { nextPointButton.addEventListener("click", function () {
      var result = window.MarsMap && window.MarsMap.goToNextExplorationPoint();
      var status = byId("next-point-status");
      if (status) { status.textContent = result ? "Siguiente punto: " + result + ". El mapa se ha centrado en esta ubicación." : "Activa al menos una capa de rover o instrumento para recorrer sus puntos."; }
    }); }
    var select = byId("mission-select");
    if (select) { select.addEventListener("change", function () {
      var id = select.value;
      var mission = missions[id] || missions.perseverance;
      var toggle = document.querySelector('[data-mission-layer="' + id + '"]');
      if (toggle && window.MarsMap) {
        MarsMap.focusMission(id, toggle.checked);
        setStatus(toggle.checked ? "Mapa centrado en " + mission.label + ". Trayectoria y puntos visibles." : "Mapa centrado en " + mission.label + ". Capa desactivada: no se muestran puntos ni trayectoria. Activa su casilla para verlos.");
      } else if (window.MarsMap && ["hirise", "themis", "ctx", "hrsc"].indexOf(id) !== -1) {
        var instrumentToggle = document.querySelector('[data-instrument-layer="' + id + '"]');
        MarsMap.focusInstrument(id, Boolean(instrumentToggle && instrumentToggle.checked));
        setStatus(instrumentToggle && instrumentToggle.checked ? "Mapa centrado en una zona de referencia de " + mission.label + "." : "Mapa centrado en una zona de referencia de " + mission.label + ". Capa desactivada: no se muestran puntos. Activa su casilla para verlos.");
      } else {
        setStatus("Misión seleccionada: " + mission.label + ". Pulsa «Cargar imágenes NASA».");
      }
    }); }
    document.querySelectorAll("[data-mission-layer]").forEach(function(toggle) {
      toggle.addEventListener("change", function() {
        if (window.MarsMap) { MarsMap.setMissionVisible(toggle.getAttribute("data-mission-layer"), toggle.checked); }
      });
    });
    document.querySelectorAll("[data-instrument-layer]").forEach(function(toggle) {
      toggle.addEventListener("change", function() {
        if (window.MarsMap) { MarsMap.setInstrumentVisible(toggle.getAttribute("data-instrument-layer"), toggle.checked); }
      });
    });
  });
})();
