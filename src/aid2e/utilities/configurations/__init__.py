"""Configuration utilities for AID2E Framework."""

from aid2e import __MAIN_VERSION__

__version__ = __MAIN_VERSION__

from .base_models import BaseParameter, RangeParameter, ChoiceParameter, Parameter, ContainerConfig
from .design_config import DesignConfig, DesignParameters, ParameterGroup, ParameterConstraint, DesignConfigLoader
from .experimental_stack_config import StackLayerConfig, StackJobDefinition, StackStageDefinition
from .problem_config import ProblemConfiguration, Objective, ProblemConfigLoader
from .stack_registry import StackRegistry
from .optimization_config import OptimizationConfiguration, OptimizerConfig
from .objectives import (
    ObjectiveDirection,
    ObjectiveDefinition,
    ObjectivePlanSpec,
    ObjectiveComputationSpec,
    MultiStepPlanSpec,
    MultiStepStage,
    ScriptObjective,
    InlineObjective,
    ObjectivesRegistry,
)
from .scheduler_config import (
    SchedulerConfiguration,
)
from .scheduler_cascade import (
    resolve_scheduler_cascade,
    create_scheduler_context,
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
    CombinedObjectivePlan,
    CombinedObjectiveMetric,
)

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
	# Experimental stack configuration
	"StackLayerConfig",
        "StackJobDefinition",
        "StackStageDefinition",
	# Problem configuration
	"ProblemConfiguration",
	"Objective",
	"ProblemConfigLoader",
	"StackRegistry",
	# Optimization configuration
	"OptimizationConfiguration",
	"OptimizerConfig",
	# Objectives (unified across problem/optimization/workflow)
	"ObjectiveDirection",
	"ObjectiveDefinition",
	"ObjectivePlanSpec",
	"ObjectiveComputationSpec",
	"MultiStepPlanSpec",
	"MultiStepStage",
	"ScriptObjective",
	"InlineObjective",
	"ObjectivesRegistry",
	# Scheduler/Runner configuration
	"SchedulerConfiguration",
	# Scheduler cascade utilities
	"resolve_scheduler_cascade",
	"create_scheduler_context",
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
    "CombinedObjectivePlan",
    "CombinedObjectiveMetric",
]
