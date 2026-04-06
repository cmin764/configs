# Profile Extraction Guide

What to pull from each source type when building the candidate profile.
The fuller the picture before scoring, the more honest the assessment.

---

## Local files

First, determine the scan root from the invocation (see SKILL.md Phase 1.1), then scan it:

```bash
find <profile-dir-or-.> -maxdepth 3 -name "*.md" -o -name "*.pdf" -o -name "*.txt" | head -30
```

Common profile file patterns to look for:

| File | Likely content |
|------|---------------|
| `README.md` (in a `username/username` profile repo) | Self-positioning, stack, current focus, highlights |
| `cv.md` / `resume.md` | Structured employment history, credentials |
| `codex.md` / `about.md` / `bio.md` | Personal strategy, detailed career narrative |
| `portfolio.md` / `projects.md` | Project highlights and outcomes |
| Any `.md` with dates or company names | Likely career context, worth reading |

Don't assume filenames. Read whatever's present that resembles professional background.

---

## Uploaded files

If the user attached files, they're at `/mnt/user-data/uploads/`. Read them directly.

**PDF / DOCX resume**: extract timeline, titles, companies, durations, quantified
achievements. A resume is structured but often sanitized — cross-reference with
other sources for the fuller story.

**Cover letter**: read what the candidate emphasizes. The choice of emphasis reveals
their own priority ranking of their experience. If they lead with X, X matters to them.

**Any recruiter-shared documents**: treat as additional context that can reweight
how critical certain requirements are.

---

## External sources

**GitHub profile README**
```
web_fetch: https://raw.githubusercontent.com/[username]/[username]/main/README.md
```
If the README links to supporting files (`codex.md`, `cv.md`, etc.), fetch those too.

Also check pinned repos: languages used, recency of activity, project scale,
README quality. A well-written README is itself a communication signal.

**LinkedIn** (if URL provided): extract endorsements, recommendations, career arc
framing. Note how the candidate narrates their own story.

**Personal site / portfolio** (if URL provided): what they lead with, what they
choose to show strangers. First impression they're deliberately crafting.

---

## What to synthesize from all sources

After reading everything, build a profile map across these dimensions:

**Hard skills with depth**
Map languages and tools to approximate years of real use — not just mention.
"18 years Python" is different from "comfortable with Python."
For AI/ML: which platforms, which frameworks, what was shipped vs. experimented with.
"Deployed a Recall.ai-based meeting agent" is signal. "Interested in LLMs" is noise.

**Leadership evidence**
Specific: team size, decision scope, measurable outcomes. What got shipped, what
changed because of this person. "Led a team" without specifics is not evidence.

**Domain depth**
Industries touched, depth per domain (surface pass vs. years embedded), B2B vs. B2C,
regulated vs. unregulated, startup vs. enterprise. All of these affect transferability.

**Career arc**
IC to lead to principal, or lateral moves? Trajectory tells you something about how
the candidate develops. Acquisitions at previous employers are a proxy for system
quality — those teams built something worth buying.

**Peer-validated achievements**
Conference talks, open-source adoption, competition results, published work,
recommendations from known people, employer acquisitions. Self-reported achievements
rank lower than things a third party confirmed.

**Profile gaps**
If a domain or skill area is genuinely absent, record it as an explicit gap rather
than omitting it. "No public writing on technical leadership" is a legitimate finding.
Omitting it only hurts the candidate when a gap surfaces in the interview unprepared.

---

## Example: reading a GitHub profile repo

*This example uses a real past assessment to show the pattern. Replace with whatever
candidate you're working with.*

A profile repo like `username/username` typically has a README that covers
positioning and stack, and sometimes supporting files for career detail (`codex.md`)
or a formal history (`cv.md`). If the README has an "About" or "Currently building"
section, that's the most current signal. The codex-style file, if present, is usually
the richest — it contains the career arc, project specifics, and strategic context
that a resume strips out. Fetch both and triangulate.
