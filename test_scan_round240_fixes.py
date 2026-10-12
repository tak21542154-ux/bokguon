# -*- coding: utf-8 -*-
"""스캔 240라운드 회귀 — api_partner_update(PATCH /api/partners/<id>) 의 등급
   검사·강등확인 관문 둘 다 "본문에 status 키가 있는가"만으로 걸려 있던 결함
   (Agent 병렬조사로 admin.js 협력사 관리 화면을 감사하다 발견).

  화면(admin.js savePartner())은 관리자가 상태를 안 건드려도 <select id="p_status">
  의 현재 선택값을 매번 함께 보낸다 — "본문에 status 가 있다"와 "상태를 바꾼다"는
  다른데, 서버가 이 둘을 구분 안 했다.

  [1] 등급검사: `if "status" in d and _admin_rank() < ROLE_RANK["중간관리자"]`가
      맨 앞에서 걸려, 하위관리자는 상태를 안 건드리고 전화번호 하나만 고쳐도
      매번 "업체 상태 변경은 중간관리자 이상만…"으로 거부됐다(라우트 자신의
      주석 "연락처 수정까지 막을 이유는 없다"와 정반대로 동작). 실측: 저장이
      100% 거부됨.
  [2] 강등확인관문: `if "status" in d: _partner_demote_gate(...)`도 같은 이유로,
      이미 '퇴출' 등으로 내려가 있는 업체를 상태값 그대로 재전송하며 다른
      필드만 고쳐도 "진행 중 사건이 있다"는 강등확인 관문에 불필요하게 걸렸다.

  이미 함수 안에 DB 현재값과 대조해 계산하는 changed 가 있었다(사유 필수
  검사에 쓰임) — 두 관문 모두 이 changed 를 재사용하도록 수정.

  [부수 결함] static/admin.js 의 partnerForm() 이 "계정 발급"·"비밀번호 재발급"
  버튼을 등급 무관하게 그린다 — 그런데 그 버튼이 부르는 POST
  /api/partners/<id>/credentials 는 @require_role("최고관리자") 라 중간·
  하위관리자는 누르면 항상 403 이다. 이 코드베이스 자신이 이미 쓰는 패턴
  (myRank() 로 등급 미달 UI 를 미리 숨김, applyRoleMenus()·VIEWS.admins 등)을
  이 화면만 놓치고 있었다 — 서버는 이미 올바르게 막으므로 보안 결함은 아니고,
  못 쓸 버튼을 보여줘 헛클릭·문의로 이어지는 UX 결함이다.

      python test_scan_round240_fixes.py
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


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 240라운드 회귀 — 협력사 정보수정의 status-키-존재만으로 문턱 오판")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = APP_SRC.index('def api_partner_update(')
i1 = APP_SRC.index("\n@app.", i0 + 1)
body = APP_SRC[i0:i1]
chk('if changed and _admin_rank() < ROLE_RANK["중간관리자"]:' in body,
    "★★★★ 등급검사가 이제 changed(실제 변경 여부)를 본다(본문 키 존재만으론 안 건다)")
chk('if changed:\n            blocked = _partner_demote_gate(conn, pid,' in body,
    "★★★★ 강등확인 관문도 changed 를 본다")
chk('if "status" in d and _admin_rank() < ROLE_RANK["중간관리자"]:' not in body,
    "STEP 옛 판정(본문 키 존재만 검사)이 더는 없다")

# ============================================================
print("\n[2] 실행 — Flask 실서버로 실제 요청 4가지 시나리오 검증")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round240_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r240low','x','검증','하위관리자')")
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r240mid','x','검증','중간관리자')")
    conn.commit(); conn.close()

    def _admin_client(username, role):
        c = A.app.test_client()
        tok = f"r240-{username}-csrf"
        with c.session_transaction() as sess:
            sess["admin"] = username; sess["admin_role"] = role; sess["admin_name"] = "검증"
            sess["_csrf"] = tok
        return c, {"X-CSRF-Token": tok}

    low, hdr_low = _admin_client("r240low", "하위관리자")
    mid, hdr_mid = _admin_client("r240mid", "중간관리자")

    def mk_partner(status="활성"):
        c = DB.get_db()
        cur = c.execute(
            "INSERT INTO partners(name,partner_type,status,phone) "
            "VALUES('R240업체','시행사',?,'01000000000')", (status,))
        c.commit(); pid = cur.lastrowid; c.close()
        return pid

    def get_status(pid):
        c = DB.get_db()
        r = c.execute("SELECT status FROM partners WHERE id=?", (pid,)).fetchone()
        c.close()
        return r["status"]

    #  ── (a) 하위관리자 — 상태는 안 건드리고(화면이 현재값을 그대로 보냄) 전화번호만 수정 ──
    pid_a = mk_partner("활성")
    ra = low.patch(f"/api/partners/{pid_a}", json={"phone": "010-9999-8888", "status": "활성"},
                   headers=hdr_low)
    chk(ra.status_code == 200 and ra.get_json().get("ok"),
        "★★★★ 하위관리자가 상태 불변(화면이 늘 함께 보내는 현재값)인 채 "
        "다른 필드만 고치면 저장된다(고치기 전엔 매번 403 FORBIDDEN 이었다)",
        ra.get_json())

    #  ── (b) 하위관리자 — 실제 상태 변경 시도는 여전히 막힌다(기존 보호 유지) ──
    rb = low.patch(f"/api/partners/{pid_a}", json={"status": "경고"}, headers=hdr_low)
    chk(rb.status_code == 403 and rb.get_json().get("code") == "FORBIDDEN",
        "★★★ 하위관리자의 **실제** 상태 변경 시도는 그대로 403 으로 막힌다"
        "(회귀로 보호가 풀리지 않았다)", rb.get_json())
    chk(get_status(pid_a) == "활성", "STEP 막힌 시도는 실제로 반영되지 않았다", get_status(pid_a))

    #  ── (c) 중간관리자 — 실제 상태 변경 + 사유 → 정상 동작(영향 없음 확인) ──
    pid_c = mk_partner("활성")
    rc = mid.patch(f"/api/partners/{pid_c}",
                   json={"status": "경고", "status_reason": "검증용 사유입니다"}, headers=hdr_mid)
    chk(rc.status_code == 200 and rc.get_json().get("ok") and get_status(pid_c) == "경고",
        "★★★ 중간관리자의 정상적인 상태 변경(+사유)은 그대로 동작한다", rc.get_json())

    #  ── (d) 이미 '퇴출'인 업체 — 상태값 그대로 재전송하며 다른 필드만 수정 ──
    #      진행중 사건을 붙여 강등확인 관문이 실제로 걸릴 조건을 만든다.
    pid_d = mk_partner("퇴출")
    conn = DB.get_db()
    conn.execute("INSERT INTO cases(case_no, partner_id, status) VALUES('R240-D', ?, '시공중')",
                 (pid_d,))
    conn.commit(); conn.close()
    rd = low.patch(f"/api/partners/{pid_d}", json={"phone": "010-1111-2222", "status": "퇴출"},
                   headers=hdr_low)
    chk(rd.status_code == 200 and rd.get_json().get("ok"),
        "★★★★ 이미 퇴출 상태인 업체를 그 값 그대로 재전송하며 다른 필드만 "
        "고치면 저장된다(고치기 전엔 '진행 중 사건이 있다' 강등확인 관문에 "
        "불필요하게 걸렸다)", rd.get_json())

    #  ── (e) 대조군 — 실제 강등 시도는 강등확인 관문이 여전히 막는다 ──
    pid_e = mk_partner("활성")
    conn = DB.get_db()
    conn.execute("INSERT INTO cases(case_no, partner_id, status) VALUES('R240-E', ?, '시공중')",
                 (pid_e,))
    conn.commit(); conn.close()
    re_ = mid.patch(f"/api/partners/{pid_e}", json={"status": "퇴출"}, headers=hdr_mid)
    chk(re_.status_code == 409 and re_.get_json().get("code") == "PARTNER_HAS_WORK",
        "★★★ 대조군 — 진행 사건이 있는 업체의 **실제** 강등 시도는 여전히 "
        "강등확인 관문에 막힌다(회귀로 보호가 풀리지 않았다)", re_.get_json())
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드240 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 소스 확인 — admin.js partnerForm() 의 계정발급 버튼 등급 게이팅")
# ------------------------------------------------------------
try:
    ADMIN_JS = read("static/admin.js")
    i2 = ADMIN_JS.index("function partnerForm(")
    i3 = ADMIN_JS.index("\nfunction ", i2 + 1)
    pf_body = ADMIN_JS[i2:i3]
    i_cred = pf_body.index('id="credbox"')
    i_cred_end = pf_body.index("정산 지급 계좌", i_cred)   # 다음 구획 시작 — 넉넉히 안전한 경계
    credbox = pf_body[i_cred:i_cred_end]
    chk("myRank() < 3" in credbox,
        "★★★ credbox 안에 myRank() 등급 분기가 있다")
    lo_branch, hi_branch = credbox.split("myRank() < 3", 1)[1].split(": (p.login_id", 1)
    chk('data-act="issueCred"' not in lo_branch,
        "★★★★ myRank() < 3(중간·하위관리자) 분기에는 계정발급 버튼이 아예 없다"
        "(고치기 전엔 등급 무관하게 항상 그려져 눌러도 매번 403 이었다)")
    chk("최고관리자만" in lo_branch,
        "STEP 대신 왜 안 되는지 안내 문구가 있다(버튼만 지우고 이유를 안 남기지 않는다)")
    chk(hi_branch.count('data-act="issueCred"') == 2,
        "★★★ myRank() >= 3(최고관리자) 분기에는 기존처럼 두 경우(신규발급/재발급) "
        "모두 버튼이 그대로 있다(과잉숨김 아님)", hi_branch.count('data-act="issueCred"'))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드240 [3] 소스 확인", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
