#!/usr/bin/env python3
"""
Astar Island — Forward Simulation Engine
==========================================
Simplified Viking settlement simulator. Uses observation-inferred parameters
to run Monte Carlo simulations and produce probability distributions.

Performance target: 300 sims of 40x40 grid x 50 years in < 10 seconds.
Achieves this through vectorized numpy operations with minimal per-cell loops.
"""

import logging

import numpy as np
from dataclasses import dataclass

log = logging.getLogger("astar.simulator")

# ─── Constants (mirror main.py) ─────────────────────────────────────────────
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

# Simulation cell states
S_EMPTY      = 0
S_SETTLEMENT = 1
S_PORT       = 2
S_RUIN       = 3
S_FOREST     = 4
S_MOUNTAIN   = 5
S_OCEAN      = 6


@dataclass
class SimParams:
    """Parameters controlling Viking settlement dynamics."""
    growth_rate: float       = 0.05   # 0.01-0.10 — population growth per year
    expansion_prob: float    = 0.08   # 0.01-0.20 — prob of settling adjacent cell
    conflict_intensity: float = 0.15  # 0.0-0.5  — raid frequency/severity
    winter_severity: float   = 0.40   # 0.1-0.8  — food depletion per winter
    reclamation_rate: float  = 0.05   # 0.01-0.10 — ruin → forest/empty rate
    trade_bonus: float       = 0.20   # 0.0-0.5  — port food bonus multiplier


# Predefined profiles at different expansion levels
EXPANSION_PROFILES = {
    0.00: SimParams(
        growth_rate=0.01, expansion_prob=0.01, conflict_intensity=0.40,
        winter_severity=0.80, reclamation_rate=0.08, trade_bonus=0.05,
    ),
    0.10: SimParams(
        growth_rate=0.02, expansion_prob=0.03, conflict_intensity=0.35,
        winter_severity=0.65, reclamation_rate=0.07, trade_bonus=0.10,
    ),
    0.25: SimParams(
        growth_rate=0.04, expansion_prob=0.06, conflict_intensity=0.25,
        winter_severity=0.50, reclamation_rate=0.05, trade_bonus=0.20,
    ),
    0.40: SimParams(
        growth_rate=0.06, expansion_prob=0.10, conflict_intensity=0.15,
        winter_severity=0.35, reclamation_rate=0.04, trade_bonus=0.30,
    ),
    0.55: SimParams(
        growth_rate=0.08, expansion_prob=0.15, conflict_intensity=0.10,
        winter_severity=0.20, reclamation_rate=0.03, trade_bonus=0.40,
    ),
    0.65: SimParams(
        growth_rate=0.10, expansion_prob=0.20, conflict_intensity=0.05,
        winter_severity=0.10, reclamation_rate=0.02, trade_bonus=0.50,
    ),
}


class SimParamMapper:
    """Map expansion level to SimParams by interpolating between profiles."""

    @staticmethod
    def from_expansion(expansion_level: float) -> SimParams:
        levels = sorted(EXPANSION_PROFILES.keys())
        exp = float(np.clip(expansion_level, levels[0], levels[-1]))

        # Find bracketing levels
        idx = 0
        for i, lv in enumerate(levels):
            if lv <= exp:
                idx = i
        if idx >= len(levels) - 1:
            return EXPANSION_PROFILES[levels[-1]]

        lo = levels[idx]
        hi = levels[idx + 1]
        t = (exp - lo) / (hi - lo) if hi > lo else 0.0

        lo_p = EXPANSION_PROFILES[lo]
        hi_p = EXPANSION_PROFILES[hi]

        return SimParams(
            growth_rate=lo_p.growth_rate + t * (hi_p.growth_rate - lo_p.growth_rate),
            expansion_prob=lo_p.expansion_prob + t * (hi_p.expansion_prob - lo_p.expansion_prob),
            conflict_intensity=lo_p.conflict_intensity + t * (hi_p.conflict_intensity - lo_p.conflict_intensity),
            winter_severity=lo_p.winter_severity + t * (hi_p.winter_severity - lo_p.winter_severity),
            reclamation_rate=lo_p.reclamation_rate + t * (hi_p.reclamation_rate - lo_p.reclamation_rate),
            trade_bonus=lo_p.trade_bonus + t * (hi_p.trade_bonus - lo_p.trade_bonus),
        )


# ─── Fast 3x3 convolution ───────────────────────────────────────────────────

_NEIGHBOR_KERNEL = np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.float32)

# 8-connected neighbor directions
_DIRS = np.array([(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)], dtype=np.int32)


def _adj_count(arr_bool, H, W):
    """Fast 3x3 neighbor count using pad + shift (no scipy needed)."""
    a = arr_bool.astype(np.float32)
    padded = np.pad(a, 1, mode='constant', constant_values=0)
    out = np.zeros((H, W), dtype=np.float32)
    for dy in range(3):
        for dx in range(3):
            if dy == 1 and dx == 1:
                continue
            out += padded[dy:dy + H, dx:dx + W]
    return out


class VikingSimulator:
    """Simplified forward simulator for Viking settlement dynamics.

    Optimized: precomputes templates and coast mask once, reuses across sims.
    Growth/winter/conflict/reclamation are fully vectorized.
    Expansion uses a semi-vectorized approach with minimal per-cell work.
    """

    def __init__(self, initial_grid, initial_settlements, params: SimParams):
        self.ig = np.array(initial_grid, dtype=np.int32)
        self.H, self.W = self.ig.shape
        self.params = params

        # Precompute static data (shared across all sims)
        self._coast = self._compute_coast_mask()

        # Build state/pop/food templates for fast init
        self._state_template = np.zeros((self.H, self.W), dtype=np.int32)
        self._state_template[self.ig == OCEAN] = S_OCEAN
        self._state_template[self.ig == MOUNTAIN] = S_MOUNTAIN
        self._state_template[self.ig == FOREST] = S_FOREST
        self._state_template[self.ig == RUIN] = S_RUIN
        self._state_template[self.ig == SETTLEMENT] = S_SETTLEMENT
        self._state_template[self.ig == PORT] = S_PORT

        settle_or_port = (self.ig == SETTLEMENT) | (self.ig == PORT)
        self._pop_template = np.zeros((self.H, self.W), dtype=np.float32)
        self._pop_template[settle_or_port] = 100.0
        self._food_template = np.zeros((self.H, self.W), dtype=np.float32)
        self._food_template[settle_or_port] = 200.0

    def _compute_coast_mask(self):
        ocean = (self.ig == OCEAN).astype(np.float32)
        padded = np.pad(ocean, 2, mode='constant', constant_values=0)
        mask = np.zeros((self.H, self.W), dtype=bool)
        for dy in range(5):
            for dx in range(5):
                mask |= padded[dy:dy + self.H, dx:dx + self.W].astype(bool)
        return mask

    def run(self, rng):
        """Run one simulation. Returns (H, W) int32 array of class indices."""
        state = self._state_template.copy()
        pop = self._pop_template.copy()
        food = self._food_template.copy()
        p = self.params
        H, W = self.H, self.W
        coast = self._coast

        growth_mult = np.float32(1.0 + p.growth_rate)
        trade_food = np.float32(p.trade_bonus * 50.0)
        winter_cost = np.float32(p.winter_severity * 100.0)
        conflict_pop_mult = np.float32(1.0 - p.conflict_intensity * 0.5)
        conflict_food_mult = np.float32(1.0 - p.conflict_intensity * 0.3)
        conflict_thresh = p.conflict_intensity * 0.3

        for year in range(50):
            settle_mask = (state == S_SETTLEMENT) | (state == S_PORT)

            # ── Phase 1: Growth ──
            adj_forest = _adj_count(state == S_FOREST, H, W)
            food[settle_mask] += adj_forest[settle_mask] * 20.0
            food[state == S_PORT] += trade_food

            grow_mask = settle_mask & (food > 50)
            pop[grow_mask] *= growth_mult
            np.minimum(pop, 500.0, out=pop)

            # ── Phase 1b: Expansion (semi-vectorized) ──
            expand_mask = settle_mask & (pop > 80)
            ey, ex = np.where(expand_mask)
            n_cand = len(ey)
            if n_cand > 0:
                # Filter by expansion probability
                keep = rng.random(n_cand) < p.expansion_prob
                ey, ex = ey[keep], ex[keep]
                n_exp = len(ey)
                if n_exp > 0:
                    # Pick random direction for each
                    dir_idx = rng.integers(8, size=n_exp)
                    ny = ey + _DIRS[dir_idx, 0]
                    nx = ex + _DIRS[dir_idx, 1]
                    # Bounds check
                    valid = (ny >= 0) & (ny < H) & (nx >= 0) & (nx < W)
                    for i in range(n_exp):
                        if not valid[i]:
                            continue
                        t = state[ny[i], nx[i]]
                        if t != S_EMPTY and t != S_FOREST:
                            continue
                        if coast[ny[i], nx[i]] and rng.random() < 0.3:
                            state[ny[i], nx[i]] = S_PORT
                        else:
                            state[ny[i], nx[i]] = S_SETTLEMENT
                        pop[ny[i], nx[i]] = pop[ey[i], ex[i]] * 0.3
                        food[ny[i], nx[i]] = 100.0
                        pop[ey[i], ex[i]] *= 0.7

            # ── Phase 2: Conflict ──
            if conflict_thresh > 0:
                settle_mask = (state == S_SETTLEMENT) | (state == S_PORT)
                hit = settle_mask & (rng.random((H, W)) < conflict_thresh)
                pop[hit] *= conflict_pop_mult
                food[hit] *= conflict_food_mult

            # ── Phase 3: Winter ──
            settle_mask = (state == S_SETTLEMENT) | (state == S_PORT)
            food[settle_mask] -= winter_cost
            starve = settle_mask & (food < 0)
            pop[starve] += food[starve]
            food[starve] = 0.0

            collapse = settle_mask & (pop < 10)
            state[collapse] = S_RUIN
            pop[collapse] = 0.0
            food[collapse] = 0.0

            # ── Phase 4: Reclamation ──
            ruin_mask = state == S_RUIN
            n_ruins = ruin_mask.sum()
            if n_ruins > 0:
                reclaim = ruin_mask & (rng.random((H, W)) < p.reclamation_rate)
                if reclaim.any():
                    adj_settle = _adj_count(
                        (state == S_SETTLEMENT) | (state == S_PORT), H, W
                    ) > 0
                    rebuild = reclaim & adj_settle & (rng.random((H, W)) < 0.3)
                    state[rebuild] = S_SETTLEMENT
                    pop[rebuild] = 30.0
                    food[rebuild] = 50.0

                    remaining = reclaim & ~rebuild
                    to_forest = remaining & (rng.random((H, W)) < 0.5)
                    state[to_forest] = S_FOREST
                    state[remaining & ~to_forest] = S_EMPTY

        # Map to class indices
        class_grid = np.zeros((H, W), dtype=np.int32)
        class_grid[state == S_SETTLEMENT] = C_SETTLEMENT
        class_grid[state == S_PORT] = C_PORT
        class_grid[state == S_RUIN] = C_RUIN
        class_grid[state == S_FOREST] = C_FOREST
        class_grid[state == S_MOUNTAIN] = C_MOUNTAIN
        # S_EMPTY and S_OCEAN → C_EMPTY (already 0)
        return class_grid


def run_monte_carlo(
    initial_grid,
    initial_settlements,
    params: SimParams,
    n_sims: int = 300,
    n_years: int = 50,
) -> np.ndarray:
    """Run Monte Carlo simulations and return probability distributions.

    Creates the simulator once and reuses it across all sims for performance.

    Returns: (H, W, 6) float64 array of class probabilities
    """
    ig = np.array(initial_grid, dtype=np.int32) if not isinstance(initial_grid, np.ndarray) else initial_grid
    H, W = ig.shape
    counts = np.zeros((H, W, N_CLASSES), dtype=np.int32)

    # Create simulator once (precomputes coast mask, templates)
    sim = VikingSimulator(ig, initial_settlements, params)

    for i in range(n_sims):
        rng = np.random.default_rng(seed=i * 12345 + 42)
        result = sim.run(rng)
        for c in range(N_CLASSES):
            counts[:, :, c] += (result == c)

    probs = counts.astype(np.float64) / n_sims

    probs = np.maximum(probs, PROB_FLOOR)
    probs /= probs.sum(axis=-1, keepdims=True)

    return probs
