# -*- coding: utf-8 -*-
"""스캔 246라운드 회귀 — admin.js 설정화면 결함 2건(admin.js 설정·통계 화면
   Agent 병렬조사로 발견).

  [1] 리마인드 드롭다운이 키 없는(새 DB) 상태를 잘못 표시·저장했다 —
      String(undefined) 가 어떤 <option> 과도 안 맞아 브라우저가 첫 옵션
      ('15분 간격')을 조용히 선택 상태로 보여주는데, 실제 서버 기본값
      (_remind_minutes 의 default=30)은 30분이다. saveSettings() 는 건드리지
      않은 필드도 매번 그대로 다시 보내므로, 화면을 열고 다른 설정만 고쳐
      저장해도 이 '15분'이 그대로 DB 에 박혀 리마인드 주기가 조용히
      반토막났다. 바로 옆 fee_vat_included 는 같은 문제를 ?? 로 이미 막고
      있었다 — 프론트(?? 기본값)와 백엔드(migrate() 백필) 양쪽에서 고친다.

  [2] 설정·감사로그 메뉴의 등급 문턱(2)이 실제 두 하위기능 어느 쪽과도 안
      맞았다 — 입찰·정산 정책 저장은 최고관리자(3) 전용인데 중간관리자(2)도
      메뉴를 열어 폼을 다 채운 뒤에야 403 을 만났고, 감사 로그는 누구나
      (require_admin, 1) 볼 수 있는데 하위관리자(1)는 메뉴 자체가 안 보여
      못 봤다. 메뉴 문턱을 감사 로그 기준으로 낮추고, 정책 패널만 형제
      (VIEWS.admins)처럼 스스로 가리도록 수정.

      python test_scan_round246_fixes.py
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
DB_SRC = read("db.py")

print("=" * 72)
print("  스캔 246라운드 회귀 — 설정화면 리마인드 기본값 오판 + 등급문턱 불일치")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = ADMIN_JS.index("VIEWS.set = async ()")
i1 = ADMIN_JS.index("\nasync function ", i0)
set_body = ADMIN_JS[i0:i1]
chk("opts(s.reminder_photo ?? '30분 간격'" in set_body,
    "★★★★ 사진검수 리마인드가 ?? 로 실제 서버 기본값(30분)을 반영한다")
chk("opts(s.reminder_payment ?? '30분 간격'" in set_body,
    "★★★★ 지급검수 리마인드도 마찬가지다")
chk('("reminder_photo", "30분 간격")' in DB_SRC and '("reminder_payment", "30분 간격")' in DB_SRC,
    "★★★ db.py migrate() 백필 목록에도 두 키가 추가됐다(새 DB 에서도 값이 실존)")

chk("gate = {admins:3, insurers:3};" in ADMIN_JS,
    "★★★★ applyRoleMenus() 의 메뉴 문턱에서 set 이 빠졌다(더 낮은 감사로그 기준으로 통일)")
chk("myRank() >= 3 ? `<div class=\"panel\">" in set_body,
    "★★★★ 입찰·정산 정책 패널 자체가 등급3 미만이면 스스로 가려진다")
_i_ternary = set_body.index("myRank() >= 3")
_i_ternary_end = set_body.index("}", set_body.index("` : `", _i_ternary)) + 1
_i_audit_header = set_body.index("감사 로그 <small>모든")
chk(_i_audit_header > _i_ternary_end,
    "STEP 감사 로그 패널(실제 헤더)은 그 삼항연산자가 끝난 뒤 — 즉 무조건 "
    "렌더링되는 자리에 있다(등급과 무관하게 항상 보인다)")

# ============================================================
print("\n[2] 실행 — Node 로 리마인드 옵션 렌더링을 실제 평가")
# ------------------------------------------------------------
HARNESS_OPTS = r'''
const opts = (cur, arr) => arr.map(o=>`<option ${String(cur)===String(o)?'selected':''}>${o}</option>`).join('');
function pick(html){
  const m = html.match(/<option selected>([^<]+)<\/option>/);
  if (m) return m[1];
  const f = html.match(/<option[^>]*>([^<]+)<\/option>/);
  return f ? f[1] : null;
}
const CHOICES = ['15분 간격','30분 간격','1시간 간격','2시간 간격'];
const out = {
  missing: pick(opts(undefined ?? '30분 간격', CHOICES)),
  explicit15: pick(opts('15분 간격' ?? '30분 간격', CHOICES)),
  explicit1h: pick(opts('1시간 간격' ?? '30분 간격', CHOICES)),
};
console.log(JSON.stringify(out));
'''
try:
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(HARNESS_OPTS)
        harness_path = f.name
    try:
        r = subprocess.run(["node", harness_path], capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=30)
    finally:
        try:
            os.unlink(harness_path)
        except OSError:
            pass
    chk(r.returncode == 0, "STEP Node 하네스가 예외 없이 끝까지 실행된다", r.stdout + r.stderr)
    out = json.loads((r.stdout or "{}").strip().splitlines()[-1]) if r.returncode == 0 else {}
    chk(out.get("missing") == "30분 간격",
        "★★★★ 키가 없는(undefined) 경우 이제 '30분 간격'이 선택 상태로 뜬다"
        "(고치기 전엔 '15분 간격'이 조용히 선택된 것처럼 보였다)", out)
    chk(out.get("explicit15") == "15분 간격" and out.get("explicit1h") == "1시간 간격",
        "STEP 실제로 저장된 값(15분·1시간)은 그 값 그대로 정확히 표시된다(회귀 없음)",
        out)
except FileNotFoundError:
    chk(False, "STEP node 실행 파일을 찾을 수 없음(PATH 확인 필요)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드246 [2] 실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — Flask 실서버로 새 DB 에서 리마인드 값이 실존하는지 확인")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round246_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()

    conn = DB.get_db()
    row = conn.execute(
        "SELECT key, value FROM settings WHERE key IN ('reminder_photo','reminder_payment')").fetchall()
    conn.close()
    found = {r["key"]: r["value"] for r in row}
    chk(found.get("reminder_photo") == "30분 간격" and found.get("reminder_payment") == "30분 간격",
        "★★★★ 새로 초기화된 DB 에도 두 키가 실제로 '30분 간격'으로 채워져 있다"
        "(고치기 전엔 이 키들이 아예 없어 화면이 undefined 를 받았다)", found)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드246 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
