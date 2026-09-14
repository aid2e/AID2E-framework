# Optimizers

## Overview

`aid2e.optimizers` exposes a shared optimizer interface and two concrete backends:
Ax for Bayesian optimization and PyMOO for evolutionary optimization. The package
also exports the shared search-space and trial data structures, plus the Pareto
utility used by the base implementation.

### Choosing a Backend

- Use **Ax** for Bayesian single- or multi-objective optimization with native
  support for the constraint forms described below.
- Use **PyMOO** for evolutionary single- or multi-objective optimization with
  generation-sized candidate batches. PyMOO does not currently enforce design
  constraints during candidate generation.

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

For Ax, `n_iterations` is the total candidate-evaluation budget and
`batch_size` controls how many candidates are submitted together. For PyMOO,
`n_iterations` is the number of generations; `pop_size` controls the initial
generation and `n_offsprings` normally controls later generations.

Ax initialization strategies are:

- `sobol`: Low-discrepancy sampling designed to cover the search space evenly.
- `uniform`: Independent pseudorandom sampling over each parameter range.
- `center`: One search-space center point followed by Sobol initialization when
  additional initial samples are requested.

## Shared Behavior

All optimizer backends use the same search-space representation, trial lifecycle,
result format, and failure accounting. Backend implementations add candidate
generation and state management without changing these shared contracts.

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
parsed into parameters. Dictionary parameter definitions require a concrete
`value` field alongside `bounds` or `choices`.

`SearchSpace.validate()` is a backend-agnostic constraint check. It evaluates
`ParameterConstraint` objects directly and is intended for backends that do not
enforce constraints natively.

### Trial Lifecycle

`Trial` is the in-memory record for one evaluated point. It stores:

- `index`
- `parameters`
- `metrics`
- `metadata`
- `status`

Statuses are normalized to lower case in `__post_init__`. The base code recognizes
`pending`, `suggested`, `running`, `completed`, `failed`, `aborted`, and
`cancelled`. Unknown values are preserved, but a warning is logged.

Failed evaluations are recorded without objective values through
`mark_trial_failed()`. Penalized evaluations are different: they are completed
trials with configured penalty objective values and `penalized` metadata, so the
optimizer can use the penalty values during subsequent candidate generation.

### Results and Pareto Front

`compute_pareto_front()` computes the non-dominated subset of completed trials
using each objective's configured `minimize` or `maximize` direction. Missing
directions default to minimization. It only considers trials whose status is
`completed` and that have metrics. The function is used by the base
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
- `mark_trial_failed()`
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
uses the first Pareto member for multi-objective cases and the best completed
trial under the configured direction for single-objective cases.

`get_optimization_results()` and `save_optimization_results()` provide a stable
JSON-friendly result export, including raw status and display status labels.
Scheduler outputs and XCom values feed objective collection before these
results are passed to the optimizer.

Objective `*_err` values are retained in the exported `objective_errors` fields,
but are not currently passed into either optimizer. Ax attaches objective data
with `sem=0.0`, and PyMOO receives only the objective values.

### Failed and Penalized Trials

`problem.evaluation_config.trial_failure_policy` controls workflow evaluation
failures and defaults to `fail`:

- `fail` calls the backend's `mark_trial_failed()` without objective values.
  Failed trials remain in optimizer history, are excluded from Pareto
  calculations, and are included in subsequently saved results.
- `penalty` requires a `penalty_objectives` value for every declared objective.
  The optimizer receives those values through `update_with_results()`, and the
  completed trial is marked with `penalized: true` metadata. These values are
  supplied by the user; the framework does not derive them from objective
  directions.

Both outcomes count toward `max_failed_trials`, which defaults to `0`. The
optimization stops when the number of failed evaluations exceeds that configured
limit, so the first failure stops the run unless a larger limit is configured.

## Ax Backend

Ax provides Bayesian single- and multi-objective optimization. The backend maps
AID2E search spaces and objectives into an Ax experiment, then records each Ax
trial in the shared optimizer history.

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

`src/aid2e/optimizers/ax/_resolver.py` keeps the config YAML-friendly by resolving
string names into the concrete Ax, BoTorch, and GPyTorch classes used by the
Modular BoTorch generator. It resolves:

- `acquisition_class`
- `botorch_acqf_class`
- `botorch_acqf_classes_with_options`
- `surrogate_spec`

The resolver currently knows about the supported model, transform, kernel,
likelihood, and MLL classes listed in that module. When `surrogate_spec` is
present, it also resolves nested `metric_to_model_configs` entries in addition
to the top-level `model_configs`.

### Search-space and objective mapping

`AxOptimizer` converts `RangeParameter` values into Ax floating-point range
parameters and `ChoiceParameter` values into Ax string choice parameters.

For multi-objective problems, the optimization config uses Ax objectives plus
optional objective thresholds. Each objective and threshold uses its configured
`minimize` or `maximize` direction; missing directions default to minimization.

### Generation strategy

The Ax backend uses the node-based Ax generation API. The constructor requires an
Ax runtime that provides `CenterGenerationNode`, `GenerationNode`,
`GeneratorSpec`, and `MinTrials`.

The generation strategy is built as:

- an initialization node using `sobol`, `uniform`, or `center`
- a model-based node using `Generators.BOTORCH_MODULAR`

`center` is handled as a center node followed by a Sobol initialization node when
additional initialization samples are needed.

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

`mark_trial_failed()` marks the corresponding Ax experiment trial and the shared
`Trial` record as failed without attaching objective data.

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
internals. The serialized payload does not currently include
`objective_directions`; `load_state()` retains the directions already present on
the initialized optimizer.

## PyMOO Backend

PyMOO provides evolutionary single- and multi-objective optimization through an
external-evaluation ask/tell loop. AID2E schedules each generated population and
returns the completed objective values to PyMOO as one generation.

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
size is determined by the PyMOO algorithm: `pop_size` for the initial generation
and normally `n_offsprings` for later generations, with `n_offsprings` defaulting
to `pop_size`. When the hint does not match the generated batch, a debug message
is logged.

For normal full GA, NSGA-II, and NSGA-III generations, the expected number of
candidate evaluations is:

```text
pop_size + (n_iterations - 1) * n_offsprings
```

When `n_offsprings` is omitted, this becomes `n_iterations * pop_size`.
MOEA/D uses its reference-direction population and does not consume the
configured `n_offsprings` value in the current backend.

The backend keeps an in-flight generation buffer and refuses to start a new
generation until the current one has been fully updated. Trials are inserted into
the shared history with status `pending` when they are suggested and are updated
to `completed` when results arrive.

`mark_trial_failed()` records a failed trial and places infinite objective values
in the PyMOO generation result matrix so the remaining generation can complete.
Configured maximize objectives are sign-adjusted to PyMOO's internal minimization
convention before `algorithm.tell()`.

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

`serialize_state()` stores the search space, config, objective names and
directions, trials, trial counter, generation count, resolved algorithm name,
and, when possible, a base64-encoded pickle of the PyMOO algorithm state.

`load_state()` reconstructs the search space and problem, then either restores
the pickled algorithm state or rebuilds the algorithm from config and seed if the
pickle is missing or cannot be loaded. Any in-flight generation state is cleared
during load.

## Constraint Enforcement

Constraints are handled through three framework layers:

1. **DesignConfig** validates constraint syntax at configuration load time.
2. **SearchSpace** stores validated constraints for optimizer use.
3. **Optimizer** enforces the constraint forms supported by its backend.

### Definition and Validation

Constraints are defined in the design configuration as expressions over
parameters. When a `DesignConfig` is instantiated, it checks that the rule is a
valid Python expression and that qualified parameter names referenced in the
rule exist in the design. This does not prove that an expression is linear or
supported by a particular optimizer backend.

`ParameterConstraint.extract_parameter_names()` extracts qualified parameter
names from a rule. `ParameterConstraint.validate_syntax()` validates the rule's
syntax and parameter names.

```python
constraint = ParameterConstraint(
    name="example",
    rule="tracker.x + magnet.y + detector.z <= 10.0",
)

param_names = constraint.extract_parameter_names()
# Returns: {'tracker.x', 'magnet.y', 'detector.z'}

valid_params = {'tracker.x', 'magnet.y', 'detector.z'}
is_valid, error_msg = constraint.validate_syntax(valid_params)

param_values = {'tracker.x': 3.0, 'magnet.y': 4.0, 'detector.z': 2.0}
is_satisfied = constraint.evaluate(param_values)
# Returns: True (3.0 + 4.0 + 2.0 = 9.0 <= 10.0)
```

```python
# Unknown parameter
rule: "group.unknown + group.y <= 10.0"
# ERROR: Unknown parameters: group.unknown

# Invalid syntax
rule: "group.x +* group.y <= 10.0"
# ERROR: Invalid syntax in constraint
```

### Runtime Validation (`SearchSpace`)

Validated constraints are passed to the `SearchSpace`:

```python
from aid2e.optimizers.base import SearchSpace

search_space = SearchSpace.from_design_config(design_config)
print(f"Constraints: {len(search_space.constraints)}")
```

The `SearchSpace` provides explicit runtime constraint checking:

```python
# Check if parameter values satisfy constraints
param_values = {"group.x": 1.5, "group.y": 9.0}
is_valid, errors = search_space.validate(param_values)

if not is_valid:
    print(f"Constraint violations: {errors}")
```

`ParameterConstraint.evaluate()` evaluates one rule against parameter values;
`SearchSpace.validate()` applies all stored constraints and reports failures.
This check is not automatically applied to candidates generated by PyMOO. These
methods can evaluate other valid Python expressions, but that does not make them
native optimizer constraints.

### Native Enforcement and Conversion (Ax)

The Ax optimizer converts constraints to Ax's native `ParameterConstraint` format:

```python
from aid2e.optimizers import AxOptimizer, AxOptimizerConfig, SearchSpace
from aid2e.utilities.configurations import DesignConfig

config_data = {
    "design_parameters": {
        "group": {
            "parameters": {
                "x": {"value": 1.0, "bounds": [0.5, 2.0]},
                "y": {"value": 5.0, "bounds": [3.0, 10.0]},
            }
        }
    },
    "parameter_constraints": [
        {
            "name": "total_limit",
            "rule": "group.x + group.y <= 10.0",
        },
        {"name": "min_y", "rule": "group.y >= 4.0"},
    ],
}

design_config = DesignConfig(**config_data)
search_space = SearchSpace.from_design_config(design_config)
optimizer = AxOptimizer(
    search_space=search_space,
    config=AxOptimizerConfig(
        n_initial_samples=10,
        initialization_strategy="sobol",
        generator="BOTORCH_MODULAR",
    ),
    objective_names=["objective"],
)

# Ax enforces supported constraints during generation
candidates = optimizer.suggest_candidates(n_candidates=20)
for candidate in candidates:
    is_valid, errors = search_space.validate(candidate)
    assert is_valid, f"Constraint violation: {errors}"
```

Ax conversion supports the linear inequalities accepted by Ax, including
weighted terms and a numeric bound. Unsupported forms raise a `ValueError` when
the Ax search space is constructed; constraints are never silently omitted.

Supported comparison operators are:

- `<=` - Less than or equal (upper bound)
- `<` - Less than (strict upper bound)
- `>=` - Greater than or equal (converted to an upper bound internally)
- `>` - Greater than (converted to an upper bound internally)

```python
# Design constraint
rule: "group.x + group.y <= 1.5"

# Converted to the Ax inequality
group.x + group.y <= 1.5
```

**Conversion logic:**
1. Separate the linear expression, comparison operator, and numeric bound
2. Convert strict inequalities to the nearest representable inclusive bound
   with `numpy.nextafter()`
3. Delegate linear-expression parsing and `>=` conversion to Ax

Example conversion:

```python
# Original: group.x + group.y >= 0.5
# Converted: -group.x - group.y <= -0.5
```

Weighted linear expressions are supported:

```python
rule: "group.x + 2.0 * group.y <= 3.0"
```

Non-linear expressions are rejected by Ax conversion:

```python
rule: "group.x * group.y <= 1.0"
rule: "group.x ** 2 + group.y ** 2 <= 1.0"
```

## Developer Reference

This section documents the public optimizer surface, runtime construction path,
and the changes required to add another backend. It follows the user-facing
backend behavior so implementation details remain available without interrupting
the configuration and lifecycle reference.

### Public Interface

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

The optimizer implementations can be imported from `aid2e.optimizers`:

```python
from aid2e.optimizers import AxOptimizer, PyMOOOptimizer
```

The implementation is split between:

- shared bookkeeping and result utilities in `src/aid2e/optimizers/base.py`
- Ax-specific configuration, symbol resolution, and candidate generation in
  `src/aid2e/optimizers/ax/`
- PyMOO-specific ask/tell logic in `src/aid2e/optimizers/pymoo/`
- canonical config and runtime builders in `src/aid2e/utilities/configurations/`
  and `src/aid2e/utilities/runtime_builders.py`

### Runtime Construction

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
constructs the optimizer object. The outer `run_optimization()` loop drives
repeated `suggest_candidates()` and `update_with_results()` calls.

The optimizer constructors accept `DesignConfig` objects directly, so the runtime
builder passes the design config rather than pre-building `SearchSpace`. The base
class handles the conversion to `SearchSpace`.

`optimization_registry.py` loads built-in backend config models on demand so the
canonical optimizer config can validate backend-specific parameters without
forcing every backend module to be imported up front.

### Extension Points

To add a new backend, the current code path requires three pieces:

- a new optimizer class implementing the four abstract methods on `BaseOptimizer`
- a Pydantic config model registered through `optimization_registry.register()`
  and, for built-in backends, its loader in `_algorithm_config_loaders`
- a runtime-builder branch that maps the canonical optimizer config to the new backend

Shared history, Pareto computation, trial export, and backend-switch seeding can
then be reused directly from `BaseOptimizer`.
