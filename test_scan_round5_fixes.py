# -*- coding: utf-8 -*-
"""5라운드 스캔 수정 회귀 — 법률 철칙 · 사진 · 알림 도달.

  ① 금액이 **올라가는** 경로(변경견적 전체재경매)에도 최저가 사유 게이트가 있다
     — 다른 두 낙찰 경로에는 있는데 하필 증액 구간에만 없었다(§188 3호 소명 근거).
  ② 미분류 사진(kind=NULL)은 입찰사에게 열리지 않는다
     — `(kind or '') not in DOCUMENT_KINDS` 가 NULL 을 '영수증 아님'으로 읽어
       직전 시공사 영수증이 경쟁사에 열렸다(낙찰가 공개).
  ③ 낙찰 통지가 경로에 따라 갈리지 않는다(피해자 안내 · 보험사 알림함).
  ④ 2차 경매 하한이 0으로 무너지지 않는다(사진 없는 접수 = 가견적 0).
"""
import atexit
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
import uuid
import http.cookiejar

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "verify.db")
MARK = "R8" + uuid.uuid4().hex[:5].upper()


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
cleanup = []


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [OK]   {name}")
    else:
        fail += 1
        print(f"  [FAIL] {name}   {got}")


def _cleanup():
    """어떻게 끝나든 검증 데이터를 지운다(레이트리밋에 걸려 죽어도).

      ⚠⚠ [라운드405] 예전엔 바깥 try 하나가 루프 전체를 감쌌다 — 사건
        하나의 DELETE FROM bids(유일하게 안 감싸져 있던 줄)가 락 경합
        등으로 실패하면 커밋 한 번 없이 나머지 사건 전부(그리고 이미
        처리한 앞선 사건들도 commit 전이라 함께) 조용히 통째로 취소됐다.
        그렇게 남은 '마감지난 진행중' 경매 하나가 이후 어떤 배터리
        실행에서든 sweep_auctions() 의 전역 스캔(app.py:5583)에 걸려
        무관한 test_b4_deadline.py 를 실패시켰다(405라운드가 직접주입
        재현으로 확정). 사건별로 감싸 하나 실패해도 나머지는 계속
        지우고, 사건마다 즉시 커밋해 부분 성공을 남긴다.
    """
    try:
        c2 = sqlite3.connect(DBP)
        for x in cleanup:
            try:
                c2.execute("DELETE FROM bids WHERE auction_id IN "
                           "(SELECT id FROM auctions WHERE case_id=?)", (x,))
                for t in ("auctions", "field_agreements", "photos", "work_lots",
                          "notifications", "change_orders"):
                    try:
                        c2.execute(f"DELETE FROM {t} WHERE case_id=?", (x,))
                    except sqlite3.Error:
                        pass
                c2.execute("DELETE FROM cases WHERE id=?", (x,))
                c2.commit()
            except sqlite3.Error as e:
                print(f"  [WARN] R5 정리 실패(case_id={x}): {e}", file=sys.stderr)
        c2.close()
    except Exception:
        pass


atexit.register(_cleanup)

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
other = conn.execute(
    "SELECT id, name FROM partners WHERE id<>? AND status='활성' LIMIT 1", (pid,)).fetchone()


def mkcase(no, **extra):
    cols = "case_no,insurer,insurer_id,category,region,address,created_at"
    vals = "?,?,?,?,?,?,datetime('now','+9 hours')"
    args = [no, "○○손보", iid, "유리·샷시·자동문", "서울", "R5검증"]
    for k, v in extra.items():
        cols += f",{k}"
        vals += ",?"
        args.append(v)
    cid = conn.execute(f"INSERT INTO cases({cols}) VALUES({vals})", args).lastrowid
    cleanup.append(cid)
    return cid


# ── ① 증액 경로에도 최저가 사유 게이트 ────────────────────────
print("\n[1] 변경견적 전체재경매 — 금액이 올라가는 구간의 소명 게이트")
cid = mkcase(f"{MARK}-A", status="시공중", partner_id=pid, partner_name=pname,
             est_price=3_000_000, award_amount=2_800_000)
co = conn.execute(
    """INSERT INTO change_orders(case_id,status,round,requested_amount,reason,created_at)
       VALUES(?,'전체재경매중',1,?,?,datetime('now','+9 hours'))""",
    (cid, 1_500_000, "실사 후 물량 증가")).lastrowid
au = conn.execute(
    """INSERT INTO auctions(case_id,change_order_id,kind,status,deadline,created_at)
       VALUES(?,?, '전체재경매','진행',datetime('now','+9 hours','-1 hour'),
              datetime('now','+9 hours'))""", (cid, co)).lastrowid
low_id = conn.execute(
    """INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
       VALUES(?,?,?,?,?,datetime('now','+9 hours'))""",
    (au, pid, pname, 4_000_000, 7)).lastrowid
high_id = conn.execute(
    """INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
       VALUES(?,?,?,?,?,datetime('now','+9 hours'))""",
    (au, other["id"], other["name"], 4_900_000, 5)).lastrowid
conn.commit()

st, r = adm.go("POST", f"/api/change-orders/{co}/close-full", {"bid_id": high_id})
chk(st == 400 and (r or {}).get("code") == "NOT_LOWEST",
    "★ 최저가가 아닌 입찰을 사유 없이 못 고른다(증액 경로)", f"{st} {r}")
row = conn.execute("SELECT partner_id, award_amount FROM cases WHERE id=?", (cid,)).fetchone()
chk(row["award_amount"] == 2_800_000, "금액이 그대로다(확정 안 됨)", row["award_amount"])

#  ★★ **사유만으로는 통과하면 안 된다.** (12라운드에서 잡힌 철칙 1 위반)
#    이 라우트는 발주처가 낼 돈이 늘어나는 확정을 한다. 종전에는 '최저가 아님 사유'
#    한 줄이면 복구온 중간관리자 혼자 증액을 확정할 수 있었고,
#    **이 테스트가 그것을 「정상」으로 굳혀 두고 있었다.**
#    (api_co_decision 에는 발주처 확인 관문을 걸어 놓고 거절 가지만 열려 있었다)
st, r = adm.go("POST", f"/api/change-orders/{co}/close-full",
               {"bid_id": high_id, "reason": "동일 현장 연속 시공으로 공기 단축"})
chk(st == 409 and (r or {}).get("code") == "INSURER_ACK_REQUIRED",
    "★ 사유만으로는 증액이 확정되지 않는다(발주처 확인이 필요하다)", f"{st} {r}")
row = conn.execute("SELECT award_amount FROM cases WHERE id=?", (cid,)).fetchone()
chk(row["award_amount"] == 2_800_000, "  금액이 그대로다(확정 안 됨)", row["award_amount"])

#  발주처 유선 지시를 근거로 남기면 대행 확정이 된다(그 근거가 감사로그에 남는다)
st, r = adm.go("POST", f"/api/change-orders/{co}/close-full",
               {"bid_id": high_id, "reason": "동일 현장 연속 시공으로 공기 단축",
                "insurer_instruction": "2026-08-06 담당자 유선 지시 — 이 업체로 진행"})
chk(st == 200, "★ 발주처 지시 근거를 남기면 통과", f"{st} {r}")
lg2 = conn.execute(
    "SELECT detail FROM activity_log WHERE action='발주처 낙찰 지시(대행)' "
    "ORDER BY id DESC LIMIT 1").fetchone()
chk(lg2 and "유선 지시" in (lg2["detail"] or ""),
    "★ 그 지시 근거가 실제로 감사로그에 남는다(받기만 하고 버리지 않는다)",
    (lg2["detail"] if lg2 else "-"))
lg = conn.execute(
    "SELECT detail FROM activity_log WHERE action='전체 재경매 낙찰' ORDER BY id DESC LIMIT 1"
).fetchone()
chk(lg and "사유" in (lg["detail"] or ""), "★ 사유가 감사로그에 남는다",
    (lg["detail"] if lg else "-"))

# ── ② 미분류 사진은 입찰사에게 안 열린다 ──────────────────────
print("\n[2] 분류 안 된 사진(kind=NULL)은 열지 않는다")
cid2 = mkcase(f"{MARK}-B", status="입찰중", est_price=5_000_000)
conn.execute(
    """INSERT INTO auctions(case_id,status,deadline,created_at)
       VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
    (cid2,))
ph_null = conn.execute(
    "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,created_at) "
    "VALUES(?,?,'협력사',?,NULL,datetime('now','+9 hours'))",
    (cid2, other["id"], "verify/unknown.jpg")).lastrowid
ph_rcpt = conn.execute(
    "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,created_at) "
    "VALUES(?,?,'협력사',?,'영수증',datetime('now','+9 hours'))",
    (cid2, other["id"], "verify/receipt.jpg")).lastrowid
ph_ok = conn.execute(
    "INSERT INTO photos(case_id,partner_id,uploader_role,rel_path,kind,created_at) "
    "VALUES(?,?,'보험사',?,'착공전',datetime('now','+9 hours'))",
    (cid2, None, "verify/damage.jpg")).lastrowid
conn.commit()

#  ⚠ **403 과 404 를 구분해야 한다.** 라우트는 권한을 먼저 보고(403),
#    그 다음에 파일 존재를 본다(404). 검증용 행은 디스크에 실물이 없으므로
#    권한이 열려 있으면 404 가 나온다 — 404 를 '차단됨'으로 세면
#    셋 다 파일이 없어서 404 인데 전부 통과로 읽힌다(실제로 그럴 뻔했다).
st, _ = par.go("GET", f"/api/photos/{ph_null}/file")
chk(st == 403, "★ 분류 안 된 사진은 입찰사에게 안 열린다(403)", st)
st, _ = par.go("GET", f"/api/photos/{ph_rcpt}/file")
chk(st == 403, "영수증은 종전대로 차단(403)", st)
st, _ = par.go("GET", f"/api/photos/{ph_ok}/file")
chk(st != 403, "★ 파손 사진은 권한이 열린다(404=파일 없음은 정상)", st)

# ── ③ 낙찰 통지가 경로에 따라 갈리지 않는다 ───────────────────
print("\n[3] 낙찰 통지 대칭 — 누가 눌렀든 같은 사람들이 받는다")
cid3 = mkcase(f"{MARK}-C", status="입찰중", est_price=4_000_000,
              victim_name="검증피해자", victim_phone="010-9999-0001")
au3 = conn.execute(
    """INSERT INTO auctions(case_id,status,deadline,created_at)
       VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
    (cid3,)).lastrowid
bid3 = conn.execute(
    """INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
       VALUES(?,?,?,?,?,datetime('now','+9 hours'))""",
    (au3, pid, pname, 3_500_000, 5)).lastrowid
conn.commit()

st, r = ins.go("POST", f"/api/insurer/cases/{cid3}/award", {"bid_id": bid3})
chk(st == 200, "보험사 경로로 낙찰 승인", f"{st} {r}")
#  ⚠ notify_victim 은 target 에 **전화번호**를 넣는다(ntype 이 '피해자안내').
vic = conn.execute(
    "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND ntype='피해자안내'",
    (cid3,)).fetchone()["n"]
chk(vic >= 1, "★ 보험사 경로에서도 피해자 안내가 나간다(예전엔 어드민 경로만)", vic)

cid4 = mkcase(f"{MARK}-D", status="입찰중", est_price=4_000_000,
              victim_name="검증피해자2", victim_phone="010-9999-0002")
au4 = conn.execute(
    """INSERT INTO auctions(case_id,status,deadline,created_at)
       VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
    (cid4,)).lastrowid
bid4 = conn.execute(
    """INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
       VALUES(?,?,?,?,?,datetime('now','+9 hours'))""",
    (au4, pid, pname, 3_400_000, 5)).lastrowid
conn.commit()
st, r = adm.go("POST", f"/api/cases/{cid4}/award", {"bid_id": bid4, "insurer_instruction": "검증 — 발주처 유선 지시(2026-08-06 담당자 확인)"})
chk(st == 200, "어드민 경로로 낙찰 승인", f"{st} {r}")
ins_n = conn.execute(
    "SELECT COUNT(*) n FROM notifications WHERE case_id=? AND audience_type='insurer'",
    (cid4,)).fetchone()["n"]
chk(ins_n >= 1, "★ 어드민 경로에서도 보험사 알림함에 뜬다(웹훅 미등록도 안다)", ins_n)

# ── ④ 2차 하한이 0으로 무너지지 않는다 ────────────────────────
print("\n[4] 사진 없는 접수(가견적 0) → 2차 경매 하한")
cid5 = mkcase(f"{MARK}-E", status="입찰중", est_price=0)
conn.execute(
    """INSERT INTO auctions(case_id,status,deadline,created_at)
       VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
    (cid5,))
conn.execute(
    """INSERT INTO field_agreements(case_id,partner_id,partner_name,field_amount,
                                    engine_low,engine_high,status,created_at)
       VALUES(?,?,?,?,?,?, '결렬', datetime('now','+9 hours'))""",
    (cid5, other["id"], other["name"], 5_000_000, 3_800_000, 6_200_000))
conn.commit()

st, d = par.go("GET", "/api/partner/dashboard")
row5 = next((c for c in ((d or {}).get("open_cases") or []) if c["id"] == cid5), None)
chk(row5 is not None, "2차 공고가 보인다", st)
if row5:
    chk(row5.get("bid_floor") == 3_800_000,
        "★ 가견적이 0이어도 하한이 선다(표준단가 개산 하단)", row5.get("bid_floor"))
    chk(not row5.get("field_ref"), "남의 실견적은 안 보인다", row5.get("field_ref"))
st, r = par.go("POST", "/api/partner/bids",
               {"case_id": cid5, "amount": 1_000_000, "days": 5})
chk(st == 400 and (r or {}).get("code") == "UNDER_FLOOR",
    "★ 하한 아래 투찰이 막힌다(예전엔 하한 0이라 100만원도 통과했다)", f"{st} {r}")
st, r = par.go("POST", "/api/partner/bids",
               {"case_id": cid5, "amount": 4_500_000, "days": 5})
chk(st == 200, "하한 위 투찰은 정상", f"{st} {r}")

conn.commit()
conn.close()
print(f"\n  통과 {ok} · 실패 {fail}   (검증 데이터 정리됨)")
sys.exit(1 if fail else 0)
