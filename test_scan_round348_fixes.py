# -*- coding: utf-8 -*-
"""
348라운드 회귀 — api_campaign_create()(app.py:8887, POST /api/campaigns)의
251라운드 중복방지가 BEGIN IMMEDIATE **밖**에서 확인해, 두 요청이 거의
동시에 도착하면(더블클릭이 밀리초 단위로 두 HTTP 요청을 보내는 흔한
패턴) 여전히 완전히 같은 캠페인이 두 건 이상 만들어지던 결함[중간,
회귀유형 — 데이터정합성/이중발송 위험].

  배경: 200라운드 이후 신규기능(campaigns·change_orders·field_agreements
  등)의 동시성 방어를 90·94·117·190라운드가 다진 낙찰·정산 계열과
  대조하는 조사에서 발견. api_campaign_create()는 이미 251라운드가
  "30초 이내 같은 제목·채널 캠페인이 있으면 새로 안 만들고 그 캠페인을
  그대로 돌려준다"는 중복방지를 넣어 뒀는데(8919~8926행), 그 확인용
  SELECT가 `BEGIN IMMEDIATE`(옛 8927행) **앞**에 있었다 — SQLite에서
  일반 SELECT는 아무 락도 잡지 않으므로, 두 요청 A·B가 그 SELECT를
  서로의 커밋 전에(즉 A의 INSERT가 아직 안 보이는 시점에) 둘 다 지나
  가면 둘 다 "중복 없음"으로 판단한다. 그 뒤 `BEGIN IMMEDIATE`가 둘을
  순서대로 직렬화하긴 하지만(SQLite 쓰기 락), 그때는 이미 두 요청 다
  "새로 만들어도 된다"고 확정한 뒤라 직렬화돼도 각자 INSERT를 실행해
  버린다 — 사람이 두 번 나눠 누르는 정도의 간격(수백ms 이상)에서는
  둘째 클릭의 SELECT가 첫째의 커밋을 보게 되어 막히지만, 더블클릭이
  두 HTTP 요청을 거의 동시에(밀리초 단위로) 보내는 경우엔 못 막는다.
  이 코드베이스가 낙찰·정산 등 원래부터 있던 기능에 이미 확립한 원칙
  ("확인은 반드시 락을 쥔 다음에 다시 한다", 94·117·190라운드)을 그대로
  적용해, 중복확인 SELECT를 `BEGIN IMMEDIATE` **뒤**로 옮겼다 — 이제
  둘째 요청은 락을 얻는 시점에 이미 첫째의 커밋이 끝나 있어 정확히
  잡는다. 지금은 실제 발송 대행사 연동이 없어(화면 자체 안내) 중복
  캠페인 자체가 당장 이중발송으로 이어지진 않지만, 연동되는 순간
  그대로 이중발송 경로가 된다는 것은 251라운드 주석이 이미 지적한 대로.

  같은 조사에서 함께 확인한 api_schedule_event_add()(app.py:17784)의
  "트랜잭션 없음" 지적은 독립검증 결과 오판으로 판단해 제외 — 이 함수는
  check-then-act가 아니라 단순 단일 INSERT이고, 한 사건에 여러 일정이
  생기는 것은 캘린더 기능의 정상 동작(같은 사건에 "1차 방문"·"2차
  방문" 등 서로 다른 일정을 의도적으로 여러 건 등록할 수 있어야 한다)
  이라 애초에 막을 대상이 아니다.

  실행기반 검증: 실제 Flask app.test_client() 5개를 각자 독립 세션으로
  인증시킨 뒤 threading.Barrier로 완전히 동시에(같은 제목·채널·본문)
  POST 시켜, DB에 실제로 몇 건이 만들어지는지 실측한다(test_dispatch.py
  가 이미 쓰는 barrier+threading 기법을 그대로 재사용).
"""
import json
import os
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

_scratch = tempfile.mkdtemp(prefix="bokguon_r348_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_scratch, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"

PASS = FAIL = 0


def chk(cond, msg, detail=None):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [OK]   {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {msg}" + (f"   {detail}" if detail else ""))


def read(rel):
    with open(os.path.join(HERE, rel), encoding="utf-8") as f:
        return f.read()


print("=" * 74)
print("  스캔 348라운드 회귀 — 캠페인 동시생성(BEGIN IMMEDIATE 밖 중복확인)")
print("=" * 74)

print("\n[1] 소스 확인")
APP_SRC = read("app.py")
i0 = APP_SRC.index("def api_campaign_create(")
i1 = APP_SRC.index("\n\n\n@app.get(\"/api/campaigns/<int:cmid>\")")
fn_src = APP_SRC[i0:i1]
i_begin = fn_src.index("BEGIN IMMEDIATE")
i_dup_select = fn_src.index("SELECT id FROM campaigns WHERE title=?")
chk(i_dup_select > i_begin,
    "★★★★★ 중복확인 SELECT가 BEGIN IMMEDIATE 뒤로 옮겨졌다(락을 쥔 다음에 확인)",
    f"begin@{i_begin} dup_select@{i_dup_select}")
chk("conn.rollback(); conn.close()" in fn_src,
    "★★★ 중복 발견 시 열려 있던 트랜잭션을 rollback으로 정리한다(그냥 close만 하지 않는다)")

print("\n[2] 실행 확인 — 실제 Flask 서버로 5개 요청을 완전히 동시에 보낸다")

import db as DB  # noqa: E402
DB.init_db(seed_demo=True)
import app as A  # noqa: E402

conn = DB.get_db()
#  발송대상(ok)이 최소 1곳 있어야 NO_RECIPIENT 로 조기반환되지 않는다(333라운드 픽스처 재사용)
conn.execute(
    "INSERT INTO partners(name,partner_type,status,category,major,region,email,"
    "                     email_opt_out,email_consent,created_at) "
    "VALUES('R348수신자','시공사','활성','가드레일','전기','서울','ok@r348.test',0,1,?)",
    (DB.now(),))
conn.commit()

N = 5
_tok = "r348-admin-csrf"
clients = []
for _i in range(N):
    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "staff"
        sess["admin_role"] = "중간관리자"
        sess["_csrf"] = _tok
    clients.append(c)

#  ⚠ 처음엔 요청 시작 지점에만 threading.Barrier 를 둬 봤는데, 5개 스레드가
#    "거의 동시에" 출발해도 실제 위험구간(중복확인 SELECT ~ BEGIN IMMEDIATE
#    사이, 코드 몇 줄뿐)은 GIL 전환 간격보다도 좁아 실전에서 거의 안 겹쳤다
#    (실측: 되돌린 코드로도 회귀 재현 실패) — 자연스러운 스레드 스케줄링에
#    기대지 않고, 270라운드가 이미 쓴 것과 같은 "연결 프록시로 정확한 지점에
#    수동 배리어를 심는다" 기법으로 그 좁은 구간을 강제로 넓힌다. DB.get_db()
#    가 돌려주는 연결의 execute() 를 감싸, **바로 그 중복확인 SQL**을 실행하는
#    순간에만 Barrier(N) 로 5개 스레드를 전부 모은다 — 그러면 5개 다 "아직
#    아무도 안 만들었다"를 보고 나서야(옛 코드 기준) 각자 진행하므로, 옛
#    코드는 100% 재현되고 고친 코드는 그 SELECT 자체가 락 뒤로 옮겨져 있어
#    다른 스레드가 이미 커밋한 뒤에만 이 지점에 도달해 배리어가 걸리지 않는다
#    (고친 코드에서 이 배리어가 실제로 안 걸리는 것 자체가 수정이 제대로
#    됐다는 방증 — 그래서 timeout 을 넉넉히 주고 타임아웃 자체를 실패로 보지
#    않는다).
#  ⚠ 배리어 타임아웃은 db.py 의 PRAGMA busy_timeout(기본 8000ms)보다 반드시
#    짧아야 한다 — 고친 코드에서 이 지점에 도달하는 건 항상 딱 1개 스레드뿐
#    (BEGIN IMMEDIATE 락을 쥔 그 스레드)이라 Barrier(N=5) 는 항상 시간초과로
#    끝나는데, 그 시간이 busy_timeout 보다 길면 락을 기다리던 나머지 스레드들이
#    "database is locked" 로 이 배리어보다 먼저 죽어(진짜 결함이 아니라 이
#    테스트 자신이 만든 인위적 장시간 락 보유 때문) 500 이 섞여 나온다.
_dup_sql_marker = "SELECT id FROM campaigns WHERE title=?"
_conn_barrier = threading.Barrier(N, timeout=1)
_real_get_db = DB.get_db


class _BarrieredConn:
    def __init__(self, real):
        self._real = real

    def execute(self, sql, *a, **kw):
        if _dup_sql_marker in sql:
            try:
                _conn_barrier.wait()
            except threading.BrokenBarrierError:
                pass
        return self._real.execute(sql, *a, **kw)

    def __getattr__(self, name):
        return getattr(self._real, name)


def _patched_get_db():
    return _BarrieredConn(_real_get_db())


A.DB.get_db = _patched_get_db

responses = [None] * N
errors = []


def fire(idx):
    try:
        r = clients[idx].post(
            "/api/campaigns", headers={"X-CSRF-Token": _tok},
            json={"title": "R348동시캠페인", "channel": "메일", "subject": "제목",
                  "body": "본문", "ptype": "시공사", "major": "전기",
                  "region": "서울", "no_login": False})
        responses[idx] = (r.status_code, r.get_json() or {})
    except Exception as e:                                          # noqa: BLE001
        errors.append(repr(e))


threads = [threading.Thread(target=fire, args=(i,)) for i in range(N)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=20)

A.DB.get_db = _real_get_db  # 이후 검증 쿼리는 원래 연결 그대로

chk(not errors, "  경합 중 예외 없음(스레드 자체가 죽지 않았다)", errors[:3])
chk(all(r is not None for r in responses), "  5개 요청 전부 응답을 받았다", responses)

ok_responses = [r for r in responses if r and r[0] == 200 and r[1].get("ok") is True]
chk(len(ok_responses) == N,
    f"  5개 요청 전부 200/ok로 응답한다(경합 자체가 요청을 실패시키지 않는다)",
    responses)

winners = [r for r in ok_responses if not r[1].get("duplicate")]
dupes = [r for r in ok_responses if r[1].get("duplicate")]
chk(len(winners) == 1,
    f"★★★★★ 동시 {N}개 요청 중 정확히 1건만 '새로 생성'으로 응답한다(고치기 전엔 락 밖 확인 탓에 "
    f"2건 이상이 새로 생성될 수 있었다)",
    f"winners={len(winners)} dupes={len(dupes)}")
if winners and dupes:
    win_id = winners[0][1]["id"]
    chk(all(d[1].get("id") == win_id for d in dupes),
        "  나머지 요청들은 전부 그 1건과 같은 id를 가리킨다", [d[1] for d in dupes])

row = conn.execute(
    "SELECT COUNT(*) FROM campaigns WHERE title=? AND channel=?",
    ("R348동시캠페인", "메일")).fetchone()
chk(row[0] == 1,
    f"★★★★★ 실제 DB에도 캠페인이 정확히 1건만 생성됐다(고치기 전엔 2건 이상 생길 수 있었다)",
    f"실제 {row[0]}건")

if winners:
    win_id = winners[0][1]["id"]
    tcnt = conn.execute(
        "SELECT COUNT(*) FROM campaign_targets WHERE campaign_id=?", (win_id,)).fetchone()[0]
    chk(tcnt == 1,
        "  수신자 스냅샷(campaign_targets)도 중복 생성되지 않았다(1곳만 씨앗으로 심었으므로 1건)",
        f"실제 {tcnt}건")

# 대조군 — 제목이 다른 요청은 동시에 와도 각자 독립적으로 생성된다(과잉차단 아님)
c_a, c_b = A.app.test_client(), A.app.test_client()
for c in (c_a, c_b):
    with c.session_transaction() as sess:
        sess["admin"] = "staff"; sess["admin_role"] = "중간관리자"; sess["_csrf"] = _tok
ra = c_a.post("/api/campaigns", headers={"X-CSRF-Token": _tok},
              json={"title": "R348캠페인A", "channel": "메일", "subject": "제목",
                    "body": "본문", "ptype": "시공사", "major": "전기",
                    "region": "서울", "no_login": False})
rb = c_b.post("/api/campaigns", headers={"X-CSRF-Token": _tok},
              json={"title": "R348캠페인B", "channel": "메일", "subject": "제목",
                    "body": "본문", "ptype": "시공사", "major": "전기",
                    "region": "서울", "no_login": False})
ja, jb = ra.get_json() or {}, rb.get_json() or {}
chk(ra.status_code == 200 and rb.status_code == 200
    and not ja.get("duplicate") and not jb.get("duplicate")
    and ja.get("id") != jb.get("id"),
    "  대조군 — 제목이 다른 캠페인 둘은 과잉차단 없이 각자 정상 생성된다",
    (ja, jb))

conn.close()

print(f"\n{'=' * 74}\n  통과 {PASS} · 실패 {FAIL}\n{'=' * 74}")
sys.exit(1 if FAIL else 0)
