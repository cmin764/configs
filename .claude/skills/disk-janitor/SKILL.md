---
name: disk-janitor
description: >
  Detect reclaimable disk space on macOS and optionally clean it up via a
  tiered Python script. Use this skill whenever the user says "my Mac is full",
  "free up disk space", "what's eating my disk", "clear caches", "clean up
  stale data", "how much space can I recover", "disk cleanup", or any variation
  of wanting to understand or reclaim storage. Always run the dry-run report
  first so the user sees what will be touched before anything is deleted.
  Triggers even when the user just wants to understand disk usage without
  committing to cleanup.
---

# Disk Janitor

Detect and reclaim wasted space on macOS via `scripts/cleanup.py`. The script
is stdlib-only (no deps), dry-run by default, and delegates to each tool's own
CLI for package-manager caches rather than deleting files directly.

---

## Workflow

1. Run the dry-run report first (always):
   ```bash
   python3 .claude/skills/disk-janitor/scripts/cleanup.py --level 2
   ```
2. Show the output to the user. Let them choose a level and confirm targets.
3. Run with `--apply` at the agreed level:
   ```bash
   python3 .claude/skills/disk-janitor/scripts/cleanup.py --level 2 --apply
   ```
4. Report the before/after free-space delta from the script output.

If the user only wants to understand space usage (no cleanup), `--level 3`
dry-run gives the fullest picture without touching anything.

---

## Levels

| Level | What it covers | Risk |
|-------|---------------|------|
| 1 (default) | Package-manager caches via official CLIs: brew, uv, pip, npm, bun; claude-tmp | Low |
| 2 | + Trash, Chrome/JetBrains/IDE caches (incl. Chrome's Application Support cache subdirs), ~/Library/Logs, Claude shell/paste cache, Claude chats older than N days, docker image and builder prune (dangling images and build cache only, stopped containers and tagged images untouched), Teams/Claude-desktop/Discord cache subdirs (login preserved, skipped entirely while the app is running), Claude memory audit (report-only) | Low-med |
| 3 | + Stale node_modules and venvs (projects untouched > N days), Xcode DerivedData and unavailable simulators (Archives kept, they hold shipped-build dSYMs), brew --prune=all, docker container prune and image prune -a (ALL stopped containers and unused images, confirm required), Claude plugin caches: cached node_modules, marketplace `.git` dirs, large tracked binaries (PDFs/zips/media) in marketplace working trees, superseded plugin version dirs, orphaned uv-managed Python installs | Med (rebuild cost) |
| dangerous | docker system prune -a --volumes (double-gated: needs --include-dangerous and explicit confirm) | High |

Trash moved from level 1 to level 2: it's the undo buffer, not a
package-manager cache, so it doesn't belong in the "always safe" tier.

Levels are cumulative. `--apply` alone runs level 1 only; you must pass
`--level N` to go deeper.

---

## Common invocations

```bash
# Dry-run scan: see what's reclaimable at each level
python3 scripts/cleanup.py --level 3

# Apply level 1 only (safe package-manager caches)
python3 scripts/cleanup.py --apply

# Apply levels 1+2
python3 scripts/cleanup.py --level 2 --apply

# Target specific tools only
python3 scripts/cleanup.py --apply --only brew,uv,pip

# Skip a target
python3 scripts/cleanup.py --level 2 --apply --skip docker

# Machine-readable output
python3 scripts/cleanup.py --level 2 --json

# Full cleanup including dangerous docker volumes (explicit confirm required)
python3 scripts/cleanup.py --level 3 --apply --include-dangerous

# Tune age thresholds
python3 scripts/cleanup.py --level 3 --chats-older-than 60 --stale-days 14 --apply

# Override project scan root (default: auto-detects Work/Projects/dev/src/repos under ~)
python3 scripts/cleanup.py --level 3 --work-dir ~/code --apply
```

---

## Safety contract

- Nothing is deleted without `--apply`.
- Delete paths are validated against an allowlist of known cache roots.
- Missing CLIs (brew, uv, docker, etc.) are skipped gracefully.
- Level 3 targets (node_modules per-dir, xcode) and dangerous targets prompt for
  confirmation unless `--yes`.
- Only top-level node_modules of stale projects are deleted, never nested ones.
- Claude chat pruning removes session transcripts only; persistent memory under
  `~/.claude/projects/*/memory/` is never touched.
- claude-tmp only removes entries older than 24h, so the live session survives.
- Docker volumes are never touched except via the explicit `--include-dangerous` path.
- Unknown `--only`/`--skip` names fail fast with the list of valid targets.
- Claude Code profiles (`~/.claude` plus any `~/.claude-*` `CLAUDE_CONFIG_DIR`
  profile) are auto-discovered by globbing: no profile list to keep in sync.
- Teams/Claude-desktop/Discord/Chrome-App-Support targets only ever delete
  literal cache-named subdirs (`Cache`, `Code Cache`, `GPUCache`, …), never
  the whole app support/container tree (login, chat history, and profile
  data are untouched).
- Claude memory (`<profile>/projects/*/memory/`) is only ever reported, never
  deleted, at any level: see `claude-memory` in the target catalog for why.
- uv Python interpreter removal goes through `uv python uninstall`, never a
  raw directory delete, and only fires for a version no venv or `uv tool`
  install references anywhere under the work dirs.
- Plugin version pruning keeps whatever `installed_plugins.json` says is the
  active install, never the numerically highest version dir, since the
  active install can be a git SHA-named directory. A plugin with no manifest
  entry at all is left alone entirely, even with multiple version dirs.
- Work dirs are never added to the allowlist wholesale: only a dir literally
  named `node_modules`, `.venv`, or `venv` under a work dir is ever deletable
  there. Nothing else under `~/Work` (or wherever `--work-dir` points) can be
  touched, even if a bug elsewhere tried to.
- Chrome/Teams/Claude-desktop/Discord cache deletion checks the app isn't
  currently running (`pgrep -x`) before `--apply` touches anything; a running
  app's target is skipped with a note to quit it first. Dry-run still
  measures regardless.
- `claude-cache` skips `shell-snapshots` whenever a `claude` process is
  running, since it's the live session's own snapshot; `paste-cache` and
  `cache` are unaffected.
- Xcode `Archives` is never a target: it holds the dSYMs for shipped builds,
  the only copy, needed to symbolicate crash reports. Only DerivedData and
  unavailable simulators are cleaned.
- A `du` failure on an existing path (e.g. `~/.Trash` blocked by macOS TCC
  for Terminal) is reported as `reclaimable: null` with a Full Disk Access
  note, never silently as "nothing to clean".
- `docker` reports `reclaimable: null` when the daemon isn't running,
  instead of the 0 a stopped daemon would otherwise produce (verified: a
  stopped Docker Desktop silently read as nothing to reclaim despite 15+
  GiB of unused images once it was started).
- `brew`'s report measures with `--prune=all` at level 3, matching what
  the apply step actually runs there; measuring without it understated
  what level 3 removes by roughly 1 GiB on this machine.

---

## Model-tiering note

The cleanup script itself is deterministic stdlib code: extending it with a new
target is Haiku-tier work (just add a target dict entry following the existing
pattern). Classifying the risk level of an unfamiliar cache location requires
judgment about what the tool stores and how expensive a rebuild is; that's
Opus/Fable territory. Codegen against an already-agreed target spec is Sonnet.

---

## Reference

See `references/targets.md` for the full target catalog: paths, levels,
measurement strategies, CLI commands, and risk notes.
