"""
B0 Tracker z-position optimization with Ax Bayesian Optimizer (toy objectives).

This is a DTLZ2-style showcase adapted to B0 tracker layer z positions.

Design variables (cm):
- layer1_z_cm, layer2_z_cm, layer3_z_cm, layer4_z_cm

Objectives (to be replaced by real computations): resolution toy model
"""

from __future__ import annotations

import numpy as np
from typing import Dict

from aid2e.utilities.workflows import (
    DAGExecutor,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobContext,
)
from aid2e.utilities.configurations.objectives import (
    ObjectiveDefinition,
    ObjectiveDirection,
)
from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig


# =============================================================================
# Toy objective function for B0 z layers
# =============================================================================

def b0_toy_objectives(z1: float, z2: float, z3: float, z4: float) -> Dict[str, float]:
    d12 = z2 - z1
    d23 = z3 - z2
    d34 = z4 - z3

    lever_arm = z4 - z1
    nonuniformity = float(np.std([d12, d23, d34]))
    asymmetry = float(abs((z1 + z4) - (z2 + z3)))

    return {
        "lever_arm": float(lever_arm),
        "nonuniformity": float(nonuniformity),
        "asymmetry": float(asymmetry),
    }


def _is_feasible(z1: float, z2: float, z3: float, z4: float) -> bool:
    if not (z1 < z2 < z3 < z4):
        return False
    if not ((z2 - z1) > 5.0 and (z3 - z2) > 5.0 and (z4 - z3) > 5.0):
        return False
    return True


def evaluate_b0_wrapper(context: JobContext) -> Dict[str, float]:
    dp = context.design_point
    z1 = float(dp["layer1_z_cm"])
    z2 = float(dp["layer2_z_cm"])
    z3 = float(dp["layer3_z_cm"])
    z4 = float(dp["layer4_z_cm"])

    if not _is_feasible(z1, z2, z3, z4):
        out = {"b0_resolution": -1e9}
        context.xcom_push("objectives", out)
        return out

    # ARBITRARY TOY PROXY FOR RESOLUTION (to be replaced by Geant4 simulations)
    d12, d23, d34 = (z2-z1), (z3-z2), (z4-z3)
    lever = (z4 - z1)
    nonu = float(np.std([d12, d23, d34]))
    toy_res = float(lever - 10.0 * nonu)

    out = {"b0_resolution": toy_res}
    context.xcom_push("objectives", out)
    return out


# =============================================================================
# Workflow definition (single branch, single job)
# =============================================================================

def create_b0_workflow() -> WorkflowDefinition:
    compute_job = JobDefinition(
        name="compute_b0_objectives",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_b0_wrapper,
            "op_args": (),
            "op_kwargs": {},
        },
    )

    eval_stage = StageDefinition(name="evaluate", jobs=[compute_job])
    main_branch = BranchDefinition(name="main", stages=[eval_stage])

    workflow = WorkflowDefinition(
        name="b0_ax_single_obj",
        description="B0 optimization (single objective)",
        branches=[main_branch],
        objectives=[
            ObjectiveDefinition(name="b0_resolution", direction=ObjectiveDirection.MAXIMIZE),
        ],
    )
    return workflow


# =============================================================================
# Main optimization loop (Ax)
# =============================================================================

def run_b0_ax():
    print("\n" + "=" * 80)
    print("B0 z-layer toy optimization with Ax Bayesian optimizer")
    print("=" * 80)

    workflow = create_b0_workflow()
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/b0_ax_optimization",
        log_level="WARNING",
    )

    # Bounds copied from your YAML draft (cm)
    search_space = SearchSpace(
        parameters={
            "layer1_z_cm": {"type": "range", "bounds": [-45.0, -35.0]},
            "layer2_z_cm": {"type": "range", "bounds": [-18.0, -8.0]},
            "layer3_z_cm": {"type": "range", "bounds": [8.0, 18.0]},
            "layer4_z_cm": {"type": "range", "bounds": [35.0, 45.0]},
        }
    )
    
    ax_config = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=12,
        batch_size=3,
        surrogate_model="saasbo",
        acquisition_function="qnehvi", #qnehvi
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=["b0_resolution"],
        seed=42,
    )

    print("\nConfig:")
    print(f"  Sobol init: {ax_config.n_initial_samples}")
    print(f"  Batch size: {ax_config.batch_size}")
    print("  Objectives: maximize b0_resolution /!\ TOY PROXY FOR NOW /!\ ")

    trial_index = 0

    # Phase 1: Sobol initialization
    n_sobol_batches = int(np.ceil(ax_config.n_initial_samples / ax_config.batch_size))
    for batch in range(n_sobol_batches):
        batch_size = min(ax_config.batch_size, ax_config.n_initial_samples - batch * ax_config.batch_size)
        candidates = optimizer.suggest_candidates(n_candidates=batch_size)
        for design_point in candidates:
            objectives = executor.execute(design_point)
            optimizer.update_with_results(trial_index, design_point, objectives)
            trial_index += 1

    # Phase 2: Bayesian optimization
    n_bayes_iterations = 10
    for it in range(n_bayes_iterations):
        candidates = optimizer.suggest_candidates(n_candidates=ax_config.batch_size)
        for design_point in candidates:
            objectives = executor.execute(design_point)
            optimizer.update_with_results(trial_index, design_point, objectives)
            trial_index += 1

    best = optimizer.get_best_trial()
    print("\nBest trial:")
    print(f"  trial={best.index}")
    print(f"  params={best.parameters}")
    print(f"  metrics={best.metrics}")

    return optimizer, executor


if __name__ == "__main__":
    run_b0_ax()