from __future__ import annotations
from typing import Dict
import numpy as np

def eval_dtlz2(design: Dict[str, float]) -> Dict[str, float]:
    # placeholder for DTLZ2 evaluation, to be replaced by real computations
    xs = np.array([design[k] for k in sorted(design.keys())], dtype=float)
    m = 2
    g = np.sum((xs[m-1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(xs[0] * np.pi / 2.0)
    f2 = (1 + g) * np.sin(xs[0] * np.pi / 2.0)
    return {"f1": float(f1), "f2": float(f2)}

def eval_epic_b0(design: Dict[str, float]) -> Dict[str, float]:
    # placeholder for B0 resolution evaluation, to be replaced by real computations
    z1 = float(design["b0_tracker.layer1_z_cm"])
    z2 = float(design["b0_tracker.layer2_z_cm"])
    z3 = float(design["b0_tracker.layer3_z_cm"])
    z4 = float(design["b0_tracker.layer4_z_cm"])
    d12, d23, d34 = (z2-z1), (z3-z2), (z4-z3)
    lever = (z4 - z1)
    nonu = float(np.std([d12, d23, d34]))
    toy_res = float(lever - 10.0 * nonu)
    return {"b0_resolution": toy_res}