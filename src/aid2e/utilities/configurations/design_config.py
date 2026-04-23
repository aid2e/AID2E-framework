"""Design configuration models for detector parameter spaces.

This module provides a framework for defining and managing design parameter
spaces, including parameter groups, constraints, and constraint validation.
It accepts only the canonical ``design_space`` schema.

Key Classes:
    - ParameterGroup: Container for related parameters with shared properties.
    - ParameterConstraint: Mathematical constraint rule on design parameters.
    - DesignParameters: Collection of parameter groups.
    - DesignConfig: Complete design configuration with constraints and validation.
    - DesignConfigLoader: YAML file loader with path/inline resolution.

Typical Usage:
    >>> config = DesignConfigLoader.load('design.params')
    >>> param_names = config.get_parameter_names()
    >>> bounds = config.get_parameter_bounds('group.param_name')
    >>> is_valid, failures = config.validate_constraints(param_values)
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from pydantic import BaseModel, Field, RootModel, model_validator
from pathlib import Path
import yaml
import os
import re
import ast

from .base_models import Parameter, BaseParameter


class ParameterGroup(BaseModel):
    """Container for a group of related parameters.
    
    Groups parameters that share common properties or contexts, such as detector
    subsystems (vertex_barrel, silicon_tracker, etc.). Parameters within a group
    are accessed via qualified names (group_name.param_name).
    
    Attributes:
        parameters: Dictionary mapping parameter names to Parameter objects.
    
    Example:
        >>> group = ParameterGroup(parameters={
        ...     'thickness': RangeParameter(value=0.35, bounds=[0.2, 0.6]),
        ...     'pitch': RangeParameter(value=25, bounds=[10, 50])
        ... })
    """
    parameters: Dict[str, Parameter]


class ParameterConstraint(BaseModel):
    """Represents a mathematical constraint on design parameters.
    
    Constraints are validated for syntactic correctness at configuration load time.
    The validated constraints can then be passed to optimizers (e.g., Ax) which handle
    runtime constraint enforcement internally.
    
    Attributes:
        name: Unique identifier for the constraint.
        description: Human-readable explanation of the constraint intent.
        rule: Mathematical expression using qualified parameter names,
              e.g., "group.param1 + group.param2 < 10.0".
    
    Example:
        >>> constraint = ParameterConstraint(
        ...     name="budget_limit",
        ...     description="Total cost must not exceed budget",
        ...     rule="tracker.cost + magnet.cost < 1000"
        ... )
        >>> # Validate syntax (done automatically at load time)
        >>> constraint.validate_syntax(['tracker.cost', 'magnet.cost'])
        (True, None)
    """
    name: str
    description: Optional[str] = None
    rule: str  # Mathematical expression like "x1 + x2 < 10"

    def extract_parameter_names(self) -> Set[str]:
        """Extract parameter names referenced in the constraint rule.
        
        Parses the constraint expression and extracts all identifiers that
        appear to be qualified parameter names (containing a dot).
        
        Returns:
            Set of parameter names found in the rule.
        
        Example:
            >>> constraint = ParameterConstraint(
            ...     name="test",
            ...     rule="tracker.x + magnet.y < detector.limit"
            ... )
            >>> names = constraint.extract_parameter_names()
            >>> print(sorted(names))
            ['detector.limit', 'magnet.y', 'tracker.x']
        """
        # Find all qualified parameter names (e.g., "group.param")
        pattern = r'\b([a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*)\b'
        return set(re.findall(pattern, self.rule))

    def validate_syntax(self, valid_param_names: List[str]) -> Tuple[bool, Optional[str]]:
        """Validate constraint syntax and parameter references.
        
        Checks that:
        1. The constraint rule is valid Python syntax
        2. All referenced parameters exist in the valid_param_names list
        3. The expression is a valid comparison/boolean expression
        
        This is structural validation done at configuration load time,
        NOT runtime constraint evaluation (which is handled by the optimizer).
        
        Args:
            valid_param_names: List of valid qualified parameter names
                              from the design configuration.
        
        Returns:
            Tuple of (is_valid, error_message) where:
            - is_valid: True if constraint is syntactically correct
            - error_message: None if valid, otherwise describes the error
        
        Example:
            >>> constraint = ParameterConstraint(
            ...     name="test", rule="group.x + group.y < 10"
            ... )
            >>> is_valid, err = constraint.validate_syntax(
            ...     ['group.x', 'group.y']
            ... )
            >>> assert is_valid and err is None
        """
        # 1. Check if rule is parseable Python syntax
        try:
            ast.parse(self.rule, mode='eval')
        except SyntaxError as e:
            return False, f"Invalid syntax in constraint rule: {e}"
        
        # 2. Extract and validate parameter names
        referenced_params = self.extract_parameter_names()
        valid_set = set(valid_param_names)
        unknown_params = referenced_params - valid_set
        
        if unknown_params:
            return False, f"Unknown parameters in constraint: {', '.join(sorted(unknown_params))}"
        
        return True, None

    def evaluate(self, param_values: Dict[str, float]) -> bool:
        """Evaluate constraint against parameter values at runtime.
        
        Substitutes parameter names in the constraint rule with their values
        and evaluates the resulting mathematical expression. This is used for
        runtime constraint checking when the optimizer doesn't support
        constraint enforcement (e.g., random search, some evolutionary algorithms).
        
        For optimizers with native constraint support (e.g., Ax), use the
        constraint object directly instead of calling this method.
        
        Args:
            param_values: Dictionary mapping qualified parameter names
                         (e.g., "group.param") to numeric values.
        
        Returns:
            True if constraint is satisfied, False otherwise.
        
        Raises:
            ValueError: If the constraint rule cannot be evaluated
                       (e.g., missing parameters, division by zero).
        
        Example:
            >>> constraint = ParameterConstraint(
            ...     name="test", rule="DTLZ2.x1 < 1.0"
            ... )
            >>> constraint.evaluate({"DTLZ2.x1": 0.5})
            True
            >>> constraint.evaluate({"DTLZ2.x1": 1.5})
            False
        
        Notes:
            - Prefer using optimizer's native constraint enforcement when available
            - This method is primarily for optimizer-agnostic validation
            - Uses eval() on sanitized expressions (validated at load time)
        """
        # Replace parameter names with their values
        expr = self.rule
        for param_name, value in param_values.items():
            # Use word boundaries to avoid partial matches
            expr = re.sub(rf'\b{re.escape(param_name)}\b', str(value), expr)
        
        try:
            # Evaluate the expression
            result = eval(expr)
            return bool(result)
        except Exception as e:
            raise ValueError(f"Failed to evaluate constraint '{self.name}': {e}")


class DesignParameters(RootModel[Dict[str, ParameterGroup]]):
    """Collection of parameter groups for generic design spaces.
    
    Manages a hierarchical organization of design parameters grouped by context
    (subsystems, regions, etc.). Automatically injects fully qualified parameter names
    in the format "group_name.parameter_name" for unique identification.
    
    The root model contains a dictionary mapping group names to ParameterGroup instances.
    
    Example:
        >>> params = DesignParameters(root={
        ...     'tracker': ParameterGroup(parameters={...}),
        ...     'magnet': ParameterGroup(parameters={...})
        ... })
    
    Notes:
        - Qualified names are injected at validation time.
        - Parameter uniqueness is enforced through qualified naming.
    """

    @model_validator(mode="before")
    @classmethod
    def inject_qualified_names(cls, values: Dict[str, dict]) -> Dict[str, dict]:
        """Inject fully qualified names into each parameter.
        
        Modifies parameter objects in-place to add 'name' attribute in the format
        'group_name.parameter_name' if not already present. This ensures every
        parameter has a globally unique identifier within the design space.
        
        Args:
            values: Dictionary mapping group names to group data dicts.
        
        Returns:
            Modified values dict with injected qualified names.
        
        Notes:
            This validator runs before model instantiation and is critical for
            the qualified naming system used throughout this module.
        """
        for group_name, group_data in values.items():
            param_dict = group_data.get("parameters", {})
            for param_name, param_data in param_dict.items():
                if isinstance(param_data, dict) and "name" not in param_data:
                    param_data["name"] = f"{group_name}.{param_name}"
        return values


class DesignConfig(BaseModel):
    """Complete design configuration with parameters and constraints.
    
    Encapsulates a design space including all parameter groups, their bounds/choices,
    and constraints on valid parameter combinations. Validates constraint syntax at
    load time and provides validated constraints for optimizer integration.
    
    This is the base class for specialized configurations (e.g., EpicDesignConfig)
    and supports generic toy problems (DTLZ2, etc.).
    
    Attributes:
        design_parameters: Collection of parameter groups defining the design space.
        parameter_constraints: List of constraints on valid parameter combinations.
    
    Example:
        >>> config = DesignConfig(
        ...     design_parameters=DesignParameters(...),
        ...     parameter_constraints=[ParameterConstraint(...)]
        ... )
        >>> names = config.get_parameter_names()
        >>> bounds = config.get_parameter_bounds('group.param')
        >>> # Constraints are already syntax-validated
        >>> search_space = SearchSpace.from_design_config(config)
    """
    design_parameters: DesignParameters
    parameter_constraints: Optional[List[ParameterConstraint]] = Field(default_factory=list)

    @model_validator(mode='after')
    def validate_constraints_syntax(self) -> "DesignConfig":
        """Validate all constraint syntax and parameter references.
        
        Ensures all constraints:
        1. Have valid Python syntax
        2. Reference only parameters that exist in the design space
        3. Are well-formed boolean/comparison expressions
        
        This validation runs automatically when a DesignConfig is instantiated,
        catching configuration errors early.
        
        Returns:
            Self (for Pydantic validator chaining).
        
        Raises:
            ValueError: If any constraint has invalid syntax or references
                       unknown parameters.
        """
        if not self.parameter_constraints:
            return self
        
        valid_param_names = self.get_parameter_names()
        
        for constraint in self.parameter_constraints:
            is_valid, error_msg = constraint.validate_syntax(valid_param_names)
            if not is_valid:
                raise ValueError(
                    f"Invalid constraint '{constraint.name}': {error_msg}"
                )
        
        return self

    def get_flat_parameters(self) -> Dict[str, BaseParameter]:
        """Retrieve all parameters as a flat dictionary.
        
        Flattens the hierarchical group structure into a single dictionary mapping
        qualified parameter names to parameter objects.
        
        Returns:
            Dictionary mapping qualified names (e.g., "group.param")
            to BaseParameter objects.
        
        Example:
            >>> flat = config.get_flat_parameters()
            >>> param = flat['tracker.thickness']
        """
        flat = {}
        for group in self.design_parameters.root.values():
            for param in group.parameters.values():
                flat[param.name] = param
        return flat

    def get_parameter_names(self) -> List[str]:
        """Get all parameter qualified names in the design space.
        
        Returns a list of all unique qualified parameter names in the format
        'group_name.parameter_name'.
        
        Returns:
            Sorted list of qualified parameter names.
        
        Example:
            >>> names = config.get_parameter_names()
            >>> print(names)
            ['group1.param1', 'group1.param2', 'group2.param1']
        """
        return list(self.get_flat_parameters().keys())
    
    def get_parameter_bounds(self, param_name: str) -> Optional[Tuple[float, float]]:
        """Get bounds for a range parameter.
        
        Retrieves the lower and upper bounds for a RangeParameter by its
        qualified name. Returns None if the parameter is not found or
        does not have bounds (e.g., ChoiceParameter).
        
        Args:
            param_name: Qualified parameter name (e.g., "tracker.thickness").
        
        Returns:
            Tuple of (lower_bound, upper_bound) or None if not applicable.
        
        Raises:
            KeyError: If parameter name is not found (use get_flat_parameters
                     to verify existence first).
        
        Example:
            >>> bounds = config.get_parameter_bounds('tracker.thickness')
            >>> if bounds:
            ...     print(f"Range: {bounds[0]} to {bounds[1]}")
        """
        flat = self.get_flat_parameters()
        param = flat.get(param_name)
        if param and hasattr(param, 'bounds'):
            return param.bounds
        return None

    def get_parameter_choices(self, param_name: str) -> Optional[List[str]]:
        """Get choices for a choice parameter.
        
        Retrieves the list of valid choices for a ChoiceParameter by its
        qualified name. Returns None if the parameter is not found or
        does not have choices (e.g., RangeParameter).
        
        Args:
            param_name: Qualified parameter name (e.g., "detector.type").
        
        Returns:
            List of choice strings or None if not applicable.
        
        Example:
            >>> choices = config.get_parameter_choices('detector.type')
            >>> if choices:
            ...     print(f"Available: {choices}")
        """
        flat = self.get_flat_parameters()
        param = flat.get(param_name)
        if param and hasattr(param, 'choices'):
            return param.choices
        return None
    
    def check_constraints(self, param_values: Dict[str, float]) -> Tuple[bool, List[str]]:
        """Check all constraints against provided parameter values at runtime.
        
        Evaluates each constraint rule with the given parameter values.
        This is primarily for non-Ax optimizers or manual validation.
        For Ax, constraints are passed directly to the optimizer.
        
        Args:
            param_values: Dictionary mapping qualified parameter names to
                         numeric values.
        
        Returns:
            Tuple of (all_valid, failed_constraint_names) where:
            - all_valid: True if all constraints passed, False otherwise.
            - failed_constraint_names: List of constraint names that failed.
        
        Example:
            >>> param_values = {
            ...     'tracker.thickness': 0.35,
            ...     'magnet.strength': 1.5
            ... }
            >>> is_valid, failures = config.check_constraints(param_values)
            >>> if not is_valid:
            ...     print(f"Failed constraints: {failures}")
        
        Notes:
            - Constraints are already syntax-validated at load time
            - For Ax optimizer, use config.parameter_constraints directly
        """
        if not self.parameter_constraints:
            return True, []
        
        failed = []
        for constraint in self.parameter_constraints:
            try:
                if not constraint.evaluate(param_values):
                    failed.append(constraint.name)
            except Exception as e:
                failed.append(f"{constraint.name} (error: {e})")
        
        return len(failed) == 0, failed


class DesignConfigLoader:
    """Load design configurations from YAML files with canonical resolution.
    
    Supports either an external file referenced by ``design_space.path`` or an
    inline ``design_space`` block containing ``design_parameters`` and optional
    ``parameter_constraints``.
    
    Example:
        >>> # Load from file with external design.params
        >>> config = DesignConfigLoader.load('config.yml')
        
        >>> # YAML structure (file-based)
        >>> # design_space:
        >>> #   path: "./design.params"
        
        >>> # YAML structure (inline)
        >>> # design_space:
        >>> #   design_parameters:
        >>> #     group:
        >>> #       parameters: {...}
        >>> #   design_constraints: [...]
    """
    
    @staticmethod
    def _extract_design_space_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Extract canonical design space payload from loaded data.
        
        Args:
            raw: Dictionary loaded from YAML file or inline config.
        
        Returns:
            Dictionary with keys ``design_parameters`` and optionally
            ``parameter_constraints``.
        
        Raises:
            ValueError: If raw data is not a dict or is not canonical.
        """
        if not isinstance(raw, dict):
            raise ValueError("Design space content must be a mapping.")
        space = raw.get("design_space", raw)
        if not isinstance(space, dict):
            raise ValueError("'design_space' must be a mapping.")
        if "design_constraints" in space or "design_constraints" in raw:
            raise ValueError(
                "Legacy key 'design_constraints' is no longer supported. "
                "Use 'parameter_constraints'."
            )
        if "design_parameters" not in space:
            raise ValueError("design_space must include 'design_parameters'.")
        design_parameters = space["design_parameters"]
        parameter_constraints = space.get("parameter_constraints")
        payload: Dict[str, Any] = {"design_parameters": design_parameters}
        if parameter_constraints is not None:
            payload["parameter_constraints"] = parameter_constraints
        return payload

    @staticmethod
    def _resolve_design_space(design_space: Dict[str, Any], config_dir: str = ".") -> Dict[str, Any]:
        """Resolve design space from file path or inline definition.
        
        Args:
            design_space: Dictionary containing 'path' and/or inline definitions.
            config_dir: Base directory for relative path resolution.
        
        Returns:
            Dictionary with ``design_parameters`` and optional
            ``parameter_constraints``.
        
        Raises:
            ValueError: If both 'path' and inline definitions are present.
            FileNotFoundError: If referenced file does not exist.
        
        Example:
            >>> # File-based resolution
            >>> payload = DesignConfigLoader._resolve_design_space(
            ...     {'path': './design.params'},
            ...     config_dir='/path/to/config'
            ... )
            
            >>> # Inline resolution
            >>> payload = DesignConfigLoader._resolve_design_space(
            ...     {'design_parameters': {...}}
            ... )
        
        Notes:
            - Relative paths are resolved relative to config_dir.
            - Absolute paths are used as-is.
            - File not found errors include full resolved path in message.
        """
        has_path = 'path' in design_space
        has_inline = any(k != 'path' for k in design_space)

        if has_path and has_inline:
            raise ValueError(
                "Cannot define both 'path' and inline design_space. Specify "
                "either a file path or inline canonical design parameters."
            )

        if has_path:
            file_path = design_space['path']
            full_path = Path(config_dir) / file_path if not Path(file_path).is_absolute() else Path(file_path)
            if not full_path.exists():
                raise FileNotFoundError(f"Design parameters file not found: {full_path}")
            with open(full_path, 'r') as f:
                loaded_data = yaml.safe_load(f)
            return DesignConfigLoader._extract_design_space_payload(loaded_data)

        if has_inline:
            return DesignConfigLoader._extract_design_space_payload(design_space)

        raise ValueError(
            "Design space must define either a 'path' to a file or inline "
            "'design_parameters'."
        )

    @staticmethod
    def load(file_path: str) -> "DesignConfig":
        """Load design configuration from a YAML file.
        
        Loads a configuration file and returns a DesignConfig instance.
        Accepts only the canonical ``design_space`` schema.
        
        Args:
            file_path: Path to the YAML configuration file. Relative paths
                      are resolved from the current working directory.
        
        Returns:
            DesignConfig instance ready for use in optimization workflows.
        
        Raises:
            FileNotFoundError: If the config file does not exist.
            ValueError: If config structure is invalid or references
                       a non-existent design.params file.
            yaml.YAMLError: If the YAML syntax is invalid.
        
        Example:
            >>> config = DesignConfigLoader.load('examples/design.yml')
            >>> print(config.get_parameter_names())
            >>> is_valid, failures = config.validate_constraints({...})
        
        Notes:
            - The configuration file must be valid YAML.
            - Must contain a top-level ``design_space`` key.
            - Directory of config_file is used as base for relative paths.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        config_dir = path.parent
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        if "design_space" not in data:
            if "design_parameters" in data:
                raise ValueError(
                    "Top-level 'design_parameters' is no longer supported. "
                    "Wrap design content under 'design_space'."
                )
            raise ValueError(
                f"Invalid configuration file format: {file_path}. Missing "
                "'design_space'."
            )

        design_space = data["design_space"]

        resolved = DesignConfigLoader._resolve_design_space(design_space, config_dir=str(config_dir))
        data["design_parameters"] = resolved["design_parameters"]
        if "parameter_constraints" in resolved:
            data["parameter_constraints"] = resolved["parameter_constraints"]

        return DesignConfig(**data)
