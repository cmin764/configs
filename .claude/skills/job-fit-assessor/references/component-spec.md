# React Component Spec

Full data schema, component structure, and rendering rules for the fit assessor artifact.

---

## Data schema

```js
const data = {
  sections: [
    {
      id: string,          // kebab-case, e.g. "ai-llm"
      label: string,       // display name, e.g. "AI & LLM Hands-on"
      items: [
        {
          fit: "strong" | "partial" | "gap",
          jd: string,      // JD requirement, verbatim or paraphrased
          you: string,     // specific evidence from candidate profile
          note: string | null  // assessor framing note, or null
        }
      ]
    }
  ]
}
```

All data is inlined as a `const`. No external fetch, no props, no localStorage.

---

## fitConfig

```js
const fitConfig = {
  strong: {
    label: "Strong Fit",
    color: "#15803d",
    bg: "rgba(21,128,61,0.06)",
    border: "rgba(21,128,61,0.18)",
    icon: "●"
  },
  partial: {
    label: "Partial Fit",
    color: "#b45309",
    bg: "rgba(180,83,9,0.06)",
    border: "rgba(180,83,9,0.18)",
    icon: "◑"
  },
  gap: {
    label: "Gap",
    color: "#b91c1c",
    bg: "rgba(185,28,28,0.06)",
    border: "rgba(185,28,28,0.18)",
    icon: "○"
  }
}
```

---

## Score formula

```js
const total = counts.strong + counts.partial + counts.gap
const score = Math.round((counts.strong * 100 + counts.partial * 50) / total)
```

Display as a large number (44–48px, DM Mono, bold) with a `%` suffix in muted color.
Alongside: per-category counts in their respective fit colors.

---

## Component tree

```
App
├── <link> Google Fonts: DM Mono + IBM Plex Sans
├── Header (white card, border-bottom)
│   ├── Label: "Fit Analysis"
│   ├── H1: "[Candidate Name] × [Role Title]"
│   ├── Subtitle: "[Company] · [REF]"
│   └── ScoreBadge (score % + per-category counts)
├── Filter row (white card, border-bottom)
│   └── Pill buttons: All | Strong Fit | Partial Fit | Gap
└── Content area (off-white background)
    ├── Hint: "Click a section to expand · Click any item to see the detail"
    └── Section[] (filtered)
        ├── Section header button (collapsible)
        │   ├── Dominant fit icon + section label
        │   └── Per-fit count badges + chevron
        └── Item[] (when section open)
            ├── Collapsed: fit icon + JD text + chevron
            └── Expanded: JD text + "You:" evidence + italic note
```

---

## Rendering rules

**Section default state**: open when `items.length <= 3`, collapsed otherwise.

**Dominant fit per section**: whichever fit type has the most items. Tie-break:
strong > partial > gap.

**Filter behavior**: hides items that don't match the active filter, hides sections
that become empty. "All" resets.

**Item expand/collapse**: click anywhere on the row.

**Typography**
- Section header label: 13px, DM Mono, semibold, `#1a1a1a`
- JD text (collapsed): 13px, IBM Plex Sans, `#555`
- "JD:" label: 10px, DM Mono, uppercase, letter-spacing 0.1em, `#ccc`
- "You:" label: 10px, DM Mono, uppercase, letter-spacing 0.1em, fit color
- You text (expanded): 13px, IBM Plex Sans, `#1a1a1a`
- Note text: 12px, IBM Plex Sans italic, `#777`, left-border in fit color

---

## What NOT to include

- No footer callout section. Strategic notes belong in the conversation, not the artifact.
- No emoji, stars, progress bars, or loading spinners.
- No footer with company name or branding.
- No localStorage, sessionStorage, or external API calls.
- No required props — data is fully self-contained.
- Never Inter, Roboto, or system-ui. DM Mono + IBM Plex Sans only.
