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
import shutil
import subprocess
import sys
import time
from pathlib import Path

HOME = Path.home()

# Common project directory names to probe when --work-dir is not specified.
_WORK_DIR_CANDIDATES = ["Work", "Projects", "projects", "dev", "code", "src", "repos"]


def _detect_work_dirs() -> list[Path]:
    found = [HOME / name for name in _WORK_DIR_CANDIDATES if (HOME / name).is_dir()]
    return found or [HOME]


# Paths outside this allowlist are never deleted, even if a target resolves there.
# Work dirs are added dynamically once args are parsed (see _build_allowlist).
_ALLOWLIST_BASE = [
    HOME / "Library" / "Caches",
    HOME / ".cache",
    HOME / ".npm",
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
    return shutil.which(binary) is not None


def _fmt(b: int) -> str:
    for unit in ("B", "K", "M", "G"):
        if b < 1024:
            return f"{b:.1f}{unit}"
        b //= 1024
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
        if p.is_file() and p.stat().st_mtime < cutoff:
            total += p.stat().st_size
            if not dry_run:
                p.unlink(missing_ok=True)
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
            p = Path(line.split(":", 1)[1].strip())
            if p.exists():
                total += p.stat().st_size if p.is_file() else _du(p)
    if total == 0:
        total = _du(HOME / "Library" / "Caches" / "Homebrew")
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
    _run(cli)
    after = _du(path)
    return max(0, before - after)


def _measure_docker() -> int:
    if not _has("docker"):
        return 0
    result = _run(["docker", "system", "df", "--format", "{{.Size}}"])
    if result.returncode != 0:
        return 0
    total = 0
    for line in result.stdout.splitlines():
        line = line.strip().rstrip("B")
        try:
            if line.endswith("G"):
                total += int(float(line[:-1]) * 1024 ** 3)
            elif line.endswith("M"):
                total += int(float(line[:-1]) * 1024 ** 2)
            elif line.endswith("K"):
                total += int(float(line[:-1]) * 1024)
            elif line.isdigit():
                total += int(line)
        except ValueError:
            pass
    return total


def _apply_docker(include_dangerous: bool, yes: bool) -> int:
    if not _has("docker"):
        return 0
    result = _run(["docker", "info"])
    if result.returncode != 0:
        print("  [SKIP] Docker daemon not running")
        return 0
    before = _measure_docker()
    if include_dangerous:
        if not yes and not _confirm("  docker system prune -a --volumes — destroys ALL unused images and volumes. Continue?"):
            return 0
        _run(["docker", "system", "prune", "-a", "--volumes", "-f"])
    else:
        _run(["docker", "system", "prune", "-f"])
    after = _measure_docker()
    return max(0, before - after)


def _find_stale_node_modules(stale_days: int, work_dirs: list[Path]) -> list[tuple[Path, int]]:
    cutoff = time.time() - stale_days * 86400
    results = []
    seen: set[Path] = set()
    for work in work_dirs:
        if not work.exists():
            continue
        for nm in work.glob("**/node_modules"):
            if nm.resolve() in seen:
                continue
            seen.add(nm.resolve())
            if nm.stat().st_mtime > cutoff:
                continue
            # Guard: the parent project root should be recent enough to be "stale."
            project = nm.parent
            try:
                project_mtime = max(
                    p.stat().st_mtime for p in project.iterdir()
                    if p.name != "node_modules"
                )
            except (StopIteration, ValueError, OSError):
                project_mtime = nm.stat().st_mtime
            if project_mtime > cutoff:
                continue
            if not _in_allowlist(nm):
                continue
            results.append((nm, _du(nm)))
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
    projects_dir = HOME / ".claude" / "projects"
    if not projects_dir.exists():
        return 0
    cutoff = time.time() - days * 86400
    total = 0
    for session in projects_dir.iterdir():
        if not session.is_dir():
            continue
        if session.stat().st_mtime < cutoff:
            size = _du(session)
            total += size
            if not dry_run:
                shutil.rmtree(session, ignore_errors=True)
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
    return p.parse_args()


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

    cli_targets = [
        ("uv", HOME / ".cache" / "uv", ["uv", "cache", "prune"]),
        ("pip", HOME / "Library" / "Caches" / "pip", ["pip", "cache", "purge"]),
        ("npm", HOME / ".npm" / "_cacache", ["npm", "cache", "clean", "--force"]),
        ("bun", HOME / "Library" / "Caches" / "bun", ["bun", "pm", "cache", "rm"]),
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

    if active("trash", 1):
        path = HOME / ".Trash"
        size = _du(path)
        freed = 0
        if not dry_run and size > 0:
            freed = _delete_dir(path, dry_run=False)
        report.append({"target": "trash", "level": 1, "reclaimable": size, "freed": freed,
                        "risk": "low", "note": "~/.Trash"})

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
        size = _measure_docker()
        freed = 0
        if not dry_run:
            freed = _apply_docker(include_dangerous=False, yes=args.yes)
        report.append({"target": "docker", "level": 2, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": "prune -f (no volumes, not -a)"})

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
        xcode_paths = [
            HOME / "Library" / "Developer" / "Xcode" / "DerivedData",
            HOME / "Library" / "Developer" / "Xcode" / "Archives",
            HOME / "Library" / "Developer" / "CoreSimulator" / "Devices",
        ]
        size = sum(_du(p) for p in xcode_paths)
        freed = 0
        if not dry_run:
            for p in xcode_paths:
                freed += _delete_dir(p, dry_run=False)
        report.append({"target": "xcode", "level": 3, "reclaimable": size, "freed": freed,
                        "risk": "med", "note": "DerivedData + Archives + Simulators"})

    # --- Dangerous ---

    if args.include_dangerous and active("docker-volumes", 3):
        size = _measure_docker()
        freed = 0
        if not dry_run:
            freed = _apply_docker(include_dangerous=True, yes=args.yes)
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
