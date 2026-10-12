# -*- coding: utf-8 -*-
"""협력업체 이메일 수집 — 등록된 홈페이지에서 공개 연락처를 찾아 채운다.

  ㈜올림포스네트웍스 전략사업실 유경탁 파트장

■ 왜 필요한가
  초기 398개사는 리서치로 모아 **전화는 있으나 이메일이 0%** 다.
  콜드메일을 보내려면 주소가 있어야 하는데, 398곳을 손으로 찾는 것은 비현실적이다.
  이미 보유한 홈페이지 주소(278곳)에서 공개된 대표 메일을 찾아 채운다.

■ 반드시 지키는 것 (정보통신망법)
  · §50-2 (전자우편주소의 무단 수집 금지)
      "수집을 거부하는 의사가 명시된" 페이지에서 자동 수집하면 안 된다.
      → 페이지에 수집거부 문구가 있으면 **그 사이트는 건너뛴다.**
      → robots.txt 가 막은 경로도 가져오지 않는다.
  · §50① (광고성 정보 전송 제한)
      **여기서 수집한 주소는 '동의'가 아니다.** 공개된 연락처일 뿐이다.
      그래서 email_consent=0, email_source='수집(홈페이지)' 로 표시해 저장한다.
      광고성 발송(캠페인)은 이 표시를 보고 동의분과 구분해 다룬다.

■ 그 밖의 예의
  · 같은 호스트에 연속 요청하지 않도록 간격을 둔다.
  · 응답이 느리거나 막히면 그냥 건너뛴다(수집은 부가 작업이지 서비스가 아니다).

실행:
    python collect_emails.py --limit 30        30곳만 시험 수집
    python collect_emails.py --all             홈페이지 있는 전 업체
    python collect_emails.py --limit 30 --dry  저장하지 않고 결과만 출력
"""
import io
import os
import re
import sys
import time
import socket
import ipaddress
import logging
import argparse
import urllib.request
import urllib.error
import urllib.robotparser
from urllib.parse import urlparse, urljoin

import db as DB

#  ⚠ 윈도 기본 콘솔은 cp949 라 '—' 같은 문자를 print 하면 UnicodeEncodeError 로
#    죽는다(아래 main() 의 "이메일 수집 — 대상 …곳" 줄). 형제 점검 도구
#    (check_tx_paths.py 등)가 이미 쓰는 방어를 그대로 옮긴다(round519).
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass

_log = logging.getLogger(__name__)

UA = "Mozilla/5.0 (compatible; BokguonContactBot/1.0; +https://bokguon.olymposnetworks.com)"
TIMEOUT = 8
PAUSE = 0.7                      # 같은 대상에 몰아치지 않도록 최소 간격
MAX_BYTES = 500_000              # 큰 페이지는 앞부분만 본다
#  ⚠⚠ [라운드420] EMAIL_RE·태그제거 정규식 둘 다 앵커가 없어(닫는 조건이
#    안 나오면 시작위치마다 끝까지 훑는다) 페이지 길이의 제곱에 비례해
#    느려진다 — 정밀조사 Agent 실측: 200,000자에서 EMAIL_RE 32.9초. 위
#    MAX_BYTES(500,000)는 네트워크 읽기만 제한할 뿐 정규식 처리 시간은
#    안 막는다. 실제 연락처·수집거부 문구는 페이지 극히 일부에 있으므로,
#    이 파일 자신의 원칙("응답이 느리거나 막히면 건너뛴다")을 정규식
#    단계까지 넓혀 별도의 더 작은 상한을 둔다(30,000자 기준 두 정규식
#    모두 1초 미만으로 확인).
MAX_SCAN_CHARS = 30_000

# 수집 거부 의사로 볼 문구 — 하나라도 있으면 그 사이트는 통째로 건너뛴다(§50-2)
REFUSE_MARKERS = [
    "이메일주소무단수집거부", "이메일주소 무단수집 거부", "무단수집거부",
    "이메일 무단 수집", "전자우편주소의 무단수집", "전자우편주소 무단 수집",
    "email collection denial", "무단으로 수집되는 것을 거부",
]

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# 사람이 쓰는 주소가 아닌 것들 — 넣어봤자 반송되거나 무의미하다
#  ⚠⚠ [라운드514] "webmaster@example" 는 죽은 항목이었다 — 이 리스트는
#    local part(예: e.partition("@")[0], @ 앞부분)에서만 단어를 찾는데,
#    local part 는 그 정의상 "@"를 절대 포함할 수 없다. 그래서 이 항목은
#    한 번도 매치될 수 없었다(실측: _bad_local_word_in("webmaster",
#    BAD_LOCAL) 은 물론 어떤 local part 를 넣어도 이 항목만으로는 절대
#    걸리지 않는다). "webmaster@example.org" 같은 흔한 플레이스홀더
#    주소가 그대로 "수집됨"으로 저장될 수 있었다 — BAD_DOMAIN 에는
#    example.com/example.co.kr 만 있고 example.org/example.net(둘 다
#    RFC 2606 예약 도메인) 은 없었기 때문이다. 이 도메인 자체를
#    BAD_DOMAIN 에 채워 넣는 것이 진짜 고침이다(아래 참고) — local part
#    리스트에서는 애초에 "@" 포함 항목을 없앤다.
BAD_LOCAL = ("example", "yourname", "your-email", "email", "sample", "test",
             "noreply", "no-reply", "donotreply")


#  ⚠⚠ [라운드299] `b in local` 부분열 검사는 "실제로 그 단어인가"가 아니라
#    "그 글자들이 어디든 섞여 있는가"만 본다 — local part 가 흔한 실제
#    단어(latest·contest·protest 등)이면 그 안에 test 가 그냥 부분열로
#    들어 있어 사람이 직접 검증한 정상 주소까지 "사람 주소 아님"으로
#    오판된다(실측: clean_collected_emails.is_junk('latest@…') 가
#    '사람 주소 아님(latest)' 을 낸다 — 이 함수가 그대로 지운다). BAD_LOCAL
#    의 각 단어가 local part 안에서 구두점(., -, _, 숫자 등)으로 구분된
#    독립된 조각일 때만 맞다고 본다 — 실제 플레이스홀더 주소(no-reply@·
#    test.account@·sample_mail@)는 전부 이 모양이고, 사고 싶은 무관한
#    단어는 그 앞뒤가 알파벳으로 이어져 있어 걸리지 않는다.
def _bad_local_word_in(local, bad_words):
    for b in bad_words:
        if re.search(r"(?:^|[^a-z0-9])" + re.escape(b) + r"(?:$|[^a-z0-9])", local):
            return b
    return None
#  ⚠⚠ [라운드514] example.com·example.co.kr 만 있고 example.org·example.net
#    (RFC 2606 이 example.com 과 동급으로 예약한 나머지 두 도메인)이 빠져
#    있었다 — 실제로는 어느 회사도 등록할 수 없는 문서용 예약 도메인이라
#    둘 다 안전하게(오탐 위험 없이) 넣을 수 있다. 위 BAD_LOCAL 에서 지운
#    죽은 "webmaster@example" 항목이 막으려던 자리를 도메인 쪽에서 채운다.
BAD_DOMAIN = ("example.com", "example.co.kr", "example.org", "example.net",
              "domain.com", "sentry.io",
              "w3.org", "schema.org", "googleapis.com", "gstatic.com",
              "jquery.com", "bootstrapcdn.com", "cloudflare.com", "wordpress.org",
              # 홈페이지 제작 도구가 심어둔 기본값·수집기 주소.
              # 업체 주소가 아니라 플랫폼 주소라, 보내면 엉뚱한 회사에 간다.
              "mysite.com", "wixpress.com", "wix.com", "sentry.wixpress.com",
              "daangn.com", "karrotmarket.com", "imweb.me", "cafe24.com",
              #  ⚠⚠ [라운드647] "naver.com." 에 꼬리점이 붙어 있어 절대 못 맞는
              #    죽은 항목이었다(라운드514가 BAD_LOCAL에서 잡은 것과 같은
              #    클래스) — 실측: EMAIL_RE 의 도메인부는 `[A-Za-z]{2,}` 로
              #    끝나 애초에 정규식 매치 자체가 꼬리점을 포함할 수 없고,
              #    설령 포함하더라도 pick_emails() 가 그 앞에서 이미
              #    e.strip(".") 로 지운다 — 이중으로 절대 안 걸린다. 게다가
              #    clean_collected_emails.py:is_junk() 도 이 BAD_DOMAIN 을
              #    그대로 import 해 쓰므로(24행), 수집 시점과 사후 정리
              #    시점 둘 다 naver.com 주소(예: 네이버 위젯이 페이지에 남긴
              #    기본 문의주소)를 하나도 못 걸렀다.
              "modoo.at", "naver.com", "benefactory.me", "godo.co.kr")

# 업체 '홈페이지' 칸에 들어있지만 실제로는 남의 플랫폼인 주소들.
# 여기서 메일을 긁으면 그 플랫폼 운영사 주소가 잡히므로 아예 수집하지 않는다.
PLATFORM_HOSTS = ("daangn.com", "karrotmarket.com", "blog.naver.com", "cafe.naver.com",
                  "smartstore.naver.com", "place.map.kakao.com", "map.naver.com",
                  "instagram.com", "facebook.com", "youtube.com", "band.us",
                  "modoo.at", "blog.me", "tistory.com", "wixsite.com")
BAD_EXT = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js")

# 대표 연락처가 있을 법한 하위 경로 — 첫 페이지에 없으면 여기까지만 더 본다
SUB_PATHS = ["/contact", "/contact.html", "/contactus", "/about", "/company", "/inquiry"]


#  ⚠⚠ [라운드517] 이 파일이 실제로 접속하는 대상(website)은 협력사가 자기신고한
#    자유 텍스트다(app.py:5508 라운드509 주석 — 등급 무관 관리자 승인만으로
#    partners.website 에 그대로 저장된다). 그런데 이 파일은 그 값을 실제로
#    fetch() 해 **서버 자신이 그 주소로 접속**하면서도 호스트 검사가 전혀
#    없었다 — website 를 127.0.0.1(이 서버 자신)이나 내부망 주소로 적어
#    두면, 이 스크립트를 돌리는 순간 서버가 자기 내부망을 대신 두드리는
#    SSRF 가 된다. app.py 는 이미 같은 위험(웹훅 URL)을 _webhook_safe_ip() 로
#    막는데(라운드38·84·157이 다듬은 그 판정), 형제인 이 파일에는 그 방어가
#    없었다 — 같은 판정을 옮긴다.
#  ⚠ ponytail: 웹훅 방어(_webhook_safe_ip)와 달리 접속을 그 IP 하나에 못박지는
#    않는다(DNS 리바인딩 — 검사와 접속이 각각 다시 resolve하는 사이 응답이
#    바뀌는 공격 — 까지는 안 막는다). 이 도구는 상시 자동재시도가 아니라
#    운영자가 결과를 눈으로 보며 그때그때 수동으로 돌리는 1회성 배치라
#    노출 반복이 훨씬 적다. 필요해지면 app.py 의 _PinnedHTTPSConnection
#    패턴을 그대로 옮긴다.
_ALLOW_LOCAL_FETCH = os.environ.get("BOKGUON_COLLECT_ALLOW_LOCAL") == "1"  # 테스트 하네스 전용 — 운영에서 켜지 않는다


def _host_is_internal(hostname, port):
    """이 호스트가 내부/사설/예약 대역으로 해석되는가(app.py _webhook_safe_ip 와 같은 판정)."""
    if _ALLOW_LOCAL_FETCH:
        return False
    try:
        for info in socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP):
            ip = ipaddress.ip_address(info[4][0])
            #  ⚠ is_site_local 은 IPv4Address 에 없다 — app.py 라운드38 과 같은 이유로
            #    getattr 기본값을 쓴다. 공유주소공간(100.64.0.0/10)은 is_global 을
            #    더해 잡는다(app.py 라운드84).
            _v4 = getattr(ip, "ipv4_mapped", None) or ip
            if (ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved
                    or ip.is_multicast or ip.is_unspecified
                    or getattr(ip, "is_site_local", False)
                    or not _v4.is_global):
                return True
        return False
    except Exception:
        # 해석 자체가 안 되면(오타·존재하지 않는 도메인) 내부망 여부를 알 수
        # 없다 — 이 함수는 "내부망이 확인되면"만 막고, 그 밖의 접속 실패는
        # fetch() 자신의 실패 처리(로그+None)에 맡긴다(이중 판단 금지).
        return False


#  ⚠⚠ [라운드664] _host_is_internal() 은 **최초 접속 주소**만 본다 — website 가
#    공인 도메인(검사 통과)이어도 그 서버가 301/302 로 내부 주소(예:
#    169.254.169.254 나 127.0.0.1:8771/admin/...)를 가리키면, fetch() 의
#    urllib.request.urlopen() 도 robots_allows() 의 RobotFileParser 도 기본
#    오프너가 **그대로 따라가** 이 파일의 유일한 방어선을 완전히 우회한다.
#    app.py 의 웹훅 SSRF 방어가 정확히 이 경로를 "③ 리다이렉트를 따라가지
#    않는다"로 막는데(_NoRedirect, 위 [라운드517] 이 옮긴 것과 같은 계열의
#    방어인데 그때는 안 옮겨졌다 — 그 라운드의 ponytail 주석은 DNS 리바인딩만
#    논의했을 뿐 리다이렉트는 언급조차 없었다), 이 파일에는 없었다. 실측:
#    로컬 리다이렉터 서버(공인 주소인 척 통과)가 내부 서버로 302 를 보내자
#    urlopen() 도 RobotFileParser.read() 도 둘 다 내부 서버에 실제로 도달해
#    본문을 그대로 받아왔다(DNS 리바인딩과 달리 경합조건조차 필요 없이 매번
#    재현됨). app.py 와 같은 _NoRedirect 오프너를 두 접속 지점 모두에 쓴다 —
#    fetch() 는 이 오프너로 직접 열고, robots_allows() 는 RobotFileParser 가
#    내부에서 직접 urlopen() 을 부르므로(오프너를 주입할 방법이 없다) 그
#    호출 동안만 전역 기본 오프너를 바꿔치기한다(바로 아래 [라운드639] 의
#    소켓 타임아웃 save/restore와 같은 방식 — 호출 끝나면 원래대로 되돌린다).
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def fetch(url):
    """페이지 본문을 가져온다. 실패하면 None."""
    try:
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.hostname and _host_is_internal(parsed.hostname, port):
            _log.warning("%s 내부/사설 주소로 판정되어 접속을 막았습니다(SSRF 방어)", url)
            return None
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "ko,en;q=0.8",
        })
        with _NO_REDIRECT_OPENER.open(req, timeout=TIMEOUT) as r:
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "html" not in ctype and "text" not in ctype:
                return None
            raw = r.read(MAX_BYTES)
        text = None
        for enc in ("utf-8", "euc-kr", "cp949"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = raw.decode("utf-8", "replace")
        #  ⚠⚠ [라운드420] 여기서 자르면 refuses_collection()·pick_emails()
        #    양쪽(본문·하위경로 둘 다) 호출부를 안 건드리고 한 곳에서 막는다
        #    — MAX_SCAN_CHARS 정의부 주석 참조.
        return text[:MAX_SCAN_CHARS]
    except Exception as e:
        # 남의 사이트를 상대하는 일이라 실패 형태가 끝이 없다(깨진 주소·잘못된 인증서·
        # 이상한 인코딩·리다이렉트 루프…). 한 곳이 실패해도 수집 전체는 계속돼야 한다.
        #  ⚠ [라운드267] 반환값(None)은 그대로 두되(호출부를 안 건드린다), 형제
        #    (crypto_util.decrypt 라운드120·addr_search.search 라운드266)처럼
        #    실패 원인만 로그에 남긴다 — 타임아웃·DNS실패·403·429가 전부 똑같이
        #    "접속 실패" 한 줄로만 뭉개지면, 방화벽이 이 봇을 막기 시작해도
        #    운영자가 로그로는 원인을 못 알아챈다.
        _log.warning("%s 접속 실패 (%s: %s)", url, type(e).__name__, e)
        return None


def robots_allows(base, path="/"):
    """robots.txt 가 막지 않는지 확인. 읽지 못하면 보수적으로 허용.

    ⚠⚠ [라운드517] fetch() 의 SSRF 방어(위 _host_is_internal 주석 참고)만으로는
      부족했다 — 이 함수도 robots.txt 를 얻으려고 **직접 접속**하는데,
      collect_one() 은 fetch() 보다 이 함수를 먼저 부른다. 실측: website 를
      127.0.0.1 로 둔 채 fetch() 만 막았더니 본문 요청은 안 갔지만
      robots.txt 요청은 실제로 내부 서버에 도달했다 — 같은 검사를 여기도
      건다(못 읽으면 허용하는 기존 원칙과 달리, 내부망으로 확인되면 그
      자리에서 즉시 차단 — 두 판정을 안 섞는다).

    ⚠⚠ [라운드639] RobotFileParser.read() 는 timeout 인자를 받지 않는다
      (표준 라이브러리 내부에서 `urllib.request.urlopen(self.url)` 을 인자
      없이 호출 — 실제 소스로 확인). 그래서 이 파일의 다른 모든 네트워크
      호출(fetch() 의 TIMEOUT=8초)과 달리, 이 함수만은 응답이 없는 서버를
      만나면 무한정 멈춘다 — 이 모듈 자신의 원칙("응답이 느리거나 막히면
      그냥 건너뛴다", 파일 맨 위 docstring)이 바로 이 자리에서만 깨진다.
      게다가 collect_one() 은 이 함수를 fetch() 보다 먼저, 사이트 한 곳당
      최대 7번(진입 1회 + SUB_PATHS 6회) 부른다 — 서버 하나가 응답 없이
      연결만 붙들면 --all 배치 전체가 그 자리에서 영구히 멈춘다(실측:
      바이트를 전혀 안 보내는 로컬 TCP 리스너로 재현 — 고치기 전에는
      12초를 기다려도 반환되지 않았다). 프로세스 전역 소켓 기본 타임아웃을
      이 호출 하나에만 잠깐 걸었다 그대로 복원한다 — rp.read() 자체의
      HTTP 오류코드 처리(401/403 전체거부·기타 4xx 전체허용)를 재구현하지
      않고 그대로 재사용할 수 있는 가장 작은 변경이다.
    """
    try:
        parsed = urlparse(base)
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        if parsed.hostname and _host_is_internal(parsed.hostname, port):
            return False
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(urljoin(base, "/robots.txt"))
        _old_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(TIMEOUT)
        #  ⚠⚠ [라운드664] RobotFileParser 는 오프너를 주입받을 방법이 없다(내부에서
        #    직접 urllib.request.urlopen() 을 부른다) — 이 호출 동안만 전역 기본
        #    오프너를 _NoRedirect 로 바꿔치기한다(위 클래스 정의부 주석 참고).
        _old_opener = urllib.request._opener
        urllib.request.install_opener(_NO_REDIRECT_OPENER)
        try:
            rp.read()
        finally:
            urllib.request.install_opener(_old_opener)
            socket.setdefaulttimeout(_old_timeout)
        return rp.can_fetch(UA, urljoin(base, path))
    except Exception:
        return True


def refuses_collection(html):
    """§50-2 — 수집 거부 의사가 명시돼 있는가."""
    #  ⚠⚠ [라운드267] 공백만 지우고 태그는 그대로 두면, 문구 중간에 인라인
    #    태그 하나만 끼어도(스크롤 애니메이션·번역위젯이 흔히 <span>으로
    #    단어를 감싸고, <b>·<br> 강조도 흔하다) 연속 문자열 매치가 깨져
    #    수집거부 의사를 놓친다 — §50-2 가 막으려는 바로 그 상황이 코드
    #    결함으로 뚫린다(미탐). 태그부터 지운 뒤 공백을 지운다.
    #  ⚠⚠ [라운드648] REFUSE_MARKERS 8개 중 유일한 비(非)한글 항목인
    #    "email collection denial" 은 이미 전부 소문자인데, 이 함수는 flat
    #    에 .lower() 를 한 번도 안 걸었다 — 한글은 대소문자가 없어 나머지
    #    7개는 영향이 없지만, 이 영문 항목만은 페이지가 "Email Collection
    #    Denial"·"EMAIL COLLECTION DENIAL"처럼 다른 대소문자로 적으면(사람이
    #    직접 쓰는 영문 문구라 표기가 갈릴 수 있다) 정확히 이 문구를 명시한
    #    사이트조차 못 거른다(실측: 대문자 섞은 샘플로 재현 — 아래 회귀
    #    테스트 참고). 대소문자만 접고 비교한다.
    flat = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", html)).lower()
    return any(re.sub(r"\s+", "", m).lower() in flat for m in REFUSE_MARKERS)


def pick_emails(html, site_host):
    """본문에서 쓸 만한 이메일만 골라낸다. 같은 도메인 주소를 우선한다."""
    found, seen = [], set()
    for m in EMAIL_RE.findall(html):
        e = m.strip().strip(".").lower()
        if e in seen:
            continue
        seen.add(e)
        local, _, dom = e.partition("@")
        if _bad_local_word_in(local, BAD_LOCAL):
            continue
        if any(dom.endswith(b) for b in BAD_DOMAIN):
            continue
        if any(e.endswith(x) for x in BAD_EXT):
            continue
        if len(e) > 100:
            continue
        found.append(e)
    # 회사 도메인과 같은 주소가 있으면 그게 대표 연락처일 가능성이 높다
    host = (site_host or "").replace("www.", "")
    found.sort(key=lambda x: (0 if host and host in x.split("@")[-1] else 1, len(x)))
    return found


def collect_one(website):
    """사이트 한 곳에서 이메일을 찾는다. (emails, note) 반환."""
    website = (website or "").strip()
    if not website or re.search(r"[\s\x00-\x1f]", website):
        return [], "홈페이지 주소 형식 오류"
    url = website if website.startswith("http") else "https://" + website
    try:
        parsed = urlparse(url)
    except ValueError:
        return [], "홈페이지 주소 형식 오류"
    if not parsed.netloc:
        return [], "홈페이지 주소 형식 오류"
    host = parsed.netloc.lower()
    if any(h in host for h in PLATFORM_HOSTS):
        return [], "업체 사이트가 아님(플랫폼 페이지)"
    base = f"{parsed.scheme}://{parsed.netloc}"
    if not robots_allows(base, parsed.path or "/"):
        return [], "robots.txt 차단"
    html = fetch(url)
    if not html:
        return [], "접속 실패"
    if refuses_collection(html):
        return [], "수집거부 명시(§50-2) — 건너뜀"
    emails = pick_emails(html, parsed.netloc)
    if emails:
        return emails, "첫 페이지"
    # 첫 페이지에 없으면 연락처 성격의 하위 경로를 더 본다
    #  ⚠⚠ [라운드218] 여기 robots.txt 검사가 아예 빠져 있었다 — 형제인
    #    refuses_collection() 은 이 루프 안에서도 매번 재검사되는데, 똑같이
    #    경로별로 검사해야 하는 robots_allows() 는 진입 URL 한 번뿐이었다.
    #    "/" 는 허용하면서 "/contact" 류만 막는 robots.txt 는 실무에 흔하고,
    #    이 스크립트가 가장 많이 찾아가는 바로 그 경로다(실측: 로컬 서버로
    #    재현, Disallow: /contact 인데도 그 페이지 메일이 그대로 수집됐다).
    #    ⚠ [:4] 슬라이스도 함께 없앤다 — SUB_PATHS 6개 중 뒤 2개(/company,
    #    /inquiry)가 이유 설명 없이 영구히 시도조차 안 되고 있었다.
    for sp in SUB_PATHS:
        if not robots_allows(base, sp):
            continue
        time.sleep(PAUSE)
        sub = fetch(urljoin(base, sp))
        if not sub:
            continue
        if refuses_collection(sub):
            return [], "수집거부 명시(§50-2) — 건너뜀"
        emails = pick_emails(sub, parsed.netloc)
        if emails:
            return emails, f"하위 {sp}"
    return [], "이메일 없음"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=30, help="처리할 업체 수")
    ap.add_argument("--all", action="store_true", help="홈페이지 있는 전 업체")
    ap.add_argument("--dry", action="store_true", help="저장하지 않고 결과만 출력")
    a = ap.parse_args()

    conn = DB.get_db()
    rows_ = conn.execute(
        """SELECT id, name, website FROM partners
            WHERE status='활성'
              AND TRIM(COALESCE(website,''))<>''
              AND TRIM(COALESCE(email,''))=''
            ORDER BY partner_type, name""").fetchall()
    targets = list(rows_) if a.all else list(rows_)[:a.limit]

    print("=" * 62)
    print(f"  이메일 수집 — 대상 {len(targets)}곳 (홈페이지 보유·이메일 미보유)")
    print(f"  {'저장하지 않음(--dry)' if a.dry else '찾으면 저장합니다'}")
    print("=" * 62)

    got = skipped = failed = refused = 0
    for i, r in enumerate(targets, 1):
        try:
            emails, note = collect_one(r["website"])
        except Exception as ex:
            emails, note = [], f"오류({type(ex).__name__})"
        if emails:
            got += 1
            best = emails[0]
            mark = "저장" if not a.dry else "발견"
            print(f"  [{i}/{len(targets)}] {mark} {r['name'][:22]:24s} {best}  ({note})")
            if not a.dry:
                try:
                    conn.execute(
                        """UPDATE partners
                              SET email=?, email_source='수집(홈페이지)',
                                  --  ⚠⚠ [라운드299] 예전엔 무조건 0 이었다 — 이 SELECT
                                  --    는 email='' 인 행만 고르지만, 그 행이 신청승인
                                  --    때(마케팅 수신동의 체크, 이메일란은 비워 둔 채)
                                  --    이미 email_consent=1 을 받아 둔 경우가 있을 수
                                  --    있다(실측: 격리 DB로 이 상태를 만들어 재현 —
                                  --    이 UPDATE 한 번으로 진짜 동의가 조용히 0으로
                                  --    영구히 사라지고, 되돌릴 화면이 앱 어디에도
                                  --    없었다). 이미 1(실제 동의)이면 그대로 두고,
                                  --    그 밖(0·NULL, 즉 동의한 적 없음)은 예전처럼 0으로
                                  --    명시해 "공개된 연락처일 뿐 동의 아님"을 남긴다.
                                  email_consent=CASE WHEN email_consent=1 THEN 1 ELSE 0 END,
                                  email_collected_at=?, contact_updated=?
                            WHERE id=?""",
                        (best, DB.now(), DB.now(), r["id"]))
                    conn.commit()
                except Exception as ex:
                    #  ⚠⚠ [라운드267] 이 UPDATE·commit 이 여태 collect_one() 의
                    #    try/except 밖에 있어서, 락 경합·디스크 오류 등으로 저장
                    #    하나가 실패하면 이미 찾아 둔 나머지 대상까지 배치 전체가
                    #    무방비로 죽었다(실행으로 확인: 이 자리 예외가 main() 밖
                    #    으로 그대로 전파). 이 행만 건너뛰고 계속한다 — 재실행하면
                    #    이 업체는 여전히 이메일 미보유로 다시 뽑혀 재시도된다.
                    conn.rollback()
                    got -= 1
                    failed += 1
                    _log.warning("협력사 #%s 이메일 저장 실패 — 건너뜀 (%s: %s)",
                                  r["id"], type(ex).__name__, ex)
        else:
            if "수집거부" in note:
                refused += 1
            elif "실패" in note or "robots" in note or "오류" in note or "형식" in note:
                failed += 1
            else:
                skipped += 1
            print(f"  [{i}/{len(targets)}] ---- {r['name'][:22]:24s} {note}")
        time.sleep(PAUSE)

    conn.close()
    print("-" * 62)
    print(f"  수집 {got} · 이메일없음 {skipped} · 접속실패 {failed} · 수집거부 {refused}")
    print()
    print("  ⚠ 여기서 얻은 주소는 '공개된 연락처'이지 광고 수신 동의가 아닙니다.")
    print("    email_consent=0 으로 저장되며, 광고성 발송 전에는 동의를 받아야 합니다")
    print("    (정보통신망법 §50①). 1:1 사업 제안·전화 후 안내 용도로 쓰세요.")


if __name__ == "__main__":
    sys.exit(main())
