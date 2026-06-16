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


async def create_kb(client: httpx.AsyncClient, name: str = "测试知识库") -> str:
    response = await client.post("/api/rag/knowledge_bases", json={"name": name})
    assert response.status_code == 200, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_upload_query_and_cleanup(client: httpx.AsyncClient) -> None:
    kb_id = await create_kb(client)

    upload_response = await client.post(
        f"/api/rag/knowledge_bases/{kb_id}/documents",
        files={
            "file": (
                "测试文档.txt",
                "模镜是一个AI平台。它支持多种模型，包括 OpenAI 和 Anthropic。",
                "text/plain",
            )
        },
    )
    assert upload_response.status_code == 200, upload_response.text
    document = upload_response.json()
    assert document["chunk_count"] >= 1

    query_response = await client.post(
        "/api/rag/query",
        json={"kb_id": kb_id, "question": "什么是模镜？"},
    )
    assert query_response.status_code == 200, query_response.text
    data = query_response.json()
    assert "AI平台" in data["answer"]
    assert data["sources"]
    assert data["sources"][0]["document_name"] == "测试文档.txt"

    delete_doc_response = await client.delete(f"/api/rag/documents/{document['id']}")
    assert delete_doc_response.status_code == 200

    list_docs_response = await client.get(f"/api/rag/knowledge_bases/{kb_id}/documents")
    assert list_docs_response.status_code == 200
    assert list_docs_response.json()["documents"] == []

    delete_kb_response = await client.delete(f"/api/rag/knowledge_bases/{kb_id}")
    assert delete_kb_response.status_code == 200


@pytest.mark.asyncio
async def test_query_after_delete_returns_404(client: httpx.AsyncClient) -> None:
    kb_id = await create_kb(client, "待删除知识库")
    delete_response = await client.delete(f"/api/rag/knowledge_bases/{kb_id}")
    assert delete_response.status_code == 200

    query_response = await client.post(
        "/api/rag/query",
        json={"kb_id": kb_id, "question": "还有内容吗？"},
    )
    assert query_response.status_code == 404


@pytest.mark.asyncio
async def test_unsupported_file_type_returns_400(client: httpx.AsyncClient) -> None:
    kb_id = await create_kb(client, "格式测试")
    response = await client.post(
        f"/api/rag/knowledge_bases/{kb_id}/documents",
        files={"file": ("bad.exe", b"not a document", "application/octet-stream")},
    )
    assert response.status_code == 400
    assert "暂不支持" in response.text


@pytest.mark.asyncio
async def test_empty_knowledge_base_query_returns_hint(client: httpx.AsyncClient) -> None:
    kb_id = await create_kb(client, "空知识库")
    response = await client.post(
        "/api/rag/query",
        json={"kb_id": kb_id, "question": "这里有什么？"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sources"] == []
    assert "没有" in data["answer"]

