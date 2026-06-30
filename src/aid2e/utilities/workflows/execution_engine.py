"""ExecutionEngine for DAG-based workflow execution.
ExecutionEngines are the smallest executable units in a workflow. They encapsulate
the logic to execute a specific job type (bash command, Python function,
Docker container, etc). Each execution engine runs within a JobContext and can
exchange data via XCom.

Inspired by Apache Airflow's operator model, execution engines provide:
- Job execution logic
- Parameter handling and templating
- Context-aware execution (logs, XCom, artifacts)
- Failure handling and retries

Supported execution engines:
    BaseExecutionEngine: Abstract base for all execution engines
    BashExecutionEngine: Execute shell commands
    PythonExecutionEngine: Execute Python functions
    ContainerExecutionEngine: Execute Docker containers

Context hierarchy:
    JobContext: Execution context for a single job
    StageContext: Parameters shared across all jobs in a stage
    BranchContext: Parameters shared across all stages in a branch

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from abc import ABC, abstractmethod
from ast import literal_eval
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from functools import reduce
import subprocess
import json
import os
import re
from pathlib import Path

from aid2e.utilities.configurations.problem_config import (
    ProblemConfiguration,
)
from aid2e.utilities.configurations.experimental_stack_config import (
    StackLayerConfig,
)
from aid2e.utilities.configurations.stack_registry import StackRegistry

from .experimental_stack import ExperimentStack


@dataclass
class WorkflowSharedContext:
    """Context shared across all jobs of one workflow execution.

    Attributes:
        workflow_id: Unique workflow identifier.
        parameters: Parameters available to all branches, stages, and
                    jobs in this workflow.
    """
    workflow_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BranchContext:
    """Context for parameters shared across all stages in a branch.
    
    Attributes:
        branch_id: Unique branch identifier.
        parameters: Parameters available to all stages in this branch.
    """
    branch_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class StageContext:
    """Context for parameters shared across all jobs in a stage.

    Attributes:
        stage_id: Unique stage identifier.
        parameters: Parameters available to all jobs in this stage.
        branch_context: Parent branch context (optional).
    """
    stage_id: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    branch_context: Optional[BranchContext] = None


@dataclass
class JobContext:
    """Execution context for a single job (XCom-like data passing).
    
    Holds job metadata, input/output data, logs, and artifacts.
    Enables data flow between jobs in a workflow.
    
    Attributes:
        task_id: Key encoding stage, job ID. Used in XCom,
                 formatted as {stage_id}:{job_id}
        job_id: Unique job identifier.
        stage_id: Parent stage identifier.
        workflow_id: Root workflow identifier.
        design_point: Input design point (optimizer output).
        xcom: Dict of data from upstream jobs (job_id:key → value).
        artifacts: Dict of output artifact paths produced by this job.
        logs: Execution logs (stdout/stderr).
        execution_dir: Working directory for job execution.
        stage_context: Parent stage context (optional).
        problem_config: Problem configuration for accessing stack-
                        dependent design space
        workflow_context: Shared workflow context (optional).
    """
    task_id: str
    job_id: str
    stage_id: str
    workflow_id: str
    design_point: Dict[str, Any] = field(default_factory=dict)
    xcom: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)
    execution_dir: Optional[str] = None
    output_dir: Optional[str] = None
    stage_context: Optional[StageContext] = None
    problem_config: Optional[ProblemConfiguration] = None
    workflow_context: Optional[WorkflowSharedContext] = None

    def xcom_key(self, key: str, task_id: str) -> str:
        """Get xcom key for a given job, stage

        Args:
            key: XCom key (e.g. 'return_value', 'metrics').
            task_id: Unique ID of job + stage (e.g. 'sim_stage:sim_job')

        Returns:
            Key formatted as task_id:key
        """
        return f"{task_id}:{key}"

    def xcom_push(self, key: str, value: Any) -> None:
        """Push data to XCom for downstream jobs.

        Data stored in a dictionary with the format:

            {'task_id:key': data}

        Args:
            key: XCom data key (e.g., 'return_value', 'metrics').
            value: Data to push (any serializable type).

        Example:
            >>> context.xcom_push('objectives', {'f1': 0.5, 'f2': 0.3})
        """
        xcom_key = self.xcom_key(key, self.task_id)
        self.xcom[xcom_key] = value

    def xcom_pull(self, task_id: str, key: str = 'return_value') -> Any:
        """Pull data from upstream job's XCom.

        Args:
            task_id: Upstream job key
            key: XCom data key (optional, default is 'return_value').

        Returns:
            Data pushed by upstream job, or None if not found.

        Example:
            >>> params = context.xcom_pull('prepare_params', key='params')
        """
        xcom_key = self.xcom_key(key, task_id)
        return self.xcom.get(xcom_key)

    def add_log(self, message: str) -> None:
        """Add a log message.
        
        Args:
            message: Log message.
        """
        self.logs.append(message)
    
    def save_artifact(self, artifact_key: str, artifact_path: str) -> None:
        """Register an output artifact.
        
        Args:
            artifact_key: Logical name for artifact (e.g., 'objectives').
            artifact_path: File path to artifact.
            
        Example:
            >>> context.save_artifact('objectives', '/work/objectives.json')
        """
        self.artifacts[artifact_key] = artifact_path


class Template:
    """class for common template substitutions

    Supports:
        - {{design_point.key}} → Value for design parameter with name `key`
        - {{job_id}} → Name of current job
        - {{stage_id}} → Name of current stage
        - {{branch_id}} → Name of current branch
        - {{workflow_id}} → Name of workflow
        - {{execution_dir}} → Current working directory
        - {{output_dir}} → Current output directory
        - {{geometry_dir}} → Geometry directory to use
        - {{artifacts[key]}} → Artifact path ID'd by key
        - {{xcom[key]}} → Scalar XCom data ID'd by key
        - {{xcom[key](acc)}} → Non-scalar XCom data ID'd by key,
                               accessed with acc
        - {{inputs[key](acc)}} → Stack layer input acc, ID'd by key
        - {{outputs[key](acc}} → Stack layer output acc, ID'd by key
        - {{arguments[key](acc}} → Stack layer argument acc, ID'd by key

    Attributes:
        _substitutions: Dictionary of template variables onto lambdas
                        to replace them. Format is {'pattern': 'rule'}.
    """
    _substitutions = {
        "{{design_point.key}}":
            (lambda text, context: reduce(lambda result, key: result.replace(f"{{{{design_point.{key[0]}}}}}", str(key[1])), context.design_point.items(), text)),
        "{{job_id}}":
            (lambda text, context: text.replace("{{job_id}}", str(context.job_id))),
        "{{stage_id}}":
            (lambda text, context: text.replace("{{stage_id}}", str(context.stage_id))),
        "{{branch_id}}":
            (lambda text, context: text.replace("{{branch_id}}", str(context.stage_context.branch_context.branch_id))
             if context.stage_context is not None and context.stage_context.branch_context is not None
             else text.replace("{{branch_id}}", "NotAvailable")),
        "{{workflow_id}}":
            (lambda text, context: text.replace("{{workflow_id}}", str(context.workflow_id))),
        "{{execution_dir}}":
            (lambda text, context: text.replace("{{execution_dir}}", str(context.execution_dir))),
        "{{output_dir}}":
            (lambda text, context: text.replace("{{output_dir}}", str(context.output_dir))),
        "{{geometry_dir}}":
            (lambda text, context: text.replace("{{geometry_dir}}", str(context.workflow_context.parameters["prepared_geometry_dir"]))
            if context.workflow_context is not None and "prepared_geometry_dir" in context.workflow_context.parameters
            else text.replace("{{geometry_dir}}", "NotAvailable")),
        "{{artifacts[key]}}":
            (lambda text, context:
                re.sub(r"{{artifacts\[(.*?)\]}}", lambda match: str(context.artifacts[match.group(1)]), text)),
        "{{xcom[key]}}":
            (lambda text, context:
                re.sub(r"{{xcom\[(.*?)\]}}", lambda match: str(context.xcom[match.group(1)]), text)),
        "{{xcom[key](acc)}}":
            (lambda text, context: re.sub(r"{{xcom\[(.*?)\]\((.*?)\)}}", lambda match: str(context.xcom[match.group(1)][literal_eval(match.group(2))]), text)),
        "{{inputs[key](acc)}}":
            (lambda text, context: re.sub(r"{{inputs\[(.*?)\]\((.*?)\)}}", lambda match: str(context.xcom[match.group(1) + ':inputs'][literal_eval(match.group(2))]), text)),
        "{{outputs[key](acc)}}":
            (lambda text, context: re.sub(r"{{outputs\[(.*?)\]\((.*?)\)}}", lambda match: str(context.xcom[match.group(1) + ':outputs'][literal_eval(match.group(2))]), text)),
        "{{arguments[key](acc)}}":
            (lambda text, context: re.sub(r"{{arguments\[(.*?)\]\((.*?)\)}}", lambda match: str(context.xcom[match.group(1) + ':arguments'][literal_eval(match.group(2))]), text)),
    }

    @classmethod
    def substitute(cls, text: str, context: JobContext) -> str:
        """Apply template substitutions

        Args:
            text: The text to apply substitution to
            context: JobContext holding job, stage, branch, and workflow info
        """
        result = text
        for template, substitution in cls._substitutions.items():
            result = substitution(result, context)
        return result


class BaseExecutionEngine(ABC):
    """Base class for all execution engines.
    
    ExecutionEngines are reusable task implementations that can be combined
    in workflows. Each execution engine encapsulates the logic to execute
    a specific type of work (shell command, Python function, container, etc).
    
    Attributes:
        engine_id: Unique identifier.
        params: Task parameters (executor-dependent).
    """
    _template = Template

    def __init__(self, engine_id: str, **kwargs):
        """Initialize execution engine.
        
        Args:
            engine_id: Unique identifier for this task
            **kwargs: Execution engine-specific parameters.
        """
        self.engine_id = engine_id
        self.params = kwargs

    @abstractmethod
    def execute(self, context: JobContext) -> Any:
        """Execute the engine.
        
        Must be implemented by subclasses. Execution engines should:
        1. Use context.xcom_pull() to get inputs from upstream tasks
        2. Perform the actual work
        3. Use context.xcom_push() to return results
        4. Use context.add_log() for logging
        5. Use context.save_artifact() to register outputs
        
        Args:
            context: Operation execution context (XCom, logs, artifacts).
            
        Returns:
            Result of execution (any serializable type).
        """
        raise NotImplementedError
    
    def __repr__(self) -> str:
        """String representation of execution engine."""
        return f"{self.__class__.__name__}(engine_id='{self.engine_id}')"


class BashExecutionEngine(BaseExecutionEngine):
    """Execute a bash shell command.

    Executes arbitrary shell commands, capturing stdout/stderr.
    Supports template variable substitution in bash_command and env.

    Attributes:
        bash_command: Bash command to execute.
        env: Environment variables (optional).

    Example:
        >>> engine = BashExecutionEngine(
        ...     engine_id='run_sim',
        ...     bash_command='python scripts/simulate.py --input {input_file}',
        ...     env={'PYTHONUNBUFFERED': '1'}
        ... )
        >>> result = engine.execute(context)
    """

    def __init__(self, engine_id: str, bash_command: str, env: Optional[Dict[str, str]] = None, **kwargs):
        """Initialize BashExecutionEngine.

        Args:
            engine_id: Task identifier.
            bash_command: Command to execute (supports template variables).
            env: Environment variables.
            **kwargs: Additional parameters.
        """
        super().__init__(engine_id, **kwargs)
        self.bash_command = bash_command
        self.env = env or {}

    def execute(self, context: JobContext) -> Dict[str, Any]:
        """Execute bash command.

        Args:
            context: Task context.

        Returns:
            Dict with 'stdout', 'stderr', 'returncode'.

        Raises:
            RuntimeError: If command fails (returncode != 0).
        """
        try:
            # Template substitution (simple string formatting)
            command = self._template.substitute(self.bash_command, context)

            context.add_log(f"Executing bash command: {command}")

            # Execute command
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                env={**os.environ, **self.env} if self.env else None,
                cwd=context.execution_dir
            )

            # Log output
            if result.stdout:
                context.add_log(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                context.add_log(f"STDERR:\n{result.stderr}")

            # Push results to XCom
            output = {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode
            }
            context.xcom_push('return_value', output)

            if result.returncode != 0:
                raise RuntimeError(f"Command failed with code {result.returncode}")

            return output

        except Exception as e:
            context.add_log(f"ERROR: {str(e)}")
            raise


class PythonExecutionEngine(BaseExecutionEngine):
    """Execute a Python callable (function).

    Executes a Python function with optional arguments.
    The function receives the JobContext as first argument.

    Attributes:
        python_callable: Function to execute.
        op_args: Positional arguments to function.
        op_kwargs: Keyword arguments to function.

    Example:
        >>> def compute_metrics(context, threshold=0.5):
        ...     data = context.xcom_pull('upstream_task', 'data')
        ...     result = apply_threshold(data, threshold)
        ...     context.xcom_push('metrics', result)
        ...     return result
        >>> 
        >>> engine = PythonExecutionEngine(
        ...     engine_id='compute',
        ...     python_callable=compute_metrics,
        ...     op_kwargs={'threshold': 0.7}
        ... )
    """

    def __init__(
        self,
        engine_id: str,
        python_callable: Callable,
        op_args: Optional[tuple] = None,
        op_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        """Initialize PythonExecutionEngine.

        Args:
            job_id: Task identifier.
            python_callable: Function to execute.
            op_args: Positional arguments (after context).
            op_kwargs: Keyword arguments.
            **kwargs: Additional parameters.
        """
        super().__init__(engine_id, **kwargs)
        self.python_callable = python_callable
        self.op_args = op_args or ()
        self.op_kwargs = op_kwargs or {}

    def execute(self, context: JobContext) -> Any:
        """Execute Python function.

        Args:
            context: Task context (passed as first argument to callable).

        Returns:
            Function return value.

        Raises:
            Exception: Any exception raised by the function.
        """
        try:
            context.add_log(f"Executing Python callable: {self.python_callable.__name__}")

            # Call function with context as first argument
            result = self.python_callable(context, *self.op_args, **self.op_kwargs)

            context.add_log(f"Function returned: {result}")

            # Push return value to XCom
            context.xcom_push('return_value', result)

            return result

        except Exception as e:
            context.add_log(f"ERROR: {str(e)}")
            raise


class ContainerExecutionEngine(BaseExecutionEngine):
    """Execute a Docker container.

    Runs a Docker image with specified parameters. Supports:
    - Environment variables
    - Volume mounts
    - Resource limits
    - Container command override

    Attributes:
        image: Docker image URI (e.g., 'python:3.10', 'ghcr.io/user/sim:latest').
        command: Container command override (optional).
        environment: Environment variables to pass into container.
        volumes: Volume mounts ({host_path: container_path}).
        resources: Resource constraints (memory, cpus, etc).

    Example:
        >>> engine = ContainerExecutionEngine(
        ...     engine_id='run_simulation',
        ...     image='physics-sim:1.0',
        ...     command=['/app/run_sim.sh'],
        ...     environment={
        ...         'INPUT_FILE': '/data/input.json',
        ...         'OUTPUT_DIR': '/output'
        ...     },
        ...     volumes={
        ...         '/host/data': '/data',
        ...         '/host/output': '/output'
        ...     },
        ...     resources={
        ...         'memory': '4g',
        ...         'cpus': '2'
        ...     }
        ... )
    """

    def __init__(
        self,
        engine_id: str,
        image: str,
        command: Optional[List[str]] = None,
        environment: Optional[Dict[str, str]] = None,
        volumes: Optional[Dict[str, str]] = None,
        resources: Optional[Dict[str, str]] = None,
        **kwargs
    ):
        """Initialize ContainerExecutionEngine.

        Args:
            engine_id: Task identifier.
            image: Docker image URI.
            command: Container command (overrides ENTRYPOINT).
            environment: Environment variables in container.
            volumes: Volume mounts (host_path: container_path).
            resources: Resource constraints.
            **kwargs: Additional parameters.
        """
        super().__init__(engine_id, **kwargs)
        self.image = image
        self.command = command
        self.environment = environment or {}
        self.volumes = volumes or {}
        self.resources = resources or {}

    def execute(self, context: JobContext) -> Dict[str, Any]:
        """Execute Docker container.

        Args:
            context: Task context.

        Returns:
            Dict with 'container_id', 'stdout', 'stderr', 'returncode'.

        Raises:
            RuntimeError: If docker run fails.
        """
        try:
            context.add_log(f"Running Docker container: {self.image}")

            # Build docker run command
            docker_cmd = self._build_docker_command(context)

            context.add_log(f"Docker command: {docker_cmd}")

            # Execute docker command
            result = subprocess.run(
                docker_cmd,
                shell=True,
                capture_output=True,
                text=True,
                cwd=context.execution_dir
            )

            # Log output
            if result.stdout:
                context.add_log(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                context.add_log(f"STDERR:\n{result.stderr}")

            # Extract container ID from output (if available)
            output = {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode,
                'image': self.image
            }
            context.xcom_push('return_value', output)

            if result.returncode != 0:
                raise RuntimeError(f"Docker container failed with code {result.returncode}")

            return output

        except Exception as e:
            context.add_log(f"ERROR: {str(e)}")
            raise

    def _build_docker_command(self, context: JobContext) -> str:
        """Build docker run command.
        
        Args:
            context: Task context.
            
        Returns:
            Docker run command string.
        """
        cmd_parts = ['docker', 'run', '--rm']
        
        # Add environment variables
        for key, value in self.environment.items():
            # Template substitution for environment values
            value_resolved = self._template.substitute(value, context)
            cmd_parts.append(f'-e {key}={value_resolved}')

        # Add volume mounts
        for host_path, container_path in self.volumes.items():
            cmd_parts.append(f'-v {host_path}:{container_path}')

        # Add resource constraints
        if 'memory' in self.resources:
            cmd_parts.append(f'-m {self.resources["memory"]}')
        if 'cpus' in self.resources:
            cmd_parts.append(f'--cpus {self.resources["cpus"]}')

        # Add image
        cmd_parts.append(self.image)

        # Add command override
        if self.command:
            cmd_parts.extend(self.command)

        return ' '.join(cmd_parts)


class StackExecutionEngine(BaseExecutionEngine):
    """Execute layers of an experimental software stack.

    Runs a sequence of layers of a generic experimental
    software stack.

    Example:
        >>> engine = StackExecutionEngine(
        ...     engine_id='run_simulation',
        ...     stack_type='EpicStack',
        ...     layers=[
        ...         StackLayerConfig(
        ...             name='sim',
        ...             inputs='in.hepmc3.tree.root',
        ...             outputs='out.edm4hep.root',
        ...         ],
        ...     ]
        ... )
    """

    def __init__(
        self,
        engine_id: str,
        stack_type: str,
        layers: List[StackLayerConfig],
        **kwargs
    ):
        """Initialize StackExecutionEngine

        Args:
            engine_id: Task identifier
            stack_type: Which type of stack to use (e.g. 'EpicStack')
            layers: List of layers to run
        """
        super().__init__(engine_id, **kwargs)
        self.layers = layers
        self.stack_type = stack_type
        self.stack_class = StackRegistry.get_experimental_stack(self.stack_type)
        if not self.stack_class:
            raise ValueError(f"Unknown stack type: {stack_type}")

    def execute(self, context: JobContext) -> Dict[str, Any]:
        """Execute experimental stack

        Args:
            context: Task context.

        Returns:
            Dict with 'stdout', 'stderr', 'returncode'

        Raises:
            RuntimeError: If execution fails

        Note:
            Layer inputs, outputs, and arguments are pushed
            to XCom for retrieval downstream.
        """
        stack = self.stack_class()

        # Do any preparations ahead of execution
        preparations = stack.prepare_for_execution(context = context)

        # Substitute templates in each layer's inputs/outputs/args and
        # push info to XCom for downstream tasks
        for layer in self.layers:
            self._apply_template_substitution(layer, context)
            context.xcom_push(f'{layer.name}:inputs', layer.inputs)
            context.xcom_push(f'{layer.name}:outputs', layer.outputs)
            context.xcom_push(f'{layer.name}:arguments', layer.arguments)

        # Build driver script and command to run it
        driver = f"{context.execution_dir}/{self.engine_id}_driver.sh"
        command = stack.make_driver_command(driver)
        stack.make_driver_script(
            script=driver,
            configs=self.layers,
            preparations=preparations,
            context=context,
        )

        # Append script and command to context
        context.add_log(f"Driver script: {driver}")
        context.add_log(f"Driver command: {command}")

        # Try running command
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
            )

            # Log output
            if result.stdout:
                context.add_log(f"STDOUT:\n{result.stdout}")
            if result.stderr:
                context.add_log(f"STDERR:\n{result.stderr}")

            # Push any output to XCom
            output = {
                'stdout': result.stdout,
                'stderr': result.stderr,
                'returncode': result.returncode,
            }
            context.xcom_push('return_value', output)

            if result.returncode != 0:
                raise RuntimeError(f"{self.stack_type} execution failed with code {result.returncode}")
            return output

        # And throw generic exception if
        # something goes wrong
        except Exception as e:
            context.add_log(f"ERROR: {str(e)}")
            raise

    def _apply_template_substitution(self, layer: StackLayerConfig, context: JobContext) -> None:
        """
        Apply template substitutions to a layer config

        Args:
            layer: The layer config to apply substitutions to
            context: Context for the current job
        """
        resolved_inputs = list()
        for layer_input in layer.inputs:
            layer_input = self._template.substitute(layer_input, context)
            resolved_inputs.append(layer_input)
        layer.inputs = resolved_inputs

        resolved_outputs = list()
        for layer_output in layer.outputs:
            layer_output = self._template.substitute(layer_output, context)
            resolved_outputs.append(layer_output)
        layer.outputs = resolved_outputs

        if layer.arguments is not None:
            resolved_arguments = list()
            for layer_argument in layer.arguments:
                layer_argument = self._template.substitute(layer_argument, context)
                resolved_arguments.append(layer_argument)
            layer.arguments = resolved_arguments


__all__ = [
    'BranchContext',
    'StageContext',
    'JobContext',
    'Template',
    'BaseExecutionEngine',
    'BashExecutionEngine',
    'PythonExecutionEngine',
    'ContainerExecutionEngine',
    'StackExecutionEngine'
]
