#!/usr/bin/env python3
"""Ingress web UI for Wyoming Voice Match — upload samples & run enrollment."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="/static", static_url_path="/static")
app.secret_key = os.environ.get("FLASK_SECRET", "wyoming-voice-match-ingress")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

ENROLLMENT_DIR = Path(os.environ.get("ENROLLMENT_DIR", "/data/enrollment"))
VOICEPRINTS_DIR = Path(os.environ.get("VOICEPRINTS_DIR", "/data/voiceprints"))
MODEL_DIR = os.environ.get("MODEL_DIR", "/data/models")
DEVICE = os.environ.get("DEVICE", "cpu")
TEMPLATE_DIR = Path("/templates")

ALLOWED_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3"}
SPEAKER_RE = re.compile(r"^[a-z0-9_\-]{1,32}$")


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def list_speakers_enrollment():
    result = []
    if not ENROLLMENT_DIR.exists():
        return result
    for d in sorted(ENROLLMENT_DIR.iterdir()):
        if d.is_dir():
            files = [
                f.name
                for f in d.iterdir()
                if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
            ]
            result.append({"name": d.name, "files": files, "count": len(files)})
    return result


def list_voiceprints():
    if not VOICEPRINTS_DIR.exists():
        return []
    return sorted(f.stem for f in VOICEPRINTS_DIR.glob("*.npy"))


@app.route("/")
def index():
    return (TEMPLATE_DIR / "index.html").read_text(encoding="utf-8")


@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("/static", filename)


@app.route("/upload", methods=["POST"])
def upload():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({
            "ok": False,
            "message": "Невірне ім'я спікера. Тільки a-z, 0-9, _ і - (1–32).",
        }), 400

    files = request.files.getlist("files")
    if not files or all(not f.filename for f in files):
        return jsonify({"ok": False, "message": "Файли не вибрані."}), 400

    target = ENROLLMENT_DIR / speaker
    target.mkdir(parents=True, exist_ok=True)

    saved = 0
    for f in files:
        if f and f.filename and allowed_file(f.filename):
            name = re.sub(r"[^\w.\-]", "_", Path(f.filename).name)
            dest = target / name
            if dest.exists():
                stem, suf = dest.stem, dest.suffix
                i = 1
                while dest.exists():
                    dest = target / f"{stem}_{i}{suf}"
                    i += 1
            f.save(str(dest))
            saved += 1

    if saved:
        return jsonify({
            "ok": True,
            "message": f"Завантажено {saved} файл(ів) для «{speaker}».",
        })
    return jsonify({
        "ok": False,
        "message": "Жоден файл не підійшов (.wav .flac .ogg .mp3).",
    }), 400


@app.route("/enroll", methods=["POST"])
def enroll():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "log": "Невірне ім'я спікера."}), 400

    speaker_dir = ENROLLMENT_DIR / speaker
    if not speaker_dir.exists() or not any(speaker_dir.iterdir()):
        return jsonify({
            "ok": False,
            "log": f"Немає файлів у /data/enrollment/{speaker}/",
        }), 400

    cmd = [
        sys.executable, "-m", "scripts.enroll",
        "--speaker", speaker,
        "--enrollment-dir", str(ENROLLMENT_DIR),
        "--voiceprints-dir", str(VOICEPRINTS_DIR),
        "--model-dir", MODEL_DIR,
        "--device", DEVICE,
    ]

    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300, env=os.environ.copy(),
        )
        log = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
        if ok:
            log += (
                "\n\n✅ Voiceprint збережено. "
                "Перезапустіть аддон, щоб сервіс підхопив новий голос."
            )
        return jsonify({"ok": ok, "log": log, "returncode": proc.returncode})
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "log": "Таймаут (5 хв)."}), 500
    except Exception as e:
        return jsonify({"ok": False, "log": str(e)}), 500


@app.route("/delete_samples", methods=["POST"])
def delete_samples():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False}), 400
    path = ENROLLMENT_DIR / speaker
    if path.exists():
        shutil.rmtree(path)
    return jsonify({"ok": True})


@app.route("/delete_voiceprint", methods=["POST"])
def delete_voiceprint():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False}), 400
    vp = VOICEPRINTS_DIR / f"{speaker}.npy"
    if vp.exists():
        vp.unlink()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify({
        "enrollment": list_speakers_enrollment(),
        "voiceprints": list_voiceprints(),
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False, threaded=True)
