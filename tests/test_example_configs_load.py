"""Smoke tests for canonical full configurations built in-memory."""

from pathlib import Path
import py_compile

import yaml

from aid2e.utilities.configurations import load_config


def test_canonical_full_config_loads(tmp_path):
    """Canonical full configs should load and preserve objective directions."""
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    output_dir.mkdir()
    work_dir.mkdir()

    cfg_path = tmp_path / "full.yml"
    cfg_path.write_text(
        yaml.safe_dump(
            {
                "problem": {
                    "name": "Smoke Problem",
                    "problem_type": "toy",
                    "output_location": str(output_dir),
                    "work_location": str(work_dir),
                    "inline_design": {
                        "design_parameters": {
                            "group": {
                                "parameters": {
                                    "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                                    "label": {
                                        "value": "a",
                                        "choices": ["a", "b"],
                                    },
                                }
                            }
                        },
                        "parameter_constraints": [
                            {"name": "bound", "rule": "group.x <= 1.0"}
                        ],
                    },
                    "objectives": [
                        {"name": "f1", "direction": "minimize"},
                        {"name": "f2", "direction": "maximize"},
                    ],
                },
                "optimizer": {
                    "name": "MOBO",
                    "type": "Bayesian",
                    "parameters": {"n_iterations": 3},
                },
            }
        )
    )

    config = load_config(str(cfg_path))
    assert config.problem.objectives
    assert [obj.to_directive() for obj in config.problem.objectives] == [
        "minimize:f1",
        "maximize:f2",
    ]


def test_optimizer_only_example_configs_load() -> None:
    """New optimizer-only example YAMLs should load as canonical full configs."""
    example_paths = [
        Path("examples/optimizers/dtlz2_ax_optimizer_only.yml"),
        Path("examples/optimizers/dtlz2_pymoo_optimizer_only.yml"),
    ]

    for cfg_path in example_paths:
        config = load_config(str(cfg_path))
        assert config.problem.problem_type == "toy"
        assert config.problem.design_config.get_parameter_names()
        assert config.optimizer.parameters


def test_optimizer_only_example_scripts_compile() -> None:
    """New optimizer-only example scripts should compile cleanly."""
    script_paths = [
        Path("examples/optimizers/run_ax_optimizer_only_example.py"),
        Path("examples/optimizers/run_pymoo_optimizer_only_example.py"),
    ]

    for script_path in script_paths:
        py_compile.compile(str(script_path), doraise=True)
