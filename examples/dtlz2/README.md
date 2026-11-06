# DTLZ2 Examples

[dtlz2_ax_joblib.yml](configurations/dtlz2_ax_joblib.yml) configures Ax optimization with 10 design variables, 2 minimized objectives, and JobLib execution.

The Ax/PyMOO JobLib and Ax Slurm configs use `problem.output_location` and `problem.work_location`; set absolute paths in the YAML. The CLI log is saved as `run.log` inside the run output directory. Slurm trial stdout/stderr are saved under `trials/trial_<index>/log/`; submission scripts and Python handoff files are under the run work directory. 

From the repository root:

```bash
aid2e describe examples/dtlz2/configurations/dtlz2_ax_joblib.yml
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib.yml --validate-only
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib.yml
```

See [configurations](configurations/) for optimization settings, [python_api](python_api/) for direct API examples, and [schedulers](schedulers/) for Slurm and PanDA examples. The [configuration guide](../../docs/user-guide/configuration.md) explains the supported schema.

[dtlz2_design.params](dtlz2_design.params) provides the shared unconstrained design with ten variables. [dtlz2_evaluator.py](dtlz2_evaluator.py) supports Python callables, direct `--x1` through `--x10` arguments, and `--design` JSON input. Inline evaluation uses the configured objective count; standalone evaluation uses `--n-objectives` (default: `2`). PanDA stage and dataset examples use a separate evaluator.

## Configuration examples

| Configuration | Feature |
| --- | --- |
| [dtlz2_ax_joblib.yml](configurations/dtlz2_ax_joblib.yml) | Bayesian optimization with local trial batches. |
| [dtlz2_ax_joblib.json](configurations/dtlz2_ax_joblib.json) | The same configuration in JSON. |
| [dtlz2_ax_slurm.yml](configurations/dtlz2_ax_slurm.yml) | Slurm trial submission with inline evaluation. |
| [dtlz2_ax_panda.yml](configurations/dtlz2_ax_panda.yml) | PanDA/iDDS callable submission. |
| [dtlz2_ax_constraints.yml](configurations/dtlz2_ax_constraints.yml) | Inline design parameters and linear Ax constraints. |
| [dtlz2_objective_collection.yml](configurations/dtlz2_objective_collection.yml) | Extract both objectives from one script execution. |
| [dtlz2_objective_plans.yml](configurations/dtlz2_objective_plans.yml) | Separate objective plans, script/inline steps, and dependencies. |
| [dtlz2_pymoo_joblib.yml](configurations/dtlz2_pymoo_joblib.yml) | NSGA-II population and offspring evaluation. |
| [dtlz2_scheduler_cascade.yml](configurations/dtlz2_scheduler_cascade.yml) | Global, workflow, branch, and stage scheduler precedence. |
| [dtlz2_sobol_joblib.yml](configurations/dtlz2_sobol_joblib.yml) | Sobol sampling without Bayesian generation. |

The Ax, PyMOO, and Sobol JobLib baselines share the same unconstrained design and 100-evaluation budget. Ax uses 20 initial Sobol samples followed by 80 Bayesian candidates, in batches of four. PyMOO uses a population of 20 followed by 20 generations of four offspring; its `n_iterations` counts generations. These are example settings, not a convergence or performance guarantee. Slurm and PanDA require site-specific setup before execution.

The Python optimizer scripts and notebook reuse the Ax/PyMOO JobLib configs, using only their problem and optimizer sections. Slurm design-JSON and PanDA multistage variants remain for separate review.
