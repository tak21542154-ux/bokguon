# -*- coding: utf-8 -*-
"""실테스트 전체 리허설 — 다음 주에 사람이 밟을 순서를 그대로 밟는다.

  트랙A(사진 있음): 보험사 접수 → 협력사 입찰 → 보험사 낙찰 승인 → 시공 사진 →
                    완료 보고 → 검수 승인(정산 생성) → 보험사 완료승인 → 입금확인 →
                    지급검수 → 이체 → 하자 접수 → 지적↔보수 → 하자 완료
  트랙B(사진 없음): 보험사 접수 → 출동 수배 → 수락 → 도착(실견적) → 1차 합의 →
                    부동의 → 2차 경매

  ⚠ 이 스크립트는 **화면이 아니라 API 순서**를 검증한다. 중간에 막히면
    "다음 주에 사람이 그 자리에서 멈춘다"는 뜻이다.
"""
import os, sys, json, zlib, struct, uuid, sqlite3
import urllib.request, http.cookiejar

BASE = "http://127.0.0.1:8799"
BASE = os.environ.get("BOKGUON_TEST_BASE", BASE)
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "bokguon.db")
MARK = "REH" + uuid.uuid4().hex[:5].upper()
RUN = uuid.uuid4().bytes


def png(rgb):
    rgb = [(c + RUN[i]) % 256 for i, c in enumerate(rgb)]
    w = h = 8
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def ck(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n"
            + ck(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ck(b"IDAT", zlib.compress(raw)) + ck(b"IEND", b""))


class C:
    def __init__(self, who):
        self.who = who
        self.op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ""

    def go(self, method, path, data=None):
        b = json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(BASE + path, data=b, method=method)
        req.add_header("Content-Type", "application/json")
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            r = self.op.open(req, timeout=25); st, raw = r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, raw = e.code, e.read().decode("utf-8", "replace")
        try:
            d = json.loads(raw)
        except Exception:
            d = raw[:200]
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
        return st, d

    def upload(self, path, files, fields=None):
        bnd = "----bg" + uuid.uuid4().hex
        body = b""
        for k, v in (fields or {}).items():
            body += (f"--{bnd}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n").encode()
        for fn, blob in files:
            body += (f"--{bnd}\r\nContent-Disposition: form-data; name=\"photos\"; "
                     f"filename=\"{fn}\"\r\nContent-Type: image/png\r\n\r\n").encode() + blob + b"\r\n"
        body += f"--{bnd}--\r\n".encode()
        req = urllib.request.Request(BASE + path, data=body, method="POST")
        req.add_header("Content-Type", f"multipart/form-data; boundary={bnd}")
        if self.csrf:
            req.add_header("X-CSRF-Token", self.csrf)
        try:
            r = self.op.open(req, timeout=60); st, raw = r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, raw = e.code, e.read().decode("utf-8", "replace")
        try:
            return st, json.loads(raw)
        except Exception:
            return st, raw[:200]


ok = fail = 0
stops = []


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  [OK]   {name}")
    else:
        fail += 1; stops.append(name); print(f"  [STOP] {name}   {got}")
    return bool(cond)


adm = C("admin"); ins = C("insurer"); par = C("partner")
chk(adm.go("POST", "/api/login", {"username": "admin",
    "password": os.environ["BOKGUON_TEST_ADMIN_PW"]})[0] == 200, "운영자 로그인")
chk(ins.go("POST", "/api/insurer/login", {"login_id": "insurer",
    "password": os.environ["BOKGUON_TEST_INSURER_PW"]})[0] == 200, "보험사 로그인")
chk(par.go("POST", "/api/partner/login", {"login_id": "partner",
    "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})[0] == 200, "시행사 로그인")

conn = sqlite3.connect(DBP); conn.row_factory = sqlite3.Row
pid = conn.execute("SELECT id FROM partners WHERE login_id='partner'").fetchone()[0]

made = []

# ══════════════ 트랙 A — 사진 있는 정상 건 ══════════════
print("\n══ 트랙A: 접수 → 입찰 → 낙찰 → 시공 → 정산 → 하자 ══")
print("\n[A1] 보험사가 사건을 올린다")
st, r = ins.go("POST", "/api/insurer/cases", {
    "category": "유리·샷시·자동문", "region": "서울", "address": f"{MARK} 리허설현장 12-3",
    "est_price": 3_000_000, "victim_name": "리허설피해자", "victim_phone": "010-2222-3333",
    "urgent": 0})
cid = (r or {}).get("id")
if not chk(st == 200 and cid, "사건 등록", f"{st} {r}"):
    sys.exit(1)
made.append(cid)
case_no = conn.execute("SELECT case_no FROM cases WHERE id=?", (cid,)).fetchone()[0]
print(f"       → {case_no}")

st, r = ins.upload(f"/api/insurer/cases/{cid}/photos", [("dmg.png", png((200, 40, 40)))])
chk(st == 200, "피해 사진 첨부", f"{st} {r}")

print("\n[A2] 시행사가 공고를 보고 입찰한다")
st, dash = par.go("GET", "/api/partner/dashboard")
opens = (dash or {}).get("open_cases") or []
mine = [c for c in opens if c.get("id") == cid]
chk(bool(mine), "공고가 협력사 목록에 뜬다", f"{st} 목록 {len(opens)}건")
if mine:
    m = mine[0]
    #  ★ 철칙 — 협력사에 상세주소·경쟁가·낙찰가가 보이면 안 된다
    leak = [k for k in ("address", "low_price", "award_amount", "manager", "victim_name",
                        "victim_phone") if m.get(k)]
    chk(not leak, "★ 공고에 상세주소·경쟁가·낙찰가·담당자가 없다(철칙)", leak)

st, r = par.go("POST", "/api/partner/bids", {"case_id": cid, "amount": 2_400_000, "days": 3})
chk(st == 200 and (r or {}).get("ok"), "입찰 제출", f"{st} {r}")
st, r = par.go("POST", "/api/partner/bids", {"case_id": cid, "amount": 2_600_000, "days": 3})
chk(st != 200, "★ 인상 재입찰은 거부(1차는 인하만)", f"{st} {r}")

print("\n[A3] 마감 → 보험사 낙찰 승인")
conn.execute("UPDATE auctions SET deadline=datetime('now','+9 hours','-1 hours') "
             " WHERE case_id=? AND change_order_id IS NULL", (cid,))
conn.commit()
st, r = adm.go("POST", "/api/admin/sweep", {})
st_now = conn.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()[0]
chk(st_now == "승인대기", "마감 후 승인대기로", st_now)

st, d = ins.go("GET", f"/api/insurer/cases/{cid}/bids")
bids = (d or {}).get("bids") or []
chk(bool(bids), "보험사가 입찰 목록을 본다", f"{st} {len(bids)}건")
if bids:
    st, r = ins.go("POST", f"/api/insurer/cases/{cid}/award", {"bid_id": bids[0]["id"]})
    chk(st == 200 and (r or {}).get("ok"), "낙찰 승인", f"{st} {r}")
row = conn.execute("SELECT status, partner_id, award_amount FROM cases WHERE id=?", (cid,)).fetchone()
chk(row["status"] == "시공중" and row["award_amount"] == 2_400_000,
    "사건이 시공중 · 낙찰가 확정", dict(row))

print("\n[A4] 시행사가 시공 사진을 올리고 완료 보고")
st, r = par.upload(f"/api/partner/cases/{cid}/photos",
                   [("b.png", png((10, 90, 200))), ("m.png", png((30, 160, 90))),
                    ("a.png", png((220, 170, 20)))])
chk(st == 200 and (r or {}).get("count") == 3, "시공 사진 3장", f"{st} {r}")
ph = conn.execute("SELECT id FROM photos WHERE case_id=? ORDER BY id", (cid,)).fetchall()
for p, kind in zip(ph[1:], ["착공전", "시공중", "완료"]):
    adm.go("POST", f"/api/photos/{p['id']}/kind", {"kind": kind})
st, r = par.go("POST", f"/api/partner/cases/{cid}/complete", {"memo": "리허설 완료"})
chk(st == 200, "완료 보고", f"{st} {r}")

print("\n[A5] 운영자 검수 → 정산 생성")
st, r = adm.go("POST", f"/api/cases/{cid}/photos/approve", {})
chk(st == 200, "사진 검수 승인", f"{st} {r}")
st, r = adm.go("POST", f"/api/cases/{cid}/approve", {})
chk(st == 200, "완료 검수 승인 → 정산 생성", f"{st} {r}")
sett = conn.execute("SELECT * FROM settlements WHERE case_id=? ORDER BY id DESC LIMIT 1",
                    (cid,)).fetchone()
chk(bool(sett), "정산이 만들어졌다", sett and dict(sett))
if sett:
    chk(sett["amount"] == 2_400_000 and sett["fee"] + sett["payout"] == sett["amount"],
        "★ 금액 구성이 맞는다(공사대금 = 수수료 + 지급액)",
        sett and f"{sett['amount']}={sett['fee']}+{sett['payout']}")
    sid = sett["id"]

print("\n[A6] 보험사 완료 승인 → 입금 → 지급검수 → 이체")
st, r = adm.go("POST", f"/api/settlements/{sid}/paid")
chk(st == 409, "★ 보험사 완료승인 없이는 입금확인이 막힌다", f"{st} {r}")
st, r = ins.go("POST", f"/api/insurer/settlements/{sid}/approve")
chk(st == 200, "보험사 공사 완료 승인", f"{st} {r}")
st, r = adm.go("POST", f"/api/settlements/{sid}/paid")
chk(st == 200, "보험사 입금 확인", f"{st} {r}")
st, r = adm.go("POST", f"/api/settlements/{sid}/review", {"double_checked": True})
chk(st == 200, "지급 검수 승인", f"{st} {r}")
st, r = adm.go("POST", f"/api/settlements/{sid}/transfer", {})
chk(st == 200, "이체 완료", f"{st} {r}")
fin = conn.execute("SELECT status FROM cases WHERE id=?", (cid,)).fetchone()[0]
chk(fin == "완료", "사건이 완료로 닫힌다", fin)

print("\n[A7] 하자 접수 → 지적 → 보수 → 완료")
after = conn.execute(
    "SELECT id FROM photos WHERE case_id=? AND kind='완료' ORDER BY id DESC LIMIT 1",
    (cid,)).fetchone()
st, r = ins.go("POST", "/api/defects", {
    "case_id": cid, "title": f"{MARK} 실링 벌어짐", "severity": "보통",
    "content": "우천 시 누수", "photos": [{"photo_id": after["id"], "note": "우측 하단 실링"}]})
chk(st == 200, "보험사 하자 접수(사진 지적 포함)", f"{st} {r}")
did = conn.execute("SELECT id FROM defects WHERE case_id=? ORDER BY id DESC LIMIT 1",
                   (cid,)).fetchone()[0]
st, r = par.go("GET", f"/api/defects/{did}/photos")
chk(st == 200 and (r or {}).get("marked_count") == 1,
    "★ 시행사가 지적 사진·사유를 본다", f"{st} {r.get('marked_count') if isinstance(r, dict) else r}")
st, r = par.upload(f"/api/defects/{did}/photos", [("fix.png", png((60, 200, 120)))],
                   {"fix_for": str(after["id"])})
chk(st == 200 and (r or {}).get("fix_for") == after["id"], "보수 사진을 지적에 붙임", f"{st} {r}")
st, r = ins.go("GET", f"/api/defects/{did}/photos")
chk(st == 200 and (r or {}).get("all_fixed") is True,
    "★ 보험사가 지적↔보수를 대조할 수 있다", f"{st} {r.get('all_fixed') if isinstance(r, dict) else r}")
st, r = par.go("POST", f"/api/partner/defects/{did}/resolve", {"resolution": "실링 전면 재시공"})
chk(st == 200, "시행사 재시공 완료 보고", f"{st} {r}")
st, r = adm.go("PATCH", f"/api/defects/{did}", {"status": "완료", "resolution": "검수 완료"})
chk(st == 200, "운영자 하자 완료 처리", f"{st} {r}")

# ══════════════ 트랙 B — 사진 없는 접수(출동) ══════════════
print("\n══ 트랙B: 사진없음 접수 → 출동 → 실견적 → 2차 경매 ══")
st, r = ins.go("POST", "/api/insurer/cases", {
    "category": "가드레일·방호울타리", "region": "서울", "address": f"{MARK} 출동현장 45",
    "est_price": 5_000_000, "no_photo": True})
cid2 = (r or {}).get("id")
chk(st == 200 and cid2, "사진없음 접수", f"{st} {r}")
if cid2:
    made.append(cid2)
    itype = conn.execute("SELECT intake_type FROM cases WHERE id=?", (cid2,)).fetchone()[0]
    chk(itype == "사진없음", "접수 유형이 '사진없음'", itype)
    st, r = adm.go("POST", f"/api/cases/{cid2}/dispatch", {})
    chk(st == 200, "출동 수배 개시", f"{st} {r}")
    dsp = conn.execute("SELECT id, status FROM dispatches WHERE case_id=? ORDER BY id DESC LIMIT 1",
                       (cid2,)).fetchone()
    chk(bool(dsp), "수배가 만들어졌다", dsp and dict(dsp))
    if dsp:
        st, r = par.go("POST", f"/api/partner/dispatches/{dsp['id']}/claim", {})
        claimed = (st == 200)
        chk(claimed or st == 409, "수배 수락(또는 이미 다른 업체가 수락)", f"{st} {r}")
        if claimed:
            st, r = par.upload(f"/api/partner/cases/{cid2}/photos",
                               [("site.png", png((140, 60, 190)))])
            chk(st == 200 and (r or {}).get("count") == 1,
                "★ 수배 상태에서 현장 사진이 올라간다(도착 보고의 전제)", f"{st} {r}")
            st, r = par.go("POST", f"/api/partner/dispatches/{dsp['id']}/arrive",
                           {"field_estimate": 4_200_000, "note": "리허설 실견적"})
            chk(st == 200, "도착 보고(실견적 제출)", f"{st} {r}")
            #  1차 합의는 자동이 아니다 — 운영자가 '견적 원문 승인 요청'을 눌러야 열린다.
            st, r = adm.go("POST", f"/api/cases/{cid2}/field-agreement", {})
            chk(st == 200, "운영자가 견적 원문 승인 요청(1차 합의 개시)", f"{st} {r}")
            fa = conn.execute("SELECT id, status FROM field_agreements WHERE case_id=? "
                              " ORDER BY id DESC LIMIT 1", (cid2,)).fetchone()
            chk(bool(fa), "1차 합의 검토가 열렸다", fa and dict(fa))
            if fa:
                st, r = ins.go("POST", f"/api/insurer/cases/{cid2}/field-agreement/decision",
                               {"approve": False, "reason": "금액 과다 — 경매로 전환"})
                chk(st == 200, "보험사 부동의", f"{st} {r}")
                st, r = adm.go("POST", f"/api/cases/{cid2}/open-auction",
                               {"est_basis": "부동의 후 현장 사진으로 2차 경매"})
                chk(st == 200 and (r or {}).get("round") == 2, "★ 2차 경매 개시", f"{st} {r}")
                lo, = conn.execute("SELECT est_price FROM cases WHERE id=?", (cid2,)).fetchone()
                chk(lo == 5_000_000, "★ 2차에서 가견적(하한)은 그대로", lo)
                st, r = par.go("POST", "/api/partner/bids",
                               {"case_id": cid2, "amount": 4_000_000, "days": 3})
                chk(st != 200, "★ 하한 미만 입찰은 거부", f"{st} {r}")
                st, r = par.go("POST", "/api/partner/bids",
                               {"case_id": cid2, "amount": 5_500_000, "days": 3})
                chk(st == 200, "★ 2차는 하한 이상이면 상한 없이 입찰 가능", f"{st} {r}")

# ══════════════ 정리 ══════════════
for x in made:
    conn.execute("DELETE FROM bids WHERE auction_id IN (SELECT id FROM auctions WHERE case_id=?)", (x,))
    conn.execute("DELETE FROM defect_photos WHERE defect_id IN (SELECT id FROM defects WHERE case_id=?)", (x,))
    for t in ("auctions", "work_lots", "field_agreements", "dispatches", "photos",
              "notifications", "defects", "settlements", "est_outcome", "happy_calls"):
        try:
            conn.execute(f"DELETE FROM {t} WHERE case_id=?", (x,))
        except sqlite3.Error:
            pass
    conn.execute("DELETE FROM cases WHERE id=?", (x,))
conn.commit(); conn.close()

print(f"\n{'='*62}")
print(f"  리허설 통과 {ok} · 막힌 지점 {fail}")
if stops:
    print("  ⚠ 다음 주에 사람이 멈추는 자리:")
    for s in stops:
        print(f"     · {s}")
print(f"{'='*62}")
sys.exit(1 if fail else 0)
