# -*- coding: utf-8 -*-
"""로컬 HTTPS 리허설용 TLS 종단 프록시 (개발 전용)

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

운영에서는 nginx 가 TLS 를 끊고 뒤의 WSGI 서버로 평문 전달한다.
그런데 운영 모드(BOKGUON_ENV=prod)는 세션 쿠키에 Secure 플래그를 붙이므로,
평문 http 로는 로그인 이후 흐름을 검증할 수 없다.

이 스크립트는 nginx 자리에 임시로 서서 같은 구조를 만든다.
  브라우저/테스트 ──https──▶ 이 프록시(8443) ──http──▶ waitress(8771)

  python dev_tls_proxy.py                 8443 → 8771
  python dev_tls_proxy.py 8443 8771       포트 지정

⚠ 자체 서명 인증서를 쓰므로 **개발·리허설 전용**이다. 운영에는 nginx + 정식 인증서를 쓴다.

⚠⚠ [라운드306] 이 프록시는 TCP 바이트를 그대로 중계할 뿐 HTTP 를 전혀
  해석하지 않는다 — 즉 실제 nginx 가 하는 X-Forwarded-For 이어붙이기
  (`$proxy_add_x_forwarded_for`, 클라이언트가 뭘 보내든 그 뒤에 실제 발신
  IP 를 덧붙여 앞쪽 값은 신뢰하지 않게 만드는 동작)를 전혀 하지 않는다.
  BOKGUON_BEHIND_PROXY=1(이 저장소 .env 의 실제 설정값)로 뜬 서버를 이
  프록시로 리허설하면, 클라이언트가 보낸 X-Forwarded-For 값이 검증 없이
  그대로 request.remote_addr 이 된다 — 관리자 IP 화이트리스트·2단계인증
  우회판정처럼 client_ip() 를 신뢰하는 검사들이 이 경로에서는 **무엇을
  보내든 통과**할 수 있다(실측 확인: 격리 환경에서 위조 헤더가 그대로
  전달됨). 루프백(127.0.0.1)에만 바인드하므로 원격 공격 표면은 아니지만,
  "이 프록시로 리허설했으니 IP 기반 방어까지 검증됐다"고 오해하면 안
  된다 — IP 신뢰 로직은 이 경로로는 리허설되지 않는다는 뜻으로만 남겨
  둔다(이 도구의 목적은 Secure 쿠키 동작 검증뿐이다).
"""
import os
import ssl
import sys
import socket
import threading
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
CERT = os.path.join(HERE, "dev_cert.pem")
KEY = os.path.join(HERE, "dev_key.pem")


def ensure_cert():
    """자체 서명 인증서가 없으면 만든다 (cryptography 사용, openssl 불필요)."""
    if os.path.exists(CERT) and os.path.exists(KEY):
        return
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "KR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Olympos Networks"),
        x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName([
                x509.DNSName("localhost"),
                x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1")),
            ]), critical=False)
            .sign(key, hashes.SHA256()))

    with open(KEY, "wb") as f:
        f.write(key.private_bytes(serialization.Encoding.PEM,
                                  serialization.PrivateFormat.TraditionalOpenSSL,
                                  serialization.NoEncryption()))
    with open(CERT, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print(f"  자체 서명 인증서 생성 — {CERT}", flush=True)


def pipe(src, dst):
    """한 방향으로 바이트를 그대로 흘려보낸다."""
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def handle(client, backend_addr):
    try:
        upstream = socket.create_connection(backend_addr, timeout=20)
    except OSError as e:
        client.close()
        print(f"  백엔드 연결 실패 {backend_addr}: {e}", flush=True)
        return
    threading.Thread(target=pipe, args=(client, upstream), daemon=True).start()
    pipe(upstream, client)


def main():
    listen_port = int(sys.argv[1]) if len(sys.argv) > 1 else 8443
    backend_port = int(sys.argv[2]) if len(sys.argv) > 2 else 8771
    ensure_cert()

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(CERT, KEY)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2      # 운영 nginx 설정과 동일하게 1.2 이상만

    #  ⚠⚠ [라운드275] Windows 는 SO_REUSEADDR 를 걸어도 같은 host:port 이중
    #    바인딩을 막지 않는다(firstday_server.py 274라운드가 먼저 발견한
    #    것과 같은 패턴 — 실측: 같은 리슨포트로 두 인스턴스를 띄우면 둘 다
    #    bind 성공, 첫 프로세스를 죽여도 둘째가 조용히 이어받아 응답한다).
    #    "재시작했다"고 믿기 쉬운데 실제로는 옛 프로세스가 계속 떠 있을 수
    #    있어, backend_port 를 바꿔 재실행하면 옛 backend 로 계속 흘려보내는
    #    혼란이 생긴다. bind 전에 이미 누가 이 포트에 응답 중인지 확인한다.
    _probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    _probe.settimeout(0.5)
    try:
        _already_up = _probe.connect_ex(("127.0.0.1", listen_port)) == 0
    finally:
        _probe.close()
    if _already_up:
        raise SystemExit(
            f"포트 {listen_port}에 이미 무언가 응답하고 있습니다 — 이전에 띄운 "
            f"dev_tls_proxy.py 가 아직 살아있을 수 있습니다(Windows는 이중 "
            f"바인딩을 조용히 허용해 옛 프로세스가 계속 응답합니다). "
            f"'netstat -ano | findstr {listen_port}' 로 기존 프로세스를 먼저 정리하세요.")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", listen_port))
    srv.listen(64)

    #  ⚠⚠ [라운드275] flush=True 없이는 이 배너도(serve_waitress.py 273라운드가
    #    찾은 것과 같은 이유로) 하드킬 시 로그에 안 남을 수 있다 — 전부에 붙인다.
    print("=" * 56, flush=True)
    print("  복구온 로컬 TLS 리허설 프록시 (개발 전용)", flush=True)
    print(f"  https://127.0.0.1:{listen_port}  →  http://127.0.0.1:{backend_port}", flush=True)
    print("  ㈜올림포스네트웍스 전략사업실 유경탁 파트장", flush=True)
    print("=" * 56, flush=True)

    while True:
        raw, addr = srv.accept()
        try:
            tls = ctx.wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError) as e:
            #  ⚠⚠ [라운드275] 같은 파일 안의 형제(handle() 의 백엔드 연결
            #    실패, 아래쪽 print)는 실패를 로그로 남기는데 이 자리만
            #    완전히 삼켰다(실측: 평문 바이트를 이 포트로 보내면 로그
            #    0줄). 핸드셰이크 실패도 같은 "연결 실패" 범주라 통일한다.
            print(f"  TLS 핸드셰이크 실패 {addr}: {type(e).__name__}: {e}", flush=True)
            raw.close()
            continue
        threading.Thread(target=handle, args=(tls, ("127.0.0.1", backend_port)), daemon=True).start()


if __name__ == "__main__":
    main()
