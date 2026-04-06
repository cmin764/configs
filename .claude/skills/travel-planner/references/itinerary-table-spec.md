# Itinerary Table Spec

Full HTML/CSS specification for the itinerary table artifact.
Derived from a working Colombia itinerary. Apply this design system exactly.

---

## Page structure

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>[Country] Itinerary v[N] — [Date range]</title>
<style>/* all CSS inline — no external sheets */</style>
</head>
<body>
<h1>[Country] — [Traveler names]</h1>
<div class="meta">[Date range] · [N] nights · [N] bases · [transport note] · [exit flight if booked]</div>
<div class="wrap">
<table>
<thead><tr><!-- column headers --></tr></thead>
<tbody>
<!-- section divider rows -->
<!-- base rows -->
<!-- exit row -->
</tbody>
</table>
<div class="footer"><!-- summary items --></div>
</div>
</body>
</html>
```

---

## CSS design system

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f4f0; padding: 24px; }

/* Page title */
h1 { font-size: 17px; font-weight: 600; color: #1a1a1a; margin-bottom: 3px; }
.meta { font-size: 12px; color: #777; margin-bottom: 20px; }

/* Table wrapper — enables horizontal scroll on mobile */
.wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 10px; overflow: hidden; box-shadow: 0 1px 4px rgba(0,0,0,.08); }

/* Column headers */
th { text-align: left; padding: 8px 11px; font-size: 10px; font-weight: 600; color: #888; text-transform: uppercase; letter-spacing: .06em; border-bottom: 1.5px solid #e0ddd5; }

/* Data cells */
td { padding: 8px 11px; vertical-align: top; border-bottom: .5px solid #ebe9e3; }
tr:last-child td { border-bottom: none; }

/* Section divider row */
.sec td { padding: 4px 11px; font-size: 10px; font-weight: 600; color: #888; letter-spacing: .07em; text-transform: uppercase; background: #f5f4f0; }

/* Transport/status badges */
.badge { display: inline-block; padding: 2px 7px; border-radius: 3px; font-size: 10px; font-weight: 600; white-space: nowrap; margin-bottom: 3px; }
.bf  { background: #dbeafe; color: #1d4ed8; }                                /* FLIGHT — blue */
.bb  { background: #f1f0eb; color: #555; border: .5px solid #d0cec6; }       /* BUS/OVERLAND — neutral grey */
.bj  { background: #fef9c3; color: #713f12; border: .5px solid #fde68a; }    /* JEEP/WILLY/COLECTIVO — amber */
.bt  { background: #f3e8ff; color: #6b21a8; border: .5px solid #e9d5ff; }    /* BOAT/FERRY/WATER — purple */

/* Inline status tags (appended after badge text) */
.upd  { font-size: 9px; padding: 1px 5px; border-radius: 3px; background: #fef3c7; color: #92400e; font-weight: 600; margin-left: 5px; }  /* "UPDATED" */
.conf { font-size: 9px; padding: 1px 5px; border-radius: 3px; background: #dcfce7; color: #166534; font-weight: 600; margin-left: 5px; }  /* "BOOKED/CONFIRMED" */

/* Night counter circle */
.nc { width: 26px; height: 26px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-weight: 600; font-size: 12px; }
/* Use inline style for background/color — one per region, e.g.: style="background:#D3D1C7;color:#2C2C2A;" */

/* Activity list (no default bullets — uses ::before dot) */
ul.al { margin: 0; padding: 0; list-style: none; }
ul.al li { padding-left: 10px; position: relative; margin-bottom: 2px; font-size: 12px; color: #1a1a1a; }
ul.al li::before { content: "·"; position: absolute; left: 0; color: #aaa; }

/* Sub-text below a cell value */
.sub  { font-size: 10.5px; color: #888; margin-top: 2px; }

/* Notes (logistics tips, context) */
.note { font-size: 10.5px; color: #888; margin-top: 5px; padding-top: 4px; border-top: .5px solid #e8e6e0; }

/* Warnings (amber) — gotchas, tight connections, cash-only, booking deadlines */
.warn { font-size: 10.5px; color: #92400e; margin-top: 5px; padding: 4px 6px; border-radius: 3px; background: #fffbeb; border: .5px solid #fde68a; }

/* WiFi status colors */
.wg { font-size: 11px; color: #16a34a; }              /* Excellent */
.wm { font-size: 11px; color: #2563eb; }              /* Good / Variable */
.wr { font-size: 11px; color: #dc2626; font-weight: 600; }  /* Poor / None */

/* Footer */
.footer { display: flex; flex-wrap: wrap; gap: 16px; padding: 10px 11px 6px; border-top: .5px solid #e0ddd5; font-size: 11px; color: #888; }
.footer strong { color: #333; }
.bwarn { color: #92400e; }
.bwarn strong { color: #92400e; }
```

---

## Column spec

| # | Column | `min-width` | Content |
|---|--------|-------------|---------|
| 1 | Base | 130px | `font-weight:600` base name + `.sub` neighborhood/sector |
| 2 | Check-in → out | 140px | `color:#777; white-space:nowrap` dates with `&rarr;` |
| 3 | Nights | 48px `text-align:center` | `.nc` circle with region color |
| 4 | Getting there | 230px | Transport `.badge` + detailed `font-size:12px` instructions, `ul.al` options, `.warn`/`.note` |
| 5 | Self-guided activities | 210px | `ul.al` bullet list + `.note` day schedule |
| 6 | Agency / guided | 210px | `ul.al` for tours, guides, day trips requiring booking |
| 7 | WiFi | 68px | `.wg`/`.wm`/`.wr` status + `.sub` caveat |

---

## Section divider rows

```html
<tr class="sec">
  <td colspan="7" style="border-left:3px solid [REGION_COLOR];">[Region name — short descriptor]</td>
</tr>
```

Base rows in that region also carry the border:
```html
<tr>
  <td style="border-left:3px solid [REGION_COLOR];">...</td>
  ...
</tr>
```

Pick one distinct color per region. Use muted, not garish:
- Andean highlands: `#888780` (warm grey)
- Coffee/rural: `#EF9F27` (amber)
- City/metro: `#7F77DD` (muted purple)
- Caribbean coast: `#D85A30` (terracotta)
- Pacific coast: `#1D9E75` (teal)
- Exit/transit: `#378ADD` (blue)

Night circle colors should roughly match:
- Andean: `background:#D3D1C7; color:#2C2C2A`
- Coffee: `background:#FAC775; color:#412402`
- City: `background:#AFA9EC; color:#26215C`
- Caribbean: `background:#F0997B; color:#4A1B0C`
- Coast: `background:#5DCAA5; color:#04342C`

---

## Getting there cell pattern

```html
<td>
  <span class="badge bf">FLIGHT — BOG→MDE, 1h</span>
  <div style="margin-top:6px;font-size:12px;"><strong>Airport → hotel (~40min):</strong> Uber or DiDi, ~$8–12 USD.</div>
  <ul class="al" style="margin-top:4px;">
    <li><strong>Best:</strong> Pre-booked transfer ...</li>
    <li><strong>Budget:</strong> Public bus + metro ...</li>
    <li><strong>Avoid:</strong> Street taxis without meter</li>
  </ul>
  <div class="warn">Warning text for gotchas</div>
  <div class="note">Note text for context or tips</div>
</td>
```

Badge text convention: `MODE — ORIGIN→DEST, duration` or `MODE — description`

---

## Exit row (final flight)

```html
<tr class="sec"><td colspan="7" style="border-left:3px solid #378ADD;">Exit — [Country] to [Destination]</td></tr>
<tr>
  <td colspan="2" style="border-left:3px solid #378ADD;">
    <div style="font-weight:600;">Apr 11 — exit flight <span class="conf">BOOKED</span></div>
    <div class="sub">Booking [CODE] · [Traveler names]</div>
  </td>
  <td style="text-align:center;">&mdash;</td>
  <td colspan="4">
    <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:2px 0;">
      <span class="badge bf">FL001 — AAA→BBB 10:00, 1h30m</span>
      <span class="badge bf">FL002 — BBB→CCC 13:00, 2h</span>
    </div>
    <div style="font-size:11px;color:#555;margin-top:6px;">
      <strong>AAA airport by 08:30.</strong> Taxi/Uber ~15min. Check in online 48h before.
    </div>
  </td>
</tr>
```

---

## Footer

```html
<div class="footer">
  <span><strong>Apps that work:</strong> Uber + DiDi in [City1], [City2]. Not reliable in [rural area].</span>
  <span><strong>Flights to book:</strong> AAA→BBB (Date) · BBB→CCC (Date)</span>
  <span><strong>Total:</strong> [N] nights · [N] bases · No rental car</span>
  <span class="bwarn"><strong>Book immediately:</strong> [Item1] · [Item2]</span>
</div>
```

Items with booking urgency go in `.bwarn`. General info in plain `<span>`.
