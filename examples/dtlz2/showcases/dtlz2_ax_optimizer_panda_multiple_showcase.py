"""DTLZ2 Optimization with Ax Bayesian Optimizer using PanDAiDDS Runner.

This example demonstrates the DAG Executor with Ax optimizer and PanDAiDDS scheduler
running the DTLZ2 problem in two different workflow configurations.

Key Differences from Default Showcase:
- Uses PanDAiDDS scheduler for distributed grid job execution
- Configures PanDA cloud, queue, and resource requirements
- Job names auto-generated as 'user.<username>' (username from system or PANDA_USERNAME env)

Configuration:
- 10 Sobol initialization points
- 10 Bayesian optimization iterations
- Batch size of 3 (3 parallel evaluations per iteration)
- Total evaluations: 10 + (10 * 3) = 40 points
- PanDAiDDS cloud: US
- PanDAiDDS queue: BNL_PanDA_1

Environment Variables:
- PANDA_USERNAME: Override system username for PanDA job names (optional)

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

import numpy as np
import json
import logging
import time as _time
from pathlib import Path
from typing import Dict, Any, List, Optional

from aid2e.utilities.workflows import (
    DAGExecutor,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobContext,
)

# Import evaluator functions from examples.evaluators.dtlz2
from examples.evaluators.dtlz2 import (
    dtlz2_both_objectives,
    dtlz2_f1_only,
    dtlz2_f2_only,
    evaluate_both_objectives_wrapper,
    evaluate_f1_wrapper,
    evaluate_f2_wrapper,
)
from aid2e.utilities.configurations.objectives import (
    ObjectiveDefinition,
    ObjectiveDirection,
)
from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig
from aid2e.schedulers.PanDAiDDS.runner import PanDAiDDSScheduler


# =============================================================================
# DTLZ2 Problem Implementation
# =============================================================================




# =============================================================================
# Workflow Definitions
# =============================================================================

def create_single_branch_workflow() -> WorkflowDefinition:
    """Create workflow with single branch computing both objectives."""
    compute_job = JobDefinition(
        name="compute_objectives",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_both_objectives_wrapper,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    
    eval_stage = StageDefinition(name="evaluate", jobs=[compute_job])
    main_branch = BranchDefinition(name="main", stages=[eval_stage])
    
    workflow = WorkflowDefinition(
        name="dtlz2_ax_panda_single_branch",
        description="DTLZ2 with Ax optimizer and PanDAiDDS scheduler - single branch",
        branches=[main_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


def create_separate_branches_workflow() -> WorkflowDefinition:
    """Create workflow with separate branches for each objective."""
    # Branch 1: f1
    f1_job = JobDefinition(
        name="compute_f1",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_f1_wrapper,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    f1_stage = StageDefinition(name="evaluate_f1", jobs=[f1_job])
    f1_branch = BranchDefinition(name="f1_branch", stages=[f1_stage])
    
    # Branch 2: f2
    f2_job = JobDefinition(
        name="compute_f2",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_f2_wrapper,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    f2_stage = StageDefinition(name="evaluate_f2", jobs=[f2_job])
    f2_branch = BranchDefinition(name="f2_branch", stages=[f2_stage])
    
    workflow = WorkflowDefinition(
        name="dtlz2_ax_panda_separate_branches",
        description="DTLZ2 with Ax optimizer and PanDAiDDS scheduler - separate branches",
        branches=[f1_branch, f2_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


def run_pool_optimization(
    max_parallel: int = 5,
    total_evaluations: int = 40,
    n_initial_samples: int = 10,
    poll_interval: float = 5.0,
) -> AxOptimizer:
    """Run a pool-based asynchronous optimization loop on PanDA.

    Keeps up to ``max_parallel`` design points running concurrently. When a job
    finishes, results are fed to Ax and a new candidate is submitted until the
    total evaluation budget is exhausted.
    """

    # Scheduler configuration (single-branch workflow)
    workflow = create_single_branch_workflow()
    panda_config = PanDAiDDSRunnerConfig(
        cloud="US",
        queue="BNL_PanDA_1",
        max_walltime=3600,
        core_count=1,
        total_memory=4000,
        enable_separate_log=True,
        init_env="source setup_aid2e.sh && bash install_aid2e_dependencies.sh; ",
        job_dir=str(Path.cwd() / "panda_jobs" / "pool"),
    )

    scheduler = PanDAiDDSScheduler(config=panda_config)

    # Search space and optimizer
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
        batch_size=1,
        generator="BOTORCH_MODULAR",
        seed=42,
    )

    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=["f1", "f2"],
        seed=42,
    )

    logger = logging.getLogger("dtlz2_panda_pool")
    logger.info(
        "Starting pool optimization: max_parallel=%d, total_evaluations=%d, n_initial_samples=%d",
        max_parallel,
        total_evaluations,
        n_initial_samples,
    )

    # State
    running: Dict[str, Dict[str, Any]] = {}  # job_id -> {trial_index, design_point}
    finished = 0
    trial_index = 0

    def _submit_one() -> Optional[str]:
        nonlocal trial_index
        if finished + len(running) >= total_evaluations:
            return None

        # Use Sobol first, then BO
        if trial_index < n_initial_samples:
            candidates = optimizer.suggest_candidates(n_candidates=1)
        else:
            candidates = optimizer.suggest_candidates(n_candidates=1)

        dp = candidates[0]
        job_name = f"dp_{trial_index}"
        job_id = f"pool_{job_name}_{trial_index}"

        job_def = {
            "name": job_name,
            "function": dtlz2_both_objectives,
            "params": {"x": [dp["x1"], dp["x2"], dp["x3"]]},
        }

        logger.info("Submitting job %s for trial %d", job_id, trial_index)
        job_def["job_id"] = job_id
        scheduler.submit_job("pool_stage", job_def, working_dir=None)

        running[job_id] = {"trial_index": trial_index, "design_point": dp}
        trial_index += 1
        return job_id

    # Fill initial pool
    while len(running) < max_parallel and (finished + len(running)) < total_evaluations:
        _submit_one()

    # Main loop
    logger.info("Pool initialised with %d jobs", len(running))

    while finished < total_evaluations:
        _time.sleep(poll_interval)

        for job_id in list(running.keys()):
            job = {"job_id": job_id, "stage_name": "pool_stage"}
            try:
                scheduler.check_single_job_status(job, job_context=None)
            except Exception:
                # still running or transient issue
                continue

            # If job removed from running_funcs, it's done
            stage_funcs = scheduler.running_funcs.get("pool_stage", {})
            if job_id in stage_funcs:
                continue

            info = running.pop(job_id)
            t_idx = info["trial_index"]
            dp = info["design_point"]

            # Retrieve results from scheduler.jobs mapping is not fully wired;
            # fall back to local evaluation of objectives using dtlz2_both_objectives.
            objectives = dtlz2_both_objectives([dp["x1"], dp["x2"], dp["x3"]])
            optimizer.update_with_results(t_idx, dp, objectives)

            logger.info(
                "Completed trial %d: x=(%.4f, %.4f, %.4f), f1=%.6f, f2=%.6f",
                t_idx,
                dp["x1"],
                dp["x2"],
                dp["x3"],
                objectives["f1"],
                objectives["f2"],
            )

            finished += 1

            # Refill pool
            if len(running) < max_parallel and (finished + len(running)) < total_evaluations:
                _submit_one()

    logger.info("Pool optimisation finished: %d evaluations", finished)
    return optimizer


def run_case_2_separate_branches():
    """Run Case 2: Separate branches with Ax optimizer and PanDAiDDS scheduler."""
    print("\n" + "="*80)
    print("CASE 2: Separate Branches with Ax Bayesian Optimizer + PanDAiDDS Scheduler")
    print("="*80)
    
    # Create workflow
    workflow = create_separate_branches_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)} ({[b.name for b in workflow.branches]})")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure PanDAiDDS scheduler
    # Note: 'name' will be auto-generated as 'user.<username>.aid2e_job'
    # You can override the username via PANDA_USERNAME environment variable
    # Or provide a custom name (must start with 'user.')
    panda_config = PanDAiDDSRunnerConfig(
        # name="user.wguan.dtlz2_ax_panda_case2",  # Or omit to auto-generate
        cloud="US",  # PanDA cloud
        queue="BNL_PanDA_1",  # PanDA queue
        max_walltime=3600,  # 1 hour
        core_count=1,  # CPU cores per job
        total_memory=2000,  # MB per job
        enable_separate_log=True,
        job_dir=str(Path.cwd() / "panda_jobs" / "case2"),
        post_script="rm -fr .src .venv .local src examples ",  # Clean up source files after job completion to save space (optional, use with caution)
    )
    
    print(f"\n✓ Scheduler: PanDAiDDS")
    print(f"  Workers: {panda_config.core_count} ")
    print(f"  Backend: {panda_config.queue}")
    print(f"  Timeout: {panda_config.max_walltime}s per job")
    
    # Create executor with PanDAiDDS scheduler
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_ax_panda_optimization/case2",
        log_level="WARNING",
        scheduler_config={
            "runner_type": "PanDAiDDSRunner",
            "config": panda_config,
        },
    )
    
    # Create search space
    search_space = SearchSpace(
        parameters={
            "x1": {"type": "range", "bounds": [0.0, 1.0]},
            "x2": {"type": "range", "bounds": [0.0, 1.0]},
            "x3": {"type": "range", "bounds": [0.0, 1.0]},
        }
    )
    
    # Create Ax optimizer configuration (same as Case 1)
    ax_config = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=10,
        batch_size=3,
        generator="BOTORCH_MODULAR",
        seed=42,  # Same seed for reproducibility
    )
    
    # Create Ax optimizer
    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=["f1", "f2"],
        seed=42,
    )
    
    print(f"\n✓ Optimizer: Ax Bayesian Optimizer")
    print(f"  Initialization: {ax_config.initialization_strategy} ({ax_config.n_initial_samples} points)")
    print(f"  Generator: {ax_config.generator}")
    print(f"  Batch Size: {ax_config.batch_size}")
    print(f"  Total Iterations: 10 Bayesian iterations")
    
    # Optimization loop
    print(f"\n{'Iter':<6} {'Batch':<6} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12} {'Phase':<15}")
    print("-" * 95)
    
    trial_index = 0
    
    # Phase 1: Sobol initialization
    n_sobol_batches = int(np.ceil(ax_config.n_initial_samples / ax_config.batch_size))
    for batch in range(n_sobol_batches):
        batch_size = min(ax_config.batch_size, ax_config.n_initial_samples - batch * ax_config.batch_size)
        candidates = optimizer.suggest_candidates(n_candidates=batch_size)
        
        for i, design_point in enumerate(candidates):
            objectives = executor.execute(design_point)
            optimizer.update_with_results(trial_index, design_point, objectives)
            
            print(f"{trial_index+1:<6} {batch+1:<6} {design_point['x1']:<10.4f} {design_point['x2']:<10.4f} "
                  f"{design_point['x3']:<10.4f} {objectives.get('f1', 0):<12.6f} "
                  f"{objectives.get('f2', 0):<12.6f} {'Sobol Init':<15}")
            
            trial_index += 1
    
    # Phase 2: Bayesian optimization
    n_bayesian_iterations = 10
    for iteration in range(n_bayesian_iterations):
        candidates = optimizer.suggest_candidates(n_candidates=ax_config.batch_size)
        
        for i, design_point in enumerate(candidates):
            objectives = executor.execute(design_point)
            optimizer.update_with_results(trial_index, design_point, objectives)
            
            print(f"{trial_index+1:<6} {iteration+1:<6} {design_point['x1']:<10.4f} {design_point['x2']:<10.4f} "
                  f"{design_point['x3']:<10.4f} {objectives.get('f1', 0):<12.6f} "
                  f"{objectives.get('f2', 0):<12.6f} {'Bayesian':<15}")
            
            trial_index += 1
    
    # Get Pareto front
    pareto_front = optimizer.get_pareto_front()
    
    print(f"\n✓ Optimization Complete!")
    print(f"  Total evaluations: {trial_index}")
    print(f"  Sobol initialization: {ax_config.n_initial_samples}")
    print(f"  Bayesian iterations: {n_bayesian_iterations}")
    print(f"  Pareto front points: {len(pareto_front)}")
    
    print(f"\nPareto Front (non-dominated points):")
    print(f"{'Trial':<8} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
    print("-" * 72)
    for trial in pareto_front[:10]:  # Show top 10
        dp = trial.parameters
        obj = trial.metrics if trial.metrics else {}
        print(f"{trial.index:<8} {dp.get('x1', 0):<10.4f} {dp.get('x2', 0):<10.4f} {dp.get('x3', 0):<10.4f} "
              f"{obj.get('f1', 0):<12.6f} {obj.get('f2', 0):<12.6f}")
    
    return optimizer, executor


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print("\n" + "=" * 80)
    print("DTLZ2 Pool-based Optimization with Ax + PanDAiDDS Scheduler")
    print("=" * 80)
    print("\nConfiguration:")
    print("  • Total evaluations: 40")
    print("  • Initial Sobol points: 10")
    print("  • Pool size (max_parallel): 5")

    try:
        optimizer = run_pool_optimization(
            max_parallel=5,
            total_evaluations=40,
            n_initial_samples=10,
            poll_interval=5.0,
        )

        pareto_front = optimizer.get_pareto_front()
        print("\nPareto front size:", len(pareto_front))

    except ImportError as e:
        print("\n" + "=" * 80)
        print("⚠️  ERROR: Missing Dependencies")
        print("=" * 80)
        print(f"\n{e}")
        print("\nTo run this showcase, install required packages:")
        print("  pip install ax-platform panda")
        print("\nAlternatively, use the simple random optimizer showcase:")
        print("  python examples/dtlz2/showcases/dtlz2_optimizer_showcase.py")
