# -*- coding: utf-8 -*-
"""스캔 61라운드 회귀 — 하자 이의제기가 판정 결과를 협력사에게 영영 안 알림
   (MEDIUM) + 절감 기준선 두 구현(SQL/파이썬)이 다른 답을 낼 수 있음(LOW-MEDIUM,
   현재는 dormant) + 캠페인 수신자 필터 LIKE 이스케이프 누락(LOW).

  조사 에이전트가 실측(격리 DB + 실제 test_client, 별도 in-memory sqlite3)으로
  증명하고 이번 라운드에서 재확인한 결함:

  ① api_partner_defect_dispute() 는 dispute_reason/disputed_at 을 남기는데, 그
     값을 지우거나 판정 결과를 알리는 코드가 전 코드베이스에 없다(주석 자체가
     "되돌리는 경로가 전 코드에 없다"고 말한다). 관리자가 귀책을 정하거나 하자를
     종결해도 화면의 "이의 검토중" 배지는 영원히 뜨고, 협력사에게는 아무 알림도
     안 간다.
  ② SAVE_BASE_SQL(절감 기준선, SQL)과 saving_base()(같은 기준선, 파이썬)가 서로
     다른 알고리즘이었다 — SQL 은 "engine_high>0 인 가장 최근 행"과
     "field_amount>0 인 가장 최근 행"을 **독립적으로** 찾는데, 파이썬은 가장
     최근 결렬 행 딱 하나만 보고 그 행의 두 컬럼을 따졌다. 결렬 행이 2개 이상
     이고 값이 서로 다른 행에 나뉘어 있으면 두 구현이 다른 기준선을 낸다.
     (open_agreement() 가 결렬 행 중복 생성을 막아 지금은 새로 못 만들지만,
     막아 놓은 코드 자체가 결함의 증거이자 재발 방지선일 뿐 파이썬 쪽 계산식은
     안 고쳤었다 — 방어가 하나뿐이면 그 방어가 뚫리는 순간 바로 드러난다.)
  ③ 캠페인(마케팅) 수신자 필터의 major/region LIKE 검색만 이 파일의 다른 모든
     LIKE 검색(_kw_like_clause)과 달리 _like_escape 를 안 거쳤다 — 검색어의
     '_'/'%' 가 와일드카드로 동작해 의도보다 넓게 걸린다.

      python test_scan_round61_fixes.py
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
DB_SRC = read("db.py")
PP_SRC = read(os.path.join("templates", "partner_portal.html"))

print("═" * 72)
print("  스캔 61라운드 회귀 — 하자이의 무응답 + 절감기준선 두 구현 불일치 + LIKE이스케이프")
print("═" * 72)


def _body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
chk('("defects", "dispute_resolved_at", "TEXT")' in DB_SRC,
    "★ ① db.py — dispute_resolved_at 컬럼 마이그레이션이 있다")

update_body = _body(APP_SRC, "api_defect_update")
chk("dispute_decided" in update_body and 'notify(conn, "하자이의처리"' in update_body,
    "★★★ ① api_defect_update — 귀책 결정·종결 시점에 이의 협력사에게 실제로 알린다")
chk('"cost_bearer" in d or st in ("완료", "반려")' in update_body,
    "★ ① 트리거가 귀책결정/종결로 좁혀져 있다(담당자·기한만 고친 건 과잉판정 안 함)")

chk("d.dispute_resolved_at" in PP_SRC,
    "★ ① partner_portal.html — 배지가 검토중/검토완료를 구분한다")

save_body = _body(APP_SRC, "saving_base")
chk(save_body.count("FROM field_agreements") == 2
    and "SELECT engine_high, field_amount FROM field_agreements" not in save_body,
    "★★★ ② saving_base — engine_high·field_amount 를 각자 독립적으로(행 하나가 아니라) 찾는다")

#  [라운드165] region 은 더 이상 SQL LIKE 를 안 쓴다 — region_matches() 로
#  파이썬에서 거르도록 바뀌어(표기 149가지 문제 해결) 이스케이프 자체가
#  무의미해졌다. major 는 여전히 LIKE 이므로 그쪽만 계속 확인한다.
#  ⚠⚠ [라운드607] 형제결함군(raw d.get(...)이 JSON 비문자열이면 500)을 고치며
#    f['major'] 가 f.get('major')로, 바깥에 _s()가 덧씌워졌다 — _like_escape가
#    여전히 감싸고 있는지(이 검사의 본래 취지)는 그대로이므로 리터럴만 갱신한다
#    (검사 취지 약화 없음, [4]의 실측 재현도 그대로 통과함으로 행동 불변 확인).
#  ⚠⚠ [라운드623] _like_escape(_s(...)) 직접호출을 같은 컬럼조합(name/region/
#    major)에 이미 쓰이는 공용 헬퍼 _kw_like_clause(_s(...), ["major"])로
#    교체했다(그 헬퍼 내부가 _like_escape를 그대로 부르므로 이스케이프 자체는
#    안 없어짐 — 오히려 가운뎃점(ㆍ/･) 정규화까지 덤으로 받는다, round499·
#    _kw_like_clause docstring 참고). 이 검사의 본래 취지(이스케이프를 거치는가)
#    는 그대로이므로 리터럴만 갱신 — round607이 61/63/135와 겪은 것과 같은 콜리전.
chk("_like_escape(_s(f.get('major')))" in APP_SRC
    or '_kw_like_clause(_s(f.get("major")), ["major"])' in APP_SRC,
    "★ ③ _campaign_recipients — major LIKE 가 이스케이프를 거친다"
    "(round623: 공용 _kw_like_clause 경유로 교체)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 서버(test_client)로 ① 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round61_")
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
    _tok = "regress-round61-csrf-token"
    _hdr = {"X-CSRF-Token": _tok}

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사61','활성')").lastrowid
    p_p = conn.execute(
        "INSERT INTO partners(name,partner_type,status) VALUES('이의제기업체61','시공사','활성')"
    ).lastrowid
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                "VALUES('admin61','x','검증','중간관리자')")
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,partner_id,partner_name,category,region) "
        "VALUES(?,'시공중',?,?,?,?,?,'서울')",
        ("61P-0001", "검증보험사61", iid, p_p, "이의제기업체61", "누수·배관·설비")).lastrowid
    did = conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,insurer,insurer_id,partner_id,partner_name,"
        "                    title,status,created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))",
        ("D26-6101", cid, "61P-0001", "검증보험사61", iid, p_p, "이의제기업체61",
         "누수 재발", "접수")).lastrowid
    conn.commit(); conn.close()

    def _admin_sess(sess):
        sess["admin"] = "admin61"; sess["admin_role"] = "중간관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = _tok

    def _n_notify_p():
        c = DB.get_db()
        n = c.execute("SELECT COUNT(*) FROM notifications WHERE ntype='하자이의처리' "
                     "AND partner_id=?", (p_p,)).fetchone()[0]
        c.close()
        return n

    with client.session_transaction() as sess:
        sess["partner_id"] = p_p; sess["_csrf"] = _tok
    rd = client.post(f"/api/partner/defects/{did}/dispute",
                     json={"reason": "저희 시공 범위 밖의 배관 노후로 인한 재발입니다."},
                     headers=_hdr)
    chk(rd.status_code == 200, "STEP 협력사가 귀책 이의를 제기한다", (rd.status_code, rd.get_json()))

    conn = DB.get_db()
    row1 = dict(conn.execute("SELECT dispute_reason, dispute_resolved_at FROM defects "
                             "WHERE id=?", (did,)).fetchone())
    conn.close()
    chk(bool(row1["dispute_reason"]) and not row1["dispute_resolved_at"],
        "STEP 이의가 접수되고 아직 검토완료는 아니다(전제 확인)", row1)

    #  대조군 — 이의와 무관한 필드(due_date)만 고치면 아직 '검토완료'로 닫히면 안 된다
    with client.session_transaction() as sess:
        _admin_sess(sess)
    r_unrelated = client.patch(f"/api/defects/{did}", json={"due_date": "2026-09-30"}, headers=_hdr)
    chk(r_unrelated.status_code == 200, "STEP 이의와 무관한 필드(기한) 수정", r_unrelated.status_code)
    conn = DB.get_db()
    row2 = dict(conn.execute("SELECT dispute_resolved_at FROM defects WHERE id=?", (did,)).fetchone())
    conn.close()
    chk(not row2["dispute_resolved_at"],
        "★ 대조군 — 이의와 무관한 필드만 고치면 아직 검토완료로 안 닫힌다(과잉판정 아님)", row2)
    chk(_n_notify_p() == 0, "★ 대조군 — 아직 협력사에게 '하자이의처리' 알림이 안 갔다", None)

    #  실제 판정 — 귀책을 정하면 그 순간 검토완료로 닫히고 협력사에게 알림이 간다
    r_decide = client.patch(f"/api/defects/{did}", json={"cost_bearer": "보험사"}, headers=_hdr)
    chk(r_decide.status_code == 200, "STEP 관리자가 귀책을 '보험사'로 정한다", r_decide.status_code)
    conn = DB.get_db()
    row3 = dict(conn.execute("SELECT dispute_reason, dispute_resolved_at, cost_bearer "
                             "FROM defects WHERE id=?", (did,)).fetchone())
    conn.close()
    chk(bool(row3["dispute_resolved_at"]) and row3["cost_bearer"] == "보험사",
        "★★★ ① 귀책이 정해지는 순간 dispute_resolved_at 이 채워진다"
        "(고치기 전엔 dispute_reason 이 영원히 '검토중'으로 남았다)", row3)
    chk(bool(row3["dispute_reason"]),
        "★ dispute_reason 원문은 지우지 않고 그대로 남는다(협력사가 되짚어 볼 수 있어야 한다)")
    chk(_n_notify_p() == 1,
        "★★★ ① 협력사에게 '하자이의처리' 알림이 실제로 1건 갔다"
        "(고치기 전엔 0건 — 판정 결과를 알 방법이 없었다)", None)

    #  재판정(같은 필드를 다시 고쳐도) — 이미 닫힌 이의를 또 알리지 않는다
    r_again = client.patch(f"/api/defects/{did}", json={"cost_bearer": "시행사"}, headers=_hdr)
    chk(r_again.status_code == 200, "STEP 귀책을 다시 '시행사'로 바꾼다(재판정)", r_again.status_code)
    chk(_n_notify_p() == 1,
        "★ 이미 검토완료된 이의는 재판정해도 알림이 중복으로 안 간다(스팸 방지)", None)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — 직접 호출로 ② saving_base 재현")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    cid2 = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region,est_price) "
        "VALUES(?,'완료',?,?,?,'서울',1000000)",
        ("61S-0001", "검증보험사61", iid, "누수·배관·설비")).lastrowid
    #  옛(더 작은 id) 결렬 행 — engine_high 만 있음
    conn.execute(
        "INSERT INTO field_agreements(case_id,status,engine_high,field_amount,created_at) "
        "VALUES(?,'결렬',5000000,0,datetime('now','+9 hours'))", (cid2,))
    #  최근(더 큰 id) 결렬 행 — field_amount 만 있음(engine_high 는 0)
    conn.execute(
        "INSERT INTO field_agreements(case_id,status,engine_high,field_amount,created_at) "
        "VALUES(?,'결렬',0,3000000,datetime('now','+9 hours'))", (cid2,))
    conn.commit()

    base_py = A.saving_base(conn, cid2, 1000000)
    base_sql = conn.execute(
        f"SELECT ({A.SAVE_BASE_SQL}) AS b FROM cases WHERE id=?", (cid2,)).fetchone()["b"]
    conn.close()
    chk(base_sql == 5000000, "STEP SAVE_BASE_SQL(기준) 은 5,000,000을 낸다(전제 확인)", base_sql)
    chk(base_py == base_sql,
        "★★★ ② saving_base() 파이썬 구현이 SAVE_BASE_SQL 과 이제 같은 답(5,000,000)을 낸다"
        "(고치기 전엔 최근 행만 봐서 3,000,000 — 서로 달랐다)", (base_py, base_sql))

    # ══════════════════════════════════════════════════════════
    print("\n[4] 실행 — 직접 호출로 ③ LIKE 이스케이프 재현")
    # ──────────────────────────────────────────────────────────
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,major,email,email_opt_out,email_consent) "
        "VALUES('밑줄포함업체61','시공사','활성','토목_비상',?,0,1)", ("wild61@example.com",))
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,major,email,email_opt_out,email_consent) "
        "VALUES('무관업체61','시공사','활성','토목A비상',?,0,1)", ("other61@example.com",))
    conn.commit()

    ok, _no_contact, _opted, _no_consent = A._campaign_recipients(
        conn, {"major": "토목_비상", "channel": "메일"})
    names = [r["name"] for r in ok]
    conn.close()
    chk("밑줄포함업체61" in names,
        "★ 리터럴 밑줄이 든 업체명은 그대로 매칭된다", names)
    chk("무관업체61" not in names,
        "★★★ ③ 이스케이프 안 된 '_' 가 아무 글자나 매칭하지 않는다"
        "(고치기 전엔 '_' 가 와일드카드로 동작해 무관한 업체까지 잡혔다)", names)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드61 실측 준비/실행", f"{type(e).__name__} {e}")
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
