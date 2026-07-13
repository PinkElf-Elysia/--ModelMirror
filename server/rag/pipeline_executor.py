from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .embedder import EmbeddingClient
from .lexical_store import LexicalChunk
from .rag_service import RagService
from .splitter import ParentChildTextSplitter, TextSplitter
from .vector_store import VectorChunk


logger = logging.getLogger(__name__)


class PipelineJobCancelled(RuntimeError):
    """Raised internally after a cooperative cancellation request."""


class KnowledgePipelineExecutor:
    """Single-process executor for versioned knowledge pipeline jobs."""

    def __init__(
        self,
        service: RagService,
        *,
        run_registry: Any | None = None,
        poll_interval: float = 0.5,
    ) -> None:
        self.service = service
        self.run_registry = run_registry
        self.poll_interval = max(0.1, poll_interval)
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._stopping = False

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self.service.recover_pipeline_jobs()
        self._task = asyncio.create_task(self._worker(), name="knowledge-pipeline-executor")
        self._wake.set()

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task is not None:
            await self._task
        self._task = None

    def notify(self) -> None:
        self._wake.set()

    async def record_job_event(
        self,
        job_id: str,
        *,
        event_type: str,
        title: str,
        summary: str = "",
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._checkpoint(
            job_id,
            event_type=event_type,
            title=title,
            summary=summary,
            severity=severity,
            metadata=metadata,
        )

    async def run_once(self) -> bool:
        job = self.service.claim_next_pipeline_job()
        if job is None:
            return False
        await self._execute(job)
        return True

    async def _worker(self) -> None:
        while not self._stopping:
            processed = await self.run_once()
            if processed:
                continue
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self.poll_interval)
            except TimeoutError:
                pass

    async def _checkpoint(
        self,
        job_id: str,
        *,
        event_type: str,
        title: str,
        summary: str = "",
        severity: str = "info",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if self.run_registry is None:
            return
        job = self.service.get_pipeline_job(job_id)
        run_id = str(job.get("run_id") or "")
        existing_run = await self.run_registry.get_run(run_id) if run_id else None
        if existing_run is None:
            previous_run_id = run_id or None
            job_status = str(job.get("status") or "queued")
            run_status = {
                "succeeded": "completed",
                "failed": "failed",
                "cancelled": "cancelled",
            }.get(job_status, "running")
            run_metadata = {
                "job_id": job_id,
                "kb_id": job["kb_id"],
                "draft_version": job["draft_version"],
            }
            if previous_run_id:
                run_metadata["recovery_of_run_id"] = previous_run_id
            run = await self.run_registry.create_run(
                "knowledge_pipeline",
                f"Knowledge pipeline: {job['kb_id']}",
                status=run_status,
                source_id=job_id,
                metadata=run_metadata,
            )
            run_id = run.run_id
            job_error = str(job.get("error") or "")
            if job_error:
                await self.run_registry.update_run(run_id, error=job_error)
            self.service.set_pipeline_job_run_id(job_id, run_id)
        await self.run_registry.record_checkpoint(
            run_id,
            event_type=event_type,
            title=title,
            summary=summary,
            severity=severity,
            metadata=dict(metadata or {}),
        )

    async def _execute(self, job: dict[str, Any]) -> None:
        job_id = str(job["job_id"])
        namespace = str(job["candidate_namespace"])
        try:
            await self._checkpoint(
                job_id,
                event_type="knowledge_pipeline.started",
                title="Knowledge pipeline started",
                summary=f"Processing {len(job['sources'])} source files.",
                metadata={"attempt": job["attempt"], "source_count": len(job["sources"])},
            )
            self.service.vector_store.delete_knowledge_base(namespace)
            self.service.lexical_store.delete_namespace(namespace)

            await self._stage(job_id, "load", self._load_sources)
            parsed = await self._stage(job_id, "process", self._parse_sources)
            chunks = await self._stage(job_id, "chunk", self._chunk_sources, parsed)
            embeddings = await self._stage(job_id, "embed", self._embed_chunks, chunks)
            await self._stage(job_id, "store", self._store_chunks, chunks, embeddings)

            version = self.service.complete_pipeline_job(
                job_id,
                document_count=len(parsed),
                chunk_count=len(chunks),
            )
            await self._checkpoint(
                job_id,
                event_type="knowledge_pipeline.version_ready",
                title="Candidate index ready",
                summary=f"Candidate v{version['version']} contains {len(chunks)} chunks.",
                metadata={
                    "version_id": version["version_id"],
                    "version": version["version"],
                    "chunk_count": len(chunks),
                },
            )
            if self.run_registry is not None:
                run_id = str(self.service.get_pipeline_job(job_id).get("run_id") or "")
                if run_id:
                    await self.run_registry.update_run(
                        run_id,
                        status="completed",
                        metadata={"candidate_version_id": version["version_id"]},
                    )
        except PipelineJobCancelled:
            self.service.vector_store.delete_knowledge_base(namespace)
            self.service.lexical_store.delete_namespace(namespace)
            await self._checkpoint(
                job_id,
                event_type="knowledge_pipeline.cancelled",
                title="Knowledge pipeline cancelled",
                summary="The candidate index was discarded; the active version was unchanged.",
                severity="warning",
            )
            if self.run_registry is not None:
                run_id = str(self.service.get_pipeline_job(job_id).get("run_id") or "")
                if run_id:
                    await self.run_registry.update_run(
                        run_id,
                        status="cancelled",
                        error="Cancelled by user.",
                    )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Knowledge pipeline job failed job_id=%s", job_id)
            self.service.vector_store.delete_knowledge_base(namespace)
            self.service.lexical_store.delete_namespace(namespace)
            self.service.fail_pipeline_job(job_id, str(exc))
            await self._checkpoint(
                job_id,
                event_type="knowledge_pipeline.failed",
                title="Knowledge pipeline failed",
                summary=str(exc),
                severity="error",
            )
            if self.run_registry is not None:
                run_id = str(self.service.get_pipeline_job(job_id).get("run_id") or "")
                if run_id:
                    await self.run_registry.update_run(run_id, status="failed", error=str(exc))

    async def _stage(
        self,
        job_id: str,
        stage_id: str,
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
    ) -> Any:
        if self.service.pipeline_job_cancel_requested(job_id):
            self.service.cancel_running_pipeline_job(job_id)
            raise PipelineJobCancelled("Knowledge pipeline job was cancelled.")
        self.service.start_pipeline_job_stage(job_id, stage_id)
        await self._checkpoint(
            job_id,
            event_type=f"knowledge_pipeline.{stage_id}.started",
            title=f"{stage_id.title()} stage started",
            metadata={"stage": stage_id},
        )
        result = await operation(job_id, *args)
        count = len(result) if isinstance(result, (list, tuple)) else None
        self.service.complete_pipeline_job_stage(job_id, stage_id, item_count=count)
        await self._checkpoint(
            job_id,
            event_type=f"knowledge_pipeline.{stage_id}.completed",
            title=f"{stage_id.title()} stage completed",
            metadata={"stage": stage_id, "item_count": count},
        )
        return result

    async def _load_sources(self, job_id: str) -> list[dict[str, Any]]:
        return self.service.load_pipeline_job_sources(job_id)

    async def _parse_sources(
        self,
        job_id: str,
    ) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self.service.parse_pipeline_job_sources, job_id)

    async def _chunk_sources(
        self,
        job_id: str,
        parsed: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        job = self.service.get_pipeline_job(job_id)
        snapshot = job["config_snapshot"]
        stages = snapshot.get("stages", snapshot)
        chunker = stages["stage_chunker"]
        strategy = str(chunker.get("strategy") or "recursive_character")
        if strategy == "local_recursive_character_chunks":
            strategy = "recursive_character"
        if strategy == "parent_child":
            splitter: TextSplitter | ParentChildTextSplitter = ParentChildTextSplitter(
                parent_chunk_size=int(chunker.get("parent_chunk_size", 1500)),
                parent_chunk_overlap=int(chunker.get("parent_chunk_overlap", 100)),
                child_chunk_size=int(chunker.get("child_chunk_size", 400)),
                child_chunk_overlap=int(chunker.get("child_chunk_overlap", 50)),
                parent_separators=(
                    list(chunker["parent_separators"])
                    if chunker.get("parent_separators")
                    else None
                ),
                child_separators=(
                    list(chunker["child_separators"])
                    if chunker.get("child_separators")
                    else None
                ),
            )
        else:
            splitter = TextSplitter(
                chunk_size=int(chunker["chunk_size"]),
                chunk_overlap=int(chunker["chunk_overlap"]),
                separators=list(chunker["separators"]) if chunker.get("separators") else None,
            )
        chunks: list[dict[str, Any]] = []
        for source in parsed:
            for segment in splitter.split_segments(str(source["text"])):
                parent_id = (
                    f"{source['source_id']}_{segment.parent_chunk_id}"
                    if segment.parent_chunk_id
                    else None
                )
                chunks.append(
                    {
                        "source": source,
                        "index": segment.index,
                        "text": segment.text,
                        "start_char": segment.start_char,
                        "end_char": segment.end_char,
                        "chunk_type": segment.chunk_type,
                        "parent_chunk_id": parent_id,
                        "parent_text": segment.parent_text,
                    }
                )
        if not chunks:
            raise RuntimeError("No indexable text chunks were produced.")
        return chunks

    async def _embed_chunks(
        self,
        job_id: str,
        chunks: list[dict[str, Any]],
    ) -> list[list[float]]:
        job = self.service.get_pipeline_job(job_id)
        snapshot = job["config_snapshot"]
        profile = snapshot.get("embedding_profile", {}) if isinstance(snapshot, dict) else {}
        model = str(profile.get("model") or self.service.embedder.model)
        embedder = self.service.embedder
        if model != self.service.embedder.model:
            embedder = EmbeddingClient(
                api_base=self.service.embedder.api_base,
                api_key=self.service.embedder.api_key,
                model=model,
                dimension=self.service.embedder.dimension,
            )
        return await embedder.embed_texts([str(item["text"]) for item in chunks])

    async def _store_chunks(
        self,
        job_id: str,
        chunks: list[dict[str, Any]],
        embeddings: list[list[float]],
    ) -> None:
        job = self.service.get_pipeline_job(job_id)
        version_id = str(job["candidate_version_id"])
        namespace = str(job["candidate_namespace"])
        vector_chunks: list[VectorChunk] = []
        lexical_chunks: list[LexicalChunk] = []
        for position, item in enumerate(chunks):
            source = item["source"]
            source_id = str(source["source_id"])
            doc_id = f"{version_id}_{source_id}"
            chunk_id = f"{doc_id}_chunk_{item['index']}"
            common = {
                "parent_chunk_id": item.get("parent_chunk_id"),
                "parent_text": item.get("parent_text"),
                "chunk_type": str(item.get("chunk_type") or "standard"),
                "start_char": int(item.get("start_char", 0)),
                "end_char": int(item.get("end_char", 0)),
            }
            vector_chunks.append(
                VectorChunk(
                    id=chunk_id,
                    kb_id=namespace,
                    doc_id=doc_id,
                    document_name=str(source["filename"]),
                    text=str(item["text"]),
                    embedding=embeddings[position],
                    chunk_index=int(item["index"]),
                    **common,
                )
            )
            lexical_chunks.append(
                LexicalChunk(
                    chunk_id=chunk_id,
                    namespace=namespace,
                    doc_id=doc_id,
                    document_name=str(source["filename"]),
                    text=str(item["text"]),
                    chunk_index=int(item["index"]),
                    **common,
                )
            )
        self.service.vector_store.add_chunks(vector_chunks)
        self.service.lexical_store.add_chunks(lexical_chunks)
        if self.service.lexical_store.count_namespace(namespace) != len(lexical_chunks):
            raise RuntimeError("Full-text index count does not match the vector candidate index.")
