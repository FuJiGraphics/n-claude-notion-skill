# n-claude-notion-skill

Claude Code 에서 Notion 을 파일시스템처럼 다루는 스킬 모음.
공식 REST API 기반이라 MCP 커넥터 없이 동작하고, 대화형 세션-서브에이전트-cron 어디서든 같은 방식으로 돈다.

## 설계: Claude 기본 도구와 1:1 대응

| Claude 도구 | 스킬 | 하는 일 |
|---|---|---|
| Read | `/notion-read` | 페이지/DB → markdown + 임베디드 이미지 다운로드, 비디오 프레임 샘플링까지 읽음 |
| Grep | `/notion-grep` | 로컬 캐시 full-text 검색 + API 제목 검색 병합 |
| Glob/ls | `/notion-ls` | 워크스페이스 전체 트리 또는 특정 페이지 하위 목록 |
| Write | `/notion-write` | markdown → 새 페이지 생성, 기존 페이지에 블록 append (allowlist 가드) |
| Edit | `/notion-edit` | `read --ids` 로 블록 특정 → 텍스트 교체 / archive (allowlist 가드) |
| (인증) | `/notion-login` `/notion-logout` | OAuth 또는 integration 토큰 등록 / 해제 |

쓰기 계열은 `~/.claude/notion/write_allowlist` 에 등록된 페이지 **하위에서만** 동작한다 -
조상 체인을 API 로 검증하는 코드 레벨 가드라 실문서를 실수로 건드릴 수 없다.

## 설치

```bash
git clone https://github.com/FuJiGraphics/n-claude-notion-skill.git
cd n-claude-notion-skill
./install.sh   # ~/.claude/skills 에 심볼릭 링크
```

이후 Claude Code 에서 `/notion-login` 실행.

## 인증

우선순위: `NOTION_TOKEN` 환경변수 → `~/.claude/notion/auth.json` → 레거시 `~/.claude/notion/token`.

- **OAuth (팀 배포용)**: 관리자가 Notion public integration 을 1회 등록
  (redirect URI `http://localhost:8917/callback`) 하고 client_id/secret 을
  `~/.claude/notion/oauth_app.json` 으로 배포. `/notion-login` 이 브라우저를 열어
  Notion 페이지 피커로 공유 범위까지 한 번에 처리.
- **Internal 토큰 (개인/즉시)**: https://www.notion.so/my-integrations 에서 internal
  integration 생성 후 `login --token <ntn_...>`. 읽을 페이지는 페이지 ⋯ 메뉴 →
  Connections 에서 integration 연결 (최상위 페이지에 걸면 하위 전체 포함).

비밀 키는 전부 `~/.claude/notion/` (chmod 600) 로컬 저장 - 레포에는 절대 안 들어감.

## 구조

```
skills/
├── notion-login/    SKILL.md
├── notion-logout/   SKILL.md
├── notion-read/     SKILL.md
│   └── scripts/
│       ├── notion_api.py         # 공용 엔진 (login/ls/read/search/sync/write/append/edit/delete/logout CLI)
│       └── fetch_notion_media.py # 이미지 다운로드 + 비디오 프레임/contact sheet
├── notion-grep/     SKILL.md
├── notion-ls/       SKILL.md
├── notion-write/    SKILL.md
└── notion-edit/     SKILL.md

```

엔진 CLI 는 스킬 밖에서도 그대로 사용 가능:

```bash
python3 skills/notion-read/scripts/notion_api.py ls
python3 skills/notion-read/scripts/notion_api.py read <url|id>
python3 skills/notion-read/scripts/notion_api.py search "<제목 키워드>"
python3 skills/notion-read/scripts/notion_api.py sync 200   # grep 용 로컬 미러
```

## 개발 규칙

- **새 서브명령 추가/변경 시 같은 커밋에서** notion_api.py 상단 docstring 의 명령표와
  해당 SKILL.md 를 함께 갱신한다. 도구가 자기 능력을 정확히 광고하지 않으면
  그 위에 세운 판단이 통째로 틀린다 (실사례: move 미기재 → "이미지 이동 불가" 오보고).
- GET 응답을 생성 API 입력으로 재사용하지 않는다. 응답 스키마 ≠ 생성 스키마 -
  반드시 `CREATE_FIELDS` 화이트리스트를 거친다.
- 파괴 동작(archive/delete)은 항상 사본/결과 검증 후에만 실행한다.

## 알아둘 제약

- 공식 `/v1/search` 는 **제목만** 검색한다 (API 제약). 본문 검색은 `sync` 로 만든
  로컬 캐시(`~/.claude/notion/cache/`) 위에서 ripgrep 으로 한다.
- 페이지 첨부파일의 서명 URL 은 약 1시간 만료 - fetch 직후 다운로드해야 한다.
- 한 페이지당 블록 3000개 상한 (초과 시 TRUNCATED 표시).
- rate limit 약 3req/s 는 스크립트가 Retry-After 로 자체 처리.
