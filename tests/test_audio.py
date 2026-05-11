from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from extractors.audio import _transcribe_file


def test_transcribe_file_uses_groq_whisper(monkeypatch, tmp_path):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_WHISPER_MODEL", "whisper-large-v3")

    mock_transcript = MagicMock()
    mock_transcript.text = "hello from audio"

    mock_client = MagicMock()
    mock_client.audio.transcriptions.create.return_value = mock_transcript

    test_audio = tmp_path / "audio.mp3"
    test_audio.write_bytes(b"fake audio data")

    with patch("extractors.audio.Groq", return_value=mock_client) as mock_groq_cls:
        result = _transcribe_file(test_audio)

    mock_groq_cls.assert_called_once_with(api_key="test-key")
    call_kwargs = mock_client.audio.transcriptions.create.call_args.kwargs
    assert call_kwargs["model"] == "whisper-large-v3"
    assert "file" in call_kwargs
    assert result == "hello from audio"


def test_transcribe_file_raises_without_groq_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    test_audio = tmp_path / "audio.mp3"
    test_audio.write_bytes(b"fake audio data")
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        _transcribe_file(test_audio)
