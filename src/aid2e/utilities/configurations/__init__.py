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
from .loaders import (
	load_raw_config,
	load_problem_config,
	load_optimization_config,
	load_scheduler_config,
	load_workflow_config,
	validate_objective_alignment,
)
from .runtime_builders import (
	infer_optimizer_backend,
	build_optimizer_from_config,
	build_scheduler_runtime_config,
	build_scheduler_from_config,
	build_workflow_executor_from_config,
)
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
	"load_raw_config",
	"load_problem_config",
	"load_optimization_config",
	"load_scheduler_config",
	"load_workflow_config",
	"validate_objective_alignment",
	"infer_optimizer_backend",
	"build_optimizer_from_config",
	"build_scheduler_runtime_config",
	"build_scheduler_from_config",
	"build_workflow_executor_from_config",
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
