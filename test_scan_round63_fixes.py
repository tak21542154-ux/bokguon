# -*- coding: utf-8 -*-
"""스캔 63라운드 회귀 — 입점 신청 '직접 접수'(전화·팩스) 경로가 주소를 안 받았다
   (MEDIUM, 같은 결함을 승인 처리 쪽은 이미 한 번 고친 적이 있다).

  조사 에이전트가 정적 추적(접수→승인→거리기반 출동 소비까지 전 구간)으로 짚고,
  이번 라운드에서 실측(실제 test_client, 접수→승인 전 구간)으로 재확인한 결함:

  공개 폼(api_create_application)과 직접 등록(api_partner_create)은 둘 다 주소를
  받는데, 전화·팩스로 받은 신청을 담당자가 대신 접수하는 '직접 접수'
  (api_application_create, /api/applications/manual) 만 주소 입력란 자체가 없었다.
  승인 처리(api_application_update)의 partners INSERT 자체는 "주소가 빠져 있었다
  — 승인으로 만든 업체는 주소가 NULL 로 시작했고, 주소가 없으면 좌표도 없어
  거리순 출동 호출에서 계속 뒤로 밀렸다" 는 주석과 함께 이미 한 번 고쳐져
  있었다 — 그런데 그 수정은 애초에 주소를 못 받는 이 접수 경로 앞에서는 무력했다.

      python test_scan_round63_fixes.py
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
JS_SRC = read(os.path.join("static", "admin.js"))

print("═" * 72)
print("  스캔 63라운드 회귀 — 입점 신청 직접접수 경로에 주소 입력이 빠져 있었다")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
create_body = _body(APP_SRC, "api_application_create")
chk("INSERT INTO partner_applications(company,biz_no,ceo,major,category,region,address,phone,"
    in create_body,
    "★★★ api_application_create — INSERT 컬럼 목록에 address 가 들어갔다")
#  ⚠⚠ [라운드607] 형제결함군(raw d.get(...)이 JSON 비문자열이면 500)을 고치며
#    (d.get("address") or "").strip()[:200] 이 _s(d.get("address"), 200)으로
#    바뀌었다 — 200자 상한을 두고 정제해 저장한다는 이 검사의 본래 취지는
#    그대로이므로(strip→slice 순서도 동일) 리터럴만 갱신한다(검사 취지 약화 없음).
chk('_s(d.get("address"), 200)' in create_body,
    "★★ api_application_create — 공개 폼과 같은 방식으로 주소를 정제해 저장한다")

chk('id="q_addr"' in JS_SRC, "★ admin.js — 직접접수 모달에 주소 입력란이 있다")
chk("address:$('#q_addr').value.trim()" in JS_SRC,
    "★★ admin.js — saveIntake() 가 주소를 실제로 요청 본문에 담는다")
chk("a.address" in JS_SRC, "★ admin.js — 신청 상세 모달이 주소를 보여준다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 접수→승인 전 구간 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round63_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import app as A

    client = A.app.test_client()
    _tok = "regress-round63-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin63','x','검증','중간관리자')")
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin63"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    with client.session_transaction() as sess:
        _admin_sess(sess)

    #  ── 주소를 실제로 넣어 직접 접수 ──
    r1 = client.post("/api/applications/manual",
                     json={"company": "테스트건설63", "major": "누수·배관·설비",
                           "phone": "010-6300-0001", "region": "서울·경기",
                           "address": "서울 강남구 테헤란로 63"},
                     headers=_hdr)
    chk(r1.status_code == 200, "STEP 직접 접수(주소 포함) — 정상 접수된다", (r1.status_code, r1.get_json()))
    aid1 = (r1.get_json() or {}).get("id")

    conn = DB.get_db()
    app_row1 = dict(conn.execute("SELECT address FROM partner_applications WHERE id=?",
                                 (aid1,)).fetchone())
    conn.close()
    chk(app_row1["address"] == "서울 강남구 테헤란로 63",
        "★★★ 신청 행에 주소가 실제로 저장됐다(고치기 전엔 컬럼 자체가 안 채워졌다)",
        app_row1)

    r1a = client.patch(f"/api/applications/{aid1}", json={"status": "승인"}, headers=_hdr)
    chk(r1a.status_code == 200, "STEP 승인 처리", (r1a.status_code, r1a.get_json()))
    conn = DB.get_db()
    pid1 = conn.execute("SELECT partner_id FROM partner_applications WHERE id=?",
                        (aid1,)).fetchone()[0]
    p1 = dict(conn.execute("SELECT address FROM partners WHERE id=?", (pid1,)).fetchone())
    conn.close()
    chk(p1["address"] == "서울 강남구 테헤란로 63",
        "★★★ 승인으로 만들어진 업체도 주소를 그대로 물려받는다"
        "(고치기 전엔 접수 단계부터 주소가 없어 승인 쪽 수정이 무력했다)", p1)

    #  ── 대조군 — 주소를 안 넣어도(선택 필드) 접수 자체는 막히지 않는다 ──
    r2 = client.post("/api/applications/manual",
                     json={"company": "테스트건설63-무주소", "major": "누수·배관·설비",
                           "phone": "010-6300-0002"},
                     headers=_hdr)
    chk(r2.status_code == 200,
        "★ 대조군 — 주소를 안 넣어도 여전히 접수된다(필수로 만들지 않았다)",
        (r2.status_code, r2.get_json()))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드63 실측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
