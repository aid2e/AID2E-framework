"""Unified objective definition models.

This module defines the single source of truth for objectives across AID2E:
- How objectives are specified in problems (name + direction)
- How they're computed in workflows (script, inline, or multi-steps/DAG)
- How they're optimized by algorithms (directives like "minimize:f1")

Key concepts:
    ObjectiveDirection: MINIMIZE or MAXIMIZE
    ObjectiveComputationSpec: How to compute (script path or inline function)
    ObjectiveDefinition: Complete spec (name + direction + computation)
    ObjectivesRegistry: Runtime mapping of objective names to definitions

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from enum import Enum
from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, ValidationInfo


class ObjectiveDirection(str, Enum):
    """Direction of optimization for an objective.
    
    Attributes:
        MINIMIZE: Minimize the objective value.
        MAXIMIZE: Maximize the objective value.
    """
    MINIMIZE = "minimize"
    MAXIMIZE = "maximize"


class ScriptObjective(BaseModel):
    """Objective computed via external script.
    
    Attributes:
        path: Path to executable script (resolved relative to config directory).
        output_file: Expected output file pattern (e.g., "objectives_*.json").
            The script should create a file matching this pattern containing
            the objective value in JSON/YAML format.
        timeout_sec: Timeout in seconds (optional, default: 300).
        
    Example:
        >>> script = ScriptObjective(
        ...     path="scripts/dtlz2_problem.py",
        ...     output_file="objectives_{job_id}.json"
        ... )
    """
    path: str = Field(..., description="Path to objective computation script")
    output_file: str = Field(..., description="Output file pattern (e.g., objectives_*.json)")
    timeout_sec: int = Field(default=300, ge=1, description="Computation timeout in seconds")


class InlineObjective(BaseModel):
    """Objective computed via inline Python function.
    
    The entrypoint should reference a callable that accepts design parameters
    and returns the objective value.
    
    Attributes:
        entrypoint: Module and function reference (format: "module.path:function_name").
        
    Example:
        >>> inline = InlineObjective(entrypoint="my_objectives:compute_f1")
        >>> # Expects function: def compute_f1(design_params: Dict[str, float]) -> float
        
    Notes:
        - The function is imported at runtime (lazy loading).
        - Must accept design_params: Dict[str, float] as argument.
        - Must return a single float value.
    """
    entrypoint: str = Field(
        ...,
        description="Module:function reference (e.g., 'my_objectives:compute_f1')"
    )
    
    @field_validator('entrypoint')
    @classmethod
    def validate_entrypoint_format(cls, v: str) -> str:
        """Validate entrypoint has 'module:function' format."""
        if ':' not in v or v.count(':') != 1:
            raise ValueError("entrypoint must be 'module:function' format")
        module_part, func_part = v.split(':')
        if not module_part or not func_part:
            raise ValueError("entrypoint module and function names cannot be empty")
        if not all(c.isalnum() or c in '_.:-' for c in module_part):
            raise ValueError(f"Invalid module name: {module_part}")
        if not (func_part[0].isalpha() or func_part[0] == '_'):
            raise ValueError(f"Invalid function name: {func_part}")
        return v


class MultiStepStage(BaseModel):
    """Single stage within a multi-step objective computation.
    
    Supports simple DAG-style sequencing for objective computation. Each stage
    can reference upstream stages via ``depends_on`` and optionally flag itself
    as the producing stage for the objective value.
    
    Attributes:
        name: Unique stage identifier.
        description: Optional human-readable description of the stage intent.
        jobs: Free-form job definitions (executor-specific payloads).
        produces_objective: Whether this stage emits the objective value.
        depends_on: Names of upstream stages this stage depends on.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Stage name (unique within multi-steps)")
    description: Optional[str] = Field(default=None, description="Stage description")
    jobs: List[Dict[str, Any]] = Field(default_factory=list, description="Job definitions (executor-specific)")
    produces_objective: bool = Field(default=False, description="Whether this stage emits the objective value")
    depends_on: List[str] = Field(default_factory=list, description="Upstream stage dependencies")

    @field_validator('depends_on')
    @classmethod
    def validate_dependencies(cls, depends_on: List[str], info: ValidationInfo) -> List[str]:
        """Ensure stages do not depend on themselves."""
        name = None
        if info and info.data:
            name = info.data.get("name")
        if name and name in depends_on:
            raise ValueError(f"Stage '{name}' cannot depend on itself")
        return depends_on


class MultiStepComputationSpec(BaseModel):
    """DAG-style multi-step computation for an objective.

    Replaces the earlier "branch" terminology with a clearer "multi-steps"
    concept. A multi-step computation is a small DAG of stages where exactly
    one stage must produce the objective value.
    
    Attributes:
        stages: Ordered list of stage definitions. Dependencies define the DAG.
        produces_from_stage: Optional explicit producing stage name. If omitted,
            exactly one stage must set ``produces_objective=True``.
    """

    model_config = ConfigDict(populate_by_name=True)

    stages: List[MultiStepStage] = Field(..., min_items=1, description="Stages composing the computation DAG")
    produces_from_stage: Optional[str] = Field(
        default=None,
        description="Explicit stage name that emits the objective (overrides flag)",
        alias="produces_from_stage",
    )

    @model_validator(mode="after")
    def validate_stages(self) -> "MultiStepComputationSpec":
        """Ensure unique names, valid dependencies, and single producer."""
        names = [stage.name for stage in self.stages]
        if len(set(names)) != len(names):
            raise ValueError("Stage names within multi-steps must be unique")

        for stage in self.stages:
            for dep in stage.depends_on:
                if dep not in names:
                    raise ValueError(f"Stage '{stage.name}' depends on unknown stage '{dep}'")

        explicit = self.produces_from_stage
        producing_flags = [s.name for s in self.stages if s.produces_objective]

        if explicit:
            if explicit not in names:
                raise ValueError(f"produces_from_stage '{explicit}' not found in stages")
            chosen = explicit
        else:
            if len(producing_flags) != 1:
                raise ValueError("Exactly one stage must set produces_objective=True when produces_from_stage is not provided")
            chosen = producing_flags[0]

        self.produces_from_stage = chosen
        return self

    def producing_stage(self) -> str:
        """Return the name of the stage that emits the objective value."""
        if not self.produces_from_stage:
            raise ValueError("produces_from_stage was not resolved")
        return self.produces_from_stage


class ObjectiveComputationSpec(BaseModel):
    """Union spec for how an objective is computed.
    
    Supports three mutually exclusive computation modes:
    - ``script``: External script execution
    - ``inline``: Inline Python callable
    - ``multi-steps``: Small DAG of stages (formerly called "branch")
    """

    model_config = ConfigDict(populate_by_name=True)

    script: Optional[ScriptObjective] = None
    inline: Optional[InlineObjective] = None
    multi_steps: Optional[MultiStepComputationSpec] = Field(
        default=None,
        alias="multi-steps",
        description="DAG-style multi-stage computation for the objective",
    )
    
    def __init__(self, **data):
        """Initialize and validate mutual exclusivity."""
        super().__init__(**data)
        has_script = self.script is not None
        has_inline = self.inline is not None
        has_multi = self.multi_steps is not None
        
        provided = [flag for flag in (has_script, has_inline, has_multi) if flag]
        if len(provided) == 0:
            raise ValueError("Provide one of 'script', 'inline', or 'multi-steps' for objective computation")
        if len(provided) > 1:
            raise ValueError("Cannot provide multiple computation modes; choose exactly one of script, inline, or multi-steps")
    
    def is_script(self) -> bool:
        """Check if this is script-based computation."""
        return self.script is not None
    
    def is_inline(self) -> bool:
        """Check if this is inline function computation."""
        return self.inline is not None

    def is_multi_steps(self) -> bool:
        """Check if this is multi-step DAG computation."""
        return self.multi_steps is not None


class ObjectiveDefinition(BaseModel):
    """Complete objective specification: name, direction, and computation.
    
    This is the unified model used across problem, optimization, and workflow layers.
    It combines what to optimize (name + direction) with how to compute it
    (script, inline function, or multi-step DAG).
    
    Attributes:
        name: Unique objective identifier (e.g., "f1", "efficiency").
        direction: Optimization direction (minimize or maximize).
        computation: How to compute (script, inline, or multi-steps).
        metrics_keys: Optional keys to extract from computation output.
            If computation produces a dict, use these keys to extract values.
            Useful when one script produces multiple metrics.
            Example: script outputs {"f1": 0.5, "f2": 0.3, "runtime": 10.2},
                    metrics_keys=["f1"] extracts only f1.
        
    Example:
        >>> # Script-based objective
        >>> obj = ObjectiveDefinition(
        ...     name="f1",
        ...     direction=ObjectiveDirection.MINIMIZE,
        ...     computation=ObjectiveComputationSpec(
        ...         script=ScriptObjective(
        ...             path="scripts/dtlz2.py",
        ...             output_file="objectives_{job_id}.json"
        ...         )
        ...     ),
        ...     metrics_keys=["f1"]
        ... )
        
        >>> # Inline objective
        >>> obj = ObjectiveDefinition(
        ...     name="f2",
        ...     direction=ObjectiveDirection.MINIMIZE,
        ...     computation=ObjectiveComputationSpec(
        ...         inline=InlineObjective(entrypoint="my_obj:compute_f2")
        ...     )
        ... )
        
    Notes:
        - If metrics_keys is empty/None, entire output is assumed to be the value.
        - For script output format, see ScriptObjective.output_file.
    """
    name: str = Field(..., description="Objective name (e.g., 'f1', 'efficiency')")
    direction: ObjectiveDirection = Field(
        ...,
        description="Optimization direction: minimize or maximize"
    )
    computation: Optional[ObjectiveComputationSpec] = Field(
        default=None,
        description="How to compute the objective (script or inline)"
    )
    metrics_keys: List[str] = Field(
        default_factory=list,
        description="Keys to extract from computation output (if dict)"
    )
    
    def to_directive(self) -> str:
        """Convert to optimization directive string format.
        
        Returns:
            String like "minimize:f1" or "maximize:efficiency".
            Useful for OptimizationConfiguration.objectives.
            
        Example:
            >>> obj = ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE, computation=None)
            >>> obj.to_directive()
            'minimize:f1'
        """
        return f"{self.direction.value}:{self.name}"
    
    @classmethod
    def from_directive(cls, directive: str, computation: Optional[ObjectiveComputationSpec] = None) -> "ObjectiveDefinition":
        """Create ObjectiveDefinition from directive string.
        
        Parses strings like "minimize:f1" or "maximize:efficiency".
        
        Args:
            directive: String in format "minimize:name" or "maximize:name".
            computation: Optional ObjectiveComputationSpec (script or inline).
            
        Returns:
            ObjectiveDefinition with parsed direction and name.
            
        Raises:
            ValueError: If directive format is invalid.
            
        Example:
            >>> directive = "minimize:f1"
            >>> obj = ObjectiveDefinition.from_directive(directive)
        """
        if ':' not in directive or directive.count(':') != 1:
            raise ValueError(f"Invalid directive format: {directive}. Expected 'minimize:name' or 'maximize:name'")
        
        direction_str, name = directive.split(':')
        try:
            direction = ObjectiveDirection(direction_str.lower())
        except ValueError:
            raise ValueError(f"Invalid direction '{direction_str}'. Must be 'minimize' or 'maximize'")
        
        if not name.strip():
            raise ValueError("Objective name cannot be empty")
        
        return cls(
            name=name.strip(),
            direction=direction,
            computation=computation
        )


class ObjectivesRegistry:
    """Runtime registry for objective definitions.
    
    Allows objectives to be registered and retrieved by name for use during
    workflow execution. This enables decoupling objective definitions from
    their runtime computation.
    
    Example:
        >>> registry = ObjectivesRegistry()
        >>> obj_f1 = ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE)
        >>> registry.register(obj_f1)
        >>> retrieved = registry.get("f1")
    """
    
    def __init__(self):
        """Initialize empty registry."""
        self._objectives: Dict[str, ObjectiveDefinition] = {}
    
    def register(self, objective: ObjectiveDefinition) -> None:
        """Register an objective by name.
        
        Args:
            objective: ObjectiveDefinition to register.
            
        Raises:
            ValueError: If objective with same name already registered.
        """
        if objective.name in self._objectives:
            raise ValueError(f"Objective '{objective.name}' already registered")
        self._objectives[objective.name] = objective
    
    def get(self, name: str) -> Optional[ObjectiveDefinition]:
        """Retrieve objective definition by name.
        
        Args:
            name: Objective name.
            
        Returns:
            ObjectiveDefinition if found, None otherwise.
        """
        return self._objectives.get(name)
    
    def list_all(self) -> List[ObjectiveDefinition]:
        """Get all registered objectives.
        
        Returns:
            List of all registered ObjectiveDefinition instances.
        """
        return list(self._objectives.values())
    
    def clear(self) -> None:
        """Clear all registered objectives."""
        self._objectives.clear()
