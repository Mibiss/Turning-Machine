#!/bin/zsh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOKEN_FILE="$HOME/.astar_token"
LOG_FILE="$PROJECT_DIR/auto_round_runner.log"

if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "Missing token file: $TOKEN_FILE" >> "$LOG_FILE"
  exit 1
fi

export ASTAR_TOKEN="$(<"$TOKEN_FILE")"
cd "$PROJECT_DIR"
/opt/anaconda3/bin/python3 "$PROJECT_DIR/auto_round_runner.py" >> "$LOG_FILE" 2>&1
