"""
Utility commands for AID2E CLI.

Auxiliary commands for displaying information and managing resources:
- list: Show available optimizers/templates/problems
- version: Display version information
- init: Create configs from templates (planned)
- graph: Visualize workflow structure (planned)
"""

from typing import Optional

import click

from aid2e import __MAIN_VERSION__


@click.command()
@click.argument("item_type", type=click.Choice(["optimizers", "templates", "problems"]), required=False)
def list_resources(item_type: Optional[str]):
    """
    List available optimizers, templates, or problem types.
    
    Examples:
        aid2e list optimizers
        aid2e list templates
        aid2e list problems
        aid2e list  # Shows all categories
    """
    if item_type is None or item_type == "optimizers":
        click.echo(click.style("Available Optimizers:", fg="cyan", bold=True))
        click.echo("  • ax (Bayesian Optimization)")
        click.echo("    - Initialization: Sobol quasi-random")
        click.echo("    - Surrogate: SAASBO (Sparse Axis-Aligned Subspace BO)")
        click.echo("    - Acquisition: qNEHVI (Noisy Expected Hypervolume Improvement)")
        click.echo("    - Use case: Multi-objective optimization, continuous parameters")
        click.echo()
    
    if item_type is None or item_type == "templates":
        click.echo(click.style("Available Templates:", fg="cyan", bold=True))
        click.echo("  • dtlz2 - Multi-objective test problem (2 objectives, 10 variables)")
        click.echo("  • basic - Minimal configuration template")
        click.echo("  • epic_tracking - EPIC detector tracking optimization")
        click.echo()
    
    if item_type is None or item_type == "problems":
        click.echo(click.style("Supported Problem Types:", fg="cyan", bold=True))
        click.echo("  • toy - Benchmark test problems (DTLZ2, ZDT, etc.)")
        click.echo("  • epic_tracking - EPIC detector tracking system")
        click.echo("  • custom - User-defined evaluation functions")
        click.echo()


@click.command()
def version():
    """Display version information."""
    click.echo(f"AID2E Framework v{__MAIN_VERSION__}")
    click.echo("AI assisted Detector Design for EIC")


# Future commands (planned, not registered yet)

def init_command():
    """
    Create configuration files from templates (PLANNED).

    Will support:
    - Template-based generation
    - Interactive wizard mode
    - Type-specific templates (design/problem/optimization)

    Usage:
        aid2e init --template dtlz2
        aid2e init --type design > design.yml
        aid2e init --interactive
    """
    pass


def graph_command():
    """
    Visualize workflow structure and dependencies (PLANNED).

    Will support:
    - Dependency graph generation
    - Export to PNG/SVG/DOT
    - Show parameter flow

    Usage:
        aid2e graph config.yml
        aid2e graph config.yml --output workflow.png
        aid2e graph config.yml --format svg
    """
    pass
