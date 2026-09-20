# Deploy tt-knowledge

Docker Compose runs **stock Hindsight 0.10.0**, PostgreSQL 17 with pgvector, Nginx traffic limits, and Caddy HTTPS. Hindsight serves its own MCP and dashboard. No custom image, retrieval server, chunker, or runtime patch is built.

## New VM

The deployment is portable to a Linux ARM64 or x86-64 VM with Docker Engine, the Compose plugin, Git, and Python 3. The tested Oracle VM has 2 CPUs and 12 GiB RAM. Local embedding/reranking models use CPU; no LLM API key is required. Allow model downloads and image pulls on first startup.

1. Give the VM a stable IP and point a DNS A record at it. Allow inbound TCP 80/443 (optionally UDP 443 for HTTP/3) and restrict SSH to your administration network. Do not publish ports 5432, 8888, 9999, or 8080.
2. Clone recursively and generate host-local credentials:

   ```bash
   git clone --recurse-submodules https://github.com/blozano-tt/tt-knowledge.git
   cd tt-knowledge
   ./deploy/setup.sh tt-knowledge.example.com
   ```

   `deploy/.env` contains the database password and the dashboard password hash. `deploy/admin-password.txt` contains the generated dashboard password; the username is **admin**. Both files are ignored by Git and created with mode 0600. Move the password into your password manager and delete the plaintext file if desired. Never source `.env` in a shell; Compose reads its quoted hash correctly.
3. Start and populate the service:

   ```bash
   ./deploy/rebuild-index.sh
   ```

   It validates selected sources before changing the bank, pulls official images, starts PostgreSQL/Hindsight, pauses public MCP, and ingests each original document through Hindsight's HTTP API. It reads every original back and checks exact text equality before bringing MCP online. A failed import leaves public MCP stopped; fix the failure and rerun. The dashboard is available once Caddy starts. A first deployment may need several minutes for models and ingestion.
4. Test from an MCP client or run the automated checks:

   ```bash
   python3 -m venv .venv-test
   .venv-test/bin/pip install -r deploy/requirements-test.txt
   .venv-test/bin/python deploy/test-mcp.py --url https://tt-knowledge.example.com/mcp
   ```

   The test uses the real MCP SDK and compares retrieved source documents with the prepared corpus. For an authenticated dashboard smoke test, add `--admin-password-file deploy/admin-password.txt`.

## Public and administrative surfaces

- `/mcp` and `/mcp/` expose the fixed `tt-knowledge` bank and only `recall`, `get_document`, `list_documents`. Hindsight's native tool allowlist enforces this; no custom dispatcher is involved.
- `/healthz` reports API health.
- `/` serves the public landing page, with setup instructions and an Admin dashboard button. Its static assets are under `/landing/`.
- `/dashboard` opens Hindsight's native administration UI. Caddy requires HTTP Basic authentication over HTTPS for **all** UI pages, assets, and UI API routes. The admin account can change data; do not share it with MCP consumers.
- Direct REST API paths and arbitrary MCP bank paths are blocked. PostgreSQL, Hindsight, and Nginx have no host port mappings. TLS terminates at Caddy.
- Nginx limits MCP to 120 requests/minute per IP (burst 30), 300/minute globally (burst 50), 2 simultaneous requests per IP, 4 globally, and 16 KiB request bodies. Hindsight additionally limits concurrent recalls to 2 and reranks at most 32/64/96 candidates for low/mid/high budgets. These native settings trade retrieval depth for latency on the 2-CPU VM. HTTP 429 includes `Retry-After: 5`. Caddy overwrites forwarding headers to prevent IP spoofing. These are bounded resource controls, not a promise of protection against every denial-of-service attack.
- Access logging is disabled in Nginx and not enabled in Caddy. Hindsight logs at warning level; errors may still contain request-related information. Requests necessarily send query text to this VM. Docker logs rotate at 10 MiB × 3 files per long-running service. No transcript ingestion is configured.

The public landing page is served directly by Caddy from `site/`. Hindsight remains unmodified and uses its normal routes; only the landing page and its explicitly listed assets bypass dashboard authentication.

For a landing-page or proxy-only update, pull the repository and recreate Caddy without rebuilding the knowledge bank:

```bash
git pull --ff-only --recurse-submodules
docker compose -f deploy/compose.yaml --env-file deploy/.env up -d --no-deps --force-recreate caddy
```

## Git-owned bank and updates

```bash
./deploy/update.sh
./deploy/status.sh
```

`update.sh` fast-forwards the repository and recursively checks out pinned submodules. `rebuild-index.sh` regenerates `.build/`, deletes and recreates **only the `tt-knowledge` bank**, and imports the current source inventory. This removes stale documents. It also discards any manual changes to this bank made in the admin UI. Other banks and PostgreSQL volumes are untouched; other banks are not publicly accessible.

Full rebuilds temporarily stop public MCP. The underlying Markdown and Git history remain authoritative. Do not use `docker compose down -v` to update: that would delete database and TLS volumes.

For configuration changes that do not change the corpus, run the relevant Compose service with `--force-recreate`; normal updates should use the script. Model and TLS caches persist. Versions can be overridden in `.env`; benchmark upgrades before deployment because native schemas and retrieval behavior can change.

To rotate the admin password, use `docker run --rm -i caddy:2-alpine caddy hash-password` (reads stdin), replace the single-quoted `UI_PASSWORD_HASH` in `.env`, and recreate Caddy. Do not alter the database password in `.env` without also changing the existing PostgreSQL role password.

## Internal VMs

The same Compose stack works internally. Use an internal DNS name that clients resolve to the VM. Caddy's default public certificate issuance requires a publicly verifiable domain and challenge reachability; for an isolated network, configure `tls internal` in the site block and install the Caddy root CA on clients, or mount a certificate/key from your organization's CA. Keep HTTPS for the protected dashboard. Adjust firewall access and traffic limits for the internal audience; no Oracle-specific code is required.

## Migration from MemPalace

Back up the old ignored `.env` privately before generating the new credentials. Hindsight uses new PostgreSQL/model-cache volume names; existing Caddy certificate volumes are reused. A controlled first migration can start `postgres hindsight`, run the `ingest` Compose profile, and only then recreate `gateway caddy` to switch traffic. Stop the old `mempalace` and `qdrant` containers after the public tests pass. Their old volumes can be retained for rollback; this deployment never reads them. Clients must refresh their cached tool list.

## Validation

CI validates corpus provenance, tag selection, ingestion failure handling, Compose configuration, and the real Caddy/Nginx boundary with a disposable backend. `test-mcp.py` tests the deployed stock Hindsight server: only three read tools, denied mutations, architecture filtering, source provenance, exact original recovery, Wormhole's 256-bit versus Blackhole's 512-bit NoC flits, and the complete congestion-adaptive buddy-bit clause. It proves source recovery, not that every agent will follow the instruction to read it or that every query ranks optimally.
