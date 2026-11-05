# DTLZ2 Examples

[dtlz2_ax_joblib.yml](configurations/dtlz2_ax_joblib.yml) configures Ax optimization with 10 design variables, 2 minimized objectives, and JobLib execution.

From the repository root:

```bash
aid2e describe examples/dtlz2/configurations/dtlz2_ax_joblib.yml
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib.yml --validate-only
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib.yml
```

See [configurations](configurations/) for optimization settings, [python_api](python_api/) for direct API examples, and [schedulers](schedulers/) for Slurm and PanDA examples. The [configuration guide](../../docs/user-guide/configuration.md) explains the supported schema.

[dtlz2_design.params](dtlz2_design.params) provides the shared unconstrained design with ten variables. [dtlz2_evaluator.py](dtlz2_evaluator.py) supports Python callables, direct `--x1` through `--x10` arguments, and `--design` JSON input. PanDA stage and dataset examples use a separate evaluator.

## Configuration examples

| Configuration | Feature |
| --- | --- |
| [dtlz2_ax_joblib.yml](configurations/dtlz2_ax_joblib.yml) | Bayesian optimization with local trial batches. |
| [dtlz2_ax_joblib.json](configurations/dtlz2_ax_joblib.json) | The same configuration in JSON. |
| [dtlz2_ax_slurm.yml](configurations/dtlz2_ax_slurm.yml) | Slurm submission and command-based evaluation. |
| [dtlz2_ax_panda.yml](configurations/dtlz2_ax_panda.yml) | PanDA/iDDS callable submission. |
| [dtlz2_ax_constraints.yml](configurations/dtlz2_ax_constraints.yml) | Inline design parameters and linear Ax constraints. |
| [dtlz2_objective_collection.yml](configurations/dtlz2_objective_collection.yml) | Extract both objectives from one script execution. |
| [dtlz2_objective_plans.yml](configurations/dtlz2_objective_plans.yml) | Separate objective plans, script/inline steps, and dependencies. |
| [dtlz2_pymoo_joblib.yml](configurations/dtlz2_pymoo_joblib.yml) | NSGA-II population and offspring evaluation. |
| [dtlz2_scheduler_cascade.yml](configurations/dtlz2_scheduler_cascade.yml) | Global, workflow, branch, and stage scheduler precedence. |
| [dtlz2_sobol_joblib.yml](configurations/dtlz2_sobol_joblib.yml) | Sobol sampling without Bayesian generation. |
| [dtlz2_ax_joblib_kb.yml](configurations/dtlz2_ax_joblib_kb.yml) | Warm start from, and upload to, an AgenticWF knowledge base. |
| [dtlz2_ax_panda_kb.yml](configurations/dtlz2_ax_panda_kb.yml) | PanDA/iDDS submission with KB warm start and upload. |

## KB warm start

[dtlz2_ax_joblib_kb.yml](configurations/dtlz2_ax_joblib_kb.yml) takes the first 10 of its 20 initial samples from the best trials of similar past runs stored in an AgenticWF knowledge base, and uploads every run back to it. The first run starts cold (the KB has no history yet), and later runs start from the points it stored.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[kb]'
source setup_aid2e.sh            # activates .venv, puts the repository root on PYTHONPATH

# The KB behind the AgenticWF server; the clients discover the sign-in settings from it
export AGENTICWF_KB_URL=https://aipanda107.cern.ch/app/kb
agenticwf login                  # or, for scripts: export AGENTICWF_TOKEN=pat_...
# (a standalone KB instead: AGENTICWF_KB_URL=http://127.0.0.1:8766/kb and its AGENTICWF_KB_TOKEN)

aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib_kb.yml   # creates the KB, cold start, uploads the run
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_joblib_kb.yml   # warm start from the first run
agenticwf kb list                                                     # the KB, as u:<username>:aid2e-dtlz2
```

The first run creates the records KB named by `upload_kb_id` when it does not exist, and later runs reuse it. `aid2e-dtlz2` is a bare slug, one of your own KBs. A `g:<group>:<slug>` ref creates a group KB instead, which needs a group admin. Set `create_upload_kb: false` to require an existing KB.

[dtlz2_ax_panda_kb.yml](configurations/dtlz2_ax_panda_kb.yml) does the same with PanDA/iDDS submission (site setup as for [dtlz2_ax_panda.yml](configurations/dtlz2_ax_panda.yml)). It uses the same `aid2e-dtlz2` KB, so JobLib and PanDA runs warm-start each other; its uploads carry `metadata.scheduler: panda`, which a `filter` can select on. It leaves `seed` unset, so a warm run's Sobol points differ from earlier runs instead of repeating them.

```bash
aid2e optimize examples/dtlz2/configurations/dtlz2_ax_panda_kb.yml
```

Warm-started trials carry `ax_model_key: kb_warm_start` and their source (`kb_source`) in `optimization_results.json`. The KB needs the `hpo` records plugin (`[records] plugins = hpo` in kb.cfg).

The Ax, PyMOO, and Sobol JobLib baselines share the same unconstrained design and 100-evaluation budget. Ax uses 20 initial Sobol samples followed by 80 Bayesian candidates, in batches of four. PyMOO uses a population of 20 followed by 20 generations of four offspring; its `n_iterations` counts generations. These are example settings, not a convergence or performance guarantee. Slurm and PanDA require site-specific setup before execution.

The Python optimizer scripts and notebook reuse the Ax/PyMOO JobLib configs, using only their problem and optimizer sections. Slurm design-JSON and PanDA multistage variants remain for separate review.
