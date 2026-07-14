# Scheduler/Runner Configuration Guide

## Overview

The scheduler/runner configuration defines how AID2E executes optimization jobs. The framework supports three execution backends:

1. **JobLibRunner** - Local parallel execution using Python's joblib library
2. **SlurmRunner** - HPC cluster execution via SLURM workload manager
3. **PanDAiDDSRunner** - Distributed execution across multiple sites via PanDA iDDS

## Configuration Structure

The `scheduler` section in your configuration file defines runner settings:

```yaml
scheduler:
  runner_type: "JobLibRunner"  # or "SlurmRunner" or "PanDAiDDSRunner"
  parameters:
    # Runner-specific settings
  # Common settings
  max_retries: 3
  output_location: "./scheduler_output"
  monitor_interval: 30
```

## JobLibRunner Configuration

**Best for:** Single-machine parallel execution with multiple CPU cores

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `n_jobs` | int | -1 | Number of jobs to run in parallel. -1 = use all available processors |
| `backend` | str | "loky" | Execution backend: "loky", "threading", "processes" |
| `timeout` | int/None | None | Timeout in seconds for each job. None = no timeout |
| `verbose` | int | 0 | Verbosity level (0-11) for joblib logging |

### Example

```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 8              # Use 8 CPU cores
    backend: "loky"        # Robust multiprocessing backend
    timeout: 3600          # 1 hour timeout per job
    verbose: 1             # Some logging output
  max_retries: 3
  output_location: "./joblib_output"
  monitor_interval: 30
```

### When to Use

- Development and testing on local machines
- Single-node multi-core systems
- Quick prototyping with manageable problem sizes
- Integration testing in CI/CD pipelines

## SlurmRunner Configuration

**Best for:** HPC cluster execution with job queuing and resource allocation

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `partition` | str/None | None | SLURM partition/queue name |
| `ntasks` | int | 1 | Number of tasks to run |
| `cpus_per_task` | int/None | None | CPU cores per task |
| `mem` | str/None | None | Memory request (e.g., "4GB", "8000MB") |
| `time` | str/None | None | Wall clock time limit (HH:MM:SS) |
| `gres` | str/None | None | Generic resource (e.g., "gpu:1" for one GPU) |
| `job_name_prefix` | str | "aid2e" | Prefix for generated SLURM job names for tracking |

### Example

```yaml
scheduler:
  runner_type: "SlurmRunner"
  parameters:
    partition: "gpu"
    ntasks: 4
    cpus_per_task: 8
    mem: "32GB"
    time: "12:00:00"
    gres: "gpu:1"
  max_retries: 3
  output_location: "./slurm_output"
  monitor_interval: 60
```

### When to Use

- Production runs on HPC clusters (NERSC, XSEDE, etc.)
- Large-scale optimization problems
- GPU-accelerated evaluations
- Jobs requiring specific resource constraints
- When you need job queuing and fair scheduling

### SLURM Tips

- Check available partitions: `sinfo`
- Monitor submitted jobs: `squeue`
- View available GPUs: `sinfo --gres`
- Check resource limits: `slurm_limits`

## PanDAiDDSRunner Configuration

**Best for:** Distributed execution across multiple computing sites with automated load balancing

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str/None | auto-generated | PanDA job name for tracking, must start with `user.` |
| `task_type` | str/None | "AID2E" | Type of processing (PanDA classification) |
| `cloud` | str/None | None | Target cloud/region |
| `max_walltime` | int/None | None | Maximum walltime in seconds |

### Example

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    cloud: null              # Auto-select best site
    task_type: "optimization"
    max_walltime: 7200   # 2 hours
  max_retries: 5
  output_location: "./panda_output"
  monitor_interval: 120
```

### When to Use

- Large-scale distributed optimization across multiple institutions
- Federated computing environments (e.g., ATLAS collaboration)
- Load-balanced execution across geographically distributed sites
- When individual sites may have intermittent availability
- Projects requiring centralized job tracking and monitoring

### PanDA iDDS Tips

- Monitor jobs via PanDA dashboard: `https://panda.cern.ch/`
- Check campaign status: `idds show --id <campaign_name>`
- View worker logs: `idds logs --id <task_id>`
- Troubleshoot: `idds status --id <campaign_name>`

## Common Parameters

These apply regardless of runner type:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_retries` | int | 3 | Global maximum retries for failed jobs |
| `output_location` | str | "./scheduler_output" | Base directory for scheduler output files |
| `monitor_interval` | int | 30 | Interval (seconds) for job status checks |

## Configuration Examples

### Minimal JobLib Configuration
```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: -1
```

### Production SLURM Setup
```yaml
scheduler:
  runner_type: "SlurmRunner"
  parameters:
    partition: "gpu"
    ntasks: 8
    cpus_per_task: 16
    mem: "64GB"
    time: "24:00:00"
    gres: "gpu:4"
    job_name_prefix: "aid2e_large_scale"
  max_retries: 5
  output_location: "./results/slurm"
  monitor_interval: 300
```

### Distributed PanDA Setup
```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    cloud: null  # Distributed across all sites
    max_walltime: 7200
  max_retries: 7
  output_location: "./results/panda"
  monitor_interval: 300
```

## Python API Usage

```python
from aid2e.utilities.configurations import (
    load_config,
    SchedulerConfiguration,
)

# Load complete config including scheduler
config = load_config("examples/basic/full_example_slurm.yml")

# Access scheduler configuration
scheduler_cfg = config.scheduler
print(f"Runner type: {scheduler_cfg.runner_type}")
print(f"Max retries: {scheduler_cfg.max_retries}")

# Get validated runner-specific config
runner_cfg = scheduler_cfg.parse_runner_params()
print(f"Runner parameters: {runner_cfg}")

# Register custom runner types if needed
from aid2e.utilities.configurations import register
from pydantic import BaseModel

class CustomRunnerConfig(BaseModel):
    # Your custom fields
    pass

register("CustomRunner", CustomRunnerConfig)
```

## Migration from Legacy Scheduler Configuration

If upgrading from an older AID2E version without scheduler configuration:

1. **JobLib (local execution)** - New default behavior
   ```yaml
   scheduler:
     runner_type: "JobLibRunner"
     parameters:
       n_jobs: -1
   ```

2. **SLURM (HPC)** - Replace old SLURM template with:
   ```yaml
   scheduler:
     runner_type: "SlurmRunner"
     parameters:
       # ... parameters from old slurm.template file
   ```

3. **No scheduler specified** - Defaults to JobLibRunner with 1 job (sequential execution)

## Troubleshooting

### Issue: "runner_type must be one of JobLibRunner, SlurmRunner, PanDAiDDSRunner"

**Solution:** Check spelling and case sensitivity. Valid values are exactly:
- `JobLibRunner`
- `SlurmRunner`
- `PanDAiDDSRunner`

### Issue: JobLib jobs timeout

**Solution:** Increase the `timeout` parameter:
```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    timeout: 7200  # Increase to 2 hours
```

### Issue: SLURM job not starting

**Solution:** Check partition availability and resource limits:
```bash
sinfo  # Check available partitions
sinfo --gres  # Check GPU availability
```

### Issue: PanDA task failures

**Solution:** Increase scheduler retries and the runner walltime:
```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    max_walltime: 7200
```

## See Also

- [Full Configuration Guide](../user-guide/overview.md)
- [Optimization Configuration](optimization_config.md)
- [Problem Configuration](problem_config.md)
- [Example Configurations](../../examples/basic/)
