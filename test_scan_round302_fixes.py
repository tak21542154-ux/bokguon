# -*- coding: utf-8 -*-
"""스캔 302라운드 회귀 — geocode_fill.py(주소→좌표 일괄 지오코딩 배치도구)
   결함 3건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — round267의
   DB저장 실패 방어(실측 재확인, 여전히 존재)·round294의 addr_search.py
   IncompleteRead 수정(실측 재확인, 여전히 존재)·데모격리(cases 는
   is_demo=0 필터 확인·partners 는 그 컬럼 자체가 없음)는 클린. 부수관찰
   (geo_src='주소검색' 이 자동일괄추정과 사람확인선택 두 신뢰수준을 한
   값으로 묶음·요청 간격 0.35초)은 스키마·정책 판단이 필요해 이번 라운드
   범위 밖으로 남김.

   ①[심각] fill() 의 검색 두 번(ADDR.search(q)·ADDR.search(q2))이 아무
      보호도 없었다 — round267 이 고친 건 DB 저장 실패뿐이었고, addr_search.
      search() 자신의 "실패하면 빈 목록" 계약이 유일한 방어선이었는데 그
      계약은 이미 한 번 깨진 적이 있다(round294, IncompleteRead 누출 —
      지금은 고쳐져 있지만 그 하위 계층이 다시 회귀하지 않는다는 가정에만
      기대면 안 된다). 한 행의 검색 실패가 나머지 행 전부(최대 --limit,
      기본 500건)를 조용히 죽였다(실측: 3건 중 2번째에서 강제로 실패시키면
      3번째로 정상 지오코딩됐을 업체가 아예 시도조차 못 받고 배치 자체가
      죽음). 그 두 검색을 감싸 이 행만 건너뛰게 수정.
   ②[심각] _region_ok() 로 "동네가 맞는지" 판정할 때, 실제로 결과를 찾은
      검색문(정제된 q2)이 아니라 항상 원문 주소(q)로 판정했다 — '본사:
      서울 강남구… / 공장: 경기 김포시…' 처럼 원문에 여러 주소가 섞여
      있으면, 검색에 안 쓰인 뒤쪽 주소(김포시)가 우연히 검색 결과의
      동네와 겹쳐 완전히 다른 도시 좌표를 "동네 일치"로 잘못 승인했다
      (실측: 같은 입력을 원문 기준/실제 검색문 기준으로 나란히 판정 —
      원문 기준은 통과, 실제 기준은 정확히 거름). 이 좌표는 geo_src=
      '주소검색'(신뢰 표식)으로 저장돼 배차 화면의 "정확한 거리" 판정에
      바로 들어간다. 실제로 좌표를 찾아낸 문자열을 기준으로 판정하도록
      수정.
   ③ 지오코딩에 실패한 행(못 찾음·한반도 밖·동네 불일치)이 아무 표식도
      안 남아 "아직 안 해 봄"과 구별이 안 됐다 — cases 는 계속 누적되는
      표라 이 도구가 반복 실행될 수 있는데, 영구히 못 찾는 낮은 id 의
      주소가 --limit 이상 쌓이면 매 실행이 그 오래된 실패건만 다시 뽑아
      정작 새로 생긴 사건은 시도조차 못 받는다(실측: 같은 5건을 두 번
      실행해도 매번 같은 3건만 뽑히고 6번째 정상 업체는 두 번 다 시도조차
      안 됨). 시도해서 못 채운 행은 geo_src 에 새 표식('시도실패')을 남겨
      다음 실행이 건너뛰게 하고, 대상 조회 쿼리에서 이 표식을 제외하도록
      수정(사람이 그 행의 geo_src 를 지우면 다시 대상에 들어간다 — 영구
      봉인이 아니다).

      python test_scan_round302_fixes.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["BOKGUON_DB_PATH"] = os.path.join(
    tempfile.mkdtemp(prefix="round302_setup_"), "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(
    os.path.dirname(os.environ["BOKGUON_DB_PATH"]), "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
import db as DB                                                     # noqa: E402
DB.init_db()

PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


GF_SRC = read("geocode_fill.py")

print("=" * 72)
print("  스캔 302라운드 회귀 — geocode_fill.py 검색보호·동네판정 기준·재시도표식")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
chk('FAILED_SRC = "시도실패"' in GF_SRC, "★★★ 재시도 방지 표식 상수가 정의돼 있다")
chk(GF_SRC.count("AND COALESCE(geo_src,'') <> ?") == 2,
    "★★★ partners·cases 두 대상조회 쿼리 모두 그 표식을 제외한다",
    GF_SRC.count("AND COALESCE(geo_src,'') <> ?"))
chk("except Exception as ex:\n            skip_search_err += 1" in GF_SRC,
    "★★★ 검색 두 번이 이제 try/except 로 보호된다(검색 실패 전용 카운터)")
chk('want = f"{r[\'region\'] or \'\'} {used_q}"' in GF_SRC,
    "★★★ 동네판정이 실제 검색에 쓰인 문자열(used_q)을 기준으로 한다"
    "(고치기 전엔 항상 원문 q)")
chk(GF_SRC.count("_mark_failed(r[\"id\"])") == 3,
    "★★ 세 실패지점(못찾음·한반도밖·동네불일치) 모두 표식을 남긴다",
    GF_SRC.count("_mark_failed(r[\"id\"])"))

import geocode_fill as GF                                            # noqa: E402
import addr_search as ADDR                                           # noqa: E402

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 검색 실패 1건이 배치 전체를 안 죽이는가(실제 fill() 호출)")
# ──────────────────────────────────────────────────────────────
_orig_search = ADDR.search
try:
    conn = DB.get_db()
    ids = []
    for i in range(3):
        ids.append(conn.execute(
            "INSERT INTO partners(name,partner_type,status,address) "
            "VALUES(?,'시공사','활성',?)",
            (f"R302-업체{i}", f"서울 강남구 테스트로 {i}")).lastrowid)
    conn.commit()
    conn.close()

    def _flaky_search(q):
        if "테스트로 1" in q:
            raise RuntimeError("강제 검색실패(2번째 업체 흉내)")
        return [{"lat": 37.5, "lng": 127.0, "region": "서울 강남구", "road": q}]

    ADDR.search = _flaky_search
    done = GF.fill("partners", limit=10, dry=False)
    chk(done == 2,
        "★★★ 중간 1건이 검색실패로 죽어도 나머지 정상 2건은 전부 채워진다"
        "(고치기 전엔 이 예외가 fill() 밖으로 그대로 튀어 배치 전체가 죽었다)",
        done)
    conn = DB.get_db()
    ok3 = conn.execute("SELECT lat FROM partners WHERE id=?", (ids[2],)).fetchone()["lat"]
    conn.close()
    chk(ok3 is not None,
        "★★★ 실패한 업체 '뒤'에 있던 3번째 업체도 시도돼 좌표가 채워졌다"
        "(고치기 전엔 아예 시도조차 못 받았다)", ok3)
except Exception as e:                                              # noqa: BLE001
    #  ⚠ [라운드302] 되돌리기 상태에선 이 예외가 fill() 밖으로 그대로 튀는
    #    것 자체가 결함 재현이다 — 잡지 않으면 이 스크립트 전체가 죽어
    #    [3][4] 검사가 통째로 안 돈다(round297·300과 같은 종류의 함정을
    #    "테스트가 부르는 함수가 바로 그 예외처리를 검증 대상으로 삼을 때"
    #    변형으로 다시 겪음).
    chk(False, "★★★ 라운드302 [2] 검색보호 실측", f"{type(e).__name__} {e}")
finally:
    ADDR.search = _orig_search

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행 — 동네판정이 실제 검색문 기준인가(에이전트 재현과 같은 시나리오)")
# ──────────────────────────────────────────────────────────────
try:
    conn = DB.get_db()
    multi_addr = "본사: 서울 강남구 테헤란로 152 / 이전 공장: 경기도 김포시 대곶면"
    pid = conn.execute(
        "INSERT INTO partners(name,partner_type,status,region,address) "
        "VALUES('R302-복수주소업체','시공사','활성','서울 강남구',?)",
        (multi_addr,)).lastrowid
    conn.commit()
    conn.close()

    def _mismatched_search(q):
        #  원문(q, 다중주소 그대로) 검색은 실패, 정제문(q2, 강남 부분만)만
        #  성공하되 — 검색엔진이 헷갈려 김포시 결과를 낸 상황을 흉내낸다.
        if q == multi_addr:
            return []
        return [{"lat": 37.63, "lng": 126.60, "region": "경기 김포시", "road": "대곶면 어딘가로 1"}]

    ADDR.search = _mismatched_search
    done = GF.fill("partners", limit=10, dry=False)
    conn = DB.get_db()
    row = conn.execute("SELECT lat, geo_src FROM partners WHERE id=?", (pid,)).fetchone()
    conn.close()
    chk(row["lat"] is None,
        "★★★ 원문에 섞인 무관한 지명(김포) 때문에 엉뚱한 도시 좌표가 승인되지 않는다"
        "(고치기 전엔 원문 기준 판정이라 '동네 일치'로 잘못 통과했다)",
        dict(row))
    #  같은 계산을 두 기준으로 나란히 재현 — 무엇이 왜 갈리는지 직접 확인
    want_buggy = f"서울 강남구 {multi_addr}"
    want_fixed = "서울 강남구 서울 강남구 테헤란로 152"
    got = "경기 김포시 대곶면 어딘가로 1"
    chk(GF._region_ok(want_buggy, got) is True,
        "STEP 원문 기준으로 계산하면(옛 버그) 실제로 '동네 일치'가 된다(전제 확인)",
        GF._region_ok(want_buggy, got))
    chk(GF._region_ok(want_fixed, got) is False,
        "★★ 실제 검색문 기준이면(고친 뒤) 정확히 '동네 불일치'로 거른다",
        GF._region_ok(want_fixed, got))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드302 [3] 동네판정기준 실측", f"{type(e).__name__} {e}")
finally:
    ADDR.search = _orig_search

# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 실패표식이 재시도 기아를 막는가(같은 배치를 두 번 실행)")
# ──────────────────────────────────────────────────────────────
try:
    conn = DB.get_db()
    bad_ids = []
    for i in range(3):
        bad_ids.append(conn.execute(
            "INSERT INTO partners(name,partner_type,status,address) "
            "VALUES(?,'시공사','활성',?)",
            (f"R302-못찾음{i}", f"존재안하는가상주소{i}번지")).lastrowid)
    good_id = conn.execute(
        "INSERT INTO partners(name,partner_type,status,address) "
        "VALUES('R302-정상업체','시공사','활성','서울 강남구 진짜주소 1')").lastrowid
    conn.commit()
    conn.close()

    def _selective_search(q):
        if "진짜주소" in q:
            return [{"lat": 37.5, "lng": 127.0, "region": "서울 강남구", "road": q}]
        return []   # 가상주소는 절대 못 찾음(영구 실패 흉내)

    ADDR.search = _selective_search
    GF.fill("partners", limit=3, dry=False)     # 1회차 — limit 안에 가상주소 3건만 들어감
    conn = DB.get_db()
    good_lat_after_1 = conn.execute(
        "SELECT lat FROM partners WHERE id=?", (good_id,)).fetchone()["lat"]
    conn.close()
    chk(good_lat_after_1 is None,
        "STEP 1회차는 limit 3건을 전부 못찾는 업체가 차지해 정상 업체는 시도조차 못 받는다"
        "(전제 확인)", good_lat_after_1)

    GF.fill("partners", limit=3, dry=False)     # 2회차 — 표식 덕분에 이번엔 정상 업체가 뽑혀야 한다
    conn = DB.get_db()
    good_lat_after_2 = conn.execute(
        "SELECT lat FROM partners WHERE id=?", (good_id,)).fetchone()["lat"]
    bad_src = conn.execute(
        "SELECT COUNT(*) FROM partners WHERE id IN (%s) AND geo_src=?"
        % ",".join("?" * len(bad_ids)), (*bad_ids, GF.FAILED_SRC)).fetchone()[0]
    conn.close()
    chk(bad_src == 3,
        "★★ 실패한 3건 모두 재시도방지 표식이 남았다", bad_src)
    chk(good_lat_after_2 is not None,
        "★★★ 2회차에선 실패건이 표식으로 제외돼 정상 업체가 드디어 시도돼 채워진다"
        "(고치기 전엔 몇 번을 다시 돌려도 이 업체는 영원히 뽑히지 않았다)",
        good_lat_after_2)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드302 [4] 재시도표식 실측", f"{type(e).__name__} {e}")
finally:
    ADDR.search = _orig_search

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
