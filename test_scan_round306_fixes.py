# -*- coding: utf-8 -*-
"""스캔 306라운드 회귀 — build_pages.py(GitHub Pages 정적 소개사이트 빌더)
   결함 2건 + dev_tls_proxy.py 문서 보강, 이 세션 사상 첫 정밀조사한
   정밀조사 Agent가 발견(조사 프롬프트 자신의 "한 번도 조사 안 됨" 전제는
   틀렸다고 Agent 스스로 정정 — 108·230·294라운드가 이미 이 파일을,
   275라운드가 dev_tls_proxy.py 를 감사했었다. 그 세 라운드의 수정은
   전부 지금도 그대로 살아 있음을 재확인했고, 이번 결함들은 그 라운드들이
   못 보던 새 각도다).

  [1][심각] `docs/`(체크인된 GitHub Pages 산출물)가 이미 `legal_docs.py`
      (진짜 원본)와 어긋나 있었다 — 289라운드가 "하자담보책임기간(24개월)"
      고정문구를 "하자담보책임기간(사건별로 정해지며, 기본 24개월)"로
      고쳤는데(그 라운드 자신의 테스트가 **살아있는 서버**는 이미 고쳐진
      문구를 낸다고 확인했다), `build_pages.py` 는 소스 변경이 있을 때마다
      사람이 손으로 다시 실행해야 하는 완전 수동 도구(`deploy/외부공개_
      안내.md` 가 유일한 문서화된 절차 — GitHub Actions 등 자동 재빌드
      없음)라 아무도 다시 안 돌려, 체크인된 `docs/legal/privacy.html`·
      `terms.html` 이 계속 옛 고정문구를 내보내고 있었다(실측: 실제
      `docs/` 를 새로 빌드한 결과와 diff — 두 파일만 정확히 다름, 나머지
      23개는 이미 일치). 근본 수정은 없다(도구 자체는 이미 정확했다) —
      `python build_pages.py` 를 실제로 다시 돌려 `docs/` 를 최신 소스와
      일치시키고, 앞으로 이 드리프트를 놓치지 않도록 "체크인된 docs/ 가
      항상 방금 빌드한 결과와 같아야 한다"를 회귀 불변식으로 못박는다.
  [2] `build_pages.py` 가 이미 `legal_docs` 를 import 해 두고도(201행,
      `LEGAL.DOCS`/`LEGAL.privacy_body()` 를 이미 쓴다) 정작 요약 출력
      한 줄("회사 정보 N/8 반영")만을 위해 `data/company_info.json` 을
      **독립적으로 다시** 읽었다 — 그런데 이 자리만 아무 보호가 없어서,
      `manage.py set-info` 를 한 번도 안 한 정상 상태(파일 없음)에서
      돌리면 `docs/` 는 이미 전부 성공적으로 써진 뒤인데도 이 마지막
      줄에서 FileNotFoundError 로 죽어 exit 1 이 됐다(그 파일에 대한
      방어는 121라운드가 이미 `legal_docs._load_info()` 에 세워 뒀는데
      이 자리만 그걸 안 썼다). 다시 읽지 않고 이미 로드된 `LEGAL.INFO`
      를 그대로 재사용하도록 수정(중복 로직 없음 — 121라운드의 방어를
      그대로 물려받는다). 안 쓰게 된 `import json` 도 제거.

  ⚠ dev_tls_proxy.py 는 코드 변경 없음 — X-Forwarded-For 가 이 로컬
    리허설 프록시를 거치면 검증 없이 그대로 통과한다는 사실(TCP 바이트
    중계라 HTTP 를 아예 해석 안 함, 실측 확인됨)을 docstring 에 명시만
    추가했다(실행 동작 변경 없음 — 회귀테스트 대상 아님).

      python test_scan_round306_fixes.py
"""
import filecmp
import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


BUILD_SRC = read("build_pages.py")
PROXY_SRC = read("dev_tls_proxy.py")

print("=" * 72)
print("  스캔 306라운드 회귀 — build_pages.py docs/ 드리프트·company_info 크래시")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("json.load(open(" not in BUILD_SRC,
    "★★★★★ build_pages.py 가 더는 company_info.json 을 독립적으로 다시 읽지 않는다"
    "(고치기 전엔 이 자리만 무방비 — legal_docs.py 가 이미 세워 둔 방어를 안 썼다)")
chk("info = LEGAL.INFO" in BUILD_SRC,
    "★★★★ 대신 이미 로드된 LEGAL.INFO(legal_docs._load_info() 의 결과, 121라운드 방어 포함)를 재사용한다")
chk("import json" not in BUILD_SRC,
    "STEP 더 이상 안 쓰는 import json 도 정리됐다")
chk("$proxy_add_x_forwarded_for" in PROXY_SRC or "X-Forwarded-For" in PROXY_SRC,
    "STEP dev_tls_proxy.py docstring 에 X-Forwarded-For 신뢰경계 한계가 명시됐다")

# ============================================================
print("\n[2] 실행 — legal_docs._load_info() 는 여전히(121라운드 방어) 파일 없을 때 {} 를 낸다")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import legal_docs as LEGAL

    _orig_info_path = LEGAL._INFO_PATH
    LEGAL._INFO_PATH = os.path.join(tempfile.mkdtemp(prefix="round306_noinfo_"), "company_info.json")
    try:
        result = LEGAL._load_info()
        chk(result == {},
            "STEP (사전조건) legal_docs._load_info() 는 파일이 없으면 {} 를 낸다(회귀 없음 — 121라운드 방어 그대로)",
            result)
    finally:
        LEGAL._INFO_PATH = _orig_info_path
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드306 [2] 사전조건 확인", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — company_info.json 이 아예 없는 샌드박스에서 build_pages.py 가 죽지 않는가")
# ------------------------------------------------------------
_sandbox = tempfile.mkdtemp(prefix="round306_sandbox_")
try:
    for fn in ("build_pages.py", "legal_docs.py", "envload.py"):
        shutil.copy2(os.path.join(HERE, fn), os.path.join(_sandbox, fn))
    os.makedirs(os.path.join(_sandbox, "templates"))
    shutil.copy2(os.path.join(HERE, "templates", "landing.html"),
                 os.path.join(_sandbox, "templates", "landing.html"))
    shutil.copy2(os.path.join(HERE, "templates", "legal.html"),
                 os.path.join(_sandbox, "templates", "legal.html"))
    shutil.copytree(os.path.join(HERE, "static"), os.path.join(_sandbox, "static"))
    #  ⚠ data/ 디렉터리 자체를 아예 안 만든다 — set-info 를 한 번도 안 한
    #    정상 상태(파일 없음)를 재현하는 것이 이 검사의 핵심이다.

    r = subprocess.run([PY, "-u", "build_pages.py"], cwd=_sandbox,
                        capture_output=True, text=True, encoding="utf-8", timeout=30)
    chk(r.returncode == 0,
        "★★★★★ company_info.json 이 없어도 build_pages.py 가 exit 0 으로 끝난다"
        "(고치기 전엔 docs/ 를 이미 다 쓰고도 마지막 요약줄에서 FileNotFoundError 로 죽어 exit 1)",
        (r.returncode, r.stdout[-500:], r.stderr[-500:]))
    chk("회사 정보 0/8 반영" in r.stdout,
        "STEP 정보가 하나도 없으니 0/8 로 정확히 집계된다(회귀 없음 — 294라운드 집계기준 그대로)",
        r.stdout)
    chk(os.path.isfile(os.path.join(_sandbox, "docs", "index.html")),
        "STEP docs/index.html 이 실제로 만들어졌다(크래시 지점 이전 단계는 원래도 성공이었다)")
finally:
    shutil.rmtree(_sandbox, ignore_errors=True)

# ============================================================
print("\n[4] 실행 — 체크인된 docs/ 가 지금 이 순간의 소스로 새로 빌드한 결과와 완전히 같은가")
# ------------------------------------------------------------
import build_pages as BP                                            # noqa: E402

REAL_OUT = BP.OUT


def _walk_files(root):
    out = set()
    for dp, _, fs in os.walk(root):
        for f in fs:
            out.add(os.path.relpath(os.path.join(dp, f), root))
    return out


_tmp_root = tempfile.mkdtemp(prefix="round306_rebuild_")
BP.OUT = os.path.join(_tmp_root, "docs")
try:
    BP.build()
    real_files = _walk_files(REAL_OUT)
    fresh_files = _walk_files(BP.OUT)
    chk(real_files == fresh_files,
        "STEP 체크인된 docs/ 와 새로 빌드한 결과의 파일 목록이 정확히 같다",
        (sorted(real_files - fresh_files), sorted(fresh_files - real_files)))

    diffs = [rel for rel in sorted(real_files & fresh_files)
             if not filecmp.cmp(os.path.join(REAL_OUT, rel), os.path.join(BP.OUT, rel), shallow=False)]
    chk(not diffs,
        "★★★★★ 체크인된 docs/ 가 지금 소스(legal_docs.py 등)로 새로 빌드한 결과와 완전히 같다"
        "(라운드306 발견 당시엔 docs/legal/privacy.html·terms.html 이 하자담보책임기간 문구에서"
        " 실제로 이렇게 어긋나 있었다 — python build_pages.py 를 다시 돌려 바로잡았다)",
        diffs)

    # ── 대조군 — 이 비교 자체가 실제로 드리프트를 잡아내는지, 안전한 사본으로 증명 ──
    _stale_root = tempfile.mkdtemp(prefix="round306_stale_")
    _stale_docs = os.path.join(_stale_root, "docs")
    shutil.copytree(REAL_OUT, _stale_docs)
    _stale_privacy = os.path.join(_stale_docs, "legal", "privacy.html")
    _orig_text = io.open(_stale_privacy, encoding="utf-8").read()
    _stale_text = _orig_text.replace(
        "하자담보책임기간(사건별로 정해지며, 기본 24개월)", "하자담보책임기간(24개월)")
    if _stale_text == _orig_text:
        chk(False, "★★★ 대조군 준비 — 되돌릴 문구를 못 찾았다(문서가 그새 또 바뀌었을 수 있다)")
    else:
        io.open(_stale_privacy, "w", encoding="utf-8").write(_stale_text)
        diffs2 = [rel for rel in sorted(real_files & fresh_files)
                  if not filecmp.cmp(os.path.join(_stale_docs, rel), os.path.join(BP.OUT, rel), shallow=False)]
        chk(diffs2 == [os.path.join("legal", "privacy.html")],
            "★★★★★ 대조군 — 예전 고정문구로 일부러 되돌린 사본과 비교하면 이 검사가 정확히"
            " 그 파일 하나만 다르다고 잡아낸다(라운드306 발견 당시의 실제 상태를 재현 — 이"
            " 검사가 그 결함을 실제로 잡을 수 있었음을 증명, 실제 docs/ 는 안 건드림)",
            diffs2)
    shutil.rmtree(_stale_root, ignore_errors=True)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드306 [4] 실측", f"{type(e).__name__} {e}")
finally:
    BP.OUT = REAL_OUT
    shutil.rmtree(_tmp_root, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
