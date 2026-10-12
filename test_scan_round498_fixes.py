# -*- coding: utf-8 -*-
"""스캔 498라운드 회귀 — 라운드497이 valid_biz_no() **내부**만 고치고
호출부 8곳의 **별도** 정규화(re.sub(r"\\D",...))는 그대로 둔 결함.

"ASCII 10자리 유효값 + 잉여 전각숫자 1개"(총 11자)를 넣으면, 이 함수
안에서는 잉여 전각 문자가 [^0-9]로 지워져 10자리 체크섬이 통과하지만
(True), 호출부 자신의 \\D 기반 정규화는 그 잉여 전각 문자를 못 지워
11자 그대로 저장·비교돼 — 라운드497이 막으려던 DUP_BIZNO 우회가 다른
입력 모양으로 재발한다. 실측: 이 입력은 라운드497 이전엔 길이불일치로
거부됐는데, 497의 수정이 뜻하지 않게 새로 통과시켰다(497 자신은
"전부 전각"·"10자리 유지한 채 1글자만 전각 치환" 두 경우만 검증해 이
"11자로 늘어나는" 조합을 놓쳤다).

이 테스트는 라운드498 자신의 기여(호출부 8곳의 정규화 통일)만 좁게
되돌린다 — valid_biz_no() 내부(라운드497의 기여)는 건드리지 않는다.

⚠⚠ [라운드626] 이전 버전은 [3]에서 app.py 실제 파일을
io.open(APP_PATH,"w").write(reverted) 로 디스크에 직접 썼다가 finally
에서 원본으로 복원했다 — 이제는 워커(test_scan_round498_worker.py)가
R498_BROKEN=1 환경변수를 보고 그 서브프로세스 **안에서만** 인메모리로
8곳(6곳은 기법1 view_functions 스왑, clean_public_form·_auto_login_id
2곳은 기법3 공유헬퍼 실모듈 __dict__ 직접 patch)을 되돌린다. app.py
실제 파일은 이 프로세스에서도 워커 서브프로세스에서도 전혀 안 쓴다.
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(c, n, d=""):
    (PASS if c else FAIL).append((n, d))
    print(("  [OK]   " if c else "  [FAIL] ") + n + ("" if c else f"   {d}"))


print("=" * 72)
print("  스캔 498라운드 회귀 — 사업자번호 호출부 정규화 미통일(잉여 전각숫자)")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 호출부 8곳이 전부 [^0-9]로 통일됐는지")
# ──────────────────────────────────────────────────────────────
PAIRS = [
    #  ⚠⚠ [라운드606] 이 자리가 round606에서 **별개 결함군**(raw d.get(...)를
    #    re.sub 문자열 인자에 그대로 넘기면 JSON 숫자에 TypeError)의 처방으로
    #    _s()가 덧씌워졌다 — [^0-9]→\\D 되돌림 대상은 이 라운드(498) 자신의
    #    기여만이므로 _s() 래핑은 cur·orig 양쪽에 그대로 남겨 둔다(round606의
    #    기여까지 되돌리면 이 테스트의 검증범위를 벗어난다).
    ('        _bz = re.sub(r"[^0-9]", "", _s(d.get("biz_no")))\n',
     '        _bz = re.sub(r"\\D", "", _s(d.get("biz_no")))\n'),
    ('        out["biz_no"] = re.sub(r"[^0-9]", "", out["biz_no"])\n',
     '        out["biz_no"] = re.sub(r"\\D", "", out["biz_no"])\n'),
    ('    biz = re.sub(r"[^0-9]", "", biz)\n',
     '    biz = re.sub(r"\\D", "", biz)\n'),
    ('            _biz = re.sub(r"[^0-9]", "", app_row.get("biz_no") or "")\n',
     '            _biz = re.sub(r"\\D", "", app_row.get("biz_no") or "")\n'),
    ('    biz = re.sub(r"[^0-9]", "", (p["biz_no"] or ""))\n',
     '    biz = re.sub(r"\\D", "", (p["biz_no"] or ""))\n'),
    #  ⚠⚠ [라운드608] round601~ 형제결함군(raw re.sub 3번째 인자가 JSON
    #    비문자열이면 TypeError로 500) 처방으로 두 호출부(api_partner_create의
    #    biz_no·api_partner_update의 d[f])가 _s()를 거치게 바뀌었다 — 이
    #    테스트가 되돌리는 [^0-9]→\D 축과는 독립적이라, cur·orig 양쪽에 _s()는
    #    그대로 남긴다(위 606 주석·497 테스트의 같은 원칙과 동일).
    ('    _biz = re.sub(r"[^0-9]", "", _s(d.get("biz_no")))\n',
     '    _biz = re.sub(r"\\D", "", _s(d.get("biz_no")))\n'),
    ('                d[f] = re.sub(r"[^0-9]", "", _s(d[f]))\n',
     '                d[f] = re.sub(r"\\D", "", _s(d[f]))\n'),
    ('            _bz = re.sub(r"[^0-9]", "", _bz)\n',
     '            _bz = re.sub(r"\\D", "", _bz)\n'),
]
for cur, orig in PAIRS:
    chk(APP_SRC.count(cur) == 1, f"호출부 지점이 소스에 유일하다: {cur.strip()}", APP_SRC.count(cur))

# bank_account(무관한 형제, 8015행 부근)는 이 라운드(498, [^0-9]→\D 통일)가
# 안 건드렸는지 — 과도한 replace_all 사고 방지.
#  ⚠⚠ [라운드608] 그 뒤 round608이 이 자리를 **별개 이유**(round601~
#    형제결함군 — d.get(...)가 truthy 비문자열이면 re.sub 3번째 인자에서
#    TypeError로 500)로 정당하게 고쳐 _s()가 덧씌워졌다. 여기서 지키려는
#    불변("498의 [^0-9] 통일이 이 무관한 형제까지 번지지 않았다")은 여전히
#    참이므로, 리터럴만 갱신한다.
chk('acct = re.sub(r"[^0-9]", "", _s(d.get("bank_account"))) if touch_acct else None' in APP_SRC,
    "★★ 무관한 형제(계좌번호 정규화)는 그대로다 — 이번 수정이 번지지 않았다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 서브프로세스 실행 — PATCH /api/partners/<id> (잉여 전각숫자 1개)")
# ──────────────────────────────────────────────────────────────
WORKER = os.path.join(HERE, "test_scan_round498_worker.py")


def run(broken=False):
    """broken=True 면 워커 서브프로세스 **안에서** 8곳을 되돌린 버전으로
    바꿔치기하고 실행한다(R498_BROKEN 환경변수로 트리거) — 실제 app.py
    파일은 이 프로세스에서도 저 서브프로세스에서도 전혀 안 건드린다."""
    env = dict(os.environ)
    if broken:
        env["R498_BROKEN"] = "1"
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


try:
    out = run()
    chk(out["status"] == 409 and out["code"] == "DUP_BIZNO",
        "새 코드: 잉여 전각숫자 1개 섞인 값이 정규화 후 중복으로 잡혀 409 DUP_BIZNO", out)
    chk(out["p2_status"] == "심사중" and out["p2_biz_no"] is None,
        "★★★★★ 새 코드: 거부된 업체는 활성화되지 않는다", out)
    chk(out["active_count"] == 1,
        "★★★★★ 새 코드: 활성 업체가 1곳뿐 — 잉여문자 변형으로도 중복 활성화가 없다", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — 라운드498 자신의 기여(호출부 8곳)만 워커 안에서 좁게 원복")
    # ──────────────────────────────────────────────────────────
    reverted_probe = APP_SRC
    for cur, orig in PAIRS:
        reverted_probe = reverted_probe.replace(cur, orig)
    assert reverted_probe != APP_SRC, "되돌림 치환이 실제로 안 먹었다"
    chk("[^0-9]" in reverted_probe, "되돌림 후에도 valid_biz_no() 내부(라운드497의 기여)는 그대로 [^0-9]다")

    out2 = run(broken=True)
    chk(out2["status"] == 200,
        "옛 코드(라운드497까지만): 잉여 전각숫자가 정규화 안 되고 그냥 통과된다", out2)
    chk(out2["p2_status"] == "활성", "★★★★★ 옛 코드: 업체가 실제로 활성화된다", out2)
    chk(out2["p2_biz_no_len"] == 11,
        "★★★★★ 옛 코드: 저장된 biz_no가 11자(잉여 전각숫자 포함) — ASCII로 "
        "정규화되지 않았다", out2)
    chk(out2["active_count"] == 2,
        "★★★★★ 옛 코드: 같은 실제 사업자번호로 활성 업체가 2곳 — 이 테스트가 "
        "라운드497 자신의 회귀테스트는 못 잡던 이 변형을 잡아낼 능력이 있음을 증명",
        out2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
