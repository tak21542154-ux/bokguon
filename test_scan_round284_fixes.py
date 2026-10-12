# -*- coding: utf-8 -*-
"""스캔 284라운드 회귀 — photo_ai.py EXIF제거 재인코딩이 8MB 상한을 못 지키던 결함
   (photo_ai.py 의 EXIF 이외 로직 최초 정밀조사, 정밀조사 Agent가 발견 후 독립 재검증).

  [심각] _strip_exif() 가 위치정보 제거를 위해 **고정 품질 92**로 재인코딩했다.
      save_upload() 는 업로드 **원본** 바이트만 8MB 상한과 대조하고(201-205행),
      재인코딩 **결과** 바이트는 그 뒤로 아무도 상한과 다시 대조하지 않은 채 그대로
      디스크에 쓰고 photos.size 로 반환했다. 이미 낮은 품질로 압축된 원본(카카오톡
      재전송 사진 등)은 픽셀 디테일은 그대로인데 더 높은 품질로 다시 압축하면
      파일이 커진다 — 정밀조사 Agent 실측: 7.2MB 원본이 재인코딩 후 11.7MB(상한
      40% 초과)로 아무 로그·표식 없이 저장됐다. 이 파일 자신이 사용자에게 보여주는
      "장당 8MB 이하" 안내가 저장 단계에서는 지켜지지 않았던 것.
      품질을 92→80→65→50→35 로 단계적으로 낮춰 가며 상한 안에 드는 첫 결과를
      쓰도록 수정(_save_within_budget) — 전부 시도해도 안 되면(PNG 는 애초에 품질
      다이얼이 없어 1회 시도) 원본을 그대로 저장하는 대신 정직하게 거부한다
      (이 파일의 다른 "복구 불가능한 손상" 케이스와 같은 UploadError 경로).

  ⚠ 이 테스트는 임시 디렉터리의 격리 파일만 쓴다 — 운영 uploads/ 는 전혀
    건드리지 않는다. sqlite DB 를 안 쓰는 순수 이미지 처리 모듈이라
    BOKGUON_DB_PATH 는 필요 없다.

      python test_scan_round284_fixes.py
"""
import io
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


PH_SRC = read("photo_ai.py")

print("=" * 72)
print("  스캔 284라운드 회귀 — photo_ai.py 재인코딩 8MB 상한 미준수")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("_save_within_budget" in PH_SRC and "_QUALITY_STEPS" in PH_SRC,
    "★★★★★ _strip_exif() 재인코딩이 품질을 단계적으로 낮춰 상한을 지키려 시도한다"
    "(고치기 전엔 고정 품질 92 한 번뿐)")
chk("except UploadError:\n        raise" in PH_SRC,
    "★★★★ 상한을 못 지키면 원본으로 조용히 대체하지 않고 UploadError 로 거부한다"
    "(고치기 전엔 바깥 except Exception 이 그 경로 자체가 없어 걸릴 일이 없었다)")

# ============================================================
print("\n[2] 실행 준비")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
from PIL import Image                                                # noqa: E402
import photo_ai as PH                                                 # noqa: E402

_orig_max = PH.MAX_FILE_BYTES


def _noise_jpeg(size=400, quality=20, seed=42):
    """이미 낮은 품질로 압축된 원본을 흉내(카카오톡 재전송 사진 등) — 픽셀은 노이즈라
    디테일은 그대로인데 원본 자체는 저품질(20)로 작게 압축돼 있다. 이 바이트를
    _strip_exif() 에 넣으면 고정 품질(92, 원본보다 높음)로 재인코딩하면서 파일이
    오히려 커진다 — 정밀조사 Agent가 실측한 것과 같은 성장 방향(사전 탐색으로
    이 조합에서 원본 32,350B → 재인코딩 56,943B, 1.76배 성장을 직접 확인함)."""
    random.seed(seed)
    im = Image.new("RGB", (size, size))
    px = im.load()
    for x in range(size):
        for y in range(size):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    out = io.BytesIO()
    im.save(out, format="JPEG", quality=quality)
    return out.getvalue()


def _noise_png(size=120, seed=7):
    random.seed(seed)
    im = Image.new("RGB", (size, size))
    px = im.load()
    for x in range(size):
        for y in range(size):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    out = io.BytesIO()
    im.save(out, format="PNG")
    return out.getvalue()


_src = _noise_jpeg()

# ============================================================
print("\n[3] 실행 — 고정품질 하나로는 상한을 못 지키는 상황에서, 품질을 낮춰 실제로 지키는가")
# ------------------------------------------------------------
try:
    #  사전 탐색 확인: 이 저품질(20) 원본은 32,350B — quality=92 재인코딩 시
    #  56,943B 로 커져 상한(40000)을 넘지만, quality=35 까지 내려가면 넘지 않는다.
    PH.MAX_FILE_BYTES = 40000
    out_bytes, err = PH._strip_exif(_src, "jpg")
    chk(err is None, "STEP 재인코딩 자체는 정상 성공(EXIF 실패 아님)", err)
    chk(len(out_bytes) <= 40000,
        "★★★★★★ 재인코딩 결과가 실제로 상한 안에 든다"
        "(고치기 전엔 고정품질 92의 결과를 그대로 반환해 상한을 넘어도 그대로 저장됐다)",
        len(out_bytes))

    #  대조군: 고정 품질 92 하나만 썼다면 이 상한을 못 지켰을 것(회귀 시나리오 재현 확인)
    _q92 = io.BytesIO()
    Image.open(io.BytesIO(_src)).save(_q92, format="JPEG", quality=92, optimize=True)
    chk(len(_q92.getvalue()) > 40000,
        "STEP 대조군 — 옛 고정품질(92) 결과는 실제로 이 상한을 넘었다"
        "(이 테스트가 진짜 그 상황을 재현했는지 확인)", len(_q92.getvalue()))
finally:
    PH.MAX_FILE_BYTES = _orig_max

# ============================================================
print("\n[4] 실행 — 가장 낮은 품질로도 도저히 상한을 못 지키면 원본을 그대로 쓰는 대신 거부하는가")
# ------------------------------------------------------------
try:
    PH.MAX_FILE_BYTES = 100          # 어떤 실제 사진도 못 지킬 상한
    raised = False
    try:
        PH._strip_exif(_src, "jpg")
    except PH.UploadError:
        raised = True
    chk(raised,
        "★★★★★ 모든 품질 단계로도 상한을 못 지키면 UploadError 로 거부한다"
        "(원본을 그대로 저장하며 성공으로 위장하지 않는다)")
finally:
    PH.MAX_FILE_BYTES = _orig_max

# ============================================================
print("\n[5] 실행 — PNG: 품질 다이얼이 없어도 상한 초과 시 조용히 넘기지 않고 거부하는가")
# ------------------------------------------------------------
try:
    _png = _noise_png()
    PH.MAX_FILE_BYTES = len(_png) // 3   # optimize 재인코딩으로도 못 지킬 만큼 낮춤
    raised_png = False
    try:
        PH._strip_exif(_png, "png")
    except PH.UploadError:
        raised_png = True
    chk(raised_png,
        "★★★★ PNG 도 재인코딩 후 상한을 넘으면 원본을 그대로 쓰지 않고 거부한다")
finally:
    PH.MAX_FILE_BYTES = _orig_max

# ============================================================
print("\n[6] 실행 — 회귀 없음: 평범한 사진(상한 안에 첫 시도로 들어감)은 그대로 성공하는가")
# ------------------------------------------------------------
try:
    #  기본 상한(8MB)에서는 이 작은 노이즈 이미지도 quality=92 로 여유 있게 들어간다
    out2, err2 = PH._strip_exif(_src, "jpg")
    chk(err2 is None and len(out2) <= PH.MAX_FILE_BYTES,
        "STEP 기본 상한(8MB)에서는 평범한 사진이 회귀 없이 정상 처리된다",
        (err2, len(out2)))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드284 [6] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[7] 실행 — 실제 save_upload() 종단: 상한 초과 상황이 사용자에게 안내되는가")
# ------------------------------------------------------------
try:
    class _FakeFileStorage:
        def __init__(self, data, filename):
            self._data = data
            self.filename = filename

        def read(self, n=-1):
            return self._data[:n] if n and n > 0 else self._data

    _tmpdir = tempfile.mkdtemp(prefix="round284_")
    _orig_root = PH.UPLOAD_ROOT
    PH.UPLOAD_ROOT = _tmpdir
    #  원본(32,350B) 은 이 상한을 여유있게 통과하지만, 옛 고정품질(92) 재인코딩
    #  결과(56,943B)는 넘는다 — save_upload() 의 입력단 크기검사(201-205행)는
    #  통과하고도 저장 직전 재인코딩에서 비로소 상한을 넘기던 실제 시나리오.
    PH.MAX_FILE_BYTES = 40000
    try:
        info = PH.save_upload(_FakeFileStorage(_src, "현장사진.jpg"), case_id=1)
        saved_path = os.path.join(_tmpdir, info["rel_path"].replace("/", os.sep))
        actual_size = os.path.getsize(saved_path)
        chk(actual_size <= 40000,
            "★★★★★★ save_upload() 종단에서도 실제 디스크 파일이 상한을 넘지 않는다"
            "(정밀조사 Agent가 재현한 것과 같은 종단간 확인 — 고치기 전엔 여기서"
            " 56,943B 짜리 파일이 40000B 상한을 넘겨 그대로 저장됐다)",
            actual_size)
        chk(info["size"] == actual_size,
            "STEP 반환된 size 가 실제 디스크 파일 크기와 일치한다(photos.size 로 그대로 저장됨)")
    finally:
        PH.UPLOAD_ROOT = _orig_root
        PH.MAX_FILE_BYTES = _orig_max
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드284 [7] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
