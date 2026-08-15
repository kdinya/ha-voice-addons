"""Entry point for Voice Match (autonomous)."""

import argparse
import asyncio
import logging
import os
import sys
from functools import partial
from pathlib import Path
from typing import List

from wyoming.client import AsyncClient
from wyoming.info import AsrModel, AsrProgram, Attribution, Describe, Info
from wyoming.server import AsyncServer

from . import __version__
from .handler import SpeakerVerifyHandler
from .verify import SpeakerVerifier

_LOGGER = logging.getLogger("main")


async def query_upstream_languages(
    uri: str, timeout: float = 10.0, max_retries: int = 10, retry_delay: float = 3.0,
) -> List[str]:
    for attempt in range(1, max_retries + 1):
        try:
            async with AsyncClient.from_uri(uri) as client:
                await client.write_event(Describe().event())
                while True:
                    event = await asyncio.wait_for(client.read_event(), timeout=timeout)
                    if event is None:
                        break
                    if Info.is_type(event.type):
                        info = Info.from_event(event)
                        languages = []
                        for asr in info.asr:
                            for model in asr.models:
                                languages.extend(model.languages)
                        seen = set()
                        unique = []
                        for lang in languages:
                            if lang not in seen:
                                seen.add(lang)
                                unique.append(lang)
                        if unique:
                            _LOGGER.info(
                                "Upstream ASR supports %d language(s): %s",
                                len(unique), ", ".join(unique),
                            )
                            return unique
        except Exception as exc:
            if attempt < max_retries:
                _LOGGER.warning(
                    "Upstream ASR not ready at %s (attempt %d/%d): %s — retrying in %.0fs",
                    uri, attempt, max_retries, exc, retry_delay,
                )
                await asyncio.sleep(retry_delay)
            else:
                _LOGGER.warning(
                    "Could not query upstream ASR languages after %d attempts: %s",
                    max_retries, exc,
                )
    return []


def get_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wyoming ASR proxy with speaker verification")
    parser.add_argument("--uri", default=os.environ.get("LISTEN_URI", "tcp://0.0.0.0:10350"))
    parser.add_argument("--upstream-uri", default=os.environ.get("UPSTREAM_URI", "tcp://localhost:10300"))
    parser.add_argument("--voiceprints-dir", default=os.environ.get("VOICEPRINTS_DIR", "/data/voiceprints"))
    parser.add_argument("--threshold", type=float, default=float(os.environ.get("VERIFY_THRESHOLD", "0.35")))
    parser.add_argument("--extraction-threshold", type=float, default=float(os.environ.get("EXTRACTION_THRESHOLD", "0.30")))
    parser.add_argument("--device", default=os.environ.get("DEVICE", "cpu"), choices=["cuda", "cpu"])
    parser.add_argument("--model-dir", default=os.environ.get("MODEL_DIR", "/data/models"))
    parser.add_argument("--debug", action="store_true", default=os.environ.get("LOG_LEVEL", "INFO").upper() == "DEBUG")
    parser.add_argument("--max-verify-seconds", type=float, default=float(os.environ.get("MAX_VERIFY_SECONDS", "5.0")))
    parser.add_argument("--window-seconds", type=float, default=float(os.environ.get("VERIFY_WINDOW_SECONDS", "3.0")))
    parser.add_argument("--step-seconds", type=float, default=float(os.environ.get("VERIFY_STEP_SECONDS", "1.5")))
    parser.add_argument("--tag-speaker", action="store_true", default=os.environ.get("TAG_SPEAKER", "false").lower() in ("true", "1", "yes"))
    parser.add_argument("--require-speaker-match", action="store_true", default=os.environ.get("REQUIRE_SPEAKER_MATCH", "true").lower() in ("true", "1", "yes"))
    parser.add_argument("--save-rejected", action="store_true", default=os.environ.get("SAVE_REJECTED", "false").lower() in ("true", "1", "yes"))
    parser.add_argument("--languages", default=os.environ.get("STT_LANGUAGES", "uk,ru"),
                        help="Comma-separated languages to advertise to Home Assistant")
    return parser.parse_args()


async def main() -> None:
    args = get_args()
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    voiceprints_dir = Path(args.voiceprints_dir)
    if not voiceprints_dir.exists():
        voiceprints_dir.mkdir(parents=True, exist_ok=True)

    _LOGGER.info("Loading ECAPA-TDNN speaker verification model...")
    verifier = SpeakerVerifier(
        voiceprints_dir=str(voiceprints_dir),
        model_dir=args.model_dir,
        device=args.device,
        threshold=args.threshold,
        extraction_threshold=args.extraction_threshold,
        max_verify_seconds=args.max_verify_seconds,
        window_seconds=args.window_seconds,
        step_seconds=args.step_seconds,
    )

    if not verifier.voiceprints:
        if args.require_speaker_match:
            _LOGGER.warning(
                "No voiceprints found in %s — enroll a speaker via the Web UI. "
                "Running with empty voiceprints (will reject until enrolled).",
                voiceprints_dir,
            )
        else:
            _LOGGER.warning("No voiceprints — bypass mode")

    _LOGGER.info(
        "Speaker verifier ready — %d speaker(s) (threshold=%.2f, extraction=%.2f, device=%s)",
        len(verifier.voiceprints), args.threshold, args.extraction_threshold, args.device,
    )

    upstream_languages = await query_upstream_languages(args.upstream_uri)
    forced_languages = [lang.strip() for lang in args.languages.split(",") if lang.strip()]

    if not upstream_languages:
        _LOGGER.warning("Could not detect upstream languages — using fallback: %s", ", ".join(forced_languages))
        upstream_languages = list(forced_languages)
    else:
        for lang in forced_languages:
            if lang not in upstream_languages:
                upstream_languages.append(lang)

    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="voice-match",
                description=f"Speaker-verified ASR proxy v{__version__}",
                attribution=Attribution(name="Voice Match (HA)", url="https://github.com/kdinya/ha-voice-addons"),
                installed=True,
                version=__version__,
                models=[
                    AsrModel(
                        name="voice-match-proxy",
                        description="ECAPA-TDNN speaker gate → upstream ASR",
                        languages=upstream_languages,
                        attribution=Attribution(name="Voice Match (HA)", url="https://github.com/kdinya/ha-voice-addons"),
                        installed=True,
                        version=__version__,
                    )
                ],
            )
        ]
    )

    _LOGGER.info("Starting server on %s → upstream %s", args.uri, args.upstream_uri)
    server = AsyncServer.from_uri(args.uri)
    await server.run(
        partial(
            SpeakerVerifyHandler,
            wyoming_info,
            verifier,
            args.upstream_uri,
            args.tag_speaker,
            args.require_speaker_match,
            args.save_rejected,
        )
    )


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
