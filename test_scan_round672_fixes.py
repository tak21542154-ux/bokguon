# -*- coding: utf-8 -*-
"""스캔 672라운드 회귀(직접조사, 하위위임 없음) — 보험사 포털 stTag()에 정산
   (settlements) 상태 '이체예약'·'승인'의 색상 매핑이 통째로 빠져 있던 결함.

   조사 배경 — round644가 이미 세운 전제를 그대로 이어받는다: 상태값→색상
   매핑은 이 저장소에 사실상 세 형제로 존재한다.
     · templates/insurer_portal.html  stTag(s)      (보험사 포털)
     · templates/partner_portal.html  stTag(s)      (시행사·시공사 포털)
     · static/admin.js                statusPill(s) (운영 콘솔)
   round75가 '취소'를, round644가 '시공중'을 세 매핑에 맞춰 놓았고, round644
   자신의 주석은 "세 매핑 중 겹치는 17개 상태값을 전수 대조"했다고 적어
   두었다 — 그런데 그 전수 대조는 **그 시점에 세 매핑 모두에 이미 존재하던
   키**만 비교했다. 정산 흐름(insurer_portal.html 1619행 주석: "①공사 완료
   승인 → ②복구온 계좌 입금 → ③복구온 입금 확인·더블 체크 → ④수수료 공제
   후 시행사 지급")의 ③단계에서 쓰는 두 상태값 '이체예약'(transfer_status)·
   '승인'(review_status)은 애초에 insurer_portal.html의 stTag() 매핑에
   **키 자체가 없었다** — round644의 대조 대상에 들지 못했을 뿐 처음부터
   빠져 있었다.

   실측(직접 조사) —
     · static/admin.js statusPill()는 이미 '이체예약':'amber'·'승인':'green'을
       갖고 있고, 실제로 statusPill(s.review_status)·statusPill(st.transfer_status)·
       statusPill(l.transfer_status)로 정산 화면 세 곳(2064·3419·5236행)에 쓴다.
     · templates/partner_portal.html stTag()도 이미 두 값을 갖고 있고,
       stTag(sett.transfer_status)(421행 "지급 상태")로 실제로 쓴다.
     · templates/insurer_portal.html stTag()만 두 키가 **없었다** — 그런데
       바로 이 파일이 sett.review_status(965행 "지급 검수")·
       sett.transfer_status(964행 "업체 지급"·1639행 정산 목록)를 stTag()에
       그대로 넘긴다. 매핑에 없으면 이 함수 자신의 기본값(회색)으로 떨어진다
       (335행 자신의 주석: "매핑에 없으면 회색이니 …는 구분돼야 한다"는
       원칙을 정작 이 두 값에는 지키지 못하고 있었다).
     · 운영 DB 읽기전용 조회(2026-09-17): settlements.review_status='승인'인
       행이 지금 21/43건 — 사건 상세를 열 때마다 절반 가까이 "지급 검수:
       승인"이 "대기"와 똑같은 회색 태그로 보인다. transfer_status='이체예약'은
       지금 스냅샷엔 0건이지만, app.py POST /api/settlements/<id>/review
       (api_settlement_review, 15247행)가
           UPDATE settlements SET review_status='승인', transfer_status='이체예약' …
       로 **review_status='승인'과 항상 같은 트랜잭션에서 함께** 찍는 값이라
       (운영팀이 정산 검수를 승인하는 매 순간 생기는 정상 경로) 도달 불가능한
       값이 아니라 관측 시점의 우연일 뿐이다.

   영향 — 보험사가 사건 상세의 "💰 정산" 패널이나 정산 내역 목록에서 지급
   진행 상황을 볼 때, "지급 검수: 승인"·"업체 지급: 이체예약"이 실제로는
   진행 중/완료에 가까운 상태인데도 "대기"와 구분 없는 회색으로 보여
   진행 상황을 오인하게 만든다. 시행사 포털·운영 콘솔에서는 같은 상태가
   올바른 색(초록/주황)으로 보이므로, 같은 사실을 세 화면이 서로 다르게
   말하는 round644와 동일한 성격의 결함이다.

   고침 — templates/insurer_portal.html의 stTag() 매핑에 '이체예약':'amber'·
   '승인':'green'을 추가해 형제 stTag()·statusPill()과 맞춘다(단일 지점
   수정). build_pages.py 재실행 + test_scan_round306_fixes.py(11/11)·
   test_template_js.py(9/9) 표준 재검증 완료.

   회귀테스트(이 파일) —
   [1] 소스 — 세 매핑에서 '이체예약'·'승인' 값을 직접 뽑아 셋 다 일치함을
       확인하고, 세 파일 모두에서 실제 호출 지점(review_status·
       transfer_status를 그대로 넘기는 자리)이 존재함을 확인한다. 또한
       app.py api_settlement_review()가 두 값을 같은 UPDATE 문으로 함께
       찍는다는 것도 소스에서 직접 정규식으로 확인한다(손으로 베끼지 않음).
   [2] 단위 — 세 함수 정의를 파일에서 그대로 잘라내(손으로 다시 타이핑하지
       않음) Node.js로 실제 실행해 stTag('이체예약')·stTag('승인')·
       statusPill(...) 결과 HTML의 색상 클래스가 세 곳 모두 일치함을
       실측 증명한다(기존 값 '대기'·'이체완료'·'시공중'은 회귀 없이 그대로임도
       같이 확인).
   [3] 종단 — (a) 실제 Flask 템플릿 렌더(로그인 세션 없이 render_template
       직접 호출)로 insurer_portal.html을 그려, 서버가 실제로 내보내는
       HTML/JS 안에 고친 매핑이 살아 있는지 확인한다. (b) 스크래치 DB +
       실제 Flask 라우트(GET /api/insurer/cases/<id>/detail,
       GET /api/insurer/dashboard)로 review_status='승인'·
       transfer_status='이체예약'인 정산 행을 실제로 만들고 조회해, 화면이
       stTag()에 넘기는 값이 정확히 이 두 문자열임을 실측한다.
   [4] 되돌리기 — [2]에서 잘라낸 (지금 고친) insurer stTag 소스 문자열
       안에서만 두 키를 제거한 옛 버전을 독립 Node 스크립트로 만들어(실제
       파일은 전혀 건드리지 않음), 그 옛 버전이 실제로 형제 두 함수와 다른
       색(회색)을 냈음을 재현 실측한다.

       python test_scan_round672_fixes.py
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
    """round644과 같은 경계 찾기 — header부터 그 뒤 처음 나오는 '줄 첫머리
    단독 닫는 중괄호'(\\n})까지. stTag/statusPill은 내부에 중첩 블록이 없다."""
    i = src.find(header)
    if i < 0:
        return ""
    j = src.find("\n}", i + len(header))
    return src[i:j + 2] if j >= 0 else ""


def func_src(src, header):
    """round253이 확립한 함수경계 슬라이스 — header부터 다음 '@app.'나
    최상위 'def ' 직전까지(app.py 라우트 함수용)."""
    i = src.find(header)
    if i < 0:
        return ""
    m = re.search(r"\n(?:@app\.|def )", src[i + len(header):])
    return src[i:i + len(header) + m.start()] if m else src[i:]


print("=" * 72)
print("  스캔 672라운드 회귀 — insurer_portal.html stTag() '이체예약'·'승인' 색상 누락")
print("=" * 72)

INSURER_SRC = read("templates/insurer_portal.html")
PARTNER_SRC = read("templates/partner_portal.html")
ADMIN_SRC = read("static/admin.js")
APP_SRC = read("app.py")

# ============================================================
print("\n[1] 소스 확인 — 세 매핑에서 '이체예약'·'승인' 값 직접 대조 + 실제 호출 지점 확인")
# ------------------------------------------------------------
STTAG_INSURER = func_src_brace(INSURER_SRC, "function stTag(s){")
STTAG_PARTNER = func_src_brace(PARTNER_SRC, "function stTag(s){")
PILL_ADMIN = func_src_brace(ADMIN_SRC, "function statusPill(s){")
chk(bool(STTAG_INSURER) and bool(STTAG_PARTNER) and bool(PILL_ADMIN),
    "  세 함수 소스를 실제 파일에서 전부 잘라냈다",
    f"len={len(STTAG_INSURER)}/{len(STTAG_PARTNER)}/{len(PILL_ADMIN)}")


def _color_in(body, s):
    m = re.search(re.escape(f"'{s}':") + r"'([a-z]+)'", body)
    return m.group(1) if m else None


for key, expect in (("이체예약", "amber"), ("승인", "green")):
    c_i = _color_in(STTAG_INSURER, key)
    c_p = _color_in(STTAG_PARTNER, key)
    c_a = _color_in(PILL_ADMIN, key)
    chk(c_i == expect,
        f"★★★★★ insurer_portal.html stTag()의 '{key}'가 이제 '{expect}'다(고치기 전엔 키 자체가 없어 gray)",
        f"실제 값: {c_i!r}")
    chk(c_p == expect,
        f"  (회귀 없음) partner_portal.html stTag()의 '{key}'는 원래부터 '{expect}'다", f"실제 값: {c_p!r}")
    chk(c_a == expect,
        f"  (회귀 없음) admin.js statusPill()의 '{key}'는 원래부터 '{expect}'다", f"실제 값: {c_a!r}")
    chk(c_i == c_p == c_a,
        f"★★★★★ 세 매핑의 '{key}' 색이 완전히 일치한다(형제 함수 동기화 완료)",
        f"insurer={c_i!r} partner={c_p!r} admin={c_a!r}")

# 이번 수정이 다른 겹치는 값을 건드리지 않았는지 확인 — round644가 전수
# 대조한 나머지 상태값들도 여전히 세 곳 모두 일치해야 한다(회귀 없음 보증).
# ⚠ round644가 말한 "그 시점의 17개"를 오늘의 매직넘버로 그대로 가져다 쓰지
#   않는다 — 그 사이 다른 라운드가 무관한 키를 추가·정리했을 수 있어 정확한
#   절대값은 이 라운드의 전제가 아니다. 대신 **이 수정 자체가 공통집합을
#   정확히 두 개 늘렸는가**만 자기완결적으로 검증한다(수정 전 insurer 키
#   집합을 이 두 키만 빼서 직접 재구성 — 손으로 옛 숫자를 베끼지 않는다).
_insurer_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", STTAG_INSURER))
_partner_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", STTAG_PARTNER))
_admin_keys = set(re.findall(r"'([가-힣]+)':'[a-z]+'", PILL_ADMIN))
_insurer_keys_before = _insurer_keys - {"이체예약", "승인"}
_common_before = _insurer_keys_before & _partner_keys & _admin_keys
_common_after = _insurer_keys & _partner_keys & _admin_keys
chk(_common_after == _common_before | {"이체예약", "승인"},
    "★★★★ 이번 수정이 세 매핑의 공통집합을 정확히 '이체예약'·'승인' 두 개만큼 늘렸다"
    "(다른 키는 안 건드림)", f"before={sorted(_common_before)} after={sorted(_common_after)}")
chk(len(_common_after) == len(_common_before) + 2,
    "  공통집합 크기가 정확히 2 증가했다", f"{len(_common_before)} → {len(_common_after)}")
_mismatch = []
for s in sorted(_common_after):
    vals = {_color_in(STTAG_INSURER, s), _color_in(STTAG_PARTNER, s), _color_in(PILL_ADMIN, s)}
    if len(vals) != 1:
        _mismatch.append((s, _color_in(STTAG_INSURER, s), _color_in(STTAG_PARTNER, s), _color_in(PILL_ADMIN, s)))
chk(not _mismatch,
    f"  (회귀 없음) 공통 상태값 {len(_common_after)}개 전부 세 매핑이 일치한다(이체예약·승인 포함)",
    str(_mismatch))

# 실제 호출 지점 — 이 두 값이 죽은 매핑이 아니라 실제로 쓰인다는 증거.
chk("stTag(sett.review_status)" in INSURER_SRC,
    "  insurer_portal.html이 실제로 stTag(sett.review_status)를 호출한다(사건 상세 '지급 검수')")
chk("stTag(sett.transfer_status)" in INSURER_SRC and "stTag(s.transfer_status)" in INSURER_SRC,
    "  insurer_portal.html이 실제로 stTag(sett.transfer_status)·stTag(s.transfer_status)를 "
    "호출한다(사건 상세 '업체 지급' + 정산 목록)")
chk("statusPill(s.review_status)" in ADMIN_SRC and "statusPill(st.transfer_status)" in ADMIN_SRC,
    "  (전제) admin.js도 같은 두 필드를 statusPill()에 그대로 넘긴다(세 형제가 같은 데이터를 그린다)")

# 서버가 실제로 두 값을 같은 트랜잭션에서 함께 찍는다는 구조적 증거.
REVIEW_FN = func_src(APP_SRC, "def api_settlement_review(sid):")
chk(REVIEW_FN != "", "  app.py에서 api_settlement_review() 함수를 실제로 찾았다")
chk("review_status='승인', transfer_status='이체예약'" in REVIEW_FN,
    "★★★★ api_settlement_review()가 review_status='승인'과 transfer_status='이체예약'을 "
    "같은 UPDATE 문으로 함께 찍는다(관측 시점과 무관하게 항상 같이 재현되는 조합)")

# ============================================================
print("\n[2] 단위 — 세 함수를 파일에서 그대로 잘라내 Node.js로 직접 실행")
# ------------------------------------------------------------
NODE = shutil.which("node")
if not NODE:
    chk(False, "node 실행파일을 찾을 수 없다 — 이 구간은 건너뛰지 않고 실패로 답한다")
    NODE = None

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

_scratch = tempfile.mkdtemp(prefix="round672_node_")


def run_node_probe(sttag_insurer_src, label, statuses=("이체예약", "승인", "대기", "이체완료", "시공중")):
    """세 함수를 한 Node 스크립트에 모아 지정한 상태값들을 넣고 실행한다."""
    script = (
        ESC_LINE + "\n"
        + sttag_insurer_src + "\n\n"
        + STTAG_PARTNER_R + "\n\n"
        + PILL_ADMIN + "\n\n"
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
    out_new = run_node_probe(STTAG_INSURER_R, "[지금 고친 버전]")
    chk(out_new is not None, "  Node로 지금 버전(고친 뒤) 세 함수를 실제 실행했다", str(out_new))
    if out_new:
        EXPECT = {"이체예약": "amber", "승인": "green", "대기": "gray",
                  "이체완료": "green", "시공중": "green"}
        for s, expect in EXPECT.items():
            g_i, g_p, g_a = (cls_of(out_new[s][k]) for k in ("insurer", "partner", "admin"))
            star = "★★★★★★" if s in ("이체예약", "승인") else "  (회귀 없음)"
            chk(g_i == expect and g_p == expect and g_a == expect,
                f"{star} 실제 실행 결과 — 상태 '{s}' → 세 함수 모두 '{expect}' 클래스",
                f"insurer={g_i} partner={g_p} admin={g_a}")

    # ============================================================
    print("\n[3] 종단 — (a) 실제 Flask 렌더  (b) 스크래치 DB + 실제 라우트")
    # ------------------------------------------------------------
    _tmpdir = tempfile.mkdtemp(prefix="round672_")
    os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
    os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
    os.environ["BOKGUON_LOG_FILE"] = os.path.join(_tmpdir, "app.log")
    os.environ["BOKGUON_ENV"] = "dev"
    os.environ["BOKGUON_SEED_DEMO"] = "0"
    sys.path.insert(0, HERE)

    import db as DB  # noqa: E402
    DB.init_db()
    import app as A  # noqa: E402
    from flask import render_template  # noqa: E402

    # -- (a) 실제 렌더 파이프라인 --
    with A.app.test_request_context("/insurer"):
        html_insurer = render_template("insurer_portal.html", nonce="testnonce", build="t", ver="t")
    chk("'이체예약':'amber','승인':'green'" in html_insurer,
        "★★★★★ 실제로 렌더된 insurer_portal.html 응답 안에 고친 매핑이 그대로 살아 있다")

    # -- (b) 스크래치 DB에 실제 정산 흐름(review_status=승인·transfer_status=이체예약)을
    #        재현하고, 실제 라우트 두 곳(사건 상세·대시보드)이 그 값을 그대로 내려주는지 확인 --
    conn = DB.get_db()
    iid = conn.execute(
        "INSERT INTO insurers(name, status, is_demo) VALUES (?, '활성', 0)",
        ("R672테스트보험사",)).lastrowid
    cid = conn.execute(
        """INSERT INTO cases(case_no, insurer, insurer_id, category, region, address, status,
                              award_amount, low_price, is_demo, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        ("R672-CASE-A", "R672테스트보험사", iid, "가드레일", "서울", "테스트로 1",
         "정산진행", 5000000, 4800000, 0, DB.now())).lastrowid
    sid = conn.execute(
        """INSERT INTO settlements(case_id, case_no, insurer, partner_name, amount, fee, payout,
                                    insurer_paid, review_status, transfer_status, is_demo, created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (cid, "R672-CASE-A", "R672테스트보험사", "R672테스트업체", 5000000, 500000, 4500000,
         "입금완료", "승인", "이체예약", 0, DB.now())).lastrowid
    conn.commit()
    conn.close()

    client = A.app.test_client()
    with client.session_transaction() as sess:
        sess["insurer_id"] = iid
        sess["insurer_name"] = "R672테스트보험사"

    r_detail = client.get(f"/api/insurer/cases/{cid}/detail")
    chk(r_detail.status_code == 200, "  (b) GET /api/insurer/cases/<id>/detail 준비 확인 — 200",
        r_detail.status_code)
    d_body = r_detail.get_json() or {}
    d_sett = d_body.get("settlement") or {}
    chk(d_sett.get("review_status") == "승인" and d_sett.get("transfer_status") == "이체예약",
        "★★★★★★ (b) 사건 상세 API가 실제로 review_status='승인'·transfer_status='이체예약'을 "
        "그대로 내려준다(화면이 stTag()에 넘기는 값이 정확히 이 문자열임을 실측)", d_sett)

    r_dash = client.get("/api/insurer/dashboard")
    chk(r_dash.status_code == 200, "  (b) GET /api/insurer/dashboard 준비 확인 — 200", r_dash.status_code)
    dash_body = r_dash.get_json() or {}
    dash_sett = next((s for s in (dash_body.get("settlements") or []) if s.get("id") == sid), None)
    chk(dash_sett is not None,
        "  (b) 대시보드 응답(정산 목록)에도 방금 만든 정산 행이 실제로 들어 있다")
    if dash_sett:
        chk(dash_sett.get("review_status") == "승인" and dash_sett.get("transfer_status") == "이체예약",
            "★★★★★ (b) 정산 목록(RENDER.settle이 쓰는 D.settlements)도 같은 원본 값을 "
            "그대로 내려준다(1639행 stTag(s.transfer_status) 호출 지점의 실제 입력값)", dash_sett)

    # ============================================================
    print("\n[4] 되돌리기 — 잘라낸 (고친) 소스 문자열 안에서만 두 키를 제거해 재현")
    #      ⚠ 실제 파일은 전혀 건드리지 않는다.
    # ------------------------------------------------------------
    #  ⚠ "'이체예약'"·"'승인'" 만으로 남아있는지 검사하면 이 파일 자신의 설명
    #    주석(위 334~346행, 조사 배경을 적으며 그 단어를 인용한다) 안의 같은
    #    글자와 헷갈린다 — 반드시 색상 값까지 붙은 "'키':'색'" 패턴으로 확인한다.
    OLD_INSURER_R = STTAG_INSURER_R.replace("'이체예약':'amber','승인':'green',\n    ", "")
    chk(OLD_INSURER_R != STTAG_INSURER_R
        and "'이체예약':'amber'" not in OLD_INSURER_R and "'승인':'green'" not in OLD_INSURER_R,
        "  (전제) 되돌린 사본에서 두 키:값 쌍이 실제로 사라졌다(실제 파일은 무변경 — "
        "설명 주석 속 같은 단어 인용과는 구분해서 확인)")

    out_old = run_node_probe(OLD_INSURER_R, "[되돌린 옛 버전]")
    chk(out_old is not None, "  Node로 옛 버전(고치기 전 재현) 세 함수를 실제 실행했다", str(out_old))
    if out_old:
        og_i_re = cls_of(out_old["이체예약"]["insurer"])
        og_i_sn = cls_of(out_old["승인"]["insurer"])
        og_p_re, og_a_re = cls_of(out_old["이체예약"]["partner"]), cls_of(out_old["이체예약"]["admin"])
        og_p_sn, og_a_sn = cls_of(out_old["승인"]["partner"]), cls_of(out_old["승인"]["admin"])
        chk(og_i_re == "gray" and og_i_sn == "gray",
            "★★★★★★ (인과관계 실측) 옛 코드라면 보험사 포털은 '이체예약'·'승인' 둘 다 "
            "회색(매핑에 없어 기본값)이었다", f"이체예약={og_i_re} 승인={og_i_sn}")
        chk(og_p_re == "amber" and og_a_re == "amber" and og_p_sn == "green" and og_a_sn == "green",
            "★★★★★★ (인과관계 실측) 같은 옛 코드에서도 시행사 포털·운영 콘솔은 이미 올바른 "
            "색(주황/초록)을 냈다 — 즉 보험사 포털만 다른 색을 말하는 불일치가 실제로 재현된다"
            "(위 [2]의 지금 결과와 정반대 = 이번 수정이 실제로 이 불일치를 없앤 것)",
            f"partner=({og_p_re},{og_p_sn}) admin=({og_a_re},{og_a_sn})")

    # 실제 파일이 여전히 고친 상태 그대로인지 마지막으로 재확인(회귀 없음).
    chk("'이체예약':'amber','승인':'green'" in read("templates/insurer_portal.html"),
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
