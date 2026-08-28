#!/usr/bin/env bash
# End-to-end simulation of `sync.py --new-profile <org>` in a throwaway HOME
# with a shimmed `claude` binary: no browser, no Keychain, no real profile
# touched. Proves the flow creates an isolated, credentialed claude-mem
# profile from nothing, and that re-running it changes nothing.
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
SYNC="$REPO_ROOT/.claude/skills/config-sync/scripts/sync.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home" PATH="$TMP/bin:$PATH"
unset CLAUDE_CONFIG_DIR CLAUDE_MEM_DATA_DIR CLAUDE_MEM_WORKER_PORT
mkdir -p "$TMP/bin" "$HOME/Work/Acme Corp" "$HOME/.claude-mem" "$HOME/.claude-mem-other"

# The shim answers exactly what --new-profile asks, and records every call so
# the test can assert the login and token steps actually ran.
cat > "$TMP/bin/claude" <<'EOF'
#!/usr/bin/env bash
echo "$CLAUDE_CONFIG_DIR $*" >> "$SHIM_LOG"
case "$*" in
  "auth status")   [ -e "$CLAUDE_CONFIG_DIR/.logged-in" ] && echo '{"loggedIn": true}' || echo '{"loggedIn": false}' ;;
  "auth login")    touch "$CLAUDE_CONFIG_DIR/.logged-in" ;;
  "plugin list")   [ -e "$CLAUDE_CONFIG_DIR/.plugins" ] && printf 'claude-mem@thedotmack\nponytail@ponytail\n' ;;
  "plugin install"*) touch "$CLAUDE_CONFIG_DIR/.plugins" ;;
  "setup-token")   echo "Token: sk-ant-oat01-SHIM (copy this)" ;;
esac
EOF
chmod +x "$TMP/bin/claude"
export SHIM_LOG="$TMP/claude.log"

DEF_W=$((37700 + $(id -u) % 100)); DEF_S=$((37877 + $(id -u) % 100))
printf '{"CLAUDE_MEM_MODEL":"m","CLAUDE_MEM_WORKER_PORT":"%s","CLAUDE_MEM_SERVER_URL":"http://127.0.0.1:%s","CLAUDE_MEM_SERVER_BETA_URL":"http://127.0.0.1:%s"}\n' "$DEF_W" "$DEF_S" "$DEF_S" > "$HOME/.claude-mem/settings.json"
# another org already holds the first candidate pair, so allocation must skip it
printf '{"CLAUDE_MEM_WORKER_PORT":"%s","CLAUDE_MEM_SERVER_URL":"http://127.0.0.1:%s"}\n' "$((DEF_W+1))" "$((DEF_W+1+200))" > "$HOME/.claude-mem-other/settings.json"

fails=0
ok()   { echo "ok   $1"; }
fail() { echo "FAIL $1"; fails=$((fails+1)); }

echo "--- dry run on a profile that doesn't exist yet ---"
out=$(python3 "$SYNC" --new-profile "acme corp" --dry-run 2>&1)
[ "$(grep -c '\[todo\]' <<<"$out")" -ge 6 ] && ok "dry run lists the work as [todo]" || fail "dry run: $out"
[ ! -e "$HOME/.claude-acme corp" ] && ok "dry run created nothing" || fail "dry run created the profile"

echo "--- real run (token piped to the hidden prompt) ---"
out=$(echo "sk-ant-oat01-SHIM" | python3 "$SYNC" --new-profile "Acme Corp" 2>&1)
grep -q 'claude setup-token' <<<"$out" && ok "setup-token step is shouted" || fail "no setup-token banner: $out"
grep -q '\[FAIL\]' <<<"$out" && fail "a step reported FAIL: $out" || ok "no step failed"
P="$HOME/.claude-acme corp"; M="$HOME/.claude-mem-acme corp"
[ -d "$P" ] && ok "profile dir created" || fail "profile dir missing"
grep -q "$P auth login" "$SHIM_LOG" && ok "login ran under the new CLAUDE_CONFIG_DIR" || fail "login not run"
grep -q "$P plugin install claude-mem@thedotmack" "$SHIM_LOG" && ok "plugins installed under the new profile" || fail "plugins not installed"
[ -L "$P/hooks" ] && [ -f "$P/settings.json" ] && ok "shared config pushed into the profile" || fail "push did not land"
grep -q 'hooks/claude-mem-pid-guard.sh' "$P/settings.json" && ok "pid-guard hooks merged into profile settings" || fail "hooks missing from settings"

python3 - "$M/settings.json" "$DEF_W" "$M" <<'EOF' && ok "claude-mem settings isolated on the next free pair, base settings kept" || fail "claude-mem settings wrong"
import json, sys
d = json.load(open(sys.argv[1])); dw = int(sys.argv[2]); m = sys.argv[3]
w = int(d["CLAUDE_MEM_WORKER_PORT"]); s = int(d["CLAUDE_MEM_SERVER_URL"].rsplit(":", 1)[1])
assert w >= dw + 2, (w, dw)                      # skipped the pair the other org holds
assert s == w + 200 and d["CLAUDE_MEM_SERVER_BETA_URL"].endswith(f":{s}")
assert d["CLAUDE_MEM_DATA_DIR"] == m and d["CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH"] == f"{m}/transcript-watch.json"
assert d["CLAUDE_MEM_QUEUE_REDIS_PREFIX"] == f"claude_mem_{w}" and d["CLAUDE_MEM_MODEL"] == "m"
EOF
grep -q '^ANTHROPIC_AUTH_TOKEN=sk-ant-oat01-SHIM$' "$M/.env" && ok ".env carries the pasted token" || fail ".env wrong: $(cat "$M/.env" 2>&1)"
[ "$(stat -f %Lp "$M/.env" 2>/dev/null || stat -c %a "$M/.env")" = "600" ] && ok ".env is mode 600" || fail ".env mode"
grep -q '\[isolated\].*\.env carries its own credential' <<<"$out" && ok "--status view reports the new profile protected" || fail "status missing"

echo "--- second run must be a no-op ---"
snap() { find "$P" "$M" -type f -not -name '*.log' -exec stat -f '%N %m' {} + 2>/dev/null || find "$P" "$M" -type f -exec stat -c '%n %Y' {} +; }
before=$(snap); : > "$SHIM_LOG"
out=$(python3 "$SYNC" --new-profile "acme corp" 2>&1)
[ "$(grep -c '\[done\]' <<<"$out")" -eq 7 ] && ok "all seven steps [done] on re-run" || fail "re-run: $out"
[ "$before" = "$(snap)" ] && ok "re-run changed no file" || fail "re-run modified files"
grep -qE 'auth login|setup-token|plugin install' "$SHIM_LOG" && fail "re-run repeated an install/login step" || ok "re-run did not repeat login/install/token"

echo "--- an unknown org is refused before anything is created ---"
python3 "$SYNC" --new-profile nope --dry-run >/dev/null 2>&1 && fail "unknown org accepted" || ok "unknown org refused"

[ "$fails" -eq 0 ] && echo "new-profile selftest ok" || { echo "$fails failure(s)"; exit 1; }
