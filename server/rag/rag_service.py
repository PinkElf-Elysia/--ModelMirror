from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .document_parser import DocumentParseError, parse_document, supported_extensions
from .embedder import EmbeddingClient, EmbeddingError
from .splitter import TextSplitter
from .vector_store import SearchResult, VectorChunk, VectorStore, create_vector_store


class RagError(RuntimeError):
    """Base error for local RAG operations."""


class KnowledgeBaseNotFoundError(RagError):
    """Raised when a knowledge base does not exist."""


class DocumentNotFoundError(RagError):
    """Raised when a document does not exist."""


class UnsupportedDocumentError(RagError):
    """Raised when an uploaded file cannot be parsed."""


class RagService:
    """Local knowledge-base service with parsing, splitting, embedding and RAG query."""

    def __init__(
        self,
        *,
        storage_dir: Path | None = None,
        uploads_dir: Path | None = None,
        embedder: EmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
        splitter: TextSplitter | None = None,
        llm_enabled: bool | None = None,
    ) -> None:
        root = Path(__file__).resolve().parent
        self.storage_dir = storage_dir or Path(os.getenv("RAG_STORAGE_DIR", str(root / "storage")))
        self.uploads_dir = uploads_dir or Path(os.getenv("RAG_UPLOAD_DIR", str(root / "uploads")))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.storage_dir / "metadata.json"
        self.embedder = embedder or EmbeddingClient()
        self.vector_store = vector_store or create_vector_store(self.storage_dir)
        self.splitter = splitter or TextSplitter(
            chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "500")),
            chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "50")),
        )
        if llm_enabled is None:
            self.llm_enabled = os.getenv("RAG_DISABLE_LLM", "").lower() not in {"1", "true", "yes"}
        else:
            self.llm_enabled = llm_enabled

    def create_knowledge_base(self, name: str) -> dict[str, Any]:
        """Create a knowledge base and return its metadata."""

        clean_name = name.strip()
        if not clean_name:
            raise ValueError("知识库名称不能为空。")

        metadata = self._read_metadata()
        kb_id = f"kb_{uuid.uuid4().hex}"
        item = {
            "id": kb_id,
            "name": clean_name,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        metadata["knowledge_bases"][kb_id] = item
        self._write_metadata(metadata)
        (self.uploads_dir / kb_id).mkdir(parents=True, exist_ok=True)
        return self._kb_payload(item, metadata)

    def list_knowledge_bases(self) -> list[dict[str, Any]]:
        """Return all knowledge bases with document counts."""

        metadata = self._read_metadata()
        items = [
            self._kb_payload(item, metadata)
            for item in metadata["knowledge_bases"].values()
        ]
        return sorted(items, key=lambda item: item["created_at"], reverse=True)

    def delete_knowledge_base(self, kb_id: str) -> None:
        """Delete a knowledge base and all related documents and vectors."""

        metadata = self._read_metadata()
        if kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("知识库不存在。")

        doc_ids = [
            doc_id
            for doc_id, document in metadata["documents"].items()
            if document["kb_id"] == kb_id
        ]
        for doc_id in doc_ids:
            metadata["documents"].pop(doc_id, None)
        metadata["knowledge_bases"].pop(kb_id, None)
        self._write_metadata(metadata)
        self.vector_store.delete_knowledge_base(kb_id)
        shutil.rmtree(self.uploads_dir / kb_id, ignore_errors=True)

    async def upload_document(self, kb_id: str, filename: str, content: bytes) -> dict[str, Any]:
        """Save, parse, split, embed and index an uploaded document."""

        metadata = self._read_metadata()
        if kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("知识库不存在。")

        extension = Path(filename).suffix.lower()
        if extension not in supported_extensions():
            raise UnsupportedDocumentError(f"暂不支持该文件格式：{extension or filename}")

        doc_id = f"doc_{uuid.uuid4().hex}"
        safe_name = _safe_filename(filename)
        target_dir = self.uploads_dir / kb_id
        target_dir.mkdir(parents=True, exist_ok=True)
        stored_path = target_dir / f"{doc_id}_{safe_name}"
        stored_path.write_bytes(content)

        try:
            text = parse_document(stored_path, filename)
            chunks = self.splitter.split_text(text)
            if not chunks:
                raise UnsupportedDocumentError("文档没有可索引的文本片段。")
            embeddings = await self.embedder.embed_texts(chunks)
        except (DocumentParseError, EmbeddingError, UnsupportedDocumentError) as exc:
            stored_path.unlink(missing_ok=True)
            raise UnsupportedDocumentError(str(exc)) from exc

        vector_chunks = [
            VectorChunk(
                id=f"{doc_id}_chunk_{index}",
                kb_id=kb_id,
                doc_id=doc_id,
                document_name=filename,
                text=chunk,
                embedding=embeddings[index],
                chunk_index=index,
            )
            for index, chunk in enumerate(chunks)
        ]
        self.vector_store.add_chunks(vector_chunks)

        document = {
            "id": doc_id,
            "kb_id": kb_id,
            "filename": filename,
            "stored_path": str(stored_path),
            "size": len(content),
            "chunk_count": len(chunks),
            "created_at": time.time(),
        }
        metadata["documents"][doc_id] = document
        metadata["knowledge_bases"][kb_id]["updated_at"] = time.time()
        self._write_metadata(metadata)
        return self._document_payload(document)

    def list_documents(self, kb_id: str) -> list[dict[str, Any]]:
        """List documents belonging to a knowledge base."""

        metadata = self._read_metadata()
        if kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("知识库不存在。")
        documents = [
            self._document_payload(document)
            for document in metadata["documents"].values()
            if document["kb_id"] == kb_id
        ]
        return sorted(documents, key=lambda item: item["created_at"], reverse=True)

    def delete_document(self, doc_id: str) -> None:
        """Delete one document and its vector chunks."""

        metadata = self._read_metadata()
        document = metadata["documents"].pop(doc_id, None)
        if not document:
            raise DocumentNotFoundError("文档不存在。")
        stored_path = Path(document.get("stored_path", ""))
        if stored_path.exists():
            stored_path.unlink()
        self.vector_store.delete_document(doc_id)
        kb_id = document["kb_id"]
        if kb_id in metadata["knowledge_bases"]:
            metadata["knowledge_bases"][kb_id]["updated_at"] = time.time()
        self._write_metadata(metadata)

    async def query(self, kb_id: str, question: str, *, top_k: int = 4) -> dict[str, Any]:
        """Run retrieval and generate an answer from the retrieved context."""

        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空。")
        metadata = self._read_metadata()
        if kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("知识库不存在。")

        query_embedding = (await self.embedder.embed_texts([clean_question]))[0]
        results = self.vector_store.query(kb_id, query_embedding, top_k)
        if not results:
            return {
                "answer": "没有在该知识库中找到相关内容，请尝试换一种问法或上传更多资料。",
                "sources": [],
            }

        answer = await self._generate_answer(clean_question, results)
        return {
            "answer": answer,
            "sources": [
                {
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "document_name": result.document_name,
                    "text": result.text,
                    "score": round(result.score, 4),
                }
                for result in results
            ],
        }

    async def _generate_answer(self, question: str, results: list[SearchResult]) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not self.llm_enabled or not api_key:
            return self._extractive_answer(results)

        context = "\n\n".join(
            f"[来源：{result.document_name}]\n{result.text}" for result in results
        )
        prompt = (
            "请仅依据<context>中的资料回答用户问题。如果资料不足，请明确说明不知道。"
            "回答后用一句话概括引用来源。\n\n"
            f"<context>\n{context}\n</context>\n\n"
            f"用户问题：{question}"
        )
        payload = {
            "model": os.getenv("RAG_LLM_MODEL", os.getenv("OPENROUTER_TEXT_FALLBACK_MODEL", "deepseek/deepseek-chat")),
            "messages": [
                {"role": "system", "content": "你是模镜的知识库问答助手，严谨、简洁，只基于给定资料回答。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": float(os.getenv("RAG_TEMPERATURE", "0.2")),
            "max_tokens": int(os.getenv("RAG_MAX_TOKENS", "1200")),
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:5173"),
            "X-Title": os.getenv("OPENROUTER_APP_TITLE", "ModelMirror"),
        }
        proxy = os.getenv("OPENROUTER_PROXY") or os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY")
        client_kwargs: dict[str, Any] = {"timeout": httpx.Timeout(45.0, connect=15.0)}
        if proxy:
            client_kwargs["proxy"] = proxy

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                response = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
        except Exception:
            return self._extractive_answer(results)

        choices = data.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str) and content.strip():
                return content.strip()
        return self._extractive_answer(results)

    def _extractive_answer(self, results: list[SearchResult]) -> str:
        best = results[0]
        return f"根据知识库资料：{best.text}"

    def _read_metadata(self) -> dict[str, dict[str, Any]]:
        if not self.metadata_path.exists():
            return {"knowledge_bases": {}, "documents": {}}
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"knowledge_bases": {}, "documents": {}}
        if not isinstance(data, dict):
            return {"knowledge_bases": {}, "documents": {}}
        return {
            "knowledge_bases": data.get("knowledge_bases") if isinstance(data.get("knowledge_bases"), dict) else {},
            "documents": data.get("documents") if isinstance(data.get("documents"), dict) else {},
        }

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        self.metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _kb_payload(self, item: dict[str, Any], metadata: dict[str, Any]) -> dict[str, Any]:
        doc_count = sum(
            1 for document in metadata["documents"].values() if document["kb_id"] == item["id"]
        )
        return {
            **item,
            "document_count": doc_count,
        }

    def _document_payload(self, document: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": document["id"],
            "kb_id": document["kb_id"],
            "filename": document["filename"],
            "size": document["size"],
            "chunk_count": document["chunk_count"],
            "created_at": document["created_at"],
        }


def _safe_filename(filename: str) -> str:
    cleaned = Path(filename).name.strip() or "document.txt"
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", cleaned)
