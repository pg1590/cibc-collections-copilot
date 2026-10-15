"""Tests never use a developer's real Gemini key: a saved data/gemini-key.txt would
otherwise turn offline tests into live, quota-using provider calls."""
import pytest


@pytest.fixture(autouse=True)
def no_real_gemini_key(monkeypatch, tmp_path):
    monkeypatch.delenv('GEMINI_API_KEY', raising=False)
    monkeypatch.setenv('GEMINI_API_KEY_FILE', str(tmp_path / 'no-gemini-key.txt'))
    monkeypatch.delenv('COPILOT_GEMINI_TEXT_EVIDENCE', raising=False)
    from app import runtime

    def clear():  # a test may have replaced provider() with a plain stub
        for cached in (runtime.provider, runtime._engine):
            getattr(cached, 'cache_clear', lambda: None)()
    clear()
    yield
    clear()
