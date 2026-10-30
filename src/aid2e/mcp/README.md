# AID2E MCP Server

The AID2E MCP server gives coding assistants a verified view of the installed
AID2E framework, and safe tools for building AID2E extensions in your own
project. It has two strictly separated tool groups:

- **Source Reference tools (read-only):** inspect the installed `aid2e`
  package and its `examples/`. The AID2E source can never be modified through
  the server.
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

These steps connect a client on your own machine to the `code-assist` model
through an SSH tunnel. The model runs on the cluster. The AID2E tools run on
your machine and work on your local files.

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
curl -sS http://127.0.0.1:4001/v1/chat/completions \
  -H "Authorization: Bearer $AID2E_LLM_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "code-assist", "messages": [{"role": "user", "content": "Reply with pong."}], "max_tokens": 200}'
```

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
        "id": "code-assist",
        "name": "AID2E Code Assist",
        "url": "http://127.0.0.1:4001/v1/chat/completions",
        "toolCalling": true,
        "vision": false,
        "maxInputTokens": 229376,
        "maxOutputTokens": 32768,
        "modelOptions": { "parallel_tool_calls": false },
        "requestHeaders": {
          "Authorization": "Bearer sk-PASTE-YOUR-PERSONAL-KEY-HERE"
        }
      }
    ]
  }
]
```

This file holds your key, so keep it private. Then open the project, start
`aid2eLocal` from the MCP view, and choose the **AID2E** agent and **AID2E Code
Assist** in Chat. If you use VS Code in WSL or over Remote-SSH, run the tunnel
in that same environment.

### Connection problems

| Problem | What to check |
| --- | --- |
| `Connection refused` or `ECONNREFUSED` | The tunnel isn't running. Restart step 1, on the same machine as your client. |
| `channel ... open failed: connect failed` in the tunnel terminal, or an empty reply from `curl` | The tunnel is up, but the gateway connection on SciClone is down. Email the administrator. |
| `Address already in use` when opening the tunnel | Port 4001 is taken on your machine. Use another port, such as `-L 4002:127.0.0.1:4000`. Then use that port in step 3, and in `--llm-url` or `url`. Re-running `init` updates the URL. |
| `401` or `Authentication Error` | Your key is wrong or isn't set in this terminal. Repeat step 2. |
| `model ... is not available` or `key not allowed to access model` | Your key doesn't include `code-assist`. Email the administrator. |
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

- **Forward the service, not a vLLM pod.** LiteLLM checks each person's key and
  records their usage. The vLLM pods do neither, and they don't know the
  `code-assist` alias.
- **Use the same host for the port-forward and the tunnel.** `kubectl` listens
  only on that host's `127.0.0.1`, so a tunnel to another login node can't reach
  it.
- **Keep the loop.** A port-forward exits when its LiteLLM pod restarts, which
  every deploy does.

Create keys as described in `LITELLM-100B.md`, and include `code-assist` in
their `models`.

## Which tools each client gets

| Model behind the client | Clients | Tool profile | Client's built-in tools |
| --- | --- | --- | --- |
| Small local model (e.g. AID2E `code-assist-*`) | VS Code Chat, OpenCode | `full`: Source Reference + Workspace read/write/validate | Disabled |
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
- OpenCode's built-in tools disabled, so the model sees only AID2E tools;
- the AID2E write tools and `run_workspace_tests` hidden in OpenCode's Plan
  agent, so planning stays read-only.

The endpoint defaults to the AID2E LiteLLM gateway's internal address
(`http://128.239.58.223:4000/v1`) with model `code-assist`, a gateway alias for
whichever model is deployed. That address has no outside access, so on your own
machine pass `--llm-url http://127.0.0.1:4001/v1` and use the
[SSH tunnel](#connect-to-the-aid2e-hosted-model). Use `--llm-model` to pin one
model (for example, `--llm-model code-assist-gemma-26b`). The API key
is read from the `AID2E_LLM_API_KEY` environment variable at runtime:

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
| `debug_workspace` | Shows the active workspace root and the read-only AID2E source paths. |
| `set_workspace_root` | Sets the workspace root to a project directory you supply. |
| `list_workspace_files` | Lists files and folders in your project, filtered by a glob pattern. |
| `search_workspace` | Searches your project files for text or a regex (`file:line` matches). |
| `read_file_in_workspace` | Reads a file; `line_numbers=true` prefixes `N:` line numbers for line-based edits. |
| `create_file_in_workspace` | Creates a file (and its parent folders); `overwrite=true` replaces an existing file. Checks Python syntax. |
| `move_file_in_workspace` | Moves or renames a file; refuses to replace an existing destination unless `overwrite=true`. |
| `replace_lines_in_workspace` | Replaces an inclusive 1-indexed line range and checks Python syntax. The caller passes the range's current text as `old_content`; if it doesn't match (for example, line numbers shifted by an earlier edit), nothing is changed. |
| `append_to_file_in_workspace` | Appends a chunk to an existing file, for building large files incrementally. |
| `validate_workspace_file` | Validates a `.py` file (syntax) or an AID2E config (`.yml`/`.yaml`/`.json`/`.config`/`.params`) against AID2E's schemas. A valid config also gets a `WARNING` for each objective plan whose later steps lack `depends_on`: AID2E orders such steps by string hash, so they can run out of listed order from one run to the next. It also warns about unknown keys in workflows, branches, stages and jobs, and about workflows with nothing to run: AID2E ignores these silently, so a misplaced `stages` block means no job runs. |
| `run_workspace_tests` | Runs `pytest` on a test file or folder in your project and returns the result (`full` profile only). |

Workspace tools return paths relative to your project.

**The AID2E source is protected in code, not just by instructions:**

- The write tools refuse any path inside the installed `aid2e` package or its
  examples, even when your workspace folder contains them.
- The workspace root can't be set inside the package.
- Reading is always allowed.
- Framework developers who intentionally want the assistant to edit an
  editable AID2E checkout can start the server with
  `AID2E_ALLOW_SOURCE_WRITES=1` in its environment.

**`run_workspace_tests` executes your project's code** as you, with the MCP
server's Python (the environment where `aid2e` is installed; it needs
`pytest`). It runs from the workspace root with no shell and closed stdin,
refuses test paths inside the AID2E source, and stops the run, including any
worker processes it started, after 50 seconds. The default is below the
~60-second request timeout of MCP clients such as OpenCode, so the assistant
sees a timeout result instead of a client error. Set `AID2E_TEST_TIMEOUT`
(seconds) in the server's environment to change the limit. Only one test run
happens at a time. Unless the server's environment sets them,
`OMP_NUM_THREADS`, `MKL_NUM_THREADS` and `OPENBLAS_NUM_THREADS` are set to 4:
on a 64-core node, a 6-trial Ax test took 36 s with torch's default threads
and 5 s with 4. The result leaves out captured stdout, logs and warning
summaries, and long output keeps its start and end: AID2E's executor logs
about 10 kB per run, which used to push the failing `E` lines out of what the
assistant saw. The tests can do
anything your code can, such as writing output files, so review what the
assistant writes. The `reference` profile does not include this tool; Claude
Code and Codex run tests with their own tools.

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
