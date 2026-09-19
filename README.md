# tt-knowledge

A human-reviewed source of factual Tenstorrent knowledge, exposed to agents through a read-only MemPalace MCP server.

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

Only reviewed Markdown files under `tt-knowledge/` are indexed. Each indexed Markdown file must declare who verified it, when it was verified, and its source(s). Drafts and templates live under `tt-knowledge/_templates/` and are excluded from the Docker image and MemPalace index.

The remote MemPalace server runs with `--read-only`, so agents cannot add or mutate knowledge through MCP. Changes happen through Git commits/PRs, followed by a clean re-index.

## Quick start

1. Add verified Markdown under `tt-knowledge/` using the template in `tt-knowledge/_templates/topic.md`.
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
