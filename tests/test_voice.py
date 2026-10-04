"""Audio access, source integrity and isolation of unverified ASR evidence."""
import hashlib
import io
import json
import types
import wave

import duckdb
import pytest
from fastapi.testclient import TestClient

from app import main, storage, voice, voice_worker
from app.features import text_features


def wav_file(root, identifier='VS-10000'):
    path = root / 'files/voice' / (identifier + '.wav')
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b'\0\0' * 8000)
    content = path.read_bytes()
    source = {'voice_sample_id': identifier, 'file_path': 'voice/' + path.name,
              'checksum_sha256': hashlib.sha256(content).hexdigest(), 'file_size_bytes': len(content), 'duration_sec': 1.0}
    return path, source


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'DB', tmp_path / 'test.duckdb')
    monkeypatch.setattr(main, 'DATASET', tmp_path)
    monkeypatch.setattr(main, 'QUALITY', tmp_path / 'quality.json')
    monkeypatch.setattr(storage, 'STATE', tmp_path / 'state.sqlite3')
    main.QUALITY.write_text('{}')
    monkeypatch.setenv('COPILOT_AGENT_ID', 'A-1')
    for role in ('analyst', 'agent', 'supervisor'):
        monkeypatch.delenv('COPILOT_' + role.upper() + '_PASSWORD', raising=False)
    path, source = wav_file(tmp_path)
    with duckdb.connect(str(main.DB)) as c:
        c.execute('CREATE SCHEMA gold')
        c.execute('CREATE SCHEMA curated')
        c.execute("CREATE TABLE gold.customers AS SELECT * FROM (VALUES ('C-1'),('C-2')) t(customer_id)")
        # Same customer can have one assigned case and a second case outside scope.
        c.execute("CREATE TABLE gold.cases AS SELECT * FROM (VALUES ('C-1','CS-1','A-1'),('C-1','CS-2','A-2'),('C-2','CS-3','A-2')) t(customer_id,case_id,assigned_agent_id)")
        c.execute("CREATE TABLE gold.crm_identity AS SELECT * FROM (VALUES ('CRM-1','C-1'),('CRM-2','C-2')) t(crm_customer_id,customer_id)")
        c.execute('CREATE TABLE curated.call_transcripts(transcript_id VARCHAR,voice_sample_id VARCHAR,contact_id VARCHAR,case_id VARCHAR,crm_customer_id VARCHAR,call_start_ts TIMESTAMP)')
        c.execute('CREATE TABLE curated.voice_samples(voice_sample_id VARCHAR,transcript_id VARCHAR,contact_id VARCHAR,file_path VARCHAR,file_size_bytes BIGINT,checksum_sha256 VARCHAR,duration_sec DOUBLE,language VARCHAR)')
        for idx, (case, crm) in enumerate([('CS-1', 'CRM-1'), ('CS-2', 'CRM-1'), ('CS-3', 'CRM-2')]):
            identifier = 'VS-' + str(10000 + idx)
            _, item = wav_file(tmp_path, identifier)
            c.execute("INSERT INTO curated.call_transcripts VALUES(?,?,?,?,?,'2026-09-01')", [str(idx), identifier, 'CT-' + str(idx), case, crm])
            c.execute('INSERT INTO curated.voice_samples VALUES(?,?,?,?,?,?,?,?)', [identifier, str(idx), 'CT-' + str(idx), item['file_path'], item['file_size_bytes'], item['checksum_sha256'], 1.0, 'en-CA'])
    with TestClient(main.app) as client:
        yield client, tmp_path, source


def login(client, role):
    response = client.post('/api/auth/login', json={'username': role, 'password': role + '-demo'})
    return {'Authorization': 'Bearer ' + response.json()['token']}


@pytest.mark.parametrize('endpoint', ['audio', 'transcription', 'transcribe'])
def test_recording_requires_auth_and_case_assignment(api, endpoint):
    client, _, _ = api
    request = client.post if endpoint == 'transcribe' else client.get
    assert request('/api/voice/VS-10000/' + endpoint).status_code == 401
    headers = login(client, 'agent')
    # C-1 is accessible, but recording belongs to its differently assigned case.
    assert request('/api/voice/VS-10001/' + endpoint, headers=headers).status_code == 404
    assert request('/api/voice/VS-10002/' + endpoint, headers=headers).status_code == 404


def test_customer_list_scopes_individual_cases_and_hides_sensitive_metadata(api):
    client, _, _ = api
    response = client.get('/api/customers/C-1/voice', headers=login(client, 'agent'))
    assert response.status_code == 200
    assert [row['voice_sample_id'] for row in response.json()['items']] == ['VS-10000']
    assert 'file_path' not in response.json()['items'][0]
    assert 'accent' not in response.text
    assert client.get('/api/customers/C-2/voice', headers=login(client, 'agent')).status_code == 404


def test_audio_is_verified_and_not_cached(api):
    client, root, _ = api
    headers = login(client, 'analyst')
    response = client.get('/api/voice/VS-10000/audio', headers=headers)
    assert response.status_code == 200
    assert response.content == (root / 'files/voice/VS-10000.wav').read_bytes()
    assert response.headers['cache-control'] == 'private, no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['content-type'] == 'audio/wav'
    with storage.connect() as c:
        assert c.execute("SELECT count(*) FROM audit WHERE action='play_recording'").fetchone()[0] == 1


def test_agent_can_play_own_case_and_unknown_roles_fail_closed(api):
    client, _, _ = api
    assert client.get('/api/voice/VS-10000/audio', headers=login(client, 'agent')).status_code == 200
    token = storage.create_session('unsupported-account', 'unsupported-role')
    headers = {'Authorization': 'Bearer ' + token}
    assert client.get('/api/customers/C-1/voice', headers=headers).status_code == 403
    assert client.get('/api/customers/unknown/voice', headers=headers).status_code == 403
    assert client.get('/api/customers', headers=headers).status_code == 403


@pytest.mark.parametrize('endpoint', ['audio', 'transcription', 'transcribe'])
def test_corrupted_audio_cannot_be_played_or_reuse_cache(api, endpoint):
    client, root, _ = api
    path = root / 'files/voice/VS-10000.wav'
    content = bytearray(path.read_bytes()); content[-1] = 1; path.write_bytes(content)
    request = client.post if endpoint == 'transcribe' else client.get
    assert request('/api/voice/VS-10000/' + endpoint, headers=login(client, 'supervisor')).status_code == 422


def test_missing_pack_and_missing_model_are_explicit(api, monkeypatch):
    client, root, _ = api
    headers = login(client, 'analyst')
    monkeypatch.setattr(voice, 'speech_available', lambda: False)
    assert client.post('/api/voice/VS-10000/transcribe', headers=headers).status_code == 503
    (root / 'files/voice/VS-10000.wav').unlink()
    assert client.get('/api/voice/VS-10000/audio', headers=headers).status_code == 404
    listed = client.get('/api/customers/C-1/voice', headers=headers).json()
    assert listed['speech_to_text_available'] is False
    assert next(row for row in listed['items'] if row['voice_sample_id'] == 'VS-10000')['audio_available'] is False


def test_crm_case_mismatch_cannot_expose_another_customer(api):
    client, _, _ = api
    with duckdb.connect(str(main.DB)) as c:
        c.execute("UPDATE curated.call_transcripts SET crm_customer_id='CRM-2' WHERE voice_sample_id='VS-10000'")
    assert client.get('/api/voice/VS-10000/audio', headers=login(client, 'supervisor')).status_code == 404


@pytest.mark.parametrize('source_change', [
    {'file_path': '../secret.wav'}, {'file_path': 'voice/VS-999.wav'},
    {'voice_sample_id': '../secret'}, {'checksum_sha256': 'x' * 64}, {'duration_sec': 999},
])
def test_paths_ids_checksums_and_durations_fail_closed(tmp_path, source_change):
    _, source = wav_file(tmp_path)
    source.update(source_change)
    with pytest.raises(voice.VoiceError):
        voice.verified_audio(tmp_path, source)


def test_symlink_escape_is_rejected(tmp_path):
    path, source = wav_file(tmp_path)
    target = tmp_path / 'outside.wav'
    path.rename(target); path.symlink_to(target)
    with pytest.raises(voice.VoiceError):
        voice.verified_audio(tmp_path, source)


def local_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, 'CACHE', tmp_path / 'cache')
    monkeypatch.setattr(voice, 'speech_available', lambda: True)
    monkeypatch.setattr(voice, 'model_fingerprint', lambda: 'a' * 64)
    monkeypatch.setattr(voice, '_jobs', {})


def test_single_flight_queue_is_bounded(tmp_path, monkeypatch):
    local_cache(tmp_path, monkeypatch)
    scheduled = []
    monkeypatch.setattr(voice, '_executor', types.SimpleNamespace(submit=lambda *args: scheduled.append(args)))
    _, source = wav_file(tmp_path)
    first = voice.start_transcription(tmp_path, source)
    assert voice.start_transcription(tmp_path, source) == first
    assert len(scheduled) == 1
    for number in range(voice.MAX_ACTIVE - 1):
        voice._jobs['other' + str(number)] = {'status': 'running'}
    # Duplicate same audio remains a single job even when the queue is full.
    assert voice.start_transcription(tmp_path, source) == first
    _, different = wav_file(tmp_path, 'VS-10001')
    path = tmp_path / 'files/voice/VS-10001.wav'
    content = bytearray(path.read_bytes()); content[-1] = 1; path.write_bytes(content)
    different['checksum_sha256'] = hashlib.sha256(content).hexdigest()
    with pytest.raises(OverflowError):
        voice.start_transcription(tmp_path, different)


def test_cached_transcription_uses_shared_cues_without_customer_attribution(tmp_path, monkeypatch):
    local_cache(tmp_path, monkeypatch)
    _, source = wav_file(tmp_path)
    text = 'The customer says my hours were cut. The agent offers payment relief.'
    payload = voice.result_payload(text, [{'start': 0, 'end': 1, 'text': text}],
        checksum=source['checksum_sha256'], model_digest='a' * 64, language='en',
        language_probability=.95, duration=1, processing_seconds=.5)
    path = voice.CACHE / (voice.cache_key(source['checksum_sha256']) + '.json')
    path.parent.mkdir(); path.write_text(json.dumps(payload))
    result = voice.transcription_status(source)
    assert result['status'] == 'completed'
    assert result['transcript']['features'] == text_features(text)
    assert result['transcript']['speaker_attribution'] == 'unavailable'
    assert result['transcript']['review_required'] is True
    assert 'review_probability' not in result['transcript']
    # Altered or outdated vectors are rejected rather than served as verified cues.
    payload['features']['income_reduction'] = 0
    path.write_text(json.dumps(payload))
    assert voice.transcription_status(source)['status'] == 'not_started'


def test_worker_decodes_audio_bytes_instead_of_existing_transcript(tmp_path, monkeypatch):
    path, source = wav_file(tmp_path)
    calls = []

    class LocalModel:
        def __init__(self, *args, **kwargs):
            assert kwargs['local_files_only'] is True
            assert kwargs['device'] == 'cpu'
            assert kwargs['compute_type'] == 'int8'

        def transcribe(self, audio, **kwargs):
            assert isinstance(audio, io.BytesIO)
            assert audio.getvalue() == path.read_bytes()
            calls.append(kwargs)
            return [types.SimpleNamespace(start=0, end=1, text='My hours were cut.')], types.SimpleNamespace(language='en', language_probability=.9)

    monkeypatch.setitem(__import__('sys').modules, 'faster_whisper', types.SimpleNamespace(WhisperModel=LocalModel))
    (tmp_path / 'provided-transcript.json').write_text('{"text":"different source text"}')
    payload = voice_worker.transcribe(path, tmp_path / 'model', source['checksum_sha256'], 'a' * 64)
    assert payload['text'] == 'My hours were cut.'
    assert payload['features']['income_reduction'] == 1
    assert payload['review_required'] is True
    assert calls[0]['vad_filter'] is True


@pytest.mark.parametrize('changes', [{'text': []}, {'text': {}}, {'duration_sec': 'nan'},
                                   {'language_probability': 2}, {'segments': [{'start': 2, 'end': 1, 'text': 'Hi'}]}])
def test_malformed_cache_is_a_miss_instead_of_server_error(tmp_path, changes):
    payload = voice.result_payload('Hi', [{'start': 0, 'end': 1, 'text': 'Hi'}], checksum='b' * 64,
        model_digest='a' * 64, language='en', language_probability=.9, duration=1, processing_seconds=.2)
    payload.update(changes)
    path = tmp_path / 'cache.json'; path.write_text(json.dumps(payload))
    assert voice._read_result(path, 'b' * 64, 'a' * 64) is None


def test_worker_timeout_is_reported_and_queue_job_can_retry(tmp_path, monkeypatch):
    local_cache(tmp_path, monkeypatch)
    _, source = wav_file(tmp_path)
    key = voice.cache_key(source['checksum_sha256'])
    voice._jobs[key] = {'status': 'queued', 'job_id': 'test'}

    def timeout(command, **kwargs):
        assert kwargs['timeout'] == 180
        assert kwargs['env']['HF_HUB_OFFLINE'] == '1'
        assert 'GEMINI_API_KEY' not in kwargs['env']
        raise voice.subprocess.TimeoutExpired(command, 180)

    monkeypatch.setenv('GEMINI_API_KEY', 'test-only-not-a-real-key')
    monkeypatch.setattr(voice.subprocess, 'run', timeout)
    voice._run(key, tmp_path / source['file_path'], source['checksum_sha256'], 1, 'a' * 64)
    assert voice._jobs[key]['status'] == 'failed'
    assert 'processing limit' in voice._jobs[key]['error']
