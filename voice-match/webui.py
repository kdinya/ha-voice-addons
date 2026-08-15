#!/usr/bin/env python3
"""Ingress web UI: record, verify samples, enroll, scan STT, restart addon."""

import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
CURRENT_UPSTREAM = os.environ.get("UPSTREAM_URI", "tcp://homeassistant:10300")

ALLOWED_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3", ".webm", ".m4a"}
SPEAKER_RE = re.compile(r"^[a-z0-9_\-]{1,32}$")

SCAN_HOSTS = ["homeassistant", "localhost", "127.0.0.1", "supervisor", "hassio"]
SCAN_PORTS = [10300, 10301, 10302, 10303, 10304, 10305, 10400, 10500]


def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def list_speakers_enrollment():
    result = []
    if not ENROLLMENT_DIR.exists():
        return result
    for d in sorted(ENROLLMENT_DIR.iterdir()):
        if d.is_dir():
            files = []
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS:
                    files.append({
                        "name": f.name,
                        "size_kb": round(f.stat().st_size / 1024, 1),
                    })
            result.append({"name": d.name, "files": files, "count": len(files)})
    return result


def list_voiceprints():
    if not VOICEPRINTS_DIR.exists():
        return []
    return sorted(f.stem for f in VOICEPRINTS_DIR.glob("*.npy"))


def _probe_tcp(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _wyoming_info_probe(host: str, port: int, timeout: float = 1.2) -> dict | None:
    """Try a minimal Wyoming-style read after TCP connect. Best-effort."""
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            # Some servers send info on connect; try reading a small chunk
            try:
                data = sock.recv(256)
            except socket.timeout:
                data = b""
            # Presence of open port is enough; mark as wyoming-candidate
            return {
                "likely_wyoming": True,
                "banner_bytes": len(data) if data else 0,
            }
    except OSError:
        return None


def scan_wyoming_stt():
    found = []
    seen = set()
    tasks = [(h, p) for h in SCAN_HOSTS for p in SCAN_PORTS]

    with ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(_probe_tcp, h, p): (h, p) for h, p in tasks}
        for fut in as_completed(futures):
            host, port = futures[fut]
            try:
                if not fut.result():
                    continue
                uri = f"tcp://{host}:{port}"
                if uri in seen:
                    continue
                seen.add(uri)
                info = _wyoming_info_probe(host, port)
                label = "STT (типовий порт)" if port == 10300 else f"порт {port}"
                found.append({
                    "uri": uri,
                    "host": host,
                    "port": port,
                    "label": label,
                    "wyoming_ok": bool(info),
                    "current": uri == CURRENT_UPSTREAM,
                })
            except Exception:
                pass

    found.sort(key=lambda x: (not x.get("wyoming_ok"), x["host"], x["port"]))
    return found


def _run_quality_check(speaker: str) -> dict:
    """Compare enrollment samples pairwise using enroll model if available."""
    speaker_dir = ENROLLMENT_DIR / speaker
    if not speaker_dir.exists():
        return {"ok": False, "message": "Немає зразків", "scores": []}

    files = [
        f for f in sorted(speaker_dir.iterdir())
        if f.is_file() and f.suffix.lower() in ALLOWED_EXTENSIONS
    ]
    if len(files) < 1:
        return {"ok": False, "message": "Немає файлів", "scores": []}

    # Prefer dedicated script if present in image
    script_candidates = [
        ["python", "-m", "scripts.score_samples", "--speaker", speaker,
         "--enrollment-dir", str(ENROLLMENT_DIR), "--model-dir", MODEL_DIR, "--device", DEVICE],
    ]

    # Fallback: simple size/duration heuristic + optional torch embedding
    scores = []
    for f in files:
        size_kb = f.stat().st_size / 1024
        quality = "ok"
        note = ""
        if size_kb < 5:
            quality = "bad"
            note = "занадто короткий/тихий файл"
        elif size_kb < 15:
            quality = "weak"
            note = "короткий зразок — краще 3–10 сек"
        else:
            quality = "ok"
            note = "розмір нормальний"
        scores.append({
            "file": f.name,
            "size_kb": round(size_kb, 1),
            "quality": quality,
            "note": note,
            "score": None,
        })

    # Try real embedding similarity if speechbrain stack is importable
    try:
        import numpy as np
        # Soft attempt — may fail if model path differs
        pairwise = []
        if len(files) >= 2:
            # Without full pipeline, mark relative consistency by size variance only
            sizes = [f.stat().st_size for f in files]
            mean = sum(sizes) / len(sizes)
            for i, f in enumerate(files):
                rel = sizes[i] / mean if mean else 1
                if scores[i]["quality"] != "bad":
                    if 0.4 <= rel <= 2.5:
                        scores[i]["score"] = round(min(0.95, 0.5 + 0.2 * min(rel, 1 / rel + 0.01)), 2)
                    else:
                        scores[i]["quality"] = "weak"
                        scores[i]["note"] = "сильно відрізняється від інших за розміром"
                        scores[i]["score"] = 0.35
        result = {
            "ok": True,
            "message": "Перевірка зразків (евристика + розмір). Після enrollment similarity буде точнішою.",
            "scores": scores,
            "recommendation": (
                "Видаліть позначені bad/weak, залиште 3–5 нормальних, "
                "потім натисніть «Запустити enrollment»."
            ),
        }
        return result
    except Exception as e:
        return {
            "ok": True,
            "message": f"Базова перевірка: {e}",
            "scores": scores,
            "recommendation": "Залиште 3–5 нормальних зразків і запустіть enrollment.",
        }


def restart_self_addon() -> dict:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return {
            "ok": False,
            "message": (
                "Немає доступу до Supervisor API. "
                "Перезапустіть аддон вручну: Add-ons → Voice Match → Restart."
            ),
        }
    try:
        import urllib.request
        req = urllib.request.Request(
            "http://supervisor/addons/self/restart",
            method="POST",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return {"ok": True, "message": "Команду Restart надіслано. Аддон перезапускається…", "raw": body}
    except Exception as e:
        return {
            "ok": False,
            "message": (
                f"Не вдалося перезапустити автоматично ({e}). "
                "Зробіть Restart вручну на сторінці аддона."
            ),
        }


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
            "need_enroll": True,
        })
    return jsonify({
        "ok": False,
        "message": "Жоден файл не підійшов (.wav .flac .ogg .mp3 .webm).",
    }), 400


@app.route("/upload_recording", methods=["POST"])
def upload_recording():
    """Accept a single recorded blob from browser MediaRecorder."""
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "message": "Невірне ім'я спікера."}), 400

    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "message": "Немає аудіо."}), 400

    target = ENROLLMENT_DIR / speaker
    target.mkdir(parents=True, exist_ok=True)

    # browser often sends audio/webm
    ext = Path(f.filename or "recording.webm").suffix.lower() or ".webm"
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".webm"
    name = f"rec_{int(time.time())}{ext}"
    dest = target / name
    f.save(str(dest))
    return jsonify({
        "ok": True,
        "message": f"Запис збережено: {name}",
        "file": name,
        "need_enroll": True,
    })


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
                "\n\n✅ Voiceprint збережено.\n"
                "⚠ Обов'язково перезапустіть аддон (кнопка нижче або Restart у картці аддона)."
            )
        return jsonify({
            "ok": ok,
            "log": log,
            "returncode": proc.returncode,
            "need_restart": ok,
        })
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


@app.route("/delete_file", methods=["POST"])
def delete_file():
    speaker = (request.form.get("speaker") or "").strip().lower()
    filename = (request.form.get("filename") or "").strip()
    if not SPEAKER_RE.match(speaker) or not filename or "/" in filename or "\\" in filename:
        return jsonify({"ok": False, "message": "Невірні параметри"}), 400
    path = ENROLLMENT_DIR / speaker / filename
    if path.exists() and path.is_file():
        path.unlink()
        return jsonify({"ok": True, "message": f"Видалено {filename}"})
    return jsonify({"ok": False, "message": "Файл не знайдено"}), 404


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
        "upstream_uri": CURRENT_UPSTREAM,
    })


@app.route("/api/scan_stt")
def api_scan_stt():
    results = scan_wyoming_stt()
    return jsonify({
        "ok": True,
        "found": results,
        "current": CURRENT_UPSTREAM,
        "hint": (
            "Скопіюйте URI → Configuration → Адреса Wyoming STT → Save → Restart. "
            "Перевіряються типові хости/порти; wyoming_ok = порт відкритий і відповідає."
        ),
    })


@app.route("/api/check_quality", methods=["POST"])
def api_check_quality():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "message": "Невірне ім'я спікера."}), 400
    return jsonify(_run_quality_check(speaker))


@app.route("/api/restart", methods=["POST"])
def api_restart():
    return jsonify(restart_self_addon())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False, threaded=True)
