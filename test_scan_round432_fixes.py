# -*- coding: utf-8 -*-
"""스캔 432라운드 회귀 — manage.py check(MG-06)의 프록시신뢰 검사가 Windows/
   waitress 배포에서 엉뚱한 변수를 보던 결함, 1건.

   정밀조사 Agent(각도1: 관리자 IP 화이트리스트 우회 가능성)가 발견 —
   MG-06(manage.py:618-)은 `BOKGUON_BEHIND_PROXY=1`인데 `BOKGUON_FORWARDED_
   ALLOW`가 비면 배포를 막는데, 이 변수를 실제로 읽는 코드는 저장소 전체에
   `gunicorn_conf.py`(Linux 배포 전용) 단 한 곳뿐임을 grep으로 확인했다.
   이 PC를 포함한 Windows 배포(`serve_waitress.py`)는 이 변수를 아예 안 읽고
   `trusted_proxy="127.0.0.1"`이 하드코딩돼 있다 — 그 하드코딩이 의미를
   가지려면 `BOKGUON_HOST`가 루프백을 유지해야 하는데(`serve_waitress.py`
   자신의 기본값이 `"0.0.0.0"`이라 설정을 빠뜨리면 외부에 그대로 노출됨을
   직접 확인), MG-06은 그 진짜 전제조건 대신 gunicorn 전용 변수만 검사해
   왔다 — manage.py 자신이 이미 274행에서 쓰는 `os.name=="nt"` 분기(WSGI
   서버 설치 확인)를 이 검사에는 안 맞췄던 것.

   실제 운영 위험은 지금 당장은 없다(이 PC의 실제 `.env`는 BOKGUON_HOST·
   FORWARDED_ALLOW 둘 다 이미 올바른 값이 들어 있다) — 문제는 점검 도구
   자체가 이 플랫폼에서 진짜 방어선을 안 본다는 것("자기도구가 내는 거짓
   초록/거짓 적신호" 부류): BOKGUON_HOST 가 실수로 0.0.0.0 등으로 바뀌어도
   이 검사는 못 잡고, 반대로 BOKGUON_FORWARDED_ALLOW 를 안 채웠다는 이유
   만으로 안전한 Windows 배포를 불필요하게 막을 수도 있었다.

   고침: MG-06 을 os.name=="nt" 로 분기 — Windows 경로는 BOKGUON_HOST 가
   루프백(127.0.0.1/localhost/::1)인지 검사하고, 그 외(Linux/gunicorn)
   경로는 기존 BOKGUON_FORWARDED_ALLOW 검사를 그대로 유지. 트레이드오프
   없는 "그냥 고치면 되는 것" — 점검 도구의 정확성 개선일 뿐 서버 자체의
   런타임 동작은 전혀 안 바뀐다.

       python test_scan_round432_fixes.py
"""
import ast
import contextlib
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


MANAGE_SRC = read("manage.py")

print("=" * 72)
print("  스캔 432라운드 회귀 — manage.py check MG-06 플랫폼 분기")
print("=" * 72)

print("\n[1] 소스 확인")
_i0 = MANAGE_SRC.index("# 4-2) 운영 보안 설정 (MG-06)")
_i1 = MANAGE_SRC.index("\n        if os.environ.get(\"BOKGUON_SEED_DEMO\"")
_mg06_body = MANAGE_SRC[_i0:_i1]
chk('if os.name == "nt":' in _mg06_body,
    "★★★★★ MG-06 이 274행과 같은 os.name==\"nt\" 분기를 쓴다")
chk('_host_val not in ("127.0.0.1", "localhost", "::1")' in _mg06_body,
    "★★★★ Windows 경로는 BOKGUON_HOST 가 루프백인지 검사한다")
chk('os.environ.get("BOKGUON_HOST", "0.0.0.0")' in _mg06_body,
    "★★★★★ 기본값 처리가 serve_waitress.py 자신의 실제 기본값(0.0.0.0)과 일치한다"
    "(비어 있으면 안전하다고 착각하지 않는다)")
chk('not os.environ.get("BOKGUON_FORWARDED_ALLOW", "").strip():' in _mg06_body,
    "  형제(Linux/gunicorn) 분기의 기존 검사는 그대로 남아 있다(회귀없음)")

print("\n[2] 실행 — 실제 manage.py check 를 이 자리(Windows)에서 그대로 돌린다")
chk(os.name == "nt", "  (전제) 이 검증 환경은 실제로 Windows다(os.name 모킹 불필요)", os.name)

_tmpdir = tempfile.mkdtemp(prefix="round432_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_ADMIN_IP_ALLOW"] = "127.0.0.1"   # 무관한 경고가 안 섞이게
sys.path.insert(0, HERE)


def _run_check():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M.cmd_check([])
    return buf.getvalue()


try:
    import db as DB
    DB.init_db()
    import manage as M

    os.environ["BOKGUON_ENV"] = "prod"
    os.environ["BOKGUON_BEHIND_PROXY"] = "1"

    print("\n[3] 실행 — BOKGUON_HOST 가 루프백이 아니면(0.0.0.0) 이제 실제로 잡힌다")
    os.environ["BOKGUON_HOST"] = "0.0.0.0"
    os.environ.pop("BOKGUON_FORWARDED_ALLOW", None)
    out1 = _run_check()
    chk("BOKGUON_HOST 가 루프백이 아닙니다" in out1,
        "★★★★★ Windows 에서 BOKGUON_HOST=0.0.0.0 이면 새 검사가 실제로 실패(✘)를 낸다"
        "(고치기 전엔 이 값 자체를 아예 안 봤다)", out1[-400:])
    chk("BOKGUON_FORWARDED_ALLOW" not in out1,
        "  Windows 경로에서는 gunicorn 전용 검사 문구가 아예 안 나온다"
        "(엉뚱한 변수를 언급하지 않는다)", out1[-400:])

    print("\n[4] 실행 — BOKGUON_HOST 를 비워도(기본값 0.0.0.0) 안전하다고 착각하지 않는다")
    os.environ.pop("BOKGUON_HOST", None)
    out2 = _run_check()
    chk("BOKGUON_HOST 가 루프백이 아닙니다" in out2,
        "★★★★ BOKGUON_HOST 를 아예 안 정해도(실제 기본값 0.0.0.0) 위험으로 잡는다",
        out2[-400:])

    print("\n[5] 실행 — BOKGUON_HOST 가 루프백이면(정상 배포) 더는 막히지 않는다"
          "(고치기 전엔 FORWARDED_ALLOW 가 비었다는 이유만으로 여기서 막혔다)")
    os.environ["BOKGUON_HOST"] = "127.0.0.1"
    os.environ.pop("BOKGUON_FORWARDED_ALLOW", None)
    out3 = _run_check()
    chk("BOKGUON_HOST 가 루프백이 아닙니다" not in out3,
        "★★★★★ 정상 루프백 설정이면 이 검사가 실패를 안 낸다(과잉차단 아님)",
        out3[-400:])
    chk("BOKGUON_FORWARDED_ALLOW" not in out3,
        "  gunicorn 전용 검사도 여전히 안 나온다(회귀없음)", out3[-400:])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행", f"{type(e).__name__} {e}")
finally:
    for k in ("BOKGUON_ENV", "BOKGUON_BEHIND_PROXY", "BOKGUON_HOST",
              "BOKGUON_FORWARDED_ALLOW", "BOKGUON_ADMIN_IP_ALLOW"):
        os.environ.pop(k, None)

# ============================================================
print("\n[6] 되돌리기 — 옛 코드(플랫폼 분기 없음)였다면 두 방향 다 틀렸는가")
print("    [round620 마이그레이션: 디스크 파일을 더는 안 건드림 — 되돌린")
print("     cmd_check() 본문을 독립 사본 네임스페이스(dict(vars(M)))에만")
print("     exec 한다(round618과 같은 기법). manage.py는 읽기 전용.]")
# ------------------------------------------------------------
MANAGE_PATH = os.path.join(HERE, "manage.py")
NEW_BLOCK = MANAGE_SRC[MANAGE_SRC.index("        # 프록시 뒤인데 신뢰 프록시가 비면"):
                       MANAGE_SRC.index("\n        if os.environ.get(\"BOKGUON_SEED_DEMO\"")]
OLD_BLOCK = '''        # 프록시 뒤인데 신뢰 프록시가 비면 client_ip 위조로 IP제한·레이트리밋이 무력화된다
        if os.environ.get("BOKGUON_BEHIND_PROXY") == "1" and \\
                not os.environ.get("BOKGUON_FORWARDED_ALLOW", "").strip():
            bad("BEHIND_PROXY=1 인데 BOKGUON_FORWARDED_ALLOW 가 비어 있습니다 "
                "(IP 위조로 접근통제가 뚫립니다)."); fails += 1
'''

try:
    chk(MANAGE_SRC.count(NEW_BLOCK) == 1, "  (준비) 되돌리기 대상 텍스트가 유일하게 식별된다")
    reverted_src = MANAGE_SRC.replace(NEW_BLOCK, OLD_BLOCK)
    chk(reverted_src != MANAGE_SRC, "  (준비) 되돌리기 텍스트가 실제로 달라졌다")

    #  되돌린 소스에서 cmd_check() 함수 전체를 AST로 뽑아, 실제 manage 모듈의
    #  독립 사본(dict(vars(M))) 네임스페이스에만 exec 한다 — ok/bad/warn/DB 등은
    #  그 사본에도 이미 들어 있으므로(얕은 복사) 그대로 정상 동작하고, manage.py
    #  파일도 이미 import 된 실제 M 모듈도 이 과정에서 전혀 안 바뀐다.
    _tree = ast.parse(reverted_src)
    _lines = reverted_src.splitlines(keepends=True)
    _fn_src = None
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "cmd_check":
            _fn_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
            break
    assert _fn_src, "되돌린 cmd_check() 함수 소스를 AST로 못 뽑음"
    chk(OLD_BLOCK in _fn_src and NEW_BLOCK not in _fn_src,
        "  (준비) 되돌린 함수 소스에 새 블록이 없고 옛 블록만 있다(되돌림 확인)")

    _ns = dict(vars(M))
    exec(compile(_fn_src, "<round432-reverted:cmd_check>", "exec"), _ns)

    def _chk_reverted():
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            _ns["cmd_check"]([])
        return buf.getvalue()

    os.environ["BOKGUON_ENV"] = "prod"
    os.environ["BOKGUON_BEHIND_PROXY"] = "1"
    #  ⚠ FORWARDED_ALLOW 는 '겉보기엔 정상'인 값을 채운다(gunicorn 기준으로는
    #    통과) — 그런데도 HOST 는 실제로 위험(0.0.0.0)하다는 게 이 시나리오의 핵심.
    os.environ["BOKGUON_HOST"] = "0.0.0.0"
    os.environ["BOKGUON_FORWARDED_ALLOW"] = "127.0.0.1"
    out_a = _chk_reverted()
    chk("BOKGUON_HOST" not in out_a,
        "★★★★★ 옛 코드(되돌림)는 BOKGUON_HOST=0.0.0.0(실제 위험)을 전혀 언급조차 안 한다"
        "(FORWARDED_ALLOW 가 겉보기에 정상이면 그대로 통과 — 인과관계 직접증명)",
        out_a[-500:])

    os.environ["BOKGUON_HOST"] = "127.0.0.1"
    os.environ.pop("BOKGUON_FORWARDED_ALLOW", None)
    out_b = _chk_reverted()
    chk("BOKGUON_FORWARDED_ALLOW" in out_b,
        "★★★★★ 옛 코드(되돌림)는 BOKGUON_HOST=127.0.0.1(안전한 배포)도 FORWARDED_ALLOW"
        "가 비었다는 이유만으로 불필요하게 막았다(과잉차단 — 인과관계 직접증명)",
        out_b[-500:])

    chk(io.open(MANAGE_PATH, encoding="utf-8").read() == MANAGE_SRC,
        "★★★★★ manage.py는 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다"
        "(되돌린 cmd_check()는 dict(vars(M)) 독립 사본에만 exec됨)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기 실행", f"{type(e).__name__} {e}")
finally:
    for _k in ("BOKGUON_ENV", "BOKGUON_BEHIND_PROXY", "BOKGUON_HOST", "BOKGUON_FORWARDED_ALLOW"):
        os.environ.pop(_k, None)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
