# AID2E CLI

## Overview

The AID2E CLI provides commands for inspecting configuration files and running optimization workflows. See the [configuration guide](configuration.md) for supported configuration types.

## CLI Commands

The available commands are:

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

**Purpose:** Quick, human-readable summary with automatic configuration type detection.

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

**Purpose:** Run config-driven optimization through the configured optimizer, scheduler, and workflow.

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

## Verify the CLI

```bash
aid2e --help
aid2e describe examples/dtlz2/configurations/dtlz2_ax_joblib.yml
aid2e inspect examples/dtlz2/configurations/dtlz2_ax_joblib.yml
aid2e validate examples/dtlz2/configurations/dtlz2_ax_joblib.yml
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib.yml --validate-only
aid2e list
aid2e version
```

## Run records

After each completed batch, `aid2e optimize` saves `optimization_results.json` (trial results) and `pareto_front.json` (Pareto solutions) under `<output>/<run-id>/`. Records include design parameters, objectives, objective errors, and trial metadata. Trial results also include status. Trial workflow outputs are kept under `trials/trial_<index>/`. Use `--log FILE` and verbosity settings to save trial progress.

Objective fields named `<objective>_err` are saved as `objective_errors`; they are not yet passed to Ax as standard errors. Penalized trials retain the penalty flag and failure reason in metadata, and count toward `max_failed_trials`.

`--validate-only` checks configuration loading; it does not execute jobs or verify the external software environment. Saved results do not provide automatic CLI resume.

See the [CLI and runtime notes](notes/cli.md) for module structure, planned commands, and runtime responsibilities.
