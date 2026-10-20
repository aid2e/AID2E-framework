# Workflows and Objectives

This guide documents AID2E's workflow execution and objective specification system.

## Execution Model

A workflow evaluates one design point. It contains branches, each branch contains stages, and each stage contains zero or more jobs. The current executor runs branches in configuration order. Within each branch, stages are treated as a sequential chain: every stage depends on the previous stage. Jobs expanded within one stage are submitted together and may run in parallel through the effective scheduler.

A downstream stage begins only after all jobs in the preceding stage complete successfully. A failed scheduler stage stops the workflow and prevents later stages in that branch from running.

The current workflow model does not expose explicit dependencies between workflow stages. Objective step plans have their own `depends_on` fields and are topologically sorted separately. Although an empty branch list is accepted by the model, the current executor does not create executable stages for an implicit branch; executable workflows should declare their branches and stages.

For each stage, the executor:

1. Expands the configured jobs.
2. Resolves the stage scheduler.
3. Executes all jobs directly or through that scheduler.
4. Collects scheduler outputs and artifacts into the workflow XCom mapping.
5. Executes the stage objective plan, when configured.

After all branches complete, the executor collects the declared objectives and returns them to the optimization loop.

## Jobs and Job Factories

### Job Execution Types

The job `payload.evaluator_type` selects the execution engine. When it is omitted, the job uses command execution.

- **Command/Bash** executes `job.command`; direct execution uses `payload.env` for additional environment variables.
- **Python** uses `evaluator_type: "python"` with `python_callable`. Direct execution expects a callable object and passes `JobContext` first, followed by `op_args` and `op_kwargs`. Scheduler-backed Python jobs forward `op_kwargs`; the workflow adapter currently rejects this evaluator type for Slurm.
- **Container** uses `evaluator_type: "container"` with image, command, environment, volume, and resource settings for direct execution.
- **Stack** uses `evaluator_type: "stack"` with a registered `stack_type` and one or more ordered layers.

### Job Factories

A stage can execute its declared jobs directly or expand the first job as a template through `job_factory`. The current executor implements two factory types: `range` and `payloads`. Other names described by the model are not implemented and raise `ValueError`.

The `range` factory creates `n` deep copies of the first job. Each copy is named `<template_name>_<index>` and receives `job_index` in its payload:

```yaml
job_factory:
  type: "range"
  params:
    n: 4
```

The `payloads` factory calls a Python function referenced as `module.path:function_name`. The function receives `stage_id`, `problem_config`, and `workflow_context` and must return a list of mappings. One deep-copied job is created for each mapping, and that mapping is merged into the template payload:

```yaml
job_factory:
  type: "payloads"
  params:
    from: "workflow_utils:simulation_payloads"
```

Because expansion deep-copies the template job, stack layer definitions are preserved for every generated job. Additional jobs declared after the first template are not expanded when a factory is present.

### Callable Entrypoints

Payload factories and inline objective functions use `module.path:function_name`. The framework imports the module and resolves the named function. Factories receive the stage and workflow context; objective functions receive the design point and objective inputs and outputs. Python job callable support depends on the execution path; direct and JobLib jobs require a callable object.

## Scheduler Cascade

### Overview

Stages inherit scheduler settings in this order:

```
Cascade Precedence (highest to lowest):
  1. Stage-level scheduler (override)
  2. Branch-level scheduler (branch default)
  3. Workflow-level scheduler (workflow default)
  4. Global scheduler (global default)
```

The top-level `scheduler` is used as the global default when present; otherwise, `workflows.global_scheduler` is used. An objective-level scheduler is reserved in the schema but raises an error in the current runtime. Scheduled objective work must be represented as a workflow stage.

### Example

Illustrative scheduler overrides (add an optimizer and evaluator for a complete run):

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

For `evaluate`, the stage-level `SlurmRunner` overrides the branch default. A stage without its own scheduler uses the branch's `JobLibRunner` with `n_jobs=2`.

## Stack Jobs and EpicStack

The stack interface allows a workflow job to execute one or more ordered layers of a registered experimental software stack. The ePIC implementation is registered as `epic`.

A stack workflow declares `stack_type`, while each stack job declares `evaluator_type: "stack"` and one or more `layers`. A job-level `stack_type` can override the workflow value. Missing or unknown stack types and missing layer configurations raise errors.

This layer fragment requires the ePIC environment and design configuration:

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

Layers execute in their listed order within one job. Inputs, outputs, arguments, commands, and rules support templates resolved from the job context.

### EpicStack

```python
from aid2e.utilities.epic_utils import EpicStack
```

`EpicStack` provides four layers:

- `geo` runs `checkOverlaps`. It requires one geometry input and one log output, and exits with code 9 unless the log reports zero illegal overlaps or extrusions.
- `sim` runs `npsim` and formats generator, HepMC, macro, and output arguments.
- `rec` runs `eicrecon` and formats reconstruction inputs and podio output arguments.
- `ana` runs a user-provided analysis command and rule.

Geometry is prepared once per trial before branches execute. In `no_build` mode, EpicStack copies `<epic_install>/share/epic` into the workflow output under `geometry/epic`, applies the design-point XML modifications, and uses that copy as `DETECTOR_PATH`. In `build` mode, it copies the configured geometry source, applies the modifications, and builds and installs that workflow copy.

Generated ePIC driver scripts use `set -euo pipefail`, initialize the selected geometry, and run through `EIC_SINGULARITY_IMAGE` or `EIC_SHELL`. The workflow therefore requires a valid ePIC environment configuration and an ePIC design configuration. See the [dRICH example](https://github.com/aid2e/AID2E-framework/tree/main/examples/drich) for a complete `geo`, `sim`/`rec`, and `ana` workflow, and the [BIC example](https://github.com/aid2e/AID2E-framework/tree/main/examples/bic) for another ePIC detector workflow.

The current full-config loader selects stack-specific workflow models when a workflow declares `stack_type`. A `WorkflowsConfiguration` should currently use one registered stack type; mixed stacks in one workflow collection are not yet supported reliably.

## Objective Plans

### Objective Collection

Objectives can be returned in three ways:

1. A job returns declared objective names directly in a mapping, an `objectives` mapping, or individual output keys.
2. A stage-level objective plan runs after that stage's jobs and stores its extracted metrics in XCom.
3. An objective-level or combined objective plan runs during final objective collection.

Objective plans execute locally inside the trial's `DAGExecutor`, even when workflow jobs use a remote scheduler. Their `StepStage` objects are separate from workflow `StageDefinition` objects and do not use the scheduler cascade.

- Inline steps receive `design_point`, `inputs`, `outputs`, `extra_args`, `xcom`, `work_dir`, `output_dir`, `problem_config`, and `workflow_context`. Trial metadata is available through `workflow_context`.
- Script steps receive design-point and step-input JSON files, run the configured executable, and read its JSON output. Parameter and output paths are passed through command arguments and environment variables.
- Dependencies determine execution order. Their results are passed to downstream steps through the input mapping. `produces_from_stage` selects the plan result.

A stage-level plan must return all objectives declared for the workflow. A single-objective plan extracts its one `metrics_keys` entry, or defaults to the objective name. Optional uncertainty values use `<objective_name>_err`.

In a full configuration, declare objectives under `problem.objectives` only; duplicated `workflows[].objectives` declarations are rejected.

See [workflow notes](notes/workflows.md) for objective model classes, stack registration, and geometry preparation internals.

Objective-level and combined-plan `scheduler` fields are reserved but unsupported by the executor. Use a workflow stage for scheduled objective work.

### Single-Step and Multi-Step Plans

All objective plans use `steps`, with one stage or several dependent stages.

Example (single script stage):

```python
from aid2e.utilities.configurations.objectives import (
    ObjectiveDefinition, ObjectiveDirection, ObjectivePlanSpec,
    ScriptObjective, StepPlanSpec, StepStage,
)

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

## Combined Objectives

### Motivation

Sometimes a single computation produces **multiple objective metrics**. For example:
- A DTLZ2 evaluation script outputs both `f1` and `f2`
- A surrogate model prediction outputs multiple target values
- A simulation produces both efficiency and quality scores

Instead of running the same plan twice, **combined objectives** allow one execution to produce multiple metrics.

### Usage in Workflows

Add `combined_objectives` to a workflow. This illustrative fragment requires matching declarations in `problem.objectives` and a script that returns all three metrics:

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
                    path: "scripts/evaluate_metrics.py"
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

The objective plan script should output a JSON file with the metric values:

```json
{
  "f1": 0.45,
  "f2": 0.67,
  "efficiency": 0.92
}
```

Each key in this object becomes extractable via `metric_key` in `CombinedObjectiveMetric`.

In full configurations, combined metrics should match `problem.objectives`, which supplies the optimizer's objective names and directions. `metric_key` controls how output keys map to those names.

## Step Plans

### Structure

A step plan contains one or more stages, each with a distinct computation:

```python
from aid2e.utilities.configurations.objectives import (
    ObjectiveDefinition, ObjectiveDirection, ObjectivePlanSpec,
    ScriptObjective, StepPlanSpec, StepStage,
)

ObjectiveDefinition(
    name="complex_eval",
    direction=ObjectiveDirection.MINIMIZE,
    objective_plan=ObjectivePlanSpec(
        steps=StepPlanSpec(
            stages=[
                StepStage(
                    name="preprocess",
                    script=ScriptObjective(path="preprocess.py", output_file="prep.json"),
                    inputs={"design_file": "design_params.json"},
                    outputs={"prepared_file": "preprocessed.json"},
                    produces_objective=False,
                ),
                StepStage(
                    name="evaluate",
                    script=ScriptObjective(path="evaluate.py", output_file="eval.json"),
                    depends_on=["preprocess"],
                    inputs={"prepared_file": "preprocessed.json"},
                    outputs={"metrics_file": "objectives.json"},
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
- `inputs` (Dict[str, Any]): Named input bindings
- `outputs` (Dict[str, Any]): Named output bindings
- `extra_args` (Dict[str, Any]): Additional arguments to pass to the stage
- `produces_objective` (bool): Whether this stage produces the objective value
- `depends_on` (List[str]): Names of preceding stages this depends on

### Validation

The model automatically validates:
- **Mutual exclusivity**: Each stage has exactly one of `script` or `inline`
- **Unique names**: All stage names are unique within a plan
- **Single producer**: Select `produces_from_stage`, or mark exactly one stage with `produces_objective=True`
- **Dependency satisfaction**: All dependencies reference existing stages

At execution, steps are topologically sorted and cycles are rejected. Results from dependencies are supplied to downstream steps through their input mapping.

## Outputs and Failures

For `aid2e optimize`, the configured output and work locations contain one directory per run:

```text
<output_location>/<run-id>/
|-- optimization_results.json
|-- pareto_front.json
`-- trials/
    `-- trial_<index>/
        |-- log/
        |-- <stage>/<job>/
        `-- geometry/epic/        # EpicStack no_build geometry

<work_location>/<run-id>/
`-- trials/
    `-- trial_<index>/
        |-- _scheduler/<stage>/
        |-- _objectives/<plan>/<step>/
        `-- <stage>/<job>/
```

Each job receives a work directory at `<work_dir>/<stage>/<job>` and an output directory at `<output_dir>/<stage>/<job>`. The workflow also creates a shared `log` directory. Direct job return values are pushed to XCom. For scheduler jobs, collected outputs, standard output, standard error, and artifacts are stored in the workflow XCom mapping for downstream stages and objective collection.

For command jobs, `job.outputs` describes scheduler-collected artifacts, with paths resolved against the runtime context. Collection depends on the runner; JobLib reads existing declared files as text. `StageDefinition.outputs` is not separately collected by the executor. Stack-layer `outputs` construct the layer commands; the current scheduler adapter does not automatically inventory them.

Workflow checkpoints record stage and job completion or failure. See [run records](cli.md#run-records) for saved optimization results.

The executor requires every declared objective. Missing metrics, invalid JSON, non-numeric values, nonzero job return codes, and failed scheduler stages are workflow errors. Direct objective collection currently visits XCom values in insertion order, so repeated objective keys can overwrite earlier values rather than raising an error; workflows with multiple producers should use an explicit aggregation plan.

Workflow errors propagate to the optimization loop. The problem's `evaluation_config.trial_failure_policy` then determines whether the optimizer marks the trial as failed or completes it with configured `penalty_objectives`. `max_failed_trials` limits tolerated failed evaluations. The default policy is `fail`, the default `max_failed_trials` is `0`, and the `penalty` policy requires a configured value for every declared objective. Scheduler retry and timeout limitations are documented in the [scheduler guide](schedulers.md#parallelism-and-failure-behavior).

## Examples and API

- [DTLZ2](https://github.com/aid2e/AID2E-framework/blob/main/examples/dtlz2/configurations/dtlz2_ax_constraints.yml): local objective evaluation with JobLib.
- [dRICH](https://github.com/aid2e/AID2E-framework/blob/main/examples/drich/workflow.yml): scheduler cascade, payload factories, EpicStack layers, and objective aggregation.
- [BIC](https://github.com/aid2e/AID2E-framework/tree/main/examples/bic): ePIC detector workflow and environment settings.
- [PanDA examples](https://github.com/aid2e/AID2E-framework/tree/main/examples/dtlz2/schedulers/panda-idds): remote jobs and multistage graphs.
- [Configuration API](../api-reference/utilities.md): workflow and objective models.
