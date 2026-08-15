#!/usr/bin/env python3
"""Ingress web UI: record→wav, quality check, enroll, scan, restart."""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import wave
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
                    "uri": uri,
                    "host": host,
                    "port": port,
                    "label": "STT" if port == 10300 else f"port {port}",
                    "wyoming_ok": _wyoming_info_probe(host, port),
                    "current": uri == CURRENT_UPSTREAM,
                })
            except Exception:
                pass
    found.sort(key=lambda x: (not x.get("wyoming_ok"), x["host"], x["port"]))
    return found


def convert_to_wav(src: Path, dest: Path) -> tuple[bool, str]:
    """Convert any audio to 16 kHz mono 16-bit WAV via ffmpeg."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(src),
        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16",
        str(dest),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if proc.returncode != 0 or not dest.exists():
            err = (proc.stderr or proc.stdout or "")[-500:]
            return False, f"ffmpeg error: {err}"
        return True, "ok"
    except FileNotFoundError:
        return False, "ffmpeg not installed"
    except subprocess.TimeoutExpired:
        return False, "ffmpeg timeout"


def analyze_wav(path: Path) -> dict:
    """Inspect WAV: duration, rate, channels, peak/rms energy."""
    info = {
        "file": path.name,
        "size_kb": round(path.stat().st_size / 1024, 1),
        "duration_s": None,
        "sample_rate": None,
        "channels": None,
        "rms": None,
        "peak": None,
        "quality": "bad",
        "note": "",
        "issues": [],
    }
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate()
            ch = w.getnchannels()
            nframes = w.getnframes()
            sampwidth = w.getsampwidth()
            duration = nframes / float(rate) if rate else 0
            info["sample_rate"] = rate
            info["channels"] = ch
            info["duration_s"] = round(duration, 2)

            raw = w.readframes(nframes)
            if sampwidth == 2 and raw:
                import array
                samples = array.array("h")
                samples.frombytes(raw)
                if ch > 1:
                    # take first channel only for metrics
                    samples = array.array("h", (samples[i] for i in range(0, len(samples), ch)))
                if samples:
                    peak = max(abs(s) for s in samples)
                    mean_sq = sum(s * s for s in samples) / len(samples)
                    rms = mean_sq ** 0.5
                    info["peak"] = int(peak)
                    info["rms"] = round(rms, 1)
            else:
                info["issues"].append("нестандартний формат семплів")
    except Exception as e:
        info["issues"].append(f"не вдалося прочитати wav: {e}")
        info["note"] = "файл пошкоджений або не WAV"
        info["quality"] = "bad"
        return info

    # Rules for enrollment quality
    if info["duration_s"] is not None:
        if info["duration_s"] < 1.5:
            info["issues"].append("занадто короткий (<1.5 с)")
        elif info["duration_s"] < 3.0:
            info["issues"].append("короткий (краще 3–10 с)")
        elif info["duration_s"] > 20:
            info["issues"].append("дуже довгий (>20 с)")

    if info["sample_rate"] and info["sample_rate"] not in (16000, 22050, 44100, 48000):
        info["issues"].append(f"незвичний sample rate {info['sample_rate']}")

    if info["channels"] and info["channels"] > 2:
        info["issues"].append(f"багато каналів ({info['channels']})")

    if info["peak"] is not None:
        if info["peak"] < 500:
            info["issues"].append("дуже тихо (майже тиша)")
        elif info["peak"] < 2000:
            info["issues"].append("тихо — говоріть гучніше/ближче")
        if info["peak"] >= 32000:
            info["issues"].append("можливе кліпування (перевантаження)")

    if info["rms"] is not None and info["rms"] < 100:
        info["issues"].append("низька енергія сигналу")

    hard = any(
        x.startswith("занадто короткий")
        or x.startswith("дуже тихо")
        or x.startswith("не вдалося")
        or x.startswith("файл пошкоджений")
        for x in info["issues"]
    )
    soft = bool(info["issues"]) and not hard

    if hard:
        info["quality"] = "bad"
        info["note"] = "; ".join(info["issues"])
    elif soft:
        info["quality"] = "weak"
        info["note"] = "; ".join(info["issues"])
    else:
        info["quality"] = "ok"
        info["note"] = (
            f"OK — {info['duration_s']}с, {info['sample_rate']} Hz, "
            f"peak={info['peak']}, rms={info['rms']}"
        )
    return info


def _run_quality_check(speaker: str) -> dict:
    speaker_dir = ENROLLMENT_DIR / speaker
    if not speaker_dir.exists():
        return {"ok": False, "message": "Немає зразків", "scores": []}

    scores = []
    for f in sorted(speaker_dir.iterdir()):
        if not f.is_file() or f.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        wav_path = f
        tmp = None
        if f.suffix.lower() != ".wav":
            tmp = Path(tempfile.mkdtemp()) / (f.stem + ".wav")
            ok, err = convert_to_wav(f, tmp)
            if not ok:
                scores.append({
                    "file": f.name,
                    "size_kb": round(f.stat().st_size / 1024, 1),
                    "quality": "bad",
                    "note": f"не конвертується: {err}",
                    "issues": [err],
                })
                continue
            wav_path = tmp
        info = analyze_wav(wav_path)
        info["file"] = f.name
        scores.append(info)
        if tmp and tmp.exists():
            try:
                tmp.unlink()
                tmp.parent.rmdir()
            except OSError:
                pass

    ok_count = sum(1 for s in scores if s.get("quality") == "ok")
    return {
        "ok": True,
        "message": f"Перевірено {len(scores)} файл(ів), нормальних: {ok_count}",
        "scores": scores,
        "recommendation": (
            "Видаліть bad, бажано й weak. Залиште 3–5 зразків зі статусом OK, "
            "потім «Запустити enrollment» → Restart."
        ),
    }


def _supervisor_request(path: str, method: str = "GET", timeout: float = 10):
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return None, "Немає SUPERVISOR_TOKEN"
    try:
        import urllib.request
        req = urllib.request.Request(
            f"http://supervisor{path}",
            method=method,
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {"raw": body}
        return data, None
    except Exception as e:
        return None, str(e)


def get_self_addon_info() -> dict:
    """Resolve slug / frontend paths for this addon via Supervisor API."""
    data, err = _supervisor_request("/addons/self/info")
    if err or not data:
        return {
            "ok": False,
            "message": err or "Не вдалося отримати info",
            "slug": "voice_match",
            "paths": [
                "/config/app/voice_match/info",
                "/hassio/addon/voice_match/info",
            ],
        }
    info = data.get("data") if isinstance(data, dict) and "data" in data else data
    if not isinstance(info, dict):
        info = {}
    slug = info.get("slug") or info.get("addon") or "voice_match"
    paths = [
        f"/config/app/{slug}/info",
        f"/hassio/addon/{slug}/info",
    ]
    if "_" in slug:
        short = slug.split("_", 1)[-1]
        if short and short != slug:
            paths.extend([
                f"/config/app/{short}/info",
                f"/hassio/addon/{short}/info",
            ])
    return {
        "ok": True,
        "slug": slug,
        "name": info.get("name") or "Voice Match",
        "state": info.get("state"),
        "version": info.get("version"),
        "paths": paths,
        "message": "ok",
    }


def restart_self_addon() -> dict:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        return {
            "ok": False,
            "message": "Немає Supervisor API. Restart вручну: Settings → Add-ons → Voice Match → Restart.",
        }
    data, err = _supervisor_request("/addons/self/restart", method="POST", timeout=15)
    if err:
        return {
            "ok": False,
            "message": f"Авто-restart не вдався ({err}). Відкрийте сторінку аддона і натисніть Restart.",
        }
    return {
        "ok": True,
        "message": "Команду Restart надіслано. Аддон зараз перезапускається (UI може на кілька секунд зникнути).",
        "raw": data,
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
        return jsonify({"ok": False, "message": "Невірне ім'я спікера (a-z0-9_-)."}), 400

    files = request.files.getlist("files")
    if not files or all(not f.filename for f in files):
        return jsonify({"ok": False, "message": "Файли не вибрані."}), 400

    target = ENROLLMENT_DIR / speaker
    target.mkdir(parents=True, exist_ok=True)
    saved, errors = 0, []

    for f in files:
        if not f or not f.filename or not allowed_file(f.filename):
            continue
        raw_name = re.sub(r"[^\w.\-]", "_", Path(f.filename).name)
        tmp_path = target / f".tmp_{int(time.time())}_{raw_name}"
        f.save(str(tmp_path))

        # Always store as wav for enrollment compatibility
        dest = target / f"{Path(raw_name).stem}_{int(time.time())}.wav"
        if dest.exists():
            dest = target / f"{Path(raw_name).stem}_{int(time.time())}_{saved}.wav"
        ok, err = convert_to_wav(tmp_path, dest)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        if ok:
            saved += 1
        else:
            errors.append(f"{raw_name}: {err}")

    if saved:
        return jsonify({
            "ok": True,
            "message": f"Збережено {saved} файл(ів) як WAV для «{speaker}».",
            "errors": errors,
            "need_enroll": True,
        })
    return jsonify({
        "ok": False,
        "message": "Не вдалося зберегти. " + "; ".join(errors[:3]),
    }), 400


@app.route("/upload_recording", methods=["POST"])
def upload_recording():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "message": "Невірне ім'я спікера."}), 400

    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "message": "Немає аудіо."}), 400

    target = ENROLLMENT_DIR / speaker
    target.mkdir(parents=True, exist_ok=True)

    tmp = target / f".rec_tmp_{int(time.time())}.webm"
    f.save(str(tmp))
    dest = target / f"rec_{int(time.time())}.wav"
    ok, err = convert_to_wav(tmp, dest)
    try:
        tmp.unlink(missing_ok=True)
    except OSError:
        pass

    if not ok:
        return jsonify({"ok": False, "message": f"Конвертація в WAV не вдалась: {err}"}), 500

    analysis = analyze_wav(dest)
    return jsonify({
        "ok": True,
        "message": f"Запис збережено як {dest.name}",
        "file": dest.name,
        "analysis": analysis,
        "need_enroll": True,
    })


@app.route("/api/analyze_blob", methods=["POST"])
def analyze_blob():
    """Analyze a recording before save (optional client flow)."""
    f = request.files.get("audio")
    if not f:
        return jsonify({"ok": False, "message": "Немає аудіо"}), 400
    with tempfile.TemporaryDirectory() as td:
        src = Path(td) / "in.webm"
        wav = Path(td) / "out.wav"
        f.save(str(src))
        ok, err = convert_to_wav(src, wav)
        if not ok:
            return jsonify({"ok": False, "message": err, "quality": "bad"})
        info = analyze_wav(wav)
        return jsonify({"ok": True, **info})


@app.route("/enroll", methods=["POST"])
def enroll():
    speaker = (request.form.get("speaker") or "").strip().lower()
    if not SPEAKER_RE.match(speaker):
        return jsonify({"ok": False, "log": "Невірне ім'я спікера."}), 400

    speaker_dir = ENROLLMENT_DIR / speaker
    if not speaker_dir.exists() or not any(speaker_dir.iterdir()):
        return jsonify({"ok": False, "log": f"Немає файлів у /data/enrollment/{speaker}/"}), 400

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
                "⚠ Обов'язково Restart аддона — блок «Restart аддона» внизу сторінки "
                "або кнопка Restart на сторінці аддона в Supervisor."
            )
        return jsonify({"ok": ok, "log": log, "need_restart": ok})
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
        "speakers": list_all_speaker_names(),
        "upstream_uri": CURRENT_UPSTREAM,
    })


@app.route("/api/scan_stt")
def api_scan_stt():
    return jsonify({
        "ok": True,
        "found": scan_wyoming_stt(),
        "current": CURRENT_UPSTREAM,
        "hint": "Скопіюйте URI → Configuration → Адреса Wyoming STT → Save → Restart.",
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


@app.route("/api/addon_info")
def api_addon_info():
    return jsonify(get_self_addon_info())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8099, debug=False, threaded=True)
