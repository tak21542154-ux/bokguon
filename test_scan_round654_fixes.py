# -*- coding: utf-8 -*-
"""스캔 654라운드 회귀(직접조사, 하위위임 없음) — check_orphan_chars.py [2]번
조판 고아문자 후보 블록의 독립된 결함 2건.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 결함 A — orphan_candidates() 의 "1글자 꼬리 예외" 목록에 '↗'가 빠져 있었다.

  이 함수는 필수표시(*)·화살표 아이콘(→←↑↓)·가운뎃점(·)·대시(—-)처럼 라벨
  뒤에 붙는 1글자 "장식 꼬리"는 조판 흠이 아니라고 보고 후보에서 뺀다
  (round124 의 "자주 우는 늑대" 교훈 — 오탐이 쌓이면 진짜 결함이 묻힌다).
  그런데 실제로 이 저장소는 외부링크 라벨 끝에 '↗'(오른쪽위 화살표)도
  똑같은 방식으로 쓰는데, 대각선이라는 이유만으로 이 예외 목록에 빠져
  있었다.

  실측(고치기 전 소스로 재현, 이 파일 [2]절에서 직접 확인) —
    static/admin.js:1135          "발주처 연동 안내서 ↗"   (<a target="_blank">)
    static/admin.js:1311          "KISCON 조회 ↗"          (<a target="_blank">)
    templates/insurer_portal.html:446  "전산 연동 안내서 ↗"  (<a ...>)
  세 곳 다 외부링크 앵커의 장식 아이콘일 뿐 실제 조판 흠이 아닌데,
  '↗'만 예외 목록에 없어서 41개 후보 안에 노이즈로 섞여 있었다.

  고침(check_orphan_chars.py orphan_candidates(), 166행) — 예외 튜플에 '↗'를
  추가했다. 코드베이스에 실제로 안 쓰이는 다른 대각선 화살표(↘·↖·↙)는
  추측성 확장이라 넣지 않았다(ponytail — 근거 있는 것만).

■ 결함 B — [2]절 요약 수치 "조판 후보 N건"이 화면에 실제로 찍은 줄만 센다.

  형제 블록인 [1]절(깨진 문자)은 `total += len(hits)`로 **자르기 전** 전체
  개수를 먼저 더한 뒤에 화면은 `hits[:6]`만 보여준다 — 그래서 total 은
  항상 정확하다. 그런데 [2]절은 `for ln, s in cs[:8]: cand += 1`처럼 이미
  8개로 잘라 놓은 목록 **안에서** cand 를 늘려서, 한 파일이 8건을 넘기면
  넘는 만큼(안내 문구 "(외 N건)"으로 사람에게는 알려주면서) 맨 끝 합계
  "조판 후보 N건"에서는 조용히 빠졌다.

  실측 — 고치기 전: static/admin.js 는 실제로 16건인데 화면엔 8개 + "(외
  8건)"만 안내하고, 맨 끝 합계는 8개만 센 41건이었다(실제 전체는 49건).
  결함 A 를 고쳐 admin.js 에서 노이즈 2건이 빠지자(16→14), 8개 컷 밖에
  있던 후보 2개가 컷 **안**으로 밀려 들어와 합계가 41→40으로 "겨우 1"만
  줄어드는 것으로 겉보기에 확인됐다 — 이 우연한 산수만으로도 합계가
  화면 표시분에 종속돼 있다는 사실이 드러난다.

  다음 라운드가 "고아문자 후보가 몇 건 남았는가"를 가늠하는 근거로 이
  숫자를 그대로 쓰므로(round641 회귀가 이 값을 41로 못박아 검증할
  정도), 화면에 몇 줄을 찍든 합계는 항상 실제 전체 건수를 반영해야
  한다.

  고침(check_orphan_chars.py main(), [2]절) — [1]절과 같은 방식으로,
  `cand += len(cs)`를 `cs[:8]` 로 자르기 **전에** 한 번만 실행한다. 화면
  출력(cs[:8] 순회)에서는 더 이상 cand 를 건드리지 않는다. 고친 뒤 실제
  값은 46건(49 − 결함 A 가 없앤 노이즈 3건)이다.

■ 테스트 충돌 — test_scan_round641_fixes.py 의 [5]절이 "조판 후보 (\\d+)건"을
  41로 못박아 검증한다. round641 이 검증하려던 것은 "그 라운드의 CSS 선언
  추가가 candidate 개수를 흔들지 않는다"이지 41이라는 숫자 자체의 정당성이
  아니었다(41 자체가 이미 결함 B 때문에 진짜 개수가 아니었다). 그 assertion
  의 하드코딩된 41을, 이번 라운드가 두 결함을 고친 뒤의 올바른 값인 46으로
  갱신했다 — 검증 의도(그 CSS 변경은 candidate 탐지에 영향이 없다)는 그대로
  보존된다.

  회귀테스트(이 파일) —
  [1] 소스 확인 — '↗' 예외가 추가됐고, cand 가 cs[:8] 밖에서 원본 길이로
      늘어난다(안에서 1씩 늘리는 옛 패턴이 사라졌다).
  [2] 실행 — 합성 파일로 결함 A 대조: '↗'로 끝나는 외부링크 라벨은 이제
      후보에서 빠지고, 평범한 1글자 꼬리(예: "...확인이 먼저 필요했던 건")는
      여전히 후보로 잡힌다(과잉관용 아님 — round124 류 대조군).
  [3] 되돌림-증명 — 실제 파일은 안 건드리고, 지금 소스에서 두 고침만
      인메모리로 되돌린 사본을 exec() 해 독립된 네임스페이스에 올린 뒤:
        (a) 되돌린 orphan_candidates() 는 '↗' 라벨을 다시 후보로 오판한다.
        (b) 되돌린 main() 을 8건 초과 합성 디렉터리에 돌리면 합계가
            실제 개수보다 적게(8) 나온다.
      같은 입력을 지금(고친) 실제 모듈로 돌리면 둘 다 바르게 나온다.
  [4] 실행 — 실제 저장소를 서브프로세스로 스캔: 옛 '↗' 오탐 3곳이 더는 안
      보이고, 화면에 찍힌 줄 수 + 모든 "(외 N건)" 합계가 맨 끝 요약
      숫자와 정확히 일치한다(매직넘버 대신 자기정합성으로 검증 — 이후
      실제 콘텐츠가 바뀌어도 이 불변식은 계속 유효하다).
  [5] test_scan_round641_fixes.py 를 독립 실행해 갱신된 46 기준으로 통과함을
      재확인.

    python test_scan_round654_fixes.py
"""
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 66)
print("  스캔 654라운드 회귀 — check_orphan_chars.py 조판후보 오탐/오계수 2건")
print("=" * 66)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ──────────────────────────────────────────────────────────────
SRC_PATH = os.path.join(HERE, "check_orphan_chars.py")
SRC = io.open(SRC_PATH, encoding="utf-8").read()

NEW_TUPLE_LINE = ('if words and words[-1] in '
                   '("*", "✓", "→", "←", "↑", "↓", "↗", "·", "—", "-"):')
chk(NEW_TUPLE_LINE in SRC, "① orphan_candidates() 예외 튜플에 '↗'가 추가됐다", NEW_TUPLE_LINE)

chk("cand += len(cs)" in SRC,
    "② cand 를 cs[:8] 로 자르기 전 원본 길이(len(cs))로 센다")

_MAIN_BODY = SRC.split("def main():", 1)[1]
chk("cand += 1" not in _MAIN_BODY,
    "③ 화면에 찍은 줄만 세던 옛 'cand += 1' 패턴이 main() 안에 더는 없다")


# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 합성 파일로 결함 A 대조(오탐 소멸 + 진짜 후보는 여전히 잡힘)")
# ──────────────────────────────────────────────────────────────
import check_orphan_chars as COC  # noqa: E402

_scratch = tempfile.mkdtemp(prefix="round654_")

_link_html = os.path.join(_scratch, "link_sample.html")
io.open(_link_html, "w", encoding="utf-8").write(
    '<a class="btn g sm" href="/x" target="_blank" rel="noopener">발주처 연동 안내서 ↗</a>\n'
    '<a class="btn g sm" href="/y" target="_blank" rel="noopener">KISCON 조회 ↗</a>\n'
)
link_hits = COC.orphan_candidates(_link_html)
chk(link_hits == [], "④ '↗'로 끝나는 외부링크 라벨 2건 모두 더는 후보가 아니다", link_hits)

_real_html = os.path.join(_scratch, "real_sample.html")
io.open(_real_html, "w", encoding="utf-8").write(
    '<p>사진이 없어 현장 확인이 먼저 필요했던 건</p>\n'
)
real_hits = COC.orphan_candidates(_real_html)
chk(len(real_hits) == 1 and real_hits[0][1] == "사진이 없어 현장 확인이 먼저 필요했던 건",
    "⑤ 대조군 — 평범한 1글자 꼬리(실제 landing.html 문구)는 여전히 후보로 잡힌다"
    "(과잉관용으로 진짜 결함을 놓치지 않는다)", real_hits)


# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌림-증명 — 인메모리 사본만 되돌린다(실제 파일은 안 건드림)")
# ──────────────────────────────────────────────────────────────
OLD_TUPLE_LINE = ('if words and words[-1] in '
                   '("*", "✓", "→", "←", "↑", "↓", "·", "—", "-"):')
chk(OLD_TUPLE_LINE not in SRC, "⑥ (사전조건) 되돌릴 옛 튜플 문자열은 지금 실제 소스엔 없다")

_OLD_COUNT_FRAGMENT = (
    "            rel = os.path.relpath(f, HERE)\n"
    "            for ln, s in cs[:8]:\n"
    "                cand += 1\n"
    "                print(f\"  {rel}:{ln}  \\\"{s}\\\"\")\n"
)
_NEW_COUNT_FRAGMENT = (
    "            cand += len(cs)\n"
    "            rel = os.path.relpath(f, HERE)\n"
    "            for ln, s in cs[:8]:\n"
    "                print(f\"  {rel}:{ln}  \\\"{s}\\\"\")\n"
)
chk(_NEW_COUNT_FRAGMENT in SRC, "⑦ (사전조건) 고친 계수 코드 조각이 지금 소스에 정확히 있다")

REVERTED_SRC = SRC.replace(NEW_TUPLE_LINE, OLD_TUPLE_LINE, 1) \
                  .replace(_NEW_COUNT_FRAGMENT, _OLD_COUNT_FRAGMENT, 1)
chk(REVERTED_SRC != SRC and OLD_TUPLE_LINE in REVERTED_SRC and _OLD_COUNT_FRAGMENT in REVERTED_SRC,
    "⑧ 두 고침이 모두 되돌려진 사본이 만들어졌다(원본 파일은 그대로)")

ns_old = dict(vars(COC))          # 실제 모듈 네임스페이스의 얕은 사본(독립 네임스페이스)
ns_old["__file__"] = COC.__file__  # exec 중 HERE = ...(__file__) 계산용
exec(compile(REVERTED_SRC, "<round654_revert>", "exec"), ns_old)

chk(ns_old["orphan_candidates"](_link_html) != [],
    "⑨ 되돌린 옛 버전은 '↗' 라벨을 다시 후보로 오판한다(결함 A 재현)",
    ns_old["orphan_candidates"](_link_html))

# 8건 초과 합성 디렉터리 — 결함 B 재현용
_many_dir = tempfile.mkdtemp(prefix="round654_many_")
_many_html = os.path.join(_many_dir, "many.html")
io.open(_many_html, "w", encoding="utf-8").write(
    "\n".join(f"<p>합성 후보 문구 {i}번째 건</p>" for i in range(10)) + "\n"
)
_true_n = len(COC.orphan_candidates(_many_html))
chk(_true_n == 10, "⑩ (사전조건) 합성 파일이 실제로 10건의 후보를 담고 있다", _true_n)


def _run_main_against(ns, scratch_dir):
    old_here = ns["HERE"]
    ns["HERE"] = scratch_dir
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            ns["main"]()
    finally:
        ns["HERE"] = old_here
    out = buf.getvalue()
    m = re.search(r"조판 후보 (\d+)건", out)
    return (int(m.group(1)) if m else -1), out


old_reported, old_out = _run_main_against(ns_old, _many_dir)
chk(old_reported == 8,
    "⑪ 되돌린 옛 버전은 실제 10건 중 8건만 요약에 센다(결함 B 재현 — 화면표시 상한에 종속)",
    f"보고값 {old_reported} (실제 {_true_n})")

new_here = COC.HERE
try:
    COC.HERE = _many_dir
    _buf = io.StringIO()
    with contextlib.redirect_stdout(_buf):
        COC.main()
    _out = _buf.getvalue()
finally:
    COC.HERE = new_here
_m = re.search(r"조판 후보 (\d+)건", _out)
new_reported = int(_m.group(1)) if _m else -1
chk(new_reported == 10,
    "⑫ 고친 지금 버전은 10건 전부를 요약에 센다(결함 B 해소)",
    f"보고값 {new_reported} (실제 {_true_n})")


# ══════════════════════════════════════════════════════════════
print("\n[4] 실행 — 실제 저장소 서브프로세스 스캔(옛 오탐 소멸 + 요약 자기정합성)")
# ──────────────────────────────────────────────────────────────
env = dict(os.environ)
env["PYTHONIOENCODING"] = "utf-8"
r = subprocess.run([sys.executable, "-u", SRC_PATH],
                    cwd=HERE, capture_output=True, text=True, encoding="utf-8", env=env)
real_out = r.stdout or ""

chk("발주처 연동 안내서 ↗" not in real_out and "KISCON 조회 ↗" not in real_out
    and "전산 연동 안내서 ↗" not in real_out,
    "⑬ 실제 저장소 스캔에서 옛 '↗' 오탐 3곳이 더는 후보 목록에 안 보인다")

section2 = real_out.split("조판 고아문자 후보", 1)[-1]
shown_lines = len(re.findall(r'^  \S.*:\d+\s+"', section2, re.M))
hidden_sum = sum(int(x) for x in re.findall(r"\(외 (\d+)건\)", section2))
m_total = re.search(r"조판 후보 (\d+)건", real_out)
real_total = int(m_total.group(1)) if m_total else -1
chk(real_total == shown_lines + hidden_sum,
    "⑭ 요약 숫자 == 화면에 찍힌 줄 수 + 모든 '(외 N건)' 합 (자기정합성 — 매직넘버 아님)",
    f"요약 {real_total} vs 표시 {shown_lines} + 숨김 {hidden_sum}")
chk(real_total == 46,
    "⑮ 오늘 기준 실제 전체 후보 수는 46건이다(round641 당시 41 → 결함B로 드러난 실제 49 "
    "→ 결함A가 없앤 노이즈 3 = 46)", f"실제 {real_total}")


# ══════════════════════════════════════════════════════════════
print("\n[5] test_scan_round641_fixes.py 독립 재실행 — 갱신된 46 기준으로 통과")
# ──────────────────────────────────────────────────────────────
r641 = subprocess.run([sys.executable, "-u", os.path.join(HERE, "test_scan_round641_fixes.py")],
                       cwd=HERE, capture_output=True, text=True, encoding="utf-8", env=env)
chk(r641.returncode == 0,
    "⑯ test_scan_round641_fixes.py 가 41→46 갱신 뒤에도 여전히 전부 통과한다",
    (r641.stdout or "")[-400:] + (r641.stderr or "")[-400:])


print("\n" + "=" * 66)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}  {dt}")
print("=" * 66)
sys.exit(1 if FAIL else 0)
