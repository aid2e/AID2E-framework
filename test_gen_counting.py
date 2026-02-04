"""Test: Does gen(n=3) count as 3 trials or 1 for GenerationStrategy?"""
import sys
sys.path.insert(0, '/sciclone/home/ksuresh/scr10/AID2E-framework/src')

from ax.core.experiment import Experiment
from ax.core.search_space import SearchSpace
from ax.core.parameter import RangeParameter, ParameterType
from ax.generation_strategy.generation_strategy import GenerationStrategy, GenerationStep
from ax.modelbridge.registry import Generators
from ax.core.optimization_config import OptimizationConfig
from ax.core.objective import Objective
from ax.core.metric import Metric

# Create search space
search_space = SearchSpace([
    RangeParameter("x1", ParameterType.FLOAT, 0.0, 1.0),
])

# Create experiment
opt_config = OptimizationConfig(objective=Objective(metric=Metric(name="f1"), minimize=True))
exp = Experiment(name="test", search_space=search_space, optimization_config=opt_config)

# Create generation strategy
gs = GenerationStrategy([
    GenerationStep(model=Generators.SOBOL, num_trials=3),
    GenerationStep(model=Generators.BOTORCH_MODULAR, num_trials=-1),
])

print("Test 1: Calling gen(n=3) once")
print(f"  Step before: {gs.current_step_index}")
gr = gs.gen(exp, n=3)
print(f"  Generated {len(gr.arms)} arms")
print(f"  Step after: {gs.current_step_index}")
print(f"  Model used: {gr._model_key}")

print(f"\nTest 2: Calling gen(n=1) again after that")
gr2 = gs.gen(exp, n=1)
print(f"  Step after: {gs.current_step_index}")
print(f"  Model used: {gr2._model_key}")

print(f"\n❓ QUESTION: Does gen(n=3) count as 1 trial or 3 trials?")
print(f"  Answer: Still at step {gs.current_step_index} after gen(n=3) + gen(n=1)")
print(f"  This means gen(n=3) was counted as... {gs.current_step_index} transition")
