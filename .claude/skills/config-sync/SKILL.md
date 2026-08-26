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

1. **Install prerequisites**: Homebrew, then `brew install gh` (git credential
   helper) and whatever else this machine's `brew leaves`/`brew list --cask`
   needs -- not committed here, by the scope rule above. Install Claude Code.
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
9. **`claude mcp add`** the one hand-added MCP server (no token needed, OAuth
   lives in the keychain):
   ```
   claude mcp add --transport http tally https://api.tally.so/mcp
   ```
10. **Register and install the two Claude Code plugins.** `enabledPlugins`
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

## Apple Silicon vs Intel

This repo was last rebuilt on an Intel Mac (`/usr/local` brew prefix). `.zprofile`
handles both prefixes. If something still assumes `/usr/local`, that's a bug --
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
