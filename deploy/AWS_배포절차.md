# 복구온 — AWS 배포 절차 (Lightsail)

**㈜올림포스네트웍스 전략사업실 유경탁 파트장**

서버가 없는 상태에서 시작해 서비스가 뜰 때까지의 순서다.
계정·결제는 사람이 해야 하고, 그 뒤 설치는 스크립트가 한다.

---

## 0단계 — 시작 전에 알아야 할 것 (중요)

### 카드 등록은 AWS도 필요하다
AWS 공식 FAQ: *"무료 플랜을 선택하든 유료 플랜을 선택하든, AWS 계정 가입에는 유효한 결제 수단을 제공해야 합니다."*
본인확인·부정사용 방지 목적이며 무료 기간에 즉시 청구되지는 않는다.
**즉, 네이버클라우드와 마찬가지로 카드 등록은 피할 수 없다.**

### ⚠ 무료 플랜으로 운영하면 안 된다 — 계정이 닫히고 데이터가 사라진다
AWS 공식 FAQ: *"6개월 무료 플랜이 만료되거나 크레딧이 소진되면 AWS는 계정을 폐쇄하고,
사용자는 리소스와 데이터에 대한 접근 권한을 잃습니다."* (유료 전환 유예 90일, 이후 영구 삭제)

복구온은 **개인정보와 정산 데이터**를 담는다. 크레딧 소진으로 계정이 닫히면
협력업체 398개사·사건·정산·시공사진이 통째로 날아간다.
→ **실서비스는 반드시 유료 플랜(Paid plan)으로 전환한 뒤 올린다.**

신규 계정 크레딧($100 즉시, 최대 $200 / 6개월)은 **초기 비용을 상쇄하는 용도**로만 본다.

### 비용 (Lightsail, 공식 요금표 기준)

| 사양 | 월 요금 | 복구온 적합성 |
|---|---|---|
| 2vCPU / **1GB** / 40GB | $7 | ✘ 사진 변환(HEIC→JPEG)에서 메모리 부족 위험 |
| 2vCPU / **2GB** / 60GB | $12 | △ 가능. 스왑 2GB 설정 필수 |
| 2vCPU / **4GB** / 80GB | **$24** | ○ **권장.** 여유 있게 돈다 |

> Lightsail 은 3개월 무료 체험이 있다. 신규 계정 크레딧과 합치면 초기 부담이 거의 없다.
> 다만 위 경고대로, 체험이 끝나기 전에 유료 플랜으로 전환해 둔다.

---

## 1단계 — Lightsail 인스턴스 생성

AWS 콘솔 → **Lightsail** → Create instance.

| 항목 | 값 | 이유 |
|---|---|---|
| 리전 | **Seoul (ap-northeast-2)** | **국내 리전 필수.** 국외 리전은 개인정보 국외이전 고지·동의 절차가 별도로 생긴다 |
| 플랫폼 | Linux/Unix | |
| 블루프린트 | **OS Only → Ubuntu 24.04 LTS** | 설치 스크립트가 apt 기준. 22.04 도 동작 |
| 인스턴스 플랜 | **4GB / 2vCPU / 80GB ($24)** | 2GB 로 줄이려면 아래 스왑 설정을 반드시 할 것 |
| 인스턴스 이름 | `bokguon-prod` | |

> **앱(WordPress 등) 블루프린트를 고르지 말 것.** 반드시 `OS Only` 다.

### SSH 키
생성 화면에서 키페어를 만들고 **`.pem` 파일을 내려받아 안전하게 보관**한다. 분실하면 서버에 못 들어간다.

### 고정 IP 연결
인스턴스 생성 후 **Networking → Create static IP** → 인스턴스에 연결.
**연결된 상태에서는 무료**다(연결 안 하고 방치하면 과금되니 주의).

### 방화벽 — 가장 많이 빠뜨리는 단계
인스턴스 → **Networking → IPv4 Firewall** 에서 규칙을 아래로 맞춘다.

| 애플리케이션 | 프로토콜 | 포트 | 제한 |
|---|---|---|---|
| SSH | TCP | 22 | **Restrict to IP → 사무실 고정 IP** |
| HTTP | TCP | 80 | 전체 허용 (인증서 발급·HTTPS 전환용) |
| HTTPS | TCP | 443 | 전체 허용 |

> **22번을 전체 개방하지 말 것.** 공개된 SSH 는 몇 시간 안에 자동 공격을 받는다.
> **8771(앱 포트)은 열지 않는다.** 앱은 127.0.0.1 에만 바인딩되고 외부는 nginx 가 받는다.

---

## 2단계 — 도메인 연결

도메인 관리 화면에서 **A 레코드**를 Lightsail 고정 IP 로 지정한다.

```
bokguon.olymposnetworks.com.   A   <고정 IP>
```

> ⚠ **DNS 전파가 끝난 뒤에** 3단계로 간다. 전파 전에 설치하면 인증서 발급이 실패한다.
> 확인: `nslookup bokguon.olymposnetworks.com` 이 고정 IP 를 돌려주면 준비 완료.

---

## 3단계 — 소스 올리기

내 PC(Git Bash / PowerShell)에서:

> ### ⚠ 묶음은 **올리기 직전에 새로 만든다**
> 바탕화면의 `260721_복구온_배포묶음.tar.gz` 를 그대로 쓰지 마십시오.
> 그 묶음은 2026-07-21 자이고, 그 안의 `app.py` 는 현재 소스의 **3분의 1 크기**입니다.
> `dispatch.py` · `compliance.py` · `notify_popbill.py` · `partner_accounts.py` 등이
> 아예 없고, 자기 `deploy/` 까지 담고 있어 **4단계의 `bootstrap.sh` 도 7월 21일 것이
> 실행됩니다.** 겉으로는 설치가 성공하고, 없는 기능은 조용히 없습니다.

```bash
# ① 지금 소스로 묶음을 만든다 (Git Bash, bokguon_service 의 상위 폴더에서)
cd ~/Desktop/olympos_bot
tar --exclude='*.db*' --exclude='.env' --exclude='*.log' --exclude='logs' \
    --exclude='backups' --exclude='uploads' --exclude='__pycache__' \
    --exclude='dev_*.pem' --exclude='.venv' --exclude='venv' \
    -czf ~/Desktop/복구온_배포묶음.tar.gz bokguon_service/

# ② 담겼는지 확인한다 — 목록에 이 파일들이 **전부** 있어야 한다
tar -tzf ~/Desktop/복구온_배포묶음.tar.gz | \
    grep -E 'bokguon_service/(app|db|manage|dispatch|compliance|notify_popbill|partner_accounts)\.py$'
#   → 7줄이 나와야 정상. 하나라도 빠지면 묶음이 잘못된 것이다.

# ③ 올린다
chmod 400 <키파일>.pem       # 권한이 넓으면 ssh 가 거부한다
scp -i <키파일>.pem ~/Desktop/복구온_배포묶음.tar.gz ubuntu@<고정IP>:~/
```

> Windows PowerShell 에서 `chmod` 가 없으면, 파일 속성 → 보안에서 본인 계정만 남기면 된다.

---

## 4단계 — 설치 (한 번에 끝난다)

```bash
ssh -i <키파일>.pem ubuntu@<고정IP>

# 2GB 플랜을 골랐다면 스왑을 먼저 잡는다 (4GB 면 건너뛴다)
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 설치
tar -xzf 복구온_배포묶음.tar.gz
cd bokguon_service
sudo BOKGUON_DOMAIN=bokguon.olymposnetworks.com \
     BOKGUON_EMAIL=c.common@olymposnetworks.com \
     bash deploy/bootstrap.sh
```

`bootstrap.sh` 가 하는 일 — 전용 계정 → 가상환경·의존성 → **시크릿 자동 생성** → DB 초기화 →
협력업체 398개사 적재 → systemd → nginx → **Let's Encrypt 인증서** → 방화벽 →
크론(5분마다 **예약 실행** · 백업 · 사진백업 · 로그정리 · 개인정보 파기) → 점검 → 스모크 테스트.

> ⚠ 예약 실행(`manage.py sweep`)이 크론에 없으면 서비스가 반쯤 죽은 채로 돕니다 —
> 경매가 마감되지 않고, 출동 기한이 지나도 재수배가 안 되고, 문자·알림톡이 발송대기로만
> 쌓입니다. 배포 후 `manage.py check` 가 이걸 봅니다.

여러 번 실행해도 안전하다. **`.env` 와 기존 DB 는 절대 덮어쓰지 않는다.**

### 설치 직후 즉시 — 이 둘을 놓치면 복구 불가
1. 출력된 **`BOKGUON_ENC_KEY`** 를 회사 비밀번호 관리자에 보관.
   **잃으면 저장된 정산 계좌번호를 영구히 복호화할 수 없다.**
2. 출력된 **최고관리자 임시 비밀번호**를 안전한 경로로 전달(최초 로그인 시 변경 강제).

---

## 5단계 — 관리자 접속 IP 지정

```bash
sudo nano /opt/bokguon/.env
#  ⚠ Windows 메모장·PowerShell 은 파일 앞에 BOM 을 붙인다 — 앱은 이제 BOM 을
#    걸러내도록 고쳐 뒀지만(305라운드), 다른 도구가 이 파일을 읽을 때 여전히
#    문제가 될 수 있다. nano/vi 권장.
```

`BOKGUON_ADMIN_IP_ALLOW` 에 **사무실 고정 IP** 를 넣는다(쉼표로 여러 개 가능).
처리방침에 "관리자 콘솔 IP 제한 시행"을 고지했으므로 비워 두면 고지와 어긋나고,
`manage.py check` 도 배포 불가로 막는다.

---

## 6단계 — 오픈

```bash
cd /opt/bokguon

./venv/bin/python manage.py show-info      # 7/8 은 이미 채워져 있다. 남은 건 PG 뿐

# 실제 관리자 계정을 **먼저** 만든다 (아이디에 admin·staff 금지)
./venv/bin/python manage.py create-admin ktyu --name 유경탁 --role 최고관리자

./venv/bin/python manage.py go-live --yes  # 운영 DB 는 시드가 없어 대개 "정리할 데모 없음"
./venv/bin/python manage.py check          # "배포 가능" 이 떠야 한다

sudo systemctl restart bokguon
#  ⚠⚠ [라운드308] 이 세 줄이 없으면 smoke_test.py 는 검사를 단 하나도 실행하지
#    않고 종료코드 2 로 끝난다(공개면·보안헤더 검사까지 전부 포함해서 안 돈다) —
#    "로그인만 건너뛴다"가 아니라 "아무것도 안 돈다". DEPLOY.md 가 125·285라운드
#    에서 이미 겪은 함정과 같다.
export BOKGUON_TEST_ADMIN_PW="bokguon2026"
export BOKGUON_TEST_INSURER_PW="bokguon2026"
export BOKGUON_TEST_PARTNER_PW="partner2026"
./venv/bin/python smoke_test.py https://bokguon.olymposnetworks.com
unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW
```

> 위 3단계(go-live)가 admin/partner/insurer 데모 계정을 이미 지웠으므로, 비밀번호를
> 넣어도 로그인 이후 검사(CSRF·입찰·정산 등)는 대부분 건너뛰고 종료코드 4 가 뜬다 —
> 이 시점에는 정상이다(공개면·보안헤더·법정문서·레이트리밋은 그래도 검증된다).
> 종료코드 0(전부 통과)을 다시 보려면 운영용 검증 계정을 별도로 만들어 실행할 것.

---

## 7단계 — 오픈 후 확인

| 확인 | 방법 |
|---|---|
| HTTPS | 브라우저 자물쇠 표시, `http://` 접속 시 자동 전환 |
| 법정 게시물 | `/legal/privacy` 에 "(미기재)" 가 PG 외에 없는지 |
| 백업 | 다음 날 `/opt/bokguon/backups/` 에 파일 생성 |
| 사진 백업 | `uploads/` 별도 백업 (DB 백업은 사진을 담지 않는다) |
| 인증서 자동갱신 | `sudo systemctl status certbot.timer` |
| **결제 플랜** | **유료 플랜으로 전환됐는지** — 무료 플랜은 계정이 닫힌다 |

### 요금 알림 설정 (권장)
AWS 콘솔 → Billing → **Budgets** 에서 월 예산 알림을 걸어 둔다.
Lightsail 은 고정 요금이라 예측 가능하지만, 다른 서비스가 붙으면 새는 곳이 생긴다.

---

## 알아둘 것

- **PG 미정 상태로도 서비스는 뜬다.** 입찰·시공·사진검수까지 정상 동작한다.
  **정산 이체 단계 전까지** PG 계약을 마치고 `set-info pg` 로 채운다.
- **알림톡은 아직 나가지 않는다.** 팝빌((주)링크허브) 연동신청·채널개설·템플릿 승인 후 발송된다.
  그전까지 알림은 '발송대기'로 쌓이고 어드민 운영알림 화면에서 확인한다.
- **SQLite 단일 서버 전제.** 서버를 늘리려면 PostgreSQL 이전이 먼저다.

---

## 사고 시 되돌리기

```bash
sudo systemctl stop bokguon
cd /opt/bokguon
# ⚠ 백업 위치는 .env 의 BOKGUON_BACKUP_DIR 가 정한다(bootstrap.sh 가 써 넣는다).
#   클라우드 기본값은 /var/backups/bokguon 이며 `backups/` 상대경로는 없다 —
#   장애 상황에서 상대경로로 치면 "파일이 없습니다" 로 끝난다. 위치부터 확인한다.
ls -lt "$(grep -oP '(?<=^BOKGUON_BACKUP_DIR=).*' .env || echo /var/backups/bokguon)" | head
./venv/bin/python manage.py restore /var/backups/bokguon/bokguon_<날짜>.db --yes
sudo systemctl start bokguon
```

> 백업은 **DB만** 뜬다. 사진은 `uploads/` 별도 백업에서 되돌린다.
> Lightsail 은 **인스턴스 스냅샷**도 제공한다(유료). 오픈 직후 1회 떠 두면 통째 복구가 쉽다.
