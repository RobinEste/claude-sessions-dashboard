"""JSONL reader for Claude Code session transcripts.

Parses Claude Code JSONL files and extracts user/assistant conversation turns.
Centralises all JSONL-specific logic so format changes only require updates here.

Assumption: Based on observed Claude Code JSONL structure (March 2026).
If the format changes, update the extraction logic in this module.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Signal words for keyword-density trimming (Dutch + English)
_SIGNAL_WORDS = re.compile(
    r"\b(oplossing|fix|beslissing|fout|werkt|keuze|error|solution|decision|bug|"
    r"problem|probleem|gekozen|resolved|fixed|debug|oorzaak|cause|workaround)\b",
    re.IGNORECASE,
)

# Secret patterns for redaction
_SECRET_PATTERNS = [
    # API keys
    re.compile(r"\b(sk-[a-zA-Z0-9]{20,})\b"),
    re.compile(r"\b(ghp_[a-zA-Z0-9]{36,})\b"),
    re.compile(r"\b(gho_[a-zA-Z0-9]{36,})\b"),
    re.compile(r"\b(glpat-[a-zA-Z0-9\-]{20,})\b"),
    re.compile(r"\b(xoxb-[a-zA-Z0-9\-]+)\b"),
    re.compile(r"\b(xoxp-[a-zA-Z0-9\-]+)\b"),
    # Tokens after keywords
    re.compile(r"(Bearer\s+[a-zA-Z0-9\-._~+/]+=*)", re.IGNORECASE),
    re.compile(r"(token=)[a-zA-Z0-9\-._~+/]{16,}", re.IGNORECASE),
    re.compile(r"(apikey=)[a-zA-Z0-9\-._~+/]{16,}", re.IGNORECASE),
    re.compile(r"(api_key=)[a-zA-Z0-9\-._~+/]{16,}", re.IGNORECASE),
    # PEM private keys
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
    # Generic long secrets after key/secret/password/token
    re.compile(
        r"(?:key|secret|password|token)[\"':\s=]+([a-zA-Z0-9\-._~+/]{32,})",
        re.IGNORECASE,
    ),
]

# PII patterns
_PII_PATTERNS = [
    re.compile(r"\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b"),  # email
    re.compile(r"(?:\+31|0)[\s\-]?[1-9][\d\s\-]{7,13}"),  # NL phone (+31 6 12345678, 06-12345678)
    re.compile(r"\+[1-9]\d{0,2}[\s\-]?\d{2,4}[\s\-]?\d{3,4}[\s\-]?\d{2,4}"),  # intl phone
]


@dataclass
class ConversationTurn:
    """A single user or assistant turn extracted from JSONL."""

    role: str  # "user" or "assistant"
    text: str
    timestamp: str = ""


@dataclass
class TranscriptResult:
    """Result of parsing a JSONL transcript."""

    session_id: str = ""
    turns: list[ConversationTurn] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    redaction_count: int = 0


class JSONLReader:
    """Reads and parses Claude Code JSONL session files."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read_transcript(self) -> TranscriptResult:
        """Parse JSONL file and extract conversation turns.

        Returns TranscriptResult with turns, warnings and redaction count.
        Tolerant of unknown types — logs warning and skips.
        """
        result = TranscriptResult()
        known_types = {"user", "assistant", "system", "progress", "file-history-snapshot"}

        try:
            with open(self.path) as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError as e:
                        result.warnings.append(f"Line {line_num}: invalid JSON: {e}")
                        continue

                    msg_type = obj.get("type", "")

                    # Capture session ID from first message that has one
                    if not result.session_id and obj.get("sessionId"):
                        result.session_id = obj["sessionId"]

                    if msg_type not in known_types:
                        result.warnings.append(
                            f"Line {line_num}: unknown type '{msg_type}', skipping"
                        )
                        continue

                    # Skip non-conversation types
                    if msg_type in ("system", "progress", "file-history-snapshot"):
                        continue

                    message = obj.get("message", {})
                    if not isinstance(message, dict):
                        continue

                    content = message.get("content", "")
                    timestamp = obj.get("timestamp", "")

                    if msg_type == "user":
                        text = self._extract_user_text(content)
                        if text:
                            result.turns.append(
                                ConversationTurn(role="user", text=text, timestamp=timestamp)
                            )

                    elif msg_type == "assistant":
                        text = self._extract_assistant_text(content)
                        if text:
                            result.turns.append(
                                ConversationTurn(
                                    role="assistant", text=text, timestamp=timestamp
                                )
                            )

        except OSError as e:
            result.warnings.append(f"Could not read file: {e}")

        return result

    def _extract_user_text(self, content) -> str:
        """Extract text from user message content."""
        if isinstance(content, str):
            # Strip command tags that are not useful for recall
            text = re.sub(r"<command-(?:message|name)>.*?</command-(?:message|name)>", "", content)
            return text.strip()
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts).strip()
        return ""

    def _extract_assistant_text(self, content) -> str:
        """Extract only text blocks from assistant content (skip tool_use)."""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts).strip()
        return ""


def redact_secrets(text: str) -> tuple[str, int]:
    """Replace detected secrets with [REDACTED]. Returns (text, count)."""
    count = 0
    for pattern in _SECRET_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            count += len(matches)
            text = pattern.sub("[REDACTED]", text)
    return text, count


def redact_pii(text: str) -> tuple[str, int]:
    """Replace detected PII with [PII]. Returns (text, count)."""
    count = 0
    for pattern in _PII_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            count += len(matches)
            text = pattern.sub("[PII]", text)
    return text, count


def _keyword_density(text: str) -> int:
    """Count signal words in text for trimming priority."""
    return len(_SIGNAL_WORDS.findall(text))


def trim_turns(
    turns: list[ConversationTurn], max_words: int = 2000
) -> tuple[list[ConversationTurn], int, int]:
    """Trim turns to fit within max_words budget.

    Strategy:
    - Always keep first 2 and last 2 turns for context
    - Middle turns are ranked by keyword-density
    - Returns (selected_turns, total_words_original, total_words_trimmed)
    """
    if not turns:
        return [], 0, 0

    total_original = sum(len(t.text.split()) for t in turns)

    # If already within budget, return all
    if total_original <= max_words:
        return list(turns), total_original, total_original

    n = len(turns)
    if n <= 4:
        # Can't trim further with so few turns — just truncate text
        return list(turns), total_original, total_original

    # Always keep bookend turns
    keep_start = min(2, n)
    keep_end = min(2, n - keep_start)
    bookend_indices = set(range(keep_start)) | set(range(n - keep_end, n))
    middle_indices = [i for i in range(n) if i not in bookend_indices]

    # Rank middle turns by keyword density (descending)
    scored = [(i, _keyword_density(turns[i].text)) for i in middle_indices]
    scored.sort(key=lambda x: x[1], reverse=True)

    # Build selection: bookends first, then middle by density
    selected_indices = sorted(bookend_indices)
    budget = max_words - sum(len(turns[i].text.split()) for i in selected_indices)

    for idx, _score in scored:
        words = len(turns[idx].text.split())
        if budget - words >= 0:
            selected_indices.append(idx)
            budget -= words
        if budget <= 0:
            break

    selected_indices.sort()
    selected = [turns[i] for i in selected_indices]
    total_trimmed = sum(len(t.text.split()) for t in selected)

    return selected, total_original, total_trimmed


def find_jsonl_for_session(
    session_id: str,
    project_path: str | None = None,
    projects_dir: Path | None = None,
) -> Path | None:
    """Find the JSONL file for a given Claude Code session.

    Primary strategy: derive directory name from project_path.
    Fallback: scan all project directories for matching sessionId.

    Args:
        session_id: The Claude Code session UUID (not the dashboard session_id).
        project_path: Absolute path to the project directory.
        projects_dir: Path to ~/.claude/projects/ (default: auto-detect).

    Returns:
        Path to the JSONL file, or None if not found.
    """
    if projects_dir is None:
        projects_dir = Path.home() / ".claude" / "projects"

    if not projects_dir.is_dir():
        return None

    # Primary strategy: derive from project path
    if project_path:
        # Claude Code encodes paths: /Users/robin/Projects/Foo → -Users-robin-Projects-Foo
        encoded = project_path.replace("/", "-")
        if encoded.startswith("-"):
            # Keep leading hyphen (from leading /)
            pass
        claude_dir = projects_dir / encoded

        if claude_dir.is_dir():
            # Look for matching JSONL
            jsonl_path = claude_dir / f"{session_id}.jsonl"
            if jsonl_path.is_file():
                return jsonl_path

    # Fallback: scan all directories
    for subdir in projects_dir.iterdir():
        if not subdir.is_dir():
            continue
        jsonl_path = subdir / f"{session_id}.jsonl"
        if jsonl_path.is_file():
            return jsonl_path

    return None
