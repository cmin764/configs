# Annotation Guide

Fit rating rubric and rules for writing assessor notes.
The quality of an assessment lives and dies on specificity.
Vague praise and softened gaps are useless to a candidate preparing for an interview.

---

## Fit rating rubric

### Strong Fit (●)
Clear, direct evidence in the profile. The candidate has done this, shipped it, and
can prove it. Not just familiarity — demonstrated execution. If you can name the
project, company, and outcome, it's a strong fit. If you're reaching for a vague
claim, it isn't.

### Partial Fit (◑)
Adjacent experience that transfers but doesn't hit the requirement squarely. The
candidate can make the argument but needs to frame it carefully. Or: they have the
skill but the evidence is thin, dated, or hard to verify publicly.

Use partial when: the domain is adjacent (not identical), the scale is smaller than
required, or the technology is similar but not the exact platform mentioned.

### Gap (○)
No credible evidence. Either absent from the profile, or present only as a vague
self-claim without backing. Don't soften a gap into a partial to spare feelings —
that only hurts the candidate when they walk into an interview unprepared.

---

## Hard vs. preferred requirements

A hard requirement absent from the profile is a Gap by default. An equivalency clause
("or equivalent practical experience") is an opening to argue, not a free pass — and
prepare for ATS to not honour it even when a human recruiter would.

A preferred requirement absent from the profile is Partial at most. But a long list of
missing preferred items can still drag the score down even if there's no single hard Gap.
Don't average away a pattern of misses.

---

## Logistics items

Employment type conflicts (full-time permanent role vs. active independent ventures),
location or clearance mismatches, and schedule conflicts are binary: either resolved or
not. Default to Gap. The note should tell the candidate what to resolve — not soften
the conflict into a Partial to make the score look cleaner.

---

## Timezone math

Do the actual UTC math. Clean morning overlap = Strong. Afternoon-to-evening shift
(sustainable but not frictionless) = Partial. Night shift or no usable overlap = Gap.
Don't call an evening shift "clean" — that sets the candidate up to be surprised on
day one.

---

## Item granularity

When a JD bundles multiple distinct sub-domains (e.g. "HR tech, fintech, or workforce
management"), split into separate items if the candidate's coverage is uneven. A single
bundled item hides exactly which sub-domain is weak. Surface it — that's the point of
the assessment.

Same logic applies to leadership scope: "mentoring individuals on AI tools" and "rolling
out AI governance at org scale" are different items even when the JD lists them in one
sentence. Split them when evidence covers one but not the other.

---

## Note-writing rules

Every item gets an assessor note when there's something useful to say. Notes should:

1. **Name specific evidence.** A product name and platform beats a category.
   "Shipped a Recall.ai-based meeting agent" beats "AI experience."
   "EuroPython 2015 talk on testing frameworks" beats "public speaking."

2. **Give framing for partial fits.** The candidate needs the *sentence to say*
   in the interview, not just a rating. Give them the exact pivot.

3. **Be honest about gap severity.** A missing "preferred" credential at a seed-stage
   startup is different from a missing hard requirement at an enterprise with a
   structured screening bar. Say which it is.

4. **Weight recruiter signals.** If the recruiter flagged something as critical,
   note that a gap there is more disqualifying than it reads on paper.

Write `null` when the fit is self-evident and nothing useful can be added.
Don't manufacture notes for their own sake.

---

## Examples

The examples below are drawn from a real past assessment (a principal AI engineer
role). They illustrate the note-writing pattern. Replace the specifics with whatever
applies to the candidate and role you're currently working on.

### Strong fit — name the evidence

**JD requirement:** "Proven experience with LLM platforms and agentic coding tools"

Bad:
> Strong AI background across multiple companies.

Good:
> Four distinct shipped products in a single client engagement: a Recall.ai-based
> meeting agent, a Firecrawl-powered RAG careers assistant, a Retell AI voice
> interview recovery system, and an agentic candidate assessment pipeline. Add an
> earlier role where the core product was an orchestration layer for GPT actions.
> This isn't AI exposure — it's a shipped portfolio.

Why it works: names the platforms, names the products, distinguishes "shipped" from
"experimented." Gives the candidate a ready-made answer.

---

### Partial fit — give the framing, not just the rating

**JD requirement:** "Experience in B2B SaaS, workforce management, HR tech, or fintech"

Bad:
> Strong HR-tech background through previous work.

Also bad (too harsh with no path forward):
> Limited domain experience, significant gap.

Good:
> Recruitment tech is adjacent but upstream from workforce management. Recruitment
> is where jobs are posted; workforce management is where people are scheduled, paid,
> and tracked. Different buyer, different data model. The argument isn't "I've done
> this" — it's "I've been one domain over, here's how fast I ramp." Frame prior work
> as deep HR-tech exposure. Don't claim workforce management without qualification.

Why it works: precise about the nature of the gap, gives the candidate the actual
framing to use, tells them what not to claim.

---

### Gap — call it clearly

**JD requirement:** "Master's degree in AI, ML, Data Science, or related field
(or equivalent practical experience)"

Bad:
> Equivalent practical experience more than compensates.

Good:
> Bachelor's in CS, no Master's. The "equivalent practical experience" clause is real
> but requires active argument — don't assume the recruiter interprets it the same
> way. Lead with the longest and most applied evidence: years of hands-on ML/AI work,
> any acquired-company track record, early-career academic signals. That's the case
> to make. But prepare for it to be flagged anyway at the screening stage, especially
> if it's a checkbox a hiring manager runs before the conversation starts.

Why it works: doesn't pretend the gap isn't there, gives specific evidence to argue
equivalency, manages expectations about where in the process this might bite.

---

### Logistics and strategic fit

These aren't technical assessments — they're reality checks. Write them plainly.

**Employment type conflict:**
> This is a full-time permanent role. If the candidate is mid-build on independent
> ventures or a consulting practice as long-term assets, accepting this subordinates
> that trajectory. This isn't a fit question — it's a strategy question. Worth
> resolving before the process goes three rounds deep.

**Clean timezone match:**
> The candidate's timezone maps cleanly to the required working hours. No compromise
> needed. One checkbox that costs nothing.

---

## Tone rules

- Name specific projects, companies, and platforms. Never write "AI work" when you
  mean a specific shipped product.
- One concrete example beats three vague claims every time.
- For partial fits: give the framing, not just the rating.
- For gaps: be honest about how disqualifying it actually is in context.
- Never write a note that reassures the candidate when they should be concerned.
  That is not kindness — it's a disservice.
- Write notes as if you're prepping the candidate for the specific question they'll be
  asked in this interview. "The Blugen framing is a sellable concept here" is useful.
  "Strong AI background" is not. Test: would the candidate know exactly what to say
  walking out of the interview if the note were all they had?
