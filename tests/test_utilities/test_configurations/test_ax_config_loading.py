"""Tests for Ax optimizer configuration parsing and validation."""

import pytest

from aid2e.optimizers.ax import AxOptimizerConfig
from aid2e.utilities.configurations.optimizer_config import OptimizerConfiguration


class TestAxConfigurationLoading:
    """Tests for loading AxOptimizerConfig from dict and YAML-shaped payloads."""

    def test_load_ax_config_from_dict(self):
        """Test loading AxOptimizerConfig from a dictionary."""
        config_dict = {
            "initialization_strategy": "sobol",
            "generator": "BOTORCH_MODULAR",
            "generator_kwargs": {
                "botorch_acqf_class": "qLogNoisyExpectedHypervolumeImprovement",
            },
            "generator_gen_kwargs": {
                "model_gen_options": {"optimizer_kwargs": {"sequential": False}}
            },
            "objective_thresholds": {"f1": 1.0, "f2": 1.0},
            "n_initial_samples": 10,
            "n_iterations": 50,
            "batch_size": 5,
            "seed": 42,
        }

        config = AxOptimizerConfig(**config_dict)

        assert config.initialization_strategy == "sobol"
        assert config.generator == "BOTORCH_MODULAR"
        assert config.generator_kwargs["botorch_acqf_class"] == (
            "qLogNoisyExpectedHypervolumeImprovement"
        )
        assert config.generator_gen_kwargs["model_gen_options"]["optimizer_kwargs"][
            "sequential"
        ] is False
        assert config.objective_thresholds == {"f1": 1.0, "f2": 1.0}
        assert config.n_initial_samples == 10
        assert config.n_iterations == 50
        assert config.batch_size == 5
        assert config.seed == 42

    def test_load_optimizer_config_with_ax(self):
        """Test loading OptimizerConfiguration with Ax optimizer payload."""
        config = OptimizerConfiguration(
            name="ax",
            type="Bayesian",
            parameters={
                "initialization_strategy": "sobol",
                "generator": "BOTORCH_MODULAR",
                "n_initial_samples": 10,
                "n_iterations": 50,
                "batch_size": 5,
                "seed": 42,
            },
        )

        assert config.name == "ax"
        assert config.parameters["generator"] == "BOTORCH_MODULAR"


class TestAxConfigurationDefaults:
    """Tests for Ax configuration defaults."""

    def test_sobol_is_default_initialization(self):
        """Test that Sobol is the default initialization strategy."""
        config = AxOptimizerConfig()
        assert config.initialization_strategy == "sobol"

    def test_mbm_is_default_generator(self):
        """Test that Modular BoTorch is the default generator."""
        config = AxOptimizerConfig()
        assert config.generator == "BOTORCH_MODULAR"

    def test_default_generator_kwargs_are_empty(self):
        """Test that generator kwargs default to an empty mapping."""
        config = AxOptimizerConfig()
        assert config.generator_kwargs == {}
        assert config.generator_gen_kwargs == {}

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

    def test_legacy_fields_are_rejected(self):
        """Test that retired Ax config fields fail fast."""
        with pytest.raises(ValueError, match="legacy fields"):
            AxOptimizerConfig(
                surrogate_model="saasbo",
                acquisition_function="qnehvi",
            )

    def test_invalid_generator_is_rejected(self):
        """Test that unsupported Ax generators fail validation."""
        with pytest.raises(ValueError, match="Unsupported Ax generator"):
            AxOptimizerConfig(generator="SAASBO")


class TestAxConfigurationDocumentation:
    """Tests verifying proper field descriptions for Ax configuration."""

    def test_ax_config_has_docstring(self):
        """Test that AxOptimizerConfig has a docstring."""
        assert AxOptimizerConfig.__doc__ is not None
        assert len(AxOptimizerConfig.__doc__) > 0

    def test_ax_config_field_descriptions(self):
        """Test that AxOptimizerConfig fields have descriptions."""
        model_fields = AxOptimizerConfig.model_fields

        assert "initialization_strategy" in model_fields
        assert "generator" in model_fields
        assert "generator_kwargs" in model_fields

        assert model_fields["initialization_strategy"].description
        assert model_fields["generator"].description
        assert model_fields["generator_kwargs"].description


class TestAxConfigurationExamples:
    """Example-driven tests for the supported config surface."""

    def test_batch_configuration_round_trips(self):
        """Test various batch configurations for the MBM-first config."""
        batch_sizes = [1, 5, 10, 20]

        for batch_size in batch_sizes:
            config = AxOptimizerConfig(
                initialization_strategy="sobol",
                generator="BOTORCH_MODULAR",
                batch_size=batch_size,
            )
            assert config.batch_size == batch_size

    def test_generator_kwargs_preserve_yaml_friendly_strings(self):
        """Test that config preserves raw string symbols until runtime resolution."""
        config = AxOptimizerConfig(
            generator_kwargs={
                "botorch_acqf_class": "qLogNoisyExpectedImprovement",
                "surrogate_spec": {
                    "model_configs": [{"botorch_model_class": "SingleTaskGP"}]
                },
            }
        )
        assert config.generator_kwargs["botorch_acqf_class"] == (
            "qLogNoisyExpectedImprovement"
        )
        assert config.generator_kwargs["surrogate_spec"]["model_configs"][0][
            "botorch_model_class"
        ] == "SingleTaskGP"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
