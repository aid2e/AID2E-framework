"""Scheduler cascade resolution utilities.

This module provides functions to resolve the effective scheduler configuration
for a given stage/branch/workflow, following the cascade precedence:

    objective-level default → workflow-level default → branch-level default → stage-level override

The cascade allows users to set sensible defaults at higher levels and override
them at lower levels only when needed.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel

from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration


def resolve_scheduler_cascade(
    stage_scheduler: Optional[SchedulerConfiguration] = None,
    branch_scheduler: Optional[SchedulerConfiguration] = None,
    workflow_scheduler: Optional[SchedulerConfiguration] = None,
    objective_scheduler: Optional[SchedulerConfiguration] = None,
    global_scheduler: Optional[SchedulerConfiguration] = None,
) -> Optional[SchedulerConfiguration]:
    """
    Resolve the effective scheduler configuration using cascade precedence.
    
    Cascade order (highest to lowest priority):
    1. Stage-level scheduler (stage override)
    2. Branch-level scheduler (branch default)
    3. Workflow-level scheduler (workflow default)
    4. Objective-level scheduler (objective default)
    5. Global scheduler (global default)
    
    Args:
        stage_scheduler: Scheduler at stage level (highest priority)
        branch_scheduler: Scheduler at branch level
        workflow_scheduler: Scheduler at workflow level
        objective_scheduler: Scheduler at objective level
        global_scheduler: Global scheduler (lowest priority)
        
    Returns:
        The first non-None scheduler in the cascade, or None if all are None
        
    Example:
        >>> stage_sched = SchedulerConfiguration(runner_type="SlurmRunner", parameters={})
        >>> branch_sched = SchedulerConfiguration(runner_type="JobLibRunner", parameters={})
        >>> effective = resolve_scheduler_cascade(stage_sched, branch_sched)
        >>> assert effective == stage_sched  # Stage overrides branch
        
        >>> effective = resolve_scheduler_cascade(None, branch_sched)
        >>> assert effective == branch_sched  # Branch used if stage is None
    """
    # Check in order of precedence
    if stage_scheduler is not None:
        return stage_scheduler
    if branch_scheduler is not None:
        return branch_scheduler
    if workflow_scheduler is not None:
        return workflow_scheduler
    if objective_scheduler is not None:
        return objective_scheduler
    if global_scheduler is not None:
        return global_scheduler
    return None


def create_scheduler_context(
    objective_scheduler: Optional[SchedulerConfiguration] = None,
    workflow_scheduler: Optional[SchedulerConfiguration] = None,
    branch_scheduler: Optional[SchedulerConfiguration] = None,
    stage_scheduler: Optional[SchedulerConfiguration] = None,
    global_scheduler: Optional[SchedulerConfiguration] = None,
) -> Dict[str, Any]:
    """
    Create a context dictionary with scheduler information for logging/debugging.
    
    Args:
        objective_scheduler: Scheduler at objective level
        workflow_scheduler: Scheduler at workflow level
        branch_scheduler: Scheduler at branch level
        stage_scheduler: Scheduler at stage level
        global_scheduler: Global scheduler
        
    Returns:
        Dictionary with scheduler cascade information for each level
        
    Example:
        >>> context = create_scheduler_context(
        ...     workflow_scheduler=SchedulerConfiguration(...),
        ...     branch_scheduler=SchedulerConfiguration(...),
        ... )
        >>> print(context["effective_scheduler"])  # Will show the effective one
    """
    effective = resolve_scheduler_cascade(
        stage_scheduler, branch_scheduler, workflow_scheduler, objective_scheduler, global_scheduler
    )
    
    return {
        "cascade_levels": {
            "stage": stage_scheduler.runner_type if stage_scheduler else None,
            "branch": branch_scheduler.runner_type if branch_scheduler else None,
            "workflow": workflow_scheduler.runner_type if workflow_scheduler else None,
            "objective": objective_scheduler.runner_type if objective_scheduler else None,
            "global": global_scheduler.runner_type if global_scheduler else None,
        },
        "effective_scheduler": effective.runner_type if effective else None,
        "source": _get_cascade_source(stage_scheduler, branch_scheduler, workflow_scheduler, objective_scheduler, global_scheduler),
    }


def _get_cascade_source(
    stage_scheduler, branch_scheduler, workflow_scheduler, objective_scheduler, global_scheduler
) -> str:
    """Determine which level provided the effective scheduler."""
    if stage_scheduler is not None:
        return "stage"
    if branch_scheduler is not None:
        return "branch"
    if workflow_scheduler is not None:
        return "workflow"
    if objective_scheduler is not None:
        return "objective"
    if global_scheduler is not None:
        return "global"
    return "none"
