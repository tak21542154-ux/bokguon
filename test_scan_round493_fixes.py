# -*- coding: utf-8 -*-
"""스캔 493라운드 회귀 — api_partner_update()(업체 정보수정, app.py:8270)의
사업자번호 중복확인(DUP_BIZNO)에 형제 둘(api_application_update 승인관문·
api_partner_create, 각각 round248/429가 이식 + 라운드466이 api_partner_create에
BEGIN IMMEDIATE 추가)과 같은 잠금이 없어, 서로 다른 두 업체를 거의 동시에
승인·정정하면 둘 다 "중복 없음"을 읽고 통과해 같은 사업자번호로 활성 업체
2곳이 생길 수 있던 결함.

⚠ 이 라운드의 수정은 함수 안 여섯 곳(BEGIN IMMEDIATE 삽입 + 기존 조기반환
  5곳 각각에 conn.rollback() 추가)에 흩어져 있어(라운드490·491과 같은
  이유), 함수 전체를 통째로(데코레이터부터 finally:conn.close()까지)
  고정문자열로 캡처해 원본 전체 텍스트로 통째 치환하는 방식으로 되돌린다.

⚠⚠ [라운드622] 되돌림-증명 기법을 옛 세대(app.py를 실제로 디스크에 써넣고
   매 실행 새로 생성한 워커 스크립트(test_scan_round493_worker.py)를
   서브프로세스로 돌린 뒤 복원)에서 round490/491이 확립한 안전패턴으로
   이관한다. api_partner_update()는 단일 라우트 핸들러라 ORIGINAL_FUNC
   텍스트(데코레이터·주석 제거)를 exec로 독립 사본 네임스페이스에 재구성해
   A.app.view_functions 딕셔너리 항목만 잠깐 치환한다 — 진짜 app.py 파일도,
   워커 파일도 전혀 안 쓴다(옛 워커는 더 이상 생성하지 않는다). 진짜 동시성
   재현(threading.Barrier + 실제 스레드 2개)은 그대로 유지하되 별도
   서브프로세스 대신 이 프로세스 안에서 직접 돈다. 세 시나리오(현재·되돌림·
   원복)가 같은 프로세스·같은 스크래치 DB를 공유하므로, 옛 워커가 매번
   고정값으로 썼던 사업자번호("1234567891")를 그대로 재사용하면 앞 시나리오가
   남긴 활성 업체가 뒤 시나리오의 중복확인에 잘못 걸린다 — 시나리오마다
   valid_biz_no()의 실제 검사식을 그대로 통과하는 새 번호를 생성해 격리한다.
"""
import io
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 493라운드 회귀 — 업체 정보수정 사업자번호 중복확인 경합")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 함수 전체를 통째로 추출")
# ──────────────────────────────────────────────────────────────
START = '@app.patch("/api/partners/<int:pid>")'
END_MARK = '    finally:\n        conn.close()\n'
_s = APP_SRC.find(START)
_e = APP_SRC.find(END_MARK, _s)
_e = _e + len(END_MARK) if _e > 0 else -1
CURRENT_FUNC = APP_SRC[_s:_e] if _s > 0 and _e > _s else ""

chk(bool(CURRENT_FUNC), "함수 전체를 찾았다")
chk(APP_SRC.count(CURRENT_FUNC) == 1, "함수 텍스트가 소스에 유일하다",
    APP_SRC.count(CURRENT_FUNC) if CURRENT_FUNC else 0)
chk("BEGIN IMMEDIATE" in CURRENT_FUNC, "BEGIN IMMEDIATE가 있다")
#  ⚠ [라운드562] 이 함수에 "값이 실제로 안 바뀌면 UPDATE·감사로그를 안 쏜다"는
#    형제(api_insurer_update, 라운드561) 기준의 새 조기반환(unchanged, 200)이
#    하나 더 생겨 정상적으로 5 → 6 이 됐다 — 이 자리도 그 앞의 것들처럼
#    conn.rollback() 으로 BEGIN IMMEDIATE 쓰기잠금을 놓는다.
chk(CURRENT_FUNC.count("conn.rollback()") == 6,
    "조기반환 6곳(404·DUP_BIZNO 409·unchanged 200[라운드562]·FORBIDDEN 403·"
    "강등거부·NEED_REASON 400) 모두 rollback을 한다", CURRENT_FUNC.count("conn.rollback()"))

#  이 세션이 수정 직전에 직접 Read로 확인해 둔 원본(라운드493 이전) 전체 텍스트.
ORIGINAL_FUNC = '''@app.patch("/api/partners/<int:pid>")
#  ⚠ 이 라우트로도 status 를 '퇴출'·'경고'·'활성' 으로 바꿀 수 있다 —
#    DELETE 쪽에만 중간관리자 문턱을 걸어 두면 옆문으로 그냥 지나간다.
#    (등급 검사는 본문에서 status 가 실제로 바뀔 때만 건다 — 연락처 수정까지 막을 이유는 없다.
#     실제 문턱은 아래 changed 계산 직후에 건다 — DB 현재값과 대조해야 "바뀐다"이지,
#     화면이 <select> 의 현재 선택값을 매번 함께 보내므로 본문에 있다는 것만으론 모른다)
@require_admin
def api_partner_update(pid):
    d = body()
    fields = ["name", "partner_type", "biz_no", "ceo", "major", "category", "region", "address",
              "phone", "email", "website", "license", "status", "doc_status"]
    sets, vals = [], []
    for f in fields:
        if f in d:
            #  ⚠ [라운드79] valid_biz_no() 검사식이 있는데(2126행, /api/partner/profile
            #    에서만 씀) 이 업체 정보수정 — 실제 상용 경로 — 엔 안 걸려 있었다.
            #    오타가 들어가면 KISCON 조회가 빈손으로 와 '무등록'으로 오판되고,
            #    협력사는 자기 프로필 수정으로도 못 고친다(값이 있으면 덮어쓰기 거부).
            if f == "biz_no" and d[f]:
                #  ⚠⚠ [429라운드] 형제(api_partner_profile_update, 3036행)는 하이픈을
                #    지운 숫자만 저장하는데 이 실사용 경로만 사용자가 입력한 표기를
                #    그대로 저장했다 — 같은 사업자를 하이픈 위치만 다르게 적으면
                #    아래 중복확인(round248과 같은 패턴)이 문자열 등치로는 못 잡는다.
                #    이 자리에서 정규화해 두면 148행 부근의 공용 저장 로직이
                #    자연히 정규화된 값을 쓴다.
                d[f] = re.sub(r"\\D", "", d[f])
                if not valid_biz_no(d[f]):
                    return jsonify({"ok": False,
                                    "error": "사업자등록번호가 올바르지 않습니다. "
                                             "10자리 숫자를 다시 확인해 주세요."}), 400
            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다 —
            #    같은 이유(형식오류가 여기선 안 걸리고 다른 화면에서만 걸림).
            if f == "phone" and d[f] and not RE_PHONE.match(d[f]):
                return jsonify({"ok": False,
                                "error": f"연락처 형식이 올바르지 않습니다: {d[f]}"}), 400
            #  ⚠ [라운드80] RE_EMAIL 검사가 연락처 수정(/api/contacts, 7640행)에만 있고
            #    이 업체 정보수정 — 훨씬 자주 쓰이는 경로 — 엔 없었다. 형식이 깨진
            #    주소가 여기로 들어가면, 나중에 연락처 화면에서 같은 값을 저장하려
            #    할 때만 400이 뜬다(두 화면이 같은 셀을 두고 어긋난다). 발송 대상
            #    집계(_campaign_recipients)는 비어있는지만 보므로 깨진 채로 캠페인에
            #    실려 나간다.
            if f == "email" and d[f] and not RE_EMAIL.match(d[f]):
                return jsonify({"ok": False,
                                "error": f"이메일 형식이 올바르지 않습니다: {d[f]}"}), 400
            #  ⚠ [라운드101] 이 필드는 검증 없이 그대로 기록됐다 — 오타 하나가 로그인
            #    허용집합·강등 관문 어디에도 안 걸리는 죽은 상태값을 만들어낼 수 있었다.
            if f == "status" and d[f] not in PARTNER_STATUSES:
                return jsonify({"ok": False,
                                "error": f"알 수 없는 업체 상태입니다: {d[f]}"}), 400
            #  ⚠⚠ [라운드174] status 와 같은 줄에서 예외 처리되던 형제 필드인데
            #    101라운드가 status 만 고치고 여기는 "화면이 <select> 로만 주는
            #    짧은 고정값이라" 남겨 뒀다 — 그런데 이 값은 통값입찰·재경매입찰
            #    (4662·4869행)이 문자열을 그대로 비교하는 자격 관문이다. 오타·임의
            #    값이 들어가면 그 업체는 아무 통지도 사유기록도 없이 조용히
            #    입찰길이 막힌다.
            if f == "partner_type" and d[f] not in PARTNER_TYPES:
                return jsonify({"ok": False,
                                "error": f"알 수 없는 업체 구분입니다: {d[f]}"}), 400
            #  ⚠⚠ [라운드169] 자기수정(api_partner_profile_update)은 같은 컬럼을
            #    전부 [:120] 으로 자르는데 이 실사용 경로(관리자 정보수정)엔 길이
            #    제한이 아예 없었다 — status/doc_status/partner_type 은 이미 별도
            #    검증(위)되거나 화면이 <select> 로만 주는 짧은 고정값이라 그대로 둔다.
            v = _s(d[f], FIELD_LIMITS.get(f, 200)) if f not in ("status", "doc_status", "partner_type") else d[f]
            sets.append(f"{f}=?"); vals.append(v)
    if "email" in d:
        #  ⚠⚠ [라운드299] 관리자가 여기(업체 정보수정, 연락처 전용 화면이 아닌
        #    일반 정보수정)에서 이메일을 고쳐도 email_source 가 안 바뀌는
        #    네 번째 자리였다(본인 마이페이지·연락처 수정·엑셀 일괄등록과
        #    같은 결함) — 그대로 두면 clean_collected_emails.py 가 여기서
        #    바로잡은 주소도 수집분으로 오판해 지울 수 있었다.
        sets.append("email_source=?"); vals.append("직접입력")
    #  주소를 검색으로 고쳐 잡으면 좌표도 같이 옮긴다(주소만 바뀌면 지도가 옛 자리를 가리킨다)
    got_fresh_coords = False
    if "lat" in d and "lng" in d:
        _nlat, _nlng = _picked_coords(d)
        if _nlat is not None:
            sets += ["lat=?", "lng=?", "geo_src=?"]
            vals += [_nlat, _nlng, "주소검색"]
            got_fresh_coords = True
    if not sets:
        return jsonify({"ok": True})
    conn = DB.get_db()
    try:
        prev = one(conn.execute(
            "SELECT name, status, address, lat, lng, biz_no FROM partners WHERE id=?", (pid,)))
        if not prev:
            return jsonify({"ok": False, "error": "없는 업체입니다."}), 404
        changed = "status" in d and (d.get("status") or "") != (prev["status"] or "")
        #  ⚠⚠ [429라운드] 형제(api_application_update 승인관문·api_partner_create,
        #    round248/429)는 같은 사업자번호로 활성 업체가 두 개 생기는 걸 막는데,
        #    기존 업체의 사업자번호를 이 화면에서 다른 활성 업체 것과 같은 값으로
        #    바꾸는 경로는 그 검사가 없었다.
        #  ⚠⚠ [라운드466] 위 방어가 "요청에 biz_no가 실려 있을 때만" 걸려 있었다
        #    — status만 '활성'으로 바꾸는(재승인) 요청은 biz_no를 안 보내도
        #    통과해, 이미 다른 활성 업체와 같은 사업자번호를 가진 채 잠자던
        #    계정을 그대로 활성화할 수 있었다(실측: status만 PATCH해 재현). 지금
        #    반영될 사업자번호(요청에 있으면 그 값, 없으면 기존 값)를 기준으로,
        #    "그 값으로 바뀌거나" "그 값을 가진 채 활성으로 바뀔 때" 둘 다 검사.
        _eff_biz = d["biz_no"] if ("biz_no" in d and d["biz_no"]) else prev["biz_no"]
        _biz_touched = "biz_no" in d and d["biz_no"]
        _activating = changed and (d.get("status") or "") == "활성"
        if (_biz_touched or _activating) and _eff_biz:
            _pdup = one(conn.execute(
                "SELECT name FROM partners WHERE biz_no=? AND status='활성' AND id<>?",
                (_eff_biz, pid)))
            if _pdup:
                return jsonify({
                    "ok": False, "code": "DUP_BIZNO",
                    "error": str(Markup(
                        "이미 등록된 업체입니다. (사업자번호 일치: {}) "
                        "중복이 아닌지 확인해 주세요.").format(escape(_pdup["name"])))}), 409
        #  ⚠⚠ [라운드154] round153이 cases 에 고친 것과 같은 결함 — 이 화면
        #    (#p_addr)은 AddrPick 자체가 없어 lat/lng 키가 절대 안 온다. 여기
        #    fields 루프는 값이 실제로 바뀌었는지 안 보고 요청에 있으면 무조건
        #    쓰므로(다른 필드도 전부 그렇다), address 가 **실제로** 바뀌었는지는
        #    지금 막 읽은 prev 와 대조해야 한다 — 안 그러면 관리자가 전화번호만
        #    고쳐도 주소가 "바뀐 것"으로 오판돼 멀쩡한 좌표까지 매번 지워진다.
        if (("address" in d and (d.get("address") or "").strip() != (prev["address"] or ""))
                and not got_fresh_coords
                and (prev["lat"] is not None or prev["lng"] is not None)):
            sets += ["lat=NULL", "lng=NULL", "geo_src=NULL"]
        # ⚠ 상태 강등은 이 경로(수정 모달)가 실제 상용 경로다. DELETE 에만 관문을 달면 구멍이 남는다.
        #  ⚠⚠ [라운드240] 예전엔 이 문턱 둘(등급검사·강등확인) 다 함수 맨 앞에서
        #    "본문에 status 키가 있는가"만으로 걸었다 — admin.js savePartner() 는
        #    관리자가 상태를 안 건드려도 <select> 의 현재 선택값을 매번 함께
        #    보내므로, "본문에 있다"≠"바뀐다"였다. 그 결과 하위관리자가 상태는
        #    그대로 두고 연락처 하나만 고쳐도 매번 "업체 상태 변경은 중간관리자
        #    이상만…"으로 거부됐다(바로 위 주석의 의도와 정반대, 실측: 저장
        #    100% 거부) — 그리고 이미 퇴출 등으로 내려가 있는 업체를 상태값
        #    그대로 재전송하며 다른 필드만 고쳐도 강등확인 관문(진행중 사건 有)에
        #    불필요하게 걸렸다. 여기서 이미 DB 현재값과 대조해 계산하는 changed
        #    를 그대로 재사용한다 — 실제로 바뀔 때만 두 문턱 모두 건다.
        if changed and _admin_rank() < ROLE_RANK["중간관리자"]:
            return jsonify({"error": "업체 상태 변경은 중간관리자 이상만 할 수 있습니다.",
                            "code": "FORBIDDEN"}), 403
        if changed:
            blocked = _partner_demote_gate(conn, pid, d.get("status"), d.get("confirm_demote"))
            if blocked:
                return blocked
        # 상태를 바꿀 때는 **사유를 남긴다**. 이유 없는 강등은 당사자가 다툴 수도,
        # 우리가 나중에 설명할 수도 없다(협력사에게는 생계가 걸린 처분이다).
        #  ⚠⚠ [331라운드] reason·insurer_instruction 류 자유텍스트는 [:300]으로
        #    자르는 관례(4177·4401·10629·13232·19386행)가 있는데, 이름이
        #    "reason"이 아니라 "status_reason"이라 grep에 안 걸려 이 필드
        #    전체(협력사·보험사 상태변경·퇴출)가 이 관례에서 빠져 있었다.
        reason = (d.get("status_reason") or "").strip()[:300]
        if changed and len(reason) < 5:
            return jsonify({"ok": False, "code": "NEED_REASON",
                            "error": "업체 상태를 바꾸려면 사유를 5자 이상 적어 주세요. "
                                     "사유는 업체에게도 함께 통지됩니다."}), 400
        if changed:
            sets += ["status_reason=?", "status_changed_at=datetime('now','+9 hours')",
                     "status_changed_by=?"]
            vals += [reason, actor()]
        vals.append(pid)
        conn.execute(f"UPDATE partners SET {','.join(sets)} WHERE id=?", vals)
        detail = f"#{pid}" + (f" 상태 {prev['status']}→{d['status']} (사유: {reason})" if changed else "")
        DB.log(conn, actor(), "업체 정보수정", detail)
        if changed:
            notify(conn, "업체상태변경", "알림톡", prev["name"] or "",
                   f"협력사 상태가 '{prev['status']}'에서 '{d['status']}'(으)로 변경되었습니다. "
                   f"사유: {reason}",
                   audience_type="partner", partner_id=pid, url="/app/partner")
        conn.commit()
        return jsonify({"ok": True})
    finally:
        conn.close()
'''

chk("BEGIN IMMEDIATE" not in ORIGINAL_FUNC, "원본 텍스트에는 BEGIN IMMEDIATE가 없다(대조군)")
chk(ORIGINAL_FUNC.count("conn.rollback()") == 0,
    "원본은 조기반환 5곳 모두 rollback이 전혀 없다(대조군)",
    ORIGINAL_FUNC.count("conn.rollback()"))

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 준비 — 스크래치 DB + 실제 Flask 인프로세스 호출(진짜 스레드 경합)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round493_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB                 # noqa: E402
DB.init_db()
import app as A                  # noqa: E402

_seed_n = [0]


def _gen_biz_no(seq):
    """valid_biz_no()의 실제 검사식을 그대로 통과하는 서로 다른 사업자번호를
    시나리오마다 새로 만든다 — 세 시나리오가 같은 스크래치 DB를 공유하므로
    옛 워커처럼 고정값을 재사용하면 앞 시나리오가 남긴 활성 업체가 뒤
    시나리오의 중복확인에 잘못 걸린다."""
    prefix = f"{100000000 + seq:09d}"
    for chk_digit in range(10):
        cand = prefix + str(chk_digit)
        if A.valid_biz_no(cand):
            return cand
    raise AssertionError(f"체크섬 후보를 못 찾음: {prefix}")


def _seed_two_partners():
    """매 시나리오(현재/되돌림/원복)마다 독립된 관리자 2명·심사중 업체 2곳·
    새 사업자번호를 만들어 세 번의 호출이 서로 간섭하지 않게 한다(옛 워커의
    시드 로직)."""
    _seed_n[0] += 1
    n = _seed_n[0]
    c = DB.get_db()
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('pa{n}','x','n1','최고관리자')")
    c.execute("INSERT INTO admins(username,password_hash,name,role) "
              f"VALUES('pb{n}','x','n2','최고관리자')")
    pid1 = c.execute(f"INSERT INTO partners(name,status) VALUES('A상사{n}','심사중')").lastrowid
    pid2 = c.execute(f"INSERT INTO partners(name,status) VALUES('B상사{n}','심사중')").lastrowid
    c.commit(); c.close()
    return pid1, pid2, _gen_biz_no(n), f"pa{n}", f"pb{n}"


def _run_concurrent_update(pid1, pid2, biz_no, u1, u2):
    """옛 워커(test_scan_round493_worker.py, 더 이상 생성 안 함)의 로직을 그대로
    옮김 — DB.get_db를 감싸, 중복확인 SELECT가 실행될 때 두 요청이 같은
    순간에 도달하도록 threading.Barrier로 강제한다."""
    cl1 = A.app.test_client()
    cl2 = A.app.test_client()
    with cl1.session_transaction() as s:
        s["admin"] = u1; s["admin_role"] = "최고관리자"; s["_csrf"] = "c1"
    with cl2.session_transaction() as s:
        s["admin"] = u2; s["admin_role"] = "최고관리자"; s["_csrf"] = "c2"

    barrier = threading.Barrier(2, timeout=5)
    hit = {"n": 0}
    hit_lock = threading.Lock()

    class _Probe:
        def __init__(self, real):
            self._real = real

        def execute(self, sql, params=()):
            if "status='활성' AND id<>" in sql:
                with hit_lock:
                    hit["n"] += 1
                try:
                    barrier.wait()
                except threading.BrokenBarrierError:
                    pass
            return self._real.execute(sql, params)

        def __getattr__(self, name):
            return getattr(self._real, name)

    _real_get_db = DB.get_db

    def _patched():
        return _Probe(_real_get_db())

    results = {}

    def worker(key, cl, hdr, pid):
        r = cl.patch(f"/api/partners/{pid}",
                     json={"biz_no": biz_no, "status": "활성", "status_reason": "심사완료함"},
                     headers=hdr)
        results[key] = (r.status_code, (r.get_json() or {}).get("code"))

    DB.get_db = _patched
    t1 = threading.Thread(target=worker, args=("t1", cl1, {"X-CSRF-Token": "c1"}, pid1))
    t2 = threading.Thread(target=worker, args=("t2", cl2, {"X-CSRF-Token": "c2"}, pid2))
    t1.start(); t2.start(); t1.join(15); t2.join(15)
    DB.get_db = _real_get_db

    conn = A.DB.get_db()
    dup_rows = conn.execute(
        "SELECT id FROM partners WHERE biz_no=? AND status='활성'", (biz_no,)).fetchall()
    conn.close()
    return {"barrier_hits": hit["n"], "r1": list(results.get("t1", (None, None))),
            "r2": list(results.get("t2", (None, None))), "dup_active_count": len(dup_rows)}


try:
    pid1a, pid2a, biz_a, u1a, u2a = _seed_two_partners()
    out = _run_concurrent_update(pid1a, pid2a, biz_a, u1a, u2a)
    chk(out["barrier_hits"] == 2, "두 요청 모두 중복확인 SELECT 지점까지 도달했다(배리어 동기화 성공)", out)
    codes = sorted([tuple(out["r1"]), tuple(out["r2"])])
    chk(codes == [(200, None), (409, "DUP_BIZNO")],
        "★★★★★ 새 코드: 진짜 동시요청이어도 정확히 하나는 성공(200)하고 "
        "나머지 하나는 DUP_BIZNO(409)로 막힌다(어느 쪽이 이기는지는 비결정적이나 "
        "결과 조합은 항상 이렇다 — BEGIN IMMEDIATE의 write-lock이 직렬화해, "
        "나중 커넥션은 먼저 커밋된 최신 상태를 보고 스스로 막는다)", out)
    chk(out["dup_active_count"] == 1,
        "★★★★★ 새 코드: 두 요청이 동시에 도착해도 같은 사업자번호로 활성 업체가 "
        "정확히 1곳만 존재한다(중복 없음)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — view_functions 딕셔너리 항목만 잠깐 치환(실제 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    assert CURRENT_FUNC, "함수를 못 뽑아 되돌림-증명을 진행할 수 없다"
    _marker = "def api_partner_update(pid):"
    ORIGINAL_BODY_FOR_EXEC = _marker + ORIGINAL_FUNC.split(_marker, 1)[1]
    _ns = dict(vars(A))
    exec(compile(ORIGINAL_BODY_FOR_EXEC, "<round493_reverted_api_partner_update>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_fn = A.require_admin(_ns["api_partner_update"])

    _orig_view = A.app.view_functions["api_partner_update"]
    A.app.view_functions["api_partner_update"] = old_fn
    try:
        pid1b, pid2b, biz_b, u1b, u2b = _seed_two_partners()
        out2 = _run_concurrent_update(pid1b, pid2b, biz_b, u1b, u2b)
    finally:
        A.app.view_functions["api_partner_update"] = _orig_view

    chk(out2["r1"][0] == 200 and out2["r2"][0] == 200,
        "★★★★★ 옛 코드(되돌림): 두 PATCH 모두 200으로 통과한다(중복확인이 서로를 못 봄)"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["dup_active_count"] == 2,
        "★★★★★ 옛 코드(되돌림): 같은 사업자번호로 활성 업체 2곳이 동시에 생긴다"
        "(round248/429/466이 막으려던 바로 그 상태 재현)", out2)

    print("\n[4] 원복 확인 — 되돌리기 이후 다시 직렬화되는가(바꿔치기가 안 샜다)")
    chk(A.app.view_functions["api_partner_update"] is _orig_view,
        "  view_functions가 원래 함수객체로 복원됐다")
    pid1c, pid2c, biz_c, u1c, u2c = _seed_two_partners()
    out3 = _run_concurrent_update(pid1c, pid2c, biz_c, u1c, u2c)
    codes3 = sorted([tuple(out3["r1"]), tuple(out3["r2"])])
    chk(codes3 == [(200, None), (409, "DUP_BIZNO")] and out3["dup_active_count"] == 1,
        "★★★★ 원복 후에는 다시 하나만 성공·나머지 DUP_BIZNO로 막힌다(바꿔치기가 안 샜다)", out3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py가 이 테스트 실행 내내 실제로 한 번도 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
