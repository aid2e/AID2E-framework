# Step 1: Unified Objectives & Workflow Config Models - COMPLETED ✅

## Summary
Implemented a **unified objective model hierarchy** that eliminates duplication across problem, optimization, and workflow layers.

### Files Created
1. **`src/aid2e/utilities/configurations/objectives.py`** (530 lines)
   - `ObjectiveDirection` enum (MINIMIZE, MAXIMIZE)
   - `ScriptObjective` (external script with output file pattern)
   - `InlineObjective` (inline function reference via entrypoint)
   - `ObjectiveComputationSpec` (union of script | inline)
   - `ObjectiveDefinition` (unified model with name, direction, computation, metrics_keys)
   - `ObjectivesRegistry` (runtime mapping for objectives)

2. **`src/aid2e/utilities/workflows/workflow_config.py`** (400 lines)
   - `ParallelismPolicy` (max_concurrent, retry_max, timeout_sec)
   - `ArtifactSpec` (output file patterns and format)
   - `JobDefinition` (name, command, payload, resources, outputs)
   - `JobFactory` (fan-out: expand one job to N parallel jobs)
   - `StageDefinition` (stage with jobs, scheduler, parallelism)
   - `BranchDefinition` (branch with stages in DAG order)
   - `WorkflowDefinition` (workflow with branches and objectives)
   - `WorkflowsConfiguration` (multiple workflows + global scheduler)

### Files Modified
1. **`src/aid2e/utilities/configurations/problem_config.py`**
   - Import `ObjectiveDirection` from objectives.py
   - Add `to_objective_direction()` method to `Objective`
   - Updated module docstring

2. **`src/aid2e/utilities/configurations/optimization_config.py`**
   - Updated docstring to reference unified `ObjectiveDefinition`

3. **`src/aid2e/utilities/configurations/__init__.py`**
   - Export all objective models (Direction, Definition, Spec, Script, Inline, Registry)

4. **`src/aid2e/utilities/workflows/__init__.py`**
   - Export all workflow config models (Workflow, Branch, Stage, Job, Factory, Policy, Artifact)

### Key Design Decisions

#### Single Source of Truth
- **Problem layer:** Uses simple `Objective(name, minimize)` for spec
- **Optimization layer:** Uses directive strings "minimize:f1" for flexibility
- **Workflow layer:** Uses full `ObjectiveDefinition` with computation spec
- **Mapping:** Conversion functions `to_directive()` and `from_directive()` connect layers
- **Benefit:** No duplication, consistent definitions across all layers

#### Objective Computation (No Blocker, Forward-Designed)
- `ObjectiveComputationSpec` supports:
  - **Script-based:** External script with output file pattern
  - **Inline:** Python function reference (module:function format)
- Parser/executor can plug in later without schema changes
- Deferred execution: computation resolved at workflow runtime

#### Workflow Structure
- **Branches:** Optional subgraphs for organizing independent pipelines
- **Stages:** Parallel execution units (fan-out jobs via JobFactory)
- **Jobs:** Smallest schedulable units with template payloads
- **JobFactory:** Expands one job template to N parallel instances
- **Scheduler:** Per-stage override + global default (inheritance)

#### Multi-Workflow Support (Option B)
- `WorkflowsConfiguration` contains list of independent `WorkflowDefinition`
- Each workflow can have own objectives, stages, and scheduler
- Supports use case: multiple objectives as independent workflows

---

## Verification Results

All 11 comprehensive tests passed:

```
✅ [Test 1] ObjectiveDirection Enum
✅ [Test 2] ScriptObjective
✅ [Test 3] InlineObjective
✅ [Test 4] ObjectiveComputationSpec (script-based)
✅ [Test 4b] ObjectiveComputationSpec (inline-based)
✅ [Test 5] ObjectiveDefinition from directive
✅ [Test 6] ObjectiveDefinition with computation
✅ [Test 7] ObjectivesRegistry
✅ [Test 8] Workflow Models (Job/Stage/Branch/Workflow)
✅ [Test 9] WorkflowDefinition
✅ [Test 10] WorkflowsConfiguration
✅ [Test 11] Unified Objective Model (DRY)
```

Test file: `test_step1_models.py` (validates all models)

---

## Post-Commit Checklist for PR

- [x] All new files have module docstrings (Google-style)
- [x] All classes have docstrings with Examples
- [x] All methods have docstrings with Args/Returns/Raises
- [x] No unused imports
- [x] Models validated with Pydantic (field validators, error messages)
- [x] DRY principle: no code duplication for objectives
- [x] Backward compatible: existing problem_config unchanged
- [x] Test coverage: 11 tests covering all models
- [x] No circular imports

---

## Commit Message (Ready to Use)

```
feat: Implement unified objective model and workflow config hierarchy

Step 1 of multi-workflow framework milestone.

- Create unified ObjectiveDefinition in objectives.py (single source of truth)
  - Supports both script-based and inline function computation
  - Provides to_directive() and from_directive() for format conversion
  - Includes ObjectivesRegistry for runtime mapping

- Implement complete workflow config models in workflow_config.py
  - WorkflowDefinition: end-to-end evaluation unit (one design point)
  - BranchDefinition: optional subgraph for independent pipelines
  - StageDefinition: parallel execution unit with fan-out via JobFactory
  - JobDefinition: smallest schedulable unit
  - JobFactory: expands one job template to N parallel instances
  - ParallelismPolicy: control max_concurrent, retry_max, timeout_sec
  - ArtifactSpec: output artifact specifications
  - WorkflowsConfiguration: multi-workflow container (Option B design)

- Refactor objective models across layers (DRY)
  - Problem layer: Objective(name, minimize) + to_objective_direction()
  - Optimization layer: objective directives "minimize:f1" + from_directive()
  - Workflow layer: ObjectiveDefinition with full computation spec
  - Single definition location (objectives.py) for all objectives

- Update exports in __init__.py files for clean API

- Add comprehensive test suite (11 tests) validating:
  - ObjectiveDirection enum, ScriptObjective, InlineObjective
  - ObjectiveComputationSpec (script and inline modes)
  - ObjectiveDefinition creation and directive conversion
  - ObjectivesRegistry registration and retrieval
  - WorkflowDefinition, BranchDefinition, StageDefinition hierarchy
  - WorkflowsConfiguration with multiple workflows
  - Unified objective model reuse across layers

Benefits:
- No duplicate objective definitions (DRY)
- Consistent objective spec across problem/optimization/workflow
- Forward-designed for future executor implementations
- Multi-workflow support for holistic optimization
- Clear separation of concerns (spec vs. execution)
```

---

## What's Next

**Step 2:** Create DAG types and topological validation
- `DagDefinition` with nodes and edges
- `topological_sort()` for execution order
- `detect_cycles()` for validation
- Integration tests with 2-step DAG

Ready to proceed? → `manage_todo_list` → Update Step 2
