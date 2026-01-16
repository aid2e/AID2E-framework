"""Tests for experimental stacks and layers."""

from aid2e.utilities.workflows import (
    AnaLayer
)


def _make_ana_layer_payload() -> dict:
    """Build a dictionary of AnaLayer details, inputs, outputs, and arguments for test."""
    return {
        "ana_details" : {
            "name"    : "test_ana",
            "command" : "python run_test_ana.py",
            "rule"    : "{command} {arguments} -I {inputs} -O {outputs}"
        },
        "ana_input" : [
            "ana_input.root",
        ],
        "ana_output" : [
            "ana_output.root",
        ],
        "ana_args" : [
            "-P 22",
        ],
    }


def test_ana_layer():
    """Validate AnaLayer functionality"""
    payload          = _make_ana_layer_payload()
    analayer         = AnaLayer()
    analayer.name    = payload["ana_details"]["name"]
    analayer.command = payload["ana_details"]["command"]
    analayer.rule    = payload["ana_details"]["rule"]
    assert analayer.name == payload["ana_details"]["name"]
    assert analayer.command == payload["ana_details"]["command"]
    assert analayer.rule == payload["ana_details"]["rule"]

    command = analayer.make_command(
        payload["ana_input"],
        payload["ana_output"],
        payload["ana_args"]
    )
    assert command == "python run_test_ana.py -P 22 -I ana_input.root -O ana_output.root"
