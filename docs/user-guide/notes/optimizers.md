# Optimizer Notes

See the [optimizer guide](../optimizers.md) for configuration, budgets, failure policies, and backend limitations.

## Shared Abstractions

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

## Ax Symbol Resolution

`src/aid2e/optimizers/ax/_resolver.py` resolves supported class names for `acquisition_class`, `botorch_acqf_class`, `botorch_acqf_classes_with_options`, and `surrogate_spec`. Supported model, transform, kernel, likelihood, and MLL classes are listed in that module. A surrogate specification can use `model_configs` and per-metric `metric_to_model_configs`.

## Ax Candidate Lifecycle and State

Ax uses the node-based generation API (`CenterGenerationNode`, `GenerationNode`, `GeneratorSpec`, and `MinTrials`). Initialization is followed by a `Generators.BOTORCH_MODULAR` node.

`suggest_candidates()` makes one generation call for the batch and converts the output to single-arm trials. Each trial is running in Ax and `suggested` in the shared history. The method records the current step or node when available and raises if Ax returns fewer generator runs than requested.

`update_with_results()` checks that all configured objectives are present, attaches their values, and marks the trial completed in Ax and the shared history.

`serialize_state()` stores the search-space parameters and constraints, objective names, seed, config, trials, and trial counter. `load_state()` rebuilds the Ax experiment and generation strategy, then replays completed trials. It does not restore a serialized Ax experiment or fitted model directly.

## PyMOO Candidate Lifecycle and State

`PyMOOProblem` describes the search space for external evaluation. `decode_x()` converts vectors to parameter dictionaries; `_evaluate()` raises `NotImplementedError`. Range parameters remain floats; choice parameters use continuous indices rounded to the nearest valid choice. Other parameter types are not supported.

`suggest_candidates()` calls `algorithm.ask()` and records trials as `pending`. The algorithm determines the batch size; a differing `n_candidates` hint only produces a debug message. `update_with_results()` buffers each result and marks the trial completed. Once the generation is fully reported, `_flush_generation()` calls `algorithm.tell()`. A new generation cannot start while one is in flight.

`serialize_state()` stores the search space, config, objective names, trials, trial counter, generation count, resolved algorithm, and, when possible, a base64-encoded pickle of the algorithm state. `load_state()` restores the pickle or rebuilds the algorithm from config and seed if it is unavailable or cannot be loaded. In-flight generation buffers are cleared.

These state APIs do not provide automatic CLI resume.

## Runtime Construction and Extension

`OptimizerConfiguration` holds the backend `name`, `type`, and `parameters`. `build_optimizer_from_config()` in `src/aid2e/utilities/runtime_builders.py` selects a backend using normalized `name`, `type`, or `algorithm` values:

- Ax: `ax`, `bo`, `mobo`, `bayesian`
- PyMOO: `pymoo`, `ga`, `nsga2`, `nsga3`, `moead`, `evolutionary`

The builder creates the backend config and passes the design configuration and objective names and directions to the optimizer. The base class converts the design configuration into a search space. Backend config models are registered lazily through `optimization_registry.py`.

`run_optimization()` controls batch submission and the iteration budget; the optimizer classes do not enforce `n_iterations` internally.

Adding a backend requires an optimizer implementing the four abstract methods, a Pydantic config registered with `optimization_registry.register()`, and a runtime-builder branch. Shared trial history, Pareto computation, and result export can then be reused from `BaseOptimizer`.
