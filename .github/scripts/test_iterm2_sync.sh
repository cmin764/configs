#!/usr/bin/env bash
# End-to-end check of config-sync's iTerm2 profile sync in a throwaway HOME
# and a throwaway git repo: a synthetic binary plist stands in for iTerm2's
# preferences, so no real profile is read or written. Covers the plist to repo
# export, the repo to machine deploy ($HOME round trip), float noise, and the
# push guard's git-history logic.
set -uo pipefail

REPO_ROOT=$(cd "$(dirname "$0")/../.." && pwd)
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
export HOME="$TMP/home" TMP
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@t GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@t
mkdir -p "$HOME/Library/Preferences" "$TMP/repo/.claude/skills/config-sync/scripts"
cp "$REPO_ROOT/.claude/skills/config-sync/scripts/sync.py" "$TMP/repo/.claude/skills/config-sync/scripts/"
git -C "$TMP/repo" init -q

python3 - <<'EOF'
import contextlib, importlib.util, io, json, os, plistlib, subprocess
from pathlib import Path

tmp, home = os.environ["TMP"], os.environ["HOME"]
repo = Path(tmp) / "repo"
spec = importlib.util.spec_from_file_location(
    "sync", repo / ".claude/skills/config-sync/scripts/sync.py")
s = importlib.util.module_from_spec(spec)
spec.loader.exec_module(s)
assert str(s.HOME) == home and s.REPO_ROOT == repo.resolve(), (s.HOME, s.REPO_ROOT)

REPO_FILE = repo / s.ITERM2_DST_REL
DST = Path(home) / "Library/Application Support/iTerm2/DynamicProfiles/Wandercode.json"
fails = 0


def ok(cond, msg, detail=""):
    global fails
    print(("ok   " if cond else "FAIL ") + msg + ("" if cond else f"\n     {detail}"))
    fails += not cond


def run(mode):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        s.sync_iterm2(mode)
    return out.getvalue()


def set_plist(spacing=1, with_wandercode=True):
    """What iTerm2 keeps for the profile: machine keys, a home path, and the
    workgroup triggers the DynamicProfiles file no longer carries."""
    wander = {"Name": "Wandercode", "Guid": "machine-guid", "Rewritable": True,
              "Is Dynamic Profile": True,
              "Dynamic Profile Filename": f"{home}/x/Wandercode.json",
              "Working Directory": home, "Horizontal Spacing": spacing,
              "Triggers": [{"action": "iTermEnterWorkgroupTrigger",
                            "parameter": "builtin.claudeCode", "partial": False}]}
    profiles = [{"Name": "Decoy", "Guid": "decoy"}] + ([wander] if with_wandercode else [])
    with open(s.ITERM2_PLIST, "wb") as f:
        plistlib.dump({"New Bookmarks": profiles}, f)


def git(*args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def dst_spacing():
    return json.loads(DST.read_text())["Profiles"][0]["Horizontal Spacing"]


print("--- nothing to read from ---")
out = run("status")
ok(out.startswith("[missing]"), "status reports a missing profile file, not silence", out)
DST.parent.mkdir(parents=True)
DST.write_text('{"Profiles": []}')
set_plist(with_wandercode=False)
out = run("pull")
ok("skip iterm2" in out and not REPO_FILE.exists(), "plist without Wandercode: pull skips and writes nothing", out)

print("--- plist to repo ---")
set_plist()
out = run("pull")
text = REPO_FILE.read_text()
p = json.loads(text)["Profiles"][0]
ok("pulled iTerm2 profile" in out, "pull writes the profile", out)
ok("Dynamic Profile Filename" not in p and "Is Dynamic Profile" not in p, "machine-specific keys dropped")
ok(p["Guid"] == s.ITERM2_PROFILE_GUID and p["Rewritable"] is True, "fixed Guid forced, Rewritable kept")
ok(p["Working Directory"] == "$HOME", "home path turned into $HOME", p.get("Working Directory"))
ok(p["Triggers"][0]["parameter"] == "builtin.claudeCode", "workgroup triggers carried over")
ok(home not in text and "/Users/" not in text and chr(0x2014) not in text,
   "repo file holds no home path or em dash (what CI enforces)")
ok("Decoy" not in text, "only the Wandercode profile is exported")

print("--- idempotence and float noise ---")
before = REPO_FILE.read_bytes()
out = run("pull")
ok("nothing to pull" in out and REPO_FILE.read_bytes() == before, "second pull is a byte-identical no-op", out)
REPO_FILE.write_text(text.replace('"Horizontal Spacing": 1,', '"Horizontal Spacing": 1.0,'))
before = REPO_FILE.read_bytes()
ok("[in sync]" in run("status"), "1 vs 1.0 counts as in sync")
out = run("pull")
ok("nothing to pull" in out and REPO_FILE.read_bytes() == before, "float noise does not rewrite the repo file", out)

s.ITERM2_PLIST.unlink()
out = run("status")
ok(out.startswith("[skip]") and "no local iTerm2 preferences" in out, "no plist: status still prints a row", out)
set_plist()

print("--- repo to machine ---")
DST.unlink()
out = run("restore")
d = json.loads(DST.read_text())["Profiles"][0]
ok(d["Working Directory"] == home, "restore expands $HOME back to the real home", d.get("Working Directory"))
ok("$HOME" not in DST.read_text(), "no literal $HOME reaches iTerm2")
ok(d["Triggers"] and d["Guid"] == s.ITERM2_PROFILE_GUID, "restored profile keeps triggers and Guid")

print("--- push guard ---")
set_plist(spacing=7)
out = run("push")
ok("skip" in out and dst_spacing() == 1, "live edit and no git history: push refuses", out)
set_plist()
git("add", "-A"); git("commit", "-qm", "v1")
out = run("push")
ok("nothing to push" in out, "in sync: push has nothing to do", out)
REPO_FILE.write_text(REPO_FILE.read_text().replace('"Horizontal Spacing": 1.0,', '"Horizontal Spacing": 2,'))
out = run("push")
ok(dst_spacing() == 2, "repo edited, live is a committed state: push writes", out)
git("checkout", "--", s.ITERM2_DST_REL)
set_plist(spacing=7)
out = run("push")
ok("skip" in out and dst_spacing() == 2, "live UI edit the repo never saw: push refuses", out)
REPO_FILE.write_text(REPO_FILE.read_text().replace('"Horizontal Spacing": 1.0,', '"Horizontal Spacing": 2,'))
out = run("push")
ok("skip" in out and dst_spacing() == 2, "both sides moved: push refuses", out)
set_plist()
git("add", "-A"); git("commit", "-qm", "v2")
DST.write_text(json.dumps({"Profiles": [{"Horizontal Spacing": 1}]}))  # iTerm2's stub
out = run("push")
ok(dst_spacing() == 2, "second machine: repo commit is ahead of an older live state, push writes", out)

print("--- broken inputs ---")
REPO_FILE.unlink()
ok("repo file gone" in run("push") and "repo file gone" in run("restore"), "push/restore survive a missing repo file")

raise SystemExit(1 if fails else 0)
EOF
rc=$?
[ "$rc" -eq 0 ] && echo "iterm2-sync test ok" || { echo "iterm2-sync test failed"; exit 1; }
