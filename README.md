# Campus Customs — AI Shopping Assistant (MGT 409 · HW4)

A full-stack storefront for **Campus Customs**, a New Haven collegiate-apparel shop, with an
AI shopping assistant ("Handsome Dan") that answers questions from the **live store database** —
checking real inventory, searching the catalogue, and rendering results as shoppable product cards.

- **Frontend:** React + Vite + TypeScript (catalogue, product detail, auth, floating chat widget)
- **Backend:** FastAPI serving the catalogue/auth/chat API, plus a **PydanticAI** agent with
  database lookup tools
- **Data:** SQLite (`campus_customs.db`) + product imagery, served statically
- **LLM:** `gpt-4o-mini` reached through **Portkey** (an OpenAI-compatible gateway)

---

## Architecture

```
Browser ──► React app (Vite dev server, :5174)
                │  /api  and  /media  are proxied to the backend
                ▼
            FastAPI backend (uvicorn, :8001)
                ├── /api/products, /api/products/:id, /api/categories   (catalogue)
                ├── /api/auth/register | login | me                     (bcrypt + signed tokens)
                ├── /api/chat                                           (PydanticAI agent)
                ├── /api/chat/history                                   (per-user memory)
                └── /media/products/*.jpg                               (static images)
                        │
                        ▼
                  SQLite  campus_customs.db   (catalogue, inventory, users, chat_history)
                        │
                        ▼
              PydanticAI agent ──► Portkey gateway ──► gpt-4o-mini
                 tools: search_products · get_product_details · check_inventory · size_guidance
```

**How the chat stays honest:** the LLM only *names* products (by id); the backend *hydrates* the
authoritative name/price/image/stock from the database, and the agent is required to call its tools
for any price/stock/size question. Every interaction is appended to `output/audit_trail.json`.

---

## Directory layout

```
hw4/
├── AI_prompts.md          # log of the vibe-coding prompts used to build this
├── requirements.txt       # Python backend dependencies
├── .env.example           # environment template (copy to .env)
├── .gitignore
├── README.md              # this file
├── frontend/              # React + Vite + TypeScript app
│   ├── src/               # components, pages, api client, auth + page context
│   ├── index.html
│   └── package.json
├── backend/               # FastAPI + PydanticAI
│   ├── main.py            # app, routes (catalogue, auth, chat, history), audit wiring
│   ├── agent.py           # PydanticAI agent: model config + instructions + tool registration
│   ├── tools.py           # DB lookup tools (search / details / inventory / size guidance)
│   ├── models.py          # Pydantic request/response + tool-result models
│   ├── db.py              # SQLite connection + shared parsing helpers
│   ├── auth.py            # bcrypt hashing + HMAC-signed session tokens
│   ├── history.py         # chat_history persistence (customer memory)
│   ├── audit.py           # append-only JSON-Lines audit trail
│   ├── prompts/prompt.md  # system prompt: persona, tool rules, safety guardrails
│   └── requirements.txt
├── output/                # deliverables / reports
│   ├── harness.md         # data + system reference (schema, tools, guardrails, specs)
│   ├── design.md          # design-polish writeup
│   ├── usability.md       # usability-improvements writeup
│   ├── app_check.html     # standalone verification report (open by double-clicking)
│   ├── app_check_images/  # screenshots used by app_check.html
│   └── audit_trail.json   # append-only agent interaction log (JSON Lines)
└── data/                  # LOCAL DATA PACK — add this yourself (git-ignored)
    ├── campus_customs.db
    └── products/*.jpg
```

> The `data/` pack (database + images) is **not committed** — add it locally before running
> (see Setup). The backend also auto-detects the pack at `HW 4/data/data/` if that is where it
> shipped, or you can point `CAMPUS_CUSTOMS_DB` at the database directly.

---

## Prerequisites

- **Python 3.11+**
- **Node.js 18+** and **npm**

---

## Setup

Run these from the project (`hw4/`) root.

**1. Add the local data pack.** Place the database and product images so that they live at:

```
data/campus_customs.db
data/products/<product-slug>.jpg
```

(The images must sit in a `products/` folder next to the database — they are served at
`/media/products/...`.) Alternatively, set `CAMPUS_CUSTOMS_DB` in `.env` to the database's path.

**2. Create your environment file** and add your Portkey key:

```bash
cp .env.example .env
```

Then edit `.env` and set `PORTKEY_API_KEY`.

**3. Install backend dependencies:**

```bash
python -m pip install -r requirements.txt
```

**4. Install frontend dependencies:**

```bash
npm --prefix frontend install
```

---

## Running the app

Open **two terminals** (both from the project root).

**Terminal 1 — backend** (FastAPI on port 8001):

```bash
python -m uvicorn backend.main:app --reload --port 8001
```

**Terminal 2 — frontend** (Vite dev server on port 5174):

```bash
npm --prefix frontend run dev
```

Then open **http://localhost:5174**. The Vite dev server proxies `/api` and `/media` to the
backend on 8001, so both must be running.

To build the frontend for production:

```bash
npm --prefix frontend run build
```

---

## What's implemented

- **Storefront:** catalogue grid with search, category pills, price filters, and in-stock toggle;
  single-item detail pages with size/stock; responsive from phone to desktop.
- **Accounts:** register / login with bcrypt-hashed passwords and signed session tokens.
- **AI chat ("Handsome Dan"):** reads live inventory, searches the catalogue (typo-tolerant),
  gives size guidance, and renders matching products as cards that link to their detail pages.
  Clicking a chat card opens the same detail view.
- **Customer memory & page context:** logged-in shoppers' conversations persist to `chat_history`
  and reload on login; the product page a shopper is on is passed to the agent so "do you have
  this in Medium?" resolves correctly.
- **Safety & audit:** explicit behavioral guardrails in the system prompt, and an append-only
  audit trail of every interaction.

Full field-by-field reference, tool capabilities, guardrails, and system specs are in
[`output/harness.md`](output/harness.md).

---

## Notes

- **LLM quota:** the app calls `gpt-4o-mini` through Portkey. If the key is missing or over its
  usage quota, the chat endpoint returns a graceful error (`503`/`502`) and the UI shows it in the
  chat panel — the rest of the storefront is unaffected.
- **Ports:** 8001 (backend) and 5174 (frontend) are the defaults the proxy expects; change both
  together if needed (`--port` on uvicorn and the proxy target in `frontend/vite.config.ts`).
- **Playwright** is only needed to regenerate the verification screenshots, not to run the app.
