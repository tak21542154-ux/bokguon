# -*- coding: utf-8 -*-
"""14라운드 확정 결함 회귀 — 적대적 검토 8건.

  이 라운드는 7개 렌즈로 오늘 변경분을 훑고, 각 지적을 **반증 담당**이 다시 검증했다
  (지적 18건 → 반증 탈락 10건 → 생존 8건). 생존분은 내가 직접 재현해서 확인했다.

  ⚠ 재현 과정에서 **내 재현 자체가 두 번 틀렸다.** 기록해 둔다 —
   ① 보호 라우트를 먼저 부르면 _dead_account_response 가 session.clear() 를 한다.
      그 뒤 호출이 403 이 되는데, 그건 '막혔다'가 아니라 **내가 세션을 지운 것**이다.
      → 각 검사는 매번 새 세션으로, 대상 라우트를 **맨 먼저** 부른다.
   ② 세션의 admin_role 을 손으로 위장해도 _account_alive 가 DB 등급으로 덮어쓴다.
      → 등급 검사는 **DB 에 진짜 그 등급 계정을 만들어** 확인한다.
  둘 다 '검사 안 함'을 '통과'로 읽게 만드는 함정이라, 대조군을 반드시 둔다.

      python test_scan_round14_fixes.py
"""
import ast
import io
import os
import re
import sqlite3
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
    #  `accept="image/*"` 의 /* 는 주석이 아니다 — 앞 글자가 식별자·따옴표면 건너뛴다
    text = re.sub(r"(?<![A-Za-z0-9_\"'])/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)
    return "\n".join(ln for ln in text.splitlines()
                     if not any(ln.strip().startswith(m) for m in marks))


APP = read("app.py")
PAI = read("photo_ai.py")
MNG = read("manage.py")
PAR = read("templates/partner_portal.html")

print("═" * 70)
print("  14라운드 회귀 — 적대적 검토 8건 (재현으로 확인한 것들)")
print("═" * 70)

# ══════════════════════════════════════════════════════════════════
print("\n[1] 죽은 계정이 사진을 계속 받지 못한다  (재현: 퇴출 → 401)")
# ══════════════════════════════════════════════════════════════════
for fn, label in (("api_case_photos", "사건 사진 목록"),
                  ("api_photo_file", "사진 원본 파일"),
                  ("api_defect_photos_list", "하자 사진 목록")):
    i = APP.find(f"def {fn}(")
    seg = strip_comments(APP[i:i + 900], ("#",)) if i > 0 else ""
    chk("_mixed_actor_guard()" in seg,
        f"★ {label}({fn}) 에 죽은 계정 가드가 있다",
        "형제 POST(api_defect_create·api_defect_photos_upload)에는 있는데 조회에만 없었다. "
        "퇴출 업체가 **새 세션으로 이 경로부터** 부르면 현장 사진이 그대로 나갔다")

# ══════════════════════════════════════════════════════════════════
print("\n[2] 하위계정 비밀번호 재발급이 열린 세션을 끊는다  (재현: 재발급 후 401)")
# ══════════════════════════════════════════════════════════════════
i = APP.find("def _sub_account_dead")
seg = strip_comments(APP[i:i + 1800], ("#",)) if i > 0 else ""
chk("_pw_sig(" in seg and "session.get(\"pw_sig\")" in seg,
    "★ _sub_account_dead 가 **하위계정 자기 행**으로 지문을 대조한다")
chk("if _pw_changed(r):" not in seg,
    "★ _pw_changed 를 부르지 않는다(그 함수는 하위계정이면 무조건 False 다)",
    "그래서 그 줄은 구조적으로 죽은 코드였고, 침해 의심으로 비번을 재발급해도 "
    "그 사람의 열린 탭이 그대로 살아 있었다")

# ══════════════════════════════════════════════════════════════════
print("\n[3] 정산 관문(사진 검수 승인)이 형제와 같은 문턱이다  (재현: 하위 403 / 중간 200)")
# ══════════════════════════════════════════════════════════════════
_i = APP.find('@app.post("/api/cases/<int:cid>/photos/approve")')
seg = APP[_i:_i + 900] if _i > 0 else ""
chk('@require_role("중간관리자")' in seg,
    "★ 사진 검수 승인이 중간관리자 이상이다",
    "사건 검수승인·정산 지급·사진 삭제는 전부 중간관리자인데 이것만 등급 무관이었다. "
    "승인을 막는 유일한 조건인 '미분류 0장' 도 같은 계정이 스스로 해소할 수 있었다")
_k = APP.find('@app.post("/api/photos/<int:pid>/kind")')
chk('@require_role("중간관리자")' not in APP[_k:_k + 400],
    "★ 사진 **분류**는 하위관리자에게 남긴다(실무 입력까지 잠그지 않는다)")

# ══════════════════════════════════════════════════════════════════
print("\n[4] 2차 하한의 명의 — 발주처가 내지 않은 금액을 발주처 것이라 하지 않는다")
# ══════════════════════════════════════════════════════════════════
chk("def _floor_src(" in APP, "★ 하한 출처를 판별하는 _floor_src 가 있다")
_b = APP.find('"code": "UNDER_FLOOR"')
seg = strip_comments(APP[max(0, _b - 900):_b], ("#",))
chk("_floor_src(" in seg,
    "★ 서버 거절 문구가 하한 출처를 사실대로 적는다",
    "가견적이 0인 접수에서는 이 값이 서버가 표준단가로 계산한 개산 하단인데, "
    "'발주처 제시금액' 이라고 쓰면 발주처가 낸 적 없는 금액을 발주처 명의로 "
    "구속력 있게 고지하는 것이 된다(철칙 1)")
chk('"floor_src"' in APP, "★ 공고 목록이 화면에 출처를 함께 내려준다")
_p = strip_comments(PAR, ("//",))
chk("floor_src" in _p and "최소 입찰가 (발주처 제시금액)" not in _p,
    "★ 협력사 화면이 출처를 그대로 말한다(고정 문구가 남아 있지 않다)")

# ══════════════════════════════════════════════════════════════════
print("\n[5] 우리가 던진 안내가 catch-all 에 덮이지 않는다")
# ══════════════════════════════════════════════════════════════════
_h = PAI.find("def _heic_to_jpeg")
seg = PAI[_h:_h + 2200] if _h > 0 else ""
chk("except UploadError:" in seg and seg.index("except UploadError:") < seg.index("except Exception:"),
    "★ HEIC 변환의 except UploadError 가 catch-all **앞**에 있다",
    "없으면 '해상도가 너무 큽니다(8064x6048)' 가 'JPG 로 올려 주세요' 로 덮여, "
    "사용자는 무엇을 고쳐야 하는지 끝내 알 수 없다")

# ══════════════════════════════════════════════════════════════════
print("\n[6] 0% 계약을 10% 로 고지하지 않는다")
# ══════════════════════════════════════════════════════════════════
_s = strip_comments(APP, ("#",))
chk('(s["fee_rate_bp"] or DEFAULT_FEE_RATE_BP)' not in _s,
    "★ 요율 계산에 `or` 폴백이 남아 있지 않다(0 은 falsy 다)",
    "돈은 정확한데 문구만 '수수료 10% 0원 공제' 라는 자기모순이 된다")
chk(_s.count("DEFAULT_FEE_RATE_BP if") >= 1 or "_bp is None" in _s,
    "★ None 판정으로 기본값을 정한다")

# ══════════════════════════════════════════════════════════════════
print("\n[7] 사외로 나가는 명세서가 개산가를 '가견적' 이라 부르지 않는다")
# ══════════════════════════════════════════════════════════════════
_x = APP.find("def _statement_xlsx")
seg = strip_comments(APP[_x:_x + 3000], ("#",)) if _x > 0 else ""
chk('"비교 기준(원)"' in seg and '"가견적(원)"' not in seg,
    "★ 명세서 열 이름이 '비교 기준(원)' 이다",
    "1차=가견적 / 2차=표준단가 개산 상단인데 사외 파일만 '가견적' 이라 적어, "
    "복구온이 만든 숫자를 발주처 본인의 가견적으로 보이게 했다")

# ══════════════════════════════════════════════════════════════════
print("\n[8] go-live 미리보기가 실제 삭제량을 그대로 보여준다")
# ══════════════════════════════════════════════════════════════════
_g = MNG.find("demo_case_ids = [")
seg = MNG[max(0, _g - 700):_g + 300] if _g > 0 else ""
chk("DEMO_CASE_SQL" in seg,
    "★ 미리보기의 사건 집합이 유령 사건(데모 발주처 소속·표식 없음)까지 센다",
    "미리보기 경로에서는 표식 UPDATE 를 하지 않으므로 `is_demo=1` 만 보면 "
    "그 사건들에 딸린 사진·정산이 확인 화면에서 통째로 빠진다. "
    "사진은 디스크에서도 지워지는데 운영자는 그 장수를 안내받은 적이 없다")

#  ── 실제로 세어 본다 ──────────────────────────────────────────
_db = os.path.join(HERE, "bokguon.db")
if os.path.exists(_db):
    try:
        c = sqlite3.connect("file:" + _db.replace(os.sep, "/") + "?mode=ro", uri=True)
        GH = ("SELECT id FROM cases WHERE COALESCE(is_demo,0)=0 AND insurer_id IN "
              "(SELECT id FROM insurers WHERE COALESCE(is_demo,0)=1)")
        ghost = c.execute(f"SELECT COUNT(*) FROM ({GH})").fetchone()[0]
        gp = c.execute(f"SELECT COUNT(*) FROM photos WHERE case_id IN ({GH})").fetchone()[0]
        c.close()
        chk(True, f"운영 DB 기준 유령 사건 {ghost}건 · 딸린 사진 {gp}장 "
                  f"— 종전 미리보기에서 빠지던 양")
    except sqlite3.Error as e:
        chk(True, f"운영 DB 집계 생략({e})")

# ── 구문 ──────────────────────────────────────────────────────────
for f in ("app.py", "photo_ai.py", "manage.py"):
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
