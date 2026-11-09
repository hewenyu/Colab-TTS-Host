# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Users
The owner of a self-hosted speech service, uploading personal recordings and operating voice cloning and training through a browser.

## Product Purpose
Turn the existing configurable ASR, translation and TTS server into a usable voice workspace: upload recordings, supply transcripts, train, select a resulting voice, synthesize and download speech.

## Operating Context
FastAPI serves the interface and API on the same localhost port. The user manages Cloudflare Tunnel. Colab is used for development and GPU experiments; Docker is the intended independent deployment package.

## Capabilities and Constraints
Reference audio produces zero-shot voices. Fine-tuning requires multiple labelled clips and an independently running worker. Training readiness must not be fabricated. Recordings stay outside Git. API keys and owner isolation remain enforced. Current inference adapters and limitations are documented in README.md.

## Stack
Python/FastAPI backend and React frontend, explicitly requested by the owner. Vite builds self-hosted assets packaged in the Python wheel and Docker image. Node is a build-time dependency, with no additional Node server in deployment.

## Evidence on Hand
docs/validation.md and docs/t4-smoke.json record real T4 inference. No personal recordings or successful personal fine-tuning run have been provided.

## Product Principles
- Show real job stages and explicit unavailable states.
- Keep upload, transcript correction, training and audition connected.
- Never put recordings, API keys or training outputs in source control.
- Make the selected voice and output unambiguous.
