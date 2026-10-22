# Scheduler Notes

See the [scheduler guide](../schedulers.md) for YAML settings, execution behavior, and troubleshooting.

## Python API

### Full Config

```python
from aid2e.utilities.configurations import load_config

# Load complete config including scheduler
config = load_config("examples/dtlz2/configurations/dtlz2_ax_slurm.yml")

# Access scheduler configuration
scheduler_cfg = config.scheduler
print(f"Runner type: {scheduler_cfg.runner_type}")
print(f"Max retries: {scheduler_cfg.max_retries}")

# Get validated runner-specific config
runner_cfg = scheduler_cfg.parse_runner_params()
print(f"Runner parameters: {runner_cfg}")
```

### Scheduler Config Only

```python
from aid2e.utilities.configurations.scheduler_config import SchedulerConfigLoader

scheduler_config = SchedulerConfigLoader.load("scheduler.yml")
runner_config = scheduler_config.parse_runner_params()
```

### Direct PanDA Config

```python
import yaml
from aid2e.schedulers.PanDAiDDS.config import PanDAiDDSRunnerConfig

# Load YAML (just PanDA parameters)
with open("panda.yml") as f:
    data = yaml.safe_load(f)

# Parse
panda_config = PanDAiDDSRunnerConfig(**data)
```
