from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from server.main import app
from server.rag.api import set_rag_service_for_tests
from server.rag.embedder import EmbeddingClient
from server.rag.rag_service import RagService
from server.rag.vector_store import LocalJsonVectorStore


@pytest_asyncio.fixture
async def client(tmp_path: Path):
    service = RagService(
        storage_dir=tmp_path / "storage",
        uploads_dir=tmp_path / "uploads",
        embedder=EmbeddingClient(api_key="", dimension=128),
        vector_store=LocalJsonVectorStore(tmp_path / "storage" / "vectors.json"),
        llm_enabled=False,
    )
    set_rag_service_for_tests(service)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as async_client:
        yield async_client
    set_rag_service_for_tests(None)


async def create_kb(client: httpx.AsyncClient, name: str = "pipeline") -> str:
    response = await client.post("/api/rag/knowledge_bases", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


async def upload_pipeline_document(client: httpx.AsyncClient, kb_id: str) -> dict:
    response = await client.post(
        f"/api/rag/knowledge_bases/{kb_id}/documents",
        files={
            "file": (
                "pipeline.txt",
                b"ModelMirror Knowledge Pipeline maps uploaded files into artifacts, chunks, and citations.",
                "text/plain",
            )
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
async def test_rag_pipeline_assets_artifacts_and_chunks(client: httpx.AsyncClient) -> None:
    kb_id = await create_kb(client, "pipeline metadata")
    document = await upload_pipeline_document(client, kb_id)

    assets_response = await client.get(f"/api/rag/pipeline/assets?kb_id={kb_id}")
    assert assets_response.status_code == 200, assets_response.text
    assets_data = assets_response.json()
    assert assets_data["asset_count"] == 1
    asset = assets_data["assets"][0]
    assert asset["document_id"] == document["id"]
    assert asset["knowledge_base_id"] == kb_id
    assert asset["filename"] == "pipeline.txt"
    assert asset["extension"] == ".txt"
    assert "stored_path" not in asset

    artifacts_response = await client.get(f"/api/rag/pipeline/artifacts?kb_id={kb_id}")
    assert artifacts_response.status_code == 200, artifacts_response.text
    artifacts_data = artifacts_response.json()
    assert artifacts_data["artifact_count"] == 1
    artifact = artifacts_data["artifacts"][0]
    assert artifact["artifact_id"] == f"artifact_{document['id']}"
    assert artifact["file_asset_id"] == asset["file_asset_id"]
    assert artifact["chunk_count"] == document["chunk_count"]

    chunks_response = await client.get(
        f"/api/rag/pipeline/artifacts/{artifact['artifact_id']}/chunks"
    )
    assert chunks_response.status_code == 200, chunks_response.text
    chunks_data = chunks_response.json()
    assert chunks_data["chunk_count"] == document["chunk_count"]
    assert chunks_data["chunks"][0]["artifact_id"] == artifact["artifact_id"]
    assert chunks_data["chunks"][0]["text_length"] > 0
    assert "Knowledge Pipeline" in chunks_data["chunks"][0]["text_preview"]


@pytest.mark.asyncio
async def test_rag_pipeline_citations(client: httpx.AsyncClient) -> None:
    kb_id = await create_kb(client, "pipeline citations")
    document = await upload_pipeline_document(client, kb_id)

    response = await client.post(
        "/api/rag/pipeline/citations",
        json={
            "kb_id": kb_id,
            "question": "What does the Knowledge Pipeline map?",
            "top_k": 2,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["kb_id"] == kb_id
    assert data["citation_count"] >= 1
    citation = data["citations"][0]
    assert citation["document_id"] == document["id"]
    assert citation["document_name"] == "pipeline.txt"
    assert citation["chunk_id"].startswith(document["id"])
    assert "artifacts" in citation["snippet"]
    assert isinstance(citation["score"], float)


@pytest.mark.asyncio
async def test_rag_pipeline_missing_resources_return_404(client: httpx.AsyncClient) -> None:
    assets_response = await client.get("/api/rag/pipeline/assets?kb_id=missing")
    assert assets_response.status_code == 404

    artifacts_response = await client.get("/api/rag/pipeline/artifacts?kb_id=missing")
    assert artifacts_response.status_code == 404

    chunks_response = await client.get("/api/rag/pipeline/artifacts/artifact_missing/chunks")
    assert chunks_response.status_code == 404
