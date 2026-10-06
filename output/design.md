# Campus Customs — Design Polish (Problem 10)

How the storefront was elevated to read as an authentic, high-end collegiate shop — the visual decisions, and why each one earns customer trust and nudges conversion.

---

## 1. A cohesive color system

The palette is anchored on **Yale Blue `#00356B`** and built out as named CSS variables ([`frontend/src/index.css`](../frontend/src/index.css) `:root`) so every surface draws from one system instead of ad-hoc hex values.

| Role | Token | Value |
|---|---|---|
| Primary | `--navy` | `#00356B` (exact Yale Blue) |
| Deep navy (headers, gradients) | `--navy-deep` | `#06203F` |
| Primary accent | `--gold` | `#C8A951` (antique gold) |
| Secondary accent | `--crimson` | `#8F2D1B` (restrained rivalry crimson, used sparingly for errors) |
| Warm parchment background | `--cream` | `#F6F2E9` |
| Crisp product cards | `--paper` | `#FFFFFF` |
| Hairlines | `--line` | `#E4DDCD` |

- **Warm parchment, not flat beige.** The body background layers two faint radial gradients (a cool navy wash top-right, a warm gold wash bottom-left) over the cream, so the page has subtle depth and looks "printed," not sterile.
- **Crisp white cards on parchment** give products maximum contrast and a gallery-like separation — the single most important move for making merchandise feel premium.
- **Gold as the one accent that recurs** (nav underline, brand mark, chat trim, active states) ties the system together; crimson is reserved for genuine alerts so it keeps its signal.

## 2. Typography

- **Display serif — Fraunces** for all headings (loaded via Google Fonts with `display=swap`, falling back to Palatino/Georgia offline). Its high-contrast, slightly old-style letterforms read as collegiate and editorial without looking like a generic template.
- **UI sans — Inter** for navigation, buttons, chips, prices, and the chat — clean, legible, and modern, so the *shopping chrome* stays crisp while the *brand voice* stays classic.
- Tighter heading tracking (`-0.02em` on H1), a consistent uppercase **gold eyebrow** label above section titles, and comfortable line-height (1.65) on body copy for readability.

## 3. Depth, spacing & motion

- **A three-step elevation scale** (`--shadow-sm/md/lg`) using soft, warm-tinted navy shadows — never harsh black — applied consistently to cards, the filter bar, forms, the hero panel, the product-detail image, and the chat panel, so the whole UI shares one light source.
- **Product cards**: resting soft shadow → on hover they lift 4px, deepen to the large shadow, warm the border, and the **product image zooms 1.045×** behind a clipped frame — the tactile "pick me up" cue of a high-end retail grid.
- **Buttons** lift and deepen their shadow on hover and depress 1px on click; inputs get a soft Yale-blue focus ring.
- A **sticky filter bar** keeps search and categories in reach while scrolling the catalogue.
- All motion uses one shared easing curve, and everything is wrapped in a **`prefers-reduced-motion`** guard that disables animation for users who ask for it.

## 4. Chat UI polish

- **Custom message bubbles**: 16px rounded with a small tail (squared corner) on the sender's side; shopper bubbles use a navy → deep-navy **gradient** with a soft shadow, assistant bubbles are crisp white with a hairline border. Each bubble **fades and rises in** as it arrives.
- **Animated typing indicator**: three navy dots that bounce in sequence (replacing the old italic "…is typing" text), with an accessible `aria-label`.
- **Seamless scrolling**: `scroll-behavior: smooth`, a slim custom scrollbar tinted to the parchment, and auto-scroll to the newest message.
- The **panel pops in** from the bottom-right with a scale/opacity animation, and the launcher lifts on hover — small touches that make the assistant feel responsive and alive.

---

## How the design boosts trust & conversions

- **Credibility through consistency.** One palette, one type system, one shadow language signals a real, established shop — not a thrown-together page. Shoppers extend that trust to the products and to checkout.
- **Products look worth the price.** Crisp white cards, generous spacing, and the hover zoom frame each garment like gallery merchandise, which supports the $32–$98 price points and reduces "is this legit?" hesitation.
- **Faster, calmer browsing converts.** The sticky filter bar, instant price pills, and clear visual hierarchy cut the clicks between landing and finding the right piece — less friction, fewer bounces.
- **A polished assistant invites engagement.** A chat that animates, types, and renders clean product cards feels trustworthy enough to actually use, turning a passive browser into a guided, higher-intent shopper.
- **Restraint reads as premium.** Gold used once, crimson reserved for alerts, motion that's quick and never gaudy, and a reduced-motion fallback — the design feels confident and considered, which is exactly the signal a high-end collegiate brand wants to send.

---

## Accessibility & responsive layout

- **Consistent focus states.** Every interactive element — buttons, links, chips, size selectors, the in-stock checkbox, and all text inputs — shares one focus treatment. Buttons and links get a 2px Yale-blue outline on `:focus-visible` (keyboard users only, so mouse clicks stay clean), switching to **gold** on dark surfaces (nav, chat header, hero panel, launcher) for contrast. Text inputs get a soft blue ring whenever focused. This is defined once with a `:where(...)` selector rather than per-component, so nothing is missed.
- **Responsive from phone to desktop.** The layout is verified with no horizontal overflow at 375px and at 1280px:
  - The hero, product-detail, and stats strip collapse from two columns to one on narrow screens.
  - The product grid flows from four columns down to a single column; cards keep their spacing.
  - The nav brand, primary links, and account actions each take a centered full-width row on a phone.
  - The filter bar stops being sticky on mobile (so it doesn't eat the small viewport), the search goes full-width, and the pills wrap.
  - The chat panel widens to the full gutter-to-gutter width and caps its height at 68vh so it never overflows a short screen.
  - Gutters, heading sizes, and the footer all tighten on small screens.

---

### Verification

All changes were checked in the running app: Fraunces and Inter load (`document.fonts.check` true for both), the accent resolves to exactly `#00356B`, the nav underline and card shadows/radii match the tokens, the chat shows the pop-in panel, 16px bubbles, 3 animated typing dots, and smooth scrolling. Type-check and production build pass with no errors.
