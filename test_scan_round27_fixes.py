# -*- coding: utf-8 -*-
"""스캔 27라운드 회귀 — 조사 에이전트가 찾은 하자 완료·반려 상충.

  api_defect_update 는 '같은 상태로 재제출'만 막았다. 담당자 둘이 같은 하자를
  두고 완료/반려를 거의 동시에 누르면(혹은 한쪽이 이미 처리된 걸 모르고 반대
  결정을 누르면) 뒤엣것이 조용히 앞엣것을 덮어쓴다 — DEFECT_CLOSED_STATES
  (app.py 의 '닫힌 하자'를 정하는 유일한 자리)가 완료·반려를 둘 다 종결로
  선언하는데, 이 라우트만 종결 후 재결정을 막지 않는 예외였다. 계약·정산·
  낙찰 등 다른 모든 결정 관문은 이미 종결 후 재결정을 막는다.

  ⚠ 화면(admin.js)에는 '완료 취소'(완료→확인중) 되돌리기가 **의도된 기능**으로
    이미 있다 — 종결이면 무조건 막는 식으로 고치면 이 기능이 조용히 깨진다.
    그래서 이번 수정은 좁게, **완료↔반려 사이**(양쪽 다 종결상태)만 막는다.
    아래 [2]가 바로 이 좁힘이 실제로 그렇게 되어 있는지를 검사한다.

  ⚠ 이 함수는 Flask 세션·DB 원장·notify()가 얽혀 있어(형제 파일
    test_feature_defect_reject_notify.py 가 이미 같은 이유로 소스 검증을
    택했다) 가짜 세션을 만드는 대신 실제 소스 문자열을 앵커로 정확히 잘라
    검사한다.

  ② 손상·중간에 끊긴 사진이 "성공"으로 저장됨 — 실측(2026-08-20): JPEG 를
     60%에서 자른 뒤 photo_ai._strip_exif() 에 넣으면 Pillow 디코딩 예외
     (`im.load()`)까지 catch-all 이 삼켜 **원본(깨진) 바이트를 그대로 돌려주고**
     save_upload() 는 그걸 검증 없이 저장해 `{"ok": true}` 를 낸다. 저장된
     파일을 다시 열어도 똑같이 깨져 있다. 유일한 신호는 운영자 전용 알림인데
     문구가 "위치정보를 지우지 못했습니다"라 실제 원인(파일 손상)과 다르다.
     HEIC 변환(_heic_to_jpeg)은 이미 디코딩 실패를 UploadError 로 거부하는데
     JPEG·PNG·WEBP 만 예외였다 — 디코딩(Image.open+im.load)과 재인코딩(exif
     제거용 save)을 분리해, **디코딩 실패만** 거부하고 재인코딩 실패는 기존대로
     원본을 그대로 쓰는(사진을 잃지 않는) 설계를 그대로 유지한다.
     현장 기사가 실외·약한 신호에서 사진을 올린다는 게 이 세션의 전제라
     다음 주 실측이 이 결함의 첫 노출 기회다.

  ③ 로그인 잠금(5회 실패/10분, (아이디,IP) 단위) 수동 해제 수단이 없었다 —
     실사용자가 막히면 운영자가 즉시 해줄 수 있는 조치가 "10분 기다리세요"뿐
     이었다. /api/login-attempts/unlock 를 추가해 아이디 기준으로 실패
     기록만 지운다(성공 기록·다른 아이디는 안 건드린다).

     ⚠⚠ 이 수정의 **첫 시도가 기존 11라운드 테스트(압축폭탄)를 깼다** — 실측:
       9000×9000 폭탄 PNG 는 MAX_PIXELS 의 2배(80,000,000픽셀)를 넘어 수동
       검사(`_w*_h>MAX_PIXELS`)에 닿기도 전에 `Image.open()` 자체가
       `PIL.Image.DecompressionBombError` 를 던진다 — 이게 새 catch-all 에
       걸려 '손상된 파일'로 오분류되며 원래는 비치명적(원본 저장+사유만 기록)
       이던 폭탄 처리가 강제 거부로 바뀌었다. `DecompressionBombError` 를
       먼저 따로 잡아 옛 비치명적 경로를 그대로 살렸다 — 아래 [4]가 이 구분을
       검사한다(11라운드 테스트에만 기대지 않는다 — 그 파일이 나중에
       바뀌거나 빠지면 이 회귀를 놓친다).

      python test_scan_round27_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def slice_by_anchor(src, start_marker, end_marker):
    i = src.find(start_marker)
    j = src.find(end_marker, i)
    if i < 0 or j < 0 or j <= i:
        return ""
    return src[i:j]


APP = read("app.py")
ADM = read("static/admin.js")

print("═" * 72)
print("  스캔 27라운드 회귀 — 하자 완료·반려 상충 방지")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 화면의 '완료 취소' 되돌리기는 그대로 살아 있는가(회귀 방지)")
# ──────────────────────────────────────────────────────────────
chk("완료를 취소하고" in ADM, "★★ 화면에 '완료 취소'(완료→확인중) 되돌리기 문구가 있다",
    "이게 사라지면 이번 수정이 의도된 기능까지 막았다는 뜻이다")
chk('data-arg2="확인중"' in ADM, "★ 되돌리기 버튼의 목표 상태가 '확인중'이다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 서버 — DEFECT_NEXT 전이표부터 확인한다(가드가 참조하는 근거)")
# ──────────────────────────────────────────────────────────────
#  ⚠ 라운드55: DEFECT_CLOSED_STATES(종결상태 집합)만으로는 "접수→완료" 한 번의
#    건너뜀을 못 막았다 — 접수는 종결이 아니므로 옛 조건("현재도 종결 AND
#    목표도 종결")에 안 걸린다. 실측: 지급 관문(DEFECT_OPEN)이 확인중·재시공배정을
#    거치지 않고 흔적 없이 열리고 닫혔다. 이제 상태쌍 특례가 아니라 "이 상태에서
#    갈 수 있는 다음 상태들"을 표(DEFECT_NEXT) 하나로 정의한다.
chk('DEFECT_CLOSED_STATES = ("완료", "반려")' in APP,
    "종결상태 정의를 찾았다(코드 전체에서 여기 한 곳뿐이어야 한다)")
chk("DEFECT_NEXT = {" in APP,
    "★★ 전이표(DEFECT_NEXT)가 생겼다 — 상태쌍 특례가 아니라 표 하나로 정한다")

_fn = slice_by_anchor(APP, "def api_defect_update(did):", "\ndef _defect_visible_to")
chk(bool(_fn), "api_defect_update 함수를 찾았다")

_i_same = _fn.find('if st and st == row["status"]:')
_i_end = _fn.find("sets, vals = [], []")
_guard = _fn[_i_same:_i_end] if 0 <= _i_same < _i_end else ""
chk(bool(_guard.strip()), "'같은 상태 재제출' 부터 본문 시작 전까지 가드 구간을 찾았다")

chk('DEFECT_NEXT.get(row["status"]' in _guard,
    "★★ 가드가 DEFECT_NEXT 를 그대로 재사용한다(따로 또 안 적는다)",
    "따로 전이 규칙을 또 적으면 언젠가 갈린다 — 실측: 지급 게이트가 이 사고를 겪었다(11334줄 주석)")

#  ★★★ 핵심 — 허용된 다음 상태 목록에 없으면 막는다는 조건이 실제로 있는가.
#  이게 없으면(상태쌍만 검사) 완료→확인중 되돌리기까지 막거나, 접수→완료 같은
#  건너뛰기를 못 막는다.
i_full_guard = _fn.find('if st and st not in DEFECT_NEXT.get(row["status"], ()):')
chk(i_full_guard >= 0,
    "★★★ '전이표에 없으면 막는다' 정확한 조건문을 찾았다",
    "이 조건문이 없으면 완료→확인중처럼 종결을 여는 되돌리기까지 막혔거나(과함), "
    "혹은 접수→완료 건너뛰기를 못 막았거나(부족) 둘 중 하나다")

_block = _fn[i_full_guard:i_full_guard + 400] if i_full_guard >= 0 else ""
chk("409" in _block, "★★ 충돌을 409로 답한다(다른 결정 관문들과 같은 신호)")
chk("DEFECT_BAD_TRANSITION" in _block, "★ 어떤 종류의 거부인지 코드로 구분된다")

# ══════════════════════════════════════════════════════════════
print("\n[3] 진리표 — 실제 조건식 문자열을 그대로 떼어 실행한다(재구현 아님)")
# ──────────────────────────────────────────────────────────────
#  ⚠ 손으로 조건을 다시 적으면 '내가 이해한 로직'만 검증하게 된다 — 위에서 찾은
#    i_full_guard 지점의 실제 소스 문자열을 잘라 그대로 eval 한다.
_cond_src = _fn[i_full_guard:_fn.find(":", i_full_guard)] if i_full_guard >= 0 else ""
_cond_src = _cond_src[len("if "):] if _cond_src.startswith("if ") else _cond_src
chk(bool(_cond_src), "가드 조건식 원문을 잘라냈다", _cond_src)

DEFECT_NEXT = {   # app.py 의 실제 값과 동일 — [2]에서 그 정의도 검사했다
    "접수":       ("확인중", "반려"),
    "확인중":     ("재시공배정", "완료", "반려"),
    "재시공배정": ("확인중", "완료", "반려"),
    "완료":       ("확인중",),
    "반려":       (),
}
cases = [
    ("완료", "반려", True),          # ★ 완료↔반려 상충(라운드27 원래 취지)
    ("반려", "완료", True),          # ★ 반대 방향도 상충
    ("완료", "확인중", False),        # ★★★ 화면의 '완료 취소' — 반드시 안 막혀야 한다
    ("완료", "재시공배정", True),     # ★★ 라운드55: 완료에서 되돌릴 곳은 확인중뿐이다
    ("접수", "완료", True),          # ★★★ 라운드55: 확인중·재시공배정을 건너뛰는
                                     #     지급관문 우회 — 반드시 막혀야 한다(핵심 결함)
    ("확인중", "반려", False),
    ("접수", "확인중", False),        # ★ 정상 전진은 안 막힌다(과잉차단 아님)
    ("확인중", "완료", False),
    ("재시공배정", "완료", False),
    ("반려", "확인중", True),        # ★ 라운드55: 반려는 되살리지 않는다
]
if _cond_src:
    all_ok = True
    for cur, new, expect_blocked in cases:
        row = {"status": cur}
        st = new
        got = bool(eval(_cond_src))                        # noqa: S307 — 우리 소스 조각이다
        ok = got == expect_blocked
        all_ok &= ok
        chk(ok, f"★ {cur} → {new} : 막혀야 함={expect_blocked}", f"실제 막힘={got}")

# ══════════════════════════════════════════════════════════════
print("\n[4] 사진 업로드 — 손상·중간에 끊긴 파일을 거부한다(원본 저장 안 함)")
# ──────────────────────────────────────────────────────────────
PHA = read("photo_ai.py")
_i_se = PHA.find("def _strip_exif(data, ext):")
_j_se = PHA.find("\ndef _heic_to_jpeg")
_se_src = PHA[_i_se:_j_se] if 0 <= _i_se < _j_se else ""
chk(bool(_se_src), "_strip_exif 함수를 찾았다")
chk("im.load()" in _se_src and "raise UploadError" in _se_src,
    "★★★ 디코딩(im.load) 실패를 이제 거부한다(HEIC 경로와 대칭)")
#  ⚠ 디코딩과 재인코딩을 분리했는지 — raise 가 im.load() 보다 뒤(같은 try 안)
#    있고, 그 뒤에 **별도의** try 가 있어 재인코딩 실패는 여전히 원본을 살린다.
_i_load = _se_src.find("im.load()")
_i_raise = _se_src.find("raise UploadError")
_i_2nd_try = _se_src.find("\n    try:", _i_raise)
chk(0 < _i_load < _i_raise < _i_2nd_try,
    "★★ 디코딩 실패만 거부하고, 재인코딩(exif 제거) 실패는 별도 블록이라 안 건드렸다",
    "순서가 어긋나면 재인코딩 실패까지 거부해 '사진을 잃는 것보다 낫다'는 기존 설계가 깨진다")
_after_2nd_try = _se_src[_i_2nd_try:] if _i_2nd_try >= 0 else ""
chk('return data, f"{type(e).__name__}: {e}"' in _after_2nd_try,
    "★ 재인코딩 실패는 여전히 원본 바이트를 그대로 돌려준다(회귀 방지 — 사진을 잃지 않는다)")

#  ⚠⚠ 압축폭탄 회귀 — 첫 시도가 11라운드 테스트를 깬 바로 그 자리.
#    DecompressionBombError 는 catch-all(raise UploadError) **앞에서** 먼저
#    잡혀야 한다 — 순서가 바뀌면 폭탄이 '손상 파일'로 오분류되어 강제 거부된다
#    (옛 동작은 비치명적: 원본 저장 + 사유만 기록).
_i_bomb = _se_src.find("except Image.DecompressionBombError")
chk(0 <= _i_bomb < _i_raise,
    "★★★ DecompressionBombError 를 catch-all 보다 먼저, 별도로 잡는다",
    "이게 없으면(또는 순서가 뒤면) 폭탄이 손상 파일로 오분류돼 강제 거부된다 — 실측: 첫 시도가 이렇게 11라운드 테스트를 깼다")
_bomb_block = _se_src[_i_bomb:_i_raise] if 0 <= _i_bomb < _i_raise else ""
chk("return data," in _bomb_block,
    "★★ 폭탄은 여전히 비치명적(raise 아님, data 를 그대로 돌려준다) — 옛 동작 유지")

#  ── 실제로 실행해 본다 — Pillow 로 진짜 이미지를 만들고 진짜로 자른다 ──────
_tmpdir4 = tempfile.mkdtemp(prefix="upload_")
os.environ["BOKGUON_UPLOAD_DIR"] = _tmpdir4
try:
    from PIL import Image
    sys.path.insert(0, HERE)
    import importlib
    import photo_ai as PH
    importlib.reload(PH)   # BOKGUON_UPLOAD_DIR 를 지금 값으로 다시 읽게 한다

    buf = io.BytesIO()
    Image.new("RGB", (60, 60), (200, 50, 50)).save(buf, format="JPEG")
    good = buf.getvalue()
    cut = good[:int(len(good) * 0.6)]   # 업로드 중간에 끊긴 것과 같은 모양

    data, err = PH._strip_exif(good, "jpg")
    chk(err is None and len(data) > 0, "★ 정상 이미지는 그대로 통과한다(회귀 방지)", err)

    try:
        PH._strip_exif(cut, "jpg")
        chk(False, "★★★ 손상 이미지가 거부돼야 하는데 통과했다 — 결함이 재현되지 않음/안 고쳐짐")
    except PH.UploadError as e:
        chk(True, "★★★ 손상 이미지를 실제로 거부한다(UploadError)", str(e))

    #  ★★★ 11라운드 테스트와 같은 폭탄(9000×9000) — 손상과 달리 **비치명적**이어야
    #    한다. 이게 예외를 던지면 첫 시도의 회귀가 되살아난 것이다.
    bomb_buf = io.BytesIO()
    Image.new("RGB", (9000, 9000), (7, 7, 7)).save(bomb_buf, format="PNG", optimize=True)
    try:
        b_data, b_err = PH._strip_exif(bomb_buf.getvalue(), "png")
        chk(bool(b_err) and b_data == bomb_buf.getvalue(),
            "★★★ 압축폭탄은 거부(예외)되지 않고 원본을 그대로 돌려준다(11라운드와 같은 계약)",
            f"err={b_err!r}")
    except PH.UploadError as e:
        chk(False, "★★★ 압축폭탄이 '손상 파일'로 오분류되어 거부됨 — 이게 바로 첫 시도의 회귀다",
            str(e))

    #  save_upload() 전체 경로 — 거부되면 디스크에 아무 파일도 안 남아야 한다
    class _FakeFS:
        def __init__(self, b, name):
            self._b = b; self.filename = name
        def read(self, n=-1):
            return self._b[:n] if n and n > 0 else self._b

    before_files = sum(len(fs) for _, _, fs in os.walk(_tmpdir4))
    try:
        PH.save_upload(_FakeFS(cut, "test.jpg"), 999999)
        chk(False, "★★★ save_upload 가 손상 파일을 저장했다 — 거부되지 않음")
    except PH.UploadError:
        after_files = sum(len(fs) for _, _, fs in os.walk(_tmpdir4))
        chk(after_files == before_files,
            "★★★ 거부되면 디스크에 파일이 남지 않는다(깨진 사진이 저장되지 않는다)",
            f"거부 전 {before_files}개 → 거부 후 {after_files}개")

    saved = PH.save_upload(_FakeFS(good, "ok.jpg"), 999999)
    chk(saved["exif_error"] is None and saved["size"] > 0,
        "★ 정상 파일은 save_upload 로 끝까지 정상 저장된다(회귀 방지)", saved.get("exif_error"))
except ImportError as e:
    chk(False, "★★★ 사진 업로드 실측 (Pillow 없음?)", f"{type(e).__name__} {e}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 사진 업로드 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    import shutil
    shutil.rmtree(_tmpdir4, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[5] 로그인 잠금 수동 해제 — 실패 기록만, 그 아이디만 지운다")
# ──────────────────────────────────────────────────────────────
_i_ul = APP.find('def api_unlock_login():')
_j_ul = APP.find("\n# ══", _i_ul)
_ul_src = APP[max(0, _i_ul - 200):_j_ul] if _i_ul >= 0 else ""
chk(bool(_ul_src.strip()), "api_unlock_login 라우트를 찾았다")
chk('@app.post("/api/login-attempts/unlock")' in _ul_src, "★ POST 전용 라우트다")
chk('@require_role("중간관리자")' in _ul_src,
    "★★ 중간관리자 이상만 부를 수 있다(운영 지원 인력이 즉시 대응 가능한 문턱)")

_i_sql = _ul_src.find('"DELETE FROM login_attempts')
_j_sql = _ul_src.find('"', _i_sql + 1)
_sql = _ul_src[_i_sql + 1:_j_sql] if _i_sql >= 0 else ""   # 따옴표 안 SQL 본문만
chk("success=0" in _sql.replace(" ", ""),
    "★★★ 실패 기록(success=0)만 지운다 — 성공 로그인 이력은 안 건드린다", _sql[:120])
#  ⚠ 라운드54 에서 "username=?" 단건 일치 → "username IN (?,?,?,?)" 로 넓어졌다
#    (협력사 P:·보험사 I:·2단계인증 OTP: 네임스페이스까지 함께 지우려고 —
#     원문 아이디만 지우면 그 세 창구의 잠금은 하나도 안 풀렸다). 다른 계정을
#     안 건드린다는 성질 자체는 그대로라 이 절의 취지는 안 바뀐다 — 확장된
#     자리표시자 개수만 반영한다.
#  ⚠⚠ 라운드414 에서 change-password("PW:")·2단계인증해제("PWX:") 창구가 더해져
#    다시 (?,?,?,?,?,?) 여섯 자리로 넓어졌다 — 같은 이유, 같은 성질(다른 계정은
#    안 건드림) 유지, 자리표시자 개수만 또 한 번 반영한다.
#  ⚠⚠ 라운드554 에서 2단계 인증 등록확인("OTPSETUP:") 창구가 더해져 다시
#    (?,?,?,?,?,?,?) 일곱 자리로 넓어졌다 — 같은 이유, 같은 성질 유지, 자리표시자
#    개수만 세 번째로 반영한다(라운드488 이 그 창구 자체는 먼저 만들었지만
#    이 수동해제 목록에 반영을 안 해 라운드554 가 뒤늦게 따라잡은 것 — 아래 6개
#    → 7개 검사도 그 격차를 그대로 보여준다).
chk("usernameIN(?,?,?,?,?,?,?)" in _sql.replace(" ", ""),
    "★★ 일곱 자리 IN 절로 좁힌다(다른 계정은 안 건드린다)")
chk("DB.log(" in _ul_src, "★ 조치를 감사로그에 남긴다")

#  ── 실제로 실행해 본다 — 추출한 DELETE 문 그대로, 손으로 다시 안 적는다 ──
_tmpdir5 = tempfile.mkdtemp(prefix="unlock_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir5, "ul.db")
try:
    import db as _db5
    _db5.DB_PATH = os.environ["BOKGUON_DB_PATH"]
    _db5.init_db()
    conn5 = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
    conn5.row_factory = sqlite3.Row

    conn5.executescript("""
        INSERT INTO login_attempts(username, ip, success, created_at) VALUES
          ('locked_user','1.1.1.1',0,datetime('now')),
          ('locked_user','1.1.1.1',0,datetime('now')),
          ('locked_user','2.2.2.2',0,datetime('now')),
          ('locked_user','1.1.1.1',1,datetime('now')),
          ('other_user','1.1.1.1',0,datetime('now'));
    """)
    conn5.commit()

    #  ⚠ 라운드54: 실제 호출부(api_unlock_login)가 넘기는 것과 같은 일곱 키
    #    (원문·P:·I:·OTP:·PW:·PWX:·OTPSETUP: — 뒤 셋은 각각 라운드414·554 추가,
    #    라운드554는 라운드488이 만든 OTPSETUP: 창구를 이 목록이 놓쳤던 것을
    #    뒤늦게 반영) — 이 픽스처엔 그 여섯 변형이 없으므로 매치 결과는 이전과
    #    동일해야 한다(원문 'locked_user' 실패기록 3건만). _sql 은 지금(고친)
    #    app.py 에서 그대로 추출한 것이라 자리표시자가 7개다 — 파라미터 개수를
    #    안 맞추면 sqlite3.ProgrammingError 로 이 스텝 자체가 죽는다(실측:
    #    라운드554가 처음 이 파일을 앞 [1] 검사만 갱신하고 이 실행부는 놓쳤을 때
    #    바로 이 예외로 재현됨).
    n = conn5.execute(
        _sql, ("locked_user", "P:locked_user", "I:locked_user", "OTP:locked_user",
               "PW:locked_user", "PWX:locked_user", "OTPSETUP:locked_user")).rowcount
    conn5.commit()

    left_target_fail = conn5.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE username='locked_user' AND success=0"
    ).fetchone()[0]
    left_target_ok = conn5.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE username='locked_user' AND success=1"
    ).fetchone()[0]
    left_other = conn5.execute(
        "SELECT COUNT(*) FROM login_attempts WHERE username='other_user'"
    ).fetchone()[0]

    chk(n == 3, "★★★ 대상 아이디의 실패 기록 3건이 정확히 지워졌다(IP 여러 개 포함)", n)
    chk(left_target_fail == 0, "★★★ 지운 뒤 그 아이디의 실패 기록은 0건이다(잠금 해제됨)")
    chk(left_target_ok == 1, "★★ 같은 아이디의 성공 로그인 이력은 그대로 남는다")
    chk(left_other == 1, "★★ 다른 아이디(other_user)는 전혀 건드리지 않는다")

    conn5.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 잠금 해제 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir5, ignore_errors=True)

#  화면 쪽 — 버튼이 실제로 연결돼 있는가(죽은 버튼 방지)
chk("ACT.unlockLogin" in ADM, "★ 화면에 잠금 해제 액션이 등록돼 있다")
chk('data-act="unlockLogin"' in ADM, "★★ 버튼이 그 액션에 연결돼 있다")
chk("/api/login-attempts/unlock" in ADM, "★ 화면이 실제 라우트를 부른다")

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
