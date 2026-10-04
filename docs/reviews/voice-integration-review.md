# Voice integration review

Reviewed 4 October 2026. The user requested audio processing and previously requested Claude input on integrations. Claude Code was invoked with `claude-opus-5-5`, `--effort high`, and all tools disabled. Response metadata confirms only `claude-opus-5-5`, successful completion and no permission denials. The review received the proposed plan and relevant source snippets only; audio, raw customer datasets and credentials were excluded. Raw prompts/responses are ignored local review files.

## Accepted implementation boundaries

- Optional official synthetic WAV pack and an explicitly downloaded local multilingual speech recognition model; runtime inference must not download a model or call a paid API.
- Recording lookup uses publisher metadata and the existing customer access check. Playback, transcription and result reads require bearer authentication and authorization; filenames or paths are never supplied by the client.
- Audio is validated and checked against the publisher checksum before inference. Path containment, file limits, PCM format, duration and actual frame length are checked.
- One bounded background worker deduplicates jobs. Cached output identifies the audio, model artifact and inference configuration; result reads recheck authorization and corrupt cache entries are discarded.
- Machine transcripts show approximate segment timestamps. Financial phrase findings use the shared feature definitions but remain unverified, speaker-unknown review prompts. They do not update customer hardship status, model scores, eligibility, contact recommendations or existing briefs.
- Synthetic audio, provided transcript and machine-generated transcript are distinct sources. Speech recognition accuracy remains unmeasured until a defined comparison is performed.

## Review findings to verify

1. The demo agent scope currently maps to a configured or default agent identity, not individual employee identities. Reject unknown roles and explain this limitation; do not claim production employee access mapping.
2. Every recording operation must authorize the manifest-resolved customer, including status and cached transcript reads. Use identical not-found responses for inaccessible recordings.
3. Hash, validate and decode the same bounded audio bytes, avoiding a checksum/read race. Verify path containment and reject symlinks.
4. Load the model only from the explicit local artifact directory. A model name alone may initiate an implicit download.
5. Include decoding configuration and feature version in cached findings. Validate cached schema and identifier; write atomically.
6. Return promptly when the queue is full; use one model instance and no shared request database connection in the worker.
7. Agent speech, negation and ASR errors can trigger keyword findings. Label each phrase unverified with unknown speaker and approximate timestamps; do not treat duplication across sources as independent confirmation.
8. Audio responses should use `Cache-Control: no-store` and `X-Content-Type-Options: nosniff`. Revoke browser audio object URLs. Audit metadata must exclude transcript text and local paths.

## Verification status

Initial review is advisory and did not run tests. The final actual-Claude source review also completed successfully with `claude-opus-5-5` and high effort; metadata was verified. Its unknown-role, completed-read audit, checksum normalization and malformed-cache findings were fixed. Local models are explicitly configured artifacts; the default base weights were verified by the setup script. One backend worker is an explicit prototype limit. Minimum verification covers authentication and scope, invalid paths and WAVs, checksum tampering, missing local model without network access, deduplication/queue bounds, cache corruption, unverified cue attribution and unchanged existing decision outputs.

Independent verification: 210 full-suite tests pass; actual offline model loading passed. All 2,000 source WAV sizes/checksums match. Three real recognition comparisons and a fourth fresh HTTP job passed. See `docs/voice-verification.md` for error rates and limitations; code review itself did not execute checks.
