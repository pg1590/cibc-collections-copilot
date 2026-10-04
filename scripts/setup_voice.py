"""Download a pinned multilingual Whisper base model for offline CPU use.

Install requirements-voice.txt first. No customer/audio data is uploaded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "Systran/faster-whisper-base"
REVISION = "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"
WEIGHTS_SHA256 = "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"


def setup(verify_only: bool = False) -> Path:
    from faster_whisper import WhisperModel

    destination = Path(os.environ.get("COPILOT_VOICE_MODEL", str(ROOT / "data" / "voice-model")))
    destination.mkdir(parents=True, exist_ok=True)
    if not verify_only:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=MODEL, revision=REVISION, local_dir=str(destination),
                          allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*", "preprocessor_config.json"])
    digest = hashlib.sha256()
    with (destination / "model.bin").open("rb") as source:
        while chunk := source.read(8 * 1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != WEIGHTS_SHA256:
        raise ValueError("Speech model weights failed the publisher checksum.")
    # Verify complete offline loading; this does not transcribe or upload audio.
    model = WhisperModel(str(destination), device="cpu", compute_type="int8", local_files_only=True, cpu_threads=2)
    del model
    provenance = {"model": MODEL, "revision": REVISION, "weights_sha256": WEIGHTS_SHA256,
                  "device": "cpu", "compute_type": "int8", "offline_load_verified": True}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    print(f"Offline CPU speech model ready: {destination}", flush=True)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Verify an existing model entirely offline.")
    args = parser.parse_args()
    setup(verify_only=args.verify_only)
