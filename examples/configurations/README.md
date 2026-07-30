# Example Configuration Files

This directory contains canonical full-config examples for the current AID2E
configuration loader and CLI.

## DTLZ2 Toy Problem

`dtlz2_optimization.yml` is a small multi-objective toy optimization using the
current objective `steps` API and the JobLib scheduler.

```bash
aid2e optimize examples/configurations/dtlz2_optimization.yml --validate-only
aid2e optimize examples/configurations/dtlz2_optimization.yml
```

## ePIC Tracking Skeleton

`epic_tracking_optimization.yml` shows the current ePIC problem-config shape:

- `epic_environment`
- `inline_design.epic_design_space`
- stack-aware workflow configuration

It is a configuration skeleton for detector workflows and requires a real ePIC
software environment plus executable workflow stages before it can be used as a
complete optimization run.

## Current Full-Config Shape

```yaml
problem:
  name: "Problem Name"
  problem_type: "toy"
  output_location: "./output"
  work_location: "./work"
  inline_design:
    design_space:
      design_parameters: {}
  objectives:
    - name: "f1"
      direction: "minimize"
      objective_plan:
        steps:
          stages:
            - name: "evaluate"
              inline:
                entrypoint: "module:function"
              produces_objective: true
      metrics_keys: ["f1"]

optimizer:
  name: "ax"
  type: "bayesian"
  parameters:
    n_initial_samples: 4
    n_iterations: 8
    batch_size: 2

scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 2
    backend: "threading"

workflows:
  workflows:
    - name: "evaluation"
      branches: []
```
