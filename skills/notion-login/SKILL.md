---
name: notion-login
description: >-
  Log in to Notion for the notion-read / notion-grep / notion-ls skills via
  OAuth — opens the browser, the user picks which pages to share in Notion's
  own picker, and tokens land in ~/.claude/notion/auth.json (chmod 600). Also
  supports pasting an internal integration token as a fallback, and guides
  first-time setup of the team's OAuth app credentials. Use when the user says
  /notion-login, asks to connect / authenticate / log in to Notion, or when
  any notion skill reports NO_TOKEN, AUTH_FAIL, or OAUTH_APP_MISSING. Also
  invocable directly as /notion-login.
---

# Notion Login

Authenticate the notion skill suite. Engine:
`~/.claude/skills/notion-read/scripts/notion_api.py` (below: `notion_api.py`).

## Workflow

1. **Check current auth first.**

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py whoami
   ```

   `OK: bot ...` → already logged in. Show workspace + accessible pages, ask if
   the user wants to re-login (e.g., to share more pages); if not, done.

2. **Run the OAuth login.**

   ```bash
   python3 ~/.claude/skills/notion-read/scripts/notion_api.py login
   ```

   This opens the browser to Notion's consent screen where the user logs in
   and **selects which pages to share** (that picker replaces the confusing
   manual "Connections" step), then a localhost callback receives the code and
   the script exchanges + stores tokens itself. Success prints
   `OK: workspace "..."` plus an accessible-page sample — relay that to the
   user and you are done.

3. **Handle the failure modes:**

   - `OAUTH_APP_MISSING` → the team's OAuth app credentials aren't installed
     on this machine. Two paths:
     - **Team member**: get `client_id` / `client_secret` from the team admin
       and write them:

       ```bash
       mkdir -p ~/.claude/notion
       cat > ~/.claude/notion/oauth_app.json <<'EOF'
       {"client_id": "<CLIENT_ID>", "client_secret": "<CLIENT_SECRET>", "port": 8917}
       EOF
       chmod 600 ~/.claude/notion/oauth_app.json
       ```

       Then re-run step 2.
     - **Admin doing first-time setup**: guide them through registering the
       app once — https://www.notion.so/my-integrations → New integration →
       type **Public** → redirect URI `http://localhost:8917/callback` →
       capabilities: Read content (read-only suite needs nothing else) → copy
       `client_id`/`client_secret` into the file above.
   - `PORT_BUSY` → something holds port 8917; find it (`lsof -i :8917`) and
     retry, or change `port` in oauth_app.json AND in the integration's
     registered redirect URI (they must match exactly).
   - `LOGIN_TIMEOUT` / `LOGIN_FAIL` → user didn't finish the browser step or
     denied; just re-run.
   - **No browser possible** (ssh, CI, cron) → fallback: internal integration
     token paste:

     ```bash
     python3 ~/.claude/skills/notion-read/scripts/notion_api.py login --token '<ntn_...>'
     ```

     or set `NOTION_TOKEN` env var (overrides everything, stores nothing).

4. **Explain access scope when relevant**: the integration sees only pages the
   user shared in the picker (plus their sub-pages). To widen access later,
   re-run `/notion-login` and pick more pages, or use the page's `⋯` →
   Connections menu.

## Notes

- Tokens: `~/.claude/notion/auth.json`, chmod 600, never in any repo. When
  confirming, show at most the first 8 chars of any token.
- Access tokens don't expire on a schedule; the script auto-refreshes via
  `refresh_token` on 401 anyway. If refresh fails, the user revoked the
  connection — re-run login.
- Full sign-out is `/notion-logout`.
