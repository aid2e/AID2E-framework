#!/usr/bin/env python3
"""Integration example: Schedulers + Workflows + Configurations.

Shows how JobLibScheduler integrates with workflow configs and objectives.
This is a preview of Step 4 (Extend FullConfig with workflows).

The example also demonstrates scheduler lookup through the registry, scheduler
configuration models, a prepare -> evaluate -> aggregate workflow with a
stage-specific scheduler, a container workflow configured for Slurm, parallel
stage execution, and stage, branch, workflow, and global scheduler resolution.
It also documents the current rejection of workflow Python evaluators selected
for Slurm execution.

Run: python examples/dtlz2/python_api/dtlz2_scheduler.py
"""

from __future__ import annotations

import json
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List

from aid2e.optimizers.base import Trial
from aid2e.utilities import build_workflow_executor_from_config
from aid2e.utilities.configurations import load_config
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
    ObjectivePlanSpec,
    ScriptObjective,
    StepPlanSpec,
    StepStage,
)
from aid2e.utilities.configurations.scheduler_cascade import (
    resolve_scheduler_cascade,
)
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration
from aid2e.schedulers.JobLib.config import JobLibRunnerConfig
from aid2e.schedulers.Slurm import SlurmRunnerConfig, SlurmScheduler
from aid2e.utilities.workflows import DAGExecutor


REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SLURM_SETUP_COMMANDS = [
    "module load miniforge3/24.9.2-0",
    "conda activate env_AID2E",
]


def compute_with_context(context: Any, scale: float = 1.0) -> Dict[str, float]:
    """Return a tiny deterministic payload from design-point context."""
    design_point = getattr(context, "design_point", {}) or {}
    base = float(design_point.get("DTLZ2_variables.x1", 0.0))
    return {"f1": base * scale, "f2": (1.0 - base) * scale}


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
                objective_plan=ObjectivePlanSpec(
                    steps=StepPlanSpec(
                        stages=[
                            StepStage(
                                name='evaluate_f1',
                                script=ScriptObjective(
                                    path='scripts/dtlz2_problem.py',
                                    output_file='objectives.json',
                                    timeout_sec=600,
                                ),
                                produces_objective=True,
                            )
                        ]
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


# ============================================================================
# Workflow Definition with Stage-specific Schedulers
# ============================================================================

def example_workflow_definition():
    """Define a complete workflow with multiple stages and schedulers."""

    workflow = WorkflowDefinition(
        name='dtlz2_evaluation',
        description='Evaluate DTLZ2 problem with multiple stages',

        # Global default scheduler
        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            parameters=JobLibRunnerConfig(n_jobs=-1).model_dump(),
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
                        # STAGE-SPECIFIC SCHEDULER (overrides global!)
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
# Workflow with ContainerEvaluator
# ============================================================================

def example_workflow_with_containers():
    """Workflow using Docker containers for evaluation."""

    workflow = WorkflowDefinition(
        name='containerized_evaluation',
        description='Evaluate using Docker containers',

        scheduler=SchedulerConfiguration(
            runner_type='JobLibRunner',
            parameters=JobLibRunnerConfig(n_jobs=4).model_dump(),
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
                                    'evaluator_type': 'container',
                                    'image': 'physics-sim:2.0',
                                    'volumes': {
                                        '/host/data': '/data',
                                        '/host/output': '/output'
                                    },
                                    'environment': {
                                        'X1': '{{design_point.x1}}',
                                        'X2': '{{design_point.x2}}',
                                        'OUTPUT_DIR': '/output'
                                    },
                                },
                                resources={
                                    'memory': '8g',
                                    'cpus': '4'
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
                            parameters={
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
        parameters=joblib_config.model_dump(),
        max_retries=3,
        monitor_interval=30,
    )
    parsed_config = scheduler_config.parse_runner_params()
    
    print(f"Scheduler type: {scheduler_config.runner_type}")
    print(f"  JobLib jobs: {parsed_config.n_jobs}")
    print(f"  Backend: {parsed_config.backend}")
    print(f"  Timeout: {parsed_config.timeout}s")
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


# ============================================================================
# Example 6: Stage Scheduler Resolution
# ============================================================================

def example_scheduler_resolution():
    """Demonstrate stage, branch, workflow, and global scheduler resolution."""
    print("\n" + "=" * 70)
    print("Example 6: Scheduler Resolution")
    print("=" * 70)

    # Global scheduler: lowest-priority default.
    global_scheduler = SchedulerConfiguration(
        runner_type="JobLibRunner",
        parameters={"n_jobs": 2},
    )

    # Workflow scheduler: overrides the global scheduler.
    workflow = WorkflowDefinition(
        name="scheduler_demo",
        scheduler=SchedulerConfiguration(
            runner_type="JobLibRunner",
            parameters={"n_jobs": 3},
        ),
        branches=[
            BranchDefinition(
                name="branch_with_scheduler",
                # Branch scheduler: overrides workflow and global schedulers.
                scheduler=SchedulerConfiguration(
                    runner_type="JobLibRunner",
                    parameters={"n_jobs": 4},
                ),
                stages=[
                    StageDefinition(
                        name="stage_uses_branch",
                        jobs=[JobDefinition(name="job1", command='echo "branch"')],
                    ),
                    StageDefinition(
                        name="stage_uses_own",
                        jobs=[JobDefinition(name="job2", command='echo "stage"')],
                        # Stage scheduler: highest-priority override.
                        scheduler=SchedulerConfiguration(
                            runner_type="SlurmRunner",
                            parameters={"partition": "gpu"},
                        ),
                    ),
                ],
            ),
            BranchDefinition(
                name="branch_uses_workflow",
                stages=[
                    StageDefinition(
                        name="stage_uses_workflow",
                        jobs=[JobDefinition(name="job3", command='echo "workflow"')],
                    )
                ],
            ),
        ],
    )

    # Resolution order: stage -> branch -> workflow -> global.
    print("\nScheduler resolution:")
    print("-" * 60)
    for branch in workflow.branches:
        for stage in branch.stages:
            scheduler = resolve_scheduler_cascade(
                stage_scheduler=stage.scheduler,
                branch_scheduler=branch.scheduler,
                workflow_scheduler=workflow.scheduler,
                global_scheduler=global_scheduler,
            )
            print(f"{stage.name}: {scheduler.runner_type}")

    # With no scheduler at stage, branch, or workflow level, use the global one.
    scheduler = resolve_scheduler_cascade(global_scheduler=global_scheduler)
    print(f"stage_uses_global: {scheduler.runner_type}")


# ============================================================================
# Example 7: Slurm Workflow Python Evaluator Rejection
# ============================================================================

def example_slurm_python_evaluator_rejection():
    """Demonstrate the current Slurm workflow Python-evaluator boundary.

    The low-level Slurm scheduler can translate importable functions with
    JSON-serializable parameters into worker commands. DAGExecutor does not yet
    translate workflow jobs configured with ``evaluator_type='python'`` into
    that representation, so it rejects the job before Slurm submission.

    This example intentionally exercises and verifies that rejection. The
    ``compute_with_context`` callable is therefore not executed.
    """
    print("\n" + "=" * 70)
    print("Example 7: Slurm Workflow Python Evaluator Rejection")
    print("=" * 70)

    python_job = JobDefinition(
        name="python_evaluator",
        command="python",
        payload={
            "evaluator_type": "python",
            "python_callable": compute_with_context,
            "op_kwargs": {"scale": 2.0},
        },
    )
    workflow = WorkflowDefinition(
        name="slurm_python_evaluator_rejection",
        branches=[
            BranchDefinition(
                name="main",
                stages=[
                    StageDefinition(
                        name="evaluate",
                        jobs=[python_job],
                    )
                ],
            )
        ],
        objectives=[],
    )

    # Use temporary workflow directories so the expected failure does not
    # leave example output behind. The rejection occurs before sbatch is used.
    with tempfile.TemporaryDirectory(prefix="aid2e_slurm_python_rejection_") as tmp:
        root = Path(tmp)
        executor = DAGExecutor(
            workflow,
            scheduler_config={
                "runner_type": "SlurmRunner",
                "config": SlurmRunnerConfig(),
            },
            output_dir=str(root / "output"),
            work_dir=str(root / "work"),
        )

        # Design point from optimizer
        design_point = {"DTLZ2_variables.x1": 0.25}
        try:
            executor.execute(design_point)
        except ValueError as exc:
            expected = "SlurmScheduler v1 does not support"
            if expected not in str(exc):
                raise
            print(f"Expected rejection: {exc}")
        else:
            raise RuntimeError(
                "Expected Slurm workflow Python evaluator to be rejected"
            )


# ============================================================================
# Example 8: Config-driven Slurm Design-JSON Workflow
# ============================================================================

def example_config_driven_slurm_design_json(
    output_root: Path | None = None,
) -> Dict[str, Any]:
    """Run the config-driven Slurm design-JSON workflow example end to end.

    This example loads the maintained full Slurm configuration, selects one
    workflow by name, executes one manually supplied design point, verifies
    the objective and artifact outputs, and writes a JSON execution summary.

    It requires a Slurm submission environment and is therefore not executed
    by the default ``__main__`` example sequence.
    """
    print("\n" + "=" * 70)
    print("Example 8: Config-driven Slurm Design-JSON Workflow")
    print("=" * 70)

    config_path = (
        REPO_ROOT
        / "examples"
        / "dtlz2"
        / "configurations"
        / "dtlz2_ax_slurm.yml"
    )
    if output_root is None:
        output_root = REPO_ROOT / "experimental_tests" / "output"
    run_dir = output_root / (
        f"slurm_design_json_example_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    config = load_config(str(config_path))
    if config.scheduler is None or config.workflows is None:
        raise RuntimeError(
            "Expected scheduler and workflows sections in the Slurm "
            "design-JSON example"
        )

    executor = build_workflow_executor_from_config(
        config.workflows,
        problem_cfg=config.problem,
        scheduler_cfg=config.scheduler,
        workflow_name="dtlz2_slurm_eval",
        base_output_dir=str(run_dir),
        log_level="INFO",
    )

    design_point = {
        "DTLZ2_variables.x1": 0.22,
        "DTLZ2_variables.x2": 0.61,
        "DTLZ2_variables.x3": 0.41,
        "DTLZ2_variables.x4": 0.56,
        "DTLZ2_variables.x5": 0.44,
        "DTLZ2_variables.x6": 0.52,
        "DTLZ2_variables.x7": 0.47,
        "DTLZ2_variables.x8": 0.63,
        "DTLZ2_variables.x9": 0.38,
        "DTLZ2_variables.x10": 0.49,
    }
    objectives = executor.execute(design_point)
    if not objectives or "f1" not in objectives or "f2" not in objectives:
        raise RuntimeError(f"Expected f1/f2 objectives, got: {objectives}")

    design_files = sorted(
        str(path) for path in executor.work_dir.glob("*/*/design_point.json")
    )
    result_files = sorted(
        str(path) for path in executor.output_dir.glob("*/*/objectives.json")
    )
    stdout_logs = sorted(
        str(path) for path in executor.output_dir.glob("*/*/stdout.log")
    )
    stderr_logs = sorted(
        str(path) for path in executor.output_dir.glob("*/*/stderr.log")
    )
    if not design_files:
        raise RuntimeError(
            "Expected the Slurm workflow to materialize at least one "
            "design_point.json file"
        )
    if not result_files:
        raise RuntimeError(
            "Expected the Slurm workflow to produce at least one objectives.json file"
        )

    summary = {
        "config_path": str(config_path),
        "design_point": design_point,
        "objectives": objectives,
        "work_dir": str(executor.work_dir),
        "output_dir": str(executor.output_dir),
        "design_files": design_files,
        "result_files": result_files,
        "stdout_logs": stdout_logs,
        "stderr_logs": stderr_logs,
        "global_xcom_keys": sorted(executor.global_xcom.keys()),
    }
    summary_path = run_dir / "run_config_driven_slurm_design_json.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


# ============================================================================
# Example 9: Direct Slurm Parallel Stage Submission
# ============================================================================

def build_dtlz2_point(index: int) -> Dict[str, float]:
    """Build one deterministic DTLZ2 design point for the parallel stage."""
    return {
        "DTLZ2_variables.x1": 0.10 + 0.05 * index,
        "DTLZ2_variables.x2": 0.65 - 0.02 * index,
        "DTLZ2_variables.x3": 0.35 + 0.01 * index,
        "DTLZ2_variables.x4": 0.58 - 0.01 * index,
        "DTLZ2_variables.x5": 0.42 + 0.01 * index,
    }


def make_slurm_scheduler(run_dir: Path) -> SlurmScheduler:
    """Construct the Slurm scheduler used by the parallel-stage example."""
    return SlurmScheduler(
        config=SlurmRunnerConfig(
            job_name_prefix="aid2e_multi10",
            setup_commands=list(DEFAULT_SLURM_SETUP_COMMANDS),
            submit_working_dir=str(run_dir),
            runtime_working_dir=str(REPO_ROOT),
            poll_interval=2,
        )
    )


def example_slurm_parallel_stage(
    output_root: Path | None = None,
) -> Dict[str, Any]:
    """Submit ten Slurm jobs together, monitor them, and collect outputs.

    Slurm decides whether the submitted jobs run simultaneously based on the
    cluster's available resources and scheduling policy. This example requires
    a Slurm submission environment and is therefore not executed by the
    default ``__main__`` example sequence.
    """
    print("\n" + "=" * 70)
    print("Example 9: Direct Slurm Parallel Stage Submission")
    print("=" * 70)

    if output_root is None:
        output_root = REPO_ROOT / "experimental_tests" / "output"
    run_dir = output_root / (
        f"slurm_ten_simultaneous_jobs_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    scheduler = make_slurm_scheduler(run_dir)
    job_definitions: List[Dict[str, Any]] = []
    expected_outputs: Dict[str, Path] = {}

    for index in range(10):
        design_point = build_dtlz2_point(index)
        job_name = f"dtlz2_design_{index}"
        design_path = run_dir / "designs" / f"{job_name}.json"
        output_path = run_dir / "results" / f"{job_name}.json"
        Trial(index=index, parameters=design_point, status="pending").save_to_json(
            design_path
        )

        job_definitions.append(
            {
                "name": job_name,
                "command": (
                    "python "
                    "examples/dtlz2/dtlz2_evaluator.py "
                    f"--design {design_path} "
                    f"--output {output_path} "
                    f"--label {job_name} "
                    "--sleep-sec 0.6 "
                    "--repeat 3"
                ),
                "payload": {"execution_dir": str(run_dir / "runtime" / job_name)},
                "outputs": [{"path": str(output_path), "format": "json"}],
                "resources": {"time": "00:05:00"},
            }
        )
        expected_outputs[job_name] = output_path

    stage_id = scheduler.submit_stage(
        "ten_dtlz2_designs",
        job_definitions,
        parallelism_policy={"poll_interval": 1},
        working_dir=str(run_dir / "scheduler"),
    )

    history: List[Dict[str, Any]] = []
    while True:
        stage_status = scheduler.check_stage_status(stage_id)
        counts = Counter(job.status for job in stage_status.job_statuses or [])
        snapshot = {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "stage_status": stage_status.status,
            "completed_jobs": stage_status.completed_jobs,
            "total_jobs": stage_status.total_jobs,
            "status_counts": dict(counts),
        }
        history.append(snapshot)
        print(f"[ten-jobs] {snapshot}")
        if stage_status.status in {"completed", "failed", "cancelled"}:
            break
        time.sleep(1)

    result = scheduler.get_stage_results(stage_id)
    if not result.success:
        raise RuntimeError(
            f"Expected all 10 jobs to succeed, got: {result.error_message}"
        )
    if len(result.job_statuses) != 10:
        raise RuntimeError(
            f"Expected 10 job statuses, got {len(result.job_statuses)}"
        )
    if any(job.status != "completed" for job in result.job_statuses):
        raise RuntimeError("Expected all ten jobs to complete successfully")

    per_job_outputs = {}
    for job_status in result.job_statuses:
        if (
            not job_status.outputs
            or "f1" not in job_status.outputs
            or "f2" not in job_status.outputs
        ):
            raise RuntimeError(
                f"Missing objective outputs for job {job_status.job_id}: "
                f"{job_status.outputs}"
            )
        per_job_outputs[job_status.job_id] = job_status.outputs

    for job_name, output_path in expected_outputs.items():
        if not output_path.exists():
            raise RuntimeError(
                f"Expected output file missing for {job_name}: {output_path}"
            )

    summary = {
        "stage_id": stage_id,
        "history": history,
        "jobs": [
            {
                "job_id": job_status.job_id,
                "status": job_status.status,
                "return_code": job_status.return_code,
                "slurm_job_id": (job_status.metrics or {}).get("slurm_job_id"),
                "outputs": job_status.outputs,
            }
            for job_status in result.job_statuses
        ],
        "design_files": sorted(
            str(path) for path in (run_dir / "designs").glob("*.json")
        ),
        "result_files": sorted(
            str(path) for path in (run_dir / "results").glob("*.json")
        ),
    }
    summary_path = run_dir / "run_slurm_ten_simultaneous_jobs.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary


if __name__ == '__main__':
    example_basic_scheduler()
    example_with_registry()
    example_workflow_with_scheduler()

    print("\n" + "=" * 70)
    print("Workflow Definition with Stage-specific Schedulers")
    print("=" * 70)
    workflow = example_workflow_definition()
    print(f"Workflow: {workflow.name}")
    print(f"Stages: {[s.name for b in workflow.branches for s in b.stages]}")
    for branch in workflow.branches:
        for stage in branch.stages:
            scheduler_desc = stage.scheduler or "(inherited)"
            print(f"  {stage.name}: scheduler = {scheduler_desc}")

    print("\n" + "=" * 70)
    print("Workflow with Containers on Slurm")
    print("=" * 70)
    workflow = example_workflow_with_containers()
    print(f"Workflow: {workflow.name}")
    stage = workflow.branches[0].stages[0]
    print(f"Stage: {stage.name}")
    print(f"Scheduler: {stage.scheduler.runner_type}")
    print(f"Container image: {stage.jobs[0].payload['image']}")

    example_scheduler_config()
    example_stage_execution()
    example_scheduler_resolution()
    example_slurm_python_evaluator_rejection()
    
    print("\n" + "=" * 70)
    print("✓ All integration examples completed successfully!")
    print("=" * 70)
