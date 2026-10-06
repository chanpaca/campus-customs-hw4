# Campus Customs — Usability Improvements (Problem 9)

Four usability improvements — two on the frontend, two in the agent/backend — each aimed at making the shopper's path shorter or the storefront's answers more trustworthy.

---

## Frontend

### 1. Chat suggestion chips

**What was added.** Three quick-start buttons inside the chat widget — **Show hoodies**, **Check size availability**, **Store hours** — shown above the composer until the shopper sends their first message. Each chip sends a pre-written question to the agent (e.g. "Show hoodies" sends *"What hoodies do you have?"*), then the chips disappear so they don't clutter an active conversation.

- Code: [`frontend/src/components/ChatWidget.tsx`](../frontend/src/components/ChatWidget.tsx) (`SUGGESTIONS`, rendered when `messages.length === 1`). The send path was refactored into a `send(text)` helper the chips and the text box both use, so a chip-sent message carries the same page context and auth as a typed one.

**Why it helps.** A blank chat box is a cold start — shoppers often don't know what to ask. The chips model good questions and get someone from "opened the widget" to "seeing hoodies" in one click, which lifts engagement. For the business, they gently steer conversations toward high-intent actions (browsing product, checking stock) and toward the store-info the shop wants surfaced.

### 2. Faster Products browsing — price pills & clear filters

**What was added.** The Products page already had a **search bar** and **category filter pills** (built in Problem 3). Problem 9 made browsing faster by adding:

- **Price-range pills** — *Under $50 / $50–$75 / Over $75* — applied **client-side** on the already-fetched list, so a click re-renders instantly with no server round-trip.
- A **Clear filters** button that appears only when a filter is active, resetting search, category, price, and the in-stock toggle in one click.
- The result count ("30 styles") updates live as filters change.

- Code: [`frontend/src/pages/Products.tsx`](../frontend/src/pages/Products.tsx) (`PRICE_BANDS`, `visibleProducts`, `clearFilters`).

**Why it helps.** Price is one of the first things a student shopper filters on; an instant band is faster than typing or scanning. "Clear filters" removes the dead-end feeling of an over-narrowed search. For the business, faster, friction-free filtering means shoppers see more of the catalogue and bounce less.

---

## Agent / Backend

### 3. Typo-tolerant product lookup

**What was added.** The product search tools now survive misspellings. If a query matches nothing as typed, each word is corrected to the nearest real catalogue word with `difflib` (fuzzy matching over a vocabulary built from product names, garment types, tags, and category synonyms) and the search is retried. So **"hoodei" → hoodies, "crewnck" → crewnecks, "quater-zip" → quarter-zips, "jaket" → jackets**, and a misspelled product name still resolves in `get_product_details` / `check_inventory`.

- Code: [`backend/tools.py`](../backend/tools.py) (`_vocabulary`, `_fuzzy_correct`, fuzzy fallback in `_find_matches` and `_resolve_product`). Uses only the standard-library `difflib` — no new dependency.
- **Bonus fix uncovered while building this:** matching was changed from raw substring to **word-boundary (prefix) matching**, because substrings like `shirt` and `tshirt` are literally inside `sweatshirt`, so a plain or fuzzy-corrected search for "tshirt" was wrongly returning every crewneck and hoodie. Word-boundary matching keeps "hood" → "hooded" working while stopping those collisions; category counts now match the catalogue exactly.

**Why it helps.** Typos are constant on phones. A search that returns "no results" for "hoodei" loses a sale the shopper was one keystroke away from. Tolerant lookup means the agent finds the right item anyway, so Handsome Dan feels smart instead of brittle — and the business doesn't lose conversions to fat-fingered spelling.

### 4. Size recommendation assistance

**What was added.** A new **`size_guidance`** tool plus a prompt guideline. The tool returns a fit label and plain advice for a product or garment type, based on general collegiate-apparel conventions:

| Category | Fit | Advice (abridged) |
|---|---|---|
| Hoodie | runs slightly roomy | heavyweight fleece; size down for a fitted look |
| Crewneck | true to size | classic cut; size up to layer |
| T-shirt | true to size | garment-washed; size up for looser |
| Quarter-zip | true to size, lightly relaxed | room for a layer |
| Jacket | roomy for layering | take usual size over a sweater |
| Long-sleeve (performance) | athletic / trimmer | size up for more room |

The system prompt now tells the agent to call `size_guidance` for any fit question, to be honest and specific, and to confirm the suggested size is in stock with `check_inventory`.

- Code: [`backend/tools.py`](../backend/tools.py) (`size_guidance`, `_FIT_BY_CATEGORY`), model `SizeGuidance` in [`backend/models.py`](../backend/models.py), guideline in [`backend/prompts/prompt.md`](../backend/prompts/prompt.md).
- **Honesty note:** the catalogue has **no measurement or fit data**, so this advice is general collegiate-apparel convention, not per-product spec. It's encoded consistently so the agent gives the same honest guidance every time rather than inventing numbers.

**Why it helps.** "What size should I get?" is the question that stalls an online apparel purchase. Clear, consistent fit advice — and a nudge to confirm stock in that size — reduces hesitation and, for the business, the returns and size-swap requests that eat margin.

---

## A note on live verification

The Portkey API key is over its usage quota (`412`), so the live LLM can't be exercised. All four features were verified without it: the frontend features in the browser (chips send the right message and render cards; price pills filter instantly and clear resets), and the backend tools directly against the database (fuzzy corrections, word-boundary counts matching ground truth, and `size_guidance` output per category). What remains unverifiable until the quota resets is the *model's* judgment in choosing to call `size_guidance` or in phrasing fit advice — the tools and prompt are in place and correct.
