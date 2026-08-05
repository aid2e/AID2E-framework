# AID2E Optimizer Architecture

## Overview

`aid2e.optimizers` exposes a shared optimizer interface and two concrete backends:
Ax for Bayesian optimization and PyMOO for evolutionary optimization. The package
also exports the shared search-space and trial data structures, plus the Pareto
utility used by the base implementation.

The current public export surface is:

- `BaseOptimizer`
- `SearchSpace`
- `Trial`
- `compute_pareto_front`
- `AxOptimizer`
- `AxOptimizerConfig`
- `PyMOOProblem`
- `PyMOOOptimizer`
- `PyMOOOptimizerConfig`
- `AID2EProblem`

The design is intentionally split between:

- shared bookkeeping and result utilities in `src/aid2e/optimizers/base.py`
- Ax-specific configuration, symbol resolution, and candidate generation in
  `src/aid2e/optimizers/ax/`
- PyMOO-specific ask/tell logic in `src/aid2e/optimizers/pymoo/`
- canonical config and runtime builders in `src/aid2e/utilities/configurations/`
  and `src/aid2e/utilities/runtime_builders.py`

## Shared Abstractions

### `SearchSpace`

`SearchSpace` is the optimizer-facing representation of the design domain. It
stores:

- `parameters`: a mapping from parameter name to `BaseParameter`
- `constraints`: optional `ParameterConstraint` objects
- `name`: optional search-space identifier
- `source_config`: optional originating `DesignConfig`

`SearchSpace.from_design_config()` flattens a validated `DesignConfig` into the
optimizer form by using `DesignConfig.get_flat_parameters()` and forwarding the
associated parameter constraints.

The constructor accepts either `BaseParameter` objects or dictionaries that are
parsed into parameters. The code rejects retired dictionary shapes, including the
legacy `values` key, and requires a concrete `value` field alongside `bounds` or
`choices`.

`SearchSpace.validate()` is a backend-agnostic constraint check. It evaluates
`ParameterConstraint` objects directly and is intended for backends that do not
enforce constraints natively.

### `Trial`

`Trial` is the in-memory record for one evaluated point. It stores:

- `index`
- `parameters`
- `metrics`
- `metadata`
- `status`

Statuses are normalized to lower case in `__post_init__`. The base code recognizes
`pending`, `suggested`, `running`, `completed`, `failed`, `aborted`, and
`cancelled`. Unknown values are preserved, but a warning is logged.

### `compute_pareto_front`

`compute_pareto_front()` computes the non-dominated subset of completed trials
using minimization semantics for every objective. It only considers trials whose
status is `completed` and that have metrics. The function is used by the base
implementation and is not Ax- or PyMOO-specific.

### `BaseOptimizer`

`BaseOptimizer` owns the shared trial ledger and the default result utilities. It
accepts either a `SearchSpace` or a `DesignConfig`, validates that the search
space and objective list are non-empty, and stores the common `seed`.

The backend-required contract is small. Only these methods remain abstract:

- `suggest_candidates`
- `update_with_results`
- `serialize_state`
- `load_state`

Everything else is provided by the base class:

- `get_trials()`
- `set_trial_status()`
- `get_optimization_results()`
- `save_optimization_results()`
- `seed_from_trials()`
- `get_pareto_front()`
- `get_best_trial()`

`seed_from_trials()` is the backend-switch primitive. It appends external trials
to the local history, assigns new sequential indices, and preserves the original
source trial index in metadata under `source_index`. This updates history only;
backends that need warm-start behavior must add their own override.

`get_pareto_front()` delegates to `compute_pareto_front()`. `get_best_trial()`
uses the first Pareto member for multi-objective cases and the lowest-valued
trial for single-objective cases.

`get_optimization_results()` and `save_optimization_results()` provide a stable
JSON-friendly result export, including raw status and display status labels.

## Ax Backend

### Configuration

`AxOptimizerConfig` is the backend config model for the Ax implementation. It is
registered under the `ax` name in the optimizer config registry.

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

The config explicitly rejects retired fields such as `surrogate_model` and
`acquisition_function`. The current surface expects the newer `generator` plus
`generator_kwargs` split instead.

`src/aid2e/optimizers/ax/_resolver.py` keeps the config YAML-friendly by resolving
string names into the concrete Ax, BoTorch, and GPyTorch classes used by the
modern Modular BoTorch generator. It resolves:

- `acquisition_class`
- `botorch_acqf_class`
- `botorch_acqf_classes_with_options`
- `surrogate_spec`

The resolver currently knows about the supported model, transform, kernel,
likelihood, and MLL classes listed in that module. When `surrogate_spec` is
present, it also resolves nested `metric_to_model_configs` entries in addition
to the top-level `model_configs`.

### Search-space and constraint mapping

`AxOptimizer` converts `RangeParameter` values into Ax floating-point range
parameters and `ChoiceParameter` values into Ax string choice parameters.

Constraint handling is best effort. The backend attempts to translate
`ParameterConstraint.rule` into an Ax linear inequality. Simple expressions are
handled; unsupported expressions are logged and skipped rather than being forced
into an incorrect shape.

For multi-objective problems, the optimization config uses Ax objectives plus
optional objective thresholds. The objective names are treated as minimization
targets in the Ax model.

### Generation strategy

The Ax backend uses the node-based Ax generation API. The constructor requires an
Ax runtime that provides `CenterGenerationNode`, `GenerationNode`,
`GeneratorSpec`, and `MinTrials`.

The generation strategy is built as:

- an initialization node using `sobol`, `uniform`, or `center`
- a model-based node using `Generators.BOTORCH_MODULAR`

`center` is handled as a center node followed by a Sobol initialization node when
additional initialization samples are needed. `uniform` falls back to Sobol if
the installed Ax runtime does not expose a uniform generator.

The backend uses `resolve_generator_kwargs()` to turn YAML-friendly values into
Ax runtime objects before passing them into the generator spec.

### Candidate lifecycle

`suggest_candidates()` makes one Ax generation call for the requested batch, then
normalizes the returned generator output into single-arm runs. Each generated arm
creates a new Ax trial, is marked running in Ax, and is recorded in the base
history as `suggested`.

The method raises if Ax returns fewer generator runs than requested. The method
also records strategy metadata such as the current Ax step index or node name
when available.

`update_with_results()` validates that every configured objective is present in
the metrics payload, attaches the results to the Ax experiment as deterministic
data, marks the Ax trial completed, and updates the shared `Trial` history.

### State model

`serialize_state()` stores:

- the search-space parameters and constraints
- objective names
- seed
- backend config
- recorded trials
- the trial counter

`load_state()` rebuilds the search space, Ax search space, optimization config,
experiment, and generation strategy from the serialized payload, then replays
completed trials into the experiment.

The code does not serialize an Ax experiment object directly. The restoration path
is therefore reconstruction-based rather than a byte-for-byte restore of Ax
internals.

## PyMOO Backend

### Configuration

`PyMOOOptimizerConfig` is registered under the `pymoo` name in the optimizer
registry. It currently supports:

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

If `algorithm` is omitted, `resolve_algorithm()` selects `ga` for single-objective
problems and `nsga2` otherwise. Explicit algorithms must match the objective
count:

- `ga` only for single-objective problems
- `nsga2`, `nsga3`, and `moead` only for multi-objective problems

### `PyMOOProblem`

`PyMOOProblem` is the public PyMOO `Problem` wrapper for the AID2E search space.
It is structural only:

- `decode_x()` converts a PyMOO float vector back into an AID2E parameter dict
- `_evaluate()` always raises `NotImplementedError`

The class is used for ask/tell workflows where evaluation happens outside the
optimizer, not inside the PyMOO problem object.

`AID2EProblem` remains available temporarily as a deprecated compatibility
alias. Ax does not expose an equivalent public `Problem` wrapper.

Choice parameters are encoded as continuous indices and rounded back to the
nearest valid choice during decoding. Range parameters are passed through as
floats. Any other parameter types are not supported by the current backend.

### Candidate lifecycle

PyMOO follows an external-evaluation ask/tell flow:

- `suggest_candidates()` calls `algorithm.ask()`
- `update_with_results()` buffers one evaluation result
- `_flush_generation()` calls `algorithm.tell()` once the full generation has
  reported back

`suggest_candidates()` ignores `n_candidates` as a hard request. The actual batch
size is determined by the PyMOO algorithm. When the hint does not match the
generated batch, a debug message is logged.

The backend keeps an in-flight generation buffer and refuses to start a new
generation until the current one has been fully updated. Trials are inserted into
the shared history with status `pending` when they are suggested and are updated
to `completed` when results arrive.

`seed_from_trials()` is overridden to guard against seeding while a generation is
in flight. The method still only updates history; it does not warm-start the
internal PyMOO population.

### Algorithm mapping

The backend currently constructs one of four algorithms:

- `ga`
- `nsga2`
- `nsga3`
- `moead`

`SBX`, polynomial mutation, and random sampling are used as the default operators.
`nsga3` and `moead` build reference directions from `n_partitions` or `pop_size`
as appropriate.

### Constraints and state

Constraints are not forwarded into PyMOO at present. When the search space
contains constraints, the optimizer logs a warning and continues, so constraint
satisfaction is not guaranteed by this backend.

`serialize_state()` stores the search space, config, objective names, trials,
trial counter, generation count, resolved algorithm name, and, when possible, a
base64-encoded pickle of the PyMOO algorithm state.

`load_state()` reconstructs the search space and problem, then either restores
the pickled algorithm state or rebuilds the algorithm from config and seed if the
pickle is missing or cannot be loaded. Any in-flight generation state is cleared
during load.

## Runtime Construction Path

`OptimizerConfiguration` is the canonical top-level config object used by the
framework. It stores the backend `name`, the optimizer `type`, and the raw
`parameters` payload.

The runtime builder resolves backend selection through `build_optimizer_from_config()`
in `src/aid2e/utilities/runtime_builders.py`:

- backend inference normalizes `name`, `type`, and the `algorithm` parameter and
  matches any of those tokens against the supported backend keywords
- `ax`, `bo`, `mobo`, and `bayesian` map to the Ax backend
- `pymoo`, `ga`, `nsga2`, `nsga3`, `moead`, and `evolutionary` map to the PyMOO backend

For Ax, the builder instantiates `AxOptimizerConfig` from the raw parameter
payload and passes `problem_cfg.design_config` into `AxOptimizer`. For PyMOO, it
does the same with `PyMOOOptimizerConfig`. In both cases, the builder only
constructs the optimizer object; batch sizing and iteration counts are consumed
by the outer orchestration or runtime loop that drives repeated
`suggest_candidates()` and `update_with_results()` calls.

The optimizer constructors accept `DesignConfig` objects directly, so the runtime
builder passes the design config rather than pre-building `SearchSpace`. The base
class handles the conversion to `SearchSpace`.

`optimization_registry.py` registers the backend config models lazily so the
canonical optimizer config can validate backend-specific parameters without
forcing every backend module to be imported up front.

## Code-Visible Limitations

- The base class assumes minimization semantics throughout.
- `compute_pareto_front()` only considers completed trials with metrics.
- `AxOptimizerConfig.n_iterations` and `PyMOOOptimizerConfig.n_iterations` are
  configuration values used by outer execution flows; the optimizer classes do
  not enforce a stop condition internally, and the runtime builder does not
  consume them itself.
- Ax constraint handling is best effort and only covers the constraint shapes
  that the parser can convert safely.
- PyMOO does not currently enforce search-space constraints.
- PyMOO only supports `RangeParameter` and `ChoiceParameter`.
- The Ax backend currently requires the node-based Ax runtime; older Ax APIs are
  not used here.

## Extension Points

To add a new backend, the current code path requires three pieces:

- a new optimizer class implementing the four abstract methods on `BaseOptimizer`
- a Pydantic config model registered through `optimization_registry.register()`
- a runtime-builder branch that maps the canonical optimizer config to the new backend

Shared history, Pareto computation, trial export, and backend-switch seeding can
then be reused directly from `BaseOptimizer`.
