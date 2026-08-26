# AID2E CLI Design and Implementation Plan

## Overview

The AID2E CLI provides a comprehensive command-line interface for managing optimization workflows, from configuration validation to execution. The CLI is designed around three configuration types that work together:

1. **DesignConfig** - Defines the parameter search space and constraints
2. **ProblemConfiguration** - Embeds design config + objectives + paths
3. **OptimizationConfiguration** - Defines optimizer selection and settings

## Modular Code Structure

The CLI is organized into focused modules for maintainability and extensibility:

```
src/aid2e/cli/
├── __init__.py                 # Exports main cli group
├── aid2e_cli.py                # Main CLI group + plugin loader + command registration
├── _helpers.py                 # Shared utilities (config detection, formatters)
├── config_commands.py          # Config inspection: describe, inspect, validate
├── workflow_commands.py        # Execution: optimize, run (future)
├── utility_commands.py         # Utilities: list, version

```

### Module Responsibilities

| Module | Purpose | Lines | Commands |
|--------|---------|-------|----------|
| `aid2e_cli.py` | Main entry point, command registration, plugin discovery | ~100 | N/A (coordinator) |
| `_helpers.py` | Shared utilities for config detection and formatting | ~400 | N/A (library) |
| `config_commands.py` | Configuration inspection and validation | ~170 | describe, inspect, validate |
| `workflow_commands.py` | Workflow execution and lifecycle management | ~150 | optimize, run*, resume*, stop*, status*, clean* |
| `utility_commands.py` | Information and resource listing | ~90 | list, version, init*, graph* |

*Planned commands not yet implemented

### Import Patterns

The CLI group is exported from `aid2e.cli`:

```python
from aid2e.cli import cli
```

## CLI Command Structure

```
aid2e
├── [Config Inspection]
│   ├── describe     # Quick summary of any config file (auto-detects type)
│   ├── inspect      # Detailed inspection with section filtering
│   └── validate     # Syntax and structure validation
├── [Workflow Execution]
│   ├── optimize     # Run optimization from full config
│   ├── run          # Execute one workflow without optimizer loop (planned)
│   ├── resume       # Restart from checkpoint (planned)
│   ├── stop         # Halt running optimization (planned)
│   ├── status       # Check progress (planned)
│   └── clean        # Remove temporary files (planned)
├── [Utilities]
│   ├── list         # Available optimizers/templates/problems
│   ├── version      # Display version
│   ├── init         # Create configs from templates (planned)
│   └── graph        # Visualize workflow (planned)
```

## Implemented Commands

### 1. `aid2e describe <config_file>`

**Purpose:** Quick, human-readable summary with automatic config type detection.

**Features:**
- Auto-detects: `full`, `problem`, `optimization`, or `design` config
- Compact or detailed output modes
- Multiple output formats: text, JSON, YAML

**Usage:**
```bash
# Quick text summary
aid2e describe config.yml

# Compact output
aid2e describe design.params --compact

# JSON output for scripting
aid2e describe config.yml --format json

# YAML output
aid2e describe config.yml --format yaml
```

**Output example:**
```
======================================================================
Configuration: dtlz2_optimization.yml
Type: FULL
======================================================================

PROBLEM
  Name: DTLZ2 Multi-Objective Optimization
  Type: toy
  Output: ./output/dtlz2
  Work Dir: ./work/dtlz2
  Design: design.params (file)
  Objectives: 2
    - f1: minimize
    - f2: minimize

OPTIMIZATION
  Algorithm: ax (Bayesian)
  Iterations: 50
  Initial Samples: 10
  Parallel: 1
  Parameters:
    initialization_strategy: sobol
    generator: BOTORCH_MODULAR
    batch_size: 2
```

### 2. `aid2e inspect <config_file>`

**Purpose:** Detailed inspection with optional section filtering.

**Features:**
- Section filtering: `--section [problem|optimization|design|all]`
- Full parameter listings with bounds/choices
- Constraint details
- Replaces/enhances the old `info` command

**Usage:**
```bash
# Inspect entire configuration
aid2e inspect config.yml

# Inspect only optimization section
aid2e inspect config.yml --section optimization

# Inspect only design parameters
aid2e inspect config.yml --section design

# Inspect only problem definition
aid2e inspect config.yml --section problem
```

**Output example:**
```
======================================================================
Configuration: DTLZ2 Multi-Objective Optimization
======================================================================

PROBLEM CONFIGURATION
  Name: DTLZ2 Multi-Objective Optimization
  Type: toy
  Output Location: ./output/dtlz2
  Work Location: ./work/dtlz2

DESIGN PARAMETERS

  DTLZ2_variables (10 parameters):
    - x1: 0.5 (0.0, 1.0)
    - x2: 0.0 (0.0, 1.0)
    ...

PARAMETER CONSTRAINTS
  - simple_constraint
    Rule: DTLZ2_variables.x1 < 1.0
    Description: x1 must be less than 1.0

OPTIMIZATION CONFIGURATION
  Name: dtlz2-optimization
  Optimizer: ax (Bayesian)
  Iterations: 50
  Initial Samples: 10
  Parallel Evaluations: 1

  Objectives (2):
    - minimize:f1
    - minimize:f2

  Optimizer Parameters:
    - initialization_strategy: sobol
    - generator: BOTORCH_MODULAR
    - batch_size: 3
    - seed: 42

======================================================================
```

### 3. `aid2e validate <config_file>`

**Purpose:** Validate configuration syntax and structure without full execution.

**Features:**
- Auto-detects config type
- Validates using appropriate loader/model
- Reports specific validation errors
- Exit code 0 on success, 1 on failure

**Usage:**
```bash
# Validate any config type
aid2e validate config.yml

# Validate design parameters
aid2e validate design.params

# Validate problem config
aid2e validate problem.yml
```

**Output examples:**
```
# Success
Validating full configuration...
✓ Configuration is valid!
  Type: full
  Parameters: 10

# Failure
Validating design configuration...
✗ Validation failed: Invalid constraint 'bad_constraint': Unknown parameters in constraint: DTLZ2.unknown
```

### 4. `aid2e list [optimizers|templates|problems]`

**Purpose:** Display available optimizers, templates, and problem types.

**Features:**
- Lists all categories when no argument provided
- Shows optimizer capabilities and use cases
- Lists available templates
- Documents supported problem types

**Usage:**
```bash
# List everything
aid2e list

# List only optimizers
aid2e list optimizers

# List only templates
aid2e list templates

# List only problem types
aid2e list problems
```

**Output example:**
```
Available Optimizers:
  • ax (Bayesian Optimization)
    - Initialization: Sobol quasi-random
    - Surrogate: SAASBO (Sparse Axis-Aligned Subspace BO)
    - Acquisition: qNEHVI (Noisy Expected Hypervolume Improvement)
    - Use case: Multi-objective optimization, continuous parameters

Available Templates:
  • dtlz2 - Multi-objective test problem (2 objectives, 10 variables)
  • basic - Minimal configuration template
  • epic_tracking - EPIC detector tracking optimization

Supported Problem Types:
  • toy - Benchmark test problems (DTLZ2, ZDT, etc.)
  • epic_tracking - EPIC detector tracking system
  • custom - User-defined evaluation functions
```

## Commands

`aid2e optimize` is the current command for full optimization execution.

### 5. `aid2e run <config_file>`

**Purpose:** Execute one configured workflow once, without the optimizer loop.

**Supported features:**
- Single workflow execution from config
- Problem, workflow, and scheduler setup
- Objective/result collection
- Output directory override
- Dry-run mode

**Usage:**
``
```bash
# Run one configured workflow
aid2e run config.yml

# Dry run (validate and show execution plan)
aid2e run config.yml --dry-run

# Override output location
aid2e run config.yml --output results/experiment_1/

# Verbose logging
aid2e run config.yml -vv --log output.log
```

### 6. `aid2e resume <checkpoint>` (WIP, HIGH PRIORITY)

**Purpose:** Resume an interrupted optimization run.

**Planned features:**
- Restart interrupted optimization from saved state
- Continue from specific iteration
- Merge results with previous runs

### 7. `aid2e status` (WIP, MEDIUM PRIORITY)

**Purpose:** Check progress of active or completed optimization runs.

**Planned features:**
- Show active runs
- Display iteration progress
- Show current best objectives
- List completed runs

### 8. `aid2e stop <run_id>` (WIP, MEDIUM PRIORITY)

**Purpose:** Gracefully halt a running optimization.

**Planned features:**
- Stop by run ID or process ID
- Save checkpoint before stopping
- Force stop option

### 9. `aid2e clean <output_dir>` (WIP, LOW PRIORITY)

**Purpose:** Remove temporary and intermediate files.

**Planned features:**
- Clean work directories
- Remove old checkpoints
- Dry-run to preview deletions

### 10. `aid2e init` (WIP, MEDIUM PRIORITY)

**Purpose:** Create new configuration files from templates.

**Planned features:**
- Template-based generation
- Interactive wizard mode
- Type-specific templates (design/problem/optimization)

**Planned usage:**
```bash
# Initialize from template
aid2e init --template dtlz2

# Create specific config type
aid2e init --type design > design.yml
aid2e init --type problem > problem.yml
aid2e init --type optimization --optimizer ax > optimization.yml

# Interactive mode
aid2e init --interactive
```

### 11. `aid2e graph <config_file>` (WIP, LOW PRIORITY)

**Purpose:** Visualize workflow structure and dependencies.

**Planned features:**
- Dependency graph generation
- Export to PNG/SVG/DOT
- Show parameter flow

**Planned usage:**
```bash
# Display workflow graph
aid2e graph config.yml

# Export to file
aid2e graph config.yml --output workflow.png
aid2e graph config.yml --format svg
```

## Configuration Type Detection

The CLI automatically detects configuration type based on structure:

```python
def _detect_config_type(data: dict) -> str:
    """Auto-detect configuration type."""
    if "problem" in data and "optimization" in data:
        return "full"           # Full workflow config
    elif "problem" in data:
        return "problem"        # Problem-only config
    elif "optimization" in data:
        return "optimization"   # Optimizer-only config
    elif "design_space" in data or "design_parameters" in data:
        return "design"         # Design space only
    else:
        return "unknown"
```

## Configuration Hierarchy

```
FullConfiguration (loaded via load_config())
├── ProblemConfiguration
│   ├── DesignConfig (embedded)
│   │   ├── DesignParameters (parameter groups)
│   │   └── ParameterConstraints (optional)
│   ├── objectives
│   └── output/work paths
└── OptimizationConfiguration
    ├── OptimizerConfig
    │   ├── name (e.g., "ax")
    │   ├── type (e.g., "Bayesian")
    │   └── parameters (algorithm-specific)
    ├── objectives
    ├── n_iterations
    └── parallel_evaluations
```

## YAML Structure Examples

### Full Configuration
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

### Design Configuration (design.params)
```yaml
design_space:
  design_parameters:
    DTLZ2_variables:
      parameters:
        x1: {value: 0.5, bounds: [0.0, 1.0]}
        x2: {value: 0.0, bounds: [0.0, 1.0]}
        # ... x3-x10

  design_constraints:
    - name: simple_constraint
      description: x1 must be less than 1.0
      rule: DTLZ2_variables.x1 < 1.0
```

### Problem Configuration Only
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

### Optimizer Configuration Section
```yaml
optimizer:
  name: ax
  type: bayesian
  parameters:
    n_initial_samples: 4
    n_iterations: 8
    batch_size: 2
```

## Implementation Status

### Modular Reorganization (v0.3.0)

**✅ COMPLETED** - CLI has been reorganized into modular structure:

| Module | Status | Lines | Purpose |
|--------|--------|-------|---------|
| `_helpers.py` | ✅ Complete | ~400 | Shared utilities and formatters |
| `config_commands.py` | ✅ Complete | ~170 | Config inspection commands |
| `workflow_commands.py` | ✅ Complete | ~150 | Optimization execution and planned workflow lifecycle commands |
| `utility_commands.py` | ✅ Complete | ~90 | Resource listing, version, and planned utility commands |
| `aid2e_cli.py` | ✅ Complete | ~100 | Main group and command registration |
| `__init__.py` | ✅ Complete | ~20 | Package exports |

### Command Implementation Status

| Command | Module | Status | Priority | Notes |
|---------|--------|--------|----------|-------|
| `describe` | config_commands | ✅ Complete | High | Auto-detects type, multiple formats |
| `inspect` | config_commands | ✅ Complete | High | Section filtering, detailed output |
| `validate` | config_commands | ✅ Complete | High | Type-aware validation |
| `list` | utility_commands | ✅ Complete | Medium | Optimizers/templates/problems |
| `version` | utility_commands | ✅ Complete | Low | Version display |
| `optimize` | workflow_commands | ✅ Complete | High | Runs config-driven optimization |
| `run` | workflow_commands | ⏳ Planned | High | Single workflow execution without optimizer loop |
| `resume` | workflow_commands | ⏳ Planned | High | Checkpoint restart |
| `stop` | workflow_commands | ⏳ Planned | Medium | Graceful halt |
| `status` | workflow_commands | ⏳ Planned | Medium | Progress monitoring |
| `clean` | workflow_commands | ⏳ Planned | Low | Cleanup temporary files |
| `init` | utility_commands | ⏳ Planned | Medium | Template generation |
| `graph` | utility_commands | ⏳ Planned | Low | Workflow visualization |

### Benefits of Modular Structure

1. **Maintainability**: Each module ~100-400 lines vs 740-line monolith
2. **Testability**: Commands can be unit tested independently
3. **Extensibility**: New commands added to appropriate module
4. **Clarity**: Functional grouping matches user mental model
5. **Simplicity**: No legacy command surface to maintain

## Design Principles

1. **Auto-detection**: Commands should detect config type automatically
2. **Consistency**: Similar output formats across commands
3. **Composability**: Output formats (JSON/YAML) for scripting
4. **Clear errors**: Specific, actionable error messages
5. **Progressive disclosure**: Compact by default, detailed on demand
6. **Exit codes**: 0 for success, 1 for failure (script-friendly)

## Next Steps

### Completed (v0.3.0)
- [x] Reorganize CLI into modular structure
- [x] Create `_helpers.py` for shared utilities
- [x] Create `config_commands.py` (describe/inspect/validate)
- [x] Create `workflow_commands.py` (optimize execution)
- [x] Create `utility_commands.py` (list/version)
- [x] Refactor `aid2e_cli.py` to main group coordinator
- [x] Update `__init__.py` for backward compatibility
- [x] Update CLI_DESIGN.md documentation

### Immediate
- [ ] Test `aid2e optimize` with full-config examples
- [ ] Verify CLI entry point: `aid2e --help`
- [ ] Add single-workflow execution as a separate `aid2e run` command
  - [ ] Test with a full config containing `workflows`

### Near Term
- [ ] Implement `run` command with WorkflowOrchestrator
- [ ] Add `resume` command for checkpoint restart
- [ ] Add `status` command for progress monitoring
- [ ] Auto-register AxOptimizerConfig in registry
- [ ] Create template system for `init` command

### Future
- [ ] Add `graph` command for visualization
- [ ] Add `clean` command for file cleanup
- [ ] Support for config composition/inheritance
- [ ] Interactive config builder
- [ ] Shell completion (bash/zsh/fish)
- [ ] Extended plugin system for custom optimizers

## Testing Strategy

```bash
# Test describe command
aid2e describe examples/basic/full_example.yml
aid2e describe examples/basic/design.params --compact

# Test inspect command
aid2e inspect examples/basic/full_example.yml
aid2e inspect examples/basic/full_example.yml --section optimization

# Test validate command
aid2e validate examples/basic/full_example.yml
aid2e validate examples/basic/design.params

# Test list command
aid2e list
aid2e list optimizers
aid2e list templates
```

## Related Files

- **CLI Implementation**: `src/aid2e/cli/aid2e_cli.py`
- **Config Loaders**:
  - `src/aid2e/utilities/configurations/design_config.py`
  - `src/aid2e/utilities/configurations/problem_config.py`
  - `src/aid2e/utilities/configurations/optimization_config.py`
  - `src/aid2e/utilities/configurations/full_config.py`
- **Example Configs**: `examples/basic/`, `tests/test_utilities/fixtures/dtlz2/`
- **Documentation**: `docs/CONSTRAINT_HANDLING.md`, `README.md`

## Support

For issues or questions about the CLI:
- Repository: https://github.com/aid2e/AID2E-framework
- Documentation: https://aid2e.github.io/AID2E-framework
- Issues: https://github.com/aid2e/AID2E-framework/issues
