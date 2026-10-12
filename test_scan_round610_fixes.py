# -*- coding: utf-8 -*-
"""스캔 610라운드 회귀 — 옵션A(새 결함각도), api_boq_update(표준내역 단가수정).

   조사 배경 — 시작 전 wc -l app.py가 직전 라운드(609) 종료시점과 정확히
   22147줄로 일치해 동시편집은 없었다(재기동 직후 프로세스 시각도 app.py
   mtime과 일치해 교차확인 완료).

   지시문이 예시로 든 "api_partner_update의 본문에 키가 있으면 무조건
   SET"(round561이 지목)는 직접 Read로 재확인한 결과 round562가 이미
   pending/diff 패턴(8843행 부근, "if v == (full[f] or ''): continue")으로
   닫아 둔 상태였다 — 지시문 예시가 낡았을 뿐 실제로는 기해결(추가조치
   불필요, 아래 [0]에서 소스로 재확인).

   같은 "화면이 폼 전체를 통째로 재전송 → 안 바뀐 값도 무조건 SET+감사로그"
   결함군(round240/299/429/493/504/543/544/549/561/562/570이 partner·
   insurer·contact·defect·admin 등 형제 함수들에서 이미 닫은 부류)을 아직
   훑지 않은 나머지 api_*_update 함수들에 대해 재점검한 결과, api_boq_update
   (17037행 부근)에서 미해결 실인스턴스 2개를 새로 찾았다(화면 admin.js
   boqSave()가 spec/unit/ref_price/price_src/price_date 5칸을 매번 통째로
   재전송 — boqEdit()가 현재값을 그대로 프리필함):

   ① [기존에 알려진 부류와 동일] 아무 값도 안 바꾸고 "저장"만 눌러도
      UPDATE·boq_price_history 개정이력·감사로그가 매번 새로 쌓였다.
      이 이력은 api_boq_history 자신의 주석대로 "이 견적이 어느 단가로
      계산됐나"를 되짚는 근거라, 가짜 "수정"(old_price==new_price) 행이
      쌓이면 실제 단가 변경 시점을 가려낼 수 없게 된다. 실측: 같은 값으로
      2회 저장 → history 2행·감사로그 2행(둘 다 "50,000 → 50,000원").

   ② [이 라운드 자체발견, ①보다 심각] 참고단가 입력칸을 지우고 저장하면
      admin.js의 digits() 헬퍼가 빈 문자열("")을 보낸다. parse_money(...,
      required=False)는 "미입력"과 "빈 문자열"을 구분하지 못해 둘 다
      (0, None)을 돌려주므로, 기존의 "ref_price" in d 만 보는 판정은 이를
      "0원으로 명시적으로 바꾼다"로 오판했다. 실측: 50,000원짜리 항목이
      가격칸만 지우고 저장한 한 번으로 에러도 확인창도 없이 조용히 0원이
      됐다(200 OK). 이 표는 admin.js 자신의 설명대로 "입찰 비교의 기준"이고
      자동견적 엔진(RE.SKU)의 참고값이라, 말없는 0원화는 입찰 비교·자동견적
      전체를 왜곡할 수 있다.

   수정(app.py 17051~17102행 부근, api_boq_update 안에서만) — 새 헬퍼 없이
   기존 관례만 재사용:
     · _price_sent = "ref_price" in d and _s(d.get("ref_price")) != "" —
       빈 문자열은 "값을 안 줬다"로 취급해 기존 값을 지킨다("0"을 명시적으로
       입력하면 그 경로는 그대로 열려 있다 — 의도적 0원 기록은 막지 않음).
     · vals 계산 직후, cur_row와 vals(5개 필드)를 전부 대조해 하나라도
       실제로 달라야만 UPDATE·_boq_history·DB.log를 실행한다(형제
       api_partner_update round562/api_contact_update round570/
       api_defect_update round549와 동일한 "changed" 게이트, 다만 여기는
       컬럼이 5개뿐이라 별도 sets/vals 리스트 대신 dict 전체비교로 처리).

   [0]은 소스 확인, [1]은 스크래치DB에 관리자 1명+표준내역 2건(일반 1건+
   자동견적 엔진 연결 1건), [2]는 두 결함이 실제로 닫혔음을 실행으로 확인,
   [3]은 정상 경로 회귀 없음(실제 가격변경·명시적 "0"·NEED_SRC·
   SKU_UNIT_MISMATCH·404 전부 그대로), [4]는 되돌림-증명 — 진짜 app.py
   파일은 전혀 안 건드리고 A.app.view_functions["api_boq_update"] 딕셔너리
   항목만 610 이전 버전(순수 파이썬 클로저, A.* 로 공유 헬퍼만 참조)으로
   임시 치환해 ①·② 둘 다 실제로 재현됨을 보인 뒤 원복(app.py 해시 불변도
   확인, 원복 후 정상 동작도 재확인).

       python test_scan_round610_fixes.py
"""
import hashlib
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
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


def _code_only(body):
    """주석 줄(이번 수정 설명 안에 옛 raw 패턴 문자열이 그대로 인용돼 있어,
       주석까지 검색하면 '옛 패턴이 아직 있다'는 오탐이 난다)을 빼고
       실제 코드 줄만 이어붙인다."""
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


print("=" * 72)
print("  스캔 610라운드 회귀 — api_boq_update 무변경저장 이력·로그 스팸 +")
print("  참고단가 빈칸저장 조용한 0원화, 2개 실결함")
print("=" * 72)

APP_SRC = read("app.py")

# ==================================================================
print("\n[0] 소스 확인 — round561 예시(api_partner_update)는 이미 round562가 "
      "닫았고, api_boq_update에 새 가드 2개가 들어갔다")
# ------------------------------------------------------------------
try:
    apu = _code_only(_py_fn_body(APP_SRC, "api_partner_update"))
    chk('pending[f] = v' in apu and 'if v == (full[f] or ""):' in apu,
        "★★★★★ api_partner_update — round561이 지목한 '무조건 SET'은 "
        "round562가 이미 pending/diff 패턴으로 닫아둠(재확인, 추가조치 불필요)")

    abu = _code_only(_py_fn_body(APP_SRC, "api_boq_update"))
    chk('_price_sent = "ref_price" in d and _s(d.get("ref_price")) != ""' in abu,
        "★★★★★ api_boq_update — ref_price 빈 문자열을 '미입력'으로 구분하는 "
        "_price_sent 가드 신설")
    chk('"ref_price": new_price if _price_sent else cur_row.get("ref_price"),' in abu,
        "★★★★★ api_boq_update — vals[ref_price]가 _price_sent를 쓰도록 변경 "
        "(예전엔 \"ref_price\" in d 만 봤다)")
    chk("_unchanged = (" in abu and 'return jsonify({"ok": True, "unchanged": True})' in abu,
        "★★★★★ api_boq_update — 5개 필드 전체비교 unchanged 가드 신설")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드610 [0] 소스 확인", f"{type(e).__name__} {e}")

APP_HASH_BEFORE = hashlib.sha256(APP_SRC.encode("utf-8")).hexdigest()

# ==================================================================
print("\n[1] 준비 — 스크래치 DB, 관리자(최고관리자) 1명 + 표준내역 2건")
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round610_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "bokguon.log")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r610-csrf"
H = {"X-CSRF-Token": CSRF}
A = DB = None
boq_id = boq_sku_id = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r610admin','x','검증','최고관리자')")
    boq_id = conn0.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price,price_src,price_date) "
        "VALUES('금속','가드레일','표준형','m',50000,'조달청 2025','2025-01')").lastrowid
    #  자동견적 엔진(RE.SKU)에 연결된 항목 — SKU_UNIT_MISMATCH 관문 회귀용
    boq_sku_id = conn0.execute(
        "INSERT INTO standard_boq(major,item,spec,unit,ref_price,price_src,price_date,sku_key) "
        "VALUES('금속','가드레일 판(2W)','4t×350×4330','개',110000,"
        "'건자재114 2026-04 자재비','2026-04','gr_panel')").lastrowid
    conn0.commit()
    conn0.close()
    chk(bool(boq_id) and bool(boq_sku_id),
        "STEP 관리자·표준내역 2건 픽스처 생성", dict(boq_id=boq_id, boq_sku_id=boq_sku_id))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드610 [1] 준비", f"{type(e).__name__} {e}")


def _admin_client():
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "r610admin"; sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"; sess["_csrf"] = CSRF
    return c


def _patch(path, **kw):
    return _admin_client().patch(path, headers=H, **kw)


def _hist_and_log(bid=None):
    bid = boq_id if bid is None else bid
    conn = DB.get_db()
    row = dict(conn.execute("SELECT * FROM standard_boq WHERE id=?", (bid,)).fetchone())
    hist = conn.execute("SELECT old_price, new_price FROM boq_price_history "
                         "WHERE boq_id=? ORDER BY id", (bid,)).fetchall()
    logs = conn.execute("SELECT detail FROM activity_log WHERE action='표준내역 단가수정' "
                         "ORDER BY id").fetchall()
    conn.close()
    return row, hist, logs


FULL_BODY = {"spec": "표준형", "unit": "m", "ref_price": "50000",
             "price_src": "조달청 2025", "price_date": "2025-01"}

# ==================================================================
print("\n[2] 실행 — 두 결함이 실제로 닫혔다")
# ------------------------------------------------------------------
try:
    r1 = _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
    rb1 = r1.get_json() or {}
    r2 = _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
    rb2 = r2.get_json() or {}
    row, hist, logs = _hist_and_log()
    chk(r1.status_code == 200 and rb1.get("unchanged") is True
        and r2.status_code == 200 and rb2.get("unchanged") is True,
        "★★★★★ ① 무변경 저장 2회 모두 unchanged:true", (rb1, rb2))
    chk(len(hist) == 0 and len(logs) == 0,
        "★★★★★ ① 무변경 저장이 boq_price_history·감사로그를 전혀 안 남김",
        (len(hist), len(logs)))
    chk(row["ref_price"] == 50000,
        "★★★★★ ① 무변경 저장 후에도 참고단가가 그대로 50,000원", row["ref_price"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2]-① 무변경 저장", f"{type(e).__name__} {e}")

try:
    body_blank = dict(FULL_BODY, ref_price="")
    r3 = _patch(f"/api/boq/{boq_id}", json=body_blank)
    rb3 = r3.get_json() or {}
    row, hist, logs = _hist_and_log()
    chk(r3.status_code == 200 and rb3.get("unchanged") is True,
        "★★★★★ ② 참고단가 칸을 비우고 저장해도 unchanged:true(다른 4칸은 "
        "그대로라 실제 변경 없음)", rb3)
    chk(row["ref_price"] == 50000,
        "★★★★★ ② 참고단가가 조용히 0원이 되지 않고 기존 50,000원 그대로 보존",
        row["ref_price"])
    chk(len(hist) == 0 and len(logs) == 0,
        "★★★★★ ② 빈칸 저장도 가짜 개정이력을 안 남김", (len(hist), len(logs)))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2]-② 빈칸 저장", f"{type(e).__name__} {e}")

try:
    #  다른 필드(규격)만 실제로 바꾸면서 가격칸은 비워 보낸 경우 — "빈칸=미입력"
    #  가드가 ref_price만 보호하고 spec 변경 자체는 정상 반영되는지 확인.
    body_mixed = dict(FULL_BODY, spec="개선형", ref_price="")
    r3b = _patch(f"/api/boq/{boq_id}", json=body_mixed)
    rb3b = r3b.get_json() or {}
    row, hist, logs = _hist_and_log()
    chk(r3b.status_code == 200 and not rb3b.get("unchanged"),
        "★★★★★ ②-보조 spec만 실제로 바뀌면 unchanged가 아니라 정상 저장", rb3b)
    chk(row["spec"] == "개선형" and row["ref_price"] == 50000,
        "★★★★★ ②-보조 spec은 반영되고 ref_price는 빈칸이라 여전히 보존",
        (row["spec"], row["ref_price"]))
    chk(len(hist) == 1 and hist[0]["old_price"] == 50000 and hist[0]["new_price"] == 50000,
        "★★★★★ ②-보조 실제 변경 1건만 이력에 남고 가격은 동일값으로 정직하게 기록",
        [dict(h) for h in hist])
    #  다음 절 전제와 맞추려고 spec을 원래대로 되돌려 둔다(정상 변경 경로 재사용, 이력 1건 추가는 의도된 부작용)
    _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [2]-②보조 혼합 변경", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 회귀 없음 — 정상 경로·기존 관문들은 그대로 동작한다")
# ------------------------------------------------------------------
try:
    row0, hist0, logs0 = _hist_and_log()
    n_hist0 = len(hist0)
    body_real = dict(FULL_BODY, ref_price="60000")
    r4 = _patch(f"/api/boq/{boq_id}", json=body_real)
    rb4 = r4.get_json() or {}
    row, hist, logs = _hist_and_log()
    chk(r4.status_code == 200 and rb4.get("ok") is True and not rb4.get("unchanged"),
        "★★★★★ 실제 가격변경(50000→60000)은 여전히 정상 200", rb4)
    chk(row["ref_price"] == 60000,
        "★★★★★ 실제 가격변경이 정확히 반영됨", row["ref_price"])
    chk(len(hist) == n_hist0 + 1 and hist[-1]["old_price"] == 50000
        and hist[-1]["new_price"] == 60000,
        "★★★★★ 이력이 정확히 1건만 추가되고 old/new가 정확함", dict(hist[-1]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 실제 가격변경 회귀", f"{type(e).__name__} {e}")

try:
    row0, hist0, logs0 = _hist_and_log()
    n_hist0 = len(hist0)
    body_zero = dict(FULL_BODY, ref_price="0")
    r5 = _patch(f"/api/boq/{boq_id}", json=body_zero)
    rb5 = r5.get_json() or {}
    row, hist, logs = _hist_and_log()
    chk(r5.status_code == 200 and rb5.get("ok") is True,
        "★★★★★ 명시적 '0' 입력은 여전히 허용됨(빈칸과 구분)", rb5)
    chk(row["ref_price"] == 0 and len(hist) == n_hist0 + 1,
        "★★★★★ 명시적 0원 기록이 정상 반영되고 이력도 정확히 1건 추가",
        (row["ref_price"], len(hist) - n_hist0))
    #  되돌리기 — 이후 절 전제(참고단가 50000)를 맞춘다
    _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 명시적 0원 회귀", f"{type(e).__name__} {e}")

try:
    #  근거(price_src) 없이 새 가격만 올리면 여전히 NEED_SRC로 막혀야 한다
    body_needsrc = {"spec": "표준형", "unit": "m", "ref_price": "77000",
                    "price_src": "", "price_date": ""}
    r6 = _patch(f"/api/boq/{boq_id}", json=body_needsrc)
    rb6 = r6.get_json() or {}
    chk(r6.status_code == 400 and rb6.get("code") == "NEED_SRC",
        "★★★★★ NEED_SRC 관문(근거 없이 단가만 올리면 400) 회귀 없음", (r6.status_code, rb6))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] NEED_SRC 관문 회귀", f"{type(e).__name__} {e}")

try:
    #  자동견적 엔진 연결 항목의 단위를 SKU 기본단위와 다르게 바꾸면 여전히 막혀야 한다
    body_skumismatch = {"spec": "4t×350×4330", "unit": "m", "ref_price": "110000",
                         "price_src": "건자재114 2026-04 자재비", "price_date": "2026-04"}
    r7 = _patch(f"/api/boq/{boq_sku_id}", json=body_skumismatch)
    rb7 = r7.get_json() or {}
    chk(r7.status_code == 400 and rb7.get("code") == "SKU_UNIT_MISMATCH",
        "★★★★★ SKU_UNIT_MISMATCH 관문(엔진 연결 항목 단위변경 차단) 회귀 없음",
        (r7.status_code, rb7))
    row_sku, _, _ = _hist_and_log(boq_sku_id)
    chk(row_sku["unit"] == "개",
        "★★★★★ 차단됐으니 단위가 실제로도 안 바뀜(원래값 '개' 유지)", row_sku["unit"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] SKU_UNIT_MISMATCH 관문 회귀", f"{type(e).__name__} {e}")

try:
    r8 = _patch("/api/boq/999999", json=FULL_BODY)
    chk(r8.status_code == 404,
        "★★★★★ 없는 항목 id는 여전히 404", r8.status_code)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ [3] 404 회귀", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 되돌리기 — 610 이전 동작이었다면 이 테스트가 실제로 잡아내는가")
# ------------------------------------------------------------------
try:
    if A is None:
        raise RuntimeError("1단계가 실패해 app 모듈이 없음 — 되돌리기 건너뜀")

    _orig_view = A.app.view_functions["api_boq_update"]

    def _old_broken_boq_update(bid):
        """610라운드 이전 동작 재현(①·② 둘 다) — 디스크의 app.py 는 전혀
        안 건드리고, 공유 이름(A.body·A.DB 등)만 참조하는 순수 함수를 이
        함수 호출 동안만 view_functions 항목에 임시로 걸어 둔다."""
        d = A.body()
        conn = A.DB.get_db()
        conn.execute("BEGIN IMMEDIATE")
        try:
            cur_row = A.one(conn.execute("SELECT * FROM standard_boq WHERE id=?", (bid,)))
            if not cur_row:
                conn.rollback()
                return A.jsonify({"ok": False, "error": "없는 항목입니다."}), 404
            new_price, err = A.parse_money(d.get("ref_price"), "참고단가", required=False)
            if err:
                conn.rollback()
                return A.jsonify({"ok": False, "error": err}), 400
            src = A._s(d.get("price_src") if "price_src" in d else cur_row.get("price_src"))
            if new_price and not src.strip():
                conn.rollback()
                return A.jsonify({"ok": False, "code": "NEED_SRC",
                                   "error": "단가에는 근거(출처)가 있어야 합니다."}), 400
            vals = {
                "spec": d.get("spec", cur_row.get("spec")),
                "unit": d.get("unit", cur_row.get("unit")),
                "ref_price": new_price if "ref_price" in d else cur_row.get("ref_price"),
                "price_src": src.strip()[:200],
                "price_date": A._s(d.get("price_date") if "price_date" in d
                                    else cur_row.get("price_date"), 20),
            }
            conn.execute(
                "UPDATE standard_boq SET spec=?, unit=?, ref_price=?, price_src=?, price_date=?, "
                "                        updated_at=? WHERE id=?",
                (vals["spec"], vals["unit"], vals["ref_price"], vals["price_src"],
                 vals["price_date"], A.DB.now(), bid))
            A._boq_history(conn, bid, {**dict(cur_row), **vals}, action="수정",
                            old_price=cur_row.get("ref_price"))
            A.DB.log(conn, A.actor(), "표준내역 단가수정",
                     f"{cur_row['major']}·{cur_row['item']} "
                     f"{int(cur_row.get('ref_price') or 0):,} → "
                     f"{int(vals['ref_price'] or 0):,}원")
            conn.commit()
            return A.jsonify({"ok": True})
        finally:
            conn.close()

    A.app.view_functions["api_boq_update"] = _old_broken_boq_update
    try:
        row_before, hist_before, logs_before = _hist_and_log()
        n_hist_before = len(hist_before)

        r_old1 = _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
        r_old2 = _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
        row_o, hist_o, logs_o = _hist_and_log()
        chk(r_old1.status_code == 200 and r_old2.status_code == 200
            and len(hist_o) == n_hist_before + 2,
            "★★★★★ 옛 동작으로 되돌리면 무변경 저장 2회가 실제로 이력 2건을 "
            "새로 쌓는다 — 이 테스트가 실제로 결함①을 잡아낸다는 증거",
            (len(hist_o) - n_hist_before))

        r_old3 = _patch(f"/api/boq/{boq_id}", json=dict(FULL_BODY, ref_price=""))
        row_o2, hist_o2, logs_o2 = _hist_and_log()
        chk(r_old3.status_code == 200 and row_o2["ref_price"] == 0,
            "★★★★★ 옛 동작으로 되돌리면 가격칸을 비운 저장이 실제로 참고단가를 "
            "0원으로 조용히 떨어뜨린다 — 이 테스트가 실제로 결함②를 잡아낸다는 증거",
            row_o2["ref_price"])
    finally:
        A.app.view_functions["api_boq_update"] = _orig_view

    #  원복 후 같은 요청들이 다시 정상(①은 unchanged, ②는 가격 보존)으로 돌아오는지
    _patch(f"/api/boq/{boq_id}", json=FULL_BODY)   # 가격을 50000으로 재고정
    r_restored1 = _patch(f"/api/boq/{boq_id}", json=FULL_BODY)
    rb_restored1 = r_restored1.get_json() or {}
    r_restored2 = _patch(f"/api/boq/{boq_id}", json=dict(FULL_BODY, ref_price=""))
    rb_restored2 = r_restored2.get_json() or {}
    row_r, hist_r, logs_r = _hist_and_log()
    chk(rb_restored1.get("unchanged") is True and rb_restored2.get("unchanged") is True,
        "★★★★ 원복 후에는 무변경·빈칸 저장 둘 다 다시 unchanged:true로 돌아온다"
        "(바꿔치기가 안 샜다)", (rb_restored1, rb_restored2))
    chk(row_r["ref_price"] == 50000,
        "★★★★ 원복 후 참고단가도 50,000원 그대로", row_r["ref_price"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 라운드610 [4] 되돌리기", f"{type(e).__name__} {e}")

APP_HASH_AFTER = hashlib.sha256(read("app.py").encode("utf-8")).hexdigest()
chk(APP_HASH_AFTER == APP_HASH_BEFORE,
    "★★★★★ 되돌리기 절차 동안 app.py 파일 내용이 전혀 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

# ==================================================================
# 정리
# ------------------------------------------------------------------
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
os.environ.pop("BOKGUON_LOG_FILE", None)
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
