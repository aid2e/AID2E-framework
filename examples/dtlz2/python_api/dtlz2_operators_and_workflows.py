"""Example: Multi-operator workflow with Airflow-like orchestration.

This example demonstrates:
1. WorkflowDefinition with stages and schedulers
2. Multiple operators (Bash, Python, Container)
3. Stage-specific scheduler overrides
4. Task data flow via XCom

Project: AID2E v0.0.0
"""

import sys
from shlex import quote
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

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
)
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration
from aid2e.utilities.configurations.objectives import ObjectiveDefinition
from examples.dtlz2.dtlz2_evaluator import evaluate_both_objectives_wrapper


# ============================================================================
# Example 1: Using Operators Directly (Low-level)
# ============================================================================

def example_operators_direct():
    """Direct operator usage with JobContext."""
    
    # Create the working directory before direct execution.
    work_dir = Path('/tmp/aid2e_operators')
    work_dir.mkdir(parents=True, exist_ok=True)

    # Create a task context
    context = JobContext(
        task_id='stage_prepare:task_1',
        job_id='task_1',
        stage_id='stage_prepare',
        workflow_id='dtlz2_eval',
        design_point={f'x{i}': 0.5 for i in range(1, 11)},
        execution_dir=str(work_dir)
    )
    
    # Example 1: BashEvaluator
    bash_op = BashEvaluator(
        engine_id='prepare_params',
        bash_command='echo "Preparing with x1={{design_point.x1}}, x2={{design_point.x2}}" > params.txt'
    )
    result = bash_op.execute(context)
    print(f"BashEvaluator result: {result}")
    
    # Example 2: PythonEvaluator
    python_op = PythonEvaluator(
        engine_id='compute',
        python_callable=evaluate_both_objectives_wrapper,
    )
    result = python_op.execute(context)
    print(f"PythonEvaluator result: {result}")
    print(f"XCom objectives: {context.xcom_pull(context.task_id, 'objectives')}")


# ============================================================================
# Example 2: Workflow Definition with Stage-specific Schedulers
# ============================================================================

def example_workflow_definition():
    """Define DTLZ2 command jobs with a stage-level Slurm override."""
    
    workflow = WorkflowDefinition(
        name='dtlz2_evaluation',
        description='Evaluate DTLZ2 using a stage-specific scheduler',
        
        # Workflow default scheduler
        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            parameters={'n_jobs': -1}
        ),
        
        branches=[
            BranchDefinition(
                name='main',
                stages=[
                    # The scheduler evaluates four copies of the same design.
                    StageDefinition(
                        name='evaluate',
                        jobs=[
                            JobDefinition(
                                name='dtlz2_eval',
                                command=(
                                    '"{{python_executable}}" "{{repo_root}}/examples/dtlz2/dtlz2_evaluator.py" '
                                    '--design "{{design_file}}" '
                                    '--output "{{output_dir}}/objectives.json" --repeat 0'
                                ),
                                outputs=[
                                    ArtifactSpec(path='{{output_dir}}/objectives.json', format='json')
                                ]
                            )
                        ],
                        job_factory=JobFactory(
                            type='range',
                            params={'n': 4}  # Four jobs, not four optimizer candidates
                        ),
                        # Stage scheduler overrides the workflow default; adjust for your cluster.
                        scheduler=SchedulerConfiguration(
                            runner_type='SlurmRunner',
                            parameters={
                                'partition': 'gpu',
                                'ntasks': 4,
                                'cpus_per_task': 2,
                                'mem': '16G',
                                'time': '00:30:00'
                            }
                        ),
                        parallelism=ParallelismPolicy(
                            max_concurrent=4,
                            retry_max=2,
                            timeout_sec=300
                        )
                    ),
                ]
            )
        ],
        
        objectives=[
            ObjectiveDefinition(name='f1', direction='minimize'),
            ObjectiveDefinition(name='f2', direction='minimize'),
        ]
    )
    
    return workflow


# ============================================================================
# Example 3: Workflow with ContainerEvaluator
# ============================================================================

def example_workflow_with_containers():
    """Define a direct Docker job writing /tmp/aid2e_container_output/objectives.json.

    Execution requires Docker and a ten-variable qualified design point.
    This example only constructs the workflow.
    """
    
    output_dir = Path('/tmp/aid2e_container_output')
    command = (
        'python /app/examples/dtlz2/dtlz2_evaluator.py '
        + ' '.join(f'--x{i} "$X{i}"' for i in range(1, 11))
        + ' --output /output/objectives.json --repeat 0'
    )
    workflow = WorkflowDefinition(
        name='containerized_evaluation',
        description='Direct Docker execution; no scheduler configured',
        branches=[
            BranchDefinition(
                name='main',
                stages=[
                    StageDefinition(
                        name='evaluate_containers',
                        jobs=[
                            JobDefinition(
                                name='dtlz2_container',
                                command=command,
                                payload={
                                    'evaluator_type': 'container',
                                    'image': 'python:3.11-slim',
                                    'container_command': ['/bin/sh', '-c', quote(command)],
                                    'volumes': {
                                        quote(str(REPO_ROOT)): '/app:ro',
                                        str(output_dir): '/output',
                                    },
                                    'environment': {
                                        f'X{i}': f'{{{{design_point.DTLZ2_variables.x{i}}}}}'
                                        for i in range(1, 11)
                                    },
                                },
                                resources={'memory': '4g', 'cpus': '2'},
                                outputs=[
                                    ArtifactSpec(path=str(output_dir / 'objectives.json'), format='json')
                                ],
                            )
                        ],
                    )
                ]
            )
        ]
    )

    return workflow


# ============================================================================
# Example 4: Stage Scheduler Resolution
# ============================================================================

def example_scheduler_resolution():
    """Demonstrate stage scheduler resolution hierarchy."""
    
    workflow = WorkflowDefinition(
        name='scheduler_demo',
        
        # Level 1: Workflow scheduler
        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            parameters={'n_jobs': 2}
        ),
        
        branches=[
            BranchDefinition(
                name='branch1',
                # Level 2: Branch scheduler
                scheduler=SchedulerConfiguration(
                    runner_type='JobLibRunner',
                    parameters={'n_jobs': 4}
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
                            parameters={'partition': 'gpu'}
                        )
                    ),
                ]
            ),
            BranchDefinition(
                name='branch2',
                scheduler=None,  # Uses workflow scheduler
                stages=[
                    StageDefinition(
                        name='stage_uses_workflow',
                        jobs=[JobDefinition(name='job3', command='echo "hi"')],
                        scheduler=None  # Uses workflow scheduler (n_jobs=2)
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
    print("stage_uses_workflow:")
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
    print(f"Workflow: {workflow.name} (definition only; execution requires Docker)")
    
    print("\n" + "=" * 70)
    print("Example 4: Scheduler Resolution")
    print("=" * 70)
    example_scheduler_resolution()
