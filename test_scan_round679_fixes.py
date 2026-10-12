# -*- coding: utf-8 -*-
"""스캔 679/680라운드 회귀(직접조사, 하위위임 없음) — round678이 남긴 핸드오프 각도1을 완주했으나,
   round679 자신이 세운 핵심 전제가 두 단계에 걸쳐 틀린 것으로 드러나, round680이 근본적으로
   다시 고쳤다.

  1단계(round679의 주장, 틀림) — grep이 아니라 AST로 저장소 전체의 subprocess.run/Popen/
  check_output/call 호출 247곳을 전수 분류해 "text=True인데 encoding= 이 없고 출력을
  캡처한다" 조건에 걸리는 12곳을 찾아낸 방법론 자체는 유효하다(이번 라운드도 재사용).
  그중 manage.py의 schtasks 세 호출(cmd_install_scheduler)에 대해 "schtasks.exe는 파이프로
  캡처될 때 실제로 UTF-8 바이트를 낸다"고 주장하며 encoding="utf-8", errors="replace"를
  넣었다.

  2단계(round680의 1차 정정, 이것도 불완전) — round680이 이 PC에서 원시 바이트를 직접
  strict 디코드 비교하니 정반대였다: utf-8은 실패하고 cp949만 성공+원본과 왕복일치했다.
  encoding="utf-8" 강제를 빼고 로케일 기본(cp949)에 errors="replace"만 방어로 남기는
  선에서 고쳤는데 — run_all_tests.py 배터리(콘솔이 없는 중첩 파이프 실행 맥락) 안에서
  두 차례 재현 가능하게 크래시가 났고, 그 크래시 로그를 열어 보니 이번엔 원시 출력이
  **영어 UI**("Folder:"·"TaskName" 등)로 나오며 그 경우엔 오히려 utf-8이 맞고 cp949가
  깨졌다.

  ★★★★★ 결론 — schtasks.exe 자신의 UI 언어(그리고 그에 따른 출력 인코딩)가 실행 맥락
  (콘솔 부착 여부 등, 근본원인 미확정)에 따라 한글 UI(cp949)와 영어 UI(utf-8) 사이를
  오간다 — "어느 한쪽이 진짜다"라는 전제 자체가 틀렸다. 그래서 text=True(고정 인코딩
  하나만 시도하고, 실패하면 background reader thread가 그 자리서 죽어 stdout 전체가
  조용히 None이 되는 방식) 자체를 버리고, **원시 바이트를 그대로 받아 메인 스레드에서
  직접** utf-8 → cp949 → cp949+errors="replace"(최후 방어선) 순서로 시도하는 로컬 헬퍼
  `_decode_schtasks()`를 manage.py의 cmd_install_scheduler() 안에 신설했다. 이러면 어느
  쪽 인코딩이 오든(둘 중 하나로 항상 성공한다는 것을 아래 [2]에서 직접 증명) 크래시도
  None도 없이 사람이 읽을 문자열을 얻는다.

  ★ round679이 나머지 9곳(node·bash 호출, manage.py 제외)에 넣은 encoding="utf-8"은
  건드리지 않는다 — Node.js·Git Bash는 schtasks.exe 같은 네이티브 Win32 콘솔 도구와 달리
  자체적으로 UTF-8을 쓰는 경향이 있고(round678의 원래 node --check 발견과 같은 근거),
  round680은 이 부분에 대한 반증을 찾지 못했다. 다만 이번 일로 "같은 패턴이라고 다른
  도구에 그대로 일반화하면 위험하다"·"한 실행 맥락에서 관찰한 인코딩을 항상-참으로
  일반화하면 위험하다"는 이중의 교훈이 생겼다(향후 라운드 참고용).

  회귀테스트(이 파일) —
  [1] 소스 — manage.py 세 호출이 이제 text=True 자체가 없는(원시 바이트) 형태이고,
      _decode_schtasks() 헬퍼가 utf-8→cp949→cp949+replace 순서로 시도하는 구조임을 실제
      함수 본문에서 그대로 잘라내 확인. round679이 고친 나머지 6개 테스트파일 호출부는
      그대로 encoding="utf-8" 유지 확인(건드리지 않았음). 저장소 전체를 AST로 재감사 —
      manage.py의 세 호출은 이제 text=True 자체가 없어 "위험"(text=True+캡처+encoding無)
      조건에 애초에 안 걸리므로, 남는 대조군은 round591·round678의 r_bad_noenc 둘뿐임을
      확인.
  [2] 단위 — manage.py 실제 소스에서 _decode_schtasks() 함수 본문을 정규식으로 그대로
      잘라내(손으로 재입력 안 함) exec, 두 가지 합성 바이트열(① cp949로 인코드한 한글
      작업이름 포함 문자열 ② utf-8로 인코드한 같은 문자열)에 각각 적용해 **둘 다** 원문
      그대로 정확히 복원됨을 증명한다 — 이것이 이 헬퍼가 존재하는 이유(어느 인코딩이
      와도 견딘다)의 핵심 증거다.
  [3] 실제 인과관계 — **진짜 설치된 운영 작업 '복구온_경매마감'을 상대로**(읽기전용
      /Query만) 지금 이 순간 실제로 어느 인코딩으로 나오든(사전에 알 수 없음, 그래서
      둘 다 시도한다) _decode_schtasks()가 크래시·None 없이 사람이 읽을 문자열을
      돌려줌을 실측한다.
  [4] 되돌리기-증명 — 위 두 합성 바이트열 각각에 대해, "text=True로 한쪽 인코딩만
      강제"하는 옛 접근(round679의 encoding="utf-8" 강제, 그리고 round680 1차 정정의
      cp949 강제) 중 최소 하나는 반드시 실패(강제한 인코딩과 실제 바이트가 다른 조합)
      함을 재현해, 새 _decode_schtasks()만이 두 경우 모두를 견딘다는 것을 대조 증명한다.
      (실제 manage.py 파일은 이 테스트 내내 전혀 건드리지 않는다 — 문자열·바이트 조작만.)

      python test_scan_round679_fixes.py
"""
import ast
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    import io
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


print("=" * 72)
print("  스캔 679/680라운드 회귀 — schtasks 인코딩은 실행 맥락에 따라 갈린다(양쪽 다 견디게)")
print("=" * 72)

MANAGE_SRC = read("manage.py")

# ============================================================
print("\n[1] 소스 확인 — manage.py 세 호출은 원시 바이트, _decode_schtasks() 신설 확인")
# ------------------------------------------------------------
_starts = [m.start() for m in re.finditer(r"subprocess\.run\(\[\"schtasks\"", MANAGE_SRC)]
chk(len(_starts) == 3,
    "  manage.py에 schtasks subprocess.run 호출이 정확히 3곳(Delete·Create·Query) 있다",
    len(_starts))

_snippets = []
for s in _starts:
    e = MANAGE_SRC.find(")", MANAGE_SRC.find("capture_output=True", s)) + 1
    _snippets.append(MANAGE_SRC[s:e])

for label, snip in zip(("/Delete", "/Create", "/Query"), _snippets):
    chk("text=True" not in snip and "encoding=" not in snip,
        f"★★★★★ manage.py의 schtasks {label} 호출은 text=True도 encoding=도 없는 "
        f"순수 원시 바이트 캡처다(round680) — 디코딩은 subprocess 내부 리더스레드가 "
        f"아니라 메인 스레드에서 _decode_schtasks()로 직접 한다", snip)

_helper_start = MANAGE_SRC.find("def _decode_schtasks(")
chk(_helper_start > 0, "  manage.py에 _decode_schtasks() 헬퍼가 실제로 있다")
_helper_end = MANAGE_SRC.find("\n\n", _helper_start)
HELPER_SRC = MANAGE_SRC[_helper_start:_helper_end]
chk('for enc in ("utf-8", "cp949")' in HELPER_SRC,
    "★★★★★ _decode_schtasks()가 utf-8을 먼저, 그다음 cp949를 시도하는 순서다",
    HELPER_SRC)
chk('errors="replace"' in HELPER_SRC,
    "  _decode_schtasks()에 두 인코딩 다 실패했을 때의 최후 방어선(errors=\"replace\")이 "
    "있다", HELPER_SRC)

_FIXED_TEST_FILES = [
    ("test_scan_round12_fixes.py", 'subprocess.run([node, _tmp]'),
    ("test_scan_round168_fixes.py", 'subprocess.run([NODE, "-e", script]'),
    ("test_scan_round289_fixes.py", '["node", node_path, os.path.join(HERE, "templates"'),
    ("test_scan_round310_fixes.py",
     'subprocess.run([_bash, "-n", os.path.join(HERE, "deploy", "backup.sh")]'),
    ("test_scan_round311_fixes.py",
     'subprocess.run([_bash, "-n", os.path.join(HERE, "deploy", "bootstrap.sh")]'),
    ("test_scan_round677_fixes.py", '"static", "admin.js")]'),
]
for fname, marker in _FIXED_TEST_FILES:
    src = read(fname)
    idx = src.find(marker)
    chk(idx >= 0, f"  {fname} — 수정 대상 호출부를 실제 소스에서 찾았다", marker)
    window = src[max(0, idx - 200):idx + 400]
    chk('encoding="utf-8"' in window and 'errors="replace"' in window,
        f"  {fname} — round679이 넣은 encoding=\"utf-8\", errors=\"replace\"가 "
        f"그대로 남아 있다(node·bash 호출은 이번에 반증 못 함, 안 건드림)", window)

_r311 = read("test_scan_round311_fixes.py")
_sed_idx = _r311.find("subprocess.run([_bash, \"-c\", _sed_cmd]")
chk(_sed_idx >= 0, "  test_scan_round311_fixes.py — sed 호출부도 찾았다")
_sed_window = _r311[_sed_idx:_sed_idx + 200]
chk('encoding="utf-8"' in _sed_window and 'errors="replace"' in _sed_window,
    "  test_scan_round311_fixes.py — sed 호출도 encoding=\"utf-8\"이 그대로 남아 있다",
    _sed_window)


#  ── 저장소 전수 재감사(AST) — round679과 같은 방법론 ──
def _iter_py_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in filenames:
            if fn.endswith(".py"):
                yield os.path.join(dirpath, fn)


def _get_func_name(func):
    parts, node = [], func
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def _is_pipe(node):
    return isinstance(node, (ast.Attribute, ast.Name)) and _get_func_name(node).endswith("PIPE")


def _audit_repo():
    at_risk = []
    for path in _iter_py_files(HERE):
        try:
            src = open(path, encoding="utf-8").read()
            tree = ast.parse(src, filename=path)
        except (UnicodeDecodeError, SyntaxError):
            continue
        lines = src.splitlines()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            base = _get_func_name(node.func).split(".")[-1]
            if base not in ("run", "Popen", "check_output", "call", "check_call"):
                continue
            has_text = has_enc = cap = False
            for kw in node.keywords:
                if kw.arg in ("text", "universal_newlines") and isinstance(kw.value, ast.Constant) \
                        and kw.value.value is True:
                    has_text = True
                if kw.arg == "encoding":
                    has_enc = True
                if kw.arg == "capture_output" and isinstance(kw.value, ast.Constant) \
                        and kw.value.value is True:
                    cap = True
                if kw.arg in ("stdout", "stderr") and _is_pipe(kw.value):
                    cap = True
            if base == "check_output":
                cap = True
            if has_text and cap and not has_enc:
                start, end = node.lineno, getattr(node, "end_lineno", node.lineno)
                snippet = "\n".join(lines[start - 1:end])
                at_risk.append((os.path.relpath(path, HERE).replace("\\", "/"), start, snippet))
    return at_risk


def _is_known_guard_case(relpath, snippet):
    if relpath == "test_scan_round591_fixes.py" and "time.sleep(0.15)" in snippet:
        return True
    if relpath == "test_scan_round678_fixes.py" and "r_bad_noenc" in snippet:
        return True
    return False


_at_risk = _audit_repo()
chk(len(_at_risk) >= 2,
    "  (harness) 전수감사가 최소한 2개(의도적 대조군)는 여전히 찾아낸다 — 감사 로직 "
    "자체가 죽은 채로 0을 보고하는 게 아니다", len(_at_risk))

_unexpected = [(p, ln, sn) for p, ln, sn in _at_risk if not _is_known_guard_case(p, sn)]
chk(len(_unexpected) == 0,
    "★★★★★★ 저장소 전체(subprocess.run/Popen/check_output/call) 중 "
    "text=True+캡처+encoding無 인 것은 의도적 대조군(round591·round678의 r_bad_noenc) "
    "뿐이다 — manage.py의 schtasks 세 곳은 이제 text=True 자체가 없어 이 위험 집합에서 "
    "구조적으로 빠졌다(디코딩을 아예 다른 방식으로 하므로)",
    [(p, ln) for p, ln, _ in _unexpected])

_known = [(p, ln) for p, ln, sn in _at_risk if _is_known_guard_case(p, sn)]
chk(len(_known) == 2,
    "  (harness) round591의 time.sleep + round678의 r_bad_noenc = 정확히 2곳이 "
    "여전히 그 자리에 있다(실수로 같이 고쳐서 그 회귀테스트들의 자기증명을 깨뜨리지 "
    "않았다)", _known)

# ============================================================
print("\n[2] 단위 — _decode_schtasks()를 두 가지 합성 바이트열(cp949/utf-8)에 직접 적용")
# ------------------------------------------------------------
_ns = {}
exec(compile(HELPER_SRC, "<round680_decode_schtasks>", "exec"), _ns)
_decode_schtasks = _ns["_decode_schtasks"]

SAMPLE_TEXT = "TaskName: 복구온_경매마감  Status: Ready"
_bytes_cp949 = SAMPLE_TEXT.encode("cp949")
_bytes_utf8 = SAMPLE_TEXT.encode("utf-8")
chk(_bytes_cp949 != _bytes_utf8,
    "  (전제) 같은 한글 포함 문자열이 cp949/utf-8로 서로 다른 바이트열이 된다"
    "(그래야 아래 시험이 의미가 있다)")

_decoded_from_cp949 = _decode_schtasks(_bytes_cp949)
chk(_decoded_from_cp949 == SAMPLE_TEXT,
    "★★★★★★★ cp949로 인코드된 바이트열을 _decode_schtasks()에 넣으면 원문 그대로 "
    "복원된다(한글 UI 시나리오)", _decoded_from_cp949)

_decoded_from_utf8 = _decode_schtasks(_bytes_utf8)
chk(_decoded_from_utf8 == SAMPLE_TEXT,
    "★★★★★★★ 같은 문자열을 utf-8로 인코드한 바이트열을 넣어도 원문 그대로 복원된다"
    "(영어 UI에서도 실제로는 데이터에 한글이 섞여 나오는 시나리오)", _decoded_from_utf8)

chk(_decode_schtasks(None) == "",
    "  None 입력(예: stderr가 비어 아예 없을 때)은 예외 없이 빈 문자열로 처리된다")

# ============================================================
print("\n[3] 실제 인과관계 — 진짜 설치된 운영 작업을 상대로(읽기전용 /Query만) "
      "실제로 지금 어느 인코딩이 오든 크래시·None 없이 디코딩되는가")
# ------------------------------------------------------------
REAL_TASK = "복구온_경매마감"
_raw = subprocess.run(["schtasks", "/Query", "/TN", REAL_TASK], capture_output=True)
if _raw.returncode != 0:
    chk(False, "  [3] 이 PC에 실제 운영 작업 '복구온_경매마감'이 설치돼 있지 않아 "
               "실제-인과관계 실측을 건너뛸 수밖에 없었다(다른 환경일 수 있음)")
else:
    chk(True, "  (전제) 실제 운영 작업 '복구온_경매마감'이 이 PC에 설치돼 있다 — "
              "이 절은 진짜 운영 데이터를 상대로(읽기전용) 실측한다")

    _decoded_real = _decode_schtasks(_raw.stdout)
    chk(bool(_decoded_real),
        "★★★★★★ manage.py의 실제 _decode_schtasks() 헬퍼로 지금 이 순간의 실제 "
        "schtasks 원시 바이트를 디코드하면(어느 인코딩이든 사전에 모름) 크래시도 "
        "빈 결과도 아닌 실제 문자열이 나온다", repr(_decoded_real)[:200])
    chk("�" not in _decoded_real or REAL_TASK.encode("cp949") not in _raw.stdout
        and REAL_TASK.encode("utf-8") not in _raw.stdout,
        "  (참고) 치환문자가 있다면 오늘 이 실행에서는 두 인코딩 다 안 맞았다는 뜻 — "
        "그래도 예외 없이 최후 방어선까지 도달했다는 사실 자체가 이 수정의 핵심")

    # ========================================================
    print("\n[4] 되돌리기-증명 — 단일 인코딩을 강제하는 옛 접근들은 최소 한 시나리오에서 "
          "반드시 깨진다(실제 파일은 무변경)")
    # --------------------------------------------------------
    def _old_forced_encoding_decode(b, enc):
        """round679(encoding='utf-8')·round680 1차 정정(cp949)이 각각 강제했던 옛 접근 —
        text=True 서브프로세스 호출 없이, 같은 실패 양상(맞지 않는 인코딩이면 예외)만
        순수 함수로 재현한다(실제 파일·프로세스 무관, 문자열/바이트 연산뿐)."""
        return b.decode(enc)  # strict — round679/680-1차와 동일하게 errors 지정 없음

    _r679_forced_utf8_on_cp949_bytes_failed = False
    try:
        _old_forced_encoding_decode(_bytes_cp949, "utf-8")
    except UnicodeDecodeError:
        _r679_forced_utf8_on_cp949_bytes_failed = True
    chk(_r679_forced_utf8_on_cp949_bytes_failed,
        "★★★★★★★ round679의 접근(utf-8 강제)은 cp949로 인코드된 바이트열(한글 UI "
        "시나리오)에서 그대로 깨진다 — 이번 세션이 처음 겪은 실제 증상 그대로 재현")

    _r680a_forced_cp949_on_utf8_bytes_failed = False
    try:
        _old_forced_encoding_decode(_bytes_utf8, "cp949")
    except UnicodeDecodeError:
        _r680a_forced_cp949_on_utf8_bytes_failed = True
    chk(_r680a_forced_cp949_on_utf8_bytes_failed,
        "★★★★★★★ round680의 1차 정정(cp949 강제)도 utf-8로 인코드된 바이트열(영어 UI "
        "시나리오)에서 그대로 깨진다 — 배터리 컨텍스트에서 실제로 재현됐던 바로 그 실패")

    chk(_decode_schtasks(_bytes_cp949) == SAMPLE_TEXT and
        _decode_schtasks(_bytes_utf8) == SAMPLE_TEXT,
        "★★★★★★★ 그런데 새 _decode_schtasks()는 위 두 시나리오(한글 UI·영어 UI) "
        "모두에서 예외 없이 원문을 정확히 복원한다 — 단일 인코딩 강제 대신 순서대로 "
        "시도하는 접근만이 실제로 관찰된 두 경우 모두를 견딘다")

    chk(read("manage.py") == MANAGE_SRC,
        "  (sanity) 이 테스트 도중에도 manage.py 실제 파일은 바이트 단위로 무변경이다"
        "(읽기만 했다)")

# 최종 문법 안전망 — manage.py가 여전히 유효한 파이썬인지
chk(bool(ast.parse(MANAGE_SRC)), "  (sanity) manage.py 전체가 여전히 유효한 파이썬 문법이다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
