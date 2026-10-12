# -*- coding: utf-8 -*-
"""스캔 298라운드 회귀 — photo_ai.py EXIF 방향유실 결함 1건[사람이 보는 사진] +
   app.py 외부 보험사 API 뷰의 담당자확인 미반영 결함 1건[심각], photo_ai.py
   (AI 파손사진 분석 모듈)를 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 —
   동시성(round71·72 방어 재확인, 이 모듈 자체엔 공유 상태가 없어 클린)·AI호출
   실패의 조용한 오판(클린)·이미지 신뢰경계(클린)·데모격리(해당없음)는 실측
   결과 전부 클린. 보조조사한 totp.py 도 클린.

   ⚠ 조사 에이전트는 _heic_to_jpeg() 도 같은 결함(exif= 없이 저장해 방향유실)
     이라고 보고했으나, 독립검증 중 이 부분만 다시 실측(pillow_heif 1.4.0의
     실제 등록 오프너로 HEIC 라운드트립, orientation 1/3/6/8 네 값)해 보니
     Image.open() 시점에 이미 픽셀에 방향이 반영되고 태그가 1로 정규화돼
     있었다(90°/270°는 실제로 가로세로가 바뀌어 나오고 180°는 유지 — 회전
     규칙과 정확히 일치) — pillow_heif 가 이미 처리하는 경로였다. 에이전트의
     재현은 이 지점만 실제 HEIC 디코드가 아니라 JPEG 를 대신 쓴 유사 재현이라
     이 특이 동작을 못 봤다(다른 보고 지점은 전부 실제 재현이었다). 그래서
     이 라운드는 _heic_to_jpeg() 는 그대로 두고, 실제로 결함이 있는
     _strip_exif() 와 _v1_case_view() 두 곳만 고쳤다 — "에이전트의 핵심
     주장뿐 아니라 재현 방법 자체도 실제 코드경로를 타는지 검증해야 한다"는
     290라운드 교훈이 이번엔 "다른 형식으로 대신 재현한 단계"에서 재발한
     사례로 기록.

   ①[사람이 보는 사진] _strip_exif() 가 EXIF Orientation 태그를 픽셀에
      반영(회전)하지 않고 그냥 지웠다 — 세로로 찍은 사진(폰카메라 대다수)이
      화면·검수자·AI 판정 전부에게 옆으로 누운 채 영구히 저장됐다(원본을
      안 남기므로 되돌릴 방법도 없음). 재인코딩 전에 먼저 ImageOps.
      exif_transpose() 로 픽셀에 방향을 반영하도록 수정.
   ②[심각] 외부 보험사 API(/api/v1/cases, /api/v1/cases/<case_no>)가
      담당자가 콘솔에서 확정한 파손 정도(human_severity)를 전혀 반영하지
      않고 AI 추정치(ai_severity)만 내보냈다 — 같은 파일 안의 두 정상 판정
      함수(_est_basis·_record_outcome)는 전부 담당자 확인값을 우선하는데
      (사람이 정한 값이 사진 판정보다 우선), 외부 API 뷰만 이 우선순위 없이
      원본 AI값을 그대로 냈다(실측: 담당자가 '중대'로 확정한 뒤에도 이 뷰는
      여전히 옛 '경미'를 반환). 세 곳이 각자 우선순위를 판단하다 하나가
      빠지는 사고(라운드54·59·93·131·297과 같은 족보)를 다시 반복하지
      않도록 그 로직을 _case_severity() 공유함수로 뽑아 세 곳 모두 이걸
      쓰게 통일. 기존 ai_severity·ai_report 필드는 값·뜻을 그대로 두고
      (문서화 안 된 필드라 기존 연동에 어떤 영향이 갈지 알 수 없다 — 안전
      하게 새 필드만 추가), human_severity·severity·severity_src 세 필드를
      새로 더했다.

      python test_scan_round298_fixes.py
"""
import io
import os
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
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 298라운드 회귀 — photo_ai.py 방향유실 + 외부API 담당자확인 미반영")
print("=" * 72)


def _section(src, start_marker, end_marker):
    i0 = src.index(start_marker)
    i1 = src.index(end_marker, i0 + len(start_marker))
    return src[i0:i1]


STRIP_EXIF = _section(PHOTO_SRC, "\ndef _strip_exif(", "\ndef _save_within_budget(")
HEIC_FN = _section(PHOTO_SRC, "\ndef _heic_to_jpeg(", "\ndef save_upload(")

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk("from PIL import Image, ImageOps" in STRIP_EXIF,
    "★★★ _strip_exif 가 ImageOps 를 들여온다")
chk("ImageOps.exif_transpose(im)" in STRIP_EXIF,
    "★★★ _strip_exif 가 재인코딩 전에 방향을 픽셀에 반영한다")
_has_transpose_call = "clean = ImageOps.exif_transpose(im)" in STRIP_EXIF
_has_jpeg_branch = 'if ext in ("jpg", "jpeg"):' in STRIP_EXIF
if _has_transpose_call and _has_jpeg_branch:
    chk(STRIP_EXIF.index("clean = ImageOps.exif_transpose(im)")
        < STRIP_EXIF.index('if ext in ("jpg", "jpeg"):'),
        "★★ 방향 반영이 JPEG/PNG/WEBP 분기보다 먼저 실행된다(세 형식 모두 적용)")
else:
    chk(False, "★★ 방향 반영이 JPEG/PNG/WEBP 분기보다 먼저 실행된다(세 형식 모두 적용)",
        "필요한 조각을 못 찾음")

#  ⚠ _heic_to_jpeg 는 의도적으로 그대로 둔다(독립검증 결과 결함이 아니었음) —
#    ImageOps 를 여기서 새로 들여오면 오히려 이번 판단을 뒤집는 회귀다.
chk("from PIL import Image\n" in HEIC_FN and "ImageOps" not in HEIC_FN,
    "★ _heic_to_jpeg 는 그대로다(pillow_heif 가 이미 방향을 반영 — 의도적 무변경)")

chk(APP_SRC.count("def _case_severity(c):") == 1,
    "★★★ _case_severity() 공유함수가 정확히 한 번 정의돼 있다")
EST_BASIS = _section(APP_SRC, "\ndef _est_basis(", "\n\n\ndef ")
chk("severity, sev_src = _case_severity(c)" in EST_BASIS,
    "★★ _est_basis 가 공유함수를 쓴다(회귀 없음)")
RECORD_OUTCOME = _section(APP_SRC, "\ndef _record_outcome(", "\n\n\ndef ")
chk("sev, src = _case_severity(c)" in RECORD_OUTCOME,
    "★★ _record_outcome 이 공유함수를 쓴다(회귀 없음)")
V1_VIEW = _section(APP_SRC, "\ndef _v1_case_view(", "\n\n\ndef ")
chk("_sev, _sev_src = _case_severity(c)" in V1_VIEW,
    "★★★ _v1_case_view 가 공유함수를 쓴다(고치기 전엔 아예 안 씀)")
chk('"human_severity": c.get("human_severity")' in V1_VIEW,
    "★★ _v1_case_view 가 human_severity 원본도 새로 내보낸다")
chk('"severity": _sev, "severity_src": _sev_src' in V1_VIEW,
    "★★★ _v1_case_view 가 최종 판정(severity/severity_src)을 새로 내보낸다")
chk('"ai_severity": c.get("ai_severity"), "ai_report": c.get("ai_report")' in V1_VIEW,
    "★ ai_severity·ai_report 원본 필드는 그대로 남아있다(기존 연동 호환)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _strip_exif 가 실제로 방향을 반영하는가(진짜 PIL 이미지)")
# ──────────────────────────────────────────────────────────────
try:
    from PIL import Image
    sys.path.insert(0, HERE)
    import photo_ai as PH

    def make_jpeg_with_orientation(w, h, orientation):
        im = Image.new("RGB", (w, h), (200, 50, 50))
        exif = im.getexif()
        exif[0x0112] = orientation      # Orientation 태그
        buf = io.BytesIO()
        im.save(buf, format="JPEG", exif=exif)
        return buf.getvalue()

    # 전제 확인 — PIL 은 일반 JPEG 를 열 때 자동회전을 하지 않는다(문제의 전제)
    raw = make_jpeg_with_orientation(100, 60, 6)
    _im0 = Image.open(io.BytesIO(raw))
    chk(_im0.size == (100, 60) and _im0.getexif().get(0x0112) == 6,
        "STEP 일반 JPEG 는 Image.open() 만으로는 자동회전이 안 된다(전제 확인)",
        (_im0.size, _im0.getexif().get(0x0112)))

    out_bytes, err = PH._strip_exif(raw, "jpg")
    chk(err is None, "STEP _strip_exif 가 정상 처리로 보고한다(오류 없음)", err)
    im_out = Image.open(io.BytesIO(out_bytes))
    chk(im_out.size == (60, 100),
        "★★★ Orientation=6(90도 보정 필요) 사진이 실제로 회전되어 저장된다"
        "(고치기 전엔 100x60 그대로 — 옆으로 누운 채 저장됐다)", im_out.size)
    chk(im_out.getexif().get(0x0112) in (None, 1),
        "★ 회전을 이미 반영했으므로 방향 태그는 안 남거나 1(정상)이다"
        "(다음에 또 회전시키는 이중적용 방지)", im_out.getexif().get(0x0112))

    # 180도(가로세로 안 바뀜) · 정상(1, 무변화)도 함께 확인 — 과잉교정 아님
    raw180 = make_jpeg_with_orientation(100, 60, 3)
    out180, _ = PH._strip_exif(raw180, "jpg")
    chk(Image.open(io.BytesIO(out180)).size == (100, 60),
        "★ Orientation=3(180도, 가로세로 안 바뀜)도 크기가 정확히 유지된다", None)

    raw_normal = make_jpeg_with_orientation(100, 60, 1)
    out_normal, _ = PH._strip_exif(raw_normal, "jpg")
    chk(Image.open(io.BytesIO(out_normal)).size == (100, 60),
        "★ 이미 정상 방향(1)인 사진은 그대로 100x60 — 과잉교정 없음(회귀 없음)", None)

    # PNG 도 같은 수정 경로를 타는지 확인 — exif_transpose 를 세 형식 모두 앞단에서 공유
    pim = Image.new("RGB", (100, 60), (10, 20, 30))
    pexif = pim.getexif()
    pexif[0x0112] = 6
    pbuf = io.BytesIO()
    pim.save(pbuf, format="PNG")   # PNG 저장 자체는 exif 파라미터가 없어 별도 확인
    # PNG 는 PIL 저장 시 exif 를 함께 못 넣으므로, im.info 경유로 직접 얹어 재현한다
    pim2 = Image.open(pbuf)
    pim2.info["exif"] = pexif.tobytes()
    pbuf2 = io.BytesIO()
    pim2.save(pbuf2, format="PNG", exif=pexif.tobytes())
    png_out, _ = PH._strip_exif(pbuf2.getvalue(), "png")
    chk(Image.open(io.BytesIO(png_out)).size == (60, 100),
        "★★ PNG 도 같은 수정으로 방향이 반영된다(JPEG 만이 아니라 세 형식 공통 수정)",
        Image.open(io.BytesIO(png_out)).size)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드298 [2] _strip_exif 실측", f"{type(e).__name__} {e}")

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — _v1_case_view 가 담당자확인을 실제로 반영하는가(격리 DB, 실제 함수)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round298_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ.setdefault("BOKGUON_GEMINI_KEY", "")

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name,status) VALUES('검증보험사298','활성')").lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer,insurer_id,category,region,"
        "                  ai_severity,ai_report,created_at) "
        "VALUES('298V-0000','접수',?,?,?,'서울','경미','[AI 판정 경미] 초기추정',"
        "        datetime('now','+9 hours'))",
        ("검증보험사298", iid, "누수·배관·설비")).lastrowid
    conn.commit()

    c_before = A.one(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)))
    v1_before = A._v1_case_view(conn, c_before)
    est_before = A._est_basis(conn, cid)
    chk(v1_before["ai_severity"] == "경미" and v1_before["severity"] == "경미"
        and v1_before["severity_src"] == "사진 판정",
        "STEP 담당자 확인 전엔 외부API·내부판정 둘 다 AI값('경미')으로 일치한다"
        "(전제 확인)", (v1_before, est_before))

    # 실제 라우트가 하는 것과 정확히 같은 SQL — 담당자가 콘솔에서 파손정도를 확정
    conn.execute(
        "UPDATE cases SET human_severity=?, human_severity_by=?, human_severity_at=? "
        "WHERE id=?", ("중대", "보험사", DB.now(), cid))
    conn.commit()

    c_after = A.one(conn.execute("SELECT * FROM cases WHERE id=?", (cid,)))
    v1_after = A._v1_case_view(conn, c_after)
    est_after = A._est_basis(conn, cid)

    chk(est_after["severity"] == "중대" and est_after["severity_src"] == "담당자 확인",
        "STEP 내부 가견적 판정(_est_basis)은 원래도 담당자 확인을 우선했다"
        "(전제 확인, 회귀 없음)", est_after)
    chk(v1_after["ai_severity"] == "경미" and v1_after["ai_report"] == "[AI 판정 경미] 초기추정",
        "★ 외부API의 ai_severity·ai_report 원본 필드는 값이 안 바뀐다(기존 연동 호환)",
        v1_after)
    chk(v1_after.get("human_severity") == "중대",
        "★★ 외부API가 담당자 확인값(human_severity)을 이제 함께 내려준다"
        "(고치기 전엔 이 필드 자체가 응답에 없었다)", v1_after.get("human_severity"))
    chk(v1_after.get("severity") == "중대" and v1_after.get("severity_src") == "담당자 확인",
        "★★★ 외부API의 최종 판정(severity)이 담당자 확인값으로 바뀐다"
        "(고치기 전엔 담당자가 '중대'로 확정해도 여전히 옛 '경미'를 냈다)",
        (v1_after.get("severity"), v1_after.get("severity_src")))

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드298 [3] _v1_case_view 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
