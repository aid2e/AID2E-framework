# CLI and runtime

See the [CLI guide](../cli.md) for commands and output files.

## Responsibilities

| Owner | Responsibility |
|---|---|
| `src/aid2e/cli/` | Parse arguments, validate inputs, and display results. |
| `run_optimization()` | Request candidate batches, schedule trials, update the optimizer, apply failure policy, and export results. |
| `run_trial_workflow()` | Prepare and execute one trial with its own work/output directories. |

Both runtime functions live in `src/aid2e/utilities/runtime_builders.py`.
Reuse this loop for new entrypoints.

The global scheduler receives `run_trial_workflow` with a config path, trial
index, and design point. Jobs inside the workflow receive `JobContext`.
Scheduler adapters must preserve the submitted callable's argument contract.

## CLI structure

`aid2e_cli.py` registers commands; `_helpers.py` handles shared formatting.
`config_commands.py`, `workflow_commands.py`, and `utility_commands.py` group
commands by purpose. Plugins use the `aid2e.commands` entrypoint group.

Main's [CLI design](https://github.com/aid2e/AID2E-framework/blob/ed8149a2f99c545235369224c52434c4136355d6/docs/CLI_DESIGN.md)
keeps commands independently testable, with compact output, optional detail,
and JSON/YAML for scripting.

## Reporting

Run records stay in the existing runtime; backend-specific files are returned
by `save_optimization_results()`. Submission/collection timestamps do not measure
worker start times. Model export does not trigger an extra fit; see
[optimizer state](optimizers.md#state-and-model-export).

`run`, `resume`, `status`, `stop`, `clean`, `init`, and `graph` are unregistered
placeholders, not available commands.
