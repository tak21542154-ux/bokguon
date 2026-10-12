# -*- coding: utf-8 -*-
"""스캔 265라운드 회귀 — 주소좌표 백필(geocode_fill.py) 결함 2건
   (좌표계산 형제파일 감사 Agent 조사로 발견, 독립 재검증 후 수정).

  [1] rows_to_fill() 이 --target cases(또는 both) 에서 is_demo 를 안
      걸렀다 — 같은 파일의 형제 report() 는 COALESCE(is_demo,0)=0 을
      건다. 게다가 cases 쪽은 ORDER BY id DESC(최신 우선)라서, 데모
      직전에 만들어져 id 가 큰 데모 사건이 --limit 예산을 실제 사건보다
      먼저 먹어치울 수 있었다(예: limit=1 이면 데모 하나만 뽑혀 실제
      사건은 이번 실행에서 아예 조회조차 안 된다). partners 테이블은
      is_demo 컬럼 자체가 없어(db.py 마이그레이션 목록에 부재) 이
      결함의 영향을 안 받는다 — 그래서 필터는 cases 쪽 쿼리에만 추가했다.

  [2] fill() 의 conn.commit() 이 배치 전체가 끝난 뒤 단 한 번뿐이었다.
      최대 500건, 건당 최대 두 번의 외부 API 호출 + 0.35~0.7초 대기가
      들어가는 배치 도중 중단(Ctrl+C·터미널 종료·네트워크 예외)되면
      이미 찾아 둔 좌표가 전부 커밋 안 된 채 날아간다(데이터 훼손은
      아니다 — 재실행하면 같은 "좌표 없음" 행을 다시 고르지만, 이미 쓴
      API 호출·대기시간이 전부 낭비된다). 같은 위험(외부 네트워크 호출이
      들어간 반복문)을 가진 형제 collect_emails.py(229~235행)는 이미
      성공한 행마다 즉시 커밋한다 — 그 패턴을 그대로 따랐다.

      python test_scan_round265_fixes.py
"""
import io
import os
import secrets
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


GEOFILL_SRC = read("geocode_fill.py")

print("=" * 72)
print("  스캔 265라운드 회귀 — geocode_fill.py 데모오염·배치커밋유실")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = GEOFILL_SRC.index("def rows_to_fill(")
i1 = GEOFILL_SRC.index("\n\n\ndef ", i0)
rtf_body = GEOFILL_SRC[i0:i1]
_split = rtf_body.index('table == "partners"')
chk("AND COALESCE(is_demo,0)=0" in rtf_body[_split:],
    "★★★★★ rows_to_fill() 의 cases 쪽 쿼리가 데모 사건을 뺀다")
chk("is_demo" not in rtf_body[:_split],
    "STEP partners 쪽 쿼리는 그대로다(그 테이블엔 is_demo 컬럼 자체가 없다)")

i2 = GEOFILL_SRC.index("def fill(")
i3 = GEOFILL_SRC.index("\n\n\ndef ", i2)
fill_body = GEOFILL_SRC[i2:i3]
_upd_pos = fill_body.index("UPDATE {table} SET lat=?")
_after_upd = fill_body[_upd_pos:]
_next_commit = _after_upd.index("conn.commit()")
_next_done = _after_upd.index("done += 1")
chk(_next_commit < _next_done,
    "★★★★★ 좌표 UPDATE 직후(다음 행으로 넘어가기 전) 즉시 커밋한다"
    "(고치기 전엔 배치 전체가 끝나야만 커밋했다)")
#  ⚠⚠ [라운드302] round302 가 실패행 표식(_mark_failed, 그 안에 자기 커밋을
#    가진 헬퍼)을 추가해 커밋 지점이 하나 더 늘었다 — 세 곳(행마다 성공
#    커밋·실패행 표식 커밋·마지막 감사로그 커밋) 모두 그대로 있는지로 갱신.
chk(fill_body.count("conn.commit()") == 3,
    "STEP 커밋이 세 곳 — 행마다 성공(방금 확인)·실패행 표식(round302)"
    " + 마지막 감사로그(DB.log()) 뒤, 전부 그대로 남아있다",
    fill_body.count("conn.commit()"))

# ============================================================
print("\n[2] 실행 — is_demo 오염으로 --limit 예산이 데모에 먹히는지 실측")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round265_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import importlib
    import db as DB
    DB.init_db()
    import geocode_fill as GF
    importlib.reload(GF)

    conn = DB.get_db()
    mark = "R265-" + secrets.token_hex(3)
    real_id = conn.execute(
        "INSERT INTO cases(case_no,category,region,address,status,manager,is_demo,created_at) "
        "VALUES(?,?,?,?,'접수','김담당',0,?)",
        (f"{mark}-real", "가드레일·방호울타리", "서울 강남구", "테헤란로 1", DB.now())).lastrowid
    demo_id = conn.execute(
        "INSERT INTO cases(case_no,category,region,address,status,manager,is_demo,created_at) "
        "VALUES(?,?,?,?,'접수','이담당',1,?)",
        (f"{mark}-demo", "가드레일·방호울타리", "서울 강남구", "테헤란로 2", DB.now())).lastrowid
    conn.commit()
    assert demo_id > real_id, "데모가 실제 사건보다 나중에(더 큰 id로) 생겨야 시나리오가 성립한다"

    rows = GF.rows_to_fill(conn, "cases", 1)
    chk(len(rows) == 1 and rows[0]["id"] == real_id,
        "★★★★★ limit=1 이어도 데모가 예산을 먹지 않고 실제 사건이 뽑힌다"
        "(고치기 전엔 id 가 큰 데모가 ORDER BY id DESC 에서 먼저 뽑혀 "
        "실제 사건은 이번 배치에서 조회조차 안 됐다)",
        [dict(r) for r in rows])

    rows_all = GF.rows_to_fill(conn, "cases", 500)
    chk(all(r["id"] != demo_id for r in rows_all),
        "STEP 예산을 넉넉히 줘도 데모 사건은 아예 후보에 없다")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드265 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 배치 중단에도 이미 처리한 행의 좌표가 살아남는지 실측")
# ------------------------------------------------------------
try:
    import addr_search as ADDR

    conn = DB.get_db()
    mark2 = "R265B-" + secrets.token_hex(3)
    p1_id = conn.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업',?,?,'활성')",
        (f"{mark2}-P1", "서울 송파구", "서울 송파구 올림픽로 300")).lastrowid
    p2_id = conn.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업',?,?,'활성')",
        (f"{mark2}-P2", "서울 강남구", "서울 강남구 테헤란로 999")).lastrowid
    conn.commit()
    conn.close()
    assert p1_id < p2_id, "P1이 먼저(더 작은 id로) 처리돼야 시나리오가 성립한다"

    _orig_search = ADDR.search
    _calls = []

    def _fake_search(q):
        _calls.append(q)
        if len(_calls) == 1:
            return [{"lat": 37.514, "lng": 127.106, "region": "서울 송파구", "road": "올림픽로 300"}]
        raise RuntimeError("SIMULATED-INTERRUPT")

    #  ⚠⚠ [라운드302] 이 시나리오(두 번째 조회 실패)가 더 이상 배치를
    #    중단시키지 않는다 — round302 가 검색 실패를 이 행만 건너뛰도록
    #    고쳤다(round265 가 원했던 "이미 처리한 앞쪽 행은 잃지 않는다"는
    #    목표를 "배치 자체가 애초에 안 죽는다"로 한 단계 더 강화한 결과).
    #    이제는 예외가 fill() 밖으로 새 나가지 않고 done=1 로 정상 반환되는
    #    것 자체가 맞는 동작이다 — 옛 "예외 전파를 기대"하는 검사를
    #    "정상 반환 + 검색실패 1건 집계"로 바꾼다.
    ADDR.search = _fake_search
    try:
        done = GF.fill("partners", 500, dry=False)
        chk(done == 1 and len(_calls) == 2,
            "★★★★★ 두 번째 조회가 실패해도 이제 배치가 안 죽고 첫 행만 채운 채"
            " 정상 반환된다(round302 강화 — 예전엔 이 실패가 배치 전체를 중단시켰다)",
            (done, _calls))
    finally:
        ADDR.search = _orig_search

    #  ⚠ fill() 내부의 conn 은 커밋도 close 도 못 하고 중단됐다 — 완전히
    #    독립된 새 연결로만 확인해야 "이미 커밋됐는가"를 진짜로 잰다.
    conn2 = DB.get_db()
    r1 = conn2.execute("SELECT lat, lng FROM partners WHERE id=?", (p1_id,)).fetchone()
    r2 = conn2.execute("SELECT lat, lng FROM partners WHERE id=?", (p2_id,)).fetchone()
    conn2.close()
    chk(r1["lat"] is not None and r1["lng"] is not None,
        "★★★★★ 중단 전에 이미 처리된 첫 행의 좌표는 독립된 새 연결에서도 보인다"
        "(고치기 전엔 배치 전체가 끝나야만 커밋돼, 중단되면 이미 쓴 API 호출·"
        "대기시간이 전부 날아갔다)",
        dict(r1) if r1 else None)
    chk(r2["lat"] is None and r2["lng"] is None,
        "STEP 대조군 — 중단된 두 번째 행은 애초에 UPDATE 자체가 안 갔다(당연히 비어있다)",
        dict(r2) if r2 else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드265 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
