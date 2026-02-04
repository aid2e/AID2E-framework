"""Test how Ax GenerationStrategy tracks trial counts."""
import sys
sys.path.insert(0, '/sciclone/home/ksuresh/scr10/AID2E-framework/src')

from ax.core.experiment import Experiment
from ax.core.search_space import SearchSpace
from ax.core.parameter import RangeParameter, ParameterType
from ax.modelbridge.generation_strategy import GenerationStrategy, GenerationStep
from ax.modelbridge.registry import Generators
from ax.core.optimization_config import OptimizationConfig
from ax.core.objective import Objective
from ax.core.metric import Metric

# Create search space
search_space = SearchSpace([
    RangeParameter("x1", ParameterType.FLOAT, 0.0, 1.0),
    RangeParameter("x2", ParameterType.FLOAT, 0.0, 1.0),
])

# Create experiment
opt_config = OptimizationConfig(objective=Objective(metric=Metric(name="f1"), minimize=True))
exp = Experiment(name="test", search_space=search_space, optimization_config=opt_config)

# Create generation strategy
gs = GenerationStrategy([
    GenerationStep(model=Generators.SOBOL, num_trials=3, max_parallelism=3),
    GenerationStep(model=Generators.BOTORCH_MODULAR, num_trials=-1, max_parallelism=3),
])

print("="*60)
print("Testing GenerationStrategy step transitions")
print("="*60)

print(f"\n📊 Initial state:")
print(f"  Current step: {gs.current_step_index}")
print(f"  Experiment trials: {len(exp.trials)}")
print(f"  Step 0: {gs._steps[0].model}, num_trials={gs._steps[0].num_trials}")
print(f"  Step 1: {gs._steps[1].model}, num_trials={gs._steps[1].num_trials}")

# Generate first batch (3 candidates)
print(f"\n🔷 Generating first batch (3 candidates):")
gr1 = gs.gen(exp, n=3)
print(f"  Generated {len(gr1.arms)} arms using {gr1._model_key}")
print(f"  Current step AFTER gen: {gs.current_step_index}")
print(f"  Experiment trials: {len(exp.trials)}")

# Create trials from generator_run
from ax.core.generator_run import GeneratorRun
for arm in gr1.arms:
    single_arm_gr = GeneratorRun(arms=[arm], weights=[1.0])
    single_arm_gr._model_key = gr1._model_key
    trial = exp.new_trial(generator_run=single_arm_gr)
    trial.mark_running(no_runner_required=True)

print(f"  Experiment trials AFTER creating trials: {len(exp.trials)}")
print(f"  Current step: {gs.current_step_index}")

# Mark trials as completed
from ax.core.data import Data
import pandas as pd
for trial_index in range(len(exp.trials)):
    trial = exp.trials[trial_index]
    trial.mark_completed()
    df = pd.DataFrame([{
        'trial_index': trial.index,
        'metric_name': 'f1',
        'arm_name': trial.arm.name,
        'mean': 0.5,
        'sem': 0.0
    }])
    exp.attach_data(Data(df=df))

print(f"  Experiment trials AFTER completion: {len(exp.trials)}")
print(f"  Current step AFTER completion: {gs.current_step_index}")

# Generate second batch (3 more candidates)
print(f"\n🔶 Generating second batch (3 candidates):")
gr2 = gs.gen(exp, n=3)
print(f"  Generated {len(gr2.arms)} arms using {gr2._model_key}")
print(f"  Current step AFTER gen: {gs.current_step_index}")

if gs.current_step_index == 1:
    print(f"\n✅ SUCCESS: Strategy transitioned from Sobol to GPEI!")
else:
    print(f"\n⚠️  WARNING: Strategy still at step {gs.current_step_index}")
    print(f"\nDEBUG INFO:")
    print(f"  Step 0 trials: {gs._steps[0].num_trials}")
    print(f"  Experiment has {len(exp.trials)} trials")
    print(f"  All trials completed: {all(t.status.is_completed for t in exp.trials)}")
