#!/usr/bin/env python3
"""Cleanup script for session exports — AVG compliance (Art. 5.1e).

Removes session exports older than a configurable retention period.
Run periodically via macOS launchd or manually.

Usage:
    python3 scripts/cleanup_exports.py --older-than 365 [--dry-run]
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DEFAULT_EXPORTS_DIR = Path.home() / ".claude" / "session-exports"
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)


def parse_frontmatter(path: Path) -> dict[str, str]:
    """Parse YAML frontmatter from a Markdown export file.

    Returns a dict of key-value pairs. Returns empty dict on error.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        logger.warning("Cannot read %s: %s", path.name, e)
        return {}

    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}

    result = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"')
    return result


def find_expired_exports(
    exports_dir: Path, older_than_days: int
) -> list[Path]:
    """Find export files with ended_at (or started_at fallback) older than threshold."""
    cutoff = datetime.now(UTC) - timedelta(days=older_than_days)
    expired = []

    for md_file in exports_dir.rglob("*.md"):
        fm = parse_frontmatter(md_file)
        if not fm:
            logger.warning("Skipping (no frontmatter): %s", md_file.name)
            continue

        # Try ended_at first, fall back to started_at
        date_str = fm.get("ended_at") or fm.get("started_at")
        if not date_str:
            logger.warning("Skipping (no date): %s", md_file.name)
            continue

        try:
            dt = datetime.fromisoformat(date_str)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
        except (ValueError, TypeError):
            logger.warning("Skipping (invalid date '%s'): %s", date_str, md_file.name)
            continue

        if dt < cutoff:
            expired.append(md_file)

    return expired


def cleanup(exports_dir: Path, older_than_days: int, dry_run: bool = False) -> int:
    """Remove expired exports and clean up empty directories.

    Returns count of deleted files.
    """
    expired = find_expired_exports(exports_dir, older_than_days)

    if not expired:
        logger.info("No exports older than %d days found.", older_than_days)
        return 0

    if dry_run:
        logger.info("DRY RUN — would delete %d exports:", len(expired))
        for p in expired:
            logger.info("  %s", p.relative_to(exports_dir))
        return 0

    deleted = 0
    for p in expired:
        try:
            p.unlink()
            deleted += 1
        except OSError as e:
            logger.warning("Could not delete %s: %s", p.name, e)

    # Clean up empty project directories
    for subdir in exports_dir.iterdir():
        if subdir.is_dir() and not any(subdir.iterdir()):
            with contextlib.suppress(OSError):
                subdir.rmdir()

    # Remove stale search index so it gets rebuilt
    index_path = exports_dir / ".search-index.json"
    if index_path.exists() and deleted > 0:
        try:
            index_path.unlink()
            logger.info("Search index removed (will rebuild on next search).")
        except OSError:
            pass

    logger.info("Deleted %d exports (without filenames or content).", deleted)
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cleanup session exports older than N days (AVG Art. 5.1e)"
    )
    parser.add_argument(
        "--older-than", type=int, required=True,
        help="Delete exports older than N days",
    )
    parser.add_argument(
        "--exports-dir", type=str, default=str(DEFAULT_EXPORTS_DIR),
        help=f"Exports directory (default: {DEFAULT_EXPORTS_DIR})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be deleted without actually deleting",
    )
    args = parser.parse_args()

    exports_dir = Path(args.exports_dir).expanduser().resolve()
    if not exports_dir.is_dir():
        logger.error("Exports directory does not exist: %s", exports_dir)
        sys.exit(1)

    cleanup(exports_dir, args.older_than, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
