"""Unified objective definition models.

This module defines the single source of truth for objectives across AID2E:
- How objectives are specified in problems (name + direction)
- How they're executed in workflows (script, inline, or multi-steps/DAG)
- How they're optimized by algorithms (directives like "minimize:f1")

Key concepts:
    ObjectiveDirection: MINIMIZE or MAXIMIZE
    ObjectivePlanSpec: How to compute (script path, inline function, or multi-step plan)
    ObjectiveDefinition: Complete spec (name + direction + objective plan)
    ObjectivesRegistry: Runtime mapping of objective names to definitions

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

from enum import Enum
from typing import Optional, List, Union, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict, ValidationInfo
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration


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
    """Single stage within a multi-step objective plan.

    Each stage executes either a script or an inline function, can declare
    inputs/outputs/extra_args, and may depend on upstream stages. If a plan has
    only one step, it is represented as a single-element multi-step list.

    Attributes:
        name: Unique stage identifier.
        description: Optional human-readable description of the stage intent.
        script: Script-based execution for this stage (mutually exclusive with inline).
        inline: Inline Python callable for this stage (mutually exclusive with script).
        inputs: Optional input bindings for this stage (free-form mapping).
        outputs: Optional output bindings for this stage (free-form mapping).
        extra_args: Additional args/metadata for the stage executor.
        jobs: Free-form job definitions (legacy/executor-specific payloads).
        produces_objective: Whether this stage emits the objective value.
        depends_on: Names of upstream stages this stage depends on.
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(..., description="Stage name (unique within multi-steps)")
    description: Optional[str] = Field(default=None, description="Stage description")
    script: Optional[ScriptObjective] = Field(default=None, description="Script execution for this stage")
    inline: Optional[InlineObjective] = Field(default=None, description="Inline callable for this stage")
    inputs: Dict[str, Any] = Field(default_factory=dict, description="Input bindings for this stage")
    outputs: Dict[str, Any] = Field(default_factory=dict, description="Output bindings for this stage")
    extra_args: Dict[str, Any] = Field(default_factory=dict, description="Extra args/metadata for the stage executor")
    jobs: List[Dict[str, Any]] = Field(default_factory=list, description="Job definitions (executor-specific)")
    produces_objective: bool = Field(default=False, description="Whether this stage emits the objective value")
    depends_on: List[str] = Field(default_factory=list, description="Upstream stage dependencies")

    @model_validator(mode="after")
    def validate_action(self) -> "MultiStepStage":
        """Ensure stage has a valid execution definition.
        
        A stage must have one of:
        - script: Script-based execution
        - inline: Inline Python callable
        - jobs: Legacy job definitions (for backward compatibility)
        
        Only one of script/inline can be set. Jobs can coexist with either.
        """
        has_script = self.script is not None
        has_inline = self.inline is not None
        has_jobs = bool(self.jobs)
        
        # script and inline are mutually exclusive
        if has_script and has_inline:
            raise ValueError("Stage must choose exactly one of script or inline, not both")
        
        # At least one execution method must be defined
        if not has_script and not has_inline and not has_jobs:
            raise ValueError("Stage must define at least one of: script, inline, or jobs")
        
        return self

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


class MultiStepPlanSpec(BaseModel):
    """DAG-style multi-step plan for an objective.

    Replaces the earlier "branch" terminology with a clearer "multi-steps"
    concept. A multi-step plan is a small DAG of stages where exactly
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
    def validate_stages(self) -> "MultiStepPlanSpec":
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


class ObjectivePlanSpec(BaseModel):
    """Plan for executing an objective (always modeled as multi-steps).

    The canonical form is a multi-step plan with one or more stages. As a
    convenience, users may supply a single script or inline definition; it will
    be wrapped into a single-step multi-step plan automatically.
    """

    model_config = ConfigDict(populate_by_name=True)

    multi_steps: MultiStepPlanSpec = Field(
        ...,
        alias="multi-steps",
        description="DAG-style multi-stage plan for the objective",
    )

    @model_validator(mode="before")
    def coerce_single_step(cls, values: Any) -> Any:
        """Allow single script/inline definitions by wrapping into a one-step plan."""
        if not isinstance(values, dict):
            return values
        if values.get("multi_steps") or values.get("multi-steps"):
            return values

        script = values.pop("script", None)
        inline = values.pop("inline", None)

        if script and inline:
            raise ValueError("Provide either script or inline, not both, for objective_plan")
        if not script and not inline:
            return values  # will fail later because multi_steps missing

        stage_payload: Dict[str, Any] = {
            "name": "objective_step",
            "produces_objective": True,
        }
        if script:
            stage_payload["script"] = script
        if inline:
            stage_payload["inline"] = inline

        values["multi_steps"] = {
            "stages": [stage_payload],
            "produces_from_stage": "objective_step",
        }
        return values

    def is_multi_steps(self) -> bool:
        """Return True if this plan is a multi-step DAG (always true for canonical form)."""
        return self.multi_steps is not None


# Compatibility aliases for in-flight refactors; prefer ObjectivePlanSpec.
MultiStepComputationSpec = MultiStepPlanSpec
ObjectiveComputationSpec = ObjectivePlanSpec


class ObjectiveDefinition(BaseModel):
    """Complete objective specification: name, direction, and objective plan.

    This is the unified model used across problem, optimization, and workflow layers.
    It combines what to optimize (name + direction) with how to execute it
    (script, inline function, or multi-step DAG).

    Attributes:
        name: Unique objective identifier (e.g., "f1", "efficiency").
        direction: Optimization direction (minimize or maximize).
        objective_plan: How to execute (script, inline, or multi-steps).
        scheduler: Optional objective-level scheduler default (cascades to stages).
        metrics_keys: Optional keys to extract from plan output when it returns a dict.
            Useful when one plan produces multiple metrics.
            Example: plan outputs {"f1": 0.5, "f2": 0.3, "runtime": 10.2},
                    metrics_keys=["f1"] extracts only f1.
    """
    name: str = Field(..., description="Objective name (e.g., 'f1', 'efficiency')")
    direction: ObjectiveDirection = Field(
        ...,
        description="Optimization direction: minimize or maximize"
    )
    objective_plan: Optional[ObjectivePlanSpec] = Field(
        default=None,
        description="How to execute the objective (script, inline, or multi-steps)",
    )
    scheduler: Optional[SchedulerConfiguration] = Field(
        default=None,
        description="Default scheduler for this objective; cascades to its stages",
    )
    metrics_keys: List[str] = Field(
        default_factory=list,
        description="Keys to extract from plan output (if dict)",
    )
    
    def to_directive(self) -> str:
        """Convert to optimization directive string format.
        
        Returns:
            String like "minimize:f1" or "maximize:efficiency".
            Useful for OptimizationConfiguration.objectives.
            
        Example:
            >>> obj = ObjectiveDefinition(name="f1", direction=ObjectiveDirection.MINIMIZE, objective_plan=None)
            >>> obj.to_directive()
            'minimize:f1'
        """
        return f"{self.direction.value}:{self.name}"
    
    @classmethod
    def from_directive(
        cls,
        directive: str,
        objective_plan: Optional[ObjectivePlanSpec] = None,
    ) -> "ObjectiveDefinition":
        """Create ObjectiveDefinition from directive string.
        
        Parses strings like "minimize:f1" or "maximize:efficiency".
        
        Args:
            directive: String in format "minimize:name" or "maximize:name".
            objective_plan: Optional ObjectivePlanSpec (script, inline, or multi-steps).
            
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
            objective_plan=objective_plan,
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
