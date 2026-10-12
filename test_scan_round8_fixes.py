# -*- coding: utf-8 -*-
"""8라운드 스캔 수정의 회귀 검사 — 돈의 산술 · 첫 사용자 · 시각경계 · 관측 · 퇴출후 · 오조작.

  ⚠ 이 라운드에서 가장 무서웠던 것은 **아무도 누르지 않아도 일어나는 손실**이다.
     보험사 등록 INSERT 가 fee_rate 를 비우지 않아, 매 기동 도는 마이그레이션이
     9% 계약을 10% 로 되돌렸다. 사람의 행위가 아니라 감사로그에도 안 남는다.

  서버가 필요 없다(로그인을 안 하므로 레이트리밋과 무관).
"""
import ast
import io
import os
import sqlite3
import sys
from datetime import datetime, timedelta, date

HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0


def chk(cond, name, got=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}   {got}")


def src(*parts):
    return io.open(os.path.join(HERE, *parts), encoding="utf-8").read()


def fn_source(tree, text, name):
    lines = text.splitlines(True)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return "".join(lines[node.lineno - 1:node.end_lineno])
    return ""


def main():
    app_s = src("app.py")
    mng_s = src("manage.py")
    ptl_s = src("templates", "partner_portal.html")
    app_t = ast.parse(app_s)
    mng_t = ast.parse(mng_s)

    print("[1] 돈 — 아무도 누르지 않아도 요율이 바뀌는가")
    chk("fee_rate_bp,fee_rate,contract_status" in app_s and "?,NULL,?,?,?" in app_s,
        "★ 보험사 등록이 fee_rate 를 NULL 로 적는다"
        " (안 적으면 DEFAULT 10 이 들어가고 재기동 때 계약 요율이 10% 로 원복된다)")
    ci = fn_source(mng_t, mng_s, "cmd_create_insurer")
    chk("fee_rate)" in ci and "NULL)" in ci,
        "★ manage.py create-insurer 도 fee_rate 를 비운다")
    st = fn_source(app_t, app_s, "api_settings_set")
    chk('"fee_rate": (0, 100)' not in st and "SETTABLE" in st,
        "★ 기본 수수료율이 정수 절사되지 않는다(9.5% 를 9% 로 저장하고 '저장되었습니다')")

    print("\n[2] 낙찰 — 세 경로가 같은 게이트를 지나는가")
    aw = fn_source(app_t, app_s, "api_insurer_award")
    chk('"PARTNER_NOT_ACTIVE"' in aw,
        "★ 보험사 낙찰 승인도 협력사 활성을 본다(어드민 두 곳에만 있었다)")
    chk(app_s.count('"PARTNER_NOT_ACTIVE"') >= 3,
        "낙찰 경로 세 곳 모두 같은 게이트를 쓴다",
        app_s.count('"PARTNER_NOT_ACTIVE"'))
    chk("COALESCE(p.status,'활성') = '활성'" in app_s,
        "비활성 업체의 입찰은 후보 목록에도 안 뜬다(고르면 교착이다)")

    print("\n[3] 오조작 — 되돌릴 수 없는 것에 안전장치가 있는가")
    chk("ACT.coReject" in ptl_s and "ACT.coAccept" in ptl_s and "coSend" in ptl_s,
        "★ 추가견적이 「나중에/거절/수락」 3지 선택이다"
        " (confirm 의 취소·ESC 가 곧 '거절 제출'이었다)")
    chk("전체 재경매로 넘어가며 되돌릴 수 없습니다" in ptl_s,
        "거절은 한 번 더 묻고, 무슨 일이 일어나는지 말한다")
    chk("dp_amt" in ptl_s and "dp_ko" in ptl_s and "ACT.dpArriveGo" in ptl_s,
        "★ 출동 실견적이 맨몸 prompt() 가 아니다(콤마·한글읽기·재확인)")
    chk("이 금액은 나중에 고칠 수 없습니다" in ptl_s,
        "정정할 수 없다는 사실을 입력 전에 말한다")
    #  이 프로젝트에 없는 CSS 클래스를 쓰면 모달이 스타일 없이 뜬다 — 실제로 겪었다
    for bad_cls in ('class="mtitle"', 'class="mbody"', 'class="mfoot"', 'class="lb"'):
        chk(bad_cls not in ptl_s,
            f"없는 CSS 클래스({bad_cls})를 쓰지 않는다")

    print("\n[4] 퇴출·해지 뒤 — 관계가 끝나면 흐름도 끊기는가")
    dw = fn_source(app_t, app_s, "deliver_webhook")
    chk('get("status") == "활성"' in dw,
        "★ 계약 해지된 보험사에게 웹훅이 나가지 않는다(인바운드만 status 를 봤다)")
    rt = fn_source(app_t, app_s, "sweep_webhook_retries")
    chk("JOIN insurers i ON i.id = d.insurer_id" in rt,
        "웹훅 재전송도 해지된 곳은 건너뛴다")
    pp = fn_source(mng_t, mng_s, "cmd_prune_personal")
    chk("'취소','미수선종결','유찰'" in pp,
        "★ 취소·미수선종결·유찰 사건의 피해자 정보도 파기 대상이다"
        " (completed_at 이 없어 어떤 시점에도 안 지워졌다)")
    chk("c.status IN ('시공중','완료보고지연'" in pp,
        "진행 중 사건이 있는 퇴출 업체의 계좌는 지우지 않는다(지급 의무는 낙찰 때 생긴다)")

    print("\n[5] 세션 — '지금의 계정 상태'를 따라가는가")
    chk("def _pw_sig(" in app_s and app_s.count('session["pw_sig"]') >= 4,
        "★ 비밀번호를 재발급하면 그 세션이 다음 요청에서 끊긴다",
        app_s.count('session["pw_sig"]'))
    chk("def _sub_account_dead(" in app_s,
        "★ 하위계정 삭제·정지가 열린 세션에 반영된다(portal_users 를 안 봤다)")
    chk("session[\"pw_sig\"] = _pw_sig(_newh)" in app_s,
        "내가 바꾼 비밀번호로는 튕기지 않는다(지문을 새로 맞춘다)")
    alive = fn_source(app_t, app_s, "_account_alive")
    chk("_sub_account_dead(conn)" in alive,
        "요청마다 도는 판정에 하위계정 검사가 들어 있다")

    print("\n[6] 시각 — 보증 마지막 날이 이미 만료인가")
    wl = fn_source(app_t, app_s, "_warranty_left")
    chk("end.date() - today" in wl,
        "★ 날짜끼리 뺀다(시각이 섞여 마지막 이틀이 만료로 찍혔다)")
    chk("_td(hours=9)" in wl,
        "★ 한국시간으로 센다(서버 로컬시각이면 UTC 서버에서 하루 어긋난다)")
    chk("start of month" in app_s and "start of month" in mng_s,
        "★ SQL 만료일도 말일 보정을 한다(SQLite 는 기본으로 다음 달로 넘긴다)")

    print("\n[7] 말일 보정이 실제로 맞는가 — SQL 을 직접 돌린다")
    ns = {}
    blk = mng_s[mng_s.index("_WEND = ("):mng_s.index("def cmd_prune_personal")]
    exec(blk, ns)
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cases(completed_at TEXT, warranty_months INT)")
    for done, mo, want in (("2026-08-31", 6, "2027-02-28"),
                           ("2026-10-31", 4, "2027-02-28"),
                           ("2026-01-31", 3, "2026-04-30"),
                           ("2028-02-29", 24, "2030-02-28"),
                           ("2026-03-15", 24, "2028-03-15")):
        conn.execute("DELETE FROM cases")
        conn.execute("INSERT INTO cases VALUES(?,?)", (done, mo))
        got = conn.execute(f"SELECT {ns['_WEND']} FROM cases").fetchone()[0]
        chk(got == want, f"{done} + {mo}개월 = {want}", got)
    conn.close()

    print("\n[8] 파이썬 쪽도 같은 날을 말하는가")
    os.environ.setdefault("BOKGUON_ENV", "dev")
    sys.path.insert(0, HERE)
    try:
        import app as APP
        today = (datetime.utcnow() + timedelta(hours=9)).date()
        for done, mo, want in (("2026-08-31", 6, date(2027, 2, 28)),
                               ("2026-01-31", 3, date(2026, 4, 30)),
                               ("2028-02-29", 24, date(2030, 2, 28))):
            left = APP._warranty_left({"completed_at": done, "warranty_months": mo})
            got = today + timedelta(days=left)
            chk(got == want, f"★ _warranty_left {done}+{mo}개월 → {want}", got)
        #  만료가 바로 오늘인 사건은 **아직 보증 중**이어야 한다(left>0 을 요구하는 곳이 있다)
        two_yrs_ago = today.replace(year=today.year - 2)
        l = APP._warranty_left({"completed_at": two_yrs_ago.strftime("%Y-%m-%d"),
                                "warranty_months": 24})
        chk(l == 0, "만료 당일의 잔여일이 0 이다(음수면 마지막 날이 이미 만료)", l)
        #  ★ 그리고 그 0 이 '아직 보증 중'으로 읽혀야 한다 — SQL 쪽과 같은 판정
        chk("left >= 0" in app_s,
            "★ 만료일 당일도 보증 기간에 포함된다(SQL 은 그렇게 보는데 파이썬만 달랐다)")
        chk("d.warranty_left>=0" in src("static", "admin.js"),
            "화면 표기도 같은 기준을 쓴다")
    except Exception as e:
        chk(False, "app 모듈로 보증 계산 검증", repr(e)[:90])

    print("\n[9] 알림·대량 — 앞 라운드 수정이 살아 있는가")
    chk("NOTIFY_MAX_CHARS" in app_s, "알림 본문 길이 상한")
    snd = fn_source(app_t, app_s, "sweep_send_notifications")
    chk("철 지난 출동 문자" in snd, "철 지난 출동 문자는 보내지 않는다")

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
