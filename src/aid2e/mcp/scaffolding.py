"""Tested integration mechanics, deliberately generic demonstration mathematics."""
import re


def verification_contract() -> dict:
    """Public interfaces for producing and checking evidence for one managed run."""
    return {
        "pytest_fixture": (
            "from aid2e.mcp.verification import run_local_optimization\n"
            "record = run_local_optimization(str(root), 'examples/demo/config.yml', ['tests/demo'])\n"
            "run_id = record['run_id']\n"
            "results = json.loads(Path(record['artifacts']['optimization_results.json']).read_text())\n"
            "front = json.loads(Path(record['artifacts']['pareto_front.json']).read_text())"
        ),
        "results": {
            "optimization_results.json": "Object with a trials array.",
            "pareto_front.json": "Array of sampled non-dominated trial records.",
            "trial_fields": ["trial_index", "design_parameters", "objectives", "metadata.ax_node_name"],
        },
        "cli_output": (
            "When a test explicitly requires CLI output under pytest tmp_path, run "
            "aid2e optimize CONFIG --output TMP_PATH --run-id cli and read TMP_PATH/cli/optimization_results.json. "
            "Keep the requested trial budget and assert its generation phases. "
            "Use the managed fixture for evidence linked to MCP acceptance."
        ),
        "device": (
            "In reconstruction, import record_diagnostic from aid2e.mcp.verification and call "
            "record_diagnostic(output_dir, 'reconstruction_device', str(tensor.device)) on the tensor used. "
            "Each trial then has diagnostics/reconstruction_device.json with name and value fields."
        ),
        "verification_requirements_example": {
            "expected_trials": 12,
            "min_pareto_points": 3,
            "require_model_based": True,
            "require_device": True,
            "require_artifacts": True,
        },
        "workflow": [
            "Finish source, tests, artifact producers and README before final pytest. "
            "Pass the whole test directory and any dynamic dependencies in source_paths.",
            "Run run_workspace_tests on the whole test directory. Use the run_id printed under "
            "'Managed run IDs created by this pytest invocation'. Keep one shared fixture for the acceptance run. "
            "A pytest execution ID is a different identifier.",
            "Call get_verification_report(run_id, requirements) to inspect checks, pytest and derived_artifacts. "
            "If changes made the run stale, rerun integrated pytest and use the new run ID.",
            "Build every requested plot or summary from record['artifacts'] for that same run. After writing "
            "each file, the producer calls write_artifact_provenance(str(root), run_id, str(path)) "
            "from aid2e.mcp.verification to create its matching .provenance.json sidecar.",
            "Call finalize_optimization_run with run_id, expected_trials, artifact_paths, min_pareto_points, "
            "require_model_based and require_device as applicable. Use JSON numbers and booleans. "
            "Report completion only when completion_allowed is true.",
        ],
        "tool_roles": {
            "verify_optimization_run": "Independent saved-result checks. Each check has status and detail.",
            "get_verification_report": "Current result, pytest and artifact evidence for the same run.",
            "finalize_optimization_run": "Strict acceptance including pytest source coverage and producer provenance.",
        },
    }


def integration_contract() -> dict:
    """Canonical runnable interfaces, shared with the actual example generator."""
    files = scaffold_files("demo")
    return {
        "inline_call": "def geometry(*, design_point, **kwargs): ...; def simulate(*, inputs, **kwargs): ...",
        "parameter_key": "design_point['demo.x']; dependencies are inputs['geometry'], never fallback searches",
        "runner": "from aid2e.mcp.verification import run_local_optimization, verify_run\n"
                  "record = run_local_optimization(str(root), 'examples/demo/config.yml', ['tests/demo'])\n"
                  "run_id = record['run_id']\n"
                  "results = json.loads(Path(record['artifacts']['optimization_results.json']).read_text())\n"
                  "# Returns a record dict, NOT (run_id, results). This invokes the real CLI.",
        "trial_fields": ["trial_index", "design_parameters", "objectives", "metadata.ax_node_name"],
        "cli": "aid2e optimize examples/demo/config.yml  # positional config; no --config or --params",
        "requirements_example": {"expected_trials": 12, "min_pareto_points": 3, "require_model_based": True},
        "typing": "Use JSON numbers and booleans, e.g. 12 and true, not strings '12' or 'true'.",
        "verification_details": "Call get_verification_contract for evidence schemas and exact run selection.",
        "config": files["examples/demo/config.yml"],
        "evaluator": files["examples/demo/evaluator.py"],
        "pytest": files["tests/demo/test_example.py"],
        "producer": files["examples/demo/plot_results.py"],
        "finish": "Finish all source/docs first; preflight, then run_workspace_tests on the entire test directory. "
                  "Use its returned run ID for every artifact. Producers call write_artifact_provenance for EACH file. "
                  "Call finalize_optimization_run with the unchanged requirements and all artifact paths. "
                  "Only completion_allowed=true permits a completion claim.",
        "bounded_workers": "When delegation is requested: assign one file/interface per worker, at most 12 tool calls; "
                           "require actual focused results and blockers. Review A/B before assigning independent tests to C. "
                           "Record real session IDs, changed files and call counts; do not assume concurrency.",
        "recovery": "After two identical errors, inspect this contract and the failing evidence; do not repeat the same call "
                    "or weaken requirements. Report blockers if unresolved.",
    }


def scaffold_files(name: str) -> dict[str, str]:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        raise ValueError("Use a lowercase Python identifier for the example name")
    module = f"examples.{name}.evaluator"
    evaluator = '''\
"""Demonstration math. Replace with the scientist's requested implementation."""
from aid2e.mcp.verification import record_diagnostic

def geometry(*, design_point, **kwargs):
    return {"x": float(design_point["demo.x"])}

def simulate(*, inputs, **kwargs):
    return {"sample": inputs["geometry"]["x"]}

def reconstruct(*, inputs, output_dir, **kwargs):
    value = inputs["simulate"]["sample"]
    record_diagnostic(output_dir, "backend", "python")
    # For tensor reconstruction, record str(actual_tensor.device) here as
    # reconstruction_device. GPU availability alone is not a measurement.
    return {"value": value}

def analyze(*, inputs, **kwargs):
    value = inputs["reconstruct"]["value"]
    return {"f1": value**2, "f2": (1.0 - value)**2}
'''
    config = f'''\
problem:
  name: {name}
  problem_type: demonstration
  output_location: output
  work_location: work
  inline_design:
    design_space:
      design_parameters:
        demo:
          parameters:
            x:
              value: 0.5
              bounds: [0.0, 1.0]
  objectives:
    - name: f1
      direction: minimize
    - name: f2
      direction: minimize
optimizer:
  name: ax
  type: bayesian
  parameters:
    n_initial_samples: 5
    n_iterations: 12
    seed: 42
scheduler:
  runner_type: JobLibRunner
  parameters:
    n_jobs: 1
    backend: threading
workflows:
  workflows:
    - name: evaluate
      combined_objectives:
        - name: metrics
          metrics:
            - name: f1
              direction: minimize
              metric_key: f1
            - name: f2
              direction: minimize
              metric_key: f2
          objective_plan:
            steps:
              stages:
                - name: geometry
                  inline:
                    entrypoint: {module}:geometry
                - name: simulate
                  depends_on: [geometry]
                  inline:
                    entrypoint: {module}:simulate
                - name: reconstruct
                  depends_on: [simulate]
                  inline:
                    entrypoint: {module}:reconstruct
                - name: analyze
                  depends_on: [reconstruct]
                  inline:
                    entrypoint: {module}:analyze
                  produces_objective: true
'''
    test = f'''\
"""One isolated CLI run shared by software and numerical assertions."""
import json
from pathlib import Path
import pytest
from aid2e.mcp.verification import run_local_optimization, verify_run

@pytest.fixture(scope="module")
def optimization():
    root = Path(__file__).resolve().parents[2]
    record = run_local_optimization(str(root), "examples/{name}/config.yml", ["tests/{name}"])
    return root, record

def test_results(optimization):
    root, record = optimization
    report = verify_run(root, record["run_id"], {{"expected_trials": 12, "min_pareto_points": 3, "require_model_based": True}})
    assert report["status"] == "passed", report
    data = json.loads(Path(record["artifacts"]["optimization_results.json"]).read_text())
    for trial in data["trials"]:
        value = trial["design_parameters"]["demo.x"]
        assert trial["objectives"]["f1"] == pytest.approx(value**2)
        assert trial["objectives"]["f2"] == pytest.approx((1-value)**2)
'''
    plot = '''\
"""Plot actual results from one managed run; attach matching provenance."""
import argparse
from pathlib import Path
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from aid2e.mcp.verification import run_directory, read_json, verify_run, write_artifact_provenance

def main(run_id):
    root = Path(__file__).resolve().parents[2]
    report = verify_run(root, run_id)
    if report["status"] != "passed":
        raise RuntimeError(report)
    record = read_json(run_directory(root, run_id) / "record.json")
    trials = read_json(Path(record["artifacts"]["optimization_results.json"]))["trials"]
    front = read_json(Path(record["artifacts"]["pareto_front.json"]))
    destination = Path(__file__).parent / "results" / run_id
    destination.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    ax.scatter([t["objectives"]["f1"] for t in trials], [t["objectives"]["f2"] for t in trials], label="Sampled trials")
    ax.scatter([t["objectives"]["f1"] for t in front], [t["objectives"]["f2"] for t in front], marker="x", label="Sampled Pareto front")
    ax.set(xlabel="f1", ylabel="f2", title="Demonstration objectives")
    ax.legend()
    figure = destination / "objectives.png"
    fig.savefig(figure)
    plt.close(fig)
    summary = destination / "summary.json"
    summary.write_text(json.dumps({"run_id": run_id, "verification": report, "pareto_front": front}, indent=2))
    for path in (figure, summary):
        write_artifact_provenance(str(root), run_id, str(path))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    main(parser.parse_args().run_id)
'''
    readme = f'''\
# {name}

This scaffold demonstrates AID2E integration using dimensionless math:
`f1=x²`, `f2=(1-x)²`, `0≤x≤1`. It is not a detector model. Replace the
equations, units and assertions with the scientist's requested specification.

The single combined objective plan runs geometry → simulate → reconstruct →
analyze once per trial. Geometry reads the qualified design parameter; every
later step reads only its named direct dependency from `inputs`.

Evaluator/config/plotting code lives here. Pytest files live in
`tests/{name}/`. Runtime data is isolated under `.aid2e/runs/<run_id>/`.
`run_local_optimization` gives each fixture its own work/output directories;
one module fixture shares that fresh run across assertions.

Use MCP `preflight_workflow` on `examples/{name}/config.yml`, then
`run_workspace_tests` on `tests/{name}/`. The tool returns the managed run IDs
created by the tests. Use `finalize_optimization_run` for the final run.
Direct execution: `python -m pytest tests/{name}/`.

To produce plots and summary from that exact run:
`python examples/{name}/plot_results.py <run_id>`.
Pass the two resulting paths to `finalize_optimization_run` with
`expected_trials=12`, `min_pareto_points=3`, `require_model_based=true`.
Producers write provenance sidecars; the tool checks them. Completion requires
`completion_allowed=true`, not just core verification status or a pytest pass.

For tensor code, use `record_diagnostic(output_dir, "reconstruction_device",
str(tensor.device))` at reconstruction, and verify with `require_device: true`.
This generic scaffold records no tensor device. Verification establishes
software properties; the scientist interprets physical validity.
'''
    return {f"examples/{name}/__init__.py": "", f"examples/{name}/evaluator.py": evaluator,
            f"examples/{name}/config.yml": config, f"examples/{name}/README.md": readme,
            f"examples/{name}/plot_results.py": plot, f"tests/{name}/test_example.py": test}
