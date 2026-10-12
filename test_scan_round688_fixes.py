# -*- coding: utf-8 -*-
"""스캔 688라운드 회귀 — 입점신청 직접접수(api_application_create)의 업체명 중복확인이
유니코드 정규화 형태를 안 봐서 같은 업체가 심사대기 상태로 두 번 등록될 수 있던 결함.

  배경 — round594가 "app.py 전체에서 name= 류 SQL 바이트비교를 쓰는 자리" 전수확인 중
  이 함수의 "SELECT id, status FROM partner_applications WHERE company=? AND status IN
  ('신규','서류검토')"를 round458(보험사명 등록)·round593(연락처 일괄등록 업체명 대조)과
  같은 결함군의 "두 번째 인스턴스"로 이미 지목했으나, 그 라운드 자신은 손대지 않고 별도
  태스크(task_f15d21d5)로 이관만 해 두었다(run_all_tests.py 등록문구에 명시). 이번
  라운드가 그 이관된 항목을 직접 조사해 실제로 재현·수정한다.

  ⚠ 라운드 번호 경합(두 번) — 이 저장소는 git 없이 여러 세션이 동시에 돌 수 있어
  (round279~281 선례) 이번 작업 중 실제로 두 번 부딪혔다: 처음 "682"로 쓰던 중 다른
  세션이 완전히 무관한 건(check_subcontractor 화면배선)으로 682번을 먼저 선점해
  test_scan_round682_fixes.py를 덮어썼고, "683"으로 옮겨 다시 쓰자 그 세션도 **같은
  타이밍에 독립적으로** 683으로 옮겨와 다시 부딪혔다. ListAgents로 그 세션(check_
  subcontractor 담당)을 실제로 찾아 SendMessage로 조율해 688번으로 최종 이동했다 —
  app.py 수정분(다른 함수, 다른 파일영역)은 두 충돌 모두에서 무사했고, 테스트 파일·
  run_all_tests.py 등록 항목만 그때마다 새 번호로 옮겨 다시 적었다.

  결함 — 단순 SQL "WHERE company=?" 바이트열 비교라, 유니코드는 같은 글자를 다른
  바이트열로도 적을 수 있어(한글 자모를 완성형 대신 풀어쓴 NFD — 맥에서 복사한 텍스트에
  흔하다) 시각적으로 완전히 같은 업체명이 이 중복확인을 그대로 통과한다. 사업자번호가
  있으면 승인 시점(api_application_update)의 biz_no 교차확인이 안전망 역할을 하지만,
  사업자번호가 없거나 신청마다 다르게 기재되면 그 안전망도 없다 — 같은 회사의 대기
  신청서가 이 심사대기 큐에 두 번 쌓인다. partner_applications.company는 이 함수와
  공개 폼(api_create_application) 두 경로가 각자 다른 시점에 채우고 db.py에 정규화
  마이그레이션도 없어, 과거 데이터의 정규화 형태를 보장할 수 없다 — round458(등록
  시점 한 곳만 정규화하면 끝나는 단일 쓰기경로)이 아니라 round593(대조 자체를 정규화
  후 비교로 바꾸는 처방)과 같은 이유·같은 처방이 맞는다.

  ⚠ 조사 중 확인 — 과제 설명이 말한 "공개폼 형제가 같은 SQL을 쓴다"는 현재 코드와
  다르다. 공개 폼(api_create_application, POST /api/applications)의 중복확인은
  이 함수와 다른 헬퍼 recent_duplicate()(업체명+전화번호+10분 창의 재전송 방지용,
  status 무관)뿐이고 이 status 기반 심사대기 중복확인 자체가 없다 — 이번 라운드는
  과제가 실제로 가리키는 결함(이 함수의 status IN (...) 대조)만 고친다.
  recent_duplicate()의 company=? 비교도 원론적으로는 같은 결함군이지만 위협모델이
  다르고(같은 브라우저 탭의 10분 내 재전송 방지용 UX 디바운스, 심사대기 중복방지가
  아님) 범위가 달라 이번 수정 대상에 포함하지 않는다.

  고침 — round593과 같은 자리·같은 방식: 지금 심사대기 중(status IN ('신규',
  '서류검토'))인 후보만 읽어(이미 이 필터가 대상을 좁혀 두므로 round593처럼 잠금
  앞으로 뺄 것도 없이 그대로 BEGIN IMMEDIATE 안에서 읽는다) 업체명을 NFKC로
  정규화해 대조한다. 새 헬퍼·새 컬럼·새 정책 없음.

  [1] 소스 확인 — 새 정규화 비교가 실제로 있고 옛 바이트비교 SQL은 없음.
  [2] 핵심 재현 — NFC로 접수한 업체를 NFD 표기로 다시 접수하면 이제 409로 막힌다.
  [3] 되돌림-증명 — unicodedata.normalize를 프로세스 메모리에서만(디스크 무수정)
      항등함수로 바꿔치기해 옛(취약) 동작 — 중복을 못 잡고 그대로 접수됨 — 이
      실제로 재현됨을 확인한 뒤 원복.
  [4] 회귀 없음 — 바이트가 완전히 같은 업체명 중복은 예전처럼 그대로 막힌다.
  [5] 인접 안전성 — (a) 서로 무관한 업체명끼리는 오탐이 없다. (b) 이전 신청이
      반려(심사대기 상태 아님)면, 정규화 표기만 다른 재신청도 status 필터가
      그대로 지켜져 정상 접수된다(과잉 차단 아님).

      python test_scan_round688_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile
import unicodedata

try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\n@app.", start + 1)
    return src[start:end if end != -1 else None]


print("=" * 72)
print("  스캔 688라운드 회귀 — 입점신청 직접접수 업체명 중복확인 유니코드 정규화 불일치")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()

try:
    fn_body = _py_fn_body(APP_SRC, "api_application_create")
    chk('_norm_company = unicodedata.normalize("NFKC", company)' in fn_body,
        "★★★★★ api_application_create가 접수 업체명을 NFKC로 정규화한다")
    chk('unicodedata.normalize("NFKC", p["company"] or "") == _norm_company' in fn_body,
        "★★★★★ 심사대기 후보들의 업체명도 같은 방식으로 정규화해 대조한다")
    chk('"SELECT id, status FROM partner_applications WHERE company=? "' not in fn_body,
        "★★★ 예전 단순 바이트열 비교 SQL(WHERE company=?)은 이 함수에서 제거됐다")
    chk("BEGIN IMMEDIATE" in fn_body,
        "STEP round553이 추가한 BEGIN IMMEDIATE 잠금은 그대로 있다(회귀 없음)")
    chk("status IN ('신규','서류검토')" in fn_body,
        "STEP 심사대기 상태 필터(status IN)는 그대로 유지된다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[1] 소스 확인", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════
print("\n[2]~[5] 실제 Flask 앱 실행")
# ══════════════════════════════════════════════════════════════
_tmpdir = tempfile.mkdtemp(prefix="round688_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r688-csrf"

try:
    import db as DB
    DB.init_db()
    import app as A

    def _call(payload, path="/api/applications/manual"):
        """관리자 세션이 실린 test_request_context 안에서 뷰 함수를 직접 호출한다
        (round553의 _call_with_session과 같은 기법 — before_request 를 안 거치므로
        CSRF 헤더 없이도 안전하게 뷰 로직만 검증한다)."""
        with A.app.test_request_context(path, method="POST", json=payload):
            from flask import session as _s
            _s["admin"] = "r688admin"; _s["admin_name"] = "검증"; _s["admin_role"] = "최고관리자"
            _s["_csrf"] = CSRF
            resp = A.api_application_create()
        if isinstance(resp, tuple):
            return resp[1], resp[0].get_json()
        return 200, resp.get_json()

    def _company_count(*names):
        qs = " OR ".join(["company=?"] * len(names))
        return DB.get_db().execute(
            f"SELECT COUNT(*) c FROM partner_applications WHERE {qs}", names).fetchone()["c"]

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('r688admin','x','검증','최고관리자')")
    conn0.commit(); conn0.close()

    # ── [2] 핵심 재현 — NFC로 접수된 업체를 NFD 표기로 다시 접수 ──
    NFC_NAME = "R688정규화검증업체"
    NFD_NAME = unicodedata.normalize("NFD", NFC_NAME)
    assert NFC_NAME != NFD_NAME, "테스트 전제(NFC!=NFD 바이트다름) 불성립"

    code1, body1 = _call({"company": NFC_NAME, "major": "가드레일·방호울타리", "phone": "010-1111-2222"})
    chk(code1 == 200 and body1.get("ok") is True,
        "STEP 첫 접수(NFC 표기)는 정상적으로 200·ok:true", (code1, body1))

    code2, body2 = _call({"company": NFD_NAME, "major": "가드레일·방호울타리", "phone": "010-1111-2222"})
    chk(code2 == 409 and body2.get("ok") is False
        and "이미 심사 중인 신청이 있습니다" in (body2.get("error") or ""),
        "★★★★★ NFD 표기로 같은 업체를 다시 접수하면 이제 409로 막힌다"
        "(예전엔 바이트가 달라 통과해 대기 신청서가 2건 생겼다)", (code2, body2))
    chk(_company_count(NFC_NAME, NFD_NAME) == 1,
        "★★★★★ 실제 DB에도 대기 신청서가 정확히 1건만 쌓였다", _company_count(NFC_NAME, NFD_NAME))

    # ── [3] 되돌림-증명 — normalize를 프로세스 메모리에서만 항등함수로 ──
    NFC_NAME2 = "R688되돌림검증업체"
    NFD_NAME2 = unicodedata.normalize("NFD", NFC_NAME2)
    assert NFC_NAME2 != NFD_NAME2, "테스트 전제(NFC!=NFD 바이트다름) 불성립"

    code3, body3 = _call({"company": NFC_NAME2, "major": "가드레일·방호울타리", "phone": "010-2222-3333"})
    chk(code3 == 200 and body3.get("ok") is True, "STEP (되돌림 준비) 첫 접수는 200", (code3, body3))

    _orig_normalize = A.unicodedata.normalize
    A.unicodedata.normalize = lambda form, s: s  # 정규화를 안 한 것과 동일 효과
    try:
        code4, body4 = _call({"company": NFD_NAME2, "major": "가드레일·방호울타리", "phone": "010-2222-3333"})
        chk(code4 == 200 and body4.get("ok") is True,
            "★★★★★ 정규화를 되돌리면 NFD 표기가 다른 업체로 오인되어 그대로 접수된다"
            "(라운드688이 막으려던 바로 그 사고 — 이 테스트가 진짜 결함을 잡아낼 능력이 "
            "있음을 증명)", (code4, body4))
    finally:
        A.unicodedata.normalize = _orig_normalize
    chk(_company_count(NFC_NAME2, NFD_NAME2) == 2,
        "★★★★★ 되돌린 상태에서는 실제로 대기 신청서가 2건 생겼다", _company_count(NFC_NAME2, NFD_NAME2))

    # ── [4] 회귀 없음 — 바이트가 완전히 같은 업체명은 여전히 막힌다 ──
    NFC_NAME3 = "R688일반중복업체"
    code5, body5 = _call({"company": NFC_NAME3, "major": "유리·샷시·자동문", "phone": "010-3333-4444"})
    chk(code5 == 200, "STEP (회귀 준비) 첫 접수는 200", (code5, body5))
    code6, body6 = _call({"company": NFC_NAME3, "major": "유리·샷시·자동문", "phone": "010-3333-4444"})
    chk(code6 == 409 and "이미 심사 중인 신청이 있습니다" in (body6.get("error") or ""),
        "STEP 바이트가 완전히 같은 업체명(기존 절대다수 경로)은 그대로 409로 막힌다"
        "(과잉 변경 아님)", (code6, body6))

    # ── [5-a] 인접 안전성 — 서로 무관한 업체명은 오탐 없음 ──
    code7, body7 = _call({"company": "R688무관업체A", "major": "방수", "phone": "010-4444-5555"})
    code8, body8 = _call({"company": "R688무관업체B", "major": "방수", "phone": "010-5555-6666"})
    chk(code7 == 200 and code8 == 200,
        "STEP 서로 다른(정규화와 무관한) 업체명 둘 다 각각 정상 접수된다(오탐 없음)",
        (code7, body7, code8, body8))

    # ── [5-b] 인접 안전성 — 반려된 신청은 status 필터로 재접수를 막지 않는다 ──
    NFC_NAME4 = "R688반려후재신청업체"
    NFD_NAME4 = unicodedata.normalize("NFD", NFC_NAME4)
    assert NFC_NAME4 != NFD_NAME4, "테스트 전제(NFC!=NFD 바이트다름) 불성립"
    code9, body9 = _call({"company": NFC_NAME4, "major": "방수", "phone": "010-6666-7777"})
    chk(code9 == 200, "STEP (준비) 첫 접수는 200", (code9, body9))
    conn = DB.get_db()
    conn.execute("UPDATE partner_applications SET status='반려' WHERE company=?", (NFC_NAME4,))
    conn.commit(); conn.close()
    code10, body10 = _call({"company": NFD_NAME4, "major": "방수", "phone": "010-6666-7777"})
    chk(code10 == 200 and body10.get("ok") is True,
        "★★★★ 이전 신청이 반려(심사대기 아님)면, 표기만 다른(NFD) 재신청도 여전히 "
        "정상 접수된다(status IN 필터가 정규화 비교로 바뀌어도 그대로 지켜짐 — 과잉 차단 아님)",
        (code10, body10))

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]~[5] 실제 앱 재현 준비/실행", f"{type(e).__name__}: {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
