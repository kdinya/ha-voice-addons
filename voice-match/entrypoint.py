#!/usr/bin/env python3
"""Entrypoint for the autonomous Voice Match Home Assistant add-on.

Reads options from /data/options.json, starts the Ingress web UI in background,
then hands off to the main wyoming_voice_match service.
"""

import json
import os
import subprocess
import sys
import time

OPTIONS_PATH = "/data/options.json"


def load_options() -> dict:
    try:
        with open(OPTIONS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(
            f"[entrypoint] {OPTIONS_PATH} not found — running with defaults",
            file=sys.stderr,
        )
        return {}


def main() -> None:
    options = load_options()

    env = os.environ.copy()
    env["UPSTREAM_URI"] = str(options.get("upstream_uri", "tcp://homeassistant:10300"))
    env["LISTEN_URI"] = "tcp://0.0.0.0:10350"
    env["VOICEPRINTS_DIR"] = "/data/voiceprints"
    env["ENROLLMENT_DIR"] = "/data/enrollment"
    env["MODEL_DIR"] = "/data/models"
    env["HF_HOME"] = "/data/hf_cache"
    env["VERIFY_THRESHOLD"] = str(options.get("verify_threshold", 0.35))
    env["EXTRACTION_THRESHOLD"] = str(options.get("extraction_threshold", 0.30))
    env["MAX_VERIFY_SECONDS"] = str(options.get("max_verify_seconds", 5.0))
    env["VERIFY_WINDOW_SECONDS"] = str(options.get("verify_window_seconds", 3.0))
    env["VERIFY_STEP_SECONDS"] = str(options.get("verify_step_seconds", 1.5))
    env["STT_LANGUAGES"] = str(options.get("stt_languages", "uk,ru"))
    env["TAG_SPEAKER"] = "true" if options.get("tag_speaker", False) else "false"
    env["REQUIRE_SPEAKER_MATCH"] = (
        "true" if options.get("require_speaker_match", True) else "false"
    )
    env["SAVE_REJECTED"] = "true" if options.get("save_rejected", False) else "false"
    env["LOG_LEVEL"] = str(options.get("log_level", "INFO"))
    env["DEVICE"] = "cpu"
    env["PYTHONPATH"] = "/app"

    # Silence / fast-path controls (2.0.9)
    env["SILENCE_THRESHOLD_ENABLED"] = (
        "true" if options.get("silence_threshold_enabled", True) else "false"
    )
    env["SILENCE_THRESHOLD"] = str(options.get("silence_threshold", 180))
    env["SILENCE_TIMEOUT_ENABLED"] = (
        "true" if options.get("silence_timeout_enabled", True) else "false"
    )
    env["SILENCE_TIMEOUT"] = str(options.get("silence_timeout", 2.0))
    env["MIN_SPEECH_DURATION_ENABLED"] = (
        "true" if options.get("min_speech_duration_enabled", True) else "false"
    )
    env["MIN_SPEECH_DURATION"] = str(options.get("min_speech_duration", 1.0))

    for d in ("/data/voiceprints", "/data/enrollment", "/data/models", "/data/hf_cache", "/data/rejections"):
        os.makedirs(d, exist_ok=True)

    print(
        f"[entrypoint] Starting Voice Match (autonomous) "
        f"(upstream={env['UPSTREAM_URI']}, languages={env['STT_LANGUAGES']})",
        file=sys.stderr,
    )
    print(
        f"[entrypoint] Silence controls: threshold={env['SILENCE_THRESHOLD']} "
        f"(on={env['SILENCE_THRESHOLD_ENABLED']}), "
        f"timeout={env['SILENCE_TIMEOUT']}s (on={env['SILENCE_TIMEOUT_ENABLED']}), "
        f"min_speech={env['MIN_SPEECH_DURATION']}s (on={env['MIN_SPEECH_DURATION_ENABLED']})",
        file=sys.stderr,
    )

    webui = subprocess.Popen(
        [sys.executable, "/webui.py"],
        env=env,
        stdout=sys.stderr,
        stderr=sys.stderr,
    )
    time.sleep(0.5)

    if webui.poll() is not None:
        print("[entrypoint] WARNING: web UI failed to start", file=sys.stderr)
    else:
        print("[entrypoint] Web UI (Ingress) listening on :8099", file=sys.stderr)

    os.execvpe("python", ["python", "-m", "wyoming_voice_match"], env)


if __name__ == "__main__":
    main()
