# Human-reviewed knowledge corpus

This directory holds locally verified articles and approved upstream documentation. Local articles use the verification template below; upstream submodules use the source-level policy in [UPSTREAM.md](../UPSTREAM.md).

Use `_templates/topic.md` as the starting point for a new topic. The template and this README are excluded from the deployed Docker image, so they cannot appear in MemPalace retrieval results.

Suggested organization:

```text
hardware/
  wormhole.md
  blackhole.md
software/
  tt-metal.md
  ttnn.md
glossary/
  memory.md
upstream/
  tt-isa-documentation/  # pinned upstream Git submodule
```

Prefer one coherent topic per Markdown file rather than one file per individual fact. Keep each factual statement concise enough that it remains correct when retrieved as a passage.
