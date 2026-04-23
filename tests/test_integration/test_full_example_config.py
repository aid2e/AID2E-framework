"""Integration test for canonical full-config loading."""

import yaml

from aid2e.utilities.configurations import FullConfig, load_config


def test_full_config_loads_via_fullconfig(tmp_path):
    """Ensure a canonical full config loads as FullConfig."""
    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    output_dir.mkdir()
    work_dir.mkdir()

    config_path = tmp_path / "full.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "problem": {
                    "name": "DTLZ2 Multi-Objective Optimization",
                    "problem_type": "toy",
                    "output_location": str(output_dir),
                    "work_location": str(work_dir),
                    "inline_design": {
                        "design_parameters": {
                            "DTLZ2_variables": {
                                "parameters": {
                                    "x1": {"value": 0.5, "bounds": [0.0, 1.0]},
                                    "x2": {"value": 0.5, "bounds": [0.0, 1.0]},
                                }
                            }
                        },
                        "parameter_constraints": [
                            {
                                "name": "simple_constraint",
                                "rule": "DTLZ2_variables.x1 < 1.0",
                            }
                        ],
                    },
                    "objectives": [
                        {"name": "f1", "direction": "minimize"},
                        {"name": "f2", "direction": "minimize"},
                    ],
                },
                "optimizer": {
                    "name": "MOBO",
                    "type": "Bayesian",
                    "parameters": {"n_iterations": 5, "n_initial_samples": 2},
                },
            }
        )
    )

    cfg = load_config(str(config_path))

    assert isinstance(cfg, FullConfig)
    assert cfg.problem.name == "DTLZ2 Multi-Objective Optimization"
    assert "DTLZ2_variables.x1" in cfg.problem.design_config.get_parameter_names()
    assert len(cfg.problem.objectives) == 2
    assert cfg.optimizer.name == "MOBO"
