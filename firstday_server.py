# -*- coding: utf-8 -*-
"""빈 DB로 서비스 '첫날'을 재현 — 데이터 0인 인스턴스를 격리 포트에 띄운다.

손으로 켜 볼 때는 인자 없이 그대로 실행하면 된다(레포 안 firstday.db·
고정 포트 8790). 자동검증(test_firstday.py)은 **이 파일을 그대로
서브프로세스로 불러**(사본을 손으로 다시 안 쓴다 — 306라운드 교훈:
사본은 원본이 나중에 강화돼도 안 따라온다) BOKGUON_DB_PATH·
BOKGUON_FIRSTDAY_PORT 두 환경변수만 자신의 값으로 오버라이드한다.

실행:  python firstday_server.py
       BOKGUON_FIRSTDAY_PORT=8791 BOKGUON_DB_PATH=... python firstday_server.py
"""
import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("BOKGUON_FIRSTDAY_PORT", "8790"))

#  ⚠⚠ [라운드307] setdefault 로 바꿨다 — test_firstday.py 가 자신의 격리된
#    임시 DB 경로를 미리 os.environ 에 심어 두고 이 파일을 서브프로세스로
#    부르면, 그 값을 그대로 존중한다(호출자가 안 정했을 때만 레포 안
#    firstday.db 로 기본 동작 — 손으로 직접 실행할 때와 동일).
os.environ.setdefault("BOKGUON_DB_PATH", os.path.join(HERE, "firstday.db"))
os.environ.setdefault("BOKGUON_ENV", "dev")
os.environ.setdefault("BOKGUON_OTP_POLICY", "off")
os.environ.setdefault("BOKGUON_SEED_DEMO", "0")
sys.path.insert(0, HERE)
os.chdir(HERE)

#  ⚠⚠ [라운드274] db.py 의 운영DB 안전장치는 진입점 파일명이 "test_"로
#    시작할 때만 발동한다(db.py:35) — 이 파일 이름은 해당 안 돼 가드의
#    보호를 못 받는다(실측: 이 이름 그대로에서 BOKGUON_DB_PATH 를 안
#    정하면 가드가 전혀 안 걸리고 운영 DB 경로를 그대로 문다). 위 줄들이
#    나중에 실수로 지워지거나 순서가 바뀌어도 걸리도록, import app
#    직전에 실제 os.environ 값을 마지막으로 한 번 더 확인한다 — 이
#    스크립트는 "빈 DB 재현"이 유일한 목적이라 운영 DB를 향할 정당한
#    이유가 원천적으로 없다.
_actual_db_path = os.environ.get("BOKGUON_DB_PATH", "")
_prod_db_path = os.path.join(HERE, "bokguon.db")
if not _actual_db_path or os.path.abspath(_actual_db_path) == os.path.abspath(_prod_db_path):
    raise SystemExit(
        "BOKGUON_DB_PATH 가 안 정해졌거나 운영 DB 파일을 가리킵니다 — "
        "'빈 DB 첫날 재현'이 목적인 도구가 운영 데이터를 열 수는 없습니다.")

#  ⚠⚠ [라운드274] Werkzeug 개발서버는 Windows 에서 같은 host:port 이중
#    바인딩을 막지 않는다 — 예외도 트레이스백도 없이 두 프로세스가 같은
#    포트를 나눠 쓴다(실측: 동일 스크립트를 두 번 실행해 재현, netstat 으로
#    두 PID 가 동시에 LISTENING 임을 확인, 첫 프로세스를 죽여도 healthz
#    가 계속 200 — 두 번째가 진짜로 요청을 처리하고 있었다). "새로 떴다"고
#    믿고 쓰다가 실제로는 신·구 프로세스가 뒤섞여 응답하는 사고를 막기
#    위해, app.run() 전에 포트가 이미 쓰이고 있는지 직접 확인한다.
_probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
_probe.settimeout(0.5)
try:
    _already_up = _probe.connect_ex(("127.0.0.1", PORT)) == 0
finally:
    _probe.close()
if _already_up:
    raise SystemExit(
        f"포트 {PORT}에 이미 무언가 응답하고 있습니다 — 이전에 띄운 "
        f"firstday_server.py 가 아직 살아있을 수 있습니다(Windows는 이중 "
        f"바인딩을 조용히 허용해 트레이스백도 없이 두 프로세스가 뒤섞입니다). "
        f"'netstat -ano | findstr {PORT}' 로 기존 프로세스를 먼저 정리하세요.")

import app  # noqa: E402
app.app.run(host="127.0.0.1", port=PORT, threaded=True, debug=False, use_reloader=False)
