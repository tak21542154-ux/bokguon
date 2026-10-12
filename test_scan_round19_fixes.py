# -*- coding: utf-8 -*-
"""19라운드 회귀 — **바로 앞 라운드가 만든 부작용**을 되돌린 것들.

  이 판의 교훈은 하나다: 새 코드를 넣으면 **그동안 아무도 안 밟던 분기가
  갑자기 기본 경로가 된다.**
    · admin.js 가 no_photo 를 보내기 시작하자, 관리자 경로의 `est = 0` 이
      깨어나 운영자가 입력한 가견적을 말없이 버렸다(그 값이 곧 2차 하한이다).
    · 같은 이유로 "입찰 공고가 발송되었습니다" 토스트가 거짓말이 됐다.
    · 새 핸들러 이름이 옛 핸들러와 겹쳐, 새 버튼이 옛 라우트를 불렀다.
    · 전환 라우트를 만들어 놓고 **누를 곳을 안 만들었다**(문만 있고 손잡이가 없다).
    · 사진을 휴지통으로 옮겨 놓고, 파기 루프는 그 하위 폴더를 안 봤다.

      python test_scan_round19_fixes.py
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


def func_body(src, header):
    i = src.find(header)
    if i < 0:
        return ""
    j = len(src)
    for pat in ("\ndef ", "\n@app."):
        k = src.find(pat, i + len(header))
        if 0 < k < j:
            j = k
    return src[i:j]


def strip_py(t):
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("#"))


def strip_js(t):
    t = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", t, flags=re.S)
    return "\n".join(ln for ln in t.splitlines() if not ln.strip().startswith("//"))


APP, ADM = read("app.py"), read("static/admin.js")
INS, MAN = read("templates/insurer_portal.html"), read("manage.py")

print("═" * 70)
print("  19라운드 회귀 — 앞 라운드가 깨운 분기·이름·입구")
print("═" * 70)

print("\n[1] 새 코드가 깨운 분기가 값을 버리지 않는다")
_ac = strip_py(func_body(APP, "def api_case_create"))
chk('if str(d.get("est_price") or "").strip():' in _ac,
    "★ 사진 없이 접수해도 입력한 가견적을 남긴다",
    "이 값은 상한이 아니라 **2차 경매의 하한**이다. 버리면 하한이 늘 0이 되어 규칙이 "
    "죽고, 가견적 수정은 '입찰중' 전용이라 되돌릴 문도 없다(형제 경로는 이미 보존)")

print("\n[2] 나가지 않은 공고를 나갔다고 말하지 않는다")
chk('"no_photo": bool(no_photo)' in _ac, "★ 응답이 트랙을 밝힌다")
chk("r.no_photo" in strip_js(ADM), "★ 화면이 그 값으로 문구를 가른다")

print("\n[3] 새 핸들러 이름이 옛 것과 겹치지 않는다")
_names = re.findall(r"ACT\.(\w+)\s*=", strip_js(ADM))
_dup = sorted({x for x in _names if _names.count(x) > 1})
chk(not _dup,
    f"★ ACT 키가 중복 대입되지 않는다 (등록 {len(_names)}개)",
    "같은 키에 두 번 대입하면 **나중 것이 이긴다** — 새 [철회] 버튼이 옛 라우트를 "
    "불러 409 를 받았다. 즉 앞 라운드의 수정이 화면에서 도달 불가였다. "
    + (f"중복: {_dup}" if _dup else ""))

print("\n[4] 만든 문에 손잡이가 있다")
for route, act, lbl in (
        ("/api/cases/<int:cid>/to-dispatch", "caseToDispatch", "출동 수배로 전환"),
        ("/api/change-orders/<int:coid>/withdraw\"", "coWithdrawReq", "실사요청 철회"),
        ("/api/outbox/<int:nid>/reopen", "obReopen", "발송 대기로 되돌리기")):
    chk(route in APP and f'data-act="{act}"' in ADM and f"ACT.{act}" in ADM,
        f"★ {lbl} — 라우트·버튼·핸들러가 다 있다",
        "라우트만 만들고 누를 곳을 안 만들면 고친 것이 아니다")

print("\n[5] 전환한 사건이 실제로 그 화면에 뜬다")
_td = strip_py(func_body(APP, "def api_case_to_dispatch"))
#  ⚠ **처음엔 intake_type 을 '사진없음' 으로 덮어써서 맞췄다.** 20라운드에서
#    그게 틀렸다고 드러났다 — 그 값은 '어떻게 들어왔나' 라는 이력이고 타임라인이
#    그것으로 가견적(= 2차 하한이 될 값) 표시를 가른다. 이력을 고쳐 목록을 맞추는
#    대신, 목록이 묻는 질문을 '지금 수배가 필요한가' 로 바로잡았다.
#    그래서 이 회귀도 '덮어쓰지 않는다 + dispatch_status 를 비운다' 로 바뀐다.
chk("intake_type='사진없음'" not in _td,
    "★ 이력(intake_type)을 덮어쓰지 않는다")
chk("dispatch_status=NULL" in _td,
    "★ 출동 이력을 비워 목록의 세 번째 조건을 맞춘다",
    "목록 조건에 `COALESCE(dispatch_status,'')=''` 가 있다 — 한 번 출동을 다녀온 "
    "사건은 이 값이 남아 목록에서 빠진다")

print("\n[6] 휴지통에 넣은 것이 실제로 파기된다")
_pp = strip_py(func_body(MAN, "def cmd_prune_personal"))
chk("os.walk(_tdir)" in _pp,
    "★ 파기가 하위 폴더까지 훑는다",
    "옮기는 쪽은 rel_path 를 살려 `_trash/<사건id>/<파일>` 로 넣는데 지우는 쪽이 "
    "최상위만 보면 영구히 남는다(처리방침의 파기 미이행)")
_of = strip_py(func_body(MAN, "def _orphan_photo_files"))
chk('os.path.join(root, "_trash")' in _of,
    "★ 고아 집계가 휴지통을 세지 않는다",
    "우리가 옮겨 둔 것을 '검증이 운영 폴더에 쓴 흔적' 으로 경고하면 정리할수록 "
    "경고가 커진다(실측 673 → 464)")

print("\n[7] 발주처가 보는 숫자·이름")
chk("(r.saved || 0) * 100 / r.est_sum" in INS,
    "★ 절감률을 엑셀과 같은 식으로 낸다",
    "서버는 절감액을 사건별 max(0, 기준−확정) 로 클램프하는데 화면만 합계끼리 "
    "(1−확정/기준) 로 재계산해, 기준을 넘는 공종에서 **'−-30.0%'** 가 찍혔다")
chk("비교 기준 합계(원)" in APP and "가견적 합계(원)" not in APP,
    "★ 절감 리포트가 개산가를 '가견적' 이라고 인쇄하지 않는다",
    "2차 사건의 비교 기준은 보상담당자 가견적이 아니라 복구온 표준단가 개산 상단이다 — "
    "보험사 결재 서류에서 명의가 바뀌면 안 된다(철칙 2). 월 명세서는 이미 고쳐져 있었다")
_il = strip_py(APP[APP.find("절감률은 **확정가"):APP.find("절감률은 **확정가") + 900])
chk('c["low_price"] or 0' not in _il,
    "★ 낙찰 전 사건에 절감률을 찍지 않는다",
    "low_price 는 투찰마다 갱신되는 현재 최저가일 뿐 확정가가 아니다 — 주석은 그걸 "
    "문제라고 적어 놓고 코드는 그대로 폴백했다")
_co = strip_py(func_body(APP, "def api_change_orders"))
chk("c.partner_name" in _co and "co.reason" in _co,
    "★ 변경견적 검색이 검색창이 약속한 3종을 다 건다",
    "검색창은 '접수번호·업체·사유' 인데 접수번호만 걸면, 업체명으로 찾을 때 0건이 "
    "나오고 운영자는 그런 건이 없다고 믿는다")

print("")
for f in ("app.py", "manage.py", "dispatch.py"):
    try:
        ast.parse(read(f)); ok_, why = True, ""
    except SyntaxError as e:
        ok_, why = False, f"{e.lineno}행: {e.msg}"
    chk(ok_, f"{f} 구문", why)

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
