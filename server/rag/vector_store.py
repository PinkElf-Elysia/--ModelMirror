from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .embedder import cosine_similarity


@dataclass(slots=True)
class VectorChunk:
    id: str
    kb_id: str
    doc_id: str
    document_name: str
    text: str
    embedding: list[float]
    chunk_index: int


@dataclass(slots=True)
class SearchResult:
    chunk_id: str
    kb_id: str
    doc_id: str
    document_name: str
    text: str
    score: float


class VectorStore(Protocol):
    """Protocol implemented by vector-store backends."""

    def add_chunks(self, chunks: list[VectorChunk]) -> None:
        """Add embedded chunks."""

    def query(self, kb_id: str, embedding: list[float], top_k: int) -> list[SearchResult]:
        """Query similar chunks in one knowledge base."""

    def delete_document(self, doc_id: str) -> None:
        """Delete all chunks for a document."""

    def delete_knowledge_base(self, kb_id: str) -> None:
        """Delete all chunks for a knowledge base."""


class LocalJsonVectorStore:
    """Small persistent vector store used as a no-network fallback and in tests."""

    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)

    def add_chunks(self, chunks: list[VectorChunk]) -> None:
        records = self._read_records()
        existing_ids = {record["id"] for record in records}
        for chunk in chunks:
            if chunk.id in existing_ids:
                continue
            records.append(_chunk_to_record(chunk))
        self._write_records(records)

    def query(self, kb_id: str, embedding: list[float], top_k: int) -> list[SearchResult]:
        scored: list[SearchResult] = []
        for record in self._read_records():
            if record.get("kb_id") != kb_id:
                continue
            score = cosine_similarity(embedding, [float(value) for value in record["embedding"]])
            scored.append(
                SearchResult(
                    chunk_id=record["id"],
                    kb_id=record["kb_id"],
                    doc_id=record["doc_id"],
                    document_name=record["document_name"],
                    text=record["text"],
                    score=score,
                )
            )
        return sorted(scored, key=lambda item: item.score, reverse=True)[:top_k]

    def delete_document(self, doc_id: str) -> None:
        self._write_records(
            [record for record in self._read_records() if record.get("doc_id") != doc_id]
        )

    def delete_knowledge_base(self, kb_id: str) -> None:
        self._write_records(
            [record for record in self._read_records() if record.get("kb_id") != kb_id]
        )

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.storage_path.exists():
            return []
        try:
            data = json.loads(self.storage_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return data if isinstance(data, list) else []

    def _write_records(self, records: list[dict[str, Any]]) -> None:
        self.storage_path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


class ChromaVectorStore:
    """ChromaDB-backed vector store with local persistence."""

    def __init__(self, persist_path: Path) -> None:
        try:
            import chromadb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("chromadb is not installed") from exc

        persist_path.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(persist_path))
        self._collection = self._client.get_or_create_collection("modelmirror_rag_chunks")

    def add_chunks(self, chunks: list[VectorChunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[chunk.id for chunk in chunks],
            embeddings=[chunk.embedding for chunk in chunks],
            documents=[chunk.text for chunk in chunks],
            metadatas=[
                {
                    "kb_id": chunk.kb_id,
                    "doc_id": chunk.doc_id,
                    "document_name": chunk.document_name,
                    "chunk_index": chunk.chunk_index,
                    "updated_at": time.time(),
                }
                for chunk in chunks
            ],
        )

    def query(self, kb_id: str, embedding: list[float], top_k: int) -> list[SearchResult]:
        response = self._collection.query(
            query_embeddings=[embedding],
            n_results=top_k,
            where={"kb_id": kb_id},
            include=["documents", "metadatas", "distances"],
        )
        ids = (response.get("ids") or [[]])[0]
        documents = (response.get("documents") or [[]])[0]
        metadatas = (response.get("metadatas") or [[]])[0]
        distances = (response.get("distances") or [[]])[0]

        results: list[SearchResult] = []
        for index, chunk_id in enumerate(ids):
            metadata = metadatas[index] or {}
            distance = float(distances[index]) if index < len(distances) else 1.0
            results.append(
                SearchResult(
                    chunk_id=chunk_id,
                    kb_id=str(metadata.get("kb_id", kb_id)),
                    doc_id=str(metadata.get("doc_id", "")),
                    document_name=str(metadata.get("document_name", "")),
                    text=str(documents[index] if index < len(documents) else ""),
                    score=1.0 / (1.0 + max(distance, 0.0)),
                )
            )
        return results

    def delete_document(self, doc_id: str) -> None:
        self._collection.delete(where={"doc_id": doc_id})

    def delete_knowledge_base(self, kb_id: str) -> None:
        self._collection.delete(where={"kb_id": kb_id})


def create_vector_store(storage_dir: Path) -> VectorStore:
    """Create the configured vector store, falling back to local JSON if needed."""

    backend = os.getenv("RAG_VECTOR_STORE", "chroma").strip().lower()
    if backend == "local":
        return LocalJsonVectorStore(storage_dir / "vector_index.json")

    try:
        return ChromaVectorStore(Path(os.getenv("CHROMA_DB_PATH", str(storage_dir / "chroma_db"))))
    except Exception:
        return LocalJsonVectorStore(storage_dir / "vector_index.json")


def _chunk_to_record(chunk: VectorChunk) -> dict[str, Any]:
    return {
        "id": chunk.id,
        "kb_id": chunk.kb_id,
        "doc_id": chunk.doc_id,
        "document_name": chunk.document_name,
        "text": chunk.text,
        "embedding": chunk.embedding,
        "chunk_index": chunk.chunk_index,
    }
