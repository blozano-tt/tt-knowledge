"""Verify failures cannot publish a partial or unverified Git-derived bank."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('ingest', Path(__file__).parents[1] / 'scripts/ingest.py')
ingest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ingest)


class IngestTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.content = '# Source\nAn original paragraph.\n'
        (self.root / 'source.md').write_text(self.content)
        self.doc = {'document_id': 'source', 'file': 'source.md', 'tags': ['arch:test'],
                    'metadata': {'source_path': '/knowledge/source.md',
                                 'sha256': hashlib.sha256(self.content.encode()).hexdigest()}}
        self.write_manifest([self.doc])
        patcher = patch.object(ingest, 'ROOT', self.root)
        patcher.start()
        self.addCleanup(patcher.stop)

    def write_manifest(self, docs):
        (self.root / 'documents.json').write_text(json.dumps(docs))

    def test_bad_input_never_touches_live_bank(self):
        variants = [[], [self.doc, self.doc], [{**self.doc, 'file': '../outside.md'}],
                    [{**self.doc, 'metadata': {**self.doc['metadata'], 'sha256': 'wrong'}}]]
        for docs in variants:
            with self.subTest(docs=docs), patch.object(ingest, 'request') as request:
                self.write_manifest(docs)
                with self.assertRaises(ValueError):
                    ingest.main()
                request.assert_not_called()

    def test_corrupted_retained_original_fails_import(self):
        def request(method, path, data=None):
            if method == 'GET':
                return {'original_text': 'Truncated source'}
            return {}
        with patch.object(ingest, 'request', side_effect=request), self.assertRaisesRegex(RuntimeError, 'preserve'):
            ingest.main()

    def test_rebuild_is_scoped_and_checks_inventory(self):
        calls = []
        def request(method, path, data=None):
            calls.append((method, path, data))
            self.assertTrue(path.startswith('/v1/default/banks/tt-knowledge'))
            if path.endswith('?limit=1'):
                return {'total': 2}  # A stale extra document must fail verification.
            return {'original_text': self.content}
        with patch.object(ingest, 'request', side_effect=request), self.assertRaisesRegex(RuntimeError, 'inventory'):
            ingest.main()
        self.assertEqual(calls[0][:2], ('DELETE', '/v1/default/banks/tt-knowledge'))
        retained = next(data for method, path, data in calls if method == 'POST')
        self.assertEqual(retained['items'][0]['content'], self.content)
        self.assertFalse(retained['async'])


if __name__ == '__main__':
    unittest.main()
