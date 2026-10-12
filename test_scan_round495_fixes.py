# -*- coding: utf-8 -*-
"""스캔 495라운드 회귀 — manage.py cmd_prune_personal()(개인정보 파기,
처리방침 제3조 이행)이 happy_calls(해피콜 기록)를 통째로 빠뜨리던 결함.

feedback(응대내용)은 상담원이 통화 중 피해자가 밝힌 이름·주소·불만 등을
그대로 받아 적는 자유텍스트라(app.py api_happy_call_add), 버킷③이 지우는
cases.victim_name/victim_phone과 같은 성격의 개인정보를 담을 수 있는데,
이 함수 298줄 어디에도 "happy_calls"가 등장하지 않았다 — 사건 쪽 이름·
연락처를 파기한 뒤에도 해피콜 화면(GET /api/happy-calls, h.* 그대로
반환)에서는 그 원문이 영원히 남아 있었다.

⚠ manage.py는 app.py가 import하는 모듈이 아니라 독립 CLI라서, 이 라운드는
  app.py/서버 재기동·BUILD_HASH 로테이션이 필요 없다(라운드475·482와
  같은 예외 — manage.py-class 변경).
"""
import ast
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 495라운드 회귀 — 개인정보 파기에서 해피콜 기록 누락")
print("=" * 72)

MANAGE_PATH = os.path.join(HERE, "manage.py")
MANAGE_SRC = io.open(MANAGE_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 세 지점을 각각 독립적으로 추출(서로 안 겹침)")
# ──────────────────────────────────────────────────────────────
#  블록A: 새 버킷⑥ 전체(순수 삽입, 원본코드 없음 — 통짜 제거로 되돌림)
_a = MANAGE_SRC.find('\n        # ⑥ **해피콜 기록**')
_marker_a = '               + ("(파기 예정)" if dry else "파기") + " — 하자담보 만료 후")\n'
_b = MANAGE_SRC.find(_marker_a, _a)
_b = _b + len(_marker_a) if _a > 0 and _b > _a else -1
BLOCK_A = MANAGE_SRC[_a:_b] if _a > 0 and _b > _a else ""

#  블록B: total 합산식(기존 줄 수정 — 원본 문자열로 치환해 되돌림)
CUR_B = "        total = n1 + n2 + n3 + n3b + n3c + n3d + n4 + n4b + n4c + n5 + n6\n"
ORIG_B = "        total = n1 + n2 + n3 + n3b + n3c + n3d + n4 + n4b + n4c + n5\n"

#  블록C: DB.log 문구 두 줄(기존 줄 수정 — 원본 문자열로 치환해 되돌림)
CUR_C = ('                   f"종료사건 조회링크 {n4c} · 하자보수기록 {n5} · 해피콜기록 {n6} "\n'
         '                   f"(기준: 문의 1년 / 계좌 퇴출·미지급없음 / 피해자·해피콜 하자담보 만료 / "\n')
ORIG_C = ('                   f"종료사건 조회링크 {n4c} · 하자보수기록 {n5} "\n'
          '                   f"(기준: 문의 1년 / 계좌 퇴출·미지급없음 / 피해자 하자담보 만료 / "\n')

chk(bool(BLOCK_A) and "happy_calls" in BLOCK_A, "블록A(버킷⑥)를 찾았다")
chk(MANAGE_SRC.count(BLOCK_A) == 1, "블록A가 소스에 유일하다", MANAGE_SRC.count(BLOCK_A) if BLOCK_A else 0)
chk(MANAGE_SRC.count(CUR_B) == 1, "블록B(total 합산식)가 소스에 유일하다", MANAGE_SRC.count(CUR_B))
chk(MANAGE_SRC.count(CUR_C) == 1, "블록C(로그 문구)가 소스에 유일하다", MANAGE_SRC.count(CUR_C))
chk("happy_calls" not in ORIG_B + ORIG_C, "원본 대조 문자열에는 happy_calls가 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 서브프로세스 실행 — cmd_prune_personal() 직접 호출")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드657] 이 워커는 내용이 결정적이라 round626이 형제(test_scan_
#    round494_worker.py)에 이미 적용한 것과 같은 이유로 정적 파일로 둔다 —
#    매 배터리 실행마다 저장소 루트에 다시 쓰지 않는다(round656 핸드오프가
#    지목한 잔여 항목). 이 파일 자신은 수정 대상이 아니다(worker 파일 참고).
WORKER = os.path.join(HERE, "test_scan_round495_worker.py")


def run(extra_args=None):
    r = subprocess.run([sys.executable, "-u", WORKER] + (extra_args or []), capture_output=True,
                        text=True, encoding="utf-8", timeout=60)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


try:
    out = run()
    chk(out["rc"] == 0, "cmd_prune_personal()이 정상 종료(exit 0)한다", out)
    chk(out["happy_call"]["feedback"] is None and out["happy_call"]["called_by"] is None,
        "★★★★★ 새 코드: 해피콜 응대내용·상담원이 NULL로 파기된다"
        "(개인정보 원문이 더 이상 이 표에 남지 않음)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — 세 지점을 되돌린 뒤 cmd_prune_personal()만")
    print("    독립 사본 네임스페이스에서 재구성해 호출(manage.py 파일은 안 건드림)")
    # ──────────────────────────────────────────────────────────
    assert BLOCK_A, "블록A를 못 뽑아 되돌림-증명을 진행할 수 없다"
    reverted = (MANAGE_SRC.replace(BLOCK_A, "")
                          .replace(CUR_B, ORIG_B)
                          .replace(CUR_C, ORIG_C))
    assert reverted != MANAGE_SRC, "되돌림 치환이 실제로 안 먹었다"

    #  되돌린 "전체 파일" 문자열에서 cmd_prune_personal() 함수 경계만 AST로
    #  정확히 뽑아낸다 — 실제 manage.py 파일은 이 과정에서 한 번도 안 열린다.
    _tree = ast.parse(reverted)
    _lines = reverted.splitlines(keepends=True)
    _reverted_fn_src = None
    for _node in ast.walk(_tree):
        if isinstance(_node, ast.FunctionDef) and _node.name == "cmd_prune_personal":
            _reverted_fn_src = "".join(_lines[_node.lineno - 1:_node.end_lineno])
            break
    assert _reverted_fn_src, "되돌린 cmd_prune_personal() 함수 소스를 AST로 못 뽑음"

    #  워커 서브프로세스로 그 함수 소스만 스크래치 임시파일에 건네준다(단순
    #  프로세스간 데이터 전달 수단일 뿐 — manage.py를 대신하는 파일이 아니다).
    _fn_fd, _fn_path = tempfile.mkstemp(suffix=".py", prefix="r495_reverted_fn_")
    os.close(_fn_fd)
    io.open(_fn_path, "w", encoding="utf-8").write(_reverted_fn_src)
    try:
        out2 = run([_fn_path])
        chk(out2["rc"] == 0, "옛 코드(되돌림)도 정상 종료한다(다른 버킷은 그대로 작동)", out2)
        chk(out2["happy_call"]["feedback"] is not None and out2["happy_call"]["called_by"] is not None,
            "★★★★★ 옛 코드(되돌림): 해피콜 응대내용·상담원이 파기되지 않고 원문 그대로 "
            "남는다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", out2)
        chk("홍길동" in (out2["happy_call"]["feedback"] or ""),
            "★★★★★ 옛 코드(되돌림): 원문에 있던 개인정보(이름 등)가 그대로 노출된 채 남는다",
            out2["happy_call"])
        chk(out2["case"]["victim_name"] is None,
            "대조군: 버킷③(사건 피해자정보)은 이번 라운드와 무관하게 여전히 정상 파기된다"
            "(회귀 없음)", out2)
    finally:
        try:
            os.remove(_fn_path)
        except OSError:
            pass
    chk(io.open(MANAGE_PATH, encoding="utf-8").read() == MANAGE_SRC,
        "★★★★★ manage.py는 이 되돌림-증명 내내 디스크에서 전혀 건드려지지 않았다"
        "(되돌린 함수는 dict(vars(M)) 독립 사본에만 exec됨)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
