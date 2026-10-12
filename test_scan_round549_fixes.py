# -*- coding: utf-8 -*-
"""스캔 549라운드 회귀 — 하자 처리(api_defect_update, PATCH /api/defects/<id>)가
   조치내용(resolution) 등 필드값이 실제로 안 바뀌어도 매번 UPDATE + "하자 처리"
   감사로그를 남기던 결함.

   조사 배경 — 오케스트레이터 지시문이 이미 닫힌 각도로 명시한 "값 불변인데도
   감사로그+UPDATE" 패턴(api_admin_update·api_partner_profile_update·
   api_insurer_profile_update·api_me_update, 4곳 "이미 알려진 인스턴스")과 겹치지
   않는 새 각도를 찾다가, 그 4곳을 고친 라운드(421·543)의 자기 자신 주석이 서로를
   "형제"로 지목하며 이식해 온 바로 그 관례(`if 새값 != 옛값:` 로 감싸고서야
   UPDATE+로그)를, 하자 처리 라우트(api_defect_update, app.py:14862)는 받은 적이
   없다는 것을 직접 소스를 읽어 확인했다 — 4곳 모두 "단일 필드 정보수정" 라우트인
   반면 이 라우트는 하자 상태·귀책·심각도·기한을 한 번에 다루는 다중필드 라우트라
   그동안의 "4곳 전수" 조사망에 안 걸렸던 것으로 보인다. 즉 같은 결함 부류의
   **5번째, 지금까지 알려지지 않은 인스턴스**다.

   결함 — 상태(status) 분기(14895행)는 이미 위(14880행)에서
   `if st and st == row["status"]:` 로 조기 반환해 "값이 같으면 UPDATE·로그
   없음"을 보장하는데, 바로 아래 resolution·severity·due_date·cost_bearer 4개
   필드 루프(수정 전 14965~14968행)는 `if f in d:` 만 보고 값 비교 없이
   sets/vals 에 무조건 담았다. det(로그 문구) 계산(수정 전 14997~14999행)은 이미
   `str(row[f] or "") != str(d[f] or "")` 로 걸러 로그 "문구" 자체는 거짓 변경을
   말하지 않았지만, 그 앞의 UPDATE 발사 여부를 막는 관문이 없어 **내용은 비어도
   ("하자번호"만 담긴) "하자 처리" 로그 행 자체와 자기자신에게 같은 값을 다시
   쓰는 UPDATE 는 매번 났다**.

   실사용 영향(추정이 아니라 프론트 코드로 확인) — static/admin.js:defectAct
   (4051행)는 조치내용 입력칸(#d_res)의 현재 값을 매번 `body = {resolution: res}`
   로 무조건 실어 보낸다(4083행). 같은 함수의 4085행 주석이 바로 이 자리에서
   "값이 안 바뀌었으면 안 보낸다 — 서버가 'cost_bearer in d' 를 '담당자가 방금
   정했다'는 신호로 쓰기 때문"이라며 cost_bearer 는 이미 변경분만 보내게
   막아 뒀는데, resolution 자신은 그 방어가 없다. 즉 조치내용을 안 건드리고
   상태만 바꾸는(예: '확인중'→'재시공배정') 모든 정상 조작마다, resolution 이
   안 바뀌었는데도 "하자 처리" 로그가 (내용 없이) 남고 UPDATE 가 한 번 더 난다
   — 하자 처리 이력(admin.js 하자 상세 타임라인이 이 로그를 그대로 보여준다)이
   실제 조치 횟수보다 부풀어 보인다.

   고침 — 새 정책·헬퍼 없이, 4개 필드의 "실제로 바뀐 것만" 판정을 det 계산이
   이미 쓰던 비교식(`str(row[f] or "") != str(d[f] or "")`) 그대로 `changed_fields`
   리스트로 뽑아, sets 루프가 그 목록만 돌게 했다. 이미 값이 같은 필드는 sets 에
   들어가지 않으므로, 다른 변경이 전혀 없으면 UPDATE 자체가 안 나가고
   (else: rollback) 로그도 없다. 형제(role 분기·api_admin_update·
   _sub_update_impl)와 완전히 같은 원칙이다.
   ⚠ 1차 시도는 det 계산도 changed_fields 를 재사용하도록 통합했으나, 이 세션의
   실측(run_all_tests.py --quick)이 test_scan_round6_fixes.py:131("하자 귀책
   변경이 '정보수정' 한 단어로 끝나지 않는다")을 그 리팩터로 깨뜨림을 즉시
   잡아냈다 — det 의 정확한 소스 문자열(`for f in ("cost_bearer", "severity",
   "resolution", "due_date")`)을 그 옛 테스트가 그대로 참조하고 있었다. 동작은
   동일해도 문자열이 달라져 생긴 회귀라, 옛 테스트를 고치는 대신 det 계산은
   원래 형태로 남기고 sets 루프만 changed_fields 로 고쳤다(아래 [0]이 이 자리를
   함께 확인한다).

   app.py 자신에 정의된 라우트 함수(api_defect_update)를 고쳤다 — 이미 떠 있는
   프로세스가 있다면 재시작해야 새 가드가 실제 요청에 반영된다.

      python test_scan_round549_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\n@app.", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 549라운드 회귀 — 하자 처리(api_defect_update)가 값 불변인데도")
print("  매번 UPDATE+감사로그를 쏘던 결함 (형제 4곳과 같은 부류의 5번째 인스턴스)")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    du_body = _py_fn_body(APP_SRC, "api_defect_update")
    chk("changed_fields = [f for f in" in du_body,
        "★★★★★ api_defect_update() 에 changed_fields 공유 목록이 생겼다"
        "(고치기 전엔 이 줄이 없었다)")
    #  ⚠ [1차 시도 교훈] det 계산까지 changed_fields 로 통합했더니 이 세션의
    #    이 실행에서 형제(test_scan_round6_fixes.py:131)가 정확히 이 소스
    #    문자열('for f in ("cost_bearer", "severity", "resolution", "due_date")')로
    #    "귀책 변경이 '정보수정' 한 단어로 안 끝난다"를 검사하고 있음을 실측
    #    회귀(run_all_tests.py --quick)로 발견했다 — 동작은 100% 동일한데
    #    문자열만 달라져 옛 테스트가 깨졌다. 옛 테스트를 고치는 대신 sets 를
    #    막는 부분(실제 결함)만 changed_fields 로 고치고 det 는 원래 형태
    #    그대로 둔다 — 그래서 sets 루프에서만 1번 쓰인다.
    chk(du_body.count('for f in changed_fields') == 1,
        "★★★★ sets 루프가 changed_fields 를 쓴다(1곳 — det 는 형제 테스트 "
        "호환을 위해 옛 형태 그대로 남겨 뒀다)",
        du_body.count('for f in changed_fields'))
    _tuple_lit = '("resolution", "severity", "due_date", "cost_bearer")'
    chk(du_body.count(_tuple_lit) == 1,
        "★★★★★ changed_fields 정의에 새 필드 튜플이 정확히 1번 있다",
        du_body.count(_tuple_lit))
    _i_changed = du_body.index("changed_fields = [f for f in")
    _i_loop = du_body.index("for f in changed_fields:")
    _i_sets = du_body.index('sets.append(f"{f}=?"); vals.append(v)')
    chk(_i_changed < _i_loop < _i_sets,
        "★★★★ 순서가 옳다 — changed_fields 계산 → sets 루프"
        "(공유 목록이 소비처보다 먼저 정의된다)")
    #  ★ 형제(round6) 호환 — det 계산은 이번 라운드가 일부러 손대지 않았다.
    #    이 문자열이 사라지면 test_scan_round6_fixes.py:131 이 다시 깨진다.
    chk('for f in ("cost_bearer", "severity", "resolution", "due_date")' in du_body,
        "★★★★ det 계산(로그 문구)은 옛 형태 그대로다"
        "(test_scan_round6_fixes.py:131 이 이 정확한 문자열을 참조 — 과잉수정 없음)")
    #  형제(status 분기의 조기 unchanged 반환)는 이번 라운드가 손대지 않았다 — 대조.
    chk('if st and st == row["status"]:' in du_body,
        "STEP 형제(status 무변경 조기반환)는 이번 라운드가 손대지 않고 그대로다"
        "(이식 원본 — 과잉수정 없음)")
    chk('dispute_decided = "cost_bearer" in d or st in ("완료", "반려")' in du_body,
        "STEP dispute_decided 판정(존재 여부 기준)도 그대로다"
        "(cost_bearer 는 화면이 이미 변경분만 보내므로 이 술어는 손대지 않는다)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드549 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 실행계정(중간관리자) + 대상 하자 3건")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round549_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r549-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
did_a = did_b = did_c = pid = cid = None
INIT = dict(resolution="초기 조치 메모", severity="보통", cost_bearer="시행사",
            due_date="2026-09-20")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin549"
        sess["admin_name"] = "실행계정549"
        sess["admin_role"] = "중간관리자"
        sess["_csrf"] = CSRF
    return c


def _log_count(conn, defect_no):
    return conn.execute(
        "SELECT COUNT(*) FROM activity_log WHERE action='하자 처리' AND detail LIKE ?",
        (defect_no + "%",)).fetchone()[0]


def _mk_defect(conn, no):
    return conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,partner_id,title,severity,"
        "                    status,cost_bearer,resolution,due_date,created_at) "
        "VALUES(?,?,?,?,'테스트 하자',?,?,?,?,?,?)",
        (no, cid, "R549-CASE", pid, INIT["severity"], "확인중", INIT["cost_bearer"],
         INIT["resolution"], INIT["due_date"], DB.now())).lastrowid


try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin549','x','실행계정549','중간관리자')")
    pid = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,created_at) "
        "VALUES('R549업체','시공사','활성','가드레일','서울',?)", (DB.now(),)).lastrowid
    cid = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,created_at) "
        "VALUES('R549-CASE','완료','가드레일','서울',?)", (DB.now(),)).lastrowid
    did_a = _mk_defect(conn0, "R549-DF-A")
    did_b = _mk_defect(conn0, "R549-DF-B")
    did_c = _mk_defect(conn0, "R549-DF-C")
    conn0.commit(); conn0.close()
    chk(bool(pid and cid and did_a and did_b and did_c),
        "STEP 실행계정 + 협력사·사건 + 하자 3건 생성", (pid, cid, did_a, did_b, did_c))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드549 [1] 준비", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[2] 실행(진짜 라우트, 지금 코드) — 아무 값도 안 바뀐 채(admin.js 가 "
      "매번 그대로 되돌려보내는 resolution 포함) 그대로 재저장하면 "
      "'하자 처리' 로그가 안 생기고 UPDATE 도 안 나간다")
# ------------------------------------------------------------------
try:
    admin_c = _admin_client()
    #  admin.js defectAct() 가 실제로 보내는 모양 그대로 — status 없이,
    #  resolution·severity·cost_bearer·due_date 를 전부 "지금 값 그대로" 담는다.
    r = admin_c.patch(f"/api/defects/{did_a}", headers=H, json={
        "resolution": INIT["resolution"], "severity": INIT["severity"],
        "cost_bearer": INIT["cost_bearer"], "due_date": INIT["due_date"]})
    rbody = r.get_json() or {}
    chk(r.status_code == 200 and rbody.get("ok") is True,
        "STEP PATCH /api/defects/<id> 가 200·ok:true 를 돌려준다", (r.status_code, rbody))

    conn = DB.get_db()
    row_a = conn.execute("SELECT resolution, severity, cost_bearer, due_date "
                          "  FROM defects WHERE id=?", (did_a,)).fetchone()
    chk(dict(row_a) == INIT, "STEP 값 자체는 전부 그대로다(같은 값 재저장)", dict(row_a))

    n_log_a = _log_count(conn, "R549-DF-A")
    chk(n_log_a == 0,
        "★★★★★ 지금 코드: 아무 것도 안 바뀌었으므로 '하자 처리' 로그가 0건이다"
        "(고치기 전엔 여기서 1건이 났다 — 내용은 하자번호뿐이라도)", n_log_a)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드549 [2] 지금 코드(완전 무변경 재저장)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[3] 회귀 안전 — 조치내용만 진짜로 바뀌면 지금 코드도 정상적으로 "
      "'하자 처리' 로그를 정확한 old→new 로 1건 남긴다(과잉교정 없음)")
# ------------------------------------------------------------------
try:
    admin_c2 = _admin_client()
    new_res = "재시공 자재 재발주 완료"
    r2 = admin_c2.patch(f"/api/defects/{did_b}", headers=H, json={
        "resolution": new_res, "severity": INIT["severity"],
        "cost_bearer": INIT["cost_bearer"], "due_date": INIT["due_date"]})
    rbody2 = r2.get_json() or {}
    chk(r2.status_code == 200 and rbody2.get("ok") is True,
        "STEP PATCH 성공(조치내용만 실제 변경)", (r2.status_code, rbody2))

    conn = DB.get_db()
    row_b = conn.execute("SELECT resolution FROM defects WHERE id=?", (did_b,)).fetchone()
    chk(row_b["resolution"] == new_res, "STEP DB 의 조치내용이 실제로 바뀌었다", row_b["resolution"])

    n_log_b = _log_count(conn, "R549-DF-B")
    chk(n_log_b == 1,
        "★★★★ 회귀 안전: 진짜 변경은 지금 코드에서도 정확히 1건 로그로 남는다"
        "(0건으로 과잉교정되지 않았다)", n_log_b)
    detail_row = conn.execute(
        "SELECT detail FROM activity_log WHERE action='하자 처리' "
        "AND detail LIKE 'R549-DF-B%'").fetchone()
    chk(bool(detail_row) and INIT["resolution"] in detail_row[0] and new_res in detail_row[0],
        "STEP 로그 문구에 실제 old→new 조치내용이 정확히 담겨 있다",
        detail_row[0] if detail_row else None)
    chk(bool(detail_row) and "severity" not in detail_row[0] and "cost_bearer" not in detail_row[0],
        "STEP 안 바뀐 필드(severity·cost_bearer·due_date)는 로그에 안 섞인다"
        "(det 필터는 이미 정확했다 — 이번 수정은 UPDATE 발사 여부만 고쳤다)",
        detail_row[0] if detail_row else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드549 [3] 회귀 안전(조치내용만 실제 변경)", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[4] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고, 이번 "
      "수정 직전의 실제 함수 본문을 문자열로 재구성해(exec, round543·547과 "
      "같은 방식) 같은 무변경 시나리오를 실행하면 정말 거짓 '하자 처리' "
      "로그가 남는가")
# ------------------------------------------------------------------
#  ⚠ 이 문자열은 이번 수정 **직전** 이 세션이 Read 로 확인한 api_defect_update
#    원문 그대로다(주석만 생략, 로직·순서는 100% 동일) — resolution 등 4개
#    필드 루프에 변경여부 비교가 없는 옛 형태다.
_PRE549_SRC = '''
def _api_defect_update_pre549(did):
    d = body()
    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    row = one(conn.execute("SELECT * FROM defects WHERE id=?", (did,)))
    if not row:
        conn.rollback(); conn.close(); return jsonify({"error": "없음"}), 404
    st = d.get("status")
    if st and st not in DEFECT_FLOW:
        conn.rollback(); conn.close()
        return jsonify({"error": "알 수 없는 상태입니다."}), 400
    if st and st == row["status"]:
        conn.rollback(); conn.close()
        return jsonify({"ok": True, "unchanged": True,
                        "message": f"이미 '{st}' 상태입니다."})
    if st and st not in DEFECT_NEXT.get(row["status"], ()):
        conn.rollback(); conn.close()
        return jsonify({"error": f"'{row['status']}' 에서 '{st}' 로는 바꿀 수 없습니다.",
                        "code": "DEFECT_BAD_TRANSITION"}), 409

    sets, vals = [], []
    if st:
        sets.append("status=?"); vals.append(st)
        if st != "완료" and row["status"] == "완료":
            sets.append("resolved_at=?"); vals.append(None)
        if st == "재시공배정":
            sets.append("assigned_at=?"); vals.append(DB.now())
            _due = d.get("due_date") or row["due_date"]
            notify(conn, "재시공배정", "알림톡", row["partner_name"] or "시행사",
                   f"{row['case_no']} 재시공이 배정되었습니다 (기한 {_due})",
                   audience_type="partner", partner_id=row["partner_id"],
                   case_id=row["case_id"], url="/app/partner")
        if st == "완료":
            sets.append("resolved_at=?"); vals.append(DB.now())
            notify(conn, "하자완료", "알림톡", row["insurer"] or "보험사",
                   f"{row['case_no']} 하자 재시공이 완료되었습니다",
                   audience_type="insurer", insurer_id=row["insurer_id"],
                   case_id=row["case_id"], url="/app/insurer")
        if st == "반려":
            notify(conn, "하자반려", "알림톡", row["insurer"] or "보험사",
                   f"{row['case_no']} 하자 접수가 반려되었습니다"
                   + (f" — {d['resolution']}" if (d.get("resolution") or "").strip() else ""),
                   audience_type="insurer", insurer_id=row["insurer_id"],
                   case_id=row["case_id"], url="/app/insurer")
    if "severity" in d and d["severity"] not in SEVERITY_VALUES:
        conn.rollback(); conn.close()
        return jsonify({"error": f"심각도는 {'/'.join(SEVERITY_VALUES)} 중 하나여야 합니다."}), 400
    if "cost_bearer" in d and d["cost_bearer"] not in ("시행사", "보험사", "협의필요"):
        conn.rollback(); conn.close()
        return jsonify({"error": "비용 부담은 시행사 / 보험사 / 협의필요 중 하나여야 합니다."}), 400
    if d.get("due_date"):
        if not re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}", d["due_date"]):
            conn.rollback(); conn.close()
            return jsonify({"error": "처리 기한은 'YYYY-MM-DD' 형식이어야 합니다."}), 400
        _norm = one(conn.execute("SELECT date(?) d", (d["due_date"],)))["d"]
        if _norm != d["due_date"]:
            conn.rollback(); conn.close()
            return jsonify({"error": "해석할 수 없는 날짜입니다."}), 400
    for f in ("resolution", "severity", "due_date", "cost_bearer"):
        if f in d:
            v = (d[f] or "")[:1000] if f == "resolution" else d[f]
            sets.append(f"{f}=?"); vals.append(v)
    dispute_pending = bool((row.get("dispute_reason") or "").strip()) \\
        and not (row.get("dispute_resolved_at") or "")
    dispute_decided = "cost_bearer" in d or st in ("완료", "반려")
    if dispute_pending and dispute_decided:
        sets.append("dispute_resolved_at=?"); vals.append(DB.now())
    if sets:
        vals.append(did)
        conn.execute(f"UPDATE defects SET {','.join(sets)} WHERE id=?", vals)
        if dispute_pending and dispute_decided:
            notify(conn, "하자이의처리", "알림톡", row["partner_name"] or "시행사",
                   f"{row['case_no']} {row['defect_no']} 귀책 이의가 검토되었습니다"
                   + (f" — 귀책: {d['cost_bearer']}" if (d.get("cost_bearer") or "").strip() else "")
                   + (f" · {d['resolution']}" if (d.get("resolution") or "").strip() else ""),
                   audience_type="partner", partner_id=row["partner_id"],
                   case_id=row["case_id"], url="/app/partner")
        refresh_partner_rating(conn, row["partner_id"])
        det = [f"{row['defect_no']} → {st}"] if st else [row["defect_no"]]
        det += [f"{f} {row[f] or '(없음)'} → {d[f]}"
                for f in ("cost_bearer", "severity", "resolution", "due_date")
                if f in d and str(row[f] or "") != str(d[f] or "")]
        DB.log(conn, actor(), "하자 처리", " · ".join(det))
        conn.commit()
    else:
        conn.rollback()
    conn.close()
    return jsonify({"ok": True})
'''
try:
    _ns = dict(vars(A))              # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE549_SRC, "<round549_pre_reconstructed>", "exec"), _ns)
    _old_update = _ns["_api_defect_update_pre549"]

    with A.app.test_request_context(
            f"/api/defects/{did_c}", method="PATCH",
            json={"resolution": INIT["resolution"], "severity": INIT["severity"],
                  "cost_bearer": INIT["cost_bearer"], "due_date": INIT["due_date"]}):
        from flask import session as _flask_session
        _flask_session["admin"] = "admin549"
        _flask_session["admin_name"] = "실행계정549"
        _flask_session["admin_role"] = "중간관리자"
        resp = _old_update(did_c)
    resp_obj = resp[0] if isinstance(resp, tuple) else resp
    chk(resp_obj is not None, "STEP 재구성한 옛 함수도 정상적으로 응답을 만든다")

    conn = DB.get_db()
    row_c = conn.execute("SELECT resolution, severity, cost_bearer, due_date "
                          "  FROM defects WHERE id=?", (did_c,)).fetchone()
    chk(dict(row_c) == INIT,
        "STEP 옛 코드(재구성)도 값 자체는 안 바꾼다(겉보기 동작은 지금 코드와 "
        "똑같다 — 그래서 그동안 아무도 눈치 못 챘다)", dict(row_c))
    n_old = _log_count(conn, "R549-DF-C")
    chk(n_old == 1,
        "★★★★★ 그런데 옛 코드(재구성)는 아무 값도 안 바뀌었는데도 "
        "'하자 처리' 감사로그를 1건 남긴다 — 지금 코드(위 [2])는 같은 "
        "시나리오에서 실제로 0건이었다. 이 차이가 이 회귀가 결함을 실제로 "
        "잡아낼 능력이 있다는 인과관계 증명이다", n_old)
    detail_row_c = conn.execute(
        "SELECT detail FROM activity_log WHERE action='하자 처리' "
        "AND detail LIKE 'R549-DF-C%'").fetchone()
    chk(bool(detail_row_c) and detail_row_c[0].strip() == "R549-DF-C",
        "STEP 거짓 로그는 내용이 비어(하자번호만) 있다 — det 필터 자체는 "
        "고치기 전에도 정확했으므로 '거짓 변경 문구'가 아니라 "
        "'헛UPDATE+빈 로그 낭비'가 옛 결함의 진짜 정체다",
        detail_row_c[0] if detail_row_c else None)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드549 [4] 원인 재현(옛 코드)", f"{type(e).__name__} {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
