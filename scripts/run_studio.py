"""Run inference, or a management UI + exclusive single-GPU training worker.

The caller loads .env. Training mode never starts inference models. Stop the old
studio process before changing mode; port conflicts fail before a worker starts.
"""
import argparse
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time

import yaml


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['gpu', 'cpu', 'train'], default='gpu')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be between 1 and 65535')
    config = Path(os.environ.get('SPEECH_CONFIG', 'config/server.yaml' if args.mode == 'cpu' else 'config/gpu.yaml'))
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', args.port))
    uvicorn = [sys.executable, '-m', 'uvicorn', 'tts_host.app:create_app', '--factory', '--host', '127.0.0.1', '--port', str(args.port), '--workers', '1', '--ws-max-size', '65536', '--ws-max-queue', '16']
    if args.mode != 'train':
        os.environ['SPEECH_CONFIG'] = str(config)
        os.execv(sys.executable, uvicorn)
    cfg = yaml.safe_load(config.read_text())
    if cfg.get('tts', {}).get('backend') != 'cosyvoice3':
        raise SystemExit('Training mode requires a CosyVoice3 GPU configuration')
    cfg.setdefault('training', {})['enabled'] = True
    processes = []

    def stop(signum, frame):
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    with tempfile.TemporaryDirectory(prefix='speech-training-config-') as temporary:
        worker_config = Path(temporary) / 'worker.yaml'
        worker_config.write_text(yaml.safe_dump(cfg))
        for service in ('asr', 'tts', 'translation'):
            cfg.setdefault(service, {})['backend'] = 'disabled'
        api_config = Path(temporary) / 'api.yaml'
        api_config.write_text(yaml.safe_dump(cfg))
        try:
            api = subprocess.Popen(uvicorn, env={**os.environ, 'SPEECH_CONFIG': str(api_config)}, start_new_session=True)
            processes.append(api)
            # Wait for this API to start before letting a worker claim persistent jobs.
            import urllib.request
            local_http = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for _ in range(100):
                if api.poll() is not None:
                    raise RuntimeError('Management API failed to start')
                try:
                    with local_http.open(f'http://127.0.0.1:{args.port}/health/live', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(.1)
            else:
                raise RuntimeError('Management API startup timed out')
            worker = subprocess.Popen([sys.executable, '-m', 'tts_host.training'], env={**os.environ, 'SPEECH_CONFIG': str(worker_config)}, start_new_session=True)
            processes.append(worker)
            print(f'Training mode: management UI on http://127.0.0.1:{args.port}; inference disabled.', flush=True)
            while all(p.poll() is None for p in processes):
                time.sleep(.5)
            raise RuntimeError('API or worker exited; stopping the other process')
        finally:
            for process in processes:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
            for process in processes:
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()


if __name__ == '__main__':
    main()
