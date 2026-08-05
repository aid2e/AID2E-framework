#!/usr/bin/env python
"""Compute DTLZ2 objectives from direct CLI arguments and write JSON output."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--x1", type=float, required=True)
    parser.add_argument("--x2", type=float, required=True)
    parser.add_argument("--x3", type=float, required=True)
    parser.add_argument("--x4", type=float, required=True)
    parser.add_argument("--x5", type=float, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", type=str, default="slurm-dtlz2")
    parser.add_argument("--sleep-sec", type=float, default=0.0)
    parser.add_argument("--repeat", type=int, default=2)
    return parser.parse_args()


def compute_objectives(x1: float, x2: float, x3: float, x4: float, x5: float) -> dict[str, float]:
    tail = [x2, x3, x4, x5]
    g = sum((value - 0.5) ** 2 for value in tail)
    factor = 1.0 + g
    f1 = factor * math.cos(x1 * math.pi / 2.0)
    f2 = factor * math.sin(x1 * math.pi / 2.0)
    return {"f1": float(f1), "f2": float(f2)}


def main() -> int:
    args = parse_args()
    for step in range(args.repeat):
        print(f"[{args.label}] progress {step + 1}/{args.repeat}", flush=True)
        print(f"[{args.label}] stderr heartbeat {step + 1}", file=sys.stderr, flush=True)
        if args.sleep_sec > 0:
            time.sleep(args.sleep_sec)

    payload = compute_objectives(args.x1, args.x2, args.x3, args.x4, args.x5)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
