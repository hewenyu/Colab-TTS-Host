#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mode="${1:-cpu}"
case "$mode" in cpu) torch_index=https://download.pytorch.org/whl/cpu ;; gpu) torch_index=https://download.pytorch.org/whl/cu121 ;; *) echo 'Usage: bootstrap_colab.sh cpu|gpu' >&2; exit 2 ;; esac
python -m pip install 'uv>=0.8,<1'
uv python install 3.10
uv venv --python 3.10 .venv
uv pip install --python .venv/bin/python torch==2.3.1 torchaudio==2.3.1 --index-url "$torch_index"
uv pip install --python .venv/bin/python --build-constraint build-constraints.txt -r requirements-models.txt
uv pip install --python .venv/bin/python -e '.[test]'
mkdir -p vendor
if [ ! -d vendor/CosyVoice/.git ]; then
  git clone https://github.com/QwenAudio/CosyVoice.git vendor/CosyVoice
fi
git -C vendor/CosyVoice checkout 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git -C vendor/CosyVoice submodule update --init --recursive
.venv/bin/python scripts/download_models.py
echo 'Environment ready. Run tests or a localhost-only model smoke test; no public tunnel is needed.'
