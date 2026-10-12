# -*- coding: utf-8 -*-
"""10라운드 확정 결함 회귀 테스트.

  이 라운드의 절반은 **9라운드 수정이 만든 결함**이었다.
  고친 척(표시만 내리고 집행은 원본)·순서를 안 봐서 무효(go-live)·
  값을 빼 놓고 화면은 그대로 읽음(combined_amount → 0원).
  그래서 여기서는 문자열 확인에 기대지 않고 **실제로 돌려 본다** —
  상한 산술을 계산하고, 시드 게이트를 진짜 DB 로 밟고, 설정 검증 블록을 실행한다.

      python test_scan_round10_fixes.py
"""
import ast
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


def read(rel, enc="utf-8"):
    try:
        return io.open(os.path.join(HERE, rel), encoding=enc).read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


def strip_comments(text, marks=("#", "//")):
    """주석 제거 — 설명문을 코드로 오독하지 않기 위해(9라운드에서 3번 당했다)."""
    return "\n".join(ln for ln in text.splitlines()
                     if not any(ln.strip().startswith(m) for m in marks))


APP = read("app.py")
MNG = read("manage.py")
DBS = read("db.py")
TREE = ast.parse(APP)


def func_src(name, tree=TREE):
    for nd in ast.walk(tree):
        if isinstance(nd, (ast.FunctionDef, ast.AsyncFunctionDef)) and nd.name == name:
            return ast.unparse(nd)
    return None


#  떼어낸 함수가 참조하는 app.py 의 모듈 상수를 **소스에서 그대로** 읽어 온다.
#  ⚠ 숫자를 여기에 베껴 쓰면 app.py 가 바뀌어도 테스트는 옛 값으로 계속 통과한다
#    (9라운드에 상한 공식을 베꼈다가 없어진 식을 검사하고 있었다).
_CONSTS = {}
for _nd in TREE.body:
    if isinstance(_nd, ast.Assign) and len(_nd.targets) == 1 \
            and isinstance(_nd.targets[0], ast.Name) and isinstance(_nd.value, ast.Constant):
        _CONSTS[_nd.targets[0].id] = _nd.value.value


def load_func(name):
    """app.py 에서 함수 하나만 떼어 **진짜로 실행**한다."""
    for nd in ast.walk(TREE):
        if isinstance(nd, ast.FunctionDef) and nd.name == name:
            ns = dict(_CONSTS)
            exec(compile(ast.Module(body=[nd], type_ignores=[]), "<x>", "exec"), ns)
            return ns[name]
    return None


print("═" * 70)
print("  10라운드 회귀 — 9라운드 부작용 정정 + 데이터 파괴·설정·상태 교착")
print("═" * 70)

# ══════════════════════════════════════════════════════════════════
print("\n[1] 철칙 4 — 재경매 상한이 원 낙찰가를 흘리지 않는다")
# ══════════════════════════════════════════════════════════════════
cap = load_func("_reauction_cap")
chk(cap is not None, "★ _reauction_cap 이 존재한다(표시·집행 공통)")
if cap:
    bad = []
    for inc, add in ((7_200_000, 950_000), (3_400_000, 120_000),
                     (12_800_000, 2_050_000), (900_000, 80_000), (5_000_000, 100_000)):
        co = {"requested_amount": add, "combined_amount": inc + add}
        if cap(co, "전체재경매") - add == inc:
            bad.append((inc, add))
    chk(not bad, "★ 상한 − 내 추가분 입찰가 ≠ 원 낙찰가 (5조합 실계산)", str(bad))
    chk(all(cap({"requested_amount": 0, "combined_amount": v}, "전체재경매") <= v
            for v in (1_234_567, 8_000_000, 99_999, 100_000)),
        "  상한은 합산가를 넘지 않는다")
    chk(cap({"requested_amount": 777_777, "combined_amount": 9_999_999}, "추가분") == 777_777,
        "  추가분은 원업체 신고액 그대로(공개해도 되는 값)")

#  ★ **집행 경로가 목록과 같은 함수를 쓰는가** — 9라운드는 목록만 고쳤다.
chk(APP.count("_reauction_cap(") == 3,
    "★ 정의 1 + 호출 2 (목록·투찰) — 둘이 갈라지지 않는다",
    f"실제 {APP.count('_reauction_cap(')}회")
_i = APP.find("cap = _reauction_cap(co, kind)")
chk(_i > 0, "★ 투찰 검증이 _reauction_cap 을 쓴다")
if _i > 0:
    seg = strip_comments(APP[_i:_i + 800], ("#",))
    chk("combined_amount" not in seg,
        "★ 초과 오류 문구가 combined_amount 원본을 쓰지 않는다",
        "그 문구가 원 낙찰가 역산의 마지막 통로였다")
    chk("직전 합산 제시가" not in seg, "  '직전 합산 제시가' 라는 표현도 뺐다")

t = strip_comments(read("templates/partner_portal.html"))
chk("won(r.combined_amount)" not in t,
    "★ 협력사 화면이 서버가 안 주는 combined_amount 를 읽지 않는다",
    "undefined → won() → '0원' 이라는 허위 안내가 났다")
chk(t.count("won(r.cap)") >= 2, "  대신 r.cap 을 쓴다(카드·투찰 폼)")

# ══════════════════════════════════════════════════════════════════
print("\n[2] 데이터 파괴 — seed() 가 운영 데이터를 데모로 표시하지 않는다")
# ══════════════════════════════════════════════════════════════════
chk("UPDATE {t} SET is_demo=1 WHERE id > ?" in DBS,
    "★ 데모 표식에 WHERE 가 있다(없으면 그 표의 모든 행이 데모가 된다)")
chk("_base[_t] = conn.execute" in DBS or "COALESCE(MAX(id),0)" in DBS,
    "  시드 전 최대 id 를 기억한다")
chk("사건이 이미" in DBS and "시드를 넣지 않습니다" in DBS,
    "★ 사건이 있는 DB 는 '빈 DB' 로 보지 않는다(admins==0 만으로 판정하지 않는다)")

#  ── 진짜 DB 로 밟아 본다 ────────────────────────────────────────
#   go-live 가 데모 관리자를 지우면 admins=0 이 된다. 그 상태에서
#   dev+SEED_DEMO 로 들어와도 실데이터가 데모로 표시되면 안 된다.
_tmp = tempfile.mkdtemp(prefix="bokguon_r10_")
_probe = os.path.join(_tmp, "probe.db")
try:
    _c = sqlite3.connect(_probe)
    _c.executescript("""
        CREATE TABLE admins(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT,
                            password_hash TEXT, name TEXT, role TEXT, created_at TEXT);
        CREATE TABLE cases(id INTEGER PRIMARY KEY AUTOINCREMENT, case_no TEXT, is_demo INT DEFAULT 0);
        INSERT INTO cases(case_no) VALUES('26-90001'),('26-90002'),('26-90003');
    """)
    _c.commit()
    #  init_db 를 그대로 부를 수는 없다(스키마 전체가 필요) — 게이트 판정만 재현한다.
    _empty = _c.execute("SELECT COUNT(*) n FROM admins").fetchone()[0] == 0
    _used = _c.execute("SELECT COUNT(*) n FROM cases").fetchone()[0]
    _would_seed = _empty and not _used
    chk(not _would_seed,
        "★ admins=0 + 사건 3건 인 DB 에서는 시드가 돌지 않는다(실판정)",
        f"empty={_empty} used={_used}")
    #  표식 WHERE 가 실제로 기존 행을 건드리지 않는지
    _base = _c.execute("SELECT COALESCE(MAX(id),0) FROM cases").fetchone()[0]
    _c.execute("INSERT INTO cases(case_no) VALUES('demo-1')")
    _c.execute("UPDATE cases SET is_demo=1 WHERE id > ?", (_base,))
    _c.commit()
    _marked = _c.execute("SELECT COUNT(*) FROM cases WHERE is_demo=1").fetchone()[0]
    chk(_marked == 1, "★ 표식이 시드 행 1건에만 붙는다(기존 3건 무사)", f"표시됨 {_marked}건")
    _c.close()
finally:
    import shutil
    shutil.rmtree(_tmp, ignore_errors=True)

# ══════════════════════════════════════════════════════════════════
print("\n[3] 설정 화면이 실제로 저장된다")
# ══════════════════════════════════════════════════════════════════
#   화면이 보내는 본문 그대로 **서버 검증 블록을 실행**한다.
#   (숫자로 바꿔 보내면 통과하므로, 반드시 화면이 만드는 값을 써야 잡힌다)
try:
    _i = APP.index('    RANGES = {"min_bidders"')
    _j = APP.index("    # 부가세 기준", _i)
    _blk = APP[_i:_j]
    _src = ("def _run(d):\n"
            + "\n".join(("    " + ln[4:]) if ln.startswith("    ") else ("    " + ln)
                        for ln in _blk.split("\n"))
            + "\n    return None\n").replace("return jsonify(", "return (")
    _ns = {"jsonify": lambda x: x}
    exec(compile(_src, "<settings>", "exec"), _ns)
    _payload = {"fee_rate": "9", "min_bidders": "3", "low_price_alert": "70",
                "report_deadline_hours": "24", "auction_hours": "6",
                "reauction_hours": "24", "fee_vat_included": "1",
                "reminder_photo": "30분 간격", "reminder_payment": "지정 시각(일 2회)"}
    _res = _ns["_run"](dict(_payload))
    chk(_res is None,
        "★ 화면이 보내는 본문(한글 라벨 포함)이 400 없이 저장 단계까지 간다",
        f"거부됨: {_res}")
    #  아무 값이나 받으면 안 된다
    _bad = _ns["_run"]({"reminder_photo": "아무거나"})
    chk(_bad is not None, "  허용 목록 밖 라벨은 거부한다", str(_bad))
    #  숫자 설정은 여전히 범위 검증
    _bad2 = _ns["_run"]({"min_bidders": "999"})
    chk(_bad2 is not None, "  숫자 설정의 범위 검증은 그대로", str(_bad2))
except Exception as e:
    chk(False, "★ 설정 검증 블록 실행", f"{type(e).__name__}: {e}")

chk('"reminder_photo": (0, 10080)' not in APP,
    "★ 리마인드 설정이 숫자 RANGES 에서 빠졌다(값은 한글 라벨이다)")
chk("REMIND_CHOICES" in APP, "  라벨 허용 목록으로 검증한다")

# ══════════════════════════════════════════════════════════════════
print("\n[4] 상태 교착 · 화면과 서버의 말 맞추기")
# ══════════════════════════════════════════════════════════════════
#  ⚠⚠ **문자열이 아니라 불변식을 잠근다.**
#    원래 이 검사는 `WHERE id=? AND status IN ('시공중','검수대기','완료보고지연')`
#    이 두 번 나오는지를 봤다. 그런데 23라운드에 **두 자리가 의도적으로 갈라졌다** —
#      · 수락확정(api_co_decision)  : **같은 업체**의 금액만 바꾼다 → '검수대기' 허용
#      · 전체재경매 낙찰(close-full): **다른 업체로 교체**한다 → '검수대기' 금지
#        ('검수대기' 는 원업체가 완료 보고를 이미 올린 상태다. 거기서 업체를 바꾸면
#         시공한 업체가 자기 사건을 못 찾고 정산이 남에게 나간다.)
#    지켜야 할 성질은 그대로다: **자동으로 붙는 '완료보고지연' 이 두 경로를 막지 않는다.**
#  ⚠ [라운드133] "SET 절에 홑따옴표(리터럴)가 전혀 없다"는 것으로 이 두 자리를
#    골라내고 있었다 — 그런데 133라운드가 api_co_close_full 의 SET 절에
#    리터럴 `award_route='경매'`를 추가하면서 그 전제가 깨졌다. 게다가 단순히
#    홑따옴표를 허용하도록 넓히면 이번엔 반대로 **다른 무관한 자리**
#    (api_insurer_award 등, 이제 SET 절에 홑따옴표가 있는 다른 UPDATE)까지
#    걸려 "두 경로 모두 완료보고지연을 받는다" 쪽이 거짓 FAIL 났다(실측).
#    문자열 모양으로 골라내는 대신, 이 검사가 애초에 이름으로 지목하는 두
#    함수(api_co_decision·api_co_close_full) 안에서만 각각 찾는다 — 구조
#    기준이라 SET 절에 리터럴이 늘어도 흔들리지 않는다.
def _fn_body(name):
    i = APP.index(f"def {name}(")
    j = APP.index("\ndef ", i + 1)
    return APP[i:j]


_co_states = []
for _fn in ("api_co_decision", "api_co_close_full"):
    _m = re.search(
        r"UPDATE cases SET.*?WHERE id=\? AND status IN \(([^)]*)\)", _fn_body(_fn), re.S)
    if _m:
        _co_states.append(_m.group(1))
chk(len(_co_states) >= 2,
    "★ 변경견적 수락·낙찰이 상태 집합으로 게이트를 건다",
    f"찾은 자리 {len(_co_states)}곳")
chk(all("'완료보고지연'" in s for s in _co_states),
    "★ 두 경로 모두 '완료보고지연' 을 받는다(자동으로 붙는 상태다)",
    f"빠진 곳: {[s for s in _co_states if chr(39)+'완료보고지연'+chr(39) not in s]}")
chk("이미 정산 단계로 넘어가 금액을 바꿀 수 없습니다" not in APP,
    "  정산이 없는데 '정산 단계' 라고 말하지 않는다")

_i = APP.find("def api_case_open_auction2")
if _i < 0:
    _i = APP.find("현장 사진이 실제로 있어야 2차 경매의 근거")
#  ⚠ [라운드73] 2500 이던 창이 라운드73 의 화이트리스트 수정 주석 때문에
#    실제 거리(anchor→"미분류 사진 일괄 분류")를 못 담게 됐다(2929자) — 앞으로도
#    이 함수에 주석이 붙을 수 있으니 여유를 넉넉히 둔다.
seg = APP[max(0, _i - 500):_i + 4000]
#  ⚠ 10라운드에는 '미분류면 거부' 였는데, 그게 운영자를 가뒀다(11라운드 회귀).
#    AI 분류가 꺼진 배포에서는 협력사 사진이 전부 미분류라 2트랙 2차 경매가
#    통째로 성립하지 않았다. 지금은 **개시 시점에 함께 분류**한다 —
#    "이 사진들로 경매를 연다"는 운영자의 판단이 곧 분류이기 때문이다.
#    지켜야 할 성질은 그대로다: **열리지 않을 공고는 열리지 않는다.**
chk("UPDATE photos SET kind='착공전'" in seg and "미분류 사진 일괄 분류" in seg,
    "★ 2차 경매 개시가 미분류 사진을 함께 확정한다(막지 않고 통과시킨다)",
    "막기만 하면 운영자가 갇힌다 — 그 판단이 곧 분류다")
chk('if not (_ph["n"] or 0):' in seg,
    "★ 사진이 **한 장도 없을 때만** 거부한다")
chk("COALESCE(p.kind,'') NOT IN ('', '영수증', '기타')" in APP,
    "★ 화면의 '피해 사진 N장'도 열리는 사진만 센다")

for f, mark in (("templates/partner_portal.html", "c.co_offer && canAct()"),
                ("templates/insurer_portal.html", "canAct() ? `<button class=\"btn a sm\" data-act=\"approveDone\"")):
    chk(mark in read(f), f"★ {os.path.basename(f)} — 서버가 막는 버튼을 화면에 두지 않는다")

# ══════════════════════════════════════════════════════════════════
print("\n[5] 참조무결성 · 개인정보 파기")
# ══════════════════════════════════════════════════════════════════
_i = APP.find("def api_photo_delete")
seg = APP[_i:_i + 4000] if _i > 0 else ""
chk("UPDATE photos SET fix_for=NULL WHERE fix_for=?" in seg,
    "★ 사진을 지우면 그 사진을 가리키던 fix_for 도 끊는다")

#  ⚠⚠ [라운드187] 고정폭(9000자) 대신 다음 함수 시작까지로 자른다 — go-live 가
#    커질 때마다(187라운드도 미리보기를 늘렸다) 고정폭이 뒤쪽 점검문을 잘라내
#    이 파일이 실제로는 안 깨진 코드를 깨졌다고 오판했다.
_i = MNG.find("def cmd_go_live")
_i1 = MNG.find("\ndef ", _i + 1) if _i > 0 else -1
seg = MNG[_i:_i1] if _i > 0 and _i1 > 0 else ""
_dp = seg.find("DELETE FROM defect_photos")
_ph = seg.find('DELETE FROM {_t} WHERE case_id')
chk(0 < _dp < _ph,
    "★ go-live 가 defect_photos 를 photos 보다 **먼저** 지운다",
    "뒤에 두면 하위질의가 빈 집합이라 항상 0행 — 9라운드 수정이 무효였다")

chk("피해자 안내 알림" in MNG and "UPDATE notifications SET target='(파기됨)'" in MNG,
    "★ 파기가 알림에 남은 연락처 사본까지 지운다",
    "cases 만 지우면 파기 증적만 남고 번호는 그대로다")
chk("UPDATE cases SET track_token=NULL" in MNG,
    "★ 진행조회 링크도 무효화한다(살아 있으면 계속 열린다)")

chk("SELECT 1 FROM admins WHERE LOWER(username)=LOWER(?)" in APP
    and APP.count("SELECT 1 FROM portal_users WHERE LOWER(login_id)=LOWER(?)") >= 2,
    "★ 아이디 전역 유일 검사가 협력사·발주처 **양쪽** 발급 경로에 있다")

# ══════════════════════════════════════════════════════════════════
print("\n[6] 돈 — 부가세 '별도' 기준이 이중 과세되지 않는다")
# ══════════════════════════════════════════════════════════════════
_cf, _sv = load_func("compute_fee"), load_func("split_vat")
chk(_cf is not None and _sv is not None, "compute_fee·split_vat 을 실제로 불러올 수 있다")
if _cf and _sv:
    bad = []
    for amt, bp in ((10_000_000, 1000), (3_600_000, 1000), (7_777_777, 950),
                    (1_234_567, 700)):
        for inc in (True, False):
            fee, payout = _cf(amt, bp, inc)
            sup, vat = _sv(fee)
            if fee + payout != amt or sup + vat != fee:
                bad.append((amt, bp, inc, fee, payout, sup, vat))
    chk(not bad, "★ 공제+지급=낙찰액 · 계산서(공급+세)=공제액 (8조합 실계산)", str(bad[:2]))
    #  별도 기준에서 공급가액이 '요율 × 금액' 과 같아야 한다(세액을 또 얹지 않는다)
    fee, _ = _cf(10_000_000, 1000, False)
    sup, vat = _sv(fee)
    chk(sup == 1_000_000 and vat == 100_000 and sup + vat == fee,
        "★ 별도 기준: 공급 100만 + 세 10만 = 공제 110만 (110만+11만이 아니다)",
        f"{sup}+{vat}={sup+vat} vs fee={fee}")
chk("def split_vat(fee_total" in APP, "  split_vat 이 '총액'만 받는다(기준 분기 없음)")

# ══════════════════════════════════════════════════════════════════
print("\n[7] 상한 · 첫날 · 종결 출구")
# ══════════════════════════════════════════════════════════════════
if cap:
    _c = cap({"requested_amount": 1_500_000, "combined_amount": None,
              "incumbent_amount": 8_000_000}, "전체재경매")
    chk(_c > 0, "★ 추가분 유찰 경로에서도 상한이 있다(제한 없음이 되지 않는다)", str(_c))
    chk(_c - 1_500_000 != 8_000_000, "  그 상한으로도 원 낙찰가가 역산되지 않는다")
chk("_cap_now = _reauction_cap(r, kind)" in APP,
    "★ 목록이 incumbent_amount 를 지우기 **전에** 상한을 계산한다")

chk(APP.count("AND COALESCE(login_id,'') <> ''") >= 2,
    "★ '매칭 시행사 N곳' 이 로그인 계정 보유만 센다",
    "명부 310곳·계정 0곳인데 '0곳' 경고가 안 뜨던 자리")

#  ⚠ 데코레이터는 **AST 로** 본다 — 주석에 그렇게 써 있는 것과 실제로 붙은 것은 다르다.
_nr = func_src("api_partner_no_repair") or ""
for _nd in ast.walk(TREE):
    if isinstance(_nd, ast.FunctionDef) and _nd.name == "api_partner_no_repair":
        _decs = [ast.unparse(d) for d in _nd.decorator_list]
        break
else:
    _decs = []
chk(any("require_portal_role" in d for d in _decs),
    "★ api_partner_no_repair — 조회 등급이 사건을 종결시킬 수 없다", f"실제: {_decs}")

chk('@app.post("/api/cases/<int:cid>/close-offline")' in APP,
    "★ 재개 상한을 소진한 유찰 사건을 닫는 출구가 있다")
chk('@app.post("/api/cases/<int:cid>/undo-no-repair")' in APP,
    "★ 미수선 종결을 되돌리는 출구가 있다")
_js = read("static/admin.js")
chk("ACT.caseCloseOffline" in _js and "ACT.caseUndoNoRepair" in _js,
    "  두 출구가 화면에도 있다(라우트만 만들면 죽은 라우트다)")
chk('data-act="caseCloseOffline"' in _js and 'data-act="caseUndoNoRepair"' in _js,
    "  버튼도 실제로 그려진다")

# ══════════════════════════════════════════════════════════════════
print("\n[8] 거짓 성공 · 개인정보 · 화면 숫자")
# ══════════════════════════════════════════════════════════════════
_i = APP.find("def api_insurer_webhook_test")
seg = APP[_i:_i + 2500] if _i > 0 else ""
chk("API_DISABLED" in seg and "INSURER_NOT_ACTIVE" in seg,
    "★ 웹훅 [테스트 발송] 이 안 보내면 안 보냈다고 한다")

_pa = read("photo_ai.py")
chk('"exif_error": _exif_err' in _pa,
    "★ EXIF 제거 실패가 저장 결과에 실려 나온다(조용히 원본 저장 안 함)")
chk('return data, "Pillow 미설치"' in _pa, "  실패 사유를 구분해서 돌려준다")
chk("_EXIF_FAILS" not in _pa, "  무한히 커지는 전역 목록을 두지 않는다")
chk("def _warn_exif(" in APP and APP.count("_warn_exif(conn") >= 3,
    "★ 업로드 경로 3곳이 모두 EXIF 실패를 운영팀에 알린다",
    f"호출 {APP.count('_warn_exif(conn')}곳")

chk("BOKGUON_TRASH_KEEP_DAYS" in MNG and "휴지통 사진" in MNG,
    "★ 휴지통(uploads/_trash)도 파기 절차에 들어간다")

chk('@app.get("/api/settlements/summary")' in APP,
    "★ 정산 상단 지표를 서버가 한 기준으로 낸다")
chk("sum = await api('GET','/api/settlements/summary')" in _js,
    "  화면이 그 값을 쓴다(목록 1000행을 더하지 않는다)")
chk("won(sum ? sum.fee_paid : 0)" in _js, "  이체완료 수수료가 서버 집계")

_i = APP.find("heads = [\"공종\", \"완료 건수\"")
seg = APP[_i:_i + 1600] if _i > 0 else ""
chk("round(sv * 100.0 / est, 1)" in seg,
    "★ 절감률을 절감액과 **같은 기준**으로 낸다(부호가 어긋나지 않는다)")
#  ⚠ 18라운드에서 건수를 S["done"](넓은 집계)에서 _n_t(by_category 합)로 바꿨다 —
#    금액 3칸이 좁은 집계라 한 줄 안에서 모집단이 갈렸기 때문이다. 여기서 보는 것은
#    "합계 행이 본문과 대사되는가" 이지 특정 변수명이 아니다.
chk('ws.append(["합계", _n_t, _est_t, _aw_t, _sv_t,' in seg,
    "  합계 행이 본문과 대사된다(빈 칸이 아니다 · 건수도 같은 모집단)")

chk("obSendListed" in _js and "send-selected" in _js,
    "★ 48시간이 지난 발송대기 건을 보낼 수단이 화면에 있다(죽은 라우트 해소)")

chk("복구온_예약실행_등록.ps1 -RunNow" in read("deploy/DEPLOY.md"),
    "★ 수동 설치 문서에 5분 sweep 예약 단계가 있다")
chk("코드 완성 · 키만 넣으면 켜짐" in read("deploy/DEPLOY.md"),
    "  '알려진 제약' 표가 구현된 기능을 미구현으로 적지 않는다")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
