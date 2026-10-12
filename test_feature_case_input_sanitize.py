# -*- coding: utf-8 -*-
"""[기능] 사건 등록 — 자모만 든 입력을 조용히 걸러낸다.

  왜 만들었나 (2026-08-19 실측) —
    발주처 포털·연동 API 가 공유하는 사건 생성 관문(`_create_case`)에는 지역·
    주소·접수번호에 아무 검증이 없었다. 그 결과 실운영 DB 에 자모만 든 값이
    실제로 들어와 있었다(지금은 손으로 데모 처리함):
      · #448  region='ㅇㄴㅁㄹㄴㅁㅎㄹ'  case_no='ㄹ호ㅠㅕㅓㄴ'
      · #449  region='ㄹㅇㄴ'
    같은 화면(공개폼)이 지역·전화번호는 정규식으로 막는 것과 대조된다.

  고친 방향 —
    **막지 않는다.** 이 화면은 현장에서 급하게 쓰는 화면이라, 값 하나가
    이상하다고 접수 전체를 거부하면 더 큰 사고(접수 자체가 안 됨)가 된다.
    자모만 섞인 값은 "못 읽음" 취급해 region 은 빈 값으로, case_no 는 자동
    채번으로 조용히 넘어간다 — codebase 의 기존 관용구(region_matches() 의
    "못 읽으면 빈 목록을 준다")와 같은 태도다.

      python test_feature_case_input_sanitize.py
"""
import os
import sqlite3
import sys

OK = FAIL = 0
MARK = "JMT" + os.urandom(3).hex()

# ⚠ [Windows] 운영 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import db as DB                                               # noqa: E402
import app as A                                                # noqa: E402


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def cleanup(conn):
    #  ⚠ case_no 로만 찾으면 안 된다 — [3]번 검사가 넣는 행은 **일부러**
    #    자모 접수번호를 버리고 자동 채번시키므로 MARK 접두어가 안 남는다.
    #    address 에도 표식을 심어 **둘 다**로 찾는다.
    ids = {r[0] for r in conn.execute(
        "SELECT id FROM cases WHERE case_no LIKE ? OR address LIKE ?",
        (MARK + "%", MARK + "%"))}
    for cid in ids:
        conn.execute("DELETE FROM notifications WHERE case_id=?", (cid,))
        conn.execute("DELETE FROM cases WHERE id=?", (cid,))
    conn.commit()
    return len(ids)


def main():
    conn = DB.get_db()
    cleanup(conn)
    print("=" * 66)
    print("  사건 등록 — 자모만 든 입력 실측")
    print("=" * 66)

    iid = conn.execute("SELECT id FROM insurers LIMIT 1").fetchone()["id"]
    iname = conn.execute("SELECT name FROM insurers WHERE id=?", (iid,)).fetchone()["name"]

    print("\n[1] 감지기 자체 — 실제 결함 값으로 검증")
    chk(A._has_bare_jamo("ㅇㄴㅁㄹㄴㅁㅎㄹ") is True,
        "★★ #448 실측값(지역)을 잡는다")
    chk(A._has_bare_jamo("ㄹ호ㅠㅕㅓㄴ") is True,
        "★★ #448 실측값(접수번호, 음절과 섞여도)을 잡는다")
    chk(A._has_bare_jamo("ㄹㅇㄴ") is True, "★★ #449 실측값을 잡는다")
    chk(A._has_bare_jamo("서울 강서구") is False, "★ 정상 지역은 안 건드린다")
    chk(A._has_bare_jamo("26-80162") is False, "★ 정상 접수번호는 안 건드린다")
    chk(A._has_bare_jamo("") is False, "★ 빈 값은 그대로 통과(별도 처리 대상 아님)")

    print("\n[2] 실제 등록 경로 — 지역이 자모만이면 빈 값으로, 접수는 막지 않는다")
    conn.execute("BEGIN IMMEDIATE")
    try:
        res = A._create_case(conn, iid, iname, {
            "categories": ["가드레일·방호울타리"],
            "case_no": f"{MARK}-1",
            "region": "ㅇㄴㅁㄹㄴㅁㅎㄹ",
            "address": f"{MARK} 정상 주소 그대로",
            "est_price": "1000000",
        }, "검증")
        conn.commit()
    except Exception as e:                                     # noqa: BLE001
        conn.rollback()
        chk(False, "★★★ 자모 지역이어도 접수 자체는 막히지 않는다",
            f"{type(e).__name__} {e}")
        res = None
    if res:
        row = conn.execute("SELECT region, address, case_no FROM cases WHERE id=?",
                           (res["id"],)).fetchone()
        chk(row["region"] == "", "★★★ 자모뿐인 지역은 빈 값으로 저장된다", row["region"])
        chk(row["address"] == f"{MARK} 정상 주소 그대로",
            "★ 다른 정상 칸(주소)은 그대로 저장된다(과잉 차단 아님)")
        chk(row["case_no"] == f"{MARK}-1",
            "★ 정상 접수번호는 그대로 쓰인다(내가 지정한 값)")

    print("\n[3] 접수번호가 자모만이면 — 그 값을 버리고 자동 채번한다")
    conn.execute("BEGIN IMMEDIATE")
    try:
        res2 = A._create_case(conn, iid, iname, {
            "categories": ["가드레일·방호울타리"],
            "case_no": "ㄹ호ㅠㅕㅓㄴ",
            "region": "서울 송파구",
            "address": f"{MARK} 정상 주소",
            "est_price": "1000000",
        }, "검증")
        conn.commit()
    except Exception as e:                                     # noqa: BLE001
        conn.rollback()
        chk(False, "★★★ 자모 접수번호여도 등록 자체는 막히지 않는다",
            f"{type(e).__name__} {e}")
        res2 = None
    if res2:
        row2 = conn.execute("SELECT case_no, region FROM cases WHERE id=?",
                            (res2["id"],)).fetchone()
        chk(row2["case_no"] != "ㄹ호ㅠㅕㅓㄴ",
            "★★★ 자모뿐인 접수번호가 그대로 저장되지 않는다", row2["case_no"])
        chk(bool(row2["case_no"]) and A._has_bare_jamo(row2["case_no"]) is False,
            "★★ 대신 정상적인 자동 채번 값이 들어간다", row2["case_no"])
        chk(row2["region"] == "서울 송파구",
            "★ 정상 지역은 그대로 저장된다(과잉 차단 아님)")

    print("\n[4] 정상 입력은 아무것도 안 바뀐다 (회귀 없음)")
    conn.execute("BEGIN IMMEDIATE")
    try:
        res3 = A._create_case(conn, iid, iname, {
            "categories": ["유리·샷시·자동문"],
            "region": "경기 성남시",
            "address": f"{MARK} 정상 주소 2",
            "est_price": "500000",
        }, "검증")
        conn.commit()
    except Exception as e:                                     # noqa: BLE001
        conn.rollback()
        chk(False, "★★ 정상 입력 등록", f"{type(e).__name__} {e}")
        res3 = None
    if res3:
        row3 = conn.execute("SELECT region FROM cases WHERE id=?", (res3["id"],)).fetchone()
        chk(row3["region"] == "경기 성남시", "★★ 정상 지역은 한 글자도 안 바뀐다")

    n = cleanup(conn)
    print(f"\n  정리: 검증용 사건 {n}건")
    conn.close()
    print("-" * 66)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
