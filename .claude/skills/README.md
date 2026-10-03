# Skills (configs' own)

Only skills that maintain this repo live here, loaded when you work inside `configs`:

| Skill | What it does |
|-------|-------------|
| [config-sync](./config-sync/) | Syncs this repo's hand-edited config with the live machine (status/restore/push/pull) and walks a fresh Mac through restoring it |

Reusable skills live in the sibling `ai-tools` repo (`skills/`). They are not copied here.

## Exposed skills

`.claude/user/skills/` holds per-skill relative symlinks into `ai-tools/skills/`. `sync.py` links that directory as `~/.claude/skills` for the default (personal) profile only. Org profiles (`~/.claude-<org>`) get no global skills; a work repo links what it needs from ai-tools itself.

```bash
# expose another skill to the personal profile
ln -s ../../../../ai-tools/skills/<name> .claude/user/skills/<name>
# hide one
rm .claude/user/skills/<name>
```

Fresh Mac: clone `ai-tools` next to this repo before `sync.py --restore`, otherwise the links dangle (`--status` flags them).

`.claude/user/skills/synced/` is a cache Claude writes for claude.ai account skills. It is git-ignored; ignore it.

`.claude/user/skills/synced/` is machine-generated (Claude Code's claude.ai account-skill sync cache), git-ignored, and a real directory, so `--status` never treats it as an exposed link. Never edit or track it.

The exposed set is disk-janitor, frontend-review, job-fit-assessor, travel-planner. frontend-review was a global skill before the move, so it stays exposed.
