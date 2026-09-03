import numpy as np
from typing import Any, Dict, List
from aid2e.utilities.workflows import JobContext

def dtlz2_both_objectives(x: List[float]) -> Dict[str, float]:
    """Compute both DTLZ2 objectives in one function."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2)
    f2 = (1 + g) * np.sin(x[0] * np.pi / 2)
    return {"f1": float(f1), "f2": float(f2)}

def dtlz2_f1_only(x: List[float]) -> float:
    """Compute only f1 objective of DTLZ2."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2)
    return float(f1)

def dtlz2_f2_only(x: List[float]) -> float:
    """Compute only f2 objective of DTLZ2."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f2 = (1 + g) * np.sin(x[0] * np.pi / 2)
    return float(f2)

def objective_payload(
    *,
    design_point: Dict[str, Any],
    **kwargs,
) -> Dict[str, float]:
    """Compute DTLZ2 objectives for the config-driven objective plan."""
    parameter_names = [
        name for name in design_point if name.startswith("DTLZ2_variables.x")
    ]
    values = [
        design_point[name]
        for name in sorted(
            parameter_names,
            key=lambda key: int(key.rsplit("x", 1)[1]),
        )
    ]
    return dtlz2_both_objectives(values)


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

def evaluate_qualified_both_objectives(context: JobContext) -> Dict[str, float]:
    """Evaluate DTLZ2 objectives from canonical qualified design keys."""
    design_point = context.design_point
    keys = [
        "DTLZ2_variables.x1",
        "DTLZ2_variables.x2",
        "DTLZ2_variables.x3",
        "DTLZ2_variables.x4",
        "DTLZ2_variables.x5",
    ]
    missing = [key for key in keys if key not in design_point]
    if missing:
        raise ValueError(
            "evaluate_qualified_both_objectives: missing design keys "
            f"{missing}; got {list(design_point.keys())}"
        )

    x = [float(design_point[key]) for key in keys]
    objectives = dtlz2_both_objectives(x)
    context.add_log(f"Qualified design point: {x}")
    context.add_log(f"Objectives: {objectives}")
    context.xcom_push("objectives", objectives)
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


def _qualified_design_vector(design_point: Dict[str, float]) -> List[float]:
    """Return DTLZ2 variables from canonical qualified design keys."""
    keys = [
        "DTLZ2_variables.x1",
        "DTLZ2_variables.x2",
        "DTLZ2_variables.x3",
        "DTLZ2_variables.x4",
        "DTLZ2_variables.x5",
    ]
    missing = [key for key in keys if key not in design_point]
    if missing:
        raise ValueError(
            "_qualified_design_vector: missing design keys "
            f"{missing}; got {list(design_point.keys())}"
        )
    return [float(design_point[key]) for key in keys]


def panda_multistep_simreco(context: JobContext, particle: str, eta_point: float, **kwargs) -> Dict[str, float]:
    """Sim/reco PanDA step used by result and dataset multi-step smokes."""
    x = _qualified_design_vector(context.design_point)
    if particle == "pi+":
        xyz = ((x[0] - 0.5) ** 3 + (x[1] - 0.5) ** 3) * float(eta_point)
    elif particle == "kaon+":
        xyz = ((x[0] - 0.5) ** 2 + (x[1] - 0.5) ** 2) * float(eta_point)
    else:
        xyz = 0.1 * float(eta_point)

    result = {"xyz": float(xyz), "particle": particle, "eta_point": float(eta_point)}
    _write_panda_multistep_outputs(result, kwargs)
    return result


def _write_panda_multistep_outputs(result: Dict[str, float], kwargs: Dict[str, object]) -> None:
    output_file_name = kwargs.get("output_file_name") or kwargs.get("output_file")
    if not output_file_name:
        return

    import json
    import os

    with open(os.path.basename(str(output_file_name)), "w", encoding="utf-8") as handle:
        json.dump({"xyz": result["xyz"]}, handle)
        handle.write("\n")


def panda_multistep_ana(
    context: JobContext,
    simreco_results: Dict[str, Dict[str, float]] | None = None,
    input_file_names: List[str] | None = None,
    **kwargs,
) -> Dict[str, float]:
    """PanDA analysis step for result-based or dataset-backed sim/reco outputs."""
    if simreco_results is not None:
        xyz_sum = sum(float(result.get("xyz", 0.0)) for result in simreco_results.values())
        return {"xyz": float(xyz_sum), "n_inputs": len(simreco_results)}

    xyz_sum = 0.0
    input_file_names = input_file_names or []
    for input_file_name in input_file_names:
        import json

        with open(input_file_name, "r") as handle:
            data = json.load(handle)
        xyz_sum += float(data.get("xyz", 0.0))
    return {"xyz": float(xyz_sum), "n_inputs": len(input_file_names)}


def panda_multistep_final(
    context: JobContext,
    ana_result: Dict[str, float] | None = None,
    ana_results: Dict[str, Dict[str, float]] | None = None,
    **kwargs,
) -> Dict[str, float]:
    """Local final step that converts analysis results into objectives."""
    x = _qualified_design_vector(context.design_point)
    base = dtlz2_both_objectives(x)
    if ana_results is not None:
        xyz = sum(float(result.get("xyz", 0.0)) for result in ana_results.values())
    else:
        xyz = float((ana_result or {}).get("xyz", 0.0))
    objectives = {
        "f1": float(base["f1"] + xyz * 0.1),
        "f2": float(base["f2"] + xyz * 0.1),
    }
    context.xcom_push("objectives", objectives)
    return objectives
