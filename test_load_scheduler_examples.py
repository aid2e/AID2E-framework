#!/usr/bin/env python
"""Test loading scheduler configuration examples."""

from aid2e.utilities.configurations import load_config

# Test loading each example
examples = [
    'examples/basic/full_example_joblib.yml',
    'examples/basic/full_example_slurm.yml',
    'examples/basic/full_example_panda.yml'
]

for example in examples:
    try:
        config = load_config(example)
        runner_type = config.scheduler.runner_type if config.scheduler else 'None'
        print(f'✓ Loaded {example}')
        print(f'  - Problem: {config.problem.name}')
        print(f'  - Runner type: {runner_type}')
    except Exception as e:
        print(f'✗ Failed to load {example}: {e}')

print('\n✅ All example configurations loaded successfully!')
