# -*- coding: utf-8 -*-
"""스캔 36라운드 회귀 — 저장형 XSS(admin.js 2곳 · insurer_portal.html 2곳).

  조사 에이전트가 ~160개 렌더 지점 중 esc() 이스케이프가 빠진 4곳을 찾았다.
  전부 같은 모양: 협력사가 스스로 입력하는 자유텍스트(업체명·접수번호 등)가
  서버를 거쳐 그대로 돌아와 `toast()`(innerHTML) 에 꽂힌다 — 형제 호출부는
  이미 esc() 를 쓰는데 이 네 곳만 빠져 있었다(형제 자리 누락 패턴).

  ① admin.js:2927 — 재경매 전체마감 낙찰 업체명 (형제 2939는 이미 esc 사용)
  ② admin.js:4272 — 출동 직접배정 성공 메시지(업체명 포함) — **평상시 성공 경로**
  ③ insurer_portal.html:694 — 사건 등록 응답의 접수번호(보험사가 직접 입력 가능)
  ④ insurer_portal.html:1038 — 1차합의 승인 충돌 오류의 담당업체명(타 협력사 이름 노출)

  이 회귀는 두 단으로 증명한다: (a) 실제 파일의 esc() 호출부를 그대로 뽑아
  Node 로 진짜 실행해 실제 결함 페이로드가 무력화되는지, (b) ②는 서버까지
  왕복시켜(가짜 세션으로 실제 라우트 호출) 원본 페이로드가 무방비로 흘러오는
  전제 자체도 실측 확인.

      python test_scan_round36_fixes.py
"""
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADMIN_JS = read("static/admin.js")
INSURER_HTML = read("templates/insurer_portal.html")

print("═" * 72)
print("  스캔 36라운드 회귀 — 저장형 XSS 4곳(admin.js·insurer_portal.html)")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 고친 자리엔 esc() 가 있고, 옛 무방비 형태는 없는가")
# ──────────────────────────────────────────────────────────────
FIXED_1 = "toast(`${esc(r.awarded)} 낙찰 (${won(r.amount)}원)`); closeModal(); VIEWS.changeorders();"
OLD_1 = "toast(`${r.awarded} 낙찰 (${won(r.amount)}원)`); closeModal(); VIEWS.changeorders();"
FIXED_2 = "closeModal(); toast(esc(r.message)); VIEWS.dispatch();"
OLD_2 = "closeModal(); toast(r.message); VIEWS.dispatch();"
FIXED_3A = "`사건 <b>${esc(r.case_no)}</b> 접수 완료"
FIXED_3B = "`사건 <b>${esc(r.case_no)}</b> 등록 완료"
#  [라운드477] faDecide()의 catch 분기가 closeModal·reload 호출을 더 받으며
#    한 줄짜리 옛 형태가 아니게 됐다 — 이 회귀가 지키려는 보안 속성(esc()로
#    감싸는 것) 자체는 그대로이므로, 정확히 그 호출 문자열만 확인한다
#    (round466의 test_scan_round154_fixes.py가 세운 방식과 동일).
FIXED_4 = "toast(esc(e.message))"

chk(FIXED_1 in ADMIN_JS, "① admin.js 재경매낙찰 — esc(r.awarded) 로 고쳐졌다")
chk(OLD_1 not in ADMIN_JS, "① 옛 무방비 형태가 남아있지 않다")
chk(FIXED_2 in ADMIN_JS, "② admin.js 직접배정 — esc(r.message) 로 고쳐졌다")
chk(OLD_2 not in ADMIN_JS, "② 옛 무방비 형태가 남아있지 않다")
chk(FIXED_3A in INSURER_HTML and FIXED_3B in INSURER_HTML,
    "③ insurer_portal.html 사건등록 — 접수번호 두 분기 모두 esc() 로 고쳐졌다")
chk(FIXED_4 in INSURER_HTML, "④ insurer_portal.html 1차합의 오류 — esc(e.message) 로 고쳐졌다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실제 파일의 esc() 호출부를 Node 로 그대로 실행해 무력화되는가")
# ──────────────────────────────────────────────────────────────
import re as _re
_esc_def = _re.search(r"const esc = s => .*;", ADMIN_JS)
chk(bool(_esc_def), "★ admin.js 에서 esc() 정의를 뽑았다")
ESC_DEF = _esc_def.group(0) if _esc_def else ""

PAYLOAD = '<img src=x onerror=window.__XSS_MARK=1>'

node_script = f"""
{ESC_DEF}
function won(n){{ return String(n); }}
let CAPTURED = [];
function toast(html){{ CAPTURED.push(html); }}
function closeModal(){{}}
const VIEWS = {{ changeorders(){{}}, dispatch(){{}} }};

// ① — 실제 admin.js 2927줄 그대로
{{
  const r = {{ awarded: {json.dumps(PAYLOAD)}, amount: 100000 }};
  {FIXED_1}
}}
// ② — 실제 admin.js 4272줄 그대로
{{
  const r = {{ message: {json.dumps(PAYLOAD + "에 직접 배정했습니다.")} }};
  {FIXED_2}
}}
// ③ — 실제 insurer_portal.html 694-696줄 그대로 (두 분기)
{{
  const r = {{ no_photo: true, case_no: {json.dumps(PAYLOAD)}, matched: 5 }};
  toast(r.no_photo
    ? `사건 <b>${{esc(r.case_no)}}</b> 접수 완료 — 사진 없는 사고로 접수되어, 인근 업체 출동으로 현장 사진을 먼저 확보합니다`
    : `사건 <b>${{esc(r.case_no)}}</b> 등록 완료 — 시행사 <b>${{r.matched}}곳</b>에 입찰 공고가 발송되었습니다`);
}}
// ④ — 실제 insurer_portal.html 1038줄 그대로
{{
  const e = {{ message: {json.dumps("이미 다른 방식으로 진행됨 · 담당 " + PAYLOAD)} }};
  try {{ throw e; }} catch(e) {{ toast(esc(e.message)); }}
}}

console.log(JSON.stringify(CAPTURED));
"""

_tmpjs = os.path.join(tempfile.mkdtemp(prefix="xssjs_"), "check.js")
io.open(_tmpjs, "w", encoding="utf-8").write(node_script)
try:
    r = subprocess.run(["node", _tmpjs], capture_output=True, text=True, encoding="utf-8", timeout=20)
    chk(r.returncode == 0, "★ Node 실행이 정상 종료한다", r.stdout + r.stderr)
    captured = json.loads(r.stdout.strip().splitlines()[-1]) if r.returncode == 0 else []
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ Node 실행", f"{type(e).__name__} {e}")
    captured = []
finally:
    import shutil
    shutil.rmtree(os.path.dirname(_tmpjs), ignore_errors=True)

if len(captured) == 4:
    chk("<img" not in captured[0] and "&lt;img" in captured[0],
        "① 페이로드가 무력화됐다(라벨: 재경매낙찰)", captured[0])
    chk("<img" not in captured[1] and "&lt;img" in captured[1],
        "② 페이로드가 무력화됐다(라벨: 직접배정)", captured[1])
    chk("<img" not in captured[2] and "&lt;img" in captured[2] and "<b>" in captured[2],
        "③ 페이로드는 무력화되고 의도된 <b> 태그는 그대로 살아있다", captured[2])
    chk("<img" not in captured[3] and "&lt;img" in captured[3],
        "④ 페이로드가 무력화됐다(라벨: 1차합의 오류)", captured[3])
else:
    chk(False, "★★★ Node 캡처 4건을 못 받았다", captured)

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — ②(직접배정)는 서버까지 왕복시켜 원본 결함 전제를 재확인")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="xssdb_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_OTP_POLICY"] = "off"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,region,major) "
        "VALUES(?,'시공사','활성','서울','금속')", (PAYLOAD,)).lastrowid
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,insurer_id,category,region) "
        "VALUES('검증-XSS-36','접수',1,'금속','서울')").lastrowid
    conn.commit()
    conn.close()

    import app as A
    client = A.app.test_client()
    _tok = "regress-round36-csrf-token"
    with client.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"
        sess["_csrf"] = _tok

    resp = client.post(f"/api/cases/{cid}/dispatch/assign",
                        json={"partner_id": pid, "reason": "회귀검증용 배정"},
                        headers={"X-CSRF-Token": _tok})
    data = resp.get_json()
    chk(resp.status_code == 200, "★ 직접배정 라우트가 정상 처리한다", data)
    chk(data.get("ok") is True and PAYLOAD in (data.get("message") or ""),
        "★★★ API 응답은 페이로드를 그대로 돌려준다(서버 계층에서 이스케이프하면 안 됨"
        " — 감사로그·알림톡 등 다른 용도에 HTML 엔티티가 섞이면 안 되므로)",
        data.get("message"))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 직접배정 서버 왕복 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_OTP_POLICY", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
