from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import httpx


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _contains_any(text: str, phrases: list[str]) -> bool:
    lowered = _normalize(text)
    return any(_normalize(phrase) in lowered for phrase in phrases)


def evaluate_row(client: httpx.Client, rag_url: str, row: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "incident_id": row["incident_id"],
        "risk_score": row["risk_score"],
        "recommended_action": row["recommended_action"],
        "asset_ids": row["asset_ids"],
    }
    resp = client.post(f"{rag_url}/evidence", json=payload)
    resp.raise_for_status()
    body = resp.json()

    citations = body.get("citations") or []
    rationale = body.get("rationale", "")
    suggested = body.get("suggested_response", "")

    expected_sources = row.get("expected_sources", [])
    expected_phrases = row.get("expected_grounding_phrases", [])
    blocked_phrases = row.get("blocked_phrases", [])

    source_hits = sum(1 for source in expected_sources if source in body.get("sources", []))
    source_recall = source_hits / max(len(expected_sources), 1)
    grounded = _contains_any(rationale + " " + suggested, expected_phrases)
    hallucination_flag = bool(
        blocked_phrases and _contains_any(rationale + " " + suggested, blocked_phrases)
    )

    return {
        "incident_id": row["incident_id"],
        "source_recall": round(source_recall, 4),
        "grounded": grounded,
        "hallucination_flag": hallucination_flag,
        "citations_present": bool(citations),
        "n_citations": len(citations),
    }


def main() -> None:
    eval_path = Path(os.getenv("RAG_EVAL_DATA", "services/rag_service/corpus/rag_eval_set.json"))
    rag_url = os.getenv("RAG_SERVICE_URL", "http://localhost:8001")

    rows = json.loads(eval_path.read_text(encoding="utf-8"))
    with httpx.Client(timeout=15.0) as client:
        results = [evaluate_row(client, rag_url, row) for row in rows]

    n = len(results)
    grounded_rate = sum(1 for r in results if r["grounded"]) / max(n, 1)
    citation_rate = sum(1 for r in results if r["citations_present"]) / max(n, 1)
    hallucination_rate = sum(1 for r in results if r["hallucination_flag"]) / max(n, 1)

    summary = {
        "cases": n,
        "grounded_rate": round(grounded_rate, 4),
        "citation_rate": round(citation_rate, 4),
        "hallucination_rate": round(hallucination_rate, 4),
        "results": results,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
