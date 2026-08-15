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
         [--filter '이름=값']... [--filter-json f.json] [--sort '[-]이름']...
         [--limit N] [--source <이름|id>]
                      페이지를 markdown 으로 출력(stdout) + 캐시 저장.
                      --ids 면 블록마다 ⟨타입 id⟩ 표시 - edit/delete/move 대상 특정 +
                      이동 가능 여부 사전 판별용 (이 모드는 캐시 안 씀)
                      DB 면 스키마 + 행 표 렌더. --filter (여러 개 = and, enum/숫자는
                      equals, 텍스트는 contains), --sort ('-' 접두 = 내림차순,
                      created/edited = 시간 정렬), --limit (기본 100), multi-source DB 는
                      --source 로 소스 선택. 필터/정렬된 부분 뷰는 캐시 안 씀
    edit <block_id> --text '<새 내용>'
                      블록 본문 교체 (allowlist 하위만, 타입 유지)
    delete <block_id> 블록 archive (Notion 휴지통 복구 가능, allowlist 하위만)
    search <query>    2층 검색: 공식 /v1/search 제목 매칭 + 로컬 캐시 본문 매칭
                      (본문층은 sync 로 만든 캐시 기준 - fetched_at 시점 표시)
    sql '<SELECT ...>' --db <url|id> [--db ...] [--source S] [--limit N]
                      DB 행들을 메모리 SQLite 로 적재 후 읽기 전용 쿼리.
                      조인/집계/서브쿼리 가능. 테이블명 t (여러 개면 t1,t2,...),
                      컬럼 = 속성명 + id, url. 날짜는 시작일, 체크박스는 0/1
    edit-str <url|id> --old '<기존>' --new '<새>' [--all]
                      블록 내 문자열 치환 (read 출력의 markdown 형태로 매칭).
                      복수 매칭 시 목록 보여주고 중단, --all 로 전부 치환.
                      블록 하나 안의 문자열만 가능 (Notion 구조 제약)
    write <parent-url|id> <title> [--file md.md] [--prop '이름=값']... [--source S]
                      allowlist 하위에만 새 페이지 생성 (markdown → 블록 변환)
                      md 확장 문법: '#> 제목'~'####> 제목' = 토글 헤딩
                      parent 가 DB 면 행 생성 - --prop 로 속성 지정 (prop --set 과 같은
                      문자열 규칙), multi-source DB 는 --source 로 소스 선택
    db-create <parent-url|id> <제목> [--prop '이름:타입[:옵션들]']... | [--json schema.json]
                      allowlist 하위 페이지에 새 DB 생성. 타입: title/rich_text/number/
                      checkbox/date/url/email/phone_number/select/multi_select/people/
                      files (select 계열은 ':옵션1,옵션2' 로 선택지). title 미지정 시
                      '이름' 자동 추가. status 는 API 생성 불가(UI 전용)
    db-prop <db-url|id> [--source S]
                      DB 스키마 조회 (이름 [타입] (선택지))
    db-prop <db-url|id> --add '이름:타입[:옵션들]' | --rename '기존=새' | --remove '이름'
                      스키마 변경 (여러 개 조합 가능, allowlist 가드)
    append <url|id> --file md.md | --text '...' | --json blocks.json
                     [--start | --after <block_id>]
                      allowlist 하위 페이지에 블록 추가. 기본 끝, --start 면 맨 위,
                      --after 면 지정 블록 뒤 (--json = 원시 블록 탈출구)
    duplicate <url|id> [--to <dest>] [--title '<새 제목>']
                      페이지/DB행 복제 (속성 + 본문 트리, 내부 파일 재업로드).
                      기본 목적지 = 원본과 같은 부모. 기본 제목 = '원본 (copy)'
    archive <url|id>  페이지/블록을 휴지통으로 (복구 가능)
    restore <url|id>  휴지통에서 복구 (archived 해제)
    prop <url|id>     페이지 속성 나열 (이름 [타입] = 값)
    prop <url|id> --set '이름=값' [--set ...] | --json props.json
                      속성 갱신 (allowlist 가드). select/status/multi_select(쉼표)/
                      number/checkbox/date(시작~끝)/url/email/title/rich_text 지원
    comments <url|id> [--all]
                      미해결 댓글 목록 (discussion 단위, 작성자/시각). 기본은 페이지
                      레벨 스레드만 - --all 이면 블록 전체를 돌며 인라인 댓글까지
                      (블록 수만큼 호출, 큰 페이지는 느림). resolved 는 API 미노출
    comment <url|block-id> --text '<내용>' [--reply <discussion_id>]
                      댓글 게시 (write ∪ comment 허용목록 하위만). --reply 는 기존
                      스레드에 답글 - 이때 첫 인자는 스레드가 있는 페이지(가드용).
                      주의: API 로 댓글 삭제 불가 - UI 에서만 지울 수 있다
    users             워크스페이스 멤버/봇 목록 (people 속성 값, 담당자 지정용)
    allow <url|id>    쓰기 허용목록에 페이지 추가 (유저 명시 승인 후에만 사용)
    allow --comment <url|id>
                      댓글 전용 허용목록에 추가 (본문 쓰기는 계속 차단됨)
    upload <path> [--attach <url|id>]
                      File Upload API 로 영구 업로드, --attach 면 이미지/파일 블록로 첨부
    move <page|block_id> --to <dest> [--after <block_id> | --start]
                      2계층 자동 분기:
                      - 페이지/DB행 → 공식 move 엔드포인트(원자, id 보존=링크/히스토리 유지).
                        목적지가 DB 면 data_source 자동 해석. DB간 이동 지원.
                      - 블록 → 복제→검증→원본 archive 합성. 내부 파일은 재업로드로 영구화.
                      DB 자체는 이동 불가(API 한계). --after/--start 는 블록 이동 전용
    sync [limit] [--full]
                      접근 가능한 페이지+DB 를 순회하며 캐시 구축 (기본 200장 제한)
                      본문 grep 은 이 캐시 위에서 rg 로 한다. DB 는 행 표로 캐시됨.
                      증분: last_edited_time 이 캐시와 같으면 생략, --full 로 강제 전체.

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
DS_API_VERSION = "2026-03-11"  # data_sources 계열 + pages/{id}/move 신버전 전용
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


def ancestor_path(obj: dict, max_depth: int = 5) -> str:
    """부모 체인을 '상위 > ... > 직계부모' 문자열로. 동명 문서 구분, 위치 파악용."""
    names = []
    p = obj.get("parent", {})
    for _ in range(max_depth):
        try:
            if p.get("type") == "page_id":
                parent = call("GET", f"/pages/{p['page_id']}")
                names.append(page_title(parent))
            elif p.get("type") == "database_id":
                parent = call("GET", f"/databases/{p['database_id']}")
                names.append("🗃️ " + (rt(parent.get("title")) or "(untitled)"))
            elif p.get("type") == "block_id":
                parent = call("GET", f"/blocks/{p['block_id']}")
                p = parent.get("parent", {})
                continue  # 블록은 경로에 이름 없이 통과
            else:
                break  # workspace 도달
            p = parent.get("parent", {})
        except ApiError:
            break
    return " > ".join(reversed(names))


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


def page_to_markdown(pid: str, show_ids: bool = False, query: dict = None):
    """(title, url, markdown, last_edited) 반환. 페이지가 아니면 데이터베이스로 재시도."""
    state = {"fetched": 0, "truncated": False, "ids": show_ids}
    try:
        page = call("GET", f"/pages/{pid}")
    except ApiError as e:
        # DB id 를 /pages 에 주면 400("is a database"), 미공유/없음이면 404 - 둘 다 DB 로 재시도
        if e.code not in (400, 404):
            raise
        return database_to_markdown(pid, query)
    title = page_title(page)
    url = page.get("url", "")
    out = []
    path = ancestor_path(page)
    if path:
        out.append(f"경로: {path}")
    # DB 행이면 속성부터 - 상태/담당자 같은 메타데이터가 본문만큼 중요하다
    if page.get("parent", {}).get("type") in ("database_id", "data_source_id"):
        plines = [f"- {n} [{p.get('type')}]: {prop_value_str(p)}"
                  for n, p in page.get("properties", {}).items() if p.get("type") != "title"]
        if plines:
            out.append("**속성**\n" + "\n".join(plines))
    for b in get_children(pid, state):
        render_block(b, "", out, state)
    md = f"# {title}\n\n" + "\n\n".join(out)
    if state["truncated"]:
        md += f"\n\n---\n*[TRUNCATED: 블록 {MAX_BLOCKS}개 상한 도달 - 페이지 뒷부분 생략됨]*"
    return title, url, md, page.get("last_edited_time", "")


def build_filter(schema: dict, expr: str) -> dict:
    """'이름=값' → query filter 객체. enum/숫자/체크/날짜는 equals, 텍스트는 contains."""
    if "=" not in expr:
        sys.exit(f"BAD_FILTER: {expr!r} - '이름=값' 형식 필요")
    name, value = expr.split("=", 1)
    name = name.strip()
    p = schema.get(name)
    if not p:
        sys.exit(f"NO_PROP: 필터 속성 {name!r} 없음. 있는 것: {', '.join(schema)}")
    t = p.get("type")
    if t in ("select", "status"):
        cond = {"equals": value}
    elif t == "multi_select":
        cond = {"contains": value}
    elif t == "checkbox":
        cond = {"equals": value.strip().lower() in ("true", "1", "yes", "y", "on", "체크")}
    elif t == "number":
        cond = {"equals": float(value)}
    elif t == "date":
        cond = {"equals": value}
    elif t in ("title", "rich_text", "url", "email", "phone_number"):
        cond = {"contains": value}
    else:
        sys.exit(f"FILTER_UNSUPPORTED: {t} 타입은 --filter 미지원 - --filter-json <파일> 사용")
    return {"property": name, t: cond}


def build_sorts(exprs) -> list:
    """['이름', '-이름', 'edited'] → sorts 배열. '-' 접두 = 내림차순, created/edited = 시간 정렬."""
    sorts = []
    for e in exprs:
        e = e.strip()
        direction = "descending" if e.startswith("-") else "ascending"
        name = e.lstrip("-")
        if name in ("created", "edited"):
            sorts.append({"timestamp": "created_time" if name == "created" else "last_edited_time",
                          "direction": direction})
        else:
            sorts.append({"property": name, "direction": direction})
    return sorts


def query_data_source(ds_id: str, body_extra: dict, limit: int):
    """POST /data_sources/{id}/query 페이지네이션 - limit 행까지 수집. (rows, 더있음) 반환."""
    rows, cursor = [], None
    while len(rows) < limit:
        body = dict(body_extra)
        body["page_size"] = min(100, limit - len(rows))
        if cursor:
            body["start_cursor"] = cursor
        data = call("POST", f"/data_sources/{ds_id}/query", body, version=DS_API_VERSION)
        rows += data.get("results", [])
        if not data.get("has_more"):
            return rows, False
        cursor = data.get("next_cursor")
    return rows, True


def rows_to_table(schema: dict, rows) -> list:
    """행 목록 → markdown 표. 컬럼 = title 먼저, 나머지 스키마 순, 끝에 id."""
    names = [n for n, p in schema.items() if p.get("type") == "title"] \
        + [n for n, p in schema.items() if p.get("type") != "title"]

    def esc(s):
        return s.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(esc(n) for n in names) + " | id |",
             "|" + "---|" * (len(names) + 1)]
    for row in rows:
        props = row.get("properties", {})
        cells = [esc(prop_value_str(props[n])) if n in props else "" for n in names]
        lines.append("| " + " | ".join(cells) + f" | {row['id']} |")
    return lines


def database_to_markdown(dbid: str, query: dict = None):
    """DB → 스키마 + 행 표 markdown. multi-source DB 는 소스별 섹션으로 렌더."""
    query = query or {}
    db = call("GET", f"/databases/{dbid}", version=DS_API_VERSION)
    title = rt(db.get("title")) or "(untitled database)"
    url = db.get("url", "")
    lines = [f"# 🗃️ {title}"]
    path = ancestor_path(db)
    if path:
        lines.append(f"경로: {path}")
    sources = db.get("data_sources", [])
    sel = query.get("source")
    if sel:
        sources = [s for s in sources if sel in (s.get("id"), s.get("name"))]
        if not sources:
            sys.exit(f"NO_SOURCE: --source {sel!r} 매칭 실패")
    if not sources:
        lines.append("*데이터 소스 없음*")
    limit = query.get("limit") or 100
    for s in sources:
        ds = call("GET", f"/data_sources/{s['id']}", version=DS_API_VERSION)
        schema = ds.get("properties", {})
        if len(sources) > 1:
            lines.append(f"\n## data source: {s.get('name')} `(id: {s['id']})`")
        lines.append("**properties:** " + ", ".join(
            f"{k}({v.get('type')})" for k, v in schema.items()))
        body = {}
        if query.get("filter_json"):
            body["filter"] = query["filter_json"]
        elif query.get("filters"):
            fs = [build_filter(schema, e) for e in query["filters"]]
            body["filter"] = fs[0] if len(fs) == 1 else {"and": fs}
        if query.get("sorts"):
            body["sorts"] = build_sorts(query["sorts"])
        rows, more = query_data_source(s["id"], body, limit)
        note = " - 더 있음, --limit 로 확장" if more else ""
        lines.append(f"\n## Rows ({len(rows)}행{note})")
        lines += rows_to_table(schema, rows) if rows else ["*조건에 맞는 행 없음*"]
    return title, url, "\n".join(lines), db.get("last_edited_time", "")


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
        # 계산 결과 값을 그대로 보여준다 - DB 표에서 합계/판정 컬럼이 읽히도록
        inner_t = v.get("type")
        inner = v.get(inner_t)
        if inner_t == "array":
            return ", ".join(prop_value_str(x) for x in inner) or "(비어있음)"
        if inner_t == "date" and isinstance(inner, dict):
            return (inner.get("start") or "") + (f" → {inner['end']}" if inner.get("end") else "")
        return "(비어있음)" if inner is None else str(inner)
    if t == "files":
        return ", ".join(f.get("name", "?") for f in v) or "(비어있음)"
    if t == "unique_id":
        prefix = v.get("prefix")
        return f"{prefix}-{v.get('number')}" if prefix else str(v.get("number"))
    if t in ("created_by", "last_edited_by"):
        return v.get("name", "?")
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
    if ptype == "people":  # '이름' / '이메일' / 'id' 쉼표 구분 - users 목록에서 해석
        return [{"id": resolve_user(s.strip())} for s in value.split(",") if s.strip()]
    if ptype == "relation":  # 연결할 페이지 id/URL 쉼표 구분
        return [{"id": to_page_id(s)} for s in value.split(",") if s.strip()]
    sys.exit(f"PROP_UNSUPPORTED: {ptype} 타입은 문자열 변환 미지원 - prop <id> --json props.json 사용.")


# ---------- 사용자 (people 속성 해석 + 멘션 대상 조회) ----------

def list_users():
    results, cursor = [], None
    while True:
        q = "/users?page_size=100" + (f"&start_cursor={urllib.parse.quote(cursor)}" if cursor else "")
        try:
            data = call("GET", q)
        except ApiError as e:
            if e.code == 403:  # OAuth 개인 토큰(personal access token)은 목록 조회 금지
                sys.exit("USERS_RESTRICTED: 이 토큰 타입은 유저 목록 조회 불가 (API 제약 -\n"
                         "OAuth personal access token). internal integration 토큰으로 로그인하면\n"
                         "가능. people 속성은 'user id' 를 직접 넣으면 이 토큰으로도 설정됨.")
            raise
        results += data.get("results", [])
        if not data.get("has_more"):
            return results
        cursor = data.get("next_cursor")


def resolve_user(sel: str) -> str:
    """이름/이메일/id → user id. 애매하면(동명이인) 후보를 보여주고 종료."""
    if UUID_RE.fullmatch(sel.replace("-", "")):
        return to_page_id(sel)
    hits = [u for u in list_users()
            if u.get("name") == sel or (u.get("person") or {}).get("email") == sel]
    if not hits:
        sys.exit(f"NO_USER: {sel!r} 매칭 없음. `users` 명령으로 목록 확인.")
    if len(hits) > 1:
        cands = ", ".join(f"{u.get('name')}={u['id']}" for u in hits)
        sys.exit(f"AMBIGUOUS_USER: {sel!r} 후보 여러 명 - id 로 지정: {cands}")
    return hits[0]["id"]


def cmd_users():
    for u in list_users():
        t = u.get("type", "?")
        email = (u.get("person") or {}).get("email", "") if t == "person" else ""
        print(f"[{t}] {u.get('name', '?')}  {email}  id: {u['id']}")


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

def write_cache(pid: str, title: str, url: str, md: str, edited: str = "") -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{pid}.md")
    fetched_at = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"---\ntitle: {title}\nurl: {url}\nfetched_at: {fetched_at}\n"
                f"edited: {edited}\n---\n\n{md}\n")
    return path


def cached_edited(pid: str) -> str:
    """캐시된 페이지의 last_edited_time (sync 증분 비교용). 없으면 ''."""
    try:
        with open(os.path.join(CACHE_DIR, f"{pid}.md"), encoding="utf-8") as f:
            for _ in range(6):  # frontmatter 안에서만 찾는다
                line = f.readline()
                if line.startswith("edited: "):
                    return line[8:].strip()
        return ""
    except (FileNotFoundError, OSError):
        return ""


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


def parse_query_opts(argv) -> dict:
    """read 의 DB 조회 옵션 (--filter/--filter-json/--sort/--limit/--source) 파싱."""
    q = {}
    fs = [argv[i + 1] for i, a in enumerate(argv) if a == "--filter"]
    if fs:
        q["filters"] = fs
    if "--filter-json" in argv:
        with open(argv[argv.index("--filter-json") + 1], encoding="utf-8") as f:
            q["filter_json"] = json.load(f)
    ss = [argv[i + 1] for i, a in enumerate(argv) if a == "--sort"]
    if ss:
        q["sorts"] = ss
    if "--limit" in argv:
        q["limit"] = int(argv[argv.index("--limit") + 1])
    if "--source" in argv:
        q["source"] = argv[argv.index("--source") + 1]
    return q


def cmd_read(argv):
    pid = to_page_id(argv[0])
    show_ids = "--ids" in argv
    query = parse_query_opts(argv)
    title, url, md, edited = page_to_markdown(pid, show_ids, query)
    print(md)
    # id 마커나 필터/정렬된 부분 뷰는 캐시(grep 대상)를 오염시키므로 저장 안 함
    if not show_ids and not query:
        cache = write_cache(pid, title, url, md, edited)
        print(f"\nCACHED: {cache}", file=sys.stderr)
    print(f"SOURCE: {url}", file=sys.stderr)


def _cache_body_search(query: str, exclude_ids: set):
    """로컬 캐시 본문 검색 (공식 API 는 제목만 검색하는 제약의 우회층)."""
    try:
        files = [f for f in os.listdir(CACHE_DIR) if f.endswith(".md")]
    except FileNotFoundError:
        return None  # 캐시 자체가 없음
    q = query.lower()
    hits = []
    for fn in files:
        pid = fn[:-3]
        if pid in exclude_ids:
            continue
        try:
            with open(os.path.join(CACHE_DIR, fn), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if q not in text.lower():
            continue
        lines = text.splitlines()
        title = url = fetched = ""
        for line in lines[:6]:
            if line.startswith("title: "):
                title = line[7:]
            elif line.startswith("url: "):
                url = line[5:]
            elif line.startswith("fetched_at: "):
                fetched = line[12:]
        snips = [ln.strip()[:100] for ln in lines[6:] if q in ln.lower()][:2]
        hits.append((title, url, fetched, snips))
    return hits


def cmd_search(query: str):
    data = call("POST", "/search", {"query": query, "page_size": 25})
    results = data.get("results", [])
    if results:
        print(f"== 제목 매칭 ({len(results)}건) ==")
        for r in results:
            t = page_title(r) if r.get("object") == "page" else rt(r.get("title"))
            print(f"[{r.get('object')}] {t}\n  {r.get('url', '')}\n  id: {r.get('id')}"
                  f"  edited: {r.get('last_edited_time', '')[:10]}")
    else:
        print(f"제목 매칭 없음: {query!r} (공식 API 는 제목만 검색)")

    # 2층: 캐시 본문 - 제목 검색이 못 잡는 본문 언급을 잡는다
    body_hits = _cache_body_search(query, {r.get("id", "") for r in results})
    if body_hits is None:
        print("\n본문 검색 불가: 캐시 없음 - `sync` 로 미러 구축 후 재시도")
    elif body_hits:
        print(f"\n== 본문 매칭 (로컬 캐시 {len(body_hits)}건, fetched_at 시점 기준) ==")
        for title, url, fetched, snips in body_hits:
            print(f"[cache] {title}\n  {url}\n  fetched: {fetched}")
            for s in snips:
                print(f"  > {s}")
    else:
        print("\n본문 매칭 없음 (캐시 기준 - 오래됐으면 `sync` 후 재시도)")


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
COMMENT_ALLOWLIST = os.path.join(CONF_DIR, "comment_allowlist")


def _load_allowlist(path: str) -> set:
    try:
        with open(path) as f:
            return {to_page_id(line) for line in f if line.strip()}
    except FileNotFoundError:
        return set()


def _ancestor_allowed(pid: str, kind: str, allow: set) -> bool:
    """대상 또는 그 조상이 allow 집합에 있으면 True. API 로 체인을 걸어 올라간다."""
    cur = pid
    for _ in range(30):  # 조상 체인 상한
        if cur in allow:
            return True
        try:
            if kind == "page":
                obj = call("GET", f"/pages/{cur}")
            elif kind == "database":
                obj = call("GET", f"/databases/{cur}")
            else:
                obj = call("GET", f"/blocks/{cur}")
        except ApiError:
            return False
        p = obj.get("parent", {})
        if p.get("type") == "page_id":
            cur, kind = to_page_id(p["page_id"]), "page"
        elif p.get("type") == "database_id":
            cur, kind = to_page_id(p["database_id"]), "database"
        elif p.get("type") == "block_id":
            cur, kind = to_page_id(p["block_id"]), "block"
        else:  # workspace 도달
            return False
    return False


def assert_writable(pid: str, kind: str = "page"):
    """대상(페이지/블록) 또는 그 조상이 write_allowlist 에 있어야 통과. 아니면 종료.

    회사 워크스페이스 실문서 오염 방지용 - 코드 레벨 가드라 스킬/모델 실수로도 못 뚫는다.
    """
    allow = _load_allowlist(WRITE_ALLOWLIST)
    if not allow:
        sys.exit("WRITE_DENIED: ~/.claude/notion/write_allowlist 비어 있음.\n"
                 "쓰기를 허용할 최상위 페이지 id 를 한 줄에 하나씩 등록해야 함.")
    if _ancestor_allowed(pid, kind, allow):
        return
    sys.exit(f"WRITE_DENIED: {pid} 는 로컬 쓰기 허용목록 밖.\n"
             "Notion 권한 문제 아님 - 토큰은 공유된 모든 페이지에 쓰기 가능하지만,\n"
             "실문서 보호를 위해 이 도구가 자체적으로 막는 것 (~/.claude/notion/write_allowlist).\n"
             "유저가 명시 승인했다면: notion_api.py allow '<page-url-or-id>' 로 열 수 있음.")


def assert_commentable(pid: str, kind: str = "block"):
    """댓글 게시 가드: write_allowlist ∪ comment_allowlist 하위면 통과.

    댓글은 본문을 파괴하진 않지만 API 로 삭제가 불가능하다(UI 수동 제거만 가능) -
    그래서 본문 쓰기보다 한 단계 가벼운 전용 허용목록을 합집합으로 둔다.
    """
    allow = _load_allowlist(WRITE_ALLOWLIST) | _load_allowlist(COMMENT_ALLOWLIST)
    if allow and _ancestor_allowed(pid, kind, allow):
        return
    sys.exit(f"COMMENT_DENIED: {pid} 는 댓글 허용목록 밖.\n"
             "본문 쓰기 없이 댓글만 허용하려면 (유저 명시 승인 후):\n"
             "  notion_api.py allow --comment '<page-url-or-id>'\n"
             "(write_allowlist 에 있는 페이지는 자동으로 댓글도 허용됨)")


def cmd_allow(argv):
    comment_only = "--comment" in argv
    target_file = COMMENT_ALLOWLIST if comment_only else WRITE_ALLOWLIST
    label = "댓글" if comment_only else "쓰기"
    pid = to_page_id([a for a in argv if not a.startswith("--")][0])
    os.makedirs(CONF_DIR, exist_ok=True)
    existing = _load_allowlist(target_file)
    if pid in existing:
        print(f"ALREADY: {pid} 이미 {label} 허용목록에 있음")
        return
    with open(target_file, "a") as f:
        f.write(pid + "\n")
    os.chmod(target_file, 0o600)
    print(f"ALLOWED: {pid} (+하위 전체) {label} 허용. 총 {len(existing) + 1}건")


# 순서 중요: ** 가 * 보다 먼저 매칭돼야 굵게/기울임이 안 섞인다
INLINE_RE = re.compile(r"(\*\*.+?\*\*|~~[^~]+~~|`[^`]+`|\[[^\]]+\]\([^)]+\)|\*[^*\n]+\*)")


def chunk_text(content: str, annotations: dict = None, link: str = None):
    """rich_text 항목 하나는 2000자 제한 - 초과분을 여러 객체로 쪼개 무손실 전송."""
    out = []
    for i in range(0, len(content), 2000) if content else [0]:
        t = {"type": "text", "text": {"content": content[i:i + 2000]}}
        if link:
            t["text"]["link"] = {"url": link}
        if annotations:
            t["annotations"] = annotations
        out.append(t)
    return out


def md_rich_text(text: str):
    """markdown 인라인(굵게/기울임/취소선/코드/링크) → rich_text 배열. 나머지는 평문."""
    out = []
    for part in INLINE_RE.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**") and len(part) > 4:
            out += chunk_text(part[2:-2], {"bold": True})
        elif part.startswith("~~") and part.endswith("~~") and len(part) > 4:
            out += chunk_text(part[2:-2], {"strikethrough": True})
        elif part.startswith("`") and part.endswith("`") and len(part) > 2:
            out += chunk_text(part[1:-1], {"code": True})
        elif part.startswith("[") and part.endswith(")"):
            m = re.match(r"\[([^\]]+)\]\(([^)]+)\)", part)
            out += chunk_text(m.group(1), link=m.group(2))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out += chunk_text(part[1:-1], {"italic": True})
        else:
            out += chunk_text(part)
    return out or [{"type": "text", "text": {"content": ""}}]


_EMOJI_RANGES = ((0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF),
                 (0x2190, 0x21FF), (0x2700, 0x27FF), (0xFE0F, 0xFE0F))


def _leading_emoji(s: str):
    """문자열이 이모지로 시작하면 (이모지, 나머지) - 콜아웃 왕복용 (`> 💡 텍스트`)."""
    if not s:
        return None
    o = ord(s[0])
    if not any(a <= o <= b for a, b in _EMOJI_RANGES):
        return None
    icon, _, rest = s.partition(" ")
    return icon, rest


def _parse_md_table(lines, i):
    """연속된 '| ... |' 줄 → table 블록. (블록, 다음 줄 index) 반환.

    table_row 는 생성 시 children 동봉이 필수라 여기서만 인라인 중첩을 쓴다.
    """
    rows, has_header = [], False
    while i < len(lines):
        s = lines[i].strip()
        if not (s.startswith("|") and s.endswith("|") and len(s) > 1):
            break
        tmp = s[1:-1].replace("\\|", "\x00")  # 이스케이프된 파이프 보호
        cells = [c.replace("\x00", "|").strip() for c in tmp.split("|")]
        if all(re.fullmatch(r":?-+:?", c) for c in cells):  # |---|---| 구분행
            has_header = bool(rows)
        else:
            rows.append(cells)
        i += 1
    width = max(len(r) for r in rows)
    trs = [{"type": "table_row", "table_row": {
        "cells": [md_rich_text(r[j]) if j < len(r) else md_rich_text("") for j in range(width)]}}
        for r in rows]
    return {"type": "table", "table": {
        "table_width": width, "has_column_header": has_header,
        "has_row_header": False, "children": trs}}, i


NESTABLE_TYPES = {"bulleted_list_item", "numbered_list_item", "to_do"}


def md_to_blocks(md: str):
    """markdown 서브셋 → Notion 블록 배열.

    지원: heading 1~4 ('#>' = 토글 헤딩), -/1. 리스트(들여쓰기 = 중첩), - [ ] 투두,
    > 인용, > 이모지 = 콜아웃, | 표 |, ``` 코드펜스, --- 구분선, 단독 URL = 북마크, 문단.
    리스트 중첩은 블록의 children 으로 들어가고 append 가 레벨 단위로 전송한다.
    """
    blocks, lines, i = [], md.splitlines(), 0
    stack = []  # [(들여쓰기 레벨, 블록)] - 리스트 중첩 부착용

    def attach(block, level, nestable):
        while stack and stack[-1][0] >= level:
            stack.pop()
        if stack:
            parent = stack[-1][1]
            parent[parent["type"]].setdefault("children", []).append(block)
        else:
            blocks.append(block)
        if nestable:
            stack.append((level, block))

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if not s:
            i += 1
            continue
        indent_level = (len(line) - len(line.lstrip())) // 2

        if s.startswith("```"):
            stack.clear()
            lang = s[3:].strip() or "plain text"
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # 닫는 펜스
            blocks.append({"type": "code", "code": {
                "language": lang, "rich_text": chunk_text("\n".join(code))}})
            continue
        if s.startswith("|") and s.endswith("|") and len(s) > 1:
            stack.clear()
            block, i = _parse_md_table(lines, i)
            blocks.append(block)
            continue

        m = re.match(r"(#{1,4})(>?)\s+(.*)", s)
        if m:
            stack.clear()
            lvl = len(m.group(1))
            h = {"rich_text": md_rich_text(m.group(3))}
            if m.group(2):  # '#>' 문법 = 토글 헤딩 (예: '####> 히스토리 확인용')
                h["is_toggleable"] = True
            blocks.append({"type": f"heading_{lvl}", f"heading_{lvl}": h})
        elif re.match(r"-\s+\[( |x)\]\s+", s):
            m = re.match(r"-\s+\[( |x)\]\s+(.*)", s)
            attach({"type": "to_do", "to_do": {
                "checked": m.group(1) == "x", "rich_text": md_rich_text(m.group(2))}},
                indent_level, True)
        elif s.startswith(("- ", "* ")):
            attach({"type": "bulleted_list_item",
                    "bulleted_list_item": {"rich_text": md_rich_text(s[2:])}},
                   indent_level, True)
        elif re.match(r"\d+\.\s+", s):
            attach({"type": "numbered_list_item",
                    "numbered_list_item": {"rich_text": md_rich_text(re.sub(r"^\d+\.\s+", "", s))}},
                   indent_level, True)
        elif s.startswith("> "):
            stack.clear()
            emoji = _leading_emoji(s[2:])
            if emoji:  # read 가 콜아웃을 '> 💡 텍스트' 로 내보낸 것의 역변환
                blocks.append({"type": "callout", "callout": {
                    "icon": {"type": "emoji", "emoji": emoji[0]},
                    "rich_text": md_rich_text(emoji[1])}})
            else:
                blocks.append({"type": "quote", "quote": {"rich_text": md_rich_text(s[2:])}})
        elif s in ("---", "***"):
            stack.clear()
            blocks.append({"type": "divider", "divider": {}})
        elif re.fullmatch(r"<https?://[^\s>]+>|https?://\S+", s):
            stack.clear()
            blocks.append({"type": "bookmark", "bookmark": {"url": s.strip("<>")}})
        else:
            stack.clear()
            blocks.append({"type": "paragraph",
                           "paragraph": {"rich_text": md_rich_text(s)}})
        i += 1
    return blocks


def append_blocks(pid: str, blocks, position=None):
    for i in range(0, len(blocks), 100):  # API 는 요청당 100블록 제한
        batch, nested = [], []
        for b in blocks[i:i + 100]:
            t = b.get("type")
            kids = None
            if t not in ("table", "column_list"):  # 표/컬럼은 생성 시 children 동봉이 필수
                kids = (b.get(t) or {}).pop("children", None)
            batch.append(b)
            nested.append(kids)
        body = {"children": batch}
        if position:
            body["position"] = position
        res = call("PATCH", f"/blocks/{pid}/children", body)
        results = res.get("results", [])
        # 리스트 중첩은 층별 append - 요청당 2단계 중첩 제한을 깊이 무관하게 우회
        for created, kids in zip(results, nested):
            if kids:
                append_blocks(created["id"], kids)
        if position and results:
            # 위치 지정 시 다음 배치는 방금 배치 꼬리 뒤에 - 호출자가 앵커 체이닝을 몰라도 순서 보존
            position = {"type": "after_block", "after_block": {"id": results[-1]["id"]}}


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
    blocks = md_to_blocks(read_md_arg(argv)) if ("--file" in argv or "--text" in argv) else []
    source_sel = argv[argv.index("--source") + 1] if "--source" in argv else None
    icon = ({"type": "emoji", "emoji": argv[argv.index("--icon") + 1]}
            if "--icon" in argv else None)
    ds = resolve_data_source(parent, source_sel)

    if ds:  # DB 가 목적지 → 행 생성 (--prop '이름=값' 으로 속성 지정)
        assert_writable(parent, kind="database")
        schema = call("GET", f"/data_sources/{ds}", version=DS_API_VERSION).get("properties", {})
        title_name = next((n for n, p in schema.items() if p.get("type") == "title"), "title")
        properties = {title_name: {"title": [{"type": "text", "text": {"content": title}}]}}
        for s in [argv[i + 1] for i, a in enumerate(argv) if a == "--prop"]:
            if "=" not in s:
                sys.exit(f"BAD_PROP: {s!r} - '이름=값' 형식 필요")
            name, value = s.split("=", 1)
            name = name.strip()
            if name not in schema:
                sys.exit(f"NO_PROP: {name!r} 속성 없음. 있는 것: {', '.join(schema)}")
            ptype = schema[name].get("type")
            properties[name] = {ptype: build_prop_payload(ptype, value)}
        body = {"parent": {"type": "data_source_id", "data_source_id": ds},
                "properties": properties}
        if icon:
            body["icon"] = icon
        page = call("POST", "/pages", body, version=DS_API_VERSION)
        label = "CREATED(row)"
    else:
        assert_writable(parent)
        body = {"parent": {"page_id": parent},
                "properties": {"title": {"title": [{"type": "text", "text": {"content": title}}]}}}
        if icon:
            body["icon"] = icon
        page = call("POST", "/pages", body)
        label = "CREATED"

    # 본문은 생성 후 append - 중첩 리스트의 층별 전송 로직을 한 경로로 통일
    if blocks:
        append_blocks(page["id"], blocks)
    print(f"{label}: {title}")
    print(f"URL: {page.get('url', '')}")
    print(f"id: {page['id']}")


DB_PROP_TYPES = {"title", "rich_text", "number", "checkbox", "date", "url", "email",
                 "phone_number", "select", "multi_select", "people", "files"}


def parse_schema_prop(spec: str):
    """'이름:타입[:옵션1,옵션2]' → (이름, 스키마 조각). 옵션은 select 계열 전용."""
    parts = spec.split(":", 2)
    if len(parts) < 2 or not parts[0].strip() or not parts[1].strip():
        sys.exit(f"BAD_SCHEMA: {spec!r} - '이름:타입[:옵션들]' 형식 필요")
    name, ptype = parts[0].strip(), parts[1].strip()
    if ptype == "status":
        sys.exit("SCHEMA_UNSUPPORTED: status 속성은 API 로 생성 불가 (Notion UI 전용) - select 로 대체 권장")
    if ptype not in DB_PROP_TYPES:
        sys.exit(f"SCHEMA_UNSUPPORTED: {ptype!r} 타입 미지원. 가능: {', '.join(sorted(DB_PROP_TYPES))}")
    if ptype in ("select", "multi_select"):
        options = [{"name": o.strip()} for o in (parts[2].split(",") if len(parts) > 2 else []) if o.strip()]
        return name, {ptype: {"options": options}}
    return name, {ptype: {}}


def cmd_db_create(argv):
    parent = to_page_id(argv[0])
    title = argv[1]
    assert_writable(parent)
    if "--json" in argv:
        with open(argv[argv.index("--json") + 1], encoding="utf-8") as f:
            props = json.load(f)
    else:
        props = {}
        for spec in [argv[i + 1] for i, a in enumerate(argv) if a == "--prop"]:
            name, piece = parse_schema_prop(spec)
            props[name] = piece
    if not any("title" in p for p in props.values()):
        props["이름"] = {"title": {}}  # title 속성은 DB 필수 - 미지정 시 기본 생성
    body = {"parent": {"type": "page_id", "page_id": parent},
            "title": [{"type": "text", "text": {"content": title}}],
            "initial_data_source": {"properties": props}}
    if "--icon" in argv:
        body["icon"] = {"type": "emoji", "emoji": argv[argv.index("--icon") + 1]}
    db = call("POST", "/databases", body, version=DS_API_VERSION)
    ds = (db.get("data_sources") or [{}])[0]
    print(f"CREATED_DB: {title}")
    print(f"URL: {db.get('url', '')}")
    print(f"db id: {db['id']}")
    print(f"data_source id: {ds.get('id')}")


def cmd_db_prop(argv):
    dbid = to_page_id(argv[0])
    source_sel = argv[argv.index("--source") + 1] if "--source" in argv else None
    ds = resolve_data_source(dbid, source_sel)
    if not ds:
        sys.exit(f"NOT_DB: {dbid} 는 데이터베이스가 아님")

    payload = {}
    for spec in [argv[i + 1] for i, a in enumerate(argv) if a == "--add"]:
        name, piece = parse_schema_prop(spec)
        payload[name] = piece
    for spec in [argv[i + 1] for i, a in enumerate(argv) if a == "--rename"]:
        if "=" not in spec:
            sys.exit(f"BAD_RENAME: {spec!r} - '기존이름=새이름' 형식 필요")
        old, new = spec.split("=", 1)
        payload[old.strip()] = {"name": new.strip()}
    for i, a in enumerate(argv):
        if a == "--remove":
            payload[argv[i + 1].strip()] = None

    if not payload:  # 조회 모드: 스키마 출력
        schema = call("GET", f"/data_sources/{ds}", version=DS_API_VERSION).get("properties", {})
        for n, p in schema.items():
            extra = ""
            if p.get("type") in ("select", "multi_select", "status"):
                opts = (p.get(p["type"]) or {}).get("options", [])
                extra = " (" + ", ".join(o.get("name", "") for o in opts) + ")"
            print(f"{n} [{p.get('type')}]{extra}")
        return

    assert_writable(dbid, kind="database")  # 스키마 변경은 쓰기
    res = call("PATCH", f"/data_sources/{ds}", {"properties": payload}, version=DS_API_VERSION)
    kept = ", ".join(f"{k}({v.get('type')})" for k, v in (res.get("properties") or {}).items())
    print(f"DB_PROP_OK: {kept}")


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


# ---------- SQL 질의 (데이터 소스 → 로컬 SQLite, 조인/집계 가능) ----------

def _sql_value(p: dict):
    """속성 값 → SQLite 셀. 빈 값은 NULL, 숫자/체크박스는 숫자형, 날짜는 시작일."""
    t = p.get("type")
    v = p.get(t)
    if v in (None, [], ""):
        return None
    if t == "number":
        return v
    if t == "checkbox":
        return 1 if v else 0
    if t == "date":
        return v.get("start")
    s = prop_value_str(p)
    return None if s == "(비어있음)" else s


def cmd_sql(argv):
    """DB 행들을 메모리 SQLite 로 적재 후 읽기 전용 쿼리 실행. 조인/집계/서브쿼리 전부 가능."""
    if not argv or "--db" not in argv:
        sys.exit("USAGE: sql '<SELECT ...>' --db <url|id> [--db ...] [--source S] [--limit N]\n"
                 "테이블명: DB 1개면 t, 여러 개면 순서대로 t1, t2, ... 컬럼 = 속성명 + id, url")
    query = argv[0]
    dbs = [argv[i + 1] for i, a in enumerate(argv) if a == "--db"]
    per_limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 1000
    source_sel = argv[argv.index("--source") + 1] if "--source" in argv else None
    import sqlite3
    conn = sqlite3.connect(":memory:")

    for idx, ref in enumerate(dbs, 1):
        dbid = to_page_id(ref)
        ds = resolve_data_source(dbid, source_sel)
        if not ds:
            sys.exit(f"NOT_DB: {ref} 는 데이터베이스가 아님")
        schema = call("GET", f"/data_sources/{ds}", version=DS_API_VERSION).get("properties", {})
        cols = list(schema.keys())
        tname = "t" if len(dbs) == 1 else f"t{idx}"
        col_defs = ", ".join([f'"{c}"' for c in cols] + ['"id"', '"url"'])
        conn.execute(f'CREATE TABLE "{tname}" ({col_defs})')
        rows, more = query_data_source(ds, {}, per_limit)
        for r in rows:
            props = r.get("properties", {})
            vals = [_sql_value(props[c]) if c in props else None for c in cols] \
                + [r["id"], r.get("url", "")]
            conn.execute(f'INSERT INTO "{tname}" VALUES ({",".join("?" * len(vals))})', vals)
        note = f" (상한 도달 - --limit 로 확장)" if more else ""
        print(f"{tname}: {len(rows)}행{note}, 컬럼: {', '.join(cols)}, id, url", file=sys.stderr)

    conn.execute("PRAGMA query_only = ON")  # 로컬 사본 읽기 전용 - 쿼리로는 아무것도 못 바꿈
    try:
        cur = conn.execute(query)
    except sqlite3.Error as e:
        sys.exit(f"SQL_ERROR: {e}")
    out_cols = [d[0] for d in cur.description or []]
    results = cur.fetchall()
    if not out_cols:
        print("(결과 컬럼 없음)")
        return

    def esc(x):
        return ("" if x is None else str(x)).replace("|", "\\|").replace("\n", " ")

    print("| " + " | ".join(out_cols) + " |")
    print("|" + "---|" * len(out_cols))
    for row in results:
        print("| " + " | ".join(esc(x) for x in row) + " |")
    print(f"\n({len(results)}행)")


# ---------- 문자열 치환 편집 (old_str → new_str, Edit 도구 대응) ----------

def _walk_text_blocks(root: str, state: dict, out: list):
    """텍스트 계열 블록 수집 (하위 페이지/DB 안으로는 안 내려감)."""
    for b in get_children(root, state):
        t = b.get("type")
        if t in RICH_TEXT_TYPES or t == "code":
            out.append(b)
        if b.get("has_children") and t not in ("child_page", "child_database"):
            _walk_text_blocks(b["id"], state, out)


def cmd_edit_str(argv):
    pid = to_page_id(argv[0])
    if "--old" not in argv or "--new" not in argv:
        sys.exit("USAGE: edit-str <url|id> --old '<기존>' --new '<새>' [--all]")
    old = argv[argv.index("--old") + 1]
    new = argv[argv.index("--new") + 1]
    assert_writable(pid, kind="block")

    state = {"fetched": 0, "truncated": False}
    blocks = []
    _walk_text_blocks(pid, state, blocks)
    hits = []
    for b in blocks:
        text = rt((b.get(b["type"]) or {}).get("rich_text"))
        if old in text:
            hits.append((b, text))
    if not hits:
        sys.exit("NOT_FOUND: --old 문자열과 매칭되는 블록 없음.\n"
                 "매칭 대상은 read 가 출력하는 markdown 형태 그대로이며, 문자열이 블록 하나\n"
                 "안에 있어야 한다 (여러 블록에 걸친 치환은 불가 - Notion 구조 제약).")
    if len(hits) > 1 and "--all" not in argv:
        listing = "\n".join(f"  ⟨{b['type']} {b['id']}⟩ {txt[:60]}" for b, txt in hits)
        sys.exit(f"AMBIGUOUS: {len(hits)}개 블록 매칭 - --all 로 전부 치환하거나 "
                 f"edit <block-id> 로 특정:\n{listing}")
    for b, text in hits:
        t = b["type"]
        newtext = text.replace(old, new)
        payload = ({"code": {"rich_text": chunk_text(newtext)}} if t == "code"
                   else {t: {"rich_text": md_rich_text(newtext)}})
        call("PATCH", f"/blocks/{b['id']}", payload)
        print(f"EDITED: {t} ⟨{b['id']}⟩")
    print(f"OK: {len(hits)}개 블록 치환")


# ---------- 댓글 (읽기 자유, 게시는 write ∪ comment 허용목록) ----------

def fetch_comments(bid: str):
    """블록/페이지의 미해결 댓글 전부 (resolved 스레드는 공개 API 미노출 - 구조 제약)."""
    results, cursor = [], None
    while True:
        q = f"/comments?block_id={bid}&page_size=100"
        if cursor:
            q += f"&start_cursor={urllib.parse.quote(cursor)}"
        data = call("GET", q, version=DS_API_VERSION)  # display_name(작성자) 동봉되는 신버전
        results += data.get("results", [])
        if not data.get("has_more"):
            return results
        cursor = data.get("next_cursor")


def _comment_user_name(uid: str, cache={}) -> str:
    if uid not in cache:
        try:
            cache[uid] = call("GET", f"/users/{uid}").get("name") or uid[:8]
        except ApiError:
            cache[uid] = uid[:8]
    return cache[uid]


def render_comments(comments):
    """discussion 단위로 묶어 시간순 출력. discussion id 는 --reply 대상."""
    by_disc = {}
    for c in comments:
        by_disc.setdefault(c.get("discussion_id"), {})[c["id"]] = c  # id 로 dedupe
    for did, cs in by_disc.items():
        anchor = next(iter(cs.values())).get("parent", {})
        where = anchor.get("block_id") or anchor.get("page_id") or "?"
        kind = "block" if anchor.get("type") == "block_id" else "page"
        print(f"[discussion {did}] ({kind} {where})")
        for c in sorted(cs.values(), key=lambda x: x.get("created_time", "")):
            name = (c.get("display_name") or {}).get("resolved_name")
            if not name:  # 구응답 폴백 - 유저 개별 조회
                name = _comment_user_name((c.get("created_by") or {}).get("id", ""))
            t = (c.get("created_time") or "")[:16].replace("T", " ")
            print(f"  {t} {name}: {rt(c.get('rich_text'))}")


def collect_block_ids(root: str, state: dict):
    """페이지 전체 블록 id 수집 (하위 페이지/DB 안까지는 안 내려감)."""
    out = []
    for b in get_children(root, state):
        out.append(b["id"])
        if b.get("has_children") and b.get("type") not in ("child_page", "child_database"):
            out += collect_block_ids(b["id"], state)
    return out


def cmd_comments(argv):
    pid = to_page_id(argv[0])
    comments = fetch_comments(pid)
    if "--all" in argv:  # 인라인(블록 앵커) 댓글까지: 블록 수만큼 API 호출 - 큰 페이지는 느림
        state = {"fetched": 0, "truncated": False}
        for bid in collect_block_ids(pid, state):
            comments += fetch_comments(bid)
    if not comments:
        hint = "" if "--all" in argv else " (인라인 블록 댓글까지 보려면 --all)"
        print(f"NO_COMMENTS: 미해결 댓글 없음{hint} - resolved 스레드는 API 에 안 나옴")
        return
    render_comments(comments)


def cmd_comment(argv):
    target = to_page_id(argv[0])
    if "--text" not in argv:
        sys.exit("NO_CONTENT: --text '<내용>' 필요.")
    text = argv[argv.index("--text") + 1]
    assert_commentable(target, kind="block")
    if "--reply" in argv:  # target 은 가드용(스레드가 있는 페이지), API 는 discussion 에 단다
        body = {"discussion_id": argv[argv.index("--reply") + 1],
                "rich_text": md_rich_text(text)}
    else:
        is_page = True
        try:
            call("GET", f"/pages/{target}")
        except ApiError:
            is_page = False
        parent = {"page_id": target} if is_page else {"block_id": target}
        body = {"parent": parent, "rich_text": md_rich_text(text)}
    res = call("POST", "/comments", body, version=DS_API_VERSION)
    print(f"COMMENTED: discussion {res.get('discussion_id')}")
    print("주의: API 로는 댓글 삭제 불가 - 잘못 달았으면 Notion UI 에서 수동 제거해야 함.")


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


def _rechunk_rich_text(arr):
    """GET 응답은 인접 text 를 서버가 병합해 2000자 초과 항목을 줄 수 있다 - 생성용 재분할."""
    out = []
    for t in arr or []:
        content = (t.get("text") or {}).get("content") if t.get("type") == "text" else None
        if content is not None and len(content) > 2000:
            link = (t.get("text") or {}).get("link")
            for i in range(0, len(content), 2000):
                nt = {"type": "text", "text": {"content": content[i:i + 2000]}}
                if link:
                    nt["text"]["link"] = link
                if t.get("annotations"):
                    nt["annotations"] = t["annotations"]
                out.append(nt)
        else:
            out.append(t)
    return out


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
    for k in ("rich_text", "caption"):
        if d.get(k):
            d[k] = _rechunk_rich_text(d[k])
    if d.get("cells"):
        d["cells"] = [_rechunk_rich_text(c) for c in d["cells"]]
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


def _inline_table_rows(src_id: str, payload: dict, state: dict) -> dict:
    """table 은 생성 시 table_row children 동봉이 필수 - 원본 행을 인라인으로 채운다."""
    fetch_state = {"fetched": 0, "truncated": False}
    rows = []
    for r in get_children(src_id, fetch_state):
        rp = block_to_payload(r, state)
        if rp:
            rows.append(rp)
            state["copied"] += 1
    payload["table"]["children"] = rows
    return payload


def copy_block_tree(src_id: str, dest_id: str, state: dict, position=None):
    """src 블록(하위 트리 포함)을 dest 의 children 으로 복제. 생성된 최상위 블록 id 반환."""
    src = call("GET", f"/blocks/{src_id}")
    payload = block_to_payload(src, state)
    if payload is None:
        sys.exit(f"MOVE_UNSUPPORTED: {src.get('type')} 블록은 복제 불가 "
                 f"(child_page/synced_block 등은 Notion UI 에서만 이동 가능).")
    if payload.get("type") == "table":
        payload = _inline_table_rows(src_id, payload, state)
    body = {"children": [payload]}
    if position:
        body["position"] = position
    res = call("PATCH", f"/blocks/{dest_id}/children", body)
    new_id = res["results"][0]["id"]
    state["copied"] += 1
    if src.get("has_children") and src.get("type") != "table":  # 표 행은 위에서 소비함
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
        if p.get("type") == "table":
            p = _inline_table_rows(k["id"], p, state)
        payloads.append(p)
        sources.append(k)
    for i in range(0, len(payloads), 100):
        res = call("PATCH", f"/blocks/{dest_parent}/children",
                   {"children": payloads[i:i + 100]})
        for created, src in zip(res["results"], sources[i:i + 100]):
            state["copied"] += 1
            if src.get("has_children") and src.get("type") != "table":
                _copy_children_into(src["id"], created["id"], state)


def resolve_data_source(dest: str, source_sel: str = None):
    """dest 가 DB 면 data_source id 반환, 아니면 None.

    multi-source DB(한 DB 에 데이터 소스 여러 개)는 --source <이름|id> 로 골라야 하며,
    미지정 시 목록을 보여주고 종료한다. write/move/db-prop 이 공유하는 해석기.
    """
    try:
        db = call("GET", f"/databases/{dest}", version=DS_API_VERSION)
    except ApiError:
        return None  # DB 아님 → 페이지 취급
    sources = db.get("data_sources", [])
    if not sources:
        return None
    if source_sel:
        for s in sources:
            if source_sel in (s.get("id"), s.get("name")):
                return s["id"]
        names = ", ".join(f"{s.get('name')}={s.get('id')}" for s in sources)
        sys.exit(f"NO_SOURCE: --source {source_sel!r} 매칭 실패. 있는 것: {names}")
    if len(sources) > 1:
        names = ", ".join(f"{s.get('name')}={s.get('id')}" for s in sources)
        sys.exit(f"MULTI_SOURCE_DB: 데이터 소스가 여러 개 - --source <이름|id> 로 지정 필요: {names}")
    return sources[0]["id"]


def resolve_move_parent(dest: str) -> dict:
    """이동 목적지 → parent 객체. DB 면 data_source_id, 아니면 page_id."""
    ds = resolve_data_source(dest)
    if ds:
        return {"type": "data_source_id", "data_source_id": ds}
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
            moved = call("POST", f"/pages/{src}/move", {"parent": parent}, version=DS_API_VERSION)
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


# ---------- 페이지 수명주기 (복제 / archive / 복구) ----------

READONLY_PROP_TYPES = {"formula", "rollup", "created_time", "created_by",
                       "last_edited_time", "last_edited_by", "unique_id"}


def cmd_duplicate(argv):
    src = to_page_id(argv[0])
    page = call("GET", f"/pages/{src}")
    new_title = (argv[argv.index("--title") + 1] if "--title" in argv
                 else page_title(page) + " (copy)")

    if "--to" in argv:
        guard_id = to_page_id(argv[argv.index("--to") + 1])
        parent_obj = resolve_move_parent(guard_id)
    else:  # 기본: 원본과 같은 부모 (DB 행이면 같은 DB)
        p = page.get("parent", {})
        if p.get("type") == "page_id":
            guard_id = to_page_id(p["page_id"])
            parent_obj = {"type": "page_id", "page_id": guard_id}
        elif p.get("type") in ("database_id", "data_source_id"):
            guard_id = to_page_id(p.get("database_id") or p.get("data_source_id"))
            parent_obj = resolve_move_parent(guard_id)
        else:
            sys.exit("DUP_NEED_DEST: workspace 루트 페이지는 --to <목적지> 지정 필요")
    # 가드는 페이지/DB id 로 탐색 (data_source id 는 조상 체인을 못 걸어 올라간다)
    assert_writable(guard_id, kind="block")

    props = {}
    for name, prop in page.get("properties", {}).items():
        t = prop.get("type")
        if t in READONLY_PROP_TYPES:
            continue
        if t == "title":
            props[name] = {"title": [{"type": "text", "text": {"content": new_title}}]}
        elif prop.get(t) not in (None, [], ""):
            props[name] = {t: prop[t]}
    body = {"parent": parent_obj, "properties": props}
    for deco in ("icon", "cover"):  # 이모지/외부 URL 만 복사 가능 (내부 파일은 서명 URL 이라 불가)
        d = page.get(deco)
        if isinstance(d, dict) and d.get("type") in ("emoji", "external"):
            body[deco] = d
    new = call("POST", "/pages", body, version=DS_API_VERSION)

    state = {"copied": 0, "skipped": []}
    try:
        _copy_children_into(src, new["id"], state)
    except BaseException:  # 본문 복제 실패 시 껍데기 페이지 잔존 방지 - 자동 롤백
        try:
            call("PATCH", f"/pages/{new['id']}", {"archived": True})
            print(f"ROLLBACK: 복제 실패 - 생성했던 페이지 archive ⟨{new['id']}⟩", file=sys.stderr)
        except ApiError:
            print(f"ROLLBACK_FAIL: 실패 잔존물 수동 정리 필요 ⟨{new['id']}⟩", file=sys.stderr)
        raise
    note = f", 스킵 {len(state['skipped'])}개({','.join(set(state['skipped']))})" if state["skipped"] else ""
    print(f"DUPLICATED: {new_title} - {state['copied']}블록 복제{note}")
    print(f"URL: {new.get('url', '')}")
    print(f"id: {new['id']}")


def cmd_archive(argv):
    pid = to_page_id(argv[0])
    assert_writable(pid, kind="block")
    try:
        obj = call("PATCH", f"/pages/{pid}", {"archived": True})
        what = f"페이지 \"{page_title(obj)}\""
    except ApiError:
        obj = call("PATCH", f"/blocks/{pid}", {"archived": True})
        what = f"{obj.get('type')} 블록"
    print(f"ARCHIVED: {what} ⟨{pid}⟩ - Notion 휴지통에서 복구 가능 (restore 명령)")


def cmd_restore(argv):
    pid = to_page_id(argv[0])
    assert_writable(pid, kind="block")
    try:
        obj = call("PATCH", f"/pages/{pid}", {"archived": False})
        what = f"페이지 \"{page_title(obj)}\""
    except ApiError:
        obj = call("PATCH", f"/blocks/{pid}", {"archived": False})
        what = f"{obj.get('type')} 블록"
    print(f"RESTORED: {what} ⟨{pid}⟩")


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
        payload = {"code": {"rich_text": chunk_text(new)}}
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


def cmd_sync(limit: int, full: bool = False):
    n, skipped, cursor = 0, 0, None
    while n < limit:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        data = call("POST", "/search", body)
        for pg in data.get("results", []):
            if n >= limit:
                break
            pid = pg["id"]
            is_db = pg.get("object") == "database"
            edited = pg.get("last_edited_time", "")
            # 증분: 마지막 수정 시각이 캐시와 같으면 본문 재다운로드 생략
            if not full and edited and cached_edited(to_page_id(pid)) == edited:
                n += 1
                skipped += 1
                continue
            try:
                title, url, md, edited = (database_to_markdown(pid) if is_db
                                          else page_to_markdown(pid))
                write_cache(pid, title, url, md, edited)
                n += 1
                print(f"[{n}/{limit}] {'🗃️ ' if is_db else ''}{title}", flush=True)
            except ApiError as e:
                print(f"  skip {pid}: HTTP {e.code}", flush=True)
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    note = f" (미변경 {skipped}건 생략 - 전체 갱신은 --full)" if skipped else ""
    print(f"SYNCED: {n} pages → {CACHE_DIR}{note}")


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
            cmd_read(sys.argv[2:])
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
        elif cmd == "db-create":
            cmd_db_create(sys.argv[2:])
        elif cmd == "db-prop":
            cmd_db_prop(sys.argv[2:])
        elif cmd == "sql":
            cmd_sql(sys.argv[2:])
        elif cmd == "edit-str":
            cmd_edit_str(sys.argv[2:])
        elif cmd == "duplicate":
            cmd_duplicate(sys.argv[2:])
        elif cmd == "archive":
            cmd_archive(sys.argv[2:])
        elif cmd == "restore":
            cmd_restore(sys.argv[2:])
        elif cmd == "comments":
            cmd_comments(sys.argv[2:])
        elif cmd == "comment":
            cmd_comment(sys.argv[2:])
        elif cmd == "users":
            cmd_users()
        elif cmd == "allow":
            cmd_allow(sys.argv[2:])
        elif cmd == "upload":
            cmd_upload(sys.argv[2:])
        elif cmd == "move":
            cmd_move(sys.argv[2:])
        elif cmd == "sync":
            nums = [a for a in sys.argv[2:] if a.isdigit()]
            cmd_sync(int(nums[0]) if nums else 200, "--full" in sys.argv)
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
