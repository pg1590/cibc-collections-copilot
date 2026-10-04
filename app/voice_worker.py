"""CPU speech recognition worker: audio is decoded locally, without cloud calls."""
import argparse
import hashlib
import io
import json
import time
import wave
from pathlib import Path

from app.voice import MAX_AUDIO_BYTES, MAX_DURATION, result_payload


def transcribe(audio, model, checksum, model_digest):
    from faster_whisper import WhisperModel

    audio = Path(audio)
    with audio.open('rb') as stream:
        content = stream.read(MAX_AUDIO_BYTES + 1)
    if not 44 <= len(content) <= MAX_AUDIO_BYTES or hashlib.sha256(content).hexdigest() != checksum:
        raise ValueError('Audio changed after validation.')
    with wave.open(io.BytesIO(content), 'rb') as wav:
        duration = wav.getnframes() / wav.getframerate()
    if not 0 < duration <= MAX_DURATION:
        raise ValueError('Unsupported audio duration.')
    started = time.perf_counter()
    engine = WhisperModel(str(model), device='cpu', compute_type='int8', cpu_threads=2, num_workers=1, local_files_only=True)
    # VAD reduces silence hallucinations; original audio timestamps are retained.
    generated, info = engine.transcribe(io.BytesIO(content), beam_size=5, vad_filter=True, condition_on_previous_text=False)
    segments = [{'start': round(segment.start, 3), 'end': round(segment.end, 3), 'text': segment.text.strip()}
                for segment in generated if segment.text.strip()]
    return result_payload(' '.join(segment['text'] for segment in segments), segments, checksum=checksum,
                          model_digest=model_digest, language=info.language,
                          language_probability=round(info.language_probability, 4), duration=duration,
                          processing_seconds=time.perf_counter() - started)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--checksum', required=True)
    parser.add_argument('--model-sha256', required=True)
    args = parser.parse_args()
    result = transcribe(args.audio, args.model, args.checksum, args.model_sha256)
    args.output.write_text(json.dumps(result, ensure_ascii=False), encoding='utf-8')
