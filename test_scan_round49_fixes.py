# -*- coding: utf-8 -*-
"""스캔 49라운드 회귀 — 사진 파일 정리 2곳.

  조사 에이전트가 실측(monkeypatch 재현)으로 증명한 결함 2곳:
  ① photo_ai.save_upload() 가 쓰다가 실패하면(디스크 꽉 참 등) os.open이
     이미 만든 빈 파일이 남는다 — 실패 시 rel_path 를 안 돌려주므로 호출부가
     못 지운다.
  ② manage.py prune-orphans 가 사진 파일을 **커밋보다 먼저** 휴지통으로
     옮겼다 — 커밋이 롤백되면 DB 행은 되살아나는데 파일은 이미 옮겨져
     "행은 있는데 파일이 없는" 상태가 된다(실제 삭제 라우트와 반대 순서).

      python test_scan_round49_fixes.py
"""
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


PHOTO_SRC = read("photo_ai.py")
MANAGE_SRC = read("manage.py")

print("═" * 72)
print("  스캔 49라운드 회귀 — 사진 파일 정리(쓰기 실패 잔여·정리순서)")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 배선이 실제로 있는가")
# ──────────────────────────────────────────────────────────────
chk("with os.fdopen(fd, \"wb\") as f:\n            f.write(data)\n    except Exception:"
    in PHOTO_SRC, "① save_upload 쓰기가 try/except 로 감싸졌다")
chk("os.remove(full)" in PHOTO_SRC, "① 실패 시 os.remove 로 잔여 파일을 지운다")
chk("os.close(fd)" in PHOTO_SRC,
    "★★ 지우기 전에 fd 를 먼저 닫는다(Windows 는 열린 핸들의 파일을 못 지움)")

#  ⚠ manage.py 전체에는 "finally:\n conn.close()" 가 여러 함수에 걸쳐 4번
#    나온다 — 파일 전체에서 첫 매치만 찾으면 엉뚱한(더 앞선) 명령의 close 와
#    비교하게 돼 순서가 우연히 맞아도 아무것도 검증하지 못한다. 반드시
#    cmd_prune_orphans **함수 안**으로 좁혀서 봐야 한다.
_fn_start = MANAGE_SRC.index("def cmd_prune_orphans")
_fn_end = MANAGE_SRC.find("\ndef ", _fn_start + 1)
_fn_body = MANAGE_SRC[_fn_start:_fn_end if _fn_end != -1 else None]
_idx_close = _fn_body.find("finally:\n        conn.close()")
_idx_trash = _fn_body.find("휴지통(_trash)으로 옮겼습니다")
chk(_idx_close != -1 and _idx_trash != -1 and _idx_close < _idx_trash,
    "★★★ ② 사진 파일 이동 코드가 (cmd_prune_orphans 안에서) conn.close() 뒤로 옮겨졌다",
    (_idx_close, _idx_trash))

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — ① 쓰기 실패 시 실제로 파일이 안 남는가")
# ──────────────────────────────────────────────────────────────
_tmpdir1 = tempfile.mkdtemp(prefix="photoclean49_")
os.environ["BOKGUON_UPLOAD_DIR"] = _tmpdir1
sys.path.insert(0, HERE)
try:
    import photo_ai as PHOTO
    import importlib
    importlib.reload(PHOTO)   # UPLOAD_ROOT 를 지금 env 로 다시 굳힌다

    case_dir = os.path.join(_tmpdir1, "999")

    class _Boom:
        def __init__(self, *a, **k):
            raise OSError(28, "No space left on device")   # ENOSPC 재현

    _orig_fdopen = os.fdopen
    os.fdopen = _Boom

    #  ⚠ 가짜 매직바이트만 주면 _strip_exif 의 디코드 단계에서 먼저 UploadError 로
    #    막혀, 정작 보려는 쓰기 실패 경로(os.fdopen)까지 못 간다 — 진짜 디코드
    #    가능한 최소 JPEG 이 필요하다.
    from PIL import Image as _PILImage
    _buf = io.BytesIO()
    _PILImage.new("RGB", (4, 4), (200, 100, 50)).save(_buf, format="JPEG")
    _real_jpeg = _buf.getvalue()

    class _FS:
        filename = "boom.jpg"

        def read(self, n):
            return _real_jpeg

    try:
        PHOTO.save_upload(_FS(), 999)
        chk(False, "★ 쓰기 실패가 예외로 전파된다(사전 조건)")
    except OSError:
        chk(True, "★ 쓰기 실패가 예외로 전파된다(사전 조건)")
    finally:
        os.fdopen = _orig_fdopen

    leftover = os.listdir(case_dir) if os.path.isdir(case_dir) else []
    chk(leftover == [], "★★★ 실패한 쓰기가 파일을 남기지 않는다(잔여 0개)", leftover)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ ① 쓰기실패 잔여 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    import shutil
    shutil.rmtree(_tmpdir1, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — ② 순서를 바꾸고도 prune-orphans 가 여전히 제대로 도는가")
# ──────────────────────────────────────────────────────────────
_tmpdir2 = tempfile.mkdtemp(prefix="prune49_")
db_path = os.path.join(_tmpdir2, "verify.db")
upload_dir = os.path.join(_tmpdir2, "uploads")
env = dict(os.environ, BOKGUON_DB_PATH=db_path, BOKGUON_UPLOAD_DIR=upload_dir,
          BOKGUON_ENV="dev", BOKGUON_SEED_DEMO="0", PYTHONIOENCODING="utf-8")
try:
    os.environ["BOKGUON_DB_PATH"] = db_path
    os.environ["BOKGUON_UPLOAD_DIR"] = upload_dir
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    #  부모 없는(고아) 사진 행 — case_id 가 가리키는 사건이 없다
    orphan_dir = os.path.join(upload_dir, "9999")
    os.makedirs(orphan_dir, exist_ok=True)
    orphan_file = os.path.join(orphan_dir, "orphan.jpg")
    io.open(orphan_file, "wb").write(b"fake-jpg-bytes")
    conn.execute(
        "INSERT INTO photos(case_id,rel_path,uploader_role,uploader) "
        "VALUES(9999,'9999/orphan.jpg','협력사','검증49')")
    conn.commit()
    _pid = conn.execute("SELECT id FROM photos WHERE rel_path='9999/orphan.jpg'").fetchone()["id"]
    conn.close()

    r = subprocess.run([sys.executable, "manage.py", "prune-orphans", "--yes"],
                       capture_output=True, text=True, encoding="utf-8", env=env,
                       cwd=HERE, timeout=30)
    chk(r.returncode == 0, "② prune-orphans 가 정상 종료한다", r.stdout[-500:] + r.stderr[-300:])

    conn = DB.get_db()
    row = conn.execute("SELECT id FROM photos WHERE id=?", (_pid,)).fetchone()
    conn.close()
    chk(row is None, "★★ 고아 사진 행이 실제로 지워졌다")
    chk(not os.path.isfile(orphan_file), "★★ 원래 자리에는 파일이 없다(옮겨짐)")
    trash_file = os.path.join(upload_dir, "_trash", "9999", "orphan.jpg")
    chk(os.path.isfile(trash_file), "★★★ 파일이 휴지통(_trash)으로 정확히 옮겨졌다", trash_file)
    if os.path.isfile(trash_file):
        chk(io.open(trash_file, "rb").read() == b"fake-jpg-bytes",
            "휴지통 파일 내용이 원본과 같다(단순 이동, 손상 없음)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ ② prune-orphans 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir2, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
