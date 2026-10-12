# -*- coding: utf-8 -*-
"""앱(홈화면 설치) 껍데기 회귀 검사.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

두 가지가 조용히 깨지기 쉬워서 검사로 묶어 둔다.
  ① viewport-fit=cover 가 없으면 env(safe-area-inset-*) 가 전부 0 이라
     노치·홈바 대응 CSS 가 통째로 무효가 된다. 새 화면을 만들 때 빠뜨리기 쉽다.
  ② 빌드 해시가 화면 파일을 다 훑지 않으면, 그 파일만 고쳤을 때 서비스워커가
     옛 캐시를 계속 내준다 — **설치된 앱은 그 수정을 영영 못 받는다.**
     (실제로 style.css 가 목록에서 빠져 있어 CSS 수정이 앱에 안 내려갔다)
"""
import io
import os
import sys
import glob

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
os.environ.setdefault("BOKGUON_LOG_FILE",
                      os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "logs", "test.log"))
HERE = os.path.dirname(os.path.abspath(__file__))
OK = FAIL = 0


def chk(cond, label, detail=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  [OK]   {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}   {detail}")


def read(p):
    return io.open(os.path.join(HERE, p), encoding="utf-8").read()


def main():
    print("=" * 70)
    print("  앱 껍데기 회귀 검사")
    print("=" * 70)

    # ── ① 모든 화면에 viewport-fit=cover ──
    print("\n[1] viewport-fit=cover")
    missing = []
    for f in sorted(glob.glob(os.path.join(HERE, "templates", "*.html"))):
        s = io.open(f, encoding="utf-8").read()
        if 'name="viewport"' in s and "viewport-fit=cover" not in s:
            missing.append(os.path.basename(f))
    chk(not missing, "★ viewport 메타가 있는 화면은 모두 viewport-fit=cover",
        f"빠진 화면: {missing}")

    # ── ② 안전영역 CSS 가 살아 있는가 ──
    print("\n[2] 노치·홈바 대응 CSS")
    css = read("static/style.css")
    for sel, why in (("env(safe-area-inset-top)", "상단바가 상태바 밑으로 들어간다"),
                     ("env(safe-area-inset-bottom)", "맨 아래 버튼이 홈바에 먹힌다"),
                     ("env(safe-area-inset-left)", "가로 모드에서 노치가 글자를 먹는다")):
        chk(sel in css, f"{sel} — 없으면 {why}")
    chk("text-size-adjust:100%" in css.replace(" ", ""),
        "★ iOS 가로 전환 시 글자를 제멋대로 키우지 않는다")
    chk("overscroll-behavior-y:contain" in css.replace(" ", ""),
        "당겨서 새로고침 고무줄이 화면을 들썩이지 않는다")

    # ── ③ 빌드 해시가 화면 파일을 실제로 훑는가 ──
    print("\n[3] 빌드 해시 = 서비스워커 캐시 이름")
    import app as A
    before = A._build_hash()
    p = os.path.join(HERE, "static", "style.css")
    orig = io.open(p, encoding="utf-8").read()
    try:
        io.open(p, "w", encoding="utf-8", newline="\n").write(orig + "\n/* 해시 검사 */\n")
        after = A._build_hash()
    finally:
        io.open(p, "w", encoding="utf-8", newline="\n").write(orig)
    chk(before != after,
        "★ style.css 만 고쳐도 해시가 바뀐다(안 바뀌면 앱이 수정을 영영 못 받는다)",
        f"{before} → {after}")
    chk(A._build_hash() == before, "원복하면 해시도 원래대로")

    print("-" * 70)
    print(f"  통과 {OK} · 실패 {FAIL}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
