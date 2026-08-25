# Quick Start

Follow the [installation guide](installation.md), then confirm that the
`aid2e` command is available:

```bash
aid2e --version
aid2e --help
```

## Review the Example Configuration

The DTLZ2 example is a full configuration with an optimizer (Ax), a
scheduler (JobLib), and an inline objective evaluator:

```bash
aid2e describe examples/configurations/dtlz2_optimization.yml
```

## Validate the Workflow

Validate the complete optimization configuration without executing it:

```bash
aid2e optimize examples/configurations/dtlz2_optimization.yml --validate-only
```

## Run the Optimization

```bash
aid2e optimize examples/configurations/dtlz2_optimization.yml
```

The number of trial evaluations is configured in the optimizer parameters:

```yaml
optimizer:
  parameters:
    n_iterations: 100
```

The optimizer, scheduler, and their parameters can be changed in the same
configuration. Results are written below the configured
`examples/configurations/output/dtlz2/` directory.

See the [CLI guide](../user-guide/cli.md) for configuration inspection,
workflow selection, output overrides, logging, and other commands.
