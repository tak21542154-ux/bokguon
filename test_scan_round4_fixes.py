# -*- coding: utf-8 -*-
"""4라운드 스캔 수정 회귀 — 낙찰 덮어쓰기 · 등급 강제 · 절감 기준선 · 경쟁가 누출.

  이 파일이 지키는 것은 전부 **한 번 뚫리면 되돌릴 수 없는** 것들이다.
   ① 보험사의 뒤늦은 1차합의 승인이 이미 시공 중인 업체를 덮어쓰지 못한다
   ② '조회' 등급 계정이 낙찰 승인·입찰 제출을 못 한다(화면이 약속한 경계를 서버가 지킨다)
   ③ 관리자 강등이 세션에 즉시 먹는다
   ④ 2차 경매 건의 절감이 0/음수로 뭉개지지 않는다(보험사에 나가는 명세서)
   ⑤ 입찰 응답이 경쟁 최저가에 대한 부등식을 흘리지 않는다
"""
import os
import sys
import json
import uuid
import sqlite3
import urllib.request
import urllib.error
import urllib.parse
import http.cookiejar
import atexit

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "verify.db")
MARK = "R7" + uuid.uuid4().hex[:5].upper()


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
            d = raw[:250]
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
        return st, d


ok = fail = 0


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK]   {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name}   {got}")


adm, ins, par = C(), C(), C()
chk(adm.go("POST", "/api/login", {"username": "admin",
    "password": os.environ["BOKGUON_TEST_ADMIN_PW"]})[0] == 200, "관리자 로그인")
chk(ins.go("POST", "/api/insurer/login", {"login_id": "insurer",
    "password": os.environ["BOKGUON_TEST_INSURER_PW"]})[0] == 200, "보험사 로그인")
chk(par.go("POST", "/api/partner/login", {"login_id": "partner",
    "password": os.environ["BOKGUON_TEST_PARTNER_PW"]})[0] == 200, "협력사 로그인")

conn = sqlite3.connect(DBP)
conn.row_factory = sqlite3.Row
iid = conn.execute("SELECT id FROM insurers WHERE login_id='insurer'").fetchone()[0]
pid = conn.execute("SELECT id FROM partners WHERE login_id='partner'").fetchone()[0]
pname = conn.execute("SELECT name FROM partners WHERE id=?", (pid,)).fetchone()[0]
cleanup = []
sub_logins = []


def _cleanup():
    """⚠ 스크립트가 **어떻게 끝나든** 검증 데이터를 지운다.

      본문 끝에만 정리를 두면, 레이트리밋·예외로 중간에 죽었을 때
      검증용 사건·계정이 DB 에 남는다. 다음 실행이 그 잔재 때문에
      엉뚱하게 실패하고, 운영자가 화면에서 그 사건을 보고 놀란다.
    """
    try:
        c2 = sqlite3.connect(DBP)
        for x in cleanup:
            c2.execute("DELETE FROM bids WHERE auction_id IN "
                       "(SELECT id FROM auctions WHERE case_id=?)", (x,))
            for t in ("auctions", "field_agreements", "photos", "work_lots",
                      "notifications", "defects"):
                c2.execute(f"DELETE FROM {t} WHERE case_id=?", (x,))
            c2.execute("DELETE FROM cases WHERE id=?", (x,))
        for lg in sub_logins:
            c2.execute("DELETE FROM portal_users WHERE login_id=?", (lg,))
        c2.execute("DELETE FROM settings WHERE key='low_price_alert'")
        c2.commit(); c2.close()
    except Exception:
        pass


atexit.register(_cleanup)


def mkcase(no, status="접수", est=3_000_000, **extra):
    cols = "case_no,insurer,insurer_id,category,region,address,est_price,status,created_at"
    vals = "?,?,?,?,?,?,?,?,datetime('now','+9 hours')"
    args = [no, "○○손보", iid, "유리·샷시·자동문", "서울", "R4검증", est, status]
    for k, v in extra.items():
        cols += f",{k}"
        vals += ",?"
        args.append(v)
    cid = conn.execute(f"INSERT INTO cases({cols}) VALUES({vals})", args).lastrowid
    cleanup.append(cid)
    return cid


# ── ① 낙찰 덮어쓰기 차단 ──────────────────────────────────────
print("\n[1] 뒤늦은 1차합의 승인이 시공 중인 업체를 덮어쓰지 못한다")
cid = mkcase(f"{MARK}-A", status="시공중", partner_id=pid, partner_name=pname,
             award_amount=2_800_000)
#  다른 업체가 올린 '검토중' 합의가 매달려 있다
other = conn.execute(
    "SELECT id, name FROM partners WHERE id<>? AND status='활성' LIMIT 1", (pid,)).fetchone()
aid = conn.execute(
    """INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,status,created_at)
       VALUES(?,?,?,?, '검토중', datetime('now','+9 hours'))""",
    (cid, other["id"], other["name"], 9_900_000)).lastrowid
conn.commit()

st, r = ins.go("POST", f"/api/insurer/cases/{cid}/field-agreement/decision", {"approve": True})
row = conn.execute("SELECT status, partner_id, award_amount FROM cases WHERE id=?", (cid,)).fetchone()
chk(row["partner_id"] == pid and row["award_amount"] == 2_800_000,
    "★ 시공 중인 업체·낙찰금액이 그대로 유지된다",
    f"partner={row['partner_id']} amount={row['award_amount']} resp={st} {r}")
chk(st >= 400, "★ 승인 요청 자체가 거부된다", f"{st} {r}")
conn.execute("DELETE FROM field_agreements WHERE id=?", (aid,))
conn.commit()

#  2차 경매를 열면 검토중 합의가 함께 닫힌다
cid2 = mkcase(f"{MARK}-B", status="접수")
aid2 = conn.execute(
    """INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,status,created_at)
       VALUES(?,?,?,?, '검토중', datetime('now','+9 hours'))""",
    (cid2, pid, pname, 5_000_000)).lastrowid
conn.execute("""INSERT INTO photos(case_id,rel_path,kind,uploader_role,created_at)
                VALUES(?,?,?,?,datetime('now','+9 hours'))""",
             (cid2, "verify/dummy.jpg", "착공전", "협력사"))
conn.commit()
st, r = adm.go("POST", f"/api/cases/{cid2}/open-auction", {"est_basis": "현장 사진 확보 완료 — 검증용"})
after = conn.execute("SELECT status FROM field_agreements WHERE id=?", (aid2,)).fetchone()[0]
chk(st == 200, "2차 경매 개시", f"{st} {r}")
chk(after == "결렬",
    "★ 2차 경매를 열면 검토중 합의가 함께 닫힌다(대기열에 유령이 안 남는다)", after)

#  보험사 대기열에도 안 보인다
st, d = ins.go("GET", "/api/insurer/dashboard")
ids = [x["id"] for x in (d.get("field_agreements") or [])]
chk(aid2 not in ids, "★ 보험사 승인 대기열에서 사라진다", ids[:5])

# ── ② 포털 하위계정 등급이 서버에서 강제된다 ──────────────────
print("\n[2] '조회' 등급 계정은 돈을 확정하지 못한다")
sub_ins = C()
sub_login = f"vsub{MARK.lower()}"
sub_logins.append(sub_login)
st, r = ins.go("POST", "/api/insurer/subaccounts",
               {"login_id": sub_login, "name": "검증조회", "role": "하위관리자"})
if st != 200:
    chk(False, "하위계정 발급", f"{st} {r}")
else:
    tmp = r.get("temp_password") or r.get("password")
    chk(bool(tmp), "하위계정 발급(임시 비밀번호 수령)", r)
    st, _ = sub_ins.go("POST", "/api/insurer/login",
                       {"login_id": sub_login, "password": tmp})
    chk(st == 200, "하위계정 로그인", st)
    #  최초 로그인 비밀번호 변경이 걸리면 조회는 되지 않으니, 변경까지 마친다
    if st == 200:
        sub_ins.go("POST", "/api/change-password", {"current": tmp, "new": "Vf7#qLm2Wz!vQr9T"})
    st, d = sub_ins.go("GET", "/api/insurer/dashboard")
    chk(st == 200, "하위계정도 조회는 된다(과잉 차단이 아니다)", st)
    chk((d.get("me") or {}).get("portal_role") == "하위관리자",
        "화면이 등급을 알 수 있다", (d.get("me") or {}).get("portal_role"))
    for path, label in (
            (f"/api/insurer/cases/{cid2}/award", "낙찰 승인"),
            (f"/api/insurer/cases/{cid2}/cancel", "사건 취소"),
            (f"/api/insurer/cases/{cid2}/reject-bids", "전부 반려")):
        st, r = sub_ins.go("POST", path, {"bid_id": 1, "reason": "검증"})
        chk(st == 403 and (r or {}).get("code") == "PORTAL_FORBIDDEN",
            f"★ 조회 계정은 {label}을 못 한다", f"{st} {r}")

#  협력사 쪽도 같은 게이트인지 **추론하지 않고 직접 확인한다**
#   (회사 명의 입찰가를 권한 없는 직원이 내면 그 회사가 이행 의무를 진다)
sub_par = C()
psub = f"pvs{MARK.lower()}"
sub_logins.append(psub)
st, r = par.go("POST", "/api/partner/subaccounts",
               {"login_id": psub, "name": "현장조회", "role": "하위관리자"})
if st != 200:
    chk(False, "협력사 하위계정 발급", f"{st} {r}")
else:
    tmp = r.get("temp_password")
    st, _ = sub_par.go("POST", "/api/partner/login", {"login_id": psub, "password": tmp})
    if st == 200:
        sub_par.go("POST", "/api/change-password", {"current": tmp, "new": "Pv7#qLm2Wz!vQr9T"})
    st, d = sub_par.go("GET", "/api/partner/dashboard")
    chk(st == 200, "협력사 하위계정도 조회는 된다", st)
    chk((d.get("me") or {}).get("portal_role") == "하위관리자",
        "협력사 화면도 등급을 안다", (d.get("me") or {}).get("portal_role"))
    st, r = sub_par.go("POST", "/api/partner/bids",
                       {"case_id": cid2, "amount": 1_000_000, "days": 5})
    chk(st == 403 and (r or {}).get("code") == "PORTAL_FORBIDDEN",
        "★ 조회 계정은 회사 명의로 입찰가를 못 낸다", f"{st} {r}")

# ── ③ 관리자 강등이 세션에 즉시 먹는다 ────────────────────────
print("\n[3] 강등이 살아 있는 세션에 즉시 반영")
old_role = conn.execute("SELECT role FROM admins WHERE username='admin'").fetchone()[0]
#  ⚠ 여기서 죽으면 **관리자가 하위관리자로 남아** 콘솔에서 아무것도 못 하게 된다.
atexit.register(lambda: sqlite3.connect(DBP).execute(
    "UPDATE admins SET role=? WHERE username='admin'", (old_role,)).connection.commit())
st, _ = adm.go("GET", "/api/dashboard")
chk(st == 200, "강등 전에는 정상 이용", st)
conn.execute("UPDATE admins SET role='하위관리자' WHERE username='admin'")
conn.commit()
st, r = adm.go("DELETE", f"/api/partners/{pid}")     # 중간관리자 이상만
chk(st == 403, "★ 강등되면 즉시 상위 권한이 막힌다(재로그인 없이도)", f"{st} {r}")
st, _ = adm.go("GET", "/api/dashboard")
chk(st == 200, "강등돼도 조회는 그대로 된다(과잉 차단 아님)", st)
conn.execute("UPDATE admins SET role=? WHERE username='admin'", (old_role,))
conn.commit()
st, _ = adm.go("GET", "/api/dashboard")
chk(st == 200, "원복 확인", st)

# ── ④ 2차 경매 절감 기준선 ────────────────────────────────────
print("\n[4] 2차 경매 건의 절감이 0/음수로 뭉개지지 않는다")
cid3 = mkcase(f"{MARK}-C", status="완료", est=3_000_000,
              award_amount=4_800_000, low_price=4_800_000,
              completed_at="2026-08-01 10:00:00")
conn.execute("""INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,
                                             engine_high,status,created_at)
                VALUES(?,?,?,?,?,'결렬',datetime('now','+9 hours'))""",
             (cid3, pid, pname, 5_000_000, 6_000_000))
conn.commit()
st, data = adm.go("GET", "/api/cases?" + urllib.parse.urlencode({"q": f"{MARK}-C"}))
row = next((x for x in (data if isinstance(data, list) else []) if x["case_no"] == f"{MARK}-C"), None)
chk(row is not None, "사건 목록 조회", st)
if row:
    chk(row.get("saving_base") == 6_000_000,
        "★ 2차 기준선 = 표준단가 개산 상단(가견적이 아니다)", row.get("saving_base"))
    chk(row.get("saving", 0) > 0,
        "★ 절감률이 양수로 나온다(예전에는 -60%였다가 화면에서 '-'로 사라졌다)",
        row.get("saving"))

# ── ④-2 사진 없이 완료 보고가 안 된다 ─────────────────────────
#   ⚠ 완료 보고를 누르는 순간 보험사·피해자에게 통지가 나가고, 그 시각이
#     하자보증 24개월 기산점으로 박힌다. 협력사는 끝난 줄 알고 현장을 뜨는데
#     현장 사진은 다시 못 찍는다. 정산 관문(사진 검수)은 한참 뒤라 그때는 늦다.
print("\n[4-2] 사진 없는 완료 보고 차단")
cid5 = mkcase(f"{MARK}-E", status="시공중", partner_id=pid, partner_name=pname,
              award_amount=3_000_000)
conn.commit()
st, r = par.go("POST", f"/api/partner/cases/{cid5}/complete", {})
chk(st == 409 and (r or {}).get("code") == "NO_PHOTO",
    "★ 사진 0장이면 완료 보고가 막힌다", f"{st} {r}")
chk(conn.execute("SELECT status FROM cases WHERE id=?", (cid5,)).fetchone()[0] == "시공중",
    "상태도 그대로다(통지·보증 기산점이 안 박힌다)")

#  반려된 사진은 증거가 아니므로 세지 않는다
conn.execute(
    "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,"
    "                   review_status,created_at) "
    "VALUES(?,?,'협력사',?,'완료','반려',datetime('now','+9 hours'))",
    (cid5, pid, "verify/rej.jpg"))
conn.commit()
st, r = par.go("POST", f"/api/partner/cases/{cid5}/complete", {})
chk(st == 409, "★ 반려된 사진만 있으면 여전히 막힌다", f"{st} {r}")

#  정상 사진이 들어오면 통과한다(과잉 차단이 아니어야 한다)
conn.execute(
    "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,created_at) "
    "VALUES(?,?,'협력사',?,'완료',datetime('now','+9 hours'))",
    (cid5, pid, "verify/ok.jpg"))
conn.commit()
st, r = par.go("POST", f"/api/partner/cases/{cid5}/complete", {})
chk(st == 200 and (r or {}).get("photos", 0) >= 1,
    "사진이 있으면 정상 보고", f"{st} {r}")

# ── ⑤ 경쟁 최저가 부등식이 새지 않는다 ────────────────────────
print("\n[5] 입찰 응답이 경쟁 최저가를 암시하지 않는다")
cid4 = mkcase(f"{MARK}-D", status="입찰중", est=10_000_000, low_price=9_000_000)
au = conn.execute(
    """INSERT INTO auctions(case_id,status,deadline,low_price,created_at)
       VALUES(?,'진행',datetime('now','+9 hours','+2 days'),9000000,datetime('now','+9 hours'))""",
    (cid4,)).lastrowid
conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('low_price_alert','20')")
conn.commit()
st, r = par.go("POST", "/api/partner/bids", {"case_id": cid4, "amount": 5_000_000, "days": 5})
warn = (r or {}).get("warn") or ""
chk(st == 200, "입찰 제출", f"{st} {r}")
chk("최저가" not in warn,
    "★ 응답에 '직전 최저가 대비' 문구가 없다(부등식 누출 차단)", repr(warn))
chk("가견적" in warn or not warn,
    "가견적 대비 경고는 그대로 남는다(가견적은 공개된 값)", repr(warn))
chk("low_price" not in json.dumps(r, ensure_ascii=False),
    "응답 어디에도 경쟁 최저가 값이 없다", list((r or {}).keys()))
#  운영팀에는 그 사실이 남아야 한다
n_alert = conn.execute(
    "SELECT COUNT(*) FROM notifications WHERE case_id=? AND ntype='저가경보' "
    "  AND audience_type='admin'", (cid4,)).fetchone()[0]
chk(n_alert >= 1, "★ 대신 운영팀에는 경보가 남는다(소명 판단은 사람이 한다)", n_alert)

# ── 정리 ──────────────────────────────────────────────────────
conn.execute("DELETE FROM settings WHERE key='low_price_alert'")
for x in cleanup:
    conn.execute("DELETE FROM bids WHERE auction_id IN (SELECT id FROM auctions WHERE case_id=?)", (x,))
    conn.execute("DELETE FROM auctions WHERE case_id=?", (x,))
    conn.execute("DELETE FROM field_agreements WHERE case_id=?", (x,))
    conn.execute("DELETE FROM photos WHERE case_id=?", (x,))
    conn.execute("DELETE FROM work_lots WHERE case_id=?", (x,))
    conn.execute("DELETE FROM notifications WHERE case_id=?", (x,))
    conn.execute("DELETE FROM cases WHERE id=?", (x,))
conn.execute("DELETE FROM portal_users WHERE login_id IN (?,?)", (sub_login, psub))
conn.commit()
conn.close()
print(f"\n  통과 {ok} · 실패 {fail}   (검증 데이터 정리됨)")
sys.exit(1 if fail else 0)
