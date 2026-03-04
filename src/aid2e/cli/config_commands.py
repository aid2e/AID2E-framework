"""
Configuration inspection commands for AID2E CLI.

Core commands for examining, describing, and validating configuration files:
- describe: Quick summary with auto-detection
- inspect: Detailed inspection with section filtering  
- validate: Syntax and structure validation
"""

import sys
from typing import Optional

import click
import yaml

from aid2e.utilities.configurations import FullConfig, load_config
from ._helpers import (
    detect_config_type,
    count_parameters,
    format_description_text,
    extract_description_data,
    inspect_full_config,
    inspect_problem_config,
    inspect_design_config,
)


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--format", type=click.Choice(["text", "json", "yaml"]), default="text", help="Output format")
@click.option("--compact", is_flag=True, help="Show compact summary")
def describe(config_file: str, format: str, compact: bool):
    """
    Describe the contents and structure of a configuration file.
    
    Automatically detects config type (design/problem/optimization/full)
    and displays relevant information in a human-readable format.
    
    Examples:
        aid2e describe config.yml
        aid2e describe design.params --compact
        aid2e describe config.yml --format json
    """
    try:
        # Load raw YAML to detect type
        with open(config_file) as f:
            data = yaml.safe_load(f)
        
        # Detect config type
        config_type = detect_config_type(data)
        
        if format == "text":
            format_description_text(data, config_type, compact, config_file)
        elif format == "json":
            import json
            description = extract_description_data(data, config_type)
            click.echo(json.dumps(description, indent=2))
        elif format == "yaml":
            description = extract_description_data(data, config_type)
            click.echo(yaml.dump(description, default_flow_style=False))
            
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)


@click.command(name="inspect")
@click.argument("config_file", type=click.Path(exists=True))
@click.option("--section", type=click.Choice(["problem", "optimization", "design", "all"]), default="all", help="Section to inspect")
def inspect(config_file: str, section: str):
    """
    Display detailed information about a configuration file.
    
    Provides comprehensive view of configuration with optional section filtering.
    
    Examples:
        aid2e inspect config.yml
        aid2e inspect config.yml --section optimization
        aid2e inspect config.yml --section design
    """
    try:
        # Load raw YAML first to determine type
        with open(config_file) as f:
            raw_data = yaml.safe_load(f)
        
        config_type = detect_config_type(raw_data)
        
        # For full configs, try to load properly
        if config_type == "full":
            config = load_config(config_file)
            inspect_full_config(config, section)
        elif config_type == "problem":
            from aid2e.utilities.configurations import ProblemConfigLoader
            config = ProblemConfigLoader.load(config_file)
            inspect_problem_config(config)
        elif config_type == "design":
            from aid2e.utilities.configurations import DesignConfigLoader
            config = DesignConfigLoader.load(config_file)
            inspect_design_config(config)
        else:
            # Fallback to raw display
            click.echo(click.style(f"Configuration Type: {config_type}", bold=True))
            click.echo(yaml.dump(raw_data, default_flow_style=False))
            
    except Exception as e:
        click.echo(click.style(f"✗ Error: {e}", fg="red"), err=True)
        sys.exit(1)


@click.command()
@click.argument("config_file", type=click.Path(exists=True))
def validate(config_file: str):
    """
    Validate a configuration file without loading full context.
    
    Checks syntax, required fields, and structural correctness.
    
    Examples:
        aid2e validate config.yml
        aid2e validate design.params
    """
    try:
        # Load raw YAML
        with open(config_file) as f:
            data = yaml.safe_load(f)
        
        config_type = detect_config_type(data)
        
        click.echo(f"Validating {config_type} configuration...")
        
        # Try to load with appropriate loader
        if config_type == "full":
            config = load_config(config_file)
        elif config_type == "problem":
            from aid2e.utilities.configurations import ProblemConfigLoader
            config = ProblemConfigLoader.load(config_file)
        elif config_type == "design":
            from aid2e.utilities.configurations import DesignConfigLoader
            config = DesignConfigLoader.load(config_file)
        elif config_type == "optimization":
            from aid2e.utilities.configurations import OptimizationConfiguration
            opt = data.get("optimization", data)
            config = OptimizationConfiguration(**opt)
        else:
            click.echo(click.style("⚠ Unknown configuration type, performing basic YAML validation only", fg="yellow"))
            click.echo(click.style("✓ YAML syntax is valid", fg="green"))
            return
        
        click.echo(click.style("✓ Configuration is valid!", fg="green", bold=True))
        click.echo(f"  Type: {config_type}")
        
        if config_type in ["full", "problem"]:
            param_count = len(config.problem.design_config.get_parameter_names() if config_type == "full" else config.design_config.get_parameter_names())
            click.echo(f"  Parameters: {param_count}")
        
    except Exception as e:
        click.echo(click.style(f"✗ Validation failed: {e}", fg="red", bold=True), err=True)
        sys.exit(1)
