"""
Unit tests for CLI helper functions (_helpers.py).

Tests config type detection, parameter counting, and formatting utilities.
"""

import pytest
from aid2e.cli._helpers import (
    detect_config_type,
    count_parameters,
    extract_description_data,
)


class TestConfigTypeDetection:
    """Test automatic configuration type detection."""
    
    def test_detect_full_config(self):
        """Full config has both problem and optimization."""
        data = {
            "problem": {"name": "test"},
            "optimization": {"name": "test"}
        }
        assert detect_config_type(data) == "full"
    
    def test_detect_problem_only(self):
        """Problem-only config has problem but no optimization."""
        data = {"problem": {"name": "test"}}
        assert detect_config_type(data) == "problem"
    
    def test_detect_optimization_only(self):
        """Optimization-only config has optimization but no problem."""
        data = {"optimization": {"name": "test"}}
        assert detect_config_type(data) == "optimization"
    
    def test_detect_design_with_design_space(self):
        """Design config has design_space key."""
        data = {"design_space": {"design_parameters": {}}}
        assert detect_config_type(data) == "design"
    
    def test_detect_design_with_design_parameters(self):
        """Design config can have design_parameters key directly."""
        data = {"design_parameters": {}}
        assert detect_config_type(data) == "design"
    
    def test_detect_unknown_config(self):
        """Unknown config type when no recognizable keys."""
        data = {"random": "data"}
        assert detect_config_type(data) == "unknown"
    
    def test_detect_empty_config(self):
        """Empty config is unknown."""
        data = {}
        assert detect_config_type(data) == "unknown"


class TestParameterCounting:
    """Test parameter counting across groups."""
    
    def test_count_single_group(self):
        """Count parameters in single group."""
        params = {
            "group1": {
                "parameters": {
                    "x1": {"value": 0.5},
                    "x2": {"value": 1.0}
                }
            }
        }
        assert count_parameters(params) == 2
    
    def test_count_multiple_groups(self):
        """Count parameters across multiple groups."""
        params = {
            "group1": {
                "parameters": {
                    "x1": {"value": 0.5},
                    "x2": {"value": 1.0}
                }
            },
            "group2": {
                "parameters": {
                    "y1": {"value": 2.0},
                    "y2": {"value": 3.0},
                    "y3": {"value": 4.0}
                }
            }
        }
        assert count_parameters(params) == 5
    
    def test_count_empty_groups(self):
        """Count zero when groups have no parameters."""
        params = {
            "group1": {"parameters": {}},
            "group2": {"parameters": {}}
        }
        assert count_parameters(params) == 0
    
    def test_count_missing_parameters_key(self):
        """Handle groups without 'parameters' key."""
        params = {
            "group1": {"parameters": {"x1": {}}},
            "group2": {"other_key": "value"}  # Missing parameters key
        }
        assert count_parameters(params) == 1
    
    def test_count_empty_dict(self):
        """Count zero for empty dict."""
        assert count_parameters({}) == 0


class TestDescriptionExtraction:
    """Test structured description extraction for JSON/YAML output."""
    
    def test_extract_full_config_description(self):
        """Extract description from full config."""
        data = {
            "problem": {
                "name": "Test Problem",
                "type": "toy",
                "objectives": [{"name": "f1"}, {"name": "f2"}]
            },
            "optimization": {
                "optimizer": {"name": "ax"},
                "n_iterations": 50
            }
        }
        result = extract_description_data(data, "full")
        
        assert result["type"] == "full"
        assert result["summary"]["problem_name"] == "Test Problem"
        assert result["summary"]["problem_type"] == "toy"
        assert result["summary"]["optimizer"] == "ax"
        assert result["summary"]["n_iterations"] == 50
        assert result["summary"]["n_objectives"] == 2
    
    def test_extract_problem_description(self):
        """Extract description from problem config."""
        data = {
            "problem": {
                "name": "Test Problem",
                "type": "custom",
                "objectives": [{"name": "f1"}]
            }
        }
        result = extract_description_data(data, "problem")
        
        assert result["type"] == "problem"
        assert result["summary"]["name"] == "Test Problem"
        assert result["summary"]["type"] == "custom"
        assert result["summary"]["n_objectives"] == 1
    
    def test_extract_optimization_description(self):
        """Extract description from optimization config."""
        data = {
            "optimization": {
                "name": "Test Opt",
                "optimizer": {"name": "ax"},
                "n_iterations": 100
            }
        }
        result = extract_description_data(data, "optimization")
        
        assert result["type"] == "optimization"
        assert result["summary"]["name"] == "Test Opt"
        assert result["summary"]["optimizer"] == "ax"
        assert result["summary"]["n_iterations"] == 100
    
    def test_extract_design_description(self):
        """Extract description from design config."""
        data = {
            "design_space": {
                "design_parameters": {
                    "group1": {
                        "parameters": {"x1": {}, "x2": {}}
                    },
                    "group2": {
                        "parameters": {"y1": {}}
                    }
                },
                "design_constraints": [
                    {"name": "c1"},
                    {"name": "c2"}
                ]
            }
        }
        result = extract_description_data(data, "design")
        
        assert result["type"] == "design"
        assert result["summary"]["n_parameters"] == 3
        assert result["summary"]["n_constraints"] == 2
        assert set(result["summary"]["groups"]) == {"group1", "group2"}
    
    def test_extract_with_alternative_constraint_key(self):
        """Handle alternative parameter_constraints key."""
        data = {
            "design_space": {
                "design_parameters": {
                    "group1": {"parameters": {"x1": {}}}
                },
                "parameter_constraints": [{"name": "c1"}]
            }
        }
        result = extract_description_data(data, "design")
        assert result["summary"]["n_constraints"] == 1
