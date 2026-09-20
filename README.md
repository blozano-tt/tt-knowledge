# tt-knowledge

A curated catalogue of public Tenstorrent knowledge, served to agents by Hindsight's native read-only MCP tools.

[`blozano-tt/tt-knowledge`](https://github.com/blozano-tt/tt-knowledge) is this project's primary knowledge catalogue and source of truth. It combines human-reviewed local Markdown with registered, pinned upstream catalogues. [`tenstorrent/tt-isa-documentation`](https://github.com/tenstorrent/tt-isa-documentation) is one upstream catalogue, not the scope of the project. Imported documents retain their original attribution.

## Connect an agent

Configure a remote **Streamable HTTP** MCP server:

```json
{
  "mcpServers": {
    "tt-knowledge": {
      "url": "https://tt-knowledge.dev/mcp"
    }
  }
}
```

Client configuration formats vary. The URL needs **no bearer token**. Access is anonymous, read-only, and rate limited. Clients should back off on HTTP 429. After migrating from MemPalace, reconnect or refresh the tool list; old tool names are gone.

Only three native Hindsight tools are exposed:

1. `recall(query, ...)` finds relevant source chunks and their `document_id`.
2. `get_document(document_id)` returns the retained original Markdown in `original_text`.
3. `list_documents(...)` browses the bank's sources.

**Read the full original before answering**, particularly when a claim depends on exceptions or the absence of a feature. Search excerpts alone are incomplete evidence. Cite the pinned `source_url` from result metadata or `document_metadata`.

For architecture-specific recall, use `tags: ["arch:wormhole-b0"]` or `tags: ["arch:blackhole-a0"]` with `tags_match: "all_strict"`. Shared ISA documents use `scope:isa-shared`. Tags come from source directories, not inferred prose.

## How it works

```text
Verified Markdown + pinned Git submodules
    → documented retain API, one complete file per document
    → Hindsight native chunks + local embeddings in PostgreSQL
    → native recall → document_id → native get_document → original Markdown
```

Deployment uses the unmodified official Hindsight image. `LLM_PROVIDER=none` and `RETAIN_EXTRACTION_MODE=chunks` disable LLM extraction and generated knowledge; local CPU models provide embeddings and reranking. This repository supplies source validation, ordinary API ingestion, and proxy configuration. It does not replace Hindsight's chunker, ranking, MCP server, or response metadata.

The bank is disposable and rebuilt from the current Git checkout. The importer verifies that every stored original exactly matches its input. Neither generated knowledge pages nor session transcripts enter the corpus.

## Dashboard and deployment

[tt-knowledge.dev](https://tt-knowledge.dev/) introduces the catalogue and guides agents through setup. Its **Admin dashboard** button opens [Hindsight's built-in administration UI](https://tt-knowledge.dev/dashboard), protected by a separate username/password. Public agents do not need those credentials. The UI can perform administrative writes; Git remains the durable source of truth, and rebuilds discard manual changes to the `tt-knowledge` bank.

See [`deploy/README.md`](deploy/README.md) for Docker Compose setup, updates, internal VM deployment, and end-to-end tests. On the server, `./deploy/update.sh` recursively updates the checkout, validates sources, and rebuilds the bank.

## Contributing knowledge

- Local articles use [`tt-knowledge/_templates/topic.md`](tt-knowledge/_templates/topic.md) and declare `verified_by`, `verified_on`, and `sources`.
- Upstream catalogues are approved in [`upstream-sources.json`](upstream-sources.json), with repository provenance, selected paths, and optional tags. Approval trusts the publisher for the stated subject; it does not claim individual verification of every statement.
- Follow [UPSTREAM.md](UPSTREAM.md) to register or update a source. Recursive checkout preserves each recorded submodule revision.

Templates, Git metadata, and repository administration files are excluded from ingestion. Changes reach the public service through Git and a rebuild. Enable GitHub rulesets requiring review/CODEOWNERS if review enforcement is desired.
