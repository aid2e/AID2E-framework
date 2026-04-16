"""Tests for the canonical optimizer config registry."""

from __future__ import annotations

import sys
from importlib import import_module

import pytest
from pydantic import BaseModel

from aid2e.utilities.configurations.optimization_registry import (
    get,
    list_registered,
    register,
)
from aid2e.utilities.configurations.optimizer_config import OptimizerConfiguration


@pytest.fixture
def clean_optimizer_registry(monkeypatch):
    """Reset registry state so lazy loading behavior is exercised explicitly."""
    registry_module = import_module("aid2e.utilities.configurations.optimization_registry")
    monkeypatch.setattr(registry_module, "_algorithm_configs", {})

    for module_name in [
        "aid2e.optimizers",
        "aid2e.optimizers.ax",
        "aid2e.optimizers.ax.config",
        "aid2e.optimizers.ax.optimizer",
        "aid2e.optimizers.pymoo",
        "aid2e.optimizers.pymoo.config",
        "aid2e.optimizers.pymoo.optimizer",
    ]:
        sys.modules.pop(module_name, None)

    return registry_module


def test_get_lazily_loads_ax_config(clean_optimizer_registry) -> None:
    model = get("ax")

    assert model is not None
    assert model.__name__ == "AxOptimizerConfig"


def test_get_lazily_loads_pymoo_config(clean_optimizer_registry) -> None:
    model = get("pymoo")

    assert model is not None
    assert model.__name__ == "PyMOOOptimizerConfig"


def test_parse_algorithm_params_returns_ax_model(clean_optimizer_registry) -> None:
    config = OptimizerConfiguration(
        name="ax",
        type="Bayesian",
        parameters={
            "generator": "BOTORCH_MODULAR",
            "n_iterations": 5,
            "batch_size": 2,
        },
    )

    parsed = config.parse_algorithm_params()

    assert parsed is not None
    assert parsed.__class__.__name__ == "AxOptimizerConfig"
    assert parsed.n_iterations == 5
    assert parsed.batch_size == 2


def test_parse_algorithm_params_returns_pymoo_model(clean_optimizer_registry) -> None:
    config = OptimizerConfiguration(
        name="pymoo",
        type="evolutionary",
        parameters={
            "pop_size": 16,
            "n_offsprings": 8,
            "n_iterations": 5,
        },
    )

    parsed = config.parse_algorithm_params()

    assert parsed is not None
    assert parsed.__class__.__name__ == "PyMOOOptimizerConfig"
    assert parsed.pop_size == 16
    assert parsed.n_offsprings == 8


def test_list_registered_includes_builtin_backends(clean_optimizer_registry) -> None:
    registered = list_registered()

    assert "ax" in registered
    assert "pymoo" in registered
    assert registered["ax"].__name__ == "AxOptimizerConfig"
    assert registered["pymoo"].__name__ == "PyMOOOptimizerConfig"


def test_register_rejects_duplicate_names(clean_optimizer_registry) -> None:
    class FirstConfig(BaseModel):
        pass

    class SecondConfig(BaseModel):
        pass

    register("custom", FirstConfig)

    with pytest.raises(ValueError, match="already registered"):
        register("custom", SecondConfig)
