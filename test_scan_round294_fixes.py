# -*- coding: utf-8 -*-
"""스캔 294라운드 회귀 — addr_search.py·build_pages.py 미조사 함수 결함 3건,
   addr_search.py 는 266라운드가 search()/_official()/_open_map() 만 다루고
   나머지 6개(_key·provider·_get·_sigungu·_building_of·demo), build_pages.py
   는 230라운드가 strip_jinja() 만 다루고 나머지 5개(_read·_write·
   drop_unfilled_rows·fix_links·build)는 이 세션 사상 첫 정밀조사한
   정밀조사 Agent가 발견 — _key·provider·_sigungu·_building_of·demo,
   _read·_write·fix_links·build 자체 로직은 실측 결과 전부 클린.

  ① addr_search.py search() 의 except 튜플에 http.client.HTTPException 이
     빠져 있었다. 이 파일이 키 없이 쓰는 무인증 엔드포인트(_open_map,
     이 파일 자신의 docstring이 "언제든 바뀔 수 있다"고 이미 경고하는
     그 API)가 Content-Length 보다 적게 보내고 연결을 끊으면 _get() 의
     r.read() 가 IncompleteRead 를 내는데, 이건 HTTPException 의
     하위클래스라 OSError 계열이 아니어서 기존 except 어디에도 안 걸려
     "실패하면 빈 목록"이라는 이 함수 자신의 계약을 깨고 그대로 새 나갔다
     (실측: 가짜 TCP 서버로 재현 — Content-Length 100 인데 10바이트만
     보내고 끊음, MRO 로 OSError/URLError 어느 쪽도 아님을 확인).
     geocode_fill.py 의 배치 루프(rows_to_fill 이후 for 문)는 267라운드가
     DB UPDATE/commit 실패만 감쌌지 검색 호출 자체(154·166행)는 안
     감싸서, 이 예외가 새면 남은 행 전부(최대 --limit, 기본 500건)가
     통째로 죽었을 것이다.
  ② build_pages.py drop_unfilled_rows() 가 페이지 전체에서 "(미기재)"가
     들어간 <tr> 을 닥치는 대로 지웠다 — 이 함수 자신의 문서화된 목적은
     처리방침 제6조(위탁) 표의 미확정 수탁자 행만 빼는 것인데, 같은
     _ph() 표시 방식이 제12조 개인정보 보호책임자·연락처 행과 사업자정보
     표의 통신판매업 신고번호·대표전화·개인정보 보호책임자 행에도 똑같이
     쓰인다. 그 값이 하나라도 비면 자리표시자만 지워지는 게 아니라 행
     전체(제목 칸까지)가 통째로 사라져, 전자상거래법 §10·개인정보
     보호법 §30 표시의무 항목이 "표시 안 됨"이 아니라 "애초에 없던 것"
     처럼 보였다(실측: company_info.json 에서 dpo·mail_order_no 를 비우고
     실제로 빌드해 재현 — 두 표에서 행이 사라짐. 현재 운영값은 전부
     채워져 있어 지금 당장 발현 중은 아니다). 제6조 절 범위로 정확히
     좁혔다.
  ③ build_pages.py 의 "회사 정보 N/8 반영" 로그가 len(info)(JSON 키
     개수)를 세어, 키는 있지만 값이 비었거나 공백뿐이면(_ph() 기준으로는
     명백한 미기재) 그대로 채워진 것으로 셌다 — "미확정 수탁자 N행
     제외" 경고와 "8/8 반영"이 같은 실행에서 동시에 찍힐 수 있었다.
     _ph() 와 같은 기준(비거나 공백뿐이면 미기재)으로 세도록 수정.

      python test_scan_round294_fixes.py
"""
import http.client
import io
import os
import socket
import sys
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
PASS, FAIL = [], []


def chk(cond, name, detail=""):
    (PASS if cond else FAIL).append((name, detail))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + ("" if cond else f"   {detail}"))


def read(rel):
    return io.open(os.path.join(HERE, rel), encoding="utf-8").read()


ADDR_SRC = read("addr_search.py")
BP_SRC = read("build_pages.py")

print("=" * 72)
print("  스캔 294라운드 회귀 — addr_search.py·build_pages.py 결함 3건")
print("=" * 72)

# ============================================================
print("\n[1] 소스 확인")
# ------------------------------------------------------------
chk("import http.client" in ADDR_SRC,
    "★★★ addr_search.py 가 http.client 를 import 한다")
chk("http.client.HTTPException" in ADDR_SRC,
    "★★★ search() 의 except 튜플에 http.client.HTTPException 이 있다")
chk('SECTION_START = "<h3>제6조 (개인정보 처리의 위탁)</h3>"' in BP_SRC,
    "★★★ drop_unfilled_rows() 가 제6조 절로 범위를 좁힌다")
chk("filled = sum(1 for v in info.values() if (v or \"\").strip())" in BP_SRC,
    "★★★ 회사 정보 완성도 집계가 _ph() 와 같은 기준(공백도 미기재)을 쓴다")

# ============================================================
print("\n[2] 실행 — addr_search.py: IncompleteRead 를 실제로 재현")
#      (외부 네트워크 없이 127.0.0.1 자체 서버만 쓴다)
# ------------------------------------------------------------
sys.path.insert(0, HERE)
try:
    import addr_search as ADDR

    def _fake_server(sock):
        conn, _ = sock.accept()
        try:
            conn.recv(4096)
            # Content-Length 100 이라 해 놓고 10바이트만 보내고 끊는다
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n0123456789")
        finally:
            conn.close()

    def _start_fake_server():
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        threading.Thread(target=_fake_server, args=(s,), daemon=True).start()
        return port

    # 2-a: _get() 자신은 여전히 raise 한다(회귀 없음 — 이 자리는 안 고쳤다)
    p1 = _start_fake_server()
    try:
        ADDR._get(f"http://127.0.0.1:{p1}/")
        chk(False, "_get() 이 IncompleteRead 를 내야 하는데 안 남")
    except http.client.HTTPException as e:
        chk(True, "_get() 은 여전히 IncompleteRead 를 그대로 낸다(회귀 없음)", type(e).__name__)
    except Exception as e:                                          # noqa: BLE001
        chk(False, "_get() 이 예상과 다른 예외를 냄", f"{type(e).__name__} {e}")

    # 2-b: search() 는 이제 그 예외를 삼키고 빈 목록을 돌려준다
    p2 = _start_fake_server()
    _orig_open_map = ADDR._open_map
    _orig_key = ADDR._key
    ADDR._open_map = lambda q: ADDR._get(f"http://127.0.0.1:{p2}/")
    ADDR._key = lambda: ""       # 무인증 경로(_open_map) 강제
    try:
        result = ADDR.search("테스트 주소 아무거나 123")
        chk(result == [],
            "★★★ search() 가 IncompleteRead 를 삼키고 빈 목록을 돌려준다"
            "(고치기 전엔 이 자리에서 그대로 죽어 geocode_fill.py 배치 전체가 멈췄다)",
            result)
    finally:
        ADDR._open_map = _orig_open_map
        ADDR._key = _orig_key
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드294 [2] addr_search.py IncompleteRead 검증", f"{type(e).__name__} {e}")

# ============================================================
print("\n[3] 실행 — build_pages.py: drop_unfilled_rows() 범위 정확성")
# ------------------------------------------------------------
try:
    import build_pages as BP

    html = (
        '<h3>제6조 (개인정보 처리의 위탁)</h3>\n'
        '<table class="ltbl">\n'
        '  <tr><th>수탁자</th><th>위탁 업무의 내용</th></tr>\n'
        '  <tr><td>호스팅업체</td><td>서버 임대</td></tr>\n'
        '  <tr><td><span class="ph">PG (미기재)</span></td><td>정산 대금 이체</td></tr>\n'
        '</table>\n'
        '<h3>제7조 (개인정보의 안전성 확보조치)</h3>\n'
        '<p>내용...</p>\n'
        '<h3>제12조 (개인정보 보호책임자)</h3>\n'
        '<table class="ltbl">\n'
        '  <tr><th>구분</th><th>내용</th></tr>\n'
        '  <tr><td>개인정보 보호책임자</td>'
        '<td><span class="ph">개인정보 보호책임자 (미기재)</span></td></tr>\n'
        '  <tr><td>연락처</td><td>010-0000-0000</td></tr>\n'
        '</table>\n'
    )
    out = BP.drop_unfilled_rows(html)
    chk("PG (미기재)" not in out and "정산 대금 이체" not in out,
        "★★★ 제6조(위탁) 표의 미확정 행은 여전히 제거된다(회귀 없음)")
    chk("개인정보 보호책임자" in out and "(미기재)" in out,
        "★★★ 제12조(DPO) 표의 미기재 행은 더는 지워지지 않는다"
        "(고치기 전엔 페이지 전체에서 '(미기재)' 들어간 행을 닥치는 대로 지웠다)")
    chk("호스팅업체" in out, "제6조 표의 정상(채워진) 행은 그대로 남는다(회귀 없음)")

    # 제6조 절 자체가 없는 문서(약관·사업자정보)는 완전히 손대지 않아야 한다
    html2 = ('<h3>제5조 (다른 조항)</h3>\n'
             '<table><tr><td><span class="ph">필드 (미기재)</span></td></tr></table>\n')
    out2 = BP.drop_unfilled_rows(html2)
    chk(out2 == html2,
        "★★★ 제6조(위탁) 절이 없는 문서는 완전히 그대로 반환된다(약관·사업자정보 보호)")
except Exception as e:                                              # noqa: BLE001
    chk(False, "★★★ 라운드294 [3] build_pages.py drop_unfilled_rows() 검증", f"{type(e).__name__} {e}")

print("\n" + "=" * 72)
print(f"  통과 {len(PASS)} · 실패 {len(FAIL)}")
if FAIL:
    print("\n  실패 항목:")
    for nm, dt in FAIL:
        print(f"    · {nm}\n        {dt}")
print("=" * 72)
sys.exit(1 if FAIL else 0)
