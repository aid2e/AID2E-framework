"""Tests for DesignConfig and EpicDesignConfig."""

import pytest
from pathlib import Path

from configurations import (
    DesignConfig,
    DesignConfigLoader,
)
from epic_utils import (
    EpicDesignConfig,
    EpicDesignConfigLoader,
)


@pytest.fixture
def toy_design_file(tmp_path):
    """Create a temporary toy design config file."""
    config_content = """design_space:
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1:
          value: 0.5
          bounds: [0.0, 1.0]
        x2:
          value: 0.0
          bounds: [0.0, 1.0]

  design_constraints:
    - name: "simple_test"
      description: "An arbitrary testing"
      rule: "DTLZ2_variables.x1 < 1.0"
"""
    config_file = tmp_path / "toy_design.params"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def design_params_file(tmp_path):
    """Create a temporary design.params file (external design parameters)."""
    params_content = """design_space:
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1:
          value: 0.5
          bounds: [0.0, 1.0]
        x2:
          value: 0.0
          bounds: [0.0, 1.0]
        x3:
          value: 0.0
          bounds: [0.0, 1.0]

  design_constraints:
    - name: "constraint1"
      description: "x1 must be less than 1.0"
      rule: "DTLZ2_variables.x1 < 1.0"
"""
    params_file = tmp_path / "design.params"
    params_file.write_text(params_content)
    return str(params_file)


@pytest.fixture
def config_with_file_path(tmp_path, design_params_file):
    """Create a config file that references an external design.params file."""
    config_content = f"""design_space:
  path: "{design_params_file}"
"""
    config_file = tmp_path / "config_with_path.yml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def config_with_inline_params(tmp_path):
    """Create a config file with inline design parameters."""
    config_content = """design_space:
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1:
          value: 0.5
          bounds: [0.0, 1.0]
        x2:
          value: 0.0
          bounds: [0.0, 1.0]

  design_constraints:
    - name: "constraint1"
      description: "x1 constraint"
      rule: "DTLZ2_variables.x1 < 1.0"
"""
    config_file = tmp_path / "config_inline.yml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.fixture
def config_with_both_path_and_inline(tmp_path, design_params_file):
    """Create an invalid config with both path and inline parameters."""
    config_content = f"""design_space:
  path: "{design_params_file}"
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1:
          value: 0.5
          bounds: [0.0, 1.0]
"""
    config_file = tmp_path / "config_invalid.yml"
    config_file.write_text(config_content)
    return str(config_file)


@pytest.mark.unit
@pytest.mark.utilities
class TestDesignConfig:
    """Tests for generic DesignConfig."""
    
    def test_load_generic_config(self, toy_design_file):
        """Test loading generic design configuration."""
        config = DesignConfigLoader.load(toy_design_file)
        
        assert isinstance(config, DesignConfig)
        assert not isinstance(config, EpicDesignConfig)
    
    def test_get_parameter_names(self, toy_design_file):
        """Test getting parameter names."""
        config = DesignConfigLoader.load(toy_design_file)
        param_names = config.get_parameter_names()
        
        assert len(param_names) == 2
        assert "DTLZ2_variables.x1" in param_names
        assert "DTLZ2_variables.x2" in param_names
    
    def test_get_parameter_bounds(self, toy_design_file):
        """Test getting parameter bounds."""
        config = DesignConfigLoader.load(toy_design_file)
        bounds = config.get_parameter_bounds("DTLZ2_variables.x1")
        
        assert bounds == (0.0, 1.0)
    
    def test_get_flat_parameters(self, toy_design_file):
        """Test getting flat parameters dictionary."""
        config = DesignConfigLoader.load(toy_design_file)
        flat_params = config.get_flat_parameters()
        
        assert len(flat_params) == 2
        assert "DTLZ2_variables.x1" in flat_params
        assert flat_params["DTLZ2_variables.x1"].value == 0.5
    
    def test_constraint_validation_pass(self, toy_design_file):
        """Test constraint validation with valid values."""
        config = DesignConfigLoader.load(toy_design_file)
        param_values = {
            "DTLZ2_variables.x1": 0.5,
            "DTLZ2_variables.x2": 0.0
        }
        
        is_valid, failed = config.validate_constraints(param_values)
        assert is_valid
        assert len(failed) == 0
    
    def test_constraint_validation_fail(self, toy_design_file):
        """Test constraint validation with invalid values."""
        config = DesignConfigLoader.load(toy_design_file)
        param_values = {
            "DTLZ2_variables.x1": 1.5,  # Violates x1 < 1.0
            "DTLZ2_variables.x2": 0.0
        }
        
        is_valid, failed = config.validate_constraints(param_values)
        assert not is_valid
        assert "simple_test" in failed


@pytest.mark.unit
@pytest.mark.utilities
class TestDesignConfigLoaderPathInline:
    """Tests for design parameter path/inline resolution logic."""
    
    def test_load_from_file_path(self, config_with_file_path):
        """Test loading design parameters from an external file."""
        config = DesignConfigLoader.load(config_with_file_path)
        
        assert isinstance(config, DesignConfig)
        param_names = config.get_parameter_names()
        assert len(param_names) == 3  # x1, x2, x3
        assert "DTLZ2_variables.x1" in param_names
        assert "DTLZ2_variables.x2" in param_names
        assert "DTLZ2_variables.x3" in param_names
    
    def test_load_inline_parameters(self, config_with_inline_params):
        """Test loading design parameters defined inline."""
        config = DesignConfigLoader.load(config_with_inline_params)
        
        assert isinstance(config, DesignConfig)
        param_names = config.get_parameter_names()
        assert len(param_names) == 2  # x1, x2
        assert "DTLZ2_variables.x1" in param_names
        assert "DTLZ2_variables.x2" in param_names
    
    def test_path_file_not_found(self, tmp_path):
        """Test error when referenced file path does not exist."""
        config_content = """design_space:
  path: "/nonexistent/design.params"
"""
        config_file = tmp_path / "config_missing.yml"
        config_file.write_text(config_content)
        
        with pytest.raises(FileNotFoundError) as exc_info:
            DesignConfigLoader.load(str(config_file))
        
        assert "Design parameters file not found" in str(exc_info.value)
    
    def test_both_path_and_inline_raises_error(self, config_with_both_path_and_inline):
        """Test that defining both path and inline parameters raises an error."""
        with pytest.raises(ValueError) as exc_info:
            DesignConfigLoader.load(config_with_both_path_and_inline)
        
        error_msg = str(exc_info.value)
        assert "Cannot define both 'path' and inline design_space" in error_msg
    
    def test_relative_path_resolution(self, tmp_path):
        """Test that relative paths are resolved relative to config file directory."""
        # Create design.params in a subdirectory
        subdir = tmp_path / "configs"
        subdir.mkdir()
        
        params_file = subdir / "design.params"
        params_content = """design_space:
  design_parameters:
    test_group:
      parameters:
        param1:
          value: 1.0
          bounds: [0.0, 2.0]
"""
        params_file.write_text(params_content)
        
        # Create config in the same subdirectory referencing design.params
        config_file = subdir / "config.yml"
        config_content = """design_space:
  path: "./design.params"
"""
        config_file.write_text(config_content)
        
        # Load should succeed with relative path
        config = DesignConfigLoader.load(str(config_file))
        assert isinstance(config, DesignConfig)
        assert "test_group.param1" in config.get_parameter_names()


@pytest.mark.unit
@pytest.mark.utilities
class TestEpicDesignConfig:
    """Tests for ePIC-specific design configuration."""
    
    @pytest.fixture
    def epic_config_file(self, tmp_path):
        """Create a temporary ePIC design config file."""
        config_content = """epic_design_parameters:
  vertex_barrel:
    file_path: "$DETECTOR_PATH/compact/tracking/vertex_barrel.xml"
    parameters:
      layer1_radius:
        value: 36.0
        bounds: [30.0, 50.0]
        xml_path: "//constant[@name='VertexBarrel_layer_1_radius']/@value"
        unit: "mm"

parameter_constraints:
  - name: "layer1_min"
    description: "Layer 1 minimum radius"
    rule: "vertex_barrel.layer1_radius > 30.0"

optimization_groups:
  vertex_only:
    - "vertex_barrel.layer1_radius"
"""
        config_file = tmp_path / "epic_tracker.params"
        config_file.write_text(config_content)
        return str(config_file)
    
    def test_load_epic_config(self, epic_config_file):
        """Test loading ePIC design configuration."""
        config = EpicDesignConfigLoader.load(epic_config_file)
        
        assert isinstance(config, EpicDesignConfig)
    
    def test_get_parameter_names(self, epic_config_file):
        """Test getting parameter names from ePIC config."""
        config = EpicDesignConfigLoader.load(epic_config_file)
        param_names = config.get_parameter_names()
        
        assert "vertex_barrel.layer1_radius" in param_names
    
    def test_get_xml_modifications(self, epic_config_file):
        """Test getting XML modifications."""
        config = EpicDesignConfigLoader.load(epic_config_file)
        param_values = {"vertex_barrel.layer1_radius": 40.0}
        
        xml_mods = config.get_xml_modifications(param_values)
        
        assert len(xml_mods) > 0
        # Check that modifications contain the right structure
        for file_path, modifications in xml_mods.items():
            assert isinstance(modifications, list)
            for xpath, unit, value in modifications:
                assert isinstance(xpath, str)
                assert isinstance(value, (int, float))
    
    def test_optimization_groups(self, epic_config_file):
        """Test optimization groups."""
        config = EpicDesignConfigLoader.load(epic_config_file)
        
        opt_groups = config.get_all_optimization_groups()
        assert "vertex_only" in opt_groups
        assert "vertex_barrel.layer1_radius" in opt_groups["vertex_only"]


@pytest.mark.unit
@pytest.mark.utilities
def test_file_not_found():
    """Test that FileNotFoundError is raised for missing files."""
    with pytest.raises(FileNotFoundError):
        DesignConfigLoader.load("nonexistent_file.params")
    
    with pytest.raises(FileNotFoundError):
        EpicDesignConfigLoader.load("nonexistent_file.params")
