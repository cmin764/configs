# configs

Personal Mac bootstrap repo, public on GitHub. Clone it on a clean machine,
run one script, and you get a working shell, git, Claude Code, and app setup
back instead of an afternoon of reconstructing it from memory.

**Scope rule**: only configuration a human deliberately edited goes in here.
Anything a tool accumulated on its own -- installed packages, browser
extensions, plugin manifests -- gets regenerated on the new machine instead of
committed. `brew bundle dump`, `cursor --list-extensions`, and similar exist
for exactly that; duplicating their output here would just be one more place
for it to go stale.

## Quick start on a new Mac

```bash
# Prerequisites: Homebrew, then gh (git credential helper), Claude Code, rtk
brew install gh rtk
gh auth login

git clone git@github.com:cmin764/configs.git ~/Work/cmin764/configs
cd ~/Work/cmin764/configs
python3 .claude/skills/config-sync/scripts/sync.py --restore
```

Then fill in `~/.zprofile.local` with real API keys (the six names are
commented in `.zprofile`) and, if this machine does client work under a
different git email, `cp .gitconfig-local.example ~/.gitconfig.local` and fill
that in too. Full restore order, including iTerm2 and the one MCP server:
`.claude/skills/config-sync/SKILL.md`, or just ask Claude Code to run
`/config-sync` once it's installed.

## What's inside

| Path | Installs to | What it is |
|---|---|---|
| `.zprofile` `.zshrc` `.vimrc` `.gitconfig` `.gitignore_global` | `~/` (symlinked) | Shell env, aliases, vim, git identity, global ignores |
| `.gitconfig-local.example` | n/a, copy to `~/.gitconfig.local` | Per-client git email override, included unconditionally, gitignored if it doesn't exist |
| `.claude/user/CLAUDE.md` | `~/.claude/CLAUDE.md` (symlinked) | Coding standards, communication style, tooling rules for every Claude Code session |
| `.claude/user/RTK.md` | `~/.claude/RTK.md` (symlinked) | RTK (token-optimizing CLI proxy) usage guide |
| `.claude/user/settings.json` | `~/.claude/settings.json` (merged, never overwritten) | Harness config: permissions, hooks, plugins, `autoMode` |
| `.claude/user/hooks/` | `~/.claude/hooks/` (symlinked) | Hook scripts referenced from `settings.json` |
| `.claude/skills/` | `~/.claude/skills/` (symlinked) | Reusable skills, see [`.claude/skills/README.md`](.claude/skills/README.md) |
| `apps/cursor/` | Cursor's settings, MCP config, and CLI agent config | |
| `apps/iterm2/` | iTerm2 profile + a `defaults write` script for globals | |
| `apps/sublime/`, `apps/docker/` | One small preferences file each | |
| `reference/` | n/a | Source material referenced from `CLAUDE.md` or imported into a design tool, not installed anywhere |

Everything under `.claude/user/` and `apps/` is written by
`.claude/skills/config-sync/scripts/sync.py`, never edited in place on a
machine and copied back by hand -- see that skill for the sync model and why
some files are symlinks and others are merged.

## Keeping it current

Run `/config-sync` (or `python3 .claude/skills/config-sync/scripts/sync.py
--pull`) after a settings change you want to keep, and review what it flags
before committing -- some of it is deliberately not auto-pulled. `AGENTS.md`
has the invariants for editing this repo; `CI` (`.github/workflows/`) checks
the mechanical stuff on every PR (no secrets, no machine-specific paths,
configs still parse); genuinely judging "hand-edited vs. accumulated noise"
stays a human-in-the-loop step in the skill, not something CI enforces.

Promoting a skill from a project repo into `.claude/skills/` here is a
separate, occasional decision -- worth doing when something proves reusable
across projects, not something to automate into the sync loop.
