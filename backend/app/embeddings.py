import os
from typing import List

import httpx
from langchain_core.embeddings import Embeddings


class LocalEmbeddings(Embeddings):
    def __init__(self, base_url: str, timeout: float = 60.0) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embed([text])[0]

    def _embed(self, texts: List[str]) -> List[List[float]]:
        response = self._client.post(
            f"{self.base_url}/embed",
            json={"inputs": texts},
        )
        response.raise_for_status()
        data = response.json()
        if isinstance(data, dict) and "embeddings" in data:
            return data["embeddings"]
        return data


def get_embeddings_client() -> Embeddings:
    provider = os.environ.get("EMBEDDINGS_PROVIDER", "").lower()
    if provider == "local":
        base_url = os.environ.get("EMBEDDINGS_URL")
        if not base_url:
            raise ValueError(
                "EMBEDDINGS_URL must be set when EMBEDDINGS_PROVIDER=local"
            )
        return LocalEmbeddings(base_url)
    raise ValueError(f"Unsupported embeddings provider: {provider}")
