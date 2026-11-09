FROM node:22-bookworm-slim AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.10-slim-bookworm AS runtime
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG COSYVOICE_REV=074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/app/cache/huggingface \
    MODELSCOPE_CACHE=/app/cache/modelscope OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 \
    TOKENIZERS_PARALLELISM=false MPLBACKEND=Agg
RUN apt-get update && apt-get install -y --no-install-recommends \
    git build-essential libsndfile1 sox ffmpeg libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install 'uv>=0.8,<1'
WORKDIR /app
COPY requirements-models.txt build-constraints.txt ./
RUN uv pip install --system torch==2.3.1 torchaudio==2.3.1 --index-url ${TORCH_INDEX_URL} \
    && uv pip install --system --build-constraint build-constraints.txt -r requirements-models.txt
RUN git clone https://github.com/QwenAudio/CosyVoice.git /opt/CosyVoice \
    && git -C /opt/CosyVoice checkout ${COSYVOICE_REV} \
    && git -C /opt/CosyVoice submodule update --init --recursive \
    && mkdir -p /app/vendor && ln -s /opt/CosyVoice /app/vendor/CosyVoice
COPY pyproject.toml ./
COPY src ./src
COPY --from=frontend /src/tts_host/web ./src/tts_host/web
RUN uv pip install --system .
COPY scripts ./scripts
COPY config ./config
COPY models.lock.json ./
RUN useradd -m -u 10001 speech && mkdir -p /app/data /app/models /app/cache \
    && chown -R speech:speech /app/data /app/models /app/cache
USER speech
EXPOSE 8000
HEALTHCHECK --interval=30s --start-period=600s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)"
ENTRYPOINT ["bash", "scripts/entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "tts_host.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-max-size", "65536", "--ws-max-queue", "16"]

FROM runtime AS training
USER root
ENV DS_BUILD_OPS=0
RUN uv pip install --system deepspeed==0.15.1
USER speech
CMD ["speech-worker"]
