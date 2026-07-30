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
import importlib
import json
import logging
import os
import subprocess
import sys
from datetime import datetime

from aid2e.utilities.configurations.problem_config import (
    ProblemConfiguration,
)
from aid2e.utilities.configurations.workflow_config import (
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
from .rule_resolution import resolve_job_rule, resolve_payload_templates


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
        scheduler_config_resolver=None,
        config_dir: Optional[str] = None,
        trial_metadata: Optional[Dict[str, Any]] = None,
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
        self.scheduler_config_resolver = scheduler_config_resolver
        self.config_dir = Path(config_dir).resolve() if config_dir else None
        self.trial_metadata = dict(trial_metadata or {})
        self.current_design_point: Dict[str, Any] = {}
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.problem_config is not None:
            work_root = Path(self.problem_config.work_location) / workflow.name / timestamp
            output_root = Path(self.problem_config.output_location) / workflow.name / timestamp
        else:
            output_root = self.base_output_dir / workflow.name / timestamp
            work_root = output_root

        work_root.mkdir(parents=True, exist_ok=True)
        output_root.mkdir(parents=True, exist_ok=True)
        self.work_dir = work_root
        self.output_dir = output_root
        self.scheduler_submit_dir = self.work_dir / "_scheduler"
        self.scheduler_submit_dir.mkdir(parents=True, exist_ok=True)
        
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
        self.logger.log_info(f"Work directory: {self.work_dir}")
        if self.scheduler:
            runner_type = self.scheduler_config.get("runner_type", "unknown")
            self.logger.log_info(f"Scheduler: {runner_type}")
    
    def _create_scheduler(self, scheduler_config: Optional[Dict[str, Any]] = None):
        """Create and initialize the scheduler from configuration.
        
        Returns:
            Initialized scheduler instance (BaseScheduler subclass).
            
        Raises:
            ValueError: If scheduler_config is invalid or scheduler type not found.
        """
        scheduler_config = scheduler_config or self.scheduler_config
        runner_type = scheduler_config.get("runner_type")
        if not runner_type:
            raise ValueError("scheduler_config must specify 'runner_type'")
        
        config = scheduler_config.get("config")
        
        # Import scheduler dynamically based on runner_type
        try:
            if runner_type == "JobLibRunner":
                from aid2e.schedulers.JobLib.runner import JobLibScheduler
                return JobLibScheduler(config=config)
            elif runner_type == "PanDAiDDSRunner":
                from aid2e.schedulers.PanDAiDDS.runner import PanDAiDDSScheduler
                return PanDAiDDSScheduler(config=config)
            elif runner_type == "SlurmRunner":
                from aid2e.schedulers.Slurm.runner import SlurmScheduler
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

        self.current_design_point = dict(design_point or {})
        self.logger.checkpoint(
            "workflow_start",
            "start",
            f"Starting workflow execution for design point: {design_point}",
            context={"design_point": design_point},
        )

        self.workflow_context = WorkflowSharedContext(
            workflow_id=self.workflow.name,
            parameters={},
        )

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
                    self._execute_stage(stage, branch, branch_context, design_point)
        
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
        branch: BranchDefinition,
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
        
        if self.scheduler_config_resolver is not None:
            scheduler_config = self.scheduler_config_resolver(branch, stage)
        else:
            scheduler_config = self.scheduler_config or None

        # Use scheduler to execute stage if configured,
        # otherwise execute directly
        if scheduler_config:
            self._execute_stage_with_scheduler(
                stage, jobs, stage_context, design_point, scheduler_config
            )
        else:
            jobs_seen = []
            for job in jobs:
                job_id = job.name
                n_seen = jobs_seen.count(job_id)
                jobs_seen.append(job_id)
                if n_seen > 0:
                    job_id = job_id + f"_{n_seen - 1}"
                    job.name = job_id
                task_id = f"{stage.name}:{job_id}"
                self._execute_job(job, job_id, task_id, stage_context, design_point)
        
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
        scheduler_config: Dict[str, Any],
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
        if scheduler_config == self.scheduler_config and self.scheduler is not None:
            scheduler = self.scheduler
        else:
            scheduler = self._create_scheduler(scheduler_config)

        # Convert jobs to scheduler format
        job_definitions = []
        jobs_seen = []
        for job in jobs:
            job_id = job.name
            n_seen = jobs_seen.count(job_id)
            jobs_seen.append(job_id)
            if n_seen > 0:
                job_id = job_id + f"_{n_seen - 1}"
                job.name = job_id
            task_id = f"{stage.name}:{job_id}"
            execution_dir, output_dir = self._build_job_directories(stage.name, job_id)
            
            # Create job context for this job
            job_context = JobContext(
                task_id=task_id,
                job_id=job_id,
                stage_id=stage_context.stage_id,
                workflow_id=self.workflow.name,
                design_point=design_point,
                xcom=self.global_xcom,
                stage_context=stage_context,
                execution_dir=str(execution_dir),
                output_dir=str(output_dir),
                workflow_context=self.workflow_context,
            )
            
            # Convert to scheduler job definition format
            scheduler_job = self._convert_job_to_scheduler_format(
                job, job_id, job_context, scheduler_config
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
            scheduler_working_dir = self.scheduler_submit_dir / stage.name
            scheduler_working_dir.mkdir(parents=True, exist_ok=True)
            result = scheduler.run_stage(
                stage_name=stage.name,
                job_definitions=job_definitions,
                parallelism_policy=parallelism_policy,
                working_dir=str(scheduler_working_dir),
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
        scheduler_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Convert a JobDefinition to scheduler job format.
        
        Args:
            job: Job definition from workflow.
            job_id: Unique job identifier.
            job_context: Job context with design point and XCom.
            
        Returns:
            Dict in scheduler format with keys: name, command, payload, outputs, etc.
        """
        runner_type = (scheduler_config or self.scheduler_config).get("runner_type")
        evaluator_type = job.payload.get("evaluator_type", "bash")
        design_file = self._materialize_design_file(job_id, job_context)
        if runner_type == "SlurmRunner" and evaluator_type == "python":
            raise ValueError(
                f"Job {job_id} uses evaluator_type='python', which SlurmScheduler v1 does not support."
            )

        command = job.command
        outputs = [
            output.model_dump() if hasattr(output, "model_dump") else output
            for output in job.outputs or []
        ]
        if evaluator_type != "python":
            command = self._resolve_scheduler_job_command(
                job,
                job_id,
                job_context,
                design_file=design_file,
            )
            outputs = self._resolve_scheduler_job_outputs(
                job,
                job_id,
                job_context,
                design_file=design_file,
            )

        scheduler_job = {
            "job_id": job_id,
            "name": job.name,
            "command": command,
            "payload": {**job.payload},
            "outputs": outputs,
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
        scheduler_job["payload"]["output_dir"] = job_context.output_dir
        scheduler_job["payload"]["design_file"] = design_file
        
        # Add resource requirements
        if job.resources:
            scheduler_job["resources"] = job.resources
        
        return scheduler_job

    def _resolve_scheduler_job_command(
        self,
        job: JobDefinition,
        job_id: str,
        job_context: JobContext,
        *,
        design_file: str,
    ) -> str:
        """Resolve command/rule/payload into a final scheduler command."""
        rule_context = {
            "job_id": job_id,
            "output_dir": job_context.output_dir,
            "execution_dir": job_context.execution_dir,
            "workflow_id": job_context.workflow_id,
            "stage_id": job_context.stage_id,
            "design_point": job_context.design_point,
            "design_file": design_file,
            "python_executable": sys.executable,
            "repo_root": str(Path(__file__).resolve().parents[4]),
            "prepared_geometry_dir": self.workflow_context.parameters.get("prepared_geometry_dir"),
            "stage_outputs": {},
            "xcom": self.global_xcom,
        }
        if "{" in job.command and "}" in job.command:
            resolved_command = resolve_payload_templates(
                {"command": job.command},
                rule_context,
                logger=self.logger,
            )["command"]
            job = job.model_copy(update={"command": resolved_command})
        return resolve_job_rule(job, rule_context, logger=self.logger)

    def _resolve_scheduler_job_outputs(
        self,
        job: JobDefinition,
        job_id: str,
        job_context: JobContext,
        *,
        design_file: str,
    ) -> List[Dict[str, Any]]:
        """Resolve scheduler output specs against the same runtime context as rules."""
        resolved_payload = resolve_payload_templates(
            job.payload,
            {
                "job_id": job_id,
                "output_dir": job_context.output_dir,
                "execution_dir": job_context.execution_dir,
                "workflow_id": job_context.workflow_id,
                "stage_id": job_context.stage_id,
                "design_point": job_context.design_point,
                "design_file": design_file,
                "repo_root": str(Path(__file__).resolve().parents[4]),
                "stage_outputs": {},
                "xcom": self.global_xcom,
            },
            logger=self.logger,
        )

        resolved_outputs: List[Dict[str, Any]] = []
        for output_spec in job.outputs or []:
            payload = {
                "path": getattr(output_spec, "path", None),
                "format": getattr(output_spec, "format", None),
            }
            resolved_outputs.append(
                resolve_payload_templates(
                    payload,
                    {
                        "job_id": job_id,
                        "output_dir": job_context.output_dir,
                        "execution_dir": job_context.execution_dir,
                        "workflow_id": job_context.workflow_id,
                        "stage_id": job_context.stage_id,
                        "design_point": job_context.design_point,
                        "design_file": design_file,
                        "repo_root": str(Path(__file__).resolve().parents[4]),
                        "stage_outputs": {},
                        "xcom": self.global_xcom,
                        "payload": resolved_payload,
                    },
                    logger=self.logger,
                )
            )

        return resolved_outputs

    def _materialize_design_file(
        self,
        job_id: str,
        job_context: JobContext,
    ) -> str:
        """Persist the incoming design point for command-style scheduler jobs."""
        from aid2e.optimizers.base import Trial

        design_path = Path(job_context.execution_dir) / "design_point.json"
        trial = Trial(
            index=-1,
            parameters=dict(job_context.design_point or {}),
            metadata={
                "job_id": job_id,
                "workflow_id": job_context.workflow_id,
                "stage_id": job_context.stage_id,
            },
        )
        trial.save_to_json(design_path)
        return str(design_path)

    def _build_job_directories(self, stage_id: str, job_id: str) -> Tuple[Path, Path]:
        """Create paired work/output directories for one job."""
        execution_dir = self.work_dir / stage_id / job_id
        output_dir = self.output_dir / stage_id / job_id
        execution_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        return execution_dir, output_dir
    
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
                    rule=template_job.rule,
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
        task_id: str,
        stage_context: StageContext,
        design_point: Dict[str, Any],
    ) -> None:
        """Execute a single job using the appropriate evaluator.
        
        Args:
            job: Job definition to execute.
            job_id: Unique job identifier.
            task_id: Key encoding stage, job ID
            stage_context: Parent stage context.
            design_point: Design point parameters.
        """
        self.logger.checkpoint(
            "job_start",
            "start",
            f"Starting job: {job_id}",
            context={"job_id": job_id, "job_name": job.name},
        )

        execution_dir, output_dir = self._build_job_directories(stage_context.stage_id, job_id)
        
        # Create job context
        job_context = JobContext(
            task_id=task_id,
            job_id=job_id,
            stage_id=stage_context.stage_id,
            workflow_id=self.workflow.name,
            design_point=design_point,
            xcom=self.global_xcom,
            stage_context=stage_context,
            execution_dir=str(execution_dir),
            output_dir=str(output_dir),
            problem_config=self.problem_config,
            workflow_context=self.workflow_context,
        )
        
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
                engine_id=job_id,
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
                engine_id=job_id,
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
                engine_id=job_id,
                stack_type=stack_type,
                layers=layers,
            )
        else:
            # Default to BashExecutionEngine
            return BashExecutionEngine(
                engine_id=job_id,
                bash_command=job.command,
                env=job.payload.get("env", {}),
            )
    
    def _compute_objectives(self) -> Dict[str, float]:
        """Compute objectives from workflow outputs.

        This method:
        1. Reads output artifacts from jobs through XCom.
        2. Executes configured objective step plans when present.
        3. Returns final objective values for declared workflow objectives.

        Returns:
            objectives: {objective_name: value}, including optional *_sem fields.
        """
        self.logger.checkpoint(
            "objectives_compute",
            "start",
            "Computing objectives from outputs",
            context={},
        )

        objective_names = {obj_def.name for obj_def in self.workflow.objectives}
        combined_metric_names = {
            metric.name
            for plan in self.workflow.combined_objectives
            for metric in plan.metrics
        }
        objective_names.update(combined_metric_names)
        sem_names = {f"{name}_sem" for name in objective_names}
        objective_fields = objective_names | sem_names
        combined_metric_keys = {
            metric.metric_key: metric.name
            for plan in self.workflow.combined_objectives
            for metric in plan.metrics
        }
        scalar_objective_keys = {name: name for name in objective_fields}
        scalar_objective_keys.update(combined_metric_keys)
        scalar_objective_keys.update(
            {
                f"{metric_key}_sem": f"{objective_name}_sem"
                for metric_key, objective_name in combined_metric_keys.items()
            }
        )
        objectives = {}

        def collect_from_mapping(values: Dict[str, Any]) -> None:
            if isinstance(values.get("objectives"), dict):
                values = values["objectives"]
            for name in objective_fields:
                if name in values:
                    objectives[name] = values[name]
            for metric_key, objective_name in combined_metric_keys.items():
                if metric_key in values:
                    objectives[objective_name] = values[metric_key]
                sem_key = f"{metric_key}_sem"
                if sem_key in values:
                    objectives[f"{objective_name}_sem"] = values[sem_key]

        for xcom_key, value in self.global_xcom.items():
            # Check for objectives dicts from jobs that pushed all metrics together.
            if isinstance(value, dict):
                collect_from_mapping(value)
                continue

            # Check for JSON artifacts collected by schedulers as string payloads.
            if isinstance(value, str):
                try:
                    parsed_value = json.loads(value)
                except json.JSONDecodeError:
                    parsed_value = None
                if isinstance(parsed_value, dict):
                    collect_from_mapping(parsed_value)
                    continue

            # Check for individual objective values from separate jobs/branches.
            output_key = xcom_key.rpartition(":")[2]
            objective_name = scalar_objective_keys.get(output_key)
            if objective_name is not None:
                objectives[objective_name] = value

        for obj_def in self.workflow.objectives:
            if obj_def.objective_plan is not None:
                if obj_def.scheduler is not None:
                    raise ValueError(
                        f"Objective {obj_def.name} declares an objective-level "
                        "scheduler. In v0, scheduled objective work must be "
                        "represented as workflow stages."
                    )
                objectives.update(self._compute_single_objective_plan(obj_def))

        for plan in self.workflow.combined_objectives:
            if plan.scheduler is not None:
                raise ValueError(
                    f"Combined objective {plan.name} declares an objective-level "
                    "scheduler. In v0, scheduled objective work must be "
                    "represented as workflow stages."
                )
            objectives.update(self._compute_combined_objective_plan(plan))

        missing = sorted(name for name in objective_names if name not in objectives)
        if missing:
            raise ValueError(
                "Workflow did not produce declared objectives: " + ", ".join(missing)
            )

        objectives = {
            name: float(value)
            for name, value in objectives.items()
            if name in objective_fields
        }

        self.logger.checkpoint(
            "objectives_computed",
            "success",
            f"Objectives computed: {objectives}",
            context={"objectives": objectives},
        )
        
        return objectives

    def _compute_single_objective_plan(self, obj_def) -> Dict[str, float]:
        """Execute one objective plan and extract its declared objective value."""
        payload = self._execute_objective_plan(
            plan=obj_def.objective_plan,
            plan_name=obj_def.name,
        )
        metric_keys = obj_def.metrics_keys or [obj_def.name]
        if len(metric_keys) != 1:
            raise ValueError(
                f"Objective {obj_def.name} must declare exactly one metrics_key"
            )
        return self._extract_objective_metrics(
            payload,
            {metric_keys[0]: obj_def.name},
        )

    def _compute_combined_objective_plan(self, combined_plan) -> Dict[str, float]:
        """Execute one combined objective plan and extract all declared metrics."""
        payload = self._execute_objective_plan(
            plan=combined_plan.objective_plan,
            plan_name=combined_plan.name,
        )
        return self._extract_objective_metrics(
            payload,
            {metric.metric_key: metric.name for metric in combined_plan.metrics},
        )

    def _execute_objective_plan(self, plan, plan_name: str) -> Dict[str, Any]:
        """Execute an objective step plan and return its producer payload."""
        step_results: Dict[str, Any] = {}
        stages_by_name = {stage.name: stage for stage in plan.steps.stages}

        for stage_name in self._objective_step_order(plan):
            stage = stages_by_name[stage_name]
            inputs = {
                dep: step_results[dep]
                for dep in stage.depends_on
            }
            inputs.update(stage.inputs)
            step_results[stage.name] = self._execute_objective_step(
                plan_name,
                stage,
                inputs,
            )

        producer = plan.steps.producing_stage()
        payload = step_results.get(producer)
        if payload is None:
            raise ValueError(
                f"Objective plan {plan_name} did not produce stage {producer}"
            )
        return payload

    def _objective_step_order(self, plan) -> List[str]:
        """Return dependency order for objective plan stages."""
        nodes = [
            DagNode(
                node_id=stage.name,
                node_type=DagNodeType.JOB,
                depends_on=list(stage.depends_on),
                description=f"Objective step {stage.name}",
            )
            for stage in plan.steps.stages
        ]
        topo_order = topological_sort(DagDefinition(name="objective_plan", nodes=nodes))
        return [
            node.node_id
            for layer in topo_order.layers
            for node in layer
        ]

    def _execute_objective_step(
        self,
        plan_name: str,
        stage,
        inputs: Dict[str, Any],
    ) -> Any:
        """Execute one objective step using its configured action."""
        if stage.inline is not None:
            return self._execute_inline_objective_step(plan_name, stage, inputs)
        if stage.script is not None:
            return self._execute_script_objective_step(plan_name, stage, inputs)
        raise ValueError(
            f"Objective step {plan_name}.{stage.name} must define inline or script"
        )

    def _execute_inline_objective_step(
        self,
        plan_name: str,
        stage,
        inputs: Dict[str, Any],
    ) -> Any:
        """Execute an inline objective step callable."""
        entrypoint = stage.inline.entrypoint
        if ":" in entrypoint:
            module_name, symbol_name = entrypoint.split(":", 1)
        else:
            module_name, symbol_name = entrypoint.rsplit(".", 1)
        config_dir = str(self.config_dir) if self.config_dir is not None else None
        added_config_dir = config_dir is not None and config_dir not in sys.path
        if added_config_dir:
            sys.path.insert(0, config_dir)
        try:
            callable_obj = getattr(importlib.import_module(module_name), symbol_name)
        finally:
            if added_config_dir:
                sys.path.remove(config_dir)
        step_dir = self._objective_step_dir(plan_name, stage.name)
        return callable_obj(
            design_point=dict(self.current_design_point),
            inputs=inputs,
            outputs=dict(stage.outputs),
            extra_args=dict(stage.extra_args),
            xcom=self.global_xcom,
            work_dir=str(step_dir),
            output_dir=str(self.output_dir),
            problem_config=self.problem_config,
            trial_metadata=dict(self.trial_metadata),
        )

    def _execute_script_objective_step(
        self,
        plan_name: str,
        stage,
        inputs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute a script objective step and parse its JSON output file."""
        from aid2e.utilities.workflows.execution_utils import build_objective_call

        step_dir = self._objective_step_dir(plan_name, stage.name)
        params_file = step_dir / "design_point.json"
        inputs_file = step_dir / "step_inputs.json"
        params_file.write_text(json.dumps(self.current_design_point, indent=2))
        inputs_file.write_text(
            json.dumps(
                {
                    "inputs": inputs,
                    "extra_args": dict(stage.extra_args),
                },
                indent=2,
            )
        )

        script_path = self._resolve_objective_script_path(stage.script.path)
        output_file = self._format_objective_output_file(
            stage.script.output_file,
            plan_name=plan_name,
            stage_name=stage.name,
            step_dir=step_dir,
        )
        output_file.parent.mkdir(parents=True, exist_ok=True)

        command = (
            [sys.executable, str(script_path)]
            if script_path.suffix == ".py"
            else [str(script_path)]
        )
        argv, env = build_objective_call(command, params_file, output_file)
        env["AID2E_STEP_INPUTS_FILE"] = str(inputs_file)
        result = subprocess.run(
            argv,
            cwd=str(step_dir),
            env={**os.environ, **env},
            text=True,
            capture_output=True,
            timeout=stage.script.timeout_sec,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Objective script {script_path} failed with code "
                f"{result.returncode}: {result.stderr}"
            )
        if not output_file.exists():
            raise FileNotFoundError(
                f"Objective script {script_path} did not write {output_file}"
            )
        try:
            return json.loads(output_file.read_text())
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Objective script {script_path} wrote invalid JSON"
            ) from error

    def _objective_step_dir(self, plan_name: str, stage_name: str) -> Path:
        """Create the working directory for one objective step."""
        step_dir = self.work_dir / "_objectives" / plan_name / stage_name
        step_dir.mkdir(parents=True, exist_ok=True)
        return step_dir

    def _resolve_objective_script_path(self, script_path: str) -> Path:
        """Resolve an objective script path using the config directory when known."""
        path = Path(script_path).expanduser()
        if not path.is_absolute() and self.config_dir is not None:
            path = self.config_dir / path
        path = path.resolve()
        if not path.exists():
            raise FileNotFoundError(f"Objective script not found: {path}")
        return path

    def _format_objective_output_file(
        self,
        output_file: str,
        *,
        plan_name: str,
        stage_name: str,
        step_dir: Path,
    ) -> Path:
        """Format a declared objective output filename."""
        try:
            formatted = output_file.format(
                objective_name=plan_name,
                stage_name=stage_name,
                job_id=stage_name,
            )
        except KeyError as error:
            raise ValueError(
                f"Unsupported objective output_file placeholder: {error}"
            ) from error
        path = Path(formatted).expanduser()
        if not path.is_absolute():
            path = step_dir / path
        return path.resolve()

    def _normalize_objective_payload(self, payload: Any) -> Dict[str, Any]:
        """Normalize objective step output into a mapping."""
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError as error:
                raise ValueError("Objective payload must be valid JSON") from error
        if isinstance(payload, dict) and isinstance(payload.get("objectives"), dict):
            payload = payload["objectives"]
        if not isinstance(payload, dict):
            raise ValueError("Objective payload must be a mapping")
        return payload

    def _extract_objective_metrics(
        self,
        payload: Dict[str, Any],
        metric_map: Dict[str, str],
    ) -> Dict[str, float]:
        """Extract declared objective metrics and optional SEM values."""
        if not isinstance(payload, dict):
            if len(metric_map) != 1:
                raise ValueError("Objective payload must be a mapping")
            objective_name = next(iter(metric_map.values()))
            return {objective_name: float(payload)}

        payload = self._normalize_objective_payload(payload)
        extracted: Dict[str, float] = {}
        missing = []
        for metric_key, objective_name in metric_map.items():
            if metric_key not in payload:
                missing.append(metric_key)
                continue
            extracted[objective_name] = float(payload[metric_key])
            sem_key = f"{metric_key}_sem"
            if sem_key in payload:
                extracted[f"{objective_name}_sem"] = float(payload[sem_key])
        if missing:
            raise ValueError(
                "Objective payload missing declared metrics: " + ", ".join(missing)
            )
        return extracted


def create_executor_from_config(
    workflow_config_path: str,
    output_dir: str = "/tmp/aid2e_runs",
    workflow: Optional[WorkflowDefinition] = None,
    log_level: str = "INFO",
    trial_metadata: Optional[Dict[str, Any]] = None,
) -> DAGExecutor:
    """Create DAGExecutor from workflow configuration file.
    
    Convenience function for loading workflow from YAML/JSON config.
    
    Args:
        workflow_config_path: Path to workflow configuration file.
        output_dir: Base directory for execution outputs.
        workflow: Optional workflow override. When omitted, uses the workflow
            from the loaded config file.
        log_level: Logging level for the executor.
        
    Returns:
        DAGExecutor instance.
        
    Example:
        >>> executor = create_executor_from_config("configs/dtlz2.yml")
        >>> objectives = executor.execute({"x1": 0.5, "x2": 0.7})
    """
    from aid2e.utilities.configurations import load_config
    from aid2e.utilities.runtime_builders import build_workflow_executor_from_config

    config = load_config(workflow_config_path)
    return build_workflow_executor_from_config(
        workflow if workflow is not None else config.workflows,
        problem_cfg=config.problem,
        scheduler_cfg=config.scheduler,
        base_output_dir=output_dir,
        log_level=log_level,
        config_dir=str(Path(workflow_config_path).resolve().parent),
        trial_metadata=trial_metadata,
    )
