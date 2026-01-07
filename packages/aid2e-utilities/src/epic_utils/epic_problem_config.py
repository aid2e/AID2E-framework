"""ePIC-specific problem configuration models."""

from typing import Optional
from pydantic import BaseModel

from configurations.problem_config import ProblemConfiguration
from epic_utils.epic_env_config import EpicConfiguration
from epic_utils.epic_design_config import EpicDesignConfig


class EpicProblemConfiguration(ProblemConfiguration):
    """Specialized problem configuration for ePIC workflows.

    Inherits from `ProblemConfiguration` and narrows the `design_config` to
    `EpicDesignConfig`. Keeps the same validation and path semantics as the
    base class while allowing ePIC-specific consumers to rely on a concrete
    design configuration type.

    Notes:
        - This subclass avoids circular imports by sourcing `EpicConfiguration`
          from `epic_env_config` and `EpicDesignConfig` from `epic_design_config`.
        - All path validations and environment activation remain in the base
          `ProblemConfiguration` logic.
    """

    # Narrow type for design_config to EpicDesignConfig for ePIC workflows
    design_config: EpicDesignConfig  # type: ignore[assignment]
