"""
Tests for Ax integration helpers.

This test suite verifies that the integration between AID2E configurations
and Ax Platform works correctly.
"""

import pytest
from aid2e.schedulers.ax_integration import (
    get_runner_from_config,
    convert_results_to_ax_format,
)
from aid2e.schedulers import JobLibRunner


class TestAxIntegration:
    """Test suite for Ax integration helpers."""

    def test_get_runner_joblib(self):
        """Test creating a JobLibRunner from configuration."""
        config = {
            "runner_type": "joblib",
            "runner_config": {
                "n_jobs": 4,
                "backend": "threading"
            }
        }
        
        runner = get_runner_from_config(config)
        
        assert isinstance(runner, JobLibRunner)
        assert runner.n_jobs == 4
        assert runner.backend == "threading"

    def test_get_runner_default(self):
        """Test creating a runner with default configuration."""
        config = {"runner_type": "joblib"}
        
        runner = get_runner_from_config(config)
        
        assert isinstance(runner, JobLibRunner)
        assert runner.n_jobs == -1  # Default
        assert runner.backend == "loky"  # Default

    def test_get_runner_unsupported(self):
        """Test that unsupported runner types raise an error."""
        config = {"runner_type": "unsupported"}
        
        with pytest.raises(ValueError, match="Unsupported runner type"):
            get_runner_from_config(config)

    def test_get_runner_slurm_not_implemented(self):
        """Test that SLURM runner raises NotImplementedError (Phase 2)."""
        config = {"runner_type": "slurm"}
        
        with pytest.raises(NotImplementedError, match="Phase 2"):
            get_runner_from_config(config)

    def test_get_runner_pandaidds_not_implemented(self):
        """Test that PanDA runner raises NotImplementedError (Phase 2)."""
        config = {"runner_type": "pandaidds"}
        
        with pytest.raises(NotImplementedError, match="Phase 2"):
            get_runner_from_config(config)

    def test_convert_results_to_ax_format(self):
        """Test converting results to Ax format."""
        results = {
            "objective1": 0.5,
            "objective2": 1.2,
            "metadata": "some_string"  # Should be ignored
        }
        
        ax_results = convert_results_to_ax_format(results)
        
        assert ax_results["objective1"] == (0.5, 0.0)
        assert ax_results["objective2"] == (1.2, 0.0)
        assert "metadata" not in ax_results

    def test_convert_results_empty(self):
        """Test converting empty results."""
        results = {}
        ax_results = convert_results_to_ax_format(results)
        assert ax_results == {}

    def test_convert_results_with_integers(self):
        """Test that integer results are converted to floats."""
        results = {"objective": 42}
        ax_results = convert_results_to_ax_format(results)
        assert ax_results["objective"] == (42.0, 0.0)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
