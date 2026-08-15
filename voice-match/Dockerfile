FROM ghcr.io/jxlarrea/wyoming-voice-match:cpu

# ffmpeg for webm→wav; flask for Ingress UI
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir flask werkzeug

COPY main.py /app/wyoming_voice_match/__main__.py
COPY entrypoint.py /entrypoint.py
COPY webui.py /webui.py
COPY templates/ /templates/
COPY static/ /static/

RUN mkdir -p /data/enrollment /data/voiceprints /data/models /data/hf_cache

WORKDIR /app
ENTRYPOINT ["python", "/entrypoint.py"]
