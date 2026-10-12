# -*- coding: utf-8 -*-
"""12라운드 확정 결함 회귀 — **출시 직전에 나온 것들**을 못 박는다.

  이 라운드에서 잡은 것 중 성격이 다른 두 부류가 있다.

   ① **만들어 놓고 안 붙인 것** — 함수는 썼는데 호출이 없고, 주석은 달았는데
      코드가 없다. 겉보기에 "고쳤다" 로 보여서 다음 사람이 다시 안 본다.
   ② **go-live 직후가 곧 시드 재실행 조건** — 사건도 관리자도 0 이 되니
      '빈 DB' 판정에 정확히 들어맞아서, 서버를 한 번 재시작하면 방금 비운
      운영 DB 에 데모가 되돌아온다. 출시 당일에만 터지는 결함이다.

      python test_scan_round12_fixes.py
"""
import ast
import glob
import io
import json
import os
import re
import shutil
import subprocess
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


def strip_comments(text, marks=("#", "//", "REM ", "rem ", "--")):
    """주석을 걷어낸다 — **내가 쓴 설명문을 코드로 오독하지 않기 위해.**

    오늘만 네 번 당했다. 고쳐 놓고도 실패가 뜨면 다음 사람은 코드를 의심한다.
    """
    #  ⚠ **`accept="image/*"` 의 `/*` 는 주석이 아니다.** 그냥 짝을 맞추면
    #    저 아래 진짜 `*/` 까지 5만 자가 '주석' 으로 지워지고, 그 구간의 코드는
    #    `X not in 코드` 검사를 전부 통과한다(거짓 초록). 실제로 그랬다.
    #    앞 글자가 식별자·따옴표면 주석 시작으로 보지 않는다.
    text = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return "\n".join(ln for ln in text.splitlines()
                     if not any(ln.strip().startswith(m) for m in marks))


APP = read("app.py")
DB_ = read("db.py")
MNG = read("manage.py")
PAI = read("photo_ai.py")
PAR = read("templates/partner_portal.html")
ADM = read("static/admin.js")

print("═" * 70)
print("  12라운드 회귀 — 반쯤 붙인 수정 · go-live 직후 · 돈 표시")
print("═" * 70)

# ══════════════════════════════════════════════════════════════════
print("\n[1] '함수만 만들고 안 붙인 것' 부류")
# ══════════════════════════════════════════════════════════════════
chk("def _xl_safe(" in APP, "_xl_safe 공통 함수가 있다")
_i = APP.find("def _statement_xlsx")
seg = strip_comments(APP[_i:_i + 6000], ("#",)) if _i > 0 else ""
_appends = re.findall(r"ws\.append\((.*?)\)\n", seg, re.S)
#  ⚠ 빈 줄(`[]`)과 머리글(`heads`, 우리가 쓴 한글 열이름)은 사람이 넣은 값이 아니다.
#    **DB 에서 온 값을 담은 append 만** 검사한다 — 안 그러면 늘 빨강이라 아무도 안 본다.
_data_appends = [a for a in _appends
                 if any(k in a for k in ("ln[", "t[", "stmt[", "stmt.get", "ln.get"))]
chk(len(_data_appends) >= 3,
    f"_statement_xlsx 에서 **데이터가 실린** ws.append 를 {len(_data_appends)}곳 찾았다",
    f"전체 {len(_appends)}곳 — 찾는 방식이 어긋났는지 확인할 것")
chk(all("_xl_safe" in a for a in _data_appends),
    "★ 보험사 월 명세서의 **데이터 행 전부**가 _xl_safe 를 지난다",
    "제어문자 하나로 그 달 명세서가 통째로 500 이 되고, 수식 주입도 열린다: "
    + "; ".join(a.strip()[:50] for a in _data_appends if "_xl_safe" not in a))

_j = PAI.find("def _heic_to_jpeg")
hseg = strip_comments(PAI[_j:_j + 1600], ("#",)) if _j > 0 else ""
chk("MAX_PIXELS" in hseg and "_w * _h > MAX_PIXELS" in hseg,
    "★ HEIC 변환에 픽셀 가드가 **코드로** 있다(주석 말고)")
chk(("_w * _h > MAX_PIXELS" in hseg and 'img.convert("RGB")' in hseg
     and hseg.index("_w * _h > MAX_PIXELS") < hseg.index('img.convert("RGB")')),
    "★ 픽셀 검사가 convert(\"RGB\") **앞**에 있다",
    "뒤에 있으면 방어선 앞에서 메모리가 터진다 — 아이폰 기본 형식이라 실제로 여기로 들어온다")

#  ⚠ 조건이 **다음 줄**에 있다(`… if _sms_live else 0`). 한 줄만 보면 늘 실패한다 —
#    '한 줄 검사' 로는 여러 줄에 걸친 식을 못 본다.
_smsapp = strip_comments(APP, ("#",))
_sms = [_smsapp[max(0, m.start() - 200):m.start() + 300]
        for m in re.finditer(r"sms = .*?normalize_phone", _smsapp, re.S)]
chk(bool(_sms), f"'문자 가능 수' 계산부를 {len(_sms)}곳 찾았다")
chk(all("_sms_live" in s for s in _sms),
    "★ '문자 가능 N곳' 이 팝빌 연동 여부(NOTIFY_ENABLED·ready)를 본다",
    "번호가 있다 ≠ 문자가 나간다. 미연동이면 0통인데 화면은 N곳이라 한다")
chk("_sms_live = NOTIFY_ENABLED and POPBILL.ready()" in _smsapp,
    "★ 판정이 실제로 NOTIFY_ENABLED 와 POPBILL.ready() 둘 다를 본다")

# ══════════════════════════════════════════════════════════════════
print("\n[2] go-live 직후가 '빈 DB' 조건이 되지 않는다")
# ══════════════════════════════════════════════════════════════════
_k = DB_.find("_empty = conn.execute")
gseg = strip_comments(DB_[_k:_k + 2600], ("#",)) if _k > 0 else ""
chk("FROM partners" in gseg,
    "★ 시드 게이트가 **협력업체 수**를 본다(go-live 가 남기는 값)")
chk("go_live_at" in gseg,
    "★ 시드 게이트가 **출시 표식**을 본다(무엇을 지워도 남는다)")
chk("go_live_at" in MNG and "INSERT INTO settings" in MNG,
    "★ go-live 가 출시 표식을 settings 에 남긴다")

# ══════════════════════════════════════════════════════════════════
print("\n[3] 마감 가드 — 형제 경로 누락")
# ══════════════════════════════════════════════════════════════════
_m = APP.find("def api_co_close_full")
cseg = strip_comments(APP[_m:_m + 2600], ("#",)) if _m > 0 else ""
chk("AUCTION_EXPIRED_SQL" in cseg and 'code": "NOT_CLOSED' in cseg,
    "★ 전체재경매 마감에 마감시각 가드가 있다",
    "마감 전에 눌러도 실행돼서, 아직 들어올 수 있던 더 낮은 입찰이 잘린다")
chk(cseg.find("NOT_CLOSED") < cseg.find('d.get("failed")'),
    "★ 가드가 **낙찰·유찰 두 갈래 앞**에 있다",
    "마감 전 유찰도 아직 투찰할 업체를 통째로 배제한다")
_adm = strip_comments(ADM)
chk(_adm.count("force:true") >= 2 and "coFailFull" in _adm,
    "★ 화면이 두 갈래 모두 force 로 되묻는다",
    "서버만 조이면 운영자가 갇힌다 — 유찰 버튼만 막히는 상태였다")
_f = _adm.find("async function coFailFull")
chk(_f > 0 and "NOT_CLOSED" in _adm[_f:_f + 1400],
    "★ 유찰 버튼이 NOT_CLOSED 를 처리한다")

# ══════════════════════════════════════════════════════════════════
print("\n[4] 돈 — 협력사가 보는 '받을 돈' 이 실제와 같은가")
# ══════════════════════════════════════════════════════════════════
chk('"fee_vat_included"' in APP,
    "★ 협력사 대시보드가 부가세 기준을 내려 준다")
_p = strip_comments(PAR, ("//",))
chk("FEE_VAT_INCLUDED" in _p and "roundHalfEven" in _p,
    "★ 화면 payoutOf 가 부가세 기준과 반올림 규칙을 함께 쓴다")

#  ── 주장 대신 **두 구현을 실제로 돌려 비교한다** ──────────────────
node = shutil.which("node")
m = re.search(r"const roundHalfEven = .*?\n\};\nconst payoutOf = \(amount, bp\) => \{.*?\n\};",
              PAR, re.S)
if not node:
    chk(False, "★ 서버·화면 지급액 대조", "node 가 없어 검사하지 못했다(검사 안 함 ≠ 통과)")
elif not m:
    chk(False, "★ 서버·화면 지급액 대조", "템플릿에서 payoutOf 를 찾지 못했다")
else:
    os.environ.setdefault("BOKGUON_ENV", "dev")
    os.environ.setdefault("BOKGUON_SEED_DEMO", "0")
    sys.path.insert(0, HERE)
    import app as A  # noqa: E402

    CASES = [(a, bp) for a in (1_000_000, 3_333_333, 5_000_000, 5_000_050,
                               12_345_678, 999_999, 7_777_775)
             for bp in (0, 500, 900, 1000, 1500)]
    js_src = ("let FEE_VAT_INCLUDED=true;const VAT_RATE=10;\n" + m.group(0) +
              "\nconst O=[];for(const [a,bp] of " + json.dumps(CASES) + "){"
              "FEE_VAT_INCLUDED=true;const i=payoutOf(a,bp);"
              "FEE_VAT_INCLUDED=false;const e=payoutOf(a,bp);O.push([a,bp,i,e]);}"
              "console.log(JSON.stringify(O));")
    _tmp = os.path.join(HERE, "._vatparity.js")
    io.open(_tmp, "w", encoding="utf-8").write(js_src)
    try:
        r = subprocess.run([node, _tmp], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    finally:
        try:
            os.remove(_tmp)
        except OSError:
            pass
    if r.returncode:
        chk(False, "★ 서버·화면 지급액 대조", (r.stderr or "")[:160])
    else:
        bad = []
        for a, bp, j_inc, j_exc in json.loads(r.stdout):
            _, s_inc = A.compute_fee(a, bp, True)
            _, s_exc = A.compute_fee(a, bp, False)
            if s_inc != j_inc:
                bad.append(f"{a:,}@{bp}bp 포함 {s_inc:,}≠{j_inc:,}")
            if s_exc != j_exc:
                bad.append(f"{a:,}@{bp}bp 별도 {s_exc:,}≠{j_exc:,}")
        chk(not bad,
            f"★ 서버 compute_fee 와 화면 payoutOf 가 {len(CASES)}조합 전부 일치",
            " / ".join(bad[:4]))

# ══════════════════════════════════════════════════════════════════
print("\n[5] 회계로 나가는 파일 — 데모가 실거래로 보이지 않는가")
# ══════════════════════════════════════════════════════════════════
_e = APP.find("def api_settlements_export")
#  ⚠⚠ [라운드598] 이 함수에 행수 상한(cap)·전체건수 COUNT 서브쿼리를 추가하면서
#    함수 앞부분이 길어져, 원래 이 자리에 있던 고정폭 3000자 창이 "정산번호"
#    보다 앞의 "구분"까지는 담아도 그 비교 대상(정산번호, 실제 offset 3029)을
#    창 밖으로 밀어냈다(실측: eseg 안에 "정산번호"가 없어 이 check 가 조용히
#    실패 — 검증 실효 상실이지 실제 열 순서 회귀가 아니었다). 함수 전체
#    길이(4737자)를 넉넉히 덮도록 창을 넓힌다 — 창 크기를 이 파일의 다른
#    자리처럼 고정폭으로 유지하되(이 파일의 기존 관례), 다음 몇 라운드의
#    사소한 추가에도 다시 안 밀리게 여유를 둔다.
eseg = strip_comments(APP[_e:_e + 6000], ("#", "--")) if _e > 0 else ""
chk("AS kind" in eseg and "insurers" in eseg,
    "★ 정산 CSV 가 데모 여부를 계산한다(발주처까지 본다)",
    "운영 DB 의 데모 사건 대부분은 is_demo 가 비어 있고 '데모 발주처 소속'으로만 데모다")
chk('"구분"' in eseg and eseg.index('"구분"') < eseg.index('"정산번호"'),
    "★ '구분' 이 **첫 열**이다(뒤에 두면 가로로 밀려 안 보인다)")

# ══════════════════════════════════════════════════════════════════
print("\n[6] 운영자가 누르는 배치 파일")
# ══════════════════════════════════════════════════════════════════
CR, LF = b"\r\n", b"\n"
_bad = []
for f in sorted(glob.glob(os.path.join(HERE, "*.bat"))):
    b = io.open(f, "rb").read()
    if b.count(CR) != b.count(LF):
        _bad.append(os.path.basename(f))
chk(not _bad, "★ 모든 .bat 이 CRLF 다",
    "LF 만 있으면 cmd 가 줄을 오독하는데 배치는 성공으로 끝난다: " + ", ".join(_bad))

_lab = read("복구온_로컬체험.bat")
chk("BOKGUON_DB_PATH" in _lab,
    "★ 체험 서버가 **자기 DB** 를 쓴다",
    "운영 DB 를 쓰면서 데모 시드를 켰다 — 출시 뒤 연습 한 번에 실사건 옆으로 데모가 섞인다")

# ══════════════════════════════════════════════════════════════════
print("\n[7] 산출물 표기")
# ══════════════════════════════════════════════════════════════════
_stale = []
for pat in ("*.md", "*.bat", "*.py", "deploy/*.md"):
    for f in glob.glob(os.path.join(HERE, pat)):
        if os.path.basename(f).startswith("test_"):
            continue
        try:
            t = io.open(f, encoding="utf-8", errors="replace").read()
        except OSError:
            continue
        if "전략기획팀" in t or "기획팀 유경탁" in t or "유경탁 실장" in t:
            _stale.append(os.path.basename(f))
chk(not _stale, "★ 구 작성자 표기(전략기획팀·기획팀·실장)가 없다",
    "정본은 '㈜올림포스네트웍스 전략사업실 유경탁 파트장' 이다: " + ", ".join(_stale))

# ══════════════════════════════════════════════════════════════════
#  13라운드 — 첫 주의 실제 동선 (운영 DB 실측에서 나온 것들)
# ══════════════════════════════════════════════════════════════════
print("\n[8] 첫 주 동선 — 전화로 부를 수 있는가")

_nb = APP.find("def api_case_nearby")
#  ⚠ [라운드130] 고정 3400자 창이었다 — 함수 안에 주석 몇 줄만 늘어도(실제로
#    130라운드가 LIKE 이스케이프 주석을 넣자) 뒤쪽의 "phone"/"reach"/"called"
#    가 창 밖으로 밀려나 거짓 FAIL 이 났다. 다음 top-level def 까지(구조
#    기준)로 자른다 — 함수가 길어져도 안 깨진다.
_nb_end = APP.find("\ndef ", _nb + 1) if _nb > 0 else -1
if _nb_end < 0:
    _nb_end = _nb + 3400
nseg = strip_comments(APP[_nb:_nb_end], ("#",)) if _nb > 0 else ""
chk('"phone"' in nseg and '"reach"' in nseg and '"called"' in nseg,
    "★ 인근업체 목록이 전화번호·연락수단·기통화 여부를 준다",
    "협력업체 399곳 중 포털 로그인 1곳 · 휴대폰 68곳 — 330곳은 전화 말고 길이 없다. "
    "그런데 이 목록에 번호가 없어서 운영자가 업체마다 다른 메뉴에서 찾아야 했다")
chk("dispatch_calls" in nseg,
    "★ '이 사건으로 이미 부른 업체'를 표시한다(중복 전화 방지)")
_adm2 = strip_comments(ADM)
chk("nearPhone" in _adm2 and "tel:" in _adm2,
    "★ 화면이 번호를 눌러 바로 걸 수 있게 한다")
chk("data-act" not in _adm2[_adm2.find("const nearPhone"):_adm2.find("const nearPhone") + 700],
    "★ 전화 링크에 등록되지 않은 data-act 를 붙이지 않았다",
    "죽은 버튼 검사에 걸린다")

print("\n[9] 철칙 1·2 — 공개면이 '보험금' 을 줄인다고 말하지 않는다")
for _f in ("templates/landing.html", "docs/index.html"):
    _t = strip_comments(read(_f))
    chk("지급보험금 절감" not in _t,
        f"★ {os.path.basename(_f)} — '지급보험금 절감' 문구가 없다",
        "복구온이 줄이는 것은 복구 공사비다. 보험금을 줄인다고 말하면 "
        "보험금 산정에 관여하는 위치가 된다")

print("\n[10] 로그온 자동시작 배치가 살아 있는가")
_STARTUP = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows",
                        "Start Menu", "Programs", "Startup",
                        "복구온_외부접속_자동시작.bat")
if not os.path.exists(_STARTUP):
    chk(True, "로그온 자동시작 .bat 없음 — 이 PC 는 검사 대상 아님")
else:
    _b = io.open(_STARTUP, "rb").read()
    chk(_b.count(b"\r\n") == _b.count(b"\n"),
        "★ 자동시작 .bat 이 CRLF 다")
    chk(b"chcp 65001" in _b,
        "★ 자동시작 .bat 에 chcp 65001 이 있다",
        "UTF-8 인데 chcp 가 없으면 cmd 가 cp949 로 읽어 한글 경로가 깨진다 — "
        "조용히 아무 일도 안 하는 자동시작이 된다(실제로 그 상태였다)")

print("\n[11] 공개면 canonical — 없는 도메인을 정본이라고 말하지 않는다")
_land = read("templates/landing.html")
_docs = read("docs/index.html")
_bp = read("build_pages.py")
chk("bokguon.olymposnetworks.com" not in _land and "bokguon.olymposnetworks.com" not in _docs,
    "★ 템플릿·공개면에 등록되지 않은 도메인이 canonical 로 박혀 있지 않다",
    "그 도메인은 DNS 조회가 안 된다(2026-08-06 확인). robots.txt 는 Allow:/ 라 "
    "검색엔진이 '정본은 저 주소' 를 믿고 실제로 뜨는 페이지를 색인에서 내린다")
chk('rel="canonical"' not in _land,
    "★ 랜딩 템플릿이 canonical 을 직접 박지 않는다(빌드가 주입한다)")
chk("if SERVICE_URL:" in _bp and 'rel="canonical"' in _bp,
    "★ build_pages 가 실주소가 있을 때만 canonical 을 넣는다")
_srv = os.environ.get("BOKGUON_SERVICE_URL", "")
chk(('rel="canonical"' in _docs) == bool(_srv),
    f"★ 생성된 공개면의 canonical 유무가 SERVICE_URL({_srv or '미설정'}) 과 일치한다")


# ── 구문 ──────────────────────────────────────────────────────────
for f in ("app.py", "db.py", "manage.py", "photo_ai.py"):
    try:
        ast.parse(read(f))
        ok, why = True, ""
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
