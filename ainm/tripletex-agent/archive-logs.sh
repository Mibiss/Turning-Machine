#!/usr/bin/env bash
# Archive current tripletex-log.txt with scores and clear it.
# Usage: ./archive-logs.sh "4.5/8, 10/10, 8/8"
#        ./archive-logs.sh   (no scores, just timestamp)
set -euo pipefail

LOG=~/Desktop/tripletex-log.txt
ARCHIVE_DIR=~/Desktop/logs-of-tasks-runs

mkdir -p "$ARCHIVE_DIR"

if [ ! -f "$LOG" ] || [ ! -s "$LOG" ]; then
    echo "No log data to archive."
    exit 0
fi

TIMESTAMP=$(date +"%Y-%m-%d_%H-%M")
SCORES="${1:-}"

if [ -n "$SCORES" ]; then
    # Sanitize scores for filename: replace / with of, spaces with _
    SAFE_SCORES=$(echo "$SCORES" | tr '/' '-' | tr ' ' '_' | tr ',' '_')
    FILENAME="run_${TIMESTAMP}__${SAFE_SCORES}.txt"
else
    FILENAME="run_${TIMESTAMP}.txt"
fi

cp "$LOG" "$ARCHIVE_DIR/$FILENAME"
> "$LOG"

echo "Archived to: $ARCHIVE_DIR/$FILENAME"
echo "Log cleared."
