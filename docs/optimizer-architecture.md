# AID2E Optimizer Architecture

## Overview

The AID2E framework implements a modular optimizer architecture that supports multiple optimization algorithms through a common `BaseOptimizer` interface. This design enables:

- **Modularity**: Easy addition of new optimizer backends
- **Consistency**: Common API across all optimizers
- **Distributed execution**: State serialization for distributed optimization
- **Extensibility**: Support for custom optimizer implementations

## Architecture

### BaseOptimizer Abstract Class

Located in `src/aid2e/optimizers/base.py`, `BaseOptimizer` defines the common interface:

```python
class BaseOptimizer(ABC):
    """Abstract base class for all optimizers."""
    
    @abstractmethod
    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        """Suggest next parameter configurations to evaluate."""
        pass
    
    @abstractmethod
    def update_with_results(self, trial_index: int, parameters: Dict[str, Any], 
                           metrics: Dict[str, float]) -> None:
        """Update optimizer with evaluation results."""
        pass
    
    @abstractmethod
    def get_pareto_front(self) -> List[Trial]:
        """Get Pareto-optimal solutions."""
        pass
    
    @abstractmethod
    def get_trials(self) -> List[Trial]:
        """Get all evaluated trials."""
        pass
    
    @abstractmethod
    def get_best_trial(self) -> Optional[Trial]:
        """Get the best trial found."""
        pass
    
    @abstractmethod
    def serialize_state(self) -> Dict[str, Any]:
        """Serialize optimizer state for distributed execution."""
        pass
    
    @abstractmethod
    def load_state(self, state: Dict[str, Any]) -> None:
        """Load optimizer state from serialized form."""
        pass
```

### AxOptimizer Implementation

`AxOptimizer` (`src/aid2e/optimizers/ax_optimizer.py`) implements `BaseOptimizer` using the Ax platform:

- **Initialization**: Sobol quasi-random sampling
- **Surrogate model**: SAASBO (Sparse Axis-Aligned Subspace Bayesian Optimization)
- **Acquisition function**: qNEHVI (Noisy Expected Hypervolume Improvement)
- **Multi-objective**: Native support for Pareto optimization

#### Integration with AxOptimizerConfig

```python
from aid2e.optimizers import BaseOptimizer, SearchSpace, AxOptimizer
from aid2e.utilities.configurations import AxOptimizerConfig

# Create configuration
config = AxOptimizerConfig(
    initialization_strategy="sobol",
    surrogate_model="saasbo",
    acquisition_function="qnehvi",
    n_initial_samples=10,
    n_iterations=50,
    batch_size=5,
    seed=42
)

# Define search space
search_space = SearchSpace(
    parameters={
        "x": {"type": "range", "bounds": [0.0, 1.0]},
        "y": {"type": "range", "bounds": [-1.0, 1.0]}
    }
)

# Create optimizer
optimizer = AxOptimizer(
    search_space=search_space,
    config=config,
    objective_names=["loss", "time"]
)
```

## Usage Example

### Basic Optimization Loop

```python
# Suggest candidates
candidates = optimizer.suggest_candidates(n_candidates=5)

# Evaluate candidates (user implements evaluation)
for idx, candidate in enumerate(candidates):
    metrics = evaluate_candidate(candidate)  # User function
    
    optimizer.update_with_results(
        trial_index=idx,
        parameters=candidate,
        metrics=metrics
    )

# Get best result
best_trial = optimizer.get_best_trial()
print(f"Best parameters: {best_trial.parameters}")
print(f"Best metrics: {best_trial.metrics}")
```

### State Serialization for Distributed Execution

```python
# Save optimizer state
state = optimizer.serialize_state()
import json
with open('optimizer_state.json', 'w') as f:
    json.dump(state, f)

# Load optimizer state on another worker
optimizer2 = AxOptimizer(
    search_space=search_space,
    config=config,
    objective_names=["loss", "time"]
)

with open('optimizer_state.json', 'r') as f:
    state = json.load(f)
optimizer2.load_state(state)

# Continue optimization
candidates = optimizer2.suggest_candidates(n_candidates=5)
```

## Adding New Optimizers

To add a new optimizer (e.g., NSGA-II, Hyperopt):

1. Create a new file in `src/aid2e/optimizers/` (e.g., `nsga2_optimizer.py`)
2. Implement `BaseOptimizer` abstract methods
3. Create a corresponding configuration class in `src/aid2e/utilities/configurations/`
4. Register the configuration in `optimization_registry.py`
5. Add tests in `tests/test_optimizers/`

Example skeleton:

```python
from aid2e.optimizers.base import BaseOptimizer, SearchSpace, Trial

class NSGA2Optimizer(BaseOptimizer):
    def __init__(self, search_space: SearchSpace, config, objective_names: List[str]):
        super().__init__(search_space, len(objective_names))
        # Initialize NSGA-II specific components
        
    def suggest_candidates(self, n_candidates: int = 1) -> List[Dict[str, Any]]:
        # Implement using NSGA-II mutation/crossover
        pass
    
    def update_with_results(self, trial_index: int, parameters: Dict[str, Any],
                           metrics: Dict[str, float]) -> None:
        # Update population with new individual
        pass
    
    # ... implement other abstract methods
```

## Data Classes

### SearchSpace

Defines the parameter search space:

```python
from aid2e.optimizers import SearchSpace

search_space = SearchSpace(
    parameters={
        "x": {"type": "range", "bounds": [0.0, 1.0]},
        "y": {"type": "range", "bounds": [-1.0, 1.0]},
        "z": {"type": "choice", "values": ["a", "b", "c"]}
    }
)
```

### Trial

Represents a single optimization trial:

```python
from aid2e.optimizers import Trial

trial = Trial(
    index=0,
    parameters={"x": 0.5, "y": 0.3},
    metrics={"loss": 0.1, "accuracy": 0.9},
    status="completed",
    metadata={"worker_id": 1}
)
```

## Testing

Run tests for the optimizer architecture:

```bash
# All optimizer tests
pytest tests/test_optimizers/ -v

# Base optimizer integration tests
pytest tests/test_optimizers/test_base_optimizer_integration.py -v

# Configuration tests
pytest tests/test_utilities/test_configurations/test_ax_config_loading.py -v
```

Run the example:

```bash
python examples/basic/ax_optimizer_example.py
```

## Requirements

- Python >=3.10
- ax-platform==1.0.0
- pydantic>=2.0

For installation:

```bash
pip install ax-platform==1.0.0
```

## Project Information

- **Project**: AID2E v0.0.1 - AI assisted Detector Design for EIC
- **Homepage**: https://aid2e.github.io/aid2e
- **Repository**: https://github.com/aid2e/AID2E-framework.git
- **Documentation**: https://aid2e.github.io/AID2E-framework
