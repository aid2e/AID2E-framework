"""Complete DAG Executor usage examples.

Demonstrates how to use the DAG Executor to orchestrate workflows with:
1. Simple sequential workflow
2. Parallel job execution with job_factory
3. Multi-stage workflow with dependencies
4. Container-based evaluators
5. Complete optimizer integration example

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

from aid2e.utilities.workflows import (
    DAGExecutor,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobFactory,
    ParallelismPolicy,
    ArtifactSpec,
)
from aid2e.utilities.configurations.objectives import (
    ObjectiveDefinition,
    ObjectiveDirection,
)


def example_1_simple_workflow():
    """Example 1: Simple workflow with one stage and one job."""
    print("\n" + "="*80)
    print("Example 1: Simple Sequential Workflow")
    print("="*80)
    
    # Define a simple job that evaluates DTLZ2
    eval_job = JobDefinition(
        name="dtlz2_eval",
        command="python -c \"import json; obj={'f1': 0.234, 'f2': 0.876}; print(json.dumps(obj))\"",
        payload={"evaluator_type": "bash"},
    )
    
    # Define a stage containing the job
    eval_stage = StageDefinition(
        name="evaluate",
        jobs=[eval_job],
    )
    
    # Define a branch containing the stage
    main_branch = BranchDefinition(
        name="main",
        stages=[eval_stage],
    )
    
    # Define the workflow
    workflow = WorkflowDefinition(
        name="dtlz2_simple",
        description="Simple DTLZ2 evaluation workflow",
        branches=[main_branch],
        objectives=[
            ObjectiveDefinition(
                name="f1",
                direction=ObjectiveDirection.MINIMIZE,
            ),
            ObjectiveDefinition(
                name="f2",
                direction=ObjectiveDirection.MINIMIZE,
            ),
        ],
    )
    
    # Create executor
    executor = DAGExecutor(
        workflow=workflow,
        base_output_dir="/tmp/aid2e_examples",
        log_level="INFO",
    )
    
    # Execute for a design point
    design_point = {"x1": 0.5, "x2": 0.7, "x3": 0.3}
    print(f"\nExecuting workflow for design point: {design_point}")
    
    objectives = executor.execute(design_point)
    
    print(f"\n✅ Workflow completed!")
    print(f"Objectives: {objectives}")
    print(f"Output directory: {executor.output_dir}")


def example_2_parallel_jobs():
    """Example 2: Workflow with parallel job execution."""
    print("\n" + "="*80)
    print("Example 2: Parallel Job Execution with JobFactory")
    print("="*80)
    
    # Job template that will be expanded to N parallel jobs
    eval_job = JobDefinition(
        name="parallel_eval",
        command="echo 'Evaluating design point with job_index={{job_index}}'",
        payload={"evaluator_type": "bash"},
    )
    
    # Stage with job_factory to expand to 4 parallel jobs
    eval_stage = StageDefinition(
        name="parallel_evaluate",
        jobs=[eval_job],
        job_factory=JobFactory(
            type="range",
            params={"n": 4},  # Create 4 parallel jobs
        ),
        parallelism=ParallelismPolicy(
            max_concurrent=4,
            retry_max=2,
            timeout_sec=300,
        ),
    )
    
    branch = BranchDefinition(name="main", stages=[eval_stage])
    
    workflow = WorkflowDefinition(
        name="parallel_workflow",
        description="Workflow with 4 parallel evaluations",
        branches=[branch],
        objectives=[],
    )
    
    executor = DAGExecutor(workflow, base_output_dir="/tmp/aid2e_examples")
    design_point = {"x1": 0.5, "x2": 0.7}
    
    print(f"\nExecuting workflow with 4 parallel jobs...")
    objectives = executor.execute(design_point)
    
    print(f"\n✅ Workflow completed with 4 parallel jobs!")
    print(f"Total jobs executed: {len(executor.global_xcom)}")


def example_3_multi_stage_workflow():
    """Example 3: Multi-stage workflow with sequential dependencies."""
    print("\n" + "="*80)
    print("Example 3: Multi-Stage Workflow with Dependencies")
    print("="*80)
    
    # Stage 1: Generate input data
    generate_job = JobDefinition(
        name="generate_data",
        command="echo 'Generating simulation input data'",
        payload={"evaluator_type": "bash"},
    )
    
    generate_stage = StageDefinition(
        name="generate",
        jobs=[generate_job],
    )
    
    # Stage 2: Run simulation (depends on generate)
    simulate_job = JobDefinition(
        name="run_simulation",
        command="echo 'Running physics simulation'",
        payload={"evaluator_type": "bash"},
    )
    
    simulate_stage = StageDefinition(
        name="simulate",
        jobs=[simulate_job],
    )
    
    # Stage 3: Compute objectives (depends on simulate)
    compute_job = JobDefinition(
        name="compute_objectives",
        command="python -c \"import json; print(json.dumps({'f1': 0.5, 'f2': 0.8}))\"",
        payload={"evaluator_type": "bash"},
    )
    
    compute_stage = StageDefinition(
        name="compute",
        jobs=[compute_job],
    )
    
    # Stages are executed sequentially: generate → simulate → compute
    branch = BranchDefinition(
        name="main",
        stages=[generate_stage, simulate_stage, compute_stage],
    )
    
    workflow = WorkflowDefinition(
        name="multi_stage_workflow",
        description="Sequential pipeline: generate → simulate → compute",
        branches=[branch],
        objectives=[],
    )
    
    executor = DAGExecutor(workflow, base_output_dir="/tmp/aid2e_examples")
    design_point = {"energy": 100, "angle": 45}
    
    print(f"\nExecuting 3-stage sequential workflow...")
    objectives = executor.execute(design_point)
    
    print(f"\n✅ Multi-stage workflow completed!")
    print(f"Stages executed: generate → simulate → compute")


def example_4_container_evaluators():
    """Example 4: Using ContainerEvaluator for Docker-based jobs."""
    print("\n" + "="*80)
    print("Example 4: Container-Based Workflow (ContainerEvaluator)")
    print("="*80)
    
    # Job using ContainerEvaluator
    container_job = JobDefinition(
        name="docker_simulation",
        command="python /app/simulate.py",  # Command inside container
        payload={
            "evaluator_type": "container",
            "image": "python:3.9-slim",
            "container_command": [
                "/bin/bash", "-c",
                "python -c \"import json; print(json.dumps({'f1': 0.3, 'f2': 0.9}))\""
            ],
            "environment": {
                "SIMULATION_MODE": "fast",
                "NUM_EVENTS": "1000",
            },
            "volumes": {
                "/tmp/input": "/app/input",
                "/tmp/output": "/app/output",
            },
        },
        resources={
            "cpu": "2",
            "memory": "4GB",
        },
    )
    
    stage = StageDefinition(
        name="containerized_eval",
        jobs=[container_job],
    )
    
    branch = BranchDefinition(name="main", stages=[stage])
    
    workflow = WorkflowDefinition(
        name="container_workflow",
        description="Workflow using Docker containers",
        branches=[branch],
        objectives=[],
    )
    
    executor = DAGExecutor(workflow, base_output_dir="/tmp/aid2e_examples")
    design_point = {"detector_thickness": 5.0}
    
    print(f"\nExecuting containerized workflow...")
    print(f"Container image: python:3.9-slim")
    print(f"Environment: SIMULATION_MODE=fast, NUM_EVENTS=1000")
    
    try:
        objectives = executor.execute(design_point)
        print(f"\n✅ Container workflow completed!")
    except Exception as e:
        print(f"\n⚠️  Container workflow failed (Docker may not be available): {e}")
        print("This is expected if Docker is not installed.")


def example_5_optimizer_integration():
    """Example 5: Complete optimizer integration example."""
    print("\n" + "="*80)
    print("Example 5: Complete Optimizer Integration")
    print("="*80)
    
    # Define workflow for optimizer
    eval_job = JobDefinition(
        name="evaluate_design",
        command=(
            "python -c \""
            "import json, sys; "
            "import numpy as np; "
            "# DTLZ2 objectives; "
            "x = [0.5, 0.7, 0.3]; "
            "f1 = x[0]; "
            "f2 = (1 + sum([(xi - 0.5)**2 for xi in x[1:]])) * (1 - np.sqrt(x[0]/(1 + sum([(xi - 0.5)**2 for xi in x[1:]]))));  "
            "print(json.dumps({'f1': float(f1), 'f2': float(f2)})); "
            "\""
        ),
        payload={"evaluator_type": "bash"},
    )
    
    eval_stage = StageDefinition(
        name="evaluate",
        jobs=[eval_job],
    )
    
    branch = BranchDefinition(name="main", stages=[eval_stage])
    
    workflow = WorkflowDefinition(
        name="optimizer_workflow",
        description="Workflow for optimizer integration",
        branches=[branch],
        objectives=[
            ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
            ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
        ],
    )
    
    executor = DAGExecutor(workflow, base_output_dir="/tmp/aid2e_examples")
    
    print("\nSimulating optimizer loop with 3 design points...")
    
    # Simulate optimizer providing design points
    design_points = [
        {"x1": 0.2, "x2": 0.5, "x3": 0.8},
        {"x1": 0.5, "x2": 0.7, "x3": 0.3},
        {"x1": 0.8, "x2": 0.3, "x3": 0.6},
    ]
    
    results = []
    for i, design_point in enumerate(design_points):
        print(f"\n  Iteration {i+1}: Evaluating {design_point}")
        objectives = executor.execute(design_point)
        results.append({
            "design_point": design_point,
            "objectives": objectives,
        })
        print(f"  → Objectives: {objectives}")
    
    print(f"\n✅ Optimizer integration complete!")
    print(f"\nResults summary:")
    for i, result in enumerate(results):
        print(f"  {i+1}. {result['design_point']} → {result['objectives']}")


def example_6_workflow_from_config():
    """Example 6: Load workflow from YAML config file."""
    print("\n" + "="*80)
    print("Example 6: Loading Workflow from Config File")
    print("="*80)
    
    import tempfile
    import yaml
    from pathlib import Path
    
    # Create sample config file
    config = {
        "name": "config_workflow",
        "description": "Workflow loaded from YAML config",
        "branches": [
            {
                "name": "main",
                "stages": [
                    {
                        "name": "evaluate",
                        "jobs": [
                            {
                                "name": "eval_job",
                                "command": "echo 'Running from config'",
                                "payload": {"evaluator_type": "bash"},
                            }
                        ],
                    }
                ],
            }
        ],
        "objectives": [],
    }
    
    # Write config to temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
        yaml.dump(config, f)
        config_path = f.name
    
    print(f"\nConfig file created: {config_path}")
    print(f"Config contents:")
    print(yaml.dump(config, default_flow_style=False, indent=2))
    
    # Load executor from config
    from aid2e.utilities.workflows import create_executor_from_config
    
    executor = create_executor_from_config(
        workflow_config_path=config_path,
        output_dir="/tmp/aid2e_examples",
    )
    
    design_point = {"param1": 1.0}
    print(f"\nExecuting workflow from config...")
    
    objectives = executor.execute(design_point)
    
    print(f"\n✅ Config-based workflow completed!")
    print(f"Workflow name: {executor.workflow.name}")
    
    # Cleanup
    Path(config_path).unlink()


if __name__ == "__main__":
    print("\n" + "="*80)
    print("DAG Executor Complete Examples")
    print("="*80)
    print("\nThese examples demonstrate the full capabilities of the DAG Executor")
    print("for orchestrating multi-stage, multi-objective workflows.\n")
    
    # Run all examples
    example_1_simple_workflow()
    example_2_parallel_jobs()
    example_3_multi_stage_workflow()
    example_4_container_evaluators()
    example_5_optimizer_integration()
    example_6_workflow_from_config()
    
    print("\n" + "="*80)
    print("All examples completed!")
    print("="*80)
