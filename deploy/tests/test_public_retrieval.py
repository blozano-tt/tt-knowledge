import importlib.util
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'deploy/scripts')]
from knowledge_catalog import Catalogue, document_record
from public_retrieval import configure

spec = importlib.util.spec_from_file_location('public_mcp', ROOT / 'deploy/scripts/public-mcp.py')
public = importlib.util.module_from_spec(spec)
spec.loader.exec_module(public)


class PublicRetrievalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        docs = {}
        for room in ('wormhole-b0', 'blackhole-a0'):
            text = '# NoC\n\nWhole paragraph. Buddy bit is congestion adaptive.\n\n# Next\n\nMore.'
            (root / f'{room}.md').write_text(text)
            docs[f'/knowledge/{room}.md'] = document_record(text, room, 'https://example.com/source')
        self.catalogue = Catalogue(root, {'version': 1, 'documents': docs},
                                   lambda wing, room, path, i: f'{room}-{i}')
        self.hits = [{'drawer_id': f'{room}-0', 'text': 'Truncated upstream snippet',
                      'distance': 0.2, 'similarity': 0.8, 'effective_distance': 0.1, 'closet_preview': 'Redundant',
                      'source_path': f'/knowledge/{room}.md', 'filed_at': 'timestamp'}
                     for room in ('wormhole-b0', 'blackhole-a0')]
        self.result = {'query': 'NoC', 'results': self.hits, 'partial': True, 'warning': 'Backend warning'}
        schema = {'type': 'object', 'properties': {'room': {'type': 'string'},
                  'cli_compatible': {'type': 'boolean'}, 'query': {'type': 'string'}}}
        tools = {name: {'handler': lambda **kw: {}, 'input_schema': schema}
                 for name in public.PUBLIC_TOOLS if name != 'mempalace_get_document'}
        tools['mempalace_search']['handler'] = lambda **kw: self.result
        tools['mempalace_get_drawer']['handler'] = lambda id: {'metadata': {'filed_at': 'timestamp'}}
        tools['mempalace_list_drawers']['handler'] = lambda **kw: {
            'drawers': [dict(hit, id=hit['drawer_id']) for hit in self.hits], 'total': 4}
        self.server = SimpleNamespace(TOOLS=tools, _READ_ONLY=True)
        self.server._http_dispatch = lambda req: self.call(req['params']['name'], **req['params']['arguments'])
        configure(self.server, self.catalogue)
        public.install(self.server)

    def call(self, name, **args):
        return self.server.TOOLS[name]['handler'](**args)

    def test_compact_and_verbose_preserve_full_chunk_and_rank(self):
        compact = self.call('mempalace_search', query='NoC')
        verbose = self.call('mempalace_search', query='NoC', verbose=True)
        self.assertTrue(compact['partial'])
        self.assertEqual(compact['warning'], 'Backend warning')
        self.assertIn('room_warning', compact)
        self.assertEqual([r['drawer_id'] for r in compact['results']], [r['drawer_id'] for r in self.hits])
        for c, v in zip(compact['results'], verbose['results']):
            self.assertEqual(set(c), {'drawer_id', 'source_path', 'room', 'section',
                                      'chunk_index', 'chunk_count', 'text', 'similarity'})
            self.assertEqual(c['similarity'], 0.8)
            self.assertEqual(c['similarity'], v['similarity'])
            self.assertIn('Buddy bit is congestion adaptive.', c['text'])
            self.assertEqual(v['text'], c['text'])
            self.assertIn('distance', v)
        self.assertNotIn('room_warning', self.call('mempalace_search', query='NoC', room='wormhole-b0'))

    def test_missing_vector_score_is_not_fabricated_from_rank_or_boost(self):
        self.hits[0]['similarity'] = None
        del self.hits[1]['similarity']
        results = self.call('mempalace_search', query='NoC')['results']
        self.assertTrue(all(hit['similarity'] is None for hit in results))

    def test_stale_drawer_fails_closed(self):
        self.hits[0]['drawer_id'] = 'stale'
        self.assertIn('error', self.call('mempalace_search', query='NoC'))

    def test_get_drawer_neighbors_and_compact_inventory(self):
        result = self.call('mempalace_get_drawer', drawer_id='wormhole-b0-0')
        self.assertEqual(result['next_drawer_id'], 'wormhole-b0-1')
        self.assertNotIn('metadata', result)
        self.assertIn('metadata', self.call('mempalace_get_drawer', drawer_id='wormhole-b0-0', verbose=True))
        listing = self.call('mempalace_list_drawers')
        self.assertEqual(listing['total'], 4)
        self.assertNotIn('text', listing['drawers'][0])
        self.assertNotIn('distance', listing['drawers'][0])

    def test_full_source_is_available_and_schema_limits_are_enforced(self):
        result = self.call('mempalace_get_document', source_path='/knowledge/wormhole-b0.md')
        self.assertTrue(result['complete'])
        self.assertIn('# Next', result['content'])
        for args in ({'max_chars': 65537}, {'offset': -1}, {'max_chars': 0}, {'url': 'https://example.com'}):
            request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                'name': 'mempalace_get_document', 'arguments': dict(source_path='/knowledge/wormhole-b0.md', **args)}}
            self.assertEqual(self.server._http_dispatch(request)['error']['code'], -32602)


if __name__ == '__main__':
    unittest.main()
