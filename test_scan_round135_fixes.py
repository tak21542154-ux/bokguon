# -*- coding: utf-8 -*-
"""스캔 135라운드 회귀 — 협력사 입점신청 승인(api_application_update)이
   신청서의 마케팅 수신동의(agree_marketing)를 새로 만드는 partners 행의
   email_consent/sms_consent 에 반영하지 않아, 정상 절차로 동의까지 받은
   업체가 캠페인 화면(_campaign_recipients)에서 전부 '동의없음'으로
   분류돼 발송 대상에 영영 못 들어갔다(정보통신망법 §50① 동의 기준
   자체는 정확히 지키고 있었지만, 그 동의 신호가 반영되는 유일한 통로가
   빠져 있어 기능이 사실상 죽어 있었다).

  공개 신청 폼의 체크박스 문구("이메일/문자로 받아보겠습니다")가 두 채널을
  함께 명시하므로, 동의 하나를 email_consent·sms_consent 양쪽에 반영한다.

      python test_scan_round135_fixes.py
"""
import io
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 135라운드 회귀 — 입점신청 승인이 마케팅 수신동의를 안 옮겨 캠페인 대상에서 영구 누락")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_au = APP_SRC.index("def api_application_update(aid):")
i_au_end = APP_SRC.index("\ndef ", i_au + 1)
au_body = APP_SRC[i_au:i_au_end]
i_ins = au_body.index("INSERT INTO partners(")
ins_sql = au_body[i_ins:au_body.index('"""', i_ins)]
chk("email_consent" in ins_sql and "sms_consent" in ins_sql,
    "★★★ 승인 시 새 협력사 INSERT 문 열 목록에 email_consent·sms_consent 가 있다", ins_sql)
chk('1 if app_row.get("agree_marketing") else 0' in au_body,
    "★★★ 신청서의 agree_marketing 값을 실제로 바인딩한다")

# ============================================================
print("\n[2] 실행 — 실제 INSERT 문 + 실제 _campaign_recipients() 로 재현")
# ------------------------------------------------------------


def _mkdb():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE partners(id INTEGER PRIMARY KEY, name TEXT, partner_type TEXT, biz_no TEXT,
            ceo TEXT, major TEXT, category TEXT, region TEXT, address TEXT, phone TEXT, email TEXT,
            license TEXT, staff_count INTEGER, doc_status TEXT, status TEXT, source TEXT,
            created_at TEXT, email_consent INTEGER DEFAULT 0, sms_consent INTEGER DEFAULT 0,
            email_opt_out INTEGER DEFAULT 0, sms_opt_out INTEGER DEFAULT 0,
            login_id TEXT, email_source TEXT, lat REAL, lng REAL, geo_src TEXT);
    """)
    return conn


try:
    conn = _mkdb()
    app_row = {"company": "테스트건설", "partner_type": "시공사", "biz_no": "111-22-33333",
               "ceo": "김대표", "major": "가드레일", "category": "가드레일", "region": "서울",
               "address": "서울 송파구", "phone": "01011112222", "email": "t@example.com",
               "license": "정상", "staff_count": 5, "agree_marketing": 1}
    conn.execute(ins_sql, (
        app_row["company"], app_row.get("partner_type") or "시공사",
        app_row["biz_no"], app_row["ceo"], app_row["major"],
        app_row["category"], app_row["region"], app_row.get("address") or "",
        app_row["phone"], app_row["email"],
        app_row.get("license") or "", app_row.get("staff_count"),
        "정상", "활성", "입점신청 승인", "2026-08-27 12:00:00",
        1 if app_row.get("agree_marketing") else 0,
        1 if app_row.get("agree_marketing") else 0,
        #  [라운드155] 실제 함수가 이 자리에 lat,lng,geo_src 를 추가했다 — 이
        #  테스트는 동의반영이 목적이라 좌표는 없는(구버전 신청서) 경우로 둔다.
        app_row.get("lat"), app_row.get("lng"),
        "주소검색" if app_row.get("lat") is not None else None,
    ))
    conn.commit()
    row = conn.execute("SELECT email_consent, sms_consent FROM partners WHERE name='테스트건설'").fetchone()
    chk(row["email_consent"] == 1 and row["sms_consent"] == 1,
        "★★★ 승인 직후 실제 partners 행에 동의가 반영된다"
        "(고치기 전엔 둘 다 0으로 굳었다 — 실측)", dict(row))

    #  _campaign_recipients() 를 실제로 실행 — 격리를 위해 필요한 조각만 exec
    #  ⚠ 다음 top-level 지점이 def 가 아니라 @app.post(...) 데코레이터로
    #    시작할 수 있다(실측: 이 함수 바로 다음이 그랬다) — "\ndef " 만 찾으면
    #    데코레이터 줄까지 잘려 들어가 뒤에 아무 def 도 없는 채로 exec 되어
    #    SyntaxError 가 난다. "\ndef "와 "\n@" 중 먼저 오는 쪽에서 끊는다.
    i_cr = APP_SRC.index("def _campaign_recipients(conn, f):")
    _cands = [i for i in (APP_SRC.find("\ndef ", i_cr + 1), APP_SRC.find("\n@", i_cr + 1)) if i > 0]
    i_cr_end = min(_cands)
    cr_src = APP_SRC[i_cr:i_cr_end].rstrip()

    def _s_stub(v, n=None):
        """app.py:_s() 재구현 — [라운드607]이 _campaign_recipients()에 이 헬퍼
        호출을 추가해(raw d.get(...)이 JSON 비문자열이면 500이던 형제결함군
        수정), 이 exec 격리 네임스페이스에도 함께 넣어야 NameError가 안 난다."""
        if v is None:
            return ""
        t = v if isinstance(v, str) else str(v)
        t = t.strip()
        return t[:n] if n else t

    ns = {"rows": lambda cur: [dict(r) for r in cur.fetchall()],
          "_like_escape": lambda s: (s or "").replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_"),
          "_s": _s_stub}
    exec(compile(cr_src, "<campaign_recipients>", "exec"), ns)  # noqa: S102 -- 우리 소스, 실제 함수 실행
    _recipients = ns["_campaign_recipients"]
    ok, no_contact, opted, no_consent = _recipients(conn, {"channel": "문자"})
    chk(no_consent == 0 and len(ok) == 1 and ok[0]["name"] == "테스트건설",
        "★★★ 동의한 이 업체가 이제 캠페인 대상(ok)에 들어간다"
        "(고치기 전엔 no_consent=1·ok=0곳으로, 동의했는데도 발송 대상에서 빠졌다)",
        {"ok": [r["name"] for r in ok], "no_consent": no_consent})
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드135 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
