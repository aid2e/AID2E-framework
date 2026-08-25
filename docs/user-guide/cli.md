# AID2E CLI

## Overview

The AID2E CLI provides commands for inspecting and validating configuration
files and running optimization workflows. See the
[configuration guide](configuration.md) for supported configuration types.

## CLI Modules

The CLI is organized into focused modules under `src/aid2e/cli/`:

- `aid2e_cli.py`: Main CLI group, command registration, and plugin discovery.
- `_helpers.py`: Shared configuration detection and output formatting.
- `config_commands.py`: Configuration inspection through `describe`, `inspect`,
  and `validate`.
- `workflow_commands.py`: Workflow commands `optimize`, `run`, `resume`, `stop`,
  `status`, and `clean`.
- `utility_commands.py`: Utility commands `list`, `version`, `init`, and `graph`.
- `__init__.py`: Exports the main `cli` group.

This structure separates command registration, configuration inspection,
workflow execution, and shared helpers. Some commands are registered, while
others have placeholders for planned commands. See below for details on
commands and plans.

## Import Patterns

Only registered commands are available through `aid2e`. Unregistered
placeholders describe planned commands and are documented separately below.
The Click group can also be imported from `aid2e.cli`:

```python
from aid2e.cli import cli
```

## CLI Commands

The currently registered command surface is:

```text
aid2e
|-- describe     configuration summary
|-- inspect      detailed configuration inspection
|-- validate     configuration validation
|-- optimize     config-driven optimization
|-- list         available optimizers, templates, and problem types
`-- version      framework version
```

The source also preserves unregistered placeholders for planned commands:

- Workflow lifecycle: `run`, `resume`, `stop`, `status`, and `clean`.
- Utilities: `init` and `graph`.

These placeholders are not available through `aid2e` until they are implemented
and registered.

## Implemented Commands

### `aid2e describe <config_file>`

**Purpose:** Quick, human-readable summary with automatic configuration type
detection.

**Features:**

- Detects `full`, `problem`, `optimizer`, or `design` configurations.
- Supports compact and detailed output.
- Supports text, JSON, and YAML output.

**Usage:**

```bash
aid2e describe config.yml
aid2e describe design.params --compact
aid2e describe config.yml --format json
aid2e describe config.yml --format yaml
```

### `aid2e inspect <config_file>`

**Purpose:** Detailed inspection with optional section filtering.

**Features:**

- Filters with `--section [problem|optimizer|design|all]`.
- Displays parameter bounds, choices, and constraints.
- Replaces and extends the previous `info` command.

**Usage:**

```bash
aid2e inspect config.yml
aid2e inspect config.yml --section optimizer
aid2e inspect config.yml --section design
aid2e inspect config.yml --section problem
```

### `aid2e validate <config_file>`

**Purpose:** Validate configuration syntax and structure without executing it.

**Features:**

- Detects the configuration type.
- Validates with the corresponding loader and model.
- Reports validation errors.
- Exits with code 0 on success and 1 on failure.

**Usage:**

```bash
aid2e validate config.yml
aid2e validate design.params
aid2e validate problem.yml
```

### `aid2e optimize <config_file>`

**Purpose:** Run config-driven optimization through the configured optimizer,
scheduler, and workflow.

**Options:**

- `--validate-only`: Validate the configuration without executing it.
- `-v`, `--verbosity`: Increase logging verbosity; may be repeated.
- `--log FILE`: Write logs to a file.
- `--workflow TEXT`: Select a workflow when the configuration declares more
  than one.
- `--output DIRECTORY`: Override the configured output directory.
- `--run-id TEXT`: Set the run directory name.

**Usage:**

```bash
aid2e optimize workflow.yml
aid2e optimize workflow.yml --validate-only
aid2e optimize workflow.yml --workflow workflow_name
aid2e optimize workflow.yml -vv --log output.log
```

### `aid2e list [optimizers|templates|problems]`

**Purpose:** Display available optimizers, templates, and problem types.

**Usage:**

```bash
aid2e list
aid2e list optimizers
aid2e list templates
aid2e list problems
```

### `aid2e version`

**Purpose:** Display the installed AID2E framework version.

```bash
aid2e version
```

## Planned Commands

### `aid2e run <config_file>`

Execute one configured workflow without the optimizer loop. Planned behavior
includes workflow and scheduler setup, objective collection, output-directory
overrides, and a dry-run mode.

### `aid2e resume <checkpoint>`

Resume an interrupted optimization from saved state and continue from a
specified iteration.

### `aid2e status`

Report active and completed runs, iteration progress, and current objective
results.

### `aid2e stop <run_id>`

Stop a running optimization and preserve a checkpoint when possible.

### `aid2e clean <output_dir>`

Remove temporary and intermediate files, with a dry-run mode to preview the
operation.

### `aid2e init`

Create configuration files from templates, including an interactive mode.

### `aid2e graph <config_file>`

Visualize workflow dependencies and export the graph to a supported file
format.

## Testing

```bash
aid2e --help
aid2e describe examples/configurations/dtlz2_optimization.yml
aid2e inspect examples/configurations/dtlz2_optimization.yml
aid2e validate examples/configurations/dtlz2_optimization.yml
aid2e optimize examples/configurations/dtlz2_optimization.yml --validate-only
aid2e list
aid2e version
```

## Related Files

- CLI implementation: `src/aid2e/cli/`
- Configuration models and loaders: `src/aid2e/utilities/configurations/`
- CLI tests: `tests/test_cli/`
- Example configurations: `examples/configurations/`

For issues or questions, use the
[AID2E issue tracker](https://github.com/aid2e/AID2E-framework/issues).
