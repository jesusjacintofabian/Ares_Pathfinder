"""Metadata of the MODELLED radiation layer (relative index from the sky-view factor).

The layer is a hypothesis of the project author, not a measurement per cell:

    radiation_modeled = sky_view_factor          (0..1, relative, dimensionless)

The anchor is the surface dose measured by RAD on Curiosity in Gale crater
(Hassler et al., 2014). Only what the published abstract states is cited as
fact; specific dose figures quoted in the project brief have NOT been checked
against the published article and are kept as metadata flagged accordingly.
They are not used in any calculation.
"""

from __future__ import annotations

from typing import Any

RADIATION_LABEL = "MODELADO"
RADIATION_INDEX_FORMULA = "radiation_modeled = sky_view_factor"
UNVERIFIED_STATUS = "no cotejado con el artículo publicado"

RAD_ANCHOR: dict[str, Any] = {
    "instrument": "RAD (Radiation Assessment Detector), rover Curiosity (MSL), cráter Gale",
    "citation": (
        "Hassler et al. (2014), Mars' Surface Radiation Environment Measured with the "
        "Mars Science Laboratory's Curiosity Rover. Science 343 (6169), 1244797"
    ),
    "doi": "10.1126/science.1244797",
    "statement": (
        "Según el resumen publicado, RAD midió en la superficie de Gale la dosis "
        "absorbida y la dosis equivalente debidas a rayos cósmicos galácticos (GCR) y "
        "a partículas energéticas solares (SEP) durante unos 300 días."
    ),
    "role": (
        "Punto ancla del modelo: la medición corresponde al lugar del rover. El índice "
        "solo describe cómo varía, de forma relativa, la fracción de cielo visible entre "
        "celdas; no convierte la medición en una dosis por celda."
    ),
    "unverified_values": {
        "values": (
            "180 a 225 µGy/día (rango), 0,21 mGy/día (media) y pico cercano a 260 µGy/día "
            "durante un evento solar, según el encargo del proyecto"
        ),
        "verification_status": UNVERIFIED_STATUS,
        "used_in_calculation": False,
    },
}

ASSUMPTIONS = (
    "La radiación que llega a la superficie se trata como isótropa en el cielo visible.",
    "El relieve que tapa el cielo bloquea por completo la radiación de esas direcciones.",
    "Más cielo visible implica más exposición relativa (hipótesis del autor).",
    "El horizonte se busca hasta un radio fijo, con muestreo al píxel más cercano y "
    "corrección por la curvatura de una esfera.",
)

LIMITATIONS = (
    "No modela la atenuación atmosférica con el ángulo cenital: la radiación que llega "
    "en ángulo bajo ya está muy atenuada, así que el índice exagera el blindaje del relieve.",
    "No modela la radiación secundaria emitida por el propio terreno (neutrones de albedo).",
    "No modela la variación de la columna atmosférica con la elevación, que probablemente "
    "es el factor espacial dominante dentro de la ventana (unos 5 km de desnivel).",
    "No modela la variación temporal (ciclo diurno de presión, ciclo solar, eventos SEP).",
    "La resolución (DEM de 200 m, celdas de 600 m) no capta relieve menor, como "
    "crestas de 1 a 2 m.",
    "No es una dosis, ni una medición por celda, ni una evaluación de seguridad.",
)


def radiation_metadata(
    *,
    horizon_radius_m: float,
    azimuths: int,
    native_cell_size_m: float,
    aggregate: int,
    body_radius_m: float,
    truncated_cells: int,
) -> dict[str, Any]:
    """`radiation_model` block stored in the processed grid JSON and served by the API."""
    aggregation = (
        f"media de los {aggregate} × {aggregate} píxeles de 200 m de cada celda"
        if aggregate > 1 else "sin agregar"
    )
    return {
        "label": RADIATION_LABEL,
        "name": "Índice relativo de radiación por cielo visible",
        "index_formula": RADIATION_INDEX_FORMULA,
        "range": [0.0, 1.0],
        "unit": "adimensional",
        "fields": {
            "sky_view_factor": (
                "Fracción del ángulo sólido del cielo no tapada por el relieve: "
                "media por acimut de 1 − sin(max(H, 0)), con H el ángulo de horizonte."
            ),
            "radiation_modeled": "Índice relativo 0–1; en esta versión es igual a sky_view_factor.",
        },
        "method": (
            f"Ángulo de horizonte en {azimuths} acimuts hasta {horizon_radius_m / 1000:g} km "
            f"sobre el DEM a resolución nativa (~{native_cell_size_m:.0f} m), con corrección "
            f"por curvatura (radio {body_radius_m:.0f} m); agregación: {aggregation}."
        ),
        "horizon_radius_m": horizon_radius_m,
        "azimuths": azimuths,
        "truncated_cells": truncated_cells,
        "anchor": RAD_ANCHOR,
        "assumptions": list(ASSUMPTIONS),
        "limitations": list(LIMITATIONS),
        "interpretation": (
            "Capa MODELADA. Plano abierto = 1; un pozo o el pie de un escarpe dan menos. "
            "Solo compara celdas entre sí; no es una medición celda por celda ni una dosis."
        ),
    }
