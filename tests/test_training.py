import numpy as np
import pytest

from tts_host.audio import wav_bytes
from tts_host.store import Store
from tts_host.training import prepare_dataset, training_config


def test_worker_claim_is_exclusive_and_data_persists(tmp_path):
    store = Store(tmp_path)
    job = store.create("job", "alice", {"status": "queued"})
    assert store.claim_job()[1]["id"] == job["id"]
    assert Store(tmp_path).claim_job() is None
    assert Store(tmp_path).get("job", "alice", job["id"])["status"] == "running"


def test_dataset_rejects_duplicate_audio(tmp_path):
    store = Store(tmp_path)
    ids = []
    for _ in range(5):
        sample = store.create("sample", "alice", {"transcript": "hello"})
        path = store.asset(sample["id"])
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(wav_bytes(np.zeros(16000), 16000))
        ids.append(sample["id"])
    with pytest.raises(ValueError, match="Duplicate"):
        prepare_dataset(store, "alice", {"sample_ids": ids}, tmp_path / "job")


def test_asset_paths_cannot_escape(tmp_path):
    with pytest.raises(ValueError):
        Store(tmp_path).asset("../../secret")
