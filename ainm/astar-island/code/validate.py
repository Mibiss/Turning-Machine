#!/usr/bin/env python3
"""
Astar Island — Validation (Leave-One-Round-Out Cross-Validation)
=================================================================
Validates conditioned priors, simulator, and blended predictions against
90 ground truth records.

Usage:
    python validate.py --method conditioned-prior   # target score > 74
    python validate.py --method simulator            # target score > 74
    python validate.py --method blended              # target score > 81
    python validate.py --method all                  # run all methods
    python validate.py --method static-baseline      # current static prior baseline
"""

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict

import numpy as np

# Add code directory to path
sys.path.insert(0, os.path.dirname(__file__))

from param_inference import ExpansionEstimator
from conditioned_prior import ConditionedPriorBuilder
from simulator import SimParamMapper, run_monte_carlo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("validate")

# ─── Constants ────────────────────────────────────────────────────────────────
OCEAN      = 10
PLAINS     = 11
EMPTY      = 0
SETTLEMENT = 1
PORT       = 2
RUIN       = 3
FOREST     = 4
MOUNTAIN   = 5

C_EMPTY      = 0
C_SETTLEMENT = 1
C_PORT       = 2
C_RUIN       = 3
C_FOREST     = 4
C_MOUNTAIN   = 5
N_CLASSES    = 6
PROB_FLOOR   = 0.01

_TERRAIN_KEY_NAME = {
    FOREST:     "forest",
    SETTLEMENT: "settlement",
    PORT:       "port",
    RUIN:       "ruin",
    PLAINS:     "plains",
    EMPTY:      "plains",
}


# ─── Scoring ─────────────────────────────────────────────────────────────────

def kl_divergence(pred, gt, initial_grid):
    """Compute mean KL divergence per dynamic cell (competition scoring)."""
    pred_safe = np.maximum(pred, 1e-10)
    gt_safe = np.maximum(gt, 1e-10)
    kl_per_cell = np.sum(gt_safe * np.log(gt_safe / pred_safe), axis=-1)
    dynamic_mask = ~((initial_grid == OCEAN) | (initial_grid == MOUNTAIN))
    if dynamic_mask.sum() == 0:
        return 0.0
    return float(kl_per_cell[dynamic_mask].mean())


def kl_to_score(kl):
    """Approximate competition score from KL divergence.

    Based on observed relationship: score ≈ 100 * (1 - kl / ln(6))
    This is a rough approximation; actual scoring may differ slightly.
    """
    return max(0.0, 100.0 * (1.0 - kl / np.log(6)))


def apply_hard_constraints(pred, initial_grid):
    """Apply ocean/mountain hard constraints."""
    out = np.array(pred, dtype=np.float64, copy=True)
    m_mtn = initial_grid == MOUNTAIN
    m_ocn = initial_grid == OCEAN
    out[m_mtn] = PROB_FLOOR
    out[m_mtn, C_MOUNTAIN] = 1.0 - (N_CLASSES - 1) * PROB_FLOOR
    out[m_ocn] = PROB_FLOOR
    out[m_ocn, C_EMPTY] = 1.0 - (N_CLASSES - 1) * PROB_FLOOR
    return out / out.sum(axis=-1, keepdims=True)


def apply_floor_and_normalize(pred):
    pred = np.maximum(pred, PROB_FLOOR)
    return pred / pred.sum(axis=-1, keepdims=True)


# ─── Static Baseline (current main2.py approach) ────────────────────────────

def _compute_settlement_distance(ig):
    H, W = ig.shape
    settle_mask = (ig == SETTLEMENT) | (ig == PORT)
    sy, sx = np.where(settle_mask)
    if len(sx) == 0:
        return np.full((H, W), 999, dtype=np.int32)
    X = np.arange(W, dtype=np.int32)[None, None, :]
    Y = np.arange(H, dtype=np.int32)[None, :, None]
    d = np.maximum(np.abs(X - sx[:, None, None]), np.abs(Y - sy[:, None, None]))
    return d.min(axis=0).astype(np.int32)


def _compute_coast_mask(ig, radius=2):
    ocean = (ig == OCEAN).astype(np.float32)
    try:
        from scipy.ndimage import maximum_filter
        return maximum_filter(ocean, size=2 * radius + 1).astype(bool)
    except ImportError:
        H, W = ig.shape
        mask = np.zeros((H, W), dtype=bool)
        oy, ox = np.where(ocean > 0)
        for cy, cx in zip(oy, ox):
            y0, y1 = max(0, cy - radius), min(H, cy + radius + 1)
            x0, x1 = max(0, cx - radius), min(W, cx + radius + 1)
            mask[y0:y1, x0:x1] = True
        return mask


def build_static_spatial_prior(ig, spatial_priors_path=None):
    """Build the same static spatial prior that main2.py uses."""
    if spatial_priors_path is None:
        spatial_priors_path = os.path.join(
            os.path.dirname(__file__), "calibration_data", "spatial_priors.json"
        )

    # Load spatial priors
    priors = {}
    if os.path.exists(spatial_priors_path):
        with open(spatial_priors_path) as f:
            data = json.load(f)
        for key, info in data.items():
            priors[key] = np.array(info["probs"], dtype=np.float64)

    H, W = ig.shape
    sdist = _compute_settlement_distance(ig)
    coast = _compute_coast_mask(ig)
    dist_bin = np.where(sdist <= 2, 0, np.where(sdist <= 5, 1, 2))
    dist_labels = {0: "0-2", 1: "3-5", 2: "6+"}

    p = np.full((H, W, N_CLASSES), 1.0 / N_CLASSES, dtype=np.float64)

    for terrain_code, tname in _TERRAIN_KEY_NAME.items():
        tmask = ig == terrain_code
        if not np.any(tmask):
            continue
        for db_idx, db_label in dist_labels.items():
            for is_coastal in (False, True):
                coast_label = "coastal" if is_coastal else "inland"
                key = f"{tname}|{db_label}|{coast_label}"
                prior_vec = priors.get(key)
                if prior_vec is None:
                    continue
                cell_mask = tmask & (dist_bin == db_idx)
                if is_coastal:
                    cell_mask = cell_mask & coast
                else:
                    cell_mask = cell_mask & ~coast
                if not np.any(cell_mask):
                    continue
                p[cell_mask] = prior_vec

    p = np.maximum(p, PROB_FLOOR)
    return p / p.sum(axis=-1, keepdims=True)


# ─── Validation Methods ─────────────────────────────────────────────────────

def validate_static_baseline(records):
    """Leave-one-round-out with static spatial priors (current main2.py approach)."""
    round_numbers = sorted(set(r["round_number"] for r in records))
    all_kls = []
    per_round = {}

    for hold_rnd in round_numbers:
        test_recs = [r for r in records if r["round_number"] == hold_rnd]
        round_kls = []

        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)

            pred = build_static_spatial_prior(ig)
            pred = apply_hard_constraints(pred, ig)
            pred = apply_floor_and_normalize(pred)

            kl = kl_divergence(pred, gt, ig)
            round_kls.append(kl)
            all_kls.append(kl)

        per_round[hold_rnd] = np.mean(round_kls)

    return all_kls, per_round


def validate_conditioned_prior(records):
    """Leave-one-round-out with expansion-conditioned priors."""
    round_numbers = sorted(set(r["round_number"] for r in records))
    all_kls = []
    per_round = {}

    cal_path = os.path.join(
        os.path.dirname(__file__), "calibration_data", "analysis_records.json"
    )

    for hold_rnd in round_numbers:
        test_recs = [r for r in records if r["round_number"] == hold_rnd]

        # Build conditioned prior excluding the held-out round
        builder = ConditionedPriorBuilder(
            calibration_path=cal_path,
            exclude_rounds={hold_rnd},
        )

        # Compute true expansion level from held-out round's GT
        exp_vals = []
        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)
            settle_mask = (ig == SETTLEMENT) | (ig == PORT)
            if settle_mask.any():
                survival = gt[settle_mask, C_SETTLEMENT] + gt[settle_mask, C_PORT]
                exp_vals.append(float(survival.mean()))
        true_expansion = float(np.mean(exp_vals)) if exp_vals else 0.33

        round_kls = []
        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)

            pred = builder.build_prior(ig, [], true_expansion)
            pred = apply_hard_constraints(pred, ig)
            pred = apply_floor_and_normalize(pred)

            kl = kl_divergence(pred, gt, ig)
            round_kls.append(kl)
            all_kls.append(kl)

        per_round[hold_rnd] = np.mean(round_kls)

    return all_kls, per_round


def validate_conditioned_prior_estimated(records):
    """LOO-CV with conditioned priors where expansion is estimated from
    other seeds in the same round (realistic scenario)."""
    round_numbers = sorted(set(r["round_number"] for r in records))
    all_kls = []
    per_round = {}

    cal_path = os.path.join(
        os.path.dirname(__file__), "calibration_data", "analysis_records.json"
    )

    for hold_rnd in round_numbers:
        round_recs = [r for r in records if r["round_number"] == hold_rnd]
        if len(round_recs) < 2:
            continue

        builder = ConditionedPriorBuilder(
            calibration_path=cal_path,
            exclude_rounds={hold_rnd},
        )

        round_kls = []
        for i, test_rec in enumerate(round_recs):
            # Estimate expansion from OTHER seeds in same round
            other_recs = [r for j, r in enumerate(round_recs) if j != i]
            exp_vals = []
            for rec in other_recs:
                ig = np.array(rec["initial_grid"], dtype=np.int32)
                gt = np.array(rec["ground_truth"], dtype=np.float64)
                settle_mask = (ig == SETTLEMENT) | (ig == PORT)
                if settle_mask.any():
                    survival = gt[settle_mask, C_SETTLEMENT] + gt[settle_mask, C_PORT]
                    exp_vals.append(float(survival.mean()))
            est_expansion = float(np.mean(exp_vals)) if exp_vals else 0.33

            ig = np.array(test_rec["initial_grid"], dtype=np.int32)
            gt = np.array(test_rec["ground_truth"], dtype=np.float64)

            pred = builder.build_prior(ig, [], est_expansion)
            pred = apply_hard_constraints(pred, ig)
            pred = apply_floor_and_normalize(pred)

            kl = kl_divergence(pred, gt, ig)
            round_kls.append(kl)
            all_kls.append(kl)

        if round_kls:
            per_round[hold_rnd] = np.mean(round_kls)

    return all_kls, per_round


def validate_simulator(records, n_sims=100, n_years=50):
    """LOO-CV with forward simulator."""
    round_numbers = sorted(set(r["round_number"] for r in records))
    all_kls = []
    per_round = {}

    cal_path = os.path.join(
        os.path.dirname(__file__), "calibration_data", "analysis_records.json"
    )

    estimator = ExpansionEstimator(cal_path)

    for hold_rnd in round_numbers:
        test_recs = [r for r in records if r["round_number"] == hold_rnd]

        # Use true expansion from GT
        exp_vals = []
        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)
            settle_mask = (ig == SETTLEMENT) | (ig == PORT)
            if settle_mask.any():
                survival = gt[settle_mask, C_SETTLEMENT] + gt[settle_mask, C_PORT]
                exp_vals.append(float(survival.mean()))
        true_expansion = float(np.mean(exp_vals)) if exp_vals else 0.33

        params = SimParamMapper.from_expansion(true_expansion)

        round_kls = []
        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)

            pred = run_monte_carlo(ig, [], params, n_sims=n_sims, n_years=n_years)
            pred = apply_hard_constraints(pred, ig)
            pred = apply_floor_and_normalize(pred)

            kl = kl_divergence(pred, gt, ig)
            round_kls.append(kl)
            all_kls.append(kl)

        per_round[hold_rnd] = np.mean(round_kls)
        log.info("  Round %d: KL=%.4f (expansion=%.3f)", hold_rnd, per_round[hold_rnd], true_expansion)

    return all_kls, per_round


def validate_blended(records, sim_weight=0.3, n_sims=100, n_years=50):
    """LOO-CV with blended conditioned prior + simulator."""
    round_numbers = sorted(set(r["round_number"] for r in records))
    all_kls = []
    per_round = {}

    cal_path = os.path.join(
        os.path.dirname(__file__), "calibration_data", "analysis_records.json"
    )

    for hold_rnd in round_numbers:
        test_recs = [r for r in records if r["round_number"] == hold_rnd]

        builder = ConditionedPriorBuilder(
            calibration_path=cal_path,
            exclude_rounds={hold_rnd},
        )

        # True expansion from GT
        exp_vals = []
        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)
            settle_mask = (ig == SETTLEMENT) | (ig == PORT)
            if settle_mask.any():
                survival = gt[settle_mask, C_SETTLEMENT] + gt[settle_mask, C_PORT]
                exp_vals.append(float(survival.mean()))
        true_expansion = float(np.mean(exp_vals)) if exp_vals else 0.33

        params = SimParamMapper.from_expansion(true_expansion)

        round_kls = []
        for rec in test_recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)

            prior_pred = builder.build_prior(ig, [], true_expansion)
            sim_pred = run_monte_carlo(ig, [], params, n_sims=n_sims, n_years=n_years)

            # Blend
            blended = (1 - sim_weight) * prior_pred + sim_weight * sim_pred
            blended = apply_hard_constraints(blended, ig)
            blended = apply_floor_and_normalize(blended)

            kl = kl_divergence(blended, gt, ig)
            round_kls.append(kl)
            all_kls.append(kl)

        per_round[hold_rnd] = np.mean(round_kls)
        log.info("  Round %d: KL=%.4f", hold_rnd, per_round[hold_rnd])

    return all_kls, per_round


# ─── Reporting ───────────────────────────────────────────────────────────────

def print_results(name, all_kls, per_round):
    """Print validation results."""
    mean_kl = np.mean(all_kls)
    std_kl = np.std(all_kls)
    approx_score = kl_to_score(mean_kl)

    print(f"\n{'=' * 70}")
    print(f"  {name}")
    print(f"{'=' * 70}")
    print(f"  Mean KL:  {mean_kl:.4f} (std={std_kl:.4f})")
    print(f"  Range:    [{min(all_kls):.4f}, {max(all_kls):.4f}]")
    print(f"  ~Score:   {approx_score:.1f}")
    print()

    if per_round:
        print(f"  {'Round':>6}  {'KL':>8}  {'~Score':>8}")
        print(f"  {'-' * 28}")
        for rnd in sorted(per_round.keys()):
            kl = per_round[rnd]
            score = kl_to_score(kl)
            print(f"  {rnd:>6}  {kl:>8.4f}  {score:>8.1f}")
        print()


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Validate Astar Island prediction methods via LOO-CV",
    )
    parser.add_argument(
        "--method",
        choices=["static-baseline", "conditioned-prior", "conditioned-estimated",
                 "simulator", "blended", "all"],
        default="all",
        help="Which method(s) to validate",
    )
    parser.add_argument("--sim-weight", type=float, default=0.3, help="Blend weight for simulator (0-1)")
    parser.add_argument("--n-sims", type=int, default=100, help="Monte Carlo simulations per cell")
    parser.add_argument("--n-years", type=int, default=50, help="Years per simulation")
    args = parser.parse_args()

    # Load ground truth records
    cal_path = os.path.join(
        os.path.dirname(__file__), "calibration_data", "analysis_records.json"
    )
    if not os.path.exists(cal_path):
        print(f"ERROR: No calibration data at {cal_path}")
        print("Run: python calibrate.py --save-data calibration_data")
        sys.exit(1)

    with open(cal_path) as f:
        records = json.load(f)
    log.info("Loaded %d ground truth records", len(records))

    methods = []
    if args.method in ("static-baseline", "all"):
        methods.append("static-baseline")
    if args.method in ("conditioned-prior", "all"):
        methods.append("conditioned-prior")
    if args.method in ("conditioned-estimated", "all"):
        methods.append("conditioned-estimated")
    if args.method in ("simulator", "all"):
        methods.append("simulator")
    if args.method in ("blended", "all"):
        methods.append("blended")

    results = {}

    for method in methods:
        log.info("Validating: %s", method)
        t0 = time.time()

        if method == "static-baseline":
            kls, per_round = validate_static_baseline(records)
        elif method == "conditioned-prior":
            kls, per_round = validate_conditioned_prior(records)
        elif method == "conditioned-estimated":
            kls, per_round = validate_conditioned_prior_estimated(records)
        elif method == "simulator":
            kls, per_round = validate_simulator(records, n_sims=args.n_sims, n_years=args.n_years)
        elif method == "blended":
            kls, per_round = validate_blended(
                records, sim_weight=args.sim_weight,
                n_sims=args.n_sims, n_years=args.n_years,
            )
        else:
            continue

        elapsed = time.time() - t0
        print_results(f"{method} (took {elapsed:.1f}s)", kls, per_round)
        results[method] = (np.mean(kls), kl_to_score(np.mean(kls)))

    # Summary
    if len(results) > 1:
        print("\n" + "=" * 70)
        print("  SUMMARY")
        print("=" * 70)
        print(f"  {'Method':<30}  {'Mean KL':>10}  {'~Score':>10}")
        print(f"  {'-' * 55}")
        for method, (kl, score) in results.items():
            print(f"  {method:<30}  {kl:>10.4f}  {score:>10.1f}")
        print()


if __name__ == "__main__":
    main()
