# tt-knowledge

A curated source of factual Tenstorrent knowledge, exposed to agents through a read-only MemPalace MCP server.

Visit [tt-knowledge.dev](https://tt-knowledge.dev/) for an introduction, source links, and agent connection instructions. The MCP endpoint is `https://tt-knowledge.dev/mcp`; no authentication is required. Public access is read-only and rate limited.

[`blozano-tt/tt-knowledge`](https://github.com/blozano-tt/tt-knowledge) is the primary knowledge catalogue and source of truth for this project. It brings together curated local articles and registered upstream catalogues. `tenstorrent/tt-isa-documentation` is one such upstream catalogue; its current coverage does not define the scope of tt-knowledge. Imported documents retain their original attribution and provenance.

MemPalace is only the retrieval layer. The deployed index is intentionally disposable and is rebuilt from scratch from the Markdown under [`tt-knowledge/`](tt-knowledge/) whenever the corpus changes.

## Repository layout

```text
tt-knowledge/
├── tt-knowledge/          # human-reviewed Markdown corpus
├── deploy/                # Docker Compose deployment
├── site/                  # public static website served by Caddy
├── scripts/               # repository validation
└── .github/               # review/validation policy
```

## Trust model

The corpus contains two kinds of material:

- **Local articles** declare `verified_by`, `verified_on`, and `sources` in front matter.
- **Approved upstream repositories** live as pinned Git submodules under `tt-knowledge/upstream/`. [`upstream-sources.json`](upstream-sources.json) records their origin, trust rationale, and selected document paths. Approving a source does not claim that every upstream statement was individually verified here.

Upstream files remain unchanged. Deployment selects only registered Markdown and keeps repository, commit, and original path in each indexed filename. Architecture directories such as `WormholeB0` and `BlackholeA0` remain distinct. Templates, Git metadata, and repository administration files are excluded from the searchable corpus. See [upstream source management](UPSTREAM.md).

The remote MemPalace server runs with `--read-only`, so agents cannot add or mutate knowledge through MCP. Changes happen through Git commits/PRs, followed by a clean re-index.

## Retrieving complete, architecture-specific sources

Search with `room: "wormhole-b0"` or `room: "blackhole-a0"` for architecture-specific questions. `mempalace_list_rooms` discovers all rooms; shared ISA documents use `isa-shared`. Routing follows source directories, not mentions of other architectures in the prose.

Search returns complete Markdown blocks with compact provenance. Use `mempalace_get_document(source_path)` to read the exact original pinned document, especially before making claims about missing features or exceptions. Follow `next_offset` for paginated documents. `mempalace_get_drawer(drawer_id)` supplies neighboring drawer IDs for local context. Search, drawer retrieval, and drawer listings accept `verbose: true` for backend diagnostic metadata; the default omits it.

## Quick start

1. Add verified local Markdown using `tt-knowledge/_templates/topic.md`, or register a pinned upstream source following [UPSTREAM.md](UPSTREAM.md).
2. Configure and deploy using [`deploy/README.md`](deploy/README.md).
3. Enable a GitHub ruleset for `main` that requires pull requests and CODEOWNERS approval if you want review enforcement rather than convention alone.

## Updating production

For website-only changes, follow the [static site update instructions](deploy/README.md#static-website) to avoid rebuilding the knowledge index.

On the server:

```bash
./deploy/update.sh
```

That fast-forwards the checkout, rebuilds the MemPalace image, destroys the old MemPalace/Qdrant state, mines the current corpus from scratch, and restarts the read-only MCP endpoint. The embedding-model cache and Caddy TLS certificates are preserved.

## Why full rebuilds?

For this repository, stale historical facts are worse than re-indexing cost. MemPalace is designed as a memory system and has supported retaining or synchronizing prior versions over time. `tt-knowledge` deliberately uses a stronger invariant: the live index is derived only from the current Git checkout.
