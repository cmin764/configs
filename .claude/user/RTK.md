# RTK - Rust Token Killer

Token-optimized CLI proxy. The PreToolUse hook in `~/.claude/settings.json`
(`rtk hook claude`) rewrites every Bash call transparently. You never type
`rtk` yourself except for the commands below.

## Truncated output

Filtered output states its own recovery path. Read the full thing with
`rtk recall <hash>` (`--grep <regex>`, `--lines N`, `--from N`, `--full`,
`--list`). Re-run as `rtk proxy <cmd>` only when a result is empty despite
expected output, contradicts its exit code, or is garbled.

## Meta commands (always use rtk directly)

```bash
rtk gain              # Token savings analytics (--history for per-command)
rtk session           # Adoption rate across recent Claude Code sessions
rtk discover          # Scan last 30 days of history for missed savings
rtk cc-economics      # Spending (ccusage) vs savings (rtk)
rtk proxy <cmd>       # Run unfiltered, still tracked
rtk init --show       # Read-only diagnostic (see below)
```

## Explicit commands worth reaching for

Not auto-intercepted, use them deliberately:

```bash
rtk err <cmd>               # errors/warnings only; prints [ok] on clean runs
rtk tsc --noEmit            # tsc with grouped errors
rtk diff file1 file2        # changed lines only
rtk summary <cmd>           # 2-line heuristic summary of any command
```

Diffs don't compress. For PRs prefer `gh pr diff --stat`, then one file at a
time with `gh pr diff -- path`. Inline `python3 <<EOF` output is unfiltered:
keep `print()` minimal or write to a temp file and `rtk read` it.

## Do not re-initialize

`rtk init -g` was already run and then hand-tuned. Running it again
overwrites this file. Don't run `rtk init` (project level) either: the global
hook already covers everything. `rtk init --show` is safe; it reports the
global `CLAUDE.md` as "not configured" because it looks for a bare `@RTK.md`
import and this repo uses `@~/.claude/RTK.md`. That mismatch is expected.

If `rtk gain` fails, the wrong `rtk` is installed (`reachingforthejack/rtk`,
"Rust Type Kit"). Install the right one with `brew install rtk`.
