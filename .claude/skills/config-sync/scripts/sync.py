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

Stdlib only. Safe to re-run any mode; that repeatability is the test.
"""
import json
import os
import plistlib
import shutil
import sys
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
    (".claude/user/CLAUDE.md", "~/.claude/CLAUDE.md"),
    (".claude/user/RTK.md", "~/.claude/RTK.md"),
    (".claude/user/hooks", "~/.claude/hooks"),
    (".claude/skills", "~/.claude/skills"),
]

# Files the owning app rewrites, so a plain copy in the direction it's used.
COPIES = [
    ("apps/cursor/settings.json",
     "~/Library/Application Support/Cursor/User/settings.json"),
    ("apps/cursor/mcp.json", "~/.cursor/mcp.json"),
    ("apps/sublime/Preferences.sublime-settings",
     "~/Library/Application Support/Sublime Text/Packages/User/"
     "Preferences.sublime-settings"),
    ("apps/docker/daemon.json", "~/.docker/daemon.json"),
    ("apps/iterm2/Driftware.json",
     "~/Library/Application Support/iTerm2/DynamicProfiles/Driftware.json"),
]

# Same as COPIES, but the live file carries fields that must never reach
# the repo (auth identity, caches). Pull drops them; push writes as-is.
TRIMMED_COPIES = [
    ("apps/cursor/cli-config.json", "~/.cursor/cli-config.json",
     {"authInfo", "privacyCache", "autoReviewAvailabilityCache",
      "serverConfigCache", "network"}),
]

# Accumulate live-only state (permission grants, plugin toggles picked up
# by the harness) -- deep-merged, never overwritten outright.
MERGES = [
    (".claude/user/settings.json", "~/.claude/settings.json"),
]

ITERM2_PLIST = Path("~/Library/Preferences/com.googlecode.iterm2.plist").expanduser()
ITERM2_PROFILE_GUID = "D3F7A1B2-3C4D-4E5F-8A9B-0C1D2E3F4A5B"


def deep_merge(dest, src):
    """Recursively merge src into dest; src wins on conflicts, dest-only
    keys survive. Neither input is mutated."""
    result = dict(dest)
    for key, value in src.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
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
    base = {"a": 1, "b": {"c": 2, "d": 3}}
    override = {"b": {"c": 99}, "e": 5}
    merged = deep_merge(base, override)
    assert merged == {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}, merged
    assert base == {"a": 1, "b": {"c": 2, "d": 3}}, "deep_merge mutated dest"
    assert override == {"b": {"c": 99}, "e": 5}, "deep_merge mutated src"
    assert diff_paths({"a": 1}, {"a": 1}) == []
    assert diff_paths({"a": 1}, {"a": 2}) == ["a: differs"]
    print("selftest ok")


def repo_path(rel):
    return REPO_ROOT / rel


def home_path(rel):
    return Path(os.path.expanduser(rel))


def ensure_parent(path):
    path.parent.mkdir(parents=True, exist_ok=True)


def backup_if_real_file(path):
    if path.exists() and not path.is_symlink():
        backup = path.with_name(path.name + ".pre-config-sync.bak")
        print(f"  backing up existing {path} -> {backup}")
        shutil.move(str(path), str(backup))


def sync_symlink(src_rel, dst_rel, mode):
    src = repo_path(src_rel)
    dst = home_path(dst_rel)
    if mode == "status":
        if dst.is_symlink() and dst.resolve() == src.resolve():
            print(f"[symlink ok]   {dst_rel}")
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
        ensure_parent(dst)
        shutil.copy2(src, dst)
        print(f"  wrote {dst_rel}")
    elif mode == "pull":
        if not dst.exists():
            print(f"  skip {src_rel}: nothing live to pull")
            return
        live = json.loads(dst.read_text())
        for k in drop_keys:
            live.pop(k, None)
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
    dst_rel = "apps/iterm2/Driftware.json"
    if mode == "status":
        if ITERM2_PLIST.exists():
            print(f"[source found] {dst_rel} (re-export with --pull to refresh)")
        else:
            print(f"[no iterm2]    {dst_rel} (plist not found on this machine)")
        return
    if mode == "pull":
        if not ITERM2_PLIST.exists():
            print("  skip iterm2: no local iTerm2 preferences to export from")
            return
        d = plistlib.load(open(ITERM2_PLIST, "rb"))
        profiles = d.get("New Bookmarks", [])
        if not profiles:
            print("  skip iterm2: no profiles in the local plist")
            return
        profile = dict(profiles[0])
        profile["Guid"] = ITERM2_PROFILE_GUID
        if profile.get("Working Directory", "").startswith(str(HOME)):
            profile["Working Directory"] = "$HOME"
        out_path = repo_path(dst_rel)
        out_path.write_text(json.dumps({"Profiles": [profile]}, indent=2, default=str))
        print(f"  pulled iTerm2 profile '{profile.get('Name')}' -> {dst_rel}")
    elif mode in ("restore", "push"):
        sync_copy(dst_rel,
                  "~/Library/Application Support/iTerm2/DynamicProfiles/Driftware.json",
                  mode)


def run(mode):
    print(f"== config-sync --{mode} ==")
    for src, dst in SYMLINKS:
        sync_symlink(src, dst, mode)
    for src, dst in COPIES:
        if src == "apps/iterm2/Driftware.json":
            continue  # handled by sync_iterm2, which also re-exports on pull
        sync_copy(src, dst, mode)
    sync_iterm2(mode)
    for src, dst, drop_keys in TRIMMED_COPIES:
        sync_trimmed(src, dst, drop_keys, mode)
    for src, dst in MERGES:
        sync_merge(src, dst, mode)


def main():
    args = sys.argv[1:]
    if "--selftest" in args:
        _selftest()
        return
    mode = "status"
    for flag, name in (("--restore", "restore"), ("--push", "push"), ("--pull", "pull")):
        if flag in args:
            mode = name
    run(mode)


if __name__ == "__main__":
    main()
