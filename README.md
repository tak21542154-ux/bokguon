# 복구온 (BOKGUON) — 기타피해물 복구 역경매 플랫폼

㈜올림포스네트웍스 전략사업실 유경탁 파트장 · 2026.07.16

보험사로부터 기타피해물(가드레일·유리·담장·차단기·누수 등) 복구 건을 받아,
검증된 **시행사**들이 **통값(총액)으로 경쟁 입찰**하고, AI가 현장 사진을 분류해
보험사로 자동 전송하며, 정산 시 **수수료 10%**를 확보하는 플랫폼의 실동작 백엔드입니다.

## 실행

```
복구온_서버실행.bat  더블클릭
```
또는
```
pip install flask
python db.py        # 최초 1회 — DB 생성·시드
python app.py       # 서버 실행 (포트 8771)
```

| 화면 | 주소 | 계정 |
|---|---|---|
| 랜딩페이지 | http://localhost:8771/ | — |
| 보험사 도입 문의 | http://localhost:8771/apply/insurer | — |
| 시행사·시공사 입점 신청 | http://localhost:8771/apply/partner | — |
| **어드민 콘솔** | http://localhost:8771/admin | `admin / bokguon2026` |
| **협력사 포털** | http://localhost:8771/partner | `partner / partner2026` |
| **보험사 포털** | http://localhost:8771/insurer | `insurer / bokguon2026` |
| 협력업체 앱(모바일 데모) | http://localhost:8771/app/partner | — |

관리자: `admin / bokguon2026`(최고관리자), `staff / staff2026`(운영관리자)

## 3자 포털 구조

| 주체 | 포털 | 핵심 기능 |
|---|---|---|
| **보험사·공제조합** | `/insurer` | 사건 등록 → 입찰 현황 → **낙찰 승인**(최저가 아니면 사유 필수) → 하자 접수 → 정산 → 절감 리포트 |
| **시행사·시공사** | `/partner` | 공고 열람 → **통값 입찰**(인하만) → 내 사건 → 정산(10% 공제 후 실수령) → **하자 재시공 완료보고** |
| **올림포스 운영** | `/admin` | 15개 메뉴 — 관제·심사·AI검수·정산검수·**하자 배정**·통계·알림·설정 |

각 포털은 **자기 데이터만 접근**한다(OWASP 2025 A01 대응). 보험사는 `insurer_id`, 협력사는 `partner_id`를
세션에서만 읽어 쿼리에 결합하므로 URL 조작(IDOR)으로 타 기관 정보를 볼 수 없다.

## 구조

```
bokguon_service/
├─ app.py                  Flask 앱 — 페이지 라우트 + REST API (40 routes)
├─ db.py                   SQLite 스키마 + 시드 (python db.py --reset 로 초기화)
├─ ingest_partners.py      리서치 결과(journal.jsonl) → 협력업체 시드 병합
├─ bokguon.db              SQLite 데이터베이스 (자동 생성)
├─ data/partners_seed.json 협력업체 시드 데이터
├─ templates/              landing, apply_insurer, apply_partner, admin, login, partner_app, insurer_app
└─ static/                 style.css, admin.css, admin.js, form.js
```

## 핵심 개념 — 시행사 vs 시공사

| 구분 | 역할 | 입찰 |
|---|---|---|
| **시행사** | 한 현장을 통째로 받아 **자기가 시공사를 선정**하고 **총액(통값)으로 입찰**. 다공종 관리·종합건설 면허 보유 | ✅ 경매 참여 주체 |
| **시공사** | 공종별 전문 업체. 시행사의 하도급 풀로 등록 | ❌ (향후 분리발주 모델 전환 시 참여) |

→ 보험사는 **단일 창구·단일 금액·단일 책임**으로 처리. 공종 분리발주(협업) 모델은
데이터 모델(`work_lots`)에 남겨두어 물량 확대 후 전환 가능.

## 주요 플로우 (전부 실동작)

1. **랜딩 CTA** → 신청 폼 → `POST /api/leads` / `POST /api/applications` → DB 저장
2. **어드민 문의함·신청함**에 인입 (사이드바 뱃지 자동 증가)
3. **심사 → 승인** → `PATCH /api/applications/:id {status:"승인"}`
   → **협력업체 자동 등록** (시행사/시공사 구분 유지) + 알림 발송 + 감사 로그
4. **공고 등록** → 매칭 업체 자동 카운트·공고 알림
5. **정산** → 보험사 입금 → **내부 지급 검수(필수 관문)** → 10% 공제 → 이체 예약

## 어드민 메뉴 (13종)

| 그룹 | 메뉴 |
|---|---|
| 모니터링 | 대시보드(작업 파이프라인·거래대금), 사건·입찰 관제 |
| 유입·심사 | 도입 문의함, 입점 신청함, 업체 등록·관리(시행사/시공사 탭) |
| 운영 | AI 사진 검수, 정산 관리, **하자·A/S 관리**, 공고·사건 등록 |
| 분석·소통 | 통계·리포트, 접속 통계, 운영 알림 로그, 공지사항 |
| 시스템 | 표준 단가·내역, 설정·감사로그 |

## 하자·A/S 처리 흐름

```
보험사 하자 접수 (/insurer)
   ↓  하자보증 기간 자동 판정 → 기간 내면 시행사 부담
어드민 확인중 → 재시공 배정 (/admin)  ── 알림톡 → 시행사
   ↓
협력사 재시공 후 완료 보고 (/partner)  ── 상태: 확인중
   ↓
어드민 완료 처리  ── 보험사 통보 + 업체 평점 자동 차감(중대 −0.2 / 보통 −0.1)
```

## API 요약

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/api/leads` | 공개 | 보험사 도입 문의 접수 |
| POST | `/api/applications` | 공개 | 입점 신청 접수 |
| GET | `/api/open-auctions` | 공개 | 진행중 공고 (협력업체 앱) |
| POST | `/api/login` `/api/logout` | — | 세션 인증 |
| GET | `/api/stats` | 관리자 | 대시보드 집계 (시행사/시공사 포함) |
| GET/PATCH | `/api/leads[/:id]` | 관리자 | 문의 조회·상태변경 |
| GET/PATCH | `/api/applications[/:id]` | 관리자 | 신청 조회·승인(→업체 생성) |
| GET/POST/PATCH/DELETE | `/api/partners[/:id]` | 관리자 | 업체 CRUD (`?partner_type=시행사`) |
| GET/POST | `/api/cases` | 관리자 | 사건 조회·등록 |
| GET | `/api/settlements` · POST `/api/settlements/:id/review` | 관리자 | 정산·지급검수 |
| GET/POST/DELETE | `/api/notices` `/api/boq` | 관리자 | 공지·표준내역 |
| GET/PATCH | `/api/settings` | 관리자 | 정책·리마인드 주기 |
| GET | `/api/activity` `/api/notifications` | 관리자 | 감사로그·알림로그 |
| POST | `/api/insurer/login` `/logout` | 보험사 | 세션 인증 |
| GET | `/api/insurer/dashboard` | 보험사 | 자기 기관 사건·정산·하자 |
| POST | `/api/insurer/cases` | 보험사 | 사건 등록 → 즉시 공고 |
| GET/POST | `/api/insurer/cases/:id/bids` `/award` | 보험사 | 입찰 조회·낙찰 승인 |
| POST | `/api/partner/login` `/logout` `/bids` | 협력사 | 인증·통값 입찰 |
| GET | `/api/partner/dashboard` `/defects` | 협력사 | 내 현황·내 하자 |
| POST | `/api/partner/defects/:id/resolve` | 협력사 | 재시공 완료 보고 |
| GET/POST/PATCH | `/api/defects` | 관리자·보험사 | 하자 접수·배정·완료 |

## 운영 전 필수 조치 (실서비스 전환 시)

- `app.secret_key`를 환경변수로 분리, 비밀번호 해시를 bcrypt/argon2로 교체
- HTTPS 적용, 운영 WSGI(gunicorn/waitress) 사용 — `app.run()`은 개발용
- SQLite → PostgreSQL 전환(동시 쓰기 대비)
- 파일 업로드(사진) 스토리지 + AI 분류 API(구글 제미나이) 실연동
- 알림톡·펌뱅킹·전자계약 실계약 및 연동
- **법률 3관문 자문**: 순수중개 유지 · 손해사정 배제 · 정산 외부 PG 위탁 (기획서 07장)
