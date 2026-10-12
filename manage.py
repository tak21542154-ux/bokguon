# -*- coding: utf-8 -*-
"""복구온 운영 관리 명령 (manage.py)

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

배포·운영 중 사람이 손으로 해야 하는 일을 전부 이 파일 하나로 모았다.
DB 를 직접 열어 UPDATE 하는 일이 없도록 하는 것이 목적이다.

  python manage.py gen-keys              .env 에 넣을 시크릿 3종 생성
  python manage.py check                 배포 전 점검 (운영 전 필수)
  python manage.py init                  DB 생성·스키마 반영·마이그레이션 (데이터 보존)
  python manage.py migrate               스키마 마이그레이션만 실행
  python manage.py create-admin <아이디> [--name 이름] [--role 역할]
  python manage.py create-insurer <기관명> <로그인ID>
  python manage.py reset-pw <admin|partner|insurer> <아이디>
  python manage.py set-fee <기관명 또는 로그인ID> <수수료율%>   보험사별 수수료율 변경
  python manage.py backup [경로]         무중단 핫 백업 (.backup API)
  python manage.py restore <백업파일>     백업본으로 복구
  python manage.py prune-logs            보관기간 지난 접속기록 삭제
  python manage.py prune-orphans [--yes]      없어진 사건의 자식 행 정리(기본 미리보기)
  python manage.py prune-personal [--dry-run]  처리방침상 보유기간 지난 개인정보 파기
                                                ⚠ 위와 반대로 기본이 **즉시 삭제**다
                                                (주간 예약작업이 플래그 없이 부른다 —
                                                 확인만 하려면 반드시 --dry-run 을 붙일 것)
  python manage.py stats                 테이블별 건수

  python manage.py sweep [--dry-run]     입찰 마감 등 예약 실행을 한 번 돌린다(크론이 부르는 것)
  python manage.py install-scheduler [--remove]  예약 실행을 주기 등록(윈도=작업 스케줄러/리눅스=cron)
  python manage.py mark-smoke-demo       스모크·검증 데이터에 데모 표식(go-live 정리 대상)을 붙인다

  python manage.py show-info             법정 게시물 회사 정보 확인 (미기재 항목 표시)
  python manage.py set-info <항목> "값"   회사 정보 입력 (코드 수정 불필요)
  python manage.py go-live --yes         실서비스 개시 — 데모 사건·계정 정리
"""
import os
import sys
import io
import re
import subprocess
import json
import base64
import secrets
import sqlite3
import shutil
import math
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

#  ── 로그 파일 분리 ──────────────────────────────────────────────
#  [Windows] 열려 있는 파일은 rename 할 수 없다(WinError 32). 운영 서버가 잡고 있는
#  bokguon.log 를 이 프로세스까지 함께 열면, 5MB 를 넘는 순간 서버의 로그 회전이
#  실패하고 그때의 로그 줄이 통째로 사라진다. 이 도구는 5분마다도 돌기 때문에
#  겹칠 확률이 높다 — 자기 파일에만 쓴다. (app.py 가 BOKGUON_LOG_FILE 를 읽는다)
os.environ.setdefault("BOKGUON_LOG_FILE", os.path.join(HERE, "logs", "manage.log"))
os.makedirs(os.path.join(HERE, "logs"), exist_ok=True)

sys.path.insert(0, HERE)

import envload  # noqa: E402
envload.load_dotenv()          # go-live 등이 BOKGUON_UPLOAD_DIR 을 올바로 읽도록
import db as DB  # noqa: E402


# [Windows] 콘솔이 cp949 면 한글·기호·ANSI 색을 출력하다 UnicodeEncodeError 로 죽는다.
#  출력 인코딩을 UTF-8 로 바꾸고, 색을 못 쓰는 콘솔에서는 색 코드를 비운다.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
_NO_COLOR = (os.name == "nt" and not os.environ.get("WT_SESSION")
             and not os.environ.get("ANSICON"))


def _c(code, s):
    return s if _NO_COLOR else f"\033[{code}m{s}\033[0m"


# ── 출력 도우미 ──────────────────────────────────────────────
def ok(msg):    print("  " + _c("92", "✔") + f" {msg}")
def warn(msg):  print("  " + _c("93", "▲") + f" {msg}")
def bad(msg):   print("  " + _c("91", "✘") + f" {msg}")
def head(msg):  print("\n" + _c("1", msg) + "\n" + "─" * 62)


def show_db_target():
    """되돌리기 어려운 명령(go-live·restore·prune-personal·prune-orphans) 앞에서
    지금 어느 DB 파일에 적용되는지 보여준다.

    ⚠⚠ [라운드263] db.py 의 유일한 운영DB 안전장치(_ENTRY 가 "test_"로 시작할
    때만 발동)는 manage.py 를 검사 대상에서 구조적으로 제외한다 — BOKGUON_DB_PATH
    를 안 정하면 이 파괴적 명령들이 조용히 실제 운영 파일(bokguon.db)에 연결되는데,
    확인 화면 어디에도 "이 파일을 지금 건드립니다"라는 표시가 없었다. 되돌리는
    것 자체를 막지는 않는다(운영자가 실제로 운영 DB에 적용해야 하는 정당한
    경우가 있다) — 다만 그 사실을 실행 직전에 반드시 눈에 띄게 만든다.
    """
    print(f"  대상 DB: {DB.DB_PATH}")


def gen_password(n=16):
    """사람이 옮겨 적을 수 있으면서 충분히 강한 임시 비밀번호.
    혼동되는 글자(0/O, 1/l/I)는 제외한다."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if any(c.isupper() for c in pw) and any(c.islower() for c in pw) and any(c.isdigit() for c in pw):
            return pw


# ══════════════════════════════════════════════════════════════
#  gen-keys — .env 시크릿 생성
# ══════════════════════════════════════════════════════════════
def cmd_gen_keys(argv):
    head("운영 시크릿 생성")
    print("아래 세 줄을 .env 파일에 그대로 붙여 넣으세요.")
    print("⚠ BOKGUON_ENC_KEY 를 잃어버리면 저장된 계좌번호를 영구히 복호화할 수 없습니다.")
    print("⚠ 키를 교체하면 기존 암호문은 모두 읽을 수 없게 됩니다. 별도 보관처(비밀번호 관리자)에 사본을 두세요.\n")
    print(f"BOKGUON_SECRET_KEY={secrets.token_hex(32)}")
    print(f"BOKGUON_ENC_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}")
    print(f"BOKGUON_INDEX_KEY={base64.urlsafe_b64encode(os.urandom(32)).decode()}")
    print()


# ══════════════════════════════════════════════════════════════
#  check — 배포 전 점검
# ══════════════════════════════════════════════════════════════
def _upload_root():
    """업로드 루트 — **빈 값을 '설정 안 함'으로 본다.**

    ⚠ `.env.example` 은 `BOKGUON_UPLOAD_DIR=` (값 없음)으로 배포되고 배포절차는
      이 파일을 복사해 쓰라고 한다. envload 는 빈 값도 그대로 환경변수에 넣으므로
      `os.environ.get(키, 기본값)` 은 기본값이 아니라 **빈 문자열**을 돌려준다.
      그러면 휴지통 경로가 `_trash`(실행 디렉터리 기준)가 되어 존재하지 않고,
      `os.path.isdir` 이 False 라 루프를 아예 안 돌아 **경고도 없이 '0건' 으로
      성공한다** — 삭제한 사진이 uploads/_trash 에 영구히 남는다(공개 처리방침의
      '복구·재생 불가 삭제' 가 무증상으로 미이행된다).
      photo_ai.py:31 은 이미 이 함정을 알고 막아 뒀는데 manage.py 만 옛 방식이었다.
      **쓰는 쪽(app.py 는 PHOTO.UPLOAD_ROOT)과 같은 답**을 내도록 맞춘다.
    """
    return (os.environ.get("BOKGUON_UPLOAD_DIR") or "").strip() \
        or os.path.join(HERE, "uploads")


def _orphan_photo_files(conn):
    """**디스크에만 있는 사진 파일**을 센다 — DB 가 모르는 것.

    ⚠ DB 행 고아(prune-orphans)는 이미 보는데 반대 방향은 아무도 안 봤다.
      검증 테스트가 BOKGUON_UPLOAD_DIR 없이 돌면 그 사진이 운영 uploads/ 로
      들어가고, 매일 백업(robocopy /E)이 지우지 않아 영구히 쌓인다.
      **지우지는 않는다** — 무엇이 얼마나 있는지만 알린다(사진은 분쟁 자료다).
    """
    root = os.path.abspath(_upload_root())
    if not os.path.isdir(root):
        return {"files": 0, "orphans": 0, "mb": 0.0, "root": root}
    known = set()
    try:
        for r in conn.execute("SELECT rel_path FROM photos "
                              " WHERE COALESCE(rel_path,'') <> ''"):
            known.add(os.path.normcase(os.path.abspath(
                os.path.join(root, str(r[0]).replace("/", os.sep)))))
    except (sqlite3.Error, OSError):
        return None
    files = orph = 0
    size = 0
    #  ⚠ **휴지통은 세지 않는다.** 삭제·정리로 우리가 직접 옮겨 둔 것이라
    #    DB 에 짝이 없는 게 당연한데, 그걸 "DB 에 없는 사진" 으로 경고하면
    #    정리를 할수록 경고가 커진다(자기가 만든 걸 자기가 고발한다).
    _trash = os.path.normcase(os.path.join(root, "_trash"))
    for dp, _dirs, fs in os.walk(root):
        if os.path.normcase(dp).startswith(_trash):
            continue
        for f in fs:
            files += 1
            fp = os.path.join(dp, f)
            if os.path.normcase(os.path.abspath(fp)) not in known:
                orph += 1
                try:
                    size += os.path.getsize(fp)
                except OSError:
                    pass
    return {"files": files, "orphans": orph, "mb": size / 1048576.0, "root": root}


def cmd_check(argv):
    head("배포 전 점검")
    fails = 0
    warns = 0

    # 1) 환경변수
    envfile = os.path.join(HERE, ".env")
    if os.path.exists(envfile):
        ok(f".env 파일 존재 — {envfile}")
        if os.name != "nt":
            mode = oct(os.stat(envfile).st_mode)[-3:]
            if mode not in ("600", "400"):
                bad(f".env 파일 권한이 {mode} 입니다. 600 으로 바꾸세요:  chmod 600 .env"); fails += 1
            else:
                ok(f".env 파일 권한 {mode}")
        #  ⚠⚠ [라운드305] 여기서 직접 다시 파싱하지 않는다 — 이 파일 61행의
        #    envload.load_dotenv() 가 이 명령이 시작되기 전에 이미 값을
        #    os.environ 에 넣어 뒀다. 예전엔 이 자리에 별도의 손짜서 파서가
        #    있었는데(utf-8-sig 로 BOM 까지 막아 그 시점의 envload.py 보다
        #    오히려 더 견고했다), 그 결과 "manage.py check 는 통과하는데
        #    실제 서버는 다른 값으로 뜬다"는 자기도구 거짓 초록이 났다 —
        #    check 가 실제 서버(wsgi.py·serve_waitress.py)와 **다른 파서로
        #    같은 파일을 읽고 있었기 때문**이다(272라운드가 popbill_check.py
        #    에서 이미 고친 것과 같은 유형 — "자체 .env 파서를 두지 말고
        #    서버가 실제로 쓰는 그 로더에 위임한다"). 공유 로더 자신의 BOM
        #    처리를 고쳤으니(envload.py) 이제 이 자리는 그 결과를 그대로
        #    신뢰하고, 두 번째 파서를 두지 않는다.
    else:
        bad(".env 파일이 없습니다.  cp .env.example .env  후 python manage.py gen-keys 로 값을 채우세요."); fails += 1

    if os.environ.get("BOKGUON_ENV", "dev").lower() != "prod":
        bad("BOKGUON_ENV 가 prod 가 아닙니다. 운영 배포 시 반드시 prod 로 두세요."); fails += 1
    else:
        ok("BOKGUON_ENV=prod")

    # 내부 시연용 계정 노출 스위치 — 대외 공개 전에 반드시 꺼야 한다.
    #  켜져 있으면 로그인 화면과 소개면 하단에 아이디·비밀번호가 그대로 보인다.
    if os.environ.get("BOKGUON_SHOW_DEMO_HINT", "0") == "1":
        bad("BOKGUON_SHOW_DEMO_HINT=1 — 체험 계정 비밀번호가 화면에 노출되고 있습니다. "
            "내부 시연용이며, 대외 공개 전에 0 으로 되돌리세요."); fails += 1
    else:
        ok("체험 계정 노출 스위치 꺼짐")

    for key, label in [("BOKGUON_SECRET_KEY", "세션 서명키"),
                       ("BOKGUON_ENC_KEY", "계좌번호 암호화키"),
                       ("BOKGUON_INDEX_KEY", "블라인드 인덱스키")]:
        v = os.environ.get(key, "")
        if not v or "여기에" in v:
            bad(f"{label}({key}) 가 비어 있거나 예시값 그대로입니다."); fails += 1
        elif len(v) < 32:
            bad(f"{label}({key}) 가 너무 짧습니다({len(v)}자)."); fails += 1
        else:
            ok(f"{label} 설정됨 ({len(v)}자)")

    #  ⚠⚠ 키 길이·존재만 보고 "설정됨"이라 답하면 안 된다 — **다른** 키라도
    #    32자 이상이면 위 검사는 그대로 통과한다. crypto_util.decrypt() 는
    #    실패를 전부 삼켜 빈 문자열을 돌려주므로(계좌 없음과 구분 불가),
    #    서버 이전 때 이 키를 그대로 옮기지 않으면 전 업체 계좌가 조용히
    #    사라진 것처럼 보이는데 어디서도 에러가 안 뜬다. 실제 저장된 암호문을
    #    복호화해 봐야만 "이 키가 맞는 키"임을 확인할 수 있다.
    try:
        import crypto_util as CRYPTO
        conn = DB.get_db()
        enc_row = conn.execute(
            "SELECT id, bank_account_enc FROM partners "
            " WHERE bank_account_enc LIKE 'v1:%' LIMIT 1").fetchone()
        conn.close()
        if enc_row:
            if CRYPTO.decrypt(enc_row["bank_account_enc"]):
                ok("계좌번호 암호화키 복호화 왕복 확인(업체 #%s)" % enc_row["id"])
            else:
                bad("계좌번호 암호화키가 저장된 암호문을 못 엽니다(업체 #%s) — "
                    "BOKGUON_ENC_KEY 가 이 DB 를 암호화한 키와 다릅니다. "
                    "서버·환경을 옮겼다면 예전 .env 의 키를 그대로 가져와야 합니다."
                    % enc_row["id"]); fails += 1
        else:
            warn("복호화 왕복 확인 건너뜀 — 암호화된 계좌가 아직 없습니다."); warns += 1
    except Exception as e:                                          # noqa: BLE001
        warn(f"복호화 왕복 확인을 못 돌렸습니다({type(e).__name__}) — DB 가 아직 없을 수 있습니다.")
        warns += 1

    # 2) 의존성
    for mod, pkg in [("flask", "Flask"), ("cryptography", "cryptography")]:
        try:
            __import__(mod); ok(f"{pkg} 설치됨")
        except ImportError:
            bad(f"{pkg} 미설치 — pip install -r requirements.txt"); fails += 1
    try:
        __import__("waitress" if os.name == "nt" else "gunicorn")
        ok("WSGI 서버 설치됨 (" + ("waitress" if os.name == "nt" else "gunicorn") + ")")
    except ImportError:
        bad("WSGI 서버 미설치 — pip install -r requirements.txt"); fails += 1

    # 3) DB
    if not os.path.exists(DB.DB_PATH):
        warn(f"DB 파일이 아직 없습니다 — python manage.py init 으로 생성하세요."); warns += 1
    else:
        conn = DB.get_db()
        jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        (ok if jm.lower() == "wal" else bad)(f"journal_mode = {jm}" + ("" if jm.lower() == "wal" else "  ← WAL 이어야 합니다"))
        if jm.lower() != "wal":
            fails += 1

        # 기본 비밀번호가 남아 있는지
        weak = []
        for row in conn.execute("SELECT username, password_hash FROM admins"):
            for guess in ("bokguon2026", "staff2026", "admin", "1234"):
                if DB.verify_pw(guess, row["password_hash"]):
                    weak.append(f"admins/{row['username']} = {guess}")
                    break
        for row in conn.execute("SELECT login_id, password_hash FROM partners WHERE login_id IS NOT NULL"):
            if row["password_hash"] and DB.verify_pw("partner2026", row["password_hash"]):
                weak.append(f"partners/{row['login_id']} = partner2026")
        for row in conn.execute("SELECT login_id, password_hash FROM insurers WHERE login_id IS NOT NULL"):
            if row["password_hash"] and DB.verify_pw("bokguon2026", row["password_hash"]):
                weak.append(f"insurers/{row['login_id']} = bokguon2026")
        if weak:
            bad(f"기본(데모) 비밀번호를 그대로 쓰는 계정 {len(weak)}개:")
            for w in weak:
                print(f"        · {w}")
            print("        → python manage.py reset-pw <역할> <아이디>  로 교체하세요.")
            fails += 1
        else:
            ok("기본 비밀번호를 쓰는 계정 없음")

        # 관리자 계정이 남아 있는가.
        #  go-live 는 관리자를 '이름'(admin·staff)으로 지우는데, bootstrap.sh 가 만드는
        #  최초 계정 이름이 하필 'admin' 이다. DEPLOY.md 순서대로 go-live 를 먼저 돌리면
        #  관리자 0명 구간이 생기고, 그 상태로도 여기서 '배포 가능'이 떠 버리면
        #  콘솔에 아무도 못 들어간다(앱에 관리자 셀프가입 경로가 없다).
        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        if n_admin == 0:
            bad("관리자 계정이 0개입니다. 콘솔에 로그인할 수 없습니다.")
            print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
            print("        ※ 아이디로 admin·staff 를 쓰지 마세요. go-live 가 다시 지웁니다.")
            fails += 1
        else:
            #  ⚠⚠ [라운드475] 위 검사는 "로그인 자체가 안 되는" 최악만 잡는다 —
            #    관리자가 1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·
            #    정산이체·요율설정 등 최고관리자 전용 기능은 아무도 못 켠다
            #    (로그인은 되니 위 검사만 보면 '정상'으로 보인다). 실측(스크래치
            #    DB): create-admin 을 --role 없이 돌린 뒤 go-live 를 실행하면
            #    정확히 이 상태(관리자 1명·최고관리자 0명)가 됐었다.
            n_super = conn.execute(
                "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
            if n_super == 0:
                bad(f"관리자 계정은 {n_admin}개 있지만 최고관리자가 0명입니다 — "
                    f"계정관리·정산이체·요율설정을 아무도 할 수 없습니다.")
                print("        → python manage.py create-admin <아이디> --name <이름> --role 최고관리자")
                fails += 1
            else:
                ok(f"관리자 계정 {n_admin}개(최고관리자 {n_super}명 포함)")

        #  활성 협력사인데 지급 계좌가 없으면, 공사를 다 끝낸 뒤 이체 관문에서 막힌다.
        #   그때는 이미 자재비·인건비가 나간 뒤라 되돌릴 수 없다. 개시 전에 센다.
        try:
            no_acct = conn.execute(
                #  ⚠ **로그인 계정이 있는** 업체만 센다. partners 에는 아직 입점 전인
                #     조사 명부(수백 곳)가 함께 들어 있어, 전체를 세면 경고가 늘 켜져
                #     아무도 안 보게 된다. 실제로 입찰·낙찰이 가능한 곳만 문제다.
                """SELECT name, login_id FROM partners
                    WHERE COALESCE(login_id,'') <> ''
                      AND COALESCE(status,'') NOT IN ('퇴출','정지','탈퇴','중지')
                      AND (COALESCE(bank_account_enc,'')='' OR COALESCE(bank_holder,'')='')
                    ORDER BY id""").fetchall()
            if no_acct:
                warn(f"지급 계좌가 없는 활성 협력사 {len(no_acct)}곳 — 낙찰받아도 이체가 나가지 않습니다.")
                for r in no_acct[:10]:
                    print(f"        · {r['name']} ({r['login_id'] or '아이디 없음'})")
                if len(no_acct) > 10:
                    print(f"        · … 외 {len(no_acct)-10}곳")
                print("        → 콘솔 [업체]에서 사업자등록증·통장 사본 확인 후 계좌를 등록하세요.")
                warns += 1
            else:
                ok("로그인 계정을 가진 협력사 전원 지급 계좌 등록됨")
        except sqlite3.Error as e:
            warn(f"계좌 점검 실패: {e}"); warns += 1

        #  알림이 '발송대기'로만 쌓이면 아무도 연락을 못 받는다. 그런데 화면상으론
        #  '알림 보냄'으로 보인다 — 조용한 실패라서 여기서 캔다.
        try:
            pend = conn.execute(
                """SELECT COUNT(*) n FROM notifications
                    WHERE status='발송대기'
                      AND created_at < datetime('now','+9 hours','-2 hours')""").fetchone()["n"]
            if pend:
                #  원인을 짚어 준다. "둘 중 하나"라고만 하면 운영자가 엉뚱한 데를 뒤진다.
                try:
                    import notify_popbill as NP
                    cause = ("팝빌 발송 설정이 아직 없습니다 — 키를 받기 전까지는 정상입니다."
                             if not NP.ready() else
                             "팝빌은 켜져 있는데 발송이 안 됩니다 — 예약 실행·발신번호 등록을 확인하세요.")
                except Exception:
                    cause = "발송 어댑터를 확인하지 못했습니다."
                warn(f"2시간 넘게 발송되지 않은 알림 {pend}건 — {cause} (콘솔 [발송대기함])")
                warns += 1
            else:
                ok("발송 적체 없음")
        except sqlite3.Error as e:
            #  ⚠⚠ [라운드184] 바로 위 계좌점검(325행)은 실패를 warn 으로 알리는데
            #    이 점검만 조용히 넘어갔다 — 같은 함수 안의 같은 종류 결함.
            warn(f"발송 적체 점검 실패: {e}"); warns += 1

        # 데모 데이터 잔존 — 이름이 아니라 **표식**으로 판별한다.
        #  시드에는 '메리츠화재'·'DB손보' 처럼 실제 사명으로 들어간 데모 행도 있어서,
        #  이름 패턴으로 세면 남아 있는데도 '없음'으로 보고된다.
        #  ⚠ DEMO_TABLES 에만 물으면 **거짓 초록**이 나온다. 출동수배·현장합의·
        #    콜백문의·일정(happy_calls·schedule_events, 116·122라운드에서 자기
        #    is_demo 를 갖게 됐다)은 그 목록에 없어, 잔재가 남아도 '없음'으로 찍혔다.
        #  ⚠⚠ [라운드183] 바깥 try 는 죽은 코드였다 — 안쪽 try 가 sqlite3.Error 를
        #    전부(표·컬럼이 없는 경우 포함) 먼저 삼켜 버려 바깥 except 에 아무것도
        #    안 왔고, demo_total=-1 은 영원히 실행되지 않았다. 그 결과 **마이그레이션
        #    전 DB**(is_demo 컬럼이 아예 없음)에서 13개 표가 전부 실패해도 demo_total
        #    은 초기값 0 그대로 남아 "데모 데이터 없음"이라는 거짓 초록을 냈다 —
        #    바로 아래의 "확인 불가" 경고 분기는 그래서 한 번도 실행된 적이 없었다.
        #    go-live 의 _dead 목록(1726행)과 같은 방식으로, 실패한 표 이름을 실제로
        #    모아서 판정한다.
        #  ⚠⚠ [라운드184] 판정은 여기서 demo_total=-1 로 확정 짓지 않고 바로 아래
        #    ghost(표식 없는 검증 사건) 판정까지 다 본 뒤로 미룬다 — 이 둘이
        #    **같은 최종 판정**(500행 부근)에 들어가는데 ghost 쪽만 여전히
        #    "실패하면 0 으로 친다"였다(운영 실측: ghost 77건·정산 39건·1억
        #    2,950만원이 지금 이 판정 뒤에 그대로 있다). 게다가 여기서 무조건
        #    -1 로 덮으면 **부분 실패라도 이미 확인된 양수 합계**(예: 12개 표는
        #    성공해 108건을 셌는데 1개만 실패)까지 "확인 불가"로 깎여, bad()가
        #    아니라 warn() 으로 떨어진다 — warn 은 배포를 막지 않는다(800행
        #    `if fails:` 만 막는다) — 그러면 **확실히 남아 있는 데모 데이터**를
        #    두고도 "배포 가능"이 나온다. demo_total 은 끝까지 '지금까지 확인된
        #    합계'로 두고, _demo_dead 는 별도로만 판정에 쓴다.
        demo_total = 0
        _demo_dead = []
        for t in list(DB.DEMO_TABLES) + ["dispatches", "field_agreements",
                                          "happy_calls", "schedule_events"]:
            try:
                demo_total += conn.execute(
                    f"SELECT COUNT(*) n FROM {t} WHERE is_demo=1").fetchone()["n"]
            except sqlite3.Error:
                _demo_dead.append(t)
        #  없어진 사건을 가리키는 고아 행 — 정리가 반쪽이었다는 신호다.
        #  ⚠ 점검과 정리(prune-orphans)가 **같은 목록**을 봐야 한다. 따로 적어 두면
        #    한쪽만 늘어나서 "정리했는데 경고가 남는다" 가 된다.
        orphan = 0
        for t in CASE_CHILD_TABLES:
            try:
                orphan += conn.execute(
                    f"SELECT COUNT(*) n FROM {t} "
                    f" WHERE case_id IS NOT NULL "
                    f"   AND case_id NOT IN (SELECT id FROM cases)").fetchone()["n"]
            except sqlite3.Error:
                pass
        #  ★ 사건 말고 **사진·하자·수배로만 닿는 표**도 본다(사각지대였다).
        for _t, _col, _parent in FK_CHILD_TABLES:
            try:
                orphan += conn.execute(
                    f"SELECT COUNT(*) n FROM {_t} "
                    f" WHERE {_col} IS NOT NULL "
                    f"   AND {_col} NOT IN (SELECT id FROM {_parent})").fetchone()["n"]
            except sqlite3.Error:
                pass
        if orphan:
            warn(f"없어진 부모를 가리키는 고아 행 {orphan}건 — "
                 f"python manage.py prune-orphans --yes 로 정리하세요."); warns += 1
        #  ★ **공종 커버리지** — 화면에서 고를 수 있는 공종이 판정표·표준단가·
        #    개산 레시피에 다 있는가. 하나라도 비면 그 공종 사건은 도급 판정이
        #    '기타' 로 떨어지거나 가견적·2차 하한이 0 이 된다(실측: '방음벽·휀스·펜스'
        #    는 셋 다 없고, '조경·수목'·'종합 원상복구' 는 레시피가 없다).
        #    ⚠ 목록을 여기에 또 적지 않는다 — 적는 순간 다섯 번째 사본이 되어
        #      화면과 어긋난다. **화면이 실제로 그리는 배열**을 읽어서 대조한다.
        try:
            import re as _re
            import compliance as _CP
            import repair_estimate as _RE
            _js = io.open(os.path.join(HERE, "static", "admin.js"),
                          encoding="utf-8", errors="replace").read()
            _m0 = _re.search(r"const majors = \[([^\]]+)\]", _js)
            _majors = ([s.strip().strip("'\"") for s in _m0.group(1).split(",")]
                       if _m0 else [])
            _rules = set(_CP.WORK_RULES.keys())
            #  ⚠ RECIPES 는 **dict**(패턴키 → 레시피)다. 그냥 순회하면 문자열 키가
            #    나와 .get 에서 터지고, 그 예외를 삼키면 "건너뛰었습니다"로만 보인다.
            _rec = {v.get("major") for v in getattr(_RE, "RECIPES", {}).values()
                    if isinstance(v, dict)}
            #  ⚠ 표는 standard_boq, 공종 열은 major 다(boq_items·category 아님).
            #    **활성 단가만** 센다 — 비활성 행만 남은 공종은 실제로는 근거가 없다
            #    (철칙 3: 근거 없는 단가를 활성으로 쓰지 않는다).
            _boq = {r["major"] for r in conn.execute(
                "SELECT DISTINCT major FROM standard_boq "
                " WHERE COALESCE(major,'') <> '' AND COALESCE(active,1)=1")}
            _gap = []
            for _m in [x for x in _majors if x]:
                _miss = ([] if _m in _rules else ["도급판정표"]) \
                    + ([] if _m in _boq else ["표준단가"]) \
                    + ([] if _m in _rec else ["개산레시피"])
                if _miss:
                    _gap.append(f"{_m}({'·'.join(_miss)})")
            if not _majors:
                warn("화면의 공종 목록을 읽지 못해 커버리지 점검을 건너뛰었습니다"); warns += 1
            elif _gap:
                warn(f"공종 자료 누락 {len(_gap)}건 — " + " / ".join(_gap)); warns += 1
                warn("  → 그 공종 사건은 가견적·2차 하한 근거가 없어 2차 공고가 막힙니다"
                     " (도급판정표가 없으면 '기타' 규칙으로 판정됩니다)")
            else:
                ok(f"공종 {len(_majors)}개가 판정표·표준단가·개산레시피에 모두 있습니다")
        except Exception as _e:
            #  ⚠ **왜 건너뛰었는지 말한다.** 이유 없는 "건너뜀"은 통과처럼 읽혀서,
            #    검사가 죽어 있는 채로 몇 판을 지나간다(실제로 그랬다 —
            #    RECIPES 가 dict 인 것과 표 이름을 몰라 두 번 조용히 꺼졌다).
            warn(f"공종 커버리지 점검을 건너뛰었습니다 — {type(_e).__name__}: {_e}")
            warns += 1
        #  ★ **반대 방향** — DB 가 모르는데 디스크에 있는 사진.
        #    검증이 운영 uploads/ 에 쓰면 여기서만 드러난다(행이 없으니
        #    위 고아 검사에는 안 잡힌다). 지우지 않고 알리기만 한다.
        _of = _orphan_photo_files(conn)
        if _of is None:
            warn("디스크 사진 점검을 건너뛰었습니다(사진 폴더를 읽지 못했습니다)"); warns += 1
        elif _of["orphans"]:
            warn(f"DB 에 없는 사진 파일 {_of['orphans']:,}개 "
                 f"({_of['mb']:.1f}MB · 전체 {_of['files']:,}개) — "
                 f"검증이 운영 폴더에 쓴 흔적일 수 있습니다. "
                 f"위치: {_of['root']}"); warns += 1
        else:
            ok(f"사진 파일 {_of['files']:,}개 — 전부 DB 와 짝이 맞습니다")
        #  ★ **부모 쪽 고아도 본다.** 위 검사는 '사건의 자식' 만 본다 —
        #    사건이 없어진 발주처·협력사를 가리키는 경우는 통째로 못 봤다.
        #    그러면 목록·엑셀·보험사 리포트가 **존재하지 않는 회사**를 인쇄한다.
        for _t, _col, _parent, _label in (("cases", "insurer_id", "insurers", "발주처"),
                                          ("cases", "partner_id", "partners", "시공업체"),
                                          ("settlements", "partner_id", "partners", "시공업체")):
            try:
                _n = conn.execute(
                    f"SELECT COUNT(*) n FROM {_t} WHERE {_col} IS NOT NULL "
                    f"  AND {_col} NOT IN (SELECT id FROM {_parent})").fetchone()["n"]
            except sqlite3.Error:
                continue
            if _n:
                warn(f"{_t} {_n}건이 **없어진 {_label}**를 가리킵니다 — "
                     f"화면·엑셀이 존재하지 않는 회사를 인쇄합니다."); warns += 1
        #  ★ **표식이 없어도 데모 발주처에 속하면 데모다.**
        #    종전에는 is_demo 표식만 세어 "45건" 이라고 말했는데, 실제로는
        #    검증이 만든 사건 81건이 표식 없이 더 있었다(go-live 가 안 지운다).
        #    사람은 45건만 지우면 된다고 믿고 열었다가, 첫날 대시보드에서
        #    남의 사건 81건과 정산 1억 2,950만원을 보게 된다.
        #  ⚠⚠ [라운드184] 실패하면 0 으로 치던 것을 _demo_dead 에 남기는 것으로
        #    바꾼다 — 위 demo_total 루프와 같은 원칙.
        try:
            ghost = conn.execute(
                "SELECT COUNT(*) n FROM cases WHERE COALESCE(is_demo,0)=0 "
                "  AND insurer_id IN (SELECT id FROM insurers "
                "                      WHERE COALESCE(is_demo,0)=1)").fetchone()["n"]
        except sqlite3.Error:
            ghost = 0
            _demo_dead.append("cases↔insurers(표식없는 검증사건)")
        if ghost:
            #  ⚠ 여기서도 실패를 0건·0원으로 감추지 않는다 — "표식 없는 사건이
            #    있는 건 확실한데 정산 규모는 못 쟀다"를 그대로 알린다.
            try:
                gmoney = conn.execute(
                    "SELECT COUNT(*) n, COALESCE(SUM(amount),0) amt FROM settlements s "
                    " WHERE s.case_id IN (SELECT id FROM cases WHERE COALESCE(is_demo,0)=0 "
                    "        AND insurer_id IN (SELECT id FROM insurers "
                    "                            WHERE COALESCE(is_demo,0)=1))").fetchone()
            except sqlite3.Error:
                gmoney = None
            if gmoney is None:
                bad(f"**표식 없는 검증 사건 {ghost}건** 이 데모 발주처에 붙어 있습니다 "
                    f"(정산 규모는 조회 실패 — 다시 실행해 확인하세요). "
                    f"go-live 가 함께 정리합니다 — 먼저 미리보기로 확인하세요.")
            else:
                bad(f"**표식 없는 검증 사건 {ghost}건** 이 데모 발주처에 붙어 있습니다 "
                    f"(정산 {gmoney['n']}건 · {gmoney['amt']:,}원). "
                    f"go-live 가 함께 정리합니다 — 먼저 미리보기로 확인하세요.")
            fails += 1
        if demo_total > 0 or ghost:
            # 데모 사건이 남으면 통계·정산이 오염된다 — 권고가 아니라 차단이다.
            #  ⚠ _demo_dead 가 있어도 여기서는 무시한다 — 이미 확인된 demo_total·
            #    ghost 만으로 충분히 "남아 있다"고 확정할 수 있는데, 아래 else 로
            #    떨어지면 확정된 사실이 "확인 불가" 경고(배포를 막지 않는다)로
            #    깎인다.
            bad(f"데모 데이터 {demo_total}건(표식) + {ghost}건(발주처 기준) = "
                f"{demo_total + ghost}건이 남아 있습니다.  python manage.py go-live --yes")
            fails += 1
        elif not _demo_dead:
            ok("데모 데이터 없음")
        else:
            warn("데모 표식을 전부 확인하지 못했습니다(" + ", ".join(_demo_dead) + ") — "
                 "표·컬럼 누락이면 python manage.py migrate, 일시적 오류(DB 잠금 등)면 "
                 "다시 실행해 확인하세요."); warns += 1
        conn.close()

    # 3-2) 외부 공개 주소가 실제로 허용 목록에 들어 있는가
    #  ⚠ 2026-08-06 실제 사고 — 사람이 손으로 서버를 재시작하자 .env 의 옛 목록
    #    (127.0.0.1,localhost)만 남아 **외부 요청이 전부 400 BAD_HOST** 로 막혔다.
    #    로컬 점검은 전부 통과해서(127.0.0.1 은 늘 허용) 몇 시간 동안 몰랐다.
    try:
        _hf = os.path.join(HERE, "logs", "public_host.txt")
        _pub = []
        if os.path.exists(_hf):
            with open(_hf, encoding="utf-8-sig") as f:
                _pub = [ln.strip().lower() for ln in f
                        if ln.strip() and not ln.strip().startswith("#")]
        _allow = {h.strip().lower() for h in
                  (os.environ.get("BOKGUON_ALLOWED_HOSTS", "") or "").split(",") if h.strip()}
        #  ★ **환경변수만 보고 판정하지 않는다.** app.py 는 ALLOWED_HOSTS 에
        #    이 파일(public_host.txt)을 합쳐서 쓴다 — 그래서 .env 에 없어도
        #    서버는 그 Host 를 받는다. 그걸 모르고 목록만 비교하면
        #    **정상 구성에서 영원히 뜨는 경고**가 되어 신호가 마모된다.
        #    유일하게 믿을 수 있는 것은 **돌고 있는 서버에 직접 물어보는 것**이다
        #    (Host 헤더만 바꿔 로컬로 — 외부 왕복이 필요 없다).
        if _pub:
            _host = _pub[0]
            _port = os.environ.get("BOKGUON_PORT", "8771")
            try:
                import http.client as _hc
                _cx = _hc.HTTPConnection("127.0.0.1", int(_port), timeout=4)
                _cx.request("GET", "/healthz", headers={"Host": _host})
                _st = _cx.getresponse().status
                _cx.close()
                if _st == 400:
                    bad(f"공개 주소 {_host} 로 온 요청을 서버가 400 으로 막고 있습니다. "
                        f"허용 Host 목록이 어긋났습니다 — "
                        f"deploy/외부접속_상시가동.ps1 로 다시 띄우세요."); fails += 1
                elif _st < 500:
                    ok(f"외부 공개 주소 통과 확인 — {_host} (서버 응답 {_st})")
                else:
                    warn(f"공개 주소 확인 중 서버가 {_st} 를 냈습니다 — {_host}"); warns += 1
            except OSError:
                #  서버가 안 떠 있는 것은 별도 항목이 본다. 여기서 두 번 울리지 않는다.
                ok(f"외부 공개 주소 {_host} (서버 미기동 — Host 통과 여부는 확인 못 함)")
        else:
            #  ⚠⚠ [라운드581] 예전엔 `elif _pub:` 였다 — 바로 위 `if _pub:` 와 조건이
            #    완전히 같아(둘 다 그냥 `_pub`) 이 분기는 _pub 값과 무관하게 실행될
            #    수 없는 죽은 코드였다(실측: `if X: ... elif X: ...` 는 X 가 참이든
            #    거짓이든 elif 가 영원히 안 걸린다 — pyflakes 가 아니라 그냥 논리로
            #    확인 가능). 그 결과 logs/public_host.txt 가 없거나(신규 배포 전)
            #    전부 주석·빈 줄뿐이면 이 구간 전체가 ok·warn·bad 어느 것도 안 찍고
            #    조용히 사라졌다 — 바로 위(공종 커버리지 점검, 492행) 같은 함수가
            #    이미 "이유 없는 건너뜀은 통과처럼 읽힌다"고 명시한 원칙을 이 자리만
            #    어기고 있었다. 이 검사 자체가 2026-08-06 사고(허용 Host 어긋남을
            #    몇 시간 동안 아무도 못 봄)의 재발 방지용이라, 검사가 안 됐다는
            #    사실 자체를 반드시 알려야 한다.
            warn("logs/public_host.txt 에 기록된 공개 주소가 없어 외부 접속 허용 "
                 "여부를 확인하지 못했습니다 — 최초 배포 전이면 정상이지만, 이미 "
                 "운영 중이라면 deploy/외부접속_상시가동.ps1 을 다시 실행해 "
                 "기록을 남기세요."); warns += 1
    except Exception as e:
        #  ⚠⚠ [라운드583] 여기가 `except Exception: pass` 였다 — 바로 위 else 절이
        #    [라운드581]에서 고친 그 원칙("이유 없는 건너뜀은 통과처럼 읽힌다")을
        #    이 바깥 except 가 한 겹 위에서 다시 어기고 있었다. 예를 들어
        #    BOKGUON_PORT 가 숫자가 아니면(공백·주석 등으로 오염) int(_port) 가
        #    ValueError 를 던지는데, 안쪽 try(597행)는 OSError 만 잡으므로 이
        #    바깥 except 까지 올라와 조용히 삼켜졌다 — ok/warn/bad 어느 것도
        #    안 찍혀, 2026-08-06 사고 재발 방지용인 이 절 전체가 실행됐는지조차
        #    알 수 없는 채로 "배포 가능"이 떴다. 형제 관례(492행 공종 커버리지
        #    점검의 except)를 그대로 따른다.
        warn(f"외부 공개 주소 확인을 하지 못했습니다 — {type(e).__name__}: {e}"); warns += 1

    # 4) 법정 게시물 미기재 항목
    try:
        import legal_docs as LEGAL
        pending = sorted(set(LEGAL.PENDING))
        if pending:
            bad(f"법정 게시물 미기재 항목 {len(pending)}개 — python manage.py set-info 로 채우세요:")
            for p in pending:
                print(f"        · {p}")
            fails += 1
        else:
            ok("법정 게시물(처리방침·약관·사업자정보) 항목 모두 기재됨")
    except Exception as e:
        warn(f"legal_docs 확인 실패: {e}"); warns += 1

    # 4-2) 운영 보안 설정 (MG-06)
    prod = os.environ.get("BOKGUON_ENV", "dev").lower() == "prod"
    if prod:
        #  ⚠ 종전에는 "값이 비면 **허위 고지**" 라 실패(✘)로 세웠다. 이제 처리방침이
        #    설정을 보고 그 문구를 빼고 표시하므로(LEGAL.privacy_body) 고지 불일치는
        #    없다 — 남는 것은 '켜 두는 편이 안전하다' 는 보안 권고뿐이라 경고(▲)로 내린다.
        #    출시를 막던 항목이 하나 줄어드는 것이므로 근거를 여기 적어 둔다.
        if not os.environ.get("BOKGUON_ADMIN_IP_ALLOW", "").strip():
            warn("관리자 콘솔 IP 제한이 꺼져 있습니다(BOKGUON_ADMIN_IP_ALLOW 비어 있음). "
                 "처리방침은 설정에 맞춰 그 문구를 빼고 표시하므로 고지 불일치는 없습니다 — "
                 "사무실 고정 IP 가 있으면 넣어 두는 편이 안전합니다."); warns += 1
        else:
            ok("관리자 콘솔 IP 화이트리스트 설정됨")
        # 프록시 뒤인데 신뢰 프록시가 비면 client_ip 위조로 IP제한·레이트리밋이 무력화된다
        #  ⚠⚠ [432라운드] BOKGUON_FORWARDED_ALLOW 는 gunicorn_conf.py 단 한 곳만
        #    읽는 값이다(grep 확인) — Windows/waitress 경로(serve_waitress.py)는
        #    이 값을 아예 안 읽고 trusted_proxy="127.0.0.1"이 하드코딩돼 있어,
        #    이 검사가 통과해도 waitress 의 실제 신뢰경계와는 무관했다. 그
        #    하드코딩이 의미를 가지려면 BOKGUON_HOST 가 루프백이어야 하는데
        #    (serve_waitress.py 자신의 기본값은 "0.0.0.0" — 설정을 빠뜨리면
        #    외부에 그대로 노출된다) 이 절은 그 진짜 전제조건을 안 보고 있었다.
        #    274행이 이미 쓰는 os.name=="nt" 분기를 이 검사에도 맞춘다.
        if os.name == "nt":
            _host_val = os.environ.get("BOKGUON_HOST", "0.0.0.0").strip().lower()
            if os.environ.get("BOKGUON_BEHIND_PROXY") == "1" and \
                    _host_val not in ("127.0.0.1", "localhost", "::1"):
                bad(f"BEHIND_PROXY=1 인데 BOKGUON_HOST 가 루프백이 아닙니다"
                    f"({_host_val or '(비어있음, 기본값 0.0.0.0)'}) — waitress 의 "
                    "trusted_proxy=127.0.0.1 하드코딩이 전제하는 조건이 깨져 "
                    "원본 서버가 외부에 직접 노출될 수 있습니다."); fails += 1
        elif os.environ.get("BOKGUON_BEHIND_PROXY") == "1" and \
                not os.environ.get("BOKGUON_FORWARDED_ALLOW", "").strip():
            bad("BEHIND_PROXY=1 인데 BOKGUON_FORWARDED_ALLOW 가 비어 있습니다 "
                "(IP 위조로 접근통제가 뚫립니다)."); fails += 1
        if os.environ.get("BOKGUON_SEED_DEMO", "0") != "0":
            bad("BOKGUON_SEED_DEMO 가 0 이 아닙니다. 운영에 데모 데이터가 들어갑니다."); fails += 1

    # 업로드 디렉터리가 웹으로 노출되면 사고 현장 사진이 그대로 새어나간다
    updir = _upload_root()
    if os.path.abspath(updir).startswith(os.path.abspath(os.path.join(HERE, "static"))):
        bad(f"업로드 디렉터리가 static/ 하위입니다({updir}). 인증 없이 사진이 노출됩니다."); fails += 1

    # 5) 백업 디렉터리
    #  ⚠ [라운드123] cmd_backup 과 같은 규칙(_backup_dir())을 쓴다 — 격리된 DB_PATH 로
    #    점검을 돌리면서 여기만 따로 진짜 운영 backups/ 를 보면, 점검 결과가
    #    지금 실제로 검사 중인 DB 와 무관한 엉뚱한 폴더를 두고 말하게 된다.
    bdir = _backup_dir()
    if os.path.isdir(bdir):
        #  ⚠ **개수는 백업이 살아 있다는 증거가 아니다.** 반년 전 파일 30개가
        #    쌓여 있어도 이 검사는 초록이었다. 크론이 조용히 멈춘 뒤 복구하려고
        #    열어 보는 순간에야 안다 — 그때는 늦다.
        #    ⚠ 리눅스는 backup.sh 가 gzip 으로 **.db.gz** 를 남긴다. `.db` 만 세면
        #    정상 운영 중인 서버에서 영원히 '0개'가 뜬다(상시 오탐 → 신호 마모).
        import time as _t
        _bk = [f for f in os.listdir(bdir) if f.endswith(".db") or f.endswith(".db.gz")]
        _newest, _age_h, _sz = None, None, 0
        for f in _bk:
            try:
                st = os.stat(os.path.join(bdir, f))
            except OSError:
                continue
            if _newest is None or st.st_mtime > _newest[1]:
                _newest, _age_h, _sz = (f, st.st_mtime), (_t.time() - st.st_mtime) / 3600.0, st.st_size
        if not _bk:
            warn(f"백업 디렉터리 {bdir} — 백업본이 없습니다."); warns += 1
        elif _age_h is None or _age_h > 26:
            warn(f"백업 {len(_bk)}개가 있지만 **가장 최근 것이 "
                 f"{int(_age_h or 0)}시간 전**입니다 ({_newest[0]}). "
                 f"일일 백업이 멈춰 있습니다 — deploy/일일백업.bat 예약을 확인하세요."); warns += 1
        elif _sz < 100 * 1024:
            warn(f"최근 백업 {_newest[0]} 이 {_sz:,}바이트로 너무 작습니다 — "
                 f"백업이 중간에 끊겼을 수 있습니다."); warns += 1
        else:
            ok(f"백업 {len(_bk)}개 · 최근 {_newest[0]} ({int(_age_h)}시간 전, {_sz//1024:,}KB)")
    else:
        warn(f"백업 디렉터리가 없습니다 — python manage.py backup 을 한 번 실행하고 크론에 등록하세요."); warns += 1

    # 5-1) 사진(uploads) 백업 — DB 백업과 별도로 돈다(cmd_backup 은 DB만 뜬다)
    #  ⚠ 시공·하자 증빙사진은 분쟁·보증의 근거인데, 이 백업이 도는지 보는 검사가
    #    이제까지 전 코드베이스에 하나도 없었다 — DB 백업만 초록이면 배포 가능으로
    #    떴다. bootstrap.sh 는 rsync, windows_setup.ps1 은 robocopy 로 매일 뜬다.
    def _newest_mtime(root):
        #  ⚠⚠ [라운드121] 형제 함수 _orphan_photo_files() 는 _trash 를 뺀다(정리를
        #    할수록 경고가 커지는 걸 막으려고) — 여기는 그 예외가 없었다.
        #    prune-orphans/go-live 가 파일을 _trash 로 옮기며 os.utime(now) 로
        #    mtime 을 "지금"으로 찍는데(라운드110 — 30일 보관판정을 살리려는
        #    의도된 동작), 그 방금 찍힌 시각이 여기서 "원본의 최신 사진"으로
        #    잘못 잡혀, 실제로는 뒤처지지 않은 백업을 "뒤처졌다"고 오탐한다.
        #    정리할 때마다 뜨는 가짜 경보는 진짜 사고가 났을 때 무시당한다.
        _trash = os.path.normcase(os.path.join(root, "_trash"))
        latest, n = None, 0
        for _dp, _dirs, _fs in os.walk(root):
            if os.path.normcase(_dp).startswith(_trash):
                continue
            for _f in _fs:
                n += 1
                try:
                    m = os.stat(os.path.join(_dp, _f)).st_mtime
                except OSError:
                    continue
                if latest is None or m > latest:
                    latest = m
        return latest, n
    if os.path.isdir(updir):
        import time as _t2
        _src_new, _src_n = _newest_mtime(updir)
        if _src_n == 0:
            ok("업로드 사진 없음 — 백업 대상 없음")
        else:
            _photobk = os.path.join(bdir, "uploads")
            if not os.path.isdir(_photobk):
                warn(f"사진 백업 디렉터리가 없습니다({_photobk}) — 원본 {_src_n}개가 "
                     f"백업 없이 있습니다. windows_setup.ps1(윈도)/bootstrap.sh(리눅스)의 "
                     f"사진 백업 예약을 확인하세요."); warns += 1
            else:
                _bk_new, _bk_n = _newest_mtime(_photobk)
                if _bk_n == 0:
                    warn(f"사진 백업 디렉터리가 비어 있습니다({_photobk}) — "
                         f"원본 {_src_n}개가 백업되지 않았습니다."); warns += 1
                elif _bk_new is None or (_src_new - _bk_new) / 3600.0 > 48:
                    _gap_h = int((_t2.time() - (_bk_new or 0)) / 3600.0)
                    warn(f"사진 백업이 뒤처져 있습니다 — 원본에는 백업본보다 최근 파일이 "
                         f"있습니다(백업 최신본 {_gap_h}시간 전). 예약이 걸려 있는지 "
                         f"확인하세요."); warns += 1
                else:
                    ok(f"사진 백업 {_bk_n}개 · 원본과 보조를 맞추고 있음")

    #  ★ **자리표시자를 '기재됨'으로 읽지 않는다.**
    #    legal_docs 의 PENDING 은 값이 **비었을 때만** 잡으므로,
    #    DEPLOY.md 의 예시 블록을 그대로 붙여넣어 "○○클라우드" 가 들어가면
    #    법정 고지가 거짓인 채로 점검은 초록이 된다(전자상거래법 표시의무).
    try:
        import json as _json
        _ci = os.path.join(HERE, "data", "company_info.json")
        if os.path.exists(_ci):
            with open(_ci, encoding="utf-8") as f:
                _cd = _json.load(f)
            _PH = ("○", "０", "OO클라우드", "O월 O일", "XX", "㈜㈜", "예시", "샘플", "TBD")
            _hit = [f"{k}={v}" for k, v in _cd.items()
                    if isinstance(v, str) and any(t in v for t in _PH)]
            if _hit:
                bad("법정 고지에 **자리표시자가 그대로** 남아 있습니다: "
                    + " · ".join(_hit[:3])
                    + "  → python manage.py set-info <키> \"실제 값\""); fails += 1
    except Exception as e:
        #  ⚠⚠ [라운드584] 여기 있던 `except Exception: pass` 는 [라운드583]이 바로
        #    위 3-2 절("외부 공개 주소")에서 고친 것과 똑같은 결함이었다 — 파일이
        #    있는데 못 읽으면(깨진 JSON·경합 중 삭제·쓰기 도중 잠금 등) 자리표시자
        #    점검 자체가 조용히 건너뛰어져 "문제없음"과 구별되지 않는다. legal_docs.py
        #    의 _load_info() 도 [라운드121]에서 같은 이유로 이미 warning 을 남기도록
        #    고쳐졌다 — 이 자리는 그 파일이 세운 관례("확인 불가는 통과가 아니다")를
        #    같은 함수 안에서마저 따르지 않고 있었다. 형제 관례(574행 3-2 절의 except)
        #    를 그대로 따른다.
        warn(f"법정 고지 자리표시자 점검을 하지 못했습니다 — "
             f"{type(e).__name__}: {e}"); warns += 1

    # 6) [B4] 입찰 마감 자동화가 실제로 돌 수 있는 상태인가
    #    이 기능의 실패는 전부 "아무 일도 안 일어남"으로만 보인다. 그래서 여기서 미리 캔다.
    try:
        conn = DB.get_db()
        n_null = conn.execute(
            "SELECT COUNT(*) FROM auctions WHERE status='진행' AND deadline IS NULL").fetchone()[0]
        if n_null:
            warn(f"마감시각이 없는 진행 경매 {n_null}건 — 이 공고들은 영원히 마감되지 않습니다. "
                 f"python manage.py migrate 로 채우세요."); warns += 1
        else:
            ok("진행 중인 경매 모두 마감시각 보유")

        #  ⚠ 'auction_sweep' 을 보면 안 된다 — 그 값은 **관리자가 대시보드를 열기만 해도**
        #    갱신된다(웹 폴백). 예약이 주말 내내 안 돌아도 초록으로 보였다.
        #    'cli_sweep' 은 manage.py sweep 만 남기는 표식이라 예약 실행을 진짜로 증명한다.
        lock = conn.execute(
            "SELECT last_run_at FROM job_locks WHERE name IN ('cli_sweep','auction_sweep')"
            " ORDER BY CASE name WHEN 'cli_sweep' THEN 0 ELSE 1 END LIMIT 1").fetchone()
        if not lock:
            warn("마감 점검 잠금 행이 없습니다 — python manage.py migrate 를 실행하세요."); warns += 1
        elif not lock[0] or str(lock[0]).startswith("1970"):
            warn("예약 실행(sweep)이 한 번도 돌지 않았습니다 — 경매 마감·출동 기한·"
                 "완료보고 독촉·문자 실발송이 전부 멈춥니다. "
                 "리눅스는 /etc/cron.d/bokguon, 윈도는 복구온_예약실행_등록.ps1 을 확인하세요."); warns += 1
        else:
            gap = conn.execute(
                "SELECT CAST((julianday(datetime('now','+9 hours')) - julianday(?)) * 1440 AS INT)",
                (lock[0],)).fetchone()[0]
            if gap is not None and gap > 30:
                warn(f"마감 점검이 {gap}분째 실행되지 않았습니다 — 예약이 걸려 있는지 확인하세요."); warns += 1
            else:
                ok(f"마감 점검 정상 — 마지막 실행 {lock[0]}")

        #  ⚠ 개인정보 파기(prune-personal)도 같은 함정이 있다 — "코드는 다 있는데
        #    예약이 안 걸려 있어 아무 일도 안 일어난다." 처리방침에 공개로 약속한
        #    보유기간(문의 1년·계좌 퇴출시·피해자 하자담보 만료)을 실제로 지키려면
        #    이 예약이 매주 돌아야 한다 — sweep 과 달리 실패해도 화면에 아무 증상이
        #    안 남으므로(그냥 안 지워질 뿐) 여기서 미리 캐지 않으면 아무도 모른다.
        plock = conn.execute(
            "SELECT last_run_at FROM job_locks WHERE name='prune_personal'").fetchone()
        if not plock or not plock[0]:
            warn("개인정보 파기(prune-personal)가 한 번도 실행되지 않았습니다 — "
                 "처리방침에 약속한 보유기간이 지켜지지 않습니다. "
                 "리눅스는 /etc/cron.d/bokguon, 윈도는 windows_setup.ps1 을 확인하세요."); warns += 1
        else:
            pgap = conn.execute(
                "SELECT CAST((julianday(datetime('now','+9 hours')) - julianday(?)) AS INT)",
                (plock[0],)).fetchone()[0]
            if pgap is not None and pgap > 10:
                warn(f"개인정보 파기가 {pgap}일째 실행되지 않았습니다(주 1회 예정) — "
                     f"예약이 걸려 있는지 확인하세요."); warns += 1
            else:
                ok(f"개인정보 파기 예약 정상 — 마지막 실행 {plock[0]}")

        #  ⚠ 접속기록 파기(prune-logs)도 같은 법정 의무(§21)·같은 주기(주 1회)의
        #    형제 예약이다 — 바로 위와 같은 이유로 여기서도 정지를 미리 캔다.
        llock = conn.execute(
            "SELECT last_run_at FROM job_locks WHERE name='prune_logs'").fetchone()
        if not llock or not llock[0]:
            warn("접속기록 파기(prune-logs)가 한 번도 실행되지 않았습니다 — "
                 "보관기간이 지난 접속기록이 계속 쌓입니다. "
                 "리눅스는 /etc/cron.d/bokguon, 윈도는 windows_setup.ps1 을 확인하세요."); warns += 1
        else:
            lgap = conn.execute(
                "SELECT CAST((julianday(datetime('now','+9 hours')) - julianday(?)) AS INT)",
                (llock[0],)).fetchone()[0]
            if lgap is not None and lgap > 10:
                warn(f"접속기록 파기가 {lgap}일째 실행되지 않았습니다(주 1회 예정) — "
                     f"예약이 걸려 있는지 확인하세요."); warns += 1
            else:
                ok(f"접속기록 파기 예약 정상 — 마지막 실행 {llock[0]}")

        #  ⚠⚠ 시계가 어긋나면 마감이 통째로 어긋난다 — **비교 없이 나란히 보여주기만
        #    하면** 사람이 매번 암산으로 두 시각을 맞춰 봐야 하고, 실제로는 아무도
        #    그렇게 안 해서 여기가 늘 초록이었다(진짜 위험한 실패 방식: 검사가
        #    있다는 사실 자체가 안심을 준다). 서버 시간대가 KST 가 아니면(UTC
        #    컨테이너 등) 하자 기한(app.py due_date)·진행조회 링크 만료·정산
        #    월 판정이 전부 이 어긋남만큼 조용히 밀린다 — 그러니 직접 비교한다.
        kst = conn.execute("SELECT datetime('now','+9 hours')").fetchone()[0]
        os_now = datetime.now()
        try:
            _kst_dt = datetime.strptime(kst, "%Y-%m-%d %H:%M:%S")
            _drift = abs((os_now - _kst_dt).total_seconds())
        except ValueError:
            _drift = None
        if _drift is None:
            warn(f"DB 기준 시각(KST) {kst} 을 OS 시각과 비교하지 못했습니다."); warns += 1
        elif _drift > 120:
            warn(f"DB 기준 시각(KST) {kst} 과 OS 시각 "
                 f"{os_now.strftime('%Y-%m-%d %H:%M:%S')} 이 {int(_drift)}초 어긋납니다 — "
                 f"서버 시간대가 KST(Asia/Seoul)가 아닐 수 있습니다. 리눅스는 "
                 f"`timedatectl set-timezone Asia/Seoul`, 윈도는 제어판의 시간대를 "
                 f"확인하세요."); warns += 1
        else:
            ok(f"DB 기준 시각(KST) {kst}  ·  OS 시각 {os_now.strftime('%Y-%m-%d %H:%M:%S')}")
        conn.close()
    except Exception as e:
        warn(f"마감 자동화 점검을 하지 못했습니다: {e}"); warns += 1

    print("─" * 62)
    if fails:
        print(f"\033[91m배포 불가 — 반드시 고쳐야 할 항목 {fails}개\033[0m" + (f", 권고 {warns}개" if warns else ""))
        return 1
    print(f"\033[92m배포 가능\033[0m" + (f" — 권고 사항 {warns}개" if warns else ""))
    return 0


# ══════════════════════════════════════════════════════════════
#  init / migrate
# ══════════════════════════════════════════════════════════════
def cmd_init(argv):
    head("DB 초기화 (기존 데이터 보존)")
    seed = "--with-demo" in argv
    DB.init_db(seed_demo=seed if seed else None, verbose=True)
    ok(f"완료 — {DB.DB_PATH}")


def cmd_migrate(argv):
    head("스키마 마이그레이션")
    conn = DB.get_db()
    applied = DB.migrate(conn, verbose=True)
    conn.close()
    ok(f"추가된 컬럼 {len(applied)}개" if applied else "변경 없음 (이미 최신)")


# ══════════════════════════════════════════════════════════════
#  계정
# ══════════════════════════════════════════════════════════════
def _arg(argv, flag, default=""):
    return argv[argv.index(flag) + 1] if flag in argv and argv.index(flag) + 1 < len(argv) else default


def cmd_create_admin(argv):
    if not argv:
        bad("사용법: python manage.py create-admin <아이디> [--name 이름] [--role 역할]"); return 1
    #  ⚠⚠ [라운드176] 웹 경로(api_admin_create, app.py:1549)는 소문자 강제 +
    #    형식검증을 이미 하는데, 이 CLI 경로만 argv 를 그대로 저장했다 — 로그인
    #    (app.py:2603)은 입력을 항상 소문자로 맞춰 비교하므로, 여기서 대문자가
    #    섞인 아이디로 계정을 만들면 **그 계정은 만들어진 순간부터 웹으로 영영
    #    로그인할 수 없다**(비밀번호 오류처럼 보여 원인을 알 방법이 없다).
    #    형제 명령(create-insurer, 아래)이 이미 쓰는 규칙을 그대로 맞춘다.
    username = argv[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9_-]{4,20}", username):
        bad(f"아이디는 영문 소문자·숫자·-·_ 4~20자로 정해 주세요(받은 값: {argv[0]}). "
            f"형식이 안 맞으면 계정은 만들어져도 웹으로 로그인할 수 없습니다.")
        return 1
    name = _arg(argv, "--name", username)
    #  ⚠ 기본값이 '운영관리자'였는데 **그런 등급은 없다.** app.py 의
    #    ROLE_RANK = {최고관리자:3, 중간관리자:2, 하위관리자:1} 에 없는 값이라
    #    _admin_rank() 가 0 을 돌려주고, 그 계정은 로그인은 되는데
    #    @require_role 이 걸린 모든 화면·기능에서 막힌다(첫날 그대로 밟는다).
    role = _arg(argv, "--role", "중간관리자")
    if role not in ("최고관리자", "중간관리자", "하위관리자"):
        bad(f"등급은 최고관리자 · 중간관리자 · 하위관리자 중 하나여야 합니다(받은 값: {role}). "
            f"목록에 없는 값을 넣으면 아무 권한도 없는 계정이 만들어집니다.")
        return 1
    pw = gen_password()
    conn = DB.get_db()
    if conn.execute("SELECT 1 FROM admins WHERE username=?", (username,)).fetchone():
        bad(f"이미 존재하는 아이디입니다: {username}"); conn.close(); return 1
    conn.execute("""INSERT INTO admins(username,password_hash,name,role,created_at,must_change_pw)
                    VALUES(?,?,?,?,?,1)""", (username, DB.hash_pw(pw), name, role, DB.now()))
    DB.log(conn, "manage.py", "관리자 계정 생성", f"{username} ({role})")
    conn.commit(); conn.close()
    head("관리자 계정 생성 완료")
    print(f"  아이디   : {username}")
    print(f"  임시 비번 : \033[1m{pw}\033[0m")
    print(f"  이름/역할 : {name} / {role}")
    warn("이 비밀번호는 다시 볼 수 없습니다. 안전한 경로로 전달하고, 최초 로그인 시 변경하도록 하세요.")


def cmd_create_insurer(argv):
    if len(argv) < 2:
        bad("사용법: python manage.py create-insurer <기관명> <로그인ID> [수수료율%]"); return 1
    name, login_id = argv[0], argv[1].strip().lower()   # 로그인은 소문자 비교 — 저장도 소문자로
    # 구 fee_rate 컬럼은 건드리지 않는다(NULL 유지). 기준은 fee_rate_bp 하나뿐이다.
    try:
        if len(argv) > 2:
            #  ⚠⚠ [라운드121] cmd_set_fee 와 같은 결함 — inf 는 OverflowError 로
            #    이 except 를 피해 그대로 죽었다. math.isfinite() 로 막는다.
            _f = float(argv[2])
            if not math.isfinite(_f):
                raise ValueError("finite 아님")
            bp = int(round(_f * 100))
        else:
            bp = 1000
    except ValueError:
        bad("수수료율은 숫자로 입력하세요. 예: 9  또는  9.5"); return 1
    if not (0 <= bp <= 10000):
        bad("수수료율은 0~100% 사이여야 합니다."); return 1
    pw = gen_password()
    conn = DB.get_db()
    if conn.execute("SELECT 1 FROM insurers WHERE login_id=?", (login_id,)).fetchone():
        bad(f"이미 존재하는 로그인ID 입니다: {login_id}"); conn.close(); return 1
    #  ⚠ fee_rate 를 NULL 로 명시한다. 생략하면 DEFAULT 10 이 들어가고, 다음 기동
    #    마이그레이션이 그 값으로 fee_rate_bp 를 덮어써 계약 요율이 10% 로 원복된다.
    conn.execute("""INSERT INTO insurers(name,login_id,password_hash,created_at,
                                         must_change_pw,fee_rate_bp,fee_rate)
                    VALUES(?,?,?,?,1,?,NULL)""",
                 (name, login_id, DB.hash_pw(pw), DB.now(), bp))
    DB.log(conn, "manage.py", "보험사 계정 생성", f"{name} / {login_id} / 수수료율 {bp/100:g}%")
    conn.commit(); conn.close()
    head("보험사 계정 생성 완료")
    print(f"  기관명   : {name}")
    print(f"  아이디   : {login_id}")
    print(f"  수수료율 : {bp/100:g}%")
    print(f"  임시 비번 : \033[1m{pw}\033[0m")
    warn("최초 로그인 시 비밀번호를 변경하도록 안내하세요.")


def cmd_sweep(argv):
    """입찰 마감 점검을 한 번 돌린다. 예약 실행(작업 스케줄러·cron)이 이 명령을 부른다.

    --dry-run : 아무것도 바꾸지 않고 대상만 센다(마이그레이션 직후 영향 범위 확인용)
    """
    import app as A
    dry = "--dry-run" in argv
    head("입찰 마감 점검" + (" (미리보기)" if dry else ""))
    conn = DB.get_db()
    #  ⚠ 전부 여기서 초기화한다. 하나라도 빠지면 --dry-run(아래 블록을 통째로
    #    건너뛴다)에서 UnboundLocalError 로 죽어 미리보기 수치를 한 줄도 못 찍는다.
    nobid, overdue, rem, snd, appr, dsp, whr, war = 0, 0, {}, {}, {}, {}, 0, 0
    #  ⚠⚠ [라운드557] res 도 실패 대비 기본값이 필요하다 — 바로 아래 except 가
    #    A.sweep_auctions() 자신의 실패(예: 락 경합이 busy_timeout 을 넘김)까지
    #    잡는데, 그러면 res 대입이 아예 안 일어나 맨 아래 res["scanned"] 참조가
    #    UnboundLocalError 로 또 죽어 방금 남긴 실패 로그·메시지까지 함께 지운다.
    res = {"scanned": 0, "closed": 0, "failed": 0, "reauction_closed": 0, "skipped": 0}
    sweep_err = None
    try:
        res = A.sweep_auctions(conn, dry_run=dry, force=True)
        if not dry:
            # 완료보고 지연 감시·검수 리마인드도 같은 예약 실행에 태운다.
            #  (설정값만 저장되고 아무 일도 안 하던 것들 — 여기서 실제로 돈다)
            nobid = A.sweep_no_bid_alert(conn)
            overdue = A.sweep_report_overdue(conn)
            rem = A.sweep_review_reminders(conn)
            #  하자보증 만료 임박·당일 — 예전엔 화면(달력)을 열어야만 보였다.
            war = A.sweep_warranty_expiry(conn)
            #  돈이 실제로 멈추는 곳 — 보험사 완료 승인. 사람이 어드민을 안 열어도 돌아야 한다.
            appr = A.sweep_approval_overdue(conn)
            #  ★ 출동 기한 점검 — 이게 빠져 있었다.
            #    협력사가 '수락'만 하고 현장에 안 가면, 사람이 어드민에서 버튼을 누르기
            #    전까지 그 사건은 영원히 '수배됨'에 멈춘다(다음 회차 재수배도, 회차 상한
            #    도달 시 '수배실패' 전환도 일어나지 않는다). dispatch.py 주석이 그대로
            #    예언하고 있던 교착이다.
            import dispatch as DP
            dsp = DP.sweep_dispatches(conn, notify=A._dispatch_notify(conn))
            snd = A.sweep_send_notifications(conn)   # 팝빌 켜져 있을 때만 실발송
            #  ★ 실패한 보험사 웹훅 재전송 — 종전에는 한 번 쏘고 끝이라,
            #    수신 서버가 잠깐 죽으면 그 사건이 보험사 전산에 영영 안 들어갔다.
            whr = A.sweep_webhook_retries(conn)
            #  ★ 예약 실행이 실제로 돌았다는 **별도 표식**.
            #    종전에는 경매 스윕 시각만 봤는데, 그 값은 사람이 포털을 열기만 해도
            #    갱신된다 — 주말 내내 예약이 안 돌아도 대시보드는 초록이었다.
            conn.execute(
                "INSERT INTO job_locks(name, last_run_at) VALUES('cli_sweep', ?) "
                " ON CONFLICT(name) DO UPDATE SET last_run_at=excluded.last_run_at",
                (DB.now(),))
            conn.commit()
    except Exception as e:
        #  ⚠⚠ [라운드557] 형제(_sweep_if_due, app.py 라운드536)는 자신이 곁들여
        #    도는 같은 배치를 이미 이렇게 감싸 로그를 남기는데, **예약 실행의
        #    진짜 진입점**인 이 함수만 감싸지 않았다 — 무입찰경보~웹훅재전송
        #    7종 중 하나가 예외를 던지면(dispatch.sweep_dispatches 는 락 경합
        #    등으로 실패하면 자기 리스를 놓아준 뒤 **의도적으로 다시 던진다**,
        #    dispatch.py 961행) main() 밖까지 그대로 새어 나갔다. 작업 스케줄러
        #    등록 스크립트(복구온_예약실행_등록.ps1)는 콘솔 없는 pythonw.exe 를
        #    표준출력 리다이렉트 없이 부르므로 그 트레이스백은 **어디에도 남지
        #    않고 사라진다.** cli_sweep 마커도 이번 회차엔 못 쓰므로 대시보드
        #    배지는 30분 뒤 결국 적색이 되지만(그 자체는 의도된 설계 — 위
        #    "예약 실행이 실제로 돌았다는 별도 표식" 주석 참고), '멈췄다'는
        #    사실만 보일 뿐 **왜** 멈췄는지는 bokguon.log 를 아무리 grep 해도
        #    0건이었다. 형제와 같은 처방 — 로그를 남기고(이미 커밋된 앞선
        #    스윕은 되돌리지 않는다), 종료코드도 실패로 보고한다(작업
        #    스케줄러 LastTaskResult·사람이 직접 돌릴 때 둘 다 "종료코드 0"
        #    만 보고 정상이라 오판하지 않도록).
        sweep_err = e
        A.app.logger.exception(
            "cmd_sweep 배치 실패 — 무입찰경보~웹훅재전송 중 하나가 예외를 던져 "
            "이후 항목과 cli_sweep 기록이 이번 회차에서 빠졌습니다")
        try:
            conn.rollback()
        except sqlite3.Error:
            pass
    finally:
        conn.close()
    if sweep_err is not None:
        bad(f"스윕 배치 도중 오류로 중단됨(부분 처리) — {sweep_err}")
        warn("bokguon.log 에 전체 트레이스백을 남겼습니다. cli_sweep 기록도 이번 "
             "회차엔 못 남아 대시보드 배지가 계속 적색일 수 있습니다.")
    #  ⚠⚠ [라운드188] 형제 스윕(overdue·rem·dsp·appr·snd·whr·war)은 전부 여기서
    #    콘솔에 보고하는데 nobid 만 반환값을 변수에만 담고 어디에도 안 찍었다 —
    #    무입찰 경보 자체(실제 알림 발송)는 정상 동작하지만, 예약 실행 로그만
    #    보고는 운영자는 이 스윕이 도는지 조용히 죽었는지 알 길이 없었다.
    if nobid:
        ok(f"무입찰 경보 {nobid}건 발송")
    if overdue:
        ok(f"완료보고 지연 표시 {overdue}건")
    if rem.get("photo") or rem.get("payout"):
        ok(f"검수 리마인드 — 사진 {rem.get('photo', 0)}건 · 지급 {rem.get('payout', 0)}건")
    if isinstance(dsp, dict) and (dsp.get("expired") or dsp.get("reopened") or dsp.get("gaveup")):
        ok(f"출동 기한 점검 — 기한초과 {dsp.get('expired', 0)}건 · "
           f"재수배 {dsp.get('reopened', 0)}건 · 수배실패 {dsp.get('gaveup', 0)}건")
    if appr.get("sent"):
        ok(f"완료승인 자동 독촉 — {appr['sent']}건 발송 (건너뜀 {appr.get('skipped', 0)})")
    if appr.get("award"):
        ok(f"낙찰승인 자동 독촉 — {appr['award']}건 발송")
    if snd.get("sent") or snd.get("failed"):
        ok(f"알림 실발송 — 발송 {snd.get('sent', 0)}건 · 실패 {snd.get('failed', 0)}건")
    if whr:
        ok(f"웹훅 재전송 {whr}건")
    if war:
        ok(f"하자보증 만료 임박·당일 알림 {war}건")
    #  ⚠⚠ [라운드557] sweep_err 가 있으면 res 는 이번 회차를 끝까지 대표하지
    #    못한다(실패 시점 이전 값 그대로) — "마감할 공고가 없습니다" 같은
    #    완결 문구를 붙이지 않고, 종료코드만 실패로 보고하고 끝낸다.
    if sweep_err is not None:
        return 1
    if not res["scanned"]:
        ok("마감할 공고가 없습니다.")
        return 0
    ok(f"대상 {res['scanned']}건 — 마감 {res['closed']} · 무입찰 유찰 {res['failed']} "
       f"· 재경매 마감 {res['reauction_closed']} · 건너뜀 {res['skipped']}")
    if dry:
        warn("미리보기라 실제로는 아무것도 바뀌지 않았습니다.")
    return 0


def cmd_install_scheduler(argv):
    """마감 점검을 주기 실행하도록 등록한다(윈도=작업 스케줄러, 리눅스=cron).

    --remove : 등록 해제
    ⚠ 이걸 등록하지 않으면 마감 점검은 **관리자가 화면을 열 때만** 돈다.
      한밤중에 마감된 공고는 아침에 누가 들어올 때까지 열려 있게 된다.
    """
    remove = "--remove" in argv
    head("마감 점검 예약 " + ("해제" if remove else "등록"))
    py = sys.executable
    task = "복구온_경매마감"

    if os.name == "nt":
        #  ⚠⚠ [라운드679, 라운드680이 정정] round679는 "schtasks.exe가 항상 UTF-8을 낸다"고
        #    실측했다며 encoding="utf-8"을 넣었다. round680이 이 PC에서 재검증하니 정반대
        #    (cp949)였다 — 그런데 이어서 배터리(콘솔 없는 중첩 파이프 실행) 안에서 같은
        #    호출을 재실행해 보니 이번엔 거꾸로 영어 UI("Folder:"·"TaskName" 등)로 나오며
        #    그 경우엔 utf-8이 맞고 cp949가 깨졌다 — **schtasks.exe 자신의 UI 언어·인코딩이
        #    실행 맥락(콘솔 부착 여부 등)에 따라 실측 두 가지 모두로 갈린다**(원인 미확정,
        #    이 프로세스 트리 안에서 재현 가능하게 양쪽 다 나옴). 그래서 "어느 한쪽"을
        #    강제하는 접근 자체가 틀렸다 —
        #    text=True(고정 인코딩 하나만 시도, background reader thread가 실패하면 그 자리서
        #    죽어 stdout 전체가 None이 됨)를 아예 안 쓰고, **원시 바이트를 그대로 받아 메인
        #    스레드에서 직접** utf-8 먼저 시도 → 실패하면 cp949 → 그래도 실패하면 cp949+
        #    replace(최후 방어선)로 디코드한다. 이러면 어느 쪽 인코딩이 오든 크래시 없이
        #    항상 사람이 읽을 문자열을 얻는다.
        def _decode_schtasks(b):
            if b is None:
                return ""
            for enc in ("utf-8", "cp949"):
                try:
                    return b.decode(enc)
                except UnicodeDecodeError:
                    continue
            return b.decode("cp949", errors="replace")

        if remove:
            #  ⚠⚠ [라운드292] 결과를 안 보고 무조건 "해제했습니다"를 찍었다 —
            #    이미 해제됐거나 schtasks 자체가 막힌 환경(정책·권한)이면
            #    schtasks 는 예외 없이 실패 종료코드만 낸다(실측: 없는 작업
            #    이름으로 재현 — returncode 1). 운영자가 "꺼졌다"고 믿는데
            #    실제로는 계속 돌 수 있었다.
            r = subprocess.run(["schtasks", "/Delete", "/TN", task, "/F"],
                                capture_output=True)
            if r.returncode:
                bad(f"해제 실패(이미 없거나 권한 문제일 수 있습니다): "
                    f"{(_decode_schtasks(r.stderr) or _decode_schtasks(r.stdout)).strip()[:200]}")
                return 1
            ok("예약을 해제했습니다.")
            return 0
        #  ⚠⚠ [라운드292] python.exe 로 등록하면 5분마다 콘솔 창이 떴다
        #    사라진다 — 이 문제를 이미 겪어 실제 이 PC의 '복구온_경매마감'은
        #    pythonw.exe 로 손으로 바로잡혀 있었다(schtasks /Query /XML 로
        #    직접 확인: Command 가 이미 pythonw.exe, .bat 자체가 없음). 그
        #    수동 조치는 이 코드에 전혀 반영돼 있지 않아서, 이 명령을
        #    다시 돌리면(재배포 등) 이미 고쳐진 운영 작업을 python.exe+
        #    .bat 방식으로 조용히 되돌렸을 것이다.
        #    옛 .bat 경유 방식의 근거("한글 경로가 bat 없인 조용히
        #    실패한다")는 os.system() 문자열 조립 시절 얘기였다 — 지금은
        #    subprocess.run([...]) 리스트 인자라 셸 파싱을 안 거친다.
        #    실측(임시 작업명으로 등록→XML 로 확인→즉시 삭제)해 보니 한글
        #    경로를 절대경로 인자로 그대로 넘겨도 정상 등록됐다 — .bat·cd
        #    없이 pythonw.exe 를 manage.py 절대경로와 함께 직접 등록한다
        #    (manage.py 자신도 HERE=os.path.dirname(os.path.abspath(
        #    __file__)) 로만 경로를 잡고 os.getcwd() 에 기대지 않으므로
        #    작업 디렉터리 지정 자체가 애초에 불필요하다).
        pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
        if not os.path.exists(pyw):
            pyw = py          # 이 PC 밖의 특수한 파이썬 배포판 대비 폴백
        manage_path = os.path.join(HERE, "manage.py")
        old_bat = os.path.join(HERE, "_마감점검.bat")
        if os.path.exists(old_bat):
            try:
                os.remove(old_bat)          # 옛 방식의 잔재 — 더는 안 쓴다
            except OSError:
                pass
        r = subprocess.run(["schtasks", "/Create", "/SC", "MINUTE", "/MO", "5",
                            "/TN", task, "/TR", f'"{pyw}" "{manage_path}" sweep', "/F"],
                           capture_output=True)
        if r.returncode:
            bad(f"등록 실패: {(_decode_schtasks(r.stderr) or _decode_schtasks(r.stdout)).strip()[:200]}")
            return 1
        # 등록됐다고 믿지 말고 확인한다.
        q = subprocess.run(["schtasks", "/Query", "/TN", task], capture_output=True)
        if q.returncode:
            bad("등록 명령은 성공했으나 조회에 실패했습니다. 작업 스케줄러에서 직접 확인하세요.")
            return 1
        ok(f"5분마다 실행하도록 등록했습니다 — 작업 이름 '{task}'")
        ok(f"실행: {pyw} {manage_path} sweep")
        return 0

    # 리눅스 — crontab 한 줄
    line = f"*/5 * * * * cd {HERE} && {py} manage.py sweep >> {HERE}/logs/sweep.log 2>&1"
    if remove:
        warn("crontab -e 로 아래 줄을 지우세요:")
        print("  " + line)
        return 0
    ok("crontab 에 아래 한 줄을 추가하세요 (crontab -e):")
    print()
    print("  " + line)
    print()
    warn("등록 후 'crontab -l' 로 확인하세요.")
    return 0


def cmd_set_fee(argv):
    """보험사별 수수료율 변경.

    이게 없어서 유일한 변경 수단이 직접 SQL 이었고, 그렇게 고친 값은
    기동 시 백필에 덮여 되돌아갔다(이제 백필은 1회성이다).
    """
    if len(argv) < 2:
        bad("사용법: python manage.py set-fee <기관명 또는 로그인ID> <수수료율%>")
        print("  예: python manage.py set-fee 공제조합 9")
        return 1
    key, raw = argv[0], argv[1]
    try:
        #  ⚠⚠ [라운드121] float("inf") 는 예외 없이 성공하고, round(inf*100) 은
        #    OverflowError(ValueError 의 하위클래스가 아니다)를 던져 이 except 를
        #    피해 그대로 죽었다(스택트레이스 노출). nan 은 반대로 round() 단계에서
        #    ValueError 라 정상 처리됐다 — 같은 방어가 입력값 따라 들쭉날쭉했다.
        #    repair_estimate.py:_validate() 가 이미 쓰는 math.isfinite() 로 통일한다.
        _f = float(raw)
        if not math.isfinite(_f):
            raise ValueError("finite 아님")
        bp = int(round(_f * 100))
    except ValueError:
        bad("수수료율은 숫자로 입력하세요. 예: 9  또는  9.5"); return 1
    if not (0 <= bp <= 10000):
        bad("수수료율은 0~100% 사이여야 합니다."); return 1
    conn = DB.get_db()
    r = conn.execute("SELECT id,name,fee_rate_bp FROM insurers WHERE name=? OR login_id=?",
                     (key, key)).fetchone()
    if not r:
        bad(f"보험사를 찾을 수 없습니다: {key}")
        print("  등록된 기관:")
        for x in conn.execute("SELECT name,login_id FROM insurers ORDER BY name"):
            print(f"    · {x['name']}  ({x['login_id'] or '-'})")
        conn.close(); return 1
    conn.execute("UPDATE insurers SET fee_rate_bp=?, fee_rate=NULL WHERE id=?", (bp, r["id"]))
    DB.log(conn, "manage.py", "수수료율 변경",
           f"{r['name']} {(r['fee_rate_bp'] or 0)/100:g}% → {bp/100:g}%")
    conn.commit(); conn.close()
    head("수수료율 변경 완료")
    print(f"  {r['name']} : {(r['fee_rate_bp'] or 0)/100:g}%  →  \033[1m{bp/100:g}%\033[0m")
    warn("이미 만들어진 정산 행에는 소급되지 않습니다(생성 시점 요율로 확정).")


ROLE_TABLE = {"admin": ("admins", "username"), "partner": ("partners", "login_id"), "insurer": ("insurers", "login_id")}


def cmd_reset_pw(argv):
    if len(argv) < 2 or argv[0] not in ROLE_TABLE:
        bad("사용법: python manage.py reset-pw <admin|partner|insurer> <아이디>"); return 1
    table, col = ROLE_TABLE[argv[0]]
    #  ⚠⚠ [라운드166] partners/insurers.login_id 는 로그인·중복확인·생성(CLI)이
    #    전부 strip+lower 로 정규화해 소문자로만 저장한다(app.py:2670·2866,
    #    _login_id_taken 의 LOWER() 비교, cmd_create_insurer) — 이 명령만
    #    정규화 없이 = 비교에 그대로 넣어, 대문자로 치거나 앞뒤 공백이 붙은
    #    입력이면 계정이 분명히 있어도 "찾을 수 없습니다"로 조용히 실패했다.
    #    admin 은 계정생성 자체가 소문자만 허용하는 정규식이고 로그인도 대소문자
    #    구분이라 원래도 문제 없다 — strip 만 한다.
    ident = argv[1].strip().lower() if argv[0] in ("partner", "insurer") else argv[1].strip()
    pw = gen_password()
    conn = DB.get_db()
    cur = conn.execute(f"UPDATE {table} SET password_hash=?, must_change_pw=1 WHERE {col}=?",
                       (DB.hash_pw(pw), ident))
    if not cur.rowcount:
        bad(f"{table} 에서 {ident} 을(를) 찾을 수 없습니다."); conn.close(); return 1
    DB.log(conn, "manage.py", "비밀번호 재설정", f"{table}/{ident}")
    conn.commit(); conn.close()
    head("비밀번호 재설정 완료")
    print(f"  대상     : {table} / {ident}")
    print(f"  임시 비번 : \033[1m{pw}\033[0m")
    warn("최초 로그인 시 변경이 강제됩니다.")


# ══════════════════════════════════════════════════════════════
#  백업 / 복구
# ══════════════════════════════════════════════════════════════
def _backup_dir():
    """백업 출력 디렉터리 — BOKGUON_BACKUP_DIR 를 명시하지 않으면 **DB_PATH 기준**으로 정한다.

    ⚠⚠ [라운드123] cmd_go_live 가 안전장치로 부르는 cmd_backup([]) 이 DB 는 BOKGUON_DB_PATH
      로 격리해 놓고 백업 출력은 여기(예전엔 그냥 HERE/backups)로만 떨어졌다 — DB 격리와
      출력 격리가 서로 다른 신호에 의존해, 격리된 스크래치 DB 를 go-live 로 정리하는
      회귀테스트를 돌릴 때마다 **진짜 운영 backups/ 폴더**에 데모 픽스처가 새어 들어갔다.
      실측: 이 라운드 자신이 그렇게 남긴 487KB 짜리 데모 백업 6개가 실제로 발견됐고
      (case_no='R122-DEMO', partners=0), 그 mtime 이 정상 03:30 백업보다 새것이라
      backup_selfcheck.py 가 정상 백업 대신 그 조각을 "최신"으로 봤다(정리 완료).
      BOKGUON_DB_PATH 가 격리되면 백업도 같은 자리 밑으로 자동으로 따라가게 한다 —
      두 번째 환경변수를 기억해야만 안전한 구조를 없앤다.
    """
    explicit = os.environ.get("BOKGUON_BACKUP_DIR")
    if explicit:
        return explicit
    return os.path.join(os.path.dirname(os.path.abspath(DB.DB_PATH)), "backups")


def cmd_backup(argv):
    """SQLite 온라인 백업 API 사용.

    운영 중인 SQLite 파일을 cp 로 복사하면 쓰기 중인 페이지가 섞여 **손상된 백업**이 만들어질 수 있다.
    sqlite3 의 .backup 은 잠금을 존중하며 일관된 스냅샷을 뜬다. WAL 사용 시 특히 중요하다.
    """
    #  ⚠⚠ [라운드292] sqlite3.connect() 는 파일이 없으면 **빈 파일을 조용히
    #    만든다.** DB_PATH 오타·미초기화 상태에서 그대로 진행하면 그 빈
    #    파일에 대고 "SELECT ... FROM partners" 를 던져 OperationalError 로
    #    실패하는데, 그 실패가 아래 범용 except 로 떨어져 "디스크 여유
    #    공간과 권한을 확인하세요"라는 엉뚱한 안내를 냈다(실측: 진짜
    #    원인은 디스크·권한이 아니라 DB_PATH 가 초기화 안 된 것). 게다가
    #    실패해도 DB_PATH 자리에 그 빈 파일이 그대로 남는다 — 다음 실행이
    #    "DB가 이미 있다"고 오판할 여지도 만든다. 시도 자체를 하기 전에
    #    막아 원인을 정확히 말하고, 빈 파일이 생기는 것 자체를 막는다.
    if not os.path.exists(DB.DB_PATH):
        head("백업 실패")
        bad(f"DB 파일이 없습니다: {DB.DB_PATH}")
        print("  BOKGUON_DB_PATH 설정을 확인하거나, 먼저 'python manage.py init' 을 실행하세요.")
        return 1
    outdir = argv[0] if argv else _backup_dir()
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.now().strftime("%y%m%d_%H%M%S")
    dest = os.path.join(outdir, f"bokguon_{stamp}.db")

    # [MG-08] 최종 이름으로 곧장 쓰지 않는다.
    #   디스크가 차거나 도중에 죽으면 **반쪽짜리 파일이 정상 백업 이름을 달고** 남는다.
    #   그러면 보관 정리도 복원도 그걸 성한 백업으로 취급한다 — 정작 필요할 때 못 쓴다.
    #   `.part` 로 받아서 무결성까지 통과한 뒤에야 원자적으로 제 이름을 준다.
    part = dest + ".part"

    # [보안] 백업본에는 개인정보(성명·연락처·암호화된 계좌)가 그대로 들어 있다.
    #        파일을 만든 **뒤에** 권한을 좁히면 그 사이에 다른 사용자가 읽을 수 있는
    #        짧은 공백 구간이 생긴다. 빈 파일을 먼저 만들고 권한부터 좁힌 다음 채운다.
    fd = os.open(part, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    os.close(fd)
    if os.name == "nt":
        # Windows 는 POSIX 권한이 없어 icacls 로 상속을 끊는다.
        # ⚠ 이때 **실행 중인 계정 자신을 반드시 포함**해야 한다.
        #   Administrators·SYSTEM 만 남기면, 관리자 그룹이 아닌 서비스 계정으로 돌 때
        #   방금 만든 파일을 자기가 열지 못해 백업이 통째로 실패한다.
        #   (백업은 마지막 방어선이라 조용히 실패하면 안 된다)
        me = os.environ.get("USERNAME") or ""
        grants = ['"Administrators:(F)"', '"SYSTEM:(F)"']
        if me:
            grants.insert(0, f'"{me}:(F)"')
        rc = os.system(f'icacls "{part}" /inheritance:r /grant:r {" ".join(grants)} >nul 2>&1')
        if rc != 0:
            warn("파일 권한 제한에 실패했습니다. 백업 파일 접근 권한을 직접 확인하세요.")

    def _drop_part():
        try:
            os.remove(part)
        except OSError:
            pass

    # 실패하면 부분 파일을 반드시 치운다. 커넥션도 예외 경로에서 새지 않게 닫는다.
    try:
        src = dst = None
        try:
            src = sqlite3.connect(DB.DB_PATH)
            dst = sqlite3.connect(part)
            with dst:
                src.backup(dst)
        finally:
            for c in (dst, src):
                if c is not None:
                    try:
                        c.close()
                    except sqlite3.Error:
                        pass

        # 무결성 검증 — 이름을 주기 **전에** 한다. 통과 못 하면 아예 남기지 않는다.
        chk = sqlite3.connect(part)
        try:
            res = chk.execute("PRAGMA integrity_check").fetchone()[0]
            n = chk.execute("SELECT COUNT(*) FROM partners").fetchone()[0]
        finally:
            chk.close()

        if res != "ok":
            _drop_part()
            head("백업 실패")
            bad(f"무결성 검사 불통과: {res} — 손상된 백업을 남기지 않고 폐기했습니다.")
            return 1

        size = os.path.getsize(part)
        os.replace(part, dest)          # 원자적 — 이 순간부터 정상 백업이다
    except Exception as e:
        _drop_part()
        head("백업 실패")
        bad(f"{type(e).__name__}: {e}")
        print("  부분 파일은 삭제했습니다. 디스크 여유 공간과 권한을 확인하세요.")
        return 1

    head("백업 완료")
    print(f"  파일 : {dest}")
    print(f"  크기 : {size:,} bytes")
    ok(f"무결성 검사: {res} · 협력업체 {n}개 확인")

    # 이전 실행이 죽으면서 남긴 찌꺼기 정리
    for f in os.listdir(outdir):
        if f.startswith("bokguon_") and f.endswith(".db.part"):
            try:
                os.remove(os.path.join(outdir, f))
            except OSError:
                pass

    # 보관 기간 (기본 30일) 지난 백업 정리
    #  ⚠⚠ [라운드446] 바로 위 찌꺼기 정리 루프는 try/except OSError 로 감싸는데
    #    이 루프만 없었다 — 실측: 백신 실시간 검사·오프사이트 동기화 도구 등이
    #    하필 그 순간 백업 파일 하나를 물고 있으면(Windows에서 드물지 않은
    #    조건) os.remove() 가 PermissionError 를 던지고, 이 함수 전체가 그
    #    예외로 죽는다(오늘 백업 자체는 이미 1324행에서 끝나 있었는데도 "실패"
    #    로 기록됨). 게다가 같은 파일이 매일 같은 이유로 잠긴다면 그 뒤로
    #    보관기간 정리가 영구히 멈춰 30일 약속과 달리 백업이 무한정 쌓일 수
    #    있다. 형제 루프와 완전히 같은 관용구를 적용 — 파일 하나 실패는 그
    #    파일만 건너뛰고 나머지는 계속 정리한다.
    keep = int(os.environ.get("BOKGUON_BACKUP_KEEP_DAYS", "30"))
    cutoff = datetime.now() - timedelta(days=keep)
    removed = 0
    for f in os.listdir(outdir):
        p = os.path.join(outdir, f)
        if f.startswith("bokguon_") and f.endswith(".db") and datetime.fromtimestamp(os.path.getmtime(p)) < cutoff:
            try:
                os.remove(p); removed += 1
            except OSError:
                pass
    if removed:
        ok(f"{keep}일 지난 백업 {removed}개 삭제")
    return 0 if res == "ok" else 1


def cmd_restore(argv):
    if not argv:
        bad("사용법: python manage.py restore <백업파일>"); return 1
    src = argv[0]
    if not os.path.exists(src):
        bad(f"백업 파일이 없습니다: {src}"); return 1
    chk = sqlite3.connect(src)
    if chk.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        bad("백업 파일 무결성 검사 실패 — 복구를 중단합니다."); chk.close(); return 1
    chk.close()

    head("복구")
    show_db_target()

    #  ★ **서버가 돌고 있으면 멈춘다.** 문서에는 "서비스를 먼저 중지하세요" 라고
    #    적혀 있었지만 그건 부탁이지 확인이 아니었다. 리눅스에는 systemctl 안내가
    #    있는데 **Windows 운영 PC 에는 서버를 내리는 절차 자체가 없다** —
    #    감시자(외부접속_상시가동.ps1)가 30초마다 되살리기까지 한다.
    #    살아 있는 프로세스가 물고 있는 파일을 갈아 끼우면 그 세션이 쓰는 것은
    #    옛 DB 이고, 화면은 정상으로 보인다(가장 나쁜 실패다).
    _port = os.environ.get("BOKGUON_PORT", "8771")
    _alive = False
    try:
        import http.client as _hc
        _cx = _hc.HTTPConnection("127.0.0.1", int(_port), timeout=3)
        _cx.request("GET", "/healthz")
        _alive = _cx.getresponse().status < 500
        _cx.close()
    except OSError:
        _alive = False
    if _alive and "--force" not in argv:
        bad(f"서버가 127.0.0.1:{_port} 에서 **아직 돌고 있습니다** — 복구를 중단합니다.")
        print("  먼저 서버를 내리세요:")
        print("    · Windows : 복구온_외부공개_중지.bat 실행 후")
        print("                Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" |")
        print("                  Where-Object { $_.CommandLine -like '*serve_waitress*' } |")
        print("                  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }")
        print("                ⚠ 감시자를 먼저 멈추지 않으면 30초 뒤 다시 뜹니다.")
        print("    · 리눅스   : sudo systemctl stop bokguon")
        print("  (정말 이대로 진행해야 한다면 --force 를 붙이십시오 — 권장하지 않습니다)")
        return 1
    if _alive:
        warn("서버가 돌고 있는데 --force 로 진행합니다. 복구 후 반드시 재시작하세요.")

    warn("현재 DB 를 백업본으로 덮어씁니다.")
    if "--yes" not in argv:
        bad("확인을 위해 --yes 를 붙여 다시 실행하세요."); return 1
    # 현재 DB 를 먼저 보존.
    #  ⚠ `shutil.copy2` 로 본체 파일만 복사하면 안 된다. WAL 모드에서는 커밋된 트랜잭션이
    #     아직 `-wal` 에만 있을 수 있는데, 바로 아래에서 그 `-wal` 을 지운다.
    #     즉 되돌릴 마지막 수단인 이 사본에서 최근 작업이 조용히 사라진다.
    #     sqlite3 온라인 백업 API 는 WAL 내용까지 합쳐 완전한 한 파일로 떠 준다.
    keep = None
    if os.path.exists(DB.DB_PATH):
        keep = DB.DB_PATH + datetime.now().strftime(".before_restore_%y%m%d_%H%M%S")
        cur_src = cur_dst = None
        try:
            cur_src = sqlite3.connect(DB.DB_PATH)
            cur_dst = sqlite3.connect(keep)
            with cur_dst:
                cur_src.backup(cur_dst)
            ok(f"기존 DB 보존(WAL 포함) → {keep}")
        except sqlite3.Error as e:
            bad(f"기존 DB 보존 실패: {e} — 복구를 중단합니다.")
            return 1
        finally:
            for c in (cur_dst, cur_src):
                if c is not None:
                    try:
                        c.close()
                    except sqlite3.Error:
                        pass
    for suffix in ("-wal", "-shm"):
        p = DB.DB_PATH + suffix
        if os.path.exists(p):
            os.remove(p)

    def _keep_hint():
        if keep:
            print("  직전 DB 는 보존돼 있습니다 — 필요하면 되돌리세요:")
            print(f"    copy \"{keep}\" \"{DB.DB_PATH}\"" if os.name == "nt"
                  else f"    cp \"{keep}\" \"{DB.DB_PATH}\"")
        else:
            print("  복구 전에는 DB 파일이 없었습니다(신규 설치) — 되돌릴 이전 본은 없습니다.")

    #  ⚠⚠ [라운드342] 이 copy2 자체가 도중에 실패하면(디스크 꽉 참·백신 잠금
    #    등 — 바로 위 주석이 이미 재해복구는 이런 불안정한 환경에서 한다고
    #    지적함) 예전엔 여기서 예외가 그대로 새어나가 처리 안 된 트레이스백과
    #    함께 죽었다 — 실패 자체는 (조용하지 않고) 요란하게 드러나지만, 20줄
    #    아래 무결성검사 실패 분기가 이미 안내하는 "keep 에서 되돌리는 법"
    #    힌트를 못 보고 죽는다는 게 문제였다(keep 은 이미 안전하게 떠 있는데
    #    그 사실을 이 실패 경로에서만 못 알려줌). 같은 안내를 재사용한다.
    try:
        shutil.copy2(src, DB.DB_PATH)
    except OSError as e:
        bad(f"백업파일 복사 실패: {type(e).__name__}: {e} — {DB.DB_PATH} 가 불완전한 상태일 수 있습니다.")
        _keep_hint()
        return 1
    #  ⚠ **복사가 끝났다고 파일이 온전하다는 뜻은 아니다.** 백업(cmd_backup)은
    #    .part 로 받아 무결성 검사를 통과한 뒤에야 원자적으로 자리를 바꾸는데,
    #    여기는 원본 자리(DB.DB_PATH)로 바로 복사한다 — 재해복구는 원래 환경이
    #    불안정할 때 하는 일이라(디스크 꽉 참·백신 잠금·정전) 복사가 중간에
    #    끊길 수 있다. 그런데 이미 옛 DB 는 지웠으므로(-wal/-shm 삭제 + 덮어쓰기),
    #    확인 없이 "복구 완료" 라고만 말하면 깨진 DB 위에서 서비스가 재시작된다.
    _vc = None
    try:
        _vc = sqlite3.connect(DB.DB_PATH)
        _vok = _vc.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    except sqlite3.Error:
        #  ⚠ 검사 자체가 깨진 파일에서 예외를 던지면(진짜 SQLite 파일이 아닌 경우
        #    등) close() 까지 못 가고 커넥션이 열린 채 남는다 — 그러면 이 손상된
        #    파일을 지우거나 다시 시도하려 해도 윈도에서 "다른 프로세스가 사용
        #    중"으로 잠긴다. 실패 경로에서도 반드시 닫는다.
        _vok = False
    finally:
        if _vc is not None:
            try:
                _vc.close()
            except sqlite3.Error:
                pass
    if not _vok:
        bad(f"복구본 무결성 검사 실패 — {DB.DB_PATH} 가 손상됐을 수 있습니다.")
        _keep_hint()
        return 1
    #  ⚠⚠ [라운드446] 무결성 검사(PRAGMA integrity_check)는 "SQLite 파일로서
    #    멀쩡한가"만 본다 — "지금 이 .env 의 BOKGUON_ENC_KEY 로 이 DB 안의
    #    암호화된 계좌정보를 실제로 열 수 있는가"는 완전히 다른 질문이다.
    #    cmd_check()(위 246-265행)는 이미 이 왕복확인을 하는데, 정작 키가
    #    안 맞을 위험이 가장 큰 순간(다른 서버·다른 .env로 복구하는 바로 이
    #    시점)엔 아무도 그 검사를 부르지 않았다 — 실측: 다른 키로 암호화된
    #    백업을 복구하면 여기까지 전부 "정상"으로 통과하고, 계좌정보는
    #    crypto_util.decrypt()가 실패를 삼켜 조용히 빈 문자열이 된다(화면상
    #    "계좌 미등록"과 구분 불가) — 되돌릴 수 없는 데이터 손실인데 그
    #    사실을 알아챌 방법이 이 명령 안에는 없었다. 같은 검사를 여기서도
    #    한 번 더 돌린다(막지는 않는다 — 파일 복구 자체는 이미 끝났고,
    #    이건 그 결과에 대한 사후 경고일 뿐이다).
    try:
        import crypto_util as CRYPTO
        _rc = DB.get_db()
        _enc_row = _rc.execute(
            "SELECT id, bank_account_enc FROM partners "
            " WHERE bank_account_enc LIKE 'v1:%' LIMIT 1").fetchone()
        _rc.close()
        if _enc_row and not CRYPTO.decrypt(_enc_row["bank_account_enc"]):
            bad(f"암호화키 복호화 왕복 확인 실패(업체 #{_enc_row['id']}) — "
                "BOKGUON_ENC_KEY 가 이 백업을 암호화한 키와 다릅니다. "
                "무결성은 정상이지만 계좌정보는 이 키로 못 엽니다 — "
                "예전 .env 의 키를 옮겨 왔는지 다시 확인하세요.")
    except Exception:                                                # noqa: BLE001
        pass
    ok(f"복구 완료 ← {src} (무결성 검사 통과)")


# ══════════════════════════════════════════════════════════════
#  운영 잡무
# ══════════════════════════════════════════════════════════════
def cmd_prune_logs(argv):
    """보관 기간이 지난 접속기록 삭제.

    「개인정보의 안전성 확보조치 기준」 제8조는 **최소** 보관기간을 정한 것이고,
    개인정보 보호법 제21조는 목적 달성 후 **지체 없는 파기**를 요구한다.
    따라서 기간이 지난 기록은 남겨두지 말고 지워야 한다.

    [MG-09] 예전에는 삭제 직후 무조건 VACUUM 을 돌렸다. VACUUM 은 DB 전체를
    다시 쓰면서 **배타 잠금**을 잡아, 주 1회 새벽이라 해도 그동안 서비스가 멈춘다.
    게다가 잠금 경합으로 VACUUM 이 실패하면 명령 전체가 실패로 끝나서,
    **법정 의무인 파기가 실제로 됐는지 헷갈리게** 만들었다.

    그래서 둘을 나눈다.
      · 파기(DELETE)  = 법정 의무. 항상 하고, 항상 결과를 보고한다.
      · 축소(VACUUM) = 디스크 회수. `--vacuum` 을 준 사람만, 점검 시간에.
    삭제된 페이지는 VACUUM 없이도 SQLite 가 재사용하므로 운영에 지장이 없다
    (파일 크기만 안 줄어들 뿐이다).
    """
    days = int(os.environ.get("BOKGUON_LOG_RETENTION_DAYS", "730"))
    #  ✓ datetime.now(DB.KST) — tz-aware라 서버 OS 시간대와 무관하게 항상 KST
    #    기준이다. naive datetime.now()(OS 시각)를 썼다면 서버가 KST가 아닐 때
    #    (UTC 컨테이너 등) 보관기간이 최대 9시간 밀렸을 것 — 형제 명령
    #    cmd_prune_personal 이 쓰는 SQL 쪽 datetime('now','+9 hours') 보정과
    #    같은 기준으로 이미 맞춰져 있다.
    cutoff = (datetime.now(DB.KST) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    conn = DB.get_db()
    n = conn.execute("SELECT COUNT(*) n FROM access_log WHERE created_at < ?", (cutoff,)).fetchone()["n"]
    conn.execute("DELETE FROM access_log WHERE created_at < ?", (cutoff,))
    #  ⚠⚠ [라운드147] 처리방침 제2조는 "로그인 시도 기록"을 접속IP·접속일시·
    #    User-Agent 와 **같은 행**에 나열하고(legal_docs.py), 제3조는 그 행 전체에
    #    "2년"을 약속했다(고시 제8조제2항). 그런데 이 함수는 access_log 만 지우고
    #    login_attempts 는 어떤 파기 경로에도 없어 무기한 쌓였다 — 잠금 판정
    #    (_recent_fails)은 LOCKOUT_MINUTES 짜리 최근 창만 보므로, 2년 지난
    #    행을 지워도 잠금 기능에는 아무 영향이 없다.
    n_login = conn.execute(
        "SELECT COUNT(*) n FROM login_attempts WHERE created_at < ?", (cutoff,)).fetchone()["n"]
    conn.execute("DELETE FROM login_attempts WHERE created_at < ?", (cutoff,))
    conn.commit()

    head("접속기록 정리")
    print(f"  보관 기준 : {days}일 (이전: {cutoff})")
    ok(f"접속기록 {n:,}건 파기")
    ok(f"로그인 시도기록 {n_login:,}건 파기")

    # 회수 가능한 공간을 알려주고, 축소는 사람이 결정하게 한다
    try:
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
        psize = conn.execute("PRAGMA page_size").fetchone()[0]
        reclaim = free * psize
    except sqlite3.Error:
        reclaim = 0

    if "--vacuum" in argv:
        print(f"  VACUUM 실행 — 이 동안 쓰기가 막힙니다 (회수 예정 {reclaim:,} bytes)")
        try:
            conn.execute("VACUUM")
            ok("DB 파일 축소 완료")
        except sqlite3.Error as e:
            # 파기는 이미 커밋됐다. 축소 실패가 파기 성공을 덮지 않도록 경고로만 남긴다.
            warn(f"VACUUM 실패(파기는 정상 완료됨): {e}")
    elif reclaim > 50 * 1024 * 1024:
        print(f"  회수 가능 공간 {reclaim:,} bytes — 점검 시간에 "
              f"`manage.py prune-logs --vacuum` 으로 축소하세요.")
    #  ★ 예약 실행이 실제로 돌았다는 표식 — prune_personal 과 같은 이유다(라운드65).
    #    이것도 법정 의무(개인정보 보호법 §21) 파기인데, 예약이 안 걸려도 화면에
    #    아무 증상이 안 남는다(그냥 안 지워질 뿐) — manage.py check 가 미리 캐려면
    #    표식이 있어야 한다.
    conn.execute(
        "INSERT INTO job_locks(name, last_run_at) VALUES('prune_logs', ?) "
        " ON CONFLICT(name) DO UPDATE SET last_run_at=excluded.last_run_at",
        (DB.now(),))
    conn.commit()
    conn.close()


def cmd_stats(argv):
    head("데이터 현황")
    conn = DB.get_db()
    tables = [r["name"] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        n = conn.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        print(f"  {t:<24} {n:>8,}")
    print("─" * 62)
    size = os.path.getsize(DB.DB_PATH) if os.path.exists(DB.DB_PATH) else 0
    print(f"  {'DB 파일 크기':<24} {size:>8,} bytes")
    conn.close()


# ══════════════════════════════════════════════════════════════
#  법정 게시물에 들어갈 회사 정보 채우기
#
#  개인정보 보호책임자·통신판매업 신고번호 같은 값은 기획팀이 정하는 것이지
#  개발자가 파이썬 파일을 열어 고칠 일이 아니다. 여기서 채운다.
# ══════════════════════════════════════════════════════════════
INFO_PATH = os.path.join(HERE, "data", "company_info.json")


def _read_info():
    try:
        with open(INFO_PATH, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}   # 아직 set-info 를 한 번도 안 한 정상 상태 — 경고 불필요
    except Exception as e:
        #  ⚠⚠ [라운드121] legal_docs._load_info() 와 같은 결함 — 손상된 JSON 도
        #    "파일 없음"과 똑같이 조용히 삼켰다. CLI 라 운영자가 바로 볼 수 있게
        #    화면에 경고한다(반환값은 그대로 {} 유지 — 호출부를 안 건드린다).
        warn(f"company_info.json 을 읽지 못했습니다 ({type(e).__name__}: {e}) — "
             f"손상됐을 수 있습니다. 이 화면의 항목이 전부 미기재로 보일 수 있습니다.")
        return {}


def cmd_show_info(argv):
    import importlib
    import legal_docs
    importlib.reload(legal_docs)
    info = _read_info()
    head("법정 게시물 회사 정보")
    print(f"  저장 위치: {INFO_PATH}\n")
    missing = 0
    for key, label, hint in legal_docs.INFO_FIELDS:
        v = (info.get(key) or "").strip()
        if v:
            ok(f"{label}\n        {v}")
        else:
            missing += 1
            bad(f"{label}  \033[90m(미기재)\033[0m")
            print(f"        {hint}")
            print(f"        → python manage.py set-info {key} \"값\"")
    print("─" * 62)
    if missing:
        print(f"\033[91m미기재 {missing}건 — 배포 전 모두 채워야 합니다.\033[0m")
        return 1
    print("\033[92m모두 기재됨\033[0m")
    return 0


def cmd_set_info(argv):
    import legal_docs
    valid = {k: (lb, h) for k, lb, h in legal_docs.INFO_FIELDS}
    if len(argv) < 2:
        bad("사용법: python manage.py set-info <항목> \"값\"")
        print("\n  사용 가능한 항목:")
        for k, (lb, h) in valid.items():
            print(f"    {k:<16} {lb}")
        return 1
    key, value = argv[0], " ".join(argv[1:]).strip()
    if key not in valid:
        bad(f"알 수 없는 항목: {key}")
        print("  사용 가능: " + ", ".join(valid))
        return 1
    # 이 값은 개인정보 처리방침·사업자정보 화면에 그대로 실린다.
    # 표시용 문자열이므로 태그가 들어갈 이유가 없다 — 애초에 받지 않는다.
    if any(c in value for c in "<>"):
        bad("값에 < 또는 > 를 쓸 수 없습니다. (법정 게시물 화면에 그대로 표시되는 항목입니다)")
        return 1
    if len(value) > 200:
        bad(f"값이 너무 깁니다. (200자 이내, 현재 {len(value)}자)")
        return 1

    info = _read_info()
    old = info.get(key, "")
    info[key] = value
    os.makedirs(os.path.dirname(INFO_PATH), exist_ok=True)
    #  ⚠⚠ [라운드121] 예전엔 INFO_PATH 를 바로 열어 덮어썼다 — 디스크 풀·강제종료로
    #    쓰기가 중간에 끊기면 JSON 이 반쪽으로 남고, _read_info()/legal_docs 의
    #    로더가 그 손상을 조용히 삼켜 이미 입력해 둔 8개 항목 전부가 흔적 없이
    #    "(미기재)"로 되돌아간다. cmd_backup() 이 이미 쓰는 .part+os.replace
    #    원자적 교체를 여기도 적용한다.
    part = INFO_PATH + ".part"
    with open(part, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    os.replace(part, INFO_PATH)

    head("회사 정보 저장")
    print(f"  항목 : {valid[key][0]}")
    if old:
        print(f"  이전 : {old}")
    print(f"  현재 : \033[1m{value}\033[0m")
    ok(f"저장됨 — {INFO_PATH}")
    warn("서비스가 실행 중이면 재시작해야 화면에 반영됩니다.")


# ══════════════════════════════════════════════════════════════
#  운영 개시 — 데모 흔적 제거
# ══════════════════════════════════════════════════════════════
DEMO_ACCOUNTS = [("admins", "username", ["admin", "staff"]),
                 ("partners", "login_id", ["partner", "p2", "p3"]),
                 ("insurers", "login_id", ["insurer", "insurer2"])]


def _demo_counts(conn):
    """데모로 판정되는 행을 테이블별로 센다.

    ⚠ **미리보기와 실행이 같은 술어를 써야 한다.** 종전에는 여기서 is_demo 만 세고
      실행 단계에서 '데모 발주처 소속' 까지 지웠다. 그래서 미리보기가
      "cases 15건 삭제" 라고 해 놓고 실제로는 96건을 지웠다 —
      **사람이 그 목록을 보고 누를지 말지 정하는데** 그 목록이 거짓이었다.
      되돌릴 수 없는 조작 앞에서 이건 가장 나쁜 종류의 거짓말이다.
    """
    #  ⚠⚠ [라운드96] cmd_check(354-356행)는 이미 "DEMO_TABLES 만 보면 거짓
    #    초록 — 출동수배·현장합의는 is_demo 컬럼이 있는데 그 목록에 없다"고
    #    고쳐 뒀는데, 정작 여기(go-live 미리보기)는 그 확장을 안 물려받았다.
    #    실행 자체(바로 아래 ① 단계)는 case_id 로 두 표를 이미 통째로 지우니
    #    데이터가 남는 건 아니지만, 이 함수 자신의 docstring이 말하는 "미리보기와
    #    실행이 같은 술어를 써야 한다"를 어긴다 — 사람이 승인 전에 보는 숫자가
    #    실제 삭제 범위보다 작게 나온다.
    out = {}
    for t in list(DB.DEMO_TABLES) + ["dispatches", "field_agreements"]:
        try:
            if t == "cases":
                n = conn.execute(
                    "SELECT COUNT(*) n FROM cases WHERE " + DEMO_CASE_SQL).fetchone()["n"]
            else:
                n = conn.execute(f"SELECT COUNT(*) n FROM {t} WHERE is_demo=1").fetchone()["n"]
        except sqlite3.Error:
            n = 0
        if n:
            out[t] = n
    return out


def cmd_go_live(argv):
    """실서비스 개시 전 정리 — 시드가 넣은 데모 데이터와 데모 계정을 제거한다.

    ⚠ 판별은 **is_demo 표식**으로만 한다.
      예전에는 보험사명에 '○○'/'△△' 가 들어있는지로 골랐는데, 시드에는
      '메리츠화재'·'DB손보' 처럼 실제 사명으로 들어간 데모 사건·정산도 있어서
      그것들이 운영 데이터에 그대로 남아 통계와 정산을 오염시켰다.

    협력업체 목록(398개사)은 실제 영업 자산이므로 건드리지 않는다.
    """
    head("운영 개시 준비")
    show_db_target()
    conn = DB.get_db()

    #  ★ **표식이 없는 검증 사건에 먼저 표식을 붙인다.**
    #    발주처가 데모면 그 사건은 실사건일 수 없다(실사건은 실제 발주처가 보낸다).
    #    표식을 붙여 두면 아래의 기존 정리 절차(사건 id · is_demo 두 갈래)가
    #    사진·입찰·정산·하자까지 **한 기준으로** 함께 치운다.
    _ghost = conn.execute(
        "SELECT COUNT(*) n FROM cases WHERE COALESCE(is_demo,0)=0 "
        "  AND insurer_id IN (SELECT id FROM insurers "
        "                      WHERE COALESCE(is_demo,0)=1)").fetchone()["n"]
    if _ghost:
        if "--yes" in argv:
            conn.execute(
                "UPDATE cases SET is_demo=1 WHERE COALESCE(is_demo,0)=0 "
                "  AND insurer_id IN (SELECT id FROM insurers "
                "                      WHERE COALESCE(is_demo,0)=1)")
            conn.commit()
        else:
            warn(f"표식 없는 검증 사건 {_ghost}건 — 데모 발주처 소속이라 함께 정리합니다.")

    counts = _demo_counts(conn)
    accounts = []
    #  ⚠⚠ [라운드209] 미리보기·실행이 같은 술어를 써야 한다는 이 함수의 원칙
    #    (docstring)을 하위계정(portal_users)에도 맞춘다 — 실행 단계가 이제
    #    데모 원계정과 함께 그 하위계정도 지우므로, 승인 전 화면에도 몇 개나
    #    지워지는지 미리 보여 준다.
    n_sub_preview = 0
    for table, col, names in DEMO_ACCOUNTS:
        for nm in names:
            if conn.execute(f"SELECT 1 FROM {table} WHERE {col}=?", (nm,)).fetchone():
                accounts.append(f"{table}/{nm}")
            if table != "admins":
                org_type = "insurer" if table == "insurers" else "partner"
                n_sub_preview += conn.execute(
                    "SELECT COUNT(*) n FROM portal_users WHERE org_type=? AND org_id IN "
                    f"(SELECT id FROM {table} WHERE {col}=?)", (org_type, nm)).fetchone()["n"]

    # 데모 사건에 딸린 것들(사진·입찰)은 표식이 없을 수도 있으므로 사건 id 로 함께 센다
    #  ⚠ **`is_demo=1` 만 보면 미리보기가 실제 삭제량보다 적게 나온다.**
    #    미리보기 경로에서는 위의 유령 표식 UPDATE 를 하지 않으므로(--yes 일 때만 한다),
    #    '데모 발주처 소속인데 표식이 없는' 사건과 거기 딸린 사진·정산·하자가
    #    확인 화면의 숫자에서 통째로 빠진다. 사진은 디스크에서도 지워지는데,
    #    운영자는 그 장수를 안내받은 적이 없는 상태로 되돌릴 수 없는 삭제를 승인한다.
    #    --yes 경로에서는 이미 표식이 붙어 있어 결과가 같다(두 경로가 같은 말을 한다).
    demo_case_ids = [r["id"] for r in
                     conn.execute("SELECT id FROM cases WHERE " + DEMO_CASE_SQL)]
    extra = {}
    if demo_case_ids:
        marks = ",".join("?" * len(demo_case_ids))
        #  ⚠⚠ [라운드187] 예전엔 photos·settlements·defects 세 표만 셌다 — dispatches·
        #    field_agreements·change_orders·work_lots·bid_events·est_outcome·
        #    damage_reads·schedule_events·contract_gate_log·notifications 는 위 ①단계가
        #    실제로 지우는데 미리보기 화면엔 아예 나타나지 않았다. CASE_CHILD_TABLES
        #    (2265행)는 정리(prune-orphans)가 쓰는 것과 같은 case_id 자식표 목록이라
        #    ①단계가 지우는 범위와 그대로 일치한다 — 새 표가 생기면 거기 한 곳만
        #    고치면 이 미리보기도 함께 맞는다.
        for t in CASE_CHILD_TABLES:
            try:
                extra[t] = conn.execute(
                    f"SELECT COUNT(*) n FROM {t} WHERE case_id IN ({marks})",
                    demo_case_ids).fetchone()["n"]
            except sqlite3.Error:
                pass
        #  case_id 가 없어 다른 표를 거쳐야만 사건에 닿는 자식표들 — ①단계와 같은 경로.
        try:
            extra["bids"] = conn.execute(
                f"SELECT COUNT(*) n FROM bids WHERE auction_id IN "
                f"(SELECT id FROM auctions WHERE case_id IN ({marks}))",
                demo_case_ids).fetchone()["n"]
        except sqlite3.Error:
            pass
        try:
            extra["ai_reviews"] = conn.execute(
                f"SELECT COUNT(*) n FROM ai_reviews WHERE photo_id IN "
                f"(SELECT id FROM photos WHERE case_id IN ({marks}))",
                demo_case_ids).fetchone()["n"]
        except sqlite3.Error:
            pass
        try:
            extra["defect_photos"] = conn.execute(
                f"SELECT COUNT(*) n FROM defect_photos WHERE photo_id IN "
                f"(SELECT id FROM photos WHERE case_id IN ({marks})) "
                f"   OR defect_id IN (SELECT id FROM defects WHERE case_id IN ({marks}))",
                demo_case_ids + demo_case_ids).fetchone()["n"]
        except sqlite3.Error:
            pass
        try:
            extra["dispatch_calls"] = conn.execute(
                f"SELECT COUNT(*) n FROM dispatch_calls WHERE dispatch_id IN "
                f"(SELECT id FROM dispatches WHERE case_id IN ({marks}))",
                demo_case_ids).fetchone()["n"]
        except sqlite3.Error:
            pass

    if "--yes" not in argv:
        #  ⚠ 닫기 전에 읽어 둔다 — 미리보기 문구가 DB 를 한 번 더 봐야 한다.
        _keep = conn.execute(
            "SELECT COUNT(*) n FROM cases WHERE NOT (" + DEMO_CASE_SQL + ")").fetchone()["n"]
        _np = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
        #  ⚠⚠ [라운드187] 아래 둘(해피콜 전량삭제·로그인시도 전량초기화)과 협력사
        #    평판 초기화는 실행(③-2·④단계)이 WHERE 없이 통째로 하는 일인데, 예전엔
        #    실행이 끝난 뒤 ok() 로만 알렸다 — 승인 버튼을 누르기 **전에** 알아야
        #    할 내용이 실행 **후** 보고로만 나온 것이다. 여기서 미리 밝힌다.
        try:
            _hc = conn.execute("SELECT COUNT(*) n FROM happy_calls").fetchone()["n"]
        except sqlite3.Error:
            _hc = 0
        try:
            _la = conn.execute("SELECT COUNT(*) n FROM login_attempts").fetchone()["n"]
        except sqlite3.Error:
            _la = 0
        conn.close()
        #  ⚠⚠ [라운드187] counts 만 보면 놓친다 — 표식 없는 유령 사건(데모 발주처
        #    소속인데 is_demo=0)만 있는 DB 는 counts 가 전부 비어 "정리할 데모
        #    데이터가 없습니다"를 찍지만, extra 는 그 유령 사건에 딸린 행을 이미
        #    잡고 있다. counts 만 보고 "없다"고 말하면 그 자체가 거짓 초록이다.
        if not counts and not extra and not accounts:
            ok("정리할 데모 데이터가 없습니다. (운영 모드로 설치했다면 정상)")
            return 0
        print("  아래를 삭제합니다:")
        for t, n in sorted(counts.items()):
            print(f"    · {t:<24} {n:>5}건  (데모 표식)")
        for t, n in sorted(extra.items()):
            if n:
                print(f"    · {t:<24} {n:>5}건  (데모 사건에 딸림)")
        print(f"    · 데모 계정               {len(accounts):>5}개  "
              f"({', '.join(accounts) if accounts else '없음'})")
        if n_sub_preview:
            print(f"    · 딸린 하위계정(portal_users) {n_sub_preview:>5}개  "
                  f"(원계정과 함께 로그인 수단이 지워집니다)")
        if _hc:
            print(f"    · happy_calls             {_hc:>5}건  (데모 여부 무관 전량 삭제)")
        if _la:
            print(f"    · login_attempts          {_la:>5}건  (전량 초기화 — 계정 잠금 임시기록이라 안전)")
        print()
        #  ⚠ '실제 사건은 유지됩니다' 를 사실 확인 없이 말하지 않는다 —
        #    지금 DB 에는 실 발주처 소속 사건이 하나도 없을 수 있다.
        warn(f"협력업체 목록({_np}개사)은 유지됩니다 — 단 평점·실적(rating·jobs_done·"
             f"win_rate)은 {_np}개사 전부 0/초기화됩니다(데모 사건에서 나온 값이라). "
             + (f"실 발주처 소속 사건 {_keep}건도 유지됩니다."
                if _keep else "**유지되는 사건은 없습니다** — 지금 DB 의 사건은 전부 검증용입니다."))
        bad("실행하려면 --yes 를 붙이세요:  python manage.py go-live --yes")
        return 1

    conn.close()
    print("  먼저 백업합니다...")
    if cmd_backup([]) == 1:
        bad("백업에 실패했습니다. 정리를 중단합니다.")
        return 1

    conn = DB.get_db()
    _photo_rel = []
    n_admin = n_partner = 0
    try:
        conn.execute("BEGIN IMMEDIATE")

        #  ⚠⚠ [라운드210] 데모 계정(③단계)의 조직 id를 **다른 무엇보다 먼저**
        #    잡아 둔다 — insurers 는 DEMO_TABLES(db.py)에도 들어 있어, 아래
        #    ②단계(`DELETE FROM insurers WHERE is_demo=1`)가 이 트랜잭션
        #    안에서 그 행을 통째로 먼저 지워 버린다(실측: 운영DB 의 데모
        #    보험사 6곳 전부 is_demo=1). ③단계가 그 뒤에 login_id 로 다시
        #    찾으려 하면 이미 사라진 행이라 하위계정 정리 서브쿼리가 매번
        #    0건이 된다 — 209라운드가 고친 하위계정 정리가 보험사 쪽에서만
        #    조용히 무력화됐었다(협력사는 DEMO_TABLES 에 없어 문제없었다).
        #    행이 지워지기 전인 지금 id 를 잡아 두면 ②가 나중에 그 행을
        #    지우든 말든 ③의 하위계정 정리는 항상 올바른 조직을 겨눈다.
        _demo_org_ids = {}
        for _table, _col, _names in DEMO_ACCOUNTS:
            if _table == "admins":
                continue
            for _nm in _names:
                _row = conn.execute(f"SELECT id FROM {_table} WHERE {_col}=?", (_nm,)).fetchone()
                if _row:
                    _demo_org_ids[(_table, _nm)] = _row["id"]

        # ① 데모 사건에 딸린 파일·행 (표식이 없을 수 있으므로 사건 id 기준)
        ids = [r["id"] for r in conn.execute("SELECT id FROM cases WHERE is_demo=1")]
        if ids:
            marks = ",".join("?" * len(ids))
            #  ⚠⚠ [라운드69] 예전엔 파일을 이 트랜잭션 도중(커밋 전) `os.remove()`
            #    로 즉시 지웠다 — 이 함수 전체가 try/except 로 보호돼 있지 않아서,
            #    아래 DELETE 들 중 하나라도 실패해 롤백되면 DB 행은 되살아나는데
            #    파일은 이미 사라져 "행은 있는데 파일이 없는" 상태가 됐다(고아
            #    정리 명령 cmd_prune_orphans 가 이미 겪고 고친 문제, 아래 주석
            #    참조 — 원칙: 파일 이동은 반드시 commit 뒤에). 경로만 먼저
            #    챙기고, 실제 이동은 아래에서 커밋이 끝난 뒤로 미룬다.
            for r in conn.execute(
                    f"SELECT rel_path FROM photos WHERE case_id IN ({marks}) "
                    f"  AND COALESCE(rel_path,'') <> ''", ids):
                _photo_rel.append(r["rel_path"])
            #  ★★ **photos 를 지우기 직전에** defect_photos 를 먼저 지운다.
            #    defect_photos 에는 case_id 가 없어 photo_id 로만 사건에 닿는다 —
            #    photos 가 먼저 사라지면 아래 하위질의가 빈 집합이 되어 **항상 0행**이다.
            #    (9·10·11라운드에 세 번 '고쳤는데' 세 번 다 이 순서를 확인하지 않았다.
            #     예외도 안 나므로 로그는 늘 정상이었다 — 검증은 **행 수를 세는 것**뿐이다.)
            _dead = []
            try:
                conn.execute(
                    f"DELETE FROM defect_photos WHERE photo_id IN "
                    f"(SELECT id FROM photos WHERE case_id IN ({marks}))", ids)
            except sqlite3.Error:
                _dead.append("defect_photos")
            #  ai_reviews·damage_reads 도 photo_id 로만 닿는다 — 같은 이유로 여기서 지운다.
            for _pt in ("ai_reviews",):
                try:
                    conn.execute(
                        f"DELETE FROM {_pt} WHERE photo_id IN "
                        f"(SELECT id FROM photos WHERE case_id IN ({marks}))", ids)
                except sqlite3.Error:
                    _dead.append(_pt)
            conn.execute(f"DELETE FROM photos WHERE case_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM bids WHERE auction_id IN "
                         f"(SELECT id FROM auctions WHERE case_id IN ({marks}))", ids)
            conn.execute(f"DELETE FROM auctions WHERE case_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM settlements WHERE case_id IN ({marks})", ids)
            conn.execute(f"DELETE FROM defects WHERE case_id IN ({marks})", ids)
            #  ⚠ **사건에 딸린 표를 빠짐없이** 지운다. 예전에는 사진·입찰·경매·정산·하자만
            #    지워, 출동수배(dispatches)·현장합의(field_agreements)·변경견적 등이
            #    **없어진 사건을 가리키는 고아 행**으로 남았다. 배포 점검은 DEMO_TABLES 만
            #    세므로 '데모 데이터 없음' 초록을 찍었고, 출동 스윕은 그 고아 수배를
            #    계속 붙들었다.
            #  ⚠⚠ [라운드263] 바로 아래(1872행대) 형제 루프는 실패를 _dead 에 모아
            #    warn() 으로 알리는데, 이 표만 except: pass 로 조용히 삼켰다 — 스키마가
            #    바뀌어 이 DELETE 가 깨져도 화면은 "삭제 완료"만 보여주고 지워진
            #    데모 사건을 가리키는 고아 dispatch_calls 행이 남을 수 있었다.
            for _t in ("dispatch_calls",):
                try:
                    conn.execute(
                        f"DELETE FROM {_t} WHERE dispatch_id IN "
                        f"(SELECT id FROM dispatches WHERE case_id IN ({marks}))", ids)
                except sqlite3.Error:
                    _dead.append(_t)
            #  ⚠ 목록에서 뺀 셋 — defect_photos 에는 case_id 컬럼이 아예 없고,
            #    gate_logs·case_notes 는 **존재하지 않는 표**다(실제 표는 contract_gate_log).
            #    세 줄 모두 OperationalError 로 죽었는데 except 가 삼켰다. 몇 달 동안
            #    "지웠다"고 말하면서 아무 일도 안 한 것이다 — 아래에서 실제 구조대로 지운다.
            #  ⚠⚠ [라운드122] schedule_events 도 case_id 로 사건에 붙는 자식표인데
            #    이 목록에 없어 데모 사건을 지워도 고아 행으로 남았다(존재하지 않는
            #    사건을 가리킨 채 영구히). 실측: go-live 뒤 cases 는 0건인데
            #    schedule_events 는 살아남은 행이 case_id=(지워진 사건)을 가리킴.
            for _t in ("dispatches", "field_agreements", "change_orders", "work_lots",
                       "bid_events", "est_outcome", "damage_reads", "schedule_events"):
                try:
                    conn.execute(f"DELETE FROM {_t} WHERE case_id IN ({marks})", ids)
                except sqlite3.Error:
                    #  ★ **조용히 죽지 않는다.** 표·컬럼이 바뀌면 여기서 말해 준다.
                    _dead.append(_t)

            #  관문 판정 기록의 실제 표 이름은 contract_gate_log 다.
            try:
                conn.execute(f"DELETE FROM contract_gate_log WHERE case_id IN ({marks})", ids)
            except sqlite3.Error:
                _dead.append("contract_gate_log")

            if _dead:
                warn("정리하지 못한 표 " + ", ".join(_dead)
                     + " — 표 이름·컬럼을 확인하세요(그 줄은 아무 일도 하지 않았습니다).")
        ok(f"데모 사건 {len(ids)}건에 딸린 사진·입찰·정산·하자·출동·합의 삭제")

        # ② 표식이 붙은 행 일괄 삭제
        removed = {}
        for t in DB.DEMO_TABLES:
            try:
                cur = conn.execute(f"DELETE FROM {t} WHERE is_demo=1")
                if cur.rowcount:
                    removed[t] = cur.rowcount
            except sqlite3.Error:
                pass
        ok("데모 표식 행 삭제 — " + (", ".join(f"{k} {v}건" for k, v in sorted(removed.items()))
                                    or "없음"))

        # ③ 데모 계정
        n_acc = 0
        n_sub = 0
        for table, col, names in DEMO_ACCOUNTS:
            for nm in names:
                if table == "admins":
                    #  ⚠⚠ [라운드475] api_admin_delete()(app.py)는 마지막
                    #    최고관리자는 지우지 못하게 막는데, 이 대량정리 경로엔
                    #    그 가드가 없었다 — go-live 전에 새 관리자를 만들면서
                    #    --role 을 안 붙이면(기본값 중간관리자) 'admin' 이
                    #    유일한 최고관리자인 채로 그대로 삭제돼, 콘솔에서
                    #    최고관리자를 다시 만들 방법이 없는 영구 락아웃이
                    #    된다(실측 재현 — 서버 쉘로 create-admin 을 직접
                    #    돌리는 것 외엔 복구 수단이 없었다). 지우면 최고관리자가
                    #    0명이 될 경우에만 건너뛰고 경고한다 — 다른 데모정리는
                    #    계속 진행하고, go-live 는 재실행 가능하므로 실제
                    #    최고관리자를 만든 뒤 다시 돌리면 그때 지워진다.
                    _row = conn.execute(
                        f"SELECT role FROM {table} WHERE {col}=?", (nm,)).fetchone()
                    if _row and _row["role"] == "최고관리자":
                        _n_super = conn.execute(
                            "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'"
                        ).fetchone()["n"]
                        if _n_super <= 1:
                            warn(f"'{nm}' 계정이 마지막 최고관리자라 지우지 않았습니다. "
                                 f"실제 최고관리자 계정을 만든 뒤 go-live를 다시 실행하세요"
                                 f"(python manage.py create-admin <아이디> --role 최고관리자).")
                            continue
                    cur = conn.execute(f"DELETE FROM {table} WHERE {col}=?", (nm,))
                else:
                    #  ⚠⚠ [라운드209/210] 하위계정(portal_users)은 원계정과
                    #    별개의 login_id·password_hash 를 갖는데, 인증 시(app.py
                    #    _portal_authenticate) 원계정의 login_id/password_hash
                    #    가 NULL인지는 안 보고 원계정 status 만 본다 — 원계정
                    #    크리덴셜만 지우면, 데모 계정으로 로그인해 미리 만들어
                    #    둔 하위계정이 실운영 전환 뒤에도 영구히 로그인 가능한
                    #    채로 남는다. [라운드210] login_id 로 다시 찾으면
                    #    안 된다 — insurers 는 위 ②단계가 is_demo=1 인 행을
                    #    이미 통째로 지웠을 수 있어(실측: 운영DB 전부 그렇다)
                    #    그 시점엔 이 조회가 항상 0건이다. 트랜잭션 맨 앞에서
                    #    미리 잡아 둔 id(_demo_org_ids)를 쓴다 — ②가 행을
                    #    지웠든 말든 항상 올바른 조직을 겨눈다.
                    org_type = "insurer" if table == "insurers" else "partner"
                    _oid = _demo_org_ids.get((table, nm))
                    if _oid is not None:
                        n_sub += conn.execute(
                            "DELETE FROM portal_users WHERE org_type=? AND org_id=?",
                            (org_type, _oid)).rowcount
                    # 협력업체·보험사는 **회사 정보 자체는 남기고** 로그인 수단만 없앤다
                    #  (다만 보험사는 데모로 표식된 행이면 ②단계가 이미 통째로
                    #   지웠을 수 있다 — 그때 이 UPDATE 는 대상이 없어 0행이고,
                    #   그건 옳다: 지워진 행에 로그인 수단만 남길 이유가 없다)
                    cur = conn.execute(
                        f"UPDATE {table} SET login_id=NULL, password_hash=NULL WHERE {col}=?", (nm,))
                n_acc += cur.rowcount
        ok(f"데모 계정 {n_acc}개 정리 (업체·기관 정보 자체는 유지)"
           + (f" · 딸린 하위계정 {n_sub}개도 함께 정리" if n_sub else ""))

        # ③-2 **협력사 평판을 0 에서 시작시킨다.**
        #  ⚠ 해피콜(happy_calls)·실적(jobs_done·win_rate)·평점(rating)은 지워진 데모 사건에서
        #    나온 값이다. 그대로 두면 **없어진 사건의 만족도 5.0** 이 실운영 낙찰 점수의
        #    유일한 근거가 되고(철칙 3), 화면은 그것을 '실적'으로 표시한다.
        #    협력업체 명부 자체는 영업 자산이라 남기되, **평판만** 비운다.
        try:
            n_hc = conn.execute("DELETE FROM happy_calls").rowcount
        except sqlite3.Error:
            n_hc = 0
        try:
            conn.execute("UPDATE partners SET rating=NULL, jobs_done=0, win_rate=0")
        except sqlite3.Error:
            pass
        ok(f"협력사 평판 초기화 — 해피콜 {n_hc}건 삭제 · 평점·실적 0 에서 시작"
           " (명부 자체는 유지)")

        # ④ 알림·로그인시도 정리.
        #  ⚠ 종전 코드는 `cutoff = DB.now()` 로 잡고 `created_at <= cutoff` 를 지웠다 —
        #    '지금 이전'이면 **전부**다. 주석은 '데모 시점 이전 것만'이라고 적혀 있는데
        #    실제로는 실운영 중 쌓인 기록까지 통째로 날아간다(실측 알림 1,553행).
        #    특히 status='발송대기' 인 통지가 사라지면 그 문자·알림톡은 영영 안 나간다.
        #    이제 **데모 사건에 딸린 것과 데모 표식이 붙은 것만** 지운다.
        n1 = 0
        if ids:
            n1 += conn.execute(
                f"DELETE FROM notifications WHERE case_id IN ({marks})", ids).rowcount
        n1 += conn.execute("DELETE FROM notifications WHERE COALESCE(is_demo,0)=1").rowcount
        #  로그인 시도 기록은 계정 잠금 판정용 임시 기록이라 전량 정리해도 손실이 없다.
        n2 = conn.execute("DELETE FROM login_attempts").rowcount
        ok(f"데모 알림 {n1}건 삭제 · 로그인 시도 기록 {n2}건 초기화 "
           f"(운영 중 쌓인 알림은 보존)")

        DB.log(conn, "manage.py", "운영 개시 정리",
               f"사건 {len(ids)}건 · 계정 {n_acc}개 · 표식행 {sum(removed.values())}건")
        #  ★ **출시 표식을 남긴다.** 이게 없으면 go-live 직후의 DB(사건 0·관리자 0)가
        #    init_db 의 '빈 DB' 조건과 똑같아져서, 서버를 한 번만 재시작해도
        #    방금 비운 운영 DB 에 데모가 되돌아온다. settings 는 go-live 가 안 지운다.
        conn.execute(
            "INSERT INTO settings(key, value) VALUES('go_live_at', datetime('now','+9 hours')) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value")
        conn.commit()

        #  ⚠⚠ [라운드629] 바로 아래 n_admin과 같은 자리에 있는 진짜 형제 결함 — round475가
        #    이미 "관리자 1명 이상이어도 전부 중간·하위관리자뿐이면 계정관리·
        #    정산이체·요율설정을 아무도 못 켠다"며 cmd_check()(317-337행)에 n_super
        #    분기를 넣고, 위 ③단계 삭제 루프(2129-2137행)에도 "이 삭제 자체가
        #    마지막 최고관리자를 지우면 안 된다"는 가드를 넣었다 — 그런데 go-live가
        #    **자기 실행 직후 찍는 이 요약**만은 그 형제 취급을 못 받았다. ③단계
        #    가드는 go-live의 삭제가 최고관리자를 0명으로 만드는 것만 막을 뿐, go-live를
        #    돌리기 **전부터** 최고관리자가 0명이던 상태(예: create-admin을 --role
        #    없이 돌려 만든 계정 하나뿐이고 데모 admin/staff는 애초에 없거나 이미
        #    지워진 경우)는 그대로 통과시킨다 — 아래 요약은 n_admin>0 이면 무조건
        #    "관리자 계정 N개 유지"(정상)로 찍어, cmd_check()가 이미 "bad"로 잡는
        #    바로 그 상태를 go-live 자신의 화면에서는 초록으로 보여준다. 다음 줄의
        #    "python manage.py check"가 뒤늦게 잡아 주긴 하지만, round627이 insurers에
        #    적용한 것과 같은 원칙(형제 요약이 이미 아는 것을 이 요약도 알아야 한다)
        #    으로 여기도 맞춘다 — 삭제 로직·판정 기준은 전혀 안 바꾸고 개수만 센다.
        #    n_admin·n_partner·n_insurer 세 줄(round627이 이미 확정한 블록) **앞**에
        #    둔다 — 그 블록 안이나 뒤에 끼우면 round627 자신의 회귀테스트가 소스를
        #    원문 그대로(문자 단위) 대조하는 자리를 깨뜨린다(직접 재현·확인).
        n_super = conn.execute(
            "SELECT COUNT(*) n FROM admins WHERE role='최고관리자'").fetchone()["n"]
        n_admin = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        n_partner = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
        #  ⚠⚠ [라운드627] round406이 발견하고 미뤄 둔 형제 결함 — 관리자(n_admin)가
        #    0명이면 아래 요약이 경고+복구명령까지 주는데, 바로 위 ②단계가
        #    is_demo=1 전량을 통째로 지우는 insurers(DEMO_TABLES 소속)는 몇 곳이
        #    남았는지 어디에도 안 나온다. round626 실측(운영DB, 읽기전용): 활성
        #    발주처 7곳 중 6곳이 is_demo=1 — 오늘 go-live를 돌리면 실제로 1곳만
        #    남는데도 화면에 안 보인다. 삭제 로직은 그대로 두고(정책 변경 아님),
        #    admins·partners와 나란히 개수만 센다.
        n_insurer = conn.execute("SELECT COUNT(*) n FROM insurers").fetchone()["n"]
    except sqlite3.Error as e:
        conn.rollback()
        bad(f"정리 실패: {e}")
        return 1
    finally:
        conn.close()

    #  ⚠ **지우지 않고 휴지통으로 옮긴다** — commit 이 끝난 뒤에야 실제로 옮긴다
    #    (위 주석 참조: 커밋 전에 옮기면 롤백 시 "행은 있는데 파일이 없는" 상태가
    #    된다). 데모로 판별된 사진이라도 유령 사건 판별(_ghost/DEMO_CASE_SQL)이
    #    혹시 틀렸을 가능성에 대비해 되돌릴 여지를 남긴다 — cmd_prune_orphans 와
    #    같은 원칙(2068행 주석).
    gone = missing = 0
    if _photo_rel:
        _root = _upload_root()
        _tr = os.path.join(_root, "_trash")
        for _rp in _photo_rel:
            _src = os.path.join(_root, str(_rp).replace("/", os.sep))
            if not os.path.isfile(_src):
                missing += 1
                continue
            _dst = os.path.join(_tr, str(_rp).replace("/", os.sep))
            try:
                os.makedirs(os.path.dirname(_dst), exist_ok=True)
                shutil.move(_src, _dst)
                #  ⚠⚠ [라운드110] shutil.move 도 원본 mtime 을 보존한다 —
                #    prune-personal 의 30일 파기 판정을 무력화한다(같은 원인, app.py
                #    _photo_to_trash 참조).
                os.utime(_dst, None)
                gone += 1
            except OSError:
                missing += 1
        if missing:
            warn(f"사진 파일 {missing}개가 이미 없거나 옮기지 못해 건너뜀 (DB 기록은 정리됨)")
        if gone:
            ok(f"사진 파일 {gone}개를 휴지통(_trash)으로 옮겼습니다 — 31일 뒤 prune-personal 이 지웁니다.")

    print("─" * 62)
    #  ⚠⚠ [라운드630] 바로 아래 n_insurer·n_admin과 같은 자리에서 나란히 세던
    #    n_partner만 이 요약 자신에서는 형제 취급을 못 받았다 — round627이
    #    발주처 0명을, round629가 "관리자는 있지만 최고관리자 0명"을 각각
    #    경고로 올렸는데, 바로 이 줄의 협력업체만 n_partner==0이어도 무조건
    #    ok()로 "유지됨"을 찍는다. go-live는 partners 행 자체를 지우지
    #    않지만(문서화된 대로 실제 영업 자산이라 보존 — 로그인 수단만
    #    정리), partners에는 create-admin/create-insurer 같은 CLI가 없어
    #    콘솔에서만 등록·삭제된다 — 누군가 go-live 전에 콘솔에서 협력사를
    #    전부 지웠거나(예: 삭제 기능 테스트) 애초에 한 곳도 등록하지 않은
    #    채(흔한 첫 배포 실수: init 직후 바로 go-live부터 돌리는 순서) go-live를
    #    돌리면 — 낙찰받아 공사를 진행할 업체가 하나도 없어 사건을 아무도
    #    처리 못 하는, n_insurer==0(사건 등록 불가)·n_super==0(관리 기능
    #    불가)과 정확히 같은 급의 운영 정지 상태인데도 화면은 초록만
    #    보여준다. 삭제 로직·판정 기준은 그대로 두고(정책 변경 아님) 개수만
    #    보고 형제와 같은 모양(if 0: warn 아니면 ok)으로 맞춘다. 복구 명령은
    #    CLI가 없으므로 콘솔 화면 이름을 안내한다.
    if n_partner == 0:
        warn("협력업체가 하나도 남지 않았습니다 — 낙찰받아 공사를 진행할 업체가 없습니다. 반드시 등록하세요:")
        print("      콘솔 로그인 → [업체 등록·관리] → + 업체 등록")
    else:
        ok(f"협력업체 {n_partner}개사 유지됨")
    if n_insurer == 0:
        warn("발주처(보험사) 계정이 하나도 남지 않았습니다 — 사건을 등록할 곳이 없습니다. 반드시 만드세요:")
        print("      python manage.py create-insurer <기관명> <로그인ID>")
    else:
        ok(f"발주처 {n_insurer}개사 유지됨")
    if n_admin == 0:
        warn("관리자 계정이 하나도 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
        print("      ※ 'admin' 이 아닌 실제 담당자 아이디를 쓰세요.")
    elif n_super == 0:
        #  ⚠⚠ [라운드629] cmd_check()(317-337행)와 같은 기준 — 관리자는 있지만
        #    전부 중간·하위관리자뿐이면 계정관리·정산이체·요율설정을 아무도 못 켠다.
        warn(f"관리자 계정은 {n_admin}개 있지만 최고관리자가 0명입니다 — "
             f"계정관리·정산이체·요율설정을 아무도 할 수 없습니다. 반드시 만드세요:")
        print("      python manage.py create-admin <아이디> --role 최고관리자")
    else:
        ok(f"관리자 계정 {n_admin}개(최고관리자 {n_super}명 포함) 유지")
    print()
    print("  다음 단계:  python manage.py check")



#  하자보증 만료일 — app.py 의 _warranty_left 와 **같은 말일 보정**을 한다.
#  (SQLite date(x,'+N months') 는 보정 없이 다음 달로 넘어간다)
_WEND = ("CASE WHEN CAST(strftime('%d', date(completed_at, '+' || "
         "COALESCE(warranty_months,24) || ' months')) AS INT) "
         " < CAST(strftime('%d', completed_at) AS INT) "
         "THEN date(completed_at, '+' || COALESCE(warranty_months,24) || "
         "' months', 'start of month', '-1 day') "
         "ELSE date(completed_at, '+' || COALESCE(warranty_months,24) || "
         "' months') END")

#  ⚠⚠ [라운드194] 하자보수기록 파기 기준일(_WEND + 3년)에도 같은 말일 보정이
#    필요했는데 빠져 있었다 — _WEND 는 이미 보정된 값이라도, 그 위에 SQLite
#    '+3 years'를 또 얹으면 윤년 2월29일이 다음 3년 뒤(윤년이 아닐 확률이 높다)
#    2월28일이 아니라 3월1일로 넘어간다(실측: sqlite3 로 재현 —
#    date('2028-02-29','+3 years') = '2031-03-01'). 그만큼 파기가 하루 늦어진다.
_DEFECT_PURGE_AT = (
    "CASE WHEN CAST(strftime('%d', datetime(" + _WEND + ", '+3 years')) AS INT) "
    " < CAST(strftime('%d', " + _WEND + ") AS INT) "
    "THEN datetime(" + _WEND + ", '+3 years', 'start of month', '-1 day') "
    "ELSE datetime(" + _WEND + ", '+3 years') END")


def cmd_prune_personal(argv):
    """처리방침이 약속한 **개인정보 파기**를 실제로 실행한다.

    ⚠ 처리방침 제3조는 보유기간을 명시해 두었는데(문의 1년, 계좌는 거래 종료 즉시,
      피해자 정보는 하자담보 만료 후), **그것을 실행하는 코드가 하나도 없었다.**
      약속만 하고 지우지 않으면 개인정보 보호법 제21조 위반이고,
      처리방침과 실제가 다르다는 점에서 제30조 위반이기도 하다.

    무엇을 지우는지 (총 6개 항목 — ⚠⚠ [라운드669] 아래 ④⑤⑥이 실제로는 이미
    구현·테스트(146·495라운드)까지 끝나 있었는데 이 목록에서만 빠져 있었다.
    처리방침 제30조는 "실제 처리 현황"을 문서가 정확히 반영할 것을 요구한다):
      ① 계약으로 이어지지 않은 도입 문의·입점 신청 — 수집 1년 경과분
      ② 퇴출 협력사의 정산 계좌 — 미지급 정산이 없을 때만(돈이 남았으면 못 지운다)
      ③ 완료 사건의 피해자 성명·연락처 — 하자담보(24개월) 만료 후
         (딸린 사본도 함께: 피해자 안내 알림 본문·진행조회 링크·휴지통 사진)
      ④ 취소·미수선종결·유찰로 종료된 사건의 피해자 성명·연락처
         — 종료 후 보관기간(기본 90일, BOKGUON_VICTIM_KEEP_DAYS) 경과분
         (③과 같은 딸린 사본도 함께: 알림 본문·진행조회 링크)
      ⑤ 하자보수 기록의 개인식별 자유텍스트(제목·내용·처리결과·접수자)
         — 준공 + 하자담보 만료 후 3년(통계용 필드는 남기고 텍스트만 소거)
      ⑥ 해피콜 기록의 응대내용·상담원 — 하자담보 만료 후(통계용 필드는 남기고 텍스트만 소거)

    --dry-run : 지우지 않고 대상 건수만 센다(먼저 이걸로 확인할 것)
    파기 결과는 activity_log 에 남겨 **증적**이 된다.
    """
    dry = "--dry-run" in argv
    head("개인정보 파기" + (" (미리보기)" if dry else ""))
    show_db_target()
    #  ⚠⚠ [라운드263] 형제(go-live·prune-orphans)는 기본이 미리보기이고 --yes 를
    #    붙여야 실행되는데, 이 명령만 반대로 **기본이 즉시 실행**이다(주간 예약
    #    작업 deploy/windows_setup.ps1·bootstrap.sh 둘 다 플래그 없이
    #    "manage.py prune-personal" 을 부르는 걸 그대로 믿는 구조라, 기본값
    #    자체를 뒤집으면 매주 도는 개인정보 보호법 §21·§30 이행 예약이 조용히
    #    빈 작업이 된다 — 실행 기준을 바꾸는 대신, 어느 쪽으로 도는지를
    #    실행 화면(및 예약작업 로그 리다이렉트)에서 절대 헷갈릴 수 없게 만든다).
    if not dry:
        warn("플래그 없이 실행 — 확인 절차 없이 지금 즉시 삭제합니다"
             "(먼저 --dry-run 으로 대상 건수를 확인하는 것을 권장합니다).")
    conn = DB.get_db()
    n1 = n2 = n3 = 0
    try:
        # ① 미전환 문의·신청 1년 경과
        for tbl, label in (("insurer_leads", "도입 문의"), ("partner_applications", "입점 신청")):
            sel = (f"SELECT COUNT(*) n FROM {tbl} "
                   f" WHERE created_at < datetime('now','+9 hours','-1 year')"
                   f"   AND COALESCE(status,'') NOT IN ('전환','승인','계약')")
            cnt = conn.execute(sel).fetchone()["n"]
            if cnt and not dry:
                conn.execute(sel.replace("SELECT COUNT(*) n FROM", "DELETE FROM"))
            n1 += cnt
            if cnt:
                ok(f"{label} {cnt}건 " + ("(삭제 예정)" if dry else "삭제"))

        # ② 퇴출 협력사 계좌 — **미지급 정산이 남아 있으면 건너뛴다**
        rs = conn.execute(
            """SELECT p.id, p.name FROM partners p
                WHERE p.status='퇴출' AND COALESCE(p.bank_account_enc,'') <> ''
                  AND NOT EXISTS (SELECT 1 FROM settlements s
                                   WHERE s.partner_id = p.id
                                     AND COALESCE(s.void_status,'') <> '취소'
                                     AND COALESCE(s.transfer_status,'') <> '이체완료')
                  --  ⚠ settlements 행만 보면 안 된다. 지급 의무는 **낙찰 시점**에
                  --    생기는데 정산행은 검수를 통과한 뒤에야 만들어진다. 그 사이
                  --    (시공중·검수대기)에 퇴출된 업체는 '정산행이 없다'는 이유로
                  --    계좌가 지워지고, 공사를 마친 뒤 지급 단계에서 막힌다.
                  AND NOT EXISTS (SELECT 1 FROM cases c
                                   WHERE c.partner_id = p.id
                                     AND c.status IN ('시공중','완료보고지연',
                                                      '검수대기','정산진행'))"""
        ).fetchall()
        for r in rs:
            if not dry:
                conn.execute(
                    "UPDATE partners SET bank_account_enc='', bank_account_idx='', "
                    "       bank_holder='', bank_name='' WHERE id=?", (r["id"],))
            n2 += 1
        if n2:
            ok(f"퇴출 협력사 계좌 {n2}건 " + ("(소거 예정)" if dry else "소거"))

        # ③ 완료 사건의 피해자 정보 — 하자담보기간 만료 후
        #  ★ **열린 하자가 있으면 파기하지 않는다.**
        #    보증 만료 당일까지 하자 접수가 열려 있는데(app.py `left >= 0`),
        #    조건이 '완료 + 보증만료' 뿐이라 재시공이 진행 중인 사건의
        #    피해자 연락처와 진행조회 링크까지 지워졌다 — 그 순간부터
        #    재시공 일정을 안내할 수단이 사라진다.
        sel3 = ("SELECT COUNT(*) n FROM cases "
                " WHERE status='완료' AND completed_at IS NOT NULL "
                "   AND (COALESCE(victim_name,'') <> '' OR COALESCE(victim_phone,'') <> '') "
                "   AND " + _WEND + " < date('now','+9 hours')"
                "   AND NOT EXISTS (SELECT 1 FROM defects d WHERE d.case_id = cases.id "
                "                    AND COALESCE(d.status,'') NOT IN ('완료','반려'))")
        n3 = conn.execute(sel3).fetchone()["n"]
        #  ⚠⚠ [라운드179] 여기만 not dry 로 막으면 바로 아래 ③-1·③-1-2(n3b·n3c)가
        #    "victim_name·victim_phone 가 이미 비어 있는 사건"을 찾는데, 미리보기는
        #    이 UPDATE 를 건너뛰므로 그 조건이 실행 전까지 영원히 거짓이다 —
        #    미리보기가 n3b·n3c 를 항상 0건으로 보여준다(실측: 격리 사본에서
        #    미리보기 2건 vs 실제 실행 7건). dry 여부와 무관하게 실행하고,
        #    함수 끝에서 dry 면 통째로 rollback 한다(2119행 부근) — 이 함수는
        #    한 트랜잭션 안에서 커밋을 한 번만 하므로 안전하다.
        if n3:
            conn.execute(
                "UPDATE cases SET victim_name=NULL, victim_phone=NULL "
                " WHERE status='완료' AND completed_at IS NOT NULL "
                "   AND (COALESCE(victim_name,'') <> '' OR COALESCE(victim_phone,'') <> '') "
                "   AND " + _WEND + " < date('now','+9 hours')"
                "   AND NOT EXISTS (SELECT 1 FROM defects d WHERE d.case_id = cases.id "
                "                    AND COALESCE(d.status,'') NOT IN ('완료','반려'))")
        if n3:
            ok(f"피해자 정보 {n3}건 " + ("(파기 예정)" if dry else "파기"))

        # ③-1 **알림에 남은 사본까지 지운다.**
        #  ⚠ cases 의 이름·전화만 지우면 파기가 끝난 게 아니다.
        #    피해자 안내 문자는 notifications.target 에 **휴대전화 원문**이,
        #    message 에 진행조회 절대주소(/track/토큰)가 그대로 들어간다.
        #    한 사건에 조회링크 발급·낙찰·완료로 여러 건이 쌓인다.
        #    cases.track_token 도 남으면 그 링크는 아직 열린다.
        _nwhere = (" WHERE case_id IN (SELECT id FROM cases"
                   "                    WHERE status='완료' AND completed_at IS NOT NULL"
                   "                      AND COALESCE(victim_name,'')='' "
                   "                      AND COALESCE(victim_phone,'')='' "
                   "                      AND " + _WEND + " < date('now','+9 hours'))"
                   "   AND ntype='피해자안내'")
        n3b = conn.execute("SELECT COUNT(*) n FROM notifications" + _nwhere).fetchone()["n"]
        if n3b and not dry:
            #  기록 자체는 남긴다(언제 무엇을 안내했는지는 증적이다) — **식별자만** 지운다.
            conn.execute(
                "UPDATE notifications SET target='(파기됨)', "
                "       message='(피해자 안내 문자 — 개인정보 파기로 본문 삭제)'" + _nwhere)
        if n3b:
            ok(f"피해자 안내 알림 {n3b}건 " + ("(본문 파기 예정)" if dry else "본문 파기"))

        # ③-1-2 진행조회 토큰도 무효화한다(살아 있으면 링크가 계속 열린다)
        _twhere = (" WHERE status='완료' AND completed_at IS NOT NULL"
                   "   AND COALESCE(track_token,'') <> ''"
                   "   AND COALESCE(victim_name,'')='' AND COALESCE(victim_phone,'')='' "
                   "   AND " + _WEND + " < date('now','+9 hours')")
        n3c = conn.execute("SELECT COUNT(*) n FROM cases" + _twhere).fetchone()["n"]
        if n3c and not dry:
            conn.execute("UPDATE cases SET track_token=NULL" + _twhere)
        if n3c:
            ok(f"진행조회 링크 {n3c}건 " + ("(무효화 예정)" if dry else "무효화"))

        # ③-3 **휴지통(uploads/_trash) 도 비운다.**
        #  ⚠ 사진을 지우면 DB 행은 사라지지만 파일은 `_trash` 로 옮겨질 뿐이고,
        #    그 뒤로는 어떤 경로도 그 파일을 보지 못한다 — go-live 는 photos 행을
        #    따라가고, 파기는 DB 만 건드린다. 사고 현장·차량번호·사람이 챍힌
        #    사진이 영구 보관된다. 처리방침은 '복구·재생할 수 없도록 안전하게
        #    삭제' 라고 공개 게시한다. 오삭제 되살리기를 위해 일정 기간은 둔다(기본 30일).
        _tkeep = int(os.environ.get("BOKGUON_TRASH_KEEP_DAYS", "30"))
        _updir = _upload_root()
        _tdir = os.path.join(_updir, "_trash")
        n3d, n3d_b = 0, 0
        if os.path.isdir(_tdir):
            import time as _tm
            _cut = _tm.time() - _tkeep * 86400
            #  ⚠ **하위 폴더까지 훑는다.** 어드민 삭제(app.py)와 prune-orphans 는
            #    rel_path 를 살려 `_trash/<사건id>/<파일>` 로 옮긴다 — 바로 아래
            #    파일만 보면 그 중첩분이 **영구히 안 지워진다**(파기 미이행).
            for _dp, _dirs, _fs in os.walk(_tdir):
                for _f in _fs:
                    _p = os.path.join(_dp, _f)
                    try:
                        if not os.path.isfile(_p) or os.path.getmtime(_p) > _cut:
                            continue
                        _sz = os.path.getsize(_p)
                        if not dry:
                            os.remove(_p)
                        n3d += 1
                        n3d_b += _sz
                    except OSError:
                        pass
        if n3d:
            ok(f"휴지통 사진 {n3d}건({n3d_b // 1024:,}KB) "
               + (f"(파기 예정 — {_tkeep}일 경과분)" if dry
                  else f"파기 ({_tkeep}일 경과분)"))

        # ③-2 **끝났는데 '완료'가 아닌 사건** — 취소·미수선종결·유찰.
        #  ⚠ ③은 `status='완료' AND completed_at IS NOT NULL` 만 본다. 그런데
        #    completed_at 을 채우는 곳은 완료 보고 한 군데뿐이라, 취소·미수선종결·
        #    유찰로 끝난 사건의 피해자 성명·연락처는 **어떤 시점에도 파기 대상에
        #    들어가지 않는다**(보유기간 초과 — 처리방침 위반).
        #    이 사건들은 시공이 없어 하자담보책임도 없으므로 종료 시각 기준으로 센다.
        _keep = int(os.environ.get("BOKGUON_VICTIM_KEEP_DAYS", "90"))
        _w4 = (" WHERE status IN ('취소','미수선종결','유찰') "
               "   AND (COALESCE(victim_name,'') <> '' OR COALESCE(victim_phone,'') <> '') "
               "   AND datetime(COALESCE(status_at, created_at), '+' || ? || ' days')"
               "       < datetime('now','+9 hours')")
        n4 = conn.execute("SELECT COUNT(*) n FROM cases" + _w4, (_keep,)).fetchone()["n"]
        #  ⚠⚠ [라운드179] n3 와 같은 이유 — 바로 아래 n4b·n4c 가 이 UPDATE 이후의
        #    상태(victim_name·victim_phone 빈값)를 찾는다. 미리보기라고 건너뛰면
        #    n4b·n4c 가 항상 0건으로 보인다.
        if n4:
            conn.execute("UPDATE cases SET victim_name=NULL, victim_phone=NULL" + _w4,
                         (_keep,))
        if n4:
            ok(f"종료(취소·미수선·유찰) 사건 피해자 정보 {n4}건 "
               + ("(파기 예정)" if dry else "파기") + f" — 보관 {_keep}일")

        #  ⚠⚠ [라운드142] ③-1/③-1-2 와 똑같은 이유(1924행 주석)가 이 버킷에도
        #    그대로 적용되는데 빠져 있었다 — cases 의 이름·전화만 지우고 끝내면
        #    notifications 에 남은 원문 전화번호·진행조회 링크, cases.track_token
        #    이 살아 있는 채로 남는다. 취소·미수선종결·유찰로 끝난 사건도 완료
        #    사건과 똑같이 "닫힌 사건"이라 같은 파기를 받아야 한다.
        _n4nwhere = (" WHERE case_id IN (SELECT id FROM cases"
                     "                    WHERE status IN ('취소','미수선종결','유찰')"
                     "                      AND COALESCE(victim_name,'')='' "
                     "                      AND COALESCE(victim_phone,'')='' "
                     "                      AND datetime(COALESCE(status_at, created_at), '+' || ? || ' days')"
                     "                          < datetime('now','+9 hours'))"
                     "   AND ntype='피해자안내'")
        n4b = conn.execute("SELECT COUNT(*) n FROM notifications" + _n4nwhere, (_keep,)).fetchone()["n"]
        if n4b and not dry:
            conn.execute(
                "UPDATE notifications SET target='(파기됨)', "
                "       message='(피해자 안내 문자 — 개인정보 파기로 본문 삭제)'" + _n4nwhere, (_keep,))
        if n4b:
            ok(f"종료(취소·미수선·유찰) 피해자 안내 알림 {n4b}건 " + ("(본문 파기 예정)" if dry else "본문 파기"))

        _n4twhere = (" WHERE status IN ('취소','미수선종결','유찰')"
                     "   AND COALESCE(track_token,'') <> ''"
                     "   AND COALESCE(victim_name,'')='' AND COALESCE(victim_phone,'')='' "
                     "   AND datetime(COALESCE(status_at, created_at), '+' || ? || ' days')"
                     "       < datetime('now','+9 hours')")
        n4c = conn.execute("SELECT COUNT(*) n FROM cases" + _n4twhere, (_keep,)).fetchone()["n"]
        if n4c and not dry:
            conn.execute("UPDATE cases SET track_token=NULL" + _n4twhere, (_keep,))
        if n4c:
            ok(f"종료(취소·미수선·유찰) 진행조회 링크 {n4c}건 " + ("(무효화 예정)" if dry else "무효화"))

        # ⑤ **하자보수 관련 기록** — 처리방침 제3조가 "준공일로부터 하자담보책임기간
        #    (24개월) 만료 후 3년"이라고 명시했는데, 그걸 실행하는 코드가 이 함수
        #    어디에도 없었다(146라운드 실측: defects 행이 이 시점을 3년 넘게 지나도
        #    영구히 그대로 남았다). 완료(_WEND, app.py _warranty_left 와 같은 말일
        #    보정)까지 이미 세 곳에 있어 그대로 재사용하고, +3년만 더한다.
        #  ⚠ **행 자체는 지우지 않는다.** severity·cost_bearer·status 는
        #    partner_rating() 의 하자 감점 집계가 계속 참조하는 통계값이라(귀책
        #    하자 건수·등급별 카운트), 행을 통째로 지우면 오래된 협력사일수록
        #    감점 이력이 사라져 평점이 부당하게 좋아 보인다. 개인/식별 소지가
        #    있는 자유텍스트(제목·내용·처리결과·접수자)만 지운다 — ②③ 버킷과
        #    같은 원칙(레코드는 남기고 개인정보만 소거).
        _dwhere = (" WHERE case_id IN (SELECT id FROM cases"
                   "                    WHERE completed_at IS NOT NULL"
                   "                      AND " + _DEFECT_PURGE_AT +
                   "                          < datetime('now','+9 hours'))"
                   "   AND (COALESCE(title,'')<>'' OR COALESCE(content,'')<>'' "
                   "        OR COALESCE(resolution,'')<>'' OR COALESCE(reporter,'')<>'')")
        n5 = conn.execute("SELECT COUNT(*) n FROM defects" + _dwhere).fetchone()["n"]
        if n5 and not dry:
            conn.execute(
                "UPDATE defects SET title='(파기됨)', content=NULL, resolution=NULL, "
                "       reporter='(파기됨)'" + _dwhere)
        if n5:
            ok(f"하자보수 기록(제목·내용·처리결과·접수자) {n5}건 "
               + ("(파기 예정)" if dry else "파기") + " — 준공+하자담보 만료 후 3년")

        # ⑥ **해피콜 기록** — 495라운드 실측: feedback 은 상담원이 통화 중
        #    피해자가 밝힌 이름·주소·불만 등을 그대로 받아 적는 자유텍스트라
        #    (app.py api_happy_call_add), ③이 지우는 victim_name·victim_phone과
        #    같은 성격의 개인정보를 담을 수 있는데, 이 함수 어디에도
        #    happy_calls 가 등장하지 않았다 — 사건 쪽 이름·연락처를 지운
        #    뒤에도 해피콜 화면(app.py api_happy_calls, GET /api/happy-calls,
        #    h.* 그대로 반환)에서는 그 원문이 영원히 그대로 남았다(재현:
        #    cases.victim_name/phone 은 NULL이 됐는데 같은 사건의
        #    happy_calls.feedback 은 파기 전 원문 그대로 생존).
        #  ⚠ **행 자체는 지우지 않는다.** score·method·created_at·partner_id 는
        #    partner_rating() 의 평점 집계가 참조하는 통계값이다(⑤와 같은
        #    원칙) — 자유텍스트(feedback·called_by)만 지운다.
        #  하자보수기록(⑤)과 달리 이건 분쟁대응용 하자기록이 아니라 순수
        #    만족도 확인이므로, +3년 연장 없이 피해자 정보(③)와 같은 기준
        #    (_WEND, 하자담보 만료)을 쓴다.
        _hwhere = (" WHERE case_id IN (SELECT id FROM cases"
                   "                    WHERE completed_at IS NOT NULL"
                   "                      AND " + _WEND + " < date('now','+9 hours'))"
                   "   AND (COALESCE(feedback,'')<>'' OR COALESCE(called_by,'')<>'')")
        n6 = conn.execute("SELECT COUNT(*) n FROM happy_calls" + _hwhere).fetchone()["n"]
        if n6 and not dry:
            conn.execute("UPDATE happy_calls SET feedback=NULL, called_by=NULL" + _hwhere)
        if n6:
            ok(f"해피콜 기록(응대내용·상담원) {n6}건 "
               + ("(파기 예정)" if dry else "파기") + " — 하자담보 만료 후")

        #  ⚠⚠ [라운드109] total 이 n3b·n3c·n3d(알림본문 파기·조회링크 무효화·휴지통
        #    실삭제)를 빠뜨렸다 — 셋 다 실제로 파괴적인 동작인데(파일은 os.remove
        #    로 영구 삭제) 이 셋만 지워지면 total==0 이 되어 DB.log 자체가 안 돌고,
        #    콘솔은 방금 지운 바로 다음 줄에 "파기 대상이 없습니다"를 찍었다.
        #    실측: uploads/_trash 에 파일 209개가 쌓여 있는데 activity_log 의
        #    '개인정보 파기'는 0행이었다. 로그 문자열도 n4(종료 사건 피해자정보)를
        #    빠뜨려, n4 만 지워진 회차는 로그는 남아도 본문이 "전부 0건"이라
        #    실제로 지운 사실과 반대로 읽혔다.
        total = n1 + n2 + n3 + n3b + n3c + n3d + n4 + n4b + n4c + n5 + n6
        if not dry and total:
            DB.log(conn, "시스템", "개인정보 파기",
                   f"문의·신청 {n1} · 계좌 {n2} · 피해자정보 {n3} · "
                   f"알림본문 {n3b} · 조회링크 {n3c} · 휴지통사진 {n3d} · "
                   f"종료사건 피해자정보 {n4} · 종료사건 알림본문 {n4b} · "
                   f"종료사건 조회링크 {n4c} · 하자보수기록 {n5} · 해피콜기록 {n6} "
                   f"(기준: 문의 1년 / 계좌 퇴출·미지급없음 / 피해자·해피콜 하자담보 만료 / "
                   f"하자보수기록 준공+하자담보 만료 후 3년)")
        if not dry:
            #  ★ 예약 실행이 실제로 돌았다는 표식 — cli_sweep 과 같은 이유다.
            #    지울 게 없는 주(총 0건)에도 "돌긴 돌았다"는 남아야, manage.py check
            #    가 "예약이 아예 안 걸려 있다"와 "이번 주는 대상이 없었다"를 구분한다.
            conn.execute(
                "INSERT INTO job_locks(name, last_run_at) VALUES('prune_personal', ?) "
                " ON CONFLICT(name) DO UPDATE SET last_run_at=excluded.last_run_at",
                (DB.now(),))
        #  ⚠⚠ [라운드179] n3·n4 의 UPDATE 를 이제 dry 여부와 무관하게 실행하므로,
        #    미리보기에서는 그 결과를 절대 남기면 안 된다 — commit 대신 rollback.
        #    이 함수는 BEGIN 을 직접 열지 않고(sqlite3 기본 지연 트랜잭션) 여기가
        #    유일한 커밋 지점이라 안전하다(중간에 conn.commit() 이 없다).
        if dry:
            conn.rollback()
        else:
            conn.commit()
        if not total:
            ok("파기 대상이 없습니다.")
        elif dry:
            warn(f"미리보기 — 실제로는 아무것도 지우지 않았습니다. 총 {total}건이 대상입니다.")
        else:
            ok(f"총 {total}건 파기 완료 — 증적을 감사로그에 남겼습니다.")
    #  ⚠⚠ [라운드188] 형제 명령 prune-orphans·go-live 는 이 자리에 전부
    #    except sqlite3.Error 를 두는데 이 함수만 없었다 — commit/rollback 전에
    #    죽으면 sqlite3 가 close() 에서 미완료 트랜잭션을 알아서 버리므로 실제
    #    데이터 위험은 없지만, 원인이 안 찍힌 채 날 traceback 대신 형제와 같은
    #    방식으로 실패를 알린다.
    except sqlite3.Error as e:
        conn.rollback()
        bad(f"파기 실패: {e}")
        return 1
    finally:
        conn.close()
    return 0


def cmd_mark_smoke_demo(argv):
    """스모크·검증이 만든 데이터에 **데모 표식**을 붙인다.

    go-live 는 `is_demo=1` 인 행만 지운다. 그런데 스모크 테스트가 만든 사건은
    표식 없이(is_demo=0) 들어가 있어서, 실테스트 첫날 정산 화면에
    거래 9,650만원·'이체완료' 14건이 **실적처럼** 뜬다.
    실제로 이체된 돈은 0원이고, 그 업체는 계좌조차 없다.
    보험사 담당자에게 그 화면을 보이면 설명할 방법이 없다.

    --dry : 무엇이 바뀔지만 본다(기본은 실제 표식)
    """
    dry = "--dry" in argv
    head("스모크·검증 데이터 표식" + (" (미리보기)" if dry else ""))
    #  주소·접수번호가 명백히 검증용인 것만. 실사건을 지우지 않도록 좁게 잡는다.
    WHERE = ("""(COALESCE(address,'') LIKE '스모크%'
                 OR COALESCE(address,'') = '검증용 주소'
                 OR case_no LIKE 'E2E%' OR case_no LIKE 'FAIR%'
                 OR case_no LIKE 'HTTPFAIR%' OR case_no LIKE 'OVRD%'
                 OR case_no LIKE 'ADDRCHK%' OR case_no LIKE 'DSP%')
                AND COALESCE(is_demo,0)=0""")
    conn = DB.get_db()
    try:
        rows = conn.execute(
            f"SELECT id, case_no, address FROM cases WHERE {WHERE} ORDER BY id").fetchall()
        if not rows:
            ok("표식을 붙일 검증 데이터가 없습니다.")
            return 0
        for r in rows[:12]:
            print(f"   · {r['case_no']:22} {(r['address'] or '')[:30]}")
        if len(rows) > 12:
            print(f"   … 외 {len(rows) - 12}건")
        if dry:
            warn(f"{len(rows)}건에 표식을 붙일 예정입니다 (--dry 라 저장하지 않음)")
            return 0
        ids = [r["id"] for r in rows]
        marks = ",".join("?" * len(ids))
        conn.execute(f"UPDATE cases SET is_demo=1 WHERE id IN ({marks})", ids)
        #  ⚠⚠ [라운드99] 자식표 목록을 여기서 또 손으로 나열했었다 —
        #    db.py 의 정본 캐스케이드(_backfill_child_is_demo, 23곳이 참조하는
        #    bids·dispatches·field_agreements·notifications·settlements)와
        #    따로 노는 두 번째 사본이었고, 그마저도 bids·field_agreements·
        #    notifications 가 빠지고 is_demo 컬럼조차 없는 photos 는 헛줄이었다
        #    (auctions 도 같은 컬럼이 없어 매번 조용히 실패했다). 사건에 표식을
        #    붙인 직후 정본 함수를 그대로 불러 그 하나의 목록만 유지한다.
        DB._backfill_child_is_demo(conn)
        DB.log(conn, "정비도구", "스모크 데이터 표식", f"사건 {len(ids)}건")
        conn.commit()
        ok(f"{len(ids)}건에 표식을 붙였습니다. 이제 `go-live` 가 함께 지웁니다.")
    finally:
        conn.close()
    return 0


#  없어진 사건을 가리킬 수 있는 자식 표들 — 점검(check)과 정리(prune-orphans)가
#  이 한 목록을 공유한다. 새 표를 만들면 **여기에만** 추가하면 된다.
#  **데모 발주처에 속한 사건**을 찾는 술어. 점검(check)과 정리(go-live)가 함께 쓴다.
#  ⚠ is_demo 표식만 보면 검증이 만든 사건을 놓친다 — 테스트가 API 로 만든 사건에는
#    표식이 안 붙기 때문이다. 발주처가 데모면 그 사건은 실사건일 수 없다.
DEMO_CASE_SQL = ("""
    COALESCE(is_demo,0)=1
 OR insurer_id IN (SELECT id FROM insurers WHERE COALESCE(is_demo,0)=1)
""")


#  case_id 가 아닌 **다른 열쇠로만 부모에 닿는** 표들.
#  ⚠ 고아 점검이 case_id 기준이라 이쪽은 통째로 안 보였다 —
#    사건을 지워도, 사진을 지워도 어디에도 안 잡히는 사각지대였다.
#    (실측: 운영 DB 에 ai_reviews 고아 5건. AI 정확도 모집단이 없는 사진을 센다.)
FK_CHILD_TABLES = (
    ("ai_reviews", "photo_id", "photos"),
    ("damage_reads", "photo_id", "photos"),
    ("defect_photos", "photo_id", "photos"),
    ("defect_photos", "defect_id", "defects"),
    ("dispatch_calls", "dispatch_id", "dispatches"),
    #  ⚠⚠ [라운드158] bids 는 case_id 가 없어(auction_id 로만 사건에 닿는다)
    #    CASE_CHILD_TABLES 에 못 들어가고, 이 목록에도 없어 통째로 사각지대였다.
    ("bids", "auction_id", "auctions"),
)


CASE_CHILD_TABLES = (
    "dispatches", "field_agreements", "photos", "settlements",
    "est_outcome", "damage_reads", "auctions",
    #  ⚠ 아래 넷은 종전 점검 목록에 없었다 — 고아가 있어도 초록이었다.
    "work_lots", "bid_events", "change_orders", "defects",
    #  ⚠⚠ [라운드158] 이 셋도 case_id 로 사건에 붙는데 빠져 있었다 — 실운영
    #    DB 에 notifications 만 34건의 고아(없어진 사건을 가리키는 미확인
    #    알림)가 이미 쌓여 있었고, 그중 14곳은 지금도 로그인 가능한 활성
    #    협력사라 포털의 "미확인" 배지에 그대로 노출되고 있었다(실측).
    "notifications", "schedule_events", "contract_gate_log",
    #  ⚠⚠ [433라운드] happy_calls(case_id NOT NULL UNIQUE, db.py:802)도 이
    #    목록에 없었다 — go-live(cmd_go_live)는 삭제 시 이 표를 조건 없이
    #    통째로 비워 우연히 사각지대를 피하지만, 운영자가 사건 하나를 직접
    #    SQL로 지우는 경우(158라운드가 이미 "실제 사고"로 증언한 바로 그
    #    시나리오)엔 이 표만 고아로 남아 check·prune-orphans 둘 다 못 잡고,
    #    partner_rating() 의 해피콜 평균에 삭제된 사건의 점수가 영구히 남는다.
    "happy_calls",
)


def cmd_prune_orphans(argv):
    """없어진 사건을 가리키는 자식 행을 지운다.

    ⚠ 왜 필요한가 — check 가 "정리가 반쪽입니다" 라고 경고하는데 그 정리를 할
      명령이 없었다. 매번 같은 경고를 보면서 아무것도 못 하면 그 경고는 배경 소음이
      되고, 정작 진짜 신호가 묻힌다.
    ⚠ **기본은 미리보기다.** 지우려면 --yes 를 붙인다.
      사건이 지워진 뒤 남은 행은 어디서도 읽히지 않지만(사건 id 로만 닿는다),
      통계·AI 정확도 모집단에는 계속 섞인다.
    """
    dry = "--yes" not in argv
    head("고아 행 정리" + (" (미리보기)" if dry else ""))
    show_db_target()
    conn = DB.get_db()
    total, detail = 0, []
    _photo_rel = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        #  (표, 열쇠, 부모표) 로 통일해 한 루프에서 처리한다.
        _pairs = [(t, "case_id", "cases") for t in CASE_CHILD_TABLES] + list(FK_CHILD_TABLES)
        for t, _col, _parent in _pairs:
            try:
                n = conn.execute(
                    f"SELECT COUNT(*) n FROM {t} "
                    f" WHERE {_col} IS NOT NULL "
                    f"   AND {_col} NOT IN (SELECT id FROM {_parent})").fetchone()["n"]
            except sqlite3.Error:
                continue          # 그 표가 없는 배포본
            if not n:
                continue
            detail.append((f"{t}.{_col}", n))
            total += n
            #  ★ 사진은 **지우기 전에 경로를 챙긴다.** 행이 사라진 뒤에는
            #    어느 파일이 그 행의 것이었는지 알 길이 없다.
            if t == "photos" and not dry:
                try:
                    _photo_rel += [r[0] for r in conn.execute(
                        f"SELECT rel_path FROM photos "
                        f" WHERE {_col} IS NOT NULL "
                        f"   AND {_col} NOT IN (SELECT id FROM {_parent}) "
                        f"   AND COALESCE(rel_path,'') <> ''")]
                except sqlite3.Error:
                    pass
            if not dry:
                conn.execute(
                    f"DELETE FROM {t} "
                    f" WHERE {_col} IS NOT NULL "
                    f"   AND {_col} NOT IN (SELECT id FROM {_parent})")
        if not dry and total:
            DB.log(conn, "정비도구", "고아 행 정리",
                   ", ".join(f"{t} {n}건" for t, n in detail))
        conn.commit()
    except sqlite3.Error as e:
        conn.rollback()
        bad(f"정리 실패: {e}")
        return 1
    finally:
        conn.close()

    #  ★ **사진 파일도 함께 치운다.** 주석은 "지우기 전에 경로를 확보해 둔다"
    #    고 적혀 있었지만 실제로는 행만 지우고 파일은 영구히 남았다 —
    #    사건이 사라진 뒤라 어느 화면에도 안 뜨는데 디스크와 매일 백업에는
    #    계속 쌓인다(개인정보 파기 미이행).
    #    **지우지 않고 휴지통으로 옮긴다** — 사진은 분쟁 자료라 되돌릴 여지를 둔다.
    #  ⚠ 반드시 commit·close **뒤에** 옮긴다 — 커밋 전에 옮기면, DB 삭제가
    #    롤백될 때 행은 되살아나는데 파일은 이미 옮겨져 있어 "행은 있는데
    #    파일이 없는" 상태가 된다(실제 삭제 라우트 api_photo_delete 와 같은 원칙).
    if not dry and _photo_rel:
        _moved = 0
        _root = _upload_root()
        _tr = os.path.join(_root, "_trash")
        for _rp in _photo_rel:
            _src = os.path.join(_root, str(_rp).replace("/", os.sep))
            if not os.path.isfile(_src):
                continue
            _dst = os.path.join(_tr, str(_rp).replace("/", os.sep))
            try:
                os.makedirs(os.path.dirname(_dst), exist_ok=True)
                shutil.move(_src, _dst)
                #  ⚠⚠ [라운드110] shutil.move 도 원본 mtime 을 보존한다 —
                #    prune-personal 의 30일 파기 판정을 무력화한다(같은 원인, app.py
                #    _photo_to_trash 참조).
                os.utime(_dst, None)
                _moved += 1
            except OSError:
                pass
        if _moved:
            print(f"  사진 파일 {_moved}개를 휴지통(_trash)으로 옮겼습니다 — "
                  f"31일 뒤 prune-personal 이 지웁니다.")

    if not total:
        ok("고아 행이 없습니다.")
        return 0
    for t, n in detail:
        print(f"    · {t:<20} {n:>5}건")
    if dry:
        warn(f"총 {total}건 — 지우려면  python manage.py prune-orphans --yes")
        return 0
    ok(f"고아 행 {total}건 정리 완료")
    return 0


COMMANDS = {
    "gen-keys": cmd_gen_keys, "check": cmd_check, "init": cmd_init, "migrate": cmd_migrate,
    "create-admin": cmd_create_admin, "create-insurer": cmd_create_insurer, "reset-pw": cmd_reset_pw,
    "set-fee": cmd_set_fee,
    "backup": cmd_backup, "restore": cmd_restore, "prune-logs": cmd_prune_logs, "prune-personal": cmd_prune_personal, "stats": cmd_stats,
    "show-info": cmd_show_info, "set-info": cmd_set_info, "go-live": cmd_go_live,
    "sweep": cmd_sweep, "install-scheduler": cmd_install_scheduler,
    "mark-smoke-demo": cmd_mark_smoke_demo,
    "prune-orphans": cmd_prune_orphans,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        bad(f"알 수 없는 명령: {cmd}")
        print(__doc__)
        return 1
    #  ⚠⚠ [라운드568] 모든 명령이 실제로 거치는 유일한 지점(여기)에 try 가 없었다.
    #    round557 이 cmd_sweep() **안에서만** 고친 것과 똑같은 결함이 이 바깥
    #    경계에는 그대로 남아 있었다 — deploy/windows_setup.ps1 이 등록하는
    #    예약작업 중 backup 을 제외한 prune-logs·prune-personal 도 sweep 전용
    #    스크립트와 똑같이 pythonw.exe 를 **표준출력 리다이렉트 없이** 부른다
    #    (실측: 284·315·327행 New-ScheduledTaskAction 셋 다 $vpyw 뿐, ">>" 없음).
    #    그런데 cmd_prune_logs() 본문(DELETE 두 건 + commit)은 try 자체가 아예
    #    없고, cmd_prune_personal() 은 sqlite3.Error 만 잡아(그 안에서 도는
    #    int(os.environ.get(...)) 두 곳이 던지는 ValueError 등은 그대로
    #    새나간다) 실패해도 콘솔 한 줄(bad())뿐 파일엔 아무것도 안 남는다 —
    #    이 세션 브리핑이 실제로 자주 관찰된다고 명시한 WAL 동시쓰기 경합
    #    한 번이면 개인정보 보호법 §21 이 요구하는 주간 파기가 콘솔도 없는
    #    pythonw 아래서 흔적 없이 죽는다. manage.py check 의 job_locks 정체
    #    감지(796·835행)가 최대 10일 뒤 "멈췄다"는 보여주지만 **왜** 멈췄는지는
    #    여전히 안 보인다(사후 부검 불가) — round557 자신이 짚은 바로 그 증상.
    #    명령마다 따로 감싸는 대신, 모든 명령이 통과하는 이 한 지점에서
    #    cmd_sweep 이 이미 세운 처방(app 로거로 전체 트레이스백을 남기고,
    #    짧은 이유는 화면에도 찍고, 종료코드는 실패로)을 그대로 적용한다 —
    #    앞으로 추가될 명령에도 자동으로 적용되고, 기존 각 명령의 개별
    #    처리(cmd_backup·cmd_prune_personal 의 좁은 except 등)는 그대로 먼저
    #    실행되므로 더 상세한 메시지를 낼 기회를 뺏지 않는다(이건 그 아래를
    #    빠져나온 것만 잡는 마지막 안전망이다).
    try:
        return COMMANDS[cmd](sys.argv[2:]) or 0
    except Exception as e:
        try:
            import app as A
            A.app.logger.exception(f"manage.py {cmd} 실행 중 처리되지 않은 예외로 중단됨")
        except Exception:
            pass
        bad(f"명령 실행 중 처리되지 않은 오류로 중단됨 — {type(e).__name__}: {e}")
        warn("전체 트레이스백을 " + os.environ.get("BOKGUON_LOG_FILE", "logs/manage.log")
             + " 에 남겼습니다(app 로거를 못 불러왔다면 이 줄이 유일한 기록입니다).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
