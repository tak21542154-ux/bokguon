# -*- coding: utf-8 -*-
"""스캔 56라운드 회귀 — "쓰는 곳과 읽는 곳의 상태값/필터 불일치" 4곳.

  라운드54 조사에서 위임한 별도 조사가 실측(읽기전용 운영 DB 대조 포함)으로
  증명한 결함 4건. 전부 "형제 자리 중 하나만 다른 규칙을 쓴다" 패턴이다.

  ① 현장 지도 상태 필터 '수배중' — cases.status 가 아니라 cases.dispatch_status
     값인데 지도 API 가 status 컬럼으로 걸러 항상 빈 지도가 나왔다.
  ② 대시보드 배지("도입문의_대기" 등)는 두 상태를 합쳐 세는데, 배지를 눌러
     이동하는 목록은 한 상태만 걸러 배지 숫자와 목록 건수가 어긋났다.
  ③ "오늘 할 일" 큐의 도입문의 항목만 형제 3곳(배지·며칠째·콘솔요약)과 다른
     좁은 상태 집합을 썼다.
  ④ 하자 사진(kind='하자'/'하자보수')이 시공사진·영수증 분류 어디에도 안 걸리는데
     '미분류' 버킷에도 안 잡혀, "총 N장"인데 화면엔 사진이 하나도 안 보였다
     (사건 상세 조회·어드민 사진 검수 큐 둘 다 같은 결함).

      python test_scan_round56_fixes.py
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
ADMINJS_SRC = read(os.path.join("static", "admin.js"))

print("═" * 72)
print("  스캔 56라운드 회귀 — 상태값/필터 불일치 4곳(지도·배지·오늘할일·사진분류)")
print("═" * 72)


def _body(fn_name):
    start = APP_SRC.index(f"\ndef {fn_name}(")
    end = APP_SRC.find("\ndef ", start + 1)
    return APP_SRC[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
map_body = _body("api_map_cases")
chk('if st == "수배중":' in map_body and "dispatch_status=?" in map_body,
    "★★★ ① api_map_cases — '수배중'을 dispatch_status 컬럼으로 가른다")
chk("_mst = c.dispatch_status === '수배중' ? '수배중' : c.status" in ADMINJS_SRC,
    "★ admin.js — 지도 마커 색상도 같은 원칙으로 맞춘다")

sf_body = _body("search_filters")
chk('sts = [x.strip() for x in st.split(",") if x.strip()]' in sf_body
    and f"{{status_col}} IN (%s)" in sf_body,
    "★★★ ② search_filters — 콤마로 여러 상태를 IN 절로 받는다(기존 단일값 호출 무변경)")
chk("appFilter='신규,서류검토'" in ADMINJS_SRC and "leadFilter='신규,검토중'" in ADMINJS_SRC,
    "★★ ② admin.js 드릴다운이 배지와 같은 상태 집합을 연다")

chk("FROM insurer_leads WHERE status IN ('신규','검토중') "
    in APP_SRC[APP_SRC.index("도입 문의가 답장을 기다립니다"):
               APP_SRC.index("도입 문의가 답장을 기다립니다") + 300],
    "★★★ ③ TODAY_QUEUE 도입문의 항목이 형제 3곳과 같은 상태 집합을 쓴다")

case_photos_body = _body("api_case_photos")
chk('p["kind"] not in PHOTO.CONSTRUCTION_KINDS' in case_photos_body
    and 'p["kind"] not in PHOTO.DOCUMENT_KINDS' in case_photos_body,
    "★★★ ④ api_case_photos — 미분류를 허용목록의 여집합으로 판정한다")
queue_body = _body("api_photos_queue")
chk("_constr_sql" in queue_body and "_doc_sql" in queue_body,
    "★★★ ④ api_photos_queue — 검수 큐 집계도 같은 원칙으로 맞춘다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 4곳 전부 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round56_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

_seq = [0]


def _no(prefix):
    _seq[0] += 1
    return f"{prefix}{_seq[0]:04d}"


try:
    import db as DB
    DB.init_db()
    import app as A

    client = A.app.test_client()
    _tok = "regress-round56-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin56','x','검증','최고관리자')")
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        sess["admin"] = "admin56"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    # ── ① 지도 필터 ──
    conn = DB.get_db()
    cid_seek = conn.execute(
        "INSERT INTO cases(case_no,status,dispatch_status,category,region,lat,lng) "
        "VALUES(?,'접수','수배중','금속','서울',37.5,127.0)", (_no("56M-"),)).lastrowid
    cid_other = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,lat,lng) "
        "VALUES(?,'입찰중','금속','서울',37.5,127.0)", (_no("56M-"),)).lastrowid
    conn.commit(); conn.close()

    r1 = client.get("/api/map/cases?status=수배중")
    d1 = r1.get_json()
    ids1 = {c["id"] for c in d1.get("cases", [])}
    chk(cid_seek in ids1,
        "★★★ ① '수배중' 필터가 실제로 수배중 사건을 찾는다(고치기 전엔 항상 0건)", ids1)
    chk(cid_other not in ids1, "① 다른 상태 사건은 안 섞여 나온다(과잉 매치 아님)", ids1)

    r1b = client.get("/api/map/cases?status=입찰중")
    ids1b = {c["id"] for c in r1b.get_json().get("cases", [])}
    chk(cid_other in ids1b and cid_seek not in ids1b,
        "★ 대조군 — 일반 상태 필터(입찰중)는 그대로 status 컬럼으로 동작한다", ids1b)

    # ── ② 배지-드릴다운 상태 집합 ──
    conn = DB.get_db()
    conn.execute("INSERT INTO insurer_leads(company,name,phone,status) "
                "VALUES('검증기관56-A','담당자','010','신규')")
    conn.execute("INSERT INTO insurer_leads(company,name,phone,status) "
                "VALUES('검증기관56-B','담당자','010','검토중')")
    conn.commit(); conn.close()

    r2 = client.get("/api/leads?status=" + "신규,검토중")
    d2 = r2.get_json()
    chk(len(d2) == 2, "★★★ ② status=신규,검토중 이 두 상태를 모두 반환한다(고치기 전엔 신규만)",
        [x.get("status") for x in d2])

    r2b = client.get("/api/leads?status=신규")
    chk(len(r2b.get_json()) == 1,
        "★ 대조군 — 콤마 없는 단일값은 그대로 하나만 반환한다(과잉차단 아님)",
        [x.get("status") for x in r2b.get_json()])

    # ── ③ 오늘 할 일 큐 ──
    r3 = client.get("/api/ops-today")
    d3 = r3.get_json()
    queue_group = next((g for g in d3.get("groups", []) if g.get("key") == "queue"), {})
    lead_item = next((i for i in queue_group.get("items", [])
                      if i.get("label") == "도입 문의가 답장을 기다립니다"), None)
    chk(lead_item is not None and lead_item.get("n") == 2,
        "★★★ ③ 오늘 할 일 큐가 배지와 같은 2건을 센다(고치기 전엔 신규 1건만)",
        lead_item)

    # ── ④ 하자 사진 분류 ──
    conn = DB.get_db()
    cid_defect = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,partner_name) "
        "VALUES(?,'시공중','금속','서울',NULL,'')", (_no("56D-"),)).lastrowid
    #  ⚠ '대기'로 심는다 — api_photos_queue 는 대기·반려가 0건인 사건을 화면에서
    #    뺀다("할 일 없는 사건은 안 보여야 정상"). '승인'이면 큐 자체에 안 잡혀
    #    이 결함과 무관한 이유로 아래 검사가 실패한다.
    conn.execute(
        "INSERT INTO photos(case_id,rel_path,uploader_role,uploader,kind,review_status,sha256) "
        "VALUES(?,?,?,?,?,?,?)",
        (cid_defect, f"{cid_defect}/defect.jpg", "관리자", "검증56", "하자", "대기", "sha56d"))
    conn.commit(); conn.close()

    with client.session_transaction() as sess:
        sess["admin"] = "admin56"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok
    r4 = client.get(f"/api/cases/{cid_defect}/photos")
    d4 = r4.get_json()
    chk(d4.get("total") == 1, "④ 사건 사진 조회 — 총 1장으로 집계된다", d4.get("total"))
    chk(len(d4.get("unclassified", [])) == 1,
        "★★★ ④ 하자 사진이 미분류 버킷에 실제로 잡힌다(고치기 전엔 어디에도 안 잡혔다)",
        d4.get("unclassified"))
    _sum = (len(d4.get("construction", [])) + len(d4.get("receipts", []))
            + len(d4.get("unclassified", [])))
    chk(_sum == d4.get("total"), "★★ 세 그룹의 합이 total 과 정확히 일치한다", (_sum, d4.get("total")))

    r4b = client.get("/api/photos")
    d4b = r4b.get_json()
    row_defect = next((r for r in d4b.get("items", []) if r.get("case_id") == cid_defect), None)
    chk(row_defect is not None and row_defect.get("unclassified") == 1,
        "★★★ ④ 어드민 사진 검수 큐도 하자 사진을 미분류 1건으로 센다(고치기 전엔 0)",
        row_defect)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드56 실측 준비/실행", f"{type(e).__name__} {e}")
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
