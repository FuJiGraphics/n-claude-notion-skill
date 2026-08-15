---
name: notion-comment
description: >-
  Read and post comments on Notion pages and blocks — review threads, feedback,
  discussion replies. Reading is unrestricted; posting is guarded by a local
  allowlist (write_allowlist ∪ comment_allowlist) and comments can NEVER be
  deleted via the API, so posts are confirmed with the user first. Use when the
  user says /notion-comment, or asks to check / read / leave / reply to
  comments on a Notion doc ("스펙에 달린 댓글 확인해줘", "노션 그 문단에 코멘트
  달아줘", "reply to the comment thread"). Also invocable directly as
  /notion-comment.
---

# Notion Comment

Comment threads, read and write. Engine:
`~/.claude/skills/notion-read/scripts/notion_api.py`.

## Read comments (no guard)

```bash
python3 ~/.claude/skills/notion-read/scripts/notion_api.py comments '<url-or-id>'
```

Page-level threads only. Add `--all` to also sweep inline comments anchored to
blocks inside the page — that walks every block (one API call each), so on big
pages say it may take a while. Output groups by `discussion` with author +
timestamp; the discussion id is what `--reply` targets.

**Resolved threads never appear** — the API only returns open comments. Say so
if the user expects a thread that isn't there.

## Post a comment (guarded, irreversible)

Two rules before any post:

1. **Show the user the exact text and target, get a yes.** The API cannot
   delete comments — a bad post stays until someone removes it by hand in the
   Notion UI. This makes comments the one write in this suite that has no
   undo; treat every post like it's permanent, because it is.
2. The target must be under the allowlist union
   (`~/.claude/notion/write_allowlist` ∪ `~/.claude/notion/comment_allowlist`),
   else `COMMENT_DENIED`.

```bash
# 페이지 레벨 댓글
... comment '<page-url-or-id>' --text '리뷰 코멘트 내용'

# 특정 블록에 인라인 댓글 (read --ids 로 블록 id 를 먼저 특정)
... comment '<block-id>' --text '이 문단에 대한 코멘트'

# 기존 스레드에 답글 - 첫 인자는 스레드가 있는 페이지(가드 검증용)
... comment '<page-url-or-id>' --reply '<discussion-id>' --text '답글'
```

Inline `**bold**`, `` `code` ``, `[link](url)` convert properly.

## On COMMENT_DENIED

The page isn't under either allowlist. If the user wants review-comments on a
company doc WITHOUT opening it up for content edits, the comment-only list is
the right tool — after the user explicitly confirms:

```bash
... allow --comment '<page-url-or-id>'
```

Never add to any allowlist without the user confirming that exact page.

## Failure modes

- `NO_TOKEN` / `AUTH_FAIL` → `/notion-login` first.
- HTTP 403 with "insufficient permissions" → the integration is missing the
  **Read comments** / **Insert comments** capabilities
  (notion.so/my-integrations → 해당 integration → Capabilities).
- `users` command for @who-is-who: lists workspace members — but OAuth
  personal tokens get `USERS_RESTRICTED` (API 제약); internal integration
  tokens can list. Individual author names in comment output resolve fine
  either way.
