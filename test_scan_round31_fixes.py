# -*- coding: utf-8 -*-
"""스캔 31라운드 회귀 — 검색어 와일드카드 이스케이프 · /api/me 3형제 생존 확인.

  ① 검색어의 %·_ 가 LIKE 와일드카드로 그대로 새었다 — search_filters·
     _partner_filter·_case_filter·_settle_filter·_activity_filter 다섯 곳
     전부 ESCAPE 절이 없어, 감사로그에서 "9%"(수수료 9% 검색)를 찾으면
     패턴이 `%9%%` 가 되어 "9 를 포함하는 모든 것"으로 넓게 걸렸다(실측).
     _like_escape() 를 만들어 _kw_like_clause(세 자리 공용)·_settle_filter·
     _activity_filter 전부에 적용했다.

  ② /api/me·/api/partner/me·/api/insurer/me 만 _account_alive() 를 안 불러,
     삭제·정지된 계정도 이 세 라우트에서는 계속 200 + 새 CSRF 를 받았다 —
     다른 모든 관문의 "행 없음/차단 → 401" 계약과 어긋났다.
     ⚠ 이 항목의 실행 회귀는 test_session_liveness.py 의 [1]·[2]·[2-4] 에
       있다(그 파일이 이미 세션 생존 검사를 갖고 있어 같은 곳에 모았다) —
       여기서는 소스 배선만 다시 확인한다.

  ③ (후속 전수훑기, 2026-08-21) ①을 고친 뒤 app.py 전체에서 "LIKE ?" 를
     다시 훑어보니 자유텍스트 검색인데 _kw_like_clause 를 안 쓰는 자리가
     네 곳 더 있었다 — api_contacts(연락처 목록)·api_outbox(발송대기함)·
     _onboard_where(협력사 온보딩)·api_license_survey(건설업 등록 전수조사).
     (내부에서 만든 case_no 로 감사로그를 찾는 자리 3곳과, 드롭다운으로만
     채워지는 캠페인 수신자 필터는 자유텍스트가 아니라서 그대로 뒀다 —
     과잉 수정 아님.) 전부 같은 공용 함수로 옮겼다.

      python test_scan_round31_fixes.py
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

print("═" * 72)
print("  스캔 31라운드 회귀 — 검색어 와일드카드 이스케이프 · /api/me 생존 확인")
print("═" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 다섯 자리가 전부 이스케이프를 쓰는가")
# ──────────────────────────────────────────────────────────────
chk("def _like_escape(s):" in APP, "★ 공용 이스케이프 함수를 찾았다")
chk("_kw_like_clause(" in APP and "ESCAPE '\\\\'" in slice_by_anchor(
    APP, "def _kw_like_clause(kw, cols):", "\n\n\n"),
    "★★★ _kw_like_clause 가 ESCAPE 절을 쓴다(search_filters·_partner_filter·"
    "_case_filter 세 곳 공용 — 실측 결함 재현·수정 확인)")

_sf = slice_by_anchor(APP, "def _settle_filter(args):", "\ndef ")
chk("_like_escape(" in _sf and "ESCAPE" in _sf,
    "★★ _settle_filter 도 이스케이프를 쓴다", bool(_sf))

_af = slice_by_anchor(APP, "def _activity_filter(args):", "\ndef ")
chk("_like_escape(" in _af and _af.count("ESCAPE") >= 2,
    "★★ _activity_filter 도 이스케이프를 쓴다(q·actor 두 자리 다)",
    f"ESCAPE 개수={_af.count('ESCAPE')}")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 리터럴 %·_ 가 더 이상 와일드카드로 새지 않는가")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="escape_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "esc.db")
sys.path.insert(0, HERE)
try:
    import db as DB
    import app as A
    DB.init_db()
    conn = DB.get_db()

    class _Args(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)

    #  ★★★ 결정적 재현 — 실제 %가 들어간 값과, 접두어만 같고 %는 없는 값을
    #    함께 심는다. 이스케이프가 없으면 "WCARD%" 검색이 "WCARDXYZ"까지
    #    와일드카드로 걸러낸다(둘 다 걸리면 결함).
    conn.execute("INSERT INTO activity_log(actor, action, detail, created_at) "
                 "VALUES('WCARD%REAL','검증','검증',datetime('now'))")
    conn.execute("INSERT INTO activity_log(actor, action, detail, created_at) "
                 "VALUES('WCARDXYZ','검증','검증',datetime('now'))")
    conn.commit()

    where, p, limit = A._activity_filter(_Args(actor="WCARD%"))
    rows_ = conn.execute(f"SELECT actor FROM activity_log{where}", p).fetchall()
    found = sorted(r[0] for r in rows_)
    chk(found == ["WCARD%REAL"],
        "★★★ _activity_filter — 리터럴 %만 있는 것만 걸린다(WCARDXYZ 는 안 걸림)",
        found)

    #  _settle_filter 도 실제 실행으로 확인 — ESCAPE 절이 SQL 오류 없이 도는가
    conn.execute("""INSERT INTO settlements(case_no, insurer, partner_name, amount,
                                             fee, payout, is_demo, created_at)
                     VALUES('ST%TEST','검증보험','검증업체',1000,100,900,0,
                            datetime('now','+9 hours'))""")
    conn.commit()
    where2, p2 = A._settle_filter(_Args(q="ST%"))
    n2 = conn.execute(
        "SELECT COUNT(*) FROM settlements s LEFT JOIN cases c ON c.id=s.case_id WHERE "
        + " AND ".join(where2), p2).fetchone()[0]
    chk(n2 == 1, "★★ _settle_filter 도 에러 없이 실행되고 리터럴 %만 찾는다", n2)

    #  가운뎃점 정규화가 이스케이프 추가로 깨지지 않았는지(회귀 방지)
    conn.execute("INSERT INTO partners(name,partner_type,major,category,region,status) "
                 "VALUES('검증아래아','시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕','서울','활성')")
    conn.commit()
    where3, p3 = A._partner_filter(_Args(q="금속·창호"))
    n3 = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE " + " AND ".join(where3) + " AND name=?",
        p3 + ["검증아래아"]).fetchone()[0]
    chk(n3 == 1, "★ 이스케이프 추가 후에도 가운뎃점 정규화는 그대로 살아있다"
        "(회귀 방지)", n3)

    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 이스케이프 실측", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)

# ══════════════════════════════════════════════════════════════
print("\n[3] /api/me 3형제 — 소스 배선(실행 회귀는 test_session_liveness.py)")
# ──────────────────────────────────────────────────────────────
for name, marker in (
    ("api_me", '@app.get("/api/me")\ndef api_me():\n    if session.get("admin"):\n        '
               '#  ⚠ 실측'),
    ("api_partner_me", '@app.get("/api/partner/me")\ndef api_partner_me():\n'
                       '    if session.get("partner_id"):\n        alive, msg = _account_alive()'),
    ("api_insurer_me", '@app.get("/api/insurer/me")\ndef api_insurer_me():\n'
                       '    if session.get("insurer_id"):\n        alive, msg = _account_alive()'),
):
    chk(marker in APP, f"★★★ {name} 가 _account_alive() 를 부른다(실측 결함 재현·수정 확인)")

# ══════════════════════════════════════════════════════════════
print("\n[4] 후속 전수훑기 — 네 자리 추가 실행 확인(2026-08-21)")
# ──────────────────────────────────────────────────────────────
for label, cols_src in (
    ("api_contacts", '["name", "region", "major"])'),
    ("api_outbox", '["ntype", "target", "message"])'),
    ("_onboard_where", '["name", "region", "major"])'),
    ("api_license_survey", '["name", "biz_no", "region", "ceo"])'),
):
    chk(f"_kw_like_clause(" in APP and cols_src in APP,
        f"★ {label} 이(가) 공용 함수를 쓴다(정확한 컬럼 목록으로)", cols_src)

#  ⚠⚠ app.py 는 커넥션 추적 래퍼(_tracked_get_db)가 있어 **같은 프로세스 안에서
#    두 번째로 import/reload 하면 래퍼가 자기 자신을 또 감싸 무한재귀로 죽는다**
#    (실측: RecursionError, 이 섹션의 첫 시도가 이렇게 죽었다 — 결과가 빈 리스트로
#    조용히 보였을 뿐 진짜 원인은 500 이었다). 이 파일은 섹션 1~3 에서 이미
#    db·app 을 import 했으므로, 이 확인은 **완전히 새 프로세스**로 분리한다
#    (prove_*.py 스크립트들과 같은 원칙 — subprocess 로 진짜 새로 시작한다).
import subprocess
_CHILD = r'''
import os, sys
sys.path.insert(0, r"{HERE}")
import db as DB
DB.init_db()
import app as A

MARK = "GB%CHK"
conn = DB.get_db()
#  ⚠ init_db() 는 관리자 계정을 하나도 안 만든다(실측: manage.py check 가
#    "관리자 계정이 0개" 라고 한다) — round 31 의 _account_alive() 가 이제
#    /api/me 3형제뿐 아니라 require_admin 에도 물려 있어, 세션만 흉내 내고
#    실제 admins 행이 없으면 401 로 정확히 막힌다(이게 바로 그 결함 수정이
#    작동하는 증거이기도 하다) — 그래서 테스트용 행을 실제로 심는다.
conn.execute("INSERT INTO admins(username, password_hash, name, role) "
             "VALUES('admin', 'x', '검증', '최고관리자')")
conn.commit()
#  ⚠⚠ 디코이는 "GB" 다음에 % 자리를 다른 글자(Q)로 메운 값이어야 한다 —
#    이스케이프가 없으면 "%GB%CHK-REAL%" 의 가운데 %가 와일드카드라 "GBQCHK-REAL"
#    도 걸린다(Q 가 그 와일드카드 자리를 메운다). 접두어만 다른 값(예전에 썼던
#    "GB%CHKXYZ-DECOY")은 이스케이프 여부와 무관하게 애초에 "-REAL" 이 없어
#    둘 다 안 걸리므로 결함을 구분하지 못한다 — 이 파일의 첫 시도가 이 실수를
#    했다(되돌려도 실패로 안 잡혔다).
REAL = MARK + "-REAL"
DECOY = "GBQCHK-REAL"
conn.execute("INSERT INTO partners(name,partner_type,status,region,major,biz_no,ceo) "
             "VALUES(?,'시행사','활성','서울','금속·창호','111','대표')", (REAL,))
conn.execute("INSERT INTO partners(name,partner_type,status,region,major,biz_no,ceo) "
             "VALUES(?,'시행사','활성','서울','금속·창호','112','대표2')", (DECOY,))
conn.execute("INSERT INTO notifications(ntype,channel,target,message,audience_type,"
             "status,created_at) VALUES('검증','웹',?,'검증',NULL,'발송대기',datetime('now'))",
             (REAL,))
conn.execute("INSERT INTO notifications(ntype,channel,target,message,audience_type,"
             "status,created_at) VALUES('검증','웹',?,'검증',NULL,'발송대기',datetime('now'))",
             (DECOY,))
conn.commit()
conn.close()

client = A.app.test_client()
with client.session_transaction() as sess:
    sess["admin"] = "admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"


def items(resp):
    d = resp.get_json()
    if isinstance(d, list):
        return d
    for k in ("items", "data", "rows"):
        if isinstance(d.get(k), list):
            return d[k]
    return []


q = "GB%25CHK-REAL"   # URL 인코딩된 리터럴 '%' — 끝에 또 붙이지 않는다
fail = 0
for label, url, key in (
    ("api_contacts", f"/api/contacts?q={{q}}", "name"),
    ("api_outbox", f"/api/outbox?q={{q}}&status=발송대기", "target"),
    ("협력사 온보딩", f"/api/partner-onboarding?q={{q}}", "name"),
    ("건설업 등록 전수조사", f"/api/license-survey?q={{q}}&status=전체", "name"),
):
    r = client.get(url)
    candidates = {{REAL, DECOY}}
    found = sorted(x.get(key, "") for x in items(r) if x.get(key, "") in candidates)
    want = [REAL]
    ok = found == want
    fail += 0 if ok else 1
    print(("OK " if ok else "FAIL ") + f"{{label}}: {{found}} (기대 {{want}}, 상태 {{r.status_code}})")

conn = DB.get_db()
conn.execute("DELETE FROM partners WHERE name IN (?,?)", (REAL, DECOY))
conn.execute("DELETE FROM notifications WHERE target IN (?,?)", (REAL, DECOY))
conn.commit()
conn.close()
sys.exit(1 if fail else 0)
'''.format(HERE=HERE)

_tmpdir4 = tempfile.mkdtemp(prefix="escape4_")
_child_env = dict(os.environ, BOKGUON_DB_PATH=os.path.join(_tmpdir4, "e4.db"),
                  PYTHONIOENCODING="utf-8")
try:
    r = subprocess.run([sys.executable, "-c", _CHILD], capture_output=True, text=True,
                       encoding="utf-8", env=_child_env, cwd=HERE, timeout=60)
    print("  " + r.stdout.strip().replace("\n", "\n  "))
    if r.returncode != 0 and r.stderr.strip():
        print("  [자식 stderr]", r.stderr.strip()[-500:])
    for line in r.stdout.splitlines():
        if line.startswith("OK ") or line.startswith("FAIL "):
            ok = line.startswith("OK ")
            chk(ok, "★★★ " + line[3 if ok else 5:].split(":")[0]
                + " — 리터럴 % 만 걸린다(실측 결함 재현·수정 확인)", line)
    if r.returncode not in (0, 1):
        chk(False, "★★★ 후속 네 자리 실측(자식 프로세스 비정상 종료)",
            f"returncode={r.returncode}")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 후속 네 자리 실측", f"{type(e).__name__} {e}")
finally:
    import shutil
    shutil.rmtree(_tmpdir4, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
