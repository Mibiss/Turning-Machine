#!/usr/bin/env python3
"""
Astar Island — Expansion-Conditioned Spatial Priors
====================================================
Instead of using the same spatial priors for every round, estimate the round's
"expansion level" from observations, then weight calibration data from similar
rounds. This directly targets the KL 0.14 → 0.07 gap between static priors
and round-conditioned priors.
"""

import json
import logging
import os

import numpy as np
from collections import defaultdict

log = logging.getLogger("astar.conditioned_prior")

# ─── Constants (mirror main2.py) ─────────────────────────────────────────────
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

_DIST_LABELS = {0: "0-2", 1: "3-5", 2: "6+"}


class ConditionedPriorBuilder:
    """Build spatial priors conditioned on the round's expansion level.

    Precomputes priors at 15 discrete expansion levels (0.0 to 0.70) using
    kernel-weighted averages of per-round spatial priors from calibration data.
    At prediction time, interpolates between the two nearest levels.
    """

    EXPANSION_LEVELS = np.linspace(0.0, 0.70, 15)
    BASE_BANDWIDTH = 0.15

    def __init__(self, calibration_path=None, exclude_rounds=None):
        """
        Args:
            calibration_path: Path to analysis_records.json. Defaults to
                calibration_data/analysis_records.json in the same directory.
            exclude_rounds: Set of round_numbers to exclude (for LOO-CV).
        """
        if calibration_path is None:
            calibration_path = os.path.join(
                os.path.dirname(__file__), "calibration_data", "analysis_records.json"
            )

        with open(calibration_path) as f:
            all_records = json.load(f)

        # Optionally exclude rounds for validation
        if exclude_rounds:
            self.records = [r for r in all_records if r["round_number"] not in exclude_rounds]
        else:
            self.records = all_records

        # Group records by round
        round_groups = defaultdict(list)
        for rec in self.records:
            round_groups[rec["round_number"]].append(rec)

        # Compute per-round expansion levels
        self.round_expansions = {}
        for rnd, recs in round_groups.items():
            exp_vals = []
            for rec in recs:
                ig = np.array(rec["initial_grid"], dtype=np.int32)
                gt = np.array(rec["ground_truth"], dtype=np.float64)
                settle_mask = (ig == SETTLEMENT) | (ig == PORT)
                if settle_mask.any():
                    survival = gt[settle_mask, C_SETTLEMENT] + gt[settle_mask, C_PORT]
                    exp_vals.append(float(survival.mean()))
            if exp_vals:
                self.round_expansions[rnd] = float(np.mean(exp_vals))

        # Precompute per-round spatial priors
        self._round_priors = {}
        for rnd, recs in round_groups.items():
            self._round_priors[rnd] = self._compute_spatial_priors(recs)

        # Precompute conditioned priors at discrete expansion levels
        self._level_priors = {}
        for level in self.EXPANSION_LEVELS:
            self._level_priors[float(level)] = self._build_level_prior(float(level))

        log.info(
            "ConditionedPriorBuilder: %d rounds, %d expansion levels precomputed",
            len(self.round_expansions), len(self.EXPANSION_LEVELS),
        )

    def _compute_spatial_priors(self, recs):
        """Compute spatial priors from a set of records (single round)."""
        dist_bin_defs = [(0, 2, "0-2"), (3, 5, "3-5"), (6, 999, "6+")]
        accum = defaultdict(list)

        for rec in recs:
            ig = np.array(rec["initial_grid"], dtype=np.int32)
            gt = np.array(rec["ground_truth"], dtype=np.float64)
            sdist = _compute_settlement_distance(ig)
            coast = _compute_coast_mask(ig)

            for tc in [SETTLEMENT, PORT, FOREST, PLAINS, EMPTY, RUIN]:
                tname = _TERRAIN_KEY_NAME.get(tc)
                if tname is None:
                    continue
                for d_lo, d_hi, d_label in dist_bin_defs:
                    for is_coastal in [True, False]:
                        coast_label = "coastal" if is_coastal else "inland"
                        if is_coastal:
                            mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & coast
                        else:
                            mask = (ig == tc) & (sdist >= d_lo) & (sdist <= d_hi) & ~coast
                        if mask.any():
                            key = f"{tname}|{d_label}|{coast_label}"
                            accum[key].append(gt[mask].mean(axis=0))

        result = {}
        for key, means in accum.items():
            arr = np.array(means).mean(axis=0)
            arr = np.maximum(arr, PROB_FLOOR)
            arr /= arr.sum()
            result[key] = arr
        return result

    def _build_level_prior(self, target_level):
        """Build spatial prior for a target expansion level using kernel-weighted averaging."""
        # Adaptive bandwidth: wider at extremes where data is sparser
        bw = self.BASE_BANDWIDTH
        if target_level < 0.10 or target_level > 0.55:
            bw = self.BASE_BANDWIDTH * 1.5

        # Compute weights for each round
        weights = {}
        for rnd, exp_level in self.round_expansions.items():
            w = np.exp(-((exp_level - target_level) ** 2) / (bw ** 2))
            if w > 1e-6:
                weights[rnd] = w

        if not weights:
            # Fall back to uniform weights
            weights = {rnd: 1.0 for rnd in self.round_expansions}

        # Collect all spatial prior keys across weighted rounds
        all_keys = set()
        for rnd in weights:
            if rnd in self._round_priors:
                all_keys.update(self._round_priors[rnd].keys())

        # Weighted average of per-round spatial priors
        combined = {}
        for key in all_keys:
            weighted_sum = np.zeros(N_CLASSES, dtype=np.float64)
            w_sum = 0.0
            for rnd, w in weights.items():
                if rnd in self._round_priors and key in self._round_priors[rnd]:
                    weighted_sum += w * self._round_priors[rnd][key]
                    w_sum += w
            if w_sum > 0:
                result = weighted_sum / w_sum
                result = np.maximum(result, PROB_FLOOR)
                result /= result.sum()
                combined[key] = result

        return combined

    def build_prior(self, initial_grid, initial_settlements, expansion_level):
        """Build (H, W, 6) prior grid conditioned on expansion level.

        Interpolates between the two nearest precomputed expansion levels.

        Args:
            initial_grid: (H, W) int32 array or list of terrain codes
            initial_settlements: list of settlement dicts (unused currently,
                reserved for future per-settlement priors)
            expansion_level: float in [0.0, 0.70]

        Returns:
            (H, W, 6) float64 normalized probability grid
        """
        ig = np.array(initial_grid, dtype=np.int32) if not isinstance(initial_grid, np.ndarray) else initial_grid
        H, W = ig.shape

        # Find two nearest precomputed levels and interpolate
        levels = self.EXPANSION_LEVELS
        exp_clamped = np.clip(expansion_level, float(levels[0]), float(levels[-1]))
        idx = int(np.searchsorted(levels, exp_clamped))
        idx = np.clip(idx, 1, len(levels) - 1)
        lo_level = float(levels[idx - 1])
        hi_level = float(levels[idx])

        if hi_level == lo_level:
            t = 0.0
        else:
            t = (exp_clamped - lo_level) / (hi_level - lo_level)
        t = float(np.clip(t, 0.0, 1.0))

        lo_priors = self._level_priors[lo_level]
        hi_priors = self._level_priors[hi_level]

        # Build spatial context
        sdist = _compute_settlement_distance(ig)
        coast = _compute_coast_mask(ig)
        dist_bin = np.where(sdist <= 2, 0, np.where(sdist <= 5, 1, 2))

        # Default: uniform prior
        p = np.full((H, W, N_CLASSES), 1.0 / N_CLASSES, dtype=np.float64)

        for terrain_code, tname in _TERRAIN_KEY_NAME.items():
            tmask = ig == terrain_code
            if not np.any(tmask):
                continue
            for db_idx, db_label in _DIST_LABELS.items():
                for is_coastal in (False, True):
                    coast_label = "coastal" if is_coastal else "inland"
                    key = f"{tname}|{db_label}|{coast_label}"

                    lo_vec = lo_priors.get(key)
                    hi_vec = hi_priors.get(key)

                    if lo_vec is None and hi_vec is None:
                        continue
                    elif lo_vec is None:
                        interp_vec = hi_vec
                    elif hi_vec is None:
                        interp_vec = lo_vec
                    else:
                        interp_vec = (1 - t) * lo_vec + t * hi_vec

                    cell_mask = tmask & (dist_bin == db_idx)
                    if is_coastal:
                        cell_mask = cell_mask & coast
                    else:
                        cell_mask = cell_mask & ~coast
                    if not np.any(cell_mask):
                        continue
                    p[cell_mask] = interp_vec

        p = np.maximum(p, PROB_FLOOR)
        return p / p.sum(axis=-1, keepdims=True)


# ─── Spatial helper functions ────────────────────────────────────────────────

def _compute_settlement_distance(ig):
    """Chebyshev distance to nearest initial settlement/port."""
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
    """Cells within radius of ocean."""
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
