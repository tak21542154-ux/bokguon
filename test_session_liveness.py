# -*- coding: utf-8 -*-
"""5라운드 회귀 — 세션 생존 확인 · 2차 하한 소급 실격 차단.

  ⚠ 계정 생존 확인은 **정상 사용자를 막으면 안 된다**. 그것부터 본다.
"""
import os, sys, json, uuid, sqlite3
import urllib.request, http.cookiejar

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bokguon.db")
MARK = "R5" + uuid.uuid4().hex[:5].upper()


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
            d = raw[:160]
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


MARK_PREFIX = MARK if isinstance(MARK, str) else 'sess'
adm, ins, par = C(), C(), C()
chk(adm.go("POST", "/api/login", {"username": "admin",
    "password": os.environ["BOKGUON_TEST_ADMIN_PW"]})[0] == 200, "관리자 로그인")
chk(ins.go("POST", "/api/insurer/login", {"login_id": "insurer",
    "password": os.environ["BOKGUON_TEST_INSURER_PW"]})[0] == 200, "보험사 로그인")
chk(par.go("POST", "/api/partner/login", {"login_id": "partner",
    "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})[0] == 200, "협력사 로그인")

conn = sqlite3.connect(DBP); conn.row_factory = sqlite3.Row
iid = conn.execute("SELECT id FROM insurers WHERE login_id='insurer'").fetchone()[0]
pid = conn.execute("SELECT id FROM partners WHERE login_id='partner'").fetchone()[0]

# ── ① 정상 사용자는 그대로 쓴다 (과잉 차단이 아닌지 — 가장 중요) ──
print("\n[1] 정상 사용자 통과 (회귀 방지)")
for who, cl, ep in (("관리자", adm, "/api/dashboard"),
                    ("보험사", ins, "/api/insurer/dashboard"),
                    ("협력사", par, "/api/partner/dashboard")):
    st, _ = cl.go("GET", ep)
    chk(st == 200, f"★ {who}는 막히지 않는다", st)
#  연속 호출에도 세션이 유지되는지(생존 확인이 세션을 건드리지 않는다)
for _ in range(3):
    st, _ = adm.go("GET", "/api/dashboard")
chk(st == 200, "★ 반복 호출에도 세션 유지", st)
#  /me 3형제도 정상일 때는 그대로 통과해야 한다(아래 [2]에서 죽었을 때를 본다)
for who, cl, ep in (("관리자", adm, "/api/me"),
                    ("보험사", ins, "/api/insurer/me"),
                    ("협력사", par, "/api/partner/me")):
    st, _ = cl.go("GET", ep)
    chk(st == 200, f"★ {who} /me 는 정상일 때 막히지 않는다(과잉 차단 아님)", st)

# ── ② 퇴출·해지가 즉시 먹는다 ────────────────────────────────
print("\n[2] 상태 변경이 살아있는 세션에 즉시 반영")
old_p = conn.execute("SELECT status FROM partners WHERE id=?", (pid,)).fetchone()[0]
conn.execute("UPDATE partners SET status='퇴출' WHERE id=?", (pid,)); conn.commit()
st, r = par.go("GET", "/api/partner/dashboard")
chk(st == 401, "★ 퇴출된 협력사는 즉시 차단(재로그인 없이도)", f"{st} {r}")
#  ⚠ 실측(2026-08-21): /api/partner/me 만 _account_alive() 를 안 불러, 퇴출된
#    협력사도 이 엔드포인트에서는 계속 200 + 새 CSRF 를 받았다 — 다른 모든
#    관문의 "행 없음/차단 → 401" 계약과 어긋났다. 죽은 세션이 여전히 살아
#    있는 window 안에서 같이 확인한다(로그인을 추가로 안 써도 된다).
st_me, r_me = par.go("GET", "/api/partner/me")
chk(st_me == 401, "★★★ /api/partner/me 도 즉시 차단된다(실측 결함 재현·수정 확인)",
    f"{st_me} {r_me}")
conn.execute("UPDATE partners SET status=? WHERE id=?", (old_p, pid)); conn.commit()
#  되돌려도 세션이 지워졌으므로 재로그인해야 한다 — 그게 맞는 동작
st, _ = par.go("POST", "/api/partner/login",
               {"login_id": "partner", "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})
chk(st == 200, "복구 후 재로그인 가능", st)
st, _ = par.go("GET", "/api/partner/dashboard")
chk(st == 200, "복구 후 정상 이용", st)

old_i = conn.execute("SELECT status FROM insurers WHERE id=?", (iid,)).fetchone()[0]
conn.execute("UPDATE insurers SET status='해지' WHERE id=?", (iid,)); conn.commit()
st, _ = ins.go("GET", "/api/insurer/dashboard")
chk(st == 401, "★ 계약 해지된 보험사도 즉시 차단", st)
st_me, r_me = ins.go("GET", "/api/insurer/me")
chk(st_me == 401, "★★★ /api/insurer/me 도 즉시 차단된다(실측 결함 재현·수정 확인)",
    f"{st_me} {r_me}")
conn.execute("UPDATE insurers SET status=? WHERE id=?", (old_i, iid)); conn.commit()
ins.go("POST", "/api/insurer/login",
       {"login_id": "insurer", "password": os.environ["BOKGUON_TEST_INSURER_PW"]})

# ── ②-2 비밀번호 재발급이 살아있는 세션을 끊는다 ────────────
#  ⚠ 운영자가 '침해가 의심된다'며 누르는 바로 그 버튼이다. 종전에는 해시만
#    갈릴 뿐 세션은 그대로여서, 그 사람이 계속 쓰고 있었다.
print("\n[2-2] 비밀번호 재발급 즉시 반영")
old_h = conn.execute("SELECT password_hash FROM partners WHERE id=?", (pid,)).fetchone()[0]
conn.execute("UPDATE partners SET password_hash=? WHERE id=?",
             (old_h[:-4] + "beef", pid))
conn.commit()
st, r = par.go("GET", "/api/partner/dashboard")
chk(st == 401, "★ 비밀번호가 바뀌면 그 세션이 즉시 끊긴다", f"{st} {r}")
chk("비밀번호" in str(r), "  이유를 말해 준다(재로그인 안내)", str(r)[:60])
conn.execute("UPDATE partners SET password_hash=? WHERE id=?", (old_h, pid))
conn.commit()
par.go("POST", "/api/partner/login",
       {"login_id": "partner", "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})
st, _ = par.go("GET", "/api/partner/dashboard")
chk(st == 200, "원복 후 재로그인하면 정상", st)

# ── ②-3 하위계정 세션 — **과잉 차단이 아닌지**가 핵심 ────────
#  ⚠ 실제로 겪은 회귀(2026-08-06): 세션 지문을 하위계정에도 넣었는데 판정은
#    원계정 해시로 해서, 하위계정은 로그인 직후 모든 요청이 401 이 됐다.
#    '막아야 할 것을 막는가'만 보면 이 결함은 안 잡힌다 —
#    **막지 말아야 할 것을 통과시키는가**를 함께 봐야 한다.
print("\n[2-3] 하위계정 세션 (과잉 차단 회귀 방지)")
SUB_ID = f"{MARK_PREFIX}sub"
#  ⚠ 중간에 실패해도 **반드시** 치운다. 안 치우면 다음 실행이 같은 아이디로
#    발급을 시도하다 막히고, 그게 코드 결함처럼 보인다(실제로 그랬다).
import atexit as _atexit


def _cleanup_sub():
    try:
        c2 = sqlite3.connect(DBP)
        c2.execute("DELETE FROM portal_users WHERE LOWER(login_id)=LOWER(?)", (SUB_ID,))
        c2.commit(); c2.close()
    except Exception:
        pass


_atexit.register(_cleanup_sub)
st, r = par.go("POST", "/api/partner/subaccounts",
               {"login_id": SUB_ID, "name": "검증담당", "role": "하위관리자"})
if st == 200 and (r or {}).get("temp_password"):
    sub = C()
    _tmp = r["temp_password"]
    st, _ = sub.go("POST", "/api/partner/login", {"login_id": SUB_ID, "password": _tmp})
    chk(st == 200, "하위계정 로그인", st)
    #  발급 직후에는 비밀번호 변경이 강제된다 — 실제 첫 로그인 흐름대로 바꾼다.
    #  (이걸 안 하면 이후 요청이 403 이라, 세션 판정 결함을 가린다)
    sub.go("POST", "/api/change-password", {"current": _tmp, "new": "Sv7#qLm2Wz!vQr9T"})
    st, d = sub.go("GET", "/api/partner/dashboard")
    chk(st == 200, "★ 하위계정도 조회가 된다(원계정 해시로 판정하면 여기서 401)", st)
    for _ in range(3):
        st, _ = sub.go("GET", "/api/partner/dashboard")
    chk(st == 200, "★ 반복 호출에도 유지", st)
    #  삭제하면 그 세션은 끊겨야 한다
    #  ⚠ 먼저 커밋해 **읽기 스냅샷을 새로 연다.** 이 연결은 계속 열려 있어서
    #    서버가 방금 만든 행을 못 보고 지나갈 수 있다(그러면 검사가 조용히 건너뛴다).
    conn.commit()
    _sid = conn.execute("SELECT id FROM portal_users WHERE LOWER(login_id)=LOWER(?)",
                        (SUB_ID,)).fetchone()
    if not _sid:
        chk(False, "하위계정 행 조회(삭제 검사를 위해)", "portal_users 에서 못 찾음")
    if _sid:
        conn.execute("DELETE FROM portal_users WHERE id=?", (_sid[0],)); conn.commit()
        st, r2 = sub.go("GET", "/api/partner/dashboard")
        chk(st == 401, "★ 하위계정을 지우면 열린 세션이 즉시 끊긴다", f"{st} {r2}")
else:
    chk(False, "하위계정 발급", f"{st} {r}")
try:
    conn.execute("DELETE FROM portal_users WHERE LOWER(login_id)=LOWER(?)", (SUB_ID,))
    conn.commit()
except sqlite3.Error:
    pass

# ── ②-4 관리자 계정도 지워지면 /api/me 가 즉시 끊는다 ──────────
#  ⚠ admins 는 "삭제=탈퇴"라 실제 DELETE 를 쓴다(1의 admins 스키마 참고). 진짜
#    admin 계정을 지우면 나머지 파일 전부가 그 로그인에 기대므로, **이름을
#    잠깐 바꿔치기**해 "행 없음"과 완전히 같은 조건을 만든다(_account_alive
#    는 username 으로 재조회하므로 이걸로 충분하다). 실패해도 finally 로
#    반드시 원래 이름으로 되돌린다.
print("\n[2-4] 관리자 계정 소멸도 /api/me 를 즉시 끊는가")
try:
    conn.execute("UPDATE admins SET username='__gone_temp__' WHERE username='admin'")
    conn.commit()
    st_me, r_me = adm.go("GET", "/api/me")
    chk(st_me == 401, "★★★ 관리자 계정이 사라지면 /api/me 도 즉시 차단된다"
        "(실측 결함 재현·수정 확인)", f"{st_me} {r_me}")
finally:
    conn.execute("UPDATE admins SET username='admin' WHERE username='__gone_temp__'")
    conn.commit()
st, _ = adm.go("POST", "/api/login",
               {"username": "admin", "password": os.environ["BOKGUON_TEST_ADMIN_PW"]})
chk(st == 200, "복구 후 재로그인 가능(관리자)", st)

# ── ③ 2차 경매 하한을 올려 기존 입찰을 실격시킬 수 없다 ────────
print("\n[3] 2차 하한 소급 실격 차단")
cid = conn.execute(
    """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,est_price,
                         status,low_price,created_at)
       VALUES(?,?,?,?,?,?,?,'입찰중',?,datetime('now','+9 hours'))""",
    (f"{MARK}-1", "○○손보", iid, "유리·샷시·자동문", "서울", "하한검증",
     5_000_000, 5_500_000)).lastrowid
#  부동의 실견적을 넣어 2차로 만든다
conn.execute("""INSERT INTO field_agreements(case_id,partner_id,field_amount,status,created_at)
                VALUES(?,?,?,'결렬',datetime('now','+9 hours'))""", (cid, pid, 6_000_000))
conn.execute("""INSERT INTO auctions(case_id,status,deadline,created_at)
                VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
             (cid,))
conn.commit()

st, r = adm.go("PATCH", f"/api/cases/{cid}", {"est_price": 6_000_000})
chk(st == 409 and (r or {}).get("code") == "FLOOR_ABOVE_BID",
    "★ 하한을 최저입찰 위로 올리면 거부(소급 실격 방지)", f"{st} {r}")
chk(conn.execute("SELECT est_price FROM cases WHERE id=?", (cid,)).fetchone()[0] == 5_000_000,
    "가견적이 그대로 유지", None)
st, r = adm.go("PATCH", f"/api/cases/{cid}", {"est_price": 4_500_000})
chk(st == 200, "★ 하한을 내리는 것은 허용(기존 입찰에 해가 없다)", f"{st} {r}")

#  1차는 종전대로 — 상한을 "이미 들어온 최고 입찰가" 아래로 못 내린다
#  ⚠ [라운드86] 이 가드는 low_price 가 아니라 MAX(bid) 를 본다 — 입찰이
#    없으면 애초에 소급 실격시킬 게 없으므로 인하가 막히지 않는다(아래 companion).
cid2 = conn.execute(
    """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,est_price,
                         status,low_price,created_at)
       VALUES(?,?,?,?,?,?,?,'입찰중',?,datetime('now','+9 hours'))""",
    (f"{MARK}-2", "○○손보", iid, "유리·샷시·자동문", "서울", "상한검증",
     3_000_000, 0)).lastrowid
aid2 = conn.execute("""INSERT INTO auctions(case_id,status,deadline,created_at)
                VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
             (cid2,)).lastrowid
conn.execute("""INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
                VALUES(?,?,'검증업체',?,10,datetime('now','+9 hours'))""", (aid2, pid, 2_500_000))
conn.commit()
st, r = adm.go("PATCH", f"/api/cases/{cid2}", {"est_price": 2_000_000})
chk(st == 409 and (r or {}).get("code") == "CAP_BELOW_BID",
    "★ 1차는 최고 입찰가(250만)보다 낮게 상한을 못 내린다", f"{st} {r}")

#  입찰이 전혀 없으면 막을 게 없다 — 라운드86이 의도한 대로 인하가 허용된다
conn.execute("DELETE FROM bids WHERE auction_id=?", (aid2,))
conn.commit()
st, r = adm.go("PATCH", f"/api/cases/{cid2}", {"est_price": 2_000_000})
chk(st == 200, "★ 입찰이 없는 1차는 같은 금액으로 내려도 막히지 않는다(라운드86)", f"{st} {r}")

for x in (cid, cid2):
    conn.execute("DELETE FROM bids WHERE auction_id IN (SELECT id FROM auctions WHERE case_id=?)", (x,))
    conn.execute("DELETE FROM auctions WHERE case_id=?", (x,))
    conn.execute("DELETE FROM field_agreements WHERE case_id=?", (x,))
    conn.execute("DELETE FROM cases WHERE id=?", (x,))
conn.commit(); conn.close()
print(f"\n  통과 {ok} · 실패 {fail}   (검증 데이터 정리됨)")
sys.exit(1 if fail else 0)
