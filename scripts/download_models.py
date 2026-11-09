"""Fetch explicit pinned model artifacts, keeping secrets in the environment/Hub credential store."""
import argparse
import json
from pathlib import Path

from huggingface_hub import snapshot_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", default="models")
    parser.add_argument("--lock", default="models.lock.json")
    args = parser.parse_args()
    root = Path(args.directory)
    lock = json.loads(Path(args.lock).read_text())
    for name, folder in (("tts", "cosyvoice3"), ("translation", "translation")):
        spec = lock[name]
        snapshot_download(spec["repo"], revision=spec["revision"], local_dir=root / folder,
                          ignore_patterns=["*.zip", "*.engine", "*.plan", "*.batch.onnx",
                                           "flow.decoder.*", "llm.rl.pt"], max_workers=4)
    spec = lock["asr"]
    if spec.get("hub") == "modelscope":
        from modelscope import snapshot_download as ms_download
        ms_download(spec["repo"], revision=spec["revision"], local_dir=str(root / "asr"))
    else:
        snapshot_download(spec["repo"], revision=spec["revision"], local_dir=root / "asr", max_workers=4)
    (root / "revisions.json").write_text(json.dumps(lock, indent=2))
    print("Pinned models are ready in", root)


if __name__ == "__main__":
    main()
