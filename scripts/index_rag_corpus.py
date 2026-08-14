from __future__ import annotations

import json
import os
from pathlib import Path

from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient


def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _client() -> SearchClient:
    endpoint = os.environ["AZURE_AI_SEARCH_ENDPOINT"]
    index_name = os.environ["AZURE_AI_SEARCH_INDEX"]
    key = os.getenv("AZURE_AI_SEARCH_KEY", "")

    if key:
        credential = AzureKeyCredential(key)
    else:
        credential = DefaultAzureCredential()

    return SearchClient(endpoint=endpoint, index_name=index_name, credential=credential)


def main() -> None:
    corpus_path = Path(
        os.getenv("RAG_CORPUS_PATH", "services/rag_service/corpus/seed_knowledge.jsonl")
    )
    if not corpus_path.exists():
        raise FileNotFoundError(f"Corpus file not found: {corpus_path}")

    docs = _load_jsonl(corpus_path)
    if not docs:
        raise ValueError("Corpus file has no documents")

    client = _client()
    result = client.upload_documents(documents=docs)

    succeeded = sum(1 for item in result if item.succeeded)
    failed = len(result) - succeeded
    print(json.dumps({"uploaded": succeeded, "failed": failed}, indent=2))


if __name__ == "__main__":
    main()
