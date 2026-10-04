# Voice processing and verification

The optional audio pack is now used for actual playback and local speech-to-text. Provided transcript summaries remain a separate evidence source. Audio recognition does not read those transcript files to produce its answer.

## Processing path

1. Resolve a recording through its supplied voice/transcript/contact IDs and a linked C360 case. Confirm that the transcript CRM identity maps to the same customer. Agents can access only their assigned case recordings.
2. Validate the recording path, bounded WAV bytes, publisher checksum, PCM16 frames and duration.
3. Run the pinned multilingual Whisper base model through faster-whisper 1.2.1, on CPU with int8 precision and two threads. Runtime processing is offline and loads an explicit local model directory.
4. Cache recognized words, approximate timestamps, actual audio/model hashes and versioned financial cue candidates. Both offline evaluation and live processing call `app.features.text_features`.
5. Present audio and machine text for human inspection. Speakers are not attributed. The existing note classifier and customer decisions are unchanged.

The model and source audio are downloaded once, never committed. A worker processes one job at a time, with four active jobs maximum and a three-minute processing timeout. Job state is process-local; use one backend process.

## Measured source checks

| Check | Result | Handling |
|---|---:|---|
| Official archive SHA-256 | Matches publisher | Pinned revision and provenance retained locally |
| Per-recording size and SHA-256 | 2,000 checked; zero mismatches | Verified before extracting each WAV |
| Voice/transcript/contact linkage | 2,000 agree | Mismatched identifiers would be excluded |
| Verified golden case/customer linkage | 1,944 recordings | Serve only these recordings |
| Recordings lacking a golden case link | 56 | Preserve source audio; exclude from customer access until identity resolution |
| Local model weight checksum and offline load | Passed | No implicit runtime download |

All 56 excluded recordings reference an existing source case but lack a linked golden case. They are not missing audio files. Full WAV frame validation is performed on access; the download verification covers all file sizes and checksums.

## Small speech-recognition comparison

`scripts/evaluate_voice.py` compares three actual WAVs with the provided whole-call transcript words. This purposive sample covers mono/stereo and a financial phrase; it is not random or representative. Word normalization removes known redaction markers equally and uses accent-insensitive lowercase words. Audio/transcript alignment has not been independently labelled.

| Recording | Duration | Processing time | Word errors / reference words | Word-error rate |
|---|---:|---:|---:|---:|
| VS-11130 | 15 s | 1.753 s | 6 / 36 | 16.67% |
| VS-1011114 | 15 s | 1.542 s | 4 / 36 | 11.11% |
| VS-3510819 | 53 s | 2.730 s | 29 / 105 | 27.62% |

Pooled word-error rate: **39 / 177 = 22.03%**. The six cue flags match the whole-call reference vectors on these three examples, and live/offline cue calculation has zero mismatches. Neither result establishes customer-only attribution, broad accuracy or hardship-classifier performance. Existing note-model evaluation remains separate.

A fourth recording, `VS-1011165`, passed authenticated playback and a fresh queued-to-completed recognition job through the Next.js API proxy. Its source hash matched; the worker recognized 14 segments in 3.318 seconds and produced an unverified income-delay cue candidate. This is an integration check, not an additional scored accuracy example.

Generated text is displayed as machine evidence with human review required. Agent speech, negation and transcription errors can trigger cue candidates. No protected acoustic/accent attributes, voice sentiment or voice-derived customer score is used.

## Reproduce

```bash
.venv/bin/python -m pip install -r requirements-voice.txt
.venv/bin/python scripts/fetch_voice.py
.venv/bin/python scripts/setup_voice.py
HF_HUB_OFFLINE=1 .venv/bin/python scripts/setup_voice.py --verify-only
HF_HUB_OFFLINE=1 .venv/bin/python scripts/evaluate_voice.py
```

Ignored evidence files: `data/voice-provenance.json`, `data/voice-model/provenance.json`, `data/voice-evaluation.json` and `data/voice-transcriptions/`. Automated coverage includes case access, corrupted audio, invalid paths, missing model, queue deduplication/bounds, malformed cache, shared cues and worker timeout. See the actual Claude source review in `docs/reviews/voice-integration-review.md`.
