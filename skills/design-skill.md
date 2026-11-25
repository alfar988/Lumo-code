---
name: design-skill
description: Design UIs, GUIs and CSS that look made for the subject: brief, direction, tokens, palettes, type, layout, components with all states, motion, accessibility, game HUDs, dashboards, forms, terminal output, copy and a review loop, with ready CSS.
---
# Design skill (UI, GUI, CSS)

For a small edit to an existing page (a color, a label, a spacing), change only what was asked and keep the page's own tokens. The brief, direction and layout parts below are for building something new.

Good design here means: one clear direction chosen for THIS subject, a small token system, generous spacing, readable type, every state of every control, honest content. **Start from a template** (`use_template("web-landing")` for sites, `"web-app"` for tools) and rebuild it for the subject; both score 100/100 on `review_ui`, and a page that only changes the title and the accent is sent back.

## Quick rules (read first)
1. Write a 5-line brief before any code: subject, audience, the one job of the screen, three mood words, constraints (device, language, offline). If the request does not say, propose one in a single line and go on.
2. Choose ONE direction for this subject (part 1, section "Pick the direction") and write it in a CSS comment. Never start from the look you would give every page.
3. Tokens first: color roles, spacing scale, type scale, radius, shadow, motion. Components use tokens only: no stray `#hex` or `13px` inside a component.
4. Text contrast at least 4.5:1 (3:1 for large text and for borders of controls). One accent color is enough; neutrals do the rest.
5. Every interactive element has default, hover, `:focus-visible`, active, disabled and (when it waits or fails) loading and error states. Touch targets are 44px or more.
6. Design at 360px wide first. No horizontal scroll, ever. Respect `prefers-reduced-motion` and `prefers-color-scheme`.
7. Real content from the request: no lorem ipsum, no invented numbers, testimonials, logos or ratings. Icons are inline SVG, not emoji.
8. Spend boldness in ONE place (the hero, a number, a color field, a type moment). Keep everything around it quiet. Before you finish, remove one decoration.
9. Build, then `verify_files`, `review_ui`, fix every HIGH and MEDIUM finding, and look again with the checks in the last part.

## Safety in this skill
- No dark patterns: no fake countdowns or "only 2 left", no hidden unsubscribe or close button, no pre-ticked consent, no buttons that lie, no confirm-shaming ("No, I hate saving money").
- No invented testimonials, ratings, statistics, awards or logos of real companies. Do not copy the look of a bank, a government site or a login page to make people believe it is that site.

## The process (do these in order, keep the notes short)
1. **Brief.** Subject, audience, the one job of the screen, mood words, constraints.
2. **Design plan** in a few lines (put it in a CSS comment at the top of the file):
   - Color: 4 to 6 named hex values (bg, surface, ink, muted, accent, accent-ink).
   - Type: the typefaces and their roles (one family or two; two only if clearly different).
   - Layout: one sentence plus a tiny ASCII wireframe, and the alignment (left, centered, split).
   - Principle: what makes this page unlike a generic page for the same subject.
3. **Check the plan against the brief.** If a choice is what you would produce for any similar page (the same palette, the same three cards, the same centered hero), change it and note what you changed. The brief's own words always win, even when they ask for a look you usually avoid.
4. **Build** with tokens, mobile first, semantic HTML (`header`, `nav`, `main`, `section`, `footer`, `button`, `label`).
5. **States and content:** all control states, real copy, empty and error states, loading.
6. **Review** with `review_ui` and the checks in part 5; fix; look again.

## Pick the direction (one per page)
| Direction | Fits | Traits |
|---|---|---|
| Editorial | blogs, magazines, portfolios, essays | serif display, generous margins, narrow text column, quiet accent, thin rules only where they mean something |
| Warm minimal | personal sites, cafes, small shops, notes | off-white background, one earthy accent, soft radius, plenty of space |
| Soft neutral | SaaS, tools, admin, forms | cool grey surfaces, one blue or green accent, 8 to 12px radius, subtle shadow, dense but airy |
| Technical | dev tools, docs, terminals, hacker tools | dark surface, monospace for data only, sharp or 4px radius, one signal color, tabular numbers |
| Bold graphic | events, music, fashion, campaigns | huge type, flat color fields, hard shadows or none, strong asymmetry, high contrast |
| Playful | kids, learning, casual games | rounded shapes, 2 to 3 saturated colors, big friendly type, bouncy motion that answers a tap |
| Game HUD | games | dark scene, one bright accent, outlined text, icons over words, minimal chrome (part 4) |
| Calm wellness | health, meditation, travel, nature | muted greens and blues, large soft shapes, slow motion, lots of whitespace |
If the user gave no style, choose by the subject: tools and business get soft neutral, personal and local get warm minimal, games get game HUD, learning for children gets playful. Do not reuse the same direction and palette on every project: the subject's own world (its materials, objects, vocabulary) is where the distinct choices come from.

## 1. Tokens first
```css
:root {
  /* direction: soft neutral. accent: blue. radius 12px. density: airy */
  --bg: #f3f5f8;  --surface: #ffffff;  --ink: #18202b;  --muted: #566070;  --line: #dde2ea;
  --accent: #2f5fd0;  --accent-ink: #ffffff;  --accent-soft: #e8eefb;
  --ok: #1b7a4b;  --warn: #8a5a00;  --danger: #b3261e;
  --radius-s: 8px;  --radius: 12px;  --radius-l: 20px;
  --shadow-1: 0 1px 2px rgba(16,24,40,.06);
  --shadow-2: 0 1px 2px rgba(16,24,40,.06), 0 8px 24px rgba(16,24,40,.08);
  --space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px; --space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 72px; --space-9: 104px;
  --font: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --ease: cubic-bezier(.2, .7, .2, 1);  --fast: 120ms;  --base: 200ms;  --slow: 420ms;
  --z-nav: 20;  --z-modal: 40;  --z-toast: 60;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #0f1419; --surface: #171d24; --ink: #e8edf2; --muted: #9aa6b2; --line: #2a333d; --accent: #7aa7ff; --accent-ink: #07111c; --accent-soft: #1b2740;
          --ok: #5fd08f; --warn: #f0b84a; --danger: #ff8a80; }
}
```
Rules: name tokens by role (`--ink`, `--surface`), not by value (`--blue-500`). Dark mode is a second set of the same names, never `filter: invert`. Raise surfaces with lighter greys, not with bigger shadows. Spacing comes from the scale only; use `gap` and `padding`, avoid margins that fight each other.
A user-facing theme switch: set `data-theme="dark"` on `<html>` and repeat the dark tokens under `:root[data-theme="dark"]`; remember the choice in `localStorage` inside try/catch.

## 2. Color
Ready palettes (chosen by subject; adapt the hue to the subject instead of copying). All pairs below pass 4.5:1; the check runs in the tests and you can run it on your own colors:
```python
# check: runs
def lum(h):
    h = h.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

def contrast(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)

PALETTES = {   # name: (bg, surface, ink, muted, accent, text on accent)
    "paper":    ("#f7f5f0", "#ffffff", "#1f2328", "#5b616a", "#1b6e50", "#ffffff"),   # editorial, warm minimal
    "mist":     ("#f3f5f8", "#ffffff", "#18202b", "#566070", "#2f5fd0", "#ffffff"),   # SaaS, tools, admin
    "ocean":    ("#f1f7f8", "#ffffff", "#12292b", "#4a6366", "#0b7285", "#ffffff"),   # wellness, travel
    "forest":   ("#f4f7f0", "#ffffff", "#1d2a1d", "#55655a", "#2d6a2f", "#ffffff"),   # food, eco, outdoors
    "candy":    ("#fff6ec", "#ffffff", "#3b2a20", "#6f5848", "#c2410c", "#ffffff"),   # playful, kids, learning
    "signal":   ("#f4f4f0", "#ffffff", "#111111", "#4d4d4d", "#d6001c", "#ffffff"),   # bold graphic, campaigns
    "midnight": ("#0f1419", "#171d24", "#e8edf2", "#9aa6b2", "#5aa9ff", "#07111c"),   # dark tools, dashboards
    "terminal": ("#0c0f0c", "#131813", "#d7e6d7", "#8fa38f", "#62d26f", "#07100a"),   # technical, hacker
    "ember":    ("#12100e", "#1c1916", "#f3ece4", "#b3a699", "#ff8a3d", "#1a0f05"),   # game HUD, action
    "plum":     ("#15101c", "#1f1829", "#efe9f7", "#aa9fbb", "#c08bff", "#1a0d2b"),   # music, creative, night
}
for name, (bg, surface, ink, muted, accent, on) in PALETTES.items():
    assert contrast(ink, bg) >= 7, name          # body text
    assert contrast(muted, surface) >= 4.5, name    # secondary text
    assert contrast(on, accent) >= 4.5, name        # button label
    assert contrast(accent, bg) >= 3, name          # accent as a border, icon or large text
assert contrast("#aaaaaa", "#ffffff") < 3            # light grey text on white fails
print("palettes ok")
```
How to build your own palette:
- **60 / 30 / 10:** about 60% background, 30% surface and text, 10% accent. If everything is accented, nothing is.
- **Neutrals tinted toward the accent hue** (a slightly blue grey beside a blue accent) look designed; pure `#000` on pure `#fff` is harsh, and `#0B0B0B` standing in for black is a generator habit.
- **Status colors** carry meaning only (`--ok`, `--warn`, `--danger`) and never rely on color alone: add an icon or a word.
- **Accent as text on dark:** lighten it (`color-mix(in srgb, var(--accent) 55%, white)`); on light backgrounds darken it until 4.5:1.
- **Gradients:** subtle, one hue family, used behind one hero block, never on body text, never purple-to-pink by default.
- **Colour-blind safe data colors** (Okabe-Ito): `#0072b2 #d55e00 #009e73 #cc79a7 #e69f00 #56b4e9`. Pair color with shape, label or pattern; on white use the darker ones for thin lines.
- **Contrast on images:** put a solid or gradient scrim behind text (`linear-gradient(transparent, rgba(0,0,0,.65))`) and check the text against the scrim, not the photo.

## 3. Typography
```css
body   { font: 400 1rem/1.6 var(--font); color: var(--ink); background: var(--bg); -webkit-text-size-adjust: 100%; }
h1     { font-size: clamp(2.2rem, 5.6vw, 3.75rem); line-height: 1.05; letter-spacing: -.025em; font-weight: 700; text-wrap: balance; }
h2     { font-size: clamp(1.6rem, 3.6vw, 2.4rem);  line-height: 1.15; letter-spacing: -.02em;  font-weight: 700; text-wrap: balance; }
h3     { font-size: 1.25rem; line-height: 1.3; font-weight: 650; }
p, li  { max-width: 66ch; text-wrap: pretty; }
small, .caption { font-size: .875rem; color: var(--muted); }
.num   { font-variant-numeric: tabular-nums; }          /* tables, prices, scores, timers */
code, kbd { font-family: var(--mono); font-size: .92em; }
```
- **Scale:** pick one ratio and stay on it. Base 16px with ratio 1.25 gives 13, 16, 20, 25, 31, 39, 49. Use 6 to 8 sizes in total; fluid sizes only for headings (`clamp()`).
- **Hierarchy** comes from size, weight and space first, color last. Three levels per screen are enough: title, body, caption.
- **Line length** 45 to 75 characters (`max-width: 66ch`). Serif body gets slightly more line-height than sans (1.65 vs 1.55). Headings are tight (1.05 to 1.2), body is loose (1.5 to 1.7).
- **One family or two.** If two, make them clearly different (a serif display with a neutral sans body, or a grotesque with a mono for data). A second family must have a job.
- **Safe stacks without downloads:** modern `system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`; editorial serif `ui-serif, "Iowan Old Style", Georgia, "Times New Roman", serif`; rounded friendly `ui-rounded, "Nunito", "Segoe UI", system-ui, sans-serif`; technical `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`. If you load a web font, use at most two families and three weights, `display=swap`, and keep the stack as fallback; check the page when the font is missing.
- **Avoid** a tracked-out ALL-CAPS eyebrow above every heading, one random word in a different color inside a headline, middle-dot strings ("A · B · C") as decoration, and arrows appended to every link. Use all caps only for short labels that really are labels.
- **Text in other languages:** Indonesian and many other languages run 20 to 30% longer than English. Buttons and cards must grow, not clip: no fixed widths on text, `overflow-wrap: anywhere` for long words, test with the longest label. Format for the user's locale: `24 Nov 2026`, `Rp 25.000`, `1.234,5`.
- **Alignment:** left-align text blocks (centered only for short headings and CTAs); numbers in tables align right; do not mix three alignments in one section.

## 4. Layout and spacing
```css
.wrap   { width: min(100% - 32px, 1080px); margin-inline: auto; }                       /* container */
.grid   { display: grid; gap: var(--space-4); grid-template-columns: repeat(auto-fit, minmax(min(100%, 240px), 1fr)); }   /* responsive cards, no media query */
.stack > * + * { margin-top: var(--space-4); }                                          /* vertical rhythm */
.row    { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: center; }
.split  { display: grid; gap: var(--space-6); align-items: center; }
@media (min-width: 860px) { .split { grid-template-columns: 1fr 1fr; } .split.flip > :first-child { order: 2; } }
.sidebar-layout { display: grid; gap: var(--space-5); }
@media (min-width: 900px) { .sidebar-layout { grid-template-columns: 260px minmax(0, 1fr); } }
section { padding-block: clamp(40px, 8vw, 88px); }
.full   { min-height: 100vh; min-height: 100dvh; }
```
- **Spacing is a system:** 4px base; related things sit close (8 to 12px), groups apart (24 to 32px), sections far apart (64 to 104px). Equal padding everywhere reads as flat; vary it on purpose.
- **Alignment:** pick a few edges and align to them. Use `gap` instead of margins between siblings. Align baselines of text in a row.
- **Hierarchy test:** squint at the page (or look at a grayscale screenshot). You should still see what is first, second and third. If two things compete, shrink or quiet one.
- **Rhythm:** vary the sections (full-bleed color band, split, grid, list, large quote) so the page does not read as one repeated block. Three identical rounded cards in a row under a centered hero is the generic pattern; ask what the content really is (a list, a table, a timeline, a comparison) and let the content choose the shape.
- **Breakpoints:** start at 360px; add `@media (min-width: 640px)`, `860px`, `1100px` only when the layout actually breaks. Prefer intrinsic layouts (`auto-fit`, `minmax`, `clamp`, `flex-wrap`).
- **Hero patterns** (pick by subject, do not default to "big number + three stats + gradient"): headline with a live demo; headline beside a drawn illustration; a full-bleed image with scrim; a single large number that matters; an interactive toy; a short before/after; a product shot on a color field.
- **Bento / uneven grids** look designed when sizes follow importance:
```css
.bento { display: grid; gap: 14px; grid-template-columns: repeat(6, 1fr); }
.bento > :nth-child(1) { grid-column: span 4; grid-row: span 2; }
.bento > :nth-child(n+2) { grid-column: span 2; }
@media (max-width: 760px) { .bento { grid-template-columns: 1fr; } .bento > * { grid-column: auto !important; grid-row: auto !important; } }
```
- **Selector care:** keep specificity flat (one class per element). A `.section` rule and an element rule such as `.cta` can cancel each other's padding; set spacing in one place (the container) and check the result.

## 5. Components (all states, ready CSS)
```css
.btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); min-height: 46px; padding: 0 var(--space-5);
       border: 1px solid transparent; border-radius: 999px; background: var(--accent); color: var(--accent-ink); font: 600 1rem var(--font); cursor: pointer;
       transition: transform var(--fast) var(--ease), box-shadow var(--fast) var(--ease), background-color var(--fast); }
.btn:hover  { box-shadow: var(--shadow-2); transform: translateY(-1px); }
.btn:active { transform: none; box-shadow: none; }
.btn:disabled, .btn[aria-disabled="true"] { opacity: .5; cursor: not-allowed; transform: none; box-shadow: none; }
.btn[aria-busy="true"] { position: relative; color: transparent; pointer-events: none; }
.btn[aria-busy="true"]::after { content: ""; position: absolute; width: 18px; height: 18px; border: 2px solid var(--accent-ink); border-right-color: transparent; border-radius: 50%; animation: spin .7s linear infinite; }
.btn.secondary { background: transparent; color: var(--ink); border-color: var(--line); }
.btn.ghost     { background: transparent; color: var(--accent); }
.btn.danger    { background: var(--danger); color: #fff; }
:focus-visible { outline: 3px solid var(--accent); outline-offset: 3px; }
@keyframes spin { to { transform: rotate(360deg); } }

.card  { background: var(--surface); border: 1px solid var(--line); border-radius: var(--radius); padding: var(--space-5); }
.field { display: grid; gap: var(--space-2); }
.field label { font-weight: 600; }
.field .hint { color: var(--muted); font-size: .875rem; }
.field .error { color: var(--danger); font-size: .875rem; }
input, select, textarea { font: inherit; color: inherit; min-height: 46px; padding: 10px 14px; background: var(--surface); border: 1px solid var(--muted); border-radius: var(--radius-s); width: 100%; }
input:hover, select:hover, textarea:hover { border-color: var(--ink); }
input:disabled { background: var(--bg); color: var(--muted); }
[aria-invalid="true"] { border-color: var(--danger); box-shadow: 0 0 0 1px var(--danger); }
.badge { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8125rem; font-weight: 600; background: var(--accent-soft); color: var(--ink); }
@media (prefers-reduced-motion: reduce) { *, *::before, *::after { animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; scroll-behavior: auto !important; } }
```
```html
<!-- a field: label, hint, error wired for screen readers -->
<div class="field">
  <label for="email">Email</label>
  <input id="email" type="email" autocomplete="email" inputmode="email" aria-describedby="email-hint email-err" required>
  <span id="email-hint" class="hint">We send the receipt here.</span>
  <span id="email-err" class="error" role="alert" hidden>Enter an address like name@example.com.</span>
</div>
```
- **Forms:** one column; label above the input (never placeholder as label); right `type`, `autocomplete`, `inputmode`; validate on blur and again on submit; the error sits next to the field, says what is wrong and how to fix it; keep the typed value; the primary button names the action ("Create account") and shows a busy state while it works; after success say what happened.
- **Navigation:** at most 5 top-level items; the current page is marked (`aria-current="page"`); on phones a bottom bar of 3 to 5 icons-with-labels or a menu button with a real `<button>`; sticky header height under 64px.
- **Modal:** use `<dialog>` and `showModal()` (focus trap and Esc for free); the first control gets focus; close button 44px with `aria-label="Close"`; click outside closes only when nothing is lost; return focus to the opener.
- **Toast:** `role="status"` (or `alert` for errors), appears for 4 to 6 seconds, never the only place an error is shown, bottom of the screen on phones, does not cover the primary button.
- **Table:** numbers right-aligned with `.num`, sticky header, zebra or row lines (not both), on phones either scroll inside `overflow-x: auto` or stack rows with `data-label` pseudo-labels.
- **Empty state:** an invitation to act ("No tasks yet. Add your first task"), one button, optionally a small drawing. **Loading:** skeletons shaped like the content, not a lone spinner; keep layout stable (no jumping).
- **Cards:** one radius family (`--radius`), one border style. Hover lift only on cards that are clickable. Not every block needs to be a card.
- **Icons:** inline SVG, `stroke="currentColor"`, 24px grid, 2px stroke, one style across the page; decorative icons get `aria-hidden="true"`, meaningful ones an accessible name.
- **Images:** set `width` and `height` (no layout shift), `loading="lazy"` below the fold, `alt` that says what the image shows (empty `alt=""` for decoration). Draw hero art with SVG or CSS when no file is given.

## 6. Motion, accessibility, responsive, performance
- **Motion has a job:** show what changed (open, expand, confirm), draw the eye once (one orchestrated page-load moment), or give feedback to a tap. Durations: 100 to 150ms for hovers and presses, 200 to 300ms for panels, 400 to 600ms for one hero entrance. Ease out for entering, ease in for leaving. Animate `transform` and `opacity` only. Fade-and-slide-up on every section and hover transitions on every card are the generic default: skip them.
- **Reduced motion:** the media query above is mandatory; also stop autoplaying video and parallax for it.
- **Accessibility floor (WCAG 2.2 AA):** contrast 4.5:1 text and 3:1 UI parts; visible focus; everything works with the keyboard in a logical order; targets 44px (24px minimum with spacing); labels for every input; `lang` on `<html>`; one `<h1>`, headings in order; links say where they go ("Read the guide", not "Click here"); do not rely on color alone; no content only on hover; zoom to 200% without loss; `aria-live` for async updates; a "skip to content" link on pages with a long header.
- **Responsive:** test at 360, 768 and 1280px wide, portrait and landscape; viewport tag `width=device-width, initial-scale=1`; use `100dvh`, `env(safe-area-inset-bottom)` for bars near the screen edge; never disable zoom; `@media (hover: hover)` for hover-only effects; `touch-action` and `user-select` only where a control needs them.
- **Performance:** no framework needed for a landing page; one CSS file or `<style>`; images sized and compressed; no autoplay audio; do not block rendering with big scripts; system fonts or at most two web fonts.

## 7. Special contexts
**Game UI and HUD** (browser games, Three.js, canvas)
- Anchor HUD parts to the corners and keep the center free: health and ammo bottom-left or top-left, score top-center or top-right, pause top-right, minimap in a corner. Respect safe areas on phones (`padding: env(safe-area-inset-top) env(safe-area-inset-right) ...`).
- Touch controls: joystick base about 120px, buttons 64 to 72px, semi-transparent (opacity .5 to .7, brighter while pressed), placed under the thumbs; `touch-action: none; user-select: none; -webkit-tap-highlight-color: transparent;` on the control layer; never put two controls closer than 16px.
- Readability: white or light text with a dark outline (`text-shadow` in four directions or `-webkit-text-stroke`), numbers in `font-variant-numeric: tabular-nums`, icons before words, bars with a shape cue besides color (a health bar has a segment ticks pattern, damage flashes the edge).
- Menus: a title, one big Play button, Settings and Shop below, a visible Back; the menu reuses the game's palette and type; show a short control hint the first time only.
- Feedback: a hit flashes, a pickup pops, a level-up pauses a moment; shake the camera a few pixels, never the HUD. Keep canvas crisp: scale by `devicePixelRatio`, and lock the layout with `max-width: 100vw; max-height: 100dvh`.
- Landscape: ask for landscape with a rotate hint when the game needs it; do not rely on locking the orientation.

**Dashboards and data**
- A KPI card is a label, one number, a unit and a change with an arrow and a word ("up 12% on last week"). Put the most important figure first, large; everything else small.
- Charts: title says the finding, axes are labeled with units, label lines directly instead of a legend when possible, bars start at zero, no 3D, no pie with more than five slices, at most five series, color-blind safe set above, gridlines faint. Tooltips repeat the exact value. Empty data says so.
- Tables: filter and sort controls above, sticky header, right-aligned numbers, units in the header, row actions at the end, paging or "load more" for long lists.
- Density: pick compact (8px rows) for power users, comfortable (12 to 16px) for everyone else; do not mix.

**Landing pages and shops**
- Order: what it is and for whom (headline, one line, one button) → proof that is real (a demo, a screenshot, a number you actually have) → how it works (3 steps if it is a sequence) → details or pricing → FAQ (`<details>`) → final call to action. Pricing: at most three plans, highlight one, show what is included, say what happens after the trial.
- Product cards: image, name, price (formatted for the locale), one-tap add, honest stock info. No fake scarcity.

**Terminal and CLI output** (Lumo itself, scripts, tools)
- Fit 72 columns by default (phones); align columns; one blank line between groups; a short title, then the result, then the next step.
- Color means something: green done, yellow warning, red error, dim secondary text; honor `NO_COLOR`; never color-only meaning (also print `ok`, `warn`, `error`).
- No emoji clutter, no ASCII-art banners that wrap, no spinners in non-interactive output. Progress: `3/12 done` beats a long bar. Errors say what failed, why, and the command to fix it.

**Mobile app screens** (PWA, mockups)
- Thumb zone: primary actions in the lower half; top bar for title and one action; bottom nav 3 to 5 items; sheets rise from the bottom; keyboards push content up (use `100dvh` and `scroll-padding`).
- One primary action per screen; secondary actions are text buttons; lists have 56 to 72px rows with a clear tap area.

## 8. Avoid the generic-AI look
Common clusters of generated design (all legitimate for some briefs, but defaults, not choices):
- warm cream background with a high-contrast serif and a terracotta accent;
- near-black background with one acid-green or vermilion accent;
- newspaper layout with hairline rules, zero radius and dense columns;
- the SaaS kit: identical rounded cards, one radius everywhere, the same grey shadow, gradient washes as decoration, glass panels;
- template chrome: a small ALL-CAPS tracked eyebrow above every heading, `A · B · C` meta strings, `WORD — fragment` labels, a monospace face for tiny labels, `→` on every link, numbered `01 / 02 / 03` markers on content that is not a sequence.
Where the brief names a look, follow it exactly. Where it does not, do not spend your freedom on these. Also avoid purple or indigo to pink gradients, gradient text, glow on everything, emoji icons, "Welcome to my website", stock-photo placeholders, heavy drop shadows, blurry text and glass behind numbers.
Structure is information: borders, dividers, numbering and labels exist to say something about the content. A number marker is for a real sequence; a divider separates real groups.

## 9. Make it yours (a template is a start, not the result)
Lumo compares your page with the template and sends you back when it is too similar. Changing the accent and the title is not design. Build the page for THIS subject and add nothing the request did not call for:
- **Identity:** 3 to 4 tokens (surface, ink, accent, one secondary tone), a deliberate type pairing, one shape language (sharp, soft, pill).
- **Real content and structure:** write the copy for THIS subject; remove sections that do not apply, add ones that do (gallery, timeline, comparison table, case studies, menu, schedule, location, team).
- **A custom hero visual** drawn with inline SVG or CSS, not the template's preview card:
```html
<svg viewBox="0 0 320 240" role="img" aria-label="Illustration of rising bars with a sun">
  <circle cx="250" cy="52" r="26" fill="var(--accent-2, var(--accent))"/>
  <rect x="40" y="130" width="46" height="80" rx="10" fill="var(--accent)" opacity=".35"/>
  <rect x="104" y="96" width="46" height="114" rx="10" fill="var(--accent)" opacity=".6"/>
  <rect x="168" y="58" width="46" height="152" rx="10" fill="var(--accent)"/>
  <path d="M20 214h280" stroke="var(--line)" stroke-width="3" stroke-linecap="round"/>
</svg>
```
- **A different rhythm:** split sections, a bento grid, one huge type moment, alternating rows, a full-bleed color band.

## 10. Writing the words (copy is design)
- Words exist to make the design easier to use. Ask what the screen must say, then say it once.
- Write from the user's side: name things by what the person does, not how the system is built ("Notifications", not "Webhook config").
- Buttons say what happens ("Save changes", "Send invoice"), the same action keeps the same name through the flow (Publish → "Published").
- Errors say what happened and how to fix it, in the interface's voice, never vague and never apologizing. Empty screens invite action.
- Sentence case, plain verbs, active voice, no filler, one job per element. Use the user's language and keep one register ("kamu" or "Anda", not both).
- A headline says what it is; the line below says for whom; no fake stats or social proof.

## 11. The review loop (do it every time)
1. Build with tokens. 2. `verify_files`. 3. `review_ui`; fix every HIGH and MEDIUM finding with `edit_file`; repeat until the score is 85 or more. 4. Run these checks by looking at the page (`preview_web` gives the address):
   - **Squint test:** the first, second and third things are clear.
   - **Grayscale test:** hierarchy survives without color.
   - **3-second test:** a stranger can say what this is and what to press.
   - **Keyboard test:** Tab reaches everything in order, focus is always visible, Esc closes dialogs.
   - **360px and 200% zoom:** nothing overflows or hides.
   - **Longest text and empty data:** the layout holds.
   - **Reduced motion and dark mode:** both still look right.
5. Fix in this order: hierarchy, spacing, contrast, alignment, states, polish. 6. Remove one decoration. 7. Tell the user how to open it and what you chose and why, in two lines.

## Troubleshooting
| Problem | Fix |
|---|---|
| Looks cramped | Increase spacing tokens, line-height and section padding; reduce the number of things per row |
| Looks flat and boring | One bolder heading size, one accent block, consistent radius, real content, one memorable element |
| Looks generic | Re-read part 8; change the layout shape to fit the content, change the palette to the subject's world |
| Mobile overflow | Find the element wider than the viewport (fixed px width, long word, wide table): `max-width: 100%`, `overflow-wrap: anywhere`, scroll container for tables |
| Low contrast flagged | Darken text or the accent, or use dark text on a light accent; run the contrast check above |
| Dark mode unreadable | Redefine the tokens in the dark block; never hard-code colors in components |
| CSS rules cancel each other | Flatten selectors, move spacing to one owner, search for the property in the file |
| Layout jumps when content loads | Reserve space (`aspect-ratio`, `min-height`, skeletons), set image sizes |
| Text clipped in another language | Remove fixed widths, allow wrapping, test the longest label |

## Good and bad examples

### 1. Tokens
Bad: values scattered through the file.
```css
.card { color: #777; margin: 13px; padding: 11px 19px; border-radius: 7px; }
.note { color: #888; margin: 14px; }
```
Good: a small set of named values.
```css
:root { --text: #1d2430; --muted: #566070; --space-2: 8px; --space-3: 16px; --radius: 10px; }
.card { color: var(--text); margin: var(--space-3); padding: var(--space-2) var(--space-3); border-radius: var(--radius); }
.note { color: var(--muted); margin: var(--space-3); }
```

### 2. Focus
Bad: `button:focus { outline: none; }` leaves keyboard users lost.
Good: `button:focus-visible { outline: 3px solid var(--accent); outline-offset: 2px; }`

### 3. Contrast
Bad: light grey text `#aaa` on white (about 2.3:1). Good: `#566070` on white (about 6.4:1).

### 4. Honest copy
Bad: "Trusted by 10,000+ happy customers. Rated #1 worldwide." (invented)
Good: "Track your reading list. Add a book, mark it read, see your year at a glance." (says what it does)

### 5. Touch targets
Bad: a 24px icon button. Good: a 44px by 44px button with the icon centered and an accessible name (`aria-label="Close"`).

### 6. Layout that survives a phone
Bad: `width: 960px`. Good: `max-width: 960px; width: 100%; padding-inline: var(--space-3);` and a grid with `repeat(auto-fit, minmax(min(100%, 220px), 1fr))`.

### 7. Shape follows content
Bad: a price list as three identical cards with an icon each. Good: a table with the plans in columns and the shared features in rows, the recommended plan tinted, one button per column.

### 8. Boldness in one place
Bad: gradient hero, glowing cards, animated icons and a marquee on one page. Good: a quiet page where one oversized number or one color field carries the memory.

## Common mistakes and fixes
| Mistake | Fix |
|---|---|
| Purple gradient, glow and glass on everything | Pick a palette from the subject's world; use an effect once, with purpose |
| Three identical cards under a centered hero | Vary the layout: a list, a table, a split section, a real image |
| Text over a busy image | Add a solid or dark scrim behind the text and check contrast against the scrim |
| Many font sizes | Use a scale: 14, 16, 20, 25, 31, 39 |
| Animation on everything | Animate one meaningful change; turn it off for reduced motion |
| Only checked on desktop | Check 360px portrait and a short landscape view |
| Placeholder used as the label | A real `<label>` above the field |
| Color is the only signal | Add an icon or a word |
| Emoji as icons | Inline SVG |
| A template with only the title changed | Rebuild the layout, palette and copy for the subject |

## Checklist before you finish
- [ ] A brief and a design plan exist (direction, palette, type, layout) and the plan is not the generic default.
- [ ] Tokens are defined and used; there are no stray color or size values.
- [ ] Contrast, focus, touch targets and all control states pass; it works at 360px and at 200% zoom.
- [ ] Copy is real, specific and contains no invented facts, fake social proof or dark patterns.
- [ ] Dark mode (if offered) and reduced motion both work.
- [ ] One memorable element, everything else quiet; one decoration removed.
- [ ] `review_ui` ran and the HIGH and MEDIUM findings are fixed.
