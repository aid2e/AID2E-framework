# AID2E Multi-Workflow Framework Milestone Checklist

**Objective:** Deliver a functional multi-workflow framework with JobLib executor, 2-step DAG, and DTLZ2 objective computation.

**Target:** End-to-end execution: load YAML → compute objectives via dtlz2_problem script → collect results.

**Status:** Not Started

---

## Phase 1: Configuration Models & Schema

### Step 1: Create Workflow Config Models
**File:** `src/aid2e/utilities/workflows/workflow_config.py` (~600 lines)

**Tasks:**
- [ ] Create Pydantic models:
  - [ ] `ObjectiveComputationSpec` (script: ScriptObjective | inline: InlineObjective)
  - [ ] `ScriptObjective` (path, output_file)
  - [ ] `InlineObjective` (entrypoint: "module:function")
  - [ ] `ObjectiveSpec` (name, computation: ObjectiveComputationSpec, metrics_keys: List[str])
  - [ ] `ArtifactSpec` (path, format: "json|yaml|csv")
  - [ ] `ParallelismPolicy` (max_concurrent: int, retry_max: int, timeout_sec: int)
  - [ ] `JobDefinition` (name, command, payload, resources, outputs: ArtifactSpec)
  - [ ] `StageDefinition` (name, jobs: List[JobDefinition], scheduler: Optional[SchedulerConfiguration], parallelism: ParallelismPolicy)
  - [ ] `BranchDefinition` (name, dag: DagDefinition)
  - [ ] `WorkflowDefinition` (name, description, branches: List[BranchDefinition], objectives: List[ObjectiveSpec])
  - [ ] `WorkflowsConfiguration` (workflows: List[WorkflowDefinition], global_scheduler: Optional[SchedulerConfiguration])

**Verification Checklist:**
- [ ] All Pydantic models pass validation
- [ ] ObjectiveSpec supports both script and inline computation
- [ ] SchedulerConfiguration is reused/imported correctly
- [ ] No circular imports
- [ ] Docstrings follow Google-style format (per .github/instructions)

**Commit Message:**
```
feat: Add workflow configuration models (WorkflowDefinition, Stage, Job, ObjectiveSpec)

- Implement WorkflowsConfiguration with multiple independent workflows
- Add ObjectiveSpec supporting script or inline computation
- Define StageDefinition with per-stage scheduler override capability
- Add ParallelismPolicy for job concurrency and retry control
- Reuse SchedulerConfiguration for stage-level scheduler specs
```

---

### Step 2: Create DAG Types and Validation
**File:** `src/aid2e/utilities/workflows/dag_types.py` (~150 lines)

**Tasks:**
- [ ] Create DAG structures:
  - [ ] `DagNode` (Union[StageDefinition, JobDefinition])
  - [ ] `DagEdge` (src_id: str, dst_id: str)
  - [ ] `DagDefinition` (nodes: List[DagNode], edges: List[DagEdge])
- [ ] Implement validation helpers:
  - [ ] `topological_sort(dag: DagDefinition) -> List[DagNode]`
  - [ ] `detect_cycles(dag: DagDefinition) -> bool`
  - [ ] `validate_dag(dag: DagDefinition) -> List[str]` (returns errors)

**Verification Checklist:**
- [ ] Topological sort produces correct order for 2-step DAG
- [ ] Cycle detection catches invalid graphs
- [ ] All validation errors are descriptive
- [ ] No circular imports with workflow_config

**Commit Message:**
```
feat: Add DAG structures and topological validation

- Implement DagDefinition with nodes (stages/jobs) and edges
- Add topological_sort for correct execution order
- Add cycle_detection to prevent invalid workflows
- Add comprehensive validation with error reporting
```

---

### Step 3: Create DTLZ2 Problem Script
**File:** `scripts/dtlz2_problem.py` (~100 lines)

**Tasks:**
- [ ] Script takes command-line arguments:
  - [ ] `--design_params_file`: JSON file with design parameters
  - [ ] `--output_file`: JSON file to write objectives
- [ ] Load design parameters from JSON
- [ ] Implement DTLZ2 function:
  - [ ] f1 = compute_f1(x)
  - [ ] f2 = compute_f2(x)
- [ ] Write output JSON: `{"f1": float, "f2": float}`
- [ ] Error handling for missing files, invalid JSON

**Verification Checklist:**
- [ ] Script runs standalone: `python scripts/dtlz2_problem.py --design_params_file params.json --output_file out.json`
- [ ] Output JSON has correct format: `{"f1": <number>, "f2": <number>}`
- [ ] Design params correctly mapped to DTLZ2 inputs
- [ ] Error messages are clear (missing files, invalid JSON)

**Commit Message:**
```
feat: Add dtlz2_problem script for objective computation

- Implement DTLZ2 objective function (f1, f2)
- Accept design_params_file (JSON) and output_file arguments
- Output objectives as JSON: {"f1": float, "f2": float}
- Add comprehensive error handling and logging
```

---

## Phase 2: Integration with FullConfig & Parsing

### Step 4: Extend FullConfig
**File:** `src/aid2e/utilities/configurations/full_config.py`

**Tasks:**
- [ ] Add `workflows: Optional[WorkflowsConfiguration] = None` to `FullConfig` class
- [ ] Keep existing `problem`, `optimization`, `scheduler` logic intact
- [ ] Update docstring to document new workflows field

**Verification Checklist:**
- [ ] FullConfig still accepts problem + optimization + scheduler (backward compatible)
- [ ] FullConfig accepts workflows optional field
- [ ] No breaking changes to existing attributes
- [ ] Docstring updated

**Commit Message:**
```
feat: Extend FullConfig to support workflows section

- Add optional workflows: WorkflowsConfiguration field to FullConfig
- Maintain backward compatibility with existing problem/optimization/scheduler
- Update FullConfig docstring
```

---

### Step 5: Implement YAML Normalization
**File:** `src/aid2e/utilities/configurations/full_config.py` (extend `_normalize_full_config_data`)

**Tasks:**
- [ ] Parse `workflows:` block from YAML to `WorkflowsConfiguration`
- [ ] For each stage scheduler: inherit global `scheduler` if not overridden
- [ ] Resolve objective script paths relative to config directory
- [ ] Validate objective specs:
  - [ ] For script: file exists, output_file pattern valid
  - [ ] For inline: entrypoint format "module:function" is valid
- [ ] Return normalized dict with `workflows` key

**Verification Checklist:**
- [ ] Loads YAML with workflows section
- [ ] Stage scheduler inherits global scheduler if not specified
- [ ] Objective script paths resolved correctly (relative to config dir)
- [ ] Validation catches missing script files
- [ ] Validation catches invalid entrypoint format
- [ ] Existing problem/optimization parsing still works

**Commit Message:**
```
feat: Implement workflow YAML parsing and normalization

- Parse workflows section from YAML to WorkflowsConfiguration
- Inherit global scheduler to stages (per-stage override supported)
- Resolve objective script paths relative to config directory
- Validate objective specs (script existence, inline entrypoint format)
- Maintain backward compatibility with problem/optimization parsing
```

---

### Step 6: Implement Objective Spec Validation
**File:** `src/aid2e/utilities/workflows/workflow_config.py` (extend `ObjectiveSpec`)

**Tasks:**
- [ ] Add `@validator` for `ObjectiveSpec`:
  - [ ] For script: resolve file path, validate output_file pattern
  - [ ] For inline: validate entrypoint "module:function" format
- [ ] Add method `get_objective_computation() -> Callable | ScriptPath`

**Verification Checklist:**
- [ ] Script objectives: file existence check (deferred to runtime OK if relative path)
- [ ] Inline objectives: entrypoint format validated
- [ ] Error messages guide user to fix issues
- [ ] get_objective_computation() callable/path accessible

**Commit Message:**
```
feat: Add objective spec validation and computation resolution

- Validate ScriptObjective path and output_file format
- Validate InlineObjective entrypoint "module:function" format
- Add helper method to resolve objective computation
- Provide clear error messages for invalid specs
```

---

## Phase 3: Example & Execution Setup

### Step 7: Create Example YAML (2-step DAG + JobLib)
**File:** `examples/basic/workflow_dtlz2_joblib.yml` (~80 lines)

**Structure:**
```yaml
# Two-step workflow:
# Stage 1: Generate N design points (fan-out)
# Stage 2: Aggregate objectives

problem:
  name: "DTLZ2 Multi-Objective with Workflow"
  # ... existing problem config

optimizer:
  # ... existing optimizer config

scheduler:
  runner_type: "JobLibRunner"
  joblib:
    n_jobs: -1
    backend: "loky"

workflows:
  - name: "dtlz2_eval"
    description: "Evaluate design points using DTLZ2"
    branches:
      - name: "main"
        dag:
          stages:
            - name: "evaluate"
              jobs:
                - name: "dtlz2_evaluate"
                  command: "python scripts/dtlz2_problem.py"
                  payload:
                    design_params_file: "{input_design_params}"
                    output_file: "{output_dir}/objectives_{job_id}.json"
              job_factory:
                type: "range"
                params:
                  n: 4  # 4 parallel design points
              parallelism:
                max_concurrent: 4
                retry_max: 2
                timeout_sec: 300
              outputs:
                - path: "objectives_*.json"
                  format: "json"
            - name: "aggregate"
              jobs:
                - name: "aggregate_results"
                  command: "python scripts/aggregate_objectives.py"
                  payload:
                    results_dir: "{stage_outputs[evaluate]}"
                    output_file: "{output_dir}/aggregated.json"
              outputs:
                - path: "aggregated.json"
                  format: "json"
    objectives:
      - name: "f1"
        computation:
          script:
            path: "scripts/dtlz2_problem.py"
            output_file: "objectives_*.json"
        metrics_keys: ["f1"]
      - name: "f2"
        computation:
          script:
            path: "scripts/dtlz2_problem.py"
            output_file: "objectives_*.json"
        metrics_keys: ["f2"]
```

**Tasks:**
- [ ] Define 2-step DAG: Stage 1 (evaluate) → Stage 2 (aggregate)
- [ ] Stage 1 with job_factory for N parallel design points
- [ ] Global JobLib scheduler (JobLib only for MVP)
- [ ] Objective specs with script computation
- [ ] Comments explaining each section

**Verification Checklist:**
- [ ] YAML is valid
- [ ] DAG structure is acyclic (Stage 1 → Stage 2)
- [ ] job_factory creates N parallel jobs
- [ ] Objective script paths are correct
- [ ] output_file patterns are consistent
- [ ] All required directories exist or will be created

**Commit Message:**
```
feat: Add workflow example YAML with 2-step DAG (JobLib)

- Define dtlz2_eval workflow with evaluate and aggregate stages
- Implement job_factory for N parallel design point evaluations
- Configure JobLibRunner scheduler for MVP
- Add objective specs with script computation
- Include comprehensive inline documentation
```

---

### Step 8: Implement JobLib Executor
**File:** `src/aid2e/utilities/workflows/joblib_executor.py` (~250 lines)

**Tasks:**
- [ ] Create `JobLibExecutor` class:
  - [ ] `execute_stage(stage: StageDefinition, context: ExecutionContext) -> StageOutput`
  - [ ] Expand job_factory to create N jobs (if factory specified)
  - [ ] Use joblib.Parallel to execute jobs in parallel
  - [ ] Collect outputs, validate against ArtifactSpec
  - [ ] Return stage outputs for downstream stages
- [ ] Handle job inputs/outputs:
  - [ ] Template substitution (e.g., `{input_design_params}`, `{job_id}`)
  - [ ] Pass outputs from Stage N to Stage N+1
- [ ] Error handling:
  - [ ] Retry failed jobs up to retry_max
  - [ ] Timeout enforcement
  - [ ] Clear error messages

**Verification Checklist:**
- [ ] Jobs execute in parallel (check with 4 concurrent jobs)
- [ ] Outputs collected correctly
- [ ] Template substitution works: `{job_id}`, `{output_dir}`, `{stage_outputs[stage_name]}`
- [ ] Artifact validation catches missing/incorrect output files
- [ ] Retry logic works (simulate failure, verify retry)
- [ ] Timeout handling works
- [ ] No circular imports

**Commit Message:**
```
feat: Implement JobLib executor for parallel stage execution

- Create JobLibExecutor.execute_stage() for parallel job execution
- Implement job_factory expansion for fan-out parallelism
- Add template substitution for job payloads ({job_id}, {output_dir}, etc)
- Add output artifact validation against ArtifactSpec
- Implement retry logic and timeout handling
- Provide comprehensive error messages
```

---

## Phase 4: Wiring & Testing

### Step 9: Wire FullConfig + Executor
**File:** `src/aid2e/utilities/workflows/executor.py` (~200 lines)

**Tasks:**
- [ ] Create `WorkflowExecutor` class:
  - [ ] `execute_workflow(workflow: WorkflowDefinition, config: FullConfig) -> WorkflowOutput`
  - [ ] Resolve scheduler at stage level (inherit from global or use stage override)
  - [ ] Execute DAG stages in topological order
  - [ ] Pass design params + iteration metadata to jobs
  - [ ] Collect objective values from objective computation
- [ ] Create `ExecutionContext` dataclass:
  - [ ] design_params: Dict[str, float]
  - [ ] iteration_id: int
  - [ ] output_dir: str
  - [ ] stage_outputs: Dict[str, StageOutput]
- [ ] Create `WorkflowOutput` dataclass:
  - [ ] workflow_id: str
  - [ ] objectives: Dict[str, float]
  - [ ] artifacts: Dict[str, Path]
  - [ ] execution_time_sec: float

**Verification Checklist:**
- [ ] WorkflowExecutor loads configuration correctly
- [ ] Scheduler resolved at stage level (global or override)
- [ ] DAG executed in correct order (topological sort)
- [ ] ExecutionContext passed through stages
- [ ] Objectives computed and collected
- [ ] WorkflowOutput contains expected fields
- [ ] Integration test can instantiate and call execute_workflow()

**Commit Message:**
```
feat: Implement workflow executor and orchestration

- Create WorkflowExecutor.execute_workflow() for DAG orchestration
- Implement ExecutionContext for passing data between stages
- Add scheduler resolution (global/stage-level override)
- Implement DAG execution in topological order
- Create WorkflowOutput with objectives and artifacts
- Add comprehensive logging for debugging
```

---

### Step 10: Add Config Parsing Tests
**File:** `tests/test_utilities/test_workflows/test_workflow_config_parsing.py` (~200 lines)

**Test Cases:**
- [ ] Test minimal workflow YAML parsing
- [ ] Test multi-stage DAG structure
- [ ] Test objective spec validation:
  - [ ] Script objective with valid path
  - [ ] Script objective with missing path (should error)
  - [ ] Inline objective with valid entrypoint
  - [ ] Inline objective with invalid entrypoint
- [ ] Test scheduler inheritance:
  - [ ] Stage inherits global scheduler if not specified
  - [ ] Stage scheduler overrides global
- [ ] Test job_factory expansion
- [ ] Test artifact spec validation

**Verification Checklist:**
- [ ] All tests pass
- [ ] Coverage > 80% for workflow_config.py
- [ ] Error messages are clear and actionable
- [ ] No flaky tests (run 5x to verify)

**Commit Message:**
```
test: Add comprehensive workflow config parsing tests

- Test minimal workflow YAML parsing
- Test multi-stage DAG structure validation
- Test objective spec validation (script and inline)
- Test scheduler inheritance and override
- Test job_factory expansion
- Test artifact spec validation
- Achieve > 80% coverage of workflow_config.py
```

---

### Step 11: Add Workflow Execution Integration Tests
**File:** `tests/test_utilities/test_workflows/test_workflow_execution.py` (~250 lines)

**Test Cases:**
- [ ] Test execute_workflow with 2-step DAG:
  - [ ] Create test fixture with 2 design points
  - [ ] Execute Stage 1 (evaluate)
  - [ ] Verify objective output files created
  - [ ] Execute Stage 2 (aggregate)
  - [ ] Verify final aggregated output
- [ ] Test JobLib parallelism:
  - [ ] Submit 4 jobs, verify all run (use pytest-timeout)
  - [ ] Verify parallelism respected (max_concurrent)
- [ ] Test objective computation:
  - [ ] dtlz2_problem.py produces correct objectives
  - [ ] Objectives parsed correctly into WorkflowOutput
- [ ] Test error handling:
  - [ ] Missing input files (should fail gracefully)
  - [ ] Invalid output format (should fail gracefully)
  - [ ] Timeout (should retry/fail)

**Verification Checklist:**
- [ ] All tests pass
- [ ] 2-step workflow execution completes successfully
- [ ] Objectives correctly computed and collected
- [ ] JobLib parallelism verified (time < 1s for 4 jobs)
- [ ] Error cases handled gracefully
- [ ] No flaky tests

**Commit Message:**
```
test: Add workflow execution integration tests

- Test 2-step DAG workflow execution end-to-end
- Test JobLib parallelism with multiple design points
- Test objective computation via dtlz2_problem.py
- Test error handling (missing files, invalid format, timeout)
- Verify objectives correctly parsed and collected
- Achieve stable, deterministic test results
```

---

## Phase 5: CLI & End-to-End

### Step 12: Update CLI optimize Command
**File:** `src/aid2e/cli/workflow_commands.py`

**Tasks:**
- [ ] Extend `optimize` command:
  - [ ] Detect if config has `workflows` section
  - [ ] If workflows present: use `WorkflowExecutor`
  - [ ] If workflows absent: fallback to simple optimize (existing behavior)
- [ ] Add output formatting:
  - [ ] Design point ID
  - [ ] Objectives dict
  - [ ] Execution status and time
- [ ] Add `--workflow-name` optional flag to select specific workflow (if multiple defined)

**Verification Checklist:**
- [ ] `aid2e optimize config.yml` works without workflows (backward compatible)
- [ ] `aid2e optimize workflow_dtlz2_joblib.yml` executes workflow
- [ ] CLI output shows objectives: "f1: 0.123, f2: 0.456"
- [ ] Help text updated (`aid2e optimize --help`)

**Commit Message:**
```
feat: Wire workflow executor into CLI optimize command

- Extend optimize command to detect and execute workflows
- Maintain backward compatibility (no workflows = simple optimize)
- Add --workflow-name flag for multi-workflow configs
- Format output: design point ID, objectives dict, execution time
- Update CLI help text with workflow examples
```

---

### Step 13: Create Workflow Configuration Documentation
**File:** `docs/workflow-configuration.md` (new)

**Sections:**
- [ ] Overview (workflow, branch, stage, job nomenclature)
- [ ] YAML schema with examples
- [ ] Stage definition and job_factory options
- [ ] Objective computation (script vs inline)
- [ ] Parallelism and retry policies
- [ ] 2-step DTLZ2 workflow walkthrough
- [ ] Troubleshooting guide

**Verification Checklist:**
- [ ] Documentation is clear and comprehensive
- [ ] Examples are copy-paste ready
- [ ] All YAML schema elements documented
- [ ] Links to related docs (scheduler-configuration.md, problem-config, etc.)

**Commit Message:**
```
docs: Add comprehensive workflow configuration guide

- Document workflow/branch/stage/job nomenclature
- Provide complete YAML schema with examples
- Explain objective computation (script and inline)
- Document parallelism and retry policies
- Include 2-step DTLZ2 workflow tutorial
- Add troubleshooting section
```

---

### Step 14: Run End-to-End Test
**File:** `scripts/test_e2e_workflow.py` (optional helper) or manual test

**Tasks:**
- [ ] Load example YAML: `examples/basic/workflow_dtlz2_joblib.yml`
- [ ] Execute via Python API:
  ```python
  config = load_config("examples/basic/workflow_dtlz2_joblib.yml")
  executor = WorkflowExecutor()
  output = executor.execute_workflow(config.workflows[0], config)
  print(output)
  ```
- [ ] OR via CLI:
  ```bash
  aid2e optimize examples/basic/workflow_dtlz2_joblib.yml
  ```
- [ ] Verify:
  - [ ] No errors
  - [ ] Objectives computed correctly
  - [ ] Output artifacts created
  - [ ] Execution time reasonable (< 60s)

**Verification Checklist:**
- [ ] Config loads without errors
- [ ] Workflow executes to completion
- [ ] Objectives: f1 and f2 have correct format/values
- [ ] Artifacts directory has expected files
- [ ] Execution time < 60s
- [ ] No leftover temp files or dangling processes

**Commit Message:**
```
test: Add end-to-end workflow execution validation

- Validate full pipeline: load config → execute workflow → verify outputs
- Test via Python API and CLI
- Verify objectives computed and artifacts created
- Confirm execution time and resource usage acceptable
```

---

## Summary & Commit Strategy

### Recommended Commit Order:
1. **Commit Phase 1:** Steps 1–3 (models, DAG, dtlz2_problem)
2. **Commit Phase 2:** Steps 4–6 (FullConfig integration, YAML parsing, validation)
3. **Commit Phase 3:** Steps 7–8 (example YAML, JobLib executor)
4. **Commit Phase 4:** Steps 9–11 (orchestration, config tests, execution tests)
5. **Commit Phase 5:** Steps 12–14 (CLI, docs, e2e test)

### Post-Commit Checklist for PR:
After each phase commit:
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No linting errors: `flake8 src/ --max-line-length=100` or your linter
- [ ] Docstrings follow Google-style format
- [ ] No unused imports
- [ ] All new files have module docstrings
- [ ] Examples are tested/runnable
- [ ] Update PR description with phase completion
- [ ] Request review if needed

---

**Next Action:** Begin Step 1 (create workflow config models). Ready?
