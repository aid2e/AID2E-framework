"""Workflow configuration models for multi-stage, multi-objective orchestration.

Defines DAG-based workflows with branches, stages, jobs, and objective computation specs.
Reuses ObjectiveDefinition from objectives.py for unified objective specification.

Key concepts:
    Workflow: An end-to-end evaluation unit (one design point evaluation).
    Branch: Optional subgraph inside a workflow (useful for multiple independent pipelines).
    Stage/Layer: Logical step group where multiple jobs run in parallel (fan-out).
    Job/Task: Smallest schedulable unit (one simulation, one training run, etc).
    Scheduler: Runtime executor for jobs (submit, monitor, collect status/artifacts).

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, field_validator
from aid2e.utilities.configurations.objectives import ObjectiveDefinition, ObjectivePlanSpec, ObjectiveDirection
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration


class CombinedObjectiveMetric(BaseModel):
    """Metric emitted by a combined objective plan.

    Attributes:
        name: Objective name (e.g., "f1").
        direction: Optimization direction for this metric.
        metric_key: Key in the plan output to extract this metric.
    """

    name: str = Field(..., description="Objective metric name")
    direction: ObjectiveDirection = Field(..., description="Direction for this metric")
    metric_key: str = Field(..., description="Key in plan output for this metric")


class CombinedObjectivePlan(BaseModel):
    """Combined objective execution producing multiple metrics in one plan.

    Attributes:
        name: Identifier for the combined objective bundle.
        objective_plan: Plan executed once to emit multiple metrics.
        metrics: Metrics extracted from the plan output with their directions.
        scheduler: Optional scheduler default for this combined plan.
    """

    name: str = Field(..., description="Combined objective bundle name")
    objective_plan: ObjectivePlanSpec = Field(..., description="Plan producing multiple metrics")
    metrics: list[CombinedObjectiveMetric] = Field(
        ..., min_items=1, description="Metrics emitted by this plan"
    )
    scheduler: Optional[SchedulerConfiguration] = Field(
        default=None,
        description="Scheduler default for this combined plan",
    )


class ParallelismPolicy(BaseModel):
    """Policy for parallel job execution within a stage.
    
    Attributes:
        max_concurrent: Maximum jobs to run concurrently in a stage.
        retry_max: Maximum retries on job failure.
        timeout_sec: Timeout per job in seconds.
        
    Example:
        >>> policy = ParallelismPolicy(max_concurrent=4, retry_max=2, timeout_sec=300)
    """
    max_concurrent: int = Field(default=4, ge=1, description="Max concurrent jobs in stage")
    retry_max: int = Field(default=2, ge=0, description="Max retries per failed job")
    timeout_sec: int = Field(default=300, ge=1, description="Timeout per job (seconds)")


class ArtifactSpec(BaseModel):
    """Output artifact specification for a stage.
    
    Defines expected output files that stages/jobs produce.
    
    Attributes:
        path: File path pattern (e.g., "objectives_*.json").
        format: File format ("json", "yaml", "csv", or "root").
        
    Example:
        >>> artifact = ArtifactSpec(path="objectives_*.json", format="json")
    """
    path: str = Field(..., description="File path pattern (e.g., 'output_*.json')")
    format: str = Field(default="json", pattern="^(json|yaml|csv|root)$", description="File format")


class JobDefinition(BaseModel):
    """Single job/task definition within a stage.
    
    A job is the smallest schedulable unit (e.g., one simulation, training run, etc).
    Jobs can be expanded from a template via job_factory.
    
    Attributes:
        name: Job name (e.g., "simulate").
        command: Executable command (e.g., "python scripts/dtlz2_problem.py").
        payload: Command arguments/payload (free-form dict, supports template substitution).
        rule: Optional template for constructing final command from payload.
              Uses format: "{command} {payload[key1]} {payload[key2]}" etc.
              If not specified, defaults to "{command}" (just execute command).
        resources: Resource requirements (free-form dict, e.g., {"memory": "4GB"}).
        outputs: Output artifacts this job produces.
        
    Example:
        >>> job = JobDefinition(
        ...     name="dtlz2_evaluate",
        ...     command="python scripts/dtlz2_problem.py",
        ...     rule="{command} {payload[design_params_file]} {payload[output_dir]} {payload[job_id]}",
        ...     payload={
        ...         "design_params_file": "{input_design_params}",
        ...         "output_dir": "{output_dir}",
        ...         "job_id": "{job_id}"
        ...     },
        ...     outputs=[ArtifactSpec(path="objectives_*.json", format="json")]
        ... )
        
    Notes:
        - Payload supports template substitution: {job_id}, {output_dir}, {stage_outputs[stage_name]}
        - Rule template follows experimental_stack.py StackLayer pattern
        - Resources dict is executor-dependent (e.g., JobLibRunner ignores, SlurmRunner uses)
    """
    name: str = Field(..., description="Job name")
    command: str = Field(..., description="Executable command")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Command arguments and metadata")
    rule: Optional[str] = Field(
        default=None,
        description="Template rule for command construction (e.g., '{command} {payload[input]} {payload[output]}')"
    )
    resources: Dict[str, Any] = Field(default_factory=dict, description="Resource requirements")
    outputs: List[ArtifactSpec] = Field(default_factory=list, description="Output artifacts")


class JobFactory(BaseModel):
    """Factory for generating multiple jobs from a template.
    
    Enables fan-out: creating N parallel jobs from one job definition.
    Useful for evaluating multiple design points in parallel.
    
    Attributes:
        type: Factory type ("range", "enumerate", "Cartesian", etc).
        params: Factory-specific parameters (e.g., {"n": 4} for range).
        
    Example:
        >>> # Create 4 parallel design point evaluations
        >>> factory = JobFactory(type="range", params={"n": 4})
        
    Notes:
        - "range" type: creates N copies with job_id = 0..N-1
        - "enumerate" type: creates one job per item in a list
        - "Cartesian" type: creates N_A * N_B jobs from two parameter sets
    """
    type: str = Field(default="range", description="Factory type (range, enumerate, Cartesian, etc)")
    params: Dict[str, Any] = Field(default_factory=dict, description="Factory parameters")


class StageDefinition(BaseModel):
    """Stage/layer definition with jobs and scheduler.
    
    A stage is a logical step group where multiple jobs run in parallel (fan-out),
    then their outputs feed into downstream stages (fan-in).
    
    Attributes:
        name: Stage name (e.g., "evaluate", "aggregate").
        jobs: Job definitions to execute (usually one template, expanded via job_factory).
        job_factory: Optional factory for expanding jobs (e.g., N parallel evals).
        scheduler: Stage-level scheduler (optional, inherits global if not set).
        parallelism: Parallelism policy for this stage.
        outputs: Output artifact specs produced by this stage.
        
    Example:
        >>> stage = StageDefinition(
        ...     name="evaluate",
        ...     jobs=[
        ...         JobDefinition(
        ...             name="dtlz2_evaluate",
        ...             command="python scripts/dtlz2_problem.py",
        ...             payload={...},
        ...             outputs=[ArtifactSpec(path="objectives_*.json", format="json")]
        ...         )
        ...     ],
        ...     job_factory=JobFactory(type="range", params={"n": 4}),
        ...     parallelism=ParallelismPolicy(max_concurrent=4, retry_max=2),
        ...     outputs=[ArtifactSpec(path="objectives_*.json", format="json")]
        ... )
        
    Notes:
        - job_factory expands the first job in jobs list to N parallel jobs
        - scheduler overrides global scheduler (from WorkflowsConfiguration)
        - outputs are collected after all jobs complete
    """
    name: str = Field(..., description="Stage name")
    jobs: List[JobDefinition] = Field(default_factory=list, description="Job definitions")
    job_factory: Optional[JobFactory] = Field(default=None, description="Job expansion factory")
    scheduler: Optional[SchedulerConfiguration] = Field(default=None, description="Stage-level scheduler override")
    parallelism: ParallelismPolicy = Field(default_factory=ParallelismPolicy, description="Parallelism policy")
    outputs: List[ArtifactSpec] = Field(default_factory=list, description="Output artifacts")


class BranchDefinition(BaseModel):
    """Branch definition (optional, for organizing stages in a DAG).
    
    A branch is an optional subgraph inside a workflow, useful when you want
    multiple independent pipelines under one workflow (e.g., "physics sim" branch
    + "surrogate" branch). Stages within a branch are executed in topological order.
    
    Attributes:
        name: Branch name (e.g., "main", "physics_sim", "surrogate").
        stages: List of stages in DAG order (assumes simple sequential order; extend with explicit DAG if needed).
        scheduler: Optional branch-level scheduler default (used if stage not set).
        
    Example:
        >>> branch = BranchDefinition(
        ...     name="main",
        ...     stages=[
        ...         StageDefinition(name="evaluate", ...),
        ...         StageDefinition(name="aggregate", ...)
        ...     ]
        ... )
        
    Notes:
        - Multiple branches in one workflow execute independently
        - For complex DAGs, extend this model with explicit edge definitions
    """
    name: str = Field(..., description="Branch name")
    stages: List[StageDefinition] = Field(default_factory=list, description="Stages in execution order")
    scheduler: Optional[SchedulerConfiguration] = Field(
        default=None,
        description="Branch-level scheduler default (overrides workflow, used if stage unset)",
    )


class WorkflowDefinition(BaseModel):
    """Workflow definition with branches, objectives, and scheduler defaults.
    
    A workflow is an end-to-end evaluation unit (e.g., one design point evaluation).
    It consists of optional branches, each with multiple stages, and defines the
    objectives to compute from the outputs.
    
    Attributes:
        name: Workflow name (e.g., "dtlz2_eval").
        description: Optional description.
        branches: Workflow branches (optional, defaults to single implicit branch if missing).
        objectives: Objectives to compute (reuses ObjectiveDefinition).
        combined_objectives: Optional combined plans emitting multiple metrics in one run.
        scheduler: Workflow-level scheduler default (used if branch/stage unset).
        
    Notes:
        - If branches is empty, executor creates single implicit branch
        - Objectives are unified model (ObjectiveDefinition) for consistency
    """
    name: str = Field(..., description="Workflow name")
    description: Optional[str] = Field(default=None, description="Workflow description")
    stack_type: Optional[str] = Field(default=None,description="Experimental stack type for workflow-level geometry prep")
    branches: List[BranchDefinition] = Field(default_factory=list, description="Workflow branches (optional)")
    objectives: List[ObjectiveDefinition] = Field(
        default_factory=list,
        description="Objectives to compute (reuses ObjectiveDefinition)"
    )
    combined_objectives: List[CombinedObjectivePlan] = Field(
        default_factory=list,
        description="Combined objective plans emitting multiple metrics in one run",
    )
    scheduler: Optional[SchedulerConfiguration] = Field(
        default=None,
        description="Workflow-level scheduler default (overrides global, used if branch/stage unset)",
    )
    stack_type: Optional[str] = Field(default=None,description="Experimental stack type for workflow-level geometry prep")

    def get_implicit_branch(self) -> BranchDefinition:
        """Get or create single implicit branch if branches list is empty.
        
        Returns:
            Single implicit branch if branches is empty, else raises error.
            
        Raises:
            ValueError: If branches list is not empty.
        """
        if self.branches:
            raise ValueError("Branches already defined; cannot use implicit branch")
        return BranchDefinition(name="implicit")


class WorkflowsConfiguration(BaseModel):
    """Top-level workflows configuration.
    
    Container for multiple independent workflows (e.g., one per objective in a
    holistic optimization). Each workflow can have its own stages, scheduler, and
    objective specs.
    
    Attributes:
        workflows: List of independent workflows.
        global_scheduler: Default scheduler for all stages (can be overridden per-stage).
        
    Example:
        >>> config = WorkflowsConfiguration(
        ...     workflows=[
        ...         WorkflowDefinition(name="dtlz2_eval", ...),
        ...         WorkflowDefinition(name="physics_sim", ...)
        ...     ],
        ...     global_scheduler=SchedulerConfiguration(
        ...         runner_type="JobLibRunner",
        ...         joblib=JobLibRunnerConfig(n_jobs=-1)
        ...     )
        ... )
        
    Notes:
        - global_scheduler is inherited by all stages unless overridden
        - workflows list must be non-empty
        - Useful for Option B: multiple independent workflows per objective
    """
    workflows: List[WorkflowDefinition] = Field(..., min_items=1, description="List of workflows")
    global_scheduler: Optional[SchedulerConfiguration] = Field(
        default=None,
        description="Default scheduler for all stages (can be overridden per-stage)"
    )
    
    @field_validator('workflows')
    @classmethod
    def validate_unique_workflow_names(cls, workflows: List[WorkflowDefinition]) -> List[WorkflowDefinition]:
        """Ensure all workflow names are unique.
        
        Args:
            workflows: List of workflow definitions.
            
        Returns:
            Same list if valid.
            
        Raises:
            ValueError: If duplicate workflow names found.
        """
        names = [w.name for w in workflows]
        if len(set(names)) != len(names):
            raise ValueError("Workflow names must be unique")
        return workflows
