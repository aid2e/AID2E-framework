"""Tests for ProblemConfigLoader and ProblemConfiguration."""

from pathlib import Path
import shutil
import yaml
import pytest

from configurations import ProblemConfigLoader, ProblemConfiguration


@pytest.fixture()
def tmp_design_file(tmp_path: Path) -> Path:
    """Copy the test design.params into a temp location for isolation."""
    src = Path(__file__).parent / "design.params"
    dst = tmp_path / "design.params"
    shutil.copy(src, dst)
    return dst


@pytest.fixture()
def tmp_problem_file(tmp_path: Path, tmp_design_file: Path) -> Path:
    """Create a problem.config in a temp dir with adjusted paths."""
    problem = {
        "problem": {
            "name": "DTLZ2 Multi-Objective Optimization",
            "type": "toy",
            "output_location": str(tmp_path / "output"),
            "work_location": str(tmp_path / "work"),
            "design_parameters_file": str(tmp_design_file.name),  # relative to file
            "objectives": [
                {"name": "f1", "minimize": True},
                {"name": "f2", "minimize": True},
            ],
        }
    }
    (tmp_path / "output").mkdir()
    (tmp_path / "work").mkdir()
    dst = tmp_path / "problem.config"
    with open(dst, "w", encoding="utf-8") as f:
        yaml.safe_dump(problem, f)
    return dst


def test_load_from_file_path(tmp_problem_file: Path):
    config = ProblemConfigLoader.load(str(tmp_problem_file))

    assert isinstance(config, ProblemConfiguration)
    assert config.name == "DTLZ2 Multi-Objective Optimization"
    assert len(config.objectives) == 2
    assert sorted([o.name for o in config.objectives]) == ["f1", "f2"]
    # design parameters come from copied design.params (10 variables)
    assert len(config.design_config.get_parameter_names()) == 10


def test_from_dict_with_inline_design(tmp_path: Path):
    # make directories to satisfy path validation
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    out_dir.mkdir()
    work_dir.mkdir()

    inline_design = {
        "design_space": {
            "design_parameters": {
                "group": {
                    "parameters": {
                        "p1": {"value": 0.1, "bounds": [0.0, 1.0]},
                        "p2": {"value": 1, "bounds": [0, 2]},
                    }
                }
            },
            "design_constraints": [
                {"name": "c1", "rule": "group.p1 + group.p2 < 3"}
            ],
        }
    }

    payload = {
        "name": "inline-problem",
        "type": "toy",
        "output_location": str(out_dir),
        "work_location": str(work_dir),
        "inline_design": inline_design,
        "objectives": [
            {"name": "loss", "minimize": True},
        ],
        "observations": [{"loss": 1.0}],
    }

    config = ProblemConfigLoader.from_dict(payload, base_dir=str(tmp_path))

    assert config.name == "inline-problem"
    assert len(config.objectives) == 1
    params = config.design_config.get_parameter_names()
    assert set(params) == {"group.p1", "group.p2"}
    assert config.observations == [{"loss": 1.0}]


def test_design_source_exclusivity_error(tmp_path: Path):
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    out_dir.mkdir()
    work_dir.mkdir()

    payload = {
        "name": "bad",
        "type": "toy",
        "output_location": str(out_dir),
        "work_location": str(work_dir),
        "design_parameters_file": "foo.params",
        "inline_design": {},
        "objectives": [{"name": "f", "minimize": True}],
    }

    with pytest.raises(ValueError):
        ProblemConfigLoader.from_dict(payload, base_dir=str(tmp_path))


def test_design_source_missing_error(tmp_path: Path):
    out_dir = tmp_path / "out"
    work_dir = tmp_path / "work"
    out_dir.mkdir()
    work_dir.mkdir()

    payload = {
        "name": "bad",
        "type": "toy",
        "output_location": str(out_dir),
        "work_location": str(work_dir),
        "objectives": [{"name": "f", "minimize": True}],
    }

    with pytest.raises(ValueError):
        ProblemConfigLoader.from_dict(payload, base_dir=str(tmp_path))
