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

# claude-mem's own health check never verifies that the worker holding this
# profile's port was actually spawned BY this profile -- a port collision
# (two profiles defaulting to the same port) or an unpatched isolation step
# (see SKILL.md's claude-mem isolation block) lets one profile silently
# reuse another's already-running worker, inheriting whatever account that
# worker authenticated as at ITS spawn time. The worker's own /api/health
# reports workerPath=__filename, which lives under <profile>/plugins/cache/
# -- a stable fingerprint of who spawned it, independent of env vars that
# could themselves be stale.
CONFIG_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
SETTINGS="$MEM_DIR/settings.json"
if [ -f "$SETTINGS" ]; then
  port=$(grep -o '"CLAUDE_MEM_WORKER_PORT":[[:space:]]*"[0-9]*"' "$SETTINGS" | grep -o '[0-9]*')
  if [ -n "$port" ]; then
    health=$(curl -s --max-time 1 "http://127.0.0.1:$port/api/health" 2>/dev/null)
    if [ -n "$health" ]; then
      worker_path=$(printf '%s' "$health" | grep -o '"workerPath":"[^"]*"' | cut -d'"' -f4)
      case "$worker_path" in
        "$CONFIG_DIR"/* | "") ;;  # ours, or field absent from an older claude-mem -- fine
        *)
          echo "claude-mem: MISMATCH -- the worker on port $port belongs to a different profile ($worker_path), not $CONFIG_DIR. It authenticated at ITS spawn time under that other profile's account; this session's memory writes may be billing/isolated wrong until fixed. See SKILL.md's claude-mem isolation block." >&2
          ;;
      esac
    fi
  fi
fi

echo '{"continue":true,"suppressOutput":true}'
