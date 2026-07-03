# configs

Personal Mac bootstrap repo. Clone it on a clean machine, copy the configs into
place, and you get a working shell, git, and Claude Code setup in minutes instead
of an afternoon of re-configuring everything from memory.

Files are plain copies, not symlinks. The repo is the source of truth for
everything shareable; a couple of files intentionally diverge on each machine
(secrets, machine-local permissions). See [Keeping things in sync](#keeping-things-in-sync).

## What's inside

| File / dir | Goes to | What it is |
|---|---|---|
| `.zprofile` | `~/.zprofile` | PATH and env setup: Homebrew, Java, Go, pyenv, Bun, NVM, JetBrains Toolbox. Secrets section at the bottom stays local-only |
| `.zshrc` | `~/.zshrc` | Aliases, daily-cached completions, pyenv/NVM/Bun shell integration, Claude Code auto-updater off |
| `.vimrc` | `~/.vimrc` | Minimal vim: line numbers, search highlight, 4-space tabs, no swap files |
| `.gitconfig` | `~/.gitconfig` | Identity plus `gh` as the GitHub credential helper |
| `.gitignore_global` | `~/.gitignore_global` | Global ignores: JetBrains metadata, Copilot sessions, Claude Code worktrees and local settings |
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | Coding standards, communication style, git and tooling rules for every Claude Code session |
| `.claude/settings.json` | `~/.claude/settings.json` | Claude Code harness config: permission allowlist, RTK PreToolUse hook, claude-mem pid guard hooks, plugins, env |
| `.claude/RTK.md` | `~/.claude/RTK.md` | RTK (token-optimizing CLI proxy) usage guide, referenced by CLAUDE.md |
| `.claude/hooks/` | `~/.claude/hooks/` | Standalone hook scripts referenced from settings.json (currently: claude-mem stale-pid cleanup) |
| `.claude/skills/` | `~/.claude/skills/` | Reusable Claude Code skills, see below |
| `claude-style.txt` | n/a | "Live Edge" writing voice guide, source material for the style rules in CLAUDE.md |
| `cursor-settings.json` | Cursor settings | Cursor IDE preferences |
| `system-design.excalidrawlib` | Excalidraw | Component library for system design diagrams (import via Excalidraw's library menu) |

### Skills

Four skills under `.claude/skills/`, each a folder with a `SKILL.md` entrypoint:

- **disk-janitor**: finds and reclaims disk space on macOS via a tiered,
  stdlib-only Python script. Always dry-runs first.
- **frontend-review**: stack-aware pre-merge review for React/Next.js projects
  (a11y, SEO, security, perf, TS, Tailwind).
- **job-fit-assessor**: scores a candidate profile against a job description,
  outputs an interactive React artifact.
- **travel-planner**: turns raw trip data into a printable itinerary table plus
  a Leaflet route map.

[`.claude/skills/README.md`](.claude/skills/README.md) covers usage details,
adding new skills, and packaging skills as `.skill` files for Claude Chat.

## Fresh Mac setup

1. **Prerequisites.** Install [Homebrew](https://brew.sh), then:

   ```bash
   brew install gh pyenv nvm
   curl -fsSL https://bun.sh/install | bash
   gh auth login
   ```

   Install [Claude Code](https://claude.com/claude-code) and RTK, the Rust
   Token Killer (the `rtk` binary must land in `~/.local/bin`; the
   settings.json hook calls it on every Bash invocation). Careful when
   searching for it: `reachingforthejack/rtk` is a different tool.

2. **Clone and copy into place.**

   ```bash
   git clone git@github.com:cmin764/configs.git ~/Work/cmin764/configs
   cd ~/Work/cmin764/configs

   cp .zprofile .zshrc .vimrc .gitconfig .gitignore_global ~/
   mkdir -p ~/.claude
   cp CLAUDE.md .claude/settings.json .claude/RTK.md ~/.claude/
   cp -R .claude/skills ~/.claude/skills
   ```

3. **Wire the global gitignore.**

   ```bash
   git config --global core.excludesfile ~/.gitignore_global
   ```

4. **Initialize RTK once.** On a brand-new machine run `rtk init -g` to install
   the global hook. Never re-run it on a machine that's already set up: it
   overwrites the customized `~/.claude/RTK.md` (see that file for details).

5. **Re-add secrets.** Open `~/.zprofile` and fill in the tokens section at the
   bottom (`GITHUB_TOKEN`, `ANTHROPIC_API_KEY`, ...). These never go in the repo.

6. **Restart the shell**, open Claude Code anywhere, and confirm the skills show
   up (`/disk-janitor` should autocomplete).

Cursor: paste `cursor-settings.json` into Cursor's user settings JSON.
Excalidraw: import `system-design.excalidrawlib` through the library sidebar.

## Keeping things in sync

There's no sync script. The model is deliberate copies in both directions:

- **Must stay identical** between repo and home: `.zshrc`, `.vimrc`,
  `.gitconfig`, `.gitignore_global`, `CLAUDE.md`, `RTK.md`, `skills/`, `hooks/`.
- **Intentionally diverge** per machine:
  - `~/.zprofile` carries real secrets; the repo copy keeps the section as
    commented placeholders. Sync everything above the secrets divider.
  - `~/.claude/settings.json` accumulates machine-local permission grants.
    Port over only the rules worth keeping everywhere.
- **Never committed**: `.claude/settings.local.json` (gitignored) and anything
  containing a token.

The maintenance loop: tweak a config in `~` as you work, then diff against the
repo and copy the shareable part back:

```bash
cd ~/Work/cmin764/configs
for f in .zshrc .zprofile .vimrc .gitconfig .gitignore_global; do
  diff -q ~/$f $f
done
diff ~/.claude/settings.json .claude/settings.json
diff -r ~/.claude/skills .claude/skills
diff -r ~/.claude/hooks .claude/hooks
```

Anything that drifted: copy it in, review with `git diff`, commit. Same flow in
reverse after a `git pull` on another machine.

## Maintenance habits

- A config change that survives a week belongs in the repo. Commit it before
  the next machine swap makes you reconstruct it.
- Skills: edit in the repo, test in a Claude Code session, copy to
  `~/.claude/skills`, commit. Claude Chat needs a manual repackage and
  re-upload after every change.
- `CLAUDE.md` edits are high-stakes (every session loads it). Keep them
  surgical and reviewed.
- Audit `~/.zprofile`'s secrets section occasionally; it's the one file where
  repo and reality are supposed to differ.
