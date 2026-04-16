"""Tests for epic design configuration utilities."""

import yaml

from aid2e.utilities.epic_utils.epic_design_config import (
    EpicDesignConfig,
    EpicDesignConfigLoader,
)


def _sample_epic_design_payload() -> dict:
    """Build a minimal epic design configuration payload for tests."""
    return {
        "epic_design_parameters": {
            "tracker": {
                "file_path": "$DETECTOR_PATH/tracker.xml",
                "parameters": {
                    "thickness": {
                        "value": 0.2,
                        "bounds": (0.1, 0.3),
                        "xml_path": "//constant[@name='tracker_thickness']",
                        "attribute": "value",
                        "unit": "cm",
                    }
                },
            }
        },
        "optimization_groups": {"default": ["tracker.thickness"]},
    }


def test_epic_design_config_getters(monkeypatch):
    """Validate key EpicDesignConfig getters and XML mapping helpers."""
    monkeypatch.setenv("DETECTOR_PATH", "/detector")
    config = EpicDesignConfig(**_sample_epic_design_payload())

    flat_params = config.get_flat_parameters()
    assert "tracker.thickness" in flat_params
    assert config.get_parameter_bounds("tracker.thickness") == (0.1, 0.3)

    modifications = config.get_xml_modifications({"tracker.thickness": 0.25})
    assert "/detector/tracker.xml" in modifications
    xml_path, attribute, unit, new_value = modifications["/detector/tracker.xml"][0]
    assert xml_path == "//constant[@name='tracker_thickness']"
    assert unit == "cm"
    assert new_value == 0.25

    file_paths = config.get_file_paths()
    assert "/detector/tracker.xml" in file_paths


def test_epic_design_config_loader(tmp_path, monkeypatch):
    """Load epic design config from YAML and ensure structure is preserved."""
    monkeypatch.setenv("DETECTOR_PATH", "/detector")
    config_path = tmp_path / "epic_design.params"
    config_path.write_text(yaml.safe_dump(_sample_epic_design_payload()))

    config = EpicDesignConfigLoader.load(str(config_path))

    assert isinstance(config, EpicDesignConfig)
    assert "tracker.thickness" in config.get_parameter_names()
    assert config.get_optimization_group("default") == ["tracker.thickness"]

    modifications = config.get_xml_modifications()
    assert "/detector/tracker.xml" in modifications
