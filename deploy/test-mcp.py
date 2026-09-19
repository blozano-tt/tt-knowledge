#!/usr/bin/env python3
"""End-to-end HTTPS smoke test; install test dependencies from requirements-test.txt."""
import argparse
import asyncio
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


async def test(env_file):
    config = dict(line.split("=", 1) for line in env_file.read_text().splitlines()
                  if line.strip() and not line.lstrip().startswith("#"))
    domain = config["DOMAIN"].strip().strip("\"'")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain):
        raise ValueError("DOMAIN must be a hostname")
    token = config["MEMPALACE_MCP_HTTP_TOKEN"].strip().strip("\"'")
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
        for headers in ({}, {"Authorization": "Bearer intentionally-invalid"}):
            denied = await public.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                                       headers=headers)
            assert denied.status_code == 401, f"Expected 401, got {denied.status_code}"
    report.update(https_health="ok", missing_and_invalid_token="rejected")
    async with httpx2.AsyncClient(headers={"Authorization": f"Bearer {token}"}, timeout=120) as client:
        async with streamable_http_client(url, http_client=client) as streams:
            async with ClientSession(*streams, read_timeout_seconds=120) as session:
                init = await session.initialize()
                report["server"] = init.server_info.model_dump()
                tools = await session.list_tools()
                names = {tool.name for tool in tools.tools}
                assert {"mempalace_search", "mempalace_get_drawer"} <= names
                assert "mempalace_add_drawer" not in names
                report["advertised_tools"] = len(names)
                # Empty arguments cannot create a drawer even if write protection regresses.
                try:
                    await session.call_tool("mempalace_add_drawer", {})
                except MCPError as exc:
                    assert exc.code == -32003, str(exc)
                    report["write_dispatch"] = "refused: read-only"
                else:
                    raise AssertionError("Write tool was not refused at dispatch")
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
