---
name: notion-grep
description: >-
  Search Notion pages by keyword — full-text over the local page cache plus
  title search via the official API. Use when the user says /notion-grep, or
  asks to find / search / locate which Notion page mentions something ("어느
  노션 문서에 X 있었지?", "find the notion page about X"). Returns matching
  pages with URLs so /notion-read can open them. Also invocable directly as
  /notion-grep.
---

# Notion Grep

Find which Notion pages mention a keyword. Two layers, run BOTH:

1. **Full-text over the local cache** — pages previously read by `/notion-read`
   or mirrored by `sync`:

   ```bash
   rg -i -l --no-messages '<query>' ~/.claude/notion/cache/
   ```

   For each hit, pull context and identify the page:

   ```bash
   rg -i -n -C1 '<query>' <hit-file>
   head -5 <hit-file>   # frontmatter: title, url, fetched_at
   ```

2. **Title search via the official API** (catches pages not yet cached — but
   the API only searches TITLES, not body text; that is a Notion API
   limitation, not a bug):

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py search '<query>'
   ```

## Report

Merge both layers, dedupe by page, and present: page title, URL, matched
snippet (from cache hits), and how fresh the cached copy is (`fetched_at`).
Offer `/notion-read <url>` for any page the user wants opened.

## When the cache is empty or stale

- Cache dir missing/empty → full-text layer is blind. Say so, and offer to
  build the mirror:

  ```bash
  python3 ~/.claude/skills/notion-read/scripts/notion_api.py sync 200
  ```

  (Caches up to 200 accessible pages AND databases as markdown. First run
  takes minutes on big workspaces; re-runs are incremental — unchanged pages
  are skipped via last_edited_time, `--full` forces everything. Then re-run
  the rg layer.)

- Hits with old `fetched_at` may be stale — mention the date; re-read the page
  with `/notion-read` if the user needs current content.
- `NO_TOKEN` / `AUTH_FAIL` from the search step → tell the user to run
  `/notion-login` and stop.
