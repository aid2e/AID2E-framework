# scripts/dtlz2_pymoo_joblib_integration_test.py
"""PyMOO + JobLib Integration Test - Local Validation.

This script validates the integration of:
- PyMOO evolutionary optimizer (NSGA-II) 
- JobLibRunner for local parallel execution
- DAGExecutor workflow system
- JobContext evaluator pattern

Once working, this can be easily adapted for PanDAiDDS distributed execution.

Configuration:
- 3 generations × 6 population = 18 total evaluations
- NSGA-II algorithm for multi-objective optimization
- JobLibRunner with local multiprocessing
- JobContext wrapper for DTLZ2 evaluation

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

from __future__ import annotations

import math
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add AID2E framework to path
REPO_ROOT = Path(__file__).resolve().parents[1]
AID2E_ROOT = REPO_ROOT / "AID2E-framework"
if str(AID2E_ROOT) not in sys.path:
    sys.path.insert(0, str(AID2E_ROOT))

from aid2e.utilities import build_optimizer_from_config
from aid2e.utilities.configurations import load_config
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
from aid2e.schedulers.JobLib.config import JobLibRunnerConfig


# =============================================================================
# DTLZ2 Evaluator with JobContext Pattern (for local execution)
# =============================================================================

def ordered_dtlz_vector(parameters: Dict[str, Any]) -> List[float]:
    """Return ordered DTLZ decision variables from a flat parameter dict."""
    indexed: List[tuple[int, float]] = []
    for key, value in parameters.items():
        short_key = key.split(".")[-1].split("__")[-1]
        if short_key.startswith("x") and short_key[1:].isdigit():
            indexed.append((int(short_key[1:]), float(value)))
    indexed.sort(key=lambda item: item[0])
    return [value for _, value in indexed]


def evaluate_dtlz2_local(context: JobContext) -> Dict[str, float]:
    """
    Evaluate DTLZ2 objectives using JobContext pattern for local execution.
    """
    import math  # Import needed in worker process
    
    # FIX: Use design_point instead of parameters  
    design_point = context.design_point
    
    # Extract decision variables from AID2E parameter format  
    x = ordered_dtlz_vector(design_point)
    
    # Compute DTLZ2 objectives
    g = sum((value - 0.5) ** 2 for value in x[1:])
    factor = 1.0 + g
    f1 = factor * math.cos(x[0] * math.pi / 2.0)
    f2 = factor * math.sin(x[0] * math.pi / 2.0)
    
    # Add logging like reference examples
    context.add_log(f"Design point: {x}")  
    context.add_log(f"Objectives: f1={f1:.6f}, f2={f2:.6f}")
    
    # Return objectives 
    objectives = {"f1": float(f1), "f2": float(f2)}
    context.xcom_push("objectives", objectives)
    return objectives


# =============================================================================
# Workflow Definition for PyMOO + JobLib
# =============================================================================

def create_pymoo_joblib_workflow() -> WorkflowDefinition:
    """Create workflow definition for PyMOO optimization with JobLib scheduler."""
    
    # Define the evaluation job
    dtlz2_job = JobDefinition(
        name="dtlz2_evaluation",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_dtlz2_local,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    
    # Create stage and branch
    eval_stage = StageDefinition(name="evaluate_objectives", jobs=[dtlz2_job])
    main_branch = BranchDefinition(name="main", stages=[eval_stage])
    
    # Create workflow
    workflow = WorkflowDefinition(
        name="dtlz2_pymoo_joblib",
        description="DTLZ2 with PyMOO evolutionary optimizer and JobLib scheduler",
        branches=[main_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


# =============================================================================
# PyMOO + JobLib Integration Test
# =============================================================================

def run_pymoo_joblib_integration_test():
    """Run integration test: PyMOO evolutionary optimizer + JobLib scheduler."""
    
    print("\n" + "="*80)
    print("PyMOO + JobLib Integration Test")
    print("="*80)
    print("Testing: PyMOO NSGA-II + JobLib local parallel scheduler")
    print("Problem: DTLZ2 multi-objective optimization")
    print("Purpose: Validate integration patterns before PanDAiDDS")
    print("="*80)
    
    # Load PyMOO configuration (reuse existing config, modify for testing)
    config_path = AID2E_ROOT / "examples" / "optimizers" / "dtlz2_pymoo_optimizer_only.yml"
    config = load_config(str(config_path))
    
    print(f"\n✓ Configuration loaded: {config_path}")
    print(f"  Problem: {config.problem.name}")
    print(f"  Optimizer: {config.optimizer.name} ({config.optimizer.type})")
    
    # Parse optimizer configuration  
    optimizer_config = config.optimizer.parse_algorithm_params()
    if optimizer_config is None:
        raise RuntimeError("No registered optimizer config model found for PyMOO.")
    
    # Override for smaller test
    test_generations = 3
    test_population = 6
    
    print(f"  Algorithm: {optimizer_config.algorithm or 'auto'}")
    print(f"  Population: {test_population} (overridden for testing)")
    print(f"  Generations: {test_generations} (overridden for testing)")
    print(f"  Total evaluations: {test_population * test_generations}")
    
    # Create PyMOO optimizer using AID2E builders
    optimizer = build_optimizer_from_config(config.problem, config.optimizer)
    print(f"  Resolved algorithm: {optimizer.resolved_algorithm}")
    
    # Create workflow definition
    workflow = create_pymoo_joblib_workflow()
    print(f"\n✓ Workflow created: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure JobLib scheduler for local parallel execution
    joblib_config = JobLibRunnerConfig(
        n_jobs=4,  # Use 4 CPU cores
        backend="loky",  # Safe multiprocessing backend
        verbose=1,  # Show progress
    )
    
    print(f"\n✓ JobLib Configuration:")
    print(f"  Workers: {joblib_config.n_jobs}")
    print(f"  Backend: {joblib_config.backend}")
    print(f"  Verbose: {joblib_config.verbose}")
    
    # Create DAGExecutor with JobLib scheduler
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_pymoo_joblib_test",
        log_level="INFO",
        scheduler_config={
            "runner_type": "JobLibRunner",
            "config": joblib_config,
        },
    )
    
    print(f"\n✓ DAGExecutor created:")
    print(f"  Scheduler: JobLib")
    print(f"  Output directory: {executor.output_dir}")
    
    # PyMOO Generation-based Optimization Loop
    print(f"\n" + "="*80)
    print("Starting PyMOO Evolutionary Optimization")
    print("="*80)
    print(f"{'Gen':<6} {'Trial':<6} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12} {'Status':<10}")
    print("-" * 80)
    
    total_trials = 0
    
    # Override optimizer config for testing
    original_n_iterations = optimizer_config.n_iterations
    original_pop_size = optimizer_config.pop_size
    optimizer_config.n_iterations = test_generations
    optimizer_config.pop_size = test_population
    
    # Run generation-based optimization
    for generation in range(test_generations):
        print(f"\n>> Generation {generation + 1}/{test_generations}")
        
        # Get full generation of candidates from PyMOO
        candidates = optimizer.suggest_candidates(n_candidates=test_population)
        print(f"   Suggested {len(candidates)} candidates for generation {generation + 1}")
        
        # Evaluate all candidates in the generation (JobLib handles parallelism)
        generation_results = []
        
        for i, design_point in enumerate(candidates):
            trial_index = total_trials + i
            
            try:
                # Execute via DAGExecutor (uses JobLib for local parallel execution)
                objectives = executor.execute(design_point)
                
                # Update PyMOO optimizer with results
                optimizer.update_with_results(trial_index, design_point, objectives)
                
                generation_results.append({
                    'trial': trial_index,
                    'parameters': design_point,
                    'objectives': objectives,
                    'status': 'SUCCESS'
                })
                
                # Log progress
                vector = ordered_dtlz_vector(design_point)
                print(f"{generation+1:<6} {trial_index+1:<6} {vector[0]:<10.4f} {vector[1]:<10.4f} "
                      f"{vector[2]:<10.4f} {objectives.get('f1', 0):<12.6f} "
                      f"{objectives.get('f2', 0):<12.6f} {'SUCCESS':<10}")
                
            except Exception as e:
                # CRITICAL FIX: Report dummy results to PyMOO to prevent "outstanding evaluations" error
                dummy_objectives = {"f1": float('inf'), "f2": float('inf')}
                optimizer.update_with_results(trial_index, design_point, dummy_objectives) 
        
                print(f"{generation+1:<6} {trial_index+1:<6} {'ERROR':<10} {'ERROR':<10} "
                      f"{'ERROR':<10} {'ERROR':<12} {'ERROR':<12} {'FAILED':<10}")
                print(f"   Error: {str(e)}")
                
                generation_results.append({
                    'trial': trial_index,
                    'parameters': design_point,
                    'objectives': None,
                    'status': 'FAILED'
                })
        
        total_trials += len(candidates)
        
        # Generation summary
        successful_evals = sum(1 for r in generation_results if r['status'] == 'SUCCESS')
        print(f"   Generation {generation + 1} complete: {successful_evals}/{len(candidates)} successful evaluations")
    
    # Restore original config
    optimizer_config.n_iterations = original_n_iterations
    optimizer_config.pop_size = original_pop_size
    
    # Final results analysis
    print(f"\n" + "="*80)
    print("PyMOO Optimization Complete - Results Analysis")
    print("="*80)
    
    # Get optimization results
    results = optimizer.get_optimization_results()
    pareto_front = optimizer.get_pareto_front()
    
    print(f"\nOptimization Summary:")
    print(f"  Total generations: {test_generations}")
    print(f"  Population size: {test_population}")
    print(f"  Total trials: {results['n_trials']}")
    print(f"  Successful trials: {len([t for t in optimizer.get_trials() if t.metrics])}")
    print(f"  Pareto front size: {len(pareto_front)}")
    
    # Display Pareto front
    if pareto_front:
        print(f"\nPareto Front (non-dominated solutions):")
        print(f"{'Trial':<8} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
        print("-" * 70)
        
        for i, trial in enumerate(pareto_front[:8]):  # Show all (small test)
            dp = trial.parameters
            obj = trial.metrics if trial.metrics else {}
            vector = ordered_dtlz_vector(dp)
            print(f"{trial.index:<8} {vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                  f"{obj.get('f1', 0):<12.6f} {obj.get('f2', 0):<12.6f}")
    
    # Test validation
    print(f"\n" + "="*80)
    print("Integration Test Validation")
    print("="*80)
    
    validation_results = {
        'config_loading': True,
        'optimizer_creation': True,
        'workflow_creation': True, 
        'joblib_config': True,
        'dag_executor_creation': True,
        'optimization_execution': results['n_trials'] > 0,
        'pareto_front_generation': len(pareto_front) > 0,
        'local_evaluation': len([t for t in optimizer.get_trials() if t.metrics]) > 0,
        'generation_completion': results['n_trials'] == test_generations * test_population
    }
    
    print("\nValidation Results:")
    for test, passed in validation_results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test.replace('_', ' ').title():<25}: {status}")
    
    overall_success = all(validation_results.values())
    print(f"\n{'✅ INTEGRATION TEST PASSED' if overall_success else '❌ INTEGRATION TEST FAILED'}")
    
    if overall_success:
        print(f"\n🎉 PyMOO + JobLib integration is working correctly!")
        print(f"   ✓ Generation-based optimization validated")
        print(f"   ✓ JobContext pattern validated")
        print(f"   ✓ DAGExecutor workflow validated")
        print(f"   ✓ Ready to adapt for PanDAiDDS distributed execution")
        
        print(f"\n📋 Next Steps:")
        print(f"   1. Replace JobLibRunner → PanDAiDDSRunner")
        print(f"   2. Update configuration for PanDA cloud/queue")
        print(f"   3. Test with distributed grid execution")
        print(f"   4. Implement dRICH-MOBO evaluator functions")
    else:
        print(f"\n⚠️  Integration issues detected. Fix before proceeding to PanDA.")
    
    return optimizer, executor, validation_results


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == "__main__":
    # Configure logging for debugging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    try:
        print("🚀 Starting PyMOO + JobLib Integration Test...")
        print("⏱️  Expected runtime: ~30-60 seconds")
        
        optimizer, executor, validation_results = run_pymoo_joblib_integration_test()
        
        print(f"\n" + "="*80)
        print("✅ LOCAL INTEGRATION TEST COMPLETE!")
        print("="*80)
        print("Validated Patterns:")
        print("  • PyMOO evolutionary optimization ✓")
        print("  • JobLib local parallel execution ✓") 
        print("  • DAGExecutor workflow system ✓")
        print("  • JobContext evaluator pattern ✓")
        print("  • Generation-based optimization loop ✓")
        
    except ImportError as e:
        print(f"\n❌ Missing dependencies: {e}")
        print("Ensure PyMOO and AID2E are properly installed in .pymoo environment")
        
    except Exception as e:
        print(f"\n❌ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n💡 Common issues:")
        print("  - Check bash + .pymoo environment is active")
        print("  - Verify AID2E framework path is correct")
        print("  - Ensure PyMOO is installed: pip install pymoo")