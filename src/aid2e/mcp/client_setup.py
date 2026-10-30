"""Project-local client setup for the AID2E MCP server.

`aid2e mcp init --client <client>` writes the client's project-local MCP
configuration. The tool profile follows the class of model behind the client:

| Model class          | Clients            | Tool profile | Client's native tools |
|----------------------|--------------------|--------------|-----------------------|
| Strong hosted agent  | Claude Code, Codex | `reference`  | kept                  |
| Local / small model  | OpenCode, VS Code  | `full`       | disabled              |

Hosted agents have capable file tools of their own, so they only need the
read-only Reference Source tools. Small locally deployed models get confused by
large or overlapping tool lists, so they see only the AID2E tools, which cover
workspace reading, editing, and validation. The deployed vLLM chat templates
assume exactly that tool set.

Files written per client:

- Claude Code: `.mcp.json` and `.claude/settings.local.json` (pre-approval).
- Codex CLI: a marked, refreshable block in `.codex/config.toml`.
- OpenCode: `opencode.json` with the `aid2e` MCP server, the local LiteLLM
  provider/model, and native tools disabled.
- VS Code: `.vscode/mcp.json` (server ID `aid2eLocal`) and a
  `.github/agents/aid2e.agent.md` custom agent restricted to `aid2eLocal/*`.

VS Code may also load a workspace-root `.mcp.json` (the portable format that
Claude Code uses). The VS Code server therefore gets its own ID, so a project
set up for both Claude Code and VS Code never has two servers with the same
name, and the AID2E agent never sees the Claude `reference` server's tools.

The server is launched with the interpreter that ran `init`
(`<python> -m aid2e.mcp --workspace <root> --tools <profile>`), so the
configuration works for editable checkouts, virtual environments, conda, and
PyPI installs without PATH or PYTHONPATH changes. Ownership of the generated
entries is recorded in `.aid2e-workspace.json`; entries added or edited by the
user are never overwritten, and no API key is ever written to disk.
"""

from __future__ import annotations

import copy
import json
import sys
import tomllib
from importlib import resources
from pathlib import Path

SERVER_NAME = "aid2e"
# Distinct ID for VS Code: it can also load Claude's root `.mcp.json` `aid2e` entry.
VSCODE_SERVER_NAME = "aid2eLocal"
OWNER = "aid2e-mcp"
METADATA_FILE = ".aid2e-workspace.json"
BEGIN = "# BEGIN aid2e managed MCP"
END = "# END aid2e managed MCP"

CLIENT_PROFILES = {
    "claude": "reference",
    "codex": "reference",
    "opencode": "full",
    "vscode": "full",
}
CLIENTS = tuple(CLIENT_PROFILES)
CLIENT_NAMES = {"claude": "Claude Code", "codex": "Codex", "opencode": "OpenCode", "vscode": "VS Code"}
PROFILES = ("full", "reference")

# The AID2E LiteLLM gateway. `code-assist` is a gateway alias for whichever model
# is deployed (Qwen 35B/100B or Gemma 26B/31B), so OpenCode keeps working across deployments.
DEFAULT_LLM_URL = "http://128.239.58.223:4000/v1"
DEFAULT_LLM_MODEL = "code-assist"
LLM_API_KEY_ENV = "AID2E_LLM_API_KEY"

_INSTRUCTION_FILES = {"claude": "CLAUDE.md", "codex": "AGENTS.md"}
# OpenCode built-in tools hidden from local models (verified against OpenCode 1.19).
_OPENCODE_NATIVE_TOOLS = (
    "bash", "edit", "write", "patch", "multiedit", "apply_patch", "read", "grep", "glob", "list",
    "lsp", "webfetch", "websearch", "codesearch", "todowrite", "todoread", "task", "skill", "question",
)
# AID2E write and execute tools hidden in OpenCode's Plan agent. With no write
# tool in the request, the AID2E chat templates switch the model to Ask
# (read-only) mode.
_OPENCODE_PLAN_HIDDEN_TOOLS = (
    "create_file_in_workspace", "move_file_in_workspace", "replace_lines_in_workspace", "append_to_file_in_workspace",
    "run_workspace_tests",
)
_VSCODE_AGENT_FILE = Path(".github") / "agents" / "aid2e.agent.md"
_VSCODE_AGENT_BODY = """\
---
name: AID2E
description: AID2E engineering assistant restricted to the aid2e MCP tools
tools: ['{server}/*']
---
Use only the aid2e tools. Read the AID2E Reference Source and examples with the
Reference Source tools; read, create, edit, and validate project files with the
User Workspace tools. Never modify the Reference Source.
"""
_VSCODE_AGENT = _VSCODE_AGENT_BODY.format(server=VSCODE_SERVER_NAME)
# Earlier generated agent files, replaced in place when unmodified.
_VSCODE_AGENT_LEGACY = (_VSCODE_AGENT_BODY.format(server=SERVER_NAME),)


def server_launch(root: Path, profile: str) -> tuple[str, list[str]]:
    """Return the command and arguments that launch the AID2E MCP server.

    Args:
        root: Absolute workspace root passed to the server.
        profile: Tool profile ('full' or 'reference').

    Returns:
        Tuple of interpreter path and argument list.
    """
    command = str(Path(sys.executable).absolute())
    args = ["-m", "aid2e.mcp", "--workspace", str(root), "--tools", profile]
    return command, args


def instructions_text(client: str) -> str:
    """Return the shipped compact AID2E agent instructions for a hosted-agent client.

    Args:
        client: 'claude' or 'codex'.

    Returns:
        Markdown instruction text.
    """
    text = (resources.files("aid2e.mcp") / "context" / "AGENTS.md").read_text(encoding="utf-8")
    if client == "claude":
        text = text.replace(
            "# AID2E Code Assistant", "# AID2E Code Assistant for Claude Code", 1
        )
    return text


def _load_metadata(path: Path) -> dict:
    """Load the ownership record, refusing files written by anything else."""
    if not path.exists():
        return {}
    metadata = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict) or metadata.get("owner") != OWNER:
        raise ValueError(f"{path} is not owned by {OWNER}; rename it and retry.")
    clients = metadata.get("clients", {})
    if not isinstance(clients, dict) or any(not isinstance(v, dict) for v in clients.values()):
        raise ValueError(f"Invalid clients record in {path}; rename it and retry.")
    return metadata


def _read_text(path: Path) -> str:
    """Read a file preserving its newlines, or return '' when it does not exist."""
    if not path.exists():
        return ""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _load_json_object(path: Path, existing: str) -> dict:
    """Parse an existing JSON config, requiring a top-level object."""
    if not existing.strip():
        if path.exists():
            raise ValueError(f"{path.name} must be a JSON object, not an empty file.")
        return {}
    try:
        config = json.loads(existing)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(config, dict):
        raise ValueError(f"{path.name} must be a JSON object.")
    return config


_MISSING = object()


def _merge_owned(
    config: dict,
    key: str,
    value,
    managed: dict,
    path: Path,
    *,
    on_conflict: str = "refuse",
    warnings: list[str] | None = None,
) -> None:
    """Set dotted `key` in `config` to `value` unless the user owns the current value.

    The current value is ours when it is absent or still equals the snapshot
    recorded in `managed` at the previous init. Otherwise `on_conflict` decides:
    'refuse' raises, 'keep' leaves the user's value and records a warning.
    `managed[key]` is updated to the snapshot that should be recorded.
    """
    *parents, leaf = key.split(".")
    node = config
    for part in parents:
        child = node.setdefault(part, {})
        if not isinstance(child, dict):
            raise ValueError(f"`{'.'.join(parents)}` in {path} must be a JSON object.")
        node = child
    current = node.get(leaf, _MISSING)
    if current is not _MISSING and current != managed.get(key, _MISSING):
        if on_conflict == "refuse":
            raise ValueError(
                f"Existing unowned or modified `{key}` entry in {path} conflicts with init. "
                "Rename or remove that entry, then retry."
            )
        if warnings is not None and current != value:
            warnings.append(f"Kept your `{key}` = {json.dumps(current)} in {path.name}.")
        managed.pop(key, None)
        return
    node[leaf] = copy.deepcopy(value)
    managed[key] = copy.deepcopy(value)


def _drop_owned(config: dict, key: str, managed: dict) -> None:
    """Remove dotted `key` if init still owns its value; prune emptied parent objects."""
    *parents, leaf = key.split(".")
    nodes = [config]
    for part in parents:
        child = nodes[-1].get(part)
        if not isinstance(child, dict):
            managed.pop(key, None)
            return
        nodes.append(child)
    if key in managed and nodes[-1].get(leaf, _MISSING) == managed[key]:
        del nodes[-1][leaf]
        for parent, part in zip(reversed(nodes[:-1]), reversed(parents)):
            if parent[part] == {}:
                del parent[part]
    managed.pop(key, None)


def _dump_json(config: dict) -> str:
    return json.dumps(config, indent=2, ensure_ascii=False) + "\n"


def _claude_settings(path: Path, existing: str) -> tuple[str, list[str]]:
    """Pre-approve the project server in `.claude/settings.local.json`.

    Returns:
        Updated JSON text and any warnings for the user.
    """
    settings = _load_json_object(path, existing)
    warnings = []
    disabled = settings.get("disabledMcpjsonServers", [])
    if isinstance(disabled, list) and SERVER_NAME in disabled:
        warnings.append(
            f"`{SERVER_NAME}` is listed in disabledMcpjsonServers in {path}; "
            "remove it there to enable the server."
        )
        return existing, warnings
    enabled = settings.get("enabledMcpjsonServers", [])
    if not isinstance(enabled, list):
        raise ValueError(f"{path.name} `enabledMcpjsonServers` must be a JSON list.")
    if SERVER_NAME in enabled:
        return existing, warnings
    settings["enabledMcpjsonServers"] = [*enabled, SERVER_NAME]
    return _dump_json(settings), warnings


def _codex_block(root: Path, profile: str) -> str:
    """Render our marked `[mcp_servers.aid2e]` TOML block."""
    command, args = server_launch(root, profile)
    quote = lambda value: json.dumps(value, ensure_ascii=False)
    return "\n".join(
        [
            BEGIN,
            f"[mcp_servers.{SERVER_NAME}]",
            f"command = {quote(command)}",
            f"args = {quote(args)}",
            f"cwd = {quote(str(root))}",
            "startup_timeout_sec = 60",
            "tool_timeout_sec = 120",
            END,
            "",
        ]
    )


def _codex_config(path: Path, existing: str, block: str) -> str:
    """Replace only our marked block in `.codex/config.toml`, validating TOML semantics."""
    try:
        tomllib.loads(existing)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path} is not valid TOML: {exc}") from exc
    lines = existing.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == BEGIN]
    ends = [i for i, line in enumerate(lines) if line.rstrip("\r\n") == END]
    if starts or ends:
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            raise ValueError(f"Malformed aid2e managed markers in {path}; repair them before retrying init.")
        owned = tomllib.loads("".join(lines[starts[0] : ends[0] + 1]))
        if set(owned) != {"mcp_servers"} or set(owned["mcp_servers"]) != {SERVER_NAME}:
            raise ValueError(f"The aid2e managed block in {path} contains other settings; move them outside the markers.")
        outside = "".join(lines[: starts[0]] + lines[ends[0] + 1 :])
    else:
        outside = existing

    unowned = tomllib.loads(outside)
    servers = unowned.get("mcp_servers", {})
    if not isinstance(servers, dict) or SERVER_NAME in servers:
        raise ValueError(
            f"Existing unowned mcp_servers.{SERVER_NAME} configuration in {path} conflicts with init. "
            "Rename or remove that entry, then retry."
        )
    # Append a fully qualified table at EOF so no unrelated keys change scope.
    if not outside or outside.endswith("\n\n"):
        separator = ""
    elif outside.endswith("\n"):
        separator = "\n"
    else:
        separator = "\n\n"
    candidate = outside + separator + block
    expected = dict(unowned)
    expected["mcp_servers"] = {**servers, SERVER_NAME: tomllib.loads(block)["mcp_servers"][SERVER_NAME]}
    if tomllib.loads(candidate) != expected:
        raise ValueError(f"Cannot safely add the MCP table to {path}; use explicit table sections and retry.")
    return candidate


def _opencode_provider(llm_url: str, llm_model: str) -> dict:
    """OpenAI-compatible provider entry for the AID2E LiteLLM gateway."""
    return {
        "npm": "@ai-sdk/openai-compatible",
        "name": "AID2E (local LLM)",
        "options": {"baseURL": llm_url, "apiKey": f"{{env:{LLM_API_KEY_ENV}}}"},
        "models": {
            llm_model: {
                "name": f"AID2E {llm_model}",
                "limit": {"context": 229376, "output": 32768},
            }
        },
    }


def _write_if_changed(path: Path, existing: str, updated: str) -> bool:
    """Write `updated` when it differs from `existing`; return whether it was written."""
    if updated == existing:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(updated)
    return True


def describe_setup(client: str, profile: str) -> str:
    """One-line description of the configured model class and tool profile."""
    name = CLIENT_NAMES[client]
    if profile == "reference":
        return f"{name}: read-only AID2E Reference Source tools alongside the client's own tools"
    if client in ("opencode", "vscode"):
        return f"{name} (local model): full AID2E tool suite, native tools disabled"
    return f"{name}: full AID2E tool suite alongside the client's own tools"


def next_steps(client: str, root: Path) -> list[str]:
    """Return short instructions for opening the configured client."""
    if client == "claude":
        return [
            f"cd {root} && claude",
            "Trust the project when prompted, then run /mcp to confirm `aid2e` is connected.",
        ]
    if client == "codex":
        return [
            f"codex -C {root}",
            "Trust the project when prompted so Codex loads .codex/config.toml; "
            "outside a Git repository add -c 'project_root_markers=[]'.",
            "Run /mcp in Codex to confirm `aid2e` is connected.",
        ]
    if client == "opencode":
        return [
            f'read -rsp "AID2E API key: " {LLM_API_KEY_ENV}; echo; export {LLM_API_KEY_ENV}',
            f"cd {root} && opencode mcp list   # confirm `aid2e` is connected",
            f"cd {root} && opencode",
        ]
    return [
        f"Open {root} in VS Code and start `{VSCODE_SERVER_NAME}` from the MCP view (or trust it when prompted).",
        "Add the AID2E model under Chat: Manage Language Models (see the AID2E README).",
        "In Chat, pick the `AID2E` agent and the AID2E model; the agent exposes only `aid2e` tools.",
    ]


def _vscode_claude_overlap(root: Path, client: str) -> str | None:
    """Warn when a project holds both the Claude `.mcp.json` and the VS Code server.

    VS Code may also load the root `.mcp.json` written for Claude Code. The
    distinct `aid2eLocal` ID and the AID2E agent's `aid2eLocal/*` tool list keep
    the local model's tool set clean, but VS Code can still start the extra
    read-only server and list its tools outside the AID2E agent.
    """
    if client not in ("claude", "vscode"):
        return None
    try:
        claude = json.loads(_read_text(root / ".mcp.json") or "{}").get("mcpServers", {})
        vscode = json.loads(_read_text(root / ".vscode" / "mcp.json") or "{}").get("servers", {})
    except (json.JSONDecodeError, AttributeError):
        return None
    if not (isinstance(claude, dict) and SERVER_NAME in claude and isinstance(vscode, dict) and VSCODE_SERVER_NAME in vscode):
        return None
    return (
        f"This project has both the Claude Code server (`{SERVER_NAME}` in .mcp.json, read-only "
        f"reference tools) and the VS Code server (`{VSCODE_SERVER_NAME}` in .vscode/mcp.json). "
        f"VS Code may also start `{SERVER_NAME}` from .mcp.json. With the AID2E agent this is harmless, "
        f"because it only exposes `{VSCODE_SERVER_NAME}/*` tools. Outside that agent, deselect the "
        f"`{SERVER_NAME}` tools (or stop that server in the MCP view) so the local model doesn't see "
        "duplicate tools."
    )


def init_workspace(
    workspace: str | Path | None = None,
    *,
    client: str,
    with_instructions: bool = False,
    profile: str | None = None,
    llm_url: str = DEFAULT_LLM_URL,
    llm_model: str = DEFAULT_LLM_MODEL,
) -> dict:
    """Configure a project-local client workspace for the AID2E MCP server.

    Args:
        workspace: Project directory (default: current directory). Created if missing.
        client: 'claude', 'codex', 'opencode', or 'vscode'.
        with_instructions: Also create `CLAUDE.md` / `AGENTS.md` when absent
            (hosted-agent clients only; local models get the AID2E prompt from
            the deployed chat template).
        profile: Tool profile override ('full' or 'reference'); defaults to
            the client's entry in `CLIENT_PROFILES`. Native client tools are
            disabled for OpenCode/VS Code exactly when the profile is 'full'.
        llm_url: OpenAI-compatible base URL of the AID2E LLM gateway (OpenCode).
        llm_model: Model name served by the gateway (OpenCode).

    Returns:
        Summary with the workspace, profile, written files, warnings, and next steps.
    """
    if client not in CLIENTS:
        raise ValueError(f"Unsupported client {client!r}; choose from {', '.join(CLIENTS)}.")
    profile = profile or CLIENT_PROFILES[client]
    if profile not in PROFILES:
        raise ValueError(f"Unknown tool profile {profile!r}; choose from {', '.join(PROFILES)}.")
    root = Path(workspace or Path.cwd()).expanduser().resolve()
    if root.exists() and not root.is_dir():
        raise ValueError(f"Workspace is not a directory: {root}")

    metadata_path = root / METADATA_FILE
    metadata = _load_metadata(metadata_path)
    clients = {name: copy.deepcopy(value) for name, value in metadata.get("clients", {}).items()}
    previous = clients.get(client, {})
    managed = dict(previous.get("managed", {}))
    if "managed_mcp_config" in previous:  # Record format from the first Claude-only release.
        managed.setdefault(f"mcpServers.{SERVER_NAME}", previous["managed_mcp_config"])
    command, args = server_launch(root, profile)
    restrict_tools = profile == "full" and client in ("opencode", "vscode")
    warnings: list[str] = []
    written: list[str] = []

    # Plan every file before writing anything, so a refusal leaves the workspace untouched.
    plans: list[tuple[Path, str, str]] = []
    if client == "claude":
        config_path = root / ".mcp.json"
        existing = _read_text(config_path)
        config = _load_json_object(config_path, existing)
        _merge_owned(config, f"mcpServers.{SERVER_NAME}", {"type": "stdio", "command": command, "args": args}, managed, config_path)
        plans.append((config_path, existing, _dump_json(config)))
        settings_path = root / ".claude" / "settings.local.json"
        settings_existing = _read_text(settings_path)
        settings_updated, settings_warnings = _claude_settings(settings_path, settings_existing)
        warnings.extend(settings_warnings)
        plans.append((settings_path, settings_existing, settings_updated))
    elif client == "codex":
        config_path = root / ".codex" / "config.toml"
        existing = _read_text(config_path)
        plans.append((config_path, existing, _codex_config(config_path, existing, _codex_block(root, profile))))
    elif client == "opencode":
        if (root / "opencode.jsonc").exists():
            raise ValueError(
                f"{root / 'opencode.jsonc'} exists; init only edits opencode.json. "
                "Merge or rename it, then retry."
            )
        config_path = root / "opencode.json"
        existing = _read_text(config_path)
        config = _load_json_object(config_path, existing)
        config.setdefault("$schema", "https://opencode.ai/config.json")
        _merge_owned(config, f"mcp.{SERVER_NAME}", {"type": "local", "command": [command, *args], "enabled": True}, managed, config_path)
        _merge_owned(config, f"provider.{SERVER_NAME}", _opencode_provider(llm_url, llm_model), managed, config_path)
        _merge_owned(config, "model", f"{SERVER_NAME}/{llm_model}", managed, config_path, on_conflict="keep", warnings=warnings)
        restricted_keys = [f"tools.{tool}" for tool in _OPENCODE_NATIVE_TOOLS]
        restricted_keys += [f"agent.plan.tools.{SERVER_NAME}_{tool}" for tool in _OPENCODE_PLAN_HIDDEN_TOOLS]
        for key in restricted_keys:
            if restrict_tools:
                _merge_owned(config, key, False, managed, config_path, on_conflict="keep", warnings=warnings)
            else:
                _drop_owned(config, key, managed)  # Profile switched to reference: hand the tools back.
        plans.append((config_path, existing, _dump_json(config)))
    else:
        config_path = root / ".vscode" / "mcp.json"
        existing = _read_text(config_path)
        config = _load_json_object(config_path, existing)
        legacy_key = f"servers.{SERVER_NAME}"  # Server ID written before the rename.
        if legacy_key in managed and config.get("servers", {}).get(SERVER_NAME, _MISSING) == managed[legacy_key]:
            del config["servers"][SERVER_NAME]
        managed.pop(legacy_key, None)
        _merge_owned(config, f"servers.{VSCODE_SERVER_NAME}", {"type": "stdio", "command": command, "args": args}, managed, config_path)
        plans.append((config_path, existing, _dump_json(config)))
    clients[client] = {"client_config": str(config_path), "profile": profile, "managed": managed}

    root.mkdir(parents=True, exist_ok=True)
    for path, existing_text, updated in plans:
        if _write_if_changed(path, existing_text, updated):
            written.append(str(path))

    if client == "vscode" and restrict_tools:
        agent_path = root / _VSCODE_AGENT_FILE
        agent_path.parent.mkdir(parents=True, exist_ok=True)
        if agent_path.exists() and agent_path.read_text(encoding="utf-8") in _VSCODE_AGENT_LEGACY:
            agent_path.write_text(_VSCODE_AGENT, encoding="utf-8")
            written.append(str(agent_path))
        else:
            try:
                with agent_path.open("x", encoding="utf-8") as handle:
                    handle.write(_VSCODE_AGENT)
                written.append(str(agent_path))
            except FileExistsError:
                if agent_path.read_text(encoding="utf-8") != _VSCODE_AGENT:
                    warnings.append(f"Kept existing {_VSCODE_AGENT_FILE}; it was not modified.")

    shared = _vscode_claude_overlap(root, client)
    if shared:
        warnings.append(shared)

    if with_instructions:
        if client in _INSTRUCTION_FILES:
            instructions_path = root / _INSTRUCTION_FILES[client]
            try:
                with instructions_path.open("x", encoding="utf-8") as handle:
                    handle.write(instructions_text(client))
                written.append(str(instructions_path))
            except FileExistsError:
                warnings.append(f"Kept existing {instructions_path.name}; it was not modified.")
        else:
            warnings.append(
                f"--with-instructions is not used for {CLIENT_NAMES[client]}: the AID2E model's chat "
                "template already supplies the AID2E system prompt."
            )

    try:
        import mcp  # noqa: F401
    except ImportError:
        warnings.append(
            "The MCP Python SDK is not installed in this interpreter; install it with "
            "`python -m pip install 'aid2e[mcp]'` before starting the client."
        )

    metadata.update(
        {
            "owner": OWNER,
            "version": 2,
            "workspace": str(root),
            "server": SERVER_NAME,
            "python": command,
            "clients": clients,
        }
    )
    metadata_text = json.dumps(metadata, indent=2) + "\n"
    if _write_if_changed(metadata_path, _read_text(metadata_path), metadata_text):
        written.append(str(metadata_path))

    # Configs pin this interpreter and the absolute workspace path; they shouldn't be committed.
    machine_specific = {str(path) for path, _, _ in plans} | {str(metadata_path)}
    return {
        "client": client,
        "profile": profile,
        "machine_specific": [path for path in written if path in machine_specific],
        "description": describe_setup(client, profile),
        "workspace": str(root),
        "client_config": str(config_path),
        "written": written,
        "warnings": warnings,
        "next_steps": next_steps(client, root),
    }
