# -*- coding: utf-8 -*-
"""고아문자·깨진문자 점검.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

두 가지를 본다.

■ 1. 깨진 문자 (파일 수준)
   · U+FFFD  — 인코딩이 어긋나 이미 복구 불가능하게 깨진 자리
   · 제어문자 — 눈에 안 보이는데 화면·엑셀·PDF 에서 사고를 낸다
   · 폭 없는 문자(U+200B 등) — 붙여넣기로 딸려 들어와 검색·비교를 조용히 깨뜨린다
   · 한글 자모 단독(ㄱ~ㅣ) — 조합이 풀린 흔적
   · 중간 BOM — 파일 첫머리가 아닌 곳의 BOM

■ 2. 고아문자 (조판 수준)
   한 문단·제목이 줄바꿈되면서 **마지막 줄에 한두 글자만** 남는 것.
   한글 문서에서 가장 흔한 조판 흠이고, 좁은 칸(카드·표 머리)에서 잘 생긴다.
   여기서는 소스의 '줄바꿈 위험 문구'를 후보로 뽑고,
   실제 렌더 측정은 브라우저로 따로 한다(폰트·폭에 좌우되므로).

실행:
    python check_orphan_chars.py
"""
import io
import os
import re
import sys
import unicodedata

#  ⚠⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로
#    죽는다. 점검 도구가 결과를 내기 직전에 죽으면 "통과했는지 실패했는지"를
#    전혀 알 수 없다(실측: 이 파일 자신이 166행에서 "고아문자 — 대상 N개
#    파일"을 찍다가 그대로 죽는다) — 형제(check_tx_paths.py)는 이미 이 방어가
#    있는데 같은 저자·같은 목적(check_*.py 점검 도구)인 이 파일만 빠져 있었다.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

HERE = os.path.dirname(os.path.abspath(__file__))

# 검사 대상 — 사람이 읽는 문구가 들어가는 파일
TARGET_EXT = (".py", ".html", ".js", ".css", ".md", ".txt", ".json", ".bat", ".ps1")
#  ⚠⚠ [라운드124] "docs" 는 다른 항목(uploads·backups·logs 등)과 성격이 다르다 —
#    저것들은 기계만 보는 산출물이지만, docs/ 는 build_pages.py 가 templates/ 에서
#    만들어내는 **실제 공개 GitHub Pages 사이트**다(legal_docs.py 로 만드는
#    개인정보처리방침·이용약관·사업자정보 포함). "생성물이니 건너뛴다"는 일반화가
#    틀렸다 — 사람이 보는 결과물일수록 이 점검이 더 필요하다. 실측: docs/ 아래
#    14개 파일이 이 점검 대상에서 통째로 빠져 있었다(전수 258개 vs 실제 272개).
SKIP_DIRS = {"uploads", "backups", "logs", "__pycache__", ".git", "static/fonts"}

BAD = {
    "�": "복구 불가하게 깨진 문자(U+FFFD)",
    "​": "폭 없는 공백(U+200B)",
    "‌": "폭 없는 비접합(U+200C)",
    "‍": "폭 없는 접합(U+200D)",
    "﻿": "BOM(U+FEFF)",
    " ": "줄바꿈 없는 공백(U+00A0)",
    "　": "전각 공백(U+3000)",
}
# 한글 자모가 홀로 있는 것 = 조합이 풀린 흔적 (ㄱ~ㅎ, ㅏ~ㅣ)
JAMO = re.compile(r"[ㄱ-ㆎ]")
#  ⚠⚠ [라운드124] 'ㆍ'(U+318D 아래아)는 깨진 흔적이 아니라 정부 공식 업종 표기
#    규칙이다(app.py 주석: "정부 공식 업종 표기('ㆍ' U+318D 아래아)... 사람은
#    '·'를 친다" — _norm_dot() 이라는 정규화 함수까지 따로 있다). docs/ 를
#    스캔 대상에 넣자 이 하나의 오탐이 app.py·compliance.py·data/*.json·
#    여러 테스트 전체에서 반복 발화해, 정작 진짜 깨진 문자(예: 이 라운드가
#    같은 실행에서 찾아낸 test_scan_round101_fixes.py 의 진짜 U+FFFD)가
#    거대한 오탐 더미에 묻혔다. 자주 우는 늑대는 아무도 안 믿는다.
_JAMO_OK = {"ㆍ"}


def scan_file(path):
    """파일 하나에서 깨진 문자를 찾는다. [(줄번호, 종류, 발췌)] 반환."""
    hits = []
    try:
        raw = io.open(path, "rb").read()
    except OSError:
        return hits
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        hits.append((0, "UTF-8 로 읽히지 않음", str(e)[:80]))
        return hits

    all_lines = text.splitlines()
    for i, line in enumerate(all_lines, 1):
        for ch, why in BAD.items():
            if ch in line:
                # 파일 첫머리 BOM 은 정상(윈도 호환 목적으로 일부러 넣은 곳이 있다)
                if ch == "﻿" and i == 1 and line.startswith("﻿"):
                    continue
                #  ⚠⚠ [라운드291] BOM·NBSP 를 코드가 "그 문자 자체"를 다루려고
                #    일부러 리터럴로 쓴 자리(.lstrip("﻿") 로 BOM 을 벗기는 코드,
                #    CSV 응답 앞에 BOM 을 붙이는 코드, widont 스크립트의 NBSP
                #    상수, 그 둘을 검증하는 테스트)까지 산문이 깨진 것처럼
                #    잡혔다 — 실측: 이번 정밀조사가 찾은 38건 전부가 이 두
                #    글자 범주였고 전부 오탐이었다(진짜 조치 대상 0건).
                #    round124 가 'ㆍ' 하나로 이미 겪은 "자주 우는 늑대" 문제의
                #    재발이다. 그 문자를 다룬다는 뜻의 식별자(.lstrip( · BOM ·
                #    NBSP, 전부 이 코드베이스가 이미 실제로 쓰는 표기)가 **바로
                #    앞뒤 줄 안에** 있으면 코드가 그 문자를 의도적으로 다루는
                #    것이지 산문 오염이 아니다 — 여러 줄에 걸친 문장(예:
                #    chk(...) 호출이 다음 줄까지 이어짐)에서도 놓치지 않게
                #    앞뒤 한 줄씩 같이 본다. 진짜 깨진 산문이 하필 그 근처에
                #    그 영어 식별자까지 우연히 담고 있을 확률은 사실상 없다.
                #    다른 5개 BAD 문자(U+FFFD·200B·200C·200D·3000)는 이런
                #    오탐 사례가 없어 그대로 둔다.
                nearby = "\n".join(all_lines[max(0, i - 2):i + 1])
                if ch == "﻿" and (".lstrip(" in nearby or "BOM" in nearby or "\\ufeff" in nearby):
                    continue
                if ch == "\xa0" and "NBSP" in nearby:
                    continue
                col = line.index(ch)
                hits.append((i, why, line[max(0, col - 25):col + 25].strip()))
        # 제어문자 (탭·개행 제외)
        for ch in line:
            if unicodedata.category(ch) == "Cc" and ch != "\t":
                hits.append((i, f"제어문자 U+{ord(ch):04X}", line[:60].strip()))
                break
        # 홀로 남은 한글 자모 — 다만 'ㄱ~ㅎ' 를 기호처럼 쓰는 경우가 있어 문맥을 같이 보여준다
        #  ⚠ [라운드124] 'ㆍ'만 예외로 건너뛴다 — search() 대신 finditer() 를 써서,
        #    같은 줄에 'ㆍ'와 진짜 깨진 자모가 같이 있어도 뒤엣것을 놓치지 않는다.
        for m in JAMO.finditer(line):
            if m.group() in _JAMO_OK:
                continue
            hits.append((i, f"한글 자모 단독 '{m.group()}'", line[max(0, m.start()-25):m.start()+25].strip()))
            break
    return hits


# ── 조판 고아문자 후보 ────────────────────────────────────────
#  좁은 칸에 들어가는 문구 중, 마지막 어절이 1글자라 줄 끝에 홀로 떨어지기 쉬운 것.
#  (실제 줄바꿈은 폰트·폭에 달렸으므로 여기서는 '위험 후보'만 고른다)
LABEL_PAT = re.compile(r'>([^<>{}\n]{6,40})<')


def orphan_candidates(path):
    """마지막 어절이 1글자인 짧은 문구를 후보로 뽑는다."""
    out = []
    try:
        text = io.open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        return out
    for m in LABEL_PAT.finditer(text):
        s = m.group(1).strip()
        if not s or "${" in s or "{{" in s or "{%" in s:
            continue
        if not re.search(r"[가-힣]", s):
            continue
        words = s.split()
        # 필수표시(*)·기호(✓ → ↑)·단위 하나짜리 꼬리는 조판 흠이 아니다.
        # 이런 걸 후보에 남기면 진짜 고아문자가 묻힌다.
        #  ⚠⚠ [라운드654] '↗'(외부링크 표시, target="_blank" 앵커 꼬리)가 이
        #    목록에서 빠져 있었다 — 이미 있는 →/←/↑/↓ 와 성격이 완전히 같은
        #    "라벨 뒤에 붙는 1글자 아이콘"인데 대각선이라는 이유만으로 빠졌다
        #    (실측: static/admin.js:1135 "발주처 연동 안내서 ↗"·:1311 "KISCON
        #    조회 ↗", templates/insurer_portal.html:446 "전산 연동 안내서 ↗"
        #    3곳 전부 <a target="_blank"> 외부링크 라벨 — 실제 조판 흠이
        #    아니다). round124 가 이미 겪은 "자주 우는 늑대"(오탐이 진짜
        #    고아문자를 묻는 문제)와 같은 클래스라 그대로 추가한다 — 코드베이스에
        #    안 쓰이는 다른 대각선 화살표(↘·↖·↙)는 추측성 확장이라 넣지 않는다.
        if words and words[-1] in ("*", "✓", "→", "←", "↑", "↓", "↗", "·", "—", "-"):
            continue
        if len(words) >= 2 and len(words[-1]) == 1:
            line = text[:m.start()].count("\n") + 1
            out.append((line, s))
    return out


def main():
    print("=" * 68)
    print("  고아문자·깨진문자 점검")
    print("=" * 68)

    files = []
    for root, dirs, names in os.walk(HERE):
        rel = os.path.relpath(root, HERE).replace("\\", "/")
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and f"{rel}/{d}".lstrip("./") not in SKIP_DIRS]
        for n in names:
            if n.endswith(TARGET_EXT):
                files.append(os.path.join(root, n))

    print(f"\n[1] 깨진 문자 — 대상 {len(files)}개 파일")
    print("-" * 68)
    total = 0
    for f in sorted(files):
        hits = scan_file(f)
        if hits:
            total += len(hits)
            rel = os.path.relpath(f, HERE)
            for ln, why, snippet in hits[:6]:
                print(f"  {rel}:{ln}  {why}")
                if snippet:
                    print(f"      … {snippet}")
            if len(hits) > 6:
                print(f"      (외 {len(hits)-6}건)")
    if not total:
        print("  깨진 문자 없음 ✓")

    print(f"\n[2] 조판 고아문자 후보 — 마지막 어절이 1글자인 문구")
    print("-" * 68)
    cand = 0
    for f in sorted(files):
        if not f.endswith((".html", ".js")):
            continue
        cs = orphan_candidates(f)
        if cs:
            #  ⚠⚠ [라운드654] 바로 위 [1]번 블록(202행 total += len(hits))은
            #    화면에 최대 6개만 찍어도 total 은 **잘리기 전 전체 개수**로
            #    센다. 그런데 형제인 이 블록은 cand 를 `for ln,s in cs[:8]:`
            #    루프 **안에서** 늘려, 화면에 실제로 찍힌(최대 8개) 것만 세고
            #    한 파일이 8건을 넘는 나머지는 "(외 N건)"으로 안내만 하고
            #    맨 끝 합계 "조판 후보 N건"에서는 조용히 빠졌다(실측: 이
            #    라운드가 고친 ↗ 오탐 2건을 admin.js에서 걷어내자, 8건 컷 밖에
            #    있던 후보 2개가 컷 안으로 밀려 들어와 요약 수치가 41→40으로
            #    "겨우 1"만 줄었다 — admin.js 는 지금도 14건인데 8개만 세여
            #    있었다는 뜻). 이 요약 숫자는 다음 라운드가 "남은 후보가
            #    몇 개인가"를 가늠하는 근거로 그대로 쓰이므로(라운드641 회귀
            #    테스트가 이 값을 41로 못박아 검증할 만큼), 화면에 몇 줄을
            #    찍든 합계는 실제 전체 건수를 반영해야 한다 — total 과 같은
            #    방식으로 자른 목록이 아니라 원본 길이(len(cs))를 센다.
            cand += len(cs)
            rel = os.path.relpath(f, HERE)
            for ln, s in cs[:8]:
                print(f"  {rel}:{ln}  \"{s}\"")
            if len(cs) > 8:
                print(f"      (외 {len(cs)-8}건)")
    if not cand:
        print("  후보 없음 ✓")
    else:
        print(f"\n  ※ 후보 {cand}건. 실제로 줄이 갈리는지는 폭에 달렸으므로")
        print("     브라우저 측정으로 확인해야 합니다(word-break:keep-all 적용 상태 포함).")

    print("-" * 68)
    print(f"  깨진 문자 {total}건 · 조판 후보 {cand}건")
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
