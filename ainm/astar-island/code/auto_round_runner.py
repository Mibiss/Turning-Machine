#!/usr/bin/env python3
"""
Run main2.py automatically once per active round.

Designed to be called periodically (e.g. launchd StartInterval).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

BASE_URL = "https://api.ainm.no"
STATE_PATH = Path(__file__).resolve().parent / ".auto_round_state.json"
LOCK_PATH = Path(__file__).resolve().parent / ".auto_round_runner.lock"


def _get_active_round(token: str):
    r = requests.get(
        f"{BASE_URL}/astar-island/rounds",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    r.raise_for_status()
    rounds = r.json()
    for rnd in rounds:
        if rnd.get("status") == "active":
            return rnd
    return None


def _get_budget(token: str) -> dict:
    r = requests.get(
        f"{BASE_URL}/astar-island/budget",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _get_round_detail(token: str, round_id: str) -> dict:
    r = requests.get(
        f"{BASE_URL}/astar-island/rounds/{round_id}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()


def _has_complete_saved_obs(script_dir: Path, round_number: int, n_seeds: int) -> bool:
    obs_dir = script_dir / "obs"
    for seed_idx in range(n_seeds):
        p = obs_dir / f"obs_r{round_number}_s{seed_idx}.json"
        if not p.exists():
            return False
    return True


def _load_state():
    if not STATE_PATH.exists():
        return {}
    try:
        return json.loads(STATE_PATH.read_text())
    except Exception:
        return {}


def _save_state(round_id: str):
    payload = {
        "last_round_id": round_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    STATE_PATH.write_text(json.dumps(payload, indent=2))


def main():
    token = os.environ.get("ASTAR_TOKEN", "").strip()
    now = datetime.now(timezone.utc).isoformat()
    print(f"[{now}] round-runner tick")
    if LOCK_PATH.exists():
        print(f"[{now}] Previous run still in progress; skipping this tick")
        return 0
    LOCK_PATH.write_text(now)
    try:
        return _run_once(token, now)
    finally:
        if LOCK_PATH.exists():
            LOCK_PATH.unlink()


def _run_once(token: str, now: str) -> int:
    if not token:
        print(f"[{now}] ASTAR_TOKEN is missing")
        return 1

    active = _get_active_round(token)
    if not active:
        print(f"[{now}] No active round")
        return 0

    round_id = active["id"]
    round_number = active.get("round_number", "?")

    state = _load_state()
    if state.get("last_round_id") == round_id:
        print(f"[{now}] Round {round_number} already processed")
        return 0

    script_dir = Path(__file__).resolve().parent
    detail = _get_round_detail(token, round_id)
    n_seeds = int(detail.get("seeds_count", 5))
    budget = _get_budget(token)
    queries_left = int(budget.get("queries_max", 0)) - int(budget.get("queries_used", 0))
    have_saved_obs = _has_complete_saved_obs(script_dir, int(round_number), n_seeds)

    if queries_left <= 0 and not have_saved_obs:
        print(
            f"[{now}] Skipping round {round_number}: no queries left and no complete saved observations."
        )
        return 0

    if have_saved_obs and queries_left <= 0:
        cmd = [sys.executable, str(script_dir / "main2.py"), "--load-obs", "./obs"]
        mode = "load-obs"
    else:
        cmd = [sys.executable, str(script_dir / "main2.py"), "--save-obs", "./obs"]
        mode = "save-obs"

    print(f"[{now}] Running pipeline for round {round_number} ...")
    print(f"[{now}] Mode={mode} | queries_left={queries_left} | saved_obs={have_saved_obs}")
    result = subprocess.run(cmd, cwd=script_dir)
    if result.returncode != 0:
        print(f"[{now}] Pipeline failed with code {result.returncode}")
        return result.returncode

    _save_state(round_id)
    print(f"[{now}] Round {round_number} completed and recorded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
