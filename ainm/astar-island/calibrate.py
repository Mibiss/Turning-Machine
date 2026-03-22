#!/usr/bin/env python3
"""
Astar Island — Prior Calibration Tool
======================================
Pulls ground truth analysis data from completed rounds, compares it against
the current terrain priors, and outputs tuned prior values to drop into main.py.

Usage:
    export ASTAR_TOKEN=<your_jwt_token>
    python3 calibrate.py

    # Save raw analysis data to disk:
    python3 calibrate.py --save-data ./calibration_data

    # Load previously saved data (no API calls):
    python3 calibrate.py --load-data ./calibration_data

    # Output just the replacement code block for main.py:
    python3 calibrate.py --emit-priors
"""

import argparse
import os
import sys
import json
import logging
from collections import defaultdict

import numpy as np
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("calibrate")

BASE_URL = "https://api.ainm.no"

# Terrain codes
OCEAN      = 10
PLAINS     = 11
EMPTY      = 0
SETTLEMENT = 1
PORT       = 2
RUIN       = 3
FOREST     = 4
MOUNTAIN   = 5

# Class indices
C_EMPTY      = 0
C_SETTLEMENT = 1
C_PORT       = 2
C_RUIN       = 3
C_FOREST     = 4
C_MOUNTAIN   = 5
N_CLASSES    = 6

CLASS_NAMES = ["empty", "settlement", "port", "ruin", "forest", "mountain"]

STATIC_TERRAINS = {OCEAN, MOUNTAIN}
DYNAMIC_TERRAINS = {PLAINS, EMPTY, SETTLEMENT, PORT, RUIN, FOREST}

TERRAIN_NAMES = {
    OCEAN:      "ocean",
    PLAINS:     "plains",
    EMPTY:      "empty",
    SETTLEMENT: "settlement",
    PORT:       "port",
    RUIN:       "ruin",
    FOREST:     "forest",
    MOUNTAIN:   "mountain",
}


# ─── API Client ───────────────────────────────────────────────────────────────

class AstarClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get_my_rounds(self) -> list:
        r = self.session.get(f"{BASE_URL}/astar-island/my-rounds")
        r.raise_for_status()
        return r.json()

    def get_round_detail(self, round_id: str) -> dict:
        r = self.session.get(f"{BASE_URL}/astar-island/rounds/{round_id}")
        r.raise_for_status()
        return r.json()

    def get_analysis(self, round_id: str, seed_index: int) -> dict:
        r = self.session.get(f"{BASE_URL}/astar-island/analysis/{round_id}/{seed_index}")
        r.raise_for_status()
        return r.json()


# ─── Data Collection ──────────────────────────────────────────────────────────

def collect_analysis_data(client: AstarClient, save_dir: str = None) -> list:
    """
    Fetch ground truth analysis for all completed rounds.
    Returns a list of records: {round_id, round_number, seed_index, initial_grid, ground_truth}
    """
    log.info("Fetching your round history...")
    my_rounds = client.get_my_rounds()

    completed = [r for r in my_rounds if r["status"] in ("completed", "scoring")]
    log.info("Found %d completed rounds.", len(completed))

    if not completed:
        log.error("No completed rounds yet — nothing to calibrate against.")
        log.error("Play a few rounds first, then run this tool.")
        sys.exit(1)

    records = []

    for rnd in completed:
        round_id     = rnd["id"]
        round_number = rnd["round_number"]
        n_seeds      = rnd.get("seeds_count", 5)

        log.info("Round %d — fetching detail...", round_number)
        try:
            detail = client.get_round_detail(round_id)
        except requests.HTTPError as e:
            log.warning("  Could not fetch detail for round %d: %s", round_number, e)
            continue

        initial_states = detail.get("initial_states", [])

        for seed_idx in range(n_seeds):
            log.info("  Seed %d — fetching analysis...", seed_idx)
            try:
                analysis = client.get_analysis(round_id, seed_idx)
            except requests.HTTPError as e:
                log.warning("  Could not fetch analysis for round %d seed %d: %s", round_number, seed_idx, e)
                continue

            initial_grid = None
            if analysis.get("initial_grid"):
                initial_grid = analysis["initial_grid"]
            elif seed_idx < len(initial_states):
                initial_grid = initial_states[seed_idx]["grid"]

            if initial_grid is None:
                log.warning("  No initial grid for round %d seed %d, skipping.", round_number, seed_idx)
                continue

            record = {
                "round_id":     round_id,
                "round_number": round_number,
                "seed_index":   seed_idx,
                "score":        analysis.get("score"),
                "initial_grid": initial_grid,
                "ground_truth": analysis["ground_truth"],  # H×W×6 list
            }
            records.append(record)
            log.info(
                "  Round %d seed %d — score: %s",
                round_number, seed_idx,
                f"{analysis.get('score'):.1f}" if analysis.get("score") is not None else "n/a",
            )

    if save_dir:
        os.makedirs(save_dir, exist_ok=True)
        path = os.path.join(save_dir, "analysis_records.json")
        with open(path, "w") as f:
            json.dump(records, f)
        log.info("Saved %d records to %s", len(records), path)

    return records


def load_analysis_data(load_dir: str) -> list:
    path = os.path.join(load_dir, "analysis_records.json")
    if not os.path.exists(path):
        log.error("No data file found at %s", path)
        sys.exit(1)
    with open(path) as f:
        records = json.load(f)
    log.info("Loaded %d records from %s", len(records), path)
    return records


# ─── Calibration Engine ───────────────────────────────────────────────────────

def calibrate(records: list) -> dict:
    """
    For each initial terrain type, accumulate the ground truth distributions
    from all completed rounds and compute the empirical mean.

    Returns:
        calibrated_priors[terrain_code] = np.array of shape (6,) — mean ground truth dist
    """
    # accumulate[terrain_code] = list of (6,) ground truth vectors
    accumulate = defaultdict(list)
    cell_count  = defaultdict(int)

    for record in records:
        initial_grid = np.array(record["initial_grid"], dtype=np.int32)
        ground_truth = np.array(record["ground_truth"], dtype=np.float32)  # H×W×6
        H, W = initial_grid.shape

        for y in range(H):
            for x in range(W):
                terrain = initial_grid[y, x]
                if terrain in STATIC_TERRAINS:
                    continue  # skip ocean and mountain — they never change
                gt_dist = ground_truth[y, x]  # shape (6,)
                accumulate[terrain].append(gt_dist)
                cell_count[terrain] += 1

    calibrated = {}
    for terrain, dists in accumulate.items():
        arr = np.array(dists)  # shape (N, 6)
        mean_dist = arr.mean(axis=0)
        mean_dist = np.maximum(mean_dist, 0.001)
        mean_dist /= mean_dist.sum()
        calibrated[terrain] = mean_dist

    return calibrated, cell_count


# ─── Spatial Calibration ─────────────────────────────────────────────────────

DIST_BIN_LABELS = {0: "0-2", 1: "3-5", 2: "6+"}


def _compute_settlement_distance(initial_grid: np.ndarray) -> np.ndarray:
    H, W = initial_grid.shape
    settle_mask = (initial_grid == SETTLEMENT) | (initial_grid == PORT)
    sy, sx = np.where(settle_mask)
    if len(sx) == 0:
        return np.full((H, W), 999, dtype=np.int32)
    X = np.arange(W, dtype=np.int32)[None, None, :]
    Y = np.arange(H, dtype=np.int32)[None, :, None]
    d = np.maximum(np.abs(X - sx[:, None, None]), np.abs(Y - sy[:, None, None]))
    return d.min(axis=0).astype(np.int32)


def _compute_coast_mask(initial_grid: np.ndarray, radius: int = 2) -> np.ndarray:
    ocean = (initial_grid == OCEAN).astype(np.float32)
    try:
        from scipy.ndimage import maximum_filter
        return maximum_filter(ocean, size=2 * radius + 1).astype(bool)
    except ImportError:
        H, W = initial_grid.shape
        mask = np.zeros((H, W), dtype=bool)
        oy, ox = np.where(ocean > 0)
        for cy, cx in zip(oy, ox):
            y0, y1 = max(0, cy - radius), min(H, cy + radius + 1)
            x0, x1 = max(0, cx - radius), min(W, cx + radius + 1)
            mask[y0:y1, x0:x1] = True
        return mask


def calibrate_spatial(records: list, save_path: str = None) -> dict:
    """
    Bin ground truth by (terrain, settlement_dist_bin, coastal) and compute
    empirical mean distributions for each bin.

    Distance bins: 0-2, 3-5, 6+
    Coastal: within 2 cells of ocean (bool)

    Returns dict keyed by "terrain|dist_bin|coastal_label" with probs and counts.
    """
    accumulate = defaultdict(list)
    counts = defaultdict(int)

    for record in records:
        initial_grid = np.array(record["initial_grid"], dtype=np.int32)
        ground_truth = np.array(record["ground_truth"], dtype=np.float32)
        H, W = initial_grid.shape

        settle_dist = _compute_settlement_distance(initial_grid)
        coast = _compute_coast_mask(initial_grid)
        dist_bin = np.where(settle_dist <= 2, 0, np.where(settle_dist <= 5, 1, 2))

        for y in range(H):
            for x in range(W):
                terrain = int(initial_grid[y, x])
                if terrain in STATIC_TERRAINS:
                    continue
                db = int(dist_bin[y, x])
                c = bool(coast[y, x])
                key = (terrain, db, c)
                accumulate[key].append(ground_truth[y, x])
                counts[key] += 1

    spatial_priors = {}
    for key in sorted(accumulate.keys()):
        terrain, db, coastal = key
        if terrain not in TERRAIN_NAMES:
            continue
        arr = np.array(accumulate[key])
        mean_dist = arr.mean(axis=0)
        mean_dist = np.maximum(mean_dist, 0.001)
        mean_dist /= mean_dist.sum()

        tname = TERRAIN_NAMES[terrain]
        coast_label = "coastal" if coastal else "inland"
        skey = f"{tname}|{DIST_BIN_LABELS[db]}|{coast_label}"
        spatial_priors[skey] = {
            "terrain": terrain,
            "dist_bin": DIST_BIN_LABELS[db],
            "coastal": coastal,
            "count": int(counts[key]),
            "probs": [float(v) for v in mean_dist],
        }

    log.info("Computed %d spatial prior bins", len(spatial_priors))
    for skey, info in spatial_priors.items():
        log.info(
            "  %s  n=%d  probs=[%s]",
            skey, info["count"],
            ", ".join(f"{v:.4f}" for v in info["probs"]),
        )

    if save_path:
        os.makedirs(os.path.dirname(save_path) or ".", exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(spatial_priors, f, indent=2)
        log.info("Saved spatial priors to %s", save_path)

    return spatial_priors


# ─── Reporting ────────────────────────────────────────────────────────────────

# Current hand-crafted priors from main.py (for comparison)
CURRENT_PRIORS = {
    FOREST: {
        "label": "forest",
        "probs": [0.10, 0.02, 0.01, 0.04, 0.78, 0.02],  # approximate (no spatial context)
    },
    SETTLEMENT: {
        "label": "settlement",
        "probs": [0.05, 0.50, 0.03, 0.22, 0.02, 0.00],
    },
    PORT: {
        "label": "port",
        "probs": [0.08, 0.12, 0.48, 0.24, 0.02, 0.00],
    },
    RUIN: {
        "label": "ruin",
        "probs": [0.20, 0.03, 0.01, 0.30, 0.20, 0.00],
    },
    PLAINS: {
        "label": "plains/empty",
        "probs": [0.70, 0.02, 0.01, 0.02, 0.12, 0.00],
    },
}


def print_report(calibrated: dict, cell_count: dict):
    print("\n" + "=" * 70)
    print("CALIBRATION REPORT")
    print("=" * 70)
    print(f"{'Terrain':<12}  {'N cells':>8}  {'empty':>7} {'settle':>7} {'port':>7} {'ruin':>7} {'forest':>7} {'mount':>7}")
    print("-" * 70)

    for terrain in [PLAINS, EMPTY, SETTLEMENT, PORT, RUIN, FOREST]:
        if terrain not in calibrated:
            continue
        p = calibrated[terrain]
        n = cell_count[terrain]
        name = TERRAIN_NAMES[terrain]
        print(
            f"{name:<12}  {n:>8}  "
            f"{p[0]:>7.3f} {p[1]:>7.3f} {p[2]:>7.3f} "
            f"{p[3]:>7.3f} {p[4]:>7.3f} {p[5]:>7.3f}"
        )

    print("\n" + "=" * 70)
    print("DELTA vs CURRENT PRIORS  (calibrated − current)")
    print("=" * 70)
    print(f"{'Terrain':<12}  {'empty':>7} {'settle':>7} {'port':>7} {'ruin':>7} {'forest':>7} {'mount':>7}")
    print("-" * 70)

    for terrain, info in CURRENT_PRIORS.items():
        if terrain not in calibrated:
            continue
        cal = calibrated[terrain]
        cur = np.array(info["probs"])
        delta = cal - cur
        name = info["label"]
        parts = []
        for d in delta:
            marker = "▲" if d > 0.05 else ("▼" if d < -0.05 else " ")
            parts.append(f"{marker}{d:+.3f}")
        print(f"{name:<12}  " + "  ".join(f"{p:>7}" for p in parts))

    print()


def emit_priors_code(calibrated: dict):
    """Print replacement prior code to paste into main.py's _terrain_prior method."""
    print("\n" + "=" * 70)
    print("REPLACEMENT PRIOR CODE — paste into _terrain_prior() in main.py")
    print("=" * 70)
    print()

    terrain_map = {
        FOREST:     "FOREST",
        SETTLEMENT: "SETTLEMENT",
        PORT:       "PORT",
        RUIN:       "RUIN",
        PLAINS:     "PLAINS",
        EMPTY:      "EMPTY",
    }

    for terrain, varname in terrain_map.items():
        if terrain not in calibrated:
            continue
        p = calibrated[terrain]
        print(f"        # Calibrated from {cell_count.get(terrain, '?')} observed cells")
        print(f"        elif terrain == {varname}:")
        print(f"            p[C_EMPTY]      = {p[C_EMPTY]:.4f}")
        print(f"            p[C_SETTLEMENT] = {p[C_SETTLEMENT]:.4f}")
        print(f"            p[C_PORT]       = {p[C_PORT]:.4f}")
        print(f"            p[C_RUIN]       = {p[C_RUIN]:.4f}")
        print(f"            p[C_FOREST]     = {p[C_FOREST]:.4f}")
        print(f"            p[C_MOUNTAIN]   = {p[C_MOUNTAIN]:.4f}")
        print()


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Calibrate Astar Island terrain priors from completed rounds",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--token",       default=os.environ.get("ASTAR_TOKEN", ""), help="JWT token")
    parser.add_argument("--save-data",   metavar="DIR", help="Save raw analysis data to DIR")
    parser.add_argument("--load-data",   metavar="DIR", help="Load saved analysis data from DIR")
    parser.add_argument("--emit-priors", action="store_true", help="Output replacement prior code for main.py")
    args = parser.parse_args()

    if args.load_data:
        records = load_analysis_data(args.load_data)
    else:
        if not args.token:
            print(
                "\n  ERROR: No JWT token provided.\n"
                "  Set it with:  export ASTAR_TOKEN=<your_token>\n"
            )
            sys.exit(1)
        client = AstarClient(args.token)
        records = collect_analysis_data(client, save_dir=args.save_data)

    if not records:
        log.error("No analysis records collected.")
        sys.exit(1)

    log.info("Calibrating from %d seed records...", len(records))
    global cell_count
    calibrated, cell_count = calibrate(records)

    print_report(calibrated, cell_count)

    # Spatial calibration — always run alongside flat calibration
    spatial_dir = args.save_data or args.load_data or "calibration_data"
    spatial_path = os.path.join(spatial_dir, "spatial_priors.json")
    calibrate_spatial(records, save_path=spatial_path)

    if args.emit_priors:
        emit_priors_code(calibrated)
    else:
        print("Tip: run with --emit-priors to get replacement code for main.py")


if __name__ == "__main__":
    main()