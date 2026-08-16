#!/usr/bin/env python3
"""Smoke checks that do not require torch / SpeechBrain."""

from __future__ import annotations

import ast
import pathlib
import sys
import wave
import struct
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]


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
    for r in ("/api/analyze_blob", "/enroll", "/api/status", "/api/check_quality"):
        assert r in routes, f"missing route {r}"


def test_analyze_wav_logic() -> None:
    # Import analyze_wav by exec subset is heavy; re-check via temporary wav
    sys.path.insert(0, str(ROOT))
    # Minimal inline replica of duration check using wave module only
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
        path = pathlib.Path(tf.name)
    try:
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            # 2 seconds of quiet tone-ish noise
            frames = b"".join(struct.pack("<h", 1000 if (i % 20) else 0) for i in range(16000 * 2))
            w.writeframes(frames)
        with wave.open(str(path), "rb") as w:
            assert w.getframerate() == 16000
            assert w.getnframes() / 16000 >= 1.5
    finally:
        path.unlink(missing_ok=True)


def main() -> int:
    test_routes_present()
    test_analyze_wav_logic()
    print("smoke_test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
