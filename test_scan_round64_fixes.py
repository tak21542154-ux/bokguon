# -*- coding: utf-8 -*-
"""스캔 64라운드 회귀 — 업체 실적 일괄 재계산이 평점 하자차감을 지운다(HIGH) +
   보증 0개월(무보증)이 4곳에서 24개월로 둔갑한다(MEDIUM).

  조사 에이전트가 정적 추적(캐논 함수와 실적 재계산 SQL 대조, warranty_months
  전 사용처 전수)으로 짚고, 이번 라운드에서 실측(실제 DB+라우트)으로 재확인한
  결함:

  ① partner_rating()/refresh_partner_rating() 은 "평점은 해피콜 평균에서 귀책
     하자만큼 뺀다"는 유일한 계산식이다 — 그 위 주석이 이미 "예전엔 두 곳이
     partners.rating 을 서로 덮어썼다"(해피콜 AVG 통째 덮어쓰기 vs 하자 뺄셈,
     비가환이라 순서에 따라 값이 갈렸다)는 옛 사고를 설명한다. 그런데 실적
     일괄 재계산 도구(api_recount_partner_stats)가 정확히 그 옛 버그의 절반
     (AVG(해피콜)만 다시 계산해 통째로 덮어쓰기)을 재현하고 있었다 — 캐논
     함수를 안 쓰고 SQL 을 다시 손으로 적어서다. 이 도구를 한 번 돌리면
     하자 차감이 있던 모든 업체의 평점이 조용히 부풀려진다(그 값이 낙찰
     점수의 15%를 차지한다).
  ② warranty_months=0(무보증, 유효한 값 — 서버가 0~120 을 명시로 검증한다)을
     `or 24`/`||24` 로 읽는 4곳(피해자 진행조회 페이지·보험사 배차확인서·
     협력사 포털·관리자 사건수정 폼)이 전부 24개월로 잘못 보여준다.
     _warranty_left() 의 주석이 이미 이 정확한 함정("or 24 로 쓰면 0을 NULL과
     구별 못 해 무보증 사건도 24개월로 둔갑한다")을 경고하고 있었다.

      python test_scan_round64_fixes.py
"""
import hashlib
import io
import os
import re
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
DR_SRC = read(os.path.join("templates", "dispatch_report.html"))
PP_SRC = read(os.path.join("templates", "partner_portal.html"))
JS_SRC = read(os.path.join("static", "admin.js"))

print("═" * 72)
print("  스캔 64라운드 회귀 — 실적재계산이 평점 하자차감 삭제 + 무보증(0개월) 4곳 오표시")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
recount_body = _body(APP_SRC, "api_recount_partner_stats")
chk('rating = (SELECT ROUND(AVG(h.score)' not in recount_body,
    "★★★ api_recount_partner_stats — 평점을 더는 SQL로 다시 계산하지 않는다")
chk("refresh_partner_rating(conn, _pid)" in recount_body,
    "★★★ api_recount_partner_stats — 캐논 함수(refresh_partner_rating)를 그대로 쓴다")

track_body = _body(APP_SRC, "track_page")
chk('24 if c["warranty_months"] is None' in track_body,
    "★★ track_page — 무보증(0)을 24로 안 둔갑시킨다")

chk("c.warranty_months if c.warranty_months is not none else 24" in DR_SRC,
    "★ dispatch_report.html — 무보증(0)을 24로 안 둔갑시킨다")
chk("c.warranty_months??24" in PP_SRC,
    "★ partner_portal.html — 무보증(0)을 24로 안 둔갑시킨다")
chk("c.warranty_months??24" in JS_SRC,
    "★ admin.js(사건수정 폼) — 무보증(0)을 24로 안 둔갑시킨다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 직접 호출·실제 DB로 ① 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round64_")
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
    _tok = "regress-round64-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사64','활성')").lastrowid
    p_pen = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('하자보유업체64','시공사','활성')"
    ).lastrowid
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin64','x','검증','최고관리자')")

    #  해피콜 2건(점수 5,5 → 평균 5.0) — case_id 는 UNIQUE 라 서로 다른 사건에 심는다
    for k in range(2):
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,category,"
            "                  region) VALUES(?,'완료',?,?,?,?,?,'서울')",
            (f"64H-000{k}", "검증보험사64", iid, p_pen, "하자보유업체64",
             "누수·배관·설비")).lastrowid
        conn.execute(
            "INSERT INTO happy_calls(case_id,partner_id,score,created_at) "
            "VALUES(?,?,5,datetime('now','+9 hours'))", (cid, p_pen))
    #  귀책 하자 1건(중대·시행사 부담 → 패널티 0.2) — 캐논 계산: 5.0 - 0.2 = 4.8
    cid_d = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,category,region) "
        "VALUES(?,'완료',?,?,?,?,?,'서울')",
        ("64D-0000", "검증보험사64", iid, p_pen, "하자보유업체64", "누수·배관·설비")).lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,status,severity,"
        "                    cost_bearer,created_at) "
        "VALUES('D26-6400',?,?,?,'재발','완료','중대','시행사',datetime('now','+9 hours'))",
        (cid_d, "64D-0000", p_pen))

    #  해피콜 없는 대조군 업체 — 재계산 뒤에도 NULL(평점 없음)이어야 한다
    p_none = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('무해피콜업체64','시공사','활성')"
    ).lastrowid
    conn.commit()

    val, info = A.partner_rating(conn, p_pen)
    chk(val == 4.8, "STEP 캐논 계산식 자체는 4.8을 낸다(전제 확인)", (val, info))
    A.refresh_partner_rating(conn, p_pen)
    conn.commit()
    before = conn.execute("SELECT rating FROM partners WHERE id=?", (p_pen,)).fetchone()[0]
    chk(before == 4.8, "STEP 캐시된 평점이 정확히 4.8로 맞춰져 있다(전제 확인)", before)

    with client.session_transaction() as sess:
        sess["admin"] = "admin64"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok
    rr = client.post("/api/admin/recount-partner-stats", headers=_hdr)
    chk(rr.status_code == 200, "STEP 실적 일괄 재계산 실행", (rr.status_code, rr.get_json()))

    conn = DB.get_db()
    after = conn.execute("SELECT rating FROM partners WHERE id=?", (p_pen,)).fetchone()[0]
    none_rating = conn.execute("SELECT rating FROM partners WHERE id=?", (p_none,)).fetchone()[0]
    conn.close()
    chk(after == 4.8,
        "★★★ ① 재계산 뒤에도 하자 차감이 그대로 남는다(4.8) — 고치기 전엔 5.0으로"
        " 조용히 부풀려졌다(15%가 낙찰 점수에 들어간다)", after)
    chk(none_rating is None,
        "★ 대조군 — 해피콜이 없는 업체는 재계산 뒤에도 NULL(평점 없음)이다", none_rating)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 실제 서버(test_client)로 ② 재현(피해자 진행조회)")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    token = "round64warranty0token12345"
    #  ⚠ [라운드295] track_page() 가 이제 track_token_hash 로 찾으므로,
    #    issue_track_link() 를 안 거치고 직접 INSERT 할 땐 그 해시도 채운다.
    conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region,"
        "                  warranty_months,completed_at,track_token,track_token_hash,track_issued_at) "
        "VALUES(?,'완료',?,?,?,'서울',0,datetime('now','+9 hours'),?,?,datetime('now','+9 hours'))",
        ("64W-0000", "검증보험사64", iid, "누수·배관·설비", token,
         hashlib.sha256(token.encode()).hexdigest()))
    conn.commit(); conn.close()

    rt = client.get(f"/track/{token}")
    chk(rt.status_code == 200, "STEP 피해자 진행조회 페이지 정상 로드", rt.status_code)
    html = rt.get_data(as_text=True)
    chk("보증 0개월" in html,
        "★★ ② 무보증(0) 사건은 '보증 0개월'로 정확히 보인다"
        "(고치기 전엔 '보증 24개월' — 없는 보증을 있다고 보여줬다)",
        re.search(r"보증\s*\d+개월", html).group(0) if re.search(r"보증\s*\d+개월", html) else html[:200])
    chk("보증 24개월" not in html,
        "★★ ② 잘못된 '보증 24개월' 문구는 더 이상 없다", None)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드64 실측 준비/실행", f"{type(e).__name__} {e}")
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
