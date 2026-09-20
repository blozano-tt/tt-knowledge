#!/usr/bin/env python3
"""Prepare a Markdown-only Docker corpus with stable upstream provenance."""

import json
import shutil
import re

from upstream_sources import ROOT, indexed_path, load_sources, source_room, git
from knowledge_catalog import document_record
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
    documents = {}
    revision = git(root, "rev-parse", "HEAD")
    for file in indexed_markdown_files():
        target = corpus / file.relative_to(ROOT / "tt-knowledge")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        relative = file.relative_to(ROOT / "tt-knowledge")
        room = re.sub(r"[^a-z0-9-]+", "-", relative.parts[0].lower()) if len(relative.parts) > 1 else "local"
        documents["/knowledge/" + relative.as_posix()] = document_record(
            file.read_bytes().decode("utf-8"), room,
            f"https://github.com/blozano-tt/tt-knowledge/blob/{revision}/tt-knowledge/{relative.as_posix()}")
        count += 1
    for source in sources:
        checkout = root / source["path"]
        for name in source["files"]:
            target = corpus / indexed_path(source, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(checkout / name, target)
            documents["/knowledge/" + indexed_path(source, name).as_posix()] = document_record(
                (checkout / name).read_bytes().decode("utf-8"), source_room(source, name),
                f"{source['repository'].removesuffix('.git')}/blob/{source['revision']}/{name}")
            count += 1
        # Preserve upstream license notices in the image, outside searchable text.
        licenses = output / "licenses" / checkout.name
        licenses.mkdir(parents=True, exist_ok=True)
        for file in checkout.glob("LICENSE*"):
            if file.is_file() and not file.is_symlink():
                shutil.copy2(file, licenses / file.name)
    (output / "licenses").mkdir(exist_ok=True)
    (output / "documents.json").write_text(json.dumps({"version": 1, "documents": documents}, indent=2) + "\n")
    (output / "sources.json").write_text(json.dumps(sources, indent=2) + "\n")
    print(f"Prepared {count} Markdown documents from {len(sources)} upstream source(s) plus local articles.")


if __name__ == "__main__":
    prepare()
