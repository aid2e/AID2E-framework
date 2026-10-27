"""Small, dependency-light objective functions for monitoring demonstrations."""

from __future__ import annotations

import math
from typing import Any


def dtlz2_objective_payload(
    *,
    design_point: dict[str, Any],
    **_: Any,
) -> dict[str, float]:
    """Evaluate the two-objective DTLZ2 function for qualified design keys."""

    parameter_names = sorted(
        (
            name
            for name in design_point
            if name.startswith("DTLZ2_variables.x")
        ),
        key=lambda key: int(key.rsplit("x", 1)[1]),
    )
    if len(parameter_names) < 2:
        raise ValueError("DTLZ2 requires at least two DTLZ2_variables.xN parameters")

    values = [float(design_point[name]) for name in parameter_names]
    g = sum((value - 0.5) ** 2 for value in values[1:])
    angle = values[0] * math.pi / 2.0
    return {
        "f1": (1.0 + g) * math.cos(angle),
        "f2": (1.0 + g) * math.sin(angle),
    }
