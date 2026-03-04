"""Smoke tests for example configuration files.

Ensures shipped example YAML configs load via `load_config` and that objectives
are parsed with names and directions, covering script/inline/multi-steps cases.
"""

from pathlib import Path
import pytest

from aid2e.utilities.configurations import load_config


EXAMPLE_REL_PATHS = [
    "examples/basic/full_example.yml",
    "examples/basic/full_example_joblib.yml",
    "examples/basic/full_example_slurm.yml",
    "examples/basic/full_example_panda.yml",
]


def _resolve_example_path(rel_path: str) -> Path:
    """Resolve an example path relative to repository root."""
    return Path(__file__).resolve().parents[1] / rel_path


@pytest.mark.parametrize("rel_path", EXAMPLE_REL_PATHS)
def test_example_configs_load(rel_path: str) -> None:
    """Examples should load and yield objectives with names and directions."""
    cfg_path = _resolve_example_path(rel_path)
    assert cfg_path.exists(), f"Example config missing: {cfg_path}"

    config = load_config(str(cfg_path))
    assert config.problem.objectives, "Objectives should not be empty"

    for obj in config.problem.objectives:
        assert getattr(obj, "name", None), "Objective must have a name"
        assert getattr(obj, "direction", None), "Objective must have a direction"
