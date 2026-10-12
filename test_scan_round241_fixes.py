# -*- coding: utf-8 -*-
"""스캔 241라운드 회귀 — 협력사 계좌번호 "삭제" 기능이 안내문에만 있고 실제
   화면엔 없던 결함(240라운드 admin.js 협력사관리 감사에서 발견한 세 번째
   항목을 이번 라운드에 완성).

  app.py의 api_partner_account_set 은 이미 clear_account:true 를 받으면
  계좌를 실제로 지울 수 있게 완성돼 있었다 — 빈 계좌번호를 보냈는데 그 값이
  없으면(=명시적 삭제 의사가 없으면) 409 CLEAR_NOT_ALLOWED 로 막고 "정말
  지우려면 '계좌 삭제'를 사용하세요"라고 안내한다. 그런데 admin.js 어디에도
  clear_account 를 보내는 통로가 없었다(레포 전체 grep 0건) — 안내가 가리키는
  기능 자체가 화면에 없었다. saveAccount()/loadAccount() 에 삭제 체크박스를
  추가해 그 통로를 연다.

      python test_scan_round241_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADMIN_JS = read("static/admin.js")

print("=" * 72)
print("  스캔 241라운드 회귀 — 협력사 계좌삭제 UI 부재")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — admin.js")
# ------------------------------------------------------------
try:
    i0 = ADMIN_JS.index("async function loadAccount(")
    i1 = ADMIN_JS.index("\nasync function ", i0 + 1)
    la_body = ADMIN_JS[i0:i1]
    chk('data-act-change="acctClearToggle"' in la_body,
        "★★★★ loadAccount() 가 삭제 체크박스를 그린다(a.bank_account 있을 때만)")
    chk("a.bank_account ? " in la_body,
        "STEP 계좌가 아예 없는 업체에는 삭제 체크박스를 안 보여준다(지울 게 없다)")

    i2 = ADMIN_JS.index("async function saveAccount(")
    i3 = ADMIN_JS.index("\nasync function ", i2 + 1)
    sa_body = ADMIN_JS[i2:i3]
    chk("body.bank_account = ''; body.clear_account = true;" in sa_body,
        "★★★★ saveAccount() 가 삭제 체크 시 clear_account:true 를 실제로 보낸다"
        "(고치기 전엔 이 코드베이스 어디에도 이 키를 보내는 곳이 없었다)")
    chk("if(!confirm(" in sa_body,
        "STEP 삭제는 확인창을 거친다(되돌릴 수 없는 조작 — 이 코드베이스의 "
        "다른 되돌릴 수 없는 조작들과 같은 원칙)")
    chk("loadAccount(id);" in sa_body,
        "STEP 저장 후 화면을 다시 불러와 삭제 결과를 반영한다"
        "(고치기 전엔 성공해도 입력칸에 옛 계좌번호가 그대로 남아 있었다)")

    chk("ACT.acctClearToggle = " in ADMIN_JS,
        "★★★ 체크박스 핸들러가 등록돼 있다(data-act 델리게이션 컨벤션)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드241 [1] 소스 확인", f"{type(e).__name__} {e}")

# ============================================================
print("\n[2] 실행 — Flask 실서버로 새 화면이 보낼 요청을 그대로 재현")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round241_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A
    import crypto_util as CRYPTO

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r241top','x','검증','최고관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,bank_name,bank_holder,bank_account_enc,bank_account_idx) "
        "VALUES('R241업체','시행사','활성','국민은행','홍길동',?,?)",
        (CRYPTO.encrypt("11022233344"), CRYPTO.blind_index("11022233344"))).lastrowid
    conn.commit(); conn.close()

    top = A.app.test_client()
    tok = "r241-csrf"
    with top.session_transaction() as sess:
        sess["admin"] = "r241top"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    def get_account_enc(pid):
        c = DB.get_db()
        r = c.execute("SELECT bank_account_enc FROM partners WHERE id=?", (pid,)).fetchone()
        c.close()
        return r["bank_account_enc"]

    #  ── (a) 대조군 — clear_account 없이 빈 계좌번호만 보내면 여전히 막힌다 ──
    ra = top.patch(f"/api/partners/{pid}/account",
                   json={"bank_name": "국민은행", "bank_holder": "홍길동", "bank_account": ""},
                   headers=hdr)
    chk(ra.status_code == 409 and ra.get_json().get("code") == "CLEAR_NOT_ALLOWED",
        "★★★ 대조군 — clear_account 없이 빈 값만 보내면 여전히 409 로 막힌다"
        "(회귀로 안전장치가 풀리지 않았다)", ra.get_json())
    chk(get_account_enc(pid), "STEP 막힌 시도는 실제로 계좌를 지우지 않았다")

    #  ── (b) 새 화면이 실제로 보내는 요청 — clear_account:true ──
    rb = top.patch(f"/api/partners/{pid}/account",
                   json={"bank_name": "국민은행", "bank_holder": "홍길동",
                         "bank_account": "", "clear_account": True},
                   headers=hdr)
    chk(rb.status_code == 200 and rb.get_json().get("ok"),
        "★★★★ 새 화면이 보내는 요청(clear_account:true)은 실제로 성공한다"
        "(고치기 전엔 이 요청을 만들 방법 자체가 화면에 없었다)", rb.get_json())
    chk(not get_account_enc(pid),
        "★★★★ 계좌 암호문이 실제로 비워졌다(진짜 삭제됨)", get_account_enc(pid))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드241 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
