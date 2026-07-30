# PanDAiDDS Scheduler YAML Configuration Guide

This guide explains how to configure the PanDAiDDS scheduler using YAML files in the AID2E framework.

## Quick Start

### Minimal Configuration

```yaml
scheduler:
  runner_type: "PanDAiDDSRunner"
  parameters:
    cloud: "US"
    queue: "BNL_PanDA_1"
    max_walltime: 3600
    core_count: 1
    total_memory: 2000
  output_location: "./panda_output"
```

The `name` field will be auto-generated as `user.<username>.aid2e_job`.

### Full Configuration

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
  max_retries: 3
  output_location: "./panda_output"
  monitor_interval: 120
```

## Configuration Fields

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `cloud` | string | PanDA cloud/region (e.g., "US", "EU") |
| `queue` | string | PanDA queue name (e.g., "BNL_PanDA_1") |

### Optional Fields

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

### Default Excluded Files

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

## Auto-Generated Fields

### Name Auto-Generation

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

### Source Directory Auto-Setting

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

### Environment Initialization Auto-Setting

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

## Loading Configurations

### Method 1: Full Config (Recommended)

```python
from aid2e.utilities.configurations.full_config import load_config

# Load complete configuration
config = load_config("config.yml")

# Access scheduler config
scheduler_config = config.scheduler
panda_config = scheduler_config.parse_runner_params()

print(panda_config.name)
print(panda_config.cloud)
```

### Method 2: Scheduler Config Only

```python
import yaml
from aid2e.utilities.configurations.scheduler_config import SchedulerConfiguration

# Load YAML
with open("scheduler.yml") as f:
    data = yaml.safe_load(f)

# Parse
scheduler_config = SchedulerConfiguration(**data)
panda_config = scheduler_config.parse_runner_params()
```

### Method 3: Direct PanDA Config

```python
import yaml
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig

# Load YAML (just PanDA parameters)
with open("panda.yml") as f:
    data = yaml.safe_load(f)

# Parse
panda_config = PanDAiDDSRunnerConfig(**data)
```

## Complete Example

See [`examples/panda_scheduler_config.yml`](panda_scheduler_config.yml) for complete examples including:
- Minimal configuration
- Full configuration with all fields
- Environment variable usage
- Integration with optimizer and problem configs

See [`examples/panda_yaml_loading_example.py`](panda_yaml_loading_example.py) for Python code examples.

## PanDA Queues

Common PanDA queues:

- `BNL_PanDA_1` - Brookhaven National Laboratory
- `ORNL_Frontier` - Oak Ridge National Laboratory
- `NERSC_Perlmutter` - NERSC Perlmutter supercomputer

Contact your PanDA administrator for available queues in your cloud.

## Validation

The configuration is validated via Pydantic models:
- Type checking
- Field validation
- Name format validation (must start with `user.`)
- Required field checks

Invalid configurations will raise `ValidationError` with detailed messages.

## See Also

- [PanDA Documentation](https://panda-wms.readthedocs.io/)
- [iDDS Documentation](https://idds.readthedocs.io/)
- [AID2E Documentation](https://aid2e.github.io/AID2E-framework)
