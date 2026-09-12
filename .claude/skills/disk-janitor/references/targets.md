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
| teams | `~/Library/Containers/com.microsoft.teams2`, `~/Library/Group Containers/UBF8T346G9.com.microsoft.teams` | sum of matched cache subdirs (`_find_electron_cache_dirs`) | delete matched subdirs only | Low — literal cache dirnames only (`Cache`, `Code Cache`, `GPUCache`, …); login/session state lives elsewhere in the container and is untouched |
| claude-desktop | `~/Library/Application Support/Claude` | sum of matched cache subdirs | delete matched subdirs only | Low — same cache-dirname allowlist; chat history/settings and `vm_bundles` (sandbox images, usually the largest item in this tree) are untouched |
| discord | `~/Library/Application Support/discord` | sum of matched cache subdirs | delete matched subdirs only | Low — same pattern; login preserved |
| claude-memory | `<profile>/projects/*/memory/` for every profile | `du -sh` each memory dir + newest mtime | **report-only, never deletes** | Info — decoding a project's live path from its encoded dirname is ambiguous (verified: every encoded dir on this machine still had a live project), and memory content doesn't go stale by age; surfaced for manual review only |

### `chrome` at level 2 also covers Application Support

Beyond `~/Library/Caches/Google/Chrome` (whole-dir delete), `chrome` also runs
`_find_electron_cache_dirs` under `~/Library/Application Support/Google/Chrome`
to catch per-profile `Service Worker/CacheStorage`, `Code Cache`, `GPUCache`,
and `component_crx_cache` — cache mixed into the same tree as bookmarks,
extensions, and cookies, which are never touched.

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
| plugin-marketplace-binaries | files under `<profile>/plugins/marketplaces/**` matching `.pdf/.zip/.dmg/.mp4/.mov`, ≥1MB | file size | confirm prompt, then delete file | Med — upstream repo content, not needed to run the plugin; **not durable**, see note below |
| plugin-old-versions | `<profile>/plugins/cache/<vendor>/<plugin>/<version>/` where more than one version dir exists | `du -sh` per superseded version dir | confirm prompt, then delete dir | Low — only the highest version is ever used by the plugin runtime; verified against a real duplicate (`thedotmack/claude-mem` 13.16.1 alongside 13.17.1, 482M) |
| venv | top-level `<work-dir>/**/.venv` or `venv` (must contain `pyvenv.cfg`, depth ≤ 4, never nested) | `du -sh` per dir; filter by project last-touched mtime | delete the venv dir only (never the project root) | Med — same staleness contract as `node_modules`; `uv sync`/`pip install` needed before next run |
| uv-python-orphans | `uv python dir`-reported interpreter dirs not referenced by any `.venv/pyvenv.cfg` or `uv tool dir` venv | `du -sh` per install dir | `uv python uninstall <version>` (delegated CLI, not a raw delete) | Low — a version is only flagged if `uv python dir`/`uv python list --only-installed` both succeed and no venv anywhere under the work dirs (or `uv tool dir`) points at it |

### Plugin-cache targets: verified, not just assumed

- **`.git` removal self-heals.** Tested against two real marketplaces
  (`ponytail`, and `thedotmack` at 128M): `claude plugin marketplace update
  <name>` detects the missing `.git`, logs "Found stale directory, cleaning
  up and re-cloning", and re-clones without manual intervention. No local
  edits are ever expected in a marketplace clone, so there's nothing to lose.
- **Cached `node_modules` are dev-only, confirmed via `package.json`.** The
  475M of tree-sitter grammar packages found in one profile's `claude-mem`
  cache all live under `devDependencies`, not `dependencies` — verified by
  reading the marketplace's `package.json` directly, not inferred. The same
  plugin's cache in the main profile ships with *no* `node_modules` at all
  (compiled/bundled at install time), which is the expected end state; the
  475M copy was leftover dev-install cruft from that profile, not a runtime
  dependency. The vercel plugin's compiled `hooks/*.mjs` were separately
  confirmed to import only Node builtins (`fs`, `path`, `crypto`, …), so
  losing its `node_modules` doesn't touch anything the hook actually runs.
- **`plugin-marketplace-binaries` is a reclaim window, not a permanent
  fix — by design.** These files are tracked in the marketplace's default
  branch upstream (confirmed: a `.git` re-clone brings them straight back
  alongside the rest of the repo). Deleting them only holds until the next
  `marketplace update`. That's an accepted tradeoff, not a bug: running
  disk-janitor periodically reclaims the space each time it accumulates,
  the same way brew/npm/pip caches are never "permanently" empty either.
  Report-only was considered and rejected — the user wants the space back
  now, refreshed cost be damned.

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
~/Library/Containers/com.microsoft.teams2
~/Library/Group Containers/UBF8T346G9.com.microsoft.teams
~/Library/Application Support/Claude
~/Library/Application Support/discord
~/Library/Application Support/Google/Chrome
```

---

## Docker.raw: apparent vs. actual size is not a separate reclaim path

`docker system df` and Finder can both show Docker Desktop's sparse
`Docker.raw` VM disk at a large "apparent" size (its provisioned cap) while
`du -h` reports a much smaller "actual" blocks-in-use figure — e.g. 128G
apparent vs. 17G actual is normal on a moderately active Docker install. The
gap is sparse-file accounting, not extra junk sitting on disk; it's already
fully addressed by the `docker`/`docker-volumes` targets above (image/build
cache pruning), not something to hunt for separately.

## Flagged but not built: `.codex`, `.local`, `.nvm`, wallpaper cache

A home-directory sweep found `~/.codex` (~1.2G), `~/.local` (~1.1G), and
`~/.nvm` (~222M) as non-trivial, unaudited dirs, and macOS's own
`com.apple.wallpaper*` dynamic-wallpaper asset cache (~2G across
`~/Library/Application Support/com.apple.wallpaper` and
`~/Library/Containers/com.apple.wallpaper.agent`). None of these got a
target: the first three have unverified internal structure (cache vs.
config/auth — the same diligence bar the plugin-cache targets went through
before their delete logic was written), and the wallpaper cache is an
Apple-managed system container with a live agent process, a different risk
class than a browser or Electron app cache. Revisit if one of these grows
large enough to be worth the verification work.
