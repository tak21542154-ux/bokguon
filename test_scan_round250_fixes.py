# -*- coding: utf-8 -*-
"""스캔 250라운드 회귀 — 협력사 온보딩·면허조사 화면 결함 3건
   (admin.js 온보딩·면허설정 화면군 Agent 병렬조사로 발견, 전부 독립 재검증 후 수정).

  [1] onbIssue("선택 업체 계정 만들기") 버튼에 등급 게이트가 없었다.
      /api/partners/bulk-credentials 는 require_role(최고관리자) 전용인데,
      화면은 등급 무관하게 그려 하위·중간관리자가 선택→확인창까지 진행한
      뒤에야 403을 만났다. 형제(협력사 상세의 개별 계정발급, admin.js 1457행)
      는 이미 myRank()<3 이면 안내문으로 바꾸는데 이 툴바 버튼만 빠뜨렸다.
      (onbInvite·licSet 은 백엔드가 require_role(하위관리자)=등급 무관 허용
      이라 게이트가 없어도 정상 — 잘못 잠그면 그게 새 결함이 된다.)

  [2] api_partner_invite() 가 이미 안내를 표시한 업체에도 매번 다시 실발송
      했다 — login_id 유무만 보고 invited_at 은 검사하지 않았다. 형제
      (api_partner_bulk_credentials, 이미 login_id 있으면 건너뛴다)와 같은
      "이미 처리된 대상은 건너뛴다" 관용구를 이 라우트만 놓쳤다. ONB.stage
      를 '전체'로 두고 "보이는 것 모두 선택"→"안내 표시"를 누르면 이미
      로그인·입찰까지 마친 업체에도 "계정이 준비되었습니다" 문자가 또
      나갈 수 있었다 — 정상 UI 조작만으로 재현되고, 재시도 방어도 겸한다.

  [3] api_partner_license() 감사로그가 새 값만 남기고 이전 값은 버렸다.
      license_status 는 하도급법 §25② 적법성 판정에 쓰이는 값이라, 등록확인
      →무등록으로 뒤집혀도 배정 당시 기준이 무엇이었는지 로그로 복원할 수
      없었다. 형제(AI 임계값, 라운드224)는 이미 UPDATE 전에 이전값을 읽어
      이전값→새값을 남긴다 — 같은 방식으로 통일(부수적으로 partner id 대신
      이름도 함께 남겨 가독성을 맞췄다).

      python test_scan_round250_fixes.py
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
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 250라운드 회귀 — 온보딩 등급게이트·중복안내·면허조사 감사로그")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("<button class=\"btn g sm\" data-act=\"onbAll\">")
i1 = ADMIN_JS.index("</div>", i0)
onb_toolbar = ADMIN_JS[i0:i1]
chk("myRank()>=3?'<button class=\"btn p sm\" data-act=\"onbIssue\">" in onb_toolbar,
    "★★★★ onbIssue 버튼이 myRank()>=3 로 게이트됐다(등급 미달이면 숨김)")
chk('<button class="btn a sm" data-act="onbInvite">선택 업체 안내 표시</button>' in onb_toolbar,
    "★★ onbInvite 버튼은 게이트하지 **않았다**(백엔드가 등급무관 허용이라 정상 — "
    "잘못 잠그면 그 자체가 새 결함)")

i2 = APP_SRC.index("def api_partner_invite(")
i3 = APP_SRC.index("\n\n\n", i2)
invite_body = APP_SRC[i2:i3]
chk("invited_at" in invite_body.split("SELECT id, name, login_id")[1][:40],
    "★★★★ invited_at 을 함께 조회한다")
chk('if p["invited_at"]:' in invite_body and '"이미 안내함"' in invite_body,
    "★★★★ 이미 안내한 업체는 건너뛴다(재시도해도 다시 안 나감)")

i4 = APP_SRC.index("def api_partner_license(")
i5 = APP_SRC.index("\n\n\n", i4)
lic_body = APP_SRC[i4:i5]
chk('before = one(conn.execute("SELECT name, license_status' in lic_body,
    "★★★★ UPDATE 전에 이전 상태를 먼저 읽는다")
chk('f"{_name}(#{pid}) {_old}→{st}"' in lic_body,
    "★★★★ 감사로그가 이전값→새값 형식으로 남는다(이전엔 새 값만 남았다)")

# ============================================================
print("\n[2] 실행(Flask) — 온보딩 안내 중복발송 방지 · 면허조사 감사로그")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round250_")
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
                 "VALUES('r250mid','x','검증','중간관리자')")
    pid_new = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id,phone,sms_opt_out) "
        "VALUES('R250-신규','시공사','활성','r250a','01011112222',0)").lastrowid
    pid_done = conn.execute(
        "INSERT INTO partners(name,partner_type,status,login_id,phone,sms_opt_out,invited_at) "
        "VALUES('R250-이미안내','시공사','활성','r250b','01033334444',0,'2020-01-01 00:00:00')").lastrowid
    pid_lic = conn.execute(
        "INSERT INTO partners(name,partner_type,status,license_status) "
        "VALUES('R250-면허업체','시공사','활성','등록확인')").lastrowid
    conn.commit(); conn.close()

    mid = A.app.test_client()
    tok = "r250-csrf"
    with mid.session_transaction() as sess:
        sess["admin"] = "r250mid"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = tok
    hdr = {"X-CSRF-Token": tok}

    #  ── (a) 신규+이미안내 혼합 선택 → 이미안내는 건너뛰고 신규만 표시된다 ──
    r1 = mid.post("/api/partners/invite", json={"ids": [pid_new, pid_done]}, headers=hdr)
    j1 = r1.get_json()
    chk(r1.status_code == 200 and j1.get("ok"), "STEP 요청 자체는 200으로 성공한다", j1)
    marked_ids = [m["id"] for m in (j1.get("marked") or [])]
    skipped_whys = {s["id"]: s["why"] for s in (j1.get("skipped") or [])}
    chk(pid_new in marked_ids, "★★★★ 신규 업체는 정상 표시(marked)된다", j1)
    chk(skipped_whys.get(pid_done) == "이미 안내함",
        "★★★★ 이미 안내한 업체는 건너뛴다(사유: 이미 안내함)", j1)

    conn = DB.get_db()
    done_row = conn.execute("SELECT invited_at FROM partners WHERE id=?", (pid_done,)).fetchone()
    conn.close()
    chk(done_row["invited_at"] == "2020-01-01 00:00:00",
        "★★★★★ 이미 안내한 업체의 invited_at 은 건드리지 않는다(재발송 흔적 없음)",
        done_row["invited_at"])

    #  ── (b) 방금 표시된 신규 업체를 다시 선택해도(재시도) 이번엔 건너뛴다 ──
    r2 = mid.post("/api/partners/invite", json={"ids": [pid_new]}, headers=hdr)
    j2 = r2.get_json()
    chk(not (j2.get("marked") or []) and (j2.get("skipped") or [{}])[0].get("why") == "이미 안내함",
        "★★★★ 방금 표시한 업체를 같은 요청으로 또 보내도 이번엔 건너뛴다(재시도 방어)", j2)

    #  ── (c) 면허조사 — 이전값→새값이 응답·로그 모두에 남는다 ──
    r3 = mid.post(f"/api/partners/{pid_lic}/license",
                  json={"license_status": "무등록"}, headers=hdr)
    chk(r3.status_code == 200, "STEP 면허상태 변경 요청은 200으로 성공한다", r3.get_json())
    conn = DB.get_db()
    row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='건설업 등록 조사' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    detail = row["detail"] if row else ""
    chk("등록확인→무등록" in detail, "★★★★ 감사로그에 이전값→새값이 남는다", detail)
    chk("R250-면허업체" in detail, "★★ 감사로그에 업체 이름도 남는다(번호만이 아님)", detail)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드250 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
