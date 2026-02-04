#!/usr/bin/env python3
"""
Validation script for workflow models and combined objectives.
Tests:
1. Import and instantiation of objective_plan models
2. Auto-wrap pre-validator for single script/inline
3. Scheduler cascade fields
4. Combined objective models
5. Example YAML loading
"""

import sys
from pathlib import Path
import yaml
from pydantic import ValidationError

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from aid2e.utilities.configurations import (
    ObjectiveDirection,
    ScriptObjective,
    InlineObjective,
    MultiStepStage,
    MultiStepPlanSpec,
    ObjectivePlanSpec,
    ObjectiveDefinition,
    CombinedObjectivePlan,
    CombinedObjectiveMetric,
)
from aid2e.utilities.workflows import (
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    WorkflowsConfiguration,
)
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration


def test_imports():
    """Test that all new models can be imported."""
    print("✓ All imports successful")


def test_objective_plan_spec_single_script():
    """Test ObjectivePlanSpec auto-wrap of single script into one-step plan."""
    print("\nTesting ObjectivePlanSpec single script auto-wrap...")
    
    # Single script (should be auto-wrapped into one-step plan)
    spec = ObjectivePlanSpec(
        script=ScriptObjective(
            path="scripts/dtlz2.py",
            output_file="output.json"
        )
    )
    
    assert spec.multi_steps is not None, "auto-wrap failed: multi_steps is None"
    assert len(spec.multi_steps.stages) == 1, f"Expected 1 stage, got {len(spec.multi_steps.stages)}"
    assert spec.multi_steps.stages[0].script is not None, "Stage should have script"
    print(f"  ✓ Auto-wrapped single script into {len(spec.multi_steps.stages)}-step plan")


def test_objective_plan_spec_single_inline():
    """Test ObjectivePlanSpec auto-wrap of single inline into one-step plan."""
    print("\nTesting ObjectivePlanSpec single inline auto-wrap...")
    
    # Single inline (should be auto-wrapped into one-step plan)
    spec = ObjectivePlanSpec(
        inline=InlineObjective(
            entrypoint="my_module:compute_objective"
        )
    )
    
    assert spec.multi_steps is not None, "auto-wrap failed: multi_steps is None"
    assert len(spec.multi_steps.stages) == 1, f"Expected 1 stage, got {len(spec.multi_steps.stages)}"
    assert spec.multi_steps.stages[0].inline is not None, "Stage should have inline"
    print(f"  ✓ Auto-wrapped single inline into {len(spec.multi_steps.stages)}-step plan")


def test_objective_plan_spec_multi_steps():
    """Test ObjectivePlanSpec with explicit multi_steps."""
    print("\nTesting ObjectivePlanSpec with multi_steps...")
    
    # Multi-step plan
    spec = ObjectivePlanSpec(
        multi_steps=MultiStepPlanSpec(
            stages=[
                MultiStepStage(
                    name="preprocess",
                    script=ScriptObjective(path="prep.py", output_file="prep.json"),
                    produces_objective=False
                ),
                MultiStepStage(
                    name="evaluate",
                    script=ScriptObjective(path="eval.py", output_file="eval.json"),
                    produces_objective=True
                ),
            ],
            produces_from_stage="evaluate"
        )
    )
    
    assert spec.multi_steps is not None
    assert len(spec.multi_steps.stages) == 2
    assert spec.multi_steps.stages[0].name == "preprocess"
    assert spec.multi_steps.stages[1].name == "evaluate"
    print(f"  ✓ Multi-step plan with {len(spec.multi_steps.stages)} stages created successfully")


def test_objective_definition_with_scheduler():
    """Test ObjectiveDefinition with scheduler field."""
    print("\nTesting ObjectiveDefinition with scheduler field...")
    
    obj_def = ObjectiveDefinition(
        name="f1",
        direction=ObjectiveDirection.MINIMIZE,
        objective_plan=ObjectivePlanSpec(
            script=ScriptObjective(path="scripts/dtlz2.py", output_file="f1.json")
        ),
        scheduler=SchedulerConfiguration(
            runner_type="JobLibRunner",
            parameters={"n_jobs": 4, "backend": "loky"}
        )
    )
    
    assert obj_def.scheduler is not None
    assert obj_def.scheduler.runner_type == "JobLibRunner"
    print(f"  ✓ ObjectiveDefinition with scheduler: {obj_def.scheduler.runner_type}")


def test_combined_objective():
    """Test CombinedObjectivePlan and CombinedObjectiveMetric."""
    print("\nTesting CombinedObjectivePlan...")
    
    combined = CombinedObjectivePlan(
        name="dtlz2_combined",
        objective_plan=ObjectivePlanSpec(
            script=ScriptObjective(path="scripts/dtlz2.py", output_file="objectives.json")
        ),
        metrics=[
            CombinedObjectiveMetric(
                name="f1",
                direction=ObjectiveDirection.MINIMIZE,
                metric_key="f1"
            ),
            CombinedObjectiveMetric(
                name="f2",
                direction=ObjectiveDirection.MINIMIZE,
                metric_key="f2"
            ),
        ]
    )
    
    assert combined.name == "dtlz2_combined"
    assert len(combined.metrics) == 2
    assert combined.metrics[0].metric_key == "f1"
    print(f"  ✓ CombinedObjectivePlan with {len(combined.metrics)} metrics created")


def test_workflow_definition_scheduler_cascade():
    """Test WorkflowDefinition with scheduler cascade fields."""
    print("\nTesting WorkflowDefinition scheduler cascade...")
    
    workflow = WorkflowDefinition(
        name="test_workflow",
        branches=[
            BranchDefinition(
                name="main",
                stages=[
                    StageDefinition(
                        name="stage1",
                        jobs=[],
                        scheduler=SchedulerConfiguration(
                            runner_type="SlurmRunner",
                            parameters={"partition": "gpu", "nodes": 1}
                        )
                    )
                ],
                scheduler=SchedulerConfiguration(
                    runner_type="JobLibRunner",
                    parameters={"n_jobs": 4, "backend": "loky"}
                )
            )
        ],
        scheduler=SchedulerConfiguration(
            runner_type="JobLibRunner",
            parameters={"n_jobs": 8, "backend": "loky"}
        )
    )
    
    assert workflow.scheduler is not None
    assert workflow.branches[0].scheduler is not None
    assert workflow.branches[0].stages[0].scheduler is not None
    print(f"  ✓ Workflow scheduler cascade: workflow → branch → stage configured")


def test_workflows_configuration_combined_objectives():
    """Test WorkflowsConfiguration with combined_objectives field."""
    print("\nTesting WorkflowsConfiguration with combined_objectives...")
    
    config = WorkflowsConfiguration(
        workflows=[
            WorkflowDefinition(
                name="combined_eval",
                branches=[
                    BranchDefinition(
                        name="main",
                        stages=[StageDefinition(name="evaluate", jobs=[])]
                    )
                ],
                objectives=[],
                combined_objectives=[
                    CombinedObjectivePlan(
                        name="dtlz2",
                        objective_plan=ObjectivePlanSpec(
                            script=ScriptObjective(path="dtlz2.py", output_file="obj.json")
                        ),
                        metrics=[
                            CombinedObjectiveMetric(
                                name="f1",
                                direction=ObjectiveDirection.MINIMIZE,
                                metric_key="f1"
                            )
                        ]
                    )
                ]
            )
        ]
    )
    
    assert len(config.workflows) == 1
    assert len(config.workflows[0].combined_objectives) == 1
    assert config.workflows[0].combined_objectives[0].name == "dtlz2"
    print(f"  ✓ WorkflowsConfiguration with combined_objectives loaded successfully")


def test_example_yaml_loading():
    """Test loading example YAML files."""
    print("\nTesting example YAML loading...")
    
    examples_dir = Path(__file__).parent / "examples" / "complete"
    
    # Test single objective example
    single_obj_yaml = examples_dir / "workflow_example_single_objective.yml"
    if single_obj_yaml.exists():
        with open(single_obj_yaml) as f:
            data = yaml.safe_load(f)
        assert "workflows" in data
        print(f"  ✓ Loaded {single_obj_yaml.name}")
    
    # Test combined objective example
    combined_obj_yaml = examples_dir / "workflow_example_combined_objectives.yml"
    if combined_obj_yaml.exists():
        with open(combined_obj_yaml) as f:
            data = yaml.safe_load(f)
        assert "workflows" in data
        workflows_data = data.get("workflows", [])
        if workflows_data:
            combined = workflows_data[0].get("combined_objectives", [])
            assert len(combined) > 0, "combined_objectives not found in YAML"
            assert "metrics" in combined[0], "metrics not found in combined objective"
        print(f"  ✓ Loaded {combined_obj_yaml.name}")


def test_backward_compatibility():
    """Test backward compatibility aliases."""
    print("\nTesting backward compatibility aliases...")
    
    try:
        from aid2e.utilities.configurations import (
            ObjectiveComputationSpec,
            MultiStepComputationSpec,
        )
        print(f"  ✓ Backward compat aliases available: ObjectiveComputationSpec, MultiStepComputationSpec")
    except ImportError as e:
        print(f"  ✗ Backward compat aliases not available: {e}")


def main():
    """Run all validation tests."""
    print("=" * 70)
    print("WORKFLOW MODEL VALIDATION TESTS")
    print("=" * 70)
    
    try:
        test_imports()
        test_objective_plan_spec_single_script()
        test_objective_plan_spec_single_inline()
        test_objective_plan_spec_multi_steps()
        test_objective_definition_with_scheduler()
        test_combined_objective()
        test_workflow_definition_scheduler_cascade()
        test_workflows_configuration_combined_objectives()
        test_example_yaml_loading()
        test_backward_compatibility()
        
        print("\n" + "=" * 70)
        print("ALL VALIDATION TESTS PASSED ✓")
        print("=" * 70)
        return 0
        
    except (ValidationError, AssertionError, Exception) as e:
        print(f"\n✗ VALIDATION FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
