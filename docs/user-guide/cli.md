# AID2E CLI

## Overview

The AID2E CLI provides commands for inspecting configuration files and running optimization workflows. See the [configuration guide](configuration.md) for supported configuration types.

## CLI Commands

The currently registered command surface is:

```text
aid2e
|-- describe     configuration summary
|-- inspect      detailed configuration inspection
|-- validate     configuration validation
|-- optimize     config-driven optimization
|-- list         available optimizers/templates/problems
`-- version      framework version
```

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
- Returns `0` on success, `1` when validation fails, and `2` for invalid CLI
  usage. Any other nonzero exit code also indicates failure.

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
- `--workflow TEXT`: Select a workflow when the configuration declares more than one.
- `--output DIRECTORY`: Override the configured output directory.
- `--run-id TEXT`: Set the run directory name under the output directory. When
  omitted, AID2E uses a timestamp in `YYYYMMDD_HHMM` format.

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

These commands have source placeholders but are not registered with `aid2e`:

- Workflow: `run`, `resume`, `status`, `stop`, and `clean`.
- Configuration utilities: `init` and `graph`.

## Developer Reference

**Python import**

Only registered commands are available through `aid2e`. The Click group can
also be imported from Python:

```python
from aid2e.cli import cli
```

**Implementation modules**

The CLI is organized into modules under `src/aid2e/cli/`:

- `aid2e_cli.py`: Main CLI group, command registration, and plugin discovery.
- `_helpers.py`: Shared configuration helpers and output formatting.
- `config_commands.py`: Configuration commands `describe`, `inspect`, and
  `validate`.
- `workflow_commands.py`: Implements `optimize` and contains placeholders for
  `run`, `resume`, `stop`, `status`, and `clean`.
- `utility_commands.py`: Implements `list` and `version` and contains
  placeholders for `init` and `graph`.
- `__init__.py`: Exports the main `cli` group.

## Verify the CLI

```bash
aid2e --help
aid2e describe examples/dtlz2/dtlz2_optimization.yml
aid2e inspect examples/dtlz2/dtlz2_optimization.yml
aid2e validate examples/dtlz2/dtlz2_optimization.yml
aid2e optimize examples/dtlz2/dtlz2_optimization.yml --validate-only
aid2e list
aid2e version
```

## Related Files

- CLI implementation: `src/aid2e/cli/`
- Configuration models and loaders: `src/aid2e/utilities/configurations/`
- CLI tests: `tests/test_cli/`
- Examples: `examples/`
