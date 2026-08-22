#!/usr/bin/env python3
"""Ingress web UI for autonomous Voice Match. Hot-reload — no restart after enrollment."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder="/static", static_url_path="/static")
# No Flask sessions are used anywhere in this app (Ingress already sits
# behind the Home Assistant Supervisor proxy for auth), so no secret_key
# is configured.
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

ENROLLMENT_DIR = Path(os.environ.get("ENROLLMENT_DIR", "/data/enrollment"))
VOICEPRINTS_DIR = Path(os.environ.get("VOICEPRINTS_DIR", "/data/voiceprints"))
MODEL_DIR = os.environ.get("MODEL_DIR", "/data/models")
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
                    files.append({"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)})
            result.append({"name": d.name, "files": files, "count": len(files)})
    return result


def list_all_speaker_names():
    names = set()
    if ENROLLMENT_DIR.exists():
        for d in ENROLLMENT_DIR.iterdir():
            if d.is_dir():
                names.add(d.name)
    if VOICEPRINTS_DIR.exists():
        for f in VOICEPRINTS_DIR.glob("*.npy"):
            names.add(f.stem)
    return sorted(names)


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


def _wyoming_info_probe(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            try:
                sock.recv(64)
            except socket.timeout:
                pass
            return True
    except OSError:
        return False


def scan_wyoming_stt():
    found, seen = [], set()
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
                found.append({
                    "uri": uri, "host": host, "port": port,
                    "label": "STT" if port == 10300 else f"port {port}",
                    "wyoming_ok": _wyoming_info_probe(host, port),
                    "current": uri == CURRENT_UPSTREAM,
                })
            except Exception:
                pass
    found.sort(key=lambda x: (not x.get("wyoming_ok"), x["host"], x["port"]))
    return found


def convert_to_wav(src: Path, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-i", str(src), "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(dest)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 or not dest.exists():
            return False, f"ffmpeg error: {(proc.stderr or '')[-500:]}"
        return True, "ok"
    except FileNotFoundError:
        return False, "ffmpeg not installed"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timeout"


def analyze_wav(path: Path) -> dict:
    info = {"file": path.name, "size_kb": round(path.stat().st_size / 1024, 1),
            "duration_s": None, "sample_rate": None, "channels": None,
            "rms": None, "peak": None, "quality": "bad", "note": "", "issues": []}
    try:
        with wave.open(str(path), "rb") as w:
            rate, ch, nframes, sampwidth = w.getframerate(), w.getnchannels(), w.getnframes(), w.getsampwidth()
            info["sample_rate"], info["channels"], info["duration_s"] = rate, ch, round(nframes / float(rate) if rate else 0, 2)
            raw = w.readframes(nframes)
            if sampwidth == 2 and raw:
                import array
                samples = array.array("h")
                samples.frombytes(raw)
                if ch > 1:
                    samples = array.array("h", (samples[i] for i in range(0, len(samples), ch)))
                if samples:
                    peak = max(abs(s) for s in samples)
                    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
                    info["peak"], info["rms"] = int(peak), round(rms, 1)
    except Exception as e:
        info["issues"].append(str(e))
        info["note"] = "файл пошкоджений"
        return info
    if info["duration_s"] is not None:
        if info["duration_s"] < 1.5:
            info["issues"].append("занадто короткий (<1.5 с)")
        elif info["duration_s"] < 3.0:
            info["issues"].append("короткий (краще 3–10 с)")
    if info["peak"] is not None:
        if info["peak"] < 500:
            info["issues"].append("дуже тихо")
        elif info["peak"] < 2000:
            info["issues"].append("тихо")
        if info["peak"] >= 32000:
            info["issues"].append("кліпування")
    hard = any(x.startswith(("занадто короткий", "дуже тихо")) for x in info["issues"])
    if hard:
        info["quality"], info["note"] = "bad", "; ".join(info["issues"])
    elif info["issues"]:
        info["quality"], info["note"] = "weak", "; ".join(info["issues"])
    else:
        info["quality"] = "ok"
        info["note"] = f"OK — {info['duration_s']}с"
    return info


def _run_quality_check(speaker: str) -> dict:
    speaker_dir = ENROLLMENT_DIR / speaker
    if not speaker_dir.exists():
        return {"ok": False, "message": "Немає зразків", "scores": []}
    scores = []
    for f in sorted(speaker_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        info = analyze_wav(f) if f.suffix.lower() == ".wav" else {"file": f.name, "quality": "bad", "note": "не wav"}
        info["file"] = f.name
        scores.append(info)
    ok_count = sum(1 for s in scores if s.get("quality") == "ok")
    return {
        "ok": True,
        "message": f"Перевірено {len(scores)}, OK: {ok_count}",
        "scores": scores,
        "recommendation": "Видаліть bad/weak. 3–5 OK → Enrollment. Restart більше НЕ потрібен (hot-reload).",
    }


def _supervisor_request(path: str, method: str = "GET", timeout: float = 10):
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return None, "Немає SUPERVISOR_TOKEN"
    try:
        import urllib.request
        req = urllib.request.Request(f"http://supervisor{path}", method=method,
                                     headers={"Authorization": f"Bearer {token}"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        return (json.loads(body) if body else {}), None
    except Exception as e:
        return None, str(e)


def get_self_addon_info() -> dict:
    data, err = _supervisor_request("/addons/self/info")
    if err or not data:
        return {"ok": False, "slug": "voice_match", "paths": ["/config/app/voice_match/info"]}
    info = data.get("data", data) if isinstance(data, dict) else {}
    slug = info.get("slug") or "voice_match"
    return {"ok": True, "slug": slug, "name": info.get("name") or "Voice Match",
            "state": info.get("state"), "version": info.get("version"),
            "paths": [f"/config/app/{slug}/info", f"/hassio/addon/{slug}/info"]}


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
        return jsonify({"ok": False, "message": "Невірне ім'я спікера."}), 400
    files = request.files.getlist("files")
    if not files:
        return jsonify({"ok": False, "message": "Файли не вибрані."}), 400
    target = ENROLLMENT_DIR / speaker
    target.mkdir(parents=True, exist_ok=True)
    saved = 0
    for f in files:
        if not f or not f.filename or not allowed_file(f.filename):
            continue
        raw = re.sub(r"[^\w.\-]", "_", Path(f.filename).name)
        tmp = target / f".tmp_{int(time.time())}_{raw}"
        f.save(str(tmp))
        dest = target / f"{Path(raw).stem}_{int(time.time())}.wav"
        ok, _ = convert_to_wav(tmp, dest)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        if ok:
            saved += 1
    if saved:
        return jsonify({"ok": True, "message": f"Збережено {saved} файл(ів).", "need_enroll": True})
    return jsonify({"ok": False, "message": "Не вдалося зберегти."}), 400


@app.route("/upload_recording", methods=["POST"])
def upload_recording():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "message": "Невірне ім'я."}), 400
    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "message": "Немає аудіо."}), 400
    target = ENROLLMENT_DIR / speaker
    target.mkdir(parents=True, exist_ok=True)
    tmp = target / f".rec_{int(time.time())}.webm"
    f.save(str(tmp))
    dest = target / f"rec_{int(time.time())}.wav"
    ok, err = convert_to_wav(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass
    if not ok:
        return jsonify({"ok": False, "message": err}), 500
    return jsonify({"ok": True, "message": f"Збережено {dest.name}", "analysis": analyze_wav(dest), "need_enroll": True})


@app.route("/api/analyze_blob", methods=["POST"])
def api_analyze_blob():
    """Analyze microphone recording before save (convert → quality check)."""
    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "quality": "bad", "message": "Немає аудіо."}), 400
    tmp_dir = Path("/tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(f.filename or "rec.webm").suffix.lower() or ".webm"
    if suffix not in ALLOWED_EXTENSIONS and suffix != ".webm":
        suffix = ".webm"
    src = tmp_dir / f"analyze_{int(time.time() * 1000)}{suffix}"
    dest = tmp_dir / f"analyze_{int(time.time() * 1000)}.wav"
    try:
        f.save(str(src))
        ok, err = convert_to_wav(src, dest)
        if not ok:
            return jsonify({"ok": False, "quality": "bad", "message": err or "Конвертація не вдалася"})
        info = analyze_wav(dest)
        info["ok"] = info.get("quality") != "bad"
        return jsonify(info)
    finally:
        for p in (src, dest):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


@app.route("/enroll", methods=["POST"])
def enroll():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "log": "Невірне ім'я."}), 400
    speaker_dir = ENROLLMENT_DIR / speaker
    if not speaker_dir.exists() or not any(speaker_dir.iterdir()):
        return jsonify({"ok": False, "log": "Немає файлів."}), 400
    cmd = [sys.executable, "-m", "scripts.enroll", "--speaker", speaker,
           "--enrollment-dir", str(ENROLLMENT_DIR), "--voiceprints-dir", str(VOICEPRINTS_DIR),
           "--model-dir", MODEL_DIR]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, env=os.environ.copy())
        log = (proc.stdout or "") + (proc.stderr or "")
        ok = proc.returncode == 0
        if ok:
            log += "\n\n✅ Voiceprint збережено і активовано.\nHot-reload: рестарт більше НЕ потрібен.\nНовий голос працює з наступного запиту."
        return jsonify({"ok": ok, "log": log, "need_restart": False})
    except Exception as e:
        return jsonify({"ok": False, "log": str(e)}), 500


@app.route("/delete_samples", methods=["POST"])
def delete_samples():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if SPEAKER_RE.match(speaker):
        path = ENROLLMENT_DIR / speaker
        if path.exists():
            shutil.rmtree(path)
    return jsonify({"ok": True})


@app.route("/delete_file", methods=["POST"])
def delete_file():
    speaker = (request.form.get("speaker") or "").strip().lower()
    filename = (request.form.get("filename") or "").strip()
    if (
        not SPEAKER_RE.match(speaker)
        or not filename
        or "/" in filename
        or "\\" in filename
        or filename in (".", "..")
    ):
        return jsonify({"ok": False}), 400
    path = ENROLLMENT_DIR / speaker / filename
    try:
        if not path.is_file():
            return jsonify({"ok": False}), 404
        path.unlink()
        return jsonify({"ok": True})
    except OSError:
        return jsonify({"ok": False}), 500


@app.route("/delete_voiceprint", methods=["POST"])
def delete_voiceprint():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if SPEAKER_RE.match(speaker):
        vp = VOICEPRINTS_DIR / f"{speaker}.npy"
        if vp.exists():
            vp.unlink()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify({"enrollment": list_speakers_enrollment(), "voiceprints": list_voiceprints(),
                    "speakers": list_all_speaker_names(), "upstream_uri": CURRENT_UPSTREAM})


@app.route("/api/scan_stt")
def api_scan_stt():
    return jsonify({"ok": True, "found": scan_wyoming_stt(), "current": CURRENT_UPSTREAM})


@app.route("/api/check_quality", methods=["POST"])
def api_check_quality():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False}), 400
    return jsonify(_run_quality_check(speaker))


@app.route("/api/addon_info")
def api_addon_info():
    return jsonify(get_self_addon_info())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False, threaded=True)
