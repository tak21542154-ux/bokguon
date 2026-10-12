#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  복구온 서비스 — 리눅스 서버 원샷 설치 스크립트
#  ㈜올림포스네트웍스 기획팀 유경탁
#
#  대상: Ubuntu 22.04 / 24.04 LTS (Debian 계열)
#
#  사용법 (서버에서 root 또는 sudo 권한으로):
#     sudo BOKGUON_DOMAIN=bokguon.olymposnetworks.com \
#          BOKGUON_EMAIL=c.common@olymposnetworks.com \
#          bash deploy/bootstrap.sh
#
#  하는 일:
#    1) 전용 시스템 계정·디렉터리 생성      2) 파이썬 가상환경·의존성 설치
#    3) .env 시크릿 자동 생성               4) DB 초기화·마이그레이션
#    5) 최고관리자 계정 발급                6) systemd 등록
#    7) nginx 설정·HTTPS 인증서 발급        8) 방화벽·백업·로그 정리 크론 등록
#    9) 배포 전 점검 + 스모크 테스트
#
#  ⚠ 여러 번 실행해도 안전하도록(멱등) 작성했다. 이미 있는 것은 건너뛴다.
#  ⚠ 기존 .env 와 DB 는 절대 덮어쓰지 않는다.
# ══════════════════════════════════════════════════════════════
set -euo pipefail

APP_USER="${BOKGUON_USER:-bokguon}"
APP_DIR="${BOKGUON_DIR:-/opt/bokguon}"
DOMAIN="${BOKGUON_DOMAIN:-}"
EMAIL="${BOKGUON_EMAIL:-}"
PORT="${BOKGUON_PORT:-8771}"
BACKUP_DIR="${BOKGUON_BACKUP_DIR:-/var/backups/bokguon}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

G='\033[92m'; Y='\033[93m'; R='\033[91m'; B='\033[1m'; N='\033[0m'
ok()   { echo -e "  ${G}✔${N} $1"; }
warn() { echo -e "  ${Y}▲${N} $1"; }
die()  { echo -e "  ${R}✘${N} $1"; exit 1; }
step() { echo -e "\n${B}$1${N}\n──────────────────────────────────────────────────────────────"; }

[ "$(id -u)" -eq 0 ] || die "root 권한이 필요합니다.  sudo bash deploy/bootstrap.sh"

echo -e "${B}"
echo "═══════════════════════════════════════════════════════════"
echo "  복구온 서비스 설치 — ㈜올림포스네트웍스 기획팀 유경탁"
echo "  설치 경로 : $APP_DIR"
echo "  도메인    : ${DOMAIN:-(미지정 — HTTPS 설정을 건너뜁니다)}"
echo "═══════════════════════════════════════════════════════════"
echo -e "${N}"

# ── 1. 시스템 패키지 ──────────────────────────────────────────
step "1. 시스템 패키지"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip sqlite3 nginx curl ufw cron >/dev/null
ok "python3 · sqlite3 · nginx · ufw · cron 설치 확인"

# 시간대 — 로그·정산 시각이 한국 기준이어야 한다
#  ⚠ 예전엔 실패해도(warn 을 찍은 바로 다음 줄에서) 무조건 "✔ 시간대 Asia/Seoul"
#    이 또 찍혔다 — 실패와 성공 문구가 나란히 뜨니 사람 눈에는 성공으로 남는다.
#    컨테이너 환경(timedatectl 없음)이 바로 그 실패가 실제로 나는 경우다.
if timedatectl set-timezone Asia/Seoul 2>/dev/null; then
  ok "시간대 Asia/Seoul"
else
  warn "시간대 설정 실패 (컨테이너 환경일 수 있음) — OS 가 KST 가 아니면 하자 기한·진행조회 만료·정산 월 판정이 어긋난다. manage.py check 의 「DB 기준 시각」줄로 배포 뒤 반드시 확인하라."
fi

# ── 2. 전용 계정·디렉터리 ─────────────────────────────────────
step "2. 전용 계정 · 디렉터리"
if id "$APP_USER" &>/dev/null; then
  ok "계정 $APP_USER 이미 존재"
else
  # 로그인 불가 시스템 계정 — 침해 시 셸 접근을 막는다
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
  ok "시스템 계정 $APP_USER 생성 (로그인 불가)"
fi

mkdir -p "$APP_DIR" "$BACKUP_DIR" "$APP_DIR/uploads"
if [ "$SRC_DIR" != "$APP_DIR" ]; then
  # .env 와 DB 는 제외하고 복사 — 재실행해도 운영 데이터가 날아가지 않는다
  rsync -a --exclude='.env' --exclude='*.db' --exclude='*.db-wal' --exclude='*.db-shm' \
        --exclude='__pycache__' --exclude='backups' --exclude='*.log' \
        --exclude='uploads' --exclude='dev_*.pem' --exclude='logs' \
        "$SRC_DIR/" "$APP_DIR/"
  ok "애플리케이션 파일 복사 ($SRC_DIR → $APP_DIR)"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR" "$BACKUP_DIR"
chmod 750 "$APP_DIR"
chmod 700 "$BACKUP_DIR"       # 백업에도 개인정보가 들어 있다
chmod 700 "$APP_DIR/uploads"  # 시공 사진 = 사고 현장 이미지
ok "권한 설정 (앱 750 · 백업 700 · 업로드 700)"

# ── 3. 파이썬 가상환경 ────────────────────────────────────────
step "3. 파이썬 가상환경 · 의존성"
if [ ! -d "$APP_DIR/venv" ]; then
  python3 -m venv "$APP_DIR/venv"
  ok "가상환경 생성"
fi
"$APP_DIR/venv/bin/pip" install -q --upgrade pip
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/venv"
ok "의존성 설치 ($( "$APP_DIR/venv/bin/pip" list 2>/dev/null | wc -l ) 패키지)"

# ── 4. 환경설정 (.env) ────────────────────────────────────────
step "4. 환경설정 · 시크릿"
if [ -f "$APP_DIR/.env" ]; then
  ok ".env 이미 존재 — 그대로 둡니다 (덮어쓰면 계좌번호 복호화 불가)"
else
  SECRET=$("$APP_DIR/venv/bin/python" -c "import secrets;print(secrets.token_hex(32))")
  ENCK=$("$APP_DIR/venv/bin/python" -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  IDXK=$("$APP_DIR/venv/bin/python" -c "import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  cat > "$APP_DIR/.env" <<EOF
# 복구온 운영 환경설정 — bootstrap.sh 자동 생성 $(date '+%Y-%m-%d %H:%M:%S')
# ⚠ BOKGUON_ENC_KEY 를 잃어버리면 저장된 계좌번호를 영구히 복호화할 수 없습니다.
#   반드시 회사 비밀번호 관리자에 사본을 보관하세요.
BOKGUON_ENV=prod
BOKGUON_SECRET_KEY=$SECRET
BOKGUON_ENC_KEY=$ENCK
BOKGUON_INDEX_KEY=$IDXK
BOKGUON_BIND=127.0.0.1:$PORT
BOKGUON_WORKERS=5
BOKGUON_BEHIND_PROXY=1
BOKGUON_FORWARDED_ALLOW=127.0.0.1
BOKGUON_SESSION_MIN=30
BOKGUON_MAX_LOGIN_FAILS=5
BOKGUON_LOCKOUT_MIN=10
BOKGUON_LOG_RETENTION_DAYS=730
BOKGUON_ADMIN_IP_ALLOW=
BOKGUON_SEED_DEMO=0
BOKGUON_SQLITE_BUSY_MS=8000
BOKGUON_BACKUP_DIR=$BACKUP_DIR
BOKGUON_BACKUP_KEEP_DAYS=30
EOF
  ok ".env 생성 (시크릿 3종 자동 발급)"
  echo -e "  ${Y}▲ 아래 암호화 키를 지금 안전한 곳에 백업하세요:${N}"
  echo "     BOKGUON_ENC_KEY=$ENCK"
fi
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
ok ".env 권한 600 (소유자만 읽기)"

# ── 5. 데이터베이스 ───────────────────────────────────────────
step "5. 데이터베이스"
FRESH_DB=0
[ -f "$APP_DIR/bokguon.db" ] || FRESH_DB=1
sudo -u "$APP_USER" env $(grep -v '^#' "$APP_DIR/.env" | xargs -d '\n') \
  "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" init
ok "스키마 반영 · 마이그레이션 완료"

if [ "$FRESH_DB" -eq 1 ]; then
  #  ⚠⚠ [라운드282] 여기 있던 ingest_partners.py 자동호출을 제거했다 — 실행해
  #    확인한 결과 이 호출은 **한 번도 성공한 적이 없다**. 그 스크립트는
  #    `python ingest_partners.py <journal.jsonl 경로>` 형태로 인자를 필수로
  #    받는데(인자 없으면 usage 만 찍고 exit 1) 여기선 인자 없이 불렀다 —
  #    `&& ok || warn` 관용구가 매번 조용히 "건너뜀" 경고로 삼켜 신선한 배포마다
  #    반복됐다. 설령 인자를 준다 해도 소용없다: 협력업체 398개사는 바로 위
  #    `manage.py init`(줄140-146)이 data/partners_seed.json 을 이미 읽어
  #    운영 DB 에 넣은 **뒤**라, ingest_partners.py 는 그 JSON 파일 자체만
  #    갱신할 뿐 이미 초기화가 끝난 DB 의 partners 표에는 반영되지 않는다.
  #    즉 이 도구는 배포 자동화가 아니라 **리서치 결과(journal.jsonl)를
  #    partners_seed.json 에 손으로 병합하고 그 결과를 커밋해 다음 배포의
  #    시드로 흘려보내는 로컬 유지보수 CLI**다 — 배포 스크립트에서 부를
  #    대상이 아니다.
  step "5-1. 최고관리자 계정 발급"
  sudo -u "$APP_USER" env $(grep -v '^#' "$APP_DIR/.env" | xargs -d '\n') \
    "$APP_DIR/venv/bin/python" "$APP_DIR/manage.py" create-admin admin --name 관리자 --role 최고관리자
  warn "위 임시 비밀번호를 안전하게 전달하세요. 최초 로그인 시 변경이 강제됩니다."
else
  ok "기존 DB 유지 (데이터 보존)"
fi

# ── 6. systemd ────────────────────────────────────────────────
step "6. systemd 서비스 등록"
#  ⚠⚠ [라운드311] bokguon.service 의 ReadWritePaths 에는 /opt/bokguon 말고
#    /var/backups/bokguon 도 하드코딩되어 있다(백업 폴더 쓰기 허용). 이 줄이
#    없던 예전에는 BOKGUON_BACKUP_DIR 을 커스텀 값으로 설치해도 유닛 파일엔
#    여전히 기본 경로가 박혀 있었다 — ProtectSystem=strict 아래에서 그 경로가
#    실제로 없으면 systemd 는 서비스 기동 자체를 거부한다(위 53행 주석과 같은 근거).
sed -e "s#/opt/bokguon#$APP_DIR#g" -e "s#User=bokguon#User=$APP_USER#" -e "s#Group=bokguon#Group=$APP_USER#" \
    -e "s#/var/backups/bokguon#$BACKUP_DIR#g" \
    "$APP_DIR/deploy/bokguon.service" > /etc/systemd/system/bokguon.service
systemctl daemon-reload
systemctl enable bokguon >/dev/null 2>&1
systemctl restart bokguon
sleep 3
if systemctl is-active --quiet bokguon; then
  ok "bokguon 서비스 기동됨"
else
  journalctl -u bokguon -n 30 --no-pager
  die "서비스 기동 실패 — 위 로그를 확인하세요."
fi

# ── 7. nginx ──────────────────────────────────────────────────
step "7. nginx 리버스 프록시"
# 레이트리밋 존은 http 블록에 있어야 한다
if ! grep -q "bokguon_login" /etc/nginx/nginx.conf 2>/dev/null; then
  cat > /etc/nginx/conf.d/bokguon_limits.conf <<'EOF'
# 복구온 레이트 리밋 존 (nginx 단 1차 방어, 앱 단이 2차)
limit_req_zone $binary_remote_addr zone=bokguon_login:10m rate=10r/m;
limit_req_zone $binary_remote_addr zone=bokguon_api:10m rate=120r/m;
EOF
  ok "레이트 리밋 존 선언"
fi

if [ -n "$DOMAIN" ]; then
  sed "s/bokguon.example.com/$DOMAIN/g" "$APP_DIR/deploy/nginx_bokguon.conf" \
    | sed "s#/opt/bokguon#$APP_DIR#g" > /etc/nginx/sites-available/bokguon
  ln -sf /etc/nginx/sites-available/bokguon /etc/nginx/sites-enabled/bokguon
  rm -f /etc/nginx/sites-enabled/default
  ok "nginx 설정 배치 ($DOMAIN)"

  # ── 8. HTTPS 인증서 ─────────────────────────────────────────
  step "8. HTTPS 인증서 (Let's Encrypt)"
  if [ ! -d "/etc/letsencrypt/live/$DOMAIN" ]; then
    apt-get install -y -qq certbot python3-certbot-nginx >/dev/null
    mkdir -p /var/www/certbot
    # 인증서가 없는 상태에서는 443 블록이 nginx 기동을 막으므로, 먼저 80 만 올린다
    cat > /etc/nginx/sites-available/bokguon_bootstrap <<EOF
server {
    listen 80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 200 'bokguon setup'; add_header Content-Type text/plain; }
}
EOF
    ln -sf /etc/nginx/sites-available/bokguon_bootstrap /etc/nginx/sites-enabled/bokguon_bootstrap
    rm -f /etc/nginx/sites-enabled/bokguon
    nginx -t >/dev/null && systemctl reload nginx

    if [ -n "$EMAIL" ]; then
      certbot certonly --webroot -w /var/www/certbot -d "$DOMAIN" \
              --email "$EMAIL" --agree-tos --non-interactive && ok "인증서 발급 완료" \
        || warn "인증서 발급 실패 — DNS 가 이 서버를 가리키는지 확인하세요."
    else
      warn "BOKGUON_EMAIL 미지정 — 인증서 발급을 건너뜁니다."
      warn "  수동 발급:  certbot certonly --webroot -w /var/www/certbot -d $DOMAIN"
    fi
    rm -f /etc/nginx/sites-enabled/bokguon_bootstrap
    ln -sf /etc/nginx/sites-available/bokguon /etc/nginx/sites-enabled/bokguon
  else
    ok "인증서 이미 존재 ($DOMAIN)"
  fi

  # 자동 갱신 확인 (certbot 패키지가 systemd 타이머를 넣어준다)
  systemctl enable --now certbot.timer 2>/dev/null && ok "인증서 자동 갱신 타이머 활성" || true

  if nginx -t 2>/dev/null; then
    systemctl reload nginx
    ok "nginx 적용"
  else
    nginx -t
    warn "nginx 설정 오류 — 위 메시지를 확인하세요."
  fi
else
  warn "BOKGUON_DOMAIN 미지정 — nginx·HTTPS 설정을 건너뜁니다."
  warn "  앱은 127.0.0.1:$PORT 에서만 응답합니다."
fi

# ── 9. 방화벽 ─────────────────────────────────────────────────
step "9. 방화벽"
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 'Nginx Full' >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || warn "ufw 활성화 실패 (클라우드 방화벽을 별도 확인하세요)"
ok "22(SSH) · 80 · 443 만 허용 — 앱 포트 $PORT 는 외부 차단"

# ── 10. 크론 (예약 실행 · 백업 · 파기) ────────────────────────
step "10. 정기 작업"
cat > /etc/cron.d/bokguon <<EOF
# 복구온 정기 작업 — bootstrap.sh 생성
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

#  ★ 5분마다 예약 실행 — **이게 없으면 서비스가 반쯤 죽은 채로 돈다.**
#    경매 마감 / 출동 기한 / 완료보고 독촉 / 보험사 승인 독촉 / 문자·알림톡 실발송이
#    전부 이 한 줄에 매달려 있다. 빠져 있으면 협력사가 '수락'만 하고 안 갔을 때
#    사건이 영원히 '수배됨'에 멈추고, 알림은 '발송대기'로 쌓이기만 한다.
#    (윈도 배포는 복구온_예약실행_등록.ps1 이 같은 일을 한다)
*/5 * * * * $APP_USER cd $APP_DIR && ./venv/bin/python manage.py sweep >> /var/log/bokguon_sweep.log 2>&1

# 매일 새벽 3시 DB 백업 (무결성 검증 포함)
0 3 * * * $APP_USER cd $APP_DIR && ./venv/bin/python manage.py backup >> /var/log/bokguon_backup.log 2>&1

# 매일 새벽 3시 20분 시공 사진 백업 (manage.py backup 은 DB만 뜨므로 별도로)
20 3 * * * $APP_USER rsync -a --delete --backup --backup-dir=$BACKUP_DIR/uploads_deleted/\$(date +\%y\%m\%d) $APP_DIR/uploads/ $BACKUP_DIR/uploads/ >> /var/log/bokguon_backup.log 2>&1
# 세대 보관본 30일 정리 — 지운 사진을 되살릴 유예 기간을 둔다
40 3 * * * $APP_USER find $BACKUP_DIR/uploads_deleted -maxdepth 1 -type d -mtime +30 -exec rm -rf {} + >> /var/log/bokguon_backup.log 2>&1

# 매주 일요일 새벽 4시 보관기간 지난 접속기록 파기 (개인정보 보호법 §21)
0 4 * * 0 $APP_USER cd $APP_DIR && ./venv/bin/python manage.py prune-logs >> /var/log/bokguon_prune.log 2>&1

#  ★ 개인정보 파기 — 처리방침에 **우리가 공개적으로 약속한 것**이다.
#    "정산 계좌 정보는 거래 종료 후 지체 없이", "피해자 성명·연락처는 하자담보책임기간
#    (24개월) 만료 후" 파기한다고 게시해 놓고 실행하는 예약이 없으면, 방침 위반이
#    그대로 사실이 된다. 지우는 대상·기준은 manage.py prune-personal 이 정한다.
30 4 * * 0 $APP_USER cd $APP_DIR && ./venv/bin/python manage.py prune-personal >> /var/log/bokguon_prune.log 2>&1
EOF
chmod 644 /etc/cron.d/bokguon
ok "5분마다 예약 실행 · 일 1회 백업 · 주 1회 파기(접속기록·개인정보) 등록"

cat > /etc/logrotate.d/bokguon <<EOF
$APP_DIR/bokguon.log /var/log/bokguon_*.log {
    weekly
    rotate 12
    compress
    delaycompress
    missingok
    notifempty
    create 0640 $APP_USER $APP_USER
}
EOF
ok "로그 로테이션 등록 (주 1회 · 12주 보관)"

# ── 11. 검증 ──────────────────────────────────────────────────
#  ⚠ **'|| warn' 이 -e 를 무력화한다.** 종전에는 manage.py check 가 '배포 불가 3개'로
#    exit 1 을 내도 노란 한 줄만 찍고 그대로 초록 '설치 완료' + exit 0 이 됐다.
#    데모 데이터 45건이 그대로인 채, 법정 고지가 빈 채, 관리자 IP 제한이 없는 채
#    "설치 완료 / 서비스: https://... " 를 보고 링크를 배포하는 흐름이 성립했다.
#    → 결과를 **변수에 담아 마지막 판정에 반영**한다.
step "11. 배포 전 점검"
cd "$APP_DIR"
CHECK_RC=0
sudo -u "$APP_USER" ./venv/bin/python manage.py check || CHECK_RC=$?
[ "$CHECK_RC" -ne 0 ] && warn "점검이 배포 불가 항목을 냈습니다(종료코드 $CHECK_RC)."

step "12. 스모크 테스트"
SMOKE_RC=0
#  ⚠⚠ [라운드125] smoke_test.py 자신은 세 계정 비밀번호가 전부 없으면 검사를
#    한 건도 안 돌고 종료코드 2 를 낸다("검사해서 통과"와 "검사 안 함"을
#    구분하려는 설계, smoke_test.py 907~914행) — 그런데 이 값을 실어 보내는
#    코드가 이 스크립트에도 없었다(저장소 전수 grep: deploy/ 아래 0곳).
#    문서대로만 실행하면 매번 "검사 0건·종료코드 2"가 나서 위 319행이 항상
#    "통과가 아닙니다"를 찍었다 — 실제 배포 상태와 무관하게. 값은
#    db.py:seed() 의 시드 기본값이다(go-live 전까지만 유효).
#  ⚠⚠⚠ [라운드285] 바로 위 문장(원래는 "go-live 후에는 그 검사만 건너뛰고
#    나머지는 계속 돈다")이 **틀렸다** — 실측: manage.py go-live 는 admins.
#    admin/staff 를 DELETE, partners/insurers.login_id='partner'|'insurer'|
#    'insurer2' 를 NULL 로 만드는데, smoke_test.py 의 test_csrf·test_bidding·
#    test_blockers·test_photos 는 전부 이 3개 로그인 결과를 물려받는 `if not
#    m`/`if not (m and p and i)` 게이트가 있어, go-live 뒤에는 CSRF·입찰·
#    이중지급방지·IDOR·정산·사진권한 등 ~90개 검사 중 ~53개가 통째로
#    건너뛰어진다 — "그 검사만"이 아니다. 이 스크립트가 배포 12단계에서
#    부르는 시점은 신규설치(go-live 전, exit 0 이 곧 전부 통과)라 이번
#    라운드는 여기 자체를 고치지 않는다 — go-live 이후 반복 실행(DEPLOY.md
#    의 다른 절차들)에서 이 사실이 새 종료코드 4 로 드러난다(아래).
export BOKGUON_TEST_ADMIN_PW="bokguon2026"
export BOKGUON_TEST_INSURER_PW="bokguon2026"
export BOKGUON_TEST_PARTNER_PW="partner2026"
if [ -n "$DOMAIN" ] && [ -d "/etc/letsencrypt/live/$DOMAIN" ]; then
  ./venv/bin/python smoke_test.py "https://$DOMAIN" || SMOKE_RC=$?
else
  warn "HTTPS 미구성 — 로컬 평문으로 공개면만 검사합니다."
  ./venv/bin/python smoke_test.py "http://127.0.0.1:$PORT" --skip-write || SMOKE_RC=$?
fi
unset BOKGUON_TEST_ADMIN_PW BOKGUON_TEST_INSURER_PW BOKGUON_TEST_PARTNER_PW
#  종료코드 2 = 검사를 하나도 안 했다 · 3 = 인증 이후를 건너뛰었다 ·
#  4 = 데모 계정이 사라져 CSRF·입찰·정산 등 핵심 회귀 검사 대부분을 건너뛰었다
#  (라운드285, smoke_test.py 자신의 판정) — 셋 다 exit 0 이 아니다.
[ "$SMOKE_RC" -eq 2 ] && warn "스모크가 **검사를 하나도 실행하지 못했습니다** — 통과가 아닙니다."
[ "$SMOKE_RC" -eq 3 ] && warn "스모크가 인증 이후 검사를 건너뛰었습니다(운영모드+평문)."
[ "$SMOKE_RC" -eq 4 ] && warn "스모크가 데모 계정 부재로 핵심 회귀 검사 대부분을 건너뛰었습니다 — 신규설치 직후라면 원인을 반드시 확인하세요."
[ "$SMOKE_RC" -eq 1 ] && warn "스모크 테스트에 실패 항목이 있습니다." 

echo
echo -e "${B}═══════════════════════════════════════════════════════════${N}"
#  ★ **판정은 마지막에 한 번만 내린다.** 설치가 끝난 것과 서비스를 열어도 되는 것은
#    다른 이야기다 — 이 구분이 없으면 초록 글자가 앞의 빨간 글자를 덮어쓴다.
if [ "$CHECK_RC" -ne 0 ] || [ "$SMOKE_RC" -ne 0 ]; then
  echo -e "  ${R}설치는 끝났지만 — 아직 열면 안 됩니다${N}"
  [ "$CHECK_RC" -ne 0 ] && echo -e "  ${R}· 배포 전 점검 미통과${N}  → ./venv/bin/python manage.py check"
  [ "$SMOKE_RC" -ne 0 ] && echo -e "  ${R}· 스모크 테스트 미통과(코드 $SMOKE_RC)${N}"
  echo "  위 항목을 처리한 뒤 두 명령을 다시 돌려 **둘 다 통과**하는지 확인하세요."
else
  echo -e "  ${G}설치 완료${N}"
fi
[ -n "$DOMAIN" ] && echo "  서비스   : https://$DOMAIN"
echo "  관리자   : ${DOMAIN:+https://$DOMAIN}/admin"
echo "  상태확인 : systemctl status bokguon"
echo "  로그     : journalctl -u bokguon -f"
echo "  재시작   : systemctl restart bokguon"
echo "  점검     : cd $APP_DIR && ./venv/bin/python manage.py check"
echo -e "${B}═══════════════════════════════════════════════════════════${N}"
#  종료코드로도 말한다 — 사람이 화면을 안 봐도(CI·로그) 실패가 전달되어야 한다.
if [ "$CHECK_RC" -ne 0 ] || [ "$SMOKE_RC" -ne 0 ]; then exit 1; fi
