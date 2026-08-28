---
name: config-sync
description: Sync hand-edited development configuration between this repo and the live machine, and restore it on a fresh Mac. Use when the user wants to check what's drifted between ~/Work/cmin764/configs and their home directory, wants to push repo config onto the machine or pull machine changes back into the repo, is setting up a new Mac, or mentions rotating the secrets in ~/.zprofile.local. Covers shell/git dotfiles, Claude Code user settings, and app configs (Cursor, Codex, iTerm2, Sublime, Docker) -- not the repo's skills themselves, which are just files.
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
| **Not synced, deliberately** | `plugins/` and MCP registrations (`.claude.json`) inside each Claude profile; Codex's `config.toml` `[marketplaces.*]`/`[plugins.*]`/`[projects.*]` blocks | User-scope Claude Code state Claude Code itself keeps per config dir, not per human -- `claude plugin install`/`claude mcp add --scope user` only ever touch whichever `CLAUDE_CONFIG_DIR` is active. Installing a plugin under the personal profile must not make it appear at work and vice versa, so each profile gets its own independent install/registration (step 7's recipe repeats the commands per org) rather than sharing one copy. Costs some duplicate disk for plugins used in both places -- worth it for the isolation. Codex's `config.toml` mixes this same kind of self-managed state (marketplaces, plugin installs, per-project trust) with a handful of genuinely hand-edited scalars (`model`, `[shell_environment_policy]`, `[desktop]` prefs) in one TOML file -- `sync.py` is stdlib-only and has no TOML writer, and splitting the file cleanly would need one, so the whole file is left untracked rather than force a partial fit. `apps/codex/hooks.json` (Codex's actual hand-authored hook wiring, the TOML file's one purely-hand-edited chunk that's easy to isolate) is tracked on its own, same as `.claude/user/settings.json`'s `hooks` block. |

**Where `.claude.json` actually lives is not consistent across profiles, and that's not a bug.**
For the *default* profile (`CLAUDE_CONFIG_DIR=~/.claude`), Claude Code writes `.claude.json` at
`$HOME/.claude.json` -- a sibling of `~/.claude/`, not a file inside it. That's a legacy layout
from before `CLAUDE_CONFIG_DIR` was configurable at all. For any *other* profile (`~/.claude-<org>`
from step 7), Claude Code instead puts `.claude.json` inside that profile's own directory
(`~/.claude-<org>/.claude.json`) -- because every profile shares the same `$HOME`, and writing
every org's project registry/OAuth/MCP state to one shared `$HOME/.claude.json` would let them
clobber each other, defeating the whole point of per-org profiles.
Practical effect: when hunting for an org profile's project entries, history, or `lastSessionId`,
look inside `~/.claude-<org>/.claude.json`, never at `$HOME/.claude.json` (that one belongs to the
default profile only, regardless of which profile you're currently `cd`'d into).
| **Copy** | `apps/cursor/settings.json`, `apps/cursor/mcp.json`, `apps/codex/hooks.json`, `apps/sublime/*`, `apps/docker/daemon.json`, `apps/iterm2/Wandercode.json` | The owning app rewrites its own file, so a symlink would let app noise flow straight into a public repo. Plain overwrite either direction is safe: these files carry no secrets. |
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

## Cursor and Codex can't get per-org profile isolation the way the terminal does

`.zshrc`'s `chpwd` hook (step 7) swaps `CLAUDE_CONFIG_DIR`/`CLAUDE_MEM_DATA_DIR`
per shell based on `$PWD` -- that only works because a terminal re-sources
`.zshrc` on every `cd`. Cursor and Codex are GUI apps launched from the Dock,
Spotlight, or a recent-projects list, not `cursor .`/`codex .` from an
already-`cd`'d shell, so their own process env is whatever it was at launch --
never workspace-aware, regardless of which project window is focused. Their
integrated terminal panels *do* re-source `.zshrc` and show the right
`CLAUDE_CONFIG_DIR` for the open project, but that panel is a separate process
from the app's own MCP/plugin host, which is what actually calls claude-mem.

Consequence: neither app's claude-mem integration can be made to follow the
open project's org profile via env-var inference -- there is no dynamic
`${env:CLAUDE_CONFIG_DIR}` trick that works here, so don't build one. Even
launching via CLI (`cursor .` from an already-`cd`'d shell) doesn't help:
both apps use a single-instance model, so once one window is open the whole
app's env is fixed at whichever launch started it, regardless of which
directory a later `cursor .` was run from -- confirmed by inspecting a
running Cursor process's env directly (no `CLAUDE_CONFIG_DIR` in it at all,
just `HOME`).

That ruled out making Cursor's `claude-mem` MCP entry profile-aware, which
left pinning it to the default profile as the only alternative -- but pinning
turned out to be worse than it looks: claude-mem's worker doesn't just
resolve a script path from `CLAUDE_CONFIG_DIR`, it authenticates as whatever
account that config dir logs into (`CLAUDE_MEM_CLAUDE_AUTH_METHOD:
"subscription"`, piggybacking the Claude Code login, not a separate API key).
Pinned to the default profile, every org-project session in Cursor would
silently bill claude-mem's summarization calls to the *personal* subscription
and write those observations into the *personal* `~/.claude-mem` DB --
exactly the cross-account commingling the whole `~/.claude-mem-<org>` split
(see step 7) exists to prevent, just via a path that's easy to forget
carries memory/billing side effects at all.

So `claude-mem` is **not present** in `apps/cursor/mcp.json` -- removed
rather than pinned. That turned out not to be the whole fix (see below).

**Cursor has a second, separate integration path that `mcp.json` doesn't
touch at all.** Beyond the hand-authored `mcp.json`, Cursor has its own
native "Plugins" feature -- an account-level list of installed Claude Code
Plugin-ecosystem plugins, tracked in `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`
(key `cursor.plugins.installedIds.<team>|<workspace>`, one entry per
workspace plus a `no-workspace` default, all listing the same numeric plugin
IDs). This is what actually spawns `Cursor Helper: mcp-process` running
claude-mem's `mcp-server.cjs` under the namespace `plugin-claude-mem-mcp-search`
-- confirmed live: talking to the *personal* profile's worker on port
`37701`, regardless of which project window is open, same billing/data leak
as above. Editing `apps/cursor/mcp.json` never touched this; it's a
completely independent install path, not repo-tracked (same "app-accumulated
state" category as the Cursor model-picker toggle, see step 12), and Cursor
doesn't expose a CLI or a readable local catalog mapping those numeric IDs
to plugin names -- config-sync can't safely identify or remove one of them by
ID without risking disabling the wrong plugin (vercel/linear/slack/github
are legitimately wanted). **Must be removed by hand: Cursor Settings ->
search "Plugins" -> find claude-mem -> Uninstall.** Do this with Cursor fully
quit and reopened after, so a stale in-memory process doesn't linger.

Codex's claude-mem integration was a native plugin too
(`config.toml`'s `[marketplaces.claude-mem-local]` /
`[plugins."claude-mem@claude-mem-local"]`), not an MCP entry -- and its own
bundled hooks (cached under `~/.codex/plugins/cache/claude-mem-local/`, not
repo-tracked) carried the same leak as Cursor's, worse:
`SessionStart`/`UserPromptSubmit`/`PreToolUse`/`PostToolUse`/`Stop` all
independently resolved `${CLAUDE_CONFIG_DIR:-$HOME/.claude}` themselves, and
`PostToolUse`/`Stop` are the ones that actually spend money (memory writes,
LLM summarization). Removed entirely rather than left disabled: both
`config.toml` blocks deleted and `~/.codex/plugins/cache/claude-mem-local/`
removed from disk (all live, machine-only edits -- the file isn't
repo-tracked, see above).

`apps/codex/hooks.json` used to also wire the `claude-mem-pid-guard.sh`
housekeeping hook (symlinked from `.claude/user/hooks/`, same script Claude
Code's profiles use) into Codex's `SessionStart`/`UserPromptSubmit`. Pulled
once the plugin above was removed: that hook exists solely to unstick
claude-mem's worker before a stale PID file makes it skip respawning, and
Codex never spawns that worker at all now, so it had nothing left to guard.

**claude-mem is now fully out of both Cursor and Codex, but stays on for
Claude Code CLI** -- uninstalled from the default `~/.claude` profile only
(`claude plugin uninstall claude-mem@thedotmack` under
`CLAUDE_CONFIG_DIR=~/.claude`; the personal worker on port `37701` was also
killed directly), left installed and correctly isolated on any
`~/.claude-<org>` profile that wants it. `.claude/user/settings.json`'s
`enabledPlugins.claude-mem@thedotmack: true` is left as `true` on purpose --
it's the shared template merged into every profile, and per the documented
behavior (step 10) it never auto-installs anything on its own, so it staying
`true` doesn't resurrect claude-mem on the personal profile; a real
reinstall there would need an explicit `claude plugin install` again.

If a specific org project genuinely needs Cursor or Codex to talk to that
org's claude-mem/plugin install, the fix is a workspace-local override
(Cursor supports a project-level `.cursor/mcp.json` that merges with the
global one) committed to *that project's own repo* -- not here, since it would
need to name the org to route correctly, which this public repo's scope rule
forbids.

## Commands

```bash
python3 .claude/skills/config-sync/scripts/sync.py            # --status, read-only
python3 .claude/skills/config-sync/scripts/sync.py --restore   # fresh Mac
python3 .claude/skills/config-sync/scripts/sync.py --push      # repo -> machine
python3 .claude/skills/config-sync/scripts/sync.py --pull      # machine -> repo
python3 .claude/skills/config-sync/scripts/sync.py --selftest  # deep_merge/diff asserts
```

All four are idempotent. `--status` never writes anything; run it first.
It also flags any `~/.claude-mem-<org>` profile still sharing its data
dir, worker port, or server-url with the default profile as `[LEAK RISK]`
-- see step 7's claude-mem isolation block, which is what this is
checking for. That's a static, point-in-time check; `claude-mem-pid-guard.sh`
(symlinked into every profile's `hooks/`, wired into `SessionStart` and
`UserPromptSubmit` in `.claude/user/settings.json`) backs it up at
runtime -- on every prompt it asks the worker actually listening on this
profile's port for its own `/api/health`, and warns loudly if that
worker's `workerPath` (its source file, which lives under
`<profile>/plugins/cache/...`) doesn't belong to this session's
`CLAUDE_CONFIG_DIR`. That catches the case `--status` can't: a stale
worker process from before a settings fix, or a port collision that
happens transiently between two profiles' cold starts. Both guards have
tests CI runs on every push: `--selftest` drives the `--status` check
against a throwaway HOME, and `.github/scripts/test_claude_mem_pid_guard.sh`
runs the real hook with `security`/`curl` replaced by PATH shims, one case
per leak state (default logged in, foreign worker, injected token, stale
pidfile, port resolution order) -- so nothing here needs a live worker or a
real keychain to be verified.

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

   # claude-mem is installed but NOT yet isolated -- run this in the SAME
   # sitting, never as a separate/optional step, or its worker silently
   # shares the default ~/.claude-mem data dir/port and bills the wrong
   # account (confirmed live 2026-08-28: an org profile went unpatched
   # between install and this block, and its worker ran against the
   # default port for hours before anyone noticed). claude-mem's worker is
   # a machine-wide singleton keyed by data dir (default `~/.claude-mem`,
   # port `37701`) that spawns SDK calls billed to whatever
   # `CLAUDE_CONFIG_DIR` its own launching env carried -- with no
   # `CLAUDE_MEM_DATA_DIR` set, every profile's claude-mem shares one
   # worker, and whichever profile boots it first pays for every other
   # profile's memory generation until reboot. `.zshrc`'s
   # `_claude_config_dir_by_pwd` hook already exports
   # `CLAUDE_MEM_DATA_DIR=~/.claude-mem-<org>` alongside `CLAUDE_CONFIG_DIR`
   # whenever this directory exists -- pick a free port per additional org
   # profile (37711, 37721, ...) if there's ever more than one:
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
   d['CLAUDE_MEM_SERVER_URL'] = 'http://127.0.0.1:37911'
   d['CLAUDE_MEM_SERVER_BETA_URL'] = 'http://127.0.0.1:37911'
   json.dump(d, open(p, 'w'), indent=2)
   "
   ```
   The `SERVER_URL`/`SERVER_BETA_URL` pair is patched too even though it's
   currently inert (`CLAUDE_MEM_RUNTIME` defaults to `worker`, and nothing
   listens on that port in worker mode) -- both default to a port derived
   from the OS uid (`37877 + uid%100`), not from the data dir, so *every*
   profile on this machine computes the identical default regardless of
   `CLAUDE_MEM_DATA_DIR`. Patching it now costs nothing and removes a
   collision that would otherwise wait silently for the day `CLAUDE_MEM_RUNTIME`
   switches to `server` (a future claude-mem default, or a deliberate opt-in).
   Pick a free port block per additional org profile (`377{1,2,...}1` for
   worker, `379{1,2,...}1` for server) if there's ever more than one.

   **Ports and data dirs isolate the data, not the billing.** Where a
   worker's SDK calls get billed is decided by what OAuth token its `claude`
   child ends up with, and claude-mem's pre-flight gets that wrong for org
   profiles: the darwin branch of its keychain reader (in
   `worker-service.cjs`) runs `security find-generic-password -s "Claude
   Code-credentials"` -- the **unsuffixed** service name, which is always the
   default `~/.claude` login (Claude Code stores org profiles under `Claude
   Code-credentials-<sha256(CLAUDE_CONFIG_DIR)[:8]>`, confirmed by inspecting
   the keychain on 2026-08-28). Whatever it finds there it injects as
   `CLAUDE_CODE_OAUTH_TOKEN` into every SDK child, and Claude Code honours
   that env var over its own per-profile keychain lookup. Net effect: a
   logged-in default profile silently pays for *every* org profile's memory
   generation, with perfect port/data-dir isolation and a correct
   `CLAUDE_CONFIG_DIR`. When the default profile is logged out the lookup
   fails, claude-mem "proceeds without token", and the `claude` child does
   its own suffixed lookup -- correct, but only by absence. No claude-mem
   setting disables the pre-flight, but a credential in
   `~/.claude-mem-<org>/.env` makes it return *before* the keychain lookup.
   Two credentials work there:
   - **`ANTHROPIC_AUTH_TOKEN=<output of CLAUDE_CONFIG_DIR=~/.claude-<org>
     claude setup-token>`** -- keeps billing on the org's Claude
     subscription. Verified 2026-08-28: the worker reported
     `authMethod: "Gateway auth token (from ~/.claude-mem/.env)"` (that
     path is a hardcoded label upstream -- the file it actually read is the
     org data dir's, the default one didn't exist), stored real
     observations, and kept doing so with a planted default-profile login
     in the keychain. Setup-tokens expire after roughly a year and can't be
     validated server-side, so the pid-guard hook also surfaces claude-mem's
     own `observer-health.json` failure counter -- an expired token shows up
     as "N consecutive SDK failures" on the next prompt instead of silently
     dead memory.
   - **`ANTHROPIC_API_KEY=<Console key>`** -- metered API billing on
     whichever Console org issued it (prepaid credits required). The
     verifiable option when the client has a Console org and wants memory
     generation on its own invoice.

   Create the file in the same sitting as the rest of the isolation block:
   ```
   umask 077 && printf 'ANTHROPIC_AUTH_TOKEN=%s\n' "$(CLAUDE_CONFIG_DIR=~/.claude-<org> claude setup-token)" > ~/.claude-mem-<org>/.env
   ```
   then kill that org's worker so it respawns reading it, and confirm
   `curl -s localhost:<port>/api/health` reports a "Gateway auth token"
   (or "API key") auth method rather than "Claude Code OAuth token".

   **Policy until it's fixed upstream: every org profile that runs
   claude-mem either carries its own `.env` credential, or the default
   profile stays logged out** (`CLAUDE_CONFIG_DIR=~/.claude claude auth
   logout`). Two guards make a violation loud instead of silent, and both
   know about `.env`: `sync.py --status` prints `[isolated] .../.env carries
   its own credential` per protected org and `[LEAK RISK]` when the
   unsuffixed keychain entry exists alongside an unprotected one;
   `claude-mem-pid-guard.sh` re-checks both on every prompt and additionally
   reads the live worker's `/api/health` `ai.authMethod` -- "(env, ...)"
   there means a default-profile token was actually injected, and the hook
   names the PID to kill.

   Skip the whole block (marketplace/install AND the isolation patch right
   after it) if this org doesn't need claude-mem/ponytail -- but never
   install claude-mem without immediately running its isolation patch.
   `python3 .claude/skills/config-sync/scripts/sync.py --status` flags any
   `~/.claude-mem-<org>` still sharing the default's data dir/port/server-url
   as `[LEAK RISK]`, so a skipped patch doesn't stay silent. If this org needs
   `tally`/`linear`/`lucid` MCP too, repeat the commands in step 9 with the
   same `CLAUDE_CONFIG_DIR=~/.claude-<org>` prefix -- also per profile, for
   the same reason.

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
  file itself. If the file mixes hand-edited scalars with the app's own
  accumulated state (installs, per-project trust, caches) the way Codex's
  `config.toml` does, don't force the whole file into one bucket -- pull out
  just the hand-edited part if it's cleanly separable (see `apps/codex/hooks.json`),
  or leave the whole thing untracked if it isn't.
- **A skill to promote from a project repo**: not this skill's job. See
  `README.md`'s note on skill promotion; it's a deliberate, occasional decision,
  not something to automate into a sync loop.
- **Auditing whether something is genuinely hand-edited or accumulated noise**:
  that's a judgment call, not a mechanical rule, which is why it isn't in CI.
  Do it here, when you're about to `--pull`, by reading the diff `--status`
  prints before deciding to commit it.
