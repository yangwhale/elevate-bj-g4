"""Policy retrieval over the approved corpus.

The corpus in knowledge/ is the only source of policy fact (FR-5.2, NFR-3.1).
This tool retrieves from it and returns citations that resolve to a real file,
so a downstream check can prove the answer was grounded rather than plausible.

An earlier version answered from a hardcoded POLICY_CATALOG whose text
contradicted the handbook — it stated 5 and 3 days of bereavement leave where
the handbook grants 4 weeks. A retrieval tool that carries its own facts will
override the corpus with confidence, which is the exact failure NFR-3.1
forbids. The catalog is gone; there is one source now.

In production this is replaced by the Vertex AI Search datastore described in
SDD.md C.2, which ingests the same directory. The scoring below is deliberately
simple: it is a stand-in for retrieval, not a search engine.
"""

from __future__ import annotations

import os
import re
from typing import Any

from .. import config

STOP_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or", "is",
    "are", "was", "were", "it", "how", "what", "can", "you", "i", "my", "me",
    "please", "tell", "show", "make", "do", "does", "with", "from", "about",
    "much", "many", "get", "have", "there", "any", "if", "when", "will",
}

_LAST_ERROR: dict[str, str] = {}

CORPUS_URI = os.environ.get(
    "POLICY_CORPUS_URI", "gs://${PROJECT_ID}-hr-policies"
)
MAX_RESULTS = 3
EXCERPT_CHARS = 900

# Terms whose presence in a document is worth more than a generic word match.
# Without this a query about bereavement ranks the leaves overview first,
# because overview pages mention every leave type once.
_TITLE_WEIGHT = 5
_MIN_SCORE = 2


def _documents() -> list[tuple[str, str, str]]:
    """Return (relative path, title, body) for every corpus document."""
    root = config.KNOWLEDGE_DIR
    if not root.exists():
        return []
    docs = []
    for path in sorted(root.rglob("*.md")):
        rel = str(path.relative_to(root))
        if rel.endswith("index.md") or rel == "log.md":
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(r'^title:\s*"?(.+?)"?\s*$', body, re.M)
        title = m.group(1) if m else path.stem.replace("-", " ").title()
        docs.append((rel, title, body))
    return docs


def _strip_front_matter(body: str) -> str:
    if body.startswith("---"):
        end = body.find("\n---", 3)
        if end != -1:
            return body[end + 4:].lstrip()
    return body



def _vertex_search(query: str) -> dict[str, Any] | None:
    """Query the Vertex AI Search datastore, or return None if unavailable.

    Production retrieval (SDD.md C.2). Returns None on any failure — missing
    configuration, missing client library, an unbuilt index — so the caller
    falls back to reading the same corpus off disk. Silence here would be a
    correctness bug, so the fallback logs which path served the answer in the
    `retrieval` field of the result.
    """
    project = config.GOOGLE_CLOUD_PROJECT
    engine = config.VERTEX_AI_SEARCH_ENGINE_ID
    if not project or not engine:
        return None
    try:
        from google.cloud import discoveryengine_v1 as de
    except ImportError:
        return None

    serving_config = (
        f"projects/{project}/locations/{config.VERTEX_AI_SEARCH_LOCATION}"
        f"/collections/default_collection/engines/{engine}"
        f"/servingConfigs/default_search"
    )
    try:
        client = de.SearchServiceClient()
        response = client.search(
            de.SearchRequest(
                serving_config=serving_config,
                query=query,
                page_size=MAX_RESULTS,
            )
        )
    except Exception as exc:  # noqa: BLE001 - the reason must not be swallowed
        _LAST_ERROR["reason"] = f"{type(exc).__name__}: {exc}"[:300]
        return None

    results = []
    for item in response.results:
        data = dict(item.document.derived_struct_data or {})
        uri = data.get("link") or ""
        if not uri:
            continue
        # Vertex AI Search rejects text/markdown, so the index reads a .txt
        # mirror of the corpus. Citations must point at the .md the corpus
        # actually publishes, or every citation resolves to nothing.
        if uri.endswith(".txt"):
            uri = uri[: -len(".txt")] + ".md"
        uri = uri.replace("-elevate-hr-policies-txt/", "-elevate-hr-policies/")
        # The datastore indexes a .txt mirror and does not return extractive
        # segments on the standard tier, so the excerpt is read from the
        # corpus that ships with the deployment. Vertex AI Search supplies the
        # ranking; the text still comes from the document being cited.
        rel = uri.split("/", 3)[-1] if uri.startswith("gs://") else uri
        local = config.KNOWLEDGE_DIR / rel
        excerpt = ""
        if local.is_file():
            excerpt = _strip_front_matter(local.read_text(encoding="utf-8"))
        if not excerpt:
            excerpt = (data.get("snippets") or [{}])[0].get("snippet", "")
        results.append({
            "title": uri.rsplit("/", 1)[-1].removesuffix(".md").replace("-", " "),
            "document": uri.split("/", 3)[-1] if uri.startswith("gs://") else uri,
            "uri": uri,
            "citation": f"Source: {uri}",
            "excerpt": excerpt[:EXCERPT_CHARS],
        })
    if not results:
        return None
    return {
        "status": "success",
        "query": query,
        "results_count": len(results),
        "results": results,
        "retrieval": "vertex_ai_search",
        "grounding_instruction": (
            "State only facts that appear in these excerpts, and end the answer "
            "with the Source line of every document you used."
        ),
    }


def vertex_search_policies(query: str) -> dict[str, Any]:
    """Search the approved HR policy corpus and return grounded excerpts.

    Every result carries a citation URI that resolves to a document in the
    corpus. If nothing scores above the floor the tool returns not_found, and
    the agent must say it could not find the answer rather than infer one.

    Args:
        query: Natural-language policy question, for example
            'how much bereavement leave' or 'medical certificate deadline'.
    """
    hosted = _vertex_search(query)
    if hosted is not None:
        return hosted

    tokens = [
        t.lower()
        for t in re.findall(r"\b[a-zA-Z0-9_-]+\b", query)
        if t.lower() not in STOP_WORDS and len(t) > 2
    ]
    if not tokens:
        return {
            "status": "not_found",
            "query": query,
            "results": [],
            "message": "The question contains no policy-specific search terms.",
        }

    scored = []
    for rel, title, body in _documents():
        text = _strip_front_matter(body)
        haystack = text.lower()
        title_l = title.lower()
        score = 0
        hits = []
        for t in tokens:
            in_title = t in title_l
            count = haystack.count(t)
            if in_title:
                score += _TITLE_WEIGHT
            if count:
                score += min(count, 3)
            if in_title or count:
                hits.append(t)
        if score >= _MIN_SCORE and hits:
            scored.append((score, rel, title, text, hits))

    if not scored:
        return {
            "status": "not_found",
            "query": query,
            "results": [],
            "message": (
                f"No approved policy document matches '{query}'. Do not speculate: "
                "tell the user this is not covered by the approved policies and "
                "offer to route them to People Ops."
            ),
        }

    # A term the corpus never uses is the strongest available signal that the
    # question is not covered. "How much paid sabbatical" matches documents on
    # "paid" and "years" while "sabbatical" appears nowhere, and without this
    # the agent receives plausible-looking context for a question it should
    # refuse.
    corpus_text = " ".join(b.lower() for _, _, b in _documents())
    absent = [t for t in tokens if t not in corpus_text]

    scored.sort(key=lambda r: (-r[0], r[1]))
    results = []
    for score, rel, title, text, hits in scored[:MAX_RESULTS]:
        uri = f"{CORPUS_URI}/{rel}"
        results.append({
            "title": title,
            "document": rel,
            "uri": uri,
            "citation": f"Source: {uri}",
            "excerpt": text[:EXCERPT_CHARS],
            "matched_terms": hits,
            "score": score,
        })

    instruction = (
        "State only facts that appear in these excerpts, and end the answer "
        "with the Source line of every document you used."
    )
    if absent:
        instruction = (
            "WARNING: the corpus contains no occurrence of "
            + ", ".join(sorted(absent))
            + ". The excerpts below matched on other words and may be about a "
            "different subject. If they do not answer the question, say the "
            "approved policies do not cover it rather than inferring an answer. "
            + instruction
        )

    return {
        "status": "success",
        "query": query,
        "results_count": len(results),
        "results": results,
        "retrieval": "local_corpus",
        "unmatched_terms": sorted(absent),
        "grounding_instruction": instruction,
    }
