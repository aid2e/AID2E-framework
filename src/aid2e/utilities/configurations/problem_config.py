"""Problem configuration models and loader.

Defines generic problem models and a YAML-based loader that parses files like
`examples/basic/problem.config`. The schema focuses on objectives (direction
plus optional computation spec), and the design space reference, while keeping
environment and workflow management outside of the problem scope.

Notes:
        - This module intentionally avoids importing ePIC-specific utilities to
            keep `ProblemConfiguration` generic. ePIC specializations live under
            `epic_utils`.
        - The loader is designed to be modular and future-proof: new keys under
            the top-level `problem` block can be added without breaking existing
            behavior.
        - Objectives now normalize to the unified
            `objectives.ObjectiveDefinition` model with support for script,
            inline, or multi-steps computation.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator, field_validator
from pathlib import Path
import yaml

from .design_config import DesignConfig, DesignConfigLoader
from .env_config import EnvironmentConfig, EnvironmentConfigLoader
from .objectives import (
    ObjectiveDirection,
    ObjectiveDefinition,
    ObjectiveComputationSpec,
)
from .stack_registry import StackRegistry
from aid2e.utilities.epic_utils import EpicConfiguration


class Objective(BaseModel):
    """Backward-compatible minimal objective specification.

    This class preserves the legacy shape (name + minimize) while allowing
    optional computation details. Use ``to_definition`` to obtain the unified
    :class:`ObjectiveDefinition` model.
    """

    name: str
    minimize: bool = True
    computation: Optional[ObjectiveComputationSpec] = None
    metrics_keys: List[str] = Field(default_factory=list)

    def to_objective_direction(self) -> ObjectiveDirection:
        """Convert to ObjectiveDirection enum."""
        return ObjectiveDirection.MINIMIZE if self.minimize else ObjectiveDirection.MAXIMIZE

    def to_definition(self) -> ObjectiveDefinition:
        """Convert to unified ObjectiveDefinition."""
        return ObjectiveDefinition(
            name=self.name,
            direction=self.to_objective_direction(),
            computation=self.computation,
            metrics_keys=self.metrics_keys,
        )


class ProblemConfiguration(BaseModel):
    """Generic problem configuration.

    Focuses on core problem attributes, a design configuration, objectives, and
    optional observations. Environment and scheduler/trial management belong to
    separate workflow components (e.g., `WorkflowManager`).

    Notes:
        - `design_config` accepts any subclass of `DesignConfig`.
        - `objectives` must be non-empty with unique names.
    """
    name: str
    output_location: str
    work_location: str
    problem_type: str  # e.g., "EPIC_TRACKING", "DTLZ2", "CLOSURE_MOO"

    # Accept any subclass of DesignConfig and EnvironmentConfig, including
    # EpicDesignConfig and EpicEnvConfig
    design_config: DesignConfig
    objectives: List[ObjectiveDefinition]
    observations: Optional[List[Dict[str, Any]]] = Field(default=None)
    environment_config: Optional[EnvironmentConfig] = Field(default=None)
    epic_configuration: Optional[EpicConfiguration] = Field(
        default=None,
        description="Optional ePIC-specific environment configuration (legacy interface)",
    )

    @field_validator("objectives", mode="before")
    @classmethod
    def normalize_objectives(cls, raw_objectives: Any) -> List[ObjectiveDefinition]:
        """Normalize various objective payload shapes into ObjectiveDefinition."""
        if not isinstance(raw_objectives, list) or not raw_objectives:
            raise ValueError("'objectives' must be a non-empty list")

        normalized: List[ObjectiveDefinition] = []

        for entry in raw_objectives:
            if isinstance(entry, ObjectiveDefinition):
                normalized.append(entry)
                continue

            if isinstance(entry, Objective):
                normalized.append(entry.to_definition())
                continue

            if isinstance(entry, dict):
                normalized.append(cls._objective_from_dict(entry))
                continue

            raise ValueError(f"Unsupported objective entry type: {type(entry)}")

        return normalized

    @model_validator(mode="after")
    def validate_paths(self) -> "ProblemConfiguration":
        """Validate directory paths and objective correctness.

        - Ensures `output_location` and `work_location` exist.
        - Ensures `objectives` is non-empty with unique names.
        """
        errors = []

        for label, path in [("output_location", self.output_location),
                            ("work_location", self.work_location)]:
            if path and not Path(path).exists():
                errors.append(f"{label} does not exist: {path}")

        # Objectives must be provided and unique
        if not self.objectives:
            errors.append("objectives must be provided and non-empty")
        else:
            names = [obj.name for obj in self.objectives]
            if len(set(names)) != len(names):
                errors.append("objective names must be unique")

        if errors:
            raise ValueError("ProblemConfiguration validation failed:\n" + "\n".join(errors))

        return self

    @staticmethod
    def _parse_computation(computation: Any) -> Optional[ObjectiveComputationSpec]:
        """Convert computation payload to ObjectiveComputationSpec."""
        if computation is None:
            return None
        if isinstance(computation, ObjectiveComputationSpec):
            return computation
        if isinstance(computation, dict):
            payload = dict(computation)
            if "multi-steps" in payload and "multi_steps" not in payload:
                payload["multi_steps"] = payload.pop("multi-steps")
            return ObjectiveComputationSpec(**payload)
        raise ValueError("Invalid computation block for objective; expected mapping or ObjectiveComputationSpec")

    @classmethod
    def _objective_from_dict(cls, payload: Dict[str, Any]) -> ObjectiveDefinition:
        """Build ObjectiveDefinition from a mapping payload."""
        if not isinstance(payload, dict):
            raise ValueError("Objective entry must be a mapping")

        if "name" not in payload:
            raise ValueError("Objective entry missing required field 'name'")

        name = payload["name"]

        if "direction" in payload:
            direction_raw = payload["direction"]
            if isinstance(direction_raw, ObjectiveDirection):
                direction = direction_raw
            else:
                direction = ObjectiveDirection(str(direction_raw).lower())
        else:
            minimize = payload.get("minimize", True)
            direction = ObjectiveDirection.MINIMIZE if minimize else ObjectiveDirection.MAXIMIZE

        computation = cls._parse_computation(payload.get("computation"))
        metrics_keys = payload.get("metrics_keys", []) or []

        return ObjectiveDefinition(
            name=name,
            direction=direction,
            computation=computation,
            metrics_keys=metrics_keys,
        )


class ProblemConfigLoader:
    """Loader for problem YAML/CONFIG files.

    Parses files following the schema used by `examples/basic/problem.config`:

                problem:
                    name: "..."
                    type: "..."
                    output_location: "..."
                    work_location: "..."
                    design_parameters_file: "./path/to/design.params"
                    objectives:
                        - name: "f1"
                            direction: "minimize"
                            computation:
                                script:
                                    path: "scripts/dtlz2_problem.py"
                                    output_file: "objectives_{job_id}.json"
                            metrics_keys: ["f1"]
                        - name: "f2"
                            direction: "minimize"

    Notes:
        Use `ProblemConfigLoader.load()` to load from a file path or
        `ProblemConfigLoader.from_dict()` to construct from an in-memory
        dictionary.
    """

    @staticmethod
    def _build_from_problem_dict(problem: Dict[str, Any], base_dir: Optional[Path]) -> ProblemConfiguration:
        """Build ProblemConfiguration from an inner 'problem' mapping.

        Supports design source via either a file path ('design_parameters_file')
        or inline design payload ('inline_design'). Exactly one must be provided.
        """
        # Required scalar fields
        required_scalar = [
            "name",
            "type",
            "output_location",
            "work_location",
            "objectives",
        ]
        missing = [k for k in required_scalar if k not in problem]
        if missing:
            raise ValueError("Invalid problem definition, missing keys: " + ", ".join(missing))

        # Objectives
        objectives_raw = problem.get("objectives", [])
        if not isinstance(objectives_raw, list) or not objectives_raw:
            raise ValueError("'objectives' must be a non-empty list")

        # Design source mutual exclusivity
        has_path = "design_parameters_file" in problem
        has_inline = "inline_design" in problem
        if has_path == has_inline:
            # Either both True or both False → invalid
            raise ValueError("Specify exactly one of 'design_parameters_file' or 'inline_design'")

        if has_path:
            # Resolve path relative to base_dir if provided
            design_params_path = Path(problem["design_parameters_file"]).expanduser()
            if base_dir and not design_params_path.is_absolute():
                design_params_path = (base_dir / design_params_path).resolve()
            if not design_params_path.exists():
                raise FileNotFoundError(f"Design parameters file not found: {design_params_path}")
            # Use design loader on file
            design_config = DesignConfigLoader.load(str(design_params_path))
        else:
            # Inline design payload, pass through design resolver
            inline = problem["inline_design"]
            if not isinstance(inline, dict):
                raise ValueError("'inline_design' must be a mapping with design parameters")
            resolved = DesignConfigLoader._resolve_design_space(inline, config_dir=str(base_dir or Path('.')))
            payload: Dict[str, Any] = {
                "design_parameters": resolved["design_parameters"],
            }
            if "parameter_constraints" in resolved:
                payload["parameter_constraints"] = resolved["parameter_constraints"]
            design_config = DesignConfig(**payload)

        # Parse epic_configuration if present (legacy hydration)
        epic_config = None
        if "epic_configuration" in problem:
            epic_config_data = problem["epic_configuration"]
            if isinstance(epic_config_data, dict):
                epic_config = EpicConfiguration(**epic_config_data)
            elif isinstance(epic_config_data, EpicConfiguration):
                epic_config = epic_config_data

        # Parse environment config if any present
        env_config = None
        for stack, components in StackRegistry.list_registered_stacks().items():
            config_model = components['config_model']
            config_loader = components['config_loader']
            if config_model.key in problem:
                env_config_data = problem[config_model.key]
                if isinstance(env_config_data, dict):
                    env_config = config_loader.load(**env_config_data)
                elif isinstance(env_config_data, config_model):
                    env_config = env_config_data

        """FIXME this needs to work with inheritance scheme
        # Merge into stack_configurations map for extensibility
        stack_confs = {}
        if "stack_configurations" in problem:
            if not isinstance(problem["stack_configurations"], dict):
                raise ValueError("stack_configurations must be a mapping")
            stack_confs.update(problem["stack_configurations"])

        if epic_config is not None:
            stack_confs.setdefault("epic", epic_config)
        """
        # Build ProblemConfiguration
        return ProblemConfiguration(
            name=problem["name"],
            problem_type=problem["type"],
            output_location=problem["output_location"],
            work_location=problem["work_location"],
            design_config=design_config,
            objectives=objectives_raw,
            observations=problem.get("observations"),
            environment_config=env_config,
            epic_configuration=epic_config,
#            stack_configurations=stack_confs, # FIXME this needs to work with inheritance scheme
        )

    @staticmethod
    def load(file_path: str) -> ProblemConfiguration:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Problem file not found: {file_path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}

        if "problem" not in data or not isinstance(data["problem"], dict):
            raise ValueError("Invalid problem file: missing 'problem' section")

        return ProblemConfigLoader._build_from_problem_dict(data["problem"], base_dir=path.parent)

    @staticmethod
    def from_dict(problem_payload: Dict[str, Any], base_dir: Optional[str] = None) -> ProblemConfiguration:
        """Construct ProblemConfiguration from a dict payload.

        Accepts the inner 'problem' mapping as a Python dict and supports both
        file-based and inline design definitions. Set base_dir for reliable
        relative path resolution when using 'design_parameters_file'.
        """
        return ProblemConfigLoader._build_from_problem_dict(problem_payload, base_dir=Path(base_dir) if base_dir else None)
