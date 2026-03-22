#!/usr/bin/env python3
"""
Comprehensive analysis of Astar Island ground truth data.
Analyzes transition probabilities, distance effects, variance across rounds,
coastal effects, and maximum achievable score.
"""

import json
import numpy as np
from collections import defaultdict

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

CLASS_NAMES = ["empty", "settlement", "port", "ruin", "forest", "mountain"]
TERRAIN_NAMES = {
    OCEAN: "ocean", PLAINS: "plains", EMPTY: "empty",
    SETTLEMENT: "settlement", PORT: "port", RUIN: "ruin",
    FOREST: "forest", MOUNTAIN: "mountain",
}

STATIC_TERRAINS = {OCEAN, MOUNTAIN}

# ─── Load data ────────────────────────────────────────────────────────────────
print("Loading data...")
with open("calibration_data/analysis_records.json") as f:
    records = json.load(f)
print(f"Loaded {len(records)} records across rounds {sorted(set(r['round_number'] for r in records))}")
print(f"Scores range: {min(r['score'] for r in records if r['score']):.2f} - {max(r['score'] for r in records if r['score']):.2f}")
print()

# ─── Helper functions ─────────────────────────────────────────────────────────

def compute_settlement_distance(initial_grid):
    H, W = initial_grid.shape
    settle_mask = (initial_grid == SETTLEMENT) | (initial_grid == PORT)
    sy, sx = np.where(settle_mask)
    if len(sx) == 0:
        return np.full((H, W), 999, dtype=np.int32)
    X = np.arange(W, dtype=np.int32)[None, None, :]
    Y = np.arange(H, dtype=np.int32)[None, :, None]
    d = np.maximum(np.abs(X - sx[:, None, None]), np.abs(Y - sy[:, None, None]))
    return d.min(axis=0).astype(np.int32)

def compute_coast_mask(initial_grid, radius=2):
    ocean = (initial_grid == OCEAN).astype(np.float32)
    H, W = initial_grid.shape
    mask = np.zeros((H, W), dtype=bool)
    oy, ox = np.where(ocean > 0)
    for cy, cx in zip(oy, ox):
        y0, y1 = max(0, cy - radius), min(H, cy + radius + 1)
        x0, x1 = max(0, cx - radius), min(W, cx + radius + 1)
        mask[y0:y1, x0:x1] = True
    return mask


# ═══════════════════════════════════════════════════════════════════════════════
# 1. TRANSITION PROBABILITIES
# ═══════════════════════════════════════════════════════════════════════════════
print("=" * 80)
print("1. TRANSITION PROBABILITIES (Initial Terrain -> Final Class Distribution)")
print("=" * 80)

terrain_probs = defaultdict(list)

for rec in records:
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)
    H, W = ig.shape
    for terrain_code in [SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
        mask = ig == terrain_code
        if mask.any():
            terrain_probs[terrain_code].append(gt[mask])

print(f"\n{'Terrain':<12} {'N cells':>8}  {'empty':>8} {'settle':>8} {'port':>8} {'ruin':>8} {'forest':>8} {'mount':>8}")
print("-" * 80)

for terrain_code in [SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
    if terrain_code not in terrain_probs:
        continue
    all_probs = np.concatenate(terrain_probs[terrain_code], axis=0)
    mean = all_probs.mean(axis=0)
    name = TERRAIN_NAMES[terrain_code]
    print(f"{name:<12} {len(all_probs):>8}  " +
          "  ".join(f"{mean[i]:>8.4f}" for i in range(N_CLASSES)))

# Detailed breakdown for each terrain type
for terrain_code, label in [(SETTLEMENT, "SETTLEMENT"), (PORT, "PORT"),
                              (FOREST, "FOREST"), (PLAINS, "PLAINS/EMPTY")]:
    codes = [terrain_code] if terrain_code != PLAINS else [PLAINS, EMPTY]
    probs_list = []
    for c in codes:
        if c in terrain_probs:
            probs_list.extend(terrain_probs[c])
    if not probs_list:
        continue
    all_probs = np.concatenate(probs_list, axis=0)
    mean = all_probs.mean(axis=0)
    std = all_probs.std(axis=0)

    print(f"\n  {label} cells ({len(all_probs)} total):")
    for i in range(N_CLASSES):
        if mean[i] > 0.001:
            bar = "#" * int(mean[i] * 50)
            print(f"    -> {CLASS_NAMES[i]:<12}: {mean[i]:7.4f} (std={std[i]:.4f}) {bar}")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. DISTANCE EFFECTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("2. DISTANCE EFFECTS (How settlement distance affects outcomes)")
print("=" * 80)

dist_bins = [(0, 1, "0-1"), (2, 3, "2-3"), (4, 6, "4-6"), (7, 999, "7+")]
# Also break down by terrain type
terrain_groups = {
    "FOREST": [FOREST],
    "PLAINS": [PLAINS, EMPTY],
    "SETTLEMENT": [SETTLEMENT],
    "PORT": [PORT],
}

for tgroup_name, tgroup_codes in terrain_groups.items():
    print(f"\n  {tgroup_name} cells by distance from initial settlements:")
    print(f"  {'Dist':>6} {'N':>8}  {'empty':>8} {'settle':>8} {'port':>8} {'ruin':>8} {'forest':>8} {'mount':>8}")
    print(f"  " + "-" * 72)

    for d_lo, d_hi, d_label in dist_bins:
        all_probs = []
        for rec in records:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)
            sdist = compute_settlement_distance(ig)

            for tc in tgroup_codes:
                mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi)
                if mask.any():
                    all_probs.append(gt[mask])

        if all_probs:
            arr = np.concatenate(all_probs, axis=0)
            mean = arr.mean(axis=0)
            print(f"  {d_label:>6} {len(arr):>8}  " +
                  "  ".join(f"{mean[i]:>8.4f}" for i in range(N_CLASSES)))
        else:
            print(f"  {d_label:>6}        0  (no cells)")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. VARIANCE ACROSS ROUNDS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("3. VARIANCE ACROSS ROUNDS (How much do hidden parameters matter?)")
print("=" * 80)

# Group by round
round_terrain_probs = defaultdict(lambda: defaultdict(list))

for rec in records:
    rnd = rec["round_number"]
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)

    for terrain_code in [SETTLEMENT, PORT, FOREST, PLAINS]:
        codes = [terrain_code]
        if terrain_code == PLAINS:
            codes = [PLAINS, EMPTY]
        for tc in codes:
            mask = ig == tc
            if mask.any():
                round_terrain_probs[terrain_code][rnd].append(gt[mask])

for terrain_code, label in [(SETTLEMENT, "SETTLEMENT"), (PORT, "PORT"),
                             (FOREST, "FOREST"), (PLAINS, "PLAINS/EMPTY")]:
    print(f"\n  {label} — per-round mean distributions:")
    print(f"  {'Round':>6}  {'empty':>8} {'settle':>8} {'port':>8} {'ruin':>8} {'forest':>8} {'mount':>8}  {'score':>8}")
    print(f"  " + "-" * 80)

    round_means = []
    for rnd in sorted(round_terrain_probs[terrain_code].keys()):
        probs_list = round_terrain_probs[terrain_code][rnd]
        if probs_list:
            arr = np.concatenate(probs_list, axis=0)
            mean = arr.mean(axis=0)
            round_means.append(mean)
            # Get avg score for this round
            round_scores = [r["score"] for r in records if r["round_number"] == rnd and r["score"]]
            avg_score = np.mean(round_scores) if round_scores else 0
            print(f"  {rnd:>6}  " +
                  "  ".join(f"{mean[i]:>8.4f}" for i in range(N_CLASSES)) +
                  f"  {avg_score:>8.2f}")

    if round_means:
        round_means = np.array(round_means)
        overall_mean = round_means.mean(axis=0)
        overall_std = round_means.std(axis=0)
        print(f"  {'MEAN':>6}  " + "  ".join(f"{overall_mean[i]:>8.4f}" for i in range(N_CLASSES)))
        print(f"  {'STD':>6}  " + "  ".join(f"{overall_std[i]:>8.4f}" for i in range(N_CLASSES)))
        print(f"  {'CV%':>6}  " + "  ".join(f"{100*overall_std[i]/max(overall_mean[i],0.001):>8.1f}" for i in range(N_CLASSES)))


# ═══════════════════════════════════════════════════════════════════════════════
# 4. COASTAL EFFECTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("4. COASTAL EFFECTS (How proximity to ocean changes outcomes)")
print("=" * 80)

for tgroup_name, tgroup_codes in terrain_groups.items():
    coastal_probs = []
    inland_probs = []

    for rec in records:
        ig = np.array(rec["initial_grid"], dtype=np.int32)
        gt = np.array(rec["ground_truth"], dtype=np.float64)
        coast = compute_coast_mask(ig)

        for tc in tgroup_codes:
            coastal_mask = (ig == tc) & coast
            inland_mask = (ig == tc) & ~coast
            if coastal_mask.any():
                coastal_probs.append(gt[coastal_mask])
            if inland_mask.any():
                inland_probs.append(gt[inland_mask])

    if coastal_probs or inland_probs:
        print(f"\n  {tgroup_name}:")
        print(f"  {'Location':>10} {'N':>8}  {'empty':>8} {'settle':>8} {'port':>8} {'ruin':>8} {'forest':>8} {'mount':>8}")
        print(f"  " + "-" * 72)

        if inland_probs:
            arr = np.concatenate(inland_probs, axis=0)
            mean = arr.mean(axis=0)
            print(f"  {'inland':>10} {len(arr):>8}  " +
                  "  ".join(f"{mean[i]:>8.4f}" for i in range(N_CLASSES)))

        if coastal_probs:
            arr = np.concatenate(coastal_probs, axis=0)
            mean = arr.mean(axis=0)
            print(f"  {'coastal':>10} {len(arr):>8}  " +
                  "  ".join(f"{mean[i]:>8.4f}" for i in range(N_CLASSES)))

        if coastal_probs and inland_probs:
            coast_mean = np.concatenate(coastal_probs, axis=0).mean(axis=0)
            inland_mean = np.concatenate(inland_probs, axis=0).mean(axis=0)
            delta = coast_mean - inland_mean
            print(f"  {'delta':>10} {'':>8}  " +
                  "  ".join(f"{delta[i]:>+8.4f}" for i in range(N_CLASSES)))


# ═══════════════════════════════════════════════════════════════════════════════
# 4b. COASTAL + DISTANCE COMBINED for key terrain types
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("4b. COASTAL x DISTANCE INTERACTION (for FOREST and PLAINS)")
print("=" * 80)

for tgroup_name, tgroup_codes in [("FOREST", [FOREST]), ("PLAINS", [PLAINS, EMPTY])]:
    print(f"\n  {tgroup_name}:")
    print(f"  {'Dist':>6} {'Coast':>8} {'N':>8}  {'empty':>8} {'settle':>8} {'port':>8} {'ruin':>8} {'forest':>8}")
    print(f"  " + "-" * 66)

    for d_lo, d_hi, d_label in dist_bins:
        for coast_label in ["inland", "coastal"]:
            all_probs = []
            for rec in records:
                ig = np.array(rec["initial_grid"], dtype=np.int32)
                gt = np.array(rec["ground_truth"], dtype=np.float64)
                sdist = compute_settlement_distance(ig)
                coast = compute_coast_mask(ig)

                for tc in tgroup_codes:
                    if coast_label == "coastal":
                        mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & coast
                    else:
                        mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & ~coast
                    if mask.any():
                        all_probs.append(gt[mask])

            if all_probs:
                arr = np.concatenate(all_probs, axis=0)
                mean = arr.mean(axis=0)
                print(f"  {d_label:>6} {coast_label:>8} {len(arr):>8}  " +
                      "  ".join(f"{mean[i]:>8.4f}" for i in range(5)))


# ═══════════════════════════════════════════════════════════════════════════════
# 5. MAXIMUM ACHIEVABLE SCORE (Ceiling Analysis)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("5. MAXIMUM ACHIEVABLE SCORE (Prior-only ceiling)")
print("=" * 80)

# Strategy: For each record, compute the KL divergence between the ground truth
# and various prediction strategies.

PROB_FLOOR = 0.01

def kl_divergence_score(pred, gt, initial_grid):
    """Compute mean KL divergence per cell (same as competition scoring)."""
    H, W, C = gt.shape
    # Apply floor
    pred_safe = np.maximum(pred, 1e-10)
    gt_safe = np.maximum(gt, 1e-10)

    # KL(gt || pred) = sum_c gt[c] * log(gt[c] / pred[c])
    kl_per_cell = np.sum(gt_safe * np.log(gt_safe / pred_safe), axis=-1)

    # Only count dynamic cells (exclude ocean and mountain)
    dynamic_mask = ~((initial_grid == OCEAN) | (initial_grid == MOUNTAIN))
    if dynamic_mask.sum() == 0:
        return 0.0
    return kl_per_cell[dynamic_mask].mean()

def build_global_mean_prior(records):
    """Build a single global mean prior from all calibration data, keyed by terrain."""
    terrain_accum = defaultdict(list)
    for rec in records:
        ig = np.array(rec["initial_grid"], dtype=np.int32)
        gt = np.array(rec["ground_truth"], dtype=np.float64)
        for tc in [SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
            mask = ig == tc
            if mask.any():
                terrain_accum[tc].append(gt[mask].mean(axis=0))

    result = {}
    for tc, means in terrain_accum.items():
        result[tc] = np.array(means).mean(axis=0)
        result[tc] = np.maximum(result[tc], PROB_FLOOR)
        result[tc] /= result[tc].sum()
    return result

def build_spatial_prior(records):
    """Build spatial prior (terrain x dist_bin x coastal)."""
    dist_bin_defs = [(0, 2, "0-2"), (3, 5, "3-5"), (6, 999, "6+")]
    accum = defaultdict(list)

    for rec in records:
        ig = np.array(rec["initial_grid"], dtype=np.int32)
        gt = np.array(rec["ground_truth"], dtype=np.float64)
        sdist = compute_settlement_distance(ig)
        coast = compute_coast_mask(ig)

        for tc in [SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
            for d_lo, d_hi, d_label in dist_bin_defs:
                for is_coastal in [True, False]:
                    coast_label = "coastal" if is_coastal else "inland"
                    if is_coastal:
                        mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & coast
                    else:
                        mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & ~coast
                    if mask.any():
                        accum[(tc, d_label, coast_label)].append(gt[mask].mean(axis=0))

    result = {}
    for key, means in accum.items():
        result[key] = np.array(means).mean(axis=0)
        result[key] = np.maximum(result[key], PROB_FLOOR)
        result[key] /= result[key].sum()
    return result

def apply_global_prior(ig, global_prior):
    """Build prediction grid using global terrain-based prior."""
    H, W = ig.shape
    pred = np.full((H, W, N_CLASSES), 1.0 / N_CLASSES)
    for tc, prior in global_prior.items():
        mask = ig == tc
        pred[mask] = prior
    # Ocean -> empty, Mountain -> mountain
    ocean_prior = np.full(N_CLASSES, PROB_FLOOR)
    ocean_prior[C_EMPTY] = 1.0 - (N_CLASSES - 1) * PROB_FLOOR
    mtn_prior = np.full(N_CLASSES, PROB_FLOOR)
    mtn_prior[C_MOUNTAIN] = 1.0 - (N_CLASSES - 1) * PROB_FLOOR
    pred[ig == OCEAN] = ocean_prior
    pred[ig == MOUNTAIN] = mtn_prior
    pred = np.maximum(pred, PROB_FLOOR)
    pred /= pred.sum(axis=-1, keepdims=True)
    return pred

def apply_spatial_prior(ig, spatial_prior, global_prior):
    """Build prediction grid using spatial (terrain x dist x coastal) prior."""
    H, W = ig.shape
    pred = apply_global_prior(ig, global_prior)  # start with global as fallback
    sdist = compute_settlement_distance(ig)
    coast = compute_coast_mask(ig)

    dist_bin_defs = [(0, 2, "0-2"), (3, 5, "3-5"), (6, 999, "6+")]

    for tc in [SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
        for d_lo, d_hi, d_label in dist_bin_defs:
            for is_coastal in [True, False]:
                coast_label = "coastal" if is_coastal else "inland"
                key = (tc, d_label, coast_label)
                if key not in spatial_prior:
                    continue
                if is_coastal:
                    mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & coast
                else:
                    mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & ~coast
                if mask.any():
                    pred[mask] = spatial_prior[key]

    pred = np.maximum(pred, PROB_FLOOR)
    pred /= pred.sum(axis=-1, keepdims=True)
    return pred

# ── Strategy evaluations ──

# A: Uniform baseline
print("\n  A) UNIFORM BASELINE (1/6 each class):")
uniform_kls = []
for rec in records:
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)
    H, W = ig.shape
    pred = np.full((H, W, N_CLASSES), 1.0 / N_CLASSES)
    pred = np.maximum(pred, PROB_FLOOR)
    pred /= pred.sum(axis=-1, keepdims=True)
    kl = kl_divergence_score(pred, gt, ig)
    uniform_kls.append(kl)
print(f"     Mean KL: {np.mean(uniform_kls):.4f} (std={np.std(uniform_kls):.4f})")
print(f"     Range:   [{np.min(uniform_kls):.4f}, {np.max(uniform_kls):.4f}]")

# B: Global mean prior (terrain-only)
print("\n  B) GLOBAL MEAN PRIOR (flat per-terrain):")
global_prior = build_global_mean_prior(records)
global_kls = []
for rec in records:
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)
    pred = apply_global_prior(ig, global_prior)
    kl = kl_divergence_score(pred, gt, ig)
    global_kls.append(kl)
print(f"     Mean KL: {np.mean(global_kls):.4f} (std={np.std(global_kls):.4f})")
print(f"     Range:   [{np.min(global_kls):.4f}, {np.max(global_kls):.4f}]")

# C: Spatial prior (terrain x dist x coastal)
print("\n  C) SPATIAL PRIOR (terrain x dist_bin x coastal):")
spatial_prior = build_spatial_prior(records)
spatial_kls = []
for rec in records:
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)
    pred = apply_spatial_prior(ig, spatial_prior, global_prior)
    kl = kl_divergence_score(pred, gt, ig)
    spatial_kls.append(kl)
print(f"     Mean KL: {np.mean(spatial_kls):.4f} (std={np.std(spatial_kls):.4f})")
print(f"     Range:   [{np.min(spatial_kls):.4f}, {np.max(spatial_kls):.4f}]")

# D: Leave-one-round-out cross-validation
print("\n  D) LEAVE-ONE-ROUND-OUT CV (spatial prior, excludes target round):")
round_numbers = sorted(set(r["round_number"] for r in records))
loo_kls = []
for hold_rnd in round_numbers:
    train = [r for r in records if r["round_number"] != hold_rnd]
    test = [r for r in records if r["round_number"] == hold_rnd]
    if not train or not test:
        continue
    gp = build_global_mean_prior(train)
    sp = build_spatial_prior(train)
    for rec in test:
        ig = np.array(rec["initial_grid"], dtype=np.int32)
        gt = np.array(rec["ground_truth"], dtype=np.float64)
        pred = apply_spatial_prior(ig, sp, gp)
        kl = kl_divergence_score(pred, gt, ig)
        loo_kls.append(kl)
print(f"     Mean KL: {np.mean(loo_kls):.4f} (std={np.std(loo_kls):.4f})")
print(f"     Range:   [{np.min(loo_kls):.4f}, {np.max(loo_kls):.4f}]")

# E: "Oracle" per-round spatial prior (train on same round's other seeds)
print("\n  E) SAME-ROUND PRIOR (spatial prior from other seeds in same round):")
same_round_kls = []
for hold_rnd in round_numbers:
    round_recs = [r for r in records if r["round_number"] == hold_rnd]
    if len(round_recs) < 2:
        continue
    for i, test_rec in enumerate(round_recs):
        train = [r for j, r in enumerate(round_recs) if j != i]
        gp = build_global_mean_prior(train)
        sp = build_spatial_prior(train)
        ig = np.array(test_rec["initial_grid"], dtype=np.int32)
        gt = np.array(test_rec["ground_truth"], dtype=np.float64)
        pred = apply_spatial_prior(ig, sp, gp)
        kl = kl_divergence_score(pred, gt, ig)
        same_round_kls.append(kl)
if same_round_kls:
    print(f"     Mean KL: {np.mean(same_round_kls):.4f} (std={np.std(same_round_kls):.4f})")
    print(f"     Range:   [{np.min(same_round_kls):.4f}, {np.max(same_round_kls):.4f}]")

# F: Perfect oracle (each cell uses its own ground truth mean across sims)
print("\n  F) ORACLE LOWER BOUND (mean over all sims for each cell -- in-sample):")
oracle_kls = []
for rec in records:
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)
    # The ground truth IS the distribution -- perfect prediction
    pred = gt.copy()
    pred = np.maximum(pred, PROB_FLOOR)
    pred /= pred.sum(axis=-1, keepdims=True)
    kl = kl_divergence_score(pred, gt, ig)
    oracle_kls.append(kl)
print(f"     Mean KL: {np.mean(oracle_kls):.4f} (this is the irreducible error from PROB_FLOOR)")

# Convert KL to approximate competition score (score = KL * some_constant)
print("\n  SUMMARY — KL divergence comparison:")
print(f"  {'Strategy':<45} {'Mean KL':>10} {'Std KL':>10}")
print(f"  " + "-" * 65)
for name, kls in [
    ("A) Uniform (1/6)", uniform_kls),
    ("B) Global terrain prior", global_kls),
    ("C) Spatial prior (terrain x dist x coast)", spatial_kls),
    ("D) Leave-one-round-out CV", loo_kls),
    ("E) Same-round prior (oracle-ish)", same_round_kls),
    ("F) Oracle (GT with floor)", oracle_kls),
]:
    print(f"  {name:<45} {np.mean(kls):>10.4f} {np.std(kls):>10.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5b. SCORE RELATIONSHIP
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("5b. ACTUAL COMPETITION SCORES vs OUR KL ESTIMATES")
print("=" * 80)

print(f"\n  {'Round':>6} {'Seed':>5} {'Actual Score':>13} {'KL(spatial)':>12} {'KL(global)':>12}")
print(f"  " + "-" * 55)
for rec in records[:20]:  # show first 20
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    gt = np.array(rec["ground_truth"], dtype=np.float64)
    pred_s = apply_spatial_prior(ig, spatial_prior, global_prior)
    pred_g = apply_global_prior(ig, global_prior)
    kl_s = kl_divergence_score(pred_s, gt, ig)
    kl_g = kl_divergence_score(pred_g, gt, ig)
    score_str = f"{rec['score']:>13.2f}" if rec.get('score') is not None else "          N/A"
    print(f"  {rec['round_number']:>6} {rec['seed_index']:>5} {score_str} {kl_s:>12.4f} {kl_g:>12.4f}")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. ADDITIONAL INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("6. ADDITIONAL INSIGHTS")
print("=" * 80)

# How often does each initial terrain class appear?
print("\n  Initial terrain frequency across all records:")
total_cells = 0
for terrain_code in [OCEAN, MOUNTAIN, SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
    count = 0
    for rec in records:
        ig = np.array(rec["initial_grid"], dtype=np.int32)
        count += (ig == terrain_code).sum()
        total_cells += (ig == terrain_code).sum()
    name = TERRAIN_NAMES.get(terrain_code, f"code={terrain_code}")
    print(f"    {name:<12}: {count:>8} cells")

# Entropy of ground truth distributions (how much uncertainty in the simulation itself?)
print("\n  Mean entropy of ground truth distributions (by terrain):")
print(f"  (Higher = more uncertain outcomes, max = log(6) = {np.log(6):.3f})")
for terrain_code in [SETTLEMENT, PORT, FOREST, PLAINS]:
    codes = [terrain_code] if terrain_code != PLAINS else [PLAINS, EMPTY]
    all_gt = []
    for rec in records:
        ig = np.array(rec["initial_grid"], dtype=np.int32)
        gt = np.array(rec["ground_truth"], dtype=np.float64)
        for tc in codes:
            mask = ig == tc
            if mask.any():
                all_gt.append(gt[mask])
    if all_gt:
        arr = np.concatenate(all_gt, axis=0)
        # clip to avoid log(0)
        arr_safe = np.maximum(arr, 1e-10)
        entropy = -np.sum(arr_safe * np.log(arr_safe), axis=-1)
        name = TERRAIN_NAMES.get(terrain_code, "plains/empty")
        print(f"    {name:<12}: mean_H={entropy.mean():.4f} std_H={entropy.std():.4f} "
              f"(min={entropy.min():.4f} max={entropy.max():.4f})")

# How many settlement/port cells per map on average?
print("\n  Settlement/port density per map:")
settle_counts = []
port_counts = []
for rec in records:
    ig = np.array(rec["initial_grid"], dtype=np.int32)
    settle_counts.append((ig == SETTLEMENT).sum())
    port_counts.append((ig == PORT).sum())
print(f"    Settlements: mean={np.mean(settle_counts):.1f} std={np.std(settle_counts):.1f} "
      f"range=[{np.min(settle_counts)}, {np.max(settle_counts)}]")
print(f"    Ports:       mean={np.mean(port_counts):.1f} std={np.std(port_counts):.1f} "
      f"range=[{np.min(port_counts)}, {np.max(port_counts)}]")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
