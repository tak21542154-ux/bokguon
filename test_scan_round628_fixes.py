# -*- coding: utf-8 -*-
"""스캔 628라운드 회귀 — db.py seed()가 협력업체 시드 파일(data/partners_seed.json)
   로드 실패를 조용히 삼키던 결함 1건(직접조사, 하위위임 없음. 611~627라운드의
   17라운드짜리 마이그레이션 배틀이 완전히 끝난 뒤 첫 순수 신규조사 라운드).

   배경 — ingest_partners.py 는 자기 파일 자신의 round300 주석에 이렇게 적어
   뒀다: "db.py 쪽은 json.load() 실패를 빈 목록으로 조용히 삼켜(실측: 잘린
   파일로 새 DB 를 만들면 협력사 0곳으로 조용히 끝난다) 아무 경고 없이 협력사
   전체가 사라진 채 배포될 수 있다." round300 은 그 라운드의 범위(쓰는 쪽)만
   고쳐 ingest_partners.py 가 임시파일 경유 원자적 교체(os.replace)로 "쓰다
   만 파일"은 막았지만, **읽는 쪽인 db.py 자신은 그 이후 단 한 번도 손대지
   않은 채** 그대로 남아 있었다 — 이번 라운드가 이어받아 실제로 db.py 소스를
   Read 로 직접 확인(1952~1956행)해 지금도 정확히 그 모양임을 확인했다.

   원자적 교체가 "쓰다 만 파일"은 막아도 그 밖의 손상 경로(수동 편집 실수·
   병합 충돌 마커·인코딩 손상·잘못된 파일을 덮어씀)는 전혀 못 막는다 — 이
   프로젝트가 반복해서 고쳐 온 "삼켜진 예외가 항목을 지운다" 계열과 같은
   모양이며, 바로 형제 함수인 boq_history()(round268)가 이미 "동작(계속
   진행)은 그대로 두고 실패 사실만 _log.warning 으로 남긴다"는 처방을 쓰고
   있는데 seed() 의 이 자리만 그 처방이 없었다.

   실측한 실제 영향 — 두 갈래.
   [A] 조용한 데이터 손실(원래 알려진 절반) — open()/json.load() 가 예외를
       내면(파일 없음·문법 오류 등) partners=[] 로 아무 경고 없이 넘어가
       admins·insurers 는 정상 시드되고 partners 만 0곳으로 끝난다. 이
       프로젝트가 실제로 반복 사용하는 "빈 DB 로 서비스 첫날 재현" 리허설
       기법이나 dev 환경 재생성 도중 이 파일이 손상되면 재현 전체가 "협력사가
       하나도 없다"는 완전히 다른 그림으로 조용히 왜곡된다.
   [B] 서버 기동 크래시(직접 조사로 새로 찾은 절반) — json.load() 는 성공했지만
       최상위가 배열이 아니거나(dict·null 등) 배열의 원소가 dict 가 아니면(예:
       ["a","b"]) 예외가 안 나서 [A]의 except 를 안 거치는데, 그 바로 뒤(기존
       코드에선 검증 없이) for 루프의 `p.get(...)` 이 dict 아닌 원소(문자열 등)를
       만나면 AttributeError 로, partners 자체가 None/정수 등이면 TypeError 로
       예외가 나며 이번엔 그 try/except **밖**이라 안 잡힌다 — db.py:seed()→
       init_db()→app.py 모듈 최상단의 무방비 DB.init_db() 호출(201행)까지 그대로
       새어나가 서버 기동 자체가 죽는다(빈 dict `{}`·빈 리스트처럼 우연히 0번
       반복되는 모양만 [A]와 똑같이 조용히 0곳이 된다 — 이것도 결함이다).

   고침(db.py, seed() 딱 한 자리) — 정책은 안 바꾼다(partners 없이도 계속
   시드한다는 기존 동작 그대로, "그래도 되는가"는 판단대기열 몫). 두 갈래를
   **같은 자리**에서 함께 막는다: (a) json.load() 실패 시 이제
   `_log.warning()` 으로 원인(파일 경로·예외 종류·메시지)을 남긴다(round268
   boq_history() 와 같은 처방, partners=[] 로 계속 진행하는 동작 자체는 불변).
   (b) 그 직후 `isinstance(partners, list) and all(isinstance(p, dict) for p
   in partners)` 로 형태까지 검증해, 배열이 아니거나 원소가 dict 가 아니면
   역시 `_log.warning()` 을 남기고 partners=[] 로 안전하게 계속한다(전엔 여기서
   못 잡고 서버가 죽었다).

   검증 — [1] 소스 확인(두 갈래 모두 자리에 있음). [2] 실행 — 실제
   DB.seed() 를 진짜 스키마+migrate() 를 마친 스크래치 :memory: DB 에 대해
   6가지 기형 입력(파일없음·JSON 문법오류·빈dict·비어있지않은dict·null·
   dict아닌원소로찬리스트) 전부와 정상 리스트 1건으로 실행해, 기형 입력
   전부가 크래시 없이 협력사 0곳으로 끝나고 admins 는 계속 2명 그대로
   시드되며(동작 불변 증명) 매번 경고가 정확히 1건씩 로그로 남는지, 정상
   입력엔 경고가 안 뜨는지(과잉경보 아님)까지 실측한다. 실제 운영 시드
   파일(data/partners_seed.json, 398개사)도 새 형태검증을 그대로 통과하는지
   (오탐 없음) 별도로 확인한다. [3] 되돌리기-증명 — 628 이전 실제 코드
   6줄을 그대로(수정 전 Read 결과와 대조해 축자적으로) 재구성해 같은 6가지
   기형 입력을 격리된 exec() 네임스페이스로 돌려, 옛 코드가 [A]형(파일없음·
   문법오류·빈dict)에서는 경고 없이 조용히 partners=[] 로 끝나고(지금 코드와
   똑같이 조용했다는 뜬 사실이 아니라, 애초에 경고를 낼 코드 자체가 없었다는
   구조적 증명) [B]형(비어있지않은dict·null·dict아닌원소리스트)에서는 실제로
   AttributeError/TypeError 로 죽는 것까지 실행으로 재현한 뒤(디스크의 실제
   db.py 는 이 과정에서 전혀 쓰이지 않는다), 마지막에 db.py 가 여전히 고쳐진
   코드를 담고 있음을 재확인한다.

       python test_scan_round628_fixes.py
"""
import io
import json
import logging
import os
import sqlite3
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))

#  ⚠ seed()를 실제로 돌리려면 진짜 스키마+migrate() 가 필요하다 — 관례대로
#    스크래치 경로부터 잡아 둔다(운영 DB.bokguon.db 는 이 파일 전체에서 전혀
#    열지 않는다 — 아래는 전부 :memory: 커넥션과 별도 스크래치 파일뿐).
_SCRATCH = tempfile.mkdtemp(prefix="round628_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_SCRATCH, "__never_created.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_SCRATCH, "uploads")
os.environ["BOKGUON_LOG_FILE"] = os.path.join(_SCRATCH, "scratch.log")
sys.path.insert(0, HERE)

PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DBS = read("db.py")
import db as DB  # noqa: E402  (import 자체는 부작용 없음 — DB_PATH 문자열만 계산)


def extract(src, start_needle, end_needle):
    """줄 단위로 온전히 잘라낸다(round584/585 와 동일한 기법)."""
    lines = src.split("\n")
    start = end = None
    for i, ln in enumerate(lines):
        if start is None and start_needle in ln:
            start = i
        elif start is not None and end_needle in ln:
            end = i
            break
    assert start is not None and end is not None, (start_needle, end_needle)
    return "\n".join(lines[start:end])


print("=" * 72)
print("  스캔 628라운드 회귀 — db.py seed() 협력업체 시드 로드 실패 은폐")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 확인")
# ══════════════════════════════════════════════════════════════
BLOCK_NOW = extract(DBS, "# --- 협력업체 시드", "import random")
chk(BLOCK_NOW.strip().startswith("# --- 협력업체 시드"), "(준비) 시드 블록 추출")

PREFIX_SHARED = ('    try:\n'
                  '        with open(SEED_JSON, encoding="utf-8") as f:\n'
                  '            partners = json.load(f)\n'
                  '    except')
chk(PREFIX_SHARED in BLOCK_NOW,
    "(준비) 옛 코드와 공유하는 try/open/json.load 자리가 그대로 남아 있다")
chk("except Exception as e:" in BLOCK_NOW and BLOCK_NOW.count("_log.warning(") == 2,
    "★★★★★ [A]+[B] 두 갈래 모두 _log.warning() 으로 알린다(전엔 경고 0건)")
chk('isinstance(partners, list) and all(isinstance(p, dict) for p in partners)' in BLOCK_NOW,
    "★★★★★ [B] 최상위 타입과 원소 타입까지 한 자리에서 함께 검증한다")
chk("except Exception as e:" in BLOCK_NOW
    and "partners = []" in BLOCK_NOW.split("except Exception as e:", 1)[-1],
    "[A] 경고 후에도 동작은 불변 — partners=[] 로 계속 진행")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 고쳐진 코드: 실제 DB.seed() 를 기형 입력 6종 + 정상 1종으로 실행")
# ══════════════════════════════════════════════════════════════
_warned = []


class _Capture(logging.Handler):
    def emit(self, record):
        _warned.append(record.getMessage())


DB._log.addHandler(_Capture())
DB._log.setLevel(logging.WARNING)
_ORIG_SEED_JSON = DB.SEED_JSON


def _fresh_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(DB.SCHEMA)
    conn.executescript(DB.PHOTO_SCHEMA)
    conn.commit()
    DB.migrate(conn)
    return conn


def _write(name, content):
    p = os.path.join(_SCRATCH, name)
    with io.open(p, "w", encoding="utf-8") as f:
        f.write(content)
    return p


FIXTURES = {
    "missing":     os.path.join(_SCRATCH, "does_not_exist.json"),
    "corrupt":     _write("corrupt.json", "{not valid json!!"),
    "empty_dict":  _write("empty_dict.json", "{}"),
    "nonempty_dict": _write("nonempty_dict.json", json.dumps({"a": 1, "b": 2})),
    "null":        _write("null.json", "null"),
    "list_of_str": _write("list_of_str.json", json.dumps(["a", "b"])),
    "valid":       _write("valid.json", json.dumps([{"name": "A사"}, {"name": "B사"}])),
}
BAD_KEYS = ("missing", "corrupt", "empty_dict", "nonempty_dict", "null", "list_of_str")


def run_seed_now(fixture_key):
    _warned.clear()
    DB.SEED_JSON = FIXTURES[fixture_key]
    conn = _fresh_conn()
    try:
        DB.seed(conn)
        n_p = conn.execute("SELECT COUNT(*) n FROM partners").fetchone()["n"]
        n_a = conn.execute("SELECT COUNT(*) n FROM admins").fetchone()["n"]
        return {"crashed": False, "partners": n_p, "admins": n_a, "warnings": list(_warned)}
    except Exception as e:
        return {"crashed": True, "error": f"{type(e).__name__}: {e}", "warnings": list(_warned)}
    finally:
        conn.close()
        DB.SEED_JSON = _ORIG_SEED_JSON


NOW_RESULTS = {}
for key in BAD_KEYS:
    r = run_seed_now(key)
    NOW_RESULTS[key] = r
    chk(not r["crashed"], f"★★★★★ 고쳐진 코드 — {key} 입력에서도 seed() 가 죽지 않는다", r)
    if not r["crashed"]:
        chk(r["partners"] == 0, f"고쳐진 코드 — {key} 입력은 협력사 0곳으로 안전하게 시작", r)
        chk(r["admins"] == 2,
            f"고쳐진 코드 — {key} 입력에도 관리자 시드는 그대로 계속된다(동작 불변)", r)
        chk(len(r["warnings"]) == 1,
            f"★★★★ 고쳐진 코드 — {key} 입력에 경고가 정확히 1건 로그로 남는다", r)

r_valid = run_seed_now("valid")
chk(not r_valid["crashed"] and r_valid["partners"] == 2 and r_valid["admins"] == 2,
    "정상 입력 회귀없음 — 협력사 2곳 그대로 들어간다", r_valid)
chk(r_valid["warnings"] == [], "정상 입력엔 경고가 안 뜬다(과잉경보 아님)", r_valid)

#  실제 운영 시드 파일(398개사)도 새 형태검증을 그대로 통과하는지 — 오탐 없음 확인
_REAL_SEED = os.path.join(HERE, "data", "partners_seed.json")
with io.open(_REAL_SEED, encoding="utf-8") as f:
    _real = json.load(f)
chk(isinstance(_real, list) and len(_real) > 300 and all(isinstance(p, dict) for p in _real),
    f"실제 운영 시드 파일({len(_real)}개사)도 새 형태검증을 그대로 통과한다(오탐 없음)")

# ══════════════════════════════════════════════════════════════
print("\n[3] 되돌리기-증명 — 628 이전 실제 코드 6줄을 그대로 재구성해 같은 입력 실행")
# ══════════════════════════════════════════════════════════════
#  ⚠ 아래 문자열은 이번 라운드가 고치기 전 db.py 1951~1956행을 Read 로 직접
#    읽어 확인한 원문 그대로다(위 PREFIX_SHARED 로 지금 코드와 공유구간이
#    글자 그대로 같음을 [1]에서 이미 확인) — 디스크의 실제 db.py 는 이 절
#    전체에서 단 한 번도 열리거나 쓰이지 않는다.
OLD_BLOCK = textwrap.dedent('''\
    try:
        with open(SEED_JSON, encoding="utf-8") as f:
            partners = json.load(f)
    except Exception:
        partners = []
    for p in partners:
        _touched.append(p.get("name"))
''')

#  BLOCK_NOW 는 맨 앞에 주석 한 줄(# --- 협력업체 시드 ...)이 그대로 남아
#  있어도 exec() 에는 무해하다 — dedent() 만 거치면 바로 실행 가능하다.
NEW_BLOCK_FOR_EXEC = textwrap.dedent(BLOCK_NOW) \
    + '\nfor p in partners:\n    _touched.append(p.get("name"))\n'


def run_block(block_text, fixture_key):
    ns = {"json": json, "SEED_JSON": FIXTURES[fixture_key], "_touched": [],
          "_log": DB._log, "isinstance": isinstance, "dict": dict, "list": list,
          "all": all, "open": open}
    try:
        exec(compile(block_text, f"<block:{fixture_key}>", "exec"), ns)
        return {"crashed": False, "partners": ns["partners"]}
    except Exception as e:
        return {"crashed": True, "error": f"{type(e).__name__}: {e}"}


_old_capture = []


class _OldCapture(logging.Handler):
    def emit(self, record):
        _old_capture.append(record.getMessage())


_old_handler = _OldCapture()
DB._log.addHandler(_old_handler)

for key in BAD_KEYS:
    _old_capture.clear()
    old_r = run_block(OLD_BLOCK, key)
    if key in ("nonempty_dict", "null", "list_of_str"):
        chk(old_r["crashed"],
            f"★★★★★ 옛 코드(되돌림) — {key} 입력은 실제로 예외로 죽는다"
            f"(이 회귀가 진짜 결함을 잡아낼 능력이 있다는 증명)", old_r)
    else:
        #  empty_dict 는 예외 없이 파싱만 성공해 partners 가 {}(딕셔너리) 그대로
        #  남는다 — [] 는 아니지만 원소 0개라 아래 루프가 0번 돌아 안 죽는 것은
        #  같다. 그래서 엄격한 == [] 대신 "비어 있음"(falsy)으로 판정한다.
        chk(not old_r["crashed"] and not old_r["partners"],
            f"옛 코드(되돌림) — {key} 입력은 죽지는 않지만 조용히 원소 0개로 끝난다", old_r)
    chk(_old_capture == [],
        f"★★★★ 옛 코드(되돌림) — {key} 입력에 경고가 단 1건도 없다"
        f"(경고를 낼 코드 자체가 없었다는 구조적 증명)", _old_capture)

for key in BAD_KEYS:
    _old_capture.clear()
    new_r = run_block(NEW_BLOCK_FOR_EXEC, key)
    chk(not new_r["crashed"] and new_r["partners"] == [],
        f"대조 — 같은 exec() 틀에서 지금 코드는 {key} 입력에도 죽지 않는다", new_r)
    chk(len(_old_capture) == 1,
        f"대조 — 같은 exec() 틀에서 지금 코드는 {key} 입력에 경고를 1건 남긴다", _old_capture)

DB._log.removeHandler(_old_handler)

chk(read("db.py") == DBS,
    "★★★★★ db.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일 — 이 라운드가 "
    "이미 적용해 둔 수정이 그대로 남아 있다는 뜻)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
