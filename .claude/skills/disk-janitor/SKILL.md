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

1. Run the dry-run report first — always:
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
| 1 (default) | Package-manager caches via official CLIs: brew, uv, pip, npm, bun | Low |
| 2 | + Chrome/JetBrains/IDE caches, ~/Library/Logs, Claude shell/paste cache, Claude chats older than N days, docker prune (no volumes) | Low-med |
| 3 | + Stale node_modules (projects untouched > N days), Xcode artifacts, brew --prune=all | Med (rebuild cost) |
| dangerous | docker system prune -a --volumes — double-gated: needs --include-dangerous + explicit confirm | High |

Levels are cumulative. `--apply` alone runs level 1 only; you must pass
`--level N` to go deeper.

---

## Common invocations

```bash
# Dry-run scan — see what's reclaimable at each level
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
- Level 3 and dangerous targets prompt for confirmation unless `--yes`.
- Docker volumes are never touched except via the explicit `--include-dangerous` path.

---

## Model-tiering note

The cleanup script itself is deterministic stdlib code — extending it with a new
target is Haiku-tier work (just add a target dict entry following the existing
pattern). Classifying the risk level of an unfamiliar cache location requires
judgment about what the tool stores and how expensive a rebuild is; that's
Opus/Fable territory. Codegen against an already-agreed target spec is Sonnet.

---

## Reference

See `references/targets.md` for the full target catalog: paths, levels,
measurement strategies, CLI commands, and risk notes.
