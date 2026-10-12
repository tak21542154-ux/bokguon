# -*- coding: utf-8 -*-
"""스캔 583라운드 회귀 — manage.py cmd_check() 의 "3-2) 외부 공개 주소" 자가점검을
   감싸는 바깥 `except Exception: pass` 가, 안쪽에서 OSError 가 아닌 예외(전형적으로
   BOKGUON_PORT 가 숫자가 아닐 때 int(_port) 가 던지는 ValueError)를 조용히 삼켜
   ok·warn·bad 무엇도 안 찍히던 결함(직접조사, 하위위임 없음).

   조사 각도 — [라운드581]이 바로 이 3-2 절의 `elif _pub:` 항등식을 고치며 남긴
   원칙("이유 없는 건너뜀은 통과처럼 읽힌다")을 "이 파일이 스스로 하는 약속을
   실제로 끝까지 지키는가"로 한 겹 더 따라가 봤다. `if _pub:` 안쪽(596행)의
   `try: ... except OSError:` 는 "서버가 안 떠 있다"만 잡도록 **의도적으로**
   좁게 설계돼 있다(주석: "서버가 안 떠 있는 것은 별도 항목이 본다. 여기서 두 번
   울리지 않는다") — 그런데 그 바깥을 감싼 578행의 try 전체가 `except Exception:
   pass` 로 끝나 있어, OSError 가 아닌 예외(가장 현실적인 예: BOKGUON_PORT 가
   공백·주석 등으로 오염돼 int(_port) 가 ValueError; 그 밖에도 public_host.txt 가
   utf-8-sig 로 못 여는 인코딩이면 UnicodeDecodeError 등)가 나면 안쪽 try 를
   그대로 통과해 바깥 except 에 잡히고, 아무 메시지도 없이 사라진다. 직접 실행으로
   재현(아래 [2])했다 — BOKGUON_PORT="abc" 로 두면 지금 파일(고치기 전)은 ok/warn/
   bad 호출이 **0번**이었다.

   실제 영향 — 이 절은 주석이 스스로 밝히는 2026-08-06 실제 운영 사고(재시작 후
   허용 Host 목록이 옛 값으로 남아 외부 요청이 전부 400 — 로컬 점검은 통과해 몇
   시간 동안 몰랐다) 재발 방지용이다. 892행 `if fails: ... else: 배포 가능`
   판정은 fails/warns 개수만 보므로, 이 절이 통째로 조용히 건너뛰어도 "배포 가능"
   출력에는 그 사실이 전혀 안 남는다 — [라운드581]이 고친 바로 그 실패 모드가,
   고친 절을 감싼 한 겹 바깥 예외처리에 그대로 남아 있었다.

   형제 대조 — 같은 함수 안 다른 모든 "확인 불가" 지점(263·361·384·492·889행)은
   전부 `except Exception as e: warn(f"...{e}"); warns += 1` 형태로 이유를 알린다.
   이 절의 바깥 except 만 `pass` 로 그 관례를 벗어나 있었다.

   고침 — manage.py 630행 부근, `except Exception: pass` 를 형제(특히 바로 앞
   492행 공종 커버리지 점검)와 같은 형식의
   `except Exception as e: warn(f"외부 공개 주소 확인을 하지 못했습니다 — "
   f"{type(e).__name__}: {e}"); warns += 1` 로 교체했다. `if _pub:`/`else:` 안의
   기존 세 분기(400 차단·정상 응답·서버 미기동·hostfile 없음)는 전혀 안 건드렸다.

   검증 — [1] 소스 확인(옛 `except Exception:\n        pass` 패턴 소멸 + 새
   except 가 warn()+warns 증가를 쓴다). [2] 실행 — manage.py 실제 소스 문자열에서
   "3-2)" 절만 그대로 오려내(on-disk 파일은 절대 안 건드림, 마커 기준 슬라이스라
   다음 라운드가 이 절을 옮겨도 자동으로 따라간다) 지금 버전을 exec() 해:
   (a) BOKGUON_PORT="abc" → warn() 정확히 1회·warns+1·fails 그대로(고치기 전엔
   0회였다는 것을 [3]이 대조), (b) hostfile 없음 → [라운드581] 분기 회귀 없이
   그대로 warn() 1회, (c) 정상 포트인데 그 포트에 아무도 안 듣는다(연결거부) →
   기존 "서버 미기동" ok() 분기 회귀 없이 그대로 유지. [3] 되돌리기-증명 — 고치기
   전 그대로 재구성한 절(바깥 except 만 pass) 을 같은 (a) 시나리오로 실행해 실제로
   호출이 0번임을 실측 대조한다.

       python test_scan_round583_fixes.py
"""
import builtins
import io
import os
import sys
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


SRC = read("manage.py")


def extract_section(src, start_needle, end_needle):
    """줄 단위로 온전히 잘라낸다 — 첫 줄도 나머지 줄과 같은 들여쓰기를 유지해야
    textwrap.dedent() 로 최상위 exec() 가능한 코드가 되기 때문(부분 문자열 index()
    로만 자르면 첫 줄만 들여쓰기가 없어져 IndentationError 가 난다)."""
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
print("  스캔 583라운드 회귀 — manage.py cmd_check() 외부공개주소 절의")
print("  바깥 except Exception: pass 가 ValueError 등을 삼켜 침묵하던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
SECTION_NOW = extract_section(SRC, "3-2) 외부 공개 주소", "# 4) 법정 게시물 미기재 항목")

chk("except Exception:\n        pass" not in SECTION_NOW,
    "★★★ 3-2 절 안에 옛 `except Exception: pass` 패턴이 더 이상 없다")
chk('except Exception as e:\n        #' in SECTION_NOW
    and 'warn(f"외부 공개 주소 확인을 하지 못했습니다' in SECTION_NOW,
    "★★★ 바깥 except 가 형제 관례대로 warn()+타입·메시지를 실제로 찍는다")
chk("warns += 1" in SECTION_NOW.rsplit("except Exception as e:", 1)[-1],
    "★★ 그 except 블록이 warns 카운터도 함께 늘린다(경고로 집계된다)")
# 기존 세 분기(400차단/정상응답/서버미기동)는 안 건드렸는지 확인
for anchor in ("허용 Host 목록이 어긋났습니다", "서버 미기동 — Host 통과 여부는 확인 못 함",
               "logs/public_host.txt 에 기록된 공개 주소가 없어"):
    chk(anchor in SECTION_NOW, f"★ 기존 분기 문구 보존 확인: {anchor[:20]}…")


# ============================================================
print("\n[2] 실행 — 현재 on-disk manage.py 에서 3-2 절만 오려내 exec()")
# ------------------------------------------------------------
def run_section(section_text, env_overrides, hostfile_lines):
    """3-2 절 텍스트를 그대로 exec() 하고 ok/warn/bad 호출·fails/warns 를 반환.
    실제 os.environ·디스크는 건드리지 않고 최소한으로만 흉내낸다."""
    calls = []
    ns = {
        "os": os,
        "HERE": r"C:\__scratch_nonexistent_round583__",
        "ok": lambda m: calls.append(("ok", m)),
        "warn": lambda m: calls.append(("warn", m)),
        "bad": lambda m: calls.append(("bad", m)),
        "fails": 0,
        "warns": 0,
    }
    old_env = dict(os.environ)
    old_exists = os.path.exists
    old_builtin_open = builtins.open
    try:
        os.environ.clear()
        os.environ.update(env_overrides)

        def fake_exists(p):
            if isinstance(p, str) and p.endswith("public_host.txt"):
                return hostfile_lines is not None
            return old_exists(p)

        def fake_open(p, *a, **kw):
            if isinstance(p, str) and p.endswith("public_host.txt"):
                return io.StringIO("\n".join(hostfile_lines or []))
            return old_builtin_open(p, *a, **kw)

        os.path.exists = fake_exists
        builtins.open = fake_open
        try:
            exec(compile(textwrap.dedent(section_text), "<section583>", "exec"), ns)
        finally:
            builtins.open = old_builtin_open
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        os.path.exists = old_exists
    return calls, ns["fails"], ns["warns"]


calls, fails, warns = run_section(SECTION_NOW, {"BOKGUON_PORT": "abc"}, ["example.com"])
chk(len(calls) == 1 and calls[0][0] == "warn",
    "★★★★★ (a) BOKGUON_PORT 오염(int 불가) → warn() 정확히 1회(고치기 전엔 0회 — [3] 대조)",
    calls)
chk(warns == 1 and fails == 0, "★★★ (a) warns 만 1 늘고 fails 는 안 늘어난다", (fails, warns))

calls_b, _, _ = run_section(SECTION_NOW, {"BOKGUON_PORT": "8771"}, None)
chk(len(calls_b) == 1 and calls_b[0][0] == "warn"
    and "기록된 공개 주소가 없어" in calls_b[0][1],
    "★★ (b) hostfile 없음 → [라운드581] 분기 회귀 없이 warn() 1회", calls_b)

calls_c, _, _ = run_section(SECTION_NOW, {"BOKGUON_PORT": "1"}, ["example.com"])
chk(len(calls_c) == 1 and calls_c[0][0] == "ok",
    "★★ (c) 정상 포트·서버 미기동(연결거부) → 기존 ok() 분기 회귀 없이 유지", calls_c)


# ============================================================
print("\n[3] 되돌리기-증명 — 고치기 전(바깥 except 만 pass) 재구성 대조")
# ------------------------------------------------------------
#  on-disk manage.py 는 안 건드린다 — 지금 절 텍스트에서 바깥 except 부분만
#  고치기 전 그대로 재구성한다(그 외 한 글자도 안 바꾼다 — 과잉수정 방지 확인 포함).
NEW_EXCEPT_TAIL = SECTION_NOW[SECTION_NOW.index("    except Exception as e:"):]
chk(NEW_EXCEPT_TAIL.lstrip().startswith("except Exception as e:"),
    "★ (준비) 새 except 블록 앵커를 찾았다")

SECTION_OLD = (SECTION_NOW[:SECTION_NOW.index("    except Exception as e:")]
               + "    except Exception:\n        pass\n")
chk("except Exception:\n        pass" in SECTION_OLD,
    "★ (준비) 되돌린 절에 옛 패턴이 실제로 들어갔다")
chk(SECTION_OLD.replace("    except Exception:\n        pass\n", "")
    == SECTION_NOW.replace(NEW_EXCEPT_TAIL, ""),
    "★★ (준비) 되돌린 절은 바깥 except 한 곳만 다르고 나머지는 지금 절과 완전히 같다"
    "(과잉수정 방지 확인)")

calls_old, fails_old, warns_old = run_section(SECTION_OLD, {"BOKGUON_PORT": "abc"}, ["example.com"])
chk(calls_old == [] and fails_old == 0 and warns_old == 0,
    "★★★★★ 되돌린(고치기 전) 절로 같은 시나리오(BOKGUON_PORT=\"abc\")를 실행하면 "
    "실제로 ok/warn/bad 호출이 0번이다 — 지금 버전의 '경고 1회'가 이 되돌리기 대비 "
    "실측 차이(0 → 1)로 인과관계가 증명된다", calls_old)

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
