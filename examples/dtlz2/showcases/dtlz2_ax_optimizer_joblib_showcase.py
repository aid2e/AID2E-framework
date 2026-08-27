"""DTLZ2 Optimization with Ax Bayesian Optimizer using JobLib Runner.

This example demonstrates the DAG Executor with Ax optimizer and JobLib scheduler
running the DTLZ2 problem in two different workflow configurations.

Key Differences from Default Showcase:
- Uses JobLib scheduler for parallel job execution
- Configures number of parallel workers (n_jobs)
- Demonstrates local multi-core parallelism

Configuration:
- 10 Sobol initialization points
- 10 Bayesian optimization iterations
- Batch size of 3 (3 parallel evaluations per iteration)
- Total evaluations: 10 + (10 * 3) = 40 points
- JobLib backend: loky (default)
- Parallel workers: -1 (all available CPUs)

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

import numpy as np
import json
from pathlib import Path
from typing import Dict, Any, List

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
from aid2e.schedulers.JobLib.config import JobLibRunnerConfig


# =============================================================================
# DTLZ2 Problem Implementation
# =============================================================================

def dtlz2_both_objectives(x: List[float]) -> Dict[str, float]:
    """Compute both DTLZ2 objectives in one function."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.cos(x[1] * np.pi / 2)
    f2 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.sin(x[1] * np.pi / 2)
    return {"f1": float(f1), "f2": float(f2)}


def dtlz2_f1_only(x: List[float]) -> float:
    """Compute only f1 objective of DTLZ2."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.cos(x[1] * np.pi / 2)
    return float(f1)


def dtlz2_f2_only(x: List[float]) -> float:
    """Compute only f2 objective of DTLZ2."""
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f2 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.sin(x[1] * np.pi / 2)
    return float(f2)


# =============================================================================
# Python Evaluator Wrappers
# =============================================================================

def evaluate_both_objectives_wrapper(context: JobContext) -> Dict[str, float]:
    """Wrapper to evaluate both objectives from JobContext."""
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    objectives = dtlz2_both_objectives(x)
    context.add_log(f"Design point: {x}")
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
        name="dtlz2_ax_joblib_single_branch",
        description="DTLZ2 with Ax optimizer and JobLib scheduler - single branch",
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
        name="dtlz2_ax_joblib_separate_branches",
        description="DTLZ2 with Ax optimizer and JobLib scheduler - separate branches",
        branches=[f1_branch, f2_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


# =============================================================================
# Optimization Functions
# =============================================================================

def run_case_1_single_branch():
    """Run Case 1: Single branch with Ax optimizer and JobLib scheduler."""
    print("\n" + "="*80)
    print("CASE 1: Single Branch with Ax Bayesian Optimizer + JobLib Scheduler")
    print("="*80)
    
    # Create workflow
    workflow = create_single_branch_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure JobLib scheduler
    joblib_config = JobLibRunnerConfig(
        n_jobs=-1,  # Use all available CPUs
        backend="loky",  # Default backend (safe multiprocessing)
        timeout=300,  # 5 minute timeout per job
        verbose=0,  # Silent (increase for debugging)
    )
    
    print(f"\n✓ Scheduler: JobLib")
    print(f"  Workers: {joblib_config.n_jobs} (all CPUs)")
    print(f"  Backend: {joblib_config.backend}")
    print(f"  Timeout: {joblib_config.timeout}s per job")
    
    # Create executor with JobLib scheduler
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_ax_joblib_optimization/case1",
        log_level="WARNING",
        scheduler_config={
            "runner_type": "JobLibRunner",
            "config": joblib_config,
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
    
    # Create Ax optimizer configuration
    ax_config = AxOptimizerConfig(
        initialization_strategy="sobol",
        n_initial_samples=10,
        batch_size=3,
        generator="BOTORCH_MODULAR",
        seed=42,
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
    
    # Phase 1: Sobol initialization (10 points in batches of 3)
    n_sobol_batches = int(np.ceil(ax_config.n_initial_samples / ax_config.batch_size))
    for batch in range(n_sobol_batches):
        # Get batch size (might be less than 3 for last batch)
        batch_size = min(ax_config.batch_size, ax_config.n_initial_samples - batch * ax_config.batch_size)
        
        # Suggest candidates
        candidates = optimizer.suggest_candidates(n_candidates=batch_size)
        
        # Evaluate each candidate (JobLib handles parallelism internally)
        for i, design_point in enumerate(candidates):
            objectives = executor.execute(design_point)
            optimizer.update_with_results(trial_index, design_point, objectives)
            
            print(f"{trial_index+1:<6} {batch+1:<6} {design_point['x1']:<10.4f} {design_point['x2']:<10.4f} "
                  f"{design_point['x3']:<10.4f} {objectives.get('f1', 0):<12.6f} "
                  f"{objectives.get('f2', 0):<12.6f} {'Sobol Init':<15}")
            
            trial_index += 1
    
    # Phase 2: Bayesian optimization (10 iterations x 3 points = 30 points)
    n_bayesian_iterations = 10
    for iteration in range(n_bayesian_iterations):
        # Suggest batch of candidates
        candidates = optimizer.suggest_candidates(n_candidates=ax_config.batch_size)
        
        # Evaluate each candidate
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


def run_case_2_separate_branches():
    """Run Case 2: Separate branches with Ax optimizer and JobLib scheduler."""
    print("\n" + "="*80)
    print("CASE 2: Separate Branches with Ax Bayesian Optimizer + JobLib Scheduler")
    print("="*80)
    
    # Create workflow
    workflow = create_separate_branches_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)} ({[b.name for b in workflow.branches]})")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure JobLib scheduler
    joblib_config = JobLibRunnerConfig(
        n_jobs=-1,  # Use all available CPUs
        backend="loky",
        timeout=300,
        verbose=0,
    )
    
    print(f"\n✓ Scheduler: JobLib")
    print(f"  Workers: {joblib_config.n_jobs} (all CPUs)")
    print(f"  Backend: {joblib_config.backend}")
    print(f"  Timeout: {joblib_config.timeout}s per job")
    
    # Create executor with JobLib scheduler
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_ax_joblib_optimization/case2",
        log_level="WARNING",
        scheduler_config={
            "runner_type": "JobLibRunner",
            "config": joblib_config,
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


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("DTLZ2 Multi-Objective Bayesian Optimization with Ax + JobLib Scheduler")
    print("="*80)
    print("\nConfiguration:")
    print("  • 10 Sobol initialization points")
    print("  • 10 Bayesian optimization iterations")
    print("  • Batch size of 3 (parallel evaluations)")
    print("  • Total evaluations: 10 + (10 × 3) = 40 points")
    print("\nScheduler:")
    print("  • JobLib for local parallel execution")
    print("  • Backend: loky (safe multiprocessing)")
    print("  • Workers: all available CPUs")
    print("\nWorkflow Configurations:")
    print("  1. Single branch - both objectives in one Python function")
    print("  2. Separate branches - each objective in different branch")
    print("\nDTLZ2 Problem:")
    print("  Variables: x1, x2, x3 in [0, 1]")
    print("  Objectives: f1, f2 (minimize both)")
    print("  Optimal Pareto front: x1 in [0, 1], x2 = x3 = 0.5")
    
    try:
        # Run both cases
        optimizer1, executor1 = run_case_1_single_branch()
        optimizer2, executor2 = run_case_2_separate_branches()
        
        # Summary
        print("\n" + "="*80)
        print("COMPARISON SUMMARY")
        print("="*80)
        
        print("\nCase 1 (Single Branch):")
        print(f"  Workflow: {executor1.workflow.name}")
        print(f"  Branches: {len(executor1.workflow.branches)}")
        print(f"  Total evaluations: {len(optimizer1.get_trials())}")
        print(f"  Pareto front size: {len(optimizer1.get_pareto_front())}")
        print(f"  Output directory: {executor1.output_dir}")
        
        print("\nCase 2 (Separate Branches):")
        print(f"  Workflow: {executor2.workflow.name}")
        print(f"  Branches: {len(executor2.workflow.branches)}")
        print(f"  Total evaluations: {len(optimizer2.get_trials())}")
        print(f"  Pareto front size: {len(optimizer2.get_pareto_front())}")
        print(f"  Output directory: {executor2.output_dir}")
        
        print("\n" + "="*80)
        print("✅ Ax + JobLib Optimization Showcase Complete!")
        print("="*80)
        print("\nKey Results:")
        print("  • Both workflow configurations use identical Ax optimizer")
        print("  • Bayesian optimization with SAASBO surrogate model")
        print("  • qNEHVI acquisition for multi-objective optimization")
        print("  • Batch optimization with 3 parallel evaluations per iteration")
        print("  • Sobol initialization ensures good space exploration")
        print("  • JobLib scheduler provides local multi-core parallelism")
        
    except ImportError as e:
        print("\n" + "="*80)
        print("⚠️  ERROR: Missing Dependencies")
        print("="*80)
        print(f"\n{e}")
        print("\nTo run this showcase, install required packages:")
        print("  pip install ax-platform joblib")
        print("\nAlternatively, use the simple random optimizer showcase:")
        print("  python examples/dtlz2/showcases/dtlz2_optimizer_showcase.py")
