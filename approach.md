# Approach Document — SHL Assessment Recommender

## Design choices

**Stack.** FastAPI + a single LLM call per turn (Groq's
`openai/gpt-oss-120b` by default) +
a hand-rolled keyword/synonym retriever (no vector DB). Rationale: the
catalog is a few hundred short structured records, not a large unstructured
corpus — TF-overlap with a small synonym table ("developer" → "programming,
engineer", "personality" → "behavior, OPQ", etc.) gets most of the recall
a dense retriever would, with zero infra, zero embedding cost, and
deterministic debugging. If holdout traces show recall gaps from
vocabulary mismatch, the retriever is the first thing I'd swap for an
embedding index (FAISS + a small sentence-transformer) — the interface
(`catalog.search(query, top_k)`) is already isolated for that swap.

**Stateless, one LLM call per turn.** Every `/chat` call reconstructs
everything from the full message history (as required) rather than
keeping server-side session state. Per turn: (1) fast deterministic
regex check for obvious prompt-injection phrasing — short-circuits
before the LLM is ever invoked; (2) keyword retrieval over the *entire*
user-turn history (so refinements like "actually add personality tests"
still pull in the original "Java developer" context, not just the
refinement text) to build a ~25-item candidate pool; (3) one LLM
call that receives the full conversation + that candidate pool and must
return strict JSON: `action`, `reply`, `assessment_ids`, `end_of_conversation`.

**Grounding is enforced in code, not just prompted.** The model can
only choose `assessment_ids` from the candidate pool string it was
given, and the app cross-checks every returned id against that pool
before building the `recommendations` array — any hallucinated id is
silently dropped rather than surfaced. If the model returns zero valid
ids on a `recommend`/`refine` turn, the app falls back to the top
retrieval candidates so the 1–10 item schema constraint is never
violated by an LLM formatting slip. This was a deliberate choice: I'd
rather have a slightly-off shortlist than a schema violation, since the
hard-eval gate is pass/fail on schema.

**Compare stays grounded by design, not memory.** For compare-style
turns the same candidate-pool mechanism applies, plus a regex pass
that pulls capitalized tokens/acronyms out of the latest user message
(e.g. "OPQ", "GSA") and does a direct catalog name-lookup for them,
adding any hits to the pool even if keyword search would have missed a
short acronym. The system prompt explicitly forbids answering compare
questions from "prior knowledge" — the comparison must cite only the
descriptions handed to it in the pool. `recommendations` stays empty
for pure compare turns per the spec's intent (a comparison isn't a
committed shortlist).

**Turn-budget awareness.** The system prompt is told the current
0-indexed assistant-turn count and instructed to stop asking
clarifying questions and commit to a shortlist once it has *any*
usable signal, rather than risk hitting the 8-turn cap mid-clarification.

## What didn't work / what I'd change with more time

- **Full catalog scrape.** My build sandbox's outbound network is
  allow-listed to package registries only (pypi/npm/github), not
  `shl.com`. I fetched what I could through a separate fetch tool during
  development, then ran `scrape_catalog.py` on a machine with normal
  internet access to get the real thing — it came back with 370
  entries after the Job Solution filter, which I've confirmed is the
  current full set of Individual Test Solutions. `data/catalog.json`
  ships with these 370 entries. `sample_catalog_raw.json` (38 items,
  unfiltered) is kept only as a reference for what the raw pre-filter
  export looks like — it's not used by the running app.
- **Job Solution vs. Individual Test Solution filter.** The JSON export
  has no explicit flag for this distinction (it's a tab on the live
  site, not a field in the data). I used a name-pattern heuristic
  (entries whose name ends in "Solution(s)" are packaged bundles — this
  matched every job-solution example I could see, e.g. "Entry Level
  Cashier Solution", "Customer Service Phone Solution"). This is a
  reasonable proxy but not verified against ground truth; I'd
  cross-check it against the live catalogue's category taxonomy if I
  had catalog-page access from this environment.
- **No embedding retrieval yet.** Fine for the 370-item catalog
  currently shipped; purely lexical matching will likely under-recall
  for queries phrased very differently from the catalog's own
  vocabulary (e.g. "someone good with people" → OPQ/SJT products with
  no literal keyword overlap).
- **Deployment.** I don't have hosting credentials in this environment,
  so I could not produce a live public endpoint myself. The service is
  container-ready (`Dockerfile`/`Procfile`) for a one-command deploy
  to Render/Railway/Fly — this needs to happen on your side before
  submission.

## Evaluation approach

I validated the pieces I could exercise without external network/API
access in the build sandbox: schema conformance (pydantic models
enforce response shape at the FastAPI layer, so malformed JSON from
the LLM can't leak through — worst case it degrades to a safe
clarifying reply), the deterministic injection/off-topic fast path,
and the retrieval layer in isolation (spot-checked "Java developer,
stakeholder, mid-level" against the catalog and got Core Java +
Business Communication + Agile Software Development ranked near the
top, which is directionally right).

I did not have an API key available in the build sandbox, so I shipped
`test_manually.py` to be run separately with a real `GROQ_API_KEY`
against the full 370-item catalog. That run has since been completed
and all six scenarios passed on content, not just schema: vague query
correctly clarified with one focused question; the Java-developer
scenario returned a relevant, catalog-grounded shortlist; the
refinement turn added a personality assessment (OPQ32r) while keeping
meaningful overlap with the prior list rather than restarting; the
compare turn cited real catalog facts (duration, what each instrument
measures) for both assessments with an empty recommendations array;
and both the injection attempt and the plain out-of-scope legal
question were refused and redirected back to assessment selection —
the second of those via the LLM's own judgment rather than the regex
fast path, which is the harder case to get right.

## AI tool usage

Built directly with Claude (this session) writing and testing the code
in an agentic sandbox — no separate no-code builder or codegen tool.