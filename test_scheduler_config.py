#!/usr/bin/env python
"""Test scheduler configuration models."""

from aid2e.utilities.configurations import (
    SchedulerConfiguration,
    JobLibRunnerConfig,
    SlurmRunnerConfig,
    PanDAiDDSRunnerConfig,
    load_config,
)

# Test JobLib config creation
joblib_cfg = SchedulerConfiguration(
    runner_type='JobLibRunner',
    joblib=JobLibRunnerConfig(n_jobs=-1, backend='loky')
)
print('✓ JobLibRunner config created successfully')
print(f'  - Runner type: {joblib_cfg.runner_type}')
print(f'  - Jobs: {joblib_cfg.joblib.n_jobs}')
print(f'  - Backend: {joblib_cfg.joblib.backend}')

# Test SLURM config creation
slurm_cfg = SchedulerConfiguration(
    runner_type='SlurmRunner',
    slurm=SlurmRunnerConfig(
        partition='gpu',
        ntasks=4,
        cpus_per_task=8,
        gres='gpu:1'
    )
)
print('\n✓ SlurmRunner config created successfully')
print(f'  - Runner type: {slurm_cfg.runner_type}')
print(f'  - Partition: {slurm_cfg.slurm.partition}')
print(f'  - CPUs per task: {slurm_cfg.slurm.cpus_per_task}')
print(f'  - GPUs: {slurm_cfg.slurm.gres}')

# Test PanDA config creation
panda_cfg = SchedulerConfiguration(
    runner_type='PanDAiDDSRunner',
    panda=PanDAiDDSRunnerConfig(
        campaign_name='test_campaign',
        n_workers=20
    )
)
print('\n✓ PanDAiDDSRunner config created successfully')
print(f'  - Runner type: {panda_cfg.runner_type}')
print(f'  - Campaign: {panda_cfg.panda.campaign_name}')
print(f'  - Workers: {panda_cfg.panda.n_workers}')

# Test get_active_config
print('\n✓ Testing get_active_config method:')
print(f'  - JobLib active config: {type(joblib_cfg.get_active_config()).__name__}')
print(f'  - SLURM active config: {type(slurm_cfg.get_active_config()).__name__}')
print(f'  - PanDA active config: {type(panda_cfg.get_active_config()).__name__}')

print('\n✅ All scheduler configurations validated successfully!')
