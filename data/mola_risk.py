"""Educational slope-only risk proxy for MOLA routing grids."""

import math

RISK_SCALE_SLOPE_DEG = 20.0
RISK_MODEL = {
    "name": "MOLA slope proxy",
    "method": "min(slope_deg / 20, 1)",
    "slope_scale_deg": RISK_SCALE_SLOPE_DEG,
    "interpretation": (
        "Educational topographic indicator derived only from slope; not a hazard "
        "probability or validated safety assessment."
    ),
}


def slope_risk(slope_deg: float) -> float:
    """Map MOLA slope to a normalized proxy; this is not a hazard probability."""
    if not math.isfinite(slope_deg) or slope_deg < 0:
        raise ValueError("La pendiente debe ser finita y no negativa.")
    return min(slope_deg / RISK_SCALE_SLOPE_DEG, 1.0)
