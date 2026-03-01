import numpy as np
from typing import Dict, List
from aid2e.utilities.workflows import JobContext

def dtlz2_both_objectives(x: List[float]) -> Dict[str, float]:
    """Compute both DTLZ2 objectives in one function."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.cos(x[1] * np.pi / 2)
    f2 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.sin(x[1] * np.pi / 2)
    return {"f1": float(f1), "f2": float(f2)}

def dtlz2_f1_only(x: List[float]) -> float:
    """Compute only f1 objective of DTLZ2."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.cos(x[1] * np.pi / 2)
    return float(f1)

def dtlz2_f2_only(x: List[float]) -> float:
    """Compute only f2 objective of DTLZ2."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f2 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.sin(x[1] * np.pi / 2)
    return float(f2)

def evaluate_both_objectives_wrapper(context: JobContext) -> Dict[str, float]:
    """Wrapper to evaluate both objectives from JobContext."""
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    objectives = dtlz2_both_objectives(x)
    context.add_log(f"Design point: {x}")
    context.add_log(f"Objectives: {objectives}")
    context.xcom_push("objectives", objectives)
    # Ensure both objectives are present
    required_keys = {"f1", "f2"}
    missing = required_keys - objectives.keys()
    if missing:
        raise ValueError(f"evaluate_both_objectives_wrapper: Missing objectives {missing} in result dict. Got: {objectives}")
    return objectives

def evaluate_f1_wrapper(context: JobContext) -> float:
    """Wrapper to evaluate f1 from JobContext."""
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    f1 = dtlz2_f1_only(x)
    context.add_log(f"Design point: {x}")
    context.add_log(f"f1 = {f1}")
    context.xcom_push("f1", f1)
    return f1

def evaluate_f2_wrapper(context: JobContext) -> float:
    """Wrapper to evaluate f2 from JobContext."""
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    f2 = dtlz2_f2_only(x)
    context.add_log(f"Design point: {x}")
    context.add_log(f"f2 = {f2}")
    context.xcom_push("f2", f2)
    return f2
