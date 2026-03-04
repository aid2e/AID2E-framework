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

from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
from aid2e.utilities.workflows.toy_evaluator import eval_epic_b0


@click.command(name="optimize")
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--validate-only", is_flag=True, help="Validate config but do not run")
@click.option("-v", "--verbosity", count=True, help="Increase verbosity (can be used multiple times)")
@click.option("--log", "log_file", type=click.Path(dir_okay=False), help="Path to log file")
def optimize(config_file: str, validate_only: bool, verbosity: int, log_file: Optional[str]):
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
        click.echo(click.style(f"Running optimization: {config.optimization.name}", fg="cyan", bold=True))
        click.echo(f"  Algorithm: {config.optimization.optimizer.name} ({config.optimization.optimizer.type})")
        click.echo(f"  Iterations: {config.optimization.n_iterations}")
        click.echo(f"  Verbosity: {verbosity}")
        if log_file:
            click.echo(f"  Log file: {log_file}")
        click.echo()
        
        # TODO: Implement actual optimization execution
        # This will involve:
        # 1. Instantiate optimizer from config.optimization.optimizer
        # 2. Setup problem evaluator from config.problem
        # 3. Run optimization loop
        # 4. Save results to config.problem.output_location
        
        # click.echo(click.style("Note: Optimizer execution not yet implemented.", fg="yellow"))
        # click.echo("The configuration has been validated and is ready for optimization.")

        # === Addressed TODO for B0 (toy model placeholder as objective function, to be replaced by Geant4 simulations later)

        if config.problem.problem_type != "EPIC_B0":
            click.echo(click.style("Note: Only EPIC_B0 toy execution is implemented for now.", fg="yellow"))
            click.echo("The configuration has been validated and is ready for optimization.")
            return

        dc = config.problem.design_config
        params = {}
        for name in dc.get_parameter_names():
            bounds = dc.get_parameter_bounds(name)
            if bounds is not None:
                params[name] = {"type": "range", "bounds": [float(bounds[0]), float(bounds[1])]}
            else:
                choices = dc.get_parameter_choices(name)
                params[name] = {"type": "choice", "values": list(choices)}
        search_space = SearchSpace(parameters=params)
        objective_names = [o.name for o in config.problem.objectives]
        n_init = int(config.optimization.n_initial_samples)
        n_iter = int(config.optimization.n_iterations)
        batch_size = int(getattr(config.optimization, "parallel_evaluations", 1))

        ax_cfg = AxOptimizerConfig(
            initialization_strategy="sobol",
            n_initial_samples=n_init,
            batch_size=batch_size,
            surrogate_model="saasbo",
            acquisition_function="qnehvi",  # OK for placeholder MOBO
            seed=42,
        )

        optimizer = AxOptimizer(
            search_space=search_space,
            config=ax_cfg,
            objective_names=objective_names,
            seed=42,
        )

        if verbosity > 0:
            click.echo(click.style("Running EPIC_B0 toy optimization (Ax)...", fg="cyan"))
            click.echo(f"  Objectives: {objective_names}")
            click.echo(f"  Sobol init: {n_init} | Iterations: {n_iter} | Batch: {batch_size}")
            click.echo()

        trial = 0
        n_total = n_init + n_iter * batch_size

        while trial < n_total:
            candidates = optimizer.suggest_candidates(n_candidates=batch_size)
            for design_point in candidates:
                # ok, failures = _check_constraints(dc, design_point)

                constraints = dc.parameter_constraints or []
                keys = sorted(design_point.keys(), key=len, reverse=True)
                failures = []
                for c in constraints:
                    expr = str(c.rule)
                    for k in keys:
                        expr = expr.replace(k, f"design_point[{k!r}]")
                    try:
                        if not bool(eval(expr, {"__builtins__": {}}, {"design_point": design_point})):
                            failures.append(c.name)
                    except Exception as e:
                        failures.append(f"{c.name} (eval error: {e})")
                ok = (len(failures) == 0)

                if not ok:
                    metrics = {name: -1e9 for name in objective_names}
                    if verbosity > 1:
                        click.echo(f"[trial {trial}] infeasible -> penalize ({failures})")
                else:
                    metrics = eval_epic_b0(design_point)
                    if verbosity > 1:
                        click.echo(f"[trial {trial}] {metrics}")

                optimizer.update_with_results(trial, design_point, metrics)
                trial += 1
                if trial >= n_total:
                    break

        best = optimizer.get_best_trial()
        click.echo(click.style("Best trial:", fg="green", bold=True))
        click.echo(f"  trial={best.index}")
        click.echo(f"  params={best.parameters}")
        click.echo(f"  metrics={best.metrics}")

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
