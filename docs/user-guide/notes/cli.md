# CLI and runtime

See the [CLI guide](../cli.md) for commands, options, and output files.

## CLI structure

```text
src/aid2e/cli/
├── __init__.py           # Exports the CLI group
├── aid2e_cli.py          # Command registration and plugin loading
├── _helpers.py           # Configuration detection and formatting
├── config_commands.py    # describe, inspect, validate
├── workflow_commands.py  # optimize and planned workflow commands
└── utility_commands.py   # list, version and planned utilities
```

The CLI keeps commands independently testable, with compact output, optional detail, and JSON/YAML for scripting. Plugins use the `aid2e.commands` entrypoint group.

## Command structure

Commands marked `planned` are not registered or available through the CLI.

```text
aid2e
├── Config inspection
│   ├── describe     # Configuration summary with automatic type detection
│   ├── inspect      # Detailed inspection with section filtering
│   └── validate     # Syntax and structure validation
├── Workflow execution
│   ├── optimize     # Run optimization from a full configuration
│   ├── run          # Execute a workflow without optimization (planned)
│   ├── resume       # Restart from a checkpoint (planned)
│   ├── stop         # Halt a running optimization (planned)
│   ├── status       # Check progress (planned)
│   └── clean        # Remove temporary files (planned)
└── Utilities
    ├── list         # Available optimizers, templates, and problems
    ├── version      # Installed framework version
    ├── init         # Create configurations from templates (planned)
    └── graph        # Visualize a workflow (planned)
```

## Runtime responsibilities

`run_optimization()` schedules trial batches, updates the optimizer, and exports results. `run_trial_workflow()` prepares and executes one trial with its own work/output directories. Both functions live in `src/aid2e/utilities/runtime_builders.py`.

The global scheduler receives `run_trial_workflow` with a configuration path, trial index, and design point. Jobs inside the workflow receive `JobContext`. Scheduler adapters must preserve the submitted callable's argument.

Run records stay in the existing runtime; files are returned by `save_optimization_results()`. 
