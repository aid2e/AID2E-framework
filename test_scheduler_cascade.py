#!/usr/bin/env python3
"""
Test scheduler cascade resolution.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from aid2e.utilities.configurations import (
    resolve_scheduler_cascade,
    create_scheduler_context,
    SchedulerConfiguration,
)


def test_cascade_resolution():
    """Test that cascade resolution works correctly."""
    print("\n" + "=" * 70)
    print("SCHEDULER CASCADE RESOLUTION TESTS")
    print("=" * 70)
    
    # Test 1: Stage override takes precedence
    print("\nTest 1: Stage override precedence")
    stage = SchedulerConfiguration(runner_type="SlurmRunner", parameters={})
    branch = SchedulerConfiguration(runner_type="JobLibRunner", parameters={"n_jobs": 4})
    workflow = SchedulerConfiguration(runner_type="JobLibRunner", parameters={"n_jobs": 8})
    
    result = resolve_scheduler_cascade(stage, branch, workflow)
    assert result == stage, "Stage should override branch and workflow"
    print(f"  ✓ Stage (SlurmRunner) correctly overrides branch and workflow")
    
    # Test 2: Branch used if stage is None
    print("\nTest 2: Branch used when stage is None")
    result = resolve_scheduler_cascade(None, branch, workflow)
    assert result == branch, "Branch should be used if stage is None"
    print(f"  ✓ Branch (JobLibRunner n_jobs=4) used when stage is None")
    
    # Test 3: Workflow used if stage and branch are None
    print("\nTest 3: Workflow used when stage and branch are None")
    result = resolve_scheduler_cascade(None, None, workflow)
    assert result == workflow, "Workflow should be used if stage and branch are None"
    print(f"  ✓ Workflow (JobLibRunner n_jobs=8) used when stage and branch are None")
    
    # Test 4: All None returns None
    print("\nTest 4: All None returns None")
    result = resolve_scheduler_cascade(None, None, None, None, None)
    assert result is None, "Should return None if all are None"
    print(f"  ✓ Returns None when all schedulers are None")
    
    # Test 5: Context shows cascade information
    print("\nTest 5: Context shows cascade information")
    context = create_scheduler_context(
        stage_scheduler=stage,
        branch_scheduler=branch,
        workflow_scheduler=workflow,
    )
    
    assert context["effective_scheduler"] == "SlurmRunner"
    assert context["source"] == "stage"
    assert context["cascade_levels"]["stage"] == "SlurmRunner"
    assert context["cascade_levels"]["branch"] == "JobLibRunner"
    assert context["cascade_levels"]["workflow"] == "JobLibRunner"
    print(f"  ✓ Context correctly shows cascade: {context['cascade_levels']}")
    print(f"  ✓ Effective source: {context['source']}")


def test_cascade_with_objectives():
    """Test cascade with all levels including objective and global."""
    print("\n" + "=" * 70)
    print("FULL CASCADE TEST (5 LEVELS)")
    print("=" * 70)
    
    global_sched = SchedulerConfiguration(runner_type="JobLibRunner", parameters={"n_jobs": 1})
    objective_sched = SchedulerConfiguration(runner_type="JobLibRunner", parameters={"n_jobs": 2})
    workflow_sched = SchedulerConfiguration(runner_type="JobLibRunner", parameters={"n_jobs": 4})
    branch_sched = SchedulerConfiguration(runner_type="JobLibRunner", parameters={"n_jobs": 8})
    stage_sched = SchedulerConfiguration(runner_type="SlurmRunner", parameters={})
    
    # Test each level
    print("\nTest 1: All five levels defined (stage should win)")
    result = resolve_scheduler_cascade(stage_sched, branch_sched, workflow_sched, objective_sched, global_sched)
    assert result.runner_type == "SlurmRunner"
    print(f"  ✓ Stage (SlurmRunner) wins: {result.runner_type}")
    
    print("\nTest 2: No stage (branch should win)")
    result = resolve_scheduler_cascade(None, branch_sched, workflow_sched, objective_sched, global_sched)
    assert result.parameters.get("n_jobs") == 8
    print(f"  ✓ Branch wins with n_jobs=8")
    
    print("\nTest 3: No stage or branch (workflow should win)")
    result = resolve_scheduler_cascade(None, None, workflow_sched, objective_sched, global_sched)
    assert result.parameters.get("n_jobs") == 4
    print(f"  ✓ Workflow wins with n_jobs=4")
    
    print("\nTest 4: No stage, branch, or workflow (objective should win)")
    result = resolve_scheduler_cascade(None, None, None, objective_sched, global_sched)
    assert result.parameters.get("n_jobs") == 2
    print(f"  ✓ Objective wins with n_jobs=2")
    
    print("\nTest 5: Only global (global should win)")
    result = resolve_scheduler_cascade(None, None, None, None, global_sched)
    assert result.parameters.get("n_jobs") == 1
    print(f"  ✓ Global wins with n_jobs=1")
    
    # Test context with full cascade
    print("\nTest 6: Context shows full cascade")
    context = create_scheduler_context(
        objective_scheduler=objective_sched,
        workflow_scheduler=workflow_sched,
        branch_scheduler=branch_sched,
        stage_scheduler=stage_sched,
        global_scheduler=global_sched,
    )
    
    assert context["source"] == "stage"
    assert context["cascade_levels"]["stage"] == "SlurmRunner"
    assert context["cascade_levels"]["branch"] == "JobLibRunner"
    assert context["cascade_levels"]["workflow"] == "JobLibRunner"
    assert context["cascade_levels"]["objective"] == "JobLibRunner"
    assert context["cascade_levels"]["global"] == "JobLibRunner"
    print(f"  ✓ Full cascade visible in context:")
    for level, runner in context["cascade_levels"].items():
        print(f"      {level:10s}: {runner}")


def main():
    """Run all tests."""
    try:
        test_cascade_resolution()
        test_cascade_with_objectives()
        
        print("\n" + "=" * 70)
        print("ALL SCHEDULER CASCADE TESTS PASSED ✓")
        print("=" * 70)
        return 0
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
