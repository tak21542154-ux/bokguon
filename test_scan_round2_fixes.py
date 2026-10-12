# -*- coding: utf-8 -*-
"""4라운드 회귀 — 스캔이 찾은 치명·높음 수정분.

  ① 입찰자에게 영수증·업로더 상호가 안 나간다(당사자는 그대로 본다)
  ② 미수선 종결이 이미 배정된 사건을 못 덮는다
  ③ 발송대기함: 웹·푸시는 '전달됨', 문자·알림톡만 '발송대기'
  ④ 고른 건은 48시간 지나도 보낼 수 있다
  ⑤ 공지는 로그인 필요 + 대상별 필터
  ⑥ 하자번호가 되감기지 않는다
"""
import os, sys, json, zlib, struct, uuid, sqlite3
import urllib.request, http.cookiejar

BASE = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")
DBP = os.environ.get("BOKGUON_DB_PATH") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "bokguon.db")
MARK = "R4" + uuid.uuid4().hex[:5].upper()
RUN = uuid.uuid4().bytes


def png(rgb):
    rgb = [(c + RUN[i]) % 256 for i, c in enumerate(rgb)]
    w = h = 8
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    def ck(t, d):
        c = t + d
        return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + ck(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + ck(b"IDAT", zlib.compress(raw)) + ck(b"IEND", b""))


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
            r = self.op.open(req, timeout=40); st, raw = r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, raw = e.code, e.read().decode("utf-8", "replace")
        try:
            return st, json.loads(raw)
        except Exception:
            return st, raw[:200]


ok = fail = 0


def chk(cond, name, got=""):
    global ok, fail
    if cond:
        ok += 1; print(f"  [OK]   {name}")
    else:
        fail += 1; print(f"  [FAIL] {name}   {got}")


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
pname = conn.execute("SELECT name FROM partners WHERE id=?", (pid,)).fetchone()[0]
made = []


def mkcase(no, status="입찰중", partner=None):
    cid = conn.execute(
        """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,est_price,
                             status,partner_id,partner_name,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,datetime('now','+9 hours'))""",
        (no, "○○손보", iid, "유리·샷시·자동문", "서울", f"{no} 검증현장",
         3_000_000, status, partner, pname if partner else None)).lastrowid
    made.append(cid)
    return cid


# ── ① 입찰자에게 영수증·업로더가 안 나간다 ──────────────────
print("\n[1] 입찰 중 공고의 사진 열람 범위")
cid = mkcase(f"{MARK}-1")
conn.execute("""INSERT INTO auctions(case_id,status,deadline,created_at)
                VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
             (cid,))
#  직전 시공사가 남긴 것처럼 사진 2장 — 시공 1장 + 영수증 1장
for kind, name in (("완료", "site.png"), ("영수증", "receipt.png")):
    conn.execute(
        """INSERT INTO photos(case_id,uploader,uploader_role,partner_id,rel_path,orig_name,
                              mime,ext,size,sha256,kind,review_status,created_at)
           VALUES(?,?,'협력사',?,?,?,'image/png','png',100,?, ?,'승인',datetime('now','+9 hours'))""",
        (cid, "직전시공사(주)", 9999, f"x/{uuid.uuid4().hex}.png", name,
         uuid.uuid4().hex, kind))
conn.commit()

st, d = par.go("GET", f"/api/cases/{cid}/photos")
chk(st == 200, "입찰 자격으로 사진 목록은 열린다(견적을 내야 하므로)", st)
chk(len(d.get("construction") or []) == 1, "시공 사진은 보인다", len(d.get("construction") or []))
chk(d.get("receipts") == [], "★ 영수증은 안 나간다(직전 시공사·공사금액이 찍혀 있다)",
    d.get("receipts"))
leaked = [k for p in (d.get("construction") or [])
          for k in ("uploader", "partner_id", "uploader_role", "orig_name") if k in p]
chk(not leaked, "★ 누가 올렸는지(업체 상호)가 안 나간다", leaked)
chk(d.get("case", {}).get("partner_name") is None, "★ 낙찰업체명도 안 나간다",
    d.get("case", {}).get("partner_name"))

rid = conn.execute("SELECT id FROM photos WHERE case_id=? AND kind='영수증'", (cid,)).fetchone()[0]
st, _ = par.go("GET", f"/api/photos/{rid}/file")
chk(st in (401, 403), "★ 영수증 원본 파일도 차단", st)

#  당사자(낙찰업체)는 그대로 다 본다 — 과잉 차단이 아닌지
own = mkcase(f"{MARK}-2", status="시공중", partner=pid)
conn.execute(
    """INSERT INTO photos(case_id,uploader,uploader_role,partner_id,rel_path,orig_name,
                          mime,ext,size,sha256,kind,review_status,created_at)
       VALUES(?,?,'협력사',?,?,'r2.png','image/png','png',100,?,'영수증','승인',
              datetime('now','+9 hours'))""",
    (own, pname, pid, f"x/{uuid.uuid4().hex}.png", uuid.uuid4().hex))
conn.commit()
st, d2 = par.go("GET", f"/api/cases/{own}/photos")
chk(st == 200 and len(d2.get("receipts") or []) == 1,
    "★ 자기 사건의 영수증은 그대로 본다(과잉 차단 아님)", f"{st} {len(d2.get('receipts') or [])}")

# ── ② 미수선 종결이 배정된 사건을 못 덮는다 ────────────────
print("\n[2] 미수선 종결 가드")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ["BOKGUON_DB_PATH"] = DBP
import dispatch as DP  # noqa: E402

busy = mkcase(f"{MARK}-3", status="시공중", partner=pid)
did = conn.execute(
    """INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,created_at,claimed_at)
       VALUES(?,?,?,?,datetime('now','+9 hours'),datetime('now','+9 hours'))""",
    (busy, DP.ST_ARRIVED, pid, pname)).lastrowid
conn.commit()
okk, msg = DP.close_no_repair(conn, did, pid, "파손이 경미해 수선 불필요", by="검증")
chk(okk is False, "★ 이미 배정·시공중인 사건은 미수선 종결 불가", f"{okk} {msg}")
chk(conn.execute("SELECT status FROM cases WHERE id=?", (busy,)).fetchone()[0] == "시공중",
    "★ 사건 상태가 그대로 유지된다", None)

free = mkcase(f"{MARK}-4", status="접수")
did2 = conn.execute(
    """INSERT INTO dispatches(case_id,status,claimed_partner_id,claimed_name,created_at,claimed_at)
       VALUES(?,?,?,?,datetime('now','+9 hours'),datetime('now','+9 hours'))""",
    (free, DP.ST_CLAIMED, pid, pname)).lastrowid
conn.commit()
okk2, msg2 = DP.close_no_repair(conn, did2, pid, "파손이 경미해 수선 불필요", by="검증")
chk(okk2 is True, "정상 건은 종전대로 종결된다", f"{okk2} {msg2}")
chk(conn.execute("SELECT status FROM cases WHERE id=?", (free,)).fetchone()[0] == "미수선종결",
    "미수선종결로 전환", None)

# ── ③ 발송대기함 소음 ───────────────────────────────────────
print("\n[3] 발송대기 상태 분리")
before_web = conn.execute(
    "SELECT COUNT(*) n FROM notifications WHERE status='발송대기' "
    " AND channel NOT IN ('알림톡','문자')").fetchone()["n"]
chk(before_web == 0, "★ 웹·푸시가 '발송대기'로 남아 있지 않다(마이그레이션 정리됨)", before_web)

st, r = ins.go("POST", "/api/insurer/cases", {
    "category": "유리·샷시·자동문", "region": "서울", "address": f"{MARK} 알림검증",
    "est_price": 1_000_000})
ncid = (r or {}).get("id")
if ncid:
    made.append(ncid)
    web = conn.execute(
        "SELECT status, channel FROM notifications WHERE case_id=? AND channel NOT IN ('알림톡','문자') "
        " ORDER BY id DESC LIMIT 1", (ncid,)).fetchone()
    if web:
        chk(web["status"] == "전달됨", "★ 새로 만든 웹 알림은 '전달됨'", dict(web))

# ── ④ 고른 건은 48시간 지나도 보낸다 ────────────────────────
print("\n[4] 오래된 건 수동 발송 경로")
old_id = conn.execute(
    """INSERT INTO notifications(ntype,channel,target,message,status,partner_id,
                                 audience_type,created_at)
       VALUES('낙찰','문자',?,?,'발송대기',?, 'partner',
              datetime('now','+9 hours','-10 days'))""",
    (pname, f"{MARK} 열흘 지난 문자", pid)).lastrowid
conn.commit()
st, r = adm.go("POST", "/api/outbox/send-selected", {"ids": [old_id]})
#  팝빌 미연동이면 409(꺼져 있음)가 정상 — 그래도 '나이 때문에 건너뜀'은 아니어야 한다
chk(st in (200, 409), "선택 발송 라우트가 존재한다", f"{st} {r}")
if st == 409:
    chk("팝빌" in str(r.get("error", "")),
        "★ 거절 사유가 '팝빌 미연동'이지 나이가 아니다", r.get("error"))
st, _ = adm.go("POST", "/api/outbox/send-selected", {"ids": []})
chk(st == 400, "빈 선택 거절", st)

# ── ⑤ 공지 접근 통제 ────────────────────────────────────────
print("\n[5] 공지 접근 통제")
anon = C()
st, _ = anon.go("GET", "/api/notices")
chk(st == 401, "★ 비로그인은 공지를 못 읽는다", st)
nid = conn.execute(
    """INSERT INTO notices(title,body,audience,pinned,created_at)
       VALUES(?,?,'보험사',0,datetime('now','+9 hours'))""",
    (f"{MARK} 보험사 전용 공지", "협력사에 보이면 안 되는 내용")).lastrowid
conn.commit()
st, d = par.go("GET", "/api/notices")
chk(st == 200 and not any(x["id"] == nid for x in (d or [])),
    "★ 협력사에게 보험사 전용 공지가 안 보인다", st)
st, d = ins.go("GET", "/api/notices")
chk(st == 200 and any(x["id"] == nid for x in (d or [])),
    "보험사는 자기 대상 공지를 본다", st)
st, d = adm.go("GET", "/api/notices")
chk(st == 200 and any(x["id"] == nid for x in (d or [])), "관리자는 전체를 본다", st)

# ── ⑥ 하자번호 되감김 ───────────────────────────────────────
print("\n[6] 하자번호 채번")
done = conn.execute(
    "SELECT id FROM cases WHERE partner_id=? AND status='완료' AND COALESCE(is_demo,0)=0 "
    " ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
if done:
    mx = conn.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTR(defect_no,5) AS INTEGER)),1000) m FROM defects "
        " WHERE defect_no LIKE 'D26-%'").fetchone()["m"]
    st, r = adm.go("POST", "/api/defects", {"case_id": done["id"],
                                            "title": f"{MARK} 채번검증", "severity": "경미"})
    chk(st == 200, "하자 접수 성공", f"{st} {r}")
    row = conn.execute("SELECT id, defect_no FROM defects WHERE title LIKE ? ORDER BY id DESC LIMIT 1",
                       (MARK + "%",)).fetchone()
    if row:
        newn = int(row["defect_no"].split("-")[1])
        chk(newn > mx, "★ 이전 최대 번호보다 큰 번호로 채번(되감김 없음)", f"{mx} → {newn}")
        conn.execute("DELETE FROM defects WHERE id=?", (row["id"],))
        conn.commit()

# ── 정리 ────────────────────────────────────────────────────
conn.execute("DELETE FROM notices WHERE id=?", (nid,))
conn.execute("DELETE FROM notifications WHERE id=?", (old_id,))
for x in made:
    conn.execute("DELETE FROM bids WHERE auction_id IN (SELECT id FROM auctions WHERE case_id=?)", (x,))
    for t in ("auctions", "work_lots", "field_agreements", "dispatches", "photos",
              "notifications", "defects", "settlements"):
        try:
            conn.execute(f"DELETE FROM {t} WHERE case_id=?", (x,))
        except sqlite3.Error:
            pass
    conn.execute("DELETE FROM cases WHERE id=?", (x,))
conn.commit(); conn.close()
print(f"\n  통과 {ok} · 실패 {fail}   (검증 데이터 정리됨)")
sys.exit(1 if fail else 0)
