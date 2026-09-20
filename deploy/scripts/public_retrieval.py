"""Compact MCP results with complete, pinned source recovery."""
from copy import deepcopy
from knowledge_catalog import Catalogue


def configure(server, catalogue=None):
    if catalogue is None:
        from mempalace.ids import make_drawer_id_from_chunk
        from mempalace.config import MempalaceConfig
        catalogue = Catalogue('/knowledge', '/opt/tt-knowledge/documents.json', make_drawer_id_from_chunk)
        catalogue.verify_index(MempalaceConfig().palace_path)
    original_search = server.TOOLS['mempalace_search']['handler']
    original_drawer = server.TOOLS['mempalace_get_drawer']['handler']
    original_list = server.TOOLS['mempalace_list_drawers']['handler']

    def search(verbose=False, **arguments):
        result = original_search(**arguments)
        if 'error' in result:
            return result
        out = dict(result) if verbose else {k: result[k] for k in (
            'query', 'error', 'partial', 'vector_disabled', 'vector_disabled_reason',
            'query_sanitized', 'warning', 'warnings', 'index_recovered'
        ) if k in result}
        hits = []
        for hit in result.get('results', []):
            try:
                compact = catalogue.chunk(hit['drawer_id'])
            except KeyError:
                return {'error': 'Index and source catalogue are out of sync; cannot return trustworthy excerpts'}
            # Preserve MemPalace's unboosted vector similarity, including null
            # for lexical-only hits. Do not reinterpret ranking boosts as confidence.
            compact['similarity'] = hit.get('similarity')
            hits.append(dict(hit, **compact) if verbose else compact)
        out['results'] = hits
        if not arguments.get('room') and len({hit['room'] for hit in hits}) > 1:
            out['room_warning'] = 'Results span rooms/architectures. Use room to scope architecture-specific claims.'
        return out

    def get_drawer(drawer_id, verbose=False):
        try:
            out = catalogue.chunk(drawer_id, detail=True)
        except KeyError:
            return {'error': 'Unknown drawer_id; search again after an index rebuild'}
        out['content'] = out.pop('text')
        if verbose:
            original = original_drawer(drawer_id)
            if 'error' in original:
                return original
            out['metadata'] = original.get('metadata', {})
        return out

    def list_drawers(verbose=False, **arguments):
        result = original_list(**arguments)
        if 'error' in result or verbose:
            return result
        out = dict(result)
        out['drawers'] = []
        for row in result.get('drawers', []):
            try:
                compact = catalogue.chunk(row.get('drawer_id') or row.get('id'))
            except KeyError:
                return {'error': 'Index and source catalogue are out of sync'}
            compact.pop('text')  # Inventory is not an excerpt; fetch content explicitly.
            out['drawers'].append(compact)
        return out

    for name, handler in (('mempalace_search', search), ('mempalace_get_drawer', get_drawer),
                          ('mempalace_list_drawers', list_drawers)):
        tool = server.TOOLS[name] = deepcopy(server.TOOLS[name])
        tool['handler'] = handler
        tool['input_schema']['properties']['verbose'] = {
            'type': 'boolean', 'default': False,
            'description': 'Include backend scores and diagnostic metadata. Off by default.'}
    search_tool = server.TOOLS['mempalace_search']
    search_tool['description'] = (
        'Search the tt-knowledge catalogue. Returns complete Markdown chunks, not full documents. '
        'For architecture-specific questions set room (wormhole-b0 or blackhole-a0); '
        'use mempalace_list_rooms for all rooms. Before making claims about absence or exceptions, '
        'read the full source with mempalace_get_document(source_path). '
        'Each hit includes MemPalace similarity: higher means closer semantic relevance, '
        'not factual confidence; null means unavailable (e.g. a lexical-only hit). '
        'Other scores/diagnostic metadata require verbose=true.')
    search_tool['input_schema']['properties']['room']['description'] = (
        'Exact room, e.g. wormhole-b0, blackhole-a0, isa-shared. Discover others with mempalace_list_rooms.')
    search_tool['input_schema']['properties']['cli_compatible']['const'] = False
    server.TOOLS['mempalace_get_drawer']['description'] = (
        'Read one complete Markdown chunk, with previous_drawer_id and next_drawer_id for traversal. '
        'Use mempalace_get_document(source_path) for the complete original source.')
    server.TOOLS['mempalace_get_document'] = {
        'description': 'Read the original pinned Markdown source exactly, using source_path from search. '
                       'This recovers context beyond chunk boundaries. complete=true means the whole source '
                       'is present; otherwise follow next_offset until null. Offsets count Unicode characters.',
        'handler': catalogue.get_document,
        'input_schema': {'type': 'object', 'required': ['source_path'], 'properties': {
            'source_path': {'type': 'string', 'description': 'Exact /knowledge/... source_path from a result'},
            'offset': {'type': 'integer', 'minimum': 0, 'default': 0},
            'max_chars': {'type': 'integer', 'minimum': 1, 'maximum': 65536, 'default': 65536}}}}
