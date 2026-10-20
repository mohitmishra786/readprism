#!/usr/bin/env bash
# Kept for crontabs that still call it: the backup is scripts/backup.sh
# (database dump + Redis snapshot + .env, CI-tested), with retention.
#   BACKUP_DIR=/var/backups/readprism ./backend/scripts/backup.sh
set -euo pipefail
exec "$(dirname "$0")/../../scripts/backup.sh" "${BACKUP_DIR:-./backups}"
