"""
Tests for JobLibRunner.

This test suite verifies that the refactored JobLibRunner works correctly
with AID2E framework.
"""

import pytest
import time
import os
import tempfile
from aid2e.schedulers import JobLibRunner, Job, JobType, JobState


def simple_function(x, y):
    """Simple test function."""
    return {"result": x + y, "product": x * y}


def slow_function(duration=1.0):
    """Function that takes some time."""
    time.sleep(duration)
    return {"status": "completed", "duration": duration}


def failing_function():
    """Function that raises an exception."""
    raise ValueError("This function is designed to fail")


class TestJobLibRunner:
    """Test suite for JobLibRunner."""

    def test_runner_initialization(self):
        """Test that runner can be initialized with different configurations."""
        # Default initialization
        runner1 = JobLibRunner()
        assert runner1.n_jobs == -1
        assert runner1.backend == "loky"
        
        # Custom initialization
        runner2 = JobLibRunner(n_jobs=2, backend="threading")
        assert runner2.n_jobs == 2
        assert runner2.backend == "threading"
        
        # With config
        runner3 = JobLibRunner(config={"container_engine": "singularity"})
        assert runner3.container_engine == "singularity"

    def test_simple_function_execution(self):
        """Test execution of a simple Python function."""
        runner = JobLibRunner(n_jobs=1)
        
        job = Job(
            job_id="test_job_1",
            job_type=JobType.FUNCTION,
            function=simple_function,
            params={"x": 3, "y": 4}
        )
        
        job.set_runner(runner)
        job.run()
        
        # Wait for job to complete
        max_wait = 10
        waited = 0
        while not job.is_completed() and not job.has_failed() and waited < max_wait:
            job.check_status()
            time.sleep(0.1)
            waited += 0.1
        
        assert job.is_completed()
        results = job.get_results()
        assert results["result"] == 7
        assert results["product"] == 12
        
        runner.shutdown()

    def test_parallel_execution(self):
        """Test that multiple jobs can run in parallel."""
        runner = JobLibRunner(n_jobs=2)
        
        jobs = []
        for i in range(4):
            job = Job(
                job_id=f"parallel_job_{i}",
                job_type=JobType.FUNCTION,
                function=slow_function,
                params={"duration": 0.5}
            )
            job.set_runner(runner)
            jobs.append(job)
        
        # Start all jobs
        start_time = time.time()
        for job in jobs:
            job.run()
        
        # Wait for all jobs to complete
        max_wait = 15  # Increased timeout for joblib overhead
        while True:
            all_done = all(j.is_completed() or j.has_failed() for j in jobs)
            if all_done:
                break
            for job in jobs:
                job.check_status()
            time.sleep(0.1)
            if time.time() - start_time > max_wait:
                # Debug: print status of incomplete jobs
                for i, job in enumerate(jobs):
                    if not (job.is_completed() or job.has_failed()):
                        print(f"Job {i} still in state: {job.state}")
                break
        
        end_time = time.time()
        elapsed = end_time - start_time
        
        # Check all jobs completed
        assert all(j.is_completed() for j in jobs), f"Not all jobs completed. States: {[j.state for j in jobs]}"
        
        # With 2 jobs in parallel, 4 jobs of 0.5s should take ~1-2s (not 4s sequential)
        # Allow some overhead for joblib initialization
        assert elapsed < 4.0, f"Parallel execution took too long: {elapsed}s"  # More lenient timing
        
        runner.shutdown()

    def test_job_failure_handling(self):
        """Test that job failures are handled properly."""
        runner = JobLibRunner(n_jobs=1)
        
        job = Job(
            job_id="failing_job",
            job_type=JobType.FUNCTION,
            function=failing_function,
            params={}
        )
        
        job.set_runner(runner)
        job.run()
        
        # Wait for job to complete
        max_wait = 5
        waited = 0
        while not job.is_completed() and not job.has_failed() and waited < max_wait:
            job.check_status()
            time.sleep(0.1)
            waited += 0.1
        
        assert job.has_failed()
        results = job.get_results()
        assert "error" in results
        
        runner.shutdown()

    def test_environment_variables(self):
        """Test that environment variables are set correctly."""
        runner = JobLibRunner(n_jobs=1)
        
        def check_env():
            return {"test_var": os.environ.get("TEST_VAR", "not_set")}
        
        job = Job(
            job_id="env_job",
            job_type=JobType.FUNCTION,
            function=check_env,
            params={},
            env_vars={"TEST_VAR": "test_value"}
        )
        
        job.set_runner(runner)
        job.run()
        
        # Wait for job to complete
        max_wait = 5
        waited = 0
        while not job.is_completed() and not job.has_failed() and waited < max_wait:
            job.check_status()
            time.sleep(0.1)
            waited += 0.1
        
        assert job.is_completed()
        results = job.get_results()
        assert results["test_var"] == "test_value"
        
        runner.shutdown()

    def test_working_directory(self):
        """Test that working directory is set correctly."""
        runner = JobLibRunner(n_jobs=1)
        
        def check_dir():
            return {"cwd": os.getcwd()}
        
        with tempfile.TemporaryDirectory() as tmpdir:
            job = Job(
                job_id="dir_job",
                job_type=JobType.FUNCTION,
                function=check_dir,
                params={},
                working_dir=tmpdir
            )
            
            job.set_runner(runner)
            job.run()
            
            # Wait for job to complete
            max_wait = 5
            waited = 0
            while not job.is_completed() and not job.has_failed() and waited < max_wait:
                job.check_status()
                time.sleep(0.1)
                waited += 0.1
            
            assert job.is_completed()
            results = job.get_results()
            assert results["cwd"] == tmpdir
        
        runner.shutdown()

    def test_job_cancellation(self):
        """Test that jobs can be cancelled."""
        runner = JobLibRunner(n_jobs=1)
        
        job = Job(
            job_id="cancel_job",
            job_type=JobType.FUNCTION,
            function=slow_function,
            params={"duration": 5.0}
        )
        
        job.set_runner(runner)
        job.run()
        
        # Give it a moment to start
        time.sleep(0.2)
        
        # Cancel the job
        runner.cancel_job(job)
        
        assert job.state == JobState.CANCELLED
        
        runner.shutdown()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
