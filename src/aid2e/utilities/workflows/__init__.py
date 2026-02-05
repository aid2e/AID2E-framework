"""Workflow utilities for AID2E Framework"""

from aid2e import __MAIN_VERSION__

from .experimental_stack import (
	AnaLayer,
        ExperimentStack,
	StackLayer,
)
from .dag_types import (
	DagDefinition,
	DagNode,
	DagEdge,
	DagNodeType,
	TopologicalOrder,
	CycleDetectionResult,
	DagValidator,
	topological_sort,
	detect_cycles,
)
# Workflow configuration is now in configurations package for architectural consistency
from aid2e.utilities.configurations.workflow_config import (
	WorkflowsConfiguration,
	WorkflowDefinition,
	BranchDefinition,
	StageDefinition,
	JobDefinition,
	JobFactory,
	ParallelismPolicy,
	ArtifactSpec,
)
from .execution_utils import build_objective_call
from .execution_engine import (
	BranchContext,
	StageContext,
	JobContext,
	BaseExecutionEngine,
	BashExecutionEngine,
	PythonExecutionEngine,
	ContainerExecutionEngine,
)
from .dag_executor import (
	DAGExecutor,
	create_executor_from_config,
)

__version__ = __MAIN_VERSION__
__all__ = [
	"StackLayer",
	"ExperimentStack",
	"AnaLayer",
	# Workflow configuration (re-exported from configurations for backward compatibility)
	"WorkflowsConfiguration",
	"WorkflowDefinition",
	"BranchDefinition",
	"StageDefinition",
	"JobDefinition",
	"JobFactory",
	"ParallelismPolicy",
	"ArtifactSpec",
	# Execution helpers
	"build_objective_call",
	# DAG structures and validation
	"DagDefinition",
	"DagNode",
	"DagEdge",
	"DagNodeType",
	"TopologicalOrder",
	"CycleDetectionResult",
	"DagValidator",
	"topological_sort",
	"detect_cycles",
	# ExecutionEngines and Contexts
	"BranchContext",
	"StageContext",
	"JobContext",
	"BaseExecutionEngine",
	"BashExecutionEngine",
	"PythonExecutionEngine",
	"ContainerExecutionEngine",
	# DAG Executor
	"DAGExecutor",
	"create_executor_from_config",
]

# Backward compatibility aliases
BaseEvaluator = BaseExecutionEngine
BashEvaluator = BashExecutionEngine
PythonEvaluator = PythonExecutionEngine
ContainerEvaluator = ContainerExecutionEngine
