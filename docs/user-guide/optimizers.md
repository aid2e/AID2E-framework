# Optimizers

## Overview

`aid2e.optimizers` exposes a shared optimizer interface and two concrete backends: Ax for Bayesian optimization and PyMOO for evolutionary optimization. The package also exports the shared search-space and trial data structures, plus the Pareto utility used by the base implementation.

### Choosing a Backend

- Use **Ax** for Bayesian single- or multi-objective optimization with native support for the constraint forms described below.
- Use **PyMOO** for evolutionary single- or multi-objective optimization with generation-sized candidate batches. PyMOO does not currently enforce design constraints during candidate generation.

## Configuration

The optimizer is selected in the top-level `optimizer` configuration.

Ax configuration:

```yaml
optimizer:
  name: ax
  type: bayesian
  parameters:
    initialization_strategy: sobol
    generator: BOTORCH_MODULAR
    n_initial_samples: 20
    n_iterations: 100
    batch_size: 4
    seed: 42
```

PyMOO configuration:

```yaml
optimizer:
  name: pymoo
  type: evolutionary
  parameters:
    algorithm: nsga2
    pop_size: 20
    n_offsprings: 20
    n_iterations: 5
    seed: 42
```

### Optimization Budget and Outputs

For Ax, `n_iterations` is the total candidate-evaluation budget, including the `n_initial_samples` initialization evaluations, and `batch_size` controls how many candidates are submitted together; it does not multiply the budget. For PyMOO, `n_iterations` is the number of generations; `pop_size` controls the initial generation and `n_offsprings` normally controls later generations.

The CLI saves `optimization_results.json` and `pareto_front.json` after each completed batch. See [run records](cli.md#run-records) for their contents.

Ax initialization strategies are:

- `sobol`: Low-discrepancy sampling designed to cover the search space evenly.
- `uniform`: Independent pseudorandom sampling over each parameter range.
- `center`: One search-space center point followed by Sobol initialization when
  additional initial samples are requested.

If the installed Ax version has no uniform generator, `uniform` falls back to Sobol.

## Shared Behavior

All optimizer backends use the same search-space representation, trial lifecycle, result format, and failure accounting. Backend implementations add candidate generation and state management without changing these shared contracts.

Trials record parameters, objective values, status, and metadata. Results include all recorded trials. The Pareto front includes only completed trials with metrics and respects each objective's `minimize` or `maximize` direction. Failed trials have no objective values; penalized trials have user-configured values that influence optimization.

Objective `<name>_err` values are saved with results, but the current Ax backend attaches observations with zero standard error. PyMOO selects candidates using objective means only.

### Failed and Penalized Trials

`problem.evaluation_config.trial_failure_policy` controls workflow evaluation failures and defaults to `fail`:

- `fail` calls the backend's `mark_trial_failed()` without objective values. Failed trials remain in optimizer history, are excluded from Pareto calculations, and are included in subsequently saved results.
- `penalty` requires a `penalty_objectives` value for every declared objective. The optimizer receives those values through `update_with_results()`, and the completed trial retains `penalized: true` and the failure `reason` in metadata. Choose poor values for each objective's direction; the framework does not derive them automatically.

Both outcomes count toward `max_failed_trials`, which defaults to `0`. The optimization stops when the number of failed evaluations exceeds that configured limit, so the first failure stops the run unless a larger limit is configured.

## Ax Backend

Ax provides Bayesian single- and multi-objective optimization. The backend maps AID2E search spaces and objectives into an Ax experiment, then records each Ax trial in the shared optimizer history.

### Configuration

`AxOptimizerConfig` is the backend config model for the Ax implementation. It is registered under the `ax` name in the optimizer config registry.

Supported fields are:

- `initialization_strategy`: `sobol`, `uniform`, or `center`
- `generator`: currently validated to `BOTORCH_MODULAR`
- `generator_kwargs`: runtime kwargs passed to the Ax generator spec
- `generator_gen_kwargs`: generation-time kwargs passed through to Ax
- `objective_thresholds`: optional multi-objective thresholds by metric name
- `n_initial_samples`
- `n_iterations`
- `batch_size`
- `seed`

`generator_kwargs` accepts supported class names as strings, including model and acquisition choices. `BOTORCH_MODULAR` uses Ax defaults unless those choices are supplied explicitly; defaults can depend on the problem and Ax version. The retired `surrogate_model` and `acquisition_function` fields are rejected; use `generator_kwargs` instead.

`src/aid2e/optimizers/ax/_resolver.py` resolves supported class names for `acquisition_class`, `botorch_acqf_class`, `botorch_acqf_classes_with_options`, and `surrogate_spec`. Supported model, transform, kernel, likelihood, and MLL classes are listed in that module. A surrogate specification can use `model_configs` and per-metric `metric_to_model_configs`.

### Search-space and constraint mapping

Ax converts range parameters to floating-point ranges and choice parameters to string choices. See [constraint enforcement](#constraint-enforcement) for supported rules.

Each objective follows its direction from `problem.objectives`. For multi-objective optimization, `objective_thresholds` defines the hypervolume reference point; these thresholds are not feasibility constraints.

## PyMOO Backend

PyMOO provides evolutionary single- and multi-objective optimization through an external-evaluation ask/tell loop. AID2E schedules each generated population and returns the completed objective values to PyMOO as one generation.

### Configuration

`PyMOOOptimizerConfig` is registered under the `pymoo` name in the optimizer registry. It currently supports:

- `algorithm`: optional explicit algorithm selection
- `pop_size`
- `n_offsprings`
- `crossover_prob`
- `crossover_eta`
- `mutation_eta`
- `n_iterations`
- `n_partitions`
- `seed`
- `verbose`

If `algorithm` is omitted, `resolve_algorithm()` selects `ga` for single-objective problems and `nsga2` otherwise. Explicit algorithms must match the objective count:

- `ga` only for single-objective problems
- `nsga2`, `nsga3`, and `moead` only for multi-objective problems

### Evaluation budget

The actual batch size is determined by the PyMOO algorithm: `pop_size` for the initial generation and normally `n_offsprings` for later generations, with `n_offsprings` defaulting to `pop_size`.

For normal full GA, NSGA-II, and NSGA-III generations, the expected number of candidate evaluations is:

```text
pop_size + (n_iterations - 1) * n_offsprings
```

When `n_offsprings` is omitted, this becomes `n_iterations * pop_size`. MOEA/D uses its reference-direction population and does not consume the configured `n_offsprings` value in the current backend.

### Algorithm mapping

`SBX`, polynomial mutation, and random sampling are used as the default operators. `nsga3` and `moead` build reference directions from `n_partitions` or `pop_size` as appropriate.

## Constraint Enforcement

Use fully qualified parameter names such as `group.x` in `design_space.parameter_constraints`. Configuration validation checks syntax and parameter names; it does not establish support in the selected optimizer.

Ax supports sums and differences of distinct parameters with unit coefficients and nonnegative bounds, using `<=`, `<`, `>=`, and `>`. Weighted terms, products, powers, and negative bounds may be skipped or translated incorrectly. Strict inequalities use a machine-epsilon adjustment. PyMOO currently does not enforce design constraints during candidate generation.

See the [configuration guide](configuration.md#constraint-handling) for YAML, explicit candidate checks with `SearchSpace.validate()`, and conversion details.

## Developer Notes

### Shared Abstractions

`src/aid2e/optimizers/base.py` provides the shared search space, trial history, and result utilities. The package exports `BaseOptimizer`, `SearchSpace`, `Trial`, `compute_pareto_front`, both optimizer classes and their config models, and `PyMOOProblem` (`AID2EProblem` is a deprecated alias).

`SearchSpace` stores parameters, constraints, an optional name, and an optional source configuration. `from_design_config()` flattens parameter groups and forwards their constraints. Parameters can be `BaseParameter` objects or canonical dictionaries with `value` and `bounds` or `choices`; the retired `values` key is rejected.

`Trial` stores `index`, `parameters`, `metrics`, `metadata`, and `status`. Statuses are normalized to lower case: `pending`, `suggested`, `running`, `completed`, `failed`, `aborted`, or `cancelled`. Unknown statuses are retained with a warning.

`BaseOptimizer` accepts a `SearchSpace` or `DesignConfig`, requires a nonempty search space and objective list, and stores the common seed. Backends implement four abstract methods:

- `suggest_candidates()`
- `update_with_results()`
- `serialize_state()`
- `load_state()`

The base class provides `get_trials()`, `set_trial_status()`, `get_optimization_results()`, `save_optimization_results()`, `seed_from_trials()`, `get_pareto_front()`, and `get_best_trial()`.

`get_pareto_front()` uses the shared `compute_pareto_front()` utility. `get_best_trial()` returns the best value for a single objective, or the first Pareto member for multiple objectives. Result exports include raw and display status labels.

`seed_from_trials()` appends trials with new sequential indices and stores their original indices as `source_index` metadata. It updates history only; it does not warm-start an Ax model or a PyMOO population. PyMOO also rejects seeding while a generation is in flight.

### Ax Candidate Lifecycle and State

Ax uses the node-based generation API (`CenterGenerationNode`, `GenerationNode`, `GeneratorSpec`, and `MinTrials`). Initialization is followed by a `Generators.BOTORCH_MODULAR` node.

`suggest_candidates()` makes one generation call for the batch and converts the output to single-arm trials. Each trial is running in Ax and `suggested` in the shared history. The method records the current step or node when available and raises if Ax returns fewer generator runs than requested.

`update_with_results()` checks that all configured objectives are present, attaches their values, and marks the trial completed in Ax and the shared history.

`serialize_state()` stores the search-space parameters and constraints, objective names, seed, config, trials, and trial counter. `load_state()` rebuilds the Ax experiment and generation strategy, then replays completed trials. It does not restore a serialized Ax experiment or fitted model directly.

### PyMOO Candidate Lifecycle and State

`PyMOOProblem` describes the search space for external evaluation. `decode_x()` converts vectors to parameter dictionaries; `_evaluate()` raises `NotImplementedError`. Range parameters remain floats; choice parameters use continuous indices rounded to the nearest valid choice. Other parameter types are not supported.

`suggest_candidates()` calls `algorithm.ask()` and records trials as `pending`. The algorithm determines the batch size; a differing `n_candidates` hint only produces a debug message. `update_with_results()` buffers each result and marks the trial completed. Once the generation is fully reported, `_flush_generation()` calls `algorithm.tell()`. A new generation cannot start while one is in flight.

`serialize_state()` stores the search space, config, objective names, trials, trial counter, generation count, resolved algorithm, and, when possible, a base64-encoded pickle of the algorithm state. `load_state()` restores the pickle or rebuilds the algorithm from config and seed if it is unavailable or cannot be loaded. In-flight generation buffers are cleared.

These state APIs do not provide automatic CLI resume.

### Runtime Construction and Extension

`OptimizerConfiguration` holds the backend `name`, `type`, and `parameters`. `build_optimizer_from_config()` in `src/aid2e/utilities/runtime_builders.py` selects a backend using normalized `name`, `type`, or `algorithm` values:

- Ax: `ax`, `bo`, `mobo`, `bayesian`
- PyMOO: `pymoo`, `ga`, `nsga2`, `nsga3`, `moead`, `evolutionary`

The builder creates the backend config and passes the design configuration and objective names and directions to the optimizer. The base class converts the design configuration into a search space. Backend config models are registered lazily through `optimization_registry.py`.

`run_optimization()` controls batch submission and the iteration budget; the optimizer classes do not enforce `n_iterations` internally.

Adding a backend requires an optimizer implementing the four abstract methods, a Pydantic config registered with `optimization_registry.register()`, and a runtime-builder branch. Shared trial history, Pareto computation, and result export can then be reused from `BaseOptimizer`.
