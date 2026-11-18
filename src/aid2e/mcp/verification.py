"""Run isolation and independent software checks for the MCP integration.

This adapter calls the installed framework; it does not change its runtime.
Records are engineering evidence, not a security boundary against workspace code.
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
import sys
import traceback
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class RunRequirements(BaseModel):
    """Explicit additions to checks derived from the executed configuration."""
    model_config = ConfigDict(extra="forbid", strict=True)
    expected_trials: int | None = Field(default=None, ge=1)
    min_pareto_points: int = Field(default=1, ge=1)
    require_model_based: bool = False
    require_device: bool = False
    require_artifacts: bool = False


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def read_json(path: Path):
    return json.loads(path.read_text())


def run_directory(root: Path, run_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{32}", run_id):
        raise ValueError("run_id must be the ID returned by run_optimization or preflight_workflow")
    path = (root / ".aid2e" / "runs" / run_id).resolve()
    path.relative_to(root.resolve())
    return path


def framework_identity() -> dict:
    from aid2e.utilities import runtime_builders
    from aid2e.utilities.workflows import dag_executor
    from aid2e.utilities.configurations import full_config
    try:
        version = importlib.metadata.version("aid2e")
    except importlib.metadata.PackageNotFoundError:
        version = "unpackaged"
    return {"version": version, "python": sys.executable, "modules": {
        str(Path(mod.__file__).resolve()): digest(Path(mod.__file__))
        for mod in (runtime_builders, dag_executor, full_config)
    }}


def source_files(root: Path, config: Path, raw: dict, extra: list[str]) -> list[Path]:
    """Track the example, entrypoints, explicit inputs and local Python imports."""
    ignored = {"output", "outputs", "results", "work", ".aid2e", ".git", "__pycache__", "node_modules", ".venv"}
    selected = {config}
    # Limit default traversal to the example rather than unrelated active tasks.
    for directory, children, names in os.walk(config.parent):
        children[:] = [p for p in children if p not in ignored and not p.startswith(".")]
        for name in names:
            path = Path(directory) / name
            if path.is_file() and path.suffix in {".py", ".yml", ".yaml", ".params", ".config", ".md"} and not name.startswith(".aid2e-"):
                selected.add(path.resolve())
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"design_parameters_file", "path"} and isinstance(value, str):
                    candidate = (config.parent / value).resolve()
                    if candidate.is_file():
                        selected.add(candidate)
                if key == "entrypoint" and isinstance(value, str):
                    module = value.split(":")[0].replace(".", "/")
                    for base in (root, config.parent):
                        for candidate in (base / (module + ".py"), base / module / "__init__.py"):
                            if candidate.is_file():
                                selected.add(candidate.resolve())
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
    walk(raw)
    for value in extra:
        path = (root / value).resolve()
        path.relative_to(root)
        if path.is_dir():
            selected.update(p.resolve() for p in path.rglob("*") if p.is_file() and not any(x in ignored for x in p.relative_to(path).parts))
        elif path.is_file():
            selected.add(path)
        else:
            raise ValueError(f"Source path does not exist: {value}")
    scanned = set()
    while pending := [p for p in selected - scanned if p.suffix == ".py"]:
        for path in pending:
            scanned.add(path)
            try:
                tree = ast.parse(path.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                modules = []
                bases = (root, config.parent)
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                    if node.level:
                        base = path.parent
                        for _ in range(node.level - 1):
                            base = base.parent
                        bases = (base,)
                    modules += [(node.module + "." if node.module else "") + a.name for a in node.names]
                for module in modules:
                    for base in bases:
                        for candidate in (base / (module.replace(".", "/") + ".py"), base / module.replace(".", "/") / "__init__.py"):
                            if candidate.is_file() and candidate.resolve().is_relative_to(root):
                                selected.add(candidate.resolve())
    for path in list(selected):
        if path.suffix == ".py" and path.is_relative_to(root):
            for parent in path.parents:
                if parent == root or not parent.is_relative_to(root):
                    break
                init = parent / "__init__.py"
                if init.is_file():
                    selected.add(init)
    return sorted(selected)


def prepare_run(root: Path, config: Path, mode: str, workflow: str, sources: list[str]) -> dict:
    import yaml
    from aid2e.utilities.configurations import load_config
    root, config = root.resolve(), config.resolve()
    config.relative_to(root)
    raw = yaml.safe_load(config.read_text())
    if not isinstance(raw, dict):
        raise ValueError("Expected a full AID2E configuration mapping")
    run_id = uuid.uuid4().hex
    folder = run_directory(root, run_id)
    folder.mkdir(parents=True, exist_ok=False)
    record = {"run_id": run_id, "mode": mode, "status": "prepared", "workspace": str(root),
              "config": str(config), "workflow": workflow or None, "created_at": datetime.now(timezone.utc).isoformat(),
              "source_paths": sources, "sources": {str(p): digest(p) for p in source_files(root, config, raw, sources)},
              "framework": framework_identity(), "pytest_execution_id": os.environ.get("AID2E_PYTEST_EXECUTION_ID"),
              "artifacts": {}, "checks": {"validation": "not_run", "execution": "not_run"}}
    write_json(folder / "record.json", record)
    try:
        from .shared_tools import _workflow_structure_warnings, _objective_plan_order_warnings
        warnings = _workflow_structure_warnings(raw) + _objective_plan_order_warnings(raw)
        plans = [o.get("objective_plan") for o in raw.get("problem", {}).get("objectives", []) if isinstance(o, dict) and o.get("objective_plan")]
        if len({json.dumps(p, sort_keys=True) for p in plans}) < len(plans):
            warnings.append("Identical objective plans execute separately; consider one combined_objectives plan for shared simulation/reconstruction.")
        record["warnings"] = warnings
        cfg = load_config(str(config))
        from aid2e.utilities.runtime_builders import infer_optimizer_backend
        backend = infer_optimizer_backend(cfg.optimizer)
        if backend == "ax":
            from aid2e.optimizers.ax.config import AxOptimizerConfig
            algorithm = AxOptimizerConfig(**cfg.optimizer.parameters)
        else:
            from aid2e.optimizers.pymoo.config import PyMOOOptimizerConfig
            algorithm = PyMOOOptimizerConfig(**cfg.optimizer.parameters)
        params = cfg.problem.design_config.get_flat_parameters()
        record["expected"] = {
            "trials": algorithm.n_iterations if backend == "ax" else None,
            "initial_samples": getattr(algorithm, "n_initial_samples", None),
            "initialization_strategy": getattr(algorithm, "initialization_strategy", None),
            "optimizer": backend,
            "objectives": {o.name: o.direction.value for o in cfg.problem.objectives},
            "parameters": {name: {"bounds": cfg.problem.design_config.get_parameter_bounds(name),
                                   "choices": cfg.problem.design_config.get_parameter_choices(name), "value": p.value}
                           for name, p in params.items()},
            "constraints": [p.model_dump() for p in cfg.problem.design_config.parameter_constraints or []],
        }
        record["checks"]["validation"] = "passed"
    except Exception as exc:
        record.update(status="failed", error=str(exc))
        record["checks"]["validation"] = "failed"
    write_json(folder / "record.json", record)
    return record


def record_diagnostic(output_dir: str, name: str, value) -> None:
    """Record a trial diagnostic, e.g. str(tensor.device), without an objective.

    Call at the operation being measured. Values are evaluator-supplied evidence;
    the helper cannot establish whether arbitrary evaluator claims are truthful.
    """
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError("Diagnostic name must be an identifier")
    write_json(Path(output_dir) / "diagnostics" / (name + ".json"), {"name": name, "value": value})


def execute_run(root: Path, run_id: str) -> int:
    """Child process: use a sibling config so original relative paths keep meaning."""
    import yaml
    folder = run_directory(root, run_id)
    record = read_json(folder / "record.json")
    config = Path(record["config"])
    temporary = config.parent / (".aid2e-" + run_id + ".yml")
    record["status"] = "running"
    write_json(folder / "record.json", record)
    trace = []
    exit_code = 1
    with (folder / "execution.log").open("w") as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        try:
            raw = yaml.safe_load(config.read_text())
            raw["problem"]["output_location"] = str(folder / "output")
            raw["problem"]["work_location"] = str(folder / "work")
            text = yaml.safe_dump(raw, sort_keys=False)
            temporary.write_text(text)
            (folder / "effective.yml").write_text(text)
            record["effective_config_hash"] = digest(temporary)
            write_json(folder / "record.json", record)
            if record["mode"] == "optimization":
                from aid2e.cli import cli
                args = ["optimize", str(temporary), "--run-id", run_id]
                if record["workflow"]:
                    args += ["--workflow", record["workflow"]]
                cli.main(args=args, prog_name="aid2e", standalone_mode=False)
                result_dir = folder / "output" / run_id
                record["artifacts"] = {name: str(result_dir / name) for name in ("optimization_results.json", "pareto_front.json")}
            else:
                from aid2e.utilities.configurations import load_config
                from aid2e.utilities.runtime_builders import build_workflow_executor_from_config
                cfg = load_config(str(temporary))
                executor = build_workflow_executor_from_config(
                    cfg.workflows, problem_cfg=cfg.problem, scheduler_cfg=cfg.scheduler,
                    workflow_name=record["workflow"], config_dir=str(config.parent),
                    output_dir=str(folder / "output"), work_dir=str(folder / "work"))
                original = executor._execute_inline_objective_step
                def traced(plan_name, step, inputs):
                    event = {"plan": plan_name, "step": step.name, "entrypoint": step.inline.entrypoint,
                             "available_inputs": {k: list(v) if isinstance(v, dict) else type(v).__name__ for k, v in inputs.items()}}
                    trace.append(event)
                    try:
                        result = original(plan_name, step, inputs)
                        event["returned"] = list(result) if isinstance(result, dict) else type(result).__name__
                        return result
                    except Exception as exc:
                        event["error"] = str(exc)
                        raise
                executor._execute_inline_objective_step = traced
                design = {k: p.value for k, p in cfg.problem.design_config.get_flat_parameters().items()}
                for name, value in design.items():
                    bounds = cfg.problem.design_config.get_parameter_bounds(name)
                    choices = cfg.problem.design_config.get_parameter_choices(name)
                    if bounds and (not _finite(value) or not bounds[0] <= value <= bounds[1]):
                        raise ValueError(f"Default candidate parameter {name}={value!r} violates bounds {bounds}")
                    if choices and value not in choices:
                        raise ValueError(f"Default candidate parameter {name}={value!r} is not in {choices}")
                for constraint in cfg.problem.design_config.parameter_constraints or []:
                    if not constraint.evaluate(design):
                        raise ValueError(f"Default candidate violates configured constraint {constraint.name}: {constraint.rule}")
                metrics = executor.execute(design)
                write_json(folder / "candidate.json", {"design_parameters": design, "objectives": metrics})
                record["artifacts"] = {"candidate": str(folder / "candidate.json"), "step_trace": str(folder / "step_trace.json")}
            exit_code = 0
            record["status"] = "completed"
            record["checks"]["execution"] = "passed"
        except BaseException as exc:
            record.update(status="failed", error=str(exc))
            record["checks"]["execution"] = "failed"
            traceback.print_exc()
        finally:
            temporary.unlink(missing_ok=True)
            write_json(folder / "step_trace.json", trace)
            record["exit_code"] = exit_code
            evidence_files = [Path(p) for p in record["artifacts"].values()]
            evidence_files += list((folder / "output").rglob("diagnostics/*.json"))
            record["artifact_hashes"] = {str(p): digest(p) for p in evidence_files if p.is_file()}
            write_json(folder / "record.json", record)
    print(json.dumps({"run_id": run_id, "status": record["status"], "error": record.get("error")}))
    return exit_code


def run_local_optimization(workspace: str, config: str, source_paths: list[str] | None = None) -> dict:
    """Pytest fixture helper: one fresh real CLI invocation, no MCP recursion."""
    root = Path(workspace).resolve()
    record = prepare_run(root, root / config, "optimization", "", source_paths or [])
    if record["status"] == "failed" or execute_run(root, record["run_id"]):
        folder = run_directory(root, record["run_id"])
        raise RuntimeError(f"Optimization failed; inspect {folder / 'record.json'} and execution.log")
    return read_json(run_directory(root, record["run_id"]) / "record.json")


def _finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def verify_run(root: Path, run_id: str, requirements: dict | None = None) -> dict:
    """Independently check saved records, not agent-authored pytest assertions."""
    req = RunRequirements.model_validate(requirements or {})
    folder = run_directory(root, run_id)
    record = read_json(folder / "record.json")
    failures, checks = [], {}
    def check(name, ok, detail=""):
        checks[name] = {"status": "passed" if ok else "failed", "detail": detail}
        if not ok:
            failures.append(name)
    def unchanged(mapping):
        return all(Path(p).is_file() and digest(Path(p)) == sha for p, sha in mapping.items())
    check("execution", record["status"] == "completed", record["status"])
    check("run_mode", record["mode"] in {"optimization", "preflight"})
    try:
        import yaml
        config = Path(record["config"])
        inventory = source_files(root.resolve(), config, yaml.safe_load(config.read_text()), record.get("source_paths", []))
        fresh = unchanged(record["sources"]) and {str(p) for p in inventory} == set(record["sources"])
    except (OSError, ValueError, TypeError, yaml.YAMLError):
        fresh = False
    check("source_freshness", fresh)
    check("framework_compatibility", record["framework"] == framework_identity())
    check("artifact_integrity", bool(record.get("artifact_hashes")) and unchanged(record.get("artifact_hashes", {})))
    effective = folder / "effective.yml"
    check("effective_config_integrity", effective.is_file() and digest(effective) == record.get("effective_config_hash"))
    devices = []
    try:
        if record["mode"] == "optimization" and not failures:
            expected = record["expected"]
            trials = read_json(Path(record["artifacts"]["optimization_results.json"]))["trials"]
            front = read_json(Path(record["artifacts"]["pareto_front.json"]))
            if not isinstance(trials, list) or not isinstance(front, list):
                raise ValueError("Expected trial and Pareto lists")
            target = expected["trials"] if expected["trials"] is not None else req.expected_trials
            check("trial_budget", target is not None and len(trials) == target and all(t["status"] == "completed" for t in trials), f"{len(trials)} recorded; expected {target}")
            if req.expected_trials is not None and expected["trials"] is not None:
                check("requested_trial_budget", target == req.expected_trials, f"configuration requests {target}; requirement is {req.expected_trials}")
            indices = [t["trial_index"] for t in trials]
            check("unique_trials", len(set(indices)) == len(indices))
            names = list(expected["objectives"])
            check("objectives", all(set(t["objectives"]) == set(names) and all(_finite(t["objectives"][n]) for n in names) for t in trials))
            def valid_parameters(t):
                values = t["design_parameters"]
                if set(values) != set(expected["parameters"]):
                    return False
                for name, spec in expected["parameters"].items():
                    value = values[name]
                    if spec["bounds"] and (not _finite(value) or not spec["bounds"][0] <= value <= spec["bounds"][1]):
                        return False
                    if spec["choices"] and value not in spec["choices"]:
                        return False
                    if not spec["bounds"] and not spec["choices"] and value != spec["value"]:
                        return False
                return True
            check("parameter_bounds", all(valid_parameters(t) for t in trials))
            from aid2e.utilities.configurations.design_config import ParameterConstraint
            constraints = [ParameterConstraint(**r) for r in expected["constraints"]]
            check("parameter_constraints", all(c.evaluate(t["design_parameters"]) for t in trials for c in constraints))
            initial = expected["initial_samples"]
            if str(expected["optimizer"]).lower() == "ax" and initial is not None:
                ordered = sorted(trials, key=lambda t: t["trial_index"])
                nodes = [t.get("metadata", {}).get("ax_node_name") for t in ordered]
                strategy = expected.get("initialization_strategy", "sobol")
                if strategy in {"sobol", "uniform"}:
                    check("initialization", all(n == "Sobol" for n in nodes[:initial]), str(nodes))
                else:
                    check("initialization", False, f"Unsupported initialization metadata contract: {strategy}")
                if len(nodes) > initial or req.require_model_based:
                    check("model_based_generation", len(nodes) > initial and all(n == "ModularBoTorch" for n in nodes[initial:]), str(nodes[initial:]))
            elif req.require_model_based:
                check("model_based_generation", False, "No supported generator metadata contract for this optimizer")
            def dominates(a, b):
                aa = [a["objectives"][n] * (1 if expected["objectives"][n] == "minimize" else -1) for n in names]
                bb = [b["objectives"][n] * (1 if expected["objectives"][n] == "minimize" else -1) for n in names]
                return all(x <= y for x, y in zip(aa, bb)) and any(x < y for x, y in zip(aa, bb))
            by_index = {t["trial_index"]: t for t in trials}
            front_ids = [t["trial_index"] for t in front]
            check("pareto_membership", len(set(front_ids)) == len(front_ids) and all(p["trial_index"] in by_index and p["objectives"] == by_index[p["trial_index"]]["objectives"] and p["design_parameters"] == by_index[p["trial_index"]]["design_parameters"] for p in front))
            independent = {t["trial_index"] for t in trials if not any(dominates(other, t) for other in trials)}
            check("pareto_front", set(front_ids) == independent and len(front_ids) >= req.min_pareto_points, f"reported {front_ids}; independently computed {sorted(independent)}")
            missing = []
            for trial in trials:
                path = Path(record["artifacts"]["optimization_results.json"]).parent / "trials" / f"trial_{trial['trial_index']}" / "diagnostics" / "reconstruction_device.json"
                if path.is_file():
                    device = read_json(path).get("value")
                    if isinstance(device, str) and device:
                        devices.append(device)
                        continue
                missing.append(trial["trial_index"])
            if req.require_device:
                check("device_records", not missing, f"missing for trials {missing}")
            else:
                checks["device_records"] = {"status": "not_measured" if missing else "passed", "detail": f"missing for trials {missing}"}
        elif record["mode"] == "preflight" and not failures:
            candidate = read_json(folder / "candidate.json")
            names = record["expected"]["objectives"]
            check("candidate_objectives", set(candidate["objectives"]) == set(names) and all(_finite(v) for v in candidate["objectives"].values()))
            if req.expected_trials is not None or req.min_pareto_points > 1 or req.require_model_based or req.require_device:
                check("optimization_required", False, "A one-candidate preflight cannot satisfy optimization trial, Pareto, generation or per-trial device requirements")
    except (KeyError, TypeError, ValueError, OSError) as exc:
        check("result_schema", False, str(exc))
    report = {"run_id": run_id, "mode": record["mode"], "status": "passed" if not failures else "failed",
              "checks": checks, "devices": sorted(set(devices)), "requirements": req.model_dump(),
              "execution_checks": record["checks"], "artifacts": record["artifacts"], "warnings": record.get("warnings", []),
              "limitations": ["Software checks only; scientific validity requires scientist interpretation.",
                              "Agent pytest and plot provenance are separate checks; use run_workspace_tests and register_run_artifacts."]}
    write_json(folder / "verification.json", report)
    return report


def save_pytest_evidence(root: Path, target: Path, result: str, started_at: float, execution_id: str) -> list[str]:
    """Store tool-observed pytest outcome separately from result verification."""
    import time
    files = sorted(target.rglob("*.py")) if target.is_dir() else [target]
    status = "passed" if result.startswith("pytest PASSED") else "not_run" if result.startswith("busy:") else "failed"
    write_json(root / ".aid2e" / "pytest" / (execution_id + ".json"), {
        "status": status, "started_at": started_at, "finished_at": time.time(),
        "files": {str(p): digest(p) for p in files if p.is_file()}, "output": result,
    })
    return [p.parent.name for p in (root / ".aid2e" / "runs").glob("*/record.json")
            if read_json(p).get("pytest_execution_id") == execution_id]


def verification_report(root: Path, run_id: str, requirements: dict | None = None) -> dict:
    """Recheck freshness every time; never reuse a historical pass unconditionally."""
    report = verify_run(root, run_id, requirements)
    folder = run_directory(root, run_id)
    record = read_json(folder / "record.json")
    report["pytest"] = {"status": "not_run", "detail": "No associated pytest execution recorded"}
    execution_id = record.get("pytest_execution_id")
    evidence_path = root / ".aid2e" / "pytest" / (str(execution_id) + ".json")
    if execution_id and evidence_path.is_file():
        evidence = read_json(evidence_path)
        created = datetime.fromisoformat(record["created_at"]).timestamp()
        if evidence["finished_at"] >= created:
            fresh = all(Path(p).is_file() and digest(Path(p)) == h for p, h in evidence["files"].items())
            report["pytest"] = {"status": evidence["status"] if fresh else "stale", "files": list(evidence["files"]),
                                "detail": "Pytest invocation that created this managed run"}
    derived_file = folder / "derived_artifacts.json"
    report["derived_artifacts"] = {"status": "not_registered", "files": []}
    if derived_file.is_file():
        entries = read_json(derived_file)
        fresh = all(Path(p).is_file() and digest(Path(p)) == v["sha256"] and Path(v["sidecar"]).is_file() and digest(Path(v["sidecar"])) == v["sidecar_hash"] for p, v in entries.items())
        report["derived_artifacts"] = {"status": "passed" if fresh else "stale", "files": list(entries)}
    missing_artifacts = report["requirements"]["require_artifacts"] and report["derived_artifacts"]["status"] == "not_registered"
    if report["status"] != "passed" or report["pytest"]["status"] in {"failed", "stale"} or report["derived_artifacts"]["status"] == "stale":
        report["overall_status"] = "failed"
    elif report["pytest"]["status"] == "not_run" or missing_artifacts:
        report["overall_status"] = "incomplete"
    else:
        report["overall_status"] = "passed"
    return publish_acceptance(root, report)


def publish_acceptance(root: Path, report: dict) -> dict:
    """Put the overall verdict first and persist a human-readable evidence card."""
    status = report["overall_status"]
    if status == "passed" and not report.get("finalization_checked"):
        status = "not_finalized"
    report = {"acceptance_status": status, "completion_allowed": status == "passed", **report}
    # Never retain a previous verdict supplied in a report being republished.
    report.update(acceptance_status=status, completion_allowed=status == "passed")
    folder = run_directory(root, report["run_id"])
    card = folder / "acceptance.md"
    report["acceptance_path"] = str(card)
    failures = [name for name, check in report["checks"].items() if check["status"] == "failed"]
    card.write_text(
        f"# AID2E acceptance: {status.upper()}\n\n"
        f"Run: `{report['run_id']}`\n\n"
        f"Completion allowed: {'yes' if report['completion_allowed'] else 'no'}\n\n"
        f"Independent checks: {report['status']}\n\n"
        f"Associated pytest: {report['pytest']['status']}\n\n"
        f"Derived artifacts: {report['derived_artifacts']['status']}\n\n"
        f"Failed checks: {', '.join(failures) or 'none'}\n\n"
        "This is a snapshot. Recheck with `aid2e mcp status RUN_ID --workspace PATH`. "
        "Model prose cannot override this verdict. Scientific interpretation remains with the scientist.\n"
    )
    write_json(folder / "report.json", report)
    return report


def finalize_run(root: Path, run_id: str, requirements: dict, artifact_paths: list[str] | None = None) -> dict:
    """Strict final acceptance; never fabricate provenance or rerun scientific code."""
    root = root.resolve()
    req = RunRequirements.model_validate(requirements).model_dump()
    req["require_artifacts"] = True
    specification = run_directory(root, run_id) / "finalization.json"
    previous = read_json(specification) if specification.is_file() else {}
    # Retain declared prerequisites across status refreshes and failed attempts.
    # A later omitted flag/path must not silently weaken prior acceptance.
    old_req = previous.get("requirements", {})
    req["min_pareto_points"] = max(req["min_pareto_points"], old_req.get("min_pareto_points", 1))
    for key in ("require_model_based", "require_device"):
        req[key] = req[key] or old_req.get(key, False)
    if not artifact_paths:
        artifact_paths = previous.get("artifact_paths")
    # Validate identity before creating state for a nonexistent run.
    read_json(run_directory(root, run_id) / "record.json")
    write_json(specification, {"requirements": req, "artifact_paths": artifact_paths})
    # Registration verifies producer-written sidecars. An invalid request must
    # not leave a historical acceptance pass as the apparent current verdict.
    registration_error = None
    if artifact_paths:
        try:
            register_run_artifacts(root, run_id, artifact_paths)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            registration_error = str(exc)
    report = verification_report(root, run_id, req)
    record = read_json(run_directory(root, run_id) / "record.json")
    tests = report["pytest"].get("files", [])
    uncovered = [p for p in tests if p not in record["sources"]]
    covered = bool(tests) and not uncovered
    report["checks"]["pytest_source_coverage"] = {
        "status": "passed" if covered else "failed",
        "detail": "" if covered else f"Include the entire test directory in source_paths; uncovered: {uncovered}",
    }
    if registration_error:
        report["checks"]["artifact_registration"] = {"status": "failed", "detail": registration_error}
    if not covered or registration_error:
        report.update(status="failed", overall_status="failed")
    report["finalization_checked"] = True
    report["next_action"] = (
        "Report the exact run and separate evidence statuses."
        if report["overall_status"] == "passed" else
        "Do not claim completion. Fix the listed prerequisites; after source/test changes run fresh integrated pytest. "
        "Produce every requested artifact from that run, write matching sidecars, and finalize again."
    )
    return publish_acceptance(root, report)


def register_run_artifacts(root: Path, run_id: str, paths: list[str]) -> dict:
    """Bind derived artifacts using a sidecar and hashes of verified source data."""
    folder = run_directory(root, run_id)
    report = verify_run(root, run_id)
    if report["status"] != "passed":
        raise ValueError("Verify the unchanged source run before registering derived artifacts")
    record = read_json(folder / "record.json")
    artifacts = {}
    for path in paths:
        target = (root / path).resolve()
        target.relative_to(root.resolve())
        if not target.is_file():
            raise ValueError(f"Artifact does not exist: {path}")
        sidecar = target.with_name(target.name + ".provenance.json")
        # Producers must write provenance when producing the artifact, not attach
        # an unchecked claim to a pre-existing image during registration.
        evidence = read_json(sidecar)
        if evidence.get("run_id") != run_id or evidence.get("artifact_hash") != digest(target) or evidence.get("source_hashes") != record["artifact_hashes"]:
            raise ValueError(f"Artifact provenance does not match this run: {path}")
        artifacts[str(target)] = {"sha256": digest(target), "sidecar": str(sidecar), "sidecar_hash": digest(sidecar)}
    write_json(folder / "derived_artifacts.json", artifacts)
    return artifacts


def write_artifact_provenance(workspace: str, run_id: str, artifact: str) -> None:
    """Call from a plot/summary producer immediately after writing its output."""
    root = Path(workspace).resolve()
    record = read_json(run_directory(root, run_id) / "record.json")
    target = Path(artifact).resolve()
    target.relative_to(root)
    write_json(target.with_name(target.name + ".provenance.json"), {
        "run_id": run_id, "artifact_hash": digest(target), "source_hashes": record["artifact_hashes"]})


if __name__ == "__main__":
    raise SystemExit(execute_run(Path(sys.argv[1]).resolve(), sys.argv[2]))
