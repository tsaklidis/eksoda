#!/bin/sh
# Database backups (requirements §16, TD §3.2). Runs in the `backup` service
# (postgres:17-alpine) with PGHOST, PGUSER, PGPASSWORD and PGDATABASE set.
#
#   backup.sh once   take one backup now
#   backup.sh loop   take one backup a day, after BACKUP_HOUR_UTC, and delete backups
#                    older than BACKUP_RETENTION_DAYS (the service's command)
#
# Each backup is a custom-format dump (`pg_dump -Fc`), written to a temporary name and
# renamed when complete, so a crash never leaves a truncated file behind a real name.
# Restoring: `make restore FILE=backups/<file>` (docs/deployment.md).
set -eu

DIR=/backups
HOUR=${BACKUP_HOUR_UTC:-1}
RETENTION_DAYS=${BACKUP_RETENTION_DAYS:-30}
# The host user (uid:gid) who owns the directory and the dumps, so that `make backup`
# and `make restore` work without sudo. Dumps stay readable by that user only.
OWNER=${BACKUP_OWNER:-}
umask 077

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) backup: $*"; }

give_to_owner() {
    if [ -n "$OWNER" ]; then chown "$OWNER" "$@"; fi
}

take_backup() {
    name="eksoda-$(date -u +%Y%m%d-%H%M%S).dump"
    if pg_dump -Fc -f "$DIR/.$name.partial"; then
        mv "$DIR/.$name.partial" "$DIR/$name"
        give_to_owner "$DIR/$name"
        log "wrote $name ($(du -h "$DIR/$name" | cut -f1))"
    else
        rm -f "$DIR/.$name.partial"
        log "FAILED"
        return 1
    fi
}

prune() {
    find "$DIR" -maxdepth 1 -name 'eksoda-*.dump' -mtime "+$((RETENTION_DAYS - 1))" \
        -print -delete | sed 's/^/pruned /'
}

give_to_owner "$DIR"
find "$DIR" -maxdepth 1 -name 'eksoda-*.dump' -exec sh -c '[ -n "$1" ] && chown "$1" "$2"' _ "$OWNER" {} \;

case "${1:-once}" in
once)
    take_backup
    ;;
loop)
    log "daily backups after ${HOUR}:00 UTC, kept for ${RETENTION_DAYS} days"
    while true; do
        today=$(date -u +%Y%m%d)
        hour=$(date -u +%H)
        if [ "${hour#0}" -ge "$HOUR" ] && ! ls "$DIR"/eksoda-"$today"-*.dump >/dev/null 2>&1; then
            take_backup || true
            prune || true
        fi
        sleep 600
    done
    ;;
*)
    echo "usage: $0 once|loop" >&2
    exit 2
    ;;
esac
