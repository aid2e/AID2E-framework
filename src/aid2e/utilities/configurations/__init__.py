"""Configuration utilities for AID2E Framework."""

from aid2e import __MAIN_VERSION__

__version__ = __MAIN_VERSION__

from .base_models import BaseParameter, RangeParameter, ChoiceParameter, Parameter, ContainerConfig
from .design_config import DesignConfig, DesignParameters, ParameterGroup, ParameterConstraint, DesignConfigLoader
from .problem_config import ProblemConfiguration, Objective, ProblemConfigLoader
from .optimization_config import OptimizationConfiguration, OptimizerConfig
from .full_config import FullConfig, load_config

__all__ = [
	# Base models
	"BaseParameter",
	"RangeParameter",
	"ChoiceParameter",
	"Parameter",
	"ContainerConfig",
	# Design configuration
	"DesignConfig",
	"DesignParameters",
	"ParameterGroup",
	"ParameterConstraint",
	"DesignConfigLoader",
	# Problem configuration
	"ProblemConfiguration",
	"Objective",
	"ProblemConfigLoader",
	# Optimization configuration
	"OptimizationConfiguration",
	"OptimizerConfig",
	# Full configuration
	"FullConfig",
	"load_config",
]
