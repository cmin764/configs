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
| **Symlink** | `.zprofile`, `.zshrc`, `.vimrc`, `.gitconfig`, `.gitignore_global` | Repo and machine are the same inode. Nothing to sync, drift is structurally impossible. |
| **Symlink (per Claude profile)** | `.claude/user/CLAUDE.md`, `.claude/user/RTK.md`, `.claude/user/hooks/`, `.claude/skills/` | Same as above, but applied once per Claude Code profile directory: `~/.claude` plus any `~/.claude-<org>` created for per-org account isolation (see restore step 7). A fresh Mac only has `~/.claude`. These are the user's own authored tooling (this repo's skills, hooks, memory files) -- deliberately identical everywhere, unlike plugins/MCP below: there's no personal-vs-work split for skills *you* wrote, only for third-party installs. A project's own `.claude/skills/` (versioned and shared with a team through that project's own repo) is a separate, unrelated layer Claude Code discovers per-project regardless of `CLAUDE_CONFIG_DIR` -- out of scope for this skill entirely, see README's note on skill promotion. |
| **Not synced, deliberately** | `plugins/` and MCP registrations (`.claude.json`) inside each Claude profile | User-scope Claude Code state Claude Code itself keeps per config dir, not per human -- `claude plugin install`/`claude mcp add --scope user` only ever touch whichever `CLAUDE_CONFIG_DIR` is active. Installing a plugin under the personal profile must not make it appear at work and vice versa, so each profile gets its own independent install/registration (step 7's recipe repeats the commands per org) rather than sharing one copy. Costs some duplicate disk for plugins used in both places -- worth it for the isolation. |
| **Copy** | `apps/cursor/settings.json`, `apps/cursor/mcp.json`, `apps/sublime/*`, `apps/docker/daemon.json`, `apps/iterm2/Wandercode.json` | The owning app rewrites its own file, so a symlink would let app noise flow straight into a public repo. Plain overwrite either direction is safe: these files carry no secrets. |
| **Merge (per Claude profile)** | `.claude/user/settings.json` (installs to `<profile>/settings.json`) | Claude Code itself writes to this file (permission grants, plugin state). A plain copy on push would erase legitimate accumulated state; a plain copy on pull would drag that noise into the repo. Deep-merge, repo wins on conflicts, machine-only keys survive a push. Applied per profile, same set as the symlinks above. |
| **`defaults` scalar** | `apps/iterm2/app-prefs.json` (`TabStyleWithAutomaticOption`, i.e. Appearance > Theme) | A handful of app-level `defaults(1)` keys that aren't part of any dynamic profile. Read/written via `defaults read/write com.googlecode.iterm2 <key>` (not a raw plist edit) so cfprefsd stays authoritative instead of racing a running iTerm2. Key list is hardcoded in `sync.py` so a first `--pull` on a machine without the template can still discover them. |

One file needs a fourth treatment: `apps/cursor/cli-config.json` carries
`authInfo` (email, userId, teamId) on the live machine that must never reach a
public repo. `sync.py` drops it (and the `*Cache` blocks) automatically when
pulling; pushing writes the repo's already-clean version as-is.

`apps/iterm2/Wandercode.json` isn't copied from a file at all -- it's re-extracted
from `~/Library/Preferences/com.googlecode.iterm2.plist` via `plistlib`, because
that's a binary plist with ~1300 keys of Sparkle-updater and window-position
junk mixed in. Pull re-exports just the one profile; push drops the extracted
JSON into `DynamicProfiles/`, which iTerm2 picks up live, no restart needed.

A second machine can already carry its own local-only dynamic profile under a
different name, predating this skill -- if it happens to share the repo's
hardcoded Guid (cloned by hand from an earlier machine), iTerm2 reports a
"duplicate Guid" warning on launch after a `--push`. That local profile isn't
managed by this skill: give it a fresh Guid by hand (any UUID, iTerm2 doesn't
care which) rather than touching `Wandercode.json`, then restart iTerm2.

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

`--pull` never auto-merges a Claude profile's `settings.json` back into the repo template.
That file accumulates permission grants and `autoMode.environment` blocks the
harness writes on its own (that's exactly the noise the template was built to
strip out). It prints a diff instead, one dotted path per difference, so a human
decides what's a deliberate setting change worth keeping versus accumulated
cruft. Everything else pulls automatically because it's either low-sensitivity
(Sublime, Docker) or already has its redaction step (Cursor, iTerm2).

## Restoring on a fresh Mac

Order matters; later steps assume earlier ones landed.

**Five things are optional, not default -- ask before installing/adding
them, don't just silently skip or silently include:** `pyenv` (step 13),
JetBrains Toolbox/any JetBrains IDE (step 12), the `tally` MCP server and
the `linear`/`lucid` MCP servers (step 9), and the `vercel` plugin (step 10
-- not in `.claude/user/settings.json`'s `enabledPlugins` at all, not
installed by step 10 either; rarely used, skip it entirely on a fresh
restore and install it fresh with `claude plugin install
vercel@claude-plugins-official` on the rare occasion it's actually needed.
Since `plugins/` is shared across every Claude profile (see the sync table
above), installing it anywhere installs it for every org profile too --
confirmed causing a recurring "enabled but not installed" panel error when
it got auto-installed by Claude Code's own official-marketplace bootstrap
on a fresh profile, so it's now fully uninstalled rather than just
disabled). Each costs real time and disk (or an auth step, or clutters
`/context` with tool defs) if added unnecessarily, and each has a genuine
"maybe I do want this" case (a project pinning an old Python via
`.python-version`, a JetBrains IDE for a specific stack, actually using
Tally forms or Linear/Lucid, doing Vercel-specific work). If an agent is
driving this restore, interview the user on these specifically before
running the corresponding install/add command -- don't infer the answer
from "everything else in the repo gets installed."

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
7. **Per-org Claude Code auth**, if any work directory needs a full separate
   subscription/account rather than the default keychain login. Claude Code
   hashes `CLAUDE_CONFIG_DIR` into a distinct macOS Keychain entry, so
   pointing it at a separate directory gives a fully separate, full-featured
   account -- not a scoped token. (`claude setup-token` /
   `CLAUDE_CODE_OAUTH_TOKEN` looked like the obvious lever here but turned
   out to be a scoped credential that silently drops feature access
   (confirmed: no Fable model access) and can't even be checked --
   `claude auth status` doesn't validate a token against the server -- so
   it's deliberately not used for this.) `.zshrc`'s `chpwd` hook switches
   `CLAUDE_CONFIG_DIR` automatically whenever you're under `~/Work/<org>`
   once the profile directory below exists; no profile directory means that
   org just keeps using the default login, nothing else to edit.

   A `CLAUDE_CONFIG_DIR` only isolates the login itself -- shared config
   (skills/hooks/`CLAUDE.md`/`RTK.md`/settings) needs linking there too, same
   as a fresh Mac's default profile does in step 3. Plugins and MCP
   registrations are Claude Code's own per-profile state, not repo content,
   and deliberately stay separate per org too -- `enabledPlugins` in
   `settings.json` merging in doesn't install anything (same caveat as step
   10), and installing a plugin under one profile must not make it appear in
   another, so each org gets its own independent installs. Full recipe for a
   new org profile (`<org>` = lowercased directory name under `~/Work`):
   ```
   mkdir -p ~/.claude-<org>
   CLAUDE_CONFIG_DIR=~/.claude-<org> claude auth login
   python3 .claude/skills/config-sync/scripts/sync.py --push
   CLAUDE_CONFIG_DIR=~/.claude-<org> claude plugin marketplace add thedotmack/claude-mem
   CLAUDE_CONFIG_DIR=~/.claude-<org> claude plugin marketplace add DietrichGebert/ponytail
   CLAUDE_CONFIG_DIR=~/.claude-<org> claude plugin install claude-mem@thedotmack
   CLAUDE_CONFIG_DIR=~/.claude-<org> claude plugin install ponytail@ponytail
   ```
   Skip the marketplace/install block if this org doesn't need
   claude-mem/ponytail. If it needs `tally`/`linear`/`lucid` MCP too, repeat
   the commands in step 9 with the same `CLAUDE_CONFIG_DIR=~/.claude-<org>`
   prefix -- also per profile, for the same reason.

   **If claude-mem is installed here, it needs its own data dir too, or its
   worker silently bills the wrong account.** claude-mem's worker is a
   machine-wide singleton keyed by data dir (default `~/.claude-mem`,
   port `37701`) that spawns SDK calls billed to whatever
   `CLAUDE_CONFIG_DIR` its own launching env carried -- with no
   `CLAUDE_MEM_DATA_DIR` set, every profile's claude-mem shares one worker,
   and whichever profile happens to boot it first pays for every other
   profile's memory generation until reboot. `.zshrc`'s
   `_claude_config_dir_by_pwd` hook already exports
   `CLAUDE_MEM_DATA_DIR=~/.claude-mem-<org>` alongside `CLAUDE_CONFIG_DIR`
   whenever that directory exists -- create it and give it a distinct
   worker port so the two workers don't collide:
   ```
   mkdir -p ~/.claude-mem-<org>
   cp ~/.claude-mem/settings.json ~/.claude-mem-<org>/settings.json
   python3 -c "
   import json
   p = '$HOME/.claude-mem-<org>/settings.json'
   d = json.load(open(p))
   d['CLAUDE_MEM_DATA_DIR'] = '$HOME/.claude-mem-<org>'
   d['CLAUDE_MEM_WORKER_PORT'] = '37711'
   d['CLAUDE_MEM_QUEUE_REDIS_PREFIX'] = 'claude_mem_37711'
   d['CLAUDE_MEM_TRANSCRIPTS_CONFIG_PATH'] = '$HOME/.claude-mem-<org>/transcript-watch.json'
   json.dump(d, open(p, 'w'), indent=2)
   "
   ```
   Pick a free port per additional org profile (`37711`, `37721`, ...) if
   there's ever more than one.

   **Known gap, not fixed here because it's currently inert:**
   `CLAUDE_MEM_SERVER_URL`/`CLAUDE_MEM_SERVER_BETA_URL` default to a port
   derived from the OS uid (`37877 + uid%100`), not from the data dir --
   every profile on this machine computes the *same* default regardless of
   `CLAUDE_MEM_DATA_DIR`, so if `CLAUDE_MEM_RUNTIME` is ever switched from
   its default `worker` to `server`, two profiles would collide on that
   port the same way the worker did before this fix. Harmless today only
   because nothing listens on it in the default `worker` runtime -- revisit
   if a future claude-mem version defaults to the server runtime, or if you
   deliberately opt into it.

   Existing profiles already sharing one worker
   need this fix too, plus a one-time purge of the other org's project rows
   out of the personal `~/.claude-mem/claude-mem.db` (back up first,
   `DELETE FROM observations/session_summaries/sdk_sessions/user_prompts
   WHERE project = '<name>'`, then `VACUUM`) -- a fresh Mac restore
   following this step never accumulates that commingling in the first
   place. After creating the profile or editing its settings, start a new
   shell (or `source ~/.zshrc` and `cd` out and back into the org
   directory) and start a fresh Claude Code session there before trusting
   `CLAUDE_MEM_DATA_DIR` -- an already-running shell or session keeps its
   env from before the change.

   Cosmetic side effect: `claude doctor` on this new profile will report
   "native installation but config install method is 'not set'" -- the
   native installer only stamps `installMethod` into the default
   `~/.claude/.claude.json`, never into a fresh profile's own
   `<profile>/.claude.json`. Affects auto-update detection messaging only,
   nothing functional. Fix if it bothers you:
   ```
   python3 -c "
   import json
   p = '<profile-dir>/.claude.json'
   d = json.load(open(p))
   d['installMethod'] = 'native'
   json.dump(d, open(p, 'w'), indent=2)
   "
   ```
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

   **`linear`/`lucid` MCP servers are optional too, same treatment.** Reused
   across work orgs rather than tied to one client, so they don't belong in
   any single org's project-local `.mcp.json` -- register them at user scope
   instead:
   ```
   claude mcp add --transport http linear https://mcp.linear.app/mcp --scope user
   claude mcp add --transport http lucid https://mcp.lucid.app/mcp --scope user
   ```
   `--scope user` is itself scoped to whichever `CLAUDE_CONFIG_DIR` is active
   when the command runs -- if a work org has its own profile (step 7),
   repeat both commands with `CLAUDE_CONFIG_DIR=~/.claude-<org>` prefixed to
   register them there too.
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
