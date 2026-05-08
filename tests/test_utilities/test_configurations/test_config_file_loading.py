"""Tests for canonical configuration loaders using DTLZ2-style fixtures."""

from pathlib import Path

import pytest
import yaml

from aid2e.utilities.configurations import (
    DesignConfigLoader,
    ProblemConfigLoader,
    load_config,
    StackRegistry,
)
from aid2e.utilities.epic_utils import EpicEnvConfig


def _fixture_dir() -> Path:
    """Return the path to the DTLZ2 fixtures directory."""
    return Path(__file__).resolve().parent.parent / "fixtures" / "dtlz2"


def test_design_config_loader_with_fixture():
    """Load canonical design.params fixture and validate parameters and constraints."""
    design_path = _fixture_dir() / "design.params"

    config = DesignConfigLoader.load(str(design_path))

    names = config.get_parameter_names()
    assert "DTLZ2_variables.x1" in names
    assert len(names) == 10

    is_valid, failures = config.check_constraints({"DTLZ2_variables.x1": 0.5})
    assert is_valid
    assert failures == []


def test_problem_config_loader_with_fixture(tmp_path):
    """Load canonical problem fixture and ensure relative design file resolution."""
    fixture_dir = _fixture_dir()
    design_dst = tmp_path / "design.params"
    design_dst.write_text((fixture_dir / "design.params").read_text())

    problem_data = yaml.safe_load((fixture_dir / "problem.config").read_text())
    output_dir = tmp_path / "output" / "dtlz2"
    work_dir = tmp_path / "work" / "dtlz2"
    output_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)

    problem_data["problem"]["output_location"] = str(output_dir)
    problem_data["problem"]["work_location"] = str(work_dir)
    problem_data["problem"]["design_parameters_file"] = "design.params"

    problem_path = tmp_path / "problem.config"
    problem_path.write_text(yaml.safe_dump(problem_data))

    config = ProblemConfigLoader.load(str(problem_path))

    assert config.name == "DTLZ2 Multi-Objective Optimization"
    assert config.problem_type == "toy"
    assert "DTLZ2_variables.x1" in config.design_config.get_parameter_names()
    assert [obj.to_directive() for obj in config.objectives] == [
        "minimize:f1",
        "minimize:f2",
    ]


def test_full_config_loader_combines_problem_optimizer_scheduler_and_workflows(tmp_path):
    """Load a canonical FullConfig with inline design and workflow wrapper."""
def test_problem_config_loader_stack_registry(tmp_path):
    """Load problem config with stack_configurations and registry deserialization."""
    fixture_dir = _fixture_dir()
    design_dst = tmp_path / "design.params"
    design_dst.write_text((fixture_dir / "design.params").read_text())

    output_dir = tmp_path / "output" / "dtlz2"
    work_dir = tmp_path / "work" / "dtlz2"
    output_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)

    # minimal problem config inlined
    design_data = yaml.safe_load((fixture_dir / "design.params").read_text())
    problem_payload = {
        "problem": {
            "name": "DTLZ2 Multi-Objective Optimization",
            "problem_type": "toy",
            "output_location": str(output_dir),
            "work_location": str(work_dir),
            "inline_design": {
                "design_parameters": design_data["design_space"]["design_parameters"],
                "parameter_constraints": design_data["design_space"].get("design_constraints", []),
            },
            "objectives": [
                {"name": "f1", "direction": "minimize"},
                {"name": "f2", "direction": "minimize"},
            ],
            "epic_environment": {
                "singularity_image": "/home/eic/local/lib/eic_xl-nightly.sif",
                "epic_install": "/home/eic/epic",
                "epic_config": "epic_full",
            }
        }
    }

    # Write and load as YAML
    config_path = tmp_path / "test.config.yml"
    config_path.write_text(yaml.safe_dump(problem_payload))

    problem_config = ProblemConfigLoader.load(str(config_path))
    assert isinstance(problem_config.environment_config, EpicEnvConfig)
    assert problem_config.environment_config.epic_install == "/home/eic/epic"


def test_full_config_loader_combines_problem_and_optimization(tmp_path):
    """Load FullConfig from combined problem and optimization payload."""
    fixture_dir = _fixture_dir()
    design_file_data = yaml.safe_load((fixture_dir / "design.params").read_text())
    design_space = design_file_data["design_space"]

    output_dir = tmp_path / "output" / "dtlz2"
    work_dir = tmp_path / "work" / "dtlz2"
    output_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)

    full_payload = {
        "problem": {
            "name": "DTLZ2 Multi-Objective Optimization",
            "problem_type": "toy",
            "output_location": str(output_dir),
            "work_location": str(work_dir),
            "inline_design": {
                "design_parameters": design_space["design_parameters"],
                "parameter_constraints": design_space["parameter_constraints"],
            },
            "objectives": [
                {"name": "f1", "direction": "minimize"},
                {"name": "f2", "direction": "minimize"},
            ],
        },
        "optimizer": {
            "name": "MOBO",
            "type": "Bayesian",
            "parameters": {
                "n_iterations": 5,
                "n_initial_samples": 2,
                "batch_size": 1,
            },
        },
        "scheduler": {
            "runner_type": "JobLibRunner",
            "parameters": {"n_jobs": 2},
        },
        "workflows": {
            "workflows": [
                {
                    "name": "main",
                    "objectives": [{"name": "f1", "direction": "minimize"}],
                    "stages": [],
                }
            ]
        },
    }

    full_config_path = tmp_path / "full.config"
    full_config_path.write_text(yaml.safe_dump(full_payload))

    config = load_config(str(full_config_path))

    assert config.problem.name == "DTLZ2 Multi-Objective Optimization"
    assert config.problem.design_config.get_parameter_bounds("DTLZ2_variables.x1") == (
        0.0,
        1.0,
    )
    assert config.optimizer.name == "MOBO"
    assert config.optimizer.parameters["n_iterations"] == 5
    assert config.scheduler.parameters["n_jobs"] == 2
    assert config.workflows.workflows[0].name == "main"


def test_design_loader_rejects_legacy_design_constraints(tmp_path):
    """Legacy design_constraints keys should fail fast."""
    config_path = tmp_path / "legacy_design.params"
    config_path.write_text(
        yaml.safe_dump(
            {
                "design_space": {
                    "design_parameters": {
                        "group": {
                            "parameters": {
                                "x": {"value": 0.5, "bounds": [0.0, 1.0]}
                            }
                        }
                    },
                    "design_constraints": [{"name": "c1", "rule": "group.x < 1.0"}],
                }
            }
        )
    )

    with pytest.raises(ValueError, match="design_constraints"):
        DesignConfigLoader.load(str(config_path))


def test_problem_loader_rejects_legacy_problem_type_and_minimize_keys(tmp_path):
    """Legacy type/minimize keys should fail fast."""
    design_path = tmp_path / "design.params"
    design_path.write_text((_fixture_dir() / "design.params").read_text())

    problem_path = tmp_path / "problem.config"
    problem_path.write_text(
        yaml.safe_dump(
            {
                "problem": {
                    "name": "Legacy Problem",
                    "type": "toy",
                    "output_location": str(tmp_path / "output"),
                    "work_location": str(tmp_path / "work"),
                    "design_parameters_file": "design.params",
                    "objectives": [{"name": "f1", "minimize": True}],
                }
            }
        )
    )
    (tmp_path / "output").mkdir()
    (tmp_path / "work").mkdir()

    with pytest.raises(ValueError, match="problem_type"):
        ProblemConfigLoader.load(str(problem_path))


def test_full_config_rejects_legacy_scheduler_shape(tmp_path):
    """Nested scheduler runner blocks should be rejected."""
    config_path = tmp_path / "full.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "problem": {
                    "name": "Strict Problem",
                    "problem_type": "toy",
                    "output_location": str(tmp_path / "output"),
                    "work_location": str(tmp_path / "work"),
                    "inline_design": {
                        "design_parameters": {
                            "group": {
                                "parameters": {
                                    "x": {"value": 0.5, "bounds": [0.0, 1.0]}
                                }
                            }
                        }
                    },
                    "objectives": [{"name": "f1", "direction": "minimize"}],
                },
                "optimizer": {
                    "name": "MOBO",
                    "type": "Bayesian",
                    "parameters": {"n_iterations": 2},
                },
                "scheduler": {
                    "runner_type": "JobLibRunner",
                    "joblib": {"n_jobs": 2},
                },
            }
        )
    )
    (tmp_path / "output").mkdir()
    (tmp_path / "work").mkdir()

    with pytest.raises(ValueError, match="Extra inputs are not permitted|joblib"):
        load_config(str(config_path))


def test_full_config_rejects_legacy_workflow_shape(tmp_path):
    """Legacy top-level workflow should be rejected."""
    config_path = tmp_path / "full.yml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "problem": {
                    "name": "Strict Problem",
                    "problem_type": "toy",
                    "output_location": str(tmp_path / "output"),
                    "work_location": str(tmp_path / "work"),
                    "inline_design": {
                        "design_parameters": {
                            "group": {
                                "parameters": {
                                    "x": {"value": 0.5, "bounds": [0.0, 1.0]}
                                }
                            }
                        }
                    },
                    "objectives": [{"name": "f1", "direction": "minimize"}],
                },
                "optimizer": {
                    "name": "MOBO",
                    "type": "Bayesian",
                    "parameters": {"n_iterations": 2},
                },
                "workflow": {
                    "name": "legacy",
                    "objectives": [{"name": "f1", "direction": "minimize"}],
                },
            }
        )
    )
    (tmp_path / "output").mkdir()
    (tmp_path / "work").mkdir()

    with pytest.raises(ValueError, match="workflow"):
        load_config(str(config_path))
