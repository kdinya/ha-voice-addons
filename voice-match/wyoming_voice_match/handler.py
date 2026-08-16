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

_MODEL_LOCK = asyncio.Lock()


class SpeakerVerifyHandler(AsyncEventHandler):
    """Wyoming ASR handler that gates transcription on speaker identity."""

    def __init__(
        self,
        wyoming_info: Info,
        verifier: SpeakerVerifier,
        upstream_uri: str,
        tag_speaker: bool = False,
        require_speaker_match: bool = True,
        save_rejected: bool = False,
        *args,
        early_reject: bool = True,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.wyoming_info = wyoming_info
        self.verifier = verifier
        self.upstream_uri = upstream_uri
        self.tag_speaker = tag_speaker
        self.require_speaker_match = require_speaker_match
        self.save_rejected = save_rejected
        self.early_reject = early_reject
        self.rejected_dir = Path("/data/rejections")
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
        sid = self._session_id
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True
        if Transcribe.is_type(event.type):
            self._language = Transcribe.from_event(event).language
            return True
        if AudioStart.is_type(event.type):
            self._audio_buffer = bytes()
            self._verify_task = None
            self._verify_started = False
            self._responded = False
            self._audio_stopped = asyncio.Event()
            self._stream_start_time = time.monotonic()
            self._verify_result_cache = None
            _LOGGER.info("[%s] -- New audio session started --", sid)
            return True
        if AudioChunk.is_type(event.type):
            chunk = AudioChunk.from_event(event)
            self._audio_rate = chunk.rate
            self._audio_width = chunk.width
            self._audio_channels = chunk.channels
            self._audio_buffer += chunk.audio
            if not self._verify_started and not self._responded:
                bps = self._audio_rate * self._audio_width * self._audio_channels
                buffered_seconds = len(self._audio_buffer) / bps if bps else 0
                if buffered_seconds >= self.verifier.max_verify_seconds:
                    self._verify_started = True
                    verify_audio = bytes(self._audio_buffer)
                    self._verify_task = asyncio.create_task(
                        self._run_early_pipeline(verify_audio)
                    )
            return True
        if AudioStop.is_type(event.type):
            self._audio_stopped.set()
            if self._responded:
                return True
            await self._process_audio_sync()
            return True
        return True

    async def _run_early_pipeline(self, verify_audio: bytes) -> None:
        sid = self._session_id
        async with _MODEL_LOCK:
            loop = asyncio.get_running_loop()
            verify_start = time.monotonic()
            result = await loop.run_in_executor(
                None, self.verifier.verify, verify_audio, self._audio_rate
            )
            verify_ms = (time.monotonic() - verify_start) * 1000

        if not result.is_match:
            _LOGGER.debug("[%s] Early verify rejected (%.4f)", sid, result.similarity)
            self._verify_result_cache = result

            # Early reject: immediately return empty transcript so the client
            # (HA / Voice Satellite) stops listening instead of waiting for its
            # max session timeout (~60s of silence).
            if (
                self.early_reject
                and self.require_speaker_match
                and not self._responded
            ):
                self._responded = True
                self._save_rejected_audio(verify_audio, result)
                _LOGGER.info(
                    "[%s] REJECTED early (best=%.4f, threshold=%.2f) — ending session",
                    sid, result.similarity, result.threshold,
                )
                await self.write_event(Transcript(text="").event())
            return

        _LOGGER.info(
            "[%s] Speaker verified: %s (similarity=%.4f)",
            sid, result.matched_speaker, result.similarity,
        )
        self._responded = True
        bps = self._audio_rate * self._audio_width * self._audio_channels

        try:
            await asyncio.wait_for(self._audio_stopped.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            _LOGGER.debug("[%s] AudioStop timeout (30s)", sid)

        full_buffer = bytes(self._audio_buffer)
        buffer_duration = len(full_buffer) / bps if bps else 0
        _LOGGER.debug("[%s] Stream ended: %.1fs buffer", sid, buffer_duration)

        speaker_name = result.matched_speaker
        extract_ms = 0.0
        if speaker_name:
            async with _MODEL_LOCK:
                loop = asyncio.get_running_loop()
                extract_start = time.monotonic()
                forward_audio = await loop.run_in_executor(
                    None,
                    self.verifier.extract_speaker_audio,
                    full_buffer,
                    speaker_name,
                    self._audio_rate,
                )
                extract_ms = (time.monotonic() - extract_start) * 1000
        else:
            forward_audio = full_buffer

        asr_duration = len(forward_audio) / bps if bps else 0
        asr_start = time.monotonic()
        transcript = await self._forward_to_upstream(forward_audio)
        asr_ms = (time.monotonic() - asr_start) * 1000
        tagged = self._tag_transcript(transcript, speaker_name)
        await self.write_event(Transcript(text=tagged).event())
        self._responded = True
        self._log_pipeline_summary(
            tagged, verify_ms, extract_ms, asr_ms, buffer_duration, asr_duration
        )

    async def _process_audio_sync(self) -> None:
        sid = self._session_id
        audio_bytes = self._audio_buffer
        bps = self._audio_rate * self._audio_width * self._audio_channels
        audio_duration = len(audio_bytes) / bps if bps else 0

        if len(audio_bytes) == 0:
            await self.write_event(Transcript(text="").event())
            return

        cached = getattr(self, "_verify_result_cache", None)
        async with _MODEL_LOCK:
            loop = asyncio.get_running_loop()
            verify_start = time.monotonic()
            result = await loop.run_in_executor(
                None, self.verifier.verify, audio_bytes, self._audio_rate
            )
            verify_ms = (time.monotonic() - verify_start) * 1000

        if cached is not None and cached.similarity > result.similarity:
            result = cached

        if result.is_match:
            _LOGGER.info(
                "[%s] Speaker verified: %s (%.4f)",
                sid, result.matched_speaker, result.similarity,
            )
            asr_audio = audio_bytes
            extract_ms = 0.0
            if result.matched_speaker and audio_duration > 3.0:
                async with _MODEL_LOCK:
                    loop = asyncio.get_running_loop()
                    extract_start = time.monotonic()
                    asr_audio = await loop.run_in_executor(
                        None,
                        self.verifier.extract_speaker_audio,
                        audio_bytes,
                        result.matched_speaker,
                        self._audio_rate,
                    )
                    extract_ms = (time.monotonic() - extract_start) * 1000

            asr_forwarded = len(asr_audio) / bps if bps else 0
            asr_start = time.monotonic()
            transcript = await self._forward_to_upstream(asr_audio)
            asr_ms = (time.monotonic() - asr_start) * 1000
            tagged = self._tag_transcript(transcript, result.matched_speaker)
            await self.write_event(Transcript(text=tagged).event())
            self._responded = True
            self._log_pipeline_summary(
                tagged, verify_ms, extract_ms, asr_ms, audio_duration, asr_forwarded
            )
        else:
            self._save_rejected_audio(audio_bytes, result)
            if not self.require_speaker_match:
                transcript = await self._forward_to_upstream(audio_bytes)
                await self.write_event(Transcript(text=transcript).event())
                self._responded = True
            else:
                _LOGGER.info(
                    "[%s] REJECTED (best=%.4f, threshold=%.2f)",
                    sid, result.similarity, result.threshold,
                )
                await self.write_event(Transcript(text="").event())
                self._responded = True

    def _save_rejected_audio(self, audio_bytes: bytes, result: VerificationResult) -> None:
        if not self.save_rejected:
            return
        try:
            self.rejected_dir.mkdir(parents=True, exist_ok=True)
            now = datetime.now(timezone.utc)
            base = f"rejected_{now.strftime('%Y%m%d_%H%M%S')}_{self._session_id}"
            wav_path = self.rejected_dir / f"{base}.wav"
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(self._audio_channels)
                wf.setsampwidth(self._audio_width)
                wf.setframerate(self._audio_rate)
                wf.writeframes(audio_bytes)
            wav_path.write_bytes(buf.getvalue())
            meta = {
                "timestamp": now.isoformat(),
                "best_score": round(result.similarity, 4),
                "threshold": round(result.threshold, 2),
                "all_scores": {k: round(v, 4) for k, v in result.all_scores.items()},
            }
            (self.rejected_dir / f"{base}.json").write_text(json.dumps(meta, indent=2))
        except Exception:
            _LOGGER.exception("[%s] Failed to save rejected audio", self._session_id)

    def _tag_transcript(self, transcript: str, speaker_name: Optional[str]) -> str:
        if self.tag_speaker and speaker_name and transcript:
            return f"[{speaker_name}] {transcript}"
        return transcript

    def _log_pipeline_summary(
        self,
        transcript: str,
        verify_ms: float,
        extract_ms: float,
        asr_ms: float,
        input_duration: float = 0.0,
        output_duration: float = 0.0,
    ) -> None:
        total_ms = self._elapsed_ms()
        _LOGGER.info(
            "[%s] Pipeline: verify=%.0fms extract=%.0fms asr=%.0fms total=%.0fms | %s",
            self._session_id, verify_ms, extract_ms, asr_ms, total_ms, transcript[:80],
        )

    def _elapsed_ms(self) -> float:
        if self._stream_start_time is not None:
            return (time.monotonic() - self._stream_start_time) * 1000
        return 0.0

    async def _forward_to_upstream(self, audio_bytes: bytes) -> str:
        try:
            async with AsyncClient.from_uri(self.upstream_uri) as client:
                await client.write_event(Transcribe(language=self._language).event())
                await client.write_event(
                    AudioStart(
                        rate=self._audio_rate,
                        width=self._audio_width,
                        channels=self._audio_channels,
                    ).event()
                )
                chunk_size = max(
                    (self._audio_rate * self._audio_width * self._audio_channels) // 10, 320
                )
                for offset in range(0, len(audio_bytes), chunk_size):
                    await client.write_event(
                        AudioChunk(
                            audio=audio_bytes[offset : offset + chunk_size],
                            rate=self._audio_rate,
                            width=self._audio_width,
                            channels=self._audio_channels,
                        ).event()
                    )
                await client.write_event(AudioStop().event())
                while True:
                    response = await client.read_event()
                    if response is None:
                        return ""
                    if Transcript.is_type(response.type):
                        return Transcript.from_event(response).text
        except Exception:
            _LOGGER.exception("Upstream ASR error at %s", self.upstream_uri)
            return ""
