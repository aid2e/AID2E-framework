"""Smoke tests for canonical full configurations built in-memory."""

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
