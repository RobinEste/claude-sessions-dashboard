"""Lightweight TF-IDF search over session export Markdown files.

Pure Python — stdlib only (collections.Counter, math.log, re).
Builds an inverted index cached as .search-index.json.

Sunset condition: This module is replaced when BeeHaive RAG (Fase 3)
is operational. After migration: remove this file, the search subcommand,
and .search-index.json.
"""

from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from pathlib import Path

DEFAULT_EXPORTS_DIR = Path.home() / ".claude" / "session-exports"
INDEX_FILENAME = ".search-index.json"

# Simple tokeniser: split on non-alphanumeric, lowercase
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]+")

# YAML frontmatter extraction
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)

# Stopwords (minimal set — Dutch + English)
_STOPWORDS = frozenset(
    "de het een van in is dat op te en er aan voor met als om maar dan "
    "ook nog bij uit ze al was ze of hun ze die dit door wordt zijn "
    "the a an in is it of to and for on at by with from or as but not "
    "this that was be are were been has have had do does did will would "
    "can could should may might".split()
)


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase words, excluding stopwords."""
    return [
        w.lower()
        for w in _TOKEN_RE.findall(text)
        if w.lower() not in _STOPWORDS and len(w) > 1
    ]


def _parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML frontmatter as key-value pairs."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}
    result = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"')
    return result


def _extract_snippet(text: str, query_tokens: set[str], max_words: int = 200) -> str:
    """Extract the best-matching snippet from text.

    Finds the paragraph with highest query token overlap,
    plus up to 1 paragraph of context before and after.
    """
    # Split into paragraphs (separated by blank lines)
    paragraphs = re.split(r"\n\s*\n", text)
    if not paragraphs:
        return ""

    # Skip frontmatter
    start = 0
    if paragraphs[0].strip().startswith("---"):
        start = 1
    paragraphs = paragraphs[start:]
    if not paragraphs:
        return ""

    # Score each paragraph by query token overlap
    best_idx = 0
    best_score = -1
    for i, para in enumerate(paragraphs):
        para_tokens = set(_tokenize(para))
        score = len(para_tokens & query_tokens)
        if score > best_score:
            best_score = score
            best_idx = i

    # Collect context: 1 before, match, 1 after
    start_idx = max(0, best_idx - 1)
    end_idx = min(len(paragraphs), best_idx + 2)
    snippet_parts = paragraphs[start_idx:end_idx]

    snippet = "\n\n".join(snippet_parts)

    # Trim to max words
    words = snippet.split()
    if len(words) > max_words:
        snippet = " ".join(words[:max_words]) + "..."

    return snippet


class SearchIndex:
    """TF-IDF inverted index over Markdown export files."""

    def __init__(self, exports_dir: Path | None = None) -> None:
        self.exports_dir = exports_dir or DEFAULT_EXPORTS_DIR
        self.index_path = self.exports_dir / INDEX_FILENAME
        self._docs: dict[str, dict] = {}  # doc_id → {tokens, metadata, path}
        self._idf: dict[str, float] = {}
        self._doc_count = 0

    def _needs_rebuild(self) -> bool:
        """Check if index needs rebuilding based on file mtimes."""
        if not self.index_path.exists():
            return True

        index_mtime = self.index_path.stat().st_mtime
        for md_file in self.exports_dir.rglob("*.md"):
            if md_file.stat().st_mtime > index_mtime:
                return True
        return False

    def build(self, force: bool = False) -> int:
        """Build or rebuild the index from Markdown exports.

        Returns number of indexed documents.
        """
        if not force and not self._needs_rebuild():
            self._load_cached()
            return self._doc_count

        self._docs = {}
        doc_freq: Counter = Counter()

        for md_file in self.exports_dir.rglob("*.md"):
            try:
                text = md_file.read_text(encoding="utf-8")
            except OSError:
                continue

            fm = _parse_frontmatter(text)
            if not fm.get("session_id"):
                continue

            tokens = _tokenize(text)
            tf = Counter(tokens)
            doc_id = fm["session_id"]

            self._docs[doc_id] = {
                "tf": dict(tf),
                "total_tokens": len(tokens),
                "metadata": {
                    "session_id": fm.get("session_id", ""),
                    "project_slug": fm.get("project_slug", ""),
                    "intent": fm.get("intent", ""),
                    "started_at": fm.get("started_at", ""),
                    "ended_at": fm.get("ended_at", ""),
                    "status": fm.get("status", ""),
                },
                "path": str(md_file),
            }

            for token in set(tokens):
                doc_freq[token] += 1

        self._doc_count = len(self._docs)

        # Compute IDF
        self._idf = {}
        for token, df in doc_freq.items():
            self._idf[token] = math.log((self._doc_count + 1) / (df + 1)) + 1

        # Cache to disk
        self._save_cached()
        return self._doc_count

    def search(
        self,
        query: str,
        project: str | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """Search the index. Returns ranked results with snippets.

        Each result: {session_id, project, intent, score, snippet, date, path}
        """
        self.build()

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        query_token_set = set(query_tokens)
        results = []

        for doc_id, doc in self._docs.items():
            # Filter by project if specified
            if project and doc["metadata"].get("project_slug") != project:
                continue

            # Compute TF-IDF score
            tf = doc["tf"]
            total = doc["total_tokens"] or 1
            score = 0.0
            for qt in query_tokens:
                if qt in tf:
                    term_freq = tf[qt] / total
                    idf = self._idf.get(qt, 1.0)
                    score += term_freq * idf

            if score > 0:
                results.append({
                    "session_id": doc["metadata"]["session_id"],
                    "project": doc["metadata"]["project_slug"],
                    "intent": doc["metadata"]["intent"],
                    "score": round(score, 4),
                    "date": doc["metadata"].get("started_at", "")[:10],
                    "path": doc["path"],
                })

        # Sort by score descending
        results.sort(key=lambda r: r["score"], reverse=True)
        results = results[:limit]

        # Add snippets for top results (read from file)
        for r in results:
            try:
                text = Path(r["path"]).read_text(encoding="utf-8")
                r["snippet"] = _extract_snippet(text, query_token_set)
            except OSError:
                r["snippet"] = ""

        return results

    def _save_cached(self) -> None:
        """Save index to disk with mode 600."""
        data = {
            "doc_count": self._doc_count,
            "idf": self._idf,
            "docs": self._docs,
        }
        fd = os.open(str(self.index_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False)

    def _load_cached(self) -> None:
        """Load index from cached file."""
        try:
            text = self.index_path.read_text(encoding="utf-8")
            data = json.loads(text)
            self._doc_count = data.get("doc_count", 0)
            self._idf = data.get("idf", {})
            self._docs = data.get("docs", {})
        except (OSError, json.JSONDecodeError):
            self.build(force=True)
