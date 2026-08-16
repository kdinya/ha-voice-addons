"""Wyoming event handler for speaker-verified ASR proxy."""

import asyncio
import io
import json
import logging
import os
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.client import AsyncClient
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

from .verify import SpeakerVerifier, VerificationResult

_LOGGER = logging.getLogger("handler")

_MODEL_LOCK = asyncio.Lock()


def _env_bool(name: str, default: bool = True) -> bool:
    return os.environ.get(name, str(default)).lower() in ("true", "1", "yes")


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(float(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


class SpeakerVerifyHandler(AsyncEventHandler):
    """Wyoming ASR handler that gates transcription on speaker identity.

    Listening duration is owned entirely by the client (Voice Satellite /
    Kiosk VAD). This handler only buffers audio until AudioStop, then
    verifies the speaker and optionally forwards to upstream STT.

    Configurable fast-path (2.0.9) returns empty Transcript quickly on
    near-silence so the client is not held by slow verification.
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
        self._audio_buffer = bytes()
        self._audio_rate: int = 16000
        self._audio_width: int = 2
        self._audio_channels: int = 1
        self._language: Optional[str] = None
        self._responded: bool = False
        self._stream_start_time: Optional[float] = None
        self._session_id: str = uuid.uuid4().hex[:8]
        self._heard_speech: bool = False
        self._last_early_check_bytes: int = 0

        # Configurable silence controls (each can be disabled)
        self.silence_threshold_enabled = _env_bool("SILENCE_THRESHOLD_ENABLED", True)
        self.silence_threshold = _env_int("SILENCE_THRESHOLD", 180)
        self.silence_timeout_enabled = _env_bool("SILENCE_TIMEOUT_ENABLED", True)
        self.silence_timeout = _env_float("SILENCE_TIMEOUT", 2.0)
        self.min_speech_duration_enabled = _env_bool("MIN_SPEECH_DURATION_ENABLED", True)
        self.min_speech_duration = _env_float("MIN_SPEECH_DURATION", 1.0)
        # Early empty Transcript during stream (before client AudioStop) so
        # Voice Satellite does not wait for LLM/TTS on pure silence.
        self.early_endpoint_enabled = _env_bool("EARLY_ENDPOINT_ENABLED", True)

    async def handle_event(self, event: Event) -> bool:
        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info.event())
            return True
        if Transcribe.is_type(event.type):
            self._language = Transcribe.from_event(event).language
            return True
        if AudioStart.is_type(event.type):
            self._audio_buffer = bytes()
            self._responded = False
            self._stream_start_time = time.monotonic()
            self._session_id = uuid.uuid4().hex[:8]
            self._heard_speech = False
            self._last_early_check_bytes = 0
            _LOGGER.info("[%s] -- New audio session started --", self._session_id)
            return True
        if AudioChunk.is_type(event.type):
            if self._responded:
                return True
            chunk = AudioChunk.from_event(event)
            self._audio_rate = chunk.rate
            self._audio_width = chunk.width
            self._audio_channels = chunk.channels
            self._audio_buffer += chunk.audio
            await self._maybe_early_endpoint()
            return True
        if AudioStop.is_type(event.type):
            if self._responded:
                return True
            await self._process_audio()
            return True
        return True

    def _buffer_duration(self) -> float:
        bps = self._audio_rate * self._audio_width * self._audio_channels
        if bps <= 0:
            return 0.0
        return len(self._audio_buffer) / bps

    async def _maybe_early_endpoint(self) -> None:
        """If the stream is still silence/cough long enough, send empty Transcript now.

        Home Assistant / Voice Satellite VAD often holds STT for ~15s (stt-vad-end
        timestamp=15000). Early empty Transcript ends the pipeline without waiting
        for AI/TTS. Real speech still waits for client AudioStop.

        Important: do NOT treat a single peak spike (click, cough) as speech —
        that was blocking early-endpoint in 2.0.13.
        """
        if self._responded or not self.early_endpoint_enabled:
            return
        if not self.silence_threshold_enabled and not self.silence_timeout_enabled:
            return

        # Throttle: check about every 0.25 s of new audio
        bps = self._audio_rate * self._audio_width * self._audio_channels
        min_bytes = max(int(bps * 0.25), 1)
        if len(self._audio_buffer) - self._last_early_check_bytes < min_bytes:
            return
        self._last_early_check_bytes = len(self._audio_buffer)

        duration = self._buffer_duration()
        need = self.silence_timeout if self.silence_timeout_enabled else 2.0
        need = max(need, 1.5)
        if duration < need:
            return

        stats = self._audio_stats(bytes(self._audio_buffer), self._audio_rate)
        thr = float(self.silence_threshold) if self.silence_threshold_enabled else 180.0
        peak = stats["peak"]
        mean = stats.get("mean", peak)
        quiet_ratio = stats.get("quiet_ratio", 0.0)
        p90 = stats.get("p90", peak)

        # Sustained speech only (mean high OR majority of frames not quiet).
        # Peak alone is ignored — cough/click must not disable early-endpoint.
        if mean >= thr * 3.0 or quiet_ratio < 0.55:
            if not self._heard_speech:
                _LOGGER.debug(
                    "[%s] Early-endpoint: speech locked (mean=%.0f quiet=%.0f%%) — wait AudioStop",
                    self._session_id, mean, quiet_ratio * 100,
                )
            self._heard_speech = True
            return

        if self._heard_speech:
            return

        # Same criteria as post-AudioStop fast-reject
        reject, reason = self._should_fast_reject(stats)
        if not reject:
            return

        sid = self._session_id
        self._responded = True
        _LOGGER.info(
            "[%s] Early-endpoint: %s (%.1fs peak=%.0f mean=%.0f p90=%.0f quiet=%.0f%% thr=%.0f) "
            "— empty transcript (client still streaming)",
            sid, reason, duration, peak, mean, p90, quiet_ratio * 100, thr,
        )
        await self.write_event(Transcript(text="").event())

    def _audio_stats(self, audio_bytes: bytes, sample_rate: int) -> dict:
        """Return duration, peak/mean RMS and quiet-frame ratio for the buffer.

        RMS is computed on int16 samples in 50 ms frames (server scale ~50–8000+).
        This is NOT the same scale as the browser silence meter in the Web UI.
        """
        bps = sample_rate * 2
        duration = len(audio_bytes) / bps if bps else 0.0
        empty = {
            "duration": duration, "peak": 0.0, "mean": 0.0,
            "p90": 0.0, "quiet_ratio": 1.0, "num_frames": 0,
        }
        if len(audio_bytes) < sample_rate // 10:  # < 0.1 s
            return empty

        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        frame_samples = max(int(sample_rate * 0.05), 1)
        num_frames = len(audio_np) // frame_samples
        if num_frames < 1:
            peak = float(np.max(np.abs(audio_np))) if len(audio_np) else 0.0
            return {
                "duration": duration, "peak": peak, "mean": peak,
                "p90": peak, "quiet_ratio": 1.0 if peak < 180 else 0.0,
                "num_frames": 1,
            }

        frames = audio_np[: num_frames * frame_samples].reshape(num_frames, frame_samples)
        rms = np.sqrt(np.mean(frames ** 2, axis=1))
        thr = float(self.silence_threshold) if self.silence_threshold_enabled else 180.0
        quiet_ratio = float(np.mean(rms < thr))
        return {
            "duration": duration,
            "peak": float(np.max(rms)),
            "mean": float(np.mean(rms)),
            "p90": float(np.percentile(rms, 90)),
            "quiet_ratio": quiet_ratio,
            "num_frames": int(num_frames),
        }

    def _should_fast_reject(self, stats: dict) -> tuple[bool, str]:
        """Decide whether to return empty Transcript without full verify.

        Uses mean / p90 / quiet-frame ratio so a single click does not force
        a full ECAPA pass on an otherwise silent buffer.
        """
        duration = stats["duration"]
        peak = stats["peak"]
        mean = stats.get("mean", peak)
        p90 = stats.get("p90", peak)
        quiet_ratio = stats.get("quiet_ratio", 0.0)

        # Rule 1: min speech duration
        if self.min_speech_duration_enabled and duration < self.min_speech_duration:
            return True, f"too short ({duration:.1f}s < {self.min_speech_duration}s)"

        if not self.silence_threshold_enabled:
            return False, ""

        thr = float(self.silence_threshold)

        # Rule 2: whole buffer is quiet by peak
        if peak < thr:
            return True, f"near-silence (peak={peak:.0f} < {thr:.0f})"

        # Rule 3: average energy is below threshold (long silence with rare spikes)
        if mean < thr:
            return True, (
                f"near-silence mean (mean={mean:.0f} < {thr:.0f}, "
                f"peak={peak:.0f}, quiet={quiet_ratio:.0%})"
            )

        # Rule 4: most frames are quiet (e.g. 85%+ below threshold) — ambient only
        if quiet_ratio >= 0.85 and p90 < thr * 2.5:
            return True, (
                f"mostly-quiet frames (quiet={quiet_ratio:.0%}, "
                f"p90={p90:.0f}, peak={peak:.0f}, thr={thr:.0f})"
            )

        # Rule 5: short buffer within silence_timeout with soft energy
        if self.silence_timeout_enabled and duration <= self.silence_timeout:
            soft_limit = thr * 2
            if peak < soft_limit or mean < thr * 1.5:
                return True, (
                    f"silence timeout ({duration:.1f}s <= {self.silence_timeout}s, "
                    f"peak={peak:.0f}, mean={mean:.0f})"
                )

        return False, ""

    async def _process_audio(self) -> None:
        """Verify speaker and forward to STT after client ends the stream."""
        sid = self._session_id
        if self._responded:
            return
        self._responded = True

        audio_bytes = bytes(self._audio_buffer)
        bps = self._audio_rate * self._audio_width * self._audio_channels
        audio_duration = len(audio_bytes) / bps if bps else 0.0

        if len(audio_bytes) == 0:
            _LOGGER.debug("[%s] Empty audio buffer — returning empty transcript", sid)
            await self.write_event(Transcript(text="").event())
            return

        stats = self._audio_stats(audio_bytes, self._audio_rate)
        reject, reason = self._should_fast_reject(stats)

        if reject:
            _LOGGER.info(
                "[%s] Fast-reject: %s (duration=%.1fs peak=%.0f mean=%.0f) — empty transcript",
                sid, reason, stats["duration"], stats["peak"], stats.get("mean", 0.0),
            )
            await self.write_event(Transcript(text="").event())
            return

        # Always log energy so user can calibrate silence_threshold from real server scale
        _LOGGER.info(
            "[%s] AudioStop — %.1fs peak=%.0f mean=%.0f p90=%.0f quiet=%.0f%% thr=%d → verifying",
            sid,
            audio_duration,
            stats["peak"],
            stats.get("mean", 0.0),
            stats.get("p90", 0.0),
            stats.get("quiet_ratio", 0.0) * 100,
            self.silence_threshold,
        )

        async with _MODEL_LOCK:
            loop = asyncio.get_running_loop()
            verify_start = time.monotonic()
            result = await loop.run_in_executor(
                None, self.verifier.verify, audio_bytes, self._audio_rate
            )
            verify_ms = (time.monotonic() - verify_start) * 1000

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

            asr_forwarded = len(asr_audio) / bps if bps else 0.0
            asr_start = time.monotonic()
            transcript = await self._forward_to_upstream(asr_audio)
            asr_ms = (time.monotonic() - asr_start) * 1000
            tagged = self._tag_transcript(transcript, result.matched_speaker)
            await self.write_event(Transcript(text=tagged).event())
            self._log_pipeline_summary(
                tagged, verify_ms, extract_ms, asr_ms, audio_duration, asr_forwarded
            )
        else:
            self._save_rejected_audio(audio_bytes, result)
            if not self.require_speaker_match:
                transcript = await self._forward_to_upstream(audio_bytes)
                await self.write_event(Transcript(text=transcript).event())
                _LOGGER.info("[%s] No match — forwarded (require_speaker_match=false)", sid)
            else:
                _LOGGER.info(
                    "[%s] REJECTED (best=%.4f, threshold=%.2f)",
                    sid, result.similarity, result.threshold,
                )
                await self.write_event(Transcript(text="").event())

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
