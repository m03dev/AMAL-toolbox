---
name: llm-wiki
description: Keep a knowledge base as a wiki the agent writes and maintains - ingest a source into linked Markdown pages, answer from the pages, and lint them for contradictions and stale facts. Use when the owner wants research, notes, a project's knowledge or AMAL's vault turned into lasting, cross-linked pages instead of one-off answers.
---

# LLM Wiki

The pattern Andrej Karpathy described in his "LLM Wiki" idea file (gist.github.com/karpathy/442a6bf555914893e9891c11519de94f,
April 2026), written here for AMAL. The idea in one line: the model compiles what it reads into a wiki once, and keeps it
current, instead of re-reading raw material for every question. "Obsidian is the IDE, the LLM is the programmer, the wiki
is the codebase."

## Three layers

1. **Sources** - the raw material, never edited: articles, papers, transcripts, the owner's files, job results.
   Keep them in `sources/` (or wherever the owner keeps them) and link to them.
2. **The wiki** - Markdown pages the agent writes: one page per thing (a person, a tool, a technique, a project, a
   decision). Short, factual, linked.
3. **The schema** - one file of rules for this wiki (in AMAL's vault: the vault's own conventions; in a project:
   `<project>/.amal/` notes or the project's AGENTS.md): page types, naming, front matter, how to link.

## Two special files

- `index.md` - every page with a one-line summary, grouped. Read it first to find what exists; update it whenever a
  page is added, renamed or retired. AMAL writes its vault's `index.md` itself.
- `log.md` - what happened, dated, newest first: what was ingested, what changed, what was found wrong. Append only.
  AMAL writes its vault's `log.md` from its episodic memory.

## Operations

- **Ingest** (a new source): read it; list the pages it touches (existing ones to update, new ones to make) before
  writing anything; write or update each page with what the source adds, citing the source; add links both ways;
  update `index.md`; add one line to `log.md`.
- **Query**: read `index.md`, open the pages that answer, answer from them with links. A good answer that is not in the
  wiki yet becomes a page (file it back).
- **Lint** (now and then, and after big ingests): find contradictions between pages, facts superseded by newer
  sources, pages with no links in or out, links to pages that do not exist, terms used two ways. Fix them or flag them
  in `log.md`.

## Conventions

- Front matter on every page: `type`, `tags`, `updated`, `sources`.
- File names say what the page is (`godotsteam.md`, `rigging-with-unirig.md`), lowercase with dashes.
- Link the first mention of a thing on a page; never link to a page that does not exist - make it, or leave plain text.
- Say where each fact came from; prefer the newest primary source when two disagree, and note the disagreement.
- Keep pages short; split a page that covers two things.
- In AMAL's vault, write only between AMAL's marks (`%% amal:begin %%` ... `%% amal:end %%`); everything else is the
  owner's.

## Where it meets AMAL's memory

The wiki is AMAL's semantic and episodic memory made readable: `memory.md` (facts) and the project memories feed
pages; `episodes.jsonl` feeds `log.md` and job pages; lessons and skills are the procedural pages. The `recall` tool
searches all of them; this skill is how pages get written and kept true.
