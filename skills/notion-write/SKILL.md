---
name: notion-write
description: >-
  Create a new Notion page or append content to an existing one, from markdown
  — headings, lists, todos, quotes, code fences, bold/inline-code/links all
  convert to real Notion blocks. Writes are HARD-RESTRICTED to pages under the
  local allowlist (~/.claude/notion/write_allowlist), so company docs can't be
  touched by accident. Use when the user says /notion-write, asks to create /
  add / save / post something to Notion ("노션에 정리해줘", "이거 노션에
  써놔", "write this up as a Notion page"). Also invocable directly as
  /notion-write.
---

# Notion Write

Create pages / append blocks, guarded by an allowlist. Engine:
`~/.claude/skills/notion-read/scripts/notion_api.py`.

## The allowlist guard (read this first)

Every write walks the target's ancestor chain via the API and refuses with
`WRITE_DENIED` unless an ancestor is listed in
`~/.claude/notion/write_allowlist` (one page id per line). This is a
code-level guard: it exists so that a slip — wrong URL, wrong id, misread
intent — cannot write into real company documents.

So on `WRITE_DENIED`: do NOT silently add the target to the allowlist. Tell
the user which page was refused and ask them to confirm widening the
allowlist; only append the id after explicit confirmation.

## Create a page

1. Write the content as a markdown file in the scratchpad (supported subset:
   `#`–`###` headings, `-` bullets, `1.` numbered, `- [ ]`/`- [x]` todos,
   `>` quotes, ``` fences with language, `---` divider, paragraphs; inline
   `**bold**`, `` `code` ``, `[text](url)`).

2. Create it under the parent page:

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py \
     write '<parent-url-or-id>' '<페이지 제목>' --file <scratchpad>/content.md
   ```

   Prints `CREATED` + the new page's URL and id — give the URL to the user.

## Append to an existing page

```bash
python3 ~/.claude/skills/notion-read/scripts/notion_api.py \
  append '<page-url-or-id>' --file <scratchpad>/content.md
```

(`--text '<한 줄>'` works for both commands when a file is overkill.)

## Things that bite

- **This tool only adds.** Changing or removing existing blocks is
  /notion-edit's job — hand off there instead of appending a correction.
- **Images**: upload separately after creating the page —
  `upload <local-path> --attach <page-id>` (File Upload API, permanent
  hosting). Image markdown inside content files is NOT converted; keep it out.
- **Toggle headings** (팀 관례 "히스토리 확인용" 같은 접힌 섹션): `#>` ~
  `####>` heading syntax marks it toggleable. Raw block JSON escape hatch:
  `append <page> --json blocks.json`.
- Needs the integration to have **Insert content** capability; a 403 with a
  permissions message means the user must enable it at
  notion.so/my-integrations.
- `NO_TOKEN` / `AUTH_FAIL` → `/notion-login` first.
- After writing, verify important output by reading the page back
  (`read <new-id>`) when correctness matters — the markdown subset is lossy
  for anything exotic.
