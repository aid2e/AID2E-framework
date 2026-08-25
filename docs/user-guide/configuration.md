# Configuration

## Overview

The AID2E CLI recognizes four configuration types:

1. **DesignConfig** - Defines the parameter search space and constraints.
2. **ProblemConfiguration** - Defines the design configuration, objectives,
   paths, and evaluation settings.
3. **OptimizerConfiguration** - Defines optimizer selection and settings.
4. **FullConfig** - Combines problem, optimizer, optional scheduler, and
   optional workflow configurations.

## Configuration Hierarchy

```
FullConfig (loaded via load_config())
├── ProblemConfiguration
│   ├── design_config: DesignConfig
│   │   ├── DesignParameters (parameter groups)
│   │   └── ParameterConstraints (optional)
│   ├── objectives: ObjectiveDefinition[]
│   ├── output_location and work_location
│   ├── environment_config (optional)
│   └── evaluation_config (optional)
├── optimizer: OptimizerConfiguration
│   ├── name and type
│   └── parameters (algorithm-specific)
├── scheduler: SchedulerConfiguration (optional)
└── workflows: WorkflowsConfiguration (optional)
```

## Loading Configurations

### Load a Problem and Design Configuration

```python
from aid2e.utilities.configurations import ProblemConfigLoader

cfg = ProblemConfigLoader.load("path/to/problem.config")
print(cfg.design_config.get_parameter_names())
```

- Example fixtures live in tests/test_utilities/fixtures/dtlz2/ (design.params, problem.config).

### Load a Full Configuration

```python
from aid2e.utilities.configurations import FullConfig, load_config

# Load a full configuration
config = load_config('examples/configurations/dtlz2_optimization.yml')

# Access configuration components
print(config.problem)
print(config.problem.design_config)
print(config.optimizer)
print(config.scheduler)
print(config.workflows)
```

The CLI automatically detects configuration type based on structure:

```python
def detect_config_type(data: dict) -> str:
    """Auto-detect configuration type."""
    if "problem" in data and "optimizer" in data:
        return "full"           # Full workflow config
    elif "problem" in data:
        return "problem"        # Problem-only config
    elif "optimizer" in data:
        return "optimizer"      # Optimizer-only config
    elif "design_space" in data or "design_parameters" in data:
        return "design"         # Design space only
    else:
        return "unknown"
```

## Problem Configuration

```yaml
problem:
  name: My Problem
  problem_type: toy
  output_location: ./output
  work_location: ./work
  design_parameters_file: ./design.params
  objectives:
    - name: f1
      direction: minimize
```

### Design Configuration (design.params)
```yaml
design_space:
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1: {value: 0.5, bounds: [0.0, 1.0]}
        x2: {value: 0.0, bounds: [0.0, 1.0]}
        # ... x3-x10

  parameter_constraints:
    - name: simple_constraint
      description: x1 must be less than 1.0
      rule: DTLZ2_variables.x1 < 1.0
```

#### Constraint Handling

This section explains constraint definition, validation, and storage in the AID2E framework.

Constraints are handled through a three-layer architecture:

1. **DesignConfig** - Validates constraint syntax at configuration load time
2. **SearchSpace** - Stores validated constraints for optimizer use  
3. **Optimizer** - Enforces supported constraints during candidate generation as described in the [optimizer guide](optimizers.md#constraint-enforcement)

##### Constraint Definition and Validation (DesignConfig)

Constraints are defined in the design configuration as expressions over parameters.

When a `DesignConfig` is instantiated, constraints are automatically validated:

**Validation checks:**
- Constraint rule is syntactically valid Python expression
- Qualified parameter names referenced in the rule exist in the design

This validation does not prove that an expression is linear or supported by a
particular optimizer backend.

`ParameterConstraint.extract_parameter_names()` extracts qualified parameter
names from a rule. `ParameterConstraint.validate_syntax()` validates the rule's
syntax and parameter names.

**Example errors caught:**

```python
# Unknown parameter
rule: "tracker.unknown + tracker.radius <= 10.0"  
# ERROR: Unknown parameters: tracker.unknown

# Invalid syntax
rule: "tracker.thickness +* tracker.radius <= 10.0"
# ERROR: Invalid syntax in constraint
```

##### Constraint Storage (SearchSpace)

Validated constraints are passed to the `SearchSpace`:

```python
from aid2e.optimizers.base import SearchSpace

# Create SearchSpace from validated DesignConfig
search_space = SearchSpace.from_design_config(design_config)

# Constraints are now stored in search_space.constraints
print(f"Constraints: {len(search_space.constraints)}")
```

`ParameterConstraint.evaluate()` evaluates a constraint at runtime.

##### Constraint Format

###### Ax Comparison Operators

- `<=` - Less than or equal (upper bound)
- `<` - Less than (strict upper bound)
- `>=` - Greater than or equal (lower bound, converted to upper bound internally)
- `>` - Greater than (strict lower bound, converted to upper bound internally)

###### Linear Constraints

Ax conversion currently supports simple linear sums and differences:

```python
# Valid: Simple sum with upper bound
rule: "group.x + group.y <= 1.5"

# Valid: Lower bound (converted internally)
rule: "group.x + group.y >= 0.5"

# Not supported by Ax conversion: weighted or non-linear expressions
rule: "group.x + 2.0 * group.y <= 3.0"
rule: "group.x * group.y <= 1.0"
rule: "group.x ** 2 + group.y ** 2 <= 1.0"
```

`ParameterConstraint.evaluate()` and `SearchSpace.validate()` can evaluate
other valid Python expressions, but that does not make them native optimizer
constraints.

###### Parameter Names

Use fully qualified parameter names so they can be validated and substituted:

```python
# Valid: Qualified names
rule: "tracker.thickness + magnet.radius <= 10.0"

# Not recognized as design parameters
rule: "thickness + radius <= 10.0"
```

##### Best Practices

1. Validate constraints at configuration time to catch errors early.
2. Always use fully qualified parameter names.
3. Use simple linear sums and differences for Ax compatibility.
4. Verify generated candidates with `SearchSpace.validate()`.

##### Planned Enhancements

Potential improvements:
- Native optimizer support for non-linear constraints
- More complex expressions (absolute values, min/max, etc.)
- Constraint propagation and simplification
- Automatic constraint tightening based on feasibility

##### Example: Complete Workflow

```python
from aid2e.optimizers import AxOptimizer, AxOptimizerConfig, SearchSpace
from aid2e.utilities.configurations import DesignConfig

config_data = {
    "design_parameters": {
        "tracker": {
            "parameters": {
                "thickness": {"value": 1.0, "bounds": [0.5, 2.0]},
                "radius": {"value": 5.0, "bounds": [3.0, 10.0]},
            }
        }
    },
    "parameter_constraints": [
        {
            "name": "total_limit",
            "rule": "tracker.thickness + tracker.radius <= 10.0",
        },
        {"name": "min_radius", "rule": "tracker.radius >= 4.0"},
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

candidates = optimizer.suggest_candidates(n_candidates=20)
for candidate in candidates:
    is_valid, errors = search_space.validate(candidate)
    assert is_valid, f"Constraint violation: {errors}"
```

##### Related Files

- Constraint configuration: `src/aid2e/utilities/configurations/design_config.py`
- Search-space validation: `src/aid2e/optimizers/base.py`
- Constraint tests: `tests/test_optimizers/test_constraint_integration.py`
- Optimizer behavior: [Optimizer Guide](optimizers.md#constraint-enforcement)

## Optimizer Configuration

```yaml
optimizer:
  name: ax
  type: bayesian
  parameters:
    n_initial_samples: 4
    n_iterations: 8
    batch_size: 2
```

See the [optimizer guide](optimizers.md) for backend behavior and settings.

## Scheduler Configuration

See the [scheduler guide](schedulers.md) for scheduler configuration and
runner-specific settings.

## Workflow Configuration

See the [workflow guide](workflows.md) for workflow structure, scheduler
cascade, jobs, and objective plans.

## Full Configuration

### Complete Example

```yaml
problem:
  name: DTLZ2 Optimization
  problem_type: toy
  output_location: ./output/dtlz2
  work_location: ./work/dtlz2
  design_parameters_file: ./design.params
  objectives:
    - name: f1
      direction: minimize
      objective_plan:
        steps:
          stages:
            - name: evaluate
              inline:
                entrypoint: examples.evaluators.dtlz2:objective_payload
              produces_objective: true
      metrics_keys: [f1]
    - name: f2
      direction: minimize
      objective_plan:
        steps:
          stages:
            - name: evaluate
              inline:
                entrypoint: examples.evaluators.dtlz2:objective_payload
              produces_objective: true
      metrics_keys: [f2]

optimizer:
  name: ax
  type: bayesian
  parameters:
    initialization_strategy: sobol
    generator: BOTORCH_MODULAR
    n_initial_samples: 4
    n_iterations: 8
    batch_size: 2
    seed: 42

scheduler:
  runner_type: JobLibRunner
  parameters:
    n_jobs: 2
    backend: threading

workflows:
  workflows:
    - name: dtlz2_eval
      branches: []
```

The referenced `design.params` follows the design configuration example above.

## See Also

- [Optimizer Guide](optimizers.md)
- [Scheduler Guide](schedulers.md)
- [Workflow Guide](workflows.md)
- [DesignConfig API Documentation](../api-reference/utilities.md)
- [SearchSpace API Documentation](../api-reference/optimizers.md)
- [AxOptimizer API Documentation](../api-reference/optimizers.md)

## Configuration Models

2. Configuration Models
FullConfig combines problem, optimizer, optional scheduler, and workflows
SchedulerConfiguration can be used globally or at workflow scopes
All configuration models are validated with Pydantic v2
