"""
Workflow execution commands for AID2E CLI.

Commands for running optimization workflows and managing execution lifecycle:
- optimize: Run optimization from configuration
- run: Execute one configured workflow without the optimizer loop (planned)
- resume: Restart from checkpoint (planned)
- stop: Halt running optimization (planned)
- status: Check optimization progress (planned)
- clean: Remove temporary files (planned)
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click

from aid2e.utilities.configurations import load_config
from aid2e.utilities.runtime_builders import run_optimization

@click.command(name="optimize")
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--validate-only", is_flag=True, help="Validate config but do not run")
@click.option("-v", "--verbosity", count=True, help="Increase verbosity (can be used multiple times)")
@click.option("--log", "log_file", type=click.Path(dir_okay=False), help="Path to log file")
@click.option("--workflow", "workflow_name", help="Workflow name to execute")
@click.option("--output", "output_dir", type=click.Path(file_okay=False), help="Output directory for this run")
@click.option("--run-id", help="Run directory name under the output directory")
def optimize(
    config_file: str,
    validate_only: bool,
    verbosity: int,
    log_file: Optional[str],
    workflow_name: Optional[str],
    output_dir: Optional[str],
    run_id: Optional[str],
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
            click.echo(click.style("✓ Configuration validated; skipping execution.", fg="green"))
            return
        
        # Display optimization info
        click.echo(click.style(f"Running optimization: {config.optimizer.name}", fg="cyan", bold=True))
        click.echo(f"  Algorithm: {config.optimizer.name} ({config.optimizer.type})")
        click.echo(f"  Iterations: {config.optimizer.parameters.get('n_iterations', 'N/A')}")
        click.echo(f"  Verbosity: {verbosity}")
        if log_file:
            click.echo(f"  Log file: {log_file}")
        if workflow_name:
            click.echo(f"  Workflow: {workflow_name}")
        if output_dir:
            click.echo(f"  Output: {output_dir}")
        if run_id:
            click.echo(f"  Run ID: {run_id}")
        click.echo()
        log_level = "DEBUG" if verbosity > 1 else "INFO" if verbosity else "WARNING"
        if log_file:
            log_path = Path(log_file).expanduser()
            log_path.parent.mkdir(parents=True, exist_ok=True)
            logging.basicConfig(
                filename=log_path,
                level=getattr(logging, log_level),
                format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                force=True,
            )
        results = run_optimization(
            config,
            config_file,
            workflow_name=workflow_name,
            output_dir=output_dir,
            run_id=run_id,
            log_level=log_level,
        )
        click.echo(click.style("Optimization completed.", fg="green"))
        click.echo(f"  Run directory: {results['run_dir']}")
        click.echo(f"  Results: {results['optimization_results']}")

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        if verbosity > 1:
            import traceback
            traceback.print_exc()
        sys.exit(1)


# Future commands (planned, not registered yet)

def run_command():
    """
    Execute one configured workflow without the optimizer loop (PLANNED).

    Will support:
    - Single workflow execution from config
    - Problem/workflow/scheduler setup
    - Objective/result collection
    - Output directory override
    - Dry-run mode

    Usage:
        aid2e run config.yml
        aid2e run config.yml --dry-run
        aid2e run config.yml --output results/experiment_1/
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
