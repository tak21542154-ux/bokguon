# -*- coding: utf-8 -*-
"""스캔 157라운드 회귀 — 웹훅 SSRF 방어의 검사·접속 사이 DNS 리바인딩 틈.

  _webhook_host_safe() 는 전송 직전에 호스트명을 resolve 해 공인망인지
  검사한다("설정 후 DNS 가 바뀌는 rebinding 방어"라고 자체 주석까지 달려
  있었다). 그런데 검사를 통과한 뒤 실제 전송은 urllib 에 **같은 호스트명을
  다시** 건넸다 — urllib 이 접속 시점에 **또 한 번** 독립적으로 resolve
  한다. 검사와 접속이 서로 다른 조회이므로, 그 사이 공격자의 네임서버가
  답을 바꿔치면(짧은 TTL의 DNS 리바인딩) 검사는 공인 IP로 통과하고 실제
  접속만 내부/루프백/클라우드 메타데이터로 갈 수 있었다. 재전송 스윕은
  최대 5회까지 같은 주소를 다시 시도하므로, 공격자에게 창이 여러 번
  주어진다는 점에서 한 번뿐인 우연이 아니라 반복 가능한 취약점이었다.

  고침: 검사(_webhook_safe_ip)가 확인한 그 IP를 실제 접속에도 그대로
  못박는다(_PinnedHTTPSConnection) — Host 헤더·TLS SNI 는 원래 호스트명을
  그대로 써서 인증서 검증과 가상호스팅은 깨지지 않는다.

      python test_scan_round157_fixes.py
"""
import io
import os
import socket
import sys
import tempfile
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


APP_SRC = read("app.py")

print("=" * 72)
print("  스캔 157라운드 회귀 — 웹훅 SSRF 검사·접속 사이 DNS 리바인딩 틈")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("def _webhook_safe_ip(url):" in APP_SRC,
    "★★★ 검증된 IP를 돌려주는 _webhook_safe_ip() 가 신설됐다")

i_hs = APP_SRC.index("def _webhook_host_safe(")
i_hs_end = APP_SRC.index("\ndef ", i_hs + 1)
hs_body = APP_SRC[i_hs:i_hs_end]
chk("return _webhook_safe_ip(url) is not None" in hs_body,
    "★★★ _webhook_host_safe 가 _webhook_safe_ip 로 위임한다(중복 로직 없음)")

chk("class _PinnedHTTPSConnection(http.client.HTTPSConnection):" in APP_SRC,
    "★★★ 검증된 IP로만 접속하는 커넥션 클래스가 신설됐다")
i_pc = APP_SRC.index("class _PinnedHTTPSConnection(")
i_pc_end = APP_SRC.index("\ndef ", i_pc + 1)
pc_body = APP_SRC[i_pc:i_pc_end]
chk("self._create_connection(\n            (self._pinned_ip, self.port)" in pc_body,
    "★★★ 접속 대상이 self.host(호스트명) 가 아니라 못박은 IP 다")
chk("server_hostname = self._tunnel_host or self.host" in pc_body,
    "★★★ TLS SNI 는 원래 호스트명을 그대로 쓴다(인증서 검증 유지)")

chk("def _pinned_webhook_opener(pinned_ip):" in APP_SRC,
    "★★★ 못박은 IP로만 접속하는 오프너 팩토리가 신설됐다")

i_ws = APP_SRC.index("def _webhook_send(")
i_ws_end = APP_SRC.index("\ndef ", i_ws + 1)
ws_body = APP_SRC[i_ws:i_ws_end]
chk("pinned_ip = _webhook_safe_ip(url)" in ws_body,
    "★★★ _webhook_send 가 검사와 동시에 접속용 IP를 확보한다")
chk("_pinned_webhook_opener(pinned_ip).open(req, timeout=5)" in ws_body,
    "★★★ _webhook_send 가 그 IP로 못박은 오프너로 전송한다")
chk("_WEBHOOK_OPENER" not in APP_SRC,
    "★ 재검사 없이 호스트명을 다시 resolve 하던 옛 공유 오프너가 제거됐다")

# ============================================================
print("\n[2] 실행 — _webhook_safe_ip 의 실제 IP 분류(진짜 getaddrinfo)")
# ------------------------------------------------------------
_tmpdir = tempfile.mkdtemp(prefix="round157_")
os.environ["BOKGUON_DB_PATH"] = os.path.join(_tmpdir, "verify.db")
os.environ["BOKGUON_UPLOAD_DIR"] = os.path.join(_tmpdir, "uploads")
os.environ["BOKGUON_ENV"] = "dev"
os.environ["BOKGUON_SEED_DEMO"] = "0"
sys.path.insert(0, HERE)
try:
    import db as DB
    DB.init_db()
    import app as A

    chk(A._webhook_safe_ip("https://100.64.0.1/h") is None,
        "★★★ 공유주소공간(CGNAT)은 여전히 차단된다(라운드84 회귀 없음)")
    chk(A._webhook_safe_ip("https://127.0.0.1/h") is None,
        "★ 루프백은 여전히 차단된다")
    chk(A._webhook_safe_ip("http://8.8.8.8/h") is None,
        "★ https 가 아니면 여전히 차단된다")
    r_ok = A._webhook_safe_ip("https://8.8.8.8/h")
    chk(r_ok == "8.8.8.8",
        "★★★ 공인 IP는 통과하고, 접속에 쓸 그 IP 자체를 돌려준다", r_ok)
    chk(A._webhook_host_safe("https://8.8.8.8/h") is True
        and A._webhook_host_safe("https://127.0.0.1/h") is False,
        "★ 위임 래퍼(_webhook_host_safe)도 동일하게 판정한다")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드157 [2] _webhook_safe_ip 실행", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — DNS 리바인딩 재현: 검사와 접속이 같은 IP를 쓰는가")
# ------------------------------------------------------------
#  getaddrinfo 를 두 번 부르면 서로 다른 답(공인→사설)을 준다 — 검사와 접속이
#  **독립적으로** 다시 조회하면 이 사이에서 뒤바뀐다. 실제 소켓 연결은 하지
#  않는다(create_connection 을 스텁으로 갈아 끼운다).
SAFE_IP = "93.184.216.34"     # 검사를 통과하는 "진짜" 공인 IP (연결은 안 한다)
EVIL_IP = "169.254.169.254"   # 클라우드 메타데이터 — 리바인딩이 성공하면 여기로 간다
FAKE_HOST = "webhook-r157.test"   # IANA 예약 테스트 TLD — 실제로 조회되지 않는다


def _mk_fakes():
    calls = {"getaddrinfo": 0}
    connect_targets = []

    def _fake_getaddrinfo(host, port, *a, **k):
        calls["getaddrinfo"] += 1
        ip = SAFE_IP if calls["getaddrinfo"] == 1 else EVIL_IP
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]

    def _fake_create_connection(address, *a, **k):
        host, port = address[0], address[1]
        try:
            import ipaddress
            ipaddress.ip_address(host)
            effective_ip = host          # 이미 IP 리터럴 — 재조회 없이 그대로 접속
        except ValueError:
            #  호스트명이 그대로 넘어왔다 — 실제 create_connection 처럼 다시 resolve
            info = _fake_getaddrinfo(host, port)
            effective_ip = info[0][4][0]
        connect_targets.append(effective_ip)
        raise OSError("test-stub: 이 테스트는 실제 네트워크 연결을 하지 않는다")

    return calls, connect_targets, _fake_getaddrinfo, _fake_create_connection


try:
    conn = DB.get_db()
    did = conn.execute(
        "INSERT INTO webhook_deliveries(insurer_id,event,target_url,status,attempts,created_at) "
        "VALUES(1,'case.awarded',?,'대기',0,?)", (f"https://{FAKE_HOST}/hook", DB.now())).lastrowid
    conn.commit(); conn.close()

    calls, targets, fake_gai, fake_cc = _mk_fakes()
    with mock.patch("socket.getaddrinfo", side_effect=fake_gai), \
         mock.patch("socket.create_connection", side_effect=fake_cc):
        A._webhook_send(did, f"https://{FAKE_HOST}/hook", "secret", '{"x":1}')

    chk(calls["getaddrinfo"] == 1,
        "★★★ DNS 조회가 정확히 한 번뿐이다(검사·접속이 같은 조회를 재사용)"
        f" — 실제 호출 {calls['getaddrinfo']}회", calls)
    chk(targets == [SAFE_IP],
        "★★★ 실제 접속 대상이 검사를 통과한 그 공인 IP 다"
        "(고치기 전엔 여기서 EVIL_IP=클라우드 메타데이터로 갔다)", targets)

    conn = DB.get_db()
    row = dict(conn.execute(
        "SELECT status, error FROM webhook_deliveries WHERE id=?", (did,)).fetchone())
    conn.close()
    chk(row["status"] == "실패" and "test-stub" in (row["error"] or ""),
        "★ 스텁 예외가 정상적으로 실패 기록으로 남는다(경로가 실제로 여기까지 왔다)", row)
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드157 [3] DNS 리바인딩 재현", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
