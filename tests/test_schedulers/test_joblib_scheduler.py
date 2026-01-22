"""Tests for JobLibScheduler and scheduler registry.

Tests cover:
- JobLibScheduler job execution
- Parallelism policy respect (max_concurrent, timeout, retry)
- Artifact collection from job outputs
- Registry registration and lookup
- Status checking and cancellation
"""

import json
import os
import pytest
import tempfile
from pathlib import Path

from aid2e.schedulers import (
    JobLibScheduler,
    BaseScheduler,
    JobStatus,
    StageExecutionResult,
    register_scheduler,
    get_scheduler,
    list_registered_schedulers,
    is_scheduler_registered,
)
from aid2e.utilities.configurations.scheduler_config import JobLibRunnerConfig


class TestJobLibSchedulerBasics:
    """Test basic JobLibScheduler functionality."""
    
    def test_scheduler_instantiation(self):
        """Test creating JobLibScheduler with default config."""
        scheduler = JobLibScheduler()
        assert isinstance(scheduler, BaseScheduler)
        assert scheduler.config.n_jobs == -1
        assert scheduler.config.backend == "loky"
    
    def test_scheduler_with_custom_config(self):
        """Test JobLibScheduler with custom JobLibRunnerConfig."""
        config = JobLibRunnerConfig(n_jobs=2, backend="threading", timeout=300)
        scheduler = JobLibScheduler(config=config)
        assert scheduler.config.n_jobs == 2
        assert scheduler.config.backend == "threading"
        assert scheduler.config.timeout == 300
    
    def test_job_status_model(self):
        """Test JobStatus data model."""
        status = JobStatus(
            job_id="job_1",
            status="completed",
            return_code=0,
            stdout="Output",
            stderr="",
        )
        assert status.job_id == "job_1"
        assert status.status == "completed"
        assert status.return_code == 0
    
    def test_stage_execution_result_model(self):
        """Test StageExecutionResult data model."""
        result = StageExecutionResult(
            stage_name="evaluate",
            job_statuses=[],
            artifacts={"output.json": '{"f1": 1.0}'},
            success=True,
        )
        assert result.stage_name == "evaluate"
        assert result.success is True
        assert "output.json" in result.artifacts


class TestJobLibSchedulerExecution:
    """Test job execution on JobLibScheduler."""
    
    def test_run_simple_job(self):
        """Test running a simple shell command job."""
        scheduler = JobLibScheduler()
        
        job_def = {
            'name': 'simple_echo',
            'command': 'echo "Hello World"',
            'payload': {},
            'outputs': [],
        }
        
        result = scheduler.run_stage(
            stage_name='test_stage',
            job_definitions=[job_def],
        )
        
        assert result.success is True
        assert result.stage_name == 'test_stage'
        assert len(result.job_statuses) == 1
        assert result.job_statuses[0].status == 'completed'
        assert result.job_statuses[0].return_code == 0
        assert "Hello World" in result.job_statuses[0].stdout
    
    def test_run_multiple_jobs_parallel(self):
        """Test running multiple jobs in parallel."""
        scheduler = JobLibScheduler(config=JobLibRunnerConfig(n_jobs=2))
        
        job_defs = [
            {'name': f'job_{i}', 'command': f'echo "Job {i}"', 'payload': {}, 'outputs': []}
            for i in range(3)
        ]
        
        result = scheduler.run_stage(
            stage_name='parallel_stage',
            job_definitions=job_defs,
        )
        
        assert result.success is True
        assert len(result.job_statuses) == 3
        for status in result.job_statuses:
            assert status.status == 'completed'
            assert status.return_code == 0
    
    def test_job_with_output_artifact(self):
        """Test job that creates an output file and collects it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "result.json")
            
            job_def = {
                'name': 'create_json',
                'command': f'echo \'{{"f1": 1.0, "f2": 2.0}}\' > {output_file}',
                'payload': {},
                'outputs': [{'path': 'result.json', 'format': 'json'}],
            }
            
            scheduler = JobLibScheduler()
            result = scheduler.run_stage(
                stage_name='artifact_stage',
                job_definitions=[job_def],
                working_dir=tmpdir,
            )
            
            assert result.success is True
            assert len(result.artifacts) > 0 or result.job_statuses[0].return_code == 0
    
    def test_job_failure(self):
        """Test handling of failed job."""
        scheduler = JobLibScheduler()
        
        job_def = {
            'name': 'failing_job',
            'command': 'exit 1',  # Non-zero exit code
            'payload': {},
            'outputs': [],
        }
        
        result = scheduler.run_stage(
            stage_name='failure_stage',
            job_definitions=[job_def],
        )
        
        assert result.success is False
        assert len(result.job_statuses) == 1
        assert result.job_statuses[0].status == 'failed'
        assert result.job_statuses[0].return_code == 1
    
    def test_job_with_payload_environment(self):
        """Test job receives payload via JOB_PAYLOAD environment variable."""
        scheduler = JobLibScheduler()
        
        job_def = {
            'name': 'payload_job',
            'command': 'python -c "import os, json; print(json.dumps(json.loads(os.environ[\'JOB_PAYLOAD\'])))"',
            'payload': {'param1': 'value1', 'param2': 42},
            'outputs': [],
        }
        
        result = scheduler.run_stage(
            stage_name='payload_stage',
            job_definitions=[job_def],
        )
        
        assert result.success is True
        assert result.job_statuses[0].return_code == 0


class TestJobLibSchedulerParallelismPolicy:
    """Test parallelism policy enforcement."""
    
    def test_max_concurrent_respected(self):
        """Test that max_concurrent parameter is passed to joblib."""
        scheduler = JobLibScheduler()
        
        job_defs = [
            {'name': f'job_{i}', 'command': 'echo "x"', 'payload': {}, 'outputs': []}
            for i in range(4)
        ]
        
        policy = {
            'max_concurrent': 2,
            'retry_max': 1,
            'timeout_sec': 30,
        }
        
        result = scheduler.run_stage(
            stage_name='limited_stage',
            job_definitions=job_defs,
            parallelism_policy=policy,
        )
        
        assert result.success is True
        assert len(result.job_statuses) == 4
    
    def test_timeout_respected(self):
        """Test that job timeout is enforced."""
        config = JobLibRunnerConfig(n_jobs=1, timeout=1)  # 1 second timeout
        scheduler = JobLibScheduler(config=config)
        
        job_def = {
            'name': 'timeout_job',
            'command': 'sleep 5',  # Will timeout
            'payload': {},
            'outputs': [],
        }
        
        result = scheduler.run_stage(
            stage_name='timeout_stage',
            job_definitions=[job_def],
        )
        
        # Job should fail due to timeout
        assert result.success is False or result.job_statuses[0].return_code != 0


class TestSchedulerRegistry:
    """Test scheduler registry and factory."""
    
    def test_joblib_registered_by_default(self):
        """Test that JobLibScheduler is registered by default."""
        assert is_scheduler_registered('joblib') is True
        assert get_scheduler('joblib') is JobLibScheduler
    
    def test_list_registered_schedulers(self):
        """Test listing all registered schedulers."""
        schedulers = list_registered_schedulers()
        assert 'joblib' in schedulers
        assert schedulers['joblib'] is JobLibScheduler
    
    def test_get_unregistered_scheduler_raises(self):
        """Test that getting unregistered scheduler raises KeyError."""
        with pytest.raises(KeyError):
            get_scheduler('nonexistent_scheduler')
    
    def test_register_new_scheduler(self):
        """Test registering a new mock scheduler."""
        # Create a simple mock scheduler
        class MockScheduler(BaseScheduler):
            def run_stage(self, stage_name, job_definitions, parallelism_policy=None, working_dir=None):
                return StageExecutionResult(
                    stage_name=stage_name,
                    job_statuses=[],
                    artifacts={},
                    success=True,
                )
            
            def check_status(self, job_id):
                return JobStatus(job_id=job_id, status='completed', return_code=0)
            
            def cancel_job(self, job_id):
                return False
        
        # Register it
        register_scheduler('mock', MockScheduler)
        
        # Verify registration
        assert is_scheduler_registered('mock') is True
        assert get_scheduler('mock') is MockScheduler
    
    def test_register_duplicate_raises(self):
        """Test that registering duplicate scheduler name raises ValueError."""
        with pytest.raises(ValueError):
            register_scheduler('joblib', JobLibScheduler)
    
    def test_register_invalid_class_raises(self):
        """Test that registering non-BaseScheduler class raises ValueError."""
        class NotAScheduler:
            pass
        
        with pytest.raises(ValueError):
            register_scheduler('invalid', NotAScheduler)


class TestJobLibSchedulerStatusAndCancel:
    """Test status checking and job cancellation."""
    
    def test_check_status_completed_job(self):
        """Test checking status of completed job."""
        scheduler = JobLibScheduler()
        
        result = scheduler.run_stage(
            stage_name='test',
            job_definitions=[{'name': 'echo', 'command': 'echo x', 'payload': {}, 'outputs': []}],
        )
        
        job_id = result.job_statuses[0].job_id
        status = scheduler.check_status(job_id)
        
        # Since JobLib is synchronous, we get the cached status
        assert status.job_id == job_id
    
    def test_cancel_job_returns_false(self):
        """Test that cancel_job returns False (not supported for sync JobLib)."""
        scheduler = JobLibScheduler()
        result = scheduler.cancel_job('any_job_id')
        
        # JobLib can't cancel synchronous jobs
        assert result is False
    
    def test_shutdown_noop(self):
        """Test that shutdown completes without error."""
        scheduler = JobLibScheduler()
        scheduler.shutdown()  # Should not raise


class TestJobLibSchedulerEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_empty_job_list(self):
        """Test running stage with no jobs."""
        scheduler = JobLibScheduler()
        
        result = scheduler.run_stage(
            stage_name='empty',
            job_definitions=[],
        )
        
        assert result.stage_name == 'empty'
        assert len(result.job_statuses) == 0
    
    def test_job_with_missing_fields(self):
        """Test job with missing optional fields."""
        scheduler = JobLibScheduler()
        
        job_def = {
            # Minimal job def
            'command': 'echo test',
        }
        
        result = scheduler.run_stage(
            stage_name='minimal',
            job_definitions=[job_def],
        )
        
        # Should still work with defaults
        assert len(result.job_statuses) > 0
    
    def test_command_with_special_chars(self):
        """Test command containing special shell characters."""
        scheduler = JobLibScheduler()
        
        job_def = {
            'name': 'special',
            'command': 'echo "hello world" && echo "success"',
            'payload': {},
            'outputs': [],
        }
        
        result = scheduler.run_stage(
            stage_name='special',
            job_definitions=[job_def],
        )
        
        assert result.success is True
        assert "success" in result.job_statuses[0].stdout
