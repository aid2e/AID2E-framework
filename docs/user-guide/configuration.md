# Configuration

## Overview

The AID2E CLI recognizes four configuration types:

1. **DesignConfig** - Defines the parameter search space and constraints.
2. **ProblemConfiguration** - Defines the design configuration, objectives,
   paths, and evaluation settings.
3. **OptimizerConfiguration** - Defines optimizer selection and settings.
4. **FullConfig** - Combines problem, optimizer, optional scheduler, and
   optional workflow configurations.

Although scheduler and workflow configurations are optional in `FullConfig`,
both are required to run `aid2e optimize`.

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
│   └── parameters (algorithm specific)
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

- The complete DTLZ2 example is defined in
  `examples/dtlz2/dtlz2_optimization.yml`.

### Load a Full Configuration

```python
from aid2e.utilities.configurations import load_config

# Load a full configuration
config = load_config("examples/dtlz2/dtlz2_optimization.yml")

# Access configuration components
print(config.problem)
print(config.problem.design_config)
print(config.optimizer)
print(config.scheduler)
print(config.workflows)
```

The CLI detects configuration type from the top-level `problem`, `optimizer`,
`design_space`, and `design_parameters` keys.

Relative problem paths, including design, output, and work paths, are resolved
relative to the configuration file.

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

### Objectives

Objectives require a unique name and a `minimize` or `maximize` direction. An
objective can also define an optional objective plan. See the
[workflow guide](workflows.md#objective-collection) for objective execution.

### Design Configuration (`design.params`)

A problem defines its design space through exactly one of these fields:

- `design_parameters_file`: Load the design space from another file.
- `inline_design`: Define the design space directly in the problem configuration.

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

Constraints are defined under `parameter_constraints` in the design space.
AID2E validates their syntax and qualified parameter names when loading the
configuration, then stores them in the optimizer search space. This validation
does not prove that an expression is supported by a particular optimizer.

Use fully qualified parameter names such as `group.parameter`. Ax currently
supports linear inequalities, including weighted terms, with `<=`, `<`, `>=`,
or `>`.
PyMOO does not currently enforce design constraints during candidate
generation.

Constraints can also be checked explicitly through the search space:

```python
from aid2e.optimizers import SearchSpace

search_space = SearchSpace.from_design_config(config.problem.design_config)
candidate = {"DTLZ2_variables.x1": 0.5, "DTLZ2_variables.x2": 0.5}
is_valid, errors = search_space.validate(candidate)
```

Best practices:

1. Validate constraints at configuration time to catch errors early.
2. Always use fully qualified parameter names.
3. Use linear inequalities for Ax compatibility.
4. Verify generated candidates with `SearchSpace.validate()`.

See the [optimizer guide](optimizers.md#constraint-enforcement) for constraint
formats, runtime validation, backend behavior, and implementation details.

**Planned enhancements**

Potential improvements:

- Native optimizer support for non-linear constraints
- More complex expressions (absolute values, min/max, etc.)
- Constraint propagation and simplification
- Automatic constraint tightening based on feasibility

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

### DTLZ2 Example

This abbreviated example follows the checked-in
`examples/dtlz2/dtlz2_optimization.yml` structure:

```yaml
problem:
  name: DTLZ2 Optimization
  problem_type: DTLZ2
  output_location: ./output/dtlz2
  work_location: ./work/dtlz2

  inline_design:
    design_space:
      design_parameters:
        DTLZ2_variables:
          parameters:
            x1: {value: 0.5, bounds: [0.0, 1.0]}
            x2: {value: 0.5, bounds: [0.0, 1.0]}
            # ... x3-x10
      parameter_constraints:
        - name: x1_upper_bound
          rule: DTLZ2_variables.x1 < 1.0
        - name: sum_constraint
          rule: DTLZ2_variables.x1 + DTLZ2_variables.x2 < 1.5

  objectives:
    - name: f1
      direction: minimize
    - name: f2
      direction: minimize

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

scheduler:
  runner_type: JobLibRunner
  parameters:
    n_jobs: 2
    backend: threading

workflows:
  workflows:
    - name: dtlz2_eval
      branches:
        - name: main
          stages:
            - name: evaluate
              objective_plan:
                steps:
                  stages:
                    - name: evaluate
                      inline:
                        entrypoint: examples.evaluators.dtlz2:objective_payload
                      produces_objective: true
```

See the checked-in configuration for all ten design parameters and constraint
descriptions.

## See Also

- [Optimizer Guide](optimizers.md)
- [Scheduler Guide](schedulers.md)
- [Workflow Guide](workflows.md)
- [DesignConfig API Documentation](../api-reference/utilities.md)
- [SearchSpace API Documentation](../api-reference/optimizers.md)
- [AxOptimizer API Documentation](../api-reference/optimizers.md)
- [Constraint Test Suite](https://github.com/aid2e/AID2E-framework/blob/main/tests/test_optimizers/test_constraint_integration.py)
