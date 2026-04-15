"""Constraint integration tests across DesignConfig, SearchSpace, and Ax."""

import pytest
from pydantic import ValidationError

from aid2e.optimizers.ax.config import AxOptimizerConfig
from aid2e.optimizers.ax.optimizer import AxOptimizer
from aid2e.optimizers.ax import optimizer as ax_optimizer_module
from aid2e.optimizers.base import SearchSpace
from aid2e.utilities.configurations.design_config import DesignConfig, ParameterConstraint


AX_NODE_RUNTIME_AVAILABLE = ax_optimizer_module.AX_NODE_STRATEGY_AVAILABLE


def _design_config_with_constraints(constraints, include_z: bool = False) -> DesignConfig:
    """Build a validated DesignConfig for constraint tests."""
    parameters = {
        "x": {"value": 0.5, "bounds": [0.0, 1.0]},
        "y": {"value": 0.5, "bounds": [0.0, 1.0]},
    }
    if include_z:
        parameters["z"] = {"value": 0.5, "bounds": [0.0, 1.0]}

    return DesignConfig(
        design_parameters={"group1": {"parameters": parameters}},
        parameter_constraints=constraints,
    )


class TestConstraintSyntaxValidation:
    """Test constraint syntax validation in DesignConfig."""

    def test_valid_constraint_accepted(self):
        """Valid constraints should be accepted during DesignConfig creation."""
        config = _design_config_with_constraints(
            [{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}]
        )
        assert len(config.parameter_constraints) == 1
        assert config.parameter_constraints[0].name == "sum_limit"

    def test_unknown_parameter_rejected(self):
        """Constraints referencing unknown parameters should be rejected."""
        with pytest.raises(ValidationError, match="Invalid constraint.*[Uu]nknown parameter"):
            DesignConfig(
                design_parameters={
                    "group1": {"parameters": {"x": {"value": 0.5, "bounds": [0.0, 1.0]}}}
                },
                parameter_constraints=[
                    {
                        "name": "bad_constraint",
                        "rule": "group1.x + group1.unknown <= 1.0",
                    }
                ],
            )

    def test_syntax_error_rejected(self):
        """Constraints with invalid syntax should be rejected."""
        with pytest.raises(ValidationError, match="Invalid constraint.*syntax"):
            DesignConfig(
                design_parameters={
                    "group1": {"parameters": {"x": {"value": 0.5, "bounds": [0.0, 1.0]}}}
                },
                parameter_constraints=[{"name": "bad_syntax", "rule": "group1.x +* 1.0"}],
            )


class TestParameterConstraintMethods:
    """Test ParameterConstraint helper methods."""

    def test_extract_parameter_names(self):
        """Test extraction of parameter names from constraint rules."""
        constraint = ParameterConstraint(
            name="test",
            rule="tracker.x + magnet.y + detector.z <= 10.0",
        )

        param_names = constraint.extract_parameter_names()
        assert param_names == {"tracker.x", "magnet.y", "detector.z"}

    def test_validate_syntax_valid(self):
        """Test syntax validation for valid constraints."""
        constraint = ParameterConstraint(
            name="test",
            rule="group1.x + group1.y <= 1.5",
        )

        valid_params = {"group1.x", "group1.y"}
        is_valid, error = constraint.validate_syntax(valid_params)
        assert is_valid
        assert error is None

    def test_validate_syntax_unknown_param(self):
        """Test syntax validation rejects unknown parameters."""
        constraint = ParameterConstraint(
            name="test",
            rule="group1.x + group1.unknown <= 1.5",
        )

        valid_params = {"group1.x"}
        is_valid, error = constraint.validate_syntax(valid_params)
        assert not is_valid
        assert "unknown parameter" in error.lower()

    def test_evaluate_constraint(self):
        """Test runtime constraint evaluation."""
        constraint = ParameterConstraint(
            name="sum_limit",
            rule="group1.x + group1.y <= 1.5",
        )

        assert constraint.evaluate({"group1.x": 0.5, "group1.y": 0.8}) is True
        assert constraint.evaluate({"group1.x": 1.0, "group1.y": 0.6}) is False


class TestSearchSpaceConstraints:
    """Test SearchSpace constraint handling."""

    def test_constraints_passed_from_design_config(self):
        """SearchSpace should receive constraints from DesignConfig."""
        design_config = _design_config_with_constraints(
            [{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}]
        )
        search_space = SearchSpace.from_design_config(design_config)

        assert len(search_space.constraints) == 1
        assert search_space.constraints[0].name == "sum_limit"
        assert search_space.constraints[0].rule == "group1.x + group1.y <= 1.5"

    def test_check_constraints_method(self):
        """Test SearchSpace.validate() for runtime validation."""
        design_config = _design_config_with_constraints(
            [{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}]
        )
        search_space = SearchSpace.from_design_config(design_config)

        is_valid, errors = search_space.validate({"group1.x": 0.5, "group1.y": 0.8})
        assert is_valid
        assert len(errors) == 0

        is_valid, errors = search_space.validate({"group1.x": 1.0, "group1.y": 0.8})
        assert not is_valid
        assert len(errors) > 0
        assert "sum_limit" in errors[0]


class TestAxOptimizerConstraints:
    """Test Ax optimizer constraint integration."""

    def test_ax_requires_node_runtime_for_constraint_integration(self):
        """Ax constraint integration should fail fast without node runtime support."""
        design_config = _design_config_with_constraints(
            [{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}]
        )
        search_space = SearchSpace.from_design_config(design_config)
        ax_config = AxOptimizerConfig(n_initial_samples=5, seed=42)

        if AX_NODE_RUNTIME_AVAILABLE:
            optimizer = AxOptimizer(
                search_space=search_space,
                config=ax_config,
                objective_names=["f1"],
            )
            assert optimizer.search_space.constraints
            return

        with pytest.raises(RuntimeError, match="node-based generation API required"):
            AxOptimizer(
                search_space=search_space,
                config=ax_config,
                objective_names=["f1"],
            )

    @pytest.mark.skipif(
        not AX_NODE_RUNTIME_AVAILABLE,
        reason="Installed Ax runtime lacks required node-based generation APIs.",
    )
    def test_constraint_parsing_to_ax_format(self):
        """Test parsing of constraint rules to Ax ParameterConstraint format."""
        design_config = _design_config_with_constraints(
            [{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}]
        )
        search_space = SearchSpace.from_design_config(design_config)

        optimizer = AxOptimizer(
            search_space=search_space,
            config=AxOptimizerConfig(n_initial_samples=5, seed=42),
            objective_names=["f1"],
        )

        constraint = design_config.parameter_constraints[0]
        ax_constraint = optimizer._parse_constraint_to_ax(constraint)

        assert ax_constraint is not None
        assert ax_constraint.constraint_dict == {"group1.x": 1.0, "group1.y": 1.0}
        assert ax_constraint.bound == 1.5

    @pytest.mark.skipif(
        not AX_NODE_RUNTIME_AVAILABLE,
        reason="Installed Ax runtime lacks required node-based generation APIs.",
    )
    def test_ax_enforces_constraints(self):
        """Test that Ax enforces constraints during candidate generation."""
        design_config = _design_config_with_constraints(
            [{"name": "sum_limit", "rule": "group1.x + group1.y <= 1.5"}]
        )
        search_space = SearchSpace.from_design_config(design_config)

        optimizer = AxOptimizer(
            search_space=search_space,
            config=AxOptimizerConfig(n_initial_samples=10, seed=42),
            objective_names=["f1"],
        )

        candidates = optimizer.suggest_candidates(n_candidates=20)
        violations = []
        for i, candidate in enumerate(candidates):
            sum_val = candidate["group1.x"] + candidate["group1.y"]
            if sum_val > 1.5:
                violations.append((i, sum_val))

        assert len(violations) == 0

    @pytest.mark.skipif(
        not AX_NODE_RUNTIME_AVAILABLE,
        reason="Installed Ax runtime lacks required node-based generation APIs.",
    )
    def test_multiple_constraints(self):
        """Test Ax with multiple constraints."""
        design_config = _design_config_with_constraints(
            [
                {"name": "sum_xy", "rule": "group1.x + group1.y <= 1.2"},
                {"name": "sum_xz", "rule": "group1.x + group1.z <= 1.3"},
            ],
            include_z=True,
        )
        search_space = SearchSpace.from_design_config(design_config)

        optimizer = AxOptimizer(
            search_space=search_space,
            config=AxOptimizerConfig(n_initial_samples=10, seed=42),
            objective_names=["f1"],
        )

        candidates = optimizer.suggest_candidates(n_candidates=20)
        violations = []
        for i, candidate in enumerate(candidates):
            x = candidate["group1.x"]
            y = candidate["group1.y"]
            z = candidate["group1.z"]
            if x + y > 1.2:
                violations.append((i, "sum_xy"))
            if x + z > 1.3:
                violations.append((i, "sum_xz"))

        assert len(violations) == 0

    @pytest.mark.skipif(
        not AX_NODE_RUNTIME_AVAILABLE,
        reason="Installed Ax runtime lacks required node-based generation APIs.",
    )
    def test_greater_than_constraint(self):
        """Test Ax with >= constraint converted to negated <=."""
        design_config = _design_config_with_constraints(
            [{"name": "min_sum", "rule": "group1.x + group1.y >= 0.3"}]
        )
        search_space = SearchSpace.from_design_config(design_config)

        optimizer = AxOptimizer(
            search_space=search_space,
            config=AxOptimizerConfig(n_initial_samples=10, seed=42),
            objective_names=["f1"],
        )

        constraint = design_config.parameter_constraints[0]
        ax_constraint = optimizer._parse_constraint_to_ax(constraint)

        assert ax_constraint is not None
        assert ax_constraint.constraint_dict == {"group1.x": -1.0, "group1.y": -1.0}
        assert ax_constraint.bound == -0.3

        candidates = optimizer.suggest_candidates(n_candidates=20)
        violations = []
        for i, candidate in enumerate(candidates):
            if candidate["group1.x"] + candidate["group1.y"] < 0.3:
                violations.append(i)

        assert len(violations) == 0
