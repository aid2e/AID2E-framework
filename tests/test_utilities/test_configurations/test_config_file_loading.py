"""Tests for configuration loaders using DTLZ2 fixture files."""

from pathlib import Path

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
    """Load design.params fixture and validate parameters and constraints."""
    design_path = _fixture_dir() / "design.params"

    config = DesignConfigLoader.load(str(design_path))

    names = config.get_parameter_names()
    assert "DTLZ2_variables.x1" in names
    assert len(names) == 10

    is_valid, failures = config.check_constraints({"DTLZ2_variables.x1": 0.5})
    assert is_valid
    assert failures == []


def test_problem_config_loader_with_fixture(tmp_path):
    """Load problem.config fixture and ensure relative design file resolution."""
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
    assert len(config.objectives) == 2


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
            "type": "toy",
            "output_location": str(output_dir),
            "work_location": str(work_dir),
            "inline_design": {
                "design_parameters": design_data["design_space"]["design_parameters"],
                "parameter_constraints": design_data["design_space"].get("design_constraints", []),
            },
            "objectives": [
                {"name": "f1", "minimize": True},
                {"name": "f2", "minimize": True},
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

    # legacy epic_configuration still works and is also mirrored
    problem_payload["problem"]["epic_configuration"] = {
        "singularity_image": "/path/to/eic-shell.sif",
        "epic_install": "/opt/epic/legacy",
        "epic_config": "epic",
    }
    config_path.write_text(yaml.safe_dump(problem_payload))
    problem_config2 = ProblemConfigLoader.load(str(config_path))
    assert problem_config2.epic_configuration is not None
    assert problem_config2.epic_configuration.epic_install == "/opt/epic/legacy"


def test_full_config_loader_combines_problem_and_optimization(tmp_path):
    """Load FullConfig from combined problem and optimization payload."""
    fixture_dir = _fixture_dir()
    design_dst = tmp_path / "design.params"
    design_dst.write_text((fixture_dir / "design.params").read_text())

    output_dir = tmp_path / "output" / "dtlz2"
    work_dir = tmp_path / "work" / "dtlz2"
    output_dir.mkdir(parents=True)
    work_dir.mkdir(parents=True)

    problem_file_data = yaml.safe_load((fixture_dir / "problem.config").read_text())
    design_file_data = yaml.safe_load((fixture_dir / "design.params").read_text())

    design_space = design_file_data.get("design_space", {})
    design_parameters = design_space.get("design_parameters", {})
    parameter_constraints = design_space.get("design_constraints", [])

    problem_payload = {
        "name": problem_file_data["problem"]["name"],
        "problem_type": problem_file_data["problem"]["type"],
        "output_location": str(output_dir),
        "work_location": str(work_dir),
        "inline_design": {
            "design_parameters": design_parameters,
            "parameter_constraints": parameter_constraints,
        },
        "objectives": problem_file_data["problem"]["objectives"],
    }

    full_payload = {
        "problem": problem_payload,
        "optimization": {
            "name": "dtlz2-optimization",
            "description": "Test optimization payload",
            "optimizer": {"name": "MOBO", "type": "Bayesian", "parameters": {}},
            "objectives": ["minimize:f1", "minimize:f2"],
            "constraints": [],
            "n_iterations": 5,
            "n_initial_samples": 2,
            "parallel_evaluations": 1,
        },
    }

    full_config_path = tmp_path / "full.config"
    full_config_path.write_text(yaml.safe_dump(full_payload))

    config = load_config(str(full_config_path))

    assert config.problem.name == "DTLZ2 Multi-Objective Optimization"
    assert config.problem.design_config.get_parameter_bounds("DTLZ2_variables.x1") == (0.0, 1.0)
    assert config.optimization.optimizer.name == "MOBO"
    # Objectives are now ObjectiveDefinition instances, check their directives
    assert len(config.optimization.objectives) == 2
    assert [obj.to_directive() for obj in config.optimization.objectives] == ["minimize:f1", "minimize:f2"]
