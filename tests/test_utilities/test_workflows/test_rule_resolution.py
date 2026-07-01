"""Unit tests for rule resolution and payload validation.

Tests cover:
- Rule template resolution with various template formats
- Payload template substitution (strings, dicts, lists)
- Conditional execution via payload validation
- Logging and checkpointing
- Error handling

Project: AID2E v0.0.0
"""

import pytest
import tempfile
from pathlib import Path
from typing import Dict, Any

from aid2e.utilities.configurations.workflow_config import JobDefinition, ArtifactSpec
from aid2e.utilities.workflows.rule_resolution import (
    resolve_job_rule,
    resolve_payload_templates,
    validate_job_payload,
    RuleResolutionError,
    PayloadValidationError
)
from aid2e.utilities.workflows.execution_logger import ExecutionLogger, create_job_logger


class TestPayloadTemplateResolution:
    """Test payload template variable resolution."""
    
    def test_simple_string_template(self):
        """Test resolving simple string template."""
        payload = {"input": "{{input_design_params}}"}
        context = {"input_design_params": "/path/to/design.params"}
        
        resolved = resolve_payload_templates(payload, context)
        assert resolved["input"] == "/path/to/design.params"
    
    def test_multiple_templates_in_payload(self):
        """Test multiple template variables in payload."""
        payload = {
            "input_file": "{{input_design_params}}",
            "output_dir": "{{output_dir}}",
            "job_id": "{{job_id}}"
        }
        context = {
            "input_design_params": "/data/design.params",
            "output_dir": "/tmp/out",
            "job_id": 0
        }
        
        resolved = resolve_payload_templates(payload, context)
        assert resolved["input_file"] == "/data/design.params"
        assert resolved["output_dir"] == "/tmp/out"
        assert resolved["job_id"] == "0"  # Templates convert to strings
    
    def test_nested_dict_resolution(self):
        """Test resolving templates in nested dicts."""
        payload = {
            "metadata": {
                "input": "{{input_design_params}}",
                "version": "1.0"
            }
        }
        context = {"input_design_params": "/path/to/design.params"}
        
        resolved = resolve_payload_templates(payload, context)
        assert resolved["metadata"]["input"] == "/path/to/design.params"
        assert resolved["metadata"]["version"] == "1.0"
    
    def test_list_in_payload(self):
        """Test resolving templates in lists."""
        payload = {
            "inputs": ["{input_design_params}", "/other/file.txt"]
        }
        context = {"input_design_params": "/path/to/design.params"}
        
        resolved = resolve_payload_templates(payload, context)
        assert resolved["inputs"][0] == "/path/to/design.params"
        assert resolved["inputs"][1] == "/other/file.txt"
    
    def test_undefined_template_variable(self):
        """Test error handling for undefined template variables."""
        payload = {"input": "{{undefined_variable}}"}
        context = {}
        
        with pytest.raises(RuleResolutionError):
            resolve_payload_templates(payload, context)
    
    def test_dict_access_template(self):
        """Test dict[key] notation in templates."""
        payload = {
            "design_params": "{{stage_outputs[preparation]}}/design_params.json"
        }
        context = {
            "stage_outputs": {
                "preparation": "/tmp/stage1"
            }
        }
        
        resolved = resolve_payload_templates(payload, context)
        assert resolved["design_params"] == "/tmp/stage1/design_params.json"
    
    def test_non_string_values_pass_through(self):
        """Test that non-string values are not modified."""
        payload = {
            "count": 42,
            "enabled": True,
            "timeout": 3.5
        }
        context = {}
        
        resolved = resolve_payload_templates(payload, context)
        assert resolved["count"] == 42
        assert resolved["enabled"] is True
        assert resolved["timeout"] == 3.5


class TestRuleResolution:
    """Test rule template resolution."""
    
    def test_simple_command_rule(self):
        """Test resolving simple command rule."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            rule="{{command}}",
            payload={}
        )
        context = {}
        
        cmd = resolve_job_rule(job, context)
        assert cmd == "python script.py"
    
    def test_rule_with_payload_substitution(self):
        """Test rule with payload variable substitution."""
        job = JobDefinition(
            name="test",
            command="python compute.py",
            rule="{{command}} {{payload[input]}} {{payload[output]}}",
            payload={
                "input": "/path/to/input.json",
                "output": "/path/to/output.json"
            }
        )
        context = {}
        
        cmd = resolve_job_rule(job, context)
        assert cmd == "python compute.py /path/to/input.json /path/to/output.json"
    
    def test_rule_with_template_substitution(self):
        """Test rule with context template variables."""
        job = JobDefinition(
            name="test",
            command="python compute.py",
            rule="{{command}} {{payload[input_file]}} {{output_dir}} {{job_id}}",
            payload={
                "input_file": "{{input_design_params}}"
            }
        )
        context = {
            "input_design_params": "/data/design.params",
            "output_dir": "/tmp/out",
            "job_id": 0
        }
        
        cmd = resolve_job_rule(job, context)
        assert cmd == "python compute.py /data/design.params /tmp/out 0"
    
    def test_default_rule_if_not_specified(self):
        """Test default rule behavior when rule is None."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            rule=None,  # No rule specified
            payload={"ignored": "value"}
        )
        context = {}
        
        cmd = resolve_job_rule(job, context)
        assert cmd == "python script.py"
    
    def test_rule_with_nested_payload_access(self):
        """Test rule accessing simple payload values."""
        job = JobDefinition(
            name="test",
            command="python run.py",
            rule="{{command}} --input {{payload[input_file]}} --output {{payload[output_file]}}",
            payload={
                "input_file": "/data/input.json",
                "output_file": "/data/output.json"
            }
        )
        context = {}
        
        cmd = resolve_job_rule(job, context)
        assert "python run.py" in cmd
        assert "--input /data/input.json" in cmd
        assert "--output /data/output.json" in cmd
    
    def test_multiple_spaces_cleaned_up(self):
        """Test that multiple spaces in resolved command are cleaned up."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            rule="{{command}}    {{payload[arg1]}}    {{payload[arg2]}}",
            payload={"arg1": "val1", "arg2": "val2"}
        )
        context = {}
        
        cmd = resolve_job_rule(job, context)
        assert "  " not in cmd  # No double spaces
        assert cmd == "python script.py val1 val2"


class TestPayloadValidation:
    """Test payload validation."""
    
    def test_validation_with_required_keys_present(self):
        """Test successful validation when required keys present."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            payload={"input": "/path", "output": "/path"}
        )
        
        is_valid, error = validate_job_payload(job, required_keys=["input", "output"])
        assert is_valid is True
        assert error is None
    
    def test_validation_fails_with_missing_required_keys(self):
        """Test validation fails when required keys missing."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            payload={"input": "/path"}
        )
        
        is_valid, error = validate_job_payload(job, required_keys=["input", "output"])
        assert is_valid is False
        assert "Missing required payload keys" in error
        assert "output" in error
    
    def test_validation_with_template_resolution(self):
        """Test validation with template resolution."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            payload={"input": "{input_design_params}"}
        )
        context = {"input_design_params": "/path/to/design.params"}
        
        is_valid, error = validate_job_payload(job, context=context)
        assert is_valid is True
        assert error is None
    
    def test_validation_fails_with_undefined_template(self):
        """Test validation with undefined template variables."""
        job = JobDefinition(
            name="test",
            command="python script.py",
            payload={"input": "{{undefined_var}}"}
        )
        
        # Test: With context, template resolution should fail if var undefined
        context = {"some_var": "value"}  # undefined_var not in context
        is_valid, error = validate_job_payload(job, context=context, logger=None)
        assert is_valid is False
        assert "Cannot resolve payload templates" in error


class TestExecutionLogging:
    """Test execution logging and checkpointing."""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory for logging."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_logger_creation(self, temp_output_dir):
        """Test creating execution logger."""
        logger = ExecutionLogger(
            job_name="test_job",
            output_dir=temp_output_dir,
            log_level="INFO"
        )
        
        assert logger.job_name == "test_job"
        assert len(logger.checkpoints) > 0  # Initial checkpoint created
    
    def test_checkpoint_creation(self, temp_output_dir):
        """Test creating checkpoints."""
        logger = ExecutionLogger(
            job_name="test_job",
            output_dir=temp_output_dir
        )
        
        logger.checkpoint(
            stage="test_stage",
            status="start",
            message="Test checkpoint"
        )
        
        last_cp = logger.get_last_checkpoint()
        assert last_cp.stage == "test_stage"
        assert last_cp.status == "start"
        assert last_cp.message == "Test checkpoint"
    
    def test_checkpoint_file_creation(self, temp_output_dir):
        """Test checkpoint file is created."""
        logger = ExecutionLogger(
            job_name="test_job",
            output_dir=temp_output_dir,
            enable_checkpoint_file=True
        )
        
        logger.checkpoint(
            stage="test",
            status="success",
            message="Test"
        )
        
        # Check that checkpoint file was created
        checkpoint_file = Path(temp_output_dir) / "test_job_checkpoints.json"
        assert checkpoint_file.exists()
    
    def test_execution_summary(self, temp_output_dir):
        """Test execution summary generation."""
        logger = ExecutionLogger(
            job_name="test_job",
            output_dir=temp_output_dir
        )
        
        logger.checkpoint("stage1", "start", "Starting stage 1")
        logger.checkpoint("stage1", "success", "Stage 1 complete")
        logger.checkpoint("stage2", "error", "Stage 2 failed")
        
        summary = logger.execution_summary()
        assert summary["total_checkpoints"] > 0
        assert summary["has_errors"] is True
        assert "stage1" in summary["stages_executed"]
        assert "stage2" in summary["stages_executed"]


class TestIntegrationWithLogger:
    """Integration tests combining rule resolution with logging."""
    
    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    def test_rule_resolution_with_logging(self, temp_output_dir):
        """Test rule resolution with execution logging."""
        logger = ExecutionLogger(
            job_name="dtlz2_eval",
            output_dir=temp_output_dir
        )
        
        job = JobDefinition(
            name="dtlz2_eval",
            command="python compute_dtlz2.py",
            rule="{{command}} {{payload[design_file]}} {{payload[output_dir]}} {{job_id}}",
            payload={
                "design_file": "{{input_design_params}}",
                "output_dir": "{{output_dir}}"
            }
        )
        
        context = {
            "input_design_params": "/data/design.params",
            "output_dir": "/tmp/stage_output",
            "job_id": 0
        }
        
        cmd = resolve_job_rule(job, context, logger)
        
        # Verify command was built correctly
        assert "python compute_dtlz2.py" in cmd
        assert "/data/design.params" in cmd
        assert "/tmp/stage_output" in cmd
        
        # Verify checkpoints were created
        rule_checkpoints = logger.get_checkpoint_by_stage("rule_resolution")
        assert len(rule_checkpoints) > 0
        assert any(cp.status == "success" for cp in rule_checkpoints)
    
    def test_full_job_execution_workflow(self, temp_output_dir):
        """Test complete job execution workflow with logging."""
        logger = create_job_logger(
            job_name="complete_test",
            output_dir=temp_output_dir,
            log_level="DEBUG"
        )
        
        job = JobDefinition(
            name="test_job",
            command="python script.py",
            rule="{command} {payload[input]} {payload[output]}",
            payload={
                "input": "{{input_design_params}}",
                "output": "{{output_dir}}/results.json"
            }
        )
        
        context = {
            "input_design_params": "/data/design.params",
            "output_dir": "/tmp/output"
        }
        
        # Validate payload
        is_valid, error = validate_job_payload(job, context=context, logger=logger)
        assert is_valid is True
        
        # Resolve rule
        cmd = resolve_job_rule(job, context, logger)
        assert "python script.py" in cmd
        
        # Check summary
        summary = logger.execution_summary()
        assert not summary["has_errors"]
        assert summary["status_breakdown"]["success"] > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
