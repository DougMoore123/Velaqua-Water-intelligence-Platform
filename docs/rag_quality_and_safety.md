# RAG Quality, Grounding, and Safety Checklist

## Knowledge Corpus

Seed corpus includes:
- SOPs
- Equipment manuals
- Incident history

Files:
- `services/rag_service/corpus/seed_knowledge.jsonl`
- `services/rag_service/corpus/rag_eval_set.json`

## Configure Azure AI Search and Azure OpenAI

```bash
chmod +x scripts/configure_rag_services.sh
./scripts/configure_rag_services.sh
```

Required environment variables:
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_AI_SEARCH_NAME`
- `AZURE_OPENAI_NAME`

## Index Corpus

```bash
python scripts/index_rag_corpus.py
```

## Grounding and Citations

Service behavior in `services/rag_service/app/main.py`:
- Grounds responses on retrieved context only.
- Adds citation references in `citations`.
- Falls back to deterministic evidence when retrieval/generation fails.

## Evaluate Retrieval Quality and Hallucination Risk

```bash
python scripts/evaluate_rag_quality.py
```

Output metrics:
- `grounded_rate`
- `citation_rate`
- `hallucination_rate`
- Per-case `source_recall`

## GenAI Safety Controls

Environment controls:
- `GENAI_BLOCKLIST_TERMS`
- `RAG_MAX_CONTEXT_CHARS`
- `RAG_MIN_RETRIEVED_DOCS`

Safety behavior:
- Blocks unsafe generated content via blocklist checks.
- Uses fallback evidence when safety check triggers.

## Note Summary

This RAG guide defines the operating conditions for grounded, auditable, and safe generation. The purpose is to keep model output tied to retrieved evidence while preserving a resilient fallback path when retrieval or model dependencies fail.

The main quality checks are:

$$
\text{Grounded Rate} = \frac{\text{Grounded Responses}}{\text{Total Responses}}
$$

$$
\text{Citation Rate} = \frac{\text{Responses with Valid Citations}}{\text{Total Responses}}
$$

$$
\text{Hallucination Rate} = \frac{\text{Unsupported Claims}}{\text{Total Claims}}
$$

$$
\text{Retrieval Recall} = \frac{\text{Relevant Documents Retrieved}}{\text{Total Relevant Documents}}
$$

The intended operating condition is grounded rate and citation rate near 1.0 while hallucination rate stays near 0.0.
