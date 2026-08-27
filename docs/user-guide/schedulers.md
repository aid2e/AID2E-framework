# Schedulers

## Overview

The scheduler configuration defines how AID2E executes optimization jobs. The
framework supports three execution backends:

1. **JobLibRunner** - Local parallel execution using Python's joblib library
2. **SlurmRunner** - HPC cluster execution through the Slurm workload manager
3. **PanDAiDDSRunner** - Distributed execution across multiple sites via PanDA iDDS

## Configuration

The `scheduler` section in your configuration file defines runner settings:

```yaml
scheduler:
  runner_type: "JobLibRunner"  # or "SlurmRunner" or "PanDAiDDSRunner"
  parameters:
    # Runner-specific settings
```

`SchedulerConfiguration` also accepts `max_retries`, `output_location`, and
`monitor_interval`. These fields are not currently consumed by the config-driven
runtime. Execution directories come from the problem and workflow runtime, while
polling is controlled by runner or stage settings.

- `max_retries` (`int`, default `3`): Reserved global retry limit; retries are
  not currently implemented.
- `output_location` (`str`, default `"./scheduler_output"`): Reserved scheduler
  output location.
- `monitor_interval` (`int`, default `30`): Reserved global monitoring
  interval.

### Scheduler Cascade

Schedulers can be set globally or for a workflow, branch, or stage. A stage
scheduler overrides the branch, workflow, and global schedulers, in that order.
See the [workflow guide](workflows.md#scheduler-cascade) for examples.

### Parallelism and Failure Behavior

Workflow stages define `parallelism.max_concurrent`, `parallelism.retry_max`,
and `parallelism.timeout_sec`. `DAGExecutor` forwards these values to
`run_stage()` as a parallelism policy.

- JobLib applies `max_concurrent`, but only logs `retry_max`; it does not retry
  failed jobs. `JobLibRunnerConfig.timeout` applies to command subprocesses,
  but not Python callable jobs. The stage `timeout_sec` is not currently used.
- Slurm uses the stage `poll_interval` while waiting for terminal job states.
  It does not currently apply `max_concurrent`, retries, or `timeout_sec`.
- PanDA uses the stage `poll_interval` while waiting for submitted function
  jobs. It does not currently retry failed jobs.

For scheduler-backed workflow stages, `DAGExecutor` currently supplies a
five-second `poll_interval`, which overrides the Slurm or PanDA runner default
for that stage.

The direct, non-scheduler executor path also reports that retries are not
implemented. A failed scheduler stage is returned to `DAGExecutor` and fails the
workflow; optimizer-level failed-trial handling is documented separately in the
[optimizer guide](optimizers.md#failed-and-penalized-trials).

`aid2e optimize` rejects a configuration without a scheduler at runtime because
optimization execution requires a scheduler.

## JobLib

**Best for:** Single-machine parallel execution with multiple CPU cores

### Configuration

- `n_jobs` (`int`, default `-1`): Number of jobs to run in parallel. `-1` uses
  all available processors.
- `backend` (`str`, default `"loky"`): JobLib backend, normally `loky`,
  `threading`, or `multiprocessing`.
- `timeout` (`int` or `None`, default `None`): Timeout for command jobs; not
  applied to Python callable jobs.
- `verbose` (`int`, default `0`): Verbosity level from 0 to 11 for joblib
  logging.

Example:

```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 8              # Use 8 CPU cores
    backend: "loky"        # Robust multiprocessing backend
    timeout: 3600          # 1 hour timeout per job
    verbose: 1             # Some logging output
```

Minimal configuration:

```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: -1
```

### When to Use

- Development and testing on local machines
- Single-node multi-core systems
- Quick prototyping with manageable problem sizes
- Integration testing in CI/CD pipelines

### JobLib Tips

- Python `function` jobs with `params` and command jobs both execute locally.
- `run_stage()` returns after every job has completed or failed.
- A stage's `parallelism.max_concurrent` setting caps the configured `n_jobs`
  value when that limit is present.

The JobLib `timeout` field applies to command subprocesses. It does not interrupt
Python callable jobs.

## Slurm

**Best for:** HPC cluster execution with job queuing and resource allocation

### Configuration

- `partition` (`str` or `None`, default `None`): Slurm partition or queue name.
- `account` (`str` or `None`, default `None`): Slurm account to charge.
- `qos` (`str` or `None`, default `None`): Slurm quality-of-service value.
- `nodes` (`int`, default `1`): Number of nodes requested.
- `ntasks` (`int`, default `1`): Number of tasks to run.
- `cpus_per_task` (`int` or `None`, default `None`): CPU cores per task.
- `mem` (`str` or `None`, default `None`): Memory request, for example `4G`.
- `time` (`str` or `None`, default `None`): Wall clock time limit in
  `HH:MM:SS` format.
- `gres` (`str` or `None`, default `None`): Generic resource, for example
  `gpu:1` for one GPU.
- `constraint` (`str` or `None`, default `None`): Optional node constraint.
- `job_name_prefix` (`str`, default `"aid2e"`): Prefix for generated Slurm job
  names for tracking.
- `setup_commands` (`list[str]`, default `[]`): Commands written before the
  workload command.
- `submit_working_dir` (`str` or `None`, default `None`): Directory used for
  `sbatch` and generated scripts.
- `runtime_working_dir` (`str` or `None`, default `None`): Directory used by
  the workload at runtime.
- `poll_interval` (`int`, default `5`): Stage status polling interval in
  seconds.
- `sbatch_extra_args` (`list[str]`, default `[]`): Additional `sbatch` command
  arguments.
- `capture_stdout` (`bool`, default `true`): Write scheduler-owned
  standard-output logs.
- `capture_stderr` (`bool`, default `true`): Write scheduler-owned
  standard-error logs.

`SchedulerConfigLoader` also accepts `template_file` inside Slurm parameters.
The file must contain a JSON object. Its values are loaded first and inline
parameters override them before `SlurmRunnerConfig` validation. Individual job
resource values can override the corresponding runner-level resource fields.

Example:

```yaml
scheduler:
  runner_type: "SlurmRunner"
  parameters:
    partition: "gpu"
    nodes: 1
    ntasks: 1
    cpus_per_task: 8
    mem: "32G"
    time: "12:00:00"
    gres: "gpu:1"
    poll_interval: 60
```

### When to Use

- Production runs on HPC clusters
- Large-scale optimization problems
- GPU-accelerated evaluations
- Jobs requiring specific resource constraints
- When you need job queuing and fair scheduling

### Slurm Tips

Command jobs and Python `function` jobs with `params` are submitted through
`sbatch`. The submission host requires `sbatch`, `squeue`, and `sacct`;
cancellation uses `scancel`. Callable jobs require an importable module function
and JSON-serializable parameters. The Python environment and handoff paths must
also be available on compute nodes.

Useful Slurm commands:

- Check available partitions: `sinfo`
- Monitor submitted jobs: `squeue`
- View available GPUs: `sinfo --gres`
- Check resource limits: `slurm_limits`

If a Slurm job does not start, check partition availability and resource limits:

```bash
sinfo  # Check available partitions
sinfo --gres  # Check GPU availability
```

## PanDA/iDDS

**Best for:** Distributed execution across multiple computing sites with automated load balancing

### Configuration

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `name` | str/None | auto-generated | PanDA job name for tracking, must start with `user.` |
| `job_name_prefix` | str | "aid2e_job" | Prefix used when auto-generating the PanDA job name |
| `task_type` | str/None | "AID2E" | Type of processing (PanDA classification) |
| `cloud` | str/None | None | Target cloud/region |
| `queue` | str/None | None | Target PanDA queue |
| `max_walltime` | int/None | None | Maximum walltime in seconds |

Example:

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    cloud: null              # Auto-select best site
    task_type: "optimization"
    max_walltime: 7200   # 2 hours
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

### Detailed YAML Configuration

This guide explains how to configure the PanDAiDDS scheduler using YAML files in the AID2E framework.

#### Quick Start

**Minimal configuration**

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    cloud: "US"
    queue: "BNL_PanDA_1"
    max_walltime: 3600
    core_count: 1
    total_memory: 2000
```

The `name` field will be auto-generated as `user.<username>.aid2e_job`.

**Full configuration**

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    name: "user.scientist.experiment"  # Must start with 'user.<username>'
    cloud: "US"
    queue: "BNL_PanDA_1"
    source_dir: null  # null = current directory
    source_dir_parent_level: 1
    exclude_source_files:
      - "(^|/)\\..*"  # Hidden files
      - ".*\\.log"
      - "__pycache__"
    max_walltime: 7200
    core_count: 4
    total_memory: 8000
    enable_separate_log: true
    job_dir: "/tmp/panda_jobs"
```

#### Configuration Fields

**Required fields**

| Field | Type | Description |
|-------|------|-------------|
| `cloud` | string | PanDA cloud/region (e.g., "US", "EU") |
| `queue` | string | PanDA queue name (e.g., "BNL_PanDA_1") |

**Optional fields**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | auto-generated | Job name, must start with `user.<username>` (auto-generates if omitted) |
| `job_name_prefix` | string | "aid2e_job" | Prefix used when auto-generating the PanDA job name |
| `init_env` | string/callable | "source setup_aid2e.sh; bash install_aid2e_dependencies.sh;" | Environment initialization (auto-sets if omitted, prepended if string) |
| `source_dir` | string | project root | Directory to upload to PanDA (auto-sets to project root if omitted) |
| `max_walltime` | int | None | Maximum walltime in seconds |
| `core_count` | int | 1 | CPU cores per job |
| `total_memory` | int | 4000 | Memory in MB per job |
| `enable_separate_log` | bool | true | Enable separate log files |
| `job_dir` | string | None | Job working directory |
| `source_dir_parent_level` | int | 1 | Parent levels to include |
| `exclude_source_files` | list | See below | File patterns to exclude (.venv, venv, .git included) |

**Default excluded files**

```python
[
    r"(^|/)\.[^/]+",           # Hidden files
    "doc*",                     # Documentation
    "DTLZ2*",                   # Test files
    ".*json",                   # JSON files
    ".*log",                    # Log files
    "work",                     # Work directory
    "log",                      # Log directory
    "OUTDIR",                   # Output directory
    "calibrations",             # Calibration files
    "fieldmaps",                # Field maps
    "gdml",                     # GDML geometry
    "EICrecon-drich-mobo",      # EIC specific
    "eic-software",             # EIC software
    "epic-geom-drich-mobo",     # EPIC geometry
    "irt",                      # IRT files
    "share",                    # Shared files
    "back*",                    # Backup files
    "__pycache__",              # Python cache
    ".venv",                    # Virtual environment
    "venv",                     # Virtual environment
    ".git",                     # Git repository
]
```

#### Auto-Generated Fields

**Name auto-generation**

The `name` field follows PanDA conventions: `user.<username>.<suffix>`

**Auto-Generation Rules:**
1. **If `name` is omitted or `null`**: Auto-generates from username
2. **System username**: Uses `getpass.getuser()`
3. **Environment override**: Set `PANDA_USERNAME` env var
4. **Validation**: Explicit names must start with `user.`

**Examples:**

```yaml
# Auto-generate from system username
parameters:
  job_name_prefix: "aid2e_job"
  cloud: "US"
  queue: "BNL_PanDA_1"
  # name omitted → "user.<system_username>.aid2e_job"
```

```bash
# Override username via environment variable
export PANDA_USERNAME=myuser
# YAML with no name → "user.myuser.aid2e_job"
```

```yaml
# Explicit name (must start with 'user.')
parameters:
  name: "user.physicist.epic_tracking"
  cloud: "US"
  queue: "BNL_PanDA_1"
```

**Source directory auto-setting**

The `source_dir` field specifies which directory to upload to PanDA.

**Auto-Setting Rules:**
1. **If `source_dir` is omitted or `null`**:
   - Defaults to the project root directory (calculated from the config module location)
2. **Environment override**: Set `PANDA_SOURCE_DIR` env var
3. **Explicit value**: Provide path directly in config

**Examples:**

```yaml
# Auto-set to project root directory
parameters:
  cloud: "US"
  queue: "BNL_PanDA_1"
  # source_dir omitted → project root directory
```

```bash
# Override via environment variable
export PANDA_SOURCE_DIR=/path/to/source
# YAML with no source_dir → "/path/to/source"
```

```yaml
# Explicit source directory
parameters:
  source_dir: "/explicit/path/to/upload"
  cloud: "US"
  queue: "BNL_PanDA_1"
```

**Environment initialization auto-setting**

The `init_env` field specifies commands to run before job execution.

**Auto-Setting Rules:**
1. **If `init_env` is omitted or `null`**:
   - Defaults to `"source setup_aid2e.sh; bash install_aid2e_dependencies.sh;"` to set up the AID2E environment
2. **If `init_env` is provided as a string**:
   - Prepends `"source setup_aid2e.sh && bash install_aid2e_dependencies.sh && "` to the provided command
   - This ensures the environment is always set up before custom commands
3. **If `init_env` is a callable or other type**:
   - Leaves it as-is (no modification)

**Examples:**

```yaml
# Auto-set to source setup script
parameters:
  cloud: "US"
  queue: "BNL_PanDA_1"
  # init_env omitted → "source setup_aid2e.sh; bash install_aid2e_dependencies.sh;"
```

```yaml
# Custom initialization command (setup script will be prepended)
parameters:
  init_env: "export MY_VAR=value && module load gcc"
  cloud: "US"
  queue: "BNL_PanDA_1"
  # Result: "source setup_aid2e.sh && bash install_aid2e_dependencies.sh && export MY_VAR=value && module load gcc"
```

#### Loading Configurations

**Method 1: Full config (recommended)**

```python
from aid2e.utilities.configurations import load_config

# Load complete configuration
config = load_config("config.yml")

# Access scheduler config
scheduler_config = config.scheduler
panda_config = scheduler_config.parse_runner_params()

print(panda_config.name)
print(panda_config.cloud)
```

**Method 2: Scheduler config only**

```python
import yaml
from aid2e.utilities.configurations.scheduler_config import SchedulerConfigLoader

# Load YAML
with open("scheduler.yml") as f:
    data = yaml.safe_load(f)

# Parse the inner scheduler mapping
scheduler_config = SchedulerConfigLoader.from_dict(data["scheduler"])
panda_config = scheduler_config.parse_runner_params()
```

**Method 3: Direct PanDA config**

```python
import yaml
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig

# Load YAML (just PanDA parameters)
with open("panda.yml") as f:
    data = yaml.safe_load(f)

# Parse
panda_config = PanDAiDDSRunnerConfig(**data)
```

#### Complete Example

See `examples/epic/tracking/panda_scheduler_config.yml` for complete examples including:
- Minimal configuration
- Full configuration with all fields
- Environment variable usage
- Integration with optimizer and problem configs

The examples are retained for reference but should be validated against the
current full configuration schema before being used as complete optimization
inputs.

#### PanDA Queues

Common PanDA queues:

- `BNL_PanDA_1` - Brookhaven National Laboratory
- `ORNL_Frontier` - Oak Ridge National Laboratory
- `NERSC_Perlmutter` - NERSC Perlmutter supercomputer

Contact your PanDA administrator for available queues in your cloud.

#### Validation

The configuration is validated via Pydantic models:
- Type checking
- Field validation
- Name format validation (must start with `user.`)
- Required field checks

Invalid configurations will raise `ValidationError` with detailed messages.

#### See Also

- [PanDA Documentation](https://panda-wms.readthedocs.io/)
- [iDDS Documentation](https://idds.readthedocs.io/)
- [AID2E Documentation](https://aid2e.github.io/AID2E-framework)

#### Troubleshooting

**"runner_type must be one of JobLibRunner, SlurmRunner, PanDAiDDSRunner"**

Check spelling and case sensitivity. Valid values are exactly:

- `JobLibRunner`
- `SlurmRunner`
- `PanDAiDDSRunner`

**Issue: PanDA task walltime**

Increase the runner walltime when the remote task requires more time:
```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    max_walltime: 7200
```

## Developer Reference

### Python API

The common scheduler interface and result models are available from
`aid2e.schedulers`. Scheduler implementations can be imported from their
scheduler packages:

```python
from aid2e.schedulers import (
    BaseScheduler,
    JobStatus,
    StageExecutionResult,
)
from aid2e.schedulers.JobLib import JobLibScheduler
from aid2e.schedulers.Slurm import SlurmScheduler
from aid2e.schedulers.PanDAiDDS import PanDAiDDSScheduler
```

```python
from aid2e.utilities.configurations import load_config
from aid2e.utilities.runtime_builders import build_scheduler_from_config

# Load a complete configuration including its scheduler
config = load_config("examples/dtlz2/dtlz2_optimization.yml")

# Access and validate the scheduler configuration
scheduler_cfg = config.scheduler
print(f"Runner type: {scheduler_cfg.runner_type}")

runner_cfg = scheduler_cfg.parse_runner_params()
print(f"Runner parameters: {runner_cfg}")

# Construct the configured scheduler
scheduler = build_scheduler_from_config(scheduler_cfg)
```

### Scheduler Registration

The framework has two scheduler registries:

- `aid2e.utilities.configurations.scheduler_registry` maps the three supported
  `runner_type` values to their Pydantic parameter models. Built-in models are
  loaded on demand and also register when their scheduler package is imported.
- `aid2e.schedulers._registry` maps short implementation names to
  `BaseScheduler` subclasses. It currently loads only `joblib` on demand.

Config-driven runtime construction does not use the implementation registry.
`build_scheduler_from_config()` explicitly constructs JobLib, Slurm, or PanDA.
Adding a new config-driven scheduler therefore requires a `BaseScheduler`
implementation, a registered parameter model, a new allowed `runner_type`, and
a runtime-builder branch. Calling `register()` alone is not sufficient.

## See Also

- [Configuration Guide](configuration.md)
- [Workflow Guide](workflows.md)
- [Optimizer Guide](optimizers.md)
- DTLZ2 configuration: `examples/dtlz2/dtlz2_optimization.yml`
- dRICH workflow: `examples/epic/drich/workflow.yml`
