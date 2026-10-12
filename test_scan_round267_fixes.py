# -*- coding: utf-8 -*-
"""스캔 267라운드 회귀 — collect_emails.py 최초 전면감사 결함 3건
   (이 파일이 라운드265·266에서 "모범 형제 패턴"으로만 인용되고 정작
   주조사대상이 된 적이 없었다는 점을 지적한 정밀조사 Agent가 발견,
   독립 재검증 후 수정. geocode_fill.py에도 같은 결함이 전파돼 있어
   함께 고쳤다).

  [1] refuses_collection() — 공백만 지우고 HTML 태그는 그대로 둬서, §50-2
      수집거부 문구 중간에 인라인 태그(<b>·<span>·<br> 등, 스크롤 애니메이션·
      번역위젯이 흔히 씀) 하나만 끼어도 연속 문자열 매치가 깨져 수집거부
      의사를 놓쳤다(미탐). 태그부터 지우도록 수정.

  [2] main() 루프의 UPDATE·commit이 collect_one() 의 try/except **밖**에
      있어서, 락 경합·디스크 오류 등으로 저장 하나가 실패하면 이미 찾아
      둔 나머지 대상까지 배치 전체가 무방비로 죽었다. 이 저장만 감싸
      건너뛰고 계속하도록 수정 — **geocode_fill.py의 좌표 저장(라운드265가
      이 파일의 행단위 커밋 패턴을 그대로 베낀 자리)에도 똑같은 무방비
      구조가 있어 함께 고쳤다.**

  [3] fetch() 의 `except Exception: return None` 이 원인을 전혀 안 남겼다
      (import logging 조차 없었다). 타임아웃·DNS실패·403·429가 전부 "접속
      실패" 한 줄로 뭉개져, 방화벽이 이 봇을 막기 시작해도 로그로는 이유를
      알 수 없었다. 형제(crypto_util.decrypt 라운드120·addr_search.search
      라운드266)처럼 반환값은 그대로 두고 원인만 로그에 남기도록 수정.

      python test_scan_round267_fixes.py
"""
import io
import json
import logging
import os
import secrets
import sqlite3
import sys
import tempfile
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []

#  ⚠ db.py 의 운영DB 안전장치가 발동하려면, collect_emails.py/geocode_fill.py
#    (둘 다 import db) 를 불러오기 **전에** 검증용 DB 경로부터 정해야 한다.
_tmpdir = tempfile.mkdtemp(prefix="round267_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


CE_SRC = read("collect_emails.py")
GF_SRC = read("geocode_fill.py")

print("=" * 72)
print("  스캔 267라운드 회귀 — collect_emails.py 최초감사(3건)+geocode_fill.py 전파분")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("_log = logging.getLogger(__name__)" in CE_SRC,
    "★★★★ collect_emails.py 에 모듈 로거가 생겼다(형제 crypto_util.py 관용구)")

i_rc = CE_SRC.index("def refuses_collection(")
i_rc_end = CE_SRC.index("\n\n\ndef ", i_rc)
rc_body = CE_SRC[i_rc:i_rc_end]
chk('re.sub(r"<[^>]+>", "", html)' in rc_body,
    "★★★★★ refuses_collection() 이 태그부터 지운 뒤 매치한다(고치기 전엔 공백만 지웠다)")

i_fetch = CE_SRC.index("def fetch(url):")
i_fetch_end = CE_SRC.index("\n\n\ndef ", i_fetch)
fetch_body = CE_SRC[i_fetch:i_fetch_end]
chk("except Exception as e:" in fetch_body and "_log.warning(" in fetch_body,
    "★★★★★ fetch() 가 실패 원인을 로그에 남긴다(고치기 전엔 완전 침묵)")

i_main = CE_SRC.index("def main():")
main_body = CE_SRC[i_main:]
chk('conn.rollback()' in main_body and 'got -= 1' in main_body and 'failed += 1' in main_body,
    "★★★★★ main() 의 UPDATE·commit 이 자기만의 try/except 로 감싸져 롤백·집계보정까지 한다")

i_gf_fill = GF_SRC.index("def fill(table, limit, dry):")
i_gf_fill_end = GF_SRC.index("\n\n\ndef ", i_gf_fill)
gf_fill_body = GF_SRC[i_gf_fill:i_gf_fill_end]
chk("skip_err" in gf_fill_body and gf_fill_body.count("conn.rollback()") == 1,
    "★★★★★ geocode_fill.py의 좌표 UPDATE·commit도 같은 방식으로 감싸졌다(전파분 함께 수정)")

# ============================================================
print("\n[2] 실행 — refuses_collection() 이 태그로 끊긴 수집거부 문구를 잡는가")
# ------------------------------------------------------------
sys.path.insert(0, HERE)
import collect_emails as CE                          # noqa: E402
importlib_dummy = None
try:
    b_tag = "<html><body><p>이메일<b>무단</b> 수집을 거부합니다.</p></body></html>"
    b_plain = "이메일무단 수집을 거부합니다."
    b_span = ("<p><span>무단으로</span> <span>수집되는</span> <span>것을</span> "
              "<span>거부</span>하며 연락처는 전화만 받습니다.</p>")
    b_br = "이메일주소 무단<br>수집거부 안내"
    b_none = "<p>회사소개: 저희는 방수·도장 전문 시공업체입니다. 문의는 전화로 부탁드립니다.</p>"

    chk(CE.refuses_collection(b_tag) is True,
        "★★★★★ 태그(<b>)로 끊긴 수집거부 문구도 탐지한다(고치기 전엔 미탐)", b_tag)
    chk(CE.refuses_collection(b_plain) is True,
        "STEP 대조군 — 태그 없는 원래 문구는 그대로 탐지된다(회귀 없음)")
    chk(CE.refuses_collection(b_span) is True,
        "★★★★ <span> 으로 단어마다 감싼(스크롤 애니메이션 등 실제 흔한 패턴) 경우도 탐지한다", b_span)
    chk(CE.refuses_collection(b_br) is True,
        "★★★★ <br> 로 끊긴 경우도 탐지한다", b_br)
    chk(CE.refuses_collection(b_none) is False,
        "STEP 대조군 — 수집거부 의사가 없는 평범한 소개문은 여전히 False 다(과잉탐지 아님)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드267 [2] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — fetch() 가 실패 원인을 로그에 남기는지(반환값은 그대로 None)")
# ------------------------------------------------------------
try:
    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(self.format(record))

    cap = _Capture()
    _ce_logger = logging.getLogger("collect_emails")
    _ce_logger.setLevel(logging.DEBUG)
    _ce_logger.addHandler(cap)

    #  ⚠⚠ [라운드664] fetch() 는 이제 urllib.request.urlopen() 이 아니라 그 위에
    #    세운 _NO_REDIRECT_OPENER.open() 을 부른다(SSRF 리다이렉트 방어 —
    #    round664 참고). 이 절은 실제 네트워크를 안 타고 예외를 주입하는 것이
    #    목적이라, fetch() 가 실제로 여는 지점(그 오프너의 .open)을 바꿔치기
    #    해야 한다 — 옛 자리(urllib.request.urlopen)는 더 이상 안 불려서
    #    바꿔치기해도 그대로 진짜 DNS 조회가 나가 버린다(실측: round664 고침
    #    직후 이 절이 URLError/getaddrinfo failed 로 전부 깨졌다).
    _orig_open = CE._NO_REDIRECT_OPENER.open
    _next_exc = {"exc": None}

    def _fake_urlopen(req, timeout=None):
        raise _next_exc["exc"]

    CE._NO_REDIRECT_OPENER.open = _fake_urlopen

    for label, exc in (
        ("타임아웃", TimeoutError("simulated timeout")),
        ("연결리셋", ConnectionResetError("simulated reset")),
        ("HTTP403", urllib.error.HTTPError("http://x", 403, "Forbidden", {}, None)),
    ):
        cap.records.clear()
        _next_exc["exc"] = exc
        r = CE.fetch("https://no-such-host.invalid.test/")
        chk(r is None, f"STEP {label} — 반환값은 그대로 None 이다(호출부 계약 불변)")
        chk(any(type(exc).__name__ in rec for rec in cap.records),
            f"★★★★★ {label} — 경고 로그에 정확한 예외종류가 남는다(고치기 전엔 로그 0건)",
            list(cap.records))

    CE._NO_REDIRECT_OPENER.open = _orig_open
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드267 [3] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[4] 실행 — collect_emails.py: 저장 1건 실패해도 배치가 계속되는가")
# ------------------------------------------------------------
class _FlakyConn:
    """execute() 가 지정한 SQL 부분문자열을 만나면 지정 횟수만큼 실패한다."""

    def __init__(self, real, fail_on_substr, fail_count=1):
        self._real = real
        self._fail_on = fail_on_substr
        self._fail_count = fail_count
        self._fired = 0

    def execute(self, sql, *args, **kwargs):
        if self._fail_on in sql and self._fired < self._fail_count:
            self._fired += 1
            raise sqlite3.OperationalError("SIMULATED-DB-FAIL-R267")
        return self._real.execute(sql, *args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._real, name)


try:
    import importlib
    import db as DB
    DB.init_db()
    importlib.reload(CE)

    mark = "R267A-" + secrets.token_hex(3)
    conn0 = DB.get_db()
    p1_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,website,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업','서울',?,'활성')",
        (f"{mark}-1", "site1-r267.test")).lastrowid
    p2_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,website,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업','서울',?,'활성')",
        (f"{mark}-2", "site2-r267.test")).lastrowid
    conn0.commit()
    conn0.close()
    assert p1_id < p2_id, "1번이 먼저(더 작은 id로) 처리돼야 시나리오가 성립한다"

    def _fake_collect_one(website):
        return [f"{website.replace('.', '-')}@ok.example"], "첫 페이지(가짜)"

    class _Capture(logging.Handler):
        def __init__(self):
            super().__init__()
            self.records = []

        def emit(self, record):
            self.records.append(self.format(record))

    cap2 = _Capture()
    logging.getLogger("collect_emails").setLevel(logging.DEBUG)
    logging.getLogger("collect_emails").addHandler(cap2)

    _orig_collect_one = CE.collect_one
    _orig_get_db = DB.get_db
    CE.collect_one = _fake_collect_one
    DB.get_db = lambda: _FlakyConn(_orig_get_db(), "UPDATE partners", fail_count=1)

    _real_argv = sys.argv
    sys.argv = ["collect_emails.py", "--all"]
    crashed = False
    try:
        CE.main()
    except Exception:
        crashed = True
    finally:
        sys.argv = _real_argv
        CE.collect_one = _orig_collect_one
        DB.get_db = _orig_get_db

    chk(not crashed,
        "★★★★★ 저장 1건이 실패해도 배치 프로세스가 죽지 않는다(고치기 전엔 여기서 그대로 죽었다)")
    chk(any("이메일 저장 실패" in rec and f"#{p1_id}" in rec for rec in cap2.records),
        "STEP 실패한 행의 경고 로그에 협력사 id·예외종류가 남는다", cap2.records)

    conn2 = DB.get_db()
    r1 = conn2.execute("SELECT email FROM partners WHERE id=?", (p1_id,)).fetchone()
    r2 = conn2.execute("SELECT email FROM partners WHERE id=?", (p2_id,)).fetchone()
    conn2.close()
    chk((r1["email"] or "") == "",
        "STEP 1번(저장 실패 대상)은 이메일이 비어있다(부분쓰기 없음, 정상)", dict(r1))
    chk((r2["email"] or "") != "",
        "★★★★★ 2번(1번 다음 순서)은 정상 저장됐다 — 앞 행 저장실패가 배치를 막지 않았다",
        dict(r2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드267 [4] 준비/실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[5] 실행 — geocode_fill.py: 좌표 저장 1건 실패해도 배치가 계속되는가(전파분 검증)")
# ------------------------------------------------------------
try:
    import geocode_fill as GF
    importlib.reload(GF)
    import addr_search as ADDR

    mark2 = "R267B-" + secrets.token_hex(3)
    conn0 = DB.get_db()
    q1_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업',?,?,'활성')",
        (f"{mark2}-1", "서울 송파구", "서울 송파구 올림픽로 300")).lastrowid
    q2_id = conn0.execute(
        "INSERT INTO partners(name,partner_type,major,category,region,address,status) "
        "VALUES(?,'시공사','금속ㆍ창호','금속ㆍ창호ㆍ지붕ㆍ건축물조립공사업',?,?,'활성')",
        (f"{mark2}-2", "서울 강남구", "서울 강남구 테헤란로 999")).lastrowid
    conn0.commit()
    conn0.close()
    assert q1_id < q2_id

    def _fake_search(q):
        return [{"lat": 37.5, "lng": 127.1, "region": "", "road": q}]

    _orig_search = ADDR.search
    _orig_get_db2 = DB.get_db
    ADDR.search = _fake_search
    DB.get_db = lambda: _FlakyConn(_orig_get_db2(), "UPDATE partners SET lat=", fail_count=1)
    gf_crashed = False
    try:
        GF.fill("partners", 500, dry=False)
    except Exception:
        gf_crashed = True
    finally:
        ADDR.search = _orig_search
        DB.get_db = _orig_get_db2

    chk(not gf_crashed,
        "★★★★★ geocode_fill.py 도 저장 1건이 실패해도 배치 프로세스가 죽지 않는다"
        "(고치기 전엔 collect_emails.py와 같은 구조라 여기서 그대로 죽었을 것)")

    conn3 = DB.get_db()
    g1 = conn3.execute("SELECT lat, lng FROM partners WHERE id=?", (q1_id,)).fetchone()
    g2 = conn3.execute("SELECT lat, lng FROM partners WHERE id=?", (q2_id,)).fetchone()
    conn3.close()
    chk(g1["lat"] is None,
        "STEP 1번(저장 실패 대상)은 좌표가 비어있다(부분쓰기 없음, 정상)", dict(g1))
    chk(g2["lat"] is not None,
        "★★★★★ 2번은 정상 저장됐다 — geocode_fill.py도 앞 행 저장실패가 배치를 막지 않는다"
        "(수정 전엔 collect_emails.py와 같은 구조라 여기서도 배치 전체가 죽었을 것)",
        dict(g2))
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드267 [5] 준비/실행", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
