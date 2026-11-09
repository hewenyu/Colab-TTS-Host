#!/usr/bin/env bash
set -euo pipefail
if [ "${DOWNLOAD_MODELS:-1}" = 1 ] && [ ! -f models/revisions.json ]; then
  python scripts/download_models.py
fi
exec "$@"
