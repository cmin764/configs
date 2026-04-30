# RTK - Rust Token Killer

**Usage**: Token-optimized CLI proxy (60-90% savings on dev operations)

The PreToolUse hook in `~/.claude/settings.json` intercepts every Bash call and rewrites it transparently. You never need to type `rtk` manually except for the meta commands below.

## Meta Commands (always use rtk directly)

```bash
rtk gain              # Token savings analytics
rtk gain --history    # Per-command history with savings
rtk session           # Adoption rate across recent Claude Code sessions
rtk discover          # Scan last 30 days of history for missed savings
rtk cc-economics      # Spending (ccusage) vs savings (rtk) side-by-side
rtk proxy <cmd>       # Run without filtering but still track usage
```

## Commands RTK Handles Automatically (via hook)

| Raw command | Rewritten to | Typical savings |
|-------------|-------------|----------------|
| `grep -n …` | `rtk grep` | ~40% |
| `cat -n …` | `rtk read` | ~17% |
| `git commit …` | `rtk git commit` | ~93% |
| `git status` | `rtk git status` | ~55% |
| `ls -la …` | `rtk ls` | ~65-75% |
| `find …` | `rtk find` | moderate |
| `gh run …` | `rtk gh` | moderate |
| `curl -s …` | `rtk curl` | moderate |
| `wc -l …` | `rtk wc` | moderate |
| `pip3 install …` | `rtk pip` | moderate |

## Explicit RTK Commands Worth Reaching For

These are not auto-intercepted — use them deliberately when the situation fits:

**Build and typecheck output (replaces `| tail -N` workarounds):**
```bash
rtk err bun run build       # errors/warnings only; prints [ok] on clean build
rtk err bun run typecheck   # same for tsc; [ok] costs near-zero tokens
rtk tsc --noEmit            # direct tsc alternative with grouped error output
rtk err bun run lint        # eslint errors only
```

**Diffs:**
```bash
rtk diff file1 file2        # ultra-condensed local diff (changed lines only)
gh pr diff > /tmp/pr.diff && rtk diff /tmp/pr.diff  # condensed PR diff via temp file
```

**Any verbose command:**
```bash
rtk summary <cmd>           # 2-line heuristic summary of any command's output
rtk err <cmd>               # errors/warnings only from any command
```

## Commands RTK Does NOT Handle — Minimize Output Manually

**`gh pr diff` (1.5% compression — diffs are incompressible):** prefer:
```bash
gh pr diff --stat                  # which files changed, ~10x smaller
gh pr view --json files            # structured file list
gh pr diff -- path/to/file.ts      # full diff for one file only when needed
```

**`python3 <<EOF` / inline scripts:** output is unfiltered. Write results to a temp file and `rtk read` it, or keep `print()` calls minimal.

**`bun install` / `bun remove` / `bun pm`:** package manager noise. Pipe through `| tail -5` or use `rtk err bun install` to surface only failures.

## Do Not Re-initialize

`rtk init -g` was already run globally. The hook in `~/.claude/settings.json` and `~/.claude/RTK.md` are the authoritative setup.

- Do not run `rtk init -g` again -- overwrites the customized RTK.md.
- Do not run `rtk init` (project-level) -- global hook already intercepts everything; local init only adds a redundant hook entry and a redundant RTK.md.
- `rtk init --show` is safe (read-only, shows current config).
- `rtk init --uninstall` is safe if you need to remove artifacts.

## Name Collision Warning

If `rtk gain` fails, you may have `reachingforthejack/rtk` (Rust Type Kit) installed instead of this tool.
