"""Real child-process lifecycle with an idle worker; no GPU or model fixture."""
import fcntl
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx


def test_training_mode_disables_inference_and_cleans_up(tmp_path):
    config = tmp_path / 'gpu.yaml'
    config.write_text('tts:\n  backend: cosyvoice3\n  device: cuda\ntraining:\n  enabled: false\n')
    original = config.read_text()
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    key = 'launcher-test-key-not-for-production'
    env = {**os.environ, 'SPEECH_CONFIG': str(config), 'SPEECH_DATA_DIR': str(tmp_path / 'data'),
           'SPEECH_API_KEYS': json.dumps({'test': key})}
    root = Path(__file__).resolve().parents[1]
    process = subprocess.Popen([sys.executable, str(root / 'scripts/run_studio.py'), '--mode', 'train', '--port', str(port)],
                               cwd=root, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with httpx.Client(base_url=f'http://127.0.0.1:{port}', headers={'Authorization': f'Bearer {key}'}, timeout=1, trust_env=False) as client:
            for _ in range(100):
                assert process.poll() is None
                try:
                    if client.get('/health/live').status_code == 200 and (tmp_path / 'data/worker.lock').exists():
                        break
                except httpx.TransportError:
                    pass
                time.sleep(.1)
            else:
                raise AssertionError('Training launcher did not become ready')
            assert client.get('/v1/studio/config').json()['training_enabled'] is True
            caps = client.get('/v1/capabilities').json()
            assert not any(caps[name]['enabled'] for name in ('asr', 'tts', 'translation'))
            assert config.read_text() == original
    finally:
        process.terminate()
        process.wait(timeout=20)
    with (tmp_path / 'data/worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    with socket.socket() as sock:
        assert sock.connect_ex(('127.0.0.1', port)) != 0


def test_mode_switch_reuses_time_wait_but_rejects_live_listener():
    import importlib.util
    import pytest
    launcher = Path(__file__).resolve().parents[1] / 'scripts/run_studio.py'
    spec = importlib.util.spec_from_file_location('run_studio', launcher)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
        listener.listen()
        with pytest.raises(OSError):
            module.check_port(port)
        with socket.create_connection(('127.0.0.1', port)) as client:
            accepted, _ = listener.accept()
            accepted.shutdown(socket.SHUT_WR)
            accepted.close()
            assert client.recv(1) == b''
    module.check_port(port)
