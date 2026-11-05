# Workflow Notes

See the [workflow guide](../workflows.md) for jobs, objective plans, and ePIC setup.

## Objective Models

| Class | Purpose |
| --- | --- |
| `ObjectiveDefinition` | Objective name, direction, optional plan, and output `metrics_keys`. |
| `ObjectivePlanSpec` | A `steps` specification containing one or more script or inline stages. |
| `CombinedObjectivePlan` | One plan with multiple metric definitions. |
| `CombinedObjectiveMetric` | Metric name, direction, and `metric_key` to extract from the plan output. |

## Stack Registration and Geometry Preparation

`StackRegistry` maps a stack name to its environment, design, problem, workflow, and execution classes.

Before branches execute, `DAGExecutor` calls `prepare_workflow_geometry()` once for a workflow with a `stack_type`, design configuration, and problem configuration.
