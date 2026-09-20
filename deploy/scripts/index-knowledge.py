#!/usr/bin/env python3
"""Mine exactly the prepared Markdown chunks and deterministic source rooms."""
from pathlib import Path
import json
from mempalace import miner
from mempalace.config import MempalaceConfig
from mempalace.ids import make_drawer_id_from_chunk
from knowledge_catalog import Catalogue, INDEX_STAMP, WING


def main():
    catalogue = Catalogue('/knowledge', '/opt/tt-knowledge/documents.json', make_drawer_id_from_chunk)
    rooms = sorted({doc['room'] for doc in catalogue.documents.values()})
    miner.load_config = lambda _: {'wing': WING, 'rooms': [{'name': room} for room in rooms]}
    miner.detect_room = lambda filepath, *_: catalogue.documents[str(filepath)]['room']

    def chunks(content, source_file, **_):
        doc = catalogue.documents[source_file]
        if content != doc['text'].replace('\r\n', '\n').replace('\r', '\n').strip():
            raise ValueError(f'Prepared source changed: {source_file}')
        return [dict(chunk, content=doc['text'][chunk['start']:chunk['end']]) for chunk in doc['chunks']]

    miner.chunk_text = chunks
    process_file = miner.process_file
    def process(**kwargs):
        kwargs['min_chunk_size'] = 1  # Do not silently discard short source documents.
        return process_file(**kwargs)
    miner.process_file = process
    palace_path = MempalaceConfig().palace_path
    miner.mine('/knowledge', palace_path, wing_override=WING,
               files=[Path(p) for p in sorted(catalogue.documents)])
    collection = miner.get_collection(palace_path)
    actual = collection.get(limit=len(catalogue.drawers) + 1, include=['metadatas', 'documents'])
    if set(actual['ids']) != set(catalogue.drawers):
        raise RuntimeError('Indexed drawer inventory does not match the prepared catalogue')
    for drawer_id, metadata, text in zip(actual['ids'], actual['metadatas'], actual['documents']):
        doc, chunk = catalogue.drawers[drawer_id]
        if metadata['room'] != doc['room'] or metadata['chunk_index'] != chunk['chunk_index']:
            raise RuntimeError('Indexed taxonomy/chunk metadata does not match the source')
        if text != doc['text'][chunk['start']:chunk['end']]:
            raise RuntimeError('Indexed content does not match the source chunk')
    stamp = Path(palace_path) / INDEX_STAMP
    temporary = stamp.with_suffix('.tmp')
    temporary.write_text(json.dumps({'fingerprint': catalogue.fingerprint}) + '\n')
    temporary.replace(stamp)
    print(f'Verified {len(catalogue.drawers)} drawers from {len(catalogue.documents)} complete documents.')


if __name__ == '__main__':
    main()
