"""Optimizers package CLI commands (plugin for core).

Provides `optimize` command registered via entry points.
"""
from pathlib import Path
import click


@click.command(name="optimize")
@click.option("-c", "--config", "config_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--validate-only", is_flag=True, help="Validate config but do not run")
@click.option("-v", "--verbosity", type=int, default=0)
@click.option("--log", "log_file", type=click.Path(dir_okay=False, path_type=Path))
def optimize_cmd(config_path: Path, validate_only: bool, verbosity: int, log_file: Path | None):
    """Run optimization (stub implementation).

    This command is discovered by core via the `aid2e.commands` entry point group.
    """
    from configurations import load_config
    cfg = load_config(str(config_path))
    if validate_only:
        click.echo("✓ Configuration validated; skipping execution.")
        return
    # Placeholder execution; in real code delegate to algorithm runner
    click.echo(f"Running optimization for: {config_path}")
    click.echo(f"Verbosity={verbosity}, Log={log_file}")
    click.echo(f"Algorithm: {cfg.optimization.optimizer.name} ({cfg.optimization.optimizer.type})")
    click.echo("Note: optimizer execution not yet implemented.")
