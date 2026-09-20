#!/usr/bin/env python3
"""Copy approved Markdown and prepare native Hindsight retain metadata."""
import hashlib
import json
import shutil
from urllib.parse import quote

from upstream_sources import ROOT, git, indexed_path, load_sources, source_tags
from validate_knowledge import indexed_markdown_files, main as validate

CATALOGUE = 'https://github.com/blozano-tt/tt-knowledge'


def prepare():
    if validate():
        raise SystemExit('Corpus validation failed')
    sources = load_sources()
    output = ROOT / '.build'
    if output.exists():
        shutil.rmtree(output)
    (output / 'knowledge').mkdir(parents=True)
    (output / 'licenses').mkdir()
    documents = []

    def add(file, relative, source_url, tags):
        target = output / 'knowledge' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file, target)
        raw = file.read_bytes()
        raw.decode('utf-8')  # Reject invalid text before touching the live bank.
        source_path = '/knowledge/' + relative.as_posix()
        documents.append({
            'document_id': hashlib.sha256(source_path.encode()).hexdigest(),
            'file': target.relative_to(output).as_posix(), 'tags': tags,
            'metadata': {'catalogue_repository': CATALOGUE, 'source_path': source_path,
                         'source_url': source_url, 'sha256': hashlib.sha256(raw).hexdigest()}})

    revision = git(ROOT, 'rev-parse', 'HEAD')
    for file in indexed_markdown_files():
        relative = file.relative_to(ROOT / 'tt-knowledge')
        add(file, relative, f'{CATALOGUE}/blob/{revision}/tt-knowledge/{quote(relative.as_posix())}',
            ['source:tt-knowledge', 'category:' + (relative.parts[0].lower() if len(relative.parts) > 1 else 'local')])
    for source in sources:
        checkout = ROOT / source['path']
        for name in source['files']:
            add(checkout / name, indexed_path(source, name),
                f"{source['repository'].removesuffix('.git')}/blob/{source['revision']}/{quote(name)}",
                source_tags(source, name))
        licenses = output / 'licenses' / checkout.name
        licenses.mkdir()
        for file in checkout.glob('LICENSE*'):
            if file.is_file() and not file.is_symlink():
                shutil.copy2(file, licenses / file.name)
    (output / 'documents.json').write_text(json.dumps(documents, indent=2) + '\n')
    (output / 'sources.json').write_text(json.dumps(sources, indent=2) + '\n')
    print(f'Prepared {len(documents)} original documents; chunking is performed by Hindsight.')


if __name__ == '__main__':
    prepare()
