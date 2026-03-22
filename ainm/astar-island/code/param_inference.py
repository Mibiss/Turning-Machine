#!/usr/bin/env python3
"""
Astar Island — Expansion Level Estimator
=========================================
Estimates the hidden "expansion level" parameter from observations.
Settlement survival rate varies 18-62% across rounds, controlled by a
dominant hidden parameter. This module infers it from observable data.
"""

import json
import logging
import os

import numpy as np
from collections import defaultdict

log = logging.getLogger("astar.param_inference")

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


class ExpansionEstimator:
    """Estimate the round's expansion level from ground truth calibration data
    and live observations."""

    def __init__(self, calibration_path=None):
        if calibration_path is None:
            calibration_path = os.path.join(
                os.path.dirname(__file__), "calibration_data", "analysis_records.json"
            )

        with open(calibration_path) as f:
            self.records = json.load(f)

        # Compute per-round expansion levels from ground truth
        # expansion = mean(GT[settlement_cells, C_SETTLEMENT] + GT[settlement_cells, C_PORT])
        round_groups = defaultdict(list)
        for rec in self.records:
            round_groups[rec["round_number"]].append(rec)

        self.round_expansions = {}  # round_number -> expansion_level
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

        self.expansion_values = sorted(self.round_expansions.values())
        self.median_expansion = (
            float(np.median(self.expansion_values)) if self.expansion_values else 0.33
        )

        log.info(
            "ExpansionEstimator: %d rounds, expansion range [%.3f, %.3f], median %.3f",
            len(self.round_expansions),
            min(self.expansion_values) if self.expansion_values else 0,
            max(self.expansion_values) if self.expansion_values else 0,
            self.median_expansion,
        )

    def estimate_from_observations(self, state) -> tuple:
        """Estimate expansion level from a single MapState's observations.

        Returns: (expansion_level: float, confidence: float)
        """
        # Strategy 1 (best): alive rate of observed initial-settlement cells
        initial_settle_positions = set()
        for s in state.initial_settlements:
            initial_settle_positions.add((s["x"], s["y"]))

        if initial_settle_positions and state.settlement_stats:
            alive_count = 0
            total_count = 0
            for pos in initial_settle_positions:
                if pos in state.settlement_stats:
                    for s in state.settlement_stats[pos]:
                        total_count += 1
                        if s.get("alive", False):
                            alive_count += 1

            if total_count >= 5:
                alive_rate = alive_count / total_count
                confidence = min(1.0, total_count / 20.0)
                log.debug(
                    "Strategy 1: alive_rate=%.3f from %d observations, confidence=%.2f",
                    alive_rate, total_count, confidence,
                )
                return alive_rate, confidence

        # Strategy 2 (fallback): settlement class fraction in observed dynamic cells
        obs = state.obs_counts
        obs_total = state.obs_total
        has_obs = obs_total > 0
        ig = state.initial_grid
        dynamic = ~((ig == OCEAN) | (ig == MOUNTAIN))
        observed_dynamic = has_obs & dynamic

        n_observed = int(observed_dynamic.sum())
        if n_observed >= 10:
            total_obs_on_dynamic = float(obs_total[observed_dynamic].sum())
            settle_obs = float(
                (obs[observed_dynamic, C_SETTLEMENT] + obs[observed_dynamic, C_PORT]).sum()
            )
            settle_frac = settle_obs / total_obs_on_dynamic
            # settle_frac ≈ 0.02 + 0.4 * expansion_level
            expansion = max(0.0, min(0.70, (settle_frac - 0.02) / 0.4))
            confidence = min(0.7, n_observed / 100.0)
            log.debug(
                "Strategy 2: settle_frac=%.4f -> expansion=%.3f, confidence=%.2f",
                settle_frac, expansion, confidence,
            )
            return expansion, confidence

        # Strategy 3 (last resort): return median
        log.debug("Strategy 3: using median expansion %.3f", self.median_expansion)
        return self.median_expansion, 0.1

    def estimate_from_cross_seed_stats(self, all_states: dict) -> tuple:
        """Aggregate settlement stats across ALL seeds for better estimation.

        All seeds in a round share the same hidden parameters, so combining
        their observations gives a more robust expansion estimate.

        Args:
            all_states: {seed_idx: MapState}

        Returns: (expansion_level: float, confidence: float)
        """
        combined_alive = 0
        combined_total = 0

        for state in all_states.values():
            initial_positions = set()
            for s in state.initial_settlements:
                initial_positions.add((s["x"], s["y"]))

            for pos in initial_positions:
                if pos in state.settlement_stats:
                    for s in state.settlement_stats[pos]:
                        combined_total += 1
                        if s.get("alive", False):
                            combined_alive += 1

        if combined_total >= 5:
            alive_rate = combined_alive / combined_total
            confidence = min(1.0, combined_total / 50.0)
            log.info(
                "Cross-seed expansion estimate: alive_rate=%.3f from %d obs (confidence=%.2f)",
                alive_rate, combined_total, confidence,
            )
            return alive_rate, confidence

        # Fall back to individual seed estimation
        for state in all_states.values():
            exp, conf = self.estimate_from_observations(state)
            if conf > 0.1:
                return exp, conf

        log.info("Cross-seed fallback to median expansion %.3f", self.median_expansion)
        return self.median_expansion, 0.1

    def get_round_expansion(self, round_number: int) -> float:
        """Get the ground-truth expansion level for a specific round (for validation)."""
        return self.round_expansions.get(round_number, self.median_expansion)
