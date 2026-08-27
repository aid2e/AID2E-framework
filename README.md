# AID2E Framework

[![Tests](https://github.com/aid2e/AID2E-framework/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/aid2e/AID2E-framework/actions/workflows/tests.yml)
[![Documentation](https://github.com/aid2e/AID2E-framework/actions/workflows/docs-deploy.yml/badge.svg?branch=main)](https://aid2e.github.io/AID2E-framework)

AI assisted Detector Design for EIC (AID2E) is a Python framework for
configuring and running detector design optimization workflows. It provides
typed configuration models, optimizer and scheduler integrations, workflow
execution, a command-line interface, and ePIC-specific utilities.

See the [documentation](https://aid2e.github.io/AID2E-framework) for
installation, configuration, and usage.

## Current Features

**Configuration and objectives**

  - YAML and dict configuration with Pydantic validation
  - Problem, design, optimizer, scheduler, objective, and workflow specifications
  - `ObjectiveDefinition` (name, direction, and optional objective plan)
  - Direct objective collection from workflow job results
  - Inline, script-based, and multi-step objective plans

**Workflow execution**

  - DAG construction with edge inference, DFS-based cycle detection, validation, and O(V+E) topological sorting using Kahn’s algorithm.
  - Execution layers for sequential stages and parallel jobs
  - Range and payload job factories
  - Generic and stack execution engines
  - Stack-specific configuration and execution are resolved through `StackRegistry`
  - ePIC-specific utilities remain under `utilities/epic_utils/`

**Schedulers**

  - Common stage execution interface through `BaseScheduler`
  - `JobLibScheduler` for local parallel execution
  - `SlurmScheduler` for scheduled command and callable jobs
  - `PanDAiDDSScheduler` implementation
  - Scheduler selection at global, workflow, branch, and stage scope
  - Artifact collection from configured job outputs

**Optimizers**

  - Shared trial tracking through `BaseOptimizer`
  - `AxOptimizer` for Bayesian optimization
  - `PyMOOOptimizer` for evolutionary optimization
  - Minimize and maximize objective directions
  - Failed-trial status and configured penalty objectives
  - Configurable maximum failed-trial limit
  - Optimization-result and Pareto-front export

**CLI optimization**

  - `aid2e optimize` loads and validates `FullConfig`
  - Optimizer candidates are submitted as scheduler-backed trial batches
  - Each trial executes one complete configured workflow
  - Objective results update the optimizer before the next batch

**Validated examples**

- [DTLZ2 framework example](examples/dtlz2/dtlz2_optimization.yml)
- [dRICH ePIC workflow example](examples/epic/drich/)

## Known Limitations

  - Configured scheduler retry fields do not currently trigger retries
  - PyMOO does not currently enforce design constraints
  - Multiple jobs returning the same direct objective require an explicit aggregation plan to avoid ambiguous results

## Future Enhancements

  - Planned CLI workflow and utility commands (`run`, `resume`, `status`, `stop`, `clean`, `init`, and `graph`)
  - Configuration composition and inheritance, an interactive configuration builder, and shell completion
  - Expanded plugin support for custom optimizers
  - Native PyMOO design-constraint enforcement and expanded constraint support for non-linear and complex expressions, constraint simplification, and automatic tightening
  - Multiple configured workflows and mixed stack types within a workflow collection
  - Explicit workflow-stage dependencies, non-linear DAG execution, asynchronous execution, and resource monitoring
  - Scheduler retry and timeout execution, advanced retry policies, and a validated scheduler/evaluator compatibility matrix
  - Optimizer uncertainty ingestion and reproducible checkpoint/resume behavior
  - Validated PanDA multi-stage execution and dataset handoff
  - Additional detector and optimization examples

## License

MIT
