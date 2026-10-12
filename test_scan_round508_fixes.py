# -*- coding: utf-8 -*-
"""스캔 508라운드 회귀 — 개인정보 처리방침 제6조(처리 위탁) 표에 AI 사진분석
   위탁처(Google Gemini API)가 통째로 빠져 있던 결함[컴플라이언스].

   photo_ai.py(BOKGUON_GEMINI_KEY 설정 시 실사용)는 협력사·보험사가 올린 시공·
   손상 사진 원본을 구글 Gemini API 로 그대로 전송해 자동분류(classify)·파손
   정도 참고 분석(analyze_damage)을 시킨다 — round224·229·284·298·328 이 이
   기능 자체(임계값·EXIF·8MB 상한·정확도 통계)를 여러 차례 다뤘지만, "이 위탁을
   개인정보 처리방침에 공개해야 하는가"는 그중 어디서도 다룬 적이 없었다.

   legal_docs.py 제6조(개인정보 처리의 위탁) 표는 호스팅·PG·알림톡 세 곳만
   나열하고, INFO_FIELDS 에도 AI 사진분석 위탁처 항목이 없다 — 개인정보 보호법
   제26조가 요구하는 처리위탁 공개 대상인데 문서 어디에도 없다.

   이 파일이 이미 같은 패턴(IP제한 유무·하자담보책임기간·보안설정 수치 3종)을
   세 번 고친 전례(round238·289·317)가 있는데, 이 자리만 그 교훈을 못 받았다.

   반대로 BOKGUON_GEMINI_KEY 가 비어 있으면(.env.example 기본값) 실제로 사진이
   전혀 안 나가므로, "안 하는 일을 한다"고 적으면 그것도 거짓 고지다(round238의
   IP제한과 정반대 방향의 같은 원칙) — 그래서 켜져 있을 때만 표에 한 줄이 붙는다.

       python test_scan_round508_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

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
print("  스캔 508라운드 회귀 — 처리방침 제6조 AI 사진분석 위탁 공개 누락")
print("=" * 74)

# ══════════════════════════════════════════════════════════════
print("\n[1] 실행 — legal_docs.privacy_body() 단위 검증")
# ──────────────────────────────────────────────────────────────
import legal_docs as LEGAL  # noqa: E402


def _pb(*a, **kw):
    try:
        return LEGAL.privacy_body(*a, **kw)
    except TypeError as e:
        return f"__TYPEERROR__{e}"


default_body = _pb(True)
chk(default_body == LEGAL.PRIVACY,
    "★★★★ 인자 없이 부르면(기존 test_feature_work_coverage.py 호출부와 동일) "
    "본문이 원본 PRIVACY 와 완전히 같다(회귀 없음)")
chk("Gemini" not in default_body and "Google" not in default_body,
    "  기본값(ai_photo_enabled 생략)은 AI 위탁을 언급하지 않는다"
    "(지금까지 이 표에 그 줄이 아예 없던 것과 동일)")

off_body = _pb(True, ai_photo_enabled=False)
chk(off_body == LEGAL.PRIVACY,
    "★★★ ai_photo_enabled=False 를 명시해도 결과는 원본과 완전히 같다")

on_body = _pb(True, ai_photo_enabled=True)
chk("Google LLC (Gemini API)" in on_body,
    "★★★★★ ai_photo_enabled=True 면 제6조 위탁 표에 Gemini API 가 실린다")
chk(on_body.count("<tr>") == on_body.count("</tr>"),
    "★★★ 표 태그가 짝이 맞는다(새 줄 삽입이 다른 행의 닫는 태그를 먹지 않았다)",
    f"<tr>={on_body.count('<tr>')} </tr>={on_body.count('</tr>')}")
_alim_idx = on_body.find("입찰·시공·정산 관련 알림 메시지 발송")
_google_idx = on_body.find("Google LLC (Gemini API)")
_table_close_idx = on_body.find("</table>", _alim_idx)
chk(0 < _alim_idx < _google_idx < _table_close_idx,
    "★★★★ 새 줄이 알림톡 행 다음 · 표가 닫히기 전에, 올바른 순서로 끼워졌다",
    f"alim={_alim_idx} google={_google_idx} close={_table_close_idx}")
chk("입찰·시공·정산 관련 알림 메시지 발송</td></tr>" in on_body,
    "★★★★ 알림톡 행 자신의 닫는 태그(</td></tr>)가 그대로 살아있다"
    "(교체 로직이 앵커 자체를 삼키면 이 태그가 사라진다)")

chk("2년" in on_body and "30분" in on_body and "5회 연속" in on_body,
    "  round317 이 다루는 세 수치는 이 변경과 무관하게 그대로 보존된다")
combo = _pb(True, max_login_fails=3, session_min=15, log_retention_days=365,
            ai_photo_enabled=True)
chk("3회 연속 오류" in combo and "15분간 활동이 없으면" in combo
    and "<td><b>1년</b></td>" in combo and "Google LLC (Gemini API)" in combo,
    "★★★★ round317 커스텀값 + AI 위탁 공개를 동시에 넘겨도 서로 간섭하지 않는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 소스 — 호출부 두 곳이 photo_ai 의 실제 판정을 그대로 넘긴다")
# ──────────────────────────────────────────────────────────────
APP_SRC = io.open(os.path.join(HERE, "app.py"), encoding="utf-8").read()
BUILD_SRC = io.open(os.path.join(HERE, "build_pages.py"), encoding="utf-8").read()

_legal_route = APP_SRC[APP_SRC.index('@app.route("/legal/<key>")'):
                        APP_SRC.index('@app.get("/robots.txt")')]
chk("ai_photo_enabled=PHOTO.is_enabled()" in _legal_route,
    "★★★★ app.py legal_page() 가 photo_ai.is_enabled() (photo_ai.py 자신이 "
    "이미 쓰는 판정)을 그대로 넘긴다 — 새 판정을 따로 만들지 않는다")

_build_fn = BUILD_SRC[BUILD_SRC.index("\ndef build("):]
chk('os.environ.get("BOKGUON_GEMINI_KEY"' in _build_fn
    and "ai_photo_enabled=_ai_photo_enabled" in _build_fn,
    "★★★★ build_pages.py 의 정적 빌드도 같은 환경변수를 직접 조회해 넘긴다")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 실제 /legal/privacy 라우트가 photo_ai 설정을 반영한다")
# ──────────────────────────────────────────────────────────────
try:
    import db as DB
    DB.init_db()
    import app as A
    client = A.app.test_client()

    _orig_key = A.PHOTO.GEMINI_KEY
    try:
        A.PHOTO.GEMINI_KEY = ""     # 이 저장소 .env 의 실제 기본 상태
        r_off = client.get("/legal/privacy")
        body_off = r_off.get_data(as_text=True)
        chk(r_off.status_code == 200, "  /legal/privacy 200 응답(꺼짐)")
        chk("Google LLC (Gemini API)" not in body_off,
            "★★★★★ GEMINI 키가 없으면(현재 .env 의 실제 상태) 실제 응답도 "
            "AI 위탁을 언급하지 않는다 — 안 하는 일을 한다고 말하지 않는다")

        A.PHOTO.GEMINI_KEY = "test-key-for-round508-repro"
        r_on = client.get("/legal/privacy")
        body_on = r_on.get_data(as_text=True)
        chk(r_on.status_code == 200, "  /legal/privacy 200 응답(켜짐)")
        chk("Google LLC (Gemini API)" in body_on,
            "★★★★★ GEMINI 키가 설정되면 실제 응답이 그 사실을 처리방침에 반영한다")
    finally:
        A.PHOTO.GEMINI_KEY = _orig_key
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★ /legal/privacy 실제 응답 검증", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — build_pages.py 정적 빌드도 같은 방식으로 반영한다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round508_")
try:
    import build_pages as BP
    _real_out = BP.OUT
    try:
        BP.OUT = os.path.join(_tmpdir, "docs_off")
        os.environ.pop("BOKGUON_GEMINI_KEY", None)
        BP.build()
        priv_off = io.open(os.path.join(BP.OUT, "legal", "privacy.html"), encoding="utf-8").read()
        chk("Google LLC (Gemini API)" not in priv_off,
            "★★★ GEMINI 키 미설정이면 정적 처리방침도 AI 위탁을 언급하지 않는다")

        BP.OUT = os.path.join(_tmpdir, "docs_on")
        os.environ["BOKGUON_GEMINI_KEY"] = "test-key-for-round508-repro"
        BP.build()
        priv_on = io.open(os.path.join(BP.OUT, "legal", "privacy.html"), encoding="utf-8").read()
        chk("Google LLC (Gemini API)" in priv_on,
            "★★★ GEMINI 키가 설정되면 정적 처리방침에도 실린다(GitHub Pages 공개본)")
    finally:
        BP.OUT = _real_out
        os.environ.pop("BOKGUON_GEMINI_KEY", None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ build_pages.py 정적빌드 실행", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
