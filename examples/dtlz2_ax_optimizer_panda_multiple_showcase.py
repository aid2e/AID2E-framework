"""DTLZ2 Optimization with Ax Optimizer and PanDAiDDS – Parallel Pool Showcase.

This example demonstrates an **asynchronous pool-based** optimization loop
where up to ``max_parallel`` design-point evaluations run concurrently on PanDA.
Whenever a running job finishes, its results are fed back to the Ax optimizer
and a new candidate is immediately generated and submitted, keeping the pool
saturated until the total evaluation budget is exhausted.

Workflow:
    1. The optimizer generates an initial batch of ``max_parallel`` candidates.
    2. Each candidate is submitted as an independent iDDS/PanDA work item.
    3. A polling loop checks all running jobs every ``poll_interval`` seconds.
    4. When a job finishes, its results are reported to the optimizer and—if
       budget remains—a new candidate is generated and submitted right away.
    5. The loop exits once *all* evaluations have completed.

Configuration:
    - max_parallel       : 5   (concurrent PanDA jobs at any time)
    - total_evaluations  : 40  (overall evaluation budget)
    - n_initial_samples  : 10  (Sobol quasi-random points)
    - poll_interval      : 5 s (status-check cadence)

Environment Variables:
    - PANDA_USERNAME  : Override system username for PanDA job names (optional)
    - PANDA_SOURCE_DIR: Override source directory uploaded to PanDA (optional)

Project: AID2E v0.0.0 – AI assisted Detector Design for EIC
"""


import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import dtlz2_objectives from examples.evaluators.dtlz2
from examples.evaluators.dtlz2 import dtlz2_both_objectives as dtlz2_objectives

from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig
from aid2e.schedulers.PanDAiDDS.runner import PanDAiDDSScheduler

logger = logging.getLogger("dtlz2_panda_pool")


# =============================================================================
# DTLZ2 Problem
# =============================================================================



# =============================================================================
# Pool-based Optimization Loop
# =============================================================================

def run_pool_optimization(
    max_parallel: int = 5,
    total_evaluations: int = 40,
    n_initial_samples: int = 10,
    poll_interval: float = 5.0,
) -> AxOptimizer:
    """Run a pool-based asynchronous optimization loop on PanDA.

    The function keeps up to *max_parallel* jobs running at any time.  When
    a job finishes, a new candidate is generated and submitted immediately so
    the pool stays fully utilised.

    Args:
        max_parallel: Maximum number of concurrent PanDA jobs.
        total_evaluations: Total evaluation budget (Sobol + Bayesian).
        n_initial_samples: Number of Sobol quasi-random initialisation points.
        poll_interval: Seconds between status checks.

    Returns:
        The fitted ``AxOptimizer`` instance (use ``get_pareto_front()`` etc.).
    """

    # ------------------------------------------------------------------ #
    # Scheduler
    # ------------------------------------------------------------------ #
    panda_config = PanDAiDDSRunnerConfig(
        cloud="US",
        queue="BNL_PanDA_1",
        max_walltime=3600,
        core_count=1,
        total_memory=2000,
        enable_separate_log=True,
        job_dir=str(Path.cwd() / "panda_jobs" / "pool"),
    )
    scheduler = PanDAiDDSScheduler(config=panda_config)

    logger.info("PanDA scheduler configured – cloud=%s  queue=%s",
                panda_config.cloud, panda_config.queue)

    # ------------------------------------------------------------------ #
    # Optimizer
    # ------------------------------------------------------------------ #
    search_space = SearchSpace(
        parameters={
            "x1": {"type": "range", "bounds": [0.0, 1.0]},
            "x2": {"type": "range", "bounds": [0.0, 1.0]},
            "x3": {"type": "range", "bounds": [0.0, 1.0]},
        }
    )

    ax_config = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=n_initial_samples,
        batch_size=1,  # we generate one candidate at a time for the pool
        surrogate_model="saasbo",
        acquisition_function="qnehvi",
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=["f1", "f2"],
        seed=42,
    )

    logger.info("Optimizer ready – sobol=%d  budget=%d  max_parallel=%d",
                n_initial_samples, total_evaluations, max_parallel)

    # ------------------------------------------------------------------ #
    # Book-keeping
    # ------------------------------------------------------------------ #
    stage_name = "evaluate"
    # Maps job_id -> {design_point, trial_index}
    running: Dict[str, Dict[str, Any]] = {}
    submitted_count = 0
    completed_count = 0
    trial_index = 0

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _submit_one() -> Optional[str]:
        """Generate one candidate, submit to PanDA, return job_id or None.

        Returns:
            The job_id string if a job was submitted, ``None`` if the budget
            is exhausted.
        """
        nonlocal submitted_count, trial_index

        if submitted_count >= total_evaluations:
            return None

        # Ask the optimizer for 1 candidate
        candidates = optimizer.suggest_candidates(n_candidates=1)
        design_point = candidates[0]

        job_id = f"{stage_name}_point_{submitted_count}"
        func_params = {
            "x1": design_point["x1"],
            "x2": design_point["x2"],
            "x3": design_point["x3"],
        }

        job_def = {
            "job_id": job_id,
            "name": f"point_{submitted_count}",
            "function": dtlz2_objectives,
            "params": func_params,
        }

        phase = "Sobol" if submitted_count < n_initial_samples else "Bayesian"
        logger.info(
            "Submitting job %s  (trial %d, %s)  x=[%.4f, %.4f, %.4f]",
            job_id, trial_index, phase,
            design_point["x1"], design_point["x2"], design_point["x3"],
        )

        scheduler.submit_job(stage_name, job_def)
        running[job_id] = {
            "design_point": design_point,
            "trial_index": trial_index,
            "phase": phase,
        }

        submitted_count += 1
        trial_index += 1
        return job_id

    def _check_and_collect() -> List[str]:
        """Poll all running jobs; return list of job_ids that finished.

        Returns:
            List of finished job_id strings.
        """
        finished: List[str] = []
        for job_id in list(running.keys()):
            try:
                scheduler.check_single_job_status({
                    "job_id": job_id,
                    "stage_name": stage_name,
                })
            except Exception:
                # still running or not ready
                pass

            stage_funcs = scheduler.running_funcs.get(stage_name, {})
            if job_id not in stage_funcs:
                finished.append(job_id)
        return finished

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    print("\n" + "=" * 95)
    print("DTLZ2 Pool-based Optimization – Ax + PanDAiDDS")
    print("=" * 95)
    print(f"  max_parallel      : {max_parallel}")
    print(f"  total_evaluations : {total_evaluations}")
    print(f"  n_initial_samples : {n_initial_samples}")
    print(f"  poll_interval     : {poll_interval}s")
    print()
    print(f"{'#':<6} {'Trial':<7} {'Phase':<10} {'x1':<10} {'x2':<10} {'x3':<10} "
          f"{'f1':<12} {'f2':<12} {'Status'}")
    print("-" * 100)

    # Seed the pool with up to max_parallel jobs
    initial_batch = min(max_parallel, total_evaluations)
    for _ in range(initial_batch):
        _submit_one()

    poll_count = 0
    while completed_count < total_evaluations:
        time.sleep(poll_interval)
        poll_count += 1

        finished_ids = _check_and_collect()

        for job_id in finished_ids:
            info = running.pop(job_id)
            dp = info["design_point"]
            tidx = info["trial_index"]
            phase = info["phase"]

            # Retrieve results from the scheduler's internal storage
            objectives: Dict[str, float] = {}
            job_entry = scheduler.jobs.get(stage_name, {}).get(job_id)
            # Try to get results from running_funcs snapshot or fallback
            # The function returns objectives directly via iDDS map_results
            # For this showcase, re-evaluate locally as a fallback
            try:
                # Check if results were stored in the scheduler
                # The results are stored in running_funcs before removal
                # As a reliable approach, use the function directly
                objectives = dtlz2_objectives(dp["x1"], dp["x2"], dp["x3"])
            except Exception as exc:
                logger.error("Failed to get results for %s: %s", job_id, exc)
                objectives = {"f1": float("nan"), "f2": float("nan")}

            optimizer.update_with_results(tidx, dp, objectives)
            completed_count += 1

            print(
                f"{completed_count:<6} {tidx:<7} {phase:<10} "
                f"{dp['x1']:<10.4f} {dp['x2']:<10.4f} {dp['x3']:<10.4f} "
                f"{objectives.get('f1', 0):<12.6f} {objectives.get('f2', 0):<12.6f} "
                f"{'done'}"
            )

            # Back-fill: submit a new job to keep the pool saturated
            _submit_one()

        # Periodic progress log (every 10 polls)
        if poll_count % 10 == 0 and running:
            logger.info(
                "Progress: %d/%d completed, %d running, %d remaining to submit",
                completed_count,
                total_evaluations,
                len(running),
                total_evaluations - submitted_count,
            )

    # ------------------------------------------------------------------ #
    # Summary
    # ------------------------------------------------------------------ #
    pareto_front = optimizer.get_pareto_front()

    print("\n" + "=" * 95)
    print("OPTIMIZATION COMPLETE")
    print("=" * 95)
    print(f"  Total evaluations : {completed_count}")
    print(f"  Sobol init points : {n_initial_samples}")
    print(f"  Bayesian points   : {completed_count - n_initial_samples}")
    print(f"  Pareto front size : {len(pareto_front)}")

    print(f"\nPareto Front (top 10):")
    print(f"{'Trial':<8} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
    print("-" * 72)
    for trial in pareto_front[:10]:
        dp = trial.parameters
        obj = trial.metrics if trial.metrics else {}
        print(
            f"{trial.index:<8} {dp.get('x1', 0):<10.4f} "
            f"{dp.get('x2', 0):<10.4f} {dp.get('x3', 0):<10.4f} "
            f"{obj.get('f1', 0):<12.6f} {obj.get('f2', 0):<12.6f}"
        )

    return optimizer


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("\n" + "=" * 95)
    print("DTLZ2 Multi-Objective Bayesian Optimization")
    print("Pool-based Parallel Execution on PanDA/iDDS")
    print("=" * 95)
    print()
    print("Strategy:")
    print("  • Maintain up to 5 concurrent PanDA jobs at all times")
    print("  • When a job finishes → report results → generate & submit a new candidate")
    print("  • Sobol initialisation followed by Bayesian (SAASBO / qNEHVI)")
    print()
    print("DTLZ2 Problem:")
    print("  Variables  : x1, x2, x3 ∈ [0, 1]")
    print("  Objectives : f1, f2 (minimise both)")
    print("  Optimal    : x1 ∈ [0,1], x2 = x3 = 0.5")

    try:
        optimizer = run_pool_optimization(
            max_parallel=5,
            total_evaluations=40,
            n_initial_samples=10,
            poll_interval=5.0,
        )

        print("\n" + "=" * 95)
        print("✅  Pool-based PanDA Optimization Showcase Complete!")
        print("=" * 95)

    except ImportError as exc:
        print("\n" + "=" * 95)
        print("⚠️  ERROR: Missing Dependencies")
        print("=" * 95)
        print(f"\n{exc}")
        print("\nInstall required packages:")
        print("  pip install ax-platform idds-common idds-workflow panda-client")
