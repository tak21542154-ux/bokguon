# -*- coding: utf-8 -*-
"""스캔 260라운드 회귀 — 피해자 진행조회 공개 페이지(/track/<token>) 데모오염
   결함 1건 (track.html 감사 Agent 조사로 발견, 독립 재검증 후 수정).

  track_page()(로그인이 전혀 없는 이 서비스의 유일한 진짜 공개 화면)의
  SELECT 가 is_demo 를 안 걸렀다 — 같은 파일의 다른 150여 곳(가장 가까운
  형제는 이 기능의 짝인 _insurer_track_stat)은 전부 COALESCE(is_demo,0)=0
  을 건다. 데모 사건에 토큰이 심겨 있으면 사건번호·지역·상태·담당자·
  업체명이 로그인 없이 인터넷에 그대로 노출된다.

      python test_scan_round260_fixes.py
"""
import hashlib
import io
import os
import secrets
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 260라운드 회귀 — 피해자 진행조회 공개페이지 데모오염 차단")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index('def track_page(token):')
i1 = APP_SRC.index("\n\n\ndef ", i0)
track_body = APP_SRC[i0:i1]
#  ⚠ [라운드295] 조회 방식이 track_token 원문에서 track_token_hash 로
#    바뀌었다(개인정보 파기 뒤에도 "예전에 발급된 적 있음"을 알 수 있게 —
#    자세한 내용은 295라운드 회귀 참고). is_demo 를 거른다는 이 라운드의
#    핵심 주장은 그대로이므로 새 조회 형태로만 맞춘다.
chk("WHERE track_token_hash=? AND COALESCE(is_demo,0)=0" in track_body,
    "★★★★★ track_page() 의 조회가 데모 사건을 뺀다")

# ============================================================
print("\n[2] 실행(Flask) — 데모 사건 토큰은 404, 실제 사건 토큰은 정상 조회")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round260_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    mark = "R260-" + secrets.token_hex(3)
    tok_demo = secrets.token_urlsafe(16)
    tok_real = secrets.token_urlsafe(16)

    #  ⚠ [라운드295] track_page() 가 이제 track_token_hash 로 찾으므로,
    #    issue_track_link() 를 안 거치고 직접 INSERT 할 땐 그 해시도 같이
    #    채워야 한다(안 그러면 이 테스트의 두 사건 다 애초에 안 잡힌다).
    conn.execute(
        "INSERT INTO cases(case_no,category,region,address,status,manager,"
        "is_demo,track_token,track_token_hash,track_issued_at,created_at) "
        "VALUES(?,?,?,?,'시공중','김담당',1,?,?,?,?)",
        (f"{mark}-demo", "가드레일·방호울타리", "서울 강남구", "검증용",
         tok_demo, hashlib.sha256(tok_demo.encode()).hexdigest(), DB.now(), DB.now()))
    conn.execute(
        "INSERT INTO cases(case_no,category,region,address,status,manager,"
        "is_demo,track_token,track_token_hash,track_issued_at,created_at) "
        "VALUES(?,?,?,?,'시공중','이담당',0,?,?,?,?)",
        (f"{mark}-real", "가드레일·방호울타리", "서울 강남구", "검증용",
         tok_real, hashlib.sha256(tok_real.encode()).hexdigest(), DB.now(), DB.now()))
    conn.commit()
    conn.close()

    c = A.app.test_client()
    rd = c.get(f"/track/{tok_demo}")
    chk(rd.status_code == 404,
        "★★★★★ 데모 사건의 조회 링크는 404 — 사건번호·담당자 등이 노출되지 않는다",
        rd.status_code)

    rr = c.get(f"/track/{tok_real}")
    chk(rr.status_code == 200,
        "STEP 대조군 — 실제 사건의 조회 링크는 정상 200 이다(과잉차단 아님)",
        rr.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드260 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
