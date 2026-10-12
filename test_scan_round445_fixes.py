# -*- coding: utf-8 -*-
"""스캔 445라운드 회귀 — JSON_AS_ASCII=False 가 Flask 3.x에서 죽은 설정
   키였던 결함, 1건(라운드441이 발견하고 범위 밖으로 미뤄둔 백로그).

   app.py:124에 있던 `JSON_AS_ASCII=False`는 Flask 2.x 시절 설정 키다 —
   설치된 Flask 3.1.3은 이 값을 전혀 안 읽는다(`app.config`엔 그대로
   저장되지만 실제 동작은 `app.json.ensure_ascii`가 결정하며, 그 값은
   여전히 기본값 True로 남아있었다). 그래서 지금까지 모든 JSON 응답의
   한글이 의도와 달리 유니코드 이스케이프(\\uXXXX 형태)로 나갔다 — 기능상
   차이는 없지만(모든 JSON 파서가 두 표기를 동일하게 디코딩) 응답 크기
   (한글 1자당 6바이트 대 UTF-8 3바이트)와 로그·디버깅 가독성 문제였다.

   고침: 죽은 `JSON_AS_ASCII=False` 설정을 제거하고 Flask 3.x 방식인
   `app.json.ensure_ascii = False`로 교체 — 기능적으로는 새 결함이 아니라
   "원래 의도를 실제로 살리는" 트레이드오프 없는 개선.

   settlements 테이블에도 같은 유형(SELECT * 무화이트리스트)의 스키마
   드리프트가 있음을 이번에 재확인했으나, 애초 예상(라운드443, 1곳)과
   달리 실제로는 14곳에 퍼져 있고 settlements 자체엔 계좌정보 등 진짜
   민감 컬럼이 없음(PRAGMA로 24개 컬럼 전부 확인)이 확정돼 있어 — 굳이
   14곳을 전부 고치는 것은 이번 백로그 처리의 원래 범위를 크게 벗어나는
   별도 작업이라 이번에도 그대로 남겨 둔다(다음 라운드 후보, 낮은
   우선순위 유지 — 이번 라운드에서 규모를 재확인해 기록을 바로잡음).

       python test_scan_round445_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

print("=" * 72)
print("  스캔 445라운드 회귀 — JSON_AS_ASCII 죽은설정 → app.json.ensure_ascii")
print("=" * 72)

print("\n[1] 소스 확인")
#  ⚠ 설명주석이 옛 키 이름을 문서화 목적으로 그대로 언급하므로(왜 바뀌었는지
#    남기려고) 파일 전체에서 "JSON_AS_ASCII" 문자열 자체를 금지하면 그 주석과
#    충돌한다 — 실제로 살아있는 설정 자리(`app.config.update(...)` 안의
#    `JSON_AS_ASCII=False,`)만 없어졌는지를 정확히 검사한다.
chk("JSON_AS_ASCII=False," not in APP_SRC,
    "★★★★★ 죽은 설정 키가 app.config.update() 안에서 실제로 제거됐다"
    "(주석에서 옛 이름을 언급하는 것과는 별개)")
chk("app.json.ensure_ascii = False" in APP_SRC,
    "★★★★★ Flask 3.x 방식(app.json.ensure_ascii)으로 교체됐다")

print("\n[2] 실행 — 실제 app.json.ensure_ascii 값과 JSON 응답 바이트를 직접 확인")
_tmpdir = tempfile.mkdtemp(prefix="round445_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A.app.json.ensure_ascii is False,
        "★★★★★ app.json.ensure_ascii가 실제로 False다(고치기 전엔 True로 "
        "남아있었다)", A.app.json.ensure_ascii)

    c = A.app.test_client()
    r = c.get("/api/version")
    raw = r.get_data(as_text=True)
    chk("복구온" in raw,
        "★★★★★ /api/version 응답에 한글이 유니코드이스케이프 없이 리터럴로 "
        "그대로 담긴다", raw)
    chk("\\u" not in raw, "  응답 전체에 \\u 이스케이프 시퀀스가 하나도 없다", raw)

    conn = DB.get_db()
    admin_pw = DB.hash_pw("Testpw123!")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r445admin',?,'테스트관리자','최고관리자')", (admin_pw,))
    conn.commit()
    admin = A.app.test_client()
    tok = "r445-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r445admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "테스트관리자"; sess["_csrf"] = tok
    r2 = admin.get("/api/me", headers={"X-CSRF-Token": tok})
    raw2 = r2.get_data(as_text=True)
    chk(r2.status_code == 200 and "테스트관리자" in raw2 and "\\u" not in raw2,
        "★★★★ 실제 로그인 화면 응답(/api/me)도 한글이 리터럴로 온다"
        "(단발성 API 하나만이 아니라 공용 jsonify 경로 전체가 영향받음)",
        (r2.status_code, raw2))
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 되돌리기 — 옛 코드(죽은 설정)였다면 실제로 재현되는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드615] 이 결함은 함수 본문이 아니라 앱 생성 시 한 번 실행되는
#    모듈최상단 설정줄(app.json.ensure_ascii = False)이다. "옛 코드가 이
#    줄 대신 죽은 JSON_AS_ASCII만 썼다"의 결과는 app.json.ensure_ascii가
#    기본값 True로 남는 것과 완전히 동일하다 — exec 재구성 없이 그 값
#    자체를 직접 되돌렸다 복원한다(예전엔 이 되돌림을 증명하려고 실제로
#    app.py 를 디스크에 다시 써서 서브프로세스를 새로 띄웠었다).
try:
    _orig_ensure_ascii = A.app.json.ensure_ascii
    A.app.json.ensure_ascii = True   # 죽은 JSON_AS_ASCII=False 였다면 실제로 이 값이 된다
    try:
        raw_old = A.app.test_client().get("/api/version").get_data(as_text=True)
    finally:
        A.app.json.ensure_ascii = _orig_ensure_ascii

    chk("\\u" in raw_old,
        "★★★★★ 옛 설정값(ensure_ascii=True)에서는 응답에 실제로 유니코드이스케이프가 "
        "섞여 나간다(인과관계 직접증명)", raw_old)
    chk("복구온" not in raw_old,
        "  옛 값에서는 한글이 리터럴로 안 보인다(이스케이프됐으므로)", raw_old)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 방어되는가(바꿔치기가 안 샜다)")
    chk(A.app.json.ensure_ascii is False,
        "  원복 후 app.json.ensure_ascii가 다시 False로 돌아왔다")
    raw_restored = A.app.test_client().get("/api/version").get_data(as_text=True)
    chk("\\u" not in raw_restored and "복구온" in raw_restored,
        "★★★★ 원복 후에는 다시 한글 리터럴 응답으로 정상 방어된다(바꿔치기가 안 샜다)",
        raw_restored)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(app.json.ensure_ascii 속성 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
