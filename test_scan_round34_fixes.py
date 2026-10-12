# -*- coding: utf-8 -*-
"""스캔 34라운드 회귀 — 조사 에이전트 2건 중 실제로 고친 한 자리.

  ① 사진/첨부파일 다운로드(`/api/photos/<id>/file`) 교차열람 조사 — **결함 없음**
     (`_photo_visible_to` 가 이미 소유권을 검증, 실측 8건 전부 정상). 이 라운드
     테스트 대상 아님.

  ② 엑셀·CSV 내보내기 8개 전부 `_safe`/`_xl_safe`/`_csv_safe` 로 수식 인젝션을
     막고 있었으나, **협력사 포털 계정 일괄발급 CLI**(`partner_accounts.py`
     `--out`)만 예외였다 — 같은 업체명/지역/공종 자유텍스트를 `csv.DictWriter`
     로 그대로 찍었다. 업체가 스스로 등록한 업체명이 `=...` 로 시작하면,
     운영자가 나중에 이 CSV 를 엑셀로 열 때 수식으로 실행된다. app.py 의
     `_csv_safe` 와 같은 규칙으로 `partner_accounts.py` 에도 이식했다.

      python test_scan_round34_fixes.py
"""
import csv
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("partner_accounts.py")

print("═" * 72)
print("  스캔 34라운드 회귀 — 협력사 계정발급 CSV 수식 인젝션")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk("def _csv_safe(v):" in SRC, "★ partner_accounts.py 에 _csv_safe 헬퍼가 있다")
#  ⚠⚠ [라운드578] app.py 의 _csv_safe·_xl_safe 는 이미 [라운드423]에서 트리거
#    집합에 탭(\t)을 추가했다(v34 당시엔 없던 규칙) — "app.py 와 같은 규칙"이라는
#    이 검사 자신의 이름을 지키려면 그 최신 규칙과 대조해야 한다. 탭 없는 옛
#    리터럴만 찾으면, 라운드578이 partner_accounts.py 를 그 규칙에 맞춰 올린
#    뒤에도(트리거 문자열이 ("=", "+", "-", "@", "\t") 로 바뀌어 옛 부분열이 더는
#    안 나옴) 이 검사가 "규칙이 갈렸다"고 오탐하게 된다.
chk('v[:1] in ("=", "+", "-", "@", "\\t")' in SRC,
    "★ app.py 의 _csv_safe 와 같은 규칙(등호·플러스·마이너스·골뱅이·[라운드578] 탭)")
chk('"업체명": _csv_safe(r["name"])' in SRC, "★★ 업체명이 실제로 감싸져 있다")
chk('"지역": _csv_safe(r["region"] or "")' in SRC, "★ 지역도 감싸져 있다")
chk('"공종": _csv_safe(r["major"] or "")' in SRC, "★ 공종도 감싸져 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 수식 페이로드 업체명이 실제로 CSV 에서 무력화되는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="pacsv_")
db_path = os.path.join(_tmpdir, "verify.db")
out_csv = os.path.join(_tmpdir, "발급.csv")
MARK = "=1+1;PACSV_MARK"

env = dict(os.environ, BOKGUON_DB_PATH=db_path, PYTHONIOENCODING="utf-8")
try:
    sys.path.insert(0, HERE)
    os.environ["BOKGUON_DB_PATH"] = db_path
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    pid = conn.execute(
        "INSERT INTO partners(name, partner_type, status, biz_no, phone, region, major) "
        "VALUES (?, '시행사', '활성', '111-22-33344', '01011112222', ?, ?)",
        (MARK, "+2;RG_MARK", "-3;MJ_MARK")).lastrowid
    conn.commit()
    conn.close()

    r = subprocess.run(
        [sys.executable, "partner_accounts.py", "--ids", str(pid), "--out", out_csv],
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=HERE, timeout=30)
    chk(r.returncode == 0, "★ 발급 CLI 가 정상 종료한다", r.stdout[-800:] + r.stderr[-800:])
    chk(os.path.isfile(out_csv), "★ CSV 파일이 실제로 생성됐다")

    if os.path.isfile(out_csv):
        with io.open(out_csv, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))

        row = next((x for x in rows if MARK in (x.get("업체명") or "")), None)
        chk(row is not None, "★ 심은 업체 행을 CSV 에서 찾았다")
        if row:
            chk(row["업체명"] == "'" + MARK,
                "★★★ 업체명이 아포스트로피로 무력화됐다(수식 아닌 텍스트로 열림)",
                row["업체명"])
            chk(row["지역"] == "'+2;RG_MARK", "★★ 지역도 무력화됐다", row["지역"])
            chk(row["공종"] == "'-3;MJ_MARK", "★★ 공종도 무력화됐다", row["공종"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 협력사 계정발급 CSV 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
