"""Unit tests for ExecutionEngine module.

Tests cover:
- JobContext (XCom push/pull, artifacts, logs)
- BashExecutionEngine (command execution, templating)
- PythonExecutionEngine (function execution, arguments)
- ContainerExecutionEngine (docker command building)

Project: AID2E v0.0.0
"""

import pytest
from pathlib import Path
import json
import tempfile
import os

from aid2e.utilities.workflows.execution_engine import (
    JobContext,
    BashExecutionEngine,
    PythonExecutionEngine,
    ContainerExecutionEngine,
    BaseExecutionEngine,
)


class TestJobContext:
    """Test JobContext (XCom and artifact management)."""
    
    def test_task_context_init(self):
        """Test JobContext initialization."""
        context = JobContext(
            job_id='task_1',
            stage_id='stage_eval',
            workflow_id='workflow_1',
            design_point={'x': 0.5},
            execution_dir='/tmp'
        )
        
        assert context.job_id == 'task_1'
        assert context.stage_id == 'stage_eval'
        assert context.workflow_id == 'workflow_1'
        assert context.design_point == {'x': 0.5}
        assert context.execution_dir == '/tmp'
        assert len(context.xcom) == 0
        assert len(context.artifacts) == 0
        assert len(context.logs) == 0
    
    def test_xcom_push_and_pull(self):
        """Test XCom push/pull functionality."""
        context = JobContext(
            job_id='upstream_task',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        # Push data
        context.xcom_push('metrics', {'f1': 0.5, 'f2': 0.3})
        context.xcom_push('status', 'success')
        
        # Pull from own task
        assert context.xcom_pull('upstream_task', key='metrics') == {'f1': 0.5, 'f2': 0.3}
        assert context.xcom_pull('upstream_task', key='status') == 'success'
        assert context.xcom_pull('upstream_task', key='nonexistent') is None
    
    def test_xcom_push_return_value_default(self):
        """Test default 'return_value' key in XCom."""
        context = JobContext(job_id='task_1', stage_id='s', workflow_id='w')
        
        # Push with default key
        context.xcom_push('return_value', 42)
        
        # Pull with default key
        assert context.xcom_pull('task_1') == 42
    
    def test_add_log(self):
        """Test log addition."""
        context = JobContext(job_id='t', stage_id='s', workflow_id='w')
        
        context.add_log('Starting execution')
        context.add_log('Step 1 complete')
        
        assert len(context.logs) == 2
        assert context.logs[0] == 'Starting execution'
        assert context.logs[1] == 'Step 1 complete'
    
    def test_save_artifact(self):
        """Test artifact registration."""
        context = JobContext(job_id='t', stage_id='s', workflow_id='w')
        
        context.save_artifact('objectives', '/work/objectives.json')
        context.save_artifact('metrics', '/work/metrics.json')
        
        assert context.artifacts['objectives'] == '/work/objectives.json'
        assert context.artifacts['metrics'] == '/work/metrics.json'


class TestBashExecutionEngine:
    """Test BashExecutionEngine."""
    
    def test_bash_engine_init(self):
        """Test BashExecutionEngine initialization."""
        op = BashExecutionEngine(
            job_id='run_sim',
            bash_command='python script.py',
            env={'DEBUG': '1'}
        )
        
        assert op.job_id == 'run_sim'
        assert op.bash_command == 'python script.py'
        assert op.env == {'DEBUG': '1'}
    
    def test_bash_engine_simple_command(self):
        """Test executing simple bash command."""
        context = JobContext(
            job_id='test_bash',
            stage_id='stage',
            workflow_id='workflow',
            execution_dir=None
        )
        
        op = BashExecutionEngine(
            job_id='echo_test',
            bash_command='echo "Hello World"'
        )
        
        result = op.execute(context)
        
        assert result['returncode'] == 0
        assert 'Hello World' in result['stdout']
    
    def test_bash_engine_with_environment(self):
        """Test bash engine with environment variables."""
        context = JobContext(
            job_id='test_env',
            stage_id='stage',
            workflow_id='workflow',
            execution_dir=None
        )
        
        op = BashExecutionEngine(
            job_id='check_env',
            bash_command='echo $TEST_VAR',
            env={'TEST_VAR': 'test_value'}
        )
        
        result = op.execute(context)
        assert result['returncode'] == 0
    
    def test_bash_engine_failure(self):
        """Test bash engine with failing command."""
        context = JobContext(
            job_id='test_fail',
            stage_id='stage',
            workflow_id='workflow',
            execution_dir=None
        )
        
        op = BashExecutionEngine(
            job_id='fail_test',
            bash_command='exit 1'
        )
        
        with pytest.raises(RuntimeError, match='Command failed'):
            op.execute(context)
    
    def test_bash_engine_template_substitution(self):
        """Test template variable substitution."""
        context = JobContext(
            job_id='test_template',
            stage_id='stage',
            workflow_id='workflow',
            design_point={'input_file': 'test.json', 'output_file': 'out.json'}
        )
        
        op = BashExecutionEngine(
            job_id='template_test',
            bash_command='echo {design_point.input_file} {design_point.output_file}'
        )
        
        # Test substitution method
        substituted = op._substitute_templates(
            'Processing {design_point.input_file} to {design_point.output_file}',
            context
        )
        
        assert substituted == 'Processing test.json to out.json'


class TestPythonExecutionEngine:
    """Test PythonExecutionEngine."""
    
    def test_python_engine_init(self):
        """Test PythonExecutionEngine initialization."""
        def my_func(context):
            return 42
        
        op = PythonExecutionEngine(
            job_id='compute',
            python_callable=my_func,
            op_kwargs={'param': 'value'}
        )
        
        assert op.job_id == 'compute'
        assert op.python_callable == my_func
        assert op.op_kwargs == {'param': 'value'}
    
    def test_python_engine_simple_function(self):
        """Test executing simple Python function."""
        def compute_sum(context, a=1, b=2):
            return a + b
        
        context = JobContext(
            job_id='test_python',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        op = PythonExecutionEngine(
            job_id='sum_test',
            python_callable=compute_sum,
            op_kwargs={'a': 5, 'b': 3}
        )
        
        result = op.execute(context)
        
        assert result == 8
        assert context.xcom_pull('test_python', key='return_value') == 8
    
    def test_python_engine_with_context(self):
        """Test Python function that uses JobContext."""
        def process_design_point(context):
            x = context.design_point.get('x', 0.0)
            y = context.design_point.get('y', 0.0)
            context.xcom_push('processed', {'sum': x + y})
            return {'sum': x + y, 'product': x * y}
        
        context = JobContext(
            job_id='processor',
            stage_id='stage',
            workflow_id='workflow',
            design_point={'x': 3.0, 'y': 4.0}
        )
        
        op = PythonExecutionEngine(
            job_id='process',
            python_callable=process_design_point
        )
        
        result = op.execute(context)
        
        assert result['sum'] == 7.0
        assert result['product'] == 12.0
        assert context.xcom_pull('processor', key='processed') == {'sum': 7.0}
    
    def test_python_engine_exception(self):
        """Test Python engine with exception in function."""
        def failing_func(context):
            raise ValueError("Test error")
        
        context = JobContext(
            job_id='test_fail',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        op = PythonExecutionEngine(
            job_id='fail_test',
            python_callable=failing_func
        )
        
        with pytest.raises(ValueError, match='Test error'):
            op.execute(context)
    
    def test_python_engine_with_args_kwargs(self):
        """Test Python engine with positional and keyword arguments."""
        def multi_arg_func(context, a, b, c=10):
            return a + b + c
        
        context = JobContext(
            job_id='test_args',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        op = PythonExecutionEngine(
            job_id='args_test',
            python_callable=multi_arg_func,
            op_args=(2, 3),
            op_kwargs={'c': 5}
        )
        
        result = op.execute(context)
        
        assert result == 10  # 2 + 3 + 5


class TestContainerExecutionEngine:
    """Test ContainerExecutionEngine."""
    
    def test_container_engine_init(self):
        """Test ContainerExecutionEngine initialization."""
        op = ContainerExecutionEngine(
            job_id='run_container',
            image='myimage:1.0',
            command=['/app/run.sh'],
            environment={'VAR': 'value'},
            volumes={'/host': '/container'},
            resources={'memory': '4g'}
        )
        
        assert op.job_id == 'run_container'
        assert op.image == 'myimage:1.0'
        assert op.command == ['/app/run.sh']
        assert op.environment == {'VAR': 'value'}
        assert op.volumes == {'/host': '/container'}
        assert op.resources == {'memory': '4g'}
    
    def test_container_engine_docker_command_basic(self):
        """Test basic docker command generation."""
        context = JobContext(
            job_id='test',
            stage_id='stage',
            workflow_id='workflow',
            design_point={'x': 0.5}
        )
        
        op = ContainerExecutionEngine(
            job_id='docker_test',
            image='myimage:latest'
        )
        
        cmd = op._build_docker_command(context)
        
        assert 'docker run' in cmd
        assert '--rm' in cmd
        assert 'myimage:latest' in cmd
    
    def test_container_engine_docker_with_env(self):
        """Test docker command with environment variables."""
        context = JobContext(
            job_id='test',
            stage_id='stage',
            workflow_id='workflow',
            design_point={'x': 0.5}
        )
        
        op = ContainerExecutionEngine(
            job_id='docker_env',
            image='myimage:latest',
            environment={
                'PARAM1': 'value1',
                'PARAM2': '{design_point.x}'
            }
        )
        
        cmd = op._build_docker_command(context)
        
        assert '-e PARAM1=value1' in cmd
    
    def test_container_engine_docker_with_volumes(self):
        """Test docker command with volume mounts."""
        context = JobContext(
            job_id='test',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        op = ContainerExecutionEngine(
            job_id='docker_vol',
            image='myimage:latest',
            volumes={
                '/host/data': '/data',
                '/host/output': '/output'
            }
        )
        
        cmd = op._build_docker_command(context)
        
        assert '-v /host/data:/data' in cmd
        assert '-v /host/output:/output' in cmd
    
    def test_container_engine_docker_with_resources(self):
        """Test docker command with resource constraints."""
        context = JobContext(
            job_id='test',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        op = ContainerExecutionEngine(
            job_id='docker_res',
            image='myimage:latest',
            resources={
                'memory': '4g',
                'cpus': '2'
            }
        )
        
        cmd = op._build_docker_command(context)
        
        assert '-m 4g' in cmd
        assert '--cpus 2' in cmd
    
    def test_container_engine_docker_with_command(self):
        """Test docker command with command override."""
        context = JobContext(
            job_id='test',
            stage_id='stage',
            workflow_id='workflow'
        )
        
        op = ContainerExecutionEngine(
            job_id='docker_cmd',
            image='myimage:latest',
            command=['/app/script.sh', 'arg1', 'arg2']
        )
        
        cmd = op._build_docker_command(context)
        
        assert '/app/script.sh' in cmd
        assert 'arg1' in cmd
        assert 'arg2' in cmd


class TestExecutionEngineInheritance:
    """Test execution engine inheritance and polymorphism."""
    
    def test_all_engines_inherit_from_base(self):
        """Test that all engines inherit from BaseExecutionEngine."""
        assert issubclass(BashExecutionEngine, BaseExecutionEngine)
        assert issubclass(PythonExecutionEngine, BaseExecutionEngine)
        assert issubclass(ContainerExecutionEngine, BaseExecutionEngine)
    
    def test_base_engine_repr(self):
        """Test string representation."""
        def dummy(context):
            pass
        
        bash_op = BashExecutionEngine(job_id='bash_task', bash_command='echo hi')
        python_op = PythonExecutionEngine(job_id='python_task', python_callable=dummy)
        container_op = ContainerExecutionEngine(job_id='container_task', image='img:1.0')
        
        assert 'BashExecutionEngine' in repr(bash_op)
        assert 'bash_task' in repr(bash_op)
        assert 'PythonExecutionEngine' in repr(python_op)
        assert 'ContainerExecutionEngine' in repr(container_op)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
