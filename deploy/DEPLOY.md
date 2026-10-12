# 복구온 서비스 — 실서버 배포 안내서

**㈜올림포스네트웍스 전략사업실 유경탁 파트장**

---

## 0. 오픈 당일 순서 (요약)

이 순서를 그대로 따르면 `check` 가 **배포 가능**으로 바뀐다. 리허설로 검증된 경로다.

```bash
cd /opt/bokguon

# 1) 회사 정보 8건 입력 — 코드를 고칠 필요 없다
#
#    ⚠ 아래 값은 **법정 게시물(개인정보처리방침·사업자정보)에 그대로 공개**된다.
#      확인되지 않은 값을 채우면 허위 고지가 된다. 모르면 비워 두고 확인부터 하라.
#
#    ── 이미 확인된 값 (회사 공개 사이트 olymposcar.com 푸터 및 개인정보처리방침 §12,
#       법인 단위 정보이므로 복구온에도 그대로 적용된다. 2026-07-21 확인) ──
./venv/bin/python manage.py set-info tel           "1533-7120"
./venv/bin/python manage.py set-info dpo           "김예찬 이사"
./venv/bin/python manage.py set-info dpo_tel       "1533-7120 · olympos@olymposnetworks.com"
./venv/bin/python manage.py set-info mail_order_no "제2022-서울송파-1106호"
#
#
#    ⚠⚠ **아래 네 줄은 일부러 주석 처리해 두었다. 블록째 붙여넣지 말 것.**
#       ○○ 같은 자리표시자가 들어가도 `manage.py check` 는 '기재됨'으로 통과한다
#       (빈 값만 미기재로 본다). 즉 **허위 고지인 채 초록불**이 된다.
#       2026-08-06 부터 check 가 자리표시자를 따로 잡아내지만, 애초에 안 넣는 게 낫다.
#
#    ── 2026-07-21 기준 이미 들어가 있는 값 (show-info 로 먼저 확인할 것) ──
#       effective_date  2026년 7월 22일
#       hosting         아마존웹서비스(AWS) — 서울 리전
#       alimtalk        (주)링크허브 (팝빌)
#
#    ── 아직 비어 있는 값 ──
#       pg : 정산 대금 이체 위탁처. **계약 체결 후** 실제 상호를 넣는다.
#            (렌터카 서비스의 KG이니시스는 카드결제 PG 라 복구온 정산과 다르다)
#
./venv/bin/python manage.py show-info          # ← **먼저 이것부터.** 뭐가 비었는지 본다
# ./venv/bin/python manage.py set-info effective_date "2026년 8월 O일"   # 오픈일이 바뀌었을 때만
# ./venv/bin/python manage.py set-info hosting       "실제 클라우드 사업자"
# ./venv/bin/python manage.py set-info pg            "실제 PG 상호"      # 계약 후
# ./venv/bin/python manage.py set-info alimtalk      "실제 발송 대행사"
./venv/bin/python manage.py check              # 자리표시자가 남아 있으면 여기서 막힌다

# 2) 실제 관리자 계정 **먼저** 발급 — 임시 비밀번호가 출력되니 즉시 받아 적을 것
#    ⚠ 아이디로 admin·staff 를 쓰지 말 것. 다음 단계 go-live 가 그 두 이름을 지운다.
#    bootstrap.sh 가 만든 계정 이름이 하필 'admin' 이라, 순서를 뒤집으면 관리자 0명 구간이 생긴다.
./venv/bin/python manage.py create-admin ktyu --name 유경탁 --role 최고관리자

# 3) 데모 사건·계정 제거 (협력업체 398개사는 유지된다)
./venv/bin/python manage.py go-live          # 먼저 --yes 없이 삭제 목록을 눈으로 확인
./venv/bin/python manage.py go-live --yes

# 4) 배포 전 점검 — "배포 가능" 이 떠야 한다
./venv/bin/python manage.py check

# 5) 재시작 후 실동작 검증
#    ⚠⚠ [라운드285] 위 3단계(go-live)가 admin/partner/insurer 데모 계정을 이미
#      지웠으므로, 아래 비밀번호를 넣어도 로그인 이후 검사(CSRF·입찰·정산 등)는
#      대부분 건너뛰고 종료코드 4 가 뜬다 — **이 시점에는 정상**이다(공개면·
#      레이트리밋 등은 그래도 검증된다). 종료코드 0(전부 통과)을 다시 보려면
#      운영용 검증 계정을 별도로 만들어 실행해야 한다.
sudo systemctl restart bokguon
export BOKGUON_TEST_ADMIN_PW="bokguon2026"
export BOKGUON_TEST_INSURER_PW="bokguon2026"
export BOKGUON_TEST_PARTNER_PW="partner2026"
./venv/bin/python smoke_test.py https://도메인
unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW
```

## 0-1. 배포 전 반드시 확정할 것

| 항목 | 채우는 곳 | 비고 |
|---|---|---|
| 도메인 | DNS A 레코드 → 서버 IP | 인증서 발급 전 DNS 전파가 끝나 있어야 함 |
| 개인정보 보호책임자 | `manage.py set-info dpo` | 성명·직책·연락처 (법 제30조 필수 기재) |
| 통신판매업 신고번호 | `manage.py set-info mail_order_no` | 관할 구청 신고 후. 순수 중개면 신고 대상 여부부터 확인 |
| 클라우드 호스팅 사업자 | `manage.py set-info hosting` | 처리방침의 수탁자 공개 항목 |
| PG(정산 이체 위탁처) | `manage.py set-info pg` | 계약 후 기재 |
| 알림톡·문자 발송 대행사 | `manage.py set-info alimtalk` | 계약 후 기재 |
| 관리자 콘솔 허용 IP | `.env` `BOKGUON_ADMIN_IP_ALLOW` | 사무실 고정 IP |
| 개인정보 내부관리계획 결재 | `deploy/개인정보_내부관리계획.md` | 고시 제4조 수립 의무 |
| 처리방침·약관 변호사 검토 | — | 오픈 전 1회 필수 |
| 법률 3관문 자문 | — | 손해사정·건설업·PG (기획서 07장) |

> 값은 `data/company_info.json` 에 저장된다. 코드를 고치지 않으므로 기획팀이 직접 입력할 수 있다.
> 미기재 항목이 남아 있으면 `manage.py check` 가 **배포 불가**로 막는다.

> ⚠ **`.env` 를 메모장으로 편집하지 말 것** — Windows 메모장·PowerShell 은 파일 앞에 BOM 을 붙인다.
> (앱은 BOM 을 걸러내도록 고쳐 두었지만, 다른 도구가 읽을 때 문제가 될 수 있다. `nano`/`vi` 권장)

> ⚠⚠ **[라운드303] `bootstrap.sh`·섹션 2(수동 설치)는 스모크 테스트를 go-live *이전*에 돌린다.**
> 이때 `smoke_test.py`(쓰기 모드, 기본값)가 데모 "insurer" 계정으로 사건·입찰·정산을
> 실제로 만든다 — go-live 가 아직 안 지나 이 사건들이 관리자 대시보드에 실적처럼 보인다
> ("거래 9,650만원·'이체완료' 14건" 식, `manage.py mark-smoke-demo` 자체 문서화 사례).
> **데이터는 안전하다** — go-live 가 발주처(`insurer_id`) 기준으로 이 사건들을 표식 유무와
> 무관하게 딸린 사진·입찰·정산까지 전부 함께 지운다(`manage.py` `DEMO_CASE_SQL`). 다만
> go-live 전에 대시보드를 다른 사람에게 보여줘야 한다면 먼저 정리한다:
> ```bash
> ./venv/bin/python manage.py mark-smoke-demo --dry   # 무엇에 표식이 붙을지 미리보기
> ./venv/bin/python manage.py mark-smoke-demo         # 표식을 붙인다(대시보드에 즉시 반영)
> ```

---

## 1. 리눅스 서버 (권장) — 원샷 설치

Ubuntu 22.04 / 24.04 LTS 기준.

```bash
# 1) 소스 업로드
scp -r bokguon_service/ ubuntu@서버IP:~/bokguon_src

# 2) 설치 (한 번에 끝난다)
ssh ubuntu@서버IP
cd ~/bokguon_src
sudo BOKGUON_DOMAIN=bokguon.olymposnetworks.com \
     BOKGUON_EMAIL=c.common@olymposnetworks.com \
     bash deploy/bootstrap.sh
```

`bootstrap.sh` 가 하는 일 — 전용 계정 생성 → 가상환경·의존성 → **시크릿 자동 생성** →
DB 초기화·마이그레이션 → 최고관리자 계정 발급 → systemd 등록 → nginx 설정 →
**Let's Encrypt 인증서 발급** → 방화벽 → 백업·로그정리 크론 → 배포 전 점검 → 스모크 테스트.

여러 번 실행해도 안전하다. **`.env` 와 기존 DB 는 절대 덮어쓰지 않는다.**

### 설치 직후 할 일

1. 출력된 **최고관리자 임시 비밀번호**를 안전한 경로로 전달한다. 최초 로그인 시 변경이 강제된다.
2. 출력된 **`BOKGUON_ENC_KEY`** 를 회사 비밀번호 관리자에 보관한다.
   이 키를 잃으면 저장된 정산 계좌번호를 **영구히 복호화할 수 없다.**
3. `sudo nano /opt/bokguon/.env` 에서 `BOKGUON_ADMIN_IP_ALLOW` 에 사무실 IP 를 넣고
   `sudo systemctl restart bokguon`.

---

## 2. 리눅스 — 수동 설치 (bootstrap 을 쓰지 않을 때)

**순서가 중요하다.** 아래 순서를 지키지 않으면 서비스 계정이 DB 에 쓰지 못해 기동에 실패한다.

```bash
# 1) 전용 계정 (로그인 불가 셸)
sudo useradd --system --home /opt/bokguon --shell /usr/sbin/nologin bokguon

# 2) 소스 배치 (개발 DB·.env·로그는 제외하고 복사)
sudo mkdir -p /opt/bokguon
sudo rsync -a --exclude='.env' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' \
    --exclude='*.log' --exclude='logs' --exclude='backups' --exclude='__pycache__' \
    --exclude='dev_*.pem' ~/bokguon_src/ /opt/bokguon/

# 3) 소유권을 **먼저** 넘긴다
sudo chown -R bokguon:bokguon /opt/bokguon

# 4) 그 다음 sudo -u bokguon 으로 가상환경·DB 를 만든다
#    ⚠ 여기서 root 로 만들면 파일 소유자가 root 가 되어
#      서비스 계정이 DB(-wal/-shm 포함)에 쓰지 못하고 기동에 실패한다.
sudo -u bokguon python3 -m venv /opt/bokguon/venv
sudo -u bokguon /opt/bokguon/venv/bin/pip install -r /opt/bokguon/requirements.txt

# 5) 환경설정
cd /opt/bokguon
sudo -u bokguon cp .env.example .env
sudo -u bokguon ./venv/bin/python manage.py gen-keys   # 출력된 3줄을 .env 에 붙여넣기
sudo -u bokguon nano .env
sudo chown bokguon:bokguon .env      # ⚠ 소유자 지정을 빠뜨리면 서비스가 읽지 못한다
sudo chmod 600 .env

# 6) DB 생성 · 관리자 계정
#    ⚠⚠ [라운드309] 이 섹션은 go-live 를 안 부르므로 여기서 만든 admin 계정은
#      이 흐름 안에서는 안전하다 — 다만 나중에(예: 이 서버에 리허설용 데모
#      데이터를 추가로 심고) go-live 를 한 번이라도 돌리면, go-live 는
#      admins.admin/staff 를 **이름으로만** 지운다(0장의 같은 경고 참고).
#      아이디로 admin·staff 를 쓰지 말 것 — go-live 를 나중에라도 돌릴
#      계획이면 실제 이름(예: ktyu)으로 만든다.
sudo -u bokguon ./venv/bin/python manage.py init
sudo -u bokguon ./venv/bin/python manage.py create-admin admin --role 최고관리자

# 7) systemd
sudo cp deploy/bokguon.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now bokguon
sudo systemctl status bokguon

# 8) nginx 레이트리밋 존 (http 블록에 있어야 한다)
sudo tee /etc/nginx/conf.d/bokguon_limits.conf > /dev/null <<'EOF'
limit_req_zone $binary_remote_addr zone=bokguon_login:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=bokguon_api:10m rate=120r/m;
EOF

# 9) nginx 사이트 + 인증서
sudo cp deploy/nginx_bokguon.conf /etc/nginx/sites-available/bokguon
sudo sed -i 's/bokguon.example.com/실제도메인/g' /etc/nginx/sites-available/bokguon
sudo ln -sf /etc/nginx/sites-available/bokguon /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo certbot --nginx -d 실제도메인
sudo nginx -t && sudo systemctl reload nginx

# 10) 방화벽
sudo ufw allow OpenSSH && sudo ufw allow 'Nginx Full' && sudo ufw --force enable

# 11) 시간대 (정산·하자보증 판정이 어긋나지 않도록)
sudo timedatectl set-timezone Asia/Seoul

# 12) 점검
sudo -u bokguon ./venv/bin/python manage.py check
#  ⚠⚠ [라운드285] 세 비밀번호를 안 넣으면 smoke_test.py 는 검사를 하나도 안 돌고
#    종료코드 2 로 끝난다(round125) — go-live 를 이미 했다면 종료코드 4(데모
#    계정 부재로 핵심 회귀 검사 대부분 건너뜀)가 정상이니 당황하지 말 것.
export BOKGUON_TEST_ADMIN_PW="bokguon2026"
export BOKGUON_TEST_INSURER_PW="bokguon2026"
export BOKGUON_TEST_PARTNER_PW="partner2026"
./venv/bin/python smoke_test.py https://실제도메인
unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW
```

---

## 3. Windows 서버 (사내 서버)

```powershell
# 관리자 권한 PowerShell
cd C:\bokguon
.\deploy\windows_setup.ps1 -Domain bokguon.olymposnetworks.com
```

가상환경 → 의존성 → `.env` 생성 → **파일 ACL 제한** → DB 초기화 → 관리자 계정 →
**NSSM 서비스 등록(로그 회전 포함)** → 방화벽 → 작업 스케줄러(백업·접속기록 파기·개인정보 파기) → 점검.

> ### ⚠ **예약 실행(sweep)을 반드시 따로 등록한다**
> `windows_setup.ps1` 은 백업·접속기록 파기만 예약한다. **5분마다 도는 `manage.py sweep`
> 이 없으면** 입찰이 자동 마감되지 않고, 출동 기한이 지나도 다음 업체로 안 넘어가며,
> 완료보고 지연 표시·보험사 승인 독촉·문자/알림톡 실발송·웹훅 재전송이 전부 멈춘다.
> **코드는 다 있는데 아무 일도 안 일어나는** 상태라 증상만 봐서는 원인을 못 찾는다.
>
> ```powershell
> # 관리자 PowerShell
> .\deploy\복구온_예약실행_등록.ps1 -RunNow
> Get-ScheduledTask -TaskName 복구온_스윕      # 등록 확인
> ```
> 리눅스를 `bootstrap.sh` 없이 수동 설치했다면 크론에 직접 넣는다:
> ```bash
> */5 * * * * cd /opt/bokguon && ./venv/bin/python manage.py sweep >> logs/sweep.log 2>&1
> ```
> 확인은 예약 화면이 아니라 **`manage.py check` 의 「마감 점검」 줄**로 한다
> (30분 넘게 안 돌면 경고가 뜬다 — 그게 실제로 돌았다는 유일한 증거다).

> ### ℹ `deploy/일일백업.bat` — 윈도에서 검증된 대안 통합 스크립트
> `windows_setup.ps1` 은 백업·접속기록 파기·개인정보 파기를 **서로 다른 이름의
> 예약 작업 3개**로 나눠 등록한다. 이 저장소에는 그 셋(+ 자가점검)을 **작업
> 하나**로 묶어 실행하고, 각 단계의 성공·실패를 명시적으로 기록하는
> `deploy/일일백업.bat` 도 함께 있다 — 실제 운영에서 오래 검증된 경로다.
>
> ⚠⚠ **[라운드68] 둘은 백업 범위가 다르다 — "어느 쪽이든 상관없다"가 아니다.**
> `windows_setup.ps1` 은 시공 사진(`uploads/`) 백업용 4번째 예약 작업
> (`복구온_사진백업`, robocopy)을 **따로** 등록한다. `일일백업.bat` 는 DB 백업·
> 개인정보파기·접속기록파기·자가점검 4단계뿐이고 **사진 백업이 아예 없다.**
> `일일백업.bat` 만 쓰면 시공 사진(하자·분쟁 증빙)이 조용히 백업되지 않는다 —
> 쓰려면 `windows_setup.ps1` 의 사진 백업 예약 작업을 따로 등록하거나
> `일일백업.bat` 에 robocopy 단계를 추가해야 한다.
> 섞어 등록하면 같은 작업(백업·파기)을 이중으로 돌릴 수 있다 — DB 백업 쪽은
> `windows_setup.ps1` 로 설치했다면 `일일백업.bat` 는 등록하지 않는다(또는
> 그 반대). 단, 사진 백업만은 위 이유로 `windows_setup.ps1` 쪽을 반드시 쓴다.
> 확인은 여기서도 `manage.py check` 로 한다.

> ⚠ **TLS 리버스 프록시를 반드시 앞에 둔다.**
> 앱은 `127.0.0.1:8771` 에만 바인딩된다. IIS(ARR) 또는 nginx for Windows 로 443 을 받아
> 프록시하고, `X-Forwarded-For` / `X-Forwarded-Proto` 를 전달해야 한다.
> HTTPS 가 없으면 운영 모드의 Secure 쿠키 때문에 **로그인이 유지되지 않는다.**

NSSM 은 https://nssm.cc 에서 받아 PATH 에 두거나 `-NssmExe C:\tools\nssm.exe` 로 지정한다.

---

## 4. 배포 산출물에 넣지 말아야 할 것

| 파일 | 이유 |
|---|---|
| `bokguon.db`, `*.db-wal`, `*.db-shm` | **개발용 데모 데이터와 기본 비밀번호 계정이 그대로 운영으로 넘어간다** |
| `.env` | 개발용 시크릿이 운영에 섞인다. 서버에서 새로 생성할 것 |
| `*.log`, `logs/`, `backups/` | 개발 중 접속 IP 등 개인정보 포함 |
| `dev_cert.pem`, `dev_key.pem` | 자체 서명 인증서 (개발 전용) |
| `__pycache__/` | 불필요 |

`bootstrap.sh` 와 `.gitignore` 가 이미 제외하지만, **수동으로 복사할 때는 직접 확인**해야 한다.

```bash
# 배포용 묶음 만들기
tar --exclude='*.db*' --exclude='.env' --exclude='*.log' --exclude='logs' \
    --exclude='backups' --exclude='__pycache__' --exclude='dev_*.pem' \
    -czf bokguon_deploy.tar.gz bokguon_service/
```

---

## 5. 운영 명령 모음

```bash
cd /opt/bokguon

./venv/bin/python manage.py check          # 배포 전/정기 점검
./venv/bin/python manage.py backup         # 즉시 백업 (무결성 검증 포함)
./venv/bin/python manage.py restore <파일> --yes   # 복구 (서비스 중지 후)
./venv/bin/python manage.py migrate        # 스키마 갱신 (데이터 보존)
./venv/bin/python manage.py create-admin <아이디>
./venv/bin/python manage.py reset-pw admin <아이디>
./venv/bin/python manage.py prune-logs     # 보관기간 지난 접속기록 파기
./venv/bin/python manage.py prune-personal # 처리방침에 약속한 개인정보 파기 (계좌·피해자 연락처)
./venv/bin/python manage.py sweep          # 예약 실행 1회 수동 (경매마감·출동기한·독촉·실발송)
./venv/bin/python manage.py stats

systemctl status bokguon           # 상태
systemctl restart bokguon          # 재시작
journalctl -u bokguon -f           # 실시간 로그
tail -f /opt/bokguon/bokguon.log   # 애플리케이션 오류 로그
```

> ⚠⚠ [라운드310] `manage.py backup` 은 압축하지 않는다(평문 `.db`). 디스크
> 용량이 빠듯하면 `deploy/backup.sh` 를 대신 크론에 등록해도 된다 — 같은
> 무결성 있는 온라인 백업을 만든 뒤 gzip 으로 압축한다(`.db.gz`). 둘 중
> 하나만 크론에 등록할 것(둘 다 등록하면 같은 시각에 두 벌이 쌓인다).
> `deploy/backup_selfcheck.py`·`manage.py check` 는 두 형식(`.db`/`.db.gz`)
> 을 이미 함께 본다.

### 코드 갱신 배포

```bash
cd /opt/bokguon
sudo -u bokguon ./venv/bin/python manage.py backup      # 1) 먼저 백업
sudo rsync -a --exclude='.env' --exclude='*.db*' --exclude='backups' \
    --exclude='logs' --exclude='*.log' ~/bokguon_src/ /opt/bokguon/   # 2) 코드만 교체
sudo chown -R bokguon:bokguon /opt/bokguon
sudo -u bokguon ./venv/bin/pip install -r requirements.txt
sudo -u bokguon ./venv/bin/python manage.py migrate     # 3) 스키마 갱신
sudo systemctl restart bokguon                          # 4) 재시작
#  ⚠⚠ [라운드285] 실운영은 이미 go-live 를 거친 뒤라 데모 계정이 없다 — 아래
#    비밀번호를 넣어도 로그인 이후 검사 대부분은 건너뛰고 종료코드 4 가
#    정상이다(공개면·레이트리밋 등은 그래도 검증됨). 회귀 검사까지 보려면
#    운영용 검증 계정을 별도로 두고 그 계정으로 다시 실행할 것.
export BOKGUON_TEST_ADMIN_PW="bokguon2026"
export BOKGUON_TEST_INSURER_PW="bokguon2026"
export BOKGUON_TEST_PARTNER_PW="partner2026"
./venv/bin/python smoke_test.py https://도메인           # 5) 검증
unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW
```

---

## 6. 정기 점검 (개인정보 내부 관리계획 제16조)

| 주기 | 항목 | 방법 |
|---|---|---|
| 매일(자동) | DB 백업 + 무결성 검증 | 크론 03:00 |
| 매주(자동) | 보관기간 지난 접속기록 파기 | 크론 일요일 04:00 |
| 매주(자동) | 처리방침에 약속한 개인정보 파기(계좌·피해자 연락처 등) | 크론/작업 스케줄러 일요일 04:30 |
| 매월 | 접속기록 점검 (계좌 열람·비정상 접속) | 관리자 콘솔 → 접속통계·감사로그 |
| 매월 | OS·라이브러리 보안 업데이트 | `apt update && apt upgrade` |
| 분기 | **백업 복구 리허설** | 별도 서버에서 `manage.py restore` |
| 분기 | 의존성 취약점 확인 | `pip list --outdated` |
| 연 1회 | 취급자 개인정보 교육 | 내부 관리계획 제14조 |
| 연 1회 | 내부 관리계획 이행 점검 | `manage.py check` + `smoke_test.py` |

---

## 7. 알려진 제약 (오픈 후 개선 대상)

정직하게 적어 둔다. 이 상태를 알고 배포하는 것과 모르고 배포하는 것은 다르다.

| 항목 | 현재 상태 | 영향 | 개선 계획 |
|---|---|---|---|
| **알림톡·문자 발송** | **코드 완성 · 키만 넣으면 켜짐** | 팝빌 어댑터(`notify_popbill.py`)가 붙어 있고 발송대기함에 실발송 버튼이 있다. `.env` 에 `POPBILL_*` + `BOKGUON_NOTIFY_ENABLED=1` 을 넣으면 **즉시 실제로 나간다**(연동 전에는 `발송대기`로만 쌓인다) | 팝빌 계약·키 발급만 남음 (`deploy/팝빌_연동가이드.md`) |
| 이메일 발송 | 미연동 | 이메일은 쓰지 않는다(문자·알림톡·인앱) | 필요 시 검토 |
| **AI 사진 자동 분류** | **파이프라인은 완성, 모델만 미연동** | 업로드·저장·검수·반려는 전부 동작한다. 다만 자동 분류가 꺼져 있어 **담당자가 직접 분류**해야 하며, 화면에도 그 사실이 표시된다 | `.env` 에 `BOKGUON_GEMINI_KEY` 를 넣으면 즉시 켜짐 (구글 AI 스튜디오 무료 등급) |
| **보험사 시스템 API 연동** | **구현됨 · 기관별 키 발급 필요** | `POST /api/v1/cases` 로 사건 자동 인입, 상태 변화는 웹훅으로 회신한다(어드민 → 발주처 → 전산 연동에서 키 발급·웹훅 주소 등록). 키를 안 준 기관은 포털 수동 등록을 쓴다 | 보험사별 규격 협의·키 발급 |
| 다중 워커 레이트 리밋 | 앱 계층은 프로세스별 | nginx `limit_req` 가 1차 방어(워커 수와 무관하게 정확), 계정 잠금은 DB 기반. 앱 계층은 보조 | Redis 도입 시 통합 |
| 관리자 MFA | 미구현 | 비밀번호 단일 인증. 관리자 IP 화이트리스트로 보완 | TOTP 도입 |
| **시공 사진 백업** | `manage.py backup` 은 **DB만** 뜬다 | `windows_setup.ps1`(robocopy)·`bootstrap.sh`(rsync 크론)은 별도 사진 백업을 이미 등록한다 — **`deploy/일일백업.bat` 만 예외로 빠져 있다**(위 콜아웃 참고) | `일일백업.bat` 사용 시 사진 백업 작업을 따로 등록 |
| ~~사진 디스크 상한~~ | **해결** | 사건당 200장·300MB 상한(`BOKGUON_MAX_PHOTOS_PER_CASE`·`BOKGUON_MAX_PHOTO_MB_PER_CASE` 로 조정) | — |
| ~~`prune-logs` VACUUM~~ | **해결** | 파기(법정의무)와 축소(VACUUM)를 분리. 예약 실행은 파기만 하고, 축소는 `--vacuum` 을 준 사람만 | — |
| ~~백업 원자성~~ | **해결** | `.part` 로 받아 무결성 통과 후 원자적 rename. 실패 시 부분 파일 삭제 | — |
| ~~정산 취소·정정~~ | **해결** | `POST /api/settlements/<id>/undo` — 입금확인·검수승인을 사유와 함께 되돌린다(감사로그). 이체완료는 돈이 나갔으므로 되돌리지 않고 반환 협의로 처리 | — |
| ~~하자 중 지급~~ | **해결** | 미해결 하자가 있으면 지급 검수 승인을 409(`DEFECT_OPEN`)로 보류 | — |
| ~~업로드 쓰기잠금~~ | **해결** | 파일 저장·HEIC 변환을 트랜잭션 밖으로 분리(저장 전부 → DB 반영 몰아서) | — |
| ~~사진 백업 세대~~ | **해결** | 리눅스는 `--backup-dir` 로 삭제분 30일 보관, Windows 는 `/MIR`→`/E` 로 삭제 미전파 | — |
| ~~restore 보존사본~~ | **해결** | `copy2` → sqlite 온라인 백업 API (WAL 미체크포인트 커밋까지 보존) | — |
| ~~빈 환경변수~~ | **해결** | `env()` 가 빈 값을 '미설정'으로 처리 — `BOKGUON_ENV=` 로 운영이 dev 로 뜨던 문제 차단 | — |
| 데이터베이스 | SQLite (WAL) | 단일 서버 전제. 동시 쓰기가 많아지면 한계 | PostgreSQL 이전 |
| systemd `ReadWritePaths` | `/opt/bokguon` 포함 | SQLite 가 같은 디렉터리에 저널 파일을 만들어 코드 경로까지 쓰기 허용 상태 | 데이터를 `/var/lib/bokguon` 으로 분리 |

### 이번 배포에서 해결된 접근성·공개면 항목

| 항목 | 조치 |
|---|---|
| 외부 CDN 글꼴 의존 | **자체 호스팅으로 전환**(`/static/fonts/`). 보험사 폐쇄망에서도 정상 렌더되고, 이용자 IP 가 국외 사업자에게 전달되지 않는다 |
| 저대비 텍스트 | `--faint` 2.97:1 → **5.24:1**, 앰버 글자 2.85:1 → **6.04:1** (WCAG AA 통과) |
| JS 실패 시 백지 | 등장 애니메이션이 콘텐츠 노출 조건이 되지 않도록 분리. **스크립트가 차단돼도 본문 전체가 보인다** |
| 모바일 전환 경로 | 좁은 화면에서 섹션 링크만 접고 **'도입 문의' 버튼은 유지** |
| 신청 폼 접근성 | `label for` 연결, `name`·`required`·`autocomplete`·`inputmode` 추가, 2단 그리드 1단 전환 |
| 봇·중복 접수 | 허니팟 + 10분 내 동일 업체·연락처 중복 차단 |
| 관리자 문의함 오차단 | 공개 폼(POST)과 관리자 조회(GET)가 같은 경로라 관리자가 새로고침만으로 차단되던 문제 → **레이트리밋을 메서드별로 분리** |
| **CSP `unsafe-inline` 제거** | 요청별 **nonce** 방식으로 전환. 인라인 이벤트 핸들러 **78곳을 전부 이벤트 위임(`data-act` + `actions.js`)으로 교체**. 이제 주입된 스크립트는 nonce 가 없어 브라우저가 실행을 거부한다 |
| **시공 사진 파이프라인** | 목업이던 「AI 사진 검수」를 실제로 구현 — 업로드(매직바이트 검증·중복 차단), 인증 경유 파일 서빙, **영수증/시공사진 분리**, 착공전→시공중→완료 정렬, 미분류 남으면 검수 승인 차단, 반려·재촬영 요청 |

### 사진 저장 경로 (운영 시 확인)

업로드된 사진은 **웹 루트 밖**(`uploads/`)에 저장되고 `/api/photos/<id>/file` 로만 나간다.
주소를 알아도 인증 없이는 받을 수 없다(사고 현장 사진 = 개인정보 포함 가능).

```bash
BOKGUON_UPLOAD_DIR=/var/lib/bokguon/uploads    # .env 로 위치 변경 가능
```
· 백업 대상에 포함할 것 — `manage.py backup` 은 **DB만** 뜬다. 사진은 별도로 백업해야 한다.
· systemd `ReadWritePaths` 에 업로드 경로를 추가해야 쓰기가 가능하다.

---

## 8. 장애 시 확인 순서

```bash
systemctl status bokguon              # 1) 프로세스가 살아 있는가
journalctl -u bokguon -n 50           # 2) 기동 실패 원인
tail -50 /opt/bokguon/bokguon.log     # 3) 애플리케이션 오류
curl -s localhost:8771/healthz        # 4) 앱이 응답하는가
sudo nginx -t                         # 5) nginx 설정 오류
tail -50 /var/log/nginx/bokguon.error.log
df -h && free -m                      # 6) 디스크·메모리
```

**"database is locked" 가 보이면** — WAL 이 꺼졌을 가능성이 있다.
```bash
sqlite3 /opt/bokguon/bokguon.db "PRAGMA journal_mode;"   # wal 이어야 정상
```

**사용자가 오류번호를 알려주면** — 그 번호로 로그를 찾는다.
서버 오류 화면에는 `오류번호 a1b2c3d4` 형태로만 표시되고, 상세 내용은 로그에만 남는다.
```bash
grep '\[a1b2c3d4\]' /opt/bokguon/bokguon.log
```

**로그인이 안 되고 계속 로그인 화면으로 돌아가면** — HTTPS 가 아닐 가능성이 높다.
운영 모드는 Secure 쿠키를 쓰므로 평문 HTTP 에서는 세션이 유지되지 않는다.

---

## 9. 보험사 연동 규격 (`/api/v1/*` · 웹훅)

> ⚠ 이 규격은 **코드가 유일한 계약**이었다(문서가 없었다). 보험사 전산이 붙기
> 전에 여기 적어 둔다. 코드를 고치면 이 절도 함께 고칠 것.

### 인증
`Authorization: Bearer <키>` 또는 `X-API-Key: <키>`.
발주처의 `api_enabled=1` 이고 `status='활성'` 이어야 한다(아니면 403 `API_DISABLED`).
키는 해시로만 저장하므로 **발급 화면에서 한 번 보여줄 때 받아 두어야 한다**
(어드민 → 거래처·심사 → 발주처 → 전산 연동).

### 사건 조회 — `GET /api/v1/cases`, `GET /api/v1/cases/<접수번호>`

돈 관련 필드는 **확정 여부를 이름으로 구분한다.**

| 필드 | 뜻 | 주의 |
|---|---|---|
| `award_amount` | **확정 낙찰가**. 미확정이면 `0` | 계약금액으로 기록해도 되는 값 |
| `low_price` | **현재 최저 입찰가**(확정 아님) | 투찰이 들어올 때마다 바뀐다. 계약금액으로 쓰면 안 된다 |
| `is_awarded` | 위 둘을 헷갈리지 않게 하는 플래그 | `false` 면 `award_amount` 는 항상 0 |
| `est_price` | 가견적. **1차는 상한 · 2차는 하한** | 회차에 따라 뜻이 반대다 |
| `saving_rate` | 절감률(%). **확정가가 있을 때만** 계산 | 미확정이면 0 |

### 웹훅 이벤트

`POST <등록한 주소>` · 본문 `{"event": …, "case_no": …, "occurred_at": …, "data": {…}}`
(`occurred_at` 은 KST 문자열 `YYYY-MM-DD HH:MM:SS`)

| event | `data` 키 |
|---|---|
| `case.awarded` | `amount` · `partner_name` · `status` · `route`(`경매`/`1차합의`) |
| `case.award_canceled` | `amount` · `partner_name` · `reason` |
| `case.completed` | `status` · `reported_at` |
| `case.no_repair` | `status`(=`미수선종결`) · `reason` — 현장 확인 결과 수선하지 않기로 종결. **경매가 열리지 않으므로 이 사건은 여기서 끝난다.** |
| `case.reviewed` | `amount` · `fee` · `payout` · `status` |
| `settlement.paid` | `amount` · `fee` · `payout` · `status` |
| `ping` | `insurer` · `message` (연동 시험용) |

> `case.awarded` 는 낙찰 경로가 셋(경매 자동마감·관리자 낙찰·1차합의)인데
> **어느 경로로 와도 키가 같다.** 예전에는 경로마다 `award_amount`/`amount`,
> `partner`/`partner_name` 이 갈려 상대 파서가 깨졌다.

### 사건 접수 — `POST /api/v1/cases`
재시도 안전장치가 있다. `Idempotency-Key` 헤더(없으면 본문의 `idempotency_key`
또는 `ext_ref`)를 주면 같은 열쇠의 재요청은 **새로 만들지 않고** 기존 사건을
`200 {"duplicate": true}` 로 돌려준다. 열쇠가 없으면 종전대로 동작한다.
