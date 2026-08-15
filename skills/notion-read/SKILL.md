---
name: notion-read
description: >-
  Read a Notion page end-to-end via the official REST API — text, tables,
  databases, AND embedded visual media (wireframes, diagrams, screenshots,
  mockups, videos). Works with just an integration token: no MCP connector
  needed, so it runs identically in interactive sessions, subagents, cron
  jobs, and workflows. Images are downloaded and video frames sampled so you
  actually see the pixels instead of skipping unreadable signed URLs. Use this
  WHENEVER the user asks to read, open, review, summarize, check, or pull
  content from a Notion page/doc/spec — especially anything with a notion.so
  or *.notion.site URL. Also invocable directly as /notion-read.
---

# Notion Read

Read a Notion page completely — text **and** embedded images/videos — using the
official REST API with an integration token.

## Prerequisites

Auth at `~/.claude/notion/auth.json` (set up via `/notion-login`). If any step
below prints `NO_TOKEN` or `AUTH_FAIL`, tell the user to run `/notion-login` and
stop.
If it prints `NO_ACCESS`, the page isn't connected to the integration — tell the
user to open the page → `⋯` menu → Connections → add the integration (connecting
a top-level page covers all its sub-pages).

## Workflow

1. **Fetch the page as markdown.** `<skill-dir>` is this skill's directory
   (normally `~/.claude/skills/notion-read`).

   ```bash
   python3 <skill-dir>/scripts/notion_api.py read '<url-or-id>' > <scratchpad>/notion_page.md
   ```

   stdout is the rendered markdown; stderr reports `CACHED:` (a copy saved to
   `~/.claude/notion/cache/` — this is what makes `/notion-grep` full-text search
   work later) and `SOURCE:` (canonical URL).

   **Databases** render as schema + a markdown table of rows (property values
   included, row ids in the last column for follow-up `prop`/`read` calls).
   Query options, DB targets only:

   ```bash
   ... read '<db-url>' --filter '상태=진행중' --filter '담당=철진' \
       --sort '-우선순위' --limit 50
   ```

   Multiple `--filter` combine as AND (enum/number/checkbox/date match exactly,
   title/rich_text match contains); `--sort '-이름'` = descending, `created`/
   `edited` sort by timestamps; `--filter-json <file>` is the escape hatch for
   anything fancier (or/date-range/relation). Multi-source DBs: pick one with
   `--source <이름|id>`. **Pages that are DB rows** render their properties
   (status, assignee, dates...) in a `**속성**` block before the body.

2. **Read the markdown file.** Read `<scratchpad>/notion_page.md`.

3. **Scan for media.** If it contains `![...](...)` images or `<video ...>`
   blocks, those carry information you cannot see from text alone:

   ```bash
   python3 <skill-dir>/scripts/fetch_notion_media.py <scratchpad>/notion_page.md <scratchpad>/media
   ```

   Downloads each image; downloads each video and samples evenly-spaced frames
   plus one tiled contact sheet via ffmpeg. Prints exactly which local files are
   vision-ready. No media markers → skip this and step 4.

4. **View the media.** `Read` each file listed under `READ THESE`. For a video,
   read its `_contact_sheet.png` first, then individual frames only if detail
   demands it. Skip decorative images; prioritize wireframes, diagrams,
   screenshots, recordings.

5. **Report.** Combine page text with what the visuals show, tying each image or
   video to the section it sits under. Mention child pages / child databases the
   page links to (they are listed but not auto-recursed) and offer to read them.

## Things that bite

- **Signed URLs expire (~1 hour).** Download media right after fetching. On
  `HTTP 403` from the media tool, re-run step 1 for fresh URLs.
- **Animated GIF** → vision sees only the first frame; describe as a still.
  **Video** → sampled stills only, never audio. **svg/pdf** → not sampled;
  mention they exist.
- **Video needs ffmpeg/ffprobe** (yt-dlp for YouTube/Vimeo embeds). If missing,
  images still work and the tool prints an install hint — never fail the run.
- **Pages over 3000 blocks are truncated** with an explicit `[TRUNCATED]` marker
  at the end — if present, say so in the report.
- **Rate limit** (~3 req/s) is handled inside the script with Retry-After; a
  huge page just takes longer, don't parallelize multiple reads of the same
  workspace aggressively.
