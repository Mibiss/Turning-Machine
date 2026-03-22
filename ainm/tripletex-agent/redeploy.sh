#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Archive logs before rebuilding
SCORES="${1:-}"
./archive-logs.sh "$SCORES"

# Build
echo "==> Building..."
./gradlew shadowJar -q

# Kill everything
echo "==> Killing old processes..."
pkill -9 -f "java.*tripletex-agent" 2>/dev/null || true
pkill -9 -f ngrok 2>/dev/null || true
sleep 1

# Start server
echo "==> Starting server..."
java -jar build/libs/tripletex-agent.jar &
sleep 2

# Start tunnel
echo "==> Starting ngrok tunnel..."
ngrok http 8080
