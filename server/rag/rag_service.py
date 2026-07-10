from __future__ import annotations

import json
import mimetypes
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


class PipelineDraftValidationError(RagError):
    """Raised when a knowledge pipeline draft config is invalid."""


PIPELINE_STAGE_IDS = {
    "data_source": "stage_data_source",
    "processor": "stage_processor",
    "chunker": "stage_chunker",
    "image_understanding": "stage_image_understanding",
}


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
        metadata["pipeline_drafts"].pop(kb_id, None)
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

    def list_pipeline_assets(self, kb_id: str | None = None) -> list[dict[str, Any]]:
        """Return FileAsset views derived from uploaded documents."""

        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        assets = [
            self._file_asset_payload(document)
            for document in metadata["documents"].values()
            if kb_id is None or document["kb_id"] == kb_id
        ]
        return sorted(assets, key=lambda item: item["created_at"], reverse=True)

    def list_pipeline_artifacts(self, kb_id: str | None = None) -> list[dict[str, Any]]:
        """Return Artifact views derived from uploaded documents."""

        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        artifacts = [
            self._artifact_payload(document)
            for document in metadata["documents"].values()
            if kb_id is None or document["kb_id"] == kb_id
        ]
        return sorted(artifacts, key=lambda item: item["created_at"], reverse=True)

    def get_pipeline_draft(self, kb_id: str) -> dict[str, Any]:
        """Return a read-only Xpert-style pipeline draft for one knowledge base."""

        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        documents = [
            document
            for document in metadata["documents"].values()
            if document["kb_id"] == kb_id
        ]
        assets = [self._file_asset_payload(document) for document in documents]
        artifacts = [self._artifact_payload(document) for document in documents]
        chunk_count = sum(int(document.get("chunk_count", 0)) for document in documents)
        draft = self._pipeline_draft_record(metadata, kb_id)
        configs = draft["stages"]

        payload = {
            "kb_id": kb_id,
            "draft_id": draft["draft_id"],
            "version": int(draft.get("version", 1)),
            "updated_at": float(draft.get("updated_at", metadata["knowledge_bases"][kb_id]["updated_at"])),
            "editable": True,
            "stages": [
                {
                    "id": "stage_data_source",
                    "kind": "data_source",
                    "title": "数据源",
                    "status": "ready" if assets else "empty",
                    "item_count": len(assets),
                    "summary": "上传文件已映射为 FileAsset 元数据。",
                    "metadata": {
                        "asset_count": len(assets),
                        "document_count": len(documents),
                    },
                },
                {
                    "id": "stage_processor",
                    "kind": "processor",
                    "title": "处理器",
                    "status": "ready" if artifacts else "empty",
                    "item_count": len(artifacts),
                    "summary": "本地解析器已将文档映射为 Artifact。",
                    "metadata": {
                        "artifact_count": len(artifacts),
                        "parser": "local_document_parser",
                    },
                },
                {
                    "id": "stage_chunker",
                    "kind": "chunker",
                    "title": "分块器",
                    "status": "ready" if chunk_count else "empty",
                    "item_count": chunk_count,
                    "summary": "当前使用本地文本分块结果作为 KnowledgeChunk。",
                    "metadata": {
                        "chunk_count": chunk_count,
                        "strategy": "local_recursive_character_chunks",
                    },
                },
                {
                    "id": "stage_image_understanding",
                    "kind": "image_understanding",
                    "title": "图像理解",
                    "status": "planned",
                    "item_count": 0,
                    "summary": "视觉语言模型处理尚未接入，本阶段仅展示规划占位。",
                    "metadata": {
                        "enabled": False,
                    },
                },
            ],
        }
        for stage in payload["stages"]:
            stage["config"] = configs.get(str(stage["id"]), {})
        return payload

    def update_pipeline_draft(
        self,
        kb_id: str,
        stage_updates: dict[str, Any],
    ) -> dict[str, Any]:
        """Persist safe editable draft config without changing ingestion behavior."""

        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        draft = self._pipeline_draft_record(metadata, kb_id)
        configs = {
            stage_id: dict(config)
            for stage_id, config in draft["stages"].items()
        }

        if not isinstance(stage_updates, dict):
            raise PipelineDraftValidationError("pipeline draft stages must be an object.")

        for raw_stage_id, raw_update in stage_updates.items():
            stage_id = self._normalize_pipeline_stage_id(str(raw_stage_id))
            if stage_id is None:
                raise PipelineDraftValidationError(f"Unknown pipeline stage: {raw_stage_id}")
            if not isinstance(raw_update, dict):
                raise PipelineDraftValidationError(f"Stage update for {raw_stage_id} must be an object.")
            raw_config = raw_update.get("config", raw_update)
            if not isinstance(raw_config, dict):
                raise PipelineDraftValidationError(f"Stage config for {raw_stage_id} must be an object.")
            configs[stage_id] = self._validated_pipeline_stage_config(
                stage_id,
                configs[stage_id],
                raw_config,
            )

        now = time.time()
        metadata["pipeline_drafts"][kb_id] = {
            "draft_id": draft["draft_id"],
            "version": int(draft.get("version", 1)) + 1,
            "updated_at": now,
            "stages": configs,
        }
        self._write_metadata(metadata)
        return self.get_pipeline_draft(kb_id)

    def preflight_pipeline_draft(self, kb_id: str) -> dict[str, Any]:
        """Return a safe preflight summary for the draft without executing it."""

        draft = self.get_pipeline_draft(kb_id)
        stages = {stage["id"]: stage for stage in draft["stages"]}
        warnings: list[str] = []
        stage_checks: list[dict[str, Any]] = []

        document_count = int(stages["stage_data_source"]["metadata"].get("document_count", 0))
        artifact_count = int(stages["stage_processor"]["metadata"].get("artifact_count", 0))
        chunk_count = int(stages["stage_chunker"]["metadata"].get("chunk_count", 0))

        if document_count == 0:
            warnings.append("当前知识库还没有上传文档，流水线只能预检配置。")
        if artifact_count == 0:
            warnings.append("当前没有可检索 Artifact，上传文档后处理器才会产生结果。")
        if chunk_count == 0:
            warnings.append("当前没有 KnowledgeChunk，RAG 检索不会返回引用片段。")

        for stage in draft["stages"]:
            severity = "info"
            status = stage["status"]
            summary = stage["summary"]
            if stage["id"] == "stage_data_source" and document_count == 0:
                severity = "warning"
                status = "empty"
                summary = "数据源配置有效，但当前知识库没有上传文件。"
            elif stage["id"] == "stage_processor" and artifact_count == 0:
                severity = "warning"
                status = "empty"
                summary = "处理器配置有效，但当前没有解析产物。"
            elif stage["id"] == "stage_chunker" and chunk_count == 0:
                severity = "warning"
                status = "empty"
                summary = "分块器草稿配置有效，但当前没有已索引 chunk。"
            elif stage["id"] == "stage_image_understanding":
                status = "planned"
                summary = "图像理解仍为规划占位，本轮不会执行。"

            stage_checks.append(
                {
                    "id": stage["id"],
                    "kind": stage["kind"],
                    "title": stage["title"],
                    "status": status,
                    "severity": severity,
                    "summary": summary,
                    "metadata": {
                        "item_count": stage["item_count"],
                        "config": stage.get("config", {}),
                    },
                }
            )

        return {
            "kb_id": kb_id,
            "draft_id": draft["draft_id"],
            "ready": not warnings,
            "warnings": warnings,
            "stage_checks": stage_checks,
            "document_count": document_count,
            "artifact_count": artifact_count,
            "chunk_count": chunk_count,
        }

    def list_pipeline_artifact_chunks(self, artifact_id: str) -> list[dict[str, Any]]:
        """Return chunk metadata for one artifact without exposing embeddings."""

        document = self._document_for_artifact_id(artifact_id)
        chunks = self.vector_store.list_document_chunks(document["id"])
        return [
            {
                "chunk_id": chunk.chunk_id,
                "artifact_id": self._artifact_id(document["id"]),
                "knowledge_base_id": chunk.kb_id or document["kb_id"],
                "document_id": document["id"],
                "index": chunk.chunk_index,
                "text_preview": _preview_text(chunk.text),
                "text_length": len(chunk.text),
            }
            for chunk in chunks
        ]

    async def create_pipeline_citations(
        self,
        kb_id: str,
        question: str,
        *,
        top_k: int = 4,
    ) -> list[dict[str, Any]]:
        """Return citation anchors using the existing RAG retrieval path."""

        result = await self.query(kb_id, question, top_k=top_k)
        citations: list[dict[str, Any]] = []
        for source in result.get("sources", []):
            chunk_id = str(source.get("chunk_id", ""))
            doc_id = str(source.get("doc_id", ""))
            citations.append(
                {
                    "citation_id": f"citation_{chunk_id}" if chunk_id else f"citation_{len(citations)}",
                    "chunk_id": chunk_id,
                    "artifact_id": self._artifact_id(doc_id) if doc_id else "",
                    "document_id": doc_id,
                    "document_name": str(source.get("document_name", "")),
                    "score": float(source.get("score", 0.0)),
                    "snippet": _preview_text(str(source.get("text", ""))),
                }
            )
        return citations

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

    def _default_pipeline_draft_stages(self) -> dict[str, dict[str, Any]]:
        return {
            "stage_data_source": {
                "source_mode": "uploaded_files",
                "allowed_extensions": sorted(supported_extensions()),
            },
            "stage_processor": {
                "parser": "local_document_parser",
            },
            "stage_chunker": {
                "strategy": "local_recursive_character_chunks",
                "chunk_size": self.splitter.chunk_size,
                "chunk_overlap": self.splitter.chunk_overlap,
            },
            "stage_image_understanding": {
                "enabled": False,
                "provider": "planned",
            },
        }

    def _pipeline_draft_record(
        self,
        metadata: dict[str, Any],
        kb_id: str,
    ) -> dict[str, Any]:
        defaults = self._default_pipeline_draft_stages()
        draft = metadata["pipeline_drafts"].get(kb_id)
        if not isinstance(draft, dict):
            return {
                "draft_id": f"draft_{kb_id}",
                "version": 1,
                "updated_at": metadata["knowledge_bases"][kb_id]["updated_at"],
                "stages": defaults,
            }

        stages = {
            stage_id: dict(config)
            for stage_id, config in defaults.items()
        }
        raw_stages = draft.get("stages")
        if isinstance(raw_stages, dict):
            for raw_stage_id, raw_config in raw_stages.items():
                stage_id = self._normalize_pipeline_stage_id(str(raw_stage_id))
                if stage_id is None or not isinstance(raw_config, dict):
                    continue
                try:
                    stages[stage_id] = self._validated_pipeline_stage_config(
                        stage_id,
                        stages[stage_id],
                        raw_config,
                    )
                except PipelineDraftValidationError:
                    continue

        return {
            "draft_id": str(draft.get("draft_id") or f"draft_{kb_id}"),
            "version": int(draft.get("version") or 1),
            "updated_at": float(draft.get("updated_at") or metadata["knowledge_bases"][kb_id]["updated_at"]),
            "stages": stages,
        }

    def _normalize_pipeline_stage_id(self, value: str) -> str | None:
        if value in self._default_pipeline_draft_stages():
            return value
        return PIPELINE_STAGE_IDS.get(value)

    def _validated_pipeline_stage_config(
        self,
        stage_id: str,
        current: dict[str, Any],
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        config = dict(current)
        if stage_id == "stage_data_source":
            source_mode = str(patch.get("source_mode", config.get("source_mode", "uploaded_files")))
            if source_mode != "uploaded_files":
                raise PipelineDraftValidationError("data_source.source_mode must be uploaded_files.")
            config["source_mode"] = source_mode
            config["allowed_extensions"] = sorted(supported_extensions())
            return config

        if stage_id == "stage_processor":
            parser = str(patch.get("parser", config.get("parser", "local_document_parser")))
            if parser != "local_document_parser":
                raise PipelineDraftValidationError("processor.parser must be local_document_parser.")
            config["parser"] = parser
            return config

        if stage_id == "stage_chunker":
            strategy = str(
                patch.get(
                    "strategy",
                    config.get("strategy", "local_recursive_character_chunks"),
                )
            )
            if strategy != "local_recursive_character_chunks":
                raise PipelineDraftValidationError(
                    "chunker.strategy must be local_recursive_character_chunks."
                )
            chunk_size = self._coerce_int(
                patch.get("chunk_size", config.get("chunk_size", self.splitter.chunk_size)),
                "chunker.chunk_size",
            )
            chunk_overlap = self._coerce_int(
                patch.get("chunk_overlap", config.get("chunk_overlap", self.splitter.chunk_overlap)),
                "chunker.chunk_overlap",
            )
            if chunk_size < 100 or chunk_size > 4000:
                raise PipelineDraftValidationError("chunker.chunk_size must be between 100 and 4000.")
            if chunk_overlap < 0 or chunk_overlap >= chunk_size:
                raise PipelineDraftValidationError(
                    "chunker.chunk_overlap must be non-negative and smaller than chunk_size."
                )
            config.update(
                {
                    "strategy": strategy,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                }
            )
            return config

        if stage_id == "stage_image_understanding":
            enabled = patch.get("enabled", config.get("enabled", False))
            if enabled not in (False, None):
                raise PipelineDraftValidationError(
                    "image_understanding.enabled must stay false until the stage is implemented."
                )
            config["enabled"] = False
            config["provider"] = "planned"
            return config

        raise PipelineDraftValidationError(f"Unknown pipeline stage: {stage_id}")

    def _coerce_int(self, value: Any, field_name: str) -> int:
        if isinstance(value, bool):
            raise PipelineDraftValidationError(f"{field_name} must be an integer.")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise PipelineDraftValidationError(f"{field_name} must be an integer.") from exc

    def _read_metadata(self) -> dict[str, dict[str, Any]]:
        if not self.metadata_path.exists():
            return {"knowledge_bases": {}, "documents": {}, "pipeline_drafts": {}}
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"knowledge_bases": {}, "documents": {}, "pipeline_drafts": {}}
        if not isinstance(data, dict):
            return {"knowledge_bases": {}, "documents": {}, "pipeline_drafts": {}}
        return {
            "knowledge_bases": data.get("knowledge_bases") if isinstance(data.get("knowledge_bases"), dict) else {},
            "documents": data.get("documents") if isinstance(data.get("documents"), dict) else {},
            "pipeline_drafts": data.get("pipeline_drafts") if isinstance(data.get("pipeline_drafts"), dict) else {},
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

    def _ensure_kb_exists(self, metadata: dict[str, Any], kb_id: str | None) -> None:
        if kb_id is not None and kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("知识库不存在。")

    def _document_for_artifact_id(self, artifact_id: str) -> dict[str, Any]:
        doc_id = artifact_id.removeprefix("artifact_")
        metadata = self._read_metadata()
        document = metadata["documents"].get(doc_id)
        if not document:
            raise DocumentNotFoundError("文档不存在。")
        return document

    def _file_asset_payload(self, document: dict[str, Any]) -> dict[str, Any]:
        extension = Path(document["filename"]).suffix.lower()
        mime_type, _ = mimetypes.guess_type(document["filename"])
        return {
            "file_asset_id": self._file_asset_id(document["id"]),
            "document_id": document["id"],
            "knowledge_base_id": document["kb_id"],
            "filename": document["filename"],
            "size": document["size"],
            "extension": extension,
            "mime_type": mime_type,
            "created_at": document["created_at"],
        }

    def _artifact_payload(self, document: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_id": self._artifact_id(document["id"]),
            "file_asset_id": self._file_asset_id(document["id"]),
            "document_id": document["id"],
            "knowledge_base_id": document["kb_id"],
            "title": document["filename"],
            "chunk_count": document["chunk_count"],
            "created_at": document["created_at"],
        }

    def _artifact_id(self, document_id: str) -> str:
        return f"artifact_{document_id}"

    def _file_asset_id(self, document_id: str) -> str:
        return f"file_{document_id}"


def _safe_filename(filename: str) -> str:
    cleaned = Path(filename).name.strip() or "document.txt"
    return re.sub(r"[^A-Za-z0-9._\-\u4e00-\u9fff]+", "_", cleaned)


def _preview_text(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[:limit].rstrip()}..."
