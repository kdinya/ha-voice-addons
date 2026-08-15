FROM ghcr.io/jxlarrea/wyoming-voice-match:cpu

# System deps for audio + web UI
RUN pip install --no-cache-dir flask werkzeug

# Our language fix + entrypoint + web UI
COPY main.py /app/wyoming_voice_match/__main__.py
COPY entrypoint.py /entrypoint.py
COPY webui.py /webui.py
COPY templates/ /templates/
COPY static/ /static/

# Ensure enrollment/voiceprints dirs exist at runtime (Supervisor maps /data)
RUN mkdir -p /data/enrollment /data/voiceprints /data/models /data/hf_cache

WORKDIR /app
ENTRYPOINT ["python", "/entrypoint.py"]
