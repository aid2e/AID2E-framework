"""DAG Executor for orchestrating workflow execution with evaluators.

The DAG Executor is the central orchestration engine that executes workflows
using the evaluator framework. It handles:
- Topological sorting of stages based on dependencies
- Context hierarchy (Branch → Stage → Job)
- Evaluator selection and execution
- XCom data passing between jobs
- Checkpoint logging and artifact collection
- Objective computation from outputs

Key workflow:
    1. Build DAG from workflow definition
    2. Topologically sort stages
    3. For each layer (stages that can run in parallel):
       - Create StageContext with parameters
       - Expand jobs via job_factory
       - For each job:
         - Create JobContext with design point
         - Select appropriate evaluator (Bash, Python, Container)
         - Execute evaluator.execute(context)
         - Log checkpoint
    4. Compute objectives from collected outputs
    5. Return objectives to optimizer

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import json
import logging
from datetime import datetime

from aid2e.utilities.configurations.problem_config import (
    ProblemConfiguration,
)
from .workflow_config import (
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobFactory,
)
from .dag_types import (
    DagDefinition,
    DagNode,
    DagNodeType,
    topological_sort,
)
from .execution_engine import (
    BaseExecutionEngine,
    BashExecutionEngine,
    PythonExecutionEngine,
    ContainerExecutionEngine,
    StackExecutionEngine,
    JobContext,
    StageContext,
    BranchContext,
    WorkflowSharedContext,
)
from .execution_logger import ExecutionLogger
from aid2e.utilities.configurations.stack_registry import StackRegistry

class DAGExecutor:
    """Executor for DAG-based workflow orchestration.
    
    Orchestrates workflow execution by:
    - Building DAG from workflow definition
    - Topologically sorting stages for correct execution order
    - Creating hierarchical contexts (Branch → Stage → Job)
    - Selecting and executing appropriate evaluators
    - Managing XCom data flow between jobs
    - Logging execution checkpoints
    - Computing objectives from outputs
    
    Attributes:
        workflow: Workflow definition to execute.
        base_output_dir: Base directory for all execution outputs.
        logger: Execution logger for checkpoints and logs.
        global_xcom: Shared XCom storage across all jobs.
        problem_config: Problem configuration for accessing stack-
                        dependent design space and environment
                        configuration (optional)
        
    Example:
        >>> workflow = WorkflowDefinition(name="dtlz2_eval", ...)
        >>> executor = DAGExecutor(workflow, output_dir="/tmp/runs")
        >>> design_point = {"x1": 0.5, "x2": 0.7}
        >>> objectives = executor.execute(design_point)
        >>> print(objectives)  # {"f1": 0.234, "f2": 0.876}
    """
    
    def __init__(
        self,
        workflow: WorkflowDefinition,
        base_output_dir: str = "/tmp/aid2e_runs",
        log_level: str = "INFO",
        problem_config: Optional[ProblemConfiguration] = None,
        scheduler_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize DAG Executor.
        
        Args:
            workflow: Workflow definition to execute.
            base_output_dir: Base directory for execution outputs.
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR).
            scheduler_config: Optional scheduler configuration dict with keys:
                - runner_type: str (e.g., "JobLibRunner", "PanDAiDDSRunner")
                - config: scheduler-specific config object or dict
        """
        self.workflow = workflow
        self.base_output_dir = Path(base_output_dir)
        self.log_level = log_level
        self.problem_config = problem_config
        self.scheduler_config = scheduler_config or {}
        
        # Create workflow-specific output directory
        workflow_dir = self.base_output_dir / workflow.name / datetime.now().strftime("%Y%m%d_%H%M%S")
        workflow_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir = workflow_dir
        
        # If provided, activate environment variables
        if self.problem_config is not None:
            if self.problem_config.environment_config is not None:
                self.problem_config.environment_config.activate()

        # Initialize logger
        self.logger = ExecutionLogger(
            job_name=f"executor_{workflow.name}",
            output_dir=str(self.output_dir),
            log_level=log_level,
        )
        
        # Global XCom storage: {job_id: {key: value}}
        self.global_xcom: Dict[str, Dict[str, Any]] = {}
        
        # Initialize scheduler if configured
        self.scheduler = None
        if self.scheduler_config:
            self.scheduler = self._create_scheduler()
        
        self.logger.log_info(f"Initialized DAGExecutor for workflow: {workflow.name}")
        self.logger.log_info(f"Output directory: {self.output_dir}")
        if self.scheduler:
            runner_type = self.scheduler_config.get("runner_type", "unknown")
            self.logger.log_info(f"Scheduler: {runner_type}")
    
    def _create_scheduler(self):
        """Create and initialize the scheduler from configuration.
        
        Returns:
            Initialized scheduler instance (BaseScheduler subclass).
            
        Raises:
            ValueError: If scheduler_config is invalid or scheduler type not found.
        """
        runner_type = self.scheduler_config.get("runner_type")
        if not runner_type:
            raise ValueError("scheduler_config must specify 'runner_type'")
        
        config = self.scheduler_config.get("config")
        
        # Import scheduler dynamically based on runner_type
        try:
            if runner_type == "JobLibRunner":
                from aid2e.schedulers.JobLib.runner import JobLibScheduler
                return JobLibScheduler(config=config)
            elif runner_type == "PanDAiDDSRunner":
                from aid2e.schedulers.PanDAiDDS.runner import PanDAiDDSScheduler
                return PanDAiDDSScheduler(config=config)
            elif runner_type == "SlurmRunner":
                from aid2e.schedulers.slurm.runner import SlurmScheduler
                return SlurmScheduler(config=config)
            else:
                raise ValueError(f"Unknown scheduler runner_type: {runner_type}")
        except ImportError as e:
            self.logger.log_error(
                f"Failed to import scheduler {runner_type}: {e}. "
                f"Make sure the scheduler module is installed."
            )
            raise ValueError(f"Scheduler {runner_type} not available: {e}") from e
        
    def execute(self, design_point: Dict[str, Any]) -> Dict[str, float]:
        """Execute workflow for a given design point.
        
        This is the main entry point for workflow execution. It orchestrates
        the entire workflow from start to finish and returns computed objectives.

        Args:
            design_point: Design point parameters (e.g., {"x1": 0.5, "x2": 0.7}).
            
        Returns:
            objectives: Computed objectives as {objective_name: value}.
            
        Raises:
            ValueError: If workflow is invalid or execution fails.
            
        Example:
            >>> design_point = {"x1": 0.5, "x2": 0.7, "x3": 0.3}
            >>> objectives = executor.execute(design_point)
            >>> print(objectives)  # {"f1": 0.234, "f2": 0.876}
        """

        self.logger.checkpoint(
            "workflow_start",
            "start",
            f"Starting workflow execution for design point: {design_point}",
            context={"design_point": design_point},
        )

        self.workflow_context = WorkflowSharedContext()

        try:
            if (
                self.problem_config is not None
                and self.problem_config.design_config is not None
                and self.workflow.stack_type is not None
            ):
                stack_class = StackRegistry.get_experimental_stack(self.workflow.stack_type)
                stack = stack_class()
                prepared_geometry_dir = stack.prepare_workflow_geometry(
                    workflow_dir=str(self.output_dir),
                    design_point=design_point,
                    problem_config=self.problem_config,
                    workflow_id=self.workflow.name,
                )
                self.workflow_context.parameters["prepared_geometry_dir"] = prepared_geometry_dir
                self.logger.log_info(f"Prepared geometry once at: {prepared_geometry_dir}")

            for branch in self._get_branches():
                self._execute_branch(branch, design_point)

            objectives = self._compute_objectives()

            self.logger.checkpoint(
                "workflow_complete",
                "success",
                f"Workflow execution completed. Objectives: {objectives}",
                context={"objectives": objectives},
            )

            return objectives
            
        except Exception as e:
            self.logger.checkpoint(
                "workflow_error",
                "error",
                f"Workflow execution failed: {str(e)}",
                context={"error": str(e)},
            )
            raise
    
    def _get_branches(self) -> List[BranchDefinition]:
        """Get branches from workflow (create implicit branch if none defined).
        
        Returns:
            List of branches to execute.
        """
        if self.workflow.branches:
            return self.workflow.branches
        else:
            # Create implicit branch from workflow stages (if any)
            # For now, return empty list if no branches defined
            # This can be extended to support legacy workflows with direct stages
            return []
    
    def _execute_branch(self, branch: BranchDefinition, design_point: Dict[str, Any]) -> None:
        """Execute a single branch.
        
        Args:
            branch: Branch definition to execute.
            design_point: Design point parameters.
        """
        self.logger.checkpoint(
            "branch_start",
            "start",
            f"Starting branch: {branch.name}",
            context={"branch_name": branch.name},
        )
        
        # Create branch context
        branch_context = BranchContext(
            branch_id=branch.name,
            parameters={},  # Can be extended to include branch-level params
        )
        
        # Build DAG from stages
        dag = self._build_dag_from_stages(branch.stages, branch.name)
        
        # Topologically sort stages
        try:
            topo_order = topological_sort(dag)
        except ValueError as e:
            self.logger.checkpoint(
                "branch_error",
                "error",
                f"Failed to sort branch DAG: {str(e)}",
                context={"branch_name": branch.name, "error": str(e)},
            )
            raise
        
        self.logger.log_info(
            f"Branch {branch.name} execution order: {topo_order.sorted_node_ids}"
        )
        
        # Execute stages layer by layer
        for layer_idx, layer in enumerate(topo_order.layers):
            self.logger.log_info(
                f"Executing layer {layer_idx} with {len(layer)} stages: "
                f"{[node.node_id for node in layer]}"
            )
            
            # Execute all stages in this layer (can be parallelized)
            for node in layer:
                stage = self._get_stage_by_name(branch.stages, node.node_id)
                if stage:
                    self._execute_stage(stage, branch_context, design_point)
        
        self.logger.checkpoint(
            "branch_complete",
            "success",
            f"Branch {branch.name} completed",
            context={"branch_name": branch.name},
        )
    
    def _build_dag_from_stages(
        self, stages: List[StageDefinition], branch_name: str
    ) -> DagDefinition:
        """Build DAG from stage list.
        
        For now, assumes simple sequential execution (each stage depends on previous).
        Can be extended to support explicit dependencies from stage definitions.
        
        Args:
            stages: List of stages in the branch.
            branch_name: Name of the parent branch.
            
        Returns:
            DagDefinition with nodes and edges.
        """
        nodes = []
        for idx, stage in enumerate(stages):
            depends_on = [stages[idx - 1].name] if idx > 0 else []
            node = DagNode(
                node_id=stage.name,
                node_type=DagNodeType.STAGE,
                depends_on=depends_on,
                description=f"Stage in branch {branch_name}",
            )
            nodes.append(node)
        
        return DagDefinition(
            name=f"dag_{branch_name}",
            nodes=nodes,
        )
    
    def _get_stage_by_name(
        self, stages: List[StageDefinition], stage_name: str
    ) -> Optional[StageDefinition]:
        """Find stage by name in stage list.
        
        Args:
            stages: List of stages to search.
            stage_name: Name of the stage to find.
            
        Returns:
            StageDefinition if found, None otherwise.
        """
        for stage in stages:
            if stage.name == stage_name:
                return stage
        return None
    
    def _execute_stage(
        self,
        stage: StageDefinition,
        branch_context: BranchContext,
        design_point: Dict[str, Any],
    ) -> None:
        """Execute a single stage.
        
        Args:
            stage: Stage definition to execute.
            branch_context: Parent branch context.
            design_point: Design point parameters.
        """
        self.logger.checkpoint(
            "stage_start",
            "start",
            f"Starting stage: {stage.name}",
            context={"stage_name": stage.name},
        )
        
        # Create stage context
        stage_context = StageContext(
            stage_id=stage.name,
            parameters=stage.parallelism.model_dump(),  # Include parallelism params
            branch_context=branch_context,
        )
        
        # Expand jobs from job_factory (if provided)
        jobs = self._expand_jobs(stage)
        
        self.logger.log_info(f"Stage {stage.name} has {len(jobs)} jobs to execute")
        
        # Check if scheduler is configured
        if self.scheduler:
            # Use scheduler to execute stage
            self._execute_stage_with_scheduler(
                stage, jobs, stage_context, design_point
            )
        else:
            # Execute jobs directly (legacy path)
            for job_idx, job in enumerate(jobs):
                job_id = f"{stage.name}_{job.name}_{job_idx}"
                self._execute_job(job, job_id, stage_context, design_point)
        
        self.logger.checkpoint(
            "stage_complete",
            "success",
            f"Stage {stage.name} completed with {len(jobs)} jobs",
            context={"stage_name": stage.name, "num_jobs": len(jobs)},
        )
    
    def _execute_stage_with_scheduler(
        self,
        stage: StageDefinition,
        jobs: List[JobDefinition],
        stage_context: StageContext,
        design_point: Dict[str, Any],
    ) -> None:
        """Execute a stage using the configured scheduler.
        
        Converts job definitions to scheduler format and handles result collection.
        
        Args:
            stage: Stage definition.
            jobs: Expanded list of jobs to execute.
            stage_context: Parent stage context.
            design_point: Design point parameters.
        """
        self.logger.log_info(f"Executing stage {stage.name} with scheduler")
        
        # Convert jobs to scheduler format
        job_definitions = []
        for job_idx, job in enumerate(jobs):
            job_id = f"{stage.name}_{job.name}_{job_idx}"
            
            # Create job context for this job
            job_context = JobContext(
                job_id=job_id,
                stage_id=stage_context.stage_id,
                workflow_id=self.workflow.name,
                design_point=design_point,
                xcom=self.global_xcom,
                stage_context=stage_context,
                execution_dir=str(self.output_dir / "jobs" / job_id),
                problem_config=self.problem_config,
                workflow_context=self.workflow_context,
            )
            
            # Ensure job execution directory exists
            Path(job_context.execution_dir).mkdir(parents=True, exist_ok=True)
            
            # Convert to scheduler job definition format
            scheduler_job = self._convert_job_to_scheduler_format(
                job, job_id, job_context
            )
            job_definitions.append(scheduler_job)
        
        # Prepare parallelism policy from stage config
        parallelism_policy = {
            "max_concurrent": stage.parallelism.max_concurrent,
            "retry_max": stage.parallelism.retry_max,
            "timeout_sec": stage.parallelism.timeout_sec,
            "poll_interval": 5,  # Default poll interval for async schedulers
        }
        
        # Execute stage via scheduler
        try:
            result = self.scheduler.run_stage(
                stage_name=stage.name,
                job_definitions=job_definitions,
                parallelism_policy=parallelism_policy,
                working_dir=str(self.output_dir / "jobs"),
            )
            
            # Process results and update XCom
            self._process_scheduler_results(result, jobs, stage.name)
            
            if not result.success:
                raise RuntimeError(
                    f"Stage {stage.name} failed: {result.error_message}"
                )
                
        except Exception as e:
            self.logger.checkpoint(
                "stage_scheduler_error",
                "error",
                f"Scheduler execution failed for stage {stage.name}: {str(e)}",
                context={"stage_name": stage.name, "error": str(e)},
            )
            raise
    
    def _convert_job_to_scheduler_format(
        self,
        job: JobDefinition,
        job_id: str,
        job_context: JobContext,
    ) -> Dict[str, Any]:
        """Convert a JobDefinition to scheduler job format.
        
        Args:
            job: Job definition from workflow.
            job_id: Unique job identifier.
            job_context: Job context with design point and XCom.
            
        Returns:
            Dict in scheduler format with keys: name, command, payload, outputs, etc.
        """
        evaluator_type = job.payload.get("evaluator_type", "bash")
        
        scheduler_job = {
            "job_id": job_id,
            "name": job.name,
            "command": job.command,
            "payload": {**job.payload},
            "outputs": job.outputs or [],
            "job_context": job_context,  # Pass context for potential XCom access in scheduler
        }
        
        # For Python evaluators, add function reference to payload
        if evaluator_type == "python":
            python_callable = job.payload.get("python_callable")
            if python_callable:
                # For schedulers that support function submission (e.g., PanDAiDDS)
                scheduler_job["function"] = python_callable
                scheduler_job["params"] = {
                    "context": job_context,
                    **(job.payload.get("op_kwargs", {})),
                }
        
        # Add design point to payload
        scheduler_job["payload"]["design_point"] = job_context.design_point
        scheduler_job["payload"]["job_id"] = job_id
        scheduler_job["payload"]["execution_dir"] = job_context.execution_dir
        
        # Add resource requirements
        if job.resources:
            scheduler_job["resources"] = job.resources
        
        return scheduler_job
    
    def _process_scheduler_results(
        self,
        stage_result,
        jobs: List[JobDefinition],
        stage_name: str,
    ) -> None:
        """Process results from scheduler execution and update XCom.
        
        Args:
            stage_result: StageExecutionResult from scheduler.
            jobs: Original job definitions.
            stage_name: Name of the stage.
        """
        self.logger.log_info(
            f"Processing scheduler results for stage {stage_name}: "
            f"{len(stage_result.job_statuses)} jobs"
        )
        
        # Process each job result
        for job_status in stage_result.job_statuses:
            job_id = job_status.job_id
            
            # Log job completion
            if job_status.status == "completed":
                self.logger.checkpoint(
                    "job_complete",
                    "success",
                    f"Job {job_id} completed via scheduler",
                    context={
                        "job_id": job_id,
                        "return_code": job_status.return_code,
                    },
                )
            else:
                self.logger.checkpoint(
                    "job_error",
                    "error",
                    f"Job {job_id} failed via scheduler",
                    context={
                        "job_id": job_id,
                        "return_code": job_status.return_code,
                        "stderr": job_status.stderr,
                    },
                )
            
            # Store stdout/stderr in XCom if available
            if job_status.stdout:
                self.global_xcom[f"{job_id}:stdout"] = job_status.stdout
            if job_status.stderr:
                self.global_xcom[f"{job_id}:stderr"] = job_status.stderr
            
            # Store outputs in XCom (objectives, metrics, etc.)
            if job_status.outputs:
                self.logger.log_info(
                    f"Storing {len(job_status.outputs)} outputs from job {job_id}"
                )
                for output_key, output_value in job_status.outputs.items():
                    xcom_key = f"{job_id}:{output_key}"
                    self.global_xcom[xcom_key] = output_value
                    self.logger.log_info(f"  XCom: {xcom_key} = {output_value}")
        
        # Store artifacts from scheduler in XCom
        if stage_result.artifacts:
            self.logger.log_info(
                f"Storing {len(stage_result.artifacts)} artifacts from stage {stage_name}"
            )
            for artifact_path, artifact_data in stage_result.artifacts.items():
                # Store artifact under job-specific key
                # Artifacts might come from different jobs in the stage
                xcom_key = f"{stage_name}:artifact:{artifact_path}"
                self.global_xcom[xcom_key] = artifact_data
    
    def _expand_jobs(self, stage: StageDefinition) -> List[JobDefinition]:
        """Expand jobs from job_factory.
        
        Args:
            stage: Stage definition with jobs and optional job_factory.
            
        Returns:
            List of expanded job definitions.
        """
        if not stage.jobs:
            return []
        
        if not stage.job_factory:
            # No factory, return jobs as-is
            return stage.jobs
        
        # Expand first job using factory
        template_job = stage.jobs[0]
        factory = stage.job_factory
        
        if factory.type == "range":
            # Create N copies of the template job
            n = factory.params.get("n", 1)
            expanded = []
            for i in range(n):
                job_copy = JobDefinition(
                    name=f"{template_job.name}_{i}",
                    command=template_job.command,
                    payload={**template_job.payload, "job_index": i},
                    resources=template_job.resources,
                    outputs=template_job.outputs,
                )
                expanded.append(job_copy)
            return expanded
        else:
            # Unsupported factory type, return original jobs
            self.logger.log_warning(
                f"Unsupported job_factory type: {factory.type}. Using original jobs."
            )
            return stage.jobs
    
    def _execute_job(
        self,
        job: JobDefinition,
        job_id: str,
        stage_context: StageContext,
        design_point: Dict[str, Any],
    ) -> None:
        """Execute a single job using the appropriate evaluator.
        
        Args:
            job: Job definition to execute.
            job_id: Unique job identifier.
            stage_context: Parent stage context.
            design_point: Design point parameters.
        """
        self.logger.checkpoint(
            "job_start",
            "start",
            f"Starting job: {job_id}",
            context={"job_id": job_id, "job_name": job.name},
        )
        
        # Create job context
        job_context = JobContext(
            job_id=job_id,
            stage_id=stage_context.stage_id,
            workflow_id=self.workflow.name,
            design_point=design_point,
            xcom=self.global_xcom,
            stage_context=stage_context,
            execution_dir=str(self.output_dir / "jobs" / job_id),
            problem_config=self.problem_config,
            workflow_context=self.workflow_context,
        )
        
        # Ensure job execution directory exists
        Path(job_context.execution_dir).mkdir(parents=True, exist_ok=True)
        
        # Select and create evaluator
        evaluator = self._create_evaluator(job, job_id)
        
        try:
            # Execute evaluator
            result = evaluator.execute(job_context)
            
            # Store result in XCom
            if result is not None:
                job_context.xcom_push("result", result)
            
            self.logger.checkpoint(
                "job_complete",
                "success",
                f"Job {job_id} completed successfully",
                context={
                    "job_id": job_id,
                    "result": str(result)[:200] if result else None,
                },
            )
            
        except Exception as e:
            self.logger.checkpoint(
                "job_error",
                "error",
                f"Job {job_id} failed: {str(e)}",
                context={"job_id": job_id, "error": str(e)},
            )
            
            # Check if retry is needed
            max_retries = stage_context.parameters.get("retry_max", 0)
            if max_retries > 0:
                self.logger.log_warning(
                    f"Job {job_id} failed. Retries not yet implemented."
                )
            
            raise
    
    def _create_evaluator(self, job: JobDefinition, job_id: str) -> BaseExecutionEngine:
        """Create appropriate execution engine for a job.
        
        Selects execution engine type based on job definition (command, payload, etc).
        
        Args:
            job: Job definition.
            job_id: Unique job identifier.
            
        Returns:
            BaseExecutionEngine instance (BashExecutionEngine, PythonExecutionEngine, or ContainerExecutionEngine).
        """
        # Check for explicit evaluator_type in payload
        evaluator_type = job.payload.get("evaluator_type", "bash")
        
        if evaluator_type == "container":
            # ContainerExecutionEngine
            return ContainerExecutionEngine(
                job_id=job_id,
                image=job.payload.get("image", "python:3.9"),
                command=job.payload.get("container_command", ["/bin/bash", "-c", job.command]),
                environment=job.payload.get("environment", {}),
                volumes=job.payload.get("volumes", {}),
                resources=job.resources,
            )
        elif evaluator_type == "python":
            # PythonExecutionEngine (requires python_callable in payload)
            python_callable = job.payload.get("python_callable")
            if not python_callable:
                raise ValueError(
                    f"Job {job_id} specifies evaluator_type='python' but missing 'python_callable'"
                )
            return PythonExecutionEngine(
                job_id=job_id,
                python_callable=python_callable,
                op_args=job.payload.get("op_args", ()),
                op_kwargs=job.payload.get("op_kwargs", {}),
            )
        elif evaluator_type == "stack":
            # StackExecutionEngine (requires stack_type in payload and layers in job)
            stack_type = job.payload.get("stack_type")
            if not stack_type:
                raise ValueError(
                    f"Job {job_id} specifies evaluator_type='stack' but is missing 'stack_type'"
                )
            layers = getattr(job, 'layers', [])
            if not layers:
                raise RuntimeError(
                    f"Job {job_id} specifies evaluator_type='stack' but is missing the layer configurations"
                )
            return StackExecutionEngine(
                job_id=job_id,
                stack_type=stack_type,
                layers=layers,
            )
        else:
            # Default to BashExecutionEngine
            return BashExecutionEngine(
                job_id=job_id,
                bash_command=job.command,
                env=job.payload.get("env", {}),
            )
    
    def _compute_objectives(self) -> Dict[str, float]:
        """Compute objectives from workflow outputs.
        
        For now, returns a placeholder. This should be extended to:
        1. Read output artifacts from jobs
        2. Apply objective computation plans
        3. Return final objective values
        
        Returns:
            objectives: {objective_name: value}.
        """
        self.logger.checkpoint(
            "objectives_compute",
            "start",
            "Computing objectives from outputs",
            context={},
        )
        
        # Placeholder implementation
        # TODO: Implement objective computation from:
        # - self.workflow.objectives
        # - self.workflow.combined_objectives
        # - Job outputs stored in XCom or artifacts
        
        objectives = {}
        
        # Extract from XCom
        # XCom keys are in format "job_id:key"
        for xcom_key, value in self.global_xcom.items():
            # Check for objectives dict (from single branch case)
            if xcom_key.endswith(":objectives") and isinstance(value, dict):
                objectives.update(value)
            
            # Check for individual objective values (from separate branches case)
            for obj_def in self.workflow.objectives:
                if xcom_key.endswith(f":{obj_def.name}"):
                    objectives[obj_def.name] = value
        
        self.logger.checkpoint(
            "objectives_computed",
            "success",
            f"Objectives computed: {objectives}",
            context={"objectives": objectives},
        )
        
        return objectives


def create_executor_from_config(
    workflow_config_path: str,
    output_dir: str = "/tmp/aid2e_runs",
) -> DAGExecutor:
    """Create DAGExecutor from workflow configuration file.
    
    Convenience function for loading workflow from YAML/JSON config.
    
    Args:
        workflow_config_path: Path to workflow configuration file.
        output_dir: Base directory for execution outputs.
        
    Returns:
        DAGExecutor instance.
        
    Example:
        >>> executor = create_executor_from_config("configs/dtlz2.yml")
        >>> objectives = executor.execute({"x1": 0.5, "x2": 0.7})
    """
    import yaml
    
    with open(workflow_config_path, 'r') as f:
        if workflow_config_path.endswith('.json'):
            config = json.load(f)
        else:
            config = yaml.safe_load(f)
    
    workflow = WorkflowDefinition(**config)
    return DAGExecutor(workflow, base_output_dir=output_dir)
