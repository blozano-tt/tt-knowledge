import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from knowledge_catalog import Catalogue, INDEX_STAMP, document_record, markdown_chunks
from upstream_sources import ROOT, load_sources, source_room


def test_id(wing, room, source, index):
    return f'{room}:{source}:{index}'


class MarkdownTests(unittest.TestCase):
    def assert_lossless(self, text, chunks):
        end = 0
        for index, chunk in enumerate(chunks):
            self.assertFalse(text[end:chunk['start']].strip())
            self.assertGreater(chunk['end'], chunk['start'])
            self.assertEqual(chunk['chunk_index'], index)
            self.assertEqual(chunk['line_start'], text.count('\n', 0, chunk['start']) + 1)
            end = chunk['end']
        self.assertFalse(text[end:].strip())

    def test_never_cuts_sentences_fences_or_tables(self):
        paragraph = 'Routing description. ' * 100 + 'The buddy bit changes with congestion.'
        fence = '```python\n# Not a heading\n\n' + 'x = 1\n' * 200 + '```'
        table = '| Field | Meaning |\n| --- | --- |\n' + '| X | Value |\n' * 200
        text = '# NoC\n\n' + paragraph + '\n\n## Code\n\n' + fence + '\n\n' + table + '\n'
        chunks = markdown_chunks(text)
        excerpts = [text[c['start']:c['end']] for c in chunks]
        for block in (paragraph, fence, table):
            self.assertTrue(any(block.rstrip() in excerpt for excerpt in excerpts))
        self.assert_lossless(text, chunks)
        self.assertNotIn('Not a heading', ' / '.join(c['section'] for c in chunks))

    def test_short_documents_and_consecutive_headings(self):
        text = '# ISA\n\n## NoC\n\nShort.\n'
        chunks = markdown_chunks(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['section'], 'ISA / NoC')
        self.assert_lossless(text, chunks)
        self.assertEqual(len(markdown_chunks('Hi.')), 1)
        code = '    indented_code()\n'
        chunk, = markdown_chunks(code)
        self.assertEqual(code[chunk['start']:chunk['end']], code.rstrip())
        with self.assertRaisesRegex(ValueError, '65,536'):
            markdown_chunks('x' * 65537)

    def test_entire_pinned_corpus_and_noc_regressions(self):
        sources = load_sources()
        for source in sources:
            for name in source['files']:
                text = (ROOT / source['path'] / name).read_text()
                chunks = markdown_chunks(text)
                self.assert_lossless(text, chunks)
                if name in {'WormholeB0/NoC/README.md', 'BlackholeA0/NoC/README.md'}:
                    paragraph = next(p for p in text.split('\n\n') if 'buddy bit can change' in p)
                    self.assertTrue(any(paragraph in text[c['start']:c['end']] for c in chunks))
                    self.assertIn('256 bits' if name.startswith('Wormhole') else '512 bits', text)
                    self.assertEqual(source_room(source, name),
                                     'wormhole-b0' if name.startswith('Wormhole') else 'blackhole-a0')


class CatalogueTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.text = '# Unicode α\r\n\r\n' + ('Complete paragraph.\r\n\r\n' * 10)
        (self.root / 'source.md').write_bytes(self.text.encode())
        self.manifest = {'version': 1, 'documents': {'/knowledge/source.md':
            document_record(self.text, 'wormhole-b0', 'https://example.com/pinned/source.md')}}
        self.catalogue = Catalogue(self.root, self.manifest, test_id)

    def test_exact_full_document_and_paginated_reassembly(self):
        full = self.catalogue.get_document('/knowledge/source.md')
        self.assertTrue(full['complete'])
        self.assertEqual(full['content'], self.text)
        self.assertEqual(full['sha256'], hashlib.sha256(self.text.encode()).hexdigest())
        offset, pages = 0, []
        while offset is not None:
            page = self.catalogue.get_document('/knowledge/source.md', offset, 17)
            pages.append(page['content'])
            offset = page['next_offset']
            self.assertFalse(page['complete'])
        self.assertEqual(''.join(pages), self.text)

    def test_source_recovery_is_allowlisted_and_digest_checked(self):
        for path in ('/etc/passwd', '/knowledge/../source.md', 'https://example.com/source.md'):
            self.assertIn('error', self.catalogue.get_document(path))
        for offset, size in ((-1, 100), (99999, 100), (0, 0), (0, 65537)):
            self.assertIn('error', self.catalogue.get_document('/knowledge/source.md', offset, size))
        (self.root / 'source.md').write_text('Altered source')
        with self.assertRaisesRegex(ValueError, 'digest'):
            Catalogue(self.root, self.manifest, test_id)
        (self.root / 'source.md').unlink()
        (self.root / 'source.md').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'regular file'):
            Catalogue(self.root, self.manifest, test_id)

    def test_neighbors_stay_in_the_same_document(self):
        text = '# A\n\nOne.\n\n# B\n\nTwo.\n\n# C\n\nThree.'
        (self.root / 'source.md').write_text(text)
        self.manifest['documents']['/knowledge/source.md'] = document_record(text, 'isa-shared', 'url')
        catalogue = Catalogue(self.root, self.manifest, test_id)
        ids = catalogue.documents['/knowledge/source.md']['drawer_ids']
        middle = catalogue.chunk(ids[1], detail=True)
        self.assertEqual((middle['previous_drawer_id'], middle['next_drawer_id']), (ids[0], ids[2]))
        self.assertIsNone(catalogue.chunk(ids[0], detail=True)['previous_drawer_id'])
        self.assertIsNone(catalogue.chunk(ids[2], detail=True)['next_drawer_id'])

    def test_server_requires_matching_verified_index(self):
        with self.assertRaisesRegex(RuntimeError, 'rebuild-index'):
            self.catalogue.verify_index(self.root)
        stamp = self.root / INDEX_STAMP
        stamp.write_text(json.dumps({'fingerprint': self.catalogue.fingerprint}))
        self.catalogue.verify_index(self.root)
        stamp.write_text(json.dumps({'fingerprint': 'old-index'}))
        with self.assertRaisesRegex(RuntimeError, 'rebuild-index'):
            self.catalogue.verify_index(self.root)

    def test_room_routing_is_by_exact_directory_prefix(self):
        source = {'path': 'tt-knowledge/upstream/isa', 'default_room': 'isa-shared',
                  'rooms': {'WormholeB0': 'wormhole-b0', 'BlackholeA0': 'blackhole-a0'}}
        self.assertEqual(source_room(source, 'WormholeB0/ComparisonToBlackhole.md'), 'wormhole-b0')
        self.assertEqual(source_room(source, 'WormholeB0Other/README.md'), 'isa-shared')
        self.assertEqual(source_room(source, 'README.md'), 'isa-shared')
        source['rooms']['../outside'] = 'bad'
        with self.assertRaises(ValueError):
            source_room(source, 'README.md')


if __name__ == '__main__':
    unittest.main()
