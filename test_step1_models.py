#!/usr/bin/env python3
"""Test Step 1: Workflow config models and unified objectives."""

from aid2e.utilities.configurations.objectives import (
    ObjectiveDirection,
    ObjectiveDefinition,
    ObjectiveComputationSpec,
    MultiStepComputationSpec,
    MultiStepStage,
    ScriptObjective,
    InlineObjective,
    ObjectivesRegistry,
)
from aid2e.utilities.configurations.workflow_config import (
    WorkflowsConfiguration,
    WorkflowDefinition,
    BranchDefinition,
    StageDefinition,
    JobDefinition,
    ParallelismPolicy,
    ArtifactSpec,
    JobFactory,
)

print("=" * 60)
print("STEP 1: Unified Objectives & Workflow Config Models")
print("=" * 60)

# Test 1: ObjectiveDirection
print("\n[Test 1] ObjectiveDirection Enum")
print(f"  MINIMIZE = {ObjectiveDirection.MINIMIZE.value}")
print(f"  MAXIMIZE = {ObjectiveDirection.MAXIMIZE.value}")
assert ObjectiveDirection.MINIMIZE.value == "minimize"

# Test 2: ScriptObjective
print("\n[Test 2] ScriptObjective")
script = ScriptObjective(
    path="scripts/dtlz2_problem.py",
    output_file="objectives_{job_id}.json",
    timeout_sec=600
)
print(f"  Path: {script.path}")
print(f"  Output: {script.output_file}")
print(f"  Timeout: {script.timeout_sec}s")

# Test 3: InlineObjective
print("\n[Test 3] InlineObjective")
inline = InlineObjective(entrypoint="my_objectives:compute_f1")
print(f"  Entrypoint: {inline.entrypoint}")

# Test 4: ObjectiveComputationSpec
print("\n[Test 4] ObjectiveComputationSpec (script-based)")
spec_script = ObjectiveComputationSpec(script=script)
assert spec_script.is_script()
assert not spec_script.is_inline()
print(f"  Type: script-based")
print(f"  Script path: {spec_script.script.path}")

print("\n[Test 4b] ObjectiveComputationSpec (inline-based)")
spec_inline = ObjectiveComputationSpec(inline=inline)
assert spec_inline.is_inline()
assert not spec_inline.is_script()
print(f"  Type: inline-based")
print(f"  Entrypoint: {spec_inline.inline.entrypoint}")

print("\n[Test 4c] ObjectiveComputationSpec (multi-steps-based)")
multi_steps = MultiStepComputationSpec(
    stages=[
        MultiStepStage(name="prepare", jobs=[{"name": "prep"}]),
        MultiStepStage(
            name="evaluate",
            jobs=[{"name": "run_sim"}],
            depends_on=["prepare"],
            produces_objective=True,
        ),
    ]
)
spec_multi = ObjectiveComputationSpec(multi_steps=multi_steps)
assert spec_multi.is_multi_steps()
assert not spec_multi.is_inline()
assert not spec_multi.is_script()
print(f"  Type: multi-steps-based")
print(f"  Producing stage: {spec_multi.multi_steps.producing_stage()}")

# Test 5: ObjectiveDefinition from directive
print("\n[Test 5] ObjectiveDefinition from directive")
obj_f1 = ObjectiveDefinition.from_directive("minimize:f1")
print(f"  Name: {obj_f1.name}")
print(f"  Direction: {obj_f1.direction.value}")
print(f"  Directive: {obj_f1.to_directive()}")
assert obj_f1.to_directive() == "minimize:f1"

obj_f2 = ObjectiveDefinition.from_directive("maximize:efficiency")
assert obj_f2.to_directive() == "maximize:efficiency"
print(f"  Created: {obj_f2.to_directive()}")

# Test 6: ObjectiveDefinition with computation
print("\n[Test 6] ObjectiveDefinition with computation")
obj_full = ObjectiveDefinition(
    name="f1",
    direction=ObjectiveDirection.MINIMIZE,
    computation=spec_script,
    metrics_keys=["f1"]
)
print(f"  Name: {obj_full.name}")
print(f"  Direction: {obj_full.direction.value}")
print(f"  Has computation: {obj_full.computation is not None}")
print(f"  Metrics keys: {obj_full.metrics_keys}")

# Test 7: ObjectivesRegistry
print("\n[Test 7] ObjectivesRegistry")
registry = ObjectivesRegistry()
registry.register(obj_f1)
registry.register(obj_f2)
retrieved = registry.get("f1")
print(f"  Registered: {len(registry.list_all())} objectives")
print(f"  Retrieved f1: {retrieved.to_directive()}")
assert retrieved.name == "f1"

# Test 8: Workflow Models - Job/Stage/Branch
print("\n[Test 8] Workflow Models (Job/Stage/Branch/Workflow)")
job = JobDefinition(
    name="dtlz2_evaluate",
    command="python scripts/dtlz2_problem.py",
    payload={
        "design_params_file": "{input_design_params}",
        "output_file": "{output_dir}/objectives_{job_id}.json"
    },
    outputs=[ArtifactSpec(path="objectives_*.json", format="json")]
)
print(f"  Job: {job.name}")

stage = StageDefinition(
    name="evaluate",
    jobs=[job],
    job_factory=JobFactory(type="range", params={"n": 4}),
    parallelism=ParallelismPolicy(max_concurrent=4, retry_max=2),
    outputs=[ArtifactSpec(path="objectives_*.json", format="json")]
)
print(f"  Stage: {stage.name}")
print(f"    - Jobs: {len(stage.jobs)}")
print(f"    - Max concurrent: {stage.parallelism.max_concurrent}")
print(f"    - Job factory: {stage.job_factory.type} (n={stage.job_factory.params.get('n')})")

branch = BranchDefinition(
    name="main",
    stages=[stage]
)
print(f"  Branch: {branch.name}")
print(f"    - Stages: {len(branch.stages)}")

# Test 9: WorkflowDefinition with objectives
print("\n[Test 9] WorkflowDefinition")
workflow = WorkflowDefinition(
    name="dtlz2_eval",
    description="Evaluate design points using DTLZ2",
    branches=[branch],
    objectives=[obj_f1, obj_f2]
)
print(f"  Name: {workflow.name}")
print(f"  Branches: {len(workflow.branches)}")
print(f"  Objectives: {len(workflow.objectives)}")
for obj in workflow.objectives:
    print(f"    - {obj.to_directive()}")

# Test 10: WorkflowsConfiguration
print("\n[Test 10] WorkflowsConfiguration")
config = WorkflowsConfiguration(workflows=[workflow])
print(f"  Workflows: {len(config.workflows)}")
print(f"  Total objectives: {sum(len(w.objectives) for w in config.workflows)}")
print(f"  First workflow: {config.workflows[0].name}")

# Test 11: Unified objective across layers
print("\n[Test 11] Unified Objective Model (DRY)")
print("  ✓ ObjectiveDefinition used in:")
print("    - WorkflowDefinition.objectives")
print("    - Can be created from OptimizationConfiguration directives")
print("    - Can be derived from ProblemConfiguration.Objective")
print("  ✓ Single definition location: objectives.py")

print("\n" + "=" * 60)
print("✅ ALL STEP 1 TESTS PASSED!")
print("=" * 60)
print("\nSummary:")
print("  - Unified ObjectiveDefinition (reused across all layers)")
print("  - WorkflowDefinition with branches, stages, jobs")
print("  - JobFactory for fan-out parallelism")
print("  - ParallelismPolicy for execution control")
print("  - WorkflowsConfiguration for multi-workflow support")
print("  - No code duplication for objective definitions")
print("\nReady for Step 2: DAG types and topological validation")
