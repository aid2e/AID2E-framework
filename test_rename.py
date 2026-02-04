#!/usr/bin/env python
"""Quick test of renamed evaluators and contexts."""

from aid2e.utilities.workflows import (
    BranchContext,
    StageContext,
    JobContext,
    BashEvaluator,
    PythonEvaluator,
    ContainerEvaluator
)

# Create context hierarchy
branch_ctx = BranchContext(
    branch_id='main_branch',
    parameters={'branch_param': 'value1', 'timeout': 300}
)

stage_ctx = StageContext(
    stage_id='evaluate',
    parameters={'stage_param': 'value2', 'parallel': 4},
    branch_context=branch_ctx
)

job_ctx = JobContext(
    job_id='dtlz2_eval_job',
    stage_id='evaluate',
    workflow_id='dtlz2_workflow',
    design_point={'x1': 0.5, 'x2': 0.7},
    stage_context=stage_ctx
)

print('✅ Context hierarchy created successfully')
print(f'\nBranchContext: {branch_ctx.branch_id}')
print(f'  Parameters: {branch_ctx.parameters}')

print(f'\nStageContext: {stage_ctx.stage_id}')
print(f'  Parameters: {stage_ctx.parameters}')
print(f'  Parent branch: {stage_ctx.branch_context.branch_id}')

print(f'\nJobContext: {job_ctx.job_id}')
print(f'  Design point: {job_ctx.design_point}')
print(f'  Access stage params: {job_ctx.stage_context.parameters}')
print(f'  Access branch params: {job_ctx.stage_context.branch_context.parameters}')

# Create evaluators
bash_eval = BashEvaluator(
    job_id='run_sim',
    bash_command='echo "Running simulation"'
)

python_eval = PythonEvaluator(
    job_id='compute',
    python_callable=lambda ctx: ctx.design_point
)

container_eval = ContainerEvaluator(
    job_id='docker_sim',
    image='physics-sim:v1',
    environment={'X1': '0.5'}
)

print('\n✅ Evaluators created successfully:')
print(f'  {bash_eval}')
print(f'  {python_eval}')
print(f'  {container_eval}')

print('\n✅ All renamings working correctly!')
print('   Operator → Evaluator ✓')
print('   TaskContext → JobContext ✓')
print('   task_id → job_id ✓')
print('   + BranchContext ✓')
print('   + StageContext ✓')
