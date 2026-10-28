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
- `center`: One search-space center point followed by Sobol initialization when additional initial samples are requested.

`n_initial_samples` is the number of completed Sobol or uniform initialization trials, including penalized trials. Failed trials without results count toward `n_iterations`, but not `n_initial_samples`.

If the installed Ax version has no uniform generator, `uniform` falls back to Sobol.

## Shared Behavior

All optimizer backends use the same search-space representation, trial lifecycle, result format, and failure accounting. Backend implementations add candidate generation and state management without changing these shared contracts.

Trials record parameters, objective values, status, and metadata. Results include all recorded trials. The Pareto front includes only completed trials with metrics and respects each objective's `minimize` or `maximize` direction. Failed trials have no objective values; penalized trials have user-configured values that influence optimization.

Objective `<name>_err` values are saved with results and trial metadata and passed to Ax as standard errors. When omitted, Ax estimates noise. For each objective, supply errors for all real evaluations or none. PyMOO selects candidates using objective means only.

### Failed and Penalized Trials

`problem.evaluation_config.trial_failure_policy` controls workflow evaluation failures and defaults to `fail`:

- `fail` calls the backend's `mark_trial_failed()` without objective values. Failed trials remain in optimizer history, are excluded from Pareto calculations, and are included in subsequently saved results.
- `penalty` requires a `penalty_objectives` value for every declared objective. The optimizer receives those values through `update_with_results()`, and the completed trial retains `penalized: true` and the failure `reason` in metadata. Choose poor values for each objective's direction; the framework does not derive them automatically. Penalties apply only to confirmed invalid designs and are excluded from the reported Pareto front.

EpicStack identifies geometry overlaps as invalid designs. Other failures are marked failed without penalties.

Both outcomes count toward `max_failed_trials`, which defaults to `0`. The optimization stops when the number of failed evaluations exceeds that configured limit, so the first failure stops the run unless a larger limit is configured. Results are updated and saved before stopping.

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

See [Ax symbol resolution](notes/optimizers.md#ax-symbol-resolution) for supported class names and surrogate specifications.

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

See [optimizer notes](notes/optimizers.md) for shared abstractions, candidate lifecycles, state handling, and extension points.
