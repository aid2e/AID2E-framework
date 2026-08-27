#!/usr/bin/env python
"""Compute DTLZ2 objectives from a design-point JSON file and write JSON output."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Dict


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", type=str, default="slurm-dtlz2")
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--repeat", type=int, default=2)
    return parser.parse_args()


def load_design(path: Path) -> Dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = [
        "DTLZ2_variables.x1",
        "DTLZ2_variables.x2",
        "DTLZ2_variables.x3",
        "DTLZ2_variables.x4",
        "DTLZ2_variables.x5",
    ]
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError(f"Design file {path} is missing required keys: {missing}")
    return payload


def compute_objectives(parameters: Dict[str, Any]) -> Dict[str, float]:
    x1 = float(parameters["DTLZ2_variables.x1"])
    tail = [
        float(parameters["DTLZ2_variables.x2"]),
        float(parameters["DTLZ2_variables.x3"]),
        float(parameters["DTLZ2_variables.x4"]),
        float(parameters["DTLZ2_variables.x5"]),
    ]
    g = sum((value - 0.5) ** 2 for value in tail)
    factor = 1.0 + g
    f1 = factor * math.cos(x1 * math.pi / 2.0)
    f2 = factor * math.sin(x1 * math.pi / 2.0)
    return {"f1": float(f1), "f2": float(f2)}


def main() -> int:
    args = parse_args()
    design = load_design(args.design)

    print(f"[{args.label}] design file: {args.design}", flush=True)
    for step in range(args.repeat):
        print(f"[{args.label}] progress {step + 1}/{args.repeat}", flush=True)
        print(f"[{args.label}] stderr heartbeat {step + 1}", file=sys.stderr, flush=True)
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    payload = compute_objectives(design)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
