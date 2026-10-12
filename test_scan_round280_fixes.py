# -*- coding: utf-8 -*-
"""스캔 280라운드 회귀 — 발송함 안내문 api_outbox() 결함 1건
   (272라운드 popbill_check.py 감사 도중 사용자가 인접 파일 app.py에서 직접
   지목한 부수 발견 — 272라운드 자체의 수정범위는 popbill_check.py였고 이
   결함은 그때 손대지 않았다).

  pb["ready"]=False 인 else 분기가 원인문구(why)를 sdk_installed·missing
  두 값만 보고 조립했는데, notify_popbill.status()의 ready 는 262라운드부터
  sdk_ok and not missing and not rotated 로 계산돼 "키 교체 직후·재시작 전"
  (key_rotated_pending_restart=True, missing=[], sdk_installed=True) 상태
  에서도 ready=False 가 될 수 있다 — 이 조합에서 why="미설정 항목: "+빈
  join()이 되어 화면에 빈칸 섞인 무의미한 문구만 뜨고 진짜 원인(재시작 필요)
  은 어디에도 안 보였다. notify_popbill.send()(262라운드)가 이미 쓰는
  문구를 그대로 재사용해 rotated 를 최우선 분기로 추가.

  ⚠ 이 파일은 원래 실체가 동시세션 라운드번호 경합(279→280→281, 세 세션이
    번호를 다투다 이 파일 내용이 dispatch.py 회귀로 덮어써짐)으로 유실돼
    재작성됐다 — app.py 의 실제 수정 자체는 14485행에 그대로 살아 있음을
    별도로 확인했고, 여기서는 그 수정을 검증하는 테스트만 새로 쓴다.
    app.py 를 일시적으로 되돌려 실패를 재현하는 통상 방식 대신(지금 이
    파일 하나에도 세션 5~6개가 동시에 붙어 있어, 공유 app.py 를 되돌리는
    바로 그 순간 다른 세션의 동시 편집과 부딪혀 새로운 경합을 낼 위험이
    있다), 고치기 전 공식(rotated 미고려)을 이 테스트 안에서 그대로
    재현해 그 공식이 실제로 빈 문구를 냈을 것임을 대조군으로 증명한다.

      python test_scan_round280_fixes.py
"""
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


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 280라운드 회귀 — 발송함 안내문 키교체대기 원인문구 누락")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인 — api_outbox() 함수 경계 안")
# ──────────────────────────────────────────────────────────────
i0 = APP_SRC.index("\ndef api_outbox():")
i1 = APP_SRC.index('\n@app.post("/api/outbox/send-now")', i0)
outbox_body = APP_SRC[i0:i1]
chk('if pb["key_rotated_pending_restart"]:' in outbox_body,
    "★★★★ api_outbox() 가 이제 키교체대기 상태를 별도 분기로 본다")
_i_rot = outbox_body.index('if pb["key_rotated_pending_restart"]:')
_i_sdk = outbox_body.index('elif not pb["sdk_installed"]:')
chk(_i_rot < _i_sdk,
    "★★★★★ 키교체대기 분기가 SDK미설치 분기보다 먼저 온다"
    "(else 로 밀리면 옛 공식처럼 무의미한 문구로 새 버린다)")
chk("연동 키가 서버 시작 뒤에 바뀌었으나" in outbox_body,
    "★★★ notify_popbill.send()(262라운드)가 쓰는 것과 같은 문구를 재사용한다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 대조군 — 고치기 전 공식이 실제로 빈 문구를 냈을 것임을 증명")
# ──────────────────────────────────────────────────────────────
def _old_why(pb):
    #  262라운드 이전 공식 그대로(rotated 미고려) — 지금은 app.py 에 없다.
    #  app.py 를 실제로 되돌리는 대신 그 공식만 여기 재현한다(위 docstring 참고).
    if not pb["sdk_installed"]:
        return "팝빌 SDK 미설치 — pip install -r requirements.txt"
    return "미설정 항목: " + ", ".join(pb["missing"])


_old_result = _old_why({"sdk_installed": True, "missing": [],
                         "key_rotated_pending_restart": True})
chk(_old_result == "미설정 항목: ",
    "★★★★★ 대조군 — 옛 공식은 '키교체대기·SDK있음·미설정없음' 조합에서 "
    "빈칸뿐인 문구를 냈다(고쳐야 했던 바로 그 결함)", repr(_old_result))

# ══════════════════════════════════════════════════════════════
print("\n[3] 실행(Flask) — 실제 /api/outbox 응답에서 세 조합 검증")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round280_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    #  [라운드480] "dev 기본값이면 데모 시드가 admin 계정을 넣어준다"에
    #    암묵 의존했었다 — BOKGUON_SEED_DEMO=0(이 세션이 전체배터리를 돌릴
    #    때 항상 명시하는 값, run_all_tests.py를 거쳐 이 서브프로세스까지
    #    그대로 전달됨)이면 시드가 꺼져 admins 테이블이 비고, 그 상태로
    #    session["admin"]="admin"만 심으면 _account_alive() 류 검사가
    #    존재하지 않는 계정으로 판정해 /api/outbox가 200 대신 리다이렉트를
    #    낸다 — 100% 재현되는 결정론적 버그였다(실측: SEED_DEMO=0일 때
    #    항상 실패, 안 줄 때 항상 통과 — "가끔 실패"가 아니었다). 다른
    #    모든 서브프로세스 워커(463·469·470·475·477·479라운드)처럼 시드
    #    여부와 무관하게 이 테스트 스스로 계정을 만든다. 데모 시드가 켜져
    #    있으면 이미 'admin'이 있을 수 있으므로(username UNIQUE, db.py:1913)
    #    OR IGNORE로 있든 없든 안전하게 보장만 한다.
    conn = DB.get_db()
    conn.execute("INSERT OR IGNORE INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','최고관리자')")
    conn.commit()
    conn.close()
    import app as A

    c = A.app.test_client()
    with c.session_transaction() as sess:
        sess["admin"] = "admin"
        sess["admin_role"] = "최고관리자"
        sess["admin_name"] = "검증"

    def _fake_status(missing=(), rotated=False, sdk_installed=True):
        return {"sdk_installed": sdk_installed, "configured": not missing,
                "missing": list(missing), "test_mode": True, "sender": None,
                "ats_template": False, "ready": False,
                "key_rotated_pending_restart": rotated}

    def _hit(**kw):
        A.POPBILL.status = lambda: _fake_status(**kw)
        r = c.get("/api/outbox")
        return r.status_code, (r.get_json() or {}).get("notice", "")

    sc1, notice1 = _hit(rotated=True)
    chk(sc1 == 200 and "재시작" in notice1,
        "★★★★★ 키교체대기 상태 — 실제 응답 안내문이 '재시작'을 언급한다"
        "(고치기 전엔 빈칸뿐인 문구였다)", notice1)

    sc2, notice2 = _hit(sdk_installed=False)
    chk(sc2 == 200 and "SDK 미설치" in notice2,
        "STEP 대조군 — SDK 미설치는 그 문구 그대로 나온다(과잉수정 아님)", notice2)

    sc3, notice3 = _hit(missing=["POPBILL_SECRET_KEY"])
    chk(sc3 == 200 and "POPBILL_SECRET_KEY" in notice3 and "재시작" not in notice3,
        "STEP 대조군 — 진짜 미설정 항목이 있으면 그 항목명이 그대로 나온다"
        "(과잉수정 아님)", notice3)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드280 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
