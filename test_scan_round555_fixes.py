# -*- coding: utf-8 -*-
"""스캔 555라운드 회귀 — test_scan_round3_fixes.py의 가중치 픽스처가 round424의
   부분 UNIQUE 인덱스와 충돌해 깨져 있던 결함, 1건(테스트 픽스처 자체의 결함,
   app.py는 무죄).

   기존에 열려 있던 "이중입찰 스캔 후보" 각도(사용자 제안 칩은 유실됐으나
   과제안내문이 처음부터 다시 조사하라고 지시)를 직접 조사 — round3 테스트
   ([1] 추천 가중치 정합)가 같은 경매·같은 협력사(pid)로 활성 입찰을 두 번
   INSERT 하는 픽스처를 쓰고 있는데, round424가 나중에 이 정확한 상태
   (auction_id, partner_id) 조합의 활성(voided_at IS NULL) 중복을 막는 부분
   UNIQUE 인덱스(db.py, idx_bids_active_partner)를 db.py 마이그레이션에 추가했다
   — round3는 round424보다 훨씬 먼저 쓰인 파일이라 이 변화를 못 따라왔다.

   실측(직접 재현, 스크래치 DB) — round3 파일에 지금 그대로 남아 있던 두 줄짜리
   반복 INSERT(같은 pid로 두 번)를 오늘자 실제 스키마(db.init_db())에 대고 그대로
   실행하면 두 번째 INSERT가 `sqlite3.IntegrityError: UNIQUE constraint failed:
   bids.auction_id, bids.partner_id`로 죽는다 — 즉 이 테스트를 실제로 돌리면(전체
   배터리, HTTP 구간) 가중치 재계산 로직과 무관한 스키마 충돌 트레이스백으로
   죽어, 의도한 검증([1] 항목 8개)은 단 하나도 실행되지 못한 채 실패한다.
   round414류(같은 세션의 round554가 이미 겪은)와 같은 성격 — app.py 자신의
   결함이 아니라 **테스트 픽스처가 현실(스키마 불변식)을 못 따라온 노후화**다.

   독립검증 — api_partner_bid()·api_partner_reauction_bid()(round424 자신의
   조사)가 이미 "재투찰은 UPDATE, 신규는 INSERT"로 파트너당 활성 입찰을 항상
   1건만 유지함을 재확인했고, `/api/insurer/cases/<id>/bids`
   (api_insurer_bids, app.py)도 `AND b.voided_at IS NULL`로 활성 입찰만 후보로
   본다 — "한 업체가 같은 경매에 활성 입찰을 두 개 가진 채로 화면에 뜨는" 이
   픽스처의 전제 자체가 실제 애플리케이션 어디에서도 나올 수 없는 상태였다.

   고침(테스트 픽스처만 — 그냥 고치면 되는 것, 새 정책·앱 코드 변경 없음):
   test_scan_round3_fixes.py의 두 번째 입찰을 별도 협력사(pid2)로 바꿔, 서로
   다른 두 업체가 각자 하나씩 입찰한 정상적인 경쟁 시나리오로 교체했다 —
   [1]이 실제로 보는 것(가중치를 바꾸면 최저가 입찰의 점수 자체가 바뀐다)은
   입찰이 여럿이기만 하면 성립하고 두 번째 입찰자가 누구인지는 안 보므로
   검증 의도는 그대로 유지된다. 끝에서 새로 만든 협력사 행도 정리한다.

   이 회귀테스트(9개 검사)는 ONLY 안전한 기법만 쓴다 — 실제 on-disk app.py는
   전혀 건드리지 않고, "되돌리기" 증명은 옛(깨졌던) 픽스처 코드를 별도 문자열로
   재구성해 exec()으로 스크래치 DB에 직접 실행해 IntegrityError를 실측한다.

       python test_scan_round555_fixes.py
"""
import io
import os
import sys
import sqlite3
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 555라운드 회귀 — round3 가중치 픽스처 vs round424 UNIQUE 인덱스")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인 — test_scan_round3_fixes.py 가 실제로 고쳐졌는가")
# ------------------------------------------------------------
R3_SRC = read("test_scan_round3_fixes.py")
#  ⚠ 옛(깨진) 패턴 — 같은 pid 로 두 번 넣는 한 줄짜리 반복문 헤더가 없어야 한다.
OLD_LOOP_HEADER = "for amt, dys in ((4_200_000, 5), (4_600_000, 3)):"
chk(OLD_LOOP_HEADER not in R3_SRC,
    "★★★★★ 같은 협력사(pid)로 두 번 넣던 옛 반복문이 더 이상 없다")
chk("INSERT INTO partners(name,status,partner_type,region,rating,jobs_done)" in R3_SRC,
    "★★★★ 두 번째(별도) 협력사를 만드는 INSERT 가 추가됐다")
chk("(pid, pname, 4_200_000, 5), (pid2, p2name, 4_600_000, 3)" in R3_SRC,
    "★★★★★ 두 입찰이 이제 서로 다른 협력사(pid/pid2)로 나뉜다")
chk('conn.execute("DELETE FROM partners WHERE id=?", (pid2,))' in R3_SRC,
    "★★★ 새로 만든 협력사 행도 끝에서 정리한다(잔재 방지)")

# ============================================================
print("\n[2] 준비 — 스크래치 DB(오늘자 실제 스키마)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round555_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)

import db as DB
DB.init_db()
import app as A

conn = DB.get_db()
idx = conn.execute(
    "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_bids_active_partner'"
).fetchone()
chk(idx is not None and "UNIQUE" in (idx["sql"] or "").upper(),
    "★★★★ 전제조건: round424의 부분 UNIQUE 인덱스가 오늘자 스키마에 실제로 있다",
    dict(idx) if idx else None)


def _mkcase(tag):
    conn.execute("INSERT INTO insurers(name,status) VALUES(?,'활성')", (f"{tag}보험사",))
    iid = conn.execute("SELECT id FROM insurers WHERE name=?", (f"{tag}보험사",)).fetchone()["id"]
    conn.execute("INSERT INTO partners(name,status,partner_type,region,rating,jobs_done) "
                 "VALUES(?,'활성','시행사','서울',4.5,10)", (f"{tag}업체1",))
    pid = conn.execute("SELECT id FROM partners WHERE name=?", (f"{tag}업체1",)).fetchone()["id"]
    conn.execute(
        """INSERT INTO cases(case_no,insurer,insurer_id,category,region,address,est_price,
                             status,created_at)
           VALUES(?,?,?,?,?,?,?,'입찰중',datetime('now','+9 hours'))""",
        (f"{tag}-CASE", f"{tag}보험사", iid, "유리·샷시·자동문", "서울", "가중치검증", 5_000_000))
    cid = conn.execute("SELECT id FROM cases WHERE case_no=?", (f"{tag}-CASE",)).fetchone()["id"]
    conn.execute(
        """INSERT INTO auctions(case_id,status,deadline,created_at)
           VALUES(?,'진행',datetime('now','+9 hours','+2 days'),datetime('now','+9 hours'))""",
        (cid,))
    aid = conn.execute("SELECT id FROM auctions WHERE case_id=?", (cid,)).fetchone()["id"]
    conn.commit()
    return iid, pid, cid, aid


# ============================================================
print("\n[3] 되돌리기 — round3의 옛(깨진) 픽스처를 오늘자 스키마에 그대로 실행하면")
#     실제로 IntegrityError로 죽는가 (인과관계 실측, exec()으로만 재구성 — 실제 파일은 안 건드림)
# ------------------------------------------------------------
_iid_old, _pid_old, _cid_old, _aid_old = _mkcase("R555OLD")
pname_old = "R555OLD업체1"
#  ⚠ round3 에 실제로 있었던 옛 코드를 문자열로만 재구성한다 — on-disk 파일은
#    전혀 건드리지 않는다(안전 규칙: in-memory 재구성 + exec 만 쓴다).
OLD_FIXTURE_SRC = (
    "for amt, dys in ((4_200_000, 5), (4_600_000, 3)):\n"
    "    conn.execute(\"\"\"INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,"
    "created_at)\n"
    "                    VALUES(?,?,?,?,?,datetime('now','+9 hours'))\"\"\",\n"
    "                 (aid, pid, pname, amt, dys))\n"
)
try:
    exec(OLD_FIXTURE_SRC, {}, {"conn": conn, "aid": _aid_old, "pid": _pid_old, "pname": pname_old})
    conn.commit()
    chk(False, "★★★★★ 옛 픽스처(같은 pid 두 번)가 오늘자 스키마에서 IntegrityError 로 "
        "거부돼야 하는데 그냥 성공해버렸다(재현 실패)")
except sqlite3.IntegrityError as e:
    conn.rollback()
    chk(True, "★★★★★ 옛 픽스처를 오늘자 스키마에 그대로 돌리면 실제로 "
        "IntegrityError 로 죽는다(round3가 실제로 이 상태였음을 인과관계로 증명)",
        str(e))
n_old = conn.execute("SELECT COUNT(*) c FROM bids WHERE auction_id=?", (_aid_old,)).fetchone()["c"]
#  ⚠ 두 INSERT 는 커밋 없이 한 트랜잭션을 공유한다(sqlite3 기본 동작) — 두
#    번째가 실패한 뒤 conn.rollback() 하면 첫 번째까지 함께 되돌아가 0건이
#    맞다(실제 round3 스크립트라면 이 지점에서 잡히지 않은 예외로 그대로
#    죽어 rollback 조차 못 부르고 커넥션만 버려지는데, 결과는 똑같이 0건이다).
chk(n_old == 0, "  실패한 두 INSERT는 한 트랜잭션이라 롤백하면 0건이 남는다"
    "(미처리 예외로 죽는 실제 상황과 결과가 같다)", n_old)

# ============================================================
print("\n[4] 실행 — round3의 새(고쳐진) 픽스처: 서로 다른 두 협력사면 정상 삽입되는가")
# ------------------------------------------------------------
_iid_new, _pid_new, _cid_new, _aid_new = _mkcase("R555NEW")
pname_new = "R555NEW업체1"
p2name_new = "R555NEW업체2"
try:
    pid2_new = conn.execute(
        """INSERT INTO partners(name,status,partner_type,region,rating,jobs_done)
           VALUES(?,'활성','시행사','서울',4.5,10)""", (p2name_new,)).lastrowid
    for _pid, _pname, amt, dys in ((_pid_new, pname_new, 4_200_000, 5),
                                    (pid2_new, p2name_new, 4_600_000, 3)):
        conn.execute(
            """INSERT INTO bids(auction_id,partner_id,partner_name,amount,days,created_at)
               VALUES(?,?,?,?,?,datetime('now','+9 hours'))""",
            (_aid_new, _pid, _pname, amt, dys))
    conn.commit()
    n_new = conn.execute(
        "SELECT COUNT(*) c FROM bids WHERE auction_id=? AND voided_at IS NULL",
        (_aid_new,)).fetchone()["c"]
    chk(n_new == 2, "★★★★★ 고쳐진 픽스처(서로 다른 두 협력사)는 제지 없이 활성 입찰 2건이 쌓인다",
        n_new)
except sqlite3.IntegrityError as e:
    chk(False, "★★★★★ 고쳐진 픽스처도 여전히 IntegrityError 로 막혀서는 안 된다", str(e))

# ============================================================
print("\n[5] 실행 — 실제 라우트(api_insurer_bids)로 round3 [1]의 검증 의도가 그대로 성립하는가")
#     (가중치를 바꾸면 최저가 입찰의 점수 자체가 바뀐다 — round3 원래 취지)
# ------------------------------------------------------------
client = A.app.test_client()
with client.session_transaction() as sess:
    sess["insurer_id"] = _iid_new

r1 = client.get(f"/api/insurer/cases/{_cid_new}/bids")
d1 = r1.get_json() or {}
chk(r1.status_code == 200 and d1.get("bids"), "실제 라우트 200 + 입찰 목록 조회", r1.status_code)
chk(len(d1.get("bids") or []) == 2, "  입찰 2건(서로 다른 협력사) 모두 후보로 보인다",
    len(d1.get("bids") or []))
chk(d1.get("weights_default") is True, "  기본 가중치에서는 default 플래그 참", d1.get("weights_default"))

old_price_w = conn.execute("SELECT value FROM settings WHERE key='bid_w_price'").fetchone()
conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('bid_w_price','0.05')")
conn.commit()
try:
    r2 = client.get(f"/api/insurer/cases/{_cid_new}/bids")
    d2 = r2.get_json() or {}
    #  ⚠ api_insurer_bids 는 순위를 매기지 않고 **가격순**으로 정렬한다(app.py,
    #    라운드 주석: "정렬은 가격순 — 우리가 만든 순서가 아니다") — bids[0] 은
    #    항상 최저가(4,200,000, pid) 행이다. round3 원래 검증대로 그 행의
    #    점수 자체가 가중치 변경 전후로 달라지는지를 본다.
    chk(d1["bids"][0]["amount"] == d2["bids"][0]["amount"] == 4_200_000,
        "  최저가 입찰(bids[0])은 가중치와 무관하게 항상 같은 건이다(가격순 정렬)",
        (d1["bids"][0]["amount"], d2["bids"][0]["amount"]))
    chk(d1["bids"][0]["score"] != d2["bids"][0]["score"],
        "★★★★★ 가중치를 바꾸면(가격비중 인하) 그 입찰의 점수 자체가 달라진다"
        "(round3 [1]의 검증 의도가 새 픽스처로도 그대로 성립)",
        f"{d1['bids'][0]['score']} -> {d2['bids'][0]['score']}")
    chk(d2.get("weights_default") is False, "  가중치 조정 사실이 default=False 로 알려진다",
        d2.get("weights_default"))
finally:
    if old_price_w:
        conn.execute("UPDATE settings SET value=? WHERE key='bid_w_price'", (old_price_w[0],))
    else:
        conn.execute("DELETE FROM settings WHERE key='bid_w_price'")
    conn.commit()

# ── 정리 ──────────────────────────────────────────────────────
for _aid in (_aid_old, _aid_new):
    conn.execute("DELETE FROM bids WHERE auction_id=?", (_aid,))
    conn.execute("DELETE FROM auctions WHERE id=?", (_aid,))
for _cid in (_cid_old, _cid_new):
    conn.execute("DELETE FROM cases WHERE id=?", (_cid,))
conn.commit()
conn.close()

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
