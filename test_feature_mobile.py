# -*- coding: utf-8 -*-
"""폰에서 눌러야 할 것이 화면 안에 있는가 — 스타일시트를 **뜯어서** 본다.

  왜 이 파일이 생겼나 (2026-08-14 실측, 폰 375×812 협력사 포털) —
    ① 「입찰」 버튼 18개가 **전부 화면 밖** x=519 에 있었다. 표는 옆으로
       굴러가지만 굴러간다는 표시가 없어서, 협력사에게는 "입찰하러 들어왔는데
       입찰 버튼이 없다" 로 읽힌다. 하자 화면의 「완료 보고」·「귀책 이의」도 같았다.
    ② 접수번호 `26-80162` 가 `26-` / `8016` / `2` 세 줄로 쪼개졌다.
       전화로 불러 주는 번호라 잘못 읽기 쉽다.

  ⚠ **문자열이 파일에 있는지 세지 않는다.** 고치는 도중 주석을 한 번 더 닫아
    (`*/` 가 하나 남아) 규칙이 파서에 통째로 먹힌 적이 있다. 그때도 파일에는
    규칙 문자열이 멀쩡히 있었고, 브라우저에서만 안 먹었다.
    → 여기서는 주석을 걷어내고 규칙 블록으로 쪼갠 뒤, **셀렉터가 성한지**까지 본다.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSS = os.path.join(HERE, "static", "style.css")

PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def strip_comments(text):
    """주석을 걷어내고, **남은 `*/` 개수**도 함께 돌려준다.

      남은 `*/` 는 주석을 두 번 닫았다는 뜻이고, 그 뒤 규칙은 셀렉터가
      오염돼 브라우저가 통째로 버린다 — 이번 결함이 정확히 그것이었다."""
    out = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return out, out.count("*/") + out.count("/*")


def rules(css):
    """`셀렉터 { 선언 }` 목록. `@media` 같은 묶음은 한 겹 벗겨 안까지 들어간다."""
    got, i, n = [], 0, len(css)
    depth_sel = []
    buf = ""
    while i < n:
        c = css[i]
        if c == "{":
            sel = buf.strip()
            buf = ""
            #  중괄호를 짝 맞춰 블록 끝을 찾는다
            d, j = 1, i + 1
            while j < n and d:
                if css[j] == "{":
                    d += 1
                elif css[j] == "}":
                    d -= 1
                j += 1
            body = css[i + 1:j - 1]
            if sel.startswith("@") and "{" in body:
                got += [(sel + " " + s, b) for s, b in rules(body)]
            else:
                got.append((sel, body))
            i = j
            continue
        buf += c
        i += 1
    return got


print("═" * 72)
print("  폰에서 눌러야 할 것이 화면 안에 있는가 — style.css")
print("═" * 72)

raw = io.open(CSS, encoding="utf-8").read()
css, marks = strip_comments(raw)

#  ── ① 스타일시트 자체가 성한가 ──────────────────────────────
chk(marks == 0, "★★ 주석이 짝이 맞는다 (`*/` 가 남으면 뒤 규칙이 통째로 죽는다)",
    f"주석 표시 {marks}개 남음")
chk(css.count("{") == css.count("}"), "★ 중괄호 짝이 맞는다",
    f"{{ {css.count('{')} / }} {css.count('}')}")

R = rules(css)
chk(len(R) > 100, "규칙을 읽어 냈다", len(R))

#  셀렉터에 한글이 있으면 주석이 새어 들어온 것이다(주석은 이미 걷어 냈다)
dirty = [s for s, _ in R if re.search(r"[가-힣]", s)]
chk(not dirty, "★★ 셀렉터에 설명 문장이 섞여 있지 않다",
    (dirty[0][:70] + " …") if dirty else "")


def find(pred):
    return [(s, b) for s, b in R if pred(s)]


#  ── ② 누를 자리가 화면 안에 남는가 ──────────────────────────
sticky = find(lambda s: ":has(td:last-child .btn)" in s and "last-child" in s.split(":has")[-1])
chk(bool(sticky), "★★ 버튼이 든 마지막 열을 오른쪽에 붙이는 규칙이 있다")
if sticky:
    body = " ".join(b for _, b in sticky).replace(" ", "")
    chk("position:sticky" in body, "★★ 실제로 sticky 다", body[:70])
    chk("right:0" in body, "★★ 오른쪽에 붙는다", body[:70])
    chk(any("background" in b for _, b in sticky),
        "★ 배경이 있다 (없으면 밑에 깔린 글자가 비쳐 겹쳐 보인다)")
    #  좁은 화면에서만 — 넓은 화면 표까지 건드리면 안 된다
    chk(all("@media" in s for s, _ in sticky), "★★ 좁은 화면에서만 적용된다",
        [s[:40] for s, _ in sticky][:2])
    chk(any("max-width" in s for s, _ in sticky), "★ 폭 조건이 걸려 있다")

#  ── ③ 불러 주는 번호가 쪼개지지 않는가 ──────────────────────
em = find(lambda s: re.search(r"\btd\.em\b", s))
chk(bool(em), "★★ 번호 칸(.em) 규칙이 살아 있다")
if em:
    body = " ".join(b for _, b in em).replace(" ", "")
    chk("white-space:nowrap" in body, "★★ 번호를 끊지 않는다", body[:70])
    chk("overflow-wrap:normal" in body, "★ 아무 데서나 끊는 설정을 되돌린다", body[:70])
    #  순서가 중요하다 — 일반 규칙(anywhere)보다 **뒤에** 와야 이긴다
    gen = [i for i, (s, _) in enumerate(R) if ".tbl td," in s.replace(" ", ",")
           or re.search(r"\.tbl\s+td\s*,", s)]
    emi = [i for i, (s, _) in enumerate(R) if re.search(r"\btd\.em\b", s)]
    chk(not gen or not emi or max(emi) > min(gen),
        "★★ 일반 규칙보다 뒤에 온다 (앞에 오면 덮인다)", f"일반 {gen[:2]} · 번호 {emi[:2]}")

#  길어서 진짜 문제인 값들은 **그대로 끊기게** 둔다 — 과잉 적용 방지
gen_body = " ".join(b for s, b in R if ".kv .v" in s or ".msub" in s).replace(" ", "")
chk("overflow-wrap:anywhere" in gen_body,
    "★ 계좌번호·이메일 칸은 그대로 끊긴다 (번호 칸만 예외로 뒀다)")

#  ── ④ 이미 있던 손가락 크기 보정이 살아 있는가 ──────────────
btn = find(lambda s: re.search(r"(^|,|\s)\.btn(\s*,|\s*$)", s) and "@media" in s)
chk(bool(btn), "★ 폰에서 버튼 최소 높이 규칙이 있다")
if btn:
    chk(any("min-height:44px" in b.replace(" ", "") for _, b in btn),
        "★★ 44px 이상 (iOS 권장 손가락 크기)")

print()
print("═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
for nm, dt in FAIL:
    print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
