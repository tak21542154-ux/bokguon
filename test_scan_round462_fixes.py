# -*- coding: utf-8 -*-
"""스캔 462라운드 회귀 — 1차합의 개시(field-agreement open) 재시도 시
알림 중복발송, 1건.

`dispatch.open_agreement()`는 이미 검토중인 합의가 있으면 새로 안
만들고 기존 id를 그대로 돌려준다(중복 생성 방지, 정상). 그런데 호출부
(`api_field_agreement_open`, app.py)는 그 반환값이 신규생성인지
재사용인지 구분하지 않고 항상 보험사·운영팀 notify()를 불렀다 —
더블클릭·네트워크 재시도·거의 동시 요청마다 매번 `notifications`
행이 새로 쌓였다(라운드228이 이미 확립한 "duplicate:true 조기반환"
관용구를 이 자리에도 이식).

[1] 소스 확인 — 재사용 조기반환 코드가 실제로 있음.
[2] 실제 Flask 앱(스크래치 DB, 한 프로세스)으로 되돌림-증명 — 진짜
    app.py 파일은 전혀 안 건드리고 A.app.view_functions
    ["api_field_agreement_open"] 딕셔너리 항목만 462 이전 버전(이 파일
    안에서 exec 로 재구성)으로 임시 치환해, 옛 동작이 실제로 재현되는지
    (알림 4건으로 새는지) · 지금 코드가 실제로 막는지(2건에서 멈추는지)
    대조한다.

    ⚠⚠ [라운드613] 원래는 이 대조를 위해 app.py를 실제로 되돌려 쓴 뒤
    (디스크에 깨진 코드가 잠깐 실존 — 그 창을 다른 세션이 관측하면
    충돌한다, round590이 실제로 겪음) 별도 서브프로세스
    (test_scan_round462_worker.py)를 두 번 띄우는 방식이었다. round411·
    610이 확립한 안전패턴(view_functions 딕셔너리 항목 임시치환 + exec 로
    사본 네임스페이스 재구성)으로 이관 — 워커 파일은 더 이상 안 쓰여
    삭제했다(이제 한 프로세스 안에서 지금 코드 실행 → 치환 → 옛 코드
    실행 → 원복 순서로 전부 처리).
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 462라운드 회귀 — 1차합의 개시 재시도 알림 중복발송")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

NEW_BLOCK = '''        _existing = conn.execute(
            "SELECT id FROM field_agreements WHERE case_id=? AND status=?",
            (cid, DP.AG_REVIEW)).fetchone()
        if _existing:
            return jsonify({"ok": True, "duplicate": True, "agreement_id": _existing["id"],
                            "agreement": DP.agreement_view(conn, cid) or {}})
        aid = DP.open_agreement(conn, cid, engine_low=lo, engine_high=hi,'''

OLD_LINE = "        aid = DP.open_agreement(conn, cid, engine_low=lo, engine_high=hi,"

chk(NEW_BLOCK in APP_SRC,
    "★★★★★ api_field_agreement_open()에 재사용 조기반환 코드가 있다")
chk(APP_SRC.count(OLD_LINE) == 1,
    "되돌림-증명에 쓸 옛 줄이 소스에 정확히 1번만 있다(대체 지점 특정 가능)",
    APP_SRC.count(OLD_LINE))


def _route_body(src, fn_name):
    """라우트 함수 정의 하나만 떼어낸다 — 바로 다음 라우트가 데코레이터로
    시작하므로 '\\ndef '로 끝을 찾으면 그 데코레이터까지 통째로 삼켜(round612
    gotcha) 단독 exec 시 SyntaxError가 난다. 이 코드베이스의 최상위 함수
    사이 관례인 '\\n\\n\\n'(빈줄 2개)로 끝을 찾아 데코레이터 앞에서 멈춘다."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.index("\n\n\n", start + 1)
    return src[start + 1:end]


print("\n[2] 실행 준비 — 스크래치 DB, 관리자 1명 + 보험사 1건 + 업체 1곳")
_tmpdir = tempfile.mkdtemp(prefix="round462_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB
    DB.init_db()
    import dispatch as DP
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    iid = conn.execute("INSERT INTO insurers(name,status) VALUES('R462보험','활성')").lastrowid
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,lat,lng) "
        "VALUES('R462업체','시행사','활성',37.5,127.0)").lastrowid
    conn.commit()

    def _admin_client():
        c = A.app.test_client()
        with c.session_transaction() as sess:
            sess["admin"] = "admin"
            sess["admin_name"] = "검증"
            sess["admin_role"] = "최고관리자"
            sess["_csrf"] = "r462-csrf"
        return c

    def _ready_case(no):
        """출동 배정→수락→도착까지 실제로 진행시킨 사건 1건을 만든다
        (1차합의 개시의 선행조건 — 예전 worker.py가 하던 절차와 동일)."""
        cid = conn.execute(
            "INSERT INTO cases(case_no,status,category,region,insurer_id,lat,lng) "
            "VALUES(?,'접수','가드레일','서울',?,37.5,127.0)", (no, iid)).lastrowid
        conn.commit()
        did, _called, _sent = DP.open_dispatch(conn, cid)
        conn.commit()
        ok_a, _msg_a, did2 = DP.assign_dispatch(conn, cid, pid, "테스트 직접배정")
        conn.commit()
        use_did = did2 if ok_a else did
        DP.claim(conn, use_did, pid, "R462업체")
        conn.commit()
        ok_r, msg_r = DP.arrive(conn, use_did, pid, photo_count=3, field_estimate=800000)
        conn.commit()
        if not ok_r:
            raise RuntimeError(f"arrive 준비 실패: {msg_r}")
        return cid

    def _counts(cid):
        n_notify = conn.execute(
            "SELECT COUNT(*) n FROM notifications WHERE ntype='합의승인요청' AND case_id=?",
            (cid,)).fetchone()["n"]
        n_agreements = conn.execute(
            "SELECT COUNT(*) n FROM field_agreements WHERE case_id=?", (cid,)).fetchone()["n"]
        return n_notify, n_agreements

    print("\n[3] 실행 — 지금(고쳐진) 코드로 라우트를 두 번 연속 호출")
    cid_fixed = _ready_case("26-462001")
    c1 = _admin_client()
    r1 = c1.post(f"/api/cases/{cid_fixed}/field-agreement", json={},
                 headers={"X-CSRF-Token": "r462-csrf"})
    r2 = c1.post(f"/api/cases/{cid_fixed}/field-agreement", json={},
                 headers={"X-CSRF-Token": "r462-csrf"})
    rb1, rb2 = r1.get_json() or {}, r2.get_json() or {}
    n_notify_fixed, n_agree_fixed = _counts(cid_fixed)

    chk(rb1.get("duplicate") is not True,
        "첫 호출은 신규생성(duplicate 표시 없음)", rb1)
    chk(rb2.get("duplicate") is True,
        "★★★★★ 재시도(2번째 호출)는 duplicate:true로 조용히 성공만 돌려준다", rb2)
    chk(n_agree_fixed == 1,
        "field_agreements는 원래도 1건으로 막혀 있다(회귀 아님)", n_agree_fixed)
    chk(n_notify_fixed == 2,
        "★★★★★ 고쳐진 코드는 두 번 호출해도 알림이 2건(최초 1회분)만 쌓인다",
        n_notify_fixed)

    print("\n[4] 되돌리기 — view_functions 항목만 462 이전 버전으로 임시 치환"
          "(디스크 미기록)")
    _route_src = _route_body(APP_SRC, "api_field_agreement_open")
    chk(NEW_BLOCK in _route_src,
        "  (준비) 추출한 라우트 본문이 새(고친) 코드블록을 담고 있다")
    reverted_route_src = _route_src.replace(NEW_BLOCK, OLD_LINE)
    chk(reverted_route_src != _route_src,
        "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    #  ⚠ require_role("중간관리자") 데코레이터는 재적용하지 않는다(round610과
    #    같은 전례) — 이 사본은 view_functions 에만 임시로 걸리고, 아래
    #    admin_role="최고관리자" 세션은 그 등급검사를 어차피 통과하므로
    #    이 회귀가 검증하려는 대상(알림 중복)과는 무관하다.
    _ns = dict(vars(A))
    exec(compile(reverted_route_src, "<round462_old_api_field_agreement_open>", "exec"), _ns)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_view = _ns["api_field_agreement_open"]

    _orig_view = A.app.view_functions["api_field_agreement_open"]
    A.app.view_functions["api_field_agreement_open"] = old_view
    try:
        cid_broken = _ready_case("26-462002")
        c2 = _admin_client()
        r3 = c2.post(f"/api/cases/{cid_broken}/field-agreement", json={},
                     headers={"X-CSRF-Token": "r462-csrf"})
        r4 = c2.post(f"/api/cases/{cid_broken}/field-agreement", json={},
                     headers={"X-CSRF-Token": "r462-csrf"})
        rb3, rb4 = r3.get_json() or {}, r4.get_json() or {}
        n_notify_broken, n_agree_broken = _counts(cid_broken)

        chk("duplicate" not in rb3 and "duplicate" not in rb4,
            "옛 코드(되돌림)는 duplicate 표시 자체가 없다(구분할 방법이 없었음을 증명)",
            (rb3.get("duplicate"), rb4.get("duplicate")))
        chk(n_agree_broken == 1,
            "옛 코드에서도 field_agreements 자체는 1건으로 막힌다"
            "(대조군 — dispatch.py는 안 건드림)", n_agree_broken)
        chk(n_notify_broken == 4,
            "★★★★★ 옛 코드(되돌림)는 두 번 호출하면 알림이 실제로 4건(2회×2건)"
            " 쌓인다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명",
            n_notify_broken)
    finally:
        A.app.view_functions["api_field_agreement_open"] = _orig_view

    print("\n[5] 원복 확인 — 복원 후에는 재시도가 다시 duplicate:true 로 돌아온다")
    cid_restored = _ready_case("26-462003")
    c3 = _admin_client()
    r5 = c3.post(f"/api/cases/{cid_restored}/field-agreement", json={},
                 headers={"X-CSRF-Token": "r462-csrf"})
    r6 = c3.post(f"/api/cases/{cid_restored}/field-agreement", json={},
                 headers={"X-CSRF-Token": "r462-csrf"})
    rb6 = r6.get_json() or {}
    chk(rb6.get("duplicate") is True,
        "★★★★ 원복 후에는 재시도가 다시 duplicate:true로 돌아온다(바꿔치기가 안 샜다)",
        rb6)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2] 준비/실행", f"{type(e).__name__}: {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

APP_SRC_AFTER = io.open(APP_PATH, encoding="utf-8").read()
chk(APP_SRC_AFTER == APP_SRC,
    "★★★★★ app.py 파일 내용이 시작부터 끝까지 전혀 안 바뀌었다"
    "(view_functions 딕셔너리 항목 임시치환만 사용 — 디스크에 깨진 코드를 쓴 적 없음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
