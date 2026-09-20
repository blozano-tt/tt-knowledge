# Approved upstream knowledge

Upstream repositories are immutable inputs at the commit recorded by the parent
repository's Git submodule entry. Their existing structure is preserved; they do
not need to fit the local hardware, software, and glossary buckets.

`upstream-sources.json` registers each source's HTTPS repository URL, trust
rationale, include patterns, and optional room routing. Only matching tracked `.md` files are indexed.
Patterns use Python `fnmatch` semantics, where `*` can match directory separators.
Source approval means we trust this publisher for the stated subject; it does not
mean every statement has been individually checked by this repository's authors.

Use `rooms` to map source directory prefixes to stable room names and
`default_room` for other selected files. For example, the ISA catalogue maps
`WormholeB0` to `wormhole-b0` and `BlackholeA0` to `blackhole-a0`, with
`isa-shared` as the default. The longest matching directory prefix wins.
Routing never examines prose. Without explicit configuration, the upstream
checkout's directory name is the room; room names must be lowercase slugs.

## Add a source

```bash
git submodule add https://github.com/OWNER/REPO.git tt-knowledge/upstream/REPO
git submodule update --init --recursive
```

Add its registration to `upstream-sources.json`, selecting factual documentation
and omitting repository administration files. Keep the default submodule name
equal to its path. Run:

```bash
python3 scripts/prepare_knowledge.py
python3 -m unittest discover -s scripts/tests
git add .gitmodules upstream-sources.json tt-knowledge/upstream/REPO
```

Commit the source registration and submodule entry together. Submodules must be
clean and initialized, at their recorded revisions. Nested submodules are checked
out recursively, but their documents are not automatically selected by a parent
source's tracked-file list; add explicit ingestion support before relying on them.

## Adopt an upstream update

```bash
git -C tt-knowledge/upstream/REPO fetch origin
git -C tt-knowledge/upstream/REPO checkout --detach <reviewed-commit>
git -C tt-knowledge/upstream/REPO submodule update --init --recursive
```

Stage the new gitlink before validation (the validator checks the index):

```bash
git add tt-knowledge/upstream/REPO
python3 scripts/prepare_knowledge.py
```

Review the upstream diff and commit the revision change. Do not run the parent
`submodule update` before staging the changed gitlink: it would restore the old
recorded revision. To initialize nested modules after switching revisions, run
`git -C tt-knowledge/upstream/REPO submodule update --init --recursive` instead.
Production only follows commits recorded in this repository, never a moving
upstream branch.

## Provenance and citations

The prepared corpus copies upstream Markdown byte-for-byte into paths such as:

```text
/knowledge/upstream/github.com/tenstorrent/tt-isa-documentation/blob/<commit>/WormholeB0/README.md
```

MemPalace's project miner stores the document path as `source_file` on each chunk.
To cite an upstream result, replace `/knowledge/upstream/` with `https://` and
URL-encode any spaces or other special characters in the path. The resulting
GitHub URL identifies the exact source revision. The original architecture path
is preserved; never transfer Wormhole B0 behavior to Blackhole A0 without evidence.
Full-document and drawer retrieval also return a pinned `source_url` directly.

The image also includes `/opt/tt-knowledge/sources.json` with the selected files,
repository URLs, and revisions, `/opt/tt-knowledge/documents.json` with source
digests, rooms, and Markdown chunk boundaries, and upstream license notices under
`/opt/tt-knowledge/licenses/`. These administrative files are not mined. Linked
diagrams and other non-Markdown assets remain accessible in the upstream repo but
are not indexed by this pipeline.

## Deployment

Clone with `--recurse-submodules`. CI checks out submodules recursively, and
`deploy/rebuild-index.sh` initializes and updates them recursively before preparing
the corpus and invoking Docker Compose. Missing sources or validation errors fail
before the live index is stopped or deleted.
