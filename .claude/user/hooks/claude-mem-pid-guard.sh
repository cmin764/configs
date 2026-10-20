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

# Billing: on 14.x claude-mem's OAuth pre-flight reads the Keychain entry
# of the config dir it resolves (CLAUDE_MEM_CLAUDE_CONFIG_DIR, else the
# spawning env's CLAUDE_CONFIG_DIR), "Claude Code-credentials-<sha256[:8]>",
# the same entry Claude Code itself uses for that profile. Only a worker that
# resolves to the default ~/.claude reads the unsuffixed, default login, and
# its /api/health says so as "profile=default" in ai.authMethod (checked
# below, live, instead of guessing from the Keychain). A credential in
# <data-dir>/.env (or CLAUDE_MEM_ENV_FILE) skips the lookup altogether.
ENV_FILE="${CLAUDE_MEM_ENV_FILE:-$MEM_DIR/.env}"

# The price of an .env credential is that it can expire (setup-tokens do,
# after about a year) and nothing upstream says so -- memory generation just
# stops. claude-mem does keep a failure counter on disk; surface it.
HEALTH_FILE="$MEM_DIR/observer-health.json"
if [ -f "$HEALTH_FILE" ]; then
  fails=$(grep -o '"consecutiveFailures":[[:space:]]*[0-9]*' "$HEALTH_FILE" | grep -o '[0-9]*$')
  if [ "${fails:-0}" -ge 2 ]; then
    msg=$(grep -o '"lastErrorMessage":[[:space:]]*"[^"]*"' "$HEALTH_FILE" | cut -d'"' -f4)
    echo "claude-mem: $fails consecutive SDK failures -- memory generation is dead until fixed (${msg:-no error message}). If this profile authenticates via $ENV_FILE, the token has probably expired: regenerate it with 'claude setup-token' under this CLAUDE_CONFIG_DIR and restart the worker." >&2
  fi
fi

# That counter does NOT move on auth errors. Verified 2026-08-28 by
# corrupting the .env token: the SDK child hung ~3 minutes, then the worker
# logged "SDK authentication failed ... 401 OAuth access token is invalid"
# and parked the batch with consecutiveFailures still 0. The log line is the
# only reliable signal -- with two qualifications learned the hard way:
#  - claude-mem's "SDK authentication failed" classification is a heuristic
#    on the model's text and misfires on ordinary prose that happens to
#    discuss authentication (seen live 2026-08-28), so the line must also
#    carry the SDK's actual error text ("API Error: 401").
#  - claude-mem logs every tool payload it observes, so the match is anchored
#    to the log's own "[time] [LEVEL] [AREA]" prefix rather than free text.
# A worker boot or any later stored observation clears the state: fixing the
# token and restarting, or the next successful summary, ends the warning.
latest_log=$(ls -t "$MEM_DIR"/logs/claude-mem-*.log 2>/dev/null | head -1)
if [ -n "$latest_log" ]; then
  auth_fail=$(awk '/^\[[^]]*\] \[INFO \] \[SYSTEM\] HTTP server started/ {hit=""; next}
                   /^\[[^]]*\] \[INFO \] \[DB    \].*STORED/ {hit=""; next}
                   /^\[[^]]*\] \[ERROR\] \[PARSER\].*SDK authentication failed.*(API Error: 401|Failed to authenticate)/ {hit=$0}
                   END {print hit}' "$latest_log")
  if [ -n "$auth_fail" ]; then
    detail=$(printf '%s' "$auth_fail" | grep -oE '401[^}]*' | head -1)
    echo "claude-mem: AUTH FAILING -- the worker's SDK calls are being rejected (${detail:-see $latest_log}) and observations are parked, not stored. If this profile authenticates via $ENV_FILE, the token is invalid or expired: regenerate it with 'claude setup-token' under this CLAUDE_CONFIG_DIR, fix $ENV_FILE, then kill the worker so it respawns." >&2
  fi
fi

# Env wins over settings.json inside claude-mem itself, so mirror that order
# here or a shell-exported port would make this probe the wrong worker.
port="${CLAUDE_MEM_WORKER_PORT:-}"
[ -z "$port" ] && [ -f "$SETTINGS" ] && \
  port=$(grep -o '"CLAUDE_MEM_WORKER_PORT":[[:space:]]*"[0-9]*"' "$SETTINGS" | grep -o '[0-9]*')
[ -z "$port" ] && port=$((37700 + $(id -u) % 100))  # claude-mem's own default

# The worker's /api/health reports workerPath=__filename, which lives under
# <profile>/plugins/cache/ -- a fingerprint of which profile spawned it that
# no stale env var can fake -- plus ai.authMethod, whose "profile=<name>"
# suffix (14.x, verified in the bundle) names the Keychain login it reads. "(env"
# in that string only means the worker inherited a CLAUDE_CODE_OAUTH_TOKEN
# fallback, which says nothing about whose login won.
health=$(curl -s --max-time 1 "http://127.0.0.1:$port/api/health" 2>/dev/null)
if [ -n "$health" ]; then
  worker_path=$(printf '%s' "$health" | grep -o '"workerPath":"[^"]*"' | cut -d'"' -f4)
  case "$worker_path" in
    "$CONFIG_DIR"/* | "") ;;  # ours, or field absent from an older claude-mem -- fine
    *)
      echo "claude-mem: MISMATCH -- the worker on port $port belongs to a different profile ($worker_path), not $CONFIG_DIR. It authenticated at ITS spawn time under that other profile's account; this session's memory writes may be billing/isolated wrong until fixed. See SKILL.md's claude-mem isolation block." >&2
      ;;
  esac
  if [ "$CONFIG_DIR" != "$HOME/.claude" ] && printf '%s' "$health" | grep -q '"authMethod":"Claude Code OAuth token [^"]* profile=default"'; then
    echo "claude-mem: LEAK ACTIVE -- the worker on port $port reads the DEFAULT profile's login (authMethod profile=default), not $CONFIG_DIR's: it was spawned without this profile's CLAUDE_CONFIG_DIR, or $SETTINGS sets CLAUDE_MEM_CLAUDE_CONFIG_DIR to ~/.claude. Fix that, then kill it (kill $(printf '%s' "$health" | grep -o '"pid":[0-9]*' | grep -o '[0-9]*')); it respawns from this session's env on the next prompt." >&2
  fi
fi

echo '{"continue":true,"suppressOutput":true}'
