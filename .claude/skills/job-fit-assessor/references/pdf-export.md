# PDF Export

When the user asks to export the assessment as a PDF, produce a self-contained
static `.html` file that prints cleanly from any browser.

---

## Approach

Generate a standalone `.html` file (not a React app) with:
- All sections and items pre-expanded, rendered as plain HTML
- Inline styles throughout — no external CSS dependencies beyond Google Fonts
- `@media print` rules that hide interactive controls and force color printing

The user opens it in Chrome or Safari, presses Cmd+P (Ctrl+P on Windows),
selects "Save as PDF", and gets a clean document.

---

## Print CSS

```css
@media print {
  .filter-row,
  .chevron,
  .hint-text {
    display: none !important;
  }

  /* Force all sections and items visible */
  .section-body,
  .item-detail {
    display: block !important;
  }

  /* Avoid page breaks inside items */
  .item {
    page-break-inside: avoid;
    break-inside: avoid;
  }

  /* Keep section headers attached to their first item */
  .section-header {
    page-break-after: avoid;
    break-after: avoid;
  }

  /* Force background color printing in Chrome/Safari */
  * {
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  body {
    background: #ffffff !important;
  }
}
```

---

## Recommended print settings (tell the user)

- Paper: A4 or Letter
- Margins: Default
- Scale: 90% (prevents right-side clipping on dense content)
- Headers and footers: off

---

## Filename convention

```
[candidate-surname]-[company]-fit-assessment.html
```

Example: `poieana-xogito-fit-assessment.html`

---

## When to offer this unprompted

Offer after delivering a large artifact (8+ sections or 15+ items):
"Want a static HTML version you can print to PDF?"
One sentence. Don't describe the process unless they ask.
