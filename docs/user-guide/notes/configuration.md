# Configuration Notes

See the [configuration guide](../configuration.md) for setup, supported constraints, and candidate checks.

## Constraint Methods

`ParameterConstraint` provides these methods for direct use:

| Method | Purpose |
| --- | --- |
| `extract_parameter_names()` | Return the qualified parameter names in the rule. |
| `validate_syntax(valid_param_names)` | Check syntax and parameter names; return validity and an error message. |
| `evaluate(param_values)` | Check whether parameter values satisfy the rule. |

`AxOptimizer._parse_constraint_to_ax()` converts supported rules into Ax constraints. For example, `group.x + group.y >= 0.5` becomes `-group.x - group.y <= -0.5`. See the [optimizer guide](../optimizers.md#search-space-and-constraint-mapping) for backend behavior.
