"""PanDA/iDDS-specific DTLZ2 evaluator stages."""

from __future__ import annotations

from typing import Any, Dict, List

from aid2e.utilities.workflows import JobContext
from examples.dtlz2.dtlz2_evaluator import design_vector, dtlz2_both_objectives


def panda_stage_simreco(context: JobContext, particle: str, eta_point: float, **kwargs) -> Dict[str, Any]:
    """Sim/reco PanDA stage used by result and dataset smoke tests."""
    x = design_vector(context.design_point)
    if particle == "pi+":
        xyz = ((x[0] - 0.5) ** 3 + (x[1] - 0.5) ** 3) * float(eta_point)
    elif particle == "kaon+":
        xyz = ((x[0] - 0.5) ** 2 + (x[1] - 0.5) ** 2) * float(eta_point)
    else:
        xyz = 0.1 * float(eta_point)

    result = {"xyz": float(xyz), "particle": particle, "eta_point": float(eta_point)}
    result["message"] = (
        f"simreco produced xyz={result['xyz']} for particle={particle} "
        f"eta_point={float(eta_point)}"
    )
    _write_panda_stage_outputs(result, kwargs)
    return result


def _write_panda_stage_outputs(result: Dict[str, Any], kwargs: Dict[str, object]) -> None:
    output_file_name = kwargs.get("output_file_name") or kwargs.get("output_file")
    if not output_file_name:
        return

    import json
    import os

    with open(os.path.basename(str(output_file_name)), "w", encoding="utf-8") as handle:
        json.dump(
            {
                "xyz": result["xyz"],
                "message": result["message"],
                "particle": result["particle"],
                "eta_point": result["eta_point"],
            },
            handle,
        )
        handle.write("\n")


def panda_stage_ana(
    context: JobContext,
    simreco_results: Dict[str, Dict[str, float]] | None = None,
    input_file_names: List[str] | None = None,
    **kwargs,
) -> Dict[str, float]:
    """PanDA analysis stage for result-based or dataset-backed sim/reco outputs."""
    if simreco_results is not None:
        xyz_sum = sum(float(result.get("xyz", 0.0)) for result in simreco_results.values())
        return {"xyz": float(xyz_sum), "n_inputs": len(simreco_results)}

    xyz_sum = 0.0
    input_file_names = input_file_names or []
    for input_file_name in input_file_names:
        import json

        with open(input_file_name, "r") as handle:
            data = json.load(handle)
        message = data.get("message", "")
        if message:
            print(f"ana read from {input_file_name}: {message}")
        xyz_sum += float(data.get("xyz", 0.0))
    return {"xyz": float(xyz_sum), "n_inputs": len(input_file_names)}


def panda_stage_final(
    context: JobContext,
    ana_result: Dict[str, float] | None = None,
    ana_results: Dict[str, Dict[str, float]] | None = None,
    **kwargs,
) -> Dict[str, float]:
    """Local final stage that converts analysis results into objectives."""
    x = design_vector(context.design_point)
    base = dtlz2_both_objectives(x)
    if ana_results is not None:
        xyz = sum(float(result.get("xyz not none ana-result", 0.0)) for result in ana_results.values())
    else:
        xyz = float((ana_result or {}).get("xyz", 0.0))
    objectives = {
        "f1": float(base["f1"] + xyz * 0.1),
        "f2": float(base["f2"] + xyz * 0.1),
    }
    context.xcom_push("objectives", objectives)
    return objectives
