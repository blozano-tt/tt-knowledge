#!/usr/bin/env python3
"""Prepare a Markdown-only Docker corpus with stable upstream provenance."""

import json
import shutil

from upstream_sources import ROOT, indexed_path, load_sources
from validate_knowledge import indexed_markdown_files, main as validate


def prepare() -> None:
    root = ROOT
    if validate():
        raise SystemExit("Corpus validation failed; refusing to prepare the Docker image")
    sources = load_sources(root)
    output = root / ".build"
    if output.exists():
        shutil.rmtree(output)
    corpus = output / "knowledge"
    corpus.mkdir(parents=True)
    count = 0
    for file in indexed_markdown_files():
        target = corpus / file.relative_to(ROOT / "tt-knowledge")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        count += 1
    for source in sources:
        checkout = root / source["path"]
        for name in source["files"]:
            target = corpus / indexed_path(source, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout / name, target)
            count += 1
        # Preserve upstream license notices in the image, outside searchable text.
        licenses = output / "licenses" / checkout.name
        licenses.mkdir(parents=True, exist_ok=True)
        for file in checkout.glob("LICENSE*"):
            if file.is_file() and not file.is_symlink():
                shutil.copy2(file, licenses / file.name)
    (output / "licenses").mkdir(exist_ok=True)
    (output / "sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    print(f"Prepared {count} Markdown documents from {len(sources)} upstream source(s) plus local articles.")


if __name__ == "__main__":
    prepare()
