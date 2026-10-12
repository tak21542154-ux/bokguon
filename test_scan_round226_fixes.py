# -*- coding: utf-8 -*-
"""스캔 226라운드 회귀 — 보험사 서버간 API(/api/v1/*, API 키 인증) 두 결함.

  [1] _security_headers()(접속기록, 개인정보 안전성 확보조치 기준 제8조 의무
      기록)가 세션 기반 인증만 읽어, API 키로 인증하는 /api/v1/* 요청은
      성공·실패를 가리지 않고 전부 user_id·role 이 NULL 로 남았다 — 이미 같은
      함수 안에 "보험사 계정이 빠져 있었다"는 주석으로 한 번 고친 전례
      (세션 기반 보험사 로그인)가 있는데, 나중에 추가된 API 키 채널에는
      같은 수정이 적용되지 않았다.
  [2] templates/insurer_api_guide.html 의 "사건 접수" 예시가 est_price 를
      빠뜨려, 문서에 적힌 그대로 요청을 보내면 100% 확정적으로 400 이 난다
      (parse_money 가 required=True 기본값이라 빈 값을 거부).

      python test_scan_round226_fixes.py
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


GUIDE_SRC = read("templates/insurer_api_guide.html")

print("═" * 72)
print("  스캔 226라운드 회귀 — /api/v1/* 접속기록 누락 · 연동안내서 예시 400")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — insurer_api_guide.html의 사건접수 예시")
# ──────────────────────────────────────────────────────────────
_i_sec4 = GUIDE_SRC.index("4. 사건 접수")
_i_sec5 = GUIDE_SRC.index("5. 진행 조회")
section4 = GUIDE_SRC[_i_sec4:_i_sec5]
#  ⚠ 이 절엔 "{{ base }}" 같은 Jinja 변수도 있어, 가장 먼저 매치되는 {...} 가
#    실제 JSON 예시가 아닐 수 있다(예: "{ base }" 처럼 중간을 잘라 매치).
#    후보를 전부 뽑아 실제로 JSON 으로 파싱되는 것만 쓴다.
example = None
for cand in re.finditer(r"\{[^{}]*\}", section4):
    try:
        parsed = json.loads(cand.group(0))
    except ValueError:
        continue
    if isinstance(parsed, dict) and "category" in parsed:
        example = parsed
        break
chk(example is not None, "STEP 사건접수 절에서 JSON 예시 블록을 찾았다(파싱 전제 확인)")
example = example or {}
chk("est_price" in example,
    "★★★★ 사건접수 예시 JSON에 est_price 가 포함된다"
    "(예전엔 빠져 있어 문서 그대로 보내면 서버가 거부했다)", example)
chk("est_price</th>" in section4 and "필수" in section4,
    "★★★ 필드 설명표에도 est_price(필수) 항목이 추가됐다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 문서의 예시를 실제로 그대로 보내본다(Flask test_client)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round226_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    RAW_KEY = "bok_live_r226testkey0000000000000000000000000"
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status,api_enabled,api_key_hash) VALUES(?,?,1,?)",
        ("R226보험사", "활성", A._hash_api_key(RAW_KEY))).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    hdr = {"X-API-Key": RAW_KEY}

    if example:
        r = client.post("/api/v1/cases", headers=hdr, json=example)
        chk(r.status_code == 201,
            "★★★★ 안내서 예시를 문자 그대로 보내면 실제로 접수가 성공한다"
            "(고치기 전엔 est_price 없음 → 400 '가견적을 입력해 주세요.')",
            (r.status_code, r.get_json()))

    # ── [1] 접속기록 — API 키 채널이 이제 '누구'로 남는가 ──
    r_ping = client.get("/api/v1/ping", headers=hdr)
    chk(r_ping.status_code == 200, "STEP ping 자체는 정상 응답한다", r_ping.status_code)

    conn = DB.get_db()
    row = conn.execute(
        "SELECT user_id, role FROM access_log WHERE path='/api/v1/ping' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    chk(row is not None and row["user_id"] == "R226보험사" and row["role"] == "보험사API",
        "★★★★ /api/v1/ping 요청의 접속기록에 이제 호출한 보험사 이름과 "
        "'보험사API' 역할이 남는다(예전엔 user_id·role 둘 다 NULL 이었다)",
        dict(row) if row else None)

    # ── 실패한 API 키 요청도 흔적이 남아야 한다(성공만 남기는 게 아님을 확인) ──
    r_bad = client.get("/api/v1/ping", headers={"X-API-Key": "존재하지않는키"})
    chk(r_bad.status_code == 401, "STEP 잘못된 키는 여전히 401 로 거절된다(회귀 아님)",
        r_bad.status_code)

    # ── 기존 세션 기반 보험사 로그인 경로는 이 수정으로 안 건드렸는가(회귀 확인) ──
    conn = DB.get_db()
    sess_iid = conn.execute(
        "INSERT INTO insurers(name,status,login_id,password_hash) "
        "VALUES('R226세션보험사','활성','r226insurer','x')").lastrowid
    conn.commit()
    conn.close()
    sess_client = A.app.test_client()
    with sess_client.session_transaction() as sess:
        sess["insurer_id"] = sess_iid
        sess["insurer_login"] = "r226insurer"
    r_sess = sess_client.get("/api/insurer/me")
    conn = DB.get_db()
    row2 = conn.execute(
        "SELECT user_id, role FROM access_log WHERE path='/api/insurer/me' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    chk(row2 is not None and row2["user_id"] == "r226insurer" and row2["role"] == "보험사",
        "STEP 기존 세션 기반 보험사 로그인 경로는 이번 수정 후에도 그대로 "
        "'보험사' 역할로 남는다(API 키 폴백을 끼워 넣으면서 건드리지 않았는지 확인)",
        (dict(row2) if row2 else None, r_sess.status_code))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드226 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
