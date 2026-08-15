---
name: notion-logout
description: >-
  Sign out of the Notion skill suite — deletes the locally stored OAuth/API
  tokens and (by default) the local page cache, since cached pages contain
  workspace content. Use when the user says /notion-logout, asks to log out /
  disconnect / de-authenticate Notion, or wants Notion credentials removed
  from this machine. Also invocable directly as /notion-logout.
---

# Notion Logout

Remove stored Notion credentials (and the page cache) from this machine.

## Workflow

1. **Ask about the cache only if the user hinted at keeping it** — default is
   to delete it too, because `~/.claude/notion/cache/` holds actual page
   contents in plaintext; a logout that leaves those behind isn't much of a
   logout. Run:

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py logout
   ```

   or, to keep the local page cache for later:

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py logout --keep-cache
   ```

2. **Relay the output.** It reports exactly what was removed (`auth.json`,
   legacy `token`, `cache`).

3. **Mention the two things logout does NOT do:**
   - The OAuth app credentials (`~/.claude/notion/oauth_app.json`) stay — they
     are the team's app identity, not the user's session. Delete manually if
     the machine is being handed off.
   - The workspace-side connection stays until revoked in Notion: Settings →
     My connections (or https://www.notion.so/my-integrations for internal
     integrations). Point the user there if they want a full revoke.
