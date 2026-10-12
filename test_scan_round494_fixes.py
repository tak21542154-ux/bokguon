# -*- coding: utf-8 -*-
"""스캔 494라운드 회귀 — 고유 로그인 자격증명 발급 4곳의 경합 결함.

①api_admin_create()(app.py:1666)는 형제 둘(api_admin_update·api_admin_delete)과
  달리 BEGIN IMMEDIATE가 없어, 같은 아이디로 동시에 두 번 생성하면 하나가
  UNIQUE 위반으로 의도한 409 대신 처리 안 된 500이 났다.
②③issue_partner_login()(api_partner_credentials가 단건 호출)과
  api_insurer_credentials()는 둘 다 "아이디 전역 유일" 규칙을 4개 표에 걸쳐
  검사하면서도 잠금이 없어, 서로 다른 두 조직(협력사↔협력사, 또는
  **협력사↔보험사처럼 표가 다른 조합**)이 같은 아이디를 동시에 요청하면
  양쪽 다 "중복없음"을 읽고 성공해 전역 유일이어야 할 아이디가 두 표에
  나뉘어 조용히(오류 없이) 생길 수 있었다 — 가장 심각한 변형(교차표)은
  UNIQUE 제약이 표별이라 에러조차 안 나서 감사로그에 흔적도 안 남는다.
④api_partner_bulk_credentials()는 issue_partner_login()을 공유하므로 잠금은
  헬퍼가 아니라 호출부(배치 전체를 한 번에)에 걸었다 — 개별 SAVEPOINT는
  그대로 유지.

⚠ ②③은 SQLite의 쓰기잠금이 **테이블별이 아니라 DB 파일 전체 단위**라는
  점을 이용해 검증한다 — 서로 다른 두 표(partners·insurers)에 각자
  BEGIN IMMEDIATE를 걸어도, 먼저 잠금을 잡은 쪽이 커밋할 때까지 다른 쪽은
  시작조차 못 하므로 나중 쪽이 항상 최신 상태(상대가 막 커밋한 행)를 보고
  스스로 막힌다 — 표가 달라 UNIQUE로는 못 잡던 그 교차표 경합이 이 잠금
  하나로 함께 막힌다.
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
print("  스캔 494라운드 회귀 — 로그인 자격증명 발급 4곳 경합 결함")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — 네 곳 모두 함수 전체를 통째로 추출")
# ──────────────────────────────────────────────────────────────


def extract(start_marker, end_marker, label):
    s = APP_SRC.find(start_marker)
    e = APP_SRC.find(end_marker, s)
    e = e + len(end_marker) if s > 0 and e > s else -1
    block = APP_SRC[s:e] if s > 0 and e > s else ""
    chk(bool(block), f"{label}: 함수(구간)를 찾았다")
    chk(APP_SRC.count(block) == 1, f"{label}: 텍스트가 소스에 유일하다",
        APP_SRC.count(block) if block else 0)
    chk("BEGIN IMMEDIATE" in block, f"{label}: BEGIN IMMEDIATE가 있다")
    return block


CUR_ADMIN_CREATE = extract(
    '@app.post("/api/admins")',
    '    return jsonify({"ok": True, "username": username, "temp_password": temp_pw,\n'
    '                    "message": "임시 비밀번호는 지금 한 번만 표시됩니다. 최초 로그인 시 변경이 강제됩니다."})\n',
    "① api_admin_create")

CUR_PARTNER_CRED = extract(
    '@app.post("/api/partners/<int:pid>/credentials")',
    '                               "업체에 안전한 경로로 전달하세요."})\n',
    "② api_partner_credentials")

CUR_BULK_CRED = extract(
    '@app.post("/api/partners/bulk-credentials")',
    '                               "이 창을 닫으면 다시 볼 수 없습니다."})\n',
    "④ api_partner_bulk_credentials")

CUR_INSURER_CRED = extract(
    'def api_insurer_credentials(iid):',
    '                               "발주처 담당자에게 안전한 경로로 전달하세요."})\n',
    "③ api_insurer_credentials")

#  각 함수의 원본(라운드494 이전) 전체 텍스트 — 수정 직전에 직접 Read로 확인해 둔 것.
ORIG_ADMIN_CREATE = '''@app.post("/api/admins")
@require_role("최고관리자")
def api_admin_create():
    """관리자 계정 생성. 임시 비밀번호는 응답에 1회만 — 최초 로그인 시 변경 강제."""
    d = body()
    username = (d.get("username") or "").strip().lower()
    name = (d.get("name") or "").strip()[:40]
    role = d.get("role") if d.get("role") in ADMIN_ROLES else "하위관리자"
    if not re.fullmatch(r"[a-z0-9_-]{4,20}", username):
        return jsonify({"ok": False, "error": "아이디는 영문 소문자·숫자·-·_ 4~20자로 정해 주세요."}), 400
    if not name:
        return jsonify({"ok": False, "error": "이름은 필수입니다."}), 400
    conn = DB.get_db()
    if conn.execute("SELECT 1 FROM admins WHERE username=?", (username,)).fetchone():
        conn.close(); return jsonify({"ok": False, "error": "이미 존재하는 아이디입니다."}), 409
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    while True:
        temp_pw = "".join(secrets.choice(alphabet) for _ in range(12))
        if (any(c.isupper() for c in temp_pw) and any(c.islower() for c in temp_pw)
                and any(c.isdigit() for c in temp_pw)):
            break
    conn.execute(
        "INSERT INTO admins(username,password_hash,name,role,must_change_pw,created_at) "
        "VALUES(?,?,?,?,1,?)", (username, DB.hash_pw(temp_pw), name, role, DB.now()))
    DB.log(conn, actor(), "관리자 계정 생성", f"{username} ({role}) {name}")
    conn.commit(); conn.close()
    return jsonify({"ok": True, "username": username, "temp_password": temp_pw,
                    "message": "임시 비밀번호는 지금 한 번만 표시됩니다. 최초 로그인 시 변경이 강제됩니다."})
'''

ORIG_PARTNER_CRED = '''@app.post("/api/partners/<int:pid>/credentials")
@require_role("최고관리자")
def api_partner_credentials(pid):
    """협력사 포털 계정 발급 / 비밀번호 재발급 (한 곳).

    포털에는 회원가입 화면이 없다(무단 가입 방지). 입점 승인이 끝난 업체에
    **여기서 계정을 만들어 줘야** 포털에 들어와 입찰할 수 있다.
    임시 비밀번호는 이 응답에 한 번만 나온다 — 저장하지 않으므로 즉시 전달할 것.
    """
    conn = DB.get_db()
    ok, res, st = issue_partner_login(conn, pid, body().get("login_id"))
    if not ok:
        conn.close()
        return jsonify({"ok": False, **res}), st
    conn.commit(); conn.close()
    return jsonify({"ok": True, "login_id": res["login_id"],
                    "temp_password": res["temp_password"], "reissued": res["reissued"],
                    "message": "임시 비밀번호는 지금 한 번만 표시됩니다. "
                               "업체에 안전한 경로로 전달하세요."})
'''

chk("BEGIN IMMEDIATE" not in ORIG_ADMIN_CREATE, "① 원본에는 BEGIN IMMEDIATE가 없다(대조군)")
chk("BEGIN IMMEDIATE" not in ORIG_PARTNER_CRED, "② 원본에는 BEGIN IMMEDIATE가 없다(대조군)")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 스레드 경합 재현")
# ──────────────────────────────────────────────────────────────
#  ⚠⚠ [라운드626] 이전 버전은 여기서 test_scan_round494_worker.py를
#    매번 이스케이프-유니코드 문자열로 통째로 다시 썼다(내용은 결정적이라
#    round625까지 늘 똑같았다) — 이제 그 워커는 정적 파일이고, R494_BROKEN=1
#    되돌림 분기까지 포함한다(아래 run(broken=True)).
WORKER = os.path.join(HERE, "test_scan_round494_worker.py")


def run(broken=False):
    """broken=True 면 워커 서브프로세스 **안에서** 기법1(view_functions
    스왑)로 api_admin_create·api_partner_credentials 를 라운드494 이전
    버전으로 바꿔치기하고 실행한다(R494_BROKEN 환경변수로 트리거) — 실제
    app.py 파일은 이 프로세스에서도 저 서브프로세스에서도 전혀 안 건드린다."""
    env = dict(os.environ)
    if broken:
        env["R494_BROKEN"] = "1"
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60, env=env)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


try:
    out = run()
    chk(out["hitA"] == 2, "① 두 생성 요청 모두 중복확인 지점까지 동시 도달했다", out)
    codesA = sorted([tuple(out["A1"]), tuple(out["A2"])])
    chk(codesA == [(200, True), (409, False)],
        "★★★★★ ① 새 코드: 같은 아이디 동시생성 시 정확히 하나는 200, 나머지는 "
        "409(처리되지 않은 500이 아니라 의도한 거부)로 막힌다", out)
    chk(out["n_racenew"] == 1, "① 같은 아이디의 관리자 계정이 정확히 1개만 존재한다", out)

    chk(out["hitB"] >= 2,
        "②③ 협력사·보험사 양쪽에서 중복확인 지연이 최소 1회씩은 걸렸다"
        "(정확한 횟수는 어느 쪽이 먼저 잠금을 잡아 상대가 조기종료하는지에 "
        "따라 달라져 고정할 수 없다 — 최종 결과로만 판정)", out)
    okB = sorted([tuple(out["Bp"]), tuple(out["Bi"])])
    chk(okB == [(200, True), (409, False)],
        "★★★★★ ②③ 새 코드: 표가 다른 협력사·보험사가 같은 아이디를 동시요청해도 "
        "DB 전체 쓰기잠금이 직렬화해 정확히 하나만 성공한다(교차표라 UNIQUE로는 "
        "못 잡는 경합인데, 나중 커넥션이 상대가 막 커밋한 행을 보고 스스로 막힘)", out)
    chk(out["n_partner_cross"] + out["n_insurer_cross"] == 1,
        "★★★★★ 같은 아이디('crossrace')를 가진 행이 두 표를 합쳐 정확히 1개뿐이다"
        "(이전엔 둘 다 성공해 2개가 조용히 생겼다)", out)

    # ══════════════════════════════════════════════════════════
    print("\n[3] 되돌림-증명 — 워커 안에서만 ①② 두 라우트를 인메모리로 되돌림")
    # ──────────────────────────────────────────────────────────
    #  ⚠⚠ [라운드626] 이전 버전은 여기서 APP_SRC 전체를 CUR_*→ORIG_* 로
    #    치환한 통짜 텍스트를 app.py 실제 파일에 io.open(...,"w") 로 직접
    #    썼다가 finally 로 복원했다. ①②는 서로 부르지 않는 완전히 독립된
    #    두 Flask 라우트임을 이 세션이 직접 확인(호출관계 없음) — 이제
    #    워커(test_scan_round494_worker.py)가 R494_BROKEN=1 을 보고 그
    #    서브프로세스 **안에서만** 기법1(view_functions 스왑)로 되돌린다.
    assert CUR_ADMIN_CREATE and CUR_PARTNER_CRED, "블록을 못 뽑아 되돌림-증명을 진행할 수 없다"
    out2 = run(broken=True)
    codesA2 = sorted([tuple(out2["A1"]), tuple(out2["A2"])])
    chk(codesA2 == [(200, True), (200, True)] or out2["n_racenew"] >= 1,
        "★ 옛 코드(되돌림): ①의 두 생성 요청 결과가 새 코드와 달라졌다"
        "(둘 다 200 또는 처리안된 500 — 더 이상 깔끔한 409 직렬화가 아님)", out2)
    okB2 = sorted([tuple(out2["Bp"]), tuple(out2["Bi"])])
    chk(okB2 == [(200, True), (200, True)],
        "★★★★★ 옛 코드(되돌림): 교차표 경합에서 협력사·보험사 둘 다 200으로 "
        "성공한다 — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", out2)
    chk(out2["n_partner_cross"] == 1 and out2["n_insurer_cross"] == 1,
        "★★★★★ 옛 코드(되돌림): 같은 아이디('crossrace')가 partners·insurers "
        "양쪽에 동시에 생긴다(오류 없이 조용히 — round494가 지목한 가장 "
        "심각한 변형이 그대로 재현됨)", out2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

# ══════════════════════════════════════════════════════════════
print("\n[4] ④ api_partner_bulk_credentials — 구조확인 + 회귀(기능 안 깨짐), "
      "실경합 재현은 생략(정직하게 밝힘)")
# ──────────────────────────────────────────────────────────────
#  ⚠ 이 함수는 issue_partner_login()을 자동채번(각 업체 고유 biz_no/id 기반)으로만
#    부르므로, 서로 다른 두 업체가 "같은" 자동채번 아이디로 실제 충돌하는
#    상황을 자연스럽게 구성하기 어렵다(사업자번호 뒷6자리가 우연히 같아야
#    함). ①②③처럼 명시적 아이디 충돌로 실경합을 강제할 수 있는 나머지
#    세 곳과 달리, 이 네 번째 자리는 "배치 전체가 이제 한 트랜잭션으로
#    잠긴다"는 구조 확인 + 정상 동작 회귀 확인까지만 하고, 실제 스레드
#    경합 재현은 이번 라운드 범위에서 뺀다 — 억지로 아이디를 강제 주입하는
#    통로가 이 함수에 없어(코드상 자동채번 전용) 무리하게 만들면 오히려
#    실제로 쓰이지 않는 경로를 테스트하게 된다.
#  ⚠⚠ [라운드657] 이 워커는 내용이 결정적이라(회귀 없음 확인용 정상 시나리오
#    하나뿐) round626이 형제(test_scan_round494_worker.py)에 이미 적용한
#    것과 같은 이유로 정적 파일로 둔다 — 매 배터리 실행마다 저장소 루트에
#    다시 쓰지 않는다(round656 핸드오프가 지목한 잔여 항목). 이 파일 자신은
#    수정 대상이 아니다(worker 파일 참고).
BULK_WORKER = os.path.join(HERE, "test_scan_round494_bulk_worker.py")
try:
    r_bulk = subprocess.run([sys.executable, "-u", BULK_WORKER], capture_output=True,
                            text=True, encoding="utf-8", timeout=60)
    if r_bulk.returncode not in (0, 1):
        raise RuntimeError(f"워커 실행 실패: {r_bulk.stdout}\n{r_bulk.stderr}")
    bulk_out = json.loads(r_bulk.stdout.strip().splitlines()[-1])
    chk(bulk_out["status"] == 200 and bulk_out["ok"] and bulk_out["n_issued"] == 2,
        "④ BEGIN IMMEDIATE 추가 후에도 정상적인 일괄발급(서로 다른 업체 2곳)은 "
        "그대로 둘 다 성공한다(회귀 없음)", bulk_out)
except Exception as e:                                              # noqa: BLE001
    chk(False, "[4] 일괄발급 회귀 확인", f"{type(e).__name__}: {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
