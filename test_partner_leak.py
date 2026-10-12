# -*- coding: utf-8 -*-
"""협력사 노출 철칙 전수 검사 — 시행사에게 가는 **모든 응답**을 훑는다.

  철칙: 협력사에 경쟁가·낙찰가·상세주소·보상담당자·피해자 연락처를 노출하지 않는다.
  ⚠ 단, **자기가 낙찰받은 건**은 주소를 알아야 시공한다 — 그 경계를 함께 확인한다.

  방법: 협력사 세션으로 /api/partner/* 를 전부 호출해 응답 JSON 을 재귀로 훑고,
        금지 키 또는 금지 값(다른 업체 입찰가, 낙찰가)이 섞였는지 본다.
"""
import io, os, re, sys, json, sqlite3
import urllib.request, http.cookiejar

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bokguon.db")


class C:
    def __init__(self):
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
            d = None
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
        return st, d


ok = fail = 0


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  [OK]   {name}")
    else:
        fail += 1; print(f"  [LEAK] {name}   {got}")


def walk(node, path=""):
    """응답 JSON 을 재귀로 훑어 (경로, 키, 값) 을 모두 뽑는다."""
    if isinstance(node, dict):
        for k, v in node.items():
            yield (path, k, v)
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node[:60]):
            yield from walk(v, f"{path}[{i}]")


par = C()
st, _ = par.go("POST", "/api/partner/login",
               {"login_id": "partner", "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})
chk(st == 200, "협력사 로그인", st)

conn = sqlite3.connect(DBP); conn.row_factory = sqlite3.Row
pid = conn.execute("SELECT id FROM partners WHERE login_id='partner'").fetchone()[0]

#  이 협력사가 **낙찰받지 않은** 사건들의 낙찰가·주소·담당자 — 새면 안 되는 값
secret_award = {r["award_amount"] for r in conn.execute(
    "SELECT award_amount FROM cases WHERE COALESCE(award_amount,0)>0 "
    " AND (partner_id IS NULL OR partner_id<>?) LIMIT 400", (pid,)) if r["award_amount"]}
#  ⚠ 주소를 **문자열로** 비교하면 안 된다 — 여러 사건이 같은 주소를 쓰면
#     자기 현장까지 유출로 잡힌다(실제로 오탐이 났다). 사건 id 소유권으로 본다.
mine_ids = {r["id"] for r in conn.execute(
    "SELECT id FROM cases WHERE partner_id=?", (pid,))}
open_ids = {r["case_id"] for r in conn.execute(
    "SELECT DISTINCT case_id FROM auctions WHERE status='진행'")}
#  남의 입찰가(경쟁가)
secret_bid = {r["amount"] for r in conn.execute(
    "SELECT amount FROM bids WHERE partner_id<>? LIMIT 400", (pid,)) if r["amount"]}
#  피해자 연락처는 어떤 경우에도 협력사에 안 간다
secret_victim = {(r["victim_phone"] or "").strip() for r in conn.execute(
    "SELECT victim_phone FROM cases WHERE COALESCE(victim_phone,'')<>'' LIMIT 400")}

print(f"\n감시 대상 — 남의 낙찰가 {len(secret_award)}개 · 내 사건 {len(mine_ids)}건 · "
      f"남의 입찰가 {len(secret_bid)}개 · 피해자 연락처 {len(secret_victim)}개")

BANNED_KEYS = {"victim_name", "victim_phone", "manager", "insurer_manager",
               "bank_account_enc", "password_hash", "track_token", "rel_path", "sha256"}

ENDPOINTS = [
    ("GET", "/api/partner/dashboard"),
    ("GET", "/api/partner/defects"),
    ("GET", "/api/partner/dispatches"),
    ("GET", "/api/partner/notifications"),
    ("GET", "/api/me"),
]

print("\n[1] 협력사 응답 전수 훑기")
for method, ep in ENDPOINTS:
    st, d = par.go(method, ep)
    if st != 200 or d is None:
        print(f"  [건너뜀] {ep} ({st})")
        continue
    bad_keys, bad_vals = [], []
    for p, k, v in walk(d):
        if k in BANNED_KEYS and v not in (None, "", 0):
            bad_keys.append(f"{p}.{k}={str(v)[:24]}")
        if isinstance(v, int) and v > 0:
            if v in secret_award and k in ("award_amount", "low_price", "amount"):
                bad_vals.append(f"{p}.{k}={v}(남의 낙찰가)")
        if isinstance(v, str) and len(v) > 6:
            sv = v.strip()
            if sv in secret_victim:
                bad_vals.append(f"{p}.{k}={sv}(피해자 연락처)")
    #  주소가 실린 항목은 그 사건이 **내 것인지** 로 판정한다.
    bad_addr = []
    def scan_addr(node, where):
        if isinstance(node, dict):
            if (node.get("address") or "").strip() and node.get("id"):
                if node["id"] not in mine_ids:
                    bad_addr.append(f"{where} case={node['id']} addr={node['address'][:20]}")
            for k, v in node.items():
                scan_addr(v, f"{where}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node[:60]):
                scan_addr(v, f"{where}[{i}]")
    scan_addr(d, ep)
    chk(not bad_keys, f"{ep} — 금지 필드 없음", bad_keys[:3])
    chk(not bad_vals, f"{ep} — 남의 금액 없음", bad_vals[:3])
    chk(not bad_addr, f"★ {ep} — 내 것이 아닌 사건의 상세주소 없음", bad_addr[:3])

print("\n[2] 남의 자원 직접 접근(IDOR)")
other_case = conn.execute(
    "SELECT id FROM cases WHERE (partner_id IS NULL OR partner_id<>?) "
    " AND status IN ('시공중','완료','정산진행') LIMIT 1", (pid,)).fetchone()
if other_case:
    st, d = par.go("GET", f"/api/cases/{other_case[0]}/photos")
    chk(st in (401, 403, 404) or not (d or {}).get("construction"),
        "★ 남의 사건 사진 목록 차단", f"{st}")
other_ph = conn.execute(
    "SELECT p.id FROM photos p JOIN cases c ON c.id=p.case_id "
    " WHERE c.partner_id IS NULL OR c.partner_id<>? LIMIT 1", (pid,)).fetchone()
if other_ph:
    st, _ = par.go("GET", f"/api/photos/{other_ph[0]}/file")
    chk(st in (401, 403, 404), "★ 남의 사진 파일 차단", st)
other_st = conn.execute(
    "SELECT id FROM settlements WHERE partner_id IS NULL OR partner_id<>? LIMIT 1",
    (pid,)).fetchone()
if other_st:
    st, _ = par.go("GET", f"/api/settlements/{other_st[0]}/detail")
    chk(st in (401, 403, 404), "★ 남의 정산 상세 차단", st)
other_df = conn.execute(
    "SELECT id FROM defects WHERE partner_id IS NULL OR partner_id<>? LIMIT 1", (pid,)).fetchone()
if other_df:
    st, _ = par.go("GET", f"/api/defects/{other_df[0]}/photos")
    chk(st in (401, 403, 404), "★ 남의 하자 사진 차단", st)

print("\n[3] 관리자 전용 라우트에 협력사 접근")
#  ⚠ 예전엔 여기 라우트를 **손으로 적어** 두었다. 그래서 새로 만든 관리자 화면
#    (오늘 할 일·등록조사·감사로그 엑셀·사건 이력)이 목록에 없어 **한 번도 안 눌러졌다**.
#    목록에 없는 문은 검사도 안 된다 — 손목록은 기능이 늘수록 조용히 뒤처진다.
#    그래서 app.py 소스에서 **관리자 게이트가 달린 GET 라우트를 전부 뽑아** 다 두드린다.
#    (import 하지 않는다 — 모듈 최상위 DB.init_db() 가 DB 를 건드린다.)
_src = io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"),
               encoding="utf-8").read()
_admin_eps = []
for _m in re.finditer(r'@app\.get\(\s*"([^"]+)"\s*\)\s*\n\s*@(require_admin|require_role)\b',
                      _src):
    _p = _m.group(1)
    if _p.startswith("/api/partner") or _p.startswith("/api/v1"):
        continue          # 협력사 자기 것 · 발주처 API 키 경로는 별도 검사가 있다
    _admin_eps.append(re.sub(r"<[^>]+>", "1", _p))
_admin_eps = sorted(set(_admin_eps))
chk(len(_admin_eps) >= 7, f"관리자 GET 라우트를 소스에서 뽑았다 — {len(_admin_eps)}개",
    "0개면 정규식이 라우트 서식과 어긋난 것이다(조용히 아무것도 검사 안 함)")
for ep in _admin_eps:
    st, _ = par.go("GET", ep)
    #  ⚠ 404 를 통과로 세면 안 된다. 게이트가 막았다면 **조회 전에** 401/403 이 난다.
    #    404 는 "게이트를 지나 대상을 찾아봤다" 는 뜻이다.
    chk(st in (401, 403), f"★ {ep} 차단", st)

print("\n[4] 내 건은 볼 수 있어야 한다(과잉 차단 확인)")
mine = conn.execute(
    "SELECT id, address FROM cases WHERE partner_id=? AND status IN ('시공중','완료','정산진행') "
    " ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
if mine:
    st, d = par.go("GET", "/api/partner/dashboard")
    mc = [c for c in ((d or {}).get("my_cases") or []) if c.get("id") == mine["id"]]
    chk(bool(mc), "내 낙찰 건이 목록에 있다", len((d or {}).get("my_cases") or []))
    if mc:
        chk(bool((mc[0].get("address") or "").strip()),
            "★ 내 현장 주소는 보인다(시공하려면 필요)", mc[0].get("address"))
    st, d = par.go("GET", f"/api/cases/{mine['id']}/photos")
    chk(st == 200, "내 사건 사진은 열린다", st)

# ── 2차 경매: 남의 실견적은 협력사에게 보이지 않는다 ──────────
#   ⚠ 경쟁 입찰가 비공개와 같은 성격이다. 실견적은 **그 업체의 원가선**이라,
#     공개하면 경쟁사가 그 아래를 겨냥한다(예전엔 −N% 퀵버튼까지 그 값을 기준으로 계산했다).
#     2차의 구속 규칙은 하한(bid_floor)뿐이므로, 판단에 실견적은 필요 없다.
import uuid as _uuid
MARK = _uuid.uuid4().hex[:6].upper()
print("\n[R5] 2차 경매 — 남의 실견적 비공개")
_iid = conn.execute("SELECT id FROM insurers WHERE login_id='insurer'").fetchone()[0]
_pid = conn.execute("SELECT id FROM partners WHERE login_id='partner'").fetchone()[0]
_other = conn.execute(
    "SELECT id, name FROM partners WHERE id<>? AND status='활성' LIMIT 1", (_pid,)).fetchone()
_c2 = conn.execute(
    "INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,est_price,"
    "                  status,created_at) "
    "VALUES(?,?,?,?,?,?,?, '입찰중', datetime('now','+9 hours'))",
    (f"LEAK2-{MARK}", "○○손보", _iid, "유리·샷시·자동문", "서울", "유출검증 2차", 0)).lastrowid
_a2 = conn.execute(
    "INSERT INTO auctions(case_id,status,deadline,created_at) "
    "VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))",
    (_c2,)).lastrowid
SECRET = 7_777_777          # 다른 업체가 낸 실견적 — 이 숫자가 새면 안 된다
conn.execute(
    "INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,"
    "                             engine_low,status,created_at) "
    "VALUES(?,?,?,?,?, '결렬', datetime('now','+9 hours'))",
    (_c2, _other["id"], _other["name"], SECRET, 4_000_000))
conn.commit()

import json as _json
#  ⚠ /api/partner/open-cases 라는 라우트는 없다 — 공고 목록은 대시보드가 함께 내려준다.
for path, label in ((f"/api/cases/{_c2}", "남의 공고 상세"),
                    ("/api/partner/dashboard", "협력사 대시보드")):
    st, d = par.go("GET", path)
    blob = _json.dumps(d, ensure_ascii=False)
    chk(str(SECRET) not in blob and "7,777,777" not in blob,
        f"★ {label}에 남의 실견적 금액이 없다", f"{st}")
    chk('"field_ref": 7777777' not in blob, f"{label} field_ref 미노출")

#  하한(bid_floor)은 규칙이므로 보여야 한다 — 과잉 차단이 아닌지 확인
st, d = par.go("GET", "/api/partner/dashboard")
row = next((x for x in ((d or {}).get("open_cases") or []) if x.get("id") == _c2), None)
chk(row is not None, "2차 공고 자체는 보인다", st)
if row:
    chk(row.get("bid_floor") == 4_000_000,
        "★ 하한은 보인다(표준단가 개산 하단 — 규칙이므로 공개)", row.get("bid_floor"))
    chk(not row.get("field_ref"), "실견적 자리는 비어 있다", row.get("field_ref"))

conn.execute("DELETE FROM field_agreements WHERE case_id=?", (_c2,))
conn.execute("DELETE FROM auctions WHERE id=?", (_a2,))
conn.execute("DELETE FROM cases WHERE id=?", (_c2,))
conn.commit()

conn.close()
print(f"\n  통과 {ok} · 유출/이상 {fail}")
sys.exit(1 if fail else 0)
