"""Simple Ax integration smoke test for AID2E.

This script is intentionally lightweight and executable directly:

    .venv/bin/python .experimental/ax_integration_smoke.py

It validates that the AID2E Ax optimizer can:
1. Construct from config.
2. Suggest candidates.
3. Accept updates with objective values.
4. Track trial metadata across initialization and model-based phases.

The script exits non-zero on failure and prints a short summary on success.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from aid2e.optimizers import AID2EAxOptimizer, AID2EAxOptimizerConfig, SearchSpace


@dataclass
class ModeResult:
    """Store smoke-test outputs for one initialization mode."""

    mode: str
    model_keys: List[str]
    n_trials: int


def _evaluate(params: Dict[str, float]) -> Dict[str, float]:
    """Return deterministic non-constant objectives for smoke testing."""
    x1 = float(params["x1"])
    x2 = float(params["x2"])
    return {
        "f1": x1**2 + x2**2,
        "f2": (1.0 - x1) ** 2 + (1.0 - x2) ** 2,
    }


def _run_mode(init_mode: str, surrogate: str = "modular_botorch") -> ModeResult:
    """Execute a short suggest/update loop for one init mode."""
    search_space = SearchSpace(
        parameters={
            "x1": {"type": "range", "bounds": [0.0, 1.0]},
            "x2": {"type": "range", "bounds": [0.0, 1.0]},
        }
    )

    cfg = AID2EAxOptimizerConfig(
        initialization_strategy=init_mode,
        surrogate_model=surrogate,
        acquisition_function="qnehvi",
        n_initial_samples=3,
        n_iterations=4,
        batch_size=1,
        seed=123,
    )

    optimizer = AID2EAxOptimizer(
        search_space=search_space,
        config=cfg,
        objective_names=["f1", "f2"],
        seed=123,
    )

    budget = cfg.n_initial_samples + 3
    model_keys: List[str] = []

    for trial_index in range(budget):
        candidate = optimizer.suggest_candidates(n_candidates=1)[0]
        metrics = _evaluate(candidate)
        optimizer.update_with_results(trial_index, candidate, metrics)

        trial = optimizer.get_trials()[-1]
        model_key = (trial.metadata or {}).get("ax_model_key", "unknown")
        model_keys.append(str(model_key))

    if len(optimizer.get_trials()) != budget:
        raise AssertionError(
            f"Expected {budget} trials, got {len(optimizer.get_trials())} for mode={init_mode}"
        )

    # Center mode should emit center point first.
    if init_mode == "center" and model_keys[0] != "CenterOfSearchSpace":
        raise AssertionError(
            f"Center mode did not emit center point first: {model_keys[0]}"
        )

    # Make sure we transition beyond initialization labels once enough trials complete.
    # If this fails, Ax may be stuck in warmup.
    init_labels = {"Sobol", "CenterOfSearchSpace", "Uniform", "UNIFORM"}
    tail = model_keys[-2:]
    if all(k in init_labels for k in tail):
        raise AssertionError(
            f"Mode={init_mode} appears stuck in initialization phase. "
            f"Last model keys: {tail}, full keys: {model_keys}"
        )

    return ModeResult(mode=init_mode, model_keys=model_keys, n_trials=budget)


def main() -> int:
    """Run integration smoke checks for supported initialization modes."""
    results = []
    for mode in ("sobol", "random", "center"):
        results.append(_run_mode(mode))

    print("Ax integration smoke test: PASS")
    for result in results:
        print(
            f"  mode={result.mode:<6} trials={result.n_trials:<2} "
            f"first={result.model_keys[0]} last={result.model_keys[-1]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
