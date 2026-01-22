"""
Legacy CLI commands for AID2E.

Commands maintained for backward compatibility, to be deprecated in future versions:
- load: Load and validate configuration (replaced by describe/validate)
- info: Display detailed information (replaced by inspect)

These commands will show deprecation warnings and may be removed in version 1.0.0.
"""

import sys

import click

from aid2e.utilities.configurations import load_config


@click.command(name="load")
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--validate-only", is_flag=True, help="Only validate the configuration without running")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def load(config_file: str, validate_only: bool, verbose: bool):
    """
    Load and validate an optimization configuration from a YAML file.
    
    ⚠️  DEPRECATED: This command is deprecated. Use 'describe' or 'validate' instead:
        - For quick summary: aid2e describe <config>
        - For validation: aid2e validate <config>
        - For detailed view: aid2e inspect <config>
    
    CONFIG_FILE: Path to the YAML configuration file.
    
    Example:
        aid2e load optimization.yml
        aid2e load optimization.yml --validate-only
    """
    # Show deprecation warning
    click.echo(click.style("⚠️  WARNING: 'load' command is deprecated.", fg="yellow", bold=True))
    click.echo(click.style("   Use 'aid2e describe' for summaries or 'aid2e validate' for validation.", fg="yellow"))
    click.echo()
    
    try:
        if verbose:
            click.echo(f"Loading configuration from: {config_file}")

        config = load_config(config_file)

        click.echo(click.style("✓ Configuration loaded successfully!", fg="green"))
        click.echo()
        click.echo(click.style("Configuration Summary:", bold=True))
        click.echo(f"  Problem: {config.problem.name}")
        click.echo(f"  Type: {config.problem.problem_type}")
        click.echo(f"  Output: {config.problem.output_location}")
        click.echo(f"  Work: {config.problem.work_location}")
        click.echo()
        click.echo(f"  Optimizer: {config.optimization.optimizer.name} ({config.optimization.optimizer.type})")
        click.echo(f"  Iterations: {config.optimization.n_iterations}")
        click.echo(f"  Initial Samples: {config.optimization.n_initial_samples}")
        click.echo(f"  Parallel Evaluations: {config.optimization.parallel_evaluations}")
        click.echo()

        param_names = config.problem.design_config.get_parameter_names()
        click.echo(f"  Design Parameters: {len(param_names)}")
        if verbose:
            for name in param_names:
                param = config.problem.design_config.get_flat_parameters()[name]
                bounds = config.problem.design_config.get_parameter_bounds(name)
                click.echo(f"    - {name}: {param.value} {bounds}")

        if config.optimization.objectives:
            click.echo()
            click.echo(f"  Objectives ({len(config.optimization.objectives)}):")
            for obj in config.optimization.objectives:
                click.echo(f"    - {obj}")

        if config.problem.design_config.parameter_constraints:
            click.echo()
            click.echo(f"  Parameter Constraints ({len(config.problem.design_config.parameter_constraints)}):")
            for constraint in config.problem.design_config.parameter_constraints:
                click.echo(f"    - {constraint.name}: {constraint.rule}")

        if validate_only:
            click.echo()
            click.echo(click.style("✓ Validation complete. Configuration is valid.", fg="green"))
            return

        click.echo()
        click.echo(click.style("Note: Optimization execution not yet implemented.", fg="yellow"))
        click.echo("The configuration has been validated and is ready to use.")

    except FileNotFoundError as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(click.style(f"✗ Configuration Error: {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Unexpected Error: {e}", fg="red"), err=True)
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
def info(config_file: str):
    """
    Display detailed information about a configuration file.
    
    ⚠️  DEPRECATED: This command is deprecated. Use 'inspect' instead:
        - aid2e inspect <config>
        - aid2e inspect <config> --section optimization
    
    CONFIG_FILE: Path to the YAML configuration file.
    
    Example:
        aid2e info optimization.yml
    """
    # Show deprecation warning
    click.echo(click.style("⚠️  WARNING: 'info' command is deprecated.", fg="yellow", bold=True))
    click.echo(click.style("   Use 'aid2e inspect' instead for detailed configuration view.", fg="yellow"))
    click.echo()
    
    try:
        config = load_config(config_file)

        click.echo(click.style("=" * 60, bold=True))
        click.echo(click.style(f"Configuration: {config.problem.name}", bold=True))
        click.echo(click.style("=" * 60, bold=True))
        click.echo()

        click.echo(click.style("PROBLEM CONFIGURATION", fg="cyan", bold=True))
        click.echo(f"  Name: {config.problem.name}")
        click.echo(f"  Type: {config.problem.problem_type}")
        click.echo(f"  Output Location: {config.problem.output_location}")
        click.echo(f"  Work Location: {config.problem.work_location}")
        click.echo()

        click.echo(click.style("DESIGN PARAMETERS", fg="cyan", bold=True))
        param_names = config.problem.design_config.get_parameter_names()
        flat_params = config.problem.design_config.get_flat_parameters()

        params_by_group = {}
        for name in param_names:
            group = name.split('.')[0]
            params_by_group.setdefault(group, []).append(name)

        for group, names in params_by_group.items():
            click.echo(f"\n  {group} ({len(names)} parameters):")
            for name in names:
                param = flat_params[name]
                param_short_name = name.split('.', 1)[1]
                bounds = config.problem.design_config.get_parameter_bounds(name)
                if bounds:
                    click.echo(f"    - {param_short_name}: {param.value} {bounds}")
                else:
                    choices = config.problem.design_config.get_parameter_choices(name)
                    click.echo(f"    - {param_short_name}: {param.value} {choices}")

        if config.problem.design_config.parameter_constraints:
            click.echo()
            click.echo(click.style("PARAMETER CONSTRAINTS", fg="cyan", bold=True))
            for constraint in config.problem.design_config.parameter_constraints:
                click.echo(f"  - {constraint.name}")
                click.echo(f"    Rule: {constraint.rule}")
                if constraint.description:
                    click.echo(f"    Description: {constraint.description}")

        click.echo()
        click.echo(click.style("OPTIMIZATION CONFIGURATION", fg="cyan", bold=True))
        click.echo(f"  Name: {config.optimization.name}")
        if config.optimization.description:
            click.echo(f"  Description: {config.optimization.description}")
        click.echo(f"  Optimizer: {config.optimization.optimizer.name} ({config.optimization.optimizer.type})")
        click.echo(f"  Iterations: {config.optimization.n_iterations}")
        click.echo(f"  Initial Samples: {config.optimization.n_initial_samples}")
        click.echo(f"  Parallel Evaluations: {config.optimization.parallel_evaluations}")

        if config.optimization.objectives:
            click.echo()
            click.echo(f"  Objectives ({len(config.optimization.objectives)}):")
            for obj in config.optimization.objectives:
                click.echo(f"    - {obj}")

        if config.optimization.optimizer.parameters:
            click.echo()
            click.echo("  Optimizer Parameters:")
            for key, value in config.optimization.optimizer.parameters.items():
                click.echo(f"    - {key}: {value}")

        click.echo()
        click.echo(click.style("=" * 60, bold=True))

    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)
