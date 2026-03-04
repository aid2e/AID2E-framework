#!/usr/bin/env python3
"""Integration example: Schedulers + Workflows + Configurations.

Shows how JobLibScheduler integrates with workflow configs and objectives.
This is a preview of Step 4 (Extend FullConfig with workflows).

Run: python3 scheduler_workflow_integration_example.py
"""

from aid2e.schedulers import (
    JobLibScheduler,
    get_scheduler,
)
from aid2e.utilities.configurations.workflow_config import (
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
    ObjectiveComputationSpec,
    ScriptObjective,
)
from aid2e.utilities.configurations.scheduler_config import (
    SchedulerConfiguration,
    JobLibRunnerConfig,
)


def example_basic_scheduler():
    """Example 1: Using JobLibScheduler directly."""
    print("=" * 70)
    print("Example 1: Basic JobLibScheduler Usage")
    print("=" * 70)
    
    scheduler = JobLibScheduler()
    
    # Define simple jobs
    jobs = [
        {
            'name': 'evaluate_1',
            'command': 'python -c "print(\'f1=1.0, f2=2.0\')"',
            'payload': {'design_id': 1},
            'outputs': []
        },
        {
            'name': 'evaluate_2',
            'command': 'python -c "print(\'f1=1.5, f2=2.5\')"',
            'payload': {'design_id': 2},
            'outputs': []
        },
    ]
    
    # Execute stage
    result = scheduler.run_stage(
        stage_name='evaluate',
        job_definitions=jobs,
        parallelism_policy={'max_concurrent': 2}
    )
    
    print(f"Stage: {result.stage_name}")
    print(f"Success: {result.success}")
    print(f"Jobs completed: {len(result.job_statuses)}")
    for status in result.job_statuses:
        print(f"  {status.job_id}: {status.status} (exit code: {status.return_code})")


def example_with_registry():
    """Example 2: Using scheduler registry to lookup schedulers."""
    print("\n" + "=" * 70)
    print("Example 2: Using Scheduler Registry")
    print("=" * 70)
    
    # Get scheduler class from registry
    SchedulerClass = get_scheduler('joblib')
    print(f"Retrieved scheduler class: {SchedulerClass.__name__}")
    
    # Create instance
    config = JobLibRunnerConfig(n_jobs=2, backend='threading')
    scheduler = SchedulerClass(config=config)
    
    jobs = [
        {'name': 'job_1', 'command': 'echo "Processing job 1"', 'payload': {}, 'outputs': []},
        {'name': 'job_2', 'command': 'echo "Processing job 2"', 'payload': {}, 'outputs': []},
    ]
    
    result = scheduler.run_stage('process', job_definitions=jobs)
    print(f"Result: {result.success} ({len(result.job_statuses)} jobs)")


def example_workflow_with_scheduler():
    """Example 3: Workflow + Scheduler integration."""
    print("\n" + "=" * 70)
    print("Example 3: Workflow + Scheduler Integration")
    print("=" * 70)
    
    # Define workflow structure
    workflow = WorkflowDefinition(
        name='dtlz2_eval',
        description='Evaluate design point using DTLZ2',
        branches=[
            BranchDefinition(
                name='main',
                stages=[
                    StageDefinition(
                        name='evaluate',
                        jobs=[
                            JobDefinition(
                                name='dtlz2_evaluate',
                                command='python scripts/dtlz2_problem.py',
                                payload={'design_id': 1},
                                outputs=[ArtifactSpec(path='objectives.json', format='json')]
                            )
                        ],
                        job_factory=JobFactory(type='range', params={'n': 1}),
                        parallelism=ParallelismPolicy(max_concurrent=1, retry_max=2, timeout_sec=300),
                    ),
                    StageDefinition(
                        name='aggregate',
                        jobs=[
                            JobDefinition(
                                name='aggregate',
                                command='echo "Aggregating results"',
                                payload={},
                                outputs=[]
                            )
                        ],
                    )
                ]
            )
        ],
        objectives=[
            ObjectiveDefinition(
                name='f1',
                direction=ObjectiveDirection.MINIMIZE,
                computation=ObjectiveComputationSpec(
                    script=ScriptObjective(
                        path='scripts/dtlz2_problem.py',
                        output_file='objectives.json',
                        timeout_sec=600
                    )
                )
            ),
            ObjectiveDefinition(
                name='f2',
                direction=ObjectiveDirection.MINIMIZE,
            ),
        ]
    )
    
    print(f"Workflow: {workflow.name}")
    print(f"  Description: {workflow.description}")
    print(f"  Branches: {len(workflow.branches)}")
    for branch in workflow.branches:
        print(f"    Branch '{branch.name}': {len(branch.stages)} stages")
        for stage in branch.stages:
            print(f"      Stage '{stage.name}': {len(stage.jobs)} jobs")
    print(f"  Objectives: {len(workflow.objectives)}")
    for obj in workflow.objectives:
        print(f"    {obj.name} ({obj.direction})")


def example_scheduler_config():
    """Example 4: SchedulerConfiguration and JobLibRunnerConfig."""
    print("\n" + "=" * 70)
    print("Example 4: SchedulerConfiguration Models")
    print("=" * 70)
    
    # Create scheduler config
    joblib_config = JobLibRunnerConfig(
        n_jobs=4,
        backend='loky',
        timeout=600,
        verbose=1
    )
    
    scheduler_config = SchedulerConfiguration(
        runner_type='JobLibRunner',
        joblib=joblib_config,
        max_retries=3,
        monitor_interval=30,
    )
    
    print(f"Scheduler type: {scheduler_config.runner_type}")
    print(f"  JobLib jobs: {scheduler_config.joblib.n_jobs}")
    print(f"  Backend: {scheduler_config.joblib.backend}")
    print(f"  Timeout: {scheduler_config.joblib.timeout}s")
    print(f"Global max retries: {scheduler_config.max_retries}")
    print(f"Monitor interval: {scheduler_config.monitor_interval}s")


def example_stage_execution():
    """Example 5: Execute a realistic workflow stage."""
    print("\n" + "=" * 70)
    print("Example 5: Realistic Stage Execution")
    print("=" * 70)
    
    scheduler = JobLibScheduler(
        config=JobLibRunnerConfig(n_jobs=3, backend='threading')
    )
    
    # Simulate DTLZ2 evaluation with 3 design points
    jobs = [
        {
            'name': f'design_{i}',
            'command': f'python -c "import json; print(json.dumps({{"f1": {1.0 + i*0.1}, "f2": {2.0 + i*0.2}}})"',
            'payload': {'design_id': i},
            'outputs': []
        }
        for i in range(3)
    ]
    
    result = scheduler.run_stage(
        stage_name='evaluate_designs',
        job_definitions=jobs,
        parallelism_policy={'max_concurrent': 3, 'retry_max': 2, 'timeout_sec': 60},
    )
    
    print(f"Stage: {result.stage_name}")
    print(f"Success: {result.success}")
    print(f"Total jobs: {len(result.job_statuses)}")
    print(f"Completed jobs: {sum(1 for s in result.job_statuses if s.status == 'completed')}")
    print(f"Failed jobs: {sum(1 for s in result.job_statuses if s.status == 'failed')}")
    
    print("\nJob Results:")
    for status in result.job_statuses:
        print(f"  {status.job_id}: {status.status} (exit: {status.return_code})")


if __name__ == '__main__':
    example_basic_scheduler()
    example_with_registry()
    example_workflow_with_scheduler()
    example_scheduler_config()
    example_stage_execution()
    
    print("\n" + "=" * 70)
    print("✓ All integration examples completed successfully!")
    print("=" * 70)
