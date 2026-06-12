# Frontend Review Checklist

Rules ordered by user-impact priority. IDs are used in review findings.
Sections marked **[gated]** apply only when the stack profile from Step 0
matches; everything else applies to any React project.

Skip anything the project's typecheck and lint configs already catch (Step 1
runs them first and they take priority). ESLint setups differ: when a project
disables a rule like `no-unused-vars`, cover that ground manually (dead
imports, unreferenced components).

---

## 1. Accessibility (A): WCAG 2.2 AA

**A1**: Every image has descriptive, contextual `alt` text. Decorative or
purely background images use `alt=""`. The same file used in two places may
need different descriptions: alt belongs at the point of use. A brand logo
describes the brand, not `alt=""` or `alt="logo"`.

**A2**: Icon-only interactive elements (buttons or links containing only an
icon, no visible text) require `aria-label`. Check menu toggles, theme
toggles, carousel and gallery controls, social links.

**A3**: ARIA state tracks React state. Toggles that open/close need
`aria-expanded`; selected items need `aria-selected`; the values must update
with state. Stale ARIA attributes actively mislead assistive technology.

**A4**: Each page has exactly one `<h1>`. Heading levels are sequential with
no skipped levels (h1 → h2 → h3). Screen-reader navigation depends on it.

**A5**: Landmark regions present on every page: `<header>`, `<nav>`,
`<main>`, `<footer>`. Flag any page that bypasses the shared layout or puts
content outside the landmarks.

**A6**: A skip-navigation link (`<a href="#main-content">Skip to content</a>`)
as the first focusable element in the root layout. Recommend adding one if
missing; flag removal if present.

**A7**: Focus is visible on every interactive element. No `outline: none` or
`outline-none` without a `focus-visible` replacement (ring or equivalent).
Check custom `<button>` elements; component libraries usually handle their own.

**A8**: Color contrast meets WCAG AA: 4.5:1 for body text, 3:1 for large
text and UI components. When the project has theming, check both light and
dark modes; brand accent colors on light backgrounds are the usual failure.

**A9**: Reduced motion is respected at every layer present:
`@media (prefers-reduced-motion: reduce)` in CSS for keyframe/transition
animations, and `<MotionConfig reducedMotion="user">` at the root when
framer-motion is used.

**A10** *(WCAG 2.2)*: Pointer targets are at least 24x24 CSS px or have
sufficient spacing. Check icon buttons, nav links, and mobile tap targets.

**A11** *(WCAG 2.2)*: Focus appearance: the indicator is at least a
2px-thick border-equivalent and contrasts at 3:1 with adjacent colors in all
themes.

**A12** *(WCAG 2.2)*: Focus not obscured. With a sticky header, an element
focused via keyboard or hash navigation must not hide behind it. Verify
`scroll-mt-*` or an equivalent scroll offset on hash targets.

**A13**: Every embed `<iframe>` has a `title`. If a vendor library injects
the iframe without one, set it via a `ref` plus `useEffect`.

**A14**: Links that open in a new tab signal it to assistive technology:
icon-only external links carry an `aria-label` including "opens in new tab"
or equivalent.

---

## 2. Next.js App Router (N) [gated: Next.js]

**N1**: `"use client"` only when the component genuinely needs browser APIs,
event handlers, or stateful hooks. Server components are the default.

**N2**: `"use client"` pulls the entire module tree below it into the client
bundle. Push it to the smallest leaf. Never put it on a parent wrapping
server-renderable siblings.

**N3**: Props crossing the server-to-client boundary must be serializable.
No class instances, `Date` objects, or functions; these throw at runtime.

**N4**: Secrets, DB clients, or non-`NEXT_PUBLIC_` env vars must not appear
in `"use client"` files. They ship to the browser.

**N5**: `next/image` for content images, never raw `<img>`. `next/link` for
internal navigation, never `<a href>` for same-origin paths.

**N6**: `error.tsx` must carry `"use client"`. Missing it is a subtle
runtime failure.

**N7**: `notFound()` and `redirect()` throw internally. Never wrap them in
`try/catch`; the throw gets swallowed and both calls silently do nothing.

**N8**: In Next.js 15+, `params` and `searchParams` in pages and layouts are
`Promise<...>`. Always `await` them.

**N9**: Never mix a static `export const metadata` with `generateMetadata`
in the same file; the static export is silently ignored.

**N10**: Caching: Next.js 15 changed the `fetch()` default from
`force-cache` to `no-store`. Bare `fetch()` calls ported from v14-era code
may be unintentionally dynamic; review each. In 16, prefer the explicit
`"use cache"` directive over `next: { revalidate: N }` options.

**N11**: `revalidateTag()` without a matching `next: { tags: [...] }` on the
originating fetch does nothing. Verify the tags actually pair up.

**N12**: Mixed `revalidate` values across a layout/page tree: the shortest
wins the whole segment. A child with `revalidate: 0` makes the route always
dynamic regardless of the layout's value.

**N13**: `unstable_cache` on per-user data must include the user identifier
in the cache key; otherwise it is a cache-poisoning risk.

**N14**: Server Actions: validate all inputs server-side with a schema
library (Zod, Valibot); client-side validation is UX only. Check
authorization inside every action (middleware can be bypassed, see SEC4).
Return `{ error: string }` instead of throwing (thrown errors are untyped and
can leak stack traces). Call `revalidatePath`/`revalidateTag` after mutations
or the UI shows stale data.

---

## 3. SPA Routing (RR) [gated: react-router]

**RR1**: Internal navigation uses `<Link>` / `<NavLink>` from react-router,
never `<a href>`. Plain `<a>` causes a full page reload. This is the single
most recurrent real-world mistake; treat it as a high-priority target.
`mailto:`/`tel:` links are the legitimate `<a>` exception.

**RR2**: The catch-all `<Route path="*" element={<NotFound />} />` stays
last in the route table.

**RR3**: Hash targets (`/#section`) need a matching `id` on the element and
a scroll offset (`scroll-mt-*`) when the header is sticky. Verify the project
has a scroll restoration component reacting to `[pathname, hash]`.

**RR4**: Same-URL hash edge case: `<Link to="/#section">` is a no-op when
the URL is already `/#section` (the location effect does not re-run). A CTA
jumping to a hash on the current page needs an explicit click handler calling
`scrollIntoView` plus `history.replaceState` to keep the URL in sync.

**RR5**: Repeated navigational data (nav links, footer items) lives as data
that menus `.map()` over, not duplicated markup between desktop and mobile.

---

## 4. SEO & Meta (S)

Mechanism varies: Next.js metadata API, React 19 native `<title>`/`<meta>` in
route components, or react-helmet. Use whichever the project already uses.

**S1**: Every route sets a unique `<title>` and `<meta name="description">`.
Missing ones silently fall back to the global shell values; flag new routes
without both.

**S2**: `<html lang>` is present and matches the content language.

**S3**: Per-route `<link rel="canonical">` with an href matching the route
path exactly. Sites on Vercel/Netlify are reachable on both the platform
subdomain and the custom domain; canonical prevents duplicate indexing.

**S4**: When the 404 page is served HTTP 200 via SPA fallback, it must
render `<meta name="robots" content="noindex">`. Never noindex real pages.
The 404 page does not need a canonical.

**S5**: OG tag split: truly global tags (`og:type`, `og:image` and its
dimensions/alt, `twitter:card`) live in the shell; route-specific values
(`og:url`, `og:title`, `og:description`) live in the route component. A
route-specific value in the shell is wrong for every other route.

**S6**: OG image stays under 200KB and dimensions are declared.

---

## 5. Security (SEC)

**SEC1**: Every `target="_blank"` link carries `rel="noopener noreferrer"`.
Missing `rel` is a reverse-tabnabbing issue.

**SEC2**: No `dangerouslySetInnerHTML` except a documented, vetted case
(e.g. an inline theme-init script with no user input). Flag any new
occurrence immediately.

**SEC3**: No secrets, API keys, or credentials in client source or committed
`.env` files. Nuance: publishable keys, form IDs, booking URLs, and contact
emails are public config, do not false-flag them. Real secret material is 🔴.

**SEC4**: Middleware is not a security boundary (CVE-2025-29927: the
`x-middleware-subrequest` header can bypass it). Verify Next.js ≥ 15.2.3 in
`package.json`. Auth and access control belong in the data layer or inside
the action/route handler, never middleware alone.

**SEC5**: Security response headers set for all routes (via `headers()` in
`next.config.*` or `vercel.json`): `X-Frame-Options: DENY` (or CSP
`frame-ancestors`), `X-Content-Type-Options: nosniff`,
`Referrer-Policy: strict-origin-when-cross-origin`, ideally a CSP. Hosting
platforms do not add these automatically. Note in full audits; per-PR it is a
blocker only when a change weakens existing headers.

**SEC6**: No new third-party scripts or embeds without reviewing their data
collection and version pinning. When a CSP exists, a new embed's origins must
be added to `frame-src`/`connect-src`. Cookie-setting embeds are a
privacy-policy update trigger.

---

## 6. Performance (P)

**P1**: The LCP/hero image loads eagerly: `priority` on `next/image`, or
`loading="eager"` plus a preload hint in a Vite app. Lazy-loading the LCP
image is the most common Core Web Vitals regression.

**P2**: Images declare dimensions to prevent CLS: `width`/`height` (or
`fill` with a sized parent). The attribute values are the natural image
dimensions as stored on disk, not the CSS display size; browsers use them for
aspect-ratio before CSS applies. In Next.js, prefer static imports for local
images: dimensions and a blur placeholder come free.

**P3**: Fonts: `next/font` in Next.js; otherwise self-hosted or
`<link>`-loaded with `font-display: swap`. A raw Google Fonts link in Next.js
adds a cross-origin request chain and skips subsetting.

**P4**: Third-party `<script>` tags use `next/script` with an explicit
`strategy` (Next.js) or `defer`/`async` (SPA). Bare `<script>` blocks parsing.

**P5**: Image weight budget: 500KB hard limit per file in `public/`, 200KB
target for the OG image. Appropriate formats: SVG for icons, WebP or
compressed PNG/JPEG for raster.

**P6**: Static data (nav arrays, card configs, year values) is defined at
module scope, not inside component bodies. Per-render re-creation wastes work
and breaks referential equality for memoized children.

**P7**: Heavy embeds and SDKs (booking widgets, payment, chat) load only on
the route that uses them, lazy/dynamic-imported where possible. Never bundle
them into the shared shell.

**P8**: Large SPAs split routes with `React.lazy` + `Suspense` (Next.js
code-splits per route automatically). Flag a single-bundle SPA once it has
more than a handful of routes.

**P9**: No `console.log` / `console.warn` / `console.error` in production
code paths. An intentional empty `catch` is error handling, not debug output;
leave it.

---

## 7. TypeScript (T)

**T1**: No `any`. Genuinely unknown types use `unknown` with narrowing.
`as X` assertions only when provably correct at that call site, never to
paper over a real mismatch.

**T2**: No `React.FC` / `React.FunctionComponent`. Plain function
declarations with typed props parameters.

**T3**: `import type` for type-only imports.

**T4**: `interface` for component props; `type` for data shapes and unions.
Event handlers use React synthetic event types
(`React.MouseEvent<HTMLButtonElement>`), not `any` or DOM `Event`.

**T5**: Default prop values go in the destructured signature, not the
deprecated `defaultProps`.

---

## 8. Tailwind (TW) [gated: Tailwind]

**TW1**: Colors use the project's semantic tokens (`bg-background`,
`text-muted-foreground`, custom token utilities), never hardcoded values
(`bg-white`, `text-gray-700`, hex). Hardcoded colors break dark mode.

**TW2**: Respect the detected dark-mode mechanism. If it is
`[data-theme="dark"]` attribute selectors, the `dark:` variant is not
configured: do not use it. If theme init runs before React mounts (to prevent
a flash of wrong theme), do not change the init order or hardcode a default.

**TW3**: v4 projects: tokens live in the global CSS via `@theme` /
`@theme inline`, no `tailwind.config.*`. No v3-style `theme()` calls in CSS;
use `var(--token)`. Prefer explicit CSS properties over `@apply`. Use
`@theme` only for values that should generate utilities; plain `:root` vars
otherwise.

**TW4**: Conditional class merging uses `cn()` (clsx + tailwind-merge) when
the project has it: string concatenation silently drops a class when two
utilities conflict. When clsx is **not** installed, template literals are
fine; flag concatenation only where conflicting utilities genuinely collide,
and do not demand a new dependency.

**TW5**: Mobile-first: default classes target small screens, `md:`/`lg:`
widen. Flag components built desktop-first and shrunk down.

**TW6**: Arbitrary values (`[32px]`) only for one-off constraints with no
matching scale step. Flag arbitrary values duplicating standard steps
(`[16px]` instead of `4`).

**TW7**: Split inline-style pattern: when a `style` object mixes a
token-expressible value and a genuinely dynamic one (computed delays,
`color-mix()`, `clamp()`), move the token to `className` and keep only the
dynamic part inline.

---

## 9. Component Structure (C)

**C1**: Follow the project's existing file placement (pages vs sections vs
shared components vs hooks vs lib). Detect the convention, do not impose one.

**C2**: shadcn/ui primitives in `components/ui/` are vendored code: do not
edit them for project-specific needs. Customize via props, composition, or
theme tokens, so future shadcn updates stay clean.

**C3**: Composition over invalid nesting: use the `asChild`/Slot pattern
rather than wrapping `<Link>` inside `<Button>` (nested interactive elements
are invalid HTML and an a11y problem).

**C4**: A component significantly over ~300 lines is a signal to extract
named sub-components. Soft threshold; judge by navigability.

**C5**: Repeated literals (contact email, external URLs, brand names) are
centralized in a constants or copy module, not scattered. When the project
separates content from markup (a `data/` or `copy.ts` layer), new content
goes there, never hardcoded in JSX.

**C6**: Reuse before writing new: check existing utils, hooks, and shadcn/ui
before adding a custom primitive or duplicate logic.

---

## 10. Code Quality (Q)

**Q1**: No commented-out code. Delete dead blocks; intentionally deferred
work gets `// TODO:` with a reason.

**Q2**: No dead code, backwards-compatibility shims, `_unused` renames, or
re-exports for removed code.

**Q3**: Imports ordered external-then-internal, no unused imports. Internal
imports use the project's alias (`@/`) when one is configured.

**Q4**: One package manager. No foreign lockfiles committed
(`package-lock.json` next to `bun.lock`, etc.).

**Q5**: Copy hygiene in any user-visible string the diff touches: no em
dashes (use a period, colon, comma, or parentheses), no AI-flavored patterns
("seamlessly", "nestled", "perfect blend of X and Y", trailing summaries).
Verbatim third-party text (reviews, quotes) is exempt. Project CLAUDE.md copy
rules are authoritative and stricter rules there win.
