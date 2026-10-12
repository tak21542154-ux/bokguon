# -*- coding: utf-8 -*-
"""스캔 677라운드 회귀(직접조사, 하위위임 없음) — 운영 콘솔(static/admin.js)의
   statusPill()이 하자(defects) 상태값 '확인중'·'재시공배정' 색상 매핑을
   통째로 빠뜨리고 있던 결함.

   조사 배경 — round644/672가 이미 세운 전제를 그대로 이어받는다: 상태값→색상
   매핑은 이 저장소에 사실상 세 형제로 존재한다.
     · templates/insurer_portal.html  stTag(s)      (보험사 포털)
     · templates/partner_portal.html  stTag(s)      (시행사·시공사 포털)
     · static/admin.js                statusPill(s) (운영 콘솔)
   round75가 '취소', round644가 '시공중', round672가 정산(settlements)의
   '이체예약'·'승인'을 세 매핑에 맞췄다 — 그런데 round672 자신의 회귀테스트도
   "그 라운드가 늘린 딱 그 두 키"만 검증했을 뿐, 하자(defects) 상태값
   DEFECT_FLOW(app.py — ["접수","확인중","재시공배정","완료","반려"])를 세
   매핑 전체와 대조하는 전수 점검은 이번이 처음이다.

   실측(직접 조사) —
     · app.py DEFECT_FLOW의 다섯 값 중 '확인중'·'재시공배정' 두 개가
       static/admin.js의 statusPill() 매핑에 **키 자체가 없었다**.
     · templates/insurer_portal.html stTag()·templates/partner_portal.html
       stTag() 둘 다 이미 '확인중':'blue'·'재시공배정':'amber'를 갖고 있다 —
       round672와 정반대 방향의 불일치다(그때는 보험사 포털만 빠졌는데,
       이번엔 운영 콘솔만 빠졌다).
     · static/admin.js 자신도 3801행 부근에 같은 DEFECT_FLOW 상수를 그대로
       복사해 두고 있고(app.py와 값 일치), defectAct 버튼(3996~3999행)이
       data-arg2="확인중"/"재시공배정"을 실제로 보낸다 — 이 값들이 도달
       불가능한 이론상의 상태가 아니라 이 파일 자신이 이미 알고 다루는 매일
       쓰는 상태값임을 이 파일 스스로 증명한다.
     · 실제 소비처는 하자 목록(舊 3860행 `<td>${statusPill(d.status)}</td>`)과
       하자 상세 모달(舊 3974행 `현재 상태 → statusPill(d.status)`) 두 곳 —
       매핑에 없으면 이 함수 자신의 기본값(회색)으로 떨어져(159행 자신의
       주석: "새로 생긴 상태가 매핑에 없으면 전부 회색으로 뭉개진다") '확인중'·
       '재시공배정'이 '완료'·'반려'·'접수'·'대기'·'미수선종결'·'중지'와 전부
       똑같은 회색 pill로 보였다 — 운영자가 하자 목록만 훑어서는 "지금
       진행 중인 하자"(확인중=파랑·재시공배정=주황이어야 정상)와 "이미 끝난
       하자"(완료·반려=회색)를 색으로 구분할 수 없었다.

   ⚠ 부수 발견(이번 라운드에서는 고치지 않음 — round678 핸드오프) —
     test_template_js.py는 `<script[^>]*>(.*?)</script>` 정규식으로 각
     템플릿의 **인라인** 스크립트만 추출한다. templates/admin.html은
     static/admin.js를 `<script src="{{ asset('admin.js') }}"></script>`로
     **외부 파일 참조**만 하므로(내용이 태그 사이에 없다), 이 정규식은 그
     자리에서 빈 문자열만 얻어 필터링돼 admin.js의 실제 소스는 이 테스트가
     "9/9 통과"로 찍어도 **단 한 번도 node --check 를 통과한 적이 없다**
     (leaflet.js·actions.js·lightbox.js·addrpick.js 도 같은 사각지대).
     안전규칙 문서가 "static/admin.js 를 건드리면 test_template_js.py 를
     재실행하라"고 적어 둔 것과 실제 커버리지가 어긋난다 — 이 라운드는 그
     대신 admin.js를 `node --check`로 직접 파싱해 검증한다(아래 [1]).

   고침 — static/admin.js의 statusPill() 매핑에 '확인중':'blue'·
   '재시공배정':'amber'를 추가해 형제 stTag() 둘과 맞춘다(단일 지점 수정,
   다른 키는 무변경). templates/*.html은 무변경이라 build_pages.py 재실행
   대상 아님. test_template_js.py(9/9)·test_scan_round306_fixes.py(11/11)
   표준 재검증 완료(위 사각지대 때문에 이번엔 node --check 를 별도로 더한다).

   회귀테스트(이 파일) —
   [1] 소스 — admin.js를 node --check로 직접 파싱(위 사각지대를 이 라운드가
       메운다), 세 매핑에서 '확인중'·'재시공배정' 값을 직접 뽑아 셋 다 일치함을
       확인, 이번 수정이 세 매핑의 공통집합을 정확히 이 두 개만큼 늘렸는지
       자기완결적으로 검증(round672와 같은 기법, 매직넘버 없음), admin.js
       자신의 DEFECT_FLOW 상수가 app.py의 DEFECT_FLOW와 값이 일치하는지,
       실제 호출부(statusPill(d.status))가 최소 2곳 있는지 확인한다.
   [2] 단위 — 세 함수 정의를 파일에서 그대로 잘라내(손으로 다시 타이핑하지
       않음) Node.js로 실제 실행해 '확인중'·'재시공배정'의 색상 클래스가 세
       곳 모두 일치함을 실측(기존 값들은 회귀 없이 그대로임도 같이 확인).
   [3] 종단 — 스크래치 DB + 실제 Flask 라우트로 하자 한 건을 만들어
       PATCH /api/defects/<id>로 '접수'→'확인중'→'재시공배정'을 실제로
       전이시키고, GET /api/defects(운영 콘솔이 그대로 쓰는 응답)가 그
       리터럴 문자열을 그대로 돌려줌을 실측한다(화면이 statusPill()에
       넘기는 값이 정확히 이 문자열임을 증명).
   [4] 되돌리기 — [2]에서 잘라낸 (지금 고친) admin statusPill 소스 문자열
       안에서만 두 키를 제거한 옛 버전을 독립 Node 스크립트로 만들어(실제
       파일은 전혀 건드리지 않음), 그 옛 버전이 실제로 형제 stTag() 둘과
       다른 색(회색)을 냈음을 재현 실측한다.

       python test_scan_round677_fixes.py
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


def func_src_brace(src, header):
    """round644/672와 같은 경계 찾기 — header부터 그 뒤 처음 나오는 '줄 첫머리
    단독 닫는 중괄호'(\\n})까지. stTag/statusPill은 내부에 중첩 블록이 없다."""
    i = src.find(header)
    if i < 0:
        return ""
    j = src.find("\n}", i + len(header))
    return src[i:j + 2] if j >= 0 else ""


print("=" * 72)
print("  스캔 677라운드 회귀 — admin.js statusPill() '확인중'·'재시공배정' 색상 누락")
print("=" * 72)

INSURER_SRC = read("templates/insurer_portal.html")
PARTNER_SRC = read("templates/partner_portal.html")
ADMIN_SRC = read("static/admin.js")
APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인 — admin.js 문법 + 세 매핑 대조 + DEFECT_FLOW 일치 + 실제 호출부")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")

if NODE:
    r = subprocess.run([NODE, "--check", os.path.join(HERE, "static", "admin.js")],
                        capture_output=True, text=True,
                        encoding="utf-8", errors="replace")
    chk(r.returncode == 0,
        "★★★★★ static/admin.js가 node --check로 직접 파싱된다(test_template_js.py는 "
        "<script src=...> 외부참조라 이 파일을 실제로는 검사하지 못하는 사각지대 — "
        "round678 핸드오프 참고, 아래 대신 이 라운드가 직접 확인한다)",
        (r.stderr or "")[:300])

STTAG_INSURER = func_src_brace(INSURER_SRC, "function stTag(s){")
STTAG_PARTNER = func_src_brace(PARTNER_SRC, "function stTag(s){")
PILL_ADMIN = func_src_brace(ADMIN_SRC, "function statusPill(s){")
chk(bool(STTAG_INSURER) and bool(STTAG_PARTNER) and bool(PILL_ADMIN),
    "  세 함수 소스를 실제 파일에서 전부 잘라냈다",
    f"len={len(STTAG_INSURER)}/{len(STTAG_PARTNER)}/{len(PILL_ADMIN)}")


def _color_in(body, s):
    m = re.search(re.escape(f"'{s}':") + r"'([a-z]+)'", body)
    return m.group(1) if m else None


for key, expect in (("확인중", "blue"), ("재시공배정", "amber")):
    c_i = _color_in(STTAG_INSURER, key)
    c_p = _color_in(STTAG_PARTNER, key)
    c_a = _color_in(PILL_ADMIN, key)
    chk(c_a == expect,
        f"★★★★★ admin.js statusPill()의 '{key}'가 이제 '{expect}'다(고치기 전엔 키 자체가 없어 gray)",
        f"실제 값: {c_a!r}")
    chk(c_i == expect,
        f"  (회귀 없음) insurer_portal.html stTag()의 '{key}'는 원래부터 '{expect}'다", f"실제 값: {c_i!r}")
    chk(c_p == expect,
        f"  (회귀 없음) partner_portal.html stTag()의 '{key}'는 원래부터 '{expect}'다", f"실제 값: {c_p!r}")
    chk(c_i == c_p == c_a,
        f"★★★★★ 세 매핑의 '{key}' 색이 완전히 일치한다(형제 함수 동기화 완료)",
        f"insurer={c_i!r} partner={c_p!r} admin={c_a!r}")

# 이번 수정이 다른 겹치는 값을 건드리지 않았는지 확인 — round672와 같은 기법으로
# "이번 수정이 공통집합을 정확히 두 개만 늘렸는가"만 자기완결적으로 검증한다.
_insurer_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", STTAG_INSURER))
_partner_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", STTAG_PARTNER))
_admin_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", PILL_ADMIN))
_admin_keys_before = _admin_keys - {"확인중", "재시공배정"}
_common_before = _insurer_keys & _partner_keys & _admin_keys_before
_common_after = _insurer_keys & _partner_keys & _admin_keys
chk(_common_after == _common_before | {"확인중", "재시공배정"},
    "★★★★ 이번 수정이 세 매핑의 공통집합을 정확히 '확인중'·'재시공배정' 두 개만큼 늘렸다"
    "(다른 키는 안 건드림)", f"before={sorted(_common_before)} after={sorted(_common_after)}")
chk(len(_common_after) == len(_common_before) + 2,
    "  공통집합 크기가 정확히 2 증가했다", f"{len(_common_before)} → {len(_common_after)}")
_mismatch = []
for s in sorted(_common_after):
    vals = {_color_in(STTAG_INSURER, s), _color_in(STTAG_PARTNER, s), _color_in(PILL_ADMIN, s)}
    if len(vals) != 1:
        _mismatch.append((s, _color_in(STTAG_INSURER, s), _color_in(STTAG_PARTNER, s), _color_in(PILL_ADMIN, s)))
chk(not _mismatch,
    f"  (회귀 없음) 공통 상태값 {len(_common_after)}개 전부 세 매핑이 일치한다(확인중·재시공배정 포함)",
    str(_mismatch))

# DEFECT_FLOW 자체가 app.py와 admin.js 사이에 값이 같은지(다섯 값 전부) — 매핑
# 색만 맞추고 정작 상태 이름 집합 자체가 갈리면 아무 의미가 없다.
m = re.search(r"DEFECT_FLOW\s*=\s*\[([^\]]*)\]", APP_SRC)
chk(bool(m), "  app.py에서 DEFECT_FLOW 정의를 실제로 찾았다")
APP_DEFECT_FLOW = set(re.findall(r"[가-힣]+", m.group(1))) if m else set()
m2 = re.search(r"const DEFECT_FLOW\s*=\s*\[([^\]]*)\]", ADMIN_SRC)
chk(bool(m2), "  admin.js에서 DEFECT_FLOW 정의를 실제로 찾았다")
ADMIN_DEFECT_FLOW = set(re.findall(r"[가-힣]+", m2.group(1))) if m2 else set()
chk(APP_DEFECT_FLOW == ADMIN_DEFECT_FLOW == {"접수", "확인중", "재시공배정", "완료", "반려"},
    "★★★★ app.py DEFECT_FLOW와 admin.js DEFECT_FLOW가 다섯 값 모두 일치한다"
    "(매핑이 다루는 상태 집합 자체는 이미 올발랐다 — 색만 두 개 빠졌었다)",
    f"app={sorted(APP_DEFECT_FLOW)} admin={sorted(ADMIN_DEFECT_FLOW)}")

# 실제 호출 지점 — 이 두 값이 죽은 매핑이 아니라 실제로 쓰인다는 증거.
chk(ADMIN_SRC.count("statusPill(d.status)") >= 2,
    "  admin.js가 실제로 statusPill(d.status)를 2곳 이상에서 호출한다"
    "(하자 목록 '상태' 칸 + 하자 상세 모달 '현재 상태' 칸)")
chk('data-arg2="확인중"' in ADMIN_SRC and 'data-arg2="재시공배정"' in ADMIN_SRC,
    "  (전제) admin.js 자신의 defectAct 버튼이 이 두 상태값을 실제로 서버에 보낸다"
    "(도달 불가능한 이론상의 값이 아니다)")

# ============================================================
print("\n[2] 단위 — 세 함수를 파일에서 그대로 잘라내 Node.js로 직접 실행")
# ------------------------------------------------------------
ESC_LINE = re.search(r"const esc = s =>.*?;\n", PARTNER_SRC).group(0)
chk(ESC_LINE in INSURER_SRC and ESC_LINE in ADMIN_SRC,
    "  (전제) esc() 헬퍼가 세 파일에서 바이트 단위로 동일하다(그대로 재사용 가능)")

# 이름이 같은 stTag()가 둘이라 한 스크립트에 같이 넣으려면 식별자만 바꾼다.
# 몸통(상태→색 매핑·return 문)은 한 글자도 바꾸지 않는다.
STTAG_INSURER_R = STTAG_INSURER.replace("function stTag(s){", "function stTagInsurer(s){", 1)
STTAG_PARTNER_R = STTAG_PARTNER.replace("function stTag(s){", "function stTagPartner(s){", 1)
chk(STTAG_INSURER_R != STTAG_INSURER and STTAG_INSURER_R.count("stTagInsurer") == 1,
    "  (harness) insurer 함수명만 바꿨다(본문은 그대로)")
chk(STTAG_PARTNER_R != STTAG_PARTNER and STTAG_PARTNER_R.count("stTagPartner") == 1,
    "  (harness) partner 함수명만 바꿨다(본문은 그대로)")

_scratch = tempfile.mkdtemp(prefix="round677_node_")


def run_node_probe(pill_admin_src, label,
                    statuses=("확인중", "재시공배정", "이체예약", "완료", "접수", "시공중")):
    """세 함수를 한 Node 스크립트에 모아 지정한 상태값들을 넣고 실행한다."""
    script = (
        ESC_LINE + "\n"
        + STTAG_INSURER_R + "\n\n"
        + STTAG_PARTNER_R + "\n\n"
        + pill_admin_src + "\n\n"
        + "const statuses = " + json.dumps(list(statuses), ensure_ascii=False) + ";\n"
        + "const out = {};\n"
        + "for (const s of statuses) { out[s] = {"
        + "insurer: stTagInsurer(s), partner: stTagPartner(s), admin: statusPill(s)}; }\n"
        + "console.log(JSON.stringify(out));\n"
    )
    p = os.path.join(_scratch, f"probe_{len(os.listdir(_scratch))}.js")
    io.open(p, "w", encoding="utf-8").write(script)
    r = subprocess.run([NODE, p], capture_output=True, text=True, encoding="utf-8", timeout=15)
    if r.returncode != 0:
        chk(False, f"  {label} Node 실행 실패", (r.stderr or "")[:300])
        return None
    try:
        return json.loads(r.stdout.strip())
    except Exception as e:
        chk(False, f"  {label} Node 출력 파싱 실패", f"{e}: {r.stdout[:200]}")
        return None


def cls_of(html):
    m = re.search(r'class="(?:tag|pill) ([a-z]+)"', html)
    return m.group(1) if m else None


if NODE:
    out_new = run_node_probe(PILL_ADMIN, "[지금 고친 버전]")
    chk(out_new is not None, "  Node로 지금 버전(고친 뒤) 세 함수를 실제 실행했다", str(out_new))
    if out_new:
        EXPECT = {"확인중": "blue", "재시공배정": "amber", "이체예약": "amber",
                  "완료": "gray", "접수": "gray", "시공중": "green"}
        for s, expect in EXPECT.items():
            g_i, g_p, g_a = (cls_of(out_new[s][k]) for k in ("insurer", "partner", "admin"))
            star = "★★★★★★" if s in ("확인중", "재시공배정") else "  (회귀 없음)"
            chk(g_i == expect and g_p == expect and g_a == expect,
                f"{star} 실제 실행 결과 — 상태 '{s}' → 세 함수 모두 '{expect}' 클래스",
                f"insurer={g_i} partner={g_p} admin={g_a}")

    # ============================================================
    print("\n[3] 종단 — 스크래치 DB + 실제 Flask 라우트로 하자 상태를 실제로 전이시킨다")
    # ------------------------------------------------------------
    _tmpdir = tempfile.mkdtemp(prefix="round677_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
    os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    sys.path.insert(0, HERE)

    import db as DB  # noqa: E402
    DB.init_db()
    import app as A  # noqa: E402

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('r677admin','x','검증','중간관리자')")
    did = conn.execute(
        "INSERT INTO defects(defect_no, case_no, title, severity, status, created_at) "
        "VALUES(?,?,?,?,?,?)",
        ("R677-D1", "R677-CASE-A", "테스트 하자(회귀용)", "보통", "접수", DB.now())).lastrowid
    conn.commit()
    conn.close()

    admin = A.app.test_client()
    _tok = "r677-admin-csrf"
    with admin.session_transaction() as sess:
        sess["admin"] = "r677admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
        sess["_csrf"] = _tok
    _hdr = {"X-CSRF-Token": _tok}

    r1 = admin.patch(f"/api/defects/{did}", headers=_hdr, json={"status": "확인중"})
    chk(r1.status_code == 200 and (r1.get_json() or {}).get("ok"),
        "  (b) PATCH /api/defects/<id> — '접수'→'확인중' 전이가 실제로 성공했다(200)",
        (r1.status_code, r1.get_json()))

    r_list1 = admin.get("/api/defects")
    chk(r_list1.status_code == 200, "  GET /api/defects 준비 확인 — 200", r_list1.status_code)
    row1 = next((x for x in (r_list1.get_json() or []) if x.get("id") == did), None)
    chk(row1 is not None and row1.get("status") == "확인중",
        "★★★★★★ (b) 운영 콘솔이 그대로 쓰는 GET /api/defects 응답이 status='확인중'을 "
        "리터럴 그대로 내려준다(화면이 statusPill()에 넘기는 값이 정확히 이 문자열임을 실측)",
        row1)

    r2 = admin.patch(f"/api/defects/{did}", headers=_hdr, json={"status": "재시공배정"})
    chk(r2.status_code == 200 and (r2.get_json() or {}).get("ok"),
        "  (b) PATCH /api/defects/<id> — '확인중'→'재시공배정' 전이가 실제로 성공했다(200)",
        (r2.status_code, r2.get_json()))

    r_list2 = admin.get("/api/defects")
    row2 = next((x for x in (r_list2.get_json() or []) if x.get("id") == did), None)
    chk(row2 is not None and row2.get("status") == "재시공배정",
        "★★★★★★ (b) 같은 응답이 상태 전이 뒤 status='재시공배정'도 리터럴 그대로 내려준다",
        row2)

    # ============================================================
    print("\n[4] 되돌리기 — 잘라낸 (고친) 소스 문자열 안에서만 두 키를 제거해 재현")
    #      ⚠ 실제 파일은 전혀 건드리지 않는다.
    # ------------------------------------------------------------
    OLD_ADMIN = PILL_ADMIN.replace("'확인중':'blue','재시공배정':'amber',", "")
    chk(OLD_ADMIN != PILL_ADMIN
        and "'확인중':'blue'" not in OLD_ADMIN and "'재시공배정':'amber'" not in OLD_ADMIN,
        "  (전제) 되돌린 사본에서 두 키:값 쌍이 실제로 사라졌다(실제 파일은 무변경)")

    out_old = run_node_probe(OLD_ADMIN, "[되돌린 옛 버전]")
    chk(out_old is not None, "  Node로 옛 버전(고치기 전 재현) 세 함수를 실제 실행했다", str(out_old))
    if out_old:
        og_a_ck = cls_of(out_old["확인중"]["admin"])
        og_a_rb = cls_of(out_old["재시공배정"]["admin"])
        og_i_ck, og_p_ck = cls_of(out_old["확인중"]["insurer"]), cls_of(out_old["확인중"]["partner"])
        og_i_rb, og_p_rb = cls_of(out_old["재시공배정"]["insurer"]), cls_of(out_old["재시공배정"]["partner"])
        chk(og_a_ck == "gray" and og_a_rb == "gray",
            "★★★★★★ (인과관계 실측) 옛 코드라면 운영 콘솔은 '확인중'·'재시공배정' 둘 다 "
            "회색(매핑에 없어 기본값)이었다", f"확인중={og_a_ck} 재시공배정={og_a_rb}")
        chk(og_i_ck == "blue" and og_p_ck == "blue" and og_i_rb == "amber" and og_p_rb == "amber",
            "★★★★★★ (인과관계 실측) 같은 옛 코드에서도 보험사·시행사 포털은 이미 올바른 "
            "색(파랑/주황)을 냈다 — 즉 운영 콘솔만 다른 색을 말하는 불일치가 실제로 재현된다"
            "(위 [2]의 지금 결과와 정반대 = 이번 수정이 실제로 이 불일치를 없앤 것)",
            f"insurer=({og_i_ck},{og_i_rb}) partner=({og_p_ck},{og_p_rb})")

    # 실제 파일이 여전히 고친 상태 그대로인지 마지막으로 재확인(회귀 없음).
    chk("'확인중':'blue','재시공배정':'amber'" in read("static/admin.js"),
        "  (sanity) 실제 파일(디스크)은 여전히 고친 상태 그대로다(위 [4]는 메모리 문자열만 다뤘다)")
else:
    chk(False, "  [2]~[4] node가 없어 건너뛸 수밖에 없었다")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    - {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
