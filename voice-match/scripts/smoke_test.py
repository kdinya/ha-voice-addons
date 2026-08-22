#!/usr/bin/env python3
"""Smoke checks that do not require torch / SpeechBrain.

Everything here only touches webui.py (Flask + stdlib) and static
analysis of the source tree, so it runs in a couple of seconds in CI
without installing the full ML stack (torch, speechbrain, scipy).
"""

from __future__ import annotations

import ast
import pathlib
import struct
import sys
import tempfile
import wave

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _write_wav(path: pathlib.Path, seconds: float, amplitude: int, rate: int = 16000) -> None:
    n = int(rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = b"".join(struct.pack("<h", amplitude if (i % 20) else 0) for i in range(n))
        w.writeframes(frames)


def test_routes_present() -> None:
    src = (ROOT / "webui.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    routes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "attr", "") == "route":
                    if dec.args and isinstance(dec.args[0], ast.Constant):
                        routes.add(dec.args[0].value)
    for r in ("/api/analyze_blob", "/enroll", "/api/status", "/api/check_quality",
              "/delete_file", "/delete_samples", "/delete_voiceprint"):
        assert r in routes, f"missing route {r}"


def test_no_leftover_silence_settings() -> None:
    """Regression guard: the silence-tuning options must stay fully removed."""
    banned = (
        "silence_threshold", "silence_timeout",
        "min_speech_duration", "early_endpoint",
    )
    for rel in ("config.yaml", "entrypoint.py", "webui.py",
                "wyoming_voice_match/handler.py", "wyoming_voice_match/__main__.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for term in banned:
            assert term not in text, f"found leftover {term!r} in {rel}"


def test_no_cuda_leftovers() -> None:
    for rel in ("wyoming_voice_match/verify.py", "wyoming_voice_match/__main__.py",
                "scripts/enroll.py", "webui.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "cuda" not in text.lower(), f"found leftover cuda reference in {rel}"


def test_analyze_wav_quality_levels() -> None:
    import webui  # noqa: WPS433 - deliberate late import, Flask-only module

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)

        good = tmp_path / "good.wav"
        _write_wav(good, seconds=4.0, amplitude=8000)
        info = webui.analyze_wav(good)
        assert info["quality"] == "ok", info

        short = tmp_path / "short.wav"
        _write_wav(short, seconds=0.5, amplitude=8000)
        info = webui.analyze_wav(short)
        assert info["quality"] == "bad", info

        quiet = tmp_path / "quiet.wav"
        _write_wav(quiet, seconds=4.0, amplitude=50)
        info = webui.analyze_wav(quiet)
        assert info["quality"] == "bad", info


def test_allowed_file_and_speaker_regex() -> None:
    import webui  # noqa: WPS433

    assert webui.allowed_file("sample.wav")
    assert webui.allowed_file("SAMPLE.WAV")
    assert not webui.allowed_file("sample.exe")

    assert webui.SPEAKER_RE.match("denys_1")
    assert not webui.SPEAKER_RE.match("../etc/passwd")
    assert not webui.SPEAKER_RE.match("")


def test_delete_file_rejects_traversal() -> None:
    """Regression test for the fixed /delete_file path-traversal edge case."""
    import webui  # noqa: WPS433

    client = webui.app.test_client()
    for bad_name in ("..", "../secret", "a/b", "a\\b"):
        resp = client.post("/delete_file", data={"speaker": "denys", "filename": bad_name})
        assert resp.status_code == 400, (bad_name, resp.status_code)

    # Non-existent but well-formed filename -> 404, not a crash.
    resp = client.post("/delete_file", data={"speaker": "denys", "filename": "missing.wav"})
    assert resp.status_code == 404, resp.status_code


def main() -> int:
    test_routes_present()
    test_no_leftover_silence_settings()
    test_no_cuda_leftovers()
    test_analyze_wav_quality_levels()
    test_allowed_file_and_speaker_regex()
    test_delete_file_rejects_traversal()
    print("smoke_test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
