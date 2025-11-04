# app/confidence.py
# Estima "confidence" si el modelo no lo entrega.

from typing import Dict

def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def estimate_confidence(data: Dict, present_fields=("summary", "findings", "risk_level")) -> float:
    """
    Heurística simple si el modelo no entregó confidence. Basado en completitud
    y consistencia básica de la salida estructurada.
    """
    base = 0.4
    completeness = sum(1 for k in present_fields if data.get(k)) / float(len(present_fields))
    richness = 0.0
    findings = data.get("findings")
    if isinstance(findings, list):
        n = len(findings) or 1
        richness = min(0.3, n * 0.05)
    risk_ok = 0.1 if data.get("risk_level") in {"bajo", "moderado", "alto"} else 0.0
    return clamp(base + 0.2 * completeness + richness + risk_ok)
