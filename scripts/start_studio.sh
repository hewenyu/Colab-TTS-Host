#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-gpu}"
case "$mode" in gpu|cpu|train) ;; *) echo 'Usage: start_studio.sh gpu|cpu|train' >&2; exit 2 ;; esac
if [ ! -f src/tts_host/web/index.html ]; then
  npm ci --prefix frontend
  npm run build --prefix frontend
fi
.venv/bin/python scripts/configure.py
set -a
source .env
set +a
if [ "$mode" != cpu ]; then default_config=config/gpu.yaml; else default_config=config/server.yaml; fi
export SPEECH_CONFIG="${SPEECH_CONFIG:-$default_config}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-2}" MKL_NUM_THREADS="${MKL_NUM_THREADS:-2}"
export TOKENIZERS_PARALLELISM=false
exec .venv/bin/python scripts/run_studio.py --mode "$mode"
