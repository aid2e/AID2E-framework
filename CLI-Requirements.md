# AID2E CLI Requirements

## Purpose

The AID2E framework should be runnable from the command line using configuration files only. A user should be able to define the problem, design space, optimizer, scheduler, workflow, runtime parameters, and output behavior in YAML/JSON configuration, then launch optimization with a CLI command such as:

```bash
aid2e optimize config.yml
```

The CLI should not require users to write Python driver scripts for standard supported workflows such as DTLZ2 with Ax or PyMOO using JobLib, Slurm, or PanDAiDDS runners.

## Current Configuration Status

The current canonical full configuration model is centered on:

- `problem`: problem metadata, objective definitions, output/work locations, and design-space source.
- `optimizer`: optimizer backend selection and backend-specific runtime parameters.
- `scheduler`: optional scheduler/runner selection and runner-specific parameters.
- `workflows`: optional workflow definitions wrapped as `workflows: { workflows: [...] }`.

The current loader intentionally rejects several legacy shapes:

- `optimization` top-level section is retired; use top-level `optimizer`.
- `problem.type` is retired; use `problem.problem_type`.
- `problem.design_space` is retired; use `problem.design_parameters_file` or `problem.inline_design`.
- `design_constraints` is retired; use `parameter_constraints`.
- Nested scheduler runner blocks such as `scheduler.joblib`, `scheduler.slurm`, or `scheduler.panda` are retired; use `scheduler.parameters`.
- Legacy top-level `workflow` is retired; use `workflows: { workflows: [...] }`.
- Legacy objective `minimize` keys are retired; use `direction`.

The optimizer and scheduler runtime builders already exist, but the main CLI execution path does not yet wire them into a generic optimization loop.

## PR #57 Coordination

This plan assumes PR #57, "Resolve config issues", is the configuration baseline for CLI work. The CLI PR should build on that work and avoid reimplementing or reverting it.

PR #57 covers:

- `SchedulerConfigLoader` for YAML/JSON scheduler sections.
- validation of JobLib, Slurm, and PanDAiDDS scheduler parameters.
- canonical scheduler shape using `scheduler.parameters`.
- Slurm inline parameters and JSON template loading.
- scheduler docs and basic examples migrated away from legacy nested runner blocks.
- ePIC problem payloads returning specialized `EpicProblemConfiguration`.
- scheduler cascade resolution through the runtime builder and `DAGExecutor`.
- `create_executor_from_config` loading canonical full configs and building a configured executor.
- updated PanDAiDDS tests and source directory defaults.

Remaining CLI work should therefore focus on the execution layer:

- call the existing config loaders/builders from `aid2e optimize`;
- build optimizer and evaluator/executor instances from the loaded config;
- run the optimizer ask/tell loop;
- persist outputs and run metadata;
- add CLI-facing validation, inspection, and execution tests.

PR #57 does not change `src/aid2e/cli/workflow_commands.py` and does not add a generic optimizer execution loop using `suggest_candidates(...)` and `update_with_results(...)`. Those pieces remain in scope for the CLI execution PR.

Open PR #57 review questions that affect CLI planning:

- Clarify the relationship between objective-level `computation.multi_steps` and top-level `workflows`.
- Decide whether the public objective-plan key remains `multi_steps` or should become `steps`.
- Keep useful scheduler validation errors for typos or unsupported `runner_type` values.
- Consider whether PanDA `init_env` should support an explicit ordered list of setup commands.

## Source TODO Traceability

This requirements document is anchored to the open TODO in `src/aid2e/cli/workflow_commands.py` at the `aid2e optimize` command. The referenced TODO states that actual optimization execution must:

1. instantiate the optimizer from `config.optimizer`;
2. set up the problem evaluator from `config.problem`;
3. run the optimization loop;
4. save results to `config.problem.output_location`.

The CLI implementation plan must satisfy those four points first. Additional lifecycle commands, richer status tracking, template generation, and scheduler cascade behavior should be treated as follow-on work unless needed to make the first end-to-end CLI optimization path reliable.

## Canonical Config Requirements

### Full Config

A CLI-runnable optimization config must contain:

```yaml
problem:
  name: "DTLZ2 Optimization"
  problem_type: "DTLZ2"
  output_location: "./output"
  work_location: "./work"
  design_parameters_file: "./design.params"
  objectives:
    - name: "f1"
      direction: "minimize"
    - name: "f2"
      direction: "minimize"

optimizer:
  name: "ax"
  type: "bayesian"
  parameters:
    n_initial_samples: 10
    n_iterations: 20
    batch_size: 4
    seed: 42

scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: -1
    backend: "loky"
```

Optional sections:

- `workflows`: for config-driven objective evaluation.
- `problem.environment_config` or stack-specific environment blocks.
- `problem.observations`: prior observations or initial data.
- scheduler cascade overrides at workflow, branch, stage, objective, or stage-plan level, using the PR #57 runtime-builder cascade behavior as the baseline.

### Problem Section

The `problem` section must define:

- `name`: human-readable run/problem name.
- `problem_type`: supported problem identifier such as `DTLZ2`, `EPIC_B0`, `EPIC_TRACKING`, or another registered problem.
- `output_location`: final results directory.
- `work_location`: runtime scratch/work directory.
- exactly one of:
  - `design_parameters_file`
  - `inline_design`
- `objectives`: non-empty list of objective definitions.

Objective definitions must use:

```yaml
objectives:
  - name: "f1"
    direction: "minimize"
  - name: "f2"
    direction: "maximize"
```

If objectives require external computation, the config must define either objective computation plans or a workflow capable of producing the configured objective names.

The CLI implementation should avoid introducing another evaluator schema until the `computation.multi_steps` versus top-level `workflows` relationship is settled. A practical initial rule is:

- use `problem.objectives[].computation.multi_steps` for objective-local execution plans;
- use top-level `workflows` for reusable or scheduler-rich DAG execution;
- do not require both for the same objective unless a later design explicitly defines how one references the other.

### Design Space

Design-space files or inline design blocks must use canonical `design_space`:

```yaml
design_space:
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1:
          value: 0.5
          bounds: [0.0, 1.0]
  parameter_constraints:
    - name: "sum_constraint"
      rule: "DTLZ2_variables.x1 + DTLZ2_variables.x2 <= 1.5"
```

The CLI must preserve:

- grouped parameter names such as `DTLZ2_variables.x1`;
- range parameters;
- choice parameters;
- parameter constraints;
- optimization groups.

### Optimizer Section

The `optimizer` section must define:

- `name`: backend name, currently `ax` or `pymoo`.
- `type`: optimizer family, for example `bayesian` or `evolutionary`.
- `parameters`: backend-specific settings.

For Ax, supported parameters include:

- `initialization_strategy`
- `generator`
- `generator_kwargs`
- `generator_gen_kwargs`
- `objective_thresholds`
- `n_initial_samples`
- `n_iterations`
- `batch_size`
- `seed`

For PyMOO, supported parameters include:

- `algorithm`
- `pop_size`
- `n_offsprings`
- `crossover_prob`
- `crossover_eta`
- `mutation_eta`
- `n_iterations`
- `n_partitions`
- `seed`
- `verbose`

The CLI must validate backend-specific parameters through the optimizer registry before execution.

### Scheduler Section

The `scheduler` section must define:

- `runner_type`: one of `JobLibRunner`, `SlurmRunner`, or `PanDAiDDSRunner`.
- `parameters`: runner-specific settings.
- optional common fields:
  - `max_retries`
  - `output_location`
  - `monitor_interval`

JobLib example:

```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: -1
    backend: "loky"
    timeout: 3600
    verbose: 1
```

PanDAiDDS example:

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    cloud: "US"
    queue: "BNL_PanDA_1"
    max_walltime: 3600
    core_count: 1
    total_memory: 4000
```

The CLI must validate runner-specific parameters through the scheduler registry before execution.

### Workflow Section

The canonical workflow wrapper is:

```yaml
workflows:
  workflows:
    - name: "dtlz2_eval"
      branches:
        - name: "main"
          stages:
            - name: "evaluate"
              jobs:
                - name: "compute_dtlz2"
                  command: "python examples/complete/scripts/slurm_dtlz2_from_cli.py"
                  rule: "{command} --input {design_file} --output {output_dir}/objectives.json"
                  outputs:
                    - path: "{output_dir}/objectives.json"
                      format: "json"
```

Requirements:

- Full-config workflows must not repeat `workflows[].objectives` when `problem.objectives` is present as the source of truth.
- CLI must select a workflow by name when multiple workflows exist.
- CLI must support a default workflow selection when exactly one workflow exists.
- Workflow execution must receive optimizer-generated design points.
- Workflow execution must return metrics matching `problem.objectives`.

## CLI Command Requirements

### `aid2e validate`

Must validate:

- YAML/JSON syntax.
- canonical full config shape.
- problem section.
- design-space loading and constraints.
- objective definitions.
- optimizer backend-specific parameters.
- scheduler runner-specific parameters.
- workflow wrapper and workflow definitions.
- relative path resolution from the config file directory.

Validation should fail with actionable errors and non-zero exit codes.

### `aid2e describe`

Must summarize:

- problem name and type;
- output/work directories;
- design source and parameter count;
- objective names and directions;
- optimizer backend and iteration settings;
- scheduler runner type and key parameters;
- workflow names when present.

### `aid2e inspect`

Must provide detailed views for:

- `problem`
- `design`
- `optimizer`
- `scheduler`
- `workflows`
- `all`

Current section support should be expanded beyond `problem`, `design`, and `optimizer`.

### `aid2e optimize`

Must run a full optimization from config only.

Required execution flow:

1. Load canonical full config.
2. Validate optimizer and scheduler parameters.
3. Ensure output/work directories exist or create them according to CLI policy.
4. Build optimizer from config.
5. Build scheduler/workflow executor from config when workflows are present.
6. Resolve built-in evaluator when `problem_type` has a built-in implementation such as DTLZ2.
7. Repeatedly call `optimizer.suggest_candidates(...)`.
8. Evaluate candidate design points through the configured evaluator/workflow/scheduler.
9. Validate returned metrics against configured objective names.
10. Call `optimizer.update_with_results(...)`.
11. Persist trial state, metrics, logs, and result summaries.
12. Emit final best trial or Pareto front summary.

The command should support:

- `--validate-only`
- `--dry-run`
- `--workflow <name>`
- `--output <path>` override
- `--work-dir <path>` override
- `--run-id <id>`
- `--resume <checkpoint>`
- `--log <path>`
- `-v/--verbosity`

### Future Lifecycle Commands

The planned commands should be implemented around persisted run metadata:

- `aid2e run`: alias or broader workflow execution entrypoint.
- `aid2e resume`: continue from optimizer/checkpoint state.
- `aid2e status`: inspect run progress and recent trials.
- `aid2e stop`: gracefully stop active/asynchronous runs where supported.
- `aid2e clean`: remove runtime artifacts with dry-run support.
- `aid2e init`: generate canonical config templates.
- `aid2e graph`: visualize workflow structure.

## Execution Requirements

### Optimizer Loop

The CLI must use the existing ask/tell optimizer interface:

- `suggest_candidates(...)`
- `update_with_results(...)`
- `get_trials()`
- `get_best_trial()`
- `get_pareto_front()`

The loop must handle differences between Ax and PyMOO:

- Ax uses configurable batch size and initial samples.
- PyMOO candidate count is governed by population/generation settings.
- Objective directions must be respected when reporting best trials or Pareto fronts.

### Evaluation

At least two evaluation modes are required:

1. Built-in evaluator mode for supported toy problems such as DTLZ2.
2. Workflow-backed evaluator mode through `DAGExecutor`.

For workflow-backed execution:

- Each optimizer candidate becomes one design point passed to `DAGExecutor.execute`.
- Returned objective metrics must match configured objective names.
- Scheduler-backed workflow stages should run through the configured scheduler.

### Scheduler Integration

The CLI must support:

- local execution through JobLib;
- HPC execution through Slurm;
- distributed execution through PanDAiDDS.

Scheduler selection must come from config, not command-specific Python code.

The CLI should rely on PR #57 scheduler config loading, runner validation, and cascade resolution. It should expose scheduler identity and output paths in logs and summaries.

### Output and Persistence

Each CLI optimization run should write:

- resolved config copy;
- run metadata;
- trial history;
- candidate design points;
- objective metrics;
- optimizer state/checkpoint if backend supports it;
- workflow logs;
- scheduler logs/artifacts;
- final summary;
- Pareto front for multi-objective runs.

Recommended structure:

```text
output_location/
  <run_id>/
    resolved_config.yml
    run.json
    trials.jsonl
    summary.json
    pareto_front.json
    logs/
    artifacts/
```

## Documentation Requirements

The documentation must be aligned with the canonical schema.

Required updates:

- Update CLI docs to reflect current command behavior and planned behavior separately.
- Add canonical examples for:
  - DTLZ2 + Ax + JobLib
  - DTLZ2 + PyMOO + JobLib
  - DTLZ2 + Ax + PanDAiDDS
  - DTLZ2 + PyMOO + PanDAiDDS
  - DTLZ2 + Slurm workflow
- Review examples not touched by PR #57 and either migrate them or mark them as legacy.
- Add a short explanation of how `problem.objectives[].computation.multi_steps` relates to top-level `workflows`.

## Testing Requirements

Required test coverage:

- `aid2e validate` succeeds for canonical full configs.
- `aid2e validate` fails for retired config keys with useful messages.
- `aid2e describe` includes optimizer, scheduler, and workflow information.
- `aid2e inspect --section scheduler` works.
- `aid2e inspect --section workflows` works.
- `aid2e optimize --validate-only` validates backend-specific optimizer and scheduler parameters.
- Minimal DTLZ2 + Ax + JobLib CLI run completes.
- Minimal DTLZ2 + PyMOO + JobLib CLI run completes.
- CLI run writes expected output files.
- CLI run returns non-zero on missing objective metrics.
- Example configs load under tests.

Optional integration tests:

- Slurm workflow dry-run or mocked submission.
- PanDAiDDS config validation and mocked submission.
- Resume from checkpoint.

## Known Gaps

- `aid2e optimize` does not yet implement generic optimizer/workflow execution.
- EPIC_B0 toy optimization is currently special-cased in the CLI.
- Some examples outside the PR #57 scope may still use retired config shapes.
- The relationship between objective-level `multi_steps` and top-level `workflows` is not yet clear enough for CLI users.
- Output/work directory creation policy is not settled.
- CLI tests do not yet exercise real optimization runs.
- PyMOO does not currently enforce design constraints during candidate generation.
- Slurm Python evaluator jobs are explicitly unsupported in the current scheduler path.

## Acceptance Criteria

The CLI work is complete when:

- A user can run DTLZ2 with Ax using only a config file and `aid2e optimize`.
- A user can run DTLZ2 with PyMOO using only a config file and `aid2e optimize`.
- A user can select JobLib or PanDAiDDS runner only by changing config.
- Config validation catches schema and backend parameter errors before execution.
- Generated run outputs are sufficient to inspect results and resume or debug a run.
- Docs and examples match the canonical schema.
- CLI tests cover validation, inspection, and at least one full local optimization run.
