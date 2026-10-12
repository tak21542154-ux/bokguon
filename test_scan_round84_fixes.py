# -*- coding: utf-8 -*-
"""스캔 84라운드 회귀 — 보험사 웹훅 전송 결함 3건.

  ① _webhook_host_safe() — 공유주소공간(100.64.0.0/10, CGNAT, RFC 6598)이
     이 파이썬 버전에서 is_private 도 is_reserved 도 아니라서 그대로 새어나갔다
     (내부망으로 이 대역을 쓰는 AWS/k8s/Tailscale 배포에서 실제로 뚫린다).

  ② sweep_webhook_retries() 의 대상 주소 — 생성 시점 스냅샷(target_url)을 계속
     썼다. 관리자가 웹훅 주소를 지우거나 바꿔도(insurers.webhook_url 만 바뀌고
     이미 쌓인 대기/실패 건은 안 바뀐다) 재전송은 옛 주소로 계속 나갔다.

  ③ sweep_webhook_retries() 의 "선기록" UPDATE — CAS(읽은 값 그대로일 때만 갱신)
     가 아니었다. 크론이 겹치면(부트스트랩 crontab 에 flock 없음) 두 워커가 같은
     건을 똑같이 "조건 충족"으로 보고 둘 다 전송해, 보험사 전산에 같은 이벤트가
     중복 도착한다. 형제(sweep_send_notifications)는 이미 CAS 로 막고 있었다.

      python test_scan_round84_fixes.py
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
print("  스캔 84라운드 회귀 — 보험사 웹훅 전송 결함 3건")
print("═" * 72)


def _py_fn_body(src, fn_name):
    start = src.index(f"\ndef {fn_name}(")
    end = src.find("\ndef ", start + 1)
    return src[start:end if end != -1 else None]


# ══════════════════════════════════════════════════════════════
print("\n[1] 소스 — 함수 경계 안에서 확인")
# ──────────────────────────────────────────────────────────────
#  [라운드157] is_global 검사 로직은 _webhook_safe_ip() 로 옮겨갔다 —
#  _webhook_host_safe() 는 이제 그 결과를 위임받는 1줄짜리 래퍼다(SSRF
#  DNS 리바인딩 방어: 검사와 실제 접속이 같은 IP를 쓰도록 못박기 위함).
safe_body = _py_fn_body(APP_SRC, "_webhook_safe_ip")
chk("_v4.is_global" in safe_body,
    "★★★ ① _webhook_safe_ip 가 is_global 검사를 더한다(CGNAT 방어)")

sweep_body = _py_fn_body(APP_SRC, "sweep_webhook_retries")
chk("i.webhook_url AS current_url" in sweep_body,
    "★★★ ② sweep_webhook_retries 가 생성시점 스냅샷 대신 보험사의 현재 주소를 쓴다")
chk("AND COALESCE(attempts,0)=?" in sweep_body and "BEGIN IMMEDIATE" in sweep_body,
    "★★★ ③ sweep_webhook_retries 의 선점 UPDATE 가 CAS(attempts 일치) 로 바뀌었다")

# ══════════════════════════════════════════════════════════════
print("\n[2] 실행 — _webhook_host_safe 를 실제로 호출(진짜 getaddrinfo)")
# ──────────────────────────────────────────────────────────────
_tmpdir = tempfile.mkdtemp(prefix="round84_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A._webhook_host_safe("https://100.64.0.1/h") is False,
        "★★★ ① 공유주소공간(CGNAT) 리터럴 IP가 차단된다"
        "(고치기 전엔 is_private/is_reserved 둘 다 아니라서 허용됐다)")
    chk(A._webhook_host_safe("https://[::ffff:100.64.0.1]/h") is False,
        "★★ ① IPv4-매핑 IPv6 로 감싼 CGNAT 도 차단된다(내부 실주소로 풀어서 검사)")
    chk(A._webhook_host_safe("https://8.8.8.8/h") is True,
        "STEP 대조군 — 평범한 공인 IPv4 는 여전히 허용된다(과잉차단 아님)")
    chk(A._webhook_host_safe("https://127.0.0.1/h") is False,
        "STEP 회귀 없음 — 루프백은 여전히 차단된다(라운드38 영역 보존)")
    chk(A._webhook_host_safe("http://8.8.8.8/h") is False,
        "STEP 회귀 없음 — http(평문)는 여전히 거부된다(무관 규칙 보존)")

    # ══════════════════════════════════════════════════════════
    print("\n[3] 실행 — sweep_webhook_retries 를 실제로 호출(임시 DB)")
    # ──────────────────────────────────────────────────────────
    OLD_URL = "https://old-vendor.example.com/hook"
    NEW_URL = "https://new-vendor.example.com/hook"
    sent = []

    def _fake_send(delivery_id, url, secret, payload_str, count_attempt=True):
        sent.append((delivery_id, url))
        return None
    _real_send = A._webhook_send
    A._webhook_send = _fake_send

    def _mk_insurer(conn, url):
        return conn.execute(
            "INSERT INTO insurers(name,status,api_enabled,webhook_url,webhook_secret) "
            "VALUES('R84보험','활성',1,?,'sec')", (url,)).lastrowid

    def _mk_delivery(conn, iid, target_url, status="실패", attempts=0):
        return conn.execute(
            "INSERT INTO webhook_deliveries(insurer_id,event,case_no,payload,target_url,"
            "status,attempts,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (iid, "case.awarded", "R84-1", "{}", target_url, status, attempts,
             DB.now())).lastrowid

    try:
        # ── ② 주소가 없어졌으면(NULL) '미설정'으로 접고 절대 전송하지 않는다 ──
        conn = DB.get_db()
        iid_a = _mk_insurer(conn, None)
        did_a = _mk_delivery(conn, iid_a, OLD_URL)
        conn.commit(); conn.close()

        conn = DB.get_db()
        A.sweep_webhook_retries(conn)
        conn.commit()
        row_a = conn.execute(
            "SELECT status FROM webhook_deliveries WHERE id=?", (did_a,)).fetchone()
        conn.close()
        chk(not any(d == did_a for d, _ in sent),
            "★★★ ② 웹훅 주소가 지워진 건은 절대 전송 시도하지 않는다", sent)
        chk(row_a["status"] == "미설정",
            "★★ ② 주소가 없어진 건은 상태가 '미설정'으로 접힌다(무한 재시도 방지)",
            dict(row_a))

        # ── ② 주소가 바뀌었으면 새 주소로 보낸다(옛 스냅샷 아님) ──
        sent.clear()
        conn = DB.get_db()
        iid_b = _mk_insurer(conn, NEW_URL)
        did_b = _mk_delivery(conn, iid_b, OLD_URL)
        conn.commit(); conn.close()

        conn = DB.get_db()
        A.sweep_webhook_retries(conn)
        conn.commit(); conn.close()
        sent_urls = [u for d, u in sent if d == did_b]
        chk(sent_urls == [NEW_URL],
            "★★★ ② 재전송이 생성시점 스냅샷(OLD_URL) 대신 지금 등록된 새 주소로 나간다"
            "(고치기 전엔 옛 주소로 나갔다)", sent_urls)

        # ── ③ 경합 — 다른 워커가 같은 건을 이미 선점했으면 이번 워커는 물러난다 ──
        sent.clear()
        conn = DB.get_db()
        iid_c = _mk_insurer(conn, NEW_URL)
        did_c = _mk_delivery(conn, iid_c, OLD_URL, attempts=0)
        conn.commit(); conn.close()

        #  ⚠ _RaceProxy — sweep_webhook_retries 가 이 건의 트랜잭션을 열기(BEGIN
        #    IMMEDIATE) **직전**, 별도의 진짜 커넥션으로 "이미 다른 워커가 이 건을
        #    선점해 attempts 를 1로 올려놨다" 는 상황을 실제로 만든다(고친 코드
        #    자신의 BEGIN IMMEDIATE 가 잠금을 잡기 전이라야 이 별도 커넥션의
        #    커밋이 안 막힌다 — UPDATE 문 자체를 가로채면 이미 잠긴 뒤라 이 주입이
        #    조용히 대기/실패한다). 고친 코드는 자신이 읽었던 attempts=0 조건이
        #    더는 안 맞아 rowcount=0 으로 물러나야 한다. 안 고친 코드는 조건에
        #    attempts 를 안 걸어 두 번째로도 그냥 통과해 이중 전송된다.
        import sqlite3 as _sqlite3
        _fired = {"n": 0}

        class _RaceConn:
            def __init__(self, real):
                self._real = real

            def execute(self, sql, params=()):
                if not _fired["n"] and sql.strip() == "BEGIN IMMEDIATE":
                    _fired["n"] += 1
                    _rc = _sqlite3.connect(os.environ["BOKGUON_DB_PATH"], timeout=5)
                    _rc.execute(
                        "UPDATE webhook_deliveries SET attempts=1, delivered_at=? "
                        "WHERE id=?", (DB.now(), did_c))
                    _rc.commit(); _rc.close()
                return self._real.execute(sql, params)

            def __getattr__(self, name):
                return getattr(self._real, name)

        conn = DB.get_db()
        A.sweep_webhook_retries(_RaceConn(conn))
        conn.commit()
        row_c = conn.execute("SELECT attempts FROM webhook_deliveries WHERE id=?",
                              (did_c,)).fetchone()
        conn.close()
        chk(_fired["n"] == 1, "STEP 경합 주입이 실제로 한 번 발동했다", _fired)
        #  주입은 DB 갱신만 하고 실제 전송은 흉내내지 않으므로(그건 "다른 워커"가
        #  이미 따로 했을 몫이다), 이 워커가 물러나면 여기서 관측되는 전송 횟수는
        #  정확히 0이어야 한다 — 안 고친 코드는 attempts 조건이 없어 그대로 통과해
        #  이 워커도 또 전송한다(그러면 여기 카운트가 1이 되어 잡힌다).
        chk(len([d for d, _ in sent if d == did_c]) == 0,
            "★★★ ③ 이미 다른 워커가 선점한 건은 이번 워커가 다시 전송하지 않는다"
            "(고치기 전엔 CAS 가 없어 attempts 값과 무관하게 통과해 이중 전송됐다)",
            [d for d, _ in sent if d == did_c])
        chk(row_c["attempts"] == 1,
            "★★ ③ attempts 도 한 번만 올라간다(경쟁자의 갱신을 덮어쓰지 않는다)",
            dict(row_c))
    finally:
        A._webhook_send = _real_send

except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드84 서버측 준비/실행", f"{type(e).__name__} {e}")
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
