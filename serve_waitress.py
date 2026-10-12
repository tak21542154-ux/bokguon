# -*- coding: utf-8 -*-
"""Windows 운영 구동 (waitress WSGI).

실행:  python serve_waitress.py
설치:  pip install waitress
"""
import io
import os
import sys

#  ⚠ 윈도 기본 콘솔은 cp949 라 '⚠' 같은 문자를 print 하면(아래 BOKGUON_ENV!=prod
#    경고줄) UnicodeEncodeError 로 죽는다(실측: U+26A0 은 cp949 인코딩 불가 — round518이
#    check_orphan_chars.py 에서 고친 것과 같은 클래스, em dash 대신 경고기호가
#    범인이라는 점만 다르다). 이 파일은 실서비스 진입점이라 감시자(외부접속_
#    상시가동.ps1)가 stdout 을 파일로 리다이렉트해 재시작하는데, BOKGUON_ENV 를
#    prod 로 명시하지 않은 채(예: 아직 안 정한 배포) 돌리면 배너조차 못 찍고
#    죽어 서버가 아예 안 뜬다. 형제 점검 도구(check_tx_paths.py 등)가 이미
#    쓰는 방어를 그대로 옮긴다(round519).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

#  ⚠⚠ [라운드273] envload.py 자신의 문서는 "app.py/wsgi.py/serve_waitress.py/
#    manage.py 가 공유한다"고 명시하는데, 실제로는 이 파일이 직접 부르지
#    않고 아래 `from wsgi import application`이 wsgi.py 안의 같은 호출을
#    먼저 실행시키는 **import 순서의 우연**에 기대고 있었다(실측 확인:
#    지금은 정상 동작하지만, 이 두 줄 순서가 나중에 바뀌면 조용히 깨져
#    .env 값 없이 기본값으로 뜬다). 명시적으로 한 번 더 부른다 —
#    load_dotenv() 는 setdefault 라 두 번 불러도 무해하다.
from envload import load_dotenv as _load_dotenv
_load_dotenv()

from wsgi import application

HOST = os.environ.get("BOKGUON_HOST", "0.0.0.0")
PORT = int(os.environ.get("BOKGUON_PORT", "8771"))
THREADS = int(os.environ.get("BOKGUON_THREADS", "8"))
#  ⚠⚠ [라운드451] waitress 자신의 기본 max_request_body_size(1GB)를 지금까지
#    한 번도 안 줄였다 — app.py 의 MAX_CONTENT_LENGTH(BOKGUON_MAX_UPLOAD_MB,
#    기본 260MB)는 Flask 계층의 검사라 waitress 가 본문을 **전부 받은 뒤**에야
#    발동한다(실측: 280MB 요청이 5.8초에 걸쳐 전량 수신되고 그동안 디스크
#    스풀이 최대 ~268MB 잡혔다가 응답 직후 해제됨). connection_limit(100)까지
#    겹치면 인증 없이 도달 가능한 아무 라우트로도 디스크를 대량 점유시킬 수
#    있다 — 형제 상수와 같은 값(+여유)을 waitress 에도 그대로 줘서 헤더의
#    Content-Length 만 보고 본문 수신 전에 즉시 거부하게 만든다(app.py 자신의
#    413 처리는 그대로 살아 있는 정상범위 안에서만 동작 — 여유를 둔 이유).
MAX_BODY_BYTES = (int(os.environ.get("BOKGUON_MAX_UPLOAD_MB", "260")) + 10) * 1024 * 1024

if __name__ == "__main__":
    try:
        from waitress import serve
    except ImportError:
        raise SystemExit("waitress가 설치되어 있지 않습니다.  pip install waitress")

    env = os.environ.get("BOKGUON_ENV", "dev")
    #  ⚠⚠ [라운드273] flush=True 가 없으면 이 배너는 정상 종료(인터프리터가
    #    스스로 언와인드)에서만 로그파일에 남는다. 그런데 실제 운영
    #    재시작은 전부 감시자(외부접속_상시가동.ps1)의 Stop-Process -Force
    #    하드킬이라(실측: 동일 리다이렉트+하드킬 패턴으로 재현 — stderr는
    #    킬 이전에도 이미 파일에 쓰였는데 stdout은 킬 전후 모두 빈 파일로
    #    남았다), waitress_out.log 에 이 배너가 사실상 영원히 안 남는다.
    print("=" * 52, flush=True)
    print("  복구온 서비스 (waitress WSGI)", flush=True)
    print(f"  환경: {env}  |  http://{HOST}:{PORT}", flush=True)
    print("  (주)올림포스네트웍스 전략사업실 유경탁 파트장", flush=True)
    print("=" * 52, flush=True)
    if env != "prod":
        print("  ⚠ BOKGUON_ENV=prod 가 아닙니다. 운영 배포 시 .env를 설정하세요.",
              flush=True)
    try:
        serve(application, host=HOST, port=PORT, threads=THREADS,
              # nginx 뒤에 둘 때 X-Forwarded-* 신뢰
              trusted_proxy="127.0.0.1", trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
              max_request_body_size=MAX_BODY_BYTES,
              ident="bokguon")
    except OSError as e:
        #  ⚠⚠ [라운드273] 예전엔 이 자리에 보호가 전혀 없어, 포트가 이미
        #    쓰이고 있으면(재시작 스크립트가 이전 프로세스를 못 죽였을 때
        #    등) waitress/asyncore 내부 스택프레임 15줄짜리 트레이스백만
        #    보여줬다(실측: PermissionError [WinError 10013]) — 침묵하진
        #    않지만(stderr 로는 남는다) 원인 파악에 불친절했다.
        raise SystemExit(
            f"서버를 시작할 수 없습니다({type(e).__name__}: {e}) — "
            f"포트 {PORT}이 이미 사용 중이거나 접근 권한이 없을 수 있습니다. "
            f"'netstat -ano | findstr {PORT}' 로 점유 프로세스를 확인하세요.")
