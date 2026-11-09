"""Explicit opt-in, single GPU CosyVoice3 LLM SFT worker. Never executes client commands."""
import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from .config import Settings
from .store import Store


class JobCancelled(Exception):
    pass


def prepare_dataset(store, owner, job, directory):
    samples = [store.get("sample", owner, sid) for sid in job["sample_ids"]]
    hashes = [hashlib.sha256(store.asset(s["id"]).read_bytes()).hexdigest() for s in samples]
    if len(set(hashes)) != len(hashes):
        raise ValueError("Duplicate recordings would leak between train and validation sets")
    samples.sort(key=lambda s: s["id"])
    valid_count = max(1, len(samples) // 10)
    splits = {"valid": samples[:valid_count], "train": samples[valid_count:]}
    for split, rows in splits.items():
        dest = directory / split
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "wav.scp").write_text("".join(f"{s['id']} {store.asset(s['id'])}\n" for s in rows))
        (dest / "text").write_text("".join(f"{s['id']} {' '.join(s['transcript'].split())}\n" for s in rows))
        (dest / "utt2spk").write_text("".join(f"{s['id']} speaker\n" for s in rows))
        (dest / "spk2utt").write_text("speaker " + " ".join(s["id"] for s in rows) + "\n")
        (dest / "instruct").write_text("".join(f"{s['id']} You are a helpful assistant.<|endofprompt|>\n" for s in rows))
    manifest = {"base_revision": job["base_revision"], "recipe": "cosyvoice3-llm-sft",
                "epochs": job["epochs"], "learning_rate": job["learning_rate"],
                "splits": {split: [s["id"] for s in rows] for split, rows in splits.items()}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def training_config(source, destination, epochs, learning_rate):
    # Keep HyperPyYAML tags intact; replace only documented scalar settings.
    text = source.read_text()
    changes = {r"(?m)^(    max_epoch:) \d+": rf"\g<1> {epochs}",
               r"(?m)^(        lr:) [\deE.+-]+": rf"\g<1> {learning_rate}",
               r"(?m)^(    use_spk_embedding:) False": r"\g<1> True",
               r"(?m)^(    max_frames_in_batch:) \d+": r"\g<1> 1000",
               r"(?m)^(    log_interval:) \d+": r"\g<1> 1"}
    for pattern, replacement in changes.items():
        text, count = re.subn(pattern, replacement, text)
        if count == 0:
            raise ValueError("Upstream recipe changed; update the training adapter")
    destination.write_text(text)


def run_job(settings, store, owner, job):
    source = settings.tts.source_dir.resolve()
    base = settings.tts.model_dir.resolve()
    directory = store.root / "jobs" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(source), str(source / "third_party/Matcha-TTS")])
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    log_path = directory / "training.log"

    def check():
        if store.get("job", owner, job["id"]).get("cancel_requested"):
            raise JobCancelled()
        if time.monotonic() - started > settings.training.max_seconds:
            raise TimeoutError("Training job deadline exceeded")

    def run(stage, args):
        check()
        store.update("job", owner, job["id"], stage=stage)
        with log_path.open("ab") as log:
            process = subprocess.Popen(args, cwd=source, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                while process.poll() is None:
                    check()
                    time.sleep(1)
                if process.returncode != 0:
                    raise RuntimeError(f"{stage} failed (exit {process.returncode}); see worker job log")
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()

    check()
    run("checking_gpu", [sys.executable, "-c", "import torch; assert torch.cuda.is_available(), 'SFT requires a CUDA GPU'"])
    if not (base / "llm.pt").is_file():
        raise ValueError("Base model llm.pt is missing")
    manifest = prepare_dataset(store, owner, job, directory)
    config = directory / "train.yaml"
    training_config(source / "examples/libritts/cosyvoice3/conf/cosyvoice3.yaml", config,
                    job["epochs"], job["learning_rate"])
    for split in ("train", "valid"):
        dest = directory / split
        (dest / "parquet").mkdir(exist_ok=True)
        run(f"{split}_embeddings", [sys.executable, "tools/extract_embedding.py", "--dir", str(dest),
                                    "--onnx_path", str(base / "campplus.onnx")])
        run(f"{split}_tokens", [sys.executable, "tools/extract_speech_token.py", "--dir", str(dest),
                                "--onnx_path", str(base / "speech_tokenizer_v3.onnx")])
        run(f"{split}_parquet", [sys.executable, "tools/make_parquet_list.py", "--num_processes", "1",
                                 "--src_dir", str(dest), "--des_dir", str(dest / "parquet")])
    output = directory / "checkpoints"
    run("training", [sys.executable, "-m", "torch.distributed.run", "--standalone", "--nproc_per_node=1",
                     "cosyvoice/bin/train.py", "--train_engine", "torch_ddp", "--model", "llm",
                     "--config", str(config), "--train_data", str(directory / "train/parquet/data.list"),
                     "--cv_data", str(directory / "valid/parquet/data.list"),
                     "--qwen_pretrain_path", str(base / "CosyVoice-BlankEN"), "--onnx_path", str(base),
                     "--checkpoint", str(base / "llm.pt"), "--model_dir", str(output),
                     "--tensorboard_dir", str(directory / "tensorboard"),
                     "--num_workers", "1", "--prefetch", "2", "--use_amp"])
    checkpoints = list(output.glob("epoch_*_whole.pt"))
    if not checkpoints:
        raise RuntimeError("Training exited without an epoch checkpoint")
    checkpoint = max(checkpoints, key=lambda path: int(path.name.split("_")[1]))
    # Inference gets a versioned directory. Base model files are never modified.
    model_dir = directory / "model"
    model_dir.mkdir(exist_ok=True)
    for path in base.iterdir():
        if path.name != "llm.pt":
            (model_dir / path.name).symlink_to(path, target_is_directory=path.is_dir())
    import torch
    weights = torch.load(checkpoint, map_location="cpu", weights_only=True)
    # Training checkpoints carry epoch/step metadata; strict inference loading rejects these keys.
    weights.pop("epoch", None)
    weights.pop("step", None)
    torch.save(weights, model_dir / "llm.pt")
    del weights
    manifest["checkpoint"] = checkpoint.name
    manifest["validation"] = "held-out loss in checkpoint YAML; perceptual evaluation required before production"
    (model_dir / "training-manifest.json").write_text(json.dumps(manifest, indent=2))
    original = store.get("voice", owner, job["voice_id"])
    new_voice = store.create("voice", owner, {k: v for k, v in {
        **original, "kind": "finetuned", "parent_voice_id": original["id"],
        "version": original["version"] + 1, "model_dir": str(model_dir), "training_job_id": job["id"],
    }.items() if k not in ("id", "created_at")})
    store.update("job", owner, job["id"], status="succeeded", stage="complete",
                 output_voice_id=new_voice["id"], finished_at=time.time())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Handle one pending job then exit")
    args = parser.parse_args()
    settings = Settings.load()
    if not settings.training.enabled or settings.tts.backend != "cosyvoice3":
        raise SystemExit("Enable training and configure cosyvoice3 before starting the worker")
    store = Store(settings.data_dir)
    lock = (store.root / "worker.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    def terminate(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminate)
    # Only one worker per data volume. Do not silently mark abandoned work as successful.
    with store.db() as db:
        rows = db.execute("SELECT owner,payload FROM records WHERE kind='job'").fetchall()
    for row in rows:
        job = json.loads(row["payload"])
        if job["status"] == "running":
            store.update("job", row["owner"], job["id"], status="interrupted", stage="worker_restarted")
    while True:
        claimed = store.claim_job()
        if claimed:
            owner, job = claimed
            try:
                run_job(settings, store, owner, job)
            except JobCancelled:
                store.update("job", owner, job["id"], status="cancelled", finished_at=time.time())
            except Exception as exc:
                store.update("job", owner, job["id"], status="failed", error=str(exc)[:500], finished_at=time.time())
        if args.once:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
