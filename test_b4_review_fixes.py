# -*- coding: utf-8 -*-
"""적대적 검토에서 확정된 B4 결함 8건의 회귀 검사.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

각 검사는 '고치기 전이라면 반드시 실패하는' 형태로 쓴다.
그렇지 않으면 나중에 누가 되돌려놔도 초록불이 유지된다.
"""
import re
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import secrets
import urllib.request
import urllib.error
import http.cookiejar

import db as DB
# [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import app as A

#  ⚠ 운영(prod) 서버는 세션 쿠키에 Secure 를 건다. 그러면 파이썬 http.cookiejar 는
#    http://127.0.0.1 로는 쿠키를 **보내지 않는다**(브라우저와 달리 localhost 예외가 없다).
#    → 로그인은 되는데 이후 요청이 전부 401/CSRF 로 떨어진다. 검증은 dev 모드 인스턴스에서 돌린다.
#  ⚠ 기본값은 **검증 서버(8799)** 다. 8771 은 운영이라, 따로 실행했을 때
#    운영을 두드리게 된다(형제 테스트들은 전부 8799 였고 이 둘만 달랐다).
BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")

# ── 검증용 자격증명 ────────────────────────────────────────────
#  ⚠ 예전에는 여기에 비밀번호를 그대로 적어 뒀다. 그 파일이 저장소에 남아 있는 한
#    비밀번호를 바꿔도 옛 값이 계속 굴러다닌다(실제로 데모 비번이 인터넷에 열린 적이 있다).
#    이제 환경변수로만 받는다. 없으면 검사를 **건너뛴다**(조용히 통과시키지 않는다).
#      set BOKGUON_TEST_ADMIN_PW=...   / _INSURER_PW / _PARTNER_PW
def _cred(env):
    return os.environ.get(env, "").strip()


def _creds_or_skip(*envs):
    missing = [e for e in envs if not _cred(e)]
    if missing:
        print("=" * 66)
        print("  [건너뜀] 검증용 계정 비밀번호가 설정되지 않았습니다.")
        print("           " + " / ".join(missing))
        print("           예) $env:BOKGUON_TEST_ADMIN_PW='...' 후 다시 실행")
        print("=" * 66)
        return False
    return True


OK = FAIL = 0
MARK = "RV" + secrets.token_hex(3)


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
    ids = [r[0] for r in conn.execute("SELECT id FROM cases WHERE case_no LIKE ?", (MARK + "%",))]
    for cid in ids:
        conn.execute("DELETE FROM bids WHERE auction_id IN "
                     "(SELECT id FROM auctions WHERE case_id=?)", (cid,))
        conn.execute("DELETE FROM change_orders WHERE case_id=?", (cid,))
        for t in ("auctions", "work_lots", "notifications"):
            conn.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM partners WHERE name LIKE ?", (MARK + "%",))
    conn.commit()


def main():
    if not _creds_or_skip('BOKGUON_TEST_ADMIN_PW'):
        return 0
    conn = DB.get_db()
    cleanup(conn)
    adm = Sess()
    print("=" * 68)
    print("  적대적 검토 확정 결함 회귀 검사")
    print("=" * 68)
    chk(adm.login("/api/login", "admin", _cred("BOKGUON_TEST_ADMIN_PW")), "관리자 로그인")
    if FAIL:
        print("  로그인 실패 — 중단"); return 1

    # ── B. 마감시각은 정규화된 값만 저장 ──────────────────────
    print("\n[B] 마감시각 형식")
    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    cur = conn.execute(
        """INSERT INTO cases(case_no,insurer_id,insurer,category,region,address,
                             est_price,low_price,status,created_at)
           VALUES(?,?,?,?,?,?,?,0,'입찰중',?)""",
        (f"{MARK}-1", iid, "검토보험", "가드레일·방호울타리", "서울", "회귀검증",
         10_000_000, DB.now()))
    cid = cur.lastrowid
    aid = A._open_original_auction(conn, cid)
    conn.commit()

    st, r = adm.go("POST", f"/api/auctions/{aid}/deadline", {"deadline": "2026-07-24T09:00:00"})
    chk(st == 400, "★ 'T' 구분자 거절 (통과하면 마감이 하루 밀린다)", f"{st} {r}")
    st, r = adm.go("POST", f"/api/auctions/{aid}/deadline",
                   {"deadline": "2451545.00000000000"})
    chk(st == 400, "★ 율리우스일 문자열 거절 (통과하면 영구 미마감)", f"{st} {r}")
    st, r = adm.go("POST", f"/api/auctions/{aid}/deadline", {"deadline": "2026-02-30 00:00:00"})
    chk(st == 400, "존재하지 않는 날짜 거절", f"{st} {r}")
    st, r = adm.go("POST", f"/api/auctions/{aid}/deadline", {"deadline": "2026-07-25 09:00:00"})
    chk(st == 200, "정상 형식 통과", f"{st} {r}")
    saved = conn.execute("SELECT deadline FROM auctions WHERE id=?", (aid,)).fetchone()[0]
    chk(saved == "2026-07-25 09:00:00", "저장값이 정규화 형식", saved)

    # ── C. 대상 0건에도 생존 신호를 남긴다 ────────────────────
    print("\n[C] 마감 점검 생존 신호")
    conn.execute("UPDATE job_locks SET last_run_at=NULL WHERE name='auction_sweep'")
    conn.execute("UPDATE auctions SET deadline=datetime('now','+9 hours','+48 hours') "
                 "WHERE status='진행'")
    conn.commit()
    n_due = conn.execute(
        "SELECT COUNT(*) FROM auctions WHERE status='진행' "
        "AND deadline IS NOT NULL AND deadline<=datetime('now','+9 hours')").fetchone()[0]
    A.sweep_auctions(conn, force=True)
    last = conn.execute(
        "SELECT last_run_at FROM job_locks WHERE name='auction_sweep'").fetchone()[0]
    chk(n_due == 0, f"  마감 대상 0건 상태 만들기 (대상 {n_due}건)")
    chk(bool(last), "★ 대상 0건이어도 last_run_at 갱신 (안 되면 배지가 상시 빨강)", last)

    # ── D. 설정 변경은 최고관리자만 ───────────────────────────
    print("\n[D] 설정 변경 권한")
    staff = Sess()
    #  ⚠ 같은 파일 119행은 이미 환경변수를 쓰는데 **여기만 비밀번호가 박혀 있었다.**
    #    고칠 때 admin 만 바꾸고 staff 를 빠뜨린 자리다. 저장소에 남은 옛 값은
    #    비밀번호를 바꿔도 계속 굴러다닌다.
    if staff.login("/api/login", "staff", _cred("BOKGUON_TEST_STAFF_PW")):
        st, r = staff.go("PATCH", "/api/settings", {"min_bidders": 5})
        chk(st == 403, "★ 중간관리자의 설정 변경 차단", f"{st} {r}")
    else:
        print("  [건너뜀] staff 계정 없음")
    st, r = adm.go("PATCH", "/api/settings", {"min_bidders": 3})
    chk(st == 200, "최고관리자는 설정 변경 가능", f"{st} {r}")

    # ── E. 어드민 낙찰은 중간관리자 이상 ──────────────────────
    print("\n[E] 낙찰 권한")
    src = open("app.py", encoding="utf-8").read()
    m = re.search(r'@app\.post\("/api/cases/<int:cid>/award"\)\s*\n@(\w+)\(([^)]*)\)', src)
    chk(m and m.group(1) == "require_role", "★ 어드민 낙찰이 등급 게이트 사용",
        m.group(0) if m else "패턴 없음")

    # ── F. 저가 경보 0 = 끔 ───────────────────────────────────
    print("\n[F] 저가 경보 끄기")
    adm.go("PATCH", "/api/settings", {"low_price_alert": 0})
    st, d = adm.go("GET", "/api/dashboard")
    chk(st == 200 and d.get("risky") == [], "★ 경보 0%면 이상 저가 목록이 비어 있음",
        f"{len(d.get('risky') or [])}건")
    adm.go("PATCH", "/api/settings", {"low_price_alert": 20})
    st, d = adm.go("GET", "/api/dashboard")
    chk(d.get("low_price_alert_pct") == 20, "경보 20%로 복원", d.get("low_price_alert_pct"))

    # ── A. 추가분 재경매 교착 출구 ────────────────────────────
    print("\n[A] 추가분 재경매 교착 해소")
    pid = conn.execute(
        "SELECT id FROM partners WHERE partner_type='시행사' AND status='활성' LIMIT 1").fetchone()[0]
    conn.execute("UPDATE cases SET status='시공중', partner_id=?, award_amount=5000000 WHERE id=?",
                 (pid, cid))
    co = conn.execute(
        """INSERT INTO change_orders(case_id,incumbent_partner_id,incumbent_amount,
                                     requested_amount,reason,status,round,created_at)
           VALUES(?,?,?,?,?,'추가경매중',1,?)""",
        (cid, pid, 5_000_000, 2_000_000, "회귀검증", DB.now())).lastrowid
    A._open_reauction(conn, cid, co, "추가분", 1)
    conn.commit()
    raid = conn.execute(
        "SELECT id FROM auctions WHERE change_order_id=?", (co,)).fetchone()[0]

    # 마감시각을 과거로 → 자동 마감
    conn.execute("UPDATE auctions SET deadline=datetime('now','+9 hours','-1 hours') WHERE id=?",
                 (raid,))
    conn.commit()
    A.sweep_auctions(conn, force=True)
    st_a = conn.execute("SELECT status FROM auctions WHERE id=?", (raid,)).fetchone()[0]
    chk(st_a == "마감", "  입찰 0건 추가분 경매가 자동 마감됨", st_a)

    # 출구 ① — 유찰 확정 라우트
    st, r = adm.go("POST", f"/api/change-orders/{co}/fail-add", {})
    chk(st == 200, "★ 추가분 유찰 확정 (없으면 영구 교착)", f"{st} {r}")
    co_st = conn.execute("SELECT status FROM change_orders WHERE id=?", (co,)).fetchone()[0]
    chk(co_st == "유찰", "  변경건이 '유찰'로 — 전체 재경매로 이어갈 수 있음", co_st)

    # 출구 ② — 마감된 재경매를 다시 열 수 있는가
    conn.execute("UPDATE auctions SET status='마감' WHERE id=?", (raid,))
    conn.commit()
    st, r = adm.go("POST", f"/api/auctions/{raid}/deadline", {"deadline": "2026-12-31 23:59:59"})
    chk(st == 200, "★ 마감된 재경매 다시 열기", f"{st} {r}")
    a2 = conn.execute("SELECT status, deadline FROM auctions WHERE id=?", (raid,)).fetchone()
    chk(a2[0] == "진행", "  상태가 '진행'으로 복귀", a2[0])

    # 원경매는 이 경로로 되살아나면 안 된다(사건 상태와 얽혀 있음)
    conn.execute("UPDATE auctions SET status='마감' WHERE id=?", (aid,))
    conn.commit()
    st, r = adm.go("POST", f"/api/auctions/{aid}/deadline", {"deadline": "2026-12-31 23:59:59"})
    chk(st == 409, "★ 원경매는 이 경로로 못 되살림(=/reopen 전용)", f"{st} {r}")

    # ── 부록. 가운뎃점 표기 흔들림에도 검색이 되는가 ────────
    #  정부 공식 업종명은 'ㆍ'(아래아)를 쓰는데 사람은 '·'를 친다.
    #  맞춰주지 않으면 결과가 0건으로 나와 **검색이 잘 된 줄 알고 넘어간다.**
    print("\n[부록] 가운뎃점 표기 흔들림")
    n_var = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE category LIKE '%ㆍ%'").fetchone()[0]
    if n_var:
        plain = conn.execute(
            "SELECT COUNT(*) FROM partners WHERE category LIKE ?", ("%금속·창호%",)).fetchone()[0]
        norm = conn.execute(
            "SELECT COUNT(*) FROM partners "
            " WHERE REPLACE(REPLACE(category,'ㆍ','·'),'･','·') LIKE ?",
            ("%금속·창호%",)).fetchone()[0]
        chk(norm > plain, f"★ 표기 맞춤 검색이 더 찾아냄 (기존 {plain}건 → {norm}건)")
        chk(A._norm_dot("금속ㆍ창호") == "금속·창호", "  _norm_dot 이 아래아를 가운뎃점으로")
    else:
        print("  [건너뜀] 이 DB 에는 아래아 표기 데이터가 없음")

    #  ⚠⚠ 위 검사는 SQL 기법 자체(REPLACE+LIKE)만 확인한다 — 실제 API 가 쓰는
    #    _partner_filter·_case_filter 가 **그 기법을 실제로 쓰는지는 안 본다.**
    #    실측(2026-08-20): 두 함수가 이 정규화 없이 각자 LIKE 를 다시 짜서, 아래아
    #    표기 협력사 10곳(실제 id 305~314)이 표준 가운뎃점 검색에 하나도 안 걸렸다
    #    (0건 = 검색이 잘 된 줄 알고 넘어간다). 여기서는 함수를 직접 호출해 확인한다.
    print("\n[부록-2] 실제 필터 함수가 아래아 표기를 실제로 찾는가")

    class _Args(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업','서울','활성')",
        (f"{MARK}-아래아업체",)).lastrowid
    conn.commit()

    where, p = A._partner_filter(_Args(q="금속·창호"))
    n = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE " + " AND ".join(where) + " AND id=?",
        p + [pid]).fetchone()[0]
    chk(n == 1, "★★★ _partner_filter 가 표준 가운뎃점 검색으로 아래아 업체를 찾는다"
        "(실측 결함 재현·수정 확인)", f"찾은 건수={n}")

    #  ⚠ _case_filter 는 데모 사건을 항상 제외한다(자기 WHERE 첫 조각) — 정규화와
    #    무관한 조건에서 오탐(false negative)이 나지 않게 is_demo=0 으로 심는다.
    cid = conn.execute(
        "INSERT INTO cases(case_no,category,status,created_at,is_demo) "
        "VALUES(?,'금속ㆍ창호ㆍ지붕공사','접수',datetime('now','+9 hours'),0)",
        (f"{MARK}-dot",)).lastrowid
    conn.commit()
    where2, p2 = A._case_filter(_Args(q="금속·창호"))
    n2 = conn.execute(
        "SELECT COUNT(*) FROM cases WHERE " + " AND ".join(where2) + " AND id=?",
        p2 + [cid]).fetchone()[0]
    chk(n2 == 1, "★★★ _case_filter 도 마찬가지로 아래아 표기 사건을 찾는다", f"찾은 건수={n2}")

    cleanup(conn)
    conn.close()
    print("-" * 68)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
