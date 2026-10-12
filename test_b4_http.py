# -*- coding: utf-8 -*-
"""B4 HTTP 경로 검증 — 실제 세션으로 사건 등록 → 투찰 → 마감 → 승인까지.

인프로세스 검사(test_b4_deadline.py)가 못 잡는 것을 본다:
  · 권한 데코레이터가 제대로 걸렸는가
  · 마감 후에도 **보험사가 실제로 승인할 수 있는가** (관문이 막히지 않았는가)
  · 마감 후 투찰이 HTTP 로 거절되는가
  · 어드민 우회 경로가 봉쇄돼 있는가
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import json
import urllib.request
import urllib.error
import http.cookiejar

import db as DB

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

    def login(self, path, uid, pw, me_path):
        # ⚠ 관리자 로그인은 필드명이 username, 포털은 login_id 다. 응답에 csrf 가 실려온다.
        st, d = self.go("POST", path, {"username": uid, "login_id": uid, "password": pw})
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
            return True
        _, me = self.go("GET", me_path)
        self.csrf = (me or {}).get("csrf", "") if isinstance(me, dict) else ""
        return bool(self.csrf)


def main():
    if not _creds_or_skip('BOKGUON_TEST_ADMIN_PW', 'BOKGUON_TEST_INSURER_PW', 'BOKGUON_TEST_PARTNER_PW'):
        return 0
    adm, ins, par = Sess(), Sess(), Sess()
    print("=" * 66)
    print("  B4 HTTP 검증")
    print("=" * 66)
    chk(adm.login("/api/login", "admin", _cred("BOKGUON_TEST_ADMIN_PW"), "/api/me"), "관리자 로그인")
    chk(ins.login("/api/insurer/login", "insurer", _cred("BOKGUON_TEST_INSURER_PW"), "/api/insurer/me"), "보험사 로그인")
    chk(par.login("/api/partner/login", "partner", _cred("BOKGUON_TEST_PARTNER_PW"), "/api/partner/me"), "협력사 로그인")
    if FAIL:
        print("  로그인 실패 — 중단"); return 1

    # ① 보험사가 사건을 등록하면 마감시각이 함께 생긴다
    st, r = ins.go("POST", "/api/insurer/cases", {
        "category": "가드레일·방호울타리", "region": "서울", "address": "B4검증 현장",
        "est_price": 10_000_000, "desc": "B4 HTTP 검증"})
    cid = (r or {}).get("id")
    chk(st == 200 and cid, "보험사 사건 등록", f"{st} {r}")
    _, cases = ins.go("GET", "/api/insurer/cases")
    _, opens = par.go("GET", "/api/open-auctions")
    mine = [c for c in (opens or []) if c.get("id") == cid]
    chk(len(mine) == 1, "협력사 공고 목록에 노출")
    chk(mine and mine[0].get("deadline"), "  공고에 마감시각이 실려 나옴",
        mine[0] if mine else "")

    # ② 마감 전 투찰은 정상
    st, r = par.go("POST", "/api/partner/bids", {"case_id": cid, "amount": 9_000_000, "days": 7})
    chk(st == 200, "마감 전 투찰 성공", f"{st} {r}")

    # ③ 마감시각을 과거로 (관리자 전용)
    _, det = adm.go("GET", f"/api/cases/{cid}/detail")
    _, allrows = adm.go("GET", "/api/dashboard")
    st, r = par.go("POST", "/api/auctions/1/deadline", {"deadline": "2020-01-01 00:00:00"})
    chk(st in (401, 403), "협력사는 마감시각을 바꿀 수 없음", st)

    # auction_id 는 어드민 사건 상세로 안 나오므로 DB 에서 직접 찾는다.
    conn = DB.get_db()
    aid = conn.execute(
        "SELECT id FROM auctions WHERE case_id=? AND change_order_id IS NULL", (cid,)).fetchone()[0]
    conn.close()
    st, r = adm.go("POST", f"/api/auctions/{aid}/deadline", {"deadline": "2020-01-01 00:00:00"})
    chk(st == 200, "관리자가 마감시각 앞당기기", f"{st} {r}")

    # ④ 마감 점검 실행
    st, r = adm.go("POST", "/api/admin/sweep", {})
    chk(st == 200 and r.get("claimed") is True, "마감 점검 실행(리스 확보)", f"{st} {r}")
    chk(r.get("closed", 0) >= 1, "  마감 처리 1건 이상", r)

    _, det = adm.go("GET", f"/api/cases/{cid}/detail")
    c = (det or {}).get("case") or det or {}
    chk(c.get("status") == "승인대기", "사건이 '승인대기'로", c.get("status"))
    chk(not c.get("partner_id") and not c.get("award_amount"),
        "★ 낙찰업체·금액이 비어 있음", f"{c.get('partner_id')} / {c.get('award_amount')}")

    # ⑤ 마감 후 투찰은 거절 (상태 전이 뒤 — 앞단 상태 가드에 걸린다)
    st, r = par.go("POST", "/api/partner/bids", {"case_id": cid, "amount": 8_000_000, "days": 7})
    chk(st == 400, "마감 처리 후 투찰 거절", f"{st} {r}")

    # ⑤-2 ★마감 가드의 본래 목적★ — 마감 점검이 **아직 안 돈** 구간.
    #   시각은 지났는데 사건 상태는 여전히 '입찰중'인 창. 여기서도 막혀야 한다.
    #   (이걸 확인 안 하면 마감 점검이 늦는 동안 마감된 공고에 투찰이 들어온다)
    st, r2 = ins.go("POST", "/api/insurer/cases", {
        "category": "가드레일·방호울타리", "region": "서울", "address": "B4검증 현장2",
        "est_price": 10_000_000, "desc": "마감 가드 검증"})
    cid2 = (r2 or {}).get("id")
    conn = DB.get_db()
    aid2 = conn.execute(
        "SELECT id FROM auctions WHERE case_id=? AND change_order_id IS NULL", (cid2,)).fetchone()[0]
    conn.close()
    adm.go("POST", f"/api/auctions/{aid2}/deadline", {"deadline": "2020-01-01 00:00:00"})
    _, d2 = adm.go("GET", f"/api/cases/{cid2}/detail")
    c2 = (d2 or {}).get("case") or {}
    chk(c2.get("status") == "입찰중", "  마감 점검 전 — 사건은 아직 '입찰중'", c2.get("status"))
    st, r = par.go("POST", "/api/partner/bids", {"case_id": cid2, "amount": 9_000_000, "days": 7})
    chk(st == 400 and (r or {}).get("code") == "CLOSED",
        "★ 마감 점검 전이라도 시각이 지났으면 투찰 거절(CLOSED)", f"{st} {r}")

    # ⑥ 마감된 공고는 목록에서 사라진다
    _, opens = par.go("GET", "/api/open-auctions")
    chk(not [c for c in (opens or []) if c.get("id") == cid], "마감 공고는 목록에서 제외")

    # ⑦ ★관문★ 마감 후에도 보험사는 승인할 수 있어야 한다
    _, bl = ins.go("GET", f"/api/insurer/cases/{cid}/bids")
    bids = (bl or {}).get("bids") or (bl if isinstance(bl, list) else [])
    chk(bool(bids), "보험사가 입찰 목록을 볼 수 있음", bl)
    if bids:
        st, r = ins.go("POST", f"/api/insurer/cases/{cid}/award", {"bid_id": bids[0]["id"]})
        chk(st == 200, "★ 마감 후에도 보험사 낙찰 승인 성공", f"{st} {r}")
        _, det = adm.go("GET", f"/api/cases/{cid}/detail")
        c = (det or {}).get("case") or det or {}
        chk(c.get("status") == "시공중" and c.get("partner_id"),
            "  낙찰 확정 후 시공중 + 낙찰업체 기록", c.get("status"))

    # ⑧ 설정 범위 검증
    for bad, why in (({"min_bidders": 0}, "최소 성립 0"),
                     ({"low_price_alert": 150}, "저가경보 150%"),
                     ({"auction_hours": 0}, "입찰창 0시간"),
                     ({"job_lease": "x"}, "내부 동작값")):
        st, _ = adm.go("PATCH", "/api/settings", bad)
        chk(st == 400, f"설정 거절 — {why}", st)

    # ⑨ dry_run 은 상태를 바꾸지 않는다
    st, r = adm.go("POST", "/api/admin/sweep", {"dry_run": True})
    chk(st == 200 and r.get("dry_run") is True and r.get("closed", 0) == 0,
        "미리보기 실행은 아무것도 바꾸지 않음", r)

    print("-" * 66)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
