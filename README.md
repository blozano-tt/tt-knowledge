# tt-knowledge

A curated source of factual Tenstorrent knowledge, exposed to agents through a read-only MemPalace MCP server.

The Git repository is the source of truth. MemPalace is only the retrieval layer. The deployed index is intentionally disposable and is rebuilt from scratch from the Markdown under [`tt-knowledge/`](tt-knowledge/) whenever the corpus changes.

## Repository layout

```text
tt-knowledge/
├── tt-knowledge/          # human-reviewed Markdown corpus
├── deploy/                # Docker Compose deployment
├── scripts/               # repository validation
└── .github/               # review/validation policy
```

## Trust model

The corpus contains two kinds of material:

- **Local articles** declare `verified_by`, `verified_on`, and `sources` in front matter.
- **Approved upstream repositories** live as pinned Git submodules under `tt-knowledge/upstream/`. [`upstream-sources.json`](upstream-sources.json) records their origin, trust rationale, and selected document paths. Approving a source does not claim that every upstream statement was individually verified here.

Upstream files remain unchanged. Deployment selects only registered Markdown and keeps repository, commit, and original path in each indexed filename. Architecture directories such as `WormholeB0` and `BlackholeA0` remain distinct. Templates, Git metadata, and repository administration files are excluded from the searchable corpus. See [upstream source management](UPSTREAM.md).

The remote MemPalace server runs with `--read-only`, so agents cannot add or mutate knowledge through MCP. Changes happen through Git commits/PRs, followed by a clean re-index.

## Quick start

1. Add verified local Markdown using `tt-knowledge/_templates/topic.md`, or register a pinned upstream source following [UPSTREAM.md](UPSTREAM.md).
2. Configure and deploy using [`deploy/README.md`](deploy/README.md).
3. Enable a GitHub ruleset for `main` that requires pull requests and CODEOWNERS approval if you want review enforcement rather than convention alone.

## Updating production

On the server:

```bash
./deploy/update.sh
```

That fast-forwards the checkout, rebuilds the MemPalace image, destroys the old MemPalace/Qdrant state, mines the current corpus from scratch, and restarts the read-only MCP endpoint. The embedding-model cache and Caddy TLS certificates are preserved.

## Why full rebuilds?

For this repository, stale historical facts are worse than re-indexing cost. MemPalace is designed as a memory system and has supported retaining or synchronizing prior versions over time. `tt-knowledge` deliberately uses a stronger invariant: the live index is derived only from the current Git checkout.
