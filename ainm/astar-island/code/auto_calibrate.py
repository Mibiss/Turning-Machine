#!/usr/bin/env python3
"""
Auto-calibration watcher.

Behavior:
- Detect when new completed/scoring rounds appear in your history.
- Re-run calibration on completed rounds.
- Save a candidate prior file for review.
- Optionally patch main2.py priors if enabled and minimum sample thresholds pass.
"""

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import calibrate as cal

SCRIPT_DIR = Path(__file__).resolve().parent
STATE_PATH = SCRIPT_DIR / ".auto_calibrate_state.json"
OUTPUT_DIR = SCRIPT_DIR / "calibration_data"
LATEST_PRIORS_PATH = OUTPUT_DIR / "calibrated_priors.latest.json"
SPATIAL_PRIORS_PATH = OUTPUT_DIR / "spatial_priors.json"
MAIN2_PATH = SCRIPT_DIR / "main2.py"

TARGET_TERRAINS = {
    "forest": cal.FOREST,
    "settlement": cal.SETTLEMENT,
    "port": cal.PORT,
    "plains_empty": cal.PLAINS,
}

# Conservative defaults so tiny samples do not auto-overwrite priors.
MIN_COUNTS_DEFAULT = {
    "forest": 10000,
    "settlement": 1500,
    "port": 100,
    "plains_empty": 10000,
}


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(last_completed_round: int, updated: bool):
    payload = {
        "last_completed_round": last_completed_round,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_main2": updated,
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2))


def _max_completed_round(my_rounds: List[dict]) -> int:
    completed = [r for r in my_rounds if r.get("status") in ("completed", "scoring")]
    if not completed:
        return -1
    return max(int(r.get("round_number", -1)) for r in completed)


def _extract_candidates(calibrated: dict, cell_count: dict) -> Dict[str, dict]:
    out = {}
    for key, terrain in TARGET_TERRAINS.items():
        if terrain not in calibrated:
            continue
        vec = [float(x) for x in calibrated[terrain].tolist()]
        out[key] = {
            "terrain_code": terrain,
            "counts": int(cell_count.get(terrain, 0)),
            "probs": vec,
        }
    return out


def _write_candidate_file(candidates: Dict[str, dict], max_round: int):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "max_completed_round": max_round,
        "candidates": candidates,
    }
    LATEST_PRIORS_PATH.write_text(json.dumps(payload, indent=2))


def _passes_thresholds(candidates: Dict[str, dict], min_counts: Dict[str, int]) -> bool:
    for key, threshold in min_counts.items():
        c = candidates.get(key)
        if c is None or c["counts"] < threshold:
            return False
    return True


def _fmt_array(vals: List[float]) -> str:
    return "[" + ", ".join(f"{v:.4f}" for v in vals) + "]"


def _apply_to_main2(candidates: Dict[str, dict]) -> bool:
    text = MAIN2_PATH.read_text()
    replacements = {
        "_PRIOR_CAL_FOREST": _fmt_array(candidates["forest"]["probs"]),
        "_PRIOR_CAL_SETTLEMENT": _fmt_array(candidates["settlement"]["probs"]),
        "_PRIOR_CAL_PORT": _fmt_array(candidates["port"]["probs"]),
        "_PRIOR_CAL_PLAINS_EMPTY": _fmt_array(candidates["plains_empty"]["probs"]),
    }
    updated = text
    for name, arr in replacements.items():
        pattern = rf"({name}\s*=\s*np\.array\(\s*)\[[^\]]+\](\s*,\s*dtype=np\.float64\s*\))"
        updated, n = re.subn(pattern, rf"\1{arr}\2", updated, count=1)
        if n != 1:
            raise RuntimeError(f"Could not update {name} in main2.py")
    if updated != text:
        MAIN2_PATH.write_text(updated)
        return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Auto-calibrate priors for main2.py")
    parser.add_argument("--token", default=os.environ.get("ASTAR_TOKEN", ""), help="JWT token")
    parser.add_argument("--apply-main2", action="store_true", help="Auto-apply candidates to main2.py")
    args = parser.parse_args()

    token = args.token.strip()
    if not token:
        print("ASTAR_TOKEN is missing")
        return 1

    client = cal.AstarClient(token)
    my_rounds = client.get_my_rounds()
    max_round = _max_completed_round(my_rounds)
    if max_round < 0:
        print("No completed rounds yet")
        return 0

    state = _load_state()
    last_seen = int(state.get("last_completed_round", -1))
    if max_round <= last_seen:
        print(f"No new completed rounds (latest {max_round})")
        return 0

    records = cal.collect_analysis_data(client, save_dir=str(OUTPUT_DIR))
    calibrated, cell_count = cal.calibrate(records)
    candidates = _extract_candidates(calibrated, cell_count)
    _write_candidate_file(candidates, max_round)

    # Spatial calibration — write spatial_priors.json for main2.py auto-loading
    cal.calibrate_spatial(records, save_path=str(SPATIAL_PRIORS_PATH))

    print(f"Saved candidate priors: {LATEST_PRIORS_PATH}")
    print(f"Saved spatial priors:   {SPATIAL_PRIORS_PATH}")
    for key in ("forest", "settlement", "port", "plains_empty"):
        c = candidates.get(key)
        if c:
            print(f"  {key:12s} count={c['counts']:6d} probs={_fmt_array(c['probs'])}")
        else:
            print(f"  {key:12s} missing")

    updated = False
    if args.apply_main2:
        if _passes_thresholds(candidates, MIN_COUNTS_DEFAULT):
            updated = _apply_to_main2(candidates)
            if updated:
                print("Applied calibrated priors to main2.py")
            else:
                print("main2.py already up-to-date with candidates")
        else:
            print("Threshold check failed; skipped main2.py update")

    _save_state(max_round, updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
