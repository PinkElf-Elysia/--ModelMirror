from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from .document_parser import DocumentParseError, parse_document, supported_extensions
from .document_processor import ProcessedDocument, StructuredDocumentProcessor
from .embedder import EmbeddingClient, EmbeddingError
from .lexical_store import LexicalSearchResult, SqliteLexicalStore
from .reranker import RerankDocument, RerankService
from .retrieval import RetrievalCandidate, RetrievalConfig, fuse_rankings
from .processor_generator import ProcessorGenerationService
from .splitter import DEFAULT_SEPARATORS, TextSplitter
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


class PipelineJobNotFoundError(RagError):
    """Raised when a knowledge pipeline job does not exist."""


class PipelineVersionNotFoundError(RagError):
    """Raised when a knowledge index version does not exist."""


class PipelineJobStateError(RagError):
    """Raised when a pipeline job operation is invalid for its current state."""


PIPELINE_STAGE_IDS = {
    "data_source": "stage_data_source",
    "processor": "stage_processor",
    "chunker": "stage_chunker",
    "image_understanding": "stage_image_understanding",
}

PIPELINE_JOB_STAGES = (
    ("load", "读取来源"),
    ("process", "解析文档"),
    ("chunk", "生成分块"),
    ("embed", "生成向量"),
    ("store", "写入候选索引"),
)


class RagService:
    """Local knowledge-base service with parsing, splitting, embedding and RAG query."""

    def __init__(
        self,
        *,
        storage_dir: Path | None = None,
        uploads_dir: Path | None = None,
        embedder: EmbeddingClient | None = None,
        vector_store: VectorStore | None = None,
        lexical_store: SqliteLexicalStore | None = None,
        reranker: RerankService | None = None,
        splitter: TextSplitter | None = None,
        document_processor: StructuredDocumentProcessor | None = None,
        processor_generator: ProcessorGenerationService | None = None,
        llm_enabled: bool | None = None,
    ) -> None:
        root = Path(__file__).resolve().parent
        self.storage_dir = storage_dir or Path(os.getenv("RAG_STORAGE_DIR", str(root / "storage")))
        self.uploads_dir = uploads_dir or Path(os.getenv("RAG_UPLOAD_DIR", str(root / "uploads")))
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_path = self.storage_dir / "metadata.json"
        self.pipeline_sources_dir = self.storage_dir / "pipeline_sources"
        self.pipeline_sources_dir.mkdir(parents=True, exist_ok=True)
        self.pipeline_processed_dir = self.storage_dir / "pipeline_processed"
        self.pipeline_processed_dir.mkdir(parents=True, exist_ok=True)
        self._metadata_lock = threading.RLock()
        self.embedder = embedder or EmbeddingClient()
        self.vector_store = vector_store or create_vector_store(self.storage_dir)
        self.lexical_store = lexical_store or SqliteLexicalStore(
            self.storage_dir / "lexical_index.sqlite3"
        )
        self.reranker = reranker or RerankService()
        self.document_processor = document_processor or StructuredDocumentProcessor()
        self.processor_generator = processor_generator or ProcessorGenerationService()
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
        metadata["pipeline_active_versions"].pop(kb_id, None)
        version_namespaces = [
            str(item.get("namespace") or "")
            for item in metadata["pipeline_versions"].values()
            if item.get("kb_id") == kb_id
        ]
        metadata["pipeline_versions"] = {
            version_id: item
            for version_id, item in metadata["pipeline_versions"].items()
            if item.get("kb_id") != kb_id
        }
        job_ids = [
            job_id
            for job_id, item in metadata["pipeline_jobs"].items()
            if item.get("kb_id") == kb_id
        ]
        metadata["pipeline_jobs"] = {
            job_id: item
            for job_id, item in metadata["pipeline_jobs"].items()
            if item.get("kb_id") != kb_id
        }
        self._write_metadata(metadata)
        self.vector_store.delete_knowledge_base(kb_id)
        self.lexical_store.delete_namespace(kb_id)
        for namespace in version_namespaces:
            if namespace:
                self.vector_store.delete_knowledge_base(namespace)
                self.lexical_store.delete_namespace(namespace)
        for job_id in job_ids:
            shutil.rmtree(self.pipeline_sources_dir / job_id, ignore_errors=True)
            shutil.rmtree(self.pipeline_processed_dir / job_id, ignore_errors=True)
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
        with self._metadata_lock:
            latest = self._read_metadata_unlocked()
            if kb_id not in latest["knowledge_bases"]:
                self.vector_store.delete_document(doc_id)
                stored_path.unlink(missing_ok=True)
                raise KnowledgeBaseNotFoundError("Knowledge base was removed during upload.")
            latest["documents"][doc_id] = document
            latest["knowledge_bases"][kb_id]["updated_at"] = time.time()
            self._write_metadata_unlocked(latest)
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
            "index_schema_version": int(draft.get("index_schema_version", 2)),
            "embedding_profile": json.loads(json.dumps(draft["embedding_profile"])),
            "retrieval_profile": json.loads(json.dumps(draft["retrieval_profile"])),
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
                        "parser": configs["stage_processor"].get(
                            "parser", "structured_local_parser"
                        ),
                        "mode": configs["stage_processor"].get("mode", "general"),
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
                        "strategy": configs["stage_chunker"].get(
                            "strategy", "recursive_character"
                        ),
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
        *,
        retrieval_profile: dict[str, Any] | None = None,
        embedding_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist safe editable draft config without changing ingestion behavior."""

        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        draft = self._pipeline_draft_record(metadata, kb_id)
        configs = {
            stage_id: dict(config)
            for stage_id, config in draft["stages"].items()
        }
        try:
            next_retrieval = RetrievalConfig.from_mapping(
                retrieval_profile,
                base=RetrievalConfig.from_mapping(draft.get("retrieval_profile")),
            ).payload()
        except ValueError as exc:
            raise PipelineDraftValidationError(str(exc)) from exc
        next_embedding = self._validated_embedding_profile(
            draft.get("embedding_profile"),
            embedding_profile,
        )

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
        with self._metadata_lock:
            latest = self._read_metadata_unlocked()
            self._ensure_kb_exists(latest, kb_id)
            current = self._pipeline_draft_record(latest, kb_id)
            latest["pipeline_drafts"][kb_id] = {
                "draft_id": current["draft_id"],
                "version": int(current.get("version", 1)) + 1,
                "updated_at": now,
                "index_schema_version": 2,
                "embedding_profile": next_embedding,
                "retrieval_profile": next_retrieval,
                "stages": configs,
            }
            self._write_metadata_unlocked(latest)
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
        processor_config = dict(stages["stage_processor"].get("config") or {})
        processor_mode = str(processor_config.get("mode") or "general")
        processor_capabilities = self.processor_generator.capabilities()

        if document_count == 0:
            warnings.append("当前知识库还没有上传文档，流水线只能预检配置。")
        if artifact_count == 0:
            warnings.append("当前没有可检索 Artifact，上传文档后处理器才会产生结果。")
        if chunk_count == 0:
            warnings.append("当前没有 KnowledgeChunk，RAG 检索不会返回引用片段。")
        if processor_mode in {"qa", "summary"} and not processor_capabilities.get(
            "llm_configured"
        ):
            warnings.append("生成式处理模式需要先配置可用的模型网关。")

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
            elif (
                stage["id"] == "stage_processor"
                and processor_mode in {"qa", "summary"}
                and not processor_capabilities.get("llm_configured")
            ):
                severity = "warning"
                status = "blocked"
                summary = "生成式处理器配置有效，但当前没有可用模型网关。"
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

    def processor_capabilities(self) -> dict[str, Any]:
        generation = self.processor_generator.capabilities()
        return {
            "version": "rag-processor-capabilities-v1",
            "parser": "structured_local_parser",
            "modes": ["general", "qa", "summary"],
            "failure_policies": ["continue_on_error", "strict"],
            "supported_extensions": sorted(supported_extensions()),
            "block_types": [
                "heading",
                "paragraph",
                "list",
                "table",
                "code",
                "page",
            ],
            "llm_configured": bool(generation.get("llm_configured")),
            "model_label": str(generation.get("model") or ""),
            "generation_targets": list(generation.get("targets") or []),
            "limits": {
                "max_generated_items": 50,
                "preview_items": 20,
                "preview_text_characters": 600,
            },
        }

    async def preview_pipeline_processor(
        self,
        kb_id: str,
        document_id: str,
        processor_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        document_record = metadata["documents"].get(document_id)
        if not isinstance(document_record, dict) or document_record.get("kb_id") != kb_id:
            raise DocumentNotFoundError("文档不存在。")
        draft = self._pipeline_draft_record(metadata, kb_id)
        current = dict(draft["stages"]["stage_processor"])
        config = self._validated_pipeline_stage_config(
            "stage_processor",
            current,
            dict(processor_override or {}),
        )
        path = Path(str(document_record.get("stored_path") or ""))
        if not path.is_file():
            raise DocumentNotFoundError("文档源文件不可用。")
        try:
            processed = await asyncio.to_thread(
                self.document_processor.process,
                path,
                filename=str(document_record["filename"]),
                source_id=str(document_record["id"]),
                config=config,
            )
        except (DocumentParseError, OSError, UnicodeError) as exc:
            raise PipelineDraftValidationError(self._safe_pipeline_error(exc)) from exc
        generated = await self.processor_generator.generate(
            processed,
            mode=str(config.get("mode") or "general"),
            model_id=str(config.get("model_id") or ""),
            max_items=min(20, int(config.get("max_generated_items", 20))),
        )
        return {
            "kb_id": kb_id,
            "document_id": document_id,
            "filename": str(document_record["filename"]),
            "title": processed.title,
            "config": config,
            "character_count": len(processed.text),
            "block_count": len(processed.blocks),
            "block_counts": processed.block_counts,
            "generated_count": len(generated),
            "warnings": list(processed.warnings),
            "blocks": [
                block.payload(max_text=600) for block in processed.blocks[:20]
            ],
            "generated_items": [
                item.payload(max_text=600) for item in generated[:20]
            ],
        }

    def create_pipeline_job(
        self,
        kb_id: str,
        *,
        draft_version: int,
        source_document_ids: list[str] | None = None,
        xpert_sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a durable job with immutable source and draft snapshots."""

        with self._metadata_lock:
            metadata = self._read_metadata_unlocked()
            self._ensure_kb_exists(metadata, kb_id)
            draft = self._pipeline_draft_record(metadata, kb_id)
            if int(draft["version"]) != int(draft_version):
                raise PipelineJobStateError(
                    f"Pipeline draft changed. Expected v{draft_version}, current v{draft['version']}."
                )

            documents = [
                item
                for item in metadata["documents"].values()
                if item["kb_id"] == kb_id
            ]
            if source_document_ids is not None:
                requested = list(dict.fromkeys(str(item) for item in source_document_ids))
                by_id = {str(item["id"]): item for item in documents}
                missing = [item for item in requested if item not in by_id]
                if missing:
                    raise DocumentNotFoundError(
                        f"Pipeline source document not found: {missing[0]}"
                    )
                documents = [by_id[item] for item in requested]

            job_id = f"kpjob_{uuid.uuid4().hex}"
            source_dir = self.pipeline_sources_dir / job_id
            source_dir.mkdir(parents=True, exist_ok=True)
            manifest: list[dict[str, Any]] = []
            try:
                for index, document in enumerate(documents):
                    source_path = Path(str(document.get("stored_path") or ""))
                    if not source_path.is_file():
                        raise DocumentNotFoundError(
                            f"Pipeline source file is unavailable: {document['id']}"
                        )
                    suffix = source_path.suffix or Path(str(document["filename"])).suffix or ".txt"
                    snapshot = source_dir / f"document_{index}{suffix.lower()}"
                    shutil.copyfile(source_path, snapshot)
                    manifest.append(
                        {
                            "source_id": str(document["id"]),
                            "source_kind": "knowledge_document",
                            "filename": str(document["filename"]),
                            "size": int(document.get("size", snapshot.stat().st_size)),
                            "snapshot_key": snapshot.relative_to(self.storage_dir).as_posix(),
                            "content_hash": self._file_sha256(snapshot),
                            "content_mode": "document",
                        }
                    )

                seen_external: set[tuple[str, str, str]] = set()
                for index, source in enumerate(xpert_sources or []):
                    key = (
                        str(source.get("xpert_id") or ""),
                        str(source.get("conversation_id") or ""),
                        str(source.get("asset_id") or ""),
                    )
                    if not all(key) or key in seen_external:
                        continue
                    seen_external.add(key)
                    text = str(source.get("text") or "")
                    if not text.strip():
                        continue
                    snapshot = source_dir / f"xpert_file_{index}.txt"
                    snapshot.write_text(text, encoding="utf-8")
                    manifest.append(
                        {
                            "source_id": f"xpert_{key[2]}",
                            "source_kind": "xpert_file",
                            "filename": str(source.get("filename") or f"attachment_{index}.txt"),
                            "size": len(text.encode("utf-8")),
                            "snapshot_key": snapshot.relative_to(self.storage_dir).as_posix(),
                            "content_hash": self._file_sha256(snapshot),
                            "content_mode": "extracted_text",
                            "xpert_id": key[0],
                            "conversation_id": key[1],
                            "asset_id": key[2],
                        }
                    )
                if not manifest:
                    raise PipelineDraftValidationError(
                        "A knowledge pipeline job requires at least one document or Xpert file."
                    )
            except Exception:
                shutil.rmtree(source_dir, ignore_errors=True)
                raise

            reserved_numbers = [
                int(item.get("version", 0))
                for item in metadata["pipeline_versions"].values()
                if item.get("kb_id") == kb_id
            ] + [
                int(item.get("candidate_version", 0))
                for item in metadata["pipeline_jobs"].values()
                if item.get("kb_id") == kb_id
            ]
            candidate_version = max(reserved_numbers, default=0) + 1
            candidate_version_id = f"kpv_{uuid.uuid4().hex}"
            now = time.time()
            processor_profile = json.loads(
                json.dumps(draft["stages"]["stage_processor"])
            )
            processor_config_hash = self._mapping_sha256(processor_profile)
            document_results = [
                {
                    "source_id": str(source["source_id"]),
                    "filename": str(source["filename"]),
                    "status": "pending",
                    "content_hash": str(source["content_hash"]),
                    "processor_config_hash": processor_config_hash,
                    "attempt": 0,
                    "block_count": 0,
                    "generated_count": 0,
                    "chunk_count": 0,
                    "qa_count": 0,
                    "summary_count": 0,
                    "warnings": [],
                    "error": None,
                    "duration_ms": None,
                    "artifact_key": (
                        self.pipeline_processed_dir
                        / job_id
                        / f"source_{index}.json"
                    ).relative_to(self.storage_dir).as_posix(),
                }
                for index, source in enumerate(manifest)
            ]
            job = {
                "job_id": job_id,
                "kb_id": kb_id,
                "draft_id": str(draft["draft_id"]),
                "draft_version": int(draft["version"]),
                "config_snapshot": {
                    "index_schema_version": int(draft.get("index_schema_version", 2)),
                    "stages": json.loads(json.dumps(draft["stages"])),
                    "processor_profile": processor_profile,
                    "embedding_profile": json.loads(json.dumps(draft["embedding_profile"])),
                    "retrieval_profile": json.loads(json.dumps(draft["retrieval_profile"])),
                },
                "sources": manifest,
                "document_results": document_results,
                "status": "queued",
                "stages": self._new_pipeline_job_stages(),
                "candidate_version_id": candidate_version_id,
                "candidate_version": candidate_version,
                "candidate_namespace": f"{kb_id}::{candidate_version_id}",
                "run_id": None,
                "attempt": 0,
                "cancel_requested": False,
                "error": None,
                "warnings": [],
                "processor_error": None,
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "completed_at": None,
            }
            metadata["pipeline_jobs"][job_id] = job
            self._write_metadata_unlocked(metadata)
            return self.pipeline_job_payload(job)

    def list_pipeline_jobs(
        self,
        *,
        kb_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        metadata = self._read_metadata()
        items = list(metadata["pipeline_jobs"].values())
        if kb_id is not None:
            self._ensure_kb_exists(metadata, kb_id)
            items = [item for item in items if item.get("kb_id") == kb_id]
        if status is not None:
            items = [item for item in items if item.get("status") == status]
        items.sort(key=lambda item: float(item.get("created_at", 0)), reverse=True)
        return [self.pipeline_job_payload(item) for item in items[: max(1, min(limit, 200))]]

    def get_pipeline_job(self, job_id: str) -> dict[str, Any]:
        metadata = self._read_metadata()
        job = metadata["pipeline_jobs"].get(job_id)
        if not isinstance(job, dict):
            raise PipelineJobNotFoundError("Knowledge pipeline job not found.")
        return json.loads(json.dumps(job))

    def pipeline_job_payload(self, job: dict[str, Any]) -> dict[str, Any]:
        sources = [
            {
                key: value
                for key, value in source.items()
                if key not in {"snapshot_key", "content_hash"}
            }
            for source in job.get("sources", [])
        ]
        document_results = [
            {
                key: json.loads(json.dumps(value))
                for key, value in result.items()
                if key
                not in {
                    "artifact_key",
                    "content_hash",
                    "processor_config_hash",
                }
            }
            for result in job.get("document_results", [])
            if isinstance(result, dict)
        ]
        return {
            key: json.loads(json.dumps(value))
            for key, value in job.items()
            if key
            not in {
                "candidate_namespace",
                "config_snapshot",
                "sources",
                "document_results",
                "processor_error",
            }
        } | {
            "sources": sources,
            "source_count": len(sources),
            "document_results": document_results,
        }

    def claim_next_pipeline_job(self) -> dict[str, Any] | None:
        with self._metadata_lock:
            metadata = self._read_metadata_unlocked()
            queued = [
                item
                for item in metadata["pipeline_jobs"].values()
                if item.get("status") == "queued"
            ]
            if not queued:
                return None
            queued.sort(key=lambda item: float(item.get("created_at", 0)))
            job = queued[0]
            now = time.time()
            job["status"] = "running"
            job["attempt"] = int(job.get("attempt", 0)) + 1
            job["started_at"] = now
            job["updated_at"] = now
            job["error"] = None
            job["cancel_requested"] = False
            self._write_metadata_unlocked(metadata)
            return json.loads(json.dumps(job))

    def recover_pipeline_jobs(self) -> int:
        with self._metadata_lock:
            metadata = self._read_metadata_unlocked()
            recovered = 0
            for job in metadata["pipeline_jobs"].values():
                if job.get("status") != "running":
                    continue
                namespace = str(job.get("candidate_namespace") or "")
                self.vector_store.delete_knowledge_base(namespace)
                self.lexical_store.delete_namespace(namespace)
                job["status"] = "queued"
                job["error"] = "Recovered after process restart."
                job["updated_at"] = time.time()
                job["stages"] = self._new_pipeline_job_stages()
                for result in job.get("document_results", []):
                    if isinstance(result, dict) and result.get("status") == "processing":
                        result["status"] = "pending"
                        result["error"] = "Recovered after process restart."
                job["processor_error"] = None
                recovered += 1
            if recovered:
                self._write_metadata_unlocked(metadata)
            return recovered

    def set_pipeline_job_run_id(self, job_id: str, run_id: str) -> None:
        self._update_pipeline_job(job_id, lambda job: job.update({"run_id": run_id}))

    def start_pipeline_job_stage(self, job_id: str, stage_id: str) -> None:
        def update(job: dict[str, Any]) -> None:
            stage = self._pipeline_stage(job, stage_id)
            stage.update(
                {
                    "status": "running",
                    "progress": 10,
                    "started_at": time.time(),
                    "completed_at": None,
                    "error": None,
                }
            )

        self._update_pipeline_job(job_id, update)

    def complete_pipeline_job_stage(
        self,
        job_id: str,
        stage_id: str,
        *,
        item_count: int | None = None,
    ) -> None:
        def update(job: dict[str, Any]) -> None:
            stage = self._pipeline_stage(job, stage_id)
            stage.update(
                {
                    "status": "completed",
                    "progress": 100,
                    "completed_at": time.time(),
                }
            )
            if item_count is not None:
                stage["item_count"] = item_count

        self._update_pipeline_job(job_id, update)

    def load_pipeline_job_sources(self, job_id: str) -> list[dict[str, Any]]:
        job = self.get_pipeline_job(job_id)
        loaded: list[dict[str, Any]] = []
        for source in job["sources"]:
            path = self._pipeline_snapshot_path(str(source["snapshot_key"]))
            if not path.is_file():
                raise PipelineJobStateError(
                    f"Pipeline source snapshot is unavailable: {source['source_id']}"
                )
            loaded.append({**source, "snapshot_exists": True})
        return loaded

    def parse_pipeline_job_sources(self, job_id: str) -> list[dict[str, Any]]:
        job = self.get_pipeline_job(job_id)
        parsed: list[dict[str, Any]] = []
        for source in job["sources"]:
            path = self._pipeline_snapshot_path(str(source["snapshot_key"]))
            if source.get("content_mode") == "extracted_text":
                text = path.read_text(encoding="utf-8")
            else:
                text = parse_document(path, str(source["filename"]))
            if text.strip():
                parsed.append({**source, "text": text})
        if not parsed:
            raise PipelineJobStateError("No pipeline sources produced readable text.")
        return parsed

    async def process_pipeline_job_sources(self, job_id: str) -> list[dict[str, Any]]:
        """Process each immutable source independently and reuse completed artifacts."""

        job = self.get_pipeline_job(job_id)
        snapshot = job.get("config_snapshot", {})
        profile = dict(
            snapshot.get("processor_profile")
            or snapshot.get("stages", {}).get("stage_processor")
            or self._default_pipeline_draft_stages()["stage_processor"]
        )
        config_hash = self._mapping_sha256(profile)
        results_by_source = {
            str(item.get("source_id")): item
            for item in job.get("document_results", [])
            if isinstance(item, dict)
        }
        completed: list[dict[str, Any]] = []
        failed: list[dict[str, Any]] = []

        for source in job.get("sources", []):
            source_id = str(source["source_id"])
            result = results_by_source.get(source_id)
            if result is None:
                raise PipelineJobStateError(
                    f"Processor result state is missing for source: {source_id}"
                )
            artifact_path = self._pipeline_processed_path(str(result["artifact_key"]))
            reusable = (
                result.get("status") == "completed"
                and result.get("content_hash") == source.get("content_hash")
                and result.get("processor_config_hash") == config_hash
                and artifact_path.is_file()
            )
            if reusable:
                try:
                    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
                    completed.append({**source, **artifact, "reused": True})
                    continue
                except (OSError, json.JSONDecodeError):
                    reusable = False

            started = time.perf_counter()
            self._update_pipeline_document_result(
                job_id,
                source_id,
                {
                    "status": "processing",
                    "attempt_increment": True,
                    "error": None,
                    "warnings": [],
                },
            )
            try:
                source_path = self._pipeline_snapshot_path(str(source["snapshot_key"]))
                extracted_text = (
                    source_path.read_text(encoding="utf-8")
                    if source.get("content_mode") == "extracted_text"
                    else None
                )
                document = await asyncio.to_thread(
                    self.document_processor.process,
                    source_path,
                    filename=str(source["filename"]),
                    source_id=source_id,
                    config=profile,
                    extracted_text=extracted_text,
                )
                if not isinstance(document, ProcessedDocument):
                    raise PipelineJobStateError(
                        "Structured processor returned an unsupported document payload."
                    )
                mode = str(profile.get("mode") or "general")
                generated = await self.processor_generator.generate(
                    document,
                    mode=mode,
                    model_id=str(profile.get("model_id") or ""),
                    max_items=int(profile.get("max_generated_items", 20)),
                )
                artifact = {
                    "processed_document": document.payload(
                        include_text=True,
                        max_block_text=None,
                    ),
                    "generated_items": [item.payload(max_text=None) for item in generated],
                }
                artifact_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
                temporary.write_text(
                    json.dumps(artifact, ensure_ascii=False),
                    encoding="utf-8",
                )
                os.replace(temporary, artifact_path)
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                generated_count = len(generated)
                result_values = {
                    "status": "completed",
                    "content_hash": str(source.get("content_hash") or ""),
                    "processor_config_hash": config_hash,
                    "block_count": len(document.blocks),
                    "generated_count": generated_count,
                    "qa_count": generated_count if mode == "qa" else 0,
                    "summary_count": generated_count if mode == "summary" else 0,
                    "warnings": list(document.warnings),
                    "error": None,
                    "duration_ms": duration_ms,
                }
                self._update_pipeline_document_result(
                    job_id,
                    source_id,
                    result_values,
                )
                completed.append({**source, **artifact, "reused": False})
            except Exception as exc:
                error = self._safe_pipeline_error(exc)
                duration_ms = round((time.perf_counter() - started) * 1000, 2)
                self._update_pipeline_document_result(
                    job_id,
                    source_id,
                    {
                        "status": "failed",
                        "error": error,
                        "duration_ms": duration_ms,
                    },
                )
                failed.append({"source_id": source_id, "error": error})

        failure_policy = str(profile.get("failure_policy") or "continue_on_error")
        processor_error: str | None = None
        if not completed:
            processor_error = "All source documents failed during processing."
        elif failed and failure_policy == "strict":
            processor_error = (
                f"Strict processor policy blocked the candidate after {len(failed)} "
                "document failure(s)."
            )
        warnings = [
            f"{len(failed)} document(s) failed and were excluded from this candidate."
        ] if failed and processor_error is None else []

        def finish(job_record: dict[str, Any]) -> None:
            job_record["processor_error"] = processor_error
            job_record["warnings"] = warnings

        self._update_pipeline_job(job_id, finish)
        return completed

    def processor_gate_error(self, job_id: str) -> str | None:
        value = self.get_pipeline_job(job_id).get("processor_error")
        return str(value) if value else None

    def pipeline_job_cancel_requested(self, job_id: str) -> bool:
        return bool(self.get_pipeline_job(job_id).get("cancel_requested"))

    def request_pipeline_job_cancel(self, job_id: str) -> dict[str, Any]:
        def update(job: dict[str, Any]) -> None:
            status = str(job.get("status"))
            if status not in {"queued", "running"}:
                raise PipelineJobStateError("Only queued or running jobs can be cancelled.")
            if status == "queued":
                job["status"] = "cancelled"
                job["completed_at"] = time.time()
            else:
                job["cancel_requested"] = True

        job = self._update_pipeline_job(job_id, update)
        return self.pipeline_job_payload(job)

    def cancel_running_pipeline_job(self, job_id: str) -> None:
        def update(job: dict[str, Any]) -> None:
            job["status"] = "cancelled"
            job["completed_at"] = time.time()
            job["error"] = "Cancelled by user."
            for stage in job["stages"]:
                if stage["status"] in {"pending", "running"}:
                    stage["status"] = "cancelled"

        self._update_pipeline_job(job_id, update)

    def retry_pipeline_job(self, job_id: str) -> dict[str, Any]:
        def update(job: dict[str, Any]) -> None:
            if job.get("status") not in {"failed", "cancelled"}:
                raise PipelineJobStateError("Only failed or cancelled jobs can be retried.")
            job.update(
                {
                    "status": "queued",
                    "stages": self._new_pipeline_job_stages(),
                    "cancel_requested": False,
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                    "processor_error": None,
                    "warnings": [],
                }
            )
            for result in job.get("document_results", []):
                if not isinstance(result, dict):
                    continue
                if result.get("status") != "completed":
                    result.update(
                        {
                            "status": "pending",
                            "error": None,
                            "duration_ms": None,
                        }
                    )

        job = self._update_pipeline_job(job_id, update)
        return self.pipeline_job_payload(job)

    def fail_pipeline_job(self, job_id: str, error: str) -> None:
        def update(job: dict[str, Any]) -> None:
            job["status"] = "failed"
            job["error"] = str(error)[:500]
            job["completed_at"] = time.time()
            for stage in job["stages"]:
                if stage["status"] == "running":
                    stage["status"] = "failed"
                    stage["error"] = str(error)[:500]
                elif stage["status"] == "pending":
                    stage["status"] = "blocked"

        self._update_pipeline_job(job_id, update)

    def complete_pipeline_job(
        self,
        job_id: str,
        *,
        document_count: int,
        chunk_count: int,
    ) -> dict[str, Any]:
        version_holder: dict[str, Any] = {}

        def update(metadata: dict[str, Any], job: dict[str, Any]) -> None:
            now = time.time()
            processor_profile = json.loads(
                json.dumps(
                    job["config_snapshot"].get("processor_profile")
                    or job["config_snapshot"].get("stages", {}).get(
                        "stage_processor", {}
                    )
                )
            )
            document_results = [
                {
                    key: json.loads(json.dumps(value))
                    for key, value in result.items()
                    if key
                    not in {
                        "artifact_key",
                        "content_hash",
                        "processor_config_hash",
                    }
                }
                for result in job.get("document_results", [])
                if isinstance(result, dict)
            ]
            version = {
                "version_id": str(job["candidate_version_id"]),
                "kb_id": str(job["kb_id"]),
                "version": int(job["candidate_version"]),
                "status": "ready",
                "namespace": str(job["candidate_namespace"]),
                "draft_id": str(job["draft_id"]),
                "draft_version": int(job["draft_version"]),
                "config_snapshot": json.loads(json.dumps(job["config_snapshot"])),
                "index_schema_version": int(job["config_snapshot"].get("index_schema_version", 1)),
                "embedding_profile": json.loads(
                    json.dumps(job["config_snapshot"].get("embedding_profile", {}))
                ),
                "retrieval_profile": json.loads(
                    json.dumps(job["config_snapshot"].get("retrieval_profile", {}))
                ),
                "vector_index_ready": True,
                "lexical_index_ready": True,
                "source_summary": [
                    {
                        key: value
                        for key, value in source.items()
                        if key not in {"snapshot_key", "content_hash"}
                    }
                    for source in job["sources"]
                ],
                "processor_profile": processor_profile,
                "document_results": document_results,
                "document_count": document_count,
                "chunk_count": chunk_count,
                "block_count": sum(
                    int(item.get("block_count", 0)) for item in document_results
                ),
                "qa_count": sum(
                    int(item.get("qa_count", 0)) for item in document_results
                ),
                "summary_count": sum(
                    int(item.get("summary_count", 0)) for item in document_results
                ),
                "warnings": list(job.get("warnings") or []),
                "job_id": job_id,
                "created_at": now,
                "activated_at": None,
            }
            metadata["pipeline_versions"][version["version_id"]] = version
            job["status"] = "succeeded"
            job["completed_at"] = now
            job["updated_at"] = now
            job["error"] = None
            version_holder.update(version)

        self._update_pipeline_job_with_metadata(job_id, update)
        return self.pipeline_version_payload(version_holder)

    def list_pipeline_versions(self, kb_id: str) -> list[dict[str, Any]]:
        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        active_id = metadata["pipeline_active_versions"].get(kb_id)
        items = [
            self.pipeline_version_payload(item, active_id=active_id)
            for item in metadata["pipeline_versions"].values()
            if item.get("kb_id") == kb_id
        ]
        items.sort(key=lambda item: int(item["version"]), reverse=True)
        return items

    def get_pipeline_version(self, version_id: str) -> dict[str, Any]:
        metadata = self._read_metadata()
        version = metadata["pipeline_versions"].get(version_id)
        if not isinstance(version, dict):
            raise PipelineVersionNotFoundError("Knowledge pipeline version not found.")
        return json.loads(json.dumps(version))

    def pipeline_version_payload(
        self,
        version: dict[str, Any],
        *,
        active_id: str | None = None,
    ) -> dict[str, Any]:
        payload = {
            key: json.loads(json.dumps(value))
            for key, value in version.items()
            if key not in {"namespace", "config_snapshot"}
        }
        payload["active"] = str(active_id or "") == str(version.get("version_id"))
        return payload

    def activate_pipeline_version(self, version_id: str) -> dict[str, Any]:
        with self._metadata_lock:
            metadata = self._read_metadata_unlocked()
            version = metadata["pipeline_versions"].get(version_id)
            if not isinstance(version, dict):
                raise PipelineVersionNotFoundError("Knowledge pipeline version not found.")
            kb_id = str(version["kb_id"])
            previous_id = metadata["pipeline_active_versions"].get(kb_id)
            if previous_id and previous_id in metadata["pipeline_versions"]:
                metadata["pipeline_versions"][previous_id]["status"] = "ready"
            version["status"] = "active"
            version["activated_at"] = time.time()
            metadata["pipeline_active_versions"][kb_id] = version_id
            metadata["knowledge_bases"][kb_id]["updated_at"] = time.time()
            self._write_metadata_unlocked(metadata)
            return self.pipeline_version_payload(version, active_id=version_id)

    async def query_pipeline_version(
        self,
        version_id: str,
        question: str,
        *,
        top_k: int | None = None,
        retrieval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        version = self.get_pipeline_version(version_id)
        profile = self._retrieval_config_for_version(version, retrieval, top_k=top_k)
        result = await self._query_namespace(
            str(version["kb_id"]),
            str(version["namespace"]),
            question,
            config=profile,
            lexical_ready=bool(version.get("lexical_index_ready")),
        )
        return {
            "version_id": version_id,
            "version": int(version["version"]),
            **result,
        }

    def get_active_pipeline_version(self, kb_id: str) -> dict[str, Any] | None:
        metadata = self._read_metadata()
        self._ensure_kb_exists(metadata, kb_id)
        version_id = metadata["pipeline_active_versions"].get(kb_id)
        if not version_id:
            return None
        version = metadata["pipeline_versions"].get(version_id)
        return self.pipeline_version_payload(version, active_id=version_id) if isinstance(version, dict) else None

    def _new_pipeline_job_stages(self) -> list[dict[str, Any]]:
        return [
            {
                "id": stage_id,
                "title": title,
                "status": "pending",
                "progress": 0,
                "item_count": None,
                "started_at": None,
                "completed_at": None,
                "error": None,
            }
            for stage_id, title in PIPELINE_JOB_STAGES
        ]

    def _pipeline_stage(self, job: dict[str, Any], stage_id: str) -> dict[str, Any]:
        for stage in job["stages"]:
            if stage["id"] == stage_id:
                return stage
        raise PipelineJobStateError(f"Unknown pipeline job stage: {stage_id}")

    def _update_pipeline_job(
        self,
        job_id: str,
        update: Any,
    ) -> dict[str, Any]:
        def wrapped(metadata: dict[str, Any], job: dict[str, Any]) -> None:
            update(job)
            job["updated_at"] = time.time()

        return self._update_pipeline_job_with_metadata(job_id, wrapped)

    def _update_pipeline_job_with_metadata(
        self,
        job_id: str,
        update: Any,
    ) -> dict[str, Any]:
        with self._metadata_lock:
            metadata = self._read_metadata_unlocked()
            job = metadata["pipeline_jobs"].get(job_id)
            if not isinstance(job, dict):
                raise PipelineJobNotFoundError("Knowledge pipeline job not found.")
            update(metadata, job)
            job["updated_at"] = time.time()
            self._write_metadata_unlocked(metadata)
            return json.loads(json.dumps(job))

    def _pipeline_snapshot_path(self, snapshot_key: str) -> Path:
        path = (self.storage_dir / snapshot_key).resolve()
        root = self.pipeline_sources_dir.resolve()
        if path != root and root not in path.parents:
            raise PipelineJobStateError("Invalid pipeline source snapshot path.")
        return path

    def _pipeline_processed_path(self, artifact_key: str) -> Path:
        path = (self.storage_dir / artifact_key).resolve()
        root = self.pipeline_processed_dir.resolve()
        if path != root and root not in path.parents:
            raise PipelineJobStateError("Invalid pipeline processor artifact path.")
        return path

    def _update_pipeline_document_result(
        self,
        job_id: str,
        source_id: str,
        values: dict[str, Any],
    ) -> None:
        def update(job: dict[str, Any]) -> None:
            result = next(
                (
                    item
                    for item in job.get("document_results", [])
                    if isinstance(item, dict) and str(item.get("source_id")) == source_id
                ),
                None,
            )
            if result is None:
                raise PipelineJobStateError(
                    f"Processor result state is missing for source: {source_id}"
                )
            attempt_increment = bool(values.get("attempt_increment"))
            result.update(
                {
                    key: value
                    for key, value in values.items()
                    if key != "attempt_increment"
                }
            )
            if attempt_increment:
                result["attempt"] = int(result.get("attempt", 0)) + 1

        self._update_pipeline_job(job_id, update)

    def update_pipeline_document_chunk_counts(
        self,
        job_id: str,
        counts: dict[str, int],
    ) -> None:
        def update(job: dict[str, Any]) -> None:
            for result in job.get("document_results", []):
                if not isinstance(result, dict):
                    continue
                source_id = str(result.get("source_id") or "")
                if source_id in counts:
                    result["chunk_count"] = int(counts[source_id])

        self._update_pipeline_job(job_id, update)

    def _file_sha256(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _mapping_sha256(self, value: dict[str, Any]) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _safe_pipeline_error(self, exc: Exception) -> str:
        value = str(exc).strip() or exc.__class__.__name__
        for root in (self.storage_dir, self.uploads_dir):
            value = value.replace(str(root), "[local-path]")
            value = value.replace(str(root.resolve()), "[local-path]")
        value = re.sub(r"(?i)(bearer\s+|api[_-]?key[=:]\s*)\S+", r"\1[redacted]", value)
        return value[:500]

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
        retrieval: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Return citation anchors using the existing RAG retrieval path."""

        result = await self.query(kb_id, question, top_k=top_k, retrieval=retrieval)
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
                    "snippet": _preview_text(
                        str(source.get("matched_text") or source.get("text", ""))
                    ),
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
        self.lexical_store.delete_document(doc_id)
        kb_id = document["kb_id"]
        if kb_id in metadata["knowledge_bases"]:
            metadata["knowledge_bases"][kb_id]["updated_at"] = time.time()
        self._write_metadata(metadata)

    async def query(
        self,
        kb_id: str,
        question: str,
        *,
        top_k: int | None = 4,
        retrieval: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run retrieval and generate an answer from the retrieved context."""

        metadata = self._read_metadata()
        if kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("Knowledge base not found.")
        active_version_id = metadata["pipeline_active_versions"].get(kb_id)
        namespace = kb_id
        version: dict[str, Any] | None = None
        if active_version_id:
            stored_version = metadata["pipeline_versions"].get(active_version_id)
            if isinstance(stored_version, dict):
                version = stored_version
                namespace = str(version.get("namespace") or kb_id)
        config = self._retrieval_config_for_version(version, retrieval, top_k=top_k)
        return await self._query_namespace(
            kb_id,
            namespace,
            question,
            config=config,
            lexical_ready=bool(version and version.get("lexical_index_ready")),
        )

    async def _query_namespace(
        self,
        kb_id: str,
        namespace: str,
        question: str,
        *,
        config: RetrievalConfig,
        lexical_ready: bool,
    ) -> dict[str, Any]:
        """Query one explicit index namespace while preserving public KB identity."""

        clean_question = question.strip()
        if not clean_question:
            raise ValueError("问题不能为空。")
        metadata = self._read_metadata()
        if kb_id not in metadata["knowledge_bases"]:
            raise KnowledgeBaseNotFoundError("知识库不存在。")

        candidate_count = min(200, config.top_k * config.candidate_multiplier)
        warnings: list[str] = []
        vector_results: list[SearchResult] = []
        lexical_results: list[LexicalSearchResult] = []

        if config.mode in {"vector", "hybrid"}:
            query_embedding = (await self.embedder.embed_texts([clean_question]))[0]
            vector_results = self.vector_store.query(namespace, query_embedding, candidate_count)
        if config.mode in {"fulltext", "hybrid"}:
            if lexical_ready or self.lexical_store.count_namespace(namespace) > 0:
                lexical_results = self.lexical_store.query(namespace, clean_question, candidate_count)
            else:
                warnings.append("Full-text index is unavailable for this legacy version; vector retrieval was used.")

        vector_candidates = [self._candidate_from_vector(item) for item in vector_results]
        lexical_candidates = [self._candidate_from_lexical(item) for item in lexical_results]
        effective_config = config
        if config.mode == "fulltext" and not lexical_candidates:
            effective_config = RetrievalConfig.from_mapping(
                {**config.payload(), "mode": "vector", "rerank_enabled": config.rerank_enabled}
            )
            if not vector_candidates:
                query_embedding = (await self.embedder.embed_texts([clean_question]))[0]
                vector_results = self.vector_store.query(namespace, query_embedding, candidate_count)
                vector_candidates = [self._candidate_from_vector(item) for item in vector_results]
        fused = fuse_rankings(vector_candidates, lexical_candidates, effective_config)

        rerank_provider = "none"
        if config.rerank_enabled and fused:
            outcome = await self.reranker.rerank(
                clean_question,
                [RerankDocument(chunk_id=item.chunk_id, text=item.matched_text) for item in fused],
                provider=config.rerank_provider,
                model=config.rerank_model,
                top_n=min(config.rerank_top_n, len(fused)),
            )
            rerank_provider = outcome.provider
            if outcome.warning:
                warnings.append(outcome.warning)
            by_id = {item.chunk_id: item for item in fused}
            reranked: list[RetrievalCandidate] = []
            for ranked in outcome.items:
                candidate = by_id.pop(ranked.chunk_id, None)
                if candidate is None:
                    continue
                candidate.rerank_score = ranked.score
                reranked.append(candidate)
            fused = reranked + sorted(
                by_id.values(), key=lambda item: (-item.fused_score, item.chunk_id)
            )

        results = [item for item in fused if item.score >= config.score_threshold][: config.top_k]
        if not results:
            return {
                "answer": "没有在该知识库中找到相关内容，请尝试换一种问法或上传更多资料。",
                "sources": [],
                "warnings": warnings,
                "retrieval": self._retrieval_diagnostics(
                    config,
                    vector_count=len(vector_results),
                    fulltext_count=len(lexical_results),
                    rerank_provider=rerank_provider,
                ),
            }

        answer = await self._generate_answer(clean_question, results)
        return {
            "answer": answer,
            "sources": [
                {
                    "chunk_id": result.chunk_id,
                    "doc_id": result.doc_id,
                    "document_name": result.document_name,
                    "text": result.context_text,
                    "matched_text": result.matched_text,
                    "score": round(result.score, 4),
                    "vector_score": _rounded_optional(result.vector_score),
                    "fulltext_score": _rounded_optional(result.fulltext_score),
                    "fused_score": round(result.fused_score, 4),
                    "rerank_score": _rounded_optional(result.rerank_score),
                    "parent_chunk_id": result.parent_chunk_id,
                    "parent_lifted": bool(result.parent_chunk_id),
                    "chunk_type": result.chunk_type,
                    "start_char": result.start_char,
                    "end_char": result.end_char,
                }
                for result in results
            ],
            "warnings": warnings,
            "retrieval": self._retrieval_diagnostics(
                config,
                vector_count=len(vector_results),
                fulltext_count=len(lexical_results),
                rerank_provider=rerank_provider,
            ),
        }

    async def _generate_answer(
        self,
        question: str,
        results: list[RetrievalCandidate],
    ) -> str:
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        if not self.llm_enabled or not api_key:
            return self._extractive_answer(results)

        context = "\n\n".join(
            f"[来源：{result.document_name}]\n{result.context_text}" for result in results
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

    def _extractive_answer(self, results: list[RetrievalCandidate]) -> str:
        best = results[0]
        return f"根据知识库资料：{best.context_text}"

    def retrieval_capabilities(self) -> dict[str, Any]:
        rerank = self.reranker.capabilities()
        return {
            "version": "rag-retrieval-capabilities-v2",
            "index_schema_version": 2,
            "vector": {
                "available": True,
                "backend": self.vector_store.__class__.__name__,
            },
            "fulltext": {
                "available": True,
                "backend": self.lexical_store.backend,
            },
            "embedding": self._default_embedding_profile(),
            "rerank": rerank,
            "modes": ["vector", "fulltext", "hybrid"],
        }

    def _retrieval_config_for_version(
        self,
        version: dict[str, Any] | None,
        override: dict[str, Any] | None,
        *,
        top_k: int | None,
    ) -> RetrievalConfig:
        if version and int(version.get("index_schema_version", 1)) >= 2:
            base = RetrievalConfig.from_mapping(version.get("retrieval_profile"))
        else:
            base = RetrievalConfig.from_mapping(
                {
                    "mode": "vector",
                    "top_k": 4,
                    "rerank_enabled": False,
                    "rerank_provider": "none",
                }
            )
        merged = dict(override or {})
        if top_k is not None:
            merged["top_k"] = top_k
        return RetrievalConfig.from_mapping(merged, base=base)

    def _candidate_from_vector(self, item: SearchResult) -> RetrievalCandidate:
        return RetrievalCandidate(
            chunk_id=item.chunk_id,
            doc_id=item.doc_id,
            document_name=item.document_name,
            matched_text=item.text,
            context_text=item.parent_text or item.text,
            parent_chunk_id=item.parent_chunk_id,
            chunk_type=item.chunk_type,
            start_char=item.start_char,
            end_char=item.end_char,
            vector_score=item.score,
        )

    def _candidate_from_lexical(self, item: LexicalSearchResult) -> RetrievalCandidate:
        return RetrievalCandidate(
            chunk_id=item.chunk_id,
            doc_id=item.doc_id,
            document_name=item.document_name,
            matched_text=item.text,
            context_text=item.parent_text or item.text,
            parent_chunk_id=item.parent_chunk_id,
            chunk_type=item.chunk_type,
            start_char=item.start_char,
            end_char=item.end_char,
            fulltext_score=item.score,
        )

    def _retrieval_diagnostics(
        self,
        config: RetrievalConfig,
        *,
        vector_count: int,
        fulltext_count: int,
        rerank_provider: str,
    ) -> dict[str, Any]:
        return {
            **config.payload(),
            "vector_candidate_count": vector_count,
            "fulltext_candidate_count": fulltext_count,
            "rerank_provider_used": rerank_provider,
        }

    def _default_embedding_profile(self) -> dict[str, Any]:
        degraded = self.embedder.embedding_mode == "hash" or not self.embedder.api_key
        return {
            "provider": "hash" if degraded else "openai_compatible",
            "model": self.embedder.model,
            "dimension": self.embedder.dimension,
            "degraded": degraded,
        }

    def _validated_embedding_profile(
        self,
        current: dict[str, Any] | None,
        patch: dict[str, Any] | None,
    ) -> dict[str, Any]:
        config = {**self._default_embedding_profile(), **dict(current or {})}
        if patch:
            unknown = set(patch) - {"model"}
            if unknown:
                raise PipelineDraftValidationError(
                    f"Unsupported embedding profile field: {sorted(unknown)[0]}"
                )
            model = str(patch.get("model") or config["model"]).strip()
            if not model or len(model) > 200:
                raise PipelineDraftValidationError("embedding_profile.model is invalid.")
            config["model"] = model
        config["provider"] = self._default_embedding_profile()["provider"]
        config["dimension"] = self.embedder.dimension
        config["degraded"] = self._default_embedding_profile()["degraded"]
        return config

    def _default_pipeline_draft_stages(self) -> dict[str, dict[str, Any]]:
        return {
            "stage_data_source": {
                "source_mode": "uploaded_files",
                "allowed_extensions": sorted(supported_extensions()),
            },
            "stage_processor": {
                "parser": "structured_local_parser",
                "mode": "general",
                "model_id": self.processor_generator.default_model(),
                "failure_policy": "continue_on_error",
                "extract_title": True,
                "preserve_tables": True,
                "preserve_code_blocks": True,
                "remove_repeated_headers_footers": True,
                "max_generated_items": 20,
            },
            "stage_chunker": {
                "strategy": "recursive_character",
                "chunk_size": self.splitter.chunk_size,
                "chunk_overlap": self.splitter.chunk_overlap,
                "separators": list(DEFAULT_SEPARATORS),
                "parent_chunk_size": 1500,
                "parent_chunk_overlap": 100,
                "child_chunk_size": 400,
                "child_chunk_overlap": 50,
                "parent_separators": list(DEFAULT_SEPARATORS),
                "child_separators": list(DEFAULT_SEPARATORS),
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
                "index_schema_version": 2,
                "embedding_profile": self._default_embedding_profile(),
                "retrieval_profile": RetrievalConfig().payload(),
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
            "index_schema_version": 2,
            "embedding_profile": self._validated_embedding_profile(
                draft.get("embedding_profile") if isinstance(draft.get("embedding_profile"), dict) else None,
                None,
            ),
            "retrieval_profile": RetrievalConfig.from_mapping(
                draft.get("retrieval_profile") if isinstance(draft.get("retrieval_profile"), dict) else None
            ).payload(),
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
            parser = str(
                patch.get("parser", config.get("parser", "structured_local_parser"))
            )
            if parser == "local_document_parser":
                parser = "structured_local_parser"
            if parser != "structured_local_parser":
                raise PipelineDraftValidationError(
                    "processor.parser must be structured_local_parser."
                )
            mode = str(patch.get("mode", config.get("mode", "general"))).strip()
            if mode not in {"general", "qa", "summary"}:
                raise PipelineDraftValidationError(
                    "processor.mode must be general, qa, or summary."
                )
            failure_policy = str(
                patch.get(
                    "failure_policy",
                    config.get("failure_policy", "continue_on_error"),
                )
            ).strip()
            if failure_policy not in {"continue_on_error", "strict"}:
                raise PipelineDraftValidationError(
                    "processor.failure_policy must be continue_on_error or strict."
                )
            model_id = str(
                patch.get(
                    "model_id",
                    config.get("model_id", self.processor_generator.default_model()),
                )
                or ""
            ).strip()
            if len(model_id) > 200 or (mode in {"qa", "summary"} and not model_id):
                raise PipelineDraftValidationError("processor.model_id is invalid.")
            max_generated_items = self._coerce_int(
                patch.get(
                    "max_generated_items",
                    config.get("max_generated_items", 20),
                ),
                "processor.max_generated_items",
            )
            if not 1 <= max_generated_items <= 50:
                raise PipelineDraftValidationError(
                    "processor.max_generated_items must be between 1 and 50."
                )
            bool_fields = (
                "extract_title",
                "preserve_tables",
                "preserve_code_blocks",
                "remove_repeated_headers_footers",
            )
            bool_values: dict[str, bool] = {}
            for field_name in bool_fields:
                value = patch.get(field_name, config.get(field_name, True))
                if not isinstance(value, bool):
                    raise PipelineDraftValidationError(
                        f"processor.{field_name} must be a boolean."
                    )
                bool_values[field_name] = value
            config.update(
                {
                    "parser": parser,
                    "mode": mode,
                    "model_id": model_id,
                    "failure_policy": failure_policy,
                    "max_generated_items": max_generated_items,
                    **bool_values,
                }
            )
            return config

        if stage_id == "stage_chunker":
            strategy = str(
                patch.get(
                    "strategy",
                    config.get("strategy", "recursive_character"),
                )
            )
            if strategy == "local_recursive_character_chunks":
                strategy = "recursive_character"
            if strategy not in {"recursive_character", "parent_child"}:
                raise PipelineDraftValidationError(
                    "chunker.strategy must be recursive_character or parent_child."
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
            separators = self._validated_separators(
                patch.get("separators", config.get("separators", DEFAULT_SEPARATORS)),
                "chunker.separators",
            )
            parent_size = self._coerce_int(
                patch.get("parent_chunk_size", config.get("parent_chunk_size", 1500)),
                "chunker.parent_chunk_size",
            )
            parent_overlap = self._coerce_int(
                patch.get("parent_chunk_overlap", config.get("parent_chunk_overlap", 100)),
                "chunker.parent_chunk_overlap",
            )
            child_size = self._coerce_int(
                patch.get("child_chunk_size", config.get("child_chunk_size", 400)),
                "chunker.child_chunk_size",
            )
            child_overlap = self._coerce_int(
                patch.get("child_chunk_overlap", config.get("child_chunk_overlap", 50)),
                "chunker.child_chunk_overlap",
            )
            if not 200 <= parent_size <= 8000:
                raise PipelineDraftValidationError(
                    "chunker.parent_chunk_size must be between 200 and 8000."
                )
            if not 100 <= child_size < parent_size:
                raise PipelineDraftValidationError(
                    "chunker.child_chunk_size must be between 100 and parent_chunk_size."
                )
            if parent_overlap < 0 or parent_overlap >= parent_size:
                raise PipelineDraftValidationError(
                    "chunker.parent_chunk_overlap must be smaller than parent_chunk_size."
                )
            if child_overlap < 0 or child_overlap >= child_size:
                raise PipelineDraftValidationError(
                    "chunker.child_chunk_overlap must be smaller than child_chunk_size."
                )
            config.update(
                {
                    "strategy": strategy,
                    "chunk_size": chunk_size,
                    "chunk_overlap": chunk_overlap,
                    "separators": separators,
                    "parent_chunk_size": parent_size,
                    "parent_chunk_overlap": parent_overlap,
                    "child_chunk_size": child_size,
                    "child_chunk_overlap": child_overlap,
                    "parent_separators": self._validated_separators(
                        patch.get(
                            "parent_separators",
                            config.get("parent_separators", DEFAULT_SEPARATORS),
                        ),
                        "chunker.parent_separators",
                    ),
                    "child_separators": self._validated_separators(
                        patch.get(
                            "child_separators",
                            config.get("child_separators", DEFAULT_SEPARATORS),
                        ),
                        "chunker.child_separators",
                    ),
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

    def _validated_separators(self, value: Any, field_name: str) -> list[str]:
        if not isinstance(value, list) or not value or len(value) > 20:
            raise PipelineDraftValidationError(
                f"{field_name} must contain between 1 and 20 strings."
            )
        result: list[str] = []
        for item in value:
            if not isinstance(item, str) or len(item) > 20:
                raise PipelineDraftValidationError(
                    f"{field_name} entries must be strings up to 20 characters."
                )
            if item not in result:
                result.append(item)
        if "" not in result:
            result.append("")
        return result

    def _empty_metadata(self) -> dict[str, dict[str, Any]]:
        return {
            "knowledge_bases": {},
            "documents": {},
            "pipeline_drafts": {},
            "pipeline_jobs": {},
            "pipeline_versions": {},
            "pipeline_active_versions": {},
        }

    def _read_metadata(self) -> dict[str, dict[str, Any]]:
        with self._metadata_lock:
            return self._read_metadata_unlocked()

    def _read_metadata_unlocked(self) -> dict[str, dict[str, Any]]:
        if not self.metadata_path.exists():
            return self._empty_metadata()
        try:
            data = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return self._empty_metadata()
        if not isinstance(data, dict):
            return self._empty_metadata()
        return {
            "knowledge_bases": data.get("knowledge_bases") if isinstance(data.get("knowledge_bases"), dict) else {},
            "documents": data.get("documents") if isinstance(data.get("documents"), dict) else {},
            "pipeline_drafts": data.get("pipeline_drafts") if isinstance(data.get("pipeline_drafts"), dict) else {},
            "pipeline_jobs": data.get("pipeline_jobs") if isinstance(data.get("pipeline_jobs"), dict) else {},
            "pipeline_versions": data.get("pipeline_versions") if isinstance(data.get("pipeline_versions"), dict) else {},
            "pipeline_active_versions": data.get("pipeline_active_versions") if isinstance(data.get("pipeline_active_versions"), dict) else {},
        }

    def _write_metadata(self, metadata: dict[str, Any]) -> None:
        with self._metadata_lock:
            self._write_metadata_unlocked(metadata)

    def _write_metadata_unlocked(self, metadata: dict[str, Any]) -> None:
        temporary = self.metadata_path.with_suffix(self.metadata_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.metadata_path)

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


def _rounded_optional(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None
