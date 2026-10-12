# -*- coding: utf-8 -*-
"""스캔 179라운드 회귀 — manage.py prune-personal --dry-run 이 ③-1(피해자 안내
알림)·③-1-2(진행조회 링크) 버킷을 항상 0건으로 보여주던 결함.

  그 두 버킷의 조회 조건이 "victim_name·victim_phone 가 이미 빈 값"인데,
  그 값을 비우는 건 바로 위 버킷(③)의 UPDATE 다. 미리보기는 그 UPDATE 를
  건너뛰므로, 실제로는 지워질 알림·링크가 미리보기에서는 영원히 0건으로
  보인다 — "먼저 이걸로 확인할 것"이라는 이 명령 자신의 안내와 반대로,
  미리보기가 실제 파기 범위를 과소보고한다(개인정보 파기는 되돌릴 수 없다).

      python test_scan_round179_fixes.py
"""
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


SRC = read("manage.py")

print("=" * 72)
print("  스캔 179라운드 회귀 — prune-personal 미리보기의 알림·링크 과소보고")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i0 = SRC.index("def cmd_prune_personal(")
i1 = SRC.index("\ndef ", i0 + 1)
body = SRC[i0:i1]
chk("if n3:\n            conn.execute(" in body,
    "★★★ 피해자정보(③) UPDATE 가 dry 여부와 무관하게 실행된다"
    "(바로 아래 알림·링크 버킷이 그 결과를 읽는다)")
chk("if n4:\n            conn.execute(\"UPDATE cases SET victim_name=NULL" in body,
    "★★★ 종료사건 피해자정보(③-2) UPDATE 도 마찬가지로 무조건 실행된다")
chk("if dry:\n            conn.rollback()\n        else:\n            conn.commit()" in body,
    "★★★ 미리보기는 끝에서 rollback 해 아무것도 실제로 남기지 않는다")

# ============================================================
print("\n[2] 실행 — 실제 격리 DB에서 미리보기 건수가 실제 실행과 일치하는가")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round179_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import manage as M

    conn = DB.get_db()
    # 완료 + 하자담보(기본 24개월) 훌쩍 지난 사건 — 열린 하자 없음
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,completed_at,"
        "                  victim_name,victim_phone,track_token,created_at) "
        "VALUES('R179-CASE','완료','가드레일','서울','2020-01-01',"
        "       '홍길동','010-1234-5678','r179-tok',?)", (DB.now(),)).lastrowid
    nid = conn.execute(
        "INSERT INTO notifications(ntype,channel,target,message,status,case_id,created_at) "
        "VALUES('피해자안내','문자','010-1234-5678','현장 접수 안내 문자','전달됨',?,?)",
        (cid, DB.now())).lastrowid
    conn.commit()

    def snapshot():
        c = conn.execute(
            "SELECT victim_name, victim_phone, track_token FROM cases WHERE id=?",
            (cid,)).fetchone()
        n = conn.execute(
            "SELECT target, message FROM notifications WHERE id=?", (nid,)).fetchone()
        return dict(c), dict(n)

    before = snapshot()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        M.cmd_prune_personal(["--dry-run"])
    preview_text = buf.getvalue()

    chk("피해자 안내 알림 1건" in preview_text,
        "★★★ 미리보기가 피해자 안내 알림 1건을 보여준다"
        "(고치기 전엔 victim_name 이 아직 안 비어 있어 0건으로 보였다)",
        preview_text)
    chk("진행조회 링크 1건" in preview_text,
        "★★★ 미리보기가 진행조회 링크 1건도 보여준다(같은 이유로 전엔 0건)",
        preview_text)
    chk("피해자 정보 1건" in preview_text,
        "미리보기가 원래도 맞게 세던 피해자 정보(③) 자체도 여전히 1건", preview_text)

    after_dry = snapshot()
    chk(after_dry == before,
        "★★★ 미리보기는 실제로는 아무것도 바꾸지 않는다(rollback 확인)",
        (before, after_dry))

    # 실제 실행 — 미리보기가 예고한 그대로 지워져야 한다
    buf2 = io.StringIO()
    with contextlib.redirect_stdout(buf2):
        M.cmd_prune_personal([])
    case_after, notif_after = snapshot()
    chk(case_after["victim_name"] is None and case_after["victim_phone"] is None,
        "실제 실행은 피해자 성명·연락처를 지운다", case_after)
    chk(case_after["track_token"] is None,
        "★ 실제 실행은 진행조회 토큰도 무효화한다(미리보기가 예고한 대로)", case_after)
    chk(notif_after["target"] == "(파기됨)" and "파기" in notif_after["message"],
        "★ 실제 실행은 알림 본문도 파기한다(미리보기가 예고한 대로)", notif_after)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드179 [2] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
