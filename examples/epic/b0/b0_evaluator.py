from typing import Any, Dict
import math


def objective_payload(
    *,
    design_point: Dict[str, Any],
    **kwargs,
) -> Dict[str, float]:
    """
    Placeholder B0 objective based only on tracker geometry.

    The effective lever arm is defined from the spread of the
    four disk z positions around their barycenter.
    """

    z = [
        float(design_point["b0_tracker.z1"]),
        float(design_point["b0_tracker.z2"]),
        float(design_point["b0_tracker.z3"]),
        float(design_point["b0_tracker.z4"]),
    ]

    z_mean = sum(z) / len(z)

    lever_arm = math.sqrt(
        sum((zi - z_mean) ** 2 for zi in z)
    )

    return {
        "lever_arm": float(lever_arm)
    }