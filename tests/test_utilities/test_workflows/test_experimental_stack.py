"""Tests for experimental stacks and layers."""

from dataclasses import dataclass, field
from typing import Dict, Any, List 
from aid2e.utilities.workflows import (
    AnaLayer,
    ExperimentStack,
    StackLayer
)


def _make_ana_layer_payload() -> Dict[str, Any]:
    """Build a dictionary of AnaLayer details, inputs, outputs, arguments for test."""
    return {
        "ana_details": {
            "name": "test_ana",
            "command": "python run_test_ana.py",
            "rule": "{{command}} {{arguments}} -I {{inputs}} -O {{outputs}}",
        },
        "ana_input": [
            "ana_input.root",
        ],
        "ana_output": [
            "ana_output.root",
        ],
        "ana_args": [
            "-P 22",
        ],
    }


def _make_experiment_stack_payload() -> Dict[str, Any]:
    """Build a dictionary of stack details, inputs, outputs for test"""
    return {
        "sim_details" : {
            "name"    : "sim",
            "command" : "dosim",
            "rule"    : '{{command}} {{arguments}} -I {{inputs}} -O {{outputs}}'
        },
        "sim_input" : [
            "sim_input.root",
        ],
        "sim_output" : [
            "sim_output.root",
        ],
        "sim_args" : [
            "--physicsList QBert.yaml",
        ]
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


def test_experiment_stack():
    """Validate ExperimentStack functionality"""
    payload = _make_experiment_stack_payload()
    class MySimLayer(StackLayer):
        name    = payload["sim_details"]["name"]
        command = payload["sim_details"]["command"]
        rule    = payload["sim_details"]["rule"]
        def _make_input_arg(self, inputs: List[str]) -> str:
            return ' '.join(inputs)
        def _make_output_arg(self, outputs: List[str]) -> str:
            return ' '.join(outputs)

    @dataclass
    class MyExperimentStack(ExperimentStack):
        sim: MySimLayer = field(default_factory = MySimLayer)

        def make_driver_command(self, script: str) -> str:
            return f"./{script}"

    mystack = MyExperimentStack()
    assert isinstance(mystack, MyExperimentStack)
    assert isinstance(mystack[payload["sim_details"]["name"]], MySimLayer)

    command = mystack[payload["sim_details"]["name"]].make_command(
        payload["sim_input"],
        payload["sim_output"],
        payload["sim_args"]
    )
    assert command == "dosim --physicsList QBert.yaml -I sim_input.root -O sim_output.root"
