#!/usr/bin/env bash
# Daily SQLite backup of the bot's database. Run by root's cron (see README):
#   0 1 * * * /home/ubuntu/finance-ai-bot/deploy/oracle/backup.sh >> /var/log/finance-bot-backup.log 2>&1
# Takes an online copy through SQLite's backup API (safe while the bot writes), checks it,
# gzips it into deploy/oracle/backups/ and keeps the last KEEP_DAYS days.
set -euo pipefail

KEEP_DAYS="${KEEP_DAYS:-14}"
cd "$(dirname "$0")"
mkdir -p backups

stamp="$(date -u +%Y%m%d-%H%M)"
tmp="data/.backup-tmp.db"
rm -f "$tmp"

docker compose exec -T bot python -c "
import sqlite3
src = sqlite3.connect('/data/finance.db')
dst = sqlite3.connect('/data/.backup-tmp.db')
src.backup(dst)
dst.close()
"

check="$(python3 -c "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('pragma integrity_check').fetchone()[0])" "$tmp")"
if [ "$check" != "ok" ]; then
    echo "$(date -u) backup integrity check failed: $check" >&2
    rm -f "$tmp"
    exit 1
fi

out="backups/finance-$stamp.db.gz"
gzip -c "$tmp" > "$out"
rm -f "$tmp"
chown -R ubuntu:ubuntu backups 2>/dev/null || true
find backups -name 'finance-*.db.gz' -mtime +"$KEEP_DAYS" -delete

echo "$(date -u) backup ok: $out ($(du -h "$out" | cut -f1))"
