# -*- coding: utf-8 -*-
"""스캔 282라운드 회귀 — ingest_partners.py + deploy/bootstrap.sh 결함 2건
   (ingest_partners.py 사상 첫 주조사, 정밀조사 Agent가 발견 후 독립 재검증).

  [1][심각] load_journal() 은 companies 가 list 인지만 확인하고 그 원소 하나하나가
      dict 인지는 안 봤다 — 리서치 에이전트 출력이 스키마를 완벽히 안 지킨 원소
      (맨 문자열·None 등) 하나만 섞여도 main() 루프의 c.get("name") 에서
      AttributeError 로 죽는다. 이 스크립트는 existing 을 메모리에서만 쌓다가
      루프가 끝나야 파일에 한 번 쓰므로(json.dump 가 루프 밖 한 곳뿐), 죽는
      순간 이미 검증까지 마친 앞쪽 항목들까지 전부 파일에 안 남고 사라진다
      (실측 확인: 크래시 후 파일이 실행 전과 바이트 단위로 동일). 형제
      (이름없음·출처없음 거부)와 같은 방식으로 dict 아닌 원소만 건너뛰도록 수정.

  [2] deploy/bootstrap.sh 가 이 스크립트를 인자 없이(`python ingest_partners.py`)
      호출했다 — 이 스크립트는 journal.jsonl 경로를 필수 인자로 받는데(없으면
      usage 출력 후 exit 1), 신선한 배포마다 100% 실패해 `&& ok || warn`
      관용구로 "건너뜀" 경고만 조용히 남겼다(실측: 실제 서브프로세스 실행으로
      재현). 설령 인자를 준다 해도 소용없다 — 협력업체 398개사는 바로 위
      `manage.py init` 이 partners_seed.json 을 이미 읽어 운영 DB 에 넣은
      뒤라, 이 스크립트는 그 JSON 파일 자체만 갱신할 뿐 이미 초기화가 끝난
      DB 에는 반영되지 않는다. 배포 자동화가 아니라 리서치 결과를 손으로
      병합하는 로컬 유지보수 CLI임이 드러나 bootstrap.sh 의 호출 자체를 제거.

  ⚠ 이 테스트는 임시 디렉터리의 격리 파일만 쓴다 — 운영 데이터는 전혀
    건드리지 않는다. sqlite DB 를 안 쓰는 순수 파일 도구라 BOKGUON_DB_PATH 는
    필요 없다.

      python test_scan_round282_fixes.py
"""
import io
import json
import os
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


IP_SRC = read("ingest_partners.py")
BOOT_SRC = read(os.path.join("deploy", "bootstrap.sh"))

print("=" * 72)
print("  스캔 282라운드 회귀 — ingest_partners.py 비-dict 원소 크래시·배치유실")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_main = IP_SRC.index("def main():")
main_body = IP_SRC[i_main:]
chk("isinstance(c, dict)" in main_body,
    "★★★★★ main() 루프가 companies 원소의 dict 여부를 확인한다"
    "(고치기 전엔 확인 없이 바로 c.get() 호출)")
chk('"$APP_DIR/ingest_partners.py"' not in BOOT_SRC,
    "★★★★ bootstrap.sh 가 인자 없이 실패하던 ingest_partners.py 실행 호출 자체를 제거했다"
    "(설명 주석에 파일명이 남는 것과는 별개 — 실제 실행 줄이 없는지 확인)")

# ============================================================
print("\n[2] 실행 준비")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
_tmpdir = tempfile.mkdtemp(prefix="round282_")
_seed_path = os.path.join(_tmpdir, "seed.json")
_journal_path = os.path.join(_tmpdir, "journal.jsonl")


def _write_seed(companies):
    io.open(_seed_path, "w", encoding="utf-8").write(
        json.dumps(companies, ensure_ascii=False))


def _write_journal(company_list):
    rec = {"type": "result", "result": {"companies": company_list}}
    io.open(_journal_path, "w", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")


def _run_ingest():
    r = subprocess.run([PY, "ingest_partners.py", _journal_path], cwd=HERE,
                        capture_output=True, text=True, encoding="utf-8", timeout=30)
    return r.returncode, r.stdout + r.stderr


# ============================================================
print("\n[3] 실행 — 비-dict 원소가 섞여도 크래시 없이, 앞뒤 정상 항목이 살아남는가")
# ------------------------------------------------------------
try:
    _write_seed([])
    good1 = {"name": "R282정상업체1", "partner_type": "시공사", "major": "누수·배관·설비",
              "source_url": "http://example.com/1"}
    good2 = {"name": "R282정상업체2", "partner_type": "시공사", "major": "도장·방수·미장",
              "source_url": "http://example.com/2"}
    _write_journal([good1, "그냥문자열", good2, None, 12345])

    #  ⚠ ingest_partners.py 는 자기 디렉터리의 data/partners_seed.json 을 고정
    #    경로로 연다 — 실제 스크립트를 건드리지 않고 임시 seed 를 쓰게 하려면
    #    모듈을 직접 불러 SEED 를 몽키패치한다(정밀조사 Agent와 같은 방법).
    import ingest_partners as IP
    _orig_seed = IP.SEED
    IP.SEED = _seed_path
    _orig_argv = sys.argv
    sys.argv = ["ingest_partners.py", _journal_path]
    _out = io.StringIO()
    import contextlib
    try:
        with contextlib.redirect_stdout(_out):
            rc = IP.main()
    finally:
        IP.SEED = _orig_seed
        sys.argv = _orig_argv

    chk(rc == 0, "★★★★★ 비-dict 원소가 섞여도 main() 이 예외 없이 정상 종료한다"
        "(고치기 전엔 AttributeError 로 크래시)", _out.getvalue())

    with io.open(_seed_path, encoding="utf-8") as f:
        saved = json.load(f)
    names = {p["name"] for p in saved}
    chk("R282정상업체1" in names and "R282정상업체2" in names,
        "★★★★★★ 비-dict 원소 앞뒤의 정상 항목이 둘 다 파일에 남는다"
        "(고치기 전엔 크래시로 파일이 실행 전과 바이트 단위로 동일 — 전부 유실)",
        names)
    chk(len(saved) == 2, "STEP 비-dict 3개(문자열·None·정수)는 전부 제외로 걸러졌다", len(saved))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드282 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — 회귀 없음: 전부 정상인 배치는 그대로 처리되는가")
# ------------------------------------------------------------
try:
    _write_seed([])
    good3 = {"name": "R282정상업체3", "partner_type": "시행사", "major": "종합 원상복구",
              "source_url": "http://example.com/3"}
    _write_journal([good3])

    IP.SEED = _seed_path
    sys.argv = ["ingest_partners.py", _journal_path]
    try:
        rc2 = IP.main()
    finally:
        IP.SEED = _orig_seed
        sys.argv = _orig_argv

    with io.open(_seed_path, encoding="utf-8") as f:
        saved2 = json.load(f)
    chk(rc2 == 0 and len(saved2) == 1 and saved2[0]["name"] == "R282정상업체3",
        "STEP 정상 배치는 회귀 없이 그대로 처리된다", saved2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드282 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — 실제 서브프로세스: 인자 없이 부르면 여전히 안전하게 실패하는가"
      "(bootstrap.sh 가 예전에 겪던 바로 그 상황, 회귀 확인용)")
# ------------------------------------------------------------
try:
    r = subprocess.run([PY, "ingest_partners.py"], cwd=HERE,
                        capture_output=True, text=True, encoding="utf-8", timeout=15)
    chk(r.returncode == 1 and "usage:" in (r.stdout + r.stderr),
        "STEP 인자 없이 부르면 여전히 안내문구와 함께 exit 1 — 이 동작 자체는 "
        "정상이라 안 바꿈(고쳐야 할 곳은 bootstrap.sh 의 호출 자체였다)",
        r.stdout + r.stderr)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드282 [5] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
