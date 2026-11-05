"""Plot hypervolume against trial index from AID2E optimization_results.json files.

For one results file the plot shows the Pareto-front hypervolume after each
trial (line) and each trial's own hypervolume, the box between the trial and
the reference point (dots, colored by where the trial came from: KB warm start,
Sobol, BoTorch, ...). For several files only the front lines are drawn, so runs
can be compared (e.g. with and without KB warm start).

Usage:
    python examples/dtlz2/plot_hypervolume.py RESULTS.json [RESULTS2.json ...] \
        [--ref 2.0 2.0] [--maximize f2] [--optimum 3.2146] [-o hv.png]
    python examples/dtlz2/plot_hypervolume.py \
        --dir output/ax_joblib_kb output/ax_joblib --runs 20261105_0905,20261105_0958

The default reference point is 2.0 per objective, the fixed DTLZ2 point used by
the Ax configs (best possible hypervolume 4 - pi/4 = 3.2146, drawn as the
dashed line by default for two-objective runs).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

# Reference palette (dataviz skill): categorical slots in fixed order.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_SECONDARY = "#52514e"
GRID = "#e6e5e0"

# Fixed slot per trial source, so a source keeps its color across plots.
SOURCE_ORDER = ["KB warm start", "Sobol", "ModularBoTorch", "Imported", "Other"]


def trial_source(trial: dict) -> str:
    meta = trial.get("metadata") or {}
    if meta.get("ax_model_key") == "kb_warm_start" or "kb_source" in meta:
        return "KB warm start"
    if meta.get("warm_started"):
        return "Imported"
    node = meta.get("ax_node_name")
    if node in SOURCE_ORDER:
        return node
    return node or "Other"


def to_min_space(values: Sequence[float], ref: Sequence[float], signs: Sequence[float]):
    """Map objectives so every one is minimized: multiply by +1 (min) or -1 (max)."""
    return [v * s for v, s in zip(values, signs)], [r * s for r, s in zip(ref, signs)]


def point_hv(point: Sequence[float], ref: Sequence[float]) -> float:
    volume = 1.0
    for p, r in zip(point, ref):
        if p >= r:
            return 0.0
        volume *= r - p
    return volume


def front_hv(points: List[Sequence[float]], ref: Sequence[float]) -> float:
    """Exact hypervolume (minimization) of ``points`` up to ``ref``."""
    inside = [p for p in points if all(pi < ri for pi, ri in zip(p, ref))]
    if not inside:
        return 0.0
    if len(ref) == 2:
        volume, best_f2 = 0.0, ref[1]
        for f1, f2 in sorted(inside):
            if f2 < best_f2:
                volume += (ref[0] - f1) * (best_f2 - f2)
                best_f2 = f2
        return volume
    import numpy as np
    from pymoo.indicators.hv import HV

    return float(HV(ref_point=np.array(ref))(np.array(inside)))


def load_run(path: Path, ref_arg: Optional[List[float]], maximize: List[str]):
    data = json.loads(path.read_text())
    names = data["objective_names"]
    ref = ref_arg if ref_arg is not None else [2.0] * len(names)
    if len(ref) != len(names):
        raise SystemExit(f"--ref needs {len(names)} values ({', '.join(names)}), got {len(ref)}")
    signs = [-1.0 if n in maximize else 1.0 for n in names]

    rows: List[Tuple[int, float, float, str]] = []  # (trial, point hv, front hv, source)
    seen: List[List[float]] = []
    trials = sorted(data["trials"], key=lambda t: t["trial_index"])
    for trial in trials:
        if trial.get("status") != "completed":
            continue
        objectives = trial.get("objectives") or {}
        values = [objectives.get(n) for n in names]
        if any(v is None or not math.isfinite(float(v)) for v in values):
            continue
        point, ref_min = to_min_space([float(v) for v in values], ref, signs)
        seen.append(point)
        rows.append((trial["trial_index"], point_hv(point, ref_min), front_hv(seen, ref_min),
                     trial_source(trial)))
    return names, ref, rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("results", nargs="*", type=Path, help="optimization_results.json file(s)")
    parser.add_argument("--dir", nargs="+", type=Path, default=[], dest="dirs",
                        help="output folder(s) holding run folders, e.g. output/ax_joblib_kb")
    parser.add_argument("--runs", default="",
                        help="comma-separated run IDs inside --dir, e.g. 20261105_0905,20261105_0958 "
                             "(default: every run found)")
    parser.add_argument("--ref", nargs="+", type=float, help="reference point, one value per objective")
    parser.add_argument("--maximize", nargs="*", default=[], help="objectives that are maximized")
    parser.add_argument("--optimum", type=float, help="best possible hypervolume (dashed line)")
    parser.add_argument("--labels", nargs="*", help="legend label per results file")
    parser.add_argument("-o", "--output", type=Path, default=Path("hypervolume.png"))
    args = parser.parse_args()

    paths = list(args.results)
    run_ids = [r.strip() for r in args.runs.split(",") if r.strip()]
    for folder in args.dirs:
        if run_ids:
            for run_id in run_ids:
                path = folder / run_id / "optimization_results.json"
                if path.is_file():
                    paths.append(path)
                else:
                    print(f"Skipping {folder.name}/{run_id}: no optimization_results.json")
        else:
            paths.extend(sorted(folder.glob("*/optimization_results.json")))
    if not paths:
        parser.error("no results found: give results files, or --dir with existing runs")

    runs = [load_run(p, args.ref, args.maximize) for p in paths]
    names, ref = runs[0][0], runs[0][1]
    labels = args.labels or [f"{p.parent.parent.name}/{p.parent.name}" for p in paths]
    optimum = args.optimum
    if optimum is None and len(names) == 2 and ref == [2.0, 2.0] and not args.maximize:
        optimum = 4 - math.pi / 4  # DTLZ2 with ref (2, 2)

    plt.rcParams.update({
        "font.size": 10, "axes.edgecolor": TEXT_SECONDARY, "axes.labelcolor": TEXT_SECONDARY,
        "xtick.color": TEXT_SECONDARY, "ytick.color": TEXT_SECONDARY, "text.color": TEXT,
    })
    fig, ax = plt.subplots(figsize=(9, 5), facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)

    if len(runs) == 1:
        rows = runs[0][2]
        sources = sorted({r[3] for r in rows},
                         key=lambda s: SOURCE_ORDER.index(s) if s in SOURCE_ORDER else 99)
        for slot, source in enumerate(sources):
            pts = [r for r in rows if r[3] == source]
            ax.scatter([r[0] for r in pts], [r[1] for r in pts], s=28, color=SERIES[slot + 1],
                       edgecolors=SURFACE, linewidths=1.0, zorder=3,
                       label=f"Trial hypervolume: {source} ({len(pts)})")
        ax.step([r[0] for r in rows], [r[2] for r in rows], where="post", color=SERIES[0],
                linewidth=2, zorder=4, label="Front hypervolume")
        last = rows[-1]
        ax.annotate(f"{last[2]:.3f}", (last[0], last[2]), xytext=(6, 0),
                    textcoords="offset points", va="center", color=TEXT)
    else:
        for slot, ((_, _, rows), label) in enumerate(zip(runs, labels)):
            ax.step([r[0] for r in rows], [r[2] for r in rows], where="post",
                    color=SERIES[slot % len(SERIES)], linewidth=2,
                    label=f"{label} (final {rows[-1][2]:.3f})")

    if optimum is not None:
        ax.axhline(optimum, color=TEXT_SECONDARY, linewidth=1, linestyle="--", zorder=2)
        ax.annotate(f"Optimum {optimum:.4f}", (0, optimum), xytext=(2, 4),
                    textcoords="offset points", color=TEXT_SECONDARY, fontsize=9)

    ref_text = ", ".join(f"{n}={r:g}" for n, r in zip(names, ref))
    ax.set_title(f"Hypervolume by trial (reference point {ref_text})", loc="left", color=TEXT)
    ax.set_xlabel("Trial index")
    ax.set_ylabel("Hypervolume")
    ax.set_ylim(bottom=0)
    ax.legend(frameon=False, loc="lower right", fontsize=9)
    fig.tight_layout()
    fig.savefig(args.output, dpi=150, facecolor=SURFACE)
    print(f"Saved {args.output}")
    for (_, _, rows), label in zip(runs, labels):
        inside = sum(1 for r in rows if r[1] > 0)
        print(f"{label}: {len(rows)} trials, final front HV {rows[-1][2]:.4f}, "
              f"{inside} trial(s) inside the reference box")


if __name__ == "__main__":
    main()
