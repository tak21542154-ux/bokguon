# -*- coding: utf-8 -*-
"""전체 검증 한 번에 — 순서·간격까지 이 파일이 안다.

  왜 필요한가 —
   테스트가 20개 가까이 쌓였는데 **어느 것을 어떤 순서로 어떤 환경에서** 돌려야
   하는지가 사람 머릿속에만 있었다. 그러면 인수인계가 안 되고, 실테스트 전날
   "전부 통과했나"를 확인할 방법이 없다.

  ⚠ 세 가지 함정을 이 파일이 대신 피한다.
   ① **로그인 레이트리밋(10회/300초).** HTTP 테스트를 연달아 돌리면 뒤쪽이
      통째로 401/429 로 죽는데, 코드 결함처럼 보인다. 그래서 간격을 둔다.
   ② **DB 를 잘못 가리키는 것.** 검증 테스트는 반드시 verify.db 를 봐야 한다.
      운영 DB 를 가리키면 실데이터에 검증 사건이 박힌다.
   ③ **서버를 잘못 가리키는 것.** ②를 막아 놓고도 2026-08-06 에 두 테스트가
      운영(8771)을 두드렸다 — 이 파일이 BOKGUON_TEST_BASE 를 **자식에게 안 넘겨서**
      각자의 기본값을 썼고, 그 둘만 기본이 운영이었다. 로그인이 실패해 드러났을
      뿐, 비밀번호가 맞았으면 ②와 똑같은 사고가 났다.
      → run() 이 base 를 환경변수로 넘기고, 사전 점검이 **채널이 '개발'인지** 본다.

  쓰는 법:
      python run_all_tests.py                 # 단위 + HTTP 전부(HTTP 레이트리밋 대기만 50분 안팎)
      python run_all_tests.py --quick         # 단위만(1분, 서버 불필요)
      python run_all_tests.py --no-wait       # 간격 없이(레이트리밋 감수)

  비밀번호는 **환경변수로만** 받는다(코드에 넣지 않는다):
      BOKGUON_TEST_ADMIN_PW / _STAFF_PW / _INSURER_PW / _PARTNER_PW
"""
import json
import os
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

#  ── 서버가 필요 없는 것들 (로그인을 안 하므로 레이트리밋과 무관) ──
UNIT = [
    #  ⚠ 이건 맨 앞에 둔다 — 새 DB 생성이 깨지면 **새 서버 배포가 통째로 막힌다**.
    #     기존 DB 로 도는 다른 테스트는 전부 통과해서 아무도 못 잡는다.
    ("test_fresh_db.py", "새 DB 생성(배포 첫 관문)"),
    ("test_dead_actions.py", "죽은 버튼(data-act ↔ ACT)"),
    #  화면이 뜨는지 자체를 본다 — 인라인 JS 구문이 깨지면 서버는 200 인데 화면만 죽는다.
    ("test_template_js.py", "템플릿 인라인 JS 구문"),
    #  배포 파일(크론)까지 본다 — 예약 실행이 안 걸리면 코드는 멀쩡한데 현장만 멈춘다.
    ("test_scan_round6_fixes.py", "스캔 6라운드 회귀(배포·감사·되돌림)"),
    ("test_scan_round7_fixes.py", "스캔 7라운드 회귀(부분실패·동시·복구·오프라인)"),
    ("test_scan_round8_fixes.py", "스캔 8라운드 회귀(돈·세션·보증·오조작)"),
    ("test_scan_round9_fixes.py", "스캔 9라운드 회귀(자기도구·권한·경쟁정보·인수인계)"),
    ("test_scan_round10_fixes.py", "스캔 10라운드 회귀(9라운드 부작용·데이터파괴·설정)"),
    ("test_scan_round11_fixes.py", "스캔 11라운드 회귀(법률철칙·DoS·무한루프)"),
    ("test_scan_round12_fixes.py", "스캔 12·13라운드 회귀(반쯤붙인수정·go-live직후·돈·첫주동선)"),
    ("test_scan_round14_fixes.py", "스캔 14라운드 회귀(적대적검토·죽은계정·등급문턱·명의)"),
    ("test_scan_round15_fixes.py", "스캔 15라운드 회귀(첫주 출동수배 교착)"),
    ("test_scan_round16_fixes.py", "스캔 16라운드 회귀(폰 탭바·업로드큐 격리)"),
    ("test_scan_round17_fixes.py", "스캔 17라운드 회귀(형제 경로 누락 전수)"),
    ("test_scan_round18_fixes.py", "스캔 18라운드 회귀(시키는 일을 할 문)"),
    ("test_scan_round19_fixes.py", "스캔 19라운드 회귀(앞 라운드가 깨운 분기·이름·입구)"),
    ("test_scan_round20_fixes.py", "스캔 20라운드 회귀(원경매 중복·상한 0원 표기)"),
    ("test_scan_round21_fixes.py", "스캔 21라운드 회귀(교착 입구·출구)"),
    ("test_scan_round22_fixes.py", "스캔 22라운드 회귀(삭제·통지·엑셀·감사로그)"),
    ("test_scan_round23_fixes.py", "스캔 23라운드 회귀(형제 중 하나만 빠진 자리)"),
    ("test_scan_round24_fixes.py", "스캔 24라운드 회귀(NULL/0 혼동·갇힌 변경건)"),
    ("test_scan_round25_fixes.py", "스캔 25라운드 회귀(배포 스크립트·공개 폼·알림 매핑)"),
    ("test_scan_round26_fixes.py", "스캔 26라운드 회귀(실적 재계산·지급 문구·협력업체 엑셀·온보딩 카드)"),
    ("test_scan_round27_fixes.py", "스캔 27라운드 회귀(하자 완료·반려 상충·손상사진 거부·잠금 해제)"),
    ("test_scan_round28_fixes.py", "스캔 28라운드 회귀(직접배정 재배차 무통지)"),
    ("test_scan_round29_fixes.py", "스캔 29라운드 회귀(1차 합의 결렬 뒤 재상신 차단)"),
    ("test_scan_round30_fixes.py", "스캔 30라운드 회귀(검색 가운뎃점 정규화·하자보증 만료 알림)"),
    ("test_scan_round31_fixes.py", "스캔 31라운드 회귀(검색어 와일드카드 이스케이프·me 3형제 생존확인)"),
    ("test_scan_round32_fixes.py", "스캔 32라운드 회귀(계좌키 복호화 왕복검증·지오코딩 한반도 범위)"),
    ("test_scan_round34_fixes.py", "스캔 34라운드 회귀(협력사 계정발급 CSV 수식 인젝션)"),
    ("test_scan_round36_fixes.py", "스캔 36라운드 회귀(저장형 XSS 4곳 — admin.js·insurer_portal.html)"),
    ("test_scan_round37_fixes.py", "스캔 37라운드 회귀(OTP 코드 무차별 대입 계정 잠금)"),
    ("test_scan_round38_fixes.py", "스캔 38라운드 회귀(웹훅 SSRF 방어의 IPv4 전면 차단 버그)"),
    ("test_scan_round39_fixes.py", "스캔 39라운드 회귀(로그인 타이밍 사이드채널 — 아이디 존재 노출)"),
    ("test_scan_round42_fixes.py", "스캔 42라운드 회귀(낙찰 확정 3곳 금액 이중 방어)"),
    ("test_scan_round45_fixes.py", "스캔 45라운드 회귀(로그인잠금·알림벨 인덱스)"),
    ("test_scan_round46_fixes.py", "스캔 46라운드 회귀(N+1 쿼리 4곳)"),
    ("test_scan_round47_fixes.py", "스캔 47라운드 회귀(LIMIT 없는 목록 쿼리 5곳)"),
    ("test_scan_round49_fixes.py", "스캔 49라운드 회귀(사진 파일 정리 2곳)"),
    ("test_scan_round50_fixes.py", "스캔 50라운드 회귀(알림 스윕 5곳 동시성)"),
    ("test_scan_round51_fixes.py", "스캔 51라운드 회귀(재경매 무등록·데모 차단, 사진용량 상한)"),
    ("test_scan_round52_fixes.py", "스캔 52라운드 회귀(도급 확정 4곳 무등록·비활성 재확인)"),
    ("test_scan_round53_fixes.py", "스캔 53라운드 회귀(협력사 하위계정 등급 게이트 누락 4곳)"),
    ("test_scan_round54_fixes.py", "스캔 54라운드 회귀(협력사 로그인 잠금 무한연장·해제실패, 등급3곳)"),
    ("test_scan_round55_fixes.py", "스캔 55라운드 회귀(발주처 부동의 금액 확정 CRITICAL, 하자 상태전이 무가드)"),
    ("test_scan_round56_fixes.py", "스캔 56라운드 회귀(지도필터·배지드릴다운·오늘할일·사진분류 4곳)"),
    ("test_scan_round57_fixes.py", "스캔 57라운드 회귀(도급 적법성 관문 누락2곳·판정기준불일치·NaN크래시)"),
    ("test_scan_round58_fixes.py", "스캔 58라운드 회귀(개산엔진 choice검증·수량식·단가단위불일치·죽은게이트·엑셀정제)"),
    ("test_scan_round59_fixes.py", "스캔 59라운드 회귀(경매마감 스윕 TOCTOU 경합·종결상태 CASE_OPEN_SQL 드리프트 4곳)"),
    ("test_scan_round60_fixes.py", "스캔 60라운드 회귀(하자사진 열람 IDOR 비대칭·업체강등 열린하자 사각지대)"),
    ("test_scan_round61_fixes.py", "스캔 61라운드 회귀(하자이의 무응답·절감기준선 SQL/파이썬 불일치·LIKE이스케이프)"),
    ("test_scan_round62_fixes.py", "스캔 62라운드 회귀(api_co_decision 업체상태·등록 재확인 누락)"),
    ("test_scan_round63_fixes.py", "스캔 63라운드 회귀(입점신청 직접접수 경로 주소 누락)"),
    ("test_scan_round64_fixes.py", "스캔 64라운드 회귀(실적재계산 평점 하자차감 삭제·무보증0개월 4곳 오표시)"),
    ("test_scan_round65_fixes.py", "스캔 65라운드 회귀(개인정보 파기 예약이 윈도 배포엔 없었음·셀프디텍션 보강)"),
    ("test_scan_round66_fixes.py", "스캔 66라운드 회귀(접속기록파기 셀프디텍션·restore 무결성확인·사진백업 점검·배포문서 5종)"),
    ("test_scan_round67_fixes.py", "스캔 67라운드 회귀(naive datetime.now() KST 어긋남 5곳·장식 시계점검·help 누락)"),
    ("test_scan_round68_fixes.py", "스캔 68라운드 회귀(사건/보험사 등록 레이스 2곳·데모시드 KST 3곳·일정삭제 권한·백업문서)"),
    ("test_scan_round69_fixes.py", "스캔 69라운드 회귀(LED보안등 자재SKU 오류·go-live 커밋전 파일삭제 트랜잭션 무보호)"),
    ("test_scan_round70_fixes.py", "스캔 70라운드 회귀(연락처 일괄등록 트랜잭션 무제한보유·예외정리 누락·인덱스부재)"),
    ("test_scan_round71_fixes.py", "스캔 71라운드 회귀(사진업로드 3경로 사건상한 레이스·AI자동승인 덮어쓰기 레이스)"),
    ("test_scan_round72_fixes.py", "스캔 72라운드 회귀(AI 파손분석 결과 순서보장 없는 덮어쓰기)"),
    ("test_scan_round73_fixes.py", "스캔 73라운드 회귀(2차경매 개시 미분류사진 일괄분류 화이트리스트 누락·로그부정확)"),
    ("test_scan_round74_fixes.py", "스캔 74라운드 회귀(admin.js 조회실패 삼킴 2곳·카운트다운 반올림 사본 2곳)"),
    ("test_scan_round75_fixes.py", "스캔 75라운드 회귀(insurer_portal.html 정렬·상태색 사본 드리프트 2곳)"),
    ("test_scan_round76_fixes.py", "스캔 76라운드 회귀(insurer_portal.html 업로드중 강제이동 유예 UP_BUSY 누락)"),
    ("test_scan_round77_fixes.py", "스캔 77라운드 회귀(admin.js 업로드중 강제이동 유예 UP_BUSY 누락)"),
    ("test_scan_round78_fixes.py", "스캔 78라운드 회귀(돈·퍼센트 표시 형제사본 드리프트 3곳)"),
    ("test_scan_round79_fixes.py", "스캔 79라운드 회귀(재경매 자릿수 방어 헐거움·사업자번호 검사 누락 4곳)"),
    ("test_scan_round80_fixes.py", "스캔 80라운드 회귀(이메일 형식 검사 누락 5곳)"),
    ("test_scan_round81_fixes.py", "스캔 81라운드 회귀(엑셀 내보내기 제목 셀 _xl_safe 누락 2곳)"),
    ("test_scan_round84_fixes.py", "스캔 84라운드 회귀(웹훅 CGNAT SSRF·주소스냅샷·재전송 경합 3건)"),
    ("test_scan_round85_fixes.py", "스캔 85라운드 회귀(완료승인 독촉 쿨다운 확인-삽입 경합)"),
    ("test_scan_round86_fixes.py", "스캔 86라운드 회귀(가견적 표시·집행 불일치 — bid_floor 미사용·상한가드 극값오류)"),
    ("test_scan_round87_fixes.py", "스캔 87라운드 회귀(표준단가 등록 검증누락·마케팅 수신자 채널판정 불일치)"),
    ("test_scan_round88_fixes.py", "스캔 88라운드 회귀(AI 정확도 자기일치 오염·달력 출동기한 데모누락)"),
    ("test_scan_round89_fixes.py", "스캔 89라운드 회귀(하자 귀책 조정 화면 입구 부재)"),
    ("test_scan_round90_fixes.py", "스캔 90라운드 회귀(업체 응답이력 데모오염·보험사 공지 부재/개수제한)"),
    ("test_scan_round91_fixes.py", "스캔 91라운드 회귀(사진재사용 데모오염·낙찰취소 변경견적 가드누락)"),
    ("test_scan_round92_fixes.py", "스캔 92라운드 회귀(실적·표본 통계 4곳 죽은 컬럼 stats_exclude)"),
    ("test_scan_round93_fixes.py", "스캔 93라운드 회귀(실적표본 통계 2곳 경매/1차합의 미분리)"),
    ("test_scan_round94_fixes.py", "스캔 94라운드 회귀(1차합의 승인/부동의 로그 사건번호 형식불일치)"),
    ("test_scan_round95_fixes.py", "스캔 95라운드 회귀(dispatch.py 감사로그 11곳 사건번호 형식통일)"),
    ("test_scan_round96_fixes.py", "스캔 96라운드 회귀(settlements 데모표식 미상속·go-live 미리보기 과소집계)"),
    ("test_scan_round97_fixes.py", "스캔 97라운드 회귀(웹훅이 데모사건을 실제 보험사 서버로 전송)"),
    ("test_scan_round98_fixes.py", "스캔 98라운드 회귀(연락처 일괄등록 형식오류 행 누락집계)"),
    ("test_scan_round99_fixes.py", "스캔 99라운드 회귀(mark-smoke-demo 자식표 캐스케이드 정본화)"),
    ("test_scan_round100_fixes.py", "스캔 100라운드 회귀(하자점수 술어불일치·최저가게이트 모집단·데모캐스케이드 2건)"),
    ("test_scan_round101_fixes.py", "스캔 101라운드 회귀(심사중 강등관문 우회·보험사 입찰목록 필터누락·추가분 최저가 필터누락)"),
    ("test_scan_round102_fixes.py", "스캔 102라운드 회귀(협력사 증거사진 무시된 완료보고·정산 관문, 정산CSV 필터누락)"),
    ("test_scan_round103_fixes.py", "스캔 103라운드 회귀(재개상한 오염·발송대기 되돌리기 미완성·하자PATCH 검증누락)"),
    ("test_scan_round104_fixes.py", "스캔 104라운드 회귀(정산 내보내기 드릴다운 누락·협력사 대시보드 동명업체 누출)"),
    ("test_scan_round105_fixes.py", "스캔 105라운드 회귀(보험사 동명기관 정산누출·완료승인 권한우회, 담당배정 감사이력 소실)"),
    ("test_scan_round106_fixes.py", "스캔 106라운드 회귀(이체관문 하자사유 형식불일치·하도급 자격판정 컬럼오류·하자집계 데모오염)"),
    ("test_scan_round107_fixes.py", "스캔 107라운드 회귀(낙찰취소 재입찰 사진노출 뒷문·도급판정 기록실패 침묵)"),
    ("test_scan_round108_fixes.py", "스캔 108라운드 회귀(정적 처리방침 허위고지·협력사 화면 표류 면허컬럼 3곳)"),
    ("test_scan_round109_fixes.py", "스캔 109라운드 회귀(하자 심각도 검증누락·개인정보파기 증적축소·보증만료 알림유실)"),
    ("test_scan_round110_fixes.py", "스캔 110라운드 회귀(휴지통 mtime 유예무력화·2차경매 배치분류 재도달)"),
    ("test_scan_round111_fixes.py", "스캔 111라운드 회귀(유찰확정 입찰방치·무입찰경보 회차유실·탈락자 미통지)"),
    ("test_scan_round112_fixes.py", "스캔 112라운드 회귀(전체재경매 무효입찰·notify case_id 누락·연락처 유실)"),
    ("test_scan_round113_fixes.py", "스캔 113라운드 회귀(변경견적 발주처확인 생애주기 3건)"),
    ("test_scan_round114_fixes.py", "스캔 114라운드 회귀(입찰목록 필터누락·사진집계 오염·추가분 유찰 무방비)"),
    ("test_scan_round115_fixes.py", "스캔 115라운드 회귀(검수승인 변경견적무시·취소정산독촉·발주처확인 등급게이트)"),
    ("test_scan_round116_fixes.py", "스캔 116라운드 회귀(협력사포털 등급게이트4곳·시공증거 낙찰업체본인·auctions is_demo)"),
    ("test_scan_round117_fixes.py", "스캔 117라운드 회귀(옛출동업체 사진남용·1차합의 부동의무시·접수번호 LIKE유출)"),
    ("test_scan_round118_fixes.py", "스캔 118라운드 회귀(하자 title·content·resolution, 리드·신청 메모 길이상한 누락)"),
    ("test_scan_round120_fixes.py", "스캔 120라운드 회귀(지오코더 오른쪽경계·지도 저장좌표 무시·복호화 침묵)"),
    ("test_scan_round121_fixes.py", "스캔 121라운드 회귀(회사정보 침묵/비원자적저장·수수료율inf크래시·백업오탐)"),
    ("test_scan_round122_fixes.py", "스캔 122라운드 회귀(schedule_events 데모누락·dispatch로거 미도달·분할회피 category일치)"),
    ("test_scan_round123_fixes.py", "스캔 123라운드 회귀(백업디렉터리 격리누수·자가점검 오염취약·CSP항진명제·보험사로그인누락)"),
    ("test_scan_round124_fixes.py", "스캔 124라운드 회귀(check_orphan_chars docs스킵·ㆍ오탐 / check_tx_paths 범위·오탐)"),
    ("test_scan_round125_fixes.py", "스캔 125라운드 회귀(windows_setup.ps1 종료코드 미검사 7곳·스모크 자격증명 미배선)"),
    ("test_scan_round126_fixes.py", "스캔 126라운드 회귀(예약스윕 중복경고 비차단·등록사각지대 / 외부공개 Remove 미종료)"),
    ("test_scan_round127_fixes.py", "스캔 127라운드 회귀(외부접속_상시가동.ps1: 서버크래시 무기록·재기동실패무시·터널타임아웃방치)"),
    ("test_scan_round128_fixes.py", "스캔 128라운드 회귀(healthz 타임아웃 여유부족·재기동 디바운스없음, 감시자6일째 구버전 발견)"),
    ("test_scan_round129_fixes.py", "스캔 129라운드 회귀(partner_portal sw캐시 계정간 유출 — 로그아웃 안 거친 계정전환)"),
    ("test_scan_round130_fixes.py", "스캔 130라운드 회귀(출동수배 공종·지역 LIKE 와일드카드 무력화 3곳)"),
    ("test_scan_round131_fixes.py", "스캔 131라운드 회귀(win_rate 분모 단위불일치·is_demo 미필터, 실측#94)"),
    ("test_scan_round132_fixes.py", "스캔 132라운드 회귀(win_rate 1차합의 낙찰이 분자에 섞여 300%까지 나오던 결함)"),
    ("test_scan_round133_fixes.py", "스캔 133라운드 회귀(낙찰확정 2곳 award_route·awarded_at 누락 — 승률오염·거짓지연알림)"),
    ("test_scan_round134_fixes.py", "스캔 134라운드 회귀(낙찰취소 co_extra 누수·미수선되돌리기 dispatch_status 누수)"),
    ("test_scan_round135_fixes.py", "스캔 135라운드 회귀(입점신청 승인이 마케팅 수신동의 미반영 — 캠페인 대상 영구누락)"),
    ("test_scan_round136_fixes.py", "스캔 136라운드 회귀(보험사 중지가 정산·1차합의 승인을 영구정지시키던 결함)"),
    ("test_scan_round137_fixes.py", "스캔 137라운드 회귀(심사중 세션생존·낙찰승인독촉 중지보험사 미감지·출동수락 상태미재확인)"),
    ("test_scan_round138_fixes.py", "스캔 138라운드 회귀(2차경매개시·1차합의승인이 dispatch_status 미리셋)"),
    ("test_scan_round139_fixes.py", "스캔 139라운드 회귀(무입찰유찰 low_price 미리셋·낙찰재배정 실적재계산 누락 2곳)"),
    ("test_scan_round140_fixes.py", "스캔 140라운드 회귀(평점감점표 '경미' 누락·1차합의 승인자 하위계정 미구분)"),
    ("test_scan_round141_fixes.py", "스캔 141라운드 회귀(승인자 하위계정 미구분 형제 자리 8곳 — 파손정도·가견적확인·하자접수·사진업로드 3종·사건등록·추가공사확인)"),
    ("test_scan_round142_fixes.py", "스캔 142라운드 회귀(엑셀 내보내기 필터 무시 3섹션·개인정보 파기 종료버킷 후속처리 누락)"),
    ("test_scan_round144_fixes.py", "스캔 144라운드 회귀(웹훅 재전송 소진 시 사람에게 알리지 않던 결함 — 상태·감사로그·알림 신설)"),
    ("test_scan_round145_fixes.py", "스캔 145라운드 회귀(알림톡·문자 발송 영구실패 시 사람에게 알리지 않던 결함 — 형제 웹훅과 같은 계열)"),
    ("test_scan_round146_fixes.py", "스캔 146라운드 회귀(처리방침 제3조 '하자보수 관련 기록' 보유기간 미이행 — defects 개인정보 스크럽 신설)"),
    ("test_scan_round147_fixes.py", "스캔 147라운드 회귀(처리방침 '접속 기록(로그) 2년' 중 login_attempts 파기 누락)"),
    ("test_scan_round149_fixes.py", "스캔 149라운드 회귀(웹훅 서명 비밀키 노출 경로 부재 — admin.js·연동안내서)"),
    ("test_scan_round151_fixes.py", "스캔 151라운드 회귀(온보딩 화면 '첫 입찰' 날짜가 재투찰로 틀어지던 결함)"),
    ("test_scan_round152_fixes.py", "스캔 152라운드 회귀(최초 출동업체 식별자가 재수배로 덮어써지던 결함)"),
    ("test_scan_round153_fixes.py", "스캔 153라운드 회귀(사건 주소 수정 시 지도 좌표가 안 갱신되던 결함)"),
    ("test_scan_round154_fixes.py", "스캔 154라운드 회귀(협력사 주소 수정 시 좌표가 안 갱신되던 결함 — 관리자콘솔·마이페이지 2곳)"),
    ("test_scan_round155_fixes.py", "스캔 155라운드 회귀(입점신청 접수·승인 파이프라인에 좌표가 통째로 빠져 있던 결함 — 공개폼·직접접수·승인 3곳 + 프런트 배선 2곳)"),
    ("test_scan_round157_fixes.py", "스캔 157라운드 회귀(웹훅 SSRF 방어 — 검사와 접속이 호스트명을 각자 다시 resolve 해 DNS 리바인딩에 뚫리던 결함)"),
    ("test_scan_round158_fixes.py", "스캔 158라운드 회귀(고아 행 점검·정리 목록에 notifications·schedule_events·contract_gate_log·bids 4개 표가 빠져 있던 결함)"),
    ("test_scan_round159_fixes.py", "스캔 159라운드 회귀(geocode_fill._region_ok 가 구 없는 시/군에서 동네일치 판정을 사실상 무력화하던 결함)"),
    ("test_scan_round160_fixes.py", "스캔 160라운드 회귀(geocode_fill.fill() 이 좌표없는 후보가 섞이면 정제주소 재시도를 포기하던 결함)"),
    ("test_scan_round161_fixes.py", "스캔 161라운드 회귀(api_notices·api_address_search·billing_guide·insurer_api_guide 4곳의 계정 생사 확인 누락)"),
    ("test_scan_round162_fixes.py", "스캔 162라운드 회귀(발주처 사건취소가 '도착' 상태 출동수배를 안 닫아 취소된 사건에 사진업로드가 계속 열려있던 결함)"),
    ("test_scan_round164_fixes.py", "스캔 164라운드 회귀(마케팅 캠페인의 '수신동의 없음' 제외 건수가 저장되지 않고 사라지던 결함)"),
    ("test_scan_round165_fixes.py", "스캔 165라운드 회귀(캠페인 지역필터가 SQL LIKE 라서 '충청남도'를 '충남'으로 못 잡던 결함)"),
    ("test_scan_round166_fixes.py", "스캔 166라운드 회귀(manage.py reset-pw 가 협력사/보험사 아이디를 정규화 없이 비교해 대소문자·공백이 다르면 못 찾던 결함)"),
    ("test_scan_round167_fixes.py", "스캔 167라운드 회귀(관리자 로그인이 아이디 대소문자를 정규화 안 해 정상 비밀번호도 실패하던 결함 — 자가잠금 위험)"),
    ("test_scan_round168_fixes.py", "스캔 168라운드 회귀(admin.js·양대포털의 esc() 가 작은따옴표를 이스케이프 안 해 form.js 의 강화판을 조용히 가리던 결함)"),
    ("test_scan_round169_fixes.py", "스캔 169라운드 회귀(관리자 직접등록·정보수정 4곳이 자유텍스트 필드 길이제한을 전혀 안 걸던 결함)"),
    ("test_scan_round170_fixes.py", "스캔 170라운드 회귀(관리자 감사로그 행위자 actor() 가 표시이름만 남겨 위조 가능하던 결함)"),
    ("test_scan_round171_fixes.py", "스캔 171라운드 회귀(협력사 사건액션·변경견적 8곳의 데모 사건 격리 누락 — 실측: 운영DB 5건 이미 실계정에 배정)"),
    ("test_scan_round172_fixes.py", "스캔 172라운드 회귀(출동 단계 4곳·알림 브로드캐스트 2곳의 데모 격리 누락 — 실측: 운영DB 협력사 2곳 이미 데모 수배에 도착 상태로 배정)"),
    ("test_scan_round173_fixes.py", "스캔 173라운드 회귀(전체재경매 유찰 처리가 탈락업체 통지·입찰무효화를 안 해 다음 회차에 반려입찰이 살아남던 결함 — 형제 두 경로엔 이미 있던 방어)"),
    ("test_scan_round174_fixes.py", "스캔 174라운드 회귀(업체정보수정이 partner_type 을 검증 없이 그대로 기록해 통값·재경매 입찰 자격판정이 오타값에 조용히 걸리던 결함)"),
    ("test_scan_round175_fixes.py", "스캔 175라운드 회귀(로그인 잠금 수동해제가 아이디를 소문자로 안 맞춰 대소문자 다르면 0건 지우고도 거짓 확인을 주던 결함 — 실측: 운영DB 144+22건 노출)"),
    ("test_scan_round176_fixes.py", "스캔 176라운드 회귀(manage.py create-admin 이 아이디를 정규화·검증 안 해 대문자 섞으면 생성된 계정이 영구히 로그인 불가되던 결함 — 실제 로그인 라우트로 401 재현 확인)"),
    ("test_scan_round177_fixes.py", "스캔 177라운드 회귀(partner_type/status 화이트리스트가 공개입점신청·관리자직접등록엔 없어 임의값이 그대로 저장되던 결함 — 101·174라운드가 수정 라우트만 막고 놓친 형제 3곳)"),
    ("test_scan_round178_fixes.py", "스캔 178라운드 회귀(철지난 출동수배 문자 일괄취소가 only_ids·is_demo·channel 을 하나도 안 지켜 선택발송이 무관한 건·데모까지 휩쓸던 결함)"),
    ("test_scan_round179_fixes.py", "스캔 179라운드 회귀(manage.py prune-personal --dry-run 이 알림본문·조회링크 파기 건수를 항상 0건으로 과소보고하던 결함 — 격리사본 실측 미리보기2건 vs 실제7건)"),
    ("test_scan_round180_fixes.py", "스캔 180라운드 회귀(표준단가 대량적재 CLI가 개정이력을 전혀 안 남기던 결함 — 실측: 운영DB 42개 항목 단가 덮어썼는데 이력 0행. app.py·db.py 공유함수로 통일)"),
    ("test_scan_round181_fixes.py", "스캔 181라운드 회귀(입찰이력 low_flag가 실제 저가경보 발생여부와 따로 놀던 결함 — 재경매 투찰은 계산값을 버렸고, 원경매는 협력사비공개 경보를 놓쳤다)"),
    ("test_scan_round182_fixes.py", "스캔 182라운드 회귀(sweep_dispatches 자동재수배 실패처리기가 Row.get() 오용으로 예외처리기 자신이 죽어 남은 대상 전부의 점검을 통째로 멈추던 결함)"),
    ("test_scan_round183_fixes.py", "스캔 183라운드 회귀(manage.py check 의 데모잔존 판정이 죽은 바깥 except 때문에 마이그레이션 전 DB에서 거짓 초록을 내던 결함 — go-live 게이트가 정반대로 통과시킴)"),
    ("test_scan_round184_fixes.py", "스캔 184라운드 회귀(manage.py check 의 ghost 판정이 여전히 실패를 0건으로 감추고, demo_total 무조건 -1 덮기가 부분실패 시 확인된 양수합계까지 지우던 결함 — 실측: 운영DB ghost 77건·정산1.3억)"),
    ("test_scan_round185_fixes.py", "스캔 185라운드 회귀(2차 경매 개시가 work_lots 생성 시 공종명을 '·'로 직접 쪼개 도급 적법성 관문을 오작동시키던 결함 — case_trades() 자신이 두 번 금지한 방식. 사건 #614가 재현 일보직전)"),
    ("test_scan_round186_fixes.py", "스캔 186라운드 회귀(입찰채점 지역점수가 norm_regions() 를 안 거치고 앞토큰 문자열포함으로 직접 판정 — 실측: 긴표기 협력사 39곳 부당감점 + 대구 11곳이 해운대구와 완전일치 오판)"),
    ("test_scan_round187_fixes.py", "스캔 187라운드 회귀(go-live 미리보기가 photos·settlements·defects 세 표만 세고 dispatches·schedule_events·contract_gate_log·bids 등은 실행이 실제로 지우는데도 화면에 안 보였고, 해피콜 전량삭제·평판초기화·로그인시도 전량초기화는 승인 후에야 알렸던 결함 — 되돌릴 수 없는 삭제 전 고지가 실제 범위보다 작았다)"),
    ("test_scan_round188_fixes.py", "스캔 188라운드 회귀(cmd_sweep 이 형제 스윕 7개는 전부 콘솔보고하면서 무입찰경보만 반환값을 버려 실제발송은 되는데 운영자는 알 길이 없던 결함 · cmd_prune_personal 이 형제(prune-orphans·go-live)와 달리 except sqlite3.Error 가 없어 도중 쿼리 실패 시 처리 안 된 traceback 으로 죽던 결함)"),
    ("test_scan_round189_fixes.py", "스캔 189라운드 회귀(assign_dispatch 가 open_dispatch 의 152라운드 CS_PHOTO 가드를 못 물려받아 이미 도착·사진확보된 사건에 제3업체를 직접배정할 수 있었던 결함 — arrive() 가 first_partner_id 를 조건없이 덮어쓰고 open_agreement 가 최근 도착을 자동선택해 선착순 원칙이 뒤집힘 · 개인정보 동의고지에서 실제수집·방침필수 항목인 '기관 유형'이 빠져있던 결함)"),
    ("test_scan_round190_fixes.py", "스캔 190라운드 회귀(close_no_repair 가 검토중인 1차 합의를 안 닫아, 되돌리기(undo-no-repair)가 사건을 '접수'로 복귀시키면 낡은 합의가 보험사 승인 대기열에 부활하던 결함 — 승인 시 settle_agreement 의 재확인을 전부 통과해 낡은 견적 그대로 낙찰 확정. 형제 경로 api_case_open_auction 의 2차 경매 개시는 이미 같은 정리를 하고 있었음)"),
    ("test_scan_round191_fixes.py", "스캔 191라운드 회귀(협력업체 입점신청이 신청 접수 즉시 사업장 주소·정밀좌표까지 수집·저장하는데(155라운드 배관) 동의고지·공식 개인정보처리방침은 둘 다 '입점 승인 후 계정등록 시'에야 수집된다고 잘못 서술하던 결함)"),
    ("test_scan_round192_fixes.py", "스캔 192라운드 회귀(cancel-award 가 1차합의로 낙찰된 사건의 field_agreements '합의' 행을 안 닫아 재개설 경매가 계속 1차 규칙(접수당시 가견적=상한)으로 판정되던 결함 — 현장실측으로 이미 부족하다고 확정된 낮은 견적이 재입찰 상한으로 재부과됨 · 개인정보처리방침이 '면허번호'를 승인후 계정등록 필수항목으로 잘못 서술하던 결함)"),
    ("test_scan_round193_fixes.py", "스캔 193라운드 회귀(완료보고의 사진 누락경고가 이용약관 제6조가 요구하는 착공전·시공중·완료·영수증 4종 중 '완료' 하나만 확인하던 결함 — 나머지 3종 누락은 현장을 뜬 뒤에는 되돌릴 수 없는데도 어떤 신호도 안 줬다. 정산 관문은 AI 오분류로 인한 오차단 위험 때문에 의도적으로 안 건드림)"),
    ("test_scan_round194_fixes.py", "스캔 194라운드 회귀(정산 되돌리기가 형제(정산취소)와 달리 아무에게도 안 알려 지급검수 취소 후에도 협력사가 방금 받은 '입금됩니다' 알림만 보고 계속 기다리던 결함(정의만 되고 안 쓰이던 '정산정정' 알림종류를 채움) · 하자기록 파기기준일이 _WEND(말일보정 완료)에 SQLite '+3 years'를 그대로 얹어 윤년 2월29일 만료건에서 하루 늦게 파기되던 결함)"),
    ("test_scan_round196_fixes.py", "스캔 196라운드 회귀(도급 적법성 관문의 분할회피 합산판정(related_sum)이 region 원문 완전일치로 '같은 지역'을 판정해 '인천 남동'/'인천광역시 남동구'처럼 표기만 다른 같은 지역을 놓치던 결함 — 개별건이 안전선 아래면 조용히 통과되고 알림도 안 감. norm_regions 를 db.py 공유지점으로 옮김(순환임포트 회피) · 보험사 낙찰승인 사유가 길이제한 없이 감사로그에 저장되던 결함)"),
    ("test_scan_round197_fixes.py", "스캔 197라운드 회귀(협력사 직접등록이 활성 협력사를 만드는 다른 모든 경로와 달리 등급 무관(@require_admin)이라 하위관리자가 이름만 보내도 즉시 활성 협력사가 생겨 실사건 출동수배 대상이 되던 결함(기본상태를 심사중으로, 활성등록은 중간관리자 이상만) · 사진 반려/반려취소가 형제(사진승인, 이미 중간관리자로 격상됨)와 달리 등급 무관이라 하위관리자가 중간관리자의 검수 판단을 일방적으로 무효화할 수 있던 결함)"),
    ("test_scan_round198_fixes.py", "스캔 198라운드 회귀(보험사 포털 사건접수가 형제(API 연동)와 달리 서버측 멱등성 보호가 없던 결함 — 응답 지연 후 재제출·새로고침·새 탭에서 같은 사고가 사건·경매·정산까지 통째로 2벌 생겼다. 프론트 CASE_LOCK 은 같은 페이지 안 중복클릭만 막고 접수번호 완전일치 방어는 채번 때문에 무력화됨 — API 경로가 이미 쓰는 Idempotency-Key+UNIQUE 인덱스를 포털에도 연결)"),
    ("test_scan_round199_fixes.py", "스캔 199라운드 회귀(협력사 계정 일괄발급이 issue_partner_login() 의 UPDATE 이후(notify() 등)에서 예외가 나면 '발급 중 오류'로 보고하고도 conn.rollback() 을 안 불러 반복이 끝나면 무조건 commit() 되던 결함 — 실패로 안내된 업체도 실제로는 로그인ID·비밀번호가 커밋돼 아무도 모르는 임시 비밀번호로 로그인이 막혔다. 업체별 SAVEPOINT/ROLLBACK TO SAVEPOINT 로 그 몫만 되돌리게 수정)"),
    ("test_scan_round200_fixes.py", "스캔 200라운드 회귀(sweep_send_notifications 의 팝빌 실발송 직후 2단계 마무리기록 구간에 예외 방어가 없던 결함 — 형제(sweep_webhook_retries)는 이미 84·144라운드로 하드닝됐는데 여기만 못 받았다. DB 오류가 나면 send_attempts는 이미 커밋됐는데 status만 안 바뀌어 성공건 중복재발송·3회소진건 영구좀비화 위험이 있었고, 무엇보다 예외가 함수 전체를 뚫고 나가 같은 배치의 나머지 대기열까지 멈췄다)"),
    ("test_scan_round201_fixes.py", "스캔 201라운드 회귀(repair_estimate.py window_pair 레시피의 입력범위(A:1.0~6.0)가 sash_ins 단가의 국토부 표준시장단가 검증범위(창호면적 3.0~6.0㎡)보다 넓어 흔한 소형창(1.2㎡ 욕실창 등)도 검증 안 된 단가로 '원격확정가능'이 되던 결함 — 그 값이 그대로 2차 입찰 하한선이 된다. 입력 자체를 막지 않고(두 소비처가 EstimateError 를 근거없이 진행/400 으로 처리해 더 나빠짐) _gate() 에 recipe별 needs_calibration_if 훅을 추가해 검증범위 밖일 때만 실측필요로 내리게 수정)"),
    ("test_scan_round202_fixes.py", "스캔 202라운드 회귀(addrpick.js 의 PICKED 좌표캐시가 DOM 노드가 아니라 선택자 문자열로 유지돼, 사건 등록·입점신청 직접접수 폼을 다시 열 때(innerHTML 통째 재생성) 이전 레코드가 고른 좌표가 새 레코드로 조용히 넘어가던 결함 — 주소는 선택 입력이라 새 레코드를 주소 없이 제출하면 엉뚱한 사건의 GPS 좌표를 그대로 물려받고, 그 좌표가 출동 배차 거리계산에 쓰이는데 화면엔 주소 자체가 없어 아무도 못 알아챈다. attach() 가 새 DOM 노드에 붙는 순간 그 선택자의 캐시를 지우게 수정. Node.js 로 실제 실행해 검증)"),
    ("test_scan_round203_fixes.py", "스캔 203라운드 회귀(partner_portal.html 의 boot() 가 재진입 가드 없이 .tab 클릭 리스너 부착과 30초 알림폴링(setInterval)을 매번 새로 무장하던 결함 — 최초 페이지 로드 말고도 실사 증액요청·변경견적 응답 성공 후 boot() 를 다시 부르는데, 둘 다 정상 업무흐름이라 세션이 길수록 리스너·폴링이 계속 누적돼 탭 클릭 한 번에 여러 번 실행되고 선착순 출동콜 폴링도 여러 겹으로 돈다. _bootedOnce 가드로 리스너·인터벌 무장은 최초 1회만, 데이터 새로고침은 매번 그대로. Node.js 로 boot() 를 원본 그대로 뽑아 세 번 호출해 리스너·인터벌 수를 실제로 검증)"),
    ("test_scan_round204_fixes.py", "스캔 204라운드 회귀(현장 사진 업로드 안전망 두 구멍 — (a) upqueue.js UPQ.put() 의 IndexedDB add() 요청에 onerror 가 없어 한 장만 실패해도 트랜잭션 전체가 abort 되어 이미 성공한 나머지까지 롤백되던 결함, onerror(preventDefault)로 그 한 장만 실패처리하고 트랜잭션은 계속 진행하게 수정. (b) partner_portal.html 의 재큐잉 조건(retryFiles && !qids.length)이 '재시도 호출일 때만 큐에 없을 수 있다'고 잘못 가정해, 최초 호출에서 UPQ.put() 자체가 실패해도 재큐잉을 시도조차 안 해 실패 사진이 기기·서버 어디에도 없이 사라질 수 있던 결함, 조건을 !failIds.length 로 바꿔 재시도 여부와 무관하게 큐 미확보분은 항상 재큐잉. 둘 다 Node.js 로 실제 실행(가짜 IndexedDB·원본 조건블록 추출)해 검증, 두 결함을 독립적으로 되살려 각각 증명)"),
    ("test_scan_round205_fixes.py", "스캔 205라운드 회귀(admin.js 의 형제 액션 3곳(defectAct·dispatchSweep·leadAct)이 try/catch 없이 api() 를 호출해 unhandled rejection 으로 끝나던 결함 — 형제 appAct 는 '콘솔의 다른 변경 동작은 전부 try/catch로 감싸져 있다'고 주석에 적어 뒀지만 틀렸다. defectAct·dispatchSweep 의 화면(하자·A/S 관리, 현장 출동 수배)은 applyRoleMenus 등급게이트 밖이라 하위관리자도 열 수 있는데 서버 API 는 require_role(중간관리자) 라 403 이 100% 재현되고 조용히 사라졌다. 셋 다 appAct 와 동일한 try/catch+toast 패턴 적용. Node.js 로 각 함수를 원본 그대로 추출해 api() 실패/성공 양쪽 실행해 검증, 세 결함을 독립적으로 되살려 각각 증명)"),
    ("test_scan_round206_fixes.py", "스캔 206라운드 회귀(콘솔 알림벨의 배지·읽음처리가 형제 포털(보험사·협력사)과 달리 브로드캐스트(audience_type='all')를 포함시키던 결함 — 포털은 read_at 컬럼이 행 하나에 하나뿐이라 브로드캐스트를 배지·읽음처리에서 명시적으로 빼는데(한 사람이 전체를 읽음처리하는 사고 방지), 콘솔만 세 곳(피드·배지·읽음처리) 전부 같은 SQL을 재사용해 원칙을 어겼다 — 관리자의 '모두 읽음'이 브로드캐스트 행의 read_at 을 채워 아직 한 번도 안 연 보험사·협력사 화면에서도 조용히 '읽음'으로 보이게 만들 수 있었다. 지금은 audience_type='all' 실사용 호출이 없어 잠들어 있는 예방적 수정. ADMIN_OWN_SQL 신설해 배지·읽음처리만 admin 전용으로 좁힘, 실제 Flask 서버로 관리자 읽음처리 후 보험사 화면에서 오염 안 되는지까지 교차검증)"),
    ("test_scan_round207_fixes.py", "스캔 207라운드 회귀(보험사 포털 계정발급의 예약어 목록이 go-live 가 실제로 지우는 데모 계정명(manage.py DEMO_ACCOUNTS: insurer·insurer2)과 어긋나던 결함 — 형제(PARTNER_ID_RESERVED)의 p2·p3 패턴을 잘못 유추해 실존하지 않는 i2·i3 를 막고 정작 실제 2번째 보험사 계정명인 insurer2(smoke_test.py 도 동일 이름 사용)는 안 막았다. 그 상태로 실보험사에 login_id=insurer2 를 발급한 뒤 go-live --yes 를 돌리면 값 기준 삭제문이 데모 여부와 무관하게 그 실계정의 로그인 수단을 경고 없이 통째로 지운다. 예약어 목록을 insurer·insurer2·admin·staff·partner 로 정정, 실제 Flask 서버로 발급 거절 확인 + go-live 삭제문 재현으로 위험의 실체 확인)"),
    ("test_scan_round208_fixes.py", "스캔 208라운드 회귀(협력사·보험사 로그인의 실패·잠금이 형제(관리자 api_login)와 달리 감사로그(activity_log)에 전혀 안 남던 결함 — 유일한 흔적인 login_attempts 는 잠금판정용 내부 카운터일 뿐 보여주는 화면이 없고, 수동 잠금해제가 누르면 그마저 지워진다. 외부 조직 계정(협력사 399곳·보험사 전체)이 관리자보다 노출표면이 큰데 침입시도 흔적이 전혀 안 남았다. api_partner_login·api_insurer_login 의 잠금·실패 분기에 관리자와 같은 자리 DB.log() 추가. 실제 Flask 서버로 5회 연속 오답→잠금까지 재현해 activity_log 기록 확인, 두 함수를 독립적으로 되살려 각각 증명)"),
    ("test_scan_round209_fixes.py", "스캔 209라운드 회귀(go-live 가 데모 원계정(협력사·보험사)의 login_id·password_hash 만 지우고 그 밑 하위계정(portal_users)은 손도 안 대던 결함 — 하위계정은 원계정과 별개의 자기 login_id·password_hash 로 인증되고, 인증 시 원계정 크리덴셜이 NULL인지는 안 보고 원계정 status만 본다. go-live 가 원계정 status는 그대로 두므로, 데모 계정(login_id=partner 등, 고정비번 문서화)으로 미리 로그인해 하위계정을 만들어 두면 go-live 뒤에도 영구 로그인 가능한 백도어로 남는다. 원계정 login_id 를 지우기 전에 그 조직 하위계정을 먼저 지우도록 순서 고정, 미리보기에도 하위계정 삭제 예정 수 표시(187라운드 원칙 계승). subprocess 로 실제 --yes 실행까지 재현해 검증(210라운드가 is_demo=1 실조건으로 강화함))"),
    ("test_scan_round210_fixes.py", "스캔 210라운드 회귀(209라운드가 고친 go-live 하위계정 정리가 보험사 쪽에서만 실행순서 때문에 조용히 무력화되던 결함 — insurers 는 db.py DEMO_TABLES 에도 있어 ②단계 일괄삭제가 is_demo=1 인 그 행을 통째로 먼저 지우는데(실측: 운영DB 데모 보험사 6곳 전부 그렇다), 209라운드의 하위계정 삭제는 ③단계에서 login_id 로 그 행을 다시 찾으려 해 매번 0건이었다(협력사는 DEMO_TABLES 에 없어 문제없었음 — 그래서 209라운드 자신의 재현으로는 안 드러났다). 조직 id를 트랜잭션 맨 앞(②보다 먼저)에서 미리 확보해 ③이 그 id를 직접 쓰게 수정 — ②가 행을 지우든 말든 항상 올바른 조직을 겨눔. 부수적으로 209라운드 테스트의 보험사 시드에 is_demo=1을 추가해 실조건을 재현하게 강화)"),
    ("test_scan_round212_fixes.py", "스캔 212라운드 회귀(대시보드·지도 API 두 구멍 — (a) '이상 저가 입찰' 경보 쿼리가 이 함수의 다른 모든 집계와 달리 데모 사건을 안 걸러 실측(운영DB 사건#90, is_demo=1, 10%% 하락)이 조건을 만족했다 — 기본 경보기준(20%%) 밑이라 잠복 중이나 기준을 낮추거나 낙폭 큰 데모건이 하나만 더 생겨도 '부정 저가입찰 의심' 경보에 가짜 데이터가 섞인다, COALESCE(c.is_demo,0)=0 추가. (b) 지도 API 사건목록(LIMIT 500)이 형제(협력사 목록, LIMIT 3000)와 달리 잘렸는지 알 총계가 없었다 — 사건은 완료돼도 안 없어져 계속 누적되므로 이 상한에 먼저 닿을 잠재적 결함, case_total 추가(partner_total 과 대칭). Flask 실서버로 데모/실사건 구분 검증 + case_total 정확성 확인, 두 결함 독립 증명)"),
    ("test_scan_round213_fixes.py", "스캔 213라운드 회귀(\"한 함수/한 묶음 안 형제 쿼리 대조\"로 찾은 세 구멍 — (a) 보험사 포털 KPI(진행중 사건)가 status<>'완료'만 써서 취소·미수선종결 사건이 영원히 진행중으로 남음(CASE_OPEN_SQL 자신의 정의주석이 정확히 이 실수를 경고, 관리자콘솔은 이미 통일됐는데 보험사 포털만 옛 공식) → CASE_OPEN_SQL로 교체. (b) sweep_approval_overdue 의 '최장 N일'이 형제(_sweep_award_approval, 137라운드에 이미 고침)와 달리 중지보험사 건까지 포함해 발송 안 된 건의 일수가 '발송했습니다' 문장에 붙음 → 활성 보험사만 필터. (c) TODAY_WAITING '업체가 지급을 기다립니다' 항목만 형제(TODAY_QUEUE)와 달리 데모필터 없음 → 추가. 셋 다 현재 데이터로는 영향 0건이나 정상 운영에서 바로 재현되는 잠재결함. Flask 실서버+직접함수호출로 검증, 세 결함 독립 증명)"),
    ("test_scan_round217_fixes.py", "스캔 217라운드 회귀(ingest_partners.py 의 load_journal() 이 에이전트 CLI 저널의 최종 result 를 항상 dict 로 가정하던 결함 — 실제로는 사람이 읽는 텍스트가 보통이라 res.get() 이 AttributeError 로 적재 전체를 죽이거나(문자열인 경우), companies 키가 없는 dict 를 조용히 버렸다(주석만 있고 실제로는 no-op 이던 흡수 분기). 216라운드까지 한 번도 감사·테스트되지 않았던 파일. 문자열이면 그 안에 JSON 이 박혀있을 가능성까지 시도해 복구하고, 그래도 아니면 죽지 않고 경고만 남긴 뒤 건너뛰게 수정. 실제 실행으로 5가지 저널 모양(정상 dict·순수텍스트·JSON을 담은 문자열·companies 없는 dict·혼합 저널)을 검증)"),
    ("test_scan_round218_fixes.py", "스캔 218라운드 회귀(collect_emails.py 의 collect_one() 이 첫 페이지 진입 URL 의 robots.txt 만 검사하고, 첫 페이지에 이메일이 없어 더 보는 하위 경로 루프 안에서는 robots.txt 를 전혀 재검사하지 않던 결함 — 이 파일 독스트링이 정보통신망법 §50-2 준수사항으로 \"robots.txt 가 막은 경로도 가져오지 않는다\"를 명시하는데, 형제 검사인 refuses_collection() 은 이 루프 안에서도 매번 재검사되도록 짜여 있으면서 정확히 robots_allows() 만 빠뜨렸다 — \"/\"는 허용하면서 /contact 류만 막는 실무에 흔한 robots.txt 패턴에서 바로 이 구멍이 뚫린다. 부수적으로 SUB_PATHS 6개 중 이유 설명 없는 [:4] 슬라이스가 뒤 2개(/company·/inquiry)를 영구히 시도조차 못 하게 막던 것도 함께 수정. 217라운드까지 한 번도 감사·테스트되지 않았던 파일. 로컬 HTTP 서버로 실제 robots.txt 접두어매칭까지 재현해 검증, 두 결함 독립 증명)"),
    ("test_scan_round220_fixes.py", "스캔 220라운드 회귀(static/admin.css 가 static/style.css 의 우측 하단 알림 트레이(.tray) 정의를 값만 미묘히 다르게(16px vs 18px 등) 통째로 재정의해, admin.html 이 둘 다 로드할 때 나중에 로드되는 admin.css 가 같은 명시도에서 항상 이기던 결함 — style.css 가 PWA standalone 대응으로 나중에 추가한 안전영역 보정(bottom:calc(10px + env(safe-area-inset-bottom)))이 admin 콘솔에서만 조용히 완전히 가려졌다. .field 같은 의도적 오버라이드는 이유를 적은 주석이 있는데(기존 확립 원칙) .tray 사본에는 전혀 없어 실수로 복붙된 것으로 판단, admin.css 쪽 사본 제거(.bellpop·.bell 은 admin 전용이라 유지). 실제 브라우저에 admin.html 과 동일한 순서로 두 스타일시트를 로드해 getComputedStyle 로 되기 전/후 값을 직접 확인)"),
    ("test_scan_round221_fixes.py", "스캔 221라운드 회귀(두 결함 — (a) api_export_xlsx 가 모듈 공유 헬퍼 _xl_safe() 대신 독자적인 로컬 _safe(ILLEGAL_CHARACTERS_RE 기반)를 재구현하고 있었다 — _xl_safe 자신의 문서가 '내보내기 어디서든 같은 규칙을 쓴다'는데 이 함수만 어겼고, 유일한 행동 차이(\\r 처리: 로컬은 보존·_xl_safe 는 제거)를 실행으로 확인해 공유 헬퍼로 통합. 비인증 공개폼(입점신청·도입문의)의 자유텍스트가 그대로 지나가는 경로라 방어가 흩어져 있으면 안 된다(방어 이중구현 클래스는 이 코드베이스에서 이미 실제 사고를 낸 전례가 있음, 81라운드). (b) static/style.css 의 body font-family 가 OS별 폴백을 손으로 Windows 값만 적어 둬, fonts.css 가 이미 정의한 전체 대체 사슬(macOS·Android 포함, --font-sans)을 랜딩·에러·약관 3개 페이지만 받고 나머지 콘솔·포털 14개 템플릿은 못 받고 있었다 — var(--font-sans) 로 교체. Flask 실서버+openpyxl 실제 왕복으로 \\r 제거와 수식주입 방어 존속을 함께 확인, 두 결함 독립 증명)"),
    ("test_scan_round222_fixes.py", "스캔 222라운드 회귀(관리자 IP 화이트리스트(ADMIN_IP_ALLOW)가 billing_guide·insurer_api_guide·api_me 세 라우트를 우회하던 결함 — before_request 전역 게이트는 _is_admin_path() 로 관리자 경로를 판정하는데 이 함수는 /admin 접두사·/api/login·@require_admin 이 심는 _admin_only 플래그 셋 중 하나로만 알아본다. 관리자·발주처·협력사가 함께 쓰는 라우트는 데코레이터를 못 붙여 이 셋 어디에도 안 걸리고, 이 빈틈을 메우려 만든 _mixed_actor_guard()(JSON API 7곳이 씀)를 billing_guide·insurer_api_guide 는 '화면이라 JSON 오류를 못 보인다'며 안 쓰고 인증·생사확인만 손으로 재구현하면서 정확히 IP 검사 절만 빠뜨렸다(api_me 도 데코레이터가 없어 동일 사유). 공용 판정 함수 _admin_ip_denied() 로 뽑아내 세 곳 모두에 적용. Flask test_client 로 REMOTE_ADDR 을 허용·비허용 IP 양쪽으로 실제 요청해 이제 403으로 막히고 허용 IP·비관리자 세션은 그대로 통과함을 확인, 세 라우트 독립 증명)"),
    ("test_scan_round224_fixes.py", "스캔 224라운드 회귀(AI 자동승인 임계값(ai_auto_threshold) 변경 시 전용 엔드포인트(PATCH /api/ai/threshold, 실제 화면이 유일하게 쓰는 경로)가 새 값만 감사로그에 남기던 결함 — 형제(PATCH /api/settings, 같은 키를 다룸)는 '이 값이 시공사진 자동승인 문턱이라 나중에 그때 기준이 뭐였나에 답해야 한다'며 덮어쓰기 전 옛값을 읽어 이전값 → 새값으로 남기는데(boq_price_history 가 단가에 대해 이미 지키는 것과 같은 원칙), 정작 화면이 실제로 부르는 전용 라우트만 이 원칙을 어겼다. 덮어쓰기 전 옛값을 읽어 형제와 같은 로그 문구로 통일. Flask 실서버로 최초설정·연속변경 두 시나리오 모두 activity_log 실제 행을 대조해 검증)"),
    ("test_scan_round226_fixes.py", "스캔 226라운드 회귀(보험사 서버간 API(/api/v1/*, API 키 인증) 두 결함 — (a) _security_headers() 의 접속기록(개인정보 안전성 확보조치 기준 제8조 의무기록)이 세션 기반 인증만 읽어 API 키 채널 요청은 성공·실패 무관 전부 user_id·role 이 NULL 로 남았다. 같은 함수 안에 '보험사 계정이 빠져 있었다'며 세션기반 보험사 로그인에 이미 적용된 수정이 나중에 추가된 API 키 채널에는 안 갔던 것 — require_api_key() 가 채워 두는 g.api_insurer 를 같은 함수가 이미 읽는 g.csp_nonce 와 같은 방식으로 반영. (b) insurer_api_guide.html 의 사건접수 예시가 est_price 를 빠뜨려 문서 그대로 보내면 100% 확정적으로 400 이 나던 결함(parse_money 가 required=True 기본값) — 예시와 필드표에 est_price(필수) 보강. Flask 실서버로 문서의 JSON 예시를 실제로 추출해 그대로 전송해 성공 확인 + access_log 실제 행으로 두 결함 독립 증명)"),
    ("test_scan_round227_fixes.py", "스캔 227라운드 회귀(Idempotency-Key 재사용이 '내용이 다른 요청'이어도 조용히 첫 요청의 사건을 그대로 돌려주고 두 번째 요청은 흔적 없이 사라지던 결함, 형제 둘 다 — api_v1_case_create·api_insurer_case_create. idem_key(198라운드)는 '같은 요청 두 번'만 막도록 설계됐는데 실제로는 열쇠만 보고 내용은 전혀 안 봐, 완전히 다른 공종·지역·가견적을 보내도 그대로 통과했다(실측: 유리/서울/50만원 접수 후 같은 열쇠로 가드레일/부산/3천만원을 보내도 200 duplicate, 두 번째 내용은 DB 어디에도 안 남음). 핵심 내용(공종·주소·가견적)의 지문(idem_fingerprint)을 같이 저장해 같은 열쇠·다른 지문이면 409 IDEM_KEY_MISMATCH 로 거절, 지문이 없는(이 수정 전) 옛 행은 하위호환으로 그대로 duplicate 처리. Flask 실서버로 두 경로 모두 같은열쇠-다른내용/같은열쇠-같은내용/옛행하위호환 세 시나리오 실행 검증, 두 함수 독립 증명)"),
    ("test_scan_round228_fixes.py", "스캔 228라운드 회귀(재시도 안전성 두 결함 — (a) api_settlement_undo 가 '지금 상태만 보고' 되돌릴 다음 단계를 추론해, 같은 요청이 재시도되면 첫 호출이 이미 되돌린 다음 단계까지 캐스케이드로 또 되돌렸다(실측: 지급검수 되돌리기 재시도가 실제 입금된 돈을 '미확인' 상태로 되돌림, 형제인 paid/transfer/void 는 이미 상태조건+rowcount 가드로 안전한데 undo 만 빠져있었음) — 클라이언트가 클릭 1회당 만드는 undo_key(settlements.last_undo_key)를 저장해 같은 열쇠 재시도는 이미 한 일을 또 안 하게 막음(진짜 새 클릭은 다른 열쇠라 정상 진행). (b) api_defect_create 에 재시도 방어가 전혀 없어 같은 요청 두 번에 하자 2건+중복알림 — 형제(api_settlement_remind_approval)의 쿨다운 패턴을 10초로 좁혀 적용. Flask 실서버로 재시도-캐스케이드/새클릭-정상진행/하자중복방지/다른제목-정상접수 시나리오 실행 검증, 두 함수 독립 증명)"),
    ("test_scan_round229_fixes.py", "스캔 229라운드 회귀(photo_ai.save_upload() 가 EXIF(GPS) 제거에 실패하면 '사진을 잃는 것보다 낫다'며 원본을 그대로 저장하고 그 사실을 exif_error 로 돌려주는데, 이 값이 photos 테이블에 저장되지 않아 열람 게이트(_photo_visible_to)가 이 사실을 알 방법이 없던 결함 — 실측: 42,000,000픽셀급(고화소 폰 원본 흔한 범위) 사진이 8MB 상한 안에 들면서 재인코딩은 픽셀상한 초과로 건너뛰어 GPS 가 박힌 원본이 그대로 저장되고, '착공전' 등 시공사진은 낙찰 전 입찰 가능한 협력사 전원(경쟁사 포함)에게 열리는 기존 규칙과 맞물려 상세주소를 시군구까지만 자르는 이 코드베이스의 철칙을 사진 한 장으로 무효화했다. photos.exif_error 컬럼 추가해 3개 업로드 경로 전부 저장, '낙찰 전 입찰자 전원에게 연다' 분기에서만 이 값을 확인(낙찰된 시행사·발주 보험사·관리자는 증거보존 원칙대로 무관하게 열람 유지). Flask 실서버로 낙찰전차단/낙찰후정상/보험사·관리자정상/업로드경로 실제저장 시나리오 검증, 두 지점 독립 증명)"),
    ("test_scan_round230_fixes.py", "스캔 230라운드 회귀(build_pages.py 가 만드는 공개 GitHub Pages 정적 사이트(docs/)가 서버 전용 서비스워커 등록 스크립트를 그대로 실어 나르던 결함 — landing.html 의 이 스크립트는 /sw.js 를 서버가 굳이 루트에서 서빙할 때만(스코프 '/' 확보) 뜻이 있는데, 정적 빌드는 static/ 를 통째로 docs/static/ 로만 옮겨 루트엔 아무것도 없다. 실측: 실제 배포된 docs/index.html 이 여전히 '/sw.js' 를 등록 시도해 조용히 404(.catch 로 감춰짐)만 냈고, 설령 경로를 맞춰도 sw.js 자신의 __APP_VERSION__·__BUILD__ 자리표시자(서버가 실행 시점에 채움)와 캐시 목록의 static/actions.js·form.js(이 빌드가 의도적으로 제외하는 파일)까지 걸려 정적 사이트에서는 애초에 완전히 살릴 수 없는 기능이었다. 반쪽짜리를 흉내내는 대신 strip_jinja() 에서 이 스크립트를 통째로 제거(legal.html 처리 시 오탐 방지 가드 포함). 실제 landing.html·docs/index.html 양쪽에서 실행 검증, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round232_fixes.py", "스캔 232라운드 회귀(sweep_send_notifications 의 '번호없음 즉시실패' 분기가 동시실행 경쟁을 대비하지 않던 결함 — 바로 아래 CAS 분기(\"선점: 내가 읽은 시도 횟수 그대로일 때만 +1\")는 rowcount 를 확인해 경쟁자가 이미 처리한 건이면 조용히 건너뛰는데, 6줄 위 '번호없음' 분기는 UPDATE 의 rowcount 를 전혀 안 보고 무조건 _alert_send_failure() 를 불렀다. 이 함수는 크론(manage.py sweep, 5분마다)·관리자 수동버튼(/api/outbox/send-now·send-selected) 셋이 같은 발송대기 큐를 보므로 겹쳐 불릴 수 있다(함수 자신의 docstring이 '동시 실행(스케줄러+수동 버튼) 대비'를 CAS 도입 이유로 명시) — 번호 없는 같은 건을 두 실행이 동시에 집어 오면 먼저 커밋한 쪽만 상태를 바꾸는데 나중 실행도 rowcount=0 UPDATE 를 성공한 것처럼 넘겨 같은 건을 운영팀에게 '발송실패'로 두 번 알리고 DB.log 도 중복으로 남겼다. CAS 분기와 같은 rowcount 확인을 추가해 경쟁 패자는 out[\"skipped\"] 로만 집계. 같은 트랜잭션 안에서 경쟁자의 처리를 먼저 커밋으로 확정시키는 방식으로 실제 동시성 경쟁을 재현해 검증, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round235_fixes.py", "스캔 235라운드 회귀(geo.py 좌표 해석기 결함 2건, Agent 병렬조사로 발견 — (a) _AMBIG['고성경남'] 판정이 SIDO_ALIAS 를 거치지 않은 원문에 대고 '경남'을 찾는데, '경남'은 정식명 '경상남도'의 부분문자열이 아니다(SIDO_ALIAS 자체를 만든 이유와 같은 함정). 실측(data/partners_seed.json): region='경상남도' 협력사가 실존해 이 판정이 항상 실패, 고성경남(군) 좌표를 못 쓰고 경남 광역중심(시청)으로 약 55km 벗어났다 — 정식명을 추가. (b) case_coords() 가 좌표만 있으면 무조건 '수동'이라 적어 실제 geo_src 컬럼(주소검색 등)을 무시했다 — 형제(partner_coords, 216라운드)는 이미 올바르게 읽는데, 216라운드 자신의 주석이 '형제는 이미 고쳐졌다'고 착각해 정작 case_coords 는 안 고쳐진 채 남아 있었다. 사건 상세지도·관제지도·인근업체 API·협력사 진행목록이 전부 이 결함의 영향을 받는다 — partner_coords 와 같은 패턴으로 통일. 두 결함 독립 검증(회귀시나리오 포함), 되돌려 실패 재현 후 복원)"),
    ("test_scan_round238_fixes.py", "스캔 238라운드 회귀(deploy/개인정보_내부관리계획.md 제4조가 실제 관리자 등급과 어긋나던 결함, Agent 병렬조사로 발견 — 문서는 '최고관리자·운영관리자' 2단계만 적었는데 실제 코드(app.py ADMIN_ROLES)는 '최고관리자·중간관리자·하위관리자' 3단계다. '운영관리자'는 3등급 체계로 통일하기 전의 옛 등급명(db.py 마이그레이션이 부팅마다 '중간관리자'로 자동 치환하는 이름)이라 어떤 계정에도 존재하지 않는다 — 개인정보 고시가 요구하는 '취급자의 범위와 역할·책임'을 문서로 감사하려는 사람이 존재하지 않는 등급을 찾고 실제 3번째 등급(하위관리자, 수십 개 라우트를 실제로 게이팅함)은 놓치게 된다. 실제 등급 3개로 표를 정정하고, app.py 의 ADMIN_ROLES 와 항상 일치하도록 묶는 회귀테스트 추가(등급 체계가 또 바뀌면 이 테스트가 먼저 잡는다). 되돌려 실패 재현 후 복원)"),
    ("test_scan_round239_fixes.py", "스캔 239라운드 회귀(static/sw.js 서비스워커의 두 캐시쓰기 블록(협력사 대시보드·출동목록의 '마지막 사본', 정적자산 캐시우선)이 waitUntil() 로 묶여 있지 않던 결함 — respondWith() 의 생명연장은 res 를 반환하는 순간까지만인데, 캐시쓰기(caches.open().then(c=>c.put()))를 그 반환값과 안 묶고 fire-and-forget 으로 띄워 뒀다. 응답이 화면에 전달된 직후 브라우저가(특히 신호 나쁜 현장에서 배터리 절약을 위해 유휴 서비스워커를 적극 종료하는 모바일 환경) 워커를 바로 죽이면 아직 안 끝난 캐시쓰기가 통째로 사라질 수 있다 — 이 코드베이스가 반복 강조하는 '지하주차장·산간 신호끊김' 시나리오에서 정작 가장 먼저 깨지는 구조였다. e.waitUntil() 로 캐시쓰기 프라미스를 명시적으로 붙잡게 수정. 부수적으로 X-Cached-At 를 붙인다던 주석도 실제 코드(X-From-Cache, 값 없는 불리언 플래그)와 안 맞아 정정. Node 로 fetch 핸들러를 실제 실행해 waitUntil 호출 여부 검증, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round240_fixes.py", "스캔 240라운드 회귀(api_partner_update 의 등급검사·강등확인 관문 둘 다 '본문에 status 키가 있는가'만으로 걸려 있던 결함, Agent 병렬조사로 admin.js 협력사 관리 화면 감사 중 발견 — 화면(admin.js savePartner())은 관리자가 상태를 안 건드려도 <select> 의 현재 선택값을 매번 함께 보내는데, 서버는 '본문에 있다'와 '바뀐다'를 구분하지 않았다. 그 결과 하위관리자가 상태는 그대로 두고 연락처 하나만 고쳐도 매번 '업체 상태 변경은 중간관리자 이상만…'으로 거부됐다(라우트 자신의 주석 '연락처 수정까지 막을 이유는 없다'와 정반대로 동작, 실측: 저장 100% 거부) — 그리고 이미 퇴출 등으로 내려가 있는 업체를 상태값 그대로 재전송하며 다른 필드만 고쳐도 강등확인 관문(진행 중 사건 有)에 불필요하게 걸렸다. 함수 안에 이미 DB 현재값과 대조해 계산하는 changed 가 있어(사유필수 검사에 씀) 그걸 두 관문 모두에 재사용하도록 수정. Flask 실서버로 5가지 시나리오(무변경저장 성공/실제변경 여전히차단/정상변경 영향없음/이미퇴출업체 무변경저장 성공/실제강등 여전히차단) 검증, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round241_fixes.py", "스캔 241라운드 회귀(협력사 계좌 '삭제' 기능이 안내문에만 있고 실제 화면엔 없던 결함 — 240라운드 admin.js 협력사관리 감사의 세 번째 발견을 이번 라운드에 완성. app.py api_partner_account_set 은 clear_account:true 를 받으면 계좌를 실제로 지울 수 있게 이미 완성돼 있었는데, admin.js 어디에도 그 키를 보내는 통로가 없어 409 안내문(정말 지우려면 계좌 삭제를 사용하라는 문구)이 가리키는 기능 자체가 화면에 없었다. loadAccount()에 계좌 있을 때만 뜨는 삭제 체크박스 추가, saveAccount()가 체크 시 확인창을 거쳐 clear_account:true 전송하고 결과를 화면에 다시 반영하도록 수정, ACT.acctClearToggle로 체크 시 계좌번호 칸을 비우고 잠금. Flask 실서버로 새 화면이 실제로 보낼 요청을 재현해 계좌 암호문이 실제로 비워짐을 확인 + 대조군(clear_account 없이는 여전히 차단)으로 안전장치 존속 확인, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round242_fixes.py", "스캔 242라운드 회귀(admin.js settleAction() 의 이체완료 확인창이 지급액 정확히 0원일 때 공사대금 전액으로 잘못 표시되던 결함, admin.js 정산화면 Agent 병렬조사로 발견 — Number(s.payout || s.amount || 0) 는 payout 이 정확히 0(수수료 100% 계약, _parse_fee_pct 는 0~100 을 다 허용해 실제 도달 가능)일 때도 '없음'으로 오판해 공사대금 전액으로 대체했다. 74라운드가 fee_rate_bp 에서 이미 고친 것과 정확히 같은 '0 은 falsy' 함정을 같은 파일 다른 자리에서 또 밟았다 — 바로 한 단계 전 더블체크 모달(settleReview, won(s.payout) 직접사용)은 이미 0원이라고 정확히 보여준 뒤라 돈이 나가는 마지막 문에서 두 화면이 서로 다른 금액을 말했다(실제 이체요청엔 금액을 안 실어 보내 DB·통지는 영향 없음 — 순수 표시결함). ?? 로 교체. Node 로 settleAction() 을 실제 실행해 payout=0/정상값 두 시나리오 모두 확인, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round243_fixes.py", "스캔 243라운드 회귀(admin.js 하자상세 귀책(cost_bearer) 드롭다운에 '보험사' 옵션이 빠져 있던 결함, admin.js 하자화면 Agent 병렬조사로 발견 — 서버(api_defect_update)는 103라운드부터 보험사도 정당한 값으로 검증·저장한다(61라운드: 이의 검토 후 귀책을 보험사로 정하는 정상 경로, API·test_fairness.py 실사용 중이라고 코드 자신의 주석이 이미 자인). 그런데 화면 드롭다운엔 시행사/협의필요 둘뿐이었다 — 보험사로 이미 정해진 하자를 열면 일치하는 옵션이 없어 브라우저가 첫 옵션(시행사)으로 자동 표시하고, 89라운드가 만든 '안 바뀌면 안 보낸다' 가드가 이 값을 절대 시행사와 같다고 안 봐서 다음 상태전이 버튼(확인중·완료·반려 등 무엇이든)을 누를 때마다 매번 시행사로 조용히 되돌려 협력사 평점 차감까지 재발할 수 있었다. 옵션 추가로 해결. Node 로 셀렉트 렌더링을 실제 평가해 브라우저가 고를 값 확인 + 가드 로직 재현, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round244_fixes.py", "스캔 244라운드 회귀(api_partner_defect_resolve 가 재시도 방어 없이 목표상태(확인중) 자신도 허용 소스에 포함시켜 중복 알림·감사로그를 쌓던 결함, admin.js 하자화면 Agent 조사가 부수적으로 발견 — DEFECT_OPEN_STATES(접수·확인중·재시공배정)를 그대로 허용 소스로 쓰면 목표 상태인 확인중 자신도 포함되는데, DEFECT_NEXT 상 확인중에서 협력사가 다시 완료보고를 낼 정상 경로는 없다. 이 조건이 열려 있어 같은 요청을 재시도하면(방금 그 요청으로 이미 확인중이 된 건도) rowcount>0 으로 또 통과해 재시공보고 알림·감사로그가 매번 중복으로 쌓였다 — 형제(api_defect_create, 228라운드)가 이미 고친 것과 같은 재시도 결함 계열. 확인중을 뺀 진짜 시작상태(접수·재시공배정)만 허용, 이미 확인중이면 진짜 오류(완료·반려로 닫힘)와 구분해 조용히 성공(duplicate)으로 반환. Flask 실서버로 최초성공/재시도duplicate/알림로그 1건유지/대조군(닫힌하자는 여전히 409) 검증, 되돌려 실패 재현 후 복원 — 기존 형제테스트(53·112·118라운드) 전부 재확인해 회귀없음 확인)"),
    ("test_scan_round245_fixes.py", "스캔 245라운드 회귀(admin.js 출동 관제화면 결함 2건, admin.js 출동화면 Agent 병렬조사로 발견 — (a) 기한초과 집계가 검색필터 걸린 items 에서 다시 세져 있었다. 같은 화면의 다른 지표(모집중·수배됨·도착)와 사이드바 배지는 전부 서버가 낸 전체집계를 쓰는데 이것만 화면에서 더했다 — 검색상태는 초기화를 누르기 전까지 다음 새로고침에도 남으므로, 필터를 걸어둔 채 화면을 벗어나면 진짜 기한초과 건이 필터 밖에 있어도 기한 내 진행이라고 조용히 잘못 말할 수 있었다. 서버가 전체집계로 낸 overdue 값을 그대로 쓰도록 수정. (b) 직접배정 드롭다운에 전화번호와 이미 부름 여부가 없었다 — 같은 API 응답의 phone·called 를 형제(loadNearby)는 이미 보여주는데(중복 전화 방지 목적), 여기는 전화로 확인한 업체를 고르라고 안내하면서 정작 번호를 안 보여줬다. 옵션 텍스트에 번호와 이미 부름 표시 추가. Flask 실서버로 필터 밖 기한초과 건도 전체집계에 잡히는지 확인 + Node 로 드롭다운 렌더링 실제 평가, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round246_fixes.py", "스캔 246라운드 회귀(admin.js 설정화면 결함 2건, admin.js 설정·통계 화면 Agent 병렬조사로 발견 — (a) 리마인드 드롭다운이 키 없는(새 DB) 상태를 잘못 표시·저장했다. String(undefined) 가 어떤 옵션과도 안 맞아 브라우저가 첫 옵션(15분 간격)을 조용히 선택된 것처럼 보여주는데 실제 서버 기본값(_remind_minutes default=30)은 30분이다. saveSettings() 는 건드리지 않은 필드도 매번 다시 보내므로 다른 설정만 고쳐 저장해도 이 15분이 그대로 DB 에 박혀 리마인드 주기가 조용히 반토막났다 — 바로 옆 fee_vat_included 는 같은 문제를 이미 ?? 로 막고 있었다. 프론트(?? 기본값)와 백엔드(migrate() 백필) 양쪽에서 수정. (b) 설정 메뉴의 등급문턱(2)이 실제 두 하위기능(정책저장=최고관리자전용3, 감사로그=누구나1) 어느 쪽과도 안 맞았다 — 중간관리자는 폼을 다 채운 뒤에야 403을 만나고 하위관리자는 볼 자격 있는 감사로그까지 메뉴가 안 보여 못 봤다. 메뉴는 감사로그 기준으로 낮추고 정책패널만 형제(VIEWS.admins)처럼 스스로 가리게 수정. Node 로 드롭다운 렌더링 실제평가 + Flask 실서버로 새 DB 값 실존 확인, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round247_fixes.py", "스캔 247라운드 회귀(admin.js 가견적기준·표준단가 화면 결함 3건, Agent 병렬조사로 발견 — (a) boq·estbands 메뉴의 추가·수정·삭제 버튼이 등급 무관하게 항상 그려졌다. POST/DELETE est-bands는 최고관리자전용, boq 쓰기는 중간관리자전용인데 형제 admins·set(246라운드)은 이미 자기차단이 있었다 — myRank() 자기차단 추가. (b) api_est_band_set이 ON CONFLICT로 기존 기준을 조용히 덮어쓰면서 옛값을 감사로그에 안 남겼다 — 형제 api_boq_update와 224라운드가 같은 이유로 고친 ai_auto_threshold는 이미 옛값-새값을 남긴다. 덮어쓰기 전에 먼저 읽어 로그에 남기도록 수정. (c) api_boq_update가 자동견적 엔진에 연결된(sku_key 有) 행의 unit을 아무 값으로나 바꿀 수 있게 뒀다 — _load_price_book() 자신의 주석이 이미 이 함정을 경고하는데 실제로 값을 고치는 이 라우트엔 검사가 없었다. 저장은 200 성공하지만 그 순간부터 가견적 계산엔 영원히 반영 안 됨(에러도 로그도 없음) — 서버는 이제 SKU 단위와 대조해 거부하고, boqEdit() 화면도 미리 경고 문구를 보여준다. Flask 실서버로 옛값-새값 로그 실측 + SKU 단위보호 실측(대조군 포함) 검증, 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round248_fixes.py", "스캔 248라운드 회귀(admin.js 도입문의·입점신청 화면 결함 3건, Agent 병렬조사로 발견 — (a) 공개 입점신청 폼(apply_partner.html, 가장 흔한 유입 경로)에 상시 인력 수 입력칸이 아예 없었다. 서버(api_create_application·api_application_update)는 이미 1인 사업자는 접수·승인 둘 다 막는 정책을 갖고 있고 그 검사가 정확히 staff_count 값을 보는데, 이 폼엔 그 값을 보낼 칸 자체가 없어 항상 없음(None)으로만 들어가 두 관문 다 한 번도 걸린 적이 없었다(0과 없음을 구분하는 코드라 없음은 통과됨) — 관리자 직접접수 폼(appIntakeForm)이 이미 쓰는 같은 문구·같은 입력방식을 그대로 가져오되 이번엔 필수로 받는다. (b) 승인 관문(api_application_update)에 사업자번호 중복확인이 없었다 — 형제(api_application_create)는 이미 하는데, 실제로 업체가 만들어지는 유일한 지점(공개폼·직접접수 두 경로가 모두 거쳐감)엔 없어서 표기만 다른 상호나 10분 창을 벗어난 재신청이 같은 사업자번호로 활성 업체를 두 개 만들 수 있었다. 승인 직전 대조를 추가. (c) appDetail() 의 서류검토·승인·반려 버튼과 메모칸이 등급 무관하게 항상 그려졌다 — PATCH 는 메모 저장까지 포함해 전부 중간관리자 이상 전용인데 형제 화면들(246·247라운드)은 이미 자기차단이 있었다. myRank() 자기차단 추가. Flask 실서버로 새 폼이 실제로 보낼 요청 재현(1인사업자 거부·정상인원 통과)과 사업자번호 중복승인 거부(대조군 포함) 검증 + 소스 확인으로 appDetail 자기차단 확인, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round249_fixes.py", "스캔 249라운드 회귀(admin.js 사건관리 화면 결함 3건, Agent 병렬조사로 발견 — (a) caseDetail() 의 사건정보 수정 폼과 8개 액션버튼(입찰재개·오프라인전환종결·미수선종결되돌리기·유찰확정·출동수배전환·검수승인정산생성·낙찰취소재공고·경매열기)·입찰마감변경·피해사진올리기가 전부 등급 무관하게 그려졌다 — 이 값들은 모두 PATCH /api/cases/<id> 또는 전용 라우트로 가는데 그 라우트들은 전부 중간관리자 이상 전용이다. 형제(estbands·boq·appDetail, 246~248라운드)처럼 등급 미달이면 입력칸은 읽기전용, 버튼은 숨기게 수정 — 단 같은 모달의 공고다시알리기·완료보고독촉 두 개는 백엔드 자체가 등급 무관 허용이라 그대로 두었다(잘못 잠그면 그게 새 결함이 된다). (b) api_case_edit() 감사로그가 공종만 이전값→새값을 남기고 지역·주소·담당·피해자정보·긴급여부·보증기간은 필드명만 남겨 분쟁 시 무엇이 어떻게 바뀌었는지 로그로 복원할 수 없었다 — 넷은 공종과 같은 형식으로, 피해자 연락처는 계좌정보 변경 선례와 같은 이유로 원문 대신 마스킹만 남기게 통일(이 값은 저장완료 토스트에도 그대로 노출된다). (c) uploadDamagePhotos() 가 중복·형식오류로 일부만 저장돼도 그냥 성공 메시지만 띄워 몇 장이 왜 빠졌는지 알 길이 없었다 — 같은 파일의 형제(createCase 안 인라인 업로드)는 이미 그 사유를 보여주는데 통일이 안 돼 있었다. Node로 사건상세 하단 버튼 24개 시나리오를 실제 렌더링해 등급별 노출여부 확인 + Flask 실서버로 감사로그·응답의 이전값→새값·마스킹을 실측, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round250_fixes.py", "스캔 250라운드 회귀(admin.js 온보딩·면허조사 화면 결함 3건, Agent 병렬조사로 발견 — (a) onbIssue(선택 업체 계정 만들기) 버튼에 등급 게이트가 없었다. /api/partners/bulk-credentials 는 최고관리자 전용인데 화면은 등급 무관하게 그려 하위·중간관리자가 확인창까지 진행한 뒤에야 403을 만났다 — 형제(협력사 상세의 개별 계정발급)는 이미 등급 미달이면 안내문으로 바꾸는데 이 툴바 버튼만 놓쳤다(onbInvite·licSet 은 백엔드가 등급 무관 허용이라 그대로 두었다 — 잘못 잠그면 그게 새 결함이 된다). (b) api_partner_invite() 가 이미 안내 표시한 업체에도 매번 다시 실발송했다 — login_id 유무만 보고 invited_at 은 검사하지 않았다. 형제(api_partner_bulk_credentials, 이미 login_id 있으면 건너뜀)와 같은 관용구를 이 라우트만 놓쳐, 필터를 '전체'로 두고 보이는 것을 모두 선택하면 이미 로그인·입찰까지 마친 업체에도 안내 문자가 또 나갈 수 있었다 — 정상 UI 조작만으로 재현. (c) api_partner_license() 감사로그가 새 값만 남기고 이전 값은 버렸다 — 이 값은 하도급법 §25② 적법성 판정에 쓰이는데 등록확인→무등록으로 뒤집혀도 이전 기준을 로그로 복원할 수 없었다. 형제(AI 임계값, 라운드224)처럼 이전값→새값(+업체명)을 남기도록 통일. Flask 실서버로 신규+이미안내 혼합선택 시 정확히 갈리는지, 같은 요청 재시도 시 재차 걸러지는지, 면허조사 감사로그에 실제로 이전값이 남는지 실측, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round251_fixes.py", "스캔 251라운드 회귀(admin.js 발송함·캠페인 화면 결함 4건, Agent 병렬조사로 발견 — (a) 캠페인 생성·취소(+새 캠페인/취소 버튼)에 등급 게이트가 없었다. api_campaign_preview·api_campaign_create·api_campaign_cancel 전부 중간관리자 전용인데 화면은 등급 무관하게 그려 하위관리자가 폼을 다 채운 뒤에야 403을 만났다. (b) 발송함의 지금발송·목록발송·테스트발송 버튼도 같은 유형 — 팝빌 스위치만 보고 등급은 안 봤다. 특히 테스트발송은 임의 번호로 실제 문자가 나가는 동작이라 더 위험했다(형제 처리함·되돌리기는 백엔드가 등급무관이라 원래도 게이트가 없는 게 맞아 그대로 둠). (c) api_campaign_create()에 중복클릭 방어가 전혀 없었다 — 저장 버튼에 비활성화·디바운스가 없어(전역 디스패처에도 이런 방어 자체가 없음) 두 번 누르면 제목·채널·본문이 완전히 같은 캠페인이 수신자 스냅샷까지 통째로 중복 생성됐다. 지금은 실발송이 안 붙었지만 연동되는 순간 그대로 이중발송으로 이어질 구조였다 — 형제(협력사 안내표시, 250라운드)와 같은 관용구로 막는다. (d) api_campaign_preview()의 본문 미리보기가 실제 저장 시 항상 붙는 광고표기·발신자정보 꼬리를 빼먹어, 정보통신망법 표기의무를 확인하려는 미리보기가 정작 그 표기를 안 보여줬다 — 저장 시와 같은 규칙으로 통일. Flask 실서버로 하위관리자 403 최종방어·미리보기 실제 표기·더블클릭 재현 시 DB에 1건만 남는지(대조군 포함) 실측, 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round252_fixes.py", "스캔 252라운드 회귀(admin.js 변경주문(추가공사) 화면 결함 2건, Agent 조사로 발견 — (a·심각) 전체재경매 낙찰 확정에 필요한 insurer_instruction(발주처 미확인 금액을 유선지시 등 근거로 남기고 강행하는 통로)이 화면에 아예 없었다. 서버는 이미 이 필드를 받아 처리하는데, 전체재경매는 구조상 원업체가 거절한 옛 합산가를 상한으로 인하 입찰되므로 낙찰가가 그 옛 발주처 확인금액과 거의 항상 달라 이 관문에 실제로 자주 걸린다 — 입력할 곳이 없어 콘솔로는 영원히 낙찰을 확정할 수 없었다(원시 API 호출로 우회해야 했다). 형제(최저가 아닌 업체 선택 사유)와 같은 방식의 입력칸을 추가하고, 오류 코드도 형제(NOT_LOWEST)처럼 바로 그 칸을 가리키게 했다. (b) coActions()가 내는 변경주문 처리 버튼 7개 전부 등급 게이트가 없었다 — 대응 백엔드 라우트 7개가 전부 중간관리자 전용인데 하위관리자에게도 노출돼 눌러야만 403을 만났다(목록 조회 자체는 등급무관이 맞아 화면은 계속 보이되 처리 버튼만 가림). Node로 상태·등급 조합별 실제 렌더링 확인 + Flask 실서버로 근거 없이는 여전히 막히고(대조군) 새 칸을 채우면 실제로 낙찰이 확정돼 사건 낙찰업체·금액까지 갱신되는지 실측, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round253_fixes.py", "스캔 253라운드 회귀(admin.js 보험사(발주처) 관리 화면 결함 2건, Agent 조사로 발견 — (a) VIEWS.insurers에 자기차단이 없었다. applyRoleMenus()는 사이드바 메뉴 항목만 등급3 미만이면 숨기는데 loadView() 자체는 등급을 안 본다 — 실제로 메뉴가 아닌 경로가 있었다(등급 무관인 사건등록 화면이 발주처 0곳일 때 보여주는 안내 버튼이 정확히 이 화면을 연다). 서버(all=1 조회)도 등급무관이라 전 발주처의 담당자·부서·연락처·포털계정 보유여부까지 하위관리자에게 그대로 노출됐다. 형제(VIEWS.admins)처럼 화면 스스로 막고, 화면만 믿지 않고 서버도 함께 막았다(사건등록이 쓰는 기본 조회모드는 등급 무관 그대로 둠). (b) 발주처 상태(활성/중지) 변경이 콘솔에서 사실상 동작 불능이었다 — 상태 select만 있고 사유입력·강등확인 재요청 배선이 전혀 없어, 서버가 사유 요구나 대기업무 확인을 요구하면 토스트 에러만 뜨고 모달이 그대로 남았다. 형제(협력사 상태변경)가 이미 구현한 배선을 그대로 옮겼다. Flask 실서버로 하위관리자 all=1 차단(대조군: 기본조회는 정상)·대기업무 있는/없는 보험사 각각의 전체 상태변경 흐름을 끝까지 실측, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round254_fixes.py", "스캔 254라운드 회귀(대시보드·접속통계 화면 결함 2건, Agent 조사로 발견 — (a) sweep_auctions()가 데모 사건의 경매도 실제로 마감·낙찰승인요청·유찰 처리하고 감사로그까지 남겼다. 개발 DB 시드에 입찰중 데모 사건이 많아 관리자가 대시보드를 여는 것만으로도(요청마다 도는 자동스윕) 데모 건이 처리되며 대시보드 최근 활동 패널에 실활동과 구분 안 되는 로그가 쌓였다 — 이 함수가 건드리는 다른 모든 집계는 이미 데모를 빼는데 스윕 자신만 빠졌다. activity_log는 case_id·is_demo 컬럼이 없어 표시 단계에서 거를 수 없으므로, 표식을 만드는 대상조회 쿼리 쪽에서 막았다. (b) api_traffic()의 로그인 성공 집계가 관리자 로그인만 세고 협력사·보험사 로그인은 빠졌다 — 같은 응답의 이용주체별 집계는 이미 네 주체를 다 보여주는데 이 카드만 하나로 좁혀 같은 화면에서 서로 다른 모집단을 말했다. Flask 실서버로 데모/실제 사건을 나란히 만들어 스윕을 실제로 돌려 데모만 그대로 남고(대조군: 실제 사건은 정상 처리) 로그도 안 남는지, 3채널 로그인이 실제로 다 집계되는지(실패한 로그인 제외) 실측, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round257_fixes.py", "스캔 257라운드 회귀(dispatch.py 출동배차 모듈 결함 1건, 최초 정밀감사로 발견 — sweep_dispatches()가 데모 사건의 수배도 실제로 시간초과 처리하고 재수배까지 열어 그 지역·공종의 실제 활성 협력사에게 실제 문자/알림톡이 나갔다. claim·decline·arrive·close_no_repair는 전부 데모 수배를 거부하는데 자동순회의 유일한 진입점인 스윕 자신만 그 필터가 없어, 개발DB에 항상 존재하는 데모 수배가 시간초과로만 끝나며 매 회차 실제 발송을 유발했다 — 형제 스윕(sweep_auctions, 254라운드)과 같은 유형. 수정 자체에서 SQL 함정도 하나 자체발견했다: 괄호 없이 OR 뒤에 AND를 이어붙이면 AND가 OR보다 결합력이 세서 데모제외 조건이 OR의 오른쪽 가지에만 걸리고 왼쪽(제한시간 초과) 가지는 여전히 샌다 — 리뷰 중 스스로 잡아 전체 OR을 괄호로 감싸 수정. 직접호출로 OR의 두 가지(제한시간초과·무응답)를 각각 데모로 만들어 실측(대조군: 실제 수배는 정상 처리), 원래 결함과 자체발견한 결합력 함정 둘 다 각각 되살려 테스트가 정확히 그 지점에서 실패하는지 증명 후 복원)"),
    ("test_scan_round260_fixes.py", "스캔 260라운드 회귀(피해자 진행조회 공개페이지 /track/<token> 데모오염 결함 1건, track.html 감사 Agent 조사로 발견 — track_page()가 이 서비스의 유일한 진짜 공개 화면(로그인 전혀 없음)인데 조회 SQL이 is_demo를 안 걸렀다. 같은 파일의 다른 150여 곳(가장 가까운 형제는 이 기능의 짝인 _insurer_track_stat)은 전부 데모를 빼는데, 데모 사건에 토큰이 심겨 있으면 사건번호·지역·상태·담당자·업체명이 로그인 없이 인터넷에 그대로 노출됐다. 같은 조사에서 토큰 생성(128비트 CSPRNG, 2만개 샘플 충돌 0건 실측)·재발급시 구토큰 무효화·금액 미노출·타사건 혼입 없음·rate limiting(전역 IP당 분당240회로 충분)·조회수 갱신 원자성은 전부 이미 견고함을 확인. Flask 실서버로 데모 사건 토큰은 404, 실제 사건 토큰은 정상 200(대조군)임을 실측, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round261_fixes.py", "스캔 261라운드 회귀(crypto_util.py 키 형식오류 완전침묵 결함 1건, 암호화 유틸 감사 Agent 조사로 발견 — _load_key()는 BOKGUON_ENC_KEY가 아예 없을 때만 신호를 낸다(운영은 예외, 개발은 경고). 값은 있는데 base64 디코드 후 16/24/32바이트가 아닌 경우(키 로테이션 중 형식이 깨진 경우 등)는 완전히 침묵한 채 SHA256 파생키로 넘어갔다 — 형제(복호화 실패 로그, 라운드120)는 증상은 이미 남기는데 그 근본 원인(키 형식)에는 신호가 없어, 값을 나중에 제대로 고치면 그 순간부터 그 사이 저장된 값이 전부 안 열리는데도 저장 시점엔 아무 경고가 없었다. AES-256-GCM 구현 자체(nonce 매회 신규생성·인증태그 검증·에러처리)는 실측 검증 결과 이미 안전함을 재확인. 이 수정은 로그 한 줄만 추가한다 — 실제 파생키·암호화 포맷은 그대로라 기존 암호문 하위호환에 영향 없음(의도적으로 최소화, 알고리즘 변경은 재암호화 마이그레이션이 걸린 별개 판단이라 손대지 않음). 실행으로 형식오류 키는 경고 발생+키 원문 미노출+왕복 정상동작을, 정상 32바이트 키는 경고 없음(대조군)을 검증, 되돌려 실패 재현 후 복원 — blind_index 미사용 관찰 1건은 사업판단 필요 항목으로 메모리에 기록만 하고 코드는 건드리지 않음)"),
    ("test_scan_round262_fixes.py", "스캔 262라운드 회귀(notify_popbill.py 문자발송 어댑터 결함 2건, Agent 조사로 발견 — (a) 키 교체가 새 키로 바뀌었다고 거짓 보고했다. popbill SDK의 PopbillBase는 클래스당 인스턴스 하나만 두는 Singleton이라 생성자 인자를 무시하는데(실측: 재호출해도 최초 생성 시점 객체 그대로, 내부 키 안 바뀜), 이 어댑터의 캐시는 설정이 바뀌면 새로 만든다고 믿고 있었다. 키 유출로 급히 교체했는데 프로세스를 재시작하지 않으면 상태화면은 새 키가 설정됐다고 정확히 보여주면서도 실제 발송은 계속 옛(유출된) 키로 나갔다. SDK 내부를 억지로 덮어쓰는 대신 최초 연동 뒤 설정이 달라졌다는 사실 자체를 감지해 재시작 전까지 발송 자체를 거부하도록 수정. (b) 재시도 시 멱등키(RequestNum) 미사용 — 최대 3회 재시도하는 스윕에서 1차 시도가 실제로는 접수됐는데 응답 수신 중 끊기면 다음 스윕이 같은 알림을 requestNum 없이 또 보내 협력사가 같은 문자를 2~3회 받을 수 있었다. 재시도해도 안 바뀌는 알림 행의 고유id를 팝빌 RequestNum으로 실어 서버측 중복접수 거르기가 작동하게 함. 실행으로 키교체 감지·거부(대조군: 재시작 흉내 후엔 정상 인식)와 멱등키가 실제 SDK 호출 인자까지 전달됨을 검증, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round263_fixes.py", "스캔 263라운드 회귀(manage.py 운영CLI 안전장치 결함 2건, Agent 조사로 발견 — (a) 되돌리기 어려운 4개 명령(go-live·restore·prune-personal·prune-orphans) 전부 실행화면에 지금 어느 DB 파일에 적용되는지가 안 보였다. db.py의 유일한 운영DB 안전장치는 test_로 시작하는 진입점에만 발동해 manage.py를 구조적으로 검사 대상에서 제외하는데, BOKGUON_DB_PATH를 안 정하면 조용히 실제 운영 파일에 연결되면서도 확인 화면엔 표시가 없었다. 공용 show_db_target()을 만들어 네 명령 모두에 붙였다(참고: prune-personal만 형제와 반대로 플래그 없으면 즉시삭제가 기본인데, 주간 예약작업(윈도 작업스케줄러·리눅스 cron) 둘 다 플래그 없이 이 명령을 부르는 구조라 기본값 자체를 뒤집으면 매주 도는 개인정보보호법 이행 예약이 조용히 빈 작업이 된다 — 실행기준은 그대로 두고 화면·--help 문구만 명확히 함, 실행기준 변경은 예약작업 등록 갱신이 필요한 별도 판단이라 이번엔 미조치). (b) go-live의 데모 사건 자식행 정리 루프에서 dispatch_calls 삭제만 실패를 조용히 삼켰다 — 바로 아래 형제 루프(dispatches 등)는 실패를 모아 경고하는데 이 표만 빠져, 스키마가 바뀌어 삭제가 깨져도 화면은 삭제완료만 보여주고 고아 행이 남을 수 있었다. 실제 서브프로세스로 dispatch_calls 표를 강제로 없애 삭제가 실패하는 상황을 재현해 화면에 실제 DB경로와 실패 표 이름이 둘 다 찍히는지 실측, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round264_fixes.py", "스캔 264라운드 회귀(geo.py 좌표 해석기 결함 2건, 좌표계산 모듈 전체감사 Agent 조사로 발견 — (a) _AMBIG 판정(구 이름이 어느 광역시·도 소속인지)이 매치 지점 근처가 아니라 문자열 전체 어디든 근거가 있으면 통과시켰다. 실측(실 시드데이터 KAD한국자동문): region에 부산·대구와 함께 열거된 '광주'(지사)가 본사 설명의 무관한 '경기' 언급 때문에 경기도 광주시로 오판정돼 실주소(화성)에서 45.4km 벗어났다. 매치 바로 앞 10자만 보도록 좁혔다 — 이 폭은 실 시드데이터 397곳 전수와 대조해(4~30 사이 여러 값 실측) 회귀 0건이 되는 구간(6~12) 안에서 고른 값이며, 5 이하로 좁히면 부산·대구 광역시 등 정상 접미어를 가진 진짜 정답 28건이 함께 깨진다는 것도 실측으로 확인했다. (b) SIDO_ALIAS의 광주시→광역시 매핑이 영원히 도달 불가능한 죽은 코드였다 — '광주시'라는 문자열 자체가 (a)의 트리거 키워드이기도 해서 GU 판정 단계가 항상 먼저 가로채 경기도 광주시로 확정해 버렸다. (a)를 고치자 별도 코드변경 없이 자연스럽게 해결됨(실측 확인). 실제 geo.resolve()로 KAD 실사례·맨입 광주시·대조군(진짜 경기도 광주시·기존 정답들·235라운드 고성경남)까지 전부 검증, 되돌려 실패 재현 후 복원)"),
    ("test_scan_round265_fixes.py", "스캔 265라운드 회귀(주소좌표 백필 geocode_fill.py 결함 2건, 좌표계산 형제파일 감사 Agent 조사로 발견 — (a) rows_to_fill()이 --target cases(또는 both)에서 is_demo를 안 걸렀다. 같은 파일의 형제 report()는 이미 COALESCE(is_demo,0)=0을 거는데 조회 함수 자신만 빠져 있었다. cases 쪽은 ORDER BY id DESC(최신 우선)이기도 해서, 데모 직전에 만들어져 id가 큰 데모 사건이 --limit 예산을 실제 사건보다 먼저 먹어치울 수 있었다(limit=1이면 데모만 뽑혀 실제 사건은 그 배치에서 조회조차 안 됨). partners 테이블엔 is_demo 컬럼 자체가 없어(db.py 마이그레이션 목록에 부재) 필터는 cases 쪽 쿼리에만 추가했다. (b) fill()의 conn.commit()이 배치 전체가 끝난 뒤 단 한 번뿐이었다 — 최대 500건, 건당 최대 두 번의 외부 API 호출과 대기가 들어가는 배치 도중 중단(강제종료·네트워크 예외)되면 이미 찾은 좌표가 전부 커밋 안 된 채 날아갔다(데이터 훼손은 아니고 낭비 문제 — 재실행하면 같은 행을 다시 고른다). 같은 위험(반복문 안 외부 네트워크 호출)을 가진 형제 collect_emails.py는 이미 성공한 행마다 즉시 커밋한다 — 그 패턴을 그대로 따랐다. rows_to_fill() 직접호출로 limit=1 시나리오에서 데모가 예산을 먹지 않는지 실측, fill()을 실제로 돌리며 두 번째 조회에서 예외를 주입해 중단시킨 뒤 독립된 새 DB연결로 첫 행의 좌표가 이미 커밋돼 살아있는지 실측, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round266_fixes.py", "스캔 266라운드 회귀(주소검색 addr_search.py 결함 2건, geocode_fill.py 감사 라운드265가 남긴 미검증 관찰의 정밀조사 Agent가 발견 — (a) search()의 광범위 except가 아무 로그도 없이 빈 목록으로 삼켰다. HTTP 429·500·타임아웃·깨진JSON을 각각 주입해도 진짜로 검색결과가 없을 때와 완전히 똑같은 값([])·완전히 똑같은 침묵(로그 0바이트)이 나와, 호출부(geocode_fill.py 배치 집계·app.py 실시간 /api/address/search 라우트 둘 다)가 이 주소는 없다와 카카오 쪽이 막혔다를 원리적으로 구분할 수 없었다. 형제(crypto_util.decrypt, 라운드120)처럼 반환값은 그대로 두고 실패 사실만 로그에 남기도록 수정, 응답이 아예 dict 모양이 아닐 때(d.get이 AttributeError)도 이 자리에서 잡도록 except 튜플에 AttributeError를 추가했다. (b) 후보 목록을 만드는 for문 안에서 후보 1건이 파싱에 실패하면(좌표가 숫자가 아님 등) 그 예외가 함수 밖으로 새 나가 search()의 광범위 except에 잡히면서 같은 응답에 있던 멀쩡한 후보들까지 통째로 사라졌다 — _official() 1곳과 _open_map()의 address·place 두 루프, 총 3곳이 같은 구조였다. 각각 후보 단위로 try/except를 둘러 불량 후보 1건만 건너뛰게 했다. urllib.request.urlopen을 몽키패치해 429·비dict응답·후보1건불량 등을 실제로 주입해 반환값·로그 양쪽을 실측, 4개 지점(바깥쪽 except, _official, _open_map 두 루프) 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round267_fixes.py", "스캔 267라운드 회귀(collect_emails.py 최초 전면감사 결함 3건+geocode_fill.py 전파분 1건, 이 파일이 라운드265·266에서 모범 형제 패턴으로만 인용되고 정작 주조사대상이 된 적 없었다는 점을 지적한 정밀조사 Agent가 발견 — (a) refuses_collection()이 공백만 지우고 HTML 태그는 그대로 둬서, 정보통신망법 제50조의2 수집거부 문구 중간에 인라인 태그(스크롤 애니메이션·번역위젯이 흔히 쓰는 span, b, br 등) 하나만 끼어도 연속 문자열 매치가 깨져 수집거부 의사를 놓쳤다(미탐, 법적 안전장치 구멍). 태그부터 지운 뒤 매치하도록 수정. (b) main() 루프의 UPDATE·commit이 collect_one()의 try/except 밖에 있어서, 락 경합·디스크 오류 등으로 저장 하나가 실패하면 이미 찾아 둔 나머지 대상까지 배치 전체가 무방비로 죽었다 — 이 저장만 감싸 건너뛰고 계속하며 집계도 보정하도록 수정, geocode_fill.py의 좌표 저장(라운드265가 이 파일의 행단위 커밋 패턴을 그대로 베낀 자리)에도 똑같은 무방비 구조가 전파돼 있어 함께 고쳤다. (c) fetch()의 except Exception이 원인을 전혀 안 남겨(로깅 자체가 없었다) 타임아웃·DNS실패·403·429가 전부 접속 실패 한 줄로 뭉개졌다 — 형제(crypto_util.decrypt 라운드120·addr_search.search 라운드266)처럼 반환값은 그대로 두고 원인만 로그에 남기도록 수정. 태그로 끊긴 수집거부 문구 3종 실제 탐지, urlopen 몽키패치로 타임아웃·연결리셋·403 각각 주입해 로그 실측, DB연결을 가로채 저장 1건을 실패시켜 두 파일 모두 배치가 계속되는지(대조군: 실패한 행은 비어있고 다음 행은 정상 저장) 실측, 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round268_fixes.py", "스캔 268라운드 회귀(표준단가 대량적재 seed_boq.py/seed_boq_led.py + 공유함수 db.py boq_history() 결함 5건, 직전 세 라운드가 반복 발견한 배치루프 DB write가 항목별 예외처리 밖·침묵 except 두 패턴을 렌즈로 삼은 정밀조사 Agent가 발견, 두 스크립트 다 사상 첫 주조사대상 — (a) db.py boq_history()가 이력 INSERT 실패를 except sqlite3.Error: pass로 완전 침묵시켰다. 이 함수 자체가 라운드180에서 단가 바뀌었는데 이력 0행을 막으려 만든 통로인데 스키마 드리프트로 이 INSERT가 실패하면 호출부는 성공만 보고했다 — 형제(crypto_util.decrypt 라운드120)처럼 로깅 추가. (b) seed_boq_led.py의 2017년 값 정리 루프가 DB.boq_history() 호출에 예외처리가 없어, 이력 기록 하나가 실패하면 뒤이은 commit()과 이 스크립트의 진짜 목적인 24개 2026년 실측단가 적재까지 통째로 막혔다 — 행단위로 감싸 계속 진행하도록 수정. (c) seed_boq.py가 기존 항목 재적재 시 무조건 덮어써, 관리자가 콘솔에서 손으로 고친 값이 재적재 한 번에 조용히 하드코딩 값으로 되돌아가도 화면엔 표시가 없었다(이력엔 남지만 그 순간엔 안 보임) — 값이 실제로 바뀔 때만 눈에 띄는 경고를 찍도록 수정(동작은 그대로, 가시성만 추가). (d) BEGIN IMMEDIATE가 try 블록 밖에 있어 그 문장 자체가 락 경합으로 실패하면 finally의 conn.close()를 건너뛰어 커넥션이 샜다 — try 안으로 이동. (e) price_src를 200자에서 안 잘라 형제(boq_history()·app.py 등록수정 라우트)와 달리 standard_boq 실운영 값이 이력 사본보다 길어질 수 있었다(현재 데이터는 미발현) — 200자로 통일. 스키마 드리프트 재현으로 로그 실측, 재적재 대조군(같은값 무경고·다른값 경고) 실측, BEGIN IMMEDIATE 실패 시 close 실측, 250자 근거 절단 실측, seed_boq_led.py를 runpy로 실행하며 이력기록 1건 실패 주입해 24개 적재가 끝까지 실행되는지 실측, 5개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round269_fixes.py", "스캔 269라운드 회귀(2단계인증 totp.py 결함 2건, 268라운드 내내 한 번도 감사대상이 된 적 없던 보안 핵심 파일의 정밀조사 Agent가 발견 — (a) admins.totp_secret이 DB에 평문으로 저장됐다. 형제(crypto_util.py, 협력사 계좌번호에 AES-256-GCM 적용 중)와 달리 이 비밀키에는 암호화가 전혀 적용되지 않아 DB 파일 하나만 유출돼도 크래킹 없이 그 즉시 해당 계정의 2단계 인증이 완전히 재현됐다. app.py의 저장 1곳(등록)·조회 2곳(로그인검증·등록확인)에 CRYPTO.encrypt/decrypt를 적용했다 — decrypt()는 v1: 접두사가 없으면 평문으로 보고 그대로 돌려주므로(형제 계좌정보와 동일한 하위호환 방식) 기존에 이미 평문으로 저장된 비밀키도 마이그레이션 없이 계속 정상 동작한다. (b) 복구 코드가 4바이트(32비트, 43억 조합)뿐이었다 — hash_recovery()가 솔트 없는 단일라운드 SHA256이라(비밀번호 해시의 PBKDF2 60만회와 달리 브루트포스를 못 늦춘다) 실행으로 실제 생성한 코드 1개를 12코어 전수탐색으로 163.2초 만에 완전히 복원했다(DB유출 시나리오 전제, 로그인 자체엔 비밀번호가 별도로 더 필요함). hash_recovery()는 입력 길이에 무관하게 동작하므로 입력을 8바이트(64비트)로 늘리는 것만으로 충분하다 — 해시함수는 그대로 둬서 이미 발급된 기존 복구코드의 해시도 계속 유효하다. 암호화 왕복+레거시 평문 하위호환 실측, 새 엔트로피 형식 실측, 구 8-hex 형식 해시 회귀없음 실측, 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round270_fixes.py", "스캔 270라운드 회귀(협력사 계정 일괄발급 partner_accounts.py 결함 2건, 이 세션 사상 첫 주조사 — 형제인 app.py api_partner_bulk_credentials가 라운드199에서 이미 겪고 고친 것과 같은 유형을 이 CLI 쪽만 안 고친 채 갖고 있었다 — (a) UPDATE가 WHERE id=? 뿐이라 재확인이 없었다. 스크립트를 동시에 두 번 돌리면(응답지연 오인 재실행 등) 두 실행이 같은 업체를 대상으로 각자 비밀번호를 계산한 뒤 나중에 커밋한 쪽이 먼저 커밋한 쪽을 에러 없이 조용히 덮어썼다(실측: 스레드 2개로 재현, 먼저 화면에 찍혀 전화로 불러줬을 비밀번호가 그 순간 무효가 됨). WHERE에 재확인(AND COALESCE(login_id,'')='')을 걸고 rowcount로 확정하도록 수정. (b) main()의 배치루프에 항목별 예외처리가 없고 commit()은 루프 전체가 끝난 뒤 한 번뿐이었다 — 한 업체 처리 중 예외(대표적으로 UNIQUE 충돌)가 나면 그 앞에서 이미 성공으로 화면에 찍힌 업체들까지 통째로 날아간다. 형제(app.py api_partner_bulk_credentials, 라운드199)의 SAVEPOINT/ROLLBACK TO SAVEPOINT 패턴을 그대로 옮겨 이 업체 몫만 격리하도록 수정. 스레드 2개로 동시실행 경합을 실제 재현(승자 1명 확정+패자는 스스로 인지+DB값 최종검증), 배치 중 예외주입으로 나머지 2곳이 살아남는지 실측, 2개 지점 각각 되돌려 실패 재현 후 복원 — 검증 과정에서 최초 작성한 테스트 하네스 자체의 결함(스레드 간 sys.stdout 전역치환 경합)도 prove 단계에서 발견해 함께 고쳤다)"),
    ("test_scan_round271_fixes.py", "스캔 271라운드 회귀(수집이메일 정리 clean_collected_emails.py 결함 3건, collect_emails.py 감사 라운드267의 직접적 후속 companion으로 이 세션 사상 첫 주조사 — (a) UPDATE가 예외처리 밖에 있고 commit은 루프 전체가 끝난 뒤 단 한 번뿐이었다. 저장 하나가 실패하면(락 경합 등) 이미 화면에 삭제로 찍힌 나머지 행까지 전부 저장되지 않았다(실측: 재조회하면 아무것도 안 지워져 있었다) — 형제(geocode_fill.py·seed_boq_led.py, 라운드265·268)처럼 행마다 즉시 커밋하고 실패한 행만 건너뛰도록 수정. (b) 되돌릴 수 없는 삭제인데 대상 DB 경로 표시·완료 감사로그가 없었다 — 형제 배치도구(geocode_fill.py·seed_boq.py 등)는 전부 갖고 있는데 이 파일만 빠져 있었다 — 표시·로그 추가. (c) 지운 이메일 원문 대신 정적 문구만 남겨 오탐이 나도 무엇을 지웠는지 DB 백업 없인 알 수 없었고, 같은 정크 주소가 재수집→재정리를 반복하면 이 정적 문구가 무한히 중복 누적됐다(실측) — 지운 원문을 메모에 남기고 이미 있는 마커는 다시 안 붙이도록 수정. DB연결을 가로채 저장 1건을 실패시켜 나머지가 살아남는지, 실행화면의 DB경로·감사로그 증가·메모에 원문보존을, 재수집 시뮬레이션으로 마커 비중복을 각각 실측, 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round272_fixes.py", "스캔 272라운드 회귀(팝빌 연동점검 popbill_check.py 결함 2건, notify_popbill.py 감사 라운드262의 companion으로 이 세션 사상 첫 주조사 — (a) 이 도구는 항상 새 프로세스로 뜨므로 라운드262가 막은 키교체 후 재시작 전 상태를 이 프로세스 자신은 절대 겪을 수 없다. 그래서 이 점검이 전부 성공으로 끝나도 그건 이 프로세스 기준으로는 문제없다는 뜻일 뿐 이미 떠 있는 운영 서버(app.py)가 재시작됐다는 보장이 아닌데 이 사실을 한 줄도 알리지 않았다 — 실측: 두 프로세스를 나란히 흉내내 재현, 이 도구가 100% 성공으로 나오는 바로 그 순간 운영 서버는 라운드262 가드로 발송을 계속 거부하고 있을 수 있었다. 매 실행마다 운영 서버 재시작 필요성을 알리는 경고를 배너 직후에 추가. (b) 자체 .env 파서가 모든 진입점(app.py/wsgi.py/serve_waitress.py/manage.py)이 공유하는 envload.py와 달리 값의 따옴표를 안 벗겼다 — 따옴표를 쓴 .env를 쓰면 이 도구만 따옴표까지 낀 값을 읽어 LinkID가 틀렸다는 오탐을 낸다(실측). 서버와 같은 값으로 점검한다는 이 함수 자신의 목적을 지키려면 서버가 실제로 쓰는 그 로더에 위임해야 해서 자체 파싱 대신 envload.load_dotenv() 호출로 교체. 공유로더를 통한 따옴표 제거 실측, main() 실행화면에 경고가 실제로(자격증명 없이도, 단계1보다 먼저) 찍히는지 실측, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round273_fixes.py", "스캔 273라운드 회귀(운영서버 진입점 serve_waitress.py 결함 3건, 이 세션에서 처음으로 companion 스크립트 대신 서빙 계층 자체를 감사한 라운드, 정밀조사 Agent가 발견 — (a) 시작배너 print에 flush=True가 없어 정상종료에서만 로그파일에 남았는데, 실제 운영 재시작은 전부 감시자(외부접속_상시가동.ps1)의 Stop-Process -Force 하드킬이라(실측: 동일 리다이렉트+하드킬 패턴으로 재현) waitress_out.log에 이 배너가 사실상 영원히 안 남았다 — flush=True 추가. (b) serve() 호출에 예외처리가 전혀 없어 포트가 이미 쓰이고 있으면 waitress/asyncore 내부 스택프레임 15줄짜리 트레이스백만 나왔다(실측: PermissionError WinError 10013) — 한국어로 원인·확인명령까지 안내하는 SystemExit으로 감싸도록 수정. (c) envload.py 자신의 문서가 이 파일도 공유한다고 명시하는데 실제로는 직접 안 부르고 wsgi.py의 같은 호출이 먼저 실행되는 import순서의 우연에 기대고 있었다(실측 확인: 지금은 정상 동작하지만 두 줄 순서가 바뀌면 조용히 깨짐) — 명시적으로 호출하도록 수정. 격리 포트로 실제 waitress 프로세스를 하드킬해 배너 생존 실측, 포트 사전점유로 충돌 재현해 친절한 안내 실측, 명시적 env로드가 OS환경변수를 안 덮는지 실측 — 운영 포트(8771)는 전 과정에서 미접촉, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round274_fixes.py", "스캔 274라운드 회귀(첫날재현 도구 firstday_server.py 결함 3건, 자동화 파이프라인에서는 죽은 코드지만 사람이 손으로 반복 실행해 온 도구로 판정된 파일의 사상 첫 주조사 — (a) db.py의 운영DB 안전장치는 진입점 파일명이 test_로 시작할 때만 발동해 이 파일은 가드의 보호를 못 받는다. 오늘은 BOKGUON_DB_PATH를 먼저 정하는 줄이 항상 먼저 실행돼 문제가 없지만 그건 내용이 우연히 안 틀렸다는 것일 뿐이다(실측: 이 이름 그대로에서 그 줄을 생략하면 가드가 전혀 안 걸리고 운영 DB 경로를 그대로 문다) — import app 직전에 실제 환경값을 마지막으로 한 번 더 확인해 운영 DB 파일과 같은 경로면 확실히 막도록 수정. (b) Werkzeug 개발서버가 Windows에서 같은 host:port 이중 바인딩을 막지 않아 예외도 트레이스백도 없이 두 프로세스가 같은 포트를 나눠 쓴다(실측: 동일 스크립트를 두 번 실행해 재현, netstat으로 두 PID가 동시에 LISTENING임을 확인, 첫 프로세스를 죽여도 healthz가 계속 200이라 두 번째가 실제로 요청을 처리하고 있었음을 확인) — app.run() 전에 포트 선점 여부를 직접 확인하도록 수정. (c) 특정 사용자 계정 절대경로가 3곳에 하드코딩돼 있었다(형제 test_firstday.py는 이미 self-path 계산으로 이 문제를 피해감) — HERE 계산으로 통일. 추출한 실제 DB검사코드를 미설정·운영경로일치·정상 세 조건으로 서브프로세스 실행해 실측, 포트 사전점유로 이중바인딩 방지 실측, 정상기동 회귀없음 확인, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round275_fixes.py", "스캔 275라운드 회귀(로컬 TLS 리허설 프록시 dev_tls_proxy.py 결함 2건, 같은 deploy_z.py 주석에서 개발 전용으로 언급된 이 세션 사상 첫 주조사 파일 — (a) Windows는 SO_REUSEADDR를 걸어도 같은 host:port 이중 바인딩을 막지 않는다(firstday_server.py 274라운드가 먼저 발견한 것과 같은 패턴, 실측: 같은 리슨포트로 두 인스턴스를 띄우면 둘 다 bind 성공, 첫 프로세스를 죽여도 둘째가 조용히 이어받아 응답한다) — bind 전에 포트 선점 여부를 직접 확인하도록 수정. (b) TLS 핸드셰이크 실패가 완전히 무로그로 삼켜졌다(실측: 평문 바이트를 HTTPS 포트로 보내면 로그 0줄) — 같은 파일의 형제(handle()의 백엔드 연결 실패)는 이미 print로 남기는데 이 자리만 침묵했다, 형제와 같은 형식으로 로그를 남기도록 수정. 수정 과정에서 새로 추가한 로그 자체가 flush=True 없이는 하드킬 시 유실된다는 것(serve_waitress.py 273라운드와 같은 함정)을 자체발견해 이 파일의 모든 print에 flush=True를 함께 적용. 포트 사전점유로 이중바인딩 방지 실측, 평문쓰레기 주입으로 핸드셰이크 실패 로깅 실측, TLS→평문→TLS 왕복 릴레이 회귀없음 실측, 2개 지점 각각 되돌려 실패 재현 후 복원 — 운영 포트(8771)는 백엔드 프록시 대상으로도 전혀 사용하지 않고 전 과정 격리 포트로만 검증)"),
    ("test_scan_round277_fixes.py", "스캔 277라운드 회귀(db.py migrate() 핵심 마이그레이션 함수 결함 2건, db.py 전체가 아닌 migrate() 로 범위를 좁힌 정밀조사 Agent가 발견 — 매 app.py 기동마다 도는 함수라 이 세션에서 가장 근본적인 지점. (a) status_at 백필·발송대기함 정리·B4(job_locks/설정/마감백필)·관리자등급 정규화·수수료율bp 환산·정산 partner_id/insurer_id 백필, 6개 블록의 except 가 전부 완전 침묵(bare except: pass) — 형제인 바로 위 MIGRATIONS 루프는 이미 verbose 모드에서 실패를 print 하는데 이 6곳만 스키마 드리프트가 있어도 아무 신호가 안 남았다. (b) 여러 문장을 한 커밋에 묶은 블록(B4·관리자등급·정산백필)은 rollback 이 없어, 먼저 실행됐지만 미커밋인 문장이 다음 블록의 트랜잭션에 얹혀 다음 블록이 성공하면 우연히 같이 저장되고(자가치유), 뒤이은 블록들마저 전부 실패하면 close()에서 통째로 사라졌다 — 실측(정밀조사 Agent의 폴트주입): job_locks·settings가 재연결 후 0행이 됨. job_locks 는 _sweep_claim() 이 기대는 행이라, 사라지면 경매 마감이 예외도 로그도 없이 영원히 멈춘다. 문장을 블록별로 쪼개 각자 즉시 커밋하고 실패 시 rollback 하도록 수정(job_locks 를 가장 먼저·독립적으로 커밋), 6곳 모두에 verbose 로그를 추가. 정상 경로(폴트 없음) 6블록 전부 회귀 없음을 먼저 확인한 뒤, status_at 실패 시 로그+rollback 실측, job_locks 뒤의 모든 블록(설정·마감백필·관리자등급 2문·수수료율·정산 2문)을 동시에 실패시켜도 job_locks 는 재연결 후에도 살아있음을 실측(정밀조사 Agent의 최악 시나리오 재연), 관리자등급 G1/G2·정산 partner_id/insurer_id 각각의 독립 커밋을 실측, 두 번 연속 실행 멱등성 확인, 4개 지점(status_at·B4 3분할·관리자등급 2분할·정산 2분할) 각각 되돌려 실패 재현 후 복원 — MIGRATIONS 테이블명 오타 시 PRAGMA 가 빈 집합만 돌려줘 verbose 로그조차 못 남기는 잠재결함 1건은 현재 180개 항목 전수감사 결과 발현 사례 0건이라 가상 리스크로 판단해 미조치)"),
    ("test_scan_round278_fixes.py", "스캔 278라운드 회귀(compliance.py 도급 적법성 관문 결함 2건, compliance.py 사상 첫 주조사로 정밀조사 Agent가 발견 — (a)[심각] 화면이 실제로 제공하는 12개 공종(app.py WORK_MAJORS) 중 '방음벽·휀스·펜스'가 도급 판정표(WORK_RULES)에 아예 없다(manage.py selfcheck 가 이미 실측 기록만 해 두고 고치지는 않은 상태). rule_for() 는 복합공종 문자열('복합(A · B · C)') 전체에 부분일치를 걸어 하나라도 걸리면 그걸로 전체를 판정했다 — 실측: '복합(방음벽·휀스·펜스 · 누수·배관·설비)'가 누수·배관·설비의 규칙(전문공사 1500만원)만으로 판정돼, 판정표에 없는 방음벽·휀스·펜스 몫은 위험도 평가를 안 거친 채 800만원짜리 건이 그대로 '도급가능'(안전선 1200만원 이내)으로 통과했다 — 이 파일 37행 자신의 원칙('업종 매핑이 확정되지 않은 공종은 통과시키지 않는다')과 정면으로 어긋난다. app.py 가 실제로 이어붙이는 구분자(' · ') 그대로 토큰별로 쪼개, 하나라도 판정표에 부분일치조차 없으면 전체를 기타(판정불가)로 내도록 수정 — 개별 업종을 배제/전문/타법 중 어디로 분류할지는 법률 판단이라 이번 수정 범위 밖으로 남김(파일 자신의 '아직 확정하지 못한 것' 절 참고, 8번째 표준 보류항목으로 메모리 등재). (b) '기타'(판정불가)로 떨어지는 두 경로(진짜 공종 미입력 vs 공종은 있는데 판정표에 없음)가 같은 '공종이 특정되지 않아' 문구를 써서, 체크박스로 정확히 '방음벽·휀스·펜스'를 골라도 마치 안 고른 것처럼 보여 운영자가 manage.py check 로 이어가지 못했다 — 공종이 실제로 있으면 그 값과 '판정표에 없다'는 진짜 원인을 함께 말하도록 수정(막는 방향 자체는 안 바뀜, 메시지 정확도만 개선). 판정표 버전(RULES_VERSION) 도 함께 올렸다(판정 결과가 바뀔 수 있는 변경이라 이 파일 자신의 원칙에 따름). 실행으로 정밀조사 Agent가 찾은 복합공종 재현(순서 뒤바꿔도 재현), 이미 판정표에 다 있는 기존 복합공종(배제업종이 이겨야 함)·단독 기존 공종·진짜 공종미입력 세 회귀시나리오 통과, 실제 gate()/실DB 경로(app.py 의 5개 낙찰확정 지점이 전부 부르는 그 함수)로도 재현, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round280_fixes.py", "스캔 280라운드 회귀(발송함 안내문 api_outbox() 결함 1건, 272라운드 popbill_check.py 감사 도중 사용자가 인접 파일 app.py에서 직접 지목한 부수 발견 — 272라운드 자체의 수정범위는 popbill_check.py였고 이 결함은 그때 손대지 않았다. pb[ready]=False 인 else 분기가 원인문구(why)를 sdk_installed·missing 두 값만 보고 조립했는데, notify_popbill.status() 의 ready 는 262라운드부터 sdk_ok and not missing and not rotated 로 계산돼 키 교체 직후·재시작 전(key_rotated_pending_restart=True, missing=[], sdk_installed=True) 상태에서도 ready=False 가 될 수 있다 — 이 조합에서 why=미설정 항목: +빈 join() 이 되어 화면에 빈칸 섞인 무의미한 문구만 뜨고 진짜 원인(재시작 필요)은 어디에도 안 보였다. notify_popbill.send()(262라운드)가 이미 쓰는 문구를 그대로 재사용해 rotated 를 최우선 분기로 추가. ⚠303라운드가 발견: 이 회귀테스트 자신이 원래 279→280→281 동시세션 번호경합(dispatch.py 회귀와 충돌해 내용이 한 번 덮어써짐, 파일 자신의 docstring 이 이미 이 경위를 기록)의 피해자였는데, run_all_tests.py 는 한때 이 결함을 test_scan_round300_fixes.py 라는 이름으로 등록해 두고 있었다 — 그런데 실제 그 파일명은 이후 완전히 다른 내용(ingest_partners.py·partner_accounts.py, 진짜 300라운드)으로 채워졌고 그쪽은 이미 별도로 올바르게 등록돼 있어, 이 옛 등록은 존재하는 파일을 실제와 다른 설명으로 가리키며 중복 등록한 상태로 남아 있었다 — 그 결과 이 회귀(test_scan_round280_fixes.py, 디스크엔 계속 있었다) 자신은 배터리에 단 한 번도 포함된 적이 없었다. 파일명을 실제 내용과 일치하는 280으로 정정하고 중복 등록을 제거. 단독 재실행 7/7 통과로 app.py 의 실제 수정(14485행 부근)이 지금도 살아있음을 재확인한 뒤에 등록 — app.py 는 미변경이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round281_fixes.py", "스캔 281라운드 회귀(dispatch.py 출동배차 모듈 결함 2건, round257 이 sweep_dispatches() 만 감사하고 claim/decline/arrive/close_no_repair 는 처음 다룬 정밀조사 Agent가 발견 — ⚠원래 279번으로 작성했으나 다른 세션의 app.py 발신함 수정과 279번이 겹쳐 280번으로 옮겼고, 그 다른 세션도 독립적으로 280번으로 옮기는 바람에 두 번째로 겹쳐 최종적으로 281번으로 정착(그 세션의 실제 app.py 수정은 무사, 그 세션 자신의 회귀테스트 파일만 이 과정에서 유실돼 재작성이 필요할 수 있음 — 세션 간 SendMessage 로 통지함). (a) decline() 만 감사로그(DB.log)가 없었다 — 같은 파일의 형제(claim·arrive·close_no_repair 등)는 상태를 바꾸는 자리마다 전부 남긴다. 그 결과 사건 상세의 감사이력(activity_log.detail LIKE '사건번호' — 라운드94·117·190 이 지켜 온 바로 그 조회)·관리자 감사로그 화면·운영 대시보드 최근활동 어디에도 누가 언제 거절했는지가 안 남았다(dispatch_calls.response='거절' 자체는 남지만 사건번호로는 못 찾는다) — 실제 실행으로 재현(거절 전후 activity_log·사건이력 조회 건수 대조). 형제와 같은 자리(성공 시, commit 직전)에 DB.log() 추가 — rowcount=0(이미 응답·데모 등 아무 변화 없는 시도)에는 로그를 안 남기도록 과잉로깅도 방지. (b) _release_lease() 의 완전 침묵 except가 형제 3곳(수배알림실패·밀려난협력사통지실패·자동재수배실패)과 다른 기준이었다 — job_locks 표를 강제로 없애 실패를 재현해 로그가 남는지 실측(리스는 120초 뒤 자연만료로 회복되니 동작 자체는 안 바꾸고 가시성만 추가). 실행으로 거절 성공 시 감사로그 1건 신규 생성+사건이력 조회로 실제 검색됨, claim() 회귀없음, 재거절·데모수배 대조군(로그 안 남음, 과잉로깅 아님 확인), 2개 지점 각각 되돌려 실패 재현 후 복원 — 낮은 확신 관찰 2건(claim() 의 response IS NULL 가드 비대칭, assign_dispatch() 슈퍼시드 시 미응답 후보 정리 누락)은 코드결함으로 단정 못해(전자는 의도된 유연성일 수 있음, 후자는 claim()의 CAS 재확인이 이미 무해화함을 실측 확인) 미조치)"),
    ("test_scan_round282_fixes.py", "스캔 282라운드 회귀(ingest_partners.py + deploy/bootstrap.sh 결함 2건, ingest_partners.py 사상 첫 주조사로 정밀조사 Agent가 발견 — (a)[심각] load_journal() 은 companies 가 list 인지만 확인하고 그 원소 하나하나가 dict 인지는 안 봤다 — 리서치 에이전트 출력이 스키마를 완벽히 안 지킨 원소(맨 문자열·None 등) 하나만 섞여도 main() 루프의 c.get(\"name\")에서 AttributeError 로 죽는다. 이 스크립트는 existing 을 메모리에서만 쌓다가 루프가 끝나야 파일에 한 번(json.dump 루프 밖 한 곳뿐) 쓰므로, 죽는 순간 이미 검증까지 마친 앞쪽 항목들까지 전부 파일에 안 남고 사라진다(실측: 크래시 후 파일이 실행 전과 바이트 단위로 동일) — geocode_fill.py·collect_emails.py·clean_collected_emails.py·seed_boq_led.py·partner_accounts.py 에서 이미 반복 발견된 바로 그 유형(배치루프 DB/파일 write가 항목별 예외처리 밖). 형제(이름없음·출처없음 거부)와 같은 방식으로 dict 아닌 원소만 건너뛰도록 수정. (b) deploy/bootstrap.sh 가 이 스크립트를 인자 없이 호출해 신선한 배포마다 100% 실패(usage 출력 후 exit 1)했는데 && ok || warn 관용구가 조용히 건너뜀 경고로 삼켰다(실측: 실제 서브프로세스 실행으로 재현) — 설령 인자를 준다 해도 소용없다: 협력업체 398개사는 바로 위 manage.py init 이 partners_seed.json 을 이미 읽어 운영 DB 에 넣은 뒤라 이 스크립트는 그 JSON 파일 자체만 갱신할 뿐 이미 초기화가 끝난 DB 에는 반영되지 않는다 — 배포 자동화가 아니라 리서치 결과를 손으로 병합해 다음 배포 시드로 커밋하는 로컬 유지보수 CLI임이 드러나 bootstrap.sh 의 호출 자체를 제거(스크립트 자신의 인자검증 동작은 안 바꿈). 실행으로 비-dict 3종(문자열·None·정수)이 섞여도 앞뒤 정상 항목이 둘 다 파일에 남는지, 정상 배치 회귀없음, 인자없이 호출 시 여전히 안전하게 실패하는지(회귀 확인용) 검증, 2개 지점 각각 되돌려 실패 재현 후 복원 — deploy_z.py 는 이 라운드 조사 시점에 세션 스크래치패드에서 확인 안 됨(다른 동시 세션의 재작성 시점과 겹친 것으로 추정, 두 결함의 검증 자체엔 영향 없음)"),
    ("test_scan_round284_fixes.py", "스캔 284라운드 회귀(photo_ai.py 재인코딩 8MB 상한 미준수 결함 1건[심각], round229 이 EXIF실패 가시성만 다룬 이 파일의 나머지 로직 최초 정밀조사로 정밀조사 Agent가 발견 — _strip_exif() 가 위치정보 제거를 위해 고정 품질92 로 재인코딩했는데, save_upload() 는 업로드 원본 바이트만 8MB 상한과 대조하고(201-205행) 재인코딩 결과 바이트는 그 뒤로 아무도 상한과 다시 대조하지 않은 채 그대로 디스크에 쓰고 photos.size 로 반환했다. 이미 낮은 품질로 압축된 원본(카카오톡 재전송 사진 등)은 픽셀 디테일은 그대로인데 더 높은 품질로 재압축하면 파일이 커진다 — 정밀조사 Agent 실측: 7.2MB 원본이 재인코딩 후 11.7MB(상한 40%초과)로 아무 로그·표식 없이 저장됐다. 이 파일 자신이 사용자에게 보여주는 장당 8MB 이하 안내가 저장 단계에서는 지켜지지 않았던 것. 품질을 92→80→65→50→35 로 단계적으로 낮춰 가며 상한 안에 드는 첫 결과를 쓰도록 수정(_save_within_budget 신설, JPEG·WEBP 공통) — 전부 시도해도 안 되면(PNG 는 품질 다이얼이 없어 1회 재인코딩만) 원본을 그대로 저장하는 대신 UploadError 로 정직하게 거부한다(이 파일의 다른 복구불가 손상 케이스와 같은 경로, 이미 모든 호출부에 PHOTO.UploadError 핸들러가 있어 그대로 통합됨). HEIC 경로도 _heic_to_jpeg() 뒤에 항상 _strip_exif() 를 다시 거치므로 이 한 곳 수정만으로 전 업로드 경로에 적용됨. 직접 실행으로 저품질원본→고정92재인코딩 시 실제 성장(1.76배) 재현, 새 로직이 그 상황에서 실제로 상한을 지킴, 모든 품질단계로도 불가능하면 거부, PNG 도 동일 거부, 평범한 사진 회귀없음, 실제 save_upload() 종단(디스크 파일 크기까지) 재현 검증, 1개 지점 되돌려 실패 재현 후 복원)"),
    ("test_scan_round285_fixes.py", "스캔 285라운드 회귀(smoke_test.py 거짓초록 결함 1건[심각], 이 세션이 반복 경계해 온 자기도구가 내는 거짓 초록 패턴을 이 도구 자신에게서 처음 정밀조사해 정밀조사 Agent가 발견 — admin/partner/insurer 로그인 계정명이 하드코딩돼 있는데, 모든 실운영 배포의 필수·문서화된 단계인 manage.py go-live(DEPLOY.md 자신이 다음 단계 go-live 가 그 이름을 지운다고 미리 경고)가 admins.admin/staff 를 DELETE, partners/insurers.login_id=partner|insurer|insurer2 를 NULL 로 만든다. 그 순간부터 이 로그인들은 어떤 비밀번호로도 영원히 실패하는데, test_csrf·test_bidding·test_blockers·test_photos 는 전부 그 결과를 물려받는 if not m/if not (m and p and i) 게이트가 있어 CSRF·입찰·이중지급방지·IDOR·정산·사진권한 등 약 90개 검사 중 약 53개가 통째로 건너뛰어진다 — bootstrap.sh 자신의 주석은 그 검사만 건너뛰고 나머지는 계속 돈다고 믿고 있었는데 실측은 그렇지 않았다. FAIL 이 0건이라 exit 0(전부 통과)이 그대로 나가 이 사실이 숨겨졌다. 로그인 실패가 데모 계정 소실 때문인지 별도로 기록(DEMO_LOGIN_GONE)해 요약에 굵게 경고하고 새 종료코드 4(핵심 회귀검사 대부분 건너뜀)로 exit 0 과 구분하도록 수정 — 무엇을 검사했는지는 안 바꾸고 정직하게 보고만 하도록 함. 부수적으로 bootstrap.sh 의 잘못된 옛 주석 정정 + 새 종료코드4 경고 추가, DEPLOY.md 의 나머지 3개 smoke_test.py 호출(round125 가 놓친 곳들)에 비밀번호 환경변수 보강(고치기 전엔 매번 검사 0건·exit 2). Client.req() 를 몽키패치해 로그인 실패/성공 양쪽을 실제 함수(test_auth_isolation·test_admin·main) 로 종단간 재현, 관련 없는 9개 검사함수만 무해한 스텁으로 격리, 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round286_fixes.py", "스캔 286라운드 회귀(envload.py 대체파서 인라인주석 오염 결함 1건, 모든 진입점(app.py/wsgi.py/serve_waitress.py/manage.py)이 공유하는 이 파일 사상 첫 정밀조사로 정밀조사 Agent가 발견 — load_dotenv()는 python-dotenv가 있으면 그걸 쓰고 없으면 자체 대체 파서로 넘어가는데, 그 대체 파서는 한 줄 전체 주석만 걸렀지 값 뒤에 붙는 인라인 주석(KEY=값  # 설명)은 전혀 안 걸러 그 문구까지 값에 그대로 붙었다 — 실측: SECRET=abc123  # rotate quarterly 를 로드하면 저장된 값이 'abc123  # rotate quarterly'가 됐다. 아무 예외·로그 없이 조용히 비밀값·설정값이 오염된다. 오늘은 python-dotenv가 requirements.txt에 고정 설치돼 있어(실제 설치 확인됨) 이 경로 자체가 항상 건너뛰어지는 죽은 코드지만, venv 손상 등 비정상 상황에서 이 경로를 타는 순간 조용히 발현된다. 공백 뒤에 오는 #부터 주석으로 잘라내되(정식 dotenv 관례와 맞춤 — # 바로 앞에 공백이 없으면 값의 일부) 따옴표로 감싼 값은 그 안의 #을 주석으로 안 보도록 수정. sys.modules[dotenv]=None으로 대체 파서 경로를 강제 선택해 그 경로 자체를 직접 실행 검증(정밀조사 Agent와 같은 방법), 핵심 재현(인라인주석 제거)에 더해 이미 확인된 8개 사례(등호중복·양쪽따옴표 교차포함·공백없는#·빈값·따옴표안# 등)와 전체행주석·빈줄·등호없는줄·기존 OS 환경변수 우선순위까지 전부 회귀없음 확인, 1개 지점 되돌려 실패 재현 후 복원)"),
    ("test_scan_round287_fixes.py", "스캔 287라운드 회귀(gunicorn_conf.py 결함 2건, wsgi.py·gunicorn_conf.py 사상 첫 정밀조사 — wsgi.py 는 실측 결과 클린(envload 명시적 호출·순서 정상, 배너/로깅 문제 없음, 예외처리는 gunicorn arbiter가 이미 안전하게 처리), gunicorn_conf.py 에서만 정밀조사 Agent가 발견 — (a) threads=4가 하드코딩돼 있었다. .env.example(23행)에 BOKGUON_THREADS=8이 이미 있고 형제 진입점 serve_waitress.py(23행)는 실제로 그 값을 읽는데 이 파일만 환경변수를 아예 안 봤다. .env.example에서 이 변수가 바로 옆 BOKGUON_BIND·BOKGUON_WORKERS(gunicorn 전용, 실제로 읽힘)와 같은 구역에 있어 운영자가 이 값을 올려도 gunicorn은 경고·로그 없이 계속 4로 돈다 — 형제와 같은 변수를 읽도록 통일(기본값 4는 유지). (b) 요청 헤더 크기 제한(헤더 기반 DoS 완화)라는 주석 아래 세 값(limit_request_line=4094·limit_request_fields=100·limit_request_field_size=8190)이 gunicorn 23.0.0(requirements.txt로 고정된 그 버전) 자체 기본값과 완전히 동일했다(실측: gunicorn 공식 소스 LimitRequestLine/Fields/FieldSize 클래스 default와 대조) — 이 블록은 실제로는 아무것도 강화하지 않는데 주석은 마치 기본보다 강화된 값을 쓰는 것처럼 읽혔다. 값 자체를 더 좁히는 것은 실제 트래픽을 보지 않고는 못 정하는 보안정책 결정이라 범위 밖 — 왜 기본값과 같은 값을 굳이 명시했는지(향후 gunicorn 버전업에도 조용히 안 바뀌게 고정)를 정확히 말하도록 주석만 정정. 순수 설정 모듈로 직접 로드해(gunicorn 자체는 이 Windows 개발기에 미설치, 확인됨) 환경변수 반영 실측, 미설정 시 기존 기본값 유지 회귀없음, 헤더상한 값 자체는 안 바뀜 확인, bind 등 다른 환경변수 설정 회귀없음, 2개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round288_fixes.py", "스캔 288라운드 회귀(입점신청 1인사업자 제외 정책 우회 결함 2건[심각], 공개 신청폼 apply_partner.html/apply_insurer.html 최초 정밀조사 — apply_insurer.html과 /api/leads는 실측 결과 클린, apply_partner.html의 백엔드 관문 3곳에서만 정밀조사 Agent가 발견 — (a) 공개접수(api_create_application)·직접접수(api_application_create)·승인(api_application_update) 세 관문이 전부 str(staff_count)==0 또는 ==0(정확히 문자열/정수 0)만 봤다 — 값을 아예 안 보내거나(라운드248이 고친 바로 그 우회를 필드명만 다시 두면 재현) 음수·이상값을 보내면 전부 통과했다. 실측(Flask 실서버, staff_count 생략): 공개 폼 접수 200 성공, 승인까지 200 성공 — 상시인력 미확인 업체가 그대로 입찰 가능한 활성 협력사가 됐다. 폼의 staff_count는 required라 정상 제출이면 항상 값이 있어야 하므로 공개접수는 파싱된 staff_n으로 없음·0·음수를 전부 막는다. 직접접수(전화·팩스)는 admin.js 자신의 안내(미입력 시 심사 때 확인하세요)대로 미입력은 일부러 허용하는 흐름이라 명백히 잘못된 값(0·음수)만 막고, 최종 방어선인 승인 관문도 같은 기준(미입력은 검토자 판단에 맡기고 0·음수만 최종 차단)으로 통일. (b) staff_count가 API 응답(SELECT *)에는 이미 있는데 admin.js 심사 화면(appDetail()) 어디에도 안 보였다 — 승인 버튼을 누르는 사람이 정작 그 값을 볼 방법이 없어 직접접수의 심사 때 확인 안내 자체가 무의미했다. 상세모달에 상시 인력 값을 미확인/1인사업자/정상 세 갈래로 눈에 띄게 추가. Flask 실서버+격리DB로 세 관문 전부(공개접수 생략·음수·0·정상, 직접접수 생략·음수, 승인 미입력·음수·0·정상) 실측 검증, admin.js는 이 세션의 표준 검증방식(Node.js 직접실행)으로 appDetail() 렌더링 실측(다른 세션이 이 폴더에서 별도 dev서버를 띄우고 있어 브라우저 확인은 표준 경로 아님), 4개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round289_fixes.py", "스캔 289라운드 회귀(하자담보책임기간 24개월 고정표기 결함 3건, legal_docs.py 사상 첫 정밀조사로 정밀조사 Agent가 발견 — cases.warranty_months 는 사건마다 관리자가 0~120 사이로 다르게 정하는 실제 컬럼인데(기본 24, NULL 일 때만 24로 대체 — db.py 278행), 실제 하자보증 판정(app.py _warranty_left)과 실제 개인정보 파기 기준일(manage.py _WEND, cmd_prune_personal)은 전부 이 사건별 실값을 쓴다. 그런데 공개 법정 문서 두 곳과 보험사 포털 화면 한 곳이 24개월을 보편적 고정값처럼 적어 실제 동작과 어긋났다 — (a)[심각] PRIVACY 제3조 표의 하자보수 관련 기록·피해자 성명·연락처 두 행이 파기 기준일을 하자담보책임기간(24개월)이라고 못박아, warranty_months 가 6이면 실제로는 완료 후 30개월 만에 지워질 피해자 성명·연락처를 처리방침은 24개월 기준으로 안내하고 있었다(개인정보 보호법 제30조 — 처리방침과 실제 처리가 일치해야 한다는 원칙 위반). (b) TERMS 제7조 1항도 같은 24개월간을 고정 서술해, 시행사 포털(partner_portal.html)이 이미 사건마다 보여주는 실제 값과 약관이 서로 다른 말을 했다. 사건별로 정해지며 기본이 24개월이라는 사실 자체를 밝히도록 문구만 정정(운영 메커니즘·검증 로직은 손대지 않음 — 이미 확인된 0=무보증 유효값 설계를 그대로 존중). (c) insurer_portal.html 의 defectForm() 하자 접수 모달도 하자보증 24개월을 고정 표시했는데, 접수 직후 토스트는 서버가 계산한 사건별 실제 warranty_ok 를 알려준다(app.py _warranty_left) — 같은 사건에 대해 접수 전후 안내가 서로 다른 말을 했다. 형제 화면(partner_portal.html 386행)이 이미 쓰는 c.warranty_months??24 표기로 통일. legal_docs.py 상수(PRIVACY·TERMS) 실제 렌더 결과와 /legal/terms·/legal/privacy 실제 HTTP 응답(운영모드 포함) 양쪽에서 옛 고정문구 소멸을 실측, insurer_portal.html 은 이 세션의 표준 검증방식(Node.js 직접실행)으로 defectForm() 이 6개월·0개월(무보증)·미설정(기본 24) 세 사건을 각각 정확히 반영하는지 실측(?? 는 0을 유효값으로 존중 — || 였다면 24로 둔갑했을 것), 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round290_fixes.py", "스캔 290라운드 회귀(공유 디스패처 actions.js 의 data-act-enter 가 data-arg 를 안 넘기던 결함 1건[심각], static/actions.js·tray.js·lightbox.js — 이 세션 static/ 안에서 마지막까지 남아있던 미조사 JS 3종 — 최초 정밀조사로 정밀조사 Agent가 발견, tray.js·lightbox.js 는 실측 결과 클린. actions.js 는 click·change·input·keydown-Enter 4종 디스패처로 data-act 계열 속성을 실제 함수에 연결하는데, change·input 두 디스패처는 이미 el.getAttribute('data-arg') 를 4번째 인자로 넘기고(input 쪽은 자신의 주석이 '안 넘기면 조용히 죽는다'고 이미 경고해 뒀다) enter 디스패처만 그 넘기기가 빠져 fn(el.value, el, ev) 세 개뿐이었다. data-act-enter 사용처 자체는 흔해도(admin.js 9곳+insurer_portal.html 1곳) 대부분 무해하다 — data-arg 를 안 읽거나 읽어도 실제로 안 쓰는 핸들러이기 때문. 그러나 클릭 경로(data-arg 1번째)와 Enter 경로(el.value 가 1번째, data-arg 는 4번째여야 함)를 모두 지원하도록 설계된 공유 컴포넌트 정확히 2곳은 실제로 깨졌다 — ① searchBar()(admin.js 66행, 관리자 콘솔 15개 화면 공용 검색창, runSearch): Enter 를 치면 화면 이름 대신 방금 입력한 검색어 자체가 view 로 들어가 VIEWS[view] 가 undefined 라 TypeError 로 죽어 화면이 그대로 멈춘다 — 같은 화면의 검색 버튼을 클릭하면 정상 동작해 와서 안 드러났다. ② 사건 상세의 메모 추가(admin.js 2065행, addMemo): Enter 를 치면 case:77 대신 입력한 메모 본문 자체가 인자로 들어가 target_type=그 문자열·target_id=NaN(JSON 직렬화 시 null)이 되어 서버(app.py MEMO_TARGETS 검사)가 400 잘못된 대상입니다로 거부해 메모가 저장되지 않는다 — 메모 추가 버튼을 클릭하면 정상 동작해 와서 안 드러났다. actions.js 의 enter 디스패처가 이제 4번째 인자로 data-arg 를 넘기도록(형제 change·input 디스패처와 통일) + admin.js 의 ACT.runSearch·ACT.addMemo 두 등록이 클릭(1번째 자리)·Enter(4번째 자리) 두 경로를 모두 지원하도록 수정(클릭 경로는 4번째가 항상 null 이라 동작이 그대로 보존됨 — 회귀 없음). 나머지 8곳(unlockLogin·onbSearch·licSearch·doPartnerSearch·doCaseSearch·ctSearch·auditSearch, insurer_portal.html 의 doCaseSearch)은 전부 data-arg 를 안 쓰거나(무인자 함수) 실제로 무시하는 핸들러임을 각각의 등록·본문 코드로 확인해 안전함을 검증. Node.js 로 actions.js 실제 디스패처(document.addEventListener 등록을 최소 가짜 DOM 으로 그대로 실행)+admin.js 실제 runSearch·addMemo·ACT 등록을 종단간 결합해 클릭 경로 회귀없음·Enter 경로 정상화(TypeError 소멸, VIEWS.leads 정확 호출, {case,77} 정확 전송) 양쪽 실측, 3개 지점 각각 되돌려 실패 재현 후 복원)"),
    ("test_scan_round291_fixes.py", "스캔 291라운드 회귀(자기진단 도구 두 개의 사각지대 결함 4건, check_tx_paths.py·check_orphan_chars.py — tray.js·lightbox.js 는 290라운드에서 이미 클린 확인된 static/ 나머지 파일이라 이번엔 함께 조사만 하고 넘어간 파일 자기진단 도구 두 개(BEGIN IMMEDIATE 트랜잭션 commit/rollback 누락 점검·고아문자 점검)를 정밀조사 Agent가 감사 — 결함을 잡는 도구 자신이 사각지대를 갖고 있는가를 보는 round285 smoke_test.py·round272 popbill_check.py 계열 조사. check_tx_paths.py 2건 — (a)[심각] begins_immediate() 가 calls_of() 의 첫 항목을 잠금 시작줄로 썼는데 calls_of() 는 ast.walk() 의 너비우선 순서를 쓴다 — 소스상의 줄 순서가 아니다. app.py 의 api_login_otp() 처럼 BEGIN IMMEDIATE 가 두 번(if 안쪽 얕은 곳과 그 뒤 최상위) 나오면 더 얕은 뒤쪽이 먼저 나와 진짜 첫 잠금 직후의 return 들이 잠금 이전으로 오판돼 검사를 완전히 건너뛰었다(실측: 94개 검사대상 함수 중 이 함수에서 실제로 재현, 지금은 그 두 return 이 우연히 정상 커밋/롤백돼 있어 실제 사고는 없다 — 도구의 사각지대일 뿐이며 미래의 회귀를 못 잡는 상태였다). 가장 이른 줄번호(min)를 쓰도록 수정. (b) calls_of()·_is_begin_immediate_call() 이 커넥션 변수명을 conn 하나로만 하드코딩했다 — app.py 의 _upload_damage_photos() 처럼 두 번째 커넥션을 c2 라는 별도 이름으로 여는 함수의 그 임계구역은 이름 매칭 자체를 못 지나쳐 존재가 안 보였다(실측: 코드베이스 전체에서 c2 가 유일한 사례). DB.get_db() 로 대입받는 이름은 전부 커넥션으로 인식하도록 수정(하드코딩 목록을 늘리는 대신 함수 안에서 실제로 쓰는 이름을 스스로 찾아 미래의 새 별칭도 자동으로 커버). check_orphan_chars.py 1건[문서 정확성] — BOM·NBSP 를 코드가 그 문자 자체를 다루려고 일부러 리터럴로 쓴 자리(.lstrip(로 BOM 벗기기, CSV 응답 앞에 BOM 붙이기, widont 스크립트의 NBSP 상수, 그 둘을 검증하는 테스트)까지 산문이 깨진 것처럼 잡았다 — 실측: 정밀조사 실행에서 나온 38건 전부가 이 두 글자 범주였고 전부 오탐, 진짜 조치 대상 0건(round124 가 ㆍ 하나로 이미 겪은 자주 우는 늑대 문제의 재발). 그 문자를 다룬다는 뜻의 식별자(.lstrip( · BOM · NBSP · \\ufeff)가 바로 앞뒤 줄 안에 있으면 건너뛰도록 수정(여러 줄에 걸친 문장도 놓치지 않게 앞뒤 한 줄씩 같이 봄) — 실측 38건→27건(11건 제거, 나머지 27건은 탐지기 자신의 정의·테스트 픽스처가 그 패턴을 직접 다루는 별개의 어려운 범주라 이번 라운드 범위 밖으로 남김). 부수적으로 deploy/*.ps1 배포 스크립트가 TARGET_EXT 에서 빠져 있던 것도 채움(round124 가 docs/ 를 채운 것과 같은 이유 — 현재 5개 파일 모두 클린이라 예방적 조치, 낮은 확신으로 표시). check_tx_paths.py 는 합성 함수(ast.parse 로 만든 재현 코드)로 두 결함 각각의 실제 함수(conn_names_of·begins_immediate)를 직접 호출해 검증하고 실제 app.py/dispatch.py/manage.py 에 대해서도 여전히 클린(회귀 없음)임을 재실행으로 확인, check_orphan_chars.py 는 실제 파일(envload.py·manage.py·templates/landing.html·app.py)의 오탐 소멸을 scan_file() 직접호출로 확인하는 동시에 합성 파일 대조군으로 마커 없는 진짜 오염은 여전히 잡히는지(과잉관용 아님) 검증, 4개 지점 각각 되돌려 실패 재현 후 복원 — check_tx_paths.py·check_orphan_chars.py 모두 app.py 가 import 하지 않는 독립 CLI 진단도구라 이번 라운드는 운영서버 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round292_fixes.py", "스캔 292라운드 회귀(manage.py 미조사 서브커맨드 결함 3건, 20개 cmd_* 중 17개(cmd_prune_personal/179·194·263, cmd_prune_orphans·cmd_check/124 만 부분적으로 다뤄짐)를 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — cmd_backup/cmd_restore/cmd_go_live 는 이미 두텁게 방어돼 있어 새 결함 없음. (a)[심각] cmd_install_scheduler 가 실제 이 PC에 등록된 예약작업과 완전히 어긋나 있었다. 실측(schtasks /Query /TN 복구온_경매마감 /XML, 읽기전용): 실제 작업은 Command이 이미 pythonw.exe, Arguments가 manage.py sweep, .bat 파일 자체가 없다(콘솔 깜빡임을 없애려 손으로 pythonw.exe 로 고쳐 둔 상태 — 프로젝트 메모리에 이미 기록된 조치). 그런데 이 코드는 그 사실을 전혀 모른 채 python.exe 로 _마감점검.bat 을 새로 만들어 schtasks /Create ... /F(무조건 덮어쓰기)로 등록하고 있었다 — 이 명령을 다시 돌리면(재배포 등) 이미 고쳐진 운영 작업을 콘솔 깜빡이는 python.exe+.bat 방식으로 조용히 되돌렸을 것이다. 옛 .bat 경유 방식의 근거(한글 경로가 bat 없인 조용히 실패한다)도 재실측: 지금 코드는 이미 os.system() 문자열조립이 아니라 subprocess.run([...]) 리스트 인자라 셸 파싱을 안 거친다 — 임시 작업이름으로 실제 등록해 XML로 확인하고 즉시삭제까지 해 보니 한글 경로를 절대경로 인자로 그대로 넘겨도 정상 등록됐다. .bat·cd 없이 pythonw.exe(없으면 python.exe 로 폴백)를 manage.py 절대경로와 함께 직접 등록하도록 수정(manage.py 자신도 HERE=os.path.dirname(os.path.abspath(__file__)) 로만 경로를 잡고 os.getcwd() 에 기대지 않으므로 작업 디렉터리 지정 자체가 불필요). (b) cmd_install_scheduler 의 --remove 가 schtasks 결과를 안 보고 무조건 해제했습니다를 찍었다 — 이미 해제됐거나 schtasks 자체가 막힌 환경(정책·권한)이면 schtasks 는 예외 없이 실패 종료코드만 낸다(실측: 없는 작업이름으로 재현 — returncode 1). 운영자가 껐다고 믿는데 실제로는 계속 돌 수 있었다. returncode 를 확인해 실패 시 정직하게 보고하도록 수정(설치 경로는 이미 이렇게 하고 있어 형제와 통일). (c) cmd_backup 이 DB_PATH 가 없을 때(오타·미초기화) sqlite3.connect() 가 조용히 빈 파일을 만들고, 그 빈 파일에 SELECT 를 던져 나는 OperationalError 가 범용 except 로 떨어져 디스크 여유 공간과 권한을 확인하세요라는 엉뚱한 안내를 냈다(실측: 격리 스크래치 경로로 재현). 게다가 실패해도 DB_PATH 자리에 그 빈 파일이 남는다. 시도 전에 os.path.exists() 로 막아 정확한 원인과 조치법을 안내하도록 수정. 부수적으로 deploy/복구온_예약실행_등록.ps1(별도 이름 복구온_스윕 작업을 만드는 다른 예약등록 스크립트)도 같은 이유로 python.exe에서 pythonw.exe 로 통일. cmd_install_scheduler 는 subprocess.run 을 가짜로 바꿔 진짜 예약작업을 절대 건드리지 않고 /Create·--remove 양쪽 실제 호출 인자와 반환값을 검증(이 결함 자체가 다시 돌리면 운영 작업을 조용히 되돌린다는 것이었으므로 실제 schtasks 호출 없이 증명), cmd_backup 은 격리 스크래치 DB로 존재하지 않는 경로(정확한 에러+빈파일 안남김)와 정상 경로(실제 백업 파일 생성+무결성검사) 양쪽 실행 검증, PS1 은 파서(Parser.ParseFile)로 구문 확인, 4개 지점 각각 되돌려 실패 재현 후 복원 — manage.py 는 app.py 가 import 하지 않는 독립 CLI 라 재기동 불필요)"),
    ("test_scan_round293_fixes.py", "스캔 293라운드 회귀(geo.py 미조사 함수 결함 2건, resolve()의 _AMBIG·SIDO_ALIAS[235·264라운드]와 case_coords()[235라운드]만 다뤄지고 나머지 7개 함수(_norm·_word_in·jitter·haversine_km·partner_coords·_has·is_precise)는 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — haversine_km·is_precise·partner_coords·_has·_norm 은 실측(실 DB·시드데이터·기존 회귀 143건 재실행) 결과 전부 클린. (a) jitter() — 사건이 몰린 지도에서 안 겹치게 흩뿌리는 결정적 오프셋인데 dx·dy 를 각각 -1~1 로 뽑아 그대로 더해 반경이 meters 가 아니라 정사각형(대각선 최대 meters*루트2)이었다. 실측: meters=350 기준 실제 최악거리 447m(1.28배 초과), 10만개 case_id 표본의 12.5%가 초과. 경도에도 위도와 같은 배율을 그대로 써서 위선이 극에 가까울수록 실거리가 짧아진다는 걸 안 봐(서울 위도 기준 동서:남북 = 0.79:1) 동서 방향이 실제보다 덜 벌어졌다. 각도+반경(넓이 기준 고른 분포)으로 뽑고 경도는 cos(위도)로 나눠 보정 — 심각도는 낮다(jitter 는 프라이버시가 아니라 지도 마커 겹침 방지용일 뿐이고, 구 단위 지도에서 수백미터 오차는 실제로 다른 구·바다로 안 넘어감을 실측 확인). (b) _word_in()의 오른쪽 경계 판정이 방위+구(서구·중구·동구·남구·북구)를 공백 없이 바로 뒤에 다른 지명이 붙으면(예: 서구청라동) 놓쳤다 — 구가 실제로 그 이름 자체의 행정단위 접미어인데 뒤 글자가 시군구읍면동리 중 하나가 아니면 무조건 거부해 인천 서구 지역중심 대신 인천 광역중심(도시 전체)까지 밀려났다. 실측: 실 DB 96건·partners 399건·시드데이터 398건 전수에 이 패턴이 0건이라 현재 오작동 사례는 없음(잠재 결함) — 그러나 강동·구리·성동·안동·양구·영동·정읍·하동처럼 우연히 같은 글자로 끝나는 무관한 지명(라운드120이 막은 함정과 같은 종류, 예: 강동원)까지 함께 풀어주면 그 보호가 깨지므로 _AMBIG 의 실제 키를 전수 확인해 진짜 복합 행정명 5개(중구·동구·서구·남구·북구)만 좁혀서 예외로 뒀다. 부수적으로 GU 딕셔너리의 23개 키가 보강분 섹션에서 그대로 다시 선언돼 앞쪽 값이 파이썬 딕셔너리 특성상 절대 안 읽히는 죽은 코드였음을 발견(차이는 대부분 0~45m, 최대 472m — 실사고 없음) — 앞뒤 값이 여러 쌍 완전히 동일해 텍스트만으로 안전하게 첫 번째만 골라 지울 수 없어 이번엔 제거 대신 그 사실을 주석으로 명시만 함(다음 기회로 미룸). jitter() 는 2만개 case_id 표본으로 실제 haversine 거리가 meters 안에 드는지, 결정성·lat=None 처리·서로 다른 위도(서울·부산) 교차검증까지 실측, _word_in()/resolve() 는 핵심 재현(서구청라동)과 회귀 없음(동해대로의 동해, 강동원의 강동은 여전히 안 잡힘 — 라운드120 보호 유지) 양쪽 실측, 기존 회귀(test_geo.py 15/15·round120/235/264 전부 재실행 통과)로 회귀 없음 재확인, 2개 지점 각각 되돌려 실패 재현 후 복원 — geo.py 는 app.py 가 import 하므로 재기동 필요, BUILD_HASH 는 불변(static/templates 아님))"),
    ("test_scan_round294_fixes.py", "스캔 294라운드 회귀(addr_search.py·build_pages.py 미조사 함수 결함 3건, addr_search.py 는 266라운드가 search()/_official()/_open_map() 만 다루고 나머지 6개(_key·provider·_get·_sigungu·_building_of·demo), build_pages.py 는 230라운드가 strip_jinja() 만 다루고 나머지 5개(_read·_write·drop_unfilled_rows·fix_links·build)는 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — _key·provider·_sigungu·_building_of·demo, _read·_write·fix_links·build 자체 로직은 실측 결과 전부 클린. (a) addr_search.py search() 의 except 튜플에 http.client.HTTPException 이 빠져 있었다. 이 파일이 키 없이 쓰는 무인증 엔드포인트(_open_map, 이 파일 자신의 docstring이 언제든 바뀔 수 있다고 이미 경고하는 그 API)가 Content-Length 보다 적게 보내고 연결을 끊으면 _get() 의 r.read() 가 IncompleteRead 를 내는데 이건 HTTPException 의 하위클래스라 OSError 계열이 아니어서 기존 except 어디에도 안 걸려 실패하면 빈 목록이라는 이 함수 자신의 계약을 깨고 그대로 새 나갔다(실측: 가짜 TCP 서버로 재현 — Content-Length 100 인데 10바이트만 보내고 끊음, MRO 로 OSError/URLError 어느 쪽도 아님을 확인). geocode_fill.py 의 배치 루프는 267라운드가 DB UPDATE/commit 실패만 감쌌지 검색 호출 자체는 안 감싸서 이 예외가 새면 남은 행 전부(최대 --limit, 기본 500건)가 통째로 죽었을 것이다. (b) build_pages.py drop_unfilled_rows() 가 페이지 전체에서 (미기재)가 들어간 tr 을 닥치는 대로 지웠다 — 이 함수 자신의 문서화된 목적은 처리방침 제6조(위탁) 표의 미확정 수탁자 행만 빼는 것인데 같은 _ph() 표시 방식이 제12조 개인정보 보호책임자·연락처 행과 사업자정보 표의 통신판매업 신고번호·대표전화·개인정보 보호책임자 행에도 똑같이 쓰인다. 그 값이 하나라도 비면 자리표시자만 지워지는 게 아니라 행 전체(제목 칸까지)가 통째로 사라져 전자상거래법 §10·개인정보 보호법 §30 표시의무 항목이 표시 안 됨이 아니라 애초에 없던 것처럼 보였다(실측: company_info.json 에서 dpo·mail_order_no 를 비우고 실제로 빌드해 재현 — 두 표에서 행이 사라짐, 현재 운영값은 전부 채워져 있어 지금 당장 발현 중은 아님). 제6조 절 범위로 정확히 좁혔다. (c) 회사 정보 N/8 반영 로그가 len(info)(JSON 키 개수)를 세어 키는 있지만 값이 비었거나 공백뿐이면 그대로 채워진 것으로 셌다 — 미확정 수탁자 N행 제외 경고와 8/8 반영이 같은 실행에서 동시에 찍힐 수 있었다. _ph() 와 같은 기준으로 세도록 수정. IncompleteRead 는 로컬 가짜 TCP 서버(외부 네트워크 없음)로 실제 재현(_get() 은 여전히 raise, search() 는 이제 삼켜서 빈 목록 반환), drop_unfilled_rows() 는 실제 문서 구조를 흉내낸 합성 HTML로 제6조 표는 여전히 정리되고 제12조 표는 더 이상 안 건드려짐을 검증(제6조 절 자체가 없는 문서는 완전히 그대로 반환됨도 확인), 3개 지점 각각 되돌려 실패 재현 후 복원 — addr_search.py 는 app.py 가 import(40행)하므로 재기동 필요, build_pages.py 는 app.py 미import, BUILD_HASH 는 둘 다 무관(static/templates 아님))"),
    ("test_scan_round295_fixes.py", "스캔 295라운드 회귀(미조사 템플릿 7종 결함 3건, change_password.html·track_expired.html·dispatch_report.html·billing_guide.html·login.html·partner_login.html·insurer_login.html 을 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — billing_guide.html·3개 로그인화면은 실측 결과 전부 클린. (a)[심각] track_expired.html 이 사실상 도달 불가능했다. 진행조회 링크 유효기간(TRACK_LINK_DAYS, 기본180일)보다 짧은 개인정보 보유기간(BOKGUON_VICTIM_KEEP_DAYS, 기본90일)에 취소·미수선종결·유찰로 끝난 사건의 cases.track_token 이 NULL 로 지워지는데 track_page() 는 WHERE track_token=? 로만 그 행을 찾아 토큰이 지워진 순간부터 그 행 자체를 다시 못 찾았다 — 링크가 만료됐습니다(410)를 보여줘야 할 자리에 페이지를 찾을 수 없습니다(404)가 영원히 나갔다(실측: 실제로 manage.py prune-personal 을 돌려 재현). 원문 토큰은 개인정보 파기 대상이 맞지만 이 토큰이 예전에 발급된 적이 있는가는 프라이버시 정책을 안 늘려도 답할 수 있어야 한다 — 되돌릴 수 없는 일방향 해시(cases.track_token_hash)를 새로 두어 발급 시 함께 채우고(파기 때는 원문만 지우고 해시는 남긴다) track_page() 가 이 해시로 찾은 뒤 원문이 이미 없으면 무조건 410 으로 판정하게 했다. 개인정보 보유기간 자체는 손대지 않았다 — 순수 아키텍처 수정이지 보유기간 정책 변경이 아니다. (b) dispatch_report.html(보험사에 넘기는 현장 출동 보고서)의 산출 근거 칸이 field_agreements.engine_basis(estimate() 의 JSON 스냅샷 원문)를 그대로 찍었다 — 형제 두 곳(api_insurer_field_agreement·합의이력)은 전부 json.loads() 로 먼저 푸는데 이 보고서만 원문 그대로 내보내 보험사에게 영어 필드명 섞인 JSON 문자열이 그대로 노출됐다(실측: 실제 Flask 라우트로 재현). 형제와 같은 파싱을 거쳐 수선 유형·직접공사비·할증·품명별 표·면책조항으로 구조화. (c) /change-password·/api/change-password 가 require_partner/require_insurer 와 달리 _account_alive() 를 안 불러 퇴출·정지된 협력사·보험사 계정도 자기 비밀번호를 바꿀 수 있었다(실측: status=퇴출 협력사로 실제 비밀번호 변경 성공 확인). 다른 보호 라우트와 같은 기준으로 맞췄다. track_expired.html 은 실제 DB+manage.py prune-personal+Flask 라우트로 파기 후 410 전환·자연만료 회귀없음·미발급토큰 404 유지·정상토큰 200 유지까지 4중 실측, dispatch_report.html 은 실제 라우트로 JSON원문 소멸+구조화표시 실측, change-password 는 퇴출계정 차단+정상계정 회귀없음 실측, 5개 지점 각각 되돌려 실패 재현 후 복원 — 스키마 변경(track_token_hash 컬럼+백필) 수반으로 app.py/db.py/templates 전부 재기동 필요·BUILD_HASH 로테이션 예상. 부수적으로 기존 회귀 2건(round260·round64) 이 track_token 원문으로 직접 INSERT 하던 방식이 새 해시조회와 안 맞아 깨진 것을 발견해 함께 수정(각각 track_token_hash 도 같이 채우도록, round260 은 소스텍스트 검사 문구도 갱신) — round142 는 상태코드를 !=200 으로만 확인해 회귀 없이 그대로 통과함을 확인)"),
    ("test_scan_round296_fixes.py", "스캔 296라운드 회귀(deploy/windows_setup.ps1 예약작업 3개 python.exe 콘솔깜빡임 결함 1건, deploy/ 아래 마지막 미조사 스크립트 2개(windows_setup.ps1·고정도메인_설정.ps1)를 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 고정도메인_설정.ps1은 실측 결과 클린(아직 아무도 안 쓴 휴면 스크립트, .cloudflared 디렉터리가 비어있고 .env에 고정도메인이 없어 이 PC엔 해당 안 됨을 직접 확인). windows_setup.ps1은 이 PC를 만든 스크립트가 아니다 — 이 스크립트 자신의 산출물(venv·bokguon 서비스·4개 예약작업 이름)이 이 PC엔 하나도 없음을 실측(Test-Path·Get-Service·schtasks 전부 없음)으로 확인했다. 그런데도 7단계(예약작업 등록)의 백업·접속기록정리·개인정보파기 3곳이 전부 $vpy(=venv의 python.exe)를 -Execute 에 직접 썼다 — 예약작업을 python.exe로 등록하면 실행마다 콘솔 창이 떴다 사라지는 결함으로, 라운드292가 복구온_예약실행_등록.ps1에서 이미 고친 것과 완전히 같은 결함 클래스다(실측 재확인: schtasks /Query /TN 복구온_경매마감 /XML — 실제 이 PC의 그 작업은 이미 pythonw.exe로 등록돼 있다). 조사 에이전트는 이 3개가 실제 운영 중인 복구온_일일백업(deploy/일일백업.bat 하나로 백업+파기 3종을 로그+자가점검까지 갖춰 통합한 것, schtasks로 직접 확인)과 겹쳐 재실행 시 중복 등록된다는 점도 짚었으나, bootstrap.sh(리눅스판)를 대조해보니 정확히 같은 3분리 구조로 cron을 등록하고 있어(실측: grep) 3분리 자체는 두 플랫폼이 맞춘 의도된 설계임을 확인 — 구조는 그대로 두고 확실한 결함(python.exe 콘솔깜빡임)만 고쳤다. 복구온_예약실행_등록.ps1과 같은 폴백 변수($vpyw, pythonw.exe 없으면 python.exe로 폴백)를 새로 두어 예약작업 3곳의 -Execute에만 쓰고, NSSM 서비스 등록(세션0이라 콘솔 자체가 없음)과 대화형 설치 단계(사람이 출력을 봐야 함)는 $vpy 그대로 둠. PowerShell 파서(Parser.ParseFile)로 전체 파일 구문 검증, $vpyw 폴백 로직 자체를 실제 임시 파일시스템(pythonw.exe 있는 경우·없는 경우 양쪽)에 대해 진짜로 실행해 검증(테스트 스크립트 자신이 BOM 없는 .ps1을 cp949로 잘못 읽는 문제와 임시 디렉터리 이름에 pythonw 라는 부분열이 섞여 자기 검증을 속일 뻔한 문제 2건을 실측으로 잡아 고친 뒤 재검증), 사진백업(cmd.exe)·NSSM·대화형 단계는 안 바뀌었음을 소스로 확인, $vpyw 정의와 3곳 치환 전체를 되돌려 실패 재현 후 복원 — windows_setup.ps1은 app.py가 import하지 않는 독립 배포 스크립트라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round297_fixes.py", "스캔 297라운드 회귀(표준단가 시드도구 sku_key 미백필 결함 1건[심각]+이력소음 2건, seed_boq.py·seed_boq_led.py를 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 재실행 안전성(멱등성)·active/is_demo 플래그·price_src/price_date 출처컬럼·공종별 값 타당성은 실측 결과 전부 클린. (a)[심각] standard_boq.sku_key(견적엔진이 DB 단가를 읽는 유일한 통로, app.py _load_price_book()이 이 값 있는 행만 내림)를 채우는 유일한 함수(db._backfill_sku_keys())가 db.migrate() 안에서만 불리는데, seed_boq.py의 유일한 적재함수 load()는 이 함수를 한 번도 안 불렀다 — 운영자가 이 CLI로 실측단가를 적재해도(성공 메시지가 뜨고 관리자 콘솔엔 활성으로 보여도) 서버 재기동이나 manage.py migrate 전까지 견적엔진은 그 값을 전혀 못 읽고 계속 내장 하드코딩 값으로 계산한다 — 화면 어디에도 이 괴리가 안 보인다(실측: 격리 스크래치 DB에서 재기동 없이 확인 — 45행 적재 직후 전부 sku_key NULL, '가드레일 판(2W)' 등 엔진 내장값과 이름·가격이 완전히 같은 항목도 _load_price_book()과 동일 조건 조회에서 안 잡힘). _backfill_sku_keys()는 NULL인 행만 채우고 스스로 커밋하는 멱등 함수라 load()의 진짜 커밋 직후에 그대로 재사용해 고쳤다(dry-run 오염 방지를 위해 반드시 커밋 뒤에 두어야 함을 순서까지 검사). seed_boq_led.py는 이 load()를 그대로 호출하므로 별도 수정 없이 함께 고쳐졌다. (b) load()가 값이 하나도 안 바뀐 재실행에도 매번 '수정'(old==new) 이력을 boq_price_history에 남겨, 이력의 존재 이유(개정 소명 자료)를 재실행 소음이 덮었다(실측: 무변경 재실행 1회로 '수정' 44건 중복 적재) — 이미 있던 가격변경 판정(print문 조건)을 이력 기록에도 그대로 적용해 실제로 값이 바뀐 경우에만 남기도록 수정. (c) seed_boq_led.py의 2017년 값 사용중지 로직이 active 조건 없이 매번 다시 걸려, 이미 비활성인 행도 재실행마다 새 '비활성' 이력을 쌓고 안 바뀐 재실행에도 'N건 사용중지'가 매번 그대로 찍혔다(실측: 합성 픽스처로 2회 실행 → 이력 2건) — SELECT·UPDATE 양쪽에 COALESCE(active,1)=1을 더해 이미 비활성인 행은 재실행에서 건드리지 않게 함(실측: 같은 픽스처로 재검증 → 이력 정확히 1건, 2차 실행 출력은 '0건'). sku_key 백필은 실제 seed_boq.load() 호출로 격리 DB에서 재기동 없이 즉시 반영을 실측(엔진 SKU와 실제 연결까지 확인), 이력 소음 2건은 각각 실제 load() 2회 재호출(가격불변→이력0건, 가격변경→이력1건)과 seed_boq_led.py 실제 서브프로세스 2회 실행(합성 픽스처, 이력 1건 유지·재실행시 '0건' 출력)으로 실측검증, 3개 지점 각각 되돌려 실패 재현 후 복원 — seed_boq.py·seed_boq_led.py 모두 app.py가 import하지 않는 독립 CLI 도구라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round298_fixes.py", "스캔 298라운드 회귀(photo_ai.py EXIF 방향유실 결함 1건+app.py 외부보험사API 담당자확인 미반영 결함 1건[심각], photo_ai.py를 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 동시성(round71·72 방어 재확인, 모듈 자체엔 공유상태 없어 클린)·AI호출실패 조용한오판·이미지 신뢰경계·데모격리는 실측 결과 전부 클린, 보조조사한 totp.py도 클린. 조사에이전트는 _heic_to_jpeg()도 같은 방향유실 결함이라 보고했으나 독립검증 중 재확인(pillow_heif 1.4.0 실제 등록오프너로 HEIC 라운드트립, orientation 1/3/6/8) 결과 Image.open() 시점에 이미 방향이 픽셀 반영되고 태그가 1로 정규화됨(90/270도는 실제로 가로세로가 바뀌고 180도는 유지 — 회전규칙과 정확히 일치)을 확인해 결함이 아님으로 판정, 에이전트의 재현이 이 지점만 실제 HEIC 디코드 대신 JPEG로 대체한 유사재현이었음을 확인(다른 지점은 전부 실제 재현) — 290라운드의 '보강 인용도 별도 검증' 교훈이 이번엔 '재현 방법 자체'에서 재발한 사례. (a) _strip_exif()가 EXIF Orientation 태그를 픽셀에 반영하지 않고 그냥 지워, 세로로 찍은 사진(폰카메라 대다수)이 화면·검수자·AI판정 전부에게 옆으로 누운 채 영구히 저장됐다(원본 미보관이라 복구 불가, 실측: Orientation=6 JPEG가 재인코딩 후에도 100x60 그대로 나오고 방향 태그만 사라짐). 재인코딩 전에 ImageOps.exif_transpose()로 먼저 픽셀에 반영하도록 수정(JPEG·PNG·WEBP 세 분기 모두 적용, 180도·이미 정상인 경우 과잉교정 없음도 확인). (b)[심각] 외부 보험사 API(/api/v1/cases*)의 _v1_case_view()가 담당자가 콘솔에서 확정한 파손정도(human_severity)를 전혀 반영 안 하고 AI추정치(ai_severity)만 냈다 — 같은 파일의 두 정상판정 함수(_est_basis·_record_outcome)는 이미 담당자 확인값을 우선하는데(사람이 정한 값이 사진판정보다 우선) 외부API 뷰만 이 우선순위가 없었다(실측: 담당자가 '중대'로 확정한 뒤에도 이 뷰는 여전히 옛 '경미'를 반환, POST /api/insurer/cases/<id>/severity는 human_severity만 갱신함을 확인). 세 곳이 각자 판단하다 하나가 빠지는 사고(round54·59·93·131·297과 같은 족보)를 반복하지 않도록 판정로직을 _case_severity() 공유함수로 뽑아 세 곳 모두 통일(리팩터링이라 est_basis·record_outcome은 회귀없음 확인), 기존 ai_severity·ai_report 필드는 값과 뜻을 그대로 두고(문서화 안 된 필드라 기존 연동 영향 불명 — insurer_api_guide.html에도 미기재 확인) human_severity·severity·severity_src 세 필드만 새로 추가. _strip_exif는 실제 PIL 이미지(Orientation 1·3·6·8)로 회전 여부 실측, _v1_case_view는 격리 DB+실제 함수호출로 담당자확인 전후 외부API 응답 변화를 실측(ai_severity 불변+human_severity·severity 신규반영), 2개 지점 각각 되돌려 실패 재현 후 복원 — photo_ai.py·app.py 둘 다 app.py가 스스로 포함되므로 재기동 필요, BUILD_HASH 로테이션 예상)"),
    ("test_scan_round299_fixes.py", "스캔 299라운드 회귀(collect_emails.py·clean_collected_emails.py 짝도구 결함 4건[일부 심각], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 재실행 자체 멱등성·데모격리(partners엔 is_demo 자체가 없음)·입력 신뢰경계(부실URL·DNS실패가 배치 전체를 안 죽임)는 실측 결과 전부 클린. (a)[심각] partners.email 을 바꾸는 실사용 경로 4곳(마이페이지 본인수정·연락처 수정·엑셀 일괄등록·업체 정보수정 — 조사에이전트는 앞 두 곳만 짚었으나 독립검증 중 grep 전수확인으로 나머지 두 곳도 추가 발견) 전부 email_source 를 안 건드렸다 — 담당자·업체 스스로 수집된 주소를 실제 검증된 주소로 고쳐도 email_source 는 '수집(홈페이지)'로 영원히 남아 clean_collected_emails.py 가 이 표식 하나만 보고 사람이 방금 고친 정상 주소를 삭제했다(실측: PATCH 직후 그 값이 삭제조건에 그대로 걸림). db.py 스키마 주석이 이미 문서화한 '직접입력' 값으로 네 경로 모두 email 변경시 함께 갱신하도록 수정. (b)[심각] clean_collected_emails.is_junk()·collect_emails.pick_emails() 가 공유하는 BAD_LOCAL 판정이 `in`(부분열 포함) 검사였다 — local part 가 흔한 실제 단어(latest·contest 등)이기만 해도 그 안에 test 가 부분열로 들어있어 사람이 검증한 정상 주소까지 사람 주소 아님으로 오판해 삭제했다(실측: is_junk('latest@…')가 실제 삭제 판정을 냄). 구두점으로 구분된 독립 조각일 때만 맞다고 보는 공유 헬퍼(_bad_local_word_in)로 두 파일 통일. (c)[심각] collect_emails.py 가 이메일을 채울 때마다 email_consent 를 무조건 0으로 덮어써, 신청승인 때(마케팅 수신동의, 이메일란은 비워둠) 이미 email_consent=1 을 받아둔 행이 이 도구에 한 번 걸리면 진짜 동의가 조용히 영구히 사라지고 앱 어디에도 되돌릴 화면이 없었다 — 이미 1이면 보존하고 그 밖만 0으로 명시하도록 수정. (d) 관리자 대시보드 집계(api_contact_summary)의 '수집' 카운트가 표식만 세어 clean_collected_emails.py 가 방금 지운(email='') 행도 계속 집계에 남았다(실측: 정리 직후에도 숫자가 안 줄어듦) — 실제 이메일 존재 조건 추가. _bad_local_word_in 은 실제 문자열(latest·contest·test·no-reply 등)로 오탐소멸+정탐유지 양쪽 실측, email_source 4곳은 실제 Flask 라우트(연락처수정·엑셀업로드·업체정보수정·본인마이페이지)로 갱신 확인+clean_collected_emails.py 삭제조건 이탈까지 실측, 대시보드 집계는 실제 삭제 전후 API 응답 변화 실측, 동의보존은 로컬 가짜 HTTP서버+실제 collect_emails.py 서브프로세스 실행으로 실측, 7개 지점 각각 되돌려 실패 재현 후 복원 — app.py 변경 포함으로 재기동 필요, BUILD_HASH 로테이션 예상. collect_emails.py·clean_collected_emails.py 자체는 app.py 미import(독립 CLI)라 재기동과 무관)"),
    ("test_scan_round300_fixes.py", "스캔 300라운드 회귀(ingest_partners.py·partner_accounts.py 결함 3건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(스스로 첫 가설을 실측으로 뒤집고 두 전제 — ingest_partners.py는 자동배포에 안 물려있음·WORK_MAJORS는 major의 진짜 enum이 아님 — 도 함께 바로잡음) — 동시성(기존 test_scan_round270_fixes.py가 이미 실측검증)·아이디 유일성 백스톱(UNIQUE 제약)·major enum 정확성·status/partner_type 초기값·is_demo 격리(partners엔 그 컬럼 자체가 없음)·평문 비밀번호 로그유출은 실측 결과 전부 클린. (a) norm_name()이 전각 괄호(（）U+FF08/09)를 반각(())과 다르게 취급해 '(주)한빛건설'과 '（주）한빛건설'이 서로 다른 중복판정 키가 됨 — 다음 리서치 배치에서 이미 있는 회사가 다시 들어갈 수 있었다(실측: 현재 398개사엔 전각 괄호가 없어 아직 미발현, 미래 배치 겨냥 결함). 전각→반각 변환 선행 후 정규화하도록 수정, 실제 398개사 데이터로 새 충돌 0건 확인. (b) partners_seed.json을 임시파일 경유 없이 직접 덮어써, 쓰는 도중 끊기면(디스크 꽉 참·Ctrl+C) 파일이 잘린 채 남고 db.py 시드로더가 json.load() 실패를 조용히 빈 목록으로 삼켜(실측: 잘린 파일로 새 DB 생성 시 협력사 0곳으로 조용히 끝남) 다음 신규배포가 경고 없이 협력사 전체 없이 뜰 수 있었다 — 임시파일+os.replace()로 원자적 교체하도록 수정(실패시 임시파일 정리까지). (c) partner_accounts.py의 CSV저장·감사로그(DB.log)가 배치가 끝까지 돈 뒤에만 한번 실행돼, 각 업체 UPDATE는 SAVEPOINT(바깥 BEGIN 없어 RELEASE 즉시 개별커밋, SQLite 특성)로 이미 개별 확정되는데도 배치 중간에 죽으면(운영자 Ctrl+C — 이 파일 자신의 '안전 원칙'이 실제 발생 행동으로 이미 인정) 앞쪽 업체들은 DB엔 로그인계정이 실제로 생겼는데 그 임시비밀번호가 화면·CSV·감사로그 어디에도 안 남아(비밀번호는 해시라 복구불가) 로그인 영원히 불가능한 죽은 계정이 됨(실측: 3번째에서 강제로 죽이면 앞 2곳이 정확히 이 상태로 남음) — CSV·감사로그를 업체 처리 직후(UPDATE와 같은 자리)로 옮겨 시점을 맞춤. norm_name은 실제 함수호출+실제 398개사 데이터 재검증, 원자적쓰기는 json.dump를 실제로 중간에 실패시켜 원본파일 무손상 실측, partner_accounts.py는 실제 서브프로세스로 3번째 업체에서 강제중단시켜 앞 2곳의 DB상태·CSV·감사로그 일치 실측, 3개 지점 각각 되돌려 실패 재현 후 복원(회귀테스트 자신의 .index() 예외로 죽는 취약점도 round297과 같은 방식으로 자체 발견해 수정) — ingest_partners.py·partner_accounts.py 둘 다 app.py가 import하지 않는 독립 CLI라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round301_fixes.py", "스캔 301라운드 회귀(notify_popbill.py SMS/LMS 바이트 계산 결함 1건[심각], notify_popbill.py·popbill_check.py를 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 재시도/포기 판정(번호없음 즉시실패·일시실패 3회 CAS재시도+RequestNum멱등키)·자격증명 미설정시 조용한무발송 아닌 명확한 (False,사유) 반환·popbill_check.py가 진짜 읽기전용 API호출임(문자열존재만 보는 게 아님)·데모사건(is_demo=1) 실발송 격리는 실측 결과 전부 클린(기존 test_notify_popbill.py 32/32 재확인 포함, 그 테스트는 '한' 한 글자만 써서 이번 결함을 원천적으로 못 잡는 구조였음도 확인). 부수관찰(POPBILL_TEST 단독변경 시 키교체 재시작경고 문구가 실제 SDK 특성보다 약간 과장 — envload가 프로세스당 1회만 실행돼 실사용경로에서 재현 불가로 수정보류)도 있었으나 확인 결과 실제 위험 없어 그대로 둠. [심각] _euckr_len()·_euckr_cut() 이 이름과 달리 진짜 EUC-KR 코덱으로 재, 1987년 KS X 1001 완성형 2,350자 밖의 한글(예: 뷁)을 2바이트가 아니라 8바이트로 측정했다(실측: 현대 한글 11,172자 중 8,822자·79%가 이 함정에 걸림, 팝빌 공식문서의 실제 과금규칙은 예외없는 2바이트). 흔치 않은 음절이 든 메시지가 실제론 SMS 로 충분한데 LMS 로 잘못 과금되거나(90바이트 문턱 오판), LMS 조차 진짜 2,000바이트 한도보다 훨씬 일찍 잘려 뒷부분이 조용히 사라졌다(실측: 뷁×1000자를 2000바이트로 자르면 250자만 남음 — 실제 한도면 1000자 전부 들어감). cp949(완성형의 상위호환, 현대 한글 11,172자 전부를 예외없이 2바이트로 잼)로 교체. 현대 한글 11,172자 전수를 실제 함수로 재확인(고치기 전 8,822자 어긋남→고친 뒤 0건), 잘림 함수가 실제 한도만큼 온전히 통과시킴을 실측, 기존 검증과 같은 FakeMsg 서비스 주입 패턴으로 실제 send() 호출이 흔치 않은 음절 45자(진짜 90바이트)에서 이제 정확히 SMS 로 가고 46자(92바이트)에서는 여전히 LMS 로 가는 회귀없음까지 실측, 1개 지점(두 함수) 되돌려 실패 재현 후 복원 — notify_popbill.py 는 app.py 33행이 import하므로 재기동 필요, BUILD_HASH 는 무관(static/templates 아님) 불변 예상)"),
    ("test_scan_round302_fixes.py", "스캔 302라운드 회귀(geocode_fill.py 주소→좌표 일괄배치 결함 3건[일부 심각], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — round267의 DB저장실패 방어(재확인, 여전히 존재)·round294의 addr_search.py IncompleteRead 수정(재확인, 여전히 존재)·데모격리(cases는 is_demo=0 필터 확인, partners는 그 컬럼 자체가 없음)는 클린. 부수관찰(geo_src='주소검색'이 자동일괄추정과 사람확인선택 두 신뢰수준을 한 값으로 묶음·요청간격 0.35초)은 스키마·정책판단 필요해 범위밖으로 남김. (a)[심각] fill()의 검색 두 번(ADDR.search(q)·ADDR.search(q2))이 아무 보호도 없었다 — round267이 고친 건 DB저장 실패뿐, addr_search.search()의 '실패하면 빈 목록' 계약이 유일한 방어선인데 그 계약은 이미 한 번 깨진 적 있다(round294 IncompleteRead — 지금은 고쳐졌지만 하위계층이 다시 회귀 안 한다는 가정에만 기대면 안 됨). 한 행의 검색실패가 나머지 행 전부(최대 --limit 500)를 조용히 죽였다(실측: 3건 중 2번째 강제실패시 3번째로 정상 지오코딩됐을 업체가 시도조차 못 받고 배치 자체가 죽음) — 검색 두 번을 감싸 이 행만 건너뛰게 수정. (b)[심각] _region_ok()로 동네판정할 때 실제로 결과를 찾은 검색문(정제된 q2)이 아니라 항상 원문주소(q)로 판정했다 — '본사: 서울 강남구… / 공장: 경기 김포시…'처럼 원문에 여러 주소가 섞이면 검색에 안 쓰인 뒤쪽 주소가 우연히 검색결과 동네와 겹쳐 완전히 다른 도시 좌표를 동네일치로 잘못 승인했다(실측: 같은 입력을 원문기준/실제검색문기준 나란히 판정 — 원문기준은 통과, 실제기준은 정확히 거름). 이 좌표는 geo_src='주소검색'(신뢰표식)으로 저장돼 배차화면의 정확한거리 판정에 바로 들어감 — 실제로 좌표를 찾아낸 문자열 기준으로 판정하도록 수정. (c) 지오코딩 실패행(못찾음·한반도밖·동네불일치)이 표식이 없어 '아직 안 해봄'과 구별 안 됨 — cases는 계속 누적되는 표라 반복실행될 수 있는데, 영구 실패주소가 --limit 이상 쌓이면 매 실행이 그 오래된 실패건만 다시 뽑아 새 사건은 시도조차 못 받음(실측: 같은 5건 두 번 실행해도 매번 같은 3건만 뽑히고 6번째 정상업체는 두 번 다 시도 안 됨) — 새 표식('시도실패')을 geo_src에 남기고 대상조회에서 제외(사람이 지우면 재대상 가능, 영구봉인 아님). 검색실패는 실제 fill() 호출로 중간행 강제실패시켜도 나머지 정상행이 전부 채워짐을 실측, 동네판정기준은 에이전트 재현과 동일 시나리오(다중주소+무관지명)로 실제 fill() 호출+두 판정기준 나란히 대조 실측, 재시도표식은 동일배치 2회 실행으로 기아현상 해소를 실측, 3개 지점 각각 되돌려 실패 재현 후 복원(회귀테스트 자신이 결함상태의 예외전파를 그대로 맞아 죽는 문제도 round297·300과 같은 방식으로 자체발견 수정) — geocode_fill.py는 app.py가 import하지 않는 독립 CLI라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round303_fixes.py", "스캔 303라운드 회귀(smoke_test.py 배포전 품질게이트 결함 3건[대부분 심각], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 독립검증 중 조사보고서의 네 번째 지적(쓰기모드 사건이 is_demo 없이 남는다)은 manage.py DEMO_CASE_SQL(is_demo=1 OR insurer_id가 데모 발주처)이 go-live 시 이미 자동정리하고 mark-smoke-demo 명령도 이미 존재·연결돼 있어 실제로는 이미 완화돼 있음을 확인(코드는 안 고치고 deploy/DEPLOY.md 에 두 안전장치 안내만 추가). (a)[심각] 관리자 IP 화이트리스트를 켰을 때 협력사·보험사 경로가 함께 막히지 않는지 보는 유일한 검사 test_admin_ip_gate() 가 정의만 있고 main() 실행목록(946~956행)에 단 한 번도 없어 PASS·FAIL·SKIP 어디에도 안 남고 통과 N/N 요약에서 조용히 빠졌다 — 그냥 이어붙이면 이 검사 자신이 앱을 프로세스 안으로 직접 import 하는 방식(852행 자신의 docstring)이라 app.py 122행의 DB.init_db() 무조건 실행 때문에 BOKGUON_DB_PATH 가 비어있으면 운영 bokguon.db 를 열 수 있는 두 번째 결함이 열린다(db.py 운영DB가드는 진입스크립트 이름이 test_ 로 시작할 때만 발동해 smoke_test.py 는 통과, 배포스크립트도 이 환경변수를 안 정해줌) — 함수 안에서 비어있을 때만 판정전용 임시DB로 먼저 격리한 뒤 main() 에 추가(test_bruteforce 바로 앞 — 반드시 마지막이어야 한다는 자신의 docstring 유지). (b)[심각] test_photos() 의 타보험사 사진접근차단(IDOR) 검사 — insurer2 로그인 실패시 형제 셋(협력사·보험사·관리자)과 달리 skip()+DEMO_LOGIN_GONE 기록이 없어 아무 흔적도 없이 사라진다는 지적을 독립검증하다 더 깊은 원인을 찾음 — manage.py DEMO_ACCOUNTS(1632행 부근)는 이미 insurer·insurer2 둘 다 go-live 가 지울 이름으로 예약해 뒀고 smoke_test.py 도 처음부터 insurer2 로 로그인을 시도하는데, db.py seed() 의 보험사 시드 두 번째 행(△△화재)이 login_id/password 둘 다 None 인 빈자리로 남아 있어 이 계정이 한 번도 존재한 적이 없었다 — go-live 이후뿐 아니라 표준 리허설에서도 이 IDOR 검사가 매번 조용히 비어 있었다는 뜻. △△화재에 login_id=insurer2·비밀번호 bokguon2026(insurer 와 동일 — smoke_test.py 가 이미 그렇게 시도 중이었다)을 채워 검사가 실제로 도는 근본원인을 고치고, 계정이 없는 상황(go-live 이후 등)을 위한 형제와 같은 기본 처리도 추가. main() 호출누락은 실제 main() 을 노이즈없는함수(9개)로 스텁교체후 실행해 test_admin_ip_gate 호출횟수를 실측(0→1), DB격리는 importlib.import_module 자체를 가로채 app 을 실제로는 절대 안 불러오면서 호출 직전 BOKGUON_DB_PATH 값을 포착(비어있던경우 운영경로 아닌 임시경로로 채워짐·호출자가 이미 정했으면 그대로 존중 양쪽 실측), insurer2 시드는 실제 격리DB에 seed() 를 돌려 login_id·비밀번호 해시일치까지 실측, IDOR 검사는 smoke_test.py 자신의 Client.req()/multipart() 를 몽키패치(285라운드 검증된 방식)해 실제 test_photos() 함수를 로그인성공/실패 두 시나리오로 실행 — 성공시 실제로 통과기록·실패시 SKIP+DEMO_LOGIN_GONE 기록 양쪽 실측. 4개 지점(main 호출·DB격리·insurer2 시드·else분기) 각각 되돌려 실패 재현 후 복원(회귀테스트 자신의 .index() 예외로 죽는 취약점도 297·300·302 와 같은 방식으로 자체발견 수정) — smoke_test.py 는 app.py 가 import 하지 않는 독립 도구, db.py 변경은 시드 데이터값뿐(스키마 아님)이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round305_fixes.py", "스캔 305라운드 회귀(envload.py 모든 진입점 공유 .env 로더 결함 3건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — envload.py 자신의 override 우선순위(이미 정해진 process 환경변수가 .env 보다 우선)는 두 경로 모두 실측 결과 클린, db.py 의 is_prod/seed_demo 판정은 함수 안에서 그때그때 읽어 이번 결함에 안 걸림, gunicorn_conf.py 는 이미 287라운드가 정밀조사했고 이번 각도(윈도/리눅스 바인딩·방화벽 정합성, X-Forwarded-For 신뢰범위, 로그와 prune-logs 무관함, graceful reload 구조차이)도 전부 클린 재확인. (a)[심각] envload.py 의 살아있는 경로(python-dotenv 설치돼 있으면 항상 이 분기, requirements.txt 고정설치 확인)가 dotenv.load_dotenv() 를 encoding 인자 없이 불러 파이썬 기본값 utf-8 이 BOM 을 안 벗겼다 — Windows 메모장·PowerShell 이 만든 .env(DEPLOY.md 가 이미 경고)의 첫 줄 키가 그대로 다른 이름이 되어 os.environ 에 원래 이름으로는 전혀 안 잡힌다(예외도 경고도 없음). 바로 아래 대체 파서는 이미 encoding=utf-8-sig 로 이 문제를 정확히 막아 뒀는데 python-dotenv 가 있는 한 죽은 코드라 실제로는 아무도 안 막고 있었다 — dotenv.load_dotenv() 에도 같은 encoding 을 넘겨 두 경로를 동일하게 방어. (b) manage.py 의 cmd_check() 가 자기만의 .env 재파싱(utf-8-sig 로 BOM 을 막아 (a)보다 오히려 더 견고)을 따로 갖고 있어, 서버가 실제로 쓰는 envload.load_dotenv() 가 (a) 결함으로 어떤 키를 놓쳐도 이 재파싱이 os.environ.setdefault() 로 조용히 그 키를 되살려 냈다 — manage.py check 는 배포 가능 이라는데 실제 서버는 dev 모드로 뜨는 자기도구 거짓 초록(272라운드가 popbill_check.py 에서 이미 고친 것과 같은 유형 — 서버가 실제로 쓰는 로더에 위임하지 않고 자체 파서를 둠). manage.py 의 envload.load_dotenv() 가 이미 이 명령 실행 전에 끝나 있으므로 중복 재파싱 블록을 제거. (c)[심각] app.py 가 db·photo_ai 등 로컬 모듈 11개를 import 한 뒤에 .env 를 로드했다(주석 자신은 모듈 최상단에서 로드한다고 주장했지만 실제 위치는 그 뒤였다) — photo_ai.py 는 GEMINI_KEY·UPLOAD_ROOT·MAX_FILES_PER_CASE 등을 함수 안이 아니라 모듈 최상단에서 즉시 os.environ.get() 으로 읽어 전역변수에 얼려 둔다. wsgi.py·serve_waitress.py 경유는 그쪽이 자신의 import 보다 먼저 이미 한 번 로드해 둬서 우연히 안전했을 뿐 — python app.py 로 직접 띄우는 경로(복구온_서버실행.bat 이 실제로 이 경로, app.py 자신의 docstring 도 이 실행법을 문서화)에서만 노출된다. .env 로드를 다른 모든 import 보다 앞(import os 바로 다음)으로 옮겨 실제로 모듈 최상단이 되도록 수정. 진짜 python-dotenv·진짜 photo_ai.py·진짜 app.py 로 실측(BOM 붙은 격리 .env 로 (a) 검증, 서브프로세스 3개로 import 순서 재현해 (c) 의 메커니즘+실제 app.py 파일 자체가 고쳐진 순서로 정확히 동작함을 검증), 3개 지점 각각 되돌려 실패 재현 후 복원 — app.py 변경 포함으로 재기동 필요, BUILD_HASH 로테이션 예상)"),
    ("test_scan_round306_fixes.py", "스캔 306라운드 회귀(build_pages.py GitHub Pages 정적 소개사이트 빌더 결함 2건 + dev_tls_proxy.py 문서보강, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 조사 프롬프트 자신의 한번도 조사 안됨 전제는 틀렸다고 Agent 스스로 정정(108·230·294라운드가 이미 build_pages.py를, 275라운드가 dev_tls_proxy.py를 감사했었고 그 수정들은 전부 지금도 살아있음을 재확인) — 이번 결함들은 그 라운드들이 못 보던 새 각도. (a)[심각] 체크인된 docs/(GitHub Pages 산출물)가 이미 legal_docs.py(진짜 원본)와 어긋나 있었다 — 289라운드가 하자담보책임기간(24개월) 고정문구를 사건별로 정해지며 기본 24개월로 고쳤는데(그 라운드 자신의 테스트가 살아있는 서버는 이미 고쳐진 문구를 낸다고 확인함), build_pages.py는 소스 변경마다 사람이 손으로 다시 실행해야 하는 완전 수동 도구(deploy/외부공개_안내.md가 유일한 문서화된 절차, GitHub Actions 등 자동 재빌드 없음)라 아무도 다시 안 돌려 체크인된 docs/legal/privacy.html·terms.html이 계속 옛 고정문구를 내보내고 있었다(실측: 실제 docs/를 새로 빌드한 결과와 diff — 두 파일만 정확히 다르고 나머지 23개는 이미 일치). 도구 자체는 이미 정확했으므로 python build_pages.py를 실제로 다시 돌려 docs/를 최신 소스와 일치시키고, 체크인된 docs/가 항상 방금 빌드한 결과와 같아야 한다를 회귀 불변식으로 못박았다. (b) build_pages.py가 이미 legal_docs를 import해 두고도(LEGAL.DOCS·LEGAL.privacy_body()를 이미 씀) 정작 요약 출력 한 줄만을 위해 company_info.json을 독립적으로 다시 읽었다 — 이 자리만 무방비라 set-info를 한번도 안 한 정상 상태(파일 없음)에서 돌리면 docs/는 이미 전부 성공적으로 써진 뒤인데도 이 마지막 줄에서 FileNotFoundError로 죽어 exit 1이 됐다(그 파일에 대한 방어는 121라운드가 이미 legal_docs._load_info()에 세워 뒀는데 이 자리만 안 씀) — 다시 읽지 않고 이미 로드된 LEGAL.INFO를 재사용하도록 수정, 안 쓰게 된 import json도 제거. dev_tls_proxy.py는 코드 변경 없음 — X-Forwarded-For가 이 로컬 리허설 프록시(TCP 바이트 중계라 HTTP를 아예 해석 안 함, 실측 확인)를 거치면 검증 없이 그대로 통과한다는 한계를 docstring에 명시만 추가(회귀 대상 아님). 실제 legal_docs._load_info()로 사전조건 재확인, 진짜 샌드박스(company_info.json 없음)에 실제 subprocess로 build_pages.py를 실행해 exit 0 확인, 체크인된 docs/ 전체(25개 파일)를 실제로 새로 빌드한 결과와 filecmp로 전수 대조해 완전 일치 확인 + 안전한 사본에 예전 문구를 되돌려 그 대조가 실제로 드리프트를 잡아냄을 증명, 2개 지점 되돌려 실패 재현 후 복원(복원 과정에서 자체 테스트의 Windows 경로구분자 버그(슬래시 vs 백슬래시)도 직접 발견해 수정) — build_pages.py·dev_tls_proxy.py 둘 다 app.py가 import 하지 않는 독립 도구라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round307_fixes.py", "스캔 307라운드 회귀(test_firstday.py 가 firstday_server.py 의 사본을 손으로 다시 써서 274라운드가 원본에 세운 안전장치 2개(운영DB 오발방지·포트 이중바인딩 방지)를 하나도 못 물려받던 결함[심각], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — Agent 자신이 조사프롬프트의 한번도 조사 안됨 전제를 재확인 과정에서 스스로 검증(run_all_tests.py 전체 등록 상태 268개 전수대조는 완벽히 1대1로 별도 결함 없음, app.py의 확신에 찬 주석 여러 건도 재검증해 전부 클린, admin.js 등 금액서식 형제드리프트도 78라운드 이후 새 사례 없음, scratch_r171_repro.py 는 아무 데서도 안 쓰이는 죽은 파일이라고 확인만 하고 삭제는 범위 밖으로 둠). Windows 의 Werkzeug 개발서버는 같은 host:port 이중 바인딩을 예외 없이 허용한다(274라운드가 이미 netstat 으로 실측) — firstday_server.py(수동 리허설 도구)는 app.run() 전에 포트를 직접 probe 해 이미 점유돼 있으면 SystemExit 하는 가드를 갖고 있는데, test_firstday.py 는 같은 부트스트랩 코드를 문자열로 다시 써서 임시 firstday_server.py 사본을 만들었고 그 사본에는 이 가드도 운영DB 오발방지 가드도 둘 다 없었다. 이전 실행이 비정상 종료해 포트 8790 에 스테일 프로세스가 남아 있으면, 다음 test_firstday.py 실행은 그 사실을 전혀 모른 채 새 프로세스를 또 띄우고 헬스체크 폴링이 어느 쪽이 응답하는지 구분 못해 옛 코드를 대상으로 60단계 전부를 돌리고도 통과를 보고할 수 있었다. 근본 수정으로 사본을 없앴다 — test_firstday.py 가 이제 firstday_server.py 원본을 그대로 서브프로세스로 불러 BOKGUON_DB_PATH·BOKGUON_FIRSTDAY_PORT 두 값만 환경변수로 오버라이드한다(firstday_server.py 쪽은 이 두 값을 os.environ.setdefault() 로 받도록 수정 — 호출자가 이미 정했으면 존중, 손으로 직접 실행할 때는 기존 기본값 그대로). 이제 원본이 앞으로 더 강화돼도 이 테스트가 자동으로 그 보호를 물려받는다. 실제 firstday_server.py 를 격리 임시포트·임시DB 로 진짜 서브프로세스 실행해 포트충돌 가드가 실제로 작동함을 실측(고친 방식은 즉시 종료·명확한 한글 메시지), 대조군으로 Werkzeug 프로세스 두 개를 정확히 같은 조건(한쪽이 일반소켓이면 Windows 가 WSAEACCES 로 막아버려 재현이 안 됨을 먼저 확인하고 고침)으로 띄워 옛 방식이 실제로 예외 없이 공존함을 실측, 회귀 전체(수정 직후 test_firstday.py 60+단계 실제 완주 — 첫날 완주 62/62 막힌지점 없음 — 이 라운드 수정 직후와 최종 복원 후 두 번 확인), test_firstday.py 의 사본생성 코드를 되돌려 실패 재현 후 복원 — firstday_server.py·test_firstday.py 둘 다 app.py 를 안 바꾸므로 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round308_fixes.py", "스캔 308라운드 회귀(deploy/ 문서군 상호정합성 결함 6건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — admin-before-go-live 순서·398개사 협력업체 수·manage.py 실제 명령목록·.env 키·PWA 매니페스트 아이콘·bokguon.service 등은 전부 클린 재확인. 306·307라운드가 다진 추적돼야 할 사본이 실제로 추적되는지 아무도 확인 안 함 패턴이 이번엔 코드가 아니라 문서에서 재발한 변종. (a)[심각] AWS·네이버클라우드 배포절차 둘 다 오픈 절차의 smoke_test.py 호출 앞에 자격증명 export 3줄이 없어, DEPLOY.md 가 125·285라운드 사고로 이미 붙여 둔 조치를 두 클라우드 문서는 안 따라가고 있었다 — export 없으면 smoke_test.py 의 _creds_or_skip() 이 어떤 검사도 안 돌리고 exit 2, 두 문서는 로그인만 건너뛴다 공개면·보안헤더는 검증된다고 적어 놓고 정작 그 검증 자체가 통째로 안 도는 상태였다. DEPLOY.md 와 같은 export+unset 블록과 종료코드 4 안내문으로 통일. (b) 네이버 문서의 6건은 이미 채워져 있다가 틀렸다(company_info.json 실측 7/8, AWS 문서는 이미 정확) — 7건으로 정정. (c)[컴플라이언스] company_info.json 의 hosting 값이 아마존웹서비스(AWS) 서울리전 으로 고정돼 공개 처리방침에 수탁자로 노출되는데, manage.py check 의 미기재 판정은 값이 있으면 통과시켜 이 오기재를 못 잡는다 — 네이버클라우드 문서에 set-info hosting 단계 신설. (d) AWS 문서의 옛 배포묶음 재사용 금지 경고(실제 사고 인용+7줄 검증 grep)가 네이버 문서엔 아예 없어 클라우드와 무관한 위험을 한쪽만 알고 있었다 — 이식. (e) 두 클라우드 문서 다 메모장 금지 BOM 때문에 첫줄이 무시된다 를 현재형으로 적어 뒀는데 305라운드가 envload.py 를 고쳐 이제 앱은 BOM 을 걸러낸다 — DEPLOY.md 는 이미 완화된 문구인데 두 클라우드 문서만 안 따라가 통일. (f)[심각, 교차파일] nginx_bokguon.conf 의 숨김파일 차단 정규식이 앱스토어_배포_가이드.md 가 안내하는 .well-known/assetlinks.json 경로까지 막고 있었다 — nginx 는 접두사 매칭이 ^~ 없이 이겨도(그 접두사가 더 길어도) 뒤따르는 정규식을 파일 순서대로 마저 검사한다(포트 80 블록엔 인증서 갱신용 예외가 있는데 443 블록엔 짝이 없었다) — location 에 ^~ 를 붙여 확정시켜 정규식 검사 자체를 안 타게 수정(처음엔 ^~ 없이 썼다가 스스로 재검토 중 발견해 정정), alias 로 실제 디렉터리 연결. 이 라운드는 문서·설정 텍스트만 고쳐 실행 코드 변경이 없어 grep 기반 구조확인 위주로 검증하되, nginx 의 실제 location 매칭 알고리즘(공식 문서의 선택규칙)을 이 설정파일의 진짜 location 블록에 그대로 재현해 실행 — /.well-known/assetlinks.json 이 이제 ^~ location 으로 확정됨을 실측, 대조군으로 진짜 숨김파일(/.env)·루트·정적파일·사진서빙·로그인 5가지 기존 경로가 전부 회귀 없이 그대로 감을 확인, ^~ 를 뺀 사본으로 재현하면 다시 막힘을 실측해 ^~ 자체가 수정의 핵심이었음을 증명 — app.py 등 실행 코드 미변경이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round309_fixes.py", "스캔 309라운드 회귀(deploy/backup_selfcheck.py 백업이 정말 만들어졌는지 확인하는 자가점검 도구 결함 2건 + DEPLOY.md 2장 보강, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — deploy/실테스트_준비절차.md(주 타겟) 는 228줄 전체를 manage.py·app.py·dispatch.py·notify_popbill.py 등 실제 코드와 대조해 전부 정확함을 확인(클린). backup_selfcheck.py 는 현재 유일한 호출자(deploy/일일백업.bat, 윈도 전용)에서는 우연히 두 결함 모두 안 드러난다(windows_setup.ps1 이 고정경로와 같은 값을 넣고, manage.py backup 이 윈도에선 평문 .db 만 남김) — 그래도 실제 결함이고 리눅스 자동화에 연결되는 순간 바로 발현되므로 고쳤다. (a) BACKUP_DIR 이 항상 레포/backups 로 고정돼 있었다 — 실제 백업을 쓰는 manage.py._backup_dir() 는 123라운드부터 BOKGUON_BACKUP_DIR 를 우선하고 없으면 BOKGUON_DB_PATH 기준 디렉터리를 쓰는데 이 스크립트만 그 통일을 안 따라갔다. bootstrap.sh 는 실제로 .env 에 BOKGUON_BACKUP_DIR=/var/backups/bokguon 을 써 넣으므로 리눅스에서 이 스크립트를 그대로 쓰면 진짜 백업이 쌓이는 곳과 다른 곳을 보고 백업이 하나도 없습니다 로 매번 실패한다. manage.py 를 통째로 import 하지 않고 같은 두 환경변수만 직접 읽어 같은 결론을 내도록 수정. (b) 파일 필터가 .db 만 인정했다 — 리눅스는 gzip 으로 .db.gz 를 남기는데(manage.py 의 cmd_check 자신이 이미 같은 이유로 두 확장자를 함께 봄) 이 스크립트만 안 따라가 정상 운영 중인 리눅스 서버에서도 영원히 0개로 실패할 뻔했다. .db.gz 도 인정하되 sqlite3 가 압축파일을 직접 못 여니 그 경우엔 크기·경과만 보고 무결성 검사는 건너뛴다(조용히 낮추지 않고 화면에 그대로 알림 — manage.py check 의 기존 선례와 같은 수준). DEPLOY.md 2장(수동 설치)이 admin 이름으로 관리자를 만드는데 0장에 있는 go-live 가 이 이름을 지운다 경고가 2장엔 없어 보강(회귀 대상 아님, 순수 문서). 회귀테스트는 진짜 backup_selfcheck.py 를 서브프로세스로, 진짜 sqlite3 로 만든 유효한 DB·진짜 gzip 압축으로 실제 실행(BOKGUON_BACKUP_DIR 직접지정·BOKGUON_DB_PATH 기준폴백·gz인식 3가지 실측) — 처음엔 반복문자 패딩이 gzip에 270배 압축돼 741바이트로 둔갑해 실패를 자체발견, 압축 안 되는 랜덤바이트로 교체해 해결(manage.py 자신의 100KB 기준이 압축여부 구분이 없는 게 실제로 맞다는 것도 함께 확인). 2곳 되돌려 결함 6건 재현(되돌린 상태에서 실제 운영 backups/ 폴더를 대신 찾아내는 것까지 실측 — 읽기전용 검사라 안전) 후 복원 — deploy/backup_selfcheck.py·DEPLOY.md 둘 다 app.py 미변경이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round310_fixes.py", "스캔 310라운드 회귀(deploy/팝빌_연동가이드.md·외부접속_안내.md·backup.sh 결함 3건 + 죽은 파일 정리, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 실제 발송 자격증명은 이 환경에 전부 비어 있음을 먼저 확인 후 조사(실발송 위험 없음). deploy/실테스트_준비절차.md 전수대조는 이미 309라운드가 클린으로 확인, 외부접속_안내.md vs 외부공개_안내.md 관계는 상호보완적이고 모순 없음을 재확인(클린), notify_popbill.py 의 바이트기준(90/2000)·재시도 3회·outbox 문구 등 팝빌 가이드의 다른 모든 구체적 수치도 301·280라운드 이후 수정과 전부 일치함을 재확인(클린). (a)[심각] 팝빌_연동가이드.md 의 .env 복사블록이 값 뒤에 샾 대신 화살표 기호로 설명을 붙여 뒀다 — envload.py 의 실제 파서는 샾으로 시작하는 주석만 인식한다. 그대로 복사해 붙이면 POPBILL_TEST 값이 문자열 1이 아니게 되고, notify_popbill.py 는 1이 아니면 운영(실발송·과금) 모드로 읽는다 — 이 가이드가 막으려던 바로 그 사고를 이 가이드 자신의 복사블록이 만들 수 있었다. 설명을 샾으로 시작하는 별도 줄로 옮김(진짜 .env 파일 자신의 관례). (b) 외부접속_안내.md 의 자동 시작 끄기 안내가 존재하지 않는 파일명을 가리키고 있었다 — 실제 등록 스크립트는 작업 스케줄러가 기본 경로이고 시작프로그램 폴백조차 다른 이름을 쓴다. 같은 문서 바로 위 줄이 이미 정확히 안내하는 중지 배치파일 + 실제 존재하는 -Remove 스위치로 정정. (c) backup.sh 가 보존기간 환경변수 이름을 잘못 읽었다 — bootstrap.sh·windows_setup.ps1 이 .env 에 실제로 써 넣고 manage.py 도 읽는 표준 이름과 이름을 통일. 부수로 scratch_r171_repro.py(307라운드가 죽은 코드로 확인, 이번 라운드가 재확인 후 삭제 — 인용된 app.py 줄번호 3곳 전부 이후 라운드들의 편집으로 이미 드리프트돼 있어 참고자료로서도 가치가 없었다)를 삭제. deploy/backup.sh 자체는 죽은 코드가 아니다 — manage.py 의 자체점검(cmd_check)·backup_selfcheck.py(309라운드) 둘 다 이 스크립트가 남기는 .db.gz 형식을 알고 있는 살아있는 대안이라 삭제하지 않고 이름만 통일 + DEPLOY.md 에 존재를 문서화. 진짜 설치된 python-dotenv 로 옛(화살표)/새(샾) 블록을 실제 파싱해 옛 블록은 실제로 POPBILL_TEST 가 1이 아니게, 새 블록(지금 문서에서 직접 추출)은 정확히 1로 파싱됨을 실측, backup.sh 문법도 실제 Git Bash -n 으로 확인 — deploy/ 문서·스크립트만 고쳐 app.py 등 실행 코드 변경 없음, 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round311_fixes.py", "스캔 311라운드 회귀(deploy/backup_selfcheck.py 크로스프로세스 .env 미로드 + bootstrap.sh systemd 백업경로 치환누락 결함 2건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — (a)[심각] backup_selfcheck.py가 309라운드에서 BOKGUON_BACKUP_DIR·BOKGUON_DB_PATH 두 환경변수를 직접 읽도록 고쳐졌지만, 이 스크립트 자신은 .env 파일을 한 번도 로드한 적이 없다 — 그 값이 이미 프로세스 환경변수로 심어져 있을 때만 통했다. 실측: 일일백업.bat 는 manage.py backup 을 먼저 부르고 그 다음 이 스크립트를 같은 배치 안에서 잇달아 호출하지만, 앞선 파이썬 프로세스가 os.environ 에 심은 값은 그 프로세스가 끝나면 사라지고 부모 배치나 형제 자식 프로세스로 전파되지 않는다(프로세스별 환경변수 격리) — app.py·manage.py 는 각자 첫 줄 부근에서 envload.load_dotenv() 를 스스로 부르는데 이 스크립트만 안 그랬다. 커스텀 BOKGUON_BACKUP_DIR 을 .env 에만 써 둔 배포에서는 이 자가점검이 항상 자기 fallback 경로(DB 옆 backups/)만 보고 백업이 하나도 없습니다 로 매번 실패했을 것이다(운영 배치는 지금까지 이 값을 프로세스 환경변수로도 심어 둬 우연히 안 걸렸다). envload 를 직접 import 해 스스로 .env 를 로드하도록 수정. (b)[심각] bootstrap.sh 가 systemd 유닛을 생성할 때 sed 로 /opt/bokguon 등 3가지만 커스텀 값으로 치환하고 bokguon.service 에 하드코딩된 ReadWritePaths=/var/backups/bokguon 은 그대로 뒀다 — BOKGUON_BACKUP_DIR 을 기본값과 다르게 설치하면 실제 백업이 쌓이는 디렉터리와 유닛이 쓰기 허용하는 디렉터리가 어긋난다. bokguon.service 자신의 주석(53행)이 이미 경고하듯 ProtectSystem=strict 아래에서 ReadWritePaths 에 적힌 경로가 기동 시점에 존재하지 않으면 systemd 는 그 경로만 제한하는 게 아니라 서비스 기동 자체를 거부한다 — 커스텀 설치 시 백업이 안 되는 정도가 아니라 서비스가 아예 안 뜰 수 있었다. sed 에 4번째 치환 규칙(/var/backups/bokguon → $BACKUP_DIR)을 추가. 회귀테스트는 진짜 backup_selfcheck.py 를 서브프로세스로 실행해 프로세스 환경변수엔 안 심고 격리된 .env 파일에만 BOKGUON_BACKUP_DIR 을 적어 일일백업.bat 가 실제로 부르는 방식 그대로 재현(고치기 전엔 fallback 경로만 봐서 실패, 고친 뒤엔 .env 의 커스텀 디렉터리에서 진짜 백업을 찾아 통과), bootstrap.sh 는 Git Bash 로 -n 문법 확인 + 새 sed 규칙을 진짜 sed 로 돌려 ReadWritePaths 가 정확히 치환되고 기존 /opt/bokguon 치환과 간섭 없음을 실측. 2곳 되돌려 결함 재현(되돌린 상태에서 회귀테스트 자신의 .index() 무가드 호출이 예외로 죽는 문제도 297·300·303 등과 같은 방식으로 자체발견 수정) 후 복원 — deploy/backup_selfcheck.py·deploy/bootstrap.sh 둘 다 app.py 미변경이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round312_fixes.py", "스캔 312라운드 회귀(seed_boq.py 표준단가 시드 도구가 관리자의 비활성 결정을 흔적 없이 되돌리던 결함 1건[심각] + seed_boq_led.py 하드코딩 절대경로 정리, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — VIEWS.estbands/VIEWS.boq(가견적기준·표준단가 관리 화면, 246라운드가 미완료로 남겼던 항목)까지 핵심 로직(myRank 등급가드·덮어쓰기 전 이전값 조회·_est_check/_est_basis 의 0원 경계) 전부 확인해 클린으로 판정, seed_boq.load() 의 deactivate_demo 블록(데모값 일괄 사용중지)도 db.py 데모시드 목록과 항목명을 전수대조해 겹치는 게 하나도 없어 의도된 설계임을 재확인(클린). [심각] seed_boq.py 의 load()(seed_boq_led.py 도 그대로 호출해 공유) 는 같은 (공종·항목·규격) 행을 찾을 때 active 상태를 전혀 안 보고, 찾으면 조건 없이 active=1 로 되돌렸다 — app.py 의 api_boq_delete(관리자 콘솔 '비활성' 버튼)가 이미 그 항목을 비활성(active=0)+이력('비활성')까지 남겨 뒀어도, seed_boq.py 를 다시 돌리면(이 CLI 는 실측상 반복 재실행이 정상 운영 패턴이다) 아무 조건 없이 되살아났다. 게다가 이력 기록은 가격이 실제로 바뀔 때만 실행되므로(297라운드가 '변경없는 재실행마다 중복 수정 이력이 쌓이던' 결함을 고치며 넣은 게이트), 가격이 그대로면 이 부활 자체가 boq_price_history 어디에도 안 남았다 — PATCH 수정 라우트(api_boq_update)는 active 컬럼을 아예 안 건드리므로, 이 CLI 가 사실상 유일한 '비활성 되돌리기' 통로였는데 그 유일한 통로가 아무 흔적을 안 남긴 것이다. 관리자가 오류·중복·폐기 판단으로 내린 결정이 다음 스크립트 재실행 한 번에 조용히 뒤집히고, 되살아난 항목은 관리자 화면(/api/boq)과 보험사 참고단가(_est_basis 의 ref_items) 양쪽에 곧바로 재노출된다. 되살리기 자체는 막지 않았다(유일한 되돌리기 수단이므로 없애면 오히려 회복 불가능한 실수를 만든다) — 대신 SELECT 에 active 를 함께 읽어 0→1 전환을 가격 변경 여부와 독립적으로 감지하고, '수정'과 구분되는 새 action='재활성' 이력을 반드시 남기도록 수정(db.py 의 boq_price_history 스키마 주석도 갱신). 부수로 seed_boq_led.py 27행의 이 PC 전용 하드코딩 절대경로(무해하지만 다른 계정·환경에서 import 경로로 쓰이면 깨질 수 있음)를 seed_boq.py 자신이 이미 쓰는 것과 같은 상대경로 패턴(os.path.dirname(os.path.abspath(__file__)))으로 정리. 회귀테스트는 격리 스크래치 DB 에서 진짜 seed_boq.load() 를 실행해 신규항목 적재 → app.py api_boq_delete 와 정확히 같은 SQL 로 비활성 처리(이력 '추가'·'비활성' 2건 확인) → 가격 변경 없이 재적재 → active 가 다시 1로 돌아오는 것(회복 기능 유지 실측)과 이력에 '재활성' 이 반드시 추가되는 것을 함께 실측, seed_boq_led.py 도 격리 스크래치 DB 로 실제 재실행해 상대경로 수정 후에도 24건 전부 정상 적재됨을 확인. 1곳 되돌려 결함 재현(되돌린 상태에서 이력이 '추가'·'비활성' 2건에서 멈추고 3번째 '재활성' 이 전혀 안 남는 것을 실측) 후 복원 — seed_boq.py·seed_boq_led.py 둘 다 app.py 가 import 하지 않는 독립 CLI, db.py 변경은 주석뿐이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round313_fixes.py", "스캔 313라운드 회귀(crypto_util.py 계좌 암호화 모듈 결함 1건[심각][컴플라이언스], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — nonce 재사용(os.urandom 12바이트, 실제 호출량이 AES-GCM 생일한계에 한참 못 미침)·복호화 실패 처리(120라운드 재확인 16/16)·키 형식오류 경고(261라운드 재확인 8/8)·blind_index/mask_account 계산 로직·키 로테이션 마이그레이션 부재(이미 261라운드 자신이 별개판단이라 명시)·encrypt 인자 타입 안전성·다중스레드 경쟁조건(실사용 경로 자체가 없음)은 실측 결과 전부 클린. [심각][컴플라이언스] _load_key() 의 '키 완전부재'(BOKGUON_ENC_KEY/BOKGUON_INDEX_KEY 미설정) 경고가 바로 그 자리 주석 자신의 약속(매번 경고를 남긴다)과 달리 warnings.warn() 을 써서 프로세스당 사실상 콜사이트 1회만 뜨고 그 뒤 영구 침묵했다 — 파이썬 warnings 모듈 기본필터가 (메시지·카테고리·호출지점) 조합을 기억해 최초 1회만 출력하기 때문(실측: 같은 줄에서 5회 warn() 해도 1건만 기록). encrypt()·blind_index() 를 같은 줄에서 함께 부르는 app.py 의 계좌 저장 라우트 기준으로, 키가 완전히 빠진 채 서버가 뜨면 최초 협력사 1곳이 계좌를 등록하는 순간에만 경고가 뜨고 그 뒤 나머지 전부(운영DB 실측 활성 협력사 365곳 규모)가 조용히 소스에 노출된 개발용 고정키로 계속 암호화됐다 — 이 파일의 다른 두 경고(라운드261 형식오류·라운드120 복호화실패)는 이미 자동 중복제거가 없는 _log.warning() 을 쓰는데 이 자리만 안 따라간 것이었다. warnings 모듈 대신 형제와 같은 _log.warning() 으로 통일(배포용 bootstrap.sh/windows_setup.ps1 은 이미 이 두 키를 자동생성해 넣으므로 정상 배포에선 이 분기 자체가 발동하지 않는다 — 이 결함은 '지금 뚫려있다'가 아니라 '방어선이 실제 발동해도 최초 1회를 놓치면 알아챌 방법이 없다'는 관측가능성 결함). 부수로 261라운드의 키 형식 길이검사(16/24/32바이트)가 base64 문자열 길이는 그대로 두고 내용만 한 글자 손상된 키는 원리적으로 못 잡는다는 잔여 사각지대(실측: 정상키 한 글자만 다른 유효 base64 문자로 치환해도 디코드 후 바이트 길이 동일, 경고 0건)를 발견했으나 이 계층에서 구조적으로 완전히 막을 방법이 없고 실제 방어선(manage.py check 의 복호화 왕복확인)이 계좌 0건인 신규배포 직후엔 건너뛰어진다는 사실만 재확인해, 코드 변경 없이 그 자리에 잔여위험과 대응절차(키 교체 뒤엔 계좌가 하나라도 들어간 채로 다시 check 를 돌려야 한다)를 주석으로 명시(사용자판단 보류항목 8개와 별개 — 정책판단이 아니라 이 계층에서 원리적으로 못 막는 잔여위험 문서화). 회귀테스트는 실제 파이썬 warnings 모듈 기본필터로 옛 동작(5회 호출→1건만 기록)을 대조군으로 먼저 재현하고, 실제 crypto_util.encrypt()·blind_index() 를 키 완전부재 상태로 5회·3회 반복호출해 _log.warning 호출횟수를 직접 실측(고치기 전 0회·고친 뒤 5회·3회 정확히 매번), 정상키가 있을 때 경고가 안 뜨고 암호화·복호화 왕복이 정상 동작함도 회귀확인. 1곳 되돌려 결함 재현(되돌린 상태에서 PowerShell 표준에러 자체가 5회 호출 중 RuntimeWarning 1건만 출력해 결함을 시각적으로도 실측) 후 복원 — crypto_util.py 는 app.py 57행이 import하므로 재기동 필요, BUILD_HASH 는 무관(static/templates 아님) 불변 예상)"),
    ("test_scan_round314_fixes.py", "스캔 314라운드 회귀(repair_estimate.py 자동가견적 엔진 전담 재조사 — 58라운드 이후 방치, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 핵심 계산로직(_span/_posts/_validate/estimate/_gate)은 58·69·201라운드가 이미 다져 놔서 새 런타임 결함 없음(클린), SKU 단가·수량배수를 seed_boq.py/seed_boq_led.py 실측값과 15종 전수대조도 완전 일치, NaN/Infinity 방어·choice 문자열/숫자 비교·price_book 주입 방어·app.py 단위불일치가드(라운드247)·db.py _backfill_sku_keys 모호성회피·순수함수 원칙(db 미import)도 전부 클린 재확인. 대신 코드는 맞는데 그걸 지키는 주변장치 3곳이 흐트러짐을 발견. (a) _gate(recipe, high, low, v=None) 가 low 를 매개변수로 계속 받았다 — high/low 비율로 판정하던 SPREAD_MAX 게이트를 지우며 함수 본문(비율이 늘 1.2로 고정돼 죽은 코드였다는 이유) 정리는 됐는데 시그니처 정리가 안 됐다, 실제로 함수 본문 어디서도 안 쓰임 — 나중에 구간폭 게이팅을 다시 살리려는 사람이 이미 low 가 들어오고 있다고 착각하지 않도록 제거. (b) test_repair_estimate.py 의 지주수(_posts) 손계산 대조 3곳(L=8,s=4/L=8,s=2/L=20,s=2)이 전부 L 이 s 의 배수라 올림(ceil)·내림(floor) 결과가 우연히 같아, 이 파일 자신은 58라운드가 고친 floor 버그 회귀를 못 잡는 구조였다(58라운드 자신의 테스트는 비배수 조합 RE._posts(9,2) 로 실제로 잡고 있어 안전망 자체는 살아있었음, 되돌려서 실측 확인). 게다가 기존 검산 라벨·수식이 '내림(floor)'으로 적혀 있어 정답인 올림(ceil)과 반대 공식을 정답처럼 보여주고 있었다 — 라벨·수식을 올림으로 정정하고 비배수 조합(9,2)을 추가해 이 파일 자신도 자립 검증하도록 이중화. (c) repair_estimate_설계.md 가 세 군데 드리프트 — 검증건수(53→실제 65건, 회귀가 늘 때마다 바뀌므로 문서 대신 실행결과를 신뢰하라는 안내로 교체), LED 보안등기구 교체 상태(69라운드가 이미 complete=False 로 내렸는데 문서는 아직 완비✅로 표기 + 완비5/보완필요5 카운트도 그에 맞춰 오기), 게이팅 규칙 3번째 조건(실제로는 삭제된 지 오래인 구간폭≤1.6배를 여전히 현재형으로 서술하고, 실제 동작 중인 needs_calibration_if 훅(현재 복층유리 창호 교체 1건만 사용)은 언급이 아예 없었음) — 셋 다 순수 문서수정, 런타임 결함 아님. 회귀테스트는 실제 inspect.signature(RE._gate) 로 시그니처 확인, 실제 estimate() 호출로 회귀없음 확인, RE.RECIPES 의 실제 complete 개수 집계(4,6)와 led_security_light 판정을 설계문서 서술과 자동 대조(둘 중 하나만 바뀌어도 다음에 걸리도록), 설계문서 텍스트가 죽은 게이트 문구를 더는 현재형으로 안 담고 실제 훅을 언급하는지 확인. repair_estimate.py 는 되돌려서(_gate 시그니처, _posts floor) 결함 재현 후 복원, 설계문서도 게이팅 규칙 절을 되돌려 재현 후 복원 — repair_estimate.py 는 app.py 66행이 import(RE)하므로 _gate() 시그니처 변경은 재기동 필요(BUILD_HASH 는 무관, static/templates 아님·불변 예상), test_repair_estimate.py·repair_estimate_설계.md 자체는 app.py 미import)"),
    ("test_scan_round315_fixes.py", "스캔 315라운드 회귀(compliance.py 복합공종 판정이 WORK_RULES 딕셔너리 등록순서라는 우연에 기대던 결함[컴플라이언스][경미~중간], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 같은 라운드가 힌트1번 dispatch.py(출동배차 알고리즘 본체, 거리계산연동·후보선정·동시성가드·IDOR방지 전부)도 전담 정밀조사했으나 94·95·117·138·152·182·189·190·257·279라운드가 이미 촘촘히 다져 놔서 새 결함 없음(클린, 이것도 정당한 결과). compliance.py 본체(rule_for·check_direct_contract·related_sum)를 힌트2번으로 파서 발견. app.py 가 사건접수에서 공종을 2개 이상 고르면 category='복합(A · B · ...)' 로 합치는데(app.py 3763행), rule_for() 는 배제업종·타법소관·판정불가가 하나라도 섞였는지는 278라운드가 이미 정확히 가려 놨지만(재확인, 클린), 전부 special(또는 general)일 때는 복합문자열 전체에 부분일치를 걸어 WORK_RULES 딕셔너리에 먼저 등록된 트레이드 하나만 그대로 썼다 — 이 파일 자신의 주석(120~122행)이 이미 '여러 공종이 섞이면 종합공사로 본다(기준 5천만원)'고 명시하는데, 실제로는 서로 다른 special 트레이드가 몇 개 섞이든 전문공사 단일한도(1,500만원)로 고정 판정됐다(딕셔너리 순서라는 우연에 의존 — 표에 항목을 추가·재배열하면 조용히 결과가 바뀔 수 있는 구조). 실측: 5개 special 업종 전수 10가지 조합을 2,500만원으로 직접 실행해 전부 재현(항상 15,000,000원 고정), '복합(유리·샷시·자동문 · 조경·수목)' 2,000만원 건이 실제로는 도급가능해야 할 금액인데 '금액초과'로 막혔다. 방향은 과소차단(형사노출)이 아니라 과잉차단(영업손실)+감사기록 부정확(그 사건 전체를 대표 못 하는 부수 트레이드 하나의 이름·기준이 contract_gate_log 소명 스냅샷에 영구히 남음)이지만, 의도적 설계가 아니라 딕셔너리 삽입순서라는 우연에 기대는 취약한 구조였다. 복합(...) 안의 토큰 각각을 재귀적으로 rule_for() 판정해 막는 kind 우선순위(기존과 동일, 회귀없음 재확인)는 그대로 두고, 전부 special/general인데 서로 다른 트레이드가 2개 이상이면 '종합 원상복구'(5천만원)로, 실질적으로 1개뿐이면(중복선택 등) 그 트레이드 자신의 규칙 그대로 반환하도록 수정 — 파일 자신이 이미 문서화한 원칙을 실제 코드로 옮긴 것이라 새 정책판단이 아니다. 부수로 record_gate()의 override_reason 매개변수가 실제 호출부 5곳(app.py) 전수 확인 결과 단 한 곳도 값을 안 넘겨 contract_gate_log.override_reason 컬럼이 항상 NULL임을 발견 — 판정불가(ok=False)여도 낙찰·승인 자체는 안 막는 이 파일의 설계상 운영자가 경고를 보고도 강행할 수 있는데 '왜 넘겼는지'가 하나도 안 남는다는 뜻이나, 이걸 메울 '강행 확인 UI'를 새로 만들지는 제품판단이 필요해 이번 라운드는 배선 문제 발견과 인라인 문서화만 하고 임의로 새 UI/API 계약을 만들지 않음(사용자판단 보류 8개 목록과는 별개 — 정책질문이 아니라 배선 안 된 필드 발견, 다음 라운드 재조사 불필요하도록 기록만). 회귀테스트는 실제 compliance.check_direct_contract() 를 다양한 실제 조합·금액으로 직접 호출(5종 전수 10가지 조합, 종합 안전선 경계값 전후, 배제·타법소관·판정불가 우선순위 회귀없음, 단일트레이드는 승격 안 됨, '복합(' 접두어 없는 278라운드 원본 형식도 경로 미변경 확인 — 이 마지막 둘은 기존 test_compliance.py 34개와도 교차 재확인해 회귀없음 이중검증). 1곳 되돌려 결함 재현(되돌린 상태에서 새 판정 관련 7개 체크가 정확히 예상대로만 깨지고 회귀방지용 6개는 그대로 통과함을 실측) 후 복원 — compliance.py 는 app.py 63행이 import(CP)하므로 재기동 필요(BUILD_HASH 는 무관, static/templates 아님·불변 예상))"),
    ("test_scan_round316_fixes.py", "스캔 316라운드 회귀(geo.py 좌표해석기 결함 2건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 같은 라운드가 totp.py(RFC 6238 공식벡터로 _code_at() 직접검증, drift·재사용차단·app.py 배선까지 전부)와 addr_search.py(카카오 x/y 좌표매핑 실라이브호출 검증, 예외튜플 전수확인)도 전담 정밀조사했으나 둘 다 실결함 없음(클린, 정당한 결과 — addr_search.py의 _road_only 필드가 계산만 되고 저장소 전체에서 아무도 안 읽는 완전한 사문임을 발견했으나 잘못된 동작을 유발하지 않아 정보성으로만 기록). geo.py 에서 실측 재현되는 결함 2건. [심각] 2022년부터 수원·고양·용인·창원 4개 시가 '특례시'라는 공식 행정명칭을 쓰는데(예: '용인특례시'), resolve() 가 시군구 매칭에 쓰는 _word_in() 의 오른쪽 경계검사(_ADMIN_SUFFIX, 지명 뒤 한 글자만 보는 문자클래스)에 '특'이 없어 매치가 거부되고, 시군구 단위로 정확히 찾을 수 있는 주소가 훨씬 부정확한 도(道) 단위 폴백까지 밀려났다 — 실측: 운영DB 협력사 #211 하우건설(주)의 실주소 '경기도 용인특례시 처인구 신송로131번길 20-10'이 정확히 이 표기(현재는 이미 저장된 정밀좌표geo_src=주소검색가 우선 적용돼 화면엔 마스킹돼 있으나, resolve() 자체의 오차를 계산하면 정상 매칭 대비 약 5배(6.35km→31.4km) 더 벌어짐). 실제 노출 경로는 카카오 주소검색(자체적으로 '특례시'를 '시'로 정규화해 돌려줘 이 경로는 무관함을 라이브 호출로 확인)이 아니라 ingest_partners.py/partners_seed.json 같은 일괄수집이나 관리자의 공문서 표기 손입력이며, 좌표가 아직 없거나 나중에 좌표해제될 때만 실제로 발현된다. resolve() 진입 시 '특례시'를 '시'로 미리 치환해 이 4개 시는 물론 향후 추가되는 특례시도 한 번에 해결(_word_in()/_ADMIN_SUFFIX 자체는 손대지 않아 다른 지명 판정에 영향 없음). [경미, 현재는 도달불가] case_coords(None) 이 형제(partner_coords)와 달리 region/address 조회를 _has() 로 안 감싸고 'region' in row.keys() 를 직접 호출해 AttributeError 로 죽는다 — 저장소 전체 호출부 4곳(app.py 3곳·dispatch.py 1곳)을 전수 추적한 결과 전부 사전에 None 을 걸러내거나 try/except 로 감싸 실제 도달 사례는 0건이지만, 형제와 다른 패턴을 유지할 이유가 없어 통일(향후 새 호출부가 형제 패턴을 가정하고 가드 없이 추가되면 바로 터질 잠복 결함이었음). 회귀테스트는 실제 GEO.resolve() 를 4개 특례시 전부(용인·수원·고양·창원)에 대해 '특례시' 표기와 '시' 표기 양쪽으로 직접 호출해 완전히 동일한 결과(좌표·출처문구)가 나옴을 실측, 운영DB 실사례(하우건설) 주소로 재현해 GU['용인'] 중심좌표와 사실상 일치함을 확인, 안산시·남동구(라운드196) 등 기존 판정 회귀없음 재확인, case_coords(None)/partner_coords(None) 양쪽 실제 호출로 안전반환 확인. 2곳 각각 되돌려 결함 재현(되돌린 상태에서 특례시 10개 체크·DB실사례 1개·case_coords(None) 1개, 정확히 예상된 조합만 깨지고 회귀방지용 5개는 그대로 통과함을 실측) 후 복원 — geo.py 는 app.py 64행이 import(GEO)하므로 재기동 필요(BUILD_HASH 는 무관, static/templates 아님·불변 예상))"),
    ("test_scan_round317_fixes.py", "스캔 317라운드 회귀(legal_docs.py 처리방침의 보안설정 수치 3종이 실제 운영 환경변수와 연동 안 되고 순수 리터럴로 박혀 있던 결함[컴플라이언스], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견(legal_docs.py Finding 2 는 이미 알려진 보류항목이라 재론 안 함, 그와 무관한 새 각도) — 힌트로 제시된 manage.py cmd_backup/cmd_restore 는 292라운드가 이미 전수조사해 두텁게 방어돼 있음을 test_scan_round292_fixes.py 재확인으로 검증(재조사 불필요 확정), check_orphan_chars.py·check_tx_paths.py·db.py·wsgi.py 도 기존 라운드태그 밀도로 이미 소진된 영역임을 확인(클린). legal_docs.py 의 처리방침 제3조(접속기록 보유기간)·제7조(안전성 확보조치)·제8조(쿠키)가 '2년'(2곳 — 제3조 표 + 제7조 문단, 서로 다른 문장에서 같은 사실을 두 번 말함)·'5회 연속 오류'·'30분'을 순수 고정문구로 서술하는데, app.py 는 이 세 사실을 전부 환경변수(BOKGUON_LOG_RETENTION_DAYS 기본730·BOKGUON_MAX_LOGIN_FAILS 기본5·BOKGUON_SESSION_MIN 기본30)로 실제 제어하고 .env.example 자신이 배포 규모에 맞춰 조정하라고 명시적으로 안내한다(예: 5만명 미만 소규모는 보관기간 365일로 낮춤 — 고시 §8 원칙 365일, 5만명↑ 또는 고유식별정보 처리 시 730일). 지금 이 저장소의 실제 .env 값은 우연히 문서 숫자와 일치할 뿐 — 운영자가 안내대로 값을 조정하는 순간 처리방침은 여전히 옛 숫자를 공개 고지하게 된다. 이 파일은 정확히 이 패턴(설정과 문서 불일치)을 이미 두 번 고친 전례가 있다 — IP제한 유무(ip_limit_enabled, ADMIN_IP_ALLOW 가 비면 그 문구만 빠짐)와 하자담보책임기간(289라운드, 사건별 가변값으로 인정) — 그런데 이 세 자리만 그 교훈을 못 받고 남아 있었다. manage.py check 의 법정게시물 미기재 검사는 company_info.json PENDING 만 보고 이 세 환경변수와 문서 텍스트를 대조하는 코드는 전무함을 grep 전수확인. 같은 두 전례와 동일한 패턴(호출부가 실제 운영값을 넘기고, 기본값은 옛 고정문구와 동일해 회귀 없음)으로 privacy_body() 를 확장 — app.py 의 /legal 라우트(MAX_LOGIN_FAILS·ACCESS_LOG_RETENTION_DAYS 기존 모듈변수 재사용 + BOKGUON_SESSION_MIN 즉시조회)와 build_pages.py 의 정적빌드(이미 envload.load_dotenv() 를 부르므로 os.environ 직접조회로 실제 .env 값을 그대로 반영) 양쪽을 갱신. 회귀테스트는 인자생략 시 옛 고정문구와 완전동일(회귀없음)·커스텀값(3회·15분·365일)이 네 자리(제3조 표·제7조 문단 각각의 '2년' 형제자리 포함) 모두에 정확히 반영·365로 안 나눠떨어지는 값(400일)은 억지로 년단위로 반올림 안 함·IP제한과 독립동작·실제 /legal/privacy 라우트를 Flask test_client 로 직접 호출해 app.py 의 실제 MAX_LOGIN_FAILS·ACCESS_LOG_RETENTION_DAYS 값이 그대로 응답에 나타남을 실측. 기존 test_feature_work_coverage.py(1개 인자로만 부르는 옛 호출부)·test_scan_round289_fixes.py·test_scan_round306_fixes.py(docs/ 와 새 빌드 완전일치 불변식)도 재실행해 전부 회귀없음 재확인(현재 .env 값이 기본값과 동일해 docs/ 재생성해도 바이트 단위로 안 바뀜을 306라운드 자신의 불변식 통과로 확인). 1곳(legal_docs.py 의 privacy_body 본체) 되돌려 결함 재현(되돌린 상태에서 app.py 실제 라우트가 새 kwarg 를 옛 시그니처에 넘겨 TypeError→500 응답까지 실측, 10개 체크 정확히 예상대로만 깨지고 회귀방지 3개는 그대로 통과) 후 복원 — app.py 자신의 라우트 본문과 legal_docs.py(app.py 60행 import) 둘 다 변경이라 재기동 필요·이번엔 app.py 자체가 바뀌어 BUILD_HASH 로테이션 예상(다른 대부분의 최근 라운드와 달리 static/templates 아닌 app.py 코드 변경))"),
    ("test_scan_round318_fixes.py", "스캔 318라운드 회귀(사건 감사로그를 찾는 3곳이 접수번호 부분열 충돌에 취약하던 결함[심각] + error.html 과잉 |safe 결함[경미,잠재적], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — run_all_tests.py 전체 등록내역을 자체 재구성해 templates/case_history.html(사건 전체 이력 리포트)이 여태 어느 라운드에도 주 타겟으로 등장한 적 없음을 확인하고 감사대상으로 확정, 부수로 admin.html·version.html 도 함께 훑어 클린 재확인(admin.html 메뉴 31개와 admin.js VIEWS.* 31개 전수대조 1:1 일치 등). activity_log 에는 case_id 외래키가 없어(db.py 스키마) 사건 감사로그를 찾는 유일한 수단이 detail LIKE '%접수번호%' 뿐인데, 접수번호는 발주처가 직접 정하고(app.py _create_case, 형식검증 없음, 20자 이내 자유입력) 한 접수번호가 다른 접수번호의 부분열이면(예: '1023'과 '10234') LIKE 는 둘을 구분 못한다 — 라운드117이 막은 '%'·'_' 와일드카드 주입과는 다른 결함으로, 와일드카드 없이 순수 숫자만으로도 재현된다(격리 DB 실측: 사건 '1023' 리포트가 무관한 사건 '10234'의 낙찰금액·시공사명까지 끌어옴). case_history_report()(철칙4: 이 문서는 발주처에게 그대로 건네질 수 있다고 라우트 자신이 명시) 외에 형제 2곳(api_settlement_detail 정산상세 타임라인, api_case_renotify 재알림 30분 쿨다운 — 후자는 반대로 정당한 재알림이 남의 쿨다운에 막히는 기능오작동 방향)도 동일 패턴. 운영DB 96건 전수대조 결과 현재 충돌쌍 0건(자동채번 78건은 자릿수 고정이라 충돌불가, 자유입력 18건도 우연히 무충돌)이라 메커니즘은 100% 실증됐으나 잠복 상태. geo.py의 지명 경계판정(_word_in, 316라운드)과 같은 원리로 _case_no_in_detail() 공유헬퍼를 신설 — LIKE 로 후보만 넓게 거르고 파이썬에서 앞뒤가 숫자·영문이 아닐 때만(더 긴 번호의 일부가 아닐 때만) 진짜 일치로 인정, 90여 곳에 달하는 DB.log() 호출부가 접수번호를 항상 맨 앞에 두는 관행에 기대는 대신(관행일 뿐 강제 아님, 검증 비용도 과다) 어느 위치에 있어도 안전한 경계검사로 해결. 정산상세는 먼저 100건을 넉넉히 받아 경계검사로 거른 뒤 20건으로 잘라(먼저 자르면 걸러진 자리만큼 화면이 빔), 재알림 쿨다운은 COUNT(*) 대신 후보를 받아 파이썬에서 경계검사 통과 여부로 판정. 부수로 error.html 의 {{ msg|safe }} 가 실제 호출 7곳 중 500에러 참조번호(secrets.token_hex, <b> 굵게표시) 단 1곳을 위해서만 필요한데 전체에 이스케이프를 꺼 둔 채였음을 발견(나머지 6곳은 전부 고정 한국어 문구뿐이라 지금 당장 악용 가능한 XSS는 없음, 라운드36과 같은 부류의 재발 토양으로만 존재) — 템플릿은 기본 이스케이프({{ msg }})로 되돌리고, 500에러 자리만 markupsafe.Markup().format(escape(ref)) 관용구로 명시적 안전표시. 회귀테스트는 _case_no_in_detail() 실제 호출로 양방향 경계(뒤에 숫자 붙음·앞에 숫자 붙음)·하이픈 채번형식·빈문자열 전수확인, 실제 부분열 충돌 사건 2건(1023/10234)을 격리 DB에 실제로 만들어 실제 DB.log() 형식 감사로그까지 남긴 뒤 실제 /report/case/<id> 라우트를 인증 세션으로 직접 호출해 무관한 사건의 낙찰금액·시공사명이 응답에 없음을 실측, 형제 2곳은 소스구조 확인+같은 픽스처로 실제 정산타임라인 쿼리를 재현해 LIKE 후보 2건 중 경계검사 통과 1건만 남음을 실측, error.html 은 실제 render_template 호출로 일반 문자열은 이스케이프되고 Markup 로 명시한 곳만 굵게 나옴을 실측. 2곳(case_no 경계헬퍼 본체, error.html+500핸들러) 각각 되돌려 결함 재현(되돌린 상태에서 실제 라우트 응답에 남의 낙찰업체명·금액이 실제로 노출됨을 실측 포함, 6개 체크 정확히 예상대로만 깨지고 나머지 9개는 회귀 없이 통과) 후 복원, 기존 test_scan_round117_fixes.py 등 배터리 전체 사전 재확인으로 무충돌 검증 — app.py 자신의 라우트·헬퍼 변경이라 재기동 필요, static/templates(error.html) 도 함께 변경이라 BUILD_HASH 로테이션 예상)"),
    ("test_scan_round319_fixes.py", "스캔 319라운드 회귀(templates/offline.html·case_history.html·insurer_api_guide.html 세 화면의 유일한 버튼이 CSP 에 막혀 죽어있던 결함[경미], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 같은 라운드가 templates/legal.html(법정게시물 셸)도 전담조사해 클린 확정(doc.title/sub/pending 전부 자동이스케이프 경로만 사용, doc.body|safe 의 실위험지점은 legal_docs.py _esc() 가 이미 전담처리, csp_nonce/asset() 전역주입 확인, PENDING 배너 dev전용 노출 실측일치, sitemap/robots 링크 무결). app.py 의 _security_headers(모든 응답에 예외없이 적용되는 전역 after_request)가 script-src 'self' 'nonce-{요청별 난수}'(unsafe-inline 없음)를 붙이는데, nonce 는 <script> 요소에만 붙을 자리가 있고 onclick='...' 같은 인라인 이벤트 핸들러 속성에는 붙일 자리 자체가 없어 모든 최신 브라우저가 무조건 차단한다 — 바로 이 이유로 static/actions.js(이벤트 위임 디스패처)가 이미 만들어져 있고 그 자신의 독스트링이 이 정확한 CSP 한계를 문서화하며, 템플릿 40여 개 중 37개가 이미 이 패턴(data-act + addEventListener)으로 전환돼 있는데 세 화면(오프라인 셸의 '다시 시도', 사건 이력 리포트·발주처 연동안내서 각각의 '인쇄 / PDF 저장')만 옛 onclick= 그대로 남아 마이그레이션에서 누락됐다. 정규식(온갖 인라인 이벤트 속성 포괄)으로 templates/ 전체 40여개 파일 전수확인한 결과 정확히 이 3곳뿐임을 확인. 500/에러 응답이 아니라 200 OK + 브라우저 콘솔 CSP 위반 경고 하나로만 나타나(서버 로그·HTTP 상태에 흔적 없음) 이 프로젝트의 HTTP상태 기반 회귀 전부가 원천적으로 못 잡는 종류 — 전체 test_*.py 에서 onclick 문자열 검색해도 0건이었음. 무거운 actions.js 전체를 새로 얹는 대신(세 페이지 다 원래 안 쓰고 있었다) 각자 id + nonce 붙은 짧은 <script> 로 addEventListener 직접 연결(케이스별 최소 변경). 회귀테스트는 세 템플릿 소스에 <button onclick= 이 더는 없음을 실제 파일로 확인(설명주석 자신이 옛 'onclick='...'' 문구를 인용해 자기참조 오탐 위험 있어 정규식으로 실제 태그 사용만 좁혀 검사, 313라운드와 같은 함정 사전회피), 실제 서버로 세 라우트(/offline 인증불필요, /docs/insurer-api 관리자세션 필요 — 함수 내부 자체 인증이라 데코레이터grep으로 안 잡힘 발견, /report/case/<id> 하위관리자 세션)를 전부 실제 호출해 응답 본문에 onclick= 없음·새 id 렌더·addEventListener 렌더를 실측, 가장 중요하게는 응답 본문 <script nonce=...> 값이 실제 CSP 응답헤더의 nonce 와 정확히 일치함(불일치하면 브라우저가 그 스크립트 자체를 차단하는 것과 같은 효과)까지 실측. 3곳 각각 되돌려 결함 재현(되돌린 상태에서 실제 세 라우트 응답 전부에 onclick= 이 재현되고 11개 체크가 정확히 예상대로만 깨짐) 후 복원 — templates/ 3개 파일 변경이라 재기동 필요·BUILD_HASH 로테이션 예상(app.py 는 미변경))"),
    ("test_scan_round320_fixes.py", "스캔 320라운드 회귀(run_all_tests.py — 이 검증 오케스트레이터 자기 자신 결함 3건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 자체 재구성 기법(UNIT 304개 전체 등록내역을 읽어 실제 주 타겟 파일 목록을 재구성)으로 db.py 제외한 루트 .py 30개·static의 js 7개·templates의 html 20개 전부가 이미 한 번 이상 주 타겟이었음을 확인한 뒤, 유일하게 한 번도 전담조사된 적 없던 파일이 279회 넘게 언급만 되고 정작 자기 자신은 조사대상이 된 적 없는 run_all_tests.py 임을 찾아냄. [중간] preflight() 가 서버 채널이 개발이 아님을 이미 감지해 problems 에 추가하고도 return 없이 그대로 흘러 빌드해시 비교를 거쳐 실제 관리자 로그인 POST 까지 그 서버로 보냈다 — 이 파일 자신의 독스트링(2026-08-06 사고)이 막으려던 바로 그 사고(BOKGUON_TEST_BASE 실수로 운영을 가리킴)가 났을 때, 이 로그인 시도가 운영 감사로그에 실패기록을 남기고 MAX_LOGIN_FAILS 문턱에 근접해 있었다면 실제 관리자를 잠글 수 있는 구조였다. 실측: 격리 스텁 서버(GET /api/version 에 channel=운영, POST /api/login 에 401 응답)를 실제로 띄워 preflight() 를 직접 호출 — channel='운영' 문제를 정확히 감지하면서도 그 서버로 실제 POST /api/login 요청이 나가는 것을 확인. 채널 문제 감지 시 그 자리에서 즉시 return 하도록 수정(빌드해시만 낡고 채널은 정상인 경우는 로그인 시도를 막을 이유가 없어 그 경로는 그대로 둠 — 대조군으로 실측 확인). [경미] HTTP 리스트가 라운드248에서 test_otp.py 를 UNIT→HTTP 로 옮기며 10→11개로 늘었는데, 중단 안내 문자열 두 곳(비밀번호환경변수 없음·사전점검 실패)이 여전히 하드코딩된 'HTTP 10개'였다(report() 함수 안의 과거 사고를 그대로 인용하는 역사적 주석 1곳은 의도적으로 안 건드림 — 그 시점 실제 있었던 수치의 기록이라 현재값으로 고치면 오히려 왜곡됨). f'HTTP {len(HTTP)}개' 로 교체해 앞으로 리스트가 또 늘어도 자동으로 맞게 수정, 독스트링의 총 소요시간 추정치(약 40분)도 현재 HTTP 레이트리밋 대기만으로 이미 50분 안팎임을 반영해 정정. [경미·구조적] local_build_hash() 가 app.py 의 _build_hash() 를 의도적으로 손으로 그대로 베낀 사본인데(검증기가 app.py 를 import 하면 안 된다는 설계) 둘이 실제로 계속 같은 값을 내는지 확인하는 테스트가 저장소에 전무했다 — 나중에 app.py 쪽만 확장자·디렉터리를 늘리면 이 사본이 조용히 낡아 preflight() 의 빌드해시 비교가 매번 거짓으로 서버가 옛 코드라며 HTTP 전체를 계속 차단하게 될 잠재 결함(81·221·272·285라운드와 같은 '자기도구가 내는 거짓신호' 계열). 회귀테스트에서 두 함수를 실제로 각각 호출해(app.py 는 실제 import, run_all_tests.py 는 이미 로드됨) 지금 이 저장소 상태에서 바이트 단위로 같은 해시를 내는지 직접 비교해 확인. 1곳(preflight 의 return) 되돌려 결함 재현(되돌린 상태에서 격리 스텁 서버가 실제로 POST /api/login 을 수신함을 실측, 8개 체크 중 정확히 그 1개만 깨지고 나머지 7개는 회귀없이 통과) 후 복원 — run_all_tests.py 는 app.py 가 import하지 않는 독립 검증도구라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round321_fixes.py", "스캔 321라운드 회귀(db.py 최상위 함수 단위 라운드태그 커버리지 대조로 찾은 결함 2건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 320라운드가 파일단위 재구성 기법을 소진시킨 것을 확인한 뒤, db.py 안의 라운드태그(정확히 24곳) 위치를 함수경계와 대조해 최상위 함수 16개 중 10개(get_db·now·sql_now·hash_pw·verify_pw·is_legacy_hash·log·_backfill_child_is_demo·_backfill_sku_keys·init_db)가 자기 코드에 대한 태그를 한 번도 받은 적 없음을 확인, 그중 8개를 정밀조사(get_db/hash_pw/verify_pw/is_legacy_hash/sql_now/log/init_db/_backfill_child_is_demo/_backfill_sku_keys — get_db·now·hash_pw·verify_pw·is_legacy_hash·log·_backfill_child_is_demo·_backfill_sku_keys·init_db 는 실제 호출부까지 대조해 클린, init_db 의 go-live 재시딩 방지 로직을 검증하는 유일한 테스트가 문자열 존재만 보는 정적검사뿐이라는 관찰도 남김 — 결함 아님). [심각] _backfill_track_token_hash() 의 행별 UPDATE 에 예외처리가 전혀 없어 형제 두 함수(_backfill_sku_keys 의 행별 UPDATE·_backfill_child_is_demo 의 표별 UPDATE, 둘 다 sqlite3.OperationalError 를 잡음)와 다르다 — deploy/DEPLOY.md 의 실제 배포절차(327~337행, 서비스 재시작 **전에** manage.py migrate 를 먼저 돌림)와 겹치면, 살아있는 서비스가 쓰기 잠금을 쥔 순간 이 함수의 UPDATE 가 그대로 database is locked 를 내며 migrate()→init_db()→app.py 모듈최상단의 무방비 DB.init_db() 호출까지 뚫려 워커 기동이 죽을 수 있는 구조(295라운드 신설 당시 그보다 오래된 [R5-05]·70·277라운드가 이미 세운 동시접근 방어 컨벤션을 못 물려받음 — '오래된 컨벤션을 나중에 만들어진 코드가 못 물려받는다'는 이 세션의 반복 패턴이 이번엔 파일이 아니라 함수 단위로 재발). 실측: 격리 DB 에서 다른 커넥션이 BEGIN IMMEDIATE 로 진짜 쓰기잠금을 쥔 상태로 이 함수와 migrate() 를 그대로 호출 — OperationalError('database is locked') 가 그대로 전파됨을 확인. 형제와 같은 try/except 패턴으로 통일(이 함수는 이미 멱등이라 실패 행은 다음 migrate() 가 마저 채움, verbose 모드에서 실패건수도 알림 — 형제 _backfill_child_is_demo 의 더 나은 관행까지 반영). [경미/설계상 잠재위험] sql_now() 가 offset 매개변수를 이스케이프 없이 SQL 문자열에 f-string 으로 그대로 이어붙인다 — 저장소 전체 호출부 2곳(app.py 8912·5294행) 전수확인 결과 지금은 리터럴이거나 항상 안전한 정수로만 채워 실제 주입 경로가 없지만, 헬퍼 자체가 이를 강제하지 않아 향후 사용자 입력에서 유도한 값이 들어오면 즉시 SQL 인젝션이 열리는 구조 — docstring 이 이미 보여주는 형식('-10 minutes' 류)만 통과시키는 화이트리스트 정규식 검증을 추가(현재 안전한 호출 2곳은 전부 그대로 통과함을 실측 확인). 부수로 sql_now()/recent_duplicate() 관련 SQL 결합 패턴도 함께 검토해 같은 결론 확인. 회귀테스트는 BOKGUON_SQLITE_BUSY_MS 를 짧게(200ms) 낮춰 실제 SQLite 잠금 재현을 빠르게 하고, 실제 두 번째 커넥션으로 BEGIN IMMEDIATE 잠금을 쥔 채 _backfill_track_token_hash()·migrate() 를 그대로 호출해 예외 없이 넘어가고(실패건은 조용히 건너뜀, 몰래 성공 아님을 행 상태로 재확인) 잠금 해제 후 재실행하면 정확한 해시로 완전히 회복됨을 실측, sql_now() 는 정상 형식 5종 통과와 SQL 인젝션 시도 3종(따옴표 이스케이프·OR 조건·세미콜론 체이닝) 차단을 실제 호출로 확인. 2곳 각각 되돌려 결함 재현(되돌린 상태에서 실제 OperationalError('database is locked') 가 두 자리(함수 단독·migrate 전체) 모두에서 그대로 전파되고, 인젝션 시도 3종이 전부 무방비로 통과함을 실측 — 정확히 5개 체크만 깨지고 나머지 7개는 회귀없이 통과) 후 복원 — db.py 는 app.py 가 import(모듈최상단에서 DB.init_db() 호출)하므로 재기동 필요 — 스키마(CREATE/ALTER) 변경은 없지만 실제 동작이 바뀌는 변경(behavioral change)이라 재기동판단 규칙(app.py/geo.py/static/templates/db.py 스키마변경 시에만 — 이 스키마는 예시일 뿐 동작변경 전반을 뜻함)에 해당(BUILD_HASH 는 무관, static/templates 아님·불변 예상))"),
    ("test_scan_round322_fixes.py", "스캔 322라운드 회귀(deploy\\고정도메인_설정.ps1 — 고정 커스텀 도메인 전환 스크립트, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — run_all_tests.py 전체 등록내역을 자체 재구성해 저장소 루트 .py 32개·static/*.js 8개·templates/*.html 20개는 이미 전부 최소 1회 정밀조사를 거쳤음을 확인한 뒤, deploy/ 폴더 안에서 유일하게 어떤 라운드 주석에도 등장한 적 없던 이 파일을 찾아냄(형제 파일들 — 외부접속_상시가동.ps1은 127·128라운드, windows_setup.ps1은 296라운드, 복구온_예약실행_등록.ps1은 292라운드가 이미 정밀조사). 이 스크립트는 서버 재기동마다 바뀌는 임시 퀵터널 주소를 구매한 고정 도메인(예: bokguon.com)으로 바꾸는 일회성 설정 도구 — 지금까지 이 프로젝트가 실제로 실행한 적은 없는 것으로 보이나(현재도 퀵터널 주소로 운영 중), 사용자가 실제 도메인을 구매하는 순간 실행될 코드라 다른 휴면 인프라 자동화(292라운드 manage.py cmd_install_scheduler와 같은 계열)와 같은 기준으로 감사 대상. 결함 2건. ① [심각] config.yml을 실행마다 Set-Content로 통째로 덮어쓰며 ingress에는 그때그때 넘긴 도메인 단 하나만 넣는다 — 두 번째 도메인을 추가하려고(예: app.bokguon.com 추가) 또는 오타를 고치려고 재실행하면 기존 도메인이 조용히 사라진다. Cloudflare DNS 레코드 자체는 그대로 남아있지만 config.yml의 ingress에 자리가 없어 요청이 맨 아래 catch-all(http_status:404)로 떨어지고, 이건 Cloudflare 엣지에서 즉시 응답되므로 origin(waitress)까지 요청이 오지 않아 서버 로그 어디에도 흔적이 안 남는다 — 외부접속_상시가동.ps1의 자가치유도 현재 추적 중인 단일 TunnelHost만 검사해 옛 도메인 장애를 구조적으로 못 본다. 기존 config.yml이 있으면 기존 hostname을 정규식으로 읽어 보존하고 새 도메인을 추가하도록 수정, 의도적으로 빼고 싶을 때만 쓰는 -Replace 스위치 신설. ② [심각] 터널 존재 확인이 이름 '포함'(-match [regex]::Escape($TunnelName), cloudflared tunnel list 텍스트 출력 전체에 대한 부분문자열 매치)이라 다른 터널 이름이 우연히 목표 이름을 부분문자열로 포함하면(예: 'my-bokguon-old-test'가 'bokguon'을 포함) '이미 있다'고 오판정해 생성 자체를 건너뛴다. 자격증명 파일 선택도 '가장 최근에 수정된 json'(Get-ChildItem *.json | Sort-Object LastWriteTime -Descending | Select -First 1)이라, 이 PC에 다른 터널의 자격증명이 남아있으면 방금 만든(또는 이미 있는) 목표 터널과 무관한 파일을 집어갈 수 있다 — 실측: 위 오판정 시나리오에서 실제로 무관한 터널의 자격증명 파일이 config.yml에 그대로 박힘. cloudflared 2026.7.2가 실제 지원하는 것을 --help로 직접 확인한 뒤 `tunnel list --name <정확한 이름> --output json`으로 교체 — 정확히 이름이 일치하는 터널만 찾고, 그 터널의 id로 자격증명 파일 경로(<id>.json)를 직접 지정(더는 mtime에 의존 안 함). 부수로(수정과 무관, 작성 과정에서 발견) 이 파일을 Write 도구로 재작성했을 때 UTF-8 BOM 없이 저장되어 Windows PowerShell 5.1이 cp949로 오독, 실제로 파싱 자체가 깨지는 것을 실행 중 확인 — BOM을 추가해 해결(원래 파일도 BOM이 없었을 가능성이 있어 이 자체가 별도의 잠재 결함이었을 수 있음, 확인은 못 했으나 안전하게 BOM 추가로 마무리). 회귀테스트는 실제 cloudflared.exe를 전혀 부르지 않고(로그인·터널 생성·DNS 변경은 브라우저 상호작용이 필요한 진짜 Cloudflare 계정 조작이라 실행 자체가 부적절) 이 테스트 파일 실행 시점에 만드는 가짜 스텁(.ps1, 파일 내 문자열로 내장 — 세션 종료 후에도 재현 가능)으로 실제 그 스크립트 파일 자체를 진짜 서브프로세스로 실행해 검증(모킹이 아니라 진짜 실행), -EnvFile로 임시 파일을 넘겨 운영 .env는 전혀 건드리지 않고, -SkipRestart로 감시자·cloudflared 프로세스 종료/재기동 단계를 건너뛰어 실제 운영 터널에 전혀 영향을 주지 않는다. 시나리오1(같은 터널로 도메인 3번 연속 실행 — 추가·보존·-Replace)과 시나리오2(부분일치하는 무관한 터널이 미리 있는 상태에서 목표 터널을 새로 만들어야 하는 경우) 각각 실제 실행으로 검증. 2곳(config.yml 병합 로직, 터널/자격증명 정확매치 로직) 각각 독립적으로 되돌려 결함 재현(각 되돌림에서 정확히 그 결함에 대응하는 체크만 깨지고 — 도메인소실 되돌림 시 1개, 정확매치 되돌림 시 3개 — 서로 영향을 안 주는 것까지 실측) 후 복원, 전체 11개 체크 재통과 확인 — 이 스크립트는 app.py가 import하지 않는 독립 운영 스크립트라 재기동 불필요·BUILD_HASH 불변(static/templates 아님). 사용자가 실제 도메인을 구매해 이 스크립트를 처음 실행할 때를 위한 사전 방어)"),
    ("test_scan_round323_fixes.py", "스캔 323라운드 회귀(deploy\\bokguon.service — Linux systemd 유닛, 현재는 미사용 대안 배포경로(실제 운영은 이 개발기에서 serve_waitress.py 직접 실행 중)의 네트워크 하드닝 주석이 실제로 안 하는 일을 한다고 주장하던 결함[경미~중간, 오인], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — round322에 이어 deploy/ 폴더 전체 20개 파일의 감사현황을 test_scan_round*.py 전수 재구성으로 재확인, backup_selfcheck.py(123·309·311)·bootstrap.sh(125·217·263·282·285·296·311 등)·복구온_외부공개_등록.ps1(126)·backup.sh(310)·일일백업.bat(311)·nginx_bokguon.conf(308)는 전부 이미 정밀조사됐음을 확인(클린 재확인, 정당한 결과) — 유일하게 bokguon.service만 311라운드가 바로 위 ReadWritePaths(쓰기경로 하드닝) 한 줄만 훑고 몇 줄 아래 네트워크 하드닝 블록은 어느 라운드도 안 건드린 부분조사 상태였음을 확인. 63~65행 주석 '로컬 소켓과 IPv4/IPv6 만... 외부 바인딩은 불필요'가 마치 이 두 줄이 아웃바운드를 막는 것처럼 읽히지만, systemd 공식문서(freedesktop.org systemd.resource-control(5), WebSearch로 직접 확인) 기준 실제로는 RestrictAddressFamilies가 소켓 프로토콜군(AF_INET 등 어떤 종류의 소켓을 만들 수 있는가)만 제한할 뿐 목적지 주소는 전혀 안 보고, IPAddressAllow=는 IPAddressDeny=any와 짝을 이뤄야만 화이트리스트로 동작하는데(공식문서 원문: 매칭 안 되는 트래픽은 'Otherwise, access is granted') 그 짝이 이 파일엔 없어 이 유닛엔 아웃바운드 IP 필터링이 전혀 걸려 있지 않다 — 보안 하드닝 블록 한가운데 있어 '이미 제한돼 있다'는 착각을 주기 쉽다. 이 파일은 현재 미사용 대안 배포경로(dormant, 292라운드 manage.py cmd_install_scheduler·322라운드 고정도메인_설정.ps1과 같은 계열 — 당장 안 쓰지만 나중에 실제 배포 시 쓰일 코드)라 지금 당장 뚫려있는 것은 아니지만, 실제로 아웃바운드를 제한하려면 IPAddressDeny=any 추가 + 팝빌 등 실제 호출 외부 API(notify_popbill.py) IP를 IPAddressAllow=에 명시해야 하는데 그 IP 목록 확정은 운영 판단이 필요하고 잘못 좁히면 알림 발송이 커널 단에서 조용히 끊기므로(애플리케이션 로그 없음) 이번 라운드는 실제 동작(지시문 자체) 변경 없이 주석을 사실대로 정정하는 데 그침(형식은 294/295/238라운드류 '문서가 실제와 다르면 문서를 실제에 맞춘다'와 같으나, 대상이 legal_docs.py류 법적문서가 아니라 보안설정 주석이라는 점이 다름). 이 파일은 systemd 유닛(텍스트 설정)이라 이 개발기(Windows, systemd 없음)에서 실행해 검증할 수 없다 — 회귀테스트는 (a) 오해를 유발하던 옛 문구가 사라졌는지, (b) 정정된 설명이 실제로 들어있는지, (c) 그 정정이 근거로 삼는 사실(파일에 IPAddressDeny 지시문이 실제로 없다 — 있었다면 설명이 달라져야 함)이 지금도 유효한지, (d) 원래 지시문 두 줄(RestrictAddressFamilies·IPAddressAllow)이 삭제사고 없이 그대로 있는지를 정적으로 확인(systemd 실행 자체가 이 환경에서 불가능해 real-execution 대신 공식문서를 근거로 삼은 정적검사 — 314/238라운드류 순수문서수정과 같은 검증한계). 주석 전체를 되돌려 결함 재현(되돌린 상태에서 정확히 주석 관련 4개 체크만 깨지고 지시문 보존 확인용 2개+사실유효성 확인용 1개는 회귀없이 통과) 후 복원 — app.py가 import 안 하는 독립 배포템플릿이라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round324_fixes.py", "스캔 324라운드 회귀(api_case_coords() — 사건 좌표 수동 입력·해제 결함 2건, 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — app.py 최상위 def/route 480개를 AST로 추출해 test_scan_round2~323 전체와 대조, 174개가 이름으로 개별 언급된 적 없음을 확인. 그중 도급관문 GET 4종·알림읽음 2종·하위계정 CRUD 10종·출동배차 상태머신(claim/arrive/assign)·OTP 2단계인증은 코드까지 직접 읽어 검증했으나 require_role/require_portal_owner의 계정생사확인·err_500 전역롤백망·CS_PHOTO 가드 등 기존 방어로 이미 안전함을 확인(클린, 정당한 결과). ① [중간] 사건 스코프 라우트 중 유일하게 UPDATE 전에 cases 행을 조회하지 않아, 존재하지 않는 cid 로 호출해도 UPDATE 0행 뒤 그대로 200/ok:true 를 반환해 운영자의 오타를 못 알아챈다. ② [중간] DB.log() 의 detail 을 f\"case {cid}\"(내부 숫자 PK, 예: \"case 123\")로 남겨, 사건별 감사이력을 찾는 유일한 통로인 case_history_report() 의 `detail LIKE '%'||case_no||'%'` + `_case_no_in_detail()` 경계검사(318라운드가 세운 관행 — 90여 곳 DB.log 호출부가 case_no 를 맨 앞에 두는 것과 같은 원리, app.py:9590·18080 등 실제 형제 호출부로 관행 재확인)와 애초에 형식이 달라 100% 매치 실패한다 — 318라운드의 \"부분열끼리 우연히 충돌\"과 달리 이쪽은 \"애초에 case_no 문자열 자체가 detail 에 아예 없어 무조건 못 찾음\"이라는 더 확실한 블라인드 스팟(전역 활동로그에는 남지만 그 사건의 분쟁 소명 리포트에는 영원히 안 나타남 — 발주처에게 그대로 건네질 수 있는 문서라는 이 리포트 자신의 철칙4와 맞물려 좌표 정정 이력이 통째로 누락될 수 있음). 함수 시작에 `SELECT case_no FROM cases WHERE id=?` 가드(없으면 404) 추가, 두 DB.log 호출의 detail 을 c['case_no'] 기반으로 형제와 통일. 회귀테스트는 실제 Flask test_client + 실제 CSRF 이중제출토큰(session['_csrf']+X-CSRF-Token 헤더, 101·102라운드가 세운 관행)으로 실제 POST 요청을 보내 (a) 존재하지 않는 cid 는 404, (b) 좌표 입력·해제 감사로그의 detail 이 실제 _case_no_in_detail() 경계검사를 통과, (c) 가장 중요하게 실제 /report/case/<id> 라우트를 호출해 두 로그가 그 사건의 리포트에 실제로 나타남을 실측(고치기 전엔 LIKE 필터에 형식 자체가 안 걸려 전혀 안 보였다). 1곳 되돌려 결함 재현(되돌린 상태에서 정확히 5개 체크만 깨지고 — 404가드·detail형식 2개·리포트노출 2개 — '조작 자체는 200으로 성공한다'는 3개는 회귀없이 그대로 통과) 후 복원 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이라 BUILD_HASH 불변 예상)"),
    ("test_scan_round325_fixes.py", "스캔 325라운드 회귀(api_admin_update() — 관리자 계정 등급/비밀번호/이름 수정, app.py:1656 — 이름 변경 분기만 감사로그가 없던 결함[중간], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 324라운드에 이어 app.py 480개를 다시 AST로 재구성, 이번엔 '가장 가까운 라운드 수정 주석까지의 줄 거리'로 감사밀도를 계산해 협력사·보험사·수수료 클러스터(라운드79~299로 이미 두텁게 검증)와 달리 관리자 계정 관리 클러스터(app.py 1612-1733행, api_admins_list/api_admin_create/api_admin_update/api_admin_delete/api_me_update)가 주변 144~186줄 안에 라운드 주석이 전무한 완전 미검증 구역임을 확인. 같은 함수 안 형제 두 분기(등급 변경=1678행, 비밀번호 재발급=1690행)는 각각 DB.log()를 남기는데 이름 변경 분기(1679~1680행)만 UPDATE 뒤 아무 흔적도 안 남겼다 — 완전히 동일한 동작(이름 수정)을 하는 자기계정용 쌍둥이 함수 api_me_update()(app.py:1722, '내 정보 수정')조차 DB.log를 남기는 것과도 대비됨. 최고관리자(또는 탈취된 세션)가 다른 관리자의 표시 이름을 바꿔도 activity_log에 무엇을 바꿨는지 전혀 안 남아(access_log엔 경로 호출 자체는 남지만 내용은 없음) 사칭·혼선 유도 후 추적이 불가능한 구조였다 — 함수명이 test_scan_round2~324 어디에도 없고 기능 자체는 200 ok로 정상 동작해 형제 로그 형식을 직접 대조해야만 보이는 침묵성 결함이라 지금까지 안 걸림. 형제와 같은 DB.log() 호출을 추가(대상 계정 username·이전 이름→새 이름을 detail에 남김, 등급변경 로그의 action(actor)+대상계정 관행과 통일). 회귀테스트는 실제 Flask test_client + CSRF 이중제출토큰(324라운드가 세운 관행)으로 실제 PATCH /api/admins/<id> 요청을 보내 (a) 다른 관리자 계정의 이름 변경 감사로그가 실제로 남고 대상계정·이전이름·새이름이 detail에 전부 들어감을 실측, (b) 형제 분기(등급 변경·비밀번호 재발급)는 회귀 없이 그대로 로그를 남김을 재확인. 1곳 되돌려 결함 재현(되돌린 상태에서 정확히 로그존재 확인 1개 체크만 깨지고 — 그에 종속된 detail내용 확인은 가드로 실행조차 안 됨 — 나머지 7개는 회귀없이 통과) 후 복원 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(324라운드에서 재확인한 대로 예측하지 말고 재기동 후 실측값을 그대로 볼 것). 부차 관찰(수정 안 함, 실무영향 낮음으로 판단): d['role']이 ADMIN_ROLES 밖 값이면 이 분기 전체가 조용히 스킵되지만 result={'ok':true}는 그대로 반환됨 — 화면이 고정 select라 정상 UI 경로로는 도달 불가, 수동 조작된 요청에서만 발현되는 무해한 API 견고성 격차라 이번 라운드는 손대지 않음)"),
    ("test_scan_round326_fixes.py", "스캔 326라운드 회귀(감사로그 화면·엑셀(/api/activity, /api/activity/export)이 관리자 계정 관리 정보를 등급 무관 노출하던 결함[중간, 접근통제 우회], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 320~325라운드가 이어온 app.py 함수단위 재구성 기법 3회차, '가장 가까운 라운드 주석까지의 최소거리'로 감사밀도를 재계산해 480개 중 최저밀도(317줄) 1위인 api_activity 를 선택. `GET /api/admins`(관리자 계정 목록)는 `@require_role('최고관리자')`로 엄격히 제한되는데 `GET /api/activity`·`GET /api/activity/export`는 등급검사 없는 `@require_admin`만 요구한다('하위관리자도 감사로그는 본다'는 의도된 설계 — 이 자체는 정당하고 안 바꿈). 그런데 관리자 계정 생성(app.py:1648)·등급변경(1680)·이름변경(1682, 325라운드 신설)·비밀번호재발급(1692)·삭제(1719)의 DB.log() detail 에 대상 계정의 아이디·이름·등급이 그대로 찍혀, 하위 등급 관리자가 /api/admins 에서는 403을 받으면서도 감사로그 화면·엑셀로 똑같은 정보를 우회해서 볼 수 있었다 — 실측: 중간관리자 세션으로 실제 재현(생성한 계정 'r326target (하위관리자) 몰래볼대상'이 detail 에 그대로 노출됨을 화면·엑셀 양쪽에서 확인). 회귀테스트 작성 중 에이전트 보고서의 부차 인용 하나(api_settings_set 이 19848행에 있다는 주장)를 grep으로 재확인 — 그 함수 자체는 실재하되 실제 위치는 19790~19791행(57줄 오차)이었다(★주의: 이 대조 과정에서 PowerShell Get-Content|Measure-Object -Line 이 이 파일의 총 줄수를 17,209줄로 잘못 보고한다는 것도 함께 발견 — Python readlines()·ripgrep 은 일관되게 19,997줄로 집계한다, cp949 오독류의 별개 버그로 추정. 처음엔 이 잘못된 17,209 수치 때문에 19848행이 파일 밖이라고 오판해 폐기했으나, 실제로는 그 함수가 존재하고 위치도 크게 안 틀렸다). 다만 이 부차 관찰 자체(SETTABLE 화이트리스트 도입 후 sweep_/job_ 접두어 차단이 도달불가 죽은코드)는 에이전트 스스로 '기능 문제는 없음'·'낮은 확신'으로 명시했으므로 이번 라운드의 수정 대상에서는 계속 제외(290라운드 원칙 — 핵심 주장 3곳의 줄번호는 전부 실측 일치했고, 부차 관찰은 위치는 대략 맞았지만 애초에 결함이 아니라고 에이전트 스스로 표시한 것이었다). 행 자체(시각·행위자·행위명)는 그대로 두고 이 5개 행위의 detail 만 최고관리자 미만에게 가리는 `_mask_admin_activity()` 공유 헬퍼를 신설해 화면(api_activity)·엑셀(api_activity_export) 양쪽에 적용 — '하위관리자도 감사로그는 본다'는 기존 원칙은 건드리지 않아 다른 90여 종 행위 로그는 회귀 없이 그대로 보인다. 회귀테스트는 실제 Flask test_client로 최고관리자 세션으로 실제 관리자 계정을 생성해 진짜 감사로그를 남긴 뒤, 중간관리자 세션으로 전환해 (a) 관리자 계정 생성 로그 행 자체는 보이되 detail 은 가려짐 (b) 무관한 대조군 로그(사건 등록)는 그대로 보임(회귀 없음) (c) 엑셀 내보내기도 화면과 동일하게 가려짐(openpyxl 로 실제 바이너리 파싱해 셀 값 확인) (d) 다시 최고관리자 세션으로 돌아가면 여전히 전부 그대로 보임(과잉차단 아님)을 전부 실측. 2곳(화면·엑셀 두 호출부) 되돌려 결함 재현(되돌린 상태에서 정확히 마스킹 관련 2개 체크만 깨지고 — 대조군 회귀없음 확인 2개, 최고관리자 회귀없음 확인 1개, 동작성공 확인 3개, 행존재 확인 1개는 전부 회귀없이 통과) 후 복원 — app.py 자신의 라우트+공유헬퍼 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round327_fixes.py", "스캔 327라운드 회귀(api_insurer_apikey_issue() — POST /api/insurers/<id>/apikey, app.py:8318 — 감사로그가 발급한 API 키의 실제 조각을 평문으로 남기던 결함[심각], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 326라운드가 세운 '등급게이트 화면 vs 그 감사로그 등급 불일치' 패턴을 다른 @require_role('최고관리자') 전용 함수 전체(협력사 계정정보·보험사 생성/수정·API키 발급/폐기/토글·웹훅 설정/테스트·AI임계값·정산이체/취소·실적재계산·견적기준·설정 등 12+개)에 적용해 검증, api_insurer_apikey_issue 하나만 실결함이고 나머지는 전부 클린(로그값이 이미 동일 등급 화면에서 노출 중이거나(예: login_id, 17488·18765행) 애초에 민감정보가 아니거나, webhook_secret·임시비밀번호는 grep 전수확인 결과 DB.log 호출부 어디에도 안 남음 — 정당한 결과). `_gen_api_key()`(app.py:1849)가 만드는 prefix 는 `API_KEY_PREFIX('bok_live_', 9자) + raw[9:16]` — 즉 secrets.token_urlsafe(32)로 만든 실제 무작위 키 앞 7글자(약 42비트)를 그대로 포함하는데, 발급 라우트(수정 전 8333행)가 이 prefix 를 DB.log() detail 에 `f\"{r['name']} ({prefix}…)\"`로 그대로 남겼다 — 형제 함수인 키 폐기(8349행)·연동토글(8367행)은 둘 다 기관명만 남기고 어떤 키 조각도 안 남기는데 발급 함수만 예외였다. 42비트 노출만으로 나머지 214비트를 브루트포스할 순 없어 즉각적인 키 탈취로 이어지진 않지만, `api_insurer_api_status`(app.py:8299, 같은 최고관리자 전용)조차 상태조회 응답에서 api_key_prefix 를 has_key 불리언으로 낮춰 최고관리자에게도 원문 prefix 를 평소엔 안 보여주는 것과 대비된다(주석 8296행: '키·계약 요율처럼 데이터 흐름을 여닫는 민감 조작이라 최고관리자 전용') — '이 키는 지금 한 번만 표시됩니다'라는 이 코드베이스 자신의 원칙(관리자 임시비밀번호도 같은 원칙으로 DB.log 엔 계정명만 남긴다, 324·325라운드 확인)을 감사로그(326라운드가 확인한 등급 무관 /api/activity·/api/activity/export)가 조용히 깨서, 최고관리자만 발급 응답에서 한 번 보게 설계된 값을 하위관리자도 감사로그를 통해 영구히 볼 수 있었다. 형제와 같은 형식(기관명만)으로 통일. 회귀테스트 작성 중 에이전트가 인용한 줄번호(1842·1849·1851·1852·8316~8337)를 grep으로 전부 정확히 재확인(326라운드의 PowerShell 줄수 오집계 교훈을 반영해 이번엔 처음부터 grep·Python만 사용). 회귀테스트는 실제 Flask test_client로 최고관리자 세션으로 실제 보험사를 만들고 진짜 API 키를 발급해(응답의 원문 키·prefix 정상 노출은 의도된 설계라 회귀 확인만) 그 prefix 안의 실제 무작위 조각(bok_live_ 뒤 7자)이 감사로그 detail 에 안 남음을 실측, 형제 함수(키 폐기)는 회귀 없이 기관명만 남김을 재확인. 1곳 되돌려 결함 재현(되돌린 상태에서 실제 로그에 'R327테스트보험 (bok_live_hxEYfKw…)' 같은 진짜 키 조각이 그대로 찍히는 것을 실측 — 정확히 그 2개 체크만 깨지고 나머지 6개는 회귀없이 통과) 후 복원 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round328_fixes.py", "스캔 328라운드 회귀(save_upload()(photo_ai.py:252) 가 HEIC 변환 뒤 크기를 다시 안 재서 '장당 8MB' 상한이 조용히 깨질 수 있던 결함[중간], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 326·327라운드의 '등급게이트 vs 감사로그' 패턴이 최고관리자 전용 함수 16개 전수로 소진되자 완전히 새 파일로 전환, dispatch.py 4형제·CSRF/rate-limit 클러스터는 URL/동작 기반 테스트로 이미 광범위 검증돼 있음을 재확인해 클린 처리(120개 파일 대조), docs/ 불변식(306라운드)도 재실행해 재확인. save_upload()(252~316행)는 원본 바이트를 딱 한 번(259~263행) MAX_FILE_BYTES(8MB)와 대조하는데, HEIC 업로드는 이후 _heic_to_jpeg() 가 새로 인코딩한 JPEG 로 data 가 통째로 바뀌고(276행) 이 새 바이트는 그 뒤 어디서도 상한과 다시 대조되지 않는다. _strip_exif() 의 정상 경로(jpg/webp 는 _save_within_budget, png 는 명시적 체크)는 자체적으로 8MB 를 지키지만, 조기 반환 3곳 — 해상도 과대(122~124행)·DecompressionBombError(126~131행)·재인코딩 중 일반 예외(176~179행) — 은 받은 data 를 상한 검사 없이 그대로 돌려준다. 직접 업로드된 jpg/png/webp 는 이 세 곳에 와도 이미 259~263행에서 검증된 원본 그대로라 안전하지만(독립검증 확인: 이 경로에선 data 가 재할당되지 않음), HEIC 는 이 세 곳에 오는 data 가 방금 새로 만든 재인코딩 결과라 한 번도 검증된 적이 없다 — 284라운드가 고친 '재인코딩하면 커질 수 있다'는 위험이 이 세 갈래엔 안 미쳤던 것. 에이전트의 정밀한 후속분석(앞의 두 갈래는 _heic_to_jpeg 자신(218~222행)이 같은 MAX_PIXELS 로 먼저 걸러 HEIC 경로에서는 이미 도달 불가, 실질 구멍은 세 번째 재인코딩 예외 갈래뿐)까지 코드로 직접 재확인. save_upload() 의 _strip_exif() 호출 직후 한 곳에서 len(data)>MAX_FILE_BYTES 를 다시 재는 것으로 수정 — 개별 갈래를 다 손보는 대신 이 세 갈래 전부와 향후 리팩터링에도 안전한 공유 지점 수정. 회귀테스트는 실제 HEIC 코덱(pillow_heif) 없이도 재현 가능하도록 MAX_PIXELS·MAX_FILE_BYTES 를 테스트 중에만 작게 낮추고(321라운드가 BOKGUON_SQLITE_BUSY_MS 를 낮춰 실제 락을 빨리 재현한 것과 같은 기법) _heic_to_jpeg() 를 '실제 Pillow 로 인코딩한 진짜 JPEG 바이트'를 돌려주는 대역으로 바꿔(HEIC 코덱 자체가 아니라 그 갈래 앞단 인터페이스만 대신함) 실제 save_upload() 전체 흐름을 그대로 실행해, 해상도 과대 갈래가 실제로 밟히고 그 결과가 상한을 넘으면 UploadError 로 거부되며 디스크에도 안 쓰임을 실측, 정상 크기 이미지는 회귀 없이 그대로 저장됨도 확인. 1곳 되돌려 결함 재현(되돌린 상태에서 실제로 상한(200바이트)을 넘는 694바이트 파일이 디스크에 그대로 쓰이는 것을 실측 — 정확히 그 3개 체크만 깨지고 정상경로 확인 1개는 회귀없이 통과) 후 복원 — photo_ai.py 는 app.py 62행이 import하므로 재기동 필요, static/templates 미변경이라 BUILD_HASH 는 불변 예상(app.py 자체는 안 바뀜 — 재기동 후 실측 확인))"),
    ("test_scan_round329_fixes.py", "스캔 329라운드 회귀(dispatch.py candidates()(156행) 가 순위 확장 여부를 '도달 가능한 후보 수'가 아니라 '찾은 후보 총수'로 판단하던 결함[심각], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 320~328라운드의 app.py 재구성·감사밀도·등급게이트 기법이 소진되자 다른 대형 모듈로 전환, repair_estimate.py 의 _validate/estimate·crypto_util.py 의 mask_account 도 함께 점검했으나 결함 없음(클린, 정당한 결과). 1순위(같은 지역+공종일치, 최대 500건 fetch) → 2순위(같은 지역, 253행) → 3순위(공종일치, 264행) 순으로 후보를 넓히는데, 2·3순위 진입 조건이 len(out)<lim(찾은 총원수)이었다. _add()(215행)는 계정도 휴대전화도 없는 도달불가(_reachable(), 188행 — 실측: 활성 파트너 399곳 중 계정1·휴대전화68뿐, ~17%) 업체까지 전부 out에 담는다 — _reachable() 자신의 독스트링이 이미 '빼는 게 아니라 뒤로 미는 것'이라 명시하는데도 '충분히 찾았는가' 판단은 이 도달가능성을 전혀 안 봤다. 그래서 인구밀집 지역·흔한 공종처럼 1순위 모집단이 lim(기본 20, dispatch_fanout 설정 — dispatch.py:92·94, open_dispatch()가 343행에서 이 값을 limit으로 넘김, 전부 grep 재확인) 이상이면 — 그중 도달 가능이 2~3곳뿐이어도 — 2·3순위가 아예 안 열리고, 더 넓은 지역·전국 공종일치에 있을 도달 가능 후보는 조회조차 안 된 채 도달불가 업체로 채워진 목록이 반환됐다. 277행의 '도달가능 우선 정렬'은 이미 모은 후보 안의 순서만 고칠 뿐 '더 찾아볼지' 판단 자체는 못 고쳤다 — 형제가 다른 함수가 아니라 같은 함수 안의 서로 다른 두 단계(모집 vs 정렬)라는 점이 94·95·117·190·318·324~328라운드류와 다르다. 253·264행의 len(out)을 sum(1 for x in out if x['reachable']) 로 교체. 회귀테스트는 실제 candidates() 를 그대로 호출해, 같은 지역·같은 공종 도달불가 25곳(1순위 모집단이 lim=20을 넘김)과 같은 지역·다른 공종 도달가능 1곳(2순위에만 걸림)을 실제 DB에 심어 도달가능 후보가 결과에 실제로 포함됨을 실측, 대조군(모집단<lim)은 회귀 없음도 확인. 2곳 되돌려 결함 재현(되돌린 상태에서 정확히 도달가능 후보 포함 체크 1개만 깨지고 대조군 1개는 회귀없이 통과) 후 복원. **부수 발견(회귀 아님, 사전 검증으로 발견)**: 기존 test_dispatch.py 의 [7] 복합공종 검사가 새로 심는 테스트 파트너를 전화·계정 둘 다 없이(도달불가) 만들어 뒀는데, 이 수정이 적용되면 정당하게 더 넓혀진 검색이 오래 누적된 verify.db 의 다른 진짜 도달가능 후보들을 더 많이 찾아내면서 그 도달불가 테스트 파트너가 limit=10 안에서 밀려나 그 검사 하나만 실패했다(이 검사의 실제 취지 — 복합 사건이 work_lots 로 개별 공종이 갈라져 매칭되는가 — 와는 무관한 우연한 충돌, 반대로 되돌리면 그 검사가 다시 통과함을 실측 확인해 인과관계 확정) — 그 테스트 파트너에 실제 휴대전화번호를 부여해(어차피 이 시스템이 찾으려는 건 진짜 연락 가능한 업체이므로 더 현실적인 픽스처) 해결, 3회 연속 재실행으로 안정성 확인 — dispatch.py 는 app.py가 import하므로 재기동 필요, static/templates 미변경이라 BUILD_HASH 불변 예상(재기동 후 실측 확인))"),
    ("test_scan_round330_fixes.py", "스캔 330라운드 회귀(api_case_award()(app.py:10615, POST /api/cases/<cid>/award, 관리자 대행 낙찰승인) 가 낙찰 사유(reason)를 무제한 길이로 감사로그에 저장하던 결함[중간], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — app.py 감사밀도 기법으로 481개 최상위 함수 중 '라운드' 언급 0회에 137줄로 최대 크기인 이 함수를 포착, geo.py·legal_docs.py+build_pages.py 배선(실측 재빌드 diff 0건)·compliance.py·crypto_util.py·check_tx_paths.py·partner_accounts.py·notify_popbill.py 도 함께 조사했으나 이미 견고해 결함 없음(클린, 정당한 결과). 같은 함수 안 형제 필드 insurer_instruction(_inst, 10629행, 대행 근거를 남기는 필수 입력)은 이미 [:300]으로 잘리는데, 몇 줄 뒤 reason(10688행, '최저가 아닌 입찰을 고를 때'만 요구되는 선택 입력)만 그 관례를 못 받아 그대로 감사로그(10744행)에 들어갔다 — 사실상 무제한(MAX_CONTENT_LENGTH 260MB, 사진업로드용, grep 재확인). 더 구체적으로는 형제 라우트 api_insurer_award()(4269행, 보험사가 직접 승인하는 경로)가 바로 이 문제로 196라운드에 reason[:300](4401행)을 이미 받았고 그 수정 옆 주석(4396행)이 '이 낙찰승인 경로만 빠져 있었다'고 적어 뒀는데 — 그 표현이 가리키던 '빠진 경로'가 관리자 대행 경로(api_case_award)에는 애초에 적용된 적이 없었다(같은 결함이 형제 함수에서 재발, 이 코드베이스 전체에 reason[:300] 관례가 최소 4곳(4177·4401·13232·19386행)에 더 있음을 grep으로 확인 — 94·95·117·190·318·324~329라운드류 '형제 중 하나만 방어가 빠졌다' 패턴의 또 다른 변종, 이번엔 형제가 같은 파일의 다른 라우트). 형제와 같은 [:300]을 적용. 회귀테스트는 196라운드의 검증기법(사건+경매+입찰 2건 실제 fixture)을 관리자 세션(CSRF 토큰 포함)으로 그대로 재현해, 실제 Flask test_client로 2000자 사유를 담아 최저가 아닌 업체를 낙찰승인한 뒤 감사로그에 원문이 그대로 안 들어가고 300자로 잘린 형태로만 남음을 실측. 1곳 되돌려 결함 재현(되돌린 상태에서 실제 로그에 2000자 원문이 그대로 찍히는 것까지 실측 — 정확히 그 1개 체크만 깨지고 나머지 3개는 회귀없이 통과) 후 복원. 부수로 이 등록 설명문 작성 중 329라운드 항목 자체에서 이미 있던 문자깨짐(U+FFFD 대체문자 1곳, '매칭'이 '매�간'으로 저장돼 있었음)을 python 스캔으로 발견해 정정 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round331_fixes.py", "스캔 331라운드 회귀(status_reason(협력사·보험사 상태변경·퇴출 사유) 필드 전체가 '저장 전 300자로 자르기' 관례에서 통째로 빠져 있던 결함[중간, 3곳], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 330라운드가 확립한 reason[:300] 관례를 grep으로 전수조사하되 이번엔 'reason'이 아닌 다른 이름의 자유텍스트 필드까지 넓혀서 찾음(94·95·117·190·318·324~330라운드류 '형제 하나만 빠짐' 패턴이 이번엔 필드 이름 자체가 처음부터 관례 검색망 밖에 있던 변종). ① _partner_update()(app.py:7889, PATCH /api/partners/<pid>)의 status_reason(7993행)이 무제한으로 partners.status_reason·activity_log·알림톡에 그대로 들어갔다. ② api_partner_delete()(app.py:8021, DELETE /api/partners/<pid>, 퇴출, @require_role('중간관리자'))는 사유를 이 코드베이스에서 유일하게 JSON body가 아닌 URL 쿼리스트링(request.args, 8030행)으로 받는데 여기도 무제한이었다. ③ api_insurer_update()(app.py:8230, PATCH /api/insurers/<iid>, @require_role('최고관리자'))는 더 미묘했다 — 8249행에서 만든 reason 변수는 길이검사(5자 이상)에만 쓰이고, 실제 저장(옛 8277행 부근)과 통지(옛 8288행 부근)는 그 변수를 안 쓰고 d.get('status_reason')을 각자 다시 읽어 길이제한이 단 한 번도 실제로 적용된 적이 없었다 — '자르는 코드는 있는데 그 결과를 아무도 안 쓰는' 죽은 방어(두 곳 다 같은 changed 플래그로 게이트돼 reason 변수가 항상 정의돼 있음을 코드 흐름으로 재확인 후 재사용으로 통일, 재조회 자체를 제거). 세 곳 다 118·196·330라운드가 세운 reason[:300] 관례를 적용. 회귀테스트는 실제 Flask test_client로 최고관리자 세션(CSRF 토큰 포함)으로 세 라우트 각각에 2000자 사유를 실제로 보내 DB 컬럼(partners.status_reason·insurers.status_reason)과 감사로그 양쪽에 원문이 그대로 안 들어가고 잘린 형태로만 남음을 실측(②는 URL 쿼리스트링으로 실제 전송, ③은 정상동작 확인용으로 상태변경 자체 성공도 함께 확인). 3곳 각각 독립적으로 되돌려 결함 재현(각 되돌림에서 정확히 그 부위의 체크만 깨지고 — ①되돌릴 때 2개, ②되돌릴 때 1개, ③되돌릴 때 1개 — 나머지는 전부 회귀없이 통과, 서로 전혀 간섭 안 함을 실측) 후 순서대로 복원 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round332_fixes.py", "스캔 332라운드 회귀(api_notice_create()(app.py:14372, POST /api/notices) 가 공지 제목·본문을 무제한 길이로 저장하던 결함[중간], 이 세션 사상 첫 정밀조사한 정밀조사 Agent가 발견 — 331라운드가 세운 '저장 전 자르기' 관례를 이번엔 reason류를 넘어 note/memo/comment/message/content/detail/instruction/feedback 계열 자유텍스트 필드 전체로 확대해 app.py·dispatch.py·compliance.py·db.py 스키마를 전수로 훑음: insurer_leads·partner_applications 의 message·note, defect_photos.note, change_orders.reason/note, field_agreements.note, schedule_events.memo, happy_calls.feedback, photos.reject_reason, dispatches.fail_reason(항상 내부 리터럴)은 전부 [:200~2000]으로 이미 정상 방어됨을 확인(클린, 정당한 결과) — compliance.py 의 override_reason 은 315라운드가 이미 '재조사 금지'로 정리한 별개 사안이라 제외. `@require_admin`(632행, 등급 무관 — 하위관리자도 그대로 통과)만 걸린 이 라우트는 title·body 를 그대로 INSERT INTO notices(14380행 옛 위치)와 DB.log(14383행 옛 위치)에 넣었는데, 같은 파일에 이미 확립된 'title 은 100~120자로 자른다' 관례(8892행 [:120], 13741·13774행 [:100])에서 이 라우트만 빠졌다 — 331라운드류 '필드 이름이 달라 검색망에 안 걸림'이 아니라 '이름도 관례도 형제와 완전히 같은데 이 라우트 하나만 적용을 깜빡함'이라는 또 다른 변종(94·95·117·190·318·324~331라운드류 '형제 하나만 방어가 빠짐' 계열의 다섯 번째 하위유형). 13772행 주석이 하자 접수(title·content)에서 이미 겪은 것과 토씨까지 같은 실패모드(무제한 저장 → DB 비대화)에 더해, GET /api/notices(14342행 옛 위치)가 SELECT * 를 LIMIT 없이 그대로 내려주므로 공지 하나가 부풀면 관리자·협력사·보험사 포털 전체가 대시보드를 열 때마다 그 큰 문자열을 매번 그대로 받는 자기유발 DoS 로 이어진다(클라이언트가 이스케이프해 렌더링하므로 XSS 는 아님). 형제와 같은 상한(title[:100]·body[:2000])을 적용, DB.log 도 잘린 title 변수를 재사용하도록 통일. 부차 관찰(수정 안 함, 다음 라운드 후보로 남김): api_campaign_create()(app.py 8894행 부근)의 text/body 필드도 형제 title(8892행 [:120])과 달리 길이제한이 없음을 검증 중 우연히 발견했으나 이번 라운드 Agent 조사 범위 밖이라 손대지 않음. 회귀테스트는 실제 Flask test_client 로 하위관리자 세션(@require_admin 의 등급무관 심각도를 그대로 증명하기 위해 의도적으로 최하위 등급 사용)이 실제 2000자 제목·5000자 본문으로 공지를 등록해 (a) 등록 자체는 정상 200/ok (b) notices.title·body 가 실제로 각각 100·2000자로 잘려 원문이 안 들어감 (c) activity_log.detail 에도 원문 제목이 안 남음을 DB 를 직접 조회해 실측, 나아가 (d) 실제 GET /api/notices 를 호출해 응답 JSON 에서도 잘린 값만 내려옴을 읽기 경로까지 실측(저장 시점에 이미 잘렸으므로 당연한 결과지만 실제 응답으로 재확인). 1곳 되돌려 결함 재현(되돌린 상태에서 정확히 title·body·감사로그·읽기경로 4개 체크만 깨지고 — 등록성공·행생성·목록조회성공 3개는 회귀없이 그대로 통과) 후 복원, 7/7 재통과 확인 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round333_fixes.py", "스캔 333라운드 회귀(api_campaign_create()(app.py:8887, POST /api/campaigns) 가 마케팅 캠페인 audience·filter_json 을 무제한 길이로 저장하던 결함[중간, 2건], round333 배경조사 Agent가 발견 — round332 자신이 notices 결함(title·body 무제한저장)을 검증하다 우연히 스친 뒤 범위 밖이라 미조치로 남긴 단서(test_scan_round332_fixes.py 상단 주석)를 이어받아 정밀조사, 독립검증으로 줄번호·소비자 전부 재확인. 같은 함수 안 형제 title[:120](8892행)·subject[:200](8893행)은 이미 잘리는데 body(8894행)·audience(옛 8941행)·filter_json(옛 8941행) 3곳이 전부 무제한이었다 — body 는 형제와 이름·관례가 완전히 같은 332류 '적용 자체를 깜빡함' 변종, audience·filter_json 은 한 걸음 더 나아가 filter_json 이 원본 요청 d 를 통째로(json.dumps(d)) 덤프해 이미 자른 title·subject·body 원문을 한 번 더 그대로 끼워 넣는 이중누출이었다. db.py 스키마 주석이 명시하는 filter_json 의 목적('수신자 산출 조건(재현용)')과 실제 유일한 소비자 _campaign_recipients()(app.py:8782)를 grep 으로 직접 대조해 그 함수가 실제로 읽는 건 channel/ptype/major/region/no_login 5개뿐이고 filter_json 자체는 어떤 코드도(admin.js 포함, grep 재확인) 프로그램적으로 다시 안 읽는 순수 기록용임을 확인 — 그래서 그 5개만 남기도록 축소해도 어떤 소비자도 안 깨진다. `GET /api/campaigns`(8874행, LIMIT 100)·`GET /api/campaigns/<id>`(8965행) 둘 다 `@require_admin`(등급 무관)이라 round332 의 notices 와 같은 구조의 자기유발 DoS 로 이어질 수 있었다(campaigns 는 삭제 라우트가 없고 취소(cancel)도 status 만 바꿔 body·filter_json 은 영구히 남는다, grep 재확인). 수정: body[:2000](형제 notices.body 와 같은 상한), audience[:200], filter_json 을 원본 d 대신 실제 소비 필드 5개만 담은 축소 dict 로 교체(major·region 각 [:120]). 회귀테스트는 실제 Flask test_client 로 중간관리자 세션(이 라우트의 실제 최소 등급 — require_role 이 _account_alive() 로 admins 표를 실제 조회하므로 db.py seed_demo() 가 만드는 'staff' 계정을 그대로 사용)이 audience 1000자·major/region 각 500자·body 5000자로 실제 캠페인을 등록해 (a) DB 컬럼(audience·filter_json·body) 전부 원문이 그대로 안 들어감 (b) filter_json 을 실제로 JSON 파싱해 키가 정확히 5개(channel/ptype/major/region/no_login)뿐이고 title·subject·body·audience 원문이 안 섞여 있음 (c) 실제 GET 목록·상세 응답에서도 잘린 값만 내려옴을 읽기 경로까지 실측(픽스처 설계상 major 는 SQL LIKE 사전필터·region 은 region_matches() 사후필터라 씨앗업체의 major·region 을 요청과 같은 긴 문자열로 맞춰야 NO_RECIPIENT 로 조기반환되지 않고 실제로 저장 결과를 확인할 수 있음, region_matches 의 '정규화 안 되면 원문 부분일치' 폴백을 이용). 1곳(body 캡+audience/filter_json 재구성, 같은 INSERT 문 하나에 걸친 하나의 일관된 수정이라 332라운드의 notices 처럼 통째로 되돌려 결함 재현 — 정확히 7개 체크만 깨지고 등록성공·행생성·HTTP 200 계열 6개는 회귀없이 통과) 후 복원, 13/13 재통과 확인 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round334_fixes.py", "스캔 334라운드 회귀(협력업체 입점신청 동의고지(static/form.js CONSENT_SPEC.partner)·공식 개인정보처리방침(legal_docs.py 제2조)이 실제로 수집·저장하는 3개 필드 — 업체 구분(partner_type)·세부 취급 품목(category)·대표 외 상시 인력 수(staff_count) — 를 빠뜨리고 있던 결함[중간], round334 배경조사 Agent가 발견 — 캠페인 생애주기(preview/create/detail/cancel) 재감사·round333 filter_json류 '원본dict 통째덤프' 형제사례(engine_inputs, 별개 성격이라 보류) 탐색 뒤 클린으로 판정하고 전환한 각도. form.js 자신의 52행 주석 '수집 항목은 실제 서버가 저장하는 컬럼과 일치해야 한다 — 바뀌면 legal_docs.py 도 함께 고칠 것'을 어긴 사례가 189라운드(기관 유형)·191라운드(사업장 주소)·192라운드(면허·등록업종)에 이어 이번이 네 번째 재발 — 앞의 세 라운드는 매번 그때 눈에 띈 필드 하나씩만 고치고 전체 목록을 다시 훑지 않아, 이번처럼 한 라운드가 동시에 3개를 놓칠 수 있는 구조적 약점이 그대로 남아 있었다. 독립검증: partner_type 은 templates/apply_partner.html:21-24 필수 select(시행사/시공사) → app.py:5395 PARTNER_TYPES 화이트리스트 → 5397-5406 INSERT INTO partner_applications, category 는 같은 템플릿:49 선택 입력 → app.py FIELD_LIMITS[category] 로 길이제한 → 같은 INSERT, staff_count 는 같은 템플릿:62-64 필수 숫자 입력(288라운드가 '이 required 는 폼을 안 거치면 무의미하다 — 이 관문이 서버측 진짜 방어선'이라고 이미 확정한 그 필드) → app.py:5364 파싱, 5375 에서 1명 미만이면 SOLO 코드로 거부(1인사업자 정책) → 같은 INSERT — 셋 다 실제로 신청 접수 즉시 수집·저장되는 살아있는 필드임을 grep 으로 전부 재확인. legal_docs.py 제2조 '협력업체 입점 신청' 행(옛 155~156행)과 form.js CONSENT_SPEC.partner.items(옛 62행) 어디에도 이 3개가 없어, 신청자가 동의 화면에서 이 항목들이 수집된다는 사실을 한 번도 못 보고 동의 체크박스를 눌렀다(개인정보 보호법 §15①1·§22, 처리방침 정확성은 §30). partner_type·staff_count 는 폼에서 required 라 필수 항목으로, category 는 선택 입력이라 선택 항목으로 두 파일 모두에 추가. app.py:2173 의 `/legal/<key>` 라우트가 legal_docs.PRIVACY 를 매 요청마다 그대로 렌더링하므로 그쪽은 재기동만 하면 즉시 반영되고, 별도의 GitHub Pages 정적사본(docs/legal/privacy.html, build_pages.py:217 이 LEGAL.DOCS 를 순회하며 생성 — round306 확립)은 이번 라운드가 build_pages.py 를 직접 재실행해 새 문구가 실제로 들어갔음을 grep 으로 재확인. 회귀테스트는 191·192라운드와 같은 순수 소스텍스트 대조 방식(이 결함 자체가 코드 로직이 아니라 두 문서 사이의 서술 불일치라 real-execution 대신 정적검사가 적절, 238·314라운드류와 같은 검증한계) — CONSENT_SPEC.partner 블록·legal_docs.py 필수/선택 행 양쪽에 3개 문구가 실제로 들어갔는지, 대조군으로 무관한 '보험사 도입 문의' 행이 오염 안 됐는지, 참고용으로 세 필드가 실제 템플릿·app.py 저장경로에 살아있는지까지 확인. 2곳(legal_docs.py 표, form.js CONSENT_SPEC) 함께 되돌려 결함 재현(되돌린 상태에서 정확히 문구 관련 5개 체크만 깨지고 — 대조군 1개+참고용 4개는 회귀없이 통과) 후 복원, 10/10 재통과 확인 — legal_docs.py 는 app.py 가 import하는 모듈의 사용자 노출 문구 변경이라 재기동 필요, static/form.js 도 함께 바뀌어 static/** 를 포함하는 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round337_fixes.py", "스캔 337라운드 회귀(admin.js 정산·하자·출동수배 3개 화면의 처리버튼이 등급 무관하게 그려지던 결함[중간, UX/권한위생 — 서버는 이미 차단, 폼을 다 채운 뒤에야 403], admin.js 화면군 Agent 조사로 발견 — 246~253라운드가 설정·가견적기준/표준단가·도입문의/입점신청·사건관리·온보딩/면허조사·발송함/캠페인·변경주문·보험사관리 8개 화면을 전수로 게이트했는데 정산(settle) 화면 자체를 안 훑고 지나갔고, 하자(defects)·출동수배(dispatch) 는 205라운드가 이미 정확히 이 결함을 주석으로 지목(try/catch 는 붙였지만 등급게이트는 못 붙임)해 뒀는데도 세 라운드(74·242·307)의 후속 수정이 전부 무관한 버그만 고치고 이 지적 자체는 끝내 처리 안 된 채 남아 있었다. ① VIEWS.settle 의 settleAction() — 버튼 6개(입금확인·더블체크승인·되돌리기=중간관리자 app.py 12529·13409·13297행, 정산취소·이체완료=최고관리자 13211·12625행)가 등급 무관. coActions()(252라운드)와 달리 버튼별 필요등급이 2/3으로 갈려 함수 전체를 한 번에 막을 수 없어 등급을 한 번만 읽어 버튼마다 개별로 확인하도록 설계(rank>=2/rank>=3 개별 삼항). 일괄 입금확인 바·체크박스열(payable/paybar, /api/settlements/paid-bulk=중간관리자, app.py 12568행)도 같은 사유로 canBulk 새로 게이트. ② defectDetail() 모달 하단 처리버튼 5개(확인중·재시공배정·완료·반려·완료취소) — PATCH /api/defects/<id> 는 require_role(중간관리자, app.py:13846)인데 이 화면 메뉴가 applyRoleMenus() 의 등급게이트(admins·insurers·settle 등만 제한)에 없어 하위관리자도 열 수 있었다. ③ VIEWS.dispatch 의 '기한 점검 실행'(dispatchSweep) 버튼 — POST /api/admin/dispatch-sweep 는 require_role(중간관리자, app.py:16978)인데 등급 무관, 과기한 건이 있으면 강조색(btn p)까지 입혀 하위관리자에게도 클릭을 권했다. 세 곳 다 목록조회 API 는 require_admin(등급무관)이라 화면 자체는 계속 보이는 게 맞고 처리 버튼만 형제(coActions)처럼 자격 없으면 조용히 안내문/숨김으로 바뀌게 수정 — 서버측 인가는 이미 전부 정확해 권한상승은 아니고, '폼을 다 채운 뒤에야 403'이라는 시간낭비를 없애는 UX/권한위생 수정(247·249~253라운드류와 같은 성격). 회귀테스트는 252라운드가 세운 Node.js 원본함수 추출 실행 기법을 그대로 따르되, settleAction() 은 버튼별 필요등급이 갈리는 첫 사례라 4개 정산단계 × 3개등급 × 5개액션(20조합) 진리표를 직접 재현해 실측(하위관리자는 어느 단계에서도 처리버튼을 전혀 못 봄·최고관리자는 단계별 주버튼을 과잉차단 없이 정상적으로 봄 양쪽 다 확인), defectDetail() 은 openModal·statusPill·document·window 를 스텁해 원본 함수 전체를 그대로 실행, dispatchSweep 버튼은 그 한 줄만 원본 그대로 추출해 실행 — 세 곳 모두 실제 렌더링 결과(HTML 문자열)를 실측했지 소스텍스트 존재만 확인한 게 아니다. 3곳 각각 독립적으로 되돌려 결함 재현(settleAction 되돌릴 때 정확히 그 13개 조합 체크만 깨지고 canBulk·defectDetail·dispatchSweep 은 회귀없이 통과, defectDetail 되돌릴 때 정확히 rank=1 4개 체크만 깨지고 나머지는 회귀없이 통과, dispatchSweep 되돌릴 때는 그 게이트 표현 자체가 소스에서 사라져 테스트 자신의 추출 로직이 ValueError 로 곧바로 죽는 것으로 결함 재현 확인 — 코드가 없으면 조용히 통과가 아니라 확실하게 죽는다는 이 캠페인의 기존 원칙과 같은 방향) 후 순서대로 복원, 93/93 재통과 확인 — static/admin.js 만 변경, app.py·templates·db.py 미변경이지만 static/** 를 포함하는 BUILD_HASH 로테이션 예상(app.py 자체 변경이 없어 재기동 필요성은 static 파일 내용을 실제 서비스에 반영하기 위함 — 예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round339_fixes.py", "스캔 339라운드 회귀(admin.js 6곳 — AI 사진검수·달력·공지·협력사·메모위젯·계정잠금해제 — 처리버튼이 등급 무관하게 그려지던 결함[중간, UX/권한위생 — 서버는 이미 차단], admin.js VIEWS.* 화면군 Agent 조사로 발견 — 246~253·337라운드가 훑은 화면들 다음으로 32개 VIEWS.* 정의를 전수 대조해 아직 안 훑은 18개 화면을 찾아냈고, 그중 6곳에서 이 패턴을 확인. ① VIEWS.photos(openPhotoReview) — 반려·반려취소(app.py 12241·12218행)·삭제(12091행)·전체검수승인(12041행) 4개 버튼 전부 require_role(중간관리자)인데 12034·12213행 주석이 이미 '재현확인: 하위관리자 세션으로 200'·'하위관리자가 중간관리자의 검수 판단을 일방적으로 무효화'라고 두 번이나 지목한 결함이 화면엔 한 번도 안 들어왔다 — 정산의 필수 관문이라 여섯 중 가장 위험(분류 select 는 12040행 주석대로 등급무관 유지). ② VIEWS.calendar(calDay) 의 일정삭제 — DELETE /api/schedule-events(17825행, 68라운드가 하위관리자에서 올림). ③ VIEWS.notices 의 공지삭제 — DELETE /api/notices(14412행). ④ VIEWS.partners(partnerForm) 의 협력사 퇴출 — DELETE /api/partners(8023행), askStatusReason() 프롬프트를 다 채운 뒤에야 403을 만나는 전형적 시간낭비형. ⑤ 공유위젯 loadMemos() 의 메모삭제 — DELETE /api/memos(1472행), 이 위젯을 쓰는 모든 상세화면(사건상세 등)에 공통 적용되는 결함이라 이 한 곳만 고치면 전부 해결(memoDone/PATCH 는 require_admin 이라 그대로 둠). ⑥ VIEWS.selfcheck 의 계정 잠금해제 — POST /api/login-attempts/unlock(2390행), 이번엔 버튼만 지우는 걸로 안 끝난다는 걸 직접 실측 확인 — 입력칸의 data-act-enter='unlockLogin'(actions.js, Enter 키로도 같은 핸들러를 부름)이 버튼과 별개로 살아있어 버튼만 숨기면 입력 후 Enter 로 그대로 우회되므로 입력칸까지 함께 등급 분기 안에 넣었다(337라운드까지의 다섯 사례엔 없던 새로운 우회경로, 이번 조사로 처음 확인). 여섯 곳 모두 목록조회 API 는 require_admin(등급무관)이라 화면 자체는 계속 보이는 게 맞고 처리 버튼만 형제(coActions·settleAction, 252·337라운드)처럼 자격 없으면 조용히 숨김/안내문으로 바뀌게 수정 — 서버측 인가는 이미 전부 정확해 권한상승은 아니다. 회귀테스트는 정적 소스대조(여섯 곳 게이트 존재+대조군으로 memoDone 등 등급무관 액션은 회귀없이 그대로 노출됨) + Node 실행(공지삭제 3단계 등급별 렌더링, 잠금해제 패널의 버튼·입력칸 Enter우회 통로 둘 다 등급별로 실제 어떻게 그려지는지) 둘 다 실측 — 이번 라운드 시작 전 337라운드 교훈대로 이 6개 함수를 직접 Node vm/subprocess 로 실행하는 다른 테스트가 있는지 먼저 grep 확인(test_scan_round27_fixes.py 는 unlockLogin 을 정적 문자열 존재확인만 하고 test_scan_round290_fixes.py 는 loadMemos 를 no-op 스텁으로 완전히 대체해 실제 함수 본문을 안 써 — 둘 다 이번 수정과 충돌 없음을 확인 후 진행). 6곳을 한 번에 되돌려 결함 재현(정확히 소스대조 8개 체크만 깨지고 — 백엔드 사전조건 8개+memoDone 대조군 1개는 회귀없이 통과 — 마지막 체크는 되돌린 코드에 그 문자열 자체가 없어 테스트 자신의 추출 로직이 IndexError 로 곧바로 죽는 것으로 결함 재현 확인, 337라운드의 dispatchSweep 되돌림과 같은 성격) 후 한 번에 복원, 27/27 재통과 확인 — static/admin.js 만 변경, app.py·templates·db.py 미변경이지만 static/** 포함 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round340_fixes.py", "스캔 340라운드 회귀(admin.js partnerForm() 의 신규 협력사 상태(select#p_status) 기본값이 배열 첫 항목('활성')에 암묵 의존하던 결함[중간, UX/권한위생], 339라운드 조사 Agent가 낮은 확신으로 남긴 관찰('+ 업체 등록' 버튼의 상태 드롭다운 기본값이 '심사중'이 아니라 '활성'이라 하위관리자가 기본값을 그대로 두면 POST /api/partners(app.py:7713-7716, 197라운드 관문)가 403을 낸다)를 이 세션이 직접 소스로 재확인 — <select id=\"p_status\"> 옵션이 `p.status===s` 로만 selected 를 매겨, 신규 등록(p={}, p.status===undefined)에서는 네 옵션 어디에도 selected 가 안 붙어 브라우저가 배열 순서상 첫 항목('활성')을 기본 표시했다(337·339라운드의 '버튼이 등급 무관하게 그려진다'와는 다른 하위유형 — 이번엔 기본 선택값 자체가 등급과 안 맞음). 바로 위 형제 필드 lc_status(1460행)가 이미 쓰는 `(p.license_status||'미확인')===s` 패턴을 그대로 재사용해 신규 등록 시 기본값이 백엔드 기본값(심사중)과 일치하도록 1472행 단일 지점 수정, 기존 업체 수정은 p.status 가 항상 실값이라 동작 변화 없음. 회귀테스트는 이 함수를 직접 실행하는 다른 테스트가 있는지 먼저 grep(round240·339 둘 다 순수 정적 텍스트 추출/대조뿐 Node 실행 없음을 확인)한 뒤 Node vm 으로 partnerForm() 을 신규(id=0)·기존(status=경고)·기존(status=활성) 세 경우 모두 직접 실행해 렌더된 select 의 selected 위치를 실측 — 신규는 심사중이 기본 선택되고 기존 두 경우는 저장된 실값이 그대로 유지됨을 확인. 1곳 되돌려 결함 재현(되돌린 상태에서 신규 등록 시 selected 가 아예 0개로 실측됨 — 소스대조 2개+실행체크 1개 정확히 3곳만 깨지고 기존수정 2개+옵션목록 불변 1개는 회귀없이 통과) 후 복원, 6/6 재통과 확인 — static/admin.js 만 변경, app.py·templates·db.py 미변경이지만 static/** 포함 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round342_fixes.py", "스캔 342라운드 회귀(manage.py cmd_restore() 가 shutil.copy2() 호출 자체가 예외를 던지면(디스크 꽉 참 등) 처리하지 않던 결함[경미, 실패경험 품질 — 데이터 유실 위험은 아님], manage.py 20개 서브커맨드 중 run_all_tests.py 어디에도 이름으로 언급된 적 없는 12개(cmd_backup·cmd_restore·cmd_reset_pw·cmd_create_admin·cmd_create_insurer 등, cmd_check·cmd_install_scheduler·cmd_go_live·cmd_prune_personal 등은 이미 다른 라운드가 다룸)를 grep 대조로 찾은 뒤 데이터안전·보안 최우선인 backup/restore/reset_pw 축으로 조사 Agent를 보내 발견 — 그 Agent의 1차 보고('shutil.copy2 가 조용히 실패해 손상된 DB가 서비스에 노출될 수 있다')는 독립검증 결과 과장이었다: 처리 안 된 예외는 프로세스를 트레이스백과 함께 크래시시키므로 오히려 요란하며, DB.DB_PATH 는 copy2 가 예외를 던지면 아무것도 안 쓴 채라 그대로 무사하고, 복사 전 이미 사전백업(keep, 1386~1405행, sqlite3 온라인 백업 API로 WAL까지 포함해 안전하게 뜸)까지 있어 실제 데이터 유실 경로는 아니었다(이전 조사 Agent가 run_all_tests.py 를 불충분히 검색해 이미 round303이 정밀조사한 smoke_test.py를 '유일한 미감사 후보'로 잘못 짚은 사고도 이번 라운드가 직접 재검증으로 걸러냄). 실제 결함은 더 좁다 — 20줄 아래 무결성검사 실패 분기(round66이 이미 만들어 둔 안전장치)는 실패 시 'keep 에서 되돌리는 법'을 안내하는데, copy2 자신이 예외를 던지는 갈래만 그 안내 없이 raw 트레이스백으로 죽어 이미 안전하게 떠 있는 keep 의 존재를 운영자가 그 순간엔 알 길이 없었다(1334행 cmd_restore 는 round292 조사에서 '이미 두텁게 방어됨'으로 클린 판정됐었지만 그 조사가 못 본 각도). shutil.copy2 호출만 try/except OSError 로 감싸고, 무결성검사 실패 분기가 쓰던 keep 안내 문구를 공유 헬퍼(_keep_hint)로 뽑아 양쪽이 재사용하도록 통일 — 새 안내를 만들지 않고 이미 있던 것을 재사용. 사전 grep 으로 cmd_restore 를 실제로 실행하는 기존 테스트(test_scan_round66_fixes.py, shutil.copy2 를 '예외 없이 깨진 내용을 쓰는' 대역으로 바꿔 무결성검사 실패 경로를 재현 — 이번 수정의 try/except 와는 겹치지 않는 별개 실패 지점)를 확인, 회귀테스트 자체가 그 파일을 서브프로세스로 재실행해 여전히 통과함을 실측. 회귀테스트는 실제 manage.cmd_restore() 를 shutil.copy2 가 진짜 OSError 를 던지는 상황으로 호출해 (a) 예외가 안 새고 1을 반환 (b) 실패 메시지에 원인이 남음 (c) keep 안내가 이 경로에서도 나옴 (d) keep 사본이 실제로 디스크에 남아 무결성까지 정상임(안내가 헛말이 아님)을 실측, 대조군(copy2 정상)은 회귀 없이 그대로 성공 확인. 1곳 되돌려 결함 재현(되돌린 상태에서 정확히 소스대조 3개+실행블록 전체가 테스트 자신의 except 로 잡힌 원인불명 크래시 형태로 깨지고 — round66 재실행 확인 1개는 회귀없이 통과, 이 크래시 자체가 '처리 안 된 예외가 그대로 샌다'는 결함의 실측 증거) 후 복원, 10/10 재통과 확인 — manage.py 는 app.py 가 import 하지 않는 독립 CLI 도구라 재기동 불필요·BUILD_HASH 불변(예측 말고 재기동 없이도 실측 확인 가능))"),
    ("test_scan_round348_fixes.py", "스캔 348라운드 회귀(api_campaign_create()(app.py:8887, POST /api/campaigns) 의 251라운드 중복방지가 BEGIN IMMEDIATE 밖에서 확인해 거의 동시에 도착한 요청끼리는 여전히 같은 캠페인이 여러 건 생기던 TOCTOU 결함[중간, 데이터정합성·미래 이중발송 위험], 200라운드 이후 신규기능(campaigns·change_orders·field_agreements·schedule_events 등)의 동시성을 90·94·117·190라운드가 다진 낙찰·정산 계열과 대조하는 조사 Agent가 발견 — 함께 지목된 api_schedule_event_add()(17784행) 의 '트랜잭션 없음'은 독립검증 결과 오판으로 제외(check-then-act 가 아니라 단순 단일 INSERT이고, 한 사건에 여러 일정이 생기는 건 캘린더 기능의 정상 동작이라 애초에 막을 대상이 아님). api_campaign_create() 는 이미 251라운드가 '30초 이내 같은 제목·채널 캠페인이 있으면 새로 안 만들고 그 캠페인을 그대로 돌려준다'는 중복방지를 넣어 뒀는데(SELECT 로 확인), 그 확인이 BEGIN IMMEDIATE 락 밖에 있어 SQLite 의 일반 SELECT 는 아무 락도 안 잡으므로, 두 요청이 서로의 커밋 전에 그 SELECT 를 둘 다 지나가면 둘 다 '중복 없음'으로 판단한다 — 그 뒤 BEGIN IMMEDIATE 가 둘을 직렬화하긴 해도 이미 둘 다 '새로 만들어도 된다'고 확정한 뒤라 각자 INSERT 해 버린다. 사람이 손으로 두 번 나눠 누르는 간격(수백ms 이상, 251라운드가 실제로 검증한 시나리오)에서는 둘째 클릭의 SELECT 가 첫째의 커밋을 보게 되어 막히지만, 더블클릭이 두 HTTP 요청을 밀리초 단위로 붙여 보내는 경우엔 못 막는다 — 형태는 251라운드가 이미 세운 방어와 똑같은데 '언제 확인하느냐'가 미묘하게 안전하지 않았던, 이 캠페인의 '형제 하나만 방어가 빠짐'류와는 다른 새 하위유형('방어는 있는데 락 순서가 안 맞음', 낙찰·정산 등 원래 기능이 94·117·190라운드에서 이미 확립한 'BEGIN IMMEDIATE 뒤에 재확인' 원칙이 이 신규 기능엔 아직 안 퍼져 있었던 것). 중복확인 SELECT 를 BEGIN IMMEDIATE 뒤로 옮기고, 중복 발견 시 이제 열려 있는 트랜잭션을 rollback 으로 정리하도록 수정(그냥 close 만 하면 트랜잭션이 붕 뜬 채 남는다). 회귀테스트는 실제 Flask app.test_client() 5개를 각자 독립 세션으로 인증시켜 완전히 동일한 캠페인을 동시에 POST — 처음엔 요청 시작 지점에만 threading.Barrier 를 뒀더니 실제 위험구간(SELECT~BEGIN IMMEDIATE 사이 몇 줄)이 GIL 전환 간격보다도 좁아 자연스러운 스레드 스케줄링으로는 재현이 안 됐다(되돌린 코드로도 통과) — DB.get_db() 가 돌려주는 연결을 감싸는 프록시(이 코드베이스가 이미 다른 라운드에서 쓴 기법)로 **그 중복확인 SQL을 실행하는 순간에만** Barrier(5) 를 심어, 5개 스레드가 전부 '아직 아무도 안 만들었다'를 보고 나서야 각자 진행하도록 강제해 실전과 동일한 결과를 100% 결정론적으로 재현했다(배리어 타임아웃은 db.py 의 PRAGMA busy_timeout(8000ms)보다 반드시 짧게 잡아야 한다 — 처음에 10초로 뒀더니 고친 코드에서 락을 기다리던 나머지 스레드들이 이 배리어보다 먼저 'database is locked' 로 죽어 500 이 섞여 나오는 자기 테스트의 부작용을 겪은 뒤 1초로 정정, 이는 테스트 자신의 설계결함이었지 실제 결함이 아니었음을 직접 확인). 되돌린 코드로는 실제로 5건 전부 '새로 생성'으로 응답하고 DB에도 정확히 5건이 만들어짐을 실측(고친 코드는 정확히 1건만 생성, 나머지 4건은 그 1건을 가리키는 duplicate:true 응답), 대조군(제목이 다른 두 캠페인은 동시에 와도 각자 독립 생성)도 과잉차단이 아님을 확인, 기존 251·333라운드의 이 함수 테스트도 회귀 없이 그대로 통과함을 재확인. 소스대조 1개+실행체크 2개 정확히 3곳만 되돌리기로 깨지고 나머지 7개(무응답 없음·200 응답·수신자 스냅샷·대조군 등)는 회귀없이 통과 확인 후 복원, 10/10 재통과 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round357_fixes.py", "스캔 357라운드 회귀(deploy/windows_setup.ps1 이 manage.py sweep 예약 등록을 아예 안 하던 결함[중간, 신규 배포 시 서비스가 반쯤 죽은 채로 뜸 — 이 PC 자체는 별도 수동조치로 이미 정상], 배포문서-실제코드 드리프트 조사 Agent가 발견 — bootstrap.sh(리눅스, 276행)는 sweep 을 직접 cron 등록하는데 그 옆 주석(275행)이 '윈도 배포는 복구온_예약실행_등록.ps1 이 같은 일을 한다'고 적어 뒀지만, DEPLOY.md 가 안내하는 윈도의 '메인' 설치 스크립트(windows_setup.ps1)는 그 별도 스크립트를 부르는 단계 자체가 없었다 — sweep 이 없으면 입찰 자동마감·출동 기한만료·완료보고 독촉·문자/알림톡 실발송이 전부 멈추는데(그 별도 스크립트 자신의 6~15행이 이미 이 사고를 실제로 겪었다고 기록), windows_setup.ps1 하나만 보고 새 윈도 서버에 처음 배포하면 이 사고가 그대로 재현된다(manage.py check 는 통과해도 서비스는 반쯤 죽는다). 조사 Agent가 함께 지목한 '환경변수 명명 불일치'(BOKGUON_HOST/PORT vs BOKGUON_BIND)는 독립검증 결과 오판으로 제외 — windows_setup.ps1 자신의 5~6행이 이미 '윈도 전용, 리눅스는 bootstrap.sh 를 쓴다'고 명시하고 실제로 윈도는 serve_waitress.py(BOKGUON_HOST/PORT 를 읽음)·리눅스는 gunicorn_conf.py(BOKGUON_BIND 를 읽음)로 서로 다른 WSGI 서버를 쓰므로 각 스크립트가 자기 플랫폼의 서버가 읽는 변수를 정확히 맞춘 것이 옳다(두 스크립트를 뒤섞어 쓰는 시나리오 자체가 성립하지 않음). 또한 이 조사 Agent가 '즉시 서비스 마비 가능'이라 표현한 심각도도 이 PC 자체에는 해당 안 됨을 직접 실측으로 확인 — `schtasks /Query`로 이 PC에 이미 '복구온_경매마감'(pythonw.exe manage.py sweep, 5분마다, Status=Ready)이 실제로 돌고 있음을 확인해, '서비스가 현재 마비돼 있다'는 프레이밍은 342·351·354라운드류의 메커니즘 과장이었고 실제 결함은 '이 설치 스크립트 자체(향후 신규/재해복구 배포)가 그 등록을 보장하지 않는다'는 더 좁은 범위임을 재확정. 고침: windows_setup.ps1 안에 스케줄 등록 로직을 새로 베끼지 않고(이미 잘 만들어진 복구온_예약실행_등록.ps1 의 중복작업 감지(.bat 내용까지 검사, 126라운드)·등록 후 실제 조회 확인(외부공개_등록.ps1 이 겪은 사고 재발 방지) 로직과 따로 노는 두 번째 구현이 생기는 것을 피함 — 처음엔 실제로 이렇게 직접 베껴 넣었다가 형제 스크립트(복구온_예약실행_등록.ps1)의 존재와 완성도를 뒤늦게 확인하고 그 시도 자체를 되돌렸다) 그 스크립트를 그대로 호출하는 한 줄(및 try/catch)만 추가 — 단일 관문 원칙 유지. 실패해도(예: 이 PC처럼 '복구온_경매마감'이 이미 돌고 있어 그 스크립트 자신의 중복감지로 정확히 실패하는 경우) 경고로만 낮춰 나머지 설치 단계를 막지 않는다. 회귀테스트는 PowerShell 을 실행하지 않고(292라운드가 이미 경고한 대로 실제 스케줄러 API 를 테스트에서 부르지 않음) 순수 정적 텍스트 대조로 검증 — & 호출연산자로 실제 실행하는지, try/catch 로 감쌌는지, 파일존재 확인이 있는지, 기존 4개 작업(백업·사진백업·접속기록·개인정보파기) 등록이 회귀 없이 그대로인지, bootstrap.sh·실제 호출 대상 파일 사이 이름이 정확히 일치하는지(오타로 엉뚱한 파일을 부르지 않는지)까지 교차확인. 되돌리기 1회로 결함 재현(정확히 호출 관련 4개 체크만 깨지고 대조군 8개는 회귀없이 통과) 후 복원, 12/12 재통과 — 이 파일은 app.py 가 import 하지 않는 배포 스크립트라 재기동·BUILD_HASH 와 무관(Z동기화는 해당 시 반영))"),
    ("test_scan_round359_fixes.py", "스캔 359라운드 회귀(api_case_cancel_award()(app.py:19358, POST /api/cases/<cid>/cancel-award, 낙찰취소) 가 형제 자식표(field_agreements·bids·change_orders·auctions·est_outcome·협력사 실적캐시)는 전부 꼼꼼히 정리하면서 defects(하자) 만 빠뜨리던 결함[중간, 데이터정합성 — 배정해제된 옛 업체를 가리키는 하자가 재공고 뒤에도 남음], 하자 상태전이 조사 Agent가 발견 — 그 구체적 재현(api_insurer_case_cancel, 4158행, 발주처 자체취소)은 직접 확인 결과 성립 불가능이었다: 그 라우트는 status in('접수','입찰중')(4186행)일 때만 허용되는데 하자는 실무상 업체가 배정돼 시공이 진행/완료된 뒤에야 생기므로 두 조건이 한 사건에서 동시에 성립할 수 없다(에이전트의 위협모델 재구성 오류, 341류와 같은 계열). 대신 직접 코드를 따라가 더 현실적인 자리를 찾음 — api_case_cancel_award()(19358행, status in('시공중','완료보고지연') 대상)는 실제로 시공이 진행/완료된 단계에서 동작하고, api_defect_create()(13707행)는 case.status 를 전혀 안 봐서(실측 확인) 그 단계에서 하자 접수 자체를 막지 않는다 — 특히 '완료보고지연'(시공은 끝났는데 보고만 밀린 상태)에서 보험사가 현장을 보고 하자를 접수하는 그림은 실제로 가능하다. 그 상태에서 낙찰이 취소되면(부도·잠적 등) 열린 하자 행이 배정해제된 옛 업체를 가리킨 채 남고, 사건은 재공고돼 전혀 다른 업체가 낙찰될 수 있다 — 새 업체는 자기가 안 한 일의 하자를 떠안을 근거가 없고 그 하자를 누가 처리할지는 사람의 판단 영역이라 코드가 임의로 정할 수 없다. 고침: 하자를 지우거나 상태를 억지로 바꾸지 않고, 같은 함수가 이미 정산·변경견적에 쓰는 것과 똑같은 방식(존재하면 조용히 진행시키지 않고 명확한 사유와 함께 차단)으로 세 번째 관문을 추가 — DEFECT_CLOSED_STATES(13525행, 이미 여러 곳에서 재사용되는 기존 상수)를 그대로 재사용해 열린 하자가 있으면 먼저 완료·반려로 정리하게 한다. 회귀테스트는 실제 Flask app.test_client() 로 '완료보고지연' 사건에 열린 하자를 심어 낙찰취소가 409/DEFECT_ACTIVE 로 막히는지, 차단 시 사건 상태·배정이 전혀 안 바뀌는지(부분변경 없음), 그 하자를 완료 처리한 뒤 재시도하면 정상 진행되는지(과잉차단 아님), 하자가 아예 없는 대조군 사건은 처음부터 안 막히는지 실측 — 기존 cancel_award 테스트(91·103·134·139·192)도 서브프로세스로 재실행해 전부 회귀 없이 통과함을 확인(다섯 다 defects 를 안 다루는 테스트라 이번 수정과 안 겹침). 되돌리기 1회로 결함 재현(소스대조가 존재하지 않는 문자열을 찾다 ValueError 로 곧바로 죽는 것으로 결함 재현 확인 — 337·339·342라운드류의 '요란한 크래시 = 부재의 증거'와 같은 성격) 후 복원, 12/12 재통과 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round364_fixes.py", "스캔 364라운드 회귀(_resync_partner_stats()·api_recount_partner_stats()(app.py:14975·15003, 협력사 win_rate·jobs_done 실적캐시 재계산)의 win_rate 분모(경매 입찰 사건 수, bids/auctions 조인)가 무효화된 입찰(voided_at IS NOT NULL)을 걸러내지 않던 결함[경미~중간, 데이터정합성 — 승률 캐시가 실제보다 낮게 저장됨], 협력사 실적통계 계산 로직 정밀조사 Agent가 발견 — 전체재경매 유찰(10153행)·추가분 유찰(19342행)·낙찰취소(19483~87행)·유찰확정(19633행) 네 자리 모두 그 순간 무효해진 입찰을 지우지 않고 voided_at 만 찍어 남기는데(입찰 이력은 소명자료라 지우지 않는다는 낙찰취소 블록 자신의 주석), 이후 '지금 유효한 입찰'만 가리는 화면·집계는 전부 voided_at IS NULL 을 붙인다(app.py 안에 33곳 — 4141·4193·4300·9806 등) — 그런데 win_rate 분모를 세는 이 두 함수의 SQL만 그 조건이 없어, 한번 무효화된 입찰의 경매까지 '경쟁한 경매'로 계속 세어 승률이 실제보다 낮게 나왔다. ⚠ 조사 Agent의 최초 보고는 이 결함을 app.py:10530 하자율 점수식(s_def=1-dcnt/jobs)과 엮어 '낙찰 순위에 영향'이라 했으나, 직접 코드를 읽어 확인한 결과 그 식의 분모는 win_rate 가 아니라 jobs_done(cases 테이블만으로 계산 — bids/auctions 를 전혀 참조하지 않는다)이라 이번 결함과 무관했고, win_rate 자체는 app.py·static/*.js·templates/* 전수 grep 결과 어디서도 읽히지 않는 — 쓰기만 되고 아무도 안 읽는 캐시값이었다(342·351·354·357라운드류의 메커니즘 과장과 같은 계열이지만 이번엔 '조용한 실패'가 아니라 '파급범위' 쪽이 과장된 사례 — 그래도 캐시값 자체가 틀린 채 저장되는 것은 독립적으로 고칠 가치가 있어 진행). 고침: 131·132라운드가 세운 '한쪽 공식을 고치면 다른 쪽도 같이 고쳐라' 원칙대로 두 함수의 win_rate 분모 서브쿼리에 동일하게 AND b.voided_at IS NULL 을 추가. 회귀테스트는 _resync_partner_stats() 를 exec 격리 실행 — 업체1이 경매1건 승·경매1건 패(둘 다 유효)+재공고로 무효화된 옛 입찰 1건을 갖는 시나리오에서 정답 50%(1승/2유효경매)가 나오는지, 무효화된 입찰이 없는 대조군은 회귀없이 종전과 동일한지 실측. 이 수정으로 함수 소스에 b.voided_at 참조가 새로 생기면서, 이 함수를 각자 자기만의 최소 인메모리 bids 스키마로 exec 격리 실행하던 기존 131·132·133라운드 테스트 3개가 'no such column: b.voided_at' 로 깨지는 것을 실행 확인 — 세 스키마 모두 voided_at TEXT 컬럼 1개만 추가(운영 스키마와 맞춤, 기존 검증 로직·assert 는 무변경). 되돌리기 1회로 결함 재현(정확히 예측한 33.3 값이 그대로 나옴, 대조군은 회귀없이 그대로 통과) 후 복원, 131·132·139(및 133) 기존 테스트까지 포함해 전부 재통과 — app.py 자신의 UPDATE 문 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round365_fixes.py", "스캔 365라운드 회귀(_bid_weights()(app.py:10480, 입찰 다속성 점수 가중치 로더)가 설정값에 무한대 문자열('inf')이 들어오면 그대로 받아들여 전체 가중치를 NaN으로 오염시키던 결함[경미, 방어적 정합성], 입찰 점수 가중치 설정 정밀조사 Agent가 발견 — Python float()이 'inf'/'Infinity'/'-inf' 문자열을 관용적으로 파싱하는데(표준 동작), 기존 검사 v>=0 은 음수만 걸러 float('inf')>=0=True 를 통과시켰고, 그 뒤 정규화(total=sum(w.values()), v/total)에서 다른 유효 키들은 finite/inf=0.0으로 죽고 inf를 받은 키 자신은 inf/inf=nan이 됐다(IEEE754 부정형) — 이 nan이 _bid_scores()(10496행)의 점수합산에 그대로 번진다. ⚠ 조사 Agent는 위협모델을 실측으로 정확히 확인해 스스로 한계를 밝혔다(8번째 관찰 '파급범위과장'류가 아닌 좋은 사례) — 이 설정키(bid_w_price 등 5개)는 /api/settings의 SETTABLE(19905행)에 아예 없어 정상 화면으로는 설정이 불가능하고 DB에도 값이 없음을 직접 확인, SQL 직접 접근(=이미 DB 파일 쓰기 권한을 가진 상태, award_amount 등을 직접 조작하는 것이 더 쉬운 수준의 접근권한)만이 유일한 경로라고 정직하게 보고 — 그래서 보안결함이 아니라 입력 파싱의 정합성 결함으로 분류. 그래도 이 함수 자신의 독스트링('설정값이 있으면 그것을... 합이 1이 되도록 정규화')이 언젠가 admin이 이 값을 바꿀 수 있게 될 것을 전제 하고 있어 그날을 위해 지금 고쳐 둠(현재 dormant한 설정경로에 대한 방어적 정합성 수정) — 음수·NaN문자열 자체(float('nan')>=0 이 이미 False)·-inf(마찬가지로 >=0 이 False)는 고치기 전에도 이미 안전했고 이번에 새로 막은 것은 양의 무한대뿐임을 대조군으로 확인. math 모듈을 새로 import하고 기존 조건에 and math.isfinite(v) 추가. 회귀테스트는 BID_WEIGHT_DEFAULT+_bid_weights()를 exec 격리 실행해 'inf' 주입 시 고치기 전엔 실제로 {price:nan, 나머지:0.0}이 나옴을 실측 재현, 고친 후엔 무효값이 무시되고 정확히 BID_WEIGHT_DEFAULT(5개 기본값의 합이 이미 1.00)로 떨어짐을 확인, 유효한 override(0.9)는 회귀 없이 정상 정규화됨을 확인, 이미 안전했던 음수·NaN문자열·-inf 세 대조군도 실행 확인. _bid_weights/_bid_scores를 참조하는 기존 4개 테스트(11·100·106·186)는 전부 정적 텍스트 대조뿐 exec 격리 실행이 없어(사전 grep 확인) 이번 math import 추가와 충돌 없음을 실행으로 재확인. 되돌리기 1회로 정확히 예측한 {price:nan, days:0.0, rating:0.0, region:0.0, defect:0.0} 재현 후 복원, 11·100·106·186 전부 재통과 — app.py 자신의 함수 변경 (모듈 top-level import 포함)이라 재기동 필요, static/templates 미변경 이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round372_fixes.py", "스캔 372라운드 회귀(공용 목록검색 헬퍼 _sq()/_sqp()(app.py:1545·1570)의 status_col 기본값('status')을, 실제로는 status 컬럼이 없는 테이블 대상 두 호출부(api_admins_list — admins 테이블, api_notices — notices 테이블)가 그대로 물려받아 ?status=아무값 쿼리스트링만 붙여도 sqlite3.OperationalError: no such column: status 로 죽던 결함[경미, 견고성 — 인증된 사용자가 URL만 바꿔도 500], 공개 리드폼·문의접수 스팸방어 정밀조사 Agent가 발견 — 1차 시도(agentId 기록 없음)는 실제 조사 없이 빈 상태메시지만 반환해 재시도, 2차 시도가 낸 보고(login/otp 길이제한 미비·notices 동적WHERE 감사필요) 중 login/otp 주장은 직접 코드 확인 결과 틀렸다(app.py:2531 code = (body().get('code') or '').strip()[:32] 로 이미 32자 절단 + 쿼리도 전부 파라미터바인딩이라 길이·인젝션 둘 다 무관). notices의 '동적 WHERE, 감사필요' 지적은 방향은 맞았으나 원인 특정을 안 했다 — 직접 search_filters()(1577행)를 끝까지 추적한 결과, status_col 이 참이고 요청에 ?status= 값이 있으면 무조건 WHERE {status_col}=? 를 붙이는데 admins·notices 테이블엔 애초에 그 컬럼이 없었다(db.py 스키마 직접대조: admins=id·username·password_hash·name·role·created_at, notices=id·title·body·audience·pinned·created_at, 둘 다 status 없음). 이 헬퍼를 부르는 8개 호출부 전수 대조(내가 처음 misuse 한 grep 패턴 '= _sq(' 는 인라인 호출 1곳(api_admins_list)을 놓쳤다가 재확인) 결과 이미 두 곳(standard_boq·est_check_band, 14459·15143행)은 status 컬럼이 없다는 걸 알고 status_col=None 을 명시해 뒀고, 나머지(insurers·campaigns·notifications·defects)는 실제로 그 컬럼이 있어 문제 없음(전부 db.py 로 대조 확인) — admins·notices 이 두 곳만 이미 확립된 관례를 놓쳤다. 고침: 두 호출부에 status_col=None 을 명시(공유 헬퍼 자체의 기본값은 다른 6곳이 정상 의존하므로 안 건드림). 회귀테스트는 실제 Flask app.test_client() 로 두 라우트에 ?status=아무값 을 붙여 고치기 전 500(또는 예외)이 실측되는지, 고친 뒤 200이 되는지, 파라미터 없는 호출·?q= 키워드검색 대조군은 회귀없이 그대로 동작하는지 실측 — search_filters/_sq/_sqp/api_admins_list/api_notices 를 참조하는 기존 7개 테스트(17·30·31·56·130·142·161)도 재실행해 전부 회귀 없이 통과 확인(전부 다른 함수·정적텍스트 대조라 이번 수정과 안 겹침). 되돌리기 1회로 정확히 예측한 500 두 건 재현 후 복원, 9/9 재통과 — app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round396_fixes.py", "스캔 396라운드 회귀(parse_days()(app.py:444)가 입찰 공기(공사기간) 입력값 하한으로 0을 허용하던 결함[경미, 데이터정합성 — 실제 공사가 0일 만에 끝난다는 물리적으로 불가능한 값이 저장·표시됨], 입찰 다속성 점수 조작 가능성 정밀조사 Agent가 발견 — 처음엔 '이 값으로 점수를 조작할 수 있다'는 우려로 지목됐으나, _bid_scores()(10496행)를 직접 대조한 결과 그건 아니었다 — s_days 계산(10511-12행) `d=b.get('days') or 0`에서 d=0은 falsy라 `(d and fast)`도 falsy가 되어 s_days=0.5(중립 기본값)로 떨어질 뿐, 점수를 인위적으로 올리는 경로는 아니다(조작 우려는 독립검증으로 기각). 다만 '공사가 0일 만에 끝난다'는 물리적으로 무의미한 값 자체는 실제로 저장·표시(화면엔 '공기 -일'로 깨져 보임)되므로 데이터 정합성 문제로는 진짜다 — parse_money()가 allow_zero 옵션으로 '0원이 유효한 경우'를 명시적으로 구분하는 것과 달리 parse_days()는 애초에 0이 유효할 이유가 없다(호출부 2곳(4856·5077행) 전부 '협력사가 약속하는 공사기간' 용도, 다른 의미로 쓰이는 자리 없음 — 전체파일 grep 재확인). 고침: 하한을 0에서 1로 올리고 오류 메시지도 '1~{MAX_DAYS}일'로 맞춤. 회귀테스트는 parse_days()를 exec 격리 실행해 0/1/365/366/-1 경계값 전부 실측 확인, 그리고 실제 Flask app.test_client()로 /api/partner/bids 에 days=0 투찰을 실제로 시도해 고치기 전엔 200으로 접수되던 것이 고친 뒤 400으로 거부됨을 실측 — 대조군 (days=5, 낮은 금액)은 회귀없이 정상 접수됨도 확인(첫 시도 실패 여부에 따라 되돌리기 상태에서 '입찰가 인하만 가능' 규칙과 충돌하지 않도록 대조군금액을 낮게 설계). parse_days를 참조하는 다른 테스트 없음(전체파일 grep 확인), test_compliance.py의 동명 매개변수(days=0, mkcase 함수)는 SQL로 created_at 시각만 보정하는 완전히 무관한 값임을 직접 코드로 확인. 되돌리기 1회로 정확히 예측한 400 거부 재현 후 복원, 9/9 재통과 — app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round405_fixes.py", "스캔 405라운드 회귀(test_b4_deadline.py 검사②가 sweep_auctions()(app.py:5546)의 전역 DB 스캔 결과(scanned==0)에 의존하던 결함[경미~중간, 테스트신뢰성 — 배터리가 357·359·372·396라운드 총 4번 '2연속실패 후 3차 클린'을 반복했다], 405라운드 디버깅 Agent가 실제 주입재현으로 근본원인 확정 — sweep_auctions()는 호출자 사건으로 범위를좁히지 않고 DB 전체의 마감지난 '진행' 경매를 스캔한다(운영에선 의도된정상설계, 고칠 대상 아님). test_b4_deadline.py는 이 전역 스캔결과가자기 시나리오에서 항상 0이라 가정했는데, 공유 verify.db에 다른테스트(test_scan_round5_fixes.py, 마감시각이 이미 지난 '진행' 경매를조건없이 만듦)가 남긴 고아 행이 하나라도 있으면 그 가정이 깨진다.그 고아 행이 남는 경로는 test_scan_round5_fixes.py의 _cleanup()이사건 하나의 DELETE 실패(락 경합 등)로 커밋 한 번 없이 전체가 조용히통째로 취소되는 구조였다(직접 코드확인 — 유일하게 안 감싸진 DELETEFROM bids 줄, 바깥 try/except Exception: pass 하나가 루프 전체를감쌈). 고침: ① test_b4_deadline.py 검사②를 '내 경매가 안 건드려졌다'로만 좁히고 '전역에 마감지난 경매가 없다'는 무관한 가정을 뺌(마감전이라는 시나리오와 무관한 전역불변식이었다). ② test_scan_round5_fixes.py의 _cleanup()을 사건별로 감싸 하나 실패해도 나머지는 계속지우고 즉시 커밋하게 함(부분성공을 남기고, 경고를 stderr로 남김).회귀테스트는 실제 sweep_auctions()를 호출해 고아 경매가 전역스캔에잡히면서도(옛 assert였다면 깨졌을 조건 직접 확인) 내 경매는 무해함을실측, test_b4_deadline.py를 오염된 스크래치 DB에 서브프로세스로통째 실행해 지금은 통과함을 확인, 그 다음 옛 assert로 코드를 임시되돌리고 새 고아를 하나 더 심어(⚠ 첫 실행의 sweep 호출 자체가 이미고아를 처리해 상태를 바꿔놔 재사용하면 옛 코드조차 통과해버리는함정을 실측으로 발견 — 자가치유 메커니즘의 실체가 바로 이것) 같은오염조건에서 실패가 정확히 재현됨을 실측(인과관계 직접증명), 이후원본 복원 후 재통과 확인. round5쪽 수정은 exec 격리로 _cleanup()함수만 추출해 case_a의 DELETE FROM bids만 실패하는 가짜 sqlite3락경합을 주입, case_a 실패에도 case_b는 정상 삭제됨을 실측(사건별격리 확인). app.py는 변경 없음(sweep_auctions()는 이미 올바른 설계로확정 — 정적 분석과 재현 둘 다로 검증) — 테스트 파일 2개만 수정이라운영서버 재기동·BUILD_HASH 확인 불필요(app.py가 이 두 test_*.py를import하지 않음, 실행경로 무관 확인))"),
    ("test_scan_round406_fixes.py", "스캔 406라운드 회귀(run_all_tests.py 가 공유 verify.db 를 UNIT 루프 시작 전에 명시적으로 초기화하지 않아, 목록에서 우연히 가장 먼저 `import app`하는 파일이 데모시드 여부를 공유 DB 전체에 떠넘기던 결함[중간~심각, 테스트신뢰성 — 스캔 28·29라운드가 배터리에서만 insurers=0 으로 매번 실패], 405라운드가 test_b4_deadline.py 플레이크를 고치는 검증 과정에서 전체 UNIT 배터리(--quick)를 재현하다 우연히 발견 — 406라운드가 먼저 조사했으나 그 보고의 리딩 가설(누군가 수동으로 manage.py go-live 를 그 스크래치 DB에 돌렸을 것)은 내가 실제로 쓴 명령을 직접 대조해 기각(그런 적 없음), env 전파도 run() 의 dict(os.environ) 로 이미 정상 확인, test_fresh_db.py 도 자기 전용 임시DB만 써서 무관함을 직접 확인. 이어 시도한 두 번째 가설(BOKGUON_ENV 가 명시 안 되면 manage.py 의 envload import 가 이 저장소의 진짜 .env(BOKGUON_ENV=prod)를 setdefault 로 읽어들여 조용히 운영모드가 된다는 것)도 run_all_tests.py 에 os.environ.setdefault('BOKGUON_ENV', 'dev') 를 넣어 직접 실측했으나 재현이 그대로 남아 기각 — 두 가설 모두 실측으로 반증한 뒤, run_all_tests.py 자신의 UNIT 리스트와 run() 함수를 그대로 재사용하는 정밀 진단 스크립트로 파일 단위 COUNT(insurers) 를 찍어 정확한 전환점을 실측 확정 — test_fresh_db.py·test_dead_actions.py 뒤에도 DB 파일 자체가 없다가 test_template_js.py 실행 직후 insurers=0 으로 떨어짐(파일은 생기되 시드는 안 됨). app.py 자신이 122행에서 무조건 DB.init_db() 를 부르는데, test_template_js.py 는 자기 검사(템플릿 인라인 JS 파싱)엔 데모데이터가 필요없어 `import app` 전에 BOKGUON_SEED_DEMO=0 을 setdefault 로 세팅해 둔다(44-45행) — 그 선택은 자기 프로세스에만 한정될 의도였지만, 공유 verify.db 를 최초로 만드는 역할을 UNIT 순서상 우연히 떠맡는 바람에 그 뒤로 도는 모든 UNIT 테스트가 보험사 하나도 없는 DB 를 물려받았다(같은 가정에 기대는 다른 UNIT 테스트가 grep 확인 결과 최소 9개 더 있어 파급범위가 28·29 두 개보다 넓을 수 있음도 함께 확인). 고침: run_all_tests.py 의 main() 에서 BOKGUON_DB_PATH 가 실제로 채워졌을 때만(quick 모드에서 사람이 그 값 자체를 안 줬으면 운영DB 오발을 새로 만들지 않기 위해 건너뜀 — db.py 의 test_ 전용 가드는 run_all_tests.py 자신은 안 잡아 주므로 이 조건이 안전장치), UNIT 루프 시작 전에 `DB.init_db(seed_demo=True)` 를 명시적으로 호출 — seed_demo 를 환경변수가 아니라 함수 인자로 강제하므로 어느 UNIT 파일이 우연히 '처음 여는 자'가 되든 그 파일 자신의 BOKGUON_ENV/BOKGUON_SEED_DEMO 선택과 무관하게 공유 DB 는 항상 씨드된 상태로 시작한다(db.py 의 admins==0 게이트 때문에 이후 재호출은 다시 지우거나 건너뛰지 않음). 회귀테스트는 실제 서브프로세스 실행으로 두 순서를 나란히 대조 — ①고친 순서(먼저 seed_demo=True 로 초기화 후 test_template_js.py 실행)는 그 파일이 SEED_DEMO=0 을 셋팅해도 insurers 가 그대로 6임을 실측 ②옛 순서(초기화 없이 test_template_js.py 를 최초 실행자로 둠)는 insurers=0 으로 정확히 재현됨을 실측 — 같은 파일, 같은 env 레시피로 오직 '먼저 초기화했는가'만 다르게 해 인과관계를 직접 증명. 이 라운드에서 나온 별도 관찰(연결 안 됨, 406라운드 원 보고): manage.py go-live 가 partners 는 명시적으로 보호하면서 insurers(DEMO_TABLES 소속, is_demo=1 전량)는 정리 후 '최소 1곳은 남았는지' 경고가 없다는 것 — 실제 데이터손실은 아니고 (is_demo=0인 진짜 계정은 안 건드림) 운영자 경험상의 누락이라 이번 라운드 범위에서는 제외, 407 이후 별도 판단 대상으로 남김. run_all_tests.py 자신은 app.py 가 import 하지 않는 독립 실행기라 재기동 불필요·BUILD_HASH 불변)"),
    ("test_scan_round409_fixes.py", "스캔 409라운드 회귀(api_contact_import()(엑셀 일괄등록, app.py:8632)의 MAX_IMPORT_ROWS(2000) 상한이 시트 XML의 <dimension> 태그(파일이 스스로 선언하는 메타데이터)에 의존해, 그 태그가 없는 파일로 완전히 우회되던 결함[중간, 가용성 — 라운드70이 세운 방어를 무력화], 파일업로드 폴리글랏/위조 각도 정밀조사 Agent가 발견 — n_rows=max((ws.max_row or 1)-1,0)(8663행)이 dimension 태그가 없으면 ws.max_row=None이 되어 n_rows=0으로 계산돼 상한검사를 무조건 통과하는데, 실제 처리루프(for row in ws.iter_rows(min_row=2):, 8677행)도 max_row 인자를 안 줘서 똑같이 None인 self.max_row에 기대(openpyxl 내부구현) 내부상한 없이 파일의 실제 행을 전부 스트리밍한다 — 가드와 처리루프가 같은 선언값을 함께 신뢰하는 게 아니라, 선언이 사라지면 가드는 0으로 처리는 무제한으로 서로 다르게 반응한다. 독립검증: 에이전트의 재현스크립트를 내 손으로 직접 재실행해 동일 결과(dimension 태그만 제거한 5000행 파일 → 가드는 0행으로 오판, 실제로는 5000행 전부 처리) 확인, .max_row 전체 10건 grep 재확인 결과 나머지 9곳은 전부 서버가 그 자리에서 만든 워크북을 append 직후 스타일링하는 용도(ws.append 뒤 ws[ws.max_row], 예 7065행)라 외부입력과 무관함을 직접 대조, 형제함수(api_partner_bulk_credentials, 7558행 ids[:300])는 실제 파싱된 리스트를 직접 슬라이싱해 이 문제가 없음도 확인. 라운드70의 자기 주석(8654-61행)이 이 상한을 만든 이유(BEGIN IMMEDIATE 가 파일 전체 처리 동안 열려있어 다른 모든 쓰기가 BUSY_TIMEOUT_MS(8초) 동안 막힘)를 직접 재확인, 사진업로드 경로(11360-64행, 사전검사는 파일저장 전 개수만 보고 실제 커밋 직전에 실제성공 개수로 다시 검사)가 이미 쓰는 원칙임을 확인해 그대로 이식 — 제품판단(스키마변경·UX설계·문턱계산)이 필요없는 형제패턴 이식 수준의 수정이라 407·408과 달리 바로 고침. 고침: 처리루프 안에서 실제로 센 행수(_real_rows)가 MAX_IMPORT_ROWS 를 넘으면 _row_limit_hit 를 세우고 즉시 break, 루프 뒤에서 rollback+400(기존 사전검사는 정직한 초과파일에 대한 빠른거부용 1차방어로 그대로 둠 — round70의 기존 회귀테스트가 이미 검증하는 부분이라 안 건드림). 회귀테스트는 실제 Flask test_client()로 dimension 태그를 제거한 2500행 위조파일을 실제 /api/contacts/import 에 POST — 고친 지금은 400으로 거부되고 partners 테이블에 실제로 아무 것도 반영 안 됨(롤백 확인)을 실측, 그 다음 코드를 옛(라운드70 시절, 실제카운트 없음) 형태로 되돌려 서브프로세스로 같은 위조파일을 다시 POST하면 200으로 통과해 2500건 전부 갱신됨을 실측(인과관계 직접증명) 후 원본 복원, 정상 소량파일(1행) 대조군은 회귀없이 그대로 동작함도 확인. round70의 기존 회귀테스트 15개도 재실행해 전부 회귀없이 통과 확인(사전검사·예외처리·인덱스 등다른 함수·다른 경로라 이번 수정과 안 겹침) — app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round410_fixes.py", "스캔 410라운드 회귀(발송대기 좀비 행 — sweep_send_notifications()의 마무리기록(status 확정 UPDATE)이 락 경합 등으로 실패하면 선-커밋된 attempts 증가만 살아남고 status='발송대기'로 영원히 남는 결함[중간, 신뢰성 — 자동스윕·[지금 보내기]·되돌리기 세 복구경로 전부 못 잡음], 크론/스케줄러 중첩 각도 정밀조사 Agent가 발견 — 라운드200 자신의 주석이 이 좀비 행을 되살리는 건 범위 밖이라 명시했던 자리를 410이 끝까지 추적. 독립검증: sweep_send_notifications 대상조회(6340-41행)의 send_attempts<3 조건이 only_ids 를 줘도 예외 없이 걸림을 직접 대조, api_outbox_reopen(옛 14858행)의 CAS가 status='수동처리'만 받아 발송대기인 좀비는 409 NOT_HANDLED 로 거부됨을 직접 확인, admin.js 되돌리기 버튼(옛 5625-26행)도 status==='수동처리' 일 때만 그려져 화면에서 복구경로 자체가 안 보임을 직접 확인, send_attempts 를 admin.js 전체에서 grep한 결과 0건이라 좀비 행이 정상 대기 건과 화면상 구분이 전혀 안 됨도 확인 — 3개 층(백엔드 스윕제외·백엔드 되돌리기게이트·프런트 버튼비노출) 전부 독립 재확인. 이미 검토·감사로그까지 갖춘 '되돌리기'(사람이 직접 눌러야만 일어나는 결정) 동작을 그대로 재사용해 닿는 범위만 넓히면 되므로(자동 재시도를 새로 만드는 게 아님, 라운드200이 우려한 중복발송 판단을 새로 내릴 필요가 없음) 제품판단 없이 바로 고칠 수 있는 결함으로 판단. 고침: ① api_outbox_reopen 의 CAS 조건에 (status='발송대기' AND send_attempts>=3) 케이스를 추가해 좀비 행도 받아줌(기존 '수동처리' 조건은 그대로 유지). ② admin.js에 같은 조건일 때 '재시도 소진' 경고문구+되돌리기 버튼을 노출. 회귀테스트(test_scan_round410_fixes.py)는 실제 Flask test_client()로 좀비 상태(status='발송대기', send_attempts=3)를 직접 재현해 ①스윕 대상조건(send_attempts<3)은 여전히 제외됨(고치지 않은 부분, 회귀아님)을 실측 ②되돌리기가 지금은 200으로 통과하고 send_attempts가 0으로 풀려 스윕 대상조건을 실제로 다시 만족함을 실측(완전 복구 확인) ③코드를 옛(라운드103 시절) CAS로 되돌려 서브프로세스로 같은 좀비를 재전송하면 409 NOT_HANDLED로 다시 막힘을 실측(인과관계 직접증명) 후 원본 복원 ④기존 '수동처리'→되돌리기 대조군은 send_attempts리셋+handled_note정리까지 회귀없이 그대로(round103의 기존 회귀테스트 16개도 재실행해 전부 통과 확인) ⑤admin.js 버튼조건은 정상대기(참거짓 실측)·좀비(참)·기존수동처리(참) 세 경우 전부 로직 대조로 검증 — app.py 자신의 라우트 변경이라 재기동 필요, static/templates(admin.js)도 함께 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round411_fixes.py", "스캔 411라운드 회귀(open_dispatch()(dispatch.py:288-415)의 알림 마무리기록(트랜잭션 밖, 398-414행)이 이 파일의 다른 모든 트랜잭션 블록과 달리 무방비였던 결함[심각, 신뢰성/가용성 — 락 경합 등으로 이 commit이 실패하면 예외가 함수 밖으로 새고, 커밋 안 된 암시적 트랜잭션이 커넥션에 남아 sweep_dispatches()의 다음 대상 BEGIN IMMEDIATE까지 깨뜨려 남은 대상 전부의 재수배를 멈추고, manage.py cmd_sweep()이 스윕들을 하나의 try로 묶어서(959-1001행) sweep_send_notifications·sweep_webhook_retries까지 그 회차 통째로 건너뛰게 만듦] + api_co_offer()(app.py:9808-9862, 이 코드베이스에서 사람 확인 없이 자동으로 낙찰자를 정하는 유일한 자리)의 최저가 조회(9825-29행)에 동점 처리 기준이 없던 결함[경미], 크론/스케줄러 중첩 각도 정밀조사 Agent가 발견 — 라운드200류와는 다른 새 사례. 독립검증: open_dispatch()의 본트랜잭션(302-390행)은 이미 try/except/rollback으로 방어됨을 직접 대조, 알림 마무리기록(407-414행)만 무방비였고 그 comment(411-13행) 자신이 '다음 스윕의 BEGIN IMMEDIATE가 죽는다'를 이미 예견하고도 commit()만 추가하고 안 막았음을 확인. sweep_dispatches()의 재수배 except(옛 825-833행)가 open_dispatch() 예외를 잡긴 하지만 rollback이 없어 다음 대상의 BEGIN IMMEDIATE(775행, try 블록 밖)가 깨짐을 확인, manage.py cmd_sweep()의 단일 try 구조(959-1001행)로 이게 다른 스윕까지 건너뛰게 만드는 캐스케이드도 직접 대조 확인. api_co_offer 동점처리는 이 코드베이스 전체의 'ORDER BY ...amount' 낙찰조회 6곳을 grep해 이 한 곳만 사람 확인 없는 자동선정(LIMIT 1)이고 나머지는 전부 사람이 목록에서 직접 고르는 표시용임을 확인해 영향범위를 정확히 좁힘. 고침: ① open_dispatch()의 마무리기록+commit을 이 파일의 다른 모든 자리처럼 try/except/rollback으로 감쌈. ② sweep_dispatches()의 재수배 except에도 rollback 추가(사람이 새로 판단할 위험 없음 — 이미 있는 지역 관례를 그대로 적용, 트랜잭션이 안 열려있어도 rollback()은 무해). ③ api_co_offer의 ORDER BY에 `, b.id ASC` 추가(먼저 낸 입찰이 동점을 이김). 회귀테스트는 실제 코드 실행으로 검증 — conn을 감싸는 결정론적 프록시로 '정확히 3번째 commit()'(대상1의 알림 마무리기록)만 실패시켜(진짜 파일락 경합은 sweep_dispatches() 호출 내내 잠금이 지속돼 무관한 자리까지 함께 실패해 재현조건을 흐린다는 것을 먼저 실측으로 확인하고 방향전환 — 자기 검증기법도 재검토한 사례) ①대상1 실패 에도 sweep_dispatches()가 예외 없이 정상 반환하고 ②대상2는 정상적으로 재수배(round=2)가 열림을 실측, 그 다음 두 수정(open_dispatch·sweep_dispatches)을 함께 되돌려 importlib.reload()로 같은 프로세스에서 재로드해 재현하면 실제로 예외가 밖으로 샘을 실측(인과관계 직접증명 — 처음엔 한쪽만 되돌려 재현이 안 됐다가, 두 수정이 서로 독립적으로도 캐스케이드를 막는다는 것을 직접 확인하고 둘 다 되돌리도록 수정) 후 원본 복원. api_co_offer는 실제 DB에 동일금액 입찰 2건(나중에 넣은 쪽이 더 큰 id)을 심어 쿼리가 결정론적으로 먼저 낸(id가 작은) 쪽을 고름을 실측. app.py + dispatch.py 둘 다 변경이라 재기동 필요, static/templates 미변경이라 BUILD_HASH 로테이션 예상(app.py 자체 변경 있음 — 예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round412_fixes.py", "스캔 412라운드 회귀(sweep_webhook_retries()(app.py:6137-6260)의 재시도상한 종결처리가 status='실패'로 굳은 경우만 다루고, write-back 실패로 status='대기'에 영구 박제되는 경로는 전혀 다루지 않던 결함[심각, 신뢰성 — 보험사 웹훅 통지가 감사기록도 알림도 없이 영구 소실될 수 있고 수동 복구 경로도 전혀 없음], 411라운드와 같은 클래스(형제는 다 하는데 한 곳만 빠짐) 정밀조사 Agent가 발견 — 410라운드가 '이론상 비슷한 좀비가 있을 수 있으나 도달조건이 훨씬 좁아 이번엔 재현 안 함'이라 명시적으로 남겨 둔 각도를 정면으로 파고들어 실제로 재현. 독립검증: _webhook_send()(1984-2019행)가 결과를 별도 커넥션(c2=DB.get_db())으로 쓰는데 그 write-back 실패를 2018-19행의 bare except가 로그 한 줄 없이 삼킴을 직접 확인, deliver_webhook()(2103행)이 활성 웹훅을 항상 status='대기'로 INSERT함을 확인, 종결처리(옛 6238·6242행)만 이 함수 안에서 이미 두 번(6197·6210행) 쓰인 status IN ('실패','대기') 관례를 안 따르고 '실패' 단독조건임을 직접 대조, webhook_deliveries 관련 라우트 전수(insurers/apikey/webhook/webhook-test)에 수동 복구 엔드포인트가 전혀 없음도 grep으로 확인. 고침: ① 종결처리 조건·UPDATE 둘 다 status IN ('실패','대기')로 넓힘(이 함수 안에 이미 있는 관례를 그대로 적용, 새 정책판단 없음). ② _webhook_send()의 write-back 실패도 app.logger.exception으로 최소한 로그는 남기게 함(진단 가능성 개선, 동작 위험 없음 — 이 자리 말고는 이 실패를 알 방법이 아예 없었음). 회귀테스트(test_scan_round412_fixes.py)는 실제 Flask 컨텍스트로 deliver_webhook() 호출 후 _webhook_send를 아무 것도 안 쓰는 가짜로 바꿔치기해 'write-back이 매번 조용히 실패'를 정확히 재현(선-기록 CAS는 write-back과 무관해 attempts는 정상적으로 5까지 오름을 실측) — 고친 지금은 5회 소진 뒤 status가 '포기'로 굳고 notifications·activity_log 둘 다 실제로 남음을 실측, 옛 조건(status=='실패' 단독)으로 되돌려 같은 시나리오를 재현하면 attempts=5인데도 status='대기'에 그대로 박제됨을 실측(인과관계 직접증명). [611라운드] 이 되돌리기는 원래 디스크의 진짜 app.py를 직접 덮어썼다가 subprocess로 재현 후 원복하는 방식이었으나, 이 저장소가 git 없이 동시세션이 상시전제라 그 창에 다른 세션이 같은 파일을 건드리면 충돌하는 위험이 있어, 함수 본문 문자열(sw_body)만 옛 조건으로 되돌려 exec(compile(...), A.__dict__)로 같은 프로세스·같은 conn에 즉석 재바인딩하는 방식(round604~610의 view_functions 딕셔너리 임시치환과 같은 발상)으로 교체 — 디스크의 진짜 app.py는 이제 전혀 안 건드리며 인과관계 증명 자체는 동일하게 유지(단독 재실행 13/13 통과 재확인). 검증 중 due조회(6185-88행)의 '대기' 분기가 delivered_at이 아니라 created_at 기준 10분 경과를 요구한다는 걸 처음엔 놓쳐 attempts가 0에 머무는 실패를 겪었다가 직접 원인을 추적해 바로잡음 (자기 재현기법도 재검토하라는 411라운드의 교훈을 바로 다음 라운드에 적용한 사례). 기존 test_scan_round144_fixes.py(이 종결처리를 처음 만든 라운드)의 소스검사 1곳도 옛 리터럴 SQL 문자열을 그대로 찾고 있어 이번 조건 확장과 충돌 — 그 라운드가 검증하려는 실제 행동(재시도 소진 시 '포기'로 못박는다)은 안 바뀌었고 실행기반 검사 9개는 전부 그대로 통과함을 확인한 뒤, 문자열 검사 1곳만 새 조건에 맞게 갱신(회귀 아님, 정당한 진화) — 갱신 후 10/10 재통과 확인. app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round413_fixes.py", "스캔 413라운드 회귀(api_login_otp()(app.py:2534-2600, 2단계 인증 코드대조)의 무차별대입 방어가 session['otp_tries'] 하나에만 의존해, 클라이언트가 최신 쿠키를 반영하지 않고 같은 쿠키를 계속 재전송하면 시도횟수가 영원히 '1번째'로 보이던 결함[심각, 인증우회 — 개인정보 안전성 확보조치 기준 §6④ 2단계인증의 무차별대입 방어가 사실상 무력화], 411·412와 같은 클래스(형제는 이미 쓰는 관례를 한 곳만 안 따름) 정밀조사 Agent가 발견 — 이 앱이 서버측 세션저장소 없이 Flask 기본 서명쿠키를 쓴다는 것(app.py:103-115, SESSION_TYPE 없음)을 직접 확인해 session 값이 클라이언트가 보낸 쿠키 그 자체임을 확정. /api/login 자신은 새 대기세션 발급 전에 이미 _recent_fails(login_attempts 테이블, (계정,IP) 스코프)로 재로그인을 통한 시도예산 리필을 막고 있음(2775행 부근, 주석 자신이 '코드 실패도 login_attempts를 같은 잠금창으로 공유해 새 대기 세션을 만들기 전에 막는다'고 명시)을 직접 대조 — 그런데 실제로 코드를 대조하는 자리인 api_login_otp() 자신에는 이 DB기반 체크가 없었다. 독립검증: Flask test_client()의 session_transaction()으로 매 시도 전 otp_tries 를 강제로 제거(비협조적 재전송 클라이언트를 이식성 있게 재현)해 실제 실행 — 고치기 전엔 12번 연속 401만 받고 429가 단 한 번도 안 뜨는 반면 DB login_attempts 에는 실패가 정상적으로 12건 누적됨(잠금 인프라 자체는 멀쩡, 이 라우트만 그걸 안 봄)을 실측 확인. 고침: /api/login과 완전히 동일한 _recent_fails/MAX_LOGIN_FAILS/LOCKOUT_MINUTES 조합을 api_login_otp() 진입부(session 카운터 증가보다 먼저)에 그대로 적용 — 새 정책·새 테이블·새 상수 불필요, 이미 있는 인프라를 다른 진입점에도 적용하는 것뿐이라 협조적 (정상) 사용자 체감은 전혀 안 바뀜. 회귀테스트(test_scan_round413_fixes.py)는 실제 Flask test_client()로 재전송 공격을 재현해 ①고친 지금은 세션쿠키를 12번 재전송해도 DB 누적 실패로 결국 429가 뜸(MAX_LOGIN_FAILS=5 이내로 제한됨) ②협조적 클라이언트는 정확히 OTP_MAX_TRIES(5)번의 401 뒤 429로 회귀없음 ③옛 코드로 되돌려 서브프로세스로 같은 재전송 공격을 재현하면 12번 내내 401만 받고 429가 한 번도 안 뜸(인과관계 직접증명)을 실측 후 원본 복원. app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round414_fixes.py", "스캔 414라운드 회귀(api_change_password()(app.py:1300-1344, 현재비밀번호 재확인)와 api_otp_disable()(app.py:2700-2717, 2단계인증 해제 비밀번호 재확인) 둘 다 로그인·OTP검증(413라운드)과 달리 무차별대입 방어(_recent_fails/_log_attempt)가 전혀 없던 결함[심각, 계정탈취 — change-password 는 특히 PW_CHANGE_ALLOW(app.py:980)가 임시비밀번호 강제세션에 열어 둔 유일한 API이자, GET /api/csrf(app.py:1238)가 무인증으로 토큰을 내줘 CSRF도 장벽이 안 됨 — 세션만 탈취한 공격자가 current 필드를 무제한 추측해 진짜 비밀번호를 알아낸 뒤 같은 요청의 new 필드로 계정을 완전히 탈취 가능], 413과 같은 클래스(형제는 이미 쓰는 관례를 한 곳만 안 따름) 3연속째 정밀조사 Agent가 발견 — DB.verify_pw( 호출 5곳(781·789·1322·2709·2747) 전수 대조로 나머지 3곳(781·789 는 _portal_authenticate() 헬퍼라 호출자인 협력사·보험사 로그인의 잠금이 감싸고 있음, 2747 은 api_login 자신)은 이미 보호돼 있고 이 2곳만 빠졌음을 직접 재확인. 고침: 로그인이 이미 쓰는 _recent_fails/_log_attempt/MAX_LOGIN_FAILS/LOCKOUT_MINUTES 인프라를 그대로 이식(새 정책 없음) — change-password 잠금키는 'PW:'+label(label 은 로그인 때 입력한 아이디 그 자체였음을 세션 대입 경로(app.py:2862·3059, 하위계정도 자기 로그인아이디가 들어감)까지 추적해 확정 — 조직 원계정 아이디와 헷갈리지 않게 직접 확인), otp-disable 잠금키는 'PWX:'+관리자아이디(겸사겸사 실패시 흔적이 전혀 없던 것도 DB.log 추가로 고침). 고치는 과정에서 부수적으로 드러난 세 번째 결함: 수동잠금해제 api_unlock_login()(app.py:2396-2430)이 스스로 라운드175 주석에 '새 창구가 생기면 이 목록만 늘린다'고 적어 둔 확장지점인데 새 창구 둘('PW:'·'PWX:')을 안 넣으면 운영자가 200(잠금해제 성공)을 받고도 이 두 창구는 그대로 잠긴 채 남는 거짓성공이 재발함을 직접 파악 — DELETE 문의 자리수(?,?,?,?)도 튜플 크기와 함께 6개로 맞춤(안 맞추면 sqlite3 파라미터 개수 불일치로 즉시 예외). 독립검증: 정밀조사 Agent 자신도 '정적 추적만 하고 실행 재현은 안 했다'고 명시적으로 밝힌 부분이라 실제 실행으로 직접 재검증 — Flask test_client() 로 관리자·협력사 하위계정 둘 다 브루트포스해 429 확인, 정상 비밀번호는 즉시 200(회귀없음), 수동잠금해제 뒤 실제로 재시도가 풀리는지까지 실측. 검증 중 자체 오류 하나 발견·수정: 하위계정 잠금해제 뒤 재시도가 여전히 429 로 나와 처음엔 고침이 안 먹은 줄 알았으나, change-password 자신에게 이미 있던 **별개의** IP 기준 레이트리밋(app.py:838, 10회/300초, 이 라운드가 손대지 않은 기존 코드)이 앞선 테스트 구간들의 누적 요청과 겹쳐 먼저 걸린 것이었음을 직접 디버그 스크립트로 격리해 확정(수동잠금해제 자체는 cleared:5·DB 직접조회로 실제로 깨끗이 지워짐을 확인) — 되돌리기 재현 스크립트도 같은 이유로 12회였던 시도횟수를 이 라우트 한정으로 9회(MAX_LOGIN_FAILS+4, 레이트리밋 10 밑)로 낮춤(otp-disable 은 전용 레이트리밋이 없어 12회 그대로 둬도 무방함을 대조 확인). 회귀테스트(test_scan_round414_fixes.py, 15개 검사)는 관리자·하위계정 각각의 브루트포스→429, 정상경로 회귀없음, 수동잠금해제의 실질적 해제, otp-disable의 429+감사로그 남김을 전부 실행 기반으로 확인하고, 세 수정 각각을 독립적으로 되돌려도 원래 결함이 각각 재현됨(옛 change-password·otp-disable 은 무제한 401만 반복, 옛 수동잠금해제는 200 성공을 주고도 PW: 잠금을 그대로 남김)을 서브프로세스 실행으로 직접증명 후 원본 복원. [611라운드] 이 되돌리기 3곳(7-1·7-2·7-3) 전부 원래 실제 on-disk app.py를 잠깐 덮어썼다가 subprocess로 재현 후 복원하는 옛 세대(round409~515대) 기법이었다 — round591이 이 중 7-3(round554가 이미 손댄 함수)만 그 창(write→subprocess.run→write 사이 동시 폴러가 관측 가능한 구간, round590이 전체배터리 중 실제로 관측)을 exec 재구성으로 없애고 7-1·7-2는 '별도 판단 필요'로 남겼는데, 이번 라운드가 그 뒤를 이어 7-1·7-2도 같은 기법(단, 여러 번 두드려야 해 A.app.view_functions 딕셔너리 항목 치환 방식 — round604~610 패턴)으로 옮겨 [7] 전체가 이제 디스크의 진짜 app.py를 전혀 안 쓴다(공유 finally 복원문도 함께 제거). 인과관계 증명 내용 자체는 그대로(단독 재실행 22/22 통과 재확인). 정밀조사 Agent 가 함께 보고한 나머지 각도(포털 데코레이터 즉시반영·가격경계·멀티탭 상태충돌)는 전부 직접 대조 결과 클린으로 확인. app.py 자신의 라우트 3개 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round415_fixes.py", "스캔 415라운드 회귀(sweep_auctions()(app.py, 마감경매 정리)와 형제 스윕 5종(sweep_no_bid_alert·sweep_report_overdue·sweep_warranty_expiry·sweep_approval_overdue·_sweep_award_approval) 의 루프 구간에 예외처리가 전무하던 결함[심각, 유령 상태전환 — 411~414에 이은 5연속째 '형제는 이미 쓰는 관례를 한 곳만 안 따름', 이번엔 앱 자신의 스윕함수 9종 중 6개가 한꺼번에], 정밀조사 Agent가 9종 스윕 전수 원문정독+실제 몽키패치 재현으로 발견 — sweep_auctions() 는 특히 심각: 루프 안 예외가 finally 의 _sweep_release() 자신의 무관한 UPDATE 커밋에 편승해, 실패한 타겟의 미완성 쓰기(cases.status='유찰' 등)까지 감사로그·알림 하나 없이 조용히 확정되고, 그 예외는 manage.py::cmd_sweep()/main() 까지 뚫고 나가(둘 다 except 없음, 직접 대조 확인) 예약 스케줄러 프로세스를 콘솔 없이 죽여 그 회차 나머지 스윕(웹훅 재시도 등)이 통째로 안 돈다. 독립검증: Agent가 스크래치패드에서만 실행하고 소스는 안 건드린 재현을 실제로 다시 실행해 직접 재확인 — sweep_auctions·sweep_dispatches·sweep_webhook_retries·sweep_send_notifications 전수 대조로 나머지 3개(sweep_dispatches는 411라운드, 웹훅재시도·발송은 84·144·200라운드에서 이미 하드닝됨)만 관례를 이미 따르고 있음을 확인. 고침: sweep_auctions() 는 이미 항목별로 커밋하므로 형제 sweep_dispatches()의 이미 검증된 항목별 try/except/rollback/continue 패턴을 그대로 이식(이전에 이미 커밋된 항목은 그대로, 실패한 항목만 롤백 후 다음으로) — res 딕셔너리에 errors 카운터 추가. 나머지 5개는 함수 끝에 한 번만 커밋하는 배치형이라 항목별 롤백이 다른 항목의 진행분까지 지울 위험이 있어(발견1과 같은 함정이 배치 안에서 재현됨), 대신 루프 구간 전체를 하나로 묶어 실패 시 배치 전체를 롤백하고 로그를 남긴 뒤 조용히 종료한다 — 이 함수들 자신의 SELECT 단계가 이미 쓰는 '가드하고 실패하면 롤백 후 반환' 패턴을 루프까지 넓힌 것뿐(새 메커니즘 없음, 오늘 실패 시 이미 아무것도 안 커밋되던 것과 최종결과는 같고 크래시가 로그+정리로 바뀌는 것뿐). 재인덴트가 필요한 85줄짜리 큰 블록이라 손으로 다시 안 치고, readlines() 인덱스로 앵커링해 기존 텍스트를 그대로 재사용하는 스크립트로 적용(각 단계 ast.parse 로 즉시 검증 — run_all_tests.py 삽입사고(414라운드) 재발 방지 차원에서 이번엔 스크립트 실행 전에도 미리 드라이런으로 확인). 회귀테스트(test_scan_round415_fixes.py, 21개 검사)는 실제 몽키패치로 notify() 를 특정 타겟에서만 실패시켜 ①sweep_auctions: 실패한 타겟은 롤백돼 상태가 그대로임을(고치기 전엔 '유찰'로 유령전환) 감사로그 직접조회로 확인, 같은 배치의 다른 타겟은 정상 처리됨을 확인 ②sweep_report_overdue: 실패 시 예외가 안 새고 0을 반환·배치 전체 롤백됨을 확인, 정상 상황 대조군 회귀없음 확인 ③옛 코드로 되돌리면(재인덴트 로직으로 원본 인덴트 복원, 재타이핑 없음) 둘 다 예외가 실제로 밖으로 새고 sweep_auctions는 그런데도 유령전환이 실제로 재현됨을 서브프로세스 실행으로 직접증명 후 원본 복원. 나머지 4개 형제는 구조적으로 동일한 변환(같은 스크립트, 같은 시점 ast.parse 통과, 육안 대조 완료)이라 소스 검사로 대체. ⚠ **발견3(제품판단 필요, 미수정)**: manage.py::cmd_sweep()(959-1003행)·main()(2628-2637행) 도 스윕 전체를 하나의 무방비 try 로 묶어, 이번 수정과 무관하게 스윕 하나가 실패하면 그 회차 나머지 스윕이 전부 스킵된다 — '무엇을 건너뛰고 무엇을 계속할지'는 설계판단이 필요해 분리 보고, 수정 보류. ⚠ **부수발견(경미, 자연치유)**: sweep_send_notifications 의 철지난문자 취소 UPDATE(6391-6404행 부근)가 rollback 없는 except sqlite3.Error: pass 지만, 바로 다음 for루프 첫 항목의 기존 rollback 이 즉시 청소해 대기열 1건만 이번 회차 조용히 밀리고 자연복구됨 — Agent가 재현 로직으로 직접 추적 확인, 시급성 낮아 미수정. app.py 자신의 스윕함수 6개 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round416_fixes.py", "스캔 416라운드 회귀(사건 등록 3경로 — 관리자콘솔 api_case_create(app.py), 보험사포털·v1 API 공용 _create_case/_normalize_categories — 전부 서버가 이미 갖고 있는 정본 공종목록(WORK_MAJORS, 14653행 부근)을 값 검증에 안 써서 브라우저(닫힌 드롭다운)를 거치지 않은 요청이면 임의 문자열을 공종으로 그대로 저장할 수 있던 결함[중간심각, 데이터무결성 — 잘못된 공종은 표준단가·공종별 매칭에서 조용히 0건 처리돼 '누구에게도 매칭 안 되는 공고'로 남을 수 있음], 정밀조사 Agent가 각도2(서버측 검증 없이 클라측만 검증하는 폼 필드) 조사에서 발견 — WORK_MAJORS 자신의 주석이 '화면 세 곳이 각각 적혀 있어 한 곳만 고치면 조용히 어긋났다, 서버로 모은다'고 명시하는데 정작 그 서버가 값 검증에 한 번도 안 씀을 3경로 전수 대조로 직접 확인. 같은 라운드 부수발견: api_case_create() 만 형제(_create_case)가 이미 쓰는 지역(region) 낱자모 오염 필터(_has_bare_jamo, 실운영 사고 region='ㅇㄴㅁㄹㄴㅁㅎㄹ' 대응)가 빠져 있었음. 고침: 이미 있는 WORK_MAJORS 화이트리스트를 _normalize_categories()·api_case_create() 양쪽에 대조 추가(새 정책 없음, CaseInputError 는 이미 있는 예외체계 재사용), region 필터도 형제와 같은 _s()+_has_bare_jamo() 조합을 그대로 이식. 고치는 중 직접 발견한 2차 함정: _idem_fingerprint(d) 도 내부에서 _normalize_categories() 를 부르는데, 그 호출이 api_insurer_case_create·api_v1_case_create 양쪽에서 전부 기존 try/except CaseInputError **밖**(멱등키 중복확인 블록 안)에 있어, 그대로 뒀으면 잘못된 공종으로 같은 idem_key 를 재사용하는 요청이 깔끔한 400 대신 처리되지 않은 예외(500)로 죽고 트랜잭션도 못 닫혔을 자리 — 두 함수 모두 BEGIN IMMEDIATE 직후부터 try 를 넓혀 같은 except 가 잡게 고침(수정 과정 자체가 새 결함을 만들 뻔한 것을 구현 전 호출경로 추적으로 미리 잡은 사례). 독립검증 중 뜻밖의 발견: 기존 테스트 5개(라운드68·141·198·227 + insurer_api_guide.html 의 실제 API 예시를 그대로 쏘는 라운드226)가 전부 축약형 공종('가드레일' 등, 정본은 '가드레일·방호울타리')을 우연히 쓰고 있어 이 화이트리스트가 켜지면 깨짐을 미리 전수감사로 발견 — 각 테스트가 실제로 검증하는 바(라운드227=멱등키 지문불일치, 라운드68=접수번호 레이스, 라운드141=하위계정 구분, 라운드198=재시도 안전장치)에 공종의 정확한 정체는 무관함을 하나하나 확인한 뒤 정본 이름으로 갱신(라운드412·414의 '구식 가정 갱신' 판단기준과 동일 사례 — 재검증 결과 5개 전부 회귀 없이 재통과). templates/insurer_api_guide.html(실제 보험사 연동 담당자에게 보여주는 공개 API 예시)의 카테고리 예시도 축약형이라 이 검증이 켜지면 그 예시를 그대로 복붙한 실제 연동 코드가 운영에서 400을 받게 되므로 함께 정본 이름 으로 교체. 회귀테스트(test_scan_round416_fixes.py, 15개 검사)는 3경로 전부 실제 실행으로 잘못된 공종 400·정상 공종 회귀없음·지역 낱자모 필터를 확인하고, 특히 v1 API에서 같은 idem_key 를 잘못된 공종으로 재사용해도 500이 아니라 400이 남을 실제로 실측(2차 함정 수정의 직접 증거) — 옛 코드로 되돌리면 없는 공종도 200으로 받아 그대로 저장됨을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 라우트 변경이라 재기동 필요, static/templates 도 함께 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인). 정밀조사 Agent가 함께 보고한 SQL 동적생성 지점 전수감사(각도1)는 실행가능한 인젝션 없음으로 직접 재확인(파라미터바인딩·닫힌 화이트리스트·모듈상수 패턴 전부 확인, 라운드321에서 이미 하드닝된 DB.sql_now() 사례 재확인). ⚠ **참고발견(보안 아님, 기능버그, 미수정)**: partner_portal.html:1164가 '비워두면 0일로 접수됩니다'라 명시하고 JS도 0을 유효값으로 통과시키는데, 서버 parse_days()(444-452행)는 1<=n<=MAX_DAYS 를 요구해 0을 매번 거부함 (app.py:4916·5137 두 투찰 경로 모두 영향) — 0일이 정말 유효한 공기인지확인이 필요한 제품판단이라 보고만.)"),
    ("test_scan_round417_fixes.py", "스캔 417라운드 회귀(협력사명이 담기는 JSON error 문구 3곳이 이스케이프 없이 f-string으로 조립돼 admin.js:toast()(app.py 무관, static/admin.js:143 innerHTML 대입, esc() 안 거침)로 그대로 렌더링되던 결함[중간심각, 저장형 마크업주입 — 전역 CSP(app.py:1026-1059, script-src 'self' 'nonce-…', unsafe-inline 없음) 덕분에 현재도 스크립트 실행까지는 안 가지만 마크업·피싱링크 주입은 가능], 정밀조사 Agent가 각도1(출력 이스케이핑) 조사에서 app.py 전체(20,254줄 실측) f-string 에러메시지 107건 전수 판독으로 발견 — ①api_application_create()(7280행, POST /api/applications/manual, @require_admin) ②api_application_update()(7377행, PATCH /api/applications/<id> 승인, @require_role) ③_payout_account_gate()(13568행) 세 곳 전부 승인된 협력사명을 사업자번호 중복확인 메시지에 그대로 echo. 독립검증: toast()(admin.js:143) 가 esc() 없이 innerHTML= 대입함을 직접 확인, 3곳 모두 f-string 삽입값이 사용자(협력사)가 정한 상호명임을 직접 대조. 같은 라운드 각도2(라우트 전수 권한데코레이터 감사, 273/273개 전수) 는 결함 0건으로 클린 확정 — 인증 데코레이터 229개, 문서화된 다중역할 커스텀 관문(_mixed_actor_guard 등) 7개, 화면용 수동 동등검사 2개, 근거 명시된 의도적 공개 라우트 35개로 273개 전부 설명됨을 직접 재확인(라운드161·222가 이미 잡은 같은 클래스 결함들이 지금도 제대로 막혀 있음도 확인). 고침: 라운드318이 이미 쓴 관용구(Markup 템플릿 + escape(보간값), Markup.format 이 보간값만 자동 이스케이프)를 그대로 3곳에 이식 — 새 메커니즘 없음, str()로 감싸 jsonify 에는 순수 문자열만 전달. 회귀테스트(test_scan_round417_fixes.py, 14개 검사)는 <b>Evil</b> 같은 위험 상호명을 가진 실제 협력사 행을 만들어 3경로 전부 실제 실행으로 응답의 error 필드가 정확히 &lt;b&gt;Evil&lt;/b&gt; 로 이스케이프됨(원문 <b> 태그가 안 섞임)을 확인 — 검증 중 자체 오류 둘 발견·수정: ①두 번째 테스트용 사업자번호를 손으로 대충 만들어 valid_biz_no() 검사를 실패했는데, 그 값은 raw SQL로 직접 넣는 값이라 애초에 그 검사를 안 거치는 경로임을 확인해 불필요한 단언을 제거 ②_payout_account_gate() 가 Response 단독이 아니라 (Response, 상태코드) 튜플을 돌려주는데 .get_json() 을 튜플에 바로 불러 AttributeError — 튜플 언패킹으로 수정. 옛 코드로 되돌리면 업체명이 원문 그대로(이스케이프없이) 나옴을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 라우트 3곳 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round418_fixes.py", "스캔 418라운드 회귀(partner_accounts.py::gen_pw()(47행 부근, 협력사 계정 일괄발급용 임시비밀번호 생성)가 형제 3곳(app.py:_gen_temp_pw 7607행, manage.py:gen_password 102행, 발주처 인라인 발급)이 이미 쓰는 '대문자·소문자·숫자 각 1개 이상 보장' 재시도 루프 없이 secrets.choice() 한 방으로 끝내던 결함[낮음~중간, 정책위반 발급 — 무차별대입 관점 보안결함은 아님(49자×12자리 약 67비트, 여전히 강력), 순전히 코드베이스 내 일관성 결함], 정밀조사 Agent가 각도2(임시비밀번호·토큰 예측가능성) 조사에서 몬테카를로20만회 실측(해석적 계산과 이중검증)으로 약 16% 확률로 숫자가 하나도 없는 비밀번호가 나옴을 발견 — 그 결과 이 앱 자신의 password_policy_error() 기준(두 종류 이상 조합)을 위반한 채 실제 협력사 계정(partners.password_hash)에 발급될 수 있었다. 독립검증: 형제 3곳 원문 직접 대조로 전부 같은 while True + any(isupper)/any(islower)/any(isdigit) 재시도 패턴을 씀을 확인, 이 파일만 그 패턴이 없음을 직접 대조. 부수발견: 같은 파일의 자체 점검(demo(), --self-check)도 길이(12)·혼동글자 배제만 보고 문자종 구성은 검증하지 않아 이 결함이 있어도 '자체 점검 통과'를 출력하고 있었음. 고침: 형제와 완전히 같은 재시도 루프를 gen_pw() 에 이식(새 정책·새 임계값 없음), demo() 의 자체점검에도 같은 문자종 단언을 추가(형제 점검 기준과 일치시킴). 회귀테스트(test_scan_round418_fixes.py, 10개 검사)는 secrets.choice 를 결정론적 큐 기반 프록시로 바꿔치기해(411라운드 _FailNthCommit 과 같은 정신 — 확률적 결함을 타이밍 대신 결정론으로 재현) '1차 시도(전부 소문자, 문자종 미달) → 재시도(정상 조합)' 순서를 직접 실측(정확히 24회 호출, 최종값은 재시도분) — 정상 경로 500회 반복도 전부 정책 만족(회귀없음) 확인. 옛 코드로 되돌리면 같은 프록시가 재시도 없이 12회만 호출되고 숫자 없는 비밀번호를 그대로 반환함을 서브프로세스로 직접증명 후 원본 복원. 검증 중 이 세션에 이미 문서화된 방어(reference_test_default_db_is_prod.md, '테스트가 운영 DB 경로를 가리키면 중단')가 실제로 발동함을 확인 — gen_pw() 자체는 DB 를 안 건드리지만 partner_accounts.py 가 import 만 해도 db 모듈을 끌어와 이 세션 표준 방어에 걸림, 다른 테스트와 같은 스크래치 BOKGUON_DB_PATH 지정으로 해결(새 함정 아님, 기존 방어가 의도대로 작동한 사례). partner_accounts.py는 app.py 가 import 하는 모듈이 아닌 독립 CLI 스크립트라 이 수정만으로는 재기동 불필요 — 운영 서버(app.py) 동작에 영향 없음, BUILD_HASH 로테이션 없음(재기동 자체를 안 함))"),
    ("test_scan_round419_fixes.py", "스캔 419라운드 회귀(app.py 4곳(2239·7219·9375·12971 부근, sitemap_xml() 의 <lastmod>·ops-kpi 및 일반 엑셀 내보내기 파일명·정산 CSV 내보내기 파일명)이 이 파일 자신이 100회 넘게 쓰는 DB.now()/datetime.now(DB.KST) 관례 대신 보정 없는 naive datetime.now()(OS 시각)를 직접 써서, 서버 OS 시계가 KST 가 아니면(deploy/bootstrap.sh 가 이미 경고하는 실제 배포 리스크 — 컨테이너 기본 UTC 등) KST 자정 전후 9시간 구간에 하루 어긋난 날짜가 찍히던 결함[낮음심각, 표시값만 영향 — 사업로직(정산금액·상태판정·법적기한)에는 영향 없음을 직접 추적 확인], 정밀조사 Agent가 각도1(KST 시간대 처리 일관성) 조사에서 app.py·dispatch.py·db.py 전체(20,267·1,295·2,202줄 실측) SQL 리터럴 계층은 100% 클린임을 먼저 확인한 뒤 Python 계층 에서 발견 — db.py:73 KST=timezone(timedelta(hours=9)) 기준 DB.now() 관례가 101+5회 압도적 주류이고, 이미 라운드68 등에서 같은 결함을 고친 이력(13121·13970·18430 부근 datetime.now(DB.KST) 패턴)이 지금도 유효함을 확인한 뒤, 그 관례를 못 받은 나머지 4곳만 남은 것을 전수 대조로 특정. 독립검증: 4곳 전부 직접 읽어 stamp/today 값이 저장값·비교·계산에 재사용되지 않고 응답헤더·SEO 태그로만 쓰임을 확인, 관련 테스트 7개 파일(round22·58·81·102·104·142·221) 대조로 이 각도를 다루는 하드코딩된 가정이나 '의도적 미수정' 코멘트가 없음을 확인(단순 누락으로 판단, 이 머신은 OS 시계가 이미 KST라 실서비스에서도 지금까지 증상이 안 보였을 뿐). 같은 라운드 각도2(사건 상태전이 가드)는 UPDATE cases SET status=... 19곳(app.py 17·dispatch.py 2, 멀티라인 정규식으로 단순 grep이 놓친 2곳(19650·1223 부근)까지 추가 발견) 전수 확인 결과 클린 확정 — 18곳은 WHERE 직접 가드 또는 BEGIN IMMEDIATE 트랜잭션 안 선행 SELECT+rowcount 확정으로 TOCTOU 창이 이미 닫혀 있고, 유일한 예외 1곳(app.py:4280 부근, 발주처 사건취소)도 WHERE 가드 대신 BEGIN IMMEDIATE+선행 SELECT체크라는 이 코드베이스 자신이 이미 설명하는(5686-5689행 부근) 유효한 대체 패턴임을 호출순서까지 직접 추적해 확인 — 411~415라운드가 심은 관례가 예외 없이 전파돼 있음. 고침: datetime.now() 4곳을 이미 있는 datetime.now(DB.KST) 패턴으로 교체(새 메커니즘 없음, 3곳은 완전히 동일한 코드줄이라 한 번의 replace_all 로 처리). 회귀테스트(test_scan_round419_fixes.py, 10개 검사) 는 datetime.datetime.now 가 불변 C확장 타입이라 직접 monkeypatch 불가능함을 확인한 뒤, app 모듈 자신의 이름공간에 바인딩된 datetime 이름 자체를 가짜 클래스로 교체하는 기법(이 세션 최초 사용, [[reference_datetime_name_rebinding_mock]])으로 '가짜 OS시각(자정경계 하루 이른 값) vs 올바른 KST 값'을 결정론적으로 재현 — /sitemap.xml 실제 호출로 <lastmod> 에 고쳐진 코드는 올바른 다음날 날짜가, 옛 코드로 되돌리면 하루 이른 날짜가 찍힘을 직접증명 후 원본 복원. app.py 자신의 코드 4곳 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round420_fixes.py", "스캔 420라운드 회귀(collect_emails.py(협력업체 이메일 수집 CLI, app.py 가 import 안 하는 독립 배치도구)의 EMAIL_RE·태그제거 정규식(57·165행 부근) 둘 다 앵커가 없어 닫는 조건이 끝까지 안 나오면 시작위치마다 문자열 끝까지 훑어 페이지 길이의 제곱에 비례해 느려지던 결함[낮음심각, 배치도구 1건 실행시간만 영향 — app.py 미참조 확인, 실서비스 웹서버 무관], 정밀조사 Agent가 각도2(정규식 ReDoS) 조사에서 알려진 파국패턴(a+)+$으로 측정도구 자체를 먼저 검증(2^n 지수폭발 정확히 재현 확인)한 뒤 실제 코드베이스 15개 프로덕션 파일 전수 스캔으로 발견 — 실측: 200,000자에서 EMAIL_RE 32.9초, 250,000자에서 51.4초(다항 O(n²), 지수 아님 — 시간비가 길이비의 제곱에 정확히 비례함을 확인). 기존 MAX_BYTES(500,000)는 네트워크 읽기만 제한할 뿐 정규식 처리시간은 안 막아, 병리적인 한 페이지(닫는 '>' 나 완성되는 이메일이 없는 페이지)가 이 배치도구 스레드를 몇 분씩 붙잡을 수 있었다. 독립검증: fetch()·refuses_collection()·pick_emails() 호출관계 직접 대조, app.py 가 이 모듈을 import 안 함을 grep(테스트 파일 3개만 히트)으로 재확인, 기존 테스트 3개(round218·267·299)는 정규식 함수를 fetch() 안 거치고 직접 짧은 문자열로 호출해 이 수정과 충돌 없음을 직접 대조. 대조 각도1(외부API 실패처리)은 팝빌 SDK(벤더 공식소스 직접확인) 자체에 소켓 타임아웃이 전혀 없어 serve_waitress.py 의 8-스레드 풀이 /api/outbox/send-now 등 동기호출 경로에서 고갈될 수 있음을 발견했으나, 몽키패치(262라운드가 이미 명시적 기각)·전역 socket.setdefaulttimeout·스레드+join 강제종료 세 후보 전부 트레이드오프가 있어 '제품판단 필요'로 분류, 미수정·기록만(DB잠금 안에서 외부호출하는 자리는 0건, 재시도 멱등성도 전수 클린 확인). db.py:880 _REGION_PAREN 도 같은 O(n²) 모양이지만 모든 호출경로가 사전에 80~120자로 슬라이싱해 실질위험 없음을 직접 추적 확인(조치 불필요). 고침: fetch() 가 반환 직전 새 상수 MAX_SCAN_CHARS(30,000)로 한 번 더 자름 — 호출부(본문· 하위경로 양쪽)를 안 건드리고 생산지 한 곳만 수정, 새 정책 없음. 30,000자 에서 두 정규식 다 실측 1초 미만(직접 측정 — 짐작 아님, 태그제거 최악 0.37초)임을 코드 작성 전에 먼저 확인 후 값을 정함. 회귀테스트(test_scan_round420_fixes.py, 12개 검사)는 urllib.request.urlopen 을 가짜로 바꿔치기해 60,000바이트 악성 페이지(닫는 '>' 없는 태그더미+완성 안 되는 이메일)를 실제로 fetch() 에 흘려보내 정확히 30,000자로 잘림·전체 처리 2초 이내를 실측, 정상 크기 페이지는 안 잘리고 이메일도 정상 검출됨(회귀없음)을 확인 — 검증 중 자체 오류 하나 발견·수정: 정상 대조군에 쓴 contact@example.com 이 이 파일 자신의 BAD_DOMAIN(88행, 플레이스홀더 도메인 배제용)에 이미 등록돼 있어 의도대로 걸러진 것을 회귀로 오인할 뻔함 — 실존 도메인 형태로 교체 후 12/12 통과. 옛 코드로 되돌리면 60,000자 그대로 안 잘리고 반환됨을 서브프로세스로 직접증명 후 원본 복원. app.py 가 import 안 하는 독립 CLI 임을 grep 으로 확인 후 재기동 생략(서버 미영향, BUILD_HASH 로테이션 없음))"),
    ("test_scan_round421_fixes.py", "스캔 421라운드 회귀(_sub_update_impl()(app.py:3220-, 협력사·보험사 포털 하위계정 권한·상태·이름 변경 공용함수)의 DB.log 가 로그인아이디만 남기고 무엇이 바뀌었는지(등급·상태의 이전값→새값)는 전혀 안 남기던 결함[낮음~중간심각, 공격표면 아님(require_portal_owner 로 조직 최고관리자만 호출 가능) — 사후 감사·분쟁해결 능력의 약점], 정밀조사 Agent가 각도2(고위험 작업 감사로그 커버리지, app.py 약 45개 후보 함수 전수대조) 조사에서 발견 — 형제 3곳(api_admin_update 1694행·api_partner_update 8162행·api_insurer_update 8439행 부근)은 전부 권한·상태 변경을 old→new 로 명시하는데 정확히 같은 범주(협력사·보험사 계정 권한·상태 변경)를 다루는 이 함수만 관례를 안 따름을 직접 대조 확인. 독립검증: 1차합의(api_insurer_field_agreement_decision→dispatch.py:settle_agreement)·협력사계정발급(api_partner_credentials→issue_partner_login) 등 '호출자 아니라 피호출자가 로그를 남기는' 정상 패턴과는 명확히 구분해서(방법론 8번 호출경로 끝까지 추적) 이 건은 진짜 결함임을 확정, 세션쿠키 보안속성(SESSION_COOKIE_SECURE=IS_PROD 등)은 dev_tls_proxy.py·DEPLOY.md 가 이미 트레이드오프를 문서화한 의도된 설계임을 3중 교차확인해 클린 판정. 고침: row 에 이미 로드된 이전 값으로 diff 를 만들어(추가 조회 불필요) DB.log detail 에 '등급 {old}→{new}'·'상태 {old}→{new}'·'이름 {old}→{new}' 를 형제와 같은 화살표(→) 표기로 남김 — 새 정책 없음. 부수개선: 값이 실제로 안 바뀌어도 매번 UPDATE+로그를 쏘던 것도 형제와 같은 기준(실제 변경분만 반영)으로 맞춰 로그 노이즈도 줄임(diff 계산이 필연적으로 변경여부 확인을 요구해 같은 수정으로 자연히 해결됨, 범위 확장 아님). 회귀테스트(test_scan_round421_fixes.py, 12개 검사)는 기존에 이 라우트를 다루는 테스트가 전무함을 grep으로 확인한 뒤(충돌 위험 없음) 협력사 하위계정을 실제로 만들어 PATCH /api/partner/subaccounts/<uid> 로 등급+상태를 동시에 바꿔 activity_log.detail 에 두 항목 다 old→new 로 남음을 실측, 같은 값으로 재요청하면 unchanged:true 와 함께 새 로그가 안 쌓임(로그노이즈 감소 확인)도 검증 — 첫 실행 12/12 통과. 옛 코드로 되돌리면 로그에 로그인아이디 뿐 등급/상태 정보가 전혀 없음을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round422_fixes.py", "스캔 422라운드 회귀(api_insurer_bids()(app.py:4222-, 보험사 포털 낙찰후보 조회)가 SELECT b.* 로 bids 테이블을 통째로 받아 형제(api_insurer_case_detail, 9495행 부근 — 이미 화이트리스트로 좁혀 받음)와 다른 관례를 쓰던 스키마드리프트 결함[낮음심각, 현재는 미노출 — bids 테이블에 민감컬럼이 없어 지금 당장 새는 값은 없음을 db.py 마이그레이션 전수대조로 직접 확인, 나중에 내부용 컬럼이 추가되면 이 자리만 조용히 새는 잠재위험], 정밀조사 Agent가 각도1(역할별 API 응답 필드 과다노출, 20여개 라우트 전수) 조사 중 부기 — 협력사·보험사 양쪽 포털 응답 20여곳을 jsonify 직전까지 직접 추적한 결과 이 1건 외 실제 유출은 0건임을 확인(계좌원문 복호화는 앱 전체 2곳뿐, 전부 @require_admin+최고관리자 재검사+감사로그 이중방어, 보험사·협력사 라우트에서 CRYPTO.decrypt 호출 0건 grep 확인). 독립검증: bids 테이블의 현재 컬럼 11개(id·auction_id·partner_id·partner_name·amount·days·created_at·is_demo·first_bid_at·voided_at·void_reason)를 CREATE TABLE(db.py:324)+마이그레이션 4건 전수대조로 직접 확정, _bid_scores()(10701행 부근)가 실제로 읽는 필드(amount·days·rating·p_region·jobs_done·partner_id)까지 확인해 필드를 함부로 줄이지 않고 현재 컬럼 전부를 그대로 나열하는 안전한 방식으로 결정. 고침: SELECT b.* 를 위 11개 컬럼 전부를 명시한 화이트리스트로 교체 — 지금 당장의 동작은 완전히 동일(제거된 필드 없음, 기존 테스트 6개(b4_http·firstday·rehearsal·round3·round4·round303)가 이 라우트를 쓰지만 전부 필드 존재여부만 확인해 충돌 없음을 grep으로 먼저 확인), 새 컬럼이 추가돼도 여기 명시적으로 추가하지 않는 한 자동으로 안 새는 것만 달라짐 — 새 정책 없음. 회귀테스트(test_scan_round422_fixes.py, 14개 검사)는 기존 필드 7종이 전부 그대로 응답에 남음(회귀없음)을 확인한 뒤, 실제로 bids 테이블에 ALTER TABLE 로 가상의 민감컬럼(internal_cost_note)을 추가해 값을 채우고 다시 호출 — 화이트리스트 덕에 그 값이 응답에 안 샘을 실측, 옛 코드(b.*)로 되돌리면 같은 시나리오에서 그 값이 그대로 새는 것도 서브프로세스로 직접증명(양방향 인과관계 검증) 후 원본 복원 — 첫 실행 14/14 통과. 부수 제안(이번 라운드 범위 밖, 기록만): 보험사측에는 협력사측 test_partner_leak.py(257줄, 관리자 GET 라우트 전수추출+IDOR 4종+ 2차경매 비공개검증)에 대칭되는 자동 유출 회귀테스트가 없음 — 다음 라운드 이후 별도로 test_insurer_leak.py 신설을 고려할 만한 투자 가치가 있으나, 이번 라운드의 단일 기계적 수정과는 규모가 달라 범위에 안 넣음. 사진 외 파일업로드(각도2)는 전수 확인 결과 엑셀 연락처 일괄등록(app.py:8796-, @require_admin) 1건뿐이고 디스크 미저장·read_only+행상한 재검증(라운드409 기설치)·매크로 미실행이라 클린 — 증빙서류 업로드 자체가 없음(오프라인채널로 처리한다는 명시적 주석 확인, app.py:4530 부근). app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인))"),
    ("test_scan_round423_fixes.py", "스캔 423라운드 회귀 — CSV/엑셀 내보내기 수식주입(Formula Injection) 탭우회 + parse_days() OverflowError 미스캐치, 2건. [1] _xl_safe()(app.py:13082)· 정산CSV 내부 _csv_safe()(app.py:12972) 둘 다 제어문자 필터에서 탭 문자를 의도적으로 보존하는데, 수식주입 트리거 판정(등호·더하기·빼기·골뱅이로 시작하는지만 확인)은 그 탭을 고려하지 않아 값이 탭으로 시작한 뒤 등호가 이어지면 보호용 따옴표가 안 붙던 결함[낮음심각, openpyxl 3.1.5의 _bind_value 가 리터럴로 등호로 시작할 때만 수식타입 승격시켜 파일을 열기만 해서는 자동실행 안 됨 — 사람이 그 셀을 재입력할 때만 발동하는 약한 잔여위험], 정밀조사 Agent가 각도1(CSV/엑셀 내보내기 8개 라우트 전수, _xl_safe·_csv_safe 공용헬퍼 대조) 조사에서 발견 — 실제 도달경로: api_lead_update()(app.py:7266-)의 note 갱신이 형제 자유텍스트 필드들( clean_public_form·company.strip()·reason.strip() 등)과 달리 strip() 이 빠져 있어, 탭으로 시작하는 note 가 그대로 저장 → EXPORT_SECTIONS['leads'](app.py:9274, note AS 메모) → api_export_xlsx() → _cell() → _xl_safe() 로 흘러감을 직접 추적 확인. ⚠ 정밀조사 Agent 보고서는 여기서 멈췄으나, 배터리 실행 전 기존 테스트 충돌을 사전확인하는 과정에서 test_scan_round118_fixes.py 자신의 주석(app.py:7414, '형제인 도입문의(insurer_leads) note 와 같은 결함 — 같은 관례로 맞춘다')이 api_application_update()(app.py:7402-, partner_applications.note)를 이미 명시적 형제로 지목해 뒀음을 발견 — 실제로 그 자리도 정확히 같은 strip() 누락 패턴이었고(같은 EXPORT_SECTIONS['applications'].note AS 심사메모 경로로 동일하게 노출), 정밀조사 Agent가 각도1에서 이 형제 하나를 놓쳤던 것으로 확인됨(에이전트 보고서 미스캘리브레이션 사례로 기록 — '형제 전수'라고 결론내리기 전에 이 코드베이스 자신의 주석이 이미 명시한 형제 관계까지 항상 재확인할 것). [2] parse_days()(app.py:444)는 parse_money() 와 달리 문자열화 없이 정수변환을 값에 직접 적용하는데, JSON 요청 바디의 무한대 리터럴(파이썬 표준 json 모듈이 관례적으로 허용 — flask.json.provider.DefaultJSONProvider 가 parse_constant 를 오버라이드하지 않아 그대로 통과함을 직접 실행으로 확인)이 부동소수 무한대로 파싱되면 정수 변환이 ValueError 가 아니라 OverflowError 를 내고, 기존 except 절이 이를 못 잡아 그대로 위로 전파되던 결함[낮음심각, 서버 크래시는 아님 — 전역 errorhandler(app.py:1201-)가 커넥션 정리 후 일반 500으로 감싸 트레이스백 노출·DB잠금잔존 없음, 원래 나가야 할 400+안내메시지 대신 의미 없는 500이 나가는 입력검증 계약 위반 수준], 각도2(입찰 amount/days 숫자 경계검증, 쓰기경로 2곳(api_partner_bid 4946행·api_partner_reauction_bid 5158행) 전수확인)에서 발견 — parse_money() 는 먼저 문자열화 후 파싱해 무한대·NaN·과학표기법 전부 정상 거부됨을 직접 실행으로 대조확인(안전, 미수정). 독립검증: 두 결함 모두 직접 실행(exec 격리)으로 재현, 기존 테스트와의 충돌 사전확인(round221의 등호로 시작하는 값·캐리지리턴 검증, round396의 parse_days 0/1/365/366/-1 경계값 검증 — 이번 수정이 그 값들의 반환값을 전혀 안 바꿈을 직접 대조). 고침: (a) _xl_safe·_csv_safe 트리거 문자 집합에 탭 문자 추가(형제 둘 다, 형제 전수감사), (b) api_lead_update()·api_application_update() 둘 다의 note 대입에 strip() 추가(형제 필드들과 통일), (c) parse_days() 의 except 튜플에 OverflowError 추가 — 셋 다 기존 정상 입력의 반환값은 전혀 안 바뀌는 순수 방어 확장, 새 정책 없음. 부수 관찰(이번 라운드 범위 밖, 제품판단 필요로 기록만): parse_days() 는 소수 입력(10.5)을 에러 없이 10으로 조용히 절삭하고 JSON 불리언 true 를 조용히 1일로 허용함 — parse_money() 처럼 문자열화-후-파싱 패턴으로 통일할지는 '공사기간에 소수점이 의미있는가'라는 정책질문이라 결정하지 않음. 회귀테스트(test_scan_round423_fixes.py, 30개 검사)는 실제 소스를 그대로 exec 격리 실행해 탭우회·무한대크래시 둘 다 고쳐졌음을 확인하고, api_lead_update()·api_application_update() 둘 다 실제 Flask+DB 로 탭 포함 note 가 strip 되어 저장됨을 실측, 옛 코드로 되돌리면 (a)(b)(c) 전부 원래 결함이 그대로 재현됨(_xl_safe·parse_days 는 격리실행으로, 두 update 라우트는 한 서브프로세스에서 함께)을 양방향 인과관계 직접증명 후 원본 복원 — 첫 실행 30/30 통과. 부수로 test_scan_round118_fixes.py 의 두 소스검사(lu_body·au_body)도 strip() 이 추가된 새 문자열에 맞춰 갱신(자르는 동작 자체·이미 있던 실행기반 길이확인은 불변, 문자열 일치 조건만 legitimate evolution). app.py 자신의 함수 4곳(lead·application note 갱신 2곳 + _xl_safe·_csv_safe 2곳) + parse_days 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)"),
    ("test_scan_round424_fixes.py", "스캔 424라운드 회귀 — bids 테이블에 부분 UNIQUE 인덱스로 동시성 방어심화, 1건. 정밀조사 Agent가 각도1(사진·증빙파일 서빙 라우트의 경로탐색+IDOR 전수, 유일한 send_file 호출인 api_photo_file(app.py:11947-) 전수확인)과 각도2(입찰 제출 동시성 TOCTOU) 둘 다 클린으로 확정 — 각도1은 photos.rel_path 가 항상 서버생성 난수(secrets.token_hex)+정수캐스팅 case_id 로만 조합돼(photo_ai.py:301-303) 사용자 입력이 경로에 섞일 여지가 구조적으로 없고, _photo_visible_to()(app.py:11353-)가 인증(_mixed_actor_guard)과 별개로 사건 소유권을 역할별로 촘촘히 재검증함을 직접 확인. 각도2는 api_partner_bid()·api_partner_reauction_bid()(app.py:4988·5204) 둘 다 읽고-계산하고-쓰는 구간 전체를 BEGIN IMMEDIATE 로 감싸고 그 안에서 'voided_at IS NULL 인 기존 입찰이 있으면 UPDATE, 없으면 INSERT'(5077-5104·5282-5308)로 파트너당 활성입찰 1건을 유지함을 확인, sweep_auctions()(5692-5718)도 마감 스윕이 잠금 획득 후 입찰자 수를 재계산해 잠금 전 이미 다뤄진 라운드가 남긴 TOCTOU 방어가 여전히 유효함을 확인. 다만 이 불변식(파트너당 활성입찰 최대 1건)을 강제하는 UNIQUE 제약이 bids 테이블 자체(db.py:324)에는 전혀 없어 — 동시성 안전성이 전적으로 이 두 호출부가 항상 BEGIN IMMEDIATE 규율을 지킨다는 애플리케이션 계층의 약속에만 의존하는 방어심화 여지를 발견(결함 아님). 독립검증: 실제 운영 DB(bokguon.db, 78건)를 직접 SQL로 조회해 (auction_id,partner_id)당 voided_at IS NULL 인 중복 행이 0건임을 확인(마이그레이션이 실패 없이 적용될 수 있음을 실측 확보), db.py 의 인덱스 생성 루프(1447-1450행)가 각 CREATE INDEX 문을 개별 try/except sqlite3.OperationalError 로 감싸 하나가 실패해도 서버 기동이 안 죽는 구조임을 확인, voided_at 을 다시 NULL로 되돌리는 코드가 0건임을 grep으로 확인(부분 인덱스가 나중에 되돌리기 로직과 충돌할 가능성 배제). 고침(방어심화, 새 정책 없음): idx_cases_idem 과 같은 부분 UNIQUE 인덱스 패턴으로 CREATE UNIQUE INDEX idx_bids_active_partner ON bids(auction_id, partner_id) WHERE voided_at IS NULL 추가 — 지금 두 호출부의 동작은 전혀 안 바뀌고(이미 지키는 불변식이라 정상 경로에서 이 인덱스에 걸릴 일이 없음), 앞으로 새 입찰-쓰기 경로가 이 규율을 빠뜨려도 DB 자체가 중복 활성입찰 삽입을 거부하는 마지막 안전망이 생김. 회귀테스트(test_scan_round424_fixes.py, 9개 검사)는 스크래치 DB에서 인덱스가 실제로 UNIQUE 로 생성됨을 sqlite_master 조회로 확인, 직접 SQL 중복 INSERT 가 IntegrityError 로 거부됨을 실측, 실제 두 스레드가 같은 협력사·같은 공고에 동시에 서로 다른 금액(85만·95만원)으로 실제 HTTP 투찰을 보내 예외 없이 정확히 1건만 남고 항상 더 낮은 금액으로 수렴함을 실측(순서 무관 불변식 실증, round50 의 실스레드 기법과 같은 정신) — 첫 실행 9/9 통과. 옛 스키마(인덱스 없음)를 별도 임시 DB로 재현해 같은 중복 INSERT 가 아무 제지 없이 성공해 2건이 쌓임을 인과관계로 직접증명. 부수로 전체배터리 최초 실행에서 test_scan_round86_fixes.py 의 테스트 픽스처 충돌 1건 발견·수정 — 이 테스트의 _mk_bid() 헬퍼가 '상한 10,000,000 에 980만·700만 두 입찰'(두 협력사가 낸 것이라는 자신의 주석 의도와 달리) 두 호출 모두 하드코딩된 partner_id=0 을 써서 같은 경매에 같은 파트너의 활성입찰이 2건 생겨 새 인덱스에 막혔다 — partner_id 를 파라미터화해 두 번째 호출에 partner_id=1 을 주는 것으로 수정(자신의 주석이 원래 의도했던 '서로 다른 업체'에 실제로 맞춤, 이 테스트가 검증하는 가견적 상한·하한 로직 자체는 무관해 회귀 아님) — 수정 후 10/10 통과 재확인. db.py 만 변경(app.py 미변경)이라도 db.py 는 app.py 가 import 하는 모듈이라 재기동 필요, static/templates·app.py 코드 자체는 안 바뀌었으나 db.py 변경이 서버 프로세스에 반영되려면 재기동해야 하므로 BUILD_HASH 로테이션 여부는 예측하지 말고 재기동 후 실측 확인할 것. 부수 제안(범위 밖, 다음 라운드 후보로 기록): sweep_auctions 의 마감-vs-투찰 경합을 코드추적이 아니라 round50 의 race() 실스레드 기법으로 직접 실측하는 회귀테스트는 아직 없음 — 코드 추적으로는 이미 안전 확인됐으나(이번 라운드 각도2), 실측 커버리지 추가는 별도 투자 가치가 있음."),
    ("test_scan_round427_fixes.py", "스캔 427라운드 회귀 — 정산 review()·transfer() 취소(void) 방어 보강, 형제 2곳. 정밀조사 Agent가 각도1(정산 지급완료 상태전이 무결성)에서 발견 — 형제 4곳(api_settlement_paid·paid-bulk·api_insurer_settlement_approve·remind-approval)은 전부 void_status=='취소'를 명시적으로 거부하는데 api_settlement_review()(app.py:13638-)·api_settlement_transfer()(app.py:12846-)만 이 검사가 빠져 있었다. 지금 당장은 도달 불가능함을 직접 확인 — api_settlement_void()(13435-)가 취소 시점에 이체완료·입금완료·검수승인 중 하나라도 있으면 거부하고(13462·13467·13472), insurer_paid='입금완료'를 세팅하는 유일한 두 곳(paid·paid-bulk)이 이미 void_status를 거부하므로 취소된 건은 insurer_paid가 영원히 '대기'로 묶여 review()의 NOT_PAID 관문(13654)에 막히고, review_status도 영원히 '대기'로 묶여 transfer()의 관문(구 12860)에 막힘 — 세 컬럼 다 단일 세터(single writer)라 이 사슬에 예외가 없음을 코드 추적으로 증명. 다만 이는 review/transfer 자신이 아니라 다른 라우트들이 우연히 지키는 불변식에 기댄 것이라, 나중에 insurer_paid를 세팅하는 새 경로(예: 관리자 수기보정)가 이 검사를 빠뜨리면 조용히 뚫리는 잠복위험(424라운드의 bids UNIQUE 인덱스와 같은 종류의 방어심화)으로 분류 — 트레이드오프 없는 '그냥 고치면 되는 것'. 같은 라운드 각도2(변경견적 권한·금액검증)는 생성권한 제한(api_change_order_create, 사건 담당업체만 가능)·승인권한(보험사 전용 insurer_ack, 협력사 자기승인 불가)·중복처리 방지 3가지는 전부 클린 확정, 다만 재경매 입찰상한의 뿌리인 requested_amount(협력사 자기신고)에 원 사건금액 대비 상대상한이 없다는 점은 정당한 대형 증액을 막을 위험이 있는 트레이드오프라 '제품판단 필요'로 분류해 미구현(2단계 사람검토(관리자+보험사)가 남아있어 즉시 자금피해로 연결되진 않음, 회귀 테스트도 신설 안 함 — 코드 변경이 없어 페어링할 대상이 없음, YAGNI). 고침: review()·transfer() 둘 다 형제와 같은 void_status=='취소' 조기 거부를 추가 — 정상 경로의 동작은 전혀 안 바뀜(정상 경로로는 이 상태 자체가 못 만들어짐). 회귀테스트(test_scan_round427_fixes.py, 10개 검사)는 정상 API로는 못 만드는 상태(취소+검수승인, 취소+입금완료)를 SQL로 직접 구성해 백스톱 실효성을 실측(두 라우트 다 409로 거부, 상태값 불변 확인) — 첫 실행 10/10 통과. 옛 코드로 되돌리면 취소된 건인데도 transfer()가 실제로 200 응답과 함께 이체완료 처리를 해버림을 서브프로세스로 직접증명(인과관계 확인) 후 원본 복원. app.py 자신의 라우트 2곳 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round429_fixes.py", "스캔 429라운드 회귀 — 사업자등록번호 체크섬 우회(공개폼→승인) + 중복 활성계정 방지 공백(create/update) + 표기 정규화 부재, 5개 지점. 정밀조사 Agent가 각도2(사업자번호 검증 실효성)에서 발견 — 사전에 run_all_tests.py 원문을 직접 대조해 하자보수 워크플로(각도1)는 16개 이상 선행 라운드가 이미 다뤘고 사업자번호도 round79가 4곳(license·update·create·직접접수)에 valid_biz_no() 체크섬검사를 이미 심어 뒀음을 먼저 확인한 뒤, round79가 안 다룬 새 형제 자리를 찾는 방향으로 좁혔다. 발견A(헤드라인): 가장 흔한 유입경로인 공개 입점신청(clean_public_form)은 자릿수·하이픈 위치만 보는 RE_BIZNO 정규식만 거치고 체크섬 검증이 전혀 없었고, 실제로 partners 에 값이 박히는 유일한 지점(api_application_update 승인관문)도 체크섬 재검증이 없어 오타가 공개폼→승인까지 아무 저지 없이 영구 저장될 수 있었다(round79 자신의 원칙 '오타를 입구에서 못 거르면 조회가 빈손이 된다'가 이 경로 하나만 못 미쳤음을 직접 대조 확인). 발견B: round248의 활성계정 중복방지(같은 biz_no로 활성업체 2개 금지)가 승인관문 한 곳에만 있고 신청서를 안 거치는 관리자 직접등록(api_partner_create)·정보수정(api_partner_update)엔 없었으며, 저장값이 하이픈 유무를 정규화하지 않아(api_partner_profile_update만 예외) 같은 사업자를 하이픈 위치만 바꿔 제출하면 문자열 등치 중복확인을 우회할 수 있었음을 직접 확인. 고침(전부 트레이드오프 없는 기계적 확장 — round79/248/profile_update가 이미 세운 원칙을 남은 형제 자리에 적용): (a) clean_public_form 의 biz_no 검사를 RE_BIZNO(형식만)→valid_biz_no()(체크섬)로 교체 + 숫자만 저장하도록 정규화, 이제 아무 데서도 안 쓰는 RE_BIZNO 정의 삭제. (b) api_application_update 승인관문에 체크섬 재검증 추가 + partners 복사값 정규화. (c) api_partner_create·api_partner_update 에 round248과 같은 활성계정 중복확인 추가(update는 자기 자신 id<>? 로 제외) + 저장값 정규화. (d) api_partner_license 도 정규화만 추가(이미 있는 값을 덮어쓸지 여부는 이 화면 특유의 정정 요구와 충돌하는 트레이드오프라 제품판단 필요로 분리, 미구현 — 사용자 결정 대기). 독립검증: valid_biz_no() 의 국세청 검사식을 직접 재구현해 테스트용 유효/무효 번호를 자체 계산으로 생성(코드 값과 완전히 독립적으로 검증), 정규화가 기존 순수숫자 픽스처에는 영향이 없음을 직접 대조. ⚠⚠ 배터리 전체 실행에서 기존 테스트 픽스처 충돌 3건 발견·수정(연속 3연타 — 전부 같은 근본원인: round79/248/417 자신의 테스트가 체크섬 무효값('1234567890' 등 임의 순번)을 승인 시나리오에 써 왔는데, 이번 라운드가 승인관문에 체크섬 재검증을 추가하면서 그 값들이 이제 DUP_BIZNO(409) 대신 체크섬오류(400)로 먼저 막혀 원래 검증하려던 중복확인 로직 자체를 더는 통과 못 시켰다): test_scan_round248_fixes.py(중복승인 시나리오 2곳)·test_scan_round417_fixes.py(BIZ_2, 원래 '검증 엔드포인트를 안 거치니 유효할 필요 없다'던 전제가 이번 승인관문 강화로 깨짐) 둘 다 실제 유효한 체크섬 값으로 교체(검증 의도인 중복확인 로직 자체는 무손상, 값만 현실적으로 교체), test_feature_license_survey.py는 소스 문자열 완전일치 검사(_bz 대입문 원본 그대로)가 정규화 코드 삽입으로 위치가 밀려 실패해 — 기존 대입문은 그대로 두고 정규화를 그 다음 줄에 별도로 추가하는 구조로 api_partner_create·api_partner_license 둘 다 재작성해 회귀 없이 기존 문자열 검사를 그대로 통과시킴(같은 교훈을 두 곳에 한 번에 적용). 회귀테스트(test_scan_round429_fixes.py, 25개 검사)는 실제 Flask+DB로 공개폼→승인 체인 전체를 통과시켜 체크섬 무효값이 두 단계(접수·승인) 모두에서 막히고 유효한 하이픈 표기값은 정규화돼 저장됨을 실측, api_partner_create·update의 하이픈-표기-차이 중복탐지(자기 자신 제외 포함)까지 실측 — 첫 실행 25/25 통과. 옛 코드로 되돌리면 체크섬 무효값이 공개 접수 단계를 그대로 통과함을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 함수 5곳 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인). ⚠ 하자보수 워크플로(각도1)는 완전 클린 확정(10개 라우트 전수, 접수·처리 권한·중복방지·보증기간 계산 전부 기존 16개+ 라운드가 이미 견고하게 방어해 둔 상태 재확인, 새 결함 없음, 코드 변경 없음)."),
    ("test_scan_round430_fixes.py", "스캔 430라운드 회귀 — api_partner_invite()의 notify() 호출에 SAVEPOINT 방어 추가(형제 api_partner_bulk_credentials·round199와 같은 이유), 1건. 정밀조사 Agent가 각도2(대량작업 부분실패 처리)에서 발견 — 이 앱은 요청당 커넥션을 추적해 예외 시 전체 롤백하는 전역 안전망(app.py:347-389, _tracked_get_db+err_500)이 있어 '일부만 조용히 커밋되는' 사고는 안 나지만 그 대가로 '배치 하나가 인프라성 예외로 전부 취소'되는 가용성 문제가 생긴다는 사실을 먼저 확인. 형제 api_partner_bulk_credentials(app.py:7738-, round199)는 이미 SAVEPOINT로 업체별 실패를 격리해 나머지 배치를 살리는데, api_partner_invite()(app.py:19277-)만 notify() 호출에 이 방어가 없어 그 안의 무방비 INSERT(app.py:1837-1843 — notify() 자신의 다른 두 하위쿼리는 이미 try/except sqlite3.Error로 방어돼 있는데 최종 INSERT만 안 그렇다는 것을 직접 대조 확인)가 예외를 던지면 이미 처리된 다른 업체들의 invited_at 표시까지 전부 취소되고, 호출자는 marked/skipped 세부 내역 없이 500만 받았다. 각도1(웹훅/콜백 인바운드 인증)은 완전 클린 확정 — 이 앱은 애초에 인바운드 웹훅/콜백을 받는 라우트가 없음을 250개 라우트 전수 데코레이터 대조로 확인(webhook_url/webhook_secret은 우리가 보험사에게 보낼 때 쓰는 아웃바운드 대상 주소, 팝빌도 발신전용+CLI폴링뿐 콜백 수신경로 없음, 결제/PG 키워드 코드 전체 0건), 외부가 우리를 호출하는 유일한 경로(/api/v1/*)는 require_api_key(SHA-256 해시 대조+Idempotency-Key)로 이미 인증됨을 직접 확인, 억지로 결함을 만들지 않고 클린으로 정직하게 보고. 심각도(각도2 발견)는 낮음(공격자가 트리거 불가, 데이터 정합성 훼손 없음 — 전역 안전망이 이미 그건 막아 줌, 순수 가용성 문제) — 트레이드오프 없는 '그냥 고치면 되는 것'으로 분류. 독립검증: notify() 본문 직접 대조로 최종 INSERT만 무방비임을 확인, bulk-credentials의 SAVEPOINT 관용구를 그대로 재사용 가능함을 확인, 기존 test_feature_onboarding.py의 두 불변조건(발송분기가 표시UPDATE보다 먼저 나오는 순서·'계정이 아직 없습니다' 문구)이 이번 수정으로 안 깨짐을 실행 확인(119/119 통과). 고침: notify(...) 호출을 SAVEPOINT로 감싸 예외 시 그 업체 몫만 롤백하고 skipped에 '안내 발송 중 오류'로 기록, 나머지 업체 처리는 계속 — 새 정책 없음, 기존 형제와 완전히 같은 관용구. 회귀테스트(test_scan_round430_fixes.py, 13개 검사)는 실제 Flask+DB로 두 업체를 동시 요청하되 notify()를 감싼 결정론적 프록시로 한 업체만 강제 실패시켜 — 200 응답(고치기 전엔 500)·marked/skipped 정확한 구분·DB상 성공업체만 invited_at 실제로 찍힘을 실측 — 첫 실행 13/13 통과. 옛 코드로 되돌리면 같은 시나리오에서 실제로 500 응답과 함께 이미 처리 됐어야 할 업체의 표시까지 통째로 취소됨을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round432_fixes.py", "스캔 432라운드 회귀 — manage.py check(MG-06)의 프록시신뢰 검사가 Windows/waitress 배포에서 엉뚱한 변수를 보던 결함, 1건. 정밀조사 Agent가 각도1(관리자 IP 화이트리스트 우회 가능성)에서 발견 — MG-06(manage.py:618-)은 BOKGUON_BEHIND_PROXY=1인데 BOKGUON_FORWARDED_ALLOW가 비면 배포를 막는데, 이 변수를 실제로 읽는 코드는 저장소 전체에서 gunicorn_conf.py(Linux 배포 전용) 단 한 곳뿐임을 grep으로 확인. 이 PC를 포함한 Windows 배포(serve_waitress.py)는 이 변수를 아예 안 읽고 trusted_proxy='127.0.0.1'이 하드코딩돼 있음을 직접 확인 — 그 하드코딩이 의미를 가지려면 BOKGUON_HOST가 루프백을 유지해야 하는데(serve_waitress.py 자신의 기본값이 '0.0.0.0'이라 설정을 빠뜨리면 외부에 그대로 노출됨을 직접 확인), MG-06은 그 진짜 전제조건 대신 gunicorn 전용 변수만 검사해 왔다 — manage.py 자신이 이미 274행에서 쓰는 os.name=='nt' 분기(WSGI 서버 설치 확인)를 이 특정 검사에는 안 맞췄던 것. 실제 운영 위험은 지금 당장 없음(이 PC의 실제 .env는 BOKGUON_HOST·FORWARDED_ALLOW 둘 다 이미 올바른 값) — 문제는 점검 도구 자체가 이 플랫폼에서 진짜 방어선을 안 본다는 것: BOKGUON_HOST가 실수로 0.0.0.0 등으로 바뀌어도 이 검사는 못 잡고(FORWARDED_ALLOW가 겉보기에 정상이면 그대로 통과), 반대로 안전한 Windows 배포도 FORWARDED_ALLOW를 안 채웠다는 이유만으로 불필요하게 막을 수 있었다. 트레이드오프 없는 '그냥 고치면 되는 것'(점검 도구 정확성 개선, 서버 런타임 동작 자체는 무변경). 같은 라운드 각도2(지오코딩 캐시/저장 무결성)는 geo.py에 캐시 자체가 없어(매 호출 순수함수/라이브 API) 캐시오염·키충돌 우려는 구조적으로 해당없음, 좌표 저장 6개 지점 전부 공용 _picked_coords()(한반도 범위검증)를 거치고 라운드153/154가 이미 심은 주소변경시 좌표 무효화 로직도 여전히 유효함을 확인 — 전부 클린. 부수 발견 2건은 낮은 우선순위/제품판단으로 기록만 하고 이번 라운드에서 구현하지 않음(YAGNI): (1) geocode_fill.py 배치 내 중복주소 재조회는 순수 성능낭비일 뿐 정확성 문제가 아니라 저빈도 정비스크립트에 실익이 작아 보류. (2) 사건(cases)의 좌표 강제초기화(clear:true)와 대칭되는 협력사(partners) 전용 API가 없는 비대칭은 의도적 설계인지 단순 누락인지 코드만으로 판단 불가해 제품판단 필요로 분류. 고침: manage.py의 MG-06을 os.name=='nt'로 분기 — Windows 경로는 BOKGUON_HOST가 루프백(127.0.0.1/localhost/::1)인지 검사(기본값 '0.0.0.0' 처리 포함, 비어있음을 안전하다고 착각하지 않음), 그 외(Linux/ gunicorn) 경로는 기존 BOKGUON_FORWARDED_ALLOW 검사를 그대로 유지. 독립검증: serve_waitress.py의 하드코딩 값·기본 HOST값 직접 확인, BOKGUON_FORWARDED_ALLOW를 읽는 코드가 gunicorn_conf.py 뿐임을 grep 재확인, manage.py를 다루는 기존 테스트 7개(round65/66/67/121/183/184/305) 전부 BOKGUON_ENV=dev로 cmd_check를 실행해 이번에 고친 if prod: 블록 자체가 실행되지 않음을 확인(충돌 없음, 7개 전부 재실행해 재확인). 회귀테스트(test_scan_round432_fixes.py, 14개 검사)는 실제 이 환경(Windows)에서 cmd_check를 그대로 실행해 HOST=0.0.0.0(미설정 포함)이면 새 검사가 실패를 내고 HOST=127.0.0.1이면 더는 막히지 않음을 실측 — 첫 실행 14/14 통과. 옛 코드로 되돌리면 (a) FORWARDED_ALLOW가 겉보기에 정상값이어도 HOST=0.0.0.0(진짜 위험)을 전혀 언급조차 안 하고, (b) HOST=127.0.0.1(안전)인데도 FORWARDED_ALLOW가 비었다는 이유만으로 불필요하게 막는 양방향 오판을 서브프로세스로 직접증명 후 원본 복원. manage.py는 app.py가 import하는 모듈이 아닌 독립 CLI 스크립트라 이 수정만으로는 서버 재기동 불필요 — 운영 서버(app.py) 동작에 영향 없음, BUILD_HASH 로테이션 없음(재기동 자체를 안 함)."),
    ("test_scan_round433_fixes.py", "스캔 433라운드 회귀 — 하자 severity 검증 우회(평점 조작 벡터) + happy_calls 고아행 사각지대, 2건. 정밀조사 Agent가 각도1(협력사 평점 계산 정확성·조작가능성)에서 발견 — api_defect_update()(app.py:14147-)의 severity 검증(round109가 추가)이 바로 옆 형제 cost_bearer 와 다른 술어를 썼다: d.get('severity') and ...(truthy)라 severity=''/null 이면 검증 자체가 스킵되고, 뒤이은 범용 저장 루프는 'severity' in d(존재)만 보고 빈 값을 그대로 저장한다. RATING_PENALTY.get(severity,0.1)(app.py:13917)이 빈 값에 0.1('보통')을 조용히 적용해 '중대'(0.2) 하자의 평점 차감이 절반으로 줄어드는 평점 조작 벡터가 됨을 직접 확인(도달권한은 중간관리자 이상으로 제한돼 내부자/탈취계정 위협모델). 같은 라운드 각도2(사건 하드삭제 캐스케이드)에서 발견 — manage.py 의 CASE_CHILD_TABLES(cmd_check 고아탐지·cmd_prune_orphans 정리가 공유하는 단일 목록, '점검과 정리가 같은 목록을 봐야 한다'는 자기 주석까지 있음, round158이 이미 형제 4곳을 이 원칙으로 추가)에 happy_calls(case_id NOT NULL UNIQUE, db.py:802)가 빠져 있었음을 직접 확인 — go-live(cmd_go_live)는 이 표를 조건 없이 통째로 비워 우연히 사각지대를 피하지만, 사건 하나를 직접 SQL로 지우는 경우(round158이 이미 '실제 사고'로 증언한 시나리오)엔 이 표만 고아로 남아 check·prune-orphans 둘 다 못 잡고 partner_rating() 의 해피콜 평균에 삭제된 사건의 점수가 영구히 남는다. 각도1의 나머지(트리거 일관성·판정시점 신선도·무효화 데이터 오염 여부)는 전부 클린, 각도2의 나머지(캐스케이드 순서·완전성·사진파일 정리·soft-delete 부재)도 전부 클린 확인. 독립검증: 두 결함 모두 직접 코드대조로 재현, round109/158 기존 테스트를 실행해 이번 수정과 충돌 없음을 확인(각 15/15·11/11 통과, 둘 다 특정 항목의 존재만 부분문자열로 확인해 새 항목 추가에 영향 없음). 고침: (a) severity 검증을 cost_bearer 와 완전히 같은 존재(presence) 검사로 통일(if 'severity' in d and ...). (b) CASE_CHILD_TABLES 에 'happy_calls' 추가 — 형제 4곳(round158)과 완전히 같은 패턴, 새 로직 불필요. 둘 다 트레이드오프 없는 '그냥 고치면 되는 것'. 회귀테스트(test_scan_round433_fixes.py, 17개 검사)는 실제 Flask+DB로 severity=''/null 둘 다 400 거부·기존 값 불변·partner_rating() 의 실제 차감값이 여전히 0.2로 정확함을 실측, happy_calls 는 실제 cmd_check 출력에 고아 경고가 뜨고 cmd_prune_orphans 로 실제 정리됨을 실측 — 첫 실행 17/17 통과. 옛 코드로 되돌리면 (a) severity='' 가 200으로 그대로 저장되고 실제 차감이 0.1로 반토막나며, (b) cmd_check 가 이 고아를 전혀 언급 안 하고 prune-orphans 로도 안 지워짐을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 함수 변경이라 재기동 필요, manage.py 는 app.py가 import하는 모듈이 아닌 독립 CLI라 그쪽 변경만으로는 재기동 불필요하나 이번엔 app.py도 함께 바뀌므로 서버 재기동 실시, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round434_fixes.py", "스캔 434라운드 회귀 — 사진 검수 승인 재호출 시 알림·감사로그 중복 + 반려취소(unreject)의 확인~갱신 사이 경합 미방어, 2건. 정밀조사 Agent가 각도1(사진 검수 워크플로 권한·상태전이)에서 발견 — 사진검수 3개 라우트(api_photos_approve·api_photo_reject·api_photo_unreject) 전부 require_role('중간관리자')로 잠겨 있어 무관한 제3자 보험사는 애초에 호출 자체가 불가함을 직접 확인(보험사 세션은 session['admin']을 절대 세팅 안 함), 사건상태(case.status) 불일치도 정산생성 관문(대기/반려 사진 있으면 정산 자체를 막음)·재반려 방지(EVIDENCE_LOCKED)·업로드 차단(시공중/검수대기 상태에서만 업로드 가능) 삼중방어로 클린 재확인. 신규 발견: api_photos_approve()(app.py:12316-)는 이번에 새로 승인된 장수(approved, UPDATE rowcount)가 0이어도 notify()·DB.log()를 무조건 실행했다 — 형제 api_photo_reject()는 이미 rowcount==0이면 409로 끝내 통지·로그 없이 종료하는데(반려된 사진 재반려 방지), 승인 쪽만 재클릭·새로고침 후 재요청·2관리자 동시진행 시마다 협력사에게 중복 알림톡이 나가고 감사로그에 '(이번 0장)' 줄이 계속 쌓였음을 직접 확인. api_photo_unreject()(app.py:12495-)는 BEGIN IMMEDIATE도, UPDATE의 상태조건(WHERE review_status=...)도 없어(단순 WHERE id=?) 확인(review_status!='반려' 체크)과 갱신 사이가 잠기지 않은 TOCTOU였음을 직접 확인 — 형제 api_photo_reject()는 이미 BEGIN IMMEDIATE + 'WHERE id=? AND review_status<>'반려''의 rowcount 가드로 이 문제를 올바르게 막고 있어 같은 파일 안에 정답 패턴이 이미 있었다. 둘 다 트레이드오프 없는 '그냥 고치면 되는 것', 응답 계약은 그대로 유지. 같은 라운드 각도2(접속기록 보존기간 파기)는 login_attempts·access_log 파기가 처리방침 실제 보유기간(2년=730일, 라운드지시문이 가정한 365일과 다름을 직접 코드·문서 대조로 정정)과 정확히 일치함을 확인(클린), 배포 스크립트의 자동 예약등록(Windows 작업스케줄러·Linux cron)도 서로 일치·존재 확인(클린). 다만 activity_log(라운드208이 추가한 로그인 실패/잠금 이벤트 포함)는 그 어떤 파기 경로에도 없어 무기한 누적됨을 발견 — 전사 업무감사이력과 뒤섞여 있어 일괄삭제 시 5년 보관 의무가 있는 협력업체 계약정보 감사증적까지 훼손할 위험이 있는 진짜 트레이드오프라 '제품판단 필요'로 분류, 임의로 우선순위를 매기지 않음(사용자 결정 대기 목록에 추가). 독립검증: api_photo_reject()의 기존 정답 패턴 직접 대조, round14/197/339/71 등 관련 기존 테스트 4개 전부 실행해 이번 수정과 충돌 없음을 확인(각 20/12/27/17 통과). 고침: (a) approve의 notify/log 호출을 if approved: 로 감싼다. (b) unreject에 형제와 동일한 BEGIN IMMEDIATE + rowcount 가드를 추가한다. 회귀테스트(test_scan_round434_fixes.py, 16개 검사)는 approve 재호출 시 알림·로그가 안 늘어남을 실측, unreject는 실제 두 스레드가 같은 사진을 동시에 반려취소해 정확히 하나만 성공(200)하고 감사로그도 정확히 1건만 남음을 실측(round50/424와 같은 실스레드 기법) — 첫 실행 16/16 통과. 옛 코드로 되돌리면 (a) 재호출마다 알림이 실제로 2건까지 쌓이고, (b) 동시 반려취소 둘 다 200으로 성공해 감사로그가 2건 남음을 서브프로세스로 직접증명 후 원본 복원. app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round435_fixes.py", "스캔 435라운드 회귀 — 두 각도 모두 결함 없음(클린), 코드 수정 없음. 정밀조사 Agent(각도1: 사진·문서 서빙 라우트의 소유권(IDOR) 검사, 각도2: 관리자 자기잠금·최후 최고관리자 보호)가 조사, 둘 다 이미 올바르게 방어돼 있음을 실제 Flask test_client로 확인. 사진·문서를 실제로 내보내는 라우트는 앱 전체에서 api_photos 파일서빙 하나뿐이고 그 유일한 인가관문 _photo_visible_to()(app.py:11414-)가 세션 조직이 그 사진이 속한 사건의 실제 당사자인지 검사함을 확인, 사건상세·사진목록·하자사진도 각각 insurer_id/partner_id 정확일치로 막음을 확인. 다만 test_partner_leak.py(협력사 쪽, 라이브서버 대상)에 대응하는 보험사 쪽 IDOR 회귀 테스트가 이 저장소에 하나도 없었음을 발견 — 코드는 클린이지만 향후 리팩터링을 잡아줄 자동회귀가 없는 커버리지 공백이라 트레이드오프 없는 '그냥 고치면 되는 것'으로 분류. 관리자 계정 관리는 이미 본인계정 삭제 차단·최후 최고관리자 삭제·강등 차단을 갖췄고 둘 다 BEGIN IMMEDIATE로 확인~변경을 원자적으로 묶어 두 최고관리자가 서로를 동시에 지우거나 강등해도 최소 1명은 반드시 생존함을 실스레드 동시성으로 실측, _account_alive()가 매 요청마다 역할을 재조회해 강등이 다음 요청부터 바로 먹음(세션캐시 우회 불가)도 확인. admins 테이블엔 is_active류 컬럼이 아예 없어 비활성화 우회 경로 자체가 존재하지 않음도 확인. 이번 라운드는 버그를 고친 게 아니라 이미 맞는 코드를 실측으로 증명했을 뿐이므로, 회귀테스트(test_scan_round435_fixes.py, 37개 검사)는 두 핵심 방어(_photo_visible_to의 보험사 분기·admin_delete의 최후 최고관리자 가드)를 각각 한 줄씩 임시로 무력화해(app.py를 그 즉시 복원하는 try/finally로 보호) 이 테스트가 실제로 그 상태를 잡아내는지 (공허한 통과가 아닌지) 증명 — 각도1 무력화 시 타 보험사가 실제로 200 (유출)을 받고, 각도2 무력화 시 두 최고관리자가 서로를 동시삭제하면 실제로 0명(완전 락아웃)까지 떨어짐을 서브프로세스로 직접증명한 뒤 app.py를 원본과 바이트단위로 동일하게 복원 완료 확인 — 첫 실행 37/37 통과. 무거운 라이브서버(port 8799) 방식 대신 이 세션의 다른 test_scan_round*.py 들과 같은 인프로세스 스크래치DB 방식으로 작성해 run_all_tests.py --quick 에 바로 편입(비례성 판단). 코드 변경 없음, app.py는 검증 종료 시점에 원본과 완전히 동일 — 서버 재기동 불필요."),
    ("test_scan_round437_fixes.py", "스캔 437라운드 회귀 — 보험사 정지(중지) 게이트가 진행 중 사건(cases)을 전혀 보지 않던 결함, 1건. 정밀조사 Agent가 각도1(협력사·보험사 탈퇴/정지 시 진행중 사건 처리)에서 발견 — 실제 도달 가능한 죽은 상태값부터 먼저 확인(_DEAD_PARTNER/_DEAD_INSURER 블랙리스트 중 실제 세팅 가능한 값은 협력사=퇴출/심사중, 보험사=중지뿐임을 PARTNER_STATUSES/INSURER_STATUSES 대조로 확정). 협력사 퇴출 게이트(_partner_demote_gate, app.py:8017-)는 이미 cases(시공중/완료보고지연/검수대기/정산진행)·미지급정산·열린하자 셋 다 검사해 정상 동작함을 재확인(결함 아님). 그런데 형제인 보험사 정지 게이트(_insurer_exit_load, 8040-)는 settlements(완료승인대기)·field_agreements(검토중) 두 가지만 보고 cases 자체를 검사하는 코드가 전혀 없었다 — settlements 행은 완료보고~검수 단계에 가서야 생기므로, 입찰중(공고만 뜬 상태)이거나 낙찰 직후 시공중(완료보고 전이라 정산행이 아직 없는) 사건은 이 두 조건 어디에도 안 걸려 확인(confirm_demote) 없이 그대로 200으로 '중지' 처리됨을 실측 확인(대조군으로 미승인 정산이 있는 보험사는 이미 409로 정상 차단됨도 함께 확인 — 라운드136 방어는 살아있고 범위만 좁았던 것). 게다가 보험사가 중지된 뒤에도 협력사는 그 보험사 소유 공고에 정상적으로 계속 투찰 가능함을 실측(api_partner_bid, app.py:4949-5077대에 사건의 insurer 상태를 확인하는 코드가 전혀 없음을 코드 전문 대조로 확인) — 경매가 아무 제지 없이 계속 진행돼 나중에 완료보고→보험사 승인 단계에 가서야(그 계정은 이미 로그인이 막혀 관리자가 대신 승인할 방법이 없음) 영구 정체가 드러난다. 트레이드오프 없는 '그냥 고치면 되는 것' — 협력사 쪽엔 이미 있는 패턴을 보험사 쪽에도 완성하는 것뿐. 독립검증: _insurer_exit_load/_insurer_demote_gate·_partner_exit_load·api_partner_bid 전체를 직접 Read로 대조, 기존 테스트 3개(round213/253/331, 전부 insurer PATCH '중지' 관련)를 실행해 이번 수정과 충돌 없음을 확인(셋 다 사건 자체가 없거나 raw SQL로 상태를 직접 심어 게이트를 안 거치는 구조라 무관 — 3개 전부 재실행 통과). 고침: _insurer_exit_load()에 형제와 같은 패턴으로 'cases WHERE insurer_id=? AND CASE_OPEN_SQL(미종결 전체) AND is_demo=0' 검사를 추가(파트너와 달리 보험사는 사건 생성 시점부터 소속이 붙어 있어 파트너보다 넓은 CASE_OPEN_SQL 기준이 필요), _insurer_demote_gate()의 차단조건·안내문에 active_count 반영. 각도2(정산 지급완료 동시성)는 api_settlement_paid/paid_bulk 둘 다 함수 첫 줄에서 BEGIN IMMEDIATE로 쓰기잠금을 먼저 잡고 조건부 UPDATE+rowcount 재확인까지 이중방어함을 실스레드 3가지 시나리오(단건 동시경합·단건 대 일괄 교차경합·순차 대조군)로 실측 확인, 감사로그 중복도 notify 중복발송도 없음(이 두 라우트엔 애초에 notify 호출 자체가 없음) — 완전 클린, 수정 없음. 회귀테스트(test_scan_round437_fixes.py, 14개 검사)는 입찰중·낙찰직후시공중(정산행 없음) 두 시나리오 모두 확인 없이는 409로 막히고 확인+사유로는 정상 통과함을 실측, 데모전용 사건은 카운트에서 빠지는 대조군·업무가 정말 없는 보험사는 기존 NEED_REASON 흐름이 그대로 유지되는 대조군까지 확인 — 첫 실행(사소한 자체 버그 수정 한 번 거친 뒤) 14/14 통과. 옛 코드로 되돌리면 입찰중 사건이 있어도 실제로 200과 함께 DB까지 '중지'로 바뀜을 서브프로세스로 직접증명 후 원본 복원(app.py 최종 바이트단위 동일 확인). 부수 발견 2건은 이번 라운드 범위 밖으로 분류해 구현하지 않음(YAGNI, 다음 라운드 후보로 기록): (1) 사건상세/목록 API(api_case_detail·api_insurer_case_detail·api_cases)가 담당 협력사·발주 보험사의 상태(퇴출/중지)를 전혀 안 보여줘, confirm으로 강행된 뒤에도 그 사실을 화면 어디서도 볼 수 없는 사후 가시성 공백. (2) api_partner_bid에 사건의 insurer 상태 확인을 추가하는 방어심화 — 이번 게이트 수정으로 신규 정지부터는 자연히 해소되는 부수효과라 우선순위 낮음. app.py 자신의 함수 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round441_fixes.py", "스캔 441라운드 회귀 — /api/insurer/defects·/api/partner/defects의 SELECT * 스키마드리프트 위험, 2건. 정밀조사 Agent가 각도1(관리자 내부메모가 협력사·보험사에 노출되는 경로)을 조사하던 중 부수 발견 — 원래 질문인 memos 테이블·partners.contact_note·insurers.webhook_secret/api_key_hash 등 진짜 관리자 전용 필드는 전부 관리자 전용 라우트에서만 다뤄지고 협력사·보험사 API와 JOIN되는 자리가 없어 완전 클린임을 실제 Flask test_client로 61/61 실측 확인(코드 변경 없음, 이 파일 범위 밖). 그 과정에서 형제 라우트 api_insurer_bids(라운드422가 이미 bids 서브쿼리에서 같은 유형을 고침, '현재 컬럼 전부를 그대로 나열해 동작은 완전히 똑같이 유지하면서 화이트리스트로 명시한다'는 전례)와 같은 패턴이 defects 목록 두 곳에는 아직 남아있음을 발견 — SELECT * FROM defects로 통째로 받아 jsonify(data) 직결, 화이트리스트 없음. 지금은 defects 테이블 27개 컬럼(기본 23+마이그레이션 4: dispute_reason·disputed_at·dispute_resolved_at·is_demo) 전부가 비민감이라 실제 유출은 없음을 db.py 스키마 전수 대조로 직접 확인했지만, 나중에 관리자 전용 컬럼이 이 테이블에 추가되는 순간 이 두 자리만 조용히 새는 스키마드리프트 구조 — 실제로 스크래치 DB에 가상의 미래 컬럼(admin_secret_note)을 ALTER TABLE로 추가해 재현: 옛 코드는 그대로 흘려보내고 새 코드(화이트리스트)는 막음을 서브프로세스로 직접 증명. 트레이드오프 없는 '그냥 고치면 되는 것' — 라운드422가 세운 전례를 기계적으로 확장하는 것뿐. 각도2(검색·필터 API의 SQL 조합 방식 전수)는 완전 클린 — 공용 헬퍼(search_filters/_kw_like_clause/_sq/_sqp)가 값은 전부 ?바인딩·LIKE는 이스케이프 처리, 컬럼명은 전부 호출부의 파이썬 리터럴이지 요청 파라미터에서 온 적이 없음을 확인. 사용자 제어 ORDER BY 기능 자체가 코드베이스에 없음을 전수 grep으로 확인(유일한 sort= 파라미터는 닫힌 삼항이라 사용자 텍스트가 직접 안 들어감). 실제 악의적 페이로드(SQL 인젝션 시도 다수, DROP TABLE 포함)를 여러 공개·관리자 라우트에 실제 발사해 전부 무해함을 실측 확인(테이블 생존 확인 포함) — 코드 변경 없음. 고침: api_insurer_defects()·api_partner_defects() 둘 다 defects의 현재 컬럼 27개를 그대로 나열해 화이트리스트로 명시, 동작은 완전히 동일 유지(제거된 필드 없음). 독립검증: 두 각도 모두 에이전트의 스크래치 스크립트 재실행으로 동일 결과(61/61, SQL인젝션 전부 무해) 재확인, defects 스키마 전체(27개 컬럼)를 db.py에서 직접 대조해 화이트리스트 누락이 없음을 확인, 기존 테스트 6개(round22/53/61/112/118/244, 이 두 라우트를 다루는 UNIT계열 전부) 실행해 충돌 없음 확인. 회귀테스트(test_scan_round441_fixes.py, 13개 검사)는 기존 실제 컬럼(기본+마이그레이션) 값이 새 화이트리스트로도 전부 그대로 옴을 실측(회귀 없음), 가상의 미래 민감컬럼을 ALTER TABLE로 추가해 옛 코드는 흘려보내고 새 코드는 막음을 서브프로세스로 직접증명 후 app.py 원본 복원까지 확인 — 첫 실행(테스트 자체의 문자열매칭·임시DB재사용 버그 2건을 직접 잡아 수정한 뒤) 13/13 통과. 부수 발견(범위 밖, 다음 라운드 후보로 기록): 같은 유형의 무화이트 리스트 SELECT c.* 패턴이 cases 테이블 기준으로 보험사 쪽 3개 라우트(api_insurer_dashboard·api_insurer_case_detail·api_insurer_bids 자신의 case 부분)에도 있음을 발견 — 협력사 쪽 자매 라우트는 이미 명시적 화이트리스트인데 보험사 쪽만 빠진 비대칭. cases는 37개+ 컬럼에 프론트엔드 소비처가 defects보다 훨씬 많아(대시보드·상세화면 등) 안전하게 좁히려면 템플릿·JS 파일까지 교차확인하는 별도의 전용 라운드가 필요해 이번 라운드 범위 밖으로 분류. 또한 조사 과정에서 app.py:124의 JSON_AS_ASCII=False 설정이 Flask 3.1.3에서 더는 반영되지 않는(죽은 설정 키) 별개 결함도 발견됐으나 이는 순수 응답크기/가독성 문제(모든 JSON파서가 유니코드 이스케이프 표기를 원문과 동일하게 디코딩하므로 기능적 차이 없음)라 이번 두 각도와 무관한 별도 후속작업으로 분리(코드 수정 안 함). app.py 자신의 함수 2곳 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round443_fixes.py", "스캔 443라운드 — 보험사 쪽 cases SELECT * 스키마드리프트 3곳(백로그 처리). 라운드441이 defects 목록 2곳을 고치면서 부수 발견하고 범위 밖으로 미뤄 둔 항목 — cases는 37개+(실측 PRAGMA table_info로 정확히 60개) 컬럼에 소비처가 많아 별도 라운드가 필요하다고 판단했던 그 작업을 이번 라운드에서 직접 완료했다(새 조사 없이 이미 스코프된 백로그를 처리 — 라운드442가 완전 클린으로 끝나 새 코드변경이 없었던 김에 미루지 않고 바로 처리). api_insurer_dashboard()(app.py:3415-)의 사건목록, api_insurer_case_detail()(9560-)의 사건상세, api_insurer_bids()(4220-)의 사건단건 조회 셋 다 SELECT c.*/SELECT *로 cases를 통째로 받아 화이트리스트 없이 그대로 반환하고 있었다 — 라운드422(bids 서브쿼리)·라운드441(defects 목록)이 이미 겪은 것과 똑같은 스키마드리프트 유형. 협력사 쪽 자매 라우트는 이미 명시적 화이트리스트라 비대칭이었다. cases 테이블 실제 컬럼을 PRAGMA table_info로 직접 조회해 60개(기본 18+마이그레이션 42, victim_name/victim_phone/track_token/track_token_hash 등 민감해 보이는 필드 다수 포함)임을 확정 확인 — settlements 테이블(24개 컬럼)에도 같은 유형이 api_insurer_dashboard 안에 별도로 있음을 함께 발견했으나 계좌정보 등 진짜 민감 컬럼이 없음을 스키마 대조로 확인해 이번 라운드 범위 밖으로 분리(다음 라운드 후보). 고침: cases의 현재 컬럼 60개 전부를 나열한 공용상수 CASE_COLS_SQL(CASE_OPEN_SQL 바로 아래)을 신설해 세 자리 모두 재사용 — 컬럼이 한 곳에 모여 있어 나중에 하나만 갱신되는 사고를 막는다. auctions와 JOIN하는 두 자리(dashboard·detail)는 id·status·low_price·created_at 등 이름이 겹쳐 c. 접두어가 필요해 상수 자체를 c. 접두어 포함으로 정의했고, 원래 별칭이 없던 bids 자리는 FROM cases c로 별칭만 붙여 그대로 재사용했다. 동작은 완전히 동일 유지(제거된 필드 없음 — 민감해 보이는 필드도 지금 이미 나가고 있던 그대로 유지, 그 값을 빼는 것은 이 하드닝과 무관한 별도의 제품판단이라 이번엔 안 건드림). 트레이드오프 없는 '그냥 고치면 되는 것'. 독립검증: cases/settlements/bids 스키마를 실제 초기화된 DB에서 PRAGMA로 직접 조회해 컬럼 목록을 확정(수작업 마이그레이션 파싱보다 신뢰도 높음), 기존 테스트 13개(round422/285/303/213/105/101/114/78/47/46/feature_victim_track — 이 세 라우트를 다루는 UNIT계열 전부) 실행해 무관함 확인(round3/4_fixes.py는 HTTP계열이라 별도 서버환경변수 없이는 애초에 실행 자체가 안 되는 것을 확인, 무관). 회귀테스트(test_scan_round443_fixes.py, 19개 검사)는 victim_name·victim_phone·track_token·track_token_hash·note·manager·lat/lng·award_amount 등 9종 컬럼값이 세 라우트 전부에서 기존과 동일하게 옴을 실측(회귀 없음), case detail의 기존 c.pop('is_demo') 동작도 화이트리스트 도입 후 그대로 유지됨을 확인, 스크래치 DB에 ALTER TABLE로 가상의 미래 민감컬럼(admin_secret_note)을 추가해 옛 코드(c.*)는 세 라우트 전부 그대로 흘려보내고 새 코드(화이트리스트)는 셋 다 막음을 서브프로세스로 직접증명 후 app.py 원본 복원까지 확인 — 첫 실행 19/19 통과. app.py 자신의 함수 3곳 변경(+공용상수 1개 신설)이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round444_fixes.py", "스캔 444라운드 — 관리자 대신로그인 기능(해당없음)·세션쿠키 보안속성 (HttpOnly/SameSite/Secure) 실측검증. 정밀조사 Agent가 각도1(관리자 대신로그인/사칭 기능과 감사흔적)에서 확인 — session['partner_id']/session['insurer_id']를 세팅하는 코드가 app.py 전체에 각 계정 자신의 로그인 라우트 딱 1곳씩(2898·3095)만 존재함을 grep 전수로 확인, 관리자 콘솔·라우트 어디에도 이 세션값을 대신 주입하는 코드가 0건이라 대신 로그인 기능 자체가 해당없음으로 확정. 유일한 개입 경로인 임시비밀번호 재발급은 이미 관리자 본인 명의 감사로그(DB.log)+계정 당사자 알림톡 통지라는 이중 안전장치를 갖추고 있음을 확인(app.py:7701-7751). 각도2(세션쿠키 보안속성)는 app.py:111-116의 SESSION_COOKIE_HTTPONLY=True·SAMESITE=Lax·SECURE=IS_PROD 설정을 실제 라이브서버(스크래치 DB, 운영동일 prod 모드로 임시 기동 후 정상 종료)로 실측 — HttpOnly는 실제 크로미움 브라우저로 로그인 후 document.cookie가 빈 문자열임을 확인(세션은 정상 유지되는데 JS로는 안 읽힘), Secure는 원문 Set-Cookie 헤더에 명시적으로 존재함을 직접 캡처하고 표준 http.cookiejar 클라이언트로는 평문 127.0.0.1 접속 시 쿠키가 재전송 안 됨을 재현했으나 실제 크로미움 브라우저는 루프백 주소를 신뢰가능 출처로 예외 처리해 쿠키가 정상 유지됨을 실측 확인 — 이는 이 서비스의 실제 문서화된 운영절차(관리자가 서버 PC에서 http://127.0.0.1:8771/admin 직접 접속, deploy\외부접속_안내.md)와 정확히 일치하는 정상 동작. SameSite=Lax도 기존 CSRF 방어와 충돌 없이 상호보완함을 확인(CSRF 토큰은 더블서브밋이 아니라 세션에 저장되는 synchronizer 토큰 패턴임을 코드로 재확인 — 서브도메인 쿠키주입으로 우회되는 더블서브밋 특유의 취약클래스가 애초에 성립 안 함). 둘 다 결함 없음, 코드 수정 없음. 다만 조사 과정에서 커버리지 공백 발견(결함 아님, 방법론 참고사항): run_all_tests.py가 데모데이터 시딩 문제(라운드406) 때문에 BOKGUON_ENV를 항상 dev로 강제해, SESSION_COOKIE_SECURE=True가 되는 운영 조합이 이 저장소의 어떤 배터리에서도 한 번도 실행된 적이 없었음 — smoke_test.py는 이미 이 사실을 인지한 주석이 있고(dev 모드 인스턴스로 우회), test_otp.py의 자체 Client는 Set-Cookie를 수동파싱해 Secure 속성 자체를 무시하는 방식이라 이 문제를 우연히 회피, test_session_liveness.py는 http.cookiejar 기반이라 prod 모드로 돌리면 실제로 깨질 수 있음(단 실배포 절차는 smoke_test.py를 진짜 HTTPS 도메인에 대고 돌리므로 실사용엔 문제 없음). 코드는 이미 올바르므로 고칠 결함이 아니라 그 정확성을 보증하는 자동회귀가 없었던 것 — 이 라운드가 그 공백만 메운다(트레이드오프 없는 '그냥 고치면 되는 것'과 '제품판단 필요' 어느 쪽도 아닌 순수 커버리지 보강). 독립검증: IS_PROD·app.config.update() 정의를 직접 Read로 대조, session 세션키 쓰기 지점이 정확히 2곳뿐임을 재확인. 회귀테스트(test_scan_round444_fixes.py, 13개 검사)는 app.py를 BOKGUON_ENV=dev/prod 각각으로 서브프로세스에서 새로 import해(모듈 최상위 상수라 프로세스당 한 번만 평가) 실제 app.config 쿠키설정 3종을 직접 확인 — dev는 Secure=False, prod는 Secure=True(이 저장소 최초의 이 조합 실측)를 확인, HttpOnly·SameSite는 환경과 무관히 항상 고정됨도 확인. 탐지력 증명으로 Secure를 실수로 False 하드코딩한 변형을 만들어 prod 모드에서도 실제로 꺼짐을 서브프로세스로 직접증명(이 테스트가 그런 실수를 잡아낼 수 있다는 뜻) 후 app.py 원본 복원까지 확인 — 첫 실행 13/13 통과. 코드 변경 없음(순수 테스트 신설), 서버 재기동 불필요, BUILD_HASH 로테이션 없음."),
    ("test_scan_round445_fixes.py", "스캔 445라운드 — JSON_AS_ASCII=False가 Flask 3.x에서 죽은 설정 키였던 결함, 1건(라운드441이 발견하고 범위 밖으로 미뤄둔 백로그 중 하나를 이번에 처리, 나머지 하나인 settlements 화이트리스트는 실제로 세어보니 1곳이 아니라 14곳에 퍼져 있고 민감 컬럼이 없음이 확정돼 있어 규모 대비 가치가 낮아 이번에도 보류하고 백로그 기록만 정정). app.py:124에 있던 JSON_AS_ASCII=False는 Flask 2.x 시절 설정 키인데, 설치된 Flask 3.1.3은 이 값을 전혀 안 읽음을 직접 실측 확인 — app.config에는 그대로 저장돼 있지만 실제 동작은 app.json.ensure_ascii가 결정하며 그 값은 여전히 기본값 True로 남아 있어, 지금까지 모든 JSON 응답의 한글이 의도와 달리 유니코드 이스케이프 표기로 나갔다(기능 차이는 없음 — 모든 JSON 파서가 두 표기를 동일하게 디코딩 — 응답 크기와 로그 가독성 문제였을 뿐). 고침: 죽은 설정을 제거하고 app.json.ensure_ascii = False로 교체 — 원래 의도를 실제로 살리는 트레이드오프 없는 개선. 독립검증: 고치기 전 app.json.ensure_ascii가 실제로 True임을(app.config 값과 실제 동작이 갈린다는 것을) 먼저 재현확인한 뒤 수정, Flask 버전·설정 재조회로 재확인. 회귀테스트(test_scan_round445_fixes.py, 11개 검사)는 실제 /api/version과 로그인 후 /api/me 응답 둘 다 한글이 리터럴 UTF-8로 그대로 옴을 실측(공용 jsonify 경로 전체가 영향받음을 확인), 옛 방식(app.config만 세팅)을 재현하면 실제로 ensure_ascii가 True로 남고 응답에 유니코드 이스케이프가 섞여 나감을 서브프로세스로 직접증명 후 app.py 원본 복원까지 확인 — 테스트 자체의 과잉 엄격 검사(주석의 옛 키 이름 언급과 실제 설정 자리를 혼동) 1건을 직접 잡아 수정한 뒤 11/11 통과. app.py 자신의 설정 변경(응답 인코딩 표기만 바뀌고 JSON 의미·구조는 완전히 동일)이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round446_fixes.py", "스캔 446라운드 회귀 — 백업/복구 결함 2건. 정밀조사 Agent가 각도1(DB 백업의 실제 복구 가능성)에서 발견, 둘 다 스크래치 환경에서 실제 재현: (1) cmd_restore()(manage.py:1350-)가 파일 무결성(PRAGMA integrity_check)만 확인하고 지금 .env의 BOKGUON_ENC_KEY로 DB 안의 암호화된 계좌정보를 실제로 열 수 있는지는 전혀 확인하지 않았다 — cmd_check()(246-265행)는 이미 이 왕복확인 로직을 갖고 있는데 정작 키가 안 맞을 위험이 가장 큰 순간(다른 서버·다른 .env로 복구하는 바로 그 시점)엔 아무도 그 검사를 부르지 않았다. 실측: 서로 다른 키A/B로 암호화한 계좌를 스크래치 DB에 저장→백업→키를 B로 바꾼 뒤 복구하면 무결성 검사 까지 전부 정상 통과하고 crypto_util.decrypt()가 실패를 삼켜 조용히 빈 문자열이 됨(화면상 계좌 미등록과 구분 불가) — 되돌릴 수 없는 데이터 손실인데 알아챌 방법이 이 명령 안에는 없었다. (2) cmd_backup()의 보관기간(기본 30일) 정리 루프(1341행 부근)에 예외 방어가 없었다 — 바로 3줄 위 같은 함수 안의 형제 루프(이전 실행 찌꺼기 .part 파일 정리)는 try/except OSError로 방어돼 있는데 이 루프만 없었다. 실측: 정리 대상 파일 하나를 다른 프로세스가 물고 있는 상태(백신 실시간검사·오프사이트 동기화 등 Windows에서 드물지 않은 조건)로 만들어 cmd_backup()을 실행하면 함수 전체가 PermissionError로 죽었다(그날 백업 자체는 이미 끝나 있었는데도 실패로 기록됨) — 같은 파일이 매일 잠긴다면 보관기간 정리가 영구히 멈춰 백업이 무한정 쌓일 수 있는 잠재적 가용성 리스크였다. 두 결함 모두 트레이드오프 없는 '그냥 고치면 되는 것'. 같은 라운드 각도2(협력사 평점 계산의 시간경과 처리)는 완전 클린 — partner_rating()이 시간창 없이 전체 이력을 영구 반영함을 실측 확인했으나, manage.py의 개인정보파기 로직(cmd_prune_personal) 자신의 주석이 '하자 감점 이력을 지우면 오래된 협력사일수록 평점이 부당하게 좋아 보인다'며 이미 이 정책을 명시적으로 검토·채택했음을 교차확인 — 제품판단이 필요한 문제가 아니라 이미 내려진 판단과 정합적인 의도된 설계, 코드 수정 없음. 캐시(partners.rating) 갱신 트리거도 app.py 전체에서 하자 UPDATE 3곳·해피콜 INSERT 1곳 전수 확인해 전부 정확히 refresh_partner_rating()을 호출함을 확인(클린) — 이 결론은 라운드433 자신의 각도1(트리거 일관성·판정시점 신선도)이 이미 내린 결론과도 독립적으로 합치. 고침: [1] cmd_restore()에 cmd_check()와 같은 복호화 왕복 확인을 무결성검사 통과 직후 추가(막지는 않음 — 파일 복구는 이미 끝났으므로 사후 경고만). [2] 보관기간 루프에 형제 루프와 같은 try/except OSError 적용. 독립검증: cmd_restore()·cmd_check()·보관기간 루프 전문을 직접 Read로 대조(수정 전 상태에 두 검사·방어가 실제로 0건임을 먼저 확인), 라운드317의 '292가 이미 다룸' 요약이 실제로는 다른 문제(스케줄러 등록·--remove 반환값·빈파일 생성)였음을 run_all_tests.py 원문 대조로 확인(라벨 재확인 규율이 이번에도 유효했음), 기존 테스트 6개(round342/292/123/121/69/66, 백업·복구 관련 UNIT계열 전부) 실행해 무관함 확인. 회귀테스트(test_scan_round446_fixes.py, 11개 검사)는 같은 키 백업+복구는 경고 없음(과잉경고 아님 대조군), 다른 키 복구는 새 경고가 뜨되 복구 자체는 여전히 완료됨(막지 않음), 보관기간 정리 중 파일 하나가 실제로 잠겨 있어도(os.remove 몽키패치로 결정론적 재현) 나머지 파일은 정상 정리되고 함수 전체가 안 죽음을 전부 실측 — 첫 실행 11/11 통과. manage.py는 app.py가 import하는 모듈이 아닌 독립 CLI라 서버 재기동 불필요 — BUILD_HASH 로테이션 없음(재기동 자체를 안 함, 확인 완료)."),
    ("test_scan_round450_fixes.py", "스캔 450라운드 회귀 — 평문 로그(bokguon.log) CRLF 개행주입(로그위조), 1건. 정밀조사 Agent가 후보A(평문 로그 개행주입, 라운드449가 백로그로 남긴 각도)에서 발견 — waitress_out.log/waitress_err.log는 순수 stdout/stderr 캡처라 위험지대가 아니었고, 진짜 위험지대는 bokguon.log 였다. app.py:1166-1168의 _WinSafeRotatingFileHandler+단순 Formatter는 메시지 속 개행을 전혀 안 거르는데, app.py:1006(Host 헤더 로깅)은 이미 %r로 안전하게 쓰면서 형제인 접속기록 실패 핸들러(1111행 부근)와 전역 예외핸들러 err_500(1229행 부근, 앱 전체 처리 안 된 예외를 전부 받는 공용 싱크)만 request.path를 %s로 그대로 찍어 형제 관례를 안 따랐다. 실측: 실제 격리 waitress 서버(스크래치 DB·로그, 운영 무접촉)에 before_request가 무조건 부르는 함수를 프로세스 메모리에서만(디스크 app.py는 무수정) 예외를 던지게 바꿔치기해 err_500을 강제 실행시키고, 경로에 URL인코딩된 CRLF(%0D%0A)를 심은 실제 HTTP 요청을 보내자 한 번의 app.logger.error() 호출이 실제로 여러 물리적 줄로 쪼개졌고, 그중 한 줄은 실제 로그 포맷(%(asctime)s %(levelname)s %(message)s)과 시각적 구분이 안 되는 완전한 위조 항목이었다. 독립검증: app.py:1006(안전한 %r 관례)·1111·1166-1168·1213-1247(err_500 전문)·1124(LOG_FILE이 실제로 bokguon.log를 가리킴)을 전부 직접 Read로 재확인, 정밀조사 Agent의 실제 재현 결과(격리 waitress+실제 CRLF 요청+로그파일 물리줄 쪼개짐)와 근거 코드가 정합함을 확인. 트레이드오프 없는 '그냥 고치면 되는 것' — 같은 파일 안에 이미 있는 정답 패턴(%r)을 나머지 두 곳에 맞추는 것뿐, 지금 당장 외부에서 그대로 완성되는 익스플로잇은 아니지만 err_500이 앱 전체의 공용 싱크라 향후 어떤 라우트든 새 예외 하나만 나면(이 세션 역사상 거의 매 라운드 발생) 그 요청의 request.path가 그대로 새는 잠재적 결함으로 분류. 고침: 두 자리 모두 request.path의 %s를 %r로 교체(request.method는 HTTP 요청줄 파싱 자체가 공백으로 구분돼 구조적으로 CRLF를 담을 수 없어 그대로 둠) — 새 메커니즘 없음, 1006행과 완전히 같은 관용구 재사용. 같은 라운드 후보B(JSON 바디 과다할당/Over-posting)는 완전 클린 확정 — 협력사·보험사·관리자·사건· 하자·하위계정 등 대표 수정형 라우트 8개 전수 정독 결과 전부 하드코딩된필드명 화이트리스트에 대해 'if f in d'로 개별 확인 후에만 SQL SET절에 추가하는 동일 관용구를 써, 클라이언트가 화이트리스트 밖 키(rating· status·win_rate·jobs_done 등)를 같이 보내도 SQL문 자체가 그 컬럼을 언급 안 해 반영될 수 없는 구조임을 실측(협력사 계정으로 그 필드들을 끼워 PATCH 요청 실제 실행 → 응답 200이지만 DB 재조회 결과 화이트리스트 밖 필드 전부 시딩값 그대로) — 코드변경 없음. 회귀테스트(test_scan_round450_fixes.py, 13개 검사)는 [1]소스에 새 %r 패턴 존재·옛 %s 패턴 부재 확인 [2]app.py를 전혀 안 건드리고 옛 포맷문자열 리터럴과 새 포맷문자열 리터럴을 각각 실제 logging.FileHandler로 파일에 써서 읽어보는 순수 메커니즘 재현으로 되돌림-증명(옛 포맷은 위조 문구가 실제로 독립된 줄로 쪼개짐을 실측해 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명, 새 포맷은 한 줄 그대로 유지되고 CRLF가 리터럴 리터럴 이스케이프 텍스트로만(원본 바이트 아님) 남음을 실측) [3]실제 app.py를 스크래치 DB로 띄우고 before_request 몽키패치로 진짜 err_500을 실행시켜 그 실제 로그 출력을 캡처해도 위조 문구가 독립된 줄로 안 나타남을 실측 — 첫 실행 13/13 통과. app.py 자신의 로깅 호출 2곳 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round451_fixes.py", "스캔 451라운드 회귀 — waitress 요청 본문 크기 상한 미설정, 1건. 정밀조사 Agent가 라운드450이 백로그로 남긴 후보A(요청 본문 크기 상한)에서 발견 — app.py:123의 MAX_CONTENT_LENGTH(BOKGUON_MAX_UPLOAD_MB, 기본 260MB)는 Flask 계층 검사라 요청 스트림을 실제로 읽기 시작할 때만 발동하는데, serve_waitress.py의 serve() 호출이 waitress 자신의 max_request_body_size를 한 번도 지정한 적이 없어 waitress 기본값 1기가바이트(waitress 패키지 adjustments.py)가 그대로 살아 있었다. waitress는 헤더를 다 읽은 뒤 본문 전체를 자기 버퍼(512킬로바이트 넘으면 디스크 임시파일로 스풀)에 다 받아야만 WSGI 앱(Flask)에 요청을 넘기므로, 260메가~1기가 사이 크기의 요청은 인증 없이도 디스크를 소모시키며 끝까지 받아들여진 뒤에야 거부됐다. 실측: 280메가바이트 요청을 실제로 전송하자 5.8초에 걸쳐 전량 수신되고 그동안 C 드라이브 여유공간이 약 268메가바이트 줄었다가 응답 직후 정확히 복구됨을 확인, connection_limit(100, waitress 기본값)까지 겹치면 인증 없이 도달 가능한 아무 라우트로도 디스크를 대량 점유시킬 수 있는 잠재적 가용성 리스크. 독립검증: app.py:123(MAX_CONTENT_LENGTH 설정)·serve_waitress.py의 실제 serve() 호출 인자(직접 Read로 max_request_body_size 언급이 전혀 없음을 확인)·설치된 waitress 패키지 자신의 adjustments.py(connection_limit=100, max_request_body_size=1073741824 정확히 1기가바이트임을 직접 확인)·parser.py(153-162행, Content-Length 헤더가 상한을 넘으면 본문을 한 바이트도 안 받고 즉시 RequestEntityTooLarge로 거부하는 코드 경로를 직접 확인 — 이 메커니즘이 실제로 존재해야 고침이 의미가 있는데 정확히 그렇게 짜여 있음을 재확인)를 전부 직접 대조. 같은 라운드 각도B(first_login_at류 최초1회기록 컬럼의 동시성)는 완전 클린 확정 — 협력사 로그인의 유일한 그런 쓰기지점(WHERE 절이 COALESCE로 이미 채워진 행을 자동으로 걸러내는 조건부 UPDATE)을 실제 8-way·24-way 강제동시 스레드 경합으로 재현했으나 이중기록·예외 0건 — SQLite 파일잠금이 같은 행 쓰기를 직렬화하고 WHERE절이 실행 순간에 재평가되는 구조상 이중기록이 애초에 불가능함을 확인, 코드 자신의 주석대로(집계 실패해도 로그인은 막지 않음) 정확히 동작함을 실측으로 재확인 — 코드변경 없음. 고침: serve_waitress.py에 형제 상수(BOKGUON_MAX_UPLOAD_MB)와 같은 값에 여유(10메가바이트, 헤더/멀티파트 오버헤드용)를 더한 값을 waitress 자신의 max_request_body_size로도 전달 — 이제 waitress가 헤더의 Content-Length만 보고 본문 수신 전에 즉시 거부하고, app.py 자신의 413 핸들러(정상범위 안내메시지)는 그 여유 구간 안에서 그대로 살아 있음. 새 정책 없음, 트레이드오프 없는 그냥 고치면 되는 것. 회귀테스트(test_scan_round451_fixes.py, 7개 검사)는 실제 waitress 인스턴스 둘을 서로 다른 스크래치 포트에 띄워(값은 테스트 속도를 위해 2메가바이트 상한으로 축소, 메커니즘은 동일) 상한을 준 쪽은 5메가바이트 요청이 WSGI 앱에 전혀 도달 안 하고 거부됨을, 상한을 안 준(이 프로젝트의 옛 코드와 정확히 같은 호출형태) 쪽은 같은 요청이 실제로 WSGI 앱까지 도달해 정상 200을 돌려줌을 실제 소켓 통신으로 실측해 되돌림-증명 — 첫 실행 7/7 통과. serve_waitress.py는 app.py가 import하는 모듈이 아닌 독립 진입점 스크립트지만 실제 운영 서버를 그 스크립트로 띄우므로 재기동 필요, static/templates·app.py 자체는 미변경이라 BUILD_HASH 로테이션 여부는 예측 말고 재기동 후 실측 확인."),
    ("test_scan_round454_fixes.py", "스캔 454라운드 회귀 — 백업 자가점검(backup_selfcheck.py) 결함 2건. 정밀조사 Agent가 라운드453이 넘겨준 후보A(백업 파일 실제 ACL 권한)에서 발견 — manage.py::cmd_backup()의 icacls 하드닝(1263-1277행 부근, 빈 파일을 먼저 만들고 icacls로 상속을 끊은 뒤 채움)은 이 PC에서 실제로 매일 성공하고 있고 운영 backups 폴더의 보관기간 내 파일 전부가 SYSTEM/Administrators/admin 세 명시적 권한뿐임을 icacls로 직접 확인했지만, icacls 호출 자체가 실패해도(계정명 조회 실패 등) warn()만 찍고 return이 없어 그대로 흘러가며, cmd_backup()의 최종 반환값은 무결성검사 결과(res=='ok')에만 좌우돼 icacls 실패 여부가 종료코드에 전혀 반영되지 않음을 실제 소스 대조로 확인(계정명을 존재하지 않는 값으로 바꿔 icacls를 실제로 실패시켜도 백업 자체는 종료코드 0으로 끝남을 스크래치로 재현). deploy/일일백업.bat는 errorlevel만 검사하므로 이 실패는 로그 파일에만 묻히고 스케줄러 화면에도 자가점검에도 신호가 안 간다. 게다가 icacls가 성공해도 그 직후 만들어지는 WAL 사이드카(.db-shm/.db-wal, 원본이 WAL 모드라 백업 사본도 그 헤더 플래그를 물려받음)는 하드닝을 안 받는다 — deploy/backup_selfcheck.py가 매일 mode=ro로 그 백업을 여는 순간 SQLite가 wal-index 확인을 위해 -shm을 새로 만드는데(mode=ro라도 필요하면 만든다는 사실을 스크래치로 직접 재현 확인), 그 신규 파일은 icacls 하드닝을 안 받고 backups 폴더 자체의 상속 권한을 그대로 받는다 — 실제 운영 backups 폴더의 실제 .db-shm 파일을 icacls로 직접 조회해 CodexSandboxUsers:(I)(RX)를 확인(로컬 비관리자 계정 그룹이 개인정보가 담긴 백업 사이드카를 읽을 수 있는 상태였다). 독립검증: manage.py의 icacls 호출부·최종 반환문·backup_selfcheck.py의 mode=ro 연결부를 전부 직접 Read로 재확인, 실제 운영 backups 폴더의 대표 파일과 그 -shm 사이드카를 icacls로 직접 재조회해 에이전트 보고와 정확히 일치함을 확인(파일 크기까지 32,768바이트로 동일), immutable=1을 안 쓴 mode=ro만으로 실제 -shm/-wal이 생기고 immutable=1을 추가하면 안 생김을 스크래치 WAL DB로 직접 재현해 그 메커니즘 자체가 진짜임을 재확인. 같은 라운드 후보B(예약작업 스크립트 NTFS 권한)는 완전 클린 확정 — 복구온 관련 예약작업 2개(경매마감·일일백업) 전부 admin 계정· Interactive 로그온·RunLevel Limited(비상승)로 돌고, 이 PC의 활성 로컬 계정은 admin 외 CodexSandboxOffline/Online 뿐인데 그 그룹은 manage.py·일일백업.bat 등 핵심 스크립트에 ReadAndExecute뿐 쓰기 권한이 전혀 없음을 icacls로 직접 재확인(예약작업 정의 파일 자체도 admin/Administrators/SYSTEM 외 ACE 없음) — 낮은 권한 계정이 스크립트를 고쳐 다음 실행 때 더 높은 권한으로 임의코드를 실행시킬 상승 경로가 이 PC엔 애초에 없음을 실제 로컬 계정·ACL로 확인, 코드변경 없음. 고침(둘 다 트레이드오프 없는 그냥 고치면 되는 것): (1) backup_selfcheck.py의 SQLite 연결에 immutable=1을 추가해 WAL 사이드카 생성 자체를 차단 (2) 같은 파일에 icacls로 최신 백업 파일의 상속 권한 여부를 확인하는 새 검사(_has_inherited_acl)를 추가해 cmd_backup()의 icacls 실패가 조용히 묻히지 않고 이 자가점검(일일백업.bat 의 errorlevel에 실제로 반영되는 유일한 지점)을 통해 표면화되도록 함 — cmd_backup() 자체는 안 건드림(백업은 계속 남겨야 한다는 기존 설계의도 유지). 회귀테스트(test_scan_round454_fixes.py, 9개 검사)는 mode=ro만 쓰면 실제로 WAL 사이드카가 생기고 immutable=1을 쓰면 안 생김을 스크래치 WAL DB로 직접 재현해 되돌림-증명, 상속 가능한 ACE를 명시로 심은 스크래치 폴더로 상속됨/안됨 두 경우를 icacls로 실제 생성해 새 감지함수가 정확히 구분함을 실측(과잉경고 아님 대조군 포함), 실제 backup_selfcheck.main()을 상속된 백업만 있는 스크래치 폴더로 호출해 자가점검이 실제로 실패(1)로 끝남을, 하드닝된 백업으로 교체하면 통과(0)함을 실측 — 첫 실행 9/9 통과. backup_selfcheck.py·manage.py 어느 것도 app.py가 import하는 모듈이 아닌 독립 도구(예약작업이 직접 호출)라 재기동 불필요, BUILD_HASH 로테이션 없음(재기동 자체를 안 함, 확인 완료)."),
    ("test_scan_round458_fixes.py", "스캔 458라운드 회귀 — 보험사 등록의 유니코드 정규화 미비로 중복검사 우회, 1건. 정밀조사 Agent가 지시받은 두 각도(EXIF 내장 썸네일 GPS 잔존, 자기서비스 비밀번호 재설정 토큰)는 둘 다 클린/해당없음으로 끝나(전자는 exif=빈값이 재인코딩 시 썸네일까지 전부 버림을 조작된 JPEG로 직접 재현 확인, 후자는 self-service 재설정 웹플로우 자체가 존재하지 않음을 확인), 참고후보였던 유니코드 호모글리프/정규화 각도로 스스로 교체해 발견 — api_insurer_create()(app.py:8491-)의 중복검사(SELECT 1 FROM insurers WHERE name=?)가 단순 바이트열 대조라, 시각적으로 완전히 같은 기관명을 다른 유니코드 정규화 형태(한글자모를 완성형 대신 풀어쓴 NFD, 전각영문 vs 반각영문 등)로 등록하면 그대로 통과해 라운드68이 막으려던 '같은 기관명 행이 2개' 사고가 다른 경로로 재발함을 실측(NFC 표기로 등록 후 그 NFD 표기를 등록하면 중복검사를 피해 실제로 두 번째 행이 생김 — 맥에서 복사한 텍스트가 흔히 NFD임을 근거로 듦). 전각/반각 영문 표기로도 같은 우회가 됨을 함께 확인. 독립 검증: app.py의 실제 중복검사·INSERT 코드(구 8501·8514행 부근)를 직접 Read로 재확인, NFC와 NFD가 파이썬 문자열 비교에서는 다르지만 unicodedata.normalize로 정규화하면 같아짐을 별도로 직접 실행해 메커니즘 자체를 재확인, insurers.name을 쓰는 자리가 이 INSERT 한 곳뿐임을(수정 라우트에서 이름을 바꾸는 경로 없음) grep 전수로 확인. require_role(최고관리자)로 게이트돼 있어 외부에서 직접 도달 가능한 구멍은 아니고 내부 데이터정합성 위험(사건 라우팅·요율이 갈라지는 라운드68 시나리오의 재발)임을 확인 — 트레이드오프 없는 그냥 고치면 되는 것으로 분류(한글 NFD 케이스). 전각/반각 폴딩까지 포함하는 더 강한 정규화(NFKC, NFC보다 상위호환)를 택함 — 두 우회경로를 한 번에 닫고, 기관명이 전각/반각으로 의도적으로 구분돼야 할 정당한 이유가 없다고 판단(라운드300이 ingest_partners.py에서 전각괄호 한 쌍만 좁게 치환한 선례와 달리, 이번엔 그 상위개념인 호환정규화를 등록 API 자체에 적용). 고침: app.py에 unicodedata import 추가, api_insurer_create()의 name 변수를 strip 직후 NFKC로 정규화해 중복 검사·저장 양쪽에 같은 기준을 적용 — 새 정책·새 메커니즘 없음, 이미 있는 문자열 비교 로직 자체는 그대로. 회귀테스트(test_scan_round458_fixes.py, 8개 검사) 신설 — 실제 Flask 앱(스크래치 DB, 데모 관리자 로그인)으로 NFC 등록 후 NFD 재등록이 400으로 거부되고 DB에 정확히 1행만 남음을, 완전히 다른 이름은 여전히 정상 등록됨(과잉차단 아님)을 실측, unicodedata.normalize를 프로세스 메모리에서만(디스크 무수정) 항등함수로 되돌려 옛(취약) 동작을 재현하면 같은 시나리오가 실제로 200/200으로 통과하고 DB에 중복 행 2개가 생김을 실측해 되돌림-증명 — 검증 중 이 테스트 자신의 버그(전역 unicodedata 모듈을 패치하면 테스트 자신의 NFD 픽스처 계산과 카운트 헬퍼도 같이 항등함수 영향을 받아, 되돌림 단계의 두 번째 등록이 첫 번째와 완전히 같은 문자열이 돼버려 정상 중복거부(400)를 '재현 실패'로 오판할 뻔한 것을 발견 — 정규화가 필요한 모든 픽스처 값을 패치 이전에 미리 계산해 두는 것으로 수정) 후 재통과 — 첫 실행(자체버그 수정 후) 8/8 통과. app.py 자신의 함수 변경(신규 import 포함)이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round462_fixes.py", "스캔 462라운드 회귀 — 1차합의(field-agreement) 개시 재시도 시 알림 중복 발송, 1건. 정밀조사 Agent가 후보A(1차합의 흐름의 동시성 방어)에서 발견 — 부동의·승인확정을 처리하는 settle_agreement()은 이미 BEGIN IMMEDIATE와 상태 재확인(WHERE id=? AND status=?, rowcount 체크)까지 갖춰 낙찰·정산과 같은 수준으로 견고함을 확인(클린, 라운드94·117·138·190·192가 다져온 패턴 그대로), 다만 개시(open_agreement) 쪽은 dispatch.py 자신이 이미 검토중인 합의가 있으면 새로 안 만들고 기존 id를 그대로 돌려주는 중복생성 방지 로직을 갖고 있는데, 그 반환값이 신규생성인지 재사용인지 호출부(app.py의 api_field_agreement_open)가 구분하지 못해 더블클릭·네트워크 재시도·거의 동시 요청마다 보험사(알림톡)·운영팀(웹) notify()가 매번 다시 나감을 발견 — DB의 field_agreements 행 자체는 정확히 1건으로 막히지만(dedup 정상) notifications 행은 호출 횟수만큼 쌓임을 실제 순차 재시도(2회 POST)와 진짜 동시 5-thread 경합(라운드348과 같은 배리어 기법) 양쪽으로 실측(각각 notifications 2건·5건 생성). 팝빌 실발송은 현재 .env에서 꺼져 있어(BOKGUON_NOTIFY_ENABLED=0) 당장 외부 문자비용으로 이어지진 않지만, 보험사 포털의 알림 목록(api_insurer_notifications, channel·status 구분 없이 최근 50건 노출)에는 발송 on/off와 무관하게 재시도 즉시 중복 항목이 뜸을 확인 — 실측 가능한 영향. 독립검증: dispatch.py의 open_agreement() 중복재사용 로직(case_id·status=검토중 조건부 SELECT 후 rollback+기존id 반환)과 app.py 호출부(반환값이 truthy기만 하면 신규·재사용 구분 없이 무조건 notify 2회+commit)를 전부 직접 Read로 재확인, 이 코드베이스 자신이 이미 확립한 '재사용이면 duplicate:true로 조용히 성공 반환, 부수효과는 건너뜀' 관용구(라운드228의 하자접수 10초 쿨다운 등)를 직접 대조해 같은 패턴을 이식. 고침: 호출부(app.py)에 dispatch.py와 똑같은 조건(case_id·status=검토중)의 조회를 open_agreement() 호출 **전에** 선행시켜, 이미 검토중인 합의가 있으면 open_agreement()도 notify()도 안 부르고 duplicate:true와 기존 합의정보만 즉시 돌려줌 — dispatch.py 자신의 내부 로직·반환 계약은 전혀 안 건드림(다른 12개 이상 호출부·테스트 파일이 이미 이 함수를 직접 부르고 있어 반환 형태를 바꾸면 그 전부가 깨졌을 것이라 그 경로는 피함), 새 메커니즘 없음. 같은 라운드 후보B(개인정보파기 예약실행 여부)는 완전 클린 확정 — 죽은 기능이 아니라 실제로 매일 자동 실행되고 있음을 5개 독립 경로(코드·배포스크립트·실제 윈도 스케줄러 조회·37일치 로그 전수· 운영DB 내부 job_locks 타임스탬프)가 서로 초 단위까지 일치하도록 교차 확인, 코드변경 없음. 회귀테스트(test_scan_round462_fixes.py, 신설 당시 10개 검사) — 실제 Flask 앱(스크래치 DB, 관리자 세션, 출동→수락→도착까지 실제 진행시킨 사건)으로 field-agreement 개시 라우트를 2회 연속 호출해 고쳐진 코드는 2번째 호출이 duplicate:true를 돌려주고 notifications가 2건(최초 1회분)에서 안 늘어남을, app.py 소스를 서브프로세스 실행 직전에만 임시로 옛(취약) 한 줄로 되돌렸다가(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오를 재실행하면 실제로 notifications가 4건(2회×2건)까지 쌓임을 실측해 되돌림-증명 — 첫 실행10/10 통과. app.py 자신의 라우트 변경이라 재기동 필요, static/templates 미변경이지만 app.py 자체 변경이라 BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인). ★[라운드613] 서브프로세스 워커(test_scan_round462_worker.py, 디스크에 되돌린 app.py를 잠깐 실기록)를 round411·610이 확립한 안전패턴(A.app.view_functions 딕셔너리 항목만 임시치환 + exec 로 사본 네임스페이스 재구성, 디스크 미기록)으로 이관하며 워커 파일은 삭제 — 검사 13개로 증가(원복 후 재확인 항목 추가)."),
    ("test_scan_round463_fixes.py", "스캔 463라운드 회귀 — 출동 직접배정(dispatch/assign, supersede=true) 재시도 시 알림 중복발송과 거짓 출동취소 통지, 1건. 정밀조사 Agent가 두 후보(데모사건 실발송 격리 여부·사진 다운로드 Content-Disposition 헤더주입 가능성)를 조사한 뒤 둘 다 클린으로 확정하고, 과제 안내문이 제시한 대체 각도(round462가 찾은 재사용-vs-신규 구분불가 버그 클래스가 다른 곳에도 있는지 체계적 재탐색)에서 새로 발견 — 후보A(데모 격리)는 스크래치 DB에서 실제 사건과 데모 사건을 각각 만들어 notify()와 sweep_send_notifications()를 실제 실행해 데모는 POPBILL.send()가 0회 호출됨을 실측 확인(클린, 코드판독과 일치). 후보B(헤더주입)는 api_photo_file()의 Content-Disposition이 파일명 파라미터 없는 상수 'inline'이라 원본 파일명이 들어갈 여지가 구조적으로 없음을 실제 악성 파일명 업로드 후 raw 응답헤더로 실측 확인(클린) — 다만 photo_ai.py의 원본 파일명 저장 자체는 이스케이프가 없되, 화면에 뿌리는 두 지점이 이미 항상 escape를 거쳐 회의 없음(기존 설계원칙의 정상 적용, 새 결함 아님). 재탐색에서 dispatch.py의 assign_dispatch()가 supersede=True면 재요청인지 최초요청인지 구분 없이 무조건 기존 수배를 취소하고 새로 만드는 것을 발견 — 호출부(api_dispatch_assign, app.py)는 성공 여부만 보고 매번 협력사 알림톡·보험사 웹 notify()를 쐈다. 관리자가 '이미 진행 중' 확인창을 누른 뒤 응답이 늦어 다시 누르거나 네트워크가 재시도하면, 이미 그 업체로 배정된 수배를 스스로 취소했다가 다시 만들어 그 업체에게 '다른 업체로 배정되어 취소되었습니다'(거짓 — 실제로는 자기 자신)와 '배정되었습니다'를 연달아 보냄을 실제 HTTP 재시도로 실측(스크래치 DB, assign_notify 2건·cancel_notify 1건·dispatches 2행). round281이 같은 함수를 이미 감사했으나 그 관찰은 완전히 다른 사안(밀려난 후보의 dispatch_calls 뒷정리 누락, claim()의 CAS 재확인이 이미 무해화함을 확인 후 미조치)임을 run_all_tests.py 원문 대조로 확인 — 겹치지 않음. 고침: 라운드462와 같은 관용구 — assign_dispatch() 호출 전에 현재 진행중 수배가 이미 요청받은 그 업체로 배정돼 있는지 선확인해, 같으면 assign_dispatch()도 notify()도 안 부르고 duplicate:true와 기존 dispatch_id만 즉시 반환. supersede=False 경로(기존 409 오류 흐름)와 다른 업체로 실제 갈아타는 정상 supersede는 이 조건에 안 걸려 그대로 동작 — dispatch.py의 assign_dispatch() 자신은 전혀 안 건드림. 회귀테스트(test_scan_round463_fixes.py와 그 서브프로세스 워커 test_scan_round463_worker.py, 12개 검사) 신설 — 실제 Flask 앱(스크래치 DB, 관리자 세션)으로 직접배정 라우트를 정상 1회 호출 후 같은 업체로 supersede 재시도를 연속 호출해, 고쳐진 코드는 2번째 호출이 duplicate:true를 돌려주고 dispatches·알림톡· 취소통지가 전혀 안 늘어남을, app.py 소스를 서브프로세스 실행 직전에만 임시로 옛(취약) 코드로 되돌렸다가(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오를 재실행하면 실제로 dispatches 2행·알림톡 2건·거짓 취소통지 1건까지 쌓임을 실측해 되돌림-증명 — 첫 실행 12/12 통과. app.py 자신의 라우트 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round464_fixes.py", "스캔 464라운드 회귀 — 사건 정보 수정(PATCH /api/cases/<id>, admin.js의 saveCaseEdit) 폼이 항상 전체 스냅샷을 보내 동시수정 lost-update를 일으키던 결함, 1건. 정밀조사 Agent가 후보A(관리자 계정 삭제 시 기존 세션 즉시무효화 여부)를 조사했으나 _account_alive()가 이미 매 요청마다 admins 테이블을 재조회해 삭제된 계정의 세션을 401로 즉시 차단함을 재확인(기존 test_session_liveness.py·round435이 이미 검증한 것과 같은 계열, 타인 계정 삭제 케이스만 새로 재현해도 9/9 통과) — 클린 확정, 대체각도(두 관리자가 거의 동시에 같은 사건 필드를 수정할 때 lost-update 발생 여부)에서 새 결함 발견. cases 테이블엔 updated_at·version류 컬럼이 아예 없고(db.py 마이그레이션 전수 확인) api_case_edit()(app.py)는 요청값을 그 순간 DB 현재값과만 비교해 다르면 갱신한다 — 폼을 연 시점의 값과 같은지는 확인하지 않는다. 그런데 admin.js의 saveCaseEdit()가 사용자가 안 건드린 필드까지 늘 폼의 현재 표시값 전체를 함께 보냈으므로, 관리자1이 지역만 고쳐 저장한 직후 관리자2가 (그 폼을 먼저 열어 옛 지역값을 그대로 들고 있는 채로) 공종만 고쳐 저장하면 관리자2 폼에 남은 옛 지역값이 관리자1의 변경을 조용히 되돌렸다 — 순차 2회 PATCH와 진짜 동시 스레드(est_price) 양쪽으로 실측(에이전트), 실제 운영 DB 읽기전용 조회로 규모도 검산(관리자 2명·사건수동수정 감사로그 8건 중 10분 이내 충돌 사례 0건 — 지금 당장 급한 사고는 아니되 구조는 그대로 남음). 판단은 혼합형: 같은 필드를 두 사람이 진짜 동시에 고치는 충돌 자체를 막는 것은 낙관적 잠금 인프라(스키마 변경·충돌 UX 설계)가 필요한 제품판단이라 결정대기 13번 항목으로 남기되, '안 만진 필드가 남의 변경을 덮어쓰는' 절대 다수의 사고 경로는 서버·스키마 변경 없이 프런트만 고쳐 즉시 막을 수 있어 이번 라운드에 바로 적용 — saveCaseEdit()를 전체 스냅샷 제출에서 필드별 diff 제출로 바꿔, 각 입력의 현재값을 그 입력이 처음 채워졌을 때의 defaultValue(select는 defaultSelected)와 대조해 실제로 달라진 필드만 PATCH body에 담는다(새 상태 저장 없이 브라우저 네이티브 속성만 사용) — 아무것도 안 바뀌었으면 PATCH 자체를 안 보낸다. 회귀테스트(test_scan_round464_fixes.py, 10개 검사, round340이 세운 Node vm 임시 harness 방식 그대로) 신설 — saveCaseEdit()·digits()·moneyVal() 함수 원문을 고정길이 텍스트창이 아니라 실제 괄호균형으로 뽑아(라운드15가 겪은 창구간충돌 클래스를 이 새 테스트 스스로도 반복하지 않기 위해) 가짜 DOM 엘리먼트로 실제 실행, region만 바꾼 시나리오에서 고쳐진 코드는 body에 region만 담김을, admin.js 소스를 실행 직전에만 임시로 옛(취약) 전체스냅샷 코드로 되돌렸다가(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오를 재실행하면 실제로 안 건드린 category·address·manager 등 전부가 body에 함께 딸려옴을 실측해 되돌림-증명 — 첫 실행 10/10 통과. app.py 변경 없음, static/admin.js만 변경이라 BUILD_HASH 로테이션 예상(서비스워커 캐시무효화를 위해 재기동 필요 — 예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round465_fixes.py", "스캔 465라운드 회귀 — 보험사 완료승인(api_insurer_settlement_approve, app.py)에 정산 4형제(review·transfer·void·paid[-bulk])와 달리 최종 UPDATE 상태조건+rowcount 겹방어가 빠져 있던 결함, 1건(방어심화 — 지금 뚫리는 결함은 아님). 정밀조사 Agent가 후보A(정산 상태전이 함수들의 재시도 멱등성 — 라운드462·463과 같은 재사용-vs-신규 버그클래스가 정산에도 있는지)를 조사해 review·transfer·void·insurer_approve 네 곳 전부 실제 동시 스레드(2~5개, 3회 반복) 재현으로 알림 중복·회계 이중계상 전혀 없음을 확인(클린) — 전부 BEGIN IMMEDIATE로 쓰기잠금을 즉시 잡아 읽기→사전확인→쓰기가 이미 직렬화돼 있음을 재확인. 다만 insurer_approve 하나만 형제와 다른 구조(사전확인은 있으나 최종 UPDATE 자체엔 상태조건 WHERE절과 rowcount 재확인이 없음 — review 13888행 등 형제 4곳은 이 겹방어까지 갖춤)임을 발견 — 지금은 BEGIN IMMEDIATE의 완전한 직렬화 덕에 사전확인만으로도 실제 이중승인이 안 남을 코드로 직접 재확인했지만(사전확인 읽기와 최종쓰기 사이에 다른 트랜잭션이 절대 못 끼어듦), 돈이 걸린 자리에서 형제만 갖춘 방어를 하나만 빠뜨려 둘 이유가 없어 같은 패턴을 이식(트레이드오프 없음, 새 메커니즘 없음). 후보B(협력사 하위계정 초기비밀번호 평문노출 여부)는 6개 발급경로(관리자·협력사 원계정·보험사 원계정·협력사 하위계정 생성/재발급·계정안내알림) 전부 실제로 계정을 만들어 notifications·activity_log를 전수 검색했으나 평문 비밀번호 0건 확정 — 하위계정 경로는 애초에 notify() 호출 자체가 없고, 원계정 경로의 notify()는 보안경보문만 담을 뿐 비밀번호는 응답 JSON에 1회만 실림(라운드330·300이 각각 DB.log·CLI 스크립트 범위에서 확인한 것을 이번엔 app.py 웹 라우트 6곳+notifications 테이블까지 넓혀 재확인) — 클린, 조치 불필요. 고침(insurer_approve): 최종 UPDATE문을 'WHERE id=? AND insurer_approved=0'로 바꾸고 rowcount=0이면 형제와 같은 문구로 409 반환 — 정상 승인·재승인시도(사전확인에서 여전히 차단) 흐름은 전혀 안 바뀜. 회귀테스트(test_scan_round465_fixes.py, 9개 검사) 신설 — [1]소스 확인 [2]실제 Flask 앱으로 정상흐름(1회 승인 성공+알림 1건, 재승인시도 여전히 409, 알림 안 늘어남) 회귀없음 확인 [3]겹방어 SQL문 자체를 사전확인 없이(가상의 우회 호출을 흉내) 스크래치 DB에 직접 실행해 미승인 행엔 반영(rowcount=1), 이미승인 행엔 거부(rowcount=0)됨을 실측 — 이 결함은 라운드462·463처럼 되돌리면 실제로 재현되는 라이브 버그가 아니라(BEGIN IMMEDIATE가 이미 안전하게 막고 있음을 직접 확인) 방어심화이므로, 정직하게 '지금 안전함을 재확인 + 새 가드 자체의 논리적 정확성 검증'으로 테스트를 설계(허위로 되돌림-증명을 주장하지 않음) — 첫 실행 9/9 통과. app.py 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round466_fixes.py", "스캔 466라운드 회귀 — round429가 세운 협력사 사업자번호 중복방지(같은 biz_no로 활성 업체 두 곳 방지)의 틈 2곳(A2·A3) 수정 + 담합 각도 1건(A1) 결정대기 신설 + 내보내기 마스킹(B) 클린. 정밀조사 Agent가 후보A(입찰 자기경쟁/담합 — 사업자번호 같은 복수계정이 같은 경매에 중복입찰)를 조사해 실제로 사업자번호 동일 협력사 2계정을 만들어 같은 경매에 둘 다 투찰시켜 재현(둘 다 200, 실질경쟁자 0인 채 낙찰후보 집계) — 다만 운영 DB 읽기전용 검산 결과 partners 400행 중 biz_no 채워진 행이 1개뿐(99.75% 공백, 라운드459와 동일 수치)이라 'biz_no 일치'만 막는 기계적 패치는 오늘의 실제 위협을 거의 못 줄임 — 동일사업자 판정 기준 자체(biz_no 필수화·유사도·수동검토 등)가 비즈니스 정책 결정이라 **사용자 결정 대기 14번 항목으로 신설**. 같은 조사에서 round429 자신이 세운 방어의 틈 2곳을 발견해 즉시 수정: (A2) api_partner_update()의 DUP_BIZNO 재확인이 '요청에 biz_no가 실려 있을 때만' 걸려 있어 status만 '활성'으로 바꾸는 재승인 요청은 그 검사를 건너뛰어, 이미 다른 활성 업체와 같은 사업자번호를 가진 채 잠자던 계정을 그대로 활성화할 수 있었음 (실측: status만 PATCH해 재현, 활성 중복 2건 생성) — 그냥 고치면 되는 것(round429 원칙을 제자리로 맞추는 것뿐, 새 정책 없음). (A3) api_partner_create()에 형제(api_application_update, 7489행 — 자신의 주석에 정확히 이 클래스의 경합을 막으려 한다고 명시)와 달리 BEGIN IMMEDIATE가 없어 중복확인 읽기와 INSERT 사이에 다른 요청이 끼어들 수 있는 구조 (TOCTOU)였음 — 그냥 고치면 되는 것(형제와 같은 패턴 이식, 트레이드오프 없음). 후보B (CSV·엑셀 내보내기 API의 피해자 개인정보 마스킹 여부)는 8개 내보내기 라우트 전부 실제 사건·정산·신청서에 피해자명·연락처를 심어 호출해 확인 — 전부 화이트리스트 SELECT이거나 집계값만 다뤄 개인정보 자체가 안 실림(양성대조로 스캔 로직 자체는 살아있음도 확인) — 클린, 조치 불필요. 고침: api_partner_update()는 prev 조회에 biz_no를 포함시키고 changed 판정을 앞당겨, '요청의 biz_no(있으면) 또는 기존 biz_no(없으면)'를 기준으로 'biz_no가 바뀌거나' 'status가 활성으로 바뀔 때' 둘 다 DUP_BIZNO를 재확인하도록 조건을 넓힘. api_partner_create()는 중복확인 SELECT 앞에 BEGIN IMMEDIATE를 추가하고 실패 시 rollback하도록 변경(형제 api_application_update와 동일 패턴, 새 메커니즘 없음). 회귀테스트(test_scan_round466_fixes.py + A2 전용 서브프로세스 워커 test_scan_round466_a2_worker.py, 14개 검사) 신설 — A2는 실제 Flask 앱으로 상태만 담은 재승인 PATCH를 보내 고쳐진 코드는 409로 막고 되돌리면 200으로 통과+활성중복 2건이 실제로 생김을 되돌림-증명(app.py 두 지점을 동시에 원복해야 함을 확인 — 한쪽만 되돌리면 changed 미정의로 NameError·500만 나서 최초 시도에서 이 함정에 직접 걸렸다가 두 지점을 함께 되돌리도록 수정해 해결). A3는 스레드 타이밍에 기대지 않고 두 sqlite3 연결의 명령 순서를 직접 통제하는 결정론적 재현을 사용 — 잠금이 없으면 두 연결이 순서대로만 불러도 (진짜 동시가 아니어도) 중복이 실제로 2건 생기고, BEGIN IMMEDIATE가 있으면 두 번째 연결이 첫 연결의 커밋 전엔 쓰기잠금 시작조차(짧은 busy_timeout으로 즉시) 실패함을 실측 — 흔들리는 스레드 경합 대신 항상 같은 결과를 내는 재현법. 첫 실행 14/14 통과. app.py 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round469_fixes.py", "스캔 469라운드 회귀 — 발주처 사건취소(api_insurer_case_cancel, app.py)가 검토중인 1차 합의(field_agreements)를 안 닫아 고아로 남기던 결함, 1건. 정밀조사 Agent가 원래 제시된 두 후보(관리자 TOTP 설정/해제 우회, 엑셀 일괄등록 부분실패 원자성)를 조사 착수 전 run_all_tests.py 원문 대조에서 둘 다 이미 촘촘히 다뤄졌음을 스스로 발견(TOTP는 라운드175·269·413·414가 실행재현까지 마쳤고, 엑셀 일괄등록은 유일한 HTTP 경로인 api_contact_import를 라운드70·98·409가, 인접한 협력사 일괄발급/CLI 일괄등록도 라운드199·250·300·418이 이미 다룸) — 방법론 9번대로 참고후보(must_change_pw 게이트 실효성, 발주처 사건취소 시 연쇄데이터 정리)로 교체. must_change_pw 게이트는 관리자· 보험사·협력사·포털하위계정 4종 세션 전부에서 실제 HTTP로 재현해 완전 클린 확인(13건 검사 — 비허용 API 403 차단, 허용목록 통과, 대조군 정상통과, 포털하위계정도 동일게이트 적용). 발주처 사건취소 각도에서 실제 결함 발견 — 형제(api_case_open_auction, 16077-16082행)는 2차 경매를 열 때 이미 검토중인 1차합의를 '결렬'로 자동종료하는데 발주처 취소 경로만 이 정리가 없어, 사건이 '접수' 상태(1차합의 심사 중이면서 아직 입찰이 없는 상태 — 실제로 도달 가능함을 확인)일 때 취소하면 field_agreements 행이 영원히 '검토중'으로 남음을 실측 재현. 독립검증: settle_agreement()의 승인·부동의 두 가지 모두(dispatch.py 1175·1247행, 각각 사건상태 재확인 — 라운드117이 부동의 가지에 이미 추가한 방어)가 취소된('취소'≠'접수') 사건에 대한 재접근을 이미 차단하고 있어 지금 위험한 결과(다른 업체로 낙찰이 덮어써지는 등)로는 안 이어짐을 코드로 재확인 — 순수 감사추적/데이터위생 문제(고아 '검토중' 행이 집계쿼리를 오도할 소지)로 성격 확정. 고침: close_live_dispatches() 호출 직후 형제(api_case_open_auction)와 동일한 패턴으로 'UPDATE field_agreements SET status=AG_BROKEN, decided_at=..., reject_reason='발주처 사건 취소로 자동 종료' WHERE case_id=? AND status=AG_REVIEW'를 실행하고 rowcount가 있으면 감사로그도 남김 — dispatch.py·settle_agreement() 자체는 전혀 안 건드림, 새 메커니즘 없음. 회귀테스트(test_scan_round469_fixes.py + 서브프로세스 워커 test_scan_round469_worker.py, 9개 검사) 신설 — 실제 Flask 앱(스크래치 DB, 사건접수→출동배정→도착→1차합의 개시까지 실제 진행시킨 사건)으로 보험사 세션이 실제 취소 라우트를 호출해, 고쳐진 코드는 1차합의가 '결렬'로 함께 닫히고 app.py 소스를 서브 프로세스 실행 직전에만 임시로 옛 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally 에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오에서 1차합의가 '검토중'인 채로 고아로 남음을 실측해 되돌림-증명 — 첫 실행 9/9 통과. app.py 자신의 라우트 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round470_fixes.py", "스캔 470라운드 회귀 — 포털 하위계정(portal_users) 생성·비밀번호 재발급(_sub_create_impl·_sub_resetpw_impl, app.py)이 secrets.token_urlsafe(6)을 써서 이 앱 자신의 password_policy_error()를 약 84% 확률로 위반하던 결함, 1건. 정밀조사 Agent가 후보A(비밀번호 복잡도 정책 강제 여부)를 조사 — round413·414는 change-password의 무차별대입 방어만, round418은 partner_accounts.py의 다른 생성기 1곳만, round465는 하위계정 임시비밀번호의 평문노출 여부만 다뤄 강도 자체는 어느 라운드도 안 다룸을 run_all_tests.py 원문 대조로 확인 — 겹치지 않는 신선한 각도로 실제 진행. token_urlsafe(6)은 6바이트→항상 정확히 8자, URL-safe base64 알파벳 64종 중 특수문자는 -·_ 단 2종뿐이라, password_policy_error()의 '3종 조합 8자 이상' 요건을 만족하려면 그 희귀한 특수문자가 반드시 껴야 함을 실제발급 300건·몬테카를로 20만회·조합론 계산 세 방법으로 확인(약 84.3% 정합) — /api/change-password(사람이 직접 고르는 유일한 문)는 실제로 '1234' 등을 거부해 정책 자체는 살아 작동 중임을 확인, 하위계정 발급만 이 문을 안 거침. 운영 DB 읽기전용 확인 — portal_users 0건(아직 실사용 전이라 지금 노출된 계정 없음, 다만 처음 쓰이는 순간부터 발급마다 재현). must_change_pw=1이 이미 걸려 있어 노출창은 발급~첫로그인으로 제한. 후보B(웹훅 재전송 자원고갈)는 실행 재현 결과 완전 클린 — max_attempts=5·attempts² 분 백오프·1회 스윕당 limit=10이 전부 이미 구현돼 있고, delivered_at을 69일 전으로 조작해도 30회 추가 스윕이 전부 재시도 없이 '포기' 상태 유지됨을 실측(2026-08-05 데몬스레드 무한재발사 결함은 이미 근본수정된 상태). 고침: 두 생성 지점 모두 정책을 이미 만족하는 형제 생성기 _gen_temp_pw()(app.py 7742행, 14자·대소문자+숫자 보장, manage.py gen_password와 같은 규칙)로 교체 — 새 정책·메커니즘 없음, round418과 같은 성격(엔트로피 자체는 48비트로 여전히 실질적 추측불가 — 무차별대입 취약점이 아니라 순수 정책일관성 결함). 회귀테스트(test_scan_round470_fixes.py + 서브프로세스 워커 test_scan_round470_worker.py, 8개 검사) 신설 — 실제 Flask 앱(스크래치 DB, 보험사 원계정 세션)으로 하위계정 30건을 실제 생성해 발급된 temp_password 전부를 이 앱 자신의 password_policy_error()로 직접 검사, 고쳐진 코드는 30건 전부 통과(위반 0건)함을, app.py 두 지점을 서브프로세스 실행 직전에만 임시로 옛 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오에서 30건 중 절반 이상(이론치 약 25건)이 위반됨을 실측해 되돌림-증명 — 첫 실행 8/8 통과. app.py 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round472_fixes.py", "스캔 472라운드 회귀 — 두 각도 다 클린 확인(코드 수정 없음), 정밀조사 Agent가 조사 — ① 알림 목록·읽음처리 조직간 IDOR: api_insurer_notifications·api_insurer_notifications_read·api_partner_notifications·api_partner_notifications_read(app.py 16503·16521·16537·16555행) 전부 session[insurer_id]/[partner_id] 로만 조직을 식별하고 request.args·요청본문의 조직id는 전혀 안 읽음을 소스로 확인 + 실제 Flask test_client 재현(20개 검사)으로 확인 — 교차조직 목록조회(쿼리파라미터 조작)·교차조직 읽음처리(다른 조직 notification id 지정) 둘 다 실제로 막힘을 실측, 읽음처리는 UPDATE의 WHERE절에 세션 조직id 조건이 같이 붙어 있어 응답은 ok:true지만 DB엔 반영 안 되는 조용한 no-op임을 확인(하위계정 portal_users 테넌시도 원계정과 동일 경계를 물려받음을 확인). ② 메모 작성자 위조·삭제 권한경계: api_memo_create(1469행)의 author 컬럼은 요청본문이 아니라 서버함수 actor()로만 채워짐(위조 author 필드 완전 무시), api_memo_delete(1513행)는 @require_role(중간관리자) 등급게이트일 뿐 작성자 일치 검사가 아님을 실제 재현(16개 검사)으로 확인 — 두 관리자의 표시이름이 완전히 같아도(둘 다 김철수) actor()가 로그인id 접미사를 붙이므로(라운드170) memos.author는 서로 다르게 남고, 하위관리자는 자기 메모든 남의 메모든(최고관리자 포함) 삭제 시도 시 전부 403, 중간관리자는 작성자 등급 무관(최고관리자가 쓴 메모도) 삭제 가능 — 이 코드베이스 전역의 '등급기반 권한, 작성자기반 아님' 원칙과 일치, 신규결함 아님. run_all_tests.py 전체 정독 + 키워드 grep 대조로 기존 라운드와 안 겹침 확인(라운드339=admin.js 처리버튼 등급표시 UI만, 라운드441=defects 목록 SELECT * 스키마드리프트만, 라운드170/325=admin 계정 개명을 통한 감사로그 행위자 위조만 — 전부 다른 질문). 코드 수정이 없는 순수 클린 확인이라 되돌림-증명 절은 없음(되돌릴 옛 코드가 없음) — 대신 경계마다 양성대조(자기 조직·자기 등급으로는 실제 성공)와 음성대조(경계를 넘으면 응답은 성공해도 DB는 그대로이거나 403)를 함께 확인해 헛테스트가 아님을 스스로 증명. 회귀테스트(test_scan_round472_fixes.py, 32개 검사) 신설 — app.py 변경 없음(클린 확인만, 서버 재기동 불필요)."),
    ("test_scan_round475_fixes.py", "스캔 475라운드 회귀 — manage.py go-live의 데모계정 정리가 마지막 최고관리자를 지울 수 있던 결함(영구 락아웃), 1건 + cmd_check 사전점검 강화. 정밀조사 Agent가 후보A(최고관리자 0명 방지)의 원안(자기강등·동시강등)은 라운드435가 이미 실스레드 동시성까지 실측해 다뤘음을 run_all_tests.py 원문 대조로 확인 — api_admin_update·api_admin_delete는 self든 other든 구분 없이 같은 코드경로라 별개 케이스가 아님을 직접 코드로도 재확인해 다른 경로로 교체. HTTP API 이외에 admins 테이블을 지우는 유일한 다른 지점(manage.py DELETE FROM admins)을 grep으로 찾아, cmd_go_live()의 데모계정 정리(admin·staff 삭제)가 api_admin_delete()(app.py 1738-1759행)와 달리 '마지막 최고관리자면 거부' 가드가 전혀 없음을 발견 — create-admin CLI의 --role 기본값이 중간관리자(920-930행)라, go-live 전에 새 관리자를 --role 없이 추가하는 자연스러운 실수만으로 데모계정 'admin'(그때까지 유일한 최고관리자)이 그대로 삭제돼 웹 콘솔에서 최고관리자를 다시 만들 방법이 없는 영구 락아웃이 됨을 실제 CLI 서브프로세스(init --with-demo → create-admin → go-live --yes)로 재현. cmd_check(316행)·cmd_go_live 자신의 사후보고(2102·2143행) 둘 다 SELECT COUNT(*) FROM admins로 등급 구분 없이 전체 개수만 세어, 이 락아웃 상태에서도 '관리자 계정 N개'로 정상표시됨도 함께 확인 — cmd_check 자신의 주석(312-315행)이 정확히 이 시나리오를 우려하면서도(go-live가 admin·staff를 지우는데 그 상태로 배포가능이 뜨면 콘솔에 아무도 못 들어간다) 구현이 그 의도를 못 지킴을 확인. 운영 DB 읽기전용 검산 — 현재 admins는 admin(최고관리자)·staff(중간관리자) 2개뿐이고 go_live_at은 아직 NULL(go-live 미실행) — 이 결함은 아직 실제 사고를 낸 적 없는 잠재 결함이며, go-live 전에 최고관리자 아닌 관리자를 먼저 추가하는 실무상 있을 법한 순서를 밟아야 발현됨을 확인. 그냥 고치면 되는 것 — 조건 하나(역할=최고관리자)만 정확히 보면 되고, 최고관리자가 0명인 상태는 어떤 시나리오에서도 정상이 아니라 트레이드오프가 없음. 고침: (1) cmd_go_live()의 admins 삭제 직전에 그 계정이 마지막 최고관리자인지 확인해, 그렇다면 삭제를 건너뛰고 경고만 남김(다른 데모정리는 계속 진행, go-live는 재실행 가능하므로 실제 최고관리자를 만든 뒤 다시 돌리면 그때 지워짐) — 형제(api_admin_delete)와 같은 패턴 이식, 새 메커니즘 없음. (2) cmd_check()의 사전점검도 최고관리자 0명을 별도로 감지하도록 강화(자신의 기존 주석이 이미 밝힌 의도와 실제 구현의 괴리를 바로잡음, 방어심화) — go-live가 이제 이 상태를 안 만들지만 수동 DB 조작 등 다른 경로에 대한 안전망으로 유효. manage.py 자신의 사후보고(2102·2143행)는 (1)의 수정만으로도 더 이상 오도되지 않아 손대지 않음. 회귀테스트(test_scan_round475_fixes.py, 11개 검사) 신설 — 실제 python manage.py 서브프로세스(init --with-demo → create-admin realops1(--role 생략) → go-live --yes → check)로 고쳐진 코드는 'admin'을 남기고 형제 데모계정('staff')은 정리하며 check가 최고관리자 존재를 정상 보고함을, manage.py 두 지점을 서브프로세스 실행 직전에만 임시로 옛(취약) 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오에서 'admin'이 실제로 삭제돼 영구 락아웃이 되고 check도 이를 놓침을 실측해 되돌림-증명 — 첫 실행(사소한 자체 어서션 오류 1건 수정 후) 11/11 통과. manage.py는 app.py가 import하지 않는 독립 CLI 도구라 서버재기동 불필요, BUILD_HASH 변화 없음(실측 확인 예정)."),
    ("test_scan_round476_fixes.py", "스캔 476라운드 회귀 — 협력사 건설업 등록조사(api_partner_license, app.py)가 '무등록'으로 기록할 때 진행 중 사건·미지급 정산·열린 하자를 안 보여주고 확인도 안 받던 결함, 1건. 정밀조사 Agent가 후보B(보험사 계약상태 비활성화 시 진행중 사건 처리)는 라운드437이 이미 이 정확한 문제(_insurer_exit_load가 cases를 안 보던 것)를 고치고 남은 2건의 소규모 백로그까지 정확히 문서화해 뒀음을 run_all_tests.py 원문 대조로 확인 — 다시 다루면 라운드437 결론 재생산일 뿐이라 다른 각도(하자보증 만료 후에도 접수 자체가 허용되는지)로 교체, 그 결과는 완전 클린(경고 없이 접수만 되고 cost_bearer가 시행사→협의필요로 정확히 바뀜 — 피해자 보호가 우선인 의도된 설계, 라운드64는 warranty_months=0 표시버그만 다뤄 겹치지 않음을 확인). 후보A(협력사 등록상태 재조사의 소급 적용)는 실제 결함으로 확정 — license_status를 쓰는 8개 진입관문(candidates·assign_dispatch·settle_agreement·각종 낙찰확정 등, 라운드52·62)은 전부 '신규 계약이 맺어지는 순간'만 재확인하고, 이미 진행 중인(시공중) 계약에는 아무 영향이 없음을 license_block_reason() 자신의 docstring 으로도 재확인. 유일한 쓰기지점 api_partner_license()(@require_role(하위관리자), 최하위 등급)는 진행중 사건 확인이 전혀 없어 실측 재현(시공중 사건을 둔 업체를 확인 없이 무등록으로 전환 시도 시 200)됨 — 형제 필드(status)의 퇴출/경고 전환에는 이미 _partner_demote_gate/_partner_exit_load(8094-8142행)라는 정교한 확인관문(진행중사건·미지급정산·열린하자를 보여주고 confirm_demote 없으면 409 PARTNER_HAS_WORK)이 있는데 '무등록'(도급 적법성의 법정 판정 기준, 건설산업기본법 제25조②— status 필드보다 오히려 법적으로 더 무거움)에는 그 상대가 전혀 없는 비대칭을 확인. 운영 DB 읽기전용 검산 — 활성 400곳 중 399곳이 미확인 상태이고 그중 3곳이 지금 이 순간 진행중 사건을 안고 있어(공개 사건 23건) 가상의 위협이 아니라 근시일 내 실제로 부딪힐 수 있는 상황임을 확인. 그냥 고치면 되는 것 — 이미 진행중인 도급을 자동으로 멈추거나 재배정하는 새 정책은 손대지 않고 형제와 같은 '정보성 확인관문'만 이식(제품판단 필요한 부분은 명확히 분리해 손대지 않음). 고침: api_partner_license()에 '무등록' 전환 시 _partner_exit_load()(기존 헬퍼 재사용)로 진행중 상태를 확인해, confirm_license가 없고 걸리는 일이 있으면 형제와 같은 PARTNER_HAS_WORK 409를 반환(단 메시지는 license_status의 실제 결과—로그인·완료보고는 안 막힘—에 맞게 새로 작성, _partner_demote_gate 자체는 안 건드림). 프런트 두 호출부(licenseSave·대량조사화면 ACT.licSet)에 confirm_license 재시도 배선 추가 — 기존 demoteConfirm() 함수는 '포털 로그인·완료보고가 막힌다'는 status 전용 고정문구라 license_status에는 사실과 달라(재사용하면 오정보) 재사용하지 않고, 서버가 이미 정확하게 써 준 error 문구를 그대로 confirm()에 넘기는 더 단순한 방식 채택. 회귀테스트(test_scan_round476_fixes.py + 서브프로세스 워커 test_scan_round476_worker.py, 9개 검사) 신설 — 실제 Flask 앱(스크래치 DB, 시공중 사건을 안고 있는 업체)으로 등록조사 라우트를 확인 없이 호출하면 409+license_status 불변, confirm_license를 붙이면 200+반영됨을, app.py 소스를 서브프로세스 실행 직전에만 임시로 옛(취약) 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오에서 확인 없이 첫 호출만으로 즉시 반영돼 버림을 실측해 되돌림-증명 — 첫 실행 9/9 통과. app.py·static/admin.js 둘 다 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round477_fixes.py", "스캔 477라운드 회귀 — 1차합의(현장 견적) 승인 경합에서 진 쪽이 받는 NOT_PENDING 409가 이미 fetch해 둔 합의 정보(승인자·확정금액·시각)를 버리고 맨 문구만 돌려주던 결함 + 보험사 포털(insurer_portal.html)의 faDecide·doAward 둘 다 실패 분기에서 성공 분기와 달리 모달을 안 닫고 새로고침도 안 하던 결함, 총 2건. 정밀조사 Agent가 후보B(협력사 정산계좌 평문유출 경로)를 먼저 조사 — bank_account_enc/decrypt() 6개 호출지점 전수 대조 + 실제 운영 로그의 최근 약 10일간 '복호화 실패' 경고 357건 전수 확인(전부 같은 안전한 일반 메시지만 남기고 평문·암호문 유출 0건)으로 클린 확정. 후보A(1차합의 동시승인 경합의 사용자경험)에서 실결함 발견 — 형제 비교: api_insurer_award()의 ALREADY_AWARDED 409는 '(현재 상태: {status})'로 현재 상태를 알려주고 dispatch.py의 settle_agreement() 가드도 '(현재 상태 X · 담당 Y)' 식으로 상태+행위자를 알려주는데, api_insurer_field_agreement_decision()의 NOT_PENDING 409만 line 17722에서 DP.agreement_view(conn, cid)로 합의 전체 행을 이미 fetch해 놓고도 그대로 버린 채 '승인 대기 중인 현장 견적이 없습니다.'만 돌려줬음을 app.py·dispatch.py 직접 대조로 확인. 프런트도 같은 파일 내 faDecide·doAward 둘 다 성공 분기(closeModal·reload·show)와 달리 catch 분기가 toast만 하고 모달을 안 갱신함을 직접 확인(1099-1123행·1385-1404행). 고침: 이미 fetch해 둔 a의 status·approver_name을 형제 관용구 그대로 에러 문자열에 포함(백엔드 한 지점), 두 catch 분기 모두 성공 분기와 같은 closeModal·reload·show 호출 추가(프런트 두 지점) — 새 포맷팅 로직이나 공용 헬퍼를 새로 만들지 않고 기존 형제의 문구 관용구·기존 성공분기의 정리 호출을 그대로 재사용. 회귀테스트(test_scan_round477_fixes.py + 서브프로세스 워커 test_scan_round477_worker.py, Node vm 프런트 harness 포함, 20개 검사) 신설 — 실제 Flask 앱(스크래치 DB)으로 사건접수→출동→도착→1차합의 개시까지 실제 진행시킨 뒤 보험사가 승인(이긴 쪽)한 직후 같은 사건에 다시 결정을 시도(진 쪽)하는 실제 HTTP 경합을 재현하고, app.py의 새 블록과 insurer_portal.html의 새 catch 두 곳을 서브프로세스 실행 직전에만 임시로 옛 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오에서 진 쪽이 맨 문구만 받고 모달도 안 갱신되는 옛 동작이 실제로 재현됨을 실측해 되돌림-증명 — 첫 실행 20/20 통과. app.py·templates/insurer_portal.html 둘 다 변경이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round479_fixes.py", "스캔 479라운드 회귀 — 477라운드가 insurer_portal.html의 faDecide()·doAward()에서 고친 '성공 분기는 모달을 정리하는데 catch 분기는 toast만 하고 낡은 모달을 방치한다' 패턴의 형제 자리 4곳, 정밀조사 Agent가 같은 두 파일 전체를 catch(e){ toast(e.message); } 형태로 전수 grep해 발견 — ① insurer_portal.html coAck()(추가공사 증액 확인/부동의) ② 같은 파일 rejectBids()(낙찰승인 모달 안, doAward() 바로 옆 버튼 — 같은 모달을 공유해 doAward가 먼저 낙찰을 승인하면 이 버튼이 걸림) ③ 같은 파일 cancelCase()(입찰 0건일 때만 뜨는 버튼 — 취소사유 prompt 입력 중 입찰이 들어오면 TOCTOU) ④ partner_portal.html reestimateGo()(실사 후 증액 요청). 네 곳 모두 대응 백엔드 라우트의 실제 도달 가능한 409를 직접 확인(app.py: api_insurer_co_ack의 CO_CLOSED/NO_AMOUNT 13472-13486, api_insurer_case_cancel의 HAS_BIDS 4346-4350·버튼이 !bids.length일 때만 뜸을 insurer_portal.html:970에서 확인, api_insurer_reject_bids의 409 4419-4421, api_change_order_create의 409 두 곳 10069-10080) — 에이전트가 인용한 파일:줄번호를 전부 직접 재확인, 오차 없음. 같은 두 파일에서 겉보기엔 비슷하지만 실제로는 다른 자리(submitDefect·submitDispute· pSaveProfile·재경매 입찰제출 — 실패해도 입력값 보존이 정상 UX인 폼, coSend()— try 이전에 무조건 closeModal 하는 별개 설계, approveDone()— 애초에 모달을 안 여는 버튼)는 형제결함이 아니라고 에이전트가 정확히 구분했음도 확인. 고침: 477라운드와 동일 — 각 함수 자신의 성공 분기가 이미 하는 정리호출(closeModal·reload 또는 boot·show)을 catch 분기에 그대로 옮김(새 헬퍼 없이 4곳 각각 인라인, 함수마다 자기 성공분기의 고유 스타일 그대로 유지 — await reload() vs reload().then() 등 섞지 않음). 회귀테스트(test_scan_round479_fixes.py, Node vm 실행 24개 검사) 신설 — 4개 함수 전부 되돌림-증명(옛 한줄짜리 catch로 임시 되돌리면 정리호출이 실제로 안 일어남을 확인 후 원복). rejectBids·cancelCase는 성공분기가 reload().then(show) 형태로 await 없이 체이닝돼 있어 테스트 harness가 외부 await만으로는 그 콜백 완료 전에 결과를 읽을 위험이 있음을 미리 인지해 매 시나리오 뒤에 setTimeout(0) 마이크로태스크 플러시를 넣어 해결 — 첫 실행 24/24 통과(플레이키 없음). app.py 변경 없음, templates 2개(insurer_portal.html·partner_portal.html)만 변경."),
    ("test_scan_round481_fixes.py", "스캔 481라운드 회귀 — 477·479라운드가 insurer_portal.html·partner_portal.html에서 고친 '성공 분기는 모달·목록을 정리하는데 catch 분기는 toast만 하고 낡은 모달을 방치한다' 패턴의 형제 자리가 admin.js(관리자 화면)에도 3곳 있었음, 정밀조사 Agent가 발견 — ① agRequest(1차합의 승인요청, admin.js:4833-4843) ② agSettle(1차합의 부동의 기록, 4846-4859, field-agreement open+settle 두 API 순차호출) ③ dpAssign(출동 직접배정, 4682-4708)의 두 실패경로 — DISPATCH_LIVE 재시도(supersede)가 다시 실패하는 안쪽 catch, DISPATCH_LIVE가 아닌 다른 409로 떨어지는 바깥 fallback. 대응 백엔드 409 전부 직접 재확인(app.py·dispatch.py): api_field_agreement_open의 '이미 1차 합의가 부동의로 끝난 사건'(17563-17565)·'현장 사진이 확보된 출동 건이 없습니다'(17584-17585, open_agreement()의 세 반환-None 사유를 감쌈), api_field_agreement_settle이 전달하는 settle_agreement()의 '이미 처리된 건입니다'(dispatch.py:1135-1137)·'상태가 바뀌어 처리하지 못했습니다'(1158-1160, rowcount TOCTOU), assign_dispatch()의 '배정할 수 있는 상태가 아닙니다'(477-479)·'이미 다른 업체가 현장에 도착해 사진을 확보한 사건입니다'(490-492). 고침: 477·479라운드와 동일 원칙 — 각 catch 분기가 자기 자신의 성공 분기와 같은 정리호출(closeModal·VIEWS.dispatch())을 그대로 옮김(새 헬퍼 없이 4개 지점 각각 인라인). 회귀테스트(test_scan_round481_fixes.py, Node vm 실행 24개 검사, dpAssign의 중첩 catch 구조 때문에 처음엔 추출 함수가 admin.js 전체 에서 유일하지 않은 '}catch(e2){'를 파일 맨 앞부터 찾아 엉뚱한 함수의 블록을 뽑는 자체 버그를 겪음 — dpAssign 함수 시작 위치 뒤로 검색 범위를 좁혀 수정 후 재실행 24/24 통과) 신설 — 4개 catch 지점 전부 되돌림-증명(옛 한 줄짜리 catch로 임시 되돌리면 정리호출이 실제로 안 일어남을 확인 후 원복) 포함."),
    ("test_scan_round482_fixes.py", "스캔 482라운드 회귀 — dispatch.py의 _claim_lease()가 이 파일의 다른 BEGIN IMMEDIATE 10곳과 달리 try/except 없이 벌거벗어 있던 결함, 1건. 정밀조사 Agent가 이 세션이 이미 33개 비테스트 .py 파일 전부를 최소 1회씩 정밀감사했음을 run_all_tests.py 전수 대조로 확인한 뒤, 새 파일을 찾는 대신 dispatch.py(1296줄, 257·281·315·329·411·462· 463·465·469·476·477·481라운드가 특정 함수 단위로만 다뤄옴) 전체를 함수 단위가 아니라 '이 파일의 트랜잭션 안전장치 관례 자체'라는 새 각도로 재감사 — 11개 BEGIN IMMEDIATE 호출을 전수 대조해 10개는 전부 바로 다음 줄이 try:(같은 파일의 except Exception: conn.rollback(); raise 관례)인데 _claim_lease()(707-717행) 하나만 없음을 확인. 호출부 sweep_dispatches()(734행)도 _claim_lease(conn) 호출(766행)이 자기 자신의 try 블록(770행) 밖에 있어, UPDATE가 예외를 던지면(락 경합으로 busy-timeout 초과 등 — 이 리스 자체가 겹친 예약실행을 막는 용도라 락 경합이 바로 이 자리에서 가장 일어나기 쉬움) sweep_dispatches() 밖까지 그대로 터짐을 확인. manage.py cmd_sweep()(989-1032행)의 유일한 try에도 except가 없고(finally만) main()(2725-2734행)도 COMMANDS[cmd] 호출을 try로 안 감싸 예외가 프로세스를 그대로 죽임을 직접 확인 — 이 경로는 실제 Windows 작업 스케줄러가 5분마다 pythonw.exe(콘솔 없음, 리눅스 crontab 줄과 달리 출력 리다이렉트도 없음)로 도는 그 경로임을 cmd_install_scheduler() 코드로 확인(app.py의 관리자 수동버튼은 force=True라 _claim_lease를 아예 안 부름 — 그 경로는 안 걸림, 17506-17511행 확인). 고침: 형제 _release_lease()(720-731행, 리스 확보 실패는 5분 뒤 다음 예약실행이 재시도하면 회복되는 문제라 예외를 삼키고 로그만 남기는 원칙)와 같은 원칙 적용 — 예외를 삼켜 호출부의 기존 정상 경로('다른 워커가 리스를 쥐고 있음', claimed=False)로 합류시킴(단순 재발생(raise)은 호출부가 자기 try 밖에서 부르는 구조라 여전히 그대로 새어나가 문제를 안 고치므로 기각 — 재조사 Agent가 이 판단을 유보했던 것을 이어받아 검증팀이 직접 결정). rollback은 이 함수만의 고유 필요(BEGIN IMMEDIATE를 직접 여는 유일한 자리). 회귀테스트(test_scan_round482_fixes.py, 8개 검사) 신설 — job_locks 테이블을 실제로 지워 UPDATE 자체가 sqlite3.OperationalError를 던지게 만든 뒤 (a) 예외가 안 새고 False를 반환하는지 (b) 같은 커넥션의 다음 BEGIN IMMEDIATE가 'cannot start a transaction' 없이 정상 진행되는지(rollback 증명)를 실제 실행으로 확인, dispatch.py를 서브프로세스 실행 직전에만 임시로 옛(벌거벗은) 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오 에서 예외가 실제로 새 나감을 실측해 되돌림-증명 — 첫 실행 8/8 통과. dispatch.py는 app.py가 import하는 모듈이라 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round483_fixes.py", "스캔 483라운드 회귀 — 보험사 등록(api_insurer_create)·관리자수정(api_insurer_update)이 형제(api_insurer_profile_update 3177행· api_partner_create 7988행·api_partner_update 8262행)와 달리 RE_EMAIL 형식검사가 빠져 있던 결함, 2건. 정밀조사 Agent가 482라운드의 '파일 전체를 하나의 관례로 재감사' 방법론을 app.py의 특정 컬럼(insurers.email) 형제경로 전수대조로 확장 적용해 발견 — RE_EMAIL.match() 호출 실제 8곳(3024·3177·5480·7455·7988·8262·8982·9106행)을 전수 grep, api_insurer_create(8546-8605)·api_insurer_update(8608-8676) 본문에는 하나도 없고 이메일은 FIELD_LIMITS 길이제한만 받음을 직접 확인. 협력사 쪽은 등록·관리자수정·자기수정 세 곳 전부 검사하는데 보험사만 자기 수정(마이페이지) 한 곳뿐인 비대칭 — 형식이 깨진 이메일이 관리자 등록·수정 화면으로 심어지면, 그 보험사가 나중에 마이페이지에서 이메일과 무관한 필드 하나만 고쳐도(화면이 manager/dept/phone/email 4개를 통째로 재전송) 그 자리에서 비로소 400이 뜬다 — 정작 값을 깨뜨린 등록·수정 화면에는 아무 경고가 없었다. 80라운드가 정확히 이 클래스로 5개 함수(api_partner_update·create·application_create· partner_profile_update·insurer_profile_update)에 검사를 붙였는데 이 두 함수는 그 목록에 없었고, 169라운드가 같은 두 함수를 건드렸지만 그 라운드 자신의 주석이 길이제한만 언급함을 직접 재확인(형식검사는 다룬 적 없음). 고침: 형제(api_partner_create·api_partner_update)와 정확히 같은 문구·조건으로 이식(새 헬퍼 없이 각 지점 인라인). 회귀테스트(test_scan_round483_fixes.py + 서브프로세스 워커 test_scan_round483_worker.py, 14개 검사) 신설 — 실제 Flask 앱(스크래치 DB)으로 형식이 깨진 이메일('담당자@손해보험', TLD 없음)로 등록·수정을 실제 HTTP 왕복으로 시도해 400 거부 + DB에 실제로 안 남음을 확인, 정상 이메일은 통과함도 확인(과잉차단 아님). app.py의 새 블록 두 곳을 서브프로세스 실행 직전에만 임시로 옛(검사 없음) 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) 같은 시나리오에서 형식이 깨진 이메일이 실제로 DB에 그대로 저장돼 버리는 옛 동작이 재현됨을 실측해 되돌림-증명 — 첫 실행 14/14 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round484_fixes.py", "스캔 484라운드 회귀 — email과 짝인 RE_PHONE(app.py:5437, 지금까지 공개폼 clean_public_form 단 한 곳에만 쓰임) 형식검사가 12개 형제 경로 전부에 빠져 있던 결함. 482·483라운드의 '형제경로 전수대조' 방법론을 email→phone 축으로 확장한 정밀조사 Agent가 발견 — 이 세션이 12곳 전부 직접 Read로 재확인(오차 없음). 형식이 깨진 연락처가 어디로 심기든 notify_popbill.normalize_phone()은 휴대전화 형식만 통과시키므로(모바일 전용 설계) 오타·쓰레기값이 '번호 없음'과 구분이 안 돼, _notify_phone()을 거치는 모든 알림(경매 마감임박·낙찰승인·완료보고 독촉·피해자 진행조회 안내 등)이 영원히 조용한 실패로 빠진다. 12곳: api_partner_profile_update(3018)·api_insurer_profile_update(3172)·api_application_create(7452)·api_partner_create(7986)·api_insurer_create(8571)·api_partner_update(8256)·api_insurer_update(8664)·api_contact_update(8997)·api_contact_import(9119, 엑셀 일괄등록)·_create_case(3966, 공유헬퍼·피해자연락처)·api_case_create(10825)·api_case_edit(9907) — 전부 같은 함수 안 email(또는 형제)이 이미 RE_EMAIL을 쓰는데 phone만 빠진 비대칭임을 직접 대조. 고침: 각 지점이 이미 쓰는 RE_EMAIL 검사와 정확히 같은 관례로 이식 — conn.close 유무·raise(CaseInputError) vs jsonify·스킵+보고(엑셀) 등 그 함수 자신의 기존 스타일을 각각 그대로 따름(새 헬퍼 발명 없음, 12곳 각각 인라인). 회귀테스트(test_scan_round484_fixes.py + 서브프로세스 워커 test_scan_round484_worker.py, 51개 검사) 신설 — 실제 Flask 앱(스크래치 DB)으로 12곳 전부에 형식이 깨진 연락처를 실제 HTTP/직접호출로 보내 정확한 거부문구까지 확인(첫 시도에서 사건등록 경로의 WORK_MAJORS 실제 표기를 몰라 엉뚱한 사유로 400이 뜬 자체 테스트 버그를 body 검증으로 잡아내 수정), 정상 연락처는 통과함도 확인. app.py의 12개 새 블록을 서브프로세스 실행 직전에만 전부 동시에 임시 제거하면(각 블록이 자기완결적이라 제거만으로 원본이 정확히 복원됨을 자체 검증, finally에서 원본과 바이트단위로 복원) 같은 시나리오에서 12곳 전부가 형식이 깨진 연락처를 그대로 통과시키는 옛 동작이 재현됨을 실측해 되돌림-증명 — 첫 실행 51/51 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round485_fixes.py", '스캔 485라운드 회귀 — int(float(x))가 x=\'inf\'/\'-inf\'/\'1e400\'류일 때 ValueError가 아니라 OverflowError를 내는 함정을, 형제 parse_days()(app.py:457-461, 396·423라운드가 이미 이식)는 아는데 같은 파일의 두 자리가 못 물려받았던 결함, 2건. 정밀조사 Agent가 482~484라운드의 \'형제경로 전수대조\' 방법론으로 이미 감사된 후보(valid_biz_no·RE_EMAIL· RE_PHONE·FIELD_LIMITS·권한데코레이터·dispatch.py BEGIN IMMEDIATE 등)를 전부 run_all_tests.py 대조로 배제한 뒤 발견 — int(float(\'inf\'))가 실제로 OverflowError를 냄을 Python 인터프리터로 직접 재현. ① _setting_int()(3738-3749, "설정이 깨졌다고 업무가 멈추면 안 되므로 예외를 위로 던지지 않는다"고 문서화된 공유 헬퍼)의 except가 이 한 예외만 못 잡음 — 같은 위협모델(settings 테이블의 \'inf\' 문자열)을 365라운드가 형제 _bid_weights()에서 이미 실제로 겪고 고친 전례가 있음(test_scan_round365_fixes.py:108). ② api_settings_set()의 RANGES 검증 루프(20578-20583)도 같은 함정 — 못 잡으면 "숫자여야 합니다" 400 대신 전역 오류핸들러(1219)가 뜻모를 500을 냄. 둘 다 이 세션이 직접 Read로 재확인(app.py 전체에서 OverflowError를 잡는 곳은 parse_days 461행 단 한 곳뿐임을 grep으로 확인), dispatch.py 자신의 독자 _setting_int()(78-84)는 int(str(x))를 바로 써서 이 버그가 원천적으로 없음도 확인. 심각도는 낮음(①은 이미 최고관리자 권한 필요, ②는 트리거 경로가 DB 직접조작·향후 회귀 의존적) — 그래도 형제가 이미 아는 함정을 못 물려받은 명백한 결함이라 수정. 고침: 두 곳 다 parse_days()와 정확히 같은 방식 — except 튜플에 OverflowError만 추가(새 헬퍼·구조변경 없음, 최소diff). 회귀테스트(test_scan_round485_fixes.py + 서브프로세스 워커 test_scan_round485_worker.py, 11개 검사) 신설 — settings.min_bidders=\'inf\'를 실제로 넣고 _setting_int()를 직접 호출해 예외 없이 기본값 반환을, 실제 Flask PATCH /api/settings에 dispatch_minutes=\'inf\'를 보내 500이 아니라 400+정확한 문구를 확인. 처음엔 같은 프로세스에서 importlib.reload(app)으로 되돌림을 재현하려다 RecursionError(Flask 앱 reload의 알려진 함정)를 직접 겪어, 이 세션의 다른 모든 되돌림-증명과 같은 서브프로세스 방식으로 교체 — app.py의 두 새 except 튜플을 서브프로세스 실행 직전에만 임시로 옛(OverflowError 못 잡는) 코드로 되돌리면(파일을 실제로 잠깐 고쳤다가 finally에서 원본과 바이트단위로 동일하게 복원) OverflowError가 그대로 새고 500이 뜨는 옛 동작이 재현됨을 실측해 되돌림-증명 — 첫 실행(reload 문제 수정 후) 11/11 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ("test_scan_round486_fixes.py", '스캔 486라운드 회귀 — admin.js caseDetail() 모달의 사건 액션 10곳(auctionDeadline·caseReopen·caseCloseOffline·caseUndoNoRepair·caseFailBidding·caseApprove·caseCancelAward·caseOpenAuction·caseToDispatch·saveCaseEdit)이 462·477·479·481라운드가 세운 모달미갱신 패턴을 그대로 갖고 있던 결함. 이 원칙을 설명하는 481라운드의 주석(admin.js:6452-6453) 바로 다음 함수부터 10곳 전부 직접 확인, 대응 서버 409(api_case_reopen·close_offline·undo_no_repair·fail_bidding·approve·cancel_award·open_auction·to_dispatch·api_case_edit)도 직접 확인. 고침: 각자 자기 성공분기의 정리호출을 catch로 이식. 회귀테스트(test_scan_round486_fixes.py, Node vm, 27개 검사) — 10곳 소스확인+실행확인, 대표 3곳(서로 다른 정리호출 모양) 되돌림-증명 — 맥락 예산 제약으로 10곳 전부의 되돌림-증명은 생략(정직하게 밝힘). 27/27 통과. app.py 변경 없음, static/admin.js만 변경.'),
    ("test_scan_round488_fixes.py", "스캔 488라운드 회귀 — api_otp_confirm()(2단계 인증 등록확인, app.py:2719)이 형제(api_login_otp·api_login의 OTP 관문·api_otp_disable, 라운드413·414)와 달리 _recent_fails 무차별대입 잠금이 없던 결함. 정밀조사 Agent가 발견 — 30회 오답을 실제로 보내도 안 잠기는데(대조군 /api/login/otp는 6회째 429) 정작 TOTP 자체 회전주기 덕에 실사용 위험은 낮음을 인지하고도 형제 4곳 중 이 곳만 방어가 빠진 비대칭으로 보고. 이 세션이 직접 코드 재확인(api_otp_disable의 _recent_fails(conn,'PWX:'+uname) 패턴, api_login의 OTP 실패분기가 _log_attempt 뒤 반드시 conn.commit()함을 직접 대조) 후 수정. 고침: api_otp_disable과 같은 관례로 _recent_fails(conn,'OTPSETUP:'+uname) 검사(MAX_LOGIN_FAILS 초과 시 429)를 TOTP.verify 호출 앞에, _log_attempt(conn, otp_key, ok)를 호출 뒤에 추가. 회귀테스트 작성 중 자체 버그 2건 발견·수정: ①실패분기에 conn.commit() 누락으로 _log_attempt의 INSERT가 실제로 커밋 안 돼(conn.close()가 롤백) 잠금이 전혀 안 걸리는 진짜 버그를 실행 중 발견해 app.py 자체를 수정(형제 api_login의 OTP 실패분기가 이미 conn.commit(); conn.close() 패턴임을 확인 후 이식) ②되돌림-증명 로직이 두 삽입지점(검사블록·_log_attempt 호출) 사이에 원본 코드(u=one() 조회·TOTP.verify 호출)가 그대로 있다는 걸 놓치고 하나로 뭉뚱그려 제거하려다 원본까지 지울 뻔한 걸 IndexError로 발견해 두 지점을 독립적으로 추출·제거하도록 수정. 최종 test_scan_round488_fixes.py(+워커) 7/7 통과 — 실제 Flask 서브프로세스로 10회 반복 시 429 발생 확인, 되돌림 시 429가 전혀 안 걸리는 옛 동작 재현 확인."),
    ('test_scan_round489_fixes.py', '스캔 489라운드 회귀 — /api/address/search·addr_search.search()의 검색어(q)에 하한(2자)만 있고 상한이 없던 결함. 정밀조사 Agent가 우선순위 지정 각도(488라운드 부차 발견의 재검증)로 확인 — 실제 몽키패치 실행재현으로 한글 5만자 입력 시 450,076바이트짜리 외부 URL이 만들어짐을 확인했고, 이 세션이 동일 스크립트를 독립적으로 재실행해 정확히 같은 수치(450076/50076/1800076)로 재현·검증했다. addr_search.py:157-159가 실시간 라우트(app.py api_address_search)와 geocode_fill.py 배치 양쪽의 유일한 공용 관문인데, _official/_open_map이 urllib.parse.quote(q)로 그대로 외부 URL에 이어붙임 — .env에 KAKAO_REST_KEY가 없어 실제로는 비공식 무인증 엔드포인트(_open_map)를 탄다. 위협모델은 즉각적 보안사고가 아니라 인증된 저신뢰 계정(협력사 포함, _mixed_actor_guard만 있음)이 서버를 대신 시켜 비공식 카카오 엔드포인트에 무제한 크기 요청을 보낼 수 있는 가용성 문제(남용 시 카카오 차단으로 전체 주소검색 기능이 죽을 위험) — 전역 rate limit(app.py:859, 분당 300회)은 횟수 제한이지 크기 제한이 아니고, waitress의 max_request_header_size 기본값 262144바이트(직접 설치된 waitress/adjustments.py:243 소스로 확인, serve_waitress.py는 max_request_body_size만 오버라이드)가 사실상 유일한 배경 상한이나 이는 이 필드를 위해 설계된 값이 아니다. geocode_fill.py 배치 경로는 partners.address/cases.address가 이미 저장 시점에 200자로 잘림(app.py:3983 _create_case, FIELD_LIMITS["address"]=200, clean_public_form)이 확인돼 안전, 실시간 HTTP 라우트만 무방비였음도 확인. 다른 request.args.get("q") 3곳(1634·15208·19842행)은 전부 내부 파라미터화 SQL LIKE 필터라 외부로 안 나가 이 결함이 코드베이스 전체 패턴이 아니라 이 한 함수에 격리됨도 확인. 고침: 이미 확립된 관례(FIELD_LIMITS["address"]=200, _create_case의 _s(d.get("address"),200))의 숫자를 그대로 재사용 — ①addr_search.search()(157-159행) 자체에 len(q)>200 상한 추가(공용 관문 한 곳만 고치면 라우트·배치 양쪽 방어) ②app.py의 api_address_search() 라우트에도 대칭으로 상한 분기 추가(보안 경계가 아니라 "결과 없음" 대신 "너무 깁니다" 원인 메시지를 보여주기 위한 사용자경험 계층, 기존 하한 검사와 같은 이중방어 형태를 그대로 따름). 회귀테스트(test_scan_round489_fixes.py + 서브프로세스 워커 test_scan_round489_worker.py, 14개 검사) 신설 — addr_search._open_map을 몽키패치해 201자 검색어가 실제로 외부 호출 함수까지 도달하는지(호출횟수 0)를 실행으로 확인, Flask 라우트도 실제 테스트클라이언트로 201자 요청 시 hint에 "너무 깁니다"가 오는지 확인. 두 지점 모두 단일 삽입(원본코드가 사이에 안 끼어있음)이라 488라운드와 달리 통짜 제거만으로 되돌림 — 되돌린 코드는 201자가 그대로 _open_map()까지 도달하고 라우트도 결과를 그대로 반환함을 실측해 되돌림-증명 — 14/14 통과. addr_search.py·app.py 둘 다 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ('test_scan_round490_fixes.py', '스캔 490라운드 회귀 — api_case_remind_report()(완료보고 독촉, app.py:16044)에 형제(api_settlement_remind_approval, 13005행, 라운드85)와 같은 BEGIN IMMEDIATE+ 24시간 쿨다운이 없던 결함. 정밀조사 Agent가 run_all_tests.py 384개 항목을 전수 대조해 새 각도(app.py 전체 BEGIN IMMEDIATE 감사·lightbox.js 캡션 이스케이프)를 찾는 과정에서 발견 — 이 세션이 직접 Read로 재확인(형제의 라운드85 주석이 정확히 "확인과 삽입 사이가 잠금 없이 비어 있었다"고 명시, notify()의 channel="알림톡"이면 status="발송대기"(app.py:1822)로 저장되고 sweep_send_notifications()가 그 상태를 실제 팝빌로 발송함을 확인, admin.js:2169-2170의 라운드249 주석이 이 라우트가 @require_admin(등급 무관)임을 이미 명시, 형제 프론트 버튼 caseRenotify(admin.js:6505) 는 confirm()이 있는데 caseRemindReport(admin.js:6201)만 없음도 확인). 위협모델: 등급 무관 관리자 계정의 빠른 더블클릭·반복클릭만으로 같은 시공사에게 무제한으로 실제 유료 알림톡이 중복발송(팝빌 과금 낭비, 협력사 알림피로). 고침: 형제와 정확히 같은 패턴 이식 — BEGIN IMMEDIATE 추가, 기존 조기반환 3곳 각각에 conn.rollback() 추가, notify() 호출 직전에 ntype=완료보고독촉 기준 24시간 쿨다운 SELECT 추가(형제와 같은 SQL, ntype만 교체) 위반 시 429 COOLDOWN, admin.js에도 형제(caseRenotify)와 같은 문구의 confirm() 추가. 회귀테스트(test_scan_round490_fixes.py+워커, 12개 검사) 신설 — 이 라운드의 수정은 함수 안 다섯 곳(BEGIN IMMEDIATE 삽입·기존 조기반환 3곳 각각의 rollback 추가·쿨다운 블록 삽입)에 흩어져 있어 개별 블록 추출로는 안전하게 못 되돌린다고 판단, 함수 전체를(데코레이터부터 자기 자신의 finally:conn.close()까지) 통째로 캡처해 이 세션이 수정 직전에 직접 Read해 둔 원본 전체 텍스트로 통째 치환하는 방식으로 되돌림-증명 — 실제 Flask 서브프로세스로 완료보고지연 상태의 사건을 만들어 연속 2회 호출한 결과, 새 코드는 1차 200·2차 429(발송대기 알림 1건)인데 되돌린 옛 코드는 2회 모두 200(발송대기 알림 2건, 중복발송 재현)임을 실측 — 12/12 통과. app.py·static/admin.js 둘 다 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인). [621라운드] 되돌림-증명이 원래 함수 전체를 실제 on-disk app.py에 통째로 써넣고 서브프로세스(자체 생성 워커 파일)로 재현한 뒤 복원하는 옛 세대 기법이었다 — 이제 ORIGINAL_FUNC 텍스트(데코레이터 제거)를 exec로 독립 사본 네임스페이스에 재구성해 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다(round488·507 패턴). 워커 생성 코드도 없앰(더 이상 워커 파일을 만들지 않음) — 파일명·설명은 그대로, 내부 구현만 교체(단독 재실행 14/14 통과 재확인).'),
    ('test_scan_round491_fixes.py', '스캔 491라운드 회귀 — api_case_renotify()(공고 재알림, app.py:19434)의 30분 쿨다운에 형제(api_settlement_remind_approval 라운드85· api_case_remind_report 라운드490)와 같은 BEGIN IMMEDIATE가 없어 진짜 동시요청 두 개가 똑같이 쿨다운을 통과해 알림이 중복발송될 수 있던 결함. 정밀조사 Agent가 지정 각도(notify() 호출하는 독촉/재알림류 라우트 전수조사)로 발견 — 수동 재알림 라우트 3곳(완료승인독촉·완료보고독촉· 공고재알림) 중 앞의 둘은 이미 고쳐져 있는데 세 번째만 빠진 비대칭을 확인. 이 세션이 직접 Read로 재확인(app.py:19447-19492, BEGIN IMMEDIATE 전혀 없음) 후, threading.Barrier로 두 스레드를 쿨다운 확인 SELECT 지점에 강제로 동시 도달시키는 재현 스크립트를 독립적으로 재실행해 같은 결과(두 요청 모두 200/ok=true, 감사로그·알림 각 2건)를 직접 확인했다. 대조군(경합 없이 순차 3번째 호출)은 정상적으로 429로 막혀, 결함이 체크 로직 자체가 아니라 동시성 창에만 있음도 확인. 고침: 형제와 정확히 같은 패턴 이식 — 함수 진입 직후 BEGIN IMMEDIATE 추가, 기존 조기반환 4곳(사건없음 404·열린공고없음 409·마감됨 409·쿨다운 429) 각각에 conn.rollback() 추가. 회귀테스트(test_scan_round491_fixes.py+ 워커, 12개 검사) 신설 — 이 라운드의 수정도 함수 안 다섯 곳에 흩어져 있어(BEGIN IMMEDIATE 삽입+조기반환 4곳 각각의 rollback 추가) 490라운드와 같은 이유로 개별 블록 추출 대신 함수 전체를 통째로 캡처해 원본 전체 텍스트로 치환하는 방식으로 되돌림 — 조사 에이전트가 쓴 것과 같은 진짜 threading.Barrier 경합 재현을 테스트에도 그대로 포함시켜, 새 코드는 동시요청 중 정확히 1건만 성공(감사로그·알림 1건)하고 되돌린 옛 코드는 2건 모두 성공(감사로그·알림 2건, 중복발송 재현)함을 실측해 되돌림- 증명 — 12/12 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ('test_scan_round492_fixes.py', '스캔 492라운드 회귀 — change_orders(변경견적) 생애주기 가시성 결함 2건. ①api_co_full_reauction()(app.py:10572)의 MAX_CO_ROUND(3) 소진(최종유찰 확정) 분기에 감사로그·통지가 전혀 없던 결함 — 같은 함수의 성공분기(전체 재경매 오픈)와 형제 dispatch.py(회차소진→수배실패, 840-848행)는 둘 다 DB.log를 남기는데 이 자리만 없었다. ②TODAY_BLOCKED(오늘 할 일)의 변경견적 항목이 거절·유찰 상태만 잡고 원업체가 응답하지 않는 원업체제안 상태는 전혀 안 잡던 결함 — change_orders에 응답기한 컬럼도, 그걸 보는 스윕도 없어(sweep_* 8개 전수확인 0건) 원업체가 알림을 놓치면 그 사건은 정산·재배정 둘 다 막힌 채(api_case_approve·api_case_cancel_ award가 CHANGE_ORDER_ACTIVE로 차단) 대시보드 어디에도 안 뜨고 무기한 방치될 수 있었다. 정밀조사 Agent가 같은 파일의 형제 분기 비교로 두 건 모두 발견하고 실행 재현(양성대조·교차파일대조 포함)까지 마쳤으며, 이 세션이 직접 Read로 재확인한 뒤 재현 스크립트를 독립 재실행해 같은 결과 (20일 방치돼도 스윕 무반응, 최종유찰 확정에 로그 0건 vs 정상 성공분기는 1건)를 확인했다. 고침: ①은 같은 함수 자신의 성공분기 및 dispatch.py의 정본 패턴 그대로 DB.log+notify(audience_type=admin) 추가(순수 삽입). ②는 새 스윕을 만드는 대신(그 구조는 라운드85·490·491이 이미 확립한 BEGIN IMMEDIATE 관례를 그대로 써야 하는 더 큰 작업) 가장 싼 수정 — 대시보드 SQL 조건에 원업체제안 AND 생성 2일 경과 조건을 추가. 회귀테스트(test_scan_round492_fixes.py+워커, 14개 검사) 신설 — ①은 순수삽입이라 블록 통짜 제거로, ②는 튜플 전체를 원본 튜플로 통째 치환하는 방식으로 각각 되돌림 — 실제 Flask 서브프로세스로 대조군(1차 거절건의 정상 2차 재경매는 로그 1건 유지, 회귀 없음 확인)·실측(라운드3 유찰건에 4차 시도 시 최종유찰 확정과 함께 로그·통지 각 1건) 그리고 TODAY_BLOCKED 항목을 app.py의 실제 런타임 리스트에서 직접 찾아 SQL을 그대로 실행해 3일 방치된 원업체제안 1건만 잡히고 방금 생긴 원업체제안은 안 잡힘을 확인 — 되돌린 옛 코드에서는 로그·통지 0건, 3일 방치도 안 잡힘을 재현해 되돌림-증명 — 14/14 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ('test_scan_round493_fixes.py', '스캔 493라운드 회귀 — api_partner_update()(업체 정보수정, app.py:8277)의 사업자번호 중복확인(DUP_BIZNO)에 형제 둘(api_application_update 승인관문· api_partner_create, 각각 round248/429가 이식 + 라운드466이 api_partner_ create에 BEGIN IMMEDIATE 추가)과 같은 잠금이 없어, 서로 다른 두 업체를 거의 동시에 승인·정정하면 둘 다 중복없음을 읽고 통과해 같은 사업자번호로 활성 업체 2곳이 생길 수 있던 결함. 정밀조사 Agent가 "형제 분기 비교" 방법론을 완전히 새로운 축(정산·웹훅·서류업로드)에 적용하다가 발견 — 정산 8개 라우트·웹훅 커밋순서 9곳은 전부 클린으로 확인(과잉조사 없이 솔직히 보고)하고, DUP_BIZNO 검사를 쓰는 정확히 3곳 중 이 함수만 BEGIN IMMEDIATE가 없는 비대칭을 찾았다. 이 세션이 직접 Read로 형제 둘(app.py 7552행·8010행)의 BEGIN IMMEDIATE와 주석까지 정확히 재확인한 뒤, 조사 에이전트의 재현 스크립트(두 연결의 SQL 실행 순서를 직접 통제)를 독립 재실행해 같은 결과(현재 코드는 두 연결 모두 중복없음을 읽고 통과, 대조군 BEGIN IMMEDIATE를 얹으면 둘째 연결이 스스로 막힘)를 확인했다. 고침: 형제 둘과 완전히 같은 처방 — conn = DB.get_db() 직후(이 함수 자신의 기존 try/finally 구조는 그대로 유지) BEGIN IMMEDIATE 추가, 기존 조기반환 5곳(없는 업체 404·DUP_BIZNO 409·FORBIDDEN 403·강등거부·NEED_REASON 400) 각각에 conn.rollback() 추가(신규 메커니즘 없음, 기계적 이식). 회귀테스트(test_scan_round493_fixes.py+워커, 12개 검사) 신설 — 라운드490·491과 같은 이유(수정이 함수 안 여섯 곳에 흩어짐)로 함수 전체를 통째로 캡처해 원본 전체 텍스트로 치환하는 방식으로 되돌림, 라운드491과 같은 진짜 threading.Barrier 경합을 실제 Flask 서브프로세스(서로 다른 두 협력사에 같은 사업자번호로 PATCH)에 적용 — 자체 테스트 버그 2건을 실행 중 발견해 수정(임의로 고른 사업자번호가 실제 검사숫자 알고리즘을 통과 못 해 400으로 조기 실패, 사유 문구가 5자 미만이라 NEED_REASON으로 조기 실패 — 둘 다 테스트 자신의 입력값 문제였지 코드결함 아님, 유효한 검사숫자를 계산하고 사유 길이를 늘려 재통과) — 새 코드는 동시요청 중 정확히 하나만 성공(200)하고 나머지는 DUP_BIZNO(409)로 막혀 활성 업체가 항상 1곳만 남고, 되돌린 옛 코드는 둘 다 200으로 통과해 같은 사업자번호로 활성 업체 2곳이 생기는 옛 동작이 재현됨을 실측해 되돌림-증명 — 12/12 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ('test_scan_round494_fixes.py', '스캔 494라운드 회귀 — 고유 로그인 자격증명 발급 4곳의 경합 결함. ①api_admin_create()(app.py:1666)는 형제 둘(api_admin_update· api_admin_delete)과 달리 BEGIN IMMEDIATE가 없어 같은 아이디로 동시에 두 번 생성하면 하나가 UNIQUE 위반으로 처리되지 않은 500이 났다. ②③issue_partner_login()(api_partner_credentials가 단건 호출)과 api_insurer_credentials()는 아이디 전역유일 규칙을 4개 표에 걸쳐 검사하면서도 잠금이 없어, 서로 다른 두 조직이(표가 다른 협력사-보험사 조합 포함) 같은 아이디를 동시 요청하면 양쪽 다 중복없음을 읽고 성공해 전역유일이어야 할 아이디가 두 표에 나뉘어 조용히(오류조차 없이) 생길 수 있었다 — 가장 심각한 변형은 UNIQUE가 표별이라 에러도 안 나서 감사로그에 흔적도 안 남았다. ④api_partner_bulk_credentials()도 같은 헬퍼를 공유해 같은 문제가 있었다. 정밀조사 Agent가 관리자계정 축을 조사하다 인접한 조직 자격증명 발급 축으로 확장해 발견 — 이 세션이 직접 Read로 형제(api_admin_update 1700행·api_admin_delete 1743행· api_insurer_apikey_issue 8794행)의 BEGIN IMMEDIATE를 재확인하고, SAVEPOINT 충돌 우려(일괄발급이 이미 라운드199 SAVEPOINT로 반복 중이라 공유헬퍼 안에 잠금을 넣으면 두 번째 항목부터 "이미 트랜잭션 안"이라 BEGIN IMMEDIATE가 에러난다는 주장)를 직접 코드 흐름으로 검증했다. 고침: ①은 형제와 동일 패턴(BEGIN IMMEDIATE+조기반환 rollback). ②는 공유헬퍼 안이 아니라 단건 호출부(api_partner_credentials)에 잠금 — 일괄발급은 별도로 배치 전체를 한 번에 감싸는 잠금을 그 함수 최상단에 추가(개별 SAVEPOINT는 그대로 유지, 이미 열린 트랜잭션 안에 중첩되므로 충돌 없음). ③은 형제(api_insurer_apikey_issue)와 동일 패턴, 조기반환 7곳 각각에 rollback 추가. 회귀테스트(test_scan_round494_fixes.py+워커 2개, 25개 검사) 신설 — SQLite 쓰기잠금이 테이블별이 아니라 DB 파일 전체 단위임을 이용해, 서로 다른 두 표(partners·insurers)에 각자 BEGIN IMMEDIATE를 걸어도 먼저 잡은 쪽이 커밋할 때까지 다른 쪽은 시작조차 못 해 나중 쪽이 항상 최신 상태를 보고 스스로 막힘을 실제 스레드로 재현 — 정확한 문장(barrier) 대신 중복확인 SQL에 짧은 인공지연을 주입해 두 스레드가 커밋 전에 반드시 겹치게 만드는 방식(여러 다른 모양의 중복확인 질의를 한 지점에 정확히 동기화하기 어려워 채택). 새 코드는 동시요청 중 정확히 하나만 성공하고 같은 아이디를 가진 행이 두 표를 합쳐도 1개뿐인데, 되돌린 옛 코드는 양쪽 다 200으로 성공해 같은 아이디가 두 표에 동시에 조용히 생기는(에러 없음) 가장 심각한 변형이 그대로 재현됨을 확인해 되돌림-증명. ④는 issue_partner_login이 일괄발급에서 자동채번(각 업체 고유 biz_no/id 기반)으로만 불려 서로 다른 두 업체가 같은 자동채번 아이디로 실제 충돌하는 상황을 자연스럽게 구성하기 어려워, 구조 확인(BEGIN IMMEDIATE 존재)과 정상 동작 회귀 확인까지만 하고 실경합 재현은 범위에서 뺀다고 테스트 자체에 정직하게 명시 — 억지로 아이디를 강제 주입하는 통로가 이 함수에 없어(코드상 자동채번 전용) 무리하게 만들면 실제로 안 쓰이는 경로를 테스트하게 되기 때문. 첫 실행 25/25 통과. app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ('test_scan_round495_fixes.py', '스캔 495라운드 회귀 — manage.py cmd_prune_personal()(개인정보 파기, 처리방침 제3조 이행)이 happy_calls(해피콜 기록)를 통째로 빠뜨리던 결함. feedback(응대내용)은 상담원이 통화 중 피해자가 밝힌 이름·주소· 불만 등을 그대로 받아 적는 자유텍스트라(app.py api_happy_call_add), 버킷③이 지우는 cases.victim_name/victim_phone과 같은 성격의 개인정보를 담을 수 있는데, 이 함수 298줄 어디에도 happy_calls가 등장하지 않았다(라운드332는 길이상한만 확인했을 뿐 보유기간·파기는 다른 축이라 혼동하면 안 됨) — 사건 쪽 이름·연락처를 파기한 뒤에도 해피콜 화면(GET /api/happy-calls, h.* 그대로 반환)에서는 그 원문이 영원히 남아 있었다. 정밀조사 Agent가 보험사/협력사 대칭성·캠페인· 엑셀일괄등록·repair_estimate.py 레시피 10종을 전수조사해 전부 클린 확정한 뒤(정직하게 보고, 억지 결함 없음) 발견. 이 세션이 함수 전체 298줄을 직접 Read로 재확인(happy_calls 언급 0건)한 뒤, 재현 스크립트를 독립 재실행해 같은 결과(cases.victim_name/phone은 NULL로 파기되는데 같은 사건의 happy_calls.feedback은 원문 그대로 생존)를 확인했다. 고침: ⑤(하자보수기록)와 같은 원칙으로 버킷⑥ 신설 — 행 자체는 안 지우고(score· method·created_at·partner_id는 partner_rating() 평점집계가 참조) feedback·called_by(자유텍스트)만 NULL로 파기. 컷오프는 ⑤의 준공+하자담보만료+3년이 아니라 ③과 같은 하자담보 만료 시점(_WEND)을 재사용 — 해피콜은 분쟁대응용 하자기록이 아니라 순수 만족도 확인이라 3년 연장 근거가 ⑤와 다르다는 이 코드베이스 자신의 기존 문서화된 판단기준을 그대로 따름. 회귀테스트(test_scan_round495_fixes.py+워커, 12개 검사) 신설 — 새 버킷은 순수삽입이라 통짜 제거로, total 합산식· 로그문구 두 곳은 각각 원본 문자열로 치환하는 방식으로 서로 겹치지 않게 독립적으로 되돌림. 8년 전 완료된 사건과 그 해피콜을 스크래치 DB에 심어 cmd_prune_personal()을 실제로 호출 — 새 코드는 해피콜 응대내용·상담원이 NULL로 파기되는데, 되돌린 옛 코드는 원문(이름 포함)이 그대로 남고 버킷③(사건 피해자정보)은 이번 라운드와 무관하게 여전히 정상 파기됨(회귀 없음)을 확인해 되돌림-증명 — 첫 실행 12/12 통과. manage.py는 app.py가 import하는 모듈이 아닌 독립 CLI라 이번 라운드는 서버 재기동·BUILD_HASH 로테이션이 불필요(라운드475·482와 같은 manage.py-class 예외). [618라운드] 이 되돌리기가 원래 실제 on-disk manage.py를 잠깐 덮어썼다가 subprocess로 재현 후 복원하는 옛 세대(round409~515대) 기법이었다 — 이제 되돌린 전체소스에서 cmd_prune_personal() 함수 경계만 AST로 뽑아 스크래치 임시파일(manage.py를 대신하는 파일이 아니라 단순 프로세스간 전달 수단)에 적고, 워커 서브프로세스 안에서 dict(vars(M)) 독립 사본 네임스페이스에 exec해 호출한다 — manage.py 자신은 이 과정 내내 디스크에서 전혀 안 열린다(단독 재실행 12/12 통과 재확인).'),
    ('test_scan_round496_fixes.py', '스캔 496라운드 회귀 — 사건 수동 수정("사건 수동 수정" activity_log) 감사로그에 피해자 "이름"만 원문 그대로 남던 결함. api_case_edit()의 피해자정보 수정 루프(app.py)에서 전화번호는 라운드249가 이미 POPBILL.mask_phone()으로 마스킹해 로그에 남기는데, 이름은 같은 루프인데도 마스킹 없이 이전값→새값 원문을 그대로 남겼다. activity_log는 cmd_prune_personal()의 파기 대상이 아니라서 (라운드495가 확정한 6개 파기 버킷 어디에도 activity_log는 없음), 사건 쪽 cases.victim_name이 하자담보 만료 후 지워져도 과거 수정 이력에 남은 원문 이름은 영구 보존된다. 처리방침 제3조(legal_docs.py)는 "피해자 성명·연락처"를 같은 줄로 묶어 같은 기준(하자담보 만료 후 파기)을 약속하므로, 이름도 형제(전화번호)와 같은 원칙으로 마스킹해야 한다. 고침: crypto_util.py에 형제 mask_account()와 같은 "화면 표시용 마스킹" 스타일로 mask_name()(첫 글자만 노출, 짧은값은 전량마스킹) 신설, app.py의 이름 분기를 CRYPTO.mask_name()으로 전화번호 분기와 동일한 형태로 교체. 회귀테스트(test_scan_round496_fixes.py+워커, 14개 검사) 신설 — crypto_util.py쪽은 순수삽입이라 통짜 제거로, app.py쪽은 한 블록 전체를 원본 문자열로 치환하는 방식으로 서로 겹치지 않게 독립적으로 되돌림. 실제 Flask test_client로 관리자 세션을 만들어 PATCH /api/cases/<id>를 직접 호출 — 새 코드는 activity_log에 마스킹된 이름(홍**)만 남는데, 되돌린 옛 코드는 수정 전후 이름(홍길동→홍길순)이 원문 그대로 노출된 채 남음을 확인해 되돌림-증명 — 첫 실행 14/14 통과. [618라운드] app.py 쪽 되돌리기가 원래 실제 on-disk app.py(+crypto_util.py)를 잠깐 덮어썼다가 subprocess로 재현 후 복원하는 옛 세대 기법이었다 — 이제 api_case_edit() 뷰만 AST로 함수 경계를 뽑아 되돌린 뒤 A.app.view_functions 딕셔너리 항목 치환(round604~610·614 패턴)으로 메모리에서 교체한다. crypto_util.py는 되돌린 뷰가 mask_name()을 아예 안 부르므로 원래도 실행-증명에는 무관함을 확인해 손대지 않기로 함(정적 소스검사만 유지, 파일 자체는 그대로) — 단독 재실행 15/15 통과. ⚠ 이 라운드는 activity_log "전체"의 나이 기반 파기 정책(라운드434가 이미 사용자결정 대기로 등록한 별개 축 — 5년 보관 의무 있는 협력업체 감사증적과 뒤섞여 일괄삭제 불가)을 건드리지 않는다 — 앞으로 새로 남는 로그에 원문을 안 남기는 좁은 범위의 고침이고, 이미 쌓인 과거 로그의 소급 마스킹은 범위 밖으로 정직하게 명시.'),
    ('test_scan_round497_fixes.py', '스캔 497라운드 회귀 — valid_biz_no()가 유니코드 전각숫자(예: １２３, U+FF10~19)를 걸러내지 못해 사업자등록번호 체크섬 검증과 DUP_BIZNO 중복확인을 동시에 우회하던 결함. 파이썬의 역슬래시D 정규식(역슬래시d의 여집합)는 유니코드 전각숫자도 숫자로 쳐서 지우지 않는다 — 체크섬은 그대로 통과하고, 저장값도 전각 그대로 남아 ASCII로 이미 등록된 같은 번호와 문자열이 달라 여러 호출지점(8곳)의 DUP_BIZNO 중복확인이 문자열 등치 비교라 우회된다. 형제(insurers.name, 라운드458)는 이미 NFKC 정규화로 이 종류의 유니코드 형태 우회를 막는데 이 함수만 못 물려받았다. 정밀조사 Agent가 DUP_BIZNO·자격증명· 개인정보파기·감사로그마스킹 등 기존 포화축을 전부 배제하고 새 각도로 발견, 이 세션이 실제 valid_biz_no() 함수와 clean_public_form()을 직접 Read하고 Python으로 전각 체크섬값이 실제로 True를 반환함을 재현해 확인. 이름(자유텍스트)과 달리 사업자번호는 순수 숫자코드라 정규화-후-수용 대신 ASCII 숫자(0-9)만 인정해 전각 입력을 자릿수 미달로 자연히 거부되게 고쳤다(정규식을 부정문자집합 [^0-9]로 교체, 함수 내부 단 한 줄, 8개 호출지점 전부가 공유하는 단일 지점이라 한 번에 다 고쳐짐). 회귀테스트(test_scan_round497_fixes.py+워커2개, 16개 검사) 신설 — 함수 내부 한 줄만 바뀐 단순 변경이라 원본 문자열로 치환하는 방식으로 되돌림. 실제 Flask test_client로 최고관리자 세션을 만들어 PATCH /api/partners/id를 직접 호출 — A상사(ASCII 사업자번호, 활성)가 이미 있는 상태에서 B상사를 전각 사업자번호로 활성화 시도 시, 새 코드는 400으로 거부해 활성 업체가 1곳 그대로인데, 되돌린 옛 코드는 실제로 승인이 통과되어 같은 실제 사업자번호를 가진 활성 업체가 2곳(문자열은 다르지만 같은 번호) 생기는 것을 확인해 되돌림-증명 — 첫 실행 16/16 통과. 경계값(순수ASCII·하이픈포함· 부분전각혼합·체크섬오류·빈문자열·None) 전부 회귀없음 단위확인. 기존 round79·248·417·429·493 테스트는 전부 순수 ASCII 값만 검증하고 valid_biz_no() 내부 구현을 리터럴로 검사하는 곳이 없음을 먼저 grep으로 확인한 뒤 수정 — 전체배터리로 회귀없음 재확인. [621라운드] 되돌림-증명이 원래 실제 on-disk app.py를 잠깐 덮어썼다가 서브프로세스(워커 2개)로 재현한 뒤 복원하는 옛 세대 기법이었다 — valid_biz_no()가 api_partner_update() 안에서 맨이름으로 불리므로(round619 gotcha), 되돌린 valid_biz_no를 먼저 공유 사본 네임스페이스(_ns = dict(vars(A)))에 exec한 뒤 되돌린 api_partner_update 본문을 같은 _ns에 exec해(기법4) 그 안의 맨이름 참조가 사본의 되돌린 버전을 찾게 하고, A.app.view_functions 딕셔너리 항목만 잠깐 치환한다 — 실제 A.valid_biz_no는 이 과정 내내 한 번도 안 바뀜. 단위확인도 더 이상 별도 워커 서브프로세스 없이 A.valid_biz_no()를 직접 호출 — 파일명·설명은 그대로, 내부 구현만 교체(단독 재실행 19/19 통과 재확인).'),
    ('test_scan_round498_fixes.py', '스캔 498라운드 회귀 — 라운드497이 valid_biz_no() 내부만 고치고 이를 호출하는 8곳이 저장·비교용 값을 만들 때 쓰는 별도의 정규화는 그대로 둔 결함. ASCII 10자리 유효 사업자번호에 유니코드 전각숫자 1개를 덧붙이면(총 11자), valid_biz_no() 안에서는 그 잉여문자가 지워져 10자리 체크섬이 통과하지만, 호출부 자신의 옛 정규화는 그 잉여문자를 못 지워 11자 그대로 저장·비교돼 DUP_BIZNO 중복확인이 다른 입력 모양으로 다시 우회됐다 — 이 입력은 라운드497 이전엔 길이불일치로 거부됐는데 497의 수정이 뜻하지 않게 새로 통과시켰다. 정밀조사 Agent가 라운드497 직후 신선한 각도로 재조사하다 발견, 이 세션이 실제 정규식 로직으로 재현해 확인(잉여문자가 호출부에서 안 지워짐, valid_biz_no는 그래도 True 반환함을 직접 실행 검증). 고침: 호출부 8곳(app.py 여러 지점)의 정규식을 전부 valid_biz_no() 내부와 같은 [^0-9]로 통일 — 이제 판정과 저장값이 항상 같은 기준을 쓴다. 무관한 형제(계좌번호 정규화, 이미 [^0-9] 사용 중이던 기존 코드)는 건드리지 않았음을 직접 확인. 회귀테스트(test_scan_round498_fixes.py+워커, 18개 검사) 신설 — 라운드498 자신의 기여(호출부 8곳)만 좁게 되돌리고 라운드497의 기여(valid_biz_no 내부)는 그대로 두는 방식으로 정확히 이 라운드의 몫만 검증. 실제 Flask test_client로 최고관리자 세션을 만들어 PATCH /api/partners/id를 잉여 전각숫자 1개 섞인 값으로 호출 — 새 코드는 정규화 후 중복으로 잡혀 409 DUP_BIZNO로 거부되는데, 되돌린 옛 코드(라운드497까지만)는 실제로 승인이 통과되어 11자짜리 오염된 값이 저장되고 같은 실제 사업자번호를 가진 활성 업체가 2곳 생기는 것을 확인해 되돌림-증명 — 첫 실행 18/18 통과. 관련 기존 테스트(round79·248·417·429·493·497)가 이 8개 호출부의 정규식을 리터럴로 검사하지 않음을 grep으로 사전 확인해 충돌 가능성을 배제 — 전체배터리로 최종 재확인.'),
    ('test_scan_round499_fixes.py', '스캔 499라운드 회귀 — 자동 출동수배(dispatch.py candidates(), open_dispatch()가 직접 호출해 SMS/알림톡 발송 대상을 정함)와 수동 근처업체 검색(app.py api_case_nearby())의 공종(category/major) LIKE 비교가 가운뎃점 표기 흔들림을 정규화하지 않던 결함. 형제(관리자 검색바의 _kw_like_clause, 라운드186)는 이미 아래아(U+318D)·반각(U+FF65) 변형을 정본 가운뎃점(U+00B7)으로 정규화해 검색어·컬럼 양쪽을 맞추는데, 이 두 함수는 그 정규화를 안 거쳤다. 정부 공식 업종 표기(아래아)를 쓰는 협력사가 실제로 10곳(id 305~314, 라운드186 실측) 있어 — 그 업체의 major/category가 사건 쪽 정본 표기와 문자열이 달라지면, api_case_nearby()는 trade=1 필터에서 하드 배제(지역-only 폴백이 없음)되고, dispatch.py candidates()는 1·3순위(공종이 걸리는 순위)에서 빠지고 2순위(같은 지역, 공종 무관)로 밀려나 트레이드 우선순위를 잃는다(그 2순위조차 1순위가 이미 정원을 채우면 안 뜬다). 정밀조사 Agent가 발견, 이 세션이 실제 소스를 직접 Read로 재확인(양쪽 다 컬럼측 REPLACE도 검색어측 정규화도 없음)하고 dispatch.py 자신의 _case_trades()·_like_escape() 독스트링이 이미 기록해 둔 과거 이력 (app.py와 dispatch.py가 같은 로직을 각자 유지하다 한쪽만 고쳐져 재발한 사례가 여러 차례 있었음, dispatch.py는 순환임포트 때문에 app.py를 못 불러 로컬 사본을 둠)을 근거로 신뢰도를 검증한 뒤 수정. 고침: dispatch.py에 형제 _like_escape()와 같은 스타일(순환임포트 경고 주석 포함)로 _norm_dot() 로컬 사본 신설, candidates()의 트레이드 조건을 _kw_like_clause()와 같은 SQL 형태(컬럼은 REPLACE로, 검색값은 _norm_dot으로 정규화)로 교체. app.py의 api_case_nearby()도 같은 형태로 교체. 회귀테스트(test_scan_round499_fixes.py+워커, 11개 검사) 신설 — dispatch.py쪽 새 함수는 순수삽입이라 통짜 제거로, 두 파일의 조건절은 각각 원본 문자열로 치환하는 방식으로 서로 겹치지 않게 독립적으로 되돌림. 실제 사건·협력사를 스크래치 DB에 심어(협력사 major는 아래아 표기) dispatch.candidates()와 실제 Flask test_client로 api_case_nearby 를 직접 호출 — 새 코드는 그 협력사가 dispatch 1순위(지역+공종 일치)에 뜨고 근처업체 trade=1 필터에도 뜨는데, 되돌린 옛 코드는 dispatch 1순위에서 빠지고 근처업체 필터에서는 완전히 빠짐을 확인해 되돌림-증명 — 첫 실행 11/11 통과. 오늘 실제 운영 DB(읽기전용 조회)의 정부공식 표기 10곳은 major가 이미 정본 표기라 이 정규화 누락이 지금 당장 트리거되진 않지만, 같은 10곳의 category 필드는 이미 아래아 습관을 보여 향후 입력이나 다른 복합공종에서 재발 가능한 구조적 결함임을 정직하게 명시(억지 결함 아님, 잠재적 위험 축소 목적). [618라운드] 되돌리기가 원래 실제 on-disk dispatch.py+app.py를 잠깐 덮어썼다가 subprocess로 재현 후 복원하는 옛 세대 기법이었다 — 이제 candidates()는 AST로 뽑은 함수 경계를 되돌려 dict(vars(dispatch)) 독립 사본에 exec해 직접 호출하고, api_case_nearby()는 A.app.view_functions 딕셔너리 항목 치환으로 되돌린다 — 두 파일 모두 이 과정 내내 디스크에는 전혀 안 쓴다(단독 재실행 13/13 통과 재확인).'),
    ('test_scan_round500_fixes.py', '스캔 500라운드 회귀 — 정산(settlements) 처리 6개 함수(settleVoid· settleUndo·settlePaid·settlePaidBulk·doSettleReview·settleTransfer, static/admin.js)의 catch 분기가 형제(caseDetail 액션버튼, 라운드481· 486이 세운 "catch도 성공 분기와 같이 정리한다" 원칙)를 못 물려받아 toast만 하고 화면을 방치하던 결함. 관리자 A·B가 같은 정산 목록을 열어둔 상태에서 B가 먼저 처리(취소·이체 등)하면, 서버 여러 지점 (app.py, "취소된 정산 건입니다"류 409 응답 다수가 code 없이 옴)이 판정 근거를 안 줘 A의 화면은 GATE 판정도 못 하고 toast만 뜬 채 이미 무효화된 행을 계속 처리 가능한 것으로 보여준다. 정밀조사 Agent가 라운드481·486이 이미 정리한 두 클러스터(1차합의·배차, 사건상세)와 달리 아직 손대지 않은 세 번째 클러스터(정산 — 돈이 실제로 움직이는 화면)에서 같은 결함을 발견, 이 세션이 admin.js 원문을 직접 Read로 재확인(6개 함수 전부 catch가 toast만 함)하고 app.py의 5개 지점에서 "취소된 정산 건입니다" 409가 code 없이 나가는 것도 직접 확인. 고침: 각 함수 catch에 **그 함수 자신의 성공 분기가 이미 하는 정리**를 그대로 옮김(VIEWS.settle()·refreshBadges(), doSettleReview만 모달 기반 흐름이라 closeModal()도 포함 — 새 정책 발명이 아니라 라운드481· 486 원칙의 기계적 확장, 함수마다 자기 자신의 기존 정리 순서를 그대로 따름). 회귀테스트(test_scan_round500_fixes.py, 17개 검사) 신설 — 중괄호 짝을 실제로 세어 함수 경계를 찾는 방식으로 6개 함수 본문을 각각 추출(초안에서 "다음 함수 선언 전까지"로 찾다가 화살표함수 등 다른 선언 스타일 때문에 훨씬 뒤의 무관한 함수까지 통째로 삼키는 걸 직접 실측해 브레이스 카운팅 방식으로 교체). 대표 두 형태(단순 catch인 settleVoid·GATE 재시도인 settleTransfer)는 실제 Node.js로 api·toast· closeModal·refreshBadges·VIEWS.settle을 목으로 만들어 진짜 실행 — 새 코드는 서버 오류 시에도 목록이 새로고침되는데, 되돌린 옛 코드는 toast만 뜨고 목록이 방치됨을 확인해 되돌림-증명 — 첫 실행 15/17에서 테스트 자신의 문자열 비교 실수(마침표 누락) 하나를 고쳐 17/17 통과. 나머지 4개 함수는 소스리터럴로 catch 내용을 확인.'),
    ('test_scan_round501_fixes.py', '스캔 501라운드 회귀 — 라운드205가 "세 형제 액션 함수"로 함께 묶었던 defectAct()(하자관리)·dispatchSweep()(출동수배 기한점검)·leadAct() (도입 문의)의 catch 분기가 형제(settleVoid 등, 라운드481·486·500이 세운 "catch도 성공 분기와 같이 정리한다" 원칙)를 못 물려받아 toast만 하고 화면(모달·목록)을 방치하던 결함 — 네 번째 클러스터. 관리자 A·B가 같은 하자 상세 모달을 동시에 열어둔 상태에서 B가 먼저 상태를 바꾸면, 서버(app.py DEFECT_BAD_TRANSITION 409)가 A의 다음 액션을 막지만 A의 모달은 옛 상태로 계속 열려 있는다. 라운드205는 이 세 함수에 try/catch 자체만 추가했을 뿐(unhandled rejection 방지)이고, catch가 성공 분기와 같은 정리를 하는 481+ 원칙은 그 당시 아직 존재하지 않아 못 물려받았다. 정밀조사 Agent가 481·486·500이 이미 처리한 세 클러스터와 다른 네 번째 화면군에서 발견, 이 세션이 admin.js 원문과 app.py의 DEFECT_BAD_TRANSITION 409를 직접 Read/grep으로 재확인. 고침: 세 함수 각각 그 함수 자신의 성공 분기가 이미 하는 정리를 catch에도 그대로 옮김 — defectAct·leadAct는 모달 기반 흐름이라 closeModal()도 포함, dispatchSweep은 목록화면 버튼이라 성공 분기도 애초에 closeModal이 없어 그대로 미러링. 회귀테스트(test_scan_round501_fixes.py, 16개 검사) 신설 — 라운드500이 확립한 중괄호 짝세기 함수경계 추출을 재사용. 세 함수 전부 실제 Node.js로 api·toast·closeModal·refreshBadges· VIEWS.x를 목으로 만들어 진짜 실행해 되돌림-증명(새 코드는 서버 오류 시에도 화면이 정리되는데 되돌린 옛 코드는 방치됨을 확인) — 첫 실행부터 16/16 통과. 등록 전 grep으로 관련 기존 테스트 6개 파일을 확인하다 라운드205 자신의 회귀테스트가 정확히 이번 라운드가 뒤집는 옛 기대값 ("실패하면 closeModal 0회·화면전환 없음")을 리터럴로 검증하고 있음을 발견 — 라운드496류의 교차라운드 테스트노후화, 세 함수 모두 실패 시 이제 성공 분기와 같은 방식으로 화면이 정리된다는 새 기대값으로 그 검사 한 곳만 좁게 갱신(dispatchSweep은 성공 분기도 애초에 closeModal 을 안 해 그 함수만 0을 유지하는 차이까지 반영), round205 재실행 16/16 통과 확인 후 전체배터리로 최종 재확인.'),
    ('test_scan_round502_fixes.py', '스캔 502라운드 회귀 — VIEWS.dispatch(현장 출동 수배) 화면의 액션버튼 4형제 중 dispatchSweep(라운드337이 이미 등급게이트)만 빼고 dpOpen (수배 개시)·dpRetry(재수배)·dpAssignForm(직접 배정) 3곳이 등급 무관하게 그려지던 결함. 서버(app.py) 확인 — /api/cases/id/dispatch (dpOpen·dpRetry 공용)·/api/cases/id/dispatch/assign(dpAssign) 둘 다 require_role(중간관리자)로, dispatchSweep의 /api/admin/dispatch-sweep 와 같은 등급을 요구한다. 정밀조사 Agent가 발견, 이 세션이 admin.js 원문과 app.py의 두 라우트 데코레이터를 직접 Read로 재확인. 라운드337 자신의 문서(그 라운드 자신의 회귀테스트 설명): "조회(목록) API는 require_admin(등급무관)이라 화면 자체는 계속 보이는 게 맞다 — 처리 버튼만 형제(coActions, 라운드252)처럼 자격 없으면 조용히 안내문/숨김 으로 바뀌어야 한다"는 이미 확정된 설계의도를 이 세션이 직접 재확인 — 그런데 337이 실제로 나열한 대상은 "기한 점검 실행" 버튼 하나뿐이고 같은 화면의 나머지 세 형제는 언급조차 없었다(run_all_tests.py 전수 검색: dpOpen·dpRetry 언급 0건). 고침: 두 곳(각각 dpOpen 단독 셀, dpRetry+dpAssignForm 공유 셀)을 형제 settleAction()(정산목록, 테이블행 액션 셀)과 같은 스타일로 게이트 — myRank()>=2가 아니면 버튼 대신 이 화면 자신이 이미 쓰던 hint 클래스로 "중간관리자 이상만 처리할 수 있습니다" 안내문을 보여준다(dispatchSweep은 여러 버튼 중 하나인 툴바라 빈 문자열로 숨겼지만, 이 둘은 테이블 행의 유일한 액션 칸이라 settleAction류의 안내문 대체가 더 맞는 형태). 회귀테스트 (test_scan_round502_fixes.py, 13개 검사) 신설 — 라운드502 자신이 작성한 주석 리터럴을 시작 마커로, 그 뒤 첫 </td>를 끝 마커로 잡아 두 셀을 독립 추출(중첩 백틱을 포함한 템플릿 리터럴이라 이스케이프를 섣불리 넣었다가 구문오류를 직접 겪어 제거 — 중첩 백틱은 이미 유효한 문법이라 손대면 안 됨을 실측). 실제 Node.js로 세 등급(1·2·3) 전부 렌더링해 하위관리자만 안내문으로 바뀌고 중간관리자 이상은 버튼이 그대로 뜨는지 확인, 되돌린 옛 코드는 하위관리자에게도 세 버튼이 전부 뜸을 확인해 되돌림-증명 — 첫 실행 문법오류 1회 자체 수정 후 13/13 통과. 등록 전 grep으로 need_dispatch·failed_cases·dpOpen· dpRetry를 참조하는 기존 테스트 4개 파일을 확인했으나 전부 서버측 데이터(데모격리·취소건 필터링)만 검사해 이번 JS 렌더링 변경과 무관함을 확인 — 전체배터리로 최종 재확인.'),
    ('test_scan_round503_fixes.py', '스캔 503라운드 회귀 — 변경견적(change_orders) 처리 8개 함수 (coWithdraw·coAddAuction·coOffer·coFullReauction·coAwardFull(2곳)· coFailFull(2곳)·ACT.coWithdrawReq·ACT.coFailAdd, static/admin.js)의 catch 분기가 형제(caseCancelAward 등, 라운드481·486·500·501이 세운 "catch도 성공 분기와 같이 정리한다" 원칙)를 못 물려받아 toast만 하고 화면(목록·모달)을 방치하던 결함 — 다섯 번째 클러스터. ACT.coFailAdd는 이미 고쳐진 형제 ACT.caseCancelAward 바로 다음 줄에 있으면서도 못 물려받았던 자리였다. 정밀조사 Agent가 발견, 이 세션이 admin.js 원문 8곳을 전부 직접 Read로 재확인(각 함수의 성공 분기가 이미 하는 정리 — VIEWS.changeorders() 또는 loadView (changeorders), coAwardFull·coFailFull은 추가로 closeModal() — 를 catch가 안 하고 있음을 확인). 고침: 8곳 각각 그 함수 자신의 성공 분기가 이미 하는 정리를 catch에도 그대로 옮김 — coAwardFull· coFailFull은 NOT_CLOSED 재시도 catch와 알수없는-오류 종단 catch 둘 다 고치되, NOT_LOWEST·INSURER_ACK_REQUIRED(사용자가 입력 중이던 칸에 포커스만 옮기는 의도된 동작)는 일부러 손대지 않음. 회귀테스트 (test_scan_round503_fixes.py, 25개 검사) 신설 — 라운드500이 확립한 중괄호 짝세기로 8개 함수 본문 전부를 독립 추출해 소스리터럴로 확인, 대표 세 형태(단순 standalone: coWithdraw, ACT객체 메서드: coFailAdd, 다중분기 복합형: coFailFull)는 실제 Node.js로 api· toast·closeModal·VIEWS·loadView·askOverride를 목으로 만들어 진짜 실행해 되돌림-증명(새 코드는 서버 오류 시에도 화면이 정리되는데 되돌린 옛 코드는 방치됨) — 첫 실행에서 자체 문법확인 실수(빠진 mock 함수·정확한 줄바꿈 불일치) 2건을 직접 발견·수정 후 25/25 통과. 등록 전 grep으로 관련 기존 테스트 4개 파일(round12·18·19· 252)을 확인 — round12는 coFailFull을 고정폭 1400자 창으로 검사하는 위험한 패턴이었으나(라운드499류 함정 가능성) 실제로 그 창 안의 내용(NOT_CLOSED 분기)은 이번 라운드가 그보다 뒤쪽만 건드려 영향 없음을 개별 실행(39/39)으로 직접 확인, round252(27/27)·18(46/46)· 19(18/18) 전부 무관함을 확인해 사전에 충돌 배제 — 전체배터리로 최종 재확인.'),
    ('test_scan_round504_fixes.py', '스캔 504라운드 회귀 — 입점신청 처리(온보딩) 화면의 두 관련 결함. (A, 서버) api_application_update()의 반려/서류검토 분기(app.py)가 승인 분기(바로 위, WHERE status<>승인)와 달리 현재 상태를 전혀 안 보고 무조건 덮어썼다 — 이미 승인되어 협력업체가 생성되고 알림톡까지 나간 신청서를, 동시에 열려 있던 다른 관리자의 구형 모달이 반려로 되돌리면 partner_applications.status만 조용히(200 OK) 뒤집혀 이미 만들어진 활성 업체·이미 발송된 승인 알림과 모순되는 상태가 된다. (B, 화면) appAct()(admin.js)의 catch 분기가 형제(leadAct 등, 라운드 481·486·500·501·503이 세운 catch도 성공 분기와 같이 정리한다 원칙)를 못 물려받았다 — 그것도 이 함수 자신이 그 형제들의 원조다(라운드89가 여기 먼저 try/catch를 붙였고, 라운드205가 leadAct·defectAct· dispatchSweep에 형제(appAct)처럼이라며 옮겨 붙였는데, 정작 원조 자신은 나중에 이 정리 원칙을 못 물려받았다) — 여섯 번째 클러스터. 정밀조사 Agent가 발견, 이 세션이 app.py의 승인 분기(WHERE status<>승인)와 반려 분기(가드 없음)를 직접 Read로 대조하고 실제 서브프로세스 실행으로 상태역전을 재현해 확인. 고침: (A) 반려/서류검토 분기에 승인 분기와 같은 형태의 WHERE status<>승인 가드 + 409 응답 추가(승인은 되돌릴 수 있는 동작이 아니므로 — 업체 생성·알림 발송을 취소하지 않음 — 이 화면으로 상태를 못 바꾸게 막는 것이 유일하게 안전한 선택, 기존 워크플로 중 정당하게 막히는 경우는 없음을 확인). (B) appAct() catch에 형제와 같은 정리(closeModal·refreshBadges·VIEWS.apps) 추가. 회귀테스트(test_scan_round504_fixes.py+워커, 15개 검사) 신설 — 서버 쪽은 실제 Flask test_client로 승인→반려 순서로 두 번 호출해, 새 코드는 두 번째 요청이 409로 막히고 신청서 상태가 승인 그대로 유지되는데, 되돌린 옛 코드는 실제로 상태가 반려로 뒤집히면서도 이미 만들어진 활성 업체는 그대로 남는 모순 상태가 실측으로 재현됨을 확인. 화면 쪽은 라운드500이 확립한 중괄호짝세기로 appAct() 본문을 추출해 실제 Node.js로 실행 — 새 코드는 서버 오류 시에도 모달을 닫고 목록을 새로고침하는데, 되돌린 옛 코드는 방치됨을 확인해 되돌림-증명 — 첫 실행 12/13(Node harness에 $ 셀렉터 mock 누락 1건)에서 발견·수정 후 15/15 통과. 등록 전 grep으로 api_application_update·appAct를 참조하는 기존 테스트 14개 파일을 확인했으나(대부분 DUP_BIZNO·승인 분기 자체를 다루는 라운드248·429·466·493 등) 이번에 고친 반려/서류검토 분기의 리터럴 텍스트나 승인후반려 시나리오를 검사하는 곳은 없음을 확인해 사전에 충돌 가능성을 낮췄고, 전체배터리로 최종 확인.'),
    ('test_scan_round505_fixes.py', '스캔 505라운드 회귀 — api_partner_delete()(협력사 퇴출, DELETE /api/partners/id)가 형제 api_partner_update()(PATCH, 같은 partners.status 컬럼, 라운드493이 BEGIN IMMEDIATE 이식)와 달리 잠금이 전혀 없던 결함. 관리자 두 명(또는 재시도)이 같은 업체에게 거의 동시에 퇴출을 실행하면 둘 다 200을 받아, 협력사에게 등록이 퇴출로 변경되었다는 알림톡이 두 번 나가고 감사로그도 중복됐다 (최종 status 자체는 퇴출 하나뿐이라 데이터 훼손은 아니지만 알림 비용·감사로그 중복이 실제로 발생). 정밀조사 Agent가 발견 — 라운드 504의 형제 분기 방어 비대칭을 함수 내부 분기가 아니라 같은 자원 (partners.status)을 쓰는 두 형제 엔드포인트(PATCH/DELETE) 사이로 확장한 사례. 이 세션이 두 함수를 app.py 원문으로 직접 대조하고, 조사 에이전트가 만든 재현 스크립트를 독립 재실행해 실제로 두 요청 모두 200 성공·알림 2건·감사로그 2건이 나옴을 직접 확인. 고침: BEGIN IMMEDIATE 추가 + 기존 조기반환 3곳에 conn.rollback() 추가 (형제와 같은 패턴) — 그런데 잠금만으론 부족함을 확인: 잠금을 먼저 넣고 재현했더니 두 번째 요청이 락을 얻은 뒤에도 여전히 다시 UPDATE·통지를 실행해 중복이 그대로 남았다 — "이미 퇴출된 업체입니다" 409 재확인을 별도로 추가해야 완전히 막힘을 실측으로 확인(settleVoid류의 이미-종결상태 재확인과 같은 원칙). _partner_demote_gate()가 이미 형제 api_partner_update()의 BEGIN IMMEDIATE 블록 안에서 안전하게 쓰이고 있음을 grep으로 확인한 뒤 중첩 안전성을 재검증. 회귀테스트(test_scan_round505_fixes.py+워커, 11개 검사) 신설 — 함수 전체를 통째로 캡처하는 방식(라운드490 이후 표준)으로 원본과 정확히 대조, 실제 threading.Barrier로 두 스레드가 UPDATE 실행 시점에 정확히 동시 도달하도록 강제해 진짜 경합을 재현 — 새 코드는 동시 요청 중 정확히 하나만 성공하고 알림·감사로그 각각 1건씩만 남는데, 되돌린 옛 코드는 실제로 둘 다 200 성공하며 알림·감사로그가 각각 2건씩 생김을 확인해 되돌림-증명 — 첫 실행 11/11 통과. 등록 전 grep으로 api_partner_delete를 참조하는 기존 테스트(라운드331 사유길이제한·라운드339 등급데코 레이터 확인)를 개별 실행해 무관함을 확인 — 라운드331은 활성 업체에 DELETE를 정확히 1번만 호출해 새 가드(이미 퇴출 시에만 작동)와 절대 겹치지 않음을 직접 확인. 전체배터리로 최종 재확인. [621라운드] 되돌림-증명이 원래 함수 전체를 실제 on-disk app.py에 통째로 써넣고 별도 워커 서브프로세스(threading.Barrier)로 재현한 뒤 복원하는 옛 세대 기법이었다 — 이제 ORIGINAL_FUNC 텍스트(데코레이터 제거)를 exec로 독립 사본 네임스페이스에 재구성해 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다(round488·507 패턴). 동시성 재현(threading.Barrier+_Probe) 로직은 옛 워커의 것을 그대로 옮겨 같은 프로세스 안에서 호출 — 워커 파일은 삭제(더 이상 안 씀) — 파일명·설명은 그대로, 내부 구현만 교체(단독 재실행 13/13 통과 재확인).'),
    ('test_scan_round506_fixes.py', '스캔 506라운드 회귀 — api_insurer_update()(보험사 정보·상태 변경, PATCH /api/insurers/id)가 형제 api_partner_update()(같은 클래스의 상태확인-수정 패턴, 라운드493이 BEGIN IMMEDIATE 이식)와 달리 트랜잭션 잠금이 전혀 없던 결함. 정밀조사 Agent가 라운드504·505의 형제 분기/엔드포인트 방어 비대칭 축을 다른 리소스로 확장하다 발견 — 관리자 두 명(또는 재시도)이 같은 보험사를 거의 동시에 중지로 바꾸면 둘 다 200을 받아 보험사상태변경 알림과 상태변경 감사로그가 각각 중복됨을 threading.Barrier로 실측 확인. 고침: 라운드493과 달리 이 함수는 매 요청마다 현재값과 대조해 changed를 계산하는 구조라, 읽기(SELECT)를 BEGIN IMMEDIATE 뒤로 옮기는 것만으로 충분했다 — 두 번째 요청은 잠금 안에서 이미 바뀐 status를 보고 changed=False로 자연히 멈춰 별도의 이미 그 상태입니다 재확인 코드를 새로 얹을 필요가 없었다(라운드505의 DELETE는 조건 없이 무조건 UPDATE라서 그 재확인이 따로 필요했던 것과 대비). 단, 필드 루프(org_type/manager/dept/phone/email/contract_status/status)가 값이 실제로 바뀌었는지와 무관하게 요청에 그 키가 있으면 무조건 sets에 넣는 동작은 형제 api_partner_update와 공통인 별개 사안이라 이번 라운드 범위 밖으로 남김(그래서 진 쪽 요청도 UPDATE 자체는 한 번 더 실행되고 정보 수정이라는 범용 감사로그 한 줄은 남지만, 알림 중복과 상태변경 감사로그 중복은 완전히 사라짐). 회귀테스트(test_scan_round506_fixes.py+워커, 12개 검사) 신설 — 함수 전체를 통째로 캡처하는 방식으로 원본과 정확히 대조, 실제 threading.Barrier로 두 스레드가 SELECT 실행 시점에 동시 도달을 시도하도록 강제(잠금이 걸리면 진 쪽은 자기 BEGIN IMMEDIATE에서 먼저 막혀 이 지점에 함께 못 옴을 디버그 트레이스로 직접 확인)해 진짜 경합을 재현 — 새 코드는 두 요청 다 200을 받지만 알림 1건·상태변경 감사로그 1건만 남는데, 되돌린 옛 코드는 실제로 알림 2건·상태변경 감사로그 2건이 생김을 확인해 되돌림-증명 — 첫 실행 12/12 통과. [621라운드] 되돌림-증명이 원래 함수 본문 일부(CUR_FUNC/ORIGINAL_FUNC, 차이 나는 구간만)를 실제 on-disk app.py에 문자열 치환해 써넣고 별도 워커 서브프로세스(threading.Barrier)로 재현한 뒤 복원하는 옛 세대 기법이었다 — CUR_FUNC/ORIGINAL_FUNC는 함수 전체가 아니라 일부만 캡처한 것이라, round499가 정착시킨 ast 기반 전체 함수 추출로 CURRENT_FULL_FUNC를 뽑은 뒤 그 안에서 CUR_FUNC→ORIGINAL_FUNC 부분 치환만 적용해 완전한 REVERTED_FULL_FUNC를 만들고, 이를 exec로 독립 사본 네임스페이스에 재구성해 A.app.view_functions 딕셔너리 항목만 잠깐 치환한다. 동시성 재현(threading.Barrier+_Probe) 로직은 옛 워커의 것을 그대로 옮김 — 워커 파일은 삭제(더 이상 안 씀) — 파일명·설명은 그대로, 내부 구현만 교체(단독 재실행 15/15 통과 재확인).'),
    ('test_scan_round507_fixes.py', '스캔 507라운드 회귀 — api_campaign_cancel()(마케팅 캠페인 취소, POST /api/campaigns/id/cancel)가 형제 api_campaign_create()(라운드348이 BEGIN IMMEDIATE 이식)와 달리 트랜잭션 잠금이 전혀 없던 결함. 상태 확인도 "발송완료"만 볼 뿐 "이미 취소됨"은 보지 않아, 관리자 두 명(또는 더블클릭·재시도)이 같은 캠페인을 거의 동시에(또는 순서대로 두 번) 취소하면 매번 UPDATE·감사로그가 다시 실행돼 "마케팅 캠페인 취소" 감사로그가 중복 적재됐다(최종 status 자체는 "취소" 하나뿐이라 데이터 훼손은 아니지만 감사로그 중복이 실제로 발생 — 라운드505의 api_partner_delete와 같은 성격). 캠페인·발송함 축은 라운드251(등급게이트·생성 중복클릭 방어)·라운드333(filter_json 길이제한)·라운드348(생성쪽 BEGIN IMMEDIATE 이식)이 이미 여러 번 손댔는데, 셋 다 생성(create) 경로만 잠그고 취소(cancel) 경로는 한 번도 검증한 적이 없었다는 사각지대를 이 세션이 grep(campaign 관련 전체 라우트·기존 테스트 전수)으로 직접 확인 — 기존 테스트는 전부 등급게이트만 보고 동시성은 다루지 않았다. 이 세션이 app.py 원문을 직접 Read로 대조해(api_campaign_cancel 에는 BEGIN IMMEDIATE가 없고 형제 api_campaign_create 에는 라운드348이 이미 이식해 둔 것을 확인) 발견하고, threading.Barrier로 두 스레드를 유일한 읽기지점(SELECT title, status FROM campaigns WHERE id=?)에 강제 동시 도달시키는 재현 스크립트를 직접 작성해 실행 — 수정 전 코드는 실제로 두 요청 모두 200 성공, 감사로그 2건이 남음을 확인. 고침: 형제 api_campaign_create와 같은 BEGIN IMMEDIATE 추가 + 기존 조기반환 2곳에 conn.rollback() 추가, 그리고 라운드505가 확립한 원칙대로(조건 없이 무조건 UPDATE하는 구조는 잠금만으로 부족) "이미 취소된 캠페인입니다" 409 재확인을 새로 추가 — campaign_targets 쪽은 원래부터 자기 WHERE status="대기" 조건을 갖고 있어 중복 실행에도 안전했으므로 손대지 않았다. 회귀테스트(test_scan_round507_fixes.py+워커, 14개 검사) 신설 — 함수 전체를 통째로 캡처하는 방식(라운드490 이후 표준)으로 원본과 정확히 대조, 실제 threading.Barrier로 두 스레드가 SELECT 실행 시점에 동시 도달을 시도하도록 강제해 진짜 경합을 재현 — 새 코드는 동시 취소 요청 중 정확히 하나만 성공(200)하고 나머지는 "이미 취소됨" 409로 막혀 감사로그가 1건만 남는데, 되돌린 옛 코드는 둘 다 200으로 성공해 감사로그가 2건 생기는 옛 동작이 그대로 재현됨을 실측해 되돌림-증명 — 첫 실행 14/14 통과. 등록 전 grep으로 api_campaign_cancel을 참조하는 기존 테스트(라운드251 — 등급게이트만 검사)를 개별 실행해 무관함을 확인(14/14 통과, 회귀 없음), 인접 테스트(라운드164·165·333·348)도 개별 실행해 전부 통과 확인(각 12/12·7/7·13/13·10/10). app.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인).'),
    ("test_feature_ops_today.py", "기능 회귀(오늘 할 일)"),
    ("test_scan_round508_fixes.py", "스캔 508라운드 회귀 — 개인정보 처리방침 제6조(개인정보 처리의 위탁) 표에 AI 사진분석 위탁처(구글 Gemini API)가 통째로 빠져 있던 결함[컴플라이언스]. photo_ai.py(BOKGUON_GEMINI_KEY 설정 시 실사용, classify·analyze_damage)는 협력사·보험사가 올린 시공·손상 사진 원본을 구글 Gemini API 로 그대로 전송해 자동분류·파손 정도 참고 분석을 시킨다 — round224·229·284·298·328 이 이 기능 자체(임계값·EXIF·8MB 상한·정확도 통계)를 여러 차례 다뤘지만, 이 위탁을 처리방침에 공개해야 하는가는 그중 어디서도 다룬 적이 없었다. 이 세션이 legal_docs.py 제6조 표(호스팅·PG·알림톡 세 곳만 나열, INFO_FIELDS 에도 AI 사진분석 항목 없음)를 직접 Read로 확인하고 photo_ai.py 의 실제 Gemini API 호출부(generativelanguage.googleapis.com, base64 인코딩된 사진 원본 전송)를 직접 확인해 발견 — 개인정보 보호법 제26조가 요구하는 처리위탁 공개 대상인데 문서 어디에도 없었다. 이 파일은 이미 같은 패턴(IP제한 유무·하자담보책임기간·보안설정 수치 3종)을 세 번 고친 전례(round238·289·317)가 있는데 이 자리만 그 교훈을 못 받았다. 반대로 이 저장소의 실제 .env 에는 BOKGUON_GEMINI_KEY 가 비어 있어(.env.example 기본값과 동일) 지금 당장 사진이 실제로 나가지는 않는다 — 안 하는 일을 한다고 적으면 그것도 거짓 고지이므로(round238의 IP제한과 정반대 방향의 같은 원칙), 켜져 있을 때만(photo_ai.is_enabled()) 표에 한 줄이 붙도록 조건부로 고쳤다. 고침: legal_docs.py privacy_body() 에 ai_photo_enabled=False 인자를 추가(기본값 False 는 지금까지 이 표에 그 줄이 아예 없던 것과 동일해 인자를 안 넘기는 호출부는 회귀 없음, round317 의 세 인자와 나란히 동작), 켜지면 알림톡 행 바로 다음에 Google LLC (Gemini API) 행을 삽입. 호출부 두 곳(app.py legal_page() 는 PHOTO.is_enabled() 를, build_pages.py 의 정적 빌드는 BOKGUON_GEMINI_KEY 환경변수를 직접 조회해) 모두 photo_ai.py 자신이 이미 쓰는 판정을 그대로 재사용한다(새 판정을 따로 만들지 않는다). 회귀테스트(test_scan_round508_fixes.py, 17개 검사) 신설 — legal_docs.privacy_body() 단위 검증(기본값 동일성·태그 짝맞음·알림톡 행 자신의 닫는 태그 보존·round317 인자와의 비간섭), 소스 검증(호출부 두 곳의 실제 연동), 실제 Flask test_client 로 /legal/privacy 를 GEMINI_KEY 있음/없음 두 상태로 직접 호출, 실제 build_pages.build() 를 임시 디렉터리에 두 번 실행해(round108 이 확립한 기법 그대로) 정적 산출물까지 확인. 세 파일(legal_docs.py·app.py·build_pages.py) 전체를 되돌려 결함 재현 — 되돌린 코드는 17개 중 10개가 정확히 예상대로(신설된 조건부 공개 관련 항목만) 실패하고 나머지 7개(회귀 없음을 확인하는 항목)는 그대로 통과함을 실측 확인 후 복원. 관련 기존 테스트(round108·round238·round289·round294·round306·round317·round193·test_compliance.py·test_feature_work_coverage.py) 전부 개별 재실행해 회귀 없음 확인 — round306 의 체크인된 docs/ 와 재빌드 완전일치 불변식도 그대로 통과(현재 .env 값이 기본값과 동일해 재생성해도 docs/ 가 바이트 단위로 안 바뀜). app.py·legal_docs.py 변경이라 WMI로 서버 재기동 필요, BUILD_HASH 로테이션 예상(build_pages.py 자신은 app.py 미import)."),
    ("test_scan_round509_fixes.py", "스캔 509라운드 회귀 — partners.website(홈페이지) 저장형 XSS, javascript 스킴이 esc() 를 그대로 통과하던 결함[신규 결함 클래스]. 정밀조사(직접 조사, 하위위임 없음) — run_all_tests.py 전체를 먼저 정독해 이미 포화된 축(형제 엔드포인트 잠금 비대칭 축 504~507, 정책문서 불일치 축 289·317·508)과 안 겹치는 각도를 찾다가, admin.js 렌더 지점을 다시 훑어 라운드36(admin.js 2곳·insurer_portal.html 2곳 — esc() 호출 자체가 아예 빠졌던 결함, test_scan_round36_fixes.py 원문 대조로 확인)과는 다른 결함 클래스를 발견 — esc() 호출은 있는데 그 자리가 a href 속성이라 esc() 만으로는 안 막히는 경우다. esc()(admin.js:104) 는 앰퍼샌드·꺾쇠 두 종류·큰따옴표·작은따옴표 다섯 문자만 이스케이프하는데, javascript 스킴 페이로드는 그 문자를 하나도 안 써도 완전한 공격이 되어 href 속성에 그대로 앉는다 — 브라우저는 target=_blank 여부와 무관하게 javascript 스킴 href 를 클릭한 탭에서 즉시 실행한다. 실제 자리는 admin.js ctEdit()(연락처 관리 화면의 수정 모달, 옛 5471행) — 홈페이지 값을 esc() 로만 감싸 a href 에 그대로 꽂는 한 줄이었다. 이 값을 채우는 세 진입로(app.py — api_partner_create 업체 직접등록 8127행 부근, api_partner_update PATCH 업체 정보수정 8412행 부근, api_contact_import 엑셀 일괄등록 9348행 부근) 는 전부 require_admin 데코레이터라 등급 무관(하위관리자도 포함)인데, 형제 필드(phone은 RE_PHONE, email은 RE_EMAIL, biz_no는 valid_biz_no)는 전부 저장 전 형식 검사를 받는 반면 website 만 길이만 자르고(FIELD_LIMITS 또는 슬라이스 120) 스킴 검사가 전혀 없었다 — 이 코드베이스가 스스로 자주 잡아내는 형제 필드 검증 누락 패턴과 정확히 같은 모양이다(라운드484가 RE_PHONE 을 12개 형제 경로에 이식한 것과 같은 축). 영향은 등급상승 경로다 — 가장 낮은 등급(하위관리자)이 업체 정보를 고치며 website 에 javascript 스킴 값을 심으면, 그 업체의 연락처 수정창을 여는 어떤 관리자든(최고관리자 포함) 링크를 클릭하는 순간 그 세션에서 임의 JS 가 실행된다. 운영 DB 읽기전용 검산 — partners.website 가 채워진 278곳 중 275곳은 이미 http 또는 https 스킴이고 3곳만 스킴이 아예 없는 도메인 표기(예: www 로 시작)였다. 지금까지 위험한 스킴이 실제로 심긴 적은 없다 — 잠재 결함이며 아직 실제 사고는 없다. 고침은 형제와 같은 문턱을 재사용한다 — (a) app.py 에 valid_website() 공용 함수를 새로 추가(5525행, RE_PHONE·RE_EMAIL 바로 아래) — http 또는 https 가 아닌 스킴(javascript·data·vbscript 등)만 막고 스킴이 아예 없는 값은 그대로 허용(실운영 3곳의 표기 방식을 안 깨기 위함 — 링크 형식 강제가 아니라 위험한 스킴 차단이 목적). 세 진입로 모두 형제(RE_PHONE 등)와 같은 자리·같은 관례로 이 검사를 추가(create 는 이메일 검사 바로 다음, update 는 fields 루프 안 이메일 분기 바로 다음, contact_import 는 전화 분기 바로 다음 — 스킵+보고 관례 유지). (b) admin.js ctEdit() 는 값이 http 또는 https 로 시작할 때만 a href 로 걸고 그 외에는 이스케이프된 평문으로만 보이게 바꿔 방어를 심화했다 — 지금까지 놓쳤을 수 있는 다른 진입로나 이미 저장된 옛 데이터에 대한 두 번째 방어선이며, 스킴 없는 도메인 3곳은 클릭 가능한 링크에서 평문으로 바뀌는 사소한 표시상 손해만 감수한다(값 자체는 그대로 보존). 회귀테스트(test_scan_round509_fixes.py + 워커 test_scan_round509_worker.py, 30개 검사) 신설 — [1] 세 백엔드 자리와 프런트 한 자리 모두 새 코드가 소스에 정확히 한 번씩 있음을 확인. [2] 실제 Flask 서브프로세스(스크래치 DB, 하위관리자 세션)로 세 진입로 모두에 javascript·data·vbscript 세 스킴을 실제로 보내 400 거부를 확인하고 DB 를 직접 조회해 거부된 값이 전혀 반영되지 않음을 확인(엑셀 일괄등록은 스킵+보고 관례라 200 이지만 skipped_invalid 로 잡히고 updated 는 0), http 및 스킴 없는 도메인은 세 진입로 모두 정상 통과함도 함께 확인(과잉차단 아님). [3] Node 로 admin.js 의 실제 esc() 정의와 ctEdit() 렌더 표현식을 그대로 뽑아 실행 — javascript 페이로드는 a 태그(href)가 아예 생성되지 않고 이스케이프된 평문으로만 나타나며, 정상 https 값은 그대로 클릭 가능한 링크로 남음을 실측. [4] 되돌림-증명 — 세 백엔드 블록과 프런트 한 줄을 동시에 옛 코드로 되돌리면, 세 진입로 모두 javascript 페이로드를 200으로 그대로 DB 에 저장하고 admin.js 렌더도 실제로 a href 에 그대로 앉음을 재현한 뒤 두 파일을 원본과 바이트단위로 동일하게 복원했다 — 첫 실행 30/30 통과. 등록 전 grep 으로 세 진입로를 참조하는 기존 테스트 26개(라운드 36·63·70·79·80·98·101·112·154·169·174·177·197·240·285·299·409·421·429·466·483·484·493·497·505·506)를 전부 개별 재실행해 회귀 없음을 확인했다(전부 통과, test_dead_actions.py·test_template_js.py·test_fresh_db.py 도 함께 재확인). app.py·static/admin.js 둘 다 변경이라 서버 재기동이 필요하고 BUILD_HASH 로테이션이 예상되나, 이 세션은 서버 재기동 권한이 없어 예측만 하고 직접 확인하지 못했다 — 별도 세션이 재기동 후 실측 확인 바람. 한계: (i) 프런트 방어심화는 ctEdit() 이 자리에만 적용했다 — admin.js 전체에서 a href 에 사용자값을 꽂는 자리를 grep 으로 전수 확인한 결과(LIC_LOOKUP 상수·사진 URL 2곳·이번에 고친 website) 나머지 3곳은 전부 서버가 만드는 안전한 값(사진 id 기반 URL, 관리자 설정 상수)이라 추가 노출 지점은 없다고 판단하지만, insurer_portal.html·partner_portal.html 등 다른 템플릿 파일까지의 전수 재확인은 이번 라운드 범위 밖으로 남긴다. (ii) valid_website() 는 스킴 존재 여부만 보는 최소 검사라 완전한 URL 형식 검증기는 아니다 — 형제 RE_PHONE·RE_EMAIL 도 완벽한 검증기가 아니라 명백한 오타·위험값만 거르는 같은 수준이므로 의도적으로 맞췄다."),
    ("test_scan_round510_fixes.py", "스캔 510라운드 회귀 — valid_website()가 스킴 이름 한가운데 탭 또는 개행이 낀 값(예: java 다음에 탭 한 글자를 끼우고 이어서 script:...)을 스킴 없음으로 오판해 통과시키던 결함. 직접 조사(하위위임 없음) — run_all_tests.py 전체를 정독해 포화된 축(형제 엔드포인트 잠금 비대칭 504~507, 정책문서 불일치 289·317·508)과 라운드509가 남긴 꼬리(다른 템플릿 파일의 href 주입 전수 확인)를 먼저 훑었다. 사진 URL은 photos.id 기반 서버생성값(app.py 12414·14840·14850·14855행)이라 전부 안전함을 확인했고, notify() 호출 117곳을 스크립트로 전수 대조해 location.href로 이어지는 값(admin.js notiOpen)이 전부 하드코딩 리터럴이거나 안전한 정수 보간임을 확인해 클린으로 판정했다. 그러다 라운드509가 막 추가한 valid_website()(아직 이 세션 이전에는 누구도 재검증하지 않은 새 코드)를 다시 읽다가 새 결함을 발견했다. 원인 — 브라우저는 URL의 스킴을 읽기 전에 ASCII 탭과 개행(CR·LF)을 문자열 어디에 있든 전부 제거한다(WHATWG URL 표준의 첫 단계이자 잘 알려진 필터 우회 기법). 그런데 valid_website()가 쓰는 _RE_URL_SCHEME 정규식의 스킴 문자 클래스에는 탭·개행이 없어서, 스킴 이름 한가운데 탭이나 개행이 끼면 콜론 앞에서 매치가 끊겨 스킴을 못 찾고 위험한 스킴이 없다고 오판했다 — 정작 브라우저는 그 문자를 지운 뒤 진짜 스킴으로 실행한다. esc()가 막는 다섯 문자를 하나도 안 쓰므로 라운드509가 막으려던 것과 완전히 같은 등급상승 경로가 재발한다. 개행 변형은 엑셀 셀에서 줄바꿈 한 번이면 생겨 탭보다도 자연스러운 입력 경로다. 이 세션이 실제 Claude 브라우저로 직접 검증했다 — 로컬 정적 페이지를 HTTP로 띄우고, 문제의 값을 href에 그대로 넣은 링크를 실제로 클릭시켜(자바스크립트 클릭 메서드는 실제 클릭과 같은 경로를 탄다) 다른 요소의 내용이 실제로 바뀌고 콘솔 로그가 실제로 찍히는 것을 확인했다(탭·개행 두 변형 모두). 이어 valid_website 함수를 이 문제의 값으로 직접 호출해 통과 판정이 나오는 것도 이 세션이 직접 재현했다 — 라운드509의 회귀테스트는 스킴이 문자열 맨 앞에 온전히 붙은 모양만 검증해 이 변형을 다루지 않았다. 영향 범위 — valid_website()는 세 진입로(업체 직접등록·정보수정·엑셀 일괄등록)가 공유하는 단일 관문이라 셋 다 같이 뚫려 있었다. admin.js의 렌더 쪽 방어(http 또는 https로 시작할 때만 링크를 건다)가 지금 알려진 유일한 렌더 지점에서는 두 번째 방어선 역할을 해 실제 클릭 경로를 우연히 막아 주지만, 그건 저장이 이미 허용된 뒤의 보험일 뿐 valid_website 자신의 계약은 깨져 있고, 이 함수만 믿는 다른 진입로나 향후 화면이 있다면 그대로 뚫린다. 고침 — valid_website 안에서 스킴을 판정하기 전에 브라우저와 같은 문자(ASCII 탭과 CR·LF)를 문자열 전체에서 미리 제거하는 한 줄을 추가했다. 저장값 자체는 바꾸지 않고 판정에만 쓰며, 세 호출부는 전혀 손대지 않았다(단일 공유 함수 한 줄만 고쳐 세 진입로가 한 번에 고쳐진다). 회귀테스트(test_scan_round510_fixes.py + 워커 test_scan_round510_worker.py, 32개 검사) 신설 — [1] 새 코드가 valid_website 본문에 정확히 한 번 있음을 소스로 확인. [2] 같은 프로세스에서 함수를 직접 호출해 탭·개행·CR 세 변형과 스킴이 문자열 앞뒤에 오는 경계 사례까지 확인, 라운드509의 기존 판정(순수 javascript·vbscript·data 거부, https·http·스킴 없는 도메인 통과)이 전부 회귀 없이 유지됨도 함께 확인. [3] 실제 Flask 서브프로세스(스크래치 DB, 하위관리자 세션)로 세 진입로 모두에 탭 또는 개행이 낀 값을 실제로 보내 400 거부 또는 스킵 처리를 확인하고 DB를 직접 조회해 거부된 값이 전혀 반영되지 않음을 확인, 정상 값은 세 진입로 모두 그대로 통과함도 확인(과잉차단 아님). [4] 되돌림-증명 — valid_website를 라운드509까지의 구현으로 런타임에 되돌려(이 함수는 DB나 세션 등 외부 상태가 없는 순수 함수라 파일을 고치지 않고 임포트된 함수 객체만 바꿔치기하는 방식이 안전하다) 같은 배터리를 다시 돌리면, 탭과 개행이 낀 값이 세 진입로 전부에서 실제로 200으로 통과해 그 문자가 리터럴 그대로 DB에 저장되는 옛 결함이 재현됨을 실측 확인 — 첫 실행 32/32 통과. 등록 전 round509 자신의 회귀테스트(30개)를 포함해 관련 기존 테스트(라운드 63·70·79·80·98·101·112·154·169·174·177·197·240·299·409·421·429·466·483·484·493·497·505·506·509)를 전부 개별 재실행해 회귀 없음을 확인했다. app.py 변경이라 서버 재기동이 필요하고 BUILD_HASH 로테이션이 예상되나, 이 세션은 서버 재기동 권한이 없어 예측만 하고 직접 확인하지 못했다 — 별도 세션이 재기동 후 실측 확인 바람. 한계 — (i) admin.js의 렌더 쪽 방어는 이미 http 또는 https로 시작하는지만 보는 허용목록 방식이라 이번 우회값의 영향을 받지 않는다는 것을 확인했지만, 그건 이 라운드가 고친 게 아니라 라운드509가 이미 심어 둔 별개의 방어선이 우연히 막아 준 것일 뿐이므로 액면 그대로 안심하면 안 된다는 점을 분명히 남긴다. (ii) 저장값을 정제하지 않고 판정만 이분법으로 유지하는 기존 관례를 그대로 따랐다 — 탭이나 개행이 섞인 값 자체는 애초에 정상적인 홈페이지 주소일 수 없으므로 저장을 허용할 이유가 없다고 판단했다."),
    ("test_scan_round511_fixes.py", "스캔 511라운드 회귀 — dispatch.py _region_key()(102행, 자동 출동 후보선정 candidates() 가 지역 매칭에 쓰는 열쇠 추출 함수)가 '대구'를 도시명이 아니라 구 단위 접미어로 오판해 도시명을 '대' 한 글자로 잘라버리던 결함. 직접 조사(하위위임 없음) — run_all_tests.py 전체를 정독해 포화된 축(형제 엔드포인트 잠금 비대칭 504~507, 정책문서 불일치 289·317·508, website 저장형 XSS 509·510, DUP_BIZNO 계열, 재알림 쿨다운, activity_log 마스킹, 가운뎃점 정규화, 출동수배 버튼 등급게이트, catch분기 화면정리 6클러스터, 입점신청 상태역전)와 겹치지 않는 각도를 '재경매·지오코딩 경계조건' 힌트로 찾다가, dispatch.py의 _region_key()가 이 세션이 확인한 run_all_tests.py 전수 대조 결과 라운드130·186·499(모두 같은 파일의 형제 함수 _like_escape·_norm_dot을 다뤘을 뿐 이 함수 자체는 대상이 아니었음)의 사각지대였음을 확인 후 함수 단위로 재감사해 발견. 결함 — '서울특별시 송파구'→'송파'처럼 시/도 접두어를 뗀 뒤 남은 토큰 중 구/시/군으로 끝나는 첫 토큰을 찾아 접미어를 자르는 로직인데, '대구'(광역시)는 도시 이름 자체의 마지막 글자가 우연히 '구'다 — '대구광역시 동구'는 리터럴 치환으로 토큰이 [대구,동구]로 쪼개지는데, 반복문이 진짜 구 단위인 '동구'에 닿기도 전에 '대구' 자신이 구로 끝난다는 이유만으로 먼저 걸려 '대'(대구의 첫 글자, 무의미한 한 글자)를 반환한다 — 실행으로 직접 재현(_region_key('대구광역시 동구','')=='대', 정상값 '동'). db.SIDO 17개 시/도 약칭 중 이 함정에 걸리는 것은 '대구' 하나뿐(나머지는 구/시/군으로 끝나지 않음)이며, geo.py가 이미 여러 라운드(120·235·264·293·316)에 걸쳐 정확히 이 클래스(짧은 지명이 다른 토큰의 접미어와 우연히 겹치는 문제)를 전용 로직(_word_in·_AMBIG·SIDO_ALIAS)으로 막아 왔는데 dispatch.py의 이 함수는 그 교훈을 못 물려받은 훨씬 단순한 자체 구현이었다. 영향 — candidates() 는 이 값을 앞뒤에 퍼센트 와일드카드를 붙인 LIKE 패턴으로 그대로 SQL 에 쓴다. 운영 DB 읽기전용 조회로 실측: 활성 협력사 400곳 중 옛 rkey('대') 매칭 88곳인데 그중 실제 '대구'가 들어간 곳은 32곳뿐 — 나머지 56곳(대전·포항·서울 강동구·경기 의왕·인천 남동구 등 전국 각지, 흔한 음절 '대' 하나의 우연한 포함)이 대구 사건에서 '같은 지역'(1·2순위)으로 잘못 섞인다. 대구는 인구 약 240만의 광역시로 실제 사건·협력사가 존재해 이론적 결함이 아니다. 고침 — db.SIDO(dispatch.py가 이미 import db as DB로 참조 가능한 기존 상수)에 있는 토큰은 구/시/군 접미어 판정 대상에서 제외하는 한 줄만 추가했다(새 헬퍼·새 상수 없음) — '대구' 외 16개 시/도는 애초에 구/시/군으로 안 끝나 이 검사가 없어도 안전했으므로 회귀 없이 '대구' 한 곳만 고쳐진다. 회귀테스트(test_scan_round511_fixes.py, 22개 검사) 신설 — [1] 새 코드가 _region_key() 본문에 정확히 1번 있음을 소스로 확인. [2] 같은 프로세스에서 _region_key()를 대구 3variant + 기존 정상 케이스(서울·부산·경기·전북특별자치도 등) 6개로 직접 호출해 대구만 고쳐지고 나머지는 회귀 없음을 확인. [3] 실제 sqlite3(:memory:)+dispatch.candidates()로(라운드130과 같은 격리 기법 — 사건·협력사 공종을 서로 안 겹치게 둬 '같은 지역' 판정만 순수 관찰) 대구 동구 사건에 진짜 대구 협력사와 대전 협력사(가짜매칭 유발)를 함께 넣어, 고친 뒤에는 대전 협력사가 '같은 지역'에서 정확히 빠짐을 확인. [4] 되돌림-증명 — _region_key()를 라운드511 이전 구현(SIDO 예외 없음)으로 런타임에 되돌리면(DB·세션 등 외부상태가 없는 순수 함수라 파일을 안 건드리고 임포트된 함수 객체만 바꿔치기하는 방식이 안전, candidates() 는 이 이름을 모듈 전역으로 호출하므로 교체가 그대로 반영됨) 같은 시나리오에서 대전 협력사가 실제로 '같은 지역'으로 잘못 섞여 들어오는 옛 결함이 재현됨을 실측 확인 후 원상복구까지 확인. [5] 운영 DB 대조(읽기전용, 쓰기 없음) — 옛 rkey 매칭 88곳 중 실제 대구는 32곳뿐임을 재확인(정보성 기록). 등록 전 grep으로 _region_key·dispatch.candidates 를 참조하는 기존 테스트 22개 파일을 확인해 관련도 높은 15개(test_dispatch.py 87/87 · 라운드130 8/8 · 라운드329 4/4 · 라운드117 16/16 · 라운드122 13/13 · 라운드138 11/11 · 라운드140 17/17 · 라운드152 9/9 · 라운드172 18/18 · 라운드182 6/6 · 라운드189 10/10 · 라운드190 6/6 · 라운드257 8/8 · 라운드281 13/13 · 라운드411 13/13 · 라운드482 8/8 · 라운드52 26/26 · 라운드94 8/8 · 라운드95 23/23)를 전부 개별 재실행해 회귀 없음을 확인했다(라운드28·29는 최초 실행 시 스크래치 DB 미초기화로 실패했으나 db.init_db() 로 스키마를 만든 뒤 재실행하니 각 15/15·11/11 통과 — 내 검증 스크립트의 준비 누락이었고 코드 결함 아님을 직접 확인). run_all_tests.py --quick 전체 배터리도 이 수정 전(406/406 통과) 확인 후 적용해 사전 베이스라인을 확보했다. dispatch.py 변경이라 서버가 그 모듈을 다시 import 하려면 재기동이 필요하나, 이 함수는 app.py 가 아니라 dispatch.py 소속이라 BUILD_HASH(app.py+static+templates 해시)에는 안 잡힌다는 점을 밝혀 둔다 — 이 세션은 서버 재기동 권한이 없어 재기동 후 실제 dispatch.candidates() 동작까지는 직접 확인하지 못했다. 한계 — (i) '경기도 수원시 팔달구'류(경기도가 SIDO에 없어 애초에 안전했던 경로)처럼 첫 매치에서 멈추는 기존 동작(시 단위에서 멈추고 더 안쪽 구 단위까지 안 내려감)은 이번 수정 범위가 아니다 — '대구' 오판과는 무관한 별개의 정밀도 이슈로, 실제 피해 사례를 못 찾아 손대지 않았다. (ii) 이 함수는 좌표가 아직 없는 사건·협력사의 지역 근사 매칭용이라(파일 상단 독스트링), 좌표 기반 정밀 검색으로 대체되면 이 함정 자체가 사라진다 — 그 전까지의 임시 방편이라는 점은 원래 설계 그대로다."),
    ("test_scan_round512_fixes.py", "스캔 512라운드 회귀 — geocode_fill.py _gu_set()가 대구를 구 단위 지명으로 오판해, 구 정보 없이 대구만 등록된 협력사·사건의 좌표를 동네 불일치로 오판해 geo_src=시도실패로 영구 낙인찍던 결함. 직접 조사(하위위임 없음) — run_all_tests.py 전체를 정독해 포화된 축(형제 엔드포인트 잠금 비대칭 504~507, 정책문서 불일치 289·317·508, website 저장형 XSS 509·510, dispatch.py 지역열쇠 파싱 511)과 겹치지 않는 각도를 찾다가, 라운드511이 dispatch.py _region_key()에서 고친 것과 정확히 같은 클래스의 결함(대구는 시/도 이름 자체의 마지막 글자가 우연히 구다)이 geo.py도 dispatch.py도 import하지 않는 별개의 독자 재구현인 geocode_fill.py _gu_set()/_region_ok()에도 전파돼 있음을 직접 대조해 발견. 결함 — _gu_set(s)는 문자열에서 정규식으로 시군구 이름을 전부 뽑는데, 대구가 그 자신의 마지막 글자 때문에 구 단위 지명으로 오판된다. 등록 지역이 대구뿐이고 주소도 구 이름을 반복하지 않는 협력사는 _region_ok()의 구 정보가 없으면 시도로 판정한다는 자신의 폴백 원칙이 이 오판 때문에 막혀, 실제로는 같은 도시인 검색 결과(대구광역시 동구 등)까지 서로 다른 구로 보고 동네 불일치로 걸러버린다 — geocode_fill.py는 그러면 그 행을 geo_src=시도실패로 표시해 재실행해도 다시는 시도조차 안 한다. 실측(직접 재현, 순수함수 호출) — _region_ok(대구, 대구광역시 동구) == False(다른 16개 시도는 전부 구/시/군으로 안 끝나 이 함정에 안 걸린다, 라운드511과 동일한 유일 충돌 지점). 운영 DB 읽기전용 조회 결과 이 저장소의 기존 대구 협력사 7곳은 전부 주소 칸에 대구광역시가 함께 적혀 있어(region과 address를 이어붙여 판정하므로 주소 쪽 직접일치가 구제) 우연히 이 함정을 피해 갔을 뿐 — 주소가 도로명만 적고 시/구를 반복하지 않는 신규 등록부터 바로 재현된다(실데이터에 이미 지사만 대구로 적는 표기 사례가 있어 이론적 결함이 아니다). 고침 — db.SIDO(라운드511이 dispatch.py에 쓴 것과 같은 기존 상수, 이 파일도 이미 import db as DB로 참조 가능)에 정확히 일치하는 토큰은 _gu_set()의 결과에서 제외하는 한 줄만 추가했다(새 헬퍼·새 상수 없음) — 대구 외 16개 시도는 애초에 구/시/군으로 안 끝나 이 제외가 없어도 안전했으므로 회귀 없이 대구 한 곳만 고쳐진다. 회귀테스트(test_scan_round512_fixes.py, 23개 검사) 신설 — [1] 새 코드가 _gu_set() 본문에 정확히 1번 있음을 소스로 확인. [2] 같은 프로세스에서 _region_ok()를 대구 4variant + 기존 자체점검(demo()) 8건으로 직접 호출해 대구만 고쳐지고 나머지는 회귀 없음을 확인. [3] 실제 geocode_fill.fill()을 스크래치 DB와 스텁 ADDR.search로 끝까지 실행해(round267이 확립한 기법) 구 정보 없이 대구만 등록된 협력사의 좌표가 실제로 채워짐을 확인. [4] 되돌림-증명 — _gu_set()을 이 라운드 이전 구현(SIDO 제외 없음)으로 런타임에 되돌려(DB·세션 등 외부상태가 없는 순수 함수라 파일을 안 건드리고 임포트된 함수 객체만 바꿔치기하는 방식이 안전, _region_ok()는 이 이름을 모듈 전역으로 호출하므로 교체가 그대로 반영됨) 같은 시나리오를 새 협력사 행으로 다시 돌리면, 실제 fill() 실행에서 geo_src=시도실패로 영구 낙인찍히는 옛 결함이 재현됨을 실측 확인 후 원상복구까지 확인 — 첫 실행 23/23 통과. 등록 전 grep으로 _gu_set·_region_ok·geocode_fill을 참조하는 기존 테스트 11개 파일(라운드120·159·160·265·266·267·271·294·302·32·489)을 전부 개별 재실행해 회귀 없음을 확인했다(전부 통과 — 라운드159의 8건 기존 자체점검·라운드267의 fill() 저장실패 격리 검증 포함). test_geo.py도 함께 재확인해 무관함을 확인(독립 모듈, 회귀 없음). geocode_fill.py는 app.py가 import하는 모듈이 아니라(수동 실행 배치 CLI) 서버 재기동이 불필요하다. 한계 — (i) 운영 DB의 기존 대구 데이터에는 현재 이 결함으로 실제 깨진 행이 없다(전부 주소에 대구광역시가 중복 기재돼 우회됨) — 잠재 결함이며 다음 신규 등록부터 영향권이라는 점을 정직하게 남긴다. (ii) _gu_set()이 도로명 중간에 우연히 구/시/군으로 끝나는 조각(예: 동대구로 → 동대구)을 잡아내는 별개의 부정확성은 이번 수정 범위가 아니다 — 대구 SIDO 충돌과는 무관한 별개의 정밀도 이슈이고 실제 피해 사례를 못 찾아 손대지 않았다(라운드511이 남긴 것과 같은 성격의 한계)."),
    ("test_scan_round513_fixes.py", "스캔 513라운드 회귀 — api_auction_set_deadline()(POST /api/auctions/<aid>/deadline)의 마감된 재경매 재개 분기가 형제 api_case_reopen()(원경매)과 달리 auctions.reopen_count/MAX_REOPEN 상한을 전혀 안 봐, 변경견적 재경매(추가분·전체재경매)를 이 경로로 몇 번이든 무제한 재개할 수 있던 결함. 전체재경매 자체의 라운드 상한(MAX_CO_ROUND, api_co_full_reauction)은 새 라운드를 여는 경로에만 걸려 이 경로에서는 우회된다. 직접 조사(하위위임 없음) — 이미 포화된 축(형제 엔드포인트 잠금 비대칭 504~507, change_orders 생애주기 492 등)과 겹치지 않는 재경매 엣지케이스를 찾다가 발견. 고침 — 형제와 같은 기존 상수(MAX_REOPEN)·컬럼(reopen_count)을 재사용해 상한 도달 시 409(MAX_EXTEND)로 막는다. 회귀검사 21개 신설 — Flask test_client로 3회 재개 성공·4번째 차단·원경매 대조군·되돌림-증명(옛 SQL은 상한 없이 무조건 성공)을 확인. 관련 기존 테스트(round103·round114·test_b4_deadline.py) 개별 재실행으로 회귀 없음 확인."),
    ("test_scan_round514_fixes.py", "스캔 514라운드 회귀 — collect_emails.py BAD_LOCAL의 webmaster@example 항목이 애초에 매치될 수 없는 죽은 데이터였던 결함(_bad_local_word_in은 e.partition(@) 앞부분인 local part에서만 단어를 찾는데 local part는 정의상 @을 담을 수 없다). 그 자리를 메워야 할 BAD_DOMAIN에는 example.com/example.co.kr만 있고 RFC 2606 예약 도메인인 example.org/example.net이 빠져 있어, webmaster@example.org 같은 흔한 플레이스홀더 주소가 collect_emails.pick_emails()에서도 clean_collected_emails.is_junk()(둘 다 이 튜플을 공유)에서도 안 걸러지고 그대로 수집됐다. 직접 조사(하위위임 없음) — 이미 포화된 축과 겹치지 않는 각도로 round218·267·299·420이 이미 여러 번 정밀조사한 collect_emails.py의 BAD_LOCAL/BAD_DOMAIN 판정 데이터를 값 단위로 대조하다 발견. 운영 DB 읽기전용 확인 — email_source=수집(홈페이지)인 행이 현재 0건이라(이 도구가 아직 실운영에서 안 돎) 실제 피해 사례는 없는 예방적 수정이다. 고침 — 절대 안 걸리는 죽은 항목을 BAD_LOCAL에서 제거하고, example.org·example.net을 BAD_DOMAIN에 추가한다(새 헬퍼·새 상수 없이 기존 도메인 차단 메커니즘만 확장, 두 파일이 공유하므로 한 번에 함께 고쳐진다). 회귀검사 23개 신설 — pick_emails()·is_junk() 양쪽에서 webmaster@example.{org,net,com,co.kr} 4종이 걸러지는지, 실제 업체 도메인의 webmaster@ 주소는 과잉차단 없이 통과하는지, round299의 BAD_LOCAL 경계(latest/contest 통과, test/no-reply 차단)에 회귀가 없는지, 되돌림-증명(옛 데이터로는 webmaster@example.org가 실제로 샘)을 확인. 관련 기존 테스트(round218·265·267·271·299·420) 개별 재실행 전부 통과로 회귀 없음 확인. collect_emails.py는 app.py가 import하지 않는 독립 배치 CLI라 서버 재기동 불필요."),
    ("test_scan_round515_fixes.py", "스캔 515라운드 회귀(1차합의 보험사 승인 시 피해자안내 누락 — 형제 낙찰경로 둘(경매·어드민)은 notify_victim을 부르는데 더 흔한 1차합의 경로만 빠짐)"),
    ("test_scan_round516_fixes.py", "스캔 516라운드 회귀 — addr_search.py _open_map()의 place(장소) 검색 결과가 구(區) 있는 시(성남·수원·용인 등)에서 그 구를 통째로 잘라 region을 도+시까지만 돌려주던 결함(앞-두-토큰 고정 추출 parts[0]/parts[1] 탓, '서울 송파구' 같은 2단계만 맞고 3단계는 깨짐). 직접 조사(하위위임 없음) — addr_search.py 감사이력(266·294·302·316·489)이 전부 예외처리·실패침묵·길이상한 같은 견고성 축이었을 뿐 정상 실행되지만 값이 틀리는 논리결함은 다룬 적이 없었고, round294가 _sigungu() 자신은 클린이라 확인했지만 그 호출부(place 루프의 인자 추출)까지는 확인한 적이 없다는 점에서 발견 — round511·512와 같은 '지역 문자열을 각 파일이 독자 재구현한다' 구조적 패턴을 addr_search.py에 적용. 실측(라이브 카카오 무인증 엔드포인트) — '용인 에버랜드'·'광교호수공원'·'카카오판교아지트' 등 이 파일의 존재 이유인 장소이름 검색 전부에서 처인구·영통구·분당구가 사라짐, 같은 질의의 address 결과(d1_name/d2_name 구조화 필드 사용)는 정확해 place 루프만의 결함임을 확인. 영향 — 이 region 값을 addrpick.js가 화면 지역칸에 그대로 채우고 사건등록·입점신청·프로필수정 4경로가 그대로 저장하는데, dispatch.py candidates()의 _region_key()는 region을 address보다 우선 읽어 자동 출동 후보 '같은 지역' 판정 열쇠로 쓴다 — 온전한 주소가 있어도 무시되고 시 전체가 같은 지역으로 뭉뚱그려진다. 고침 — 새 헬퍼 _admin_region(addr) 신설, 첫 토큰(시/도)은 그대로 두고 이어지는 토큰이 시/군/구로 끝나는 동안 계속 담아 2단계·3단계 양쪽을 하나의 규칙으로 맞춘다(동·읍·면은 이 접미어로 안 끝나 자연히 멈춤). 구조화 필드를 쓰는 address 루프·_official()은 그대로 둔다. 회귀검사 16개 신설 — 단위(2단계·3단계·경계값 7종)·되돌림-증명(옛 앞-두-토큰 로직으로 실제 재현)·_open_map() 실행(같은 가짜 응답에서 address·place 대조) 확인. 관련 기존 테스트(round160·161·266·267·294·302·316·489·512) 개별 재실행 전부 통과로 회귀 없음 확인. addr_search.py는 app.py가 import하는 모듈이나 이번 수정은 place 검색이 실제로 호출될 때만 경로를 타므로 재기동 후 실사용으로 최종 확인 권장."),
    ("test_scan_round517_fixes.py", "스캔 517라운드 회귀 — collect_emails.py가 partners.website를 실제로 fetch()하면서 SSRF 방어가 전혀 없던 결함. website는 3개 진입로(api_partner_create·api_partner_update·api_contact_import)가 전부 @require_admin(등급 무관, 라운드509 주석)로 저장하고, 저장 시점 검증(valid_website, 라운드509·510)은 위험한 URL 스킴(javascript: 등)만 막을 뿐 호스트는 전혀 안 봐서 http(s):// 형식이면 127.0.0.1이든 사설망 주소든 그대로 통과했다. app.py는 이미 같은 위험(웹훅 URL)을 _webhook_safe_ip()로 막는데(라운드38·84·157) 형제인 이 파일에는 그 방어가 없어, 하위관리자 계정 하나(또는 그 탈취)만 있으면 website를 내부 주소로 심어 두고 운영자가 이 배치를 나중에 돌리는 순간 서버가 자기 내부망을 대신 두드리게 만들 수 있었다(실측: 로컬 서버로 재현). 고침 — app.py와 같은 판정(_host_is_internal, ipaddress 기반 loopback·link-local·private·reserved·multicast·unspecified·CGNAT 차단)을 collect_emails.py에 이식하고 fetch()뿐 아니라 robots_allows()에도 건다(실측: fetch()만 막으면 robots.txt 요청 한 번은 그대로 내부 서버에 도달했다 — 두 자리 모두 막아야 함). 웹훅 방어와 달리 접속을 IP 하나에 못박는 DNS 리바인딩 방어까지는 하지 않는다(ponytail 주석으로 명시 — 이 도구는 상시 자동재시도가 아니라 운영자가 결과를 보며 수동으로 돌리는 1회성 배치라 노출이 훨씬 적다). 테스트 하네스가 127.0.0.1 로컬 서버로 사이트를 흉내내는 기존 회귀 2개(라운드218·299)는 BOKGUON_COLLECT_ALLOW_LOCAL=1로 이 방어만 예외 허용하도록 함께 수정(운영에서는 켜지 않음) — 두 테스트 모두 개별 재실행 통과 확인, 나머지 collect_emails 관련 테스트(265·267·271·420·514)는 실제 DNS가 안 풀리는 가짜 호스트나 urlopen 자체를 모킹해 이 방어와 충돌하지 않음을 확인. 회귀테스트 15개 신설 — 실제 getaddrinfo로 대역별 분류 확인, 실제 로컬 서버로 fetch()·robots_allows() 두 접속지점 모두 도달하지 않음을 증명, 되돌리기(방어를 끄면 실제로 새는 것)로 인과관계 직접증명, 테스트 하네스 예외 스위치 동작 확인까지 포함. collect_emails.py는 독립 CLI(app.py가 import하지 않음)라 재기동 불필요."),
    ("test_scan_round518_fixes.py", "스캔 518라운드 회귀 — check_orphan_chars.py(고아문자·깨진문자 점검 CLI)가 한국어 윈도 기본 콘솔 코드페이지(cp949)에서 결과를 한 줄도 못 내고 UnicodeEncodeError 로 죽던 결함. 직접 조사(하위위임 없음) — 이미 포화된 축(형제 엔드포인트 잠금 비대칭 504~507, 지역문자열 독자구현 511·512·516, XSS/SSRF 509·510·517, 정책문서 불일치 289·317·508)과 겹치지 않는 각도를 찾다가, 소스만 읽지 않고 이 저장소의 점검 도구(check_*.py)들을 실제로 실행해 보는 접근으로 전환 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 누락 점검, 106개 함수 전수)를 먼저 실행해 클린임을 확인한 뒤 형제 도구 check_orphan_chars.py 를 실행하자 166행 print(고아문자 — 대상 N개 파일)에서 UnicodeEncodeError('\\u2014' 인코딩 불가)로 즉시 죽는 것을 실측. 원인 — check_tx_paths.py(19~27행)·repair_estimate.py·popbill_check.py·manage.py·partner_accounts.py 등 이 저장소의 거의 모든 단독 실행 CLI(27개 파일에서 확인)는 윈도 기본 콘솔이 cp949 라 em dash 같은 문자를 print 하면 죽는다는 이유로 stdout 을 UTF-8 로 reconfigure() 하는 방어를 이미 갖고 있는데, 같은 저자·같은 목적(check_*.py 점검 도구)·거의 같은 구조인 check_orphan_chars.py 만 이 방어가 빠져 있었다 — 이 코드베이스가 스스로 반복해서 잡아내는 형제는 이미 막았는데 이 파일만 빠졌다 패턴. 더 나쁜 점 — 이 스크립트 자신이 다른 코드의 인코딩 결함(깨진 문자·고아문자)을 잡는 도구인데, 정작 자신이 한국어 윈도 콘솔에서 결과를 하나도 못 내고 죽으면 실제로 깨진 문자가 있는지 없는지조차 알 방법이 없다(자기도구가 내는 거짓 초록의 자매 격인 자기도구가 아예 안 도는 실패). 고침 — check_tx_paths.py 가 이미 쓰는 것과 정확히 같은 방어(try: reconfigure, 실패시 TextIOWrapper 폴백)를 check_orphan_chars.py 의 기존 import 직후에 그대로 옮겼다(새 헬퍼·새 상수 없음). 회귀테스트(test_scan_round518_fixes.py, 12개 검사) 신설 — [1] 소스로 형제와 같은 방어가 정확히 한 번 있음을 확인. [2] 실제 서브프로세스(PYTHONIOENCODING=cp949 로 강제 — 콘솔에 붙어있지 않을 때 파이썬이 stdout 인코딩을 고를 때 실제로 참조하는 값이며 이 저장소가 도는 한국어 윈도의 기본 ANSI 코드페이지와 같음, cmd.exe 파일 리다이렉트로 환경변수 없이도 같은 크래시를 재현 확인)로 check_orphan_chars.py 를 끝까지 실행해 트레이스백 없이 실제 진단 머리글까지 출력됨을 확인. [3] 되돌림-증명 — 방어 블록만 정확히 도려낸 사본(도려낸 결과가 원본 임포트 헤더와 글자 그대로 동일함을 먼저 확인)을 같은 cp949 환경에서 서브프로세스로 실행해, 방어를 지우면 실제로 같은 UnicodeEncodeError 로 죽고 진단 결과를 하나도 못 냄을 재현 확인 — 첫 실행 12/12 통과. check_orphan_chars.py 는 app.py 가 import 하지 않는 독립 CLI 라 서버 재기동 불필요."),
    ("test_scan_round519_fixes.py", "스캔 519라운드 회귀 — round518 과 같은 cp949 콘솔 크래시가 남아 있던 형제 배치 CLI 6개(collect_emails.py·build_pages.py·clean_collected_emails.py·serve_waitress.py·crypto_util.py·db.py). 직접 조사(하위위임 없음) — round518 이 '이 저장소의 거의 모든 단독 실행 CLI는 이미 방어를 갖고 있다'고 적어 둔 말을 액면 그대로 믿지 않고, grep 으로 '실행: python 파일명.py' 식 배치 CLI를 전수 나열해 방어(stdout.reconfigure) 존재 여부를 파일 단위로 직접 대조했다. 1순위 3개는 이미 리드가 있었고 grep 으로 방어 부재와 정확한 print 문구(em dash 포함)까지 재확인 후 수정: collect_emails.py(이메일 수집 — 대상 …곳), build_pages.py(표 밖 자리표시자 / docs 생성 완료), clean_collected_emails.py(수집분 검사 — …건 / 삭제 실패 — 건너뜀) — 정확한 줄번호는 이후 가드 삽입으로 몇 줄씩 밀렸으므로 문구로 특정. 2순위 전수조사에서 두 개를 추가로 발견했다. ① serve_waitress.py(실서비스 운영 진입점 자신) — app.py(print 8곳 실측, 전부 fingerprint(d) 오탐이거나 개발서버 전용 분기라 클린)·wsgi.py(prints는 자신의 __main__ 분기뿐)는 무관했지만, serve_waitress.py:72 의 시작배너 경고줄이 '⚠'(U+26A0)을 쓰면서 방어가 전혀 없었다(이 세션이 c.encode('cp949') 로 U+26A0·U+2014·U+2550·U+2022·U+2013 등이 cp949 인코딩 불가함을 직접 실측, U+2605·U+25B6·U+2192 등은 가능함도 확인). BOKGUON_ENV 를 prod 로 명시하지 않은 채(dev 기본값) 감시자가 stdout 을 파일로 리다이렉트해 재시작하면 서버가 배너조차 못 찍고 죽어 아예 기동하지 않는 경로라 원래 3개보다 파급이 크다고 판단해 함께 고쳤다. ② serve_waitress.py 를 조사하며 app.py 가 import 하는 로컬 모듈 11개를 cp949 강제 환경에서 하나씩 import 해 stdout 인코딩 변화를 대조(bisection)하다가, repair_estimate.py 가 이미 갖고 있던 방어가 app.py 를 거치는 모든 실행에 부작용으로 전파된다는 것을 발견 — 그 김에 app.py 가 import 하는 나머지 로컬 모듈의 __main__ 자체점검 블록도 전수로 열어 보다가 crypto_util.py(자체 암복호화 점검 데모의 마지막 줄, '검증 통과 — 암호화/복호화 정상')도 같은 결함이 있음을 발견. app.py 를 거쳐 실행될 땐 repair_estimate.py 의 방어에 우연히 묻어가지만 'python crypto_util.py' 단독 실행에는 그 우연한 구제가 없어 그대로 죽는다(실측 확인). ③ crypto_util.py 를 고치며 같은 논리로 app.py 가 import 하는 더 아래(기반) 계층인 db.py 의 __main__ 자체점검('python db.py', 스키마 반영·건수 요약)도 열어 보니 '⚠ 기존 DB 에 데이터가 있습니다' 경고줄(--reset 시 기존 데이터 보호용)에 같은 결함이 있었다 — db.py 는 app.py 보다 아래 계층이라(app.py 가 db.py 를 import) repair_estimate.py 의 우연한 구제가 애초에 닿지 않는다. 참고로 firstday_server.py 의 raise SystemExit(...) 두 곳도 em dash 를 쓰지만 실측 결과 크래시 없음 — CPython 은 stderr 기본 오류처리가 backslashreplace 라 uncaught SystemExit/예외 메시지는 애초에 print() 와 다른 안전한 경로를 타기 때문(수정 불필요, 다음 라운드 참고용 지식으로 남김). gunicorn_conf.py 는 print() 자체가 없어 무관. app.py 자신의 'python app.py' 직접실행 경로(21044행 부근 print, ⚠ 포함)는 복구온_서버실행.bat 이 chcp 65001 로 콘솔을 UTF-8 로 미리 바꿔 두는 데다 repair_estimate.py 의 부작용까지 이중으로 보호돼 있어 이번 라운드 범위에서 의도적으로 제외(20000행 규모 핵심 파일이라 현재 비노출 상태에서 손대는 리스크가 이득보다 크다고 판단, 다음 라운드 참고용으로 명시). 고침은 여섯 파일 모두 동일 — check_tx_paths.py 가 이미 쓰는 방어(try: reconfigure, 실패 시 TextIOWrapper 폴백)를 각 파일의 기존 import 직후에 그대로 옮겼다(새 헬퍼·새 상수 없음). 회귀테스트(test_scan_round519_fixes.py, 62개 검사) 신설 — 여섯 파일 모두 소스 확인 + 실제 서브프로세스(PYTHONIOENCODING=cp949 강제)로 각 대상 print 라인을 실제로 통과시켜 확인 + 되돌림-증명까지 포함. DB 를 쓰는 세 파일(collect_emails.py·clean_collected_emails.py·db.py)은 BOKGUON_DB_PATH 를 스크래치로 못박고 DB.init_db()로 통제된 스키마를 만들어(대상 0건 또는 --reset 안전분기) 네트워크 호출·실 데이터 훼손 없이 안전하게 실행했다. build_pages.py 는 실제 build() 가 docs/ 를 rmtree 하므로 templates/·static/·data/·legal_docs.py·envload.py 만 복사한 격리 임시 디렉터리에서 돌려 리포지토리 실제 docs/ 를 절대 안 건드렸다(테스트 자신도 이를 사후 확인). serve_waitress.py 는 round273 이 확립한 격리 포트 하드킬 패턴을 재사용해 운영 포트(8771)를 전혀 건드리지 않았다. crypto_util.py·db.py 는 app.py 를 거치지 않는 단독 실행 자체점검이라 격리 없이도 안전했다. 되돌림-증명 과정에서 세 가지 숨은 사이드채널을 이 세션이 직접 실측으로 발견해 바로잡았다 — (a) collect_emails.py 는 db.py 를 import 하는데, db.py 도 이번 라운드에서 방어가 생겨 그 import 시점에 형제의 방어가 먼저 걸려 이 파일 자신의 방어를 지워도 크래시가 안 남 — db.py 도 함께 되돌린 사본으로 import 대상을 바꿔치기해 순수한 인과관계를 확인. (b) clean_collected_emails.py 는 collect_emails.py 와 db.py 둘 다 import 하는 사슬이라, 이 둘을 모두(그리고 collect_emails.py 되돌린 사본 자신의 db.py import 까지) 함께 되돌려야 순수한 인과관계가 나왔다(처음 실행 시 실제로 이 함정에 두 번 빠져 '안 죽음'으로 잘못 나옴). (c) serve_waitress.py 는 from wsgi import application 으로 app.py 를 끌어오는데, app.py 가 import 하는 repair_estimate.py 가 이미 자기 몫의 reconfigure 방어를 모듈 최상단에 갖고 있어 프로세스 전체의 stdout 을 먼저 바꿔 버림(처음 실행 시 크래시 대신 '정상 기동 후 타임아웃'으로 잘못 나옴) — 실제 app.py 대신 아무 방어 없는 더미 WSGI 앱을 붙인 격리 사본으로 순수한 인과관계를 확인. crypto_util.py·db.py 는 app.py 를 거치지 않는 단독 실행이라 이런 사이드채널이 없었다. 첫 실행(모든 사이드채널 수정 후) 62/62 통과. 여섯 파일 모두 app.py 가 import 하지 않는(app.py 는 오히려 이 중 crypto_util.py·db.py 를 import 하는 쪽) 독립 배치 CLI/진입점 스크립트/기반 모듈이라 서버 코드 자체의 재기동 필요는 없으나, serve_waitress.py 는 실행 중인 서비스 프로세스 자신의 소스이므로 다음 하드킬 재시작부터 이 수정이 실제로 반영된다(재기동 자체는 이 세션 권한 밖 — 오케스트레이터가 WMI 로 처리). db.py 는 app.py 가 module 최상단에서 무조건 import·init_db() 하는 핵심 기반 파일이라 신중하게 다뤘다 — 실제로 fresh import + init_db(seed_demo=False) + get_db() 스모크 테스트를 먼저 통과시키고, --reset 흐름을 실제 데이터가 있는 스크래치 DB 로 실행해(--yes 없이) 경고 후 SystemExit 으로 안전하게 멈추는 것까지 확인한 뒤에야 회귀테스트에 반영했다."),
    ("test_scan_round520_fixes.py", "스캔 520라운드 회귀 — 협력사·보험사 포털 로그인(_portal_authenticate, app.py:784)이 레거시(SHA256) 비밀번호 해시를 검증은 하면서도 PBKDF2로 승급하지 않던 결함. 직접 조사(하위위임 없음) — 이미 포화된 축(형제 엔드포인트 잠금 비대칭, 지역문자열 독자구현, XSS/SSRF, 정책문서 불일치, cp949 콘솔인코딩 7파일, 권한데코레이터 260개 라우트 전수)과 겹치지 않는 새 각도를 찾다가, manage.py 20개 서브커맨드·repair_estimate.py 계산식·dispatch.py candidates()·compliance.py 도급판정·crypto_util.py AES-GCM·geo.py haversine·sw.js 오프라인캐시 등 십수 개 축을 순서대로 파봤으나 전부 이미 다층으로 방어돼 있거나(각 round 주석이 실측 근거까지 남김) 자체 검증 통과(check_tx_paths.py 106개 함수 전수 클린)로 판정 — 마지막에 db.py 의 인증 원시함수(hash_pw/verify_pw/is_legacy_hash)로 방향을 틀어, admin 로그인(api_login, app.py:2883)이 DB.is_legacy_hash() 로 로그인 성공 시 레거시 해시를 PBKDF2로 자동 승급하는 코드가 있음을 확인한 뒤, 이 함수를 부르는 app.py 전체를 grep 해 딱 1곳(admin 로그인)에서만 쓰이는 것을 실측 — 협력사·보험사가 공유하는 유일한 로그인 관문 _portal_authenticate()(원계정·하위계정 두 갈래 모두)에는 이 승급이 아예 없었다(같은 db.verify_pw()/hash_pw() 를 쓰면서 형제 함수의 로직만 안 옮겨진 형제 불일치). 영향 — db.py:verify_pw() 의 레거시 분기(솔트 없는 단일회 SHA256, bokguon$ 접두어+비번)로 저장된 협력사·보험사 계정(원계정이든 portal_users 하위계정이든)은 로그인이 계속 성공하면서도 관리자 계정보다 노출 표면이 훨씬 큰(협력사 수백 곳·보험사 전체) 채로 그 약한 해시가 영구히 방치된다 — admin 로그인 경로에 이 승급이 애초에 추가됐다는 사실 자체가 이 저장소 어딘가에 실제로 레거시 해시 계정이 존재했거나 존재할 수 있다는 근거다. 고침 — app.py:_portal_authenticate() 의 원계정(row) 분기·하위계정(sub) 분기 둘 다에 admin 로그인과 정확히 같은 패턴(DB.is_legacy_hash() 확인 → DB.hash_pw() 로 재해시 → 자기 표만 UPDATE, 원계정은 partners/insurers, 하위계정은 portal_users)을 이식했다(새 헬퍼·새 상수 없음, 기존 db.py 함수만 재사용). 승급도 해시를 바꾸므로 반환 dict 구성 전에 로컬 row/sub 딕셔너리를 갱신해 pw_sig(세션 지문)가 새 해시를 보게 했다(admin 경로와 동일 원칙). 회귀테스트(test_scan_round520_fixes.py, 19개 검사) 신설 — [1] 소스 확인(두 분기 모두 is_legacy_hash 호출 + 각자의 표를 UPDATE함). [2]~[4] 실행 기반 — 협력사 원계정과 보험사 하위계정 각각에 레거시 해시를 직접 심고 실제 Flask 테스트클라이언트로 /api/partner/login·/api/insurer/login 을 호출해 (a) 레거시 해시로도 로그인 자체는 성공하고(회귀 없음) (b) 로그인 성공 직후 DB의 password_hash 가 실제로 pbkdf2$ 형식으로 바뀌었으며 (c) 새 해시로 같은 비밀번호가 그대로 검증되고(왕복 확인) (d) 승급된 해시로 재로그인해도 정상 동작함을 확인. [5] 되돌림-증명 — DB.is_legacy_hash 를 일시적으로 '항상 아니오'로 무력화(코드를 되돌리지 않고 이 라운드가 새로 부르기 시작한 판정 함수만 꺼서 이전 상태와 동일한 효과를 재현)한 뒤 같은 시나리오를 실행해, 로그인은 여전히 성공하면서 해시는 레거시로 그대로 남는 것(=수정 전 결함 상태)을 실측 재현 확인 — 첫 실행 19/19 통과. app.py 를 고쳤으므로 재기동 필요 — 다만 이 함수는 협력사·보험사 로그인 요청마다(수시로) 실제로 호출되는 살아있는 코드경로이므로(관리자 로그인과 마찬가지로 요청마다 도는 인증 로직 그 자체이며, sweep 류처럼 예약 실행에만 걸리는 경로가 아니다) 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round521_fixes.py", "스캔 521라운드 회귀 — 전체재경매 낙찰확정(api_co_close_full, app.py:10836)에서 담당업체가 교체되는데도 피해자 안내가 통째로 빠져 있던 결함. 직접 조사(하위위임 없음) — round520이 새로 연 '형제 함수가 같은 하위 함수를 쓰면서도 사후처리 한 단계만 못 물려받는다' 유형을 이어 notify_victim()/DB.log 형제비교 축을 훑었다. 사건의 담당업체(cases.partner_id)가 확정·교체되는 경로는 넷 — ①보험사 경매낙찰 승인(api_insurer_award)·②관리자 직접 낙찰확정(api_case_award)·③보험사 1차합의 승인(api_insurer_field_agreement_decision, round515가 이미 notify_victim 추가)·④전체재경매 낙찰확정(api_co_close_full) — 인데, round515 자신의 주석(4627행 원칙 인용)이 ①·②·③ 셋만 짚고 ④는 언급조차 하지 않았다는 점에서 사각지대를 확인했다. api_co_close_full()은 원업체가 증액 변경견적을 거절·유찰시켜 열리는 전체 재경매에서 새 업체가 낙찰되면 cases.partner_id를 옛 업체에서 새 업체로 통째로 교체하는데(10977행 UPDATE), 낙찰자 통지(notify)·탈락자 통지(notify_bid_losers)는 있으면서 피해자 통지만 빠져 있었다 — 오히려 ①·②·③보다 '모르는 업체가 찾아온다'는 위험이 더 직접적으로 들어맞는다(원업체 A가 온다고 들은 피해자에게 실제로는 새 업체 B가 현장에 간다). 고침 — notify_bid_losers 호출 다음(낙찰확정 분기 안쪽, 최종 DB.log 이전)에 형제 세 경로와 같은 문구(\"복구 업체가 선정되었습니다(…). 곧 공사 일정을 안내드립니다.\")로 notify_victim(conn, co[\"case_id\"], …) 한 줄을 추가했다(새 헬퍼·새 상수 없음, 기존 notify_victim 재사용). 회귀테스트(test_scan_round521_fixes.py, 14개 검사) 신설 — [1] 소스 확인(새 블록이 notify_bid_losers 다음·최종 DB.log 이전에 정확히 있음). [2] 실행 기반 — 사건을 '시공중'(원업체 A 배정)으로 직접 앉히고 원업체가 증액을 거절한 상태를 재현한 뒤, 실제 Flask 테스트클라이언트로 전체재경매 오픈(/api/change-orders/<coid>/full-reauction)→신규업체 B 투찰(/api/partner/reauction-bids)→마감 낙찰확정(/api/change-orders/<coid>/close-full)까지 진행시켜 담당업체가 실제로 A→B로 교체되고 notifications 테이블에 피해자안내가 1건 쌓이며 문구에 새 업체명이 담김을 확인. [3] 되돌림-증명 — app.py 파일 자체는 건드리지 않고(동시 세션이 app.py를 같이 건드릴 수 있는 환경이라 round520과 같은 원칙으로 전체 소스 스왑을 피함) 이 라운드가 새로 부르기 시작한 notify_victim 호출만 런타임에 무력화해 같은 시나리오를 별도 사건으로 재실행 — 낙찰확정 자체(구조)는 그대로 성공하면서 피해자안내만 0건으로 돌아감을 확인해 이 테스트가 결함을 실제로 잡아낼 능력이 있음을 증명한 뒤 원 함수로 복원하고, 복원 후 세 번째 사건으로 다시 1건이 쌓임까지 확인 — 첫 실행 14/14 통과. app.py 를 고쳤으므로 재기동 필요 — 이 함수는 app.py 자신 안에 정의돼 있고 전체재경매 낙찰확정을 누를 때마다(수시로) 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round522_fixes.py", "스캔 522라운드 회귀 — 전체재경매 낙찰확정(api_co_close_full, app.py:10836)에서 보험사 통지(인앱 + case.awarded 웹훅)가 통째로 빠져 있던 결함. 직접 조사(하위위임 없음) — round521이 남긴 리드(같은 함수의 SELECT를 insurer_id까지 확장해야 웹훅을 보낼 수 있다)를 먼저 검증했다. 사건의 담당업체(cases.partner_id)가 확정·교체되는 경로 넷 중 담당업체를 '교체'하는 것은 ①보험사 경매낙찰 승인(api_insurer_award)·②관리자 직접 낙찰확정(api_case_award)·④전체재경매 낙찰확정(api_co_close_full) 셋뿐인데(③1차합의는 첫 배정), WEBHOOK_EVENTS(18972행)에 정의된 6개 이벤트 중 이 재낙찰을 대체할 이벤트가 따로 없어 case.awarded 가 유일한 통지 수단임을 확인 — ①·②는 in-app 통지(notify, audience_type=insurer)+deliver_webhook(case.awarded, route=경매)를 함께 보내는데 ④만 (round521이 짚은 웹훅뿐 아니라) 인앱 통지까지 둘 다 없었다(다른 경로로 보완되지 않음, 진짜 결함으로 확정). 참고로 원업체가 증액을 그대로 수락하는 api_co_decision 의 수락 분기는 업체 교체가 없어 이 웹훅 계약의 범위 밖(별도 사안, 이번 회귀 대상 아님). 고침 — api_co_close_full()의 SELECT를 'case_no, partner_id' 에서 'case_no, partner_id, insurer_id, insurer' 로 확장하고, notify_bid_losers 호출 다음(=round521 피해자안내 블록 바로 앞)에 형제 api_case_award와 정확히 같은 모양(if c.get('insurer_id'): notify(...) + deliver_webhook(...))으로 in-app 통지+웹훅을 추가했다(새 헬퍼·새 이벤트 없음, 기존 notify()/deliver_webhook() 재사용, payload 키도 형제 두 곳과 동일: partner_name/amount/status/route). 회귀테스트(test_scan_round522_fixes.py, 23개 검사) 신설 — [1] 소스 확인(SELECT 확장 + [라운드522] 블록이 notify_bid_losers 다음·round521 블록 이전에 정확히 위치, deliver_webhook·audience_type=insurer·insurer_id 가드·route=경매 전부 포함). [2] 실행 기반 — 사건을 '시공중'(원업체 A)으로 앉히고 원업체가 증액을 거절한 상태를 재현한 뒤, 실제 Flask 테스트클라이언트로 전체재경매 오픈→신규업체 B 투찰→마감(낙찰확정)까지 진행시켜 notifications(audience_type=insurer, ntype=낙찰확정) 1건과 webhook_deliveries(event=case.awarded) 1건이 실제로 쌓이고 payload에 새 업체명(4,500,000원)·status=시공중·route=경매가 정확히 담김을 확인. [3] 되돌림-증명 — app.py 파일 자체는 건드리지 않고(동시 세션이 app.py를 같이 건드릴 수 있는 환경 — round520·521과 같은 원칙) 이 라운드가 새로 부르기 시작한 두 호출(A.notify/A.deliver_webhook)만 런타임에 무력화해 같은 시나리오를 별도 사건으로 재실행 — 낙찰확정 자체(상태전이·담당업체 교체)는 그대로 성공하면서 보험사 통지·웹훅만 0건으로 돌아감을 확인해 이 테스트가 결함을 실제로 잡아낼 능력이 있음을 증명한 뒤 원 함수로 복원하고, 세 번째 사건으로 통지·웹훅이 다시 1건씩 쌓임까지 확인 — 첫 실행 23/23 통과. app.py를 고쳤으므로 재기동 필요 — 이 함수는 app.py 자신 안에 정의돼 있고 전체재경매 낙찰확정을 누를 때마다(수시로) 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round523_fixes.py", "스캔 523라운드 회귀 — app.py:_sweep_claim()(5765행, 경매마감 스윕의 리스 확보)이 sqlite3.Error 를 전혀 잡지 않던 결함. 직접 조사(하위위임 없음) — 지시받은 세 후보 중 ①manage.py CLI 서브커맨드는 round292·342·446·109·142·179·188·263·495 로 이미 극도로 두껍게 방어돼 있었고 ②repair_estimate.py 계산식도 round69·201·247·314·462 로 이미 손을 댄 상태라 둘 다 클린 — ③예약실행/스윕 스크립트의 동시성·멱등성으로 넘어가 app.py 의 sweep_* 8종과 dispatch.py 의 sweep_dispatches 를 나란히 대조하다가, '겹친 스윕을 막는' 리스(job_locks) 기전이 두 벌(app.py _sweep_claim/_sweep_release — auction_sweep, dispatch.py _claim_lease/_release_lease — dispatch_sweep) 존재함을 발견했다. _sweep_claim() 은 conn.execute(\"BEGIN IMMEDIATE\") 와 뒤이은 UPDATE 를 예외 처리 없이 그대로 실행했다 — 정확히 같은 목적의 두 형제(같은 파일의 _sweep_release, 이미 try/except sqlite3.Error 로 감쌈 / dispatch.py 의 _claim_lease, round482 가 \"이 파일의 다른 BEGIN IMMEDIATE 10곳은 전부 try/except로 감싸는데 여기만 없었다\"며 이미 고친 바로 그 결함 클래스)는 둘 다 방어돼 있는데 원조격인 이 함수만 무방비였다. 이 리스 자체가 겹친 스윕을 막는 용도라 락 경합(busy-timeout 초과, db.py BUSY_TIMEOUT_MS=8초)이 바로 이 자리에서 가장 일어나기 쉽다. 영향 경로 확인 — sweep_auctions() 를 부르는 3곳 중 manage.py cmd_sweep()·api_admin_sweep() 은 둘 다 force=True 를 넘겨 단락평가로 _sweep_claim() 자체가 호출 안 됨(예약 실행·관리자 수동 버튼은 영향 밖) — 실제로 이 함수를 호출하는 유일한 경로는 _sweep_if_due()(6850행, force 기본값 False — 관리자 대시보드·보험사 포털·협력사 공고 목록을 열 때마다 곁들여 도는 인라인 스윕, 3535·6888·20997·21025행 네 곳에서 트리거)뿐이다. 거기서 예외가 새면 같은 호출 안에 이어지는 나머지 네 스윕(sweep_no_bid_alert·sweep_report_overdue·sweep_review_reminders·sweep_warranty_expiry)까지 그 회차 전체가 통째로 건너뛰고, _LAST_INLINE_SWEEP 는 이미 갱신돼 있어 60초 동안 재시도조차 없는데, _sweep_if_due() 의 바깥 except 는 로그 한 줄 없이 삼켜 아무도 못 알아챈다. 고침 — _sweep_claim() 을 형제 두 곳과 같은 원칙으로 try/except sqlite3.Error 로 감쌌다(BEGIN IMMEDIATE 문 자체까지 try 안에 넣어 dispatch.py 형제보다 한 겹 더 방어 — 그 형제는 BEGIN IMMEDIATE 가 try 밖이라 그 문장 자체에서 나는 예외는 여전히 샌다). 실패하면 app.logger.exception() 으로 남기고(형제 스윕들의 '~점검 잠금 실패' 관례) rollback 도 자신만의 try/except 로 한 번 더 감싸(sweep_report_overdue 등 이 파일의 지배적 관례) False 를 반환한다(함수 자신의 독스트링이 이미 약속한 계약 그대로). 새 헬퍼·새 상수 없음. 회귀테스트(test_scan_round523_fixes.py, 23개 검사) 신설 — [1] 소스 확인(try: 가 BEGIN IMMEDIATE·UPDATE 보다 먼저 오고 except sqlite3.Error: 가 두 번·rollback 이 두 번·app.logger.exception 포함). [2] 실행(순수 단위) — 가짜 conn 으로 BEGIN IMMEDIATE 실패·UPDATE 실패 각각 예외 없이 False+rollback 1회+commit 0회를 확인, 대조군으로 rowcount=0(락 경합 없음)·정상성공(rowcount=1) 둘 다 회귀 없음 확인. [3] 실행(경로 통합) — 실제 스크래치 DB(DB.init_db())+진짜 job_locks 행 위에서, 진짜 커넥션을 감싸되 BEGIN IMMEDIATE 호출만 락 경합처럼 실패시키는 프록시를 A.sweep_auctions(proxy)(=_sweep_if_due 가 실제로 쓰는 호출 모양)에 넣어 마감 지난 경매가 있어도 예외 없이 claimed=False 로 물러나고 그 경매 행은 안 건드려짐을 확인. [4] 되돌림-증명 — app.py 자체는 건드리지 않고(동시 세션이 app.py를 같이 건드릴 수 있는 환경 — round520-522와 같은 원칙) 이 라운드 이전 코드 그대로(try/except 없음)를 테스트 안에 재구성해 같은 가짜 conn 에 돌려 sqlite3.OperationalError 가 그대로 새는 것을 확인 — 새 코드([2])와 대조해 이 회귀가 진짜 그 차이를 잡아냄을 증명 — 첫 실행 23/23 통과. app.py 를 고쳤으므로 재기동 필요 — 이 함수는 app.py 자신 안에 정의돼 있고, 관리자 대시보드·보험사 포털·협력사 공고 목록을 열 때마다(수시로) _sweep_if_due() 를 통해 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round524_fixes.py", "스캔 524라운드 회귀 — dispatch.py:_claim_lease()(742행, 출동수배 스윕의 리스 확보)가 \"BEGIN IMMEDIATE\" 문 자체는 여전히 try 밖에 남겨 뒀던 잔여 결함. 직접 조사(하위위임 없음) — round523이 남긴 리드(\"app.py의 sweep_* 8종 중 _sweep_claim/_sweep_release처럼 자기만의 리스(job_locks) 기전을 따로 갖고 있는 게 있는지 확인하라\")를 그대로 따라 sweep_no_bid_alert·sweep_report_overdue·sweep_review_reminders·sweep_warranty_expiry·sweep_approval_overdue·_sweep_award_approval·sweep_webhook_retries·sweep_send_notifications 8종을 전부 직접 Read로 대조했으나 전부 자기 도메인 테이블에 BEGIN IMMEDIATE로 직접 dedup을 거는 방식이지 job_locks 기반의 별도 리스는 없었다(job_locks grep 전수로도 auction_sweep·dispatch_sweep 두 벌뿐임을 재확인) — 이 리드 자체는 막다른 길로 확인됨. 그 확인 과정에서 dispatch.py의 _claim_lease()(app.py _sweep_claim의 형제, round482가 최초로 고치고 round523이 '이미 방어됨'으로 인용한 바로 그 함수)를 다시 읽다가, round523 자신의 회귀테스트(test_scan_round523_fixes.py 132행)가 이미 'dispatch.py 형제(_claim_lease)는 BEGIN IMMEDIATE 가 try 밖이라 이 지점은 더 얕게 방어된다'고 스스로 적어 두고도 그 잔여 결함은 app.py 파일 범위 밖이라며 넘기지 않은 것을 발견했다. 실제 코드 확인 — round482의 수정은 UPDATE·commit·rollback 은 try/except sqlite3.Error 로 감쌌지만 그 앞의 conn.execute(\"BEGIN IMMEDIATE\") 한 줄은 try 블록 이전에 그대로 남아 있었다(round482 자신의 회귀테스트도 job_locks 테이블을 DROP해 UPDATE만 실패시켰을 뿐 BEGIN IMMEDIATE 자체를 실패시키는 경우는 검증하지 않아 이 구멍을 못 잡았다). 영향 — db.py가 모든 커넥션에 PRAGMA busy_timeout을 걸어 두므로 다른 커넥션이 이미 RESERVED/EXCLUSIVE 락을 쥔 채 시간을 넘기면 BEGIN IMMEDIATE 문 자체가 UPDATE보다 먼저 sqlite3.OperationalError(\"database is locked\")를 던진다 — 이 예외는 호출부 sweep_dispatches()(force 인자 없이 부르는 유일한 실경로인 manage.py:1019 cmd_sweep)의 try 블록 밖에서 일어나 그대로 새어나가고, cmd_sweep()의 유일한 try(989-1032행)에도 except가 없어(finally만 있음) 그 회차의 sweep_send_notifications·sweep_webhook_retries·생존신호(job_locks cli_sweep 갱신)까지 통째로 건너뛴다 — 이 경로는 실제 Windows 작업 스케줄러가 주기적으로 pythonw.exe로 도는 cmd_sweep() 그 자체다(app.py의 관리자 수동버튼 api_admin_sweep은 force=True라 영향 밖). 고침 — dispatch.py:_claim_lease()의 conn.execute(\"BEGIN IMMEDIATE\")를 try 블록 안으로 옮겨 형제 app.py:_sweep_claim()(round523)과 정확히 같은 모양으로 맞췄고, except 블록의 rollback도 형제처럼 자신만의 try/except sqlite3.Error로 한 번 더 감쌌다. 새 헬퍼·새 상수 없음. 회귀테스트(test_scan_round524_fixes.py, 26개 검사) 신설 — [1] 소스 확인(try: 가 BEGIN IMMEDIATE·UPDATE 보다 먼저 오고 except sqlite3.Error: 가 두 번·rollback 이 두 번·[라운드524] 표식 1회). [2] 실행(순수 단위) — 가짜 conn 으로 BEGIN IMMEDIATE 실패·UPDATE 실패 각각 예외 없이 False+rollback 1회+commit 0회 확인, 대조군으로 rowcount=0(락 경합 없음)·정상성공(rowcount=1) 둘 다 회귀 없음 확인. [3] 실행(경로 통합) — 실제 스크래치 DB(DB.init_db())의 진짜 job_locks(dispatch_sweep) 행 위에서, BEGIN IMMEDIATE 호출만 락 경합처럼 실패시키는 프록시로 (a) DP._claim_lease(proxy) 직접 호출이 예외 없이 False를 반환하고 rollback이 실제로 되어 바로 다음 진짜 시도가 성공함을 확인, (b) 기한 지난 수배 행을 실제로 심고 DP.sweep_dispatches(proxy)(=cmd_sweep이 실제로 쓰는 force 생략 호출 모양)가 claimed=False로 물러나며 그 수배 행이 전혀 안 건드려짐을 확인. [4] 되돌림-증명 — dispatch.py 자체는 건드리지 않고(동시 세션이 이 파일을 같이 건드릴 수 있는 환경 — round520-523과 같은 원칙) 이 라운드 이전 실제 코드(BEGIN IMMEDIATE가 try 밖)를 테스트 안에만 재구성해 같은 가짜 conn 에 돌려 sqlite3.OperationalError가 그대로 새는 것을 확인 — 새 코드([2]-①)와 대조해 이 회귀가 진짜 그 차이를 잡아낼 능력이 있음을 증명 — 첫 실행 26/26 통과. dispatch.py는 app.py가 import하는 모듈이자 manage.py cmd_sweep()이 예약 실행(Windows 작업 스케줄러)마다 force 없이 실제로 호출하는 살아있는 코드경로이므로 재기동 필요."),
    ("test_scan_round525_fixes.py", "스캔 525라운드 회귀 — 하자 접수(api_defect_create, app.py:14543)·해피콜 기록(api_happy_call_add, app.py:18868)의 INSERT 문이 is_demo 를 채우지 않아, 이미 존재하는 데모 사건(is_demo=1)에 서버 가동 중 새로 접수하면 매번 스키마 기본값 0(실 데이터)으로 떨어지던 결함. 직접 조사(하위위임 없음) — 지시받은 네 후보(사진업로드 검증·정산 계산·통계 집계·알림 배지)를 순서대로 Read로 직접 대조했으나 사진업로드(_case_photo_quota_guard 가 3개 라우트에 공유되며 이미 일치)·정산(compute_fee/split_vat/void 가드, api_settlement_review·paid·transfer 전부 형제와 같은 void_status 방어)·알림 배지(admin/insurer/partner 세 라우트, round206 이 이미 ADMIN_FEED_SQL 과 ADMIN_OWN_SQL 을 분리)·통계집계(api_dashboard·api_stats·_insurer_statement·_resync_partner_stats — 전부 COALESCE(is_demo,0)=0 과 SAVE_BASE_SQL·CASE_AMOUNT_SQL 을 형제 자리와 일치)는 이미 여러 라운드에 걸쳐 다층 방어가 있어 클린 판정했다. 네 후보 밖으로 넓혀 partner_rating()(협력사 평점, app.py:14440)을 다시 보다가, 이 함수의 두 읽기 질의가 전부 COALESCE(is_demo,0)=0 으로 defects·happy_calls 를 거른다는 것과 db.py:_backfill_child_is_demo() 가 여러 자식표에 is_demo 를 사건에서 캐스케이드한다는 것을 확인했는데, 이 백필은 db.migrate()(서버 기동 시 1회)에서만 불리고 app.py 안에는 호출이 전혀 없었다(grep 전수 확인) — 즉 가동 중 실시간으로 생기는 새 자식 행은 각 INSERT 자신이 is_demo 를 채워야 한다. 실제로 이 원칙은 이미 두 군데서 지켜지고 있었다 — ① bids(app.py:5277·5481, \"데모 표식을 사건에서 물려받아 여기서 채운다\", INSERT 문에 COALESCE((SELECT c.is_demo FROM auctions a JOIN cases c ...),0) 서브쿼리) ② notify()(app.py:1870, 40여 곳 호출부를 대신해 이 함수 하나가 case_id 로 다시 조회해 is_demo 를 채움, \"호출부가 40곳 넘으므로 각자 채우게 두지 않는다\"). 그런데 형제인 defects·happy_calls 의 INSERT 문(호출부가 각 1곳뿐이라 공유 관문조차 없음)은 둘 다 is_demo 컬럼이 아예 없어 스키마 기본값(DEFAULT 0)으로 떨어졌다 — round106 은 partner_rating() 의 읽는 쪽에 is_demo 필터를 추가하며 \"형제인 happy_calls 질의는 이미 걸러낸다\"고 적었지만 그 채우는 쪽이 서버 기동 시점 일괄보정뿐이라는 점은 그 라운드도, 이후 defects/happy_calls 를 손댄 round140·round433(각각 평점감점표·severity검증우회·고아행정리가 목적이라 이 INSERT 문 자체는 안 봄)도 확인하지 않아 지금까지 살아남았다. 영향 — 관리자 콘솔에서 이미 존재하는 데모 사건에(두 라우트 모두 case_id/cid 의 is_demo 를 확인하지 않는다) 하자를 접수하거나 해피콜을 기록하면 다음 서버 재기동 전까지 그 행이 실 데이터로 잡혀 partner_rating()·_bid_scores()(진행 중인 경매의 낙찰점수 하자 감점, app.py:11332)·api_defects_summary()·api_happy_calls() 의 실협력사 집계에 그대로 섞인다 — 데모 사건 하나가 실제 낙찰 결과를 바꿀 수 있다. 고침 — 두 INSERT 문 모두에 is_demo 컬럼을 추가하고 이미 조회해 둔 사건 행의 c[\"is_demo\"](정수 캐스팅)를 그대로 넣었다(bids·notify() 와 같은 원칙, 호출 지점이 각 1곳뿐이라 새 공유 헬퍼는 만들지 않음). api_happy_call_add() 는 기존 SELECT 목록에 is_demo 가 없어 함께 추가했다. 새 상수 없음. 회귀테스트(test_scan_round525_fixes.py, 15개 검사) 신설 — [1] 소스 확인(두 INSERT 컬럼 목록에 is_demo 추가, c[\"is_demo\"] 대입, happy_call SELECT 확장). [2]~[4] 실행 기반 — 실제 스크래치 DB(DB.init_db())+admins 표 실계정 위에서 진짜 Flask 테스트클라이언트로 /api/defects·POST /api/cases/<cid>/happy-call 을 호출해, 데모 사건(is_demo=1)에 접수한 하자·해피콜은 is_demo=1 로 저장되고 대조군(실사건, is_demo=0)은 여전히 is_demo=0 으로 저장됨을 확인(과잉수정이 아님도 함께 검증). [5] 되돌림-증명 — app.py 자체는 건드리지 않고(동시 세션이 이 파일을 같이 건드릴 수 있는 환경 — round520-524 와 같은 원칙, 이 저장소는 git 이 없어 파일 스왑 방식은 위험이 더 크다고 판단) 라운드525 이전 실제 INSERT 문 원문(is_demo 컬럼이 아예 없던 코드, 수정 직전 이 세션이 직접 Read 로 확인한 텍스트)을 문자열로만 재구성해 같은 데모 사건에 직접 실행 — 새 코드([2]~[4])는 is_demo=1인데 옛 코드(재구성)는 is_demo=0으로 떨어지는 차이를 실측해 이 회귀가 진짜 그 차이를 잡아낼 능력이 있음을 증명 — 첫 실행 15/15 통과. app.py 를 고쳤으므로 재기동 필요 — 이 두 함수는 app.py 자신 안에 정의돼 있고, 관리자가 하자를 접수하거나 해피콜을 기록할 때마다(수시로) 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round526_fixes.py", "스캔 526라운드 회귀 — settlements(api_case_approve)·auctions(원경매를 여는 _open_original_auction·재경매를 여는 _open_reauction·낙찰취소 폴백인 api_case_cancel_award 내부, 3곳)·schedule_events(api_schedule_event_add)의 실시간 INSERT 문 5곳 전부가 사건의 is_demo 를 못 물려받던 결함 — round525(defects·happy_calls)와 정확히 같은 축의 잔여 3표. 직접 조사(하위위임 없음) — 지시받은 리드(db.py 의 _CHILD_DEMO_SQL 이 나열하는 9개 자식표를 전부 대조하라)를 그대로 따랐다. bids·dispatches·field_agreements·notifications 는 이미 실시간 INSERT 에서 정상 캐스케이드됨을 직접 확인했고(dispatch.py 의 open_dispatch·assign_dispatch·open_agreement 3곳 모두 COALESCE((SELECT is_demo FROM cases WHERE id=?),0) 서브쿼리, notify() 는 case_id 로 재조회), round525가 막 고친 defects·happy_calls 를 제외한 나머지 셋(settlements·auctions·schedule_events)을 Read 로 대조하니 셋 다 round525 이전 defects·happy_calls 와 정확히 같은 모양 — is_demo 컬럼 자체가 INSERT 문에 없어 스키마 기본값 0(실 데이터)으로 떨어졌다. 이 셋은 db.py 자신의 주석이 이미 '유일한 생성 지점이 이 컬럼을 아예 안 채운다'고 못박아 뒀는데(settlements: 1692행 round96 주석 · auctions: 1715행 round116 주석 · schedule_events: 1726행 round122 주석) 그 라운드들은 db.py 의 백필(_CHILD_DEMO_SQL, 서버 기동 시 1회)만 추가했을 뿐 app.py 의 실시간 INSERT 자체는 그 뒤로 아무도 고치지 않았다 — round525가 '백필은 가동 중 실시간 INSERT 를 못 고쳐 준다'는 구분을 처음 명시했는데 db.py 안에 나란히 적힌 이 세 형제 주석은 그때도 안 보고 넘어간 것이다. 영향 — 이미 존재하는 데모 사건에 대해 가동 중(=다음 재기동 전까지) 검수 승인을 누르거나 낙찰을 취소해 경매를 재개설하거나 변경견적 추가경매/전체재경매를 열거나 수동 일정을 등록하면 그 새 행이 실 데이터로 잡힌다 — settlements 는 관리자 대시보드(GMV·수수료합계·검수대기건수)·보험사 명세서(_insurer_statement)·go-live 삭제 미리보기가 전부 COALESCE(is_demo,0)=0 으로 거르므로 데모 정산 1건이 실매출 지표에 그대로 섞인다(db.py round96 주석이 '넷 중 어느 것보다 재무적으로 더 무겁다'고 이미 적어 둔 표), auctions 는 협력사 공고 목록·마감 스윕·견적엔진 표본에 데모 경매가 노출된다. 고침 — 다섯 INSERT 문(settlements 1곳·auctions 3곳·schedule_events 1곳) 전부에 is_demo 컬럼을 추가했다. settlements 는 이미 조회해 둔 사건 행 c 가 있어 round525 와 같은 원칙(int(c[\"is_demo\"] or 0))을 그대로 썼고, auctions 3곳과 schedule_events 는 cid(또는 case_id)만 갖고 있어 형제 dispatch.py 가 이미 쓰는 서브쿼리 원칙 COALESCE((SELECT is_demo FROM cases WHERE id=?),0) 을 그대로 따랐다 — schedule_events 는 case_id 가 NULL(사건과 무관한 일반 일정)이면 서브쿼리가 못 찾아 자동으로 0이 되므로 db.py _CHILD_DEMO_SQL 의 schedule_events 백필과 의도가 정확히 같다. 새 헬퍼·새 상수 없음. 회귀테스트(test_scan_round526_fixes.py, 32개 검사) 신설 — [1] 소스 확인(5곳 전부 is_demo 컬럼·값 표현식 확인). [2]~[7] 실행 기반 — 실제 스크래치 DB(DB.init_db())+admins 표 실계정 위에서 _open_original_auction()·_open_reauction() 은 내부 함수로 직접 호출, 낙찰취소 폴백·검수승인·일정등록은 진짜 Flask 테스트클라이언트로 실제 라우트를 호출해 데모 사건(is_demo=1)에서 만들어진 새 행은 전부 is_demo=1, 대조군(실사건)은 전부 is_demo=0, case_id 없는 일정은 과잉수정 없이 0으로 저장됨을 확인. [8] 되돌림-증명 — app.py 자체는 건드리지 않고(동시 세션이 이 파일을 같이 건드릴 수 있는 환경 — round520-525 와 같은 원칙) 라운드526 이전 실제 INSERT 문 3종(settlements·auctions·schedule_events, 수정 직전 이 세션이 직접 Read 로 확인한 원문)을 문자열로만 재구성해 같은 데모 사건에 직접 실행 — 새 코드는 is_demo=1인데 옛 코드(재구성)는 전부 0으로 떨어지는 차이를 실측해 이 회귀가 진짜 그 차이를 잡아낼 능력이 있음을 증명 — 첫 실행 32/32 통과. app.py 를 고쳤으므로 재기동 필요 — 다섯 함수(api_case_approve·_open_original_auction·_open_reauction·api_case_cancel_award·api_schedule_event_add) 전부 app.py 자신 안에 정의돼 있고 검수 승인·낙찰취소·변경견적 경매 개설·수동 일정 등록을 누를 때마다(수시로) 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round527_fixes.py", "스캔 527라운드 회귀 — 1차합의 승인(api_insurer_field_agreement_decision, app.py:18134)에서 CP.record_gate() 가 sqlite3.Error 가 아닌 예외로 실패하면 도급 적법성 판정 기록이 통째로 안 남는데도 아무에게도 알려지지 않던 결함. 직접 조사(하위위임 없음) — 지시받은 후보(도급 적법성 검사 완전성 축, round521·522의 '피해자안내·보험사웹훅' 축과는 다른 각도)를 따라 담당업체가 확정되는 다섯 자리(경매·보험사=api_insurer_award·경매·관리자=api_case_award·변경견적수락=api_co_decision·전체재경매=api_co_close_full·1차합의=api_insurer_field_agreement_decision) 전부에서 CP.record_gate() 호출이 있는지부터 grep 전수 대조했는데 다섯 곳 모두 이미 호출은 있었다(round57·521·522 등이 '형제 몇 곳엔 있는데 여기만 없다'류는 이미 다 잡아 놓음) — 그래서 '호출이 있는가'가 아니라 '그 호출이 실패하면 어떻게 되는가'로 각도를 옮겨 다섯 함수의 트랜잭션 경계를 직접 대조했다. 형제 넷은 함수 시작에서 BEGIN IMMEDIATE 로 트랜잭션을 열고 _gate_alert(..., CP.record_gate(...)) 를 그 안에서 예외처리 없이(api_case_award 는 명시적으로 except Exception: conn.rollback(); raise, 나머지 셋 api_insurer_award·api_co_decision·api_co_close_full 은 try/except 자체가 없음) 부른다 — 안에서 예외가 나면 담당업체 배정 UPDATE 자체가 아직 커밋 전이라 함께 롤백되거나(명시적 rollback) 그대로 새어나가 전역 오류핸들러(app.py:1236 err_500)의 _cleanup_conns(rollback=True) 가 되돌린다. 즉 '계약은 성립했는데 소명 기록만 없다'는 상태 자체가 이 넷에서는 구조적으로 나올 수 없다. 1차합의 경로만 다르다 — 사건 배정(status=시공중·partner_id 확정)이 DP.settle_agreement() 안에서 일어나는데 그 함수는 자기 트랜잭션을 스스로 커밋한다(dispatch.py:1188 BEGIN IMMEDIATE ~ 1334 conn.commit()), app.py 쪽은 이 함수를 부르기 전에 별도로 BEGIN IMMEDIATE 를 걸지 않는다(걸면 '트랜잭션 안에서 트랜잭션 시작' 으로 즉시 깨진다). 그 뒤에 _record_outcome·_gate_alert(CP.record_gate(...)) 를 부르는데 이 호출들은 settle_agreement() 가 이미 커밋한 뒤에 실행되고 게다가 except Exception: app.logger.exception(...) 으로 감싸여 있다 — 여기서 예외가 나도 이미 성립된 계약은 되돌릴 방법이 없고(디스크에 이미 있다) 그 except 는 서버 로그(상시 감시 없음)에만 흔적을 남기고 끝난다. record_gate() 자신의 독스트링(compliance.py:451)이 '판정을 막는 함수가 아니다'라고 이미 명시하므로 계약을 막지 않는 설계 자체는 맞다 — 문제는 _gate_alert() 가 record_gate 자신의 실패(sqlite3.Error, res[\"_log_failed\"])에는 이미 운영팀 알림(notify, 3898행)을 주는데, gate()/check_direct_contract() 내부의 sqlite3.Error 가 아닌 예외(프로그래밍 버그 등, record_gate 자신의 try/except 는 sqlite3.Error 만 잡음)로 그 알림 함수 자신이 호출되기도 전에 예외가 나는 경우에는 이 원칙이 안 미친다는 점이다. 영향 — 1차합의는 app.py 18209행 자신의 주석대로 '소액 직접 도급의 본류'라 실사용 빈도가 형제 넷보다 높은데, 그 확정 순간 CP.record_gate() 가 위와 같은 이유로 실패하면 계약(시공중 배정)은 정상 성립하고 보험사에게는 200 ok:True 가 돌아가지만 contract_gate_log 에는 그 확정의 소명 스냅샷이 영원히 안 남고 그 사실을 아무도 모른다 — 나중에 '왜 등록 없이 이 금액을 직접 도급했는지'(경미한 건설공사 예외의 법적 근거)를 증명해야 하는 순간 근거가 아예 없는데도 어드민 화면 어디에도 그 사실이 드러나지 않는다. 고침 — 그 except 블록 안에 _gate_alert() 가 record_gate 자신의 실패에 이미 주는 것과 같은 무게의 운영팀 알림(notify(ntype=\"도급판정\", audience_type=\"admin\"))과 활동로그(DB.log)를 추가했다(기존 함수만 재사용, 새 헬퍼·새 상수 없음) — 이 알림 자체가 실패해도 이미 성립된 승인을 실패로 되돌리지 않도록 안쪽에 자기만의 try/except 를 한 겹 더 둔다(바깥쪽 except 하나만으로는 알림 실패가 그대로 500 으로 샐 수 있었다). 회귀테스트(test_scan_round527_fixes.py, 23개 검사) 신설 — [1] 소스 확인(새 블록이 기존 except 안ㆍ[라운드527] 표식 아래ㆍ그다음 '낙찰' 알림 이전에 정확히 있고 자기 자신의 try/except 로 한 번 더 감싸져 있음, 형제 넷의 트랜잭션 경계도 함께 소스에서 대조: api_insurer_award·api_co_decision·api_co_close_full 은 try/except 전무, api_case_award 는 except Exception: conn.rollback(); raise). [2] 실행 기반 — 실제 스크래치 DB(DB.init_db())+진짜 Flask 테스트클라이언트로 사건접수→출동→도착→1차합의개시→보험사승인까지 실제로 진행시키되 CP.record_gate() 를 RuntimeError 로 몽키패치해(sqlite3.Error 가 아닌 실패 재현) 승인 자체는 여전히 200/성공, 사건도 실제로 '시공중' 배정, contract_gate_log 는 0건인 채로 notifications 에 운영팀 대상 '도급판정' 알림이 실제로 1건(문구에 사건번호·'1차합의' 포함) 쌓이고 activity_log 에도 1건 남음을 확인. [3] 되돌림-증명 — app.py 파일 자체는 건드리지 않고(동시 세션이 이 파일을 같이 건드릴 수 있는 환경, round520 이후와 같은 원칙) 이 라운드가 새로 부르기 시작한 그 notify() 호출 한 줄만(문구로 특정) 런타임에 무력화해 같은 시나리오를 새 사건으로 재실행 — 승인 자체(구조)는 그대로 성공하면서 '도급판정' 알림만 0건으로 돌아감을 확인해 이 회귀가 실제로 결함을 잡아낼 능력이 있음을 증명한 뒤 원 함수로 복원하고 세 번째 사건으로 알림이 다시 1건 쌓임까지 확인. [4] 형제 대조 — 같은 CP.record_gate 결함 주입을 api_insurer_award(보험사 경매 낙찰)에도 그대로 적용해 그 경로는 승인 자체가 500 으로 실패하고 사건이 롤백되어 '입찰중'·업체 미배정 그대로 남는 것을 실측 확인 — '계약은 성립했는데 기록만 없다'는 상태가 1차합의에서만 가능하고 형제 경로는 구조적으로 그 상태에 도달할 수 없음을 대조로 증명 — 첫 실행 23/23 통과. app.py 를 고쳤으므로 재기동 필요 — 이 함수는 app.py 자신 안에 정의돼 있고 보험사가 1차합의(현장 실견적)를 승인할 때마다(수시로, 이 경로 자신의 주석대로 '소액 직접 도급의 본류') 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round528_fixes.py", "스캔 528라운드 회귀 — 웹훅 \"테스트\" 버튼(api_insurer_webhook_test, app.py:9175)이 데모 발주처(insurers.is_demo=1)에도 실제 webhook_url 로 그대로 나갈 수 있던 결함. 직접 조사(하위위임 없음) — 지시받은 후보 ②(웹훅 재시도 로직의 재시도상한·백오프·영구실패 판정)를 먼저 실측(실제 sqlite3 로 date() 월가산의 실제 동작·sweep_webhook_retries 의 attempts²(1·4·9·16분) 백오프 간격·선-CAS·전송시점 재검증까지 전부 코드와 직접 대조)했으나 이미 round84·144·200·412 가 촘촘히 막아 놓아 클린으로 확인, 후보 ①(notifications 만료·보관 정책)도 sweep_* 함수 전수 확인 결과 자체 정리 로직 자체가 아예 없어(activity_log 와 같은 부류라 새로 제안하지 않음) 조사를 접었다. 그래서 앱 전체를 라우트 단위로 스캔해 '라운드 감사 흔적이 전혀 없는 함수'를 찾는 기계적 접근(221개 라우트 전수 — 데코레이터부터 다음 정의 앞까지의 본문에 \"라운드\" 문자열이 단 한 번도 없는 함수만 추출해 금액·승인·삭제·확정 키워드로 우선순위)으로 전환했다 — api_settlement_void 등 유력해 보이던 후보들은 형제(paid·review·transfer·undo)와 대조해 보니 이미 모든 상태전이 가드가 정확했고(정산계산 축은 포화 처리), 최종적으로 api_insurer_webhook_test 에서 결함을 확인했다. deliver_webhook()(모든 웹훅의 유일한 공유 관문 — round97 이 '데모 사건은 절대 실제 서버로 안 나간다'를 지킨 바로 그 함수)의 데모 판정은 `SELECT is_demo FROM cases WHERE case_no=?` 하나뿐이라 사건이 실제로 존재해야만 걸리는데, api_insurer_webhook_test 는 사건과 무관하게 발주처 자신의 연동만 확인하는 진단 기능이라 case_no=\"TEST-0000\"(실제 cases 행이 아닌 고정 문자열)으로 deliver_webhook 을 부른다 — 그 결과 위 조회는 항상 빈 값이 되어 사건 쪽 데모 검사가 이 호출에 대해서만 구조적으로 절대 못 걸리고, 발주처 자신이 데모(insurers.is_demo=1)여도 webhook_url·api_enabled 만 채워져 있으면 실제 HTTP POST 가 그대로 나간다(round97 이 막은 '8개 이벤트 자리' 목록에 이 진단 호출은 애초에 포함되지 않았던 사각지대). 운영DB 를 직접 조회해 확인(읽기전용 mode=ro) — 지금 데모 발주처 6곳(id 1~6)은 전부 webhook_url·api_enabled 가 비어 있어 오늘 당장 새고 있는 건 아니지만, 막는 코드가 없으니 다음에 누군가 데모 발주처의 그 칸을 채우는 순간부터(예: 웹훅 기능 자체를 데모로 시연·점검할 때) 조용히 실제 외부 주소로 HTTP 가 나간다. 고침 — deliver_webhook() 의 insurers 조회에 is_demo 컬럼을 추가하고, 조회한 발주처 자신이 데모면 사건 유무와 무관하게 enabled 를 꺼서 기존 4개 상태값 중 '미설정'으로 막는다(round97 과 같은 함수·같은 상태값 재사용, 새 상태값 없음 — 이 관문 하나만 고쳐 9개 호출 지점 전부에 자동으로 적용된다). api_insurer_webhook_test 에도 이 함수 자신이 이미 갖고 있던 원칙(\"안 보내 놓고 보냈다고 하지 않는다\", 바로 아래 API_DISABLED·INSURER_NOT_ACTIVE 두 사전차단과 같은 자리·같은 문체)으로 INSURER_IS_DEMO(409) 사전 차단을 추가해, 화면이 조용히 ok:True 를 받는 대신 명확한 사유를 보게 했다. 새 헬퍼·새 상수 없음(기존 SELECT·if 문 확장뿐). 회귀테스트(test_scan_round528_fixes.py, 16개 검사) 신설 — [1] 소스 확인(두 함수 모두 is_demo 조회·조건문·INSURER_IS_DEMO 코드가 정확한 순서로 있음, round97 방어가 그대로 남아 있음). [2]~[3] 실행 기반 — 실제 스크래치 DB(DB.init_db())+진짜 Flask 테스트클라이언트로 데모·실보험사 두 곳을 만들어 deliver_webhook() 직접 호출과 실제 라우트 호출 양쪽에서 데모 발주처는 '미설정'/409·배송이력 미생성·_webhook_send() 미호출까지 확인하고 실보험사는 과잉차단 없이 정상 동작함을 대조 확인(_webhook_send 는 실네트워크 없이 스텁으로 교체해 example.com 등 외부 의존 없이 검증). [4] 되돌림-증명 — app.py 파일 자체는 건드리지 않고(동시 세션이 이 파일을 같이 건드릴 수 있는 환경, round520 이후 표준 관례) 이 라운드 직전의 실제 deliver_webhook 본문(수정 직전 이 세션이 Read 로 확인한 원문)에서 insurers.is_demo 검사 두 줄만 뺀 것을 테스트 안에 문자열로 재구성해 같은 시나리오(사건 없는 case_no)에 직접 실행 — 옛 코드는 이 데모 발주처를 '대기'(발송 큐)로 그대로 올리는 반면 지금 코드(위 [2])는 같은 입력에서 '미설정'임을 실측 대조해 이 회귀가 실제로 결함을 잡아낼 능력이 있음을 증명 — 첫 실행 16/16 통과. app.py 를 고쳤으므로 재기동 필요 — deliver_webhook·api_insurer_webhook_test 둘 다 app.py 자신 안에 정의돼 있고 웹훅 발송·웹훅 테스트 버튼을 누를 때마다 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round529_fixes.py", "스캔 529라운드 회귀 — 피해자 안내 적재(notify_victim, app.py:19469)가 sqlite3.Error 를 로그 한 줄 없이 삼키던 결함. 직접 조사(하위위임 없음) — round528 과 같은 기계적 스캔(데코레이터~다음 def 사이에 '라운드' 문자열이 없는 함수 전수 추출)을 라우트 221개뿐 아니라 최상위 헬퍼 함수까지 넓혀 다시 뽑고(라우트 126개 후보는 재확인해 형제와 일치함을 재검증), 호출 빈도로 우선순위를 매겼다. notify_victim() 은 낙찰확정(4666행)·변경견적(11115)·경매 낙찰(11599)·완료보고(11806)·직접배정(18261)·조회링크 발급(19464) 6곳에서 불리는, 피해자에게 나가는 문자를 발송대기함에 적재하는 유일한 공유 관문인데 본문 전체가 `except sqlite3.Error: pass` 로만 감싸여 있었다 — 형제 함수 _dispatch_notify(내부 콜백, 17346행)가 이미 겪고 고친 것과 정확히 같은 모양이다. 그 형제의 수정 코멘트가 스스로 적어 둔 두 가지 잘못(① c 미방어로 인한 이중삼킴 ② 로그 없이 삼켜 콜 0건 사실이 안 남음) 중 notify_victim 은 ①은 이미 `if not c` 로 방어돼 있어 없었지만 ②는 그대로 갖고 있었다. 실제 영향 — notify() 내부 INSERT 가 DB 잠금 등 어떤 이유로든 sqlite3.Error 를 내면 notify_victim 은 아무 흔적 없이 조용히 넘어가는데, 조회링크 발급 라우트(api_track_link, 19007행)는 notify_victim 호출 직후 무조건 sent=True 를 찍어 화면에 '안내 예약'이라 답한다 — 실제로는 발송대기함에 아무것도 안 쌓였는데 운영자는 보낸 줄 알고 넘어간다. notify() 자기 자신은 같은 종류의 실패(1884행, 데모표식 조회 실패)에 이미 app.logger.exception 을 쓰므로 그 형제 관례를 그대로 맞췄다. 고침 — 예외를 여전히 밖으로 올리지 않는다(주 업무 흐름은 이 함수 실패로 깨지면 안 된다는 원래 설계·docstring 그대로 유지, api_track_link 등 6개 호출부의 응답 의미는 바꾸지 않는다) — except 블록 안에서 app.logger.exception() 으로 실패 사실만 남긴다(새 헬퍼·새 상수 없음, notify() 1884행과 같은 관례 재사용). 회귀테스트(test_scan_round529_fixes.py, 14개 검사) 신설 — [1] 소스 확인(except 블록이 여전히 예외를 안 올리면서 app.logger.exception 호출이 그 블록 몸통 안에 있음). [2] 실행 기반 — 실제 스크래치 DB(DB.init_db())로 정상 경로(연락처 있음·conn 정상)는 그대로 1건 적재되고 로그도 안 남아 과잉수정이 아님을 확인. [3] 실행 기반 — 몽키패치가 아니라 실제로 닫은 커넥션에 conn.execute() 를 던져 진짜 sqlite3.ProgrammingError(Error 의 서브클래스) 를 자연발생시켜, notify_victim() 이 예외를 여전히 안 올리면서(주 흐름 보호 유지) app.logger.exception 으로 사건id 를 포함한 로그를 실제로 남김을 확인. [4] 실행 기반(라우트) — 진짜 Flask 테스트클라이언트로 POST /api/cases/<cid>/track-link 를 부르되 notify() 를 sqlite3.OperationalError('database is locked')로 몽키패치해 실패를 재현 — 라우트는 여전히 200/ok:True/has_phone:True 를 그대로 돌려주면서(원래 설계대로 주 흐름 안 깨짐) 로그에는 실패가 남고, notifications 테이블에는 실제로 0건이 추가돼(응답의 '안내 예약'과 정반대) 그 간극이 로그 없이는 아무도 못 보던 부분임을 실측. [5] 되돌림-증명 — app.py 자체는 건드리지 않고(동시 세션이 같은 파일을 건드릴 수 있는 환경, round520 이후 표준 관례) 수정 직전 이 세션이 Read 로 확인한 원문(app.logger.exception 없이 pass 만 있는 버전)을 테스트 안에 문자열로만 재구성해 같은 닫힌 커넥션 시나리오에 직접 실행 — 옛 코드도 예외는 똑같이 안 올리지만(그래서 지금까지 안 들켰다) 로그를 단 한 줄도 안 남기는 차이를 실측 대조해 이 회귀가 실제로 결함을 잡아낼 능력이 있음을 증명 — 첫 실행 14/14 통과. 전체 배터리 1차 실행에서 이 라운드 자신이 회귀 1건을 냈다 — 새 except 블록 주석(호출부 나열)에 '경매 낙찰'이라는 표현을 썼는데, 형제 검사(test_feature_victim_track.py [7] '문자에 금액을 적지 않는다')가 notify_victim() 의 함수 소스 전체(주석 포함)에서 '낙찰' 문자열 자체가 있는지를 본다 — 실행 코드가 아니라 **주석 텍스트**가 이 가드에 걸린 것이다. '경매 낙찰'을 실제 그 알림 문구('복구 업체가 선정되었습니다')에 맞춘 '업체선정'으로 바꿔 해결(의미 변화 없음) — 재실행해 그 형제 테스트가 37/37로 복귀함을 확인. 이 자체가 배터리를 실제로 끝까지 돌려 봐야 하는 이유를 보여준다(소스 확인·단위 실행만으로는 이 클래스의 형제 회귀를 못 잡는다). app.py 를 고쳤으므로 재기동 필요 — notify_victim 은 app.py 자신 안에 정의돼 있고 낙찰·변경견적·완료보고·직접배정·조회링크 발급 등을 누를 때마다(수시로) 실제로 호출되는 살아있는 코드경로이므로 재기동 없이는 이 수정이 반영되지 않는다."),
    ("test_scan_round530_fixes.py", "스캔 530라운드 회귀 — app.py 전체에서 통째로 사라졌던 마감판정 상수 5개(MIN_BIDDERS_DEFAULT·LOW_PRICE_ALERT_DEFAULT·AUCTION_HOURS_DEFAULT·REAUCTION_HOURS_DEFAULT·AUCTION_EXPIRED_SQL) 복원. 직전 529라운드가 배터리 반복실행 중 무관한 다수 테스트가 동시에 실패하는 현상을 발견하고 AUCTION_EXPIRED_SQL·REAUCTION_HOURS_DEFAULT·MIN_BIDDERS_DEFAULT 세 이름의 미정의를 원인으로 지목했으나, 동시편집 중인 다른 세션 소유일 가능성 때문에 손대지 않고 재기동을 보류했다. 이번 라운드가 직접 재조사(하위위임 없음) — grep이 아니라 AST로 app.py 전체의 Load/Store 바인딩을 대조해 대상이 세 개가 아니라 다섯 개임을 확인했다(AUCTION_HOURS_DEFAULT·LOW_PRICE_ALERT_DEFAULT 도 같은 삭제사고의 일부, 3782~3794행 네 헬퍼가 나란히 참조). bokguon.log 의 당일 라이브 트레이스백에서 이 다섯 이름 전부의 NameError 를 실측(다른 동시 세션이 띄운 서버가 같은 파일을 물고 있었다는 뜻). 복원값은 창작이 아니라 db.py 의 독립된 두 설정 시드(1541·2143행, 서로 다른 시점에 각각 auction_hours=48·reauction_hours=24·min_bidders=3·low_price_alert=20 을 명시)와 app.py 5917행(sweep_auctions 내부)에 별칭만 붙은 채 그대로 남아있던 같은 판정식의 인라인 사본에서 역산했다. 복원 과정에서 새 결함도 하나 잡았다 — AUCTION_EXPIRED_SQL 을 괄호 없이 'A AND B' 형태로만 넣었다면 NOT{AUCTION_EXPIRED_SQL} 호출부 3곳(10537·10857·20411행, 마감 전 강제진행 확인 게이트)이 SQL의 NOT이 AND보다 우선순위가 높은 특성 때문에 조용히 항상 거짓으로 평가돼 그 가드가 영구히 무력화됐을 것이다 — 회귀테스트([3]단계)가 이 정확한 실패를 먼저 재현해 잡아냈고 괄호를 추가해 고쳤다(스스로 낸 회귀를 스스로 잡은 사례). 회귀테스트(test_scan_round530_fixes.py, 18개 검사) 신설 — [1] 소스: 다섯 상수가 전부 정의됐음을 grep이 아니라 AST 바인딩 분석으로 확인. [2] 실행 기반 — 실제 스크래치 DB(DB.init_db())로 네 헬퍼(_min_bidders 등)를 직접 호출해 NameError 없이 돌고 db.py 시드값과 일치함을 확인. [3] 실행 기반 — 원경매를 실제로 열어(_open_original_auction 경유로 AUCTION_HOURS_DEFAULT 도 같이 태움) AUCTION_EXPIRED_SQL 이 미래/과거 마감을 긍정형·NOT 부정형 양쪽 다 올바르게 가름을 대조. [4] 실행 기반 — sweep_auctions() 를 force=True로 실제 호출해(MIN_BIDDERS_DEFAULT+AUCTION_EXPIRED_SQL 이 한 경로 안에서 동시에 쓰인다) NameError 없이 끝까지 돌아 입찰 1건(최소성립 미달)짜리 사건이 자동유찰이 아니라 '승인대기'로 정확히 전환됨을 확인 — 첫 실행 18/18 통과. app.py 자신의 라이브 코드경로(입찰 마감판정 8곳 전부 포함)를 고쳤으므로 재기동 필요."),
    ("test_scan_round532_fixes.py", "스캔 532라운드 회귀 — run_all_tests.py:run()(모든 회귀 파일을 실제로 스폰하는 유일한 공유 지점, UNIT·HTTP·STANDALONE 세 목록 전부가 이 함수 하나를 공유)이 자식에게 PYTHONIOENCODING 을 안 넘겨, 이 값을 우연히도 갖고 있지 않은 셸(이 세션의 Bash 도구 등)로 배터리를 돌리면 실제 결함과 무관하게 회귀 파일 대다수가 UnicodeEncodeError 로 거짓 FAIL 되던 결함. 직접 조사(하위위임 없음) — 지시받은 6개 후보(알림 재시도 큐·파일 정리 경로·타임존 경계·페이지네이션 상한·관리자 등급 경계·협력사 탈퇴 정합성)를 전부 실측 대조했으나 전부 클린이었다(알림은 round84·144·200·232·262·412 가 이미 CAS+request_id+최종알림까지 촘촘, 사진 파일 정리는 case 취소 두 경로 다 photo 가 생기기 전 단계에서만 취소 가능해 원천적으로 무관, 타임존은 round68·419 가 app.py·db.py 전체를 이미 KST-aware 로 통일하고 다른 8개 모듈도 date.today() 포함 재확인 결과 잔여 없음, 엑셀 6곳+CSV 1곳 전부 상한·수식주입 방어(_xl_safe/_csv_safe) 통일, 최고관리자 경계는 데코레이터 21곳+인라인 체크 전부 일관, exit gate 는 round136·437·476·505 로 이미 촘촘). 그래서 각도를 'app.py 안의 새 결함'에서 '이 라운드들의 결과를 실제로 증명하는 배터리 자체가 믿을 만한가'로 옮겨 --quick 배터리를 실제로 동기 실행해 보니 report() 최종 실패 목록에 round166 부터 round526 대(기능 회귀 8개 포함)까지 거의 전부가 찍혔다 — round166 을 단독 실행해 좁혀 보니 4번째 줄 print() 에서 UnicodeEncodeError('\\u2014' em dash)로 즉사, round250·300·500 도 같은 지점에서 같은 예외로 재현돼 round 번호와 무관한 공통 원인임을 확인했다. 근본원인 — run()이 `_env = dict(os.environ)`로 현재 프로세스 환경만 물려주는데, 자식은 capture_output=True 라 콘솔이 전혀 없는 순수 파이프 stdout 을 받아 PYTHONIOENCODING 이 없으면 파이썬이 OS 로케일(이 서비스가 도는 한국어 윈도의 cp949)로 그 파이프를 연다 — 자체 sys.stdout.reconfigure() 방어가 있는 최신 파일(round528~530 등 일부)만 살아남고 나머지 다수(회귀 파일 400여 개 중 절대다수)는 첫 em dash 에서 죽는다. 이 PC 의 PowerShell $프로필이 우연히 PYTHONIOENCODING=utf-8:surrogateescape 를 갖고 있어 사람이 PowerShell로 돌리면 안 드러나지만(부모 run_all_tests.py 자신도 이 세션의 Bash 도구가 제공하는 채널 덕에 별문제 없이 진행되는 것으로 실측), 그 프로필을 안 읽는 셸(Bash 도구·예약작업·CI·새 사용자 프로필)로 돌리는 순간 자식 전부가 이 이유 하나로 대량 거짓 FAIL 을 낸다 — round518·519 가 '이 저장소의 단독 실행 CLI 27개+6개가 cp949 콘솔에서 죽는다'를 이미 파고들어 각 파일에 개별 방어를 심었지만 그 조사범위는 독립 CLI 도구였지 이 실행기 자신의 자식-스포너는 다루지 않은 사각지대였다. 고침 — 이 저장소가 이미 갖고 있던 관례(test_scan_round6·7·31·34·49_fixes.py·test_fresh_db.py·test_firstday.py 가 자기가 여는 하위 프로세스 env 에 이미 PYTHONIOENCODING=\"utf-8\" 를 넣는 것)를 그대로, 이 유일한 공유 스포너 한 곳에만 추가했다(_env.setdefault(\"PYTHONIOENCODING\", \"utf-8\"), run_all_tests.py 516행 부근 — 새 정책·새 헬퍼 없음, setdefault 라서 호출 셸이 이미 다른 값을 정해 뒀으면 그대로 존중). 회귀테스트(test_scan_round532_fixes.py, 12개 검사) 신설 — [1] 소스: setdefault 줄이 subprocess.run 호출보다 코드상 앞에 정확히 있다(AST로 run() 함수 본문만 추출해 확인). [2] 실행(모킹) — subprocess.run 을 스텁으로 바꿔 실제 run() 을 호출, 전달되는 env 에 PYTHONIOENCODING=utf-8 이 채워짐과 이미 다른 값이 있으면 안 덮어씀(setdefault 의미) 둘 다 확인. [3] 실행(진짜 서브프로세스) — PYTHONIOENCODING 을 없앤 환경에서 지금(수정된) 진짜 run() 으로 round166 회귀를 실제로 스폰해 성공(returncode 0)함을 확인. [4] 되돌림-증명 — run_all_tests.py 파일 자체는 건드리지 않고(동시편집 세션이 이 파일도 같이 건드릴 수 있는 환경, 기존 라운드 표준 관례) 수정 전 run() 본문을 메모리 문자열로만 재구성해 같은 환경으로 실행 — 옛 코드는 실제로 UnicodeEncodeError/cp949 로 죽고 바로 옆(같은 환경) 지금 코드는 성공함을 대조해 이 회귀가 실제로 결함을 잡아낼 능력이 있음을 증명 — 첫 실행 12/12 통과. run_all_tests.py 는 app.py 가 import 하지 않는 독립 검증 실행기라 서버(app.py) 재기동은 불필요 — 다음에 run_all_tests.py 를 실행하는 순간부터 바로 반영된다."),
    ("test_scan_round533_fixes.py", "스캔 533라운드 회귀 — 개인정보 처리방침 제6조(개인정보 처리의 위탁) 표에 주소검색(카카오) 위탁처가 통째로 빠져 있던 결함[round508과 같은 클래스의 새 사례]. 직접 조사(하위위임 없음) — 지시받은 예시 각도(입력길이 상한·cases.status 동시성·is_demo 이외 플래그·비밀번호 재설정 토큰·이모지 SMS·관리자 삭제 세션무효화)를 전부 실측 대조했으나 전부 클린이었다(cases.status를 건드리는 UPDATE 16곳 전수 BEGIN IMMEDIATE 확인, SMS 바이트계산은 이모지·단독서로게이트·ZWJ 전부 cp949 errors=replace 로 안전 치환됨을 실행확인, 엑셀은 _xl_safe 로 이미 통일, 비밀번호 재설정은 토큰링크가 아니라 관리자 즉시발급 구조라 토큰만료 개념 자체가 없음, 관리자 삭제·강등은 _account_alive() 가 매 요청 재확인, is_demo 외 소프트삭제 플래그는 스키마에 없음). 그래서 각도를 '이미 발견된 결함의 형제가 또 있는가'로 옮겨 round508(처리위탁 표 누락)을 다시 보니 — addr_search.py(/api/address/search)가 사건·협력업체 등록 화면의 주소검색 입력을 카카오(dapi.kakao.com, 키 없으면 공개 무인증 엔드포인트로 자동폴백)로 그대로 전송해 좌표를 받아오는데, 제2조 표가 이미 '사업장 주소(위치정보 포함)'·'사고 현장 주소'를 수집 항목으로 명시하면서도 그 값을 실제로 내보내는 이 위탁은 제6조 표 어디에도 없었다. round508(Gemini)과 달리 이 기능은 끌 수 있는 스위치가 없다(KAKAO_REST_KEY 유무는 두 카카오 엔드포인트 중 어디로 갈지만 가르지 '안 보낸다'는 상태가 없다 — addr_search.py 자신이 '키 없이도 오늘 당장 동작한다'고 명시) — 그래서 ai_photo_enabled류 조건부가 아니라 HOSTING·PG·ALIMTALK처럼 상시 행으로 legal_docs.py PRIVACY 표에 추가했다(ALIMTALK 행 앞에 — 뒤에 넣으면 round508이 심은 _ALIMTALK_ROW_TAIL 앵커가 끊겨 그 라운드의 Gemini 조건부 삽입이 조용히 깨진다). 회귀테스트(test_scan_round533_fixes.py, 32개 검사) 신설 — [1] 소스: PRIVACY 원문에 카카오 행이 무조건 있고 ALIMTALK보다 앞이며 _ALIMTALK_ROW_TAIL 앵커가 안 끊겼고 표 태그 짝이 맞는다. [2] 실행 — privacy_body() 4개 조합 전부에서 카카오는 항상, Gemini는 여전히 플래그대로(round508 무회귀). [3] 되돌림-증명 — 방금 추가한 행만 정규식으로 도려낸 옛 버전을 메모리로 재구성해 '카카오'가 실제로 한 글자도 없었음을 확인(round508이 못 잡았던 진짜 공백임을 증명), 옛 코드에서도 round508 자신의 Gemini 조건부 삽입은 정상 동작함을 대조. [4] 실행(진짜 Flask 앱, 격리 DB) — test_client 로 실제 /legal/privacy 응답에 카카오가 실림을 확인. [5] 실행 — build_pages.py 정적 빌드(GEMINI_KEY 있음/없음 둘 다)에도 카카오가 실리고 Gemini는 여전히 플래그를 따름을 확인. [6] 실측 — addr_search.provider()가 KAKAO_REST_KEY 유무 두 경우 다 '비활성' 없이 유효한 카카오 경로만 돌려줘 조건부가 아니라 상시행이 맞다는 근거를 재확인. 첫 실행 32/32 통과. legal_docs.py 하나만 고쳤고 app.py는 건드리지 않았다 — 다만 app.py 가 이 모듈을 모듈 최상위에서 import 하므로, 이미 떠 있는 프로세스는 재시작해야 /legal/privacy 실제 응답에 반영된다."),
    ("test_scan_round534_fixes.py", "스캔 534라운드 회귀 — 보험사 포털 '자기조회' 내보내기 2곳(절감 리포트 api_insurer_report_export·월 정산 명세서 api_insurer_statement_self_export)이 파일은 정상 응답하면서 감사 로그를 전혀 안 남기던 결함. 직접 조사(하위위임 없음) — 지시받은 신선한 각도 예시 (2)'관리자 콘솔의 CSV/엑셀 내보내기가 전부 감사 로그를 남기는가'를 app.py 전수(ast로 Workbook() 을 만드는 함수 8개를 기계적으로 추출) 검사했다: api_ops_kpi_export·api_export_xlsx·api_settlements_export·api_insurer_statement_export·api_activity_export·api_partner_onboarding_export 6곳은 이미 DB.log 를 남기는데(api_activity_export 는 test_feature_audit_export.py 가 이미 전담 검증 중) 마지막 두 개(둘 다 보험사 포털의 '내 것만 자기조회' 짝)만 없었다. 결정적 증거 — api_insurer_statement_export(어드민, 13822행)와 api_insurer_statement_self_export(보험사 포털)는 같은 헬퍼 _statement_xlsx() 를 불러 바이트 단위로 동일한 파일을 만드는데, 어드민이 대신 뽑으면 '월 정산 명세서 내보내기'가 activity_log 에 남고 보험사 본인이 자기 명세서를 뽑으면 아무 흔적이 없었다 — 더 자주 쓰일 경로(본인 다운로드)가 오히려 감사 사각지대였다. api_insurer_report_export(절감 리포트, 이 함수 자신의 docstring 이 '분기 보고서·결재 첨부용'이라고 스스로 밝히는 산출물)도 같은 계산 코어(_compute_ops_kpi)를 쓰는 형제 api_ops_kpi_export(어드민 운영KPI)와 달리 DB.log 가 없었다. test_feature_audit_export.py 자신이 이미 명시한 원칙('내보낸 사실도 감사 로그에 남긴다 — 개인정보 취급 이력')이 보험사 포털 자기조회 두 곳에서만 새고 있었다. 고침 — app.py 두 함수 끝(파일 완성 직후, 응답 조립 직전)에 형제와 정확히 같은 모양의 DB.log(_c, portal_actor(), '...', detail); _c.commit(); _c.close() 블록을 이식했다 — actor() 대신 portal_actor() 를 쓰는 것만 다르다(조직명만으로는 하위계정 중 누가 내려받았는지 특정 못 한다는 라운드141 관례 재사용). action 라벨도 형제와 동일하게 맞췄다('월 정산 명세서 내보내기'·'엑셀 내보내기'). 새 헬퍼·새 상수 없음. 회귀테스트(test_scan_round534_fixes.py, 22개 검사) 신설 — [1]~[3] 소스: 두 함수 다 DB.log(portal_actor(),..)·commit 을 ast로 정확히 추출해 확인, 어드민 형제 둘(api_insurer_statement_export·api_ops_kpi_export)은 이번 라운드가 손대지 않고 여전히 actor() 그대로임을 대조, app.py 전체 ast.parse 성공. [4]~[6] 실행(진짜 Flask app + test_client + 격리 스크래치 DB, 보험사 세션): 되돌림-증명으로 이번 라운드가 심은 블록만 정확히 도려낸(ast로 뽑은 두 함수 소스에서 '[라운드534]' 주석~'_c.commit(); _c.close()' 구간만 문자열로 제거) '라운드534 이전' 버전을 만들어 app.view_functions 에 require_insurer 로 다시 감싸 임시로 꽂아 보면 — 두 내보내기 다 여전히 200 으로 파일을 정상 응답하는데 activity_log 는 0건 늘어난다(파일은 받았는데 흔적이 없다는 결함이 실제로 재현됨). 되돌린 뷰를 원상복구한 뒤 지금(고친) 버전으로 같은 두 호출을 하면 정확히 2건이 새로 남고, actor 열이 session['insurer_name'] 원문 그대로가 아니라 portal_actor() 형식('조직명(로그인아이디)')으로 남는 것까지 확인 — 첫 실행 22/22 통과. app.py 자신 안에 정의된 두 함수 본문을 고쳤다(다른 모듈이 아니라) — 이미 떠 있는 프로세스가 있다면 재시작해야 이 두 내보내기 라우트의 실제 응답에 반영된다."),
    ("test_scan_round535_fixes.py", "스캔 535라운드 회귀 — 대시보드(api_dashboard, app.py:6924) '최근 활동' 위젯이 관리자 계정 관련 감사로그 5개 행위(_ADMIN_ACCOUNT_ACTIONS)의 detail 을 마스킹 없이 노출하던 결함. 직접 조사(하위위임 없음) — 지시받은 신선한 각도 예시 (6)'관리자 콘솔에서 다른 관리자의 활동을 볼 때(activity_log 조회), 민감한 필드가 로그 문자열에 실수로 포함돼 있는지'를 따라 activity_log 를 읽는 모든 지점을 app.py 전수(grep \"FROM activity_log\")했다(그 전에 업로드 감사로그 3곳·생성/삭제 감사 짝 8쌍·app.py 전체 LIKE 절 와일드카드 이스케이프(partner_accounts.py 기지 2곳 제외 전부 클린, _like_escape/ESCAPE '\\\\' 일관)·엑셀 6곳+CSV 1곳 수식주입 방어(_xl_safe/_csv_safe)·임시비밀번호 발급 6곳의 DB.log detail(전부 username/login_id 만 남기고 비밀번호 값 자체는 안 실음)까지 전부 실측 대조했으나 클린이었다). 결정적 증거 — round326 은 하위관리자가 /api/admins(관리자 목록, 최고관리자 전용)에서 403 을 받으면서도 감사 로그로 같은 정보(대상 관리자 아이디·이름·등급)를 우회해 볼 수 있던 것을 막으려고 _mask_admin_activity() 헬퍼를 만들어 형제 둘 — api_activity(화면)·api_activity_export(엑셀), 둘 다 등급 무관 @require_admin — 에 심었다. 그런데 activity_log 를 읽는 세 번째 지점인 api_dashboard() 의 '최근 활동' 위젯(최신 8건, 역시 등급 무관 @require_admin)은 이 헬퍼를 거치지 않고 원본을 그대로 반환했고, static/admin.js:759(`${a.action}${a.detail?' — '+esc(a.detail):''}`)가 action·detail 을 가감 없이 그렸다 — 로그인 직후 가장 먼저 보는 화면에서 round326 이 막으려던 것과 똑같은 우회가 세 번째 문으로 열려 있었다. 고침 — api_dashboard() 안의 `recent = rows(conn.execute(...))` 를 형제 둘과 완전히 같은 모양으로 `recent = _mask_admin_activity(rows(conn.execute(...)))` 로 감쌌다(app.py 7130행 부근, 한 줄). 새 헬퍼·새 정책 없음 — round326 이 이미 만든 헬퍼를 세 번째 호출부에 그대로 이식했을 뿐이다. 회귀테스트(test_scan_round535_fixes.py, 16개 검사) 신설 — [1]~[3] 소스: api_dashboard 가 _mask_admin_activity(rows(conn.execute( 를 부르고 [라운드535] 표식이 있음을 ast로 정확히 추출해 확인, 형제 둘(api_activity·api_activity_export)은 이번 라운드가 손대지 않고 여전히 같은 헬퍼를 부름을 대조, app.py 전체 ast.parse 성공. [4]~[7] 실행(진짜 Flask app+test_client+격리 스크래치 DB, 하위관리자·최고관리자 세션 2종): 되돌림-증명으로 이번 라운드가 심은 마스킹 래퍼만 도려낸(ast로 뽑은 함수 소스에서 '[라운드535]' 표식~`_mask_admin_activity(rows(conn.execute(...)))` 구간만 문자열로 원상 대체) '라운드535 이전' 버전을 만들어 app.view_functions 에 require_admin 으로 다시 감싸 임시로 꽂아 보면 — 하위관리자 세션으로 /api/dashboard 를 불렀을 때 '관리자 계정 생성' 행의 detail(대상 관리자 아이디·등급·이름)이 원문 그대로 샌다(결함이 실제로 재현됨). 되돌린 뷰를 원상복구한 뒤 지금(고친) 버전으로 같은 호출을 하면 그 detail 이 형제(api_activity)와 동일한 문구 '(최고관리자만 볼 수 있습니다)' 로 가려지고, 같은 요청을 최고관리자 세션으로 하면 지금도 원문이 그대로 보여 과잉마스킹이 아님까지 확인 — 첫 실행 16/16 통과. app.py 자신 안에 정의된 api_dashboard() 본문을 고쳤다 — 이미 떠 있는 프로세스가 있다면 재시작해야 대시보드 실제 응답에 반영된다."),
    ("test_scan_round536_fixes.py", "스캔 536라운드 회귀 — 인라인 마감 스윕(_sweep_if_due, app.py:6888)의 바깥 except 가 예외를 로그 한 줄 없이 삼키던 결함. 직접 조사(하위위임 없음) — 지시받은 여섯 예시 각도(오프셋 페이지네이션 동점자·숫자입력 서버측 상한·동시 파일명 충돌·관리자 알림 공유읽음상태·스케줄 시간중복·DB 마이그레이션 동시성)를 전부 실측 대조했으나 전부 클린이었다(app.py 전체에 OFFSET 기반 페이지네이션 자체가 없음=예제(1) 무관, parse_money/parse_days 가 입찰·재경매·가견적 등 금액·기간 입력 7곳 전부에서 음수·초과값을 서버가 일관 거부, photo_ai.save_upload() 가 secrets.token_hex(16) 로 저장명을 지어 파일명 충돌이 구조적으로 불가능, round206 이 이미 ADMIN_OWN_SQL/ADMIN_FEED_SQL 로 브로드캐스트 알림의 공유읽음처리를 관리자·보험사·협력사 세 포털 전부에서 동일하게 차단, schedule_events 는 협력업체·시간대 개념이 없는 범용 캘린더라 이중예약 자체가 성립하지 않음, db.py migrate() 의 ALTER TABLE 이 이미 duplicate-column 예외를 무시하도록 gunicorn 동시기동을 전제로 설계됨). 그래서 각도를 '이미 알려진 결함 중 스스로 고치지 않았다고 자백한 것이 있는가'로 옮겨 round523 의 주석을 다시 읽었다 — round523(app.py:5779 _sweep_claim)은 자신의 수정 코멘트(5792행)에 \"그런데도 _sweep_if_due() 의 바깥 except 는 로그 한 줄 없이 삼켜 아무도 못 알아챈다\"고 스스로 명시해 두고도 그 라운드는 형제 _sweep_claim() 의 락 경합 실패(sqlite3.Error)만 고쳤을 뿐 이 문장이 가리키는 _sweep_if_due() 자신은 그때도, 이후 524~535 라운드 동안(grep 재확인 — 이 함수를 실제로 수정한 라운드가 없음)도 손대지 않았다. _sweep_if_due() 는 보험사·관리자·협력사 포털 4개 호출부(app.py 3549·6937·21135·21163행)가 화면을 열 때마다 곁들이는, 5개 스윕(sweep_auctions·sweep_no_bid_alert·sweep_report_overdue·sweep_review_reminders·sweep_warranty_expiry)을 감싸는 유일한 공유 관문인데, 그 바깥 `except Exception: try: conn.rollback() except sqlite3.Error: pass` 는 (자신의 docstring대로) 화면을 안 깨뜨리는 데는 성공하지만 5개 스윕 중 하나가 락 경합이 아닌 다른 이유(프로그래밍 버그·디스크 오류 등)로 실패하면 그 회차 전체가 조용히 건너뛰어지고 _LAST_INLINE_SWEEP 는 이미 갱신돼 있어 INLINE_SWEEP_GAP_SEC(60초) 동안 재시도조차 안 열리는데, 그 실패가 어디에도 안 남아 마감 점검이 몇 분씩 멈춰도 화면은 계속 200을 돌려주니 아무도 눈치챌 수 없다 — round523 자신이 정확히 예견한 그 상태 그대로였다. 고침 — 예외를 여전히 밖으로 올리지 않는다(주 흐름 보호 원래 설계 그대로). except 블록 맨 앞(rollback 시도보다 먼저)에 형제와 완전히 같은 모양의 `app.logger.exception(\"인라인 마감 스윕 실패 — 다음 회차까지 재시도 없음\")` 한 줄을 추가했다(app.py 6911행 부근) — _sweep_claim(5809행)·notify_victim(round529)과 정확히 같은 관례 재사용, 새 헬퍼·새 상수 없음. 회귀테스트(test_scan_round536_fixes.py, 19개 검사) 신설 — [1] 소스: except Exception(주흐름 보호)이 그대로 남아 있고 app.logger.exception 호출이 except 블록 몸통 안(rollback보다 먼저)에 있음을 확인, 5개 스윕 호출이 순서·개수 그대로임을 위치 대조로 확인(주석 삽입 중 실행문 유실 사고 방지), 형제 _sweep_claim 의 round523 로그가 이번 라운드로 안 건드려졌음을 대조, app.py 전체 ast.parse 성공. [2]~[2-b] 실행(진짜 DB.init_db() 격리 스크래치 DB) — 정상 경로(아무 실패 없음)에서는 로그가 안 남아 과잉로깅이 아님을 확인, 조절창(60초) 안 재호출은 스윕 본문 자체가 안 불림을 카운팅 스텁으로 확인(이번 수정이 조절창을 안 깼음). [3] 실행 — sweep_auctions 를 RuntimeError(sqlite3.Error 아님, round527 과 같은 원칙)로 몽키패치해 실제로 실패시키면 _sweep_if_due() 는 여전히 예외를 안 올리면서 이제 로그가 정확히 남고, 커넥션 추적 프록시로 close()·rollback() 이 실패 경로에서도 그대로(각 1회) 실행됨을 확인. [4] 실행(라우트) — 진짜 Flask test_client + 관리자 세션으로 실제 /api/dashboard 를 호출해 같은 실패를 재현 — 화면은 여전히 200이면서 서버 로그에 흔적이 남음을 확인. [5] 되돌림-증명 — app.py 파일 자체는 건드리지 않고(동시편집 세션이 이 파일을 같이 건드릴 수 있는 환경, round520 이후 표준 관례) 라운드536 이전 실제 _sweep_if_due 본문(수정 직전 이 세션이 Read 로 확인한 원문)을 테스트 안에서만 문자열로 재구성해 독립된 조절창으로 같은 실패를 실행 — 옛 코드도 예외는 똑같이 안 올리지만(그래서 13개 라운드 동안 아무도 눈치 못 챘다) 로그를 단 한 줄도 안 남기는 차이를 실측 대조해 이 회귀가 실제로 결함을 잡아낼 능력이 있음을 증명 — 첫 실행 19/19 통과. app.py 자신 안에 정의된 _sweep_if_due() 본문을 고쳤다 — 이미 떠 있는 프로세스가 있다면 재시작해야 보험사·관리자·협력사 포털 4개 호출부의 실제 인라인 스윕 실패가 로그에 반영된다."),
    ("test_scan_round537_fixes.py", "스캔 537라운드 회귀 — 관리자 계정 삭제(api_admin_delete, "
     "app.py:1763 DELETE /api/admins/<id>)가 그 계정의 2단계 인증 복구코드"
     "(admin_recovery_codes)를 지우지 않고 고아로 남기던 결함. 직접 조사(하위위임 없음) — "
     "지시받은 다섯 예시 각도 중 (5)\"사건 하드삭제 시 자식레코드 고아화\"를 이 저장소에 "
     "적용해 봤다(cases 자체엔 하드삭제 라우트가 없음=grep 재확인, DELETE FROM cases 전무). "
     "같은 질문을 admins(실제 물리 DELETE 되는 유일한 계정 테이블)에 적용하니, "
     "admin_recovery_codes(admin_id INTEGER, REFERENCES 없음·PRAGMA foreign_keys 도 꺼져 "
     "있어 엔진 차원 정리가 전혀 없음)가 그대로 남았다. 형제 api_otp_disable()(2단계 인증만 "
     "해제, 계정은 그대로 두는 더 가벼운 조작)은 이미 이 정리를 하는데, 계정을 통째로 "
     "영구 삭제하는 더 강한 조작만 그 정리가 빠진 비대칭. admins.id 는 AUTOINCREMENT라 "
     "재사용되지 않아 활성 악용 경로는 없음(운영 DB 실측 — 현재 admin_recovery_codes 0행, "
     "2FA 실사용 전이라 아직 고아행 미발생), 순수 데이터 정리 누락. 다른 네 각도(TODO/FIXME류 "
     "미완성 주석 전수·정산 금액 저장 타입 float 오염·관리자 다중탭 세션무효화 전파·웹훅 "
     "시크릿 재발급 경쟁)는 전부 클린이었다(코드·운영DB 실측 대조 — 미완성 주석 7건은 전부 "
     "이미 해소된 설계메모, settlements.amount/fee/payout 등 INTEGER 금액컬럼 전수(220개 "
     "컬럼) 스캔 결과 float 오염 0건, 웹훅 시크릿은애초 재발급 라우트 자체가 없어 경쟁 성립 "
     "불가). 고침 — 형제와 정확히 같은 한 줄 `DELETE FROM admin_recovery_codes WHERE "
     "admin_id=?` 을 admins 삭제 직전(app.py:1790)에 추가. 새 정책·새 헬퍼 없음. "
     "회귀 16건 전부 통과(소스 검증 6 · 실제 라우트 실행 4 · 되돌림-인과증명 3 · "
     "최고관리자 삭제경로 3) — 되돌림 테스트가 재구성한 수정 전 코드로 실행하면 복구코드 "
     "3건이 실제로 고아로 남는 것을 실측 확인해 이 회귀의 탐지력을 직접 증명했다. "
     "app.py 자신 안에 정의된 라우트 함수 본문을 고쳤다 — 이미 떠 있는 프로세스가 있다면 "
     "재시작해야 실제 DELETE /api/admins/<id> 호출에서 복구코드 정리가 반영된다."),
    ("test_scan_round538_fixes.py", "스캔 538라운드 회귀 — 사진 업로드 형제 셋(협력사 시공사진 "
     "api_partner_upload_photos·보험사/운영자 피해사진 _upload_damage_photos·하자 사진 "
     "api_defect_photos_upload) 모두 '저장 성공 뒤 INSERT 실패 시 방금 쓴 파일을 os.remove로 "
     "치우고 errors[]로 사용자에게 알린다'는 [PH-07]류 관례는 똑같이 갖고 있었는데, 그중 "
     "가장 나중에 손 본 하자 사진 경로만 그 실패를 app.logger.exception()으로 서버 로그에 "
     "남기고 나머지 둘(실무에서 가장 자주 쓰이는 협력사 시공사진 포함)은 침묵하던 결함. "
     "직접 조사(하위위임 없음) — 지시받은 각도 (2)'파일시스템 파일이 DB 레코드 삭제 시 "
     "실제로 지워지는지, round110이 안 다루는 삭제 경로가 있는지'를 따라가다 photos의 유일한 "
     "진짜 삭제 라우트(api_photo_delete, round110·PH-03)는 ai_reviews·damage_reads· "
     "defect_photos·fix_for·ai_photo_id까지 이미 전부 정리해 완전했다(신선한 결함 없음). "
     "그래서 '삭제'가 아니라 '업로드 중 INSERT 실패'라는 형제 실패경로로 옮겨 사진 업로드 "
     "3곳의 except Exception: 블록을 나란히 대조하니, 셋 다 파일 고아화 방지(os.remove)는 "
     "이미 완비했지만 서버 로그 유무만 갈렸다 — api_defect_photos_upload만 스스로 "
     "\"조용히 삼키면 안 된다\"는 주석과 함께 로깅하고 있었다. 다른 네 각도(강한 작업 vs "
     "약한 작업 패턴을 협력사·보험사·하위계정 삭제에 적용·GET 라우트의 DB 쓰기 전수·관리자 "
     "콘솔 검색 대소문자 일관성·웹훅/알림 재시도 정책 비교)는 전부 클린이었다(협력사 퇴출은 "
     "애초 물리 DELETE가 아니라 상태변경뿐이라 강/약 비교 대상 자체가 없고 보험사는 하드삭제 "
     "라우트가 아예 없음, 하위계정(portal_users)은 참조하는 자식 테이블이 스키마 전체에 "
     "0개라 고아화 불가능, GET 라우트 128개 중 쓰기가 있는 곳은 track_page 1곳뿐이고 그마저 "
     "round260·295가 이미 감싼 의도된 조회수 집계, 검색은 전부 SQL LIKE(SQLite ASCII 기본 "
     "대소문자 무시)만 쓰고 GLOB·COLLATE 충돌 0건, 재시도 정책(웹훅 5회 제곱백오프 vs 알림 "
     "3회 무백오프)은 round144/145가 이미 두 계열의 '소진 시 통지' 3종 세트를 교차 이식해 "
     "의도된 차이임을 재확인). 고침 — 형제(api_defect_photos_upload)가 이미 쓰는 스타일 "
     "그대로 app.logger.exception(...) 한 줄씩만 두 함수에 이식했다: "
     "api_partner_upload_photos()는 'app.logger.exception(\"시공 사진 저장 실패 case=%s\", "
     "cid)'(app.py, [PH-07] 블록 맨 앞), _upload_damage_photos()는 'app.logger.exception("
     "\"피해 사진 저장 실패 case=%s\", cid)'(app.py, 같은 위치의 except Exception: 블록 맨 "
     "앞). 기존 os.remove 정리·errors[] 응답 로직의 위치·순서는 전혀 안 건드렸다. 새 정책·새 "
     "헬퍼 없음. 회귀테스트(test_scan_round538_fixes.py, 29개 검사) 신설 — [1] 소스: 두 "
     "함수 다 새 로그 호출이 있고 로그→정리→응답 순서가 유지되며, 형제(하자 사진)의 기존 "
     "호출은 손 안 댄 채 그대로임을 확인, app.py 전체 ast.parse 성공. [2]~[3] 실행(진짜 "
     "Flask app+test_client+격리 스크래치 DB) — photo_ai.save_upload()를 몽키패치해 파일은 "
     "실제로 디스크에 저장한 뒤 반환 dict의 size만 sqlite3가 바인딩 못 하는 타입으로 바꿔치기, "
     "실제 INSERT가 sqlite3.ProgrammingError로 실패하는 상황을 두 라우트 각각에서 실제로 "
     "재현 — 응답은 여전히 200·errors[] 1건(무회귀)이면서 서버 로그에 해당 메시지가 정확히 "
     "1건(exc_info 포함) 남고, [PH-07] 파일 정리도 그대로 동작함을 확인. [4] 실행 — 형제 "
     "(하자 사진, 이번 라운드가 손대지 않음)도 같은 방식으로 실패시켜 원래부터 로그가 남는 "
     "이식 원본임을 대조(이 형제는 전부 실패 시 200이 아니라 409를 주는 자기만의 기존 규칙이 "
     "있음을 확인 — 이번 수정과 무관한 사전 동작이라 그대로 존중). [5]~[6] 되돌림-인과증명 — "
     "app.py 파일 자체는 안 건드리고(동시편집 세션이 이 파일을 같이 건드릴 수 있는 환경, "
     "round520 이후 표준 관례) 이 세션이 고치기 직전 Read로 확인한 두 함수의 실제 원문을 "
     "문자열로 재구성해 더미 루프 안에서 같은 예외로 실행 — 옛 코드는 errors[]는 채우면서도 "
     "로그가 0건임을 실측 확인했고(같은 조건에서 지금 코드는 정확히 1건), 지금 코드 쪽은 "
     "손으로 옮겨 적지 않고 app.py에서 직접 뽑아 온 문자열을 그대로 실행해 이 회귀의 탐지력을 "
     "직접 증명했다 — 첫 실행 29/29 통과. app.py 자신 안에 정의된 두 라우트 함수 본문을 "
     "고쳤다(다른 모듈이 아니라) — 이미 떠 있는 프로세스가 있다면 재시작해야 실제 업로드 "
     "INSERT 실패가 서버 로그에 반영된다."),
    ("test_feature_victim_track.py", "기능 회귀(피해자 진행조회)"),
    ("test_feature_license_survey.py", "기능 회귀(등록 전수조사)"),
    ("test_feature_audit_export.py", "기능 회귀(감사로그 엑셀·사건 이력)"),
    ("test_feature_onboarding.py", "기능 회귀(협력사 온보딩)"),
    ("test_feature_selfcheck.py", "기능 회귀(운영 점검·연동 안내서)"),
    ("test_feature_work_coverage.py", "기능 회귀(공종 개산 근거 경고)"),
    ("test_feature_case_input_sanitize.py", "기능 회귀(사건 등록 — 자모 입력 정제)"),
    ("test_feature_mobile.py", "기능 회귀(폰 화면 — 누를 자리·번호·손가락 크기)"),
    ("test_feature_demo_isolation.py", "기능 회귀(데모가 실운영 자리로 새지 않는가)"),
    ("test_feature_defect_reject_notify.py", "기능 회귀(하자 반려 시 보험사 통지)"),
    ("test_app_shell.py", "앱 셸"),
    ("test_approval_sweep.py", "승인 독촉 스윕"),
    ("test_auction_round2.py", "2차 경매 규칙"),
    ("test_b3_ai_routing.py", "AI 라우팅"),
    ("test_b4_deadline.py", "입찰 마감"),
    ("test_b5_severity.py", "파손 정도"),
    ("test_compliance.py", "도급 적법성 관문"),
    ("test_concurrency.py", "동시성"),
    ("test_dispatch.py", "출동 배차"),
    ("test_fairness.py", "공정성"),
    ("test_geo.py", "좌표·거리"),
    ("test_notify_popbill.py", "팝빌 발송 어댑터"),
    ("test_repair_estimate.py", "견적 엔진"),
    ("test_scan_round540_fixes.py", "스캔 540라운드 회귀 — 직전 라운드(538·539)가 고친 출동 "
     "'직접배정'(api_dispatch_assign, round463) 재시도 결함('기존 것을 취소하고 새로 만드는' "
     "API가 재시도를 진짜 실패와 구분 못 해 같은 업체에게 거짓 취소통지+중복알림)과 같은 "
     "계열이 다른 API에도 있는지 전수 점검(지시받은 각도 (1), 직접 조사·하위위임 없음) — "
     "출동 '선착순 수락'(claim, dispatch.py:580)에서 발견. 내가 방금 성공시킨 바로 그 수배를 "
     "같은 pid로 다시 두드리면(더블탭·네트워크 재시도) claim()은 rowcount=0이 되어 '이미 다른 "
     "업체가 출동을 맡았습니다'를 그대로 돌려주는데 그 '다른 업체'는 사실 나 자신이다 — "
     "claim()은 '모집중일 때만 성공'만 볼 뿐 실패 시 claimed_partner_id가 이미 자기 자신인지는 "
     "안 본다. round463과 달리 DB 훼손·중복발송은 없다(현재 ok=False라 호출부의 보험사 "
     "notify() 블록에 아예 안 닿는다) — 대신 문구 자체가 거짓이라 프론트(partner_portal.html "
     "dpClaim, \"이건 오류가 아니라 선착순의 정상 결과다\"라는 자기 주석)가 그대로 alert 하면 "
     "실제로 배정된 기사가 '남이 이미 맡았다'고 오인해 30분 SLA인 현장에 안 갈 수 있다. 같은 "
     "각도로 함께 점검한 낙찰취소→재공고(api_case_cancel_award)·낙찰확정(api_case_award)· "
     "입찰재개(api_case_reopen)·유찰확정(api_case_fail_bidding)·오프라인전환· "
     "변경견적 추가경매/전체재경매 강제개시(api_co_open_add·api_co_full_reauction)는 전부 "
     "'BEGIN IMMEDIATE 뒤에 상태를 다시 읽어 rowcount로만 판정 + 상태전이가 되돌아오지 않는 "
     "단방향'이라 재시도가 자연히 409로 막혀 클린이었다(회귀 없음, 별도 결함 아님) — claim()만 "
     "'같은 대상으로 되돌아오는' 유일한 패턴이라 이 위험에 걸렸다. 스윕 5종(무입찰경보·완료보고 "
     "지연·검수리마인드·보증만료·완료승인독촉, 지시각도 (2))도 각각 BEGIN IMMEDIATE 트랜잭션 "
     "또는 rowcount 재확인 UPDATE로 이미 동시성 안전(클린, 별도 결함 아님). 관리자 필터 AND "
     "결합(지시각도 (3))·로그인 실패 메시지 계정열거(지시각도 (5))·캠페인/출동콜 수신자 중복 "
     "(지시각도 (4))도 전수 확인했으나 전부 클린. 고침 — 새 정책·새 헬퍼 없이 형제 "
     "(api_dispatch_assign, round463)가 이미 쓰는 자리(호출 전 '이미 내가 그 자원을 쥐고 "
     "있는가'만 먼저 확인)를 그대로 옮겼다: app.py:api_partner_dispatch_claim() 맨 앞에서 "
     "dispatches.status='수배됨' AND claimed_partner_id=이 요청의 pid 인지 보고, 맞으면 "
     "DP.claim()도 보험사 notify()도 부르지 않고 duplicate:true로 조용히 반환한다. dispatch.py "
     "의 claim() 자신은 건드리지 않았다(유일한 호출부 하나뿐이라 이 호출부에서 막는 것이 근본"
     "수정) — claim()이 ok=True를 돌려주게 바꾸는 방식은 시도하지 않았다(호출부가 그대로 "
     "흘러 재시도마다 보험사에게 새 중복알림을 또 보내는, round463이 막으려던 바로 그 부류의 "
     "회귀를 만든다). 회귀테스트(test_scan_round540_fixes.py, 14개 검사) 신설 — [0] 소스: 새 "
     "가드·duplicate 분기 존재 확인, app.py 전체 ast.parse 성공. [1] 원인 재확인 — 손대지 않은 "
     "dispatch.py::claim()을 직접 두 번 호출해 같은 pid 재시도가 여전히 '다른 업체' 오보를 "
     "냄을 실측(회귀 없음 — claim() 자체는 의도적으로 그대로 둠). [2] 실행(진짜 Flask "
     "app+test_client+격리 스크래치 DB) — 같은 협력사가 같은 수배를 HTTP로 재수락 요청하면 "
     "이제 200·duplicate:true·정확한 메시지를 받고, notifications 테이블에 '출동배정' 알림이 "
     "추가되지 않음(중복발송 없음)을 실측. [3] 회귀 안전 — 다른 협력사(B)가 같은 수배를 노리면 "
     "여전히 원래 409·'다른 업체' 문구 그대로(진짜 실패는 안 숨김). [4] 회귀 안전 — 아무도 안 "
     "잡은 새 수배는 이 지름길 없이 정상 최초 수락(HTTP)됨. 첫 실행 14/14 통과. app.py 자신 "
     "안에 정의된 라우트 함수(api_partner_dispatch_claim) 본문을 고쳤다(dispatch.py 등 "
     "app.py가 import하는 모듈은 무수정) — 이미 떠 있는 프로세스가 있다면 재시작해야 이 "
     "가드가 실제 요청에 반영된다."),
    ("test_scan_round541_fixes.py", "스캔 541라운드 회귀 — 지시받은 각도 (1) '협력사가 이미 "
     "마감된(취소된/거절된) 출동을 뒤늦게 수락 시도하면 문구가 정확한가'를 직접 조사(하위위임"
     "없음)해 출동 선착순 수락(dispatch.py::claim(), 580행)에서 발견 — 직전 두 라운드(539·540)가 "
     "다룬 '같은 업체가 자기가 이미 성공시킨 자원을 재시도로 다시 두드림' 계열과 뿌리가 다르다. "
     "여기는 **애초에 그 수배를 못 잡은(또는 아예 안 잡힌 채 끝난) 협력사**가 뒤늦게 눌렀을 때 "
     "생긴다: CAS UPDATE의 rowcount=0(='모집중'이 아니다)의 실제 원인은 ① 진짜 다른 업체가 먼저 "
     "잡음(ST_CLAIMED, 문구가 사실) ② 아무도 못 잡은 채 스윕(sweep_dispatches)이 제한시간 초과로 "
     "ST_FAILED 처리(아무도 안 갔다) ③ 운영자 직접배정(assign_dispatch, supersede)이 이 수배를 "
     "ST_CANCELED로 걷어감(선착순 경쟁이 아니라 운영자 개입)으로 셋인데, claim()은 원인을 묻지 "
     "않고 셋 다 '이미 다른 업체가 출동을 맡았습니다'로 답했다 — ②·③은 이 문구가 거짓이다. "
     "프론트(partner_portal.html:903 dpClaim, 자기 주석 \"이건 오류가 아니라 선착순의 정상 "
     "결과다\")는 서버 문구를 그대로 alert()하므로, 늦게 확인한 협력사는 실제로는 아무도 안 갔거나 "
     "운영자가 개입한 것을 '남이 이미 갔다'로 오인한다 — round540이 고친 것과 결이 같은 위험이지만 "
     "트리거(재시도 vs 애초에 못 잡은 협력사의 지연 클릭)가 다르다. 같은 파일의 형제 셋(거절 "
     "decline·도착 arrive·미수선종결 close_no_repair)도 함께 대조했으나 전부 클린이었다 — 셋 다 "
     "실패 문구가 처음부터 '~일 수 있습니다'·'~이거나' 식으로 헤지되어 있어(예: arrive/"
     "close_no_repair의 '출동을 맡은 상태가 아닙니다(기한이 지났을 수 있습니다)', decline 호출부의 "
     "'이미 마감되었거나 다른 곳이 수락한 수배입니다') 원인이 여럿이어도 특정 원인을 단정하지 "
     "않는다 — claim()만 유일하게 '다른 업체'라고 범인을 지목하는 단정형 문구를 썼다가 이번에 "
     "걸렸다. 고침 — claim() 자신의 case-종료 분기(606~613행, '이 건은 종료돼 출동이 필요 "
     "없습니다')가 이미 쓰는 원칙(진짜 이유를 그대로 말한다)을 CAS 실패 분기에도 그대로 이식했다 "
     "— 새 정책·새 헬퍼 없음. dispatch.py:623-639, BEGIN IMMEDIATE 직후 읽어 둔 d[\"status\"] "
     "(이 트랜잭션이 쥔 RESERVED 락 때문에 그 사이 바뀔 수 없다)를 CAS 실패 시 재사용해 "
     "ST_FAILED→'이 수배는 응답 시간이 지나 이미 마감되었습니다.', ST_CANCELED→'이 수배는 "
     "취소되었습니다. 현장으로 가지 마세요.' 두 갈래만 추가했다(그 외 상태·진짜 실패는 기존 "
     "'이미 다른 업체가 출동을 맡았습니다' 그대로 — 숨기지 않는다). dispatch.py는 app.py가 "
     "import하는 모듈이고 app.py 자신은 무수정이다(유일한 호출부 api_partner_dispatch_claim, "
     "app.py:17892는 ok/msg를 그대로 jsonify({\"error\":msg})하므로 호출 계약 불변 — 이미 떠 있는 "
     "프로세스가 있다면 재시작해야 새 문구가 실제 요청에 반영된다, 파이썬은 이미 임포트한 모듈을 "
     "자동으로 다시 읽지 않는다). 회귀테스트(test_scan_round541_fixes.py, 17개 검사) 신설 — "
     "[0] 소스: 새 분기·새 문구·기존 문구 보존 확인, dispatch.py·app.py 전체 ast.parse 성공. "
     "[1] 원인 재현 — app.py·run_all_tests.py는 전혀 건드리지 않고 지금 dispatch.py 실제 텍스트에서 "
     "이번 수정 블록만 원래 한 줄로 되돌린 old_fn_src를 문자열 surgery로 재구성해 exec — "
     "ST_FAILED·ST_CANCELED 둘 다 옛 코드가 실제로 거짓 문구를 냄을 실측해 이 회귀의 탐지력을 "
     "직접 증명했다. [2] 실행(dispatch.claim() 직접호출) — 지금 코드는 두 상태 모두 정확한 문구로 "
     "갈린다. [3] 회귀 안전 — 진짜 다른 업체가 먼저 잡은 경우(ST_CLAIMED)는 원래 문구 그대로(진짜 "
     "실패를 안 숨긴다). [4] 실행(진짜 Flask app+test_client+격리 스크래치 DB, 진짜 HTTP 라우트) "
     "— 시간초과 건을 실제 API로 눌러도 정확한 문구가 그대로 error 필드에 실려 온다. [5] 회귀 "
     "안전 — 모집중 상태의 정상 최초 수락은 무회귀. 첫 실행 17/17 통과."),
    ("test_scan_round542_fixes.py", "스캔 542라운드 회귀 — 지시받은 각도 (2) '협력사 "
     "등급·평점 계산'을 직접 조사(하위위임없음)하다 win_rate 계산(_resync_partner_stats, "
     "15962·15991행)이 이미 COALESCE(b.is_demo,0)=0 으로 데모입찰을 거르는 것을 확인하고, "
     "같은 bids 표를 '입찰해 본 적 있는가'로 읽는 다른 자리도 그런지 대조하다 협력사 "
     "온보딩 화면(app.py:19993 api_partner_onboarding)의 다섯 단계 중 '입찰 경험 있음'"
     "(문구 그대로 '실제로 부를 수 있는 업체')과 그 목록·엑셀이 같은 판정에 쓰는 "
     "first_bid_at(ONBOARD_COLS)에서 발견 — 둘 다 'WHERE partner_id IS NOT NULL'만 걸고 "
     "is_demo 를 전혀 안 걸렀다. bids.is_demo 는 사건에서 물려받아 채워지므로(5301행 "
     "부근 주석) 실제 활성 협력사가 데모 사건에 입찰한 적이 있으면 그 행은 실업체를 "
     "가리키면서 is_demo=1이다 — 데모입찰 1건뿐인 업체가 이 화면의 가장 신뢰하는 마지막 "
     "단계로 잘못 집계되면 운영자는 한 번도 안 불러본 업체를 '이미 검증된 업체'로 믿는다. "
     "고침 — 새 정책·새 헬퍼 없이 같은 질문을 던지는 형제(app.py:4806행 my_bids_total — "
     "협력사 포털 자신의 '누적 제출' 카운트)가 쓰는 조건(COALESCE(is_demo,0)=0, win_rate "
     "와 달리 voided_at 은 거르지 않는다 — 여긴 승률 분모가 아니라 참여 이력을 묻는 "
     "자리라 my_bids_total 과 범위를 맞춘다)을 ONBOARD_STAGES 네 조건과 ONBOARD_COLS 의 "
     "first_bid_at 서브쿼리에 그대로 이식했다(app.py:19834-19915) — 두 자리를 함께 고친 "
     "이유는 목록의 stage_of()/_stage() 가 ONBOARD_COLS 의 first_bid_at 을 그대로 읽어, "
     "카드만 고치면 이 파일 자신의 원칙('카드 합계는 목록의 단계 배지와 항상 일치한다', "
     "19829행)이 새로 깨지기 때문이다. app.py 자신에 정의된 모듈 전역(ONBOARD_STAGES·"
     "ONBOARD_COLS)을 고쳤다 — import 하는 별도 모듈이 아니라, 재시작해야 새 조건이 "
     "실제 요청에 반영된다. 회귀테스트(test_scan_round542_fixes.py, 15개 검사) 신설 — "
     "[0] 소스: 네 조건·서브쿼리 모두 수정 확인, app.py 전체 ast.parse 성공. [1]~[2] "
     "실행(진짜 스크래치 DB, ONBOARD_STAGES·_onboard_rows 직접 호출) — 데모입찰 1건뿐인 "
     "업체는 '안내 전'에 남고 '입찰 경험 있음'으로 새지 않는다. [3] 원인 재현 — app.py·"
     "run_all_tests.py 는 건드리지 않고 지금 조건 문자열에서 이번 수정만 되돌린 옛 "
     "조건으로 같은 데이터를 다시 판정해 실제로 데모입찰만으로 '입찰 경험 있음'이 됨을 "
     "실측했다. [4] 회귀 안전 — 실입찰 1건은 지금 코드에서도 정상적으로 '입찰 경험 "
     "있음'으로 분류된다(과잉교정 없음), 다른 업체의 실입찰이 데모입찰뿐인 업체 판정에 "
     "교차오염을 안 낸다. [5] 배타성 — 활성 협력사 전원이 다섯 카드 중 정확히 하나에만 "
     "잡힌다(중복·누락 없음). 첫 실행 15/15 통과."),
    ("test_socket_timeout.py",
     "socket 전역 기본 타임아웃 회귀 — [420라운드 대조각도1][사용자결정 2026-09-10]. "
     "420라운드가 '제품판단 필요'로 기록만 해 두고 미수정 상태였던 결함(팝빌 SDK가 "
     "소켓 타임아웃을 전혀 안 걸어 serve_waitress.py 8-스레드 풀이 무한대기에 빠질 "
     "수 있음)을 사용자가 후보 3개 중 전역 socket.setdefaulttimeout(추천 후보)으로 "
     "승인 — app.py 모듈 최상위(\"app = Flask(\" 바로 앞)에 적용, 기본 30초"
     "(BOKGUON_SOCKET_TIMEOUT_SEC 로 조정). 회귀테스트 13개 검사: [1] 소스에 그 줄이 "
     "실제로 있고 Flask 앱 생성보다 앞선다. [2] app.py 를 실제로 import 하면 프로세스 "
     "기본 소켓 타임아웃이 30.0 이 됨을 실측 + 환경변수로 조정됨을 별도 프로세스로 "
     "재확인. [3] 응답 없는 진짜 소켓 서버(accept 만 하고 침묵)에 연결 — 적용 전엔 "
     "안전장치 시간까지 안 걸리고 적용 후엔 정확히 그 값 근처(실측 1.01s)에서 "
     "socket.timeout 이 실제로 발생함을 증명. [4] 메인 스레드에서 건 값이 나중에 만든 "
     "별도 워커 스레드의 새 소켓에도 그대로 적용됨을 실측(waitress 워커 스레드 모델과 "
     "동일 구조 — 짐작 아님). [5] 이미 자기 timeout 을 주는 호출(addr_search.py 6초·"
     "photo_ai.py 20초·app.py _webhook_send() 5초)은 더 짧은 전역 기본값이 걸려도 "
     "영향받지 않음을 실측(explicit timeout 우선) — 이 세 파일 모두 회귀 없음. "
     "sweep_send_notifications() 는 발송을 트랜잭션 밖에서 하므로(자신의 독스트링이 "
     "명시) 이 타임아웃이 걸려도 DB 락과 무관. 첫 실행 13/13 통과."),
    ("test_scan_round543_fixes.py", "스캔 543라운드 회귀 — 지시받은 각도 (1) '새 "
     "비밀번호가 기존과 같아도 변경완료 감사로그가 남는지'를 좇다 /api/change-password "
     "자체는 이미 current==new 를 400 으로 막아 깨끗함을 확인하고, 같은 질문을 다른 "
     "'정보수정' 라우트로 넓히다 api_admin_update(PATCH /api/admins/<id>, app.py:1748) "
     "안에서 발견 — role 분기(1759행)는 d['role']!=a['role'] 를 확인한 뒤에만 UPDATE+"
     "로그를 쏘는데 바로 아래 name 분기(수정 전 1771~1774행)는 d.get('name') 이 "
     "비어있지만 않으면 새 값이 옛 이름과 같아도 매번 UPDATE 하고 '관리자 이름 변경: "
     "홍길동→홍길동' 식으로 로그를 남겼다. 결정적 형제 증거 — _sub_update_impl"
     "(app.py:3375)의 자기 주석(3384~3389행)이 '값이 같아도 매번 UPDATE+로그를 쏘던' "
     "바로 이 결함을 라운드421이 자기 자신에서 고치며 '형제(api_admin_update)와 같은 "
     "기준으로 맞춘다'고 적었는데, 정작 그 기준점 자신의 name 분기는 그 기준을 충족 "
     "못하고 있었다. 실사용 영향(추정 아닌 프론트 코드 확인) — 편집 모달(admin.js "
     "adminForm, 2906행)이 이름칸을 항상 현재 이름으로 미리 채우고 저장(saveAdmin, "
     "2940행)은 등급만 바꿔도 그 값을 그대로 재전송하므로 등급만 바꾸는 모든 저장이 "
     "예외 없이 거짓 '이름 변경' 항목을 만들었다 — '관리자 이름 변경'은 "
     "_ADMIN_ACCOUNT_ACTIONS(17300행 부근)에 속해 최고관리자만 볼 수 있게 가리는 5개 "
     "민감 행위 중 하나라 그 신뢰가 직접 훼손됐다. 고침 — 새 정책·새 헬퍼 없이 바로 "
     "위 role 분기·_sub_update_impl 이 이미 쓰는 관례(새값!=옛값 일 때만 UPDATE+로그)를 "
     "name 분기에 그대로 이식했다(app.py:1787, if new_name != (a['name'] or ''):) — "
     "UPDATE·로그 두 줄을 한 단 들여쓰기만 했을 뿐 그 외 로직·문구·반환값은 그대로다. "
     "app.py 자신에 정의된 라우트 함수를 고쳤다 — import 하는 별도 모듈이 아니라, "
     "재시작해야 새 가드가 실제 요청에 반영된다. 회귀테스트(test_scan_round543_fixes.py, "
     "22개 검사) 신설 — [0] 소스: 새 가드와 순서(계산→가드→UPDATE→로그) 확인, 형제 "
     "role·reset_pw 분기는 무수정 확인, app.py 전체 ast.parse 성공. [1]~[2] 실행(진짜 "
     "Flask app+test_client+격리 스크래치 DB, 진짜 PATCH 라우트) — 등급만 바꾸며 "
     "이름칸에 옛 이름을 그대로 재전송해도(편집 모달의 실제 동작 재현) 지금 코드는 "
     "'관리자 이름 변경' 로그를 0건으로 남긴다(등급 변경 로그는 정상적으로 1건). "
     "[3] 원인 재현 — app.py·run_all_tests.py 는 건드리지 않고 이번 수정 직전의 실제 "
     "함수 본문을 문자열로 재구성(exec, round537과 같은 방식)해 같은 시나리오를 "
     "실행하면 옛 코드는 실제로 '박영희543→박영희543' 식 거짓 로그를 1건 남김을 "
     "실측 — 이 회귀의 실제 탐지력을 인과관계로 증명. [4] 회귀 안전 — 이름이 진짜로 "
     "바뀌면 지금 코드도 정확한 old→new 로 정상 로그(과잉교정 없음), 등급 로그와 "
     "교차오염 없음. [5] 회귀 안전 — 이름·등급 모두 무변경 재저장은 두 로그 모두 "
     "0건(완전 no-op). 첫 실행 22/22 통과."),
    ("test_scan_round544_fixes.py", "스캔 544라운드 회귀 — 543라운드가 예시로 든 "
     "'협력사·보험사 포털의 내 정보 수정 화면도 같은(값이 안 바뀌어도 UPDATE+로그를 "
     "쏘는) 패턴이 있는지'를 직접 조사(하위위임 없음)해 두 형제 함수 모두에서 발견 — "
     "api_partner_profile_update(PATCH /api/partner/profile, app.py:3138 부근)의 "
     "(ceo,phone,email,address,region) 루프는 'd에 그 키가 있는가'만 보고 무조건 "
     "fields/vals/notes에 추가했고, prev 조회도 address·lat·lng뿐이라 애초에 이전값과 "
     "비교할 수단이 없었다. api_insurer_profile_update(PATCH /api/insurer/profile, "
     "app.py:3316 부근)는 prev 조회 자체가 아예 없어 (manager,dept,phone,email) 네 "
     "필드 전부 '제출됐다'만 보고 무조건 UPDATE+로그였다. 실사용 영향(프론트 코드로 "
     "확인) — partner_portal.html의 pSaveProfile()과 insurer_portal.html의 mi_save "
     "리스너 둘 다 저장 버튼을 누르면 마이페이지의 모든 입력칸을 손 안 댄 칸까지 "
     "항상 통째로 재전송하므로, 담당자가 아무것도 안 고치고 '저장'만 눌러도 두 "
     "라우트 모두 예외 없이 거짓 '정보 수정' 감사로그를 남겼다(email 분기는 덤으로 "
     "email_source까지 매번 '직접입력'으로 재기록 — round299가 '본인이 직접 고쳤다'는 "
     "신호로 쓰려던 컬럼이 안 고쳐도 계속 갱신되는 잡음이 됨). 고침 — 새 정책·새 "
     "헬퍼 없이 형제(api_admin_update의 name 분기·_sub_update_impl)가 이미 쓰는 관례 "
     "(새값!=옛값일 때만 UPDATE+로그)를 그대로 이식 — 협력사쪽 prev SELECT를 "
     "ceo/phone/email/address/region/lat/lng로 넓히고 루프 안에 "
     "`if v == ((prev or {}).get(f) or ''): continue`를 추가했으며(email_source "
     "재기록도 changed 집합 조건으로 가드), 보험사쪽은 없던 prev SELECT를 새로 추가한 "
     "뒤 같은 가드를 이식했다. RE_PHONE/RE_EMAIL 형식 검사·biz_no 분기·좌표 초기화 "
     "분기·반환값·문구는 전혀 안 바꿨다. app.py 자신에 정의된 라우트 함수 두 개를 "
     "고쳤다 — import하는 별도 모듈이 아니라, 재시작해야 새 가드가 실제 요청에 "
     "반영된다. 회귀테스트(test_scan_round544_fixes.py, 40개 검사) 신설 — [0] 소스: "
     "두 함수 모두 이전값 비교 가드·순서(루프→가드→append) 확인, 형제 형식검사·"
     "biz_no·좌표분기는 무수정 확인, app.py 전체 ast.parse 성공. [1] 준비 — 협력사 "
     "2곳(현재코드용·구코드재현용)+보험사 2곳, 전부 실값으로 시드. [2][5] 실행(진짜 "
     "Flask app+test_client+격리 스크래치 DB, 진짜 PATCH 라우트) — 마이페이지 저장 "
     "버튼이 실제로 보내는 것과 같은 payload(무변경 통째 재전송)를 그대로 다시 "
     "보내도 unchanged:true·로그 0건. [3][6] 회귀 안전 — 필드 하나(region/dept)만 "
     "실제로 바뀌면 그 필드만 담은 로그 정확히 1건, 나머지 필드 오염 없음. [4] 회귀 "
     "안전 — email 실변경 시 email_source도 정상 갱신. [7][8] 원인 재현 — app.py·"
     "run_all_tests.py는 건드리지 않고 이번 수정 직전의 실제 함수 본문을 문자열로 "
     "재구성(exec, round543과 같은 방식)해 완전히 손대지 않은 별도 협력사·보험사에 "
     "같은 무변경 재전송을 실행하면 옛 코드는 실제로 다섯/네 필드 전부를 '바뀌었다'고 "
     "우기는 거짓 로그를 정확히 1건씩 남김을 실측 — 이 회귀의 실제 탐지력을 "
     "인과관계로 증명(actor를 [2]~[6]과 겹치지 않게 분리해 LIKE 조회 교차집계를 "
     "차단). 첫 실행(actor 분리 전 1차 시도는 로그 교차집계로 2건 오탐 → actor 분리 "
     "수정 후) 40/40 통과."),
    ("test_scan_round545_fixes.py", "스캔 545라운드 회귀 — 지시받은 신선한 각도 (5) "
     "'날짜/기간 표시의 반올림·버림 방향이 사용자에게 유리한지 불리한지 "
     "일관되는지'를 직접 조사(하위위임 없음)해 templates/partner_portal.html "
     "dlText()(2561행, '진행중 입찰 공고' 표의 '마감' 열 — 시공사가 입찰 여유를 "
     "판단하는 숫자)에서 발견 — h(남은 시간, 시간 단위)>=1 분기가 "
     "`Math.round(h)+'시간'` 이라 h=1.5(정확히 1시간30분 남음)에서 JS 의 "
     "'.5 는 위로' 반올림 때문에 '2시간 남음'이 찍혔다(최대 약 30분 과대평가, "
     "h=1.99 처럼 1시간59분대에서도 마찬가지). 같은 파일의 형제 카운트다운 "
     "둘은 이미 반대 방향 관례를 지킨다 — leftText()(1210행)의 정수 시간 "
     "자릿수는 항상 Math.floor(분 자릿수만 반올림+60분 캐리, 오차 최대 30초), "
     "dpLeft()(766행)는 분 단위를 통째로 Math.floor(항상 과소평가). dlText() "
     "자신의 h<1 분기도 라운드74가 '분을 반올림해 60분이 단독 표기되는' "
     "결함은 고쳤는데 바로 옆 h>=1 분기(반대 방향의 과대평가)는 그때 손대지 "
     "않았다 — round74 회귀테스트의 node 실행값(0.9999·0.999·0.5·2·0)에도 "
     "이 분기를 가르는 1<h<2 구간이 없어 지금까지 안 걸렸다. 실사용 영향 — "
     "시공사가 '2시간 남았다'며 여유를 부리다 실제로는 1시간30분 뒤 마감돼 "
     "입찰 기회를 놓칠 수 있다(다른 두 카운트다운과 정반대로 사용자에게 "
     "유리한 착시를 주는 방향이라 정책이 갈라져 있었다). 고침 — 새 정책·새 "
     "헬퍼 없이 형제 leftText 의 관례(정수 시간 자릿수는 Math.floor)를 그대로 "
     "이식 — `Math.round(h)` → `Math.floor(h)` 한 줄만 바꿨다(h<1 분기·label·"
     "urgent 판정·반환 HTML 구조는 무수정). 정적 템플릿이라 app.py 자신의 "
     "함수도 app.py 가 import 하는 .py 모듈도 아니지만, .env 의 "
     "BOKGUON_ENV=prod 로 실서비스는 IS_PROD=True 이고 app.py 가 "
     "TEMPLATES_AUTO_RELOAD=not IS_PROD(156행)로 이를 꺼 두므로 Jinja 가 "
     "컴파일된 템플릿을 캐시한다 — 이 수정도 프로세스 재기동 전까지는 "
     "반영되지 않는다. 회귀테스트(test_scan_round545_fixes.py, 20개 검사) "
     "신설 — round25·round74 와 같은 전제(중괄호 균형)로 dlText() 본문을 "
     "실파일에서 그대로 뽑아 node 로 실행(Date.now() 의존부만 round74 와 "
     "동일하게 우회 치환, 로직은 원본 그대로). [0] 소스: 고친 자리·형제 "
     "leftText/dpLeft·round74 수정분 무수정 확인. [1] 실행 — h=1.5·1.99·1.01 "
     "전부 '1시간'(과대평가 없음), 통제군 h=2(정수)는 그대로 '2시간', 회귀 "
     "안전 h=0.9999(라운드74 수정분)·h=0.5 도 그대로. [2] 원인 재현 — 이번에 "
     "고친 딱 한 줄만 메모리 문자열에서 되돌려(실파일은 전혀 안 건드림) 다시 "
     "돌리면 옛 코드는 h=1.5·1.99 둘 다 실측으로 '2시간'을 찍어 이 회귀의 "
     "실제 탐지력을 인과관계로 증명. 첫 실행 20/20 통과."),
    ("test_scan_round546_fixes.py", "스캔 546라운드 회귀 — 지시받은 신선한 각도들"
     "(카운트다운 반올림 전수확장·금액 부동소수점·동시접속 오류메시지·예약취소 "
     "큐·알림채널 캐시)을 직접 조사(하위위임 없음)했으나 전부 이미 안전했다"
     "(카운트다운은 545가 마지막 구멍을 막았고, admin.js 의 남은 Math.round/"
     "floor 는 전부 진행률바 너비이거나 '경과일수' 표시라 방향성 문제와 무관, "
     "VAT_RATE=10 가 하드코딩 상수라 admin.js:3653 의 부가세 분해가 "
     "Math.round 를 써도 파이썬 round() 의 banker's rounding 과 절대 갈릴 수 "
     "없음을 수학적으로 확인, 캠페인 취소 이중클릭은 507이 이미 가드 완비, "
     "'예약 발송' 자동 실행 큐 자체가 이 앱에 없음(알림은 '발송대기'까지만 "
     "기록되고 실발송은 계약 전), 포털별 알림채널 on/off 설정 기능 자체가 "
     "없음). 그러다 543·544가 고친 '값이 안 바뀌어도 UPDATE+로그를 쏘는' "
     "패턴의 형제를 다시 훑다가 api_me_update(PATCH /api/me, app.py:1839 "
     "부근 — 운영자 '내 계정' 모달의 이름 저장)에서 발견 — 543(api_admin_"
     "update 의 name 분기)·544(api_partner_profile_update·api_insurer_"
     "profile_update)가 근거로 든 형제 목록에 못 든 네 번째 형제였다: 543/544 "
     "는 '남의 계정을 고치는 자리'와 '협력사·보험사가 자기 마이페이지를 "
     "고치는 자리'를 훑었지만 '관리자가 자기 자신의 마이페이지를 고치는 "
     "자리'(api_partner/insurer_profile_update 의 직접 대응짝)는 빠져 있었다. "
     "수정 전 코드는 `conn.execute(\"UPDATE admins SET name=? WHERE "
     "username=?\", ...)` 뒤에 곧장 `DB.log(..., \"내 정보 수정\", f\"이름 → "
     "{name}\")`를 쏴 새 이름이 옛 이름과 같은지 비교하는 코드가 전혀 없었다. "
     "실사용 영향(프론트 코드로 확인) — admin.js myAccount()(2961행)가 "
     "'내 계정' 모달의 #my_name 입력칸을 현재 이름으로 미리 채우고, "
     "saveMyName()(3072행, 비밀번호 변경과 별개의 독립 버튼)은 그 값을 그대로 "
     "PATCH 하므로 아무것도 안 고치고 '이름 저장'만 눌러도 예외 없이 거짓 "
     "'내 정보 수정' 로그가 남았다. 고침 — 새 정책·새 헬퍼 없이 형제 넷"
     "(api_admin_update name 분기 1787행·api_partner_profile_update 3170행·"
     "api_insurer_profile_update 3343행·_sub_update_impl 3390행)과 같은 관례"
     "('새값!=옛값일 때만 UPDATE+로그')를 이식 — api_me_update 는 앞서 로드된 "
     "행이 없어 `cur = one(conn.execute(\"SELECT name FROM admins WHERE "
     "username=?\", ...))`를 새로 추가한 뒤 그 비교로 감쌌다. 빈 이름 400 "
     "검증·session 갱신·반환값은 무수정. app.py 자신의 라우트 함수를 고쳤다 "
     "— import 하는 별도 모듈이 아니라 재시작해야 반영된다. 회귀테스트"
     "(test_scan_round546_fixes.py, 23개 검사) 신설 — [0] 소스: 새 SELECT·"
     "가드·순서 확인, 형제 셋(543·544 가드)은 무수정 확인, ast.parse 성공. "
     "[1]~[2] 실행(진짜 Flask app+test_client+격리 스크래치 DB, 진짜 PATCH "
     "라우트) — '내 계정' 모달이 실제로 보내는 것과 같은 payload(현재 이름 "
     "그대로)를 재전송해도 지금 코드는 '내 정보 수정' 로그 0건. [3] 회귀 "
     "안전 — 이름이 진짜로 바뀌면 정확히 1건, 문구도 정확. [4] 원인 재현 — "
     "app.py·run_all_tests.py는 건드리지 않고 수정 직전 함수 본문을 문자열로 "
     "재구성(exec, round543·544와 같은 방식)해 완전히 손대지 않은 별도 "
     "관리자에게 같은 무변경 재전송을 실행하면 옛 코드는 실제로 '이름 → "
     "이민수546' 거짓 로그를 1건 남김을 실측 — 이 회귀의 실제 탐지력을 "
     "인과관계로 증명. [5] 세 관리자 로그 집계 교차오염 없음(전체 2건 — "
     "진짜 변경 1건 + 옛코드 재현 1건). 첫 실행 23/23 통과."),
    ("test_scan_round547_fixes.py", "스캔 547라운드 회귀 — 지시받은 신선한 각도 예시(photo_ai "
     "AI분류 타임아웃 잔류·RE_PHONE/RE_EMAIL 정규식 오탐·region 자유입력 오탈자·관리자 "
     "메모 삭제 가능여부·문서 워터마크)를 직접 조사(하위위임 없음)했으나 photo_ai 는 "
     "이미 30초 데드라인 초과분이 '대기'로 안전히 남고 담당자 수동 재분류 라우트"
     "(api_photo_reclassify, app.py:12763)가 이미 있음을 확인, RE_PHONE/RE_EMAIL 은 "
     "이미 12개 호출부 전수(round484·80)가 형제 누락만 다뤘고 패턴 자체(플러스태그 "
     "이메일 통과·010 외 번호 형식 등)도 기존 업무 범위에서 문제 없음을 확인, 관리자 "
     "메모는 이미 물리 DELETE 라우트(api_memo_delete, app.py:1554, require_role "
     "중간관리자)가 존재해 삭제 가능함을 확인, 문서 워터마크·발급번호는 그런 기능 "
     "자체가 이 서비스에 없어(견적서·정산명세서 PDF/엑셀 생성부 전수 확인) 결함이 "
     "아니라 미구현 — 대신 db.py region_matches()/norm_regions()(시/도 수준 정규화, "
     "round61·165·186·196·333이 이미 감사)와는 완전히 별개로 dispatch.py 가 자기만의 "
     "구/시/군 단위 지역 열쇠 추출 함수 _region_key()(102행, round511이 '대구' 한 "
     "건만 고쳤을 뿐 이 세션 각도로는 처음 재감사)를 갖고 있음을 발견 — 시/도 접두어를 "
     "뗀 뒤 '구'·'시'·'군'으로 끝나는 첫 토큰을 찾는데, 한국어 구어체는 그 접미어를 "
     "흔히 생략한다('인천 남동구'→'인천 남동', '서울 강서구'→'서울 강서'). 그러면 "
     "반복문이 그 토큰을 못 찾고 parts[0](시/도 자기 자신)으로 폴백해 '남동'·'강서' "
     "같은 세부지역이 통째로 사라지고 '인천'·'서울'만 남는다 — 하필 사건등록 화면 "
     "자신의 안내문구(templates/insurer_portal.html #c_region, placeholder=\"예: 인천 "
     "남동\")가 바로 이 구어체를 예시로 들어, 안내를 그대로 따르면 매번 이 결함에 "
     "걸린다. candidates()는 이 열쇠로 partners.region/address 를 LIKE 검색해 \"같은 "
     "지역\"(1·2순위, 30분 도착이 관건인 출동 배차의 우선순위)을 정하므로, 뭉개진 "
     "열쇠는 실제로는 남동구만 부를 사건에 인천 전역(강화군 등 먼 지역 포함)을 "
     "\"같은 지역\"으로 우선 호출 대상에 넣는다. 실측(운영 DB, 읽기전용 SELECT — "
     "쓰기 없음): region 있는 사건 96건 중 28건(29%)이 이 모양('서울 강서'→'서울', "
     "'경기 용인'→'경기' 14건 반복접수, '인천 남동'→'인천' 등 placeholder 예시와 "
     "정확히 일치하는 사례 포함). 고침 — 새 정책·새 헬퍼 없이 이 함수가 이미 참조하는 "
     "db.SIDO(round511과 동일)를 재사용해, SIDO 에 없는(=시/도 자체가 아닌) 토큰 중 "
     "마지막 것을 최종 폴백으로 쓴다(dispatch.py:_region_key). 시/도만 적었을 때(예: "
     "'대구' 단독, round511 대조군)는 non_sido 가 비어 기존 parts[0] 폴백 그대로라 "
     "회귀 없음. 이 파일은 app.py 가 import 하는 별도 모듈이라 재시작해야 실제 자동 "
     "출동 수배에 반영된다(BUILD_HASH 는 app.py 자체 변경이 아니므로 로테이션 없음). "
     "회귀테스트(test_scan_round547_fixes.py, 35개 검사) 신설 — [1] 소스: 새 폴백 "
     "코드·round511 SIDO 예외 처리 모두 정확히 1번씩. [2] 실행 — 접미어 생략 구어체 "
     "9종(실측 사례 기반) 전부 정상 추출 + round511 UNIT_CASES 9개·주소 폴백 전부 "
     "재확인(회귀 없음). [3] 실행(진짜 sqlite3 :memory: + 실제 dispatch.candidates(), "
     "round130·511과 같은 공종 비격리 기법) — '인천 남동' 사건에 진짜 남동구 협력사와 "
     "강화군(가짜매칭 유발) 협력사를 넣어, 강화군은 안 섞이고 남동구만 \"같은 지역\""
     "으로 잡힘을 확인. [4] 되돌림-증명 — round511 시점 구현(이 세션이 고치기 직전 "
     "실제 원문)으로 런타임 monkeypatch(파일 미수정, 순수함수라 안전) 후 같은 시나리오를 "
     "재실행하면 강화군 협력사가 실제로 \"같은 지역\"으로 잘못 섞여 들어옴을 재현해 "
     "이 회귀의 탐지력을 증명, 이후 복원 확인. [5] 운영 DB 대조(읽기전용, 정보성) — "
     "뭉개진 사건 수가 옛 로직 28건 → 새 로직 0건으로 실측 감소. 첫 실행 35/35 통과."),
    ("test_scan_round549_fixes.py", "스캔 549라운드 회귀 — 오케스트레이터가 이미 닫힌 각도로 "
     "명시한 \"값 불변인데도 감사로그+UPDATE\" 패턴(api_admin_update round543·"
     "_sub_update_impl round421·api_partner_profile_update·api_insurer_profile_update·"
     "api_me_update round546, \"4곳 전수 닫음\")과 겹치지 않으려 직접 조사(하위위임 없음)한 "
     "결과, 정작 그 4곳을 고친 두 라운드(421·543) 자신이 서로를 \"형제\"로 지목하며 "
     "이식해 온 바로 그 관례(if 새값 != 옛값: 로 감싸고서야 UPDATE+로그)가 하자 처리 "
     "라우트(api_defect_update, PATCH /api/defects/<id>, app.py:14862)엔 아예 이식된 적이 "
     "없음을 발견 — 4곳 모두 '단일 정보 수정' 라우트였던 반면 이 라우트는 상태·귀책·"
     "심각도·기한을 한 번에 다루는 다중필드 라우트라 그동안의 4곳 전수 조사망에 안 "
     "걸렸던 것으로 보이는, 같은 결함 부류의 5번째 미발견 인스턴스. 상태(status) 분기는 "
     "이미 조기 unchanged 반환이 있는데, 바로 아래 resolution·severity·due_date·"
     "cost_bearer 4개 필드 루프(수정 전)는 'f in d' 만 보고 값 비교 없이 sets/vals 에 "
     "무조건 담았다 — det(로그 문구) 계산은 이미 str(row[f] or \"\")!=str(d[f] or \"\") 로 "
     "걸러 '거짓 변경 문구'는 안 만들었지만, 그 앞의 UPDATE 발사 자체를 막는 관문이 없어 "
     "값이 하나도 안 바뀌어도 (하자번호만 담긴 빈) '하자 처리' 로그와 no-op UPDATE 가 "
     "매번 났다. 실사용 영향(프론트 코드로 확인) — static/admin.js:defectAct(4051행)는 "
     "조치내용 입력칸(#d_res)을 매번 body={resolution: res}로 무조건 실어 보낸다(4083행) "
     "— 바로 그 옆(4085행)의 cost_bearer 는 \"값이 안 바뀌었으면 안 보낸다\"고 이미 "
     "방어해 뒀는데 resolution 자신은 그 방어가 없어, 조치내용을 안 건드리고 상태만 "
     "바꾸는 모든 정상 조작마다 내용 없는 '하자 처리' 로그가 하나씩 더 쌓였다. 고침 — "
     "새 정책·헬퍼 없이 4개 필드의 '실제로 바뀐 것' 판정을 changed_fields 리스트 "
     "하나로 만들어(app.py:14974 부근, 기존 det 의 비교식을 그대로 승격) sets 루프가 "
     "그 목록만 돌게 했다 — 새 비교 로직 없음. ⚠ 1차 시도는 det 계산도 changed_fields "
     "를 재사용하도록 통합했으나, 이 라운드 자신의 회귀테스트 신설 직후 이 실행기로 돌린 "
     "--quick 배터리가 그 리팩터로 test_scan_round6_fixes.py:131(정확한 소스 문자열 "
     "'for f in (\"cost_bearer\", \"severity\", \"resolution\", \"due_date\")' 로 "
     "귀책변경 감사문구를 확인)이 깨짐을 즉시 잡아내 — 동작은 동일해도 문자열만 달라진 "
     "회귀라, 옛 테스트를 고치는 대신 det 계산은 원래 형태(하드코딩 튜플) 그대로 남기고 "
     "sets 루프만 changed_fields 로 고쳤다(그래서 필드 튜플은 여전히 두 곳에 있다 — "
     "의도적 비-DRY, round6 호환이 우선). app.py 자신에 정의된 라우트라 재시작해야 "
     "반영된다(BUILD_HASH 로테이션 있음). 회귀테스트(test_scan_round549_fixes.py, "
     "21개 검사) 신설 — [0] 소스: changed_fields 정의·sets 루프 재사용(1곳)·필드 튜플 "
     "정확히 1번·det 는 round6 호환 위해 옛 형태 그대로임을 모두 확인. [1]~[2] "
     "실행(진짜 Flask app+test_client+격리 스크래치 DB, 진짜 PATCH 라우트) — admin.js "
     "가 실제로 보내는 것과 같은 payload(resolution·severity·cost_bearer·due_date "
     "전부 지금 값 그대로, status 없음)를 재전송해도 지금 코드는 '하자 처리' 로그 0건. "
     "[3] 회귀 안전 — 조치내용만 진짜로 바뀌면 정확히 1건, 문구도 old→new 정확하고 안 "
     "바뀐 필드는 안 섞임. [4] 원인 재현 — app.py·run_all_tests.py는 건드리지 않고 수정 "
     "직전 함수 본문을 문자열로 재구성(exec, round543·547과 같은 방식)해 완전히 별도인 "
     "세 번째 하자에 같은 무변경 재전송을 실행하면 옛 코드는 실제로 내용 없는 '하자 처리' "
     "로그를 1건 남김을 실측 — 이 회귀의 실제 탐지력을 인과관계로 증명. 첫 실행 21/21 "
     "통과, 전체 배터리(443/443)에서 round6 포함 회귀 없음 재확인."),
    ("test_scan_round550_fixes.py", "스캔 550라운드 회귀 — 지시받은 신선한 각도들"
     "(CSV/엑셀 내보내기 수식주입·인코딩, 대시보드 집계 0건/NULL/동률, 경매마감 스윕 대 "
     "투찰 경쟁조건, 사진/파일 삭제와 고아파일, 페이지네이션, 온보딩 서류검증, 보험사 "
     "일괄작업)을 직접 조사(하위위임 없음)했으나 전부 클린 — CSV·엑셀은 _csv_safe/_xl_safe "
     "가 전 내보내기 지점에 이미 있고, 대시보드는 COALESCE·pct() 헬퍼로 0건/NULL 을 이미 "
     "방어하며, 경매 마감은 BEGIN IMMEDIATE + 잠금 이후 재조회로 TOCTOU 가 없고, 사진삭제는 "
     "휴지통 이동+자식행(ai_reviews·damage_reads·defect_photos·fix_for) 정리까지 이미 "
     "처리하고, 페이지네이션은 서버쪽에 애초에 없으며(LIMIT 고정 목록뿐), 온보딩 엑셀은 "
     "화면과 같은 조회함수(_onboard_rows)를 공유하고, 보험사 일괄작업(paid-bulk)은 CAS+행별 "
     "skip 사유로 이미 방어됨을 각각 실제 소스로 확인. 이어서 기계적 전수조사 2건도 0건 — "
     "① AST로 app.py 의 @app.post/patch/delete 106개 함수 전부를 스캔해 'SELECT 로 읽고 "
     "쓰기까지 하면서 BEGIN IMMEDIATE 가 없는 라우트'가 0건임을 확인(이 저장소가 지금까지 "
     "10회 넘게 고쳐 온 TOCTOU 계열이 구조적으로 이미 전수 방어돼 있음을 재확인). ② "
     "check_csrf() 는 GET/HEAD/OPTIONS 를 검사하지 않는 표준 설계인데, 그 전제(GET 라우트는 "
     "쓰기를 안 한다)가 실제로 지켜지는지 같은 AST 스캔으로 @app.get() 106개를 대조해 "
     "UPDATE/INSERT/DELETE 를 직접 담은 GET 라우트 0건 확인(있었다면 <img src> 하나로 "
     "트리거되는 CSRF 구멍이었을 것). 두 전수조사가 전부 0건으로 나온 뒤, 지금까지 어느 "
     "라운드도 전담 조사한 적이 없는 보험사 API 연동 관리 구역(app.py:9091-9312)을 직접 "
     "읽다가 발견한 결함 — DELETE /api/insurers/<id>/apikey(api_insurer_apikey_revoke, "
     "app.py:9115)가 인바운드 API 키(api_key_hash·api_key_prefix·api_enabled) 세 컬럼만 "
     "지우고 아웃바운드 웹훅 서명키(webhook_secret)는 손대지 않았다. 형제 두 곳"
     "(api_insurer_apikey_issue·api_insurer_webhook_set)은 둘 다 "
     "'r.get(\"webhook_secret\") or (새로 생성)' 식이라 이미 값이 있으면 재사용한다"
     "(이 자체는 admin.js insWhSave 의 안내문 \"주소를 다시 저장해도 같은 값입니다\"가 "
     "명시하는 의도된 동작 — 손대지 않음). 문제는 '폐기' 라우트다 — 이 버튼과 재발급 "
     "버튼의 확인창은 둘 다 \"보험사 전산 연동이 즉시 끊깁니다\"·\"기존 키는 즉시 무효\"라며 "
     "같은 강도로 완전 차단을 약속하는데, 실제로는 api_key_hash 만 새로 나가고 "
     "webhook_secret 은 폐기 이전 값 그대로 되살아났다 — 키 유출을 의심해 폐기했다면 그 "
     "유출 경로가 webhook_secret 까지 함께 드러냈을 수 있는데 재발급 후에도 옛 서명키가 "
     "계속 유효해 위조 서명 웹훅을 보험사가 정상으로 오인할 창이 남는다. 지금 당장 새는 "
     "것은 아님을 직접 확인 — deliver_webhook()·sweep_webhook_retries()·"
     "api_insurer_webhook_test() 세 발송 경로 전부 secret 을 읽기 전에 api_enabled=0 을 "
     "먼저 보고 걸러 폐기 직후엔 안전하다(세 함수 다 실제로 호출해 실측, 아래 [1]) — 위험은 "
     "'폐기 후 재발급'으로 연동을 다시 켜는 시점에만 열린다. 고침 — 새 정책·헬퍼 없이 "
     "revoke 의 UPDATE 에 webhook_secret=NULL 한 컬럼만 더했다. NULL 로 비워 두면 다음 "
     "발급·웹훅 저장 때 형제의 'or' 분기가 자연히 새 시크릿을 만든다. ⚠ 1차 시도는 감사"
     "로그 문구에 '웹훅 서명키도 함께 무효화'를 조건부로 덧붙였으나, 그 직후 돌린 --quick "
     "배터리가 test_scan_round327_fixes.py를 깨뜨림을 즉시 잡아냈다 — 그 라운드가 이미 "
     "'형제(폐기·토글)는 기관명만 남긴다'는 exact-match 계약(감사로그가 API 키 조각 등 "
     "민감정보를 새로 흘리지 않는다는 위협모델)을 고정해 뒀기 때문 — 덧붙이려던 문구 "
     "자체는 민감정보가 아니었지만 같은 계약을 깨는 것은 같아, 로그 문구는 손대지 않고 "
     "DB 컬럼만 고쳐 그 기존 계약을 그대로 지켰다(round549 가 det/changed_fields 를 "
     "분리해 round6 계약을 지킨 것과 같은 원칙). 회귀테스트(test_scan_round550_fixes.py, "
     "25개 검사) 신설 — [0] 소스: webhook_secret=NULL 이 UPDATE 문 안에 있음·감사로그 문구는 "
     "형제와 같은 기관명-only 형식 그대로임·형제 두 곳(발급·웹훅설정)은 안 건드렸음을 확인. "
     "[1] 사전확인 — 세 발송 경로가 실제로 secret 을 읽기 전에 api_enabled=0 으로 막힘을 "
     "진짜 함수 호출로 실측. [2] 실행(진짜 라우트) — 키·웹훅이 설정된 보험사를 폐기하면 "
     "webhook_secret 이 NULL 이 되고 webhook_url 은 안 건드리며 감사로그는 round327 계약대로 "
     "기관명만 남음을 확인. [3] 회귀 안전 — 웹훅을 설정한 적 없는 보험사도 정상 동작. "
     "[4] 인과관계 증명 — 폐기 뒤 재발급하면 완전히 새 시크릿이 나고 옛 값은 다시 안 "
     "살아남을 실제 라우트 두 번 호출로 확인. [5] 원인 재현 — 수정 직전(즉 애초 결함 상태) "
     "함수 본문을 문자열로 재구성(exec, round543·547·549와 같은 방식)해 같은 시나리오를 "
     "실행하면 옛 코드는 정말 webhook_secret 을 그대로 남김을 실측 — 이 회귀의 탐지력을 "
     "인과관계로 증명. 등록 전 grep 으로 이 라우트를 참조하는 기존 테스트를 확인해 "
     "test_scan_round327_fixes.py(형제 함수의 감사로그 형식을 exact-match 로 검사) 1건을 "
     "찾아 개별 재실행(8/8)으로 충돌 없음을 확정한 뒤 등록 — 최종 25/25(round550 자체) 및 "
     "8/8(round327 재확인) 통과. app.py 자신의 라우트 함수를 고쳤으니 재시작해야 반영된다"
     "(BUILD_HASH 로테이션 예상)."),
    ("test_scan_round553_fixes.py", "스캔 553라운드 회귀 — round550이 145개 POST/PATCH/DELETE "
     "라우트 BEGIN IMMEDIATE 전수조사에서 유일하게 잠금 없는 곳으로 남겨 두고 "
     "\"다음 라운드 조사거리\"로 명시적으로 미뤄 둔 api_application_create(입점신청 직접접수, "
     "app.py:7675)를 이번 라운드가 직접 조사(하위위임 없음)해 실제로 재현·수정. 결함 — "
     "업체명 중복확인(SELECT ... status IN ('신규','서류검토'))과 사업자번호 교차확인"
     "(SELECT ... FROM partners WHERE biz_no=?) 둘 다 BEGIN IMMEDIATE 없이 read-then-write라, "
     "전화 상담원 둘이 같은 업체를 거의 동시에 접수하거나 화면 이중클릭 시 두 요청 모두 "
     "\"심사 중인 신청 없음\"을 읽어 둘 다 INSERT에 성공 — 같은 업체의 대기 신청서가 2건 "
     "생긴다. 영향은 과장하지 않는다 — 활성 업체 중복까지는 안 번진다(그 최종 관문인 "
     "api_application_update는 이미 round189/248/429가 BEGIN IMMEDIATE+DUP_BIZNO로 막아 "
     "뒀고 이번 라운드는 그쪽을 안 건드림, 재확인 완료). 고침 — 새 헬퍼 없이 형제 "
     "api_application_update가 이미 쓰는 것과 정확히 같은 자리·같은 방식(BEGIN IMMEDIATE를 "
     "conn = DB.get_db() 직후에, 두 중복확인의 조기반환 conn.close()를 "
     "conn.rollback(); conn.close()로)만 옮겼다 — 사이의 _picked_coords(d)는 순수 계산이라 "
     "잠금을 오래 안 쥔다. 회귀테스트(test_scan_round553_fixes.py, 17개 검사) 신설 — [0] 소스: "
     "BEGIN IMMEDIATE 위치·두 rollback+close·형제 함수 불변 확인. [1] 준비. [2] 순차 회귀 "
     "안전 — 동시성 없을 때는 업체명·사업자번호 중복 둘 다 지금까지와 똑같이 409(회귀 없음). "
     "[3]+[4] threading.Barrier로 실제 두 요청을 동기화하고 _picked_coords()에 테스트 전용 "
     "인위적 지연(0.25초, 실제 코드는 무관)을 걸어 잠금 대기 창을 결정론적으로 넓힌 뒤 — "
     "지금 코드는 정확히 하나만 200 성공·하나는 409, 대기 신청서 1건. 그 직후 이번 수정 "
     "직전 원문을 문자열로 재구성해(exec, round543·547·549·550과 같은 기법 — 실제 .py 파일은 "
     "전혀 안 건드림) 같은 동시접수를 실행하면 옛 코드는 둘 다 200 성공해 대기 신청서가 "
     "실제로 2건 생김을 실측 — 이 회귀의 탐지력을 인과관계로 증명. 등록 전 grep으로 이 "
     "라우트를 참조하는 기존 테스트 10개(round63·79·80·155·177·248·288·417·429·484)를 "
     "찾아 개별 재실행 — round417만 실패(그 테스트의 되돌리기용 하드코딩 리터럴 NEW_1/OLD_1이 "
     "이번 수정으로 conn.close()가 conn.rollback(); conn.close()로 바뀐 그 줄을 정확히 문자열째 "
     "물고 있어 더 이상 매칭이 안 됨 — round417 자신이 검증하는 실제 동작(Markup 이스케이프)은 "
     "그대로 살아 있었고 [1]~[5]는 계속 통과, 문자열이 안 맞아 되돌리기만 실패하는 순수 "
     "테스트-핏처 노후화였다). round553의 잠금 변경과 round417의 이스케이프 변경은 서로 "
     "독립된 변수이므로, round417의 NEW_1/OLD_1 둘 다에 rollback();을 그대로 반영해 잠금은 "
     "유지한 채 이스케이프 유무만 바뀌게 갱신 — round417 재실행 14/14로 정상화(app.py는 그 "
     "테스트의 임시 되돌리기 뒤 원본과 바이트단위 동일 확인). 나머지 9개는 수정 전부터 그대로 "
     "10/10·13/13·15/15·24/24·25/25·51/51·10/10·24/24·16/16 통과. 이번 라운드 자체도 4연속 "
     "재실행 전부 17/17로 타이밍 flake 없음 확인. app.py 자신의 라우트 함수를 고쳤으니 "
     "재시작해야 반영된다(BUILD_HASH 로테이션 예상)."),
    ("test_scan_round554_fixes.py", "스캔 554라운드 회귀 — 수동잠금해제(api_unlock_login, "
     "app.py:2565-)가 라운드488이 새로 만든 \"OTPSETUP:\" 창구(2단계 인증 등록확인 "
     "api_otp_confirm 의 무차별대입 방어)를 누락한 결함. 직접 조사(하위위임 없음) — 오케스트"
     "레이터가 준 \"이미 닫힌 각도\" 목록이 이 함수 자체는 언급하지 않아, 이 함수 자신의 "
     "독스트링·주석이 스스로 명시한 확장 계약(\"새 창구가 생기면 이 목록만 늘린다\", 라운드175가 "
     "적어 두고 라운드414가 PW:/PWX: 추가 때 실제로 지킨 바로 그 규칙)을 실마리로 저장소 전체의 "
     "_recent_fails/_log_attempt 호출부를 전수 grep해 실제 접두사 7종(무접두 admin·P·I·OTP·"
     "PW·PWX·OTPSETUP)을 확정한 뒤 api_unlock_login()의 keys 튜플과 대조 — OTPSETUP: 하나만 "
     "빠져 있음을 발견. run_all_tests.py의 라운드488 등록 문구를 대조해 그 라운드가 "
     "api_otp_confirm() 자신만 고치고 api_unlock_login()은 전혀 안 건드렸음을 재확인(라운드175·"
     "414가 이미 두 번 겪은 \"새 창구 추가 시 이 목록 갱신 누락\" 클래스가 세 번째로 재발). 영향 — "
     "등록확인 코드를 5회 틀려 OTPSETUP: 창구만 잠긴 계정에 운영자가 수동잠금해제를 불러도 "
     "{\"ok\":true,\"cleared\":0}으로 \"잠겨 있지 않았다\"는 거짓 확인을 주고 실제로는 여전히 "
     "잠겨 있다(이 함수 자신의 독스트링이 막으려던 바로 그 사고). 고침 — keys 튜플에 "
     "\"OTPSETUP:\"+uname 하나를 추가하고 SQL IN 자리수를 6개(?,?,?,?,?,?)에서 7개로 늘렸다"
     "(라운드414가 PW:/PWX: 두 개를 추가할 때 쓴 것과 정확히 같은 방식, 새 정책·새 헬퍼 없음). "
     "회귀테스트(test_scan_round554_fixes.py, 19개 검사) 신설 — [0] 소스: OTPSETUP: 이 keys "
     "튜플·SQL 자리수 사이에 있음, 기존 6개 창구 전부 회귀 없음, 저장소 전체 접두사 집합이 "
     "정확히 이 7종과 일치(새 창구 누락 감시). [1] 준비. [2] 실제 Flask 라우트(A.app.test_client)"
     "로 등록확인을 반복 오답해 OTPSETUP: 창구를 실제로 잠금(라운드488 방어 자체 회귀 없음). "
     "[3] 지금 코드로 수동잠금해제 호출 — OTPSETUP: 실패기록이 실제로 0건이 됨을 실측. [4] "
     "되돌림-증명 — 실제 on-disk app.py 파일은 전혀 건드리지 않고, 수정 직전 Read로 확인한 "
     "원문을 별도 함수로 문자열 재구성해(exec, round543·547·549·550·553과 같은 기법) app 모듈 "
     "네임스페이스 사본에서 직접 호출 — 옛 코드는 200·ok:true를 돌려주면서도 OTPSETUP: 실패"
     "기록이 그대로 남음을 실측해 이 회귀의 탐지력을 인과관계로 증명. 등록 전 이 함수를 문자열"
     "째 하드코딩해 다루는 기존 테스트 1개(round414, OLD_3/NEW_3로 revert-and-prove)를 grep으로 "
     "찾아 개별 재실행한 결과 [7-3]만 실패 확인 — round417을 round553이 갱신한 것과 같은 원인"
     "(NEW_3 리터럴이 이번 keys 튜플·주석·SQL 변경으로 더 이상 실제 텍스트와 안 맞아 "
     ".replace()가 no-op 되고 \"되돌린\" 파일이 사실은 지금 코드 그대로라 STILL_LOCKED가 기대와 "
     "반대인 False로 나옴, round414 자신이 증명하려는 PW:/PWX: 부재 결함과는 무관한 순수 "
     "테스트-핏처 노후화). round414의 NEW_3만 이번 라운드의 실제 app.py 문구로 갱신(OLD_3는 "
     "이번 변경과 무관해 그대로 둠) — round414 재실행 13/13으로 정상화. 최종: round554 자체 "
     "19/19, round414 재확인 13/13 통과. app.py 자신의 함수를 고쳤으니 재시작해야 반영된다"
     "(BUILD_HASH 로테이션 예상)."),
    ("test_scan_round555_fixes.py", "스캔 555라운드 회귀 — test_scan_round3_fixes.py의 가중치 "
     "픽스처가 round424의 부분 UNIQUE 인덱스와 충돌해 깨져 있던 결함, 1건(테스트 픽스처 자체의 "
     "결함, app.py는 무죄). 과제안내문의 '유실된 이중입찰 제안 칩' 각도를 처음부터 재조사 — "
     "round3 [1](추천 가중치 정합)이 같은 경매·같은 협력사(pid)로 활성 입찰을 두 번 INSERT하는 "
     "픽스처를 쓰는데, round424가 그보다 훨씬 뒤에 db.py 마이그레이션으로 추가한 부분 UNIQUE "
     "인덱스(idx_bids_active_partner, ON bids(auction_id,partner_id) WHERE voided_at IS NULL)가 "
     "이제 그 두 번째 INSERT를 IntegrityError로 거부함을 실측 재현(오늘자 실제 스키마에 round3 "
     "원문 그대로의 반복문을 exec으로 돌려 확인) — round3를 실제로 돌리면(전체 배터리, HTTP 구간) "
     "가중치 재계산과 무관한 스키마 충돌 트레이스백으로 죽어 의도한 검증 8개가 하나도 실행되지 "
     "못한다. round554가 겪은 round414류(테스트-픽스처가 현실을 못 따라온 노후화)와 같은 성격이지 "
     "app.py 결함이 아님 — api_partner_bid()·api_partner_reauction_bid()(round424 자신이 이미 "
     "확인)는 재투찰을 항상 UPDATE로 처리해 파트너당 활성 입찰 1건만 유지하고, api_insurer_bids도 "
     "voided_at IS NULL인 것만 후보로 보므로 '한 업체가 같은 경매에 활성 입찰을 두 개 가진 채 "
     "화면에 뜨는' 이 픽스처의 전제 자체가 실제 애플리케이션 어디서도 나올 수 없었다. 고침(픽스처만, "
     "새 정책·앱 코드 변경 없음): test_scan_round3_fixes.py의 두 번째 입찰을 별도 협력사(pid2)로 "
     "바꿔 서로 다른 두 업체가 각자 하나씩 입찰한 정상 경쟁 시나리오로 교체하고 끝에서 그 협력사 "
     "행도 정리 — round3 [1]이 실제로 보는 것(가중치를 바꾸면 최저가 입찰의 점수 자체가 바뀐다)은 "
     "입찰이 여럿이기만 하면 성립해 검증 의도는 그대로다. 회귀테스트(test_scan_round555_fixes.py, "
     "14개 검사) 신설 — [1] 소스 확인. [2] 스크래치 DB(오늘자 스키마)에 인덱스 실재 확인. [3] "
     "되돌리기 — round3의 옛 코드를 문자열로만 재구성해 exec()으로 실행(on-disk 파일은 안 건드림), "
     "실제 IntegrityError 재현. [4] 고쳐진 픽스처(서로 다른 두 협력사)는 제지 없이 삽입됨을 확인. "
     "[5] 실제 Flask 라우트(A.app.test_client, insurer 세션 직접 주입)로 gap 없이 200 응답과 입찰 "
     "2건을 확인하고, bid_w_price 설정을 낮춰 재조회하면 최저가 입찰(bids[0], 가격순 정렬이라 항상 "
     "같은 건)의 점수 자체가 달라짐을 실측해 round3 원래 검증 의도가 새 픽스처로도 성립함을 증명 — "
     "첫 실행 확인 과정에서 자체 어서션 1건(트랜잭션 롤백 시 남는 행수를 1로 잘못 기대 — sqlite3는 "
     "두 INSERT가 커밋 없이 한 트랜잭션을 공유해 rollback하면 0건이 맞음) 수정 후 14/14 통과. "
     "app.py·db.py 변경 없음(테스트 파일 2개만 수정/신설) — 서버 재기동 불필요, BUILD_HASH 불변."),
    ("test_scan_round556_fixes.py", "스캔 556라운드 회귀 — 과제가 제시한 신규 각도('관리자 생성 "
     "사건 vs 보험사 생성 사건의 필드 정합성')를 직접 조사해 찾은 결함 1건. cases.source 컬럼은 "
     "db.py 스키마 주석부터 '포털/ API/ 관리자 수동' 세 갈래(통계·감사용, ALTER 기본값 '포털')를 "
     "문서화해 두고 있는데, 형제 경로 _create_case(보험사 포털·v1 API 공용)는 이미 '포털'/'API'를 "
     "명시로 채우는 반면 api_case_create(관리자 콘솔 전용, POST /api/cases)만 이 컬럼이 INSERT문에 "
     "빠져 있어 ALTER 기본값('포털')으로 조용히 떨어졌다 — 관리자가 등록한 사건이 전부 '포털 접수'로 "
     "잘못 집계되는 결함. 관리자 콘솔 경로가 스키마 마이그레이션으로 나중에 추가된 컬럼을 못 따라와 "
     "형제와 갈라지는, 이 세션에서 이미 여러 번 잡힌 것과 같은 유형(라운드68·198·416·484)이라 같은 "
     "처방(형제 경로와 같은 값을 채운다)으로 고침 — api_case_create의 INSERT에 source 컬럼과 "
     "'관리자수동' 값을 추가(app.py). note 컬럼은 관리자 콘솔 화면에 애초에 입력 칸이 없어(기능 "
     "없음, 다른 종류의 문제) 손대지 않았고, warranty_months는 컬럼 DEFAULT 24가 _create_case의 "
     "하드코딩값(24)과 이미 일치해 드리프트가 없었다. 회귀테스트(test_scan_round556_fixes.py, 9개 "
     "검사) 신설 — [1] 소스 확인(INSERT문에 source 추가·'관리자수동' 리터럴·형제 경로 불변 확인). "
     "[2] 스크래치 DB에 source 컬럼 기본값이 여전히 '포털'인 전제 확인. [3] 되돌리기 — 옛(source "
     "누락) INSERT문을 문자열로만 재구성해 exec()으로 오늘자 스키마에 실행(on-disk 파일은 안 "
     "건드림), 관리자가 만든 사건도 '포털'로 오기록됨을 인과관계로 실측. [4] 실제 Flask 라우트 "
     "(A.app.test_client, 관리자 세션 직접 주입)로 POST해 source='관리자수동'이 정확히 남음을 확인. "
     "[5] 형제 경로(_create_case)를 '포털'/'API'로 각각 직접 호출해 세 갈래가 서로 침범 없이 동시에 "
     "성립함을 확인. app.py 1곳 수정(INSERT 컬럼·값 추가) — 서버 재기동 필요."),
    ("test_scan_round557_fixes.py", "스캔 557라운드 회귀 — manage.py:cmd_sweep()(예약 실행의 진짜 "
     "진입점)의 유일한 try 블록에 except가 없던 결함. 새 발견이 아니다 — round411·415·482·523·524 "
     "가 전부 독립적으로 같은 문장('cmd_sweep()의 유일한 try에도 except가 없어')을 남겼지만, 다섯 "
     "라운드 모두 이걸 근거로 더 안쪽(app.py 개별 스윕 함수 6종 — 411·415, dispatch.py의 "
     "_claim_lease() — 482·524)만 고치고 정작 그 방어들이 전부 모이는 이 바깥 경계 자체는 5라운드에 "
     "걸쳐 그대로 남겨 뒀다. 지금도 뚫려 있는 구체 경로 — dispatch.sweep_dispatches()는 처리 실패 시 "
     "자기 리스를 놓아준 뒤 의도적으로 다시 던진다(dispatch.py 961행 `except Exception: "
     "_release_lease(conn,\"오류\"); raise`). 이 예외는 cmd_sweep()의 무방비 try를 그대로 뚫고 "
     "main()(COMMANDS[cmd] 호출도 try 없음)까지 나가 프로세스를 죽인다 — 실제 예약 실행"
     "(복구온_예약실행_등록.ps1)은 콘솔 없는 pythonw.exe를 표준출력 리다이렉트 없이 부르므로 그 "
     "트레이스백은 어디에도 남지 않는다. cli_sweep job_locks 마커도 이번 회차엔 못 쓰여 대시보드 "
     "배지는 30분 뒤 결국 적색이 되지만(그 자체는 의도된 설계, round B4의 '예약 실행이 실제로 돌았다는 "
     "별도 표식'), '왜' 멈췄는지는 bokguon.log를 grep해도 0건이었다. 고침 — 형제(_sweep_if_due, "
     "app.py 라운드536)와 같은 처방을 이 바깥 경계에도 적용: 배치 전체를 try/except Exception으로 "
     "감싸 A.app.logger.exception()으로 남기고(이미 커밋된 이전 스윕은 되돌리지 않는다), 종료코드도 "
     "실패(1)로 보고한다(예약실행_등록.ps1의 -RunNow가 LastTaskResult를 그대로 신뢰하므로 실패를 0으로 "
     "보고하면 그 확인 절차 자체가 무의미해진다). res 변수도 A.sweep_auctions() 자신의 실패에 대비해 "
     "기본값을 갖도록 사전 초기화(안 하면 맨 아래 res['scanned'] 참조가 UnboundLocalError로 또 죽어 "
     "방금 남긴 실패 로그까지 함께 지운다). 회귀테스트(test_scan_round557_fixes.py, 14개 검사) 신설 — "
     "[1] 소스 확인(except Exception 추가·sweep_err·A.app.logger.exception 호출·return 1). "
     "[2] 스크래치 DB 준비, cli_sweep이 아직 NULL(한 번도 안 돎)인 전제 확인. [3] 되돌리기 — 옛(except "
     "없는) cmd_sweep 모양을 문자열로만 재구성해 exec()로 실행, A.sweep_review_reminders를 예외를 "
     "던지도록 몽키패치한 뒤 실제로 예외가 밖으로 새는 것을 인과관계로 실측(on-disk manage.py는 안 "
     "건드림). [4] 같은 몽키패치 상태에서 진짜 M.cmd_sweep()을 직접 호출 — 예외가 안 새고, 종료코드 "
     "1을 반환하고, A.app.logger.exception이 실제로 불렸고, cli_sweep 마커는 여전히 NULL로 남아 "
     "대시보드 배지가 계속 '멈췄다'를 정확히 가리킴을 확인. [5] 몽키패치 해제 후 --dry-run과 정상 "
     "실행이 각각 여전히 0을 반환하고, 정상 실행은 cli_sweep 마커를 실제로 남김을 확인(회귀 없음). "
     "첫 실행 14/14 통과. manage.py 1곳(cmd_sweep) 수정 — app.py가 import하지 않는 독립 CLI라 서버 "
     "재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round558_fixes.py", "스캔 558라운드 회귀 — round557이 남긴 각도를 직접 조사(하위위임 "
     "없음): dispatch.py:sweep_dispatches()의 같은 루프 안 형제 셋(출동 실패 처리기·회차소진 처리기·"
     "재수배 처리기) 중 재수배 처리기(라운드182·411)만 '대상 하나의 실패가 나머지 전부의 처리를 막아선 "
     "안 된다'(이 함수 docstring 이 못박은 존재 이유)는 원칙으로 이미 rollback 후 continue 하는데, 나머지 "
     "둘은 여전히 `except Exception: conn.rollback(); raise`로 남아 대상 하나의 일시적 DB 락 경합만으로도 "
     "이 스윕(최대 50건)의 나머지 대상 전부, 나아가 manage.py cmd_sweep()(라운드557이 고친 바깥 경계)의 "
     "이후 단계(무입찰경보~웹훅재전송·cli_sweep 생존신호)까지 이번 회차 전부 건너뛰게 만들었다. 조사 결과 "
     "이 둘이 형제와 다르게 raise 해야 할 트랜잭션상 이유는 없었다(rollback 이 이미 이 대상의 미완료 "
     "트랜잭션을 정리하므로 다음 대상의 BEGIN IMMEDIATE는 안전하다). 고침 — 출동 실패 처리기는 rollback 후 "
     "로그하고 continue(바로 위 CAS-미스 분기 자신과 같은 모양), 회차소진 처리기는 rollback 후 로그만 하고 "
     "raise 하지 않음(이 if가 for 몸통의 마지막이라 continue 없이도 자연히 다음 대상으로) — res['gaveup'] "
     "증가도 성공시에만 세도록 try 안(commit 직후)으로 옮김(실패를 성공으로 잘못 세지 않는다). 회귀테스트"
     "(test_scan_round558_fixes.py, 32개 검사) 신설 — [1] 소스 확인. [2] 지금 소스에서 그 두 지점만 짧고 "
     "고유한 표식으로 옛(raise) 모양으로 되돌린 사본을 준비(exec용, on-disk 파일은 안 건드림). [3] 스크래치 "
     "DB 준비. [4]-[5] 첫 처리기만 실패시켜 실제 DP.sweep_dispatches()는 안 죽고 둘째 대상까지 처리되는데 "
     "옛 사본은 실제로 예외가 새고 둘째 대상이 아예 손도 안 닿음을 인과관계로 실측. [6]-[7] 같은 방식으로 "
     "둘째 처리기(회차소진)도 실측. 첫 실행 32/32 통과 — 이 과정에서 round411 회귀테스트의 사전확인 문자열 "
     "하나가 메시지 텍스트 없이 들여쓰기+자리표만 썼다가 이번에 회차소진 처리기에 새로 생긴 같은 모양의 "
     "rollback+로그와 우연히 겹쳐 오탐하는 것을 발견 — 그 문자열에 메시지('자동 재수배 실패')를 추가해 "
     "정확히 재수배 처리기 하나만 가리키도록 좁힘(round411 재실행 13/13 통과 확인). dispatch.py 1곳(두 "
     "처리기) 수정 — app.py가 import하는 모듈이라 서버 재기동 필요·BUILD_HASH 불변(dispatch.py 변경은 "
     "app.py 자신의 내용이 아니라 BUILD_HASH에 안 반영되는 것이 이 세션의 기존 확인된 패턴)."),
    ("test_scan_round559_fixes.py", "스캔 559라운드 회귀 — round557·558이 닫은 '예약작업이 조용히 실패한다' "
     "앵글의 세 번째 변종을 직접 조사(하위위임 없음): 이번엔 실행 시점이 아니라 *등록* 시점. "
     "deploy/windows_setup.ps1 7단계가 예약작업 4개(복구온_DB백업·복구온_사진백업·복구온_접속기록정리·"
     "복구온_개인정보파기)를 등록할 때 전부 `Register-ScheduledTask ... | Out-Null` 뒤 조건 없이 Ok 를 "
     "찍었다 — 이 파일 25행 $ErrorActionPreference='Stop' 이 있어도 이 cmdlet의 CIM 오류는 승격되지 "
     "않는다는 사실을, 바로 같은 deploy/ 안의 형제 스크립트 두 개(복구온_예약실행_등록.ps1 121~141행· "
     "복구온_외부공개_등록.ps1 100~116행)가 이미 2026-08-06 실제 사고(\"Access is denied 인데 화면은 "
     "등록됐다고 했다\")로 겪어 -ErrorAction Stop + try/catch + 등록 뒤 Get-ScheduledTask 재조회로 고쳐 "
     "뒀는데, 그 처리가 그 두 스크립트에만 머물고 windows_setup.ps1 이 직접 등록하는 이 4곳(라운드296이 "
     "고친 건 pythonw.exe 콘솔깜빡임이라는 다른 결함이고 이 재조회 결함은 손대지 않았다)에는 한 번도 "
     "옮겨오지 않았음을 발견 — 권한 문제가 있는 PC에서 실행하면 DB 백업도, 처리방침이 공개 약속한 "
     "개인정보 파기(299~303행, 개인정보 보호법 §21·§30)도 전혀 등록 안 되는데 화면은 전부 초록 [OK]만 "
     "보일 수 있었다. 고침 — 형제 두 스크립트와 같은 처리를 함수 하나(Register-BokguonTask)로 모아 4개 "
     "호출 지점이 전부 그것만 쓰게 함(중복 대신 공유 지점 하나). 회귀테스트(test_scan_round559_fixes.py, "
     "21개 검사) 신설 — .ps1이라 monkeypatch 대신 round296과 같은 방식(실제 소스에서 중괄호 균형으로 "
     "함수 추출, 가짜 Register-ScheduledTask/Get-ScheduledTask 아래 PowerShell로 진짜 실행)을 따름: "
     "[1] 소스 확인(4개 호출지점 전부 새 함수 사용, 옛 원시호출 패턴 잔존 없음). [2] 형제 두 스크립트가 "
     "실제로 이 패턴의 원본임을 확인. [3] 전체 파일 PowerShell 파서 통과 확인. [4] 실제 함수를 성공/"
     "throw실패/2026-08-06 재현(조용히 반환하지만 재조회하면 없음) 3가지 시나리오로 실행 — 앞 둘은 기존 "
     "기대대로, 세 번째(핵심)는 재조회 안전망이 거짓 OK를 막음을 실측. 되돌리기 증명 — 실제 파일은 안 "
     "건드리고 옛 패턴을 메모리 문자열로만 재구성해 같은 조건에 돌리니 실제로 거짓 'OK'를 찍었음을 인과로 "
     "확인(대조군으로 진짜 throw 조건에선 옛 패턴도 거짓 OK를 못 찍음을 함께 확인해 과잉일반화 방지). "
     "테스트 작성 중 자체발견 2건: (a) 새로 쓴 설명 주석 자체가 'Register-ScheduledTask' 문자열을 담아 "
     "단순 개수셈 체크가 오탐할 뻔함 → 호출 지점 패턴만 보도록 수정, (b) Windows PowerShell 5.1이 "
     "리다이렉트된 stdout의 한글을 시스템 코드페이지로 써서 Python이 UTF-8로 읽으면 깨짐(round296이 겪은 "
     "입력측 BOM 문제의 출력측 짝) → 가짜 스크립트 서두에 [Console]::OutputEncoding=UTF8 추가로 해결. "
     "첫 실행 21/21 통과. deploy/windows_setup.ps1 1곳 수정 — app.py가 import하지 않는 독립 배포 "
     "스크립트라 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round560_fixes.py", "스캔 560라운드 회귀 — 관리자 콘솔 사건등록(api_case_create, "
     "POST /api/cases)이 발주 보험사 본인에게 '사건접수' 알림을 전혀 보내지 않던 결함. round556이 "
     "같은 두 함수(_create_case vs api_case_create)를 INSERT 컬럼 기준으로 대조해 source 누락을 "
     "잡았던 바로 그 자리를, 이번엔 notify() 호출 기준으로 다시 대조해 발견 — 형제(_create_case, "
     "보험사 포털·v1 API 공용, 4078행)는 사진 유무와 무관하게 두 분기 모두 발주 보험사 본인에게 "
     "audience_type='insurer' 알림을 보내는데(4186·4212행), api_case_create 위에 남아 있는 주석 "
     "①②③(보험사 경로가 대조군이라며 협력사·운영팀 알림 결함 3건을 고친 기록)이 스스로 증명하듯 "
     "그 대조군을 보고 협력사·운영팀 알림은 고쳤으면서 정작 대조군이 보내는 보험사 본인 알림은 "
     "옮기지 않았다 — 대상이 협력사·운영팀이지 보험사가 아니라 그 수정의 시야 밖에 있었던 것으로 "
     "보인다. 실측: 관리자 콘솔(전화·팩스 접수 대행)로 등록한 사건은 GET /api/insurer/notifications"
     "(audience_type='insurer' AND insurer_id=? 로 거름)에 단 한 건도 뜨지 않는다 — 협력사·운영팀은 "
     "새 공고를 아는데 정작 사건의 주인인 보험사만 모른다. 고침 — n_match 계산 뒤·DB.log() 앞, "
     "no_photo 분기와 무관한 공통 지점 1곳에 형제와 같은 문구의 notify(audience_type='insurer', "
     "insurer_id=insurer_id, ...) 호출을 추가(분기마다 넣지 않고 메시지만 삼항으로 갈라 정합 유지). "
     "note/warranty_months 컬럼 드리프트는 round556이 이미 '실질적 차이 없음'으로 조사를 끝낸 사안이라 "
     "재조사하지 않음. 회귀테스트(test_scan_round560_fixes.py, 13개 검사) 신설 — [1] 소스 확인(notify "
     "호출 추가, 정확히 1곳, 기존 협력사·운영팀 알림 불변). [2] 스크래치 DB 준비. [3] 되돌리기 — 옛(알림 "
     "없는) 꼬리부를 메모리 문자열로 재구성해 exec()로 오늘자 스키마에 실행, 보험사 알림함이 실제로 "
     "텅 빔을 인과관계로 증명. [4] 실제 라이브 라우트(Flask test_client, POST /api/cases)로 사진없음·"
     "사진있음 두 분기 모두 보험사 알림이 정확히 1건씩 남고 문구도 형제와 일치함을 확인. [5] 그 보험사 "
     "본인 세션으로 실제 GET /api/insurer/notifications 를 불러 종단까지(unread 배지 포함) 확인. "
     "[6] 회귀 방지 — 형제 _create_case는 이번 수정과 무관하게 여전히 정상 발송. 첫 실행 13/13 통과. "
     "app.py 1곳 수정 — BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round561_fixes.py", "스캔 561라운드 회귀 — 보험사 관리자수정(api_insurer_update, "
     "PATCH /api/insurers/<iid>)의 일반 필드 루프(org_type/manager/dept/phone/email/contract_status/"
     "status)가 '본문에 그 키가 있는가'만 보고 실제로 값이 바뀌었는지는 안 봐, 관리자가 담당자 한 칸만 "
     "고쳐 저장해도(화면이 폼 전체를 통째로 재전송) 나머지 칸까지 전부 '바뀐 값'인 양 매번 다시 SET "
     "되고 감사로그도 notes가 비어 '정보 수정'이라는 빈 문구만 남기던 결함. 오케스트레이터가 준 각도 "
     "'admin-vs-portal case UPDATE 필드 정합성'은 사건(cases)에 대칭되는 보험사측 일반수정 라우트가 "
     "없어(보험사는 severity 등 좁은 전용 라우트뿐) 막다른 길이었고, 같은 구도를 보험사 엔티티에 적용해 "
     "직접 조사(하위위임 없음)한 결과 발견 — round544가 자기수정(api_insurer_profile_update)에 이식한 "
     "prev 대조 가드가 형제인 이 관리자수정 경로엔 없었다. round506 자신의 주석이 이미 '완전한 결백 "
     "증명은 아니다 — 필드 루프가 값이 실제로 바뀌었는지와 무관하게 무조건 sets에 넣는 것은 이 함수와 "
     "형제 api_partner_update 양쪽에 공통인, 이번 라운드 범위 밖의 별개 동작'이라고 미리 밝혀 둔 바로 "
     "그 결함이다. api_partner_update는 검증-전 필드루프가 DB 연결·prev 조회보다 먼저 실행되는 구조라 "
     "같은 가드를 이식하려면 연결 수명 재구성이 필요해 위험도가 더 커서, 이번 라운드는 구조 변경 없이 "
     "안전하게 고칠 수 있는 api_insurer_update 하나로 범위를 좁혔다(같은 결함이 api_partner_update에 "
     "남아 있음을 테스트 파일 자체에 기록해 후속 라운드로 넘김). 고침 — 형제(api_insurer_profile_update)"
     "와 같은 `if v == (r[f] or \"\"): continue` 가드를 이식(이미 r을 SELECT * 로 갖고 있어 새 조회 "
     "불필요), status는 changed 블록이 이미 old→new 문구를 남기므로 bare 'status' 중복 기재만 피함. "
     "회귀테스트(test_scan_round561_fixes.py, 20개 검사) 신설 — [1] 소스 확인(새 가드·회귀 방지 6종: "
     "round506 잠금·round136 상태허용목록·round483 이메일검사·round484 연락처검사·수수료율 로그·"
     "api_partner_update 미수정 기록). [2] 되돌리기 — 옛(대조 없는) 루프 핵심 3줄만 메모리 문자열로 "
     "재구성해 exec()로 인과관계 실측(형식검사·조기반환은 무관해 제외). [3] 스크래치 DB 준비. [4] 실제 "
     "라이브 라우트로 전체 재전송(무변경) → unchanged:True·감사로그 0건. [5] manager 한 칸만 변경 → "
     "changed=['manager'] 정확히, 감사로그도 특정 필드 명시. [6] 형제(자기수정)가 계정 정지 전에는 "
     "여전히 unchanged 원칙을 지킴(회귀 방지). [7] 상태변경+일반필드 동시변경 → bare 'status' 중복 "
     "없이 서술형 문구만. 첫 실행 CSRF/계정정지 순서 문제 2건 자체발견 후 정정, 최종 20/20 통과. "
     "app.py 1곳 수정(api_insurer_update) — BUILD_HASH 로테이션 예상(재기동 후 실측 확인). "
     "test_scan_round506_fixes.py의 CUR_FUNC 리터럴 캡처도 새 소스에 맞춰 함께 갱신(round506·136·"
     "169·483·484·421 전부 재실행해 회귀 없음 확인)."),
    ("test_scan_round562_fixes.py", "스캔 562라운드 회귀 — 업체 정보수정(api_partner_update, "
     "PATCH /api/partners/<pid>)의 일반 필드 루프(name/partner_type/ceo/major/category/region/"
     "address/phone/email/website/license/status/doc_status)가 '본문에 그 키가 있는가'만 보고 "
     "실제로 값이 바뀌었는지는 안 봐, 관리자가 칸 하나만 고쳐 저장해도(admin.js savePartner()가 폼 "
     "전체를 통째로 재전송) 나머지 13개 필드까지 전부 '바뀐 값'인 양 매번 다시 SET 되고 감사로그도 "
     "'#{pid}' 뿐인 채로 매번 쌓이던 결함 — round561이 형제(api_insurer_update)에서 이미 고치며 "
     "'이 함수는 검증-전 필드루프가 DB 연결·prev 조회보다 먼저 실행되는 구조라 위험도가 더 크다'고 "
     "다음 라운드로 명시 이월한 바로 그 과제. 함수 전체를 끝까지 직접 읽어 두 구조적 선택지(DB 연결을 "
     "검증 루프 앞으로 끌어올리기 vs 후보값만 모았다가 prev 직후 대조필터링) 중 후자를 골랐다 — "
     "전자는 조기반환 6곳 전부에 rollback/close를 새로 달아야 해 더 침습적이었다. 고침 — 검증 루프는 "
     "그대로 두고 결과를 pending 딕셔너리에 모으기만 하도록 바꾼 뒤, 이미 있는 prev 조회 직후(같은 "
     "BEGIN IMMEDIATE 잠금 안)에서 컬럼 전체(full = SELECT *)를 한 번 더 읽어 pending과 대조, 실제로 "
     "바뀐 값만 sets/vals에 넣는다(prev 자체를 SELECT *로 넓히지 않은 이유: round154/466이 그 SELECT "
     "문을 고정 리터럴로 잠가 둔 회귀테스트가 있어 깨진다). email_source 갱신(round299)은 '본문에 "
     "email 키가 있는가'에서 '실제로 바뀌었는가'로 좁혔다. 감사로그도 형제(round561)처럼 실제로 바뀐 "
     "필드명을 남기도록 보강. 아무 것도 안 바뀌면 새 조기반환(unchanged:True, 200)이 생겨 "
     "api_partner_update의 conn.rollback() 개수가 5(round493)→6이 됐다 — test_scan_round493_fixes.py의 "
     "고정 카운트 assertion도 근거 주석과 함께 6으로 갱신. 이 함수를 건드리는 기존 회귀테스트 9개"
     "(round79·80·101·154·174·240·299·429·466)를 전부 재실행해 회귀 없음 확인(각 파일이 쓰는 고정 "
     "리터럴 블록들을 미리 하나씩 대조해 건드리지 않을 자리만 골라 편집). 회귀테스트"
     "(test_scan_round562_fixes.py, 34개 검사) 신설 — [1] 소스 확인(새 가드·9개 회귀 방지). [2] "
     "되돌리기 — 옛/새 루프 핵심부를 메모리 문자열로 재구성해 exec()로 인과관계 실측(옛 루프는 13개 "
     "전부 SET, 새 루프는 0개). [3] 스크래치 DB 준비. [4] 실제 라이브 라우트로 전체 재전송(무변경) → "
     "unchanged:True·감사로그 0건·email_source도 안 건드림. [5] phone 한 칸만 변경 → 그 필드만 반영, "
     "감사로그도 특정. [6] email 실제 변경 시 email_source는 여전히 '직접입력'으로 갱신(round299 취지 "
     "보존). [7] 상태변경+일반필드 동시변경 → 서술형 상태문구와 바뀐 필드명이 함께 로그에 남음. [8] "
     "무관한 키만 있는 요청은 DB 조회 없이 조기 종료(회귀 없음). 첫 실행 34/34 통과. app.py 1곳 수정"
     "(api_partner_update) — BUILD_HASH 로테이션 예상(재기동 후 실측 확인). "
     "test_scan_round493_fixes.py의 conn.rollback() 카운트 assertion도 5→6으로 함께 갱신(근거 주석 "
     "포함, round466·154·299·174·429·79·80·101·240 전부 재실행해 회귀 없음 확인)."),
    ("test_scan_round563_fixes.py", "스캔 563라운드 회귀 — 협력사 사건상세(api_partner_case_detail, "
     "GET /api/partner/cases/<cid>/detail)의 '입찰 판단' 분기(mine=False)가 판단자료(피해사진 장수·"
     "파손 정도)를 조용히 빠뜨리던 결함. 형제(api_partner_dashboard 의 open_cases)는 damage_photos·"
     "human_severity·ai_severity 를 이미 계산해 내려주고 프런트(bidForm())도 그걸 읽어 '피해 사진 N장 "
     "보기' 버튼과 파손 태그를 그리는데, 이 상세 엔드포인트만 c(=SELECT *)에 이미 있던 human_severity/"
     "ai_severity 를 화이트리스트에서 빠뜨렸고 damage_photos 는 세지도 않았다 — 행을 클릭해 여는 "
     "caseDetail() 의 mine=false 렌더가 '닫기' 버튼뿐이었고, 특히 입찰 버튼 자체가 없는 시공사(조회"
     "전용) 계정에게는 이 경로가 사진·파손정도를 볼 유일한 길인데 거기서도 못 봤다. 사진 열람 라우트"
     "(GET /api/cases/<cid>/photos)는 이미 입찰중 공고에 대해 이 접근을 허용해 뒀고(_is_biddable 분기), "
     "damage_photos/severity 자체도 대시보드를 통해 이미 전 입찰참여 협력사에게 노출돼 있어(경쟁 "
     "입찰가·실견적과는 다른 종류) 새로 여는 정보가 아니다 — 진입점 간 데이터 계약을 맞추는 수정. "
     "고침 — app.py: case_view 에 damage_photos(대시보드와 동일한 kind 화이트리스트 COUNT 쿼리 1개 "
     "추가)·human_severity·ai_severity 3키 추가. templates/partner_portal.html: caseDetail() 의 "
     "mine=false 렌더에 bidForm() 과 동일한 마크업(피해사진/파손정도 태그 + 사진 있으면 '사진 보기' "
     "버튼)을 추가하고, bidForm() 이 이미 겪은 것과 같은 이유로 이 모달도 openModal() 직후 "
     "[data-view] 리스너를 직접 연결(안 하면 목록 클릭위임이 안 닿아 버튼이 조용히 안 눌림). "
     "회귀테스트(test_scan_round563_fixes.py, 22개 검사) 신설 — [1] app.py 소스 확인(새 키 3종 + "
     "형제 대시보드와 동일 화이트리스트인지 대조 + 기존 철칙 3종 회귀 방지). [2] partner_portal.html "
     "소스 확인(caseDetail() mine=false 렌더 + [data-view] 리스너 + bidForm() 과 sev 계산식이 문자 "
     "그대로 같은지 대조). [3] 되돌리기 — 옛 case_view 키 집합엔 판단자료 3종이 아예 없었음을 대조. "
     "[4]-[5] 스크래치 DB + 실제 라이브 라우트로 남의 입찰중 사건 조회 → damage_photos=2(영수증 "
     "1장은 제외)·human_severity='중'·ai_severity='경미' 정확히 반영, 기존 철칙(실견적·상세주소·"
     "담당자 비공개)은 회귀 없음. [6] 대조군 — 사진·판정이 없는 사건은 0/None 으로 정직하게 반영"
     "(과잉조작 아님). 첫 실행 22/22 통과. app.py·templates/partner_portal.html 각 1곳 수정 — "
     "BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round564_fixes.py", "스캔 564라운드 회귀 — 보험사 월 정산 명세서 기본 조회월"
     "(_stmt_period_args)이 자기 자신의 문서(\"?year=&month= 파싱 — 없으면 지난달\")와 실제 동작"
     "(없으면 이번 달)이 정반대였던 결함. 이 헬퍼는 보험사 자기조회 JSON/엑셀(GET /api/insurer/"
     "statement, .../export)·어드민 조회/엑셀(GET /api/insurer-statement, .../export) 4개 호출부가 "
     "공유하는 유일한 파라미터 파서다. 어드민·보험사 포털 화면은 <select> 로 매번 year·month 를 "
     "명시적으로 붙여 보내 평소엔 이 기본값 경로를 안 타지만, 이 GET 엔드포인트는 파라미터 없이도 "
     "호출 가능한 JSON API 이고 기존 회귀테스트 두 개(test_scan_round96_fixes.py:139, "
     "test_scan_round534_fixes.py:207/222)가 이미 파라미터 없이 이 경로를 부른다 — '파라미터 생략'은 "
     "실제 호출 표면이다. 그 상태에서 기본값이 '이번 달'이면, 달이 다 지나기도 전에 아직 안 끝난 "
     "정산 숫자를 '월 정산 명세서'라는 이름으로 내려주고, 정작 방금 마감된 지난달(문서가 원래 의도한 "
     "값)은 명시 파라미터 없이는 볼 수 없었다. 고침 — now.year/now.month 기본값을 이번 달 1일에서 "
     "하루를 뺀 지난달(연도 경계도 함께 넘어간다 — 1월이면 자동으로 작년 12월)로 교체. 단일 공유 지점 "
     "하나만 고쳐 호출부 4곳 전부 동시에 맞다. 명시 ?year=&month= 우선순위·1~12 범위검사 폴백 구조는 "
     "그대로(회귀 없음). 회귀테스트(test_scan_round564_fixes.py, 18개 검사) 신설 — [1] app.py 소스 "
     "확인(옛 폴백 부재·새 계산식 존재·단일 공유 지점 호출 수 대조). [2]-[3] 되돌리기 — 옛 함수를 "
     "별도 문자열로 exec() 해 app 모듈 전역(A.datetime)을 가짜 시계로 재바인딩한 뒤 요청 컨텍스트만으로 "
     "직접 호출 대조(3월 기준·1월 연도경계 기준 둘 다 재현) + 명시 파라미터·범위초과 month 폴백 회귀 "
     "없음 확인. [4]-[5] 스크래치 DB + 실제 라이브 라우트(GET /api/insurer/statement)로 지난달/이번달 "
     "정산 각 1건을 심어 파라미터 없이 호출 → 지난달 건만 담기고 이번달 건은 안 샘, 그 다음 "
     "A._stmt_period_args 를 옛 버전으로 잠깐 갈아끼워 같은 라이브 라우트에서 증상을 실제로 재현한 뒤 "
     "원상복구까지 확인. 첫 실행 18/18 통과. app.py 1곳(공유 헬퍼) 수정 — BUILD_HASH 로테이션 예상"
     "(재기동 후 실측 확인)."),
    ("test_scan_round565_fixes.py", "스캔 565라운드 회귀 — 협력사 사건상세(api_partner_case_detail, "
     "GET /api/partner/cases/<cid>/detail)의 '남의 사건' 열람 게이트가 status 문자열만 보고, 형제(사진 "
     "열람 게이트 _is_biddable, GET /api/cases/<cid>/photos 가 참조)가 함께 보는 '마감 전'은 보지 "
     "않던 결함(round563이 낮은 우선순위로 남겨 둔 항목). _is_biddable() 은 "
     "status='입찰중' AND (deadline IS NULL OR deadline > 지금) 두 조건을 함께 보는데, 상세 게이트는 "
     "status='입찰중' 하나만 봤다 — 마감이 지났지만 정기 스윕(_sweep_if_due)이 아직 상태를 정리하지 "
     "않은 짧은 구간에는, 상세 API 가 그 사건을 여전히 '입찰중'으로 열어 round563이 추가한 "
     "damage_photos/human_severity/ai_severity 와 '사진 보기' 버튼까지 그려 주면서, 정작 그 버튼을 "
     "누르면 사진 라우트는 _is_biddable() 이 False 라 열리지 않는 죽은 버튼이 된다. 고침 — 상세 "
     "게이트를 `c[\"status\"] != \"입찰중\"` 에서 `not _is_biddable(conn, cid)` 로 교체(새 로직 없이 "
     "기존 헬퍼 재사용, 단일 지점). mine=True 분기·round563 필드·다른 상태(예: 시공중) 차단은 이 "
     "게이트를 타지 않거나 그대로라 회귀 없음. 회귀테스트(test_scan_round565_fixes.py, 15개 검사) "
     "신설 — [1] app.py 소스 확인(새 게이트·옛 게이트 부재·_is_biddable 자신의 이중조건 대조·round563 "
     "필드 잔존). [2]-[3] 스크래치 DB + _is_biddable() 자체가 '입찰중이지만 마감 지남' 사건에서 이미 "
     "False 를 내는지 직접 대조(옛 게이트와 갈리는 지점 확인). [4] 되돌리기 — 현재 함수 전체를 문자열로 "
     "재구성해 게이트 한 줄만 옛 버전으로 되돌리고 exec() 한 뒤 A.app.view_functions 에 잠깐 갈아끼워 "
     "같은 실제 URL(GET /api/partner/cases/<cid>/detail)로 증상을 재현(마감 지난 사건을 200/mine:false "
     "로 열어 줌) → 즉시 원상복구. [5] 원상복구한 실제 라이브 라우트로 같은 사건 재조회 → 403. 대조군 "
     "3종(마감 안 지난 입찰중은 여전히 200, 아예 다른 상태는 여전히 403, mine=True 소유주는 마감과 "
     "무관하게 여전히 200) 전부 회귀 없음. 첫 실행 15/15 통과. app.py 1곳(단일 게이트) 수정 — "
     "BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round566_fixes.py", "스캔 566라운드 회귀 — 협력사 안내표시 일괄(api_partner_invite, "
     "POST /api/partners/invite)이 형제(api_partner_bulk_credentials, round494)와 달리 배치 전체를 "
     "잠그지 않던 결함. 관리자 일괄(ids 배열) 라우트 4곳 전수(grep 'body().get(\"ids\")') 중 "
     "이 라우트만 conn = DB.get_db() 뒤 BEGIN IMMEDIATE 없이 반복문을 돌았다 — 안의 '이미 안내함' "
     "가드(if p[\"invited_at\"]:, round250)는 잠금 없는 평범한 SELECT라, 두 요청(연타·admin 탭 2개가 "
     "겹치는 선택으로 동시 제출)이 같은 업체를 커밋 전에 동시에 읽으면 둘 다 가드를 통과해 "
     "notify()(단순 INSERT라 중복 방지 수단 없음)가 그 업체에게 '계정안내' 알림톡을 실제로 두 번 "
     "내보낸다. 내부 관리자 전용 화면이라 외부 공격면은 아니지만, round494가 이미 같은 무게로 다룬 "
     "것과 같은 수준의 실피해(알림톡 비용 중복·업체측 혼란)다. 고침 — 형제(round494)와 정확히 같은 "
     "자리·같은 방식으로 conn.execute(\"BEGIN IMMEDIATE\")를 live 계산 직후·반복문 앞에 추가(호출부에서 "
     "배치 전체를 한 번에 잠금, 안의 SAVEPOINT 중첩·round430은 그대로). 회귀테스트"
     "(test_scan_round566_fixes.py, 24개 검사) 신설 — [0] app.py 소스 확인(BEGIN IMMEDIATE 위치·"
     "round250/430 가드 잔존·형제 대조). [1] 스크래치 DB+관리자 세션 준비. [2] 순차 요청 회귀 없음"
     "(중복 없을 때는 지금까지와 동일). [3]+[4] 동시요청 실경합 재현 — DB.get_db()를 감싸 문제의 "
     "SELECT 직전에서 두 스레드를 전용 threading.Barrier로 강제 동시 도달시킨 뒤(round494의 고정 "
     "time.sleep()은 한쪽이 먼저 깨어나 통째로 커밋을 끝내버려 재현이 안 됨을 실측 확인 — barrier로 "
     "교체), 지금 코드는 marked 합계 1·알림 1건으로 정확히 직렬화됨을, 이 세션이 고치기 직전 Read로 "
     "확인한 원문을 문자열로 재구성한(exec, on-disk 파일은 안 건드림) 옛 코드는 같은 조건에서 marked "
     "합계 2·알림 2건이 실제로 생김을 각각 실측 대조. 첫 실행 24/24 통과(재실행 3회 동일). app.py 1곳"
     "(단일 호출부) 수정 — BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round567_fixes.py", "스캔 567라운드 회귀 — 정산 되돌리기(api_settlement_undo, "
     "POST /api/settlements/<sid>/undo)만 정산 상태를 진짜로 바꾸는 형제 6곳(void·review·paid·"
     "paid-bulk·transfer·insurer_approve) 중 유일하게 void_status=='취소' 를 스스로 다시 보지 "
     "않던 결함. app.py 전수(grep 'UPDATE settlements SET')로 정산을 실제로 바꾸는 라우트 7곳을 "
     "찾아 대조 — 나머지 6곳은 전부 이 가드를 갖고 있고, 그중 review·transfer·insurer_approve는 "
     "round427·465가 '그 보장은 이 함수가 아니라 다른 라우트가 지키는 것이라 새 경로가 하나라도 "
     "추가되면 조용히 뚫릴 수 있다'는 같은 이유로 명시적으로 겹방어를 이식받았다 — undo() 만 "
     "이 원칙이 안 옮겨져 있었다. 지금 이 순간의 실제 위험(과장하지 않는다) — api_settlement_void "
     "는 review_status=='승인'이거나 insurer_paid=='입금완료'인 건은 취소 자체를 막아 두므로 "
     "정상 흐름으로는 '취소됐는데 review_status가 승인으로 남아있는' 조합이 생기지 않아, 오늘은 "
     "undo()를 취소 건에 불러도 그냥 '되돌릴 단계가 없습니다'(409)로 끝나 무해하다 — 이 라운드는 "
     "'다른 함수의 가드에만 기대지 않는다'는 이 서브시스템 자신의 반복된 원칙(427·465)을 마지막 "
     "한 곳까지 완성한다. 고침 — transfer_status=='이체완료' 검사 바로 앞에 형제와 같은 문구"
     "('취소된 정산 건입니다.', 409)로 void_status 가드를 추가(app.py 1곳). 회귀테스트"
     "(test_scan_round567_fixes.py, 18개 검사) 신설 — [0] app.py 소스 확인(가드 위치·형제 5곳 "
     "대조·round228 재시도가드/이체완료가드 잔존). [1] 스크래치 DB·관리자 세션 준비. [2] 지금 "
     "코드: void_status='취소'+review_status='승인' 조합(정상 라우트로는 못 만들어 직접 INSERT로 "
     "가드만 분리 검증)을 되돌리려 하면 409로 막고 행이 전혀 안 바뀜을 확인. [3] 되돌리기 증명 — "
     "이 세션이 고치기 직전 Read로 확인한 원문을 문자열로 재구성(exec, on-disk 파일은 안 건드림)한 "
     "옛 코드는 같은 조합에서 200 성공으로 review_status·transfer_status를 실제로 '대기'로 되돌려 "
     "취소된 건을 검수·이체 파이프라인에 조용히 복귀시킴을 실측 대조. [4] 취소되지 않은 정상 건의 "
     "되돌리기·'되돌릴 단계 없음' 케이스는 회귀 없이 그대로 동작. 첫 실행 18/18 통과. app.py 1곳"
     "(단일 호출부) 수정 — BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round568_fixes.py", "스캔 568라운드 회귀 — manage.py:main()(모든 명령이 실제로 "
     "거치는 유일한 지점)의 COMMANDS[cmd] 호출에 try가 없던 결함. round557/558/559가 이미 닫은 "
     "'예약 실행이 조용히 죽는다' 앵글을 직접 조사(하위위임 없음)해 그 세 라운드가 안 건드린 네 번째 "
     "지점을 찾았다 — round557은 cmd_sweep() 내부만 고쳤을 뿐 main() 자체(당시도 지금도 try 없음)는 "
     "그대로 뒀다. deploy/windows_setup.ps1이 등록하는 예약작업 중 backup을 뺀 prune-logs·"
     "prune-personal도 sweep과 똑같이 pythonw.exe를 표준출력 리다이렉트 없이 부르는데(실측: 284·315·"
     "327행 New-ScheduledTaskAction 전부 $vpyw뿐 '>>' 없음), cmd_prune_logs()는 본문(DELETE 두 건+"
     "commit)에 try 자체가 없고 cmd_prune_personal()은 except sqlite3.Error뿐이라 그 안의 "
     "int(os.environ.get('BOKGUON_TRASH_KEEP_DAYS','30')) 같은 자리가 던지는 ValueError 등은 그대로 "
     "새나간다. 이 세션이 여러 세션 동시편집을 실제로 자주 관찰하는 환경이라 WAL 동시쓰기 경합"
     "(sqlite3.OperationalError) 한 번이면 개인정보 보호법 §21이 요구하는 주간 파기가 콘솔도 없는 "
     "pythonw 아래서 흔적 없이 죽는다 — manage.py check의 job_locks 정체 감지(796·835행)가 최대 "
     "10일 뒤 '멈췄다'만 보여줄 뿐 왜 멈췄는지는 round557이 cmd_sweep에서 이미 짚은 것과 똑같이 "
     "안 보인다. 고침 — 명령마다 따로 감싸는 대신 모든 명령이 통과하는 이 한 지점(main())에 "
     "cmd_sweep이 이미 세운 처방과 같은 모양(app 로거로 전체 트레이스백을 남기고, 짧은 이유는 "
     "화면에도 찍고, 종료코드는 실패로)을 적용(manage.py 1곳) — 앞으로 추가될 명령에도 자동 적용. "
     "회귀테스트(test_scan_round568_fixes.py, 14개 검사) 신설 — [0] 소스 확인(try/except Exception·"
     "A.app.logger.exception·bad()·return 1·이중 임포트 안전망). [1] 스크래치 DB 준비. [2] 되돌리기 "
     "— 옛(try 없는) main() 반환문을 그대로 문자열 재구성해 exec()하고 M.COMMANDS에 예외를 던지는 "
     "가짜 명령을 주입해 예외가 그대로 새는 것을 인과관계로 실측(on-disk manage.py는 조회만 함). "
     "[3] 같은 가짜 명령 상태에서 진짜 M.main()을 sys.argv로 직접 호출 — 예외가 안 새고 종료코드 1을 "
     "반환하고 A.app.logger.exception이 실제로 불리고 화면에도 원인 요약이 찍힘을 확인. [4] 회귀 없음 "
     "— 정상 명령(stats)은 여전히 0을 반환하고 새 안전망이 로거를 건드리지 않으며, 미지 명령·도움말도 "
     "그대로 동작. 첫 실행 14/14 통과(재실행 동일). manage.py 1곳(main()) 수정 — app.py가 import하지 "
     "않는 독립 CLI라 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round569_fixes.py", "스캔 569라운드 회귀 — 어드민 콘솔 자체 모달(직접조사, 하위위임 "
     "없음)의 피해자 조회 링크 발급 모달(trackLink(), static/admin.js)에서 주소칸 클릭시 전체선택을 "
     "구현하던 인라인 onclick=\"this.select()\" 가 이 앱의 전역 CSP(script-src 'self' 'nonce-…', "
     "unsafe-inline/unsafe-hashes 전혀 없음)에 막혀 조용히 죽어 있던 결함. round319가 같은 이유로 "
     "서버 렌더 템플릿 3곳(<button onclick=)을 이미 잡았지만 그 수정은 세 파일만의 일회성 정규식 "
     "테스트였고, admin.js가 JS 안에서 직접 그리는 모달 마크업까지는 어떤 상시검사도 보지 않았다. "
     "매 라운드 도는 상시검사 test_dead_actions.py도 이 결함의 사각지대다 — data-act↔ACT 짝만 보므로 "
     "data-act 자체가 없는 인라인 onclick 은 '미등록'으로도 안 걸린다. 실제 영향은 경미(같은 모달의 "
     "'주소 복사' 버튼은 data-act=\"copyTrack\"으로 정상 동작해 주 기능은 살아 있었다 — 입력칸을 "
     "직접 클릭해 수동 선택하려던 보조 동선만 죽어 있었다). 고침 — ① static/admin.js: 문제의 "
     "<input id=\"tk_url\"> 에서 onclick=\"this.select()\" 를 data-act=\"selectText\" 로 교체하고 "
     "바로 위에 ACT.selectText = (a, el) => el.select(); 를 신규 등록(기존 data-act/ACT 관용구 그대로, "
     "새 메커니즘 없음). ② [true convergence] test_dead_actions.py 에 '인라인 이벤트 핸들러가 없다' "
     "상시검사를 신설 — data-act 존재 여부와 무관하게 admin.js·actions.js·admin.html·"
     "insurer_portal.html·partner_portal.html 전체에서 <tag on*=\"...\"> 패턴을 정규식(단일 지점, "
     "SCREENS 딕셔너리 재사용)으로 잡아, round319가 세 템플릿에서만 일회성으로 잡던 것을 앞으로 "
     "추가되는 인라인 핸들러에도 자동 적용되게 한다. 회귀테스트(test_scan_round569_fixes.py, 20개 "
     "검사) 신설 — [1] admin.js 소스 확인(새 data-act·ACT.selectText 등록과 본문·형제 copyTrack "
     "잔존). [2] admin.js 전체가 신설 정규식을 통과. [3] 되돌리기 — 이 한 줄만 옛 onclick 버전으로 "
     "되돌린 메모리 문자열([파일 미기록])에는 신설 정규식이 실제로 걸리고 현재 버전은 여전히 통과함을 "
     "대조. [4] 되돌리기 — actions.js run()의 위임 계약을 그대로 옮긴 순수 파이썬 시뮬레이션으로, 옛 "
     "마크업(data-act 자체 없음)은 디스패처 후보에도 못 올라 select() 가 절대 안 불리고 새 마크업은 "
     "실제 디스패치돼 select() 가 불림을 대조. [5] 실제 살아있는 앱(/offline, 인증불필요)의 CSP 헤더를 "
     "실측해 script-src 에 unsafe-inline·unsafe-hashes 가 전혀 없음을 확인(round319와 동일 기법). "
     "[6] test_dead_actions.py 를 서브프로세스로 실제 실행해 0(전부 통과)과 신설 검사 출력을 확인 "
     "(Windows cp949 자동판정 UnicodeDecodeError 방지 위해 encoding=\"utf-8\"+PYTHONIOENCODING 명시). "
     "첫 실행 20/20 통과. static/admin.js·test_dead_actions.py 각 1곳 수정 — 정적 자산·테스트 파일만 "
     "변경(app.py/dispatch.py 미변경)이라 BUILD_HASH 로테이션 예상되나 백엔드 로직 재기동 실익은 "
     "낮음(재기동해 실측 확인)."),
    ("test_scan_round570_fixes.py", "스캔 570라운드 회귀 — 연락처 개별수정(api_contact_update, PATCH "
     "/api/contacts/<pid>, 관리자 콘솔 '연락처 관리' 탭)의 일반 필드 루프(phone/email/email2/manager/"
     "contact_note)가 '본문에 그 키가 있는가'만 보고 실제로 값이 바뀌었는지는 안 보던 결함 — 이미 닫힌 "
     "'값 불변인데도 UPDATE+감사로그' 7건(api_admin_update 등)과 같은 클래스의 미발견 인스턴스다. "
     "app.py 전체 'for f in (' 전수 확인 중 9089행 api_insurer_update(라운드561이 이미 고침)·10452/"
     "10497행 api_case_edit(처음부터 대조 있어 클린)과 달리 이 함수만 대조가 없었다. admin.js ctSave()가 "
     "5칸을 통째로 재전송하는 관례(round240)라 메모 한 줄만 고쳐도 나머지 4칸이 매번 '바뀐 값'인 양 "
     "다시 SET 되고 '연락처 수정' 감사로그도 실제 변경 없이 남았다. 더 심각한 부수효과 — email_source "
     "강제갱신 조건이 '\"email\" in d' 였다(형제 api_partner_profile_update 는 라운드544가 이미 "
     "'\"email\" in changed' 로 좁혀 둠). ctSave()가 email 을 매번 동봉하므로 메모·연락처만 고쳐도 "
     "email_source 가 매번 '직접입력'으로 강제로 바뀌어, collect_emails.py 가 자동수집해 email_source="
     "'수집(홈페이지)'로 표시한 뒤 아무도 검증한 적 없는 주소가 조용히 '사람이 확인한 값'으로 둔갑하고, "
     "그 뒤로 clean_collected_emails.py(이 표식만 청소 대상으로 봄)는 그 행을 영원히 정리하지 않는다. "
     "고침 — api_contact_update 단일 지점(이 결함의 유일한 발생 지점) — SELECT 를 phone/email/email2/"
     "manager/contact_note/email_opt_out/sms_opt_out 까지 넓혀 이전값 대조 재료(p)로 쓰고, 형제와 동일한 "
     "'if v == (p.get(f) or \"\"): continue' 를 일반 필드 루프와 email_opt_out/sms_opt_out 불리언 루프 "
     "둘 다에 이식했으며, email_source 조건을 changed 세트 기준('\"email\" in changed')으로 교체했다. "
     "회귀테스트(test_scan_round570_fixes.py, 32개 검사) 신설 — [1] 소스 확인(넓어진 SELECT·changed "
     "세트·대조 후 continue·email_source 조건 교체·불리언 대조·RE_PHONE/RE_EMAIL·contact_updated·감사로그 "
     "액션명 등 기존 방어 잔존). [2] 되돌리기 — 옛(대조 없는) 루프 핵심부만 별도 문자열로 재구성해 "
     "exec()로 인과관계 실측(전부 미변경인데 옛 루프는 필드5+email_source 전부 SET 대상으로 잡히지만 새 "
     "루프는 0개, 특히 contact_note 하나만 바뀌어도 옛 루프는 email 불변인데도 email_source 를 강제로 "
     "넣고 새 루프는 안 넣음을 대조 — 이 라운드의 핵심 인과관계). [3]-[8] 실제 Flask test_client + "
     "스크래치 DB로 관리자 세션을 통해 종단 확인 — 5칸 전체 무변경 재전송시 unchanged:True·로그 0건· "
     "email_source 그대로, 메모만 변경시 그 필드만 로그되고 email_source 는 여전히 '수집(홈페이지)', "
     "email 실제 변경시에만 email_source 가 '직접입력'으로 갱신(라운드299 취지 보존), email_opt_out "
     "재전송(동일값)은 무시되고 실제 토글만 반영·로그, 무관한 키만 있는 요청은 완전 no-op. 첫 실행 "
     "32/32 통과. app.py 1곳만 수정(다른 caller 없음) — 백엔드 로직 변경이라 재기동 필요."),
    ("test_scan_round571_fixes.py", "스캔 571라운드 회귀 — round569가 신설한 '인라인 이벤트 핸들러가 "
     "없다' 상시검사(test_dead_actions.py)가 '재발을 이 검사 하나로 앞으로도 막는다'고 등록설명에 "
     "적었지만 실제 스캔 대상은 SCREENS 딕셔너리(3화면 · 5개 파일)뿐이었던 결함. 이 프로젝트의 "
     "templates/*.html 20개·static/*.js 8개 중 위 5개를 뺀 나머지(templates 15개 + static JS 6개)가 "
     "사각지대였다 — 하필 round319가 **원래** <button onclick= 을 고쳤던 offline.html·"
     "case_history.html·insurer_api_guide.html 세 곳도 포함(그 셋은 test_scan_round319_fixes.py가 "
     "<button onclick= 하나만 별도로 볼 뿐 on*= 전체·다른 태그는 안 본다). app.py:_security_headers는 "
     "@app.after_request라 예외 없이 모든 응답에 같은 CSP(unsafe-inline 전혀 없음)를 붙이므로 위험 "
     "자체는 5화면에 국한되지 않는다. 지금 20+8개 파일 전부 실측하면 위반 0건 — 당장 살아있는 죽은 "
     "버튼은 없고, 이 라운드는 검사 자신의 커버리지 결함(다음 회귀를 정말로 잡는가)이다. 고침 — "
     "test_dead_actions.py 단일 지점(유일한 정의처) — SCREENS 기반 _inline_files 를 "
     "glob.glob('templates/*.html')+glob.glob('static/*.js') 로 교체(data-act↔ACT 대조는 화면 단위 "
     "defines/uses 짝이 구조적으로 필요해 손대지 않음 — 인라인 핸들러 검사만 '파일' 단위로 넓힘). "
     "static/leaflet/ 같은 하위 폴더 벤더 라이브러리는 글롭이 비재귀라 의도대로 빠진다. 회귀테스트"
     "(test_scan_round571_fixes.py, 29개 검사) 신설 — [1] 소스 확인(glob import·새 _inline_files·"
     "SCREENS/data-act 대조 로직 잔존). [2] 되돌리기 — on-disk 소스에서 SCREENS 블록을 그대로 잘라내 "
     "exec()해 얻은 진짜 SCREENS로 옛 파일목록(정확히 5개)과 새 파일목록(28개)을 대조 — login.html· "
     "offline.html·case_history.html·insurer_api_guide.html·form.js 등 23개가 옛 스캔에서 빠져 있었음을 "
     "실측. [3] 인과관계 핵심 — 스크래치 디렉토리에 SCREENS 5개 파일은 깨끗하게, login.html에는 실제 "
     "<button onclick=...> 을 심고 옛/새 스캔 로직을 그대로 돌려 옛 스캔은 0건(완전히 놓침)·새 스캔은 "
     "정확히 그 파일 하나를 잡음을 대조, static/leaflet/(하위 폴더 벤더)은 의도대로 스캔 안 됨도 확인. "
     "[4] 실제 test_dead_actions.py를 서브프로세스로 그대로 실행해 저장소 전체가 지금 0건(종료코드 0)"
     "이고 새로 추가된 11개 파일이 출력에 실제로 찍히며 기존 죽은버튼·메뉴제목 검사도 그대로 도는지 "
     "확인. 첫 실행 29/29 통과. test_dead_actions.py 1곳만 수정(app.py/dispatch.py 미변경) — 정적 "
     "자산·테스트 파일만 바뀌었으므로 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round572_fixes.py", "스캔 572라운드 회귀 — '서버가 낡았다'고 스스로 알리는 배너"
     "(_src_hash/server_is_stale, admin·insurer_portal·partner_portal 상단)가 실제로는 app.py·"
     "db.py 둘만 보고 있어서, app.py 가 import 하는 로컬 모듈 11개(compliance·dispatch·photo_ai·"
     "geo·legal_docs·crypto_util·totp·notify_popbill·addr_search·repair_estimate·envload)가 "
     "바뀌어도 배너가 절대 뜨지 않던 결함. compliance.py 는 무등록 도급 형사벌(건산법 5년 이하)을 "
     "막는 compliance.gate() 의 유일한 소재지라 실질적 위험이 크다. 실측: crypto_util.py·"
     "dispatch.py·addr_search.py 가 이번 세션에 app.py 와 같은 시각대에 함께 수정됐다(mtime 확인) "
     "— 이론이 아니라 매 라운드 실제로 밟히는 사각지대. round571이 인라인 핸들러 검사 자신의 스캔 "
     "범위를 되짚었던 것과 같은 각도를 또 다른 자기점검 장치에 적용한 결과. 이 장치를 다룬 회귀"
     "테스트는 지금까지 하나도 없었다. 고침 — app.py:_src_hash() 단일 지점(유일한 정의처, "
     "server_is_stale() 하나만 호출) — 최상단에 import sys 추가, 하드코딩 2파일 튜플을 sys.modules "
     "순회(__file__ 폴더가 app.py 와 같은 모듈 전부)로 교체. app.py 자신은 sys.modules 조회와 "
     "무관하게 항상 명시적으로 포함해 __main__ 실행이든 모듈 import 든 안전하다. _build_hash() 가 "
     "이미 배운 '손으로 나열한 목록은 반드시 어긋난다'는 원칙을 그대로 따라 새 하드코딩 목록도 "
     "만들지 않았다 — 새 로컬 모듈이 생겨도 import 되는 순간 저절로 잡힌다. 회귀테스트"
     "(test_scan_round572_fixes.py, 31개 검사) 신설 — [1] 소스 확인(import sys·sys.modules 순회· "
     "dirname 일치 필터·정렬·app.py 명시 포함). [2] 스크래치 DB로 실제 app.py 를 안전하게 import 해 "
     "sys.modules 실측 — compliance·dispatch·photo_ai 등 11개 전부와 db 를 합쳐 12개+ 로컬 모듈이 "
     "실제로 잡힘을 확인. [3] 되돌리기 — 옛(2파일) 버전을 인메모리 문자열로 재구성(exec, "
     "라운드562·570·571과 같은 기법)해 같은 실제 프로세스에서 compliance 모듈을 sys.modules 에서 "
     "잠깐 뺐다 복원 — 옛 방식은 값이 완전히 그대로(놓침)인데 새 방식은 값이 바뀜(잡음)을 대조, "
     "서드파티(flask)를 빼도 새 값이 그대로임을 대조군으로 확인(과잉 포함 아님). [4] 스크래치 "
     "디렉토리의 가짜 로컬 모듈 내용을 실제로 고쳐 옛 방식은 해시 불변·새 방식은 해시 변경을 "
     "재확인, app.py 자신이 바뀌는 경우는 옛/새 둘 다 여전히 잡음도 회귀 방지로 확인. 첫 실행 "
     "31/31 통과. app.py 1곳만 수정(다른 caller 없음) — 백엔드 로직 변경이라 재기동 필요."),
    ("test_scan_round574_fixes.py", "스캔 574라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE "
     "트랜잭션 commit/rollback 누락 점검 CLI)의 TARGET_FILES 가 여전히 'app.py 가 import 하는가' "
     "기준으로 뽑힌 3개(app.py·dispatch.py·manage.py)뿐이라, 그 기준 밖의 독립 CLI seed_boq.py가 "
     "BEGIN IMMEDIATE 로 쓰기 잠금을 잡는데도(load(), 200행) 이 점검을 완전히 벗어나 있던 결함. "
     "round124('app.py 만 하드코딩해서 봤다' → dispatch.py·manage.py 추가)와 정확히 같은 각도를 "
     "재적용 — 저장소 전체를 'BEGIN IMMEDIATE' 로 grep 하면 실제로 이 문장을 쓰는 프로덕션 파일은 "
     "app.py·dispatch.py·manage.py·seed_boq.py 정확히 4개뿐(db.py 는 주석 2곳뿐이라 round124 가 "
     "이미 정확히 제외, test_*.py 는 단명 프로세스라 이 도구의 존재 이유와 무관해 원래 범위 밖). "
     "seed_boq.py 는 manage.py 와 같은 성격의 CLI(운영자가 손으로 돌려 실제 운영 DB에 표준단가표를 "
     "적재 — round180/268/297/312 가 이미 '실측상 가장 자주 쓰이는 실제 적재 경로'라고 기록해 둔 "
     "도구)라 재기동 없이도 실제로 프로덕션 DB 락을 잡는다. load() 는 지금은 유일한 return 이 "
     "try/finally(conn.close()) 밖의 함수 끝 한 곳뿐이라 이번 확장으로도 위반 0건(클린)이지만 — "
     "round124·571 과 같은 '점검 도구 자신의 사각지대' 유형으로, 코드가 우연히 안전했을 뿐 검사는 "
     "이 함수를 보고 있지 않았다. 고침 — check_tx_paths.py:TARGET_FILES 단일 지점(유일한 정의처)에 "
     "'seed_boq.py' 추가. 회귀테스트(test_scan_round574_fixes.py, 13개 검사) 신설 — [1] 소스 확인. "
     "[2] 되돌리기 — TARGET_FILES 를 옛(3파일) 값으로 monkeypatch 해 seed_boq.py:load() 가 실제로 "
     "검사대상에서 빠짐을 실측(같은 프로세스의 실제 check_tx_paths.main() 호출, on-disk 파일은 안 "
     "건드림). [3] 지금(4파일) 값으로는 다시 잡히고 검사대상 함수 수가 정확히 1개 늘며 위반은 "
     "여전히 0건임을 확인. [4] 이빨이 있는가 — BEGIN IMMEDIATE 뒤 커밋/롤백/finally 없이 바로 "
     "return 하는 합성 파일을 스크래치 디렉터리에 심고 CTP.HERE 를 잠깐 그쪽으로 돌려 실제로 위반"
     "1건을 잡아내는지, 형제 정상 파일(try/finally)은 과잉탐지 없이 통과하는지 확인. [5] 실제 "
     "check_tx_paths.py 를 서브프로세스(encoding='utf-8' 명시 — round518/519 류 cp949 콘솔 함정 "
     "회피)로 그대로 실행해 저장소 전체가 109개 함수·위반 0건으로 끝남을 재확인. 첫 실행 13/13 "
     "통과. check_tx_paths.py 는 app.py 가 import 하지 않는 독립 CLI 진단도구라 서버 재기동 "
     "불필요·BUILD_HASH 불변."),
    ("test_scan_round577_fixes.py", "스캔 577라운드 회귀 — static/sw.js 의 PRECACHE 배열이 "
     "style.css·fonts.css·actions.js·form.js 를 물음표 없는 맨 경로로 넣어 둬, install 이 미리 "
     "데워 두는 캐시가 실제 페이지 요청과 영영 어긋나던 결함. round572·239 가 이미 다룬 같은 "
     "파일을 '스스로 하는 약속(파일 상단 주석 5행 — 정적 자산은 캐시 우선으로 빠르게 연다)을 "
     "실제 코드가 지키는가'라는 세 번째 각도로 재검사해 발견. app.py:asset()(모든 템플릿이 "
     "CSS/JS 를 링크할 때 쓰는 유일한 헬퍼)는 이 4개 파일을 항상 '/static/파일명?v=<해시>' "
     "형태로만 내보내는데, Cache API 의 match/addAll 은 기본적으로(ignoreSearch 미사용, 이 "
     "저장소 grep 0건) 쿼리스트링까지 정확히 같아야 같은 키로 본다 — install 이 넣는 키(물음표 "
     "없음)와 실제 요청 키(물음표+해시)가 달라 이 4개 항목은 정의상 한 번도 못 맞아떨어진다. "
     "icon-192.png(manifest.webmanifest 가 물음표 없이 참조)·/offline(내비게이션도 물음표 없음) "
     "은 원래도 문제 없었다. 고침 — static/sw.js 의 PRECACHE 4개를 자리표시자로, app.py:"
     "service_worker() 단일 지점(이 파일을 내려보내는 유일한 라우트, __APP_VERSION__/__BUILD__ "
     "를 이미 같은 방식으로 채우던 자리)에서 asset() 실제 값으로 채운다 — 새 헬퍼·새 상수 없이 "
     "이미 있던 단일 소스 재사용. 회귀테스트(test_scan_round577_fixes.py, 29개 검사) 신설 — "
     "[1] 소스 확인(자리표시자 4개·옛 리터럴 소멸·round239 waitUntil 두 곳 회귀 없음). [2] "
     "스크래치 DB로 실제 app.py 를 test_client 로 띄워 진짜 /sw.js 응답을 받아 자리표시자가 "
     "실제 asset() 값(파일 바이트 sha256 앞10자리와도 독립 대조)으로 채워졌는지 실측. [3] "
     "되돌리기 — PRECACHE 블록만 옛(맨 경로) 버전으로 바꿔치기한 것과 지금 버전을, Node 로 "
     "구현한 실제 Cache API 의미론(쿼리스트링 정확매치, 상대경로는 워커 origin 기준 절대경로로 "
     "정규화)에 나란히 태워 대조 — 옛 버전은 install 후에도 실제 페이지 요청에서 라이브 fetch 가 "
     "다시 발생(캐시미스)함을, 지금 버전은 발생하지 않음(캐시히트)을 실측, 물음표 없는 "
     "icon-192.png 는 옛/새 둘 다 정상 히트함(회귀 없음)도 확인. 첫 실행 29/29 통과. static/"
     "sw.js·app.py 둘 다 서버가 서빙·실행하는 파일이라 재기동 필요."),
    ("test_scan_round578_fixes.py", "스캔 578라운드 회귀 — partner_accounts.py:_csv_safe() 가 "
     "'app.py 의 동명 헬퍼와 같은 규칙'이라는 자기 docstring 약속과 달리 탭(\\t)으로 시작하는 "
     "값의 수식주입을 못 막던 결함. round577(파일이 스스로 하는 약속을 코드가 지키는가)을 "
     "'여러 파일에 걸친 약속'으로 변형해 재검사해 발견 — app.py 는 이미 round423 에서 "
     "_csv_safe·_xl_safe 두 형제 모두 트리거 판정에 탭을 추가했는데(제어문자 필터는 탭을 "
     "보존하면서도 트리거 집합 v[:1] in ('=','+','-','@') 는 그 탭을 안 봤던 결함), 그 수정이 "
     "app.py 안의 두 곳에만 적용되고 이 저장소에 실측 정확히 3곳뿐인 같은 판정식 중 세 번째 "
     "(partner_accounts.py, 자기 docstring 이 app.py 와 동일 규칙이라고 명시)는 빠졌다. "
     "협력사 CSV 내보내기(--out)의 업체명·지역·공종은 이 파일 자신이 이미 '업체가 스스로 "
     "입력한 자유 텍스트'라 부르는 값이라 같은 우회가 열려 있었다. 고침 — 트리거 집합에 '\\t' "
     "추가(새 헬퍼 없이 app.py 와 동일 규칙 적용), 이 파일 자신의 --self-check(demo())에도 "
     "round418 이 세운 관례(고친 함수는 자체점검에도 반영)대로 assert 3개 추가. 회귀테스트"
     "(test_scan_round578_fixes.py, 18개 검사) 신설 — [1] 소스 확인(형제 전수 3곳 중 "
     "partner_accounts.py 만 갱신되고 app.py 2곳은 회귀 없이 그대로임을 카운트로 확인). "
     "[2] 실제 모듈 import 로 _csv_safe() 호출 + CLI `--self-check` 서브프로세스까지 실행. "
     "[3] 되돌리기 — 옛 트리거 집합(탭 없음)을 문자열 치환+exec 로 재구성(on-disk 파일은 "
     "안 건드림)해 옛 버전이 실제로 탭우회를 막지 못했음을 대조 확인. 첫 실행 18/18 통과. "
     "partner_accounts.py 는 app.py 가 import 하지 않는 독립 CLI 도구(운영자가 협력사 계정을 "
     "일괄 발급할 때만 수동 실행)라 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round580_fixes.py", "스캔 580라운드 회귀 — 현장 출동 보고서(dispatch_report, "
     "GET /report/dispatch/<cid>)의 사진 정렬이 죽은 컬럼(photos.sort_order)에 기대고 있어 "
     "뒤늦게 추가된 '착공전' 사진이 '완료' 사진보다 뒤에 실리던 결함. 조사 각도 — '읽는 자리 "
     "vs 쓰는 자리'(자식표 플래그를 아무도 안 채우면 그 필터/정렬은 죽어 있다)를 정렬 컬럼에 "
     "적용 — db.py의 photos.sort_order(INTEGER DEFAULT 0)를 이 파일 두 곳(api_case_photos·"
     "dispatch_report)의 SQL이 ORDER BY sort_order, id 로 읽는데, 이 저장소 전체(app.py·모든 "
     "모듈·기존 회귀테스트 전부)에 이 컬럼에 값을 쓰는 코드는 단 한 곳도 없다(전수 grep 확인) "
     "— 항상 기본값 0으로 묶여 그 ORDER BY는 사실상 id순(업로드순)과 같다. 정상 흐름에서는 "
     "업로드 순서가 곧 공정 순서(착공전→시공중→완료)라 우연히 맞아떨어지지만, "
     "_upload_damage_photos()(가견적 근거 사진, 항상 kind='착공전')는 보험사·운영자 양쪽에서 "
     "사건 상태와 무관하게 아무 때나 호출된다(호출부 둘 다 사건 존재만 확인, status는 안 봄) "
     "— 이미 '완료' 사진까지 올라온 사건에 뒤늦게 피해사진을 추가하면 그 착공전 사진이 가장 "
     "큰 id로 들어와 raw id순에서는 맨 뒤로 밀린다. 형제 대조 — api_case_photos()(관리자 "
     "사진검수 화면 API)는 이미 이 문제를 비켜가고 있었다(SQL은 똑같이 죽은 sort_order를 "
     "읽지만 그 뒤 Python에서 PHOTO.CONSTRUCTION_KINDS 순서로 재정렬해 반환) — "
     "dispatch_report()만 그 재정렬 없이 raw SQL 순서를 템플릿에 그대로 넘기고 있었다. 고침 "
     "— api_case_photos() 바로 앞에 그 재정렬 로직을 _sort_construction_phase()로 이름 붙여 "
     "뽑고, api_case_photos()는 그 함수를 호출하도록 바꾸고(동작 동일), dispatch_report()도 "
     "SQL 조회 직후 같은 함수를 호출하게 했다 — 새 컬럼·새 판정 없이 이미 검증된 규칙 하나를 "
     "공유. 회귀테스트(test_scan_round580_fixes.py, 20개 검사) 신설 — [1] 소스 확인(헬퍼가 "
     "정확히 한 곳에 정의되고 두 호출부가 실제로 그것을 쓰며, sort_order에 값을 대입하는 "
     "코드가 여전히 없음을 재확인). [2] 단위 실행 — _sort_construction_phase() 자체를 id·kind "
     "가 뒤섞인 입력으로 직접 호출. [3] 종단 실행 — 스크래치 DB에 시공중→완료→착공전 순으로 "
     "사진을 넣어(실제 버그 시나리오) 실제 Flask 테스트클라이언트로 GET /report/dispatch/<cid> "
     "를 호출, 응답 HTML의 이미지 순서가 착공전→시공중→완료로 나옴을 실측(형제 API "
     "api_case_photos의 construction 배열도 회귀 없이 동일 순서 유지 확인). [4] 되돌리기 — "
     "on-disk 파일은 건드리지 않고 dispatch_report 안에 실제로 있는 SQL 문자열을 그대로 다시 "
     "실행해 '고치기 전이었다면' 착공전이 실제로 맨 뒤였음을 대조 확인(같은 raw 결과에 헬퍼를 "
     "통과시키면 착공전이 맨 앞으로 옴도 확인) — 첫 실행 20/20 통과. app.py 자신의 함수 변경 "
     "(신설 1개+수정 2곳)이라 재기동 필요, static/templates 미변경."),
    ("test_scan_round581_fixes.py", "스캔 581라운드 회귀 — manage.py cmd_check()의 '외부 "
     "공개 주소' 자가점검이 `if _pub: ... elif _pub: ...` 로 두 조건이 글자 그대로 같아, "
     "logs/public_host.txt 가 없거나(신규 배포 전) 전부 주석·빈 줄뿐이면 이 절 전체가 "
     "ok·warn·bad 무엇도 안 찍고 조용히 사라지던 결함. 조사 각도 — pyflakes 정적분석을 "
     "핵심 모듈 전체에 걸어 사람이 읽어서는 안 보이는 조용한 모순을 찾음 — app.py 8건은 "
     "전부 무해로 판명(소스만으로 판단 가능해 회귀 불필요), geo.py 의 dictionary-key 경보 "
     "15건은 이미 [라운드293]이 스스로 실측·설명해 둔 사안이라 재조사 제외. manage.py:585 "
     "'_allow 미사용' 을 따라가다 바로 아래 `elif _pub:` 를 발견 — 바로 위 `if _pub:` 와 "
     "조건이 문자 그대로 같아 elif 가 _pub 값과 무관하게 영원히 못 걸리는 항등식이었다. 이 "
     "절은 주석이 스스로 밝히는 2026-08-06 실제 운영 사고(재시작 후 허용 Host 목록이 옛 "
     "값으로 남아 외부 요청이 전부 400 — 로컬 점검은 통과해 몇 시간 동안 몰랐다) 재발 "
     "방지용인데, logs/public_host.txt 가 없는 상태(신규 클론 등)에서는 정확히 이 검사가 "
     "있는지조차 출력으로 알 수 없었다. 형제 대조 — 같은 함수 안 '확인 불가' 유형은 전부 "
     "이유를 대며 warn()+warns 증가를 쓰는데 이 절만 그 관례를 안 따름. 고침 — `elif _pub:` "
     "를 `else:` 로, 죽어 있던(애초에 `_pub[0]` 로 IndexError 였을) ok() 한 줄을 형제와 같은 "
     "형식의 warn()+warns 증가로 교체 — `if _pub:` 안의 기존 분기는 전혀 안 건드림. "
     "회귀테스트(test_scan_round581_fixes.py, 10개 검사) 신설 — [1] 소스 확인(실제 코드 "
     "줄 기준으로 옛 elif 소멸 확인 — 이 라운드 자신의 설명 주석이 옛 패턴을 산문으로 "
     "인용하므로 round580 이 겪은 자기참조 오탐 함정을 피해 주석 아닌 줄만 셈). [2] "
     "되돌리기 — manage.py 실제 소스 문자열에서 이 절만 오려내(on-disk 파일은 안 건드림) "
     "지금 버전과 고치기 전 그대로 재구성한 버전을 각각 exec() 해 같은 입력(_pub 없음·"
     "주석뿐)에서 옛 버전은 침묵(ok/warn/bad 0회·warns 그대로)하고 지금 버전은 warn() 정확히"
     "1회·warns+1 을 실측 대조. [3] 회귀 없음 — _pub 가 있는 경우 아무도 안 듣는 포트로 "
     "강제 연결거부를 유도해 기존 '서버 미기동' 분기가 그대로 나옴을 실행으로 확인. 첫 실행 "
     "10/10 통과. manage.py 는 app.py 가 import 하지 않는 독립 CLI 도구(운영자가 배포 전 "
     "`python manage.py check` 로 수동 실행)라 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round582_fixes.py", "스캔 582라운드 회귀 — static/addrpick.js 의 attach() "
     "가 호출될 때마다 문서 전체 클릭 리스너('바깥을 클릭하면 이 위젯의 드롭다운을 닫는다')"
     "를 새로 하나씩 등록하던 결함. 조사 각도 — round202 의 자기 주석(\"폼을 다시 열 때마다 "
     "wrap.innerHTML 을 통째로 갈아엎어 매번 새 DOM 노드를 만든다\")을 그대로 따라가 같은 "
     "attach() 함수의 **다른 절반**을 봄 — round202 는 PICKED 캐시(데이터)가 새지 않게 "
     "고쳤지만, 그 직후에 있는 리스너 등록문은 그대로 attach() 안에 남아 있었다. attach() "
     "는 admin.js(977·1819행)·insurer_portal.html(691행)·partner_portal.html(2520행)·"
     "apply_partner.html(97행) 5곳에서 부르는데, 그중 사건 등록·발주처 신규접수 모달은 "
     "SPA 라우팅으로 하루에도 수십 번 다시 열리는 화면(round202 자신의 관찰)이라 열 때마다 "
     "익명함수 리스너가 문서에 하나씩 쌓인다 — 참조를 어디에도 안 남겨 removeEventListener "
     "로 지울 방법이 없고, 그 클로저가 당시의 wrap(입력칸·버튼·드롭다운까지 포함한 서브트리 "
     "전체)을 영원히 GC 되지 못하게 붙잡는다. 즉각적인 오작동은 없지만(각 리스너는 자기 wrap "
     "만 보므로 잘못 닫는 일은 없다) 운영자가 콘솔을 오래 켜 둘수록 죽은 리스너·DOM 서브트리가 "
     "무한정 누적되는 메모리 누수. 고침 — 단일 공유 지점으로 옮긴다: 그 등록을 attach() 안에서 "
     "빼내 모듈이 로드될 때(파일당 한 번) 최상위에서 딱 한 번만 등록하고, 그 안에서는 그 순간 "
     "실제로 문서에 남아 있는 .apwrap 전부를 document.querySelectorAll 로 다시 찾는 델리게이션 "
     "으로 바꿨다 — 지워진 옛 wrap 은 그 질의에 애초에 안 잡히므로 attach() 를 몇 번을 불러도 "
     "리스너는 항상 1개다. 회귀테스트(test_scan_round582_fixes.py, 14개 검사) 신설 — [1] 소스 "
     "확인(등록문이 파일 전체에 정확히 1번뿐이고 attach() 본문 밖에 있음 — 새 설명 주석 자체가 "
     "코드를 그대로 인용하면 이 카운트에 자기참조 오탐을 낼 수 있어 산문에서 리터럴 인용을 "
     "피함, 실제로 1차 작성 때 2로 잡혀 고침). [2] 실행(Node.js, round202 가 만든 addrpick.js "
     "전용 최소 DOM 스텁을 document.querySelectorAll·리스너 카운터로 확장) — attach() 를 "
     "매번 새 입력칸으로 3번(=폼 3번 재열기) 불러도 문서 클릭 리스너가 1개로 유지됨을 확인하고, "
     "델리게이션으로 바뀐 뒤에도 안쪽 클릭은 유지·바깥 클릭은 닫힘이라는 기존 계약이 그대로 "
     "동작함을 같은 실행에서 확인. [3] 되돌리기 — 고치기 전 코드를 문자열로만 재구성해(on-disk "
     "파일은 안 건드림) 같은 시나리오를 다시 실행 — 실제로 리스너가 3개까지 쌓임을 실측해 "
     "3→1 이 이 수정의 인과효과임을 대조. 첫 실행 14/14 통과. static 파일만 바꿨으므로 "
     "build_pages.py 로 docs/ 재빌드 필요, 서버 재기동은 static 서빙 갱신을 위해 필요."),
    ("test_scan_round583_fixes.py", "스캔 583라운드 회귀 — manage.py cmd_check()의 '3-2) "
     "외부 공개 주소' 절을 감싼 바깥 `except Exception: pass` 가, 안쪽 `except OSError:`(서버 "
     "미기동만 의도적으로 잡음)를 지나친 다른 예외 — 전형적으로 BOKGUON_PORT 가 숫자가 아닐 "
     "때 int(_port) 의 ValueError — 를 조용히 삼켜 ok·warn·bad 무엇도 안 찍히던 결함. 조사 "
     "각도 — [라운드581]이 바로 이 절의 `elif _pub:` 항등식을 고치며 남긴 원칙('이유 없는 "
     "건너뜀은 통과처럼 읽힌다')을 한 겹 더 따라가 '이 파일이 스스로 하는 약속을 끝까지 "
     "지키는가'로 봄 — 그 원칙을 지키도록 갓 고친 절 자신이, 그 절을 감싼 바깥 except 때문에 "
     "여전히 같은 실패 모드(침묵)를 낼 수 있었다. 실행으로 재현(BOKGUON_PORT=\"abc\") — "
     "고치기 전 코드는 ok/warn/bad 호출 0회. 892행 `if fails:` 최종판정은 fails/warns 개수만 "
     "보므로 이 절이 통째로 안 돌아도 '배포 가능' 출력엔 흔적이 없다 — 2026-08-06 사고(허용 "
     "Host 어긋남을 몇 시간 동안 못 봄) 재발 방지용 검사 자체가 무력화된다. 형제 대조 — 같은 "
     "함수 안 다른 모든 '확인 불가' 지점(263·361·384·492·889행)은 전부 `except Exception as "
     "e: warn(f'...{e}'); warns += 1` 로 이유를 알리는데 이 절의 바깥 except 만 `pass`. 고침 "
     "— 그 한 곳을 형제(492행 공종 커버리지 점검)와 같은 형식의 warn()+warns 증가로 교체 — "
     "`if _pub:`/`else:` 안의 기존 세 분기(400차단·정상응답·서버미기동·hostfile없음)는 전혀 "
     "안 건드림. 회귀테스트(test_scan_round583_fixes.py, 14개 검사) 신설 — [1] 소스 확인. "
     "[2] 실행 — manage.py 실제 소스에서 마커 기준으로 3-2 절만 그대로 오려내(on-disk 파일은 "
     "안 건드림) exec() 해 (a) BOKGUON_PORT 오염 → warn() 1회·warns+1, (b) hostfile 없음 → "
     "[라운드581] 분기 회귀 없음, (c) 정상 포트·연결거부 → 기존 ok() 분기 회귀 없음을 각각 "
     "실측. [3] 되돌리기-증명 — 바깥 except 한 곳만 고치기 전으로 재구성(나머지는 지금 절과 "
     "완전히 동일함을 문자열 대조로 확인해 과잉수정 방지)해 같은 (a) 시나리오를 실행 — 실제로 "
     "호출 0회임을 실측해 0→1 이 이 수정의 인과효과임을 대조. 첫 실행 14/14 통과. manage.py 는 "
     "app.py 가 import 하지 않는 독립 CLI 도구(운영자가 배포 전 수동 실행)라 서버 재기동 "
     "불필요·BUILD_HASH 불변."),
    ("test_scan_round584_fixes.py", "스캔 584라운드 회귀 — manage.py cmd_check() 의 "
     "'법정 고지 자리표시자' 점검 절(786~800행)을 감싼 바깥 `except Exception: pass` 가, "
     "company_info.json 이 있는데 못 읽는 경우(깨진 JSON·최상위가 dict 아님 등)를 조용히 "
     "삼켜 ok·warn·bad 무엇도 안 찍히던 결함. 조사 각도 — [라운드583]이 cmd_check() 의 "
     "'3-2) 외부 공개 주소' 절에서 고친 바로 그 결함 유형('이 파일이 스스로 하는 약속을 "
     "실제로 끝까지 지키는가')이 **같은 함수의 다른 형제 절에도 다 퍼졌는지** 전수 확인 — "
     "cmd_check() 안에 남은 `except Exception: pass` 를 모두 뒤져보니 583이 고친 절의 "
     "바로 다음다음 절(자리표시자 점검)이 여전히 이 패턴이었다. 실제 영향 — 이 절은 값은 "
     "채워졌지만 DEPLOY.md 예시 블록을 그대로 붙여넣은 자리표시자('○○클라우드'·'예시'·"
     "'TBD' 등)가 남아 전자상거래법 표시의무를 위반하는 상태를 잡는 최후 방어선인데(같은 "
     "파일의 legal_docs.PENDING 은 값이 비어 있을 때만 잡으므로 서로 안 겹치는 독자 방어), "
     "파일이 있는데 못 읽으면 JSONDecodeError/AttributeError 가 안쪽에 잡는 코드 없이 "
     "그대로 바깥 except 로 올라가 조용히 사라져 이 점검이 돌았는지조차 알 수 없는 채로 "
     "'배포 가능' 판정에 도달했다. 형제 대조 — 같은 파일 legal_docs.py 의 _load_info() 는 "
     "[라운드121]에서 이미 같은 이유로 고쳐져 실패 시 _log.warning() 을 남기고, manage.py "
     "자신도 [라운드583]이 3-2 절에서 `except Exception as e: warn(...); warns += 1` 로 "
     "통일했는데 이 절만 그 관례 확산 이전 형태(pass)로 남아 있었다. 고침 — 799행 부근 "
     "`except Exception: pass` 를 3-2 절과 같은 형식의 `except Exception as e: "
     "warn(f'법정 고지 자리표시자 점검을 하지 못했습니다 — {type(e).__name__}: {e}'); "
     "warns += 1` 로 교체 — try 블록 안 기존 세 갈래(파일없음 침묵·자리표시자없음 침묵·"
     "자리표시자있음 bad+fails)는 한 글자도 안 건드림. 회귀테스트(test_scan_round584_"
     "fixes.py, 17개 검사) 신설 — [1] 소스 확인. [2] 실행 — manage.py 실제 소스에서 이 "
     "절만 그대로 오려내(on-disk 파일은 안 건드림) exec() 해 (a) 깨진 JSON → warn() 1회·"
     "warns+1, (b) 최상위가 dict 아님(AttributeError) → 같은 except 가 warn() 1회(단일 "
     "예외타입 과적합 아님 확인), (c) 파일 없음/(d) 정상값/(e) 자리표시자 있음 → 기존 세 "
     "갈래 회귀 없음을 각각 실측. [3] 되돌리기-증명 — 바깥 except 한 곳만 고치기 전으로 "
     "재구성(나머지는 지금 절과 완전히 동일함을 문자열 대조로 확인해 과잉수정 방지)해 같은 "
     "(a) 시나리오를 실행 — 실제로 호출 0회임을 실측해 0→1 이 이 수정의 인과효과임을 대조. "
     "첫 실행 17/17 통과. manage.py 는 app.py 가 import 하지 않는 독립 CLI 도구(운영자가 "
     "배포 전 수동 실행)라 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round585_fixes.py", "스캔 585라운드 회귀 — db.py init_db()/seed() 의 "
     "두 비가역 안전게이트(증거조회 3종·_base 스냅샷)가 조회 자체의 실패를 "
     "'증거없음(0)'으로 취급해 정확히 거꾸로 동작하던 결함. 조사 각도 — [라운드584] "
     "전수확인 목록의 db.py·collect_emails.py·crypto_util.py·build_pages.py·"
     "check_tx_paths.py 를 다 열어봤다 — stdout 인코딩 폴백 5곳은 [라운드519] 동일 "
     "관례라 클린, CREATE INDEX·_backfill_sku_keys 행별 스킵은 [라운드277]·[라운드321]이 "
     "'멱등 백필이라 다음 실행이 마저 채운다'로 이미 정당화한 패턴과 같은 모양이라 "
     "그대로 둠. 그런데 init_db() 의 '이 DB 가 이미 쓰이는가' 증거조회(사건·협력사·"
     "go_live_at)와 seed() 의 '시드 전 최대 id' 스냅샷은 멱등 백필이 아니라 한 번 "
     "잘못되면 되돌릴 수 없는(비가역) 게이트다 — 조회 실패를 옛 코드는 둘 다 '증거 "
     "없음'(_n=0 / _base[_t]=0)으로 취급해, admins=0(주석이 스스로 밝히는 go-live "
     "직후 정상 상태)일 때 세 증거조회가 전부 'database is locked' 등으로 실패하면 "
     "(같은 파일 1399행이 '워커 여럿 동시 부팅'을 이미 실측 근거로 듦) 실사건·"
     "실협력사가 있어도 _used=0 그대로 남아 seed() 가 돌 수 있었고, seed() 자신도 "
     "_base 스냅샷 실패 시 0 폴백 때문에 표시 루프가 'UPDATE {t} SET is_demo=1 WHERE "
     "id > 0' 을 그 표의 기존 행까지 포함해 쏠 수 있었다 — 둘 다 각 함수 자신의 "
     "주석이 명시적으로 막으려는 사고. 고침 — (A) 증거조회 except 를 '증거 있음'과 "
     "동일하게(_used=1, 즉시 break) 처리해 판정 불가를 시드 차단 쪽으로 넘김. (B) "
     "_base[_t] 를 0 대신 None 으로 남기고 표시 루프가 None 인 표를 통째로 건너뜀 "
     "(표시 루프 자신의 except pass 는 이미 안전한 방향이라 손대지 않음). 회귀테스트"
     "(test_scan_round585_fixes.py, 24개 검사) 신설 — [1] 소스 확인. [2] 실행 — 현재 "
     "db.py 에서 세 절(증거조회 루프·_base 스냅샷·표시 루프)만 오려내(on-disk 파일은 "
     "안 건드림) 가짜 conn 으로 exec() 해 정상/단일실패/전체실패 시나리오 실측(정상 "
     "경로 2종 회귀 없음 확인 포함). [3][4] 되돌리기-증명 — 각 절 except 블록만 고치기 "
     "전으로 재구성(앞뒤 문자열 완전동일 대조로 과잉수정 방지)해 같은 실패 시나리오를 "
     "돌리면: 옛 A 절은 세 조회가 전부 실패해도 _used=0 로 남고, 옛 B+C 절 조합은 "
     "조회 실패했던 표에 실제로 'UPDATE cases ... WHERE id > 0' 을 쏜다 — 지금 버전은 "
     "이 호출 자체가 사라짐(있음→없음 이 인과효과). 첫 실행 24/24 통과. db.py 는 "
     "app.py 가 모듈 최상단에서 무조건 import 하므로 서버 재기동 필요."),
    ("test_scan_round588_fixes.py", "스캔 588라운드 회귀 — check_rate_limit()(레이트리밋 "
     "카운터, @app.before_request 로 모든 요청마다 실행)의 '버킷 길이확인 → append'가 "
     "락 없이 두 문장으로 쪼개져, waitress 스레드풀이 같은 IP·경로 동시요청을 처리하면 "
     "여러 스레드가 서로의 append 전에 나란히 상한확인을 통과해 실제 허용 건수가 limit 을 "
     "넘어서던 결함. 조사 각도 — 오케스트레이터가 준 '동시성 실측 재현' 각도로 app.py "
     "전역 인메모리 공유상태를 훑어 _rate_buckets(defaultdict(deque))를 찾았다 — app.py "
     "전체에 threading.Lock 이 단 한 곳도 없었고(기존 동시성 방어는 전부 BEGIN IMMEDIATE "
     "류 DB 트랜잭션), 39·414·450라운드 등 기존 테스트는 이 이름을 clear() 로 다른 "
     "테스트를 격리하는 용도로만 썼을 뿐 check_rate_limit() 자신의 스레드 안전성은 실측한 "
     "적이 없었다. 영향(과장하지 않음) — 이 계층 자신의 주석이 '2차 방어선, 1차는 nginx, "
     "실제 무차별대입 저지선은 DB 기반 계정잠금'이라 명시하므로 로그인 계정이 이 결함만으로 "
     "뚫리진 않지만, 그 주석은 워커 프로세스 수 배수 문제만 다룰 뿐 같은 프로세스 안 "
     "스레드 경쟁은 다루지 않았다 — /api/leads 같은 공개 폼은 이 계층이 사실상 유일한 "
     "스팸 방어선이라 실피해가 있다. 고침 — 모듈 전역 _rate_lock = threading.Lock() 신설, "
     "check_rate_limit() 의 정리+확인+추가 구간 전체를 with _rate_lock: 로 감쌈(임계구간이 "
     "전부 인메모리 연산뿐이라 락 경합 비용 무시할 만함, 키별 락 아닌 전역 락 하나로 충분). "
     "회귀테스트(test_scan_round588_fixes.py, 18개 검사) 신설 — DB 를 안 건드리는 순수 "
     "인메모리 함수라 서버·DB 픽스처 없이, app.py 실제 소스에서 함수를 오려내(on-disk "
     "파일은 안 건드림) 'bucket.append(now)' 직전에만 테스트 전용 배리어 훅을 심어 exec() "
     "하고(round585 기법) 실제 Flask test_request_context + 진짜 threading.Thread 12개로 "
     "부른다(round566 기법 — 순수 스레드경쟁+전환간격 조정만으로는 재현 안 됨을 먼저 "
     "확인한 뒤 배리어로 전환). 지금 코드는 12스레드 동시경합에도 배리어 훅 도달·허용·"
     "최종버킷길이가 모두 정확히 limit=3. 되돌리기-증명 — with _rate_lock: 한 줄만 지우고 "
     "들여쓰기만 되돌린(break 이후 문자열 완전동일 대조) 옛 버전은 같은 경합에서 12스레드 "
     "전부 훅 도달·전부 허용·최종버킷길이 12(limit 4배 초과) 실측 — '한도 안'에서 '한도 "
     "밖'으로가 이 수정의 인과효과. 첫 실행 18/18 통과, 3회 재실행 전부 안정(배리어 기반이라 "
     "결정론적). app.py 자신을 고쳤으므로 서버 재기동 필요, BUILD_HASH 로테이션 예상."),
    ("test_scan_round590_fixes.py", "스캔 590라운드 회귀 — 계정 잠금(_recent_fails/"
     "_log_attempt, 로그인·OTP·비밀번호변경 등 8곳이 공유하는 무차별대입 방어)의 "
     "'실패횟수 확인(SELECT)'과 '실패 기록(INSERT)' 사이에 느린 verify_pw(PBKDF2 60만회, "
     "실측 평균 111ms)가 끼어 있는데 그 구간을 잠그는 코드가 전혀 없던 결함 + 첫 고침을 "
     "실행 기반 배터리로 재확인하다가 잡은 2차 결함 세 가지(직접조사, 하위위임 없음). "
     "조사 각도 — 오케스트레이터가 round588·589 뒤에 준 '다른 in-memory 공유상태' 각도로 "
     "app.py 전역 가변상태를 재훑었다 — _ASSET_VER(무해)·_rate_buckets/_rate_lock(round588 "
     "기수정)·_LAST_INLINE_SWEEP(무해, DB 트랜잭션 자체가 동시안전) 다음으로, "
     "check_rate_limit() 바로 위 주석('계정 잠금은 DB 기반이라 워커·재시작에 안전하다')이 "
     "세운 전제를 의심해 _recent_fails/_log_attempt 8개 호출부를 전수 확인 — 어디에도 "
     "BEGIN IMMEDIATE 가 없었다(app.py 안 145곳 넘는 BEGIN IMMEDIATE 중 이 자리엔 한 번도 "
     "안 씀). 영향(과장하지 않음) — waitress 스레드풀(기본 8)과 /api/login 자신의 "
     "레이트리밋(5분 10회)이 상한을 걸어 두어 무제한 대입은 아니지만, 잠금 창(기본 10분)"
     "마다 의도한 MAX_LOGIN_FAILS(5)회 대신 최대 min(스레드수,레이트리밋)회(기본 최대 "
     "8~10회)까지 새어 '창당 최대 N회'라는 계정 잠금 자신의 정의를 못 지켰다 — "
     "check_rate_limit() 을 결함으로 판정한 것과 같은 기준. 1차 고침(_recent_fails/"
     "_log_attempt 단일 공유 지점) — 느린 verify_pw 를 BEGIN IMMEDIATE 로 통째로 감싸면 "
     "검증 한 번마다 앱 전체 쓰기가 멎으므로(사진 업로드 AI 분류를 트랜잭션 밖에서 하는 "
     "것과 같은 이유로 금지) 대신, 커밋된 실패수에 '지금 검증 중이라 아직 안 커밋된' "
     "시도수를 더한다 — round588 이 만든 _rate_lock/_rate_buckets 를 그대로 재사용해(새 "
     "전역 없음) LOGINFLIGHT:+username 키에 시각을 적립하고(_recent_fails) 검증이 끝나면 "
     "지운다(_log_attempt). 이 1차 고침만으로 --quick 배터리를 실제로 돌려 보니 기존 "
     "회귀 3개가 깨졌다 — 추측이 아니라 배터리 자신이 잡아낸 것들이다. 2차 결함(a, "
     "test_scan_round37_fixes.py 가 잡음) — 표식이 5초 안에 스스로 지워지므로 괜찮다고 "
     "생각했는데, api_login() 의 OTP 관문 확인(뒤이어 _log_attempt 를 절대 안 부르는 "
     "'조회 전용' 호출 — 실제 코드 검증은 별도 엔드포인트 /api/login/otp 가 한다)처럼 "
     "**매번** 표식만 남기고 끝나는 호출은 지울 사람이 아예 없어, 5초 내내 살아남으며 "
     "그 사이 도착하는 진짜 시도 전부의 집계를 +1 씩 영구히 부풀렸다(실측: 정상 5회째가 "
     "401 대신 429). 고침 — mark_inflight=False 매개변수를 추가해 그 관문 확인 한 곳만 "
     "표식 자체를 안 남기게 함(호출 시그니처는 그대로, 새 인자 기본값이 기존 동작을 "
     "그대로 보존). 2차 결함(b, test_scan_round413·414_fixes.py 가 잡음) — 이미 문턱을 "
     "넘은 뒤에도(그 이후 요청은 caller 가 곧 거절해 _log_attempt 가 절대 안 불린다) "
     "_recent_fails 는 그때마다 표식을 계속 새로 남겼다 — 잠긴 계정을 계속 두드리기만 "
     "해도(공격자의 전형적 행동) 표식이 한도 없이 쌓이고, 관리자가 수동잠금해제로 DB 행을 "
     "지운 직후에도 안 지워진 표식 때문에 몇 초간 잠금이 유령처럼 되살아났다(실측: 정상 "
     "5회째가 401 대신 429, 잠금해제 직후 재시도도 429). 고침 — db_fails+inflight 합계가 "
     "이미 MAX_LOGIN_FAILS 이상이면 표식 자체를 안 남기도록 게이팅(거절될 시도의 자리를 "
     "미리 차지할 이유가 없다). 2차 결함(c, 직접 대조로 발견) — 표식 키가 아이디만으로 돼 "
     "있어(IP 없음) _recent_fails 자신이 문서화한 방어 ②(계정 잠금 DoS — 아이디만 알면 "
     "다른 IP 의 정당한 로그인까지 잠글 수 있던 옛 결함)를 인메모리 계층에서 다시 열고 "
     "있었다 — DB 조회는 (아이디,IP) 로 좁히는데 인메모리 표식만 아이디 단독이라, 공격자가 "
     "자기 IP 에서 동시요청을 쏟아부으면 다른 IP 의 정당한 사용자 카운트까지 같이 오른다. "
     "고침 — 키에 client_ip() 를 더해 DB 와 같은 (아이디,IP) 단위로 좁힘. 부수 발견(이번 "
     "라운드 범위 밖, 직접 수정만 함) — 같은 배터리 재실행 중 api_unlock_login()(수동 "
     "잠금해제)의 실패기록 삭제 키 목록이 round414·488·554 가 이미 추가했던 'PW:'·'PWX:'·"
     "'OTPSETUP:' 세 창구 없이 옛(414 이전) 4개 키 형태로 되돌아가 있음을 발견(이 라운드가 "
     "손댄 적 없는 코드 — 이 프로젝트 자신의 문서화된 위험인 '동시세션 여러개 가능(git無)"
     "→라운드번호 파일 경합' 이 원인으로 추정) — 그 세 라운드 자신의 회귀테스트(414·488·"
     "554_fixes.py)가 이미 들고 있는 정확한 원문으로 복원, 세 테스트 모두 재실행해 그린 "
     "확인. 회귀테스트(test_scan_round590_fixes.py, 55개 검사) 신설 — [1]~[5]는 1차 고침을 "
     "round588 과 같은 '정확한 경계로 오려내 exec()' 기법으로 검증(경쟁 지점이 함수 하나 "
     "안이 아니라 두 함수 호출 사이라 소스에 배리어 훅을 심을 필요가 없다는 점이 round588과 "
     "다름 — 테스트 하네스 자신의 worker() 에서 그 경계에 threading.Barrier 를 둠), 진짜 "
     "SQLite 스크래치 DB(WAL) 위에서 진짜 threading.Thread N=10(THRESHOLD=실제 "
     "MAX_LOGIN_FAILS 값 그대로 사용)으로 지금/옛 버전을 경합시켜 지금 코드는 정확히 "
     "threshold 개만 허용·DB 커밋도 threshold 이하, 되돌린 옛 버전은 N개 전부 허용·DB 에 "
     "N행 커밋(인과관계 직접증명)까지 확인. [6][7][8]은 2차 결함 (a)(b)(c) 각각을 함수 "
     "수준에서 원인·수정 양쪽 다 대조군과 함께 재현 — mark_inflight 유무 대조, 문턱 게이팅 "
     "유무 대조(이미 잠긴 뒤 20회를 더 두드려도 지금 코드는 표식 0개·게이팅 없는 대조군은 "
     "20개), IP 포함/제외 대조(공격자 IP 가 아무리 두드려도 다른 IP 의 조회는 영향 없음을 "
     "지금 코드로, 키에서 IP 를 빼면 오염됨을 대조군으로 확인). 회귀테스트 첫 초안 자체의 "
     "버그도 하나 잡음 — '순차' 검증이 스레드를 전부 먼저 start() 해 버려 배리어 없이도 "
     "동시성이 생기던 하네스 결함, start-then-join 을 하나씩으로 고쳐 해결(회귀 방지 주석 "
     "남김). 최종 55/55 통과, 3회 재실행 전부 안정(배리어 기반이라 결정론적). app.py 자신을 "
     "고쳤으므로(_recent_fails/_log_attempt/api_login 호출부 1곳/api_unlock_login 복원) "
     "서버 재기동 필요, BUILD_HASH 로테이션 예상."),
    ("test_scan_round591_fixes.py", "스캔 591라운드 회귀 — round590이 '동시세션 "
     "파일경합'으로만 추정하고 넘어간 api_unlock_login() keys 일시 되돌아감의 정확한 "
     "인과관계를 확정. 직접 조사(하위위임 없음) 결과: 별도 세션 없이도 이 저장소 자기 "
     "자신의 test_scan_round414_fixes.py [7-3]이 원인이었다 — 그 스텝이 옛 세대"
     "(round409~515대) 기법으로 reverted_3(옛 4키 버전)를 실제 on-disk app.py 에 잠깐 "
     "써넣고 하위 프로세스를 돌린 뒤 finally 에서 복원했는데, 복원 로직 자체는 항상 "
     "정확했지만(APP_SRC 매번 새로 읽음, NEW_3 하드코딩 리터럴도 지금 app.py 문구와 "
     "바이트 단위 일치 확인 — '복원이 낡은 버전으로 된다' 가설은 직접 대조로 반증) "
     "write→subprocess→restore 사이 실제 파일이 옛 코드로 열려 있는 창 자체가 실재해 "
     "그 순간 이 저장소를 읽는 어떤 창구든(동시 세션이든 이 세션 자신의 병렬 Read든) "
     "옛 코드를 보게 됐다(스크래치 더미파일 재현으로 관측 가능함을 실측 확정). 같은 "
     "함수를 다루는 형제 round554([4])가 이미 쓰던 '실제 파일은 전혀 안 건드리는' "
     "exec()-네임스페이스 기법으로 [7-3]만 옮겨 창을 없앴다(OLD_3/NEW_3 상수와 증명 "
     "내용은 그대로, 기법만 교체 — test_scan_round414_fixes.py 수정, 18/18 재확인). "
     "7-1·7-2(change-password·otp-disable)는 이번 라운드가 관측한 증상과 무관해 손대지 "
     "않음(같은 부류 위험 남아있음, 별도 판단 영역). 회귀테스트(test_scan_round591_"
     "fixes.py, 13개 검사) 신설 — [0]은 정적 확인([7-3]이 안전 기법을 쓰고 7-1/7-2는 "
     "의도대로 그대로임), [1]은 격리 재현(더미 스크래치 파일만 사용 — 옛 기법과 같은 "
     "모양이 동시 폴러에게 관측 가능한 창을 만듦을 실측 증명), [2]는 실제 실행 기반 "
     "회귀 가드(지금 코드의 test_scan_round414_fixes.py 를 실제로 돌리며 진짜 app.py 를 "
     "계속 폴링해 api_unlock_login() 이 단 한 번도 옛 4키로 안 보임 + 실행 전후 app.py "
     "해시 완전 동일까지 확인). 최종 13/13 통과. 순수 테스트 파일만 고쳤으므로(app.py 자신은 "
     "손 안 댐) 서버 재기동 불필요."),
    ("test_scan_round592_fixes.py", "스캔 592라운드 회귀 — 극단값 입력 각도로 새로 조사. "
     "POST /api/admin/notifications/read(콘솔 알림 읽음처리)가 id를 숫자로 못 바꾸는 값"
     "(문자열·리스트·객체·4300자리 넘는 숫자문자열 등)으로 받으면 int(d[\"id\"])가 "
     "ValueError/TypeError를 던지는데 이 함수의 except는 sqlite3.Error만 잡아 그대로 "
     "새 나가 500(SERVER_ERROR)이 됐다 — 형제(10657행 api_case_update의 "
     "warranty_months·18037행 api_dispatch_assign의 partner_id 등 이 파일 전체가 쓰는 "
     "압도적 다수 관례)는 전부 int()를 try/except(TypeError,ValueError)로 감싸 400을 "
     "돌려주는데 이 자리만 빠져 있었다(이 파일에서 int(d[\"필드\"]) 직접 캐스팅 단 2곳 "
     "중 유일한 예외). 고침 — BEGIN IMMEDIATE(쓰기 잠금)를 열기 전에 미리 파싱·검증해 "
     "잘못된 값이면 트랜잭션을 열지도 않고 400으로 끝낸다(같은 로직 위치만 이동, "
     "정상 경로 무변경). 부수 확인 — 예외가 새 나가도 전역 err_500 핸들러(1291행)가 "
     "해당 요청 커넥션을 전부 rollback+close 하므로 실제로는 쓰기 잠금이 눌러붙지 "
     "않는다(회귀테스트로 실측 확인) — 이번 결함은 잠금 누수가 아니라 '친절한 400 대신 "
     "불필요한 500 + 로그 소음'이었다. 회귀테스트(test_scan_round592_fixes.py, 26개 "
     "검사) 신설 — [1]은 소스 확인(검증이 BEGIN IMMEDIATE보다 먼저), [3]은 극단값 6종 "
     "전부 400 확인 + 양성대조(정수·숫자문자열 id는 여전히 200, 엉뚱한 행 미변경, "
     "잘못된 요청 직후에도 정상 요청이 곧바로 200), [4]는 round565와 같은 "
     "view_functions 임시치환 기법으로 되돌린 옛 버전이 실제로 500을 재현함을 "
     "인과관계까지 직접 증명(실제 on-disk app.py는 안 건드림), [5]는 원상복구 확인. "
     "최종 26/26 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round593_fixes.py", "스캔 593라운드 회귀 — 국제화/인코딩 극단사례 각도로 새로 "
     "조사. api_contact_import(엑셀 연락처 일괄등록, 9663행)의 업체명 대조 말단경로"
     "(사업자번호가 없을 때만 타는 폴백)가 단순 SQL 바이트열 비교(WHERE name=?)였다 — "
     "유니코드는 같은 글자를 다른 바이트열로도 적을 수 있어(한글 자모를 완성형 대신 "
     "풀어쓴 NFD, 맥에서 복사한 텍스트에 흔함) 시각적으로 완전히 같은 업체명이 "
     "정규화 형태만 달라도 대조가 실패해 실재하는 업체가 '존재하지 않음'(skip_none)"
     "으로 조용히 버려졌다 — 라운드458이 보험사명 등록 중복검사에서 이미 고친 것과 "
     "같은 결함군인데(app.py 전체에서 unicodedata.normalize 호출은 그 한 곳뿐이었다) "
     "이 형제 경로만 못 받았다. 고침 — 잠금을 잡기 전에 partners 전체를 한 번 읽어 "
     "이름을 NFKC로 정규화한 사전을 만들고(round70의 '쓰기 잠금은 짧게' 원칙과 같은 "
     "자리), 엑셀 업체명도 같은 방식으로 정규화해 대조한다(SQL WHERE 대신 파이썬 "
     "사전 조회로 전환 — 업체 400여 곳, _onboard_rows가 이미 쓰는 '전부 읽어 파이썬 "
     "에서 거른다' 관례와 동일). partners.name 저장 시점(신청승인·직접등록·정보수정 "
     "3곳)은 이번 라운드에서 손대지 않았다 — 관리자가 언제든 이름을 다시 입력할 수 "
     "있어 저장값의 정규화 형태를 보장할 수 없으므로, 저장을 막는 대신 대조 자체를 "
     "정규화 후 비교로 바꿔 어느 쪽이 저장돼 있어도 항상 맞게 만들었다(round458과 "
     "달리 이쪽은 쓰기 지점이 여럿이라 '저장 시 정규화'만으로는 과거 데이터를 못 "
     "덮는다). 부수 효과 — 정규화 형태가 서로 다르게 저장된 동명업체 2곳을 이제 "
     "'동명업체' 애매함으로 정확히 잡아낸다(옛 코드는 이 경우를 감지 못해 우연히 "
     "바이트가 맞는 한쪽만 조용히 갱신할 위험이 있었다). 회귀테스트"
     "(test_scan_round593_fixes.py, 9개 검사) 신설 — [1]은 소스 확인, [2]는 NFD로 "
     "되올린 엑셀 이름이 NFC로 저장된 기존 업체와 실제 매칭·DB 반영까지 확인(핵심 "
     "재현), [3]은 unicodedata.normalize를 프로세스 메모리에서만(디스크 무수정) "
     "항등함수로 바꿔 옛(취약) 동작 — not_found로 빠지고 DB도 안 바뀜 — 이 실제로 "
     "재현됨을 인과관계까지 증명한 뒤 원복, [4]는 바이트가 완전히 같은 절대다수 "
     "경로가 그대로 매칭되는 회귀 없음 확인, [5]는 정규화 형태만 다른 동명업체 2곳이 "
     "애매함으로 걸러지고 어느 쪽도 조용히 안 바뀌는 부수 안전성 확인. 최종 9/9 통과. "
     "app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round594_fixes.py", "스캔 594라운드 회귀 — round593과 같은 국제화/인코딩 "
     "각도로 'app.py 전체에서 name= 류 SQL 바이트비교를 쓰는 다른 자리' 전수확인. "
     "api_case_create(관리자 콘솔 사건 등록, POST /api/cases, 11496행)가 insurer_id "
     "없이 보험사 이름만 왔을 때 유일매칭을 시도하는 폴백(11550행)이 단순 SQL "
     "바이트열 비교(WHERE name=?)였다 — round593이 api_contact_import에서 고친 것과 "
     "같은 결함군의 세 번째 인스턴스(첫 번째는 round593이 고쳤고, 두 번째 "
     "api_application_create는 이미 별도 태스크 task_f15d21d5로 이관되어 이번 라운드는 "
     "손대지 않음). 지금 admin.js의 createCase()는 <select> 옵션 id를 항상 같이 "
     "보내 이 폴백을 안 타지만, 이 라우트는 require_admin뿐이라 관리자 세션으로 "
     "이름만 보내는 직접 호출(스크립트 연동·향후 폼 변경)이 가능하고, 그 이름이 "
     "등록된 보험사명과 유니코드 정규화 형태만 달라도(NFD 등) 시각적으로 완전히 "
     "같은 보험사가 NO_INSURER 400으로 튕겼다. 고침 — insurer_id가 없을 때 insurers "
     "전체를 읽어 이름을 NFKC로 정규화해 대조한다(round593과 같은 처방). round105가 "
     "건 '유일하게 하나만 맞을 때만 해석'하는 동명 보험사 안전장치(COUNT(*)=1)는 "
     "그대로 유지 — 정규화 형태만 다른 동명 보험사 2곳이 있어도 여전히 애매함으로 "
     "막힌다. (같은 파일에 있는 나머지 두 name= 폴백 — 3701행 _insurer_settlement_scope, "
     "5023행 파트너 정산 대시보드 — 은 매번 인증된 자기 자신의 DB 레코드 이름끼리 "
     "대조하는 DB-대-DB 비교라 이번 결함과 위협모델이 달라 손대지 않음.) 회귀테스트"
     "(test_scan_round594_fixes.py, 12개 검사) 신설 — [1]은 소스 확인, [2]는 NFD로 "
     "보낸 보험사 이름이 NFC로 저장된 기존 보험사와 실제 매칭되어 사건이 생성되고 "
     "DB에도 올바른 insurer_id가 반영됨을 확인(핵심 재현), [3]은 "
     "unicodedata.normalize를 프로세스 메모리에서만(디스크 무수정) 항등함수로 바꿔 "
     "옛(취약) 동작 — NO_INSURER 400으로 빠지고 사건도 안 만들어짐 — 이 실제로 "
     "재현됨을 인과관계까지 증명한 뒤 원복, [4]는 바이트가 완전히 같은 이름은 그대로 "
     "매칭되는 회귀 없음 확인, [5]는 정규화 형태만 다른 동명 보험사 2곳이 애매함으로 "
     "걸러지고 사건이 생성되지 않는 부수 안전성 확인. 최종 12/12 통과. app.py 자신을 "
     "고쳤으므로 서버 재기동 필요."),
    ("test_scan_round595_fixes.py", "스캔 595라운드 회귀 — round592~594와 다른 각도(실제 HTTP "
     "클라이언트가 보낼 수 있는 극단값 URL·쿼리스트링)로 새로 조사. 같은 근본원인(sqlite3가 "
     "자기 INTEGER 컬럼의 실제 상한 — 부호있는 8바이트, 2**63-1 — 을 넘는 파이썬 int를 "
     "바인딩하려 하면 OverflowError를 던지는데, 그 값이 전역 예외핸들러까지 올라가 500 "
     "SERVER_ERROR로 새 '없는 자원'(정상 404/응답)과 전혀 다르게 응답한다)를 서로 다른 두 "
     "유입구에서 확인해 각자의 단일 공유 지점에서 고쳤다. 결함A — <int:...> 라우트 변환기"
     "(app.py 전체 120곳 — 사건·사진·협력사·입찰 등 거의 모든 상세/파일 라우트가 <int:cid> "
     "류를 쓴다)에 자릿수 상한이 없다(실측: /api/photos/<9×40자리>/file, "
     "/api/cases/<9×40자리>/detail 둘 다 500, 정상 out-of-range 대조군은 404) — 고침: "
     "라우트마다 <int(max=...):x>를 120번 반복하는 대신, app.py의 Flask 앱 생성 직후(첫 "
     "@app.get 데코레이터보다 반드시 먼저 — Werkzeug는 Rule을 라우팅 맵에 추가하는 시점에 "
     "변환기를 인스턴스화해 그 Rule에 고정하므로 순서가 틀리면 이미 등록된 라우트에 효과가 "
     "없다) 기본 int 변환기 자체를 sqlite 상한으로 막는 _BoundedIntConverter로 교체 — 한 "
     "지점 수정으로 120곳 전부가 함께 방어된다. 결함B — /api/insurer-statement·-export "
     "두 라우트는 int(request.args.get('insurer_id'))가 성공하면 그대로 믿는데(파이썬 "
     "int()는 자릿수 제한이 없다), 결함A의 라우트 변환기는 URL 경로만 검사해 쿼리스트링은 "
     "못 막는다(실측: 두 라우트 모두 huge insurer_id에서 500) — 고침: 두 라우트가 공유하는 "
     "_insurer_statement() 안에서 sqlite에 안전하게 바인딩할 수 없는 insurer_id를 -1(실제 "
     "id와 절대 안 겹침)로 치환 — 이 함수는 이미 '존재하지 않는 id'를 정상 처리하므로 "
     "호출부·반환 모양을 바꿀 필요가 없었다. 두 결함 모두 정보 유출은 없지만(450라운드 "
     "전역 핸들러가 이미 참조번호만 노출) 스캐너·봇의 무작위 대입·연동 스크립트 자릿수 "
     "오타만으로도 실서비스 로그가 이 소음(매번 전체 스택트레이스)으로 채워지고, 실제 "
     "자동증가 id·insurer_id는 이 상한 근처에도 못 가 정상 동작에는 영향이 없다. "
     "회귀테스트(test_scan_round595_fixes.py, 24개 검사) 신설 — [1]은 소스 확인(변환기 "
     "등록이 첫 라우트보다 앞선다는 순서 불변조건, 두 결함의 상수(2**63-1) 통일 포함), "
     "[2]는 결함A의 서로 다른 두 라우트 모두 huge id에서 404를 받아 한 지점 수정이 여러 "
     "라우트에 함께 적용됨을 확인(핵심 재현), [3]은 이미 바인딩된 Rule의 변환기 인스턴스 "
     ".max 속성만 프로세스 메모리에서(디스크 무수정) 임시로 None으로 되돌려 옛(취약) 동작 "
     "— 실제 뷰의 SELECT ... WHERE id=? 바인딩에서 OverflowError가 발생해 500 "
     "SERVER_ERROR로 되돌아감 — 이 실제로 재현됨을 인과관계까지 증명한 뒤 원복, [4]는 실제 "
     "존재하는 사건이 정상 id로 여전히 200을 받고 경계값 id=0도 평소처럼 라우팅됨을 확인"
     "(회귀 없음), [5]는 sqlite 상한값 자체는 정상 라우팅되고 상한+1만 라우터 단계에서 "
     "걸러짐을 확인(경계 정확성), [6]은 결함B의 두 라우트 모두 huge insurer_id에서 500이 "
     "아니라 '존재하지 않는 보험사'와 동일한 200을 받음을 확인(핵심 재현), [7]은 "
     "_insurer_statement를 새 가드가 빠진 대역으로 몽키패치(디스크 무수정)해 같은 huge "
     "insurer_id가 실제로 500 SERVER_ERROR를 냄을 확인한 뒤 원복(인과관계 증명), [8]은 "
     "실제 존재하는 보험사가 정상 insurer_id로 여전히 올바른 명세를 받음을 확인(회귀 "
     "없음), [9]는 insurer_id=0은 그대로 400(기존 검증 유지)이고 자릿수만 큰 음수도 "
     "sqlite에 안전한 보통 음수(-5)와 동일하게 200으로 처리되며 sqlite 상한값 자체는 "
     "정상 처리됨을 확인(경계 정확성 — 새 가드가 새 상태코드를 만들지 않는다). 최종 "
     "24/24 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round596_fixes.py", "스캔 596라운드 회귀 — round595와 같은 근본원인(자릿수만 "
     "비정상으로 큰 정수 바인딩 시 sqlite3 OverflowError→500)을 세 번째 유입구(JSON 본문 id)"
     "에서 확인. round595는 URL 경로(<int:...> 변환기)·쿼리스트링(insurer_id) 두 곳을 "
     "고쳤는데, 이 파일 전체가 본문 id류에 쓰는 관례 `except (TypeError, ValueError)`는 "
     "자릿수만 큰 순수 숫자 문자열엔 안 걸린다(int()는 자릿수 제한이 없어 ValueError가 "
     "안 남 — round592가 고친 '숫자가 아닌 값'과는 다른 입력 모양). 실측(직접조사, 하위위임 "
     "없음): api_admin_notifications_read에 body={'id':'9'*40}을 보내면 UPDATE ... WHERE "
     "id=? 바인딩에서 OverflowError가 나 500 — 같은 관례를 쓰는 api_dispatch_assign의 "
     "partner_id 등 이 파일에 흩어진 여러 곳이 전부 같은 값(직접 확인). 고침 — 흩어진 "
     "호출부를 전부 고치는 대신, 이 예외가 모이는 단 하나의 지점인 전역 예외핸들러 "
     "err_500(app.py) 안에서 OverflowError만 골라 400(BAD_INPUT)으로 돌린다. 기존 "
     "커넥션 정리(_cleanup_conns)·로깅 파이프라인은 그대로 재사용(새 정리 로직 없음). "
     "회귀테스트(test_scan_round596_fixes.py, 16개 검사) 신설 — [1]은 소스 확인(분기 "
     "위치가 HTTPException 판정 뒤·커넥션 정리 앞에 온다는 순서), [2]는 서로 무관한 두 "
     "호출부(본문 id·partner_id) 모두 500이 아니라 400을 받아 한 지점 수정이 여러 "
     "호출부에 함께 적용됨을 확인(핵심 재현), [3]은 Flask에 실제 등록된 예외핸들러를 "
     "새 분기가 빠진 옛 버전으로 메모리에서만 바꿔치기해(디스크 무수정) 같은 요청이 "
     "실제로 500 SERVER_ERROR로 되돌아감을 확인한 뒤 원복(인과관계 증명), [4]는 overflow "
     "직후 같은 라우트(쓰기 잠금을 여는 경로)를 다시 두드려도 busy_timeout(8초) 대기 "
     "없이 즉시 응답해 쓰기 잠금이 안 샜음을 확인(기존 커넥션 정리 파이프라인 재사용 "
     "검증), [5]는 정상 id·round592가 고친 '숫자 아님' 케이스·이 결함과 무관한 예외"
     "(KeyError)가 전부 회귀 없이 그대로 동작함을 확인(과잉 변경·과잉 일반화 아님). "
     "최종 16/16 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round598_fixes.py", "스캔 598라운드 회귀 — 관리자 엑셀/CSV 내보내기 2곳"
     "(api_export_xlsx·api_settlements_export)에 행수 상한이 전혀 없던 결함. 지시받은 "
     "신선한 각도 '대량 데이터 내보내기의 메모리 사용'을 실제로 재현 — 형제"
     "(api_activity_export·api_partner_onboarding_export)는 이미 상한+잘림표시를 "
     "갖췄는데, cases·partners·settlements 등 가장 크게 자라는 6개 표를 한 곳에서 "
     "담당하는 api_export_xlsx 와 회계 대사용 정산 CSV 두 곳만 없었다(다른 내보내기 "
     "6개는 KPI 집계·1개월/1개 발주처 단위로 자연히 바운드돼 대상 아님 — 직접 확인). "
     "실측(격리 스크래치 DB, settlements 6만행 — 운영 43건의 약 1,400배): 상한 없는 "
     "옛 코드는 /api/export/settlements 단일 요청이 9분 넘게 안 끝나(CPU 563초·상주 "
     "512MB 이상 소진, 강제종료 시점 기준) waitress 스레드 하나를 그만큼 묶어 뒀다. "
     "고침 — SQL 문자열은 그대로 두고(round22의 'conn.execute(sql, p)' 원문 검증 유지) "
     "fetchmany(cap)로 자르고 COUNT(*) 서브쿼리로 전체건수를 따로 구해, 잘렸으면 "
     "그 사실을 파일 안에 적는다(활동로그 엑셀과 동일 원칙 재사용, 기본 20,000·최대 "
     "100,000 동일). 회귀테스트(test_scan_round598_fixes.py, 33개 검사) 신설 — [1]은 "
     "소스 확인, [2]는 실제 서버 경로로 15건 중 낮은 ?max=로 잘림을 강제해 안내문구· "
     "머리글 위치·정확한 건수·감사로그 기록까지 확인하고 안 잘리는 경우(기존 계약: "
     "헤더=1행) 회귀 없음도 함께 확인, [3]은 상한 로직이 빠진 옛 버전을 "
     "view_functions 딕셔너리로 메모리에서만 바꿔치기해(디스크 무수정) 같은 요청이 "
     "실제로 ?max=를 무시하고 전부 돌려줌을 확인한 뒤 원복(인과관계 증명). 최종 33/33 "
     "통과. 수정 후 성능 특성(참고용, 부가 실측): cap=100→0.7초, cap=2000→2.5초, "
     "기본상한 20,000(15열 xlsx, 6만행 테이블 기준)→158초·98.5MB, 같은 조건 CSV는 "
     "1.6초 — openpyxl 쪽이 non-linear로 무거워지는 것으로 보임(원인 미상, 원인규명은 "
     "범위 밖). 상한이 전혀 없던 것(무한 대기)보다는 명확한 개선이지만, cases· "
     "settlements가 실제로 20,000건 근처까지 자라면 이 특정 xlsx 섹션은 리버스프록시/"
     "터널 타임아웃(보통 60~100초)에 먼저 걸릴 수 있다 — 599라운드 인계: 필요하면 "
     "이 섹션 전용으로 cap을 더 낮추거나 openpyxl write_only 모드 전환을 검토할 것"
     "(이번 라운드는 무한→유한 전환까지만, 그 이상은 범위 밖으로 남김). app.py 자신을 "
     "고쳤으므로 서버 재기동 필요."),
    ("test_scan_round599_fixes.py", "스캔 599라운드 회귀 — 정산취소 CSV(api_settlements_"
     "export, 회계 대사용)가 셀 정제를 공유 _xl_safe() 대신 로컬 _csv_safe() 로 따로 "
     "재구현해, 트리거 아닌 제어문자 보존 범위가 갈라져 있던 결함. _xl_safe·_csv_safe "
     "형제 쌍은 이미 5개 라운드(34·423·532·550·578)가 '수식주입 트리거 문자 집합' "
     "일치를 정밀 감사했지만, 트리거가 아닌 문자를 어떻게 보존하는지는 비교한 적이 "
     "없었다. 실측(exec 격리): _xl_safe('1줄\\n2줄')는 그대로인데 로컬 _csv_safe는 "
     "'1줄2줄'(개행이 치환이 아니라 삭제돼 단어 경계까지 사라짐). 실제 도달 경로 — "
     "api_settlement_void()의 reason은 .strip()만 하고 내부 개행은 그대로 저장하므로, "
     "여러 줄로 적은 정산취소 사유가 이 CSV에서만 줄바꿈이 사라진 채 붙어 나간다. "
     "round221(api_export_xlsx의 동일 패턴 중복재구현)과 완전히 같은 근본원인의 두 "
     "번째 사례 — 같은 처방으로 로컬 _csv_safe()를 없애고 공유 _xl_safe()를 그대로 "
     "쓴다(partner_accounts.py의 별도 _csv_safe는 업체명·지역·공종처럼 구조적으로 "
     "한 줄짜리 값만 다뤄 개행 도달 경로가 없음을 확인 — 이번 라운드는 손대지 않음). "
     "회귀테스트(test_scan_round599_fixes.py, 13개 검사) 신설 — [1]은 소스 확인(로컬 "
     "정의 제거·_xl_safe 호출 전환, _xl_safe 자신의 개행보존·탭우회 방어는 회귀 없음), "
     "[2]는 실제 Flask+DB로 개행 포함 취소사유를 가진 정산을 만들어 CSV로 내보내 "
     "개행이 그대로 담기고 수식주입 방어도 회귀 없이 동작함을 확인, [3]은 옛 로컬 "
     "_csv_safe 동작을 view_functions 딕셔너리로 메모리에서만 재현해(디스크 무수정) "
     "같은 데이터에서 실제로 개행이 사라짐을 확인한 뒤 원복(인과관계 증명). 최종 "
     "13/13 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round601_fixes.py", "스캔 601라운드 회귀 — 보험사 사건 등록 공용 헬퍼 "
     "_create_case()의 접수번호(case_no) 정제가 형제들(region·address·manager·"
     "victim_name·victim_phone·note, 전부 _s() 사용)과 달리 raw (d.get(\"case_no\") "
     "or \"\").strip() 이라, 보험사 전산이 접수번호를 숫자로 보내면 AttributeError: "
     "'int' object has no attribute 'strip' 로 500이 나던 결함. 조사 배경 — 운영 "
     "로그(bokguon.log) 전수 분류 중 발견한 시그니처 대부분(round527·430·199·538 등, "
     "예: 'type object is not supported' 249건)은 각 라운드 자신의 회귀테스트가 "
     "되돌리기 증명용으로 낸 고의 주입 결함(직접 재현으로 확인, 실제 소스는 정상)인데, "
     "이 AttributeError(2026-08-05, POST /api/v1/cases, _normalize_categories 안)는 "
     "이미 _s()로 고쳐져 있었으나 같은 함수의 case_no 칸까지는 못 미쳤다 — _s() 자신의 "
     "문서가 정확히 지목하는 패턴이 바로 옆 줄에 남아 있었다. 실제 도달 경로 — POST "
     "/api/v1/cases(API 연동)·POST /api/insurer/cases(포털) 둘 다 이 공용 헬퍼를 "
     "부른다. 고침 — 같은 함수 안 형제들이 이미 쓰는 _s(d.get(...), n) 패턴을 이 칸에도 "
     "그대로 적용(app.py, _create_case() 안 case_no 정제 한 줄). 회귀테스트"
     "(test_scan_round601_fixes.py, 12개 검사) 신설 — [1]은 소스 확인(raw .strip() "
     "제거·_s() 전환), [2]는 실제 Flask+DB로 /api/v1/cases에 case_no를 정수로 보내 "
     "500 대신 201과 문자열화된 case_no를 확인(+문자열 case_no 무회귀·20자 상한 "
     "유지), [3]은 수정 직전 원문을 재구성해 실제로 AttributeError가 남을 확인한 뒤 "
     "지금 소스에서 그대로 뽑은 문장은 예외 없이 동작함을 대조(인과관계 직접증명). "
     "최종 12/12 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round602_fixes.py", "스캔 602라운드 회귀 — 보험사 사건 등록 멱등키 "
     "지문 헬퍼 _idem_fingerprint()의 address 정제가 형제(_create_case() 안 case_no, "
     "라운드601)와 같은 결함으로 raw (d.get(\"address\") or \"\").strip() 이라, 보험사 "
     "전산이 주소를 숫자로 보내면(우편번호를 주소칸에 넣는 등) AttributeError: 'int' "
     "object has no attribute 'strip' 로 500이 나던 결함. 조사 배경 — 이번 라운드 "
     "지시 각도 '_s()의 의도된 적용범위(보험사 서버-서버 연동) 전체 재확인'을 따라 "
     "_create_case() 자신(이미 601에서 case_no까지 전부 _s()로 통일됨, 클린 재확인)뿐 "
     "아니라 그 함수의 호출부(api_v1_case_create·api_insurer_case_create)가 공유하는 "
     "멱등키 지문 헬퍼까지 훑어 발견 — 바로 옆 줄 est_price는 이미 str() 강제 뒤 "
     ".strip()인데(안전) address만 그 강제가 빠져 있었다. 실제 도달 경로 — POST "
     "/api/v1/cases에 Idempotency-Key(헤더 또는 본문 idempotency_key/ext_ref)를 실어 "
     "보내면 _create_case() 자신은 이미 _s()로 안전하게 저장한 뒤 _idem_fingerprint(d)가 "
     "지문 UPDATE를 위해 raw d를 다시 읽어 그 자리에서 크래시한다(같은 키 재시도 시의 "
     "지문 비교 호출도 동일 결함). 운영 로그(bokguon.log) 전수 마이닝으로는 이 조합의 "
     "실제 사례를 못 찾았다(과거 결함주입 조사 시점엔 없었던 멱등키 기능의 이 경로까지는 "
     "안 닿았던 것으로 보임) — 이번 라운드는 로그 마이닝이 아니라 코드 대조로 찾은 "
     "사례. 나머지 조사 각도(페이지네이션 정렬안정성=이 앱엔 OFFSET/커서 페이지네이션 "
     "자체가 없어 해당없음, 알림톡 재시도=sweep_send_notifications가 이미 3회 재시도· "
     "소진알림·CAS로 성숙하게 처리 중이라 클린, 쿠키 Secure/HttpOnly/SameSite 전수="
     "Flask 세션 쿠키 1종뿐이고 이미 올바르게 설정됨을 확인)는 결함 없음. 로그 마이닝 "
     "중 발견한 나머지 시그니처(NameError _dov·KeyError open_defect_count·no such "
     "column: name 등)는 전부 이미 오래 전 라운드(106·530 등)가 고친 옛 결함이거나 "
     "각 라운드 자신의 되돌림-증명용 고의 주입(round199·430·450·485 등)이었다 — "
     "repair_estimate.py의 NaN 경로(round57이 math.isfinite로 이미 방어)는 전체 "
     "레시피 10종 × 숫자입력 전체에 NaN/Inf/극값을 직접 주입하는 퍼징으로 재검증해 "
     "크래시 0건 확인. 고침 — 바로 옆 형제 est_price와 같은 목적의 공용 헬퍼 _s()를 "
     "이 칸에도 그대로 적용(app.py, _idem_fingerprint() 안 address 정제 한 줄). "
     "회귀테스트(test_scan_round602_fixes.py, 12개 검사) 신설 — [1]은 소스 확인(raw "
     ".strip() 제거·_s() 전환), [2]는 실제 Flask+DB로 Idempotency-Key와 숫자 address를 "
     "함께 보내 500 대신 201을 확인 + 같은 키 재시도가 200 duplicate로 살아남음(첫 "
     "번째 호출 지점도 안전) + 같은 키에 다른 숫자 address는 여전히 409 "
     "IDEM_KEY_MISMATCH로 정상 구분됨(식별력 유지) + 문자열 address 무회귀, [3]은 "
     "수정 직전 원문을 재구성해 실제로 AttributeError가 남을 확인한 뒤 지금 소스에서 "
     "그대로 뽑은 문장은 예외 없이 동작함을 대조(인과관계 직접증명). 최종 12/12 통과. "
     "app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_insurer_leak.py", "603라운드 신설 — test_partner_leak.py(협력사쪽, 라이브서버 대상)의 "
     "보험사쪽 대칭 회귀가 없다는 round422 제안(round435가 사진/문서 IDOR 핵심 6곳만 부분 "
     "충족)을 직접 조사(하위위임 없음) — round435 이후 168라운드 동안 아무도 안 채운 나머지 "
     "두 축을 확인: (a) 관리자 GET 라우트를 손목록이 아니라 @require_admin/@require_role "
     "정규식으로 자동추출해 보험사 세션으로 전수 두드리는 스윕이 이 저장소에 하나도 없었다 "
     "(협력사판엔 test_partner_leak.py [3]에 이미 있음). (b) 보험사 자신의 목록성 GET "
     "응답(대시보드·하자·정산명세 등)이 타 보험사 사건번호/피해자정보/추적토큰/업체계좌를 "
     "흘리는지 재귀 스캔하는 테스트도 없었다. 코드 자체는 클린 — (a)는 59개 관리자 GET "
     "라우트 전부 실제로 401/403, (b)는 대시보드·하자·알림·리포트·정산명세·하위계정·프로필 "
     "등 8개 응답 전부 타사(I1) 값·금지필드(비밀번호해시·업체계좌) 무검출, 사건상세/입찰 "
     "IDOR도 404로 정상 차단(round435와 같은 결과 재확인, 최소 재현)을 실제 Flask "
     "test_client+스크래치DB로 확인. round435와 같은 상황(버그를 고친 게 아니라 커버리지 "
     "공백만 메움)이라 되돌릴 옛 코드가 없어, [5][6]에서 두 새 축의 탐지력을 증명 — 단, "
     "round435와 달리 이번엔 **디스크의 진짜 app.py 파일에 깨진 코드를 절대 쓰지 않는다**(이 "
     "저장소가 git 없이 여러 세션이 동시에 같은 파일을 만질 수 있다는 이번 라운드 안전규칙에 "
     "따름) — 대신 A.app.view_functions 딕셔너리 항목 하나만 메모리에서 임시 치환(요청 "
     "직후 finally로 원복, 파일 변경 없음)해 [5]관리자게이트 무력화 시 실제 200(뚫림)을, "
     "[6]대시보드 타사값 유출 무력화 시 실제 재귀훑기가 그 값을 잡아냄을 각각 증명한 뒤 "
     "즉시 원복 확인(app.py mtime·해시 불변 직접 확인). 첫 실행 88/88 통과. 코드 변경 "
     "없음(app.py는 시작부터 끝까지 원본 그대로) — 서버 재기동 불필요."),
    ("test_scan_round603_fixes.py", "스캔 603라운드 회귀 — is_bot()(app.py, 공개폼 허니팟 판정)이 "
     "raw (d.get(...) or d.get(...) or \"\").strip() 이라 website_url/_hp 를 문자열이 아닌 값(숫자·"
     "배열·불리언 등)으로 보내면 AttributeError로 500이 나던 결함. round601(_create_case()의 "
     "case_no)·round602(_idem_fingerprint()의 address)와 같은 결함 패턴을 이번 라운드가 지시한 "
     "'형제결함탐지기법을 다른 결함군에도 적용'으로 직접 조사(하위위임 없음)하다 발견 — 앞의 둘은 "
     "보험사 B2B 연동(/api/v1/cases) dict였지만 이번 건은 완전히 다른 파이프라인인 미인증 공개폼"
     "(/api/leads·/api/applications)의 봇 차단 로직이라 round602의 전수대조 범위(보험사 사건생성 "
     "dict 하나) 밖이었다. 실제 Flask test_client로 재현 확인: {\"website_url\": 12345} 등을 두 "
     "라우트에 보내면 실제로 500 SERVER_ERROR가 남 — 더 나쁜 점은 is_bot() 자신의 설계의도(\"봇에게는 "
     "성공한 것처럼 보이게 한다\")가 크래시로 정반대로 뒤집힌다는 것. 고침 — 형제와 같은 처방인 _s() "
     "로 감싸 최종값만 안전하게 문자열화(app.py 1곳, is_bot() 본문) — or 단락 순서(website_url 우선, "
     "없으면 _hp)는 그대로 두어 0처럼 이미 falsy이던 값의 분기는 회귀 없음. 회귀테스트"
     "(test_scan_round603_fixes.py, 49개 검사) 신설 — [1]소스(새 코드 유일존재·옛 raw strip 소멸). "
     "[2]실제 HTTP로 두 라우트×두 필드×4개 비문자열타입 전부 500 대신 200(위장성공, ok:true·id:0) "
     "확인. [3]허니팟 필드 없는 정상 제출 회귀없음. [4]is_bot() 단위호출로 단락순서·0의 falsy분기가 "
     "그대로 보존됨을 확인. [5]되돌림-증명 — ⚠이 저장소는 git 없이 여러 세션이 동시에 같은 파일을 "
     "만질 수 있어 **디스크의 진짜 app.py에는 절대 깨진 코드를 쓰지 않고**, 대신 A.is_bot 모듈전역 "
     "이름을 옛 구현으로 monkeypatch(즉시 finally 원복)해 실제 라우트 호출로 500이 재현됨을 인과관계로 "
     "증명 후 원복 확인, app.py 파일 내용 자체는 테스트 시작부터 끝까지 미변경 확인(단, 이 마지막 "
     "불변검사는 다른 구식(파일-쓰기 되돌리기 방식) 회귀와 동시에 별도로 실행하면 그 테스트의 임시파일쓰기 "
     "창과 겹쳐 일시적으로만 실패할 수 있음을 이번 라운드가 직접 관찰 — run_all_tests.py 자신은 UNIT을 "
     "순차실행하므로 정식 배터리 안에서는 겹치지 않음). [사안2] 같은 라운드가 지시각도4(bokguon.log "
     "마이닝)를 이어가다 발견한 별개 결함 — run_all_tests.py:main() 이 UNIT 자식에게 BOKGUON_DB_PATH·"
     "BOKGUON_UPLOAD_DIR 은 스크래치로 갈라 주면서 BOKGUON_LOG_FILE 은 안 갈라, app.py:1226 LOG_FILE "
     "기본값이 이 저장소의 진짜 bokguon.log(실서버가 쓰는 그 파일)로 떨어지던 결함 — test_scan_round*.py "
     "400여 개 중 20개 남짓만 스스로 이 값을 세팅함을 grep으로 확인. 실측 — bokguon.log·log.1 마이닝 중 "
     "\"R430\"·\"R450-TEST-INJECTED-FAULT\"·\"simulated gate bug(round527 test)\"처럼 이름표 붙은 것부터 "
     "이름표 없이 진짜 운영장애처럼 보이는 \"Cannot operate on a closed database\"(2026-07-23~오늘까지 "
     "15~45분 간격 반복 — 이 배터리 주기와 일치)까지 발견, 후자를 열어 보니 파일경로가 test_scan_round527_"
     "fixes.py:_broken_record_gate 등 배터리 자신이었다. 이 발견 자체도 이 테스트를 처음 BOKGUON_LOG_FILE "
     "없이 작성해 돌리다 실서버 로그에 자기 크래시가 실제로 남는 것을 직접 관찰하며 재확인했다(그 직후 이 "
     "파일과 test_insurer_leak.py 둘 다에 BOKGUON_LOG_FILE 격리를 추가). 고침 — UPLOAD_DIR과 같은 자리· "
     "같은 패턴으로 run_all_tests.py:main()이 스크래치 BOKGUON_LOG_FILE 기본값을 한 곳에서만 세팅(이미 "
     "자기 몫을 세팅하는 20개는 os.environ.setdefault/직접대입이라 영향 없음). 회귀([6]~[9], 이 테스트에 "
     "포함) — 소스로 새 블록 유일존재·UPLOAD_DIR 블록 뒤 위치 확인, app.py의 LOG_FILE 폴백이 진짜 "
     "bokguon.log 경로와 정확히 일치함을 계산으로 확인(이 폴백은 실제로 타지 않음 — 실서버 로그에 절대 "
     "쓰지 않는다는 규칙 준수), round527 파일이 전제조건대로 BOKGUON_LOG_FILE을 스스로 안 세팅함을 확인, "
     "실제 run_all_tests.run()을 호출해 그 함수가 만든 스크래치 로그에 자식(round527)의 태그된 트레이스백이 "
     "실제로 담기는지 실행기반으로 확인(이 과정에서도 진짜 bokguon.log 크기·내용은 관찰 대상으로 삼지 "
     "않음 — 오직 스크래치 로그만 검사). 최종 56/56 통과(단독 실행), --quick 배터리 안에서도 재확인 — 이 "
     "수정 이후의 --quick 실행부터는 UNIT 400여 개가 더 이상 실서버 bokguon.log 에 쓰지 않는다(이 라운드 "
     "자신이 발견 전 이미 돌린 배터리 1회는 옛 코드로 돌아 실서버 로그에 그만큼 더해졌음 — 되돌릴 수 없고 "
     "bokguon.log는 읽기전용 규칙이라 그대로 둠). app.py·run_all_tests.py 둘 다 고쳤으므로 서버 재기동 "
     "필요(run_all_tests.py는 app.py가 import 안 하는 독립 실행기라 그 자체 변경은 재기동과 무관, app.py "
     "변경 때문에 재기동 필요)."),
    ("test_scan_round604_fixes.py", "스캔 604라운드 회귀 — 하자(defect/warranty) 서브시스템 + 시공완료보고의 "
     "자유텍스트 필드(title·content·resolution·reason·memo) 12곳이 형제결함군(round601 _create_case() "
     "case_no·round602 _idem_fingerprint() address·round603 is_bot() website_url/_hp)과 같은 raw "
     "(d.get(...) or \"\").strip() / (d.get(...) or \"\")[:N] / d['x'][:N] 패턴이라, 보험사 포털·협력사 포털이 "
     "그 필드를 숫자 등 비문자열로 보내면 AttributeError/TypeError로 500이 나던 결함. 조사 배경 — 지시각도(3) "
     "'4번째 인스턴스 사냥'을 따라 app.py 전체 notify() 호출 114건을 AST로 정적분석해 message 인자가 "
     "f-string/리터럴이 아닌 자리를 추리다(직접조사, 하위위임 없음) api_defect_update의 두 notify 조건이 raw "
     "(d.get(\"resolution\") or \"\").strip() 임을 발견, 같은 필드 재조회 지점(changed_fields 루프)까지 전수 "
     "grep해 3곳을 확정한 뒤 같은 하자 서브시스템의 형제 라우트(api_defect_create — 보험사 포털 또는 어드민, "
     "api_partner_defect_resolve·api_partner_defect_dispute — 협력사 포털)까지 넓혀 5곳을 더 찾았다. 1차 "
     "수정 후 실측([2])에서 보험사 포털의 숫자 title 이 여전히 500임을 발견 — f-string 보간 자체는 str() "
     "강제라 안전해도 그 안의 하위식(d['title'][:20])은 f-string이 문자열화하기 **전에** 평가된다는 것을 "
     "놓쳤었다(api_defect_create 안 notify·DB.log 각 1곳, 실측으로 교훈삼아 고침). 같은 실수를 안 했는지 "
     "정규식으로 raw dict 읽기+슬라이스/문자열메서드 직결 패턴을 app.py 전체에서 재확인하다 완전히 다른 함수 "
     "api_partner_complete(협력사 포털, 시공완료보고)의 memo(body().get(\"memo\", \"\")[:500] — \"memo\" 키가 "
     "있는데 비문자열이면 기본값이 안 먹혀 그대로 슬라이스됨)도 같은 결함임을 발견해 함께 고쳤다. 이 결함군은 "
     "이제 보험사 B2B API·공개폼에 이어 보험사 포털·협력사 포털까지 확인됐다(총 12개 지점, 5개 함수). 범위 "
     "판단(정책메모) — 같은 grep을 app.py 전체로 넓히면 관리자 콘솔 전용 경로(api_insurer_credentials·"
     "issue_partner_login의 login_id, api_notice_create의 title/body 등)에서 80곳 넘게 더 나온다 — 전부 "
     "로그인한 직원만 호출 가능해 이번 라운드 지시각도('새 파이프라인 사냥')의 목표 밖이라 의도적으로 손대지 "
     "않고 605 인계로 남긴다(전수 목록은 라운드604 최종보고 참고, 개별 패치보다 공용 정제 헬퍼/데코레이터가 "
     "나을 수 있다는 제안 포함). 고침 — 형제들이 이미 쓰는 _s(d.get(...), n) 을 12곳 전부에 적용: "
     "api_defect_create()는 _title = _s(d.get(\"title\"), 100) 을 함수 앞에서 한 번만 계산해 중복확인 쿼리·"
     "INSERT·notify·DB.log 네 곳에서 재사용(+content를 _s(d.get(\"content\"), 1000)로), api_defect_update()는 "
     "changed_fields 루프의 resolution 슬라이스와 '반려'·'하자이의처리' 두 notify 조건을 _s()로(cost_bearer "
     "조건은 이미 화이트리스트를 거쳐야만 도달하므로 그대로 둠), api_partner_defect_resolve()·"
     "api_partner_defect_dispute()·api_partner_complete()는 각각 resolution/reason/memo 한 줄씩. 회귀테스트"
     "(test_scan_round604_fixes.py, 48개 검사) 신설 — [0]은 소스 확인(12곳 전부 옛 raw 패턴 소멸·_s() 전환, "
     "주석 제외 코드만 대조), [1]~[4B]는 실제 Flask+스크래치DB로 어드민·보험사·협력사 세 세션 전부에서 "
     "숫자·비문자열 필드를 실제로 보내 500 대신 200과 문자열화된 DB 저장값을 확인, [5]는 정상 문자열·기존 "
     "화이트리스트/길이검증이 그대로임을 확인(과잉교정 없음), [6]은 되돌림-증명 — 진짜 app.py 파일은 전혀 "
     "안 건드리고 공용 헬퍼 A._s 하나만 '604 이전'(문자열 강제 없는 raw strip/slice) 버전으로 몽키패치해 "
     "같은 요청들이 실제로 다시 500이 됨을 확인한 뒤 원복(app.py 해시 불변도 확인). 첫 실행 48/48 통과. "
     "app.py의 라우트 5곳(api_defect_create·api_defect_update·api_partner_defect_resolve·"
     "api_partner_defect_dispute·api_partner_complete)을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round605_fixes.py", "스캔 605라운드 회귀 — round604가 인계한 이번 라운드 최우선 지시각도(무인증 "
     "공개 로그인 4곳)를 그대로 따라 api_login_otp()의 code·api_login()의 username·api_partner_login()·"
     "api_insurer_login()의 login_id를 직접 Read로 재확인(시작 전 wc -l app.py가 21952줄로 동시편집 없음 "
     "확인), 4곳 전부 round601~604와 같은 형제결함군(raw (d.get(...) or \"\").strip())임을 확정했다. password "
     "필드는 지시대로 안 건드림(DB.verify_pw가 이미 안전 — round604 확인 완료). 같은 grep을 app.py 전체로 "
     "넓히다 5번째 형제를 우연히 발견 — _sub_create_impl()(보험사·협력사 포털 하위계정 생성 공용 함수, "
     "/api/insurer/subaccounts·/api/partner/subaccounts 둘 다 호출)의 login_id도 같은 raw 패턴이라 원계정이 "
     "숫자 login_id를 보내면 500이었다(require_portal_owner 인증은 걸려 있으나 그 뒤에서 크래시) — 기계적으로 "
     "동일한 한 줄 결함이라 함께 고쳤다. app.py 전체에 같은 패턴이 5곳 더 있음을 확인했으나(api_admin_create "
     "username·api_unlock_login uname·api_otp_confirm code·api_insurer_credentials login_id 2곳) 전부 "
     "require_role/require_admin/admin_role 게이트 뒤라 round604가 이미 분류해 둔 어드민 콘솔 전용 더미(~85곳)에 "
     "속해 이번 라운드도 의도적으로 손대지 않고 606 인계에 남긴다. 고침 — 형제들이 이미 쓰는 _s(d.get(...), n)을 "
     "그대로 재사용: code = _s(body().get(\"code\"), 32), username/login_id(4곳)는 _s(d.get(...)).lower()[:60] "
     "(.lower()를 _s() 뒤로 빼 strip→lower→slice 원래 순서를 그대로 보존 — n을 먼저 주면 slice가 lower보다 "
     "먼저 실행돼 순서가 바뀌므로). 회귀테스트(test_scan_round605_fixes.py, 31개 검사) 신설 — [0]은 소스 확인(5곳 "
     "전부 옛 raw 패턴 소멸·_s() 전환), [1]~[2]는 실제 Flask+스크래치DB로 숫자 문자열 아이디의 관리자·보험사·"
     "협력사 계정과 TOTP 등록 관리자 1명을 만들어 각 필드를 JSON 정수로 보내도 500 대신 200(OTP는 실제 유효한 "
     "TOTP 코드로 끝까지 로그인 완료까지 확인)과 세션/DB에 문자열로 매칭·저장됨을 확인, [3]은 같은 계정에 원래 "
     "타입(문자열) 자격증명을 보내는 정상 경로가 그대로 200임을 확인(과잉교정 없음), [4]는 되돌림-증명 — 진짜 "
     "app.py 파일은 전혀 안 건드리고 공용 헬퍼 A._s 하나만 '605 이전'(문자열 강제 없는 raw strip) 버전으로 "
     "몽키패치해 같은 모양의 요청들이 실제로 다시 500이 됨을 확인한 뒤 원복(app.py 해시 불변도 확인). 첫 실행 "
     "31/31 통과. app.py의 함수 5곳(api_login_otp·api_login·api_partner_login·api_insurer_login·"
     "_sub_create_impl)을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round606_fixes.py", "스캔 606라운드 회귀 — round605가 인계한 우선순위② 10개 함수(11자리, "
     "api_partner_profile_update가 두 자리를 겸함)를 하나씩 직접 Read로 재확인(시작 전 wc -l app.py가 21973줄로 "
     "동시편집 없음 확인). 10/11 함수(11자리)에서 실결함 확정, api_insurer_case_create만 클린(idempotency_key가 "
     "이미 str(d.get(...) or \"\")로 먼저 문자열을 강제해 안전 — 형제 api_v1_case_create와 동일 관례, 회귀 없음). "
     "지시각도 밖에서 두 갈래 더 발견: ① round605가 login_id만 고치고 남겨 둔 같은 함수의 형제 필드 — "
     "_sub_create_impl()·_sub_update_impl()의 name(round605 주석이 이미 '지시범위 밖이라 남겨 둠'이라 명시); "
     "② api_partner_profile_update 자체를 [0] 소스검사 정규식으로 재스윕하다 스스로 잡은 3번째 자리 — 좌표검색 "
     "미사용 시 옛 좌표를 지우는 elif 분기의 address 비교식(1차 검토에서 '비교뿐이라 안전'이라 오판했다가 재점검 "
     "에서 자체 정정). 합쳐서 14곳 확정 — 전부 형제 헬퍼 _s(v, n=None)을 그대로 재사용(새 헬퍼 없음): "
     "api_partner_profile_update(루프 v·biz_no의 re.sub 인자·좌표초기화 elif의 address, 3곳)·"
     "api_insurer_profile_update(루프 v)·_sub_create_impl(name)·_sub_update_impl(name)·"
     "api_insurer_case_cancel(reason)·api_insurer_reject_bids(reason)·api_insurer_award(reason)·"
     "api_change_order_create(reason)·api_insurer_co_ack(note)·api_insurer_set_severity(severity)·"
     "api_insurer_est_ack(reason)·api_insurer_field_agreement_decision(reason). app.py 전체 재스윕 결과 같은 "
     "raw 패턴이 78곳 더 있음을 확인(대표: api_application_create 9·api_campaign_create 6·api_partner_license 5·"
     "api_case_edit 3·api_est_band_set 3·api_schedule_event_add 3 등, 39개 함수에 분산) — 전부 require_admin/"
     "require_role 뒤(어드민 콘솔 전용)라 round604가 분류해 둔 ③ 더미(~85곳)에 속해 의도적으로 손대지 않고 607 "
     "인계에 남긴다. 회귀테스트(test_scan_round606_fixes.py, 70개 검사) 신설 — [0]은 소스 확인(14곳 전부 옛 raw "
     "패턴 소멸·_s() 전환 + api_insurer_case_create의 기존 안전패턴 회귀 없음), [1]은 스크래치DB에 보험사·협력사 "
     "각 1곳과 낙찰용 사건 2벌(고침증명·되돌림증명 분리 — 같은 사건 재사용 시 첫 낙찰로 상태가 시공중이 되어 "
     "되돌림 재현이 reason 줄 대신 앞단 409에서 막히는 것을 실제로 확인하고 분리함), [2]는 14곳 전부에 JSON 정수 "
     "값을 보내도 500 대신 원래의 정상 응답(200/400/404)과 문자열화된 DB 저장값을 확인, [3]은 원래 타입(문자열) "
     "값의 정상 경로가 그대로임을 확인(과잉교정 없음), [4]는 되돌림-증명 — 진짜 app.py 파일은 전혀 안 건드리고 "
     "공용 헬퍼 A._s 하나만 '606 이전'(문자열 강제 없는 raw strip) 버전으로 몽키패치해 [2]의 14개 요청이 실제로 "
     "다시 500이 됨을 확인한 뒤 원복(app.py 해시 불변도 확인, 대표 3곳 정상 회복도 확인 — api_insurer_award는 "
     "reason 줄이 UPDATE 이전이라 크래시가 쓰기 전에 멈췄음을 재확정하며 200으로 복귀). 첫 실행 70/70 통과. "
     "app.py의 함수 12곳(api_partner_profile_update·api_insurer_profile_update·_sub_create_impl·"
     "_sub_update_impl·api_insurer_case_cancel·api_insurer_reject_bids·api_insurer_award·"
     "api_change_order_create·api_insurer_co_ack·api_insurer_set_severity·api_insurer_est_ack·"
     "api_insurer_field_agreement_decision)를 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round607_fixes.py", "스캔 607라운드 회귀 — round606이 인계한 어드민콘솔 전용 78곳·39개함수 "
     "배치 중 이름이 지목된 6개 함수(api_application_create·api_campaign_create·api_case_edit·"
     "api_est_band_set·api_schedule_event_add·api_partner_license)를 app.py 전체 재정규식스윕으로 직접 "
     "Read해 재확인(시작 전 wc -l app.py가 22009줄로 동시편집 없음 확인). 6개 전부 실결함 확정 — "
     "api_application_create 11곳(9개 필드: company·biz_no·phone·email·ceo·category·region·address·"
     "message)·api_campaign_create 6곳(title·subject·body·audience·filter_json.major/region)·"
     "api_case_edit 7곳(지시는 3곳이었으나 category 필드 하나가 순차 실행되는 3개 자리에서 각각 raw로 "
     "읽혀 실결함은 7곳 — 필수값 검사·victim_name/victim_phone 루프·address_changed 비교식·category/"
     "region/address/manager 루프·work_lots 동기화 _nc)·api_est_band_set 3곳(major·severity·src)·"
     "api_schedule_event_add 3곳(title·event_date·event_time)·api_partner_license 5곳(license_status·"
     "license_no 사전확인·biz_no·license_no 실제UPDATE 재읽기·license_trades). 지시각도 밖 신선한 각도 "
     "둘도 함께 고쳤다 — ① _campaign_recipients()가 _like_escape()(내부 (s or \"\").replace(...))로 "
     "major를 넘기고 region도 raw strip이던 자리(캠페인 생성이 호출하는 형제 헬퍼, _like_escape 다른 "
     "8개 호출부는 전수 점검 결과 이미 안전한 값만 사용해 클린), ② api_schedule_event_add의 memo가 "
     ".strip()도 없이 (v or \"\")[:500] 슬라이스뿐이던 자리(리스트는 슬라이스가 되지만 int/bool은 안 되고 "
     "sqlite3 바인딩도 list/dict를 못 받아 결국 500), ③ 같은 요청모양을 공유하는 형제 라우트 "
     "api_campaign_preview의 body(_fill_template 내부 .replace() 경유)·subject_preview(AD_PREFIX "
     "문자열결합 경유). 합쳐서 40곳 확정 — 전부 형제 헬퍼 _s(v, n=None)을 그대로 재사용(새 헬퍼 없음). "
     "★★ 과정 중 발견 — api_application_create의 phone/email을 처음엔 형제 biz(같은 함수, 검증 후 "
     "로컬변수 _biz를 INSERT에서 재사용 중)을 본떠 _phone/_email 재사용으로 고쳤더니, 전체배터리에서 "
     "그 부분이 아닌 **다른 4개 기존 테스트가 콜리전**을 냈다: test_scan_round61_fixes.py(campaign_"
     "recipients의 _like_escape(f['major']) 리터럴 소스매칭), test_scan_round63_fixes.py(application_"
     "create의 address strip 리터럴 소스매칭), test_scan_round135_fixes.py(_campaign_recipients를 exec "
     "격리로 떼어 테스트하는데 새 _s() 호출이 그 격리 네임스페이스에 없어 NameError), "
     "test_scan_round484_fixes.py(RE_PHONE/RE_EMAIL 검사 블록만 정확히 도려내 '검사를 없애면 옛 버그가 "
     "재현되는가'를 증명하는 되돌림-테스트인데, _phone/_email 재사용 때문에 그 블록을 도려내면 INSERT가 "
     "정의되지 않은 변수를 참조해 NameError/500 — 검사 제거가 아니라 이 라운드의 리팩터가 콜리전 원인), "
     "test_feature_license_survey.py(api_partner_license의 biz_no 캡처·'등록확인'시 license_no 요구, "
     "두 곳 모두 옛 raw 리터럴 소스매칭). "
     "앞의 셋(61·63·135)은 '옛 리터럴을 찾던 소스검사'라 리터럴만 갱신(검증 취지 그대로 유지)했지만, "
     "484는 이 라운드의 phone/email 리팩터 자체가 484의 되돌림-증명 전제(그 필드를 쓰는 코드가 RE_PHONE "
     "검사 블록 밖에는 없다)를 깼으므로, phone/email을 나머지 7개 필드와 같은 방식(각자 독립적으로 "
     "_s(d.get(...), N), round604 결론 '필드별 _s() 적용'과도 일치)으로 되돌려 484를 원래대로 통과시켰다 "
     "— INSERT 시점의 재읽기 자체는 d가 불변이라 크래시 관점에서 무해함(첫 읽기가 안전하면 재읽기도 "
     "항상 안전)을 확인한 뒤의 판단. round606이 인계한 78곳 중 이번엔 6개 지시함수(+그 호출 경로의 형제 "
     "2곳)만 다뤘고, 정밀 재스윕(request.args 지역변수 별칭까지 제외)한 결과 나머지는 58곳·38개 함수로 "
     "확인됐다(608 라운드에 함수별 정확한 줄번호 인계) — 78이라는 이전 추정치는 args 별칭을 못 걸러낸 "
     "과대추정이었다. 회귀테스트(test_scan_round607_fixes.py, 70개 검사) 신설 — [0]은 소스 확인(40곳 "
     "전부 옛 raw 패턴 소멸·_s() 전환), [1]은 스크래치DB에 관리자(최고관리자) 1명·사건 1건·캠페인 수신자 "
     "매칭용/면허조사용 협력사 각 1곳, [2]는 6개 함수+형제 2곳 전부에 JSON 정수 값을 보내도 500 대신 "
     "원래의 정상 응답(200/400)과 문자열화된 DB 저장값을 확인(캠페인은 수신자 1곳 실매칭까지), [3]은 원래 "
     "타입(문자열) 값의 정상 경로가 그대로임을 확인(과잉교정 없음), [4]는 되돌림-증명 — 진짜 app.py 파일은 "
     "전혀 안 건드리고 공용 헬퍼 A._s 하나만 '607 이전'(문자열 강제 없는 raw strip) 버전으로 몽키패치해 "
     "대표 7개 요청이 실제로 다시 500이 됨을 확인한 뒤 원복(app.py 해시 불변도 확인, 대표 2곳 정상 회복도 "
     "확인). 단독 실행 70/70 통과, 전체배터리는 위 5개 콜리전(모두 이번 라운드가 옛 raw 리터럴을 바꾼 "
     "자리를 정확히 그 문자열로 소스매칭하던 옛 테스트들 — 484만 리터럴이 아니라 재사용 리팩터 자체가 "
     "전제를 깬 구조적 콜리전)을 전부 해소한 뒤 491/491 통과(0 실패, 3회 전체배터리 재실행으로 확인). "
     "app.py의 함수 8곳(api_application_create·_campaign_recipients·api_campaign_preview·"
     "api_campaign_create·api_case_edit·api_est_band_set·api_schedule_event_add·api_partner_license)를 "
     "고쳤으므로 서버 재기동 필요."),
    ("test_scan_round608_fixes.py", "스캔 608라운드 회귀 — round607이 인계한 58곳·38개함수(정확한 목록은 "
     "세션종료로 소멸)를 app.py 전체 재정규식스윕으로 재발굴, 25곳(25개함수+공유헬퍼 valid_biz_no 1곳, "
     "api_settlement_undo는 아래 콜리전 조사 중 자체발견해 같은 패턴으로 즉시 추가)을 "
     "실결함으로 확정해 고쳤다. round607이 지목한 우선후보 3개는 위협모델부터 판단: "
     "api_partner_dashboard 6곳·_payout_account_gate의 DB row 3곳은 partners/change_orders TEXT "
     "컬럼 재읽기라 sqlite3 자체 실험(TEXT affinity는 저장 시점에 int/float/bool을 전부 TEXT로 "
     "강제하고 dict/list는 바인딩 자체가 막힌다)으로 클린 확정 — 수정 안 함. 대신 _payout_account_gate의 "
     "override_reason(함수 파라미터, 호출부 2곳 모두 body().get('no_account_reason') 원시값)과 "
     "api_co_close_full의 reason·insurer_instruction(d=body() 원시값)은 실결함이었다. 그 외 21곳 — "
     "api_memo_create(body)·valid_biz_no(공유헬퍼, re.sub 3번째 인자, 호출부 8곳 영향)·"
     "api_otp_confirm(code)·api_partner_account_set(bank_account, re.sub)·api_partner_create(biz_no, "
     "re.sub)·api_partner_update(biz_no re.sub·address·status_reason, 3곳)·api_insurer_update"
     "(status_reason)·api_co_withdraw/withdraw_offer(reason)·api_photo_reject(reason)·"
     "api_settlement_paid/paid_bulk(memo)·api_settlement_transfer/review(defect_override_reason)·"
     "api_settlement_void(reason)·api_outbox_test_send(phone)·api_outbox_handled(note)·"
     "api_boq_update(price_src·price_date, 삼항식이라 단순정규식엔 안 걸림 — price_date의 \"본문에 "
     "있음\" 분기는 or \"\" 폴백조차 없어 null만 보내도 크래시였던 더 심한 변종, 2곳)·"
     "api_case_to_dispatch/cancel_award/close_offline/undo_no_repair(reason)·api_case_award"
     "(insurer_instruction·reason, 2곳). 전부 형제 헬퍼 _s(v, n=None) 재사용 — 새 헬퍼 없음. "
     "클린 확정(수정 안 함, 근거 확인) — _insurer_ack_ok/api_co_decision의 co.get('insurer_ack')(DB "
     "row TEXT), api_partner_profile의 bank_account_masked(CRYPTO.mask_account가 항상 str 반환), "
     "api_defect_update의 cost_bearer(round604가 이미 화이트리스트 검증 후 도달만 가능하다고 확정), "
     "api_partner_defect_dispute(round604가 이미 _s()로 수정), _create_case/api_case_create의 "
     "est_price·api_auction_set_deadline의 deadline(str() 강제가 이미 있음), _partner_filter/"
     "_case_filter/_settle_filter/_activity_filter/_onboard_where(_rows)(파라미터명이 args여도 "
     "호출부 전수확인 결과 request.args만 전달됨), _victim_notice의 LD.INFO(정적 설정). 회귀테스트"
     "(test_scan_round608_fixes.py, 78개 검사) 신설 — [0]은 소스 확인(25곳 전부 옛 raw 패턴 소멸·"
     "_s() 전환), [1]은 스크래치DB에 관리자 1명·사건 1건(원경매+전체재경매 각각 입찰 1건)·협력사 "
     "2곳(계좌있음/계좌없음)·정산 4건(2건은 [2]에서 상태가 실제로 전이돼 소모되므로 [4] 되돌리기용 "
     "여분을 별도로 심음)·표준내역 1건, [2]는 각 라우트에 JSON 정수/명시적 null을 보내도 500이 아님을 "
     "확인(다수는 200 완주까지), [3]은 원래 타입(문자열) 정상 경로 회귀 없음, [4]는 공용 헬퍼 A._s만 "
     "608 이전 버전으로 몽키패치해 대표 9개 요청이 실제로 다시 500이 됨을 확인한 뒤 원복(app.py 해시 "
     "불변도 확인, 대표 3곳 정상 회복도 확인 — settlement_paid는 되돌리기 크래시가 나도 부분 UPDATE가 "
     "없음도 함께 확인). 단독 실행 78/78 통과. 전체배터리 1차 실행에서 콜리전 5건 발견(옛 리터럴을 "
     "그대로 소스매칭하던 회귀 — test_scan_round11/429/497/498/506_fixes.py, round607이 겪은 것과 "
     "같은 클래스) — 전부 검증 취지는 그대로 두고 리터럴만 갱신(497/498은 valid_biz_no 관련 별개 축 "
     "[^0-9]↔\\D 되돌림-증명에 _s() 래핑만 추가, 506은 함수 본문 통째 캡처 문자열 갱신)한 뒤 재실행해 "
     "492/492(신규 78개 포함 총 492) 통과 확인(콜리전 수정도 포함해 3회 전체배터리 재실행으로 확인). "
     "round609에 인계 — 재스윕으로 찾았으나 개별 확인을 못 한 나머지: api_admin_create(username·"
     "name)·api_admin_update(name)·api_me_update(name)·api_unlock_login(username)·"
     "api_create_application(address)·api_insurer_create(name)·api_insurer_credentials(login_id "
     "2곳)·api_insurer_webhook_set(webhook_url)·api_contact_update(v=d.get(f) 루프)·"
     "_attach_defect_photos(item.get('note'))·api_notice_create(body)·api_boq_create(price_src·"
     "price_date)·api_case_open_auction(est_basis)·api_field_agreement_open(pattern)·"
     "api_happy_call_add(feedback·method, .strip() 없는 슬라이스). _gate_alert의 res.get('reason')은 "
     "CP.record_gate()가 내부에서 항상 str 리터럴/f-string으로만 채우는 값이라(compliance.py 직접 "
     "확인) 외부 공격자 입력이 아니고 위협모델이 달라 낮은 우선순위. app.py의 함수 25곳 + 공유헬퍼 "
     "valid_biz_no를 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round609_fixes.py", "스캔 609라운드 회귀 — round608 인계 15곳(①, 개별 Read로 재확인)과 "
     "round608이 분리요청한 새 결함군(② RE_PHONE.match()/RE_EMAIL.match()/valid_website()가 비문자열 "
     "JSON에 TypeError, 컴파일된 정규식 .match()/.fullmatch()/.search() 전수스윕)을 처리했다. ① 15곳 중 "
     "14곳 실결함·1곳 클린(api_create_application의 address — FIELD_LIMITS에 이미 있고 "
     "clean_public_form()이 str(v) 강제라 수정 불필요). ② 스윕 결과 api_partner_create·"
     "api_partner_update(루프)·api_insurer_create·api_insurer_update(루프) 4개 함수에서 phone/email/"
     "website 검사 8곳이 raw d.get()/d[f]를 정규식에 직결해 실결함이었고, api_contact_update는 ①에서 "
     "v를 _s()로 감싸면 같은 줄의 RE_PHONE/RE_EMAIL도 동반 안전화(추가 수정 불필요). 자체발견 3건: "
     "①api_change_password(current/new, password_policy_error() 내부 re.search 3곳이 raw pw를 받음) "
     "②issue_partner_login(공유헬퍼 want — 유일 호출부 api_partner_credentials가 body().get('login_id') "
     "원시값을 그대로 넘김) ③api_defect_update(due_date, re.fullmatch 직결). ★3중 구조 발견 — "
     "api_boq_create의 price_src/price_date를 INSERT 튜플에서만 _s()로 고치고 실행검증했더니 여전히 "
     "500: _boq_history(conn, bid, {**d, ...}, ...)가 원본 raw d를 그대로 넘기고, db.py:boq_history() "
     "안의 (row.get('price_src') or '')[:200]이라는 **세 번째** raw 슬라이스가 있었다(호출부 3곳 중 "
     "이 함수만 raw d를 넘긴다). db.py는 app.py의 _s()를 가져올 수 없어(순환 임포트) 공유 래퍼 "
     "_boq_history() 안에서 한 번 더 강제해 호출부 3곳(api_boq_create·update·delete) 전체를 한 번에 "
     "닫았다(seed_boq.py 등 CLI 직접호출 2곳은 위협모델이 달라 범위 밖). 전부 형제 헬퍼 _s(v, n=None) "
     "재사용 — 새 헬퍼 없음. raw-strip 결함군(①)은 601~609 9개 라운드에 걸쳐 사실상 완결(누적 165곳+). "
     "회귀테스트(test_scan_round609_fixes.py, 95개 검사) 신설 — [0]은 소스 확인(_code_only()로 주석의 "
     "옛 패턴 인용 오탐 제거), [1]은 스크래치DB에 관리자 2명·협력사 3곳·보험사 3곳·사건 3건(경매용+완료"
     "×2), [2]는 각 라우트에 JSON 정수를 보내도 500이 아님을 확인(다수 200 완주), [3]은 원래 타입(문자열)"
     " 정상 경로 회귀 없음, [4]는 공용 헬퍼 A._s만 609 이전 버전으로 몽키패치해 대표 19개 요청이 실제로 "
     "다시 500이 됨을 확인한 뒤 원복(app.py 해시 불변·happy_calls 부분INSERT 없음·정상회복 확인). 단독 "
     "실행 95/95 통과. 동시편집 없음(시작 전 22062줄 일치). app.py의 함수 21곳 + 공유래퍼 _boq_history "
     "를 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round610_fixes.py", "스캔 610라운드 회귀 — 옵션A(새 결함각도). 지시문이 예시로 든 "
     "api_partner_update의 '본문에 키가 있으면 무조건 SET'(round561 지목)은 직접 Read로 재확인한 결과 "
     "round562가 이미 pending/diff 패턴으로 닫아 뒀다(지시문 예시가 낡음, 추가조치 불필요). 같은 "
     "'화면이 폼 전체를 통째로 재전송 → 무변경도 무조건 SET+감사로그' 결함군(round240/299/429/493/504/"
     "543/544/549/561/562/570이 이미 닫은 부류)을 아직 안 훑은 나머지 api_*_update들을 재점검해 "
     "api_boq_update(17037행)에서 미해결 실인스턴스 2개를 새로 찾았다. ① 형제와 동일 — 화면(admin.js "
     "boqSave)이 5칸(spec/unit/ref_price/price_src/price_date)을 매번 통째로 재전송해, 아무것도 안 "
     "바꾸고 저장만 눌러도 boq_price_history 개정이력·감사로그가 매번 새로 쌓였다(실측: 무변경 저장 2회 "
     "→ '50,000 → 50,000원' 이력·로그 각 2건). 이 이력은 api_boq_history 주석대로 '이 견적이 어느 "
     "단가로 계산됐나'를 되짚는 근거라 가짜 개정이 실제 변경 시점을 가린다. ② 이 라운드 자체발견(①보다 "
     "심각) — 참고단가 입력칸을 지우면 admin.js digits()가 빈 문자열을 보내는데, parse_money(...,  "
     "required=False)가 '미입력'과 '빈 문자열'을 구분 못 해 둘 다 (0, None)이 되고, 기존 "
     "'\"ref_price\" in d' 판정은 이를 '0원으로 명시적으로 바꾼다'로 오판했다 — 실측: 50,000원 항목이 "
     "가격칸만 지우고 저장한 한 번으로 에러도 확인창도 없이 조용히 0원이 됐다(200 OK). 이 표는 "
     "'입찰 비교의 기준'이자 자동견적 엔진(RE.SKU) 참고값이라 말없는 0원화가 입찰비교·자동견적을 "
     "왜곡할 수 있다. 수정은 api_boq_update 안에서만, 새 헬퍼 없이 형제 관례 재사용: "
     "_price_sent = '\"ref_price\" in d and _s(d.get(\"ref_price\")) != \"\"'로 빈 문자열을 '미입력'과 "
     "동일 취급(명시적 '0' 입력 경로는 그대로 허용)하고, vals 계산 직후 cur_row와 5개 필드 전체를 "
     "대조해 하나라도 실제로 달라야만 UPDATE·_boq_history·DB.log를 실행한다. 회귀테스트"
     "(test_scan_round610_fixes.py, 28개 검사) 신설 — [0]은 소스 확인(api_partner_update가 이미 "
     "고쳐졌음도 재확인), [1]은 스크래치DB에 관리자 1명·표준내역 2건(일반+자동견적엔진 연결), [2]는 "
     "①·②가 실제로 닫혔음을 실행으로 확인(무변경·빈칸 저장 모두 unchanged:true, 이력·로그 0건 — "
     "혼합변경에서는 spec만 정상 반영되고 가격은 보존), [3]은 회귀 없음(실제 가격변경 1건 정확 반영· "
     "명시적 '0' 허용·NEED_SRC·SKU_UNIT_MISMATCH·404 전부 그대로), [4]는 되돌리기 — 진짜 app.py는 "
     "안 건드리고 A.app.view_functions['api_boq_update']만 610 이전 동작을 재현하는 순수 함수(A.* 로 "
     "공유 헬퍼만 참조)로 임시 치환해 ①·② 둘 다 실제로 재현됨을 확인한 뒤 원복(app.py 해시 불변· "
     "원복 후 정상회복 확인). 단독 실행 28/28 통과. 동시편집 없음(시작 전 22147줄 일치, 재기동 직후 "
     "프로세스 시각도 app.py mtime과 일치). app.py의 함수 1곳(api_boq_update)만 고쳤으므로 서버 재기동 "
     "필요."),
    ("test_scan_round613_fixes.py", "스캔 613라운드 회귀 — 자동견적 엔진(repair_estimate.py)의 "
     "RE.estimate()가 inputs를 dict로 가정해, 클라이언트가 정수·실수·bool(True) 같은 '참인 non-dict' "
     "값을 보내면 _validate() 안 'k in inputs'가 TypeError로 죽던 결함. EstimateError(ValueError "
     "상속)가 아니라 이 모듈이 안 잡는 예외라, 두 호출부 중 가드가 없는 api_repair_estimate(app.py "
     "20567행, 'd.get(\"inputs\") or {}'뿐 — None/0/빈값만 막고 참인 non-dict는 통과)에서 그대로 새어 "
     "전역 핸들러(err_500)까지 뚫고 SERVER_ERROR(500)가 됐다. 다른 호출부 api_field_agreement_open은 "
     "자기 쪽에서 'isinstance(d.get(\"inputs\"), dict) else {}'로 이미 막고 있었으나 그건 그 호출부 "
     "하나만 지킬 뿐이었다. round601~609가 전역적으로 훑은 'raw .strip()류 AttributeError' 결함군과 "
     "실패 형태가 달라(k in inputs의 TypeError) 그 정규식스윕들이 못 잡았다. 실측(스크래치DB+실제 "
     "Flask 앱): POST /api/repair-estimate {'pattern':'guardrail_section','inputs':42}(3.14·true도 "
     "동일) → 수정 전 500 SERVER_ERROR. 고침 — 호출부 하나만 patch하는 대신 실제 합류점인 _validate() "
     "맨 앞에서 isinstance(inputs, dict)를 확인해 아니면 EstimateError로 거절(다른 호출부·미래 호출부 "
     "까지 한 곳에서 방어, 숫자범위·choice·NaN/Inf 등 기존 검증 로직은 안 건드림). 회귀테스트"
     "(test_scan_round613_fixes.py, 21개 검사) 신설 — [1]은 소스 확인, [2]는 스크래치DB에 관리자 1명, "
     "[3]은 RE.estimate() 직접호출로 정수·실수·bool·문자열·리스트 5종 모두 EstimateError로 거절됨을 "
     "확인, [4]는 같은 5종을 실제 라우트로 쏴 500이 아니라 400임을 확인, [5]는 회귀없음(정상 dict "
     "입력·계산결과 그대로, 빈 dict는 가드는 통과하고 필드별 required 검사에서 정상 거절), [6]은 "
     "되돌리기 — 진짜 repair_estimate.py 파일은 안 건드리고 RE.__dict__['_validate']만 가드 없는 "
     "613 이전 버전(exec로 재구성)으로 임시 치환해 TypeError(직접호출)·500(라우트) 둘 다 실제로 "
     "재현됨을 확인한 뒤 원복(파일 해시 불변·원복 후 400/EstimateError 재확인). 처음부터 이 안전패턴 "
     "(exec + 함수객체 임시치환, 디스크 미기록)으로 작성 — round411·610이 확립한 기법. 단독 실행 "
     "21/21 통과. repair_estimate.py 1곳만 고쳤고 app.py는 무변경이지만 repair_estimate가 app.py의 "
     "정적 임포트 대상이라 서버 재기동 필요."),
    ("test_scan_round614_fixes.py", "스캔 614라운드 회귀 — 도입문의 상태변경(api_lead_update, PATCH "
     "/api/leads/<id>)에 존재확인(404)도 status 화이트리스트도 없던 결함. 가장 가까운 형제 "
     "(api_application_update, 입점신청의 같은 PATCH류 상태변경 라우트)는 lid가 없으면 404를 "
     "돌려주는데 여기만 존재확인이 아예 없어, 없는 lid로 호출해도 UPDATE가 조용히 0행 적용된 채 "
     "{\"ok\":true}를 그대로 돌려줬다 — 이 저장소가 반복해서 잡아 온 '지웠다는데 안 지워지는' 부류의 "
     "거짓 성공. status 값도 이 앱의 다른 상태값들(SEVERITY_VALUES·PARTNER_STATUSES·"
     "INSURER_STATUSES)과 달리 화이트리스트 대조가 전혀 없어, 화면(admin.js leadDetail)이 실제로 "
     "보내는 값 3종(검토중·승인·반려) 밖의 임의 문자열이나 null이 그대로 저장될 수 있었다. 고침 — "
     "LEAD_STATUSES=('신규','검토중','승인','반려') 화이트리스트 신설(SEVERITY_VALUES와 동일한 모양) "
     "+ 함수 맨 앞에서 lid 존재를 한 번만 확인(상태변경·메모 두 분기 모두 보호), 새 메커니즘 없음. "
     "회귀테스트(test_scan_round614_fixes.py, 15개 검사) 신설 — [1]은 소스 확인, [2]는 스크래치DB에 "
     "관리자 1명·도입문의 1건, [3]은 실제 라우트로 없는 lid는 404·화면이 안 쓰는 임의 status는 400·"
     "정상값은 200으로 반영됨을 확인(회귀없음), [4]는 되돌리기 — 진짜 app.py 파일은 안 건드리고 "
     "A.app.view_functions['api_lead_update']만 614 이전 버전(exec로 재구성)으로 임시 치환해 없는 "
     "lid도 200 거짓성공을, 임의 status도 그대로 저장됨을 실제로 재현한 뒤 원복(파일 해시 불변·원복 "
     "후 404/400 재확인). 처음부터 이 안전패턴(exec + view_functions 딕셔너리 항목 임시치환, 디스크 "
     "미기록)으로 작성 — round414·610이 확립한 기법. 단독 실행 15/15 통과. app.py 1곳(api_lead_update) "
     "변경 + LEAD_STATUSES 상수 신설이라 서버 재기동 필요."),

    ("test_scan_round615_fixes.py", "스캔 615라운드 회귀 — 입점신청 상태변경(api_application_update, "
     "PATCH /api/applications/<id>)의 elif 분기(서류검토·반려 등 '승인' 아닌 상태변경)에 상태값 "
     "화이트리스트가 없던 결함, 1건. 형제 셋(LEAD_STATUSES round614·PARTNER_STATUSES round101·"
     "INSURER_STATUSES round136)은 전부 화이트리스트가 있는데 이 신청서 상태만 없었다 — round614가 "
     "고친 api_lead_update의 형제(같은 PATCH류 상태변경 라우트)를 훑다가 발견. '승인' 분기는 "
     "정확일치 비교라 우연히 안전했지만 elif 분기는 화면(admin.js appAct, 서류검토·승인·반려 버튼 "
     "3개만 보냄)과 무관하게 임의 문자열을 그대로 UPDATE에 태웠다 — 잘못 들어간 값은 이 표를 "
     "status IN ('신규','서류검토')로 훑는 대기 배지·드릴다운·통계 4곳(7357·7419·7584·17931행)에서 "
     "조용히 사라져 아무도 결정 안 내린 신청서가 영원히 방치될 수 있었다. 고침: APPLICATION_STATUSES="
     "('신규','서류검토','승인','반려') 신설(LEAD_STATUSES와 동일한 4값 관례) + new_status를 읽은 "
     "직후 한 번만 화이트리스트 검사(두 분기 모두 보호), 새 메커니즘 없음. 회귀테스트"
     "(test_scan_round615_fixes.py, 15개 검사) 신설 — [1]은 소스 확인, [2]는 스크래치DB에 관리자 "
     "1명, [3]은 실제 라우트로 임의 status는 400·정상값(서류검토)은 200으로 반영·없는 aid는 여전히 "
     "404(회귀없음), [4]는 되돌리기 — 진짜 app.py 파일은 안 건드리고 A.app.view_functions"
     "['api_application_update']만 615 이전 버전(exec로 재구성)으로 임시 치환해 임의 status가 그대로 "
     "저장됨을 실제로 재현한 뒤 원복(파일 해시 불변·원복 후 400 재확인). 처음부터 이 안전패턴"
     "(exec + view_functions 딕셔너리 항목 임시치환, 디스크 미기록)으로 작성 — round414·610·614가 "
     "확립한 기법. 단독 실행 15/15 통과. app.py 1곳(api_application_update) 변경 + "
     "APPLICATION_STATUSES 상수 신설이라 서버 재기동 필요."),
    ("test_scan_round616_fixes.py", "스캔 616라운드 회귀 — round609가 '사실상 완결'(601~609 누적 "
     "165곳+)이라 선언한 raw-strip 형제결함군의 잔여 3곳을 app.py 전체 재스윕(정규식 grep으로 "
     "d.get(...)나 d[...]가 falsy면 빈 문자열로 접히는 or 뒤 raw strip() 패턴 전수확인)으로 추가 "
     "발견해 고침. ① api_lead_update(insurer_leads.note, 7925행) ② api_application_update"
     "(partner_applications.note, 8115행 — 이 라운드가 애초에 받은 리드) — 둘 다 라운드118 주석이 "
     "서로를 형제로 인용하면서도 정작 118 자신이 둘 다 raw로 남겨 뒀다. ③ api_case_create의 "
     "insurer_name(11806행) — BEGIN IMMEDIATE로 쓰기 잠금을 쥔 뒤라 셋 중 가장 무겁다(다만 app.py "
     "429행 _tracked_get_db가 모든 DB.get_db() 커넥션을 g._conns에 등록해 두고 전역 예외핸들러· "
     "teardown_appcontext 둘 다 rollback하는 안전망이 이미 있어 먹통까지는 안 가고 500으로 끝남을 "
     "[4]에서 직접 재현·확인). 오탐 배제 재확인 2곳(수정 안 함) — api_create_application(address, "
     "6091행)은 d=clean 이후 읽어 clean_public_form()의 FIELD_LIMITS[address]=200이 이미 str(v) "
     "강제를 거쳐 항상 안전(round609와 동일 결론), api_defect_update(cost_bearer, 15684행)는 "
     "15628행 화이트리스트(not in 대조)가 비문자열을 포함한 모든 미허용값을 그 앞에서 걸러 항상 "
     "안전(라운드604 자신의 분석과 동일 결론). 전부 형제 헬퍼 _s(v, n=None)(1507행) 재사용, 새 "
     "헬퍼·새 로직 없음. 회귀테스트(test_scan_round616_fixes.py, 20개 검사) 신설 — [0]은 소스 확인"
     "(3곳 모두 _s()로 바뀌고 오탐 2곳은 그대로임을 함께 확인), [1]은 스크래치DB에 관리자 1명+도입"
     "문의 1건+입점신청 1건, [2]는 세 라우트에 JSON 정수를 보내도 500이 아님(note류는 200, insurer는 "
     "400 NO_INSURER)을 실제 Flask test_client로 확인, [3]은 문자열 값의 정상 동작이 안 바뀜(회귀 "
     "없음), [4]는 되돌리기 — 진짜 app.py 파일은 안 건드리고 세 곳이 공유하는 헬퍼 A._s만 616 이전"
     "(str 강제 없는 raw strip) 버전으로 몽키패치해 세 라우트가 실제로 다시 500이 됨을 재현한 뒤 "
     "원복(파일 해시 불변·원복 후 200 재확인), 되돌린 채로 다음 BEGIN IMMEDIATE가 잠기지 않음도 함께 "
     "확인(전역 안전망이 이 크래시 지점에서도 실제로 롤백함을 증명) — round609가 확립한 공유 헬퍼 "
     "몽키패치 기법을 처음부터 그대로 사용(디스크 미기록). 단독 실행 20/20 통과. app.py 3곳(모두 "
     "같은 헬퍼 _s() 재사용, 새 상수·새 로직 없음) 변경이라 서버 재기동 필요. 참고로 이 세션은 Part "
     "A로 test_scan_round482·507·515_fixes.py 세 파일의 되돌림-증명도 옛 on-disk write→subprocess"
     "→write 패턴에서 round488·414·610이 확립한 안전패턴(exec 독립사본/view_functions 딕셔너리 "
     "치환)으로 이관했다(파일명·설명은 그대로, 내부 구현만 교체 — 이 등록 항목은 그 세 파일이 아니라 "
     "이번에 신설한 616 자체 테스트에 대한 것)."),
    ("test_scan_round618_fixes.py", "스캔 618라운드 회귀 — partner_accounts.py(협력사 포털 계정 "
     "일괄발급 독립 CLI) make_login_id()가 유니코드 전각숫자를 걸러내지 못해 발급 아이디 끝자리에 "
     "전각 문자가 그대로 박히던 결함. 형제 app.py:_auto_login_id()(issue_partner_login()의 자동채번 "
     "경로가 쓰는 바로 그 함수, 8352행)는 이미 [^0-9]로 사업자번호에서 숫자만 뽑는데 이 CLI만 "
     "\\D(=\\d의 여집합)를 썼다 — round497이 valid_biz_no()에서 이미 밝힌 것과 같은 결함 클래스다 "
     "(파이썬의 \\d는 유니코드 전각숫자 １２３ 등도 숫자로 쳐서 \\D가 안 지움). partners.biz_no에 "
     "전각숫자가 섞여 있으면(round497 수정 이전에 등록됐거나, 이 CLI 자신은 valid_biz_no()를 아예 "
     "거치지 않고 pick()이 그냥 SELECT 해 온 값을 그대로 신뢰하므로) 그 문자가 살아남아 로그인 "
     "아이디 끝에 그대로 박힌다 — 이 함수 자신이 명시한 설계 목적('전화로 불러 주기 쉬워야 한다', "
     "혼동하기 쉬운 0/O·1/l/I를 이미 알파벳에서 뺀 것과 같은 이유)에 정면으로 어긋나고, "
     "issue_partner_login의 수동 아이디 지정 경로가 요구하는 [a-z0-9_-] 형식과도 어긋나 업체가 "
     "일괄발급받은 아이디를 타이핑조차 못 해 첫 로그인이 막힐 수 있다. 직접조사(하위위임 없음) — "
     "round618 지시가 제시한 각도 중 '파일 업로드/파일명 검증' 축을 app.py 전수조사(request.files "
     "4곳·load_workbook 1곳)하다 전부 이미 촘촘함을 확인한 뒤, '전에 열어본 적 없는 코드'로 각도를 "
     "돌려 app.py 바깥의 독립 CLI 3종(manage.py·partner_accounts.py·ingest_partners.py)을 훑다가 "
     "app.py:_auto_login_id()와 문자 그대로 같은 목적의 자매함수를 partner_accounts.py에서 찾아 "
     "정규식 리터럴을 직접 대조해 발견. 고침: [^0-9]로 교체(round497과 동일한 한 글자 문자클래스 "
     "수정, 새 헬퍼 없음). 회귀테스트(test_scan_round618_fixes.py, 11개 검사) 신설 — [1] 소스: 새 "
     "정규식이 함수 본문 안에 유일하게 있고 형제 app.py 쪽은 이번 라운드가 안 건드렸음을 확인. [2] "
     "실행 — 이 파일 자신의 demo() self-check가 이미 쓰는 FakeConn으로 실제 make_login_id()를 직접 "
     "호출, ASCII 10자리+잉여 전각숫자 1개를 주면 전각이 정규화로 걸러져 'p567890'(형제·demo()와 "
     "동일 규칙)이 나오고 순수 ASCII 입력의 회귀없음도 확인. [3] 되돌림-증명 — 진짜 "
     "partner_accounts.py 파일은 전혀 안 건드리고 AST로 뽑은 되돌린 함수 소스를 dict(vars(PA)) "
     "독립 사본 네임스페이스에 exec해서만 호출 — 옛 코드는 정확히 예상한 모양(전각숫자가 아이디 "
     "마지막 글자로 그대로 박힌 'p67890１')으로 재현됨을 확인, 파일 불변도 재확인 — 단독 실행 "
     "11/11 통과. partner_accounts.py는 app.py가 import하는 모듈이 아닌 독립 CLI라 서버 재기동· "
     "BUILD_HASH 로테이션 불필요(라운드475·482·495와 같은 독립 CLI류 예외). Part A로 "
     "test_scan_round495·496·499_fixes.py 세 파일의 되돌림-증명도 옛 on-disk write→subprocess"
     "→write 패턴에서 round488·414·610·614가 확립한 안전패턴(exec 독립사본 네임스페이스/"
     "view_functions 딕셔너리 치환)으로 이관했다(파일명·설명은 그대로, 내부 구현만 교체 — 각 "
     "파일 자신의 등록 항목에 [618라운드] 각주로 남김)."),
    ("test_scan_round620_fixes.py", "스캔 620라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 "
     "commit/rollback 누락 점검 CLI, round124·291·574가 이미 여러 번 자기 사각지대를 고친 그 도구)가 "
     "지금까지 return 문만 보고 있었고 반복문 안에서 continue/break 로 그 회차를 빠져나가는 경로는 "
     "한 번도 검사 대상이 아니었던 결함(직접조사, 하위위임 없음). 조사 각도 — app.py 요청 경로가 "
     "포화 상태라 이 저장소 스스로 만든 점검 도구(check_*.py) 자신의 소스가 자기 docstring 이 약속한 "
     "범위를 실제로 구현했는지 되짚었다. main() 은 ast.walk(fn) 에서 ast.Return 노드만 걸러 검사하는데, "
     "이 도구가 실제로 보는 함수 중 sweep_dispatches·sweep_webhook_retries·sweep_send_notifications· "
     "sweep_auctions 넷은 전부 '반복문 한 회차마다 BEGIN IMMEDIATE 를 열고 그 회차 안에서 "
     "commit/rollback 한다'는 패턴이고 조기 이탈은 return 이 아니라 continue(실측 dispatch.py:901·931, "
     "app.py:6962·6975·6979 등)로 이뤄진다 — round291이 'conn' 하나만 보다가 c2 등도 보게 넓힌 것과 "
     "같은 성격의, 이름이 아니라 노드 종류 축의 사각지대다. 합성 함수(반복문 안 BEGIN IMMEDIATE 뒤 "
     "commit/rollback 없이 continue)로 실제 재현 — 고치기 전 로직은 continue 가 ast.Return 이 아니므로 "
     "검사 후보에도 못 들어가 '클린(0건)'을 오보고했다. 실제 4개 함수 전수 재확인 결과 지금까지 이 "
     "사각지대가 실제 운영 결함을 감춘 적은 없었다(전부 continue/break 앞에 이미 commit()/rollback() "
     "이 있다) — round574의 seed_boq.py 확장과 같은 '지금 클린한 것은 코드가 우연히 안전해서일 뿐, "
     "검사 자체가 이 경로를 보고 있지 않았다'는 유형. 고침 — check_tx_paths.py 에 _own_loop_exits(loop) "
     "신설: 어떤 반복문의 몸통에 직접 속한 continue/break 만 뽑는다(중첩 반복문·중첩 함수 안의 것은 "
     "그쪽 소관이라 안 내려간다 — return 과 달리 continue/break 는 자신을 감싼 가장 가까운 반복문에만 "
     "영향을 주므로 그 반복문 자체가 BEGIN IMMEDIATE 를 담고 있을 때만 검사대상으로 삼아 무관한 "
     "계산용 중첩 루프의 continue 까지 잡는 오탐을 피한다). main() 은 이제 exit_nodes(return + 이런 "
     "반복문의 own-exit)에 같은 commit/rollback/finally 텍스트창 검사를 적용한다. "
     "safe_lock_failure_returns()·safe_finally_protected_returns() 도 (Return,Continue,Break) 3종을 "
     "함께 보도록 넓혔다. 실제 저장소 재확인 — 고친 뒤에도 4개 파일·109개 함수 전부 여전히 클린(위반 "
     "0건, 오탐 없음). 회귀테스트(test_scan_round620_fixes.py, 14개 검사) 신설 — [1] 소스: "
     "_own_loop_exits 신설과 main() 의 exit_nodes 배선이 정확히 한 번씩만 있음을 확인. [2] 되돌림-증명 "
     "— main() 함수 본문만 AST로 되돌려(옛 사각지대 텍스트) dict(vars(CTP)) 독립 사본 네임스페이스에 "
     "exec(check_tx_paths.py 파일도 실제 CTP 모듈도 안 건드림), 합성 결함 파일 하나짜리 스크래치 "
     "디렉터리에 겨눠 옛 로직이 실제로 클린(0건, 사각지대 재현)을 보고함을 확인. [3] 지금(고쳐진) 실제 "
     "CTP.main() 은 같은 합성 파일에서 위반 1건(함수명 포함)으로 정확히 잡고, continue 앞에 rollback() "
     "이 있는 정상 합성 파일은 과잉탐지 없이 통과함을 확인(HERE·TARGET_FILES 는 스크래치 값으로 임시 "
     "교체 후 되돌림). [4] 실제 check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소 전체가 109개 "
     "함수·위반 0건으로 끝남을 재확인 — 단독 실행 14/14 통과. check_tx_paths.py 는 app.py 가 import 하지 "
     "않는 독립 진단 CLI 라 서버 재기동·BUILD_HASH 로테이션 불필요."),
    ("test_scan_round621_fixes.py", "스캔 621라운드 회귀 — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 "
     "commit/rollback 누락 점검 CLI, round124·291·574·620이 이미 여러 번 자기 사각지대를 고친 그 도구)의 "
     "main() 이 '잠금~반환 구간에 commit/rollback 이 있었는가' 를 그 구간의 원문 텍스트에서 "
     "'conn.commit()'/'conn.rollback()'/'finally' 라는 글자가 있는지만으로 판정하던 결함(직접조사, "
     "하위위임 없음). 조사 각도 — 레거시 온디스크 되돌림-복원 마이그레이션을 계속하며 이 세션 자신이 "
     "쓰는 되돌림-증명 코드의 문체('옛 코드는 conn.rollback() 을 안 불렀다' 류 설명 주석)가 이 저장소 "
     "전역에 매우 흔함을 재확인하다가, check_tx_paths.py 의 핵심 판정부가 AST 가 아니라 "
     "window = '\\n'.join(lines[head:r.lineno]) 로 만든 원문 텍스트 조각에 부분문자열 검사를 한다는 것을 "
     "발견 — 그 글자가 주석 안에 있어도 구분하지 못한다. synthetic 함수로 직접 재현(실행 기반) — BEGIN "
     "IMMEDIATE 뒤 이른 return 바로 앞줄에 '실패해도 상위 호출자가 conn.rollback() 을 대신 처리한다' 는 "
     "설명 주석만 있고 실제 rollback() 호출은 전혀 없어도, 옛 로직은 그 return 을 안전으로 오판해 "
     "클린(0건)을 보고했다 — 'finally' 글자 검사도 같은 결함('옛 버전은 finally 블록에서 정리했다' 류 "
     "주석만 있어도 진짜 try/finally 구조 없이 안전 처리됨). 실제 저장소(app.py·dispatch.py·manage.py· "
     "seed_boq.py, 109개 함수) 재확인 — 고치기 전/후 모두 위반 0건(클린, 오탐 없음) — round124·574·620과 "
     "같은 '점검 도구 자신의 사각지대' 유형으로, 지금까지 이 틈이 실제 결함을 감춘 적은 없었지만 다음에 "
     "추가되는 설명 주석 한 줄이 조용히 이 방어를 무력화할 수 있는 상태였다. 고침 — "
     "_is_commit_or_rollback_call()·_commit_rollback_linenos()·_finally_protecting_ends() 세 헬퍼를 "
     "신설: 원문 텍스트가 아니라 진짜 AST Call 노드(<conn>.commit()/<conn>.rollback())와 진짜 try/finally "
     "구조(finally 안에 실제 commit/rollback 호출이 있는 경우만)만 본다. 중첩 헬퍼 함수 안의 호출은(그 "
     "함수가 지금 당장 불렸다는 보장이 없으므로) main() 이 이미 exit_nodes 에 쓰는 것과 같은 inner 집합으로 "
     "제외해, 새 판정 자신이 '중첩 함수 속 커밋도 바깥을 지켜준다'는 새 오판을 내지 않게 했다. "
     "회귀테스트(test_scan_round621_fixes.py, 16개 검사) 신설 — [1] 소스: 세 헬퍼 신설과 main() 판정부의 "
     "새 배선이 정확히 한 번씩만 있음을 확인. [2] 되돌림-증명 — main() 판정부만 옛(원문 텍스트 부분문자열 "
     "검사) 텍스트로 되돌려 dict(vars(CTP)) 독립 사본 네임스페이스에 exec(check_tx_paths.py 파일도 실제 "
     "CTP 모듈도 안 건드림), '설명 주석만 있고 진짜 commit/rollback 은 없는' 합성 결함 파일 하나짜리 "
     "스크래치 디렉터리에 겨눠 옛 로직이 실제로 클린(0건, 사각지대 재현)을 보고함을 확인. [3] 지금(고쳐진) "
     "실제 CTP.main() 은 같은 합성 파일에서 위반 1건(함수명 포함)으로 정확히 잡고, 같은 성격이지만 진짜 "
     "rollback() 호출이 있는 정상 합성 파일은 과잉탐지 없이 통과함을 확인(HERE·TARGET_FILES 는 스크래치 "
     "값으로 임시 교체 후 되돌림). [4] 실제 check_tx_paths.py 를 서브프로세스로 그대로 실행해 저장소 "
     "전체가 109개 함수·위반 0건으로 끝남을 재확인 — 단독 실행 16/16 통과. check_tx_paths.py 는 app.py 가 "
     "import 하지 않는 독립 진단 CLI 라 서버 재기동·BUILD_HASH 로테이션 불필요."),
    ("test_scan_round622_fixes.py",
     "스캔 622라운드 회귀 — dispatch.py _region_key()(자동 출동 후보선정 candidates() 가 지역 매칭에 "
     "쓰는 열쇠 추출 함수)가 '특례시'(2022년부터 수원·고양·용인·창원 4개 시가 쓰는 공식 행정 명칭, 예: "
     "'용인특례시')를 도시명+접미어 '시'로 오판해 도시명을 '용인특례'처럼 3글자나 통째로 뭉개던 결함. "
     "직접조사(하위위임 없음) — Part A(레거시 온디스크 되돌림-복원 마이그레이션)를 계속하며 round490·"
     "491·493·437·441의 되돌림-증명 템플릿을 옮기던 중, geo.py resolve()(round316)가 이미 이 표기를 "
     "src.replace('특례시','시')로 정규화해 두고 실측 근거로 '운영DB 협력사 #211 하우건설(주)의 실주소가 "
     "정확히 용인특례시 표기'라고 남긴 것을 다시 읽다가, dispatch.py가 지역 문자열을 각자 재구현하는 "
     "구조(round511·512·516이 이미 지적한 패턴)라는 점에서 이 정규화가 dispatch.py _region_key()에도 "
     "물려받아졌는지 grep으로 직접 대조 — '특례시' 문자열이 이 저장소 전체에서 geo.py 단 한 곳에만 있고 "
     "dispatch.py에는 전혀 없음을 확인했다. 실행으로 직접 재현 — _region_key('경기도 용인특례시 기흥구','')"
     "=='용인특례'(정상값 '용인'), 수원·고양·창원 3곳도 동일 재현. candidates()는 이 rkey를 그대로 LIKE "
     "패턴('%용인특례%')에 써서, '용인특례시'로 등록된 사건은 '용인시'로만 표기된(가장 흔한 정상표기) 실제 "
     "같은 지역 협력사와 전혀 매칭되지 않는다 — round511의 '대구'(우연한 접미어 충돌)와는 원인이 다르지만 "
     "(이번엔 신설 행정명칭이 접미어를 셋이나 더 얹음) 자동 출동 후보의 '같은 지역' 우선순위가 조용히 "
     "무력화되는 같은 증상을 낸다. 고침 — geo.py가 round316에서 이미 검증해 둔 것과 정확히 같은 정규화 "
     "(src.replace('특례시','시'))를 시/도 접두어 제거 단계 바로 앞에 추가했다 — 새 헬퍼·새 상수 없이 "
     "round511·512와 같은 ponytail 원칙(이미 있는 교훈을 형제 파일로 그대로 옮긴다). 회귀테스트"
     "(test_scan_round622_fixes.py, 33개 검사) 신설 — [1] 소스: 새 치환이 _region_key() 본문에 정확히 "
     "한 번, round511·547의 기존 처리는 그대로 남아있음(회귀 없음) 확인. [2] 실행 — 특례시 4개 도시"
     "(구 있음/단독) 직접 호출 + round511·547 UNIT_CASES 전부 재확인(회귀 없음). [3] 실행 — 실제 "
     "sqlite3(:memory:)+dispatch.candidates()(round130·511·547과 같은 격리 기법)로 '경기도 용인특례시 "
     "기흥구' 사건에 '용인시 기흥구'(정상표기, 진짜 같은 지역) 협력사와 '안양시 동안구'(무관지역, 가짜매칭 "
     "유발) 협력사를 함께 넣어 새 코드가 전자만 '같은 지역'으로 정확히 잡음을 확인. [4] 되돌림-증명 — "
     "_region_key()를 이 라운드 이전(round547 시점, 특례시 정규화 없음) 구현으로 런타임에 되돌려(순수 "
     "함수라 파일 미수정, candidates()는 모듈 전역 이름으로 호출하므로 교체가 그대로 반영됨) 같은 시나리오를 "
     "다시 돌리면 진짜 같은 지역 협력사('용인시 기흥구')가 '같은 지역'에서 실제로 빠짐을 재현 후 원상복구 "
     "확인 — 첫 실행 33/33 통과. dispatch.py는 app.py가 import하는 모듈이라 서버 재기동이 필요하나, 이 "
     "함수는 app.py 소속이 아니라 BUILD_HASH(app.py+static+templates 해시)에는 안 잡힌다(round511과 같은 "
     "한계)."),
    ("test_scan_round623_fixes.py",
     "스캔 623라운드 회귀 — 마케팅 캠페인 대상선정(_campaign_recipients, app.py:10076-)의 major(업종) "
     "검색이 공용 헬퍼 _kw_like_clause()(app.py:1688-, name/region/major 조합 검색 7곳이 이미 씀)를 "
     "안 쓰고 손으로 LIKE 절을 다시 짜, 그 헬퍼가 이미 막아 둔 가운뎃점 표기 사각지대(round499·"
     "_kw_like_clause 자기 docstring이 증언 — 정부 공식 업종 표기 'ㆍ' U+318D 를 쓰는 실제 협력사 10곳, "
     "id 305~314)를 이 화면에서만 다시 겪던 결함을 직접 확인 — 코드 자신의 주석(app.py:10099-10101, "
     "'이 파일의 다른 LIKE 검색은 전부 이 이스케이프를 거친다 — 여기만 예외였다')이 이 사각지대를 "
     "이미 알고 있었지만 부분적으로만(이스케이프만, round607) 고쳐져 있었다. 영향 — 운영자가 이 10곳을 "
     "캠페인 대상으로 좁혀 찾으려 하면(예: major='금속·창호') 조용히 0곳이 나와 있는 대상을 없는 것으로 "
     "오판하고 캠페인에서 빠뜨리게 된다. 고침 — round607의 _s() 방어(숫자 major 를 보내도 500 대신 "
     "안전 처리)는 그대로 둔 채, 손으로 짠 LIKE 절을 같은 컬럼 조합에 이미 쓰이는 공용 헬퍼 "
     "_kw_like_clause(_s(f.get('major')), ['major']) 호출로 교체 — 새 로직 없이 기존 헬퍼 재사용, "
     "트레이드오프 없는 '그냥 고치면 되는 것'. 회귀테스트(test_scan_round623_fixes.py, 12개 검사)는 "
     "실제 스크래치 DB로 공식표기('ㆍ') 협력사를 흔한 가운뎃점('·')으로 검색해 찾아짐(고치기 전엔 0건)과 "
     "일반 검색·숫자 major 방어(round607)의 회귀 없음을 실측, ast로 함수 본문을 뽑아 옛 LIKE 절로 치환한 "
     "독립 사본을 exec해(디스크 미기록·서브프로세스 미사용, round491/499 계열 안전기법) 옛 코드가 실제로 "
     "0건을 반환함을 인과관계로 직접증명 — 처음부터 이 세션이 이관 중인 안전기법으로 작성(온디스크 "
     "되돌리기 방식을 새로 만들지 않음). 첫 실행 12/12 통과 — 단, 이 배터리 자신이 병행 실행되는 동안 "
     "다른(아직 이관 안 된) 라운드가 app.py를 일시적으로 온디스크에 되돌려 쓰는 순간과 겹치면 이 테스트의 "
     "'app.py 불변' 방어확인이 일시적으로 거짓 실패할 수 있음을 실측(재실행 시 12/12로 통과, 이 테스트 "
     "자신의 결함이 아니라 동시 실행 중인 다른 온디스크 되돌리기 테스트와의 경합 — round623 마이그레이션 "
     "동기 자체를 실측으로 재확인한 셈). app.py 변경이라 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 "
     "말고 재기동 후 실측 확인)."),
    ("test_scan_round624_fixes.py",
     "스캔 624라운드 회귀 — 사건 생성(_create_case, app.py:4301-, 보험사 포털·v1 API 공용)이 "
     "데모 발주처(insurers.is_demo=1)가 만든 사건에 cases.is_demo 표식을 안 붙이던 결함. 직접조사 "
     "발견(하위위임 없음, 레거시 온디스크 되돌리기 이관 작업 중 '완결됐다는 주장 재검증' 각도로 "
     "찾음). require_insurer/require_api_key 둘 다 is_demo 를 안 보므로 데모 발주처도 정상적으로 "
     "포털·API 로 사건을 만들 수 있는데, 고치기 전 _create_case()의 INSERT INTO cases(...) 는 "
     "is_demo 컬럼 자체가 목록에 없어 스키마 기본값(db.py, INTEGER DEFAULT 0)이 항상 그대로 박혔다 "
     "— db.py 자신의 주석이 증언하는 화면·집계 23여 곳과 _backfill_child_is_demo() 캐스케이드 "
     "(db.py:1676-1734, cases.is_demo=1 만을 진원지로 삼음)가 전부 이 하나의 컬럼으로 데모를 거르므로, "
     "그 발주처의 사건·입찰·출동·통지·정산이 실적처럼 새어 나갈 수 있었다. 이 세션이 같은 문제의 "
     "세 증상을 이미 확인했다 — round528(deliver_webhook()/api_insurer_webhook_test() 에 "
     "'발주처 자신의 is_demo 도 본다'는 검사를 따로 추가, 그 주석이 '지금 이 운영DB의 데모 발주처 "
     "6곳'이라 현재형으로 실측까지 남김), manage.py의 DEMO_CASE_SQL(insurer_id IN 데모발주처를 "
     "OR로 더함, 이유: 'API로 만든 사건에는 표식이 안 붙기 때문'), test_scan_round187/188/209 "
     "(표식 없는 '유령 사건'을 원시 SQL로 직접 만들어 청소도구가 그래도 자식표를 찾는지만 검증) — "
     "전부 증상(웹훅 유출·유령 자식표)만 개별 패치했을 뿐 뿌리(사건 생성 자체)는 한 번도 안 "
     "고쳤었다. round187/188/209 는 _create_case()를 거치지 않는 원시 INSERT라 이번 수정과 안 "
     "겹치고, go-live 청소는 여전히 DEMO_CASE_SQL의 두 경로 모두로 안전망이 남는다. 고침 — "
     "_create_case() 안에서 insurers.is_demo 를 한 번 더 읽어(iid 는 이미 파라미터) 그 값을 그대로 "
     "cases.is_demo 에 심는다 — 새 헬퍼·새 컬럼·새 정책 없음, round528 의 원칙을 사건 생성 시점으로 "
     "옮겼을 뿐이라 이후 23여 곳은 전부 자동으로 따라온다. 회귀테스트(test_scan_round624_fixes.py, "
     "14개 검사) 신설 — 실보험사·데모보험사 각각 실제 Flask 포털 라우트(/api/insurer/cases, "
     "no_photo=True로 경매개설 생략)로 사건을 등록해 실보험사는 is_demo=0(회귀없음), 데모보험사는 "
     "is_demo=1(고치기 전엔 0)임을 실측. 되돌림-증명 — _create_case()는 api_insurer_case_create()·"
     "api_v1_case_create() 가 맨이름으로 부르는 평범한 모듈함수라(기법3, round416/422/492 계열 "
     "안전기법으로 처음부터 작성 — 온디스크 되돌리기 신규작성 없음) 되돌린 본문을 같은 이름으로 "
     "A.__dict__에 직접 exec해 옛 코드가 데모 발주처의 사건도 is_demo=0으로 새는 '유령 사건'을 "
     "실제로 재현함을 확인 후 원래 함수객체로 복원 — 첫 실행 14/14 통과. app.py 변경이라 재기동 "
     "필요, BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),
    ("test_scan_round625_fixes.py",
     "스캔 625라운드 회귀 — 관리자수동 사건등록(api_case_create, POST /api/cases)이 데모 발주처 "
     "(insurers.is_demo=1)가 만든 사건에 cases.is_demo 표식을 안 붙이던 결함. 직접조사 발견(하위위임 "
     "없음) — round624이 고친 형제 경로(_create_case, 보험사 포털·v1 API 공용)와 정확히 같은 결함 "
     "클래스가 사건을 만드는 두 번째 문에 그대로 남아 있었다. 증거 — app.py 전체에 'INSERT INTO "
     "cases(' 가 정확히 두 곳뿐인데 round624은 grep 없이 하나만 보고 그것만 고쳤다. admin.js의 "
     "발주처 드롭다운(createCase, 1779행 부근)은 is_demo 필터가 전혀 없이 전체 발주처를 보여주므로 "
     "관리자가 화면 그대로(정상 절차로) 데모 발주처를 골라도 아무 경고 없이 등록된다 — round594 "
     "주석도 이 라우트가 require_admin 뿐이라 콘솔 화면 밖(직접 API 호출)에서도 자유롭게 도달 "
     "가능함을 스스로 문서화해 두고 있었다. 고치기 전 이 경로의 INSERT는 is_demo 컬럼 자체가 목록에 "
     "없어 스키마 기본값(INTEGER DEFAULT 0)이 항상 그대로 박혔다 — round624이 옮긴 "
     "_backfill_child_is_demo() 캐스케이드와 화면·집계 23여 곳은 전부 cases.is_demo 하나만 보고 "
     "데모를 거르므로, 관리자수동으로 등록된 데모 사건도 이 뿌리에서부터 실적처럼 새어 나갈 수 "
     "있었다. 고침 — _create_case()(round624)와 정확히 같은 처방: insurer 조회(두 갈래 — insurer_id "
     "직접조회·NFKC 이름매칭) 시 is_demo 도 함께 읽어 cases.is_demo 에 그대로 심는다. 새 헬퍼·새 "
     "컬럼·새 정책 없음. 회귀테스트(test_scan_round625_fixes.py, 18개 검사) 신설 — 실보험사·데모보험사 "
     "각각 실제 Flask 관리자 라우트(POST /api/cases, no_photo=True로 경매개설 생략)로 사건을 등록해 "
     "실보험사는 is_demo=0(회귀없음), 데모보험사는 is_demo=1(고치기 전엔 0)임을 실측. 되돌림-증명 — "
     "api_case_create()는 _create_case()와 달리 라우트 자신이라(기법1, round504/509/477 계열 안전 "
     "기법과 동일 — 온디스크 되돌리기 신규작성 없음) view_functions 딕셔너리를 되돌린 함수객체로 "
     "스왑해 옛 코드가 데모 발주처의 사건도 is_demo=0으로 새는 '유령 사건'을 실제로 재현함을 확인 후 "
     "원래 함수객체로 복원 — 첫 실행 18/18 통과. app.py 변경이라 재기동 필요, BUILD_HASH 로테이션 "
     "예상(예측 말고 재기동 후 실측 확인)."),

    ("test_scan_round626_fixes.py",
     "스캔 626라운드 회귀 — GET /api/insurers 기본모드(사건 등록·월 정산 명세서 드롭다운용, ?all=1 아님)가 is_demo를 안 담아 "
     "관리자가 데모 발주처를 구분할 방법이 전혀 없던 결함, 2건(백엔드 1 + 프런트 2자리). 직접조사(하위위임 없음) — round624/625가 세운 "
     "cases.is_demo는 발주처 기준을 정확히 반영해야 한다는 불변식이 관련 경로 전체에 지켜지는지 확인하다가, round625 자신의 되돌림-증명 "
     "근거(admin.js의 발주처 드롭다운(createCase)은 is_demo 필터가 전혀 없다는 사실)를 실제로 파고들어 발견 — round625는 이 사실을 "
     "DB 저장값 일관성(cases.is_demo)의 근거로만 쓰고, 화면에 표시가 빠졌다는 사실 자체는 고치지 않고 남겨 뒀다. 근거(전부 이 세션이 "
     "grep+Read로 직접 확인) — api_insurers_list()의 기본모드 SELECT(자기 docstring이 사건 등록 드롭다운용이라고 스스로 "
     "밝힘)는 is_demo가 아예 없고, all=1 모드(발주처 관리 화면 전용, 최고관리자만)는 이미 담아 admin.js 발주처 목록(2659행 부근)이 회색 "
     "데모 표까지 붙이는데 정작 이 기본모드를 쓰는 두 화면(createCase 발주처 선택 1779행 부근·월 정산 명세서 발주처 선택 5168행 부근 — GET "
     "호출부 전수 대조로 이 둘뿐임을 확정, 2824행은 POST라 무관)은 그 표를 못 보여줬다. 운영 DB(읽기전용 조회) 실측 — 활성 발주처 7곳 중 6곳이 "
     "is_demo=1(DB손보·KB손보·메리츠화재 등 실제 보험사명을 그대로 쓴 데모 데이터)이라 이 드롭다운만 보면 관리자가 어느 게 실제 계약처인지 전혀 "
     "구분할 수 없다 — 이론적 위험이 아니라 지금 이 순간의 실제 상태. round624/625가 이미 cases.is_demo 자체는 발주처 기준으로 정확히 "
     "심도록 고쳐 통계·정산 집계가 새는 위험은 없으므로, 이 결함은 데이터 오염이 아니라 사람이 고르는 순간 아무 경고가 없다는 절차적 위험이다. 고침: 새 "
     "컬럼·새 정책·새 API 없음 — (a) 백엔드: 기본모드 SELECT에 is_demo 컬럼 추가(all=1 모드와 같은 컬럼명) (b) 프런트: 두 "
     "option 렌더에 발주처 이름 뒤 대괄호 데모 표기를 is_demo가 참일 때만 추가(옵션 태그는 HTML을 못 담으므로 목록화면의 pill 대신 대괄호 "
     "평문 표기). 회귀테스트(test_scan_round626_fixes.py+워커, 22개 검사) 신설 — 실제 Flask 서브프로세스로 데모 발주처 1곳·실제 "
     "발주처 1곳을 심고 GET /api/insurers(기본모드)를 호출해 응답 JSON에 is_demo가 정확한 값으로 담김을 확인, Node vm으로 "
     "admin.js의 두 옵션 렌더 표현식을 그대로 실행해 데모 발주처에만 대괄호 데모 표기가 실제로 붙음을 확인. 되돌림-증명 — 백엔드는 "
     "api_insurers_list()가 독립된 단일 Flask 라우트라 기법1(view_functions 딕셔너리 스왑, R626_BROKEN 환경변수로 워커 "
     "서브프로세스 안에서만 트리거, 온디스크 되돌리기 없음), 프런트는 추출한 두 옵션 템플릿을 스크래치 메모리 문자열로 되돌려 Node로 재실행 — 둘 다 옛 "
     "코드가 데모 발주처를 실제 발주처와 구분 없이 보여주는 옛 동작을 재현함을 확인, 실제 app.py·admin.js 파일은 이 검증 내내 디스크에 전혀 쓰이지 "
     "않았음을 매번 원본 대조로 확인 — 첫 실행 22/22 통과. app.py·static/admin.js 둘 다 변경이라 WMI로 서버 재기동 필요, "
     "BUILD_HASH 로테이션 예상(예측 말고 재기동 후 실측 확인)."),

    ("test_scan_round627_fixes.py",
     "스캔 627라운드 회귀(Part B, 직접조사·하위위임 없음) — manage.py go-live가 데모 발주처(insurers, is_demo=1 전량)를 통째로 "
     "지우면서도 남은 실제 발주처가 몇 곳인지(0곳 포함) 사후요약 어디에도 안 보여주던 결함, 1건. round406이 다른 조사(공유 "
     "verify.db 시딩 경쟁조건) 도중 관찰만 하고 '407 이후 별도 판단 대상'으로 미뤄 둔 항목을 이 세션이 회수 — round624/625/626이 "
     "이 세션에서 막 세운 cases.is_demo/insurers.is_demo 불변식 조사의 연장선에서, '다른 곳에도 is_demo 노출 누락이 있는가'를 "
     "살피다가 round626 자신의 실측 수치(운영DB 읽기전용: 활성 발주처 7곳 중 6곳이 is_demo=1)를 다시 짚어 확정. round475가 형제 "
     "표(admins)의 정확히 같은 모양 결함(go-live의 데모계정 정리가 마지막 최고관리자를 지울 위험)을 고치며 사후요약에 '관리자 "
     "계정이 하나도 없습니다' 경고+정확한 복구 명령까지 넣었는데, admins·partners 둘 다 있는 그 사후요약 줄(manage.py "
     "cmd_go_live() 끝부분, 직접 Read로 확인)이 insurers 에는 처음부터 없었다 — 오늘 go-live 를 돌리면 실제로 발주처 1곳만 "
     "남는데도 화면에 전혀 안 나온다. 삭제 로직 자체(무엇을 is_demo=1로 보고 지우는가)는 이미 624/625/626이 확정한 그대로라 "
     "안 건드림(정책 변경 아님, round406도 '실제 데이터손실은 아니고 운영자 경험상의 누락'이라고 스스로 정리해 둠) — 순수 "
     "가시성 추가이지 정책판단이 아니므로 결정대기로 넘기지 않고 바로 처리. 고침 — ②단계(트랜잭션 안, admins·partners 카운트와 "
     "나란히) 직후에 n_insurer 를 한 번 더 세고, 트랜잭션이 끝난 뒤 사후요약에 admins 형제와 정확히 같은 패턴(0곳이면 경고+"
     "create-insurer 복구 명령, 아니면 '발주처 N개사 유지됨' 개수 보고)을 그대로 이식 — 새 컬럼·새 정책·새 메커니즘 없음. "
     "회귀테스트(test_scan_round627_fixes.py+launcher, 13개 검사) 신설 — round475 launcher 패턴(기법: manage.py 소스를 "
     "R627_BROKEN 환경변수로 인메모리에서만 옛 코드로 치환해 exec, 실제 파일은 이 프로세스에서도 launcher 프로세스에서도 전혀 "
     "안 씀) 그대로 재사용. 실제 python manage.py 서브프로세스(init --with-demo → go-live --yes)로 두 시나리오 대조 — "
     "①데모만 있던 스크래치 DB는 go-live 뒤 발주처가 실제로 0곳이 됨을 확인 후 고친 코드는 경고+복구명령을 실제로 출력함을, "
     "②create-insurer로 실제 발주처 1곳을 미리 심으면 go-live 뒤에도 1곳이 살아남음을 확인 후 고친 코드는 '발주처 1개사 "
     "유지됨'으로 보고하고 0곳 경고는 안 뜸(과잉경보 아님)을 실측. 되돌림-증명 — 두 시나리오 모두 옛 코드로도 삭제 자체(0곳/1곳 "
     "결과)는 동일하게 재현되지만 go-live 출력 어디에도 '발주처'·'보험사' 언급이 전혀 없음을 확인 — 회귀가 삭제 로직이 아니라 "
     "보고 누락이었음을 정확히 증명. 첫 실행 13/13 통과. manage.py는 app.py가 import하지 않는 독립 CLI 도구라 서버 재기동 "
     "불필요, BUILD_HASH 불변(app.py·static·templates 미변경이라 재기동 자체를 안 함)."),
    ("test_scan_round628_fixes.py",
     "스캔 628라운드 회귀(직접조사, 하위위임 없음. 611~627라운드 17라운드짜리 온디스크 되돌림 마이그레이션이 끝난 뒤 첫 순수 "
     "신규조사 라운드) — db.py seed()가 협력업체 시드 파일(data/partners_seed.json)을 못 읽거나 형식이 틀려도 아무 경고 없이 "
     "협력사 0곳으로 조용히 넘어가던 결함 1건. ingest_partners.py 자신의 round300 주석이 이미 예언해 둔 채 그동안 아무도 손대지 "
     "않고 남아 있던 자리 — round300은 그 라운드 범위(쓰는 쪽, 임시파일 경유 원자적 교체)만 고치고 '읽는 쪽 db.py 는 json.load() "
     "실패를 빈 목록으로 조용히 삼킨다'는 사실은 그대로 남겨 뒀다. 직접 Read로 db.py 1952~1956행이 지금도 정확히 그 모양임을 "
     "확인한 뒤 조사 — 실제 위험은 두 갈래였다. [A] open()/json.load() 가 예외를 내면(파일없음·문법오류 등) 기존 except가 "
     "partners=[] 로 조용히 넘어가 admins·insurers 는 정상 시드되는데 partners 만 경고 없이 0곳으로 끝난다(이 프로젝트가 실제로 "
     "쓰는 '빈 DB로 서비스 첫날 재현' 리허설이나 dev DB 재생성 도중 이 파일이 손상되면 재현 전체가 조용히 왜곡됨). [B] "
     "json.load() 는 성공했지만 최상위가 배열이 아니거나(dict·null) 배열 원소가 dict 가 아니면(예: ['a','b']) 그 except를 "
     "안 거쳐 곧바로 아래 for 루프의 p.get() 이 없는 타입을 만나 AttributeError/TypeError 로 못 잡힌 채 app.py 모듈 최상단의 "
     "무방비 DB.init_db() 호출까지 새어나가 서버 기동 자체가 죽는다(빈 dict·빈 리스트처럼 우연히 0번 반복되는 모양만 [A]와 "
     "똑같이 조용히 0곳이 됨) — 실행으로 직접 재현해 확정. 고침(db.py seed(), 정책 불변 — partners 없이도 계속 시드하는 기존 "
     "동작은 그대로, boq_history()의 round268 처방과 같은 모양) — 같은 자리에서 두 갈래를 함께 막는다: (a) json.load() 실패 시 "
     "_log.warning() 으로 원인을 남긴다, (b) isinstance(partners, list) and all(isinstance(p, dict) for p in partners) 로 형태까지 "
     "검증해 어긋나면 역시 _log.warning() 후 partners=[] 로 안전하게 계속한다. 회귀테스트(test_scan_round628_fixes.py, 57개 검사) "
     "신설 — 실제 DB.seed()를 :memory: DB(진짜 스키마+migrate() 적용)에 기형 입력 6종(파일없음·JSON문법오류·빈dict·"
     "비어있지않은dict·null·dict아닌원소 리스트)+정상 리스트로 실행해 기형 입력 전부가 크래시 없이 협력사 0곳·경고 정확히 1건· "
     "admins 시드는 그대로(동작 불변)임을, 정상 입력엔 경고가 없음(과잉경보 아님)을, 실제 운영 시드파일(398개사)도 새 형태검증을 "
     "그대로 통과함(오탐 없음)을 실측. 되돌리기-증명 — 628 이전 실제 코드 6줄을 그대로 재구성해 격리된 exec() 네임스페이스로 같은 "
     "6종 입력을 실행(디스크의 실제 db.py 는 이 절에서 전혀 안 씀) — 옛 코드는 [A]형에서 경고 없이 조용히 원소 0개로 끝나고 "
     "[B]형(비어있지않은dict·null·dict아닌원소 리스트)에서는 실제로 AttributeError/TypeError 로 죽는 것까지 실행으로 재현해 이 "
     "회귀가 실제 결함을 잡아낼 능력이 있음을 증명한 뒤 복원. 추가로 db.py 파일 자신이 이 검증 내내 디스크에 전혀 안 쓰였음(원본과 "
     "동일)까지 확인. 첫 실행 57/57 통과. db.py는 app.py 최상단에서 import되고 무조건 DB.init_db() 를 호출하므로 정적임포트 "
     "재기동 원칙에 따라 재기동 대상 — 다만 이번 수정은 seed()의 예외 로깅·형태검증 추가일 뿐이라 이미 시드가 끝난 기존 운영 "
     "DB(cases·partners·go_live_at 존재)의 조회/쓰기 경로에는 영향이 없다(seed()는 DB가 완전히 비어 있을 때만 도는 일회성 경로)."),
    ("test_scan_round629_fixes.py",
     "스캔 629라운드 회귀(직접조사, 하위위임 없음. 611~627라운드 마이그레이션이 끝난 뒤의 순수 신규조사) — manage.py go-live의 "
     "사후요약이 '관리자는 있지만 최고관리자가 0명'인 상태를 그대로 '정상(유지됨)'으로 찍던 결함, 1건. round475는 이미 이 정확한 "
     "위험을 실측으로 증명했다 — create-admin을 --role 없이 돌린 뒤 go-live를 실행하면 '관리자 1명·최고관리자 0명'이 되고, 그러면 "
     "계정관리·정산이체·요율설정을 아무도 켤 수 없다. 그 라운드는 이 위험을 두 곳에 심었다 — cmd_check()(317-337행)의 사전점검에 "
     "n_super 분기, cmd_go_live()의 ③단계 삭제 루프(2129-2137행)에 '이 삭제 자체가 마지막 최고관리자를 지우면 안 된다'는 가드. "
     "round627이 바로 이 함수의 사후요약(3번째 자리)에 n_insurer를 보태며 '형제 요약이 이미 아는 것을 이 요약도 알아야 한다'는 "
     "원칙을 세웠는데, 그 원칙이 admins 자신에게는 적용된 적이 없었다 — go-live의 사후요약은 n_admin==0만 보고, 관리자가 1명 "
     "이상이면 최고관리자가 하나도 없어도 무조건 '관리자 계정 N개 유지'(정상)로 찍는다. ③단계 가드는 'go-live의 삭제 자체가 "
     "최고관리자를 0명으로 만드는 것'만 막을 뿐 — go-live를 돌리기 전부터 이미 최고관리자가 0명이던 상태(데모 admin/staff가 "
     "애초에 없거나 이미 지워진 채 create-admin을 --role 없이 돌려 만든 계정 하나만 있는 흔한 배포 실수)는 그대로 통과시켜 화면에 "
     "초록을 찍는다 — round475가 cmd_check()에서 'bad'로 잡는 바로 그 상태를 go-live 자신의 요약에서는 아무도 못 알아챈다. 고침"
     "(manage.py, cmd_go_live() 한 함수 두 자리, 정책 변경 아님) — 트랜잭션 안에서 n_admin과 나란히 n_super(role='최고관리자')를 "
     "한 번 더 세고, 사후요약에 cmd_check()와 같은 문구(관리자는 있지만 최고관리자 0명이면 경고+복구명령, 아니면 최고관리자 포함 "
     "개수 보고)를 이식 — 새 컬럼·새 정책·새 메커니즘 없음. 회귀테스트(test_scan_round629_fixes.py+launcher, 18개 검사) 신설 — "
     "round627 launcher 패턴(manage.py 소스를 R629_BROKEN 환경변수로 인메모리에서만 옛 코드로 치환해 exec, 실제 파일은 이 "
     "프로세스에서도 launcher 프로세스에서도 전혀 안 씀) 그대로 재사용. 실제 python manage.py 서브프로세스(init → "
     "[create-admin 선택] → go-live --yes)로 세 시나리오 대조 — ①--role 없이 만든 관리자 1명뿐인 스크래치 DB는 go-live 뒤 고친 "
     "코드가 경고+복구명령을 실제로 출력함을, ②--role 최고관리자로 만든 관리자가 있으면 경고 대신 '최고관리자 N명 포함' 개수를 "
     "보고하고 과잉경보가 없음을, ③관리자를 아예 안 만들면 round629 이전부터 있던 '관리자 계정이 하나도 없습니다' 경고가 회귀 없이 "
     "그대로 뜸을(elif로 붙였으므로) 실측. 되돌림-증명 — 세 시나리오 모두 옛 코드로도 계정 상태(삭제 여부)는 동일하게 재현되지만, "
     "①에서만 go-live 출력 어디에도 최고관리자 관련 경고가 전혀 없이 '관리자 계정 1개 유지'라는 거짓 초록이 그대로 찍힘을 확인 — "
     "회귀가 삭제 로직이 아니라 보고 누락이었음을 정확히 증명. 첫 실행 18/18 통과. manage.py는 app.py가 import하지 않는 독립 CLI "
     "도구라 서버 재기동 불필요, BUILD_HASH 불변(app.py·static·templates 미변경이라 재기동 자체를 안 함)."),
    ("test_scan_round630_fixes.py",
     "스캔 630라운드 회귀(직접조사, 하위위임 없음. 611~629라운드 마이그레이션·미세보수가 끝난 뒤의 순수 신규조사) — manage.py "
     "go-live의 사후요약이 '협력업체가 0개사'인 상태를 그대로 '유지됨'(정상)으로 찍던 결함, 1건. round627은 발주처(n_insurer) "
     "0명을, round629는 '관리자는 있지만 최고관리자 0명'을 각각 사후요약에 경고로 이식하며 '형제 요약이 이미 아는 것을 이 요약도 "
     "알아야 한다'는 원칙을 세웠는데, 바로 그 두 형제와 나란히 같은 트랜잭션에서 함께 세는 세 번째 숫자 n_partner만은 이 원칙이 "
     "한 번도 적용된 적이 없었다. go-live는 partners 행 자체를 지우지 않지만(문서화된 대로 실제 영업 자산이라 보존 — 로그인 "
     "수단·평판만 정리), partners에는 create-admin/create-insurer 같은 CLI가 없어 콘솔에서만 등록·삭제된다 — 누군가 go-live 전에 "
     "콘솔에서 협력사를 전부 지웠거나 애초에 한 곳도 등록하지 않은 채(흔한 첫 배포 실수: init 직후 바로 go-live부터 돌리는 순서) "
     "go-live를 돌리면, 사후요약은 n_partner==0이어도 무조건 '협력업체 0개사 유지됨'을 초록으로 찍는다 — 낙찰받을 업체가 하나도 "
     "없어 사건을 아무도 처리 못 하는, n_insurer==0(사건 등록 불가)·n_super==0(관리 기능 불가)과 정확히 같은 급의 운영 정지 "
     "상태인데도. 고침(manage.py, cmd_go_live() 사후요약 한 자리, 정책 변경 아님) — 삭제 로직·판정 기준은 그대로 두고, "
     "n_insurer·n_admin과 같은 모양(if 0: warn 아니면 ok)으로 n_partner도 맞춘다 — CLI가 없으므로 복구 안내는 콘솔 화면 이름"
     "([업체 등록·관리])을 가리킨다. 회귀테스트(test_scan_round630_fixes.py+launcher, 17개 검사) 신설 — round627/629 launcher "
     "패턴(manage.py 소스를 R630_BROKEN 환경변수로 인메모리에서만 옛 코드로 치환해 exec, 실제 파일은 이 프로세스에서도 launcher "
     "프로세스에서도 전혀 안 씀) 그대로 재사용. 실제 python manage.py 서브프로세스(init → [partners 직접 INSERT 선택] → go-live "
     "--yes)로 시나리오 대조 — ①협력업체 0곳인 스크래치 DB는 go-live 뒤 고친 코드가 경고+콘솔 화면 안내를 실제로 출력함을, "
     "②협력업체 1곳을 미리 넣어 두면 경고 대신 '1개사 유지' 개수를 보고하고 과잉경보가 없음을, ③이 수정 옆의 발주처·관리자 형제 "
     "경고가 회귀 없이 그대로 뜸을 실측. 되돌림-증명 — 두 시나리오 모두 옛 코드로도 partners 행 상태(삭제 안 함)는 동일하게 "
     "재현되지만, ①에서만 go-live 출력 어디에도 협력업체 관련 경고가 전혀 없이 '협력업체 0개사 유지됨'이라는 거짓 초록이 그대로 "
     "찍힘을 확인 — 회귀가 삭제 로직이 아니라 보고 누락이었음을 정확히 증명. 첫 실행 17/17 통과. manage.py는 app.py가 import하지 "
     "않는 독립 CLI 도구라 서버 재기동 불필요, BUILD_HASH 불변(app.py·static·templates 미변경이라 재기동 자체를 안 함). 이 수정이 "
     "round627의 사후요약 NEW_BLOCK_2를 문자 단위로 건드려 round627·629 두 라운드의 회귀테스트 하드코딩 상수도 함께 갱신하고 "
     "각각 standalone 재실행으로 재확인(627: 13/13, 629: 18/18, 둘 다 회귀 없이 그대로 통과)."),
    ("test_scan_round631_fixes.py",
     "스캔 631라운드 회귀(직접조사, 하위위임 없음. 611~630라운드의 마이그레이션·미세보수가 끝난 뒤의 순수 신규조사) — AI 자동승인 "
     "임계값(settings.ai_auto_threshold)을 다루는 두 자리가 OverflowError를 못 잡던 결함, 2건. round485가 'int(float(x))는 x가 "
     "inf/-inf/1e400류(float 변환은 성공하지만 int 변환만 실패)일 때 ValueError가 아니라 OverflowError를 낸다'는 함정을 발견해 "
     "형제 둘(_setting_int·api_settings_set의 RANGES 루프)에 이식했고, round596은 같은 예외의 또 다른 유입구(JSON 본문의 id류)를 "
     "전역 예외핸들러(err_500)에서 한 번에 400으로 눌러 뒀는데, 이 두 라운드 사이에서 정확히 같은 값(ai_auto_threshold)을 다루는 "
     "세 번째·네 번째 자리가 빠져 있었음을 app.py 전체의 OverflowError 8곳 전수대조로 확인(round485·596 자신의 위치만 있고 이 "
     "두 함수는 어디에도 없었다). [A] _ai_threshold(conn) — 자동승인 임계값을 읽는 유일한 헬퍼(호출부 2곳: _apply_ai_routing· "
     "api_ai_review_stats). docstring 자체가 설정값이 있으면 그것을, 없으면 기본 90으로 항상 안전하게 되돌아간다고 약속하는데"
     "(_setting_int과 똑같은 계약) except가 (sqlite3.Error, ValueError)뿐이라 settings.value='inf'면 그대로 새어나간다 — 유일한 "
     "실사용 호출부 _apply_ai_routing()은 사진이 이미 저장·커밋된 뒤 자동승인 여부만 결정하는 후처리인데 그 함수 자신의 except가 "
     "sqlite3.Error 하나뿐이라(직접 Read로 확인) 못 가려, 사진은 반영됐는데 업로드 응답 전체가 400(round596 전역핸들러의 범용 "
     "문구)으로 돌아가 협력사가 자기 사진이 이미 저장됐다는 사실을 알 방법이 없어진다. [B] api_ai_threshold_set()(PATCH "
     "/api/ai/threshold, 최고관리자 전용) — JSON 본문의 threshold가 1e400이면(표준 JSON 문법) 파서가 그대로 float('inf')로 성공 "
     "파싱하고(실측: json.loads로 직접 확인) int() 변환이 OverflowError를 내는데 이 라우트 자신의 except가 (TypeError, "
     "ValueError)뿐이라 이 라우트가 준비한 구체적 안내문이 round596 전역핸들러의 범용 문구(code=BAD_INPUT)로 가려진다 — 500은 "
     "아니지만(round596 안전망) 이 함수 자신의 UX 의도가 무효화됨. 고침(app.py, 두 곳 다 형제와 같은 최소 diff) — except 튜플에 "
     "OverflowError를 추가([A]는 TypeError도 함께, _setting_int과 바이트 단위로 같은 튜플). 새 메커니즘·새 정책 없음. 회귀테스트"
     "(test_scan_round631_fixes.py, 24개 검사) 신설 — 실제 Flask 앱(스크래치 DB, 최고관리자 세션)으로 [1] 소스 확인(두 except "
     "튜플·_apply_ai_routing 자신은 여전히 sqlite3.Error 하나뿐이라는 구조적 근거), [2] settings에 문자 그대로 'inf'를 심고 "
     "_ai_threshold()를 직접 호출해 예외 없이 기본값(90)을 돌려주는지, PATCH 라우트에 1e400을 실제 HTTP 왕복으로 보내 이 라우트 "
     "고유 안내문이 나오는지(정상값·범위밖 정상숫자·비숫자 문자열은 기존과 동일해 회귀없음도 함께 확인), [3] 되돌리기-증명 — 두 "
     "함수 다 이 라운드가 고친 except 튜플만 옛(취약) 튜플로 되돌린 사본을 exec로 격리 재구성해([A]는 모듈 속성 A._ai_threshold "
     "직접치환, [B]는 view_functions 딕셔너리 항목치환 — round414·610·615가 확립한 안전패턴 그대로) 옛 코드가 실제로 "
     "OverflowError를 던지거나(A) 전역핸들러의 범용 문구로 가려지는지(B)를 실행으로 재현한 뒤 finally에서 원복 — 진짜 app.py "
     "파일은 이 과정 전체에서 단 한 바이트도 안 바뀐다(테스트 시작/끝 시점 소스 바이트 단위 대조로 재확인). 첫 실행 24/24 통과. "
     "app.py 자신의 변경(_ai_threshold·api_ai_threshold_set 두 함수)이라 서버 재기동 필요, BUILD_HASH 로테이션 예상(예측 말고 "
     "재기동 후 실측 확인)."),
    ("test_scan_round632_fixes.py",
     "스캔 632라운드 회귀(직접조사, 하위위임 없음) — 복합공종(2개 이상 트레이드) 사건의 cases.category 표시문자열이 "
     "제출 순서에 그대로 의존해, compliance.related_sum()의 분할회피(쪼개기) 탐지가 같은 트레이드 집합을 가진 관련 건을 "
     "놓치던 결함. compliance.py는 이 사업의 형사리스크 방어선(무등록 건설업, 5년 이하 징역 또는 5천만원 이하 벌금)이고, "
     "related_sum()은 같은 보험사·같은 공종·같은 지역·최근 30일인 관련 건을 합산해 대법원 2018도3821 기준 쪼개기를 잡는다. "
     "그런데 두 사건이 둘 다 아직 work_lots로 안 쪼개졌을 때(no_photo:true 2트랙 접수 등, compliance.py 자신이 상시 상태로 "
     "적어 둔 경로 — _create_case()가 work_lots INSERT 루프를 no_photo 분기의 이른 return 뒤에만 두기 때문) '같은 공종' "
     "판정은 cases.category 문자열의 완전일치로 폴백한다(round122). 트레이드 이름 내부에 구분자와 같은 문자(·)가 섞여 "
     "안전하게 못 쪼갠다는 이유로 compliance.py·dispatch.py·app.py 세 곳의 _case_trades()/case_trades() 모두 이 폴백을 "
     "의도적으로 유지해 왔는데, 정작 그 문자열을 만드는 유일한 생성 지점(app.py _create_case, grep 재확인 — 이후 재작성 "
     "경로 없음)이 _normalize_categories()가 입력 순서 그대로 돌려준 cats를 정렬 없이 이어붙였다(복합(A · B)). 보험사 "
     "포털·v1 API가 같은 트레이드 집합을 다른 순서로 두 번 보내면(체크박스 클릭 순서 등 흔한 우연, 공격일 필요도 없음) "
     "문자열이 서로 달라져 related_sum()이 0원을 돌려준다 — 이 파일 자신의 상단 선언(당사자·동일유형·반복수주가 가장 "
     "취약)과 region 쪽에 이미 적용된 애매하면 합산 원칙(round196)에 정면으로 어긋난다. 실측(직접 실행, 되돌리기 전) — "
     "같은 두 트레이드(유리·샷시·자동문·조경·수목)를 no_photo:true로 순서만 바꿔 두 번 접수하면 related_sum()이 서로를 "
     "관련건으로 못 보고 0원을 돌려준다. 고침(app.py _create_case, 단 한 곳) — 트레이드 이름을 새로 파싱하는 대신(세 "
     "_case_trades() 모두가 피해 온 위험을 다시 만드는 셈이라) 유일한 생성 지점에서 cats를 정렬해 같은 집합이면 항상 "
     "같은 문자열이 나오게 한다(cats를 sorted(cats)로) — _idem_fingerprint()가 같은 종류의 문제(제출 순서 차이)를 이미 "
     "sorted()로 푼 것과 동일한 처방이라 새 메커니즘·새 정책판단이 아니다. rule_for()의 복합판정(round315, 토큰을 집합 "
     "으로 재귀판정)은 이미 순서 무관이라 영향 없음(회귀없음 재확인). 회귀테스트(test_scan_round632_fixes.py, 16개 검사) "
     "신설 — 실제 Flask 앱(스크래치 DB) + 실제 v1 API 라우트(POST /api/v1/cases, X-API-Key 인증, no_photo:true)로 [1] "
     "소스 확인(join(sorted(cats))이 정확히 1곳), [2]~[3] 같은 두 트레이드를 순서만 바꿔 두 번 접수해 (a) 저장된 "
     "category 문자열이 이제 동일함 (b) 실제 compliance.related_sum()이 서로를 관련건으로 정확히 합산함 (c) 단일 공종·"
     "동일순서 재접수는 회귀없음을 확인, [4]~[5] 되돌리기-증명 — _create_case() 안의 sorted(cats) 토큰 하나만 옛 코드로 "
     "되돌린 사본을 exec로 격리 재구성해(round414·610·615·631이 확립한 안전패턴, 실제 파일 미변경) 옛 코드가 실제로 "
     "순서 다른 문자열을 만들고 related_sum() 합산을 놓치는지 실행으로 재현(별도 보험사로 격리해 앞 단계 사건과 섞이지 "
     "않게 함)한 뒤 finally에서 원복, [6] 원복 후 재확인. 첫 실행 16/16 통과. app.py 자신의 변경(_create_case 한 줄)이라 "
     "서버 재기동 필요, BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round634_fixes.py",
     "스캔 634라운드 회귀(직접조사, 하위위임 없음) — notify()의 반복형 알림(_REPEATING_NTYPES: 완료승인독촉·낙찰승인독촉·"
     "완료보고독촉) 중복접기가 (ntype, audience_type, case_id)만 보고 옛 '안읽음' 알림을 read_at으로 접어, 실제 수신자"
     "(insurer_id/partner_id)는 전혀 보지 않던 결함. 전체재경매 낙찰확정(app.py 약 11729행, cases.partner_id를 통째로 "
     "새 업체로 갈아치우는 정상 절차 — '시공중'·'완료보고지연' 상태에서 허용된다) 뒤 같은 사건에 같은 반복형 ntype"
     "(완료보고독촉, api_case_remind_report가 유일한 호출부)을 새 업체에게 보내면, 예전 코드는 case_id·ntype·"
     "audience_type만 대조해 옛 업체가 한 번도 열어 본 적 없는 알림까지 read_at을 채워 읽음으로 만들었다(직접 실행 재현: "
     "partner_id만 다른 두 번째 notify() 호출만으로 첫 번째 행이 조용히 읽음이 됨 — 실제 포털 배지 API로도 재확인). "
     "협력사 포털의 미읽음 배지 수·감사기록이 본 적 없는데 읽었다고 거짓말하게 되는, 읽음배지·알림중복접기 결함. 고침"
     "(app.py, notify() 딱 한 곳 — 5개 반복형 ntype 전부가 거치는 유일한 합류점): 중복접기 UPDATE의 WHERE 절에 "
     "insurer_id·partner_id COALESCE 비교 두 줄을 추가해 수신자까지 같을 때만 옛 행을 접는다. 관리자 브로드캐스트(둘 다 "
     "NULL)·같은 수신자 반복은 기존과 동일하게 동작해 회귀가 없다(직접 실행으로 재확인). 새 메커니즘·새 정책 판단 없음. "
     "회귀테스트(test_scan_round634_fixes.py, 14개 검사) 신설 — 실제 app.py import + 스크래치 DB + 실제 Flask "
     "테스트클라이언트(GET /api/partner/notifications 포털 배지)로 [1] 소스 확인(고친 SQL이 정확히 한 번 있음), [2]~[3] "
     "재배정 시나리오를 실제 실행해 (a) 고친 코드는 옛 수신자의 안읽음을 보호하고 포털 배지도 정확함 (b) 같은 수신자 "
     "반복은 여전히 중복접기가 동작함을 확인, [4]~[5] 되돌리기-증명 — notify() 안 SQL 한 곳만 옛 코드로 되돌린 사본을 "
     "exec로 격리 재구성해(round414·490·507·610·615·621·631·632가 확립한 안전패턴, A.notify 속성만 임시치환·실제 파일 "
     "미변경) 옛 코드가 실제로 read_at을 부당하게 채우고 포털 배지도 틀리게 내려주는지 실행으로 재현한 뒤 finally에서 "
     "원복, 원복 후 재확인. 첫 실행 14/14 통과. app.py 자신의 변경(notify() 한 곳)이라 서버 재기동 필요, BUILD_HASH "
     "로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round636_fixes.py",
     "스캔 636라운드 회귀(직접조사, 하위위임 없음) — 승률(win_rate)·절감(saving) KPI 양쪽이 이 사건이 실제로 낙찰됐는가를 "
     "award_amount 하나만 곧이곧대로 믿고 재던 결함. CASE_AMOUNT_SQL(app.py 상단)은 이미 award_amount 가 NULL/0 일 수 "
     "있어 low_price 로 넘어가야 한다는 캐논인데, 그 방어가 안 미친 두 자리가 따로 있었다 — _resync_partner_stats()· "
     "api_recount_partner_stats() 의 승률 분자(COALESCE(c2.award_amount,0)>0, 두 함수는 서로 고치면 여기도 같이 고치라고 "
     "지목하는 텍스트 중복이었다)와 _compute_ops_kpi() 의 절감 집계(save_row·by_cat, bare award_amount 를 WHERE·산술 "
     "양쪽에 씀). 실측(운영 DB, 읽기전용, 두 방법으로 재확인) — 사건#19(26-80003, is_demo=0 진짜 사건)는 낙찰→시공→"
     "완료보고까지 정상 진행돼 awarded_at·partner_id·completed_at 이 다 찍혀 있고 low_price=3,400,000 인데 award_amount "
     "만 NULL 이다(award_route 도 NULL — 지금 코드의 낙찰 경로 셋 중 어느 것도 이 조합을 새로 못 만든다, api_insurer_award·"
     "api_case_award·dispatch.settle_agreement 전부 award_amount·awarded_at·award_route 를 같은 UPDATE 문 안에서 함께 "
     "쓴다 — 옛 결함이 남긴 화석으로 보인다). 지금은 검수대기라 완료(status=완료) 조건을 보는 두 KPI 엔 아직 영향이 "
     "없지만(직접확인: is_demo=0·status=완료·award_amount NULL 인 사건 0건), 이 사건이 훗날 완료로 넘어가면 승률 분자에서 "
     "조용히 빠지고(분모인 입찰엔 이미 잡혀 있다) 절감 집계에선 그 사건 자체가 통째로 안 잡힌다. 고침(app.py) — "
     "_compute_ops_kpi 는 새 공유 상수 AWARD_CONFIRMED_SQL(CASE_AMOUNT_SQL 바로 아래 신설: "
     "COALESCE(NULLIF(award_amount,0), NULLIF(low_price,0), 0) — CASE_AMOUNT_SQL 의 앞 두 단과 같고 est_price 단만 "
     "뺐다, 낙찰 못 받은 사건도 est_price>0 이라 거기까지 내려가면 낙찰 표본이 아닌 사건까지 섞인다)를 이미 쓰던 "
     "f-string 관례(CASE_AMOUNT_SQL·SAVE_BASE_SQL) 그대로 8곳에 적용. 반면 _resync_partner_stats·"
     "api_recount_partner_stats 는 **일부러 그 상수를 안 쓴다** — 1차 시도(세 자리 전부 공유 상수화)가 전체 배터리에서 "
     "round6·26·131·132·133·364 여섯 개의 기존 회귀테스트를 깨는 것을 실행으로 직접 확인했다: 그 다섯 라운드(26·131·"
     "132·133·364)는 이 두 함수 본문을 conn.execute(플레인 삼중따옴표) 앵커로 오려내 빈 네임스페이스에 exec 격리하는 "
     "기법을 쓰는데, f-string(conn.execute(f 삼중따옴표))으로 바꾸자 앵커 자체가 사라져 엉뚱한 함수를 오려내거나 "
     "NameError로 죽었고, round6 는 _compute_ops_kpi 안의 옛 리터럴 문구를 소스 문자열로 직접 세는 검사라 문구를 "
     "바꾸면 당연히 깨졌다. 최종 설계 — _compute_ops_kpi 만 공유 상수를 쓰고(원래도 f-string·외부상수 참조 관례가 "
     "있던 함수라 새 위험이 없다), 여러 라운드가 반복해서 격리-exec 로 단독 검증해 온 _resync_partner_stats· "
     "api_recount_partner_stats 두 곳은 리터럴 NULLIF 사슬(COALESCE(NULLIF(c2.award_amount,0), "
     "NULLIF(c2.low_price,0), 0))을 그대로 복제해 넣는다 — '고치면 여기도 같이 고쳐라'라는 이 두 함수 자신의 기존 "
     "관례(텍스트 중복 유지) 그대로다. 이 판단에 맞춰 여섯 개 기존 테스트도 손봤다 — round6 는 새 리터럴 문구에 맞춰 "
     "검사 문자열 갱신(round364 가 이 두 함수를 다룰 때 이미 세운 '공식이 정당하게 바뀌면 옛 검사 문구도 같이 "
     "갱신한다'는 원칙 그대로), round131·132·364 는 새 SQL이 읽는 c2.low_price 컬럼이 세 파일의 최소 인메모리 스키마에 "
     "없어 난 OperationalError를 해결하려 CREATE TABLE cases 에 low_price INTEGER 한 컬럼만 추가(기존 "
     "assert·시나리오는 무변경 — 세 파일의 INSERT 가 전부 award_amount 를 직접 채우므로 NULLIF 사슬이 그 값에서 바로 "
     "멈춰 low_price 가 NULL 이어도 결과에 영향 없음, round364 가 b.voided_at 추가할 때 이미 겪은 것과 같은 종류의 "
     "스키마 캐치업), round26·133 은 이번 변경으로 이미 그린이라 무변경. 여섯 파일 전부 단독 재실행으로 그린 재확인. "
     "회귀테스트(test_scan_round636_fixes.py, 29개 검사) 신설 — 실제 app.py import + 스크래치 DB + 실제 Flask "
     "테스트클라이언트(POST /api/admin/recount-partner-stats)로 [1] 소스 확인(_compute_ops_kpi 는 공유 상수 8곳, "
     "두 win_rate 함수는 플레인 삼중따옴표를 유지하고 공유 상수에 의존하지 않으며 새 리터럴 NULLIF 사슬을 정확히 "
     "한 번씩 씀), [2]~[3] 사건#19와 똑같은 모양(award_amount NULL·low_price 有·낙찰 경매 bids/auctions 존재)의 화석 "
     "사건을 심어 (a) _resync_partner_stats 가 승률 100.0을 낸다 (b) _compute_ops_kpi 가 절감 1건·1,000,000원을 잡는다 "
     "(c) 실제 HTTP 라우트(api_recount_partner_stats)도 같은 100.0을 낸다는 것을 확인, [4]~[5] 되돌리기-증명 — 세 함수 "
     "본문만 옛 SQL로 되돌린 사본을 exec로 격리 재구성해(round414·490·507·610·615·621·631·632·634가 확립한 안전패턴, "
     "모듈 속성과 app.view_functions[api_recount_partner_stats](require_role 데코레이터까지 다시 씌움)만 임시치환·실제 "
     "파일 미변경) 옛 코드가 실제로 승률을 0.0으로, 절감 집계를 0건으로 떨어뜨리는지 세 곳 모두 실행으로 재현한 뒤 "
     "finally에서 원복, 원복 후 재확인. 첫 실행(수정 반영 후) 29/29 통과, 전체 배터리 재확인까지 완료(콜라트럴 6개 "
     "포함 전부 그린). app.py 자신의 변경(공유 상수 신설 + _compute_ops_kpi 8곳 + 두 win_rate 함수 리터럴 교체)이라 "
     "서버 재기동 필요, BUILD_HASH 로테이션 예상(재기동 후 실측 확인)."),
    ("test_scan_round637_fixes.py",
     "스캔 637라운드 회귀(직접조사, 하위위임 없음) — 발주처(보험사) 관리 화면(admin.js VIEWS.insurers)의 요약 카드 "
     "4개(등록 발주처·계약 체결·포털 계정·평균 계약 요율)가 GET /api/insurers?all=1 이 돌려주는 data 를 그대로 세어 "
     "데모 발주처까지 실적에 합산하던 결함. round624~626 이 바로 이 화면·이 API 의 is_demo 배선을 연달아 고치며 "
     "실측 남긴 값 그대로 — 운영 DB(읽기전용, 2026-09-13) 재확인: 활성 발주처 7곳 중 6곳이 is_demo=1(실제 보험사명을 "
     "그대로 쓴 시연용 데이터)이고 실계약은 'R450검증손보' 1곳뿐인데, 화면 맨 위 '평균 계약 요율' 카드는 이 6곳까지 "
     "섞어 9.9%로 떴다(실제 10.0%). 목록 표는 행마다 이미 회색 '데모' 표를 붙이는데(round626 이 실측 근거로 쓴 그 "
     "표), 정작 맨 위 요약 카드 넷만 못 걸렀다 — 이 코드베이스 전체가 지키는 '데모는 실적 집계에서 뺀다'는 원칙 "
     "(대시보드·KPI·v1 API 의 AWARD_CONFIRMED_SQL 계열, round624~626 의 is_demo 배선 등)이 이 화면 요약 카드에는 "
     "미치지 못했던 사각지대. 고침(static/admin.js, VIEWS.insurers) — `const act = data.filter(i=>i.status==='활성');` "
     "한 줄을 `const real = data.filter(i=>!i.is_demo); const act = real.filter(i=>i.status==='활성');` 두 줄로 바꾸고, "
     "'계약 체결'·'포털 계정' 카드의 data.filter(...) 도 real.filter(...) 로 바꿨다(목록 표 자체는 그대로 data 전체를 "
     "보여준다 — 요약 숫자만 고쳤다). 회귀테스트(test_scan_round637_fixes.py, 20개 검사) 신설 — [1] 소스: round253 이 "
     "확립한 함수경계 슬라이스로 VIEWS.insurers 본문만 뽑아 새 두 줄이 있고 옛 줄이 없음을 확인. [2] Node 실행 — "
     "admin.js 에서 그대로 뽑은 bpPct 정의·계산식·krow 템플릿 블록을 운영DB 실측과 같은 모양의 목데이터(활성 7곳 중 "
     "6곳 데모)로 실제 실행해 '등록 발주처=1·활성=1·평균 요율=10.0%'이 나옴을 확인. [3] 되돌림-증명 — admin.js 는 이 "
     "세션 내내 한 바이트도 안 건드리고, round626 이 확립한 기법 그대로 옛(버그) 코드를 저장소 밖 임시 스크래치 .js "
     "파일(tempfile.mkdtemp() 산출물)에만 재현해 같은 목데이터로 실행 — '등록 발주처=7·평균 요율=9.9%'로 실제로 "
     "새는 것을 확인해 이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명. 첫 실행 20/20 통과, admin.js 는 테스트 "
     "실행 전후 바이트 단위로 동일함을 확인. static/admin.js 만의 변경(순수 클라이언트 렌더 로직, 서버 API·DB 스키마 "
     "무관)이라 app.py 자체는 안 바뀌었지만, static/ 파일도 BUILD_HASH(app.py+static+templates 해시) 산정에 들어가고 "
     "서비스워커가 그 값으로 캐시를 가르므로 재기동은 필요 — 재기동 안 하면 이미 열어 둔 PWA/브라우저가 옛 admin.js "
     "를 캐시에서 계속 쓸 수 있다."),
    ("test_scan_round639_fixes.py",
     "스캔 639라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py 의 robots_allows() 가 응답 없는 "
     "서버를 만나면 무한정 멈추던 결함. 표준 라이브러리 urllib.robotparser.RobotFileParser.read() 는 내부에서 "
     "urllib.request.urlopen(self.url) 을 timeout 인자 없이 호출한다(실제 소스로 확인) — 이 파일의 다른 모든 "
     "네트워크 호출(fetch() 의 TIMEOUT=8초)과 달리 robots_allows() 만 시간제한이 없었다. collect_one() 은 이 "
     "함수를 fetch() 보다 먼저, 사이트 한 곳당 최대 7번(진입 1회+SUB_PATHS 6회) 부르므로 응답 없는 서버 하나가 "
     "--all 배치 전체를 영구히 멈출 수 있었다 — 이 파일 자신의 docstring 원칙('응답이 느리거나 막히면 그냥 "
     "건너뛴다')과 정면으로 어긋난 사각지대. 실측: 바이트를 전혀 안 보내는 로컬 TCP 리스너로 재현 — 고치기 전 "
     "코드는 12초를 기다려도 반환되지 않았다. 고침(collect_emails.py robots_allows(), 225~266행) — rp.read() "
     "호출 구간에만 프로세스 전역 소켓 기본 타임아웃을 fetch() 와 같은 TIMEOUT(8초)으로 잠깐 걸었다 finally 로 "
     "복원한다(rp.read() 자체의 HTTP 오류코드 처리 401/403 전체거부·기타 4xx 전체허용은 재구현하지 않고 그대로 "
     "재사용). 회귀테스트(test_scan_round639_fixes.py, 6개 검사) 신설 — [1] 실행: 고친 함수가 바이트 없는 "
     "로컬 TCP 리스너를 상대로도 TIMEOUT(8초) 부근에서 반환하고 보수적으로 True(허용)를 돌려줌을 실측. [2] "
     "되돌리기-증명 — 라운드639 이전 원문을 독립 네임스페이스에 exec 로 재구성(실제 파일은 미변경)해 같은 "
     "서버를 상대로 호출, 12초가 지나도 여전히 멈춰 있음을 확인해 결함의 인과관계를 직접 증명. [3] 실제 "
     "호출부 collect_one() 도 robots_allows()+fetch() 두 단계 TIMEOUT 을 합친 시간 안에 끝까지 완주해 "
     "'접속 실패'로 정리됨을 실측. 기존 회귀(round218·267·299·420·514·517, collect_emails 관련 전부)를 "
     "재실행해 그린 유지 확인 — 테스트 충돌 없음. db.py/dispatch.py/manage.py/app.py/static·templates 는 "
     "무변경(collect_emails.py 는 관리자 콘솔이 아니라 수동 배치 스크립트라 서버 재기동 대상 아님, BUILD_HASH "
     "영향 없음)."),
    ("test_scan_round640_fixes.py",
     "스캔 640라운드 회귀(직접조사, 하위위임 없음) — check_tx_paths.py(BEGIN IMMEDIATE 트랜잭션 commit/ "
     "rollback 누락 점검 CLI, round124·291·574·620·621 이 이미 여러 번 자기 사각지대를 고친 도구)의 main() "
     "이 '이 commit/rollback 호출이 잠금~반환 구간 줄 번호 사이에 있는가'만 보고 '같은 실행 경로 위에 "
     "있는가'는 안 보던 결함. if/elif 로 갈라진 서로 다른 가지에 각각 commit() 과 (아무 처리 없는) return 이 "
     "있어도, 앞가지의 commit() 줄이 뒷가지 return 보다 앞줄이기만 하면 안전으로 오판됐다 — synthetic 함수로 "
     "직접 재현(if flag_a: commit();return 'a' / elif not flag_a: return 'b' — commit/rollback 전혀 없음)해 "
     "고치기 전 실제 코드가 이 결함 있는 합성 파일도 클린(0건)으로 오판함을 실측. 실제 저장소(app.py· "
     "dispatch.py·manage.py·seed_boq.py, 109개 함수) 재확인 — 고치기 전/후 모두 위반 0건(클린, 오탐 없음, "
     "지금까지 이 틈이 실제 결함을 감춘 적은 없었다). 고침 — check_tx_paths.py 에 _parent_map()·_branch_path()· "
     "_may_precede() 세 헬퍼를 신설해 공통 조상 if 에서 서로 다른 가지로 갈라지는 commit/rollback 호출은 그 "
     "return 을 지켜주지 못하는 것으로 판정하게 했다(기존 _commit_rollback_linenos() 는 _commit_rollback_calls() "
     "로 개명 — 줄번호 대신 실제 Call 노드가 필요해서). 범위 밖(다루지 않음, 확인되지 않음) — try/except 가지 "
     "사이의 같은 성격 사각지대, elif 가 아니라 독립된 두 if 로 각각 조기 return 하는 가드절 형태. 회귀테스트 "
     "(test_scan_round640_fixes.py, 18개 검사) 신설 — [1] 소스: 새 헬퍼 넷이 정확히 한 번씩 있음을 확인. [2] "
     "되돌림-증명 — main() 판정부에서 _may_precede 가지검사만 제거한(round621 까지의 AST 노드 판정은 유지한) "
     "옛 버전을 dict(vars(CTP)) 독립 사본 네임스페이스에 exec(check_tx_paths.py 파일·실제 모듈 둘 다 안 "
     "건드림), 그 되돌린 main 이 elif 가지 결함 합성 파일을 클린(0건)으로 오판함을 확인. [3] 지금(고쳐진) "
     "실제 CTP.main() 은 같은 합성 파일을 위반(exit 1)으로 정확히 잡고, elif 가지에 rollback() 이 있는 정상 "
     "합성 파일은 과잉탐지 없이 통과함을 확인. [4] 실제 check_tx_paths.py 를 서브프로세스로 실행해 저장소 "
     "전체가 109개 함수·위반 0건으로 끝남을 재확인. 이 수정으로 소스 텍스트가 바뀐 자리를 정적으로 문자열 "
     "매칭하던 round621 자신의 회귀테스트(test_scan_round621_fixes.py) 의 헬퍼 이름·main() 판정부 앵커 두 곳이 "
     "함께 갱신됐다 — round620·621 두 파일 모두 재실행해 각각 14/14·16/16 통과로 충돌 없음 재확인. "
     "check_tx_paths.py 는 app.py/dispatch.py/manage.py 어디에도 import 되지 않는 독립 진단 CLI라 서버 재기동 "
     "대상 아님, BUILD_HASH 영향 없음."),
    ("test_scan_round641_fixes.py",
     "스캔 641라운드 회귀(직접조사, 하위위임 없음) — templates/landing.html '협력사 포털' 카드 설명문이 "
     "실제 렌더에서 '· 정산' 두 글자만 마지막 줄에 홀로 남는 고아문자(orphan) 결함. round640 이 남긴 후보 — "
     "check_orphan_chars.py 의 41개 조판 후보는 소스 정규식뿐이라 실제 렌더 측정이 안 됐다 — 를 따라가 실제 "
     "8771 운영 서버를 브라우저(Chromium)로 직접 열어 이 저장소 자신의 측정 도구(orphan_probe.js "
     "window.__scan/__compare)로 모바일 375px·데스크톱 폭 둘 다 비교했다. 실측 — '입찰 공고 · 원터치 입찰 · "
     "시공 사진 보고 · 정산' 이 static/style.css 의 body{text-wrap:pretty}(전역 상속) 가 켜진 채로도 마지막 "
     "줄에 '· 정산'만 남았다(옆 카드 '…절감 리포트'는 우연히 pretty만으로 충분했을 뿐). "
     "check_orphan_chars.py 가 이 자리를 못 잡은 이유 — orphan_candidates() 는 마지막 어절이 정확히 1글자일 "
     "때만 후보로 보는데 '정산'은 2글자다. 기준을 <=2로 넓히는 것은 하지 않는다 — round124가 이미 겪은 "
     "'자주 우는 늑대'(한글 2글자 명사가 압도적으로 흔해 오탐 폭주, 옆 카드가 그 증거)가 재발하므로 정적 "
     "스캔의 1글자 기준은 의도된 설계로 그대로 둔다. 고침(templates/landing.html, .portal-card의 유일한 "
     "정의 자리 — 전수 grep 확인) — 기존 '.portal-card p{color:#5A7089;font-size:.9rem;line-height:1.6}' "
     "규칙에 text-wrap:balance 를 추가(클래스+타입 선택자라 특이도 0,1,1로 body(0,0,1)를 소스 순서와 무관하게 "
     "항상 이긴다). 이 저장소가 짧은 라벨류(h1~h4·.pt·.k·.lbl·.tag·.pill·label·표 셀)에 이미 쓰는 것과 같은 "
     "처방. 실기동 확인 — 서버 재기동 후(정적 파일 변경) 브라우저로 재확인, __scan() 이 더 이상 이 문구를 "
     "고아문자로 안 봄 + 스크린샷으로 두 줄이 고르게 나뉨을 직접 확인(BUILD_HASH 14462f94→117995c9). "
     "회귀테스트(test_scan_round641_fixes.py, 14개 검사) 신설 — 실제 텍스트 레이아웃(줄바꿈 위치)은 브라우저 "
     "엔진 몫이라 파이썬만으로 재현하지 않는다. 대신 '문자열이 파일에 있는가'가 아니라 진짜 CSS 블록 구조로 "
     "확인한다 — [1] 실제 Flask 앱으로 landing.html 렌더(test_template_js.py와 같은 기법, 스크래치 DB) 후 "
     "임베디드 <style> 추출. [2] 콤마 선택자 목록과 중괄호 블록을 실제로 파싱하는 미니 CSS 파서로 "
     "'.portal-card p' 선택자에 text-wrap:balance가 걸려있음을 확인, 대조군으로 '.portal-card h4'에는 "
     "없음을 확인(파싱이 선택자별로 격리됨을 증명). [3] 되돌림-증명 — 렌더된 CSS 문자열 안에서만(실제 파일은 "
     "안 건드림) ';text-wrap:balance'를 제거한 옛 버전을 재구성해 같은 파서에 통과시키면 text-wrap이 사라지고 "
     "color 등 다른 선언은 그대로임을 확인 — 이 검사가 실제로 있음/없음을 가릴 수 있음을 증명. [4] 렌더된 "
     "실제 HTML에서 문제의 문구가 지금도 정확히 그 모양(마지막 어절 2글자)임을 재확인. [5] "
     "check_orphan_chars.py를 서브프로세스로 실행해 조판 후보가 여전히 41건(CSS 선언 추가는 '>텍스트<' 패턴과 "
     "무관해 후보 수가 안 흔들림)임을 재확인. templates/landing.html 901→906행(+5, 주석 5줄+선언 1개 추가). "
     "static/style.css·app.py·db.py·dispatch.py·manage.py는 무변경."),
    ("test_scan_round642_fixes.py",
     "스캔 642라운드 회귀(직접조사, 하위위임 없음) — templates/dispatch_report.html '2-1. 호출 이력' "
     "요약문의 '가장 가까운 업체' 계산이 거리 0.0km를 '없음'으로 걸러내던 결함. dispatch_calls.dist_km은 "
     "dispatch.py:447에서 round(dkm,1)로 저장되므로 협력사가 현장 반경 50m 이내(대형 단지 등 드물지 않음)면 "
     "정확히 0.0이 된다. 111행(수정 전) `calls|selectattr('dist_km')|map(attribute='dist_km')|list`은 "
     "Jinja2 selectattr()에 테스트를 안 주면 진리값 검사로 동작해(공식문서 확인, 실측: "
     "Template(\"{{ [{'d':0.0}]|selectattr('d')|list }}\").render()=='[]') dist_km=0.0인 호출을 통째로 "
     "제외한다 — 세 줄 뒤(122행, 표의 개별 행)는 `k.dist_km is not none`으로 0과 None을 정확히 구분하는데 "
     "요약문만 그 원칙을 놓쳤다. 같은 파일 195행 자신의 주석('0은 무보증이라는 유효한 값이다 — or는 0도 "
     "걸러 24로 둔갑시킨다')이 이미 경계하던 것과 같은 부류의 함정이 몇 줄 위 selectattr() 자리에는 남아 "
     "있었다. 실제 영향 — 이 보고서는 보험사에 넘기는 '소명을 위한 전체 기록'인데, 호출이 0.0km 하나뿐이면 "
     "거리를 알면서도 '거리 미상'으로, 0.0km와 다른 거리가 섞여 있으면 실제 최솟값이 아닌 더 먼 값을 "
     "'가장 가까운 업체' 거리로 잘못 표시한다. 운영 DB(읽기전용 SELECT) 확인 결과 dist_km=0.0 행은 현재 "
     "0건(전체 74건 중)이라 아직 발현 전이지만 round(dkm,1) 특성상 근접 협력사가 생기면 바로 재현되는 "
     "잠재 결함. 고침(templates/dispatch_report.html, 111행→116행) — `selectattr('dist_km')`를 "
     "`selectattr('dist_km', 'ne', none)`로 바꿔 None만 제외하고 0.0은 남긴다(122행과 같은 구분 원칙). "
     "설명 주석 5줄 추가, 판정 로직은 한 줄만 변경(218→222행, +4). 형제 전수 확인 — templates/ 전체에서 "
     "테스트 없는 단독 selectattr()가 이 자리 말고 더 없음을 확인(다른 selectattr 한 곳은 이미 'equalto' "
     "테스트를 명시해 안전). build_pages.py는 이 템플릿(관리자 전용 보고서, docs/ 공개 사이트 미포함)을 "
     "안 읽으므로 재실행해도 docs/ 해시가 빌드 전후 완전히 동일함을 실측 확인(그래도 표준 절차대로 재실행 "
     "+ test_scan_round306_fixes.py 11/11 재확인 완료). 회귀테스트(test_scan_round642_fixes.py, 23개 검사) "
     "신설 — [1] 소스: 고친 표현 존재+옛 표현 부재+템플릿 전수 형제감사. [2] 단위: 독립 Jinja2 Environment로 "
     "옛/새 표현 5가지 케이스(0.0 단독·0.0+3.2 혼재·None+2.5·None 단독·빈 목록) 실제 렌더 결과를 직접 대조. "
     "[3] 종단: 스크래치 DB+실제 Flask 라우트(GET /report/dispatch/<cid>)+지금 고쳐진 실제 템플릿 파일로 "
     "세 시나리오(0.0 단독, 0.0+3.2 혼재, 전부 None) 재현 — 실제 응답 HTML에서 올바른 값 확인. [4] "
     "되돌리기 — 실제 파일은 무변경, 옛 표현 문자열만 독립 Jinja2 문자열 템플릿으로 재구성해 같은 데이터를 "
     "먹이면 (a)거리 미상 오표시 (b)3.2km 오표시가 실제로 재현됨을 인과관계로 직접 증명. 기존 형제 회귀 "
     "(round64·295·580, 전부 dispatch_report.html을 다루는 테스트)를 재실행해 각각 14/14·27/27·20/20 "
     "그대로 통과 — 테스트 충돌 없음. app.py/db.py/dispatch.py/manage.py는 무변경, static/도 무변경 — "
     "템플릿 파일 하나만 바뀌었으므로 재기동 필요(정적 파일이 BUILD_HASH 산정에 들어감)."),
    ("test_scan_round643_fixes.py",
     "스캔 643라운드 회귀(직접조사, 하위위임 없음) — 피해자 진행조회 화면(templates/track.html, "
     "GET /track/<token>)이 '취소'된 사건에서도 5단계 진행표를 그대로 보여줘 '지금 한창 진행 중'으로 "
     "오인시키던 결함. app.py:5419 CASE_CLOSED=('완료','취소','미수선종결')는 이 셋을 이미 '더 진행되지 "
     "않는 사건'으로 묶어 다루고, 그 정의 바로 위 주석은 '보험사가 취소한 사건이 진행중 건수에 영원히 "
     "남았다'는 실측 사고를 근거로 든다 — 그런데 track_page()는 이 셋 중 '미수선종결' 하나만 no_repair "
     "플래그로 걸러 전용 안내 카드를 보여주고 단계표를 건너뛰며, '취소'는 그 필터가 없어 "
     "smap.get('취소',0)=0으로 떨어져 5단계 진행표의 1단계('접수')가 호박색 '현재' 표시로 켜진 채 "
     "렌더됐다 — 바로 옆 배지는 VICTIM_LABEL['취소']='접수 취소'를 보여줘 한 화면에 '취소되었다'와 "
     "'지금 1/5단계, 한창 진행 중이다'가 동시에 나타난다. 실제 도달 가능성 — 진행조회 링크는 사건 접수 "
     "시점에 자동 발급되는데(app.py:4445 '★★' 주석) 보험사의 사건 취소(api_insurer_case_cancel, "
     "4786행)는 status가 '접수'·'입찰중'일 때만 허용된다(4813행) — 피해자가 이미 링크를 받은 뒤 사건이 "
     "취소되는 순서가 이 기능의 정상 사용 범위 안에 있다. 고침(app.py track_page() render_template 호출, "
     "+15행 — cancelled=(c['status']=='취소') 추가와 그 근거 설명 주석; templates/track.html, 59→78행, "
     "+12행 — {% if no_repair %}와 {% else %}(단계표) 사이에 {% elif cancelled %} 가지를 넣어 no_repair "
     "카드와 같은 모양의 전용 안내 카드('이 접수 건은 취소되었습니다')를 보여주고 단계표는 건너뜀. "
     "smap·VICTIM_LABEL·STAGES 등 기존 계산은 무변경(더는 취소 사건 렌더링에 안 쓰일 뿐 남겨 둬도 무해). "
     "build_pages.py는 이 템플릿(로그인 없는 피해자 전용 링크, docs/ 공개 사이트 미포함)을 안 읽으므로 "
     "재실행해도 docs/에 track.html 자체가 없음을 확인(표준 절차대로 재실행 + test_scan_round306_fixes.py "
     "11/11 재확인 완료, docs/ 파일 목록·해시 완전 동일). 회귀테스트(test_scan_round643_fixes.py, 21개 "
     "검사) 신설 — [1] 소스: track_page() 함수 슬라이스 안에 새 cancelled= 인자, 템플릿에 새 "
     "{% elif cancelled %} 가지와 안내 문구가 정확히 한 번씩, CASE_CLOSED 전제 확인. [2] 단위: "
     "templates/track.html에서 실제 if/elif/else 블록 원문을 그대로 잘라내(손으로 재입력하지 않음) "
     "독립 Jinja2 템플릿으로 실제 상태값 3가지(취소·미수선종결·시공중) 렌더 차이를 직접 실행으로 증명. "
     "[3] 종단: 스크래치 DB+실제 Flask 라우트(GET /track/<token>)+지금 고쳐진 실제 템플릿 파일로 세 사건 "
     "재현 — 취소 사건은 안내 카드만(단계표 없음), 미수선종결·시공중은 기존 그대로(회귀 없음). [4] "
     "되돌리기 — 실제 파일은 무변경, [2]에서 잘라낸 실제 블록에서 {% elif cancelled %} 가지만 제거해 "
     "옛 구조를 재구성(손으로 재입력하지 않음)한 뒤 (a)와 같은 실제 값(cur_stage=0, status='접수 취소')을 "
     "넣으면 1단계가 호박색 '현재'로 켜진 진행표가 '접수 취소' 배지와 함께 그대로 나오는 모순된 화면이 "
     "실제로 재현됨을 인과관계로 직접 증명. app.py는 track_page() 함수 내부(주석 위주)만 변경, db.py/ "
     "dispatch.py/manage.py는 무변경 — 정적 파일(templates/track.html)이 바뀌었으므로 재기동 필요"
     "(BUILD_HASH 산정에 들어감)."),
    ("test_scan_round644_fixes.py",
     "스캔 644라운드 회귀(직접조사, 하위위임 없음) — 시행사(협력사) 포털 stTag()의 '시공중' 태그 색이 "
     "보험사 포털·운영 콘솔과 어긋나 있던 결함. 상태값→색상 매핑은 이 저장소에 사실상 세 형제로 존재한다 "
     "(templates/insurer_portal.html stTag(s) · templates/partner_portal.html stTag(s) · static/admin.js "
     "statusPill(s)). insurer_portal.html 327~328행 주석이 '두 stTag는 매핑을 동기화해야 한다'는 원칙을 "
     "이미 명시하고(라운드75가 '취소' 색을 두 stTag에 동시에 맞춘 이력) 있는데, 세 매핑의 겹치는 상태값 "
     "17개를 전수 대조하면 '시공중' 하나만 partner_portal.html이 'blue', 나머지 둘(insurer_portal.html·"
     "admin.js)은 'green'이었다 — 다른 16개는 세 곳 모두 완전히 일치. '시공중'은 낙찰 직후 가장 흔한 "
     "상태값이고 caseDetail() 모달 헤더(partner_portal.html 360·395행, insurer_portal.html 834행과 완전히 "
     "같은 `<h3>${esc(c.case_no)} ${stTag(c.status)}</h3>` 패턴)가 그 값을 그대로 stTag()에 넘겨, 같은 "
     "사건을 시행사가 열면 파란 '시공중', 보험사가 열면 초록 '시공중'으로 보였다. 고침 — "
     "templates/partner_portal.html stTag()의 '시공중'을 'blue'→'green'으로 바꿔 다수 의견(2/3, 운영 "
     "콘솔 포함)에 맞춘다(같은 파일 RENDER.sites 카드의 별도 자기완결적 인라인 색상 조건문은 형제 불일치 "
     "증거가 없어 이번엔 손대지 않음 — 다음 라운드 참고용으로만 남김). 회귀테스트(test_scan_round644_"
     "fixes.py, 24개 검사) 신설 — [1] 소스: 세 매핑에서 '시공중' 값을 직접 대조해 셋 다 'green'으로 "
     "일치함을 확인, '시공중' 이외 공통 상태값은 세 매핑이 여전히 전부 일치함도 함께 확인(회귀 없음). "
     "[2] 단위: 세 함수 정의를 파일에서 그대로 잘라내(손으로 재입력하지 않음) Node.js로 직접 실행해 "
     "stTag('시공중')·statusPill('시공중') 결과의 색상 클래스가 셋 다 green으로 일치함을 실측 증명. "
     "[3] 되돌리기 — 실제 파일은 무변경, [2]에서 잘라낸 (고친) partner stTag 소스 문자열 안에서만 "
     "'시공중':'green'을 다시 'blue'로 치환한 옛 버전을 독립 Node 스크립트로 만들어, 그 옛 버전이 실제로 "
     "insurer_portal.html·admin.js와 다른 색(blue vs green)을 냈음을 재현 실측 — 위 [2]의 지금 결과와 "
     "정반대여서 이번 수정이 실제로 이 불일치를 없앤 것임을 인과관계로 증명. [4] 종단 — 실제 Flask "
     "템플릿 렌더(로그인 세션 없이 render_template 직접 호출, test_template_js.py와 같은 기법)로 "
     "partner_portal.html·insurer_portal.html을 그대로 그려 서버가 실제로 내보내는 HTML 안에 고친 매핑이 "
     "살아 있는지 확인. build_pages.py 재실행 + test_scan_round306_fixes.py 11/11 재확인 완료(docs/는 "
     "landing.html·legal.html만 반영하므로 partner_portal.html 변경은 docs/에 영향 없음을 함께 확인) — "
     "정적 파일(templates/partner_portal.html)이 바뀌었으므로 재기동 필요(BUILD_HASH 산정에 들어감). "
     "app.py/db.py/dispatch.py/manage.py는 무변경."),
    ("test_scan_round645_fixes.py",
     "스캔 645라운드 회귀(직접조사, 하위위임 없음) — 시행사(협력사) 포털 '시공 현장' 카드"
     "(templates/partner_portal.html RENDER.sites, ~1495행)가 stTag()와 무관한 별도의 "
     "자기완결 3항 색상 조건식을 갖고 있던 결함. 라운드644가 이 파일 stTag()의 '시공중'만 "
     "'blue'였던(형제 insurer_portal.html stTag·admin.js statusPill은 둘 다 'green') 드리프트를 "
     "고치면서, 같은 파일 RENDER.sites 카드(1511행 부근)의 별도 인라인 조건문은 'stTag()와 무관한 "
     "자기완결 조건식이라 형제 불일치 증거가 없다'며 의도적으로 안 건드리고 다음 라운드 후보로만 "
     "남겼다. 실측 — 그 조건식(c.status==='시공중'?'blue':(c.status==='완료보고지연'?'red':"
     "(c.status==='검수대기'?'amber':'green')))은 시공중·완료보고지연·검수대기 세 값만 따로 "
     "처리하고 나머지는 전부 'green'으로 뭉갠다. 그런데 이 카드가 그리는 my_cases는 app.py(약 "
     "5239행) 쿼리가 status IN ('시공중','완료보고지연','검수대기','정산진행','완료')로 다섯 값을 "
     "전부 내려주므로, stTag()의 정답(시공중=green·완료=gray)과 대조하면 '시공중'(여기선 blue)과 "
     "'완료'(여기선 default green) 둘 다 실제로 어긋나 있었다 — '완료' 쪽은 라운드644도 못 본 새 "
     "발견. 고침(templates/partner_portal.html, 1511행) — 3항 조건식을 지우고 같은 파일에 이미 "
     "있는(라운드644가 형제와 동기화해 둔) stTag(c.status) 호출로 교체(매핑을 한 곳에만 유지, "
     "esc() 중복 처리도 함께 제거) — 2853→2859줄(+6, 대부분 근거 주석). 회귀테스트"
     "(test_scan_round645_fixes.py, 21개 검사) 신설 — [1] 소스: RENDER.sites 함수 몸통에서 옛 "
     "3항 조건식이 사라지고 stTag(c.status) 호출로 바뀌었음을 확인. [2] 소스: stTag() 매핑 자체가 "
     "시공중=green·완료=gray를 유지함(전제) 확인. [3] 단위: stTag()를 파일에서 그대로 잘라내(손으로 "
     "재입력하지 않음) Node.js로 실행해 my_cases가 실제로 낼 수 있는 5개 상태값 전부에서 색상 "
     "클래스가 정답과 일치함을 실측. [4] 되돌리기 — 실제 파일은 무변경, 지운 옛 3항 조건식을 메모리 "
     "문자열로만 재구성해 Node로 실행, 옛 코드였다면 시공중=blue·완료=green이 나와 stTag()의 정답과 "
     "실제로 갈렸음을(결함 2개 모두) 인과관계로 재현 증명, 나머지 3개 상태값(완료보고지연·검수대기·"
     "정산진행)은 우연히 일치했었다는 것도 함께 확인. [5] 종단 — 실제 Flask 템플릿 렌더(로그인 "
     "세션 없이, test_template_js.py와 같은 기법)로 partner_portal.html을 그대로 그려 서버가 "
     "실제로 내보내는 HTML 안에 옛 조건식이 없고 새 호출이 살아 있는지 확인. build_pages.py 재실행 "
     "+ test_scan_round306_fixes.py 11/11 재확인 완료(docs/는 landing.html·legal.html만 반영하므로 "
     "partner_portal.html 변경은 영향 없음을 함께 확인), test_template_js.py도 재확인(9/9, "
     "partner_portal.html 인라인 JS 2개 정상 파싱) — 정적 파일(templates/partner_portal.html)이 "
     "바뀌었으므로 재기동 필요(BUILD_HASH 산정에 들어감). app.py/db.py/dispatch.py/manage.py는 "
     "무변경."),
    ("test_scan_round646_fixes.py",
     "스캔 646라운드 회귀(직접조사, 하위위임 없음) — dispatch.py:_setting_int()가 app.py의 "
     "동명 형제 함수와 다르게 동작하던 결함. settings 정수값을 읽는 이 헬퍼는 순환 임포트를 "
     "피하려 app.py(4112행)·dispatch.py(78행) 두 곳에 각자 존재하는데, 이 저장소는 이런 형제 "
     "함수를 이미 두 번(_like_escape·_norm_dot) '반드시 같은 규칙을 유지한다'는 동기화 주석과 "
     "함께 다뤄 왔다. _setting_int()에는 그 주석이 전혀 없었고 실제로 동작이 갈라져 있었다 — "
     "app.py 판은 저장값이 [lo,hi] 범위 밖이면 조용히 default로 되돌리는데(함수 자신의 "
     "독스트링이 명시하는 계약, round485가 이미 'inf'류 OverflowError까지 방어), dispatch.py "
     "판은 max(lo, min(hi, v))로 경계값에 그대로 밀어 넣었다(clamp) — 아무도 설정한 적 없는 "
     "경계값(dispatch_minutes라면 240분)이 조용히 운영값이 된다. 파싱도 app.py 판은 "
     "int(float(x))라 '30.0'류 문자열을 허용하는데 dispatch.py 판은 int(str(x))라 그런 값이 "
     "오면 ValueError로 default에 떨어져 있었다. 지금 유일한 저장 경로(api_settings_set의 "
     "RANGES 검증)는 저장 시점에 이미 이 폭을 강제해 정상 화면 조작으로는 재현되지 않지만, 그 "
     "검증을 거치지 않는 경로(수기 DB 수정 등)로 값이 깨지면 형제와 다른 결과를 낸다. 고침 — "
     "dispatch.py:_setting_int()(78행)를 app.py 판과 동일한 계약(범위 밖은 default, "
     "int(float(x)) 파싱, OverflowError 포함 예외 처리)으로 맞추고 동기화 주석을 남김 — "
     "1432→1453줄(+21, 대부분 근거 주석). 회귀테스트(test_scan_round646_fixes.py, 18개 검사) "
     "신설 — [1] 소스: 실행문에서 옛 clamp 표현이 사라지고 '범위 밖이면 default' 계약이 "
     "실제로 담겼음을 확인(주석 속 인용과 실행문을 구분). [2] 단위: 스크래치 DB에 범위 밖 값을 "
     "직접 넣고(dispatch_minutes=999, dispatch_fanout=0, dispatch_max_round=50) 실제 dispatch "
     "모듈로 호출 — 경계값이 아니라 기본값(30·20·3)을 돌려줌을 실측, '45.0' 같은 소수점 문자열 "
     "파싱과 정상범위 값(회귀 없음)도 함께 확인. [3] 되돌리기 — 실제 파일은 무변경, 메모리 "
     "안에서만 옛 clamp 버전을 재구성해 같은 입력(999)이 실제로 경계값 240을 냄을 인과관계로 "
     "재현 증명(이 테스트가 회귀를 잡아낼 힘이 있음을 증명). [4] 형제일치: app.py._setting_int()"
     "와 dispatch.py._setting_int()가 이제 같은 깨진 입력에 완전히 같은 결과(30)를 냄을 실측 — "
     "정적 파일(templates/static) 무변경이라 재기동·BUILD_HASH 변경 불필요, dispatch.py만 변경."),
    ("test_scan_round647_fixes.py",
     "스캔 647라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py BAD_DOMAIN 목록의 "
     "'naver.com.'(꼬리점) 이 절대 못 맞는 죽은 항목이던 결함. round514가 BAD_LOCAL에서 "
     "'webmaster@example'(local part 리스트인데 '@'가 있어 절대 매치 불가)를 잡은 뒤로 이 "
     "세션이 같은 클래스('이 항목이 실제로 한 번이라도 맞을 수 있는가')를 BAD_DOMAIN 26개 "
     "전체에 훑어, 'naver.com.' 하나만 꼬리에 마침표가 붙어 있음을 발견했다. 이중으로 못 "
     "맞는다 — EMAIL_RE(80행)의 도메인부가 `[A-Za-z]{2,}`로 끝나 매치 자체가 마침표로 끝날 "
     "수 없고, 설령 뚫려도 pick_emails()의 `e.strip(\".\")`이 한 번 더 지운다. 확산 범위 — "
     "clean_collected_emails.py 24행이 `from collect_emails import BAD_DOMAIN`으로 같은 "
     "튜플을 그대로 쓰므로(is_junk()), 이 죽은 항목은 수집 시점과 사후 정리 시점 양쪽에서 "
     "동시에 죽어 있었다 — 회사 자체 도메인 페이지에 네이버 지도·위젯이 남긴 "
     "'…@naver.com' 류 기본 문의주소가 실제 업체 연락처인 양 수집·보존될 수 있었다(옆 "
     "주석이 명시하는 '보내면 엉뚱한 회사에 간다'는 상황). 고침 — collect_emails.py "
     "118~127행 BAD_DOMAIN의 'naver.com.' 꼬리점 제거 → 'naver.com'(오타만 제거, 값 추가는 "
     "아님) + 근거 주석 10줄, 438→448줄(+10). import로 튜플을 공유하는 "
     "clean_collected_emails.py는 무변경(공유 지점 하나만 고치면 두 소비자 모두 고쳐짐). "
     "이 고침은 naver.com 전체를 통째로 막는다(목록의 다른 wholesale 차단·googleapis.com "
     "등과 같은 방식) — 새 정책이 아니라 기존에 이미 있던 항목의 오타 제거다. "
     "회귀테스트(test_scan_round647_fixes.py, 13개 검사) 신설 — [1] 소스: ast로 BAD_DOMAIN "
     "리터럴을 파싱(주석 속 인용부호에 오염되지 않도록)해 'naver.com.'이 없고 'naver.com'이 "
     "있음을 확인, 파싱값이 실제 런타임 CE.BAD_DOMAIN과 일치함도 확인. [2] 구조: EMAIL_RE가 "
     "본문에 마침표가 뒤따라도 그 앞에서 매치를 끊음을 정규식 실행으로 실측. [3] 단위: 실제 "
     "회사 주소(daehan-guardrail.co.kr)와 네이버 위젯 주소가 나란히 있는 HTML 샘플로 "
     "pick_emails()가 회사 주소만 남기고 is_junk()도 네이버 주소를 정리 대상으로 잡음을 "
     "확인(회사 주소는 정상으로 남음, 회귀 없음). [4] 되돌리기 — 실제 파일은 무변경, "
     "CE.BAD_DOMAIN·CC.BAD_DOMAIN 두 모듈 속성만 메모리에서 옛(꼬리점) 값으로 잠깐 바꿔 "
     "같은 시나리오를 다시 돌리면 pick_emails()·is_junk() 둘 다 네이버 주소를 놓침을 "
     "인과관계로 재현 증명, finally로 정확히 복원됐음도 확인. 관련 회귀(round218·267·271·"
     "299·420·514·517·639, 전부 collect_emails.py/clean_collected_emails.py를 다룸) 전부 "
     "단독 재확인 완료(충돌 없음) — 정적 파일(templates/static) 무변경이라 재기동·"
     "BUILD_HASH 변경 불필요, app.py/db.py/dispatch.py/manage.py도 무변경."),
    ("test_scan_round648_fixes.py",
     "스캔 648라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py refuses_collection()이 "
     "REFUSE_MARKERS(§50-2 수집거부 문구 목록) 8개 중 유일한 비한글 항목 'email collection "
     "denial'을 대소문자가 다르면 못 잡던 결함. round514(BAD_LOCAL 죽은 항목)·round647"
     "(BAD_DOMAIN 죽은 항목)이 이 파일의 리터럴 목록을 '이 항목이 실제로 맞을 수 있는가' "
     "관점으로 훑은 데 이어, 이번엔 REFUSE_MARKERS를 같은 관점으로 훑었다. flat = "
     "re.sub(공백제거, re.sub(태그제거, html)) 과 마커 비교 양쪽 다 .lower()가 전혀 없어 "
     "대소문자를 그대로 비교했다 — 한글 7개 항목은 대소문자 개념이 없어 무관하지만, 영문 "
     "1개는 REFUSE_MARKERS에 이미 소문자로 적혀 있어 실제 사이트가 'Email Collection "
     "Denial'·'EMAIL COLLECTION DENIAL'처럼 다르게 표기하면(사람이 쓰는 영문 안내문이라 "
     "표기가 갈릴 수 있다) 정확히 이 문구를 명시한 사이트조차 못 걸러 그대로 스크래핑했다 "
     "(실측: 대문자 샘플로 재현). 이 파일 자신의 존재 이유(모듈 docstring, 정보통신망법 "
     "§50-2 — 수집거부 의사가 명시된 페이지에서 자동 수집 금지)를 정면으로 벗어나는 결함. "
     "고침 — refuses_collection()의 flat과 마커 비교 양쪽에 .lower() 추가, 448→456줄"
     "(+8, 대부분 근거 주석). 한글 마커는 .lower()가 완전한 무연산이라 회귀 위험 없음. "
     "회귀테스트(test_scan_round648_fixes.py, 14개 검사) 신설 — [1] 소스: ast로 함수 본문을 "
     "파싱해 실제 .lower() 호출(Attribute 노드)이 정확히 2번임을 확인(이 결함 자신의 근거"
     "주석이 '.lower()' 문구를 인용해 순수 텍스트 카운트는 3이 나옴을 먼저 보이고, "
     "round647처럼 ast로 그 오염을 걷어냄). [2] 단위: 대문자·Title케이스(<span>으로 끊긴 "
     "경우 포함) 영문 마커가 이제 탐지됨, 기존 소문자 그대로·태그로 끊긴 한글 마커"
     "(round267)는 회귀 없이 그대로 동작, 마커 없는 평범한 한/영 소개문은 여전히 False"
     "(과잉탐지 아님)임을 확인. [3] 되돌리기 — 실제 파일은 무변경, 고치기 전 소스를 "
     "REFUSE_MARKERS만 CE에서 공유해 독립 이름공간에 exec(안전원칙 3항 함수단위 되돌리기, "
     "모듈 몽키패치 없음) — 같은 대문자·Title케이스 샘플이 되돌린 코드에서는 실제로 False를 "
     "냄을 인과관계로 재현, 되돌린 코드도 소문자 그대로인 마커·한글 마커는 원래부터 잡았음을 "
     "대조해 이번 회귀가 '대소문자'에만 정확히 좁혀짐을 확인(round267 결함과는 별개). 첫 "
     "실행 14/14 통과 — 정적 파일(templates/static) 무변경이라 재기동·BUILD_HASH 변경 "
     "불필요, app.py/db.py/dispatch.py/manage.py도 무변경."),
    ("test_scan_round649_fixes.py",
     "스캔 649라운드 회귀(직접조사, 하위위임 없음) — geocode_fill.py _region_ok()의 첫 갈래 "
     "`if w & g: return True`가 구 이름만 겹치면 시도(광역시/도)는 아예 안 보고 곧장 "
     "'같은 동네'로 통과시키던 결함. round512가 같은 파일 _gu_set()의 '대구' 결함을 고친 "
     "이후 처음으로 이 파일에 다시 대 본 감사인데, 이번엔 정반대 방향 — '중구·동구·서구· "
     "남구·북구'는 서울·부산·대구·인천·광주·대전·울산이 나눠 쓰는 흔한 이름이라, 구 이름이 "
     "겹쳐도 시도가 다르면 완전히 다른 도시다(서울 중구 ≠ 부산 중구). 이 함수의 둘째 갈래"
     "(시도가 겹치는데 구가 다를 때의 round159 정보비대칭 구제)는 이미 시도를 검사하는데, "
     "그보다 먼저 걸리는 첫째 갈래(구가 직접 겹칠 때)엔 시도 검사가 아예 없었다 — round159의 "
     "교훈이 같은 함수 형제 갈래로 전파되지 않은 상태. 실측: 고치기 전 코드로 서울 중구·부산 "
     "중구, 대전 동구·광주 동구, 인천 서구·대구 서구, 울산 남구·부산 남구 4조합 전부 "
     "'같은 동네'로 오판했다. round512(못 채움 — 안전 방향 실패)와 달리 이번은 **틀린 좌표를 "
     "채워 버리는**(위험 방향 실패) 더 심각한 결함 — 이 파일 자신의 모듈 docstring이 명시한 "
     "안전 원칙('엉뚱한 좌표는 없느니만 못하다 — 배차가 조용히 틀린 업체를 부른다')을 정면으로 "
     "벗어난다. 고침 — `if w & g:` 분기 안에 시도 정보가 양쪽 다 있고 서로 안 겹칠 때만 거르는 "
     "검사 추가(한쪽만 시도 정보가 없는 정보 비대칭은 round159와 같은 원칙으로 그대로 통과). "
     "새 헬퍼·새 상수 없이 기존 _sido_set() 재사용(ponytail 원칙, round512와 동일). "
     "340→361줄(+21, 대부분 근거 주석 — _region_ok() 자체 수정 + demo() 회귀 케이스 추가). "
     "회귀테스트(test_scan_round649_fixes.py, 28개 검사) "
     "신설 — [1] 소스: ast로 함수 본문에서 새 시도충돌 검사가 정확히 1번, round159 로직이 "
     "그대로 남아있음을 확인. [2] 단위: 기존 자체점검 12건(demo()와 동일, round512분 포함) "
     "회귀 없음 + 신규 충돌 4조합이 이제 전부 거름 + 대조군(같은 시도·같은 구는 여전히 통과) "
     "2건. [3] 실행 — 실제 fill()을 스크래치 DB + 스텁 ADDR.search(서울 중구 협력사 검색에 "
     "부산 중구 좌표를 내주는 가짜 카카오 응답)로 끝까지 돌려, 고친 코드에서는 그 좌표가 "
     "저장되지 않고 geo_src='시도실패'로 표시됨을 확인. [4] 되돌림-증명 — _region_ok()를 "
     "이 라운드 이전 구현(시도충돌 검사 없음)으로 런타임에 되돌려(파일은 무변경, 순수함수라 "
     "안전) 같은 시나리오를 새 협력사 행으로 다시 돌리면, 실제 fill() 실행에서 부산 좌표가 "
     "서울 협력사에 geo_src='주소검색'(확인됨)으로 잘못 저장되는 옛 결함이 재현됨을 확인 "
     "(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명). 첫 실행 28/28 통과 — 정적 파일"
     "(templates/static) 무변경이라 재기동·BUILD_HASH 변경 불필요, app.py/db.py/dispatch.py/"
     "manage.py도 무변경(geocode_fill.py는 운영 서버 app.py가 import하지 않는 독립 CLI 도구)."),
    ("test_scan_round650_fixes.py",
     "스캔 650라운드 회귀(직접조사, 하위위임 없음) — geocode_fill.py _sido_set()이 쓰는 "
     "_SIDO 정규식이 경계 없이 부분일치해, '세종로'·'세종대로'(서울 도로명) 안의 '세종'을 "
     "세종특별자치시로 오판하던 결함. round649 검증 중 오케스트레이팅 세션이 남긴 후속 "
     "후보. 세종시는 '구' 자체가 없는 특별자치시라 _region_ok() 맨 아래 시도-only 갈래를 "
     "거의 항상 타는데, 그 갈래가 '세종대로'의 가짜 '세종'과 진짜 세종시의 '세종'을 "
     "겹치는 것으로 잘못 판정한다. 실측: 고치기 전 코드로 "
     "_region_ok(\"서울 중구 세종대로 110\", \"세종특별자치시 반곡동 108\") == True "
     "(약 120km 떨어진 다른 도시). '경기장길'의 '경기'도 같은 함정(경기도로 오판). "
     "이 파일 모듈 docstring의 안전 원칙('엉뚱한 좌표는 없느니만 못하다')을 정면으로 "
     "벗어난다 — round649와 같은 위험 방향(못 채움이 아니라 틀리게 채움) 실패이지만 "
     "원인은 다른 함수(_region_ok 자체가 아니라 그 하위 의존 _sido_set/_SIDO). "
     "고침 — _SIDO 정규식에 lookahead 경계 추가: 시도 이름 뒤에 문자열 끝·비한글 문자·"
     "행정단위 접미('시'·'도'·'특별'·'광역'·'통합')·또 다른 시도 이름(기존 결합 표기 "
     "지원 유지)이 이어질 때만 인정. 새 헬퍼·새 상수 없이 기존 _SIDO 정규식 자체를 "
     "넓혔다(ponytail 원칙, round512·649와 동일). 361→392줄(+31, 대부분 근거 주석 + "
     "demo() 회귀 케이스 3건). "
     "회귀테스트(test_scan_round650_fixes.py, 15개 검사) 신설 — [1] 소스: _SIDO 정의에 "
     "lookahead와 라운드650 표식 확인. [2] 단위: geocode_fill.demo() 전체(round159·512·649 "
     "포함) 회귀 없음 + 신규 discriminating 3케이스(세종대로·세종로·경기장길) + 대조군 "
     "2건(진짜 세종시끼리·같은 세종대로끼리는 여전히 통과). [3] 실행 — 실제 fill()을 "
     "스크래치 DB + 스텁 ADDR.search(서울 '세종대로' 협력사 검색에 진짜 세종시 좌표를 "
     "내주는 가짜 카카오 응답)로 끝까지 돌려, 고친 코드에서는 그 좌표가 저장되지 않고 "
     "geo_src='시도실패'로 표시됨을 확인. [4] 되돌림-증명 — GF._SIDO를 이 라운드 이전 "
     "정규식(경계 없음)으로 런타임에 되돌려(파일은 무변경, 컴파일된 패턴 객체 교체라 "
     "안전) 같은 시나리오를 새 협력사 행으로 다시 돌리면, 실제 fill() 실행에서 세종시 "
     "좌표가 서울 협력사에 geo_src='주소검색'(확인됨)으로 잘못 저장되는 옛 결함이 재현됨을 "
     "확인(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명). 첫 실행 15/15 통과 — 정적 "
     "파일(templates/static) 무변경이라 재기동·BUILD_HASH 변경 불필요, app.py/db.py/"
     "dispatch.py/manage.py도 무변경(geocode_fill.py는 운영 서버 app.py가 import하지 않는 "
     "독립 CLI 도구)."),
    ("test_scan_round651_fixes.py",
     "스캔 651라운드 회귀(직접조사, 하위위임 없음) — compliance.check_direct_contract()가 "
     "amount/related_amount에 float('inf')/float('-inf')/float('nan')를 받으면 "
     "int(amount or 0)에서 OverflowError(inf) 또는 ValueError(nan, 'cannot convert float "
     "NaN to integer')를 그대로 던지던 결함. 형제(app.py _setting_int 라운드485, "
     "_ai_threshold 라운드631)가 이미 겪고 고친 'int(float(x))/int(x)가 inf·nan에서 "
     "ValueError가 아니라 OverflowError/ValueError를 던진다'는 같은 함정을 compliance.py "
     "에서도 재현. repair_estimate.py/addr_search.py/photo_ai.py는 동적 퍼징(경계값 "
     "min/max/이상/이하 전수, choice 전수, None/int/list/nan/inf 등)으로 이미 탄탄함을 "
     "먼저 실측 확인했고, compliance.check_direct_contract()·gate() 두 곳만 이 자리에서 "
     "실제로 크래시함을 직접 재현했다. 리치어빌리티(정직하게 밝힘) — 현재 이 두 함수에 "
     "amount/related_amount를 흘려보내는 모든 실제 경로(bids.amount·cases.est_price/"
     "award_amount/low_price·field_agreements.field_amount 전부 parse_money() 종착, "
     "gate()의 두 query-string 오버라이드는 .isdigit() 가드)를 전수 대조한 결과 오늘 "
     "당장 이 크래시에 닿는 실제 호출부는 없다 — 그래도 이 파일 자신의 원칙('애매하면 "
     "도급 불가로 낸다')과 '이 관문이 뚫리면 형사 리스크가 열린다'는 자체 서술을 감안해, "
     "db·app을 모르는 공용 순수함수가 호출부의 사전 검증에 기대지 않도록 예방적으로 "
     "막는다(485·631과 같은 성격의 방어적 강화). 고침 — check_direct_contract()의 "
     "amt=int(amount or 0)/rel=int(related_amount or 0)와 gate()의 동일 int() 변환을 "
     "각각 try/except(TypeError, ValueError, OverflowError)로 감싸, 실패 시 0원으로 "
     "위장해 통과시키는 대신 이 파일에 이미 있는 kind=='unknown' 분기와 같은 모양(code="
     "NO_UNKNOWN, ok=False)으로 되돌린다. compliance.py 491→517줄(+26, 두 곳). 회귀테스트 "
     "(test_scan_round651_fixes.py, 20개 검사) 신설 — [1] 되돌림-증명(exec, 원본 파일은 "
     "안 건드림) — 가드 없는 옛 코드가 amount=inf에서 실제 OverflowError, nan에서 실제 "
     "ValueError를 던짐을 먼저 재현. [2] 수정본이 inf/-inf/nan(amount·related_amount "
     "양쪽)에서 크래시 없이 ok=False·code=NO_UNKNOWN·amount=None(0원으로 위장 안 함)을 "
     "돌려줌을 확인. [3] 회귀 없음 — 정상 정수·숫자문자열·기존 배제업종/금액초과/카테고리 "
     "None 경로가 전부 기존과 동일하게 동작함을 확인. gate()의 수정은 record_gate()의 "
     "dict.get() 기반 다운스트림 소비(INSERT 바인딩·_gate_alert() 전부 .get() 사용)와 "
     "이미 있는 test_scan_round57_fixes.py의 gate() 소스 대조(코드 개수 c[\"award_amount\"] "
     "or c[\"low_price\"] or c[\"est_price\"] or 0 존재 확인)까지 개별 재실행해 충돌 "
     "없음을 확인(둘 다 그대로 통과). app.py는 미변경(compliance.py만 변경)이라 BUILD_HASH "
     "불변, app.py가 compliance를 import하므로 서버 재기동은 필요."),
    ("test_scan_round652_fixes.py",
     "스캔 652라운드 회귀(직접조사, 하위위임 없음) — app.py 전역에서 'JSON 본문 값을 "
     "가공 없이 그대로 int()로 바꾸는' 자리 11곳이 OverflowError(1e400류 → json 파서가 "
     "float('inf')로 성공 파싱 → int(그 값)이 ValueError가 아니라 OverflowError)를 못 "
     "잡던 결함. 형제(app.py _setting_int 라운드485, _ai_threshold·api_ai_threshold_set "
     "라운드631, compliance.check_direct_contract 라운드651)와 같은 함정이 이 세션 네 "
     "번째로 재발한 사례군 — round592는 api_admin_notifications_read의 '자릿수만 큰 "
     "정수 문자열' 유입구만 막았고 자기 자신의 except 튜플에도 OverflowError는 없었다. "
     "app.py 전체에서 int() 변환을 감싸는 except(TypeError,ValueError) 계열 튜플 30여 "
     "곳을 전수 대조 — request.args.get() 기반(항상 문자열, int('1e400')는 ValueError일 "
     "뿐이라 애초에 안전)·str()로 먼저 감싼 값(int('inf')도 ValueError)·float() 변환+한반도 "
     "범위검사(inf·nan 모두 범위밖으로 안전 처리, _picked_coords 실측 확인)는 전부 "
     "안전함을 확인하고, 'JSON 본문 값을 가공 없이 int()에 직접 넘기고 OverflowError가 "
     "빠진' 11곳만 추렸다: ①api_create_application(POST /api/applications, 무인증 "
     "공개폼!)·②api_application_create(POST /api/applications/manual, admin)의 "
     "staff_count 형제쌍, ③api_partner_bulk_credentials·⑤api_settlements_paid_bulk·"
     "⑦api_outbox_send_selected·⑪api_partner_invite의 ids 리스트 4형제, "
     "④api_case_edit의 warranty_months, ⑥_attach_defect_photos(내부 헬퍼)의 photo_id, "
     "⑧api_admin_notifications_read의 id(round592 자신의 후속 결함), "
     "⑨api_dispatch_assign의 partner_id, ⑩api_happy_call_add의 score. ①은 로그인 없이 "
     "누구나 트리거 가능해 가장 심각하고, ⑥은 단순 400이 아니라 '사진 1장의 잘못된 "
     "photo_id가 같은 요청의 나머지 정상 사진 첨부까지 통째로 유실시킨다'는 점에서 "
     "증상이 다르다(round596 전역핸들러 안전망 밖 — 라우트가 아니라 순수 함수라 그 "
     "핸들러를 거치지 않고 그대로 위로 샌다). 고침 — 11곳 전부 except 튜플에 "
     "OverflowError를 추가(형제들과 바이트 단위로 같은 처방, 새 메커니즘·새 헬퍼 없음). "
     "app.py 22358→22396줄(+38, 11곳 각각 1~7행의 근거 주석+except 튜플 확장만). "
     "회귀테스트(test_scan_round652_fixes.py, 41개 검사) 신설 — [1] 소스: 11곳 전부 "
     "자기 함수 본문 안에 새 except 튜플 확인. [2] 실행 — 스크래치 DB+실제 Flask 앱, "
     "최고관리자 세션 하나로 11곳 전부(_admin_rank()가 최소등급만 보므로 하위·중간관리자 "
     "라우트도 그대로 통과함을 실측)에 1e400류를 실제 HTTP/직접 호출로 흘려보내 500이 "
     "아니라 400(또는 정상 200)이고, round596 전역핸들러의 범용 문구(code=BAD_INPUT) "
     "대신 그 자리 자신의 구체적 문구·동작이 나옴을 확인. [3] 회귀없음 — 정상 "
     "staff_count·warranty_months 값은 기존과 동일하게 동작. [4] 되돌리기-증명(대표 "
     "2곳, round414·565·631 패턴) — api_dispatch_assign(view_functions 치환)과 "
     "_attach_defect_photos(모듈 속성 치환)를 옛(취약) except 튜플로 되돌린 사본을 "
     "exec로 격리 재구성해, 옛 코드가 실제로 전역핸들러 범용문구로 새거나(라우트) "
     "OverflowError를 그대로 던지는지(헬퍼) 실행으로 재현한 뒤 즉시 원복 — 실제 app.py "
     "파일은 이 과정 전체에서 한 바이트도 안 바뀜을 마지막에 재확인. 첫 실행 41/41 통과. "
     "app.py만 변경이라 BUILD_HASH 로테이션 대상(재기동 필요), db.py/dispatch.py/"
     "manage.py/compliance.py/templates/static은 미변경."),
    ("test_scan_round653_fixes.py",
     "스캔 653라운드 회귀(직접조사, 하위위임 없음) — geocode_fill.py _sido_set()이 전남·"
     "전북·충남·충북·경남·경북 여섯 도의 정식 명칭('경상북도' 등)을 못 알아봐, round649가 "
     "막았던 '구 이름이 같아도 시도가 다르면 다른 동네' 검사를 건너뛰게 만들던 결함 — "
     "round649/650이 이미 두 번 고친 같은 함수(_region_ok/_sido_set)의 세 번째 독립된 "
     "구멍(원인은 매번 달랐다: 649=구만 보고 시도 무시, 650=도로명 속 부분일치, 653=정식 "
     "명칭 미인식). _SIDO 정규식이 축약형만 담아 정식 명칭 쪽 _sido_set()이 빈 집합을 "
     "돌려주면 _region_ok()의 'if sw and sg and not (sw & sg)' 검사가 sw=falsy로 그냥 "
     "건너뛰어진다 — 실측: _region_ok('경상북도 포항시 남구 대잠동', '부산광역시 남구 "
     "대연동')이 True(포항·부산은 100km+ 떨어진 완전히 다른 도시, '남구'라는 흔한 구 "
     "이름만 겹침). 운영 DB 실측(읽기전용) — partners.address 73건이 이미 이 여섯 도의 "
     "정식 명칭을 쓰고, cases는 region이 비어 있는데 address만 있는 행도 실제로 있다(비-"
     "데모 78건 중 1건) — 기존 partners 행은 region 칸에 축약형이 이미 채워져 있어 "
     "우연히 안 터졌을 뿐(region 값 표본 확인), region이 빈 신규/2트랙 행에서만 실제로 "
     "터진다. 고침 — geocode_fill.py:_sido_set() 단일 지점(111~133행 부근) — db.REGION_"
     "LONG(정확히 이 문제를 풀려고 이미 있는 표, norm_regions()가 쓰는 것과 같다. 이 "
     "파일은 순환임포트 걱정 없이 db를 이미 import한다)으로 정식 명칭을 먼저 축약형으로 "
     "바꾼 뒤 기존 _SIDO 정규식은 그대로 쓴다(새 헬퍼·새 정규식 없음, ponytail 원칙, "
     "round512·649·650과 동일). geocode_fill.py 392→425줄(+33, 근거 주석+demo() 회귀 "
     "케이스 6건). 회귀테스트(test_scan_round653_fixes.py, 18개 검사) 신설 — [1] 소스 "
     "확인(_sido_set()이 DB.REGION_LONG을 쓰고 라운드653 표식이 있다). [2] 실행 — demo()"
     "의 기존 자체점검 전부(round159·512·649·650 회귀 없음) + 신규 discriminating "
     "4케이스(포항·여수·천안·창원)를 _region_ok() 직접 호출로 확인 + 대조군(정식명칭 vs "
     "축약형 같은 도는 여전히 통과, round650 세종대로 방어 잔존). [3] 실행 — 실제 "
     "geocode_fill.fill()을 스크래치 DB + 스텁 ADDR.search(경북 포항 협력사를 검색하면 "
     "부산 좌표를 내주는 가짜 카카오 응답, region 칸은 실데이터 조건 그대로 비워 둠)로 "
     "끝까지 돌려, 고친 코드는 틀린 좌표를 안 저장하고 geo_src='시도실패'로 표시함을 "
     "확인. [4] 되돌림-증명 — GF._sido_set을 라운드653 이전 구현(DB.REGION_LONG 정규화 "
     "없음)으로 런타임에 되돌려(파일은 안 건드림 — 함수 객체 교체만) 같은 시나리오를 새 "
     "협력사 행으로 다시 돌리면 실제로 부산 좌표가 경북 협력사에 geo_src='주소검색'으로 "
     "잘못 저장되는 옛 결함이 fill() 실행으로 재현됨을 확인, 즉시 원복 확인까지. 이 세션 "
     "내내 geocode_fill.py가 디스크에서 한 바이트도 안 바뀜을 마지막에 재확인. 첫 실행 "
     "18/18 통과. round649·650 회귀테스트도 개별 재실행해 충돌 없음 확인(각각 28/28· "
     "15/15 통과). geocode_fill.py는 app.py/serve_waitress.py가 import하지 않는 독립 "
     "유지보수 CLI(운영자가 손으로 돌림)라 서버 재기동 불필요·BUILD_HASH 불변."),
    ("test_scan_round654_fixes.py",
     "스캔 654라운드 회귀(직접조사, 하위위임 없음) — check_orphan_chars.py [2]절(조판 "
     "고아문자 후보) 독립 결함 2건. 결함A: orphan_candidates()의 1글자 꼬리 예외 목록"
     "(*, ✓, →←↑↓, ·, —-)에 '↗'(외부링크 라벨 끝에 붙는 아이콘)가 빠져 있었다 — 실측: "
     "static/admin.js:1135 '발주처 연동 안내서 ↗'·:1311 'KISCON 조회 ↗', templates/"
     "insurer_portal.html:446 '전산 연동 안내서 ↗' 3곳 전부 target=\"_blank\" 외부링크 "
     "라벨일 뿐 실제 조판 흠이 아닌데 오탐으로 41개 후보에 섞여 있었다(round124 '자주 "
     "우는 늑대'와 같은 클래스). 결함B: main()의 요약수치 '조판 후보 N건'이 화면표시 "
     "상한(cs[:8])에 종속돼, 한 파일이 8건을 넘기면 넘는 만큼(admin.js 처럼 '(외 N건)' "
     "안내는 하면서) 맨 끝 합계에서는 조용히 빠졌다 — 형제 블록([1]절 깨진 문자)은 "
     "total += len(hits)로 자르기 전 원본 길이를 먼저 더해 정확한데 이 블록만 cs[:8] "
     "루프 **안에서** cand += 1을 해 어긋나 있었다. 두 결함이 겹쳐 round641 당시 41건은 "
     "이미 틀린 값이었고(결함B가 admin.js 8건을 숨김), 실제 전체는 49건, 결함A가 없앤 "
     "노이즈 3건을 빼면 정확한 값은 46건이다. 고침 — check_orphan_chars.py "
     "orphan_candidates()의 예외 튜플에 '↗' 추가(코드베이스에 없는 ↘↖↙는 추측성 확장이라 "
     "안 넣음), main()의 cand 집계를 cs[:8]로 자르기 **전** len(cs)로 한 번만 하도록 "
     "이동(형제 total 패턴과 통일). check_orphan_chars.py 222→245줄(+23, 근거 주석 "
     "포함). 회귀테스트(test_scan_round654_fixes.py, 16개 검사) 신설 — [1] 소스 확인. "
     "[2] 실행 — 합성 파일: '↗'로 끝나는 외부링크 라벨은 후보에서 빠지고 평범한 1글자 "
     "꼬리(실제 landing.html 문구 재사용)는 여전히 잡힘(대조군). [3] 되돌림-증명(exec, "
     "원본 파일은 안 건드림) — 두 고침을 인메모리로 되돌린 사본은 '↗' 라벨을 다시 "
     "오판하고, 10건짜리 합성 디렉터리에서 8건만 요약에 세는 것까지 재현, 지금 버전은 "
     "둘 다 정확함을 대조 확인. [4] 실제 저장소 서브프로세스 스캔 — 옛 '↗' 오탐 3곳 "
     "소멸 확인 + '화면 표시 줄 수 + 모든 (외 N건) 합 == 요약 숫자' 자기정합성 검증"
     "(매직넘버 대신 불변식으로 검증해 향후 콘텐츠 변경에도 안 깨짐), 오늘 기준 실제값 "
     "46건 확인. [5] 테스트 충돌 해소 — test_scan_round641_fixes.py [5]절이 '조판 후보 "
     "(\\d+)건'을 41로 못박아 검증하고 있었다(그 라운드의 실제 검증 의도는 'CSS 선언 "
     "추가가 candidate 탐지를 안 흔든다'였지 41이라는 숫자 자체가 아니었다 — 41 자체가 "
     "결함B 때문에 이미 부정확했다). 그 assertion의 기대값만 46으로 갱신(검증 의도는 "
     "그대로), round641을 독립 재실행해 14/14 통과 재확인. check_orphan_chars.py는 "
     "app.py/serve_waitress.py가 import하지 않는 독립 점검 스크립트(운영자가 손으로 "
     "돌림)라 서버 재기동 불필요·BUILD_HASH 불변. templates/static 미변경이라 "
     "build_pages.py 재실행 불필요."),
    ("test_scan_round655_fixes.py",
     "스캔 655라운드 회귀(직접조사, 하위위임 없음) — landing.html 임베디드 위전문(widow-fix) "
     "런타임 스크립트가 '문단 전체의 진짜 마지막 줄'만 보고 <b> 강조구간이 문단 중간에서 "
     "끝나는 경우는 못 잡던 사각지대(round654가 인계한 '46건 조판 고아후보 실측' 후보를 "
     "실제로 착수한 첫 사례). 스크래치 정적서버(python -m http.server, docs/)에 브라우저로 "
     "직접 떠 320~1440px 전수 스윕 — landing.html '통값 경쟁 입찰' 단계의 <b>사진이 없어 "
     "현장 확인이 먼저 필요했던 건</b>이 375·390px(가장 흔한 모바일 폭)에서만 '건' 한 글자로 "
     "둘째 줄에 홀로 남음을 실측. 근본원인 — 이 <b>는 문단 끝이 아니라 중간(뒤에 문장이 "
     "이어짐)이라 round641의 text-wrap:balance(문단 끝 전용)도, landing.html 자신이 이미 "
     "갖고 있던 위전문 스크립트(문단 전체 마지막 공백 하나만 NBSP로 붙임)도 이 자리를 "
     "다루지 못했다. 더 나쁜 점 — 그 스크립트의 되돌리기 1단계가 el 하위 텍스트노드 전체를 "
     "훑어 NBSP를 원상복구하므로, <b> 안에 정적 &nbsp;를 박는 손쉬운 처방은 로드/리사이즈 "
     "때마다 조용히 지워진다(이 세션이 실제로 시도해 겪음). 고침 — 위전문 <script>의 "
     "fix(el) 기존 2~4단계를 glueLastGap(nodes)로 그대로 뽑아내고(로직 불변), "
     "textNodesOf(root) 헬퍼 신설, 신규 hasMoreText(afterEl, el)로 '문단의 진짜 마지막 "
     "내용인 <b>'만 걸러 이중처리를 막은 뒤, fix(el)이 문단 전체 처리 뒤에 "
     "el.querySelectorAll('b') 전체를 순회하며 hasMoreText 가드를 통과한 것만 "
     "glueLastGap을 추가로 돌린다. 실측 재확인 — 375·390px 모두 '필요했던 건'으로 합쳐져 "
     "해소, 나머지 폭 무변화, 페이지의 다른 <b> 89개 블록 전수 자동스캔도 새 회귀 0건(단 "
     "360px에서 <b>AI가 시공 전·중·후로 분류·정렬</b>이 '·' 자체를 별도 줄바꿈 허용지점으로 "
     "보는 렌더러 특성 때문에 '분류·'/'정렬'로 갈리는 기존 별개 사각지대를 발견 — 이 세션이 "
     "NBSP 반전 재현으로 이번 고침과 무관함을 직접 확인, 2글자 꼬리라 round124/641 정책상 "
     "범위 밖으로 기록만 하고 미착수). 방법론 메모 — 스크래치 포트를 서버 재시작 후 "
     "재사용하면 브라우저 공유 캐시가 옛 응답을 돌려줌(캐시버스터 필요), NBSP 리터럴은 "
     "항상 JS \\u00a0 이스케이프로 써서 U+00A0/U+0020 혼동을 피할 것(이 세션이 두 번 겪음). "
     "회귀테스트(test_scan_round655_fixes.py, 18개 검사) 신설 — [1] Flask 렌더로 실제 "
     "위전문 <script> 추출. [2] 신규 함수·호출부 구조 확인. [3] node로 실제 코드 직접 "
     "실행(미니멀 DOM 셈, jsdom 미의존) — round655 결함 모양 재현 트리에서 대상 <b>가 "
     "실제로 글루됨·hasMoreText가 중간/트레일링을 정확히 구분·fix() 재호출(리사이즈 흉내) "
     "안정·트레일링 대조군은 정확히 1회만 글루(이중처리 없음) 전부 실행으로 확인. [4] "
     "되돌림-증명 — round655 착수 직전 실제 백업에서 그대로 추출한(재타이핑 없음) 옛 "
     "버전을 같은 하네스로 돌려 같은 트리에서 글루가 실제로 안 걸림을 확인. [5] "
     "check_orphan_chars.py 재실행, 조판 후보 46건 불변(런타임 JS만 바꿔 소스 패턴 무관) "
     "재확인. templates/landing.html만 변경(843→908행 부근, +약60행), build_pages.py "
     "재실행으로 docs/index.html 재생성 완료(25개 파일), templates/landing.html 변경이라 "
     "서버 재기동 필요."),
    ("test_scan_round656_fixes.py",
     "스캔 656라운드 회귀(직접조사, 하위위임 없음) — 협력사 포털 '못 올린 사진' 자동재전송 "
     "upqAutoFlush()가 boot()의 UPQ.setWho() 결정보다 먼저 뛸 수 있던 경합. UPQ.setWho()는 "
     "reload()(587행 부근) 안에서만 불리는데, upqAutoFlush()는 파일 하단 "
     "window.addEventListener('online',…)·document.addEventListener('visibilitychange',…) "
     "전역 리스너로 boot()/reload() 진행과 완전히 독립적으로도 불린다 — 페이지를 막 연 뒤 "
     "reload()가 setWho()에 닿기 전(신호 나쁜 현장에선 수초까지) 그 사이 신호가 돌아오거나 "
     "화면을 켜면(이 기능이 정확히 노리는 상황) UPQ.who가 아직 null이라 upqueue.js "
     "UPQ.all()의 소유자 필터가 통째로 빠져 같은 기기의 다른 업체 사진까지 이 세션 "
     "자격증명으로 업로드를 시도한다. app.py api_partner_upload_photos(12895행)는 사건 "
     "소유자가 아니면 404 '내 시공 건이 아닙니다'로 정확히 막지만, uploadPhotos()의 "
     "RETRYABLE=[401,403,408,409,413,419,423,425,429] 목록엔 404가 없어 permanent(영구"
     "거절)로 분류돼 UPQ.remove()로 남의 미업로드 현장사진이 기기에서 영구 삭제된다(재촬영 "
     "불가 — 이 파일 전체가 지키려는 불변식 위반). 고침 — 단일 초크포인트: boot()가 "
     "UPQ.setWho()를 결정(성공이든 org_id 없음이든)하는 시점에 새 플래그 "
     "_upqIdentityReady를 true로 세우고(reload() 내 setWho 바로 다음 줄), "
     "upqAutoFlush() 진입 가드에 `|| !_upqIdentityReady`를 추가했다(upqBanner()·upRetry()는 "
     "이 함수를 거쳐야만 도달해 다른 독립 경로 없음을 grep으로 확인 — 수동 '지금 올리기' "
     "버튼은 reload()가 그린 배너 안에만 있어 원래도 안전, 안 건드림). "
     "회귀테스트(test_scan_round656_fixes.py, 15개 검사) 신설 — [1] 소스 확인(플래그 선언· "
     "reload() 내 설정 위치·가드 조건, 근거로 든 인과사슬 4곳(upqueue.js 필터·app.py 소유자 "
     "검사·404 응답·RETRYABLE 목록) 전부 실측). [2] 실제 Node.js 실행 — upqAutoFlush() 함수를 "
     "실제 파일에서 그대로 추출해 최소 sandbox(fake UPQ·File·navigator)로 돌려, 플래그가 "
     "false면 UPQ.grouped() 자체가 안 불리고(남의 사진을 건드릴 기회 원천 차단) true면 정상 "
     "동작함(기능 자체는 안 죽음)을 확인. [3] 되돌림-증명 — 가드에서 `|| !_upqIdentityReady` "
     "한 절만 스크래치 사본에서 제거해 같은 하네스로 돌리면 boot 전·후를 구분 못하고 즉시 "
     "UPQ.grouped()가 불려 결함이 재현됨을 확인(실제 templates/partner_portal.html은 검증 "
     "내내 디스크에 안 씀). templates/partner_portal.html만 변경(3곳 — 플래그 선언· "
     "reload() 내 설정·upqAutoFlush() 가드), build_pages.py는 이 파일을 안 건드리지만 규정상 "
     "재실행(무변화 확인), 서버 재기동 필요(app.py가 templates/를 서빙)."),
    ("test_scan_round658_fixes.py",
     "스캔 658라운드 회귀(직접조사, 하위위임 없음) — popbill_check.py _hint() 오류코드 매핑 "
     "결함 2건. 라운드649가 '공식 문서 필요'로 미결 처리한 뒤 5라운드(649~657) 보류돼 있던 "
     "항목을 이번 라운드에 웹 접근으로 직접 해소 — 공식 linkhub-sdk/popbill.exception 저장소의 "
     "990_linkhub.csv(UTF-8)·150_message.csv(EUC-KR)를 raw로 내려받아(AI 요약이 아니라 원문 "
     "바이트 직접 디코드) 전수 대조. [결함1] exact 표의 '-99004022'/'-99004023'가 실제로는 "
     "'생성할 링크아이디정보/서비스 목록이 입력되지 않았습니다'(신규 LinkID 발급용 관리자 API "
     "오류 — 이 도구가 실제로 부르는 checkIsMember/getCorpInfo/getSenderNumberList/getBalance/ "
     "send 어느 것도 낼 수 없는 코드)인데 'SecretKey가 틀렸다'/'서명이 맞지 않는다'는 그럴듯 "
     "하지만 근거 없는 문구가 붙어 있었다(이 함수 자신의 주석 '정확한 것만 덧붙인다' 위반). "
     "반대로 진짜 서명불일치 코드 -99010007('권한요청 정보의 서명이 일치하지 않습니다')은 "
     "특정 안내가 없어 애매한 '-99' 통합문구로만 떨어졌다. [결함2] 발신번호 판정 "
     "`c.startswith(\"-100\") or \"1004\" in c`가 실제 발신번호 미등록 코드(-15001009~014, "
     "예: '등록되지 않은 발신번호입니다')를 단 하나도 못 잡는다(전부 '-15001' 대역이라 '-100' "
     "prefix에 안 걸리고 '1004' 부분문자열도 없음 — 이 도구 자신의 문서화된 '가장 많이 막히는' "
     "지점인데 실제 코드엔 조용히 실패). 반대로 전혀 무관한 -15001004('삭제할 수신거부번호가 "
     "입력되지 않았습니다')는 '1004' 부분일치로 오탐. 고침 — exact 표를 검증된 코드로 교체 "
     "(-99004022/023 제거, -99010007 추가), 발신번호 판정을 실제 6개 코드(-15001009~014)의 "
     "정확한 set 매칭으로 교체(같은 '-15001' 대역에 섞인 수신거부(080) 관리 오류 "
     "-15001001~008·015는 발신번호와 무관하므로 prefix 대신 set 사용). demo() 자체점검 안의 "
     "합성코드 '-1004'도 실제 코드 '-15001014'로 교체. 회귀테스트(test_scan_round658_fixes.py, "
     "20개 검사) 신설 — [1] AST로 exact 딕셔너리 키 집합과 발신번호 판정 튜플 원소를 직접 "
     "추출해 정확한 코드 집합인지 확인. [2] 실제 _hint() 직접호출로 6개 코드(신규/제거/정직한 "
     "폴백 포함) 검증. [3] 실제 main()/step() 파이프라인 종단확인 — 가짜 서비스 객체가 진짜 "
     "popbill.PopbillException을 던지게 해 화면 출력까지 확인(4개 코드). [4] 되돌리기 — 고치기 "
     "전 _hint() 소스를 문자열로 격리 네임스페이스에 exec해(실파일 미접촉) 옛 버전이 실제로 "
     "네 가지 증상(미탐지·오탐·근거없는 확정문구·애매한 폴백)을 냈음을 인과관계로 증명. [5] "
     "--self-check 서브프로세스 재확인. 기존 popbill_check.py 관련 회귀 6개(round272/280/291/ "
     "301/305/518) 전부 재실행해 회귀 없음 확인. popbill_check.py는 app.py가 import하지 않는 "
     "독립 CLI라 서버 재기동 불필요."),
    ("test_scan_round659_fixes.py",
     "스캔 659라운드 회귀(직접조사, 하위위임 없음) — 실사용자 보고(\"관리자 콘솔·보험사 어드민·"
     "시공사 어드민 사이 동기화가 안 된다\")를 조사해 발견: 보험사 사건 등록 공용 헬퍼 "
     "_create_case()의 정상 접수 경로(사진있음)가 협력사 전체(공고오픈)·보험사 본인(사건접수) "
     "에게는 실시간 알림을 보내면서 운영팀에게는 알림을 전혀 안 보내고 있었다 — 사진없는 접수"
     "(수배필요)·매칭 0곳(참여업체없음) 두 예외 경로에만 운영팀 알림이 있었을 뿐, 가장 흔한 "
     "정상 경로만 빠져 있었다. 목록(api_cases)은 필터 없이 항상 보이므로 사건 자체가 안 보이는 "
     "것은 아니었지만, 운영팀이 매번 목록을 직접 열어보지 않는 한 새 접수를 알 방법이 없었다. "
     "같은 조사에서 함께 확인한 별개 사실(코드 결함 아님, 이번 라운드 범위 밖) — 운영 DB 실측: "
     "활성 시행사 90곳 중 로그인 계정 보유는 2곳뿐이고, 문자·알림톡 실발송 스위치"
     "(BOKGUON_NOTIFY_ENABLED)가 .env에서 꺼져 있다(팝빌 연동 대기 상태) — 둘 다 운영/계정 "
     "설정 문제라 사용자 확인 후 범위에서 제외. 고침 — 형제 두 알림(수배필요·참여업체없음)과 "
     "같은 자리·같은 패턴으로 정상 접수 경로에 \"사건접수\"→admin 알림 한 곳만 추가(app.py, "
     "_create_case() 안). 협력사 전체·보험사 본인 알림 로직은 무변경. 회귀테스트"
     "(test_scan_round659_fixes.py, 19개 검사) 신설 — [1] 소스 확인(새 notify() 호출이 "
     "정상경로에만 있고 no_photo 경로엔 없음). [2] 실제 Flask+DB로 매칭 0곳·매칭 1곳·사진없는 "
     "접수 세 시나리오 전부 확인(문구의 매칭수까지 정확한지, 형제 알림과 상호배타적인지). "
     "[3] 되돌림-증명 — 새 알림 블록만 dict(vars(A)) 네임스페이스의 사본에서 제거해(실제 "
     "app.py는 안 건드림) 결함이 실제로 재현됨을 확인. templates/static 미변경, app.py만 "
     "변경(_create_case() 한 곳)이라 서버 재기동 필요."),
    ("test_scan_round662_fixes.py",
     "스캔 662라운드 회귀(직접조사, 하위위임 없음) — round661 인계 각도(PWA 서비스워커·"
     "dispatch_calls 스케줄링) 자체 로직은 전 함수 정독 결과 이미 극도로 촘촘해 클린이었으나, "
     "각도를 '이 함수들의 로직'에서 '이 함수들이 불리는 경로가 형제와 같은가'로 옮겨 발견 — "
     "app.py:_sweep_if_due()(조회 화면을 열 때마다 곁들여 도는 인라인 마감 스윕 백스톱)가 "
     "정확히 5개(sweep_auctions·sweep_no_bid_alert·sweep_report_overdue·"
     "sweep_review_reminders·sweep_warranty_expiry)만 부르고, 형제뻘인 "
     "sweep_approval_overdue()·dispatch.sweep_dispatches() 두 개는 처음부터 빠져 있었다. "
     "둘 다 manage.py cmd_sweep()(예약 실행 크론, 10분 주기) 단 한 곳에서만 불렸다(grep 전수"
     "확인) — sweep_approval_overdue() 자신의 독스트링이 '사람이 어드민을 열고 눌러야만 "
     "알림이 갔다. 아무도 안 열면 영원히 아무 일도 일어나지 않는다'고 못박은 바로 그 문제를, "
     "크론이 멈추면(이 저장소 자신의 기록에 실제 사례 있음 — deploy/복구온_예약실행_등록.ps1 "
     "머리말) 형제 5개와 달리 어떤 페이지를 열어도 되살릴 방법이 없이 그대로 재현한다. "
     "dispatch.sweep_dispatches() 도 같은 처지(모듈 독스트링: '이것이 없으면 한 업체가 "
     "수락만 하고 안 가는 순간 사건이 영원히 멈춘다') — manage.py 자신의 주석('★ 출동 기한 "
     "점검 — 이게 빠져 있었다')이 크론에는 추가됐음을 증언하지만 인라인 백스톱은 못 받았다. "
     "안전성 확인 — 이 둘은 sweep_send_notifications·sweep_webhook_retries(외부 API 실호출·"
     "블로킹이라 의도적으로 크론 전용)와 다르다: DB 트랜잭션만 쓰고(실제 문자·알림톡 발송은 "
     "여전히 크론 전용 sweep_send_notifications 몫), 동시실행 방어도 이미 자체적으로 있다"
     "(dispatch_sweep=job_locks 리스, 승인독촉=알림 24시간 쿨다운 — 형제 5개와 동일 패턴). "
     "고침 — _sweep_if_due() 의 try 블록 끝(기존 5개 다음, except 이전)에 "
     "sweep_approval_overdue(conn) 과 DP.sweep_dispatches(conn, notify=_dispatch_notify(conn)) "
     "두 줄만 추가(새 헬퍼·새 상수 없음, 기존 5개 순서·주석 무변경). 회귀테스트"
     "(test_scan_round662_fixes.py, 15개 검사) 신설 — [1] 소스: _sweep_if_due() 본문에 새 "
     "2줄이 기존 5개 뒤·except 이전에 정확히 있고, manage.py cmd_sweep 쪽은 안 건드렸음을 "
     "AST/문자열 위치로 확인. [2] 모킹 직접호출로 새 2개가 실제로 실행부에서 불림을 확인"
     "(죽은 텍스트가 아님). [3] 스크래치 DB에 APPROVAL_REMIND_DAYS를 넘겨 방치된 완료승인 "
     "대기 정산 1건과 dispatch_minutes를 넘겨 방치된 '모집중' 수배 1건을 실제로 심고, 진짜 "
     "_sweep_if_due() 를 호출해 독촉 알림 생성과 수배 '실패' 전환이 실제로 일어남을 확인. "
     "[4] 되돌림-증명 — 고치기 전 5개짜리 _sweep_if_due() 원문을 문자열로 재구성해(실제 "
     "app.py는 안 건드림) 같은 방치 시나리오를 다시 심고 돌려, 옛 코드는 독촉 알림도 안 "
     "만들고 수배도 '모집중'에 그대로 방치함을 대조 확인(인과관계 증명). templates/static "
     "미변경, app.py만 변경(_sweep_if_due() 한 곳)이라 서버 재기동 필요."),
    ("test_scan_round663_fixes.py",
     "스캔 663라운드 회귀(직접조사, 하위위임 없음) — round640 자신이 '확인되지 않았다'고 "
     "명시적으로 남긴 두 사각지대(check_tx_paths.py, BEGIN IMMEDIATE 트랜잭션 commit/rollback "
     "누락 점검 CLI) 중 '독립된 두 if 로 각각 조기 return 하는 가드절' 을 실제로 확인해 보니 "
     "살아 있는 결함이었다. _may_precede() 의 `r_path.get(if_id, branch) == branch` 는 r 이 "
     "그 if 안에 아예 없을 때도(딕셔너리 기본값이 그대로 branch 와 같아) 조건을 만족한 것으로 "
     "쳐, 'if a: commit(); return x' 다음에 오는 완전히 독립된 'if b: return y'(commit 없음, "
     "if a 에 else 없음) 를 안전하다고 오판했다(synthetic 실측 — 아래 [2]). 다른 사각지대 "
     "①(try/except 형제 가지)은 109개 함수 전수 재확인 결과 지금은 무해함을 확인, round640 "
     "주석 그대로 다음 라운드 몫으로 남김. 고침 — `_branch_path()` 가 if 노드의 id 대신 노드 "
     "자신을 담게 바꾸고, `_branch_has_commit()`·`_if_guarantees_commit()`(if/else 양쪽 가지 "
     "모두 commit/rollback 을 보장하는가, orelse 없으면 False) 두 헬퍼를 신설, `_may_precede()` "
     "는 r 이 같은 가지가 아니면 그 if 가 `_if_guarantees_commit` 이 아닌 한 False. ⚠ 단순히 "
     "'r 이 그 if 안에 없으면 무조건 False'로만 고쳤다면 이 저장소에서 가장 흔한 관용구(if X: "
     "commit() else: rollback() 뒤에 무조건 return — app.py sweep_review_reminders 6636행· "
     "api_defect_update 15894행) 가 새 거짓양성으로 잡혔을 것 — _if_guarantees_commit() 이 "
     "그 회귀를 막는다(실측 확인). 회귀테스트(test_scan_round663_fixes.py, 17개 검사) 신설 — "
     "[1] 소스: 새 헬퍼 둘·_may_precede() 새 6인자 시그니처·main() 새 호출부가 정확히 한 번씩 "
     "있음을 확인. [2] 되돌림-증명 — _branch_path()·_may_precede()·main() 호출부를 round640 "
     "시절(id 기반) 텍스트로 되돌린 옛 버전을 dict(vars(CTP)) 독립 사본 네임스페이스에 exec"
     "(check_tx_paths.py 파일·실제 모듈 둘 다 안 건드림), 독립 가드절 결함 합성 파일에 겨눠 "
     "실제로 클린(0건, 사각지대 재현)을 보고함을 확인. [3] 지금(고쳐진) 실제 CTP.main() 은 "
     "같은 합성 결함을 위반(exit 1, 함수명 포함)으로 잡고, if/else 양쪽이 각각 commit·rollback "
     "하는 정상 합성 파일은 과잉탐지 없이 통과함을 확인. [4] 실제 check_tx_paths.py 를 서브 "
     "프로세스로 실행해 저장소 전체가 109개 함수·위반 0건으로 끝남을 재확인(오탐 없음). 이 "
     "수정으로 소스 텍스트가 바뀐 자리를 정적으로 문자열 매칭하던 round621·640 자신의 "
     "회귀테스트(test_scan_round621_fixes.py·test_scan_round640_fixes.py) 의 _may_precede 시그"
     "니처·main() 호출부 앵커가 함께 갱신됐다 — 두 파일 모두 재실행해 각각 16/16·18/18 통과로 "
     "충돌 없음 재확인. check_tx_paths.py 는 app.py/dispatch.py/manage.py 어디에도 import 되지 "
     "않는 독립 진단 CLI라 서버 재기동 불필요, templates/static 무변경."),
    ("test_scan_round664_fixes.py",
     "스캔 664라운드 회귀(직접조사, 하위위임 없음) — collect_emails.py 가 partners.website 를 "
     "실제로 GET 하면서 리다이렉트는 전혀 막지 않은 SSRF 결함(round517 이 놓친 같은 계열의 새 "
     "우회로). round517 은 _host_is_internal() 을 fetch()·robots_allows() 두 접속 지점에 걸어 "
     "website 를 내부주소로 직접 적어 두는 SSRF 는 막았지만, 그 검사는 최초 접속 주소만 본다 — "
     "website 가 공인 도메인(검사 통과)이라도 그 서버가 301/302 로 내부 주소를 가리키면 "
     "urllib.request.urlopen() 도 RobotFileParser 도 기본 오프너가 그대로 따라가 검사를 완전히 "
     "우회한다(round517 자신의 ponytail 주석은 DNS 리바인딩만 논의했을 뿐 리다이렉트는 언급조차 "
     "없었다 — 경합조건 없이 정적 301 응답 하나로 매번 재현되는 별개의 더 쉬운 우회로). app.py 의 "
     "웹훅 SSRF 방어가 정확히 이 경로를 '③ 리다이렉트를 따라가지 않는다'(_NoRedirect)로 막는데 "
     "형제인 이 파일에는 없었다. 실측(격리 로컬 리다이렉터+내부 서버로 재현) — 고치기 전엔 "
     "urlopen() 도 RobotFileParser.read() 도 둘 다 301/302 를 그대로 따라가 내부 서버의 '비밀' "
     "이메일이 그대로 수집됐다. 고침 — app.py 와 같은 _NoRedirect(HTTPRedirectHandler 서브클래스, "
     "redirect_request 가 항상 None) 오프너 _NO_REDIRECT_OPENER 를 신설해 fetch() 가 이 오프너로 "
     "직접 열게 하고, robots_allows() 는 RobotFileParser 가 오프너를 주입받을 방법이 없어(내부에서 "
     "직접 urlopen() 을 부른다) rp.read() 를 부르는 동안만 전역 기본 오프너를 바꿔치기한다(기존 "
     "[라운드639] 소켓 타임아웃 save/restore와 같은 방식). 두 접속 지점이 _NO_REDIRECT_OPENER 하나를 "
     "공유하는 단일 근본원인 수정. 회귀테스트(test_scan_round664_fixes.py, 12개 검사) 신설 — "
     "[1] 소스: _NoRedirect 가 HTTPRedirectHandler 서브클래스로 정의돼 있고 fetch() 가 이제 "
     "_NO_REDIRECT_OPENER.open(req 를 쓰며(옛 urlopen(req 패턴 없음), robots_allows() 가 "
     "install_opener 로 바꿔치기·복원함을 확인. [2] 실행 — 실제 로컬 리다이렉터→내부 서버 두 개로 "
     "fetch() 를 직접 호출해 내부 서버 0건 요청·fetch() None 반환을 확인. [3] 실행 — collect_one() "
     "전체 경로(robots_allows()·fetch() 모두)에서도 안 샘을 확인. [4] 되돌리기 — "
     "_NO_REDIRECT_OPENER 하나만 옛 기본(리다이렉트 추종) 오프너로 바꾸면(fetch()·robots_allows() "
     "코드는 안 건드림) 내부 서버의 '비밀' 이메일이 실제로 수집됨을 확인해 인과관계를 증명. "
     "collect_emails.py 는 app.py 어디에도 import 되지 않는 독립 CLI라 서버 재기동 불필요, "
     "templates/static 무변경."),
    ("test_scan_round665_fixes.py",
     "스캔 665라운드 회귀(직접조사, 하위위임 없음) — check_tx_paths.py _may_precede() 가 round640이 "
     "범위 밖으로 남기고 round663이 '다음 라운드감'으로 재확인한 나머지 사각지대(①try/except 가지 "
     "사이)를 실제로 안고 있던 결함. _branch_path() 는 If 조상만 가지로 기록하고 Try 는 그냥 지나쳐, "
     "try 본문의 commit() 과 형제 except 안의 무방비 return 이 서로 배타적인데도(예외가 나야 그 "
     "except 로 온다) '가지 구분 없음' 취급되어 안전 쪽 기본값으로 새 나갔다. synthetic 재현 — try 는 "
     "commit 후 return, except 는 아무 commit/rollback 없이 return: 고치기 전엔 클린(0건) 오판. "
     "handler 끼리도 같은 문제(한쪽만 commit+return, 다른 쪽 무방비). 고침 — _branch_path() 가 Try "
     "본문/orelse 는 'try'로, 각 handler 는 서로 다른 ('except', id(handler))로 기록(핸들러끼리도 "
     "배타적 가지). _try_guarantees_commit() 신설(_if_guarantees_commit 과 같은 역할 — 정상경로 + try "
     "다음으로 이어지는 모든 handler 가 커밋하는가, _handler_falls_through 로 raise/return/continue/"
     "break 로 끝나 다음 코드로 안 이어지는 handler 는 제외). _may_precede() 는 r 이 그 조상의 '가지 "
     "밖'(다음 코드)일 때만 guarantee 우회를 쓰고, r 이 이미 그 조상의 다른 가지 안이면 곧장 위험 "
     "판정하도록 구분(안 그러면 r 자신의 handler 가 스스로 면제돼 이 라운드가 잡으려던 결함을 다시 "
     "놓친다 — 조사 중 synthetic 으로 직접 확인). 일반화 도중 실제 4개 대상 파일 재검사에서 오탐 5건 "
     "발견 — 전부 이미 안전한 관용구 2종이었다(app.py 4곳 'try: rollback() except: pass' 방어용 "
     "래퍼는 _is_bare_rollback_guard 로 투명 처리, dispatch.py:1020 sweep_dispatches 는 유일한 "
     "handler 가 항상 raise 로 다시 던져 다음 코드로 안 이어지므로 _handler_falls_through 로 커밋 "
     "요구에서 제외). 실제 저장소(109개 함수) 재확인 결과 고치기 전/후 모두 위반 0건 — 이 사각지대가 "
     "지금까지 실제 결함을 감춘 적은 없었지만 다음에 추가되는 'try 커밋 + 형제 except 무방비 return' "
     "하나가 조용히 이 방어를 무력화할 수 있는 상태였다. round640의 오래된 test_scan_round640_fixes.py "
     "가 _branch_path() 의 옛 3인자 시그니처 문자열을 그대로 검증하고 있어 새 4인자(conn_names 추가) "
     "시그니처로 갱신 — 검증 의도(헬퍼가 정확히 한 번 존재)는 그대로 두고 재실행해 18/18 통과로 충돌 "
     "없음 재확인. 회귀테스트(test_scan_round665_fixes.py, 25개 검사) 신설 — [1] 소스: 새 헬퍼 "
     "(_is_bare_rollback_guard·_handler_falls_through)·확장된 _branch_path/_try_guarantees_commit·"
     "손본 _may_precede 확인. [2] 실행 — synthetic 5종(진짜 결함 2개는 반드시 잡히고 이미 안전한 "
     "관용구 3개는 오탐 없이 통과)을 실제 CTP.main() 으로 확인. [3] 실행 — 실제 check_tx_paths.py 를 "
     "서브프로세스로 그대로 실행해 109개 함수·위반 0건 재확인. [4] 되돌리기 — _branch_path·"
     "_may_precede 만 round663 시절(Try 미인식) 텍스트로 독립 사본 네임스페이스에 되돌리면(파일도 "
     "실제 모듈도 안 건드림) bad_try_except_sibling 합성 파일이 클린(0건)으로 오판됨을 확인해 "
     "인과관계를 증명. check_tx_paths.py 는 app.py/dispatch.py/manage.py 어디에도 import 되지 않는 "
     "독립 진단 CLI라 서버 재기동 불필요, templates/static 무변경."),
    ("test_scan_round667_fixes.py",
     "스캔 667라운드 회귀(직접조사, 하위위임 없음) — 보험사 월 정산 명세서 화면(관리자 콘솔·보험사 "
     "포털 둘 다)의 기본 선택월이 여태 '이번 달'이었던 결함. 서버 _stmt_period_args()(round564)는 "
     "\"없으면 지난달\"을 정확히 계산하는데, round564 자신의 회귀설명이 이미 \"어드민·보험사 포털 "
     "화면은 <select> 로 매번 year·month 를 명시적으로 붙여 보내 평소엔 이 기본값 경로를 안 탄다\"고 "
     "적어 둔 그대로 — 두 화면 다 자기 <select> 기본 선택값 자체를(admin.js STMT 초기값·"
     "insurer_portal.html 두 <select>) 브라우저 로컬시각의 '이번 달'로 채우고 그 값을 항상 명시 "
     "파라미터로 보내, 서버의 그 폴백은 실제 사람 클릭 경로에서 단 한 번도 안 걸린다 — round564 가 "
     "고치려던 문제(미완성 이번 달 숫자가 '월 정산 명세서'라는 이름으로 나감)가 정작 가장 흔한 사용 "
     "경로에서는 여전히 매번 재현된다. 부수 발견 — insurer_portal.html 의 연도 <select> 는 애초 "
     "selected 속성 자체가 없어 '목록 첫 값=오늘 연도'라는 암묵적 가정에만 기댔다(1월에 열면 월은 "
     "지난달 12월이어도 연도는 여전히 올해로 어긋날 잠재 결함). 고침 — 단일 근본원인 수정 두 곳(공유"
     "프론트엔드 모듈이 없어 화면마다 자기 몫의 todayKST() 를 이미 복제해 갖고 있는 이 저장소 관례를 "
     "그대로 따름): admin.js 는 STMT 초기값·stmtRead() 폴백을, insurer_portal.html 은 RENDER.settle() "
     "의 두 <select>(연도 select 에 처음으로 명시적 selected 부여)와 ACT.insStmtExport() 의 방어적 "
     "폴백을 각각 todayKST() 기반 지난달 계산(_lastY/_lastM · lastY/lastM)으로 교체. 서버 "
     "_stmt_period_args() 는 이번 라운드가 손대지 않음(명시 ?year=&month= 우선순위 그대로, 회귀 없음). "
     "회귀테스트(test_scan_round667_fixes.py, 26개 검사) 신설 — [1] 소스: 두 파일에서 옛(브라우저 "
     "로컬시각) 패턴이 사라지고 todayKST() 기반 지난달 계산이 정확히 그 자리에 있음을 실제 파일 "
     "텍스트로 확인, app.py _stmt_period_args() 는 이번 라운드가 안 건드렸음도 확인. [2] 실행 — "
     "admin.js 에서 그대로 뽑은 실제 코드를 node 로 실행해 평범한 달·연도경계(1월) 시나리오에서 정확히 "
     "'지난달'을 계산함을 확인. [3] 실행 — insurer_portal.html RENDER.settle() 에서 그대로 뽑은 실제 "
     "<select> 템플릿 식을 node 로 실행해, 렌더된 HTML 문자열에서 실제로 지난달·해당 연도 옵션에만 "
     "selected 가 붙고 이번 달/이번 해에는 안 붙음을 확인. [4] 되돌리기-증명 — round667 이전 원문"
     "(브라우저 로컬시각 그대로 쓰는 옛 코드)을 실제 파일은 전혀 안 건드리고 독립 문자열로 재구성해 "
     "같은 시나리오에 돌려보면, 옛 코드는 '이번 달'을 기본값으로 골라(연도경계에서는 연도 select 에 "
     "selected 자체가 없음까지) 실제 증상이 재현됨을 확인해 인과관계를 증명. admin.js·"
     "insurer_portal.html 변경이므로 test_template_js.py 표준 재검증(9/9 통과) 및 build_pages.py 재실행"
     "+test_scan_round306_fixes.py 표준 재검증(11/11 통과, insurer_portal.html 은 애초 docs/ 를 안 "
     "먹이므로 드리프트 없음)까지 마쳤다. API 라우트·DB 스키마 무변경 — BUILD_HASH 는 static/templates "
     "를 해시하므로 로테이션 예상, 재기동 필요."),
    ("test_scan_round669_fixes.py",
     "스캔 669라운드 회귀(직접조사, 하위위임 없음) — manage.py cmd_prune_personal()(개인정보 파기, "
     "처리방침 제30조 이행) 독스트링의 '무엇을 지우는지' 목록이 실제 6개 버킷 중 3개(①도입 문의·입점 "
     "신청 ②퇴출 협력사 계좌 ③완료 사건 피해자정보)만 나열하고, 오래전 개별 구현·테스트까지 이미 끝난 "
     "나머지 3개(④종료(취소·미수선종결·유찰) 사건 피해자정보/142라운드 ⑤하자보수 기록 자유텍스트/"
     "146라운드 ⑥해피콜 기록 자유텍스트/495라운드)를 빠뜨리고 있던 결함(round666 핸드오프가 지목, 실행 "
     "로직이 아니라 함수 자신의 자기서술만 낡아 있었다). 실행 로직은 이미 다른 라운드가 개별 증명했으므로 "
     "되풀이하지 않고, '독스트링이 주장하는 항목 수 == 실제로 동시에 살아있는 코드경로 수'라는 이번 "
     "라운드의 축만 확인한다. 고침 — 독스트링에 ④⑤⑥ 항목(보관기준 포함) 추가, 코드 로직은 무변경. "
     "회귀테스트(test_scan_round669_fixes.py, 21개 검사) 신설 — [1] 소스: AST로 뽑은 함수 독스트링이 "
     "①~⑥ 여섯 마커·키워드를 모두 담고, total 합산식(n1~n6, 부속 n3b/n3c/n3d/n4b/n4c 포함)이 여전히 "
     "그대로임을 확인. [2] 직접호출 — import된 manage 모듈의 실제 함수 객체 __doc__(소스 텍스트가 아닌 "
     "런타임 속성)도 6개를 담고 있음을 확인. [3] 실행 — 여섯 버킷을 동시에 채운 격리 DB에서 "
     "cmd_prune_personal(['--dry-run'])을 실제로 호출해 ①~⑥ 전부가 실수 0건 없이 동시에 미리보기에 "
     "잡히고, 아무것도 실제로 지워지지 않음(rollback)을 확인. [4] 되돌리기-증명 — 라운드669 이전 실제 "
     "독스트링 원문(파일은 안 건드리고 문자열로만 재구성)이 ④⑤⑥ 부재로 같은 6항목 검사에 실패함을 "
     "확인해 인과관계를 증명. manage.py는 app.py가 import하지 않는 독립 CLI라 서버 재기동·BUILD_HASH "
     "로테이션 불필요, templates/static 무변경."),
    ("test_scan_round670_fixes.py",
     "스캔 670라운드 회귀(직접조사, 하위위임 없음) — 피해자 진행조회 공개 화면(templates/track.html을 "
     "채우는 app.py track_page())이 사진 없는 사건이 선착순 출동으로 현장 사진을 확보하는 동안("
     "dispatch_status='수배중')에도 cases.status 만 보고 판정해, 다른 대기 상태(입찰중·승인대기·유찰)와 "
     "달리 이 기간에는 피해자에게 내부 상태값 그대로인 '접수'가 뜨던 결함. '수배중'은 cases.status 값이 "
     "아니라 dispatch_status 값인데(dispatch.py CS_SEEKING, db.py 스키마 주석), track_page()의 smap· "
     "VICTIM_LABEL 두 딕셔너리는 여전히 c[\"status\"] 하나만 보고 '수배중' 키를 넣어 놔서 절대 안 걸리는 "
     "죽은 키였다 — 형제 함수 api_map_cases(지도 필터)는 이미 라운드56에서 똑같은 혼동을 "
     "dispatch_status로 갈라 고쳤는데, 이 화면만 그 수정이 안 퍼져 있었다. smap 쪽은 '수배중'과 '접수' "
     "값이 우연히 같아(0) 무해했지만 VICTIM_LABEL은 문구가 달라('업체 선정 중') 실제로 갈렸다. 고침 — "
     "SELECT에 dispatch_status 추가, _disp_key=(\"수배중\" if status=='접수' and dispatch_status=='수배중' "
     "else status)를 계산해 smap.get·VICTIM_LABEL.get 모두 이 키로 조회하도록 단일 지점에서 수정. "
     "회귀테스트(test_scan_round670_fixes.py, 27개 검사) 신설 — [1] 소스: SELECT에 dispatch_status가 "
     "있고 두 조회가 새 _disp_key를 쓰며 옛 c[\"status\"] 직접조회 패턴이 없음, 전제(dispatch.py "
     "CS_SEEKING, 형제 api_map_cases의 라운드56 수정)도 확인. [2] 단위 — 실제 파일에서 그대로 잘라낸 "
     "_disp_key 대입식 한 줄을 손으로 재입력하지 않고 exec로 직접 실행해 네 조합(수배중/미출동/도착 후"
     "에도 접수 단계/있을 수 없는 시공중+수배중 방어조합)에서 판정이 옳음을 증명. [3] 종단 — 스크래치 "
     "DB+실제 Flask 라우트(GET /track/<token>)로 세 사건 재현: 접수+수배중→'업체 선정 중', 접수+미출동"
     "→회귀없이 '접수', 시공중+수배중(방어)→회귀없이 '복구 공사 진행 중'. [4] 되돌리기-증명 — "
     "dispatch_status 인지가 없던 옛 구조를 함수 리네임+exec로 재구성해 A.app.view_functions[\"track_page\"]"
     "만 잠깐 치환(실제 파일 무변경)한 뒤 같은 사건을 재현하면 '업체 선정 중' 대신 '접수'가 나와 "
     "인과관계를 실측. app.py 변경이지만 API 계약·DB 스키마는 무변경(기존 컬럼을 SELECT에 추가만 함) — "
     "재기동 후 BUILD_HASH 로테이션 확인 필요, templates 무변경이라 build_pages.py 재실행은 불필요."),
    ("test_scan_round671_fixes.py",
     "스캔 671라운드 회귀(직접조사, 하위위임 없음) — 협력사 포털 '시공 현장' 카드의 '실사 증액 요청' "
     "버튼이 사건 상태 '완료보고지연'(낙찰 후 24시간 경과, 지방·주말 공사에서는 정상)일 때 나타나지 "
     "않던 결함. app.py api_change_order_create()(POST /api/cases/<id>/change-order)는 "
     "c[\"status\"] not in (\"시공중\",\"검수대기\",\"완료보고지연\") 로 막아 서버는 이 세 상태를 전부 "
     "받는데(그 함수 자신의 주석이 '완료보고지연 상태의 업체가 요청 창구를 잃었다'며 왜 이 상태를 "
     "받게 됐는지까지 적어 뒀다), 정작 그 버튼을 그리는 templates/partner_portal.html RENDER.sites()는 "
     "['시공중','검수대기']로만 걸어 '완료보고지연'이 빠진 옛 2원소 집합 그대로였다 — 같은 카드의 "
     "바로 위 두 버튼(📷 업로드·완료 보고)은 이미 이 상태를 포함하고, 이 버튼 바로 위 주석조차 "
     "'서버가 받는 상태와 같은 집합을 쓴다'고 스스로 규칙을 적어 놨는데 정작 이 버튼만 그 규칙을 "
     "어기고 있었다(round645 상태색 드리프트·round670 dispatch_status 드리프트와 같은 '형제는 "
     "고쳐졌는데 이 자리만 안 퍼졌다' 계열). 실제 영향 — 완료 보고가 24시간을 넘겨 지연된(흔한 "
     "지방·주말 공사) 협력사가 현장에서 파손이 더 크다는 걸 뒤늦게 확인해도 증액 요청 버튼 자체가 "
     "안 보여 요청할 길이 없었다(서버는 이미 받을 준비가 돼 있었으므로 손실은 순전히 화면 누락). "
     "고침 — 조건을 ['시공중','검수대기','완료보고지연']로 서버와 맞춘다(templates/partner_portal.html "
     "단일 지점). build_pages.py 재실행 + test_scan_round306_fixes.py(11/11)·test_template_js.py(9/9) "
     "표준 재검증 완료. 회귀테스트(test_scan_round671_fixes.py, 24개 검사) 신설 — [1] 소스: 화면 조건과 "
     "서버 허용집합을 각각 정규식으로 파싱해 두 집합이 정확히 같음을 구조적으로 확인. [2] 단위 — 실제"
     "템플릿에서 그대로 잘라낸 배열 리터럴을 node로 직접 실행해 5개 상태의 포함 여부가 모두 옳음을 "
     "증명. [3] 종단 — (a) 실제 render_template 파이프라인으로 그린 HTML에도 고쳐진 조건이 그대로 "
     "있음을 재확인, (b) 스크래치 DB+실제 Flask 라우트로 status='완료보고지연'인 내 낙찰 사건에 실제 "
     "증액 요청을 접수해 200을 실측. [4] 되돌리기-증명 — 잘라낸 배열에서 '완료보고지연'만 제거한 "
     "사본(실제 파일 무변경)을 같은 node 실행에 넣으면 그 상태만 false로 바뀌어 결함이 재현됨을 확인. "
     "templates/partner_portal.html만 변경, API 계약·DB 스키마 무변경 — 재기동 후 BUILD_HASH 로테이션 "
     "확인 필요."),
    ("test_scan_round672_fixes.py",
     "스캔 672라운드 회귀(직접조사, 하위위임 없음) — 보험사 포털 stTag()에 정산(settlements) 상태 "
     "'이체예약'(transfer_status)·'승인'(review_status)의 색상 매핑이 통째로 빠져 있던 결함. round644가 "
     "세 형제(insurer_portal.html stTag·partner_portal.html stTag·admin.js statusPill)의 '시공중' 색을 "
     "맞추며 '겹치는 17개 상태값을 전수 대조'했다고 적어 뒀지만, 그 대조는 그 시점에 세 매핑 모두에 이미 "
     "존재하던 키만 비교했다 — insurer_portal.html의 stTag()에는 이 두 키 자체가 처음부터 없었다. "
     "partner_portal.html stTag()·admin.js statusPill()은 이미 두 값을 갖고 실제로 "
     "stTag(sett.transfer_status)·statusPill(s.review_status) 등으로 쓰는데, insurer_portal.html만 "
     "sett.review_status(사건 상세 '지급 검수')·sett.transfer_status(사건 상세 '업체 지급'·정산 목록)를 "
     "그대로 stTag()에 넘기면서 매핑에 없어 기본값(회색)으로 떨어졌다. 운영 DB 읽기전용 조회(실측): "
     "review_status='승인'인 정산이 21/43건이라 사건 상세를 열 때마다 절반 가까이 재현되고, "
     "transfer_status='이체예약'은 app.py api_settlement_review()(POST /api/settlements/<id>/review)가 "
     "review_status='승인'과 항상 같은 UPDATE 문으로 함께 찍는 값이라 관측 여부와 무관하게 도달 가능하다. "
     "고침 — templates/insurer_portal.html의 stTag() 매핑에 '이체예약':'amber'·'승인':'green' 추가해 "
     "형제 stTag()·statusPill()과 맞춘다(단일 지점). build_pages.py 재실행 + "
     "test_scan_round306_fixes.py(11/11)·test_template_js.py(9/9) 표준 재검증 완료. 회귀테스트"
     "(test_scan_round672_fixes.py, 37개 검사) 신설 — [1] 소스: 세 매핑에서 두 값을 직접 추출해 일치 "
     "확인, 이번 수정이 3사 공통집합을 정확히 두 개만 늘렸음을 자기완결적으로 확인(round644의 그 시점 "
     "숫자를 매직넘버로 재사용하지 않음), 세 파일의 실제 호출 지점과 api_settlement_review()의 동시 "
     "UPDATE도 구조적으로 확인. [2] 단위 — 세 함수를 파일에서 그대로 잘라내 Node.js로 실행해 두 상태 "
     "모두 세 함수가 일치하는 색을 냄을 증명(기존 값 회귀 없음도 함께 확인). [3] 종단 — (a) 실제 "
     "render_template로 그린 HTML에 고친 매핑이 살아 있음을 확인, (b) 스크래치 DB+실제 Flask 라우트"
     "(GET /api/insurer/cases/<id>/detail, GET /api/insurer/dashboard)로 review_status='승인'·"
     "transfer_status='이체예약'인 정산 행을 실제로 만들어 두 라우트 모두 그 값을 그대로 내려줌을 실측. "
     "[4] 되돌리기-증명 — 잘라낸 (고친) insurer 소스 문자열에서 두 키:값만 제거한 사본(실제 파일 "
     "무변경)을 같은 Node 실행에 넣으면 그 두 상태만 회색으로 되돌아가 형제 두 함수와 갈라짐을 재현. "
     "templates/insurer_portal.html만 변경, API 계약·DB 스키마 무변경 — 재기동 후 BUILD_HASH 로테이션 "
     "확인 필요."),
    ("test_scan_round673_fixes.py",
     "스캔 673라운드 회귀(직접조사, 하위위임 없음) — 비밀번호 변경 화면의 실시간 규칙 체크리스트가 "
     "서버 정책(password_policy_error, app.py 1393행)의 네 규칙 중 ③ '로그인 아이디를 비밀번호에 "
     "포함할 수 없음'을 통째로 빠뜨리고 있던 결함. 이 함수는 /api/change-password(1489행)에서 실제 "
     "로그인 아이디를 ident로 넘겨 모든 비밀번호 변경(임시 비밀번호 강제변경 포함)에 실제로 강제되는데, "
     "templates/change_password.html의 checkRule()는 나머지 세 규칙(종류·길이·연속문자)만 실시간으로 "
     "보여주고 이 규칙은 화면 요소 자체가 없었다 — 사용자는 '규칙 3/3 초록불'을 보고 제출해도 새 "
     "비밀번호에 자기 로그인 아이디가 들어 있으면(회사명 축약형 등을 아이디로 쓰는 사용자가 비밀번호에도 "
     "같은 조각을 넣는 것은 흔한 습관) 그제서야 서버가 거부한다 — 화면이 '다 됐다'고 말한 뒤 제출에서만 "
     "뒤통수를 치는 구조(round670~672의 '한쪽엔 있는 규칙이 짝에는 없다' 계열이지만, 이번 짝은 색상 "
     "매핑이 아니라 서버 검증 규칙 대 화면 실시간 체크리스트라는 새 쌍). 이 세션 사상 한 번도 정밀조사 "
     "되지 않은 파일(round295가 '미조사 템플릿 7종'을 훑을 때도 change_password.html은 죽은 계정 "
     "_account_alive() 누락 한 건만 고쳤을 뿐 이 체크리스트는 손대지 않음)에서 직접 발견. 고침 — (a) "
     "app.py change_password_page()(1427행)가 세션의 실제 로그인 아이디(원계정·하위계정 모두 "
     "password_policy_error 호출부와 동일한 session 키 조합: session['admin'] or "
     "session['partner_login'] or session['insurer_login'])를 login_id로 템플릿에 내려준다. (b) "
     "change_password.html이 그 값을 const MY_ID로 받아(tojson으로 안전 이스케이프) checkRule()에 "
     "서버와 같은 대소문자 무시 부분일치 검사를 더해 네 번째 규칙칸(#r_id '아이디 포함 금지')을 "
     "실시간으로 보여준다. 단일 지점 수정 — 서버 검증 규칙(password_policy_error) 자체는 무변경. "
     "build_pages.py 재실행 + test_scan_round306_fixes.py(11/11)·test_template_js.py(9/9) 표준 재검증 "
     "완료. 회귀테스트(test_scan_round673_fixes.py, 32개 검사, node 필요) 신설 — [1] 소스: login_id "
     "전달과 템플릿의 #r_id·MY_ID·set('r_id',...) 존재를 정규식으로 확인. [2] 단위: 협력사·보험사·"
     "관리자 세 역할 실제 로그인 후 실제 GET /change-password가 내려주는 진짜 렌더 결과에서 JS를 그대로 "
     "잘라내 Node로 실행, 규칙①②④는 만족하지만 아이디를 포함한 비밀번호에 대해 r_id 칸이 실제로 꺼짐을 "
     "확인하고 같은 케이스를 서버 실제 함수 password_policy_error() 직접 호출과 교차검증. [3] 종단: "
     "세 역할 모두 화면에 박히는 아이디가 실제 로그인 아이디와 일치함을 확인, 실제 POST "
     "/api/change-password로 아이디 포함 비밀번호는 400(에러문구에 '아이디')·아이디 없는 비밀번호는 "
     "200 성공을 실측. [4] 되돌리기-증명 — 잘라낸 JS에서 MY_ID·set('r_id',...)만 제거한 옛 버전(실제 "
     "파일 무변경)은 같은 비밀번호에 대해 규칙①②④ 세 칸은 전부 켜지고 r_id 칸 자체가 존재하지 않았음을 "
     "재현해, 그 순간에도 서버는 이미 거부하고 있었다는 인과관계를 대조했다. app.py+"
     "templates/change_password.html 변경, API 계약·DB 스키마 무변경 — 재기동 후 BUILD_HASH 로테이션 "
     "확인 필요."),
    ("test_scan_round674_fixes.py",
     "스캔 674라운드 회귀(직접조사, 하위위임 없음) — billing_guide()(GET /report/billing, 관리자· "
     "발주처·협력사 세 주체 공용 화면)가 미인증 방문과 계정사망(퇴출·해지 등) 두 갈래 모두 조건 없이 "
     "redirect('/admin/login')였던 결함. round673이 남긴 '테스트 파일 언급수가 적은 순' 기법으로 "
     "templates/billing_guide.html(언급 2건, round295가 화면 자체는 이미 클린으로 결론)을 다시 열어 "
     "이번엔 화면이 아니라 그 화면을 감싸는 app.py 라우트의 리다이렉트 목적지를 봤다. 이 화면의 실제 "
     "진입로는 insurer_portal.html·partner_portal.html 두 곳의 target=_blank 새 탭 링크뿐이라(admin.html "
     "에는 링크가 아예 없음) 실사용자는 사실상 전부 발주처·협력사인데, 오래 열어 둔 포털 탭에서 세션이 "
     "끊긴 뒤(만료·다른 기기 로그아웃 등) 그 링크를 누르면 관리자 아이디·비밀번호 입력창(/admin/login)에 "
     "갇혔다 — 그 화면에 쓸 수 있는 아이디 자체가 없다. round161(test_scan_round161_fixes.py:120~122)이 "
     "정확히 '협력사 퇴출 뒤 같은 세션 재요청' 케이스를 이미 회귀로 남겼지만 상태코드(302)만 확인하고 "
     "Location 값은 검사한 적이 없어 여러 라운드 동안 초록불이었다. 형제 insurer_api_guide()(admin+insurer "
     "두 주체 전용)는 처음부터 역할이 하나뿐이라 /insurer/login 하나로 옳았다 — billing_guide()만 세 "
     "주체라 실제로 '역할을 모르는 방문'이 생기는데도 구분 없이 관리자용으로 뭉뚱그린 것이 이번 결함. "
     "_account_alive()는 _dead_account_response()와 달리 session을 지우지 않아 계정사망 분기에서도 "
     "partner_id/insurer_id가 세션에 남아 있음을 실측으로 확인. 고침 — (a) 세션이 전혀 없는 분기는 역할을 "
     "알 방법이 없으므로 세 포털 링크를 모두 가진 랜딩(/)으로, (b) 계정사망 분기는 세션에 남은 값으로 "
     "partner_id면 /partner/login·insurer_id면 /insurer/login·그 외(admin)는 원래대로 /admin/login — "
     "partner_portal()·insurer_portal()이 이미 쓰는 것과 같은 목적지를 재사용(새 화면·새 상수 없음). "
     "_account_alive·_admin_ip_denied·compute_fee·split_vat 등 검증 로직은 전부 무변경, 바뀐 것은 "
     "리다이렉트 문자열뿐. app.py만 수정(templates/billing_guide.html 자체는 무변경)이라 build_pages.py·"
     "test_template_js.py 재실행 대상 아님. 회귀테스트(test_scan_round674_fixes.py, 28개 검사) 신설 — "
     "[1] 소스: billing_guide() 함수 경계 안에서 무조건적 /admin/login이 admin 전용 최종 폴백 한 곳만 "
     "남았는지, 두 분기에 랜딩·역할별 목적지가 실제로 있는지, 세 리다이렉트가 partner→insurer→admin 순서로 "
     "나타나는지 확인, 형제 insurer_api_guide()는 무변경(회귀 없음)임도 확인. [2]+[3] 단위+종단(이 화면은 "
     "판정 로직 자체가 라우트 함수 안 조건문이라 실제 HTTP 왕복 없이 분리할 단위 계층이 없어 통합): "
     "스크래치 DB에 협력사·보험사·관리자 세 계정을 만들어 실제 로그인 후 각 status를 퇴출·해지로 바꾸거나 "
     "계정 행을 지워 같은 세션으로 GET /report/billing 재요청 — Location이 각자 자기 역할의 로그인 화면 "
     "(관리자는 원래대로 /admin/login)인지 실측, 완전 비로그인 새 클라이언트는 Location이 '/'인지 확인, "
     "활성 상태에서는 그대로 200(과잉차단 아님)도 함께 확인. [4] 되돌리기-증명 — "
     "app.view_functions['billing_guide']를 고치기 전 두 분기(둘 다 무조건 /admin/login, 나머지는 지금 "
     "고친 실제 함수에 위임)로 일시 교체해 같은 세 시나리오를 재요청하면 퇴출된 협력사·해지된 보험사· "
     "비로그인 방문자 모두 /admin/login으로 떨어짐을 재현하고 finally로 원래 함수를 되돌린 뒤 복원까지 "
     "재확인 — 실제 파일은 전혀 건드리지 않았다. app.py만 변경, API 계약·DB 스키마 무변경 — 재기동 후 "
     "BUILD_HASH 로테이션 확인 필요."),
    ("test_scan_round675_fixes.py",
     "스캔 675라운드 회귀(직접조사, 하위위임 없음) — 변경견적 재경매(추가분·전체재경매) 입찰 자격이 있는 "
     "업체가 그 사건의 사진·상세를 볼 방법이 전혀 없던 결함. round674 핸드오프의 '언급수 낮은 순' 기법을 "
     "다시 계산해 보니(version.html 0건·error.html/insurer_login.html/partner_login.html 각 1건 등) 전부 "
     "이미 여러 라운드가 클린으로 결론 낸 화면이라 이 기법 자체가 말라 있었다 — 대신 partner_portal.html의 "
     "11개 RENDER 패널 중 핸드오프가 '이미 감사됨'으로 분류하지 않은 reauction 패널을 직접 열어 그 패널이 "
     "부르는 백엔드 게이트를 끝까지 따라갔다. RENDER.reauction(변경 견적 재경매 입찰 화면)은 접수번호·공종·"
     "지역·증액사유·입찰 상한만 보여줄 뿐 사진을 볼 방법이 전혀 없었는데, 정작 이 흐름 자신의 설계 문서"
     "(app.py 11169·11172행 '…추가사진')는 원업체가 거절해 전체재경매로 넘어갈 때 '추가사진 붙여' 연다고 "
     "명시한다 — 사진이 있는데 볼 방법이 없는 상태. 원인은 사진 열람의 단일 판정 지점인 _is_biddable"
     "(conn, case_id)(round565가 이미 api_partner_case_detail을 여기로 통일해 둔 바로 그 헬퍼)가 원경매"
     "(a.change_order_id IS NULL, cases.status='입찰중')만 보고 변경견적 재경매는 전혀 판정하지 않은 것 — "
     "재경매는 이미 낙찰된 뒤(cases.status='시공중' 등)라 이 조건이 항상 거짓이었다. 그 결과 재경매 자격이 "
     "있는(=/api/reauctions 목록에 뜨는) 제3의 업체가 ① _photo_visible_to()의 시공사진 파일 열람 "
     "② api_case_photos()의 bidder_only 판정(GET /api/cases/<cid>/photos) ③ api_partner_case_detail()의 "
     "'남의 사건' 상세 열람(GET /api/partner/cases/<cid>/detail) 세 곳 모두에서 403을 받았다(전부 실측 "
     "재현) — 확대된 공사범위에 사진 한 장 없이 총액을 적으라는 것과 같다(2차입찰을 '사진이 다 올라온 "
     "뒤에만' 여는 이 코드베이스 자신의 설계원칙과 정면으로 모순). 고침 — (a) app.py _is_biddable(): 기존 "
     "원경매 조건이 거짓일 때 /api/reauctions(22415행 근처)이 이미 쓰는 것과 같은 조건(au.status='진행'· "
     "마감 전·change_order 존재·co.status IN ('추가경매중','전체재경매중'))으로 한 번 더 확인해 True를 "
     "반환 — 단일 지점 수정이라 이 헬퍼를 부르는 세 소비처가 전부 무변경으로 함께 고쳐진다. (b) "
     "templates/partner_portal.html RENDER.reauction: 원경매 목록(1057행)이 이미 쓰는 data-act=\"caseDetail\" "
     "액션(전역 ACT.caseDetail, 새 함수 없음)을 재사용해 '현장 사진·상세' 버튼 한 줄만 추가 — /api/reauctions "
     "응답에는 case_id가 이미 내려오고 있어(22409행) 프런트 응답 스키마 변경은 없다. build_pages.py 재실행 "
     "+ test_scan_round306_fixes.py(11/11)·test_template_js.py(9/9) 표준 재검증 완료. 회귀테스트"
     "(test_scan_round675_fixes.py, 25개 검사) 신설 — [1] 소스: _is_biddable()에 원경매 조건 잔존(회귀 "
     "없음)·change_orders 조인 신설·/api/reauctions와 동일한 상태집합 재사용을 확인, 템플릿의 새 "
     "data-act=\"caseDetail\" 버튼과 그 액션이 이미 등록돼 있음도 확인. [2] 단위: 살아있는 전체재경매·마감 "
     "지난 재경매·아직 '실사요청' 단계·변경견적 자체가 없는 사건·평범한 원경매 다섯 가지를 스크래치 DB에 "
     "만들어 _is_biddable() 직접 호출로 대조(과잉차단 방지 포함). [3] 종단: 재경매 자격이 있는 제3의 업체 "
     "세션으로 실제 GET 세 개(상세·사진목록·사진파일) 전부 200으로 열림과 damage_photos 집계·redact 유지를 "
     "실측, 마감 지난 사건·변경견적 없는 사건은 여전히 403임도 함께 확인. [4] 되돌리기-증명 — 고치기 전 "
     "원문 그대로의 _is_biddable을 별도 함수로 정의해 A._is_biddable 모듈 속성만 잠깐 바꿔친 뒤 같은 실제 "
     "HTTP 요청 두 개가 다시 403으로 재현됨을 확인하고 finally로 즉시 원상복구, 복구 후 재요청이 다시 "
     "200임까지 확인 — 실제 파일은 전혀 건드리지 않았다. app.py+templates/partner_portal.html 변경, API "
     "계약·DB 스키마 무변경(응답 필드 추가 없음) — 재기동 후 BUILD_HASH 로테이션 확인 필요."),
    ("test_scan_round677_fixes.py",
     "스캔 677라운드 회귀(직접조사, 하위위임 없음) — 운영 콘솔(static/admin.js) statusPill()이 하자(defects) "
     "상태값 DEFECT_FLOW(app.py — [\"접수\",\"확인중\",\"재시공배정\",\"완료\",\"반려\"]) 중 '확인중'·'재시공배정' "
     "두 개의 색상 매핑을 통째로 빠뜨리고 있던 결함. round644/672가 세운 '상태값→색상 매핑은 세 형제 "
     "(insurer_portal.html stTag·partner_portal.html stTag·admin.js statusPill)로 존재하고 동기화돼야 "
     "한다'는 원칙을 이어받아, round672가 자기 라운드가 늘린 키만 검증하고 멈춘 지점에서 하자 상태 다섯 "
     "값 전체를 세 매핑과 대조했다 — insurer_portal.html·partner_portal.html stTag()는 이미 "
     "확인중=blue·재시공배정=amber를 갖고 있는데(하자 목록 stTag(d.status) 호출부가 실제로 이 값을 받는다) "
     "admin.js statusPill()에만 두 키가 처음부터 없었다(round672와 정반대 방향 — 그때는 보험사 포털만 "
     "빠졌었다). 실제 소비처는 admin.js 자신의 하자 목록·상세 모달 두 곳(statusPill(d.status)), 매핑에 "
     "없으면 자신의 기본값(회색)으로 떨어져 '확인중'·'재시공배정'이 '완료'·'반려'와 구분 없이 똑같은 회색 "
     "pill로 보였다 — admin.js 자신의 DEFECT_FLOW 상수 복사본과 defectAct 버튼(data-arg2=\"확인중\"/"
     "\"재시공배정\")이 이미 이 두 값을 매일 다루고 있음을 스스로 증명한다. 고침 — admin.js statusPill() "
     "매핑에 '확인중':'blue'·'재시공배정':'amber' 추가해 형제 stTag() 둘과 맞춘다(단일 지점 수정, 다른 키 "
     "무변경). templates/*.html 무변경이라 build_pages.py 대상 아님. test_template_js.py(9/9)· "
     "test_scan_round306_fixes.py(11/11) 표준 재검증 완료 — 단, 조사 중 test_template_js.py의 "
     "<script[^>]*>(.*?)</script> 정규식은 admin.html이 admin.js를 <script src=...>로 외부참조만 하는 "
     "지점에서는 내용을 못 얻어(빈 문자열로 필터링됨) admin.js 소스 자체를 실제로는 한 번도 검사하지 "
     "못해 온 사각지대를 발견(이번엔 별도로 node --check 직접 실행으로 보강, round678 핸드오프로 남김 — "
     "이번 라운드에서는 손대지 않음). 회귀테스트(test_scan_round677_fixes.py, 38개 검사) 신설 — [1] 소스: "
     "admin.js를 node --check로 직접 파싱, 세 매핑에서 두 값을 직접 추출해 일치 확인, 이번 수정이 3사 "
     "공통집합을 정확히 두 개만 늘렸음을 자기완결적으로 확인(매직넘버 없음), app.py DEFECT_FLOW와 admin.js "
     "자신의 DEFECT_FLOW 복사본이 다섯 값 모두 일치함을 확인, 실제 호출 지점·defectAct 버튼도 구조적으로 "
     "확인. [2] 단위 — 세 함수를 파일에서 그대로 잘라내 Node.js로 실행해 두 상태 모두 세 함수가 일치하는 "
     "색을 냄을 증명(기존 값 회귀 없음도 함께 확인). [3] 종단 — 스크래치 DB+실제 Flask 라우트로 하자 한 "
     "건을 만들어 PATCH /api/defects/<id>로 '접수'→'확인중'→'재시공배정'을 실제로 전이시키고 GET "
     "/api/defects(운영 콘솔이 그대로 쓰는 응답)가 그 리터럴 문자열을 그대로 돌려줌을 실측. [4] "
     "되돌리기-증명 — 잘라낸 (고친) admin 소스 문자열에서 두 키:값만 제거한 사본(실제 파일 무변경)을 같은 "
     "Node 실행에 넣으면 admin만 회색으로 되돌아가 형제 두 함수(파랑/주황)와 갈라짐을 재현. static/admin.js"
     "만 변경, API 계약·DB 스키마 무변경 — 재기동 후 BUILD_HASH 로테이션 확인 필요."),
    ("test_scan_round678_fixes.py",
     "스캔 678라운드(직접조사, 하위위임 없음) — 기능 버그가 아니라 안전망 자체(test_template_js.py)의 "
     "커버리지 사각지대를 메운다. round677이 발견하고 손대지 않은 것: test_template_js.py는 각 템플릿을 "
     "렌더해 `<script[^>]*>(.*?)</script>`로 태그 사이 본문만 뽑아 node --check 하는데, admin.html은 "
     "static/admin.js를 `<script src=\"{{ asset('admin.js') }}\"></script>`로 외부 참조만 해서 본문이 "
     "비어(if s.strip()에 걸러짐) admin.js 자신은 이 파일이 9/9 통과를 찍는 동안 단 한 번도 node --check를 "
     "받은 적이 없었다 — actions.js·lightbox.js·addrpick.js·form.js·tray.js·upqueue.js·leaflet.js도 같은 "
     "사각지대. 안전규칙 문서가 'static/admin.js를 고치면 test_template_js.py를 재실행하라'고 이 세션에서 "
     "15회 넘게 요구해 온 전제와 실제 커버리지가 어긋나 있었다. 고침(test_template_js.py) — 각 템플릿을 "
     "렌더할 때 이미 갖고 있는 HTML에서 `<script src=\"/static/....js\">`를 정규식(r'<script\\b[^>]*\\b"
     "src=\"([^\"]+)\"')으로 직접 뽑아(하드코딩 목록이 아니라 그 순간 렌더 결과를 신뢰) 실제 파일 경로로 "
     "접어, 인라인처럼 잘라낼 필요 없이 원본을 그대로 node --check한다(같은 파일이 여러 템플릿에서 "
     "참조되면 한 번만 검사). 오늘 리포지토리 실측 — 9개 템플릿에서 정확히 8개의 고유 static/*.js 파일이 "
     "발견되고(admin.js·actions.js·addrpick.js·form.js·leaflet/leaflet.js·lightbox.js·tray.js·"
     "upqueue.js) 전부 통과(sw.js는 <script src=>로 참조 안 돼 대상 밖). 부수 발견(같이 고침) — 이 환경"
     "(경로에 한글 사용자명 '개발자3'이 낀 Windows)에서 실측하다가, node --check를 부르는 두 subprocess.run"
     "(기존 인라인용 1곳 + 이번에 늘린 외부참조용 1곳) 모두 encoding을 안 준다는 것을 발견 — node가 실제 "
     "에러에서 그 경로를 찍으면 파이썬 내부 리더 스레드가 OS 로케일(cp949)로 잘못 디코드하다 죽는다. "
     "프로세스 전체는 안 죽지만(실측: 예외가 메인 스레드로 전파 안 됨) r.stderr가 None이 되어 정작 필요한 "
     "실패 원인 메시지가 사라지고 콘솔엔 무관해 보이는 스레드 traceback만 남는다 — '실제로 파싱해 보는 "
     "것만이 증거다'라는 이 파일의 취지가 정작 실패했을 때의 상세 진단에서는 무력화되는 결함이었다. 두 "
     "호출 모두 encoding=\"utf-8\", errors=\"replace\"를 추가해 이 배터리의 다른 서브프로세스 호출"
     "(run_all_tests.py의 run() 등)과 관례를 맞췄다. 새 test_scan_roundNNN 파일이 아니라 기존 테스트 "
     "인프라 파일 자체를 고치는 것이라 이번 회귀테스트(test_scan_round678_fixes.py, 45개 검사)는 '그 고침이 "
     "실제로 사각지대를 메우는가'를 증명하는 데 집중한다 — [1] 소스: test_template_js.py 자신에서 새 "
     "정규식·새 subprocess 호출(fp를 직접 검사, 임시추출 아님)·중복제거 구조·encoding kwargs 두 곳 모두를 "
     "실제로 잘라내 확인(손으로 재입력 안 함), 새로 늘어난 코드 블록(주석 제외)에 .js 파일명이 따옴표 "
     "리터럴로 박혀 있지 않음을 확인해 동적 탐색임을 증명, 기존 인라인 정규식은 이번 라운드에서 안 건드렸음도 "
     "확인. [2] 단위 — 실제 test_template_js.py를 스크래치 DB로 서브프로세스 실행해 오늘 리포지토리에 대해 "
     "정말 통과하는지, 8개 파일 전부를 이름으로 실제로 언급하는지 확인하고, 템플릿 원문을 독립적으로(렌더가 "
     "아니라 소스 정규식으로) 다시 스캔해 그 개수·이름 집합이 일치함을 대조. [3] 인과관계 실측 — 실제 "
     "admin.html을 렌더해 (a) 옛 인라인 정규식이 admin.js의 실제 내용(특징 토큰 'function statusPill')을 "
     "단 한 글자도 못 본다는 것과 (b) 새 정규식은 그 자리에서 실제 static/admin.js 절대경로를 정확히 "
     "복원한다는 것을 같은 렌더 결과로 동시에 증명한 뒤, 실제 admin.js 바이트를 스크래치 사본으로만 떠서"
     "(원본 무변경) 정상 사본은 node --check 통과·마지막 '}' 한 글자만 제거한 손상 사본은 실패로 갈리는 "
     "것을 실측(옛 경로는 손상 여부와 무관하게 늘 통과, 새 경로는 정확히 반응). 이어서 encoding 부수발견도 "
     "같은 손상 사본으로 재현 — encoding 없이 돌리면 returncode는 정상(1)인데 stderr가 None이 되어 진단이 "
     "사라짐을, encoding=\"utf-8\"을 주면 정상 메시지가 실려 옴을 나란히 실측. 실제 static/admin.js·"
     "templates/admin.html은 시종일관 무변경(스크래치 사본만 다룸)임을 마지막에 바이트 비교로 재확인. "
     "test_template_js.py만 변경(templates/*.html·static/*.js 무변경)이라 build_pages.py 재실행 대상 "
     "아니고, app.py가 import하지 않는 테스트 전용 파일이라 재기동·BUILD_HASH 로테이션도 불필요 — "
     "run_all_tests.py --quick 전체 배터리 재확인 완료."),
    ("test_scan_round679_fixes.py",
     "스캔 679/680라운드(직접조사, 하위위임 없음) — round679이 round678 핸드오프 각도1을 AST 전수감사로 "
     "완주(grep '~31곳' 추정 대신 247곳 전수분류, 진짜 위험 12곳 확정)했으나, 그중 manage.py의 "
     "cmd_install_scheduler() 세 schtasks 호출에 넣은 핵심 전제(\"schtasks.exe는 항상 UTF-8 바이트를 "
     "낸다\")가 **틀려 있었다** — round680이 이 PC에서 원시 바이트를 직접 strict 디코드 비교하니 "
     "정반대(cp949)였다. encoding=\"utf-8\" 강제를 빼고 cp949 로케일 기본값에 errors=\"replace\"만 "
     "방어로 남기는 선에서 1차 정정했는데, run_all_tests.py 배터리(콘솔 없는 중첩 파이프 실행 맥락) "
     "안에서 재현 가능하게(2/2) UnicodeDecodeError로 크래시가 났다 — 크래시 당시의 원시 출력을 열어 "
     "보니 이번엔 거꾸로 **영어 UI**(\"Folder:\"·\"TaskName\" 등)로 나오며 그 경우엔 utf-8이 맞고 "
     "cp949가 깨졌다. 결론 — schtasks.exe 자신의 UI 언어·인코딩이 실행 맥락(콘솔 부착 여부 등, "
     "근본원인 미확정)에 따라 한글(cp949)·영어(utf-8) 두 가지 모두로 실제 갈린다 — \"어느 한쪽이 "
     "진짜다\"라는 전제 자체가 틀렸다. 최종 고침 — text=True(고정 인코딩 하나만 시도, 실패 시 "
     "백그라운드 리더스레드가 죽어 stdout 전체가 조용히 None이 됨) 자체를 버리고, 세 호출 모두 원시 "
     "바이트로만 캡처한 뒤 새로 만든 로컬 헬퍼 _decode_schtasks()(cmd_install_scheduler() 안)가 "
     "메인 스레드에서 직접 utf-8 → cp949 → cp949+errors=\"replace\"(최후 방어선) 순서로 디코드한다 — "
     "리더스레드 크래시 자체가 구조적으로 불가능해지고, 어느 인코딩이 오든 실제로 견딘다. 나머지 "
     "9곳(node·bash 호출 — test_scan_round12·168·289·310·311(2곳)·677_fixes.py)은 손대지 않음 — "
     "Node.js·Git Bash는 네이티브 Win32 콘솔 도구와 달리 자체적으로 UTF-8을 쓰는 경향이 있고(round678의 "
     "원래 node --check 발견과 같은 근거), 반증을 못 찾아 그대로 둠(round679이 발견한 round310/311의 "
     "r.stderr[-300:] None가드 없음도 그대로 유효). 회귀테스트(test_scan_round679_fixes.py, 36개 검사, "
     "round680이 재작성) — [1] manage.py 3곳이 text=True·encoding= 둘 다 없는 순수 원시 바이트 캡처임과 "
     "_decode_schtasks()의 utf-8→cp949 순서·최후 방어선을 실제 소스에서 확인, 저장소 전수 AST 재감사로 "
     "'위험' 집합이 정당한 대조군 2곳(round591 time.sleep+round678 r_bad_noenc)뿐임을 확인(manage.py "
     "세 곳은 text=True 자체가 없어져 이 위험 조건에서 구조적으로 빠짐). [2] 실제 _decode_schtasks() "
     "함수 본문을 소스에서 그대로 잘라 exec, 같은 한글 포함 문자열을 cp949로 인코드한 바이트열과 "
     "utf-8로 인코드한 바이트열 **둘 다**에 적용해 양쪽 모두 원문 그대로 복원됨을 직접 증명(스키마 "
     "의존적 실측이 아니라 결정론적 합성 데이터로 증명). [3] 진짜 설치된 운영 작업 '복구온_경매마감'을 "
     "상대로(읽기전용 /Query만) 지금 이 순간 실제로 어느 인코딩이 오든 크래시·None 없이 디코딩됨을 "
     "실측. [4] 되돌리기-증명 — round679(utf-8 강제)는 cp949 바이트열에서, round680 1차 정정(cp949 "
     "강제)은 utf-8 바이트열에서 각각 반드시 깨짐을 재현해 대조, 새 _decode_schtasks()만 두 시나리오 "
     "모두를 견딤을 증명. manage.py는 app.py가 import하지 않고 templates/static도 무변경이라 재기동·"
     "BUILD_HASH 로테이션 불필요 — run_all_tests.py --quick 전체 배터리로 재확인(재현되던 크래시가 "
     "사라졌음을 반복 실행으로 확인 완료)."),
    ("test_scan_round681_fixes.py",
     "스캔 681라운드 회귀(직접조사, 하위위임 없음) — static/admin.js의 dispatches.status 전용 색상 맵 "
     "DP_ST()가 같은 필드를 그리는 형제(templates/insurer_portal.html의 dpCell()→stTag(d.status))와 "
     "5개 키 중 3개가 어긋나 있던 결함. round75/644/672/677은 '상태값→색상 매핑은 세 형제(insurer "
     "stTag·partner stTag·admin statusPill)로 존재한다'는 전제로 그 세 곳만 대조해 왔는데, admin.js "
     "안에는 그 세 형제와 별개로 dispatches.status(모집중/수배됨/도착/실패/취소 — dispatch.py "
     "ST_OPEN·ST_CLAIMED, db.py 728행 스키마 주석이 전체 정의역임을 증언) 전용의 네 번째 미니맵 DP_ST가 "
     "따로 있었고, 지금까지 어떤 회귀 테스트도 'DP_ST'를 언급한 적이 없었다(직접 grep 확인, 0건). 실측 "
     "대조 결과 '모집중'·'수배됨'은 색이 통째로 뒤바뀌어 있었다(DP_ST: 모집중=blue·수배됨=amber ↔ "
     "insurer stTag: 모집중=amber·수배됨=blue). '취소'는 이 저장소 전체에서 DP_ST만 유일하게 'gray'였다 "
     "— insurer stTag·partner stTag·admin statusPill 셋 다 이미 'red'로 일치(정확히 round75가 세운 "
     "'취소는 회색이면 안 된다' 원칙의 대상인데 이 네 번째 맵에는 못 지켰다). 도착·실패 2개는 원래부터 "
     "일치. 셋 다 도달 가능한 정상 값(dispatch.py의 실제 개시·수락 경로, app.py 5375행 UPDATE dispatches "
     "SET status='취소')이라 같은 출동 콜이 관제 콘솔(VIEWS.dispatch 목록·dispatchDetail 모달)과 보험사 "
     "포털(사건 목록 진행 열)에서 서로 다른 색으로 보인다 — round644와 동일한 성격의 결함. 고침 — "
     "admin.js DP_ST 정의(단일 지점 — 4677·4851행 두 호출부가 이 상수 하나를 물려받는다)를 insurer "
     "stTag 값에 맞춘다: 모집중=amber·수배됨=blue·취소=red(도착·실패 무변경). admin.js는 <script src>로만 "
     "참조돼(admin.html 안에 인라인되지 않음, round678 확인 사항) build_pages.py 재실행 대상이 아니고, "
     "test_template_js.py(17/17, admin.js 포함 외부참조 8개 전부) 표준 재검증 완료. 회귀테스트"
     "(test_scan_round681_fixes.py, 61개 검사) 신설 — [1] 소스: DP_ST와 insurer stTag에서 5개 키 값을 "
     "직접 추출해 전부 일치 확인, '취소'는 partner stTag·admin statusPill과도 일치 확인, 실제 호출 "
     "지점(DP_ST[x.status]·DP_ST[v.status]·stTag(d.status))과 재현 가능성 근거(ST_OPEN/ST_CLAIMED "
     "상수·UPDATE ... status='취소'·db.py 스키마 주석)를 소스에서 직접 정규식으로 확인. [2] 단위 — "
     "DP_ST 객체 리터럴과 세 형제 함수를 파일에서 그대로 잘라내 Node.js로 실행해, admin.js 실제 호출부와 "
     "바이트 단위로 같은 인라인 표현식으로 만든 배지가 5개 상태 전부에서 형제와 같은 색 클래스를 냄을 "
     "증명. [3] 종단 — (a) 실제 Flask 정적 파일 서빙(GET /static/admin.js)으로 고친 리터럴이 응답 "
     "바이트에 그대로 담김을 확인, (b) 스크래치 DB+실제 Flask 라우트 두 개(GET /api/dispatches 관리자용, "
     "GET /api/insurer/dashboard 보험사용)로 5개 상태의 출동 콜을 실제로 만들어 두 라우트가 정확히 같은 "
     "원본 문자열을 내려줌을 실측. [4] 되돌리기-증명 — 잘라낸 (고친) DP_ST 문자열에서 3개 키만 옛 값으로 "
     "되돌린 사본(실제 파일 무변경)을 같은 Node 실행에 넣으면 그 3개 상태만 형제와 다른 색이 되어 결함이 "
     "재현됨을 확인, 안 건드린 도착·실패는 옛 버전에서도 이미 일치했음도 함께 확인. static/admin.js만 "
     "변경, API 계약·DB 스키마 무변경 — 재기동 후 BUILD_HASH 로테이션 확인 필요."),
    ("test_scan_round688_fixes.py",
     "스캔 688라운드 회귀(직접조사, 하위위임 없음) — round594가 \"app.py 전체 name= 류 SQL 바이트비교\" "
     "전수확인 중 같은 결함군의 두 번째 인스턴스로 지목만 하고 별도 태스크(task_f15d21d5)로 이관해 둔 "
     "api_application_create(입점신청 직접접수, POST /api/applications/manual)의 업체명 중복확인을 "
     "실제로 고쳤다. ⚠ 라운드 번호 경합(두 번) — 이 저장소는 git 없이 여러 세션이 동시에 돌 수 있어"
     "(round279~281 선례) 이 작업이 실제로 두 번 부딪혔다: 처음 \"682\"로 쓰던 중 다른 세션이 완전히 "
     "무관한 건(check_subcontractor 화면배선)으로 682번을 먼저 선점해 test_scan_round682_fixes.py를 "
     "그대로 덮어썼고, \"683\"으로 옮겨 다시 쓰자 그 세션도 같은 타이밍에 독립적으로 683으로 옮겨와 "
     "다시 부딪혔다. ListAgents로 그 세션을 실제로 찾아 SendMessage로 조율해(양쪽 다 서로의 결과물을 "
     "건드리지 않기로 확인) 688번으로 최종 이동했다 — app.py 수정분(다른 함수, 다른 파일영역)은 두 "
     "충돌 모두에서 무사했고, 테스트 파일·등록 항목만 그때마다 새 번호로 옮겨 다시 적는다. 결함 — \"SELECT id, "
     "status FROM partner_applications WHERE company=? AND status IN ('신규','서류검토')\"가 단순 SQL "
     "바이트열 비교라, 유니코드 정규화 형태만 다른(한글 자모를 완성형 대신 풀어쓴 NFD 등 — 맥에서 복사한 "
     "텍스트에 흔하다) 같은 업체명이 이 중복확인을 그대로 통과해 심사대기 상태로 같은 업체의 대기 신청서가 "
     "두 번 쌓일 수 있었다(사업자번호가 있으면 승인 시점 biz_no 교차확인이 안전망이 되지만, 없거나 신청마다 "
     "다르게 기재되면 그 안전망도 없다). ⚠ 조사 중 확인 — 과제 설명이 말한 \"공개 폼 형제가 같은 SQL을 "
     "쓴다\"는 현재 코드와 다르다: 공개 폼(api_create_application, POST /api/applications)의 중복확인은 "
     "recent_duplicate()(업체명+전화번호+10분 창의 재전송 방지, status 무관)뿐이고 이 status 기반 심사대기 "
     "중복확인 자체가 없다 — 위협모델이 달라(10분 내 같은 탭 재전송 방지 UX 디바운스, 심사대기 중복방지가 "
     "아님) 이번 수정 대상에서 제외했다(recent_duplicate() 자체의 정규화는 별도 검토 대상으로 남겨 둠). "
     "고침 — round458(등록 시점 단 한 곳만 정규화하면 끝나는 단일 쓰기경로)이 아니라 round593(연락처 "
     "일괄등록 업체명 대조 — 저장을 막는 대신 대조 자체를 정규화 후 비교로 바꾸는 처방)과 같은 이유·같은 "
     "처방을 썼다: company 컬럼은 이 함수와 공개 폼 두 경로가 각자 다른 시점에 채우고 db.py에 정규화 "
     "마이그레이션도 없어 저장값의 정규화 형태를 보장할 수 없기 때문이다. 지금 심사대기 중(status IN)인 "
     "후보만 읽으면 되므로(round593의 partners 전체 400여 곳과 달리 이미 좁은 대상) round593처럼 잠금 "
     "앞으로 뺄 것도 없이 BEGIN IMMEDIATE 안에서 그대로 NFKC 정규화 대조로 바꿨다 — round553이 세운 "
     "잠금(BEGIN IMMEDIATE → rollback+close)은 그대로 유지. 새 헬퍼·새 컬럼·새 정책 없음. 회귀테스트"
     "(test_scan_round688_fixes.py, 16개 검사) 신설 — [1] 소스: 새 정규화 비교가 실제로 있고 옛 "
     "바이트비교 SQL은 없음, BEGIN IMMEDIATE·status IN 필터 유지 확인. [2] 핵심 재현 — 실제 Flask 뷰 "
     "함수(test_request_context+관리자 세션)로 NFC 업체명을 접수한 뒤 그 NFD 표기로 다시 접수하면 409로 "
     "막히고 DB에도 대기 신청서가 정확히 1건만 쌓임을 실측. [3] 되돌림-증명 — unicodedata.normalize를 "
     "프로세스 메모리에서만(디스크 무수정) 항등함수로 바꿔치기하면 같은 시나리오가 그대로 통과해 대기 "
     "신청서 2건이 생김을 실제로 재현한 뒤 원복(이 테스트가 진짜 결함을 잡아낼 능력이 있음을 증명). "
     "[4] 회귀 없음 — 바이트가 완전히 같은 업체명 중복은 예전처럼 그대로 409로 막힘. [5] 인접 안전성 — "
     "(a) 서로 무관한 업체명끼리는 오탐 없이 각각 정상 접수, (b) 이전 신청이 반려(심사대기 상태 아님)면 "
     "정규화 표기만 다른 재신청도 status IN 필터가 그대로 지켜져 정상 접수됨(과잉 차단 아님)을 확인. "
     "최종 16/16 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round690_fixes.py",
     "스캔 690라운드 회귀(직접조사, 하위위임 없음) — 발송 대기함(GET /api/outbox)이 "
     "notifications.is_demo 를 전혀 안 걸러 데모 알림이 목록·집계에 그대로 섞이던 결함. "
     "round88(api_calendar)·round254(sweep_auctions)와 같은 결함 클래스(형제 집계는 "
     "COALESCE(is_demo,0)=0 을 거는데 이 자리만 빠짐)의 새 발생지점 — is_demo 가진 9개 "
     "자식표 기준 app.py 전체 conn.execute() 900건을 정적 스캔(변수 조립 SQL은 함수 "
     "전체 텍스트로 재확인해 오탐 제거)해 찾았다. 실측(운영 DB, 읽기전용): is_demo=1로 "
     "정상 마킹된 알림 67건 중 7건이 status='발송대기'라 이 화면 기본 뷰에 실제로 섞여 "
     "노출 중이었다. notify() 자신의 case_id→is_demo 캐스케이드는 round525/526이 이미 "
     "실시간 INSERT 경로에서 고쳐 놨고(2026-08-05 이후로 case_id 없는 알림이 재발한 적 "
     "없음을 메시지 내 사건번호 역추적으로 실측 확인) — 이번 결함은 캐스케이드가 아니라 "
     "'캐스케이드된 표식을 읽는 쪽'이 빠진 것. 고침 — where·cw 두 초기값을 \"1=1\"에서 "
     "\"COALESCE(is_demo,0)=0\"으로 교체, 새 헬퍼·새 컬럼·새 정책 없음(형제와 완전히 "
     "같은 조건문 재사용). 별도 확인만 하고 손대지 않은 것 — 2026-07-23~08-05 사이 생성된 "
     "레거시 알림 223건(case_id NULL) 중 8건이 실제 데모 사건과 일치하는데 is_demo=0으로 "
     "남아 있다(8/5 이후 재발 없는 과거 데이터 오염이라 코드 결함이 아니고, 운영 DB UPDATE는 "
     "사용자 승인 없이 하지 않는다 — 절대 규칙). 회귀테스트(test_scan_round690_fixes.py, "
     "19개 검사) 신설 — [1] 소스: where·cw 초기값 확인, 무관한 다른 함수의 동명 변수는 "
     "안 건드렸음을 카운트로 확인. [2] 핵심 재현 — 실제 Flask 뷰 함수(test_request_context+"
     "관리자 세션)로 실사건·데모사건 각 1건 알림을 실제로 만들어(notify() 경유) 목록에는 "
     "실사건만, 집계(counts)에는 실사건 개수만 정확히 반영됨을 실측. [3] 종단 — "
     "status=전체&days=0(필터 최대 개방)으로도 데모가 새지 않음을 확인해 우회 경로 없음을 "
     "증명. [4] 되돌림-증명 — where/cw 초기값만 옛 값으로 되돌린 함수 사본을 app 모듈 "
     "전역 네임스페이스로 인메모리 exec(디스크 무수정)해 같은 시나리오를 돌리면 데모 "
     "알림이 실제로 새어 나옴을 재현한 뒤, 실제 app.py 파일이 바이트 단위로 무변경임을 "
     "마지막에 재확인. [5] 인접 안전성 — 검색어(q) 필터는 회귀 없이 그대로 동작. "
     "최종 19/19 통과. app.py 자신을 고쳤으므로 서버 재기동 필요."),
    ("test_scan_round683_fixes.py",
     "스캔 683라운드(직접조사, 하위위임 없음) — round567이 미해결로 남긴 제품판단: "
     "compliance.check_subcontractor()(건산법 §25② 하수급인 자격 판정)가 GET "
     "/api/partners/<pid>/subcontract-check 로만 닿는데 admin.js·templates 어디에도 "
     "호출부가 없는 죽은 라우트였다. round567이 준 두 선택지(①화면 배선 ②round105 선례처럼 "
     "삭제) 중 실제로 확인해 ①을 택했다 — check_subcontractor는 round105의 "
     "api_assign_manager(완전 중복·대체 로직 없음이라 삭제)와 달리 test_compliance.py [6]이 "
     "라우트 없이 직접 단위테스트해 온 고유 법률로직(round106/108이 데이터소스 버그까지 고친 "
     "이력)이라 지우면 검증된 자산이 사라진다. check_subcontractor는 license_block_reason"
     "(dispatch.py 1237행, 수배·배정 진입문 — '미확인'을 통과시킨다)과 다른 질문에 답한다 — "
     "'지금 이 업체에 하도급을 줘도 되는가'(더 엄격한 §25② 고유 질문, round106 주석이 이미 "
     "'미확인을 안전으로 보지 않는 것이 이 함수의 목적'이라고 명시). 고침 — app.py·"
     "compliance.py는 전혀 안 건드리고(서버는 이미 맞다) static/admin.js만 세 곳: (a) "
     "partnerForm()의 '🏛️ 건설업 등록 조사' 패널 끝에 #subcheckbox 자리표시자 추가 (b) 모달을 "
     "열 때 loadAccount(id)와 나란히 loadSubcontractCheck(id) 호출 추가 (c) 그 함수 신설 — "
     "loadAccount/#acctbox와 정확히 같은 '동기 렌더 후 비동기로 하위 패널 채우기' 기존 관례를 "
     "그대로 따른다. 기존 pill(조사현황)과 헷갈리지 않도록 새 줄은 '하도급 적격'이라는 별도 "
     "이름의 법적 판정문(서버 reason 그대로, esc() 처리)으로 나란히 붙였다. 형제 죽은 라우트 "
     "GET /api/contract-gate/rules(api_contract_gate_rules)는 이번 결정 범위 밖이라 손대지 "
     "않았다(여전히 무호출 — 별도 판단 필요, 소스 확인으로 '이번 라운드가 지운 게 아님'을 "
     "명시적으로 남김). ⚠ 라운드 번호 경합 — 이 작업은 처음 round682로 썼으나 이 저장소에 "
     "git이 없는 동시세션 환경에서 다른 세션이 같은 번호를 먼저 run_all_tests.py에 등록해(다른 "
     "결함 — api_application_create NFKC 중복확인, task_f15d21d5) 파일이 겹쳤다(round279~281과 "
     "같은 종류의 실측 위험). 그 세션의 소스 수정(app.py 8160행)은 살아있지만 그 세션 자신의 "
     "회귀테스트 파일은 이 세션의 파일쓰기와 경합해 사라진 상태였다 — git이 없어 복구 불가, "
     "번호를 683으로 옮겨 경합을 정리하고 공백은 별도로 보고한다(이 파일 삭제·이전 자체가 "
     "그 세션 결과물을 건드린 것은 아니다). 회귀테스트(test_scan_round683_fixes.py, 26개 검사) "
     "신설 — [0] 소스: admin.js partnerForm()·loadAccount()·loadSubcontractCheck() 세 "
     "함수 경계를 직접 슬라이싱해 배선 지점·호출 문자열·형태 일치를 확인하고, 고치기 직전 Read로 "
     "확인한 옛 원문 조각(패널 끝부분·모달 오픈 호출)을 문자열로 재구성해 그때는 없었음을 대조군으로 "
     "증명. app.py·compliance.py는 무변경(라우트·check_subcontractor·형제 죽은 라우트 전부 그대로) "
     "확인. [1]+[2] 종단 — 스크래치 DB+실제 Flask 앱으로 무등록·미확인·등록확인·공란(NULL) 네 가지 "
     "license_status를 실제로 만들어 하위관리자(ROLE_RANK 최저 등급) 세션으로 GET을 실행, 응답의 "
     "check 객체가 CP.check_subcontractor() 직접호출과 완전히 같음을 실측(4가지 상태 전부+없는 id "
     "404 회귀 없음). test_template_js.py 17/17 재검증 완료(admin.js 외부참조 파싱 포함) — "
     "admin.js는 <script src>로만 참조돼 build_pages.py 재실행 대상 아님(round678/681과 동일), "
     "API 계약·DB 스키마 무변경이라 재기동 불필요."),
]

#  ── 서버(verify)가 떠 있어야 하고, 로그인을 하므로 간격이 필요한 것들 ──
HTTP = [
    ("test_b4_http.py", "마감 HTTP"),
    ("test_b4_review_fixes.py", "검토 수정 회귀"),
    ("test_e2e.py", "전 구간 E2E"),
    ("test_rehearsal.py", "운영 리허설 45단계"),
    ("test_partner_leak.py", "협력사 유출 전수"),
    ("test_scan_round2_fixes.py", "스캔 2라운드 회귀"),
    ("test_scan_round3_fixes.py", "스캔 3라운드 회귀"),
    ("test_scan_round4_fixes.py", "스캔 4라운드 회귀"),
    ("test_scan_round5_fixes.py", "스캔 5라운드 회귀"),
    ("test_session_liveness.py", "세션 생존"),
    #  ⚠ [라운드248] 여기 있어야 한다 — BASE(기본 127.0.0.1:8799)로 실제 로그인·
    #    OTP확인·복구코드 검증까지 도는 HTTP 테스트인데, 그동안 UNIT(서버 불필요
    #    구간)에 잘못 끼어 있었다. --quick 은 UNIT 만 돌리고 곧장 끝나므로, 이
    #    세션 내내(라운드232~247) 모든 --quick 배터리가 사실은 서버 연결거부를
    #    "OTP 결함"처럼 보고해 왔다 — preflight·GAP 레이트리밋 보호도 없이
    #    돌던 것도 이 오분류 탓. 이제 --quick 은 이 테스트를 아예 건너뛰고,
    #    전체(HTTP 포함) 실행에서만 서버 기동을 전제로 돈다.
    ("test_otp.py", "OTP"),
]

#  ── 자기 서버를 직접 띄우는 것(포트 8790) — 간격 불필요 ──
STANDALONE = [
    ("test_firstday.py", "빈 DB 첫날 완주 60단계"),
]

GAP = 300          # 레이트리밋 창(300초)이 풀릴 때까지
#  ⚠ STAFF_PW 가 빠져 있었다. 그래서 중간관리자 권한 검사들이 **옛 값을 코드에
#    박아 두고** 돌았고, 그 값이 지금 서버와 달라 매번 401 이 났다.
#    필요한 것을 입구에서 다 요구해야 코드에 비밀번호가 박히지 않는다.
NEEDED_ENV = ("BOKGUON_TEST_ADMIN_PW", "BOKGUON_TEST_STAFF_PW",
              "BOKGUON_TEST_INSURER_PW", "BOKGUON_TEST_PARTNER_PW")


def run(script, label, base=None):
    """⚠ **자식에게 어느 서버를 두드릴지 넘긴다.**

      종전에는 안 넘겼다. 그래서 각 테스트가 자기 기본값을 썼는데
      test_b4_http.py · test_b4_review_fixes.py 두 개만 기본이 **8771(운영)** 이었다.
      실행기는 8799 를 점검해 놓고 자식은 운영을 두드리는 상태 —
      로그인이 실패해서 드러났을 뿐, 비밀번호가 맞았으면
      **운영 DB 에 검증 사건이 박혔다.**
    """
    t0 = time.time()
    _env = dict(os.environ)
    #  ⚠⚠ [라운드532] 자식(각 test_scan_roundN_fixes.py)은 capture_output=True 로
    #    **순수 파이프**에 물린다 — 콘솔이 없으니 파이썬은 PYTHONIOENCODING 이
    #    없으면 OS 로케일(이 서비스가 도는 한국어 윈도에서는 cp949)로 stdout 을
    #    연다. 회귀 파일 대부분은 첫 줄부터 "—"(em dash)를 print 하는데 그 문자는
    #    cp949 로 인코딩이 안 돼 UnicodeEncodeError 로 **그 자리에서** 죽는다
    #    (그 파일 자신의 sys.stdout.reconfigure() 방어가 있으면 산다 — round528~
    #    530 등 일부 최신 파일만 있음, 나머지 다수는 없음). 이 실행기 자신은
    #    호출된 셸이 우연히 PYTHONIOENCODING 을 갖고 있으면(PowerShell 프로필 등)
    #    자식도 그걸 물려받아 안 죽지만, 그 값이 없는 셸(예: 이 저장소의 Bash
    #    도구 호출)로 돌리면 실측: UNIT 400여 개 중 자체 방어 없는 다수가 전부
    #    이 이유 하나로 FAIL 처리된다 — 실제 결함이 하나도 없어도 배터리가
    #    거짓 대량 실패를 낸다. 형제(test_scan_round6·7·31·34·49·test_fresh_db·
    #    test_firstday 가 **자기들이 여는** 하위 프로세스에 이미 각자
    #    PYTHONIOENCODING="utf-8" 를 넣는 관례)를 이 유일한 공유 진입점에 한
    #    번만 적용한다 — setdefault 라 호출 셸이 이미 다른 값(예: round518·519
    #    자신의 cp949 강제 재현 테스트)을 정해 뒀으면 그대로 존중한다.
    _env.setdefault("PYTHONIOENCODING", "utf-8")
    if base:
        _env["BOKGUON_TEST_BASE"] = base
    r = subprocess.run([sys.executable, script], cwd=HERE,
                       capture_output=True, text=True, env=_env,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    tail = [ln for ln in out.splitlines() if ln.strip()]
    last = tail[-1][:90] if tail else ""
    mark = "OK  " if r.returncode == 0 else "FAIL"
    print(f"  [{mark}] {label:<28} {last}   ({time.time()-t0:.0f}초)")
    if r.returncode != 0:
        for ln in tail[-14:]:
            print(f"          {ln[:120]}")
    return r.returncode == 0


def server_up(base):
    try:
        urllib.request.urlopen(base + "/partner/login", timeout=5)
        return True
    except Exception:
        return False


def local_build_hash():
    """app.py 가 계산하는 것과 **같은 방식**으로 로컬 코드 해시를 낸다.
       (app.py 를 import 하지 않는다 — 검증 실행기가 앱을 띄우면 안 된다)"""
    import hashlib
    h = hashlib.sha256()
    files = [os.path.join(HERE, "app.py")]
    for d in ("static", "templates"):
        for dirpath, _, names in os.walk(os.path.join(HERE, d)):
            files += [os.path.join(dirpath, n) for n in names
                      if n.endswith((".js", ".css", ".html", ".webmanifest"))]
    for f in sorted(files):
        try:
            with open(f, "rb") as fp:
                h.update(fp.read())
        except OSError:
            pass
    return h.hexdigest()[:8]


def preflight(base):
    """**돌리기 전에** 그 서버가 쓸 만한지 본다.

      ⚠ 왜 필요한가 — 실제로 겪은 것(2026-08-05):
        몇 시간 전 세션이 띄운 서버가 포트를 계속 잡고 있어서, 그날 고친 코드가
        아니라 **옛 코드**를 두드렸다. 게다가 그 서버는 **다른 DB** 를 물고 있어
        로그인부터 전부 401 이었다. 10개 파일 · 50분을 돌리고 나서야 알았고
        결과는 전부 '코드 결함처럼 보이는 거짓 실패'였다.
        포트에 응답이 온다는 것은 "서버가 있다"일 뿐 "**그** 서버다"가 아니다.
    """
    problems = []
    try:
        with urllib.request.urlopen(base + "/api/version", timeout=5) as r:
            info = json.loads(r.read().decode("utf-8"))
        #  ★ **운영 서버에는 붙지 않는다.**
        #    검증은 사건을 만들고 입찰하고 정산까지 밀어 본다 — 운영에 대고 하면
        #    실데이터에 검증 사건이 박힌다. 포트 숫자로 판정하면 포트를 바꾼 순간
        #    무의미해지므로, **서버가 스스로 밝히는 채널**을 본다(dev=개발/prod=운영).
        if (info.get("channel") or "") != "개발":
            problems.append(
                f"이 서버는 채널이 '{info.get('channel')}' 입니다 — "
                f"검증은 **개발(dev) 서버에만** 붙습니다. {base} 를 확인하세요. "
                f"운영에 대고 돌리면 실데이터에 검증 사건이 박힙니다.")
            #  ⚠⚠ [라운드320] 예전엔 여기서 안 멈췄다 — 채널이 운영임을 이미
            #    알아낸 바로 다음 줄이 그대로 빌드해시를 비교하고, 그 아래는
            #    **실제 로그인 POST**까지 그 서버로 보냈다(실측: 격리 스텁
            #    서버로 재현, channel='운영' 감지 후에도 /api/login 요청이
            #    실제로 나감). BOKGUON_TEST_BASE 가 실수로 운영을 가리키면
            #    (독스트링 14~17행이 인용하는 바로 그 사고 부류), 이 로그인
            #    시도가 운영 감사로그에 실패 기록을 남기고 MAX_LOGIN_FAILS
            #    문턱에 근접해 있었다면 실제 관리자를 잠글 수 있었다 — 이
            #    함수가 막으려던 사고를 이 함수 자신이 완성시킬 뻔한 구조.
            #    채널 문제는 다른 문제(빌드해시 낡음)와 성격이 달라 즉시
            #    반환한다 — 빌드해시만 낡은 경우(개발서버는 맞음)는 로그인
            #    시도 자체를 막을 이유가 없어 그 아래로 그대로 흘려보낸다.
            return problems
        srv, loc = info.get("build"), local_build_hash()
        if srv != loc:
            problems.append(
                f"서버가 옛 코드입니다 (서버 build={srv} · 로컬 build={loc}). "
                f"그 서버를 죽이고 지금 코드로 다시 띄우세요 — "
                f"안 그러면 고친 것을 검증하지 못합니다.")
    except Exception as e:
        problems.append(f"/api/version 을 읽지 못했습니다({e}) — 서버 확인 불가")

    #  로그인 1회로 DB·비밀번호를 확인한다(여기서 막히면 이후 전부 401 로 죽는다)
    try:
        req = urllib.request.Request(
            base + "/api/login",
            data=json.dumps({"username": "admin",
                             "password": os.environ.get("BOKGUON_TEST_ADMIN_PW", "")
                             }).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.getcode() != 200:
                problems.append(f"관리자 로그인이 {r.getcode()} 입니다")
    except urllib.error.HTTPError as e:
        problems.append(
            f"관리자 로그인이 {e.code} 입니다 — 서버가 보는 DB 의 비밀번호가 다릅니다. "
            f"BOKGUON_DB_PATH 와 **서버가 실제로 물고 있는 DB** 가 같은 파일인지 보세요.")
    except Exception as e:
        problems.append(f"로그인 시도 실패({e})")
    return problems


def main():
    quick = "--quick" in sys.argv
    nowait = "--no-wait" in sys.argv
    base = os.environ.get("BOKGUON_TEST_BASE", "http://127.0.0.1:8799")

    #  ⚠⚠ [라운드406] BOKGUON_ENV 를 안 정해 주면, manage.py 를 거치는 어떤
    #    하위 테스트든 envload 가 이 저장소의 진짜 .env(BOKGUON_ENV=prod,
    #    실운영용)를 setdefault 로 읽어들여 조용히 "운영 모드"가 된다 —
    #    db.py.init_db() 는 그러면 seed_demo 기본값을 꺼서 보험사·시행사 등
    #    데모 데이터를 아예 안 심는다. BOKGUON_DB_PATH 로 이미 검증 전용
    #    DB 를 가리키게 막아 놓았으니(바로 아래) 이 값을 강제로 "dev" 로
    #    깔아도 운영 DB 에는 전혀 영향이 없다 — 실측: 이 줄 없이 그대로
    #    `python run_all_tests.py --quick` 을 새 DB 로 돌리면 스캔
    #    28·29라운드 회귀가 매번 `SELECT id FROM insurers LIMIT 1` 이
    #    None 을 돌려받아 TypeError 로 죽었다(406라운드가 실제 재현).
    #    setdefault 라 호출자가 일부러 다른 값을 준 경우는 그대로 존중한다.
    os.environ.setdefault("BOKGUON_ENV", "dev")

    #  ★ **사진 폴더도 함께 갈라놓는다.**
    #    DB 는 BOKGUON_DB_PATH 로 막아 놓고 uploads 는 안 막아서, 검증이 올린
    #    사진이 **운영 uploads/ 에 그대로 쌓였다**(실측: 파일 673개 · 운영 DB 에
    #    없는 사건 id 폴더 59개 · 최신 파일이 방금 돌린 배터리 것).
    #    매일 03:20 백업(robocopy /E)은 지우지 않으므로 그 쓰레기가 백업본에
    #    영구히 남아 진짜 시공 증빙과 섞인다.
    #    ⚠ import 보다 **먼저** 정해야 한다 — photo_ai 는 모듈을 읽는 순간
    #      UPLOAD_ROOT 를 굳힌다. 여기서 세워 두면 하위 프로세스도 물려받는다.
    if not os.environ.get("BOKGUON_UPLOAD_DIR"):
        _dbp = os.environ.get("BOKGUON_DB_PATH", "")
        _base = os.path.dirname(os.path.abspath(_dbp)) if _dbp else HERE
        _up = os.path.join(_base, "verify_uploads")
        try:
            os.makedirs(_up, exist_ok=True)
            os.environ["BOKGUON_UPLOAD_DIR"] = _up
        except OSError as e:
            print(f"✖ 검증용 사진 폴더를 못 만들었습니다: {e}")
            return 2

    #  ⚠⚠ [라운드603] 로그 파일도 갈라놓는다 — 위 uploads 와 같은 이유, 같은 사고다.
    #    app.py:1226 의 LOG_FILE 기본값은 BOKGUON_LOG_FILE 이 없으면 **이 저장소
    #    폴더의 진짜 bokguon.log**(실서버가 쓰는 그 파일)로 떨어진다. UNIT
    #    목록의 test_scan_round*.py 400여 개 중 스스로 BOKGUON_LOG_FILE 을
    #    세팅하는 것은 20개 남짓뿐(grep 확인) — 나머지는 각자 "고의로 예외를
    #    던져 로그에 남기는지 확인" 류 검사를 할 때마다 그 RuntimeError/
    #    AttributeError 트레이스백이 실서버 bokguon.log 에 그대로 쌓인다.
    #    실측(이 라운드) — bokguon.log/.log.1 을 실제로 마이닝해 보니 "R430 지연
    #    발송(테스트 주입)"·"R450-TEST-INJECTED-FAULT"·"simulated gate bug
    #    (round527 test)" 같은 이름표 붙은 트레이스백이 수백~수천 건씩 섞여
    #    있고, 그중 다수(예: "Cannot operate on a closed database")는 이름표가
    #    없어 실제 운영장애처럼 보이지만 파일 경로를 보면 test_scan_round527_
    #    fixes.py 의 _broken_record_gate 등 **이 배터리 자신**이 낸 것이다 —
    #    2026-07-23부터 오늘까지 15~45분 간격으로 계속 나타나는 패턴이 바로
    #    이 배터리가 라운드마다 도는 주기와 일치한다. 결과: bokguon.log 는
    #    "진짜 운영 신호 대 자기유발 소음"의 비율이 극단적으로 낮아져, 이후
    #    라운드들이 이 파일을 근거로 삼을 때마다 매번 소스대조로 걸러내야 하는
    #    부담을 지웠고(601~602 라운드가 실제로 그렇게 함), 5MB 회전 한도를
    #    실제 트래픽보다 훨씬 빨리 채워 **진짜 과거 장애 기록을 조기에 밀어낸다.**
    #    고침 — UPLOAD_DIR 과 같은 자리·같은 패턴으로 스크래치 로그 경로를
    #    한 곳에서만 세팅한다(이미 자기 몫을 세팅하는 20개 파일은 각자 os.environ
    #    setdefault/직접대입을 그대로 유지하므로 영향 없음 — 이미 있으면 안 건드림).
    if not os.environ.get("BOKGUON_LOG_FILE"):
        _dbp2 = os.environ.get("BOKGUON_DB_PATH", "")
        _base2 = os.path.dirname(os.path.abspath(_dbp2)) if _dbp2 else HERE
        os.environ["BOKGUON_LOG_FILE"] = os.path.join(_base2, "verify.log")

    #  ⚠ DB 를 안 정해 주면 테스트가 운영 DB 를 건드린다. 여기서 막는다.
    dbp = os.environ.get("BOKGUON_DB_PATH", "")
    if not quick and not dbp:
        print("✖ BOKGUON_DB_PATH 가 없습니다. 검증용 DB(verify.db)를 가리켜 주세요.")
        print("  운영 DB 로 돌리면 실데이터에 검증 사건이 박힙니다.")
        return 2

    #  ⚠⚠ [라운드406] UNIT 목록 중 그 무엇도 이 공유 verify.db 를 명시적으로
    #    처음 만들지 않는다(test_fresh_db.py 는 자기 전용 임시 DB 만 씀) —
    #    그래서 실제로는 UNIT 순서상 **가장 먼저 `import app`을 하는 파일**이
    #    (app.py 자신의 무조건 DB.init_db() 호출을 통해) 이 공유 DB 를 처음
    #    만드는 역할을 우연히 떠맡는다. 지금 그 파일은 test_template_js.py
    #    인데, 그 파일은 자기 검사(템플릿 인라인 JS 파싱)엔 데모 데이터가
    #    필요 없어 BOKGUON_SEED_DEMO=0 을 스스로 세팅해 둔다 — 그 선택은
    #    자기 프로세스에만 한정될 의도였지만, "공유 DB 를 처음 만드는 자"가
    #    되어버리는 바람에 그 뒤로 도는 **모든** UNIT 테스트가 보험사 하나도
    #    없는 DB를 물려받았다(실측: 406라운드가 파일 단위로 COUNT(insurers)
    #    를 찍어 이 파일 직후 0으로 떨어짐을 직접 확인). `SELECT ... FROM
    #    insurers LIMIT 1` 류 가정에 기대는 다른 UNIT 테스트(최소 9개, grep
    #    확인)가 `TypeError: 'NoneType' object is not subscriptable` 로
    #    죽는다 — 정확히 스캔 28·29라운드가 배터리에서만(단독 실행은 항상
    #    클린) 실패해 온 이유. 여기서 **명시적으로, seed_demo 를 환경변수가
    #    아니라 인자로 강제**해 초기화해 두면, 어느 UNIT 파일이 우연히
    #    "처음 여는 자"가 되든, 그 파일 자신의 BOKGUON_ENV/BOKGUON_SEED_DEMO
    #    선택과 무관하게 공유 DB 는 항상 씨드된 상태로 시작한다(db.py 의
    #    admins==0 게이트 때문에 이후 어떤 재호출도 다시 지우거나 건너뛰지
    #    않는다). dbp 가 실제로 채워졌을 때만 돈다 — quick 모드에서 사람이
    #    BOKGUON_DB_PATH 자체를 안 줬다면(위 검사가 넘어가는 유일한 경우)
    #    이 초기화도 하지 않는다(운영 DB 를 잘못 건드릴 길을 새로 만들지
    #    않기 위함 — db.py 의 test_ 전용 가드는 이 실행기(run_all_tests.py)
    #    자신은 안 잡아 준다).
    if dbp:
        import db as DB
        DB.init_db(seed_demo=True)

    print("=" * 66)
    print("  복구온 전체 검증")
    print(f"  DB   : {dbp or '(각 테스트 기본값)'}")
    print(f"  사진 : {os.environ.get('BOKGUON_UPLOAD_DIR') or '(운영 uploads/ — 위험)'}")
    print(f"  서버 : {base}")
    print("=" * 66)

    results = []
    missing_files = []
    print("\n[1] 단위 — 서버 없이 도는 것들")
    for s, label in UNIT:
        #  ⚠ 파일이 없으면 **없다고 말한다.** 조용히 넘기면 이름을 잘못 적거나
        #    파일을 옮긴 날부터 그 검사는 영원히 안 돌면서 '전부 통과'가 된다
        #    (오늘 하루에만 회귀 테스트 4개가 추가됐다 — 오타 한 글자면 사라진다).
        if not os.path.exists(os.path.join(HERE, s)):
            print(f"  ✖ {label} — 파일이 없습니다: {s}")
            missing_files.append(s)
            continue
        results.append((label, run(s, label, base)))

    if quick:
        return report(results, missing=missing_files)

    missing = [k for k in NEEDED_ENV if not os.environ.get(k)]
    if missing:
        print(f"\n✖ 비밀번호 환경변수가 없습니다: {', '.join(missing)}")
        print("  (코드에 넣지 않습니다 — 실행할 때 환경변수로 주세요)")
        return report(results, 2, missing_files,
                      f"[2] HTTP {len(HTTP)}개 · [3] 빈 DB 첫날 완주")
    if not server_up(base):
        print(f"\n✖ 검증 서버가 {base} 에 없습니다. 먼저 띄워 주세요.")
        return report(results, 2, missing_files)

    #  ★ 여기서 막는다. HTTP 여러 개를 50분 가까이 돌리고 나서 "환경이 틀렸다"를 알면 늦다.
    probs = preflight(base)
    if probs:
        print("\n✖ 사전 점검에서 막혔습니다 — HTTP 검증을 시작하지 않습니다.")
        for p in probs:
            print(f"   · {p}")
        return report(results, 2, missing_files,
                      f"[2] HTTP {len(HTTP)}개 · [3] 빈 DB 첫날 완주")
    print("\n  사전 점검 통과 — 서버 코드가 최신이고 로그인이 됩니다.")

    print(f"\n[2] HTTP — 로그인을 하므로 사이에 {GAP}초씩 쉽니다"
          + ("  (--no-wait 로 생략됨)" if nowait else ""))
    print(f"    ⚠ 안 쉬면 레이트리밋(10회/{GAP}초)에 걸려 **코드 결함처럼 보이는 실패**가 납니다.")
    for i, (s, label) in enumerate(HTTP):
        if not os.path.exists(os.path.join(HERE, s)):
            print(f"  ✖ {label} — 파일이 없습니다: {s}")
            missing_files.append(s)
            continue
        if i and not nowait:
            print(f"         … {GAP}초 대기(레이트리밋)")
            time.sleep(GAP)
        results.append((label, run(s, label, base)))

    print("\n[3] 독립 — 자기 서버를 띄워 도는 것")
    for s, label in STANDALONE:
        if not os.path.exists(os.path.join(HERE, s)):
            print(f"  ✖ {label} — 파일이 없습니다: {s}")
            missing_files.append(s)
        else:
            #  ⚠ 이건 자기 DB(임시)를 쓴다 — 검증 DB 를 물려주면 안 된다
            env_backup = os.environ.pop("BOKGUON_DB_PATH", None)
            try:
                results.append((label, run(s, label, base)))
            finally:
                if env_backup is not None:
                    os.environ["BOKGUON_DB_PATH"] = env_backup

    return report(results, missing=missing_files)


def report(results, code=0, missing=None, aborted=""):
    bad = [n for n, ok in results if not ok]
    missing = missing or []
    print("\n" + "=" * 66)
    #  ★ **중간에 끊겼으면 '전부 통과' 라고 쓰지 않는다.**
    #    비밀번호 환경변수가 없어 HTTP 10개와 첫날 완주가 통째로 안 돌았는데
    #    마지막 줄은 "24/24 — 전부 통과" 였다. 종료코드는 2 였지만,
    #    로그를 눈으로 보는 사람에게는 초록으로 읽힌다(파이프로 코드가 가려지기도 한다).
    _tail = (f"   ⚠ 중간에 끊김 — 통과가 아닙니다 ({aborted})" if aborted
             else (f"   ✖ 실패 {len(bad)}" if bad else "   — 전부 통과"))
    print(f"  {len(results) - len(bad)} / {len(results)} 통과" + _tail)
    if aborted:
        print(f"  실행되지 않은 단계: {aborted}")
    for n in bad:
        print(f"    · {n}")
    #  ★ **없어서 안 돈 검사는 '통과'가 아니다.** 분모에서 빠질 뿐이라
    #    화면은 오히려 더 깨끗해 보인다 — 그래서 따로 세어 종료코드에 반영한다.
    if missing:
        print(f"\n  ✖ 실행되지 않은 검사 {len(missing)}개 (파일 없음):")
        for m in missing:
            print(f"    · {m}")
        code = code or 2
    print("=" * 66)
    return code or (1 if bad else 0)


if __name__ == "__main__":
    sys.exit(main())
