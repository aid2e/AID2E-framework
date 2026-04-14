"""Run optimization from one full YAML/JSON configuration file.

This example consumes a single full configuration in the same style as
``examples/configurations/dtlz2_ax_panda_multiple.yml`` with sections for
problem, optimization, scheduler, and workflows.

Usage:
    python examples/optimizers/run_optimizer_with_joblib.py \
        examples/optimizers/dtlz2_ax_joblib_full.yml
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from aid2e.utilities.configurations import (
    build_optimizer_from_config,
    build_workflow_executor_from_config,
    infer_optimizer_backend,
    load_optimization_config,
    load_problem_config,
    load_raw_config,
    load_scheduler_config,
    load_workflow_config,
    validate_objective_alignment,
)


def _ensure_repo_root_on_path() -> None:
    """Ensure repository root is importable for workflow callable resolution.

    This allows module paths such as ``examples.evaluators.dtlz2`` to resolve
    even when the script is launched from ``examples/optimizers``.
    """
    repo_root = Path(__file__).resolve().parents[2]
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


def _resolve_results_path(config_path: Path, raw_config: Dict[str, Any]) -> Path:
    """Resolve output results file location for optimization payload.

    Args:
        config_path: Path to the loaded config file.
        raw_config: Raw top-level config dictionary.

    Returns:
        Resolved path where trial results should be written.
    """
    candidate = raw_config.get("results_file")
    if candidate is None:
        metadata = raw_config.get("metadata") or {}
        candidate = metadata.get("results_file")

    if not candidate:
        stem = config_path.stem
        candidate = f"examples/optimizers/output/{stem}_results.json"

    return Path(candidate).resolve()


def _infer_batch_size(optimizer: Any, optimization_cfg: Any) -> int:
    """Infer evaluation batch size from optimizer/config settings.

    Args:
        optimizer: Concrete optimizer instance.
        optimization_cfg: Parsed optimization configuration.

    Returns:
        Positive batch size integer.
    """
    value = getattr(getattr(optimizer, "config", None), "batch_size", None)
    if value is None:
        value = getattr(getattr(optimizer, "config", None), "pop_size", None)
    if value is None:
        value = optimization_cfg.parallel_evaluations
    if value is None:
        value = 1
    return max(1, int(value))


def _print_iteration_row(
    trial_number: int,
    iteration_number: int,
    design_point: Dict[str, Any],
    objectives: Dict[str, float],
    phase: str,
) -> None:
    """Print one tabular iteration row.

    Args:
        trial_number: One-based trial number.
        iteration_number: One-based loop index.
        design_point: Candidate parameters.
        objectives: Evaluated objective values.
        phase: Human-readable phase label.
    """
    display_point = _with_short_parameter_aliases(design_point)
    x1 = float(display_point.get("x1", 0.0))
    x2 = float(display_point.get("x2", 0.0))
    x3 = float(display_point.get("x3", 0.0))
    f1 = float(objectives.get("f1", 0.0))
    f2 = float(objectives.get("f2", 0.0))
    print(
        f"{trial_number:<6} {iteration_number:<6} "
        f"{x1:<10.4f} {x2:<10.4f} {x3:<10.4f} "
        f"{f1:<12.6f} {f2:<12.6f} {phase:<15}"
    )


def _with_short_parameter_aliases(design_point: Dict[str, Any]) -> Dict[str, Any]:
    """Add short aliases (for example ``x1``) for grouped parameter keys.

    Args:
        design_point: Original optimizer parameter dictionary.

    Returns:
        Copy of the input dictionary with added aliases for keys that use
        separators like ``group.x1`` or ``group__x1``.
    """
    alias_point = dict(design_point)
    for key, value in list(design_point.items()):
        if "." in key:
            short = key.split(".")[-1]
            alias_point.setdefault(short, value)
        if "__" in key:
            short = key.split("__")[-1]
            alias_point.setdefault(short, value)
    return alias_point


def run_from_full_config(config_file: str, workflow_name: Optional[str] = None) -> int:
    """Run a full optimization loop from one complete configuration file.

    Args:
        config_file: Path to full YAML/JSON config.
        workflow_name: Optional workflow selector for multi-workflow config.

    Returns:
        Process exit code.
    """
    _ensure_repo_root_on_path()
    config_path = Path(config_file).resolve()
    raw = load_raw_config(str(config_path))

    problem_cfg = load_problem_config(str(config_path))
    optimization_cfg = load_optimization_config(str(config_path))
    scheduler_cfg = load_scheduler_config(str(config_path))
    workflows_cfg = load_workflow_config(str(config_path))

    if workflows_cfg is None:
        raise ValueError("Config must include 'workflows' or 'workflow' section")

    validate_objective_alignment(problem_cfg, optimization_cfg)
    backend = infer_optimizer_backend(optimization_cfg)
    optimizer = build_optimizer_from_config(problem_cfg, optimization_cfg, backend=backend)

    executor = build_workflow_executor_from_config(
        workflows_cfg,
        scheduler_cfg=scheduler_cfg,
        workflow_name=workflow_name,
        base_output_dir=str(Path("/tmp") / "aid2e" / "optimizer_examples"),
        log_level="WARNING",
    )

    batch_size = _infer_batch_size(optimizer, optimization_cfg)
    n_initial_samples = int(getattr(getattr(optimizer, "config", None), "n_initial_samples", 0) or 0)
    n_iterations = int(optimization_cfg.n_iterations)

    print(f"Backend: {backend}")
    print(f"Workflow: {executor.workflow.name}")
    print(f"Batch size: {batch_size}")
    print(f"Initial samples: {n_initial_samples}")
    print(f"Iterations: {n_iterations}")
    print(f"Config: {config_path}")
    print(
        f"\n{'Iter':<6} {'Batch':<6} {'x1':<10} {'x2':<10} {'x3':<10} "
        f"{'f1':<12} {'f2':<12} {'Phase':<15}"
    )
    print("-" * 95)

    trial_index = 0

    if backend == "ax" and n_initial_samples > 0:
        n_sobol_batches = int(math.ceil(n_initial_samples / batch_size))
        for batch in range(n_sobol_batches):
            this_batch = min(batch_size, n_initial_samples - batch * batch_size)
            candidates = optimizer.suggest_candidates(n_candidates=this_batch)
            for design_point in candidates:
                workflow_input = _with_short_parameter_aliases(design_point)
                objectives = executor.execute(workflow_input)
                optimizer.update_with_results(trial_index, design_point, objectives)
                _print_iteration_row(
                    trial_number=trial_index + 1,
                    iteration_number=batch + 1,
                    design_point=design_point,
                    objectives=objectives,
                    phase="Init",
                )
                trial_index += 1

    for iteration in range(n_iterations):
        candidates = optimizer.suggest_candidates(n_candidates=batch_size)
        for design_point in candidates:
            workflow_input = _with_short_parameter_aliases(design_point)
            objectives = executor.execute(workflow_input)
            optimizer.update_with_results(trial_index, design_point, objectives)
            _print_iteration_row(
                trial_number=trial_index + 1,
                iteration_number=iteration + 1,
                design_point=design_point,
                objectives=objectives,
                phase="Optimize",
            )
            trial_index += 1

    output_path = _resolve_results_path(config_path, raw)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    saved = optimizer.save_optimization_results(output_path)

    payload = optimizer.get_optimization_results()
    pareto_size = len(optimizer.get_pareto_front())
    print(f"\nSaved results to: {saved}")
    print(f"Trials recorded: {payload['n_trials']}")
    print(f"Objectives: {payload['objective_names']}")
    print(f"Pareto points: {pareto_size}")

    return 0


def main(argv: List[str]) -> int:
    """Run optimization from a full YAML/JSON config.

    Args:
        argv: Command-line argument list.

    Returns:
        Process exit code.
    """
    if len(argv) not in {2, 3}:
        print(
            "Usage: python run_optimizer_with_joblib.py <full_config.yaml|json> "
            "[workflow_name]"
        )
        return 1

    config_file = argv[1]
    workflow_name = argv[2] if len(argv) == 3 else None
    return run_from_full_config(config_file=config_file, workflow_name=workflow_name)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
