"""Configuration utilities for AID2E Framework."""

from aid2e import __MAIN_VERSION__

__version__ = __MAIN_VERSION__

from .base_models import BaseParameter, RangeParameter, ChoiceParameter, Parameter, ContainerConfig
from .design_config import DesignConfig, DesignParameters, ParameterGroup, ParameterConstraint, DesignConfigLoader
from .problem_config import ProblemConfiguration, Objective, ProblemConfigLoader
from .optimization_config import OptimizationConfiguration, OptimizerConfig
from .objectives import (
    ObjectiveDirection,
    ObjectiveDefinition,
    ObjectiveComputationSpec,
	MultiStepComputationSpec,
	MultiStepStage,
    ScriptObjective,
    InlineObjective,
    ObjectivesRegistry,
)
from .scheduler_config import (
    SchedulerConfiguration,
    SlurmRunnerConfig,
    PanDAiDDSRunnerConfig,
)
from .scheduler_registry import register_runner_config, get_runner_config_model, list_registered_runners
from .full_config import FullConfig, load_config
from .workflow_config import (
    WorkflowsConfiguration,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    JobFactory,
    ParallelismPolicy,
    ArtifactSpec,
)

# Lazy load JobLibRunnerConfig to avoid circular imports with joblib
def __getattr__(name: str):
    """Lazy-load JobLibRunnerConfig when accessed."""
    if name == "JobLibRunnerConfig":
        from aid2e.schedulers.JobLib import JobLibRunnerConfig
        return JobLibRunnerConfig
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
	# Objectives (unified across problem/optimization/workflow)
	"ObjectiveDirection",
	"ObjectiveDefinition",
	"ObjectiveComputationSpec",
	"MultiStepComputationSpec",
	"MultiStepStage",
	"ScriptObjective",
	"InlineObjective",
	"ObjectivesRegistry",
	# Scheduler/Runner configuration
	"SchedulerConfiguration",
	"JobLibRunnerConfig",
	"SlurmRunnerConfig",
	"PanDAiDDSRunnerConfig",
	# Scheduler registry
	"register_runner_config",
	"get_runner_config_model",
	"list_registered_runners",
	# Full configuration
	"FullConfig",
	"load_config",
	# Workflow configuration
	"WorkflowsConfiguration",
	"WorkflowDefinition",
	"BranchDefinition",
	"StageDefinition",
	"JobDefinition",
	"JobFactory",
	"ParallelismPolicy",
	"ArtifactSpec",
]
