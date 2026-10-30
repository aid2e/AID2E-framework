"""Tests for `aid2e mcp init` client setup and MCP tool profiles."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path

import pytest
from click.testing import CliRunner

from aid2e.cli.aid2e_cli import cli
from aid2e.mcp.client_setup import (
    BEGIN,
    CLIENT_PROFILES,
    END,
    LLM_API_KEY_ENV,
    METADATA_FILE,
    init_workspace,
)


def _expected_args(root: Path, profile: str = "reference") -> list[str]:
    return ["-m", "aid2e.mcp", "--workspace", str(root), "--tools", profile]


def test_claude_init_writes_project_config(tmp_path: Path) -> None:
    result = init_workspace(tmp_path, client="claude")

    config = json.loads((tmp_path / ".mcp.json").read_text())
    server = config["mcpServers"]["aid2e"]
    assert server["type"] == "stdio"
    assert server["command"] == str(Path(sys.executable).absolute())
    assert server["args"] == _expected_args(tmp_path.resolve())

    settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    assert settings["enabledMcpjsonServers"] == ["aid2e"]

    metadata = json.loads((tmp_path / METADATA_FILE).read_text())
    assert metadata["owner"] == "aid2e-mcp"
    assert metadata["clients"]["claude"]["managed"]["mcpServers.aid2e"] == server
    assert metadata["clients"]["claude"]["profile"] == "reference"
    assert result["client_config"] == str(tmp_path.resolve() / ".mcp.json")
    assert not (tmp_path / "CLAUDE.md").exists()


def test_claude_init_preserves_unrelated_entries_and_is_idempotent(tmp_path: Path) -> None:
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}))
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({"enabledMcpjsonServers": ["other"], "permissions": {"allow": ["Bash(ls)"]}})
    )

    init_workspace(tmp_path, client="claude")
    config = json.loads((tmp_path / ".mcp.json").read_text())
    assert set(config["mcpServers"]) == {"other", "aid2e"}
    settings = json.loads((tmp_path / ".claude" / "settings.local.json").read_text())
    assert settings["enabledMcpjsonServers"] == ["other", "aid2e"]
    assert settings["permissions"] == {"allow": ["Bash(ls)"]}

    second = init_workspace(tmp_path, client="claude")
    assert second["written"] == []


def test_claude_init_refuses_user_owned_entry(tmp_path: Path) -> None:
    original = json.dumps({"mcpServers": {"aid2e": {"command": "my-own-aid2e"}}})
    (tmp_path / ".mcp.json").write_text(original)

    with pytest.raises(ValueError, match="unowned or modified"):
        init_workspace(tmp_path, client="claude")
    assert (tmp_path / ".mcp.json").read_text() == original
    assert not (tmp_path / METADATA_FILE).exists()


def test_claude_init_refuses_hand_edited_managed_entry(tmp_path: Path) -> None:
    init_workspace(tmp_path, client="claude")
    config = json.loads((tmp_path / ".mcp.json").read_text())
    config["mcpServers"]["aid2e"]["args"].append("--sse")
    (tmp_path / ".mcp.json").write_text(json.dumps(config))

    with pytest.raises(ValueError, match="unowned or modified"):
        init_workspace(tmp_path, client="claude")


def test_codex_init_writes_managed_block_and_preserves_toml(tmp_path: Path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    existing = textwrap.dedent(
        """\
        model = "gpt-5"

        [mcp_servers.other]
        command = "other"
        """
    )
    (codex_dir / "config.toml").write_text(existing)

    init_workspace(tmp_path, client="codex")
    text = (codex_dir / "config.toml").read_text()
    assert text.startswith(existing)
    assert text.count(BEGIN) == 1 and text.count(END) == 1
    parsed = tomllib.loads(text)
    assert parsed["model"] == "gpt-5"
    assert set(parsed["mcp_servers"]) == {"other", "aid2e"}
    server = parsed["mcp_servers"]["aid2e"]
    assert server["command"] == str(Path(sys.executable).absolute())
    assert server["args"] == _expected_args(tmp_path.resolve())
    assert server["cwd"] == str(tmp_path.resolve())

    assert init_workspace(tmp_path, client="codex")["written"] == []
    assert (codex_dir / "config.toml").read_text() == text


def test_codex_init_refuses_unowned_server_table(tmp_path: Path) -> None:
    codex_dir = tmp_path / ".codex"
    codex_dir.mkdir()
    (codex_dir / "config.toml").write_text('[mcp_servers.aid2e]\ncommand = "mine"\n')

    with pytest.raises(ValueError, match="unowned"):
        init_workspace(tmp_path, client="codex")


def test_both_clients_share_one_workspace(tmp_path: Path) -> None:
    init_workspace(tmp_path, client="claude")
    init_workspace(tmp_path, client="codex")
    metadata = json.loads((tmp_path / METADATA_FILE).read_text())
    assert set(metadata["clients"]) == {"claude", "codex"}
    # Claude ownership survives a Codex init, so a Claude re-run still refreshes.
    init_workspace(tmp_path, client="claude")


def test_with_instructions_never_overwrites(tmp_path: Path) -> None:
    init_workspace(tmp_path, client="claude", with_instructions=True)
    claude_md = (tmp_path / "CLAUDE.md").read_text()
    assert claude_md.startswith("# AID2E Code Assistant for Claude Code")
    assert "validate_workspace_file" in claude_md

    (tmp_path / "AGENTS.md").write_text("my rules\n")
    result = init_workspace(tmp_path, client="codex", with_instructions=True)
    assert (tmp_path / "AGENTS.md").read_text() == "my rules\n"
    assert any("Kept existing AGENTS.md" in warning for warning in result["warnings"])


def test_profiles_follow_model_class() -> None:
    assert CLIENT_PROFILES == {
        "claude": "reference",
        "codex": "reference",
        "opencode": "full",
        "vscode": "full",
    }


def test_opencode_init_targets_local_model_with_only_aid2e_tools(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv(LLM_API_KEY_ENV, "sk-secret-should-not-be-written")
    result = init_workspace(tmp_path, client="opencode", llm_url="http://gw:4000/v1", llm_model="code-assist-100b")
    assert result["profile"] == "full"

    config = json.loads((tmp_path / "opencode.json").read_text())
    root = tmp_path.resolve()
    assert config["mcp"]["aid2e"] == {
        "type": "local",
        "command": [str(Path(sys.executable).absolute()), *_expected_args(root, "full")],
        "enabled": True,
    }
    provider = config["provider"]["aid2e"]
    assert provider["npm"] == "@ai-sdk/openai-compatible"
    assert provider["options"] == {"baseURL": "http://gw:4000/v1", "apiKey": "{env:AID2E_LLM_API_KEY}"}
    assert list(provider["models"]) == ["code-assist-100b"]
    assert config["model"] == "aid2e/code-assist-100b"
    for tool in ("bash", "edit", "write", "read", "grep", "glob", "task", "skill", "webfetch"):
        assert config["tools"][tool] is False
    assert config["agent"]["plan"]["tools"] == {
        f"aid2e_{tool}": False
        for tool in (
            "create_file_in_workspace", "move_file_in_workspace", "replace_lines_in_workspace", "append_to_file_in_workspace",
            "run_workspace_tests",
        )
    }

    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert "sk-secret" not in path.read_text()
    assert init_workspace(tmp_path, client="opencode", llm_url="http://gw:4000/v1", llm_model="code-assist-100b")["written"] == []


def test_opencode_init_respects_user_choices(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text(
        json.dumps({
            "model": "anthropic/claude-x",
            "tools": {"bash": True},
            "mcp": {"other": {"type": "local", "command": ["x"]}},
            "provider": {"other": {"npm": "y"}},
        })
    )
    result = init_workspace(tmp_path, client="opencode")
    config = json.loads((tmp_path / "opencode.json").read_text())
    assert config["model"] == "anthropic/claude-x"
    assert config["tools"]["bash"] is True and config["tools"]["edit"] is False
    assert set(config["mcp"]) == {"other", "aid2e"} and set(config["provider"]) == {"other", "aid2e"}
    assert any("model" in warning for warning in result["warnings"])
    assert any("tools.bash" in warning for warning in result["warnings"])

    config["mcp"]["aid2e"]["enabled"] = False
    (tmp_path / "opencode.json").write_text(json.dumps(config))
    with pytest.raises(ValueError, match="unowned or modified `mcp.aid2e`"):
        init_workspace(tmp_path, client="opencode")


def test_opencode_reference_override_restores_native_tools(tmp_path: Path) -> None:
    init_workspace(tmp_path, client="opencode")
    init_workspace(tmp_path, client="opencode", profile="reference")
    config = json.loads((tmp_path / "opencode.json").read_text())
    assert "tools" not in config and "agent" not in config
    assert config["mcp"]["aid2e"]["command"][-1] == "reference"


def test_opencode_plan_agent_keeps_user_settings(tmp_path: Path) -> None:
    (tmp_path / "opencode.json").write_text(json.dumps({"agent": {"plan": {"model": "x/y"}}}))
    init_workspace(tmp_path, client="opencode")
    init_workspace(tmp_path, client="opencode", profile="reference")
    config = json.loads((tmp_path / "opencode.json").read_text())
    assert config["agent"] == {"plan": {"model": "x/y"}}


def test_opencode_refuses_jsonc(tmp_path: Path) -> None:
    (tmp_path / "opencode.jsonc").write_text("{}")
    with pytest.raises(ValueError, match="opencode.jsonc"):
        init_workspace(tmp_path, client="opencode")


def test_vscode_init_writes_mcp_json_and_restricted_agent(tmp_path: Path) -> None:
    (tmp_path / ".vscode").mkdir()
    (tmp_path / ".vscode" / "mcp.json").write_text(json.dumps({"servers": {"other": {"type": "stdio", "command": "x"}}}))
    init_workspace(tmp_path, client="vscode")

    config = json.loads((tmp_path / ".vscode" / "mcp.json").read_text())
    assert set(config["servers"]) == {"other", "aid2eLocal"}
    assert config["servers"]["aid2eLocal"] == {
        "type": "stdio",
        "command": str(Path(sys.executable).absolute()),
        "args": _expected_args(tmp_path.resolve(), "full"),
    }
    agent = (tmp_path / ".github" / "agents" / "aid2e.agent.md").read_text()
    assert "tools: ['aid2eLocal/*']" in agent

    assert init_workspace(tmp_path, client="vscode")["written"] == []


def test_claude_and_vscode_in_one_project_use_distinct_ids_and_warn(tmp_path: Path) -> None:
    first = init_workspace(tmp_path, client="claude")
    assert not any("both the Claude Code server" in w for w in first["warnings"])

    second = init_workspace(tmp_path, client="vscode")
    assert any("both the Claude Code server" in w for w in second["warnings"])
    claude = json.loads((tmp_path / ".mcp.json").read_text())["mcpServers"]
    vscode = json.loads((tmp_path / ".vscode" / "mcp.json").read_text())["servers"]
    assert set(claude) == {"aid2e"} and set(vscode) == {"aid2eLocal"}
    assert claude["aid2e"]["args"][-1] == "reference" and vscode["aid2eLocal"]["args"][-1] == "full"

    # The warning appears from either side once both exist.
    assert any("both the Claude Code server" in w for w in init_workspace(tmp_path, client="claude")["warnings"])


def test_vscode_migrates_previous_server_id(tmp_path: Path) -> None:
    from aid2e.mcp import client_setup

    init_workspace(tmp_path, client="vscode")
    # Rewrite the project as the earlier release left it: server ID `aid2e`.
    config_path = tmp_path / ".vscode" / "mcp.json"
    config = json.loads(config_path.read_text())
    config["servers"] = {"aid2e": config["servers"].pop("aid2eLocal")}
    config_path.write_text(json.dumps(config))
    metadata = json.loads((tmp_path / METADATA_FILE).read_text())
    managed = metadata["clients"]["vscode"]["managed"]
    managed["servers.aid2e"] = managed.pop("servers.aid2eLocal")
    (tmp_path / METADATA_FILE).write_text(json.dumps(metadata))
    agent = tmp_path / ".github" / "agents" / "aid2e.agent.md"
    agent.write_text(client_setup._VSCODE_AGENT_LEGACY[0])

    init_workspace(tmp_path, client="vscode")
    assert set(json.loads(config_path.read_text())["servers"]) == {"aid2eLocal"}
    assert "tools: ['aid2eLocal/*']" in agent.read_text()


def test_legacy_claude_record_still_refreshes(tmp_path: Path) -> None:
    init_workspace(tmp_path, client="claude")
    metadata = json.loads((tmp_path / METADATA_FILE).read_text())
    claude = metadata["clients"]["claude"]
    metadata["clients"]["claude"] = {
        "client_config": claude["client_config"],
        "managed_mcp_config": claude["managed"]["mcpServers.aid2e"],
    }
    (tmp_path / METADATA_FILE).write_text(json.dumps(metadata))
    init_workspace(tmp_path, client="claude")


def test_cli_init_and_help(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["mcp", "init", "--client", "claude", "--workspace", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "Initialized workspace" in result.output
    assert "Claude Code: read-only AID2E Reference Source tools" in result.output
    assert (tmp_path / ".mcp.json").exists()

    help_result = runner.invoke(cli, ["mcp", "--help"])
    assert help_result.exit_code == 0
    assert "--tools" in help_result.output and "init" in help_result.output

    oc = runner.invoke(
        cli,
        ["mcp", "init", "--client", "opencode", "--workspace", str(tmp_path), "--llm-model", "code-assist-gemma-26b"],
    )
    assert oc.exit_code == 0, oc.output
    assert "OpenCode (local model): full AID2E tool suite, native tools disabled" in oc.output
    assert json.loads((tmp_path / "opencode.json").read_text())["model"] == "aid2e/code-assist-gemma-26b"


def test_cli_init_reports_conflict(tmp_path: Path) -> None:
    (tmp_path / ".mcp.json").write_text("[]")
    result = CliRunner().invoke(cli, ["mcp", "init", "--client", "claude", "--workspace", str(tmp_path)])
    assert result.exit_code != 0
    assert "Workspace init failed" in result.output


_WRITE_TOOLS = {
    "set_workspace_root",
    "list_workspace_files",
    "search_workspace",
    "read_file_in_workspace",
    "create_file_in_workspace",
    "move_file_in_workspace",
    "replace_lines_in_workspace",
    "append_to_file_in_workspace",
    "run_workspace_tests",
}
_SOURCE_REFERENCE_TOOLS = {
    "get_subsystem_blueprints",
    "search_repository",
    "grep_framework_source",
    "get_symbol_source",
    "get_class_contracts",
    "read_framework_file",
    "read_example_file",
    "list_files_in_framework_subdirectory",
    "list_example_directory_files",
}


def _profile_tools(profile: str) -> set[str]:
    """Register a profile in a fresh interpreter (the server module is a singleton)."""
    script = textwrap.dedent(
        f"""
        import asyncio, json
        from aid2e.mcp import server
        server.register_tools({profile!r})
        print(json.dumps(sorted(tool.name for tool in asyncio.run(server.mcp.list_tools()))))
        """
    )
    pytest.importorskip("mcp")
    output = subprocess.run(
        [sys.executable, "-c", script], check=True, capture_output=True, text=True
    ).stdout
    return set(json.loads(output.strip().splitlines()[-1]))


def test_tool_profiles() -> None:
    full = _profile_tools("full")
    reference = _profile_tools("reference")

    assert _WRITE_TOOLS <= full
    assert reference.isdisjoint(_WRITE_TOOLS)
    assert reference == full - _WRITE_TOOLS
    assert reference == _SOURCE_REFERENCE_TOOLS | {"debug_workspace", "validate_workspace_file"}
    assert full == reference | _WRITE_TOOLS
    assert len(full) == 20 and len(reference) == 11


def _profile_instructions(profile: str) -> str:
    """Return the server instructions advertised for a profile (fresh interpreter)."""
    pytest.importorskip("mcp")
    script = textwrap.dedent(
        f"""
        import json
        from aid2e.mcp import server
        server.register_tools({profile!r})
        print(json.dumps(server.mcp.instructions))
        """
    )
    output = subprocess.run([sys.executable, "-c", script], check=True, capture_output=True, text=True).stdout
    return json.loads(output.strip().splitlines()[-1])


def test_profile_instructions() -> None:
    from aid2e.mcp import server

    reference = _profile_instructions("reference")
    for rule in ("read-only", "Never invent names", "Never modify the Reference Source", "validate_workspace_file"):
        assert rule in reference
    assert "create_file_in_workspace" not in reference
    assert _profile_instructions("full") == server._FULL_INSTRUCTIONS


def test_init_lists_machine_specific_files(tmp_path: Path) -> None:
    result = init_workspace(tmp_path, client="claude", with_instructions=True)
    root = tmp_path.resolve()
    assert set(result["machine_specific"]) == {
        str(root / ".mcp.json"),
        str(root / ".claude" / "settings.local.json"),
        str(root / METADATA_FILE),
    }
    assert str(root / "CLAUDE.md") not in result["machine_specific"]
    assert init_workspace(tmp_path, client="claude")["machine_specific"] == []

    out = CliRunner().invoke(cli, ["mcp", "init", "--client", "codex", "--workspace", str(tmp_path)]).output
    assert "keep them out of version control: .codex/config.toml, .aid2e-workspace.json" in out
