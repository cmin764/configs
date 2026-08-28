#!/usr/bin/env python3
"""Sync hand-edited config between this repo and the live machine.

Modes:
  --status   report drift for every entry, change nothing (default)
  --restore  fresh machine: create symlinks, write copies/merges
  --push     repo -> machine (symlinks ensured, copies overwritten,
             merge targets deep-merged so accumulated live state survives)
  --pull     machine -> repo (copies pulled back, sensitive fields
             trimmed, iterm2 profile re-exported; merge targets are
             reported only -- never auto-pulled, or the noise we
             deliberately pruned from the template would come right back)
  --new-profile <org> [--dry-run]
             create ~/.claude-<org> for a ~/Work/<Org> directory: login,
             shared config, plugins, an isolated claude-mem data dir on
             its own ports, and the .env credential that keeps claude-mem
             off the default profile's login. Every step is skipped when
             already done, so re-running it is the way to audit a profile.

Stdlib only. Safe to re-run any mode; that repeatability is the test.
"""
import contextlib
import getpass
import io
import json
import os
import plistlib
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
HOME = Path.home()

# Files that install as a symlink: the repo copy IS the live file.
SYMLINKS = [
    (".zprofile", "~/.zprofile"),
    (".zshrc", "~/.zshrc"),
    (".vimrc", "~/.vimrc"),
    (".gitconfig", "~/.gitconfig"),
    (".gitignore_global", "~/.gitignore_global"),
]

# Same shape as SYMLINKS/MERGES, but applied once per Claude Code profile
# directory: the default ~/.claude plus any ~/.claude-<org> profile created
# for per-org account isolation (see .zshrc's chpwd hook). A fresh Mac has
# only ~/.claude, so --restore behaves exactly as before this existed.
CLAUDE_PROFILE_SYMLINKS = [
    (".claude/user/CLAUDE.md", "CLAUDE.md"),
    (".claude/user/RTK.md", "RTK.md"),
    (".claude/user/hooks", "hooks"),
    (".claude/skills", "skills"),
]
CLAUDE_PROFILE_MERGES = [
    (".claude/user/settings.json", "settings.json"),
]


def claude_profile_dirs():
    """~/.claude plus any ~/.claude-<org> profile that actually matches a
    ~/Work/<org> directory -- not a blind ~/.claude-* glob, which would also
    catch unrelated dirs other tools own (e.g. claude-mem's ~/.claude-mem)."""
    default = [HOME / ".claude"]
    work = HOME / "Work"
    if not work.is_dir():
        return default
    orgs = sorted(p.name.lower() for p in work.iterdir() if p.is_dir())
    extra = [HOME / f".claude-{org}" for org in orgs
             if (HOME / f".claude-{org}").is_dir()]
    return default + extra


ITERM2_DST_REL = "apps/iterm2/Wandercode.json"
ITERM2_DST = "~/Library/Application Support/iTerm2/DynamicProfiles/Wandercode.json"

# Files the owning app rewrites, so a plain copy in the direction it's used.
# iTerm2 is handled separately by sync_iterm2 (its repo copy is re-extracted
# from a binary plist, not just copied), so it isn't listed here.
COPIES = [
    ("apps/cursor/settings.json",
     "~/Library/Application Support/Cursor/User/settings.json"),
    ("apps/cursor/mcp.json", "~/.cursor/mcp.json"),
    ("apps/sublime/Preferences.sublime-settings",
     "~/Library/Application Support/Sublime Text/Packages/User/"
     "Preferences.sublime-settings"),
    ("apps/docker/daemon.json", "~/.docker/daemon.json"),
    # Codex's hook wiring, hand-authored the same way Claude Code's
    # settings.json hooks are. config.toml isn't tracked here: it mixes this
    # kind of hand-edited scalar with Codex's own accumulated state
    # (marketplaces/plugins/projects), the same category as Claude Code's
    # plugins/.claude.json -- see SKILL.md.
    ("apps/codex/hooks.json", "~/.codex/hooks.json"),
]

# Same shape as the app-rewritten list above, but the live file carries
# fields that must never reach a public repo (auth identity, caches).
# Pull drops them; push writes as-is.
TRIMMED_COPIES = [
    ("apps/cursor/cli-config.json", "~/.cursor/cli-config.json",
     {"authInfo", "privacyCache", "autoReviewAvailabilityCache",
      "serverConfigCache", "network"}),
]

ITERM2_PLIST = Path("~/Library/Preferences/com.googlecode.iterm2.plist").expanduser()
ITERM2_PROFILE_GUID = "D3F7A1B2-3C4D-4E5F-8A9B-0C1D2E3F4A5B"

# App-level (not per-profile) iTerm2 preferences, applied through `defaults`
# so cfprefsd stays authoritative instead of a raw plist write racing a
# running iTerm2. Int-valued only for now (all keys tracked so far are);
# extend the type if a non-int key ever needs tracking.
ITERM2_APP_PREFS_REL = "apps/iterm2/app-prefs.json"
ITERM2_APP_PREFS_DOMAIN = "com.googlecode.iterm2"
# Keys tracked regardless of what's currently in the repo file, so a first
# --pull on a machine that has never had the template can still discover them.
ITERM2_APP_PREF_KEYS = ["TabStyleWithAutomaticOption"]  # Appearance > Theme


def deep_merge(dest, src):
    """Recursively merge src into dest; src wins on conflicts, dest-only
    keys survive. Lists are unioned (dest first, then new src entries) so
    accumulated live-only entries (e.g. permission grants) aren't dropped.
    Neither input is mutated."""
    result = dict(dest)
    for key, value in src.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = result[key] + [v for v in value if v not in result[key]]
        else:
            result[key] = value
    return result


def diff_paths(dest, src, prefix=""):
    """List dotted paths present in src whose value differs from dest."""
    out = []
    for key, value in src.items():
        path = f"{prefix}.{key}" if prefix else key
        if key not in dest:
            out.append(f"{path}: missing on the other side")
        elif isinstance(value, dict) and isinstance(dest[key], dict):
            out.extend(diff_paths(dest[key], value, path))
        elif dest[key] != value:
            out.append(f"{path}: differs")
    return out


def _selftest():
    base = {"a": 1, "b": {"c": 2, "d": 3}, "grants": ["live-only"]}
    override = {"b": {"c": 99}, "e": 5, "grants": ["template", "live-only"]}
    merged = deep_merge(base, override)
    assert merged == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5,
                       "grants": ["live-only", "template"]}, merged
    assert base == {"a": 1, "b": {"c": 2, "d": 3}, "grants": ["live-only"]}, \
        "deep_merge mutated dest"
    assert override == {"b": {"c": 99}, "e": 5, "grants": ["template", "live-only"]}, \
        "deep_merge mutated src"
    assert diff_paths({"a": 1}, {"a": 1}) == []
    assert diff_paths({"a": 1}, {"a": 2}) == ["a: differs"]

    # check_claude_mem_isolation against a throwaway HOME: the three states
    # it must tell apart are "org shares the default's port/dir", "isolated
    # but the default profile is logged in", and "fully isolated".
    def isolation_report(org_settings, logged_in, env_text=None):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".claude-mem").mkdir()
            (home / ".claude-mem" / "settings.json").write_text(json.dumps({
                "CLAUDE_MEM_DATA_DIR": str(home / ".claude-mem"),
                "CLAUDE_MEM_WORKER_PORT": str(CLAUDE_MEM_DEFAULT_WORKER_PORT),
                "CLAUDE_MEM_SERVER_URL": f"http://127.0.0.1:{CLAUDE_MEM_DEFAULT_SERVER_PORT}",
                "CLAUDE_MEM_SERVER_BETA_URL": f"http://127.0.0.1:{CLAUDE_MEM_DEFAULT_SERVER_PORT}"}))
            (home / ".claude-mem-org").mkdir()
            (home / ".claude-mem-org" / "settings.json").write_text(json.dumps(org_settings))
            if env_text is not None:
                (home / ".claude-mem-org" / ".env").write_text(env_text)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                check_claude_mem_isolation(home, lambda: logged_in)
            return out.getvalue()
    isolated = isolated_claude_mem_settings(
        {}, Path("/x/.claude-mem-org"), str(CLAUDE_MEM_DEFAULT_WORKER_PORT + 1),
        str(CLAUDE_MEM_DEFAULT_WORKER_PORT + 1 + CLAUDE_MEM_SERVER_PORT_OFFSET))
    shared = dict(isolated, CLAUDE_MEM_WORKER_PORT=str(CLAUDE_MEM_DEFAULT_WORKER_PORT))
    r = isolation_report(shared, False)
    assert "[LEAK RISK]" in r and "CLAUDE_MEM_WORKER_PORT" in r, r
    r = isolation_report(isolated, True)
    assert "[isolated]     .claude-mem-org" in r and "default profile (~/.claude) is logged in" in r, r
    r = isolation_report(isolated, False)
    assert r.count("[isolated]") == 2 and "LEAK" not in r, r
    # An .env credential makes the default login irrelevant for that org...
    r = isolation_report(isolated, True, "ANTHROPIC_AUTH_TOKEN=sk-ant-oat01-test\n")
    assert ".env carries its own credential" in r and "LEAK" not in r, r
    # ...but an .env with only empty placeholders does not.
    r = isolation_report(isolated, True, "ANTHROPIC_API_KEY=\nANTHROPIC_AUTH_TOKEN=\n")
    assert "[LEAK RISK]    default profile" in r, r

    # --new-profile's pure parts: port blocks skip whatever any profile uses,
    # and the isolated settings touch exactly the six colliding keys.
    d, off = CLAUDE_MEM_DEFAULT_WORKER_PORT, CLAUDE_MEM_SERVER_PORT_OFFSET
    free = lambda p: True  # noqa: E731 -- no real sockets in the selftest
    assert allocate_claude_mem_ports(set(), set(), free) == (str(d + 1), str(d + 1 + off))
    assert allocate_claude_mem_ports({str(d + 1)}, set(), free) == (str(d + 2), str(d + 2 + off))
    assert allocate_claude_mem_ports(set(), {str(d + 1 + off)}, free) == (str(d + 2), str(d + 2 + off))
    assert allocate_claude_mem_ports(set(), set(), lambda p: p != d + 1) == (str(d + 2), str(d + 2 + off))
    assert allocate_claude_mem_ports(set(), set(), lambda p: p != d + 1 + off) == (str(d + 2), str(d + 2 + off))
    # ten orgs allocate ten distinct pairs with no overlap between worker and server sides
    used_w, used_s, seen = set(), set(), set()
    for _ in range(10):
        w_, s_ = allocate_claude_mem_ports(used_w, used_s, free)
        assert w_ not in seen and s_ not in seen, (w_, s_, seen)
        seen.update({w_, s_}); used_w.add(w_); used_s.add(s_)
    w, srv = str(d + 1), str(d + 1 + off)
    s = isolated_claude_mem_settings(
        {"CLAUDE_MEM_MODEL": "m", "CLAUDE_MEM_WORKER_PORT": str(CLAUDE_MEM_DEFAULT_WORKER_PORT)},
        Path("/h/.claude-mem-org"), w, srv)
    assert s["CLAUDE_MEM_MODEL"] == "m" and s["CLAUDE_MEM_WORKER_PORT"] == w
    assert s["CLAUDE_MEM_DATA_DIR"] == "/h/.claude-mem-org"
    assert s["CLAUDE_MEM_QUEUE_REDIS_PREFIX"] == f"claude_mem_{w}"
    assert s["CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH"] == "/h/.claude-mem-org/transcript-watch.json"
    assert s["CLAUDE_MEM_SERVER_URL"] == s["CLAUDE_MEM_SERVER_BETA_URL"] == f"http://127.0.0.1:{srv}"
    assert CLAUDE_MEM_CRED_RE.search("ANTHROPIC_AUTH_TOKEN=sk-x\n") and \
        not CLAUDE_MEM_CRED_RE.search("ANTHROPIC_AUTH_TOKEN=\n# ANTHROPIC_API_KEY=y\n")
    # The registry is whatever settings.json files exist, minus the profile
    # being (re)built, with claude-mem's defaults filled in for missing keys.
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        for name, body in (("a", {"CLAUDE_MEM_WORKER_PORT": "40000", "CLAUDE_MEM_SERVER_URL": "http://127.0.0.1:40200"}),
                           ("b", {}), ("self", {"CLAUDE_MEM_WORKER_PORT": "1"})):
            (home / f".claude-mem-{name}").mkdir()
            (home / f".claude-mem-{name}" / "settings.json").write_text(json.dumps(body))
        uw, us = used_claude_mem_ports(home, exclude=home / ".claude-mem-self")
        assert uw == {"40000", str(CLAUDE_MEM_DEFAULT_WORKER_PORT)}, uw
        assert us == {"40200", str(CLAUDE_MEM_DEFAULT_SERVER_PORT)}, us
    print("selftest ok")


def repo_path(rel):
    return REPO_ROOT / rel


def home_path(rel):
    return Path(rel).expanduser()


def ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def backup_if_real_file(path):
    if path.exists() and not path.is_symlink():
        backup = path.with_name(path.name + ".pre-config-sync.bak")
        n = 1
        while backup.exists():
            backup = path.with_name(f"{path.name}.pre-config-sync.bak.{n}")
            n += 1
        print(f"  backing up existing {path} -> {backup}")
        shutil.move(str(path), str(backup))


def sync_symlink(src_rel, dst_rel, mode):
    src = repo_path(src_rel)
    dst = home_path(dst_rel)
    if mode == "status":
        if dst.is_symlink() and dst.resolve() == src.resolve():
            print(f"[symlink ok]   {dst_rel}")
        elif dst.is_symlink():
            print(f"[broken link]  {dst_rel} (wrong or dangling target, --restore will fix)")
        elif not dst.exists():
            print(f"[missing]      {dst_rel} (not yet linked)")
        else:
            print(f"[not a link]   {dst_rel} (real file, --restore will back it up)")
        return
    if mode == "pull":
        return  # nothing to pull, it's the same inode as the repo file
    # restore / push: idempotent link creation
    backup_if_real_file(dst)
    ensure_parent(dst)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    dst.symlink_to(src)
    print(f"  linked {dst_rel} -> {src_rel}")


def sync_copy(src_rel, dst_rel, mode):
    src = repo_path(src_rel)
    dst = home_path(dst_rel)
    if mode == "status":
        if not dst.exists():
            print(f"[missing]      {dst_rel}")
        elif not src.exists():
            print(f"[missing src]  {dst_rel} (repo file gone, check COPIES)")
        elif src.read_bytes() == dst.read_bytes():
            print(f"[in sync]      {dst_rel}")
        else:
            print(f"[differs]      {dst_rel}")
        return
    if mode in ("restore", "push"):
        ensure_parent(dst)
        shutil.copy2(src, dst)
        print(f"  wrote {dst_rel}")
    elif mode == "pull":
        if not dst.exists():
            print(f"  skip {src_rel}: nothing live to pull")
            return
        ensure_parent(src)
        shutil.copy2(dst, src)
        print(f"  pulled {dst_rel} -> {src_rel}")


def sync_trimmed(src_rel, dst_rel, drop_keys, mode):
    src = repo_path(src_rel)
    dst = home_path(dst_rel)
    if mode == "status":
        if not dst.exists():
            print(f"[missing]      {dst_rel}")
            return
        live = json.loads(dst.read_text())
        for k in drop_keys:
            live.pop(k, None)
        repo_json = json.loads(src.read_text()) if src.exists() else {}
        print(f"[{'in sync' if live == repo_json else 'differs'}]      "
              f"{dst_rel} (trimmed compare)")
        return
    if mode in ("restore", "push"):
        sync_copy(src_rel, dst_rel, mode)
        return
    if mode == "pull":
        if not dst.exists():
            print(f"  skip {src_rel}: nothing live to pull")
            return
        live = json.loads(dst.read_text())
        for k in drop_keys:
            live.pop(k, None)
        ensure_parent(src)
        src.write_text(json.dumps(live, indent=2) + "\n")
        print(f"  pulled {dst_rel} -> {src_rel} (dropped {', '.join(sorted(drop_keys))})")


def sync_merge(src_rel, dst_rel, mode):
    src = repo_path(src_rel)
    dst = home_path(dst_rel)
    repo_json = json.loads(src.read_text()) if src.exists() else {}
    if mode == "status":
        if not dst.exists():
            print(f"[missing]      {dst_rel}")
            return
        live_json = json.loads(dst.read_text())
        diffs = diff_paths(live_json, repo_json)
        if not diffs:
            print(f"[in sync]      {dst_rel}")
        else:
            print(f"[differs]      {dst_rel}:")
            for d in diffs:
                print(f"                 {d}")
        return
    if mode in ("restore", "push"):
        live_json = json.loads(dst.read_text()) if dst.exists() else {}
        merged = deep_merge(live_json, repo_json)
        ensure_parent(dst)
        dst.write_text(json.dumps(merged, indent=2) + "\n")
        print(f"  merged repo values into {dst_rel} (live-only keys preserved)")
    elif mode == "pull":
        if not dst.exists():
            print(f"  skip {src_rel}: nothing live to pull")
            return
        live_json = json.loads(dst.read_text())
        diffs = diff_paths(repo_json, live_json)
        if diffs:
            print(f"  NOT auto-pulled ({dst_rel} differs from the template):")
            for d in diffs:
                print(f"    {d}")
            print("  review by hand -- pulling automatically would re-add "
                  "the noise the template deliberately strips.")
        else:
            print(f"  {dst_rel} matches the template, nothing to pull")


def sync_iterm2(mode):
    if mode == "status":
        sync_copy(ITERM2_DST_REL, ITERM2_DST, mode)
        return
    if mode == "pull":
        if not ITERM2_PLIST.exists():
            print("  skip iterm2: no local iTerm2 preferences to export from")
            return
        with open(ITERM2_PLIST, "rb") as f:
            d = plistlib.load(f)
        profiles = d.get("New Bookmarks", [])
        if not profiles:
            print("  skip iterm2: no profiles in the local plist")
            return
        profile = next((p for p in profiles if p.get("Name") == "Wandercode"), None)
        if profile is None:
            print("  skip iterm2: no profile named 'Wandercode' in the local plist "
                  "-- rename your profile first, or this would overwrite the "
                  "template with the wrong one")
            return
        profile = dict(profile)
        profile["Guid"] = ITERM2_PROFILE_GUID
        if profile.get("Working Directory", "").startswith(str(HOME)):
            profile["Working Directory"] = "$HOME"
        out_path = repo_path(ITERM2_DST_REL)
        ensure_parent(out_path)
        out_path.write_text(json.dumps({"Profiles": [profile]}, indent=2, default=str))
        print(f"  pulled iTerm2 profile '{profile.get('Name')}' -> {ITERM2_DST_REL}")
    elif mode in ("restore", "push"):
        sync_copy(ITERM2_DST_REL, ITERM2_DST, mode)


def _defaults_read_int(domain, key):
    result = subprocess.run(["defaults", "read", domain, key],
                             capture_output=True, text=True)
    return int(result.stdout.strip()) if result.returncode == 0 else None


def sync_iterm2_app_prefs(mode):
    src = repo_path(ITERM2_APP_PREFS_REL)
    repo_prefs = json.loads(src.read_text()) if src.exists() else {}
    if mode == "status":
        for key in ITERM2_APP_PREF_KEYS:
            value = repo_prefs.get(key)
            live = _defaults_read_int(ITERM2_APP_PREFS_DOMAIN, key)
            state = "in sync" if live == value else "differs"
            print(f"[{state}]      iterm2 app pref {key} (repo={value} live={live})")
        return
    if mode in ("restore", "push"):
        for key in ITERM2_APP_PREF_KEYS:
            if key not in repo_prefs:
                continue
            subprocess.run(["defaults", "write", ITERM2_APP_PREFS_DOMAIN, key,
                             "-int", str(repo_prefs[key])], check=True)
        if repo_prefs:
            print(f"  wrote iterm2 app prefs: {', '.join(repo_prefs)} "
                  "(quit and reopen iTerm2 to pick up)")
    elif mode == "pull":
        live_prefs = {k: _defaults_read_int(ITERM2_APP_PREFS_DOMAIN, k)
                      for k in ITERM2_APP_PREF_KEYS}
        live_prefs = {k: v for k, v in live_prefs.items() if v is not None}
        if not live_prefs:
            print(f"  skip {ITERM2_APP_PREFS_REL}: nothing live to pull")
            return
        ensure_parent(src)
        src.write_text(json.dumps(live_prefs, indent=2) + "\n")
        print(f"  pulled iterm2 app prefs -> {ITERM2_APP_PREFS_REL}")


def _default_profile_logged_in():
    """True when the unsuffixed 'Claude Code-credentials' keychain entry --
    the default ~/.claude login -- exists. Org profiles get a hashed suffix,
    so this is exactly the entry claude-mem's pre-flight would pick up."""
    if sys.platform != "darwin":
        return False
    return subprocess.run(
        ["security", "find-generic-password", "-s", "Claude Code-credentials",
         "-a", getpass.getuser()], capture_output=True).returncode == 0


def check_claude_mem_isolation(home=HOME, default_logged_in=_default_profile_logged_in):
    """Status-only: an org's ~/.claude-mem-<org>/settings.json must not still
    point at the default profile's data dir/port, or its worker silently
    shares data and billing with the default profile instead of isolating
    (confirmed live 2026-08-28 -- see SKILL.md step 7's claude-mem block).
    Not a sync target itself (claude-mem, not this repo, owns these files),
    just a tripwire so the leak is visible in --status instead of silent.
    `home`/`default_logged_in` are injectable so --selftest can drive it."""
    default_settings = home / ".claude-mem" / "settings.json"
    if not default_settings.exists():
        return
    default = json.loads(default_settings.read_text())
    shared_keys = ["CLAUDE_MEM_DATA_DIR", "CLAUDE_MEM_WORKER_PORT",
                   "CLAUDE_MEM_SERVER_URL", "CLAUDE_MEM_SERVER_BETA_URL"]
    org_dirs = [d for d in sorted(home.glob(".claude-mem-*"))
                if (d / "settings.json").exists()]
    # A credential in <data-dir>/.env makes claude-mem's pre-flight return
    # before its Keychain lookup, so that profile is immune to the default
    # login below. Same regex the pid-guard hook uses.
    cred_re = CLAUDE_MEM_CRED_RE
    unprotected = []
    for org_dir in org_dirs:
        org = json.loads((org_dir / "settings.json").read_text())
        clashes = [k for k in shared_keys if org.get(k) == default.get(k)]
        worker, server = claude_mem_ports(org_dir / "settings.json")
        if clashes:
            print(f"[LEAK RISK]    {org_dir.name}/settings.json shares "
                  f"{', '.join(clashes)} with the default profile -- fix "
                  f"per SKILL.md step 7's claude-mem isolation block")
        else:
            print(f"[isolated]     {org_dir.name}/settings.json "
                  f"(worker port {worker}, server port {server})")
        env_file = org_dir / ".env"
        if env_file.exists() and cred_re.search(env_file.read_text()):
            print(f"[isolated]     {org_dir.name}/.env carries its own credential "
                  f"(claude-mem's Keychain pre-flight bypassed)")
        else:
            unprotected.append(org_dir.name)
    # Ports and data dirs don't cover the auth side: claude-mem's OAuth
    # pre-flight reads the DEFAULT profile's unsuffixed Keychain entry no
    # matter which CLAUDE_CONFIG_DIR spawned it, and injects that token into
    # its SDK calls (mechanism documented in claude-mem-pid-guard.sh). So a
    # logged-in default profile is a leak for every org profile that has no
    # .env credential of its own.
    if unprotected:
        if default_logged_in():
            print(f"[LEAK RISK]    default profile (~/.claude) is logged in and "
                  f"{', '.join(unprotected)} have no .env credential -- their "
                  f"workers will inject its token; give them one, or run: "
                  f"CLAUDE_CONFIG_DIR=~/.claude claude auth logout")
        else:
            print("[isolated]     default profile logged out (nothing for "
                  "claude-mem's OAuth pre-flight to hijack)")


CLAUDE_MEM_CRED_RE = re.compile(
    r"^(ANTHROPIC_API_KEY|ANTHROPIC_AUTH_TOKEN|ANTHROPIC_BASE_URL)=.+", re.MULTILINE)

# claude-mem derives its default ports from the OS uid, not from the data
# dir -- so every profile on one machine computes the same pair, which is
# the root of the collision --new-profile exists to prevent. Same formulas
# as worker-service.cjs; the pid-guard hook repeats the worker one in shell.
_UID = os.getuid() if hasattr(os, "getuid") else 77
CLAUDE_MEM_DEFAULT_WORKER_PORT = 37700 + _UID % 100
CLAUDE_MEM_DEFAULT_SERVER_PORT = 37877 + _UID % 100
# An org's server-mode port is its worker port plus this, so one number per
# profile is enough to know both. The registry of who has which port is the
# set of ~/.claude-mem*/settings.json files -- there is no separate list.
CLAUDE_MEM_SERVER_PORT_OFFSET = 200


def _port_bindable(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def claude_mem_ports(settings_path):
    """(worker, server) port strings a profile's claude-mem settings claim;
    missing keys fall back to claude-mem's own uid-derived defaults."""
    d = json.loads(settings_path.read_text())
    worker = d.get("CLAUDE_MEM_WORKER_PORT") or str(CLAUDE_MEM_DEFAULT_WORKER_PORT)
    server = (d.get("CLAUDE_MEM_SERVER_URL") or f":{CLAUDE_MEM_DEFAULT_SERVER_PORT}").rsplit(":", 1)[-1]
    return worker, server


def allocate_claude_mem_ports(used_worker, used_server, bindable=_port_bindable):
    """Lowest worker port above the default that no profile claims and
    nothing on this machine currently binds, with its server port checked
    the same way. Sequential, so it scales to as many orgs as there are
    ports; `--status` lists the result per profile."""
    port = CLAUDE_MEM_DEFAULT_WORKER_PORT + 1
    while port + CLAUDE_MEM_SERVER_PORT_OFFSET < 65535:
        worker, server = str(port), str(port + CLAUDE_MEM_SERVER_PORT_OFFSET)
        if worker not in used_worker and server not in used_server \
                and worker not in used_server and server not in used_worker \
                and bindable(port) and bindable(port + CLAUDE_MEM_SERVER_PORT_OFFSET):
            return worker, server
        port += 1
    raise SystemExit("no free claude-mem port pair left")


def isolated_claude_mem_settings(base, mem_dir, worker_port, server_port):
    """The default profile's claude-mem settings re-pointed at an org's own
    data dir and ports. These six keys are every place claude-mem would
    otherwise land on the same file or socket as another profile."""
    out = dict(base)
    out.update({
        "CLAUDE_MEM_DATA_DIR": str(mem_dir),
        "CLAUDE_MEM_WORKER_PORT": worker_port,
        "CLAUDE_MEM_QUEUE_REDIS_PREFIX": f"claude_mem_{worker_port}",
        "CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH": str(mem_dir / "transcript-watch.json"),
        "CLAUDE_MEM_SERVER_URL": f"http://127.0.0.1:{server_port}",
        "CLAUDE_MEM_SERVER_BETA_URL": f"http://127.0.0.1:{server_port}",
    })
    return out


def _claude(config_dir, *args, capture=False):
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config_dir))
    try:
        return subprocess.run(["claude", *args], env=env, text=True,
                              capture_output=capture)
    except FileNotFoundError:  # no claude binary (CI, or restore step 1 skipped)
        return subprocess.CompletedProcess(["claude", *args], 127, "", "claude: not found")


def used_claude_mem_ports(home, exclude=None):
    """(worker ports, server ports) every claude-mem profile under `home`
    claims, except `exclude` -- the registry --new-profile allocates against."""
    used_w, used_s = set(), set()
    for other in home.glob(".claude-mem*/settings.json"):
        if other.parent != exclude:
            w, s = claude_mem_ports(other)
            used_w.add(w)
            used_s.add(s)
    return used_w, used_s


def new_profile(org, dry_run=False, home=HOME):
    """Interactive, idempotent: everything SKILL.md step 7 used to ask a
    human to type, in order, each step skipped when its end state already
    holds. The one step that needs a browser round-trip (the setup-token
    for claude-mem's .env) is shouted, because skipping it is the leak."""
    org = org.lower()
    work = home / "Work"
    matches = [p for p in work.iterdir() if p.is_dir() and p.name.lower() == org] \
        if work.is_dir() else []
    if not matches:
        raise SystemExit(f"no ~/Work/<dir> matching '{org}' -- .zshrc's chpwd hook "
                         f"derives the profile from that directory name, so it must "
                         f"exist first")
    config_dir = home / f".claude-{org}"
    mem_dir = home / f".claude-mem-{org}"
    env_file = mem_dir / ".env"
    print(f"== config-sync --new-profile {org}{' (dry run)' if dry_run else ''} ==")
    print(f"   work dir   {matches[0]}\n   profile    {config_dir}\n   claude-mem {mem_dir}")

    def step(label, done, action):
        if done():
            print(f"  [done]  {label}")
        elif dry_run:
            print(f"  [todo]  {label}")
        else:
            print(f"  [....]  {label}")
            action()
            print(f"  [{'done' if done() else 'FAIL'}]  {label}")

    step("profile directory", config_dir.is_dir,
         lambda: config_dir.mkdir(mode=0o700))

    def logged_in():
        if not config_dir.is_dir():
            return False
        r = _claude(config_dir, "auth", "status", capture=True)
        return r.returncode == 0 and '"loggedIn": true' in r.stdout
    step("logged in under this profile (browser OAuth, full account)", logged_in,
         lambda: _claude(config_dir, "auth", "login"))

    step("shared config linked/merged into the profile (the per-profile part of --push)",
         lambda: (config_dir / "hooks").is_symlink() and (config_dir / "settings.json").exists(),
         lambda: sync_profile(config_dir, "push"))

    def plugins_installed():
        r = _claude(config_dir, "plugin", "list", capture=True)
        return r.returncode == 0 and "claude-mem@thedotmack" in r.stdout and "ponytail@ponytail" in r.stdout

    def install_plugins():
        for args in (("marketplace", "add", "thedotmack/claude-mem"),
                     ("marketplace", "add", "DietrichGebert/ponytail"),
                     ("install", "claude-mem@thedotmack"),
                     ("install", "ponytail@ponytail")):
            _claude(config_dir, "plugin", *args)  # re-adding a marketplace is a no-op error
    step("claude-mem + ponytail plugins installed in this profile", plugins_installed, install_plugins)

    settings = mem_dir / "settings.json"
    changed = []  # steps that wrote something the running worker can't see

    def mem_isolated():
        if not settings.exists():
            return False
        d = json.loads(settings.read_text())
        return d.get("CLAUDE_MEM_DATA_DIR") == str(mem_dir) and \
            d.get("CLAUDE_MEM_WORKER_PORT") not in (None, str(CLAUDE_MEM_DEFAULT_WORKER_PORT))

    def isolate_mem():
        worker, server = allocate_claude_mem_ports(*used_claude_mem_ports(home, exclude=mem_dir))
        default = home / ".claude-mem" / "settings.json"
        base = json.loads(default.read_text()) if default.exists() else {}
        mem_dir.mkdir(mode=0o700, exist_ok=True)
        settings.write_text(json.dumps(
            isolated_claude_mem_settings(base, mem_dir, worker, server), indent=2) + "\n")
        changed.append("settings")
        print(f"          worker port {worker}, server port {server}")
    step("claude-mem data dir isolated on its own ports", mem_isolated, isolate_mem)

    def has_cred():
        return env_file.exists() and bool(CLAUDE_MEM_CRED_RE.search(env_file.read_text()))

    def write_cred():
        print("\n  ******************************************************************")
        print("  *  claude-mem's OAuth pre-flight reads the DEFAULT profile's login  *")
        print("  *  unless this file carries a credential. Running                    *")
        print(f"  *    CLAUDE_CONFIG_DIR={config_dir} claude setup-token")
        print("  *  now -- finish the browser flow, copy the token it prints, paste  *")
        print("  *  it below (input hidden). Ctrl-C leaves the profile unprotected   *")
        print("  *  and --status will keep saying so.                                 *")
        print("  ******************************************************************\n")
        _claude(config_dir, "setup-token")
        token = getpass.getpass("  paste the token: ").strip()
        if not token:
            print("  no token given -- skipping; re-run --new-profile to finish")
            return
        mem_dir.mkdir(mode=0o700, exist_ok=True)
        env_file.write_text(
            "# Read by claude-mem before every SDK spawn. A credential here makes it\n"
            "# skip the Keychain lookup that would otherwise pick up the DEFAULT\n"
            "# profile's login (see config-sync SKILL.md step 7). Written by\n"
            "# sync.py --new-profile; regenerate with `claude setup-token` when the\n"
            "# pid-guard hook reports AUTH FAILING (tokens last about a year).\n"
            f"ANTHROPIC_AUTH_TOKEN={token}\n")
        env_file.chmod(0o600)
        changed.append(".env")
    step("claude-mem .env credential (keeps billing on THIS profile's account)", has_cred, write_cred)

    def worker_pids():
        if not settings.exists():
            return []
        port = json.loads(settings.read_text()).get("CLAUDE_MEM_WORKER_PORT")
        r = subprocess.run(["lsof", f"-tiTCP:{port}", "-sTCP:LISTEN"], capture_output=True, text=True)
        return [int(p) for p in r.stdout.split()]
    # A worker that booted before settings/.env changed keeps the old values
    # until it dies; a worker that booted after them is fine where it is.
    step("running worker has seen the current settings and credential",
         lambda: not changed or not worker_pids(),
         lambda: [os.kill(p, 15) for p in worker_pids()])

    print("\n  next: open a NEW shell, cd into the work dir, start Claude Code once, then")
    print("        curl -s localhost:$(python3 -c 'import json;print(json.load(open(\"" + str(settings) + "\"))[\"CLAUDE_MEM_WORKER_PORT\"])')/api/health")
    print("        must report authMethod 'Gateway auth token' (not 'Claude Code OAuth token').")
    print("        Optional MCP (linear/lucid/tally) is per profile too -- see SKILL.md step 9.\n")
    check_claude_mem_isolation(home)


def sync_profile(profile_dir, mode):
    """The per-Claude-profile slice of a sync: shared symlinks plus the
    settings merge, for one ~/.claude[-<org>] directory."""
    print(f"-- profile {profile_dir} --")
    for src, rel in CLAUDE_PROFILE_SYMLINKS:
        sync_symlink(src, profile_dir / rel, mode)
    for src, rel in CLAUDE_PROFILE_MERGES:
        sync_merge(src, profile_dir / rel, mode)


def run(mode):
    print(f"== config-sync --{mode} ==")
    for src, dst in SYMLINKS:
        sync_symlink(src, dst, mode)
    for profile_dir in claude_profile_dirs():
        sync_profile(profile_dir, mode)
    for src, dst in COPIES:
        sync_copy(src, dst, mode)
    sync_iterm2(mode)
    sync_iterm2_app_prefs(mode)
    for src, dst, drop_keys in TRIMMED_COPIES:
        sync_trimmed(src, dst, drop_keys, mode)
    if mode == "status":
        check_claude_mem_isolation()


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        _selftest()
        return
    if "--new-profile" in args:
        i = args.index("--new-profile")
        if i + 1 >= len(args) or args[i + 1].startswith("--"):
            raise SystemExit("usage: sync.py --new-profile <org> [--dry-run]")
        new_profile(args[i + 1], dry_run="--dry-run" in args)
        return
    mode = "status"
    for flag, name in (("--restore", "restore"), ("--push", "push"), ("--pull", "pull")):
        if flag in args:
            mode = name
    run(mode)


if __name__ == "__main__":
    main()
