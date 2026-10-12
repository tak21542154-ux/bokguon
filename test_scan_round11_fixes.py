# -*- coding: utf-8 -*-
"""11라운드 확정 결함 회귀 — **출시 차단 8건**이 되돌아오지 않게 못 박는다.

  이 라운드는 '열어도 되는가' 를 판정하려고 돌렸고, 법률 철칙 위반 4건이 나왔다.
  전부 "화면 한 줄"·"컬럼 하나" 라서 다음 수정에서 조용히 되살아나기 쉽다.

      python test_scan_round11_fixes.py
"""
import ast
import io
import os
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


def strip_comments(text, marks=("#", "//")):
    """주석을 걷어낸다 — 설명문을 코드로 오독하지 않기 위해.

      ⚠ **블록 주석까지 지워야 한다.** 오늘만 세 번 당했다:
        "🏆 배너를 없앴다" 라고 적은 `${/* … */}` 주석이 '🏆 가 있다' 로 잡히고,
        "list(im.getdata()) 를 없앴다" 라는 `#` 주석이 '그 코드가 있다' 로 잡혔다.
        고쳐 놓고도 실패가 뜨면, 다음 사람은 테스트가 아니라 코드를 의심한다.
    """
    import re as _re
    #  ⚠ **`accept="image/*"` 의 `/*` 는 주석이 아니다.** 그냥 짝을 맞추면
    #    저 아래 진짜 `*/` 까지 5만 자가 '주석' 으로 지워지고, 그 구간의 코드는
    #    `X not in 코드` 검사를 전부 통과한다(거짓 초록). 실제로 그랬다.
    #    앞 글자가 식별자·따옴표면 주석 시작으로 보지 않는다.
    text = _re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", text, flags=_re.S)
    text = _re.sub(r"<!--.*?-->", " ", text, flags=_re.S)     # <!-- … -->
    return "\n".join(ln for ln in text.splitlines()
                     if not any(ln.strip().startswith(m) for m in marks))


APP = read("app.py")
TREE = ast.parse(APP)
INS = read("templates/insurer_portal.html")
PAR = read("templates/partner_portal.html")

print("═" * 70)
print("  11라운드 회귀 — 법률 철칙 · DoS · 무한루프 (출시 차단 항목)")
print("═" * 70)

# ══════════════════════════════════════════════════════════════════
print("\n[1] 철칙 5·7 — 복구온이 특정 업체를 지목하지 않는다")
# ══════════════════════════════════════════════════════════════════
_i = APP.find("def _bid_scores")
seg = strip_comments(APP[_i:_i + 4000], ("#",)) if _i > 0 else ""
chk('out[0]["recommended"] = True' not in seg,
    "★ 1등에 'recommended' 를 붙이지 않는다",
    "복구온이 승자를 지목한 화면에서 발주처가 승인 버튼을 누르게 된다")
chk('out.sort(key=lambda x: (-x["score"]' not in seg,
    "★ 점수 내림차순으로 재정렬하지 않는다")
chk('out.sort(key=lambda x: (x.get("amount") or 0' in seg,
    "★ 가격순으로 준다(역경매의 자연 순서)")

_ins = strip_comments(INS)
chk("🏆" not in _ins, "★ 발주처 화면에 🏆 추천 배너가 없다")
chk("b.recommended" not in _ins, "★ '추천' 배지가 없다")
chk("가격순" in _ins, "  대신 '가격순' 이라고 말한다")

# ══════════════════════════════════════════════════════════════════
print("\n[2] 철칙 3 — 근거 없는 평점을 만들지도, 쓰지도 않는다")
# ══════════════════════════════════════════════════════════════════
DBS = strip_comments(read("db.py"), ("#",))
chk("rnd.uniform(3.8, 4.9)" not in DBS,
    "★ 시드가 평점 난수를 만들지 않는다",
    "실명 리서치 협력사 399곳에 난수 평점이 붙어 발주처에 제시됐다")
chk("rnd.randint(0, 80)" not in DBS, "★ 실적(완료 건수) 난수도 만들지 않는다")

_i = APP.find("def api_recount_partner_stats")
seg = APP[_i:_i + 2000] if _i > 0 else ""
#  ⚠ 라운드64: 여기서 rating 을 SQL로 직접 다시 계산했었다(AVG(해피콜)만 통째로
#    덮어쓰기) — 그게 정확히 이 라운드가 고친 옛 사고(해피콜 AVG 덮어쓰기가
#    하자 차감을 지운다)의 절반이었다. 이제는 캐논 함수(refresh_partner_rating)를
#    불러 하자 차감까지 포함해 실측으로 되돌린다 — 검증 대상 메커니즘만 바뀌고
#    "재계산이 rating 도 실측으로 되돌린다"는 원래 취지는 그대로다.
chk("refresh_partner_rating(conn, _pid)" in seg,
    "★ 실적 재계산이 평점도 실측(해피콜-하자차감)으로 되돌린다",
    "종전에는 jobs_done·win_rate 만 고치고 정작 점수에 들어가는 rating 은 뒀다")
chk("해피콜이 있는 업체만" in INS, "  화면이 평점의 근거를 밝힌다")

# ══════════════════════════════════════════════════════════════════
print("\n[3] 철칙 1 — 복구온이 금액·낙찰을 단독으로 정하지 않는다")
# ══════════════════════════════════════════════════════════════════
_i = APP.find("def api_co_decision")
seg = APP[_i:_i + 3000] if _i > 0 else ""
chk("INSURER_ACK_REQUIRED" in seg,
    "★ 변경견적 증액은 발주처가 확인한 뒤에만 확정된다",
    "발주처가 '부동의' 를 눌러도 그대로 계약금액이 됐다")
#  ⚠ 라운드55: 금액 대조 로직이 api_co_decision 안에 직접 있었는데, 형제(전체재경매
#    마감)에는 없어서 발주처가 부동의한 금액이 다른 경로로는 그대로 확정됐다
#    (withdraw-offer 가 확인을 안 지워서 새 라운드에 같은 금액이 재현되면 통과).
#    판단을 공유 함수 _insurer_ack_ok 하나로 모았다 — 여기서는 "그 함수를 부르는가"
#    까지만 보고, "그 함수가 금액까지 정확히 대조하는가"는 함수 정의 자체에서 본다.
chk('_insurer_ack_ok(co, co["combined_amount"])' in seg,
    "★ 공유 판단 함수(_insurer_ack_ok)를 부른다(따로 또 구현 안 함)")
_i_fn = APP.find("def _insurer_ack_ok(co, amount):")
_fn_seg = APP[_i_fn:_i_fn + 700] if _i_fn > 0 else ""
chk(bool(_fn_seg), "★ 공유 판단 함수 정의를 찾았다")
chk('int(co.get("insurer_ack_amount") or 0) == int(amount or 0)' in _fn_seg,
    "★ 확인한 **금액**까지 대조한다(금액이 바뀌면 확인은 무효)")
chk('(co.get("insurer_ack") or "").strip() == "확인"' in _fn_seg,
    "★★ 금액이 같아도 '확인' 상태 자체가 아니면(부동의·미회신) 막는다 "
    "(라운드55 핵심 결함 — 예전엔 이 검사가 close-full 쪽엔 아예 없었다)")

_i = APP.find("def api_case_award")
seg = APP[_i:_i + 2500] if _i > 0 else ""
chk("INSTRUCTION_REQUIRED" in seg,
    "★ 운영자 대행 낙찰에는 발주처 지시 근거가 필수다",
    "보험사 조작 0회로 낙찰이 확정됐다")
#  ⚠⚠ [라운드608] round601~ 형제결함군(raw (v or "").strip()는 JSON 비문자열에
#    AttributeError로 500) 처방으로 _s()가 덧씌워졌다 — 리터럴만 갱신, 검증
#    취지(근거를 실제로 받는가)는 그대로.
chk('_inst = _s(d.get("insurer_instruction"), 300)' in seg,
    "  근거를 실제로 받는다")

# ══════════════════════════════════════════════════════════════════
print("\n[4] 철칙 2·4 — 보험의 언어 · 낙찰가 역산")
# ══════════════════════════════════════════════════════════════════
chk("손해사정사 출동을 기다릴 필요" not in INS,
    "★ 발주처 화면이 손해사정 절차와 비교하지 않는다")

_i = APP.find("def api_reauctions")
seg = APP[_i:_i + 4000] if _i > 0 else ""
chk('r.pop("requested_amount", None)' in seg,
    "★ 전체재경매 응답에서 추가예상액도 뺀다",
    "상한 − 추가예상액 = 원 낙찰가 가 그대로 복원됐다")

#  ── 실제 계산: 폴백 상한으로도 원 낙찰가가 안 나오는가 ──────────
def load_func(name):
    consts = {}
    for nd in TREE.body:
        if isinstance(nd, ast.Assign) and len(nd.targets) == 1 \
                and isinstance(nd.targets[0], ast.Name) and isinstance(nd.value, ast.Constant):
            consts[nd.targets[0].id] = nd.value.value
    for nd in ast.walk(TREE):
        if isinstance(nd, ast.FunctionDef) and nd.name == name:
            ns = dict(consts)
            exec(compile(ast.Module(body=[nd], type_ignores=[]), "<x>", "exec"), ns)
            return ns[name]
    return None


cap = load_func("_reauction_cap")
if cap:
    bad = []
    for inc, req in ((800_000, 300_000), (60_000, 30_000), (5_000_000, 1_000_000)):
        co = {"requested_amount": req, "combined_amount": None, "incumbent_amount": inc}
        if cap(co, "전체재경매") - req == inc:
            bad.append((inc, req))
    chk(not bad, "★ 폴백 상한 − 추가예상액 ≠ 원 낙찰가 (3조합 실계산)", str(bad))

# ══════════════════════════════════════════════════════════════════
print("\n[5] DoS — 사진 압축폭탄")
# ══════════════════════════════════════════════════════════════════
PA = strip_comments(read("photo_ai.py"), ("#",))
chk("MAX_PIXELS" in PA and "Image.MAX_IMAGE_PIXELS = MAX_PIXELS" in PA,
    "★ 픽셀 상한을 건다")
chk("list(im.getdata())" not in PA,
    "★ 픽셀을 파이썬 객체로 펼치지 않는다(그 한 줄이 6GB 를 잡았다)")
try:
    sys.path.insert(0, HERE)
    import photo_ai as _pa
    from PIL import Image as _Im
    _b = io.BytesIO()
    _Im.new("RGB", (9000, 9000), (7, 7, 7)).save(_b, format="PNG", optimize=True)
    _out, _err = _pa._strip_exif(_b.getvalue(), "png")
    chk(bool(_err), "★ 9000×9000 폭탄 PNG(0.24MB)를 실제로 거부한다", str(_err)[:60])
    _b2 = io.BytesIO()
    _Im.new("RGB", (1600, 1200), (200, 30, 30)).save(_b2, format="JPEG", quality=95)
    _o2, _e2 = _pa._strip_exif(_b2.getvalue(), "jpg")
    chk(_e2 is None and len(_o2) > 1000,
        "★ 정상 사진은 그대로 처리된다(과잉 차단 아님)", f"{_e2} {len(_o2)}B")
except Exception as e:
    chk(False, "★ 압축폭탄 실검증", f"{type(e).__name__}: {e}")

# ══════════════════════════════════════════════════════════════════
print("\n[6] 현장 — 무한 재업로드 루프")
# ══════════════════════════════════════════════════════════════════
chk("올릴 수 없어 대기 목록에서 제외했습니다" in PAR,
    "★ 서버가 영구 거절(4xx)한 사진은 큐에서 뺀다",
    "다시 보내도 같은 답인데 2초마다 영원히 재전송했다")
chk("if(UPQ_AUTO_BUSY) return;" in PAR,
    "★ 자동 재전송에서는 화면을 다시 그리지 않는다(재예약 고리 절단)")
#  ⚠ 11라운드에는 **메시지 문자열**로 판정했는데, 던지는 오류에 HTTP 상태가 없어
#    401·403·429·5xx 까지 '영구 거절'로 읽혀 현장 사진이 지워졌다(12라운드).
#    지금은 상태 코드로 판정한다 — 지켜야 할 성질은 같다: **애매하면 보존.**
chk("let httpStatus = 0;" in PAR and "RETRYABLE = [401, 403, 408, 409, 413, 419, 423, 425, 429]" in PAR,
    "★ 파기 판정을 **HTTP 상태**로 한다(문자열이 아니라)",
    "다시 못 찍는 현장 사진이 큐의 마지막 보루다")
chk("httpStatus >= 400 && httpStatus < 500" in PAR,
    "  5xx·상태 미상(네트워크 단절)은 무조건 보존")

# ══════════════════════════════════════════════════════════════════
print("\n[7] 출시 정리 — 데모 판정 · 고아 행")
# ══════════════════════════════════════════════════════════════════
MNG = read("manage.py")
chk("DEMO_CASE_SQL" in MNG,
    "★ 데모 판정을 한 술어로 모은다(점검·미리보기·실행이 같은 기준)")
chk("insurer_id IN (SELECT id FROM insurers WHERE COALESCE(is_demo,0)=1)" in MNG,
    "★ 발주처가 데모면 그 사건도 데모다",
    "표식 없는 검증 사건 81건(정산 1억 2,950만원)이 go-live 를 통과했다")
chk('if t == "cases":' in MNG and "DEMO_CASE_SQL" in MNG,
    "★ 미리보기가 실행과 같은 숫자를 보여 준다",
    "'cases 15건 삭제' 라고 하고 실제로는 96건을 지웠다")
chk("def cmd_prune_orphans" in MNG and '"prune-orphans"' in MNG,
    "★ 고아 행을 치울 명령이 있다(경고만 하고 방법이 없었다)")
chk("없어진 {_label}" in MNG, "★ 부모 고아(없어진 발주처·업체)도 본다")

# ══════════════════════════════════════════════════════════════════
print("\n[8] 첫 주 — 조용한 실패를 소리 나게")
# ══════════════════════════════════════════════════════════════════
#   공고 알림은 포털 알림함('푸시')으로만 간다. 팝빌 미연동이면 문자가 안 나가므로
#   협력사가 앱을 열지 않으면 아무도 모른다 — 그런데 무입찰은 **마감 뒤에야** 알려졌다.
chk("def sweep_no_bid_alert" in APP,
    "★ 마감 **전에** 무입찰을 알리는 스윕이 있다",
    "종전에는 '무입찰 유찰' 로 끝난 뒤에야 알았다(손 쓸 시간 0)")
_i = APP.find("def sweep_no_bid_alert")
seg = APP[_i:_i + 4000] if _i > 0 else ""
chk("nn.ntype='무입찰경보' AND nn.case_id = c.id" in seg,
    "★ 같은 공고에 한 번만 보낸다(5분마다 쌓이면 아무도 안 본다)")
chk("COALESCE(login_id,'') <> ''" in seg,
    "★ **참여할 수 있는 업체 수**를 함께 말한다",
    "'계정이 없다' 와 '안 본다' 는 할 일이 완전히 다르다")
chk("partner_accounts.py" in seg, "  계정이 0곳이면 발급 명령을 알려 준다")
chk("sweep_no_bid_alert(conn)" in APP and "A.sweep_no_bid_alert(conn)" in MNG,
    "★ 콘솔 스윕과 크론 스윕 **양쪽**에 걸려 있다",
    "한쪽만 걸면 크론이 없는 환경에서 안 돈다")

# ══════════════════════════════════════════════════════════════════
print("\n[9] 12라운드 — 형제 경로 · 대외 문서 · 큐")
# ══════════════════════════════════════════════════════════════════
_i = APP.find("def api_co_close_full")
#  ⚠ 창을 넓게 잡는다 — 경계에 걸리면 코드가 맞는데도 실패로 보인다.
seg = APP[_i:_i + 12000] if _i > 0 else ""
chk("INSURER_ACK_REQUIRED" in seg,
    "★ 전체재경매 낙찰도 발주처 확인·지시를 요구한다",
    "co_decision 에만 걸고 거절 가지(전체재경매)는 그대로 열려 있었다")
#  ⚠⚠ [라운드113] 여기서 옛날엔 insurer_ack_amount 만 낙찰가에 맞춰 찍었다 —
#    그러면 확인 여부(insurer_ack)·서명자·시각은 그대로 남아 **확인한 적
#    없는 금액에 '확인' 배지**가 붙었다(이 체크 이름이 바로 그 증상을
#    묘사한다). 실제 고침은 그 금액에 대한 진짜 확인일 때만 그대로 두고,
#    아니면(대행 통과) 없던 확인을 지어내지 않도록 전부 비우는 것이다.
chk("insurer_ack=NULL, insurer_ack_amount=NULL" in seg,
    "★ 확인한 적 없는 금액에는 '확인' 배지를 지어내지 않는다"
    "(옛 수정은 금액만 맞춰 배지가 그대로 살아났다 — 113라운드가 바로잡음)")
chk(APP.count('"발주처 낙찰 지시(대행)"') >= 2,
    "★ 대행 지시 근거를 실제로 기록한다",
    "받기만 하고 버려서, 관문이 생기기 전과 법적 위치가 같았다")

_i = APP.find("def api_case_open_auction")
seg = APP[_i:_i + 9000] if _i > 0 else ""
_u, _r = seg.find("SET status=?, decided_at"), seg.find("rnd = 2 if fa else 1")
chk(0 < _u < _r,
    "★ 2차 경매 회차 판정이 '검토중→결렬' 처리 **뒤**에 있다",
    "앞에 있으면 상한이라 공지하고 하한으로 받는다(철칙 6)")

_L = read("legal_docs.py")
for _bad, _lb in ((" 낙찰 업체 추천,", "처리목적"),
                  ("추천 순위 산정", "처리방침 제9조"),
                  ("낙찰 후보를 추천하며", "약관 제3조4항"),
                  ("낙찰 추천 순위에 반영", "약관 제4조4항")):
    chk(_bad not in _L, f"★ 대외 문서에 '추천' 약속이 없다 — {_lb}",
        "코드에서 지운 것을 문서가 서면으로 자인하고 있었다(철칙 5·7)")
chk("낙찰 업체를 추천하거나 입찰을 순위로 매기지 않습니다" in _L,
    "  대신 '추천하지 않는다' 를 명시한다")
chk("낙찰 업체를 추천하면" not in read("templates/landing.html"),
    "★ 공개 랜딩도 '추천' 광고를 하지 않는다")

chk("FK_CHILD_TABLES" in MNG,
    "★ 사진·하자로만 닿는 표의 고아도 본다(case_id 기준 사각지대)")
chk("협력사 평판 초기화" in MNG,
    "★ go-live 가 해피콜·평점·실적을 0 에서 시작시킨다",
    "지워진 데모 사건의 만족도 5.0 이 실운영 낙찰 점수의 근거가 됐다")
#  ⚠⚠ [라운드209] 고정폭(9000자) 스캔은 cmd_go_live() 가 커지면(라운드209가
#    하위계정 정리를 추가하며 실제로 그랬다) 뒤쪽 텍스트가 창 밖으로 밀려나
#    거짓 실패를 낸다(9·10라운드가 이미 187라운드에서 겪은 함정과 같다) —
#    다음 함수 정의 직전까지로 범위를 잡아 함수가 커져도 안전하게 한다.
_i = MNG.find("def cmd_go_live")
_i_end = MNG.find("\ndef ", _i + 1) if _i > 0 else -1
seg = MNG[_i:_i_end] if _i > 0 and _i_end > 0 else ""
_dp, _ph = seg.find("DELETE FROM defect_photos"), seg.find("DELETE FROM photos WHERE case_id")
chk(0 < _dp < _ph,
    "★ defect_photos 를 photos 보다 **먼저** 지운다 (세 라운드 연속 무효였다)",
    "photos 가 먼저 사라지면 하위질의가 빈 집합이라 항상 0행 — 예외도 안 난다")

print("\n" + "═" * 70)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("═" * 70)
sys.exit(1 if FAIL else 0)
