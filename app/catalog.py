import json
import os
import re
from collections import Counter
from functools import lru_cache

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "catalog.json")

STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with",
    "is", "are", "be", "who", "we", "i", "need", "want", "looking",
    "assessment", "test", "hiring", "hire", "role", "job", "candidate",
    "candidates", "someone", "person", "please", "would", "like", "you",
    "our", "my", "me", "this", "that", "it", "as", "at", "by", "from",
}

# lightweight synonym expansion for common recruiting vocabulary so a
# query like "Java developer" also surfaces "Core Java", "programming",
# "coding" style entries even without an exact string match.
SYNONYMS = {
    "developer": ["programming", "development", "software", "coding", "engineer"],
    "engineer": ["engineering", "development", "programming"],
    "stakeholder": ["communication", "interpersonal"],
    "manager": ["management", "leadership", "supervisor"],
    "leadership": ["management", "leader", "executive"],
    "personality": ["behavior", "behavioural", "opq"],
    "cognitive": ["ability", "aptitude", "reasoning", "verify"],
    "sales": ["selling", "customer", "persuasion"],
    "graduate": ["entry-level", "early career"],
    "entry": ["entry-level", "graduate"],
    "senior": ["mid-professional", "professional individual contributor"],
    "junior": ["entry-level", "graduate"],
}


def _tokenize(text: str):
    text = text.lower()
    tokens = re.findall(r"[a-z0-9\+\#\.]+", text)
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def _expand(tokens):
    expanded = list(tokens)
    for t in tokens:
        if t in SYNONYMS:
            expanded.extend(SYNONYMS[t])
    return expanded


@lru_cache(maxsize=1)
def load_catalog():
    with open(CATALOG_PATH) as f:
        catalog = json.load(f)
    for entry in catalog:
        blob = " ".join([
            entry.get("name", ""),
            entry.get("description", ""),
            " ".join(entry.get("keys", [])),
            " ".join(entry.get("job_levels", [])),
        ])
        entry["_tokens"] = Counter(_tokenize(blob))
        entry["_name_tokens"] = set(_tokenize(entry.get("name", "")))
    return catalog


def get_by_id(entry_id: str):
    for e in load_catalog():
        if str(e["id"]) == str(entry_id):
            return e
    return None


def get_by_name(name: str):
    """Fuzzy exact-ish match on assessment name, used for /compare."""
    catalog = load_catalog()
    name_l = name.lower().strip()
    # exact match first
    for e in catalog:
        if e["name"].lower() == name_l:
            return e
    # substring / token-overlap match
    best, best_score = None, 0
    q_tokens = set(_tokenize(name))
    for e in catalog:
        if name_l in e["name"].lower():
            return e
        overlap = len(q_tokens & e["_name_tokens"])
        if overlap > best_score:
            best, best_score = e, overlap
    return best if best_score > 0 else None


def search(query: str, top_k: int = 20):
    """Simple TF overlap scoring across name/description/keys/job_levels,
    weighted so name matches count more than description matches."""
    catalog = load_catalog()
    q_tokens = _expand(_tokenize(query))
    if not q_tokens:
        return catalog[:top_k]

    scored = []
    for e in catalog:
        score = 0.0
        for t in q_tokens:
            score += e["_tokens"].get(t, 0)
            if t in e["_name_tokens"]:
                score += 2.0  # name match bonus
        if score > 0:
            scored.append((score, e))

    scored.sort(key=lambda x: x[0], reverse=True)
    if not scored:
        # fall back to a broad slice so the LLM still has something to
        # ground on rather than an empty pool
        return catalog[:top_k]
    return [e for _, e in scored[:top_k]]


def public_view(entry: dict) -> dict:
    return {
        "name": entry["name"],
        "url": entry["url"],
        "test_type": (entry.get("test_types") or [""])[0],
    }


def candidate_context(entries: list) -> str:
    """Compact text block of candidates to feed the LLM as grounding."""
    lines = []
    for e in entries:
        lines.append(
            f"- id={e['id']} | name=\"{e['name']}\" | types={','.join(e.get('test_types', []))} "
            f"| duration={e.get('duration') or 'n/a'} | job_levels={','.join(e.get('job_levels', [])) or 'n/a'} "
            f"| desc={e.get('description', '')[:220]}"
        )
    return "\n".join(lines)
