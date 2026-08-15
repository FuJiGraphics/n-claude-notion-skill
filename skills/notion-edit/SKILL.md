---
name: notion-edit
description: >-
  Edit or delete specific blocks inside an existing Notion page — the Notion
  counterpart of the Edit tool. Notion has no string-replace, so the flow is:
  read the page with block ids, pick the target block, then replace its text
  or archive it. Writes are HARD-RESTRICTED to pages under the local allowlist
  (~/.claude/notion/write_allowlist). Use when the user says /notion-edit, or
  asks to change / fix / update / remove specific content in an existing
  Notion page ("노션 그 문단 고쳐줘", "그 줄 지워줘", "update that section in
  Notion"). For adding new content use notion-write instead. Also invocable
  directly as /notion-edit.
---

# Notion Edit

Block-level edit/delete, allowlist-guarded. Engine:
`~/.claude/skills/notion-read/scripts/notion_api.py`.

Notion pages are block trees, not text files — but `edit-str` gives you the
old_string → new_string feel when the target text lives inside one block:

```bash
python3 ~/.claude/skills/notion-read/scripts/notion_api.py \
  edit-str '<page-url-or-id>' --old '<기존 문자열>' --new '<새 문자열>' [--all]
```

It matches against the markdown form that `read` prints (so copy old strings
straight from a read). Multiple matches stop with a block list — pick one via
the id workflow below, or pass `--all`. Strings spanning multiple blocks can't
be replaced in one go (Notion 구조 제약) — fall back to block-level editing.

## Block-id workflow (when edit-str isn't enough)

1. **Read the page with ids** to find the target block:

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py read '<url-or-id>' --ids
   ```

   Every block renders with a trailing `⟨block-id⟩`. (This mode skips the grep
   cache on purpose — id markers would pollute it.)

2. **Replace a block's text** (block type is preserved; inline `**bold**`,
   `` `code` ``, `[link](url)` convert properly):

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py \
     edit '<block-id>' --text '<새 내용>'
   ```

   Works on text-bearing blocks (paragraph, headings, list items, to_do,
   toggle, quote, callout, code). `EDIT_UNSUPPORTED` on anything else
   (images, tables, embeds...) — for those, delete + re-append via
   notion-write is the honest path; say so.

3. **Move** — one command, two very different mechanics underneath:

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py \
     move '<page-or-block-id>' --to '<dest-id>' [--after '<sibling-id>' | --start]
   ```

   - **Whole page (or database row)** → the official move endpoint: atomic,
     **page id preserved**, so inbound links/mentions, comments, and history
     all survive. Destination may be a page or a database (data_source is
     resolved automatically) — this covers page→page, page→DB, and DB→DB row
     moves. Databases themselves cannot be moved (API limit). Property
     behavior when schemas differ between DBs is undocumented — spot-check
     the result after a cross-DB move.
   - **Block inside a page** → no atomic API exists, so it deep-copies to the
     destination, verifies, then archives the original. Destruction happens
     only after the copy is confirmed: worst failure = duplicate, never loss.
     Notion-hosted files inside (screenshots etc.) are re-uploaded via the
     File Upload API so they survive signed-URL expiry. `--after`/`--start`
     position the copy; they don't apply to page moves. `synced_block` and
     `link_to_page` blocks refuse to copy — those move only in the Notion UI.

4. **Delete a block**:

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py delete '<block-id>'
   ```

   This archives — recoverable from Notion's trash — but still confirm with
   the user before deleting anything you didn't create in this session.

5. **Page-level lifecycle** (same allowlist guard):

   ```bash
   ... duplicate '<page-id>' [--to '<dest>'] [--title '새 제목']  # 속성+본문 복제
   ... archive '<page-or-block-id>'    # 휴지통으로
   ... restore '<page-or-block-id>'    # 휴지통에서 복구
   ```

6. **Verify**: re-read the page (without `--ids`) and confirm the change took.

## The allowlist guard

Same guard as notion-write: the block's ancestor chain must reach a page
listed in `~/.claude/notion/write_allowlist`, else `WRITE_DENIED`. Never add
an id to the allowlist yourself without the user explicitly confirming that
widening.

## Failure modes

- `NO_TOKEN` / `AUTH_FAIL` → `/notion-login` first.
- 403 permissions error → integration needs **Update content** capability
  (notion.so/my-integrations).
- Editing a to_do keeps its checked state; only the text changes.
