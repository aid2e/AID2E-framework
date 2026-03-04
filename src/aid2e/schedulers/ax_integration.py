"""
Ax Integration - Helper functions to integrate AID2E with Ax Platform and runners.

This module provides utilities to:
1. Create Ax clients from AID2E configurations
2. Get appropriate runners based on configuration
3. Bridge AID2E config system with scheduler_epic's AxScheduler
"""

import logging
from typing import Dict, Any, Optional
from ax.service.ax_client import AxClient
from .joblib_runner import JobLibRunner


logger = logging.getLogger(__name__)


def create_ax_client_from_config(
    problem_config,
    design_config,
    minimize: bool = True,
    random_seed: Optional[int] = None
) -> AxClient:
    """
    Create an AxClient from AID2E configuration objects.

    Args:
        problem_config: AID2E ProblemConfiguration object
        design_config: AID2E DesignConfiguration object
        minimize: Whether to minimize objectives (default: True)
        random_seed: Random seed for reproducibility

    Returns:
        Configured AxClient instance

    Example:
        >>> from aid2e.configuration import ProblemConfiguration, DesignConfiguration
        >>> problem_config = ProblemConfiguration.from_yaml("problem.yaml")
        >>> design_config = DesignConfiguration.from_yaml("design.yaml")
        >>> ax_client = create_ax_client_from_config(problem_config, design_config)
    """
    ax_client = AxClient(random_seed=random_seed)

    # Build parameters list for Ax
    parameters = []
    for param in design_config.parameters:
        param_dict = {
            "name": param.name,
            "type": "range",  # AID2E typically uses continuous parameters
            "bounds": [param.lower_bound, param.upper_bound],
            "value_type": "float",
        }
        
        # Add log scale if specified
        if hasattr(param, 'log_scale') and param.log_scale:
            param_dict["log_scale"] = True
            
        parameters.append(param_dict)

    # Build objectives list for Ax
    objectives = {}
    for obj in problem_config.objectives:
        # Ax uses "minimize" as the default, so we flip if needed
        objectives[obj.name] = "minimize" if minimize else "maximize"

    # Create the experiment
    ax_client.create_experiment(
        name=problem_config.name if hasattr(problem_config, 'name') else "optimization",
        parameters=parameters,
        objectives=objectives,
        overwrite_existing_experiment=True,
    )

    logger.info(f"Created Ax client with {len(parameters)} parameters and {len(objectives)} objectives")
    return ax_client


def get_runner_from_config(scheduler_config: Dict[str, Any]) -> Any:
    """
    Create and return the appropriate runner based on configuration.

    Args:
        scheduler_config: Scheduler configuration dictionary with keys:
            - runner_type: 'joblib', 'slurm', or 'pandaidds'
            - runner_config: Additional configuration for the runner

    Returns:
        Runner instance (JobLibRunner, SlurmRunner, or PanDAiDDSRunner)

    Raises:
        ValueError: If runner_type is not supported

    Example:
        >>> config = {
        ...     "runner_type": "joblib",
        ...     "runner_config": {
        ...         "n_jobs": 4,
        ...         "backend": "loky"
        ...     }
        ... }
        >>> runner = get_runner_from_config(config)
    """
    runner_type = scheduler_config.get("runner_type", "joblib").lower()
    runner_config = scheduler_config.get("runner_config", {})

    if runner_type == "joblib":
        n_jobs = runner_config.get("n_jobs", -1)
        backend = runner_config.get("backend", "loky")
        return JobLibRunner(n_jobs=n_jobs, backend=backend, config=runner_config)
    
    elif runner_type == "slurm":
        # TODO: Implement in Phase 2
        raise NotImplementedError("SlurmRunner will be available in Phase 2")
    
    elif runner_type == "pandaidds":
        # TODO: Implement in Phase 2
        raise NotImplementedError("PanDAiDDSRunner will be available in Phase 2")
    
    else:
        raise ValueError(f"Unsupported runner type: {runner_type}. Supported types: joblib, slurm, pandaidds")


def create_scheduler_from_config(
    problem_config,
    design_config,
    scheduler_config: Dict[str, Any],
    objective_function,
    minimize: bool = True,
    random_seed: Optional[int] = None
):
    """
    Create a complete scheduler setup from AID2E configurations.
    
    This is a convenience function that combines Ax client creation and runner setup
    with scheduler_epic's AxScheduler.

    Args:
        problem_config: AID2E ProblemConfiguration object
        design_config: AID2E DesignConfiguration object
        scheduler_config: Scheduler configuration dictionary
        objective_function: Function to evaluate objectives
        minimize: Whether to minimize objectives
        random_seed: Random seed for reproducibility

    Returns:
        Tuple of (ax_client, runner, scheduler)

    Example:
        >>> def my_objective(x1, x2):
        ...     return {"objective": x1**2 + x2**2}
        >>> 
        >>> scheduler_config = {
        ...     "runner_type": "joblib",
        ...     "runner_config": {"n_jobs": 4}
        ... }
        >>> 
        >>> ax_client, runner, scheduler = create_scheduler_from_config(
        ...     problem_config, design_config, scheduler_config, my_objective
        ... )
    """
    # Import here to avoid circular dependencies
    try:
        from scheduler_epic import AxScheduler
    except ImportError:
        raise ImportError(
            "scheduler_epic is required for AxScheduler. "
            "Install it or use create_ax_client_from_config and get_runner_from_config separately."
        )

    # Create Ax client
    ax_client = create_ax_client_from_config(
        problem_config, design_config, minimize=minimize, random_seed=random_seed
    )

    # Create runner
    runner = get_runner_from_config(scheduler_config)

    # Create scheduler
    scheduler = AxScheduler(
        ax_client=ax_client,
        runner=runner,
        objective_function=objective_function,
    )

    logger.info(f"Created scheduler with {scheduler_config['runner_type']} runner")
    return ax_client, runner, scheduler


# Utility function to convert AID2E results to Ax format
def convert_results_to_ax_format(results: Dict[str, Any]) -> Dict[str, tuple]:
    """
    Convert results from AID2E format to Ax format.

    Ax expects results as {"objective_name": (mean, std_err)}

    Args:
        results: Dictionary with objective values

    Returns:
        Dictionary in Ax format with (mean, 0.0) tuples

    Example:
        >>> results = {"f1": 0.5, "f2": 0.3}
        >>> ax_results = convert_results_to_ax_format(results)
        >>> # Returns: {"f1": (0.5, 0.0), "f2": (0.3, 0.0)}
    """
    ax_results = {}
    for key, value in results.items():
        if isinstance(value, (int, float)):
            ax_results[key] = (float(value), 0.0)  # (mean, std_err)
    return ax_results
