# -*- coding: utf-8 -*-
"""E2E — 사진 없는 접수부터 이체 완료까지, 3자가 실제로 주고받는 전 과정.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

smoke_test.py 는 **1차 트랙**(사진 있는 접수 → 상한 경매 → 낙찰 → 정산)을 본다.
이 검사는 그것과 겹치지 않는 **2차 트랙**을 끝까지 태운다 —
사진이 없어 현장 확인이 먼저 필요했던 건, 즉 실무에서 더 흔하고 더 잘 막히는 쪽이다.

    보험사 접수(사진 없음)
      → 운영자 출동 수배  → 협력사 선착순 수락 → 현장 도착·사진·실견적
      → 보험사 부동의     → 2차 경매(가견적이 **하한**, 상한 없음)
      → 협력사 입찰(하한 미만 거절 확인) → 낙찰 → **패자 통보**
      → 시공 사진 업로드  → 완료 보고(**특이사항 저장**)
      → 운영자 검수 승인  → 정산 생성
      → 보험사 완료 승인(**자동 독촉**도 확인) → 입금 확인
      → 지급 검수 승인    → 이체 완료(**관문 우회** 포함)
      → 하자 접수 → 협력사 **귀책 이의**

실서버에 HTTP 로 붙어 돈다. 검증 인스턴스(사본 DB)에서 실행할 것 —
  BOKGUON_TEST_BASE / BOKGUON_DB_PATH / BOKGUON_TEST_*_PW
"""
import io
import os
import sys
import json
import zlib
import struct
import urllib.parse
import urllib.request
import urllib.error
import http.cookiejar

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import db as DB
import dispatch as DP

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
MARK = "E2E"
PARTNER_PW = "E2ePw!2026#k"
OK = FAIL = 0
STEP = ""

def png(rgb):
    """색만 다른 1×1 PNG 를 만든다.

    ⚠ 뒤에 바이트를 덧붙여 '다른 파일'을 만들면 안 된다 — 서버가 이미지 검증에서
      옳게 거부하고, 그러면 저장은 0장인데 응답은 200 이라 검사가 통과해 버린다.
      (실제로 그래서 4장 중 1장만 저장된 걸 못 잡았다.)
    """
    def chunk(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00" + bytes(rgb)))
            + chunk(b"IEND", b""))


def head(t):
    global STEP
    STEP = t
    print(f"\n── {t} " + "─" * max(0, 56 - len(t)))


def chk(c, label, detail=""):
    global OK, FAIL
    if c:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def die(msg):
    print(f"\n  ✖ {STEP} 에서 더 진행할 수 없습니다 — {msg}")
    return 1


def _cred(k):
    return os.environ.get(k, "").strip()


class Sess:
    """쿠키·CSRF 를 들고 다니는 한 사람."""

    def __init__(self, who):
        self.who = who
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def go(self, m, p, d=None):
        b = json.dumps(d).encode() if d is not None else None
        r = urllib.request.Request(BASE + p, data=b, method=m)
        if b:
            r.add_header("Content-Type", "application/json")
        if self.csrf:
            r.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.op.open(r, timeout=20) as x:
                raw = x.read().decode("utf-8", "replace")
                return x.status, (json.loads(raw) if raw.startswith(("{", "[")) else raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            return e.code, (json.loads(raw) if raw.startswith(("{", "[")) else raw)

    def upload(self, path, files):
        """multipart 업로드 — 표준 라이브러리만으로 만든다(외부 의존 없음)."""
        bnd = "----bokguonE2E"
        body = b""
        for name, data in files:
            body += (f"--{bnd}\r\n"
                     f'Content-Disposition: form-data; name="photos"; filename="{name}"\r\n'
                     f"Content-Type: image/png\r\n\r\n").encode()
            body += data + b"\r\n"
        body += f"--{bnd}--\r\n".encode()
        r = urllib.request.Request(BASE + path, data=body, method="POST")
        r.add_header("Content-Type", f"multipart/form-data; boundary={bnd}")
        if self.csrf:
            r.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.op.open(r, timeout=30) as x:
                return x.status, json.loads(x.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            return e.code, (json.loads(raw) if raw.startswith("{") else raw)

    def login(self, path, uid, pw, me):
        self.go("POST", path, {"username": uid, "login_id": uid, "password": pw})
        st, d = self.go("GET", me)
        self.csrf = (d or {}).get("csrf", "") if isinstance(d, dict) else ""
        return bool(self.csrf)


def cleanup(conn):
    for cid in [r[0] for r in conn.execute(
            "SELECT id FROM cases WHERE case_no LIKE ?", (f"{MARK}%",))]:
        for p in conn.execute("SELECT rel_path FROM photos WHERE case_id=?", (cid,)):
            try:
                os.remove(os.path.join("uploads", (p[0] or "").replace("/", os.sep)))
            except OSError:
                pass
        for aid in [r[0] for r in conn.execute(
                "SELECT id FROM auctions WHERE case_id=?", (cid,))]:
            conn.execute("DELETE FROM bids WHERE auction_id=?", (aid,))
        for did in [r[0] for r in conn.execute(
                "SELECT id FROM dispatches WHERE case_id=?", (cid,))]:
            conn.execute("DELETE FROM dispatch_calls WHERE dispatch_id=?", (did,))
        #  하자를 지우기 전에 지적 사진 연결부터 — 안 그러면 고아 행이 남는다
        for dfid in [r[0] for r in conn.execute(
                "SELECT id FROM defects WHERE case_id=?", (cid,))]:
            conn.execute("DELETE FROM defect_photos WHERE defect_id=?", (dfid,))
        for t in ("photos", "auctions", "dispatches", "field_agreements", "settlements",
                  "defects", "notifications", "work_lots", "est_outcome",
                  "contract_gate_log", "happy_calls"):
            try:
                conn.execute(f"DELETE FROM {t} WHERE case_id=?", (cid,))
            except Exception:
                pass
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.execute("DELETE FROM partners WHERE name LIKE ?", (f"{MARK}%",))
    conn.commit()


def main():
    for k in ("BOKGUON_TEST_ADMIN_PW", "BOKGUON_TEST_INSURER_PW"):
        if not _cred(k):
            print(f"[건너뜀] {k} 가 설정되지 않았습니다.")
            return 0

    conn = DB.get_db()
    cleanup(conn)
    print("=" * 66)
    print(f"  E2E — 2차 트랙 전 과정   ({BASE})")
    print("=" * 66)

    adm, ins, par = Sess("운영자"), Sess("보험사"), Sess("협력사")

    # ── 0. 등장인물 ────────────────────────────────────────────
    head("0. 로그인")
    chk(adm.login("/api/login", "admin", _cred("BOKGUON_TEST_ADMIN_PW"), "/api/me"), "운영자")
    chk(ins.login("/api/insurer/login", "insurer", _cred("BOKGUON_TEST_INSURER_PW"),
                  "/api/insurer/me"), "보험사")
    if FAIL:
        return die("로그인 실패")

    iid = conn.execute("SELECT id FROM insurers WHERE login_id='insurer'").fetchone()[0]
    #  이 검사 전용 협력사 — 계좌까지 갖춘 정상 업체
    conn.execute(
        "INSERT INTO partners(name, partner_type, major, region, status, login_id, "
        " password_hash, must_change_pw, staff_count, bank_name, bank_holder, "
        " bank_account_enc) "
        "VALUES(?,'시행사','가드레일·방호울타리','서울','활성',?,?,0,5,'국민','E2E검증','x')",
        (f"{MARK}업체", f"{MARK.lower()}p", DB.hash_pw(PARTNER_PW)))
    pid = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    conn.commit()
    chk(par.login("/api/partner/login", f"{MARK.lower()}p", PARTNER_PW, "/api/partner/me"),
        "협력사")
    if FAIL:
        return die("협력사 로그인 실패")

    # ── 1. 보험사가 사진 없이 접수 ─────────────────────────────
    head("1. 보험사 접수 (사진 없음 → 출동 트랙)")
    st, d = ins.go("POST", "/api/insurer/cases", {
        "case_no": f"{MARK}-C1", "category": "가드레일·방호울타리", "region": "서울 송파",
        "address": "올림픽로 300", "est_price": 3000000, "desc": "E2E 검증 — 사진 없이 접수",
        "no_photo": True})
    cid = (d or {}).get("id")
    chk(st == 200 and cid, "사건 접수", f"{st} {d}")
    if not cid:
        return die("사건이 만들어지지 않았습니다")
    row = conn.execute("SELECT case_no, status, est_price FROM cases WHERE id=?", (cid,)).fetchone()
    chk(row["est_price"] == 3000000, "보상담당자 가견적 300만 기록", str(row["est_price"]))
    case_no = row["case_no"]

    # ── 2. 출동 수배 → 선착순 수락 ─────────────────────────────
    head("2. 출동 수배 · 선착순 수락")
    conn.execute("UPDATE cases SET status='접수', dispatch_status=NULL WHERE id=?", (cid,))
    conn.commit()
    st, d = adm.go("POST", f"/api/cases/{cid}/dispatch", {})
    chk(st == 200 and (d or {}).get("dispatch_id"), "운영자가 수배 개시",
        f"{st} {str(d)[:90]}")
    chk((d or {}).get("notified") is not None,
        "★ '불렀다'와 '닿았다'를 구분해 돌려준다", f"called={d.get('called')} notified={d.get('notified')}")
    did = (d or {}).get("dispatch_id")
    if not did:
        return die("수배가 열리지 않았습니다")
    #  내 업체가 후보에 없으면 직접 넣어 준다(지역·공종 매칭은 이 검사의 대상이 아니다)
    if not conn.execute("SELECT 1 FROM dispatch_calls WHERE dispatch_id=? AND partner_id=?",
                        (did, pid)).fetchone():
        conn.execute("INSERT INTO dispatch_calls(dispatch_id, partner_id, partner_name, "
                     "  call_order, notified_at, created_at) "
                     "VALUES(?,?,?,99,datetime('now','+9 hours'),datetime('now','+9 hours'))",
                     (did, pid, f"{MARK}업체"))
        conn.commit()
    st, d = par.go("POST", f"/api/partner/dispatches/{did}/claim", {})
    chk(st == 200 and (d or {}).get("ok"), "협력사가 선착순 수락", f"{st} {str(d)[:80]}")

    # ── 3. 현장 도착 — 사진 + 실견적 500만 ─────────────────────
    head("3. 현장 도착 · 사진 · 실견적")
    st, d = par.upload(f"/api/partner/cases/{cid}/photos",
                       [("e2e_site1.png", png((10, 20, 30))),
                        ("e2e_site2.png", png((40, 50, 60)))])
    #  ★ 보낸 장수가 아니라 **서버가 저장한 장수**를 본다
    chk(st == 200 and (d or {}).get("count") == 2, "현장 사진 2장 업로드",
        f"{st} count={(d or {}).get('count')}")
    st, d = par.go("POST", f"/api/partner/dispatches/{did}/arrive", {"field_estimate": 5000000})
    chk(st == 200 and (d or {}).get("ok"), "도착 보고 + 실견적 500만", f"{st} {str(d)[:90]}")

    # ── 4. 보험사 부동의 → 2차 경매 ────────────────────────────
    head("4. 보험사 부동의 → 2차 경매 (가견적이 하한)")
    st, d = adm.go("POST", f"/api/cases/{cid}/field-agreement", {})
    st, d = ins.go("POST", f"/api/insurer/cases/{cid}/field-agreement/decision",
                   {"approve": False, "reason": "실견적이 가견적을 크게 초과 — 경매로 전환"})
    chk(st == 200, "보험사 부동의 기록", f"{st} {str(d)[:80]}")
    fa = conn.execute("SELECT status, field_amount FROM field_agreements WHERE case_id=? "
                      "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()
    chk(fa and fa["status"] == DP.AG_BROKEN, "현장합의가 '결렬'로", (fa or {})["status"] if fa else "")
    #  개산 구간이 없으면 절감 기준선이 실견적으로 떨어진다 — 근거값을 넣어 둔다
    conn.execute("UPDATE field_agreements SET engine_low=4200000, engine_high=5400000 "
                 " WHERE case_id=?", (cid,))
    conn.execute("UPDATE cases SET status='접수' WHERE id=?", (cid,))
    conn.commit()
    st, d = adm.go("POST", f"/api/cases/{cid}/open-auction",
                   {"est_basis": "현장 사진 2장 확보 · 보험사 부동의로 경매 전환"})
    chk(st == 200, "2차 경매 개시", f"{st} {str(d)[:100]}")
    cs = conn.execute("SELECT status, est_price FROM cases WHERE id=?", (cid,)).fetchone()
    chk(cs["status"] == "입찰중", "사건이 '입찰중'으로", cs["status"])
    chk(cs["est_price"] == 3000000,
        "★ 가견적 300만이 그대로 보존된다(하한이므로 덮으면 안 된다)", str(cs["est_price"]))

    # ── 5. 입찰 — 하한 미만 거절, 하한 위는 통과 ───────────────
    head("5. 2차 입찰 — 하한 검증")
    st, d = par.go("POST", "/api/partner/bids", {"case_id": cid, "amount": 2500000, "days": 3})
    chk(st == 400 and (d or {}).get("code") == "UNDER_FLOOR",
        "★★ 가견적 아래(250만)는 거절된다", f"{st} {(d or {}).get('code')}")
    st, d = par.go("POST", "/api/partner/bids", {"case_id": cid, "amount": 4000000, "days": 5})
    chk(st == 200 and (d or {}).get("ok"),
        "★★ 가견적 위(400만)는 통과한다 — 1차 규칙이면 OVER_CAP 이었다", f"{st} {str(d)[:80]}")
    st, d = par.go("GET", "/api/partner/dashboard")
    oc = [x for x in (d or {}).get("open_cases", []) if x.get("id") == cid]
    chk(oc and oc[0].get("auction_round") == 2 and oc[0].get("bid_cap") == 0,
        "★ 화면에 '2차 · 상한 없음'으로 실려 나온다", str(oc[:1])[:90])
    #  ★★ 2차 경매의 전제 — "사진이 다 올라왔으니 실견적에 가까운 금액을 내라".
    #     그 사진을 못 보면 이 경매 자체가 성립하지 않는다.
    #     (예전 화면은 '피해 사진 N장 (낙찰 후 열람)' 이라고 안내했다)
    st, d = par.go("GET", f"/api/cases/{cid}/photos")
    chk(st == 200 and (d or {}).get("total", 0) >= 1,
        "★★ 입찰 전에 협력사가 현장 사진을 볼 수 있다", f"{st} {str(d)[:70]}")
    ph_id = ((d or {}).get("unclassified") or (d or {}).get("construction") or [{}])[0].get("id")
    if ph_id:
        st, _ = par.go("GET", f"/api/photos/{ph_id}/file")
        chk(st == 200, "★ 사진 원본도 열린다(목록만 되고 원본이 막히면 의미가 없다)", str(st))
    #  ⚠ 사진은 열되 **상세 주소는 여전히 낙찰 뒤에만** 보여야 한다(철칙)
    chk("address" not in str((oc or [{}])[0]) or not (oc or [{}])[0].get("address"),
        "★★ 사진을 열어도 상세 주소는 새지 않는다", str((oc or [{}])[0].get("address")))

    # ── 6. 낙찰 + 패자 통보 ────────────────────────────────────
    head("6. 낙찰 · 패자 통보")
    #  떨어질 업체 하나를 더 넣는다
    conn.execute("INSERT INTO partners(name, partner_type, major, region, status) "
                 "VALUES(?,'시행사','가드레일·방호울타리','서울','활성')", (f"{MARK}업체B",))
    pB = conn.execute("SELECT last_insert_rowid() r").fetchone()[0]
    aid = conn.execute("SELECT id FROM auctions WHERE case_id=? AND change_order_id IS NULL "
                       "ORDER BY id DESC LIMIT 1", (cid,)).fetchone()[0]
    conn.execute("INSERT INTO bids(auction_id, partner_id, partner_name, amount, days, created_at) "
                 "VALUES(?,?,?,4500000,6,datetime('now','+9 hours'))",
                 (aid, pB, f"{MARK}업체B"))
    myb = conn.execute("SELECT id FROM bids WHERE auction_id=? AND partner_id=?",
                       (aid, pid)).fetchone()[0]
    conn.commit()
    #  ★ 더 비싼 입찰을 사유 없이 고를 수 없다 — 최저가 낙찰이 이 플랫폼의 약속이다.
    #    (보험사 라우트에만 있던 게이트를 관리자 라우트에도 맞췄다)
    bB = conn.execute("SELECT id FROM bids WHERE auction_id=? AND partner_id=?",
                      (aid, pB)).fetchone()[0]
    st, d = adm.go("POST", f"/api/cases/{cid}/award", {"bid_id": bB, "insurer_instruction": "검증 — 발주처 유선 지시(2026-08-06 담당자 확인)"})
    chk(st == 400 and (d or {}).get("code") == "NOT_LOWEST",
        "★★ 최저가 아닌 입찰은 사유 없이 낙찰되지 않는다", f"{st} {(d or {}).get('code')}")
    st, d = adm.go("POST", f"/api/cases/{cid}/award", {"bid_id": myb, "insurer_instruction": "검증 — 발주처 유선 지시(2026-08-06 담당자 확인)"})
    chk(st == 200, "최저가 낙찰 확정", f"{st} {str(d)[:80]}")
    lose = [dict(r) for r in conn.execute(
        "SELECT partner_id, message FROM notifications WHERE ntype='입찰결과' AND case_id=?",
        (cid,))]
    chk(len(lose) == 1 and lose[0]["partner_id"] == pB, "★ 떨어진 업체에 결과 통보",
        str(lose)[:80])
    chk(lose and "4,000,000" not in (lose[0]["message"] or "")
        and f"{MARK}업체" not in (lose[0]["message"] or ""),
        "★★ 낙찰가·낙찰업체가 새지 않는다(철칙)", str(lose)[:80])

    # ── 7. 시공 → 완료 보고(특이사항) ──────────────────────────
    head("7. 시공 사진 · 완료 보고")
    st, d = par.upload(f"/api/partner/cases/{cid}/photos",
                       [("e2e_work1.png", png((70, 80, 90))),
                        ("e2e_work2.png", png((100, 110, 120)))])
    chk(st == 200 and (d or {}).get("count") == 2, "시공 사진 2장 업로드",
        f"{st} count={(d or {}).get('count')}")
    MEMO = "지주 2본 추가 교체 · 우천으로 1일 지연"
    st, d = par.go("POST", f"/api/partner/cases/{cid}/complete", {"memo": MEMO})
    chk(st == 200 and (d or {}).get("ok"), "완료 보고", f"{st} {str(d)[:80]}")
    lg = conn.execute("SELECT detail FROM activity_log WHERE action='시공 완료 보고' "
                      " ORDER BY id DESC LIMIT 1").fetchone()
    chk(lg and "지주 2본" in (lg["detail"] or ""),
        "★ 현장 특이사항이 감사로그에 저장된다(예전엔 항상 비었다)",
        (lg["detail"] if lg else "")[:60])

    # ── 8. 검수 승인 → 정산 ────────────────────────────────────
    head("8. 검수 승인 · 정산 생성")
    #  AI 미연동이면 사진이 '기타'로 남는다 — 그때는 담당자가 직접 분류한다.
    #  분류가 안 끝나면 검수 승인이 막히고, 검수가 막히면 정산이 안 생긴다.
    st, d = adm.go("GET", f"/api/cases/{cid}/photos")
    chk((d or {}).get("total") == 4, "사진 4장이 모두 남아 있다",
        f"total={(d or {}).get('total')}")
    unc = (d or {}).get("unclassified") or []
    for i, ph in enumerate(unc):
        adm.go("POST", f"/api/photos/{ph['id']}/kind",
               {"kind": "착공전" if i < 2 else "완료"})
    st, d = adm.go("GET", f"/api/cases/{cid}/photos")
    chk(not (d or {}).get("unclassified"), f"미분류 {len(unc)}장 담당자 재분류",
        str(len((d or {}).get("unclassified") or [])))
    st, d = adm.go("POST", f"/api/cases/{cid}/photos/approve", {})
    chk(st == 200, "사진 검수 일괄 승인", f"{st} {str(d)[:70]}")
    st, d = adm.go("POST", f"/api/cases/{cid}/approve", {})
    sid = (d or {}).get("settlement_id")
    chk(st == 200 and sid, "정산 생성", f"{st} {str(d)[:90]}")
    if not sid:
        return die("정산이 생성되지 않았습니다")
    s = conn.execute("SELECT amount, fee, payout FROM settlements WHERE id=?", (sid,)).fetchone()
    chk(s["amount"] == 4000000 and s["fee"] + s["payout"] == s["amount"],
        "낙찰가 = 수수료 + 실수령", f"{dict(s)}")

    # ── 9. 절감 기준선 — 2차는 개산 상단 ───────────────────────
    head("9. 절감 기준선 (2차는 표준단가 개산)")
    base = conn.execute(
        "SELECT COALESCE((SELECT fa.engine_high FROM field_agreements fa "
        "   WHERE fa.case_id=cases.id AND fa.status='결렬' AND COALESCE(fa.engine_high,0)>0 "
        "   ORDER BY fa.id DESC LIMIT 1), cases.est_price) b FROM cases WHERE id=?",
        (cid,)).fetchone()["b"]
    chk(base == 5400000, "기준선 = 개산 상단 540만", str(base))
    chk(base - 4000000 > 0,
        "★★ 절감이 양수(+140만) — 가견적 기준이면 −100만으로 찍혔다", str(base - 4000000))

    # ── 10. 완료승인 자동 독촉 ─────────────────────────────────
    head("10. 완료승인 자동 독촉")
    conn.execute("UPDATE settlements SET created_at=datetime('now','+9 hours','-9 days') "
                 " WHERE id=?", (sid,))
    conn.commit()
    import app as A
    c2 = DB.get_db()
    A.sweep_approval_overdue(c2)
    c2.close()
    n = conn.execute("SELECT COUNT(*) FROM notifications WHERE ntype='완료승인독촉' AND case_id=?",
                     (cid,)).fetchone()[0]
    chk(n == 1, "★ 9일 정체 건에 발주처 안내가 자동 발송", f"{n}통")
    c2 = DB.get_db()
    A.sweep_approval_overdue(c2)
    c2.close()
    n2 = conn.execute("SELECT COUNT(*) FROM notifications WHERE ntype='완료승인독촉' AND case_id=?",
                      (cid,)).fetchone()[0]
    chk(n2 == 1, "★★ 바로 다시 돌려도 스팸이 되지 않는다(24h 쿨다운)", f"{n2}통")

    # ── 11. 보험사 완료 승인 → 입금 확인 ───────────────────────
    head("11. 보험사 완료 승인 · 입금 확인")
    st, d = adm.go("POST", f"/api/settlements/{sid}/paid", {})
    chk(st == 409 and (d or {}).get("code") == "INSURER_NOT_APPROVED",
        "★ 보험사 승인 전에는 입금 확인이 막힌다", f"{st} {(d or {}).get('code')}")
    ins.go("GET", "/api/insurer/me")
    st, d = ins.go("POST", f"/api/insurer/settlements/{sid}/approve", {})
    chk(st == 200 and (d or {}).get("ok"), "보험사 공사 완료 승인", f"{st} {str(d)[:80]}")
    st, d = adm.go("POST", f"/api/settlements/{sid}/paid", {})
    chk(st == 200 and (d or {}).get("ok"), "입금 확인", f"{st} {str(d)[:80]}")

    # ── 12. 하자 접수 → 지급 관문 → 사유로 우회 ────────────────
    head("12. 하자 · 지급 관문 · 사유로 우회")
    st, d = adm.go("POST", f"/api/settlements/{sid}/review", {"double_checked": True})
    chk(st == 200 and (d or {}).get("ok"), "지급 검수 승인(계좌 있음)", f"{st} {str(d)[:80]}")
    conn.execute(
        "INSERT INTO defects(defect_no, case_id, case_no, insurer_id, partner_id, partner_name, "
        "  title, severity, status, cost_bearer, created_at) "
        "VALUES(?,?,?,?,?,?, '검수 후 발견된 하자','보통','접수','시행사',"
        "  datetime('now','+9 hours'))",
        (f"{MARK}-D1", cid, case_no, iid, pid, f"{MARK}업체"))
    conn.commit()
    st, d = adm.go("POST", f"/api/settlements/{sid}/transfer", {})
    chk(st == 409 and (d or {}).get("code") == "DEFECT_OPEN",
        "★ 열린 하자가 이체를 막는다", f"{st} {(d or {}).get('code')}")
    st, d = adm.go("POST", f"/api/settlements/{sid}/transfer",
                   {"defect_override_reason": "보험사 합의로 하자와 별개 선지급"})
    chk(st == 200 and (d or {}).get("ok"),
        "★★ 사유를 적으면 통과한다(예전엔 화면에 창구가 없었다)", f"{st} {str(d)[:80]}")
    lg = conn.execute("SELECT detail FROM activity_log WHERE action='이체 완료' "
                      " ORDER BY id DESC LIMIT 1").fetchone()
    chk(lg and "선지급" in (lg["detail"] or ""), "★ 넘긴 사유가 감사로그에 남는다",
        (lg["detail"] if lg else "")[:60])
    cs = conn.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()
    chk(cs["status"] == "완료", "사건이 '완료'로 닫힌다", cs["status"])

    # ── 13. 협력사 귀책 이의 ───────────────────────────────────
    head("13. 하자 귀책 이의")
    dfid = conn.execute("SELECT id FROM defects WHERE defect_no=?", (f"{MARK}-D1",)).fetchone()[0]
    st, d = par.go("POST", f"/api/partner/defects/{dfid}/dispute", {"reason": "짧음"})
    chk(st == 400, "사유가 짧으면 거절", f"{st}")
    st, d = par.go("POST", f"/api/partner/defects/{dfid}/dispute",
                   {"reason": "착공 전 사진에 동일 손상이 이미 찍혀 있습니다."})
    chk(st == 200, "이의 접수", f"{st} {str(d)[:70]}")
    df = conn.execute("SELECT status, cost_bearer, dispute_reason FROM defects WHERE id=?",
                      (dfid,)).fetchone()
    chk(df["status"] == "접수" and df["cost_bearer"] == "시행사",
        "★★ 이의가 귀책을 자동으로 바꾸지 않는다(사람이 재검토)",
        f"{df['status']}/{df['cost_bearer']}")

    # ── 13-2. 하자 지적 사진 — 어느 사진의 무엇이 문제인가 ──────
    #  하자가 제목·내용 '글자'뿐이면 시행사는 어느 지점인지 모른 채 현장에 간다.
    #  보험사가 완료 사진을 보며 고른 사진과 사유가 **그대로** 시행사에 닿아야 한다.
    head("13-2. 하자 지적 사진이 시행사에 닿는가")
    ph = [r["id"] for r in conn.execute(
        "SELECT id FROM photos WHERE case_id=? ORDER BY id", (cid,))]
    chk(len(ph) >= 2, "지적할 사진이 있다", len(ph))
    st, d = ins.go("POST", "/api/defects", {
        "case_id": cid, "title": "방수 마감 불량", "content": "우천 후 누수",
        "severity": "중대",
        "photos": [{"photo_id": ph[0], "note": "좌측 이음부 실링 벌어짐"},
                   {"photo_id": ph[1], "note": "하단 마감 들뜸"}]})
    chk(st == 200 and (d or {}).get("marked_photos") == 2,
        "★★ 보험사가 사진 2장을 사유와 함께 지적한다",
        f"{st} {(d or {}).get('marked_photos')}")
    did2 = (d or {}).get("id")
    #  ★ 시행사가 그 사진과 사유를 그대로 본다
    st, d = par.go("GET", f"/api/defects/{did2}/photos")
    items = (d or {}).get("marked") or []      # 첨부(items)가 아니라 **지적**을 본다
    chk(st == 200 and len(items) == 2, "★★ 시행사가 지적 사진을 연다", f"{st} {len(items)}")
    notes = " ".join((i.get("note") or "") for i in items)
    chk("실링" in notes and "들뜸" in notes,
        "★★ 사진별 사유가 그대로 전달된다(글자 한 줄이 아니라 지점별로)", notes[:60])
    if items:
        st, _ = par.go("GET", f"/api/photos/{items[0]['id']}/file")
        chk(st == 200, "★ 지적 사진 원본이 열린다(사건이 이미 완료로 닫혔어도)", str(st))
    #  ★ 목록에서도 '사진이 있다'는 것부터 보여야 열어 본다
    st, d = par.go("GET", "/api/partner/defects")
    mine = [x for x in (d or []) if x.get("id") == did2]
    chk(mine and mine[0].get("marked_photos") == 2,
        "★ 하자 목록에 지적 사진 장수가 보인다", str(mine[:1])[:80])
    #  ⚠ 남의 사건 사진을 끌어와 걸 수 없다 — 걸리면 엉뚱한 현장을 고치러 간다
    other = conn.execute("SELECT id FROM photos WHERE case_id<>? LIMIT 1", (cid,)).fetchone()
    if other:
        st, d = ins.go("POST", "/api/defects", {
            "case_id": cid, "title": "타사건 사진 시도", "severity": "경미",
            "photos": [{"photo_id": other["id"], "note": "다른 현장"}]})
        chk((d or {}).get("marked_photos") == 0,
            "★★ 다른 사건의 사진은 걸리지 않는다", str((d or {}).get("marked_photos")))

    # ── 14. 협력사가 자기 일의 결과를 볼 수 있는가 ─────────────
    head("14. 협력사 화면 — 결과·정산이 보이는가")
    st, d = par.go("GET", "/api/partner/dashboard")
    mb = [b for b in (d or {}).get("my_bids", []) if b.get("case_id") == cid]
    chk(mb and mb[0].get("my_result") == "낙찰", "내 입찰 결과가 '낙찰'로 보인다", str(mb[:1])[:80])
    chk(mb and mb[0].get("case_no") == case_no, "사건번호가 함께 보인다")
    ss = [x for x in (d or {}).get("settlements", []) if x.get("case_id") == cid]
    chk(ss and ss[0].get("stage") == "지급 완료", "정산 단계가 '지급 완료'로 보인다",
        str((ss or [{}])[0].get("stage")))
    chk("rating_basis" in (d or {}).get("me", {}), "평점 근거가 함께 내려온다")

    # ── 15. 어드민 알림함 ──────────────────────────────────────
    head("15. 운영 알림이 종 알림함에 뜨는가")
    st, d = adm.go("GET", "/api/admin/notifications")
    items = (d or {}).get("notifications", [])
    kinds = {i.get("ntype") for i in items}
    chk("하자이의" in kinds, "★ 하자 이의가 운영자 알림함에 뜬다", str(sorted(kinds))[:90])

    # ── 16. 주소 검색 → 좌표 확정 ──────────────────────────────
    #  주소가 자유 입력이던 시절에는 좌표가 시군구 중심뿐이라 지도가 '동네'를 가리켰고,
    #  거리순 배차도 사실상 해시 순서였다. 골라 넣은 좌표가 끝까지 남는지 본다.
    head("16. 주소 검색 · 좌표 확정")
    st, d = adm.go("GET", "/api/address/search?q=" +
                   urllib.parse.quote("송파구 올림픽로 300"))
    hits = (d or {}).get("items") or []
    chk(st == 200 and hits, "주소 검색이 결과를 준다", f"{st} {len(hits)}건")
    top = hits[0] if hits else {}
    chk(bool(top.get("lat") and top.get("lng")), "★ 좌표가 함께 온다",
        f"{top.get('lat')} {top.get('lng')}")
    chk((top.get("region") or "").startswith("서울"), "지역이 시군구로 정리된다",
        str(top.get("region")))
    st, d = ins.go("POST", "/api/insurer/cases", {
        "case_no": f"{MARK}-ADDR", "categories": ["가드레일·방호울타리"],
        "region": top.get("region") or "서울 송파구",
        "address": (top.get("road") or "") + " 지하 2층",
        "est_price": 1000000, "no_photo": True,
        "lat": top.get("lat"), "lng": top.get("lng"),
        "victim_name": "E2E피해자", "victim_phone": "010-0000-0000"})
    acid = (d or {}).get("id")
    row2 = conn.execute("SELECT lat, lng, geo_src, victim_phone FROM cases WHERE id=?",
                        (acid,)).fetchone() if acid else None
    chk(row2 and row2["geo_src"] == "주소검색" and row2["lat"],
        "★★ 고른 좌표가 사건에 저장된다", str(dict(row2)) if row2 else "없음")
    chk(row2 and (row2["victim_phone"] or "") == "010-0000-0000",
        "★ 접수 단계에서 피해자 연락처가 저장된다(예전엔 칸이 없어 늘 비었다)",
        str(row2["victim_phone"]) if row2 else "없음")
    #  한반도 밖 좌표는 버려야 한다 — 틀린 좌표는 없느니만 못하다
    st, d = ins.go("POST", "/api/insurer/cases", {
        "case_no": f"{MARK}-BADXY", "categories": ["가드레일·방호울타리"],
        "region": "서울", "address": "어딘가", "est_price": 500000,
        "no_photo": True, "lat": 1.0, "lng": 200.0})
    bad = conn.execute("SELECT lat, geo_src FROM cases WHERE id=?",
                       ((d or {}).get("id"),)).fetchone()
    chk(bad and bad["lat"] is None, "★ 범위 밖 좌표는 저장되지 않는다",
        str(dict(bad)) if bad else "없음")

    # ── 17. 피해자 조회 링크 ───────────────────────────────────
    head("17. 피해자 조회 링크 · 안내 예약")
    st, d = adm.go("POST", f"/api/cases/{acid}/track-link", {})
    chk(st == 200 and (d or {}).get("token"), "링크 발급", f"{st} {str(d)[:60]}")
    chk((d or {}).get("has_phone") is True, "★ 연락처가 있음을 화면에 알려 준다")
    chk(str((d or {}).get("full_url", "")).startswith("http"),
        "★★ 문자에 넣을 주소가 절대 주소다(예전엔 /track/… 만 나가 열 수 없었다)",
        str((d or {}).get("full_url"))[:50])
    vn = [dict(r) for r in conn.execute(
        "SELECT message FROM notifications WHERE ntype='피해자안내' AND case_id=?", (acid,))]
    chk(vn and "http" in (vn[0]["message"] or ""),
        "★★ 발급과 동시에 안내가 적재된다(예전엔 발급만 하고 아무것도 안 보냈다)",
        str(vn)[:80])
    st, d = adm.go("GET", "/track/" + (d or {}).get("token", "x"))
    chk(st == 200 and isinstance(d, str) and "복구" in d, "피해자 화면이 열린다", str(st))
    chk(isinstance(d, str) and "1,000,000" not in d,
        "★★ 피해자 화면에 금액이 새지 않는다(철칙)")

    # ── 18. 운영 문서 ──────────────────────────────────────────
    head("18. 현장 출동 보고서 · 청구 항목 설명서")
    st, d = adm.go("GET", f"/report/dispatch/{cid}")
    chk(st == 200 and "현장 출동 보고서" in str(d), "출동 보고서가 열린다", str(st))
    chk("호출 이력" in str(d) and "손해액을 사정" in str(d),
        "★ 호출 이력과 법적 한계 고지가 함께 실린다")
    st, d = adm.go("GET", "/report/billing")
    chk(st == 200 and "청구 항목 설명서" in str(d), "청구 설명서가 열린다", str(st))
    chk("400,000" in str(d) and "3,600,000" in str(d),
        "★★ 예시 금액이 실제 계산 함수에서 나온다(문서에 숫자를 박지 않았다)")
    #  로그인 없이는 못 본다 — 계약 요율이 담긴 문서다.
    #  ⚠ 상태코드로 보면 안 된다: 서버는 302 로 로그인 화면에 보내는데
    #    urllib 이 그걸 따라가 200 을 돌려준다. **내용이 보이는지**로 판정한다.
    anon = Sess("비로그인")
    st, body = anon.go("GET", "/report/billing")
    chk("청구 항목 설명서" not in str(body), "★ 비로그인은 내용을 볼 수 없다",
        f"{st} {str(body)[:60]}")
    st, body = anon.go("GET", f"/report/dispatch/{cid}")
    chk("현장 출동 보고서" not in str(body), "★ 비로그인은 출동 보고서도 볼 수 없다",
        f"{st} {str(body)[:60]}")

    cleanup(conn)
    conn.close()
    print("\n" + "=" * 66)
    print(f"  E2E 통과 {OK} · 실패 {FAIL}   (검증 데이터 정리됨)")
    print("=" * 66)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
