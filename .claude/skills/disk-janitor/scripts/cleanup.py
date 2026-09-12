"""
Mac disk cleanup utility. Dry-run by default; delegates to each tool's own CLI
for package-manager caches. Run with --help for full usage.

Usage:
    python3 cleanup.py                        # dry-run, level 1
    python3 cleanup.py --level 2              # dry-run levels 1+2
    python3 cleanup.py --apply                # execute level 1
    python3 cleanup.py --level 2 --apply      # execute levels 1+2
    python3 cleanup.py --apply --only brew,uv
    python3 cleanup.py --level 3 --apply --include-dangerous
    python3 cleanup.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()
_TMP_DIR = Path("/private/tmp") if Path("/private/tmp").exists() else Path("/tmp")
_CLAUDE_TMP = _TMP_DIR / f"claude-{os.getuid()}"

# Claude Code may be running this very script; only tmp entries older than this
# are touched so the live session's buffers survive.
_CLAUDE_TMP_MAX_AGE_S = 24 * 3600

# Scan depth under each work dir when hunting node_modules.
_NM_MAX_DEPTH = 4

KNOWN_TARGETS = {
    "brew", "uv", "pip", "npm", "bun", "trash", "claude-tmp",
    "chrome", "jetbrains", "logs", "claude-cache", "claude-chats", "docker",
    "node_modules", "xcode", "docker-volumes",
    "plugin-node-modules", "plugin-marketplace-git", "plugin-marketplace-binaries",
    "plugin-old-versions", "teams", "claude-desktop", "discord", "claude-memory",
    "venv", "uv-python-orphans",
}

# Directory names that are unambiguously Electron/Chromium cache, never
# profile data (bookmarks, cookies, extensions, login state live elsewhere
# in the same tree). Shared by every "app support cache, not whole app"
# target (teams, claude-desktop, discord, chrome's Application Support half).
_ELECTRON_CACHE_DIRNAMES = {
    "Cache", "Code Cache", "GPUCache", "blob_storage", "CacheStorage",
    "component_crx_cache", "DawnGraphiteCache", "DawnWebGPUCache",
}

# Common project directory names to probe when --work-dir is not specified.
_WORK_DIR_CANDIDATES = ["Work", "Projects", "projects", "dev", "code", "src", "repos"]

# File extensions treated as large binaries when scanning marketplace clones.
# Deliberately short and explicit rather than a generic "big file" heuristic,
# so we never delete something a marketplace actually needs to run.
_MARKETPLACE_BINARY_EXTS = {".pdf", ".zip", ".dmg", ".mp4", ".mov"}
_MARKETPLACE_BINARY_MIN_SIZE = 1024 * 1024  # skip small icon/asset files


def _detect_work_dirs() -> list[Path]:
    found = [HOME / name for name in _WORK_DIR_CANDIDATES if (HOME / name).is_dir()]
    return found or [HOME]


def _detect_claude_profiles() -> list[Path]:
    """~/.claude plus any ~/.claude-* CLAUDE_CONFIG_DIR profile that has a plugins/ dir.

    Profiles aren't centrally registered anywhere (config-sync deliberately
    doesn't sync plugins/ across them), so this globs for them at runtime
    instead of hardcoding a list that would go stale.
    """
    candidates = [HOME / ".claude"] + sorted(HOME.glob(".claude-*"))
    return [p for p in candidates if (p / "plugins").is_dir()]


# Paths outside this allowlist are never deleted, even if a target resolves there.
# Work dirs are added dynamically once args are parsed (see _build_allowlist).
_ALLOWLIST_BASE = [
    _CLAUDE_TMP,
    HOME / "Library" / "Caches",
    HOME / ".cache",
    HOME / ".npm",
    HOME / ".bun" / "install" / "cache",
    HOME / ".Trash",
    HOME / ".claude" / "projects",
    HOME / ".claude" / "shell-snapshots",
    HOME / ".claude" / "paste-cache",
    HOME / ".claude" / "cache",
    HOME / "Library" / "Logs",
    HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
    HOME / "Library" / "Developer" / "CoreSimulator" / "Devices",
    HOME / "Library" / "Containers" / "com.microsoft.teams2",
    HOME / "Library" / "Group Containers" / "UBF8T346G9.com.microsoft.teams",
    HOME / "Library" / "Application Support" / "Claude",
    HOME / "Library" / "Application Support" / "discord",
    HOME / "Library" / "Application Support" / "Google" / "Chrome",
]

ALLOWLIST: list[Path] = []


def _build_allowlist(work_dirs: list[Path], profiles: list = None) -> None:
    # Work dirs are deliberately never added here: they hold live project
    # data, and _in_allowlist is a blanket "anything under this path is
    # deletable" check. Stale node_modules/venv dirs under a work dir are
    # gated by _stale_dir_allowed instead, which requires both the dirname
    # and a work-dir ancestor -- nothing else under a work dir is ever
    # deletable by _delete_dir/_apply_dirs.
    ALLOWLIST.clear()
    ALLOWLIST.extend(_ALLOWLIST_BASE)
    for profile in profiles or []:
        ALLOWLIST.append(profile / "plugins" / "cache")
        ALLOWLIST.append(profile / "plugins" / "marketplaces")
        ALLOWLIST.append(profile / "projects")
        ALLOWLIST.append(profile / "shell-snapshots")
        ALLOWLIST.append(profile / "paste-cache")
        ALLOWLIST.append(profile / "cache")


def _in_allowlist(path: Path) -> bool:
    resolved = path.resolve()
    return any(
        resolved == allowed.resolve() or resolved.is_relative_to(allowed.resolve())
        for allowed in ALLOWLIST
    )


_STALE_DIR_NAMES = {"node_modules", ".venv", "venv"}


def _stale_dir_allowed(path: Path, work_dirs: list[Path]) -> bool:
    """Delete guard for stale node_modules/venv dirs, independent of the
    general ALLOWLIST: the path's own name must be one of the known
    stale-dir names AND it must sit under one of the work dirs. Work dirs
    are never added to ALLOWLIST itself (see _build_allowlist), so this is
    the only way anything under a work dir is ever deletable.
    """
    if path.name not in _STALE_DIR_NAMES:
        return False
    resolved = path.resolve()
    return any(w.exists() and resolved.is_relative_to(w.resolve()) for w in work_dirs)


def _measure_or_none(path: Path) -> int | None:
    """Directory size in bytes; 0 if missing; None if `du` fails on an
    existing path (e.g. macOS TCC blocking Terminal from reading
    ~/.Trash). None is distinct from 0 so a report row can show
    'reclaimable: null' with a permission note instead of silently
    reading as "nothing to clean". See _du for the apply-time helper
    that collapses a failure to 0.
    """
    if not path.exists():
        return 0
    result = subprocess.run(
        ["du", "-sk", str(path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.split()[0]) * 1024
    except (IndexError, ValueError):
        return None


def _du(path: Path) -> int:
    """Directory size in bytes, 0 if missing or unreadable.

    0-on-failure is fine here: this is the internal apply-time helper used
    for sizing a delete that's already been decided, where a read failure
    just means nothing gets counted as freed.
    """
    measured = _measure_or_none(path)
    return 0 if measured is None else measured


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    """Run a subprocess command."""
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _has(binary: str) -> bool:
    if shutil.which(binary) is None:
        return False
    # Shims (e.g. pyenv) may exist on PATH but fail at runtime; verify executable.
    result = subprocess.run([binary, "--version"], capture_output=True)
    return result.returncode == 0


def _running(name: str) -> bool:
    """Whether a process named exactly `name` is running, via pgrep -x.

    Used to skip pulling a live app's cache out from under it: a running
    Electron app can have open file handles into a "cache" dir, and
    deleting it mid-session can leave service-worker/IndexedDB state
    pointing at nothing. pgrep is absent on some minimal systems; treat
    that as "not running" rather than failing the whole target.
    """
    if shutil.which("pgrep") is None:
        return False
    result = subprocess.run(["pgrep", "-x", name], capture_output=True)
    return result.returncode == 0


def _electron_app_running(process_name: str, user_data_dir: Path) -> bool:
    """Whether an Electron/Chromium app looks live: its process by exact
    name, OR its SingletonLock file in the app's user-data root.

    pgrep -x alone misses a lingering helper process after the main one
    exits and is brittle to any rename; SingletonLock is the mechanism
    Electron/Chromium itself uses to detect another live instance of the
    same profile, so it's a stronger, per-profile signal pgrep can't give.
    Either signal is enough to call it running -- this only ever widens
    when a cache delete gets skipped, never narrows it.
    """
    if _running(process_name):
        return True
    lock = user_data_dir / "SingletonLock"
    return lock.exists() or lock.is_symlink()


def _fmt(b) -> str:
    if b is None:
        return "?"
    for unit in ("B", "K", "M", "G"):
        if b < 1024:
            return f"{b:.1f}{unit}"
        b /= 1024
    return f"{b:.1f}T"


def _confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False


def _delete_dir(path: Path, dry_run: bool) -> int:
    if not path.exists():
        return 0
    if not _in_allowlist(path):
        print(f"  [SKIP] {path} not in allowlist", file=sys.stderr)
        return 0
    size = _du(path)
    if not dry_run:
        shutil.rmtree(path, ignore_errors=True)
    return size


def _empty_dir(path: Path, dry_run: bool) -> int:
    """Delete every entry inside `path`, keeping `path` itself. Used where
    the directory has meaning beyond its contents (~/.Trash's permissions
    and Finder integration), so recreating it via rmtree-then-nothing is
    the wrong move, unlike _delete_dir which removes the whole tree.
    """
    if not path.exists():
        return 0
    if not _in_allowlist(path):
        print(f"  [SKIP] {path} not in allowlist", file=sys.stderr)
        return 0
    total = 0
    try:
        entries = list(path.iterdir())
    except OSError:
        return 0
    for entry in entries:
        try:
            size = _du(entry) if entry.is_dir() else entry.stat().st_size
        except OSError:
            continue
        total += size
        if not dry_run:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
    return total


def _find_electron_cache_dirs(root: Path) -> list[Path]:
    """Find literal cache-named subdirs under an Electron/Chromium app tree.

    Never returns the root itself or profile-data siblings (bookmarks,
    cookies, login state) -- only dirs whose name is unambiguously cache
    (see _ELECTRON_CACHE_DIRNAMES). Matched dirs aren't descended into: the
    whole matched dir is one deletion unit, so nothing nested under it needs
    a separate entry.
    """
    if not root.exists():
        return []
    results = []
    for r, dirs, _files in os.walk(root):
        matched = [d for d in dirs if d in _ELECTRON_CACHE_DIRNAMES]
        results.extend(Path(r) / d for d in matched)
        dirs[:] = [d for d in dirs if d not in _ELECTRON_CACHE_DIRNAMES]
    return results


def _electron_cache_report(roots: list[Path], process_name: str, dry_run: bool):
    """Shared measure/apply for Electron cache-named subdirs across `roots`,
    gated on the app not currently running when applying (process name OR
    its SingletonLock, see _electron_app_running): a live app can have open
    handles into a "cache" dir, and deleting it mid-session can leave
    service-worker/IndexedDB state pointing at nothing (dry-run still
    measures regardless of whether the app is running). `roots[0]` is used
    as the app's user-data root for the lock-file check.

    Returns (size, freed, running, detail_paths).
    """
    electron_dirs = [d for r in roots for d in _find_electron_cache_dirs(r)]
    size = sum(_du(d) for d in electron_dirs)
    running = _electron_app_running(process_name, roots[0])
    freed = 0
    if not dry_run and not running:
        freed = sum(_delete_dir(d, dry_run=False) for d in electron_dirs)
    return size, freed, running, [str(d) for d in electron_dirs]


def _delete_old_files(path: Path, days: int, dry_run: bool) -> int:
    if not path.exists():
        return 0
    if not _in_allowlist(path):
        return 0
    cutoff = time.time() - days * 86400
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and p.stat().st_mtime < cutoff:
                total += p.stat().st_size
                if not dry_run:
                    p.unlink(missing_ok=True)
        except OSError:
            continue
    return total


# ---------------------------------------------------------------------------
# Target implementations
# ---------------------------------------------------------------------------

def _measure_brew(level: int = 1) -> int:
    """Mirrors _apply_brew's own --prune=all gate at level >= 3: measuring
    without it undercounts what apply will actually remove (verified on
    this machine: 150.6MB without --prune=all, 1.3GB with it), the same
    dry-run-versus-apply mismatch already fixed elsewhere in this target
    catalog for other targets.
    """
    if not _has("brew"):
        return 0
    args = ["brew", "cleanup", "-n", "-s"]
    if level >= 3:
        args.append("--prune=all")
    result = _run(args)
    total = 0
    for line in result.stdout.splitlines():
        if line.startswith("Would remove:"):
            # Brew appends a size suffix like " (1.2MB)" to each path.
            raw = re.sub(r"\s*\([^)]*\)\s*$", "", line.split(":", 1)[1].strip())
            p = Path(raw)
            if p.exists():
                total += p.stat().st_size if p.is_file() else _du(p)
    return total


def _apply_brew(level: int) -> int:
    if not _has("brew"):
        return 0
    before = _du(HOME / "Library" / "Caches" / "Homebrew")
    args = ["brew", "cleanup", "-s"]
    if level >= 3:
        args.append("--prune=all")
    _run(args)
    after = _du(HOME / "Library" / "Caches" / "Homebrew")
    return max(0, before - after)


def _cli_cache_target(name: str, path: Path, cli: list[str]) -> dict:
    return {"name": name, "path": path, "cli": cli}


def _apply_cli(cli: list[str], path: Path) -> int:
    binary = cli[0]
    if not _has(binary):
        return 0
    before = _du(path)
    # Run from HOME so CLIs that require a project context (e.g. bun) don't fail.
    subprocess.run(cli, capture_output=True, text=True, cwd=str(HOME))
    after = _du(path)
    return max(0, before - after)


def _parse_docker_size(value: str) -> int:
    """Parse a docker size string like '1.185GB (100%)' into bytes."""
    value = re.sub(r"\s*\([^)]*\)\s*$", "", value.strip()).rstrip("B")
    try:
        if value.endswith("G"):
            return int(float(value[:-1]) * 1024 ** 3)
        if value.endswith("M"):
            return int(float(value[:-1]) * 1024 ** 2)
        if value.endswith("K"):
            return int(float(value[:-1]) * 1024)
        if value.isdigit():
            return int(value)
    except ValueError:
        pass
    return 0


def _measure_docker(include_containers: bool = False, all_images: bool = False) -> int:
    """Measure reclaimable docker space for exactly what the matching apply
    call will prune.

    Level 2 (include_containers=False, all_images=False): dangling images
    and build cache only, what 'docker image prune -f' + 'docker builder
    prune -f' actually free. Stopped containers are excluded even though
    'docker system df' reports them as reclaimable: level 2 no longer
    prunes containers, since a stopped dev database without a named volume
    is real data, not cache.
    Level 3 turns on include_containers (adds 'container prune -f',
    confirm-gated) and/or all_images (adds tagged unused images).

    Returns None (not 0) when the daemon isn't reachable, so a report row
    can show reclaimable: null instead of reading as "nothing to reclaim"
    when the real answer is "never actually measured" -- verified on this
    machine, where the daemon being stopped silently reported 0 despite
    15+ GiB of unused images once it was started.
    """
    if not _has("docker"):
        return 0  # no docker at all is a real 0, unlike a stopped daemon
    info = _run(["docker", "info"])
    if info.returncode != 0:
        return None
    result = _run(["docker", "system", "df", "--format", "{{.Type}}\t{{.Reclaimable}}"])
    if result.returncode != 0:
        return None
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        dtype, reclaimable = parts[0].strip(), parts[1].strip()
        if dtype == "Local Volumes":
            continue  # never freed without --volumes
        if dtype == "Containers":
            if include_containers:
                total += _parse_docker_size(reclaimable)
            continue
        if dtype == "Images":
            if all_images:
                total += _parse_docker_size(reclaimable)
            else:
                # image prune -f skips tagged images; count only dangling ones
                dangling = _run(["docker", "images", "-q", "-f", "dangling=true"])
                for img_id in dangling.stdout.split():
                    inspect = _run(["docker", "inspect", "--format", "{{.Size}}", img_id])
                    try:
                        total += int(inspect.stdout.strip())
                    except ValueError:
                        pass
            continue
        total += _parse_docker_size(reclaimable)  # Build Cache, etc.
    return total


def _apply_docker(include_containers: bool, all_images: bool, include_dangerous: bool, yes: bool) -> int:
    if not _has("docker"):
        return 0
    result = _run(["docker", "info"])
    if result.returncode != 0:
        print("  [SKIP] Docker daemon not running")
        return 0
    before = _measure_docker(include_containers=include_containers or include_dangerous,
                              all_images=all_images or include_dangerous)
    if include_dangerous:
        if not yes and not _confirm("  docker system prune -a --volumes: destroys ALL unused images and volumes. Continue?"):
            return 0
        _run(["docker", "system", "prune", "-a", "--volumes", "-f"])
    else:
        if include_containers:
            if not yes and not _confirm("  docker container prune -f: removes ALL stopped containers. Continue?"):
                return 0
            _run(["docker", "container", "prune", "-f"])
        if all_images:
            if not yes and not _confirm("  docker image prune -a -f: removes ALL unused images (not just dangling). Continue?"):
                return 0
            _run(["docker", "image", "prune", "-a", "-f"])
        else:
            _run(["docker", "image", "prune", "-f"])
        _run(["docker", "builder", "prune", "-f"])
    after = _measure_docker(include_containers=include_containers or include_dangerous,
                             all_images=all_images or include_dangerous)
    return max(0, before - after)


def _walk_work_dirs(work_dirs: list[Path]):
    """Yield (root_path, dirs) under every work dir, depth-capped at
    _NM_MAX_DEPTH and with hidden dirs pruned after each step.

    `dirs` is the live list os.walk uses to decide what to descend into --
    a caller may remove entries from it (to stop descending into a matched
    dir) exactly as with a plain os.walk loop; hidden-dir pruning is applied
    on top of whatever the caller left once it resumes. Shared by every
    scan that needs the same depth cap: stale node_modules/venvs, the
    "still referenced" venv cfg scan for uv-python-orphans.
    """
    for work in work_dirs:
        if not work.exists():
            continue
        base_depth = len(work.resolve().parts)
        for root, dirs, _files in os.walk(work):
            root_path = Path(root)
            depth = len(root_path.resolve().parts) - base_depth
            if depth >= _NM_MAX_DEPTH:
                dirs.clear()
                continue
            yield root_path, dirs
            dirs[:] = [d for d in dirs if not d.startswith(".")]


def _project_touched_since(root_path: Path, exclude_name: str, cutoff: float) -> bool:
    """Whether anything under root_path (other than exclude_name) has an
    mtime newer than cutoff, checked at any depth with an early break the
    moment a qualifying file or dir is found.

    A directory's own mtime does not change when a file inside it is
    edited in place, so checking only directory mtimes, or stopping at a
    fixed depth, can miss a project with no commits and a recent edit
    several levels down (verified in a scratch repo: a git commit bumps
    .git's mtime even for a nested-only edit, so that case is covered
    regardless, but a project with no commits has no other signal). Fresh
    projects almost always have something recent near the top and exit in
    a handful of stats; only a genuinely stale project pays the full walk,
    which is exactly where certainty matters.
    """
    try:
        entries = list(root_path.iterdir())
    except OSError:
        return False
    for p in entries:
        if p.name == exclude_name:
            continue
        try:
            if p.stat().st_mtime > cutoff:
                return True
        except OSError:
            continue
        if p.is_dir():
            try:
                walk = p.rglob("*")
            except OSError:
                continue
            for q in walk:
                try:
                    if q.stat().st_mtime > cutoff:
                        return True
                except OSError:
                    continue
    return False


def _find_stale_dirs(
    stale_days: int, work_dirs: list[Path], names: tuple[str, ...], marker: str = None
) -> list[Path]:
    """Find top-level dirs named one of `names` whose project has been
    untouched within the stale window. Shared by node_modules and venv
    staleness checks -- same depth cap, same "project touched recently"
    guard, same never-descend-into-a-match rule (so a nested node_modules,
    or a venv inside a venv, is never returned). `marker`, when given,
    requires that file to exist directly under the matched dir (pyvenv.cfg
    for venvs, so a directory literally named "venv" that isn't one is
    never mistaken for a virtualenv).
    """
    cutoff = time.time() - stale_days * 86400
    results = []
    seen: set[Path] = set()
    for root_path, dirs in _walk_work_dirs(work_dirs):
        matched = [
            d for d in dirs
            if d in names and (marker is None or (root_path / d / marker).is_file())
        ]
        for name in matched:
            dirs.remove(name)
            target = root_path / name
            if target.resolve() in seen:
                continue
            seen.add(target.resolve())
            if not _stale_dir_allowed(target, work_dirs):
                continue
            if target.stat().st_mtime > cutoff:
                continue
            # Guard: skip if the project was touched recently, at any depth.
            if _project_touched_since(root_path, name, cutoff):
                continue
            results.append(target)
    return results


def _find_all_venv_cfgs(work_dirs: list[Path]) -> list[Path]:
    """Every .venv/venv pyvenv.cfg under the work dirs, staleness aside --
    used to build the "still referenced" set for uv-python-orphans, where
    an actively-used venv must count even if it isn't stale.
    """
    results = []
    for root_path, _dirs in _walk_work_dirs(work_dirs):
        for name in (".venv", "venv"):
            cfg = root_path / name / "pyvenv.cfg"
            if cfg.is_file():
                results.append(cfg)
    return results


def _find_referenced_uv_pythons(work_dirs: list[Path]) -> set[Path]:
    """Every interpreter root a project venv's or uv tool venv's pyvenv.cfg
    still points at, as a resolved Path (symlinks followed).

    Resolving matters: uv keeps a minor-version symlink
    (cpython-3.14-... -> cpython-3.14.6-...) alongside the real install dir,
    and a venv's 'home' can point through either one. Comparing resolved
    paths means both spellings count as the same referenced interpreter.
    """
    cfg_paths = _find_all_venv_cfgs(work_dirs)
    tool_dir_result = _run(["uv", "tool", "dir"]) if _has("uv") else None
    if tool_dir_result is not None and tool_dir_result.returncode == 0:
        tool_dir = Path(tool_dir_result.stdout.strip())
        if tool_dir.is_dir():
            cfg_paths.extend(p for p in tool_dir.glob("*/pyvenv.cfg") if p.is_file())
    referenced = set()
    for cfg in cfg_paths:
        try:
            for line in cfg.read_text().splitlines():
                if line.strip().lower().startswith("home"):
                    home = line.split("=", 1)[1].strip()
                    try:
                        referenced.add(Path(home).resolve().parent)
                    except OSError:
                        continue
        except OSError:
            continue
    return referenced


def _find_orphan_uv_pythons(work_dirs: list[Path], referenced: set = None) -> list[tuple[str, Path]]:
    """uv-managed Python installs not referenced by any venv or uv tool.

    Deliberately conservative: only flags a version if `uv python dir` and
    `uv python list --only-installed` both succeed and the resolved install
    dir is genuinely under `uv python dir`. `uv python list` reports each
    interpreter's own binary path, which can itself be a minor-version
    alias (cpython-3.14-... -> cpython-3.14.6-...) or a Homebrew/system
    Python entirely (verified live: `/opt/homebrew/bin/python3.14`,
    `/usr/bin/python3` both appear in the listing) -- resolving the path
    and checking it's an actual descendant of `uv python dir` is what
    keeps those out, not an incidental is_dir()/is_symlink() check on a
    name-derived path.

    `referenced` should be computed once up front by the caller, before any
    target in this run has deleted anything: computing it lazily in here
    would miss a venv this same run's venv/node_modules target already
    deleted (see build_report, where the referenced set is built before
    any target applies for exactly this reason).
    """
    if not _has("uv"):
        return []
    dir_result = _run(["uv", "python", "dir"])
    if dir_result.returncode != 0:
        return []
    python_dir = Path(dir_result.stdout.strip())
    if not python_dir.is_dir():
        return []
    resolved_python_dir = python_dir.resolve()
    list_result = _run(["uv", "python", "list", "--only-installed"])
    if list_result.returncode != 0:
        return []
    if referenced is None:
        referenced = _find_referenced_uv_pythons(work_dirs)
    orphans = []
    for line in list_result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        key, raw_path = parts[0], parts[1]
        try:
            interpreter = Path(raw_path).resolve()
        except OSError:
            continue
        install_dir = interpreter.parent.parent if interpreter.parent.name == "bin" else interpreter.parent
        if not install_dir.is_relative_to(resolved_python_dir):
            continue  # Homebrew/system Python, or anything outside uv's own install dir
        if install_dir in referenced:
            continue
        orphans.append((key, install_dir))
    return orphans


def _apply_uv_python_orphans(work_dirs: list[Path], dry_run: bool, yes: bool, referenced: set = None) -> list[dict]:
    """Delegates the actual removal to `uv python uninstall`, not a raw
    directory delete -- matches the skill's CLI-over-rm-rf pattern for
    every other package-manager-owned target (brew/pip/npm)."""
    results = []
    for key, install_dir in _find_orphan_uv_pythons(work_dirs, referenced=referenced):
        size = _du(install_dir)
        freed = 0
        if not dry_run:
            if not yes and not _confirm(f"  uv python uninstall {key} ({_fmt(size)})?"):
                continue
            _run(["uv", "python", "uninstall", key])
            if not install_dir.exists():
                freed = size
        results.append({"path": str(install_dir), "size": size, "freed": freed})
    return results


def _audit_claude_memory(profiles: list[Path]) -> list[dict]:
    """Report-only: per-project memory dir size + newest-file mtime.

    Never deletes. Decoding a project's live path from its encoded dirname
    is ambiguous (real directory names contain hyphens), so automated
    "is this project gone" detection produces false positives -- verified
    on this machine, where every encoded dir still had a live project.
    Memory content also doesn't go stale by age the way a cache does, so
    this stays a human decision.
    """
    results = []
    for profile in profiles:
        projects_dir = profile / "projects"
        if not projects_dir.exists():
            continue
        for project in projects_dir.iterdir():
            mem = project / "memory"
            if not mem.is_dir():
                continue
            size = _du(mem)
            if size == 0:
                continue
            try:
                newest = max(
                    (p.stat().st_mtime for p in mem.rglob("*") if p.is_file()),
                    default=None,
                )
            except OSError:
                newest = None
            results.append({"path": str(mem), "size": size, "newest": newest})
    return results


def _apply_dirs(paths: list[Path], dry_run: bool, yes: bool, allowed=_in_allowlist) -> list[dict]:
    """Shared apply logic for any list of directory delete candidates:
    delete-gate, size, confirm (unless --yes), rmtree whole. Used for
    stale node_modules/venvs and plugin cache dirs (old versions, plugin
    node_modules, marketplace .git) alike -- all are directories deleted
    in one piece, never partially.

    `allowed` defaults to the general ALLOWLIST check; stale node_modules/
    venv callers pass `_stale_dir_allowed` bound to the work dirs instead,
    since work dirs are deliberately never added to ALLOWLIST itself.
    """
    results = []
    for path in paths:
        if not allowed(path):
            continue
        size = _du(path)
        freed = 0
        if not dry_run:
            if not yes and not _confirm(f"  Delete {path} ({_fmt(size)})?"):
                continue
            shutil.rmtree(path, ignore_errors=True)
            freed = size
        results.append({"path": str(path), "size": size, "freed": freed})
    return results


def _find_plugin_node_modules(profiles: list[Path]) -> list[Path]:
    """node_modules dirs under <profile>/plugins/cache/**.

    Unlike project node_modules, these belong to the plugin runtime, not a
    live workspace, so there's no age/staleness question: they're rebuilt
    automatically the next time the plugin runs. depth is bounded the same
    way _find_stale_dirs bounds project scans.
    """
    results = []
    for profile in profiles:
        cache_dir = profile / "plugins" / "cache"
        if not cache_dir.exists():
            continue
        base_depth = len(cache_dir.resolve().parts)
        for root, dirs, _files in os.walk(cache_dir):
            root_path = Path(root)
            depth = len(root_path.resolve().parts) - base_depth
            if depth >= _NM_MAX_DEPTH:
                dirs.clear()
                continue
            if "node_modules" in dirs:
                dirs.remove("node_modules")
                results.append(root_path / "node_modules")
            dirs[:] = [d for d in dirs if not d.startswith(".")]
    return results


def _load_plugin_manifest_paths(profile: Path) -> set[Path]:
    """Resolved installPath values from <profile>/plugins/installed_plugins.json.

    Missing or unparseable manifest -> empty set, which makes
    _find_plugin_old_versions flag nothing for that profile: unknown state
    is never a delete candidate.
    """
    manifest = profile / "plugins" / "installed_plugins.json"
    if not manifest.is_file():
        return set()
    try:
        data = json.loads(manifest.read_text())
    except (OSError, json.JSONDecodeError):
        return set()
    paths = set()
    for entries in data.get("plugins", {}).values():
        for entry in entries:
            install_path = entry.get("installPath")
            if not install_path:
                continue
            try:
                paths.add(Path(install_path).resolve())
            except OSError:
                continue
    return paths


def _find_plugin_old_versions(profiles: list[Path]) -> list[Path]:
    """Version dirs under <profile>/plugins/cache/<vendor>/<plugin>/<version>/
    that installed_plugins.json does not point at, for a plugin that has at
    least one dir the manifest does point at.

    Driven by the manifest, not version-sorting: Claude Code's active
    install for a plugin is not always the numerically highest version dir
    -- it can be a git SHA (verified on this machine:
    frontend-design@claude-plugins-official installs to a SHA-named dir,
    not a version number). A plugin with no manifest entry at all is left
    alone entirely, even if it has multiple version dirs.
    """
    results = []
    for profile in profiles:
        cache_dir = profile / "plugins" / "cache"
        if not cache_dir.exists():
            continue
        keep = _load_plugin_manifest_paths(profile)
        manifest = profile / "plugins" / "installed_plugins.json"
        try:
            manifest_mtime = manifest.stat().st_mtime
        except OSError:
            manifest_mtime = None
        for vendor in cache_dir.iterdir():
            if not vendor.is_dir():
                continue
            for plugin in vendor.iterdir():
                if not plugin.is_dir():
                    continue
                versions = [v for v in plugin.iterdir() if v.is_dir()]
                resolved = {v: v.resolve() for v in versions}
                if not any(r in keep for r in resolved.values()):
                    continue  # no manifest entry for this plugin; leave alone
                for v, r in resolved.items():
                    if r in keep:
                        continue
                    # Install then manifest-update is two steps; a version
                    # dir created after the manifest was last written might
                    # be the incoming active install with its manifest
                    # entry not landed yet. Skip it rather than risk
                    # deleting the install about to become active.
                    if manifest_mtime is not None:
                        try:
                            if v.stat().st_mtime > manifest_mtime:
                                continue
                        except OSError:
                            pass
                    results.append(v)
    return results


def _find_plugin_marketplace_git(profiles: list[Path]) -> list[Path]:
    """.git dirs at the top of each marketplace clone under <profile>/plugins/marketplaces."""
    results = []
    for profile in profiles:
        marketplaces = profile / "plugins" / "marketplaces"
        if not marketplaces.exists():
            continue
        for marketplace in marketplaces.iterdir():
            git_dir = marketplace / ".git"
            if git_dir.is_dir():
                results.append(git_dir)
    return results


def _find_plugin_marketplace_binaries(profiles: list[Path]) -> list[Path]:
    """Large tracked binaries (PDFs, archives, media) inside marketplace working trees.

    These are upstream repo content, not a cache, but they aren't needed to
    run a plugin and get re-fetched on the next marketplace update.
    """
    results = []
    for profile in profiles:
        marketplaces = profile / "plugins" / "marketplaces"
        if not marketplaces.exists():
            continue
        for path in marketplaces.rglob("*"):
            if path.suffix.lower() not in _MARKETPLACE_BINARY_EXTS:
                continue
            try:
                if not path.is_file() or path.stat().st_size < _MARKETPLACE_BINARY_MIN_SIZE:
                    continue
            except OSError:
                continue
            results.append(path)
    return results


def _apply_plugin_marketplace_binaries(profiles: list[Path], dry_run: bool, yes: bool) -> list[dict]:
    results = []
    for path in _find_plugin_marketplace_binaries(profiles):
        if not _in_allowlist(path):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        freed = 0
        if not dry_run:
            if not yes and not _confirm(f"  Delete {path} ({_fmt(size)})?"):
                continue
            path.unlink(missing_ok=True)
            freed = size
        results.append({"path": str(path), "size": size, "freed": freed})
    return results


def _prune_claude_chats(profiles: list[Path], days: int, dry_run: bool) -> int:
    """Prune old session transcripts under <profile>/projects for every profile.

    Each project dir holds session .jsonl files, per-session subdirs, and a
    persistent memory/ dir. Only session files (and their matching subdir) older
    than the cutoff are removed; memory and the project dir itself are never
    touched.
    """
    cutoff = time.time() - days * 86400
    total = 0
    for profile in profiles:
        projects_dir = profile / "projects"
        if not projects_dir.exists():
            continue
        resolved_root = projects_dir.resolve()
        for project in projects_dir.iterdir():
            if not project.is_dir():
                continue
            if not project.resolve().is_relative_to(resolved_root):
                continue  # symlink escaping the projects tree, never follow it
            for entry in project.glob("*.jsonl"):
                try:
                    if entry.stat().st_mtime >= cutoff:
                        continue
                    size = entry.stat().st_size
                except OSError:
                    continue
                session_dir = project / entry.stem
                if session_dir.is_dir() and session_dir.name != "memory":
                    size += _du(session_dir)
                total += size
                if not dry_run:
                    entry.unlink(missing_ok=True)
                    if session_dir.is_dir() and session_dir.name != "memory":
                        shutil.rmtree(session_dir, ignore_errors=True)
    return total


def _delete_aged_entries(path: Path, max_age_s: float, dry_run: bool) -> int:
    """Delete top-level entries of `path` older than `max_age_s`, keeping
    `path` itself and anything touched more recently. A filesystem fact
    (mtime) rather than a process-name guess: a `pgrep` check for whatever
    process might be using `path` can't distinguish the live instance from
    an unrelated background daemon of the same name that's always running
    (verified: Claude Code's own bg-spare/bg-pty-host daemons keep `pgrep
    -x claude` matching permanently, which would make a process-based
    guard here never clean anything at all).
    """
    if not path.exists():
        return 0
    if not _in_allowlist(path):
        return 0
    cutoff = time.time() - max_age_s
    total = 0
    for entry in path.iterdir():
        try:
            if entry.stat().st_mtime >= cutoff:
                continue
            size = _du(entry) if entry.is_dir() else entry.stat().st_size
        except OSError:
            continue
        total += size
        if not dry_run:
            if entry.is_dir():
                shutil.rmtree(entry, ignore_errors=True)
            else:
                entry.unlink(missing_ok=True)
    return total


def _clean_claude_tmp(dry_run: bool) -> int:
    """Remove aged entries from Claude Code's tmp dir, sparing live sessions."""
    return _delete_aged_entries(_CLAUDE_TMP, _CLAUDE_TMP_MAX_AGE_S, dry_run)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _selftest() -> None:
    import tempfile

    # _positive_int: negative ages must be rejected, zero/positive accepted.
    try:
        _positive_int("-1")
        raise AssertionError("_positive_int accepted a negative value")
    except argparse.ArgumentTypeError:
        pass
    assert _positive_int("0") == 0
    assert _positive_int("30") == 30

    # _prune_claude_chats: a project dir symlinked outside ~/.claude/projects
    # must never be traversed, even if it holds stale-looking .jsonl files.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        outside = tmp_path / "outside"
        outside.mkdir()
        old_file = outside / "session.jsonl"
        old_file.write_text("{}")
        os.utime(old_file, (0, 0))  # far in the past, would match any cutoff

        projects_dir = tmp_path / ".claude" / "projects"
        projects_dir.mkdir(parents=True)
        (projects_dir / "escape-link").symlink_to(outside)

        global HOME
        real_home = HOME
        HOME = tmp_path
        try:
            freed = _prune_claude_chats([tmp_path / ".claude"], days=1, dry_run=True)
        finally:
            HOME = real_home
        assert freed == 0, "symlinked project dir was followed outside the tree"
        assert old_file.exists(), "file outside the projects tree was touched"

    # Plugin profile discovery + target scanning: build a fake ~/.claude-fake
    # profile with a node_modules, a marketplace .git, and a big tracked PDF,
    # confirm the glob and walks find all three.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        profile = tmp_path / ".claude-fake"
        nm = profile / "plugins" / "cache" / "vendor" / "plugin" / "1.0.0" / "node_modules"
        nm.mkdir(parents=True)
        (nm / "pkg.js").write_text("x")

        marketplace = profile / "plugins" / "marketplaces" / "vendor"
        (marketplace / ".git").mkdir(parents=True)
        (marketplace / ".git" / "HEAD").write_text("ref: refs/heads/main")

        plans = marketplace / "plans"
        plans.mkdir(parents=True)
        big_pdf = plans / "deck.pdf"
        big_pdf.write_bytes(b"0" * (_MARKETPLACE_BINARY_MIN_SIZE + 1))

        # Plugin version pruning is manifest-driven, not version-sorted: the
        # active install can be a git SHA dirname, not the highest version.
        # thedotmack/claude-mem has a SHA-named active install with an older
        # numeric version dir alongside it -- the manifest points at the SHA.
        sha_dir = profile / "plugins" / "cache" / "thedotmack" / "claude-mem" / "b819188d2eea"
        old_version = profile / "plugins" / "cache" / "thedotmack" / "claude-mem" / "13.16.1"
        sha_dir.mkdir(parents=True)
        old_version.mkdir(parents=True)
        (profile / "plugins" / "installed_plugins.json").write_text(json.dumps({
            "version": 2,
            "plugins": {
                "claude-mem@thedotmack": [{"installPath": str(sha_dir)}],
            },
        }))

        # A plugin with two version dirs but no manifest entry at all must
        # never be flagged -- unknown state is never a delete candidate.
        unmanifested_old = profile / "plugins" / "cache" / "thedotmack" / "q" / "1.0.0"
        unmanifested_new = profile / "plugins" / "cache" / "thedotmack" / "q" / "1.1.0"
        unmanifested_old.mkdir(parents=True)
        unmanifested_new.mkdir(parents=True)

        real_home = HOME
        HOME = tmp_path
        try:
            profiles = _detect_claude_profiles()
            assert profile in profiles, "fake profile with plugins/ not discovered"
            assert nm in _find_plugin_node_modules(profiles), "plugin node_modules not found"
            assert (marketplace / ".git") in _find_plugin_marketplace_git(profiles), \
                "marketplace .git not found"
            assert big_pdf in _find_plugin_marketplace_binaries(profiles), \
                "large marketplace binary not found"
            old_versions = _find_plugin_old_versions(profiles)
            assert old_version in old_versions, "superseded version dir not flagged"
            assert sha_dir not in old_versions, \
                "manifest-referenced SHA install wrongly flagged"
            assert unmanifested_old not in old_versions, \
                "unmanifested plugin version wrongly flagged"
            assert unmanifested_new not in old_versions, \
                "unmanifested plugin version wrongly flagged"
        finally:
            HOME = real_home

    # uv-python-orphans: a venv's pyvenv.cfg must mark its interpreter as
    # referenced; an interpreter no pyvenv.cfg points at must not be. A venv
    # that references the interpreter through uv's minor-version symlink
    # (cpython-3.14-x -> cpython-3.14.6-x) must resolve to the same real
    # dir as one referencing it directly, so the real install is never
    # flagged as an orphan just because of which spelling a venv used.
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        work_dir = tmp_path / "work"
        python_dir = tmp_path / "uv-python"
        real_dir = python_dir / "cpython-3.14.6-macos-aarch64-none"
        (real_dir / "bin").mkdir(parents=True)
        symlink_dir = python_dir / "cpython-3.14-macos-aarch64-none"
        symlink_dir.symlink_to(real_dir)
        orphan_dir = python_dir / "cpython-3.13.15-macos-aarch64-none"
        (orphan_dir / "bin").mkdir(parents=True)

        venv_dir = work_dir / "proj" / ".venv"
        venv_dir.mkdir(parents=True)
        (venv_dir / "pyvenv.cfg").write_text(
            f"home = {symlink_dir / 'bin'}\nversion = 3.14.6\n"
        )
        referenced = _find_referenced_uv_pythons([work_dir])
        assert real_dir.resolve() in referenced, \
            "symlinked uv python home not resolved to its real interpreter dir"
        assert orphan_dir.resolve() not in referenced, \
            "unreferenced uv python incorrectly counted as referenced"

    # _measure_or_none vs _du: an unreadable existing path must report None
    # (not 0), so a report row can show reclaimable: null instead of
    # silently reading as "nothing to clean"; _du must coerce that same
    # failure back to 0 for apply-time arithmetic; and summing reclaimable
    # across mixed None/int rows (as build_report's total does) must skip
    # the Nones rather than raise. A throwaway-HOME fixture run as the
    # owning user never actually hits a du permission failure, so this is
    # the only place that failure path gets exercised at all. Skipped as
    # root (geteuid() == 0): root ignores permission bits, so chmod 000
    # wouldn't actually block du there, and the assertion would fail for a
    # reason unrelated to the code under test.
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        with tempfile.TemporaryDirectory() as tmp:
            blocked = Path(tmp) / "blocked"
            blocked.mkdir()
            (blocked / "f").write_text("x")
            os.chmod(blocked, 0o000)
            try:
                measured = _measure_or_none(blocked)
                assert measured is None, f"unreadable path must report None, got {measured}"
                assert _du(blocked) == 0, "_du must coerce an unreadable path's failure to 0"
            finally:
                os.chmod(blocked, 0o755)  # restore so TemporaryDirectory cleanup can remove it
    rows = [{"reclaimable": None}, {"reclaimable": 100}]
    total = sum(r["reclaimable"] for r in rows if r["reclaimable"] is not None)
    assert total == 100, "totals sum must skip a None reclaimable row without raising"

    print("selftest ok")


def _positive_int(value: str) -> int:
    """Argparse type: rejects negative ages, which flip the cutoff into the
    future and make every file look stale (see --selftest)."""
    n = int(value)
    if n < 0:
        raise argparse.ArgumentTypeError(f"must be >= 0, got {n}")
    return n


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mac disk cleanup: dry-run by default.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--level", type=int, default=1, choices=[1, 2, 3],
                   help="Cleanup depth (1=safe, 2=moderate, 3=aggressive). Default: 1")
    p.add_argument("--apply", action="store_true",
                   help="Execute cleanup. Without this flag, only reports reclaimable space.")
    p.add_argument("--only", type=str, default="",
                   help="Comma-separated list of targets to include (e.g. brew,uv,pip)")
    p.add_argument("--skip", type=str, default="",
                   help="Comma-separated list of targets to exclude")
    p.add_argument("--include-dangerous", action="store_true",
                   help="Enable dangerous targets (docker system prune -a --volumes)")
    p.add_argument("--yes", action="store_true",
                   help="Skip all interactive confirmation prompts")
    p.add_argument("--json", action="store_true", dest="json_out",
                   help="Output machine-readable JSON")
    p.add_argument("--selftest", action="store_true",
                   help="Run internal self-checks and exit (handled in main() before parsing)")
    p.add_argument("--chats-older-than", type=_positive_int, default=30, metavar="DAYS",
                   help="Age threshold for Claude chat pruning (default: 30)")
    p.add_argument("--stale-days", type=_positive_int, default=30, metavar="DAYS",
                   help="Age threshold for stale node_modules (default: 30)")
    p.add_argument("--work-dir", type=str, default="", metavar="DIR",
                   help="Directory to scan for stale node_modules (default: auto-detect "
                        f"from {_WORK_DIR_CANDIDATES})")
    args = p.parse_args()
    for flag in ("only", "skip"):
        names = set(getattr(args, flag).split(",")) - {""}
        unknown = names - KNOWN_TARGETS
        if unknown:
            p.error(f"--{flag}: unknown target(s) {sorted(unknown)}; "
                    f"valid: {sorted(KNOWN_TARGETS)}")
    return args


def build_report(args: argparse.Namespace, work_dirs: list[Path], profiles: list[Path]) -> list[dict]:
    only = set(args.only.split(",")) - {""} if args.only else set()
    skip = set(args.skip.split(",")) - {""} if args.skip else set()
    dry_run = not args.apply
    level = args.level

    # Computed once, up front, before any target below has deleted anything:
    # venv/node_modules apply earlier in this function than uv-python-orphans
    # does, and if the referenced set were recomputed lazily inside that
    # target it would no longer see a pyvenv.cfg this same run just deleted,
    # turning its own interpreter into a false "orphan" and uninstalling it
    # in the same --apply. Computing it here means the orphan decision
    # always reflects the state before this run touched anything.
    referenced_uv_pythons = _find_referenced_uv_pythons(work_dirs)

    def active(name: str, target_level: int) -> bool:
        if target_level > level:
            return False
        if only and name not in only:
            return False
        if name in skip:
            return False
        return True

    report: list[dict] = []

    # --- Level 1: package-manager CLIs ---

    if active("brew", 1):
        size = _measure_brew(level)
        freed = 0
        if not dry_run and size > 0:
            freed = _apply_brew(level)
        note = "brew cleanup -s --prune=all" if level >= 3 else "brew cleanup -s"
        report.append({"target": "brew", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": note})

    pip_bin = "pip" if _has("pip") else "pip3"
    cli_targets = [
        ("uv", HOME / ".cache" / "uv", ["uv", "cache", "prune"]),
        ("pip", HOME / "Library" / "Caches" / "pip", [pip_bin, "cache", "purge"]),
        ("npm", HOME / ".npm" / "_cacache", ["npm", "cache", "clean", "--force"]),
    ]
    for name, path, cli in cli_targets:
        if not active(name, 1):
            continue
        if not _has(cli[0]):
            report.append({"target": name, "level": 1, "reclaimable": 0, "freed": 0,
                            "risk": "low", "note": f"{cli[0]} not found, skipped"})
            continue
        size = _du(path)
        freed = 0
        if not dry_run and size > 0:
            freed = _apply_cli(cli, path)
        report.append({"target": name, "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": " ".join(cli)})

    if active("bun", 1):
        # bun pm cache rm requires a project context; delete the cache dir directly.
        bun_cache = HOME / ".bun" / "install" / "cache"
        size = _du(bun_cache)
        freed = 0
        if not dry_run and size > 0:
            freed = _delete_dir(bun_cache, dry_run=False)
        report.append({"target": "bun", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": "~/.bun/install/cache"})

    if active("claude-tmp", 1):
        size = _clean_claude_tmp(dry_run=True)
        freed = 0
        if not dry_run and size > 0:
            freed = _clean_claude_tmp(dry_run=False)
        report.append({"target": "claude-tmp", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low",
                        "note": f"{_CLAUDE_TMP} entries older than 1d (live session preserved)"})

    # --- Level 2: app caches + logs + Claude ---

    if active("trash", 2):
        # Not a package-manager cache, so this moved out of level 1: Trash
        # is the undo buffer, not a cache. Also: ~/.Trash is TCC-blocked
        # for Terminal on macOS by default, which _measure_or_none surfaces
        # as reclaimable: null instead of a silent "nothing to clean".
        path = HOME / ".Trash"
        size = _measure_or_none(path)
        freed = 0
        if size is None:
            note = "unreadable, grant Full Disk Access to the terminal"
        else:
            note = "~/.Trash"
            if not dry_run and size > 0:
                freed = _empty_dir(path, dry_run=False)
        report.append({"target": "trash", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": note})

    if active("chrome", 2):
        path = HOME / "Library" / "Caches" / "Google" / "Chrome"
        app_support = HOME / "Library" / "Application Support" / "Google" / "Chrome"
        size, freed, running, details = _electron_cache_report([app_support], "Google Chrome", dry_run)
        size += _du(path)
        if path.exists():
            details = [str(path)] + details
        if not dry_run and not running:
            freed += _delete_dir(path, dry_run=False)
        if running and not dry_run:
            note = "Google Chrome running, skipped -- quit Chrome first"
        else:
            note = "quit Chrome before --apply; App Support cache subdirs only, profile/bookmarks untouched"
        report.append({"target": "chrome", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": note, "details": details})

    if active("teams", 2):
        teams_roots = [
            HOME / "Library" / "Containers" / "com.microsoft.teams2",
            HOME / "Library" / "Group Containers" / "UBF8T346G9.com.microsoft.teams",
        ]
        size, freed, running, details = _electron_cache_report(teams_roots, "MSTeams", dry_run)
        if running and not dry_run:
            note = "MSTeams running, skipped -- quit Teams first"
        else:
            note = "cache subdirs only; login/session preserved"
        report.append({"target": "teams", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": note, "details": details})

    if active("claude-desktop", 2):
        path = HOME / "Library" / "Application Support" / "Claude"
        size, freed, running, details = _electron_cache_report([path], "Claude", dry_run)
        if running and not dry_run:
            note = "Claude running, skipped -- quit Claude desktop first"
        else:
            note = ("cache subdirs only; chat history/settings untouched, as is "
                     "vm_bundles (Cowork sandbox VM disk image, not cache -- "
                     "usually the biggest item here, deleting it forces a rebuild "
                     "from its bundled .zst next time Cowork runs)")
        report.append({"target": "claude-desktop", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": note, "details": details})

    if active("discord", 2):
        path = HOME / "Library" / "Application Support" / "discord"
        size, freed, running, details = _electron_cache_report([path], "Discord", dry_run)
        if running and not dry_run:
            note = "Discord running, skipped -- quit Discord first"
        else:
            note = "cache subdirs only; login preserved"
        report.append({"target": "discord", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": note, "details": details})

    if active("claude-memory", 2):
        mem_results = _audit_claude_memory(profiles)
        total_size = sum(r["size"] for r in mem_results)
        report.append({"target": "claude-memory", "level": 2, "reclaimable": 0, "freed": 0,
                        "risk": "info",
                        "note": f"{_fmt(total_size)} across {len(mem_results)} project dirs: "
                                "report-only, review manually (never auto-deleted)",
                        "details": [r["path"] for r in mem_results]})

    if active("jetbrains", 2):
        jb = HOME / "Library" / "Caches" / "JetBrains"
        size = _du(jb)
        freed = 0
        if not dry_run and size > 0:
            for subdir in jb.iterdir() if jb.exists() else []:
                if subdir.is_dir() and _in_allowlist(subdir):
                    freed += _delete_dir(subdir, dry_run=False)
        report.append({"target": "jetbrains", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low-med", "note": "IDE reindexes on next open"})

    if active("logs", 2):
        path = HOME / "Library" / "Logs"
        size = _delete_old_files(path, args.stale_days, dry_run=True)
        freed = 0
        if not dry_run:
            freed = _delete_old_files(path, args.stale_days, dry_run=False)
        report.append({"target": "logs", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": f"logs older than {args.stale_days}d"})

    if active("claude-cache", 2):
        # shell-snapshots holds the live session's own snapshot file;
        # deleting it out from under a running Claude Code process kills
        # every Bash call in that session. Age-gated like claude-tmp
        # rather than process-checked: a pgrep check can't tell the live
        # session apart from Claude Code's own background daemons, which
        # keep `pgrep -x claude` matching permanently (verified live), so
        # a process-based guard here would never clean anything at all.
        size = 0
        freed = 0
        for p in profiles:
            snap_size = _delete_aged_entries(p / "shell-snapshots", _CLAUDE_TMP_MAX_AGE_S, dry_run=True)
            size += snap_size
            if not dry_run:
                freed += _delete_aged_entries(p / "shell-snapshots", _CLAUDE_TMP_MAX_AGE_S, dry_run=False)
            for sub in ("paste-cache", "cache"):
                path = p / sub
                size += _du(path)
                if not dry_run:
                    freed += _delete_dir(path, dry_run=False)
        report.append({"target": "claude-cache", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low",
                        "note": f"shell-snapshots entries older than 1d (live session preserved), "
                                "paste-cache, cache dirs"})

    if active("claude-chats", 2):
        size = _prune_claude_chats(profiles, args.chats_older_than, dry_run=True)
        freed = 0
        if not dry_run:
            freed = _prune_claude_chats(profiles, args.chats_older_than, dry_run=False)
        report.append({"target": "claude-chats", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low-med",
                        "note": f"sessions older than {args.chats_older_than}d (loses --resume)"})

    if active("docker", 2):
        all_imgs = level >= 3
        include_containers = level >= 3
        size = _measure_docker(include_containers=include_containers, all_images=all_imgs)
        freed = 0
        if size is None:
            note = "Docker daemon not running, unmeasured -- start it and re-run"
        else:
            if not dry_run and size > 0:
                freed = _apply_docker(include_containers=include_containers, all_images=all_imgs,
                                       include_dangerous=False, yes=args.yes)
            if all_imgs:
                note = "image prune -a -f + builder prune -f + container prune -f (no volumes)"
            else:
                note = "image prune -f + builder prune -f (dangling only, no volumes, containers untouched)"
        report.append({"target": "docker", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": note})

    # --- Level 3: aggressive ---

    if active("node_modules", 3):
        nm_paths = _find_stale_dirs(args.stale_days, work_dirs, ("node_modules",))
        nm_results = _apply_dirs(nm_paths, dry_run=dry_run, yes=args.yes,
                                  allowed=lambda p: _stale_dir_allowed(p, work_dirs))
        size = sum(r["size"] for r in nm_results)
        freed = sum(r["freed"] for r in nm_results)
        note = f"{len(nm_results)} dirs untouched >{args.stale_days}d; reinstall needed"
        report.append({"target": "node_modules", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": note,
                        "details": [r["path"] for r in nm_results]})

    if active("xcode", 3):
        # Archives deliberately excluded: they hold the dSYMs for shipped
        # builds, the only copy, not a cache -- without them a crash report
        # from a user can't be symbolicated. DerivedData is a pure build
        # cache and always safe to rebuild.
        build_paths = [
            HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
        ]
        sim_path = HOME / "Library" / "Developer" / "CoreSimulator" / "Devices"
        size = sum(_du(p) for p in build_paths) + _du(sim_path)
        freed = 0
        if not dry_run and size > 0:
            if args.yes or _confirm(f"  Delete Xcode DerivedData + prune simulators ({_fmt(size)})?"):
                for p in build_paths:
                    freed += _delete_dir(p, dry_run=False)
                # Only the official CLI's own notion of "unavailable" is
                # ever removed. No xcrun fallback: rmtree-ing the whole
                # Devices tree would wipe every simulator, available ones
                # included, along with their installed app containers and
                # databases -- not what "unavailable simulators" promises.
                if sim_path.exists() and _has("xcrun"):
                    before = _du(sim_path)
                    _run(["xcrun", "simctl", "delete", "unavailable"])
                    freed += max(0, before - _du(sim_path))
        report.append({"target": "xcode", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": "DerivedData + unavailable simulators (Archives kept: shipped-build dSYMs, not a cache)"})

    if active("venv", 3):
        venv_paths = _find_stale_dirs(args.stale_days, work_dirs, (".venv", "venv"), marker="pyvenv.cfg")
        venv_results = _apply_dirs(venv_paths, dry_run=dry_run, yes=args.yes,
                                    allowed=lambda p: _stale_dir_allowed(p, work_dirs))
        size = sum(r["size"] for r in venv_results)
        freed = sum(r["freed"] for r in venv_results)
        note = f"{len(venv_results)} dirs untouched >{args.stale_days}d; uv sync/pip install needed"
        report.append({"target": "venv", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": note,
                        "details": [r["path"] for r in venv_results]})

    if active("uv-python-orphans", 3):
        orphan_results = _apply_uv_python_orphans(work_dirs, dry_run=dry_run, yes=args.yes,
                                                    referenced=referenced_uv_pythons)
        size = sum(r["size"] for r in orphan_results)
        freed = sum(r["freed"] for r in orphan_results)
        report.append({"target": "uv-python-orphans", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "low",
                        "note": f"{len(orphan_results)} uv Python(s) unreferenced by any venv/tool; "
                                "uv python uninstall",
                        "details": [r["path"] for r in orphan_results]})

    if active("plugin-old-versions", 3):
        old_version_results = _apply_dirs(_find_plugin_old_versions(profiles), dry_run=dry_run, yes=args.yes)
        size = sum(r["size"] for r in old_version_results)
        freed = sum(r["freed"] for r in old_version_results)
        report.append({"target": "plugin-old-versions", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": f"{len(old_version_results)} superseded plugin version dirs",
                        "details": [r["path"] for r in old_version_results]})

    if active("plugin-node-modules", 3):
        nm_results = _apply_dirs(_find_plugin_node_modules(profiles), dry_run=dry_run, yes=args.yes)
        size = sum(r["size"] for r in nm_results)
        freed = sum(r["freed"] for r in nm_results)
        report.append({"target": "plugin-node-modules", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med",
                        "note": f"{len(nm_results)} dirs; reinstalled on next plugin run "
                                "(rebuild path unverified, try once on a secondary profile first)",
                        "details": [r["path"] for r in nm_results]})

    if active("plugin-marketplace-git", 3):
        git_results = _apply_dirs(_find_plugin_marketplace_git(profiles), dry_run=dry_run, yes=args.yes)
        size = sum(r["size"] for r in git_results)
        freed = sum(r["freed"] for r in git_results)
        report.append({"target": "plugin-marketplace-git", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": f"{len(git_results)} dirs; re-cloned on next marketplace update",
                        "details": [r["path"] for r in git_results]})

    if active("plugin-marketplace-binaries", 3):
        bin_results = _apply_plugin_marketplace_binaries(profiles, dry_run=dry_run, yes=args.yes)
        size = sum(r["size"] for r in bin_results)
        freed = sum(r["freed"] for r in bin_results)
        report.append({"target": "plugin-marketplace-binaries", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": f"{len(bin_results)} files; re-fetched from upstream if needed",
                        "details": [r["path"] for r in bin_results]})

    # --- Dangerous ---

    if args.include_dangerous and active("docker-volumes", 3):
        size = _measure_docker(include_containers=True, all_images=True)
        freed = 0
        note = "docker system prune -a --volumes: ALL images and volumes"
        if size is None:
            note = "Docker daemon not running, unmeasured -- start it and re-run"
        elif not dry_run:
            freed = _apply_docker(include_containers=True, all_images=True,
                                   include_dangerous=True, yes=args.yes)
        report.append({"target": "docker-volumes", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "HIGH", "note": note})

    return report


def main() -> None:
    if "--selftest" in sys.argv[1:]:
        _selftest()
        return

    args = parse_args()
    dry_run = not args.apply

    work_dirs = [Path(args.work_dir).expanduser()] if args.work_dir else _detect_work_dirs()
    profiles = _detect_claude_profiles()
    _build_allowlist(work_dirs, profiles)

    disk = shutil.disk_usage("/")
    free_before = disk.free

    if not args.json_out:
        mode = "DRY-RUN" if dry_run else "APPLY"
        print(f"\n=== disk-janitor [{mode}] level={args.level} ===")
        print(f"Free before: {_fmt(free_before)} / {_fmt(disk.total)}\n")

    report = build_report(args, work_dirs, profiles)

    free_after = shutil.disk_usage("/").free
    # A row's reclaimable can be None (unreadable path, see _measure_or_none);
    # excluded from the total rather than crashing the sum, since it isn't a
    # known quantity of freeable space.
    total_reclaimable = sum(r["reclaimable"] for r in report if r["reclaimable"] is not None)
    total_freed = sum(r["freed"] for r in report)

    if args.json_out:
        output = {
            "mode": "dry-run" if dry_run else "apply",
            "level": args.level,
            "free_before": free_before,
            "free_after": free_after,
            "total_reclaimable": total_reclaimable,
            "total_freed": total_freed,
            "targets": report,
        }
        print(json.dumps(output, indent=2))
        return

    col_w = 16
    print(f"{'TARGET':<{col_w}} {'LVL':>3}  {'RECLAIMABLE':>11}  {'FREED':>8}  RISK        NOTE")
    print("-" * 90)
    for r in report:
        details = r.get("details", [])
        print(
            f"{r['target']:<{col_w}} {r['level']:>3}  "
            f"{_fmt(r['reclaimable']):>11}  {_fmt(r['freed']):>8}  "
            f"{r['risk']:<10}  {r['note']}"
        )
        for d in details[:3]:
            print(f"  {'':>{col_w + 5}} {d}")
        if len(details) > 3:
            print(f"  {'':>{col_w + 5}} ... and {len(details) - 3} more")

    print("-" * 90)
    if dry_run:
        print(f"Total reclaimable: {_fmt(total_reclaimable)}")
        print("\nRun with --apply to execute. Add --level 2 or --level 3 for deeper cleanup.")
    else:
        delta = free_after - free_before
        print(f"Total freed: {_fmt(total_freed)}")
        print(f"Free space: {_fmt(free_before)} → {_fmt(free_after)} (delta: +{_fmt(max(0, delta))})")


if __name__ == "__main__":
    main()
