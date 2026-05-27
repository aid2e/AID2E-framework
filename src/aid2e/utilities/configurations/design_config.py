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

from typing import ClassVar, Dict, List, Optional, Tuple, Any, Set
from pydantic import BaseModel, Field, RootModel, model_validator
from pathlib import Path
from dataclasses import dataclass
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
        key: YAML key associated with a list of models.

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
    key: ClassVar[str] = 'parameter_constraints'

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

    Attributes:
        root: Dictionary mapping group names to parameter groups.
        key: YAML key associated with models.

    Example:
        >>> params = DesignParameters(root={
        ...     'tracker': ParameterGroup(parameters={...}),
        ...     'magnet': ParameterGroup(parameters={...})
        ... })
    
    Notes:
        - Qualified names are injected at validation time.
        - Parameter uniqueness is enforced through qualified naming.
    """
    key: ClassVar[str] = 'design_parameters'

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
                           Can be specialized for specific contexts such as
                           EpicDesignConfig.
        parameter_constraints: List of constraints on valid parameter combinations.
        key: YAML key associated with model.
    
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
    key: ClassVar[str] = 'design_space'

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
    
    Supports either loading design configuration form an external file or from an
    inline YAML block. In both cases, data should include a `design_space` block
    containing `design_parameters` and optional `parameter_constraints`.

    Class attributes:
        space_key: YAML key of the design space instance to parse, such as
                   'epic_design_space'.
        param_key: YAML key of the design parameters to extract, such as
                   'epic_design_parameters'.
        constrain_key: YAML key of the list of parameter constraints to extract,
                       such as 'parameter_constraints'.

    Example:
        >>> # Load design space from an external file
        >>> config = DesignConfigLoader.load('./configs/design.params')

        >>> # Or load from an inlined design space in a YAML block
        >>> yaml = {
        >>>     "inline design" : {
        >>>         "design_space" : {
        >>>             "design_parameters" : {
        >>>                 "group" : {
        >>>                     "parameters" : {...}
        >>>                 },
        >>>             },
        >>>             "parameter_constraints" : [...]
        >>>         }
        >>>     }
        >>> }
        >>> config = DesignConfigLoader.load(yaml)
    """
    space_key = DesignConfig.key
    param_key = DesignParameters.key
    constrain_key = ParameterConstraint.key

    @classmethod
    def _extract_design_space_payload(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        """Extract canonical design space payload from loaded data.
        
        Args:
            raw: Dictionary loaded from YAML file or inline config.

        Returns:
            Extracted design space as a dictionary.

        Raises:
            ValueError: If raw data is not a dict, is not canonical
                        or is missing required blocks.
        """
        if not isinstance(raw, dict):
            raise ValueError("Design space content must be a mapping.")

        payload = raw.get(cls.space_key, raw)
        if not isinstance(payload, dict):
            raise ValueError(f"{cls.space_key} must be a mapping.")
        if cls.param_key not in payload:
            raise KeyError(f"Required block {cls.param_key} not found in {cls.space_key}")

        # throw errors if any legacy configurations are being used
        if "design_constraints" in payload or "design_constraints" in raw:
            raise ValueError(
                "Legacy key 'design_constraints' is no longer supported. "
                "Use 'parameter_constraints'."
            )
        if cls.space_key not in raw:
            if cls.param_key in raw:
                raise ValueError(
                    f"Top-level {cls.param_key} is no longer supported. "
                    f"Wrap design content under {cls.space_key}."
                )

        return payload

    @classmethod
    def _resolve_design_space(cls, file_path: str, config_dir: str) -> Dict[str, Any]:
        """Resolve design space from a file path
        
        Args:
            file_path: Path to the YAML design config file, can be relative
                       or absolute.
            config_dir: For resolution of relative file_path.

        Returns:
            Dictionary with ``design_parameters`` and optional
            ``parameter_constraints``.
        
        Raises:
            ValueError: If both 'path' and inline definitions are present.
            FileNotFoundError: If referenced file does not exist.

        Notes:
            - Absolute paths are used as-is.
            - File not found errors include full resolved path in message.
        """
        full_path = Path(file_path)
        if config_dir and not full_path.is_absolute():
            full_path = (config_dir / full_path).resolve()
        if not full_path.exists():
            raise FileNotFoundError(f"Design parameters file not found: {full_path}")

        payload = None
        with open(full_path, 'r') as f:
            loaded_data = yaml.safe_load(f)
            payload = DesignConfigLoader._extract_design_space_payload(loaded_data)
        return payload

    @classmethod
    def _process_inputs(cls, design_data: Dict[str, Any] = None, file_path: str = None, config_dir: str = None) -> Dict[str, Any]:
        """Process inputs to load

        Either loads a configuration file and extracts design space config,
        Or processes pre-loaded data to extract design space config. Returns
        the extracted design space config as a dictionary.

        Args:
            design_data: Loaded data stored in a dictionary
            file_path: Path to the YAML design config file, can be relative
                       or absolute.
            config_dir: For resolution of relative file_path.

        Returns:
            Extracted data as dictionary mapping keys onto parameter groups and,
            if present, a list of parameter constraints

        Raises:
            RunTimeWarning: If both inline data and a file path were provided.
            FileNotFoundError: If the config file does not exist.
            ValueError: If config structure is invalid or references
                       a non-existent design.params file.
            yaml.YAMLError: If the YAML syntax is invalid.
            RunTimeError: If neither inline data nor a file path were provided

        Notes:
            - The configuration file must be valid YAML.
            - Must contain a top-level ``design_space`` key.
            - Directory of config_file is used as base for relative paths.
        """
        # should EITHER provide data as a dict OR a file path
        # as a string
        is_data_provided = design_data is not None
        is_file_provided = file_path is not None
        if is_data_provided and is_file_provided:
            raise RuntimeWarning(f"Both data and a file path ({file_path}) were provided. Defaulting to data.")

        payload = None
        if is_data_provided:
            payload = DesignConfigLoader._extract_design_space_payload(design_data)
        elif is_file_provided:
            payload = DesignConfigLoader._resolve_design_space(file_path=file_path, config_dir=config_dir)
        else:
            raise RuntimeError("Provide either data as a dictionary or a path to a file")

        data = {cls.param_key: payload[cls.param_key]}
        if cls.constrain_key in payload:
            data[cls.constrain_key] = payload[cls.constrain_key]
        return data

    @staticmethod
    def load(design_data: Dict[str, Any] = None, file_path: str = None, config_dir: str = None) -> "DesignConfig":
        """Load design configuration.

        Args:
            design_data: Loaded data stored in a dictionary
            file_path: Path to the YAML design config file. Relative paths
                       are resolved from config_dir.
            config_dir: Path to problem YAML config file. Used for resolution
                        of relative paths to YAML design config.

        Returns:
            DesignConfig instance ready for use in optimization workflows.

        Example:
            >>> config = DesignConfigLoader.load('examples/design.yml')
            >>> print(config.get_parameter_names())
            >>> is_valid, failures = config.validate_constraints({...})
        """
        data = DesignConfigLoader._process_inputs(design_data, file_path, config_dir)
        return DesignConfig(**data)
