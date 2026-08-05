"""Small Python callable used to verify Slurm python-evaluator rejection."""

from __future__ import annotations

from typing import Any, Dict


def compute_with_context(context: Any, scale: float = 1.0) -> Dict[str, float]:
    """Return a tiny deterministic payload from design-point context."""
    design_point = getattr(context, "design_point", {}) or {}
    base = float(design_point.get("DTLZ2_variables.x1", 0.0))
    return {"f1": base * scale, "f2": (1.0 - base) * scale}
