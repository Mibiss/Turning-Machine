#!/usr/bin/env python3
"""
Astar Island — Viking Civilisation Prediction Pipeline
=======================================================
Canonical entrypoint for the round: authenticate → observe → model → predict → submit.
(Other `*.py` helpers in this folder are optional / legacy.)

Usage:
    export ASTAR_TOKEN=<your_jwt_token>   # from app.ainm.no cookies
    python astar_island.py

    # Dry run (observe but don't submit):
    python astar_island.py --dry-run

    # Save observations to disk after sweeping (recommended):
    python astar_island.py --save-obs ./obs

    # Load saved observations and skip re-querying:
    python astar_island.py --load-obs ./obs

    # Save obs + dry-run (observe, save, don't submit):
    python astar_island.py --save-obs ./obs --dry-run

    # Load saved obs + submit (build predictions from disk, submit):
    python astar_island.py --load-obs ./obs

    # Skip observation entirely (uniform baseline):
    python astar_island.py --baseline-only
"""

import argparse
import os
import sys
import time
import json
import logging
from typing import Optional

import numpy as np
import requests

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("astar")

# ─── Conditioned prior + simulator imports (lazy — only loaded if available) ─
_expansion_estimator = None
_conditioned_prior_builder = None

def _get_expansion_estimator():
    global _expansion_estimator
    if _expansion_estimator is None:
        try:
            from param_inference import ExpansionEstimator
            _expansion_estimator = ExpansionEstimator()
        except Exception as e:
            log.warning("Could not load ExpansionEstimator: %s", e)
    return _expansion_estimator

def _get_conditioned_prior_builder():
    global _conditioned_prior_builder
    if _conditioned_prior_builder is None:
        try:
            from conditioned_prior import ConditionedPriorBuilder
            _conditioned_prior_builder = ConditionedPriorBuilder()
        except Exception as e:
            log.warning("Could not load ConditionedPriorBuilder: %s", e)
    return _conditioned_prior_builder

# ─── Constants ────────────────────────────────────────────────────────────────

BASE_URL = "https://api.ainm.no"

# ── Initial map terrain codes ──
OCEAN      = 10
PLAINS     = 11
EMPTY      = 0
SETTLEMENT = 1
PORT       = 2
RUIN       = 3
FOREST     = 4
MOUNTAIN   = 5

# ── Prediction class indices ──
C_EMPTY      = 0
C_SETTLEMENT = 1
C_PORT       = 2
C_RUIN       = 3
C_FOREST     = 4
C_MOUNTAIN   = 5
N_CLASSES    = 6

TERRAIN_TO_CLASS = {
    OCEAN:      C_EMPTY,
    PLAINS:     C_EMPTY,
    EMPTY:      C_EMPTY,
    SETTLEMENT: C_SETTLEMENT,
    PORT:       C_PORT,
    RUIN:       C_RUIN,
    FOREST:     C_FOREST,
    MOUNTAIN:   C_MOUNTAIN,
}

# NEVER assign 0 to any class — KL divergence becomes infinite
PROB_FLOOR = 0.01

# Per-terrain pseudo-count weight for prior blend: (counts + α·π) / (n + α)
# Cross-validated on 85 ground-truth records. Higher alpha = trust prior more.
# Optimal around 8-10 for all terrains with 1-3 observations per cell.
ALPHA_PER_TERRAIN = {
    PLAINS:     10.0,
    EMPTY:      10.0,
    FOREST:     10.0,
    SETTLEMENT:  8.0,
    PORT:        8.0,
    RUIN:        8.0,
}
ALPHA_DEFAULT = 10.0

# ── Spatial priors ──
# Keyed by "terrain|dist_bin|coastal_label" → [empty, settlement, port, ruin, forest, mountain]
# Computed from 90 ground-truth records via calibrate.py calibrate_spatial().
# Loaded from spatial_priors.json if available; these hardcoded values are the fallback.
_SPATIAL_PRIORS_HARDCODED = {
    # Settlement terrain
    "settlement|0-2|inland":  [0.4225, 0.3453, 0.0010, 0.0271, 0.2031, 0.0010],
    "settlement|0-2|coastal": [0.4233, 0.3278, 0.0193, 0.0257, 0.2029, 0.0010],
    # Port terrain
    "port|0-2|coastal":       [0.4587, 0.1013, 0.1935, 0.0226, 0.2230, 0.0010],
    # Forest terrain
    "forest|0-2|inland":      [0.1037, 0.2140, 0.0010, 0.0183, 0.6621, 0.0010],
    "forest|0-2|coastal":     [0.0910, 0.1798, 0.0420, 0.0166, 0.6697, 0.0010],
    "forest|3-5|inland":      [0.0500, 0.1145, 0.0010, 0.0104, 0.8231, 0.0010],
    "forest|3-5|coastal":     [0.0368, 0.0760, 0.0225, 0.0076, 0.8561, 0.0010],
    "forest|6+|inland":       [0.0061, 0.0266, 0.0010, 0.0023, 0.9631, 0.0010],
    "forest|6+|coastal":      [0.0061, 0.0169, 0.0054, 0.0017, 0.9689, 0.0010],
    # Plains/empty terrain
    "plains|0-2|inland":      [0.7228, 0.2090, 0.0010, 0.0177, 0.0485, 0.0010],
    "plains|0-2|coastal":     [0.7293, 0.1688, 0.0432, 0.0158, 0.0419, 0.0010],
    "plains|3-5|inland":      [0.8561, 0.1087, 0.0010, 0.0101, 0.0232, 0.0010],
    "plains|3-5|coastal":     [0.8760, 0.0748, 0.0230, 0.0075, 0.0176, 0.0010],
    "plains|6+|inland":       [0.9728, 0.0210, 0.0010, 0.0016, 0.0026, 0.0010],
    "plains|6+|coastal":      [0.9711, 0.0177, 0.0056, 0.0018, 0.0029, 0.0010],
    # Ruin terrain (rare in initial grids — use settlement-like priors with ruin bias)
    "ruin|0-2|inland":        [0.2000, 0.1800, 0.0010, 0.3000, 0.2000, 0.0010],
    "ruin|0-2|coastal":       [0.2000, 0.1500, 0.1000, 0.2500, 0.2000, 0.0010],
    "ruin|3-5|inland":        [0.3000, 0.0800, 0.0010, 0.2500, 0.2500, 0.0010],
    "ruin|3-5|coastal":       [0.3000, 0.0600, 0.0500, 0.2000, 0.2500, 0.0010],
    "ruin|6+|inland":         [0.3500, 0.0300, 0.0010, 0.2000, 0.3000, 0.0010],
    "ruin|6+|coastal":        [0.3500, 0.0250, 0.0300, 0.1800, 0.3000, 0.0010],
}

# Map terrain codes to the name prefix used in spatial prior keys
_TERRAIN_KEY_NAME = {
    FOREST:     "forest",
    SETTLEMENT: "settlement",
    PORT:       "port",
    RUIN:       "ruin",
    PLAINS:     "plains",
    EMPTY:      "plains",  # empty uses same priors as plains
}


def _load_spatial_priors() -> dict:
    """Load spatial priors from JSON file, falling back to hardcoded values."""
    search_paths = [
        os.path.join(os.path.dirname(__file__), "calibration_data", "spatial_priors.json"),
        os.path.join("calibration_data", "spatial_priors.json"),
    ]
    for path in search_paths:
        if os.path.exists(path):
            try:
                with open(path) as f:
                    data = json.load(f)
                # Convert to {key: np.array} format
                priors = {}
                for key, info in data.items():
                    priors[key] = np.array(info["probs"], dtype=np.float64)
                log.info("Loaded %d spatial priors from %s", len(priors), path)
                return priors
            except Exception as e:
                log.warning("Failed to load spatial priors from %s: %s", path, e)
    log.info("Using hardcoded spatial priors (no spatial_priors.json found)")
    return {k: np.array(v, dtype=np.float64) for k, v in _SPATIAL_PRIORS_HARDCODED.items()}


_SPATIAL_PRIORS = _load_spatial_priors()

# Rate limits
SIMULATE_DELAY = 0.22   # <= 5 req/sec
SUBMIT_DELAY   = 0.55   # <= 2 req/sec


# ─── API Client ───────────────────────────────────────────────────────────────

class AstarClient:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        })

    def get_rounds(self) -> list:
        return self._get("/astar-island/rounds")

    def get_active_round(self) -> Optional[dict]:
        return next((r for r in self.get_rounds() if r["status"] == "active"), None)

    def get_round_detail(self, round_id: str) -> dict:
        return self._get(f"/astar-island/rounds/{round_id}")

    def get_budget(self) -> dict:
        return self._get("/astar-island/budget")

    def simulate(self, round_id: str, seed_index: int, vx: int, vy: int, vw: int = 15, vh: int = 15) -> dict:
        return self._post("/astar-island/simulate", {
            "round_id": round_id,
            "seed_index": seed_index,
            "viewport_x": vx,
            "viewport_y": vy,
            "viewport_w": vw,
            "viewport_h": vh,
        })

    def submit(self, round_id: str, seed_index: int, prediction: np.ndarray) -> dict:
        _validate_prediction(prediction)
        return self._post("/astar-island/submit", {
            "round_id": round_id,
            "seed_index": seed_index,
            "prediction": prediction.tolist(),
        })

    def _get(self, path: str):
        r = self.session.get(BASE_URL + path)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, payload: dict) -> dict:
        r = self.session.post(BASE_URL + path, json=payload)
        r.raise_for_status()
        return r.json()


# ─── Prediction Validation ────────────────────────────────────────────────────

def _validate_prediction(pred: np.ndarray):
    H, W, C = pred.shape
    assert C == N_CLASSES, f"Expected 6 classes, got {C}"
    assert pred.min() >= 0, f"Negative probability: {pred.min()}"
    sums = pred.sum(axis=-1)
    if not np.allclose(sums, 1.0, atol=0.01):
        raise ValueError(f"Probabilities don't sum to 1. Range: [{sums.min():.4f}, {sums.max():.4f}]")


def apply_floor_and_normalize(pred: np.ndarray, floor: float = PROB_FLOOR) -> np.ndarray:
    pred = np.maximum(pred, floor)
    pred = pred / pred.sum(axis=-1, keepdims=True)
    return pred


def apply_static_hard_constraints(pred: np.ndarray, initial_grid: np.ndarray, floor: float = PROB_FLOOR) -> np.ndarray:
    """Near-deterministic ocean (empty) and mountain; keeps a floor on other classes for numerical safety."""
    out = np.array(pred, dtype=np.float64, copy=True)
    m_mtn = initial_grid == MOUNTAIN
    m_ocn = initial_grid == OCEAN
    out[m_mtn] = floor
    out[m_mtn, C_MOUNTAIN] = 1.0 - (N_CLASSES - 1) * floor
    out[m_ocn] = floor
    out[m_ocn, C_EMPTY] = 1.0 - (N_CLASSES - 1) * floor
    return out / out.sum(axis=-1, keepdims=True)


# ─── Map State ────────────────────────────────────────────────────────────────

class MapState:
    def __init__(self, height: int, width: int, initial_grid: list, initial_settlements: list):
        self.H = height
        self.W = width
        self.initial_grid        = np.array(initial_grid, dtype=np.int32)
        self.initial_settlements = initial_settlements

        self.obs_counts = np.zeros((height, width, N_CLASSES), dtype=np.float32)
        self.obs_total  = np.zeros((height, width), dtype=np.int32)

        # Settlement metadata from simulate responses: {(x,y): [list of stat dicts]}
        self.settlement_stats: dict = {}

        # Optional: conditioned prior grid (H, W, 6) set externally
        # When set, used instead of _terrain_prior_grid() for better predictions
        self.conditioned_prior_grid: Optional[np.ndarray] = None

        self._coast_mask    = self._compute_coast_mask(radius=2)
        self._settle_dist   = self._compute_settlement_distance()

    # ── Save / load ───────────────────────────────────────────────────────────

    def save(self, path: str):
        """Serialise observation counts to JSON so they survive between runs."""
        # Convert settlement_stats keys from tuples to strings for JSON
        ss_serialized = {f"{x},{y}": v for (x, y), v in self.settlement_stats.items()}
        data = {
            "height":              self.H,
            "width":               self.W,
            "initial_grid":        self.initial_grid.tolist(),
            "initial_settlements": self.initial_settlements,
            "obs_counts":          self.obs_counts.tolist(),
            "obs_total":           self.obs_total.tolist(),
            "settlement_stats":    ss_serialized,
        }
        with open(path, "w") as f:
            json.dump(data, f)

    @classmethod
    def load(cls, path: str) -> "MapState":
        """Restore a MapState from a saved JSON file."""
        with open(path) as f:
            data = json.load(f)
        ms = cls(
            height=data["height"],
            width=data["width"],
            initial_grid=data["initial_grid"],
            initial_settlements=data["initial_settlements"],
        )
        ms.obs_counts = np.array(data["obs_counts"], dtype=np.float32)
        ms.obs_total  = np.array(data["obs_total"],  dtype=np.int32)
        # Restore settlement stats if present
        ss_raw = data.get("settlement_stats", {})
        for key_str, v in ss_raw.items():
            x, y = map(int, key_str.split(","))
            ms.settlement_stats[(x, y)] = v
        return ms

    # ── Observation ingestion ─────────────────────────────────────────────────

    def add_observation(self, viewport: dict, grid: list, settlements: list):
        vx = viewport["x"]
        vy = viewport["y"]

        settle_cls = {}
        for s in settlements:
            sx, sy = s["x"], s["y"]
            if s.get("alive", True):
                cls = C_PORT if s.get("has_port") else C_SETTLEMENT
            else:
                cls = C_RUIN
            settle_cls[(sx, sy)] = cls

            # Capture settlement metadata for prediction adjustments
            key = (sx, sy)
            if key not in self.settlement_stats:
                self.settlement_stats[key] = []
            self.settlement_stats[key].append({
                "alive": s.get("alive", True),
                "has_port": s.get("has_port", False),
                "population": s.get("population"),
                "food": s.get("food"),
                "wealth": s.get("wealth"),
                "defense": s.get("defense"),
                "technology": s.get("technology"),
                "owner_id": s.get("owner_id"),
            })

        for row_i, row in enumerate(grid):
            for col_i, terrain_code in enumerate(row):
                wx = vx + col_i
                wy = vy + row_i
                if not (0 <= wx < self.W and 0 <= wy < self.H):
                    continue
                if (wx, wy) in settle_cls:
                    cls = settle_cls[(wx, wy)]
                else:
                    cls = TERRAIN_TO_CLASS.get(terrain_code, C_EMPTY)
                self.obs_counts[wy, wx, cls] += 1
                self.obs_total[wy, wx] += 1

    # ── Prediction builder ────────────────────────────────────────────────────

    def build_prediction(self, baseline_only: bool = False) -> np.ndarray:
        if baseline_only:
            pred = np.full((self.H, self.W, N_CLASSES), 1.0 / N_CLASSES, dtype=np.float64)
            pred = apply_static_hard_constraints(pred, self.initial_grid)
            pred = apply_floor_and_normalize(pred)
            return pred.astype(np.float32)

        pred = self.raw_prediction_grid()
        pred = apply_static_hard_constraints(pred, self.initial_grid)
        pred = apply_floor_and_normalize(pred)
        return pred.astype(np.float32)

    def raw_prediction_grid(self) -> np.ndarray:
        """
        Distribution per cell before static hard constraints and probability floor.
        Uses spatial priors, per-terrain alpha, and settlement metadata for blending.
        If conditioned_prior_grid is set, uses it instead of static spatial priors
        and applies a reduced alpha (conditioned prior is already better matched).
        """
        g = self.initial_grid

        # Use conditioned prior if available, otherwise static spatial priors
        if self.conditioned_prior_grid is not None:
            terrain_p = self.conditioned_prior_grid.copy()
            use_conditioned = True
        else:
            terrain_p = self._terrain_prior_grid()
            use_conditioned = False

        # Apply settlement metadata adjustments to the prior
        terrain_p = self._adjust_priors_from_metadata(terrain_p)

        pred = terrain_p.copy()

        m_mtn = g == MOUNTAIN
        m_ocn = g == OCEAN
        pred[m_mtn] = self._static_prior_row(C_MOUNTAIN)
        pred[m_ocn] = self._static_prior_row(C_EMPTY)

        n = self.obs_total.astype(np.float64)
        has_obs = n > 0
        blend_mask = has_obs & ~m_mtn & ~m_ocn
        if np.any(blend_mask):
            # Build per-cell alpha grid from initial terrain
            alpha_grid = np.full((self.H, self.W), ALPHA_DEFAULT, dtype=np.float64)
            for terrain_code, alpha_val in ALPHA_PER_TERRAIN.items():
                alpha_grid[g == terrain_code] = alpha_val
            # Reduce alpha when using conditioned priors (they're already better matched)
            if use_conditioned:
                alpha_grid *= 0.6  # ~10 → ~6
            # With more observations, trust data more — lower effective alpha
            alpha = alpha_grid[..., None]  # (H, W, 1) for broadcasting
            counts = self.obs_counts.astype(np.float64)
            blended = (counts + alpha * terrain_p) / (n[..., None] + alpha_grid[..., None])
            pred = np.where(blend_mask[..., None], blended, pred)

        return pred

    def _adjust_priors_from_metadata(self, prior: np.ndarray) -> np.ndarray:
        """
        Adjust priors for settlement cells based on observed metadata.
        Strong settlements (high pop/food/defense) → more likely to survive.
        Weak settlements → more likely to become ruins.
        """
        if not self.settlement_stats:
            return prior

        out = prior.copy()
        for (sx, sy), stats_list in self.settlement_stats.items():
            if not (0 <= sx < self.W and 0 <= sy < self.H):
                continue

            # Average stats across observations
            alive_frac = sum(1 for s in stats_list if s.get("alive")) / len(stats_list)

            # Extract numeric stats (may be None if API doesn't return them)
            pops = [s["population"] for s in stats_list if s.get("population") is not None]
            foods = [s["food"] for s in stats_list if s.get("food") is not None]
            defenses = [s["defense"] for s in stats_list if s.get("defense") is not None]

            if not pops:
                # No metadata available — skip adjustment
                continue

            avg_pop = sum(pops) / len(pops) if pops else 0
            avg_food = sum(foods) / len(foods) if foods else 0
            avg_def = sum(defenses) / len(defenses) if defenses else 0

            # Health score: 0 (dying) to 1 (thriving)
            # Normalize roughly — typical pop ~50-200, food ~0-500, defense ~0-100
            health = min(1.0, (avg_pop / 150 + avg_food / 300 + avg_def / 80) / 3)

            p = out[sy, sx].copy()
            initial_terrain = self.initial_grid[sy, sx]
            is_coastal = self._coast_mask[sy, sx]

            if alive_frac > 0.5:
                # Settlement is alive in most observations
                # High health → stays settlement/port; low health → risk of ruin
                survival_boost = 0.15 * health
                p[C_SETTLEMENT] += survival_boost
                p[C_RUIN] -= survival_boost * 0.5
                p[C_EMPTY] -= survival_boost * 0.3
                p[C_FOREST] -= survival_boost * 0.2
                if is_coastal and health > 0.5:
                    p[C_PORT] += 0.05 * health
                    p[C_SETTLEMENT] -= 0.05 * health
            else:
                # Settlement is dead in most observations → boost ruin/forest
                p[C_RUIN] += 0.10
                p[C_FOREST] += 0.05
                p[C_SETTLEMENT] -= 0.10
                p[C_PORT] -= 0.03
                p[C_EMPTY] -= 0.02

            # Owner diversity signal: many factions → conflict → higher ruin risk
            owner_ids = [s.get("owner_id") for s in stats_list if s.get("owner_id") is not None]
            if len(owner_ids) >= 2:
                n_unique = len(set(owner_ids))
                diversity = n_unique / len(owner_ids)  # 0..1
                if diversity > 0.5:
                    # High diversity → conflict → boost ruin, reduce settlement
                    conflict_adj = 0.08 * (diversity - 0.5)
                    p[C_RUIN] += conflict_adj
                    p[C_SETTLEMENT] -= conflict_adj * 0.6
                    p[C_EMPTY] -= conflict_adj * 0.4
                elif diversity < 0.3:
                    # Low diversity → stability → boost settlement survival
                    stability_adj = 0.05 * (0.3 - diversity)
                    p[C_SETTLEMENT] += stability_adj
                    p[C_RUIN] -= stability_adj

            p = np.maximum(p, PROB_FLOOR)
            out[sy, sx] = p / p.sum()

        return out

    # ── Priors (vectorised) ───────────────────────────────────────────────────

    @staticmethod
    def _static_prior_row(dominant_class: int) -> np.ndarray:
        p = np.full(N_CLASSES, PROB_FLOOR, dtype=np.float64)
        p[dominant_class] = 1.0 - (N_CLASSES - 1) * PROB_FLOOR
        return p

    def _terrain_prior_grid(self) -> np.ndarray:
        """Build per-cell prior using spatial context (settlement distance + coastal)."""
        g = self.initial_grid
        coast = self._coast_mask
        sdist = self._settle_dist

        # Distance bins: 0 = 0-2, 1 = 3-5, 2 = 6+
        dist_bin = np.where(sdist <= 2, 0, np.where(sdist <= 5, 1, 2))
        dist_labels = {0: "0-2", 1: "3-5", 2: "6+"}

        # Default: uniform-ish prior
        p = np.full((self.H, self.W, N_CLASSES), 1.0 / N_CLASSES, dtype=np.float64)

        # For each dynamic terrain, assign spatial priors per cell
        for terrain_code, tname in _TERRAIN_KEY_NAME.items():
            tmask = g == terrain_code
            if not np.any(tmask):
                continue
            for db_idx, db_label in dist_labels.items():
                for is_coastal in (False, True):
                    coast_label = "coastal" if is_coastal else "inland"
                    key = f"{tname}|{db_label}|{coast_label}"
                    prior_vec = _SPATIAL_PRIORS.get(key)
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

    # ── Spatial helpers ───────────────────────────────────────────────────────

    def _compute_coast_mask(self, radius: int = 2) -> np.ndarray:
        ocean = (self.initial_grid == OCEAN).astype(np.float32)
        try:
            from scipy.ndimage import maximum_filter
            return maximum_filter(ocean, size=2 * radius + 1).astype(bool)
        except ImportError:
            mask = np.zeros((self.H, self.W), dtype=bool)
            oy, ox = np.where(ocean)
            for cy, cx in zip(oy, ox):
                y0, y1 = max(0, cy - radius), min(self.H, cy + radius + 1)
                x0, x1 = max(0, cx - radius), min(self.W, cx + radius + 1)
                mask[y0:y1, x0:x1] = True
            return mask

    def _compute_settlement_distance(self) -> np.ndarray:
        if not self.initial_settlements:
            return np.full((self.H, self.W), 999, dtype=np.int32)
        sx = np.array([s["x"] for s in self.initial_settlements], dtype=np.int32)
        sy = np.array([s["y"] for s in self.initial_settlements], dtype=np.int32)
        X = np.arange(self.W, dtype=np.int32)[None, None, :]
        Y = np.arange(self.H, dtype=np.int32)[None, :, None]
        d = np.maximum(np.abs(X - sx[:, None, None]), np.abs(Y - sy[:, None, None]))
        return d.min(axis=0).astype(np.int32)

    # ── Diagnostics ───────────────────────────────────────────────────────────

    def coverage_report(self) -> dict:
        observed     = (self.obs_total > 0).sum()
        total        = self.H * self.W
        static_cells = ((self.initial_grid == OCEAN) | (self.initial_grid == MOUNTAIN)).sum()
        dynamic      = total - static_cells
        dynamic_obs  = (
            (self.obs_total > 0)
            & (self.initial_grid != OCEAN)
            & (self.initial_grid != MOUNTAIN)
        ).sum()
        return {
            "total_cells":      total,
            "observed":         int(observed),
            "coverage_pct":     round(100 * observed / total, 1),
            "dynamic_cells":    int(dynamic),
            "dynamic_observed": int(dynamic_obs),
            "dynamic_pct":      round(100 * dynamic_obs / dynamic, 1) if dynamic else 0,
        }


# ─── Query Strategy ───────────────────────────────────────────────────────────

class QueryStrategy:
    def __init__(self, height: int, width: int, viewport_size: int = 15):
        self.H  = height
        self.W  = width
        self.VS = viewport_size

    def full_coverage_tiles(self) -> list:
        tiles = []
        ys = list(range(0, self.H, self.VS))
        xs = list(range(0, self.W, self.VS))
        if ys[-1] + self.VS > self.H:
            ys[-1] = max(0, self.H - self.VS)
        if xs[-1] + self.VS > self.W:
            xs[-1] = max(0, self.W - self.VS)
        for vy in ys:
            for vx in xs:
                tiles.append((vx, vy))
        return tiles

    def dynamic_coverage_tiles(self, state: MapState, max_tiles: int,
                               min_tile_weight: float = 2.0) -> list:
        """
        Greedy tile selection maximizing coverage of uncovered dynamic cells,
        weighted by settlement proximity.
        Tiles whose uncovered dynamic weight is below *min_tile_weight* are
        skipped — those cells are mostly ocean/mountain/distant forest where
        the prior alone is sufficient.
        """
        g = state.initial_grid
        static = (g == OCEAN) | (g == MOUNTAIN)
        dynamic = ~static

        # Weight by settlement proximity: dist 0-2 → 3.0, dist 3-5 → 1.0, dist 6+ → 0.1
        sdist = state._settle_dist
        weight = np.where(sdist <= 2, 3.0, np.where(sdist <= 5, 1.0, 0.1))
        weight[static] = 0.0

        # Track which cells are already covered
        covered = np.zeros((self.H, self.W), dtype=bool)
        VS = self.VS

        # Generate candidate tile positions
        candidates = []
        ys = list(range(0, self.H, VS))
        xs = list(range(0, self.W, VS))
        if ys[-1] + VS > self.H:
            ys[-1] = max(0, self.H - VS)
        if xs[-1] + VS > self.W:
            xs[-1] = max(0, self.W - VS)
        for vy in ys:
            for vx in xs:
                candidates.append((vx, vy))

        selected = []
        for _ in range(min(max_tiles, len(candidates))):
            best_score = -1
            best_tile = None
            best_idx = -1
            for idx, (vx, vy) in enumerate(candidates):
                patch_dyn = dynamic[vy : vy + VS, vx : vx + VS]
                patch_cov = covered[vy : vy + VS, vx : vx + VS]
                patch_w = weight[vy : vy + VS, vx : vx + VS]
                uncovered = patch_dyn & ~patch_cov
                score = float((uncovered * patch_w).sum())
                if score > best_score:
                    best_score = score
                    best_tile = (vx, vy)
                    best_idx = idx
            if best_tile is None or best_score < min_tile_weight:
                break
            selected.append(best_tile)
            vx, vy = best_tile
            covered[vy : vy + VS, vx : vx + VS] = True
            candidates.pop(best_idx)

        return selected

    def entropy_ranked_viewports(self, state: MapState, n: int, stride: int = 3) -> list:
        """Rank candidate viewports by dynamic-cell entropy (ignore ocean/mountain)."""
        p = np.clip(state.raw_prediction_grid(), 1e-12, 1.0)
        ent = -(p * np.log(p)).sum(axis=-1)

        # Zero out entropy on static cells — they don't contribute to scoring
        static_mask = (state.initial_grid == OCEAN) | (state.initial_grid == MOUNTAIN)
        ent[static_mask] = 0.0
        dynamic_mask = ~static_mask

        VS = self.VS
        scored = []
        for vy in range(0, max(1, self.H - VS + 1), stride):
            for vx in range(0, max(1, self.W - VS + 1), stride):
                vx2 = min(vx, self.W - VS)
                vy2 = min(vy, self.H - VS)
                patch_ent = ent[vy2 : vy2 + VS, vx2 : vx2 + VS]
                patch_dyn = dynamic_mask[vy2 : vy2 + VS, vx2 : vx2 + VS]
                n_dyn = patch_dyn.sum()
                if n_dyn == 0:
                    continue  # skip all-static viewports
                score = float(patch_ent.sum()) * int(n_dyn)
                scored.append((score, vx2, vy2))
        scored.sort(reverse=True, key=lambda t: t[0])
        seen = set()
        result = []
        for _, vx, vy in scored:
            if (vx, vy) in seen:
                continue
            seen.add((vx, vy))
            result.append((vx, vy))
            if len(result) >= n:
                break
        return result

    def reobs_ranked_viewports(self, state: MapState, n: int, stride: int = 3) -> list:
        """
        Rank viewports by observation-count-aware entropy score.
        score(viewport) = sum_cell [ entropy(cell) / sqrt(obs_count(cell) + 1) ]
        for dynamic cells only.  Prioritises unseen high-entropy cells while
        still giving value to re-observing cells with few observations.
        """
        p = np.clip(state.raw_prediction_grid(), 1e-12, 1.0)
        ent = -(p * np.log(p)).sum(axis=-1)  # (H, W)

        static_mask = (state.initial_grid == OCEAN) | (state.initial_grid == MOUNTAIN)
        ent[static_mask] = 0.0

        # Observation-count discount: 1/sqrt(n+1)
        obs_discount = 1.0 / np.sqrt(state.obs_total.astype(np.float64) + 1.0)
        weighted_ent = ent * obs_discount  # (H, W)

        VS = self.VS
        scored = []
        for vy in range(0, max(1, self.H - VS + 1), stride):
            for vx in range(0, max(1, self.W - VS + 1), stride):
                vx2 = min(vx, self.W - VS)
                vy2 = min(vy, self.H - VS)
                patch = weighted_ent[vy2 : vy2 + VS, vx2 : vx2 + VS]
                score = float(patch.sum())
                if score <= 0:
                    continue
                scored.append((score, vx2, vy2))

        scored.sort(reverse=True, key=lambda t: t[0])
        seen = set()
        result = []
        for _, vx, vy in scored:
            if (vx, vy) in seen:
                continue
            seen.add((vx, vy))
            result.append((vx, vy))
            if len(result) >= n:
                break
        return result


# ─── Main Pipeline ────────────────────────────────────────────────────────────

class AstarPipeline:
    def __init__(
        self,
        token: str,
        dry_run: bool = False,
        save_obs: Optional[str] = None,
        load_obs: Optional[str] = None,
    ):
        self.client   = AstarClient(token)
        self.dry_run  = dry_run
        self.save_obs = save_obs   # directory to write obs_r{N}_s{S}.json files
        self.load_obs = load_obs   # directory to read  obs_r{N}_s{S}.json files
        self.states: dict = {}
        self._baseline_only = False

    def run(self, baseline_only: bool = False):
        self._baseline_only = baseline_only
        log.info("=" * 60)
        log.info("Astar Island Pipeline")
        log.info("=" * 60)

        # 1 ── Find active round ───────────────────────────────────────────────
        log.info("Fetching active round...")
        active = self.client.get_active_round()
        if not active:
            log.error("No active round found. Check app.ainm.no for schedule.")
            return

        round_id     = active["id"]
        round_number = active["round_number"]
        log.info("Round %d active | closes: %s", round_number, active["closes_at"])

        # 2 ── Fetch round details ─────────────────────────────────────────────
        log.info("Fetching round details...")
        detail  = self.client.get_round_detail(round_id)
        H       = detail["map_height"]
        W       = detail["map_width"]
        n_seeds = detail["seeds_count"]
        log.info("Map: %d×%d | seeds: %d", W, H, n_seeds)

        for i, state_data in enumerate(detail["initial_states"]):
            ms = MapState(
                height=H,
                width=W,
                initial_grid=state_data["grid"],
                initial_settlements=state_data["settlements"],
            )
            self.states[i] = ms
            log.info(
                "  Seed %d: %d settlements | %d ports",
                i,
                sum(1 for s in state_data["settlements"] if not s.get("has_port")),
                sum(1 for s in state_data["settlements"] if s.get("has_port")),
            )

        # 3 ── Check budget ────────────────────────────────────────────────────
        budget_info  = self.client.get_budget()
        queries_used = budget_info["queries_used"]
        queries_max  = budget_info["queries_max"]
        queries_left = queries_max - queries_used
        log.info("Budget: %d / %d queries used (%d remaining)", queries_used, queries_max, queries_left)

        # 4a ── Load saved observations from disk ──────────────────────────────
        if self.load_obs:
            log.info("Loading observations from %s ...", self.load_obs)
            loaded = 0
            for seed_idx in range(n_seeds):
                obs_path = os.path.join(self.load_obs, f"obs_r{round_number}_s{seed_idx}.json")
                if os.path.exists(obs_path):
                    self.states[seed_idx] = MapState.load(obs_path)
                    rep = self.states[seed_idx].coverage_report()
                    log.info(
                        "  Seed %d loaded | coverage %s%% | dynamic %s%%",
                        seed_idx, rep["coverage_pct"], rep["dynamic_pct"],
                    )
                    loaded += 1
                else:
                    log.warning("  Seed %d — no file at %s, will use prior only", seed_idx, obs_path)
            log.info("Loaded %d / %d seeds from disk.", loaded, n_seeds)

        # 4b ── Observation phase ──────────────────────────────────────────────
        if baseline_only or queries_left == 0:
            if baseline_only:
                log.info("Baseline-only mode — skipping observation (uniform + static cells).")
            else:
                log.warning("No queries remaining — building from priors only.")
        else:
            self._observe(round_id, n_seeds, queries_left, H, W)

        # 4c ── Save observations to disk ──────────────────────────────────────
        if self.save_obs:
            os.makedirs(self.save_obs, exist_ok=True)
            for seed_idx, state in self.states.items():
                obs_path = os.path.join(self.save_obs, f"obs_r{round_number}_s{seed_idx}.json")
                state.save(obs_path)
                rep = state.coverage_report()
                log.info(
                    "  Saved seed %d → %s | coverage %s%% | dynamic %s%%",
                    seed_idx, obs_path, rep["coverage_pct"], rep["dynamic_pct"],
                )

        # 5 ── Build and submit predictions ────────────────────────────────────
        self._predict_and_submit(round_id, n_seeds)

    # ── Observation ───────────────────────────────────────────────────────────

    def _observe(self, round_id: str, n_seeds: int, budget: int, H: int, W: int):
        log.info("-" * 40)
        log.info("Observation phase — %d queries available", budget)

        strategy = QueryStrategy(H, W, viewport_size=15)

        # ── Pool 1: Per-seed coverage ─────────────────────────────────────────
        # Give each seed a reduced coverage budget; remaining goes to cross-seed re-obs
        coverage_per_seed = min(7, budget // n_seeds)
        total_coverage_budget = coverage_per_seed * n_seeds
        queries_used_total = 0

        log.info(
            "Pool 1 — coverage: %d/seed × %d seeds = %d queries",
            coverage_per_seed, n_seeds, total_coverage_budget,
        )

        for seed_idx in range(n_seeds):
            state = self.states[seed_idx]
            log.info("── Seed %d coverage ──", seed_idx)

            coverage = strategy.dynamic_coverage_tiles(state, coverage_per_seed)
            log.info("  %d coverage tiles (budget %d)", len(coverage), coverage_per_seed)
            queries_this_seed = 0
            for vx, vy in coverage:
                if queries_this_seed >= coverage_per_seed:
                    break
                result = self._simulate_with_retry(round_id, seed_idx, vx, vy)
                if result is None:
                    break
                state.add_observation(result["viewport"], result["grid"], result["settlements"])
                queries_this_seed += 1
                time.sleep(SIMULATE_DELAY)

            queries_used_total += queries_this_seed
            rep = state.coverage_report()
            log.info(
                "  Seed %d coverage done | dynamic %s%% | queries: %d",
                seed_idx, rep["dynamic_pct"], queries_this_seed,
            )

        # ── Pool 2: Cross-seed re-observation ─────────────────────────────────
        reobs_budget = budget - queries_used_total
        log.info(
            "Pool 2 — re-observation: %d queries remaining across all seeds",
            reobs_budget,
        )

        reobs_used = 0
        while reobs_used < reobs_budget:
            # Rank candidate viewports across ALL seeds
            best_score = -1.0
            best_seed = -1
            best_vp = None

            for seed_idx in range(n_seeds):
                state = self.states[seed_idx]
                candidates = strategy.reobs_ranked_viewports(state, 1, stride=2)
                if not candidates:
                    continue
                vx, vy = candidates[0]
                # Compute the score for this viewport to compare across seeds
                p = np.clip(state.raw_prediction_grid(), 1e-12, 1.0)
                ent = -(p * np.log(p)).sum(axis=-1)
                static_mask = (state.initial_grid == OCEAN) | (state.initial_grid == MOUNTAIN)
                ent[static_mask] = 0.0
                obs_discount = 1.0 / np.sqrt(state.obs_total.astype(np.float64) + 1.0)
                weighted_ent = ent * obs_discount
                patch = weighted_ent[vy : vy + 15, vx : vx + 15]
                score = float(patch.sum())

                if score > best_score:
                    best_score = score
                    best_seed = seed_idx
                    best_vp = (vx, vy)

            if best_vp is None or best_score <= 0:
                log.info("  No more useful re-observation targets; stopping early.")
                break

            vx, vy = best_vp
            result = self._simulate_with_retry(round_id, best_seed, vx, vy)
            if result is None:
                break
            self.states[best_seed].add_observation(
                result["viewport"], result["grid"], result["settlements"],
            )
            reobs_used += 1
            if reobs_used % 5 == 0 or reobs_used == reobs_budget:
                log.info("  Re-obs %d/%d → seed %d @ (%d,%d) score=%.1f",
                         reobs_used, reobs_budget, best_seed, vx, vy, best_score)
            time.sleep(SIMULATE_DELAY)

        queries_used_total += reobs_used
        log.info("Re-observation done: %d queries used", reobs_used)

        # ── Summary ───────────────────────────────────────────────────────────
        for seed_idx in range(n_seeds):
            state = self.states[seed_idx]
            rep = state.coverage_report()
            dyn_mask = (state.initial_grid != OCEAN) & (state.initial_grid != MOUNTAIN)
            dyn_obs = state.obs_total[dyn_mask]
            avg_dyn = float(dyn_obs[dyn_obs > 0].mean()) if (dyn_obs > 0).any() else 0
            log.info(
                "  Seed %d summary | dynamic %s%% | avg dyn obs/cell: %.2f",
                seed_idx, rep["dynamic_pct"], avg_dyn,
            )
        log.info("Total queries used: %d / %d", queries_used_total, budget)

    def _simulate_with_retry(self, round_id: str, seed_idx: int, vx: int, vy: int, retries: int = 3) -> Optional[dict]:
        for attempt in range(retries):
            try:
                return self.client.simulate(round_id, seed_idx, vx, vy)
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else None
                if status == 429:
                    wait = 2 ** attempt
                    log.warning("Rate limited — waiting %ds...", wait)
                    time.sleep(wait)
                elif status == 400:
                    log.error("Simulate 400: round not active or invalid seed_index.")
                    return None
                else:
                    log.error("Simulate error %s: %s", status, e)
                    if attempt == retries - 1:
                        return None
        return None

    # ── Predict & submit ──────────────────────────────────────────────────────

    def _predict_and_submit(self, round_id: str, n_seeds: int):
        log.info("-" * 40)
        log.info("Prediction + submission phase")

        # ── Cross-seed expansion estimation ──
        # All seeds share the same hidden parameters, so aggregate stats
        estimator = _get_expansion_estimator()
        builder = _get_conditioned_prior_builder()

        expansion_level = None
        if estimator is not None and builder is not None:
            exp, conf = estimator.estimate_from_cross_seed_stats(self.states)
            expansion_level = exp
            log.info(
                "Expansion estimate: %.3f (confidence %.2f)", exp, conf,
            )

            # Build conditioned priors for each seed
            for seed_idx in range(n_seeds):
                state = self.states[seed_idx]
                prior = builder.build_prior(
                    state.initial_grid, state.initial_settlements, expansion_level,
                )
                state.conditioned_prior_grid = prior
                log.info("  Seed %d: conditioned prior set (expansion=%.3f)", seed_idx, expansion_level)
        else:
            log.info("Conditioned priors not available — using static spatial priors")

        for seed_idx in range(n_seeds):
            state = self.states[seed_idx]
            log.info("Building prediction for seed %d...", seed_idx)
            pred = state.build_prediction(baseline_only=self._baseline_only)
            _validate_prediction(pred)
            log.info(
                "  Seed %d | shape %s | min=%.4f max=%.4f sum_range=[%.4f, %.4f]",
                seed_idx, pred.shape, pred.min(), pred.max(),
                pred.sum(axis=-1).min(), pred.sum(axis=-1).max(),
            )

            if self.dry_run:
                log.info("  [DRY RUN] Not submitting seed %d", seed_idx)
            else:
                try:
                    resp = self.client.submit(round_id, seed_idx, pred)
                    log.info("  Seed %d submitted → status: %s", seed_idx, resp.get("status", "?"))
                except requests.HTTPError as e:
                    log.error("Submit failed for seed %d: %s", seed_idx, e)
                    if e.response is not None:
                        log.error("  Response: %s", e.response.text)

            time.sleep(SUBMIT_DELAY)

        log.info("=" * 60)
        log.info("Pipeline complete.")
        if not self.dry_run:
            log.info("Check your scores at: app.ainm.no")


# ─── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Astar Island prediction pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--token",        default=os.environ.get("ASTAR_TOKEN", ""), help="JWT token")
    parser.add_argument("--dry-run",      action="store_true", help="Observe but don't submit")
    parser.add_argument("--baseline-only",action="store_true", help="Skip observation; uniform prior + hard ocean/mountain")
    parser.add_argument("--save-obs",     metavar="DIR",       help="Save observations to DIR after sweeping")
    parser.add_argument("--load-obs",     metavar="DIR",       help="Load saved observations from DIR instead of re-querying")
    parser.add_argument("--debug",        action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if not args.token:
        print(
            "\n  ERROR: No JWT token provided.\n"
            "  Set it with:  export ASTAR_TOKEN=<your_token>\n"
            "  Get it from:  app.ainm.no → browser devtools → Cookies → access_token\n"
        )
        sys.exit(1)

    pipeline = AstarPipeline(
        token=args.token,
        dry_run=args.dry_run,
        save_obs=args.save_obs,
        load_obs=args.load_obs,
    )
    pipeline.run(baseline_only=args.baseline_only)


if __name__ == "__main__":
    main()