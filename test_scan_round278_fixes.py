# -*- coding: utf-8 -*-
"""스캔 278라운드 회귀 — compliance.py 도급 적법성 관문 결함 2건
   (compliance.py 사상 첫 주조사, 정밀조사 Agent가 발견 후 독립 재검증).

  [1][심각] WORK_MAJORS(app.py, 화면이 실제로 제공하는 12개 공종) 중
      '방음벽·휀스·펜스'가 WORK_RULES(compliance.py 의 도급 판정표)에 아예 없다
      (manage.py selfcheck 가 이미 "실측: 방음벽·휀스·펜스는 셋 다 없고"로 기록해
      둔 상태 — 경고만 하고 고치지는 않는 진단이었다). rule_for() 는 복합공종
      문자열("복합(A · B · C)") 전체에 부분일치를 걸어 **하나라도 걸리면 그걸로
      전체를 판정**했다 — 실측: '복합(방음벽·휀스·펜스 · 누수·배관·설비)' 가
      누수·배관·설비의 규칙(전문공사, 1500만원)만으로 판정돼, 판정표에 없는
      방음벽·휀스·펜스 몫은 위험도 평가 자체를 안 거친 채 800만원짜리 건이 그대로
      '도급가능'으로 통과했다(안전선 1200만원 이내). 이 파일 37행 자신의 원칙
      ("업종 매핑이 확정되지 않은 공종은 통과시키지 않는다")과 정면으로 어긋난다.
      복합공종을 app.py 가 이어붙이는 그대로(" · " 구분자) 토큰별로 쪼개, 하나라도
      판정표에 부분일치조차 없으면 전체를 '기타'(판정불가)로 내도록 수정 —
      개별 업종을 어떤 kind(배제/전문/타법)로 분류할지는 법률 판단이라 이번
      수정 범위 밖으로 남겨 둔다(파일 자신의 "아직 확정하지 못한 것" 절 참고).

  [2] 위 결함과 별개로, '기타'(판정불가)로 떨어지는 두 경로(①진짜 공종 미입력
      ②공종은 있는데 판정표에 없음)가 같은 "공종이 특정되지 않아" 문구를 써서,
      체크박스로 정확히 '방음벽·휀스·펜스'를 골라도 마치 아예 안 고른 것처럼
      보였다 — 진짜 원인(판정표 누락)을 감춰 운영자가 manage.py check 로 이어가지
      못했다. 공종이 실제로 있으면 그 값과 함께 "판정표에 없다"고 정확히 말하고,
      진짜 미입력일 때만 기존 문구를 그대로 쓰도록 수정(막는 방향 자체는 안 바뀜
      — 메시지 정확도만 개선).

  ⚠ 이 테스트는 임시 디렉터리의 격리 DB만 쓴다 — 운영 bokguon.db 는 전혀
    건드리지 않는다.

      python test_scan_round278_fixes.py
"""
import io
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

_tmpdir = tempfile.mkdtemp(prefix="round278_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


CP_SRC = read("compliance.py")
APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 278라운드 회귀 — compliance.py 복합공종 판정표 누락 미탐지")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
i_rf = CP_SRC.index("def rule_for(")
i_rf_end = CP_SRC.index("\n\n\ndef check_direct_contract(")
rf_body = CP_SRC[i_rf:i_rf_end]
chk('re.match(r"^복합\\(' in rf_body,
    "★★★★★ rule_for() 가 복합공종 문자열을 토큰별로 쪼개 대조한다"
    "(고치기 전엔 전체 문자열 부분일치만 있었다)")
#  ⚠ [라운드315] 원래는 "_fuzzy_hits(t) for t in tokens" 를 직접 찾았다 — 315라운드가
#    이 "토큰 하나라도 판정표에 없으면 기타" 판정을 rule_for(t) 재귀호출로 다시 써서
#    (여러 special 트레이드가 섞이면 종합공사로 승격시키는 기능을 같은 자리에 추가하며
#    함께 리팩터링됨) 그 리터럴이 사라졌다 — 동작(대조군 [2]가 실측)은 그대로 보존됐다.
#    검사 의도는 그대로이므로 새 코드 모양으로 문자열만 좁힌다.
chk('resolved = [rule_for(t) for t in tokens]' in rf_body
    and 'any(name == "기타" for name, _ in resolved)' in rf_body,
    "★★★★★ 토큰 하나라도 부분일치가 없으면 전체를 기타(판정불가)로 낸다")

i_cdc = CP_SRC.index("def check_direct_contract(")
i_cdc_end = CP_SRC.index('\n    if kind == "other_law"', i_cdc)
cdc_body = CP_SRC[i_cdc:i_cdc_end]
chk('raw = (category or "").strip()' in cdc_body and "아직 도급판정표에 없어" in cdc_body,
    "★★★★ '기타' 사유가 진짜 미입력과 판정표 누락을 구분해 말한다"
    "(고치기 전엔 둘 다 '공종이 특정되지 않아'로 뭉뚱그렸다)")

i_majors = APP_SRC.index("WORK_MAJORS = (")
majors_line = APP_SRC[i_majors:APP_SRC.index(")", i_majors)]
chk("방음벽·휀스·펜스" in majors_line,
    "STEP 화면 공종 목록(WORK_MAJORS)에 '방음벽·휀스·펜스'가 실제로 있다"
    "(있는데 판정표에만 없었다는 전제 확인)")

# ============================================================
print("\n[2] 실행 — 순수 함수 재현 (정밀조사 Agent가 찾은 시나리오)")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
import compliance as CP                                             # noqa: E402

try:
    r1 = CP.check_direct_contract("방음벽·휀스·펜스", 50_000)
    chk(r1["code"] == CP.NO_UNKNOWN and not r1["ok"],
        "STEP 단독 '방음벽·휀스·펜스'는 판정불가로 막힌다(원래도 안전한 방향)")
    chk("방음벽·휀스·펜스" in r1["reason"] and "판정표" in r1["reason"],
        "★★★★ 사유가 실제 공종명과 '판정표에 없다'는 진짜 원인을 정확히 말한다"
        "(고치기 전엔 '공종이 특정되지 않아'로 마치 미입력인 것처럼 보였다)",
        r1["reason"])

    r2 = CP.check_direct_contract("복합(방음벽·휀스·펜스 · 누수·배관·설비)", 8_000_000)
    chk(r2["code"] == CP.NO_UNKNOWN and not r2["ok"],
        "★★★★★★ 복합공종 중 하나가 판정표에 없으면 전체가 판정불가로 막힌다"
        "(고치기 전엔 누수·배관·설비 규칙만으로 800만원이 그대로 '도급가능'이 났다)",
        r2)

    r2b = CP.check_direct_contract("복합(누수·배관·설비 · 방음벽·휀스·펜스)", 8_000_000)
    chk(r2b["code"] == CP.NO_UNKNOWN and not r2b["ok"],
        "STEP 토큰 순서를 바꿔도(뒤에 와도) 똑같이 막힌다(순서 우연이 아님)")

    r3 = CP.check_direct_contract("복합(유리·샷시·자동문 · 교통안전시설)", 5_000_000)
    chk(r3["code"] == CP.NO_TRADE and not r3["ok"],
        "★★★★ 회귀 없음 — 둘 다 판정표에 있는 기존 복합공종(배제업종이 이겨야 함)은 "
        "여전히 정확히 배제업종으로 막힌다", r3)

    r4 = CP.check_direct_contract("누수·배관·설비", 5_000_000)
    chk(r4["code"] == CP.OK_DIRECT and r4["ok"],
        "★★★★ 회귀 없음 — 판정표에 있는 단독 공종은 여전히 정상적으로 도급가능이 난다", r4)

    r5 = CP.check_direct_contract("", 1000)
    chk(r5["code"] == CP.NO_UNKNOWN and not r5["ok"]
        and r5["reason"] == "공종이 특정되지 않아 적용 법률과 기준을 정할 수 없습니다. "
                             "사람이 공종을 분류한 뒤 다시 판정하세요.",
        "★★★ 회귀 없음 — 진짜 공종 미입력(빈 문자열)은 기존 문구 그대로 유지된다", r5)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드278 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — 실제 진입점 gate()/실DB 로 재현(app.py 가 실제로 부르는 그 함수)")
# ------------------------------------------------------------
try:
    import db as DB                                                 # noqa: E402
    DB.init_db()
    conn = DB.get_db()
    conn.execute(
        "INSERT INTO cases(case_no, category, est_price, is_demo) "
        "VALUES('R278-GAP', ?, 8000000, 0)",
        ("복합(방음벽·휀스·펜스 · 누수·배관·설비)",))
    conn.commit()
    cid = conn.execute("SELECT id FROM cases WHERE case_no='R278-GAP'").fetchone()["id"]

    res = CP.gate(conn, cid)
    chk(res["code"] == CP.NO_UNKNOWN and not res["ok"],
        "★★★★★★ 실제 gate()/실DB 경로로도 이 사건은 판정불가로 막힌다"
        "(app.py 의 5개 낙찰확정 지점이 전부 이 gate() 를 부른다)", res)
    conn.close()
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드278 [3] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
