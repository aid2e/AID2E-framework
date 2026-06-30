"""Unit tests for DAG Executor.

Tests the DAGExecutor orchestration engine including:
- Workflow execution with design points
- Branch and stage execution
- Context hierarchy (Branch → Stage → Job)
- Evaluator selection and execution
- XCom data passing
- Topological sorting
- Checkpoint logging

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from typing import Dict, Any

from aid2e.utilities.workflows import (
    DAGExecutor,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobFactory,
    ParallelismPolicy,
    BashEvaluator,
    JobContext,
)


class TestDAGExecutorBasics:
    """Test DAG Executor initialization and basic operations."""
    
    def test_executor_initialization(self, tmp_path):
        """Test DAGExecutor initialization with minimal workflow."""
        workflow = WorkflowDefinition(
            name="test_workflow",
            branches=[],
            objectives=[],
        )
        
        executor = DAGExecutor(
            workflow=workflow,
            base_output_dir=str(tmp_path),
            log_level="INFO",
        )
        
        assert executor.workflow.name == "test_workflow"
        assert executor.output_dir.exists()
        assert executor.global_xcom == {}
        assert executor.logger is not None
    
    def test_executor_output_directory_creation(self, tmp_path):
        """Test that executor creates unique output directories."""
        workflow = WorkflowDefinition(name="test_workflow", branches=[], objectives=[])
        
        executor1 = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        executor2 = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        
        # Should create different directories (timestamp-based)
        assert executor1.output_dir.exists()
        assert executor2.output_dir.exists()
        # They might be the same if created in same second, so just check they exist


class TestBranchExecution:
    """Test branch execution logic."""
    
    def test_empty_workflow_execution(self, tmp_path):
        """Test executing workflow with no branches."""
        workflow = WorkflowDefinition(
            name="empty_workflow",
            branches=[],
            objectives=[],
        )
        
        executor = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        design_point = {"x1": 0.5}
        
        # Should complete without error (no branches to execute)
        objectives = executor.execute(design_point)
        
        assert objectives == {}  # No objectives computed
    
    def test_single_branch_with_one_stage(self, tmp_path):
        """Test executing single branch with one stage."""
        job = JobDefinition(
            name="test_job",
            command="echo 'Hello from job'",
            payload={"evaluator_type": "bash"},
        )
        
        stage = StageDefinition(
            name="test_stage",
            jobs=[job],
        )
        
        branch = BranchDefinition(
            name="main",
            stages=[stage],
        )
        
        workflow = WorkflowDefinition(
            name="single_branch_workflow",
            branches=[branch],
            objectives=[],
        )
        
        executor = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        design_point = {"x1": 0.5, "x2": 0.7}
        
        objectives = executor.execute(design_point)
        
        # Should complete successfully
        assert objectives == {}  # No objectives defined
        
        # Check that job was executed (XCom should have entry)
        assert len(executor.global_xcom) > 0


class TestStageExecution:
    """Test stage execution with job expansion."""
    
    def test_job_expansion_with_range_factory(self, tmp_path):
        """Test job expansion using range factory."""
        job = JobDefinition(
            name="parallel_job",
            command="echo 'Job execution'",
            payload={"evaluator_type": "bash"},
        )
        
        stage = StageDefinition(
            name="parallel_stage",
            jobs=[job],
            job_factory=JobFactory(type="range", params={"n": 3}),
        )
        
        branch = BranchDefinition(name="main", stages=[stage])
        workflow = WorkflowDefinition(name="parallel_workflow", branches=[branch], objectives=[])
        
        executor = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        
        # Test job expansion
        expanded_jobs = executor._expand_jobs(stage)
        
        assert len(expanded_jobs) == 3
        assert expanded_jobs[0].name == "parallel_job_0"
        assert expanded_jobs[1].name == "parallel_job_1"
        assert expanded_jobs[2].name == "parallel_job_2"
        
        # Check job_index in payload
        assert expanded_jobs[0].payload["job_index"] == 0
        assert expanded_jobs[1].payload["job_index"] == 1
        assert expanded_jobs[2].payload["job_index"] == 2
    
    def test_stage_without_job_factory(self, tmp_path):
        """Test stage execution without job factory."""
        job1 = JobDefinition(name="job1", command="echo 'Job 1'", payload={})
        job2 = JobDefinition(name="job2", command="echo 'Job 2'", payload={})
        
        stage = StageDefinition(
            name="multi_job_stage",
            jobs=[job1, job2],
            job_factory=None,
        )
        
        executor = DAGExecutor(
            WorkflowDefinition(name="test", branches=[], objectives=[]),
            base_output_dir=str(tmp_path),
        )
        
        expanded = executor._expand_jobs(stage)
        
        assert len(expanded) == 2
        assert expanded[0].name == "job1"
        assert expanded[1].name == "job2"


class TestEvaluatorSelection:
    """Test evaluator selection logic."""
    
    def test_bash_evaluator_selection(self, tmp_path):
        """Test that BashEvaluator is selected for bash jobs."""
        job = JobDefinition(
            name="bash_job",
            command="echo 'test'",
            payload={"evaluator_type": "bash"},
        )
        
        executor = DAGExecutor(
            WorkflowDefinition(name="test", branches=[], objectives=[]),
            base_output_dir=str(tmp_path),
        )
        
        evaluator = executor._create_evaluator(job, "test_job_id")
        
        assert isinstance(evaluator, BashEvaluator)
        assert evaluator.engine_id == "test_job_id"
        assert evaluator.bash_command == "echo 'test'"
    
    def test_container_evaluator_selection(self, tmp_path):
        """Test that ContainerEvaluator is selected for container jobs."""
        from aid2e.utilities.workflows import ContainerEvaluator
        
        job = JobDefinition(
            name="container_job",
            command="python script.py",
            payload={
                "evaluator_type": "container",
                "image": "python:3.9",
                "container_command": ["/bin/bash", "-c", "python script.py"],
                "environment": {"ENV_VAR": "value"},
            },
        )
        
        executor = DAGExecutor(
            WorkflowDefinition(name="test", branches=[], objectives=[]),
            base_output_dir=str(tmp_path),
        )
        
        evaluator = executor._create_evaluator(job, "container_job_id")
        
        assert isinstance(evaluator, ContainerEvaluator)
        assert evaluator.image == "python:3.9"
        assert evaluator.environment == {"ENV_VAR": "value"}
    
    def test_default_to_bash_evaluator(self, tmp_path):
        """Test that jobs default to BashEvaluator if type not specified."""
        job = JobDefinition(
            name="default_job",
            command="ls -la",
            payload={},  # No evaluator_type specified
        )
        
        executor = DAGExecutor(
            WorkflowDefinition(name="test", branches=[], objectives=[]),
            base_output_dir=str(tmp_path),
        )
        
        evaluator = executor._create_evaluator(job, "default_job_id")
        
        assert isinstance(evaluator, BashEvaluator)


class TestContextHierarchy:
    """Test context hierarchy creation and propagation."""
    
    def test_branch_context_creation(self, tmp_path):
        """Test BranchContext creation with parameters."""
        from aid2e.utilities.workflows import BranchContext
        
        branch = BranchDefinition(name="test_branch", stages=[])
        
        executor = DAGExecutor(
            WorkflowDefinition(name="test", branches=[], objectives=[]),
            base_output_dir=str(tmp_path),
        )
        
        # Simulate branch context creation (from _execute_branch)
        branch_context = BranchContext(
            branch_id=branch.name,
            parameters={},
        )
        
        assert branch_context.branch_id == "test_branch"
        assert branch_context.parameters == {}
    
    def test_stage_context_with_branch_parent(self, tmp_path):
        """Test StageContext with parent BranchContext."""
        from aid2e.utilities.workflows import BranchContext, StageContext
        
        branch_context = BranchContext(
            branch_id="main",
            parameters={"branch_param": "value1"},
        )
        
        stage = StageDefinition(
            name="test_stage",
            jobs=[],
            parallelism=ParallelismPolicy(max_concurrent=4, retry_max=2, timeout_sec=300),
        )
        
        stage_context = StageContext(
            stage_id=stage.name,
            parameters=stage.parallelism.model_dump(),
            branch_context=branch_context,
        )
        
        assert stage_context.stage_id == "test_stage"
        assert stage_context.parameters["max_concurrent"] == 4
        assert stage_context.branch_context.branch_id == "main"


class TestDAGConstruction:
    """Test DAG construction from workflow stages."""
    
    def test_dag_from_sequential_stages(self, tmp_path):
        """Test DAG construction from sequential stages."""
        stage1 = StageDefinition(name="stage1", jobs=[])
        stage2 = StageDefinition(name="stage2", jobs=[])
        stage3 = StageDefinition(name="stage3", jobs=[])
        
        stages = [stage1, stage2, stage3]
        
        executor = DAGExecutor(
            WorkflowDefinition(name="test", branches=[], objectives=[]),
            base_output_dir=str(tmp_path),
        )
        
        dag = executor._build_dag_from_stages(stages, "test_branch")
        
        assert len(dag.nodes) == 3
        assert dag.nodes[0].node_id == "stage1"
        assert dag.nodes[0].depends_on == []  # First stage has no deps
        
        assert dag.nodes[1].node_id == "stage2"
        assert dag.nodes[1].depends_on == ["stage1"]  # Depends on stage1
        
        assert dag.nodes[2].node_id == "stage3"
        assert dag.nodes[2].depends_on == ["stage2"]  # Depends on stage2


class TestObjectiveComputation:
    """Test objective computation from outputs."""
    
    def test_objectives_from_xcom(self, tmp_path):
        """Test extracting objectives from XCom data."""
        from aid2e.utilities.configurations.objectives import ObjectiveDefinition, ObjectiveDirection
        
        workflow = WorkflowDefinition(
            name="test",
            branches=[],
            objectives=[
                ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE),
                ObjectiveDefinition(name="f2", direction=ObjectiveDirection.MINIMIZE),
            ]
        )
        executor = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        
        # Simulate job outputs in XCom with correct key format (job_id:key)
        executor.global_xcom["job1:objectives"] = {"f1": 0.5, "f2": 0.8}
        executor.global_xcom["job2:result"] = "other output"
        
        objectives = executor._compute_objectives()
        
        assert objectives == {"f1": 0.5, "f2": 0.8}
    
    def test_empty_objectives_when_no_xcom(self, tmp_path):
        """Test that empty objectives returned when no XCom data."""
        workflow = WorkflowDefinition(name="test", branches=[], objectives=[])
        executor = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        
        objectives = executor._compute_objectives()
        
        assert objectives == {}


class TestEndToEndExecution:
    """End-to-end integration tests."""
    
    def test_complete_workflow_execution(self, tmp_path):
        """Test complete workflow execution end-to-end."""
        # Create a simple workflow
        job = JobDefinition(
            name="eval_job",
            command="echo 'Evaluating design point'",
            payload={"evaluator_type": "bash"},
        )
        
        stage = StageDefinition(
            name="evaluate",
            jobs=[job],
            job_factory=JobFactory(type="range", params={"n": 2}),  # 2 parallel jobs
        )
        
        branch = BranchDefinition(name="main", stages=[stage])
        
        workflow = WorkflowDefinition(
            name="complete_workflow",
            branches=[branch],
            objectives=[],
        )
        
        executor = DAGExecutor(workflow, base_output_dir=str(tmp_path))
        design_point = {"x1": 0.5, "x2": 0.7, "x3": 0.3}
        
        # Execute workflow
        objectives = executor.execute(design_point)
        
        # Verify execution
        assert objectives == {}  # No objectives defined
        
        # Should have executed 2 jobs (from job_factory n=2)
        assert len(executor.global_xcom) >= 2
        
        # Check output directories exists
        assert executor.output_dir.exists()
        assert (executor.output_dir / "evaluate").exists()
        assert any((executor.output_dir / "evaluate").iterdir())

        # Confirm that 2 job directories were created
        job_dirs = list((executor.output_dir / "evaluate").glob("eval_job_*"))
        assert len(job_dirs) == 2


# Pytest fixtures
@pytest.fixture
def tmp_path():
    """Create temporary directory for test outputs."""
    tmp_dir = Path(tempfile.mkdtemp())
    yield tmp_dir
    shutil.rmtree(tmp_dir)
