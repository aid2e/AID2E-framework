#!/usr/bin/env python3
"""
AID2E Command Line Interface.

Main CLI entry point that coordinates all command modules:
- Config commands: describe, inspect, validate (config_commands.py)
- Workflow commands: optimize, run (workflow_commands.py)
- Utility commands: list, version (utility_commands.py)
"""

import click
import importlib.metadata
from pathlib import Path

from aid2e import __MAIN_VERSION__

# Import commands from modular files
from .config_commands import describe, inspect, validate
from .workflow_commands import optimize
from .utility_commands import list_resources, version


@click.group()
@click.version_option(version=__MAIN_VERSION__, prog_name="aid2e")
def cli():
    """
    AID2E - AI assisted Detector Design for EIC.
    
    A framework for optimization of detector designs and other complex systems.
    
    Commands are organized into categories:
    
    \b
    Configuration Inspection:
      describe   - Quick summary of config files (auto-detects type)
      inspect    - Detailed configuration view with section filtering
      validate   - Validate configuration syntax and structure
    
    \b
    Workflow Execution:
      optimize   - Run optimization from configuration
    
    \b
    Utilities:
      list       - Show available optimizers/templates/problems
      version    - Display version information

    \b
    MCP:
      mcp        - Run the AID2E MCP server
      mcp init   - Set up Claude Code, Codex, OpenCode, or VS Code in a project
    """
    pass


@click.group(name="mcp", invoke_without_command=True)
@click.option("--sse", is_flag=True, help="Run over streamable HTTP instead of stdio.")
@click.option(
    "--workspace",
    default=None,
    help="Set the initial User Workspace directory (or use AID2E_WORKSPACE; no CWD fallback).",
)
@click.option(
    "--tools",
    type=click.Choice(["full", "reference"]),
    default="full",
    show_default=True,
    help="Tool profile: 'full' (workspace read/write suite) or 'reference' (read-only Reference Source tools).",
)
@click.pass_context
def mcp(ctx: click.Context, sse: bool, workspace: str | None = None, tools: str = "full") -> None:
    """Run the AID2E MCP server.

    Use `aid2e mcp init --client claude|codex|opencode|vscode` to configure a
    client in a project. The server is imported only when it is started so the main CLI remains
    usable when the optional ``mcp`` dependency is not installed.
    """
    if ctx.invoked_subcommand is not None:
        return
    try:
        from aid2e.mcp.server import mcp_command
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    ctx.invoke(mcp_command, sse=sse, workspace=workspace, tools=tools)


@mcp.command(name="init")
@click.option(
    "--client",
    type=click.Choice(["claude", "codex", "opencode", "vscode"]),
    required=True,
    help="Client to configure. Claude Code/Codex (hosted agents) get read-only reference tools; "
    "OpenCode/VS Code (local AID2E models) get the full aid2e suite with native tools disabled.",
)
@click.option(
    "--workspace",
    default=None,
    type=click.Path(file_okay=False),
    help="Project directory to configure (default: current directory).",
)
@click.option(
    "--with-instructions",
    is_flag=True,
    help="Also create CLAUDE.md (Claude) or AGENTS.md (Codex) with AID2E guidance, only if absent.",
)
@click.option(
    "--tools",
    "profile",
    type=click.Choice(["full", "reference"]),
    default=None,
    help="Override the client's default tool profile.",
)
@click.option(
    "--llm-url",
    default=None,
    help="OpenAI-compatible base URL of the LLM gateway (OpenCode; default: the AID2E LiteLLM gateway).",
)
@click.option(
    "--llm-model",
    default=None,
    help="Model served by the gateway (OpenCode; default code-assist, which follows the deployed model).",
)
def mcp_init(
    client: str,
    workspace: str | None,
    with_instructions: bool,
    profile: str | None,
    llm_url: str | None,
    llm_model: str | None,
) -> None:
    """Configure a project-local client workspace for the AID2E MCP server.

    Writes project-local configuration only: `.mcp.json` (Claude),
    `.codex/config.toml` (Codex), `opencode.json` (OpenCode), or
    `.vscode/mcp.json` plus an `AID2E` custom agent (VS Code). The server is
    launched with this Python interpreter. No global client configuration,
    authentication, or API key is written.
    """
    from aid2e.mcp.client_setup import DEFAULT_LLM_MODEL, DEFAULT_LLM_URL, init_workspace

    if client != "opencode" and (llm_url or llm_model):
        click.secho("Warning: --llm-url/--llm-model only apply to --client opencode; ignoring them.", fg="yellow", err=True)
    try:
        result = init_workspace(
            workspace,
            client=client,
            with_instructions=with_instructions,
            profile=profile,
            llm_url=llm_url or DEFAULT_LLM_URL,
            llm_model=llm_model or DEFAULT_LLM_MODEL,
        )
    except (OSError, ValueError) as exc:
        raise click.ClickException(f"Workspace init failed: {exc}") from exc

    click.echo(f"Initialized workspace: {result['workspace']}")
    click.echo(f"  {result['description']}")
    click.echo(f"MCP config: {result['client_config']}")
    for path in result["written"]:
        click.echo(f"  wrote {path}")
    for warning in result["warnings"]:
        click.secho(f"Warning: {warning}", fg="yellow", err=True)
    if result["machine_specific"]:
        root = Path(result["workspace"])
        names = ", ".join(Path(path).relative_to(root).as_posix() for path in result["machine_specific"])
        click.echo(f"These files contain machine-specific absolute paths; keep them out of version control: {names}")
    click.echo("Next steps:")
    for step in result["next_steps"]:
        click.echo(f"  {step}")


def _load_plugin_commands(group: click.Group):
    """
    Discover and register plugin commands from entry points.

    Uses the `aid2e.commands` entry point group. Each entry point must
    resolve to a Click command object.
    
    Args:
        group: Click command group to register plugins to
    """
    try:
        eps = importlib.metadata.entry_points()
        candidates = eps.select(group="aid2e.commands") if hasattr(eps, "select") else eps.get("aid2e.commands", [])
        for ep in candidates:
            try:
                cmd = ep.load()
                if isinstance(cmd, click.core.Command):
                    group.add_command(cmd)
            except Exception:
                # Swallow plugin errors to keep the CLI functional
                continue
    except Exception:
        # If entry point discovery fails, keep the CLI functional
        pass


# Register commands from modular files
cli.add_command(describe)
cli.add_command(inspect)
cli.add_command(validate)
cli.add_command(optimize)
cli.add_command(list_resources, name="list")
cli.add_command(version)
cli.add_command(mcp)

# Load plugin commands
_load_plugin_commands(cli)


if __name__ == "__main__":
    cli()
