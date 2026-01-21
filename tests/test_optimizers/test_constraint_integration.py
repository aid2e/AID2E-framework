"""Integration tests for constraint handling across DesignConfig, SearchSpace, and Ax optimizer.

Tests the complete constraint workflow:
1. DesignConfig validates constraint syntax at load time
2. SearchSpace stores validated constraints
3. Ax optimizer converts constraints to native Ax format
4. Ax enforces constraints during candidate generation
"""

import pytest
from pydantic import ValidationError
from aid2e.utilities.configurations.design_config import DesignConfig, ParameterConstraint
from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax.optimizer import AxOptimizer
from aid2e.optimizers.ax.config import AxOptimizerConfig


class TestConstraintSyntaxValidation:
    """Test constraint syntax validation in DesignConfig."""

    def test_valid_constraint_accepted(self):
        """Valid constraints should be accepted during DesignConfig creation."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}
            ]
        }
        
        # Should not raise
        config = DesignConfig(**config_data)
        assert len(config.parameter_constraints) == 1
        assert config.parameter_constraints[0].name == "sum_limit"

    def test_unknown_parameter_rejected(self):
        """Constraints referencing unknown parameters should be rejected."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "bad_constraint", "rule": "group1.x + group1.unknown <= 1.0"}
            ]
        }
        
        with pytest.raises(ValidationError, match="Invalid constraint.*[Uu]nknown parameter"):
            DesignConfig(**config_data)

    def test_syntax_error_rejected(self):
        """Constraints with invalid syntax should be rejected."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "bad_syntax", "rule": "group1.x +* 1.0"}  # Invalid syntax
            ]
        }
        
        with pytest.raises(ValidationError, match="Invalid constraint.*syntax"):
            DesignConfig(**config_data)


class TestParameterConstraintMethods:
    """Test ParameterConstraint helper methods."""

    def test_extract_parameter_names(self):
        """Test extraction of parameter names from constraint rules."""
        constraint = ParameterConstraint(
            name="test",
            rule="tracker.x + magnet.y + detector.z <= 10.0"
        )
        
        param_names = constraint.extract_parameter_names()
        assert param_names == {'tracker.x', 'magnet.y', 'detector.z'}

    def test_validate_syntax_valid(self):
        """Test syntax validation for valid constraints."""
        constraint = ParameterConstraint(
            name="test",
            rule="group1.x + group1.y <= 1.5"
        )
        
        valid_params = {'group1.x', 'group1.y'}
        is_valid, error = constraint.validate_syntax(valid_params)
        assert is_valid
        assert error is None

    def test_validate_syntax_unknown_param(self):
        """Test syntax validation rejects unknown parameters."""
        constraint = ParameterConstraint(
            name="test",
            rule="group1.x + group1.unknown <= 1.5"
        )
        
        valid_params = {'group1.x'}
        is_valid, error = constraint.validate_syntax(valid_params)
        assert not is_valid
        assert "unknown parameter" in error.lower()

    def test_evaluate_constraint(self):
        """Test runtime constraint evaluation."""
        constraint = ParameterConstraint(
            name="sum_limit",
            rule="group1.x + group1.y <= 1.5"
        )
        
        # Test satisfying constraint
        assert constraint.evaluate({'group1.x': 0.5, 'group1.y': 0.8}) is True
        
        # Test violating constraint
        assert constraint.evaluate({'group1.x': 1.0, 'group1.y': 0.6}) is False


class TestSearchSpaceConstraints:
    """Test SearchSpace constraint handling."""

    def test_constraints_passed_from_design_config(self):
        """SearchSpace should receive constraints from DesignConfig."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}
            ]
        }
        
        design_config = DesignConfig(**config_data)
        search_space = SearchSpace.from_design_config(design_config)
        
        assert len(search_space.constraints) == 1
        assert search_space.constraints[0].name == "sum_limit"
        assert search_space.constraints[0].rule == "group1.x + group1.y <= 1.5"

    def test_check_constraints_method(self):
        """Test SearchSpace.validate() for runtime validation."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}
            ]
        }
        
        design_config = DesignConfig(**config_data)
        search_space = SearchSpace.from_design_config(design_config)
        
        # Test with valid parameters
        valid_params = {'group1.x': 0.5, 'group1.y': 0.8}
        is_valid, errors = search_space.validate(valid_params)
        assert is_valid
        assert len(errors) == 0
        
        # Test with invalid parameters
        invalid_params = {'group1.x': 1.0, 'group1.y': 0.8}
        is_valid, errors = search_space.validate(invalid_params)
        assert not is_valid
        assert len(errors) > 0
        assert "sum_limit" in errors[0]


class TestAxOptimizerConstraints:
    """Test Ax optimizer constraint integration."""

    def test_constraint_parsing_to_ax_format(self):
        """Test parsing of constraint rules to Ax ParameterConstraint format."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}
            ]
        }
        
        design_config = DesignConfig(**config_data)
        search_space = SearchSpace.from_design_config(design_config)
        
        ax_config = AxOptimizerConfig(
            name="test_ax",
            n_initial_samples=5,
            model_type="SOBOL",
            objectives=["f1"]
        )
        
        optimizer = AxOptimizer(
            search_space=search_space,
            config=ax_config,
            objective_names=["f1"]
        )
        
        # Test constraint parsing
        constraint = design_config.parameter_constraints[0]
        ax_constraint = optimizer._parse_constraint_to_ax(constraint)
        
        assert ax_constraint is not None
        assert ax_constraint.constraint_dict == {'group1.x': 1.0, 'group1.y': 1.0}
        assert ax_constraint.bound == 1.5

    def test_ax_enforces_constraints(self):
        """Test that Ax actually enforces constraints during generation."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}
            ]
        }
        
        design_config = DesignConfig(**config_data)
        search_space = SearchSpace.from_design_config(design_config)
        
        ax_config = AxOptimizerConfig(
            name="test_ax",
            n_initial_samples=10,
            model_type="SOBOL",
            objectives=["f1"]
        )
        
        optimizer = AxOptimizer(
            search_space=search_space,
            config=ax_config,
            objective_names=["f1"]
        )
        
        # Generate candidates
        candidates = optimizer.suggest_candidates(n_candidates=20)
        
        # Verify all candidates satisfy the constraint
        violations = []
        for i, candidate in enumerate(candidates):
            x = candidate['group1.x']
            y = candidate['group1.y']
            sum_val = x + y
            if sum_val > 1.5:
                violations.append((i, x, y, sum_val))
        
        assert len(violations) == 0, (
            f"Found {len(violations)} constraint violations: {violations}"
        )

    def test_multiple_constraints(self):
        """Test Ax with multiple constraints."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "z": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "sum_xy", "rule": "group1.x + group1.y <= 1.2"},
                {"name": "sum_xz", "rule": "group1.x + group1.z <= 1.3"},
            ]
        }
        
        design_config = DesignConfig(**config_data)
        search_space = SearchSpace.from_design_config(design_config)
        
        ax_config = AxOptimizerConfig(
            name="test_ax",
            n_initial_samples=10,
            model_type="SOBOL",
            objectives=["f1"]
        )
        
        optimizer = AxOptimizer(
            search_space=search_space,
            config=ax_config,
            objective_names=["f1"]
        )
        
        # Generate candidates
        candidates = optimizer.suggest_candidates(n_candidates=20)
        
        # Verify all candidates satisfy both constraints
        violations = []
        for i, candidate in enumerate(candidates):
            x = candidate['group1.x']
            y = candidate['group1.y']
            z = candidate['group1.z']
            
            if x + y > 1.2:
                violations.append((i, 'sum_xy', x + y))
            if x + z > 1.3:
                violations.append((i, 'sum_xz', x + z))
        
        assert len(violations) == 0, (
            f"Found {len(violations)} constraint violations: {violations}"
        )

    def test_greater_than_constraint(self):
        """Test Ax with >= constraint (converted to negated <=)."""
        config_data = {
            "design_parameters": {
                "group1": {
                    "parameters": {
                        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
                        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
                    }
                }
            },
            "parameter_constraints": [
                {"name": "min_sum", "rule": "group1.x + group1.y >= 0.3"}
            ]
        }
        
        design_config = DesignConfig(**config_data)
        search_space = SearchSpace.from_design_config(design_config)
        
        ax_config = AxOptimizerConfig(
            name="test_ax",
            n_initial_samples=10,
            model_type="SOBOL",
            objectives=["f1"]
        )
        
        optimizer = AxOptimizer(
            search_space=search_space,
            config=ax_config,
            objective_names=["f1"]
        )
        
        # Test constraint parsing (should negate to: -x - y <= -0.3)
        constraint = design_config.parameter_constraints[0]
        ax_constraint = optimizer._parse_constraint_to_ax(constraint)
        
        assert ax_constraint is not None
        assert ax_constraint.constraint_dict == {'group1.x': -1.0, 'group1.y': -1.0}
        assert ax_constraint.bound == -0.3
        
        # Generate candidates and verify constraint
        candidates = optimizer.suggest_candidates(n_candidates=20)
        
        violations = []
        for i, candidate in enumerate(candidates):
            x = candidate['group1.x']
            y = candidate['group1.y']
            sum_val = x + y
            if sum_val < 0.3:
                violations.append((i, x, y, sum_val))
        
        assert len(violations) == 0, (
            f"Found {len(violations)} constraint violations: {violations}"
        )
