#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  복구온 코드스페이스 자동 복구 스크립트 (멱등 — 몇 번 실행해도 안전)
#  작성: 2026-10-13 · 올림포스 어벤저스 아이언하트 (서버 연동 담당)
#
#  하는 일:
#   1) 의존성 확인 (리빌드로 꾸러미가 사라져도 자가 복구)
#   2) gunicorn 서버가 죽어 있으면 기동   (~/bin 경로 자동 탐색)
#   3) cloudflared 예비 터널이 죽어 있으면 기동
#
#  사용:
#   - 코드스페이스 안에서:  bash deploy/codespace_start.sh
#   - 토니 PC에서(자동):    gh codespace ssh -c <이름> -- "bash /workspaces/bokguon/deploy/codespace_start.sh"
#     (꺼져 있으면 SSH가 코드스페이스까지 자동으로 켜준다)
# ══════════════════════════════════════════════════════════════
set -u
cd /workspaces/bokguon || exit 1
export PATH="$HOME/.local/bin:$PATH"

# 1) 의존성 보장 — 있으면 즉시 통과
if ! python3 -c "import flask, cryptography, gunicorn" >/dev/null 2>&1; then
  python3 -m pip install --user -q -r requirements.txt gunicorn >> logs/gunicorn_out.log 2>&1 || true
fi

# gunicorn 실행 파일 탐색 (파이썬 버전이 바뀌어도 견디게)
GUNICORN="$(command -v gunicorn 2>/dev/null || true)"
if [ -z "$GUNICORN" ]; then
  GUNICORN="$(ls -1 "$HOME"/.local/lib/python*/site-packages/bin/gunicorn 2>/dev/null | head -1)"
fi
if [ -z "$GUNICORN" ]; then
  GUNICORN="$(python3 -m site --user-base 2>/dev/null)/bin/gunicorn"
fi

# 2) gunicorn — 이미 돌고 있으면 건드리지 않는다
if ! pgrep -f 'gunicorn -c gunicorn_conf.py' >/dev/null 2>&1; then
  if [ -x "$GUNICORN" ]; then
    nohup "$GUNICORN" -c gunicorn_conf.py wsgi:application >> logs/gunicorn_out.log 2>&1 &
    sleep 2
  fi
fi

# 3) cloudflared 예비 터널 — 링크가 필요 없으면 그대로 둬도 무해
if ! pgrep -f 'cloudflared tunnel --url http://127.0.0.1:8771' >/dev/null 2>&1; then
  if [ -x "$HOME/bin/cloudflared" ]; then
    ( cd "$HOME/bin" && nohup ./cloudflared tunnel --url http://127.0.0.1:8771 --no-autoupdate >> "$HOME/cloudflared.log" 2>&1 & )
  fi
fi

sleep 1
UP="$(pgrep -fc 'gunicorn -c gunicorn_conf.py' 2>/dev/null || echo 0)"
LISTEN="$(ss -tln 2>/dev/null | grep -c ':8771' || echo 0)"
echo "OK $(date -u +%FT%TZ) gunicorn_procs=${UP} listen8771=${LISTEN}"
