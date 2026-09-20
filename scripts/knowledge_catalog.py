"""Lossless source catalogue and Markdown-aware chunk boundaries."""
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import re

WING = "tt-knowledge"
INDEX_STAMP = "tt-knowledge-index.json"
TARGET_CHARS = 1600  # A soft target: never sever a paragraph, table, or fence.
MAX_BLOCK_CHARS = 65536


def markdown_chunks(text, target_chars=TARGET_CHARS):
    """Pack complete Markdown blocks; headings start new sections, fences stay whole."""
    blocks, start, offset, fence = [], None, 0, None
    for line in text.splitlines(keepends=True):
        heading = re.match(r"^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$", line) if not fence else None
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if heading and start is not None:
            blocks.append((start, offset, None))
            start = None
        if start is None and line.strip():
            start = offset
        offset += len(line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
        elif marker:
            fence = marker[1]
        if heading:
            blocks.append((start, offset, (len(heading[1]), heading[2])))
            start = None
        elif not line.strip() and not fence and start is not None:
            blocks.append((start, offset, None))
            start = None
    if start is not None:
        blocks.append((start, len(text), None))

    lines = [0] + [m.end() for m in re.finditer("\n", text)]
    chunks, headings, pending, has_body = [], [], None, False

    def emit(end):
        nonlocal pending, has_body
        if pending is None:
            return
        a, section = pending
        b = end
        # `a` starts at the first nonblank line. Keep indentation: it can be
        # meaningful Markdown (e.g. an indented code block or nested list).
        while b > a and text[b - 1].isspace():
            b -= 1
        if a < b:
            chunks.append({"start": a, "end": b, "section": section,
                           "line_start": bisect_right(lines, a),
                           "line_end": bisect_right(lines, b - 1),
                           "chunk_index": len(chunks)})
        pending, has_body = None, False

    previous_end = 0
    for a, b, heading in blocks:
        if b - a > MAX_BLOCK_CHARS:
            raise ValueError("Markdown block exceeds 65,536 characters; split it editorially before indexing")
        if heading:
            if has_body:
                emit(previous_end)
            level, title = heading
            headings = [(n, t) for n, t in headings if n < level] + [(level, title)]
            if pending:
                pending = (pending[0], " / ".join(title for _, title in headings))
        elif pending and has_body and b - pending[0] > target_chars:
            emit(previous_end)
        if pending is None:
            pending = (a, " / ".join(title for _, title in headings))
        has_body = has_body or heading is None
        previous_end = b
    emit(previous_end)
    return chunks


def document_record(text, room, source_url):
    return {"room": room, "source_url": source_url,
            "sha256": hashlib.sha256(text.encode()).hexdigest(),
            "chunks": markdown_chunks(text)}


class Catalogue:
    """Read only files in the prepared manifest; source_path is never a filesystem query."""
    def __init__(self, root, manifest, id_factory):
        root = Path(root).resolve()
        manifest = json.loads(Path(manifest).read_text()) if not isinstance(manifest, dict) else manifest
        if manifest["version"] != 1:
            raise ValueError("Unsupported source catalogue version")
        self.documents, self.drawers = {}, {}
        for source_path, record in manifest["documents"].items():
            relative = Path(source_path).relative_to("/knowledge")
            path = root / relative
            if path.is_symlink() or not path.resolve().is_relative_to(root) or not path.is_file():
                raise ValueError("Source is not a regular file inside the prepared corpus")
            text = path.read_bytes().decode("utf-8")
            if hashlib.sha256(text.encode()).hexdigest() != record["sha256"]:
                raise ValueError(f"Source digest mismatch: {source_path}")
            if markdown_chunks(text) != record["chunks"]:
                raise ValueError(f"Chunk contract mismatch: {source_path}")
            doc = dict(record, text=text, source_path=source_path)
            doc["drawer_ids"] = [id_factory(WING, doc["room"], source_path, c["chunk_index"])
                                 for c in doc["chunks"]]
            self.documents[source_path] = doc
            for chunk, drawer_id in zip(doc["chunks"], doc["drawer_ids"]):
                self.drawers[drawer_id] = (doc, chunk)
        self.fingerprint = hashlib.sha256(json.dumps(
            {'manifest': manifest, 'drawer_ids': sorted(self.drawers)}, sort_keys=True).encode()).hexdigest()

    def verify_index(self, palace_path):
        stamp = Path(palace_path) / INDEX_STAMP
        if not stamp.is_file() or json.loads(stamp.read_text()).get('fingerprint') != self.fingerprint:
            raise RuntimeError('Index does not match source/chunk manifest; run deploy/rebuild-index.sh')

    def chunk(self, drawer_id, detail=False):
        doc, chunk = self.drawers[drawer_id]
        i = chunk["chunk_index"]
        out = {"drawer_id": drawer_id, "source_path": doc["source_path"], "room": doc["room"],
               "section": chunk["section"], "chunk_index": i, "chunk_count": len(doc["chunks"]),
               "text": doc["text"][chunk["start"]:chunk["end"]]}
        if detail:
            out.update(source_url=doc["source_url"], line_start=chunk["line_start"], line_end=chunk["line_end"],
                       previous_drawer_id=doc["drawer_ids"][i-1] if i else None,
                       next_drawer_id=doc["drawer_ids"][i+1] if i+1 < len(doc["chunks"]) else None)
        return out

    def get_document(self, source_path, offset=0, max_chars=65536):
        doc = self.documents.get(source_path)
        if doc is None:
            return {"error": "Unknown source_path; use an exact source_path returned by search"}
        if not 0 <= offset <= len(doc['text']) or not 1 <= max_chars <= 65536:
            return {"error": "Invalid document offset or page size"}
        end = min(offset + max_chars, len(doc["text"]))
        return {"source_path": source_path, "source_url": doc["source_url"], "room": doc["room"],
                "sha256": doc["sha256"], "content": doc["text"][offset:end],
                "offset": offset, "total_chars": len(doc["text"]),
                "complete": offset == 0 and end == len(doc["text"]),
                "next_offset": end if end < len(doc["text"]) else None}
