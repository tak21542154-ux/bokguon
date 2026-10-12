# -*- coding: utf-8 -*-
"""스캔 484라운드 회귀 — email과 짝인 RE_PHONE(5437행, 지금까지 공개폼
clean_public_form 단 한 곳에만 쓰였다) 형식검사가 12개 형제 경로 전부에
빠져 있던 결함(정밀조사 Agent가 발견 — 482·483라운드의 '형제경로
전수대조' 방법론을 email→phone 축으로 확장).

  형식이 깨진 연락처가 어디로 심기든 notify_popbill.normalize_phone()이
  휴대전화 형식만 통과시키므로(모바일 전용 설계) 오타·쓰레기값이 "번호
  없음"과 구분이 안 돼, _notify_phone()을 거치는 모든 알림(경매 마감임박·
  낙찰승인·완료보고 독촉·피해자 진행조회 안내 등)이 영원히 조용한 실패로
  빠진다 — 담당자는 "번호가 원래 없나 보다"라고만 여기게 된다.

  12곳: ①api_partner_profile_update ②api_insurer_profile_update
  ③api_application_create ④api_partner_create ⑤api_insurer_create
  ⑥api_partner_update ⑦api_insurer_update ⑧api_contact_update
  ⑨api_contact_import(엑셀 일괄등록) ⑩_create_case(공유헬퍼, 피해자
  연락처) ⑪api_case_create ⑫api_case_edit.

  고침: 각 지점이 이미 쓰는 RE_EMAIL 검사와 정확히 같은 관례로 이식
  (조건·conn.close 유무·raise vs jsonify 등 그 함수 자신의 기존 스타일을
  그대로 따름 — 예: _create_case는 CaseInputError를 던지는 관례라 그대로,
  api_contact_import는 스킵+보고 관례라 그대로).

  [1] 소스 확인 — 12곳 모두 새 RE_PHONE 검사 블록이 실제로 있음.
  [2] 실제 Flask 서브프로세스(서브프로세스 워커) 실행 — 12곳 전부에
      형식이 깨진 연락처("전화아님")를 실제 HTTP/직접호출로 보내 정확한
      거부 문구를 확인, 정상 연락처("010-1234-5678")는 통과함도 확인.
  [3] 되돌림-증명 — 12곳의 새 블록을 전부 동시에 제거해도(각 블록은
      독립적으로 삽입된 자기완결 텍스트라 제거만으로 원본이 복원됨)
      원본과 바이트단위로 같아짐을 자체 검증한 뒤, 그 되돌린 코드로
      서브프로세스를 다시 돌려 12곳 전부가 형식이 깨진 연락처를 그대로
      통과시키는 옛 동작이 재현되는지 한 번에 대조.

  ⚠⚠ [라운드626] 이전 버전은 [3]에서 app.py 실제 파일을
  io.open(APP_PATH,"w").write(reverted_src) 로 디스크에 직접 썼다가
  finally 에서 원본으로 복원했다 — 이제는 워커(test_scan_round484_worker.py)
  가 R484_BROKEN=1 환경변수를 보고 그 서브프로세스 **안에서만** 인메모리로
  11곳(기법1, view_functions 스왑)+1곳(기법3, 공유헬퍼 _create_case 실모듈
  __dict__ 직접 patch)을 되돌린다. app.py 실제 파일은 이 프로세스에서도
  워커 서브프로세스에서도 전혀 안 쓴다.
"""
import io
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


print("=" * 72)
print("  스캔 484라운드 회귀 — 12개 형제 경로의 RE_PHONE 형식검사 누락")
print("=" * 72)

APP_PATH = os.path.join(HERE, "app.py")
APP_SRC = io.open(APP_PATH, encoding="utf-8").read()


def extract(src, start_marker, end_marker):
    a = src.find(start_marker)
    if a < 0:
        return ""
    e = src.find(end_marker, a)
    return src[a:e] if e > 0 else ""


SITES = [
    ("① api_partner_profile_update",
     "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE(5437행)이 12개 형제 경로",
     "            #  ⚠ [라운드80] RE_EMAIL 검사가 관리자 쪽 연락처 수정에만 있고 협력사\n"),
    ("② api_insurer_profile_update",
     "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 없었다(협력사 자기",
     "            #  ⚠ [라운드80] RE_EMAIL 검사가 관리자 쪽 연락처 수정에만 있고 보험사\n"),
    ("③ api_application_create",
     "    #  ⚠⚠ [라운드484] 형제(clean_public_form)는 RE_PHONE 으로 연락처 형식도",
     "    #  ⚠ [라운드80] 공개 폼(clean_public_form)은 RE_EMAIL 로 형식을 보는데\n"),
    ("④ api_partner_create",
     "    #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 직접등록엔 없었다.\n",
     "    #  ⚠ [라운드80] RE_EMAIL 검사가 연락처 수정에만 있고 이 직접등록엔 없었다"),
    ("⑤ api_insurer_create",
     "    #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 보험사 직접등록엔 없었다.\n",
     "    conn = DB.get_db()\n"),
    ("⑥ api_partner_update",
     "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다 —\n",
     "            #  ⚠ [라운드80] RE_EMAIL 검사가 연락처 수정(/api/contacts"),
    ("⑦ api_insurer_update",
     "            #  ⚠⚠ [라운드484] email과 짝인 RE_PHONE 검사가 이 자리엔 없었다.\n",
     "            v = _s(d[f], _R169_LIMITS[f]) if f in _R169_LIMITS else d[f]\n"),
    ("⑧ api_contact_update",
     "            #  ⚠⚠ [라운드484] email·email2와 짝인 RE_PHONE 검사가 이 자리엔 없었다.\n",
     "            if f in (\"email\", \"email2\") and v and not RE_EMAIL.match(v):\n"),
    ("⑨ api_contact_import",
     "                        #  ⚠⚠ [라운드484] email·email2와 짝인 RE_PHONE 검사가\n",
     "                        sets.append(f\"{field}=?\"); vals.append(v[:120])\n"),
    ("⑩ _create_case",
     "    #  ⚠⚠ [라운드484] partners·insurers.phone과 같은 결함",
     "    if _vn or _vp:\n"),
    ("⑪ api_case_create",
     "    #  ⚠⚠ [라운드484] 형제(_create_case)와 같은 결함 — RE_PHONE 검사가 없어\n",
     "    if _vn or _vp:\n"),
    ("⑫ api_case_edit",
     "            #  ⚠⚠ [라운드484] 형제(_create_case·api_case_create)와 같은 결함 —\n",
     "            sets.append(f\"{f}=?\"); vals.append(nv)\n"),
]

print("\n[1] 소스 확인 — 12곳 모두 새 RE_PHONE 블록이 있는가")
NEW_BLOCKS = {}
for label, start, end in SITES:
    block = extract(APP_SRC, start, end)
    NEW_BLOCKS[label] = block
    chk(bool(block) and "RE_PHONE.match" in block,
        f"{label} — 새 RE_PHONE 검사 블록을 찾았다", "블록을 못 뽑음" if not block else "")
    chk(APP_SRC.count(block) == 1 if block else False,
        f"{label} — 되돌림-증명에 쓸 블록이 소스에 정확히 1번만 있다",
        APP_SRC.count(block) if block else "")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실제 Flask 서브프로세스 — 12곳 전부 형식오류 거부 + 정상값 통과 확인")
# ──────────────────────────────────────────────────────────────
WORKER = os.path.join(HERE, "test_scan_round484_worker.py")


def _run_worker(broken=False):
    """broken=True 면 워커 서브프로세스 **안에서** 12곳을 되돌린 버전으로
    바꿔치기하고 실행한다(R484_BROKEN 환경변수로 트리거) — 실제 app.py
    파일은 이 프로세스에서도 저 서브프로세스에서도 전혀 안 건드린다."""
    env = dict(os.environ)
    if broken:
        env["R484_BROKEN"] = "1"
    r = subprocess.run([sys.executable, "-u", WORKER], capture_output=True,
                        text=True, encoding="utf-8", timeout=60, env=env)
    if r.returncode != 0:
        raise RuntimeError(f"워커 실행 실패(rc={r.returncode}): {r.stdout}\n{r.stderr}")
    return json.loads(r.stdout.strip().splitlines()[-1])


# (label, bad_status_key, bad_body_key, expected_substring_in_error, good_status_key or None)
CHECKS = [
    ("① partner_profile", "partner_profile_bad", "partner_profile_bad_body", "연락처 형식", None),
    ("② insurer_profile", "insurer_profile_bad", "insurer_profile_bad_body", "연락처 형식", None),
    ("③ application_create", "application_create_bad", "application_create_bad_body", "연락처 형식", None),
    ("④ partner_create", "partner_create_bad", "partner_create_bad_body", "연락처 형식", "partner_create_good"),
    ("⑤ insurer_create", "insurer_create_bad", "insurer_create_bad_body", "연락처 형식", "insurer_create_good"),
    ("⑥ partner_update", "partner_update_bad", "partner_update_bad_body", "연락처 형식", None),
    ("⑦ insurer_update", "insurer_update_bad", "insurer_update_bad_body", "연락처 형식", None),
    ("⑧ contact_update", "contact_update_bad", "contact_update_bad_body", "연락처 형식", None),
    ("⑩ _create_case(포털)", "insurer_case_create_bad", "insurer_case_create_body", "피해자 연락처 형식", None),
    ("⑪ case_create", "case_create_bad", "case_create_body", "피해자 연락처 형식", None),
    ("⑫ case_edit", "case_edit_bad", "case_edit_bad_body", "피해자 연락처 형식", None),
]

try:
    fixed = _run_worker()
    for label, bk, bbk, needle, gk in CHECKS:
        chk(fixed.get(bk) == 400 and needle in (fixed.get(bbk) or {}).get("error", ""),
            f"★★★★★ {label} — 형식이 깨진 연락처는 400으로 거부되고 문구도 정확하다",
            fixed.get(bbk))
        if gk:
            chk(fixed.get(gk) == 200, f"{label} — 정상 연락처는 통과한다(과잉차단 아님)", fixed.get(gk))
    # ⑨ contact_import — 스킵+보고 관례(하드 400 아님)
    imp = fixed.get("contact_import_body") or {}
    chk(fixed.get("contact_import_status") == 200 and imp.get("skipped_invalid") == 1
        and any("연락처 형식" in e for e in imp.get("errors", [])),
        "★★★★★ ⑨ contact_import — 형식이 깨진 연락처는 해당 행만 스킵되고 보고된다"
        "(엑셀 일괄등록의 기존 관례 그대로)", imp)

    # (B) 되돌림 — 워커 서브프로세스 **안에서만** 12곳을 인메모리로 되돌려
    #     재실행(R484_BROKEN=1) — 실제 app.py 파일은 안 건드림
    print("\n[3] 되돌림-증명 — 12곳 전부 동시 되돌림(워커 안, 인메모리) 후 재현")
    for label, block in NEW_BLOCKS.items():
        assert block, f"{label} 블록을 못 뽑아 되돌림-증명을 진행할 수 없다"
    broken = _run_worker(broken=True)
    for label, bk, bbk, needle, gk in CHECKS:
        chk(broken.get(bk) == 200,
            f"★★★★★ {label} — 옛 코드(되돌림)는 형식이 깨진 연락처도 200으로 통과시킨다"
            " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", broken.get(bk))
    imp2 = broken.get("contact_import_body") or {}
    chk(broken.get("contact_import_status") == 200 and imp2.get("skipped_invalid") == 0
        and imp2.get("updated") == 1,
        "★★★★★ ⑨ contact_import — 옛 코드(되돌림)는 형식이 깨진 연락처를 그대로 저장한다"
        " — 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명", imp2)

except Exception as e:                                              # noqa: BLE001
    chk(False, "[2]+[3] 실행/되돌림-증명", f"{type(e).__name__}: {e}")

chk(io.open(APP_PATH, encoding="utf-8").read() == APP_SRC,
    "★★★★★ app.py는 이 검증 내내 디스크에 전혀 쓰이지 않았다(원본과 동일)")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
print("=" * 72)
if FAIL:
    print("\n실패 상세:")
    for name, detail in FAIL:
        print(f"  - {name}: {detail}")
sys.exit(1 if FAIL else 0)
