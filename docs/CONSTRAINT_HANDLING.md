# Constraint Handling in AID2E

This document explains the complete constraint workflow in the AID2E framework, from definition to enforcement.

## Overview

Constraints are handled through a three-layer architecture:

1. **DesignConfig** - Validates constraint syntax at configuration load time
2. **SearchSpace** - Stores validated constraints for optimizer use  
3. **Optimizer** - Enforces constraints during candidate generation (optimizer-specific)

## Architecture

### 1. Constraint Definition (DesignConfig)

Constraints are defined in the design configuration as expressions over parameters:

```yaml
design_parameters:
  tracker:
    parameters:
      thickness:
        value: 1.0
        bounds: [0.5, 2.0]
      radius:
        value: 5.0
        bounds: [3.0, 10.0]

parameter_constraints:
  - name: "thickness_radius_limit"
    rule: "tracker.thickness + tracker.radius <= 10.0"
  - name: "minimum_radius"
    rule: "tracker.radius >= 4.0"
```

### 2. Syntax Validation (DesignConfig)

When a `DesignConfig` is instantiated, constraints are automatically validated:

```python
from aid2e.utilities.configurations.design_config import DesignConfig

# This will validate all constraints
config = DesignConfig(**config_data)
```

**Validation checks:**
- ✅ Constraint rule is syntactically valid Python expression
- ✅ All parameter names referenced in the rule exist in the design
- ✅ Parameter names are properly qualified (e.g., `group.param`)

**Example errors caught:**

```python
# Unknown parameter
rule: "tracker.unknown + tracker.radius <= 10.0"  
# ERROR: Unknown parameters: tracker.unknown

# Invalid syntax
rule: "tracker.thickness +* tracker.radius <= 10.0"
# ERROR: Invalid syntax in constraint
```

### 3. Constraint Storage (SearchSpace)

Validated constraints are passed to the `SearchSpace`:

```python
from aid2e.optimizers.base import SearchSpace

# Create SearchSpace from validated DesignConfig
search_space = SearchSpace.from_design_config(design_config)

# Constraints are now stored in search_space.constraints
print(f"Constraints: {len(search_space.constraints)}")
```

### 4. Runtime Validation (SearchSpace)

The `SearchSpace` provides runtime constraint checking for non-Ax optimizers:

```python
# Check if parameter values satisfy constraints
param_values = {'tracker.thickness': 1.5, 'tracker.radius': 9.0}
is_valid, errors = search_space.validate(param_values)

if not is_valid:
    print(f"Constraint violations: {errors}")
```

### 5. Native Enforcement (Ax Optimizer)

The Ax optimizer converts constraints to Ax's native `ParameterConstraint` format:

```python
from aid2e.optimizers.ax.optimizer import AxOptimizer
from aid2e.optimizers.ax.config import AxOptimizerConfig

# Create optimizer with constraints
ax_config = AxOptimizerConfig(
    name="constrained_opt",
    n_initial_samples=10,
    model_type="SOBOL",
    objectives=["minimize:objective"]
)

optimizer = AxOptimizer(
    search_space=search_space,
    config=ax_config,
    objective_names=["objective"]
)

# Ax automatically enforces constraints during generation
candidates = optimizer.suggest_candidates(n_candidates=5)
# All candidates will satisfy constraints!
```

## Constraint Format

### Supported Operators

- `<=` - Less than or equal (upper bound)
- `<` - Less than (strict upper bound)
- `>=` - Greater than or equal (lower bound, converted to upper bound internally)
- `>` - Greater than (strict lower bound, converted to upper bound internally)

### Linear Constraints

Currently, only **linear constraints** are supported:

```python
# ✅ Valid: Simple sum with upper bound
rule: "group.x + group.y <= 1.5"

# ✅ Valid: Weighted sum
rule: "group.x + 2.0 * group.y <= 3.0"

# ✅ Valid: Lower bound (converted internally)
rule: "group.x + group.y >= 0.5"

# ❌ Not supported: Non-linear constraints
rule: "group.x * group.y <= 1.0"
rule: "group.x ** 2 + group.y ** 2 <= 1.0"
```

### Parameter Names

Parameter names must be fully qualified with group prefix:

```python
# ✅ Valid: Qualified names
rule: "tracker.thickness + magnet.radius <= 10.0"

# ❌ Invalid: Unqualified names
rule: "thickness + radius <= 10.0"
```

## Implementation Details

### ParameterConstraint Methods

The `ParameterConstraint` class provides three key methods:

#### 1. `extract_parameter_names() -> Set[str]`

Extracts all qualified parameter names from the constraint rule:

```python
constraint = ParameterConstraint(
    name="example",
    rule="tracker.x + magnet.y + detector.z <= 10.0"
)

param_names = constraint.extract_parameter_names()
# Returns: {'tracker.x', 'magnet.y', 'detector.z'}
```

#### 2. `validate_syntax(valid_param_names: Set[str]) -> Tuple[bool, Optional[str]]`

Validates constraint syntax and parameter existence:

```python
valid_params = {'tracker.x', 'magnet.y', 'detector.z'}
is_valid, error_msg = constraint.validate_syntax(valid_params)

if not is_valid:
    print(f"Validation error: {error_msg}")
```

#### 3. `evaluate(param_values: Dict[str, Any]) -> bool`

Evaluates constraint at runtime:

```python
param_values = {'tracker.x': 3.0, 'magnet.y': 4.0, 'detector.z': 2.0}
is_satisfied = constraint.evaluate(param_values)
# Returns: True (3.0 + 4.0 + 2.0 = 9.0 <= 10.0)
```

### Ax Constraint Conversion

The Ax optimizer converts constraint rules to Ax's `ParameterConstraint` format:

```python
# Design constraint
rule: "group.x + group.y <= 1.5"

# Converted to Ax ParameterConstraint
ax_constraint = ParameterConstraint(
    constraint_dict={'group.x': 1.0, 'group.y': 1.0},
    bound=1.5
)
```

**Conversion logic:**
1. Parse constraint rule to extract parameters and coefficients
2. Create `constraint_dict` mapping parameter names to coefficients
3. Extract bound value
4. Handle `>=` and `>` by negating coefficients and bound

Example conversion:

```python
# Original: x + y >= 0.5
# Converted: -x - y <= -0.5
ax_constraint = ParameterConstraint(
    constraint_dict={'x': -1.0, 'y': -1.0},
    bound=-0.5
)
```

## Testing

Comprehensive tests verify constraint handling at all levels:

### Syntax Validation Tests

```python
def test_valid_constraint_accepted():
    """Valid constraints are accepted."""
    # Test with: "group.x + group.y <= 1.5"
    
def test_unknown_parameter_rejected():
    """Constraints with unknown parameters are rejected."""
    # Test with: "group.x + group.unknown <= 1.0"
    
def test_syntax_error_rejected():
    """Constraints with invalid syntax are rejected."""
    # Test with: "group.x +* 1.0"
```

### Runtime Validation Tests

```python
def test_evaluate_constraint():
    """Test runtime constraint evaluation."""
    constraint = ParameterConstraint(
        name="sum_limit",
        rule="group.x + group.y <= 1.5"
    )
    
    # Satisfies constraint
    assert constraint.evaluate({'group.x': 0.5, 'group.y': 0.8}) is True
    
    # Violates constraint
    assert constraint.evaluate({'group.x': 1.0, 'group.y': 0.6}) is False
```

### Ax Enforcement Tests

```python
def test_ax_enforces_constraints():
    """Test that Ax enforces constraints during generation."""
    # Generate 20 candidates with constraint: x + y <= 1.5
    candidates = optimizer.suggest_candidates(n_candidates=20)
    
    # Verify ALL candidates satisfy constraint
    for candidate in candidates:
        assert candidate['x'] + candidate['y'] <= 1.5
```

## Best Practices

### 1. Define Constraints Early

Validate constraints at configuration time to catch errors early:

```python
# ✅ Good: Errors caught immediately
try:
    config = DesignConfig(**config_data)
except ValidationError as e:
    print(f"Invalid constraints: {e}")
```

### 2. Use Qualified Names

Always use fully qualified parameter names:

```python
# ✅ Good
rule: "tracker.thickness + magnet.radius <= 10.0"

# ❌ Bad
rule: "thickness + radius <= 10.0"
```

### 3. Keep Constraints Linear

Stick to linear constraints for Ax compatibility:

```python
# ✅ Supported
rule: "a + 2*b + 3*c <= 10.0"

# ❌ Not supported
rule: "a * b <= 5.0"
rule: "a ** 2 + b ** 2 <= 1.0"
```

### 4. Test Constraint Enforcement

Always verify constraints are enforced:

```python
# Generate candidates
candidates = optimizer.suggest_candidates(n_candidates=100)

# Verify constraints
for candidate in candidates:
    is_valid, errors = search_space.validate(candidate)
    assert is_valid, f"Constraint violation: {errors}"
```

## Limitations

### Current Limitations

1. **Linear constraints only** - Non-linear constraints (products, powers) not supported
2. **Simple operators** - Only `+`, `-`, `*` (with constants), `<=`, `>=`, `<`, `>`
3. **Ax-specific** - Full native constraint support only for Ax optimizer

### Future Enhancements

Potential improvements:
- Support for non-linear constraints (via penalty methods or constraint-aware sampling)
- More complex expressions (absolute values, min/max, etc.)
- Constraint propagation and simplification
- Automatic constraint tightening based on feasibility

## Example: Complete Workflow

Here's a complete example showing the entire constraint workflow:

```python
from aid2e.utilities.configurations.design_config import DesignConfig
from aid2e.optimizers.base import SearchSpace
from aid2e.optimizers.ax.optimizer import AxOptimizer
from aid2e.optimizers.ax.config import AxOptimizerConfig

# 1. Define design with constraints
config_data = {
    "design_parameters": {
        "tracker": {
            "parameters": {
                "thickness": {"value": 1.0, "bounds": [0.5, 2.0]},
                "radius": {"value": 5.0, "bounds": [3.0, 10.0]},
            }
        }
    },
    "parameter_constraints": [
        {"name": "total_limit", "rule": "tracker.thickness + tracker.radius <= 10.0"},
        {"name": "min_radius", "rule": "tracker.radius >= 4.0"}
    ]
}

# 2. Create and validate DesignConfig
design_config = DesignConfig(**config_data)
print(f"✅ Config validated with {len(design_config.parameter_constraints)} constraints")

# 3. Create SearchSpace
search_space = SearchSpace.from_design_config(design_config)
print(f"✅ SearchSpace created with {len(search_space.constraints)} constraints")

# 4. Create optimizer
ax_config = AxOptimizerConfig(
    name="constrained_optimization",
    n_initial_samples=10,
    model_type="SOBOL",
    objectives=["objective"]
)

optimizer = AxOptimizer(
    search_space=search_space,
    config=ax_config,
    objective_names=["objective"]
)
print("✅ Optimizer created with native constraint enforcement")

# 5. Generate candidates (constraints automatically enforced!)
candidates = optimizer.suggest_candidates(n_candidates=20)
print(f"✅ Generated {len(candidates)} candidates")

# 6. Verify constraints (optional - Ax already enforces them)
violations = 0
for i, candidate in enumerate(candidates):
    thickness = candidate['tracker.thickness']
    radius = candidate['tracker.radius']
    
    # Check constraint 1: thickness + radius <= 10.0
    if thickness + radius > 10.0:
        violations += 1
        print(f"❌ Candidate {i}: total={thickness + radius:.2f} > 10.0")
    
    # Check constraint 2: radius >= 4.0
    if radius < 4.0:
        violations += 1
        print(f"❌ Candidate {i}: radius={radius:.2f} < 4.0")

if violations == 0:
    print("✅ All candidates satisfy constraints!")
else:
    print(f"⚠️ Found {violations} constraint violations")
```

## See Also

- [DesignConfig API Documentation](api-reference/utilities.md)
- [SearchSpace API Documentation](api-reference/optimizers.md)
- [AxOptimizer API Documentation](api-reference/optimizers.md)
- [Test Suite](https://github.com/aid2e/AID2E-framework/blob/main/tests/test_optimizers/test_constraint_integration.py)
