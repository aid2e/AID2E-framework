"""Quick validation that Ax showcase will work with strategy tracking."""

import sys
sys.path.insert(0, '/sciclone/home/ksuresh/scr10/AID2E-framework/src')

from aid2e.optimizers.ax import AxOptimizer, AxOptimizerConfig
from aid2e.optimizers.base import SearchSpace

print("✓ Imports successful")

# Create search space
search_space = SearchSpace(
    parameters={
        "x1": {"type": "range", "bounds": [0.0, 1.0]},
        "x2": {"type": "range", "bounds": [0.0, 1.0]},
        "x3": {"type": "range", "bounds": [0.0, 1.0]},
    }
)
print(f"✓ SearchSpace created: {len(search_space.parameters)} parameters")

# Create config with small n_initial_samples for testing
config = AxOptimizerConfig(
    initialization_strategy="sobol",
    n_initial_samples=3,  # Small for testing
    batch_size=3,
    surrogate_model="saasbo",
    acquisition_function="qnehvi",
    seed=42,
)
print(f"✓ AxOptimizerConfig created: {config.initialization_strategy}, n_initial={config.n_initial_samples}")

# Create optimizer
optimizer = AxOptimizer(
    search_space=search_space,
    config=config,
    objective_names=["f1", "f2"],
    seed=42,
)
print(f"✓ AxOptimizer created: {optimizer}")

# Check initial state
print(f"\n📊 Initial State:")
print(f"  Current step: {optimizer.generation_strategy.current_step_index}")
print(f"  Step 0: {optimizer.generation_strategy._steps[0].model}, num_trials={optimizer.generation_strategy._steps[0].num_trials}")
print(f"  Step 1: {optimizer.generation_strategy._steps[1].model}, num_trials={optimizer.generation_strategy._steps[1].num_trials}")

# Sobol phase: Suggest 3 candidates (should use Sobol)
print(f"\n🔷 Sobol Phase (first 3 trials):")
print(f"  Experiment trials before: {len(optimizer.experiment.trials)}")
candidates1 = optimizer.suggest_candidates(n_candidates=3)
print(f"  ✓ Suggested {len(candidates1)} candidates")
print(f"  Experiment trials after: {len(optimizer.experiment.trials)}")
print(f"  Current step after gen: {optimizer.generation_strategy.current_step_index}")
for i, c in enumerate(candidates1):
    print(f"    {i+1}. x1={c['x1']:.4f}, x2={c['x2']:.4f}, x3={c['x3']:.4f}")

# Update with fake results
for i, design_point in enumerate(candidates1):
    fake_results = {"f1": 0.5 + i*0.1, "f2": 0.3 - i*0.05}
    optimizer.update_with_results(i, design_point, fake_results)
    print(f"  ✓ Updated trial {i}: f1={fake_results['f1']:.3f}, f2={fake_results['f2']:.3f}")

print(f"  Current step after updates: {optimizer.generation_strategy.current_step_index}")
print(f"  Experiment trials: {len(optimizer.experiment.trials)}")

# Bayesian phase: Suggest 3 more candidates (should switch to SAASBO)
print(f"\n🔶 Bayesian Phase (next 3 trials):")
print(f"  Experiment trials before: {len(optimizer.experiment.trials)}")
candidates2 = optimizer.suggest_candidates(n_candidates=3)
print(f"  ✓ Suggested {len(candidates2)} candidates")
print(f"  Experiment trials after: {len(optimizer.experiment.trials)}")
print(f"  Current step after gen: {optimizer.generation_strategy.current_step_index}")
for i, c in enumerate(candidates2):
    print(f"    {i+1}. x1={c['x1']:.4f}, x2={c['x2']:.4f}, x3={c['x3']:.4f}")

# Update with fake results
for i, design_point in enumerate(candidates2):
    trial_idx = 3 + i
    fake_results = {"f1": 0.4 - i*0.05, "f2": 0.6 + i*0.1}
    optimizer.update_with_results(trial_idx, design_point, fake_results)
    print(f"  ✓ Updated trial {trial_idx}: f1={fake_results['f1']:.3f}, f2={fake_results['f2']:.3f}")

print(f"  Current step after updates: {optimizer.generation_strategy.current_step_index}")

# Summary
print(f"\n📈 Summary:")
print(f"  Total trials: {len(optimizer.get_trials())}")
print(f"  Experiment trials: {len(optimizer.experiment.trials)}")
print(f"  Current generation step: {optimizer.generation_strategy.current_step_index}")
print(f"  Expected: Step 0 (Sobol) for first 3, Step 1 (SAASBO) for rest")
print(f"  Pareto front size: {len(optimizer.get_pareto_front())}")

# Verify transition happened
if optimizer.generation_strategy.current_step_index == 1:
    print(f"\n✅ SUCCESS: Strategy correctly transitioned from Sobol to SAASBO!")
else:
    print(f"\n⚠️  WARNING: Strategy still at step {optimizer.generation_strategy.current_step_index}")
    print(f"  This suggests the transition did not happen correctly.")

print(f"\n✅ All Ax optimizer operations complete!")
