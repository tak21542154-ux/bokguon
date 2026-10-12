# -*- coding: utf-8 -*-
"""스캔 121라운드 회귀 — 회사정보 JSON 손상 침묵(legal_docs·manage.py 양쪽) +
   비원자적 저장, 수수료율 inf 입력 크래시, 사진백업 최신성 점검이 _trash 를
   원본 최신파일로 잘못 센다.

  [1] legal_docs._load_info()/manage.py:_read_info() 가 JSON 손상을 "아직
      설정 안 함"과 똑같이 조용히 삼켜, 이미 입력해 둔 8개 항목 전부가
      아무 경고 없이 "(미기재)"로 되돌아갈 수 있었다. cmd_set_info() 의
      비원자적 저장(디스크풀·강제종료 시 반쪽 JSON)이 실제 발화 경로다.
  [2] manage.py set-fee/create-insurer 가 float("inf") 는 통과시키고
      round(inf*100) 의 OverflowError(ValueError 아님)에 그대로 죽었다
      (nan 은 반대로 정상 처리돼 방어가 들쭉날쭉했다).
  [3] manage.py 의 사진 백업 최신성 점검(_newest_mtime)이 _trash 를
      빼지 않아, prune-orphans/go-live 정리 직후 방금 옮겨진 휴지통
      파일의 mtime 을 "원본의 최신 사진"으로 오인해 실제로는 안 뒤처진
      백업을 "뒤처졌다"고 오탐했다.

      python test_scan_round121_fixes.py
"""
import contextlib
import io
import logging
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


LEGAL_SRC = read("legal_docs.py")
MANAGE_SRC = read("manage.py")

print("═" * 72)
print("  스캔 121라운드 회귀 — 회사정보 침묵/비원자적저장·수수료율inf크래시·백업오탐")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
li_body = _py_fn_body(LEGAL_SRC, "_load_info")
chk("FileNotFoundError" in li_body and "_log.warning" in li_body,
    "★★ legal_docs._load_info 가 손상과 '파일없음'을 구분해 손상만 경고한다")

ri_body = _py_fn_body(MANAGE_SRC, "_read_info")
chk("FileNotFoundError" in ri_body and "warn(" in ri_body,
    "★★ manage.py:_read_info 도 같은 구분을 한다")

si_body = _py_fn_body(MANAGE_SRC, "cmd_set_info")
chk(".part" in si_body and "os.replace(part, INFO_PATH)" in si_body,
    "★★★ cmd_set_info 가 .part+os.replace 원자적 저장을 쓴다(cmd_backup 과 같은 방식)")

chk("math.isfinite" in _py_fn_body(MANAGE_SRC, "cmd_set_fee"),
    "★★★ cmd_set_fee 가 math.isfinite 로 inf/-inf 를 막는다")
chk("math.isfinite" in _py_fn_body(MANAGE_SRC, "cmd_create_insurer"),
    "★★★ cmd_create_insurer 도 같은 방어를 한다")

nm_body = _py_fn_body(MANAGE_SRC, "_newest_mtime") if "\ndef _newest_mtime(" in MANAGE_SRC else None
# _newest_mtime 은 cmd_check 내부 중첩함수라 위 헬퍼로 안 잡힌다 — 직접 텍스트로 확인
chk('_trash = os.path.normcase(os.path.join(root, "_trash"))' in MANAGE_SRC
    and MANAGE_SRC.count('_trash = os.path.normcase(os.path.join(root, "_trash"))') >= 1,
    "★★★ _newest_mtime 이 _trash 를 빼고 센다(형제 _orphan_photo_files 와 같은 방식)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 회사정보 로더가 손상만 경고하는가 (legal_docs)")
# ──────────────────────────────────────────────────────────────
sys.path.insert(0, HERE)
_tmpdir = tempfile.mkdtemp(prefix="round121_")

try:
    import legal_docs as LD

    class _Cap(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(record)

    cap = _Cap()
    logger = logging.getLogger("legal_docs")
    logger.addHandler(cap)
    logger.setLevel(logging.WARNING)
    try:
        _orig_path = LD._INFO_PATH
        # (a) 파일이 아예 없는 정상 상태 — 경고가 뜨면 안 된다
        LD._INFO_PATH = os.path.join(_tmpdir, "no_such_file.json")
        r_missing = LD._load_info()
        chk(r_missing == {} and not cap.records,
            "STEP 파일이 아예 없으면 조용히 {}(경고 없음) — 정상 상태를 오탐하지 않는다",
            (r_missing, len(cap.records)))
        # (b) 손상된 JSON — 이제는 경고가 떠야 한다
        broken_path = os.path.join(_tmpdir, "broken.json")
        io.open(broken_path, "w", encoding="utf-8").write('{"dpo": "홍길동 이')  # 잘림
        LD._INFO_PATH = broken_path
        r_broken = LD._load_info()
        chk(r_broken == {}, "STEP 손상된 JSON 은 여전히 {} 를 반환한다(호출부 안 건드림)", r_broken)
        chk(any("company_info.json" in r.getMessage() for r in cap.records),
            "★★★ 손상된 JSON 은 이제 경고 로그를 남긴다(예전엔 완전 침묵)",
            [r.getMessage() for r in cap.records])
    finally:
        LD._INFO_PATH = _orig_path
        logger.removeHandler(cap)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드121 준비/실행(legal_docs)", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 수수료율 inf 입력이 더 이상 크래시하지 않는다 (manage.py)")
# ──────────────────────────────────────────────────────────────
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
try:
    import db as DB
    DB.init_db()
    import manage as M

    # ── cmd_set_info 가 실제로 원자적으로 저장하고, _read_info 가 손상만
    #    경고하는지 — 진짜 data/company_info.json 은 절대 안 건드리도록
    #    M.INFO_PATH 를 임시경로로 바꿔서 실행한다 ──────────────────────
    _orig_info_path = M.INFO_PATH
    try:
        M.INFO_PATH = os.path.join(_tmpdir, "manage_company_info.json")
        buf0 = io.StringIO()
        with contextlib.redirect_stdout(buf0):
            M.cmd_set_info(["dpo", "R121테스트 담당자"])
        saved = M._read_info()
        chk(saved.get("dpo") == "R121테스트 담당자" and not os.path.exists(M.INFO_PATH + ".part"),
            "★★★ cmd_set_info 가 실제로 저장하고 .part 찌꺼기를 안 남긴다",
            (saved, os.path.exists(M.INFO_PATH + ".part")))

        io.open(M.INFO_PATH, "w", encoding="utf-8").write('{"dpo": "잘린 J')  # 고의 손상
        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            back = M._read_info()
        chk(back == {} and "company_info.json" in buf1.getvalue(),
            "★★★ manage.py:_read_info 도 손상 시 화면에 실제로 경고를 찍는다"
            "(예전엔 legal_docs 와 마찬가지로 완전 침묵)",
            (back, buf1.getvalue()[:200]))
    finally:
        M.INFO_PATH = _orig_info_path

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc1 = M.cmd_set_fee(["없는기관", "inf"])
    chk(rc1 == 1 and "숫자로 입력" in buf.getvalue(),
        "★★★ set-fee 에 inf 를 줘도 크래시 대신 친절한 안내로 끝난다"
        "(예전엔 OverflowError 로 그대로 죽었다)", (rc1, buf.getvalue()[:200]))

    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        rc2 = M.cmd_create_insurer(["R121테스트보험사", "r121insln", "inf"])
    chk(rc2 == 1 and "숫자로 입력" in buf2.getvalue(),
        "★★★ create-insurer 도 마찬가지다", (rc2, buf2.getvalue()[:200]))

    # 과잉차단 아님 — 정상 숫자는 여전히 통과한다
    buf3 = io.StringIO()
    with contextlib.redirect_stdout(buf3):
        rc3 = M.cmd_set_fee(["없는기관", "9.5"])
    chk(rc3 == 1 and "찾을 수 없습니다" in buf3.getvalue(),
        "STEP 정상 숫자는 여전히 파싱을 통과한다(그 다음 단계인 '기관 없음'까지 간다)",
        (rc3, buf3.getvalue()[:200]))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드121 준비/실행(manage.py inf)", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 사진백업 최신성 점검이 _trash 를 더 이상 원본최신으로 안 센다")
# ──────────────────────────────────────────────────────────────
try:
    #  cmd_check() 내부 중첩함수라 임포트로 못 부른다 — 정확한 현재 소스에서
    #  함수 본문을 그대로 뽑아 격리된 네임스페이스에서 실행한다(에이전트가
    #  조사 때 쓴 것과 같은 방법 — 로직이 원본과 100% 동일함을 보장한다).
    start = MANAGE_SRC.index("    def _newest_mtime(root):")
    end = MANAGE_SRC.index("return latest, n", start) + len("return latest, n")
    fn_src = MANAGE_SRC[start:end]
    import textwrap
    ns = {"os": os}
    exec(compile("import os\n" + textwrap.dedent(fn_src), "<_newest_mtime>", "exec"), ns)
    _newest_mtime = ns["_newest_mtime"]

    up = os.path.join(_tmpdir, "uploads")
    bk = os.path.join(_tmpdir, "backup_uploads")
    os.makedirs(os.path.join(up, "case1"))
    os.makedirs(os.path.join(bk, "case1"))
    os.makedirs(os.path.join(up, "_trash", "case1"))

    old_t = time.time() - 10 * 86400
    src_photo = os.path.join(up, "case1", "old_photo.jpg")
    bk_photo = os.path.join(bk, "case1", "old_photo.jpg")
    io.open(src_photo, "w").write("x")
    io.open(bk_photo, "w").write("x")
    os.utime(src_photo, (old_t, old_t))
    os.utime(bk_photo, (old_t, old_t))     # 백업이 원본과 완전히 보조를 맞춘 정상 상태

    trash_photo = os.path.join(up, "_trash", "case1", "deleted_photo.jpg")
    io.open(trash_photo, "w").write("x")   # mtime = 지금(방금 정리로 옮겨진 것)

    src_latest, src_n = _newest_mtime(up)
    bk_latest, bk_n = _newest_mtime(bk)
    gap_h = (src_latest - bk_latest) / 3600.0
    chk(src_n == 1, "★★ _trash 안 파일은 원본 파일수에도 안 잡힌다(형제 함수와 동일 규칙)",
        src_n)
    chk(abs(gap_h) < 1,
        "★★★ 방금 정리된 _trash 파일이 있어도 원본·백업이 '보조를 맞추고 있음'으로 "
        "정확히 판정된다(예전엔 240시간 차이로 '백업이 뒤처졌다' 오탐)",
        f"{gap_h:.1f}시간 차이")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드121 준비/실행(사진백업 오탐)", f"{type(e).__name__} {e}")
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
