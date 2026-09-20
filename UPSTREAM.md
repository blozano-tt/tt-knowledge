# Approved upstream knowledge

Upstream repositories are immutable inputs at the commit recorded by the parent
repository's Git submodule entry. Their existing structure is preserved; they do
not need to fit the local hardware, software, and glossary buckets.

`upstream-sources.json` registers each source's HTTPS repository URL, trust
rationale, include patterns, and optional architecture tags. Only matching tracked `.md` files are indexed.
Patterns use Python `fnmatch` semantics, where `*` can match directory separators.
Source approval means we trust this publisher for the stated subject; it does not
mean every statement has been individually checked by this repository's authors.

Use `tags` for labels shared by every document, `path_tags` for directory-prefix
mappings, and `default_tags` when no prefix matches. The ISA catalogue maps
`WormholeB0` to `arch:wormhole-b0` and `BlackholeA0` to `arch:blackhole-a0`, with
`scope:isa-shared` as the default. The longest matching prefix wins. These labels
are native Hindsight tags; routing never examines prose or generates a taxonomy.

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

Each document is submitted whole to Hindsight's retain API with `document_id`,
`tags`, and metadata: `catalogue_repository`, `source_path`, `source_url`, `sha256`.
`source_url` identifies the exact Git revision. The original architecture path
is preserved; never transfer Wormhole B0 behavior to Blackhole A0 without evidence.
Use a recall hit's `document_id` with native `get_document` to read `original_text`
and `document_metadata`. The importer checks every original against Git after retain.

`.build/documents.json` records the input inventory and digests; `.build/sources.json`
records registered repositories and revisions. Upstream license notices are copied
under `.build/licenses/`. No chunk boundaries or retrieval implementation are stored
in this repository: Hindsight owns those. Linked diagrams and other non-Markdown
assets remain accessible in the upstream repo but are not indexed by this pipeline.

## Deployment

Clone with `--recurse-submodules`. CI checks out submodules recursively, and
`deploy/rebuild-index.sh` initializes and updates them recursively before preparing
the corpus and invoking Docker Compose. Missing sources or validation errors fail
before the live index is stopped or deleted.
