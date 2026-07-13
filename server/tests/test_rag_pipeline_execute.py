from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from server.main import app
from server.rag.api import (
    set_pipeline_executor_for_tests,
    set_rag_service_for_tests,
)
from server.rag.embedder import EmbeddingClient
from server.rag.pipeline_executor import KnowledgePipelineExecutor
from server.rag.rag_service import RagService
from server.rag.vector_store import LocalJsonVectorStore
from server.xpert_runtime.run_registry import RunRegistry
from server.xperts.api import set_xpert_context_store_for_tests
from server.xperts.context import XpertContextStore


@pytest_asyncio.fixture
async def pipeline_runtime(tmp_path: Path):
    service = RagService(
        storage_dir=tmp_path / "rag-storage",
        uploads_dir=tmp_path / "rag-uploads",
        embedder=EmbeddingClient(api_key="", dimension=128),
        vector_store=LocalJsonVectorStore(tmp_path / "rag-storage" / "vectors.json"),
        llm_enabled=False,
    )
    registry = RunRegistry()
    executor = KnowledgePipelineExecutor(service, run_registry=registry, poll_interval=0.01)
    context_store = XpertContextStore(tmp_path / "runtime-storage")
    set_rag_service_for_tests(service)
    set_pipeline_executor_for_tests(executor)
    set_xpert_context_store_for_tests(context_store)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client, service, executor, registry, context_store
    set_pipeline_executor_for_tests(None)
    set_rag_service_for_tests(None)
    set_xpert_context_store_for_tests(None)


async def create_kb(client: httpx.AsyncClient, name: str = "versioned") -> str:
    response = await client.post("/api/rag/knowledge_bases", json={"name": name})
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def upload_text(client: httpx.AsyncClient, kb_id: str, filename: str, text: str) -> str:
    response = await client.post(
        f"/api/rag/knowledge_bases/{kb_id}/documents",
        files={"file": (filename, text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 200, response.text
    return str(response.json()["id"])


async def execute_current_draft(
    client: httpx.AsyncClient,
    executor: KnowledgePipelineExecutor,
    kb_id: str,
    *,
    source_document_ids: list[str] | None = None,
    xpert_file_refs: list[dict[str, str]] | None = None,
) -> dict:
    draft = (await client.get(f"/api/rag/pipeline/draft?kb_id={kb_id}")).json()
    response = await client.post(
        f"/api/rag/pipeline/draft/{kb_id}/execute",
        json={
            "draft_version": draft["version"],
            "source_document_ids": source_document_ids,
            "xpert_file_refs": xpert_file_refs or [],
        },
    )
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["status"] == "queued"
    assert await executor.run_once() is True
    completed = (await client.get(f"/api/rag/pipeline/jobs/{created['job_id']}")).json()
    assert completed["status"] == "succeeded"
    return completed


@pytest.mark.asyncio
async def test_candidate_version_requires_manual_activation_and_supports_rollback(
    pipeline_runtime,
) -> None:
    client, service, executor, registry, _ = pipeline_runtime
    kb_id = await create_kb(client)
    alpha_id = await upload_text(
        client,
        kb_id,
        "alpha.txt",
        "Alpha release policy uses manual approval before deployment.",
    )

    first_job = await execute_current_draft(
        client,
        executor,
        kb_id,
        source_document_ids=[alpha_id],
    )
    versions = (await client.get(f"/api/rag/pipeline/versions?kb_id={kb_id}")).json()
    first_version = versions["versions"][0]
    assert first_version["status"] == "ready"
    assert first_version["active"] is False
    assert service.get_active_pipeline_version(kb_id) is None

    activate = await client.post(
        f"/api/rag/pipeline/versions/{first_version['version_id']}/activate"
    )
    assert activate.status_code == 200, activate.text
    assert activate.json()["active"] is True

    beta_id = await upload_text(
        client,
        kb_id,
        "beta.txt",
        "Beta architecture introduces a versioned index candidate.",
    )
    active_before = await service.query(kb_id, "Beta architecture", top_k=5)
    assert {item["document_name"] for item in active_before["sources"]} == {"alpha.txt"}

    second_job = await execute_current_draft(
        client,
        executor,
        kb_id,
        source_document_ids=[alpha_id, beta_id],
    )
    second_version_id = str(second_job["candidate_version_id"])
    preview = await client.post(
        f"/api/rag/pipeline/versions/{second_version_id}/query",
        json={"question": "Beta architecture", "top_k": 5},
    )
    assert preview.status_code == 200, preview.text
    assert "beta.txt" in {item["document_name"] for item in preview.json()["sources"]}

    active_still_first = service.get_active_pipeline_version(kb_id)
    assert active_still_first is not None
    assert active_still_first["version_id"] == first_version["version_id"]

    await client.post(f"/api/rag/pipeline/versions/{second_version_id}/activate")
    active_after = await service.query(kb_id, "Beta architecture", top_k=5)
    assert "beta.txt" in {item["document_name"] for item in active_after["sources"]}

    rollback = await client.post(
        f"/api/rag/pipeline/versions/{first_version['version_id']}/activate"
    )
    assert rollback.status_code == 200
    rolled_back = await service.query(kb_id, "Beta architecture", top_k=5)
    assert {item["document_name"] for item in rolled_back["sources"]} == {"alpha.txt"}

    runs = await registry.list_runs(run_type="knowledge_pipeline")
    assert len(runs) == 2
    first_checkpoints = await registry.list_checkpoints(runs[-1].run_id, limit=100)
    assert {item.event_type for item in first_checkpoints} >= {
        "knowledge_pipeline.started",
        "knowledge_pipeline.version_ready",
        "knowledge_pipeline.version_activated",
    }


@pytest.mark.asyncio
async def test_persisted_job_rebinds_to_recovery_run_after_registry_restart(
    pipeline_runtime,
) -> None:
    client, service, executor, _, _ = pipeline_runtime
    kb_id = await create_kb(client, "registry recovery")
    document_id = await upload_text(client, kb_id, "recovery.txt", "Recovery run source.")
    completed = await execute_current_draft(
        client,
        executor,
        kb_id,
        source_document_ids=[document_id],
    )
    previous_run_id = str(completed["run_id"])

    recovered_registry = RunRegistry()
    recovered_executor = KnowledgePipelineExecutor(
        service,
        run_registry=recovered_registry,
    )
    await recovered_executor.record_job_event(
        completed["job_id"],
        event_type="knowledge_pipeline.version_previewed",
        title="Candidate previewed after restart",
    )

    recovered_job = service.get_pipeline_job(completed["job_id"])
    assert recovered_job["run_id"] != previous_run_id
    recovered_run = await recovered_registry.get_run(recovered_job["run_id"])
    assert recovered_run is not None
    assert recovered_run.status == "completed"
    assert recovered_run.metadata["recovery_of_run_id"] == previous_run_id
    checkpoints = await recovered_registry.list_checkpoints(recovered_run.run_id)
    assert [item.event_type for item in checkpoints] == [
        "knowledge_pipeline.version_previewed"
    ]


@pytest.mark.asyncio
async def test_xpert_attachment_source_is_snapshotted_and_cross_xpert_access_is_rejected(
    pipeline_runtime,
) -> None:
    client, _, executor, _, context_store = pipeline_runtime
    kb_id = await create_kb(client, "attachment target")
    conversation = context_store.create_conversation("xpert-a", title="source")
    asset = context_store.add_file(
        "xpert-a",
        conversation.conversation_id,
        filename="brief.txt",
        content=b"The attachment defines the Orion launch checklist.",
    )

    bad = await client.post(
        f"/api/rag/pipeline/draft/{kb_id}/execute",
        json={
            "draft_version": 1,
            "source_document_ids": [],
            "xpert_file_refs": [
                {
                    "xpert_id": "xpert-b",
                    "conversation_id": conversation.conversation_id,
                    "asset_id": asset.asset_id,
                }
            ],
        },
    )
    assert bad.status_code == 404

    completed = await execute_current_draft(
        client,
        executor,
        kb_id,
        source_document_ids=[],
        xpert_file_refs=[
            {
                "xpert_id": "xpert-a",
                "conversation_id": conversation.conversation_id,
                "asset_id": asset.asset_id,
            },
            {
                "xpert_id": "xpert-a",
                "conversation_id": conversation.conversation_id,
                "asset_id": asset.asset_id,
            },
        ],
    )
    assert completed["source_count"] == 1
    context_store.archive_file("xpert-a", conversation.conversation_id, asset.asset_id)
    preview = await client.post(
        f"/api/rag/pipeline/versions/{completed['candidate_version_id']}/query",
        json={"question": "Orion checklist", "top_k": 3},
    )
    assert preview.status_code == 200
    assert preview.json()["sources"][0]["document_name"] == "brief.txt"


@pytest.mark.asyncio
async def test_cancelled_and_failed_jobs_do_not_change_active_version(
    pipeline_runtime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, service, executor, _, _ = pipeline_runtime
    kb_id = await create_kb(client, "failure isolation")
    document_id = await upload_text(client, kb_id, "stable.txt", "Stable production index.")
    completed = await execute_current_draft(
        client,
        executor,
        kb_id,
        source_document_ids=[document_id],
    )
    version_id = str(completed["candidate_version_id"])
    await client.post(f"/api/rag/pipeline/versions/{version_id}/activate")

    draft = (await client.get(f"/api/rag/pipeline/draft?kb_id={kb_id}")).json()
    queued = await client.post(
        f"/api/rag/pipeline/draft/{kb_id}/execute",
        json={"draft_version": draft["version"], "source_document_ids": [document_id]},
    )
    cancel = await client.post(f"/api/rag/pipeline/jobs/{queued.json()['job_id']}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert service.get_active_pipeline_version(kb_id)["version_id"] == version_id

    failed = await client.post(
        f"/api/rag/pipeline/draft/{kb_id}/execute",
        json={"draft_version": draft["version"], "source_document_ids": [document_id]},
    )

    async def fail_embeddings(_: list[str]) -> list[list[float]]:
        raise RuntimeError("synthetic embedding failure")

    monkeypatch.setattr(service.embedder, "embed_texts", fail_embeddings)
    assert await executor.run_once() is True
    failed_payload = (await client.get(f"/api/rag/pipeline/jobs/{failed.json()['job_id']}")).json()
    assert failed_payload["status"] == "failed"
    assert "synthetic embedding failure" in failed_payload["error"]
    assert service.get_active_pipeline_version(kb_id)["version_id"] == version_id

    retry = await client.post(f"/api/rag/pipeline/jobs/{failed_payload['job_id']}/retry")
    assert retry.status_code == 200
    assert retry.json()["status"] == "queued"


def test_pipeline_metadata_is_atomic_and_recovers_running_jobs(tmp_path: Path) -> None:
    service = RagService(
        storage_dir=tmp_path / "storage",
        uploads_dir=tmp_path / "uploads",
        embedder=EmbeddingClient(api_key="", dimension=32),
        vector_store=LocalJsonVectorStore(tmp_path / "storage" / "vectors.json"),
        llm_enabled=False,
    )
    kb = service.create_knowledge_base("recovery")
    source = tmp_path / "source.txt"
    source.write_text("recovery source", encoding="utf-8")
    metadata = service._read_metadata()
    metadata["documents"]["doc-recovery"] = {
        "id": "doc-recovery",
        "kb_id": kb["id"],
        "filename": "source.txt",
        "stored_path": str(source),
        "size": source.stat().st_size,
        "chunk_count": 1,
        "created_at": 1.0,
    }
    service._write_metadata(metadata)
    job = service.create_pipeline_job(
        kb["id"],
        draft_version=1,
        source_document_ids=["doc-recovery"],
    )
    claimed = service.claim_next_pipeline_job()
    assert claimed is not None and claimed["status"] == "running"
    assert service.recover_pipeline_jobs() == 1
    recovered = service.get_pipeline_job(job["job_id"])
    assert recovered["status"] == "queued"
    assert service.metadata_path.exists()
    assert not service.metadata_path.with_suffix(".json.tmp").exists()
