# -*- coding: utf-8 -*-
"""스캔 585라운드 회귀 — db.py init_db()/seed() 의 "안전 판정 조회가 실패하면
   증거 없음(0)"으로 보는 방향이, 두 게이트 모두에서 정확히 거꾸로였던 결함
   (직접조사, 하위위임 없음).

   조사 각도 — [라운드584]가 남긴 "except Exception: pass(및 형제 패턴) 전수 확인"
   목록을 이어받아, app.py 6곳·db.py·collect_emails.py·crypto_util.py·build_pages.py·
   check_tx_paths.py 의 조용히-넘어가는 예외처리를 전부 열어봤다. collect_emails.py·
   crypto_util.py·build_pages.py·check_tx_paths.py·db.py 24~25행은 전부 "[라운드519]
   형제 점검 도구가 이미 쓰는 방어를 그대로 옮긴다"는 동일한, 의도된 stdout 인코딩
   폴백이라 클린. db.py 의 CREATE INDEX 스킵(1483행)·_backfill_sku_keys 행별 UPDATE
   스킵(1855행)은 [라운드277]·[라운드321]이 이미 "멱등 백필이라 다음 실행이 마저
   채운다"는 근거로 정착시킨 패턴과 완전히 같은 모양이라 그대로 둔다.

   그런데 init_db() 의 "이 DB 가 이미 쓰이고 있는가" 증거조회 3종(사건·협력사·
   go_live_at, 옛 1891~1894행)과 seed() 의 "시드 전 최대 id" 스냅샷(옛 1921~1923행)은
   백필과 성격이 다르다 — 둘 다 스스로 남긴 주석(1870~1881행, 1914~1916행)이 밝히는
   대로 "틀리면 운영 데이터가 데모로 표시되고 go-live 가 그걸 지운다"는 **한 방향
   으로만 위험한(비가역)** 게이트인데, 조회 자체가 실패하면 옛 코드는 둘 다 그
   실패를 "증거 없음"(_n=0 / _base[_t]=0)으로 취급했다 — 판정 불가를 게이트가
   막으려는 바로 그 사고 쪽으로 떨어뜨리는 방향이었다. [라운드321]이 정착시킨
   "멱등 백필은 스킵해도 안전"이라는 근거는 이 두 곳에는 적용되지 않는다(스킵해도
   다음 실행이 못 고쳐주는, 한 번 잘못되면 끝인 종류의 실수이기 때문).

   실제 영향
   [A] init_db() — admins==0(=go-live 직후 정상 상태, 주석이 스스로 설명)일 때만
       도는 이 3종 조회 중 하나라도 "database is locked" 등으로 실패하면(같은 파일
       1399행 주석이 "워커 여럿이 동시에 부팅"을 이미 실제 근거로 든다) 옛 코드는
       _n=0 폴백 때문에 다음 신호로 계속 넘어갔고, 세 신호가 전부 조회 실패하면
       _used=0 그대로 남아 _empty=True 가 유지됐다 — BOKGUON_SEED_DEMO=1 환경이면
       실사건·실협력사가 있는 DB 에 seed() 가 그대로 돈다.
   [B] seed() — _base[_t] 스냅샷 조회가 실패하면 옛 코드는 0 으로 폴백해, 바로 뒤
       표시 루프가 "UPDATE {t} SET is_demo=1 WHERE id > 0" 을 그 표의 **기존 행까지
       포함해서** 돌린다 — seed() 자신의 주석(★)이 명시적으로 막으려는 사고 그 자체.

   고침(db.py)
   [A] 증거조회 except 를 "증거 있음"과 동일하게(_used=1, 즉시 break) 처리 —
       판정 불가는 시드를 막는 쪽으로 넘어간다(재시도로 복구되는 손해 vs 비가역
       손해의 비대칭이 근거).
   [B] _base[_t] 를 0 이 아니라 None 으로 남기고, 표시 루프가 None 인 표는 그
       표만 건너뛴다(UPDATE 자체를 안 함). 표시 루프 자신의 except(마킹 실패 시
       pass)는 이미 안전한 방향(표시 누락일 뿐 오표시가 아니다)이라 손대지 않았다.

   검증 — [A]·[B]·표시 루프 세 절을 현재 db.py 소스에서 그대로 오려내(on-disk
   파일은 안 건드림) 가짜 conn 으로 실제 exec() 한다. [1] 소스 확인. [2] 실행 —
   조회 성공/단일 실패/전체 실패 시나리오를 실측. [3] 되돌리기-증명 — 각 절의
   except 블록만 고치기 전 그대로 재구성(그 외 문자열은 완전히 동일함을 대조해
   과잉수정 방지)해 같은 실패 시나리오를 돌리고, 옛 코드가 실제로 반대 결과
   (게이트를 못 막았다 / 기존 행에 UPDATE 를 실제로 쐈다)를 냄을 대조한다.

       python test_scan_round585_fixes.py
"""
import io
import os
import sqlite3
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
#  ⚠ import db 자체는 부작용이 없다(DB_PATH 문자열만 계산) — 그래도 관례대로
#    스크래치 경로를 먼저 지정해 둔다(이 파일이 DB.init_db()/DB.seed() 를 직접
#    부르지는 않지만, 다음 라운드가 이 파일을 베껴 쓸 때의 안전망).
os.environ.setdefault("BOKGUON_DB_PATH",
                       os.path.join(HERE, "__scratch_round585_never_created.db"))

PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


DBS = read("db.py")
import db as DB  # noqa: E402  (정의만 참조 — DEMO_TABLES 실값을 그대로 쓴다)


def extract(src, start_needle, end_needle):
    """줄 단위로 온전히 잘라낸다(round584 와 동일한 기법) — 첫 줄 들여쓰기를
    유지해야 textwrap.dedent() 로 최상위 exec() 가 가능하다."""
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
print("  스캔 585라운드 회귀 — db.py init_db()/seed() 안전판정 조회 실패가")
print("  '증거없음(0)'으로 취급돼 두 비가역 게이트를 무력화하던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
SEC_A_NOW = extract(DBS, '_used, _why = 0, ""', "if _empty:")
SEC_B_NOW = extract(DBS, "_base = {}", "t = now()")
SEC_C_NOW = extract(DBS, "for t in DEMO_TABLES:", 'log(conn, "정비도구"')

chk(SEC_A_NOW.strip().startswith('_used, _why = 0, ""'), "(준비) A 절(증거조회 루프) 추출")
chk(SEC_B_NOW.strip().startswith("_base = {}"), "(준비) B 절(_base 스냅샷) 추출")
chk(SEC_C_NOW.strip().startswith("for t in DEMO_TABLES:"), "(준비) C 절(표시 루프) 추출")

chk("except sqlite3.Error as e:" in SEC_A_NOW and "_used, _why = 1," in SEC_A_NOW,
    "★★★ A 절 — 조회 실패를 '증거 있음'과 동일하게 처리한다(즉시 _used=1)")
chk("_n = 0" not in SEC_A_NOW,
    "★★ A 절 — 옛 '_n = 0' 폴백이 더 이상 없다")
chk("_base[_t] = None" in SEC_B_NOW and "_base[_t] = 0" not in SEC_B_NOW,
    "★★★ B 절 — 조회 실패 시 0 이 아니라 None 을 남긴다")
chk("if _base.get(t) is None:" in SEC_C_NOW and "continue" in SEC_C_NOW,
    "★★★ C 절 — 표시 루프가 기준 미상 표를 건너뛴다")

# ============================================================
print("\n[2] 실행 — 현재 db.py 에서 세 절만 오려내 가짜 conn 으로 exec()")
# ------------------------------------------------------------


class _Cur:
    def __init__(self, row):
        self._row = row

    def fetchone(self):
        return self._row


class _AConn:
    """A 절용 — SQL 문자열 그대로 매칭."""

    def __init__(self, raise_for, values):
        self.raise_for = set(raise_for)
        self.values = values
        self.calls = []

    def execute(self, sql, *a):
        self.calls.append(sql)
        if sql in self.raise_for:
            raise sqlite3.OperationalError("simulated: database is locked (round585 test)")
        return _Cur({"n": self.values.get(sql, 0)})


class _BConn:
    """B 절용 — FROM 뒤 테이블명으로 매칭."""

    def __init__(self, raise_tables, values):
        self.raise_tables = set(raise_tables)
        self.values = values
        self.calls = []

    def execute(self, sql, *a):
        tbl = sql.rsplit("FROM ", 1)[-1].strip()
        self.calls.append(tbl)
        if tbl in self.raise_tables:
            raise sqlite3.OperationalError("simulated: database is locked (round585 test)")
        return _Cur({"m": self.values.get(tbl, 0)})


class _CConn:
    """C 절용 — UPDATE 문의 대상 테이블·파라미터를 기록만 한다."""

    def __init__(self):
        self.calls = []

    def execute(self, sql, params=()):
        tbl = sql.split()[1]
        self.calls.append((tbl, params[0] if params else None))
        return _Cur({})


def run_a(section_text, raise_for, values, verbose=False):
    conn = _AConn(raise_for, values)
    ns = {"conn": conn, "sqlite3": sqlite3, "verbose": verbose,
          "_empty": "SENTINEL_NOT_TOUCHED"}
    exec(compile(textwrap.dedent(section_text), "<secA>", "exec"), ns)
    return ns.get("_used"), ns.get("_why"), ns.get("_empty"), conn.calls


def run_b(section_text, raise_tables, values):
    conn = _BConn(raise_tables, values)
    ns = {"conn": conn, "sqlite3": sqlite3, "DEMO_TABLES": list(DB.DEMO_TABLES)}
    exec(compile(textwrap.dedent(section_text), "<secB>", "exec"), ns)
    return ns.get("_base"), conn.calls


def run_c(section_text, base):
    conn = _CConn()
    ns = {"conn": conn, "sqlite3": sqlite3, "DEMO_TABLES": list(DB.DEMO_TABLES),
          "_base": dict(base)}
    exec(compile(textwrap.dedent(section_text), "<secC>", "exec"), ns)
    return conn.calls


CASES_SQL = "SELECT COUNT(*) n FROM cases"
PARTNERS_SQL = "SELECT COUNT(*) n FROM partners"
GOLIVE_SQL = "SELECT COUNT(*) n FROM settings WHERE key='go_live_at'"

# --- A: 정상 경로(회귀 없음) ---------------------------------------------
used, why, empty, calls = run_a(SEC_A_NOW, raise_for=(), values={CASES_SQL: 97})
chk(used == 97 and empty is False and calls == [CASES_SQL],
    "★★ A(정상) — 사건 97건 조회 성공 → 즉시 _used=97·_empty=False(1회 조회로 중단)",
    (used, empty, calls))

used, why, empty, calls = run_a(SEC_A_NOW, raise_for=(),
                                 values={CASES_SQL: 0, PARTNERS_SQL: 0, GOLIVE_SQL: 0})
chk(used == 0 and empty == "SENTINEL_NOT_TOUCHED",
    "★★ A(정상) — 세 신호 전부 조회 성공·전부 0(진짜 빈 DB) → 게이트가 안 막는다(회귀 없음)",
    (used, empty))

# --- A: 조회 실패 시나리오 -------------------------------------------------
used, why, empty, calls = run_a(SEC_A_NOW, raise_for={CASES_SQL},
                                 values={PARTNERS_SQL: 400})
chk(used == 1 and empty is False and calls == [CASES_SQL],
    "★★★★★ A(신규) — 첫 조회가 실패하면 나머지를 보지도 않고 즉시 막는다"
    "(진짜 증거 400 이 있어도 그걸 보러 가지 않음을 calls 로 확인)", (used, empty, calls))

used_all, why_all, empty_all, calls_all = run_a(
    SEC_A_NOW, raise_for={CASES_SQL, PARTNERS_SQL, GOLIVE_SQL}, values={})
chk(used_all == 1 and empty_all is False,
    "★★★★★ A(신규) — 세 조회가 전부 실패해도(완전한 판정불가) 안전 쪽(막음)으로 떨어진다",
    (used_all, empty_all))

# ============================================================
print("\n[3] 되돌리기-증명 — A 절: 조회 실패 시 옛 '_n=0' 폴백으로 재구성")
# ------------------------------------------------------------
i_a = SEC_A_NOW.index("            except sqlite3.Error as e:")
j_a = SEC_A_NOW.index("\n            if _n:")
chk(i_a > 0 and j_a > i_a, "(준비) A 절에서 except 블록 경계를 찾았다")
OLD_BLOCK_A = "            except sqlite3.Error:\n                _n = 0"
SEC_A_OLD = SEC_A_NOW[:i_a] + OLD_BLOCK_A + SEC_A_NOW[j_a:]
chk("_used, _why = 1," not in SEC_A_OLD and "_n = 0" in SEC_A_OLD,
    "(준비) 되돌린 A 절에 새 수정이 없고 옛 패턴만 있다")
#  ⚠ SEC_A_OLD 는 SEC_A_NOW 보다 짧다(옛 except 블록이 더 짧아서) — 뒷부분을
#    같은 인덱스 j_a 로 비교하면 안 되고, 각자 자기 except 블록 바로 뒤부터
#    비교해야 한다(둘 다 SEC_A_NOW[j_a:] 를 그대로 이어붙였으므로 실제로 동일해야 함).
chk(SEC_A_OLD[:i_a] == SEC_A_NOW[:i_a]
    and SEC_A_OLD[i_a + len(OLD_BLOCK_A):] == SEC_A_NOW[j_a:],
    "★★ (준비) 되돌린 A 절은 except 블록 한 곳만 다르고 앞뒤는 지금 절과 "
    "완전히 같다(과잉수정 방지 확인)")

used_old, why_old, empty_old, calls_old = run_a(
    SEC_A_OLD, raise_for={CASES_SQL, PARTNERS_SQL, GOLIVE_SQL}, values={})
chk(used_old == 0 and empty_old == "SENTINEL_NOT_TOUCHED"
    and calls_old == [CASES_SQL, PARTNERS_SQL, GOLIVE_SQL],
    "★★★★★ 되돌린(옛) A 절은 세 조회가 전부 실패해도 세 번 다 '넘어가' _used=0 로 "
    "남는다 — 실사건 97건이 있어도 못 막았을 것(0→1 이 이 수정의 인과효과)",
    (used_old, empty_old, calls_old))

# ============================================================
print("\n[4] 실행/되돌리기-증명 — B·C 절: _base 스냅샷 실패 → 표시 루프 연동")
# ------------------------------------------------------------
#  "cases" 표의 MAX(id) 조회만 실패(잠금)한다고 가정 — 그 표에는 실제로 기존 행
#  (id=50)이 있는데 조회 실패로 그 사실을 모르는 상태.
base_new, calls_b_new = run_b(SEC_B_NOW, raise_tables={"cases"},
                               values={t: 0 for t in DB.DEMO_TABLES if t != "cases"})
chk(base_new["cases"] is None,
    "★★★ B(신규) — 조회 실패한 표는 0 이 아니라 None 으로 남는다", base_new.get("cases"))
chk(all(base_new[t] == 0 for t in DB.DEMO_TABLES if t != "cases"),
    "  나머지 표는 정상적으로 실제 값을 받는다(회귀 없음)")

calls_c_new = run_c(SEC_C_NOW, base_new)
chk(("cases", None) not in calls_c_new and not any(t == "cases" for t, _ in calls_c_new),
    "★★★★★ C(신규) — 기준을 못 구한 'cases' 표는 UPDATE 자체를 안 쏜다"
    "(기존 id=50 행이 안전)", calls_c_new)
chk(any(t == "settlements" for t, _ in calls_c_new),
    "  기준이 있는 다른 표는 평소대로 UPDATE 를 쏜다(회귀 없음)")

#  되돌리기 — B 절 except 만 옛 '_base[_t] = 0' 으로 재구성
i_b = SEC_B_NOW.index("        except sqlite3.Error:")
SEC_B_OLD = SEC_B_NOW[:i_b] + "        except sqlite3.Error:\n            _base[_t] = 0"
chk("_base[_t] = 0" in SEC_B_OLD and "_base[_t] = None" not in SEC_B_OLD,
    "(준비) 되돌린 B 절에 옛 패턴만 있다")

base_old, calls_b_old = run_b(SEC_B_OLD, raise_tables={"cases"},
                               values={t: 0 for t in DB.DEMO_TABLES if t != "cases"})
chk(base_old["cases"] == 0,
    "★★ 되돌린(옛) B 절은 조회 실패한 표에 0 을 남긴다(옛 동작 재현)", base_old.get("cases"))

#  옛 _base(cases=0)를 지금 C 절(표시 루프)에 흘려도, 옛 시절엔 C 절도 무가드였다 —
#  가드 없는 C 절(옛)을 만들어 실제로 UPDATE 가 나가는지까지 확인한다.
_skip_guard = ("        if _base.get(t) is None:\n"
               "            continue  # [라운드585] 시드 전 기준 id 를 못 구한 표 — 표시를 건너뛴다\n")
chk(_skip_guard in SEC_C_NOW, "(준비) C 절에서 스킵 가드 원문을 찾았다")
SEC_C_OLD = SEC_C_NOW.replace(_skip_guard, "", 1)
chk("if _base.get(t) is None" not in SEC_C_OLD, "(준비) 되돌린 C 절에 새 가드가 없다")

calls_c_old = run_c(SEC_C_OLD, base_old)
chk(("cases", 0) in calls_c_old,
    "★★★★★ 되돌린(옛) B+C 절 조합 — 조회가 실패했던 'cases' 표에 실제로 "
    "'UPDATE cases ... WHERE id > 0' 이 나간다(기존 id=50 행까지 데모로 표시됐을 것) "
    "— 지금 버전은 이 호출 자체가 사라짐(있음→없음 이 이 수정의 인과효과)", calls_c_old)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
