#!/usr/bin/env python3
"""Notion 공식 REST API 클라이언트 - /notion-login, /notion-read, /notion-grep 스킬의 공용 도구.

MCP 커넥터 없이 OAuth 또는 integration token 으로 동작한다. 대화형 세션,
서브에이전트, cron, 워크플로 어디서든 같은 방식으로 돈다.

인증 (우선순위 순):
    1. 환경변수 NOTION_TOKEN                          - cron/CI 용
    2. ~/.claude/notion/auth.json (chmod 600)          - `login` 명령이 저장 (OAuth)
    3. ~/.claude/notion/token                          - 레거시 폴백 (토큰 문자열 1줄)

OAuth 앱 자격증명 (팀 관리자가 1회 등록, 사내 채널로 배포):
    ~/.claude/notion/oauth_app.json
    {"client_id": "...", "client_secret": "...", "port": 8917}
    등록: https://www.notion.so/my-integrations → New integration → Public
          redirect URI: http://localhost:8917/callback

명령:
    login             OAuth 로그인 - 브라우저 열림, Notion 페이지 피커에서 공유
                      범위 선택, localhost 콜백으로 토큰 수신 후 저장
    login --token T   폴백 - internal integration 토큰을 직접 저장
    whoami            토큰 검증 + 접근 가능한 페이지 샘플 출력
    logout [--keep-cache]
                      auth.json/token 삭제 + 캐시 삭제(기본). --keep-cache 면 캐시 유지.
    ls [url|id]       인자 없음: 접근 가능한 전체를 트리로 출력 (제목+URL)
                      인자 있음: 그 페이지 바로 아래의 하위 페이지/DB 목록
    read <url|id> [--ids]
                      페이지를 markdown 으로 출력(stdout) + 캐시 저장.
                      --ids 면 블록마다 ⟨타입 id⟩ 표시 - edit/delete/move 대상 특정 +
                      이동 가능 여부 사전 판별용 (이 모드는 캐시 안 씀)
    edit <block_id> --text '<새 내용>'
                      블록 본문 교체 (allowlist 하위만, 타입 유지)
    delete <block_id> 블록 archive (Notion 휴지통 복구 가능, allowlist 하위만)
    search <query>    공식 /v1/search - 제목만 검색된다(본문 미지원, API 제약)
    write <parent-url|id> <title> [--file md.md]
                      allowlist 하위에만 새 페이지 생성 (markdown → 블록 변환)
                      md 확장 문법: '#> 제목'~'####> 제목' = 토글 헤딩
    append <url|id> --file md.md | --text '...' | --json blocks.json
                     [--start | --after <block_id>]
                      allowlist 하위 페이지에 블록 추가. 기본 끝, --start 면 맨 위,
                      --after 면 지정 블록 뒤 (--json = 원시 블록 탈출구)
    prop <url|id>     페이지 속성 나열 (이름 [타입] = 값)
    prop <url|id> --set '이름=값' [--set ...] | --json props.json
                      속성 갱신 (allowlist 가드). select/status/multi_select(쉼표)/
                      number/checkbox/date(시작~끝)/url/email/title/rich_text 지원
    allow <url|id>    쓰기 허용목록에 페이지 추가 (유저 명시 승인 후에만 사용)
    upload <path> [--attach <url|id>]
                      File Upload API 로 영구 업로드, --attach 면 이미지/파일 블록로 첨부
    move <page|block_id> --to <dest> [--after <block_id> | --start]
                      2계층 자동 분기:
                      - 페이지/DB행 → 공식 move 엔드포인트(원자, id 보존=링크/히스토리 유지).
                        목적지가 DB 면 data_source 자동 해석. DB간 이동 지원.
                      - 블록 → 복제→검증→원본 archive 합성. 내부 파일은 재업로드로 영구화.
                      DB 자체는 이동 불가(API 한계). --after/--start 는 블록 이동 전용
    sync [limit]      접근 가능한 페이지를 순회하며 캐시 구축 (기본 200장 제한)
                      본문 grep 은 이 캐시 위에서 rg 로 한다.

캐시: ~/.claude/notion/cache/<page_id>.md (frontmatter 에 title/url/fetched_at)

이미지·비디오 블록은 ![caption](url) / <video src="url"> 형태로 출력되므로
fetch_notion_media.py 가 그대로 파싱해 다운로드할 수 있다. 서명 URL 은 ~1시간 만료.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
CONF_DIR = os.path.expanduser("~/.claude/notion")
AUTH_FILE = os.path.join(CONF_DIR, "auth.json")
OAUTH_APP_FILE = os.path.join(CONF_DIR, "oauth_app.json")
TOKEN_FILE = os.path.join(CONF_DIR, "token")  # 레거시 폴백
CACHE_DIR = os.path.join(CONF_DIR, "cache")
MAX_BLOCKS = 3000  # 한 페이지에서 가져올 블록 상한 (폭주 방지)
DEFAULT_PORT = 8917
OAUTH_TIMEOUT = 300  # 브라우저 로그인 대기 상한(초)


class ApiError(Exception):
    def __init__(self, code, detail):
        self.code = code
        super().__init__(f"HTTP {code}: {detail}")


def load_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_auth(data: dict):
    os.makedirs(CONF_DIR, exist_ok=True)
    with open(AUTH_FILE, "w") as f:
        json.dump(data, f, indent=2)
    os.chmod(AUTH_FILE, 0o600)


def get_token() -> str:
    t = os.environ.get("NOTION_TOKEN", "").strip()
    if t:
        return t
    auth = load_json(AUTH_FILE)
    if auth and auth.get("access_token"):
        return auth["access_token"]
    try:
        with open(TOKEN_FILE) as f:
            t = f.read().strip()
    except FileNotFoundError:
        sys.exit("NO_TOKEN: 인증 정보 없음 (~/.claude/notion/auth.json). /notion-login 먼저 실행.")
    if not t:
        sys.exit("NO_TOKEN: 토큰 파일이 비어 있음. /notion-login 다시 실행.")
    return t


def oauth_basic_header(app: dict) -> str:
    import base64
    raw = f"{app['client_id']}:{app['client_secret']}".encode()
    return "Basic " + base64.b64encode(raw).decode()


def oauth_token_request(app: dict, body: dict) -> dict:
    """POST /v1/oauth/token (code 교환, refresh 공용). 실패 시 ApiError."""
    req = urllib.request.Request(
        API + "/oauth/token", data=json.dumps(body).encode(), method="POST",
        headers={"Authorization": oauth_basic_header(app),
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, e.read().decode(errors="replace")[:300])


def try_refresh() -> bool:
    """만료/폐기된 access_token 을 refresh_token 으로 갱신 시도."""
    auth = load_json(AUTH_FILE)
    app = load_json(OAUTH_APP_FILE)
    if not auth or not auth.get("refresh_token") or not app:
        return False
    try:
        fresh = oauth_token_request(app, {
            "grant_type": "refresh_token",
            "refresh_token": auth["refresh_token"]})
    except ApiError:
        return False
    auth.update(fresh)
    save_auth(auth)
    return True


def call(method: str, path: str, body=None, _retried=False, version=None):
    data = json.dumps(body).encode() if body is not None else None
    for _ in range(6):
        req = urllib.request.Request(
            API + path, data=data, method=method,
            headers={
                "Authorization": f"Bearer {get_token()}",
                # 기본은 구버전 유지(데이터베이스 엔드포인트 호환), 신기능만 개별 오버라이드
                "Notion-Version": version or NOTION_VERSION,
                "Content-Type": "application/json",
            })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:  # rate limit(약 3req/s) - Retry-After 존중 후 재시도
                time.sleep(float(e.headers.get("Retry-After", "1")) + 0.2)
                continue
            if e.code == 401 and not _retried and try_refresh():
                return call(method, path, body, _retried=True, version=version)
            raise ApiError(e.code, e.read().decode(errors="replace")[:300])
    raise ApiError(429, "rate limit 재시도 초과")


# ---------- id / rich_text ----------

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{32}", re.I)


def to_page_id(s: str) -> str:
    """URL 또는 id 문자열에서 페이지 id 추출. URL 은 마지막 매치가 페이지 id."""
    s = urllib.parse.unquote(s.strip())
    matches = UUID_RE.findall(s)
    if not matches:
        sys.exit(f"BAD_ID: 페이지 id 를 찾지 못함: {s!r}")
    raw = matches[-1].replace("-", "").lower()
    return f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}-{raw[20:32]}"


def rt(arr) -> str:
    """rich_text 배열 → markdown 인라인."""
    out = []
    for t in arr or []:
        s = t.get("plain_text", "")
        if t.get("type") == "equation":
            s = f"${s}$"
        a = t.get("annotations", {})
        if a.get("code"):
            s = f"`{s}`"
        if a.get("bold"):
            s = f"**{s}**"
        if a.get("italic"):
            s = f"*{s}*"
        if a.get("strikethrough"):
            s = f"~~{s}~~"
        if t.get("href"):
            s = f"[{s}]({t['href']})"
        out.append(s)
    return "".join(out)


def page_title(page: dict) -> str:
    for prop in page.get("properties", {}).values():
        if prop.get("type") == "title":
            return rt(prop.get("title")) or "(untitled)"
    return "(untitled)"


# ---------- 블록 → markdown ----------

def get_children(block_id: str, state: dict):
    if state["fetched"] >= MAX_BLOCKS:
        state["truncated"] = True
        return []
    results, cursor = [], None
    while True:
        q = f"/blocks/{block_id}/children?page_size=100"
        if cursor:
            q += f"&start_cursor={urllib.parse.quote(cursor)}"
        data = call("GET", q)
        results += data.get("results", [])
        state["fetched"] += len(data.get("results", []))
        if not data.get("has_more") or state["fetched"] >= MAX_BLOCKS:
            if state["fetched"] >= MAX_BLOCKS and data.get("has_more"):
                state["truncated"] = True
            break
        cursor = data.get("next_cursor")
    return results


def file_url(d: dict) -> str:
    return (d.get("file") or {}).get("url") or (d.get("external") or {}).get("url") or ""


LIST_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do", "toggle"}


def render_block(b: dict, indent: str, out: list, state: dict):
    t = b.get("type", "unsupported")
    d = b.get(t, {}) or {}
    text = rt(d.get("rich_text"))
    has_children = b.get("has_children", False)
    line = None

    if t == "paragraph":
        line = text
    elif t.startswith("heading_") and t[8:].isdigit():
        # 공식 heading_1~4. is_toggleable 헤딩은 접힌 섹션 - ▸ 로 표시
        marker = "▸ " if d.get("is_toggleable") else ""
        line = "#" * min(int(t[8:]), 6) + " " + marker + text
    elif t == "bulleted_list_item":
        line = "- " + text
    elif t == "numbered_list_item":
        line = "1. " + text
    elif t == "to_do":
        line = f"- [{'x' if d.get('checked') else ' '}] {text}"
    elif t == "toggle":
        line = f"- ▸ {text}"
    elif t == "quote":
        line = "> " + text.replace("\n", "\n> ")
    elif t == "callout":
        icon = (d.get("icon") or {}).get("emoji") or "💡"
        line = f"> {icon} " + text.replace("\n", "\n> ")
    elif t == "code":
        cap = rt(d.get("caption"))
        line = f"```{d.get('language', '')}\n{text}\n```" + (f"\n*{cap}*" if cap else "")
    elif t == "divider":
        line = "---"
    elif t == "equation":
        line = f"$$\n{d.get('expression', '')}\n$$"
    elif t == "image":
        line = f"![{rt(d.get('caption'))}]({file_url(d)})"
    elif t == "video":
        cap = rt(d.get("caption"))
        line = f'<video src="{file_url(d)}"></video>' + (f" *{cap}*" if cap else "")
    elif t in ("file", "pdf", "audio"):
        name = d.get("name") or t
        line = f"[{t}: {name}]({file_url(d)})"
    elif t in ("bookmark", "embed", "link_preview"):
        cap = rt(d.get("caption")) if d.get("caption") else ""
        line = f"<{d.get('url', '')}>" + (f" *{cap}*" if cap else "")
    elif t == "child_page":
        line = f"📄 **child page:** {d.get('title', '')} `(id: {b['id']})`"
        has_children = False  # 하위 페이지로 내려가지 않는다 (비용 가드)
    elif t == "child_database":
        line = f"🗃️ **child database:** {d.get('title', '')} `(id: {b['id']})`"
        has_children = False
    elif t == "table":
        rows = get_children(b["id"], state)
        lines = []
        for i, r in enumerate(rows):
            cells = [rt(c).replace("|", "\\|") for c in r.get("table_row", {}).get("cells", [])]
            lines.append("| " + " | ".join(cells) + " |")
            if i == 0 and cells:
                lines.append("|" + "---|" * len(cells))
        line = "\n".join(lines)
        has_children = False  # 행은 위에서 소비함
    elif t == "synced_block":
        sf = d.get("synced_from")
        if sf and sf.get("block_id"):  # 복제본 → 원본의 children 렌더
            for c in get_children(sf["block_id"], state):
                render_block(c, indent, out, state)
            return
        # 원본은 아래 children 경로로 처리
    elif t in ("column_list", "column", "table_of_contents", "breadcrumb"):
        pass  # 컨테이너/장식 - children 만 따라간다
    else:
        line = f"*[unsupported block: {t}]*"

    if line:
        if state.get("ids"):  # 타입 동봉 - move 가능 여부를 옮기기 전에 판별할 수 있게
            line += f"  ⟨{t} {b['id']}⟩"
        out.append(indent + line.replace("\n", "\n" + indent) if indent else line)

    if has_children:
        child_indent = indent + ("  " if t in LIST_TYPES else "")
        for c in get_children(b["id"], state):
            render_block(c, child_indent, out, state)


def page_to_markdown(pid: str, show_ids: bool = False):
    """(title, url, markdown) 반환. 페이지가 아니면 데이터베이스로 재시도."""
    state = {"fetched": 0, "truncated": False, "ids": show_ids}
    try:
        page = call("GET", f"/pages/{pid}")
    except ApiError as e:
        if e.code != 404:
            raise
        return database_to_markdown(pid)
    title = page_title(page)
    url = page.get("url", "")
    out = []
    for b in get_children(pid, state):
        render_block(b, "", out, state)
    md = f"# {title}\n\n" + "\n\n".join(out)
    if state["truncated"]:
        md += f"\n\n---\n*[TRUNCATED: 블록 {MAX_BLOCKS}개 상한 도달 - 페이지 뒷부분 생략됨]*"
    return title, url, md


def database_to_markdown(dbid: str):
    db = call("GET", f"/databases/{dbid}")
    title = rt(db.get("title")) or "(untitled database)"
    url = db.get("url", "")
    props = ", ".join(f"{k}({v.get('type')})" for k, v in db.get("properties", {}).items())
    lines = [f"# 🗃️ {title}", f"**properties:** {props}", "", "## Rows (최대 100)"]
    data = call("POST", f"/databases/{dbid}/query", {"page_size": 100})
    for row in data.get("results", []):
        lines.append(f"- {page_title(row)} `(id: {row['id']})` {row.get('url', '')}")
    if data.get("has_more"):
        lines.append("- *[더 있음 - 100행 초과]*")
    return title, url, "\n".join(lines)


# ---------- 페이지 속성 (DB 카드 워크플로: 상태 변경 등) ----------

def prop_value_str(p: dict) -> str:
    t = p.get("type")
    v = p.get(t)
    if v is None:
        return "(비어있음)"
    if t in ("title", "rich_text"):
        return rt(v) or "(비어있음)"
    if t in ("select", "status"):
        return v.get("name", "(비어있음)")
    if t == "multi_select":
        return ", ".join(o.get("name", "") for o in v) or "(비어있음)"
    if t == "date":
        return (v.get("start") or "") + (f" → {v['end']}" if v.get("end") else "")
    if t == "people":
        return ", ".join(u.get("name", "?") for u in v) or "(비어있음)"
    if t == "relation":
        return f"{len(v)}개 연결"
    if t in ("formula", "rollup"):
        return f"(읽기전용 {t})"
    return str(v)


def build_prop_payload(ptype: str, value: str):
    """문자열 값 → 속성 타입에 맞는 payload. 지원 밖 타입은 --json 탈출구 안내."""
    if ptype in ("title", "rich_text"):
        return [{"type": "text", "text": {"content": value}}]
    if ptype in ("select", "status"):
        return {"name": value}
    if ptype == "multi_select":
        return [{"name": s.strip()} for s in value.split(",") if s.strip()]
    if ptype == "number":
        return float(value)
    if ptype == "checkbox":
        return value.strip().lower() in ("true", "1", "yes", "y", "on", "체크")
    if ptype == "date":
        parts = [s.strip() for s in value.split("~")]
        d = {"start": parts[0]}
        if len(parts) > 1:
            d["end"] = parts[1]
        return d
    if ptype in ("url", "email", "phone_number"):
        return value
    sys.exit(f"PROP_UNSUPPORTED: {ptype} 타입은 문자열 변환 미지원 - prop <id> --json props.json 사용.")


def cmd_prop(argv):
    pid = to_page_id(argv[0])
    page = call("GET", f"/pages/{pid}")
    props = page.get("properties", {})

    sets = [argv[i + 1] for i, a in enumerate(argv) if a == "--set"]
    use_json = "--json" in argv
    if not sets and not use_json:  # 조회 모드
        for name, p in props.items():
            print(f"{name} [{p.get('type')}] = {prop_value_str(p)}")
        return

    assert_writable(pid)  # 갱신은 쓰기 - 가드 필수 (raw API 우회 경로 봉쇄 목적의 명령)
    if use_json:
        with open(argv[argv.index("--json") + 1], encoding="utf-8") as f:
            payload = json.load(f)
    else:
        payload = {}
        for s in sets:
            if "=" not in s:
                sys.exit(f"BAD_SET: {s!r} - '이름=값' 형식 필요")
            name, value = s.split("=", 1)
            name = name.strip()
            if name not in props:
                sys.exit(f"NO_PROP: {name!r} 속성 없음. 있는 것: {', '.join(props)}")
            ptype = props[name].get("type")
            if ptype in ("formula", "rollup", "created_time", "created_by",
                         "last_edited_time", "last_edited_by", "unique_id"):
                sys.exit(f"PROP_READONLY: {name} 은 {ptype} - 갱신 불가")
            payload[name] = {ptype: build_prop_payload(ptype, value)}
    call("PATCH", f"/pages/{pid}", {"properties": payload})
    for name in payload:
        p = call("GET", f"/pages/{pid}")["properties"].get(name, {})
        print(f"PROP_SET: {name} = {prop_value_str(p)}")


# ---------- 캐시 ----------

def write_cache(pid: str, title: str, url: str, md: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{pid}.md")
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nurl: {url}\nfetched_at: {fetched_at}\n---\n\n{md}\n")
    return path


# ---------- 명령 ----------

def cmd_whoami():
    me = call("GET", "/users/me")
    ws = (me.get("bot") or {}).get("workspace_name", "?")
    print(f"OK: bot \"{me.get('name', '?')}\", workspace \"{ws}\"")
    sample = call("POST", "/search", {"page_size": 10})
    results = sample.get("results", [])
    if not results:
        print("접근 가능한 페이지 0개 - integration 을 페이지에 연결해야 함"
              " (페이지 ⋯ → Connections → integration 추가)")
        return
    print(f"접근 가능한 페이지 샘플 ({len(results)}개):")
    for r in results:
        t = page_title(r) if r.get("object") == "page" else rt(r.get("title"))
        print(f"  [{r.get('object')}] {t}  {r.get('url', '')}")


def cmd_read(target: str, show_ids: bool = False):
    pid = to_page_id(target)
    title, url, md = page_to_markdown(pid, show_ids)
    print(md)
    if not show_ids:  # id 마커가 섞인 출력은 캐시(grep 대상)를 오염시키므로 저장 안 함
        cache = write_cache(pid, title, url, md)
        print(f"\nCACHED: {cache}", file=sys.stderr)
    print(f"SOURCE: {url}", file=sys.stderr)


def cmd_search(query: str):
    data = call("POST", "/search", {"query": query, "page_size": 25})
    results = data.get("results", [])
    if not results:
        print(f"NO_MATCH: 제목에 {query!r} 포함하는 페이지 없음"
              " (공식 API 는 제목만 검색 - 본문은 캐시 rg 로)")
        return
    for r in results:
        t = page_title(r) if r.get("object") == "page" else rt(r.get("title"))
        print(f"[{r.get('object')}] {t}\n  {r.get('url', '')}\n  id: {r.get('id')}"
              f"  edited: {r.get('last_edited_time', '')[:10]}")


def _item_title(r: dict) -> str:
    return page_title(r) if r.get("object") == "page" else (rt(r.get("title")) or "(untitled)")


def _item_icon(r: dict) -> str:
    return "📄" if r.get("object") == "page" else "🗃️"


def cmd_ls(args, limit=1000):
    if args:  # 특정 페이지 아래 한 단계 나열
        pid = to_page_id(args[0])
        state = {"fetched": 0, "truncated": False}
        found = 0
        for b in get_children(pid, state):
            t = b.get("type")
            if t == "child_page":
                print(f"📄 {b['child_page'].get('title', '')}  (id: {b['id']})")
                found += 1
            elif t == "child_database":
                print(f"🗃️ {b['child_database'].get('title', '')}  (id: {b['id']})")
                found += 1
        if not found:
            print("EMPTY: 하위 페이지/데이터베이스 없음 (본문 블록만 있는 페이지)")
        return

    # 전체 트리: search 로 접근 가능한 모든 page/database 수집 후 parent 로 조립
    items = {}
    cursor = None
    while len(items) < limit:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = call("POST", "/search", body)
        for r in data.get("results", []):
            items[r["id"]] = r
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")

    children, roots = {}, []
    for r in items.values():
        p = r.get("parent", {})
        parent_id = p.get("page_id") or p.get("database_id") or p.get("block_id")
        if parent_id and parent_id in items:
            children.setdefault(parent_id, []).append(r)
        else:  # workspace 직속이거나 상위가 미공유 → 루트로 취급
            roots.append(r)

    def newest_first(rs):
        return sorted(rs, key=lambda x: x.get("last_edited_time", ""), reverse=True)

    def walk(r, indent):
        print(f"{indent}{_item_icon(r)} {_item_title(r)}  {r.get('url', '')}")
        for c in newest_first(children.get(r["id"], [])):
            walk(c, indent + "  ")

    for r in newest_first(roots):
        walk(r, "")
    more = " (limit 도달, 더 있을 수 있음)" if len(items) >= limit else ""
    print(f"\nTOTAL: {len(items)} items - 접근 가능(공유된) 범위 기준{more}")


# ---------- 쓰기 (allowlist 가드) ----------

WRITE_ALLOWLIST = os.path.join(CONF_DIR, "write_allowlist")


def assert_writable(pid: str, kind: str = "page"):
    """대상(페이지/블록) 또는 그 조상이 write_allowlist 에 있어야 통과. 아니면 종료.

    회사 워크스페이스 실문서 오염 방지용 - 코드 레벨 가드라 스킬/모델 실수로도 못 뚫는다.
    """
    try:
        with open(WRITE_ALLOWLIST) as f:
            allow = {to_page_id(line) for line in f if line.strip()}
    except FileNotFoundError:
        allow = set()
    if not allow:
        sys.exit("WRITE_DENIED: ~/.claude/notion/write_allowlist 비어 있음.\n"
                 "쓰기를 허용할 최상위 페이지 id 를 한 줄에 하나씩 등록해야 함.")
    cur = pid
    for _ in range(30):  # 조상 체인 상한
        if cur in allow:
            return
        try:
            if kind == "page":
                obj = call("GET", f"/pages/{cur}")
            elif kind == "database":
                obj = call("GET", f"/databases/{cur}")
            else:
                obj = call("GET", f"/blocks/{cur}")
        except ApiError:
            break
        p = obj.get("parent", {})
        if p.get("type") == "page_id":
            cur, kind = to_page_id(p["page_id"]), "page"
        elif p.get("type") == "database_id":
            cur, kind = to_page_id(p["database_id"]), "database"
        elif p.get("type") == "block_id":
            cur, kind = to_page_id(p["block_id"]), "block"
        else:  # workspace 도달
            break
    sys.exit(f"WRITE_DENIED: {pid} 는 로컬 쓰기 허용목록 밖.\n"
             "Notion 권한 문제 아님 - 토큰은 공유된 모든 페이지에 쓰기 가능하지만,\n"
             "실문서 보호를 위해 이 도구가 자체적으로 막는 것 (~/.claude/notion/write_allowlist).\n"
             "유저가 명시 승인했다면: notion_api.py allow '<page-url-or-id>' 로 열 수 있음.")


def cmd_allow(argv):
    pid = to_page_id(argv[0])
    os.makedirs(CONF_DIR, exist_ok=True)
    existing = set()
    try:
        with open(WRITE_ALLOWLIST) as f:
            existing = {to_page_id(line) for line in f if line.strip()}
    except FileNotFoundError:
        pass
    if pid in existing:
        print(f"ALREADY: {pid} 이미 허용목록에 있음")
        return
    with open(WRITE_ALLOWLIST, "a") as f:
        f.write(pid + "\n")
    os.chmod(WRITE_ALLOWLIST, 0o600)
    print(f"ALLOWED: {pid} (+하위 전체) 쓰기 허용. 총 {len(existing) + 1}건")


INLINE_RE = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))")


def md_rich_text(text: str):
    """markdown 인라인(굵게/코드/링크) → rich_text 배열. 나머지는 평문."""
    out = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append({"type": "text", "text": {"content": part[2:-2]},
                        "annotations": {"bold": True}})
        elif part.startswith("`") and part.endswith("`"):
            out.append({"type": "text", "text": {"content": part[1:-1]},
                        "annotations": {"code": True}})
        elif part.startswith("[") and part.endswith(")"):
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            out.append({"type": "text",
                        "text": {"content": m.group(1), "link": {"url": m.group(2)}}})
        else:
            out.append({"type": "text", "text": {"content": part}})
    return out or [{"type": "text", "text": {"content": ""}}]


def md_to_blocks(md: str):
    """markdown 서브셋 → Notion 블록 배열.

    지원: heading 1~3, -/1. 리스트, - [ ] 투두, > 인용, ``` 코드펜스, --- 구분선, 문단.
    """
    blocks, lines, i = [], md.splitlines(), 0
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            lang = s[3:].strip() or "plain text"
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # 닫는 펜스
            blocks.append({"type": "code", "code": {
                "language": lang,
                "rich_text": [{"type": "text", "text": {"content": "\n".join(code)[:2000]}}]}})
            continue
        m = re.match(r"(#{1,4})(>?)\s+(.*)", s)
        if m:
            lvl = len(m.group(1))
            h = {"rich_text": md_rich_text(m.group(3))}
            if m.group(2):  # '#>' 문법 = 토글 헤딩 (예: '####> 히스토리 확인용')
                h["is_toggleable"] = True
            blocks.append({"type": f"heading_{lvl}", f"heading_{lvl}": h})
        elif re.match(r"-\s+\[( |x)\]\s+", s):
            m = re.match(r"-\s+\[( |x)\]\s+(.*)", s)
            blocks.append({"type": "to_do", "to_do": {
                "checked": m.group(1) == "x", "rich_text": md_rich_text(m.group(2))}})
        elif s.startswith(("- ", "* ")):
            blocks.append({"type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": md_rich_text(s[2:])}})
        elif re.match(r"\d+\.\s+", s):
            blocks.append({"type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": md_rich_text(re.sub(r"^\d+\.\s+", "", s))}})
        elif s.startswith("> "):
            blocks.append({"type": "quote", "quote": {"rich_text": md_rich_text(s[2:])}})
        elif s in ("---", "***"):
            blocks.append({"type": "divider", "divider": {}})
        else:
            blocks.append({"type": "paragraph",
                           "paragraph": {"rich_text": md_rich_text(s)}})
        i += 1
    return blocks


def append_blocks(pid: str, blocks, position=None):
    for i in range(0, len(blocks), 100):  # API 는 요청당 100블록 제한
        body = {"children": blocks[i:i + 100]}
        if position:
            body["position"] = position
        res = call("PATCH", f"/blocks/{pid}/children", body)
        if position and res.get("results"):
            # 위치 지정 시 다음 배치는 방금 배치 꼬리 뒤에 - 호출자가 앵커 체이닝을 몰라도 순서 보존
            position = {"type": "after_block", "after_block": {"id": res["results"][-1]["id"]}}


def read_md_arg(argv) -> str:
    if "--file" in argv:
        with open(argv[argv.index("--file") + 1], encoding="utf-8") as f:
            return f.read()
    if "--text" in argv:
        return argv[argv.index("--text") + 1]
    sys.exit("NO_CONTENT: --file <md 경로> 또는 --text '<내용>' 필요.")


def arg_blocks(argv):
    """--json <파일> 이면 블록 JSON 배열 그대로(탈출구), 아니면 markdown 변환."""
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], encoding="utf-8") as f:
            return json.load(f)
    return md_to_blocks(read_md_arg(argv))


def cmd_write(argv):
    parent = to_page_id(argv[0])
    title = argv[1]
    assert_writable(parent)
    blocks = md_to_blocks(read_md_arg(argv)) if ("--file" in argv or "--text" in argv) else []
    page = call("POST", "/pages", {
        "parent": {"page_id": parent},
        "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}},
        "children": blocks[:100]})
    if len(blocks) > 100:
        append_blocks(page["id"], blocks[100:])
    print(f"CREATED: {title}")
    print(f"URL: {page.get('url', '')}")
    print(f"id: {page['id']}")


# ---------- 파일 업로드 (File Upload API: 생성 → 바이트 전송 2단계) ----------

def upload_bytes(data: bytes, filename: str, content_type: str) -> str:
    """단일 파트 업로드(20MB 이하). 성공 시 file_upload id 반환 - 블록에 영구 첨부 가능."""
    import secrets
    up = call("POST", "/file_uploads", {
        "mode": "single_part", "filename": filename, "content_type": content_type})
    boundary = "----nskill" + secrets.token_hex(12)
    body = (
        (f"--{boundary}\r\n"
         f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
         f"Content-Type: {content_type}\r\n\r\n").encode()
        + data + f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        up["upload_url"], data=body, method="POST",
        headers={"Authorization": f"Bearer {get_token()}",
                 "Notion-Version": NOTION_VERSION,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            res = json.load(r)
    except urllib.error.HTTPError as e:
        raise ApiError(e.code, "file upload send 실패: " + e.read().decode(errors="replace")[:200])
    if res.get("status") != "uploaded":
        sys.exit(f"UPLOAD_FAIL: status={res.get('status')}")
    return up["id"]


def guess_content_type(name: str) -> str:
    import mimetypes
    return mimetypes.guess_type(name)[0] or "application/octet-stream"


def upload_from_url(url: str, fallback_name: str) -> str:
    """서명 URL 등에서 바이트를 받아 Notion 에 재업로드. 만료 URL 을 영구 파일로 바꾸는 핵심."""
    name = os.path.basename(url.split("?", 1)[0]) or fallback_name
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    if len(data) > 20 * 1024 * 1024:
        sys.exit(f"UPLOAD_TOO_BIG: {name} 20MB 초과 (multi_part 미구현)")
    return upload_bytes(data, name, guess_content_type(name))


def cmd_upload(argv):
    path = argv[0]
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    fid = upload_bytes(data, name, guess_content_type(name))
    print(f"UPLOADED: {name} → file_upload id {fid}")
    if "--attach" in argv:  # 이미지/파일 블록으로 즉시 첨부
        pid = to_page_id(argv[argv.index("--attach") + 1])
        assert_writable(pid)
        btype = "image" if guess_content_type(name).startswith("image/") else "file"
        append_blocks(pid, [{"type": btype, btype: {
            "type": "file_upload", "file_upload": {"id": fid}}}])
        print(f"ATTACHED: {btype} block → {pid}")


# ---------- 블록 이동 (합성 명령: 복제 → 검증 → 원본 archive) ----------
# API 에 블록 이동 원자 연산이 없다. 이 명령은 "손실 불가" 순서를 보장한다:
# 파괴 동작(archive)은 사본 생성이 확인된 뒤에만 실행 → 최악의 실패 = 중복, 손실은 불가능.

MEDIA_BLOCK_TYPES = {"image", "file", "pdf", "video", "audio"}
UNCOPYABLE_TYPES = {"child_page", "child_database", "link_to_page", "synced_block"}

# 생성 API 가 받는 필드 화이트리스트. GET 응답에는 list_start_index(numbered_list),
# icon: null(paragraph) 같은 응답 전용 필드가 섞여 있고, 그대로 생성에 넘기면
# HTTP 400. 근본 원인 = "응답 스키마 ≠ 생성 스키마" 라서 타입별 허용 필드만 통과시킨다.
_RT = {"rich_text", "color"}
CREATE_FIELDS = {
    "paragraph": _RT,
    "heading_1": _RT | {"is_toggleable"}, "heading_2": _RT | {"is_toggleable"},
    "heading_3": _RT | {"is_toggleable"}, "heading_4": _RT | {"is_toggleable"},
    "bulleted_list_item": _RT, "numbered_list_item": _RT,
    "to_do": _RT | {"checked"}, "toggle": _RT, "quote": _RT,
    "callout": _RT | {"icon"},
    "code": {"rich_text", "language", "caption"},
    "equation": {"expression"},
    "divider": set(), "breadcrumb": set(),
    "table_of_contents": {"color"},
    "bookmark": {"url", "caption"}, "embed": {"url", "caption"},
    "table": {"table_width", "has_column_header", "has_row_header"},
    "table_row": {"cells"},
    "column_list": set(), "column": set(),
}


def block_to_payload(b: dict, state: dict):
    """GET 으로 받은 블록 → 생성용 payload. Notion 내부 파일은 재업로드로 영구화."""
    t = b.get("type")
    if t in UNCOPYABLE_TYPES or t == "unsupported":
        state["skipped"].append(t)
        return None
    if t == "link_preview":  # 생성 불가 타입 - 같은 URL 의 bookmark 로 강등
        return {"type": "bookmark", "bookmark": {"url": (b.get(t) or {}).get("url", "")}}
    d = dict(b.get(t) or {})
    allowed = CREATE_FIELDS.get(t)
    if allowed is not None:
        d = {k: v for k, v in d.items() if k in allowed and v is not None}
    else:  # 목록에 없는 타입: None 값만 제거하는 최선 노력
        d = {k: v for k, v in d.items() if v is not None}
    # callout 아이콘이 업로드 파일이면 생성 시 못 받음 - 제거 (이모지/external 은 통과)
    if t == "callout" and isinstance(d.get("icon"), dict) and d["icon"].get("type") not in ("emoji", "external"):
        d.pop("icon", None)
    if t in MEDIA_BLOCK_TYPES:
        if d.get("type") == "file":  # Notion 내부 호스팅 - 서명 URL 은 1시간 만료
            fid = upload_from_url(d["file"]["url"], f"{t}.bin")
            nd = {"type": "file_upload", "file_upload": {"id": fid}}
        elif d.get("type") == "external":
            nd = {"type": "external", "external": d["external"]}
        elif d.get("type") == "file_upload":
            nd = {"type": "file_upload", "file_upload": d["file_upload"]}
        else:
            state["skipped"].append(t)
            return None
        if d.get("caption"):
            nd["caption"] = d["caption"]
        if t == "file" and d.get("name"):
            nd["name"] = d["name"]
        d = nd
    return {"type": t, t: d}


def copy_block_tree(src_id: str, dest_id: str, state: dict, position=None):
    """src 블록(하위 트리 포함)을 dest 의 children 으로 복제. 생성된 최상위 블록 id 반환."""
    src = call("GET", f"/blocks/{src_id}")
    payload = block_to_payload(src, state)
    if payload is None:
        sys.exit(f"MOVE_UNSUPPORTED: {src.get('type')} 블록은 복제 불가 "
                 f"(child_page/synced_block 등은 Notion UI 에서만 이동 가능).")
    body = {"children": [payload]}
    if position:
        body["position"] = position
    res = call("PATCH", f"/blocks/{dest_id}/children", body)
    new_id = res["results"][0]["id"]
    state["copied"] += 1
    if src.get("has_children"):
        _copy_children_into(src_id, new_id, state)
    return new_id


def _copy_children_into(src_parent: str, dest_parent: str, state: dict):
    """자식들을 레벨 단위로 복제 (요청당 중첩 2단계 제한 우회: 층별 append)."""
    fetch_state = {"fetched": 0, "truncated": False}
    kids = get_children(src_parent, fetch_state)
    payloads, sources = [], []
    for k in kids:
        p = block_to_payload(k, state)
        if p is None:
            continue
        payloads.append(p)
        sources.append(k)
    for i in range(0, len(payloads), 100):
        res = call("PATCH", f"/blocks/{dest_parent}/children",
                   {"children": payloads[i:i + 100]})
        for created, src in zip(res["results"], sources[i:i + 100]):
            state["copied"] += 1
            if src.get("has_children"):
                _copy_children_into(src["id"], created["id"], state)


MOVE_API_VERSION = "2026-03-11"  # pages/{id}/move + data_sources 는 신버전 전용


def resolve_move_parent(dest: str) -> dict:
    """이동 목적지 → parent 객체. DB 면 data_source_id, 아니면 page_id."""
    try:
        db = call("GET", f"/databases/{dest}", version=MOVE_API_VERSION)
        sources = db.get("data_sources", [])
        if len(sources) > 1:
            names = ", ".join(f"{s.get('name')}={s.get('id')}" for s in sources)
            sys.exit(f"MULTI_SOURCE_DB: 데이터 소스가 여러 개 - id 로 직접 지정 필요: {names}")
        if sources:
            return {"type": "data_source_id", "data_source_id": sources[0]["id"]}
    except ApiError:
        pass  # DB 아님 → 페이지 취급
    return {"type": "page_id", "page_id": dest}


def cmd_move(argv):
    if "--to" not in argv:
        sys.exit("USAGE: move <id[,id2,...]> --to <dest> [--after <block_id> | --start]")
    srcs = [to_page_id(x) for x in argv[0].split(",") if x.strip()]
    dest = to_page_id(argv[argv.index("--to") + 1])
    for s in srcs:
        assert_writable(s, kind="block")
    assert_writable(dest, kind="block")

    position = None
    if "--after" in argv:
        position = {"type": "after_block",
                    "after_block": {"id": to_page_id(argv[argv.index("--after") + 1])}}
    elif "--start" in argv:
        position = {"type": "start"}

    for src in srcs:
        # 1층: 페이지(DB 행 포함)면 공식 move 엔드포인트 - 원자 연산, id 보존(링크 안 깨짐)
        is_page = True
        try:
            call("GET", f"/pages/{src}")
        except ApiError:
            is_page = False
        if is_page:
            parent = resolve_move_parent(dest)
            moved = call("POST", f"/pages/{src}/move", {"parent": parent}, version=MOVE_API_VERSION)
            kind = "data_source" if parent["type"] == "data_source_id" else "page"
            print(f"MOVED(page): {page_title(moved)} → {kind} {dest} (id 보존, 링크/히스토리 유지)", flush=True)
            continue

        # 2층: 블록이면 복제→검증→archive 합성 (블록 이동 API 는 없음)
        state = {"copied": 0, "skipped": []}
        new_id = copy_block_tree(src, dest, state, position)
        call("DELETE", f"/blocks/{src}")  # 사본 확인 후에만 원본 archive
        note = f", 스킵 {len(state['skipped'])}개({','.join(set(state['skipped']))})" if state["skipped"] else ""
        print(f"MOVED(block): {state['copied']}블록 복제{note} → 새 위치 ⟨{new_id}⟩, 원본 archive 완료 (휴지통 복구 가능)", flush=True)
        # 다중 이동 시 원본 순서 유지: 다음 블록은 방금 만든 사본 뒤에 삽입
        position = {"type": "after_block", "after_block": {"id": new_id}}


RICH_TEXT_TYPES = {"paragraph", "heading_1", "heading_2", "heading_3", "heading_4",
                   "bulleted_list_item", "numbered_list_item", "to_do",
                   "toggle", "quote", "callout"}


def cmd_edit(argv):
    bid = to_page_id(argv[0])
    assert_writable(bid, kind="block")
    new = read_md_arg(argv).strip()
    b = call("GET", f"/blocks/{bid}")
    t = b.get("type")
    if t == "code":
        payload = {"code": {"rich_text": [{"type": "text", "text": {"content": new[:2000]}}]}}
    elif t in RICH_TEXT_TYPES:
        payload = {t: {"rich_text": md_rich_text(new)}}
    else:
        sys.exit(f"EDIT_UNSUPPORTED: {t} 블록은 텍스트 교체 불가 (텍스트 계열 블록만 지원).")
    call("PATCH", f"/blocks/{bid}", payload)
    print(f"EDITED: {t} ⟨{bid}⟩")


def cmd_delete(argv):
    bid = to_page_id(argv[0])
    assert_writable(bid, kind="block")
    b = call("GET", f"/blocks/{bid}")
    call("DELETE", f"/blocks/{bid}")
    print(f"DELETED(archived): {b.get('type')} ⟨{bid}⟩ - Notion 휴지통에서 복구 가능")


def cmd_append(argv):
    pid = to_page_id(argv[0])
    assert_writable(pid, kind="block")
    blocks = arg_blocks(argv)
    position = None  # move 와 대칭: --start / --after 지원
    if "--after" in argv:
        position = {"type": "after_block",
                    "after_block": {"id": to_page_id(argv[argv.index("--after") + 1])}}
    elif "--start" in argv:
        position = {"type": "start"}
    append_blocks(pid, blocks, position)
    where = "맨 위" if position and position["type"] == "start" else ("지정 위치" if position else "끝")
    print(f"APPENDED: {len(blocks)} blocks → {pid} ({where})")


def cmd_sync(limit: int):
    n, cursor = 0, None
    while n < limit:
        body = {"page_size": 100, "filter": {"value": "page", "property": "object"}}
        if cursor:
            body["start_cursor"] = cursor
        data = call("POST", "/search", body)
        for pg in data.get("results", []):
            if n >= limit:
                break
            pid = pg["id"]
            try:
                title, url, md = page_to_markdown(pid)
                write_cache(pid, title, url, md)
                n += 1
                print(f"[{n}/{limit}] {title}", flush=True)
            except ApiError as e:
                print(f"  skip {pid}: HTTP {e.code}", flush=True)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    print(f"SYNCED: {n} pages → {CACHE_DIR}")


def cmd_login(argv):
    # 폴백: internal integration 토큰 직접 저장
    if "--token" in argv:
        tok = argv[argv.index("--token") + 1].strip()
        save_auth({"access_token": tok, "method": "internal"})
        print("토큰 저장됨. 검증:")
        cmd_whoami()
        return

    app = load_json(OAUTH_APP_FILE)
    if not app or not app.get("client_id") or not app.get("client_secret"):
        sys.exit(
            "OAUTH_APP_MISSING: ~/.claude/notion/oauth_app.json 없음.\n"
            "관리자에게 client_id/client_secret 을 받아 아래 형식으로 저장:\n"
            '  {"client_id": "...", "client_secret": "...", "port": 8917}\n'
            "(chmod 600 권장) 또는 internal 토큰으로: login --token <TOKEN>")

    import http.server
    import secrets
    import webbrowser

    port = int(app.get("port", DEFAULT_PORT))
    redirect_uri = f"http://localhost:{port}/callback"
    state = secrets.token_urlsafe(16)
    auth_url = (f"{API}/oauth/authorize?client_id={urllib.parse.quote(app['client_id'])}"
                f"&response_type=code&owner=user"
                f"&redirect_uri={urllib.parse.quote(redirect_uri)}"
                f"&state={state}")

    result = {}

    class Callback(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            if parsed.path != "/callback":
                self.send_response(404)
                self.end_headers()
                return
            if qs.get("state", [""])[0] != state:
                result["error"] = "state mismatch (CSRF 의심)"
            elif qs.get("error"):
                result["error"] = qs["error"][0]
            else:
                result["code"] = qs.get("code", [""])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "로그인 실패 - 터미널 확인" if "error" in result else "로그인 완료 - 이 탭을 닫고 터미널로 돌아가세요"
            self.wfile.write(f"<html><body style='font-family:sans-serif'><h2>{msg}</h2></body></html>".encode())

        def log_message(self, *a):  # 콜백 서버 로그 침묵
            pass

    try:
        server = http.server.HTTPServer(("127.0.0.1", port), Callback)
    except OSError as e:
        sys.exit(f"PORT_BUSY: localhost:{port} 사용 중 ({e}). 점유 프로세스 종료 후 재시도.")

    print(f"브라우저에서 Notion 로그인 + 공유할 페이지 선택 진행 (최대 {OAUTH_TIMEOUT}초 대기)")
    print(f"브라우저가 안 열리면 직접 열기: {auth_url}")
    webbrowser.open(auth_url)

    server.timeout = 1
    deadline = time.time() + OAUTH_TIMEOUT
    while not result and time.time() < deadline:
        server.handle_request()
    server.server_close()

    if not result:
        sys.exit("LOGIN_TIMEOUT: 콜백 미수신. 브라우저에서 승인했는지 확인 후 재시도.")
    if "error" in result:
        sys.exit(f"LOGIN_FAIL: {result['error']}")

    tokens = oauth_token_request(app, {
        "grant_type": "authorization_code",
        "code": result["code"],
        "redirect_uri": redirect_uri})
    tokens["method"] = "oauth"
    save_auth(tokens)
    ws = tokens.get("workspace_name", "?")
    print(f"OK: workspace \"{ws}\" 로그인 완료 → {AUTH_FILE}")
    print("접근 범위 확인:")
    cmd_whoami()


def cmd_logout(keep_cache: bool):
    removed = []
    if os.path.exists(AUTH_FILE):
        os.remove(AUTH_FILE)
        removed.append("auth.json")
    if os.path.exists(TOKEN_FILE):
        os.remove(TOKEN_FILE)
        removed.append("token")
    if not keep_cache and os.path.isdir(CACHE_DIR):
        import shutil
        shutil.rmtree(CACHE_DIR)
        removed.append("cache")
    if removed:
        print(f"LOGOUT: 삭제됨 - {', '.join(removed)}")
    else:
        print("LOGOUT: 삭제할 것 없음 (이미 로그아웃 상태)")
    if keep_cache and os.path.isdir(CACHE_DIR):
        print(f"캐시 유지됨: {CACHE_DIR}")
    print("integration 자체 폐기는 https://www.notion.so/my-integrations 에서 직접.")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    cmd = sys.argv[1]
    try:
        if cmd == "whoami":
            cmd_whoami()
        elif cmd == "login":
            cmd_login(sys.argv[2:])
        elif cmd == "logout":
            cmd_logout("--keep-cache" in sys.argv)
        elif cmd == "ls":
            cmd_ls(sys.argv[2:])
        elif cmd == "read":
            cmd_read(sys.argv[2], "--ids" in sys.argv)
        elif cmd == "edit":
            cmd_edit(sys.argv[2:])
        elif cmd == "delete":
            cmd_delete(sys.argv[2:])
        elif cmd == "search":
            cmd_search(sys.argv[2] if len(sys.argv) > 2 else "")
        elif cmd == "write":
            cmd_write(sys.argv[2:])
        elif cmd == "append":
            cmd_append(sys.argv[2:])
        elif cmd == "prop":
            cmd_prop(sys.argv[2:])
        elif cmd == "allow":
            cmd_allow(sys.argv[2:])
        elif cmd == "upload":
            cmd_upload(sys.argv[2:])
        elif cmd == "move":
            cmd_move(sys.argv[2:])
        elif cmd == "sync":
            cmd_sync(int(sys.argv[2]) if len(sys.argv) > 2 else 200)
        else:
            print(__doc__)
            sys.exit(2)
    except ApiError as e:
        if e.code == 401:
            sys.exit(f"AUTH_FAIL: 토큰이 유효하지 않음 ({e}). /notion-login 으로 재로그인.")
        if e.code in (403, 404):
            sys.exit(f"NO_ACCESS: 페이지에 integration 이 연결되지 않았거나 없음 ({e}).\n"
                     "페이지 ⋯ 메뉴 → Connections → integration 추가 후 재시도.")
        sys.exit(str(e))


if __name__ == "__main__":
    main()
