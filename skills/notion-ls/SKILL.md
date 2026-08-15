---
name: notion-ls
description: >-
  List the Notion workspace like a filesystem — the full accessible page/database
  tree, or the sub-pages under one page. Use when the user says /notion-ls, asks
  what pages exist / what's in the workspace / what docs are under X ("노션에 뭐
  있어?", "이 페이지 하위 목록 보여줘", "what pages do we have in Notion"), or
  when you need to discover a page's URL before /notion-read or /notion-grep.
  Also invocable directly as /notion-ls.
---

# Notion Ls

Explore the workspace structure. Engine:
`~/.claude/skills/notion-read/scripts/notion_api.py`.

## Two modes

**Whole tree** — everything the integration can see, newest-edited first,
indented by parent/child:

```bash
python3 ~/.claude/skills/notion-read/scripts/notion_api.py ls
```

**One page's children** — sub-pages and sub-databases directly under a page:

```bash
python3 ~/.claude/skills/notion-read/scripts/notion_api.py ls '<url-or-id>'
```

`EMPTY` means the page has only content blocks, no sub-pages — that's an answer,
not an error.

## Handling big workspaces

The full tree caps at 1000 items and prints `limit 도달` when it hits the cap —
real workspaces blow past this because every database row is a page. So:

- When the user asks about a **specific area**, don't dump the whole tree —
  pipe through grep (`ls | rg -i '<이름>'`) or start from the relevant page id.
- When the tree is large, summarize the top-level structure for the user
  instead of relaying hundreds of lines; offer to drill into a branch.
- Databases show as 🗃️ with their rows nested under them; rows of a shared
  database are included automatically.

## Failure modes

- `NO_TOKEN` / `AUTH_FAIL` → tell the user to run `/notion-login`, stop.
- A page missing from the tree usually means it isn't shared with the
  integration — sharing its top-level ancestor (page `⋯` → Connections) brings
  the whole subtree in.
