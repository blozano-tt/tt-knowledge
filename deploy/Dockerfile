# syntax=docker/dockerfile:1.7

ARG MEMPALACE_IMAGE=ghcr.io/mempalace/mempalace:3.10.0
FROM ${MEMPALACE_IMAGE}

ARG GIT_SHA=unknown
LABEL org.opencontainers.image.title="tt-knowledge MemPalace" \
      org.opencontainers.image.description="Read-only MemPalace image built from the human-reviewed tt-knowledge corpus" \
      org.opencontainers.image.source="https://github.com/blozano-tt/tt-knowledge" \
      org.opencontainers.image.revision="${GIT_SHA}"

# prepare_knowledge.py selects validated local articles and approved upstream
# Markdown. Git metadata, templates, and administration files are not included.
COPY --chown=1000:1000 .build/knowledge/ /knowledge/
COPY --chown=1000:1000 .build/licenses/ /opt/tt-knowledge/licenses/
COPY --chown=1000:1000 .build/sources.json /opt/tt-knowledge/sources.json
COPY --chown=1000:1000 deploy/scripts/wait-and-mine.sh /opt/tt-knowledge/wait-and-mine.sh
