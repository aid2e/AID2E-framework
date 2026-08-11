# Workflow and Objective Improvements Guide

This guide documents the improvements made to AID2E's workflow and objective specification system.

## Table of Contents

1. [Objective Plan Terminology](#objective-plan-terminology)
2. [Scheduler Cascade](#scheduler-cascade)
3. [Combined Objectives](#combined-objectives)
4. [Multi-Step Plans](#multi-step-plans)
5. [Migration Guide](#migration-guide)
6. [Examples](#examples)

---

## Objective Plan Terminology

### What Changed?

The term **"computation"** has been renamed to **"objective_plan"** throughout the codebase for clarity. An objective plan represents the executable specification of how to compute an objective value.

### Key Classes

- **`ObjectiveDefinition`**: Top-level objective specification
  - `name` (str): Objective name (e.g., "f1", "f2")
  - `direction` (ObjectiveDirection): MINIMIZE or MAXIMIZE
  - `objective_plan` (ObjectivePlanSpec): How to compute this objective
  - `scheduler` (Optional[SchedulerConfiguration]): Objective-level scheduler default
  - `metrics_keys` (List[str]): Keys to extract from objective output

- **`ObjectivePlanSpec`**: Canonical specification for computing an objective
  - Uses `steps`: `StepPlanSpec` with one or more stages
  - Each stage defines either:
    - `script`: Path to executable script
    - `inline`: Entrypoint to Python function

### Single-Step and Multi-Step Plans

By design, all objective plans use the same `steps` structure. A simple
objective can define one stage, while more complex objectives can define
multiple dependent stages. This provides:
- Unified handling of simple and complex computations
- Support for preprocessing, evaluation, and postprocessing stages
- Clear separation of concerns

Example (single script stage):

```python
ObjectiveDefinition(
    name="f1",
    direction=ObjectiveDirection.MINIMIZE,
    objective_plan=ObjectivePlanSpec(
        steps=StepPlanSpec(
            stages=[
                StepStage(
                    name="f1_stage_0",
                    script=ScriptObjective(
                        path="scripts/dtlz2.py",
                        output_file="f1.json",
                    ),
                    produces_objective=True,
                )
            ]
        )
    )
)
```

---

## Scheduler Cascade

### Overview

Instead of a single global scheduler, AID2E now supports **scheduler cascading** at multiple levels:

```
Cascade Precedence (highest to lowest):
  1. Stage-level scheduler (override)
  2. Branch-level scheduler (branch default)
  3. Workflow-level scheduler (workflow default)
  4. Objective-level scheduler (objective default)
  5. Global scheduler (global default)
```

This allows fine-grained control while maintaining sensible defaults.

### Cascade Resolution

Use the `resolve_scheduler_cascade()` utility to determine the effective scheduler:

```python
from aid2e.utilities.configurations import resolve_scheduler_cascade

effective_scheduler = resolve_scheduler_cascade(
    stage_scheduler=stage_config.scheduler,
    branch_scheduler=branch_config.scheduler,
    workflow_scheduler=workflow_config.scheduler,
    objective_scheduler=objective_config.scheduler,
    global_scheduler=global_config.scheduler,
)
```

### Example

YAML configuration with scheduler cascade:

```yaml
problem:
  name: "DTLZ2"
  type: "toy"
  design_space:
    path: "design.params"

# Global/workflow-level scheduler
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 8
    backend: "loky"

workflows:
  - name: "dtlz2_eval"
    
    # Workflow-level scheduler (overrides global)
    scheduler:
      runner_type: "JobLibRunner"
      parameters:
        n_jobs: 4
        backend: "threading"
    
    branches:
      - name: "main"
        
        # Branch-level scheduler (overrides workflow)
        scheduler:
          runner_type: "JobLibRunner"
          parameters:
            n_jobs: 2
            backend: "loky"
        
        stages:
          - name: "evaluate"
            
            # Stage-level scheduler (overrides branch)
            scheduler:
              runner_type: "SlurmRunner"
              parameters:
                partition: "gpu"
                nodes: 1
            
            jobs:
              - name: "compute_objective"
                command: "python eval.py"

    objectives:
      - name: "f1"
        direction: "minimize"
        
        # Objective-level scheduler (applies to this objective)
        scheduler:
          runner_type: "JobLibRunner"
          parameters:
            n_jobs: 1
        
        objective_plan:
          steps:
            stages:
              - name: "evaluate_f1"
                script:
                  path: "scripts/dtlz2.py"
                  output_file: "f1.json"
                produces_objective: true
```

### Precedence Resolution

For the objective "f1" in the above example:
1. Check objective-level scheduler → Found: `JobLibRunner` with `n_jobs=1`
2. This is the effective scheduler for objective execution

For a stage without explicit scheduler:
1. Check stage-level scheduler → Not found
2. Check branch-level scheduler → Found: `JobLibRunner` with `n_jobs=2`
3. This is the effective scheduler for the stage

---

## Combined Objectives

### Motivation

Sometimes a single computation produces **multiple objective metrics**. For example:
- A DTLZ2 evaluation script outputs both `f1` and `f2`
- A surrogate model prediction outputs multiple target values
- A simulation produces both efficiency and quality scores

Instead of running the same plan twice, **combined objectives** allow one execution to produce multiple metrics.

### Key Classes

- **`CombinedObjectivePlan`**: Bundle of a plan with multiple metric definitions
  - `name` (str): Combined objective name
  - `objective_plan` (ObjectivePlanSpec): The plan to execute
  - `metrics` (List[CombinedObjectiveMetric]): Metrics extracted from the output
  - `scheduler` (Optional[SchedulerConfiguration]): Scheduler for this plan

- **`CombinedObjectiveMetric`**: A single metric from a combined plan
  - `name` (str): Metric name (e.g., "f1", "f2")
  - `direction` (ObjectiveDirection): MINIMIZE or MAXIMIZE
  - `metric_key` (str): Key to extract from plan output (e.g., "f1" from `{"f1": 0.5, "f2": 0.3}`)

### Usage in Workflows

Add `combined_objectives` to a `WorkflowDefinition`:

```yaml
workflows:
  - name: "dtlz2_multi"
    
    branches:
      - name: "main"
        stages:
          - name: "evaluate"
            jobs:
              - name: "dtlz2"
                command: "python scripts/dtlz2.py"
                outputs:
                  - path: "objectives.json"
                    format: "json"
    
    # Combined objectives: one plan produces multiple metrics
    combined_objectives:
      - name: "dtlz2_pareto"
        
        objective_plan:
          steps:
            stages:
              - name: "evaluate_objectives"
                script:
                  path: "scripts/dtlz2.py"
                  output_file: "objectives.json"
                produces_objective: true
        
        metrics:
          - name: "f1"
            direction: "minimize"
            metric_key: "f1"  # Extract {"f1": ...} from output
          
          - name: "f2"
            direction: "minimize"
            metric_key: "f2"  # Extract {"f2": ...} from output
          
          - name: "efficiency"
            direction: "maximize"
            metric_key: "efficiency"  # Extract {"efficiency": ...}
```

### Output Format

The objective plan script should output a JSON/YAML file with the metric values:

```json
{
  "f1": 0.45,
  "f2": 0.67,
  "efficiency": 0.92
}
```

Each key in this object becomes extractable via `metric_key` in `CombinedObjectiveMetric`.

---

## Step Plans

### Structure

A step plan contains one or more stages, each with a distinct computation:

```python
ObjectiveDefinition(
    name="complex_eval",
    direction=ObjectiveDirection.MINIMIZE,
    objective_plan=ObjectivePlanSpec(
        steps=StepPlanSpec(
            stages=[
                StepStage(
                    name="preprocess",
                    script=ScriptObjective(path="preprocess.py", output_file="prep.json"),
                    inputs=["design_params.json"],
                    outputs=["preprocessed.json"],
                    produces_objective=False,
                ),
                StepStage(
                    name="evaluate",
                    script=ScriptObjective(path="evaluate.py", output_file="eval.json"),
                    inputs=["preprocessed.json"],
                    outputs=["objectives.json"],
                    produces_objective=True,  # This stage produces the final objective
                ),
            ],
            produces_from_stage="evaluate",  # Which stage's output is the objective value
        )
    )
)
```

### StepStage Fields

- `name` (str): Stage name (must be unique within a plan)
- `script` or `inline` (exactly one): The execution mode
  - `script`: Path to executable script
  - `inline`: Python function entrypoint
- `inputs` (List[str]): Input artifacts required
- `outputs` (List[str]): Output artifacts produced
- `extra_args` (Dict[str, Any]): Additional arguments to pass to the stage
- `produces_objective` (bool): Whether this stage produces the objective value
- `depends_on` (List[str]): Names of preceding stages this depends on

### Validation

The model automatically validates:
- **Mutual exclusivity**: Each stage has exactly one of `script` or `inline`
- **Unique names**: All stage names are unique within a plan
- **DAG integrity**: Dependencies form a valid DAG (no cycles)
- **Single producer**: Exactly one stage marks `produces_objective=True`
- **Dependency satisfaction**: All dependencies reference existing stages

---

## Migration Guide

### Old Terminology → New Terminology

| Old Term | New Term | Notes |
|----------|----------|-------|
| "Computation" | "Objective Plan" | More descriptive; plan indicates it's an executable specification |
| `multi_steps` | `steps` | Objective plans now use a neutral name for one or more stages |

### Updating Your Configurations

#### Before (old terminology):

```yaml
objectives:
  - name: "f1"
    direction: "minimize"
    computation:  # Old field name
      script:
        path: "scripts/dtlz2.py"
        output_file: "f1.json"
```

#### After (new terminology):

```yaml
objectives:
  - name: "f1"
    direction: "minimize"
    objective_plan:  # New field name
      steps:
        stages:
          - name: "evaluate_f1"
            script:
              path: "scripts/dtlz2.py"
              output_file: "f1.json"
            produces_objective: true
```

### Python Code Updates

```python
from aid2e.utilities.configurations import ObjectivePlanSpec, StepPlanSpec, StepStage

spec = ObjectivePlanSpec(
    steps=StepPlanSpec(
        stages=[
            StepStage(...),
        ],
    ),
)
```

---

## Examples

### Example 1: Single Objective with Scheduler Cascade

File: [`examples/complete/workflow_example_single_objective.yml`](../examples/complete/workflow_example_single_objective.yml)

Shows:
- Single objective with `objective_plan`
- Scheduler cascade from global → workflow → branch → stage
- Job factory for parameter sweeps
- Clear comments on precedence resolution

### Example 2: Combined Objectives

File: [`examples/complete/workflow_example_combined_objectives.yml`](../examples/complete/workflow_example_combined_objectives.yml)

Shows:
- One plan producing multiple metrics (f1, f2)
- Metric extraction via `metric_key`
- Combined objective in workflow
- Optional scheduler override at combined objective level

### Example 3: Multi-Step Objective Plan

```python
# Three-stage pipeline: preprocess → evaluate → aggregate
ObjectivePlanSpec(
    steps=StepPlanSpec(
        stages=[
            StepStage(
                name="preprocess",
                script=ScriptObjective(path="preprocess.py"),
                inputs=["raw_design.json"],
                outputs=["design_preprocessed.json"],
                produces_objective=False,
            ),
            StepStage(
                name="evaluate",
                script=ScriptObjective(path="evaluate.py"),
                inputs=["design_preprocessed.json"],
                outputs=["raw_objectives.json"],
                produces_objective=False,
            ),
            StepStage(
                name="aggregate",
                inline=InlineObjective(entrypoint="my_module:aggregate_objectives"),
                inputs=["raw_objectives.json"],
                outputs=["final_objectives.json"],
                produces_objective=True,
            ),
        ],
        produces_from_stage="aggregate",
    )
)
```

---

## Summary of Benefits

1. **Clarity**: "Objective plan" is more intuitive than "computation"
2. **Flexibility**: Scheduler cascade allows both global consistency and local overrides
3. **Efficiency**: Combined objectives avoid redundant computations
4. **Composability**: Multi-step plans support complex workflows within a single objective
5. **Backward Compatibility**: Old code continues to work with alias imports

---

## Questions & Support

For more information:
- See [`docs/api-reference/`](../docs/api-reference/) for detailed API docs
- Check [`tests/test_utilities/test_workflows/`](../tests/test_utilities/test_workflows/) for integration tests
- Review [YAML examples](../examples/complete/) for real-world use cases
