#!/usr/bin/env python
"""Example demonstrating BaseOptimizer and AxOptimizer integration with DTLZ2.

This script shows how to:
1. Load optimizer configuration from YAML file
2. Define a search space using the new BaseOptimizer interface
3. Create an AxOptimizer instance
4. Run multi-objective optimization on DTLZ2 benchmark
5. Serialize and deserialize optimizer state

DTLZ2 is a multi-objective test problem with a known Pareto front.
For 2 objectives and M variables, the optimal solutions lie on the unit sphere.

Project: AID2E v0.0.0 - AI assisted Detector Design for EIC
Homepage: https://aid2e.github.io/aid2e-framework
Repository: https://github.com/aid2e/AID2E-framework.git
"""

import os
import json
import yaml
import numpy as np
from pathlib import Path
from aid2e.optimizers import BaseOptimizer, SearchSpace, AxOptimizer, AxOptimizerConfig
from aid2e.utilities.configurations import OptimizerConfiguration


def dtlz2(x_dict, n_objectives=2):
    """DTLZ2 multi-objective test problem.
    
    Args:
        x_dict: Dictionary of parameters (x1, x2, ..., x10)
        n_objectives: Number of objectives (default: 2)
    
    Returns:
        Dictionary with objective values {f1, f2, ...}
    
    Notes:
        For 2 objectives, the Pareto front lies on the unit circle.
        Optimal solutions have g(x) = 0, where g is the sum of squared
        deviations from 0.5 for decision variables after the first M-1.
    """
    # Convert dict to array
    x = np.array([x_dict[f'x{i+1}'] for i in range(len(x_dict))])
    k = len(x) - n_objectives + 1
    
    # g function (auxiliary function)
    g = np.sum((x[n_objectives-1:] - 0.5) ** 2)
    
    # Compute objectives
    objectives = {}
    for i in range(n_objectives):
        f = 1.0 + g
        for j in range(n_objectives - i - 1):
            f *= np.cos(x[j] * np.pi / 2.0)
        if i > 0:
            f *= np.sin(x[n_objectives - i - 1] * np.pi / 2.0)
        objectives[f'f{i+1}'] = f
    
    return objectives


def main():
    print("=" * 70)
    print("AID2E BaseOptimizer + AxOptimizer: DTLZ2 Example")
    print("=" * 70)
    
    # 1. Load configuration from YAML file
    print("\n1. Loading configuration from YAML file...")
    # Note: You can also use JSON format - just change the extension:
    config_path = Path(__file__).parent / "ax_dtlz2_config.json"
    with open(config_path, 'r') as f:
        config_data = json.load(f)
    # For YAML format:
    # config_path = Path(__file__).parent / "ax_dtlz2_config.yml"
    # with open(config_path, 'r') as f:
    #     config_data = yaml.safe_load(f)
    
    print(f"   Config file: {config_path.name}")
    print(f"   Problem: {config_data['name']}")
    
    # 2. Parse configuration using OptimizerConfiguration
    print("\n2. Parsing optimization configuration...")
    optimizer_payload = config_data.get("optimizer", config_data)
    opt_config = OptimizerConfiguration(**optimizer_payload)
    objective_names = config_data.get("objectives", [])
    n_iterations = config_data.get("n_iterations", 30)
    
    print(f"   Optimizer: {opt_config.name}")
    print(f"   Strategy: {opt_config.parameters.get('initialization_strategy', 'sobol')}")
    print(f"   Generator: {opt_config.parameters.get('generator', 'BOTORCH_MODULAR')}")
    
    # 3. Create AxOptimizerConfig from parsed parameters
    print("\n3. Creating AxOptimizerConfig...")
    optimizer_params = opt_config.parameters
    ax_config = AxOptimizerConfig(
        initialization_strategy=optimizer_params.get('initialization_strategy', 'sobol'),
        generator=optimizer_params.get('generator', 'BOTORCH_MODULAR'),
        generator_kwargs=optimizer_params.get('generator_kwargs', {}),
        generator_gen_kwargs=optimizer_params.get('generator_gen_kwargs', {}),
        objective_thresholds=optimizer_params.get('objective_thresholds'),
        n_initial_samples=optimizer_params.get('n_initial_samples', 10),
        n_iterations=n_iterations,
        batch_size=optimizer_params.get('batch_size', 3),
        seed=optimizer_params.get('seed', 42)
    )
    print(f"   Initial samples: {ax_config.n_initial_samples}")
    print(f"   Total iterations: {ax_config.n_iterations}")
    print(f"   Batch size: {ax_config.batch_size}")
    
    # 4. Define search space from configuration parameters
    print("\n4. Defining search space from configuration...")
    search_space_params = {}
    parameters = config_data.get('parameters', {})
    for param_name, param_config in parameters.items():
        search_space_params[param_name] = {
            "type": "range",
            "bounds": param_config["bounds"]
        }
    
    search_space = SearchSpace(parameters=search_space_params)
    print(f"   Parameters: {list(search_space.parameters.keys())}")
    print(f"   Total dimensions: {len(search_space.parameters)}")
    
    # 5. Create AxOptimizer instance
    print("\n5. Creating AxOptimizer...")
    optimizer = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=objective_names,
        seed=ax_config.seed
    )
    print(f"   Optimizer: {optimizer}")
    print(f"   Objectives: {objective_names}")
    print(f"   Inherits from BaseOptimizer: {isinstance(optimizer, BaseOptimizer)}")
    
    # 6. Run multi-objective optimization loop
    print("\n6. Running multi-objective optimization on DTLZ2...")
    n_iterations = 5
    
    for iteration in range(n_iterations):
        print(f"\n   Iteration {iteration + 1}/{n_iterations}:")
        
        # Suggest candidates
        candidates = optimizer.suggest_candidates(n_candidates=ax_config.batch_size)
        print(f"   - Suggested {len(candidates)} candidates")
        
        # Get current trial count before adding results
        trial_start_idx = len(optimizer.experiment.trials) - len(candidates)
        
        # Evaluate candidates using DTLZ2
        for idx, candidate in enumerate(candidates):
            # Evaluate DTLZ2
            objectives = dtlz2(candidate, n_objectives=len(objective_names))
            
            # Update optimizer with results
            trial_idx = trial_start_idx + idx
            optimizer.update_with_results(
                trial_index=trial_idx,
                parameters=candidate,
                metrics=objectives
            )
            
            # Display results
            x_vals = [f"{candidate[f'x{i+1}']:.3f}" for i in range(3)]  # Show first 3
            obj_vals = [f"{objectives[obj]:.4f}" for obj in objective_names]
            print(f"     Trial {trial_idx}: x=[{', '.join(x_vals)}, ...] → {dict(zip(objective_names, obj_vals))}")
    
    # 7. Get Pareto front
    print("\n7. Retrieving Pareto front...")
    pareto_front = optimizer.get_pareto_front()
    print(f"   Pareto front size: {len(pareto_front)}")
    
    if pareto_front:
        print("\n   Pareto-optimal solutions:")
        for i, trial in enumerate(pareto_front[:5]):  # Show first 5
            obj_vals = [f"{trial.metrics[obj]:.4f}" for obj in objective_names]
            print(f"     Solution {i+1}: {dict(zip(objective_names, obj_vals))}")
        
        if len(pareto_front) > 5:
            print(f"     ... and {len(pareto_front) - 5} more solutions")
    
    # 8. Get best trial (representative from Pareto front)
    print("\n8. Best trial (from Pareto front):")
    best_trial = optimizer.get_best_trial()
    if best_trial:
        print(f"   Objectives: {best_trial.metrics}")
        print(f"   (For DTLZ2, optimal Pareto front is on unit sphere)")
    
    # 9. Get all trials
    print(f"\n9. Total trials evaluated: {len(optimizer.get_trials())}")
    
    # 10. Serialize and deserialize state
    print("\n10. Testing state serialization...")
    state = optimizer.serialize_state()
    print(f"    Serialized state has {len(state['trials'])} trials")
    
    # Create new optimizer and load state
    optimizer2 = AxOptimizer(
        search_space=search_space,
        config=ax_config,
        objective_names=objective_names,
        seed=ax_config.seed
    )
    optimizer2.load_state(state)
    print(f"    Loaded state: {len(optimizer2.get_trials())} trials restored")
    
    pareto_front2 = optimizer2.get_pareto_front()
    print(f"    Pareto front after reload: {len(pareto_front2)} solutions")
    
    print("\n" + "=" * 70)
    print("DTLZ2 multi-objective optimization completed successfully!")
    print("=" * 70)


if __name__ == "__main__":
    main()
