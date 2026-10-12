# -*- coding: utf-8 -*-
"""B5 검증 — 가견적 정합성 점검.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

이 기능의 가장 위험한 실패는 **판정이 없는데 '이상 없음'으로 보이는 것**이다.
그래서 '판정없음'이 정상으로 분류되지 않는지를 최우선으로 검사한다.

AI 키가 없어도 전부 검증된다 — 점검 함수가 순수 함수이고,
파손 정도는 담당자가 직접 정할 수 있게 만들었기 때문이다.
"""
import sys
import json
import secrets
import urllib.request
import urllib.error
import http.cookiejar

import db as DB
import os
# [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import app as A

#  ⚠⚠ 기본값은 **검증 서버(8799)** 다. 여기만 8771(운영)로 박혀 있었고, 환경변수도
#    읽지 않아 배터리를 돌릴 때마다 **운영 로그인**을 두드렸다. 비밀번호까지
#    옛 값이 박혀 있어 매번 401 — 운영 감사로그에 로그인 실패가 383건 쌓였고,
#    계정 잠금(5회)이 걸린 서버라 실운영 중 잠길 수 있었다.
#    형제 테스트들은 전부 8799 인데 이 파일만 빠져 있었다.
BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")


def _cred(env):
    """검증용 비밀번호는 **환경변수로만** 받는다.

    ⚠ 코드에 적어 두면 비밀번호를 바꿔도 저장소에 옛 값이 계속 남는다.
      없으면 조용히 통과시키지 말고 **건너뛴다**.
    """
    return os.environ.get(env, "").strip()
OK = FAIL = 0
MARK = "B5T" + secrets.token_hex(3)


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


class Sess:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def go(self, method, path, data=None):
        body = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(BASE + path, data=body, method=method)
        if body:
            req.add_header("Content-Type", "application/json")
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.op.open(req, timeout=15) as r:
                raw = r.read().decode("utf-8", "replace")
                return r.status, (json.loads(raw) if raw.startswith(("{", "[")) else raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            return e.code, (json.loads(raw) if raw.startswith(("{", "[")) else raw)

    def login(self, path, uid, pw):
        st, d = self.go("POST", path, {"username": uid, "login_id": uid, "password": pw})
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
            return True
        return False


def cleanup(conn):
    ids = [r[0] for r in conn.execute("SELECT id FROM cases WHERE case_no LIKE 'B5T%'")]
    for cid in ids:
        for t in ("photos", "work_lots", "damage_reads", "auctions", "notifications"):
            conn.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM est_check_band WHERE src LIKE 'B5 검증%'")
    conn.commit()


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 68)
    print("  B5 검증 — 가견적 정합성 점검")
    print("=" * 68)

    # ── 1. 순수 함수 — 판정 규칙 그 자체 ─────────────────────
    print("\n[1] 점검 규칙 (순수 함수 · AI 키 불필요)")
    band = {"min_price": 3_000_000, "max_price": 8_000_000, "src": "시험"}
    one_cat = ["가드레일·방호울타리"]

    code, _ = A._est_check("보통", "담당자 확인", 5_000_000, band, one_cat, 2)
    chk(code == "정상", "구간 안 → 정상", code)

    code, note = A._est_check("보통", "담당자 확인", 9_000_000, band, one_cat, 2)
    chk(code == "금액과다", "상한 초과 → 금액과다", code)
    chk("8,000,000" in note, "  문구에 상한 금액이 보임", note)

    code, _ = A._est_check("보통", "담당자 확인", 1_000_000, band, one_cat, 2)
    chk(code == "금액과소", "하한 미만 → 금액과소", code)

    # ★ 가장 중요한 검사 — 판정이 없으면 '정상'이 아니어야 한다
    code, note = A._est_check(None, "미정", 5_000_000, band, one_cat, 2)
    chk(code == "판정없음", "★ 파손 정도 미정 → '정상' 아님(판정없음)", code)
    chk("직접 확인" in note, "  담당자에게 무엇을 하라고 알려줌", note)

    code, _ = A._est_check("보통", "담당자 확인", 5_000_000, None, one_cat, 2)
    chk(code == "기준없음", "★ 점검 기준이 없으면 '정상' 아님(기준없음)", code)

    code, _ = A._est_check("보통", "담당자 확인", 5_000_000, band, one_cat, 0)
    chk(code == "사진없음", "★ 사진이 없으면 '정상' 아님(사진없음)", code)

    code, _ = A._est_check("보통", "담당자 확인", 5_000_000, band,
                           ["가드레일·방호울타리", "유리·샷시·자동문"], 2)
    chk(code == "복합미대조", "복합 공종은 대조하지 않음", code)

    # 경계 — 상한과 정확히 같으면 통과
    code, _ = A._est_check("보통", "담당자 확인", 8_000_000, band, one_cat, 2)
    chk(code == "정상", "상한과 같은 금액은 통과(경계)", code)

    # ── 2. 실제 사건으로 — 근거 묶음 ─────────────────────────
    print("\n[2] 사건 단위 점검")
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,created_at,stats_exclude)
           VALUES(?,?,?,?,?,?,?,0,'입찰중',?,1)""",
        (f"{MARK}-1", iid, "검증보험", "가드레일·방호울타리", "서울", "B5검증",
         9_000_000, DB.now()))
    cid = cur.lastrowid
    conn.execute("INSERT INTO work_lots(case_id,category,status,created_at) "
                 "VALUES(?,?,'입찰중',?)", (cid, "가드레일·방호울타리", DB.now()))
    conn.commit()

    b = A._est_basis(conn, cid)
    chk(b["code"] == "사진없음", "사진 없는 사건 → 사진없음", b["code"])

    # 사진 1장 추가
    conn.execute(
        """INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,orig_name,
                              mime,ext,size,sha256,kind,review_status,created_at)
           VALUES(?,NULL,'검증','보험사',?,?,?,?,?,?,?,'승인',?)""",
        (cid, f"t/{MARK}.jpg", "t.jpg", "image/jpeg", ".jpg", 100,
         "b5_" + secrets.token_hex(6), "착공전", DB.now()))
    conn.commit()
    b = A._est_basis(conn, cid)
    chk(b["code"] == "판정없음", "사진은 있고 판정 없음 → 판정없음", b["code"])
    chk(b["photo_count"] == 1, "  사진 수를 셈", b["photo_count"])

    # 담당자가 파손 정도를 직접 확정
    conn.execute("UPDATE cases SET human_severity='보통', human_severity_by='검증' WHERE id=?", (cid,))
    conn.commit()
    b = A._est_basis(conn, cid)
    chk(b["code"] == "기준없음", "판정은 있고 기준 없음 → 기준없음", b["code"])
    chk(b["severity_src"] == "담당자 확인", "  판정 출처가 담당자", b["severity_src"])

    # 점검 기준 등록
    conn.execute(
        """INSERT INTO est_check_band(major,severity,min_price,max_price,src,updated_by,updated_at)
           VALUES(?,?,?,?,?,?,?)""",
        ("가드레일·방호울타리", "보통", 3_000_000, 8_000_000, "B5 검증용", "검증", DB.now()))
    conn.commit()
    b = A._est_basis(conn, cid)
    chk(b["code"] == "금액과다", "기준 등록 후 → 금액과다(9백만 > 상한 8백만)", b["code"])
    chk(b["band"] and b["band"]["src"] == "B5 검증용", "  기준의 근거가 함께 나옴")

    # ★ 사람 판정이 사진 판정보다 우선하는가
    conn.execute("UPDATE cases SET ai_severity='경미' WHERE id=?", (cid,))
    conn.commit()
    b = A._est_basis(conn, cid)
    chk(b["severity"] == "보통" and b["severity_src"] == "담당자 확인",
        "★ 담당자 판정이 사진 판정보다 우선", f"{b['severity']}/{b['severity_src']}")

    # ── 3. 확인 처리는 그때 그 금액에만 유효 ─────────────────
    print("\n[3] 경고 확인 처리")
    conn.execute("UPDATE cases SET est_ack_code='금액과다', est_ack_est=9000000 WHERE id=?", (cid,))
    conn.commit()
    b = A._est_basis(conn, cid)
    chk(b["acked"] is True, "확인 처리하면 확인됨으로 표시")

    conn.execute("UPDATE cases SET est_price=9500000 WHERE id=?", (cid,))
    conn.commit()
    b = A._est_basis(conn, cid)
    chk(b["acked"] is False, "★ 금액이 바뀌면 확인이 자동 무효", f"acked={b['acked']}")

    # ── 4. 점검이 금액을 절대 바꾸지 않는가 ──────────────────
    print("\n[4] 금액 불변")
    before = conn.execute("SELECT est_price FROM cases WHERE id=?", (cid,)).fetchone()[0]
    for _ in range(3):
        A._est_basis(conn, cid)
    after = conn.execute("SELECT est_price FROM cases WHERE id=?", (cid,)).fetchone()[0]
    chk(before == after, "★ 점검을 몇 번 돌려도 가견적이 그대로", f"{before}→{after}")

    # ── 5. 표준 단가는 참고 표시일 뿐 합계를 내지 않는가 ─────
    print("\n[5] 표준 단가 취급")
    b = A._est_basis(conn, cid)
    chk(isinstance(b.get("ref_items"), list), "표준 단가를 참고로 내려줌")
    chk("합계" not in json.dumps(b, ensure_ascii=False) or "합계를 내지 않습니다" in (b.get("ref_note") or ""),
        "★ 합계·추천가 필드를 만들지 않음")
    if b.get("ref_items"):
        chk(b.get("ref_note") and "수량 정보가 없어" in b["ref_note"],
            "  수량이 없어 합계를 못 낸다고 밝힘", b.get("ref_note"))

    # ── 6. 판정 이력이 성공·실패 모두 남는가 ─────────────────
    print("\n[6] 판정 이력")
    A._record_damage_read(conn, cid, None, "중대", "시험 소견", "test-model", 9_000_000)
    A._record_damage_read(conn, cid, None, None, "키 미연동", "", 9_000_000)
    conn.commit()
    n_ok = conn.execute("SELECT COUNT(*) FROM damage_reads WHERE case_id=? AND ok=1", (cid,)).fetchone()[0]
    n_no = conn.execute("SELECT COUNT(*) FROM damage_reads WHERE case_id=? AND ok=0", (cid,)).fetchone()[0]
    chk(n_ok == 1 and n_no == 1, "★ 성공·실패 판정이 모두 이력에 남음", f"성공{n_ok}/실패{n_no}")

    # ── 7. 권한 ──────────────────────────────────────────────
    print("\n[7] 권한")
    adm, staff = Sess(), Sess()
    #  ⚠ 비밀번호가 없으면 **로그인을 시도조차 하지 않는다.** 종전에는 옛 값으로
    #    무작정 시도해 401 을 쌓았다 — 그게 감사로그를 채우고 잠금 카운터를 태운다.
    if not (_cred("BOKGUON_TEST_ADMIN_PW") and _cred("BOKGUON_TEST_STAFF_PW")):
        print("  [건너뜀] BOKGUON_TEST_ADMIN_PW / _STAFF_PW 가 없습니다 "
              "— 권한 검사를 건너뜁니다(통과로 세지 않습니다).")
    elif adm.login("/api/login", "admin", _cred("BOKGUON_TEST_ADMIN_PW")):
        st, r = adm.go("POST", "/api/est-bands",
                       {"major": "유리·샷시·자동문", "severity": "보통", "max_price": 5_000_000})
        chk(st == 400, "★ 근거 없이 기준 등록 거절", f"{st} {r}")
        st, r = adm.go("POST", "/api/est-bands",
                       {"major": "유리·샷시·자동문", "severity": "보통",
                        "max_price": 5_000_000, "src": "B5 검증용 근거"})
        chk(st == 200, "근거를 적으면 등록", f"{st} {r}")
        st, r = adm.go("POST", "/api/est-bands",
                       {"major": "유리·샷시·자동문", "severity": "보통",
                        "min_price": 9_000_000, "max_price": 1_000_000, "src": "B5 검증"})
        chk(st == 400, "하한이 상한보다 크면 거절", st)
        st, d = adm.go("GET", "/api/est-bands")
        chk(st == 200 and isinstance(d.get("bands"), list), "기준 목록 조회")
        chk("award_samples" in d, "★ 낙찰 표본 수를 함께 알려줌(과신 방지)", d.get("award_samples"))
    if _cred("BOKGUON_TEST_STAFF_PW") and staff.login(
            "/api/login", "staff", _cred("BOKGUON_TEST_STAFF_PW")):
        st, _ = staff.go("POST", "/api/est-bands",
                         {"major": "조경·수목", "severity": "보통", "max_price": 1, "src": "x"})
        chk(st == 403, "★ 중간관리자는 기준을 못 바꿈", st)

    cleanup(conn)
    conn.close()
    print("-" * 68)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
