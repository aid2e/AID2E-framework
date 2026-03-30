"""ePIC-specific utilities for AID2E Framework."""

from aid2e import __MAIN_VERSION__

from .epic_design_config import (
	EpicDesignConfig,
	EpicParameter,
	EpicParameterGroup,
	EpicDesignParameters,
	EpicDesignConfigLoader,
)
from .epic_env_config import (
	EpicConfiguration,
	EpicEnvConfig,
	EpicEnvConfigLoader,
)
from .epic_stack import (
	EpicGeoLayer,
	EpicSimLayer,
	EpicRecLayer,
	EpicAnaLayer,
	EpicStack,
)
from .epic_stack_config import (
	EpicLayerConfig,
	EpicJobDefinition,
	EpicStageDefinition,
)

__version__ = __MAIN_VERSION__
__all__ = [
	"EpicDesignConfig",
	"EpicParameter",
	"EpicParameterGroup",
	"EpicDesignParameters",
	"EpicDesignConfigLoader",
	"EpicConfiguration",
	"EpicEnvConfig",
        "EpicEnvConfigLoader",
	"EpicGeoLayer",
	"EpicSimLayer",
	"EpicRecLayer",
	"EpicAnaLayer",
	"EpicStack",
	"EpicLayerConfig",
	"EpicJobDefinition",
	"EpicStageDefinition",
]
