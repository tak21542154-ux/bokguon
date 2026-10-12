# -*- coding: utf-8 -*-
"""스캔 108라운드 회귀 — 정적 공개 처리방침의 허위 보안고지, 협력사 화면의 표류 면허컬럼 3곳.

  [1] app.py 서버 라우트는 이미 "처리방침은 실제 설정과 같은 말을 해야 한다"며
      관리자IP제한 문구를 ADMIN_IP_ALLOW 설정에 맞춰 넣고 뺐는데, GitHub Pages 로
      나가는 정적 빌드(build_pages.py)는 그 특례 없이 원문을 그대로 썼다.
      게다가 이 스크립트만 공유 .env 로더(envload.py)를 안 써서 .env 의
      BOKGUON_ADMIN_IP_ALLOW 값 자체를 못 봤다.
  [2] 106라운드가 compliance.check_subcontractor 에서 고친 것과 같은 오판
      (partners.license — 자기신고 자유텍스트 — 을 "면허/등록"으로 표시)이
      협력사 목록 열·수정모달 라벨·엑셀 내보내기 3곳에 그대로 남아 있었다.

      python test_scan_round108_fixes.py
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


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")
ADMINJS_SRC = read("static/admin.js")
BUILD_SRC = read("build_pages.py")

print("═" * 72)
print("  스캔 108라운드 회귀 — 정적 처리방침 허위고지·협력사 화면 표류 면허컬럼 3곳")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 다섯 지점 모두 확인")
# ──────────────────────────────────────────────────────────────
chk("import envload" in BUILD_SRC and "envload.load_dotenv()" in BUILD_SRC,
    "★★★ build_pages.py 가 이제 공유 .env 로더를 쓴다")
build_body = _py_fn_body(BUILD_SRC, "build")
chk('if key == "privacy" and hasattr(LEGAL, "privacy_body"):' in build_body,
    "★★★ 정적 빌드도 서버와 같은 규칙으로 privacy 본문을 특별 처리한다")

exp_partners = APP_SRC[APP_SRC.index('"partners": ("협력업체"'):
                       APP_SRC.index('"applications": ("입점신청"')]
chk("COALESCE(license_status,'미확인') AS 건설업등록" in exp_partners,
    "★★★ 협력업체 엑셀이 정본(license_status)을 내보낸다")

chk("p.license_status==='등록확인'?'<span class=\"pill green\">등록확인</span>'" in ADMINJS_SRC,
    "★★★ 시행사 목록 '면허' 열이 이제 license_status 를 pill 로 보여준다")
chk("(자기신고 — 참고용, 아래 조사 결과가 정본)" in ADMINJS_SRC,
    "★★ 수정모달의 자기신고 입력란 라벨이 더는 '필수 확인'이라고 하지 않는다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 정적 처리방침을 실제로 빌드해 본다")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round108_")
try:
    sys.path.insert(0, HERE)
    import build_pages as BP
    _real_out = BP.OUT
    BP.OUT = os.path.join(_tmpdir, "docs_off")
    try:
        os.environ["BOKGUON_ADMIN_IP_ALLOW"] = ""
        BP.build()
        priv_off = io.open(os.path.join(BP.OUT, "legal", "privacy.html"), encoding="utf-8").read()
        chk("관리자 콘솔 접속 IP 제한" not in priv_off,
            "★★★ IP 제한이 미설정이면 정적 처리방침도 그 문구를 안 뺀 게 아니라 뺀다"
            "(예전엔 .env 를 못 읽어 이 경로가 아예 안 탔다)",
            "관리자 콘솔 접속 IP 제한" in priv_off)

        BP.OUT = os.path.join(_tmpdir, "docs_on")
        os.environ["BOKGUON_ADMIN_IP_ALLOW"] = "203.0.113.10"
        BP.build()
        priv_on = io.open(os.path.join(BP.OUT, "legal", "privacy.html"), encoding="utf-8").read()
        chk("관리자 콘솔 접속 IP 제한" in priv_on,
            "STEP IP 제한이 실제로 설정되면 그 문구가 정상적으로 실린다(과잉삭제 아님)",
            "관리자 콘솔 접속 IP 제한" in priv_on)
    finally:
        BP.OUT = _real_out
        os.environ.pop("BOKGUON_ADMIN_IP_ALLOW", None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드108 정적빌드 실행", f"{type(e).__name__} {e}")
finally:
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
