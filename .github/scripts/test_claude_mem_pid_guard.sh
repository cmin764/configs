#!/usr/bin/env bash
# Exercises .claude/user/hooks/claude-mem-pid-guard.sh against every state it
# is supposed to catch, without touching a live worker: `curl` is replaced
# by a PATH shim whose behaviour is driven by env vars, and HOME points at a
# throwaway directory. Runs on macOS and Linux alike, so CI covers it on
# every push.
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
GUARD="$REPO_ROOT/.claude/user/hooks/claude-mem-pid-guard.sh"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

mkdir -p "$TMP/bin" "$TMP/home/.claude" "$TMP/home/.claude-org" "$TMP/home/.claude-mem" "$TMP/home/.claude-mem-org"
cat > "$TMP/bin/curl" <<'EOF'
#!/usr/bin/env bash
# records the URL it was asked for, prints canned health JSON if any
for a in "$@"; do case "$a" in http*) echo "$a" >> "$SHIM_LOG";; esac; done
[ -n "${SHIM_HEALTH:-}" ] && printf '%s' "$SHIM_HEALTH" || exit 7
EOF
chmod +x "$TMP/bin/curl"
export PATH="$TMP/bin:$PATH" HOME="$TMP/home" SHIM_LOG="$TMP/curl.log"
printf '{"CLAUDE_MEM_WORKER_PORT": "37711"}\n' > "$HOME/.claude-mem-org/settings.json"

fails=0
# Start every case from a scrubbed env: the developer running this is
# usually inside some profile already, and inheriting its vars would turn
# the "default profile" cases into org-profile cases against real files.
SCRUB=(-u CLAUDE_CONFIG_DIR -u CLAUDE_MEM_DATA_DIR -u CLAUDE_MEM_WORKER_PORT)
run() {  # run <name> <expect-regex-on-stderr | -> [env assignments...]
  local name=$1 expect=$2; shift 2
  : > "$SHIM_LOG"
  local err
  err=$(env "${SCRUB[@]}" "$@" bash "$GUARD" 2>&1 >/dev/null)
  if [ "$expect" = "-" ]; then
    [ -z "$err" ] && echo "ok   $name" || { echo "FAIL $name: expected silence, got: $err"; fails=$((fails+1)); }
  else
    grep -qE "$expect" <<<"$err" && echo "ok   $name" || { echo "FAIL $name: expected /$expect/, got: ${err:-<nothing>}"; fails=$((fails+1)); }
  fi
}
# authMethod strings verbatim from each supported worker-service.cjs.
health() {  # health <pid> <profile dir> <authMethod>
  printf '{"pid":%s,"workerPath":"%s/plugins/cache/x/worker-service.cjs","ai":{"provider":"claude","authMethod":"%s"}}' "$1" "$HOME/$2" "$3"
}
v13='Claude Code OAuth token (read from system keychain at spawn)'
v14='Claude Code OAuth token (read from the Claude Code credential store at spawn)'
envtok='Claude Code OAuth token (env, refreshed via keychain at spawn)'
ORG="CLAUDE_CONFIG_DIR=$HOME/.claude-org CLAUDE_MEM_DATA_DIR=$HOME/.claude-mem-org"

run "org profile, own login (13.28)"                  -                 $ORG SHIM_HEALTH="$(health 5432 .claude-org "$v13 profile=.claude-org")"
run "org profile, own login (14.x)"                   -                 $ORG SHIM_HEALTH="$(health 5432 .claude-org "$v14 profile=.claude-org")"
run "org profile, inherited env token, own profile"   -                 $ORG SHIM_HEALTH="$(health 5432 .claude-org "$envtok profile=.claude-org")"
run "org profile, .env gateway token"                 -                 $ORG SHIM_HEALTH="$(health 5432 .claude-org 'Gateway auth token (from ~/.claude-mem/.env)')"
run "org profile, worker not running"                 -                 $ORG
run "default profile reading its own login"           -                 SHIM_HEALTH="$(health 2052 .claude "$v14 profile=default")"
run "org profile, other profile's worker -> MISMATCH" 'MISMATCH'        $ORG SHIM_HEALTH="$(health 2052 .claude "$v14 profile=default")"
run "org worker on default login (13.28) -> LEAK ACTIVE" 'LEAK ACTIVE.*kill 5432' $ORG SHIM_HEALTH="$(health 5432 .claude-org "$v13 profile=default")"
run "org worker on default login (14.x) -> LEAK ACTIVE"  'LEAK ACTIVE.*kill 5432' $ORG SHIM_HEALTH="$(health 5432 .claude-org "$envtok profile=default")"
run "org profile, workerPath absent (old claude-mem)" -                 $ORG SHIM_HEALTH='{"pid":1}'

# Expired/failing credentials show up as claude-mem's own failure counter.
printf '{"consecutiveFailures": 3, "lastErrorMessage": "401 invalid token"}\n' > "$HOME/.claude-mem-org/observer-health.json"
run "3 consecutive SDK failures -> warns with message"      'consecutive SDK failures.*401 invalid token' $ORG
printf '{"consecutiveFailures": 1, "lastErrorMessage": "flake"}\n' > "$HOME/.claude-mem-org/observer-health.json"
run "1 failure is not worth a warning"                      -           $ORG
rm -f "$HOME/.claude-mem-org/observer-health.json"

# Auth errors never touch that counter (verified live); the worker log line is
# the signal, and only when it postdates the current worker's boot.
mkdir -p "$HOME/.claude-mem-org/logs"
L="$HOME/.claude-mem-org/logs/claude-mem-2026-01-01.log"
printf '[x] [INFO ] [SYSTEM] HTTP server started {port=37711, pid=1}\n[x] [ERROR] [PARSER] [session-1] SDK authentication failed; run /login {preview=Failed to authenticate. API Error: 401 OAuth access token is invalid.}\n' > "$L"
run "auth failure after boot -> AUTH FAILING with detail"   'AUTH FAILING.*401 OAuth access token is invalid' $ORG
FAILLINE='[x] [ERROR] [PARSER] [session-1] SDK authentication failed; run /login {preview=Failed to authenticate. API Error: 401 OAuth access token is invalid.}'
printf '%s\n[x] [INFO ] [SYSTEM] HTTP server started {port=37711, pid=2}\n[x] [INFO ] [DB    ] STORED | obsIds=[1]\n' "$FAILLINE" > "$L"
run "auth failure before latest boot -> recovered, quiet"   -           $ORG
printf '[x] [INFO ] [SYSTEM] HTTP server started {port=37711, pid=2}\n%s\n[x] [INFO ] [DB    ] [session-1] STORED | obsIds=[2]\n' "$FAILLINE" > "$L"
run "auth failure followed by a stored observation -> quiet" -          $ORG
# claude-mem's classifier is a heuristic on the model's prose and misfires when
# the summarized work is ABOUT authentication (seen live 2026-08-28): without
# the SDK's real error text the line is not a failure.
printf '[x] [INFO ] [SYSTEM] HTTP server started {port=37711, pid=3}\n[x] [ERROR] [PARSER] [session-1] SDK authentication failed; run /login {outputClass=prose, preview=This session has completed a comprehensive suite of auth tests}\n' > "$L"
run "parser misclassifying prose about auth -> quiet"      -           $ORG
# claude-mem logs the tool payloads it observes; a developer grepping the log
# for the failure phrase must not trip the detector (also seen live).
printf '[x] [INFO ] [SYSTEM] HTTP server started {port=37711, pid=3}\n[x] [INFO ] [QUEUE ] ENQUEUED | tool=Bash(grep -E "SDK authentication failed.*API Error: 401" log) | depth=1\n' > "$L"
run "phrase inside an observed command -> not an auth failure" -        $ORG
rm -rf "$HOME/.claude-mem-org/logs"

# Port resolution order must mirror claude-mem's own: env > settings.json > uid default.
probe() {  # probe <name> <expected-port> [env assignments...]
  local name=$1 port=$2; shift 2
  run "$name (runs)" - "$@"
  grep -q ":$port/" "$SHIM_LOG" && echo "ok   $name" || { echo "FAIL $name: probed $(cat "$SHIM_LOG")"; fails=$((fails+1)); }
}
probe "port from settings.json"                    37711 $ORG
probe "env port overrides settings.json"           37799 $ORG CLAUDE_MEM_WORKER_PORT=37799
probe "uid-derived default when nothing configured" "$((37700 + $(id -u) % 100))"

# Stale pidfile housekeeping (the hook's original job) still works.
printf '{"pid": 999999, "port": 37711}\n' > "$HOME/.claude-mem-org/worker.pid"
touch "$HOME/.claude-mem-org/claude-mem.db-wal"
run "stale worker.pid cleared" 'cleared stale worker.pid' $ORG
[ -e "$HOME/.claude-mem-org/claude-mem.db-wal" ] && echo "ok   -wal kept" || { echo "FAIL -wal deleted"; fails=$((fails+1)); }
[ ! -e "$HOME/.claude-mem-org/worker.pid" ] && echo "ok   stale pidfile removed" || { echo "FAIL stale pidfile still present"; fails=$((fails+1)); }
printf '{"pid": %s, "port": 37711}\n' "$$" > "$HOME/.claude-mem-org/worker.pid"
run "live worker.pid kept" - $ORG
[ -e "$HOME/.claude-mem-org/worker.pid" ] && echo "ok   live pidfile kept" || { echo "FAIL live pidfile removed"; fails=$((fails+1)); }

# Every run must still hand control back to Claude Code.
out=$(env "${SCRUB[@]}" $ORG bash "$GUARD" 2>/dev/null)
[ "$out" = '{"continue":true,"suppressOutput":true}' ] && echo "ok   hook JSON contract" || { echo "FAIL hook JSON contract: $out"; fails=$((fails+1)); }

[ "$fails" -eq 0 ] && echo "claude-mem-pid-guard selftest ok" || { echo "$fails failure(s)"; exit 1; }
