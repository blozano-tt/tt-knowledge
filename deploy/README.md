# Deployment

This deployment targets a small public Linux VM such as an Oracle Cloud Always Free/Always Free-eligible instance. It uses:

- **MemPalace** for semantic retrieval and MCP over HTTP.
- **Qdrant** as the disposable vector/text backend.
- **Caddy** for automatic public TLS.
- A **read-only MCP server**. The Git repository is the only write path for knowledge.

The MemPalace image contains validated local articles and selected Markdown from approved upstream sources. Before building, the deployment script initializes submodules recursively and prepares `.build/knowledge`. The Docker build uses this prepared corpus; Git metadata, templates, and deployment secrets are excluded. Upstream license notices and a source manifest are retained outside the searchable corpus.

## 1. Provision the VM

An Ubuntu ARM64 or AMD64 VM is fine; the published MemPalace CPU image is multi-architecture.

At the cloud firewall/security-list level, allow inbound:

- TCP 22 from wherever you administer the VM.
- TCP 80 from the internet (needed for normal ACME/HTTP handling).
- TCP 443 from the internet.
- UDP 443 from the internet if you want HTTP/3; it is optional.

Do **not** expose Qdrant port 6333 or MemPalace port 8765 publicly. Compose keeps Qdrant on an internal Docker network and only Caddy publishes public ports.

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
openssl rand -hex 32
```

Edit `deploy/.env` and set:

```dotenv
DOMAIN=knowledge.example.com
MEMPALACE_MCP_HTTP_TOKEN=<the generated secret>
```

`deploy/.env` is gitignored. Never commit the token.

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
7. Starts MemPalace with `--read-only`.
8. Starts Caddy on ports 80/443.

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

and requires:

```text
Authorization: Bearer <MEMPALACE_MCP_HTTP_TOKEN>
```

For Claude Code, MemPalace documents the client shape as:

```bash
claude mcp add --transport http tt-knowledge https://knowledge.example.com/mcp \
  --header "Authorization: Bearer $MEMPALACE_MCP_HTTP_TOKEN"
```

Other MCP clients use the same URL and bearer header.

### End-to-end MCP test

Run this on the server so its bearer token stays in the existing `deploy/.env`:

```bash
python3 -m venv /tmp/tt-knowledge-mcp-test
/tmp/tt-knowledge-mcp-test/bin/pip install -r deploy/requirements-test.txt
/tmp/tt-knowledge-mcp-test/bin/python deploy/test-mcp.py
```

The test uses the official MCP client against the public HTTPS endpoint. It checks TLS/health, rejects missing and incorrect bearer tokens, verifies that write calls are refused, performs semantic search, and fetches indexed `SFPMUL` content from both Wormhole and Blackhole at the pinned ISA revision. Failures return a nonzero exit status. Its JSON report contains retrieval evidence, never the token. Use `--report /path/to/report.json` to save it.

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
docker compose -f deploy/compose.yaml --env-file deploy/.env logs -f mempalace caddy

# Rebuild from the already-checked-out commit
./deploy/rebuild-index.sh

# Stop public services without deleting data/certs
docker compose -f deploy/compose.yaml --env-file deploy/.env stop
```

## Security properties

- MCP writes are disabled with MemPalace `--read-only`.
- MCP still requires a bearer token even though the knowledge repository is public; this prevents arbitrary internet clients from consuming your compute without authorization.
- Qdrant is not host-published.
- Plaintext MemPalace HTTP exists only inside Docker; Caddy is the public TLS boundary.
- Caddy certificates survive truth-index rebuilds.
- The bearer token is stored only in `deploy/.env` on the host.

## Upgrade policy

`deploy/.env.example` pins MemPalace and Qdrant versions. Upgrade those intentionally, rebuild, and test rather than silently following `latest` for the two stateful/application components.

## Direct Compose builds

Use `./deploy/rebuild-index.sh` for normal deployment; it fetches submodules before invoking Compose. Compose's local build context does not itself run Git. If building manually, prepare the checkout first:

```bash
git submodule sync --recursive
git submodule update --init --recursive
python3 scripts/prepare_knowledge.py
docker compose -f deploy/compose.yaml --env-file deploy/.env build mempalace
```

Regenerate the prepared corpus after any local document or submodule change. Validation rejects missing, modified, or mismatched upstream checkouts. An upstream revision change must be committed in the parent repository to reach other deployments.
