# syntax=docker/dockerfile:1.7

ARG MEMPALACE_IMAGE=ghcr.io/mempalace/mempalace:3.10.0
FROM ${MEMPALACE_IMAGE}

ARG GIT_SHA=unknown
LABEL org.opencontainers.image.title="tt-knowledge MemPalace" \
      org.opencontainers.image.description="Read-only MemPalace image built from the human-reviewed tt-knowledge corpus" \
      org.opencontainers.image.source="https://github.com/blozano-tt/tt-knowledge" \
      org.opencontainers.image.revision="${GIT_SHA}"

# The root .dockerignore ensures only deploy runtime files and the verified
# corpus reach the build context. Human-only README/template files are excluded.
COPY --chown=1000:1000 tt-knowledge/ /knowledge/
COPY --chown=1000:1000 deploy/scripts/wait-and-mine.sh /opt/tt-knowledge/wait-and-mine.sh
