"""Tests for lib/jsonl_reader.py — JSONL parsing, redaction, trimming."""

from __future__ import annotations

import json
from pathlib import Path

from lib.jsonl_reader import (
    ConversationTurn,
    JSONLReader,
    redact_pii,
    redact_secrets,
    trim_turns,
)

# ---------------------------------------------------------------------------
# Helper: write temp JSONL
# ---------------------------------------------------------------------------


def _write_jsonl(lines: list[dict], tmp_path: Path) -> Path:
    path = tmp_path / "test.jsonl"
    with open(path, "w") as f:
        for obj in lines:
            f.write(json.dumps(obj) + "\n")
    return path


# ---------------------------------------------------------------------------
# JSONLReader
# ---------------------------------------------------------------------------


class TestJSONLReader:
    def test_basic_user_assistant_extraction(self, tmp_path):
        lines = [
            {
                "type": "user",
                "sessionId": "abc-123",
                "timestamp": "2026-03-01T10:00:00Z",
                "message": {"role": "user", "content": "How do I fix the auth bug?"},
            },
            {
                "type": "assistant",
                "sessionId": "abc-123",
                "timestamp": "2026-03-01T10:01:00Z",
                "message": {
                    "role": "assistant",
                    "content": [
                        {"type": "text", "text": "The auth bug is caused by..."},
                        {"type": "tool_use", "name": "Read", "input": {}},
                    ],
                },
            },
        ]
        path = _write_jsonl(lines, tmp_path)
        reader = JSONLReader(path)
        result = reader.read_transcript()

        assert result.session_id == "abc-123"
        assert len(result.turns) == 2
        assert result.turns[0].role == "user"
        assert result.turns[0].text == "How do I fix the auth bug?"
        assert result.turns[1].role == "assistant"
        assert result.turns[1].text == "The auth bug is caused by..."
        assert "tool_use" not in result.turns[1].text

    def test_skip_non_conversation_types(self, tmp_path):
        lines = [
            {"type": "file-history-snapshot"},
            {"type": "system", "subtype": "compact_boundary"},
            {"type": "progress", "message": "running..."},
            {
                "type": "user",
                "sessionId": "s1",
                "message": {"role": "user", "content": "hello"},
            },
        ]
        path = _write_jsonl(lines, tmp_path)
        reader = JSONLReader(path)
        result = reader.read_transcript()

        assert len(result.turns) == 1
        assert result.turns[0].text == "hello"

    def test_unknown_type_warning(self, tmp_path):
        lines = [
            {"type": "new_unknown_type", "data": "something"},
        ]
        path = _write_jsonl(lines, tmp_path)
        reader = JSONLReader(path)
        result = reader.read_transcript()

        assert len(result.turns) == 0
        assert any("unknown type" in w for w in result.warnings)

    def test_invalid_json_warning(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        with open(path, "w") as f:
            f.write('{"type": "user"}\n')
            f.write("not valid json\n")
            f.write('{"type": "user", "message": {"role": "user", "content": "ok"}}\n')
        reader = JSONLReader(path)
        result = reader.read_transcript()

        assert len(result.turns) == 1
        assert any("invalid JSON" in w for w in result.warnings)

    def test_command_tags_stripped(self, tmp_path):
        """Command-only messages produce empty text and are filtered out."""
        lines = [
            {
                "type": "user",
                "sessionId": "s1",
                "message": {
                    "role": "user",
                    "content": (
                        "<command-message>sessie-start</command-message>"
                        "<command-name>/sessie-start</command-name>"
                    ),
                },
            },
        ]
        path = _write_jsonl(lines, tmp_path)
        reader = JSONLReader(path)
        result = reader.read_transcript()

        # Empty text after stripping → turn is dropped (by design)
        assert len(result.turns) == 0

    def test_user_content_list(self, tmp_path):
        lines = [
            {
                "type": "user",
                "sessionId": "s1",
                "message": {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Part 1"},
                        {"type": "text", "text": "Part 2"},
                    ],
                },
            },
        ]
        path = _write_jsonl(lines, tmp_path)
        reader = JSONLReader(path)
        result = reader.read_transcript()

        assert result.turns[0].text == "Part 1\nPart 2"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class TestRedaction:
    def test_api_key_redacted(self):
        text = "My key is sk-abc123def456ghi789jkl012mno"
        result, count = redact_secrets(text)
        assert "[REDACTED]" in result
        assert "sk-abc123" not in result
        assert count >= 1

    def test_github_token_redacted(self):
        text = "token: ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result, count = redact_secrets(text)
        assert "[REDACTED]" in result
        assert count >= 1

    def test_bearer_token_redacted(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.test"
        result, count = redact_secrets(text)
        assert "[REDACTED]" in result
        assert count >= 1

    def test_pem_key_redacted(self):
        text = "-----BEGIN RSA PRIVATE KEY-----\ndata\n-----END RSA PRIVATE KEY-----"
        result, count = redact_secrets(text)
        assert "[REDACTED]" in result
        assert count >= 1

    def test_email_redacted(self):
        text = "Contact: jan.jansen@example.com for details"
        result, count = redact_pii(text)
        assert "[PII]" in result
        assert "jan.jansen@example.com" not in result
        assert count >= 1

    def test_phone_redacted(self):
        text = "Call +31 6 12345678 for support"
        result, count = redact_pii(text)
        assert "[PII]" in result
        assert count >= 1

    def test_no_false_positives_on_normal_text(self):
        text = "The function returns a list of items sorted by date."
        secret_result, s_count = redact_secrets(text)
        pii_result, p_count = redact_pii(text)
        assert s_count == 0
        assert p_count == 0
        assert secret_result == text
        assert pii_result == text


# ---------------------------------------------------------------------------
# Trimming
# ---------------------------------------------------------------------------


class TestTrimming:
    def _make_turns(self, n: int, words_per: int = 50) -> list[ConversationTurn]:
        turns = []
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            text = f"Turn {i} " + " ".join(f"word{j}" for j in range(words_per))
            turns.append(ConversationTurn(role=role, text=text))
        return turns

    def test_small_input_unchanged(self):
        turns = self._make_turns(3, words_per=10)
        selected, orig, trimmed = trim_turns(turns, max_words=2000)
        assert len(selected) == 3
        assert orig == trimmed

    def test_trim_respects_budget(self):
        turns = self._make_turns(20, words_per=200)
        selected, _orig, trimmed = trim_turns(turns, max_words=2000)
        assert trimmed <= 2000 + 200  # Allow some overshoot from last included turn
        assert len(selected) < 20

    def test_bookends_preserved(self):
        turns = self._make_turns(10, words_per=100)
        # Add signal words to middle turns
        turns[5].text = "The fix was to change the constraint. Oplossing werkt nu."
        selected, _, _ = trim_turns(turns, max_words=500)

        # First 2 and last 2 should always be present
        assert selected[0].text == turns[0].text
        assert selected[1].text == turns[1].text
        assert selected[-1].text == turns[-1].text
        assert selected[-2].text == turns[-2].text

    def test_keyword_density_prioritized(self):
        turns = self._make_turns(10, words_per=50)
        # Turn 5 has high keyword density
        turns[5].text = "The fix was a decision to use this workaround for the error."
        # Turn 6 has no signal words
        turns[6].text = "Here are some random generic placeholder sentences about nothing."

        selected, _, _ = trim_turns(turns, max_words=500)
        selected_texts = [t.text for t in selected]

        # Turn 5 (with keywords) should be prioritized over turn 6
        assert turns[5].text in selected_texts

    def test_empty_input(self):
        selected, orig, trimmed = trim_turns([], max_words=2000)
        assert selected == []
        assert orig == 0
        assert trimmed == 0
