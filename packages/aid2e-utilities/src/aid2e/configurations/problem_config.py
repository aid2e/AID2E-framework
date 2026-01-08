"""Problem configuration models and loader.

Defines generic problem models and a YAML-based loader that parses files like
`examples/basic/problem.config`. The schema focuses on objectives and the
design space reference while keeping environment and workflow management
outside of the problem scope.

Notes:
        - This module intentionally avoids importing ePIC-specific utilities to
            keep `ProblemConfiguration` generic. ePIC specializations live under
            `epic_utils`.
        - The loader is designed to be modular and future-proof: new keys under
            the top-level `problem` block can be added without breaking existing
            behavior.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, model_validator
from pathlib import Path
import yaml

from .design_config import DesignConfig, DesignConfigLoader


class Objective(BaseModel):
    """Single optimization objective.

    Args:
        name: Objective identifier (e.g., "f1").
        minimize: Whether to minimize the objective; if False, maximization.
    """

    name: str
    minimize: bool = True


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

    # Accept any subclass of DesignConfig, including EpicDesignConfig
    design_config: DesignConfig
    objectives: List[Objective]
    observations: Optional[List[Dict[str, Any]]] = Field(default=None)

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
              minimize: true
            - name: "f2"
              minimize: true

    Args:
        file_path: Path to the problem configuration file.

    Returns:
        ProblemConfiguration: Fully instantiated configuration with a loaded
        `design_config` from the referenced design parameters file.

    Raises:
        FileNotFoundError: If the problem file or design parameters file does
        not exist.
        ValueError: If required keys are missing or invalid.
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
        objectives = [Objective(**obj) for obj in objectives_raw]

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

        # Build ProblemConfiguration
        return ProblemConfiguration(
            name=problem["name"],
            problem_type=problem["type"],
            output_location=problem["output_location"],
            work_location=problem["work_location"],
            design_config=design_config,
            objectives=objectives,
            observations=problem.get("observations"),
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
