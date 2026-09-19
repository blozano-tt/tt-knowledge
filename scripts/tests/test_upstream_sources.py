import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from upstream_sources import indexed_path, load_sources


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL).strip()


class UpstreamSourcesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        upstream = base / "source"
        upstream.mkdir()
        git(upstream, "init")
        git(upstream, "config", "user.name", "Test")
        git(upstream, "config", "user.email", "test@example.com")
        (upstream / "WormholeB0").mkdir()
        (upstream / "WormholeB0/Instruction.md").write_text("# ISA\nOriginal documentation.\n")
        (upstream / "CODE_OF_CONDUCT.md").write_text("# Administration\n")
        (upstream / "WormholeB0/diagram.svg").write_text("<svg/>")
        git(upstream, "add", ".")
        git(upstream, "commit", "-m", "Fixture")
        self.root = base / "parent"
        self.root.mkdir()
        git(self.root, "init")
        self.path = "tt-knowledge/upstream/isa"
        git(self.root, "-c", "protocol.file.allow=always", "submodule", "add", str(upstream), self.path)
        url = "https://github.com/example/isa.git"
        git(self.root, "config", "-f", ".gitmodules", f"submodule.{self.path}.url", url)
        (self.root / "upstream-sources.json").write_text(json.dumps({"sources": [{
            "path": self.path, "repository": url, "reason": "Test primary source",
            "include": ["WormholeB0/**"]}]}))

    def test_selects_only_approved_markdown_with_exact_revision_provenance(self):
        source, = load_sources(self.root)
        self.assertEqual(source["files"], ["WormholeB0/Instruction.md"])
        self.assertEqual(indexed_path(source, source["files"][0]).as_posix(),
                         f"upstream/github.com/example/isa/blob/{source['revision']}/WormholeB0/Instruction.md")

    def test_missing_submodule_fails_instead_of_silently_indexing_nothing(self):
        git(self.root, "submodule", "deinit", "--force", "--all")
        with self.assertRaisesRegex(ValueError, "Uninitialized"):
            load_sources(self.root)

    def test_modified_upstream_fails(self):
        (self.root / self.path / "WormholeB0/Instruction.md").write_text("Modified")
        with self.assertRaisesRegex(ValueError, "must be clean"):
            load_sources(self.root)

    def test_unrecorded_commit_fails(self):
        checkout = self.root / self.path
        git(checkout, "-c", "user.name=Test", "-c", "user.email=test@example.com",
            "commit", "--allow-empty", "-m", "Unrecorded update")
        with self.assertRaisesRegex(ValueError, "recorded commit"):
            load_sources(self.root)

    def test_unregistered_directory_fails(self):
        (self.root / "tt-knowledge/upstream/unapproved").mkdir()
        with self.assertRaisesRegex(ValueError, "Unregistered"):
            load_sources(self.root)

    def test_repository_mismatch_fails(self):
        git(self.root, "config", "-f", ".gitmodules", f"submodule.{self.path}.url",
            "https://github.com/another/isa.git")
        with self.assertRaisesRegex(ValueError, "differs"):
            load_sources(self.root)


if __name__ == "__main__":
    unittest.main()
