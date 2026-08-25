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

### Problem and Objective Definition

  - Load configuration from YAML/dict
  - Problem, optimizer, scheduler, design, objective, and workflow specs
  - Full validation through Pydantic
  - ObjectiveDirection (MINIMIZE/MAXIMIZE)
  - ObjectivePlanSpec (inline/script/multi-step plans)
  - ObjectiveDefinition (name, direction, and optional objective plan)
  - Direct objective collection when workflow jobs return declared objectives
  - Inline Python functions referenced by entrypoint
  - Scripts configured by file path
  - Optional objective error values through *_err fields

### Workflow Infrastructure

  - DagDefinition with edge inference
  - DagNode, DagEdge with flexible typing
  - topological_sort() with Kahn's algorithm (O(V+E))
  - detect_cycles() with DFS-based cycle detection
  - DagValidator with comprehensive checks
  - Execution layer computation for parallelization
  - Sequential stages and parallel jobs within stages
  - Range and payload job factories
  - Generic and stack execution engines
  - Workflow configuration models live in utilities/configurations/
  - Workflow execution lives in utilities/workflows/
  - Stack-specific configuration and execution are resolved through
    StackRegistry
  - ePIC-specific utilities remain under utilities/epic_utils/

### Scheduler Infrastructure

  - BaseScheduler abstract class with a common stage execution interface
  - JobLibScheduler for local parallel execution
  - SlurmScheduler for scheduled command and callable jobs
  - PanDAiDDSScheduler implementation
  - Scheduler selection at global, workflow, branch, and stage scope
  - Artifact collection from configured job outputs

### Optimizer Infrastructure

  - BaseOptimizer abstract class with shared trial tracking
  - AxOptimizer for Bayesian optimization
  - PyMOOOptimizer for evolutionary optimization
  - Objective direction, result, failure, and penalty handling
  - Failed optimizer trial status
  - Configured penalty objectives
  - Maximum failed-trial limit
  - Optimization and Pareto-front result export

### CLI Optimization Workflow

  - aid2e optimize loads and validates FullConfig
  - Optimizer candidates are submitted as scheduler-backed trial batches
  - Each trial executes one complete configured workflow
  - Objective results update the optimizer before the next batch

### Validated Examples

  - DTLZ2 framework example
  - dRICH ePIC workflow example

## Known Limitations

  - Configured scheduler retry fields do not currently trigger retries
  - PyMOO does not currently enforce design constraints
  - PanDA/iDDS dataset handoff requires additional validation
  - Multiple jobs returning the same direct objective require an explicit
    aggregation plan to avoid ambiguous results

## Planned Work

### Release Validation

  - Complete clean-install and supported-platform checks
  - Maintain a tested optimizer, scheduler, and workflow compatibility matrix
  - Complete backend-specific validation where external services are required

### Documentation and Examples

  - Complete public documentation cleanup
  - Retain and maintain the release examples
  - Document supported backend combinations and external requirements

### Future Enhancements

  - Planned CLI workflow lifecycle commands
  - Advanced retry policies
  - Additional detector and optimization examples

## License

MIT
