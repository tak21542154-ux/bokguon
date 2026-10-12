# -*- coding: utf-8 -*-
"""스캔 81라운드 회귀 — 엑셀 내보내기 제목 셀 2곳에 _xl_safe 누락(가용성, 500).

  _xl_safe() 는 "엑셀 내보내기 어디서든 같은 규칙을 쓴다"는 목적으로 만든 모듈
  전역 헬퍼인데, 두 함수의 **본문 행**은 이미 이 헬퍼를 거치면서(주석에 "여기만
  빠져 있었다"고 스스로 적어 뒀다) 바로 위 **제목 셀**은 같은 함수 안에서도
  빠뜨렸다.

  ① api_ops_kpi_export — 제목의 period label 이 ?from=/?to= 쿼리스트링을
     그대로 이어붙인 값이라, 제어문자가 섞이면 openpyxl 이
     IllegalCharacterError 로 내보내기 전체를 500 으로 만든다.
  ② api_insurer_report_export — 제목에 insurers.name 이 낀다. 이 값은 등록
     때(관리자가 붙여넣기로 입력) 제어문자 정제 없이 그대로 저장되고 이후
     아무도(보험사 자기수정도, 관리자수정도) 못 고친다 — 형제 명세서는 이미
     _xl_safe 를 거치는데 이 리포트만 빠져, 제어문자 하나가 그 보험사의 이
     리포트를 영구히 못 받게 만든다(사외로 나가는 산출물).

      python test_scan_round81_fixes.py
"""
import io
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("═" * 72)
print("  스캔 81라운드 회귀 — 엑셀 내보내기 제목 셀 _xl_safe 누락 2곳")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
kpi_body = _py_fn_body(APP_SRC, "api_ops_kpi_export")
chk('ws.append([_xl_safe(f"복구온 운영 KPI' in kpi_body,
    "★★ ① api_ops_kpi_export 의 제목 셀이 _xl_safe 를 거친다")

rpt_body = _py_fn_body(APP_SRC, "api_insurer_report_export")
chk("ws.append([_xl_safe(f\"복구온 절감 리포트" in rpt_body,
    "★★ ② api_insurer_report_export 의 제목 셀이 _xl_safe 를 거친다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — 실서버 경로(Flask test_client + 임시 DB)로 실제 재현")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round81_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    #  ⚠ 제어문자는 반드시 실제 서버 로직(요청 파싱 → SQL → 라벨 조합 → 엑셀 저장)을
    #    다 태워서 검사한다 — 파이썬 문자열을 직접 만들어 openpyxl 에 넣으면
    #    _compute_ops_kpi/등록 라우트가 자체적으로 걸러내는지는 증명하지 못한다.
    VTAB = "\x0b"   # 수직탭 — openpyxl 이 IllegalCharacterError 로 거부하는 제어문자

    conn = DB.get_db()
    conn.execute("INSERT INTO admins(username,password_hash,name,role) "
                 "VALUES('admin','x','검증','중간관리자')")
    iid = conn.execute(
        "INSERT INTO insurers(name) VALUES(?)", (f"R81보험{VTAB}사",)).lastrowid
    conn.commit()
    conn.close()

    # ── ① api_ops_kpi_export — 쿼리스트링에 낀 제어문자 ──
    admin = A.app.test_client()
    with admin.session_transaction() as sess:
        sess["admin"] = "admin"; sess["admin_role"] = "중간관리자"; sess["admin_name"] = "검증"
    r1 = admin.get("/api/ops-kpi/export?from=2026-01-01%0B&to=")
    #  ⚠ 성공 응답은 xlsx(zip) 바이너리라 텍스트로 디코딩하면 그 자체로 깨진다 —
    #    실패했을 때만(보통 JSON 에러) 본문을 보여준다.
    _d1 = "" if r1.status_code == 200 else r1.get_data(as_text=True)[:300]
    chk(r1.status_code == 200,
        "★★★ ① 조건문에 제어문자가 섞여도 운영 KPI 엑셀 내보내기가 500 대신 "
        "정상 파일을 낸다(고치기 전엔 IllegalCharacterError 로 500이 났다)",
        f"{r1.status_code} {_d1}")
    chk(r1.status_code == 200
        and r1.headers.get("Content-Type", "").startswith(
            "application/vnd.openxmlformats"),
        "STEP 응답이 실제 xlsx 컨텐트타입이다(에러 JSON이 아니다)",
        r1.headers.get("Content-Type"))

    # ── ② api_insurer_report_export — 기관명에 낀 제어문자 ──
    insurer_client = A.app.test_client()
    with insurer_client.session_transaction() as sess:
        sess["insurer_id"] = iid
    r2 = insurer_client.get("/api/insurer/report/export")
    _d2 = "" if r2.status_code == 200 else r2.get_data(as_text=True)[:300]
    chk(r2.status_code == 200,
        "★★★ ② 기관명에 제어문자가 섞여 있어도 보험사 절감 리포트 내보내기가 "
        "500 대신 정상 파일을 낸다(고치기 전엔 그 보험사가 이 리포트를 영원히 "
        "못 받았다)",
        f"{r2.status_code} {_d2}")
    chk(r2.status_code == 200
        and r2.headers.get("Content-Type", "").startswith(
            "application/vnd.openxmlformats"),
        "STEP 응답이 실제 xlsx 컨텐트타입이다(에러 JSON이 아니다)",
        r2.headers.get("Content-Type"))

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드81 서버측 준비/실행", f"{type(e).__name__} {e}")
finally:
    os.environ.pop("BOKGUON_DB_PATH", None)
    os.environ.pop("BOKGUON_UPLOAD_DIR", None)
    os.environ.pop("BOKGUON_ENV", None)
    os.environ.pop("BOKGUON_SEED_DEMO", None)
    shutil.rmtree(_tmpdir, ignore_errors=True)

print("\n" + "═" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("═" * 72)
sys.exit(1 if FAIL else 0)
