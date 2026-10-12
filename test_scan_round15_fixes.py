# -*- coding: utf-8 -*-
"""15라운드 회귀 — **go-live 직후 DB 로 첫날을 실제로 밟아** 나온 것들.

  기존 test_firstday.py 는 '빈 DB' 에서 출발한다. 그런데 다음 주의 실제 출발점은
  **go-live 직후** 다: 협력사 399곳과 표준단가 71건은 남고, 발주처·관리자·사건은 0.
  그 상태에서만 드러나는 교착이 있다.

  이 라운드에서 재현으로 확인한 것:
   협력사 399곳 중 포털 계정 0곳 · 팝빌 미연동 → 출동 수배 수락은 **구조적으로 0**.
   30분마다 회차만 올라 3회차에 소진되는데(호출 60곳), 그 사이 운영자가 전화로
   업체를 구해도 직접 배정이 409 로 막혔다. 진행 중 수배를 멈추는 라우트는 없었다.
   → 되돌릴 수 없는 일이 아니므로 **막지 말고 되묻는다**(DISPATCH_LIVE → supersede).

      python test_scan_round15_fixes.py
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


def read(rel):
    try:
        return io.open(os.path.join(HERE, rel), encoding="utf-8").read()
    except OSError as e:
        return f"<<읽기실패 {e}>>"


def func_body(src, name):
    """`def name(` 부터 **다음 최상위 def 까지** — 창을 글자수로 자르지 않는다.

    ⚠ 고정 길이(4000자)로 자르면 함수가 길 때 뒤쪽 코드를 못 본다.
      그러면 멀쩡히 있는 호출을 "없다" 고 말한다(실제로 그랬다).
    """
    i = src.find("def " + name + "(")
    if i < 0:
        return ""
    j = src.find("\ndef ", i + 1)
    return src[i:j if j > 0 else len(src)]


def strip_comments(text, marks=("#", "//")):
    text = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return "\n".join(ln for ln in text.splitlines()
                     if not any(ln.strip().startswith(m) for m in marks))


APP = read("app.py")
DSP = read("dispatch.py")
ADM = read("static/admin.js")
MNG = read("manage.py")
INS = read("templates/insurer_portal.html")

print("═" * 70)
print("  15라운드 회귀 — 첫 주 출동 수배 교착")
print("═" * 70)

print("\n[1] 진행 중 수배가 있어도 직접 배정으로 넘어갈 수 있다")
_i = DSP.find("def assign_dispatch")
seg = strip_comments(DSP[_i:_i + 2600], ("#",)) if _i > 0 else ""
chk("supersede" in DSP[_i:_i + 200],
    "★ assign_dispatch 가 supersede 를 받는다",
    "첫 주엔 수락 가능 업체가 0곳이라 수배가 늘 돌고 있다. 그때 전화로 잡은 업체를 "
    "넣을 수 없으면 회차가 소진될 때까지(30분×3) 현장이 멈춘다")
chk("if live and not supersede:" in seg,
    "★ supersede 없이 왔을 때만 막는다")
chk("ST_CANCELED" in seg and "운영자 직접 배정" in DSP[_i:_i + 2600],
    "★ 접은 수배에 **왜 접었는지**가 남는다('실패' 아니라 '취소')",
    "업체가 늦은 게 아니라 우리가 거둔 것이다 — 업체 이행 이력에 불리하게 쌓이면 안 된다")

_a = APP.find("def api_dispatch_assign")
# 라운드463이 함수 앞부분에 주석 블록을 추가해 DISPATCH_LIVE가 2200자 밖으로
# 밀려남 — 함수 전체(약 3100자)를 여유 있게 덮도록 2900으로 넓힘.
aseg = strip_comments(APP[_a:_a + 2900], ("#",)) if _a > 0 else ""
chk('"DISPATCH_LIVE"' in aseg,
    "★ 서버가 화면이 알아볼 코드로 알린다(DISPATCH_LIVE)",
    "문구만 주면 화면이 되물을 수 없다")
chk("supersede=_sup" in aseg or "supersede=" in aseg,
    "★ 라우트가 supersede 를 그대로 넘긴다")

_adm = strip_comments(ADM)
_f = _adm.find("dispatch/assign")
chk("DISPATCH_LIVE" in _adm,
    "★ 화면이 그 코드를 처리한다",
    "서버만 열어 두면 운영자는 여전히 못 넘어간다 — 오늘 반복해서 잡은 부류")
chk("supersede:true" in _adm.replace(" ", ""),
    "★ 확인 후 supersede 로 재요청한다")

print("\n[2] 첫 주 조건에서 수배가 조용히 늙지 않는다")
chk("DISPATCH_UNCLAIMED_SQL" in DSP,
    "★ 아무도 수락 안 한 수배(due_at NULL)도 만료 대상이다",
    "due_at 은 수락 시점에 채워진다. 그 조건만 보면 '모집중' 이 영원히 남는다")
_s = DSP.find("DISPATCH_UNCLAIMED_SQL =")
chk("due_at IS NULL" in DSP[_s:_s + 300] and "created_at" in DSP[_s:_s + 300],
    "★ 그 판정이 created_at + 제한시간으로 이뤄진다")

print("\n[3] 수락 가능 업체 수를 사실대로 말한다(12라운드 연장)")
_r = APP.find("def _dispatch_reach")
rseg = strip_comments(APP[_r:_r + 1400], ("#",)) if _r > 0 else ""
chk("_sms_live" in rseg and "NOTIFY_ENABLED" in rseg,
    "★ '문자 가능 N곳' 이 팝빌 연동 여부를 본다")
chk("can_accept" in rseg and "warn" in rseg,
    "★ 수락할 수단이 없으면 화면에 경고를 준다")

print("\n[4] 2차 경매를 열면 살아 있는 수배를 함께 닫는다")
chk("def close_live_dispatches(" in APP,
    "★ 수배 정리를 한 함수에 두고 여러 곳이 부른다",
    "발주처 취소 경로에만 있던 정리(수배 닫기·호출 마감·출발한 곳 통지)가 "
    "2차 경매 개시에는 없어, 이미 넘어간 사건으로 협력사가 계속 불려 갔다")
oseg = strip_comments(func_body(APP, "api_case_open_auction"), ("#",))
chk("close_live_dispatches(" in oseg,
    "★ 2차 경매 개시가 그 함수를 부른다")

print("\n[5] 웹훅이 '대기' 로 굳어도 재전송이 집는다")
_w = APP.find("FROM webhook_deliveries d")
wseg = APP[max(0, _w - 600):_w + 1400] if _w > 0 else ""
chk("d.status='대기'" in wseg.replace(" ", "") or "'대기'" in wseg,
    "★ 재전송 대상에 '대기' 고착 행이 포함된다",
    "성공/실패 판정은 데몬 스레드가 쓴다 — 배포 재시작으로 그 스레드가 죽으면 "
    "아무도 못 쓰고, '실패' 만 보는 스윕은 그 배송을 영원히 안 집는다")
chk("status IN ('실패','대기')" in APP,
    "★ 선기록(attempts 증가)도 '대기' 를 포함한다",
    "선기록이 '실패' 만 잡으면 대기 행은 rowcount 0 으로 건너뛴다")

print("\n[6] 개인정보 파기가 열린 하자를 남긴다")
_p = MNG.find("sel3 = (")
pseg = strip_comments(MNG[_p:_p + 1800], ("#",)) if _p > 0 else ""
chk(pseg.count("NOT EXISTS (SELECT 1 FROM defects") >= 2,
    "★ 집계와 실제 파기 **둘 다** 열린 하자를 제외한다",
    "한쪽만 고치면 '파기 예정 0건' 인데 실제로는 지워지거나 그 반대가 된다")
chk("'완료','반려'" in pseg,
    "★ 닫힘 판정이 서버 표준(완료·반려)과 같다")

print("\n[7] 사진 장수가 화면과 도착보고에서 같은 기준이다")
chk("SELECT COUNT(*) n FROM photos WHERE case_id=? AND partner_id=?" in APP,
    "★ 협력사 목록도 '내가 올린 사진' 을 센다",
    "사건 전체를 세면 화면은 '사진 3장' 인데 도착 보고는 '1장 이상 올려야' 로 거절된다")

print("\n[8] 발주처 화면이 서버 문턱과 같은 말을 한다")
_ins = strip_comments(INS, ("//",))
chk("Number(o.combined_amount||0) > 0" in _ins,
    "★ 합산 금액이 정해지기 전에는 추가공사 회신칸을 열지 않는다",
    "서버는 NO_AMOUNT 로 409 를 준다 — 눌러도 아무 일이 없는 버튼이었다")
_fa = _ins.find('data-act="faDecide"')
chk("canAct()" in _ins[max(0, _fa - 700):_fa],
    "★ 현장견적 승인 버튼이 등급으로 가려진다")
_ea = _ins.find('data-act="estAck"')
chk("canAct()" in _ins[max(0, _ea - 500):_ea],
    "★ 가견적 경보 확인 버튼이 등급으로 가려진다")

print("\n[9] 배포·백업 절차가 실제와 맞는다")
for _f in ("deploy/AWS_배포절차.md", "deploy/네이버클라우드_배포절차.md"):
    _t = read(_f)
    chk("restore backups/bokguon_" not in _t,
        f"★ {os.path.basename(_f)} — 상대경로 복구 명령이 없다",
        "bootstrap.sh 가 .env 에 /var/backups/bokguon 을 쓴다. 문서대로 치면 "
        "장애 상황에서 '파일이 없습니다' 로 끝난다")
    chk("BOKGUON_BACKUP_DIR" in _t,
        f"★ {os.path.basename(_f)} — 백업 위치를 어디서 읽는지 적혀 있다")
_ps = read("deploy/windows_setup.ps1")
chk("GEQ 8" in _ps and "/LOG" in _ps,
    "★ 사진 백업이 종료코드를 정규화하고 로그를 남긴다",
    "robocopy 는 정상 복사에도 1 을 준다 — 스케줄러에 늘 0x1 로 찍혀 "
    "성공·실패를 구분할 수 없었고 로그도 없었다")


# ── 구문 ──────────────────────────────────────────────────────────
for f in ("app.py", "dispatch.py"):
    try:
        ast.parse(read(f)); ok, why = True, ""
    except SyntaxError as e:
        ok, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok, f"{f} 구문", why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
