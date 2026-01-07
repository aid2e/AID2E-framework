"""Problem configuration models for defining optimization problems."""

from typing import Optional, Union
from pydantic import BaseModel, model_validator
from pathlib import Path
import os

from .design_config import DesignConfig
from epic_utils.epic_design_config import EpicDesignConfig
from epic_utils.epic_problem_config import EpicConfiguration


class ProblemConfiguration(BaseModel):
    """Complete problem configuration including design and environment."""
    name: str
    output_location: str
    work_location: str
    problem_type: str  # e.g., "EPIC_TRACKING", "DTLZ2", "CLOSURE_MOO"
    
    design_config: Union[DesignConfig, EpicDesignConfig]
    epic_configuration: Optional[EpicConfiguration] = None

    @model_validator(mode="after")
    def validate_paths(self) -> "ProblemConfiguration":
        """Validate all paths exist."""
        errors = []

        # Check directory paths
        for label, path in [("output_location", self.output_location),
                            ("work_location", self.work_location)]:
            if path and not Path(path).exists():
                errors.append(f"{label} does not exist: {path}")

        # Check ePIC installation files
        if self.epic_configuration:
            if self.epic_configuration.epic_install and not Path(self.epic_configuration.epic_install).exists():
                errors.append(f"epic_install path does not exist: {self.epic_configuration.epic_install}")
            if not Path(self.epic_configuration.singularity_image).exists():
                errors.append(f"Singularity image path does not exist: {self.epic_configuration.singularity_image}")

        if errors:
            raise ValueError("ProblemConfiguration validation failed:\n" + "\n".join(errors))

        # Activate ePIC environment if configured
        if self.epic_configuration:
            self.epic_configuration.activate()

        return self
