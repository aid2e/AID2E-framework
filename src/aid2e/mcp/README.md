# AID2E MCP Server

The AID2E MCP server gives coding assistants a verified view of the installed
AID2E framework, and safe tools for building AID2E extensions in your own
project. It has two strictly separated tool groups:

- **Source Reference tools (read-only):** inspect the installed `aid2e`
  package and its `examples/`. File tools refuse changes to that source.
- **Workspace tools:** read, create, edit, and validate files in your project.

To use the AID2E-hosted model from your own machine, follow
[Connect to the AID2E-hosted model](#connect-to-the-aid2e-hosted-model).

## Install

AID2E needs Python 3.11 or newer.

```bash
python -m pip install "aid2e[mcp]"
# or, from a checkout: python -m pip install -e ".[mcp]"
```

## Connect to the AID2E-hosted model

These steps connect a client on your own machine to the AID2E LiteLLM gateway
through an SSH tunnel. The default model is **Qwen 3.8 Flash-Next**
(`qwen-3.8-flash-next`). The AID2E tools run on your machine and work on your
local files.

```text
your client -> 127.0.0.1:4001 -> SSH tunnel -> SciClone 127.0.0.1:4000 -> LiteLLM gateway -> model
```

### What you need

- AID2E installed with its `mcp` extra (see [Install](#install)).
- An account that can SSH to `cm.geo.sciclone.wm.edu`. Connect to the W&M VPN
  first if you're off campus.
- A personal API key beginning with `sk-`. To request one, email
  [jgiroux@wm.edu](mailto:jgiroux@wm.edu) with your W&M username. Don't share
  your key or commit it to a repository.
- [OpenCode](https://opencode.ai) if you want the terminal client:
  `curl -fsSL https://opencode.ai/install | bash`. For VS Code, see
  [step 4](#4-start-your-client).

### 1. Open the tunnel

In a separate terminal on your machine, run this command with your username:

```bash
ssh -N \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes \
  -L 4001:127.0.0.1:4000 \
  <your-wm-username>@cm.geo.sciclone.wm.edu
```

After you log in, the command prints nothing and keeps running. That means it's
working. Leave this terminal open while you use the model.

### 2. Set your API key

In the terminal where you'll run your client:

```bash
read -rsp "Paste your AID2E API key: " AID2E_LLM_API_KEY; echo; export AID2E_LLM_API_KEY
```

The key lasts only for that terminal, so repeat this step in each new one.

### 3. Check the connection

```bash
curl -sS http://127.0.0.1:4001/v1/models \
  -H "Authorization: Bearer $AID2E_LLM_API_KEY"

curl -sS http://127.0.0.1:4001/v1/chat/completions \
  -H "Authorization: Bearer $AID2E_LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "qwen-3.8-flash-next", "messages": [{"role": "user", "content": "Reply with pong."}], "max_tokens": 200}'
```

A `/v1/models` response lists the model IDs available to your API key. If your
key has access to a different model, use its exact ID in the test request.
A JSON response with a `choices` field means the tunnel, your key and the model
all work. Otherwise, see [Connection problems](#connection-problems).

### 4. Start your client

**OpenCode.** Run this once per project:

```bash
aid2e mcp init --client opencode --workspace /path/to/your/project --llm-url http://127.0.0.1:4001/v1
```

Then, each time you work:

```bash
cd /path/to/your/project
opencode mcp list     # aid2e should show as connected
opencode
```

**VS Code Chat.** Run this once per project:

```bash
aid2e mcp init --client vscode --workspace /path/to/your/project
```

In VS Code, run **Chat: Manage Language Models**, choose **Add Models** >
**Custom Endpoint**, and enter your key when prompted. Open
`chatLanguageModels.json` from the Language Models editor and use the following
configuration, with your key in both places:

```json
[
  {
    "name": "AID2E",
    "vendor": "customendpoint",
    "apiKey": "sk-PASTE-YOUR-PERSONAL-KEY-HERE",
    "apiType": "chat-completions",
    "models": [
      {
        "id": "qwen-3.8-flash-next",
        "name": "AID2E Qwen 3.8 Flash-Next",
        "url": "http://127.0.0.1:4001/v1/chat/completions",
        "toolCalling": true,
        "vision": false,
        "maxInputTokens": 253952,
        "maxOutputTokens": 8192,
        "modelOptions": { "parallel_tool_calls": false },
        "requestHeaders": {
          "Authorization": "Bearer sk-PASTE-YOUR-PERSONAL-KEY-HERE"
        }
      }
    ]
  }
]
```

This file holds your key, so keep it private. Open the project, start
`aid2eLocal` from the MCP view, and choose the **AID2E** agent and
**AID2E Qwen 3.8 Flash-Next** in Chat. To add another model or update an entry
using the old `code-assist` alias, set `id` to the exact ID from `/v1/models`.
If you use VS Code in WSL or over Remote-SSH, run the tunnel in that same
environment.

### Connection problems

| Problem | What to check |
| --- | --- |
| `Connection refused` or `ECONNREFUSED` | The tunnel isn't running. Restart step 1, on the same machine as your client. |
| `channel ... open failed: connect failed` in the tunnel terminal, or an empty reply from `curl` | The tunnel is up, but the gateway connection on SciClone is down. Email the administrator. |
| `Address already in use` when opening the tunnel | Port 4001 is taken on your machine. Use another port, such as `-L 4002:127.0.0.1:4000`. Then use that port in step 3, and in `--llm-url` or `url`. Re-running `init` updates the URL. |
| `401` or `Authentication Error` | Your key is wrong or isn't set in this terminal. Repeat step 2. |
| `model ... is not available` or `key not allowed to access model` | Compare the requested ID with `/v1/models` for your key. Contact the administrator if you need access to another model. |
| OpenCode can't reach the model, but step 3 works | The project's `opencode.json` has a different URL, or `AID2E_LLM_API_KEY` isn't exported in this terminal. Re-run `init`, then repeat step 2. |
| Long pauses | The model is shared and generates about 25 tokens per second, so long answers take a while. |

When you ask for help, send the error message but never your key.

### For the administrator

The tunnel reaches SciClone's port 4000, so keep a port-forward to the LiteLLM
service running on `cm.geo.sciclone.wm.edu`, for example in `tmux`:

```bash
while true; do
  kubectl -n ai4phys port-forward service/litellm-100b 4000:4000
  sleep 2
done
```

- **Forward the LiteLLM service.** It resolves gateway model IDs, checks each
  person's key, and records usage.
- **Use the same host for the port-forward and the tunnel.** `kubectl` listens
  only on that host's `127.0.0.1`, so a tunnel to another login node can't reach
  it.
- **Keep the loop.** A port-forward exits when its LiteLLM pod restarts, which
  every deploy does.

Create keys as described in `LITELLM-100B.md` and include the permitted gateway
IDs, such as `qwen-3.8-flash-next`, in each key's `models`.

## Which tools each client gets

| Model behind the client | Clients | Tool profile | Client's built-in tools |
| --- | --- | --- | --- |
| AID2E Code Assist (e.g. Qwen 3.8 Flash-Next) | VS Code Chat, OpenCode | `full`: Source Reference + Workspace read/write/validate | Disabled |
| Strong hosted agent | Claude Code, Codex | `reference`: Source Reference + `validate_workspace_file` | Kept |

Small models get confused by large or overlapping tool lists, so they see only
the AID2E tools, which cover everything needed to read, edit, and validate a
project. Hosted agents keep their own file tools and use AID2E as a read-only
reference. Their AID2E working rules (verify names with the tools, never
modify the Reference Source, mirror its architecture, validate new files)
arrive automatically through the server's MCP instructions.

## Set up a client: `aid2e mcp init`

Run this from the Python environment where AID2E is installed:

```bash
aid2e mcp init --client vscode   --workspace /path/to/your/project
aid2e mcp init --client opencode --workspace /path/to/your/project
aid2e mcp init --client claude   --workspace /path/to/your/project
aid2e mcp init --client codex    --workspace /path/to/your/project
```

`--workspace` defaults to the current directory. `init` writes only
project-local configuration and never writes an API key. You can set up
several clients in one project.

- **The interpreter is pinned.** Each entry launches
  `<this-python> -m aid2e.mcp --workspace <project> --tools <profile>`, so
  PATH and PYTHONPATH don't matter. Re-run `init` after moving the project or
  switching environments.
- **Your edits are kept.** `init` refreshes only the entries it owns, recorded
  in `.aid2e-workspace.json`. It refuses to overwrite an `aid2e` entry you
  added or edited, and keeps your own choices, such as a different default
  model or a tool you re-enabled.
- **Keep the generated files out of version control.** They contain
  machine-specific absolute paths; `init` lists them after writing.
- `--tools full|reference` overrides a client's default profile.

### VS Code Chat

`init --client vscode` writes:

- `.vscode/mcp.json`, which starts the `aid2eLocal` server (full profile);
- `.github/agents/aid2e.agent.md`, a custom **AID2E** agent whose tools are
  limited to `aid2eLocal/*`.

Open the project, start `aid2eLocal` from the MCP view, then choose the
**AID2E** agent and your model in Chat. Configure the model endpoint itself
under **Chat: Manage Language Models**.

The VS Code server is named `aid2eLocal` rather than `aid2e` because VS Code
may also load a root `.mcp.json`, which is where `--client claude` puts its
read-only `aid2e` server. With distinct names the two never collide, and the
AID2E agent only uses `aid2eLocal` tools. `init` warns you if a project has
both.

### OpenCode

`init --client opencode` writes `opencode.json` with:

- the `aid2e` MCP server (full profile);
- an `aid2e` provider for an OpenAI-compatible endpoint, set as the default
  model;
- OpenCode's native file/shell tools disabled, with the normal `task` tool
  enabled only for Build to delegate to `general` subagents;
- the AID2E write tools, `run_workspace_tests` and `run_workspace_command` hidden in OpenCode's Plan
  agent, so planning stays read-only and cannot delegate;
- one-level delegation, with workers unable to delegate, change the workspace
  root or move files. Workers can run commands and focused tests; the coordinator
  runs final integrated tests.

The AID2E system prompt comes from the deployed server chat template or gateway. `init`
does not add custom agent prompts or instruction files for OpenCode. General
workers inherit the calling model. Use the normal interactive OpenCode window
and ask it to use subagents; no launcher or experimental background flag is
required. The optional background mode is a separate OpenCode feature.

Concurrent subagents share the selected backend's serving slots. LiteLLM
user/key concurrency limits apply independently; existing keys retain their stored
limits when gateway defaults change. A request limit is not a worker-count limit.

The endpoint defaults to the AID2E LiteLLM gateway's internal address
(`http://128.239.58.223:4000/v1`). OpenCode prefixes the LiteLLM ID with
`aid2e/` in its model selector. Select `aid2e/qwen-3.8-flash-next` (the
default) or `aid2e/glm-5.3-flash`. The generated config also includes
`aid2e/MiniMax-M3.1-Flash`; use it when `/v1/models` lists
`MiniMax-M3.1-Flash` for your key.

Pass the bare LiteLLM ID to `init`. For example, use
`--llm-model glm-5.3-flash` to set the default and auxiliary model. The named
routes have 262,144 total context tokens, 8,192 output tokens, and a 4,096-token
compaction reserve in the generated config. Use
`--llm-context` and `--llm-output` to override the configured default model's limits.
Rerunning `aid2e mcp init --client opencode` refreshes managed settings and
preserves user overrides.

From outside the internal network, use the [SSH tunnel](#connect-to-the-aid2e-hosted-model)
and pass `--llm-url http://127.0.0.1:4001/v1`. OpenCode reads the gateway API key
from `AID2E_LLM_API_KEY` at runtime.

```bash
export AID2E_LLM_API_KEY=...        # never written to disk by init
cd /path/to/your/project
opencode mcp list                   # aid2e should show as connected
opencode
```

### Claude Code and Codex

These use your own Claude or Codex login and models.

| Client | Files written |
| --- | --- |
| Claude Code | `.mcp.json`, plus `.claude/settings.local.json` (pre-approves the server) |
| Codex CLI | a marked `# BEGIN/END aid2e managed MCP` block in `.codex/config.toml` |

- **Claude Code:** `cd /path/to/your/project && claude`, trust the project,
  and run `/mcp` to confirm `aid2e` is connected.
- **Codex:** `codex -C /path/to/your/project` and trust the project. Outside
  a Git repository, add `-c 'project_root_markers=[]'`. Run `/mcp` to confirm.

Add `--with-instructions` to also create a compact `CLAUDE.md` or `AGENTS.md`
with the longer AID2E guide. An existing file is never modified.

## Tools

### Source Reference tools (read-only)

| Tool | Description |
| --- | --- |
| `get_subsystem_blueprints` | Abstract base class, implementations, registry files, and example configs for a subsystem (`schedulers`, `optimizers`, `workflows`, `configurations`, etc.). |
| `search_repository` | Finds AID2E modules, classes, functions, and methods related to a concept or name. |
| `grep_framework_source` | Exact text or regex search across the AID2E source and/or `examples/` (`scope`), with `file:line` matches. |
| `get_class_contracts` | Base classes, known subclasses, attributes, and method signatures for a class. |
| `get_symbol_source` | Exact source and `file:start-end` lines for a class, function, or method. |
| `list_files_in_framework_subdirectory` | Lists AID2E source files in a subsystem, filtered by a glob pattern. |
| `read_framework_file` | Reads an AID2E source file in numbered chunks of at most 80 lines; continue with `start_line`. |
| `list_example_directory_files` | Lists example scripts and configs, filtered by a glob pattern. |
| `read_example_file` | Reads an example script or config in numbered chunks of at most 80 lines. |

### Workspace tools (your project)

| Tool | Description |
| --- | --- |
| `debug_workspace` | Shows the workspace, Python interpreter/version, environment bin directory, test directory and read-only AID2E source paths. |
| `set_workspace_root` | Sets the workspace root to a project directory you supply. |
| `list_workspace_files` | Lists files and folders in your project, filtered by a glob pattern. |
| `search_workspace` | Searches your project files for text or a regex (`file:line` matches). |
| `read_file_in_workspace` | Reads a file; `line_numbers=true` prefixes `N:` line numbers for line-based edits. |
| `create_file_in_workspace` | Creates a file (and its parent folders); `overwrite=true` replaces an existing file. Checks Python syntax. |
| `move_file_in_workspace` | Moves or renames a file; refuses to replace an existing destination unless `overwrite=true`. |
| `replace_lines_in_workspace` | Replaces an inclusive 1-indexed line range and checks Python syntax. The caller passes the range's current text as `old_content`; if it doesn't match (for example, line numbers shifted by an earlier edit), nothing is changed. |
| `append_to_file_in_workspace` | Appends a chunk to an existing file, for building large files incrementally. |
| `validate_workspace_file` | Validates a `.py` file (syntax) or an AID2E config (`.yml`/`.yaml`/`.json`/`.config`/`.params`) against AID2E's schemas. A valid config also gets a `WARNING` for each objective plan whose later steps lack `depends_on`: AID2E orders such steps by string hash, so they can run out of listed order from one run to the next. It also warns about unknown keys in workflows, branches, stages and jobs, and about workflows with nothing to run: AID2E ignores these silently, so a misplaced `stages` block means no job runs. |
| `run_workspace_command` | Executes an argument list in the MCP environment, e.g. `["aid2e", "optimize", "examples/demo/config.yml"]` or `["python", "examples/demo/check.py"]`; returns exit code, duration, interpreter, CWD and output (`full` only). |
| `run_workspace_tests` | Runs `pytest` in the MCP Python environment, defaulting to `tests/`; workers can run focused checks and the coordinator runs final integrated tests (`full` only). |

File tools return paths relative to your project; execution results include the
absolute Python interpreter and working directory for diagnosis.

Reserve `tests/<task>/` for pytest files, conftest.py and test fixtures.
Put example evaluator code, configuration, scripts, README and results under
`examples/<task>/`. Runtime output/work data belongs in isolated managed run
folders (`.aid2e/runs/<run_id>/`) or pytest temporary directories. File tools
create parent directories; use `__init__.py` for importable example packages.

Managed execution tools (`full` profile):

| Tool | Purpose |
|---|---|
| `scaffold_example(name)` | Runnable generic four-step combined-objective example, isolated CLI fixture and provenance-aware plotting; preserves existing files. |
| `preflight_workflow(config)` | Validate and execute one default candidate; returns named step input/return keys and errors. Does not run optimization. |
| `run_optimization(config)` | Run the real CLI with unique work/output directories, source/framework hashes, exact artifact paths and independent checks. |
| `verify_optimization_run(run_id, requirements)` | Check execution/source freshness, trial budget, bounds, constraints, finite objectives, Ax generation metadata and exact sampled Pareto membership/dominance. |
| `get_verification_report(run_id, requirements, artifact_paths)` | Recheck evidence, associated pytest and registered derived artifact provenance before reporting completion. |
| `get_integration_contract()` | Canonical runnable config, inline, shared-fixture and producer patterns; bounded worker instructions. |
| `finalize_optimization_run(run_id, expected_trials, artifact_paths, ...)` | Mandatory artifact/pytest source coverage checks; independent acceptance status and Markdown card. |

Read the integration contract before writing code. Finalize the exact final
pytest-created run and require `completion_allowed=true` before declaring done.
Both profiles provide `get_verification_contract()` for public verification APIs,
result schemas, and recovery steps. AID2E file tools omit MCP implementation files.
Users can recheck independently with `aid2e mcp status RUN_ID --workspace PATH`;
nonzero exit means not accepted. Core verification and pytest passes alone are
not full acceptance. The finalizer does not create provenance for existing files
or generate scientific plots. Refresh managed client permissions and restart MCP
to load new tools.

`requirements` accepts `expected_trials`, `min_pareto_points`,
`require_model_based`, `require_device`, and `require_artifacts`. Unknown fields are rejected.
The configured budget remains authoritative; an extra requirement cannot reduce it.
All executing tools share the existing execution slot and timeout.
Plan hides these tools; Build and general workers have access in the full profile.

For pytest fixtures call `aid2e.mcp.verification.run_local_optimization` once
and share the returned record. When invoked through `run_workspace_tests`, its
run is associated with that exact pytest execution. An unrelated pytest pass
cannot verify an earlier managed run. Agent-written tests remain separate from
the installed result checker. Source/test changes invalidate their old evidence.

Use `record_diagnostic(output_dir, "reconstruction_device", str(tensor.device))`
at the measured operation. Diagnostic values are evaluator-supplied evidence;
GPU availability is not a device measurement. Missing records remain explicit.
Use `write_artifact_provenance(workspace, run_id, artifact)` when producing each
plot/summary, then supply those workspace-relative paths in `artifact_paths`.
Sidecars bind producer-declared provenance and file hashes; they do not prove
that arbitrary plotting code faithfully represents its source data.

The adapter changes only output/work locations in a temporary sibling config,
retaining original relative-path semantics and requested trial settings. It
preserves the original config, effective config and hashes in the run record.
Track additional dynamic imports/assets using `source_paths`. A sibling config
left by a timed-out child is cleaned by the tool. Execution is trusted workspace
code, not a sandbox. Records are not tamper-proof against arbitrary commands.
The checker establishes software properties, not scientific validity.

`run_workspace_command` takes separate arguments, not a shell string. `python`
and `python3` use the MCP interpreter; `pytest` uses its pytest module; `aid2e`
invokes the real CLI entry point with that same interpreter. Neither
`python -m aid2e` nor `python -m aid2e.cli` is supported by the current framework.
No wrapper file is needed to run a command or inspect CLI help. The command's
`directory` defaults to the workspace root and must stay inside the workspace.
The workspace is added to `PYTHONPATH` for nested script/CLI imports, and the
interpreter's bin directory is prepended to `PATH` for child processes.

**File tools protect the AID2E source in code:**

- The write tools refuse any path inside the installed `aid2e` package or its
  examples, even when your workspace folder contains them.
- The workspace root can't be set inside the package.
- Reading is always allowed.
- Framework developers who intentionally want the assistant to edit an
  editable AID2E checkout can start the server with
  `AID2E_ALLOW_SOURCE_WRITES=1` in its environment.

**Both execution tools run your trusted project's code** as you, with the MCP
server's Python environment. Pytest needs `pytest` installed. Tests run from the
workspace root; commands can select a workspace subdirectory. Both use no shell
and closed stdin, refuse execution/test directories inside the AID2E source,
and stop the run, including any worker processes it started, after 50 seconds.
The default is below the
~60-second request timeout of MCP clients such as OpenCode, so the assistant
sees a timeout result instead of a client error. Set `AID2E_TEST_TIMEOUT`
(seconds) in the server's environment to change the limit for both tools. Only
one command or test runs at a time across the coordinator and workers sharing
that MCP server. A concurrent call returns `busy` instead of starting more work;
coordinate the next execution after the current result. Unless the server's environment sets them,
`OMP_NUM_THREADS`, `MKL_NUM_THREADS` and `OPENBLAS_NUM_THREADS` are set to 4:
on a 64-core node, a 6-trial Ax test took 36 s with torch's default threads
and 5 s with 4. The pytest result leaves out captured stdout, logs and warning
summaries, and long output keeps its start and end: AID2E's executor logs
about 10 kB per run, which used to push the failing `E` lines out of what the
assistant saw. Execution runs with your account's permissions and is not an OS
sandbox; the source-write guards above apply to file tools, not arbitrary Python
code. The `reference` profile does not include either execution tool; Claude
Code and Codex run commands and tests with their own tools.

## Running the server directly

```bash
aid2e mcp --workspace /path/to/your/project [--tools full|reference] [--sse]
python -m aid2e.mcp --workspace /path/to/your/project   # same, without the aid2e script
```

`--workspace` (or the `AID2E_WORKSPACE` environment variable) sets the project
the Workspace tools operate on. The server never falls back to its current
directory or your home directory. If no workspace is set, `debug_workspace`
reports `UNSET` and workspace tools refuse to run.

### Manual VS Code configuration

If you don't use `init`, add a server under **MCP: Open User Configuration**:

```json
{
  "servers": {
    "aid2eLocal": {
      "command": "/absolute/path/to/your/env/bin/aid2e",
      "args": ["mcp", "--workspace", "${workspaceFolder}"]
    }
  }
}
```

For conda, use a shell wrapper such as
`"command": "bash", "args": ["-c", "source /path/to/miniforge3/bin/activate aid2e_env && aid2e mcp --workspace \"${workspaceFolder}\""]`.
Then enable only the AID2E tools in the Chat tool picker (the two-lines icon
next to the model picker), and disable the built-in tools.

![AID2E MCP tool selection](assets/tool_list.png)

## Troubleshooting

| Problem | What to check |
| --- | --- |
| No `aid2e` tools in the client | Open the project directory you initialized, trust it, and start or approve the server (`/mcp`, or the VS Code MCP view). Check that the pinned Python in the generated config still exists; re-run `init` if not. |
| `debug_workspace` shows `UNSET` | The server was started without `--workspace`. Re-run `init`, or pass `--workspace`. |
| A write is refused as "read-only AID2E Reference Source" | Working as intended: write your code in your project, not in the AID2E package. |
| `init` refuses to change an entry | You added or edited an `aid2e` entry yourself. Rename or remove it, then re-run `init`. |

Automatic trial-budget/generation checks currently cover fresh Ax runs with
Sobol/uniform initialization and ModularBoTorch generation. Center initialization
is reported as unsupported. For other optimizer families, provide an explicit
`expected_trials`; generation metadata is checked only where supported. Warm-start
trial accounting requires separate review. Missing required derived artifacts
produce an incomplete overall report when `require_artifacts` is true.
