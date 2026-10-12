# -*- coding: utf-8 -*-
"""스캔 46라운드 회귀 — N+1 쿼리 4곳(사진재사용·하자·보험사/협력사 대시보드).

  조사 에이전트가 실측(쿼리 수, N=2배로 늘려 기울기 확인)으로 증명한 결함
  4곳을 전부 배치 조회로 고쳤다. 이 회귀는 각 라우트를 두 배 다른 행수로
  두 번 돌려 **쿼리 수가 행수에 비례해 늘지 않는지**(N+1 → O(1)에 가깝게)와
  **값이 여전히 정확한지**를 함께 본다(빨라지는 대신 틀려지면 의미 없다).

      python test_scan_round46_fixes.py
"""
import io
import itertools
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []
#  각 시드 함수를 두 번(누적 스케일) 부르므로, case_no 충돌 없이 계속 늘어나는
#  번호를 준다 — 루프 지역 인덱스(0..n-1)를 그대로 쓰면 두 번째 호출이 첫 호출과 겹친다.
_seq = itertools.count()


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 46라운드 회귀 — N+1 쿼리 4곳")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk('WHERE p.sha256 IN ({",".join("?" * len(shas))})' in APP_SRC,
    "① photo-reuse — sha256 을 IN() 으로 한 번에 묶는다")
chk('SELECT id, completed_at, warranty_months FROM cases WHERE id IN ({_ph})' in APP_SRC,
    "② defects — 보증잔여 조회가 IN() 배치로 바뀌었다")
chk("_BID_CAP_FA_UNSET" in APP_SRC and "fa=_BID_CAP_FA_UNSET" in APP_SRC,
    "③ bid_cap_of 가 미리 조회한 값을 받을 수 있다(하위호환)")
chk("def _fa_latest(cid):" in APP_SRC and "def _fa_latest_with_engine_high(cid):" in APP_SRC,
    "③ 보험사 대시보드가 field_agreements 를 배치로 미리 모은다")
chk('_wd = int((_now_kst - _cdt).total_seconds() // 86400)' in APP_SRC,
    "④ 협력사 대시보드 wait_days 가 DB 왕복 없이 계산된다")
chk('_co_map.setdefault(_r.pop("case_id"), _r)' in APP_SRC,
    "④ 협력사 대시보드 change_orders 조회가 IN() 배치로 바뀌었다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제로 쿼리 수가 행수에 비례해 늘지 않는가 + 값이 맞는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="n1_46_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

#  ⚠ sqlite3.Connection 은 C 타입이라 메서드를 직접 못 바꿔친다
#    (TypeError: cannot set 'execute' attribute of immutable type).
#    대신 sqlite3.connect() 를 감싸, 만들어지는 커넥션마다
#    set_trace_callback 을 걸어 실행되는 문장 수를 센다 — DB.get_db() 를
#    포함해 어디서 커넥션을 열든(app.py 의 자체 추적 래퍼와도 무관하게) 잡힌다.
_qcount = [0]
_orig_connect = sqlite3.connect


def _counting_connect(*a, **k):
    conn = _orig_connect(*a, **k)
    conn.set_trace_callback(lambda sql: _qcount.__setitem__(0, _qcount[0] + 1))
    return conn


def _hits(fn, *a, **k):
    """fn 실행 동안 발생한 sqlite 쿼리 수."""
    before = _qcount[0]
    out = fn(*a, **k)
    return out, _qcount[0] - before


try:
    sqlite3.connect = _counting_connect
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin46','x','검증','최고관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('검증보험46','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,jobs_done) "
        "VALUES('검증업체46','시공사','활성',0)").lastrowid
    conn.commit()
    conn.close()

    import app as A
    client = A.app.test_client()
    with client.session_transaction() as sess:
        sess["admin"] = "admin46"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"

    # ── ① photo-reuse ──────────────────────────────────────────
    def _seed_photo_groups(n_groups):
        c = DB.get_db()
        for g in range(n_groups):
            sha = f"sha46group{next(_seq):06d}"
            for k in range(2):    # 그룹당 사진 2장 = 서로 다른 사건에 같은 파일
                cid = c.execute(
                    "INSERT INTO cases(case_no,status,insurer_id) VALUES(?,?,?)",
                    (f"46P-{next(_seq)}", "접수", iid)).lastrowid
                c.execute("INSERT INTO photos(case_id,sha256,uploader_role,uploader,rel_path) "
                          "VALUES(?,?,?,?,?)",
                          (cid, sha, "협력사", "검증업체46", f"46/{next(_seq)}.jpg"))
        c.commit(); c.close()

    _seed_photo_groups(5)
    r1, q1 = _hits(client.get, "/api/photo-reuse")
    _seed_photo_groups(5)   # 그룹 수를 2배로
    r2, q2 = _hits(client.get, "/api/photo-reuse")
    d1, d2 = r1.get_json(), r2.get_json()
    chk(d1["count"] == 5 and d2["count"] == 10, "★ 그룹 수 자체는 정확하다(5→10)",
        (d1["count"], d2["count"]))
    chk(all(len(g["photos"]) == 2 for g in d2["groups"]),
        "★★ 그룹당 사진 2장씩 정확히 묶였다(sha256 별 그룹핑 정확)")
    print(f"       [①] q1={q1} q2={q2} delta={q2 - q1}")
    chk(q2 - q1 < 3, f"★★★ 그룹 수 2배(5→10)에도 쿼리 증가가 미미하다(N+1 아님)",
        f"q1={q1} q2={q2}")

    # ── ② defects ───────────────────────────────────────────────
    def _seed_defects(n):
        c = DB.get_db()
        for _ in range(n):
            _sq = next(_seq)
            cid = c.execute(
                "INSERT INTO cases(case_no,status,insurer_id,completed_at,warranty_months) "
                "VALUES(?,?,?,?,?)",
                (f"46D-{_sq}", "완료", iid, "2026-01-01 00:00:00", 12)).lastrowid
            c.execute("INSERT INTO defects(case_id,defect_no,title,status,severity) "
                      "VALUES(?,?,?,?,?)", (cid, f"D46-{_sq}", "누수", "접수", "보통"))
        c.commit(); c.close()

    _seed_defects(10)
    r3, q3 = _hits(client.get, "/api/defects")
    _seed_defects(10)
    r4, q4 = _hits(client.get, "/api/defects")
    d3, d4 = r3.get_json(), r4.get_json()
    chk(len(d3) == 10 and len(d4) == 20, "★ 하자 건수 자체는 정확하다(10→20)",
        (len(d3), len(d4)))
    chk(all(x["warranty_left"] is not None for x in d4),
        "★★ 보증잔여(warranty_left)가 전 건에 정확히 채워졌다")
    print(f"       [②] q3={q3} q4={q4} delta={q4 - q3}")
    chk(q4 - q3 < 3, "★★★ 하자 건수 2배(10→20)에도 쿼리 증가가 미미하다(N+1 아님)",
        f"q3={q3} q4={q4}")

    # ── ③ 보험사 대시보드 ─────────────────────────────────────
    with client.session_transaction() as sess:
        sess.clear(); sess["insurer_id"] = iid; sess["insurer_name"] = "검증보험46"
    #  ⚠ 이 라우트는 맨 위에서 _sweep_if_due() 를 부른다 — 실제 스윕은 1분에 한 번만
    #    돌고(그 안에서만 몇 쿼리 더 나간다) 그 뒤로는 조용히 건너뛴다. 첫 측정
    #    호출이 그 1회성 비용을 떠안으면 delta 가 음수로 나와(실측) N+1 신호가
    #    완전히 가려진다 — 측정 전에 한 번 예열해 그 비용을 미리 떨군다.
    client.get("/api/insurer/dashboard")

    def _seed_insurer_cases(n):
        c = DB.get_db()
        for _ in range(n):
            cid = c.execute(
                "INSERT INTO cases(case_no,status,insurer_id,est_price,award_amount) "
                "VALUES(?,?,?,?,?)",
                (f"46I-{next(_seq)}", "입찰중", iid, 1000000, 0)).lastrowid
            c.execute(
                "INSERT INTO field_agreements(case_id,partner_id,partner_name,status,"
                "field_amount,engine_low,engine_high) VALUES(?,?,?,?,?,?,?)",
                (cid, pid, "검증업체46", "결렬", 900000, 800000, 950000))
        c.commit(); c.close()

    _seed_insurer_cases(10)
    r5, q5 = _hits(client.get, "/api/insurer/dashboard")
    _seed_insurer_cases(10)
    r6, q6 = _hits(client.get, "/api/insurer/dashboard")
    d5, d6 = r5.get_json(), r6.get_json()
    #  ⚠ 대시보드 쿼리는 상태 무관 전건이라 앞선 ①·② 구간이 같은 iid 로 심어 둔
    #    사건까지 섞여 나온다 — 이 구간이 만든 case_no("46I-")만 걸러서 본다.
    mine5 = [c_ for c_ in d5["cases"] if c_["case_no"].startswith("46I-")]
    mine6 = [c_ for c_ in d6["cases"] if c_["case_no"].startswith("46I-")]
    chk(len(mine5) == 10 and len(mine6) == 20,
        "★ 사건 수 자체는 정확하다(10→20)", (len(mine5), len(mine6)))
    chk(all(c_["auction_round"] == 2 and c_["bid_floor"] == 1000000 for c_ in mine6),
        "★★ 2차 회차·하한(가견적) 값이 전 건에 정확하다(field_agreements 배치 결과 정확)",
        [(c_["auction_round"], c_["bid_floor"]) for c_ in mine6[:3]])
    print(f"       [③] q5={q5} q6={q6} delta={q6 - q5} (전체사건 {len(d5['cases'])}→{len(d6['cases'])})")
    chk(q6 - q5 < 3, "★★★ 사건 수 2배(10→20)에도 쿼리 증가가 미미하다(N+1 아님)",
        f"q5={q5} q6={q6}")

    # ── ④ 협력사 대시보드 ─────────────────────────────────────
    with client.session_transaction() as sess:
        sess.clear(); sess["partner_id"] = pid; sess["partner_name"] = "검증업체46"

    def _seed_partner_data(n):
        c = DB.get_db()
        for _ in range(n):
            _sq = next(_seq)
            c.execute(
                "INSERT INTO settlements(case_id,case_no,insurer,partner_name,amount,fee,"
                "payout,transfer_status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (None, f"46S-{_sq}", "검증보험46", "검증업체46", 1000000, 100000, 900000,
                 "대기", "2026-08-01 00:00:00"))
            cid = c.execute(
                "INSERT INTO cases(case_no,status,insurer_id,partner_id) VALUES(?,?,?,?)",
                (f"46C-{_sq}", "시공중", iid, pid)).lastrowid
            c.execute(
                "INSERT INTO change_orders(case_id,incumbent_partner_id,status,"
                "combined_amount,add_low) VALUES(?,?,?,?,?)",
                (cid, pid, "원업체제안", 1200000, 200000))
        c.commit(); c.close()

    _seed_partner_data(8)
    r7, q7 = _hits(client.get, "/api/partner/dashboard")
    _seed_partner_data(8)
    r8, q8 = _hits(client.get, "/api/partner/dashboard")
    d7, d8 = r7.get_json(), r8.get_json()
    chk(len(d7["settlements"]) == 8 and len(d8["settlements"]) == 16,
        "★ 정산 건수 자체는 정확하다(8→16 누적)",
        (len(d7["settlements"]), len(d8["settlements"])))
    from datetime import datetime as _dt2, timedelta as _td2
    _expected_wd = int(((_dt2.utcnow() + _td2(hours=9))
                        - _dt2(2026, 8, 1)).total_seconds() // 86400)
    chk(all(s["wait_days"] == _expected_wd for s in d8["settlements"]),
        "★★ wait_days 가 DB 없이도 전 건에 정확한 값으로 채워졌다(직접 계산과 일치)",
        f"기대={_expected_wd} 실제={[s['wait_days'] for s in d8['settlements'][:3]]}")
    conn3 = DB.get_db()
    n_co = conn3.execute(
        "SELECT COUNT(*) n FROM change_orders WHERE incumbent_partner_id=?", (pid,)
    ).fetchone()["n"]
    conn3.close()
    chk(n_co == 16, "협력사 사건·변경건 시드가 누적됐다(8+8)", n_co)
    my_cases8 = d8.get("my_cases", [])
    chk(len(my_cases8) == 16, "★ 내 사건 수 자체는 정확하다(8→16 누적)", len(my_cases8))
    chk(all((mc.get("co_offer") or {}).get("combined_amount") == 1200000 for mc in my_cases8),
        "★★ 원업체제안 change_order 값이 전 건에 정확히 붙었다")
    chk(all("case_id" not in (mc.get("co_offer") or {"case_id": None}) for mc in my_cases8),
        "★ co_offer 응답 모양이 그대로다(내부 그룹핑용 case_id 가 안 새어나간다)")
    print(f"       [④] q7={q7} q8={q8} delta={q8 - q7}")
    chk(q8 - q7 < 3, "★★★ 사건 수 2배(8→16)에도 쿼리 증가가 미미하다(N+1 아님)",
        f"q7={q7} q8={q8}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ N+1 배치 실측", f"{type(e).__name__} {e}")
finally:
    sqlite3.connect = _orig_connect
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
