# -*- coding: utf-8 -*-
"""스캔 599라운드 회귀 — api_settlements_export()(정산취소 CSV, 회계 대사용)가
   셀 정제를 공유 _xl_safe() 대신 로컬 _csv_safe() 로 따로 재구현하면서,
   트리거 아닌 제어문자 처리 범위가 갈라져 있던 결함.

   조사 배경 — round598 이 방금 손댄 api_export_xlsx·api_settlements_export
   두 내보내기를 다시 들여다보다가, _xl_safe()·_csv_safe() 형제 쌍이 이미
   5개 라운드(34·423·532·550·578)에 걸쳐 "수식주입 트리거 문자 집합(=+-@탭)"
   일치를 정밀 감사받았음을 확인했다 — 그런데 그 감사들은 전부 트리거 문자만
   봤고, **트리거가 아닌 제어문자를 보존하는 범위**는 서로 비교한 적이 없었다.

   실제 소스 대조(수정 전):
     _xl_safe(app.py, module-level)   — ch in ("\\t","\\n") or ch>=" " 를 보존(둘 다)
     _csv_safe(로컬, 이 함수 안)      — ch=="\\t" or ch>=" " 만 보존(개행은 삭제)

   실측(exec 격리, 수정 전 소스로): _xl_safe("1줄\\n2줄") == "1줄\\n2줄"(그대로)
   인데 _csv_safe("1줄\\n2줄") == "1줄2줄" — 개행이 **치환이 아니라 삭제**돼
   두 줄이 단어 경계 없이 붙어 버린다.

   실제 도달 경로 — api_settlement_void()(app.py:14645 부근)의 reason 은
   .strip() 만 하고 내부 개행은 그대로 저장한다(호출은 JSON body, 프런트가
   지금은 prompt() 를 쓰지만 API 계약 자체는 개행을 막지 않는다). 그렇게
   저장된, 여러 줄로 적은 정산취소 사유가 이 CSV(회계 대사용 — 이 함수 자신의
   docstring)에서만 줄바꿈이 사라진 채 말이 안 되게 붙어 나간다 — 같은 값이
   화면·감사로그·다른 어디에도 이렇게 깨지지 않는다.

   이 결함은 round221 이 이미 한 번 고친 것(api_export_xlsx 가 셀 정제를
   로컬에서 독자 재구현 — _xl_safe 자신의 문서 "내보내기 어디서든 같은 규칙을
   쓴다"를 어김)과 완전히 같은 근본원인이 다른 함수에 남아있던 두 번째
   사례다. round221 과 같은 처방 — 로컬 _csv_safe() 를 없애고 공유 _xl_safe()
   를 그대로 쓴다(partner_accounts.py 의 별도 _csv_safe() 는 업체명·지역·
   공종처럼 구조적으로 한 줄짜리인 값만 다뤄 개행 도달 경로가 없다 — 직접
   확인, 이번 라운드에서는 손대지 않음).

   [1] 소스 확인 — api_settlements_export() 함수 본문에 로컬 _csv_safe 정의가
       더 이상 없고, 셀 정제 호출이 _xl_safe(x) 로 바뀌었다. _xl_safe() 자신은
       손대지 않았으므로 개행 보존·탭우회 방어(round423) 모두 회귀 없음.
   [2] 실행 — 실제 Flask+DB. 개행이 포함된 취소사유를 가진 정산을 만들고
       CSV 내보내기를 실제로 호출해, 개행이 삭제되지 않고 그대로 담기는지
       확인. 같은 요청에서 수식주입 방어(=로 시작하는 값 접두)도 회귀 없이
       그대로 동작하는지 함께 확인.
   [3] 되돌리기 — view_functions 딕셔너리 항목만 임시로 옛 로컬 _csv_safe
       동작으로 바꿔치기해(디스크 무수정) 같은 데이터에서 실제로 개행이
       사라짐을 확인한 뒤 원복 — 이 테스트가 실제로 회귀를 잡아낼 능력이
       있음을 증명.

       python test_scan_round599_fixes.py
"""
import csv
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


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 599라운드 회귀 — 정산취소 CSV(api_settlements_export) 개행삭제")
print("=" * 72)

print("\n[1] 소스 확인")
_se = _py_fn_body(APP_SRC, "api_settlements_export")
chk("def _csv_safe" not in _se,
    "★★★★★ api_settlements_export 안에 로컬 _csv_safe 재구현이 더는 없다")
chk("_xl_safe(x) for x in" in _se,
    "★★★★★ 셀 정제가 공유 _xl_safe() 를 직접 쓴다(round221과 같은 처방)")
#  주석 속 역사적 언급(위 round599 설명)은 허용하고, 실제 코드로서의
#  호출/정의(`_csv_safe(`)가 남아있는 줄만 있으면 잡아낸다.
_live_csv_safe_lines = [ln for ln in _se.splitlines()
                        if "_csv_safe(" in ln and not ln.strip().startswith("#")]
chk(_live_csv_safe_lines == [],
    "★ 이 함수 본문에 _csv_safe 를 실제로 부르거나 정의하는 코드가 없다"
    "(주석 속 역사적 언급은 허용)", _live_csv_safe_lines)

#  _xl_safe 자신은 이번 라운드에서 손대지 않았다 — 개행 보존·탭우회 방어
#  (round423) 둘 다 기존 계약 그대로인지 exec 격리로 대조군 확인.
_xi0 = APP_SRC.index("def _xl_safe(v):")
_xi1 = APP_SRC.index("\ndef ", _xi0 + 1)
ns_xl = {}
exec(compile(APP_SRC[_xi0:_xi1], "<_xl_safe>", "exec"), ns_xl)  # noqa: S102 -- 우리 소스
_xl_safe = ns_xl["_xl_safe"]
chk(_xl_safe("1줄\n2줄") == "1줄\n2줄",
    "  대조군 — _xl_safe() 는 개행을 그대로 보존한다(회귀 없음)",
    repr(_xl_safe("1줄\n2줄")))
chk(_xl_safe("\t=1+1")[:1] == "'",
    "  대조군 — _xl_safe() 의 탭우회 수식주입 방어(round423)는 그대로(회귀 없음)")

print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 실제 재현")
_tmpdir = tempfile.mkdtemp(prefix="round599_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
os.environ["BOKGUON_OTP_POLICY"] = "off"
sys.path.insert(0, HERE)

MULTI = "1차 확인 후 재작성 필요\n담당자: 검증팀 (승인번호 R599)"
admin = None

try:
    import db as DB
    DB.init_db()
    import app as A

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r599admin','x','검증','최고관리자')")
    #  ⚠ 실제 저장 경로(api_settlement_void)는 .strip()만 하고 내부 개행은
    #    그대로 저장한다 — 여기서는 그 결과 상태를 직접 재현해 CSV 내보내기
    #    자체의 결함(이 라운드의 실제 수정 대상)에 집중한다.
    conn.execute(
        "INSERT INTO settlements(case_no,insurer,partner_name,amount,fee,payout,"
        "                        created_at,is_demo,void_status,void_reason,void_at) "
        "VALUES(?,?,?,?,?,?,datetime('now'),0,'취소',?,datetime('now'))",
        ("R599-001", "R599보험", "=1+1", 1000000, 100000, 900000, MULTI))
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "r599admin"; sess["admin_role"] = "최고관리자"; sess["admin_name"] = "검증"

    r = admin.get("/api/settlements/export")
    chk(r.status_code == 200, "STEP 정산 CSV 200", r.status_code)
    body_txt = r.get_data(as_text=True).lstrip("﻿")
    csv_rows = list(csv.reader(io.StringIO(body_txt)))
    head = csv_rows[0]
    i_case = head.index("접수번호")
    i_partner = head.index("시공업체")
    i_reason = head.index("취소사유")
    data_row = next((row for row in csv_rows[1:] if row[i_case] == "R599-001"), None)
    chk(data_row is not None, "★ 방금 만든 정산(R599-001)이 CSV에 실제로 담겼다",
        [row[i_case] for row in csv_rows[1:]])

    if data_row is not None:
        chk(data_row[i_reason] == MULTI,
            "★★★★★ 개행이 포함된 취소사유가 삭제되지 않고 그대로 담긴다"
            "(고치기 전엔 '1차 확인 후 재작성 필요담당자: ...'로 줄바꿈이 통째로 사라졌다)",
            repr(data_row[i_reason]))
        chk("\n" in data_row[i_reason],
            "★★★ 실제로 개행 문자 자체가 남아있다(공백 치환이 아니라 원문 그대로 보존)")
        chk(data_row[i_partner] == "'=1+1",
            "  회귀 없음 — 수식주입 방어(=로 시작하는 값 접두)는 공유헬퍼 통합 후에도 그대로",
            data_row[i_partner])
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 준비/실행(api_settlements_export)", f"{type(e).__name__} {e}")

print("\n[3] 되돌리기 — 로컬 _csv_safe(옛 동작)였다면 이 테스트가 실제로 잡아내는가")
try:
    if admin is None:
        raise RuntimeError("2단계가 실패해 admin 클라이언트가 없음 — 되돌리기 건너뜀")

    _orig_view = A.app.view_functions["api_settlements_export"]

    def _old_broken_view():
        """599라운드 이전 동작 재현 — 개행을 삭제하는 로컬 _csv_safe.
        ⚠ 디스크의 app.py 는 건드리지 않는다 — view_functions 항목만 이 함수
          호출 동안만 임시로 바꿔치고 바깥 try/finally 에서 반드시 원복한다."""
        def _old_csv_safe(v):
            if not isinstance(v, str):
                return v
            v = "".join(ch for ch in v if ch == "\t" or ch >= " ")  # 개행 보존 없음(수정 전 결함)
            return ("'" + v) if v[:1] in ("=", "+", "-", "@", "\t") else v
        conn2 = A.DB.get_db()
        row2 = conn2.execute(
            "SELECT case_no, partner_name, void_reason FROM settlements "
            "WHERE case_no='R599-001'").fetchone()
        conn2.close()
        buf2 = A.io.StringIO()
        w2 = A.csv.writer(buf2)
        w2.writerow(["접수번호", "시공업체", "취소사유"])
        w2.writerow([_old_csv_safe(row2["case_no"]), _old_csv_safe(row2["partner_name"]),
                     _old_csv_safe(row2["void_reason"])])
        return A.make_response(buf2.getvalue())

    A.app.view_functions["api_settlements_export"] = _old_broken_view
    try:
        r_old = admin.get("/api/settlements/export")
        rows_old = list(csv.reader(io.StringIO(r_old.get_data(as_text=True))))
        old_reason = rows_old[1][2]
        chk(old_reason == MULTI.replace("\n", ""),
            "★★★★★ 옛 로컬 _csv_safe 로 되돌리면 개행이 실제로 삭제돼 두 줄이 "
            "단어 경계 없이 붙는다 — 이 테스트가 실제로 회귀를 잡아낸다는 증거",
            repr(old_reason))
        chk("\n" not in old_reason,
            "★★★★ 옛 동작(재현)에는 개행 문자 자체가 남아있지 않다(인과관계 직접증명)")
    finally:
        A.app.view_functions["api_settlements_export"] = _orig_view

    #  원복 후 같은 요청이 다시 정상(개행 보존)으로 돌아오는지 — 바꿔치기가 안 샜다
    r_restored = admin.get("/api/settlements/export")
    rows_restored = list(
        csv.reader(io.StringIO(r_restored.get_data(as_text=True).lstrip("﻿"))))
    head_r = rows_restored[0]
    i_reason_r = head_r.index("취소사유")
    i_case_r = head_r.index("접수번호")
    restored_row = next((row for row in rows_restored[1:] if row[i_case_r] == "R599-001"), None)
    chk(bool(restored_row) and restored_row[i_reason_r] == MULTI,
        "★ 원복 후에는 다시 개행이 정상 보존된다(바꿔치기가 안 샜다)",
        repr(restored_row[i_reason_r]) if restored_row else None)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★★★ 되돌리기(api_settlements_export) 실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
