"""Tests for epic stack utilities."""

import subprocess
from types import SimpleNamespace

import pytest

import aid2e.utilities.epic_utils.epic_stack as epic_stack_module
from aid2e.utilities.epic_utils.epic_stack import (
    EpicGeoLayer,
    EpicSimLayer,
    EpicRecLayer,
    EpicAnaLayer,
    EpicStack
)


def test_epic_geometry_build_failure_is_not_marked_compiled(tmp_path, monkeypatch):
    """A failed geometry build should not create compiled.log."""
    class FakeDesignConfig:
        def get_xml_modifications(self, _design_point):
            return {}

    template_dir = tmp_path / "template"
    template_dir.mkdir()
    workflow_dir = tmp_path / "workflow"
    problem_config = SimpleNamespace(
        design_config=FakeDesignConfig(),
        environment_config=SimpleNamespace(
            geometry_mode="build",
            epic_install=str(template_dir),
        ),
    )
    stack = EpicStack()
    monkeypatch.setattr(epic_stack_module, "EpicDesignConfig", FakeDesignConfig)
    monkeypatch.setattr(stack, "make_driver_command", lambda _script: "false")

    with pytest.raises(subprocess.CalledProcessError):
        stack.prepare_workflow_geometry(
            workflow_dir=str(workflow_dir),
            design_point={},
            problem_config=problem_config,
            workflow_id="test",
        )

    assert not (workflow_dir / template_dir.name / "compiled.log").exists()


def _make_epic_stack_payload() -> dict:
    """Build a dictionary of epic stack layer inputs, outputs, and arguments for tests."""
    return {
        "geo_input" : [
            "./epic/my_epic.xml",
        ],
        "geo_output" : [
            "overlap_output.log",
        ],
        "geo_args" : [
            "--tolerance 0.01",
        ],
        "sim_input" : [
            "steering_input.py",
            "hepmc_input.hepmc",
            "hepmc_tree_input.hepmc3.root",
            "macro_input.mac",
        ],
        "sim_output" : [
            "sim_output.edm4hep.root",
        ],
        "sim_args" : [
            "--numberOfEvents 100",
            "--skipNEvents 10",
        ],
        "rec_output" : [
            "rec_output.edm4eic.root",
        ],
        "rec_args" : [
            "-Pnthreads=8",
            "-Pjana:global_loglevel=debug",
        ],
    }


def test_epic_geo_layer():
    """EpicGeoLayer functionality"""
    payload  = _make_epic_stack_payload()
    geolayer = EpicGeoLayer()
    command  = geolayer.make_command(
        payload["geo_input"],
        payload["geo_output"],
        payload["geo_args"]
    )
    assert command.startswith(
        "checkOverlaps --tolerance 0.01 -c ./epic/my_epic.xml"
        " >& overlap_output.log\ngrep"
    )
    assert ":[[:space:]]*0[[:space:]]*$" in command


def test_epic_sim_layer():
    """Validate EpicSimLayer functionality"""
    payload  = _make_epic_stack_payload()
    simlayer = EpicSimLayer()
    command  = simlayer.make_command(
        payload["sim_input"],
        payload["sim_output"],
        payload["sim_args"]
    )
    assert command == "npsim --compactFile $DETECTOR_PATH/$DETECTOR_CONFIG.xml --numberOfEvents 100 --skipNEvents 10 --enableG4GPS -G --steeringFile steering_input.py -I hepmc_input.hepmc -I hepmc_tree_input.hepmc3.root --macroFile macro_input.mac --outputFile sim_output.edm4hep.root"


def test_epic_rec_layer():
    """Validate EpicRecLayer functionality"""
    payload  = _make_epic_stack_payload()
    reclayer = EpicRecLayer()
    command  = reclayer.make_command(
        payload["sim_output"],
        payload["rec_output"],
        payload["rec_args"]
    )
    assert command == "eicrecon -Pnthreads=8 -Pjana:global_loglevel=debug -Ppodio:output_file=rec_output.edm4eic.root sim_output.edm4hep.root"


def test_epic_stack():
    """Validate EpicStack functionality"""
    payload = _make_epic_stack_payload()
    epstack = EpicStack()
    assert isinstance(epstack, EpicStack)
    assert isinstance(epstack["geo"], EpicGeoLayer)
    assert isinstance(epstack["sim"], EpicSimLayer)
    assert isinstance(epstack["rec"], EpicRecLayer)
    assert isinstance(epstack["ana"], EpicAnaLayer)

    geocomm = epstack["geo"].make_command(
        payload["geo_input"],
        payload["geo_output"],
        payload["geo_args"]
    )
    simcomm = epstack["sim"].make_command(
        payload["sim_input"],
        payload["sim_output"],
        payload["sim_args"]
    )
    reccomm = epstack["rec"].make_command(
        payload["sim_output"],
        payload["rec_output"],
        payload["rec_args"]
    )
    assert ":[[:space:]]*0[[:space:]]*$" in geocomm
    assert simcomm == "npsim --compactFile $DETECTOR_PATH/$DETECTOR_CONFIG.xml --numberOfEvents 100 --skipNEvents 10 --enableG4GPS -G --steeringFile steering_input.py -I hepmc_input.hepmc -I hepmc_tree_input.hepmc3.root --macroFile macro_input.mac --outputFile sim_output.edm4hep.root"
    assert reccomm == "eicrecon -Pnthreads=8 -Pjana:global_loglevel=debug -Ppodio:output_file=rec_output.edm4eic.root sim_output.edm4hep.root"
