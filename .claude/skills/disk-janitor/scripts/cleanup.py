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
}

# Common project directory names to probe when --work-dir is not specified.
_WORK_DIR_CANDIDATES = ["Work", "Projects", "projects", "dev", "code", "src", "repos"]


def _detect_work_dirs() -> list[Path]:
    found = [HOME / name for name in _WORK_DIR_CANDIDATES if (HOME / name).is_dir()]
    return found or [HOME]


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
    HOME / "Library" / "Developer" / "Xcode" / "Archives",
    HOME / "Library" / "Developer" / "CoreSimulator" / "Devices",
]

ALLOWLIST: list[Path] = []


def _build_allowlist(work_dirs: list[Path]) -> None:
    ALLOWLIST.clear()
    ALLOWLIST.extend(_ALLOWLIST_BASE)
    ALLOWLIST.extend(work_dirs)


def _in_allowlist(path: Path) -> bool:
    resolved = path.resolve()
    return any(
        resolved == allowed.resolve() or resolved.is_relative_to(allowed.resolve())
        for allowed in ALLOWLIST
    )


def _du(path: Path) -> int:
    """Return directory size in bytes, 0 if missing."""
    if not path.exists():
        return 0
    result = subprocess.run(
        ["du", "-sk", str(path)], capture_output=True, text=True
    )
    if result.returncode != 0:
        return 0
    try:
        return int(result.stdout.split()[0]) * 1024
    except (IndexError, ValueError):
        return 0


def _run(cmd: list[str], check: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _has(binary: str) -> bool:
    if shutil.which(binary) is None:
        return False
    # Shims (e.g. pyenv) may exist on PATH but fail at runtime; verify executable.
    result = subprocess.run([binary, "--version"], capture_output=True)
    return result.returncode == 0


def _fmt(b: float) -> str:
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

def _measure_brew() -> int:
    if not _has("brew"):
        return 0
    result = _run(["brew", "cleanup", "-n", "-s"])
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


def _measure_docker(all_images: bool = False) -> int:
    """Measure reclaimable docker space.

    With all_images=False (level 2): counts dangling images, stopped containers,
    and build cache — what 'prune -f' actually frees. Tagged unused images are
    excluded because 'prune -f' never removes them.
    With all_images=True (level 3): also counts unused tagged images.
    """
    if not _has("docker"):
        return 0
    result = _run(["docker", "system", "df", "--format", "{{.Type}}\t{{.Reclaimable}}"])
    if result.returncode != 0:
        return 0
    total = 0
    for line in result.stdout.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        dtype, reclaimable = parts[0].strip(), parts[1].strip()
        if dtype == "Local Volumes":
            continue  # never freed without --volumes
        if dtype == "Images" and not all_images:
            # prune -f skips tagged images; count only dangling ones
            dangling = _run(["docker", "images", "-q", "-f", "dangling=true"])
            for img_id in dangling.stdout.split():
                inspect = _run(["docker", "inspect", "--format", "{{.Size}}", img_id])
                try:
                    total += int(inspect.stdout.strip())
                except ValueError:
                    pass
            continue
        total += _parse_docker_size(reclaimable)
    return total


def _apply_docker(all_images: bool, include_dangerous: bool, yes: bool) -> int:
    if not _has("docker"):
        return 0
    result = _run(["docker", "info"])
    if result.returncode != 0:
        print("  [SKIP] Docker daemon not running")
        return 0
    before = _measure_docker(all_images=all_images or include_dangerous)
    if include_dangerous:
        if not yes and not _confirm("  docker system prune -a --volumes — destroys ALL unused images and volumes. Continue?"):
            return 0
        _run(["docker", "system", "prune", "-a", "--volumes", "-f"])
    elif all_images:
        if not yes and not _confirm("  docker system prune -a -f — removes ALL unused images (not just dangling). Continue?"):
            return 0
        _run(["docker", "system", "prune", "-a", "-f"])
    else:
        _run(["docker", "system", "prune", "-f"])
    after = _measure_docker(all_images=all_images or include_dangerous)
    return max(0, before - after)


def _find_stale_node_modules(stale_days: int, work_dirs: list[Path]) -> list[tuple[Path, int]]:
    """Find top-level node_modules dirs of projects untouched within the stale window.

    Nested node_modules (inside another node_modules) are never returned: deleting
    one would corrupt a possibly-active project's dependency tree. The walk prunes
    hidden dirs, never descends into a matched node_modules, and stops at
    _NM_MAX_DEPTH levels under each work dir.
    """
    cutoff = time.time() - stale_days * 86400
    results = []
    seen: set[Path] = set()
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
            if "node_modules" in dirs:
                dirs.remove("node_modules")
                nm = root_path / "node_modules"
                if nm.resolve() in seen:
                    continue
                seen.add(nm.resolve())
                if not _in_allowlist(nm):
                    continue
                if nm.stat().st_mtime > cutoff:
                    continue
                # Guard: skip if anything in the project root was touched recently.
                try:
                    project_mtime = max(
                        p.stat().st_mtime for p in root_path.iterdir()
                        if p.name != "node_modules"
                    )
                except (StopIteration, ValueError, OSError):
                    project_mtime = nm.stat().st_mtime
                if project_mtime > cutoff:
                    continue
                results.append((nm, _du(nm)))
            dirs[:] = [d for d in dirs if not d.startswith(".")]
    return results


def _apply_node_modules(stale_days: int, work_dirs: list[Path], dry_run: bool, yes: bool) -> list[dict]:
    targets = _find_stale_node_modules(stale_days, work_dirs)
    results = []
    for nm, size in targets:
        freed = 0
        if not dry_run:
            if not yes and not _confirm(f"  Delete {nm} ({_fmt(size)})?"):
                continue
            shutil.rmtree(nm, ignore_errors=True)
            freed = size
        results.append({"path": str(nm), "size": size, "freed": freed})
    return results


def _prune_claude_chats(days: int, dry_run: bool) -> int:
    """Prune old session transcripts under ~/.claude/projects.

    Each project dir holds session .jsonl files, per-session subdirs, and a
    persistent memory/ dir. Only session files (and their matching subdir) older
    than the cutoff are removed; memory and the project dir itself are never
    touched.
    """
    projects_dir = HOME / ".claude" / "projects"
    if not projects_dir.exists():
        return 0
    cutoff = time.time() - days * 86400
    total = 0
    for project in projects_dir.iterdir():
        if not project.is_dir():
            continue
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


def _clean_claude_tmp(dry_run: bool) -> int:
    """Remove aged entries from Claude Code's tmp dir, sparing live sessions."""
    if not _CLAUDE_TMP.exists():
        return 0
    if not _in_allowlist(_CLAUDE_TMP):
        return 0
    cutoff = time.time() - _CLAUDE_TMP_MAX_AGE_S
    total = 0
    for entry in _CLAUDE_TMP.iterdir():
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Mac disk cleanup — dry-run by default.",
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
    p.add_argument("--chats-older-than", type=int, default=30, metavar="DAYS",
                   help="Age threshold for Claude chat pruning (default: 30)")
    p.add_argument("--stale-days", type=int, default=30, metavar="DAYS",
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


def build_report(args: argparse.Namespace, work_dirs: list[Path]) -> list[dict]:
    only = set(args.only.split(",")) - {""} if args.only else set()
    skip = set(args.skip.split(",")) - {""} if args.skip else set()
    dry_run = not args.apply
    level = args.level

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
        size = _measure_brew()
        freed = 0
        if not dry_run and size > 0:
            freed = _apply_brew(level)
        report.append({"target": "brew", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": "brew cleanup -s"})

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

    if active("trash", 1):
        path = HOME / ".Trash"
        size = _du(path)
        freed = 0
        if not dry_run and size > 0:
            freed = _delete_dir(path, dry_run=False)
        report.append({"target": "trash", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": "~/.Trash"})

    if active("claude-tmp", 1):
        size = _clean_claude_tmp(dry_run=True)
        freed = 0
        if not dry_run and size > 0:
            freed = _clean_claude_tmp(dry_run=False)
        report.append({"target": "claude-tmp", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low",
                        "note": f"{_CLAUDE_TMP} entries older than 1d (live session preserved)"})

    # --- Level 2: app caches + logs + Claude ---

    if active("chrome", 2):
        path = HOME / "Library" / "Caches" / "Google" / "Chrome"
        size = _du(path)
        freed = _delete_dir(path, dry_run) if not dry_run else 0
        report.append({"target": "chrome", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": "close Chrome before cleaning"})

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
        claude_paths = [
            HOME / ".claude" / "shell-snapshots",
            HOME / ".claude" / "paste-cache",
            HOME / ".claude" / "cache",
        ]
        size = sum(_du(p) for p in claude_paths)
        freed = 0
        if not dry_run:
            for p in claude_paths:
                freed += _delete_dir(p, dry_run=False)
        report.append({"target": "claude-cache", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": "shell-snapshots, paste-cache, cache dirs"})

    if active("claude-chats", 2):
        size = _prune_claude_chats(args.chats_older_than, dry_run=True)
        freed = 0
        if not dry_run:
            freed = _prune_claude_chats(args.chats_older_than, dry_run=False)
        report.append({"target": "claude-chats", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "low-med",
                        "note": f"sessions older than {args.chats_older_than}d (loses --resume)"})

    if active("docker", 2):
        all_imgs = level >= 3
        size = _measure_docker(all_images=all_imgs)
        freed = 0
        if not dry_run:
            freed = _apply_docker(all_images=all_imgs, include_dangerous=False, yes=args.yes)
        note = ("prune -a -f (no volumes)" if all_imgs else "prune -f (no volumes, not -a)")
        report.append({"target": "docker", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": note})

    # --- Level 3: aggressive ---

    if active("node_modules", 3):
        nm_results = _apply_node_modules(args.stale_days, work_dirs, dry_run=dry_run, yes=args.yes)
        size = sum(r["size"] for r in nm_results)
        freed = sum(r["freed"] for r in nm_results)
        note = f"{len(nm_results)} dirs untouched >{args.stale_days}d; reinstall needed"
        report.append({"target": "node_modules", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": note,
                        "details": [r["path"] for r in nm_results]})

    if active("xcode", 3):
        build_paths = [
            HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
            HOME / "Library" / "Developer" / "Xcode" / "Archives",
        ]
        sim_path = HOME / "Library" / "Developer" / "CoreSimulator" / "Devices"
        size = sum(_du(p) for p in build_paths) + _du(sim_path)
        freed = 0
        if not dry_run and size > 0:
            if args.yes or _confirm(f"  Delete Xcode DerivedData/Archives + prune simulators ({_fmt(size)})?"):
                for p in build_paths:
                    freed += _delete_dir(p, dry_run=False)
                # Official CLI removes only orphaned simulator data; fall back to
                # deleting the dir when xcrun is unavailable.
                if sim_path.exists():
                    before = _du(sim_path)
                    if _has("xcrun"):
                        _run(["xcrun", "simctl", "delete", "unavailable"])
                        freed += max(0, before - _du(sim_path))
                    else:
                        freed += _delete_dir(sim_path, dry_run=False)
        report.append({"target": "xcode", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": "DerivedData + Archives + unavailable simulators"})

    # --- Dangerous ---

    if args.include_dangerous and active("docker-volumes", 3):
        size = _measure_docker(all_images=True)
        freed = 0
        if not dry_run:
            freed = _apply_docker(all_images=True, include_dangerous=True, yes=args.yes)
        report.append({"target": "docker-volumes", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "HIGH", "note": "docker system prune -a --volumes — ALL images + volumes"})

    return report


def main() -> None:
    args = parse_args()
    dry_run = not args.apply

    work_dirs = [Path(args.work_dir).expanduser()] if args.work_dir else _detect_work_dirs()
    _build_allowlist(work_dirs)

    disk = shutil.disk_usage("/")
    free_before = disk.free

    if not args.json_out:
        mode = "DRY-RUN" if dry_run else "APPLY"
        print(f"\n=== disk-janitor [{mode}] level={args.level} ===")
        print(f"Free before: {_fmt(free_before)} / {_fmt(disk.total)}\n")

    report = build_report(args, work_dirs)

    free_after = shutil.disk_usage("/").free
    total_reclaimable = sum(r["reclaimable"] for r in report)
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
