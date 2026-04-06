---
name: job-fit-assessor
description: >
  Produces a structured, interactive React artifact that annotates a job description
  against a candidate profile, surfacing strong fits, partial fits, and gaps — each
  with specific evidence and honest assessor notes. Use this skill whenever a job
  description or JD URL is shared alongside profile materials (resume, GitHub, cover
  letter, personal documents, online accounts), or when the user says things like
  "how do I match this role", "assess my fit", "annotate this JD", "should I apply",
  "what are my weak points for this job", or "run a fit assessment". Also trigger when
  the user shares recruiter context alongside their background, or asks to evaluate any
  role against their experience. Accepts an optional profile directory path (positional,
  --profile-dir flag, or natural language like "my profile is at ~/path/") to read
  candidate materials from a specific location instead of the working directory.
  The output is a filterable, collapsible React artifact with an overall fit score
  and optional PDF export.
---

# Job Fit Assessor

Produces an interactive React artifact that scores a candidate against a JD, grouped
into thematic sections, with per-item fit ratings and honest evidence-backed notes.

---

## Phase 1: Gather candidate profile

Build the fullest possible picture of the candidate before scoring anything.
Work through available sources in priority order.

### 1.1 Local files

First, determine the scan root:

1. **Check the invocation for a profile directory path.** The user may supply it as:
   - A positional argument: `/job-fit-assessor ~/path/to/profile [JD URL]`
   - A flag: `--profile-dir ~/path/to/profile`
   - Natural language: "my profile is at ~/docs/career/", "use ~/profile/ for my CV"
2. **If a path is provided**, use it as the scan root.
   **If no path is provided**, fall back to the current working directory.

Scan the root directory (depth ≤ 3) for profile-related files. Common patterns:

```
README.md         ← self-positioning, stack, current focus
cv.md / cv.pdf    ← structured work history and credentials
codex.md          ← personal strategy, career timeline, projects
bio.md            ← narrative background
portfolio.md      ← project highlights
```

Use `ls`, `find`, or `glob` to discover what's actually present. Don't assume
specific filenames — read whatever exists that looks like professional background.
If the directory contains a profile README (e.g. `username/username` on GitHub), that's
the primary source.

### 1.2 Uploaded files

If the user has attached files to the conversation, read them:
- PDF or DOCX resume: extract at `/mnt/user-data/uploads/`
- Cover letter, bio, portfolio doc
- Any recruiter-shared materials

### 1.3 External sources (when URL provided or no local files)

If the user provides a GitHub username or profile URL:
```
web_fetch: https://raw.githubusercontent.com/[username]/[username]/main/README.md
```

Check for supporting docs linked from the README and fetch those too.

If the user provides a LinkedIn, portfolio, or personal site URL, fetch it.

### 1.4 What to extract

Read `references/profile-extraction.md` for the full extraction guide.
The key outputs are: hard skills with experience depth, leadership evidence,
AI/domain specifics, career arc, and peer-validated achievements.

---

## Phase 2: Research the company and role

### 2.1 Fetch the JD

If the user provides a URL: `web_fetch: [URL]`

If pasted as text, use it directly.

Classify every requirement as:
- **Hard** ("required", "must have", "X+ years")
- **Preferred** ("nice to have", "bonus", "preferred")
- **Implied** (domain knowledge implied by responsibilities but not stated)

### 2.2 Company context

Run these searches in parallel:

```
web_search: "[company] company overview funding model"
web_search: "[company] glassdoor reviews"
web_search: "[company] revenue size employees"
```

Extract: business model, scale, remote posture, culture signals from reviews,
leadership background, any recent funding or distress signals.

### 2.3 Recruiter context

If the user shares recruiter messages or notes, extract:
- What they emphasized beyond the JD (often the real priority)
- What previous candidates were missing
- Interview process details
- Unstated expectations (hours, pace, visibility)

Recruiter emphasis changes the weight of individual items. A recruiter who says
"communication is critical" means a communication gap is more disqualifying than
it reads on paper.

---

## Phase 3: Map and annotate

Read `references/annotation-guide.md` for the full rubric and note-writing rules.

### 3.1 Group into sections

Regroup JD requirements into 6-8 coherent sections. Don't follow the JD's structure
slavishly — regroup to make the fit story readable. Typical sections:

- Years & Seniority
- Core Technical Skills
- AI / Domain-Specific Skills
- Technical Leadership & Influence
- Domain Fit
- Credentials & Education
- Communication & Soft Skills
- Logistics & Practical Fit

Adjust sections to the role. A design role needs different groupings than a
backend engineering role or a product management role.

### 3.2 Rate each item

| Rating | When |
|--------|------|
| **Strong (●)** | Direct evidence. The candidate shipped this, can prove it. |
| **Partial (◑)** | Adjacent experience that transfers but doesn't hit squarely. |
| **Gap (○)** | No credible evidence. Absent or unsubstantiated in the profile. |

Hard requirements with no profile evidence = Gap, even if an equivalency clause exists.
The clause is an opening to argue in the interview, not a free pass at the rating stage.

Structural/logistical items (employment type, location, clearance, timezone) are binary.
A concrete conflict is a Gap — rate it honestly and let the note explain what to resolve.

### 3.3 Score

```
score = round((strong_count × 100 + partial_count × 50) / total_items)
```

---

## Phase 4: Build the React artifact

Read `references/component-spec.md` for the full component schema, data structure,
and rendering rules.

**Design system (light theme)**

| Token | Value |
|-------|-------|
| Background | `#f0efec` |
| Surface | `#ffffff` |
| Border | `#e4e4e4` |
| Text primary | `#111111` |
| Text secondary | `#555555` |
| Strong fit | `#15803d` |
| Partial fit | `#b45309` |
| Gap | `#b91c1c` |
| Display font | DM Mono (Google Fonts) |
| Body font | IBM Plex Sans (Google Fonts) |

All data inlined as a `const`. No props, no external fetch, no localStorage.

---

## Phase 5: Deliver

After the artifact, add a brief plain-text summary in the conversation (150 words max):
- Where the candidate is clearly strong (2-3 sentences)
- The 1-2 real gaps and why they matter in context
- Any strategic question to resolve before going deep in the process

The artifact has the detail. The summary is the orientation.

If the assessment has 8+ sections or 15+ items, offer: "Want a static HTML version
you can print to PDF?"

---

## Reference files

Read these on demand as each phase requires them:

- `references/profile-extraction.md` — what to pull from each source type
- `references/annotation-guide.md` — fit rating rubric and note-writing rules
- `references/component-spec.md` — React component schema and rendering logic
- `references/pdf-export.md` — print CSS and static HTML export instructions
