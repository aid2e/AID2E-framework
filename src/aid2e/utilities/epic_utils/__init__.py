"""ePIC-specific utilities for AID2E Framework."""

from aid2e import __MAIN_VERSION__

from .epic_design_config import (
	EpicDesignConfig,
	EpicParameter,
	EpicParameterGroup,
	EpicDesignParameters,
	EpicDesignConfigLoader,
)
from .epic_env_config import EpicConfiguration
from .epic_stack import (
	EpicSimLayer,
	EpicRecLayer,
	EpicAnaLayer,
	EpicStack
)

__version__ = __MAIN_VERSION__
__all__ = [
	"EpicDesignConfig",
	"EpicParameter",
	"EpicParameterGroup",
	"EpicDesignParameters",
	"EpicDesignConfigLoader",
	"EpicConfiguration",
	"EpicSimLayer",
	"EpicRecLayer",
	"EpicAnaLayer",
	"EpicStack"
]
