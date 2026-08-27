# Workflows and Objectives

This guide documents AID2E's workflow execution and objective specification system.

## Execution Model

A workflow evaluates one design point. It contains branches, each branch
contains stages, and each stage contains zero or more jobs. The current executor
runs branches in configuration order. Within each branch, stages are treated as
a sequential chain: every stage depends on the previous stage. Jobs expanded
within one stage are submitted together and may run in parallel through the
effective scheduler.

A downstream stage begins only after all jobs in the preceding stage complete
successfully. A failed scheduler stage stops the workflow and prevents later
stages in that branch from running.

The current workflow model does not expose explicit dependencies between
workflow stages. Objective step plans have their own `depends_on` fields and are
topologically sorted separately. Although an empty branch list is accepted by
the model, the current executor does not create executable stages for an
implicit branch; executable workflows should declare their branches and stages.

For each stage, the executor:

1. Expands the configured jobs.
2. Resolves the stage scheduler.
3. Executes all jobs directly or through that scheduler.
4. Collects scheduler outputs and artifacts into the workflow XCom mapping.
5. Executes the stage objective plan, when configured.

After all branches complete, the executor collects the declared objectives and
returns them to the optimization loop.

---

## Jobs and Job Factories

### Job Execution Types

The job `payload.evaluator_type` selects the execution engine. When it is
omitted, the job uses command execution.

- **Command/Bash** executes `job.command`; `payload.env` can supply environment
  variables.
- **Python** uses `evaluator_type: "python"` with `python_callable` and optional
  `op_args` and `op_kwargs`. String callables use
  `module.path:function_name`.
- **Container** uses `evaluator_type: "container"` with image, command,
  environment, volume, and resource settings for direct execution.
- **Stack** uses `evaluator_type: "stack"` with a registered `stack_type` and
  one or more ordered layers.

### Job Factories

A stage can execute its declared jobs directly or expand the first job as a
template through `job_factory`. The current executor implements two factory
types: `range` and `payloads`. Other names described by the model are not
implemented and raise `ValueError`.

The `range` factory creates `n` deep copies of the first job. Each copy is named
`<template_name>_<index>` and receives `job_index` in its payload:

```yaml
job_factory:
  type: "range"
  params:
    n: 4
```

The `payloads` factory calls a Python function referenced as
`module.path:function_name`. The function receives `stage_id`,
`problem_config`, and `workflow_context` and must return a list of mappings. One
deep-copied job is created for each mapping, and that mapping is merged into the
template payload:

```yaml
job_factory:
  type: "payloads"
  params:
    from: "workflow_utils:simulation_payloads"
```

Because expansion deep-copies the template job, stack layer definitions are
preserved for every generated job. Additional jobs declared after the first
template are not expanded when a factory is present.

### Callable Entrypoints

AID2E references Python callables using:

```text
module.path:function_name
```

The framework imports the module and resolves the named function. Callable
entrypoints can be used to execute Python jobs, generate job payloads, or
calculate objectives. The arguments supplied to the function depend on where
the callable is configured: Python jobs use their configured arguments and job
context, payload factories receive the stage and workflow context, and inline
objective functions receive the design point, workflow context, and objective
inputs and outputs.

---

## Scheduler Cascade

### Overview

Instead of a single global scheduler, AID2E now supports **scheduler cascading** at multiple levels:

```
Cascade Precedence (highest to lowest):
  1. Stage-level scheduler (override)
  2. Branch-level scheduler (branch default)
  3. Workflow-level scheduler (workflow default)
  4. Global scheduler (global default)
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
    global_scheduler=global_config.scheduler,
)
```

The top-level `scheduler` is used as the global default when present; otherwise,
`workflows.global_scheduler` is used. An objective-level scheduler is reserved
in the schema but raises an error in the current runtime. Scheduled objective
work must be represented as a workflow stage.

### Example

YAML configuration with scheduler cascade:

```yaml
problem:
  name: "DTLZ2"
  problem_type: "DTLZ2"
  design_parameters_file: "design.params"
  objectives:
    - name: "f1"
      direction: "minimize"

# Global/workflow-level scheduler
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 8
    backend: "loky"

workflows:
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

```

### Precedence Resolution

For the `evaluate` stage in the above example:
1. Check stage-level scheduler → Found: `SlurmRunner`
2. This is the effective scheduler for the stage

For a stage without explicit scheduler:
1. Check stage-level scheduler → Not found
2. Check branch-level scheduler → Found: `JobLibRunner` with `n_jobs=2`
3. This is the effective scheduler for the stage

---

## Stack Jobs and EpicStack

The stack interface allows a workflow job to execute one or more ordered layers
of a registered experimental software stack. `StackRegistry` maps a stack name
to its environment, design, problem, workflow, and execution classes. The ePIC
implementation is registered as `epic`.

A stack workflow declares `stack_type`, while each stack job declares
`evaluator_type: "stack"` and one or more `layers`. A job-level `stack_type` can
override the workflow value. Missing or unknown stack types and missing layer
configurations raise errors.

```yaml
workflows:
  workflows:
    - name: "epic_workflow"
      stack_type: "epic"
      branches:
        - name: "main"
          stages:
            - name: "sim_rec"
              jobs:
                - name: "epic_sim_rec"
                  payload:
                    evaluator_type: "stack"
                  layers:
                    - layer: "sim"
                      inputs: []
                      outputs: ["sim.root"]
                      arguments: ["-N 100"]
                    - layer: "rec"
                      inputs: ["sim.root"]
                      outputs: ["reco.root"]
```

`StackExecutionEngine` resolves templates in each layer's inputs, outputs,
arguments, command, and rule; writes one driver script for the job; and executes
the configured layers in their listed order. Layer inputs, outputs, and
arguments are also pushed to XCom for downstream access. Stack jobs can run
directly or be converted into commands for scheduler-backed stages.

### EpicStack

```python
from aid2e.utilities.epic_utils import EpicStack
```

`EpicStack` provides four layers:

- `geo` runs `checkOverlaps`. It requires one geometry input and one log output,
  and exits with code 9 unless the log reports zero illegal overlaps or
  extrusions.
- `sim` runs `npsim` and formats generator, HepMC, macro, and output arguments.
- `rec` runs `eicrecon` and formats reconstruction inputs and podio output
  arguments.
- `ana` runs a user-provided analysis command and rule.

Before branches execute, `DAGExecutor` calls `prepare_workflow_geometry()` once
for a workflow with a `stack_type`, design configuration, and problem
configuration. In `no_build` mode, EpicStack copies
`<epic_install>/share/epic` into the workflow output under `geometry/epic`,
applies the design-point XML modifications, and uses that copy as
`DETECTOR_PATH`. In `build` mode, it copies the configured geometry source,
applies the modifications, and builds and installs that workflow copy.

Generated ePIC driver scripts use `set -euo pipefail`, initialize the selected
geometry, and run through `EIC_SINGULARITY_IMAGE` or `EIC_SHELL`. The workflow
therefore requires a valid ePIC environment configuration and an ePIC design
configuration. See the [dRICH example](https://github.com/aid2e/AID2E-framework/tree/main/examples/epic/drich) for a
complete `geo`, `sim`/`rec`, and `ana` workflow.

The current full-config loader selects stack-specific workflow models when a
workflow declares `stack_type`. A `WorkflowsConfiguration` should currently use
one registered stack type; mixed stacks in one workflow collection are not yet
supported reliably.

---

## Objective Collection

Objectives can be returned in three ways:

1. A job returns declared objective names directly in a mapping, an
   `objectives` mapping, or individual output keys.
2. A stage-level objective plan runs after that stage's jobs and stores its
   extracted metrics in XCom.
3. An objective-level or combined objective plan runs during final objective
   collection.

Objective plans execute locally inside `DAGExecutor`. An inline step calls a
configured Python function with `design_point`, `inputs`, `outputs`,
`extra_args`, `xcom`, `work_dir`, `output_dir`, `problem_config`, and
`workflow_context`. Trial metadata is available through `workflow_context`. A
script step writes design-point and step-input JSON files, supplies the
parameter and output paths through command arguments and environment variables,
runs the configured executable, and reads its JSON output file. Step
dependencies are topologically sorted, and the stage selected by
`produces_from_stage` supplies the plan result. A stage-level plan must return
all objectives declared for the workflow. A single-objective plan extracts its
one declared `metrics_keys` entry or defaults to the objective name. Optional
uncertainty values use the `<objective_name>_err` key.

An objective plan represents the executable specification of how to compute an objective value.

Objective-plan `StepStage` objects are separate from workflow `StageDefinition`
objects. Objective-plan steps execute locally inside `DAGExecutor` and do not
use the workflow scheduler cascade.

### Key Classes

- **`ObjectiveDefinition`**: Top-level objective specification
  - `name` (str): Objective name (e.g., "f1", "f2")
  - `direction` (ObjectiveDirection): MINIMIZE or MAXIMIZE
  - `objective_plan` (ObjectivePlanSpec): How to compute this objective
  - `scheduler` (Optional[SchedulerConfiguration]): Reserved; objective-level scheduler execution is not currently supported
  - `metrics_keys` (List[str]): Key to extract from objective output; a single-objective plan must resolve to exactly one key

- **`ObjectivePlanSpec`**: Canonical specification for computing an objective
  - Uses `steps`: `StepPlanSpec` with one or more stages
  - Each stage defines either:
    - `script`: Path to executable script
    - `inline`: Entrypoint to Python function

In a full configuration, `problem.objectives` is the single source of truth.
`build_workflow_executor_from_config()` copies those definitions to the selected
workflow and rejects duplicated `workflows[].objectives` declarations.

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

### Combined Objectives

#### Motivation

Sometimes a single computation produces **multiple objective metrics**. For example:
- A DTLZ2 evaluation script outputs both `f1` and `f2`
- A surrogate model prediction outputs multiple target values
- A simulation produces both efficiency and quality scores

Instead of running the same plan twice, **combined objectives** allow one execution to produce multiple metrics.

#### Key Classes

- **`CombinedObjectivePlan`**: Bundle of a plan with multiple metric definitions
  - `name` (str): Combined objective name
  - `objective_plan` (ObjectivePlanSpec): The plan to execute
  - `metrics` (List[CombinedObjectiveMetric]): Metrics extracted from the output
  - `scheduler` (Optional[SchedulerConfiguration]): Reserved; combined objective schedulers are not currently supported

- **`CombinedObjectiveMetric`**: A single metric from a combined plan
  - `name` (str): Metric name (e.g., "f1", "f2")
  - `direction` (ObjectiveDirection): MINIMIZE or MAXIMIZE
  - `metric_key` (str): Key to extract from plan output (e.g., "f1" from `{"f1": 0.5, "f2": 0.3}`)

#### Usage in Workflows

Add `combined_objectives` to a `WorkflowDefinition`:

```yaml
workflows:
  workflows:
    - name: "dtlz2_multi"

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

```

#### Output Format

The objective plan script should output a JSON file with the metric values:

```json
{
  "f1": 0.45,
  "f2": 0.67
}
```

Each key in this object becomes extractable via `metric_key` in `CombinedObjectiveMetric`.

`combined_objectives` is supported for configurations that use this schema.
In canonical full configurations, the optimizer's objective names and directions
still come from `problem.objectives`; each combined metric should correspond to
one of those declared objectives. The combined plan controls how output keys
are mapped to those declared names. A configured scheduler on a combined plan
raises an error. Use a workflow stage for scheduled aggregation work.

---

### Step Plans

#### Structure

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
                    inputs={"design_params": "design_params.json"},
                    outputs={"preprocessed": "preprocessed.json"},
                    produces_objective=False,
                ),
                StepStage(
                    name="evaluate",
                    script=ScriptObjective(path="evaluate.py", output_file="eval.json"),
                    inputs={"preprocessed": "preprocessed.json"},
                    outputs={"objectives": "objectives.json"},
                    produces_objective=True,  # This stage produces the final objective
                    depends_on=["preprocess"],
                ),
            ],
            produces_from_stage="evaluate",  # Which stage's output is the objective value
        )
    )
)
```

#### StepStage Fields

- `name` (str): Stage name (must be unique within a plan)
- `script` or `inline` (exactly one): The execution mode
  - `script`: Path to executable script
  - `inline`: Python function entrypoint
- `inputs` (Dict[str, Any]): Input bindings for the stage
- `outputs` (Dict[str, Any]): Output bindings for the stage
- `extra_args` (Dict[str, Any]): Additional arguments to pass to the stage
- `produces_objective` (bool): Whether this stage produces the objective value
- `depends_on` (List[str]): Names of preceding stages this depends on

#### Validation

The model automatically validates:
- **Mutual exclusivity**: Each stage has exactly one of `script` or `inline`
- **Unique names**: All stage names are unique within a plan
- **Single producer**: Exactly one stage marks `produces_objective=True` when
  `produces_from_stage` is omitted
- **Dependency satisfaction**: All dependencies reference existing stages

The executor topologically sorts the objective steps before execution and
rejects cyclic dependencies at runtime.

---

## Outputs and Failures

For `aid2e optimize`, the configured output and work locations contain one
directory per run:

```text
<output_location>/<run-id>/
|-- optimization_results.json
|-- pareto_front.json
`-- trials/
    `-- trial_<index>/
        |-- log/
        |-- <stage>/<job>/
        `-- geometry/                 # Stack workflows when prepared

<work_location>/<run-id>/
`-- trials/
    `-- trial_<index>/
        |-- _scheduler/<stage>/
        |-- _objectives/<plan>/<step>/
        `-- <stage>/<job>/
```

When a standalone `DAGExecutor` is created without explicit output and work
directories, it creates `<workflow>/<timestamp>` directories below the problem
output and work locations. Without a problem configuration, it uses
`base_output_dir` for both.

Each job receives a work directory at `<work_dir>/<stage>/<job>` and an output
directory at `<output_dir>/<stage>/<job>`. The workflow also creates a shared
`log` directory. Direct job return values are pushed to XCom. For scheduler
jobs, collected outputs, standard output, standard error, and artifacts are
stored in the workflow XCom mapping for downstream stages and objective
collection.

For command jobs, `job.outputs` describes scheduler-collected artifacts and its
paths are resolved against the runtime context. `StageDefinition.outputs` is
accepted by the configuration model but is not separately collected by the
current executor. Stack-layer `outputs` are used to construct layer commands;
they are not automatically converted into scheduler artifact specifications, so
downstream code should use their configured paths explicitly.

The executor requires every declared objective. Missing metrics, invalid JSON,
non-numeric values, nonzero job return codes, and failed scheduler stages are
workflow errors. Direct objective collection currently visits XCom values in
insertion order, so repeated objective keys can overwrite earlier values rather
than raising an error; workflows with multiple producers should use an explicit
aggregation plan.

Workflow errors propagate to the optimization loop. The problem's
`evaluation_config.trial_failure_policy` then determines whether the optimizer
marks the trial as failed or completes it with configured
`penalty_objectives`. `max_failed_trials` limits tolerated failed evaluations.
The default policy is `fail`, the default `max_failed_trials` is `0`, and the
`penalty` policy requires a configured value for every declared objective.
Scheduler retry and timeout limitations are documented in the
[scheduler guide](schedulers.md#parallelism-and-failure-behavior).

---

## Examples

Current full-configuration examples include:

- [DTLZ2](https://github.com/aid2e/AID2E-framework/blob/main/examples/dtlz2/dtlz2_optimization.yml): one-stage
  objective evaluation with JobLib.
- [dRICH](https://github.com/aid2e/AID2E-framework/blob/main/examples/epic/drich/workflow.yml): scheduler cascade, payload job
  factories, EpicStack stages, and objective aggregation.

### Multi-Step Objective Plan

```python
# Three-stage pipeline: preprocess → evaluate → aggregate
ObjectivePlanSpec(
    steps=StepPlanSpec(
        stages=[
            StepStage(
                name="preprocess",
                script=ScriptObjective(path="preprocess.py", output_file="prep.json"),
                inputs={"raw_design": "raw_design.json"},
                outputs={"design_preprocessed": "design_preprocessed.json"},
                produces_objective=False,
            ),
            StepStage(
                name="evaluate",
                script=ScriptObjective(path="evaluate.py", output_file="eval.json"),
                inputs={"design_preprocessed": "design_preprocessed.json"},
                outputs={"raw_objectives": "raw_objectives.json"},
                produces_objective=False,
                depends_on=["preprocess"],
            ),
            StepStage(
                name="aggregate",
                inline=InlineObjective(entrypoint="my_module:aggregate_objectives"),
                inputs={"raw_objectives": "raw_objectives.json"},
                outputs={"final_objectives": "final_objectives.json"},
                produces_objective=True,
                depends_on=["evaluate"],
            ),
        ],
        produces_from_stage="aggregate",
    )
)
```

---

## Developer Reference

### Workflow Features

1. **Objective collection**: Supports direct outputs and inline or script-based objective plans.
2. **Scheduler cascade**: Allows both global consistency and local overrides.
3. **Combined objectives**: Avoid redundant computations.
4. **Step plans**: Support dependent operations within a single objective.
5. **Validation**: Rejects invalid dependencies, actions, and objective producers.

---

### DATA FLOW (Workflow Execution)

User Config (YAML)
    -> Full Config Parser (load_config)
    -> FullConfig Object
        |-- problem (ProblemConfiguration with objectives)
        |-- optimizer (OptimizerConfiguration)
        |-- scheduler (optional global SchedulerConfiguration)
        `-- workflows (WorkflowsConfiguration)

    -> Build Optimizer and Global Scheduler
    -> Suggest Candidate Batch
    -> Execute One Workflow per Trial
        `-- WorkflowDefinition
            `-- BranchDefinition[]
                `-- StageDefinition[] (sequential)
                    |-- JobDefinition[] (parallel within a stage)
                    |-- SchedulerConfiguration
                    `-- StageExecutionResult

    -> Collect Objectives
        |-- Direct values returned by jobs
        |-- Inline objective-plan function
        `-- Script objective plan

    -> Update Completed, Penalized, or Failed Trials
    -> Save Optimization Results and Pareto Front
    -> Suggest Next Candidate Batch

### Key Integration Points

1. Objectives
ProblemConfiguration.objectives -> ObjectiveDefinition[]
The optimizer uses the declared objective names and directions
The workflow returns or calculates values for those declared objectives

2. Workflow Execution
Stages execute sequentially within a branch
Jobs within a stage are submitted together
Range and payload job factories support job fan-out

3. Stack Registry
Generic workflow code resolves stack configuration through StackRegistry
EpicStack supplies geo, sim, rec, and ana layer behavior

### Questions & Support

For more information:
- See the [API reference](../api-reference/utilities.md) for detailed API docs
- Check the [workflow integration tests](https://github.com/aid2e/AID2E-framework/tree/main/tests/test_utilities/test_workflows) for integration tests
- Review the [DTLZ2](https://github.com/aid2e/AID2E-framework/blob/main/examples/dtlz2/dtlz2_optimization.yml) and
  [dRICH](https://github.com/aid2e/AID2E-framework/blob/main/examples/epic/drich/workflow.yml) YAML examples for current usage
