---
name: travel-planner
description: >
  Generate two paired HTML travel artifacts from raw trip data: (1) a dense,
  printable itinerary table and (2) an interactive Leaflet route map. Use this
  skill whenever the user wants to plan, document, or visualize a multi-stop
  trip — especially when they describe a route with dates, stays, flights, or
  transport legs. Triggers on phrases like "create my itinerary", "build a route
  map", "plan my trip", "update the travel table", "add a new stop", "I'm flying
  to X then Y", or any trip planning conversation involving 3+ locations. Also
  triggers when the user uploads booking confirmations, flight tickets, or
  accommodation details and asks to incorporate them into a trip overview.
  Always produce both artifacts together unless the user explicitly asks for one.
---

# Travel Planner

Two outputs, always paired: an **itinerary table** (HTML) and a **route map**
(Leaflet HTML). Read this file fully before writing a single line of code.

---

## Traveler Profile (default persona — override with user input)

**Rhythm**
- Remote workers: 3-5h morning work block, non-negotiable. WiFi is a hard
  filter, not a preference. Always ask for or note WiFi quality per location.
- Minimum 3 nights per base. No single-night stops.
- No activities on arrival or departure days.
- Alternating heavy days (full-day trips) and rest/city days.

**Movement**
- No rental cars. Public transport, shuttles, local jeeps, water taxis, buses.
- Prefers Uber/DiDi/InDrive over street taxis in cities.
- Pre-booked transfers for airport runs and early morning departures.
- Checks into a base and radiates outward for day trips — doesn't move hotels
  to chase individual sights.

**Accommodation**
- Private apartment or house via HomeExchange or Airbnb. Never hostels,
  never anything with "backpacker" in the name or description.
- Private bathroom and entrance non-negotiable.
- Quiet at night, natural light during the day.
- Good ventilation / air circulation. Openable windows on multiple sides
  preferred; AC is not a substitute for natural airflow.
- Authentic residential neighborhoods over tourist zones.
- Host track record weighted heavily (10+ reviews preferred).
- WiFi verification before booking: message every host "Do you have Starlink?"
  for remote areas.

**What they're after**
- Wildlife photography (Sony A7IV + drone, subject to local regulations).
- Nature, national parks, authentic local food and culture.
- Real neighborhoods, not tourist bubbles.
- Avoids: backpacker bars, party zones, generic tours.

**Luggage**
- One carry-on trolley + one backpack + one small camera bag each, two pax.
- Trolleys get checked on BASIC fares. Backpack + camera bag under seat.
- Always verify baggage allowance from ticket before building packing logic.

**Safety**
- Research neighborhood safety before accepting any accommodation.
- Higher on the hill = higher risk (applies in many Latin American cities).
- Avoid tourist-facing scams: always decline DCC at ATMs, pay in local currency.

---

## Artifact 1: Itinerary Table

### File naming
`[country]_itinerary_v[N].html` — increment version, delete old ones.

### Structure
One HTML file. No external dependencies. Inline CSS only.

Read `references/itinerary-table-spec.md` for the full HTML/CSS specification,
design tokens, component classes, and markup patterns.

**Columns:**
| Base | Check-in → out | Nights | Getting there | Self-guided activities | Agency / guided | WiFi |

**Rows:**
- Section dividers (colored left border matching transport color) for each
  country or coast region.
- One row per base. Never split a base into multiple rows unless there's a
  meaningful mid-stay change (e.g., moving to a different neighborhood).
- Footer row with: booked flights summary, transport apps that work,
  pending bookings, urgent action items.

### Content density rules
- Activities column: bullet list, 12px. Concrete and specific — not "explore
  the city" but "Parque Botero + Museo de Antioquia, then cable car to
  Santo Domingo."
- Day trips column: include cost, duration, booking requirement, and whether
  to book ahead.
- Getting there: always show two hops. (1) Inter-city transport badge at the
  top. (2) A `font-size:12px` sub-block for "Airport/station → accommodation"
  with app recommendation, approximate cost, and duration. Use `ul.al` with
  Best / Budget / Avoid for airports with multiple realistic options. Include
  operator name and known friction (e.g., "Uber blocked here — pre-arranged
  transfer only").
- Activities cell: end every cell with a `.note` showing the workday structure
  for that base — morning work block hours, then what type of afternoon the
  location best supports (nature, culture, food, rest). One sentence.
- WiFi column: Excellent / Good / Variable / Poor / None. Excellent is green,
  Good/Variable are blue, Poor/None are red. Add a `.sub` caveat if context
  matters (e.g., "None inside park").
- Warn badges (amber `.warn`) for: tight connections, cash-only locations,
  areas requiring advance booking, luggage restrictions. Standalone callouts,
  not attached to a specific booking.
- Confirmed badges (green `.conf`) for: booked flights, confirmed
  accommodation.
- Updated badges (amber `.upd`) for: revised flights, changed accommodation,
  any previously confirmed item whose details changed. Attaches inline to the
  specific badge, not a standalone callout.

---

## Artifact 2: Route Map

### File naming
`[country]_route_map.html`

### Stack
Leaflet 1.9.4 via CDN. Esri World Topo tiles (works offline, shows terrain).
Pure vanilla JS. No frameworks.

Read `references/route-map-spec.md` for the full Leaflet implementation spec,
marker patterns, arc drawing functions, signal zones, and popup templates.

**Base markers** — numbered circles (34px), colored by region:
- Each base gets a number matching the itinerary sequence.
- Popup on click: base name, dates, nights, WiFi, 2-3 key logistics notes.
- Use contrasting colors per region.

**Arcs between bases** — colored by transport mode (see transport-modes.md):
- Arcs with arrowheads showing travel direction.
- Label each arc with mode + distance + duration.

**Day trip markers** — small purple pill labels, offset from base.

**Signal zones** — circles for offline or variable WiFi areas.

**Legend** — bottom bar showing transport color codes.

**Map init** — fitBounds to all markers. No hardcoded center.

---

## Build Process

1. Establish booking sequencing order before planning logistics: most
   constrained accommodation first (island lodges, popular park-adjacent stays,
   Carnival-season cities), day tours second, transport legs last. Flag any
   confirmed items out of this order as a warn badge — flights booked before
   accommodation exists is a common trip-breaking mistake.
2. Parse all input (dates, locations, flights, accommodation, activities).
2. Geocode each location — look up approximate lat/lng coordinates.
3. Build itinerary table first — it forces you to clarify every leg before
   drawing lines on a map.
4. Build route map second, using the same data.
5. Output both files to the current working directory (or user-specified path).
6. Delete any prior version of the itinerary (keep map unless told to regenerate).

---

## Input formats accepted

- Free-text trip description ("I'm flying from X to Y on date Z, staying 5
  nights, then taking a bus to W...")
- Uploaded flight e-tickets (PDF) — extract: flight number, dep/arr times,
  fare class, baggage allowance, booking code, seats.
- Uploaded accommodation guides / welcome books (PDF) — extract: WiFi creds,
  checkout rules, transport recommendations, host contact.
- HomeExchange / Airbnb listing exports.
- Prior itinerary HTML — update in place, increment version.

When parsing flight tickets, always check:
- Fare class (BASIC = no overhead carry-on)
- Baggage column (0PC ≠ no bag if ABAG SSR is present)
- Endorsements field for hidden restrictions

---

## What to flag automatically

Surface these in the itinerary footer or as warn badges without being asked:

- BASIC fare with trolley in carry-on plan → luggage conflict
- Connection under 2h domestic→international → flag as tight
- ATM availability in remote areas → suggest cash prep
- Advance booking required (national park entries, popular day tours,
  island ferries, sought-after restaurants)
- Drone restrictions in national parks or protected areas
- IVA/tax exemptions available to tourists (Colombia, Ecuador, etc.)
- "Higher on the hill = higher risk" for neighborhood safety assessments
- Host with fewer than 5 reviews → flag track record gap
- Transit-constrained locations (island ferries or park boats running once per
  day): flag that all transport legs should be afternoon-slotted to protect the
  morning work block. Note the specific cutoff time if known (e.g., "3PM ferry
  — last slot, book immediately").

---

## Reference files

Read these when needed:

- `references/itinerary-table-spec.md` — full HTML/CSS spec, design tokens,
  component classes, and markup patterns for the itinerary table
- `references/route-map-spec.md` — Leaflet implementation spec, marker and arc
  patterns, signal zones, popup templates, legend structure
- `references/transport-modes.md` — arc colors, label formats, cost ranges
  by country/region
- `references/safety-zones.md` — neighborhood safety reference for cities
  covered so far (Medellín, Cartagena, Bogotá, Quito)
- `references/atm-fees.md` — ATM fee data by bank for Colombia and Ecuador
- `references/accommodation-filters.md` — full preference checklist for
  evaluating any accommodation listing

---

## Quick checklist before outputting

- [ ] Every base has: dates, nights, getting-there info, activities, WiFi rating
- [ ] Every flight has: flight number, dep/arr times, booking code, baggage
- [ ] Luggage plan is consistent with fare class on every flight
- [ ] Warn badges on: cash-only, advance bookings, tight connections
- [ ] Map arcs are directed with arrowheads
- [ ] Map popups match itinerary data
- [ ] Both files saved and old itinerary version deleted
