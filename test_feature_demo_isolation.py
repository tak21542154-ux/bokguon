# -*- coding: utf-8 -*-
"""[기능] 데모가 실운영 자리로 새지 않는가 — 회귀.

  왜 만들었나 (2026-08-18 실측) —
    화면·집계 23곳이 `bids.is_demo` · `dispatches.is_demo` ·
    `field_agreements.is_demo` · `notifications.is_demo` 로 데모를 거르는데,
    그 표식을 **채우는 코드가 어디에도 없었다.** 전 행이 0 이니 그 조건들은
    언제나 참 — 23곳 전부가 아무것도 못 걸렀다. 실제로 벌어진 일:
      ① 발주처 포털 「현장 견적 승인 대기」에 데모 2건이 떠 있었다.
         승인 라우트에도 데모 차단이 없어, 누르면 데모 사건이 '시공중' 으로
         배정되고 **실제 협력사에게 시공 지시 알림이 나간다.**
      ② 지급검수 리마인드가 데모 정산 1건을 세어 19일간 882통,
         사진검수는 875통. 눌러서 간 화면에는 그 행이 없다.
      ③ 협력사 '누적 제출' 이 78건(실제 76), 운영 KPI 출동 지표는 100% 데모.
      ④ 「오늘 할 일」의 '입점 신청 심사대기' 는 존재한 적 없는 상태값을 세어
         **영원히 0** 이었다(형제 3곳은 ('신규','서류검토') 를 쓴다).

  고친 방향 —
    읽는 23곳을 각각 고치지 않는다. **표식을 채우는 쪽**을 고쳤다
    (삽입 자리 6곳 + 기동마다 도는 백필). 그래야 새로 쓰는 질의가
    같은 실수를 반복하지 않는다.

  ⚠ 이 검사는 **문자열을 세지 않는다.** SQL 을 실제 DB 에 돌려 숫자를 본다 —
    조건이 파일에 적혀 있어도 안 먹는 경우를 여러 번 겪었다.
  ⚠ 운영 DB 를 절대 열지 않는다. 임시 파일에 스키마를 세워 쓴다.

      python test_feature_demo_isolation.py
"""
import io
import os
import re
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    try:
        return io.open(os.path.join(HERE, rel), encoding="utf-8").read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


def flat(src):
    """공백만 눌러 한 줄로 만든다.

      ⚠ **삼중따옴표를 걷어내면 안 된다.** 이 코드베이스의 SQL 은 전부
        삼중따옴표 안에 있다 — 처음에 주석 제거기가 그것까지 지우는 바람에
        검사가 빈 문자열을 뒤지며 **전부 통과**했다(거짓 초록).
      ⚠ 대신 검사에 쓰는 조각은 **주석 문장에 나올 수 없는 것**만 고른다.
        아래 ①에서 결함 패턴이 파일 전체에 0회임을 먼저 못박아, 주석에
        섞여 통과하는 길을 막는다."""
    return re.sub(r"\s+", " ", src)


#  ── 임시 DB — 운영·검증 어느 쪽도 건드리지 않는다 ─────────────
TMP = tempfile.mkdtemp(prefix="bokguon_demo_iso_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(TMP, "iso.db")
sys.path.insert(0, HERE)
import db as DB                                              # noqa: E402

conn = sqlite3.connect(os.environ["BOKGUON_DB_PATH"])
conn.row_factory = sqlite3.Row
DB.migrate(conn)

print("═" * 72)
print("  데모가 실운영 자리로 새지 않는가")
print("═" * 72)

#  실사건 1 · 데모 1 을 세우고, 각각에 자식행을 단다
conn.executescript("""
DELETE FROM cases; DELETE FROM auctions; DELETE FROM bids;
DELETE FROM dispatches; DELETE FROM field_agreements; DELETE FROM notifications;
INSERT INTO cases(id, case_no, status, is_demo) VALUES (1,'REAL-1','접수',0);
INSERT INTO cases(id, case_no, status, is_demo) VALUES (2,'DEMO-1','접수',1);
INSERT INTO auctions(id, case_id, status) VALUES (11,1,'진행'),(12,2,'진행');
INSERT INTO bids(id, auction_id, partner_id, partner_name, amount)
     VALUES (101,11,1,'실업체',1000),(102,12,2,'데모업체',2000);
INSERT INTO dispatches(id, case_id, round, status) VALUES (201,1,1,'수배중'),(202,2,1,'수배중');
INSERT INTO field_agreements(id, case_id, partner_id, partner_name, field_amount, status)
     VALUES (301,1,1,'실업체',500,'검토중'),(302,2,2,'데모업체',600,'검토중');
INSERT INTO notifications(id, ntype, channel, target, message, status, case_id)
     VALUES (401,'입찰','문자','실','x','발송대기',1),
            (402,'입찰','문자','데모','x','발송대기',2);
""")
conn.commit()

#  ── ① 백필이 실제로 채우는가 ────────────────────────────────
#   ⚠ **migrate() 를 부른다.** 예전 판은 `_backfill_child_is_demo` 를 직접 불러서,
#     migrate() 에서 그 호출을 통째로 빼도 검사가 통과했다(배선이 끊긴 걸 못 봤다).
#     기동할 때 실제로 도는 경로로 확인한다.
print("\n  ① 표식을 채우는 쪽 — 기동 시 백필")
DB.migrate(conn)
n_demo = sum(conn.execute(f"SELECT COUNT(*) FROM {t} WHERE COALESCE(is_demo,0)=1").fetchone()[0]
             for t in ("bids", "dispatches", "field_agreements", "notifications"))
chk(n_demo == 4, "★★ migrate() 가 데모 사건의 자식행 4개를 채운다", n_demo)


def demo_ids(table):
    return sorted(r[0] for r in conn.execute(
        f"SELECT id FROM {table} WHERE COALESCE(is_demo,0)=1"))


chk(demo_ids("bids") == [102], "★★ 입찰 — 데모만", demo_ids("bids"))
chk(demo_ids("dispatches") == [202], "★★ 출동 — 데모만", demo_ids("dispatches"))
chk(demo_ids("field_agreements") == [302], "★★ 현장합의 — 데모만", demo_ids("field_agreements"))
chk(demo_ids("notifications") == [402], "★★ 알림 — 데모만", demo_ids("notifications"))
chk(DB._backfill_child_is_demo(conn) == 0, "★ 두 번 돌려도 더 안 바꾼다(멱등)")
#  백필 자체가 migrate() 에 **배선되어 있는가** — 함수만 있고 안 부르면 소용없다
chk("_backfill_child_is_demo(conn)" in re.sub(r"#[^\n]*", "", read("db.py")),
    "★★ migrate() 가 백필을 실제로 부른다 (주석 처리되어 있지 않다)")

#  사람이 손으로 표시한 것을 지우지 않는다
conn.execute("UPDATE bids SET is_demo=1 WHERE id=101")
conn.commit()
DB._backfill_child_is_demo(conn)
chk(conn.execute("SELECT is_demo FROM bids WHERE id=101").fetchone()[0] == 1,
    "★★ 손으로 붙인 표식을 되돌리지 않는다 (채우기만 한다)")
conn.execute("UPDATE bids SET is_demo=0 WHERE id=101")
conn.commit()

#  ── ② 화면·집계 SQL 을 **실제로 돌려** 본다 ──────────────────
print("\n  ② 화면이 세는 숫자 — SQL 을 돌려 본다")
app_src = read("app.py")


def one(sql):
    return conn.execute(sql).fetchone()[0]


chk(one("SELECT COUNT(*) FROM bids WHERE COALESCE(is_demo,0)=0") == 1,
    "★★ 협력사 누적 제출 — 실사건 입찰만")
chk(one("SELECT COUNT(*) FROM dispatches WHERE COALESCE(is_demo,0)=0") == 1,
    "★★ 운영 KPI 출동 — 실사건만")
chk(one("""SELECT COUNT(*) FROM field_agreements f JOIN cases c ON c.id=f.case_id
            WHERE f.status='검토중' AND COALESCE(c.is_demo,0)=0""") == 1,
    "★★ 발주처 승인 대기 — 실사건만")
chk(one("SELECT COUNT(*) FROM notifications WHERE COALESCE(is_demo,0)=0") == 1,
    "★★ 발송 큐 — 실사건 알림만")

#  ── ③ 소스가 **사건의 표식**을 보는가 ────────────────────────
print("\n  ③ 어디를 보는가")
src = app_src                     # 원본 그대로 본다(SQL 이 삼중따옴표 안에 있다)
_flat = flat(src)
#  결함 패턴이 **파일 전체에 0회** — 주석에 섞여 통과하는 길을 먼저 막는다
chk(src.count("COALESCE(f.is_demo,0)=0") == 0,
    "★★ 발주처 승인 대기가 자식표(f) 대신 사건(c) 표식을 본다",
    src.count("COALESCE(f.is_demo,0)=0"))
chk("f.status=? AND COALESCE(c.is_demo,0)=0" in _flat,
    "★ 그 자리가 c.is_demo 로 바뀌어 있다",
    _flat[_flat.find("c.insurer_id=?"):][:90] if "c.insurer_id=?" in _flat else "못 찾음")

#  ── ④ 승인 라우트가 데모를 **서버에서** 막는가 ────────────────
print("\n  ④ 승인은 계약 성립 — 서버에서 막는다")
i = src.find("def api_insurer_field_agreement_decision")
body = src[i:i + 1400] if i >= 0 else ""
chk(i >= 0, "승인 라우트를 찾았다")
chk("is_demo" in body, "★★ 라우트가 사건의 데모 여부를 읽는다")
chk(re.search(r"if not c or .*is_demo", body) is not None,
    "★★ 읽기만 하는 게 아니라 **막는다**", body[body.find("if not c"):][:90])

#  ── ⑤ 리마인드·오늘 할 일 SQL 을 돌려 본다 ───────────────────
print("\n  ⑤ 30분마다 두드리는 알림 — 없는 일을 세지 않는가")
#  ⚠ **밀린 것이 데모뿐인 상태**를 먼저 만든다 — 그때 0건이어야 한다.
#    실사건 정산은 이미 검수를 마친 것으로 둔다(있기만 하면 세지 않는지도 함께 본다).
conn.executescript("""
DELETE FROM settlements; DELETE FROM photos;
INSERT INTO settlements(id, case_id, review_status, insurer_paid, is_demo, created_at)
     VALUES (1,1,'완료','입금완료',0,'2000-01-01 00:00:00'),
            (2,2,'대기','입금완료',1,'2000-01-01 00:00:00');
INSERT INTO photos(id, case_id, rel_path, review_status, created_at)
     VALUES (1,1,'a.jpg','완료','2000-01-01 00:00:00'),
            (2,2,'b.jpg','대기','2000-01-01 00:00:00');
""")
conn.commit()


def sql_of(marker, src_text):
    """소스에 적힌 SQL 문자열을 그대로 꺼낸다 — 내가 다시 쓰면 검사가 무의미하다."""
    j = src_text.find(marker)
    if j < 0:
        return None
    k = src_text.find('"""', j)
    return src_text[k + 3:src_text.find('"""', k + 3)] if k >= 0 else None


_SEG = r'"(?:[^"\\]|\\.)*"'


def call_sql(marker, src_text):
    """`marker(` 뒤에 이어붙은 큰따옴표 문자열들(파이썬 인접 문자열 연결)을 하나로 합친다.

      sql_of() 는 삼중따옴표 전용이라 `scalar("A" "B")` 같은 한 줄짜리 호출에는
      안 먹는다. 괄호 매칭 대신 **따옴표 짝**으로 끝을 찾는다 — SQL 문자열 안에
      `('완료','반려')` 처럼 괄호가 들어 있어도 헷갈리지 않는다."""
    m = re.search(re.escape(marker) + r"\(\s*((?:" + _SEG + r"\s*)+)\)", src_text)
    if not m:
        return None
    return "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))


def call_sql_all(marker, src_text):
    """call_sql() 의 복수형 — 같은 이름의 dict 키가 배지·며칠째 두 딕셔너리에
      반복되는 자리(도입문의_대기·입점_심사대기)를 **둘 다** 뜬다."""
    pat = re.compile(re.escape(marker) + r"\(\s*((?:" + _SEG + r"\s*)+)\)")
    return ["".join(re.findall(r'"((?:[^"\\]|\\.)*)"', m.group(1)))
            for m in pat.finditer(src_text)]


pay = sql_of('("reminder_payment", "지급검수리마인드"', app_src)
pho = sql_of('("reminder_photo", "사진검수리마인드"', app_src)
chk(pay is not None and pho is not None, "리마인드 SQL 을 소스에서 꺼냈다")
if pay and pho:
    n_pay = conn.execute(pay, (30,)).fetchone()[0]
    n_pho = conn.execute(pho, (30,)).fetchone()[0]
    chk(n_pay == 0, "★★ 지급검수 리마인드 — 데모뿐이면 0건(알림이 안 나간다)", n_pay)
    chk(n_pho == 0, "★★ 사진검수 리마인드 — 데모뿐이면 0건", n_pho)
    #  실사건이 밀리면 **제대로 울린다** — 경보를 죽인 것이 아님을 증명한다
    conn.execute("UPDATE settlements SET review_status='대기' WHERE id=1")
    conn.execute("UPDATE photos SET case_id=1 WHERE id=2")
    conn.commit()
    chk(conn.execute(pay, (30,)).fetchone()[0] == 1,
        "★★ 실사건이 밀리면 그대로 울린다 (경보를 죽인 것이 아니다)",
        conn.execute(pay, (30,)).fetchone()[0])
    chk(conn.execute(pho, (30,)).fetchone()[0] == 1, "★★ 사진도 실사건이면 울린다")
    conn.execute("UPDATE settlements SET review_status='완료' WHERE id=1")
    conn.execute("UPDATE photos SET case_id=2 WHERE id=2")
    conn.commit()

#  ── ⑥ 「오늘 할 일」 대기열 ─────────────────────────────────
print("\n  ⑥ 오늘 할 일 — 눌러서 간 화면과 같은 숫자인가")
m = re.search(r"TODAY_QUEUE = \[(.*?)\n\]", app_src, re.S)
chk(m is not None, "TODAY_QUEUE 를 찾았다")
if m:
    #  ⚠ 문자열을 세지 않고 **SQL 을 꺼내 돌린다.** 조각이 여러 줄로 이어 붙어
    #    있으니 따옴표 안쪽만 모아 잇는다(파이썬 인접 문자열 연결과 같은 방식).
    q_sqls = []
    for item in re.finditer(r'\(\s*"([^"]+)",\s*"[^"]*",\s*"(#[a-z]+)",\s*((?:"[^"]*"\s*)+)\)',
                            m.group(1)):
        label, go, chunk = item.group(1), item.group(2), item.group(3)
        q_sqls.append((label, go, " ".join(re.findall(r'"([^"]*)"', chunk))))
    chk(len(q_sqls) >= 5, "대기열 항목의 SQL 을 꺼냈다", len(q_sqls))
    got = {}
    for label, go, q in q_sqls:
        try:
            got[label] = conn.execute(q).fetchone()[0]
        except sqlite3.Error as e:
            got[label] = f"오류 {e}"
    #  지금 DB: 실사건 정산 1건(검수완료) · 데모 정산 1건(대기) · 데모 사진 1장(대기)
    chk(got.get("지급 검수가 밀려 있습니다") == 0,
        "★★ 지급 검수 대기 — 데모를 안 센다", got.get("지급 검수가 밀려 있습니다"))
    chk(got.get("사진 검수가 밀려 있습니다") == 0,
        "★★ 사진 검수 대기 — 데모를 안 센다", got.get("사진 검수가 밀려 있습니다"))
    chk(got.get("발주처 입금이 확인되지 않았습니다") == 0,
        "★★ 발주처 입금 — 데모를 안 센다", got.get("발주처 입금이 확인되지 않았습니다"))
    #  입점 신청 — 실제로 쓰이는 상태값을 세는가
    conn.execute("DELETE FROM partner_applications")
    conn.execute("INSERT INTO partner_applications(company, status, is_demo) VALUES('가',?,0)",
                 ("신규",))
    conn.commit()
    lab = "입점 신청이 심사를 기다립니다"
    q = dict((a, c) for a, b, c in q_sqls).get(lab, "")
    chk(bool(q) and conn.execute(q).fetchone()[0] == 1,
        "★★ 입점 신청 — '신규' 를 실제로 센다 (예전엔 없는 상태값이라 영원히 0)",
        conn.execute(q).fetchone()[0] if q else "SQL 못 찾음")

#  ── ⑦ notify() 가 표식을 채우는가 ───────────────────────────
print("\n  ⑦ 알림을 만들 때 표식을 채우는가")
ns = src[src.find("def notify("):]
ns = ns[:ns.find("\ndef ")] if "\ndef " in ns else ns[:4000]
chk("FROM cases WHERE id=?" in ns, "★★ 사건에서 데모 여부를 읽는다(호출부에 맡기지 않는다)")
#  ⚠ **INSERT 컬럼 목록에 실제로 실리는지**를 본다. 예전 판은 함수 안에
#    'is_demo' 라는 글자가 있기만 하면 통과해서, INSERT 에서 빼도 못 잡았다.
chk(any("is_demo" in cols for cols in re.findall(
        r"INSERT INTO notifications\s*\(([^)]*)\)", ns)),
    "★★ 그 값이 INSERT 컬럼 목록에 실린다")

#  ── ⑧ 삽입 자리 6곳이 표식을 채우는가 ───────────────────────
print("\n  ⑧ 새로 만들어지는 행 — 삽입 자리")
def insert_sites(text, table):
    """`INSERT INTO <표>(...)` 의 괄호 안 컬럼 목록을 전부 꺼낸다.

      ⚠ 줄바꿈을 건너야 한다 — 컬럼 목록이 두 줄에 걸친 자리가 있다.
        (grep 으로 세면 그 자리를 놓쳐 '고쳤는데 안 고친 것처럼' 보인다)"""
    return re.findall(re.escape(f"INSERT INTO {table}") + r"\s*\(([^)]*)\)", text)


disp = read("dispatch.py")
for text, table, least in ((disp, "dispatches", 3),
                           (disp, "field_agreements", 1),
                           (src, "bids", 2)):
    sites = insert_sites(text, table)
    ok = [s for s in sites if "is_demo" in s]
    chk(len(sites) >= least and len(ok) == len(sites),
        f"★★ {table} 삽입 {len(sites)}곳 전부가 표식을 채운다",
        f"{len(ok)}/{len(sites)}")

#  ── ⑨ 2라운드에서 새로 나온 네 자리 (2026-08-19) ────────────────
print("\n  ⑨ 협력사 공지 · 하자 목록 · 도입문의/입점신청 배지 · 출동관제")

#  ⑨-a 협력사 공지 — 실측: 뜨는 공지 2건이 전부 데모였다
_notices_q = call_sql("notices = rows(conn.execute", app_src)
chk(_notices_q is not None and "COALESCE(is_demo,0)=0" in _notices_q,
    "★★ 협력사 공지 조회에 데모 제외가 있다", _notices_q)
if _notices_q:
    conn.executescript("""
    DELETE FROM notices;
    INSERT INTO notices(title, body, audience, pinned, is_demo, created_at)
         VALUES ('데모 공지','x','전체',0,1,'2000-01-01'),
                ('실공지','x','전체',0,0,'2000-01-01');
    """)
    conn.commit()
    got_titles = [r["title"] for r in conn.execute(_notices_q).fetchall()]
    chk(got_titles == ["실공지"], "★★ 실행하면 실제로 데모 공지가 빠진다", got_titles)

#  ⑨-b 하자 — 목록·배지·요약이 같은 모집단을 쓰는가 (실측: 4건 표시 vs 실 1건)
conn.executescript("""
DELETE FROM defects;
INSERT INTO defects(defect_no, case_id, title, status, severity, is_demo)
     VALUES ('D-DEMO',2,'x','접수','중대',1), ('D-REAL',1,'x','접수','중대',0);
""")
conn.commit()
_open_q = call_sql("defect_open = scalar", app_src)
chk(_open_q is not None and "COALESCE(is_demo,0)=0" in _open_q,
    "★★ 하자 배지(defect_open)가 데모를 뺀다")
if _open_q:
    chk(conn.execute(_open_q).fetchone()[0] == 1, "★★ 배지 실행 결과도 1건",
        conn.execute(_open_q).fetchone()[0])
i_ad = src.find('def api_defects():')
j_ad = src.find("data = rows(conn.execute(q, p))", i_ad)
ad_body = src[i_ad:j_ad]
chk("COALESCE(is_demo,0)=0" in ad_body, "★★ 하자 목록(api_defects)이 데모를 뺀다")
i_sm = src.find("def api_defects_summary():")
sm_body = src[i_sm:src.find("@app.get(\"/api/settings\")", i_sm)]
chk("_live = " in sm_body and "COALESCE(is_demo,0)=0" in sm_body,
    "★★ 하자 요약카드(api_defects/summary)가 데모를 뺀다")
i_pd = src.find("def api_partner_defects():")
#  ⚠ [441라운드] 고정폭 600자였다 — 라운드441이 이 함수에 SELECT * 스키마
#    드리프트 방지용 화이트리스트(주석+컬럼나열)를 추가하면서 COALESCE(is_demo,0)=0
#    의 실제 위치가 911번째 문자로 밀려 이 창을 완전히 벗어났다(조건 자체는
#    그대로 있는데 창이 못 미쳐서 실패). 다음 함수 정의 이전까지는 안전하게
#    여유를 두고 1000자로 넓힌다.
pd_body = src[i_pd:i_pd + 1000]
chk("COALESCE(is_demo,0)=0" in pd_body, "★ 협력사 자기 하자 목록도 데모를 뺀다")

#  ⑨-c 도입문의·입점신청 배지 3곳씩 (실측: 25 vs 24, 22 vs 21)
#    ⚠ "도입문의_대기"·"입점_심사대기" 라는 같은 dict 키가 **배지 딕셔너리**와
#      **며칠째(드릴다운) 딕셔너리** 두 곳에 반복된다 — call_sql() 은 첫 번째
#      자리만 집으므로 call_sql_all() 로 **둘 다** 떠서 각각 실행한다.
#    ⚠ TODAY_QUEUE(⑥에서 이미 검증)에도 같은 문구가 나오므로 그 앞부분만 본다.
conn.executescript("""
DELETE FROM insurer_leads; DELETE FROM partner_applications;
INSERT INTO insurer_leads(company, status, is_demo, created_at)
     VALUES ('데모','신규',1,'2000-01-01'), ('실','신규',0,'2000-01-01');
INSERT INTO partner_applications(company, status, is_demo, created_at)
     VALUES ('데모','신규',1,'2000-01-01'), ('실','신규',0,'2000-01-01');
""")
conn.commit()
_ops_region = app_src[:app_src.find("TODAY_QUEUE = [")]
for label, marker, n_sites in (
        ("도입문의(배지·며칠째)", '"도입문의_대기": scalar', 2),
        ("입점신청(배지·며칠째)", '"입점_심사대기": scalar', 2),
        ("도입문의(콘솔요약)", "leads_pending = scalar", 1),
        ("입점신청(콘솔요약)", "apps_pending = scalar", 1),
):
    qs = call_sql_all(marker, _ops_region)
    chk(len(qs) == n_sites,
        f"★ {label} — 자리 수가 예상과 같다(자리 자체가 사라지지 않았다)", len(qs))
    for k, q in enumerate(qs):
        chk("COALESCE(is_demo,0)=0" in q, f"★★ {label} #{k+1} — 소스에 데모 제외가 있다", q)
        #  ① COUNT 형태만 실행해서 정확한 건수까지 확인한다(MAX/며칠째 형태는
        #    같은 조건이라도 반환값이 '경과일수'라 기대값을 픽셀 단위로 못 박기
        #    어렵다 — 소스 검사만으로 충분하다).
        if q.strip().upper().startswith("SELECT COUNT(*)"):
            try:
                got = conn.execute(q).fetchone()[0]
            except sqlite3.Error as e:
                got = f"오류 {e}"
            chk(got == 1, f"★★ {label} #{k+1} — 실행하면 실사건 1건만 잡힌다", got)

#  ⑨-d 출동 수배 관제 — 실측: dispatches 5건이 전부 데모였다
conn.executescript("""
DELETE FROM dispatches;
INSERT INTO dispatches(case_id, round, status, is_demo) VALUES (2,1,'실패',1),(1,1,'도착',0);
""")
conn.commit()
i_dl = src.find("def api_dispatch_list():")
j_dl = src.find("return jsonify({\"items\": data,", i_dl)
dl_body = src[i_dl:j_dl]
#  ⚠ 셋을 **각자** 확인한다. 이 함수엔 이미 데모를 거르던 자리가 둘 있었다
#    (need_dispatch·failed_cases) — 총 개수만 세면 그 둘의 몫에 가려
#    새로 고친 자리 하나를 빼도 문턱을 넘어 통과해 버린다(실측: 이 실수로
#    한 번 놓쳤다).

#  ⑨-d-1 목록(base) — 실제로 실행해서 데모가 빠지는지 본다
#    ⚠ app_src 전체가 아니라 **이 함수 안에서만** 찾는다 — "base = (\"\"\"" 로
#    시작하는 다른 쿼리가 파일 앞쪽(발주처 목록)에도 있어 sql_of() 가 그걸 집는다.
_base_q = sql_of("base = (", dl_body)
chk(_base_q is not None and "COALESCE(d.is_demo,0)=0" in _base_q,
    "★★ 출동관제 목록(base) 이 데모를 뺀다", _base_q[-120:] if _base_q else None)
if _base_q:
    #  ⚠ 절대 id 값을 기대하지 않는다 — 앞 절들이 이미 여러 행을 넣고 지워
    #    시퀀스가 1부터가 아니다. **내용**(case_id·status)으로 확인한다.
    got = [(r["case_id"], r["status"]) for r in conn.execute(_base_q + " ORDER BY d.id").fetchall()]
    chk(got == [(1, "도착")],
        "★★ 실행하면 실사건 출동(사건1·도착) 만 나온다(데모 사건2·실패는 빠짐)", got)

#  ⑨-d-2 상태별 집계(agg) — 자리를 정확히 찍어 확인한다
_agg_src = call_sql("agg = {r[0]: r[1] for r in conn.execute", dl_body)
chk(_agg_src is not None and "COALESCE(is_demo,0)=0" in _agg_src,
    "★★ 상태별 집계(agg) 가 데모를 뺀다", _agg_src)
_agg_q = "SELECT status, COUNT(*) FROM dispatches WHERE COALESCE(is_demo,0)=0 GROUP BY status"
chk(dict(conn.execute(_agg_q).fetchall()) == {"도착": 1},
    "★★ 실행하면 실사건 1건만 잡힌다(데모 3건 빠짐)",
    dict(conn.execute(_agg_q).fetchall()))

#  ⑨-d-3 미수선 건수(no_rep) — 자리를 정확히 찍어 확인한다
_i_nr = dl_body.find("no_rep = conn.execute(")
_nr_block = dl_body[_i_nr:_i_nr + 220] if _i_nr >= 0 else ""
chk(_i_nr >= 0 and "COALESCE(is_demo,0)=0" in _nr_block,
    "★★ 미수선 건수(no_rep) 가 데모를 뺀다", _nr_block)

conn.close()
try:
    for f in os.listdir(TMP):
        os.remove(os.path.join(TMP, f))
    os.rmdir(TMP)
except OSError:
    pass

print()
print("═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
for nm, dt in FAIL:
    print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
