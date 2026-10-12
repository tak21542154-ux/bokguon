# -*- coding: utf-8 -*-
"""스캔 538라운드 회귀 — 사진 업로드 3형제(협력사 시공사진 api_partner_upload_photos·
   보험사/운영자 피해사진 _upload_damage_photos·하자 사진 api_defect_photos_upload)가
   전부 "INSERT 실패 → 방금 저장한 파일 정리(os.remove) → 사용자에게 errors[]로 통지"
   까지는 똑같이 하는데, 그중 하나(하자 사진, 가장 나중에 손 본 것)만 그 실패를
   app.logger.exception() 으로 서버 로그에 남기고 나머지 둘은 침묵하던 결함.

   조사 배경 — 이번 라운드 지시 각도 (2)"파일시스템에 저장된 실제 파일이 DB 레코드
   삭제 시 실제로 지워지는지, round110이 커버 안 하는 다른 삭제 경로가 있는지"를
   따라가다 photos 테이블의 유일한 실제 삭제 경로(api_photo_delete, round110·PH-03)
   자체는 이미 완벽했다(ai_reviews·damage_reads·defect_photos·fix_for·ai_photo_id
   전부 정리). 그런데 "삭제"가 아니라 "업로드 중 INSERT 실패"라는 형제 실패경로를
   보니, 사진 업로드 라우트 3곳 전부가 이미 [PH-07]류 관례(저장 성공 뒤 INSERT가
   실패하면 방금 디스크에 쓴 파일이 고아로 남으므로 os.remove 로 치운다)를 갖고
   있었다 — 이 자체는 이미 완비돼 있어 파일 고아화 위험은 없었다.

   대신 세 함수의 except Exception: 블록을 나란히 대조하니 로깅 여부가 갈렸다.
   api_defect_photos_upload(app.py, round538 당시 15130행 부근)만 자기 자신의
   docstring 격 주석으로 "조용히 삼키면 안 된다"고 명시하며 app.logger.exception(
   "하자 사진 저장 실패 defect=%s", did) 를 남기는데, 형제 api_partner_upload_photos
   (round538 당시 12269행 부근, [PH-07] 원본 주석의 함수 — 세 경로 중 실무에서
   가장 자주 쓰이는 "협력사 시공사진" 경로)와 _upload_damage_photos(12407행 부근,
   보험사·운영자 공용 "피해사진" 경로) 는 둘 다 errors[] 에는 담아 사용자에게는
   실패를 보여주면서도(그래서 "화면은 성공인데 실제로 0장" 류의 라운드178/round15130
   자체 주석이 말하는 결함은 아니다), 서버 로그에는 아무 흔적을 안 남겼다 — 디스크
   손상·인코딩 이상 등 원인 모를 INSERT 실패가 반복돼도 운영자는 알 방법이 없다.
   이 원칙(침묵이면 반복 실패해도 아무도 모른다)은 이 저장소 자신이 round279
   (dispatch.py _release_lease)·round536(app.py _sweep_if_due)에서 이미 반복
   확인한 것과 같은 계열이다.

   고침 — 새 정책·새 헬퍼 없이, 형제(api_defect_photos_upload)가 이미 쓰는 그
   스타일 그대로 app.logger.exception(...) 한 줄씩만 두 함수에 이식했다.
     · api_partner_upload_photos(): app.logger.exception("시공 사진 저장 실패 case=%s", cid)
     · _upload_damage_photos():     app.logger.exception("피해 사진 저장 실패 case=%s", cid)
   기존 [PH-07] 고아파일 정리(os.remove)·errors[] 응답 로직의 위치·순서는
   전혀 건드리지 않았다(로그 호출을 그 앞에 한 줄 추가했을 뿐).

      python test_scan_round538_fixes.py
"""
import io
import logging
import os
import shutil
import sys
import tempfile

#  ⚠ 윈도 기본 콘솔은 cp949 라 em dash(—) 같은 문자를 print 하면
#    UnicodeEncodeError 로 죽는다 — 형제 테스트(round528·536·537 등)가 이미 쓰는
#    방어를 그대로 옮긴다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 538라운드 회귀 — 사진 업로드 형제 3곳 중 2곳의 INSERT 실패 서버로그 누락")
print("=" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ==================================================================
print("\n[1] 소스: 형제 셋 중 두 곳에 app.logger.exception 을 새로 추가했고, "
      "나머지 한 곳(하자 사진, 이식 원본)의 기존 호출은 손대지 않았다")
# ------------------------------------------------------------------
import ast as _ast
chk(_ast.parse(APP_SRC) is not None, "STEP app.py 전체 ast.parse 성공")

pu_body = _py_fn_body(APP_SRC, "api_partner_upload_photos")
chk('app.logger.exception("시공 사진 저장 실패 case=%s", cid)' in pu_body,
    "★★★★★ api_partner_upload_photos() 가 이제 INSERT 실패를 app.logger.exception "
    "으로 남긴다(고치기 전엔 이 문자열이 이 함수 안에 없었다)")
chk('[PH-07]' in pu_body,
    "STEP 기존 [PH-07] 고아파일 정리 주석·로직은 그대로 남아 있다")
#  ⚠ os.remove(PHOTO.abs_path(info["rel_path"])) 문자열은 이 함수 안에 **셋**이다
#    (쿼터 재검사 정리·중복사진 정리·[PH-07] 정리) — _log_idx **이후** 첫 등장을
#    찾아야 내가 새로 넣은 블록 안의 것과 비교하는 것이 된다(처음 것을 그냥
#    집으면 훨씬 앞선 무관한 블록과 비교하게 된다).
_log_idx = pu_body.index('app.logger.exception("시공 사진 저장 실패 case=%s", cid)')
_rm_idx = pu_body.index('os.remove(PHOTO.abs_path(info["rel_path"]))', _log_idx)
_err_idx = pu_body.index("저장에 실패했습니다", _log_idx)
chk(_log_idx < _rm_idx < _err_idx,
    "STEP 순서 — 로그 남기기 → 고아파일 정리(os.remove) → 사용자 응답(errors[]) 순서"
    "(기존 정리·응답 로직의 상대 위치는 전혀 안 바뀌었다)")

dp_body = _py_fn_body(APP_SRC, "_upload_damage_photos")
chk('app.logger.exception("피해 사진 저장 실패 case=%s", cid)' in dp_body,
    "★★★★★ _upload_damage_photos() 도 이제 INSERT 실패를 app.logger.exception 으로 "
    "남긴다(고치기 전엔 이 문자열이 이 함수 안에 없었다)")
_log_idx2 = dp_body.index('app.logger.exception("피해 사진 저장 실패 case=%s", cid)')
_rm_idx2 = dp_body.index('os.remove(PHOTO.abs_path(info["rel_path"]))',
                         dp_body.index("except Exception:"))
chk(_log_idx2 < _rm_idx2,
    "STEP 순서 — 여기서도 로그가 고아파일 정리보다 먼저다")

#  형제(내가 손대지 않은 이식 원본) 대조 — 그대로 남아 있는지
df_body = _py_fn_body(APP_SRC, "api_defect_photos_upload")
chk('app.logger.exception("하자 사진 저장 실패 defect=%s", did)' in df_body,
    "★★★ 형제 api_defect_photos_upload() 의 기존 로깅(이식 원본)은 이번 라운드가 "
    "손대지 않고 그대로 남아 있다")

# ==================================================================
# 실행 준비
# ------------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round538_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

CSRF = "r538-csrf"
H = {"X-CSRF-Token": CSRF}
A = None
DB = None
PHOTO_MOD = None
_ORIG_SAVE_UPLOAD = None
client = None
pid_org = cid_partner = cid_damage = None


def _jpeg_bytes(color):
    """진짜로 디코드 가능한 최소 JPEG — round141 과 같은 이유
    (photo_ai._strip_exif 의 Image.load() 가 가짜 매직바이트를 OSError로 거부)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), color).save(buf, format="JPEG")
    return buf.getvalue()


class _Recorder(logging.Handler):
    """app.logger 에 붙여 실제로 남는 로그 레코드를 그대로 받아 적는다."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _as_admin():
    with client.session_transaction() as sess:
        sess.clear()
        sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증관리자"
        sess["_csrf"] = CSRF
    return H


def _as_partner():
    with client.session_transaction() as sess:
        sess.clear()
        sess["partner_id"] = pid_org
        sess["partner_name"] = "R538업체"
        sess["_csrf"] = CSRF
    return H


def _poison_factory(sink):
    """진짜 save_upload() 를 그대로 불러 파일을 실제로 디스크에 쓰게 한 뒤,
    돌아온 dict 의 size 만 sqlite3 가 바인딩할 수 없는 값으로 바꿔치기한다.
    → INSERT 문에서 sqlite3.ProgrammingError(Exception 의 하위클래스, IntegrityError
    아님) 가 나 bare except Exception: 블록으로 정확히 떨어진다. 파일은 이미 실제로
    저장됐으므로 [PH-07] 정리(os.remove)가 진짜로 할 일이 있는 상태에서 검증된다."""
    def _poison(fs, cid):
        info = _ORIG_SAVE_UPLOAD(fs, cid)
        sink["rel_path"] = info["rel_path"]
        info = dict(info)
        info["size"] = object()          # sqlite3 가 못 바인딩하는 타입
        return info
    return _poison


try:
    import db as DB
    DB.init_db()
    import app as A
    import photo_ai as PHOTO_MOD
    _ORIG_SAVE_UPLOAD = PHOTO_MOD.save_upload

    chk(A.PHOTO is PHOTO_MOD,
        "STEP app.py 의 PHOTO 는 photo_ai 모듈 그 자체 — 이 테스트의 몽키패치가 "
        "app.py 의 실제 호출에도 그대로 먹는다")

    conn0 = DB.get_db()
    conn0.execute("INSERT INTO admins(username,password_hash,name,role) "
                  "VALUES('admin','x','검증관리자','최고관리자')")
    pid_org = conn0.execute(
        "INSERT INTO partners(name,partner_type,status,category,region,phone,login_id) "
        "VALUES('R538업체','시공사','활성','가드레일','서울','01099990001','r538p_org')").lastrowid
    cid_partner = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,partner_id,is_demo) "
        "VALUES('R538-P','시공중','가드레일','서울',?,0)", (pid_org,)).lastrowid
    cid_damage = conn0.execute(
        "INSERT INTO cases(case_no,status,category,region,is_demo) "
        "VALUES('R538-D','입찰중','가드레일','서울',0)").lastrowid
    conn0.commit(); conn0.close()

    client = A.app.test_client()
    chk(True, "STEP 스크래치 DB·app 모듈 로드 성공 — 관리자·협력사·사건 2건 준비",
        os.environ["BOKGUON_DB_PATH"])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드538 실행 준비(DB.init_db·app import)", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[2] 실행(진짜 라우트): 협력사 시공사진 업로드 — INSERT 가 실패하면 "
      "이제 서버 로그에 남는다")
# ------------------------------------------------------------------
try:
    sink = {}
    PHOTO_MOD.save_upload = _poison_factory(sink)
    rec = _Recorder()
    A.app.logger.addHandler(rec)
    try:
        hdr = _as_partner()
        img = (io.BytesIO(_jpeg_bytes((10, 20, 30))), "p538.jpg")
        r = client.post(f"/api/partner/cases/{cid_partner}/photos", headers=hdr,
                         data={"photos": [img]}, content_type="multipart/form-data")
        body = r.get_json() or {}
        chk(r.status_code == 200,
            "STEP INSERT 가 실패해도 라우트 자체는 200 을 유지한다(사용자 경험 무회귀)",
            (r.status_code, body))
        chk(body.get("count") == 0 and len(body.get("errors") or []) == 1,
            "STEP 응답 errors[] 에 실패 메시지가 여전히 담긴다(기존 동작 무회귀)", body)

        msgs = [x.getMessage() for x in rec.records]
        chk(msgs.count(f"시공 사진 저장 실패 case={cid_partner}") == 1,
            "★★★★★ 서버 로그에 '시공 사진 저장 실패 case=<사건id>' 가 정확히 1건 "
            "남는다(고치기 전엔 여기 0건이었다)", msgs)
        _new_recs = [x for x in rec.records
                     if x.getMessage() == f"시공 사진 저장 실패 case={cid_partner}"]
        chk(bool(_new_recs) and _new_recs[0].exc_info is not None,
            "STEP app.logger.exception() 답게 exc_info(트레이스백)까지 함께 남는다")

        _full = PHOTO_MOD.abs_path(sink["rel_path"])
        chk(not os.path.exists(_full),
            "STEP [PH-07] 고아파일 정리는 이번에도 그대로 동작 — 실제로 디스크에 "
            "저장됐던 파일이 지워졌다(새 로그 한 줄이 기존 정리 로직을 밀어내지 않았다)")
    finally:
        A.app.logger.removeHandler(rec)
        PHOTO_MOD.save_upload = _ORIG_SAVE_UPLOAD
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드538 [2] 협력사 시공사진 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[3] 실행(진짜 라우트): 운영자 피해사진 업로드 — INSERT 가 실패하면 "
      "이제 서버 로그에 남는다")
# ------------------------------------------------------------------
try:
    sink2 = {}
    PHOTO_MOD.save_upload = _poison_factory(sink2)
    rec2 = _Recorder()
    A.app.logger.addHandler(rec2)
    try:
        hdr = _as_admin()
        img = (io.BytesIO(_jpeg_bytes((40, 50, 60))), "d538.jpg")
        r = client.post(f"/api/cases/{cid_damage}/photos/damage", headers=hdr,
                         data={"photos": [img]}, content_type="multipart/form-data")
        body = r.get_json() or {}
        chk(r.status_code == 200,
            "STEP INSERT 가 실패해도 라우트 자체는 200 을 유지한다", (r.status_code, body))
        chk(len(body.get("errors") or []) == 1,
            "STEP 응답 errors[] 에 실패 메시지가 여전히 담긴다(기존 동작 무회귀)", body)

        msgs2 = [x.getMessage() for x in rec2.records]
        chk(msgs2.count(f"피해 사진 저장 실패 case={cid_damage}") == 1,
            "★★★★★ 서버 로그에 '피해 사진 저장 실패 case=<사건id>' 가 정확히 1건 "
            "남는다(고치기 전엔 여기 0건이었다)", msgs2)

        _full2 = PHOTO_MOD.abs_path(sink2["rel_path"])
        chk(not os.path.exists(_full2), "STEP 고아파일 정리는 이 경로에서도 그대로 동작")
    finally:
        A.app.logger.removeHandler(rec2)
        PHOTO_MOD.save_upload = _ORIG_SAVE_UPLOAD
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드538 [3] 운영자 피해사진 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[4] 실행(형제 대조군, 손대지 않음): 하자 사진 업로드는 이식 원본 그대로 "
      "여전히 로깅한다")
# ------------------------------------------------------------------
try:
    hdr = _as_admin()
    r = client.post("/api/defects", json={"case_id": cid_damage, "title": "R538 하자"}, headers=hdr)
    chk(r.status_code == 200, "STEP 하자 접수 200", (r.status_code, r.get_data(as_text=True)))
    did = r.get_json()["id"]

    sink3 = {}
    PHOTO_MOD.save_upload = _poison_factory(sink3)
    rec3 = _Recorder()
    A.app.logger.addHandler(rec3)
    try:
        img = (io.BytesIO(_jpeg_bytes((70, 80, 90))), "def538.jpg")
        r = client.post(f"/api/defects/{did}/photos", headers=hdr,
                         data={"photos": [img]}, content_type="multipart/form-data")
        body = r.get_json() or {}
        #  ⚠ 이 형제만 "한 장도 못 올렸으면 성공이라고 말하지 않는다"(15154행 부근
        #    주석)는 자기만의 원칙으로 saved 가 비면 409 를 준다 — 다른 두 형제
        #    (항상 200)와 다른, 이번 라운드와 무관한 기존 동작이다. 이 테스트는
        #    로깅 여부만 보므로 상태코드는 그 실제 동작(409)에 맞춘다.
        chk(r.status_code == 409 and len(body.get("errors") or []) == 1,
            "STEP 한 장도 못 올리면 409·errors[] 1건(기존 동작, 무회귀)", (r.status_code, body))
        msgs3 = [x.getMessage() for x in rec3.records]
        chk(msgs3.count(f"하자 사진 저장 실패 defect={did}") == 1,
            "STEP 형제(하자 사진, 이번 라운드가 손대지 않은 이식 원본)는 원래부터 "
            "로그를 남긴다 — 이식해 온 원본이 여전히 살아 있다는 대조군", msgs3)
    finally:
        A.app.logger.removeHandler(rec3)
        PHOTO_MOD.save_upload = _ORIG_SAVE_UPLOAD
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드538 [4] 형제 대조군(하자 사진) 실행", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[5] 되돌리기 — 협력사 시공사진: app.logger.exception 줄을 빼면(수정 전 코드 "
      "재구성) 정말 로그가 0건이 되는가(인과관계 직접증명)")
# ------------------------------------------------------------------
#  ⚠ app.py 자체는 건드리지 않는다 — 동시편집 세션이 이 파일을 같이 건드릴 수 있는
#    환경(round520 이후 표준 관례). "수정 전" 은 이 세션이 고치기 **직전**에 Read 로
#    직접 확인한 실제 원문을 문자열로만 재구성하고, "수정 후" 는 지금 app.py 에서
#    실제로 뽑아 온 문자열(손으로 옮겨 적지 않음)을 쓴다 — 둘 다 같은 방식(작은
#    except 블록만 떼어 더미 for 루프 안에서 강제로 예외를 내 실행)으로 돌려
#    로그 유무만 비교한다.
_PRE538_PARTNER = (
    '        except Exception:\n'
    '            # [PH-07] INSERT 가 실패하면 방금 저장한 파일이 고아로 남는다 — 정리한다.\n'
    '            try:\n'
    '                os.remove(PHOTO.abs_path(info["rel_path"]))\n'
    '            except OSError:\n'
    '                pass\n'
    '            errors.append(f"\'{info[\'orig_name\']}\' 저장에 실패했습니다.")\n'
    '            continue\n'
)


def _run_snippet(body_src, cid_val):
    ns = {"os": os, "PHOTO": PHOTO_MOD, "app": A.app}
    errors = []
    info = {"rel_path": "no/such/round538/file.jpg", "orig_name": "x.jpg"}
    src = ("def _snip(errors, info, cid):\n"
           "    for _once in (0,):\n"
           "        try:\n"
           "            raise RuntimeError('forced failure for round538 proof')\n"
           + body_src)
    exec(compile(src, "<round538_snippet>", "exec"), ns)          # noqa: S102
    ns["_snip"](errors, info, cid_val)
    return errors


try:
    chk(_PRE538_PARTNER not in pu_body,
        "STEP 수정 직전 원문 그대로는(app.logger.exception 없이) 지금 소스에 더 이상 "
        "없다 — 그 자리에 로그 호출이 새로 끼어들었다는 뜻")

    rec_old = _Recorder()
    A.app.logger.addHandler(rec_old)
    try:
        errs_old = _run_snippet(_PRE538_PARTNER, 999001)
    finally:
        A.app.logger.removeHandler(rec_old)
    chk(len(errs_old) == 1 and not rec_old.records,
        "★★★★★ 수정 전 코드(재구성)는 errors[] 는 그대로 채우지만 서버 로그는 0건"
        "(사용자에겐 실패로 보이는데 운영자는 원인을 알 방법이 없었다)",
        [x.getMessage() for x in rec_old.records])

    _s = pu_body.index("        except Exception:\n            # [PH-07]")
    _e = pu_body.index("continue\n", _s) + len("continue\n")
    _CUR_PARTNER = pu_body[_s:_e]
    chk("app.logger.exception" in _CUR_PARTNER,
        "STEP 지금 소스에서 뽑아 온 블록(손으로 옮겨 적지 않음)에 로그 호출이 있다")

    rec_new = _Recorder()
    A.app.logger.addHandler(rec_new)
    try:
        errs_new = _run_snippet(_CUR_PARTNER, 999002)
    finally:
        A.app.logger.removeHandler(rec_new)
    _new_msgs = [x.getMessage() for x in rec_new.records]
    chk(len(errs_new) == 1 and _new_msgs.count("시공 사진 저장 실패 case=999002") == 1,
        "★★★★★ 지금(수정 후) 코드를 같은 방식으로 돌리면 로그가 정확히 1건 남는다 "
        "— 같은 입력·같은 예외인데 이 몇 줄 차이가 로그 유무를 가른다는 인과관계 "
        "직접증명", _new_msgs)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드538 [5] 되돌림-증명(협력사)", f"{type(e).__name__} {e}")

# ==================================================================
print("\n[6] 되돌리기 — 운영자 피해사진: 같은 방식으로 인과관계 재확인")
# ------------------------------------------------------------------
_PRE538_DAMAGE = (
    '        except Exception:\n'
    '            try:\n'
    '                os.remove(PHOTO.abs_path(info["rel_path"]))\n'
    '            except OSError:\n'
    '                pass\n'
    '            errors.append(f"\'{info[\'orig_name\']}\' 저장에 실패했습니다.")\n'
    '            continue\n'
)
try:
    chk(_PRE538_DAMAGE not in dp_body,
        "STEP 수정 직전 원문 그대로는 지금 소스에 더 이상 없다")

    rec_old2 = _Recorder()
    A.app.logger.addHandler(rec_old2)
    try:
        errs_old2 = _run_snippet(_PRE538_DAMAGE, 999003)
    finally:
        A.app.logger.removeHandler(rec_old2)
    chk(len(errs_old2) == 1 and not rec_old2.records,
        "★★★★★ 수정 전 코드(재구성)는 여기서도 로그 0건", [x.getMessage() for x in rec_old2.records])

    _s2 = dp_body.index("except Exception:")
    _e2 = dp_body.index("continue\n", _s2) + len("continue\n")
    _CUR_DAMAGE = "        " + dp_body[_s2:_e2]
    chk("app.logger.exception" in _CUR_DAMAGE,
        "STEP 지금 소스에서 뽑아 온 블록(손으로 옮겨 적지 않음)에 로그 호출이 있다")

    rec_new2 = _Recorder()
    A.app.logger.addHandler(rec_new2)
    try:
        errs_new2 = _run_snippet(_CUR_DAMAGE, 999004)
    finally:
        A.app.logger.removeHandler(rec_new2)
    _new_msgs2 = [x.getMessage() for x in rec_new2.records]
    chk(len(errs_new2) == 1 and _new_msgs2.count("피해 사진 저장 실패 case=999004") == 1,
        "★★★★★ 지금(수정 후) 코드는 로그가 정확히 1건 남는다 — 인과관계 직접증명",
        _new_msgs2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드538 [6] 되돌림-증명(운영자 피해사진)", f"{type(e).__name__} {e}")

# ==================================================================
# 정리
# ------------------------------------------------------------------
if PHOTO_MOD is not None and _ORIG_SAVE_UPLOAD is not None:
    PHOTO_MOD.save_upload = _ORIG_SAVE_UPLOAD
os.environ.pop("BOKGUON_DB_PATH", None)
os.environ.pop("BOKGUON_UPLOAD_DIR", None)
os.environ.pop("BOKGUON_ENV", None)
os.environ.pop("BOKGUON_SEED_DEMO", None)
shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
