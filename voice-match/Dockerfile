FROM python:3.11-slim

LABEL maintainer="HA Voice Add-ons"
LABEL description="Voice Match — speaker verification for Home Assistant (autonomous)"

WORKDIR /app

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libsndfile1 \
        ffmpeg \
        curl \
        && rm -rf /var/lib/apt/lists/*

# PyTorch CPU (amd64) / default torch for aarch64
ARG TARGETARCH
RUN if [ "$TARGETARCH" = "amd64" ]; then \
        pip install --no-cache-dir torch==2.4.1+cpu torchaudio==2.4.1+cpu \
            --index-url https://download.pytorch.org/whl/cpu; \
    else \
        pip install --no-cache-dir torch==2.4.1 torchaudio==2.4.1; \
    fi

# Python packages (pinned where practical)
RUN pip install --no-cache-dir \
    wyoming==1.8.0 \
    "speechbrain>=1.0.0,<1.1" \
    "scipy>=1.11.0,<1.15" \
    "numpy>=1.24.0,<2.1" \
    "soundfile>=0.12.0" \
    "requests>=2.28.0" \
    "huggingface_hub>=0.20.0,<0.27.0" \
    flask \
    werkzeug

# Application code
COPY wyoming_voice_match/ /app/wyoming_voice_match/
COPY scripts/ /app/scripts/
COPY entrypoint.py /entrypoint.py
COPY webui.py /webui.py
COPY templates/ /templates/
COPY static/ /static/

RUN mkdir -p /data/enrollment /data/voiceprints /data/models /data/hf_cache /data/rejections

ENV PYTHONPATH=/app
ENV HF_HOME=/data/hf_cache
ENV DEVICE=cpu

WORKDIR /app
EXPOSE 10350 8099

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
  CMD curl -sf http://127.0.0.1:8099/ || exit 1

ENTRYPOINT ["python", "/entrypoint.py"]
