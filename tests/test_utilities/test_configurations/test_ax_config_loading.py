"""Tests for loading Ax optimizer configuration.

Tests cover configuration parsing, validation, and registration
for the Ax-based optimizer with Sobol initialization, SAASBO surrogate model,
and qNEHVI acquisition function.
"""

import pytest
# Import from the new optimizers.ax location
from aid2e.optimizers.ax import AxOptimizerConfig
from aid2e.utilities.configurations.optimization_registry import (
    get_algorithm_config_model,
    register_algorithm_config,
)
from aid2e.utilities.configurations.optimization_config import OptimizationConfiguration, OptimizerConfig


class TestAxConfigurationLoading:
    """Tests for loading Ax optimizer configuration."""
    
    def test_load_ax_config_from_dict(self):
        """Test loading AxOptimizerConfig from a dictionary."""
        config_dict = {
            "initialization_strategy": "sobol",
            "surrogate_model": "saasbo",
            "acquisition_function": "qnehvi",
            "n_initial_samples": 10,
            "n_iterations": 50,
            "batch_size": 5,
            "seed": 42,
        }
        
        config = AxOptimizerConfig(**config_dict)
        
        assert config.initialization_strategy == "sobol"
        assert config.surrogate_model == "saasbo"
        assert config.acquisition_function == "qnehvi"
        assert config.n_initial_samples == 10
        assert config.n_iterations == 50
        assert config.batch_size == 5
        assert config.seed == 42
    
    def test_load_optimization_config_with_ax(self):
        """Test loading OptimizationConfiguration with Ax optimizer."""
        config = OptimizationConfiguration(
            name="test_ax_optimization",
            description="Test Ax optimizer configuration",
            optimizer=OptimizerConfig(
                name="ax",
                type="Bayesian",
                parameters={
                    "initialization_strategy": "sobol",
                    "surrogate_model": "saasbo",
                    "acquisition_function": "qnehvi",
                    "n_initial_samples": 10,
                    "n_iterations": 50,
                    "batch_size": 5,
                    "seed": 42,
                }
            ),
            objectives=["minimize:f1", "maximize:f2"],
            n_iterations=50,
            n_initial_samples=10,
        )
        
        assert config.optimizer.name == "ax"
        assert config.optimizer.parameters["surrogate_model"] == "saasbo"
    


class TestAxConfigurationDefaults:
    """Tests for Ax configuration defaults."""
    
    def test_sobol_is_default_initialization(self):
        """Test that Sobol is the default initialization strategy."""
        config = AxOptimizerConfig()
        
        assert config.initialization_strategy == "sobol"
    
    def test_saasbo_is_default_surrogate_model(self):
        """Test that SAASBO is the default surrogate model."""
        config = AxOptimizerConfig()
        
        assert config.surrogate_model == "saasbo"
    
    def test_qnehvi_is_default_acquisition(self):
        """Test that qNEHVI is the default acquisition function."""
        config = AxOptimizerConfig()
        
        assert config.acquisition_function == "qnehvi"
    
    def test_reasonable_default_iterations(self):
        """Test that default iterations are reasonable."""
        config = AxOptimizerConfig()
        
        assert config.n_iterations >= 10
        assert config.n_iterations <= 1000
    
    def test_reasonable_default_initial_samples(self):
        """Test that default initial samples are reasonable."""
        config = AxOptimizerConfig()
        
        assert config.n_initial_samples >= 1
        assert config.n_initial_samples <= 100


class TestAxConfigurationValidation:
    """Tests for Ax configuration validation."""
    
    def test_positive_n_initial_samples_required(self):
        """Test that n_initial_samples must be positive."""
        with pytest.raises(ValueError):
            AxOptimizerConfig(n_initial_samples=0)
        
        with pytest.raises(ValueError):
            AxOptimizerConfig(n_initial_samples=-1)
    
    def test_positive_n_iterations_required(self):
        """Test that n_iterations must be positive."""
        with pytest.raises(ValueError):
            AxOptimizerConfig(n_iterations=0)
        
        with pytest.raises(ValueError):
            AxOptimizerConfig(n_iterations=-5)
    
    def test_positive_batch_size_required(self):
        """Test that batch_size must be positive."""
        with pytest.raises(ValueError):
            AxOptimizerConfig(batch_size=0)
        
        with pytest.raises(ValueError):
            AxOptimizerConfig(batch_size=-1)
    
    def test_none_seed_allowed(self):
        """Test that seed can be None for non-deterministic results."""
        config = AxOptimizerConfig(seed=None)
        
        assert config.seed is None
    
    def test_integer_seed_allowed(self):
        """Test that seed can be an integer."""
        config = AxOptimizerConfig(seed=42)
        
        assert config.seed == 42
        assert isinstance(config.seed, int)


class TestAxConfigurationDocumentation:
    """Tests verifying proper docstrings for Ax configuration."""
    
    def test_ax_config_has_docstring(self):
        """Test that AxOptimizerConfig has a docstring."""
        assert AxOptimizerConfig.__doc__ is not None
        assert len(AxOptimizerConfig.__doc__) > 0
    
    def test_ax_config_field_descriptions(self):
        """Test that AxOptimizerConfig fields have descriptions."""
        model_fields = AxOptimizerConfig.model_fields
        
        # Check that key fields have descriptions
        assert "initialization_strategy" in model_fields
        assert "surrogate_model" in model_fields
        assert "acquisition_function" in model_fields
        
        # Field info should have description
        assert model_fields["initialization_strategy"].description
        assert model_fields["surrogate_model"].description
        assert model_fields["acquisition_function"].description


class TestSobolSaasboQnehviIntegration:
    """Integration tests for Sobol + SAASBO + qNEHVI combination."""
    
    def test_sobol_saasbo_qnehvi_with_various_seed_values(self):
        """Test Sobol + SAASBO + qNEHVI with different seed values."""
        seeds = [None, 0, 42, 12345, 999999]
        
        for seed in seeds:
            config = AxOptimizerConfig(
                initialization_strategy="sobol",
                surrogate_model="saasbo",
                acquisition_function="qnehvi",
                seed=seed,
            )
            
            assert config.seed == seed
    
    def test_sobol_saasbo_qnehvi_with_batch_configurations(self):
        """Test various batch configurations for Sobol + SAASBO + qNEHVI."""
        batch_sizes = [1, 5, 10, 20]
        
        for batch_size in batch_sizes:
            config = AxOptimizerConfig(
                initialization_strategy="sobol",
                surrogate_model="saasbo",
                acquisition_function="qnehvi",
                batch_size=batch_size,
            )
            
            assert config.batch_size == batch_size


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
