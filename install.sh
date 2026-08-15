#!/usr/bin/env bash
# ~/.claude/skills 에 스킬 전체를 심볼릭 링크로 설치한다.
# 링크 방식이라 레포에서 수정하면 즉시 반영된다. 재실행 안전(idempotent).
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/skills"
mkdir -p "$DEST"

for s in notion-login notion-logout notion-read notion-grep notion-ls notion-write notion-edit notion-comment; do
  rm -rf "$DEST/$s"
  ln -sfn "$REPO/skills/$s" "$DEST/$s"
  echo "linked: $DEST/$s -> $REPO/skills/$s"
done

echo "done. 다음 단계: Claude Code 에서 /notion-login 실행해 로그인."
