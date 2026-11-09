"""Upload only a completed job's weights + manifest to a PRIVATE Hugging Face repo.

HF_TOKEN comes from the environment or the user's own local huggingface login.
No raw reference recordings or training transcripts are uploaded.
"""
import argparse
import json
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

parser = argparse.ArgumentParser()
parser.add_argument('--job-dir', required=True, type=Path)
parser.add_argument('--repo', required=True, help='your-user/your-model')
args = parser.parse_args()
model = args.job_dir.resolve() / 'model'
if not (model / 'llm.pt').is_file() or not (model / 'training-manifest.json').is_file():
    raise SystemExit('This job has no exported model. Finish training first.')
api = HfApi()
api.create_repo(args.repo, repo_type='model', private=True, exist_ok=True)
if not api.model_info(args.repo).private:
    raise SystemExit('Refusing to upload voice weights into an existing public repository')
manifest = json.loads((model / 'training-manifest.json').read_text())
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    # symlink avoids duplicating multi-GB weights locally; upload reads the resolved bytes.
    (root / 'llm.pt').symlink_to((model / 'llm.pt').resolve())
    (root / 'training-manifest.json').write_text(json.dumps(manifest, indent=2))
    (root / 'README.md').write_text('---\nlicense: apache-2.0\nbase_model: FunAudioLLM/Fun-CosyVoice3-0.5B-2512\n---\n\n'
        '# Personal voice LLM checkpoint\n\nOverlay `llm.pt` on the exact base revision recorded in training-manifest.json. '
        'Reference audio is supplied separately to the server. This repository contains no raw recordings.\n')
    result = api.upload_folder(repo_id=args.repo, folder_path=root, commit_message='Upload completed voice training checkpoint')
    print(result.commit_url)
