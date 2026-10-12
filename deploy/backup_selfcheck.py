# -*- coding: utf-8 -*-
"""백업이 **정말로** 만들어졌는지 확인한다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

왜 필요한가 — 예전에 일일백업 배치가 아무 일도 안 하면서 종료코드 0(성공)을
돌려주던 적이 있다. 리다이렉션 대상 경로가 망가져 cmd 가 명령을 통째로
건너뛰었는데, 배치는 끝까지 진행돼 '성공'으로 보고했다.
작업 스케줄러 화면에는 계속 초록불이었고, 그동안 백업은 없었다.

**종료코드는 일이 일어났다는 증거가 아니다.** 그래서 파일을 직접 본다.
  · 오늘 날짜 백업 파일이 실제로 있는가
  · 크기가 말이 되는가(빈 파일·잘린 파일이 아닌가)
  · SQLite 로 열리고 무결성 검사를 통과하는가

하나라도 어긋나면 1을 돌려준다 → 배치가 실패로 끝나고, 스케줄러에 빨간불이 뜬다.
"""
import os
import subprocess
import sys
import sqlite3
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

#  ⚠⚠ [라운드311] 이 스크립트는 지금까지 .env 를 전혀 읽지 않았다 — BOKGUON_BACKUP_DIR
#    을 커스텀 값으로 쓰는 배포에서도 항상 자기 fallback 경로(DB 옆 backups/)만 봤다.
#    실측: 일일백업.bat 는 manage.py backup 을 부른 뒤 이 스크립트를 그 **같은 배치
#    안에서** 잇달아 호출하지만, manage.py 쪽 프로세스가 os.environ 에 심은 값은
#    그 프로세스가 끝나면 사라진다 — 부모 셸에도, 형제 자식 프로세스에도 전파되지
#    않는다(프로세스별 환경변수 격리). app.py/manage.py 가 각자 첫 줄에서
#    envload.load_dotenv() 를 부르는 것과 똑같이, 이 스크립트도 스스로 불러야 한다.
sys.path.insert(0, ROOT)
import envload                                                       # noqa: E402
envload.load_dotenv()

_db_path = os.environ.get("BOKGUON_DB_PATH") or os.path.join(ROOT, "bokguon.db")
BACKUP_DIR = os.environ.get("BOKGUON_BACKUP_DIR") \
    or os.path.join(os.path.dirname(os.path.abspath(_db_path)), "backups")
KST = timezone(timedelta(hours=9))

#  갓 만든 백업이 이보다 작으면 뭔가 잘못된 것이다(빈 DB 는 수십 KB).
MIN_BYTES = 100 * 1024
#  '오늘 것'의 허용 범위 — 03:30 에 도는 배치가 자정을 넘겨 끝나는 경우까지 감안한다.
MAX_AGE_HOURS = 26


def fail(msg):
    print(f"  ✖ 자가점검 실패 — {msg}")
    return 1


def _has_inherited_acl(path):
    """이 파일에 상속된(icacls 로 안 좁혀진) 권한이 남아있는지 확인.

    ⚠⚠ [라운드454] manage.py::cmd_backup() 이 .db 본체를 icacls 로 좁히지만,
       그 icacls 호출 자신이 실패해도(계정명 조회 실패 등) 경고만 찍고
       종료코드엔 안 남는다 — 일일백업.bat 는 errorlevel 만 보므로 이 실패가
       조용히 로그 파일에 묻힌다. 그 실패를 여기서 대신 잡아낸다.
       (I) 표기는 icacls 자신의 고유 마커라 콘솔 코드페이지와 무관하게
       바이트로 안전하게 매치된다.
    """
    try:
        r = subprocess.run(["icacls", path], capture_output=True, timeout=10)
    except Exception:
        return None  # icacls 를 못 돌리면(비Windows 등) 판단 보류 — 오탐 방지
    return b"(I)" in r.stdout


def main():
    print("\n백업 자가점검")
    print("─" * 62)
    if not os.path.isdir(BACKUP_DIR):
        return fail(f"백업 폴더가 없습니다: {BACKUP_DIR}")

    #  ⚠⚠ [라운드309] .db 만 셌다 — 리눅스는 backup.sh/manage.py 가 gzip 으로
    #    .db.gz 를 남기는데(용량 절감), 이 필터가 그걸 못 보면 정상 운영
    #    중인 리눅스 서버에서도 영원히 "0개"가 뜬다. manage.py 의 cmd_check
    #    가 이미 같은 이유로 두 확장자를 함께 본다(그 코드의 주석과 같은 말).
    files = [os.path.join(BACKUP_DIR, f) for f in os.listdir(BACKUP_DIR)
             if f.startswith("bokguon_") and (f.endswith(".db") or f.endswith(".db.gz"))]
    if not files:
        return fail("백업 파일이 하나도 없습니다")

    #  ⚠⚠ [라운드123] "가장 최근 mtime" 만으로는 **진짜 운영 백업**이라는 보장이 없다.
    #    실측: cmd_go_live 를 격리된 스크래치 DB 에 돌리는 회귀테스트가 이 폴더에
    #    487KB 짜리(정상 100KB 기준은 통과) 데모 스냅샷을 남겼고, 그 mtime 이 정상
    #    18MB 짜리 03:30 백업보다 새것이라 이 스크립트가 그 조각을 "최신"으로 봤다
    #    (partners=0 이라 우연히 막바지에 걸렸을 뿐 — 데모가 파트너 1곳이라도
    #    시딩했으면 그대로 통과했을 것이다). 이 표는 매일 순증가만 하는 운영
    #    DB 스냅샷이라, 직전 백업의 절반에도 못 미치는 크기는 "최신"이 아니라
    #    "엉뚱한 파일"일 가능성이 압도적으로 크다.
    files.sort(key=os.path.getmtime)
    newest = files[-1]
    age = datetime.now(KST) - datetime.fromtimestamp(os.path.getmtime(newest), KST)
    size = os.path.getsize(newest)
    print(f"  최신 백업 : {os.path.basename(newest)}")
    print(f"  크기      : {size:,} bytes")
    print(f"  경과      : {age.total_seconds() / 3600:.1f}시간")

    if age > timedelta(hours=MAX_AGE_HOURS):
        return fail(f"최신 백업이 {age.days}일 {age.seconds // 3600}시간 전 것입니다 "
                    f"— 오늘 백업이 만들어지지 않았습니다")
    if size < MIN_BYTES:
        return fail(f"백업 파일이 너무 작습니다({size:,} bytes) — 잘렸을 수 있습니다")
    if len(files) >= 2:
        prev_size = os.path.getsize(files[-2])
        if prev_size > 0 and size < prev_size * 0.5:
            return fail(f"최신 백업이 직전 백업({prev_size:,} bytes)의 절반도 안 됩니다"
                        f"({size:,} bytes) — 실제 운영 스냅샷이 아니라 다른 도구가 "
                        f"남긴 파일일 수 있습니다")

    if os.name == "nt" and _has_inherited_acl(newest):
        return fail(f"백업 파일 권한이 상속돼 있습니다({os.path.basename(newest)}) — "
                    f"cmd_backup() 의 icacls 하드닝이 실패했거나 안 걸렸을 수 있습니다. "
                    f"개인정보(성명·연락처·암호화된 계좌)가 담긴 파일이라 icacls 로 "
                    f"직접 확인해 권한을 좁혀야 합니다")

    #  ⚠⚠ [라운드309] gzip 파일은 sqlite3 가 직접 못 연다 — 압축을 풀지 않고는
    #    이 아래 무결성 검사(quick_check·협력업체 수)를 할 수 없다. manage.py
    #    check 도 .db.gz 는 크기·경과만 보고 이 단계를 건너뛴다(같은 선례) —
    #    조용히 검사를 낮추지 않고, 무엇을 못 봤는지 그대로 알린다.
    if newest.endswith(".db.gz"):
        print("  ✔ 크기·경과 확인(gzip 백업 — SQLite 무결성·협력업체 수는 이 자리에서 건너뜁니다)")
        return 0

    # 열리는지·깨지지 않았는지 직접 확인한다. 파일이 있다는 것만으로는 부족하다.
    #  ⚠⚠ [라운드454] mode=ro 만으로는 부족했다 — 원본이 WAL 모드(db.py)라 그
    #    헤더 플래그가 백업 사본에도 그대로 복사되고, SQLite 는 mode=ro 로 열 때도
    #    wal-index 확인을 위해 -shm 을 새로 만든다(실측: 이 스크립트가 처음 열 때
    #    -shm/-wal 이 그 순간 생겼다). 그 사이드카는 cmd_backup() 의 icacls 하드닝을
    #    안 받고 backups/ 폴더의 상속 권한을 그대로 받는다(실측: CodexSandboxUsers
    #    (I)(RX) 확인). immutable=1 은 "아무도 이 파일을 안 바꾼다"고 선언해 그
    #    wal-index 확인 자체를 건너뛰므로 사이드카가 아예 안 생긴다.
    try:
        c = sqlite3.connect(f"file:{newest}?mode=ro&immutable=1", uri=True)
        ic = c.execute("PRAGMA quick_check").fetchone()[0]
        n = c.execute("SELECT COUNT(*) FROM partners").fetchone()[0]
        c.close()
    except sqlite3.Error as e:
        return fail(f"백업을 열 수 없습니다: {e}")
    if ic != "ok":
        return fail(f"무결성 검사 실패: {ic}")
    if not n:
        return fail("협력업체가 0곳입니다 — 빈 DB 를 백업했을 수 있습니다")

    print(f"  ✔ 무결성 ok · 협력업체 {n}곳 · 오늘 백업 확인")
    return 0


if __name__ == "__main__":
    sys.exit(main())
