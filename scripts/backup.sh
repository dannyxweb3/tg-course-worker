#!/usr/bin/env bash
# 每日备份。丢进 crontab：
#   0 4 * * * cd /opt/tg-course-worker && bash scripts/backup.sh >> logs/backup.log 2>&1
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/data/backup"
STAMP="$(date +%Y%m%d)"
KEEP_DAYS=14

mkdir -p "$DEST"

# .backup 是 SQLite 的在线备份，不会撞上 WAL 里的半截事务
sqlite3 "$ROOT/data/worker.db" ".backup '$DEST/worker-$STAMP.db'"

tar -czf "$DEST/prompts-$STAMP.tar.gz" -C "$ROOT/config" prompts

find "$DEST" -type f -mtime +"$KEEP_DAYS" -delete

echo "$(date -Is) 备份完成: worker-$STAMP.db"
