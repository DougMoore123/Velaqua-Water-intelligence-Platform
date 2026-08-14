from __future__ import annotations

import json
import logging
import os
from typing import List

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from azure.search.documents import SearchClient
from fastapi import FastAPI
from openai import AzureOpenAI
from pydantic import BaseModel

from services.shared.models import EvidencePackage

app = FastAPI(title="Water RAG Service", version="0.1.0")
logger = logging.getLogger(__name__)


SEARCH_ENDPOINT = os.getenv("AZURE_AI_SEARCH_ENDPOINT", "")
SEARCH_INDEX = os.getenv("AZURE_AI_SEARCH_INDEX", "")
SEARCH_KEY = os.getenv("AZURE_AI_SEARCH_KEY", "")
OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
GENAI_BLOCKLIST_TERMS = [
    term.strip().lower()
    for term in os.getenv(
        "GENAI_BLOCKLIST_TERMS",
        "drop all pressure alarms,disable safety interlocks",
    ).split(",")
    if term.strip()
]
MAX_CONTEXT_CHARS = int(os.getenv("RAG_MAX_CONTEXT_CHARS", "4000"))
MIN_RETRIEVED_DOCS = int(os.getenv("RAG_MIN_RETRIEVED_DOCS", "1"))


class EvidenceRequest(BaseModel):
    incident_id: str
    risk_score: float
    recommended_action: str
    asset_ids: List[str]


def _search_enabled() -> bool:
    return bool(SEARCH_ENDPOINT and SEARCH_INDEX)


def _openai_enabled() -> bool:
    return bool(OPENAI_ENDPOINT and OPENAI_DEPLOYMENT)


def _citations_from_docs(docs: List[dict]) -> List[str]:
    citations: List[str] = []
    for d in docs:
        source = d.get("source", "unknown")
        doc_id = d.get("id", "na")
        title = d.get("title", "Untitled")
        citations.append(f"{source}::{doc_id}::{title}")
    return citations


def _contains_blocked_content(text: str) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in GENAI_BLOCKLIST_TERMS)


def get_search_client() -> SearchClient:
    if SEARCH_KEY:
        credential = AzureKeyCredential(SEARCH_KEY)
    else:
        credential = DefaultAzureCredential()
    return SearchClient(endpoint=SEARCH_ENDPOINT, index_name=SEARCH_INDEX, credential=credential)


def retrieve_knowledge_context(payload: EvidenceRequest, top_k: int = 5) -> List[dict]:
    if not _search_enabled():
        return []

    query = (
        f"incident {payload.incident_id} leak response {payload.recommended_action} "
        f"assets {' '.join(payload.asset_ids)}"
    )
    docs: List[dict] = []

    try:
        client = get_search_client()
        results = client.search(search_text=query, top=top_k)
        for item in results:
            docs.append(
                {
                    "id": item.get("id", ""),
                    "title": item.get("title", "Untitled"),
                    "source": item.get("source", "unknown"),
                    "content": item.get("content", "")[:1200],
                }
            )
    except Exception as exc:
        logger.warning("Search retrieval failed: %s", exc)

    return docs


def _build_openai_client() -> AzureOpenAI:
    if OPENAI_API_KEY:
        return AzureOpenAI(
            api_key=OPENAI_API_KEY,
            api_version=OPENAI_API_VERSION,
            azure_endpoint=OPENAI_ENDPOINT,
        )

    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
    )
    return AzureOpenAI(
        azure_ad_token_provider=token_provider,
        api_version=OPENAI_API_VERSION,
        azure_endpoint=OPENAI_ENDPOINT,
    )


def synthesize_evidence(payload: EvidenceRequest, docs: List[dict]) -> EvidencePackage:
    if docs and len(docs) < MIN_RETRIEVED_DOCS:
        return build_fallback_evidence(payload)

    if not _openai_enabled():
        return build_fallback_evidence(payload)

    context_lines = []
    for d in docs:
        context_lines.append(
            f"- [{d.get('source', 'unknown')}] {d.get('title', 'Untitled')}: {d.get('content', '')}"
        )
    context = "\n".join(context_lines) if context_lines else "No retrieved context available."
    context = context[:MAX_CONTEXT_CHARS]
    citations = _citations_from_docs(docs)

    system_prompt = (
        "You are a utility operations copilot. Produce concise, factual incident evidence. "
        "Return JSON with keys: sources (array of strings), rationale (string), "
        "suggested_response (string), citations (array of strings). Only provide guidance grounded "
        "in retrieved evidence and never invent source references."
    )
    user_prompt = (
        f"Incident payload: {payload.model_dump_json()}\n"
        f"Retrieved evidence:\n{context}\n"
        "Ground your response in retrieved evidence when available."
    )

    try:
        client = _build_openai_client()
        response = client.chat.completions.create(
            model=OPENAI_DEPLOYMENT,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        parsed = json.loads(raw)
        rationale = parsed.get("rationale", "No rationale provided by model.")
        suggested_response = parsed.get(
            "suggested_response",
            "Escalate to operator with manual review checklist.",
        )
        if _contains_blocked_content(rationale) or _contains_blocked_content(suggested_response):
            logger.warning("Safety guardrail triggered. Falling back to deterministic evidence.")
            return build_fallback_evidence(payload)

        return EvidencePackage(
            sources=parsed.get("sources") or [d.get("source", "unknown") for d in docs[:3]],
            rationale=rationale,
            suggested_response=suggested_response,
            citations=parsed.get("citations") or citations,
        )
    except Exception as exc:
        logger.warning("OpenAI synthesis failed: %s", exc)
        return build_fallback_evidence(payload)


def build_fallback_evidence(payload: EvidenceRequest) -> EvidencePackage:
    sources = [
        "SOP: Leak Isolation Standard Work v3",
        "Maintenance Manual: Pump & Valve Response Guide",
        "Incident Archive: Similar high-risk events",
    ]
    rationale = (
        f"Incident {payload.incident_id} has risk score {payload.risk_score:.2f}. "
        f"Recommended action is {payload.recommended_action}."
    )
    suggested_response = (
        "Validate upstream/downstream pressure, isolate suspected segment, "
        "and create a CMMS work order with priority based on confidence."
    )
    return EvidencePackage(
        sources=sources,
        rationale=rationale,
        suggested_response=suggested_response,
        citations=[
            "SOP:LeakIsolationStandardWorkV3::section-4",
            "Manual:PumpValveResponseGuide::chapter-2",
        ],
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "search_configured": _search_enabled(),
        "openai_configured": _openai_enabled(),
    }


@app.post("/evidence", response_model=EvidencePackage)
def evidence(payload: EvidenceRequest) -> EvidencePackage:
    docs = retrieve_knowledge_context(payload)
    return synthesize_evidence(payload, docs)
