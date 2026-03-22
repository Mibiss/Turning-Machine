#!/usr/bin/env bash
set -euo pipefail

if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "Error: Set GEMINI_API_KEY first"
    echo "  export GEMINI_API_KEY=AIza..."
    exit 1
fi

echo "==> Building..."
./gradlew shadowJar -q

echo "==> Starting server..."
java -jar build/libs/tripletex-agent.jar &
SERVER_PID=$!

sleep 2

echo "==> Starting ngrok tunnel..."
echo "    Submit the HTTPS URL below at https://app.ainm.no/submit/tripletex"
echo ""
ngrok http 8080

kill $SERVER_PID 2>/dev/null
