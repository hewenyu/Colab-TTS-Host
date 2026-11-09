# TTS reference-prefix regression — 2026-11-09

A user reported that generated speech began with the last words of their reference recording. The studio POSTs a complete text, but the adapter had wrapped it in a generator and selected upstream `inference_bistream`. This differs from audio streaming: full text can use the regular LLM decoder while audio still arrives incrementally.

## Real T4 reproduction

Compared the same private reference, target and random seed against the pinned CosyVoice3 model. Only aggregate results are recorded here; no personal recording, reference transcript, generated private audio, voice identifier or key is committed.

| Input path | Recognized target start | Prefix | Target-only match |
| --- | --- | --- | --- |
| Generator split into text pieces | Offset 4 | Matches reference suffix | No |
| Generator yielding the complete target | Offset 4 | Matches reference suffix | No |
| Complete string, audio `stream=True` | Offset 0 | None | Yes |

Re-recognition of the reference matched the supplied transcript after punctuation normalization. Merely changing generator chunk size did not fix the issue. The corrected production adapter was then run separately: 3 audio chunks, recognized target at offset 0, exact normalized target match. This is a regression check on this recording, not a guarantee of perfect pronunciation on every input.

## Scope

- HTTP TTS (both PCM streaming and complete WAV responses) and committed translation sentences select complete-text decoding.
- WebSocket TTS with genuinely incremental `text.delta` keeps native bistream behavior. The pinned upstream decoder's prompt-prefix problem can still occur on that path; this change does not claim to fix it universally.
- No arbitrary leading-audio trimming and no change to user reference files.
- Cold first audio in the corrected adapter check was 50.93 seconds. The already-loaded direct comparison produced first audio at 3.82 seconds. These different conditions are not a speedup benchmark. ONNX Runtime currently falls back to CPU for the speech tokenizer; this PR does not change CUDA dependencies.

## Mode-switch regression

A cleanly stopped inference server can leave HTTP sockets in TIME_WAIT. The startup port probe treated these as an occupied server and prevented immediate switching to training mode. Probe with SO_REUSEADDR, still rejecting an active listener. A real TCP regression test covers both cases; the idle training worker/API lifecycle test confirms cleanup.

Validation: 25 backend tests passed, followed by 16 targeted tests after explicit routing assertions were added; the browser end-to-end workflow also passed. Training mode was enabled on the T4 runtime with existing data/key/tunnel retained; no training job has run yet.
