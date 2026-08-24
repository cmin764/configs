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

If `rtk gain` fails, you may have "Rust Type Kit" (a different `rtk` on crates.io) installed instead of this tool.

## Upgrading

Currently on v0.45.0, installed to `~/.local/bin/rtk` via the official installer:

```bash
curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
```

It downloads the release tarball for your platform, verifies it against `checksums.txt`
(SHA-256), and swaps the binary at `~/.local/bin/rtk`. There is no `rtk update`/`self-update`
subcommand — check `rtk --version` against the latest GitHub release manually.

`brew install rtk` also exists (this tool is in `homebrew-core`), but on this Mac it has no
bottle for the installed macOS/Homebrew tier and falls back to building from source, pulling
in `llvm` as a dependency (a 30+ minute build for a small CLI). Stick with the installer script
above unless a future bottle covers this machine.

## Fixed Bug — `git log` After a Merge (resolved in v0.42.0)

Previously (through v0.37.2): `rtk git log` / `rtk git log --graph` — even `rtk git log HEAD -N` —
could drop the merge commit entirely right after a merge and show a non-ancestor commit as if it
were HEAD. Fixed upstream in v0.42.0 ("honor explicit -n N limit for git log on merge commits") and
verified against v0.44.1 with a synthetic merge repo — `rtk git log --graph` output now matches
native `git log --graph` exactly. No workaround needed on v0.42.0+; if you ever see suspicious
`rtk git log` output again, sanity-check with `/usr/bin/git log --oneline --graph -10` and confirm
you're actually running a patched version (`rtk --version`).
