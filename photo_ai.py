# -*- coding: utf-8 -*-
"""시공 사진 — 검증 · 저장 · AI 자동 분류

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 이 모듈이 필요한가
  현장 작업자는 사진을 순서대로 찍어 올리지 않는다. 완료 사진을 먼저 올리고
  착공 전 사진을 나중에 올리는 일이 흔하고, 자재 영수증까지 같은 앨범에 섞여 있다.
  이걸 내부 직원이 일일이 눈으로 분류하면 사람이 병목이 된다.
  그래서 **일괄 업로드 → AI 자동 분류 → 사람은 낮은 신뢰도만 확인** 구조로 간다.

■ 보안 원칙 (업로드는 외부에서 들어오는 유일한 파일 경로다)
  1. 확장자를 믿지 않는다 — **파일 앞부분의 시그니처(매직 바이트)로 실제 형식을 판정**한다.
     `evil.php` 를 `evil.jpg` 로 바꿔 올리는 것을 막는 최소 조건이다.
  2. 원본 파일명을 쓰지 않는다 — `../../etc/passwd` 같은 경로 조작을 원천 차단하기 위해
     저장명은 서버가 만든 임의 값으로만 쓴다. 원본명은 표시용으로 DB에만 둔다.
  3. **웹 루트(static/) 밖에 저장**한다 — 사건 사진은 사고 현장·차량번호가 담긴 증거 자료다.
     주소를 아는 사람이 그냥 받아갈 수 있으면 안 되므로, 인증을 거치는 라우트로만 내보낸다.
  4. 응답의 Content-Type 은 **클라이언트가 보낸 값이 아니라 서버가 판정한 형식**을 쓴다.
"""
import os
import io
import hashlib
import secrets

HERE = os.path.dirname(os.path.abspath(__file__))
# ⚠ `.get(key, 기본값)` 은 키가 **빈 문자열로 존재**하면 기본값을 쓰지 않는다.
#    .env.example 에 `BOKGUON_UPLOAD_DIR=` 이 그대로 있어서, 지시대로 복사해 쓰면
#    UPLOAD_ROOT='' 가 되고 사진이 프로세스 작업디렉터리에 상대경로로 저장됐다.
#    그 경로는 백업 대상(uploads/)이 아니므로 사진이 조용히 백업에서 빠진다.
UPLOAD_ROOT = (os.environ.get("BOKGUON_UPLOAD_DIR") or "").strip() or os.path.join(HERE, "uploads")

# 사진 분류 — 보험사에 제출하는 증빙 체계와 같은 이름을 쓴다
KINDS = ["착공전", "시공중", "완료", "영수증", "기타"]
CONSTRUCTION_KINDS = ["착공전", "시공중", "완료"]      # 시공 사진
DOCUMENT_KINDS = ["영수증"]                            # ⚠ 시공 사진과 **분리해서** 보여줘야 한다

#  ⚠ "앱 전체 상한 10MB" 이던 시절의 비교 주석이었다 — 그 상한은 이미
#    BOKGUON_MAX_UPLOAD_MB(기본 260MB, app.py MAX_CONTENT_LENGTH)로 올라갔다
#    (요청 하나로 여러 장을 올리므로 장당 상한과 요청 전체 상한은 다른 값이다).
MAX_FILE_BYTES = 8 * 1024 * 1024        # 장당 8MB
MAX_FILES_PER_REQUEST = 30

# [PH-10] 사건 단위 누적 상한.
#   장당·요청당 제한만 있으면 인증된 협력사가 요청을 반복해서 디스크를 채울 수 있다.
#   디스크가 차면 사진뿐 아니라 **SQLite 쓰기까지 실패**해 서비스가 통째로 멈춘다.
#   복구 1건에 실제로 필요한 양(착공전·시공중·완료·영수증)을 넉넉히 덮되 유한하게 막는다.
#   운영 중 조정할 수 있게 env 로 뺀다(코드 수정·재배포 없이 튜닝).
def _int_env(key, default):
    try:
        v = int(os.environ.get(key, "").strip() or default)
        return v if v > 0 else default
    except ValueError:
        return default


MAX_FILES_PER_CASE = _int_env("BOKGUON_MAX_PHOTOS_PER_CASE", 200)
MAX_BYTES_PER_CASE = _int_env("BOKGUON_MAX_PHOTO_MB_PER_CASE", 300) * 1024 * 1024

# 파일 시그니처 → (확장자, MIME). 확장자가 아니라 이 값으로 판정한다.
_SIGNATURES = [
    (b"\xff\xd8\xff",                    "jpg",  "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n",               "png",  "image/png"),
]


def sniff_image(head: bytes):
    """파일 앞부분으로 실제 이미지 형식을 판정. (확장자, MIME) 또는 None."""
    for sig, ext, mime in _SIGNATURES:
        if head.startswith(sig):
            return ext, mime
    # WebP 는 RIFF....WEBP 구조라 오프셋 검사가 필요하다
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", "image/webp"
    # HEIC/HEIF — 아이폰 기본 형식. ftyp 박스의 브랜드로 판정한다.
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"heim"):
        return "heic", "image/heic"
    return None


class UploadError(Exception):
    """사용자에게 그대로 보여줘도 되는 업로드 오류."""


#  사진 한 장의 픽셀 상한. 4,000만 화소면 실무 사진(1억 화소 폰 포함 리사이즈 전)은
#  거의 다 통과하고, 압축폭탄은 못 통과한다.
MAX_PIXELS = int(os.environ.get("BOKGUON_MAX_IMAGE_PIXELS", "40000000"))


def _strip_exif(data, ext):
    """사진에서 EXIF 를 지운다. **(바이트, 실패사유) 를 돌려준다.**

    **디코딩 자체가 안 되면 업로드를 거부한다.** 파일이 손상됐거나 중간에
    끊겼으면 그 바이트에는 애초에 사진이 없다 — '원본을 그대로 저장'해도
    구제되는 사진이 없고, 다시 열면 그대로 깨져 있다(실측 2026-08-20: 잘린
    JPEG 를 넣으면 이 함수가 "성공"으로 원본을 그대로 돌려주고, 저장된 파일은
    다시 열어도 동일 오류로 렌더링이 안 됐다). HEIC 변환(_heic_to_jpeg)은
    이미 이렇게 거부한다 — 형식마다 다르게 다루지 않는다.

    디코딩은 됐는데 **재인코딩**(exif 제거용)만 실패하면 원본을 그대로
    돌려준다 — 사진을 잃는 것보다 낫다. 이 경우엔 GPS 가 남을 수 있으므로
    **실패 사유를 함께 돌려준다.**

    ⚠ 재인코딩 방식이라 화질이 아주 조금 떨어진다(품질 92). 시공 검수용으로는
      충분하고, 위치정보 유출을 막는 값어치가 훨씬 크다.
    """
    if ext not in ("jpg", "jpeg", "png", "webp"):
        return data, "지원하지 않는 형식"
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return data, "Pillow 미설치"

    try:
        #  ★ **압축폭탄을 먼저 막는다.** 0.24MB 짜리 9000×9000 단색 PNG 한 장이
        #    픽셀로 펼치면 6GB 다 — 8MB 파일 상한·장수 상한을 전부 통과하고,
        #    Pillow 기본 경고선(89,478,485px)에도 안 걸린다.
        #    waitress 는 단일 프로세스라 그 순간 세 포털이 함께 죽는다.
        #    공격이 아니어도 밟는다(고화소 폰 사진).
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        im = Image.open(io.BytesIO(data))
        _w, _h = im.size
        if _w * _h > MAX_PIXELS:
            return data, f"해상도 과대({_w}x{_h}) — 위치정보를 지우지 못했습니다"
        im.load()
    except Image.DecompressionBombError as e:
        #  ⚠ Pillow 자신의 상한(MAX_PIXELS 의 2배)을 넘으면 바로 위 수동 검사
        #    (_w*_h>MAX_PIXELS)에 닿기도 전에 Image.open() 이 여기서 먼저 터진다 —
        #    손상 파일이 아니라 '너무 큰 정상 파일'이므로 아래의 손상 거부로 묶지
        #    않고, 수동 검사와 같은 비치명적 경로(원본 저장 + 사유만 남김)를 쓴다.
        return data, f"해상도 과대 — 위치정보를 지우지 못했습니다 ({e})"
    except Exception as e:
        raise UploadError(
            f"사진 파일이 손상되었거나 업로드 중간에 끊겼습니다({type(e).__name__}). "
            f"다시 촬영하거나 다시 올려 주세요.")

    try:
        #  ⚠ `list(im.getdata())` 로 픽셀을 파이썬 객체로 만들면 픽셀당 수십 바이트가
        #    한꺼번에 잡힌다. 저장할 때 exif 를 빼면 같은 목적을 메모리 없이 이룬다.
        #  ⚠⚠ [라운드284] 재인코딩이 **고정 품질 92**였다 — 이미 낮은 품질로 압축된
        #    원본(카카오톡 재전송 사진 등)은 픽셀 디테일은 그대로인데 더 높은 품질로
        #    다시 압축하면 파일이 오히려 커진다. 실측: 7.2MB 원본이 재인코딩 후
        #    11.7MB(상한 40% 초과)로 저장됐고, 이 함수는 물론 save_upload() 어디도
        #    재인코딩 **뒤의** 크기를 상한과 다시 대조하지 않아 아무 로그·표식 없이
        #    '장당 8MB'라는 이 파일 자신의 안내·상한이 저장 단계에서 지켜지지
        #    않았다. 품질을 단계적으로 낮춰 가며 상한 안에 드는 첫 결과를 쓴다
        #    (_save_within_budget) — 대부분 화질 차이가 눈에 안 띄는 선에서 해결된다.
        #  ⚠⚠ [라운드298] exif=b"" 로 방향 정보를 지우기만 하고 그 방향을 픽셀에
        #    반영(회전)한 적이 없었다 — 세로로 찍은 사진(폰카메라 대다수, 특히
        #    가장 큰 비중인 아이폰 HEIC)이 화면·검수자·AI 판정 전부에게 옆으로
        #    누운 채로 영구히 저장됐다(실측: Orientation=6 JPEG 를 통과시키면
        #    100×60 그대로 나오고 방향 태그만 사라짐 — 회전이 반영된 60×100이
        #    아니다). 원본을 안 남기므로 되돌릴 방법도 없었다. 재인코딩 **전에**
        #    먼저 픽셀에 방향을 반영한다(exif_transpose 는 Orientation=1(정상)
        #    이면 그대로 돌려주므로 이미 바른 사진은 영향 없음).
        clean = ImageOps.exif_transpose(im)
        if ext in ("jpg", "jpeg"):
            if clean.mode not in ("RGB", "L"):
                clean = clean.convert("RGB")
            return _save_within_budget(clean, "JPEG", optimize=True, exif=b""), None
        elif ext == "png":
            #  PNG 는 무손실이라 품질 다이얼이 없다 — optimize 재인코딩으로도 상한을
            #  못 지키면 그대로 거부한다(원본을 그대로 쓰면 이 함수에 들어온 이유,
            #  즉 GPS 제거 자체가 무효가 된다 — "사진을 잃는 것보다 낫다"는 원칙은
            #  재인코딩 자체가 실패했을 때 얘기지, 위치정보가 남는 것과는 다르다).
            out = io.BytesIO()
            clean.save(out, format="PNG", optimize=True)
            out_bytes = out.getvalue()
            if len(out_bytes) > MAX_FILE_BYTES:
                raise UploadError(
                    f"위치정보 제거 후 크기가 상한({MAX_FILE_BYTES // (1024*1024)}MB)을 "
                    f"넘습니다. 사진을 더 작게 찍거나 JPG 로 저장해 다시 올려 주세요.")
            return out_bytes, None
        else:
            return _save_within_budget(clean, "WEBP"), None
    except UploadError:
        raise
    except Exception as e:
        return data, f"{type(e).__name__}: {e}"


_QUALITY_STEPS = (92, 80, 65, 50, 35)


def _save_within_budget(im, fmt, **extra):
    """MAX_FILE_BYTES 안에 들 때까지 JPEG/WEBP 품질을 낮춰 가며 저장한다.

    전부 시도해도 상한을 못 지키면 UploadError(호출부가 그대로 화면에 보여준다).
    """
    last = None
    for q in _QUALITY_STEPS:
        out = io.BytesIO()
        im.save(out, format=fmt, quality=q, **extra)
        last = out.getvalue()
        if len(last) <= MAX_FILE_BYTES:
            return last
    raise UploadError(
        f"위치정보 제거 후에도 크기가 상한({MAX_FILE_BYTES // (1024*1024)}MB)을 "
        f"넘습니다. 사진을 더 작게 찍거나 압축해 다시 올려 주세요.")


def _heic_to_jpeg(data, orig):
    """HEIC 바이트 → JPEG 바이트. 변환 못 하면 UploadError.

    ⚠ **픽셀 가드가 여기에도 있어야 한다.** 압축폭탄 방어를 _strip_exif 에만 넣었는데,
      HEIC 는 그보다 **먼저** 이 함수에서 통째로 디코딩된다 — 방어선 앞에서 터진다.
      아이폰 기본 형식이라 실제로 가장 큰 사진이 이 경로로 들어온다.
    """
    try:
        import io as _io
        import pillow_heif
        from PIL import Image
        pillow_heif.register_heif_opener()
        Image.MAX_IMAGE_PIXELS = MAX_PIXELS
        img = Image.open(_io.BytesIO(data))
        #  ★ **여기서도 픽셀을 먼저 잰다.** convert("RGB") 가 전체를 메모리에 펼친다 —
        #    _strip_exif 의 방어선은 이 뒤에 있어서, 폭탄은 그 앞에서 터진다.
        _w, _h = img.size
        if _w * _h > MAX_PIXELS:
            raise UploadError(
                f"'{orig}' 사진의 해상도가 너무 큽니다({_w}x{_h}). "
                f"카메라 설정을 낮추거나 크기를 줄여 다시 올려 주세요.")
        #  ⚠⚠ [라운드298] _strip_exif 의 exif_transpose 결함(아래 참조)을 처음
        #    발견했을 때 이 함수도 exif= 없는 img.save() 라 같은 결함이라고
        #    잠깐 판단했었다 — 그런데 실측(pillow_heif 1.4.0, 실제 등록된
        #    오프너로 orientation=1/3/6/8 네 값을 HEIC 라운드트립)해 보니
        #    Image.open() 시점에 **이미** 방향이 픽셀에 반영되고 태그는 1로
        #    정규화돼 있었다(6·8 은 가로세로가 실제로 바뀌어 나오고, 3 은
        #    유지 — 회전 규칙과 정확히 일치). 즉 이 경로는 pillow_heif 가
        #    이미 처리하고 있어 여기서 다시 exif_transpose 를 부르는 건
        #    아무 일도 안 하는 죽은 코드였다 — 실제로 결함이 있는 곳은
        #    아래에서 부르는 _strip_exif 뿐이다(일반 JPEG/PNG/WEBP 는 PIL 이
        #    자동회전을 안 하므로 진짜로 방향이 버려진다).
        img = img.convert("RGB")
        buf = _io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue(), "jpg", "image/jpeg"
    except ImportError:
        raise UploadError(
            f"'{orig}' 은(는) HEIC 형식입니다. 아이폰 [설정 > 카메라 > 포맷]을 "
            f"'높은 호환성'으로 바꾸거나 JPG 로 저장해 다시 올려 주세요.")
    except UploadError:
        #  ★ **우리가 던진 안내는 그대로 올려보낸다.** 아래 catch-all 이 먼저 잡으면
        #    '해상도가 너무 큽니다(8064x6048)' 가 'JPG 로 올려 주세요' 로 덮여,
        #    사용자는 무엇을 고쳐야 하는지 끝내 알 수 없다(오늘 넣은 픽셀 가드가
        #    바로 이 try 안에 있다).
        raise
    except Exception:
        raise UploadError(f"'{orig}' HEIC 사진을 변환하지 못했습니다. JPG 로 올려 주세요.")


def save_upload(file_storage, case_id):
    """업로드 파일 1건을 검증하고 저장한다.

    반환: dict(stored_name, rel_path, ext, mime, size, sha256, orig_name)
    """
    orig = (file_storage.filename or "사진")[:120]

    data = file_storage.read(MAX_FILE_BYTES + 1)
    if not data:
        raise UploadError(f"'{orig}' 파일이 비어 있습니다.")
    if len(data) > MAX_FILE_BYTES:
        raise UploadError(f"'{orig}' 파일이 너무 큽니다. (장당 {MAX_FILE_BYTES // (1024*1024)}MB 이하)")

    sniffed = sniff_image(data[:32])
    if not sniffed:
        raise UploadError(
            f"'{orig}' 은(는) 사진 파일이 아닙니다. JPG·PNG·WebP·HEIC 만 올릴 수 있습니다.")
    ext, mime = sniffed

    # 저장명은 서버가 만든다 — 원본 파일명은 경로 조작에 쓰일 수 있어 파일시스템에 반영하지 않는다
    # [PH-05] HEIC(아이폰 기본 형식)는 크롬·엣지·파이어폭스가 못 그린다.
    #  저장 시점에 JPEG 로 변환해 검수 화면에서 항상 보이게 한다.
    #  변환 라이브러리가 없으면 안내와 함께 거부한다(안 보이는 사진을 저장하지 않는다).
    if ext == "heic":
        data, ext, mime = _heic_to_jpeg(data, orig)

    # [법령·철칙] 위치정보(EXIF GPS) 제거
    #  협력사에게는 현장 **상세주소를 공개하지 않는다**(경쟁 우회·직거래 방지).
    #  화면에서는 시군구까지만 자르는데, 사진 EXIF 에 GPS 가 그대로 남아 있으면
    #  사진 한 장을 지도에 올리는 것만으로 그 노력이 전부 무효가 된다.
    #  촬영시각·기기정보도 같이 사라지지만, 우리 업무에는 업로드 시각·업로더가
    #  이미 기록되므로 잃는 것이 없다.
    #  ⚠ **실패를 삼키지 않는다.** 종전에는 바이트 하나만 돌려줘서,
    #    Pillow 가 없거나 그 파일을 못 열면 **GPS 가 박힌 원본이 그대로 저장**되는데
    #    아무 흔적이 없었다. 그 사진은 입찰 가능한 모든 협력사에게 열린다 —
    #    상세주소를 가려 온 노력이 사진 한 장으로 무효가 된다.
    data, _exif_err = _strip_exif(data, ext)
    #  ⚠⚠ [328라운드] _strip_exif() 의 조기 반환 3곳(해상도 과대·압축폭탄·재인코딩
    #    예외)은 그 자리에서 받은 data 를 상한 대조 없이 그대로 돌려준다 — 직접
    #    업로드된 jpg/png/webp는 259~263행에서 이미 원본이 8MB 이하로 걸러진
    #    뒤라 안전하지만, HEIC 는 여기 들어오는 data 가 _heic_to_jpeg() 가 방금
    #    새로 인코딩한 JPEG 라 한 번도 상한과 대조된 적이 없다(284라운드가
    #    고친 '재인코딩하면 커질 수 있다'는 것과 같은 위험이 이 세 갈래엔
    #    안 미쳤었다). 개별 갈래를 다 손보는 대신 이 한 지점에서 다시 잰다 —
    #    정상 경로(_save_within_budget·PNG 명시체크)는 이미 상한 안이라 그냥
    #    통과한다.
    if len(data) > MAX_FILE_BYTES:
        raise UploadError(f"'{orig}' 파일이 너무 큽니다. (장당 {MAX_FILE_BYTES // (1024*1024)}MB 이하)")

    stored = f"{secrets.token_hex(16)}.{ext}"
    rel = os.path.join(str(int(case_id)), stored)
    full = os.path.join(UPLOAD_ROOT, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)

    # 소유자만 읽을 수 있게 만든 뒤 채운다 (권한 공백 구간 제거)
    fd = os.open(full, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
    except Exception:
        #  ⚠ os.open(O_CREAT) 가 이 시점에 이미 파일을 만들어 둔다 — 쓰다가
        #    실패하면(디스크 꽉 참 등) 이 함수는 rel_path 를 못 돌려주므로
        #    호출부가 지울 방법이 없어 빈 파일이 그대로 남는다(실측 재현됨).
        #  ⚠⚠ os.fdopen 자체가 실패하면 fd 가 파일객체로 감싸이기 전이라 열린
        #    채 남는다 — Windows 는 핸들이 열려 있는 파일을 못 지운다(자물쇠).
        #    지우기 전에 반드시 닫는다(with 블록 안에서 실패했다면 이미 닫혀
        #    있어 이 close 는 그냥 실패하고 넘어간다 — 그래도 안전하다).
        try:
            os.close(fd)
        except OSError:
            pass
        try:
            os.remove(full)
        except OSError:
            pass
        raise

    return {
        "stored_name": stored,
        "rel_path": rel.replace("\\", "/"),
        "ext": ext,
        "mime": mime,
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "orig_name": orig,
        #  ★ 위치정보를 **못 지웠으면 그 사실을 함께 돌려준다.** None 이면 정상.
        #    호출부가 이 값을 보고 사진에 표식을 남기고 운영팀에 알린다.
        "exif_error": _exif_err,
    }


def abs_path(rel_path):
    """DB에 저장된 상대경로 → 실제 경로. 업로드 루트 밖으로 나가지 못하게 막는다."""
    full = os.path.abspath(os.path.join(UPLOAD_ROOT, rel_path))
    root = os.path.abspath(UPLOAD_ROOT)
    if not full.startswith(root + os.sep):
        raise UploadError("잘못된 파일 경로입니다.")
    return full


# ══════════════════════════════════════════════════════════════
#  AI 자동 분류
#
#  실제 모델 연동은 **어댑터로 분리**한다. 지금은 API 키가 없으므로
#  자동 분류가 동작하지 않으며, 그 사실을 숨기지 않고 '미분류'로 남긴다.
#  (예전 화면처럼 신뢰도 97% 같은 값을 지어내면 운영자가 검수를 건너뛰게 된다)
#
#  키를 넣으면(.env 의 BOKGUON_GEMINI_KEY) 곧바로 동작한다.
#  구글 AI 스튜디오 무료 등급으로 분류·영수증 판별·금액 판독을 한 모델로 처리할 수 있다.
# ══════════════════════════════════════════════════════════════
GEMINI_KEY = os.environ.get("BOKGUON_GEMINI_KEY", "")
GEMINI_MODEL = os.environ.get("BOKGUON_GEMINI_MODEL", "gemini-2.0-flash")

CLASSIFY_PROMPT = """이 사진은 교통사고로 파손된 시설물(가드레일·담장·유리·차단기 등)의 복구 공사 기록입니다.
아래 다섯 가지 중 하나로만 분류하고 JSON 으로만 답하세요.

- 착공전: 파손된 상태 그대로. 복구 작업이 시작되지 않음
- 시공중: 철거·설치·양생 등 작업이 진행 중. 장비나 작업자가 보임
- 완료: 복구가 끝나 정상 상태로 돌아옴
- 영수증: 자재 구매 영수증·거래명세서·세금계산서 등 서류
- 기타: 위 어디에도 해당하지 않음

{"kind":"착공전|시공중|완료|영수증|기타","confidence":0~100,"reason":"20자 이내"}"""


def is_enabled():
    return bool(GEMINI_KEY)


def classify(abs_file_path, mime):
    """사진 1장을 분류한다.

    반환: (kind, confidence, model, note)
      · 키가 없거나 호출에 실패하면 (None, 0, ...) 을 돌려주고,
        호출부는 '미분류' 상태로 두어 **사람이 반드시 확인**하게 한다.
    """
    if not GEMINI_KEY:
        return None, 0, "", "AI 미연동 — 담당자 분류 필요"

    import base64
    import json
    import urllib.request
    import urllib.error

    try:
        with open(abs_file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}")
        payload = {
            "contents": [{"parts": [
                {"text": CLASSIFY_PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        # 타임아웃을 반드시 둔다 — 외부 호출이 업로드 응답을 무한정 붙잡으면 안 된다
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode())

        text = body["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
        kind = out.get("kind")
        if kind not in KINDS:
            return None, 0, GEMINI_MODEL, f"분류 결과 해석 실패({kind})"
        conf = max(0, min(100, int(out.get("confidence") or 0)))
        return kind, conf, GEMINI_MODEL, (out.get("reason") or "")[:40]

    except urllib.error.HTTPError as e:
        return None, 0, GEMINI_MODEL, f"AI 호출 실패 HTTP {e.code}"
    except Exception as e:
        return None, 0, GEMINI_MODEL, f"AI 호출 실패: {type(e).__name__}"


# ══════════════════════════════════════════════════════════════
#  AI 파손 정도 분석 (사건 등록 사진 → 파손 리포트)
#
#  보험사가 등록 때 올린 피해 현장 사진으로 파손 정도를 개략 분석한다.
#  ⚠ 이건 **참고용 개략치**다. 실측·실견적은 낙찰 시행사가 수행한다(가견적 원칙).
#     키가 없으면 지어내지 않고 '미연동'으로 정직하게 남긴다.
# ══════════════════════════════════════════════════════════════
DAMAGE_PROMPT = """당신은 도로·시설물 복구 견적 보조입니다. 이 사진은 교통사고 등으로 파손된
기타 피해물(가드레일·담장·유리·차단기·방음벽·누수 등)의 현장 사진입니다.
파손 정도를 아래 셋 중 하나로만 판정하고, 복구 관점의 핵심 소견을 한국어로 간단히 쓰세요.
과장하지 말고 보이는 것만 판단하세요. JSON 으로만 답하세요.

- 경미: 국부 손상·교체 범위 작음
- 보통: 부재 여러 개 손상·표준적 복구 범위
- 중대: 광범위·구조적 손상·대규모 복구 필요

{"severity":"경미|보통|중대","summary":"복구 소견 40자 이내","items":"주요 파손 항목 30자 이내"}"""


def analyze_damage(abs_file_path, mime):
    """피해 사진 1장의 파손 정도를 분석한다.

    반환: (severity, summary, model)
      · 키가 없거나 실패하면 severity=None 을 돌려주고, 호출부는 '미연동'으로 남긴다.
    """
    if not GEMINI_KEY:
        return None, "AI 미연동 — 담당자가 사진으로 파손 정도를 확인해 주세요.", ""

    import base64
    import json
    import urllib.request
    import urllib.error
    try:
        with open(abs_file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}")
        payload = {
            "contents": [{"parts": [
                {"text": DAMAGE_PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}},
            ]}],
            "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
        }
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode())
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        out = json.loads(text)
        sev = out.get("severity")
        if sev not in ("경미", "보통", "중대"):
            return None, f"분석 결과 해석 실패({sev})", GEMINI_MODEL
        summary = (out.get("summary") or "")[:60]
        items = (out.get("items") or "")[:40]
        return sev, (f"{summary} (주요 항목: {items})" if items else summary), GEMINI_MODEL
    except urllib.error.HTTPError as e:
        return None, f"AI 분석 실패 HTTP {e.code}", GEMINI_MODEL
    except Exception as e:
        return None, f"AI 분석 실패: {type(e).__name__}", GEMINI_MODEL
