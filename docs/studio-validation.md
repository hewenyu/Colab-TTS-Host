# Voice Studio verification — 2026-11-09

## Python + React

- React 19.3.1 / Vite 8.3.7 production build completed. Assets are bundled locally, with no CDN or runtime Node server.
- Python wheel built and inspected: includes HTML, hashed JS and CSS assets.
- 22 Python tests passed, including owner-isolated sample audio/list APIs, production static asset serving, CSP and training-launcher lifecycle. Training launcher test starts a real idle worker, checks inference is disabled, then confirms both subprocesses stop.
- 3 Node audio tests passed: PCM chunk boundary handling, truncated audio rejection and WAV headers/clipping.
- Real Chromium browser workflow passed: incorrect key, connection, streamed playback, reference upload and automatic transcription, material upload/selection, training submission/cancellation/result selection, 390px responsive layout and disconnect privacy. This fixture uses synthetic audio and substitute models; it does not establish model quality or actual training success.
- Fresh visual review passed after mobile audition actions and focus-only skip-link presentation were corrected. Generated screenshots are local test artifacts, not committed data.

## Newly allocated Colab T4

A fresh Tesla T4 runtime (15,360 MiB VRAM) installed the pinned model dependencies and downloaded the pinned base models. `scripts/smoke_models.py --config config/gpu.yaml` completed successfully on the existing API implementation, before the UI branch was deployed:

| Check | Observed result |
| --- | --- |
| File ASR | Recognized upstream public reference audio |
| Streaming ASR | 4 partial results and final text |
| Translation | Returned English translation |
| TTS before input.end | First audio received while text input remained open |
| Cold TTS first chunk | 52.58 seconds |
| Warm TTS first chunk | 3.18 seconds |
| Warm TTS total / generated duration | 23.56 / 15.20 seconds |
| Warm real-time factor | 1.55 |
| Combined interpretation | Final ASR, translation and 2 audio chunks |

The reference is the public upstream test recording, not personal user audio. TTS is functionally streaming but this measurement does not meet sustained real-time generation (RTF must be ≤1). No personal voice has been trained. Deepspeed installation completed; GPU SFT memory suitability and perceptual quality still require actual dataset validation. The full Docker image has not been built in this environment; the frontend build and Python packaging have been verified separately.
