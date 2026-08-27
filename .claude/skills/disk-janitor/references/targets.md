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
| bun | `~/.bun/install/cache` | `du -sh` on path | delete dir directly (`bun pm cache rm` requires a project context) | Low |
| trash | `~/.Trash` | `du -sh` on path | `rm -rf ~/.Trash/*` | Low |
| claude-tmp | `/private/tmp/claude-<uid>/` | sum entries older than 24h | delete only entries older than 24h | Low — CC session task/tool buffers; live sessions preserved by the age gate |

---

## Level 2 — App/browser/IDE caches + logs + Claude data

| Target | Path(s) | Measure | Apply action | Risk |
|--------|---------|---------|--------------|------|
| chrome | `~/Library/Caches/Google/Chrome` | `du -sh` | delete dir | Low — browser refetches; close Chrome first |
| jetbrains | `~/Library/Caches/JetBrains/` | `du -sh` | delete subdirs | Low-med — IDE reindexes on next open |
| logs | `~/Library/Logs` | `du -sh` | delete files older than --stale-days | Low |
| claude-cache | `~/.claude/shell-snapshots`, `~/.claude/paste-cache`, `~/.claude/cache` | `du -sh` each | delete dirs | Low |
| claude-chats | `~/.claude/projects/*/<session>.jsonl` + matching session subdir | sum session files with mtime < --chats-older-than | delete session files and their subdirs | Low-med — loses --resume for old sessions; memory never touched |
| docker | daemon socket | dangling images + stopped containers + build cache (tagged images excluded) | `docker system prune -f` (no -a, no --volumes) | Med — removes dangling images, stopped containers, build cache; tagged images untouched |

### Claude chat pruning detail

Each directory under `~/.claude/projects/` is one *project*, holding session
transcript `.jsonl` files, per-session subdirs (tool results), and a persistent
`memory/` dir. The script deletes only session files (and the subdir with the
same name) older than `--chats-older-than` days (default 30). The project dirs
themselves, the `memory/` dirs, and tool configs are never touched.

---

## Level 3 — Aggressive (rebuild/reinstall cost)

| Target | Path(s) | Measure | Apply action | Risk |
|--------|---------|---------|--------------|------|
| node_modules | top-level `<work-dir>/**/node_modules` (depth ≤ 4, never nested) | `du -sh` per dir; filter by project last-touched mtime | delete `node_modules/` dir only (never the project root) | Med — `npm/bun install` needed before next run |
| xcode | `~/Library/Developer/Xcode/DerivedData`, `~/Library/Developer/Xcode/Archives`, `~/Library/Developer/CoreSimulator/Devices` | `du -sh` each | confirm prompt, then delete DerivedData/Archives; simulators via `xcrun simctl delete unavailable` | Med — Xcode rebuilds; only orphaned simulators removed |
| brew-prune-all | `~/Library/Caches/Homebrew` | `brew cleanup -n --prune=all` | `brew cleanup -s --prune=all` | Med — removes all cached bottles, not just expired |
| docker (at level 3) | daemon socket | `docker system df` Images RECLAIMABLE | `docker system prune -a -f` (no --volumes) — requires confirm | Med-high — removes ALL unused images including tagged ones; re-pull needed |
| plugin-node-modules | `<profile>/plugins/cache/**/node_modules` (depth ≤ 4) for every discovered profile | `du -sh` per dir | confirm prompt, then delete dir | Med — rebuilt automatically on next plugin run |
| plugin-marketplace-git | `<profile>/plugins/marketplaces/*/.git` for every discovered profile | `du -sh` per dir | confirm prompt, then delete dir | Med — re-cloned on next `claude plugin marketplace update` |
| plugin-marketplace-binaries | files under `<profile>/plugins/marketplaces/**` matching `.pdf/.zip/.dmg/.mp4/.mov`, ≥1MB | file size | confirm prompt, then delete file | Med — upstream repo content, not needed to run the plugin; re-fetched if the marketplace is updated |

### node_modules safety constraints

- Only `node_modules` subdirectories are ever deleted, never the project root.
- Nested `node_modules` (inside another `node_modules`) are never matched;
  deleting one would corrupt an active project's dependency tree.
- Projects touched within `--stale-days` (default 30) are skipped.
- The scan is capped at 4 directory levels deep under the work dir and skips
  hidden directories.
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
`Would remove: ~/Library/Caches/Homebrew/downloads/... (1.2MB)`; the script
strips the size suffix and sizes each path. Docker uses the RECLAIMABLE column
of `docker system df`, not total size.

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
~/.bun/install/cache/
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
<profile>/plugins/cache/     (for ~/.claude and every ~/.claude-* profile)
<profile>/plugins/marketplaces/
```
