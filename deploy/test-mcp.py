#!/usr/bin/env python3
"""End-to-end HTTPS smoke test; install test dependencies from requirements-test.txt."""
import argparse
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess

import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError


def unpack(result):
    if result.is_error:
        raise RuntimeError(str(result.content))
    data = json.loads(next(item.text for item in result.content if item.type == "text"))
    if "error" in data:
        raise RuntimeError(data["error"])
    return data


async def test_retrieval(session, root):
    """Check the public contract against exact prepared sources, not model answers."""
    manifest = json.loads((root / '.build/documents.json').read_text())['documents']
    expected_rooms = Counter()
    for doc in manifest.values():
        expected_rooms[doc['room']] += len(doc['chunks'])

    async def call(name, **args):
        # Leave room for protocol traffic under the shared-IP request quota.
        await asyncio.sleep(0.6)
        return unpack(await session.call_tool(name, args))

    rooms = await call('mempalace_list_rooms', wing='tt-knowledge')
    assert rooms['rooms'] == dict(expected_rooms), rooms
    taxonomy = await call('mempalace_get_taxonomy')
    assert taxonomy['taxonomy'] == {'tt-knowledge': dict(expected_rooms)}, taxonomy
    report = {'rooms': rooms['rooms'], 'noc_regressions': []}
    for arch, room, width in (('WormholeB0', 'wormhole-b0', '256 bits'),
                              ('BlackholeA0', 'blackhole-a0', '512 bits')):
        source = next(path for path in manifest if path.endswith(f'/{arch}/NoC/README.md'))
        original = (root / '.build/knowledge' / source.removeprefix('/knowledge/')).read_bytes().decode()
        document = await call('mempalace_get_document', source_path=source)
        assert document['complete'] and document['next_offset'] is None
        assert document['content'] == original
        assert document['sha256'] == hashlib.sha256(original.encode()).hexdigest()
        assert width in document['content']
        paragraph = next(p for p in original.split('\n\n') if 'buddy bit can change' in p)
        args = {'query': 'buddy bit changes at each hop in response to network congestion',
                'room': room, 'source_file': source, 'limit': 5}
        compact = await call('mempalace_search', **args)
        hits = compact['results']
        assert hits and all(hit['room'] == room and hit['source_path'] == source for hit in hits), hits
        match = next(hit for hit in hits if paragraph in hit['text'])
        assert all(set(hit) == {'drawer_id', 'source_path', 'room', 'section',
                                'chunk_index', 'chunk_count', 'text'} for hit in hits)
        drawer = await call('mempalace_get_drawer', drawer_id=match['drawer_id'])
        assert drawer['content'] == match['text']
        neighbor_id = drawer['previous_drawer_id'] or drawer['next_drawer_id']
        assert neighbor_id
        neighbor = await call('mempalace_get_drawer', drawer_id=neighbor_id)
        assert neighbor['source_path'] == source
        assert abs(neighbor['chunk_index'] - drawer['chunk_index']) == 1
        verbose = await call('mempalace_search', **args, verbose=True)
        assert [hit['drawer_id'] for hit in verbose['results']] == [hit['drawer_id'] for hit in hits]
        assert all('distance' in hit for hit in verbose['results'])
        compact_size, verbose_size = (len(json.dumps(result)) for result in (compact, verbose))
        assert compact_size < verbose_size
        # Room-only filtering must work independently of the source_path filter.
        widths = await call('mempalace_search', query='NoC flit width bits', room=room, limit=5)
        assert widths['results'] and all(hit['room'] == room for hit in widths['results'])
        assert any(width in hit['text'] for hit in widths['results']), widths
        report['noc_regressions'].append({'room': room, 'flit_width': width,
                                         'congestion_paragraph': 'complete', 'full_source': 'byte-exact UTF-8',
                                         'neighbors': 'passed', 'compact_chars': compact_size,
                                         'verbose_chars': verbose_size})
    # An unknown source is a tool-level error and cannot trigger an arbitrary file/URL fetch.
    denied = await session.call_tool('mempalace_get_document', {'source_path': '/etc/passwd'})
    assert 'Unknown source_path' in str(denied.content)
    return report


async def test(env_file):
    config = dict(line.split("=", 1) for line in env_file.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    domain = config["DOMAIN"].strip().strip("\"'")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain):
        raise ValueError("DOMAIN must be a hostname")
    url = f"https://{domain}/mcp"
    root = Path(__file__).resolve().parents[1]
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD:tt-knowledge/upstream/tt-isa-documentation"],
        text=True).strip()
    report = {"endpoint": url, "isa_revision": revision}
    async with httpx2.AsyncClient(timeout=120) as public:
        landing = await public.get(f"https://{domain}/")
        landing.raise_for_status()
        assert "text/html" in landing.headers["content-type"]
        assert "Public knowledge." in landing.text
        for path, content_type in (("styles.css", "text/css"),
                                   ("site.js", "javascript"),
                                   ("favicon.svg", "image/svg+xml")):
            asset = await public.get(f"https://{domain}/{path}")
            asset.raise_for_status()
            assert content_type in asset.headers["content-type"]
        report["public_website"] = "HTML and assets served without authentication"
        health = await public.get(f"https://{domain}/healthz")
        health.raise_for_status()
        assert health.text.strip() == "ok", health.text
        for path in ("/statusz", "/logstream/stream", "/sync/status"):
            denied = await public.get(f"https://{domain}{path}")
            assert denied.status_code == 404, (path, denied.status_code)
        oversized = await public.post(url, content=b"x" * 16385)
        assert oversized.status_code == 413
    report.update(https_health="ok", access="anonymous", private_routes="blocked", body_limit="16 KiB")
    async with httpx2.AsyncClient(timeout=120) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            async with ClientSession(*streams, read_timeout_seconds=120) as session:
                init = await session.initialize()
                report["server"] = init.server_info.model_dump()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert names == {"mempalace_search", "mempalace_get_drawer", "mempalace_list_drawers",
                                 "mempalace_list_wings", "mempalace_list_rooms", "mempalace_get_taxonomy",
                                 "mempalace_get_document"}
                report["advertised_tools"] = len(names)
                for name in ("mempalace_add_drawer", "mempalace_reconnect", "mempalace_event_wait"):
                    # Empty arguments cannot create a drawer if protection regresses.
                    try:
                        await session.call_tool(name, {})
                    except MCPError as exc:
                        assert exc.code == -32003, str(exc)
                    else:
                        raise AssertionError(f"Non-public tool was not refused: {name}")
                report["write_and_admin_dispatch"] = "refused: public read-only allowlist"
                listing = unpack(await session.call_tool("mempalace_list_drawers",
                                                        {"wing": "tt-knowledge", "limit": 1}))
                report["inventory"] = {key: value for key, value in listing.items()
                                       if key not in {"drawers", "results"}}
                report["searches"] = []
                queries = [("semantic", "Tensix SFPU floating point multiplication", None)]
                for arch in ("WormholeB0", "BlackholeA0"):
                    source = (f"/knowledge/upstream/github.com/tenstorrent/tt-isa-documentation/blob/"
                              f"{revision}/{arch}/TensixTile/TensixCoprocessor/SFPMUL.md")
                    queries.append((arch, "SFPMUL multiplication", source))
                for label, query, source in queries:
                    args = {"query": query, "wing": "tt-knowledge", "limit": 3}
                    if source:
                        args["source_file"] = source
                    result = unpack(await session.call_tool("mempalace_search", args))
                    hits = result.get("results", [])
                    assert hits, f"No ISA results for {label}"
                    hit = hits[0]
                    assert f"tt-isa-documentation/blob/{revision}/" in hit["source_path"]
                    if source:
                        assert hit["source_path"] == source
                    drawer = unpack(await session.call_tool("mempalace_get_drawer",
                                                           {"drawer_id": hit["drawer_id"]}))
                    assert drawer.get("content") or drawer.get("text"), "Drawer content is empty"
                    report["searches"].append({"test": label, "query": query,
                                               "source": hit["source_path"],
                                               "drawer_id": hit["drawer_id"],
                                               "excerpt": hit["text"][:350]})
                report['retrieval_contract'] = await test_retrieval(session, root)
    report["result"] = "passed"
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(__file__).with_name(".env"))
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = asyncio.run(test(args.env_file))
    output = json.dumps(report, indent=2) + "\n"
    if args.report:
        args.report.write_text(output)
    print(output, end="")
