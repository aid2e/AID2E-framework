"""Evaluate DTLZ2 through Python callables, CLI arguments, or a design JSON file."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from aid2e.utilities.workflows import JobContext

def dtlz2_both_objectives(x: List[float]) -> Dict[str, float]:
    """Compute both DTLZ2 objectives in one function."""
    g = sum((value - 0.5) ** 2 for value in x[1:])
    f1 = (1 + g) * math.cos(x[0] * math.pi / 2)
    f2 = (1 + g) * math.sin(x[0] * math.pi / 2)
    return {"f1": float(f1), "f2": float(f2)}

def dtlz2_f1_only(x: List[float]) -> float:
    """Compute only f1 objective of DTLZ2."""
    g = sum((value - 0.5) ** 2 for value in x[1:])
    f1 = (1 + g) * math.cos(x[0] * math.pi / 2)
    return float(f1)

def dtlz2_f2_only(x: List[float]) -> float:
    """Compute only f2 objective of DTLZ2."""
    g = sum((value - 0.5) ** 2 for value in x[1:])
    f2 = (1 + g) * math.sin(x[0] * math.pi / 2)
    return float(f2)

def design_vector(design_point: Dict[str, Any], prefix: str = "DTLZ2_variables.") -> List[float]:
    """Return all DTLZ2 variables in numeric order (x1, ..., x10)."""
    names = sorted(
        (name for name in design_point if name.startswith(f"{prefix}x")),
        key=lambda name: int(name.rsplit("x", 1)[1]),
    )
    if len(names) < 2 or names != [f"{prefix}x{i}" for i in range(1, len(names) + 1)]:
        raise ValueError("DTLZ2 requires consecutive variables x1 through xN, with N >= 2")
    return [float(design_point[name]) for name in names]


def objective_payload(
    *,
    design_point: Dict[str, Any],
    **kwargs,
) -> Dict[str, float]:
    """Compute DTLZ2 objectives for the config-driven objective plan."""
    return dtlz2_both_objectives(design_vector(design_point))


def prepare_objective_inputs(*, design_point: Dict[str, Any], **kwargs) -> Dict[str, List[float]]:
    """Pass ordered design values to the dependent objective step."""
    return {"values": design_vector(design_point)}


def evaluate_prepared_objective(*, inputs: Dict[str, Any], **kwargs) -> Dict[str, float]:
    """Compute f2 from the prepare step's output."""
    return {"f2": dtlz2_f2_only(inputs["prepare"]["values"])}


def evaluate_both_objectives_wrapper(context: JobContext) -> Dict[str, float]:
    """Wrapper to evaluate both objectives from JobContext."""
    design_point = context.design_point
    x = design_vector(design_point, prefix="")
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
    x = design_vector(design_point)
    objectives = dtlz2_both_objectives(x)
    context.add_log(f"Qualified design point: {x}")
    context.add_log(f"Objectives: {objectives}")
    context.xcom_push("objectives", objectives)
    return objectives

def evaluate_f1_wrapper(context: JobContext) -> float:
    """Wrapper to evaluate f1 from JobContext."""
    design_point = context.design_point
    x = design_vector(design_point, prefix="")
    f1 = dtlz2_f1_only(x)
    context.add_log(f"Design point: {x}")
    context.add_log(f"f1 = {f1}")
    context.xcom_push("f1", f1)
    return f1

def evaluate_f2_wrapper(context: JobContext) -> float:
    """Wrapper to evaluate f2 from JobContext."""
    design_point = context.design_point
    x = design_vector(design_point, prefix="")
    f2 = dtlz2_f2_only(x)
    context.add_log(f"Design point: {x}")
    context.add_log(f"f2 = {f2}")
    context.xcom_push("f2", f2)
    return f2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--design", "--design_params_file", type=Path)
    inputs.add_argument("--x1", type=float)
    for index in range(2, 11):
        parser.add_argument(f"--x{index}", type=float)
    parser.add_argument("--output", "--output_file", type=Path, required=True)
    parser.add_argument("--label", type=str, default="slurm-dtlz2")
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--repeat", type=int, default=2)
    args = parser.parse_args()

    values = [getattr(args, f"x{index}") for index in range(1, 11)]
    if args.design:
        if any(value is not None for value in values):
            parser.error("Use either --design or --x1 through --x10, not both")
        design = json.loads(args.design.read_text(encoding="utf-8"))
        values = design_vector(design)
        print(f"[{args.label}] design file: {args.design}", flush=True)
    elif any(value is None for value in values):
        parser.error("Direct argument mode requires --x1 through --x10")

    for step in range(args.repeat):
        print(f"[{args.label}] progress {step + 1}/{args.repeat}", flush=True)
        print(f"[{args.label}] stderr heartbeat {step + 1}", file=sys.stderr, flush=True)
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    payload = dtlz2_both_objectives(values)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
