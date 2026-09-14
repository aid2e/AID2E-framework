"""
Shared helper functions for CLI commands.

This module contains utilities used across multiple CLI commands,
including config type detection, parameter counting, and formatters
for different output modes.
"""

from typing import Dict, Any
import click
import yaml


def detect_config_type(data: dict) -> str:
    """
    Detect configuration type from structure.
    
    Args:
        data: Parsed YAML configuration data
        
    Returns:
        Config type: 'full', 'problem', 'optimizer', 'design', or 'unknown'
    """
    if "problem" in data and "optimizer" in data:
        return "full"
    elif "problem" in data:
        return "problem"
    elif "optimizer" in data:
        return "optimizer"
    elif "design_space" in data or "design_parameters" in data:
        return "design"
    else:
        return "unknown"


def count_parameters(design_params: dict) -> int:
    """
    Count total parameters across all groups.
    
    Args:
        design_params: Design parameters dictionary (grouped)
        
    Returns:
        Total parameter count
    """
    count = 0
    for group_data in design_params.values():
        if isinstance(group_data, dict) and "parameters" in group_data:
            count += len(group_data["parameters"])
    return count


def format_description_text(data: dict, config_type: str, compact: bool, config_file: str):
    """
    Display text description of config.
    
    Args:
        data: Configuration data dictionary
        config_type: Detected configuration type
        compact: Whether to show compact output
        config_file: Path to config file (for display)
    """
    from pathlib import Path
    
    # Header
    click.echo(click.style("=" * 70, fg="cyan"))
    click.echo(click.style(f"Configuration: {Path(config_file).name}", bold=True, fg="cyan"))
    click.echo(click.style(f"Type: {config_type.upper()}", fg="cyan"))
    click.echo(click.style("=" * 70, fg="cyan"))
    click.echo()
    
    if config_type == "full":
        format_full_config(data, compact)
    elif config_type == "problem":
        format_problem_config(data, compact)
    elif config_type == "optimizer":
        format_optimizer_config(data, compact)
    elif config_type == "design":
        format_design_config(data, compact)
    else:
        click.echo(click.style("⚠ Unknown configuration format", fg="yellow"))
        click.echo("\nRaw structure:")
        click.echo(f"  Top-level keys: {list(data.keys())}")


def format_full_config(data: dict, compact: bool):
    """Format full configuration for text output."""
    problem = data.get("problem", {})
    optimizer = data.get("optimizer", {})
    parameters = optimizer.get("parameters", {})
    
    click.echo(click.style("PROBLEM", fg="green", bold=True))
    click.echo(f"  Name: {problem.get('name', 'N/A')}")
    click.echo(f"  Type: {problem.get('type', problem.get('problem_type', 'N/A'))}")
    
    if not compact:
        click.echo(f"  Output: {problem.get('output_location', 'N/A')}")
        click.echo(f"  Work Dir: {problem.get('work_location', 'N/A')}")
    
    # Design info
    if "design_parameters_file" in problem:
        click.echo(f"  Design: {problem['design_parameters_file']} (file)")
    elif "inline_design" in problem:
        design = problem["inline_design"].get("design_space", problem["inline_design"])
        param_count = count_parameters(design.get("design_parameters", {}))
        click.echo(f"  Design: inline ({param_count} parameters)")
    elif "design_space" in problem:
        param_count = count_parameters(problem["design_space"].get("design_parameters", {}))
        click.echo(f"  Design: inline ({param_count} parameters)")
    
    # Objectives
    objectives = problem.get("objectives", [])
    click.echo(f"  Objectives: {len(objectives)}")
    if not compact and objectives:
        for obj in objectives[:3]:  # Show first 3
            if isinstance(obj, dict):
                direction = obj.get("direction", "minimize" if obj.get("minimize", True) else "maximize")
                click.echo(f"    - {obj.get('name')}: {direction}")
            else:
                click.echo(f"    - {obj}")
        if len(objectives) > 3:
            click.echo(f"    ... and {len(objectives) - 3} more")
    
    click.echo()
    click.echo(click.style("OPTIMIZER", fg="green", bold=True))
    click.echo(f"  Algorithm: {optimizer.get('name', 'N/A')} ({optimizer.get('type', 'N/A')})")
    click.echo(f"  Iterations: {parameters.get('n_iterations', 'N/A')}")
    click.echo(f"  Initial Samples: {parameters.get('n_initial_samples', 'N/A')}")
    click.echo(f"  Batch Size: {parameters.get('batch_size', 1)}")
    
    if not compact and parameters:
        click.echo("  Parameters:")
        for key, val in list(parameters.items())[:5]:
            click.echo(f"    {key}: {val}")
        if len(parameters) > 5:
            click.echo(f"    ... and {len(parameters) - 5} more")


def format_problem_config(data: dict, compact: bool):
    """Format problem-only config for text output."""
    problem = data.get("problem", data)
    
    click.echo(f"Name: {problem.get('name', 'N/A')}")
    click.echo(f"Type: {problem.get('type', problem.get('problem_type', 'N/A'))}")
    
    objectives = problem.get("objectives", [])
    click.echo(f"Objectives: {len(objectives)}")
    if not compact and objectives:
        for obj in objectives:
            if isinstance(obj, dict):
                direction = obj.get("direction", "minimize" if obj.get("minimize", True) else "maximize")
                click.echo(f"  - {obj.get('name')}: {direction}")
    
    if "design_parameters_file" in problem:
        click.echo(f"Design Source: {problem['design_parameters_file']}")
    elif "inline_design" in problem:
        design = problem["inline_design"].get("design_space", problem["inline_design"])
        param_count = count_parameters(design.get("design_parameters", {}))
        click.echo(f"Design Source: inline ({param_count} parameters)")


def format_optimizer_config(data: dict, compact: bool):
    """Format optimizer-only config for text output."""
    optimizer = data.get("optimizer", data)
    parameters = optimizer.get("parameters", {})
    
    click.echo(f"Name: {optimizer.get('name', 'N/A')}")
    click.echo(f"Algorithm: {optimizer.get('name', 'N/A')} ({optimizer.get('type', 'N/A')})")
    click.echo(f"Iterations: {parameters.get('n_iterations', 'N/A')}")
    click.echo(f"Initial Samples: {parameters.get('n_initial_samples', 'N/A')}")
    
    if not compact and parameters:
        click.echo("\nParameters:")
        for key, val in parameters.items():
            click.echo(f"  {key}: {val}")


def format_design_config(data: dict, compact: bool):
    """Format design-only config for text output."""
    design_space = data.get("design_space", data)
    params = design_space.get("design_parameters", {})
    constraints = design_space.get("design_constraints", design_space.get("parameter_constraints", []))
    
    param_count = count_parameters(params)
    click.echo(f"Parameters: {param_count}")
    
    if not compact:
        for group_name, group_data in params.items():
            group_params = group_data.get("parameters", {})
            click.echo(f"  {group_name}: {len(group_params)} parameters")
    
    click.echo(f"Constraints: {len(constraints)}")
    if not compact and constraints:
        for c in constraints[:3]:
            click.echo(f"  - {c.get('name')}: {c.get('rule')}")
        if len(constraints) > 3:
            click.echo(f"  ... and {len(constraints) - 3} more")


def extract_description_data(data: dict, config_type: str) -> dict:
    """
    Extract structured description for JSON/YAML output.
    
    Args:
        data: Configuration data dictionary
        config_type: Detected configuration type
        
    Returns:
        Structured description dictionary
    """
    description = {
        "type": config_type,
        "summary": {}
    }
    
    if config_type == "full":
        problem = data.get("problem", {})
        optimizer = data.get("optimizer", {})
        parameters = optimizer.get("parameters", {})
        description["summary"] = {
            "problem_name": problem.get("name"),
            "problem_type": problem.get("type", problem.get("problem_type")),
            "optimizer": optimizer.get("name"),
            "n_iterations": parameters.get("n_iterations"),
            "n_objectives": len(problem.get("objectives", []))
        }
    elif config_type == "problem":
        problem = data.get("problem", data)
        description["summary"] = {
            "name": problem.get("name"),
            "type": problem.get("type", problem.get("problem_type")),
            "n_objectives": len(problem.get("objectives", []))
        }
    elif config_type == "optimizer":
        optimizer = data.get("optimizer", data)
        description["summary"] = {
            "name": optimizer.get("name"),
            "optimizer": optimizer.get("name"),
            "n_iterations": optimizer.get("parameters", {}).get("n_iterations"),
        }
    elif config_type == "design":
        design_space = data.get("design_space", data)
        params = design_space.get("design_parameters", {})
        constraints = design_space.get("design_constraints", design_space.get("parameter_constraints", []))
        description["summary"] = {
            "n_parameters": count_parameters(params),
            "n_constraints": len(constraints),
            "groups": list(params.keys())
        }
    
    return description


def inspect_full_config(config, section: str):
    """
    Inspect full configuration with optional section filter.
    
    Args:
        config: Loaded FullConfig object
        section: Section to display ('all', 'problem', 'design', 'optimizer')
    """
    click.echo(click.style("=" * 70, bold=True))
    click.echo(click.style(f"Configuration: {config.problem.name}", bold=True))
    click.echo(click.style("=" * 70, bold=True))
    click.echo()
    
    if section in ["all", "problem"]:
        click.echo(click.style("PROBLEM CONFIGURATION", fg="cyan", bold=True))
        click.echo(f"  Name: {config.problem.name}")
        click.echo(f"  Type: {config.problem.problem_type}")
        click.echo(f"  Output Location: {config.problem.output_location}")
        click.echo(f"  Work Location: {config.problem.work_location}")
        click.echo()
    
    if section in ["all", "design"]:
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
    
    if section in ["all", "optimizer"]:
        click.echo(click.style("OPTIMIZER CONFIGURATION", fg="cyan", bold=True))
        click.echo(f"  Name: {config.optimizer.name}")
        click.echo(f"  Type: {config.optimizer.type}")

        if config.optimizer.parameters:
            click.echo()
            click.echo("  Parameters:")
            for key, value in config.optimizer.parameters.items():
                click.echo(f"    - {key}: {value}")
        click.echo()
    
    click.echo(click.style("=" * 70, bold=True))


def inspect_problem_config(config):
    """
    Inspect problem-only configuration.
    
    Args:
        config: Loaded ProblemConfiguration object
    """
    click.echo(click.style("PROBLEM CONFIGURATION", fg="cyan", bold=True))
    click.echo(f"  Name: {config.name}")
    click.echo(f"  Type: {config.problem_type}")
    click.echo(f"  Objectives: {len(config.objectives)}")
    for obj in config.objectives:
        direction = getattr(obj, "direction", None)
        direction_str = direction.value if direction else "minimize" if getattr(obj, "minimize", True) else "maximize"
        click.echo(f"    - {obj.name}: {direction_str}")


def inspect_design_config(config):
    """
    Inspect design-only configuration.
    
    Args:
        config: Loaded DesignConfig object
    """
    click.echo(click.style("DESIGN CONFIGURATION", fg="cyan", bold=True))
    param_names = config.get_parameter_names()
    click.echo(f"  Parameters: {len(param_names)}")
    
    params_by_group = {}
    for name in param_names:
        group = name.split('.')[0]
        params_by_group.setdefault(group, []).append(name)
    
    for group, names in params_by_group.items():
        click.echo(f"\n  {group}: {len(names)} parameters")
