"""Integration test loading the examples/basic full_example.yml via FullConfig."""

from pathlib import Path
import shutil
import yaml

from aid2e.utilities.configurations import FullConfig, load_config


def test_full_example_yaml_loads_via_fullconfig(tmp_path):
    """Ensure the sample full_example.yml can be normalized and loaded as FullConfig."""
    example_dir = Path("examples/basic")
    source_config = example_dir / "full_example.yml"
    source_design = example_dir / "design.params"

    # Copy fixtures into an isolated temp dir
    config_path = tmp_path / "full_example.yml"
    design_path = tmp_path / "design.params"
    shutil.copyfile(source_config, config_path)
    shutil.copyfile(source_design, design_path)

    data = yaml.safe_load(config_path.read_text())

    output_dir = tmp_path / "output"
    work_dir = tmp_path / "work"
    output_dir.mkdir()
    work_dir.mkdir()

    data["problem"]["output_location"] = str(output_dir)
    data["problem"]["work_location"] = str(work_dir)
    data["problem"].setdefault("design_space", {})["path"] = str(design_path)

    config_path.write_text(yaml.safe_dump(data))

    cfg = load_config(str(config_path))

    assert isinstance(cfg, FullConfig)
    assert cfg.problem.name == "DTLZ2 Multi-Objective Optimization"
    assert "DTLZ2_variables.x1" in cfg.problem.design_config.get_parameter_names()
    assert len(cfg.optimization.objectives) == len(data["problem"]["objectives"])
    assert cfg.optimization.optimizer.name == data.get("optimizer", {}).get("kind", "")
