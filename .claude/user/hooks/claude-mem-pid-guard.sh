#!/usr/bin/env bash
# claude-mem's own health check trusts worker.pid without verifying the
# process is alive, so a killed worker leaves a PID file that makes every
# future session skip respawning. This clears that stale state before it
# can cause a hook timeout.
set -uo pipefail

MEM_DIR="${CLAUDE_MEM_DATA_DIR:-$HOME/.claude-mem}"
PIDFILE="$MEM_DIR/worker.pid"

if [ -f "$PIDFILE" ]; then
  pid=$(grep -o '"pid":[[:space:]]*[0-9]*' "$PIDFILE" | grep -o '[0-9]*')
  if [ -n "$pid" ] && ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$PIDFILE" "$MEM_DIR/claude-mem.db-shm" "$MEM_DIR/claude-mem.db-wal"
    echo "claude-mem: cleared stale worker.pid (pid $pid was not running). Restart Claude Code if this session already hung on a prompt." >&2
  fi
fi

echo '{"continue":true,"suppressOutput":true}'
