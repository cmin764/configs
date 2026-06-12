# Disk Janitor: Target Catalog

Full reference for every cleanup target. Each entry shows: path(s), level,
measurement strategy, apply action, risk, and notes.

---

## Level 1 — Package-manager caches (official CLIs)

| Target | Path(s) | Measure | Apply CLI | Risk |
|--------|---------|---------|-----------|------|
| brew | `~/Library/Caches/Homebrew` | `brew cleanup -n 2>&1` (parse output) | `brew cleanup -s` | Low |
| uv | `~/.cache/uv` | `du -sh` on path | `uv cache prune` | Low |
| pip | `~/Library/Caches/pip` | `du -sh` on path | `pip cache purge` | Low |
| npm | `~/.npm/_cacache` | `du -sh` on path | `npm cache clean --force` | Low |
| bun | `~/Library/Caches/bun` | `du -sh` on path | `bun pm cache rm` | Low |
| trash | `~/.Trash` | `du -sh` on path | `rm -rf ~/.Trash/*` | Low |
| claude-tmp | `/private/tmp/claude-<uid>/` | `du -sh` on path | delete dir | Low — CC session task/tool buffers; only clean when Claude Code is not running |

---

## Level 2 — App/browser/IDE caches + logs + Claude data

| Target | Path(s) | Measure | Apply action | Risk |
|--------|---------|---------|--------------|------|
| chrome | `~/Library/Caches/Google/Chrome` | `du -sh` | delete dir | Low — browser refetches; close Chrome first |
| jetbrains | `~/Library/Caches/JetBrains/` | `du -sh` | delete subdirs | Low-med — IDE reindexes on next open |
| logs | `~/Library/Logs` | `du -sh` | delete files older than --stale-days | Low |
| claude-cache | `~/.claude/shell-snapshots`, `~/.claude/paste-cache`, `~/.claude/cache` | `du -sh` each | delete dirs | Low |
| claude-chats | `~/.claude/projects/*/` | count dirs, find mtime < --chats-older-than | delete matching project dirs | Low-med — loses --resume for old sessions |
| docker | daemon socket | `docker system df` | `docker system prune -f` (no -a, no --volumes) | Med — removes dangling images, stopped containers, build cache |

### Claude chat pruning detail

Each subdirectory under `~/.claude/projects/` is one conversation session.
The script checks the mtime of the session directory and deletes those older
than `--chats-older-than` days (default 30). Only the project dirs are removed;
the `~/.claude/` root and tool configs are never touched.

---

## Level 3 — Aggressive (rebuild/reinstall cost)

| Target | Path(s) | Measure | Apply action | Risk |
|--------|---------|---------|--------------|------|
| node_modules | `<work-dir>/**/node_modules` (depth ≤ 4) | `du -sh` per dir; filter by project last-touched mtime | delete `node_modules/` dir only (never the project root) | Med — `npm/bun install` needed before next run |
| xcode | `~/Library/Developer/Xcode/DerivedData`, `~/Library/Developer/Xcode/Archives`, `~/Library/Developer/CoreSimulator/Devices` | `du -sh` each | delete contents | Med — Xcode rebuilds; simulators re-downloaded |
| brew-prune-all | `~/Library/Caches/Homebrew` | `brew cleanup -n --prune=all` | `brew cleanup -s --prune=all` | Med — removes all cached bottles, not just expired |

### node_modules safety constraints

- Only `node_modules` subdirectories are ever deleted, never the project root.
- Projects touched within `--stale-days` (default 30) are skipped.
- The scan is capped at 4 directory levels deep under the work dir to avoid
  surprises in deeply nested monorepos.
- A project is considered "touched" if any file in the project root (excluding
  node_modules itself) has mtime within the stale window.

---

## Dangerous — double-gated

| Target | Apply CLI | Gates |
|--------|-----------|-------|
| docker-volumes | `docker system prune -a --volumes` | `--include-dangerous` flag AND interactive confirm (bypassed only with `--yes`) |

This removes ALL unused images (not just dangling), ALL stopped containers,
ALL build cache, and ALL unused volumes. Irreversible without a registry push.
Never runs as part of a normal level 3 sweep.

---

## Measurement strategies

**du-based:** `du -sk <path>` → bytes. Used when the path is a plain directory.
Skipped if path doesn't exist.

**CLI dry-run parsing:** `brew cleanup -n` outputs lines like
`Would remove: ~/Library/Caches/Homebrew/downloads/...` — the script counts
total bytes from that output. `docker system df` gives structured size data.

**mtime filtering:** for node_modules and claude chats, the script walks the
filesystem and filters by `os.stat().st_mtime`.

---

## Allowlist (safety)

Deletes are only permitted inside these roots. Any resolved path outside the
allowlist raises an error and skips the target:

```
/private/tmp/claude-<uid>/  (or /tmp/claude-<uid>/ on Linux)
~/Library/Caches/
~/.cache/
~/.npm/
~/.Trash/
~/.claude/projects/
~/.claude/shell-snapshots
~/.claude/paste-cache
~/.claude/cache
<work-dir>/  (node_modules subdirs only; auto-detected or set via --work-dir)
~/Library/Logs/
~/Library/Developer/Xcode/DerivedData
~/Library/Developer/Xcode/Archives
~/Library/Developer/CoreSimulator/Devices
```
