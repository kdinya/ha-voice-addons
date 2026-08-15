"""Speaker verification using SpeechBrain ECAPA-TDNN with hot-reload."""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import torch
from scipy.spatial.distance import cosine
from speechbrain.inference.speaker import EncoderClassifier

_LOGGER = logging.getLogger("verify")


@dataclass
class VerificationResult:
    is_match: bool
    similarity: float
    threshold: float
    matched_speaker: Optional[str] = None
    all_scores: Dict[str, float] = field(default_factory=dict)
    speech_audio: Optional[bytes] = field(default=None, repr=False)
    speech_start_sec: Optional[float] = None
    speech_end_sec: Optional[float] = None


class SpeakerVerifier:
    """Verifies speaker identity against enrolled voiceprints.

    Supports hot-reload: automatically reloads voiceprints when the
    directory changes on disk (no addon restart needed after enrollment).
    """

    def __init__(
        self,
        voiceprints_dir: str,
        model_dir: str = "/data/models",
        device: str = "cuda",
        threshold: float = 0.30,
        extraction_threshold: float = 0.25,
        max_verify_seconds: float = 5.0,
        window_seconds: float = 3.0,
        step_seconds: float = 1.5,
    ) -> None:
        self.threshold = threshold
        self.extraction_threshold = extraction_threshold
        self.max_verify_seconds = max_verify_seconds
        self.window_seconds = window_seconds
        self.step_seconds = step_seconds

        if device == "cuda" and not torch.cuda.is_available():
            _LOGGER.warning("CUDA requested but not available, falling back to CPU")
            device = "cpu"
        self.device = device

        run_opts = {"device": device} if device == "cuda" else {}
        self.classifier = EncoderClassifier.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir=f"{model_dir}/spkrec-ecapa-voxceleb",
            run_opts=run_opts,
        )

        self.voiceprints: Dict[str, np.ndarray] = {}
        self._voiceprints_dir = voiceprints_dir
        self._vp_mtime: float = 0.0
        self._load_voiceprints(voiceprints_dir)

    def _load_voiceprints(self, voiceprints_dir: str | None = None) -> None:
        if voiceprints_dir is None:
            voiceprints_dir = self._voiceprints_dir
        vp_path = Path(voiceprints_dir)
        self.voiceprints.clear()
        if not vp_path.exists():
            _LOGGER.warning("Voiceprints directory not found: %s", vp_path)
            self._vp_mtime = 0.0
            return

        for npy_file in sorted(vp_path.glob("*.npy")):
            speaker_name = npy_file.stem
            try:
                voiceprint = np.load(str(npy_file))
                self.voiceprints[speaker_name] = voiceprint
                _LOGGER.info("Loaded voiceprint: %s (shape=%s)", speaker_name, voiceprint.shape)
            except Exception as e:
                _LOGGER.warning("Failed to load %s: %s", npy_file, e)

        try:
            self._vp_mtime = vp_path.stat().st_mtime
        except OSError:
            self._vp_mtime = 0.0

        if not self.voiceprints:
            _LOGGER.warning("No voiceprints found in %s", vp_path)

    def reload_voiceprints(self, voiceprints_dir: str | None = None) -> None:
        dir_ = voiceprints_dir or self._voiceprints_dir
        _LOGGER.info("Reloading voiceprints from %s", dir_)
        self._load_voiceprints(dir_)

    def _maybe_reload_voiceprints(self) -> None:
        """Hot-reload if the voiceprints directory has changed on disk."""
        try:
            current = Path(self._voiceprints_dir).stat().st_mtime
        except OSError:
            return
        if current > self._vp_mtime:
            _LOGGER.info("Voiceprints directory changed — hot-reloading")
            self._load_voiceprints()

    def verify(self, audio_bytes: bytes, sample_rate: int = 16000) -> VerificationResult:
        """Verify if audio matches any enrolled speaker."""
        # Hot-reload if enrollment changed (no restart needed)
        self._maybe_reload_voiceprints()

        if not self.voiceprints:
            _LOGGER.warning("No voiceprints enrolled — rejecting audio")
            return VerificationResult(is_match=False, similarity=0.0, threshold=self.threshold)

        embedding = self._extract_embedding(audio_bytes, sample_rate)
        scores: Dict[str, float] = {}
        best_sim = -1.0
        best_speaker = None

        for name, vp in self.voiceprints.items():
            sim = 1.0 - cosine(embedding, vp)
            scores[name] = float(sim)
            if sim > best_sim:
                best_sim = sim
                best_speaker = name

        is_match = best_sim >= self.threshold
        _LOGGER.debug(
            "Verify: best=%s sim=%.3f threshold=%.2f match=%s",
            best_speaker, best_sim, self.threshold, is_match,
        )

        return VerificationResult(
            is_match=is_match,
            similarity=float(best_sim),
            threshold=self.threshold,
            matched_speaker=best_speaker if is_match else None,
            all_scores=scores,
            speech_audio=audio_bytes if is_match else None,
        )

    def extract_embedding(self, audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
        return self._extract_embedding(audio_bytes, sample_rate)

    def _extract_embedding(self, audio_bytes: bytes, sample_rate: int = 16000) -> np.ndarray:
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
        audio_np /= 32768.0
        signal = torch.tensor(audio_np).unsqueeze(0)
        if self.device == "cuda":
            signal = signal.to("cuda")
        with torch.no_grad():
            embedding = self.classifier.encode_batch(signal)
        return embedding.squeeze().cpu().numpy()
