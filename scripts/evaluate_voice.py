"""Small, local whole-call ASR smoke evaluation; not a general accuracy benchmark.

Uses supplied synthetic WAVs and transcript text, writes only ignored data/ output.
No speaker attribution, customer hardship classification or API calls are used.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.features import normalize_text, text_features
from app import voice
from app.voice_worker import transcribe

# Two short mono/stereo calls plus one longer call whose supplied transcript
# contains a financial phrase. This purposive smoke sample is not random.
DEFAULT_IDS = ("VS-11130", "VS-1011114", "VS-3510819")


def words(text: str) -> list[str]:
    # Apply the same redaction-token removal to both hypotheses and references.
    # Actual spoken names remain words; original audio/transcript alignment has
    # not been independently validated and this is explicitly reported below.
    text = re.sub(r"\[(?:redacted|pii|pci)[^\]]*\]|<(?:redacted|pii|pci)[^>]*>", " ", text, flags=re.I)
    return re.findall(r"[a-z0-9]+", normalize_text(text))


def edit_counts(reference: list[str], hypothesis: list[str]) -> dict:
    """Levenshtein path counts; deterministic ties prefer substitution/deletion."""
    previous = [(j, 0, 0, j) for j in range(len(hypothesis) + 1)]
    for i, expected in enumerate(reference, 1):
        current = [(i, 0, i, 0)]
        for j, observed in enumerate(hypothesis, 1):
            if expected == observed:
                current.append(previous[j - 1])
                continue
            cost, substitutions, deletions, insertions = previous[j - 1]
            choices = [(cost + 1, substitutions + 1, deletions, insertions)]
            cost, substitutions, deletions, insertions = previous[j]
            choices.append((cost + 1, substitutions, deletions + 1, insertions))
            cost, substitutions, deletions, insertions = current[j - 1]
            choices.append((cost + 1, substitutions, deletions, insertions + 1))
            current.append(min(choices, key=lambda item: item[0]))
        previous = current
    errors, substitutions, deletions, insertions = previous[-1]
    return {"substitutions": substitutions, "deletions": deletions, "insertions": insertions,
            "word_errors": errors, "reference_words": len(reference), "hypothesis_words": len(hypothesis),
            "word_error_rate": errors / len(reference) if reference else None}


def evaluate(ids: list[str], output: Path, cache: bool = True) -> dict:
    if not voice.speech_available():
        raise RuntimeError("Install requirements-voice.txt and run scripts/setup_voice.py before evaluation.")
    release = Path(os.environ.get("COPILOT_DATASET", str(ROOT / "data/maple_collections_release"))).resolve()
    with (release / "data/voice_samples.csv").open(newline="", encoding="utf-8-sig") as source:
        samples = {row["voice_sample_id"]: row for row in csv.DictReader(source)}
    with (release / "data/call_transcripts.csv").open(newline="", encoding="utf-8-sig") as source:
        transcripts = {row["transcript_id"]: row for row in csv.DictReader(source)}
    results = []
    model_digest = voice.model_fingerprint()
    for identifier in ids:
        source = dict(samples[identifier])
        source["file_size_bytes"] = int(source["file_size_bytes"])
        audio, _, checksum, duration = voice.verified_audio(release, source)
        transcript_path = (release / "files" / transcripts[source["transcript_id"]]["file_path"]).resolve()
        if not transcript_path.is_relative_to(release / "files/transcripts"):
            raise ValueError("Reference transcript path is outside the source folder.")
        supplied = json.loads(transcript_path.read_text(encoding="utf-8"))
        reference = " ".join(str(turn.get("text", "")) for turn in supplied.get("turns", []))
        cache_path = voice.CACHE / (voice.cache_key(checksum) + ".json")
        cached = voice._read_result(cache_path, checksum, model_digest) if cache else None
        result = cached or transcribe(audio, voice.MODEL, checksum, model_digest)
        if cache and not cached:
            voice.CACHE.mkdir(parents=True, exist_ok=True)
            temporary = cache_path.with_suffix(".eval.tmp")
            temporary.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
            if voice._read_result(temporary, checksum, model_digest) is None:
                temporary.unlink(missing_ok=True)
                raise ValueError("Transcription result fails the live cache schema.")
            temporary.replace(cache_path)
        reference_cues, hypothesis_cues = text_features(reference), text_features(result["text"])
        record = {"voice_sample_id": identifier, "channels": int(source["channels"]),
                  "duration_sec": duration, "processing_seconds": result["processing_seconds"],
                  "used_cached_result": bool(cached), "detected_language": result["language"],
                  "source_sha256": checksum, **edit_counts(words(reference), words(result["text"])),
                  "whole_call_reference_cues": reference_cues, "whole_call_asr_cues": hypothesis_cues,
                  "cue_vector_equal": reference_cues == hypothesis_cues,
                  "serving_feature_parity": result["features"] == hypothesis_cues}
        results.append(record)
        print(f"{identifier}: WER={record['word_error_rate']}, processing={record['processing_seconds']:.2f}s", flush=True)
    reference_words = sum(row["reference_words"] for row in results)
    report = {"scope": "Exploratory whole-call transcription of a tiny deterministic synthetic English TTS sample.",
              "limitations": ["Supplied audio/transcript word alignment is not independently validated.",
                              "Default samples intentionally cover mono/stereo and a financial phrase; they are not random.",
                              "No speaker attribution; cues may describe agent speech and are not customer decisions.",
                              "This sample is not a held-out, representative ASR accuracy benchmark."],
              "normalization": "Accent-insensitive lowercase a-z/0-9 words; known redaction markers removed identically.",
              "model_sha256": model_digest, "feature_version": voice.VERSION,
              "sample_count": len(results), "samples": results,
              "pooled_word_error_rate": sum(row["word_errors"] for row in results) / reference_words if reference_words else None,
              "serving_feature_parity_mismatches": sum(not row["serving_feature_parity"] for row in results)}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Local evaluation written to {output}", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ids", nargs="+", default=list(DEFAULT_IDS))
    parser.add_argument("--output", type=Path, default=ROOT / "data/voice-evaluation.json")
    parser.add_argument("--no-cache", action="store_true")
    args = parser.parse_args()
    evaluate(args.ids, args.output, cache=not args.no_cache)
