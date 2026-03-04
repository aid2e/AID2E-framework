"""DTLZ2 Optimization Showcase with DAG Executor.

This example demonstrates two workflow configurations for the DTLZ2 problem:

Case 1: Single Branch - Both objectives computed in one Python function
Case 2: Separate Branches - Each objective computed in a separate branch

The DTLZ2 problem is a standard multi-objective test problem with:
- 3 decision variables (x1, x2, x3) in [0, 1]
- 2 objectives (f1, f2) to minimize
- Optimal Pareto front: x1 in [0, 1], x2 = x3 = 0.5

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


# =============================================================================
# DTLZ2 Problem Implementation
# =============================================================================

def dtlz2_both_objectives(x: List[float]) -> Dict[str, float]:
    """Compute both DTLZ2 objectives in one function.
    
    DTLZ2 is defined as:
        g(x) = sum((x_i - 0.5)^2 for i in 2..n)
        f1(x) = (1 + g(x)) * cos(x1 * pi/2) * cos(x2 * pi/2)
        f2(x) = (1 + g(x)) * cos(x1 * pi/2) * sin(x2 * pi/2)
    
    For n=3: x = [x1, x2, x3] in [0, 1]^3
    Pareto front: x1 in [0, 1], x2 = x3 = 0.5
    
    Args:
        x: Design point [x1, x2, x3]
        
    Returns:
        Dictionary with f1 and f2 values
    """
    x = np.array(x)
    n = len(x)
    
    # g(x) = sum of squared deviations from 0.5 for x2, x3, ...
    g = np.sum((x[1:] - 0.5) ** 2)
    
    # f1 = (1 + g) * cos(x1 * pi/2) * cos(x2 * pi/2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.cos(x[1] * np.pi / 2)
    
    # f2 = (1 + g) * cos(x1 * pi/2) * sin(x2 * pi/2)
    f2 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.sin(x[1] * np.pi / 2)
    
    return {"f1": float(f1), "f2": float(f2)}


def dtlz2_f1_only(x: List[float]) -> float:
    """Compute only f1 objective of DTLZ2.
    
    Args:
        x: Design point [x1, x2, x3]
        
    Returns:
        f1 value
    """
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f1 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.cos(x[1] * np.pi / 2)
    return float(f1)


def dtlz2_f2_only(x: List[float]) -> float:
    """Compute only f2 objective of DTLZ2.
    
    Args:
        x: Design point [x1, x2, x3]
        
    Returns:
        f2 value
    """
    x = np.array(x)
    g = np.sum((x[1:] - 0.5) ** 2)
    f2 = (1 + g) * np.cos(x[0] * np.pi / 2) * np.sin(x[1] * np.pi / 2)
    return float(f2)


# =============================================================================
# Python Evaluator Wrapper for JobContext
# =============================================================================

def evaluate_both_objectives_wrapper(context: JobContext) -> Dict[str, float]:
    """Wrapper to evaluate both objectives from JobContext.
    
    Extracts design point from context and returns objectives.
    """
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    objectives = dtlz2_both_objectives(x)
    
    # Log results
    context.add_log(f"Design point: {x}")
    context.add_log(f"Objectives: {objectives}")
    
    # Store in XCom for executor to collect
    context.xcom_push("objectives", objectives)
    
    return objectives


def evaluate_f1_wrapper(context: JobContext) -> float:
    """Wrapper to evaluate f1 from JobContext."""
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    f1 = dtlz2_f1_only(x)
    
    context.add_log(f"Design point: {x}")
    context.add_log(f"f1 = {f1}")
    
    # Store in XCom
    context.xcom_push("f1", f1)
    
    return f1


def evaluate_f2_wrapper(context: JobContext) -> float:
    """Wrapper to evaluate f2 from JobContext."""
    design_point = context.design_point
    x = [design_point['x1'], design_point['x2'], design_point['x3']]
    f2 = dtlz2_f2_only(x)
    
    context.add_log(f"Design point: {x}")
    context.add_log(f"f2 = {f2}")
    
    # Store in XCom
    context.xcom_push("f2", f2)
    
    return f2


# =============================================================================
# Case 1: Single Branch Workflow
# =============================================================================

def create_single_branch_workflow() -> WorkflowDefinition:
    """Create workflow with single branch computing both objectives.
    
    Workflow structure:
        Branch: main
            Stage: evaluate
                Job: compute_objectives (PythonEvaluator)
                    → Computes both f1 and f2 in one function
    """
    # Job using PythonEvaluator to compute both objectives
    compute_job = JobDefinition(
        name="compute_objectives",
        command="python",  # Not used for PythonEvaluator
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_both_objectives_wrapper,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    
    # Stage containing the job
    eval_stage = StageDefinition(
        name="evaluate",
        jobs=[compute_job],
    )
    
    # Single branch
    main_branch = BranchDefinition(
        name="main",
        stages=[eval_stage],
    )
    
    # Workflow with objectives
    workflow = WorkflowDefinition(
        name="dtlz2_single_branch",
        description="DTLZ2 with both objectives in single branch",
        branches=[main_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


# =============================================================================
# Case 2: Separate Branches Workflow
# =============================================================================

def create_separate_branches_workflow() -> WorkflowDefinition:
    """Create workflow with separate branches for each objective.
    
    Workflow structure:
        Branch: f1_branch
            Stage: evaluate_f1
                Job: compute_f1 (PythonEvaluator)
                    → Computes only f1
        
        Branch: f2_branch
            Stage: evaluate_f2
                Job: compute_f2 (PythonEvaluator)
                    → Computes only f2
    """
    # Branch 1: Compute f1
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
    
    # Branch 2: Compute f2
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
    
    # Workflow with both branches
    workflow = WorkflowDefinition(
        name="dtlz2_separate_branches",
        description="DTLZ2 with separate branches for each objective",
        branches=[f1_branch, f2_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


# =============================================================================
# Simple Random Optimizer (for demonstration)
# =============================================================================

class SimpleRandomOptimizer:
    """Simple random search optimizer for demonstration.
    
    Generates random design points within bounds and tracks best results.
    This is a simple optimizer for demonstration - in production, use
    Ax optimizer or other sophisticated algorithms.
    """
    
    def __init__(
        self,
        bounds: Dict[str, tuple],
        n_iterations: int = 10,
        seed: int = 42,
    ):
        """Initialize optimizer.
        
        Args:
            bounds: Parameter bounds, e.g., {"x1": (0, 1), "x2": (0, 1)}
            n_iterations: Number of optimization iterations
            seed: Random seed for reproducibility
        """
        self.bounds = bounds
        self.n_iterations = n_iterations
        self.rng = np.random.RandomState(seed)
        
        # Track results
        self.design_points: List[Dict[str, float]] = []
        self.objectives: List[Dict[str, float]] = []
        self.iteration = 0
    
    def suggest(self) -> Dict[str, float]:
        """Suggest next design point to evaluate.
        
        Returns:
            Design point dictionary
        """
        design_point = {}
        for param, (lower, upper) in self.bounds.items():
            design_point[param] = self.rng.uniform(lower, upper)
        return design_point
    
    def tell(self, design_point: Dict[str, float], objectives: Dict[str, float]):
        """Provide feedback with evaluation results.
        
        Args:
            design_point: Evaluated design point
            objectives: Computed objectives
        """
        self.design_points.append(design_point)
        self.objectives.append(objectives)
        self.iteration += 1
    
    def get_best_pareto_front(self, n_points: int = 5) -> List[Dict[str, Any]]:
        """Get approximate Pareto front points.
        
        Args:
            n_points: Number of points to return
            
        Returns:
            List of dicts with design_point and objectives
        """
        if not self.objectives:
            return []
        
        # Simple Pareto dominance check
        pareto_indices = []
        for i, obj_i in enumerate(self.objectives):
            is_dominated = False
            for j, obj_j in enumerate(self.objectives):
                if i == j:
                    continue
                # Check if j dominates i (all objectives worse or equal, at least one worse)
                if all(obj_j[k] <= obj_i[k] for k in obj_i) and \
                   any(obj_j[k] < obj_i[k] for k in obj_i):
                    is_dominated = True
                    break
            if not is_dominated:
                pareto_indices.append(i)
        
        # Return Pareto points
        pareto_points = [
            {
                "design_point": self.design_points[i],
                "objectives": self.objectives[i],
            }
            for i in pareto_indices[:n_points]
        ]
        
        return pareto_points


# =============================================================================
# Main Optimization Functions
# =============================================================================

def run_case_1_single_branch():
    """Run Case 1: Single branch with both objectives."""
    print("\n" + "="*80)
    print("CASE 1: Single Branch - Both Objectives in One Python Function")
    print("="*80)
    
    # Create workflow
    workflow = create_single_branch_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Create executor
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_optimization/case1",
        log_level="WARNING",  # Reduce verbosity
    )
    
    # Create optimizer
    optimizer = SimpleRandomOptimizer(
        bounds={"x1": (0, 1), "x2": (0, 1), "x3": (0, 1)},
        n_iterations=15,
        seed=42,
    )
    
    print(f"\n✓ Optimizer: SimpleRandomOptimizer")
    print(f"  Iterations: {optimizer.n_iterations}")
    print(f"  Bounds: {optimizer.bounds}")
    
    # Optimization loop
    print(f"\n{'Iter':<6} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
    print("-" * 72)
    
    for i in range(optimizer.n_iterations):
        # Get design point from optimizer
        design_point = optimizer.suggest()
        
        # Execute workflow to evaluate design point
        objectives = executor.execute(design_point)
        
        # Provide feedback to optimizer
        optimizer.tell(design_point, objectives)
        
        # Print results
        print(f"{i+1:<6} {design_point['x1']:<10.4f} {design_point['x2']:<10.4f} "
              f"{design_point['x3']:<10.4f} {objectives.get('f1', 0):<12.6f} "
              f"{objectives.get('f2', 0):<12.6f}")
    
    # Get Pareto front
    pareto_front = optimizer.get_best_pareto_front(n_points=5)
    
    print(f"\n✓ Optimization Complete!")
    print(f"  Total evaluations: {len(optimizer.objectives)}")
    print(f"  Pareto front points: {len(pareto_front)}")
    
    print(f"\nPareto Front (top 5 non-dominated points):")
    print(f"{'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
    print("-" * 72)
    for point in pareto_front:
        dp = point['design_point']
        obj = point['objectives']
        print(f"{dp['x1']:<10.4f} {dp['x2']:<10.4f} {dp['x3']:<10.4f} "
              f"{obj.get('f1', 0):<12.6f} {obj.get('f2', 0):<12.6f}")
    
    return optimizer, executor


def run_case_2_separate_branches():
    """Run Case 2: Separate branches for each objective."""
    print("\n" + "="*80)
    print("CASE 2: Separate Branches - Each Objective in Different Branch")
    print("="*80)
    
    # Create workflow
    workflow = create_separate_branches_workflow()
    print(f"\n✓ Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)} ({[b.name for b in workflow.branches]})")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Create executor
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_optimization/case2",
        log_level="WARNING",  # Reduce verbosity
    )
    
    # Create optimizer
    optimizer = SimpleRandomOptimizer(
        bounds={"x1": (0, 1), "x2": (0, 1), "x3": (0, 1)},
        n_iterations=15,
        seed=42,  # Same seed for reproducibility
    )
    
    print(f"\n✓ Optimizer: SimpleRandomOptimizer")
    print(f"  Iterations: {optimizer.n_iterations}")
    print(f"  Bounds: {optimizer.bounds}")
    
    # Optimization loop
    print(f"\n{'Iter':<6} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
    print("-" * 72)
    
    for i in range(optimizer.n_iterations):
        # Get design point from optimizer
        design_point = optimizer.suggest()
        
        # Execute workflow (will run both branches)
        objectives = executor.execute(design_point)
        
        # Provide feedback to optimizer
        optimizer.tell(design_point, objectives)
        
        # Print results
        print(f"{i+1:<6} {design_point['x1']:<10.4f} {design_point['x2']:<10.4f} "
              f"{design_point['x3']:<10.4f} {objectives.get('f1', 0):<12.6f} "
              f"{objectives.get('f2', 0):<12.6f}")
    
    # Get Pareto front
    pareto_front = optimizer.get_best_pareto_front(n_points=5)
    
    print(f"\n✓ Optimization Complete!")
    print(f"  Total evaluations: {len(optimizer.objectives)}")
    print(f"  Pareto front points: {len(pareto_front)}")
    
    print(f"\nPareto Front (top 5 non-dominated points):")
    print(f"{'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
    print("-" * 72)
    for point in pareto_front:
        dp = point['design_point']
        obj = point['objectives']
        print(f"{dp['x1']:<10.4f} {dp['x2']:<10.4f} {dp['x3']:<10.4f} "
              f"{obj.get('f1', 0):<12.6f} {obj.get('f2', 0):<12.6f}")
    
    return optimizer, executor


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    print("\n" + "="*80)
    print("DTLZ2 Multi-Objective Optimization with DAG Executor")
    print("="*80)
    print("\nThis showcase demonstrates two workflow configurations:")
    print("  1. Single branch - both objectives in one Python function")
    print("  2. Separate branches - each objective in different branch")
    print("\nDTLZ2 Problem:")
    print("  Variables: x1, x2, x3 in [0, 1]")
    print("  Objectives: f1, f2 (minimize both)")
    print("  Optimal Pareto front: x1 in [0, 1], x2 = x3 = 0.5")
    
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
    print(f"  Jobs executed: {len(executor1.global_xcom)}")
    print(f"  Output directory: {executor1.output_dir}")
    
    print("\nCase 2 (Separate Branches):")
    print(f"  Workflow: {executor2.workflow.name}")
    print(f"  Branches: {len(executor2.workflow.branches)}")
    print(f"  Jobs executed: {len(executor2.global_xcom)}")
    print(f"  Output directory: {executor2.output_dir}")
    
    print("\n" + "="*80)
    print("✅ Showcase Complete!")
    print("="*80)
    print("\nKey Takeaways:")
    print("  • Both workflow configurations produce the same results")
    print("  • Single branch is simpler for tightly coupled objectives")
    print("  • Separate branches allow independent objective computation")
    print("  • DAG Executor handles both cases seamlessly")
    print("  • Optimizer integration is identical for both cases")
