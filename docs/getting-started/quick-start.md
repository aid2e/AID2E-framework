# Quick Start

Follow the [installation guide](installation.md), then run the following
commands from the repository root. Confirm that the `aid2e` command is
available:

```bash
aid2e version
aid2e --help
```

## Review the Example Configuration

The DTLZ2 example is a full configuration with an optimizer (Ax), a
scheduler (JobLib), and an inline objective evaluator:

```bash
aid2e describe examples/dtlz2/dtlz2_optimization.yml
```

## Validate the Configuration

Validate the complete optimization configuration without executing it:

```bash
aid2e optimize examples/dtlz2/dtlz2_optimization.yml --validate-only
```

## Run the Optimization

```bash
aid2e optimize examples/dtlz2/dtlz2_optimization.yml
```

For this Ax example, `n_iterations` controls the total number of trial
evaluations:

```yaml
optimizer:
  parameters:
    n_iterations: 100
```

Reduce `n_iterations` for a shorter initial run. The optimizer, scheduler, and
their parameters can be changed in the same configuration.

## Review the Results

Each run creates a directory under:

```text
examples/dtlz2/output/dtlz2/<run-id>/
```

The primary outputs are `optimization_results.json` and `pareto_front.json`.

See the [CLI guide](../user-guide/cli.md) for configuration inspection,
workflow selection, output overrides, logging, and other commands.
