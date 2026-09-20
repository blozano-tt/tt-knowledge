# Deployment

This deployment targets a small public Linux VM such as an Oracle Cloud Always Free/Always Free-eligible instance. It uses:

- **MemPalace** for semantic retrieval and MCP over HTTP.
- **Qdrant** as the disposable vector/text backend.
- **Caddy** for automatic public TLS and the static landing page.
- **Nginx** for public MCP request and concurrency limits.
- A **read-only MCP server**. The Git repository is the only write path for knowledge.

The MemPalace image contains validated local articles and selected Markdown from approved upstream sources. Before building, the deployment script initializes submodules recursively and prepares `.build/knowledge`. The Docker build uses this prepared corpus; Git metadata, templates, and deployment secrets are excluded. Upstream license notices and a source manifest are retained outside the searchable corpus.

## 1. Provision the VM

An Ubuntu ARM64 or AMD64 VM is fine; the published MemPalace CPU image is multi-architecture.

At the cloud firewall/security-list level, allow inbound:

- TCP 22 from wherever you administer the VM.
- TCP 80 from the internet (needed for normal ACME/HTTP handling).
- TCP 443 from the internet.
- UDP 443 from the internet if you want HTTP/3; it is optional.

Do **not** expose Qdrant port 6333, MemPalace port 8765, or gateway port 8080 publicly. Compose keeps Qdrant on an internal Docker network and only Caddy publishes public ports.

## 2. Install Git, Python, Docker + the Compose plugin

Install Git and Python 3.10 or newer on the host for submodule checkout and corpus validation. Install current Docker Engine and the Docker Compose plugin using Docker's official instructions for your Linux distribution. Confirm:

```bash
docker --version
docker compose version
```

If you add your login user to the `docker` group, log out/in before continuing.

## 3. Clone the public repository

```bash
git clone --recurse-submodules https://github.com/blozano-tt/tt-knowledge.git
cd tt-knowledge
```

## 4. Create DNS

Create an `A` record such as:

```text
knowledge.example.com -> <VM public IPv4>
```

Wait until the name resolves to the VM. Caddy will request and renew the TLS certificate automatically.

For an experiment without your own domain, an IP-based DNS service can provide a hostname such as `tt-knowledge.146-235-201-105.sslip.io`. Set `DOMAIN` to the hostname using **your** VM's public IP. This depends on that DNS provider; use your own domain for a permanent deployment.

## 5. Configure the deployment

```bash
cp deploy/.env.example deploy/.env
```

Edit `deploy/.env` and set:

```dotenv
DOMAIN=knowledge.example.com
```

`deploy/.env` is gitignored. No bearer token is needed. For an existing deployment, remove the old `MEMPALACE_MCP_HTTP_TOKEN` line; Compose explicitly clears it inside the server.

## 6. Build, mine, and start

```bash
./deploy/rebuild-index.sh
```

The script deliberately performs a **clean rebuild**:

1. Runs `git submodule sync --recursive` and `git submodule update --init --recursive`, validates the pinned source checkouts, prepares the selected Markdown, and builds `tt-knowledge-mempalace:local`. Missing submodule contents are cloned at this step even if the original clone omitted `--recurse-submodules`.
2. Stops MemPalace/Qdrant.
3. Deletes the old Qdrant and MemPalace state volumes.
4. Preserves the embedding-model cache and Caddy TLS state. A network-isolated, one-shot Compose service initializes volume ownership; indexing and serving run as UID 1000. Failure to remove old index volumes aborts the rebuild.
5. Starts empty Qdrant.
6. Mines `/knowledge` into the `tt-knowledge` wing.
7. Starts MemPalace with `--read-only` and the public retrieval allowlist.
8. Starts the private Nginx gateway and Caddy on ports 80/443.

This guarantees the searchable corpus comes from the current checkout instead of accumulating historical/stale document versions.

## 7. Verify

```bash
./deploy/status.sh
```

Or directly:

```bash
curl https://knowledge.example.com/healthz
```

Expected body:

```text
ok
```

The MCP endpoint is:

```text
https://knowledge.example.com/mcp
```

No authentication, API key, or authorization header is required. For Claude Code:

```bash
claude mcp add --scope user --transport http tt-knowledge https://knowledge.example.com/mcp
```

Other remote MCP clients use the same URL with Streamable HTTP and no authentication. Remove old bearer headers from existing client configurations. In Claude Code, remove the previous entry with `claude mcp remove --scope user tt-knowledge`, then add it again.

### End-to-end MCP test

Run this from the deployed checkout, with its prepared `.build` corpus and `DOMAIN` in `deploy/.env`:

```bash
python3 -m venv /tmp/tt-knowledge-mcp-test
/tmp/tt-knowledge-mcp-test/bin/pip install -r deploy/requirements-test.txt
/tmp/tt-knowledge-mcp-test/bin/python deploy/test-mcp.py
```

The test uses the official MCP client against the public HTTPS endpoint. It checks the public landing page and assets, TLS/health, connects without credentials, checks the public tool allowlist, blocks private routes and oversized requests, verifies that write and administrative calls are refused, performs semantic search, and fetches indexed `SFPMUL` content from both Wormhole and Blackhole at the pinned ISA revision. Failures return a nonzero exit status. Its JSON report contains retrieval evidence. Use `--report /path/to/report.json` to save it.

Retrieval regressions also verify the populated taxonomy against the build manifest, both NoC flit widths with architecture filters, the complete congestion-adaptive buddy-bit paragraph in search results, neighboring chunk traversal, byte-exact full-source recovery, and compact versus verbose responses.

## Static website

Caddy serves `/` and the explicitly listed website assets from the read-only `site/` mount. Only `/mcp` and `/healthz` reach the private gateway. Other paths return 404, including MemPalace’s status, sync, and event-stream routes. The website has no build step, external fonts, or analytics service.

Edit `site/index.html`, `site/styles.css`, or `site/site.js`. The connection examples use the current page origin in JavaScript; the HTML fallback names the public deployment at `tt-knowledge.dev`. For a fork, update the fallback URL, project links, source description, and maintainer information in the HTML too.

For a change confined to the website and Caddy configuration, from the VM checkout:

```bash
git pull --ff-only --recurse-submodules
docker compose -f deploy/compose.yaml --env-file deploy/.env run --rm --no-deps caddy \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --no-deps --force-recreate caddy
```

This adds or refreshes the site mount without changing the index. After the mount exists, HTML/CSS/JS edits become available directly; Caddy configuration changes require a reload or recreation. Use the full update workflow below whenever corpus or application changes are included. Re-run `deploy/test-mcp.py` after changing proxy routing to verify both the public website and anonymous MCP.

## Updating the corpus

After reviewed changes land on the server's tracked branch:

```bash
./deploy/update.sh
```

That performs `git pull --ff-only --recurse-submodules` followed by a complete index rebuild. Submodules use the commits recorded in this repository; deployment never uses `git submodule update --remote`.

## Useful commands

```bash
# Service status
./deploy/status.sh

# Logs
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f mempalace gateway caddy

# Rebuild from the already-checked-out commit
./deploy/rebuild-index.sh

# Stop public services without deleting data/certs
docker compose -f deploy/compose.yaml --env-file deploy/.env stop
```

## Public access and traffic limits

Public access is intentional: only already-public documents belong in this deployment. Caddy terminates HTTPS and forwards `/mcp` through Nginx. The gateway is not host-published. Caddy overwrites `X-Real-IP` using the connection’s peer address, and only Caddy and the gateway share the internal ingress network. Do not publish the gateway port or accept client-supplied IP headers. If adding a CDN, configure its trusted IP ranges deliberately; otherwise clients will share the CDN’s address quota.

The defaults in `deploy/nginx.conf` are:

| Control | Limit |
| --- | --- |
| Requests per client IP | 120/minute, burst allowance 30 |
| Requests across all clients | 300/minute, burst allowance 50 |
| Active MCP requests per IP | 2 |
| Active MCP requests globally | 4 |
| Request body | 16 KiB |
| Search results | 20 per call |
| Drawer listing | 100 per call |
| Full-document page | 65,536 Unicode characters |

Rate limits use Nginx’s leaky-bucket accounting, not fixed minute windows. Clients behind the same office or VPN address share an IP quota. Nginx returns HTTP **429** and `Retry-After: 5` when a rate or concurrency limit is hit. Agents should retry with exponential backoff. These limits protect ordinary VM capacity; they do not provide upstream protection against a large bandwidth flood.

The public entrypoint additionally limits actual backend dispatch to four active requests, retaining each slot until the work finishes even if a client disconnects. Exhaustion there returns a JSON-RPC “Server busy” error. Proxy timeouts do not cancel backend work. JSON-RPC batches are rejected, argument schemas are enforced, and string lengths and pagination are bounded.

Only these tools are advertised and accepted: `mempalace_search`, `mempalace_get_drawer`, `mempalace_get_document`, `mempalace_list_drawers`, `mempalace_list_wings`, `mempalace_list_rooms`, and `mempalace_get_taxonomy`. Writes, maintenance, diary, sync, and agent-coordination tools are unavailable. The underlying server also runs with `--read-only`. Changes to the corpus happen through Git.

### Retrieval contract

The build creates a source manifest containing SHA-256 digests, exact chunk offsets, pinned source URLs, and rooms. The indexer and MCP adapter share this manifest. Mining must produce exactly the expected drawer IDs, contents, and rooms or deployment fails. A successful verification records the manifest fingerprint in the palace state. The query service refuses to start without a matching fingerprint. Rebuild the index when changing chunk boundaries or routing.

Markdown headings start sections. Paragraphs, tables, and fenced code stay intact, with a soft 1,600-character packing target. Oversized blocks stay whole; blocks over 65,536 characters fail preparation so they can be split editorially. Search is still selective retrieval: an excerpt is not evidence that an unreturned fact does not exist. Long indivisible blocks can also exceed an embedding model's input window, so full-source access remains important.

`mempalace_get_document` reads only prepared, digest-verified sources using the exact `source_path` returned by search. It cannot read arbitrary VM files or fetch URLs. The default page is 65,536 characters; `complete: true` means the entire document is present. Otherwise follow `next_offset` until null and concatenate the content. `source_url` links to the original pinned file. `mempalace_get_drawer` returns a complete chunk with `previous_drawer_id` and `next_drawer_id` from the same document.

Upstream rooms are explicit path-prefix mappings in `upstream-sources.json`; local article rooms follow their top-level catalogue folder. The ISA source uses `wormhole-b0`, `blackhole-a0`, and `isa-shared`. Query the taxonomy tools to discover current counts. Unfiltered search warns when results span rooms.

Search results default to `drawer_id`, `source_path`, `room`, `section`, `chunk_index`, `chunk_count`, `text`, and `similarity`. Similarity is MemPalace's unboosted vector similarity, passed through unchanged: higher means a closer semantic match to the query, not a probability that the content is correct. A missing score (for example, a lexical-only hit) is `null`. Hybrid ranking may order results differently from this score. `verbose: true` adds the other backend scores and diagnostic metadata. Drawer retrieval and listings also support `verbose`. The alternate `cli_compatible` search output is disabled on the public endpoint to preserve this contract.

MemPalace’s explicit no-token HTTP setting applies only inside Docker; Caddy is the public TLS boundary. The public entrypoint starts the MCP server directly, so the `serve` CLI cannot silently generate a replacement token. Qdrant and MemPalace have no host ports. Caddy certificates survive index rebuilds.

Gateway access logs are disabled. Docker logs for each long-running service rotate at 10 MiB × 3. Error logs and application logs can still contain request metadata; anonymous access is not a promise of zero logging. Do not send private material in search queries.

### Testing the public boundary

Unit tests require `jsonschema` (also present in the pinned MemPalace image):

```bash
python -m unittest discover -s scripts/tests
python -m unittest discover -s deploy/tests -p 'test_public*.py'
```

The proxy integration tests use the production Caddy/Nginx configurations with a disposable backend, no public ports, and no production volumes. They check rate and concurrency limits, spoofed IP headers, request size, and route isolation:

```bash
docker compose -f deploy/tests/compose.yaml up -d mempalace gateway caddy
docker compose -f deploy/tests/compose.yaml run --rm test
docker compose -f deploy/tests/compose.yaml down -v
```

## Upgrade policy

`deploy/.env.example` pins MemPalace, Qdrant, and Nginx versions. Upgrade those intentionally, rebuild, and test rather than silently following `latest` for those components. The public entrypoint integrates with MemPalace’s dispatcher; verify it against each new MemPalace version.

## Direct Compose builds

Use `./deploy/rebuild-index.sh` for normal deployment; it fetches submodules before invoking Compose. Compose's local build context does not itself run Git. If building manually, prepare the checkout first:

```bash
git submodule sync --recursive
git submodule update --init --recursive
python3 scripts/prepare_knowledge.py
docker compose -f deploy/compose.yaml --env-file deploy/.env build mempalace
```

Regenerate the prepared corpus after any local document or submodule change. Validation rejects missing, modified, or mismatched upstream checkouts. An upstream revision change must be committed in the parent repository to reach other deployments.
