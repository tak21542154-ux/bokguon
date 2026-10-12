# -*- coding: utf-8 -*-
"""9라운드 확정 결함 회귀 테스트 — 자기도구·권한행렬·참조무결성·오류계약·경쟁공정성·인수인계.

  이 라운드의 주제는 **"운영을 돕는 코드가 거짓 초록을 낸다"** 였다.
  그래서 검사도 '문자열이 들어 있나'로 끝내지 않는다 —
  데코레이터는 AST 로 확인하고, 산술은 실제로 계산해 본다.

      python test_scan_round9_fixes.py
"""
import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def strip_comments(text, marks=("#", "//")):
    """주석을 걷어낸다.

      ⚠ 이게 없으면 **자기가 쓴 설명 주석을 코드로 오독**한다.
        "is_lowest 를 주지 않는다" 라는 주석이 'is_lowest 가 있다'로 잡혀
        고쳐 놓고도 실패가 뜬다(실제로 이 테스트가 그랬다).
    """
    out = []
    for ln in text.splitlines():
        t = ln.strip()
        if any(t.startswith(m) for m in marks):
            continue
        out.append(ln)
    return "\n".join(out)


def read(rel, enc="utf-8"):
    try:
        return io.open(os.path.join(HERE, rel), encoding=enc).read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


APP = read("app.py")
MNG = read("manage.py")
APP_TREE = ast.parse(APP)


# ── 데코레이터를 **AST 로** 본다 ────────────────────────────────────
#    ⚠ 문자열 검색은 "주석에 그렇게 써 있다"와 "실제로 붙어 있다"를 구분 못 한다.
def decorators_of(fn_name):
    for node in ast.walk(APP_TREE):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            out = []
            for d in node.decorator_list:
                out.append(ast.unparse(d))
            return out
    return None


print("═" * 70)
print("  9라운드 회귀 — 철칙(경쟁정보) · 권한 · 참조무결성 · 오류계약 · 자기도구")
print("═" * 70)

# ══════════════════════════════════════════════════════════════════
print("\n[1] 철칙 4 — 경쟁 입찰가·낙찰가 비공개")
# ══════════════════════════════════════════════════════════════════

#  ① is_lowest 는 '내가 지금 최저인가' 오라클이다 — 인하 재투찰로 경쟁가를 역산한다.
for fn in ("api_partner_bid", "api_partner_reauction_bid"):
    src = None
    for node in ast.walk(APP_TREE):
        if isinstance(node, ast.FunctionDef) and node.name == fn:
            src = ast.unparse(node)
    if src is None:
        #  이름이 다를 수 있다 — 라우트로 다시 찾는다
        continue
    chk("is_lowest" not in src, f"★ {fn} 응답에 is_lowest 가 없다", "경쟁가 역산 통로")

#  라우트 기준으로 한 번 더 (함수명이 바뀌어도 잡히게)
for route in ("/api/partner/bids", "/api/partner/reauction-bids"):
    i = APP.find(f'@app.post("{route}")')
    chk(i > 0, f"라우트 존재 — {route}")
    if i > 0:
        seg = APP[i:i + 12000]
        nxt = seg.find("\n@app.")
        #  ⚠ 주석을 걷어내고 본다 — "is_lowest 를 주지 않는다" 라는 **설명**이
        #    'is_lowest 가 있다'로 잡혀 고쳐 놓고도 실패가 떴다.
        seg = strip_comments(seg[:nxt] if nxt > 0 else seg, ("#",))
        chk("is_lowest" not in seg, f"★ {route} 가 is_lowest 를 안 준다",
            "10만원씩 내리며 재투찰하면 경쟁사 금액이 특정된다")

chk("현재 최저가입니다" not in strip_comments(read("templates/partner_portal.html")),
    "★ 협력사 화면에 '현재 최저가입니다' 표시가 없다")

#  ② 전체재경매 상한으로 원 낙찰가를 뺄셈해 알아낼 수 없어야 한다.
i = APP.find("def api_reauctions")
seg = APP[i:i + 6000] if i > 0 else ""
chk('r.pop("combined_amount", None)' in seg,
    "★ 전체재경매 응답에서 combined_amount 를 뺀다")
#  ⚠ 산술은 _reauction_cap 한 곳으로 옮겼다(10라운드) — 목록이 그걸 쓰는지만 본다.
#    식을 여기에 다시 적으면 또 낡은 사본이 된다.
chk("_reauction_cap(" in seg,
    "★ 목록의 상한이 공통 함수(_reauction_cap)를 쓴다 — 집행과 갈라지지 않는다")

#  실제로 계산해 본다 — 상한에서 내 추가분 입찰가를 빼도 원 낙찰가가 안 나와야 한다.
#  ⚠ **공식을 여기에 베껴 쓰지 않는다.** 종전에는 파이썬으로 재구현해 뒀는데,
#    app.py 의 식이 바뀌자 이 테스트는 **없어진 식**을 검사하며 계속 통과했다
#    (거짓 초록). 진짜 함수를 떼어 와서 그것을 돌린다.
def _load(name):
    for _nd in ast.walk(APP_TREE):
        if isinstance(_nd, ast.FunctionDef) and _nd.name == name:
            _ns = {}
            exec(compile(ast.Module(body=[_nd], type_ignores=[]), "<x>", "exec"), _ns)
            return _ns[name]
    return None


_capfn = _load("_reauction_cap")
chk(_capfn is not None, "★ _reauction_cap 을 실제로 불러올 수 있다")


def cap_of(combined):
    return _capfn({"requested_amount": 0, "combined_amount": combined}, "전체재경매")


_bad = []
for incumbent, add_bid in ((7_200_000, 950_000), (3_400_000, 120_000),
                           (12_800_000, 2_050_000), (900_000, 80_000)):
    combined = incumbent + add_bid
    recovered = cap_of(combined) - add_bid
    if recovered == incumbent:
        _bad.append((incumbent, add_bid, recovered))
chk(not _bad, "★ 상한 − 내 입찰가 ≠ 원 낙찰가 (4가지 조합 실계산)", str(_bad))
chk(all(cap_of(c) <= c for c in (1_234_567, 8_000_000, 99_999)),
    "상한은 합산가를 넘지 않는다(경제적 취지 유지)")

#  ③ 출동만 했던 업체가 낙찰업체의 영수증·상호를 보면 안 된다.
i = APP.find("def _photo_visible_to")
seg = APP[i:i + 3000] if i > 0 else ""
chk('photo.get("partner_id") == session["partner_id"]' in seg
    and "_is_my_dispatch" in seg,
    "★ 사진 원본 — 출동 업체는 **자기가 올린 것만** 열람")

i = APP.find("def api_case_photos")
if i < 0:
    i = APP.find('"partner_name": (None if redact else')
seg = APP[max(0, i - 4000):i + 4000]
chk("dispatched = bool(" in APP and "redact = bidder_only or dispatched" in APP,
    "★ 사진 목록 — 당사자(party)와 출동(dispatched)을 가른다")
chk('"partner_name": (None if redact else' in APP,
    "★ 낙찰업체 상호를 출동 업체에게도 가린다")
chk('"receipts": ([] if redact' in APP,
    "★ 영수증(직전 시공사·공사금액)을 출동 업체에게도 가린다")

# ══════════════════════════════════════════════════════════════════
print("\n[2] 권한 — 정책 문구(하위관리자=조회+접수보조)를 서버가 지킨다")
# ══════════════════════════════════════════════════════════════════
GATES = {
    "api_co_decision":          '@require_portal_role(\'partner\', \'중간관리자\')',
    "api_partner_complete":     '@require_portal_role(\'partner\', \'중간관리자\')',
    "api_insurer_est_ack":      '@require_portal_role(\'insurer\', \'중간관리자\')',
    "api_defect_update":        "@require_role('중간관리자')",
    "api_outbox_send_selected": "@require_role('중간관리자')",
    "api_application_update":   "@require_role('중간관리자')",
    "api_photo_delete":         "@require_role('중간관리자')",
    "api_co_withdraw_offer":    "@require_role('중간관리자')",
}
for fn, want in GATES.items():
    got = decorators_of(fn)
    chk(got is not None and any(want.lstrip("@") in g for g in got),
        f"★ {fn} — {want.lstrip('@')}", f"실제: {got}")

#  ⚠ **과잉 차단이 아닌지도 본다.** 접수 보조까지 막으면 그 등급이 일을 못 한다.
got = decorators_of("api_insurer_set_severity")
chk(got is not None and not any("require_portal_role" in g for g in got),
    "★ 파손 정도 확인은 열어 둔다(접수 보조 — 과잉 차단 방지)", f"실제: {got}")

#  기존 게이트가 그대로인지 (되돌아가지 않았는지)
for fn, want in (("api_partner_bid", "require_portal_role"),
                 ("api_insurer_award", "require_portal_role")):
    got = decorators_of(fn) or []
    chk(any(want in g for g in got), f"기존 게이트 유지 — {fn}", f"실제: {got}")

# ══════════════════════════════════════════════════════════════════
print("\n[3] 참조무결성")
# ══════════════════════════════════════════════════════════════════
chk("UPDATE work_lots SET category=? WHERE case_id=?" in APP,
    "★ 사건 공종을 고치면 work_lots.category 도 옮긴다")
chk("복합 공종" in APP, "  복합 사건은 손대지 않고 알려 준다")

i = APP.find("def _partner_exit_load")
seg = APP[i:i + 1200] if i > 0 else ""
chk("COALESCE(void_status,'') <> '취소'" in seg,
    "★ 퇴출 관문의 '미지급 정산'에서 취소된 정산을 뺀다")

i = APP.find("def api_photo_delete")
seg = APP[i:i + 3500] if i > 0 else ""
chk('("ai_reviews", "photo_id")' in seg and '("defect_photos", "photo_id")' in seg,
    "★ 사진을 지우면 자식 행(ai_reviews·damage_reads·defect_photos)도 지운다")

chk("UPDATE est_outcome SET partner_id=? WHERE case_id=?" in APP,
    "★ 전체재경매 낙찰로 시공사가 바뀌면 표본의 업체도 옮긴다")

#  아이디 유일성은 전역이어야 한다
chk(APP.count("SELECT 1 FROM portal_users WHERE LOWER(login_id)=LOWER(?)") >= 1
    and "SELECT 1 FROM admins WHERE LOWER(username)=LOWER(?)" in APP,
    "★ 협력사 아이디 중복 검사가 portal_users·admins 까지 본다")

#  go-live 의 죽은 DELETE 3줄
#  ⚠⚠ [라운드187] 고정폭(9000자) 대신 다음 함수 시작까지로 자른다 — go-live 가
#    커질 때마다(187라운드도 미리보기를 늘렸다) 고정폭이 뒤쪽 점검문을 잘라내
#    이 파일이 실제로는 안 깨진 코드를 깨졌다고 오판했다.
i = MNG.find("def cmd_go_live")
_i1 = MNG.find("\ndef ", i + 1) if i > 0 else -1
seg = MNG[i:_i1] if i > 0 and _i1 > 0 else ""
chk('"gate_logs", "case_notes"' not in seg, "★ 존재하지 않는 표를 지우는 척하지 않는다")
chk("DELETE FROM defect_photos WHERE photo_id IN" in seg,
    "★ defect_photos 는 사진 id 로 거슬러 지운다(case_id 컬럼이 없다)")
chk("DELETE FROM contract_gate_log" in seg, "★ 관문 판정은 실제 표 이름으로 지운다")
chk("_dead.append" in seg and "정리하지 못한 표" in seg,
    "★ 삭제가 죽으면 조용히 넘기지 않고 말한다")

# ══════════════════════════════════════════════════════════════════
print("\n[4] 오류 계약 — 화면이 서버가 적어 보낸 사유를 버리지 않는다")
# ══════════════════════════════════════════════════════════════════
for f in ("templates/insurer_portal.html", "templates/partner_portal.html"):
    t = read(f)
    chk("if(r.status===401)" in t and "if(r.status===403){" in t,
        f"★ {os.path.basename(f)} — 401 과 403 을 나눈다")
    chk("PORTAL_FORBIDDEN" in t,
        f"★ {os.path.basename(f)} — 권한 부족은 사유를 보여 준다(로그인으로 안 튕긴다)")
    chk("d5.ref" in t, f"  {os.path.basename(f)} — 500 오류번호를 살려 둔다")

t = read("templates/insurer_portal.html")
chk(t.count("pd.duplicates") >= 2,
    "★ 보험사 사진 업로드 — 중복을 실패로 읽지 않는다(등록·재업로드 양쪽)")
chk("다시 올려도 같은 결과입니다" in t, "  전량 중복이면 '다시 올리기'를 시키지 않는다")

t = read("templates/partner_portal.html")
chk("/fetch|network|networkerror|failed to|load failed/i" in t,
    "★ 입찰 제출 — 통신 끊김과 서버 거절을 가른다")
chk("같은 금액 그대로" in t, "  인하 전용 규칙 때문에 재입력 안내가 필요하다")

i = APP.find("def api_defect_photos_upload")
seg = APP[i:i + 6000] if i > 0 else ""
chk('"error": _err' in seg and "이미 이 사건에 올라간 사진입니다" in seg,
    "★ 하자 사진 409 가 '왜' 를 말한다(불가능한 행동을 지시하지 않는다)")

chk("btn.textContent=label" in read("static/form.js").replace(" ", ""),
    "★ 공개 폼 — 실패해도 버튼 글자를 되돌린다")
chk("r.awarded ?" in read("static/admin.js").replace("? ", "? "),
    "★ 재경매 강제 마감도 '누가 얼마에' 를 말한다")

# ══════════════════════════════════════════════════════════════════
print("\n[5] 자기도구 — 운영을 돕는 코드가 거짓 초록을 내지 않는다")
# ══════════════════════════════════════════════════════════════════
chk("_age_h > 26" in MNG and ".db.gz" in MNG,
    "★ 백업 점검이 개수 대신 **신선도**를 본다 + 리눅스 .db.gz 도 센다")
chk('_cx.request("GET", "/healthz", headers={"Host": _host})' in MNG,
    "★ 공개 주소를 **돌고 있는 서버에 직접 물어본다**(목록 대조가 아니라)")
chk("자리표시자가 그대로" in MNG, "★ 법정 고지의 자리표시자를 잡아낸다")

sm = read("smoke_test.py")
chk("return 2" in sm and "검사를 하나도 실행하지 않았습니다" in sm,
    "★ 스모크가 0건 검사하고 0 을 돌려주지 않는다")
chk("if total == 0:" in sm, "  통과 0건도 통과가 아니다")

ra = read("run_all_tests.py")
chk("파일이 없습니다" in ra and "실행되지 않은 검사" in ra,
    "★ 실행기가 없는 테스트 파일을 드러낸다")
chk("code = code or 2" in ra, "  누락이 종료코드에 반영된다")

#  ★ **검증이 운영 서버를 두드리지 않는다.**
#    2026-08-06 실측 — 실행기가 BOKGUON_TEST_BASE 를 자식에게 안 넘겨서
#    두 테스트가 각자의 기본값 8771(운영)로 붙었다. DB 는 막아 놓고
#    **서버는 안 막아 둔 것**이라, 비밀번호가 맞았으면 운영에 검증 사건이 박혔다.
chk('_env["BOKGUON_TEST_BASE"] = base' in ra,
    "★ 실행기가 자식에게 **어느 서버인지** 넘긴다")
chk('info.get("channel") or "") != "개발"' in ra,
    "★ 사전 점검이 운영 채널이면 거부한다(포트 숫자가 아니라 서버가 밝히는 채널로)")
for _c in ("run(s, label, base)",):
    chk(ra.count(_c) >= 3, f"  호출부 3곳 모두 base 전달 ({ra.count(_c)}곳)")

#  HTTP 테스트 중 **운영 포트를 기본값으로 둔 파일이 없어야** 한다
_prod_default = []
_SELF = os.path.basename(__file__)
for _f in os.listdir(HERE):
    if not (_f.startswith("test_") and _f.endswith(".py")) or _f == _SELF:
        continue          # 자기 자신은 뺀다 — 이 검사문 자체가 그 문자열을 담고 있다
    _t = strip_comments(read(_f), ("#",))
    if 'BOKGUON_TEST_BASE", "http://127.0.0.1:8771"' in _t:
        _prod_default.append(_f)
chk(not _prod_default, "★ 어떤 테스트도 운영(8771)을 기본 서버로 두지 않는다",
    str(_prod_default))

bs = read("deploy/bootstrap.sh")
chk("CHECK_RC" in bs and "SMOKE_RC" in bs, "★ bootstrap 이 점검·스모크 결과를 받는다")
chk("설치는 끝났지만 — 아직 열면 안 됩니다" in bs,
    "★ 미통과면 초록 '설치 완료' 를 찍지 않는다")
chk('if [ "$CHECK_RC" -ne 0 ] || [ "$SMOKE_RC" -ne 0 ]; then exit 1; fi' in bs,
    "★ 종료코드로도 실패를 알린다")

reg = read("deploy/복구온_예약실행_등록.ps1", "utf-8-sig")
chk("Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue" in reg
    and "$registered" in reg,
    "★ 스윕 등록이 실패를 성공이라고 말하지 않는다")
chk("이미 같은 스윕을 도는 작업이 있습니다" in reg, "★ 중복 스윕 작업을 감지한다")

sup = read("deploy/외부접속_상시가동.ps1", "utf-8-sig")
chk("Global\\Bokguon_Supervisor" in sup and "2중 실행 방지" in sup,
    "★ 감시자가 2중으로 뜨지 않는다(자동시작 경로가 둘이다)")
chk("PublicServable" in sup, "  공개 주소 관문 확인은 그대로 있다")
chk("고정도메인_설정절차.md" not in sup, "★ 없는 문서를 가리키지 않는다")

stop = read("복구온_외부공개_중지.bat", "utf-8-sig")
chk("$_.ProcessId -ne $me" in stop,
    "★ 중지 배치가 **자기 자신을 죽이지 않는다**(그 뒤 문장이 통째로 안 돈다)")
chk("Disable-ScheduledTask" in stop and ".off" in stop,
    "★ 「중지」가 자동 재시작 경로까지 실제로 멈춘다")
chk("다시 열려면" in stop, "  되돌리는 방법을 알려 준다")

# ══════════════════════════════════════════════════════════════════
print("\n[6] 인수인계 — 문서대로 하면 맞아야 한다")
# ══════════════════════════════════════════════════════════════════
aws = read("deploy/AWS_배포절차.md")
#  ⚠ **명령줄만 본다.** 경고문에는 옛 파일명이 나올 수밖에 없다
#    ("그것을 쓰지 마라"고 적어야 하니까) — 문서 전체 검색은 그걸 위반으로 읽는다.
_cmds = [ln for ln in aws.splitlines()
         if ln.strip().startswith(("scp ", "tar ", "cd ", "sudo ", "chmod ", "ssh "))]
chk(not any("260721" in ln for ln in _cmds),
    "★ AWS 절차의 **명령**이 2주 전 배포묶음을 쓰지 않는다",
    str([l for l in _cmds if "260721" in l][:2]))
chk("그대로 쓰지 마십시오" in aws, "  옛 묶음을 쓰지 말라고 명시한다")
chk("tar --exclude=" in aws and "grep -E 'bokguon_service/(app|db|manage" in aws,
    "★ 묶음을 지금 만들고, 담겼는지 확인시킨다")

dep = read("deploy/DEPLOY.md")
_live = [ln for ln in dep.split("\n")
         if ln.strip().startswith("./venv/bin/python manage.py set-info")]
chk(not any(("○" in ln or "O월 O일" in ln) for ln in _live),
    "★ 실행되는 set-info 줄에 자리표시자가 없다",
    str([l for l in _live if "○" in l or "O월" in l][:2]))
chk("show-info          # ← **먼저 이것부터.**" in dep,
    "  먼저 무엇이 비었는지 보게 한다")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
