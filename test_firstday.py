# -*- coding: utf-8 -*-
"""서비스 첫날 완주 — **빈 DB에서 시작해** 2트랙을 끝까지 걸어 본다.

  기존 리허설(test_rehearsal.py)은 이미 데이터가 있는 DB에서 돈다.
  실테스트는 go-live 직후, 사건 0·업체 0·정산 0 에서 시작한다.
  그 상태에서만 드러나는 것을 잡으려고 처음부터 다시 걷는다.

  ⚠ 이 스크립트는 **막히면 거기서 멈추고 이유를 말한다.**
     "통과/실패" 개수를 세는 게 목적이 아니라, 운영자가 어디서 손이 멈추는지를 찾는 것이다.
"""
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import http.cookiejar

import tempfile

#  ⚠ 경로를 박아 두지 않는다 — 다른 PC·다른 사람이 그대로 돌릴 수 있어야 한다.
SRC = os.path.dirname(os.path.abspath(__file__))        # 이 파일이 있는 곳 = 프로젝트
HERE = os.path.join(tempfile.gettempdir(), "bokguon_firstday")
os.makedirs(HERE, exist_ok=True)
DB = os.path.join(HERE, "firstday.db")                  # 운영·검증 DB 는 절대 건드리지 않는다
PORT = int(os.environ.get("BOKGUON_FIRSTDAY_PORT", "8790"))
BASE = f"http://127.0.0.1:{PORT}"
PY = sys.executable

steps = []


def step(ok, name, detail=""):
    steps.append((ok, name, detail))
    print(f"  {'[OK]  ' if ok else '[STOP]'} {name}" + (f"   {detail}" if detail else ""))
    return ok


class C:
    """포털 하나를 쓰는 사람 한 명."""

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
            r = self.op.open(req, timeout=25)
            st, raw = r.getcode(), r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            st, raw = e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            return 0, {"error": str(e)}
        try:
            d = json.loads(raw)
        except Exception:
            d = raw[:200]
        if isinstance(d, dict) and d.get("csrf"):
            self.csrf = d["csrf"]
        return st, d


def manage(*args):
    env = dict(os.environ)
    env.update({"BOKGUON_DB_PATH": DB, "BOKGUON_ENV": "dev",
                "BOKGUON_SEED_DEMO": "0", "PYTHONIOENCODING": "utf-8"})
    r = subprocess.run([PY, "manage.py", *args], cwd=SRC, env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


# ── 0. 완전히 빈 상태에서 시작 ────────────────────────────────
print("\n[0] go-live 직후 상태 만들기")
for suf in ("", "-wal", "-shm"):
    p = DB + suf
    if os.path.exists(p):
        os.remove(p)
rc, out = manage("init")
step(rc == 0, "빈 DB 생성", out.strip().splitlines()[-1] if out.strip() else "")
rc, out = manage("create-admin", "opadmin", "--name", "운영담당", "--role", "최고관리자")
adm_pw = ""
for ln in out.splitlines():
    if "임시 비번" in ln:
        adm_pw = ln.split(":")[-1].strip().replace("\x1b[1m", "").replace("\x1b[0m", "")
step(bool(adm_pw), "실관리자 계정 발급", "임시 비밀번호 수령" if adm_pw else out[-200:])
rc, out = manage("create-insurer", "테스트손해보험", "realins", "10")
ins_pw = ""
for ln in out.splitlines():
    if "임시 비번" in ln:
        ins_pw = ln.split(":")[-1].strip().replace("\x1b[1m", "").replace("\x1b[0m", "")
step(bool(ins_pw), "보험사 실계정 발급", "임시 비밀번호 수령" if ins_pw else out[-200:])

# 서버 기동 — firstday_server.py 를 사본 없이 그대로 서브프로세스로 부른다.
#  ⚠⚠ [라운드307] 예전엔 이 자리에서 같은 부트스트랩 코드를 문자열로 다시
#    써서 임시 firstday_server.py 사본을 만들었다 — 274라운드가 원본에
#    추가한 두 안전장치(운영DB 오발방지·포트 이중바인딩 방지, Windows 는
#    같은 포트를 두 프로세스가 예외 없이 나눠 쓸 수 있다)가 그 사본에는
#    끝내 반영되지 않았다(원본 강화 후 사본은 아무도 다시 안 씀 — 306라운드
#    가 build_pages.py 산출물에서 찾은 것과 같은 "추적돼야 할 사본이 실제로
#    추적되는지 아무도 확인 안 함" 패턴). 사본을 만드는 대신 원본을 그대로
#    부르고 환경변수 두 개만 오버라이드하면, 원본이 앞으로 더 강화돼도
#    이 테스트가 자동으로 그 보호를 물려받는다.
env = dict(os.environ)
env.update({"BOKGUON_DB_PATH": DB, "BOKGUON_FIRSTDAY_PORT": str(PORT)})
proc = subprocess.Popen([PY, os.path.join(SRC, "firstday_server.py")], cwd=HERE, env=env,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
up = False
for _ in range(30):
    time.sleep(0.6)
    try:
        urllib.request.urlopen(BASE + "/partner/login", timeout=3)
        up = True
        break
    except Exception:
        pass
step(up, f"첫날 인스턴스 기동 (:{PORT})")
if not up:
    proc.terminate()
    sys.exit(1)

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
try:
    # ── 1. 관리자 첫 로그인 ───────────────────────────────────
    print("\n[1] 운영자 첫 로그인 (임시 비밀번호 → 변경 강제)")
    adm = C("운영자")
    st, d = adm.go("POST", "/api/login", {"username": "opadmin", "password": adm_pw})
    step(st == 200, "임시 비밀번호로 로그인", st)
    step(d.get("must_change_pw") is True, "비밀번호 변경이 강제된다", d.get("must_change_pw"))
    NEW_ADM = "Op7#qLm2Wz!vQr9T"
    st, d = adm.go("POST", "/api/change-password", {"current": adm_pw, "new": NEW_ADM})
    step(st == 200, "비밀번호 변경", f"{st} {d}")
    st, d = adm.go("GET", "/api/dashboard")
    step(st == 200, "콘솔 진입", st)
    if st == 200:
        _m = d.get("money") or {}
        step(_m.get("wip_amount") == 0 and d.get("cases_active") == 0,
             "빈 대시보드가 0 으로 보인다(NaN 아님)",
             f"wip={_m.get('wip_amount')} active={d.get('cases_active')}")

    # ── 2. 협력사 3곳 등록 + 계정 발급 ────────────────────────
    print("\n[2] 협력사 등록 → 포털 계정 발급 → 계좌 등록")
    pids = []
    for i, nm in enumerate(("가나시행", "다라시행", "마바시행"), 1):
        st, d = adm.go("POST", "/api/partners", {
            "name": nm, "partner_type": "시행사", "major": "유리·샷시·자동문",
            "region": "서울", "phone": f"010-1000-000{i}", "status": "활성",
            "address": "서울 강남구 테헤란로 100", "staff_count": 5})
        if st == 200:
            pids.append(d.get("id"))
    step(len(pids) == 3, "시행사 3곳 등록 (경매 최소 참여사)", f"{len(pids)}곳")

    creds = []
    for i, pid in enumerate(pids, 1):
        st, d = adm.go("POST", f"/api/partners/{pid}/credentials", {"login_id": f"fdpart{i}"})
        if st == 200:
            creds.append((f"fdpart{i}", d.get("temp_password")))
    step(len(creds) == 3, "포털 계정 3개 발급", f"{len(creds)}개")

    #  ⚠ 계좌가 없으면 공사를 마쳐도 이체가 안 나간다 — 첫날에 반드시 하는 일
    acct_ok = 0
    for i, pid in enumerate(pids, 1):
        st, _ = adm.go("PATCH", f"/api/partners/{pid}/account", {
            "bank_name": "국민은행", "bank_holder": f"가나시행{i}",
            "bank_account": f"1234567890{i}"})
        if st == 200:
            acct_ok += 1
    step(acct_ok == 3, "지급 계좌 3곳 등록", f"{acct_ok}곳")

    #  협력사 첫 로그인 (비번 변경 강제)
    pars = []
    for lg, tmp in creds:
        p = C(lg)
        st, d = p.go("POST", "/api/partner/login", {"login_id": lg, "password": tmp})
        if st == 200 and d.get("must_change_pw"):
            p.go("POST", "/api/change-password", {"current": tmp, "new": "Pt7#qLm2Wz!vQr9T"})
        pars.append(p)
    st, d = pars[0].go("GET", "/api/partner/dashboard")
    step(st == 200, "협력사 첫 로그인 → 포털 진입", st)
    if st == 200:
        step(d.get("acct_ready") is True, "계좌 등록 완료로 보인다(할 일 경고 없음)",
             d.get("acct_ready"))

    # ── 3. 보험사 첫 로그인 → 사건 등록(사진 있음 = 1차 트랙) ──
    print("\n[3] 보험사 첫 로그인 → 사진 있는 사건 접수 (1차 경매)")
    ins = C("보험사")
    st, d = ins.go("POST", "/api/insurer/login", {"login_id": "realins", "password": ins_pw})
    step(st == 200, "보험사 임시 비밀번호 로그인", st)
    if d.get("must_change_pw"):
        ins.go("POST", "/api/change-password", {"current": ins_pw, "new": "In7#qLm2Wz!vQr9T"})
    st, d = ins.go("GET", "/api/insurer/dashboard")
    step(st == 200, "보험사 포털 진입", st)

    st, d = ins.go("POST", "/api/insurer/cases", {
        "case_no": "FD-0001", "categories": ["유리·샷시·자동문"], "region": "서울",
        "address": "서울 강남구 테헤란로 152", "est_price": "3600000",
        "victim_name": "홍길동", "victim_phone": "010-2000-0001",
        "note": "1층 자동문 유리 파손"})
    cid1 = (d or {}).get("id")
    step(st == 200 and cid1, "사건 접수(가견적 360만)", f"{st} {d if not cid1 else ''}")
    if cid1:
        step((d or {}).get("matched", 0) == 3,
             "참여 가능 시행사 3곳으로 집계된다", (d or {}).get("matched"))
        #  협력사 알림함에 실제로 떴는가
        st2, dn = pars[0].go("GET", "/api/partner/notifications")
        got = [n for n in (dn.get("notifications") or []) if n.get("case_id") == cid1]
        step(bool(got), "★ 공고가 협력사 알림함에 실제로 뜬다", f"{len(got)}건")

    # ── 4. 1차 경매 — 상한(가견적) 규칙 ───────────────────────
    print("\n[4] 1차 입찰 — 가견적이 상한(인하만)")
    if cid1:
        st, d = pars[0].go("GET", "/api/partner/dashboard")
        opens = [c for c in (d.get("open_cases") or []) if c["id"] == cid1]
        step(bool(opens), "협력사 공고 목록에 보인다", len(d.get("open_cases") or []))
        if opens:
            step("address" not in opens[0] or not opens[0].get("address"),
                 "★ 입찰 전에는 상세주소가 안 보인다(철칙)",
                 opens[0].get("address"))
        st, d = pars[0].go("POST", "/api/partner/bids",
                           {"case_id": cid1, "amount": 4_000_000, "days": 7})
        step(st >= 400, "★ 가견적 위로는 투찰이 막힌다(1차=상한)", f"{st} {d}")
        amts = (3_400_000, 3_250_000, 3_100_000)
        okn = 0
        for p, a in zip(pars, amts):
            st, d = p.go("POST", "/api/partner/bids", {"case_id": cid1, "amount": a, "days": 7})
            if st == 200:
                okn += 1
                if "low_price" in json.dumps(d, ensure_ascii=False):
                    step(False, "★ 응답에 경쟁 최저가가 실렸다(철칙 위반)", d)
        step(okn == 3, "3개사 투찰 완료", f"{okn}/3")

    # ── 5. 낙찰 승인은 보험사 단독 ────────────────────────────
    print("\n[5] 낙찰 승인 — 보험사만, 추천은 기본선택 없음")
    bid_id = None
    if cid1:
        st, r = ins.go("GET", f"/api/insurer/cases/{cid1}/bids")
        step(st == 200 and len(r.get("bids") or []) == 3, "보험사 화면에 입찰 3건", st)
        if r.get("bids"):
            step(r.get("weights") and abs(sum(r["weights"].values()) - 1) < 0.01,
                 "추천 가중치가 실제 값으로 내려온다", r.get("weights"))
            bid_id = min(r["bids"], key=lambda b: b["amount"])["id"]
        st, d = adm.go("POST", f"/api/insurer/cases/{cid1}/award", {"bid_id": bid_id})
        step(st in (401, 403), "★ 운영자는 낙찰을 승인할 수 없다(철칙)", f"{st} {d}")
        st, d = ins.go("POST", f"/api/insurer/cases/{cid1}/award",
                       {"bid_id": bid_id, "reason": ""})
        step(st == 200, "보험사가 낙찰 승인", f"{st} {d}")

    # ── 6. 시공 → 완료보고 → 검수 → 정산 → 이체 ──────────────
    print("\n[6] 시공 → 완료 보고 → 보험사 완료승인 → 입금 → 검수 → 이체")
    win = None
    if cid1:
        row = conn.execute("SELECT partner_id, partner_name, award_amount FROM cases WHERE id=?",
                           (cid1,)).fetchone()
        step(row and row["partner_id"], "낙찰 업체가 사건에 기록됐다",
             f"{row['partner_name'] if row else '-'} {row['award_amount'] if row else ''}")
        win = next((p for p, pid in zip(pars, pids) if pid == (row["partner_id"] if row else 0)), None)
        step(win is not None, "낙찰 업체 세션 확보")
    if win and cid1:
        st, d = win.go("GET", "/api/partner/dashboard")
        mine = [c for c in (d.get("my_cases") or []) if c["id"] == cid1]
        step(bool(mine), "낙찰 업체 화면에 내 현장으로 뜬다", len(d.get("my_cases") or []))
        if mine:
            step(bool(mine[0].get("address")), "★ 낙찰 뒤에는 상세주소가 열린다",
                 mine[0].get("address"))
        #  사진 없이 완료 보고가 되는가(되면 안 된다)
        st, d = win.go("POST", f"/api/partner/cases/{cid1}/complete", {})
        step(st == 409 and (d or {}).get("code") == "NO_PHOTO",
             "★ 사진 없이 완료 보고가 막힌다", f"{st} {d}")
        #  사진을 심고(업로드는 multipart 라 DB 직접) 다시
        for k in ("착공전", "시공중", "완료"):
            conn.execute(
                """INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,kind,
                                      review_status,created_at)
                   VALUES(?,?,?,'협력사',?,?, '승인', datetime('now','+9 hours'))""",
                (cid1, row["partner_id"], row["partner_name"], f"fd/{k}.jpg", k))
        conn.commit()
        st, d = win.go("POST", f"/api/partner/cases/{cid1}/complete", {})
        step(st == 200, "사진 갖춘 뒤 완료 보고", f"{st} {d}")

        st, d = ins.go("GET", "/api/insurer/dashboard")
        waits = [c for c in (d.get("cases") or []) if c["id"] == cid1]
        step(bool(waits), "보험사 화면에서 완료 승인 대기로 보인다",
             waits[0]["status"] if waits else "-")

    sid = None
    if cid1:
        st, d = adm.go("POST", f"/api/cases/{cid1}/approve", {})
        r = conn.execute("SELECT id, amount, fee, payout FROM settlements WHERE case_id=?",
                         (cid1,)).fetchone()
        sid = r["id"] if r else None
        step(sid is not None, "검수 승인 → 정산 생성",
             f"금액 {r['amount']:,} 수수료 {r['fee']:,} 지급 {r['payout']:,}" if r else f"{st} {d}")
        if r:
            step(r["fee"] == round(r["amount"] * 0.10),
                 "★ 수수료가 계약 요율 10% 그대로", f"{r['fee']} vs {round(r['amount']*0.10)}")
    if sid:
        st, d = ins.go("POST", f"/api/insurer/settlements/{sid}/approve", {})
        step(st == 200, "보험사 공사 완료 승인", f"{st} {d}")
        st, d = adm.go("POST", f"/api/settlements/{sid}/paid", {})
        step(st == 200, "보험사 입금 확인", f"{st} {d}")
        st, d = adm.go("POST", f"/api/settlements/{sid}/review",
                       {"double_checked": True, "note": "첫날 검증"})
        step(st == 200, "지급 검수(더블 크로스체크)", f"{st} {d}")
        st, d = adm.go("POST", f"/api/settlements/{sid}/transfer", {})
        step(st == 200, "업체 이체 완료", f"{st} {d}")
        fin = conn.execute("SELECT status FROM cases WHERE id=?", (cid1,)).fetchone()[0]
        step(fin == "완료", "사건이 '완료'로 닫힌다", fin)

    # ── 7. 2차 트랙 — 사진 없이 접수 ──────────────────────────
    print("\n[7] 2차 트랙 — 사진 없는 접수 → 출동 → 실견적 → 보험사 부동의 → 2차 경매")
    st, d = ins.go("POST", "/api/insurer/cases", {
        "case_no": "FD-0002", "categories": ["유리·샷시·자동문"], "region": "서울",
        "address": "서울 강남구 역삼로 200", "no_photo": True,
        "victim_name": "김철수", "victim_phone": "010-2000-0002"})
    cid2 = (d or {}).get("id")
    step(st == 200 and cid2, "사진 없는 사건 접수", f"{st} {d if not cid2 else ''}")
    if cid2:
        stt = conn.execute("SELECT status, est_price FROM cases WHERE id=?", (cid2,)).fetchone()
        step(stt["status"] == "접수" and not stt["est_price"],
             "★ 경매가 열리지 않고 '접수'로 선다(가견적 강제 없음)",
             f"{stt['status']} est={stt['est_price']}")
        st, d = adm.go("POST", f"/api/cases/{cid2}/dispatch", {})
        step(st == 200, "출동 수배 개시", f"{st} {d}")
        st, d = pars[0].go("GET", "/api/partner/dispatches")
        calls = [x for x in (d if isinstance(d, list) else d.get("items", [])) or []
                 if x.get("case_id") == cid2]
        step(bool(calls), "협력사 출동 콜 목록에 뜬다", len(calls))
        if calls:
            did = calls[0].get("id") or calls[0].get("dispatch_id")
            st, d = pars[0].go("POST", f"/api/partner/dispatches/{did}/claim", {})
            step(st == 200, "선착순 수락", f"{st} {d}")
            st, d = pars[1].go("POST", f"/api/partner/dispatches/{did}/claim", {})
            step(st >= 400, "★ 두 번째 업체는 수락할 수 없다(선착순 1곳)", f"{st} {d}")

        #  ── 도착 보고: 사진이 있어야 인정된다 ──────────────────
        st, d = pars[0].go("POST", f"/api/partner/dispatches/{did}/arrive",
                           {"field_estimate": 5_000_000})
        step(st >= 400, "★ 사진 없이 도착 보고가 안 된다", f"{st} {d}")
        prow = conn.execute("SELECT id, name FROM partners WHERE id=?", (pids[0],)).fetchone()
        for k in ("현장", "파손부위"):
            conn.execute(
                "INSERT INTO photos(case_id,partner_id,uploader,uploader_role,rel_path,kind,"
                "                   created_at) "
                "VALUES(?,?,?,'협력사',?,?,datetime('now','+9 hours'))",
                (cid2, prow["id"], prow["name"], f"fd/{k}.jpg", "착공전"))
        conn.commit()
        st, d = pars[0].go("POST", f"/api/partner/dispatches/{did}/arrive",
                           {"field_estimate": 5_000_000})
        step(st == 200, "사진 올린 뒤 도착 보고 + 실견적 500만", f"{st} {d}")

        #  ── 1차 합의: 운영자는 '전달'만, 승인은 보험사 ─────────
        #  ⚠ 수선 패턴을 함께 보낸다 — 이게 **정상 경로**다.
        #    서버가 표준단가로 개산 구간을 계산해 남기고, 그 하단이 2차 경매의 하한이 된다.
        #    (패턴을 안 고르면 근거가 없어 하한도 없다 — 그때는 운영팀에 경보가 뜬다)
        st, d = adm.go("POST", f"/api/cases/{cid2}/field-agreement",
                       {"pattern": "glass_tempered", "inputs": {"W": "2.0", "H": "2.4"}})
        step(st == 200, "운영자가 실견적 원문을 보험사에 전달(개산 근거 포함)", f"{st} {d}")
        _eng = conn.execute(
            "SELECT engine_low, engine_high FROM field_agreements WHERE case_id=? "
            "ORDER BY id DESC LIMIT 1", (cid2,)).fetchone()
        step(_eng and (_eng["engine_low"] or 0) > 0,
             "★ 서버가 표준단가로 개산 구간을 계산해 남긴다(위조 불가)",
             f"{_eng['engine_low'] if _eng else '-'}~{_eng['engine_high'] if _eng else '-'}")
        fa = conn.execute(
            "SELECT id, field_amount, status FROM field_agreements WHERE case_id=? "
            "ORDER BY id DESC LIMIT 1", (cid2,)).fetchone()
        step(fa and fa["field_amount"] == 5_000_000,
             "★ 금액은 출동 업체 실견적 그대로(운영자가 못 바꾼다)",
             f"{fa['field_amount'] if fa else '-'}")
        if fa:
            st, d = adm.go("POST", f"/api/field-agreements/{fa['id']}/settle",
                           {"agreed": True, "amount": 4_000_000})
            step(st in (400, 403, 409),
                 "★ 운영자는 합의를 확정할 수 없다(철칙)", f"{st} {d}")

        #  ── 보험사 부동의 → 2차 경매 ────────────────────────────
        st, d = ins.go("POST", f"/api/insurer/cases/{cid2}/field-agreement/decision",
                       {"approve": False, "reason": "표준단가 대비 과다"})
        step(st == 200, "보험사 부동의", f"{st} {d}")
        st, d = adm.go("POST", f"/api/cases/{cid2}/open-auction",
                       {"est_basis": "출동 업체 현장 사진 2장 확보 · 실견적 500만"})
        step(st == 200, "2차 경매 개시", f"{st} {d}")
        rnd = conn.execute("SELECT est_price, status FROM cases WHERE id=?", (cid2,)).fetchone()
        step(rnd["status"] == "입찰중", "사건이 '입찰중'으로", rnd["status"])

        #  ⚠ 2차는 가견적이 **하한**이다 — 1차와 정반대
        st, d = pars[1].go("GET", "/api/partner/dashboard")
        oc = [c for c in (d.get("open_cases") or []) if c["id"] == cid2]
        step(bool(oc), "2차 공고가 협력사에 보인다", len(d.get("open_cases") or []))
        _floor = (oc[0].get("bid_floor") if oc else 0) or 0
        step(_floor > 0, "★ 2차에 최소 금액이 선다(개산 하단)", _floor)
        st, d = pars[1].go("POST", "/api/partner/bids",
                           {"case_id": cid2, "amount": max(1, _floor - 1), "days": 5})
        step(st >= 400 and (d or {}).get("code") == "UNDER_FLOOR",
             "★ 2차는 하한 아래로 투찰이 막힌다(1차와 정반대)", f"{st} {d}")
        okn2 = 0
        for p, a in zip(pars[1:], (_floor + 600_000, _floor + 300_000)):
            st, d = p.go("POST", "/api/partner/bids", {"case_id": cid2, "amount": a, "days": 5})
            if st == 200:
                okn2 += 1
        step(okn2 == 2, "2차 투찰(하한 위에서 경쟁)", f"{okn2}/2")

        st, r = ins.go("GET", f"/api/insurer/cases/{cid2}/bids")
        if r.get("bids"):
            b2 = min(r["bids"], key=lambda b: b["amount"])
            st, d = ins.go("POST", f"/api/insurer/cases/{cid2}/award", {"bid_id": b2["id"]})
            step(st == 200, "보험사가 2차 낙찰 승인", f"{st} {d}")
            fin = conn.execute("SELECT status, award_amount FROM cases WHERE id=?",
                               (cid2,)).fetchone()
            step(fin["status"] == "시공중", "2차 트랙도 시공으로 넘어간다",
                 f"{fin['status']} {fin['award_amount']:,}")

    print("\n" + "=" * 62)
    bad = [s for s in steps if not s[0]]
    print(f"  첫날 완주 {len(steps) - len(bad)} / {len(steps)}"
          + (f"   ⚠ 막힌 지점 {len(bad)}" if bad else "   — 막힌 지점 없음"))
    for _, n, dt in bad:
        print(f"    · {n}   {dt}")
finally:
    conn.close()
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except Exception:
        proc.kill()

sys.exit(1 if [s for s in steps if not s[0]] else 0)
