"""Resolve approved, pinned upstream Markdown without modifying submodules."""

import fnmatch
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def load_sources(root: Path = ROOT) -> list[dict]:
    sources = json.loads((root / "upstream-sources.json").read_text())["sources"]
    registered = set()
    for source in sources:
        path = source["path"]
        relative = Path(path)
        if (len(relative.parts) != 3 or relative.parts[:2] != ("tt-knowledge", "upstream")
                or relative.name in {".", ".."} or path in registered):
            raise ValueError(f"Invalid or duplicate upstream path: {path}")
        registered.add(path)
        if not re.fullmatch(r"https://github\.com/[\w.-]+/[\w.-]+\.git", source["repository"]):
            raise ValueError(f"Expected a GitHub HTTPS repository URL: {path}")
        if not source.get("reason") or not source.get("include"):
            raise ValueError(f"Source needs a trust reason and include patterns: {path}")

        # Read the gitlink, not a moving upstream branch. The index also supports
        # validating an intentionally staged submodule revision before commit.
        entries = git(root, "ls-files", "--stage", "--", path).splitlines()
        if len(entries) != 1 or not entries[0].startswith("160000 "):
            raise ValueError(f"Source must be a registered Git submodule: {path}")
        revision = entries[0].split()[1]
        configured_path = git(root, "config", "-f", ".gitmodules", "--get", f"submodule.{path}.path")
        configured_url = git(root, "config", "-f", ".gitmodules", "--get", f"submodule.{path}.url")
        if configured_path != path or configured_url != source["repository"]:
            raise ValueError(f"Source registration differs from .gitmodules: {path}")
        checkout = root / path
        if not (checkout / ".git").exists():
            raise ValueError(f"Uninitialized submodule: {path}; run git submodule update --init --recursive")
        if git(checkout, "rev-parse", "HEAD") != revision:
            raise ValueError(f"Submodule does not match its recorded commit: {path}")
        if git(checkout, "status", "--porcelain"):
            raise ValueError(f"Upstream checkout must be clean: {path}")
        # Do not strip leading spaces: they signify a correctly pinned checkout.
        status = subprocess.check_output(
            ["git", "-C", str(root), "submodule", "status", "--recursive", "--", path], text=True)
        if any(line and line[0] != " " for line in status.splitlines()):
            raise ValueError(f"Uninitialized or mismatched nested submodule: {path}")
        source["revision"] = revision
        source["files"] = []
        tracked = git(checkout, "ls-files", "-z").split("\0")
        for name in tracked:
            if not name.endswith(".md") or not any(fnmatch.fnmatchcase(name, p) for p in source["include"]):
                continue
            file = checkout / name
            if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(checkout.resolve()):
                raise ValueError(f"Source document must be a regular file within its checkout: {file}")
            source_tags(source, name)  # Validate routing before preparing any build input.
            source["files"].append(name)
        if not source["files"]:
            raise ValueError(f"Source has no selected Markdown: {path}")

    upstream = root / "tt-knowledge/upstream"
    if upstream.exists():
        for child in upstream.iterdir():
            if child.relative_to(root).as_posix() not in registered:
                raise ValueError(f"Unregistered upstream source: {child.relative_to(root)}")
    return sources


def indexed_path(source: dict, name: str) -> Path:
    # Keep revision and architecture visible in the prepared source path.
    repository = source["repository"].removeprefix("https://").removesuffix(".git")
    return Path("upstream") / repository / "blob" / source["revision"] / name


def source_tags(source: dict, name: str) -> list[str]:
    """Apply configured provenance/architecture tags at ingestion through the public API."""
    mappings = source.get("path_tags", {})
    if not isinstance(mappings, dict):
        raise ValueError("path_tags must be a directory-to-tags mapping")
    base = source.get("tags", [])
    default = source.get("default_tags", [])
    for tags in [base, default, *mappings.values()]:
        if not isinstance(tags, list) or any(not isinstance(t, str) or not t or len(t) > 128 for t in tags):
            raise ValueError("Source tags must be lists of nonempty strings up to 128 characters")
    matches = []
    for prefix, tags in mappings.items():
        if not prefix or prefix.startswith("/") or any(p in {"", ".", ".."} for p in prefix.split("/")):
            raise ValueError(f"Invalid tag path prefix: {prefix}")
        if name.startswith(prefix + "/"):
            matches.append((len(prefix), tags))
    selected = max(matches, key=lambda item: item[0])[1] if matches else default
    return sorted(set(base + selected))
