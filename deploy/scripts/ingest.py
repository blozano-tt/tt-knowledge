#!/usr/bin/env python3
"""Rebuild a Git-owned bank using only Hindsight's documented HTTP API."""
import hashlib
import json
import os
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(os.environ.get('CORPUS_DIR', '/corpus'))
API = os.environ.get('HINDSIGHT_URL', 'http://hindsight:8888').rstrip('/')
BANK = '/v1/default/banks/tt-knowledge'


def request(method, path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = Request(API + path, data=body, method=method, headers={'Content-Type': 'application/json'})
    with urlopen(req, timeout=600) as response:
        return json.load(response)


def main():
    documents = json.loads((ROOT / 'documents.json').read_text())
    if not documents or len({d['document_id'] for d in documents}) != len(documents):
        raise ValueError('Expected a nonempty corpus with unique document IDs')
    for doc in documents:
        path = ROOT / doc['file']
        if not path.resolve().is_relative_to(ROOT.resolve()):
            raise ValueError('Document path escapes the prepared corpus')
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != doc['metadata']['sha256']:
            raise ValueError('Prepared source digest mismatch')
        doc['content'] = raw.decode('utf-8')
    # This bank is derived solely from Git. Other banks and database volumes are untouched.
    try:
        request('DELETE', BANK)
    except HTTPError as error:
        if error.code != 404:
            raise
    request('PUT', BANK, {'name': 'tt-knowledge'})
    for i, doc in enumerate(documents, 1):
        item = {key: doc[key] for key in ('document_id', 'content', 'metadata', 'tags')}
        request('POST', BANK + '/memories', {'items': [item], 'async': False})
        stored = request('GET', BANK + '/documents/' + doc['document_id'])
        if stored['original_text'] != doc['content']:
            raise RuntimeError('Hindsight did not preserve the original document exactly')
        print(f"[{i}/{len(documents)}] verified {doc['metadata']['source_path']}", flush=True)
    listing = request('GET', BANK + '/documents?limit=1')
    if listing['total'] != len(documents):
        raise RuntimeError('Unexpected document inventory after ingestion')
    print(f"Verified {len(documents)} exact original documents in tt-knowledge.")


if __name__ == '__main__':
    main()
