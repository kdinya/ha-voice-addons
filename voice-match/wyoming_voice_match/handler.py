"""Wyoming event handler for speaker-verified ASR proxy."""

import asyncio
import io
import json
import logging
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from .verify import SpeakerVerifier, VerificationResult

_LOGGER = logging.getLogger("handler")

# Lock to prevent concurrent model inference
_MODEL_LOCK = asyncio.Lock()


class SpeakerVerifyHandler(AsyncEventHandler):
    """Wyoming ASR handler that gates transcription on speaker identity.

    Runs speaker verification early (as soon as enough audio is buffered).
    Once verified, waits for the full audio stream, then uses voiceprint-based
    speaker extraction to isolate the enrolled speaker's voice from background
    noise (TV, radio, other people) before forwarding to ASR.
    """

    def __init__(
        self,
        wyoming_info: Info,
        verifier: SpeakerVerifier,
        upstream_uri: str,
        tag_speaker: bool = False,
        require_speaker_match: bool = True,
        save_rejected: bool = False,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.wyoming_info = wyoming_info
        self.verifier = verifier
        self.upstream_uri = upstream_uri
        self.tag_speaker = tag_speaker
        self.require_speaker_match = require_speaker_match
        self.save_rejected = save_rejected
        self.rejected_dir = Path("/data/rejections")

        # Per-connection state
        self._audio_buffer = bytes()
        self._audio_rate: int = 16000
        self._audio_width: int = 2
        self._audio_channels: int = 1
        self._language: Optional[str] = None
        self._verify_task: Optional[asyncio.Task] = None
        self._verify_started: bool = False
        self._responded: bool = False
        self._stream_start_time: Optional[float] = None
        self._session_id: str = uuid.uuid4().hex[:8]
        self._audio_stopped = asyncio.Event()

    async def handle_event(self, event: Event) -> bool:
        """Process a single Wyoming event."""
        sid = self._session_id

        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True

        if AudioStart.is_type(event.type):
            audio_start = AudioStart.from_event(event)
            self._audio_buffer = bytes()
            self._audio_rate = audio_start.rate
            self._audio_width = audio_start.width
            self._audio_channels = audio_start.channels
            self._verify_started = False
            self._responded = False
            self._stream_start_time = time.monotonic()
            self._audio_stopped.clear()
            if self._verify_task and not self._verify_task.done():
                self._verify_task.cancel()
            self._verify_task = None
            _LOGGER.debug("[%s] AudioStart rate=%s", sid, self._audio_rate)
            return True

        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            self._audio_buffer += chunk.audio

            # Start verification once we have enough audio
            if (
                not self._verify_started
                and not self._responded
                and len(self._audio_buffer) >= int(self._audio_rate * self._audio_width * 1.5)
            ):
                self._verify_started = True
                self._verify_task = asyncio.create_task(self._run_verification())
            return True

        if AudioStop.is_type(event.type):
            self._audio_stopped.set()
            _LOGGER.debug("[%s] AudioStop, buffer=%d bytes", sid, len(self._audio_buffer))

            if self._verify_task and not self._verify_task.done():
                try:
                    await self._verify_task
                except asyncio.CancelledError:
                    pass

            if not self._responded:
                await self._finalize()
            return True

        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)
            self._language = transcribe.language
            return True

        return True

    async def _run_verification(self) -> None:
        """Run speaker verification on buffered audio."""
        sid = self._session_id
        try:
            async with _MODEL_LOCK:
                result = self.verifier.verify(self._audio_buffer, self._audio_rate)

            if result.is_match:
                _LOGGER.info(
                    "[%s] Speaker matched: %s (sim=%.3f)",
                    sid, result.matched_speaker, result.similarity,
                )
            else:
                _LOGGER.info(
                    "[%s] Speaker rejected (best=%.3f, threshold=%.2f)",
                    sid, result.similarity, result.threshold,
                )
                if self.require_speaker_match:
                    self._responded = True
                    if self.save_rejected:
                        self._save_rejection(result)
                    # Do not forward to upstream
                    return

        except Exception as e:
            _LOGGER.exception("[%s] Verification error: %s", sid, e)

    async def _finalize(self) -> None:
        """Forward verified audio to upstream ASR and return transcript."""
        sid = self._session_id
        self._responded = True

        if not self._audio_buffer:
            return

        try:
            async with _MODEL_LOCK:
                result = self.verifier.verify(self._audio_buffer, self._audio_rate)

            if self.require_speaker_match and not result.is_match:
                _LOGGER.info("[%s] Final reject (sim=%.3f)", sid, result.similarity)
                if self.save_rejected:
                    self._save_rejection(result)
                return

            # Extract speaker audio if available
            audio_to_send = result.speech_audio if result.speech_audio else self._audio_buffer

            transcript_text = await self._forward_to_upstream(audio_to_send)
            if transcript_text is None:
                return

            if self.tag_speaker and result.matched_speaker:
                transcript_text = f"[{result.matched_speaker}] {transcript_text}"

            await self.write_event(Transcript(text=transcript_text).event())
            _LOGGER.info("[%s] Transcript: %s", sid, transcript_text[:80])

        except Exception as e:
            _LOGGER.exception("[%s] Finalize error: %s", sid, e)

    async def _forward_to_upstream(self, audio: bytes) -> Optional[str]:
        """Send audio to upstream Wyoming ASR and get transcript."""
        try:
            async with AsyncClient.from_uri(self.upstream_uri) as client:
                if self._language:
                    await client.write_event(Transcribe(language=self._language).event())
                await client.write_event(
                    AudioStart(
                        rate=self._audio_rate,
                        width=self._audio_width,
                        channels=self._audio_channels,
                    ).event()
                )
                # Send in chunks
                chunk_size = 2048
                for i in range(0, len(audio), chunk_size):
                    await client.write_event(
                        AudioChunk(
                            rate=self._audio_rate,
                            width=self._audio_width,
                            channels=self._audio_channels,
                            audio=audio[i : i + chunk_size],
                        ).event()
                    )
                await client.write_event(AudioStop().event())

                while True:
                    event = await asyncio.wait_for(client.read_event(), timeout=30.0)
                    if event is None:
                        break
                    if Transcript.is_type(event.type):
                        return Transcript.from_event(event).text
        except Exception as e:
            _LOGGER.error("Upstream ASR error: %s", e)
        return None

    def _save_rejection(self, result: VerificationResult) -> None:
        """Save rejected audio for debugging."""
        try:
            self.rejected_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            path = self.rejected_dir / f"reject_{ts}_{self._session_id}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(self._audio_channels)
                w.setsampwidth(self._audio_width)
                w.setframerate(self._audio_rate)
                w.writeframes(self._audio_buffer)
            meta = {
                "similarity": result.similarity,
                "threshold": result.threshold,
                "scores": result.all_scores,
            }
            path.with_suffix(".json").write_text(json.dumps(meta, indent=2))
        except Exception:
            pass
