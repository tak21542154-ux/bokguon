# -*- coding: utf-8 -*-
"""스캔 419라운드 회귀 — /sitemap.xml·엑셀/CSV 내보내기 3종의 날짜·타임스탬프가
   `DB.now()`/`datetime.now(DB.KST)` 관례(이 파일에서만 100회 넘게 쓰임) 대신
   보정 없는 naive `datetime.now()`(OS 시각)를 직접 써서, 서버 OS 시계가 KST가
   아니면(배포스크립트 deploy/bootstrap.sh 가 이미 경고하는 실제 배포 리스크 —
   컨테이너 기본 UTC 등) KST 자정 전후 9시간 구간에 하루 어긋난 날짜가 찍히던
   결함(정밀조사 Agent 발견 — 각도1: KST 시간대 처리 일관성).

     ①app.py:2239 부근 sitemap_xml() — <lastmod> SEO 메타데이터
     ②app.py:7219 부근 — /api/ops-kpi/export 엑셀 파일명
     ③app.py:9375 부근 — /api/export/<section> 엑셀 파일명
     ④app.py:12971 부근 — /api/settlements/export CSV 파일명

   전부 표시값·파일명일 뿐 사업로직(정산금액·상태판정·법적기한)에는 영향
   없음(직접 추적 확인) — 그래도 이미 100회 넘게 쓰이는 자기 관례를 이 4곳만
   안 따르는 순수 일관성 결함이라 그냥 고치면 되는 것으로 분류.

   datetime.datetime.now 는 불변 C 확장 타입이라 직접 monkeypatch 할 수
   없다 — app.py 자신의 이름공간에 바인딩된 `datetime` 이름 자체를 교체하는
   기법을 쓴다(이 세션 최초 사용).

       python test_scan_round419_fixes.py
"""
import datetime as _dt_mod
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
APP_PATH = os.path.join(HERE, "app.py")
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 419라운드 회귀 — sitemap/내보내기 4곳 naive datetime.now() 잔존")
print("=" * 72)

print("\n[1] 소스 확인")
n_bare = APP_SRC.count("datetime.now()")   # 주석 포함 카운트라 별도 검증
n_kst = APP_SRC.count("datetime.now(DB.KST)")
chk(n_kst >= 4,
    f"★★★★★ datetime.now(DB.KST) 패턴이 최소 4곳(이번 라운드 수정분) 있다", n_kst)
# 코드(주석 제외) 안에 실제 실행되는 bare datetime.now() 가 없는지 — 줄 단위로
# '#' 로 시작하는 주석 줄은 제외하고 확인한다.
_code_lines_with_bare = [
    l for l in APP_SRC.split("\n")
    if "datetime.now()" in l and not l.strip().startswith("#")
]
chk(len(_code_lines_with_bare) == 0,
    "★★★★★ 실행되는 코드 줄에는 naive datetime.now() 가 하나도 안 남았다"
    "(주석 안의 설명·경고 문구는 제외하고 확인)", _code_lines_with_bare)

print("\n[2] 실행 준비")
sys.path.insert(0, HERE)
_tmpdir_env = os.environ.get("BOKGUON_DB_PATH")
if not _tmpdir_env:
    import tempfile
    _tmpdir = tempfile.mkdtemp(prefix="round419_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"

try:
    import db as DB
    DB.init_db()
    import app as A

    #  가짜 OS 시각: KST 로는 다음날 08:30 인 순간을, "보정 없는 naive now()"는
    #  전날 23:30(UTC 느낌)으로 잘못 본다고 가정 — 자정 경계를 정확히 넘긴다.
    class _FakeDatetime:
        @staticmethod
        def now(tz=None):
            if tz is None:
                return _dt_mod.datetime(2026, 3, 9, 23, 30, 0)      # "틀린" naive 값
            return _dt_mod.datetime(2026, 3, 10, 8, 30, 0, tzinfo=tz)  # 올바른 KST 값

    print("\n[3] 실행 — sitemap_xml(): 가짜 OS 시각으로 자정경계 재현")
    _orig_datetime = A.datetime
    A.datetime = _FakeDatetime
    try:
        with A.app.test_client() as c:
            r = c.get("/sitemap.xml")
    finally:
        A.datetime = _orig_datetime
    chk(r.status_code == 200, "  /sitemap.xml 은 여전히 200을 돌려준다(회귀없음)", r.status_code)
    body = r.get_data(as_text=True)
    chk("2026-03-10" in body,
        "★★★★★ KST 로 올바른 날짜(다음날)가 <lastmod> 에 찍힌다"
        "(고치기 전엔 OS시각 그대로인 전날 2026-03-09 가 찍혔다)", body[:300])
    chk("2026-03-09" not in body,
        "  잘못된(하루 이른) 날짜는 안 섞여 있다", body[:300])

    print("\n[4] 대조군 — 진짜 시계로는 정상 동작(형식만 확인)")
    with A.app.test_client() as c2:
        r2 = c2.get("/sitemap.xml")
    chk(r2.status_code == 200 and "<lastmod>" in r2.get_data(as_text=True),
        "  정상 시계에서도 sitemap 이 여전히 정상 응답한다(회귀없음)", r2.status_code)

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 되돌리기 — 옛 코드로 되돌리면 하루 어긋난 날짜가 재현되는가")
# ------------------------------------------------------------
#  ⚠⚠ [라운드617] on-disk 되돌리기(파일에 직접 쓰고 subprocess 로 재현)를
#    인메모리 exec 로 이관 — sitemap_xml() 은 데코레이터 없는 단일 Flask
#    라우트 핸들러라 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다
#    (신설 함수는 이름 충돌을 피하려 _sitemap_xml_pre419 로 리네임해 사본
#    이름공간에 exec 로 재구성 — round417 이 정착시킨 기법1). 가짜 시계는
#    그 사본 이름공간의 "datetime" 이름에만 심어, 실 모듈 A.datetime 은
#    전혀 안 건드린다 — 디스크의 app.py 도 이제 전혀 안 건드린다.

NEW_TODAY = '''    #  ⚠⚠ [라운드419] naive datetime.now() 는 OS 시각이다 — 배포스크립트
    #    (deploy/bootstrap.sh)가 이미 경고하는 것과 같은 계열 위험. 다른 곳
    #    (app.py:13121·13970·18430)이 이미 쓰는 KST-aware 패턴으로 맞춘다.
    today = datetime.now(DB.KST).strftime("%Y-%m-%d")'''
OLD_TODAY = '''    today = datetime.now().strftime("%Y-%m-%d")'''


def _py_fn_body(src, fn_name):
    """함수 본문 — 다음 def뿐 아니라 다음 라우트의 @app. 데코레이터가 먼저
    나오면 거기서 자른다(round610 정착 기법)."""
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    dec = src.find("\n@app.", start + 1)
    if dec != -1 and (end == -1 or dec < end):
        end = dec
    return src[start:end if end != -1 else None]


try:
    chk(APP_SRC.count(NEW_TODAY) == 1, "  (준비) sitemap 되돌리기 대상 텍스트가 유일하게 식별된다")
    reverted = APP_SRC.replace(NEW_TODAY, OLD_TODAY)
    chk(reverted != APP_SRC, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    _body419 = _py_fn_body(APP_SRC, "sitemap_xml")
    chk(NEW_TODAY in _body419, "  (준비) sitemap_xml() 본문 안에 NEW_TODAY가 있다")
    _old_body419 = (_body419
                    .replace("def sitemap_xml():", "def _sitemap_xml_pre419():", 1)
                    .replace(NEW_TODAY, OLD_TODAY, 1))
    chk(_old_body419.count(OLD_TODAY) == 1 and "_sitemap_xml_pre419" in _old_body419,
        "  (준비) 함수 리네임 + 되돌리기가 정확히 적용됐다(실제 파일은 안 건드림)")

    _ns419 = dict(vars(A))
    _ns419["datetime"] = _FakeDatetime
    exec(compile(_old_body419, "<round419_pre419_sitemap_xml>", "exec"), _ns419)  # noqa: S102 -- 우리 소스에서 그대로 추출, 디스크 미기록
    old_sitemap_fn = _ns419["_sitemap_xml_pre419"]

    _orig_view419 = A.app.view_functions["sitemap_xml"]
    A.app.view_functions["sitemap_xml"] = old_sitemap_fn
    try:
        with A.app.test_client() as c3:
            r_old = c3.get("/sitemap.xml")
    finally:
        A.app.view_functions["sitemap_xml"] = _orig_view419

    body_old = r_old.get_data(as_text=True)
    chk("2026-03-09" in body_old,
        "★★★★★ 옛 코드(되돌림, 실제 파일은 안 건드림)는 가짜 OS시각의 하루 이른 "
        "날짜를 그대로 <lastmod> 에 찍는다(인과관계 직접증명)", body_old[:300])
    chk("2026-03-10" not in body_old,
        "  옛 코드에는 올바른 날짜가 아예 안 나온다", body_old[:300])

    chk(A.app.view_functions["sitemap_xml"] is _orig_view419,
        "  view_functions가 원래 함수객체로 복원됐다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
