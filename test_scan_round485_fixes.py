# -*- coding: utf-8 -*-
"""스캔 485라운드 회귀 — int(float(x))가 x='inf'/'-inf'/'1e400'류일 때
ValueError가 아니라 OverflowError를 내는 함정을, 형제 parse_days()
(457-461행, 396·423라운드가 이미 이식)는 아는데 같은 파일의 두 자리가
못 물려받았던 결함, 2건(정밀조사 Agent가 발견).

  ① _setting_int()(3738-3749행) — "설정이 깨졌다고 업무가 멈추면 안
     되므로 예외를 위로 던지지 않는다"고 문서화된 공유 헬퍼가 이 한
     가지 예외만 못 잡음. 같은 위협모델(settings 테이블에 'inf' 문자열)
     을 365라운드가 형제 _bid_weights()에서 이미 실제로 겪고 고쳤음
     (test_scan_round365_fixes.py:108).
  ② api_settings_set()의 RANGES 검증 루프(20578-20583행) — 이 except가
     못 잡으면 "숫자여야 합니다" 400 대신 전역 오류핸들러가 뜻모를 500을
     낸다.

  [1] 소스 확인 — 두 지점 모두 OverflowError를 잡음.
  [2] 실제 실행 — settings 테이블에 'inf'를 직접 넣고 _setting_int()를
      실제로 불러 예외 없이 기본값을 돌려주는지, 실제 Flask PATCH
      /api/settings에 "inf"를 보내 500이 아니라 400+정확한 문구가
      오는지 확인.
  [3] 되돌림-증명 — 두 지점을 옛(OverflowError 못 잡는) 코드로 임시
      되돌려 같은 시나리오에서 실제로 처리되지 않은 예외가 새는지 대조.
"""
import ast
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 485라운드 회귀 — int(float('inf')) OverflowError 미포착 2건")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
_i1 = APP_SRC.find("def _setting_int(conn, key, default, lo, hi):")
_j1 = APP_SRC.find("    return default", _i1)
NEW_1 = APP_SRC[_i1:_j1 + len("    return default")] if _i1 > 0 and _j1 > 0 else ""

_i2 = APP_SRC.find("            try:\n                v = int(float(d[k]))\n")
_j2 = APP_SRC.find('), 400', _i2)
NEW_2 = APP_SRC[_i2:_j2 + len('), 400')] if _i2 > 0 and _j2 > 0 else ""

chk(_i1 > 0 and "OverflowError" in NEW_1, "① _setting_int() — OverflowError를 잡는다",
    NEW_1[-200:] if NEW_1 else "블록을 못 뽑음")
chk(APP_SRC.count(NEW_1) == 1 if NEW_1 else False,
    "① 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다")
chk(_i2 > 0 and "OverflowError" in NEW_2, "② api_settings_set() — OverflowError를 잡는다",
    NEW_2[-200:] if NEW_2 else "블록을 못 뽑음")
chk(APP_SRC.count(NEW_2) == 1 if NEW_2 else False,
    "② 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다")

# ══════════════════════════════════════════════════════════════
print("\n[2]+[3] 실제 Flask 앱(in-process) — 실행 + 되돌림-증명")
print("    [round620 마이그레이션: importlib.reload의 RecursionError 함정은 그대로")
print("     피하되, 서브프로세스 대신 독립 사본 네임스페이스 exec(①) + view_functions")
print("     딕트 스왑(②)을 쓴다 — 새 인터프리터도, app.py 디스크 쓰기도 필요 없다.]")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="r485_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

try:
    import db as DB               # noqa: E402
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.execute("INSERT INTO settings(key,value) VALUES('min_bidders','inf') "
                 "ON CONFLICT(key) DO UPDATE SET value='inf'")
    conn.commit()
    conn.close()

    import app as A                # noqa: E402

    # (A) 현재(고쳐진) 코드로 먼저 실행 — 실제 함수·실제 view_functions 그대로
    conn2 = DB.get_db()
    try:
        setting_int_result = A._setting_int(conn2, "min_bidders", 3, 1, 20)
        setting_int_raised = None
    except Exception as _e:                                        # noqa: BLE001
        setting_int_result = None
        setting_int_raised = type(_e).__name__
    finally:
        conn2.close()
    chk(setting_int_raised is None,
        "★★★★★ ① settings.value='inf'여도 _setting_int()가 예외 없이 끝난다", setting_int_raised)
    chk(setting_int_result == 3,
        "★★★★★ ① 손상값이라 기본값(3)으로 되돌아간다(문서화된 계약대로)", setting_int_result)

    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_name"] = "검증"
        sess["admin_role"] = "최고관리자"; sess["_csrf"] = "r485-csrf"
    r = c.patch("/api/settings", json={"dispatch_minutes": "inf"},
                headers={"X-CSRF-Token": "r485-csrf"})
    patch_body = r.get_json(silent=True)
    chk(r.status_code == 400,
        "★★★★★ ② PATCH /api/settings에 'inf'를 보내면 500이 아니라 400이다", r.status_code)
    chk((patch_body or {}).get("error") == "dispatch_minutes 는 숫자여야 합니다.",
        "★★★★★ ② 정확한 안내문구가 온다(제네릭 500 아님)", patch_body)

    # (B) 되돌림 — 두 지점을 옛(OverflowError 못 잡는) 코드로 임시 교체, 재현, 복원
    #     각 NEW 블록 안에서 "삽입한 주석 전체 + 넓힌 except 튜플"만 좁은
    #     원래 except 튜플로 되돌린다 — 나머지(함수 본문)는 그대로 둔다.
    assert NEW_1 and NEW_2, "새 블록을 못 뽑아 되돌림-증명을 진행할 수 없다"
    _comment_1_end = NEW_1.find("    except (sqlite3.Error, ValueError, TypeError, OverflowError):")
    _comment_1_start = NEW_1.find("    #  ⚠⚠ [라운드485]")
    assert _comment_1_start > 0 and _comment_1_end > _comment_1_start, "①의 주석 경계를 못 찾음"
    REVERT_1 = NEW_1[_comment_1_start:_comment_1_end] + \
        "    except (sqlite3.Error, ValueError, TypeError, OverflowError):"
    OLD_1_ACTUAL = NEW_1.replace(
        REVERT_1, "    except (sqlite3.Error, ValueError, TypeError):")
    assert OLD_1_ACTUAL != NEW_1, "①의 되돌림 치환이 안 먹었다"

    _comment_2_end = NEW_2.find("            except (TypeError, ValueError, OverflowError):")
    _comment_2_start = NEW_2.find("            #  ⚠⚠ [라운드485]")
    assert _comment_2_start > 0 and _comment_2_end > _comment_2_start, "②의 주석 경계를 못 찾음"
    REVERT_2 = NEW_2[_comment_2_start:_comment_2_end] + \
        "            except (TypeError, ValueError, OverflowError):"
    OLD_2_ACTUAL = NEW_2.replace(
        REVERT_2, "            except (TypeError, ValueError):")
    assert OLD_2_ACTUAL != NEW_2, "②의 되돌림 치환이 안 먹었다"

    reverted_src = APP_SRC.replace(NEW_1, OLD_1_ACTUAL).replace(NEW_2, OLD_2_ACTUAL)
    assert reverted_src != APP_SRC, "되돌림 치환이 실제로 안 먹었다"

    _tree = ast.parse(reverted_src)
    _lines = reverted_src.splitlines(keepends=True)
    _fn_src = {}
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name in ("_setting_int", "api_settings_set"):
            _fn_src[_node.name] = "".join(_lines[_node.lineno - 1:_node.end_lineno])
    assert set(_fn_src) == {"_setting_int", "api_settings_set"}, \
        f"되돌린 함수 소스를 AST로 못 뽑음: {sorted(_fn_src)}"
    chk("OverflowError" not in _fn_src["_setting_int"],
        "  (준비) 되돌린 _setting_int() 소스에 OverflowError 포착이 없다(되돌림 확인)")
    chk("OverflowError" not in _fn_src["api_settings_set"],
        "  (준비) 되돌린 api_settings_set() 소스에 OverflowError 포착이 없다(되돌림 확인)")

    #  독립 사본 네임스페이스에 두 되돌린 함수를 모두 exec — 서로 안 부르는
    #  별개 함수라(위에서 grep으로 확인) 이름공간을 공유해도 안전하다.
    _ns = dict(vars(A))
    exec(compile(_fn_src["_setting_int"], "<round485-reverted:_setting_int>", "exec"), _ns)
    exec(compile(_fn_src["api_settings_set"], "<round485-reverted:api_settings_set>", "exec"), _ns)

    conn3 = DB.get_db()
    try:
        _ns["_setting_int"](conn3, "min_bidders", 3, 1, 20)
        broken_setting_int_raised = None
    except Exception as _e:                                        # noqa: BLE001
        broken_setting_int_raised = type(_e).__name__
    finally:
        conn3.close()
    chk(broken_setting_int_raised == "OverflowError",
        "★★★★★ ① 옛 코드(되돌림)는 OverflowError가 그대로 샌다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken_setting_int_raised)

    temp_settings_set = A.require_role("최고관리자")(_ns["api_settings_set"])
    original_settings_set = A.app.view_functions["api_settings_set"]
    A.app.view_functions["api_settings_set"] = temp_settings_set
    try:
        r_broken = c.patch("/api/settings", json={"dispatch_minutes": "inf"},
                            headers={"X-CSRF-Token": "r485-csrf"})
        broken_patch_body = r_broken.get_json(silent=True)
        #  ⚠⚠ [라운드596] 이 자리(②, Flask 라우트)는 더 이상 500으로 새지 않는다 —
        #    round596이 전역 예외핸들러(err_500)에 OverflowError→400 분기를 추가해,
        #    이 라우트의 **지역** 방어(위에서 되돌린 것)가 없어도 **전역** 방어가
        #    받아낸다(두 방어가 겹치는 방어심층 — 정상). 다만 문구는 이 라우트
        #    자신의 것("dispatch_minutes 는 숫자여야 합니다.")이 아니라 전역 핸들러의
        #    제네릭 문구("입력값이 너무 큽니다.")로 내려간다 — 그 차이가 지역 방어가
        #    여전히 값어치 있다는 증거다(사용자에게 어느 필드가 문제인지 알려주는
        #    구체적 안내는 전역 방어가 대신할 수 없다). ①(_setting_int, Flask 요청과
        #    무관한 순수 함수 — 백그라운드 스윕 등에서도 불릴 수 있다)은 전역
        #    핸들러의 우산 밖이라 여전히 그대로 OverflowError가 새므로(바로 위 검사가
        #    이미 확인) 지역 방어가 여전히 필수임은 변함없다.
        chk(r_broken.status_code == 400 and (broken_patch_body or {}).get("code") == "BAD_INPUT",
            "★★★★★ ② 옛 코드(되돌림)는 500 대신 round596의 전역 방어(400/BAD_INPUT)로 "
            "받아진다 — 지역 방어를 없애면 라우트 고유의 친절한 문구를 잃는다는 것을 "
            "이 테스트가 여전히 증명함", broken_patch_body)
        chk((broken_patch_body or {}).get("error") != "dispatch_minutes 는 숫자여야 합니다.",
            "STEP 지역 방어가 빠지면 필드별 안내문구도 함께 사라진다"
            "(전역 방어는 제네릭 문구만 준다 — 지역 방어의 존재가치 확인)", broken_patch_body)
    finally:
        A.app.view_functions["api_settings_set"] = original_settings_set

    chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
        "★★★★★ app.py는 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다"
        "(되돌린 함수들은 dict(vars(A)) 독립 사본에만 exec되고 view_functions만 임시 스왑됨)")

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")
finally:
    for _k in ("BOKGUON_DB_PATH", "BOKGUON_UPLOAD_DIR", "BOKGUON_ENV", "BOKGUON_SEED_DEMO"):
        os.environ.pop(_k, None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
