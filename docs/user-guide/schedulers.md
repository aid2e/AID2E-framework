# Schedulers

## Overview

The scheduler configuration defines how AID2E executes optimization jobs. The framework supports three execution backends:

1. **JobLibRunner** - Local parallel execution using Python's joblib library
2. **SlurmRunner** - HPC cluster execution through the Slurm workload manager
3. **PanDAiDDSRunner** - Distributed execution across multiple sites via PanDA iDDS

## Configuration

The `scheduler` section in your configuration file defines runner settings:

```yaml
scheduler:
  runner_type: "JobLibRunner"  # or "SlurmRunner" or "PanDAiDDSRunner"
  parameters: {}  # Runner-specific settings
```

`SchedulerConfiguration` also accepts:

- `max_retries` (`int`, default `3`): Caps the stage `retry_max` policy passed to scheduler runners. The current runners do not resubmit jobs from this setting.
- `output_location` (`str`, default `"./scheduler_output"`): Common output setting; execution directories currently come from the problem and workflow runtime.
- `monitor_interval` (`int`, default `30`): Common monitoring setting; runner or stage polling settings control the actual polling interval.

### Scheduler Cascade

Schedulers can be set globally or for a workflow, branch, or stage. A stage scheduler overrides the branch, workflow, and global schedulers, in that order. See the [workflow guide](workflows.md#scheduler-cascade) for examples.

### Parallelism and Failure Behavior

Workflow stages define `parallelism.max_concurrent`, `parallelism.retry_max`, `parallelism.timeout_sec`, and `parallelism.poll_interval`. `DAGExecutor` forwards these values to `run_stage()` as a parallelism policy.

- JobLib applies `max_concurrent`, but only logs `retry_max`; it does not retry failed jobs. `JobLibRunnerConfig.timeout` applies to command subprocesses, but not Python callable jobs. The stage `timeout_sec` is not currently used.
- Slurm uses the stage `poll_interval` while waiting for terminal job states. It does not currently apply `max_concurrent`, retries, or `timeout_sec`.
- PanDA uses `poll_interval` while waiting for submitted function jobs and `max_concurrent` to limit concurrent multistage graphs. It does not currently resubmit failed jobs from `retry_max`.

For scheduler-backed stages, `DAGExecutor` forwards the stage `poll_interval` (default `5` seconds), overriding the runner default.

Direct workflow execution has an attempt loop. A failed scheduler stage is returned to `DAGExecutor` and fails the workflow. Optimizer-level failed-trial handling is documented separately in the [optimizer guide](optimizers.md#failed-and-penalized-trials).

`aid2e optimize` rejects a configuration without a scheduler at runtime because optimization execution requires a scheduler.

## JobLib

**Best for:** Single-machine parallel execution with multiple CPU cores

### Configuration

- `n_jobs` (`int`, default `-1`): Number of jobs to run in parallel. `-1` uses all available processors.
- `backend` (`str`, default `"loky"`): JobLib backend, normally `loky`, `threading`, or `multiprocessing`.
- `timeout` (`int` or `None`, default `None`): Timeout for command jobs; not applied to Python callable jobs.
- `verbose` (`int`, default `0`): Verbosity level from 0 to 11 for joblib logging.

Example:

```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 8              # Use 8 CPU cores
    backend: "loky"        # Robust multiprocessing backend
    timeout: 3600          # 1 hour timeout per job
    verbose: 1            # Joblib logging
```

### When to Use

- Development and testing on local machines
- Single-node multi-core systems
- Quick prototyping with manageable problem sizes
- Integration testing in CI/CD pipelines

### JobLib Tips

- Python `function` jobs with `params` and command jobs both execute locally.
- `run_stage()` returns after every job has completed or failed.
- A stage's `parallelism.max_concurrent` setting caps the configured `n_jobs` value when that limit is present.

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
- `time` (`str` or `None`, default `None`): Wall clock time limit in `HH:MM:SS` format.
- `gres` (`str` or `None`, default `None`): Generic resource, for example `gpu:1` for one GPU.
- `constraint` (`str` or `None`, default `None`): Optional node constraint.
- `job_name_prefix` (`str`, default `"aid2e"`): Prefix for generated Slurm job names for tracking.
- `setup_commands` (`list[str]`, default `[]`): Commands written before the workload command.
- `submit_working_dir` (`str` or `None`, default `None`): Directory used for `sbatch` and generated scripts.
- `runtime_working_dir` (`str` or `None`, default `None`): Directory used by the workload at runtime.
- `poll_interval` (`int`, default `5`): Stage status polling interval in seconds.
- `sbatch_extra_args` (`list[str]`, default `[]`): Additional `sbatch` command arguments.
- `capture_stdout` (`bool`, default `true`): Write scheduler-owned standard-output logs.
- `capture_stderr` (`bool`, default `true`): Write scheduler-owned standard-error logs.

`SchedulerConfigLoader` also accepts `template_file` inside Slurm parameters. The file must contain a JSON object. Its values are loaded first and inline parameters override them before `SlurmRunnerConfig` validation. Individual job resource values can override the corresponding runner-level resource fields.

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

Command jobs and Python `function` jobs with `params` are submitted through `sbatch`. The submission host requires `sbatch`, `squeue`, and `sacct`; cancellation uses `scancel`. Callable jobs require an importable module function and JSON-serializable parameters. The Python environment and handoff paths must also be available on compute nodes.

Useful Slurm commands:

- Check available partitions: `sinfo`
- Monitor submitted jobs: `squeue`
- View available GPUs: `sinfo --gres`
- Inspect a job: `scontrol show job <job_id>`

## PanDA/iDDS

**Best for:** Distributed execution across multiple computing sites with automated load balancing

### Client Setup

For the checked-in PanDA examples, initialize the client environment before running the CLI:

```bash
source examples/schedulers/panda-idds/setup_panda.sh
export PANDA_USERNAME=your_panda_username  # Optional account-name override
aid2e optimize examples/schedulers/panda-idds/input-panda.yml
```

The setup script contains shared BNL PanDA endpoint and OIDC settings. It does not set a personal PanDA username.

### Configuration

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | auto-generated | Job name; explicit names must start with `user.` |
| `init_env` | string/list/callable | None | Worker environment initialization; no setup commands are prepended |
| `post_script` | string/callable | cleanup command | Worker cleanup; defaults to `rm -fr .local .venv src examples tests docs` |
| `working_group` | string | "AID2E" | PanDA working group |
| `task_type` | string | "AID2E" | Type of processing (PanDA classification) |
| `cloud` | string | None | PanDA cloud/region |
| `queue` | string | None | PanDA queue; choose one available to your account |
| `init_env_file` | path | None | YAML list or plain-text file of environment commands, resolved relative to the scheduler config file; mutually exclusive with `init_env` |
| `source_dir` | string | cwd/src or cwd | Directory to upload; `PANDA_SOURCE_DIR` overrides the default |
| `max_walltime` | int | None | Maximum walltime in seconds |
| `core_count` | int | 1 | CPU cores per job |
| `total_memory` | int | 4000 | Memory in MB per job |
| `enable_separate_log` | bool | true | Enable separate log files |
| `job_dir` | string | None | Job working directory |
| `source_dir_parent_level` | int | 1 | Parent levels to include |
| `exclude_source_files` | list | See config defaults below | File patterns to exclude (.venv, venv, .git included) |

### Example

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    name: "user.scientist.experiment"  # Must start with 'user.'
    cloud: "US"
    queue: "BNL_PanDA_1"
    source_dir: null  # cwd/src when present, otherwise cwd
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

### Generated Names and Worker Environment

When `name` is omitted, it becomes `user.<username>.aid2e_job`. The username comes from `PANDA_USERNAME`, or the system account when unset. Set `name` explicitly for a different suffix.

`source_dir` defaults to `PANDA_SOURCE_DIR` if set, then `cwd/src` when that directory exists, otherwise `cwd`. Set it explicitly if workers also need examples or other files outside `src`. `exclude_source_files` controls archive exclusions; inspect the [config defaults](https://github.com/aid2e/AID2E-framework/blob/main/src/aid2e/schedulers/PanDAiDDS/config.py) before packaging inputs.

Worker setup must be provided through `init_env` or `init_env_file`; no setup script is automatically prepended. A command list is joined with spaces, so include shell separators where needed:

```yaml
parameters:
  init_env:
    - "source setup_aid2e.sh &&"
    - "export MY_VAR=value"
```

`init_env_file` accepts a YAML list, a YAML string or `init_env` mapping, or a plain-text file of commands. Its path is relative to the configuration file. Do not specify both `init_env` and `init_env_file`.

### All-to-One Dataset Inputs

For an `all2one` dataset dependency, YAML may group multiple parent datasets under the callable argument that should receive their files:

```yaml
dep_type: "datasets"
dep_map: "all2one"
input_datasets:
  input_file_names:
    - "user.example.simreco.a"
    - "user.example.simreco.b"
```

The PanDA adapter expands this list into separate string-valued iDDS input maps during submission. On the worker, it combines the injected file lists and calls the evaluator with `input_file_names=[...]`. This translation applies only to `all2one`; ordinary string-valued dataset mappings are unchanged.

### Examples and Queues

See the [scheduler configuration](https://github.com/aid2e/AID2E-framework/blob/main/examples/schedulers/panda-idds/panda_scheduler_config.yml) and [CLI workflow](https://github.com/aid2e/AID2E-framework/blob/main/examples/schedulers/panda-idds/input-panda.yml). The checked-in examples use BNL settings; choose a queue and cloud available to your account with your PanDA administrator.

### Inspecting Requests, Tasks, and Jobs

The read-only diagnostic script follows the iDDS/PanDA identifier chain from a request to its transforms, JEDI tasks, and PanDA jobs. Source the project and PanDA environments first:

```bash
source setup_aid2e.sh
source examples/schedulers/panda-idds/setup_panda.sh
```

Query a complete iDDS request:

```bash
python examples/schedulers/panda-idds/check_panda_jobs.py --request-id 3665
```

The script also accepts narrower identifiers:

```bash
python examples/schedulers/panda-idds/check_panda_jobs.py --request-id 3665 --transform-id 32469
python examples/schedulers/panda-idds/check_panda_jobs.py --jedi-task-id 40758
python examples/schedulers/panda-idds/check_panda_jobs.py --job-id 4879003
```

`--task-id` and `--runtaskid` are aliases for `--request-id`, not JEDI task IDs. Use `--max-jobs N` to bound job-detail queries. The output is JSON so it can also be filtered with tools such as `jq`.

## Python API

See [scheduler notes](notes/schedulers.md#python-api) for loading scheduler configurations and constructing runner configuration objects in Python.

## Troubleshooting

### Invalid Runner Type

Check spelling and case. Valid values are:

- `JobLibRunner`
- `SlurmRunner`
- `PanDAiDDSRunner`

### JobLib Command Timeout

If the command needs more time, increase `timeout`. This setting does not interrupt Python callable jobs:

```yaml
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    timeout: 7200  # Increase to 2 hours
```

### Slurm Job Not Starting

Check partition availability and resource requests:

```bash
sinfo  # Check available partitions
sinfo --gres  # Check GPU availability
```

### PanDA Task Failure

Inspect the request and worker logs using the [PanDA diagnostic script](#inspecting-requests-tasks-and-jobs). If the job exceeded its walltime, adjust:

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    max_walltime: 7200
```

## See Also

- [Configuration Guide](configuration.md)
- [Workflow Guide](workflows.md)
- [Optimizer Guide](optimizers.md)
- [DTLZ2 configuration](https://github.com/aid2e/AID2E-framework/blob/main/examples/configurations/dtlz2_optimization.yml)
- [dRICH workflow](https://github.com/aid2e/AID2E-framework/blob/main/examples/drich/workflow.yml)
- [PanDA Documentation](https://panda-wms.readthedocs.io/)
- [iDDS Documentation](https://idds.readthedocs.io/)
