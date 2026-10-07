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

    MCP:
      mcp        - Run the AID2E MCP server
    """
    pass


@click.command(name="mcp")
@click.option("--sse", is_flag=True, help="Run over streamable HTTP instead of stdio.")
@click.pass_context
def mcp(ctx: click.Context, sse: bool) -> None:
    """Run the AID2E MCP server.

    The server is imported only when this command is invoked so the main CLI
    remains usable when the optional ``mcp`` dependency is not installed.
    """
    try:
        from aid2e.mcp.server import mcp_command
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc

    ctx.invoke(mcp_command, sse=sse)


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
