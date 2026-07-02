# SHL Assessment Recommender

Conversational agent over the SHL Individual Test Solutions catalog.
Stateless FastAPI service: `GET /health`, `POST /chat`.

## 1. Get the full catalog (one-time, needs normal internet access)

This sandbox I built it in only has network access to pypi/npm/github-type
domains, so I could **not** run this step for you — you need to run it
once yourself, or let it run during your deploy build step:

```bash
python scrape_catalog.py
```

This fetches `shl_product_catalog.json`, filters out packaged Job
Solutions (see the docstring in `scrape_catalog.py` for the exact
heuristic — it's name-pattern based since the export has no explicit
"Individual Test Solution" flag; tighten it if you have access to the
live site's tab structure), and writes `data/catalog.json`.

A real 370-item catalog is already checked in at `data/catalog.json`
so the service runs out of the box for local testing and deployment.
A smaller 38-item sample used during early development is kept at
`sample_catalog_raw.json` for reference only. If you want to confirm
370 is the complete current SHL catalog (rather than re-verify it
yourself against the live site), re-run `scrape_catalog.py` before a
submission-critical deploy.

## 2. Configure the LLM key

```bash
export GROQ_API_KEY=gsk_...
```

The dialogue-decision call uses Groq's `openai/gpt-oss-120b` by default
(`SHL_AGENT_MODEL` env var to override — other options noted in
`app/llm.py` are `moonshotai/kimi-k2-instruct` and
`llama-3.3-70b-versatile`). `app/llm.py` talks to Groq through an
OpenAI-compatible client, so swapping to a different OpenAI-compatible
provider (OpenRouter, etc.) just means changing the `base_url` and env
var name — the rest of the app doesn't care which backend it is, as
long as `call_agent_decision()` still returns the same JSON shape.

## 3. Run locally

```bash
pip install -r requirements.txt
python scrape_catalog.py   # optional, refreshes data/catalog.json
uvicorn app.main:app --reload
curl localhost:8000/health
```

## 4. Deploy (free tier)

**Render**: New Web Service → connect repo → Build: `pip install -r
requirements.txt && python scrape_catalog.py` → Start: `uvicorn
app.main:app --host 0.0.0.0 --port $PORT` → add `GROQ_API_KEY` env
var. Cold start is normal on free tier; the evaluator allows 2 minutes
for the first `/health` call.

**Railway / Fly / HF Spaces**: the included `Dockerfile` works as-is —
just set `GROQ_API_KEY` as a secret and deploy.

## How it works

- `app/catalog.py` — loads `data/catalog.json`, does lightweight
  keyword+synonym retrieval (no embedding service needed) to build a
  grounding "candidate pool" for each turn.
- `app/llm.py` — single LLM call per turn (Groq by default); the model must return
  strict JSON (`action`, `reply`, `assessment_ids`, `end_of_conversation`)
  and can only pick `assessment_ids` from the candidate pool it was
  given — the app cross-checks every returned id against the pool
  before it's allowed into the response, so hallucinated catalog items
  can never reach the user.
- `app/main.py` — stateless `/chat`: rebuilds context from the full
  message history every call, runs a deterministic prompt-injection
  fast path before ever touching the LLM, then does one grounded LLM
  call per turn.

See `approach.md` for design rationale and evaluation notes.