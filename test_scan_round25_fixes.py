# -*- coding: utf-8 -*-
"""25라운드 회귀 — **아무도 안 훑던 곳**(배포 스크립트·공개 폼·알림 매핑).

  ① 윈도 설치 스크립트가 `manage.py check` 의 **종료코드를 버렸다.**
     check 가 '배포 불가' 를 내고 exit 1 을 돌려줘도 그대로 초록 '설치 완료' 와
     서비스 URL 을 찍었다($LASTEXITCODE 가 파일 전체에 0번). 리눅스판은 같은 결함을
     이미 고쳐 뒀는데(CHECK_RC·경고 분기·exit 1) 윈도판엔 셋 다 없었다 —
     **그런데 실운영은 이 윈도 경로다.**

  ② 공개 입점신청 폼의 '사업장 주소'가 **서버에서 통째로 버려졌다.**
     FIELD_LIMITS 에 키가 없어 정제 결과에 안 담기는데 라우트는 그 결과를 읽는다.
     실행 검증(고치기 전): '서울 송파구 올림픽로 300' → 저장값 ''.
     그 화면 라벨은 "가까운 현장의 출동 요청을 우선 받으시려면 정확히 적어 주세요" 다.

  ③ 발주처 하자 목록·배지에 데모가 섞였다(형제 셋은 전부 걸렀다).
     실측: 진행중 하자 배지 2건 → 실제 1건.

  ④ 알림을 눌렀을 때 **갈 화면을 모르는 종류**가 협력사 1 · 발주처 5 있었다.
     ('미수선종결' 은 22라운드에 알림을 새로 만들면서 매핑을 빠뜨린 것이다)

  ⑤ 어드민 대행 낙찰만 low_price 를 안 고쳤다(형제는 둘 다 쓴다).
  ⑥ 승인 모달이 서버가 안 내려주는 회차를 읽어 라벨이 늘 '상한' 으로 굳었다.
  ⑦ 잔여시간이 'N시간 60분 남음' 으로 찍혔다.
  ⑧ 절감 리포트 엑셀만 셀 정제를 안 거쳤다(제어문자 하나로 500).

      python test_scan_round25_fixes.py
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


def read(rel, enc="utf-8"):
    try:
        return io.open(os.path.join(HERE, rel), encoding=enc).read()
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


def notify_calls(src):
    """`notify(` 를 **괄호 균형**으로 통째로 뜬다 — 여러 줄에 걸쳐 있다."""
    for m in re.finditer(r"\bnotify\(", src):
        i, depth = m.end() - 1, 0
        while i < len(src):
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        yield src[m.start():i + 1]


def tab_keys(html, var):
    i = html.find(f"const {var} = {{")
    if i < 0:
        return set()
    return set(re.findall(r"'([^']+)'\s*:", html[i:html.find("};", i)]))


APP = read("app.py")
PP = read("templates/partner_portal.html")
IP = read("templates/insurer_portal.html")

print("═" * 70)
print("  25라운드 회귀 — 배포 스크립트 · 공개 폼 · 알림 매핑")
print("═" * 70)

# ── ① ────────────────────────────────────────────────────────
print("\n[1] 설치 스크립트가 점검 실패를 초록으로 덮지 않는다")
PS = read("deploy/windows_setup.ps1", "utf-8-sig")
chk(not PS.startswith("<<읽기실패"), "windows_setup.ps1 을 읽었다", PS[:60])

#  ⚠⚠ **BOM 은 정확히 한 번.** PowerShell 5.1 은 BOM 없는 UTF-8 을 cp949 로 읽어
#    한글을 깨뜨리므로 BOM 이 필요하지만, **두 번 박히면 두 번째가 `﻿` 라는
#    보통 문자가 되어 `param()` 블록 인식이 깨진다**(구문 오류 3건).
#    실제로 이 파일을 고치면서 그렇게 만들었다 — utf-8 로 읽고 utf-8-sig 로 썼다.
#    사람 눈에는 안 보이고, 설치 담당자가 실행할 때 처음 터진다.
for _ps in ("deploy/windows_setup.ps1", "deploy/고정도메인_설정.ps1",
            "deploy/복구온_예약실행_등록.ps1", "deploy/복구온_외부공개_등록.ps1",
            "deploy/외부접속_상시가동.ps1"):
    _p = os.path.join(HERE, _ps)
    if not os.path.exists(_p):
        continue
    _b = io.open(_p, "rb").read()
    chk(_b[:3] == b"\xef\xbb\xbf",
        f"★ BOM 이 있다 — {os.path.basename(_ps)}",
        "없으면 PS 5.1 이 cp949 로 읽어 한글이 깨진다")
    chk(_b[3:6] != b"\xef\xbb\xbf",
        f"★★ BOM 이 **한 번만** 있다 — {os.path.basename(_ps)}",
        "두 번이면 param() 인식이 깨져 스크립트가 통째로 안 돈다")
chk(PS.count("$LASTEXITCODE") >= 2,
    f"★★ 종료코드를 실제로 받는다 ({PS.count('$LASTEXITCODE')}곳)",
    "PowerShell 5.1 의 $ErrorActionPreference='Stop' 은 **네이티브 exe 의 0 아닌 "
    "종료코드를 오류로 승격시키지 않는다** — 받아서 직접 보지 않으면 실패가 흐름을 "
    "멈추지 못한다")
chk("manage.py check" in PS and "$CheckRc" in PS,
    "★ check 의 결과를 변수에 담는다")
chk("smoke_test.py" in PS,
    "★ 두 번째 관문(스모크)도 부른다",
    "관문이 하나뿐이면 그것만 통과시키면 된다")
chk("아직 열면 안 됩니다" in PS,
    "★★ 실패하면 **초록 결론을 내지 않는다**")
chk(re.search(r"\bexit 1\b", PS) is not None,
    "★★ 실패하면 0 이 아닌 코드로 끝난다",
    "자동화가 이 스크립트를 부를 때 성공/실패를 구분할 수 있어야 한다")
#  ⚠ '설치 완료' 라는 글자는 파일 안에 여러 번 나온다(`Ok "의존성 설치 완료"`,
#    설명 주석…). **최종 결론 배너**만 찾아야 한다 — 그냥 find() 하면 훨씬 앞의
#    다른 문장을 집어 순서 판정이 뒤집힌다(실제로 그렇게 헛돌았다).
_i_fail = PS.find("아직 열면 안 됩니다")
_m_ok = re.search(r'Write-Host\s+"\s*설치 완료"', PS)
_i_ok = _m_ok.start() if _m_ok else -1
chk(0 < _i_fail < _i_ok,
    "★★ 실패 분기가 **최종 '설치 완료' 배너보다 먼저** 나온다(초록이 덮지 않는다)",
    f"실패분기 {_i_fail} · 최종배너 {_i_ok}")
chk(PS.find("exit 1", _i_fail) < _i_ok if _i_ok > 0 else False,
    "★ 그 분기 안에서 실제로 빠져나간다(배너까지 흘러가지 않는다)")
#  ★ 리눅스판이 되돌아가지 않았는지도 함께 본다
_sh = read("deploy/bootstrap.sh")
chk("CHECK_RC" in _sh and "아직 열면 안 됩니다" in _sh,
    "리눅스판도 그대로다(둘 다 같은 규칙을 쓴다)")

# ── ② ────────────────────────────────────────────────────────
print("\n[2] 공개 폼이 수집한 값을 버리지 않는다")
_i = APP.find("FIELD_LIMITS = ")
_fl = APP[_i:APP.find("\n\n", _i)]
chk('"address"' in _fl,
    "★★ FIELD_LIMITS 에 address 가 있다",
    "없으면 clean_public_form 결과에 안 담기고, 라우트가 그 결과를 읽으므로 "
    "**입력값이 조용히 ''** 가 된다")
#  ★ 화면이 실제로 그 칸을 두고 있는지도 확인 — 서버만 고치면 짝이 안 맞는다
_ap = read("templates/apply_partner.html")
chk("address" in _ap,
    "★ 신청 화면에 그 입력칸이 있다(짝이 맞는다)")
#  ★★ 화면이 보내는 키가 **전부** 서버에 받아지는지 전수로 본다
_sent = set(re.findall(r"(\w+)\s*:\s*val\('([^']+)'\)", _ap))
_sent = {b for _a, b in _sent}
_limits = set(re.findall(r'"(\w+)"\s*:\s*\d+', _fl))
#  ⚠ [라운드248] staff_count 는 has_license/has_insurance 와 같은 이유로 여기 있다 —
#    api_create_application 이 d=clean(FIELD_LIMITS 필터) 로 덮어쓰기 **전에** 원본
#    body 에서 먼저 읽어(1인사업자 관문 판정 + staff_n 추출) INSERT 에 직접 묶는다.
#    FIELD_LIMITS 는 문자열 길이제한 용도라 정수 필드는 애초에 거길 거칠 필요가 없다.
_extra = {"agree_privacy", "website_url", "_hp", "has_license", "has_insurance", "staff_count"}
_lost = sorted(_sent - _limits - _extra)
chk(not _lost,
    "★★ 신청 화면이 보내는 값이 하나도 버려지지 않는다",
    f"서버가 안 받는 키: {_lost} — 화면은 물어보고 서버는 버린다")

# ── ③ ────────────────────────────────────────────────────────
print("\n[3] 발주처 하자에 데모가 섞이지 않는다")
chk("FROM defects WHERE insurer_id=? AND COALESCE(is_demo,0)=0" in APP,
    "★★ 데모를 뺀다",
    "같은 응답의 형제 셋(cases·settlements·field_agreements)은 전부 뺀다. "
    "실측: 진행중 하자 배지가 2건(실제 1건) — 정확히 2배")
chk(APP.count("FROM defects WHERE insurer_id=? AND COALESCE(is_demo,0)=0") == 2,
    "★ 대시보드와 전용 라우트 **둘 다** 고쳤다",
    "한쪽만 고치면 같은 화면의 두 경로가 다른 숫자를 준다")

# ── ④ ────────────────────────────────────────────────────────
print("\n[4] 알림을 누르면 갈 화면을 안다")
_aud = {"partner": set(), "insurer": set()}
for _f in ("app.py", "dispatch.py", "compliance.py"):
    _s = read(_f)
    if _s.startswith("<<읽기실패"):
        continue
    for _call in notify_calls(_s):
        _t = re.search(r'notify\(\s*conn\s*,\s*"([^"]+)"', _call)
        _a = re.search(r'audience_type\s*=\s*"([\w-]+)"', _call)
        if not (_t and _a):
            continue
        if _a.group(1) in ("partner", "all-partner"):
            _aud["partner"].add(_t.group(1))
        elif _a.group(1) == "insurer":
            _aud["insurer"].add(_t.group(1))
_pt, _it = tab_keys(PP, "NOTI_TAB"), tab_keys(IP, "NOTI_TAB")
chk(_aud["partner"] and _pt, "알림 종류와 탭 표를 둘 다 읽었다")
_gap_p = sorted(_aud["partner"] - _pt)
chk(not _gap_p,
    f"★★ 협력사가 받는 {len(_aud['partner'])}종이 전부 갈 탭을 안다",
    f"모르는 종류: {_gap_p} — 폴백으로 떨어지면 눌린 알림과 무관한 화면이 열린다")
_gap_i = sorted(_aud["insurer"] - _it)
chk(not _gap_i,
    f"★★ 발주처가 받는 {len(_aud['insurer'])}종이 전부 갈 탭을 안다",
    f"모르는 종류: {_gap_i}")
_no = func_body(PP, "async function notiOpen") or PP
chk("n.case_id ? 'sites'" in PP,
    "★ 모르는 종류라도 사건이 걸려 있으면 그 사건이 있는 화면으로 간다",
    "'입찰 공고' 로 보내면 눌린 알림과 아무 상관이 없는 화면이 뜬다")

# ── ⑤ ────────────────────────────────────────────────────────
print("\n[5] 낙찰가를 화면마다 다르게 말하지 않는다")
_aw = APP.find("award_route='경매'\n                WHERE id=? AND status IN ('입찰중','승인대기')")
_seg = APP[max(0, _aw - 500):_aw] if _aw > 0 else ""
chk("low_price=?" in _seg,
    "★★ 어드민 대행 낙찰도 low_price 를 확정한다",
    "형제(발주처 낙찰 승인)는 둘 다 쓴다. 여기만 안 쓰면 최저가가 아닌 업체를 "
    "고른 경우 low_price 에 옛 최저가가 남는다")

# ── ⑥ ────────────────────────────────────────────────────────
print("\n[6] 승인 모달이 없는 값을 읽지 않는다")
chk('"auction_round": bid_cap_of(conn, c)[3]' in APP,
    "★ 서버가 회차를 내려준다",
    "화면은 `case.auction_round===2` 로 라벨을 갈라 쓰는데(1차=상한/2차=최소금액) "
    "서버가 안 주면 판정이 늘 거짓이라 **라벨이 '상한' 으로 굳는다**(철칙 6)")
chk("2차 최소금액" in IP,
    "★ 화면의 두 갈래 라벨은 그대로다")

# ── ⑦ ────────────────────────────────────────────────────────
print("\n[7] '60분 남음' 이 찍히지 않는다")
chk("if(mm === 60){ hh += 1; mm = 0; }" in PP,
    "★★ 반올림이 60분을 만들면 시간으로 올린다",
    "`Math.round((h%1)*60)` 은 h=1.999 에서 60 을 만든다 → '1시간 60분 남음'")
#  ★ 실제로 그 함수를 돌려 본다 — 문자열 검사만으로는 못 잡는다
_lt = func_body(PP, "function leftText") or ""
_body = PP[PP.find("function leftText"):]
_body = _body[:_body.find("\n}") + 2]
try:
    import subprocess
    _js = _body + "\n" + "".join(
        f"console.log(JSON.stringify([{h}, leftText({h})]));"
        for h in (1.999, 0.9999, 2.4999, 47.999, 1.5, 0.5, 0))
    _r = subprocess.run(["node", "-e", _js], capture_output=True)
    _out = (_r.stdout or b"").decode("utf-8", "replace")
    _bad = [ln for ln in _out.splitlines() if "60분" in ln]
    chk(not _bad and _out, f"★★ 실제로 돌려 봐도 60분이 안 나온다",
        f"{_bad or _out or (_r.stderr or b'').decode('utf-8', 'replace')[:200]}")
    print("        " + " · ".join(_out.split()))
except Exception as _e:
    chk(False, "leftText 실행", f"{type(_e).__name__}: {_e}")

# ── ⑧ ────────────────────────────────────────────────────────
print("\n[8] 보험사에 나가는 엑셀이 제어문자로 죽지 않는다")
chk('ws.append([_xl_safe(r["category"]), r["n"], est, aw, sv,' in APP,
    "★ 절감 리포트 엑셀도 셀 정제를 거친다",
    "자매인 월 정산 명세서는 이미 거친다 — 공종명에 제어문자가 하나라도 있으면 "
    "openpyxl 이 IllegalCharacterError 로 죽어 내려받기가 500 이 된다")

print("\n[+] 공개 서빙 경로에 서비스 파일만 있다")
#  ⚠ `static/` 아래는 **인증 없이 누구나 읽는다.** 도구가 여기에 세션 상태를
#    남긴 적이 있고(`static/.omc/`), 운영 서버가 그대로 200 으로 내줬다.
#    배포 목록이 손목록이던 시절엔 눈에도 안 띄었다 — 글롭으로 바꾸자마자 드러났다.
_junk = []
for _root, _dirs, _names in os.walk(os.path.join(HERE, "static")):
    for _n in _names:
        _rel = os.path.relpath(os.path.join(_root, _n), HERE).replace("\\", "/")
        if any(p.startswith(".") for p in _rel.split("/")[1:]):
            _junk.append(_rel)
chk(not _junk, "★★ static/ 에 숨김 파일·도구 상태가 없다",
    f"공개 서빙된다: {_junk[:4]}")
_ext = {os.path.splitext(n)[1].lower()
        for _r, _d, _ns in os.walk(os.path.join(HERE, "static")) for n in _ns}
_bad_ext = _ext & {".db", ".sqlite", ".sqlite3", ".env", ".key", ".pem", ".log", ".bak"}
chk(not _bad_ext, "★★ static/ 에 DB·키·로그 확장자가 없다", f"{sorted(_bad_ext)}")

print("\n[+] 처음 들어온 발주처에게 무엇부터 할지 알려 준다")
#  ⚠ 종전에는 첫 로그인 화면이 **0으로만** 채워졌다(진행중 0 · 승인대기 0 ·
#    절감 0원 · 지급 0원). 무엇부터 눌러야 하는지도, 그 다음에 무슨 일이
#    생기는지도 없었다 — 실측으로 '환영·처음·시작하기·첫 사건' 이 0건이었다.
#    협력사 포털에서 고친 것과 같은 빈틈이다.
chk("function insurerStartPanel" in IP, "★ 첫 사용 안내가 있다")
_isp = IP[IP.find("function insurerStartPanel"):IP.find("RENDER.home = () => {")]
chk("(k.total || 0) > 0) return ''" in _isp.replace("if((", "(").replace("if ((", "("),
    "★★ 사건이 하나라도 있으면 안 뜬다(자리를 차지하지 않는다)")
chk("${insurerStartPanel()}" in IP, "★ 홈 화면이 실제로 부른다")
#  ★★ 법률 철칙 — 금액을 정하는 것은 발주처다
chk("귀사가 승인" in _isp, "★★ 승인 주체가 발주처임을 밝힌다 (철칙 1)")
chk("복구온이 금액을 정하거나 협상하지 않습니다" in _isp,
    "★★ 우리가 금액을 정하지 않는다고 적는다 (철칙 1·2)",
    "'알아서 싸게 해 준다' 로 읽히면 손해사정 경계를 넘는 인상을 준다")
for _bad in ("손해사정", "보험금", "면책"):
    chk(_bad not in _isp, f"★ 보험의 언어를 쓰지 않는다 — '{_bad}'")
chk('data-arg="newcase"' in _isp, "★ 첫 사건 등록으로 바로 갈 수 있다")
chk('href="/docs/insurer-api"' in _isp, "★ 연동 안내서로 이어진다")

print("\n[+] 발주처 연동 API 가 데모 사건을 내보내지 않는다")
#  ⚠ 발주처 **화면**은 `COALESCE(c.is_demo,0)=0` 으로 걸렀는데 **연동 API 만**
#    빠져 있었다. 실측: ○○손보 화면 78건 vs API 90건 — 12건이 남의 전산으로
#    들어간다. 받는 쪽은 그게 우리 검증용인지 알 방법이 없고, 자기 시스템에
#    없는 사건이 섞이면 대사가 통째로 깨진다.
#    ⚠ POST(접수)의 idem_key 조회는 **중복 제출 확인**이라 대상이 아니다 —
#      거기에 데모 조건을 걸면 같은 키로 두 번 들어온 요청을 못 막는다.
for _rt, _fn in (("/api/v1/cases", "def api_v1_case_list"),
                 ("/api/v1/cases/<case_no>", "def api_v1_case_status")):
    _b = func_body(APP, _fn)
    chk("FROM cases" in _b and "is_demo" in _b,
        f"★★ {_rt} 가 데모를 거른다",
        "발주처 화면과 같은 기준이어야 한다 — 한쪽만 걸면 숫자가 갈린다")
_lst = func_body(APP, "def api_v1_case_list")
_one = func_body(APP, "def api_v1_case_status")
chk("COALESCE(is_demo,0)=0" in _lst and "COALESCE(is_demo,0)=0" in _one,
    "★ 목록과 단건이 **같은 조건**을 쓴다",
    "목록에 없는 사건이 단건으로 열리면 '목록이 빠뜨렸다' 로 읽힌다")

print("\n[+] 검증 도구가 운영 서버·비밀번호를 품고 있지 않다")
#  ⚠ 실제로 겪었다 — `test_b5_severity.py` 하나만 BASE 가 8771(운영)로 박혀 있었고
#    환경변수도 안 읽었다. 게다가 admin/staff 비밀번호까지 옛 값이 박혀 있어
#    배터리를 돌릴 때마다 **운영 로그인을 두드려 401** 을 냈다.
#    운영 감사로그에 로그인 실패 383건이 쌓였고, 잠금(5회)이 걸린 서버라
#    실운영 중 계정이 잠길 수 있었다. 형제 파일들은 이미 8799 로 고쳐져 있었다.
_bad_base, _bad_pw = [], []
for _f in sorted(os.listdir(HERE)):
    if not (_f.startswith("test_") and _f.endswith(".py")):
        continue
    _s = read(_f)
    if _s.startswith("<<읽기실패"):
        continue
    #  주석은 뺀다 — "8771 은 운영이라" 같은 **설명 문구**가 걸리면 안 된다.
    _code = "\n".join(l for l in _s.splitlines() if not l.strip().startswith("#"))
    if re.search(r'BASE\s*=\s*"[^"]*:8771', _code):
        _bad_base.append(_f)
    if re.search(r'login\([^)]*"(bokguon2026|staff2026|admin1234)"', _code):
        _bad_pw.append(_f)
chk(not _bad_base,
    "★★ 어떤 검증 파일도 BASE 를 운영(8771)로 두지 않는다", _bad_base)
chk(not _bad_pw,
    "★★ 어떤 검증 파일도 비밀번호를 코드에 적어 두지 않는다", _bad_pw)

print("\n[+] 검증 도구가 운영 DB 를 가리킨 채로는 못 돈다")
#  ⚠ 실제로 겪었다 — `test_dispatch.py` 를 BOKGUON_DB_PATH 없이 돌렸더니
#    기본 경로(운영 bokguon.db)로 붙었고, 그 실행이 중간에 죽어 cleanup 이
#    안 돌아 운영에 검증 사건 10건·협력사 2곳·호출 208이 남았다.
#    배터리 입구에는 방어가 있었지만 **테스트 하나를 직접 돌리는 문 36개**에는
#    아무것도 없었다. 그래서 방어를 DB 를 여는 곳 한 곳에 뒀다.
_dbsrc = read("db.py")
chk("_ENTRY.startswith(\"test_\")" in _dbsrc,
    "★★ db.py 가 검증 진입점을 알아본다")
chk("os.path.abspath(DB_PATH) == os.path.abspath" in _dbsrc,
    "★★ **경로가 운영 파일일 때만** 막는다",
    "자기 임시 DB 를 쓰는 검증(첫날 완주)까지 막으면 안 된다")
chk("raise SystemExit" in _dbsrc, "★ 경고가 아니라 **중단**이다")
chk("BOKGUON_DB_PATH" in _dbsrc.split("raise SystemExit")[1][:600],
    "★ 어떻게 고치는지 알려 준다")

print("")
try:
    ast.parse(APP); _ok, _why = True, ""
except SyntaxError as e:
    _ok, _why = False, f"{e.lineno}행: {e.msg}"
chk(_ok, "app.py 구문", _why)
for _f, _t in (("templates/partner_portal.html", PP),
               ("templates/insurer_portal.html", IP)):
    chk(_t.count("<div") == _t.count("</div>"),
        f"{_f} div 균형", f"{_t.count('<div')} / {_t.count('</div>')}")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
