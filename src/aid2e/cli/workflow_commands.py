"""
Workflow execution commands for AID2E CLI.

Commands for running optimization workflows and managing execution lifecycle:
- optimize: Run optimization from configuration (current placeholder)
- run: Execute full workflow (planned)
- resume: Restart from checkpoint (planned)
- stop: Halt running optimization (planned)
- status: Check optimization progress (planned)
- clean: Remove temporary files (planned)
"""

import sys
from typing import Optional

import click

from aid2e.utilities.configurations import load_config
from aid2e.utilities.optimization_runner import (
    OptimizationRunOptions,
    run_optimization_from_config,
)


@click.command(name="optimize")
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--validate-only", is_flag=True, help="Validate config but do not run")
@click.option(
    "--workflow",
    "workflow_name",
    help="Workflow name to execute when multiple workflows are configured",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(file_okay=False),
    help="Override optimization output directory",
)
@click.option("--run-id", help="Stable run identifier for output/checkpoint files")
@click.option(
    "-v",
    "--verbosity",
    count=True,
    help="Increase verbosity (can be used multiple times)",
)
@click.option("--log", "log_file", type=click.Path(dir_okay=False), help="Path to log file")
def optimize(
    config_file: str,
    validate_only: bool,
    workflow_name: Optional[str],
    output_dir: Optional[str],
    run_id: Optional[str],
    verbosity: int,
    log_file: Optional[str],
):
    """
    Run optimization based on configuration file.
    
    CONFIG_FILE: Path to the YAML configuration file.
    
    Example:
        aid2e optimize optimization.yml
        aid2e optimize optimization.yml --validate-only
        aid2e optimize optimization.yml -vv --log output.log
    """
    try:
        if verbosity > 0:
            click.echo(f"Loading configuration from: {config_file}")
        
        config = load_config(config_file)
        
        if validate_only:
            click.echo(
                click.style("✓ Configuration validated; skipping execution.", fg="green")
            )
            return
        
        click.echo(
            click.style(
                f"Running optimization: {config.optimizer.name}",
                fg="cyan",
                bold=True,
            )
        )
        click.echo(f"  Algorithm: {config.optimizer.name} ({config.optimizer.type})")
        click.echo(f"  Iterations: {config.optimizer.parameters.get('n_iterations', 'N/A')}")
        if workflow_name:
            click.echo(f"  Workflow: {workflow_name}")
        if output_dir:
            click.echo(f"  Output: {output_dir}")
        if run_id:
            click.echo(f"  Run ID: {run_id}")
        click.echo(f"  Verbosity: {verbosity}")
        if log_file:
            click.echo(f"  Log file: {log_file}")
        click.echo()

        log_level = "DEBUG" if verbosity > 1 else "INFO"
        result = run_optimization_from_config(
            config,
            options=OptimizationRunOptions(
                workflow_name=workflow_name,
                output_dir=output_dir,
                run_id=run_id,
                log_level=log_level,
            ),
        )

        click.echo(click.style("✓ Optimization completed.", fg="green"))
        click.echo(f"  Run directory: {result.run_dir}")
        click.echo(
            f"  Trials: {result.completed_trials} completed, "
            f"{result.failed_trials} failed"
        )
        click.echo(f"  Pareto front size: {len(result.pareto_front)}")

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        if verbosity > 1:
            import traceback
            traceback.print_exc()
        sys.exit(1)


# Future commands (placeholders for documentation)

def run_command():
    """
    Execute complete optimization workflow (PLANNED).
    
    Will support:
    - Full orchestration: config → problem → optimizer → execution → results
    - Checkpoint/resume support
    - Output directory override
    - Dry-run mode
    
    Usage:
        aid2e run config.yml
        aid2e run config.yml --dry-run
        aid2e run config.yml --output results/experiment_1/
        aid2e run config.yml --resume checkpoint.json
    """
    pass


def resume_command():
    """
    Resume optimization from checkpoint (PLANNED).
    
    Will support:
    - Restart interrupted optimization from saved state
    - Continue from specific iteration
    - Merge results with previous runs
    
    Usage:
        aid2e resume checkpoint.json
        aid2e resume checkpoint.json --iterations 50
    """
    pass


def stop_command():
    """
    Gracefully halt running optimization (PLANNED).
    
    Will support:
    - Stop by run ID or process ID
    - Save checkpoint before stopping
    - Force stop option
    
    Usage:
        aid2e stop <run_id>
        aid2e stop <run_id> --force
        aid2e stop --all
    """
    pass


def status_command():
    """
    Check progress of optimizations (PLANNED).
    
    Will support:
    - Show active runs
    - Display iteration progress
    - Show current best objectives
    - List completed runs
    
    Usage:
        aid2e status
        aid2e status <run_id>
        aid2e status --all
    """
    pass


def clean_command():
    """
    Remove temporary and intermediate files (PLANNED).
    
    Will support:
    - Clean work directories
    - Remove old checkpoints
    - Clear cache files
    - Dry-run to preview deletions
    
    Usage:
        aid2e clean <output_dir>
        aid2e clean <output_dir> --dry-run
        aid2e clean <output_dir> --keep-checkpoints
    """
    pass
