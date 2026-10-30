"""Unit tests for the AID2E MCP tool suite and repository index."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from aid2e.mcp.coder_tools import register_coder_tools
from aid2e.mcp.planner_tools import register_planner_tools
from aid2e.mcp.repository import RepositoryIndex
from aid2e.mcp.shared_tools import register_shared_tools


class DummyMCP:
    """Minimal FastMCP stand-in for testing tool registration and invocation."""

    def __init__(self) -> None:
        self.tools: dict[str, callable] = {}

    def tool(self, **_kwargs):
        def decorator(fn):
            self.tools[fn.__name__] = fn
            return fn

        return decorator


def _build_test_harness(tmp_path: Path):
    dummy = DummyMCP()
    index = RepositoryIndex()
    ws_root = tmp_path.resolve()

    def resolver(raw: str) -> Path:
        cleaned = (raw or "").strip().lstrip("/")
        target = (ws_root / cleaned).resolve()
        target.relative_to(ws_root)
        return target

    register_shared_tools(
        dummy,
        index,
        workspace_resolver=resolver,
        workspace_root_getter=lambda: ws_root,
    )
    register_planner_tools(dummy, index)
    register_coder_tools(dummy, index)
    return dummy.tools, index


def test_workspace_requires_explicit_root(tmp_path: Path, monkeypatch) -> None:
    from aid2e.mcp import server

    monkeypatch.setattr(server, "_ACTIVE_WORKSPACE_ROOT", None)
    monkeypatch.delenv("AID2E_WORKSPACE", raising=False)
    assert server.debug_workspace()["workspace"].startswith("UNSET:")
    try:
        server.workspace_path("example.py")
    except ValueError as exc:
        assert "User Workspace is not set" in str(exc)
    else:
        raise AssertionError("workspace path must not default to the process CWD")

    try:
        server.set_active_workspace_root(".")
    except ValueError as exc:
        assert "must be absolute" in str(exc)
    else:
        raise AssertionError("relative workspace root should be rejected")

    server.set_active_workspace_root(str(tmp_path))
    assert server.workspace_path("example.py") == tmp_path / "example.py"


def test_repository_index_and_reference_tools(tmp_path: Path) -> None:
    tools, index = _build_test_harness(tmp_path)
    index.ensure_built()

    assert len(index.info.modules) > 10
    assert len(index.info.classes) > 10

    # Subsystem discovery & blueprints (including previously unrecognized subsystems)
    sched_bp = tools["get_subsystem_blueprints"]("schedulers")
    assert "BaseScheduler" in sched_bp or "base.py" in sched_bp
    assert "Slurm" in sched_bp

    unknown_bp = tools["get_subsystem_blueprints"]("nonexistent_xyz")
    assert "Available subsystems:" in unknown_bp

    all_subsystems = tools["get_subsystem_blueprints"]("")
    assert "schedulers" in all_subsystems
    assert "optimizers" in all_subsystems

    # Class contracts & subclasses
    contract = tools["get_class_contracts"]("BaseScheduler")
    assert "Class contract:" in contract
    assert "Known subclasses:" in contract

    # Symbol source
    src = tools["get_symbol_source"]("BaseScheduler")
    assert "class BaseScheduler" in src

    # Grep framework source
    grep_res = tools["grep_framework_source"]("BaseScheduler", scope="source")
    assert "schedulers" in grep_res

    # Read framework file with line range
    read_res = tools["read_framework_file"](path="schedulers/base.py", start_line=1, end_line=15)
    assert "1:" in read_res
    assert "lines 1-15" in read_res

    # Default and oversized requests still return one bounded, resumable chunk.
    large_path = "optimizers/ax/optimizer.py"
    first = tools["read_framework_file"](path=large_path)
    assert "lines 1-80" in first
    assert "Next chunk: start_line=81" in first
    assert "81:" not in first
    second = tools["read_framework_file"](path=large_path, start_line=81)
    assert "lines 81-160" in second
    assert "81:" in second
    example = tools["read_example_file"](path="dtlz2/python_api/dtlz2_ax_panda.py")
    assert "lines 1-80" in example
    assert "Next chunk: start_line=81" in example
    assert "Line 999999 is past end of file" in tools["read_framework_file"](
        path=large_path, start_line=999999
    )


def test_workspace_tools_lifecycle(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)

    # Create a Python file; parent folders are created automatically.
    code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    create_res = tools["create_file_in_workspace"](content=code, path="schedulers/k8s/runner.py")
    assert create_res == "written (2 lines): schedulers/k8s/runner.py"
    assert str(tmp_path) not in create_res

    # Refuse overwrite when overwrite=False
    refuse_res = tools["create_file_in_workspace"](content=code, path="schedulers/k8s/runner.py", overwrite=False)
    assert "refused:" in refuse_res

    malformed = tools["create_file_in_workspace"](
        content="bad file", path="schedulers/k8s/runner.py.overwrite=True"
    )
    assert "Pass only the filename in `path`" in malformed
    assert not (tmp_path / "schedulers/k8s/runner.py.overwrite=True").exists()

    missing = tools["create_file_in_workspace"](content="bad file", path="")
    assert "pass the workspace-relative file as `path`" in missing

    malformed_edit = tools["replace_lines_in_workspace"](
        start_line=1,
        end_line=1,
        old_content="",
        new_content="bad file",
        path="schedulers/k8s/runner.py.start_line=1",
    )
    assert "Pass only the filename in `path`" in malformed_edit
    assert not (tmp_path / "schedulers/k8s/runner.py.start_line=1").exists()

    updated = tools["create_file_in_workspace"](
        content=code, path="schedulers/k8s/runner.py", overwrite=True
    )
    assert "written (2 lines)" in updated

    # Plain read by default; numbered read for line-based editing.
    plain = tools["read_file_in_workspace"](path="schedulers/k8s/runner.py")
    assert plain == code
    numbered = tools["read_file_in_workspace"](path="schedulers/k8s/runner.py", line_numbers=True)
    assert numbered.startswith("# schedulers/k8s/runner.py (lines 1-2 of 2)")
    assert "1: def add(a: int, b: int) -> int:" in numbered
    assert "2:     return a + b" in numbered

    # Replace lines
    rep_res = tools["replace_lines_in_workspace"](
        start_line=2,
        end_line=2,
        old_content="    return a + b",
        new_content="    return a * b",
        path="schedulers/k8s/runner.py",
    )
    assert rep_res.startswith("replaced lines 2-2; file now has 2 lines: schedulers/k8s/runner.py\n"), rep_res
    assert "2:     return a * b" in rep_res

    # Append chunk
    app_res = tools["append_to_file_in_workspace"](
        content="\ndef multiply_twice(x: int) -> int:\n    return add(x, x)\n",
        path="schedulers/k8s/runner.py",
    )
    assert app_res.startswith("appended;") and app_res.endswith(": schedulers/k8s/runner.py")

    # Validate file
    val_res = tools["validate_workspace_file"](path="schedulers/k8s/runner.py")
    assert val_res.startswith("VALID Python file: schedulers/k8s/runner.py")
    assert "add" in val_res
    assert "multiply_twice" in val_res

    # List & search workspace
    top_level = tools["list_workspace_files"]()
    assert "schedulers/" in top_level
    assert "runner.py" not in top_level
    list_res = tools["list_workspace_files"](directory="schedulers", recursive=True)
    assert "schedulers/k8s/runner.py" in list_res

    search_res = tools["search_workspace"]("multiply_twice")
    assert "schedulers/k8s/runner.py" in search_res


def test_workspace_listing_is_bounded_and_skips_hidden_trees(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    hidden = tmp_path / ".cache"
    hidden.mkdir()
    (hidden / "ignored.py").write_text("needle\n", encoding="utf-8")
    for number in range(2100):
        (tmp_path / f"file_{number:04d}.py").write_text("content\n", encoding="utf-8")

    listing = tools["list_workspace_files"](recursive=True)
    assert "truncated" in listing
    assert "ignored.py" not in listing
    assert listing.count("- `") <= 300
    search = tools["search_workspace"]("needle")
    assert "Narrow `directory`" in search


def test_unknown_configuration_is_not_reported_as_valid(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    config = tmp_path / "other.yaml"
    config.write_text("unrelated: value\n", encoding="utf-8")

    result = tools["validate_workspace_file"](path="other.yaml")
    assert result.startswith("UNRECOGNIZED AID2E configuration:")
    assert "no AID2E schema was identified or validated" in result


_PIPELINE_CONFIG = """\
problem:
  name: "Pipeline"
  problem_type: "Pipeline"
  output_location: "./output"
  work_location: "./work"
  design_parameters_file: "design.params"
  objectives:
    - name: "f1"
      direction: "minimize"
optimizer:
  name: "ax"
  type: "bayesian"
  parameters:
    n_initial_samples: 2
    n_iterations: 4
scheduler:
  runner_type: "JobLibRunner"
  parameters:
    n_jobs: 1
workflows:
  workflows:
    - name: "pipeline"
      branches:
        - name: "main"
          stages:
            - name: "evaluate"
              objective_plan:
                steps:
                  stages:
                    - name: "gen_geom"
                      inline: {entrypoint: "pipeline:gen_geom"}
                    - name: "run_sim"
                      inline: {entrypoint: "pipeline:run_sim"}
                      RUN_SIM_DEPS
                    - name: "analyze"
                      inline: {entrypoint: "pipeline:analyze"}
                      produces_objective: true
                      ANALYZE_DEPS
"""


def test_validate_warns_about_unordered_objective_steps(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    (tmp_path / "design.params").write_text(
        "design_space:\n  design_parameters:\n    g:\n      parameters:\n"
        "        x: {value: 0.5, bounds: [0.0, 1.0]}\n",
        encoding="utf-8",
    )
    config = tmp_path / "config.yml"

    config.write_text(
        _PIPELINE_CONFIG.replace("RUN_SIM_DEPS", "").replace("ANALYZE_DEPS", ""),
        encoding="utf-8",
    )
    result = tools["validate_workspace_file"](path="config.yml")
    assert result.startswith("VALID AID2E configuration (full)")
    assert "WARNING: workflows.workflows[0].branches[0].stages[0].objective_plan" in result
    assert "steps run_sim, analyze have no depends_on" in result
    assert "inputs['<step name>']" in result

    config.write_text(
        _PIPELINE_CONFIG.replace("RUN_SIM_DEPS", "depends_on: [gen_geom]")
        .replace("ANALYZE_DEPS", "depends_on: [run_sim]"),
        encoding="utf-8",
    )
    result = tools["validate_workspace_file"](path="config.yml")
    assert result.startswith("VALID AID2E configuration (full)")
    assert "WARNING" not in result


def test_validate_warns_about_workflow_blocks_that_never_run(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    (tmp_path / "design.params").write_text(
        "design_space:\n  design_parameters:\n    g:\n      parameters:\n"
        "        x: {value: 0.5, bounds: [0.0, 1.0]}\n",
        encoding="utf-8",
    )
    head = _PIPELINE_CONFIG.split("workflows:\n")[0]
    config = tmp_path / "config.yml"

    config.write_text(
        head + "workflows:\n  workflows:\n    - name: eval\n      stages:\n"
        "        - name: sim\n          jobs:\n            - {name: run, command: ''}\n",
        encoding="utf-8",
    )
    result = tools["validate_workspace_file"](path="config.yml")
    assert result.startswith("VALID AID2E configuration (full)")
    assert "WARNING: workflows.workflows[0]: AID2E ignores unknown keys stages" in result
    assert "WARNING: workflows.workflows[0]: no branches" in result

    config.write_text(
        head + "workflows:\n  workflows:\n    - name: eval\n      branches:\n"
        "        - name: main\n          stages:\n            - name: sim\n"
        "              jobs:\n                - {name: run, command: '', python_callable: m.f}\n",
        encoding="utf-8",
    )
    result = tools["validate_workspace_file"](path="config.yml")
    assert "WARNING: workflows.workflows[0].branches[0].stages[0].jobs[0]: " in result
    assert "unknown keys python_callable" in result
    assert "no branches" not in result

    config.write_text(
        head + "workflows:\n  workflows:\n    - name: eval\n      branches:\n"
        "        - name: main\n          stages:\n            - name: sim\n"
        "              jobs:\n                - {name: run, command: ''}\n",
        encoding="utf-8",
    )
    result = tools["validate_workspace_file"](path="config.yml")
    assert result.startswith("VALID AID2E configuration (full)")
    assert "WARNING" not in result


def test_move_file_in_workspace(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    bad_name = "toy_optimization.py.overwrite=True"
    (tmp_path / bad_name).write_text("answer = 42\n", encoding="utf-8")

    moved = tools["move_file_in_workspace"](
        source_path=bad_name, destination_path="toy_optimization.py"
    )
    assert moved == f"moved: {bad_name} -> toy_optimization.py"
    assert not (tmp_path / bad_name).exists()
    assert (tmp_path / "toy_optimization.py").read_text(encoding="utf-8") == "answer = 42\n"

    (tmp_path / bad_name).write_text("new content\n", encoding="utf-8")
    refused = tools["move_file_in_workspace"](
        source_path=bad_name, destination_path="toy_optimization.py"
    )
    assert refused.startswith("refused:")
    assert (tmp_path / "toy_optimization.py").read_text(encoding="utf-8") == "answer = 42\n"

    malformed = tools["move_file_in_workspace"](
        source_path=bad_name, destination_path="other.py.overwrite=True"
    )
    assert "Pass only the filename" in malformed


def _build_source_guard_harness(tmp_path: Path):
    """Workspace that contains a stand-in Reference Source (package + examples)."""
    ws = (tmp_path / "ws").resolve()
    package = ws / "vendor" / "aid2e"
    examples = ws / "vendor" / "examples"
    package.mkdir(parents=True)
    examples.mkdir(parents=True)
    (package / "base.py").write_text("class Base:\n    pass\n", encoding="utf-8")
    (examples / "demo.yml").write_text("key: value\n", encoding="utf-8")
    (ws / "mine.py").write_text("x = 1\n", encoding="utf-8")

    dummy = DummyMCP()
    index = RepositoryIndex(root=ws, package_root=package, examples_root=examples)

    def resolver(raw: str) -> Path:
        target = (ws / raw.strip().lstrip("/")).resolve()
        target.relative_to(ws)
        return target

    register_shared_tools(dummy, index, workspace_resolver=resolver, workspace_root_getter=lambda: ws)
    return dummy.tools, ws, package, examples


def test_replace_lines_refuses_stale_line_numbers(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    target = tmp_path / "loop.py"
    target.write_text("a = 1\nb = 2\nc = 3\nd = 4\n", encoding="utf-8")

    # First edit grows the file, so the old numbers for `d = 4` are now stale.
    first = tools["replace_lines_in_workspace"](
        path="loop.py", start_line=1, end_line=1, old_content="a = 1", new_content="a = 1\na2 = 1.5"
    )
    assert "Lines 1-4 now:\n1: a = 1\n2: a2 = 1.5\n3: b = 2\n4: c = 3" in first, first
    stale = tools["replace_lines_in_workspace"](
        path="loop.py", start_line=4, end_line=4, old_content="d = 4", new_content="d = 40"
    )
    assert stale.startswith("refused: lines 4-4 of loop.py do not match old_content"), stale
    assert "4: c = 3" in stale and "old_content is at lines 5-5" in stale
    assert target.read_text(encoding="utf-8") == "a = 1\na2 = 1.5\nb = 2\nc = 3\nd = 4\n"

    # Trailing whitespace differences are tolerated; deleting lines works.
    ok = tools["replace_lines_in_workspace"](
        path="loop.py", start_line=5, end_line=5, old_content="d = 4   \n", new_content=""
    )
    assert ok.startswith("replaced lines 5-5; file now has 4 lines"), ok
    assert target.read_text(encoding="utf-8") == "a = 1\na2 = 1.5\nb = 2\nc = 3\n"


def test_write_tools_refuse_reference_source(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("AID2E_ALLOW_SOURCE_WRITES", raising=False)
    tools, ws, package, examples = _build_source_guard_harness(tmp_path)
    original = (package / "base.py").read_text(encoding="utf-8")

    attempts = [
        tools["create_file_in_workspace"](path="vendor/aid2e/new.py", content="x = 1\n"),
        tools["create_file_in_workspace"](path="vendor/aid2e/base.py", content="hacked\n", overwrite=True),
        tools["create_file_in_workspace"](path="vendor/examples/new.yml", content="a: 1\n"),
        tools["create_file_in_workspace"](path="other/../vendor/aid2e/sneaky.py", content="x = 1\n"),
        tools["replace_lines_in_workspace"](
            path="vendor/aid2e/base.py", start_line=1, end_line=1, old_content="", new_content="hacked"
        ),
        tools["append_to_file_in_workspace"](path="vendor/aid2e/base.py", content="hacked\n"),
        tools["move_file_in_workspace"](source_path="mine.py", destination_path="vendor/aid2e/mine.py"),
        tools["move_file_in_workspace"](source_path="vendor/aid2e/base.py", destination_path="stolen.py"),
    ]
    for result in attempts:
        assert "read-only AID2E Reference Source" in result, result
        assert str(ws) not in result, result
    assert (package / "base.py").read_text(encoding="utf-8") == original
    assert not (package / "new.py").exists() and not (package / "sneaky.py").exists()
    assert not (examples / "new.yml").exists() and not (ws / "stolen.py").exists()
    assert (ws / "mine.py").exists()

    # A symlink inside the workspace that points into the source is also refused.
    (ws / "link").symlink_to(package, target_is_directory=True)
    via_link = tools["create_file_in_workspace"](path="link/evil.py", content="x = 1\n")
    assert "read-only AID2E Reference Source" in via_link
    assert not (package / "evil.py").exists()

    # Reading and validating the source through workspace tools is still allowed.
    assert tools["read_file_in_workspace"](path="vendor/aid2e/base.py") == original
    assert "VALID Python file" in tools["validate_workspace_file"](path="vendor/aid2e/base.py")
    # Normal workspace writes are unaffected.
    assert "written" in tools["create_file_in_workspace"](path="pkg/runner.py", content="y = 2\n")


def test_source_writes_operator_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AID2E_ALLOW_SOURCE_WRITES", "1")
    tools, _ws, package, _examples = _build_source_guard_harness(tmp_path)
    result = tools["create_file_in_workspace"](path="vendor/aid2e/new.py", content="x = 1\n")
    assert result.startswith("written"), result
    assert (package / "new.py").exists()


def test_run_workspace_tests_reports_pass_and_failure(tmp_path: Path) -> None:
    tools, _index = _build_test_harness(tmp_path)
    (tmp_path / "sphere.py").write_text("def distance(x, y):\n    return (x * x + y * y) ** 0.5\n")
    (tmp_path / "test_sphere.py").write_text(
        "from sphere import distance\n\n"
        "def test_origin():\n    assert distance(0, 0) == 0\n\n"
        "def test_wrong():\n    assert distance(3, 4) == 7\n"
    )

    failed = tools["run_workspace_tests"](path="test_sphere.py")
    assert failed.startswith("pytest FAILED (exit 1"), failed
    assert "test_wrong" in failed and "assert 5.0 == 7" in failed

    passed = tools["run_workspace_tests"](path="test_sphere.py", test_filter="origin")
    assert passed.startswith("pytest PASSED (exit 0"), passed
    assert not (tmp_path / ".pytest_cache").exists()

    (tmp_path / "empty").mkdir()
    assert "NO TESTS COLLECTED" in tools["run_workspace_tests"](path="empty")
    assert tools["run_workspace_tests"](path="missing.py").startswith("not found")


def test_run_workspace_tests_shows_error_despite_noisy_logs(tmp_path: Path) -> None:
    # Like AID2E's DAGExecutor: many kB of INFO logs before the failure.
    tools, _index = _build_test_harness(tmp_path)
    (tmp_path / "test_noisy.py").write_text(
        "import logging, sys, warnings\n\n"
        "log = logging.getLogger('noisy')\n"
        "log.addHandler(logging.StreamHandler(sys.stdout))\n"
        "log.setLevel(logging.INFO)\n\n"
        "def test_noisy():\n"
        "    for i in range(500):\n"
        "        log.info('stage %d resolved payload templates | context: {}', i)\n"
        "        warnings.warn(f'deprecated {i}', DeprecationWarning)\n"
        "    raise RuntimeError('Undefined template variable: {{stage_outputs[sim]}}')\n"
    )

    result = tools["run_workspace_tests"](path="test_noisy.py")
    assert result.startswith("pytest FAILED (exit 1"), result
    assert "E   RuntimeError: Undefined template variable" in result
    assert "resolved payload templates" not in result
    assert len(result) < 8000


@pytest.mark.skipif(os.name != "posix", reason="process-group kill is POSIX-only")
def test_run_workspace_tests_timeout_kills_workers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("AID2E_TEST_TIMEOUT", "3")
    tools, _index = _build_test_harness(tmp_path)
    (tmp_path / "test_hang.py").write_text(
        "import subprocess, sys, time\n\n"
        "def test_hang():\n"
        "    worker = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
        "    open('worker.pid', 'w').write(str(worker.pid))\n"
        "    time.sleep(120)\n"
    )

    result = tools["run_workspace_tests"](path="test_hang.py")
    assert result.startswith("pytest TIMED OUT after 3s"), result
    worker_pid = int((tmp_path / "worker.pid").read_text())
    stat_file = Path(f"/proc/{worker_pid}/stat")
    for _ in range(50):
        try:
            os.kill(worker_pid, 0)
        except ProcessLookupError:
            break
        # A killed orphan stays a zombie (state Z) if PID 1 does not reap it, as in some containers.
        if stat_file.exists() and stat_file.read_text().rsplit(")", 1)[1].split()[0] == "Z":
            break
        time.sleep(0.1)
    else:
        raise AssertionError("worker started by the timed-out test is still running")


def test_run_workspace_tests_caps_threads(tmp_path: Path, monkeypatch) -> None:
    for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("MKL_NUM_THREADS", "2")  # operator setting wins
    tools, _index = _build_test_harness(tmp_path)
    (tmp_path / "test_env.py").write_text(
        "import os\n\n"
        "def test_env():\n"
        "    assert os.environ['OMP_NUM_THREADS'] == '4'\n"
        "    assert os.environ['OPENBLAS_NUM_THREADS'] == '4'\n"
        "    assert os.environ['MKL_NUM_THREADS'] == '2'\n"
    )
    result = tools["run_workspace_tests"](path="test_env.py")
    assert result.startswith("pytest PASSED"), result


def test_run_workspace_tests_refuses_overlapping_runs(tmp_path: Path, monkeypatch) -> None:
    import threading

    monkeypatch.setenv("AID2E_TEST_TIMEOUT", "20")
    tools, _index = _build_test_harness(tmp_path)
    (tmp_path / "test_slow.py").write_text(
        "import pathlib, time\n\n"
        "def test_slow():\n"
        "    pathlib.Path('started').touch()\n"
        "    time.sleep(2)\n"
    )
    results = []
    first = threading.Thread(target=lambda: results.append(tools["run_workspace_tests"](path="test_slow.py")))
    first.start()
    for _ in range(200):
        if (tmp_path / "started").exists():
            break
        time.sleep(0.05)
    busy = tools["run_workspace_tests"](path="test_slow.py")
    first.join()
    assert busy.startswith("busy:"), busy
    assert results[0].startswith("pytest PASSED"), results[0]
    # The lock is released afterwards.
    assert tools["run_workspace_tests"](path="test_slow.py", test_filter="nothing_matches").startswith(
        "pytest NO TESTS COLLECTED"
    )


def test_run_workspace_tests_refuses_reference_source(tmp_path: Path) -> None:
    tools, _ws, _package, _examples = _build_source_guard_harness(tmp_path)
    result = tools["run_workspace_tests"](path="vendor/aid2e")
    assert result.startswith("refused:") and "read-only AID2E Reference Source" in result


def test_workspace_root_cannot_be_inside_reference_source(monkeypatch) -> None:
    from aid2e.mcp import server

    monkeypatch.delenv("AID2E_ALLOW_SOURCE_WRITES", raising=False)
    monkeypatch.setattr(server, "_ACTIVE_WORKSPACE_ROOT", None)
    package = server._INDEX.package_root.resolve()
    for inside in (package, package / "schedulers"):
        try:
            server.set_active_workspace_root(str(inside))
        except PermissionError as exc:
            assert "read-only AID2E Reference Source" in str(exc)
        else:
            raise AssertionError(f"workspace root inside the source was accepted: {inside}")
    assert "UNSET" in server.debug_workspace()["workspace"]

    # A root that merely contains the source (e.g. the repo checkout) is allowed;
    # writes into the source part are refused by the write tools instead.
    container = package.parent
    assert server.set_active_workspace_root(str(container)) == container

    monkeypatch.setenv("AID2E_ALLOW_SOURCE_WRITES", "1")
    assert server.set_active_workspace_root(str(package)) == package


def test_failed_lookups_point_to_workspace(tmp_path: Path) -> None:
    tools, _ = _build_test_harness(tmp_path)
    (tmp_path / "analysis").mkdir()
    (tmp_path / "analysis" / "stats.py").write_text("def spread(values):\n    return 0\n", encoding="utf-8")

    hint = "read_file_in_workspace(path='analysis/stats.py')"
    assert hint in tools["grep_framework_source"](query="analysis/stats.py")
    assert hint in tools["search_workspace"](query="analysis/stats.py")
    assert "read_file_in_workspace" not in tools["search_workspace"](query="no/such/file.py")
    assert "search_workspace" in tools["get_symbol_source"](symbol="NoSuchSymbolXyz")
