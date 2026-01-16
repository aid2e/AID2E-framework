"""Tests for epic stack utilities."""

from aid2e.utilities.epic_utils.epic_stack import (
    EpicSimLayer,
    EpicRecLayer,
    EpicAnaLayer
)


def _make_epic_stack_payload() -> dict:
    """Build a dictionary of epic stack layer inputs, outputs, and arguments for tests."""
    return {
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


def test_epic_sim_layer():
    """Validate EpicSimLayer functionality"""
    payload  = _make_epic_stack_payload()
    simlayer = EpicSimLayer()
    command  = simlayer.make_command(
        payload["sim_input"],
        payload["sim_output"],
        payload["sim_args"]
    )
    assert command == "npsim --numberOfEvents 100 --skipNEvents 10 --steeringFile steering_input.py -I hepmc_input.hepmc -I hepmc_tree_input.hepmc3.root --macroFile macro_input.mac --outputFile sim_output.edm4hep.root"


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
