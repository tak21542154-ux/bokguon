#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════
#  복구온 DB 백업 스크립트
#  ㈜올림포스네트웍스 기획팀 유경탁
#
#  cron 등록 예 (매일 새벽 3시):
#    0 3 * * * /opt/bokguon/deploy/backup.sh >> /var/log/bokguon_backup.log 2>&1
# ══════════════════════════════════════════════════════════════
set -euo pipefail

APP_DIR="${BOKGUON_DIR:-/opt/bokguon}"
DB="$APP_DIR/bokguon.db"
BACKUP_DIR="${BOKGUON_BACKUP_DIR:-/var/backups/bokguon}"
#  ⚠⚠ [라운드310] 변수 이름이 BOKGUON_BACKUP_KEEP 이었다 — bootstrap.sh·
#    windows_setup.ps1 이 .env 에 실제로 써 넣는 이름은 BOKGUON_BACKUP_
#    KEEP_DAYS(manage.py cmd_backup 도 같은 이름을 읽는다). 이 스크립트를
#    실제로 쓰는 사람이 .env 에 그 표준 이름으로 보존기간을 정해 둬도
#    이 자리는 조용히 못 보고 하드코딩 기본값(30일)으로 돌아갔다.
KEEP_DAYS="${BOKGUON_BACKUP_KEEP_DAYS:-30}"
STAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

if [ ! -f "$DB" ]; then
  echo "[$(date)] ERROR: DB를 찾을 수 없습니다 — $DB"
  exit 1
fi

# sqlite3 .backup 은 실행 중에도 무결성 있는 스냅샷을 만든다 (cp 는 위험)
OUT="$BACKUP_DIR/bokguon_$STAMP.db"
sqlite3 "$DB" ".backup '$OUT'"
gzip -9 "$OUT"

# [보안] 백업 파일에도 개인정보가 포함되므로 소유자만 접근
chmod 600 "$OUT.gz"

echo "[$(date)] 백업 완료: $OUT.gz ($(du -h "$OUT.gz" | cut -f1))"

# 보존기간 초과분 삭제
find "$BACKUP_DIR" -name 'bokguon_*.db.gz' -mtime +"$KEEP_DAYS" -delete
echo "[$(date)] ${KEEP_DAYS}일 초과 백업 정리 완료"
