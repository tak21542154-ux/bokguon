# -*- coding: utf-8 -*-
"""스캔 669라운드 회귀(직접조사, 하위위임 없음) — manage.py cmd_prune_personal()의
독스트링이 실제 파기 항목 6개 중 3개(①②③)만 나열하고 나머지 3개(④종료(취소·
미수선종결·유찰) 사건 피해자정보 / ⑤하자보수 기록 텍스트 / ⑥해피콜 기록 텍스트)를
빠뜨리고 있던 결함(round666 핸드오프가 지목, 이번 라운드에서 실제 수정).

④⑤⑥은 코드 자체는 이미 오래전에 구현되고 개별 회귀테스트(142·146·495라운드)까지
끝나 있었다 — 이번 결함은 실행 로직이 아니라, 이 함수 자신의 "무엇을 지우는지"
설명(개인정보 보호법 제30조가 요구하는 "처리방침=실제 처리"의 일치)이 실제 코드를
따라가지 못하고 낡아 있었다는 점이다. 로직 자체(n1~n6 각 버킷)는 이미 다른 라운드가
개별로 증명했으므로 이번 테스트는 그걸 되풀이하지 않고, "독스트링이 주장하는 항목
수 == 실제로 동시에 살아있는 코드경로 수"라는, 이번 라운드가 새로 잡아낸 축만 본다.

⚠ manage.py는 app.py가 import하는 모듈이 아니라 독립 CLI라서, 이 라운드는
  app.py/서버 재기동·BUILD_HASH 로테이션이 필요 없다(495·475·482라운드와 같은 예외).

    python test_scan_round669_fixes.py
"""
import ast
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
print("  스캔 669라운드 회귀 — prune-personal 독스트링이 6개 중 3개만 나열")
print("=" * 72)

MARKERS = ["①", "②", "③", "④", "⑤", "⑥"]
KEYWORDS = ["도입 문의", "퇴출 협력사", "완료 사건", "취소", "하자보수 기록", "해피콜"]

#  되돌리기-증명용 — 라운드669 이전 실제 원문 그대로(파일은 전혀 안 건드리고
#  이 테스트 안에서만 독립 문자열로 보존한다).
OLD_DOCSTRING_BODY = (
    "    무엇을 지우는지:\n"
    "      ① 계약으로 이어지지 않은 도입 문의·입점 신청 — 수집 1년 경과분\n"
    "      ② 퇴출 협력사의 정산 계좌 — 미지급 정산이 없을 때만(돈이 남았으면 못 지운다)\n"
    "      ③ 완료 사건의 피해자 성명·연락처 — 하자담보(24개월) 만료 후\n"
)


def all_markers_present(text):
    return all(m in (text or "") for m in MARKERS)


# ============================================================
print("\n[1] 소스 확인 — AST로 뽑은 cmd_prune_personal() 독스트링·본문")
# ------------------------------------------------------------
tree = ast.parse(SRC, filename="manage.py")
fn_node = None
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "cmd_prune_personal":
        fn_node = node
        break
chk(fn_node is not None, "cmd_prune_personal 함수를 AST에서 찾았다")

doc = ast.get_docstring(fn_node) if fn_node else ""
chk(all_markers_present(doc),
    "★★★ 독스트링이 ①~⑥ 여섯 항목을 모두 나열한다(고치기 전엔 ③까지만 있었다)",
    doc)
for kw in KEYWORDS:
    chk(kw in doc, f"독스트링에 '{kw}' 항목 설명이 있다")

lines = SRC.splitlines(keepends=True)
fn_src = "".join(lines[fn_node.lineno - 1:fn_node.end_lineno]) if fn_node else ""
chk("total = n1 + n2 + n3 + n3b + n3c + n3d + n4 + n4b + n4c + n5 + n6" in fn_src,
    "실제 집계식은 여전히 6개 버킷(n1~n6, 부속 n3b/n3c/n3d/n4b/n4c 포함)을 전부 합산한다 "
    "— 독스트링을 3개에서 6개로 늘린 근거가 실제 코드와 일치")

# ============================================================
print("\n[2] 직접호출 증명 — 실제 로드된 함수 객체의 런타임 __doc__(소스 텍스트가")
print("    아니라 import된 모듈 속성)도 6개 항목을 담고 있는가")
# ------------------------------------------------------------
#  ⚠ manage/db는 import 시점에 BOKGUON_DB_PATH를 본다(비워두면 운영 bokguon.db를
#    가리키는 안전장치가 즉시 중단시킨다) — 두 모듈을 건드리는 [2][3] 모두를 위해
#    먼저 스크래치 경로부터 못박는다.
_tmpdir = tempfile.mkdtemp(prefix="round669_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import manage as M
    live_doc = M.cmd_prune_personal.__doc__
    chk(all_markers_present(live_doc),
        "★★★ import된 manage 모듈의 실제 함수 객체 __doc__ 도 ①~⑥ 전부 담고 있다",
        live_doc)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드669 [2] manage import", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 여섯 버킷을 동시에 채운 격리 DB에서 --dry-run 미리보기가")
print("    ①~⑥ 전부를 동시에 보여주는가(독스트링의 '6개' 주장이 실제 동작과 일치)")
# ------------------------------------------------------------
try:
    import db as DB
    DB.init_db()
    M2 = M

    conn = DB.get_db()

    # ① 1년 넘은 도입 문의(미전환)
    conn.execute(
        "INSERT INTO insurer_leads(company,status,created_at) "
        "VALUES('R669문의사','신규','2020-01-01 00:00:00')")

    # ② 퇴출 협력사 계좌 — 미지급 정산·열린 사건 없음(NOT EXISTS 둘 다 공짜로 충족)
    conn.execute(
        "INSERT INTO partners(name,partner_type,status,bank_name,bank_account_enc,"
        "                     bank_account_idx,bank_holder) "
        "VALUES('R669퇴출업체','시공사','퇴출','국민','ENC(1234)','idx-1234','홍길동')")

    # ③⑤⑥ 공유 — 준공 2020-01-01 완료 사건(하자담보 24개월+3년 다 지남)에
    #   완료된 하자기록(자유텍스트 포함)과 해피콜(피드백 포함)을 함께 매단다.
    #   defect 가 status='완료'(닫힘)라 ③의 NOT EXISTS(열린 하자) 조건도 그대로 충족.
    cid = conn.execute(
        "INSERT INTO cases(case_no,status,category,region,completed_at,warranty_months,"
        "                  victim_name,victim_phone,is_demo) "
        "VALUES('R669-DONE','완료','가드레일','서울','2020-01-01 10:00:00',24,"
        "       '홍길동','01011112222',0)").lastrowid
    conn.execute(
        "INSERT INTO defects(defect_no,case_id,case_no,title,content,resolution,reporter,"
        "                    reporter_type,status,severity,cost_bearer,created_at) "
        "VALUES('DEF-R669',?,?,'낡은 하자 제목','낡은 내용','낡은 조치','김검수','보험사',"
        "       '완료','중대','시행사','2020-06-01 10:00:00')", (cid, "R669-DONE"))
    conn.execute(
        "INSERT INTO happy_calls(case_id,score,feedback,called_by,created_at) "
        "VALUES(?,5,'홍길동 고객 응대 기록 — 매우 만족','이상담','2020-06-01 10:00:00')",
        (cid,))

    # ④ 종료(취소) 사건 — 보관기간(기본 90일) 훌쩍 지남
    conn.execute(
        "INSERT INTO cases(case_no,status,category,region,status_at,created_at,"
        "                  victim_name,victim_phone,is_demo) "
        "VALUES('R669-CANCEL','취소','가드레일','서울','2020-01-01 10:00:00',"
        "       '2020-01-01 10:00:00','박철수','01033334444',0)")
    conn.commit()

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = M2.cmd_prune_personal(["--dry-run"])
    preview = buf.getvalue()

    chk(rc == 0, "STEP cmd_prune_personal(--dry-run) 정상 종료(0)", rc)
    checks = [
        ("도입 문의 1건", "① 도입 문의 1건이 미리보기에 잡힌다"),
        ("퇴출 협력사 계좌 1건", "② 퇴출 협력사 계좌 1건이 잡힌다"),
        ("피해자 정보 1건", "③ 완료 사건 피해자 정보 1건이 잡힌다"),
        ("종료(취소·미수선·유찰) 사건 피해자 정보 1건", "④ 종료 사건 피해자 정보 1건이 잡힌다"),
        ("하자보수 기록", "⑤ 하자보수 기록 1건이 잡힌다"),
        ("해피콜 기록", "⑥ 해피콜 기록 1건이 잡힌다"),
    ]
    for needle, label in checks:
        chk(needle in preview,
            f"★★★ {label} — 독스트링이 새로 주장하는 6개 항목이 실제로 전부 동시에 "
            "살아있는 코드경로임을 증명(하나라도 죽어 있었다면 독스트링을 6개로 늘린 "
            "것 자체가 또 다른 과장이 됐을 것)", preview)

    still_there = conn.execute(
        "SELECT victim_name FROM cases WHERE case_no='R669-DONE'").fetchone()
    chk(still_there["victim_name"] == "홍길동",
        "--dry-run 은 실제로는 아무것도 지우지 않는다(대조군 — rollback 확인)")
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드669 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 되돌리기-증명 — 라운드669 이전의 실제 독스트링 원문(파일은 전혀 안")
print("    건드리고 문자열로만 재구성)은 이 라운드가 새로 요구하는 검사를 못 넘긴다")
# ------------------------------------------------------------
chk(not all_markers_present(OLD_DOCSTRING_BODY),
    "★★★ 되돌린(라운드669 이전) 독스트링 원문은 ④⑤⑥이 없어 6항목 검사에 실패한다 "
    "— 이 회귀테스트가 실제로 그 결함을 잡아낼 능력이 있음을 증명",
    OLD_DOCSTRING_BODY)
chk(OLD_DOCSTRING_BODY.count("①") == 1 and "④" not in OLD_DOCSTRING_BODY
    and "⑤" not in OLD_DOCSTRING_BODY and "⑥" not in OLD_DOCSTRING_BODY,
    "옛 원문은 ①~③만 있고 ④⑤⑥은 아예 등장하지 않는다(정확히 3/6만 있었다는 확인)")
chk(all_markers_present(doc),
    "대조 — 지금 실제 파일([1]에서 뽑은 독스트링)은 같은 검사를 통과한다(고침이 반영돼 있음)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
