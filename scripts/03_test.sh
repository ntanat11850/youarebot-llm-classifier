#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:6872}"

echo "Testing readiness:"
curl -fsS "$BASE_URL/ready"
echo
echo

echo "Testing /predict:"
curl -fsS -X POST "$BASE_URL/predict" \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello"}'
echo
