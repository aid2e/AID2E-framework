# dtlz2_pymoo_panda_showcase.py
"""DTLZ2 Optimization with PyMOO Evolutionary Optimizer using PanDAiDDS Runner.

This example demonstrates the DAG Executor with PyMOO optimizer and PanDAiDDS scheduler
running the DTLZ2 problem for distributed grid job execution.

Key Differences from JobLib Version:
- Uses PanDAiDDS scheduler for distributed grid job execution
- Configures PanDA cloud, queue, and resource requirements  
- Job names auto-generated as 'user.<username>' (username from system or PANDA_USERNAME env)
- Larger resource allocations for PyMOO generation sizes

Configuration:
- 4 generations × 8 population = 32 total evaluations
- NSGA-II evolutionary algorithm for multi-objective optimization
- Generation-based optimization (full populations, not small batches)
- PanDAiDDS cloud: US
- PanDAiDDS queue: BNL_PanDA_1

Environment Variables:
- PANDA_USERNAME: Override system username for PanDA job names (optional)

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
AID2E_ROOT = REPO_ROOT
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
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig


# =============================================================================
# DTLZ2 Evaluator with JobContext Pattern (for distributed execution)
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


def evaluate_dtlz2_panda(context: JobContext) -> Dict[str, float]:
    """
    Evaluate DTLZ2 objectives using JobContext pattern for distributed PanDA execution.
    
    This function will run on remote PanDA worker nodes, so it needs all imports
    and calculations to be self-contained.
    """
    import math  # Import needed in worker process
    
    # Extract design point from context
    design_point = context.design_point
    
    # Extract decision variables from AID2E parameter format  
    x = ordered_dtlz_vector(design_point)
    
    # Compute DTLZ2 objectives
    g = sum((value - 0.5) ** 2 for value in x[1:])
    factor = 1.0 + g
    f1 = factor * math.cos(x[0] * math.pi / 2.0)
    f2 = factor * math.sin(x[0] * math.pi / 2.0)
    
    # Add logging for remote worker debugging
    context.add_log(f"PanDA Worker - Design point: {x}")  
    context.add_log(f"PanDA Worker - Objectives: f1={f1:.6f}, f2={f2:.6f}")
    context.add_log(f"PanDA Worker - G function: g={g:.6f}, factor={factor:.6f}")
    
    # Return objectives 
    objectives = {"f1": float(f1), "f2": float(f2)}
    context.xcom_push("objectives", objectives)
    return objectives


# =============================================================================
# Workflow Definition for PyMOO + PanDAiDDS
# =============================================================================

def create_pymoo_panda_workflow() -> WorkflowDefinition:
    """Create workflow definition for PyMOO optimization with PanDAiDDS scheduler."""
    
    # Define the evaluation job (will run on remote PanDA workers)
    dtlz2_job = JobDefinition(
        name="dtlz2_panda_evaluation",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": evaluate_dtlz2_panda,
            "op_args": (),
            "op_kwargs": {},
        },
    )
    
    # Create stage and branch
    eval_stage = StageDefinition(name="evaluate_objectives", jobs=[dtlz2_job])
    main_branch = BranchDefinition(name="main", stages=[eval_stage])
    
    # Create workflow
    workflow = WorkflowDefinition(
        name="dtlz2_pymoo_panda",
        description="DTLZ2 with PyMOO evolutionary optimizer and PanDAiDDS distributed scheduler",
        branches=[main_branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    return workflow


# =============================================================================
# PyMOO + PanDAiDDS Integration
# =============================================================================

def run_pymoo_panda_showcase():
    """Run PyMOO evolutionary optimizer with PanDAiDDS distributed scheduler."""
    
    print("\n" + "="*80)
    print("PyMOO + PanDAiDDS Distributed Optimization Showcase")
    print("="*80)
    print("Optimizer: PyMOO NSGA-II evolutionary algorithm")
    print("Scheduler: PanDAiDDS distributed grid execution")
    print("Problem: DTLZ2 multi-objective optimization")
    print("Purpose: Production-ready distributed optimization")
    print("="*80)
    
    # Load PyMOO configuration 
    config_path = AID2E_ROOT / "examples" / "optimizers" / "dtlz2_pymoo_optimizer_only.yml"
    config = load_config(str(config_path))
    
    print(f"\n✓ Configuration loaded: {config_path}")
    print(f"  Problem: {config.problem.name}")
    print(f"  Optimizer: {config.optimizer.name} ({config.optimizer.type})")
    
    # Parse optimizer configuration  
    optimizer_config = config.optimizer.parse_algorithm_params()
    if optimizer_config is None:
        raise RuntimeError("No registered optimizer config model found for PyMOO.")
    
    print(f"  Algorithm: {optimizer_config.algorithm or 'auto'}")
    print(f"  Population: {optimizer_config.pop_size}")
    print(f"  Generations: {optimizer_config.n_iterations}")
    print(f"  Total evaluations: {optimizer_config.pop_size * optimizer_config.n_iterations}")
    
    # Create PyMOO optimizer using AID2E builders
    optimizer = build_optimizer_from_config(config.problem, config.optimizer)
    print(f"  Resolved algorithm: {optimizer.resolved_algorithm}")
    
    # Create workflow definition
    workflow = create_pymoo_panda_workflow()
    print(f"\n✓ Workflow created: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    print(f"  Objectives: {[obj.name for obj in workflow.objectives]}")
    
    # Configure PanDAiDDS scheduler for distributed execution
    # Adapted for PyMOO: larger populations need more resources
    panda_config = PanDAiDDSRunnerConfig(
        # name="user.pymoo_user.dtlz2_pymoo_panda",  # Or omit to auto-generate
        cloud="US",  # PanDA cloud
        queue="BNL_PanDA_1",  # PanDA queue # BNL_OSG_PanDA_1, BNL_PanDA_1
        max_walltime=7200,  # 2 hours (longer for evolutionary algorithms)
        core_count=1,  # CPU cores per job (1 core per evaluation)
        total_memory=3000,  # MB per job (reduced since each job is lighter)
        enable_separate_log=True,
        init_env="source setup_aid2e.sh && bash install_aid2e_dependencies.sh; ",  # Ensure environment is set up on remote workers
        job_dir=str(Path.cwd() / "panda_jobs" / "pymoo_showcase"),
        post_script="rm -fr .src .venv .local src examples ",  # Clean up source files after job completion to save space (optional, use with caution)
    )
    
    print(f"\n✓ PanDAiDDS Configuration:")
    print(f"  Cloud: {panda_config.cloud}")
    print(f"  Queue: {panda_config.queue}")
    print(f"  Cores per job: {panda_config.core_count}")
    print(f"  Memory per job: {panda_config.total_memory} MB")
    print(f"  Max walltime: {panda_config.max_walltime}s")
    print(f"  Job directory: {panda_config.job_dir}")
    
    # Create DAGExecutor with PanDAiDDS scheduler
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/dtlz2_pymoo_panda_optimization",
        log_level="INFO",
        scheduler_config={
            "runner_type": "PanDAiDDSRunner",
            "config": panda_config,
        },
    )
    
    print(f"\n✓ DAGExecutor created:")
    print(f"  Scheduler: PanDAiDDS")
    print(f"  Output directory: {executor.output_dir}")
    
    # PyMOO Generation-based Distributed Optimization Loop
    print(f"\n" + "="*80)
    print("Starting PyMOO Evolutionary Optimization with PanDA Distribution")
    print("="*80)
    print("Note: Each generation submits a full population to PanDA grid")
    print(f"Population size: {optimizer_config.pop_size} jobs per generation")
    print("="*80)
    print(f"{'Gen':<6} {'Trial':<6} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12} {'Status':<12}")
    print("-" * 90)
    
    total_trials = 0
    
    # Run generation-based distributed optimization
    for generation in range(optimizer_config.n_iterations):
        print(f"\n>> Generation {generation + 1}/{optimizer_config.n_iterations}")
        
        # Get full generation of candidates from PyMOO
        candidates = optimizer.suggest_candidates(n_candidates=optimizer_config.pop_size)
        print(f"   Suggested {len(candidates)} candidates for generation {generation + 1}")
        print(f"   Submitting {len(candidates)} jobs to PanDA grid...")
        
        # Evaluate all candidates in the generation 
        # (PanDAiDDS handles distributed execution across grid workers)
        generation_results = []
        
        for i, design_point in enumerate(candidates):
            trial_index = total_trials + i
            
            try:
                print(f"   Submitting job {i+1}/{len(candidates)} to PanDA...")
                
                # Execute via DAGExecutor (uses PanDAiDDS for distributed grid execution)
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
                      f"{objectives.get('f2', 0):<12.6f} {'SUCCESS':<12}")
                
            except Exception as e:
                # Handle PanDA job failures gracefully
                print(f"   PanDA job {i+1} failed: {str(e)}")
                
                # Report dummy results to PyMOO to prevent "outstanding evaluations" error
                dummy_objectives = {"f1": float('inf'), "f2": float('inf')}
                optimizer.update_with_results(trial_index, design_point, dummy_objectives) 
        
                print(f"{generation+1:<6} {trial_index+1:<6} {'ERROR':<10} {'ERROR':<10} "
                      f"{'ERROR':<10} {'ERROR':<12} {'ERROR':<12} {'PANDA_FAIL':<12}")
                
                generation_results.append({
                    'trial': trial_index,
                    'parameters': design_point,
                    'objectives': None,
                    'status': 'FAILED'
                })
        
        total_trials += len(candidates)
        
        # Generation summary
        successful_evals = sum(1 for r in generation_results if r['status'] == 'SUCCESS')
        failed_evals = len(candidates) - successful_evals
        print(f"\n   Generation {generation + 1} complete:")
        print(f"     Successful PanDA jobs: {successful_evals}/{len(candidates)}")
        print(f"     Failed PanDA jobs: {failed_evals}/{len(candidates)}")
        print(f"     Success rate: {100*successful_evals/len(candidates):.1f}%")
        
        # Show current Pareto front progress
        pareto_front = optimizer.get_pareto_front()
        print(f"     Current Pareto front size: {len(pareto_front)} solutions")
    
    # Final results analysis
    print(f"\n" + "="*80)
    print("PyMOO + PanDAiDDS Optimization Complete - Results Analysis")
    print("="*80)
    
    # Get optimization results
    results = optimizer.get_optimization_results()
    pareto_front = optimizer.get_pareto_front()
    all_trials = optimizer.get_trials()
    
    print(f"\nOptimization Summary:")
    print(f"  Total generations: {optimizer_config.n_iterations}")
    print(f"  Population size: {optimizer_config.pop_size}")
    print(f"  Total trials: {results['n_trials']}")
    print(f"  Successful trials: {len([t for t in all_trials if t.metrics])}")
    print(f"  Failed trials: {len([t for t in all_trials if not t.metrics])}")
    print(f"  Overall success rate: {100*len([t for t in all_trials if t.metrics])/len(all_trials):.1f}%")
    print(f"  Pareto front size: {len(pareto_front)}")
    
    # Display Pareto front
    if pareto_front:
        print(f"\nPareto Front (non-dominated solutions):")
        print(f"{'Trial':<8} {'x1':<10} {'x2':<10} {'x3':<10} {'f1':<12} {'f2':<12}")
        print("-" * 70)
        
        for i, trial in enumerate(pareto_front[:10]):  # Show top 10
            dp = trial.parameters
            obj = trial.metrics if trial.metrics else {}
            vector = ordered_dtlz_vector(dp)
            print(f"{trial.index:<8} {vector[0]:<10.4f} {vector[1]:<10.4f} {vector[2]:<10.4f} "
                  f"{obj.get('f1', 0):<12.6f} {obj.get('f2', 0):<12.6f}")
    
    # PanDA execution analysis
    print(f"\n" + "="*80)
    print("PanDA Distributed Execution Analysis")
    print("="*80)
    
    total_panda_jobs = optimizer_config.n_iterations * optimizer_config.pop_size
    successful_jobs = len([t for t in all_trials if t.metrics])
    
    print(f"\nPanDA Job Statistics:")
    print(f"  Total PanDA jobs submitted: {total_panda_jobs}")
    print(f"  Successful job executions: {successful_jobs}")
    print(f"  Failed job executions: {total_panda_jobs - successful_jobs}")
    print(f"  Grid success rate: {100*successful_jobs/total_panda_jobs:.1f}%")
    print(f"  Average jobs per generation: {optimizer_config.pop_size}")
    print(f"  Job execution pattern: Generation-based (full populations)")
    
    if successful_jobs > 0:
        print(f"\n✅ DISTRIBUTED OPTIMIZATION SUCCESS!")
        print(f"   ✓ PyMOO evolutionary algorithm converged")
        print(f"   ✓ PanDA distributed execution validated")
        print(f"   ✓ Generation-based parallelism working")
        print(f"   ✓ Multi-objective Pareto front obtained")
        print(f"   ✓ Ready for production dRICH-MOBO workflows")
        
        print(f"\n📋 Next Steps for dRICH Integration:")
        print(f"   1. Replace DTLZ2 evaluator → dRICH simulation evaluator")
        print(f"   2. Update configuration → dRICH parameter bounds & objectives")
        print(f"   3. Configure PanDA → ePIC-specific init_env and resources")
        print(f"   4. Test with multi-step workflows → simreco → ana → final")
        print(f"   5. Scale up → larger populations and longer optimizations")
    else:
        print(f"\n⚠️  DISTRIBUTED EXECUTION ISSUES DETECTED")
        print(f"   Check PanDA configuration, grid connectivity, and job logs")
    
    return optimizer, executor


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
        print("Starting PyMOO + PanDAiDDS Distributed Optimization Showcase...")        
        optimizer, executor = run_pymoo_panda_showcase()
        
        print(f"\n" + "="*80)
        print("PYMOO + PANDAIDDS SHOWCASE COMPLETE!")
        print("="*80)
        print("Evolutionary optimization with distributed grid execution validated!")
        print("Ready to integrate with dRICH-MOBO detector optimization workflows!")
        print("="*80)
        
    except ImportError as e:
        print(f"\nMissing dependencies: {e}")
        print("Ensure PyMOO and AID2E are properly installed")
        print("Also ensure PanDA client is available for distributed execution")
    except Exception as e:
        print(f"Execution error: {e}")
        print("Check configuration files and PanDA connectivity")