# Deployment

This deployment targets a small public Linux VM such as an Oracle Cloud Always Free/Always Free-eligible instance. It uses:

- **MemPalace** for semantic retrieval and MCP over HTTP.
- **Qdrant** as the disposable vector/text backend.
- **Caddy** for automatic public TLS.
- A **read-only MCP server**. The Git repository is the only write path for knowledge.

The MemPalace image is built from this repository and contains only the verified corpus. The root `.dockerignore` excludes the corpus README, templates, Git metadata, and deployment secrets from the image.

## 1. Provision the VM

An Ubuntu ARM64 or AMD64 VM is fine; the published MemPalace CPU image is multi-architecture.

At the cloud firewall/security-list level, allow inbound:

- TCP 22 from wherever you administer the VM.
- TCP 80 from the internet (needed for normal ACME/HTTP handling).
- TCP 443 from the internet.
- UDP 443 from the internet if you want HTTP/3; it is optional.

Do **not** expose Qdrant port 6333 or MemPalace port 8765 publicly. Compose keeps Qdrant on an internal Docker network and only Caddy publishes public ports.

## 2. Install Docker + the Compose plugin

Install current Docker Engine and the Docker Compose plugin using Docker's official instructions for your Linux distribution. Confirm:

```bash
docker --version
docker compose version
```

If you add your login user to the `docker` group, log out/in before continuing.

## 3. Clone the public repository

```bash
git clone https://github.com/blozano-tt/tt-knowledge.git
cd tt-knowledge
```

## 4. Create DNS

Create an `A` record such as:

```text
knowledge.example.com -> <VM public IPv4>
```

Wait until the name resolves to the VM. Caddy will request and renew the TLS certificate automatically.

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

1. Builds `tt-knowledge-mempalace:local` from the current Git checkout.
2. Stops MemPalace/Qdrant.
3. Deletes the old Qdrant and MemPalace state volumes.
4. Preserves the embedding-model cache and Caddy TLS state.
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

## Updating the corpus

After reviewed changes land on the server's tracked branch:

```bash
./deploy/update.sh
```

That performs `git pull --ff-only` followed by a complete index rebuild.

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
