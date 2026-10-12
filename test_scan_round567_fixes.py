# -*- coding: utf-8 -*-
"""스캔 567라운드 회귀 — 정산 되돌리기(api_settlement_undo, POST
   /api/settlements/<sid>/undo)만 형제 6곳(review·paid·paid-bulk·transfer·
   insurer_approve·void 자신)과 달리 void_status=='취소' 를 스스로 다시
   보지 않던 결함.

   조사 각도 — "정산 상태를 진짜로 바꾸는 라우트들이 전부 같은 겹방어를
   갖추고 있는가"를 이 세션이 직접 조사(하위위임 없음)했다. 정산의 값을
   바꾸는 UPDATE 문을 app.py 전수(grep 'UPDATE settlements SET')로 훑으니
   7곳이 나온다 — void(14358행)·paid(13638)·paid-bulk(13677)·
   review(14561)·transfer(그 옆)·insurer_approve(3591)·undo(14444).
   앞의 6곳은 전부 "if (s['void_status'] or '') == '취소': ... 409" 를
   갖추고 있고, 그중 review·transfer·insurer_approve 는 각자 라운드427·465
   에서 "그 보장은 이 함수가 아니라 다른 라우트가 지키는 것이라 새 경로가
   하나라도 추가되면 조용히 뚫릴 수 있다"는 같은 이유로 명시적으로 겹방어를
   이식받았다(형제가 이미 서로를 못 믿고 각자 방어하기로 한 원칙). 그런데
   유독 undo() 만 이 가드가 없었다.

   지금 이 순간의 실제 위험도(과장하지 않는다) — api_settlement_void() 는
   review_status=='승인' 이거나 insurer_paid=='입금완료' 인 정산은애초에
   취소할 수 없게 막아 두므로(그 값을 먼저 undo 로 내려야 취소가 열린다),
   정상 흐름에서는 "취소됐는데 review_status 가 아직 '승인'으로 남아있는"
   조합 자체가 생기지 않는다 — 그래서 오늘 이 순간에는 undo() 를 취소된
   건에 불러도 review_status/insurer_paid 분기 둘 다 거짓이라 그냥 "되돌릴
   단계가 없습니다"(409)로 끝나 실제 피해는 없다. 이 라운드가 고치는 것은
   "다른 함수의 가드에만 기대지 말라"는 이 정산 서브시스템 자신의 반복된
   원칙(427·465)을 마지막 한 곳까지 완성하는 것이다 — 아래 [3]은 그 가드가
   실제로 막아 주는 시나리오(다른 원인으로 void_status='취소' 이면서
   review_status='승인' 인 행이 생겼을 때)를 직접 만들어, 고치기 전 코드는
   그 행을 그대로 "되돌려 살려內"버리고 고친 코드는 막는다는 것을 실측으로
   증명한다.

   고침 — app.py: api_settlement_undo() 에서 transfer_status=='이체완료'
   검사 바로 앞에 void_status 가드를 추가했다(형제와 같은 문구·같은 409).

   테스트 기법 — on-disk app.py 는 조회만 한다. "되돌리기" 증명은 이 세션이
   고치기 **직전** Read 로 확인한 원문(void_status 가드 없는 버전)을
   문자열로 재구성해 exec() 한 것이며, 실제 파일에는 절대 쓰지 않는다
   (round543/547/549/550/553/566 과 같은 기법). void_status='취소' +
   review_status='승인' 조합은 지금 라우트 어디로도 정상 도달할 수 없으므로,
   그 행을 스크래치 DB에 직접 INSERT 해 가드 자체만 분리해 검증한다
   (동시성 재현이 아니라 상태-가드 단위 검증).

      python test_scan_round567_fixes.py
"""
import io
import os
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


print("=" * 72)
print("  스캔 567라운드 회귀 — 정산 되돌리기(api_settlement_undo) void_status 가드 누락")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — 고친 지점이 실제로 app.py 에 있는가"
      "(동시편집 세션이 되돌렸다면 여기서부터 정직하게 실패해야 한다)")
# ------------------------------------------------------------------
try:
    import ast as _ast
    chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

    _start = APP_SRC.index('@app.post("/api/settlements/<int:sid>/undo")')
    _end_marker = "을(를) 되돌렸습니다.\"})\n"
    _end = APP_SRC.index(_end_marker, _start) + len(_end_marker)
    fn_body = APP_SRC[_start:_end]
    chk("def api_settlement_undo" in fn_body,
        "STEP api_settlement_undo() 함수 본문을 추출했다")
    chk(fn_body.count("if (s[\"void_status\"] or \"\") == \"취소\":") == 1,
        "★★★★★ api_settlement_undo() 안에 void_status 가드가 있다(고치기 전엔 없었다)")
    _i_void = fn_body.index('if (s["void_status"] or "") == "취소":')
    _i_transfer = fn_body.index('if s["transfer_status"] == "이체완료":')
    _i_review = fn_body.index('if s["review_status"] == "승인":')
    chk(_i_void < _i_transfer < _i_review,
        "STEP void_status 가드가 transfer_status 검사보다, 그것이 review_status 분기보다 앞이다"
        "(막는 자리가 실제 분기보다 먼저 실행된다)")
    chk('if undo_key and s["last_undo_key"] == undo_key:' in fn_body,
        "  회귀 방지: 라운드228의 재시도(idempotent) 방어는 그대로 남아 있다")
    chk('if s["transfer_status"] == "이체완료":' in fn_body,
        "  회귀 방지: 이체완료 건 되돌리기 금지 가드도 그대로 남아 있다")

    # 형제 6곳도 이미 같은 가드를 갖고 있는지 대조(이번 라운드가 그중 하나를
    # 실수로 지우지 않았는지 확인 겸, 결함 설명의 '7곳 중 1곳만 없었다'를 실측)
    _siblings = [
        ('def api_settlement_void(sid):', '@app.post("/api/settlements/<int:sid>/void")'),
        ('def api_settlement_review(sid):', '@app.post("/api/settlements/<int:sid>/review")'),
        ('def api_settlement_paid(sid):', '@app.post("/api/settlements/<int:sid>/paid")'),
        ('def api_settlements_paid_bulk():', '@app.post("/api/settlements/paid-bulk")'),
        ('def api_insurer_settlement_approve(sid):',
         '@app.post("/api/insurer/settlements/<int:sid>/approve")'),
    ]
    _n_guarded = 0
    for fn_sig, route_decorator in _siblings:
        _s0 = APP_SRC.index(route_decorator)
        _s1 = APP_SRC.index("\n@app.", _s0 + 1)
        sib = APP_SRC[_s0:_s1]
        if "void_status" in sib and "취소" in sib:
            _n_guarded += 1
    chk(_n_guarded == len(_siblings),
        f"STEP 형제 {len(_siblings)}곳 전부 void_status 가드를 이미 갖고 있다"
        "(이번 라운드가 손대지 않았고, 그대로 남아 있다)", _n_guarded)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드567 [0] 소스 확인", f"{type(e).__name__} {e}")


# ==================================================================
print("\n[1] 준비 — 격리 스크래치 DB · 관리자 세션")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round567_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r567-csrf"
A = DB = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin567','x','실행계정567','최고관리자')")
    conn0.commit(); conn0.close()
    chk(True, "STEP 스크래치 DB·관리자 계정 준비 완료")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드567 [1] 준비", f"{type(e).__name__} {e}")


def mkcase(case_no):
    c = DB.get_db()
    c.execute(
        "INSERT INTO cases(case_no, insurer, category, region, address, status, "
        "est_price, low_price, created_at) VALUES(?,?,?,?,?,?,?,?,?)",
        (case_no, "테스트보험", "가드레일", "서울", "테스트로 1", "정산진행",
         1000000, 900000, DB.now()))
    c.commit()
    cid = c.execute("SELECT id FROM cases WHERE case_no=?", (case_no,)).fetchone()["id"]
    c.close()
    return cid


def mksettlement(case_id, case_no, *, void_status=None, review_status="대기",
                  insurer_paid="대기", transfer_status="대기"):
    """void_status='취소' + review_status='승인' 조합처럼 정상 라우트로는 도달할 수
    없는 상태를, 가드 자체만 떼어 검증하기 위해 스크래치 DB에 직접 심는다."""
    c = DB.get_db()
    c.execute(
        """INSERT INTO settlements(case_id, case_no, insurer, partner_id, partner_name,
               amount, fee, payout, insurer_paid, review_status, transfer_status,
               void_status, void_reason, void_by, void_at, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_id, case_no, "테스트보험", 1, "테스트업체",
         900000, 90000, 810000, insurer_paid, review_status, transfer_status,
         void_status, ("결함 재현용 취소" if void_status else None),
         ("admin567" if void_status else None),
         (DB.now() if void_status else None), DB.now()))
    c.commit()
    sid = c.execute("SELECT id FROM settlements WHERE case_id=?", (case_id,)).fetchone()["id"]
    c.close()
    return sid


def _call(fn, sid, payload):
    with A.app.test_request_context(f"/api/settlements/{sid}/undo", method="POST", json=payload):
        from flask import session as _s
        _s["admin"] = "admin567"
        _s["admin_name"] = "실행계정567"
        _s["admin_role"] = "최고관리자"
        _s["_csrf"] = CSRF
        resp = fn(sid)
    if isinstance(resp, tuple):
        resp_obj, code = resp[0], resp[1]
    else:
        resp_obj, code = resp, 200
    return code, resp_obj.get_json()


def _settlement_row(sid):
    c = DB.get_db()
    r = c.execute("SELECT * FROM settlements WHERE id=?", (sid,)).fetchone()
    c.close()
    return dict(r) if r else None


# ==================================================================
print("\n[2] 지금 코드 — 취소된 정산은 되돌리기가 막는가")
# ------------------------------------------------------------------
try:
    cid2 = mkcase("R567-VOID-NEW")
    #  void_status='취소' 이면서 review_status='승인' 인, 정상 라우트로는 못 만드는
    #  조합을 직접 심는다 — "다른 함수의 가드가 이미 이 조합을 막아 준다"에
    #  기대지 않고 이 함수 자신의 가드만 떼어 검증한다.
    sid2 = mksettlement(cid2, "R567-VOID-NEW", void_status="취소", review_status="승인",
                        insurer_paid="입금완료", transfer_status="대기")
    before2 = _settlement_row(sid2)

    code2, body2 = _call(A.api_settlement_undo, sid2, {"reason": "테스트 사유 5자이상"})
    chk(code2 == 409, "STEP 지금 코드: 취소된 정산의 되돌리기는 409로 막힌다", (code2, body2))
    chk(body2.get("ok") is False and body2.get("error") == "취소된 정산 건입니다.",
        "★★★★★ 지금 코드: 형제와 같은 문구('취소된 정산 건입니다.')로 막는다", body2)

    after2 = _settlement_row(sid2)
    chk(after2 == before2,
        "★★★★★ 지금 코드: 취소된 정산 행이 전혀 바뀌지 않았다(review_status='승인' 그대로)",
        {"before": before2, "after": after2})
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드567 [2] 지금 코드", f"{type(e).__name__}: {e}")


# ==================================================================
print("\n[3] 되돌리기 증명 — 옛(void_status 가드 없는) 버전을 문자열로 재구성해 exec()")
# ------------------------------------------------------------------
#  ⚠ on-disk app.py 는 절대 건드리지 않는다. 이 세션이 고치기 **직전** Read 로
#    확인한 원문 그대로를 옮긴 것이다.
_PRE567_SRC = '''
def _api_settlement_undo_pre567(sid):
    d = body()
    reason = (d.get("reason") or "").strip()
    if len(reason) < 5:
        return jsonify({"ok": False, "error": "되돌리는 사유를 5자 이상 남겨 주세요."}), 400
    undo_key = (str(d.get("undo_key") or "")).strip()[:80] or None

    conn = DB.get_db()
    conn.execute("BEGIN IMMEDIATE")
    s = one(conn.execute("SELECT * FROM settlements WHERE id=?", (sid,)))
    if not s:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "정산 건을 찾을 수 없습니다."}), 404

    if undo_key and s["last_undo_key"] == undo_key:
        conn.rollback(); conn.close()
        return jsonify({"ok": True, "duplicate": True,
                        "message": "방금 같은 요청을 이미 처리했습니다."})

    if s["transfer_status"] == "이체완료":
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "code": "ALREADY_TRANSFERRED",
                        "error": "이미 이체가 나간 건은 되돌릴 수 없습니다. "
                                 "실제 입금이 끝났으므로 반환 협의로 처리해 주세요."}), 409

    if s["review_status"] == "승인":
        conn.execute("UPDATE settlements SET review_status='대기', transfer_status='대기', "
                     "last_undo_key=? WHERE id=?", (undo_key, sid))
        step = "지급 검수 승인"
    elif s["insurer_paid"] == "입금완료":
        conn.execute("UPDATE settlements SET insurer_paid='대기', last_undo_key=? WHERE id=?",
                     (undo_key, sid))
        step = "보험사 입금 확인"
    else:
        conn.rollback(); conn.close()
        return jsonify({"ok": False, "error": "되돌릴 단계가 없습니다. (아직 아무 단계도 진행되지 않음)"}), 409

    DB.log(conn, actor(), "정산 되돌림", f"{s['case_no']} {step} 취소 — 사유: {reason[:60]}")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "undone": step,
                    "message": f"'{step}'을(를) 되돌렸습니다."})
'''
try:
    chk("void_status" not in _PRE567_SRC, "STEP 재구성한 옛 원문에는 void_status 가드가 없다(대조군)")
    _ns = dict(vars(A))          # app 모듈 네임스페이스 복사(진짜 모듈은 안 건드림)
    exec(compile(_PRE567_SRC, "<round567_pre_reconstructed>", "exec"), _ns)
    old_fn = _ns["_api_settlement_undo_pre567"]

    cid3 = mkcase("R567-VOID-OLD")
    sid3 = mksettlement(cid3, "R567-VOID-OLD", void_status="취소", review_status="승인",
                        insurer_paid="입금완료", transfer_status="대기")
    before3 = _settlement_row(sid3)

    code3, body3 = _call(old_fn, sid3, {"reason": "테스트 사유 5자이상"})
    chk(code3 == 200 and body3.get("ok") is True,
        "★★★★★ 옛 코드(재구성): 취소된 정산인데도 200 성공으로 '되돌렸다'고 응답한다"
        "(지금 코드는 위 [2]에서 409로 막았다)", (code3, body3))

    after3 = _settlement_row(sid3)
    chk(after3 is not None and after3["review_status"] == "대기"
        and after3["transfer_status"] == "대기",
        "★★★★★ 옛 코드(재구성): 취소된 정산의 review_status·transfer_status 가 실제로"
        " '대기'로 되돌려졌다 — 취소된 건이 검수·이체 파이프라인으로 조용히 복귀한다"
        "(결함이 실재했음을 실측으로 증명 — 이 차이가 이 회귀테스트의 인과관계 증명이다)",
        {"before": before3, "after": after3})
    chk(after3["void_status"] == "취소",
        "  참고: void_status 자체는 옛 코드도 안 건드린다(그래서 화면 목록에서는 여전히"
        " '취소'로 보이면서도, 내부 상태만 검수승인으로 되돌아가는 눈에 덜 띄는 형태의 결함)",
        after3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드567 [3] 되돌리기 증명", f"{type(e).__name__}: {e}")


# ==================================================================
print("\n[4] 순차 회귀 안전 — 취소되지 않은 정상 건의 되돌리기는 그대로 동작하는가")
# ------------------------------------------------------------------
try:
    cid4 = mkcase("R567-NORMAL")
    sid4 = mksettlement(cid4, "R567-NORMAL", void_status=None, review_status="승인",
                        insurer_paid="입금완료", transfer_status="이체예약")
    code4, body4 = _call(A.api_settlement_undo, sid4, {"reason": "정상 되돌리기 테스트"})
    chk(code4 == 200 and body4.get("ok") is True and body4.get("undone") == "지급 검수 승인",
        "STEP 지금 코드: 취소되지 않은 정상 건은 예전처럼 검수 승인을 되돌린다(회귀 없음)",
        (code4, body4))
    after4 = _settlement_row(sid4)
    chk(after4["review_status"] == "대기" and after4["transfer_status"] == "대기",
        "STEP 정상 건의 되돌리기는 review_status·transfer_status 를 실제로 '대기'로 내렸다",
        after4)

    # 이미 취소 처리된 건이 없는(void_status IS NULL) 그다음 되돌릴 단계 없음 케이스도 확인
    cid5 = mkcase("R567-NOSTEP")
    sid5 = mksettlement(cid5, "R567-NOSTEP", void_status=None)
    code5, body5 = _call(A.api_settlement_undo, sid5, {"reason": "되돌릴 단계 없음 테스트"})
    chk(code5 == 409 and "되돌릴 단계가 없습니다" in (body5.get("error") or ""),
        "STEP 지금 코드: 취소되지 않았고 아무 단계도 안 밟은 건은 여전히"
        " '되돌릴 단계가 없습니다'로 막힌다(회귀 없음)", (code5, body5))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드567 [4] 순차 회귀 안전", f"{type(e).__name__}: {e}")


# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
