# -*- coding: utf-8 -*-
"""3라운드 스캔 수정 회귀 — 추천 가중치 정합 · 계좌 미등록 조기 고지.

  두 가지 모두 "화면이 사실과 다른 말을 한다"는 같은 병이다.
   ① 보험사가 보는 가중치 설명이 **실제 점수를 낸 값**과 달랐다
      → 복구온이 설정을 바꾸면 보험사는 모르는 채 추천을 믿게 된다(철칙: 승인은 보험사 단독).
   ② 지급 계좌가 없다는 사실을 **공사가 끝난 정산 단계**에서야 알려 줬다
      → 그때는 자재비·인건비가 이미 나간 뒤다.
"""
import os, sys, json, uuid, sqlite3, atexit
import urllib.request, urllib.error, urllib.parse, http.cookiejar

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "verify.db")
MARK = "R6" + uuid.uuid4().hex[:5].upper()


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
            r = self.op.open(req, timeout=25)
            st, raw = r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, raw = e.code, e.read().decode("utf-8", "replace")
        try:
            d = json.loads(raw)
        except Exception:
            d = raw[:200]
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
        return st, d


ok = fail = 0


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  [OK]   {name}")
    else:
        fail += 1; print(f"  [FAIL] {name}   {got}")


ins, par = C(), C()
chk(ins.go("POST", "/api/insurer/login", {"login_id": "insurer",
    "password": os.environ["BOKGUON_TEST_INSURER_PW"]})[0] == 200, "보험사 로그인")
chk(par.go("POST", "/api/partner/login", {"login_id": "partner",
    "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})[0] == 200, "협력사 로그인")

conn = sqlite3.connect(DBP); conn.row_factory = sqlite3.Row
iid = conn.execute("SELECT id FROM insurers WHERE login_id='insurer'").fetchone()[0]
pid = conn.execute("SELECT id FROM partners WHERE login_id='partner'").fetchone()[0]
pname = conn.execute("SELECT name FROM partners WHERE id=?", (pid,)).fetchone()[0]

# ── ① 보험사가 보는 가중치 = 실제 점수를 낸 가중치 ─────────────
print("\n[1] 추천 가중치 정합 (보험사 화면 ↔ 실제 계산)")
cid = conn.execute(
    """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,est_price,
                         status,created_at)
       VALUES(?,?,?,?,?,?,?,'입찰중',datetime('now','+9 hours'))""",
    (f"{MARK}-W", "○○손보", iid, "유리·샷시·자동문", "서울", "가중치검증",
     5_000_000)).lastrowid
aid = conn.execute(
    """INSERT INTO auctions(case_id,status,deadline,created_at)
       VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
    (cid,)).lastrowid
#  ⚠⚠ [라운드555] 두 입찰을 전부 같은 partner_id(pid)로 넣었었다 — round424가
#    세운 부분 UNIQUE 인덱스(idx_bids_active_partner, db.py: ON bids(auction_id,
#    partner_id) WHERE voided_at IS NULL)가 같은 협력사·같은 경매의 두 번째
#    활성 입찰 INSERT를 IntegrityError로 거부해 이 픽스처 자체가 깨져 있었다
#    (실측 재현: 두 번째 INSERT에서 그대로 죽음). 실제 API도 재투찰은 UPDATE로
#    처리해 한 업체당 활성 입찰이 항상 1건뿐이므로(api_partner_bid), "한 업체가
#    같은 경매에 입찰을 두 번"인 이 픽스처는 애초에 현실에 없는 상태였다 —
#    round424(이 인덱스를 세운 라운드)보다 먼저 쓰인 이 파일만 못 따라왔다.
#    서로 다른 두 업체의 입찰로 바꾼다 — 바로 아래 가중치 재계산 검증은
#    입찰이 여럿이기만 하면 되고 두 번째 업체가 누구인지는 안 본다.
p2name = f"{MARK}-업체2"
pid2 = conn.execute(
    """INSERT INTO partners(name,status,partner_type,region,rating,jobs_done)
       VALUES(?,'활성','시행사','서울',4.5,10)""", (p2name,)).lastrowid
for _pid, _pname, amt, dys in ((pid, pname, 4_200_000, 5), (pid2, p2name, 4_600_000, 3)):
    conn.execute("""INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
                    VALUES(?,?,?,?,?,datetime('now','+9 hours'))""",
                 (aid, _pid, _pname, amt, dys))
conn.commit()

st, r = ins.go("GET", f"/api/insurer/cases/{cid}/bids")
chk(st == 200 and r.get("bids"), "입찰 목록 조회", st)
w0 = (r or {}).get("weights") or {}
chk(abs(sum(w0.values()) - 1.0) < 0.01, "가중치 합이 1", sum(w0.values()))
chk(r.get("weights_default") is True, "기본 설정에서는 default 플래그 참", r.get("weights_default"))

#  복구온이 설정에서 가중치를 바꾼다 — 가격 비중을 크게 낮춘다
old = conn.execute("SELECT value FROM settings WHERE key='bid_w_price'").fetchone()


def _restore_weight():
    """⚠ 스크립트가 **어떻게 끝나든** 설정을 되돌린다.

      예전에는 원복이 본문 끝에만 있었다. 로그인 레이트리밋에 걸려 중간에
      죽자 bid_w_price=0.05 가 그대로 남았고, 다음 실행이 그 오염된 설정 때문에
      '가중치가 안 바뀐다'며 실패했다 — 코드는 멀쩡한데 테스트가 거짓말을 했다.
    """
    try:
        c2 = sqlite3.connect(DBP)
        if old:
            c2.execute("UPDATE settings SET value=? WHERE key='bid_w_price'", (old[0],))
        else:
            c2.execute("DELETE FROM settings WHERE key='bid_w_price'")
        c2.commit(); c2.close()
    except Exception:
        pass


atexit.register(_restore_weight)
conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('bid_w_price','0.05')")
conn.commit()
st, r2 = ins.go("GET", f"/api/insurer/cases/{cid}/bids")
w1 = (r2 or {}).get("weights") or {}
chk(st == 200 and w1.get("price") is not None, "변경 후 조회", st)
chk(w1.get("price", 1) < w0.get("price", 0),
    "★ 설정을 바꾸면 보험사에 내려가는 가중치도 함께 바뀐다(고정값 아님)",
    f"{w0.get('price')} → {w1.get('price')}")
chk(r2.get("weights_default") is False,
    "★ 기본값에서 조정됐다는 사실을 보험사에 알린다", r2.get("weights_default"))
#  점수도 실제로 그 가중치로 계산됐는지 — 가격 비중이 죽으면 순위가 뒤집힌다
top0 = r["bids"][0]["amount"]; top1 = r2["bids"][0]["amount"]
chk(top0 != top1 or r["bids"][0]["score"] != r2["bids"][0]["score"],
    "★ 화면 설명만이 아니라 점수 자체가 새 가중치로 계산된다",
    f"{r['bids'][0]['score']} → {r2['bids'][0]['score']}")

#  정상 종료 경로의 원복(atexit 와 중복이지만 멱등이다 — 빠른 원복이 낫다)
if old:
    conn.execute("UPDATE settings SET value=? WHERE key='bid_w_price'", (old[0],))
else:
    conn.execute("DELETE FROM settings WHERE key='bid_w_price'")
conn.commit()

# ── ② 계좌 미등록을 첫 화면에서 알린다 ────────────────────────
print("\n[2] 지급 계좌 미등록 조기 고지")
row = conn.execute("SELECT bank_account_enc, bank_holder FROM partners WHERE id=?",
                   (pid,)).fetchone()
st, d = par.go("GET", "/api/partner/dashboard")
chk(st == 200 and "acct_ready" in d, "★ 대시보드가 계좌 등록 여부를 내려준다", st)
chk(d.get("acct_ready") is bool(
    (row["bank_account_enc"] or "").strip() and (row["bank_holder"] or "").strip()),
    "현재 계좌 상태와 일치", d.get("acct_ready"))

#  계좌를 지운 상태로 만들면 acct_ready 가 False 로 바뀐다
conn.execute("UPDATE partners SET bank_account_enc=NULL WHERE id=?", (pid,)); conn.commit()
st, d2 = par.go("GET", "/api/partner/dashboard")
chk(st == 200 and d2.get("acct_ready") is False,
    "★ 계좌가 없으면 정산 전에 곧바로 False", d2.get("acct_ready"))
conn.execute("UPDATE partners SET bank_account_enc=? WHERE id=?",
             (row["bank_account_enc"], pid)); conn.commit()
st, d3 = par.go("GET", "/api/partner/dashboard")
chk(d3.get("acct_ready") == d.get("acct_ready"), "원복 확인", d3.get("acct_ready"))

# ── ③ 발송대기함에 수신자 연락처가 붙는다 ──────────────────
print("\n[3] 발송대기함 — 전화로 알릴 수 있는가")
adm = C()
chk(adm.go("POST", "/api/login", {"username": "admin",
    "password": os.environ["BOKGUON_TEST_ADMIN_PW"]})[0] == 200, "관리자 로그인")
nid = conn.execute(
    """INSERT INTO notifications(ntype,channel,target,message,status,partner_id,
                                 audience_type,created_at)
       VALUES('낙찰','알림톡',?,?,'발송대기',?, 'partner', datetime('now','+9 hours'))""",
    (pname, f"{MARK} 연락처 검증", pid)).lastrowid
conn.commit()
st, d = adm.go("GET", "/api/outbox?days=1&status="
               + urllib.parse.quote("발송대기"))
row = next((x for x in (d.get("items") or []) if x.get("id") == nid), None)
chk(st == 200 and row is not None, "발송대기함 조회", st)
if row:
    want = (conn.execute("SELECT phone FROM partners WHERE id=?", (pid,)).fetchone()[0] or "").strip()
    chk(row.get("to_phone") == want,
        "★ 화면이 '전화로 처리하세요'라고 하면 번호도 함께 준다", f"{row.get('to_phone')!r} vs {want!r}")
    chk(row.get("to_name"), "수신자 이름도 함께", row.get("to_name"))
conn.execute("DELETE FROM notifications WHERE id=?", (nid,))

conn.execute("DELETE FROM bids WHERE auction_id=?", (aid,))
conn.execute("DELETE FROM auctions WHERE id=?", (aid,))
conn.execute("DELETE FROM cases WHERE id=?", (cid,))
conn.execute("DELETE FROM partners WHERE id=?", (pid2,))
conn.commit(); conn.close()
print(f"\n  통과 {ok} · 실패 {fail}   (검증 데이터 정리됨)")
sys.exit(1 if fail else 0)
