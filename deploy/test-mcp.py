#!/usr/bin/env python3
"""Exercise native MCP retrieval and the deployed proxy against prepared Git sources."""
import argparse
import asyncio
import json
import time
from pathlib import Path

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def unpack(result):
    if result.is_error:
        raise AssertionError(str(result.content))
    value = json.loads(next(c.text for c in result.content if c.type == 'text'))
    assert 'error' not in value, value
    return value


async def test(args):
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / '.build/documents.json').read_text())
    by_id = {d['document_id']: d for d in manifest}
    base = args.url.removesuffix('/mcp').rstrip('/')
    report = {'endpoint': args.url, 'documents_expected': len(manifest)}
    if not args.skip_proxy_checks:
        async with httpx2.AsyncClient(timeout=120) as client:
            landing = await client.get(base + '/')
            assert landing.status_code == 200 and 'Admin dashboard' in landing.text
            for asset in ('styles.css', 'site.js', 'favicon.svg'):
                assert (await client.get(base + '/landing/' + asset)).status_code == 200
            report['public_landing'] = 'HTML and assets accessible without login'
            for path in ('/dashboard', '/api/banks', '/api/banks.json', '/_next/static/test.js'):
                response = await client.get(base + path)
                assert response.status_code == 401, (path, response.status_code)
            for path in ('/v1/default/banks', '/mcp/other-bank/', '/docs', '/openapi.json'):
                assert (await client.get(base + path)).status_code == 404, path
            assert (await client.get(base + '/healthz')).status_code == 200
            assert (await client.post(args.url, content=b'x' * 16385)).status_code == 413
            if args.admin_password_file:
                auth = httpx2.BasicAuth('admin', args.admin_password_file.read_text().strip())
                page = await client.get(base + '/dashboard', auth=auth, follow_redirects=True)
                assert page.status_code == 200 and 'text/html' in page.headers['content-type']
                banks = await client.get(base + '/api/banks', auth=auth)
                assert banks.status_code == 200 and 'tt-knowledge' in banks.text, banks.status_code
                report['dashboard_login'] = 'passed'
        report.update(dashboard_anonymous='401 on pages, assets and UI API',
                      private_routes='404', request_size_limit='16 KiB')
    async with httpx2.AsyncClient(timeout=180, headers={'X-Bank-Id': 'not-the-public-bank'}) as client:
        async with streamable_http_client(args.url, http_client=client) as streams:
            async with ClientSession(*streams, read_timeout_seconds=180) as session:
                init = await session.initialize()
                names = {t.name for t in (await session.list_tools()).tools}
                assert names == {'recall', 'get_document', 'list_documents'}, names
                report['server'] = init.server_info.model_dump()
                report['tools'] = sorted(names)

                report['recall_seconds'] = []

                async def call(name, **kw):
                    await asyncio.sleep(0.6)
                    started = time.monotonic()
                    result = unpack(await session.call_tool(name, kw))
                    if name == 'recall':
                        elapsed = round(time.monotonic() - started, 2)
                        report['recall_seconds'].append(elapsed)
                        print(f'Native recall completed in {elapsed}s', flush=True)
                    return result

                listing = await call('list_documents', limit=1)
                assert listing['total'] == len(manifest), listing
                report['documents_indexed'] = listing['total']
                report['regressions'] = []
                for arch, tag, width in [('WormholeB0', 'arch:wormhole-b0', '256 bits'),
                                          ('BlackholeA0', 'arch:blackhole-a0', '512 bits')]:
                    expected = next(d for d in manifest if d['metadata']['source_path'].endswith(f'/{arch}/NoC/README.md'))
                    for query in ('NoC buddy bit congestion adaptive per hop', 'NoC flit width bits'):
                        hits = (await call('recall', query=query, tags=[tag], tags_match='all_strict',
                                           budget='low', max_tokens=4096))['results']
                        assert hits and all(tag in h['tags'] for h in hits), hits
                        match = next((h for h in hits if h['document_id'] == expected['document_id']), None)
                        assert match, f'No NoC original reachable from recall: {arch}: {query}'
                        assert match['metadata']['source_url'] == expected['metadata']['source_url']
                        doc = await call('get_document', document_id=match['document_id'])
                        original = (root / '.build' / expected['file']).read_bytes().decode('utf-8')
                        assert doc['original_text'] == original
                        assert doc['document_metadata']['source_url'] == expected['metadata']['source_url']
                        assert width in doc['original_text']
                        assert 'buddy bit can change at each hop in response to network congestion' in doc['original_text']
                        report['regressions'].append({'architecture': arch, 'query': query,
                            'document_id': match['document_id'], 'source_url': match['metadata']['source_url'],
                            'flit_width': width,
                            'full_source_exact': True, 'congestion_clause': 'present'})
                    hits = (await call('recall', query='SFPMUL SFPU floating point multiplication',
                                      tags=[tag], tags_match='all_strict', budget='low', max_tokens=4096))['results']
                    assert hits and all(tag in h['tags'] for h in hits)
                    match = next((h for h in hits if h['metadata']['source_path'].endswith('/SFPMUL.md')), None)
                    assert match, f'SFPMUL not recalled: {arch}'
                    doc = await call('get_document', document_id=match['document_id'])
                    assert doc['original_text'] == (root / '.build' / by_id[match['document_id']]['file']).read_bytes().decode()
                for tool in ('retain', 'reflect', 'delete_bank'):
                    await asyncio.sleep(0.6)
                    denied = await session.call_tool(tool, {})
                    assert denied.is_error, f'Unexpected tool dispatch: {tool}'
                missing = await session.call_tool('get_document', {'document_id': '/etc/passwd'})
                assert missing.is_error or 'error' in json.loads(next(c.text for c in missing.content if c.type == 'text'))
                report['mutations'] = 'unregistered and refused'
                report['bank_header_override'] = 'ignored; fixed public bank'
    report['result'] = 'passed'
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='https://tt-knowledge.dev/mcp')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--admin-password-file', type=Path)
    parser.add_argument('--skip-proxy-checks', action='store_true', help='Test a private native bank endpoint before cutover')
    args = parser.parse_args()
    report = asyncio.run(test(args))
    text = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.write_text(text)
    print(text, end='')
