#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/configure.py
case "${1:-cpu}" in
  cpu) docker compose up -d --build api ;;
  gpu) docker compose -f compose.yaml -f compose.gpu.yaml up -d --build api ;;
  *) echo 'Usage: bash scripts/deploy.sh cpu|gpu' >&2; exit 2 ;;
esac
