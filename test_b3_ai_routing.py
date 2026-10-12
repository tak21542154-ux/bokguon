# -*- coding: utf-8 -*-
"""B3 검증 — AI 신뢰도 기준에 따른 자동 승인 라우팅.

AI 키 없이도 라우팅 규칙 자체를 검증한다.
(실제 판정값을 직접 넣고, 기준 위/아래에서 어떻게 갈리는지 확인)
"""
import sys
import secrets
import db as DB
import os
# [Windows] 운영 서버가 연 로그 파일을 검증까지 함께 열면 회전이 실패한다 — 자기 파일로.
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
import app as A

OK = FAIL = 0


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")


def mkphoto(conn, case_id, kind, conf, status="대기"):
    cur = conn.execute(
        """INSERT INTO photos(case_id, partner_id, uploader, uploader_role, rel_path,
                              orig_name, mime, ext, size, sha256,
                              kind, ai_kind, ai_confidence, ai_model, review_status, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (case_id, 1, "테스트", "관리자", f"t/{kind}{conf}.jpg", "t.jpg", "image/jpeg", ".jpg",
         100, "b3test_" + secrets.token_hex(8), kind, kind, conf, "테스트", status, DB.now()))
    conn.commit()
    return cur.lastrowid


def main():
    conn = DB.get_db()
    case_id = conn.execute("SELECT id FROM cases ORDER BY id DESC LIMIT 1").fetchone()
    if not case_id:
        print("사건이 없어 검증할 수 없습니다."); return 1
    case_id = case_id["id"]

    conn.execute("DELETE FROM ai_reviews WHERE photo_id IN "
                 "(SELECT id FROM photos WHERE sha256 LIKE 'b3test_%')")
    conn.execute("DELETE FROM photos WHERE sha256 LIKE 'b3test_%'")
    conn.commit()

    th = A._ai_threshold(conn)
    print("=" * 62)
    print(f"  B3 검증 — 현재 자동 승인 기준 {th}점")
    print("=" * 62)

    # ① 기준 이상 + 공사 사진 → 자동 승인
    p1 = mkphoto(conn, case_id, "착공전", th + 5)
    chk(A._apply_ai_routing(p1) == "auto", f"신뢰도 {th+5}점 착공전 → 자동 승인")
    r = conn.execute("SELECT review_status FROM photos WHERE id=?", (p1,)).fetchone()
    chk(r["review_status"] == "승인", "  실제 상태가 '승인'으로 바뀜", r["review_status"])

    # ② 기준 미만 → 사람이 봐야 함
    p2 = mkphoto(conn, case_id, "시공중", th - 5)
    chk(A._apply_ai_routing(p2) != "auto", f"신뢰도 {th-5}점 → 자동 승인 안 됨")
    r = conn.execute("SELECT review_status FROM photos WHERE id=?", (p2,)).fetchone()
    chk(r["review_status"] == "대기", "  상태가 '대기'로 남음", r["review_status"])

    # ③ 영수증은 신뢰도가 아무리 높아도 사람이 본다 (돈이 걸린 서류)
    p3 = mkphoto(conn, case_id, "영수증", 99)
    chk(A._apply_ai_routing(p3) != "auto", "신뢰도 99점 영수증 → 자동 승인 제외")
    r = conn.execute("SELECT review_status FROM photos WHERE id=?", (p3,)).fetchone()
    chk(r["review_status"] == "대기", "  영수증은 '대기' 유지", r["review_status"])

    # ④ 이미 승인·반려된 사진은 건드리지 않는다
    p4 = mkphoto(conn, case_id, "완공후", 99, status="반려")
    chk(A._apply_ai_routing(p4) != "auto", "이미 반려된 사진 → 다시 승인하지 않음")

    # ⑤ 판정 기록이 남는가 (정확도 계산의 근거)
    n = conn.execute("SELECT COUNT(*) n FROM ai_reviews WHERE photo_id IN (?,?,?,?)",
                     (p1, p2, p3, p4)).fetchone()["n"]
    chk(n >= 1, f"판정 기록 적재 ({n}건)")
    rec = conn.execute("SELECT * FROM ai_reviews WHERE photo_id=?", (p1,)).fetchone()
    chk(rec and rec["route"] == "자동승인", "자동 승인 건의 경로가 '자동승인'으로 기록")

    # ⑥ 사람이 AI 판정을 뒤집으면 불일치로 남는가
    p5 = mkphoto(conn, case_id, "착공전", 60)
    ph = A.one(conn.execute("SELECT * FROM photos WHERE id=?", (p5,)))
    A._record_ai_review(conn, ph, "시공중", "사람검수", "테스트")
    conn.commit()
    rec = conn.execute("SELECT * FROM ai_reviews WHERE photo_id=? ORDER BY id DESC LIMIT 1",
                       (p5,)).fetchone()
    chk(rec and rec["agreed"] == 0, "사람이 다르게 고치면 '불일치'로 기록")

    # ⑦ 기준을 100으로 올리면 아무것도 자동 승인되지 않는다
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('ai_auto_threshold','100')")
    conn.commit()
    p6 = mkphoto(conn, case_id, "착공전", 95)
    chk(A._apply_ai_routing(p6) != "auto", "기준 100점에서 95점 사진 → 자동 승인 안 됨")

    # 원복
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('ai_auto_threshold',?)", (str(th),))
    # 검증용 사진 정리
    conn.execute("DELETE FROM ai_reviews WHERE photo_id IN (?,?,?,?,?,?)", (p1,p2,p3,p4,p5,p6))
    conn.execute("DELETE FROM photos WHERE id IN (?,?,?,?,?,?)", (p1,p2,p3,p4,p5,p6))
    conn.commit()
    conn.close()

    print("-" * 62)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
