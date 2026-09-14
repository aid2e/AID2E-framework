import argparse
import json
import numpy as np
import sys
import time
from pathlib import Path
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


def prepare_objective_inputs(
    *,
    design_point: Dict[str, Any],
    **kwargs,
) -> Dict[str, List[float]]:
    """Prepare ordered DTLZ2 values for a downstream objective step."""
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
    return {"values": values}


def evaluate_prepared_objective(
    *,
    inputs: Dict[str, Any],
    **kwargs,
) -> Dict[str, float]:
    """Compute f2 from the output of the prepare objective step."""
    return {"f2": dtlz2_f2_only(inputs["prepare"]["values"])}


def parse_args() -> argparse.Namespace:
    """Parse objective-script, Slurm design-file, or direct-argument input."""
    parser = argparse.ArgumentParser(
        description="Compute DTLZ2 objectives from design JSON or direct CLI arguments."
    )
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "--design_params_file",
        "--design",
        dest="design_params_file",
        type=Path,
    )
    input_group.add_argument("--x1", type=float)
    for index in range(2, 11):
        parser.add_argument(f"--x{index}", type=float)
    parser.add_argument(
        "--output_file",
        "--output",
        dest="output_file",
        type=Path,
        required=True,
    )
    parser.add_argument("--label", type=str, default="slurm-dtlz2")
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--repeat", type=int, default=2)
    return parser.parse_args()


def load_design(path: Path) -> Dict[str, Any]:
    """Load and validate a framework-generated DTLZ2 design JSON file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    parameter_names = [
        name
        for name in payload
        if name.startswith("DTLZ2_variables.x")
        and name.rsplit("x", 1)[1].isdigit()
    ]
    if len(parameter_names) < 2:
        raise ValueError(
            f"Design file {path} must contain at least two DTLZ2 variables"
        )
    return payload


def load_direct_arguments(args: argparse.Namespace) -> Dict[str, float]:
    """Return a design point from the direct ``--x1`` through ``--x10`` form."""
    missing = [
        f"--x{index}"
        for index in range(1, 11)
        if getattr(args, f"x{index}") is None
    ]
    if missing:
        raise ValueError(
            "Direct argument mode requires all DTLZ2 parameters; missing "
            + ", ".join(missing)
        )
    return {
        f"DTLZ2_variables.x{index}": getattr(args, f"x{index}")
        for index in range(1, 11)
    }


def main() -> int:
    """Run the evaluator through the objective-script or Slurm interface."""
    args = parse_args()
    direct_values = [getattr(args, f"x{index}") for index in range(1, 11)]
    if args.design_params_file and any(value is not None for value in direct_values):
        raise ValueError(
            "Use either --design/--design_params_file or direct --x1 through "
            "--x10 arguments, not both"
        )
    design_point = (
        load_design(args.design_params_file)
        if args.design_params_file
        else load_direct_arguments(args)
    )

    if args.design_params_file:
        print(f"[{args.label}] design file: {args.design_params_file}", flush=True)
    else:
        print(f"[{args.label}] direct design arguments", flush=True)
    for step in range(args.repeat):
        print(f"[{args.label}] progress {step + 1}/{args.repeat}", flush=True)
        print(
            f"[{args.label}] stderr heartbeat {step + 1}",
            file=sys.stderr,
            flush=True,
        )
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    payload = objective_payload(design_point=design_point)
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return 0


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


if __name__ == "__main__":
    raise SystemExit(main())
