from __future__ import annotations
from typing import Dict
import numpy as np
from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig


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

def run_epic_b0_toy_optimization(config, verbosity=0):
    # runner for toy optimization of ePIC B0 tracker design,
    # using Ax optimizer with a simple proxy objective function (to be replaced by real computations later)
    dc = config.problem.design_config
    params = {}
    for name in dc.get_parameter_names():
        bounds = dc.get_parameter_bounds(name)
        if bounds is not None:
            params[name] = {"type": "range", "bounds": [float(bounds[0]), float(bounds[1])]}

    search_space = SearchSpace(parameters=params)

    objective_names = [o.name for o in config.problem.objectives]

    ax_cfg = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=config.optimization.n_initial_samples,
        batch_size=config.optimization.parallel_evaluations,
        surrogate_model="saasbo",
        acquisition_function="qnehvi",
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_cfg,
        objective_names=objective_names,
        seed=42,
    )

    trial = 0
    n_total = config.optimization.n_initial_samples + config.optimization.n_iterations * ax_cfg.batch_size

    while trial < n_total:
        candidates = optimizer.suggest_candidates(n_candidates=ax_cfg.batch_size)

        for design_point in candidates:

            failures = []
            for c in (dc.parameter_constraints or []):
                expr = str(c.rule)
                for k in sorted(design_point.keys(), key=len, reverse=True):
                    expr = expr.replace(k, f"design_point[{k!r}]")

                if not bool(eval(expr, {"__builtins__": {}}, {"design_point": design_point})):
                    failures.append(c.name)

            ok = len(failures) == 0

            if not ok:
                metrics = {"b0_resolution": -1e9}
            else:
                metrics = eval_epic_b0(design_point)

            optimizer.update_with_results(trial, design_point, metrics)

            trial += 1
            if trial >= n_total:
                break

    best = optimizer.get_best_trial()

    print("Best trial:")
    print(best.parameters)
    print(best.metrics)