#!/usr/bin/env bash
# End-to-end proof of disk-janitor's delete contract in a throwaway HOME with
# shimmed uv/docker/pgrep binaries: dry-run touches nothing, --apply removes
# exactly the fixture's cache/stale dirs and nothing else, every sibling of
# profile/project data survives, and a second apply is a no-op.
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
CLEANUP="$REPO_ROOT/.claude/skills/disk-janitor/scripts/cleanup.py"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home" PATH="$TMP/bin:$PATH"
unset CLAUDE_CONFIG_DIR
mkdir -p "$TMP/bin"
export SHIM_LOG="$TMP/shim.log"
: > "$SHIM_LOG"

fails=0
ok()   { echo "ok   $1"; }
fail() { echo "FAIL $1"; fails=$((fails+1)); }

# --- shims: uv, docker, pgrep. brew/claude-tmp are skipped via --skip below,
# so they need no shim; xcrun is left real (only used if a simulator fixture
# exists, which this test deliberately doesn't create). ---

cat > "$TMP/bin/uv" <<EOF
#!/usr/bin/env bash
echo "uv \$*" >> "$SHIM_LOG"
case "\$*" in
  --version) echo "uv 0.0.0-shim" ;;
  "python dir") echo "$HOME/.local/share/uv/python" ;;
  "python list --only-installed")
    # Real uv output reports each interpreter's own binary path, which for
    # the 3.14 install goes through the minor-version alias symlink -- the
    # exact shape that broke a naive key-derived install dir.
    printf 'cpython-3.14.6-macos-aarch64-none    %s/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin/python3.14\n' "$HOME"
    printf 'cpython-3.13.15-macos-aarch64-none   %s/.local/share/uv/python/cpython-3.13.15-macos-aarch64-none/bin/python3.13\n' "$HOME" ;;
  "tool dir") echo "$HOME/.local/share/uv/tools" ;;
  "cache prune") : ;;
  "python uninstall "*)
    rm -rf "$HOME/.local/share/uv/python/\$3" ;;
esac
EOF
chmod +x "$TMP/bin/uv"

cat > "$TMP/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >> "$SHIM_LOG"
case "$*" in
  --version) echo "Docker version 0.0.0-shim" ;;
  info) exit 0 ;;
  "system df --format {{.Type}}"*)
    printf 'Images\t500MB (50%%)\nContainers\t50MB (100%%)\nLocal Volumes\t0B (0%%)\nBuild Cache\t20MB\n' ;;
  "images -q -f dangling=true") echo "img1" ;;
  "inspect --format {{.Size}} img1") echo "10485760" ;;
  "image prune -f"|"image prune -a -f"|"builder prune -f"|"container prune -f") : ;;
esac
EOF
chmod +x "$TMP/bin/docker"

cat > "$TMP/bin/pgrep" <<'EOF'
#!/usr/bin/env bash
echo "pgrep $*" >> "$SHIM_LOG"
[ "$2" = "Claude" ] || [ "$2" = "claude" ]
EOF
chmod +x "$TMP/bin/pgrep"

# --- fixture ---

# Electron app caches + sibling profile data that must always survive.
mkdir -p "$HOME/Library/Application Support/Claude/Cache" \
         "$HOME/Library/Application Support/Claude/vm_bundles" \
         "$HOME/Library/Application Support/Claude/Local Storage" \
         "$HOME/Library/Application Support/discord/Cache" \
         "$HOME/Library/Application Support/discord/Local Storage" \
         "$HOME/Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage" \
         "$HOME/Library/Caches/Google/Chrome/Default" \
         "$HOME/Library/Containers/com.microsoft.teams2/Data/Library/Cache"
echo x > "$HOME/Library/Application Support/Claude/Cache/f"
echo x > "$HOME/Library/Application Support/Claude/vm_bundles/rootfs.img"
echo x > "$HOME/Library/Application Support/Claude/Local Storage/f"
echo x > "$HOME/Library/Application Support/discord/Cache/f"
echo x > "$HOME/Library/Application Support/discord/Local Storage/f"
echo x > "$HOME/Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage/f"
echo x > "$HOME/Library/Application Support/Google/Chrome/Default/Bookmarks"
echo x > "$HOME/Library/Caches/Google/Chrome/Default/f"
echo x > "$HOME/Library/Containers/com.microsoft.teams2/Data/Library/Cache/f"
echo x > "$HOME/Library/Containers/com.microsoft.teams2/Data/Library/Cookies"

# Xcode: DerivedData must go, Archives must survive (shipped-build dSYMs).
mkdir -p "$HOME/Library/Developer/Xcode/DerivedData/x" "$HOME/Library/Developer/Xcode/Archives/x"
echo x > "$HOME/Library/Developer/Xcode/DerivedData/x/f"
echo x > "$HOME/Library/Developer/Xcode/Archives/x/f"

# Plugin cache: manifest points at a SHA dir, an older numeric version sits
# alongside it and must be flagged; a second plugin has two versions and no
# manifest entry and must never be flagged. The plugin-node-modules fixture
# sits under the KEPT q/1.1.0 dir, not under p/2.0.0 (itself a superseded
# version plugin-old-versions deletes wholesale) -- otherwise whichever
# target runs first zeroes the other's count, making a reclaimable>0
# assertion on plugin-node-modules order-dependent rather than a real test
# of that target on its own.
mkdir -p "$HOME/.claude/plugins/cache/v/p/1.0.0" \
         "$HOME/.claude/plugins/cache/v/p/2.0.0" \
         "$HOME/.claude/plugins/cache/v/p/b819188d2eea" \
         "$HOME/.claude/plugins/cache/v/q/1.0.0" \
         "$HOME/.claude/plugins/cache/v/q/1.1.0/node_modules" \
         "$HOME/.claude/plugins/marketplaces/m/.git"
echo x > "$HOME/.claude/plugins/cache/v/q/1.1.0/node_modules/pkg.js"
echo x > "$HOME/.claude/plugins/cache/v/p/2.0.0/file.txt"
echo "ref: refs/heads/main" > "$HOME/.claude/plugins/marketplaces/m/.git/HEAD"
cat > "$HOME/.claude/plugins/installed_plugins.json" <<EOF
{"version": 2, "plugins": {"p@v": [{"installPath": "$HOME/.claude/plugins/cache/v/p/b819188d2eea"}]}}
EOF

# Claude project memory (never touched) + an old session transcript (pruned)
# and a fresh one (kept).
mkdir -p "$HOME/.claude/projects/proj/memory"
echo x > "$HOME/.claude/projects/proj/memory/notes.md"
echo '{}' > "$HOME/.claude/projects/proj/old.jsonl"
echo '{}' > "$HOME/.claude/projects/proj/new.jsonl"

# claude-cache dirs; shell-snapshots must survive since the fixture file's
# mtime is fresh (age-gated like claude-tmp, not process-checked).
mkdir -p "$HOME/.claude/shell-snapshots" "$HOME/.claude/paste-cache" "$HOME/.claude/cache"
echo x > "$HOME/.claude/shell-snapshots/snap.sh"
echo x > "$HOME/.claude/paste-cache/f"
echo x > "$HOME/.claude/cache/f"

# Work dirs: stale node_modules/.venv must go, fresh ones and a plain file
# directly under Work/ must survive, and a dir literally named "venv" with
# no pyvenv.cfg must never be mistaken for a virtualenv.
mkdir -p "$HOME/Work/stale/node_modules" "$HOME/Work/stale/.venv" \
         "$HOME/Work/fresh/node_modules" "$HOME/Work/fresh/.venv" \
         "$HOME/Work/notavenv/venv"
echo x > "$HOME/Work/stale/node_modules/x"
echo x > "$HOME/Work/stale/src.py"
echo x > "$HOME/Work/fresh/node_modules/x"
echo x > "$HOME/Work/notavenv/venv/x"
echo x > "$HOME/Work/plainfile.txt"

# uv-managed pythons: a symlinked minor-version alias that a stale venv
# points through (must not orphan the real interpreter), and a real orphan.
mkdir -p "$HOME/.local/share/uv/python/cpython-3.14.6-macos-aarch64-none/bin" \
         "$HOME/.local/share/uv/python/cpython-3.13.15-macos-aarch64-none/bin"
echo x > "$HOME/.local/share/uv/python/cpython-3.14.6-macos-aarch64-none/bin/python3"
echo x > "$HOME/.local/share/uv/python/cpython-3.13.15-macos-aarch64-none/bin/python3"
ln -s "$HOME/.local/share/uv/python/cpython-3.14.6-macos-aarch64-none" \
      "$HOME/.local/share/uv/python/cpython-3.14-macos-aarch64-none"
cat > "$HOME/Work/stale/.venv/pyvenv.cfg" <<EOF
home = $HOME/.local/share/uv/python/cpython-3.14-macos-aarch64-none/bin
version = 3.14.6
EOF
# fresh/.venv deliberately does NOT also reference 3.14.6: the stale venv
# must be its only referrer, so if the referenced set were (re)computed
# after the stale venv is deleted instead of before, this fresh venv would
# no longer mask that regression -- 3.14.6 would wrongly become an orphan.
cat > "$HOME/Work/fresh/.venv/pyvenv.cfg" <<EOF
home = $HOME/.local/share/uv/python/cpython-3.9.6-unrelated/bin
version = 3.9.6
EOF

# Stale mtimes: everything under Work/stale, two levels deep, plus the old
# session transcript. Everything under Work/fresh keeps its just-created
# (recent) mtime.
touch -t 197001010000 \
  "$HOME/Work/stale" "$HOME/Work/stale/node_modules" "$HOME/Work/stale/node_modules/x" \
  "$HOME/Work/stale/.venv" "$HOME/Work/stale/.venv/pyvenv.cfg" "$HOME/Work/stale/src.py"
touch -t 197001010000 "$HOME/.claude/projects/proj/old.jsonl"

BASE_ARGS=(--skip brew,claude-tmp --work-dir "$HOME/Work")
snap() { find "$HOME" | wc -l | tr -d ' '; }

echo "--- environment sanity ---"
sw_vers -productVersion 2>/dev/null || true
uname -m
[ "$(uname -m)" = "arm64" ] && ok "running on arm64" || fail "not arm64: $(uname -m)"

echo "--- dry run: level 3, nothing touched ---"
before=$(snap)
out=$(python3 "$CLEANUP" --level 3 --json "${BASE_ARGS[@]}" 2>&1)
after=$(snap)
[ "$before" = "$after" ] && ok "dry run changed nothing on disk" || fail "dry run changed the tree ($before -> $after)"
grep -q 'uninstall' "$SHIM_LOG" && fail "dry run ran uv python uninstall" || ok "dry run never uninstalled a uv python"
grep -qE 'prune' "$SHIM_LOG" && fail "dry run ran a docker prune command" || ok "dry run never pruned docker"

python3 - "$out" <<'PYEOF' && ok "dry-run JSON shape and target set are correct" || fail "dry-run JSON checks failed"
import json, sys
d = json.loads(sys.argv[1])
targets = {t["target"]: t for t in d["targets"]}
assert all(t["freed"] == 0 for t in d["targets"]), "a target reported freed > 0 on dry-run"
known = {
    "uv", "pip", "npm", "bun", "trash", "chrome", "jetbrains", "logs",
    "claude-cache", "claude-chats", "docker", "node_modules", "xcode",
    "plugin-node-modules", "plugin-marketplace-git", "plugin-marketplace-binaries",
    "plugin-old-versions", "teams", "claude-desktop", "discord", "claude-memory",
    "venv", "uv-python-orphans",
}
assert set(targets) == known, f"target set mismatch: {set(targets) ^ known}"
for name in ("chrome", "teams", "claude-desktop", "discord", "venv", "node_modules",
             "plugin-old-versions", "uv-python-orphans", "claude-chats"):
    assert targets[name]["reclaimable"] > 0, f"{name} measured 0 reclaimable"
assert "shell-snapshots" in targets["claude-cache"]["note"], targets["claude-cache"]["note"]
PYEOF

echo "--- apply: level 3 + yes ---"
out=$(python3 "$CLEANUP" --level 3 --apply --yes --json "${BASE_ARGS[@]}" 2>&1)

# Electron caches gone, siblings survive.
[ -d "$HOME/Library/Application Support/Claude/Cache" ] && ok "claude-desktop Cache survived (Claude reported running, skipped)" || fail "claude-desktop Cache deleted while Claude was running"
[ -f "$HOME/Library/Application Support/Claude/vm_bundles/rootfs.img" ] && ok "vm_bundles survived" || fail "vm_bundles deleted"
[ -f "$HOME/Library/Application Support/Claude/Local Storage/f" ] && ok "Claude Local Storage survived" || fail "Claude Local Storage deleted"
[ ! -d "$HOME/Library/Application Support/discord/Cache" ] && ok "discord Cache gone" || fail "discord Cache survived"
[ -f "$HOME/Library/Application Support/discord/Local Storage/f" ] && ok "discord Local Storage survived" || fail "discord Local Storage deleted"
[ ! -d "$HOME/Library/Containers/com.microsoft.teams2/Data/Library/Cache" ] && ok "teams Cache gone" || fail "teams Cache survived"
[ -f "$HOME/Library/Containers/com.microsoft.teams2/Data/Library/Cookies" ] && ok "teams Cookies survived" || fail "teams Cookies deleted"
[ ! -d "$HOME/Library/Application Support/Google/Chrome/Default/Service Worker/CacheStorage" ] && ok "chrome Service Worker CacheStorage gone" || fail "chrome cache survived"
[ -f "$HOME/Library/Application Support/Google/Chrome/Default/Bookmarks" ] && ok "chrome Bookmarks survived" || fail "chrome Bookmarks deleted"
[ ! -d "$HOME/Library/Caches/Google/Chrome" ] && ok "chrome top-level Caches dir gone" || fail "chrome top-level Caches dir survived"

# Xcode.
[ ! -d "$HOME/Library/Developer/Xcode/DerivedData" ] && ok "Xcode DerivedData gone" || fail "DerivedData survived"
[ -f "$HOME/Library/Developer/Xcode/Archives/x/f" ] && ok "Xcode Archives survived" || fail "Archives deleted"

# Plugins.
[ ! -d "$HOME/.claude/plugins/cache/v/p/1.0.0" ] && ok "superseded plugin version 1.0.0 gone" || fail "1.0.0 survived"
[ -d "$HOME/.claude/plugins/cache/v/p/b819188d2eea" ] && ok "manifest-referenced SHA install survived" || fail "SHA install deleted"
[ ! -d "$HOME/.claude/plugins/cache/v/p/2.0.0" ] && ok "superseded plugin version 2.0.0 gone" || fail "2.0.0 survived"
[ ! -d "$HOME/.claude/plugins/cache/v/q/1.1.0/node_modules" ] && ok "plugin node_modules gone (from the kept q/1.1.0 dir)" || fail "plugin node_modules survived"
[ -d "$HOME/.claude/plugins/cache/v/q/1.0.0" ] && [ -d "$HOME/.claude/plugins/cache/v/q/1.1.0" ] && ok "unmanifested plugin version dirs both survived" || fail "unmanifested plugin version wrongly deleted"
[ ! -d "$HOME/.claude/plugins/marketplaces/m/.git" ] && ok "marketplace .git gone" || fail ".git survived"

# Claude chats / memory.
[ -f "$HOME/.claude/projects/proj/memory/notes.md" ] && ok "claude memory survived" || fail "claude memory deleted"
[ -f "$HOME/.claude/projects/proj/new.jsonl" ] && ok "recent session transcript survived" || fail "new.jsonl deleted"
[ ! -f "$HOME/.claude/projects/proj/old.jsonl" ] && ok "old session transcript pruned" || fail "old.jsonl survived"

# claude-cache: shell-snapshots survives because the fixture file's mtime
# is fresh (age-gated, not process-checked -- see _delete_aged_entries).
[ -f "$HOME/.claude/shell-snapshots/snap.sh" ] && ok "shell-snapshots survived (fresh mtime)" || fail "shell-snapshots deleted despite fresh mtime"
[ ! -f "$HOME/.claude/paste-cache/f" ] && ok "paste-cache cleaned" || fail "paste-cache survived"

# Work dirs.
[ ! -d "$HOME/Work/stale/node_modules" ] && ok "stale node_modules gone" || fail "stale node_modules survived"
[ ! -d "$HOME/Work/stale/.venv" ] && ok "stale .venv gone" || fail "stale .venv survived"
[ -d "$HOME/Work/fresh/node_modules" ] && [ -d "$HOME/Work/fresh/.venv" ] && ok "fresh node_modules/.venv survived" || fail "fresh dirs wrongly deleted"
[ -f "$HOME/Work/notavenv/venv/x" ] && ok "dir literally named venv (no pyvenv.cfg) survived" || fail "notavenv/venv wrongly deleted"
[ -f "$HOME/Work/plainfile.txt" ] && ok "plain file directly under Work/ survived" || fail "plainfile.txt deleted"

# uv pythons. cpython-3.14.6 is referenced ONLY by the stale (symlinked)
# venv this same apply just deleted -- it must still survive THIS run,
# proving the referenced set is computed before any target in the run
# deletes anything, not recomputed live after the venv is already gone
# (the bug: a single apply would otherwise delete the venv, no longer see
# its pyvenv.cfg, and uninstall the now-"orphaned" interpreter in the same
# pass, freeing more than the dry-run the user read had promised).
[ -d "$HOME/.local/share/uv/python/cpython-3.14.6-macos-aarch64-none" ] && ok "referenced uv python survived this apply despite its only referrer venv being deleted in the same run" || fail "referenced uv python wrongly cascaded away in the same apply as its venv"
[ ! -d "$HOME/.local/share/uv/python/cpython-3.13.15-macos-aarch64-none" ] && ok "orphan uv python removed" || fail "orphan uv python survived"
[ "$(grep -c 'uninstall cpython-3.13.15-macos-aarch64-none' "$SHIM_LOG")" = "1" ] && ok "exactly one uv python uninstall, the orphan" || fail "unexpected uv uninstall count"
[ "$(grep -c 'uninstall cpython-3.14.6-macos-aarch64-none' "$SHIM_LOG")" = "0" ] && ok "the just-referenced 3.14.6 was not uninstalled in this same apply" || fail "3.14.6 uninstalled in the same apply as its own venv"

# Docker: level 3 apply prunes containers + all images + build cache, never system prune.
grep -q 'docker image prune -a -f' "$SHIM_LOG" && ok "docker image prune -a -f ran at level 3" || fail "image prune -a -f missing"
grep -q 'docker container prune -f' "$SHIM_LOG" && ok "docker container prune -f ran at level 3" || fail "container prune -f missing"
grep -q 'docker builder prune -f' "$SHIM_LOG" && ok "docker builder prune -f ran" || fail "builder prune -f missing"
grep -q 'docker system prune' "$SHIM_LOG" && fail "docker system prune ran (should never run)" || ok "docker system prune never ran"

python3 - "$out" <<'PYEOF' && ok "apply JSON: total_freed > 0, claude-desktop note names the skip" || fail "apply JSON checks failed"
import json, sys
d = json.loads(sys.argv[1])
assert d["total_freed"] > 0
targets = {t["target"]: t for t in d["targets"]}
note = targets["claude-desktop"]["note"].lower()
assert "running" in note and "quit" in note, note
PYEOF

echo "--- docker at level 2 only: image + build cache, never containers ---"
shim_before=$(wc -l < "$SHIM_LOG")
python3 "$CLEANUP" --level 2 --apply --yes --only docker >/dev/null 2>&1
tail -n +$((shim_before + 1)) "$SHIM_LOG" > /tmp/docker_l2.log 2>/dev/null || sed -n "$((shim_before + 1)),\$p" "$SHIM_LOG" > /tmp/docker_l2.log
grep -q 'docker image prune -f' /tmp/docker_l2.log && ok "level 2: image prune -f ran" || fail "level 2: image prune -f missing"
grep -q 'docker builder prune -f' /tmp/docker_l2.log && ok "level 2: builder prune -f ran" || fail "level 2: builder prune -f missing"
grep -q 'docker container prune' /tmp/docker_l2.log && fail "level 2: container prune ran (should never run below level 3)" || ok "level 2: container prune never ran"
grep -q 'docker image prune -a' /tmp/docker_l2.log && fail "level 2: image prune -a ran (should only prune dangling)" || ok "level 2: only dangling images pruned"
rm -f /tmp/docker_l2.log

echo "--- docker daemon not running: null, not a silent 0 ---"
mkdir -p "$TMP/bin-down"
cat > "$TMP/bin-down/docker" <<'EOF'
#!/usr/bin/env bash
case "$*" in
  --version) echo "Docker version 0.0.0-shim" ;;
  info) exit 1 ;;
esac
EOF
chmod +x "$TMP/bin-down/docker"
out=$(PATH="$TMP/bin-down:$TMP/bin:$PATH" python3 "$CLEANUP" --level 3 --json --only docker 2>&1)
python3 - "$out" <<'PYEOF' && ok "docker daemon down: reclaimable null, not 0; total_reclaimable still sums" || fail "docker-down JSON check failed"
import json, sys
d = json.loads(sys.argv[1])
t = d["targets"][0]
assert t["reclaimable"] is None, t["reclaimable"]
assert "not running" in t["note"].lower(), t["note"]
assert d["total_reclaimable"] == 0
PYEOF

echo "--- --only with an unknown target fails fast ---"
python3 "$CLEANUP" --only nope --level 3 >/dev/null 2>&1 && fail "unknown --only target accepted" || ok "unknown --only target refused"

echo "--- second apply: now-orphaned 3.14.6 gets caught, expected and correct ---"
# Its only referrer (the stale venv) is genuinely gone from disk after the
# first apply, so on this fresh invocation cpython-3.14.6 really is
# unreferenced now -- this is real orphan detection catching up on the
# next run, not the same-run cascade the previous section proved is fixed.
out=$(python3 "$CLEANUP" --level 3 --apply --yes --json "${BASE_ARGS[@]}" 2>&1)
[ ! -d "$HOME/.local/share/uv/python/cpython-3.14.6-macos-aarch64-none" ] && ok "3.14.6 now correctly reclaimed on the next run, its venv is truly gone" || fail "3.14.6 unexpectedly survived the second apply"
[ "$(grep -c 'uninstall cpython-3.14.6-macos-aarch64-none' "$SHIM_LOG")" = "1" ] && ok "exactly one uninstall of 3.14.6 on this run" || fail "unexpected uninstall count for 3.14.6"
python3 - "$out" <<'PYEOF' && ok "second-apply JSON: total_freed > 0 (the newly-orphaned interpreter)" || fail "second-apply total_freed check failed"
import json, sys
d = json.loads(sys.argv[1])
assert d["total_freed"] > 0, d["total_freed"]
PYEOF

echo "--- third apply is the true no-op ---"
before=$(snap)
out=$(python3 "$CLEANUP" --level 3 --apply --yes --json "${BASE_ARGS[@]}" 2>&1)
after=$(snap)
[ "$before" = "$after" ] && ok "re-apply changed nothing on disk" || fail "re-apply changed the tree ($before -> $after)"
python3 - "$out" <<'PYEOF' && ok "re-apply JSON: total_freed == 0" || fail "re-apply total_freed check failed"
import json, sys
d = json.loads(sys.argv[1])
assert d["total_freed"] == 0, d["total_freed"]
PYEOF

[ "$fails" -eq 0 ] && echo "disk-janitor fixture test ok" || { echo "$fails failure(s)"; exit 1; }
