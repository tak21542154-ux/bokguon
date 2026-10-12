# -*- coding: utf-8 -*-
"""스캔 328라운드 회귀 — save_upload()(photo_ai.py)가 HEIC 변환 뒤 크기를
   다시 안 재서 '장당 8MB' 상한이 조용히 깨질 수 있던 결함[중간], 이 세션
   사상 첫 정밀조사한 정밀조사 Agent가 발견(app.py 480개 함수단위 재구성이
   140개+ 미조사로 정체되자, "등급게이트 vs 감사로그" 패턴(326·327라운드)이
   소진된 뒤 완전히 새 파일로 전환해 찾음 — dispatch.py 4형제·CSRF/rate-limit
   클러스터는 URL/동작 기반 테스트로 이미 광범위 검증돼 있음을 재확인해
   클린 처리, docs/ 불변식(306라운드)도 재실행해 재확인).

   save_upload()(252~316행)는 원본 바이트를 딱 한 번(259~263행)
   MAX_FILE_BYTES(8MB)와 대조한다. HEIC 업로드는 이후 _heic_to_jpeg()가
   새로 인코딩한 JPEG 로 data 가 통째로 바뀌는데(276행), 이 새 바이트는
   그 뒤 어디서도 상한과 다시 대조되지 않는다. _strip_exif()의 "정상
   경로"(jpg/webp 는 _save_within_budget, png 는 명시적 체크)는 자체적으로
   8MB 를 지키지만, 조기 반환 3곳 — 해상도 과대(122~124행)·
   DecompressionBombError(126~131행)·재인코딩 중 일반 예외(176~179행) —
   은 받은 data 를 상한 검사 없이 그대로 돌려준다. 직접 업로드된
   jpg/png/webp 는 이 세 곳에 와도 이미 259~263행에서 검증된 원본
   그대로라 안전하지만, HEIC 는 이 세 곳에 오는 data 가 방금 새로 만든
   재인코딩 결과라 한 번도 검증된 적이 없다 — 284라운드가 고친
   "재인코딩하면 커질 수 있다"는 위험이 이 세 갈래엔 안 미쳤던 것.
   (앞의 두 갈래는 _heic_to_jpeg 자신이 같은 MAX_PIXELS 로 먼저 걸러
   HEIC 경로에서는 이미 도달 불가 — 실질 구멍은 세 번째 재인코딩
   예외 갈래뿐이지만, 개별 갈래를 다 손보는 대신 save_upload() 의
   _strip_exif() 호출 직후 한 곳에서 다시 재는 것이 이 세 갈래 전부와
   향후 리팩터링에도 안전하다). 회귀테스트는 실제 _heic_to_jpeg() 를
   HEIC 코덱 없이도 재현 가능하도록, MAX_PIXELS·MAX_FILE_BYTES 를
   작게 낮추고 _heic_to_jpeg() 를 "실제 Pillow 로 인코딩한 진짜 JPEG
   바이트"를 돌려주는 대역으로 바꿔(해상도 과대 갈래를 실제로 태움 —
   HEIC 코덱 자체를 흉내내는 게 아니라 그 갈래 앞단만 대신함) 실제
   save_upload() 전체 흐름을 그대로 실행한다.
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r328_")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_scratch, "uploads")

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
print("  스캔 328라운드 회귀 — HEIC 변환 후 8MB 상한 재검증 누락")
print("=" * 74)

import photo_ai as PA  # noqa: E402
from PIL import Image  # noqa: E402

print("\n[1] 준비 — 실제 Pillow 로 '해상도 과대' 갈래를 밟을 진짜 JPEG를 만든다")
im = Image.new("RGB", (50, 50), color=(120, 60, 30))
_buf = io.BytesIO()
im.save(_buf, format="JPEG", quality=90)
FAKE_HEIC_OUTPUT = _buf.getvalue()
print(f"    실제 JPEG 크기: {len(FAKE_HEIC_OUTPUT)} 바이트, 픽셀수: {50*50}")

# 테스트 동안만 상한을 낮춰 이 작은 이미지로도 실제 조건을 그대로 재현한다
# (321라운드가 BOKGUON_SQLITE_BUSY_MS 를 낮춰 실제 락을 빨리 재현한 것과 같은 기법)
PA.MAX_PIXELS = 100          # 50*50=2500 > 100 → _strip_exif 의 "해상도 과대" 갈래를 실제로 밟는다
PA.MAX_FILE_BYTES = 200      # 실제 JPEG(수백~천여 바이트)가 이미 이 상한을 넘도록


def _fake_heic_to_jpeg(data, orig):
    # 실제 HEIC 코덱(pillow_heif) 없이도, _heic_to_jpeg() 가 "새로 인코딩한 JPEG
    # 바이트를 돌려준다"는 인터페이스 계약만 실제 Pillow 산출물로 재현한다.
    return FAKE_HEIC_OUTPUT, "jpg", "image/jpeg"


PA._heic_to_jpeg = _fake_heic_to_jpeg


class _FakeFileStorage:
    def __init__(self, data, filename):
        self._data = data
        self.filename = filename

    def read(self, n=-1):
        return self._data if n < 0 else self._data[:n]


# 진짜 HEIC 매직바이트(ftyp+heic) — sniff_image() 가 실제로 "heic" 로 판정하게 한다.
# 원본 업로드 자체는 (낮춘) MAX_FILE_BYTES 이내라 1차 검사(259~263행)는 통과해야 한다.
HEIC_MAGIC = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 20
assert len(HEIC_MAGIC) <= PA.MAX_FILE_BYTES, "픽스처 자체가 이미 상한을 넘으면 1차 검사에서 막혀 재현이 안 됨"

print("\n[2] 실행 — 이 조건으로 실제 save_upload() 를 그대로 호출한다")
fs = _FakeFileStorage(HEIC_MAGIC, "사진.heic")
try:
    result = PA.save_upload(fs, case_id=1)
    raised = None
except PA.UploadError as e:
    raised = e
    result = None

chk(raised is not None,
    "★★★★★ 재인코딩 결과가 상한을 넘으면 UploadError 로 거부된다"
    "(고치기 전엔 예외 없이 그대로 저장됐다)", raised)

if result is not None:
    chk(result["size"] <= PA.MAX_FILE_BYTES,
        "  (혹시 통과했다면) 최소한 저장된 크기가 상한 이내여야 한다", result["size"])
    saved_path = os.path.join(PA.UPLOAD_ROOT, result["rel_path"])
    on_disk = os.path.getsize(saved_path) if os.path.exists(saved_path) else -1
    chk(on_disk <= PA.MAX_FILE_BYTES,
        "  ★★★★★ 디스크에 실제로 쓰인 파일도 상한 이내여야 한다"
        "(고치기 전엔 여기서 실제로 상한을 넘겼다)", on_disk)
else:
    chk(True, "  (정상: 저장 자체가 거부돼 디스크에 아무것도 안 남는다)")

print("\n[3] 실행 — 정상 경로(상한 안의 이미지)는 회귀 없이 그대로 저장된다")
PA.MAX_PIXELS = 40_000_000
PA.MAX_FILE_BYTES = 8 * 1024 * 1024
PA._heic_to_jpeg = lambda data, orig: (FAKE_HEIC_OUTPUT, "jpg", "image/jpeg")
fs2 = _FakeFileStorage(HEIC_MAGIC, "사진2.heic")
try:
    result2 = PA.save_upload(fs2, case_id=2)
    #  ⚠ exif 제거 자체가 재인코딩이라 바이트 크기는 원본과 달라질 수 있다
    #    (정상 동작) — 여기선 "성공적으로 저장됐고 상한 안"만 확인한다.
    chk(result2 is not None and 0 < result2["size"] <= PA.MAX_FILE_BYTES,
        "  정상 크기의 이미지는 회귀 없이 그대로 저장된다(과잉차단 아님)",
        result2)
except PA.UploadError as e:
    chk(False, "  정상 크기의 이미지가 잘못 거부됨(과잉차단)", e)

print("\n" + "=" * 74)
print(f"  통과 {PASS} · 실패 {FAIL}")
if FAILED:
    print("\n  실패 항목:")
    for m in FAILED:
        print(f"    · {m}")
print("=" * 74)

sys.exit(1 if FAIL else 0)
