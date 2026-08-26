---
name: config-sync
description: Sync hand-edited development configuration between this repo and the live machine, and restore it on a fresh Mac. Use when the user wants to check what's drifted between ~/Work/cmin764/configs and their home directory, wants to push repo config onto the machine or pull machine changes back into the repo, is setting up a new Mac, or mentions rotating the secrets in ~/.zprofile.local. Covers shell/git dotfiles, Claude Code user settings, and app configs (Cursor, iTerm2, Sublime, Docker) -- not the repo's skills themselves, which are just files.
---

# config-sync

This repo is a fresh-Mac bootstrap for hand-edited configuration. The scope rule
is load-bearing: **only configuration a human deliberately edited** goes in here.
Anything a tool accumulated by itself (installed-package lists, plugin caches,
extension inventories) gets regenerated on the new machine instead of committed
-- `brew bundle dump`, `cursor --list-extensions`, and similar exist for that.

`scripts/sync.py` (stdlib only) does the mechanical work. This file is the
judgment layer: what's safe to automate, what needs a human, and the restore
order on a bare machine.

## The three ways a file is kept in sync

| Kind | Files | Why |
|---|---|---|
| **Symlink** | `.zprofile`, `.zshrc`, `.vimrc`, `.gitconfig`, `.gitignore_global`, `.claude/user/CLAUDE.md`, `.claude/user/RTK.md`, `.claude/user/hooks/`, `.claude/skills/` | Repo and machine are the same inode. Nothing to sync, drift is structurally impossible. |
| **Copy** | `apps/cursor/settings.json`, `apps/cursor/mcp.json`, `apps/sublime/*`, `apps/docker/daemon.json`, `apps/iterm2/Wandercode.json` | The owning app rewrites its own file, so a symlink would let app noise flow straight into a public repo. Plain overwrite either direction is safe: these files carry no secrets. |
| **Merge** | `.claude/user/settings.json` (installs to `~/.claude/settings.json`) | Claude Code itself writes to this file (permission grants, plugin state). A plain copy on push would erase legitimate accumulated state; a plain copy on pull would drag that noise into the repo. Deep-merge, repo wins on conflicts, machine-only keys survive a push. |

One file needs a fourth treatment: `apps/cursor/cli-config.json` carries
`authInfo` (email, userId, teamId) on the live machine that must never reach a
public repo. `sync.py` drops it (and the `*Cache` blocks) automatically when
pulling; pushing writes the repo's already-clean version as-is.

`apps/iterm2/Wandercode.json` isn't copied from a file at all -- it's re-extracted
from `~/Library/Preferences/com.googlecode.iterm2.plist` via `plistlib`, because
that's a binary plist with ~1300 keys of Sparkle-updater and window-position
junk mixed in. Pull re-exports just the one profile; push drops the extracted
JSON into `DynamicProfiles/`, which iTerm2 picks up live, no restart needed.

## Commands

```bash
python3 .claude/skills/config-sync/scripts/sync.py            # --status, read-only
python3 .claude/skills/config-sync/scripts/sync.py --restore   # fresh Mac
python3 .claude/skills/config-sync/scripts/sync.py --push      # repo -> machine
python3 .claude/skills/config-sync/scripts/sync.py --pull      # machine -> repo
python3 .claude/skills/config-sync/scripts/sync.py --selftest  # deep_merge/diff asserts
```

All four are idempotent. `--status` never writes anything; run it first.

## What `--pull` deliberately refuses to automate

`--pull` never auto-merges `~/.claude/settings.json` back into the repo template.
That file accumulates permission grants and `autoMode.environment` blocks the
harness writes on its own (that's exactly the noise the template was built to
strip out). It prints a diff instead, one dotted path per difference, so a human
decides what's a deliberate setting change worth keeping versus accumulated
cruft. Everything else pulls automatically because it's either low-sensitivity
(Sublime, Docker) or already has its redaction step (Cursor, iTerm2).

## Restoring on a fresh Mac

Order matters; later steps assume earlier ones landed.

**Four things are optional, not default -- ask before installing/adding/
enabling them, don't just silently skip or silently include:** `pyenv`
(step 13), JetBrains Toolbox/any JetBrains IDE (step 12), the `tally` MCP
server (step 9), and the `vercel` plugin (step 10 -- `enabledPlugins` reads
`false` for it in `.claude/user/settings.json` on purpose; rarely used,
install it but leave it disabled, `claude plugin enable vercel@claude-plugins-official`
turns it on when actually needed). Each costs real time and disk (or an
auth step, or clutters `/context` with tool defs) if added unnecessarily,
and each has a genuine "maybe I do want this" case (a project pinning an
old Python via `.python-version`, a JetBrains IDE for a specific stack,
actually using Tally forms, doing Vercel-specific work). If an agent is
driving this restore, interview the user on these specifically before
running the corresponding install/add/enable command -- don't infer the
answer from
"everything else in the repo gets installed."

1. **Install prerequisites**: Homebrew, then `brew install gh` (git credential
   helper) and whatever else this machine's `brew leaves`/`brew list --cask`
   needs -- not committed here, by the scope rule above.
   Install Claude Code via the **official installer only**, never
   `brew install --cask claude-code`:
   `curl -fsSL https://claude.ai/install.sh | bash` (lands at `~/.local/bin/claude`).
   The cask exists and installs fine, but it fights the installer's own
   self-update mechanism -- `DISABLE_AUTOUPDATER: "1"` in
   `.claude/user/settings.json` turns off silent background updates either
   way, but with the cask installed, `claude update` and `brew upgrade`
   become two competing update paths for the same binary. Update only with
   `claude update`; if a cask install is ever found on a machine
   (`brew list --cask | grep claude-code`), `brew uninstall --cask
   claude-code` then reinstall via the curl command above.
   Install `rtk` (now in homebrew-core: `brew install rtk`; do **not** copy the
   x86_64 binary from an Intel machine's `~/.local/bin/rtk`).
2. **Clone this repo**: `git clone git@github.com:cmin764/configs.git ~/Work/cmin764/configs`.
3. **Restore**: `cd ~/Work/cmin764/configs && python3 .claude/skills/config-sync/scripts/sync.py --restore`.
   Any real file already at a symlink target gets backed up to
   `<name>.pre-config-sync.bak` next to it, never silently overwritten.
4. **Do not run `rtk init -g` on restore.** This repo's `.claude/user/settings.json`
   already declares the `PreToolUse` hook (`rtk hook claude`) and its
   `.claude/user/CLAUDE.md` already imports `@~/.claude/RTK.md` -- step 3's
   merge and symlink land both, so the hook is live the moment restore
   finishes. `rtk init -g` doesn't check for this: it unconditionally
   rewrites `~/.claude/RTK.md` and appends to `~/.claude/CLAUDE.md` with its
   own generic template, and since both are symlinks into this repo, running
   it here destroys the hand-tuned `RTK.md` content through the symlink
   (confirmed by running it on a fresh restore -- it silently replaced the
   full command reference and the "do not re-run" warning itself with rtk's
   stock output). If that ever happens, `git checkout -- .claude/user/RTK.md
   .claude/user/CLAUDE.md` recovers the repo copy.
   Verify instead of initializing: confirm the hook fires (run something
   `RTK.md` lists as intercepted, e.g. `git status`, and see rtk's condensed
   output rather than git's normal output). `rtk init --show` is safe and
   read-only if you want rtk's own diagnostic, but expect it to report the
   global `CLAUDE.md` as "not configured" even when everything works --
   it's checking for the bare `@RTK.md` line its own installer would have
   added, not this repo's `@~/.claude/RTK.md` form; that mismatch is
   expected here and not a problem.
5. **Fill in secrets**: create `~/.zprofile.local` (`chmod 600`) with the six
   keys named in `.zprofile`'s comments (`GITHUB_TOKEN`, `OPENAI_API_KEY`,
   `GEMINI_API_KEY`, `GOOGLE_MAPS_API_KEY`, `TALLY_API_KEY`, `CAL_API_KEY`).
   **Rotate these on the first restore after 2026-08-23** -- they were exposed
   in a Claude Code session transcript while this repo was being rebuilt, so
   treat the old values as burned regardless of which machine you're on.
6. **Per-client git identity**, if any: `cp .gitconfig-local.example
   ~/.gitconfig.local` and fill in the real `includeIf` block. `.gitconfig`
   includes this file unconditionally; git silently skips it if absent, so
   personal machines with no client work need to do nothing here.
7. **Per-org Claude Code auth**, if any work directory needs a subscription
   other than the default keychain login: from inside `~/Work/<org>`, run
   `claude setup-token`, then add the result to `~/.zprofile.local` as
   `export CLAUDE_<ORG>_OAUTH_TOKEN="..."` (org name uppercased, dashes to
   underscores -- `.zshrc`'s `chpwd` hook derives the exact name from the
   directory automatically, nothing to edit there). No token set means that
   directory just keeps using the default login.
8. **iTerm2 globals**: `bash apps/iterm2/globals.sh` once, then restart iTerm2.
9. **`tally` MCP is optional, not default -- ask before adding it.** Like
   pyenv and JetBrains, don't assume it's wanted just because it's
   documented here. If it is:
   ```
   claude mcp add --transport http tally https://api.tally.so/mcp --scope user
   ```
   `--scope user` matters -- `claude mcp add` defaults to `local` (scoped to
   whatever directory you happen to run it from, i.e. this repo checkout),
   not usable from any project. No token needed at add time, but OAuth
   lives in the keychain of the *previous* machine, not this one -- expect
   `claude mcp get tally` to show "Needs authentication" on a fresh Mac.
   Finish it interactively: run `/mcp` inside a Claude Code session and
   authorize `tally` there. Left un-added (or added and left
   unauthenticated), it just shows as disabled in `/mcp` -- harmless
   either way, no need to remove it if you change your mind later.
10. **Register and install the Claude Code plugins.** `enabledPlugins`
    and `extraKnownMarketplaces` in `.claude/user/settings.json` only
    *declare* that `claude-mem` and `ponytail` should be on -- restore's
    merge step does not actually fetch or install them. Do it by hand:
    ```
    claude plugin marketplace add thedotmack/claude-mem
    claude plugin marketplace add DietrichGebert/ponytail
    claude plugin install claude-mem@thedotmack
    claude plugin install ponytail@ponytail
    ```
    `claude plugin list` should then show both as `enabled`. Two more
    things worth knowing before expecting the statusline badges to go
    green:
    - **claude-mem's hooks need a JS runtime already on `PATH`** (its
      `SessionStart` hook invokes `node .../bun-runner.js`) -- if this
      machine hasn't reached the Node/nvm/Bun step yet, the worker will
      fail to start and `statusLine`'s `[MEM]` badge will read
      `[MEM:DOWN]` until it has. Not a bug, just an ordering dependency
      worth doing the toolchain step first, or re-checking after.
    - **Both plugins only fully activate on a fresh `SessionStart`**
      (claude-mem spawns its worker there; ponytail's mode-tracker hook
      writes the flag file its statusline badge reads). If you install
      them mid-session, restart Claude Code once before judging whether
      the statusline is broken.
11. **Verify**: open a new shell (`echo $PATH` should start with
   `~/.local/bin`), `gh auth login`, then `gh auth status` and a `git fetch` on
   a private repo to confirm the credential helper resolves `gh` via `PATH`
   rather than the Intel-only `/usr/local/bin/gh` this repo used to hardcode.
   Start Claude Code outside this repo and confirm `/disk-janitor`
   autocompletes (proves the skills symlink worked) and `/status` shows
   `autoMode` active (it's a user-scope key, dead if the settings file ever
   ends up back at project scope).
12. **GUI apps**, `brew install --cask` for each, one at a time, config file
    validated (diff against `apps/<tool>/`) before moving to the next:
    ```
    brew install --cask cursor
    brew install --cask sublime-text
    brew install --cask docker
    ```
    - `docker` needs `sudo` for `docker-credential-osxkeychain` under
      `/usr/local/bin` -- it prompts for a password interactively, so this
      one can't run unattended/non-interactively.
    - Cursor's `apps/cursor/cli-config.json` pins a specific `modelId` --
      open Cursor once and confirm it still resolves in the model picker;
      Cursor rotates model aliases over time and this repo doesn't track
      that automatically.
    - Cursor's chat model picker (which models are toggled on/off) lives in
      `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
      (a SQLite DB, `cursor/initialModelState` key) -- app-accumulated
      state, not a hand-edited config, so it's out of scope for this repo
      per the scope rule (README.md) and doesn't sync. Toggle these on by
      hand in Settings > Models, everything else off: **Cursor Grok 4.6,
      Composer 2.5, GPT-5.6 Sol** (the pinned CLI model above), **Codex
      5.3, Gemini 3.1 Pro**. `Auto` stays on regardless, it's not a model
      choice.
    - `jetbrains-toolbox` (`.zprofile`'s `path+=(...)` entry for its
      `scripts/` dir is still there, harmless when the app isn't
      installed -- zsh doesn't error on a nonexistent PATH entry) is
      **not** part of the default install; only add it when a JetBrains
      IDE is actually needed. It needs one manual launch-and-click-through
      before `~/Library/Application Support/JetBrains/Toolbox/scripts`
      exists, which is what that PATH entry points at.
13. **Dev toolchains**, in any order, `pyenv` deliberately excluded (this
    repo's Python workflow is `uv`-only; both `.zprofile` and `.zshrc` guard
    their pyenv lines behind existence checks, so skipping it causes no
    shell errors):
    ```
    brew install openjdk go nvm uv
    ```
    Then, since `nvm`'s formula doesn't manage a Node version for you:
    ```
    nvm install --lts
    ```
    watch its own log line ("Now using node ...") land, not just the exit
    code -- in one fresh shell run `nvm install --lts`, in the *next* fresh
    shell confirm `node --version`/`npm --version`, since nvm's default-alias
    autoload only applies to shells started after the install.
    For Bun, use the official installer, **not** `brew install bun`
    (`.zprofile`/`.zshrc` already export `BUN_INSTALL`/`PATH` and source
    `~/.bun/_bun` completions):
    ```
    curl -fsSL https://bun.sh/install | bash
    ```
    Its installer appends its own `BUN_INSTALL`/PATH/completions block
    straight to `~/.zshrc` -- which is a symlink into this repo. That block
    is 100% redundant with what's already there, and it hardcodes an
    absolute `/Users/<you>/.bun/_bun` path (exactly what CI's
    hardcoded-path check flags). Check `git status` in this repo right
    after running the installer and `git checkout -- .zshrc` if it added
    anything.
    Verify all five in a **login + interactive** shell (`zsh -li -c
    '...'`, matching how a real terminal window starts) -- a plain
    `zsh -l` won't source `.zshrc` (nvm/bun live partly there) and a plain
    `zsh -i` won't source `.zprofile` (Java/Go/Bun's PATH exports live
    there), so testing with only one or the other gives false negatives.
14. **Restart Claude Code once** after step 13. The MCP servers and plugin
    hooks that shell out to `node` (claude-mem's MCP entry, its `SessionStart`
    worker spawn) were resolved against whatever `PATH` the *currently
    running* Claude Code session started with -- if that session predates
    the toolchain install, `claude mcp list` and the statusline's `[MEM]`
    badge will look broken even though everything is actually fine. A fresh
    session picks up the new `PATH`.

## Apple Silicon vs Intel

Originally bootstrapped on an Intel Mac (`/usr/local` brew prefix); validated
end-to-end on Apple Silicon (`/opt/homebrew` prefix) during the Wandercode
restore. `.zprofile` handles both prefixes, and `brew install rtk` in
particular now bottles cleanly on Apple Silicon (seconds) where it used to
fall back to a 30+ minute source build on the Intel machine -- see `RTK.md`.
If something still assumes `/usr/local` unconditionally, that's a bug --
grep the repo for the literal string and fix it rather than adding a third
special case.

## When something doesn't fit this skill's model

- **A new app config to track**: add it to `apps/<tool>/`, then add one line to
  the right list in `sync.py` (`SYMLINKS`, `COPIES`, `TRIMMED_COPIES`, or
  `MERGES`, per the table above). Symlink only if the app never rewrites the
  file itself.
- **A skill to promote from a project repo**: not this skill's job. See
  `README.md`'s note on skill promotion; it's a deliberate, occasional decision,
  not something to automate into a sync loop.
- **Auditing whether something is genuinely hand-edited or accumulated noise**:
  that's a judgment call, not a mechanical rule, which is why it isn't in CI.
  Do it here, when you're about to `--pull`, by reading the diff `--status`
  prints before deciding to commit it.
