"""Verified source audio and bounded, local, review-only speech transcription.

The HTTP layer authorizes a case before calling this module. No supplied transcript
is substituted for speech recognition. ASR financial cues have no speaker attribution
and never enter the existing customer classifier or contact/eligibility decisions.
"""
import hashlib
import importlib.util
import io
import json
import math
import os
import re
import subprocess
import sys
import threading
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from app.features import VERSION, text_features
from app.settings import ROOT

MAX_AUDIO_BYTES = 16 * 1024 * 1024
MAX_DURATION = 600
MAX_ACTIVE = 4
MAX_RESULT_BYTES = 1024 * 1024
CACHE = ROOT / 'data/voice-transcriptions'
MODEL = Path(os.getenv('COPILOT_VOICE_MODEL', ROOT / 'data/voice-model')).resolve()
MODEL_FILES = ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt')
ASR_VERSION = 'voice-asr-v1'


class VoiceError(ValueError):
    pass


def audio_path(dataset_root, source):
    """Confine files to the supplied voice pack, excluding symlink escapes."""
    identifier = str(source.get('voice_sample_id', ''))
    if not re.fullmatch(r'VS-\d+', identifier):
        raise VoiceError('Invalid recording identifier.')
    allowed = (Path(dataset_root) / 'files/voice').resolve()
    path = (Path(dataset_root) / 'files' / str(source.get('file_path', ''))).resolve()
    if not path.is_relative_to(allowed) or path.name != identifier + '.wav':
        raise VoiceError('Recording path is outside the voice pack.')
    return path


def audio_available(dataset_root, source):
    try:
        path = audio_path(dataset_root, source)
        return path.is_file() and 44 <= path.stat().st_size <= MAX_AUDIO_BYTES
    except (VoiceError, OSError):
        return False


def verified_audio(dataset_root, source):
    path = audio_path(dataset_root, source)
    if not path.is_file():
        raise FileNotFoundError('Optional voice pack is not installed.')
    size = path.stat().st_size
    expected_size = source.get('file_size_bytes')
    if size < 44 or size > MAX_AUDIO_BYTES or size != expected_size:
        raise VoiceError('Recording size does not match its source metadata.')
    checksum = str(source.get('checksum_sha256', '')).lower()
    if not re.fullmatch(r'[0-9a-f]{64}', checksum):
        raise VoiceError('The recording has no valid source checksum.')
    with path.open('rb') as stream:
        content = stream.read(MAX_AUDIO_BYTES + 1)
    if len(content) != size or hashlib.sha256(content).hexdigest() != checksum:
        raise VoiceError('Recording checksum does not match the supplied dataset.')
    try:
        with wave.open(io.BytesIO(content), 'rb') as wav:
            duration = wav.getnframes() / wav.getframerate()
            if wav.getcomptype() != 'NONE' or wav.getsampwidth() != 2 or wav.getnchannels() not in (1, 2):
                raise VoiceError('Only the supplied mono/stereo PCM16 WAV files are supported.')
            if not 8000 <= wav.getframerate() <= 48000 or not 0 < duration <= MAX_DURATION:
                raise VoiceError('Recording sample rate or duration is unsupported.')
            if len(wav.readframes(wav.getnframes())) != wav.getnframes() * wav.getnchannels() * wav.getsampwidth():
                raise VoiceError('The recording PCM frame data is truncated.')
            if abs(duration - float(source['duration_sec'])) > 1:
                raise VoiceError('Recording duration does not match its source metadata.')
    except (wave.Error, EOFError, ZeroDivisionError, KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, VoiceError):
            raise
        raise VoiceError('The recording is not a valid supplied WAV file.') from exc
    return path, content, checksum, duration


def speech_available():
    required = ('faster_whisper', 'av', 'ctranslate2', 'onnxruntime', 'tokenizers', 'huggingface_hub')
    return all((MODEL / name).is_file() for name in MODEL_FILES) and all(importlib.util.find_spec(name) is not None for name in required)


def model_fingerprint():
    """Hash model artifacts once per observed size/mtime change, never a remote name."""
    global _model_signature, _model_digest
    try:
        signature = (str(MODEL),) + tuple((name, (MODEL / name).stat().st_size, (MODEL / name).stat().st_mtime_ns) for name in MODEL_FILES)
    except OSError as exc:
        raise RuntimeError('Local speech model is incomplete.') from exc
    with _fingerprint_lock:
        if signature != _model_signature:
            digest = hashlib.sha256()
            for name in MODEL_FILES:
                digest.update(name.encode())
                try:
                    with (MODEL / name).open('rb') as stream:
                        while chunk := stream.read(1024 * 1024):
                            digest.update(chunk)
                except OSError as exc:
                    raise RuntimeError('Local speech model is incomplete.') from exc
            _model_signature, _model_digest = signature, digest.hexdigest()
        return _model_digest


_fingerprint_lock = threading.Lock()
_model_signature = None
_model_digest = None
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='local-speech')
_jobs = {}


def cache_key(checksum):
    # The exact feature implementation participates so changed definitions cannot
    # silently reuse an old feature vector under the same nominal version.
    features_digest = hashlib.sha256((ROOT / 'app/features.py').read_bytes()).hexdigest()
    decoder_digest = hashlib.sha256((ROOT / 'app/voice_worker.py').read_bytes()).hexdigest()
    return hashlib.sha256(f'{ASR_VERSION}:{checksum}:{model_fingerprint()}:{decoder_digest}:{VERSION}:{features_digest}'.encode()).hexdigest()


def _read_result(path, checksum, model_digest):
    try:
        if not path.is_file() or path.stat().st_size > MAX_RESULT_BYTES:
            return None
        result = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(result, dict) or not isinstance(result.get('text'), str) or not isinstance(result.get('segments'), list):
            return None
        if len(result['text']) > 100000 or len(result['segments']) > 2000:
            return None
        if result['source_sha256'] != checksum or result['model_sha256'] != model_digest or result['asr_version'] != ASR_VERSION:
            return None
        if result['features'] != text_features(result['text']) or result['feature_version'] != VERSION:
            return None
        if result['speaker_attribution'] != 'unavailable' or result['review_required'] is not True:
            return None
        duration = float(result['duration_sec'])
        processing = float(result['processing_seconds'])
        probability = float(result['language_probability'])
        if not math.isfinite(duration + processing + probability) or not 0 < duration <= MAX_DURATION or processing < 0 or not 0 <= probability <= 1:
            return None
        if not isinstance(result['language'], str) or not re.fullmatch(r'[a-z]{2,3}', result['language']):
            return None
        for segment in result['segments']:
            start, end = float(segment['start']), float(segment['end'])
            if not isinstance(segment['text'], str) or not math.isfinite(start + end) or not 0 <= start <= end <= duration + 1:
                return None
        if result['text'] != ' '.join(segment['text'] for segment in result['segments']):
            return None
        return result
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        return None


def transcription_status(source):
    if not speech_available():
        return {'status': 'not_started'}
    checksum = str(source.get('checksum_sha256', '')).lower()
    key = cache_key(checksum)
    cached = _read_result(CACHE / (key + '.json'), checksum, model_fingerprint())
    if cached:
        return {'status': 'completed', 'transcript': cached}
    with _lock:
        return dict(_jobs.get(key, {'status': 'not_started'}))


def start_transcription(dataset_root, source):
    if not speech_available():
        raise RuntimeError('Install requirements-voice.txt and run scripts/setup_voice.py first.')
    path, _, checksum, duration = verified_audio(dataset_root, source)
    key = cache_key(checksum)
    cached = _read_result(CACHE / (key + '.json'), checksum, model_fingerprint())
    if cached:
        return {'status': 'completed', 'transcript': cached}
    with _lock:
        current = _jobs.get(key)
        if current and current['status'] in ('queued', 'running'):
            return dict(current)
        if sum(job['status'] in ('queued', 'running') for job in _jobs.values()) >= MAX_ACTIVE:
            raise OverflowError('The local transcription queue is full. Try again after a job finishes.')
        if len(_jobs) >= 128:
            for expired in [name for name, job in _jobs.items() if job['status'] not in ('queued', 'running')][:64]:
                _jobs.pop(expired, None)
        job = {'status': 'queued', 'job_id': str(uuid.uuid4())}
        _jobs[key] = job
        _executor.submit(_run, key, path, checksum, duration, model_fingerprint())
        return dict(job)


def _run(key, path, checksum, duration, model_digest):
    """Isolate speech decoding in a subprocess with a hard timeout, no API calls."""
    output = CACHE / (key + '.json')
    temporary = CACHE / (key + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with _lock:
            _jobs[key]['status'] = 'running'
        CACHE.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
        # No provider key or inherited Claude session is needed by local ASR.
        for name in list(env):
            if any(term in name.upper() for term in ('API_KEY', 'API_TOKEN', 'ANTHROPIC', 'CLAUDE', 'GEMINI')):
                env.pop(name, None)
        command = [sys.executable, '-m', 'app.voice_worker', '--audio', str(path), '--model', str(MODEL),
                   '--output', str(temporary), '--checksum', checksum, '--model-sha256', model_digest]
        completed = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180, check=False)
        if completed.returncode != 0:
            raise RuntimeError('Local speech recognition failed. Check the installed model and recording.')
        result = _read_result(temporary, checksum, model_digest)
        if result is None or abs(result['duration_sec'] - duration) > 1:
            raise RuntimeError('Local speech recognition returned an invalid result.')
        temporary.replace(output)
        with _lock:
            _jobs[key].update(status='completed')
    except subprocess.TimeoutExpired:
        with _lock:
            _jobs[key].update(status='failed', error='Local speech recognition exceeded the three-minute processing limit.')
    except Exception:
        with _lock:
            _jobs[key].update(status='failed', error='Local speech recognition failed. Verify the voice pack and model, then retry.')
    finally:
        temporary.unlink(missing_ok=True)


def result_payload(text, segments, *, checksum, model_digest, language, language_probability, duration, processing_seconds):
    """One cue definition for live ASR and offline evaluation; never classifier inputs."""
    return {'text': text, 'segments': segments, 'source_sha256': checksum,
            'model': 'faster-whisper local CPU int8', 'model_sha256': model_digest,
            'asr_version': ASR_VERSION, 'feature_version': VERSION, 'features': text_features(text),
            'language': language, 'language_probability': language_probability,
            'duration_sec': duration, 'processing_seconds': round(processing_seconds, 3),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'speaker_attribution': 'unavailable', 'review_required': True}
