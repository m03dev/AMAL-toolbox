# Goldfish (developer memory) in AMAL

- Source: https://github.com/anortham/goldfish (MIT per its package.json (author anortham); the repository has no LICENSE file of its own), commit `0f74184edd0a13fdc1400146e68219b29763e7f7` (2026-11-09).
- Copied verbatim: `skills/` (recall, checkpoint, brief, handoff, standup...) - its method for crash-safe checkpoints and restoring context. AMAL keeps these memories itself (episodes.jsonl, recall), so the skills are read as method, not as calls to Goldfish's own MCP server.
- Not copied: its Bun/TypeScript MCP server, hooks, evals and tests.
- Updating: copy the same folders from a newer commit and update the commit above.
