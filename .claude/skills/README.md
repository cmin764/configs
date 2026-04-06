# Skills

Custom Claude skills for this repo.

Skills follow the [Agent Skills open standard](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills).
Each skill is a folder under `.claude/skills/` with a `SKILL.md` entrypoint and
optional `references/`, `scripts/`, and `assets/` subdirectories.

---

## How auto-discovery works

When you open Claude Code in this repo, it scans `.claude/skills/` at startup and
loads the `name` and `description` from every skill's YAML frontmatter into its
system prompt. When you ask for something that matches a skill's description, Claude
loads the full `SKILL.md` and any referenced files on demand. You can also invoke
any skill directly with `/skill-name`.

No config required. Clone the repo, open Claude Code, done.

---

## Available skills

| Skill | What it does |
|-------|-------------|
| [job-fit-assessor](./job-fit-assessor/) | Assesses a candidate profile against any JD, producing a scored, filterable React artifact with per-requirement annotations |

---

## Using job-fit-assessor

### In Claude Code

Pass a profile directory and a JD — Claude does the rest:

```
Assess my fit against this role: https://example.com/jobs/principal-engineer
My profile files are at: ~/personal/career/
```

Or with the shorthand flag:

```
/job-fit-assessor --profile-dir ~/personal/career/ https://example.com/jobs/principal-engineer
```

If you don't pass a profile path, Claude scans the current working directory for
profile files (useful when you open Claude Code inside a repo that contains your CV,
codex, etc.).

You can also mix sources:

```
Assess my fit against this role: [URL]
My profile dir: ~/career/
Here's my CV: [attach file]
And recruiter notes: [paste]
```

Claude merges everything it finds.

### In Claude Chat (claude.ai)

Upload the `.skill` file (see packaging below) via **Settings > Skills > Add skill**.
Then in any conversation:

```
Assess my fit against this role: [URL or paste]
```

Without local files, point Claude at your GitHub profile or attach your CV directly.

---

## Packaging a skill for Claude Chat

Skills need to be packaged into a `.skill` file before uploading to Claude Chat.

### One-time setup

```bash
# Clone Anthropic's skills repo anywhere convenient
git clone https://github.com/anthropics/skills.git ~/tools/anthropic-skills
```

### Package a skill

```bash
cd ~/tools/anthropic-skills/skills/skill-creator
python3 -m scripts.package_skill /path/to/repo/.claude/skills/job-fit-assessor
# outputs: job-fit-assessor.skill in the current directory
# note: requires pyyaml — install once with: pip3 install pyyaml
```

### Upload to Claude Chat

1. Go to [claude.ai](https://claude.ai) > **Settings > Skills**
2. Click **Add skill**
3. Upload `job-fit-assessor.skill`

The skill is now available in every Claude Chat conversation until you remove it.

---

## Updating a skill

Edit in the repo, test in Claude Code, then repackage and re-upload for Chat.

```bash
# 1. Edit
vim .claude/skills/job-fit-assessor/SKILL.md

# 2. Test locally — open Claude Code and run an assessment

# 3. Commit
git add .claude/skills/job-fit-assessor/
git commit -m "update job-fit-assessor: [what changed]"
git push

# 4. Repackage
cd ~/tools/anthropic-skills/skills/skill-creator
python3 -m scripts.package_skill /path/to/repo/.claude/skills/job-fit-assessor

# 5. In claude.ai Settings > Skills: remove the old version, upload the new .skill file
```

Claude Chat requires a manual re-upload after every update. There is no auto-sync.
That's a current platform limitation, not something you can work around.

---

## Adding a new skill

```bash
mkdir -p .claude/skills/my-new-skill/references

cat > .claude/skills/my-new-skill/SKILL.md << 'SKILLEOF'
---
name: my-new-skill
description: >
  [Third-person. What it does and when to trigger it.
  Include specific trigger phrases.]
---

# My New Skill

[Instructions here]
SKILLEOF
```

Commit and push. Claude Code picks it up immediately on next session.

---

## Skill structure reference

```
.claude/skills/
└── skill-name/
    ├── SKILL.md          ← required: YAML frontmatter + instructions
    ├── references/       ← optional: docs loaded on demand
    │   └── *.md
    ├── scripts/          ← optional: executable code Claude can run
    │   └── *.py / *.sh
    └── assets/           ← optional: templates, fonts, static files
```

**SKILL.md frontmatter requirements:**

```yaml
---
name: skill-name          # lowercase, hyphens only, no spaces
description: >            # third-person; what it does AND when to trigger
  ...
---
```

**Progressive disclosure:** only `name` and `description` load at startup (system
prompt cost). The `SKILL.md` body loads when Claude decides the skill is relevant.
Reference files load only when explicitly needed. Keep `SKILL.md` under ~300 lines
and move detail into `references/`.

---

## Security note

Skill files committed to a public repo are publicly readable. Don't include API
keys, client details, or private context in any skill file.
