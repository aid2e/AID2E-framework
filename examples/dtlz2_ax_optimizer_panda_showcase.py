"""DTLZ2 Optimization with Ax Bayesian Optimizer using PanDA/iDDS Runner.

This example demonstrates the DAG Executor with Ax optimizer and PanDA/iDDS scheduler
running the DTLZ2 problem in two different workflow configurations.

Key Differences from JobLib Showcase:
- Uses PanDA/iDDS scheduler for distributed job execution
- Configures cloud, queue, and resource requirements
- Demonstrates large-scale distributed parallelism on grid infrastructure
- Requires iDDS and PanDA client installation

Configuration:
- 10 Sobol initialization points
- 10 Bayesian optimization iterations
- Batch size of 3 (3 parallel evaluations per iteration)
- Total evaluations: 10 + (10 * 3) = 40 points
- PanDA cloud: US (configurable)
- Queue: managed (configurable)
- Max walltime: 3600s per job

Prerequisites:
- Install iDDS: pip install idds-client idds-workflow
- Configure PanDA credentials and authentication
- Ensure source code is accessible to PanDA workers

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
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig


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
        name="dtlz2_ax_panda_single_branch",
        description="DTLZ2 with Ax optimizer and PanDA/iDDS scheduler - single branch",
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
        description="DTLZ2 with Ax optimizer and PanDA/iDDS scheduler - separate branches",
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
    """Run Case 1: Single branch with Ax optimizer and PanDA/iDDS scheduler."""
    print("\n" + "="*80)
    print("CASE 1: Single Branch with Ax Bayesian Optimizer + PanDA/iDDS Scheduler")
    print("="*80)
    
    # Create workflow
    workflow = create_single_branch_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure PanDA/iDDS scheduler
    scheduler_config = PanDAiDDSRunnerConfig(
        name="dtlz2_panda_single",
        cloud="US",  # Change to your PanDA cloud
        # "queue": "BNL_PanDA_1",  # BNL_OSG_PanDA_1, BNL_PanDA_1
        queue="BNL_PanDA_1",  # Change to your queue
        source_dir=str(Path(__file__).parent.parent / "src"),
        source_dir_parent_level=1,
        exclude_source_files=[
            "*.pyc",
            "__pycache__",
            "*.git*",
            "*.pytest_cache",
            "*.egg-info",
            "*.tox",
            "*.coverage",
            "tests/",
            "docs/",
        ],
        max_walltime=3600,  # 1 hour
        core_count=1,
        total_memory=2000,  # MB
        enable_separate_log=True,
        job_dir=str(Path.cwd() / "panda_jobs" / "case1"),
    )
    
    print(f"\n✓ Scheduler: PanDA/iDDS")
    print(f"  Cloud: {scheduler_config.cloud}")
    print(f"  Queue: {scheduler_config.queue}")
    print(f"  Max walltime: {scheduler_config.max_walltime}s")
    print(f"  Resources: {scheduler_config.core_count} cores, {scheduler_config.total_memory} MB")
    
    # Define search space
    search_space = SearchSpace(
        parameters={
            "x1": {"type": "range", "bounds": [0.0, 1.0]},
            "x2": {"type": "range", "bounds": [0.0, 1.0]},
            "x3": {"type": "range", "bounds": [0.0, 1.0]},
        }
    )
    print(f"\n✓ Search space: {len(search_space.parameters)} parameters")
    for param_name, param_def in search_space.parameters.items():
        print(f"  - {param_name}: {param_def['bounds']}")
    
    # Configure optimizer
    optimizer_config = AxOptimizerConfig(
        n_sobol_steps=10,  # Initial random samples
        n_bayes_steps=10,  # Bayesian optimization steps
        batch_size=3,      # Parallel evaluations per step
    )
    
    print(f"\n✓ Optimizer: Ax Bayesian")
    print(f"  Sobol initialization: {optimizer_config.n_sobol_steps} points")
    print(f"  Bayesian iterations: {optimizer_config.n_bayes_steps} steps")
    print(f"  Batch size: {optimizer_config.batch_size} parallel evaluations")
    print(f"  Total evaluations: {optimizer_config.n_sobol_steps + optimizer_config.n_bayes_steps * optimizer_config.batch_size}")
    
    # Create optimizer
    optimizer = AxOptimizer(config=optimizer_config)
    optimizer.initialize(
        search_space=search_space,
        objectives=workflow.objectives,
    )
    
    # Create executor with scheduler
    executor = DAGExecutor(
        workflow=workflow,
        optimizer=optimizer,
        scheduler_config={
            "runner_type": "PanDAiDDSRunner",
            "config": scheduler_config.model_dump(),
        },
    )
    
    print("\n" + "-"*80)
    print("Starting optimization...")
    print("-"*80)
    
    # Run optimization
    results = executor.execute()
    
    # Display results
    print("\n" + "="*80)
    print("OPTIMIZATION RESULTS - Case 1")
    print("="*80)
    
    if results:
        print(f"\nTotal iterations: {len(results)}")
        print(f"Last iteration objectives:")
        for obj_name, obj_value in results[-1].get("objectives", {}).items():
            print(f"  {obj_name}: {obj_value:.6f}")
        
        # Find best point for each objective
        best_f1 = min(results, key=lambda r: r.get("objectives", {}).get("f1", float('inf')))
        best_f2 = min(results, key=lambda r: r.get("objectives", {}).get("f2", float('inf')))
        
        print(f"\nBest f1: {best_f1['objectives']['f1']:.6f}")
        print(f"  at x = [{best_f1['design_point']['x1']:.4f}, {best_f1['design_point']['x2']:.4f}, {best_f1['design_point']['x3']:.4f}]")
        
        print(f"\nBest f2: {best_f2['objectives']['f2']:.6f}")
        print(f"  at x = [{best_f2['design_point']['x1']:.4f}, {best_f2['design_point']['x2']:.4f}, {best_f2['design_point']['x3']:.4f}]")
    
    print("\n✓ Case 1 completed successfully!")
    return results


def run_case_2_separate_branches():
    """Run Case 2: Separate branches with Ax optimizer and PanDA/iDDS scheduler."""
    print("\n" + "="*80)
    print("CASE 2: Separate Branches with Ax Bayesian Optimizer + PanDA/iDDS Scheduler")
    print("="*80)
    
    # Create workflow
    workflow = create_separate_branches_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure PanDA/iDDS scheduler
    scheduler_config = PanDAiDDSRunnerConfig(
        name="dtlz2_panda_separate",
        cloud="US",  # Change to your PanDA cloud
        queue="managed",  # Change to your queue
        source_dir=str(Path(__file__).parent.parent / "src"),
        source_dir_parent_level=1,
        exclude_source_files=[
            "*.pyc",
            "__pycache__",
            "*.git*",
            "*.pytest_cache",
            "*.egg-info",
            "*.tox",
            "*.coverage",
            "tests/",
            "docs/",
        ],
        max_walltime=3600,  # 1 hour
        core_count=1,
        total_memory=2000,  # MB
        enable_separate_log=True,
        job_dir=str(Path.cwd() / "panda_jobs" / "case2"),
    )
    
    print(f"\n✓ Scheduler: PanDA/iDDS")
    print(f"  Cloud: {scheduler_config.cloud}")
    print(f"  Queue: {scheduler_config.queue}")
    print(f"  Max walltime: {scheduler_config.max_walltime}s")
    print(f"  Resources: {scheduler_config.core_count} cores, {scheduler_config.total_memory} MB")
    
    # Define search space
    search_space = SearchSpace(
        parameters={
            "x1": {"type": "range", "bounds": [0.0, 1.0]},
            "x2": {"type": "range", "bounds": [0.0, 1.0]},
            "x3": {"type": "range", "bounds": [0.0, 1.0]},
        }
    )
    print(f"\n✓ Search space: {len(search_space.parameters)} parameters")
    for param_name, param_def in search_space.parameters.items():
        print(f"  - {param_name}: {param_def['bounds']}")
    
    # Configure optimizer
    optimizer_config = AxOptimizerConfig(
        n_sobol_steps=10,  # Initial random samples
        n_bayes_steps=10,  # Bayesian optimization steps
        batch_size=3,      # Parallel evaluations per step
    )
    
    print(f"\n✓ Optimizer: Ax Bayesian")
    print(f"  Sobol initialization: {optimizer_config.n_sobol_steps} points")
    print(f"  Bayesian iterations: {optimizer_config.n_bayes_steps} steps")
    print(f"  Batch size: {optimizer_config.batch_size} parallel evaluations")
    print(f"  Total evaluations: {optimizer_config.n_sobol_steps + optimizer_config.n_bayes_steps * optimizer_config.batch_size}")
    
    # Create optimizer
    optimizer = AxOptimizer(config=optimizer_config)
    optimizer.initialize(
        search_space=search_space,
        objectives=workflow.objectives,
    )
    
    # Create executor with scheduler
    executor = DAGExecutor(
        workflow=workflow,
        optimizer=optimizer,
        scheduler_config={
            "runner_type": "PanDAiDDSRunner",
            "config": scheduler_config.model_dump(),
        },
    )
    
    print("\n" + "-"*80)
    print("Starting optimization...")
    print("-"*80)
    
    # Run optimization
    results = executor.execute()
    
    # Display results
    print("\n" + "="*80)
    print("OPTIMIZATION RESULTS - Case 2")
    print("="*80)
    
    if results:
        print(f"\nTotal iterations: {len(results)}")
        print(f"Last iteration objectives:")
        for obj_name, obj_value in results[-1].get("objectives", {}).items():
            print(f"  {obj_name}: {obj_value:.6f}")
        
        # Find best point for each objective
        best_f1 = min(results, key=lambda r: r.get("objectives", {}).get("f1", float('inf')))
        best_f2 = min(results, key=lambda r: r.get("objectives", {}).get("f2", float('inf')))
        
        print(f"\nBest f1: {best_f1['objectives']['f1']:.6f}")
        print(f"  at x = [{best_f1['design_point']['x1']:.4f}, {best_f1['design_point']['x2']:.4f}, {best_f1['design_point']['x3']:.4f}]")
        
        print(f"\nBest f2: {best_f2['objectives']['f2']:.6f}")
        print(f"  at x = [{best_f2['design_point']['x1']:.4f}, {best_f2['design_point']['x2']:.4f}, {best_f2['design_point']['x3']:.4f}]")
    
    print("\n✓ Case 2 completed successfully!")
    return results


# =============================================================================
# Main Execution
# =============================================================================

def main():
    """Run both showcase cases."""
    print("\n" + "="*80)
    print("DTLZ2 Optimization Showcase with Ax Bayesian Optimizer")
    print("Using PanDA/iDDS Scheduler for Distributed Execution")
    print("="*80)
    print("\nProject: AID2E v0.0.0 - AI assisted Detector Design for EIC")
    print("Repository: https://github.com/aid2e/AID2E-framework.git")
    print("\nThis showcase demonstrates two workflow configurations:")
    print("  1. Single branch computing both objectives together")
    print("  2. Separate branches for each objective (f1 and f2)")
    print("\nNote: This example requires:")
    print("  - iDDS client and workflow packages installed")
    print("  - PanDA credentials and authentication configured")
    print("  - Access to PanDA cloud resources")
    print("="*80)
    
    try:
        # Run Case 1
        results_case1 = run_case_1_single_branch()
        
        # Optional: Save results
        output_dir = Path("outputs") / "panda_showcase"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        case1_file = output_dir / "case1_single_branch_results.json"
        with open(case1_file, 'w') as f:
            json.dump(results_case1, f, indent=2)
        print(f"\n✓ Results saved to: {case1_file}")
        
        print("\n" + "="*80)
        print("Proceeding to Case 2...")
        print("="*80)
        
        # Run Case 2
        results_case2 = run_case_2_separate_branches()
        
        case2_file = output_dir / "case2_separate_branches_results.json"
        with open(case2_file, 'w') as f:
            json.dump(results_case2, f, indent=2)
        print(f"\n✓ Results saved to: {case2_file}")
        
        # Summary
        print("\n" + "="*80)
        print("SHOWCASE SUMMARY")
        print("="*80)
        print(f"\n✓ Both cases completed successfully!")
        print(f"  Case 1 iterations: {len(results_case1)}")
        print(f"  Case 2 iterations: {len(results_case2)}")
        print(f"\n✓ Results saved to: {output_dir}")
        print("\nThe PanDA/iDDS scheduler enables:")
        print("  • Distributed execution across grid infrastructure")
        print("  • Automatic resource management and job scheduling")
        print("  • Fault tolerance and automatic retry mechanisms")
        print("  • Scalability to thousands of parallel evaluations")
        print("\nFor production use, configure:")
        print("  • cloud: Your target PanDA cloud (e.g., US, EU, CERN)")
        print("  • queue: Appropriate queue for your workload")
        print("  • source_dir: Ensure all dependencies are included")
        print("  • max_walltime: Set appropriate time limits")
        print("  • core_count/total_memory: Match your job requirements")
        
    except Exception as e:
        print(f"\n❌ Error during showcase execution: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
