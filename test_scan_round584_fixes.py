# -*- coding: utf-8 -*-
"""스캔 584라운드 회귀 — manage.py cmd_check() 의 "자리표시자를 '기재됨'으로 읽지
   않는다"(법정 고지 placeholder 점검) 절을 감싼 바깥 `except Exception: pass` 가,
   company_info.json 이 있는데 못 읽는 경우(깨진 JSON 등)를 조용히 삼켜 ok·warn·bad
   무엇도 안 찍히던 결함(직접조사, 하위위임 없음).

   조사 각도 — [라운드583]이 cmd_check() 안의 "3-2) 외부 공개 주소" 절에서 고친
   바로 그 결함 유형("이 파일이 스스로 하는 약속을 실제로 끝까지 지키는가")을,
   그 절이 세운 관례가 **같은 함수의 다른 형제 절에도 다 퍼졌는지** 확인하는
   방향으로 한 겹 더 따라갔다. cmd_check() 안에 남아 있던 `except Exception:
   pass` 를 전수 확인한 결과, 782~800행("법정 고지 자리표시자" 점검)이 여전히
   이 패턴이었다 — [라운드583]이 고친 절의 바로 다음다음 절인데도 놓쳐 있었다.

   실제 영향 — 이 절은 스스로 밝히는 이유(786행 위 주석)대로, `data/company_info.json`
   에 값은 채워졌지만 DEPLOY.md 예시 블록을 그대로 붙여넣은 자리표시자
   ("○○클라우드"·"예시"·"TBD" 등)가 남아 있으면 전자상거래법 표시의무 위반을
   잡아내는 최후 방어선이다(legal_docs.PENDING 은 값이 **비어 있을 때만** 잡으므로
   이 점검과 서로 겹치지 않는, 독자적인 방어). 그런데 파일이 있는데 못 읽으면
   (깨진 JSON, 쓰기 도중 잠금·경합, set-info 저장 중 크래시로 인한 손상 등)
   `_json.load(f)` 가 JSONDecodeError 를, `_cd.items()` 가(최상위가 dict 가 아니면)
   AttributeError 를 던지는데 둘 다 안쪽에 그걸 잡는 코드가 없어 그대로 바깥
   `except Exception: pass` 로 올라가 조용히 사라진다 — bad/warn 어느 것도 안 찍혀,
   이 점검이 이번 실행에서 돌았는지조차 알 수 없는 채로 "배포 가능" 판정에 도달한다.

   형제 대조 — 같은 파일(legal_docs.py)의 _load_info() 는 [라운드121]에서 이미
   똑같은 이유로 고쳐졌다: "파일이 있는데 못 읽는 경우까지 '아직 설정 안 함'과
   똑같이 조용히 삼켰다"(그 파일 63~68행 주석) — 지금은 실패 시 `_log.warning()`
   으로 이유를 남긴다. manage.py 자신도 [라운드583]이 3-2 절에서 "형제 관례를
   따른다"며 `except Exception as e: warn(f"...{type(e).__name__}: {e}");
   warns += 1` 형태로 통일했다. 이 절만 그 관례 확산 이전 형태(pass)로 남아 있었다.

   고침 — manage.py 799행 부근, `except Exception:\n        pass` 를 3-2 절
   (574행)과 같은 형식의 `except Exception as e: warn(f"법정 고지 자리표시자
   점검을 하지 못했습니다 — {type(e).__name__}: {e}"); warns += 1` 로 교체했다.
   try 블록 안의 기존 세 갈래(파일 없음=조용히 통과·자리표시자 없음=조용히 통과·
   자리표시자 있음=bad+fails 증가)는 한 글자도 안 건드렸다.

   검증 — [1] 소스 확인(옛 패턴 소멸 + 새 except 가 warn()+warns 증가를 실제로
   쓴다 + 기존 세 갈래 문자열 보존). [2] 실행 — manage.py 실제 소스 문자열에서
   이 절만 그대로 오려내(on-disk 파일은 절대 안 건드림, 마커 기준 슬라이스라
   다음 라운드가 이 절을 옮겨도 자동으로 따라간다) 지금 버전을 exec() 해:
   (a) 깨진 JSON → warn() 정확히 1회·warns+1·fails 그대로(고치기 전엔 0회였다는
   것을 [3]이 대조), (b) 최상위가 dict 아님(JSON 배열) → AttributeError 도 같은
   except 가 잡아 warn() 1회(단일 예외타입에 과적합되지 않았음을 확인), (c) 파일
   없음 → 회귀 없이 그대로 침묵, (d) 정상 값(자리표시자 없음) → 회귀 없이 침묵,
   (e) 자리표시자 있는 값 → 회귀 없이 기존 bad()+fails 증가 그대로. [3] 되돌리기-
   증명 — 고치기 전 그대로 재구성한 절(바깥 except 만 pass, 나머지 한 글자도 안
   바꿈 — 문자열 대조로 과잉수정 방지까지 확인)을 같은 (a) 시나리오로 실행해
   실제로 호출이 0번임을 실측 대조한다.

       python test_scan_round584_fixes.py
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
print("  스캔 584라운드 회귀 — manage.py cmd_check() 법정 고지 자리표시자 절의")
print("  바깥 except Exception: pass 가 깨진 JSON 등을 삼켜 침묵하던 결함")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
SECTION_NOW = extract_section(SRC, "자리표시자를 '기재됨'으로", "# 6) [B4]")

chk("except Exception:\n        pass" not in SECTION_NOW,
    "★★★ 이 절 안에 옛 `except Exception: pass` 패턴이 더 이상 없다")
chk("    except Exception as e:" in SECTION_NOW
    and 'warn(f"법정 고지 자리표시자 점검을 하지 못했습니다' in SECTION_NOW,
    "★★★ 바깥 except 가 형제 관례(3-2 절)대로 warn()+타입·메시지를 실제로 찍는다")
chk("warns += 1" in SECTION_NOW.rsplit("except Exception as e:", 1)[-1],
    "★★ 그 except 블록이 warns 카운터도 함께 늘린다(경고로 집계된다)")
# 기존 세 갈래(파일없음 침묵/자리표시자없음 침묵/자리표시자있음 bad)는 안 건드렸는지 확인
for anchor in ("if os.path.exists(_ci):", "if _hit:",
               "법정 고지에 **자리표시자가 그대로** 남아 있습니다"):
    chk(anchor in SECTION_NOW, f"★ 기존 로직 문구 보존 확인: {anchor[:24]}…")


# ============================================================
print("\n[2] 실행 — 현재 on-disk manage.py 에서 이 절만 오려내 exec()")
# ------------------------------------------------------------
def run_section(section_text, file_content):
    """자리표시자 절 텍스트를 그대로 exec() 하고 ok/warn/bad 호출·fails/warns 를
    반환한다. 실제 디스크는 건드리지 않고 company_info.json 하나만 흉내낸다.
    file_content=None 이면 '파일 없음'(os.path.exists 가 False)을 흉내낸다."""
    calls = []
    ns = {
        "os": os,
        "HERE": r"C:\__scratch_nonexistent_round584__",
        "ok": lambda m: calls.append(("ok", m)),
        "warn": lambda m: calls.append(("warn", m)),
        "bad": lambda m: calls.append(("bad", m)),
        "fails": 0,
        "warns": 0,
    }
    old_exists = os.path.exists
    old_builtin_open = builtins.open

    def fake_exists(p):
        if isinstance(p, str) and p.endswith("company_info.json"):
            return file_content is not None
        return old_exists(p)

    def fake_open(p, *a, **kw):
        if isinstance(p, str) and p.endswith("company_info.json"):
            return io.StringIO(file_content)
        return old_builtin_open(p, *a, **kw)

    os.path.exists = fake_exists
    builtins.open = fake_open
    try:
        exec(compile(textwrap.dedent(section_text), "<section584>", "exec"), ns)
    finally:
        builtins.open = old_builtin_open
        os.path.exists = old_exists
    return calls, ns["fails"], ns["warns"]


calls_a, fails_a, warns_a = run_section(SECTION_NOW, "{not valid json")
chk(len(calls_a) == 1 and calls_a[0][0] == "warn",
    "★★★★★ (a) 깨진 JSON → warn() 정확히 1회(고치기 전엔 0회 — [3] 대조)", calls_a)
chk(warns_a == 1 and fails_a == 0, "★★★ (a) warns 만 1 늘고 fails 는 안 늘어난다",
    (fails_a, warns_a))

calls_b, fails_b, warns_b = run_section(SECTION_NOW, "[1, 2, 3]")
chk(len(calls_b) == 1 and calls_b[0][0] == "warn",
    "★★★ (b) 최상위가 dict 아님(AttributeError) → 같은 except 가 warn() 1회"
    "(단일 예외타입 과적합이 아님을 확인)", calls_b)
chk(warns_b == 1 and fails_b == 0, "★★ (b) warns 만 1 늘고 fails 는 안 늘어난다",
    (fails_b, warns_b))

calls_c, fails_c, warns_c = run_section(SECTION_NOW, None)
chk(calls_c == [] and fails_c == 0 and warns_c == 0,
    "★★ (c) 파일 없음 → 회귀 없이 그대로 침묵(설정 전 정상 상태)", calls_c)

calls_d, fails_d, warns_d = run_section(SECTION_NOW, '{"hosting": "네이버클라우드"}')
chk(calls_d == [] and fails_d == 0 and warns_d == 0,
    "★★ (d) 정상 값(자리표시자 없음) → 회귀 없이 그대로 침묵", calls_d)

calls_e, fails_e, warns_e = run_section(SECTION_NOW, '{"hosting": "OO클라우드"}')
chk(len(calls_e) == 1 and calls_e[0][0] == "bad" and fails_e == 1 and warns_e == 0,
    "★★★ (e) 자리표시자 있는 값 → 회귀 없이 기존 bad()+fails 증가 그대로", calls_e)


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

calls_old, fails_old, warns_old = run_section(SECTION_OLD, "{not valid json")
chk(calls_old == [] and fails_old == 0 and warns_old == 0,
    "★★★★★ 되돌린(고치기 전) 절로 같은 시나리오(깨진 JSON)를 실행하면 "
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
