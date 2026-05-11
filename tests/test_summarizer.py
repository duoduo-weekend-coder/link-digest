from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from summarizer import summarize_text


def test_summarize_text_calls_groq_chat_completions(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    mock_message = MagicMock()
    mock_message.content = "  A great summary.  "
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = mock_response

    with patch("summarizer.Groq", return_value=mock_client) as mock_groq_cls:
        result = summarize_text("youtube", "Test Title", "hello world transcript")

    mock_groq_cls.assert_called_once_with(api_key="test-key")
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert call_kwargs["model"] == "llama-3.3-70b-versatile"
    messages = call_kwargs["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert "hello world transcript" in messages[1]["content"]
    assert result == "A great summary."


def test_summarize_text_raises_without_groq_key(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
        summarize_text("youtube", None, "some text")
