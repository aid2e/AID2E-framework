"""Example: Multi-operator workflow with Airflow-like orchestration.

This example demonstrates:
1. WorkflowDefinition with stages and schedulers
2. Multiple operators (Bash, Python, Container)
3. Stage-specific scheduler overrides
4. Task data flow via XCom
5. Design point evaluation loop

Project: AID2E v0.0.0
"""

import json
from pathlib import Path
from typing import Dict, Any

from aid2e.utilities.workflows import (
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobFactory,
    ParallelismPolicy,
    ArtifactSpec,
    JobContext,
    BashEvaluator,
    PythonEvaluator,
    ContainerEvaluator,
)
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration, JobLibRunnerConfig


# ============================================================================
# Example 1: Using Operators Directly (Low-level)
# ============================================================================

def example_operators_direct():
    """Direct operator usage with JobContext."""
    
    # Create a task context
    context = JobContext(
        job_id='task_1',
        stage_id='stage_prepare',
        workflow_id='dtlz2_eval',
        design_point={'x1': 0.5, 'x2': 0.7},
        execution_dir='/tmp/work'
    )
    
    # Example 1: BashEvaluator
    bash_op = BashEvaluator(
        job_id='prepare_params',
        bash_command='echo "Preparing with x1={design_point.x1}, x2={design_point.x2}" > params.txt'
    )
    result = bash_op.execute(context)
    print(f"BashEvaluator result: {result}")
    
    # Example 2: PythonEvaluator
    def compute_metrics(context: JobContext, scale: float = 1.0) -> Dict[str, float]:
        """Compute metrics from design point."""
        x1 = context.design_point.get('x1', 0.0)
        x2 = context.design_point.get('x2', 0.0)
        metrics = {
            'f1': (x1 ** 2) * scale,
            'f2': ((x2 - 1.0) ** 2) * scale
        }
        return metrics
    
    python_op = PythonEvaluator(
        job_id='compute',
        python_callable=compute_metrics,
        op_kwargs={'scale': 2.0}
    )
    result = python_op.execute(context)
    print(f"PythonEvaluator result: {result}")
    
    # Example 3: ContainerEvaluator
    container_op = ContainerEvaluator(
        job_id='run_sim',
        image='dtlz2-simulator:1.0',
        command=['/app/dtlz2.sh'],
        environment={
            'INPUT_FILE': '/data/input.json',
            'OUTPUT_DIR': '/output',
            'X1': '{design_point.x1}',
            'X2': '{design_point.x2}'
        },
        volumes={
            '/host/data': '/data',
            '/host/output': '/output'
        },
        resources={
            'memory': '4g',
            'cpus': '2'
        }
    )
    # Note: Don't execute this without Docker; just show the command
    docker_cmd = container_op._build_docker_command(context)
    print(f"ContainerEvaluator command: {docker_cmd}")


# ============================================================================
# Example 2: Workflow Definition with Stage-specific Schedulers
# ============================================================================

def example_workflow_definition():
    """Define a complete workflow with multiple stages and operators."""
    
    workflow = WorkflowDefinition(
        name='dtlz2_evaluation',
        description='Evaluate DTLZ2 problem with multiple stages',
        
        # Global default scheduler
        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            joblib=JobLibRunnerConfig(n_jobs=-1)
        ),
        
        branches=[
            BranchDefinition(
                name='main',
                stages=[
                    # Stage 1: Prepare parameters (sequential, no special resources)
                    StageDefinition(
                        name='prepare',
                        jobs=[
                            JobDefinition(
                                name='prepare_params',
                                command='python scripts/prepare.py',
                                payload={
                                    'input_design': '{design_point}',
                                    'output_file': '{work_dir}/params.json'
                                },
                                outputs=[
                                    ArtifactSpec(path='params.json', format='json')
                                ]
                            )
                        ],
                        # Uses global scheduler (JobLibRunner)
                        scheduler=None,
                        parallelism=ParallelismPolicy(
                            max_concurrent=1,
                            timeout_sec=60
                        )
                    ),
                    
                    # Stage 2: Parallel evaluation (uses STAGE-SPECIFIC scheduler!)
                    StageDefinition(
                        name='evaluate',
                        jobs=[
                            JobDefinition(
                                name='dtlz2_eval',
                                command='python scripts/dtlz2_problem.py',
                                payload={
                                    'params_file': '{work_dir}/params.json',
                                    'output_file': '{work_dir}/objectives_{job_id}.json'
                                },
                                outputs=[
                                    ArtifactSpec(path='objectives_*.json', format='json')
                                ]
                            )
                        ],
                        job_factory=JobFactory(
                            type='range',
                            params={'n': 4}  # 4 parallel evaluations
                        ),
                        # ⭐ STAGE-SPECIFIC SCHEDULER (overrides global!)
                        scheduler=SchedulerConfiguration(
                            runner_type='SlurmRunner',
                            slurm={
                                'partition': 'gpu',
                                'ntasks': 4,
                                'cpus_per_task': 2,
                                'mem_per_node': '16G',
                                'time': '00:30:00'
                            }
                        ),
                        parallelism=ParallelismPolicy(
                            max_concurrent=4,
                            retry_max=2,
                            timeout_sec=300
                        )
                    ),
                    
                    # Stage 3: Aggregate results (back to local scheduler)
                    StageDefinition(
                        name='aggregate',
                        jobs=[
                            JobDefinition(
                                name='aggregate_results',
                                command='python scripts/aggregate.py',
                                payload={
                                    'objectives_dir': '{work_dir}',
                                    'final_output': '{work_dir}/final_objectives.json'
                                },
                                outputs=[
                                    ArtifactSpec(path='final_objectives.json', format='json')
                                ]
                            )
                        ],
                        scheduler=None,  # Uses global scheduler
                        parallelism=ParallelismPolicy(
                            max_concurrent=1,
                            timeout_sec=120
                        )
                    )
                ]
            )
        ],
        
        objectives=[
            # Objectives definition would go here
        ]
    )
    
    return workflow


# ============================================================================
# Example 3: Workflow with ContainerEvaluator
# ============================================================================

def example_workflow_with_containers():
    """Workflow using Docker containers for evaluation."""
    
    workflow = WorkflowDefinition(
        name='containerized_evaluation',
        description='Evaluate using Docker containers',
        
        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            joblib=JobLibRunnerConfig(n_jobs=4)
        ),
        
        branches=[
            BranchDefinition(
                name='main',
                stages=[
                    StageDefinition(
                        name='evaluate_containers',
                        jobs=[
                            JobDefinition(
                                name='physics_simulation',
                                command='python /app/container_runner.py',
                                payload={
                                    # When executed, job will be wrapped in ContainerEvaluator
                                    'operator_type': 'container',
                                    'image': 'physics-sim:2.0',
                                    'volumes': {
                                        '/host/data': '/data',
                                        '/host/output': '/output'
                                    },
                                    'environment': {
                                        'X1': '{design_point.x1}',
                                        'X2': '{design_point.x2}',
                                        'OUTPUT_DIR': '/output'
                                    },
                                    'resources': {
                                        'memory': '8g',
                                        'cpus': '4'
                                    }
                                },
                                outputs=[
                                    ArtifactSpec(path='results.json', format='json')
                                ]
                            )
                        ],
                        job_factory=JobFactory(
                            type='range',
                            params={'n': 2}
                        ),
                        # Docker containers run on batch system
                        scheduler=SchedulerConfiguration(
                            runner_type='SlurmRunner',
                            slurm={
                                'partition': 'gpu',
                                'gres': 'gpu:2',
                                'mem': '16G'
                            }
                        ),
                        parallelism=ParallelismPolicy(
                            max_concurrent=2,
                            timeout_sec=600
                        )
                    )
                ]
            )
        ]
    )
    
    return workflow


# ============================================================================
# Example 4: Optimizer Integration Pattern
# ============================================================================

def example_optimizer_integration():
    """Pattern for integrating workflow execution with optimizer."""
    
    from aid2e.utilities.workflows.execution_logger import ExecutionLogger
    
    class DAGExecutor:
        """Simple DAG executor (placeholder for full implementation)."""
        
        def __init__(self, workflow: WorkflowDefinition, execution_logger: ExecutionLogger):
            self.workflow = workflow
            self.logger = execution_logger
        
        def execute(self, design_point: Dict[str, Any]) -> Dict[str, float]:
            """Execute workflow for one design point.
            
            Returns:
                objectives: {objective_name: value}
            """
            print(f"\n{'='*60}")
            print(f"Evaluating design point: {design_point}")
            print(f"{'='*60}")
            
            # In real implementation:
            # 1. Extract stages from workflow.branches
            # 2. Build DagDefinition from stage dependencies
            # 3. Topological sort stages
            # 4. For each layer:
            #    - For each stage:
            #      - Get stage.scheduler (or inherit)
            #      - Expand jobs via job_factory
            #      - Execute each job with scheduler
            #      - Log checkpoints
            # 5. Compute objectives from final outputs
            # 6. Return objectives
            
            # Placeholder: return dummy objectives
            objectives = {
                'f1': design_point.get('x1', 0.0) ** 2,
                'f2': (design_point.get('x2', 0.0) - 1.0) ** 2
            }
            
            print(f"Objectives: {objectives}")
            return objectives
    
    # Usage in optimizer loop
    workflow = example_workflow_definition()
    logger = ExecutionLogger(output_dir='/tmp/logs')
    executor = DAGExecutor(workflow, logger)
    
    # Design points from optimizer
    design_points = [
        {'x1': 0.2, 'x2': 0.3},
        {'x1': 0.5, 'x2': 0.7},
        {'x1': 0.8, 'x2': 0.9},
    ]
    
    # Evaluate each design point
    objectives_list = []
    for design_point in design_points:
        objectives = executor.execute(design_point)
        objectives_list.append(objectives)
    
    print(f"\nAll objectives: {objectives_list}")


# ============================================================================
# Example 5: Stage Scheduler Resolution
# ============================================================================

def example_scheduler_resolution():
    """Demonstrate stage scheduler resolution hierarchy."""
    
    workflow = WorkflowDefinition(
        name='scheduler_demo',
        
        # Level 1: Global scheduler
        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            joblib=JobLibRunnerConfig(n_jobs=2)
        ),
        
        branches=[
            BranchDefinition(
                name='branch1',
                # Level 2: Branch scheduler
                scheduler=SchedulerConfiguration(
                    runner_type='JobLibRunner',
                    joblib=JobLibRunnerConfig(n_jobs=4)
                ),
                stages=[
                    StageDefinition(
                        name='stage_uses_branch',
                        jobs=[JobDefinition(name='job1', command='echo "hi"')],
                        scheduler=None  # Uses branch scheduler (n_jobs=4)
                    ),
                    StageDefinition(
                        name='stage_uses_own',
                        jobs=[JobDefinition(name='job2', command='echo "hi"')],
                        # Level 3: Stage scheduler (MOST SPECIFIC)
                        scheduler=SchedulerConfiguration(
                            runner_type='SlurmRunner',
                            slurm={'partition': 'gpu'}
                        )
                    ),
                ]
            ),
            BranchDefinition(
                name='branch2',
                scheduler=None,  # Uses global scheduler
                stages=[
                    StageDefinition(
                        name='stage_uses_global',
                        jobs=[JobDefinition(name='job3', command='echo "hi"')],
                        scheduler=None  # Uses global scheduler (n_jobs=2)
                    ),
                ]
            )
        ]
    )
    
    # Resolution for each stage:
    print("\nScheduler Resolution:")
    print("-" * 60)
    print("stage_uses_branch:")
    print("  1. stage.scheduler? No")
    print("  2. branch.scheduler? Yes → JobLibRunner(n_jobs=4)")
    print()
    print("stage_uses_own:")
    print("  1. stage.scheduler? Yes → SlurmRunner(partition=gpu)")
    print()
    print("stage_uses_global:")
    print("  1. stage.scheduler? No")
    print("  2. branch.scheduler? No")
    print("  3. workflow.scheduler? Yes → JobLibRunner(n_jobs=2)")


# ============================================================================
# Main
# ============================================================================

if __name__ == '__main__':
    print("=" * 70)
    print("Example 1: Direct Operator Usage")
    print("=" * 70)
    example_operators_direct()
    
    print("\n" + "=" * 70)
    print("Example 2: Workflow Definition with Stage Schedulers")
    print("=" * 70)
    workflow = example_workflow_definition()
    print(f"Workflow: {workflow.name}")
    print(f"Stages: {[s.name for b in workflow.branches for s in b.stages]}")
    for branch in workflow.branches:
        for stage in branch.stages:
            scheduler_desc = stage.scheduler or "(inherited)"
            print(f"  {stage.name}: scheduler = {scheduler_desc}")
    
    print("\n" + "=" * 70)
    print("Example 3: Workflow with Containers")
    print("=" * 70)
    workflow = example_workflow_with_containers()
    print(f"Workflow: {workflow.name}")
    
    print("\n" + "=" * 70)
    print("Example 4: Optimizer Integration")
    print("=" * 70)
    example_optimizer_integration()
    
    print("\n" + "=" * 70)
    print("Example 5: Scheduler Resolution")
    print("=" * 70)
    example_scheduler_resolution()
