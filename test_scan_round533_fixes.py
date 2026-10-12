# -*- coding: utf-8 -*-
"""스캔 533라운드 회귀 — 개인정보 처리방침 제6조(처리 위탁) 표에 주소검색(카카오)
   위탁처가 통째로 빠져 있던 결함[컴플라이언스, round508과 같은 클래스의 새 사례].

   직접 조사(하위위임 없음) — 지시받은 예시 각도(입력길이 상한·cases.status 동시성
   ·is_demo 이외 플래그·비밀번호 재설정 토큰·이모지/서로게이트 SMS·관리자 삭제 세션
   무효화)를 전부 실측 대조했으나 전부 클린이었다: cases.status 를 건드리는 UPDATE
   16곳 전수확인 결과 전부 BEGIN IMMEDIATE 안에 있었고(app.py, 스크립트로 함수경계
   자동추출해 확인), SMS 바이트계산(notify_popbill._euckr_len/_euckr_cut)은 이모지·
   단독서로게이트·ZWJ 전부 cp949 errors="replace" 로 1바이트씩 안전 치환됨을 실행
   확인, 엑셀 내보내기(_xl_safe)는 제어문자·수식주입 방어가 이미 통일돼 있고,
   비밀번호 재설정은 토큰링크가 아니라 관리자가 임시비밀번호를 즉시 발급하는 구조라
   토큰만료 개념 자체가 없으며, 관리자 계정 삭제·강등은 _account_alive() 가 매
   요청마다 DB 를 재확인해 세션을 즉시 무효화한다(이미 촘촘). is_demo 외의 소프트
   삭제류 플래그는 스키마 전체에 없다(db.py 검색 결과 없음).

   그래서 각도를 "이미 점검한 코드 경로"에서 "이미 한 번 발견됐던 결함의 형제가
   또 있는가"로 옮겨 round508(처리위탁 표 누락) 을 다시 봤다 — 그 라운드는
   photo_ai.py(Gemini) 위탁 누락만 고쳤을 뿐, "이 표에 실제로 나가야 하는 항목이
   그것 하나뿐인가"는 되묻지 않았다.

   실측 — addr_search.py(/api/address/search, app.py:18377, 운영자·보험사·협력사가
   사건/협력업체 등록 화면에서 주소를 검색할 때 공용으로 부르는 서버 프록시)는
   사용자가 입력한 주소 문자열을 카카오로 그대로 전송한다: KAKAO_REST_KEY 가 있으면
   dapi.kakao.com(카카오 로컬 API), 없으면 search.map.kakao.com(공개 엔드포인트)으로
   자동 폴백한다 — 그 모듈 자신의 docstring 이 "키 없이도 오늘 당장 동작한다"고
   명시한다. legal_docs.py 제2조 표(155·160행)는 이미 "사업장 주소(위치정보 포함)"·
   "사고 현장 주소"를 수집 항목으로 명시하는데, 그 값을 실제로 좌표로 바꾸려고
   외부(카카오)로 내보낸다는 사실은 제6조(위탁) 표 어디에도 없었다.

   round508(Gemini)과의 결정적 차이 — Gemini 위탁은 BOKGUON_GEMINI_KEY 가 없으면
   "실제로 아무 사진도 안 나가"(그 라운드 자신의 표현) 조건부로 감싸야 했다. 반면
   이 주소검색은 **끌 수 있는 스위치가 없다** — KAKAO_REST_KEY 유무는 두 카카오
   엔드포인트 중 어디로 갈지만 가르지, "카카오로 안 보낸다"는 상태가 없다. 그래서
   round508 처럼 ai_photo_enabled 류 플래그로 조건부 삽입하면 오히려 부정확한
   문서가 된다(항상 하는 일을 조건부로 적으면 그것도 거짓 고지) — HOSTING·PG·
   ALIMTALK 와 같은 자리에 상시 행으로 추가하는 것이 맞다.

   수정 — legal_docs.py 의 PRIVACY(제6조 표)에 카카오 행을 ALIMTALK 행 **앞에**
   무조건 추가했다(219~220행 부근). 뒤에 추가하지 않은 이유: round508 이 이미 심어
   둔 _ALIMTALK_ROW_TAIL(알림톡 행이 표의 마지막 행이라는 전제로 "…발송</td></tr>
   \\n</table>" 을 한 덩어리로 찾아 그 뒤에 Gemini 행을 끼워 넣는 상수)이 끊기지
   않아야 하기 때문 — 실제로 이 파일 [3]절이 그 앵커가 여전히 붙어 있고 round508
   메커니즘이 그대로 동작함을 실행으로 재확인한다.

   회귀 검사 — [1] 소스: PRIVACY 원문에 카카오 행이 무조건 있고 ALIMTALK 보다
   앞이며 표 태그 짝이 맞는다. [2] 실행: privacy_body() 의 네 가지 조합
   (기본값 · ai_photo_enabled=False/True · 커스텀 보안수치 동시 전달) 전부에서
   카카오 행은 항상 있고 Gemini 행은 여전히 플래그를 따른다(round508 무회귀 재확인).
   [3] 되돌림-증명: 방금 추가한 카카오 행만 정규식으로 도려낸 옛 버전을 메모리로
   재구성해 "카카오"가 실제로 한 글자도 없었음을 보여 이 라운드가 채운 공백이
   진짜임을 증명한다. [4] 실행(진짜 서브프로세스 아님, 진짜 Flask 앱): 격리
   DB 로 앱을 띄우고 test_client 로 실제 /legal/privacy 응답에 카카오가 실린다.
   [5] 실행: build_pages.py 정적 빌드(GEMINI_KEY 있음/없음 두 경우 다)에도
   실린다 — 무조건이므로 두 경우 다 있어야 한다(Gemini 는 대조를 위해 여전히
   조건부). [6] 실측: addr_search.py 가 "끌 수 없다"는 이 라운드 comment 의
   근거 — KAKAO_REST_KEY 유무 두 경우 다 provider() 가 유효한 카카오 경로만
   돌려주고 "꺼짐" 상태가 없음을 실제로 호출해 확인한다.

   ⚠ app.py 는 이 라운드에서 건드리지 않았다 — 수정은 legal_docs.py 하나뿐이다.
     app.py 는 이 모듈을 모듈 최상위에서 `import legal_docs as LEGAL` 하므로
     (63행), 이미 떠 있는 프로세스는 재시작해야 이 문서 수정이 실제 응답에
     반영된다(이 파일의 [4]절은 이 프로세스 안에서 새로 import 해 확인하는
     것이라 재시작 여부와 무관하게 통과한다 — 운영 서버 자체의 재시작 필요성과는
     별개다).

       python test_scan_round533_fixes.py
"""
import io
import os
import re
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로
#    죽는다(round518 이 이미 잡은 것과 같은 클래스) — 형제 방어를 그대로 쓴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PASS = FAIL = 0
FAILED = []


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        FAILED.append(msg)
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


print("=" * 74)
print("  스캔 533라운드 회귀 — 처리방침 제6조 주소검색(카카오) 위탁 공개 누락")
print("=" * 74)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — PRIVACY 원문에 카카오 행이 무조건(플래그 없이) 있다")
# ──────────────────────────────────────────────────────────────
import legal_docs as LEGAL  # noqa: E402

_KAKAO_ROW_RE = re.compile(r"  <tr><td>카카오\(Kakao Corp\.\).*?</tr>\n", re.S)

chk("카카오(Kakao Corp.)" in LEGAL.PRIVACY,
    "★★★★★ PRIVACY 원문(제6조 표)에 카카오 위탁 행이 있다")
chk(bool(_KAKAO_ROW_RE.search(LEGAL.PRIVACY)),
    "  정규식으로도 그 행 전체(여는~닫는 태그)를 한 덩어리로 뽑을 수 있다")

_idx_kakao = LEGAL.PRIVACY.find("카카오(Kakao Corp.)")
_idx_alim = LEGAL.PRIVACY.find(LEGAL.ALIMTALK)
chk(0 < _idx_kakao < _idx_alim,
    "★★★★ 카카오 행이 ALIMTALK 행보다 앞에 있다(round508 의 _ALIMTALK_ROW_TAIL "
    "앵커가 표의 마지막 행이라는 전제를 깨지 않기 위해 반드시 앞이어야 한다)",
    f"kakao={_idx_kakao} alimtalk={_idx_alim}")
chk(LEGAL._ALIMTALK_ROW_TAIL in LEGAL.PRIVACY,
    "★★★★★ round508 이 심은 _ALIMTALK_ROW_TAIL 앵커가 여전히 원문에 그대로 "
    "붙어 있다(카카오 행을 뒤가 아니라 앞에 넣었기 때문에 안 끊겼다)")
chk(LEGAL.PRIVACY.count("<tr>") == LEGAL.PRIVACY.count("</tr>"),
    "  표 태그가 짝이 맞는다(새 행 삽입이 다른 행의 닫는 태그를 먹지 않았다)",
    f"<tr>={LEGAL.PRIVACY.count('<tr>')} </tr>={LEGAL.PRIVACY.count('</tr>')}")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — privacy_body() 네 조합 전부에서 카카오는 항상, Gemini는 플래그대로")
# ──────────────────────────────────────────────────────────────
combos = [
    dict(ip_limit_enabled=True),
    dict(ip_limit_enabled=True, ai_photo_enabled=False),
    dict(ip_limit_enabled=True, ai_photo_enabled=True),
    dict(ip_limit_enabled=False, max_login_fails=3, session_min=15,
         log_retention_days=365, ai_photo_enabled=True),
]
for i, kw in enumerate(combos, 1):
    body = LEGAL.privacy_body(**kw)
    chk("카카오(Kakao Corp.)" in body,
        f"★★★★★ 조합{i} {kw} — 카카오 행이 항상 있다(무조건 위탁이므로)")
    want_gemini = kw.get("ai_photo_enabled", False)
    has_gemini = "Google LLC (Gemini API)" in body
    chk(has_gemini == want_gemini,
        f"  조합{i} — Gemini 행은 여전히 ai_photo_enabled 를 정확히 따른다"
        "(round508 무회귀)", f"want={want_gemini} has={has_gemini}")
    chk(body.count("<tr>") == body.count("</tr>"),
        f"  조합{i} — 표 태그 짝 유지")

_default = LEGAL.privacy_body(True)
chk("카카오" in _default and "Gemini" not in _default and "Google" not in _default,
    "★★★★ 인자 생략(기존 다른 호출부와 동일 형태)해도 카카오는 있고 "
    "Gemini 는 없다(round508 이 지키던 '안 하는 일을 한다고 안 적는다' 유지)")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — 이번에 추가한 행만 도려낸 '이전' 버전을 메모리로 재구성")
# ──────────────────────────────────────────────────────────────
#   legal_docs.py 파일 자체는 건드리지 않는다 — 이미 로드된 LEGAL.PRIVACY 문자열에서
#   정규식으로 카카오 행 하나만 도려내 "이 라운드 이전"을 재현한다.
_old_privacy, _n_removed = _KAKAO_ROW_RE.subn("", LEGAL.PRIVACY)
chk(_n_removed == 1,
    "★★★ 카카오 행을 정확히 1곳에서 도려냈다(중복 삽입 없음 확인 겸)",
    f"removed={_n_removed}")
chk("카카오" not in _old_privacy and "Kakao" not in _old_privacy,
    "★★★★★ 그 행을 빼면(=round533 이전 상태) 처리방침 전체에 '카카오'가 "
    "단 한 글자도 없다 — round508 은 이 결함을 못 잡았다는 뜻(실제 공백이었다)")
chk(LEGAL._ALIMTALK_ROW_TAIL in _old_privacy,
    "  옛 버전에도 _ALIMTALK_ROW_TAIL 은 그대로 있다(이 라운드가 그 앵커를 "
    "새로 만든 게 아니라 원래 있던 것 앞에 끼워 넣기만 했다는 대조)")


def _old_privacy_body(ip_limit_enabled, max_login_fails=5, session_min=30,
                       log_retention_days=730, ai_photo_enabled=False):
    """round533 이전의 privacy_body() 그대로(카카오 행이 없는 PRIVACY 기준).
       실제 파일에는 절대 쓰지 않는다 — 이 함수 안에서만 메모리로 재현한다."""
    body = _old_privacy if ip_limit_enabled else _old_privacy.replace(LEGAL._IP_ON, LEGAL._IP_OFF, 1)
    retention = LEGAL._period_text(log_retention_days)
    body = body.replace(LEGAL._RETENTION_TABLE_ON, f"<td><b>{retention}</b></td>", 1)
    body = body.replace(LEGAL._RETENTION_PARA_ON,
                         f"취급자의 접속 기록을 {retention} 이상 보관", 1)
    body = body.replace(LEGAL._LOGIN_LOCK_ON,
                         f"비밀번호 {max_login_fails}회 연속 오류 시 계정 잠금, "
                         f"{session_min}분 무동작 시 세션 자동 종료,", 1)
    body = body.replace(LEGAL._SESSION_COOKIE_ON,
                         f"브라우저를 종료하거나 {session_min}분간 활동이 없으면 만료되며", 1)
    if ai_photo_enabled:
        body = body.replace(LEGAL._ALIMTALK_ROW_TAIL,
                             LEGAL._ALIMTALK_ROW_TAIL.replace("</table>",
                                                               LEGAL._AI_PHOTO_ROW + "</table>"), 1)
    return body


old_default = _old_privacy_body(True)
chk("카카오" not in old_default,
    "★★★★★ 옛 privacy_body() 기본 호출 결과에도 카카오가 없다(재현 성공 — "
    "이 라운드 수정이 실제로 이 공백을 메운다는 증거)")
old_ai_on = _old_privacy_body(True, ai_photo_enabled=True)
chk("카카오" not in old_ai_on and "Google LLC (Gemini API)" in old_ai_on,
    "  옛 코드도 round508 자신의 몫(Gemini 조건부 삽입)은 정상 동작했다 "
    "(이 라운드가 고치는 것은 별개의 새 결함이라는 대조)")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 격리 DB로 실제 앱을 띄워 /legal/privacy 응답을 확인")
# ──────────────────────────────────────────────────────────────
_tmpdir4 = tempfile.mkdtemp(prefix="round533_")
try:
    os.environ.setdefault("BOKGUON_ENV", "dev")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir4, "r533.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir4, "uploads")
    import db as DB
    DB.init_db()
    import app as A
    client = A.app.test_client()

    _orig_key = A.PHOTO.GEMINI_KEY
    try:
        A.PHOTO.GEMINI_KEY = ""
        r = client.get("/legal/privacy")
        body = r.get_data(as_text=True)
        chk(r.status_code == 200, "  /legal/privacy 200 응답")
        chk("카카오" in body and "Kakao Corp." in body,
            "★★★★★ 실제 HTTP 응답(GEMINI 꺼짐 상태)에도 카카오 위탁이 실린다 "
            "— 이 라운드 수정 전에는 이 응답에 카카오가 전혀 없었다")
        chk("Google LLC (Gemini API)" not in body,
            "  같은 응답에서 Gemini 는 여전히 언급되지 않는다(꺼진 그대로, round508 무회귀)")
    finally:
        A.PHOTO.GEMINI_KEY = _orig_key
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★ /legal/privacy 실제 응답 검증", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir4, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[5] 실행 — build_pages.py 정적 빌드(GEMINI_KEY 있음/없음 둘 다)에도 실린다")
# ──────────────────────────────────────────────────────────────
_tmpdir5 = tempfile.mkdtemp(prefix="round533_build_")
try:
    import build_pages as BP
    _real_out = BP.OUT
    try:
        BP.OUT = os.path.join(_tmpdir5, "docs_off")
        os.environ.pop("BOKGUON_GEMINI_KEY", None)
        BP.build()
        priv_off = io.open(os.path.join(BP.OUT, "legal", "privacy.html"), encoding="utf-8").read()
        chk("카카오" in priv_off and "Kakao Corp." in priv_off,
            "★★★★ GEMINI_KEY 미설정이어도 정적 처리방침에 카카오 위탁이 실린다"
            "(무조건 위탁이므로 Gemini 와 달리 꺼지지 않는다)")
        chk("Google LLC (Gemini API)" not in priv_off,
            "  같은 정적 빌드에서 Gemini 는 여전히 빠져 있다(round508 그대로)")

        BP.OUT = os.path.join(_tmpdir5, "docs_on")
        os.environ["BOKGUON_GEMINI_KEY"] = "test-key-for-round533-repro"
        BP.build()
        priv_on = io.open(os.path.join(BP.OUT, "legal", "privacy.html"), encoding="utf-8").read()
        chk("카카오" in priv_on and "Google LLC (Gemini API)" in priv_on,
            "★★★★ GEMINI_KEY 설정 시 정적 빌드에 카카오·Gemini 둘 다 실린다")
    finally:
        BP.OUT = _real_out
        os.environ.pop("BOKGUON_GEMINI_KEY", None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ build_pages.py 정적빌드 실행", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir5, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[6] 실측 — addr_search.py 는 실제로 '끌 수 있는 스위치'가 없다")
# ──────────────────────────────────────────────────────────────
#   이 라운드가 카카오 행을 (round508 의 Gemini 처럼) 조건부가 아니라 상시행으로
#   넣은 근거 — KAKAO_REST_KEY 유무 두 경우 다 provider() 가 유효한 카카오 경로만
#   돌려주고, "비활성"을 뜻하는 값이 없음을 실제로 호출해 확인한다.
import addr_search as ADDR  # noqa: E402

_orig_kakao_key = os.environ.pop("KAKAO_REST_KEY", None)
try:
    p_off = ADDR.provider()
    chk("카카오" in p_off, "  KAKAO_REST_KEY 없어도 provider() 가 카카오 경로를 밝힌다"
        "(비활성 상태가 없다)", p_off)

    os.environ["KAKAO_REST_KEY"] = "dummy-key-for-round533-check"
    p_on = ADDR.provider()
    chk("카카오" in p_on, "  KAKAO_REST_KEY 있으면 다른 카카오 경로(REST API)를 밝힌다", p_on)
    chk(p_off != p_on,
        "  두 경로 표시 문구가 서로 달라 실제로 다른 엔드포인트임을 구분할 수 있다"
        "(둘 다 '카카오'라는 사실 자체는 바뀌지 않는다)", f"off={p_off!r} on={p_on!r}")
finally:
    if _orig_kakao_key is None:
        os.environ.pop("KAKAO_REST_KEY", None)
    else:
        os.environ["KAKAO_REST_KEY"] = _orig_kakao_key

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
