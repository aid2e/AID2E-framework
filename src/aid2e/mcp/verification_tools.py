"""Small-model tools for managed runs, preflight, scaffolding and evidence."""
from __future__ import annotations

from pathlib import Path
from functools import wraps
import sys
import yaml

from .verification import (RunRequirements, finalize_run, prepare_run, read_json, register_run_artifacts, run_directory,
                           verification_report, verify_run, write_json)


def register_verification_tools(register, resolve, root_getter, execute):
    def tool(description):
        def decorate(fn):
            @wraps(fn)
            def guarded(*args, **kwargs):
                try:
                    return fn(*args, **kwargs)
                except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
                    # MCP SDK v2 sanitizes unexpected exceptions. Return expected
                    # input/config errors explicitly so the model can correct them.
                    return {"completion_allowed": False, "status": "error", "error": str(exc)}
            return register(description)(guarded)
        return decorate

    def launch(config: str, mode: str, workflow: str, source_paths: list[str]) -> dict:
        root = root_getter().resolve()
        path = resolve(config, write=True)
        if path.suffix not in {".yml", ".yaml", ".json"}:
            raise ValueError("Pass a full YAML/JSON AID2E configuration")
        resolve(".aid2e/runs", write=True)
        record = prepare_run(root, path, mode, workflow, source_paths)
        folder = run_directory(root, record["run_id"])
        if record["status"] != "failed":
            outcome = execute([sys.executable, "-m", "aid2e.mcp.verification", str(root), record["run_id"]], root, mode)
            record = read_json(folder / "record.json")
            if record["status"] != "completed":
                status = "not_run" if outcome.startswith("busy:") else "timed_out" if "TIMED OUT" in outcome else "failed"
                record.update(status=status, tool_output=outcome)
                record["checks"]["execution"] = status
                write_json(folder / "record.json", record)
            (path.parent / (".aid2e-" + record["run_id"] + ".yml")).unlink(missing_ok=True)
        report = verify_run(root, record["run_id"])
        result = {"run_id": record["run_id"], "status": record["status"], "record": str(folder / "record.json"),
                  "log": str(folder / "execution.log"), "verification": report}
        if record["status"] != "completed":
            result["error"] = record.get("error", record.get("tool_output", "Run did not complete"))
            log = folder / "execution.log"
            if log.is_file():
                result["log_tail"] = log.read_text(errors="replace")[-4000:]
        if mode == "preflight":
            trace = folder / "step_trace.json"
            result["step_trace"] = read_json(trace) if trace.is_file() else []
        return result

    @tool("Execute the real AID2E optimize CLI with unique work/output directories and source hashes. "
              "Use this for optimizations instead of searching latest output folders. Preserves the trial budget. "
              "Returns run_id and independent result checks. Shares the command/pytest execution slot.")
    def run_optimization(config: str, workflow: str = "", source_paths: list[str] | None = None) -> dict:
        """source_paths adds workspace-relative files/directories for dynamic imports or external inputs."""
        return launch(config, "optimization", workflow, source_paths or [])

    @tool("Validate and execute one configured candidate without optimization, in isolated directories. "
              "Returns step input keys, return keys and errors. This is execution, not a full trial-budget test.")
    def preflight_workflow(config: str, workflow: str = "", source_paths: list[str] | None = None) -> dict:
        return launch(config, "preflight", workflow, source_paths or [])

    @tool("Independently verify a managed run: freshness, completed trial budget, bounds, constraints, finite "
              "objectives, Ax generation metadata and Pareto dominance. requirements accepts expected_trials, "
              "min_pareto_points, require_model_based, require_device, require_artifacts. Checks software behavior, not scientific validity.")
    def verify_optimization_run(run_id: str, requirements: RunRequirements | None = None) -> dict:
        return verify_run(root_getter(), run_id, requirements)

    @tool("Get current execution, independent verification, associated pytest and derived-artifact evidence. "
              "Call before reporting completion. Optional artifact_paths registers plots/summaries with matching "
              "producer-written .provenance.json sidecars. Missing measurements stay explicit.")
    def get_verification_report(run_id: str, requirements: RunRequirements | None = None, artifact_paths: list[str] | None = None) -> dict:
        root = root_getter()
        specification = run_directory(root, run_id) / "finalization.json"
        if specification.is_file():
            for path in artifact_paths or []:
                resolve(path, write=True)
            return finalize_run(root, run_id, requirements or read_json(specification)["requirements"], artifact_paths)
        if artifact_paths:
            for path in artifact_paths:
                resolve(path, write=True)
            register_run_artifacts(root, run_id, artifact_paths)
        return verification_report(root, run_id, requirements)

    @tool("Read canonical runnable AID2E integration patterns before writing code: inline design_point/inputs, "
          "combined config, record-dict runner, shared pytest fixture, provenance producer and bounded workers. "
          "Use after an API/schema error instead of inventing imports or repeating the same rejected call.")
    def get_integration_contract() -> dict:
        from .scaffolding import integration_contract
        return integration_contract()

    @tool("Finalize the exact pytest-created managed run. Always requires associated fresh pytest, test source coverage "
          "and registered producer-written artifact provenance. Never creates sidecars or reruns optimization. "
          "Pass expected_trials as an integer (8), require_model_based as a boolean (true), and EVERY requested "
          "plot/summary path. Only completion_allowed=true means accepted; saves acceptance.md independently of model prose.")
    def finalize_optimization_run(run_id: str, expected_trials: int, artifact_paths: list[str] | None = None,
                                  min_pareto_points: int = 1, require_model_based: bool = True,
                                  require_device: bool = False) -> dict:
        for path in artifact_paths or []:
            resolve(path, write=True)
        requirements = RunRequirements(expected_trials=expected_trials, min_pareto_points=min_pareto_points,
                                       require_model_based=require_model_based, require_device=require_device,
                                       require_artifacts=True)
        return finalize_run(root_getter(), run_id, requirements.model_dump(), artifact_paths)

    @tool("Create a runnable generic example scaffold in examples/<name>/ and pytest files in tests/<name>/. "
              "Includes explicit step inputs, one combined objective plan, an isolated real-CLI fixture, README "
              "and provenance-aware plotting. Never overwrites files. Replace the demonstration math with the requested specification.")
    def scaffold_example(name: str) -> dict:
        from .scaffolding import scaffold_files
        files = scaffold_files(name)
        if not resolve("examples/__init__.py", write=True).exists():
            files = {"examples/__init__.py": "", **files}
        targets = [(resolve(path, write=True), content) for path, content in files.items()]
        if any(path.exists() for path, _ in targets):
            raise ValueError("Scaffold target already exists; existing files are preserved")
        for path, content in targets:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        return {"created": list(files), "next": f"preflight_workflow(config='examples/{name}/config.yml')"}
