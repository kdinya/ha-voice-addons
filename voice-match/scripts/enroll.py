"""Enrollment script — generate a voiceprint from WAV samples.

Usage:
    python -m scripts.enroll --speaker NAME
    python -m scripts.enroll --list
    python -m scripts.enroll --delete NAME
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import torch
import soundfile as sf
import torchaudio
from speechbrain.inference.speaker import EncoderClassifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_LOGGER = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".flac", ".ogg", ".mp3"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Enroll speaker voice samples")
    parser.add_argument("--speaker", help="Speaker name to enroll")
    parser.add_argument("--list", action="store_true", help="List enrolled speakers")
    parser.add_argument("--delete", metavar="NAME", help="Delete a voiceprint")
    parser.add_argument("--enrollment-dir", default=os.environ.get("ENROLLMENT_DIR", "/data/enrollment"))
    parser.add_argument("--voiceprints-dir", default=os.environ.get("VOICEPRINTS_DIR", "/data/voiceprints"))
    parser.add_argument("--model-dir", default=os.environ.get("MODEL_DIR", "/data/models"))
    args = parser.parse_args()

    if args.list:
        vp_dir = Path(args.voiceprints_dir)
        if vp_dir.exists():
            for f in sorted(vp_dir.glob("*.npy")):
                print(f.stem)
        return

    if args.delete:
        vp = Path(args.voiceprints_dir) / f"{args.delete}.npy"
        if vp.exists():
            vp.unlink()
            print(f"Deleted {vp}")
        else:
            print(f"Not found: {vp}")
        return

    if not args.speaker:
        parser.error("--speaker is required (or use --list / --delete)")

    speaker_dir = Path(args.enrollment_dir) / args.speaker
    if not speaker_dir.exists():
        _LOGGER.error("Enrollment directory not found: %s", speaker_dir)
        sys.exit(1)

    files = [
        f for f in sorted(speaker_dir.iterdir())
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if not files:
        _LOGGER.error("No audio files found in %s", speaker_dir)
        sys.exit(1)

    _LOGGER.info("Loading ECAPA-TDNN model (CPU)...")
    classifier = EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=f"{args.model_dir}/spkrec-ecapa-voxceleb",
    )

    embeddings = []
    for audio_file in files:
        _LOGGER.info("Processing %s", audio_file.name)
        try:
            signal, sr = sf.read(str(audio_file), dtype="float32")
            if signal.ndim > 1:
                signal = signal.mean(axis=1)
            if sr != 16000:
                signal = torchaudio.functional.resample(
                    torch.tensor(signal).unsqueeze(0), sr, 16000
                ).squeeze(0).numpy()
            tensor = torch.tensor(signal).unsqueeze(0)
            with torch.no_grad():
                emb = classifier.encode_batch(tensor)
            embeddings.append(emb.squeeze().cpu().numpy())
        except Exception as e:
            _LOGGER.warning("Failed to process %s: %s", audio_file.name, e)

    if not embeddings:
        _LOGGER.error("No embeddings extracted")
        sys.exit(1)

    voiceprint = np.mean(embeddings, axis=0)
    out_dir = Path(args.voiceprints_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.speaker}.npy"
    np.save(str(out_path), voiceprint)
    _LOGGER.info("Saved voiceprint: %s (shape=%s, from %d samples)", out_path, voiceprint.shape, len(embeddings))


if __name__ == "__main__":
    main()
