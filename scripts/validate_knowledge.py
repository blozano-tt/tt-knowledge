#!/usr/bin/env python3
"""Validate the human-verification metadata on indexed Markdown files.

This deliberately uses only the Python standard library so CI has no package
installation step. It is not a general YAML parser; it validates the small
front-matter contract used by this repository.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "tt-knowledge"
SKIP_DIRS = {"_templates"}
SKIP_FILES = {CORPUS / "README.md"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def indexed_markdown_files() -> list[Path]:
    files: list[Path] = []
    for path in CORPUS.rglob("*.md"):
        if path in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(CORPUS).parts):
            continue
        files.append(path)
    return sorted(files)


def parse_front_matter(path: Path) -> tuple[dict[str, str], list[str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("missing opening YAML front-matter delimiter '---'")

    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise ValueError("missing closing YAML front-matter delimiter '---'") from exc

    metadata: dict[str, str] = {}
    sources: list[str] = []
    in_sources = False

    for raw in lines[1:end]:
        line = raw.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        if in_sources and re.match(r"^\s+-\s+", line):
            sources.append(re.sub(r"^\s+-\s+", "", line).strip().strip('"\''))
            continue

        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if match:
            key, value = match.groups()
            value = value.strip().strip('"\'')
            metadata[key] = value
            in_sources = key == "sources"
        elif in_sources:
            raise ValueError(f"malformed source entry: {line!r}")

    return metadata, sources


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        metadata, sources = parse_front_matter(path)
    except ValueError as exc:
        return [str(exc)]

    for key in ("verified_by", "verified_on"):
        if not metadata.get(key):
            errors.append(f"missing non-empty '{key}'")

    verified_on = metadata.get("verified_on", "")
    if verified_on and not DATE_RE.match(verified_on):
        errors.append("'verified_on' must use YYYY-MM-DD")

    if not sources or any(not source for source in sources):
        errors.append("'sources' must contain at least one non-empty list item")

    return errors


def main() -> int:
    failures = 0
    files = indexed_markdown_files()

    for path in files:
        errors = validate(path)
        for error in errors:
            failures += 1
            print(f"ERROR {path.relative_to(ROOT)}: {error}")

    if failures:
        print(f"\nValidation failed with {failures} error(s).")
        return 1

    print(f"Validated {len(files)} indexed Markdown file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
