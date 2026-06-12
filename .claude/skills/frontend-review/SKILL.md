---
name: frontend-review
description: >
  Stack-aware frontend code review for any React or Next.js project. Detects the
  project's stack (Next.js App Router, Vite SPA, react-router, Tailwind v3/v4,
  shadcn/ui, framer-motion) and applies only the matching rules from a unified
  checklist covering accessibility (WCAG 2.2 AA), routing, SEO, security,
  performance, TypeScript, Tailwind, component structure, and code quality.
  Use when self-reviewing changes before merge, auditing a frontend codebase, or
  when the user says "review my frontend", "audit this React app", "check this
  branch before merge", or "frontend review". Diff mode by default; pass `full`
  to audit the whole codebase. Fixes critical findings by default; tier the fix
  pass with `--fix all` or `--fix none`.
argument-hint: "[full] [--fix all|none]"
allowed-tools: [Read, Glob, Grep, Bash, Edit]
---

# Frontend Review

Self-review of a React/Next.js frontend before merge. A project-local
`frontend-review` skill, if present, takes precedence over this one.

## Arguments

- No arguments: **diff mode**, review files changed on the current branch vs the default branch, fix 🔴 Critical findings after reporting.
- `full`: **full mode**, audit the entire codebase.
- `--fix all`: also apply 🟡 Important and 🔵 Suggestion fixes.
- `--fix none`: report only, change nothing.

---

## Step 0: Detect the stack

Read `package.json`, the lockfile, and the project's `CLAUDE.md` (and
`docs/dev-guide.md` or similar, if CLAUDE.md points to one). Build a stack
profile; it gates which checklist sections apply:

| Signal | How to detect |
|--------|---------------|
| Framework | `next` dep + `app/` dir = Next.js App Router; `app/` absent = Pages Router; `vite` dep = Vite SPA |
| Router | `react-router-dom` dep (note major version) vs Next built-in |
| Tailwind | v4: `@import "tailwindcss"` / `@theme` in global CSS, usually no config file; v3: `tailwind.config.{ts,js}` |
| Dark mode | `dark:` variant configured, `class` strategy, `[data-theme]` attribute selectors, or none. Grep the global CSS and config |
| shadcn/ui | `components/ui/` directory, `components.json` |
| Class merging | `cn()` helper in `lib/utils`, or `clsx`/`tailwind-merge` deps. If absent, do not demand them |
| Animation | `framer-motion` / `motion` dep |
| Package manager | lockfile: `bun.lock*`, `pnpm-lock.yaml`, `yarn.lock`, `package-lock.json` |
| CI scripts | actual script names in `package.json` for typecheck, lint, build |

Project conventions stated in the project's CLAUDE.md override this skill's
generic rules wherever they conflict. Project-specific disciplines (copy rules,
image pipelines, legal pages, content registries) live there, not here; apply
them as written.

---

## Step 1: CI gate

Run the detected typecheck and lint scripts; for Next.js also run the build
(it catches App Router mistakes types alone miss). If anything fails, report
the errors at the top and stop. Tooling errors outrank every finding below and
must be fixed first. Do not re-litigate what the project's tsc/eslint config
already catches; this review covers what tooling cannot.

---

## Step 2: Gather code

### Diff mode

Detect the default branch: `git symbolic-ref refs/remotes/origin/HEAD` (strip
the prefix), falling back to `main`, then `master`. Get the current branch with
`git branch --show-current`.

List changed files:
`git diff <base>...HEAD --name-only -- '*.tsx' '*.ts' '*.jsx' '*.js' '*.css' '*.html'`
plus the framework config files (`next.config.*`, `vite.config.*`,
`tailwind.config.*`, `vercel.json`). If the list is empty and you are on a
branch other than the default, fall back to `git diff HEAD~1 --name-only` to
catch the last commit. If on the default branch with no changes, stop and
report: "No diff found. Run this skill on a feature branch, or use
`/frontend-review full` to audit the entire codebase." Never silently review
`HEAD~1` on the default branch.

Get the patch with the same `git diff <base>...HEAD -- ...` paths.

Read the **full content** of each changed file; the diff alone is not enough
for structure and a11y checks. Always also read the stack's cross-cutting
files, even when not in the diff, because changes elsewhere can affect them:

- **Next.js**: root `app/layout.tsx`, the global CSS, `next.config.*`
- **Vite SPA**: `src/App.tsx` (or the router root), `index.html`, the global CSS

### Full mode

Glob all source files (`src/**/*.{tsx,ts}`, plus `app/**/*.{tsx,ts}` for
Next.js). Read every file plus the cross-cutting files above.

---

## Step 3: Apply the checklist

Read `references/checklist.md` from this skill's directory. Apply only the
sections matching the stack profile from Step 0; skip gated sections that do
not apply (for example, no Next.js rules against a Vite app). In diff mode,
focus findings on changed files but still evaluate cross-cutting rules
(routing completeness, landmarks, meta tags, security headers) by reading
related files when a change could affect them.

---

## Step 4: Classify findings

Every finding goes into one of three tiers:

**🔴 Critical**: must fix before merge. Runtime errors, security issues,
broken a11y, broken behavior, data exposure.

**🟡 Important**: should fix before merge. Type-safety gaps, performance
regressions, significant convention violations, copy/voice policy breaches.

**🔵 Suggestion**: optional. Readability, minor inefficiencies, style nits.

For each finding include:
- **File**: path from repo root
- **Line**: line number or range
- **Rule**: rule ID from the checklist (e.g. `A3`, `N2`, `RR1`)
- **Issue**: what is wrong and why it matters
- **Fix**: concrete suggestion

Drop findings below 80% confidence. Mark borderline cases *(low confidence)*.

---

## Step 5: Report, then fix

Use the output template below. Skip categories with no findings, and build the
summary table only from the sections actually applied. Order categories by
user-impact priority as laid out in the checklist.

After the report, apply fixes per the `--fix` argument:
- default: fix 🔴 Critical findings only
- `--fix all`: fix 🔴 + 🟡 + 🔵
- `--fix none`: report only

State what changed and why for every edit. Never blind-edit user-visible copy
or content strings: typographic quotes, localization files, and content
registries often have their own editing workflow (check the project's
CLAUDE.md). Report copy findings; apply them only through the project's
documented workflow, or leave them to the user when none exists.

---

## Output template

```
## Frontend Review: [diff | full]

Stack: <framework> · <router> · <styling> · <package manager>
Branch: `<branch>` vs `<base>`
Files reviewed: <n>

---

### <Category> (<n> findings | PASS)

#### [Short finding title] · 🔴 critical | 🟡 important | 🔵 suggestion
- **File**: `path/to/file.tsx` L<line>
- **Rule**: <ID>
- **Issue**: <description>
- **Fix**: <suggestion>

---

### Summary

| Category | Result |
|----------|--------|
| <each applied section> | PASS / n findings |

**Verdict**: ✅ Ready to merge | ⚠️ Needs attention | 🚫 Block merge
<n> critical · <n> important · <n> suggestions
```
