# 本地 RAG 知识库集成指南

本文件说明模镜本地 RAG 模块的架构、API、扩展方式和测试方法。该模块位于 `server/rag/`，前端入口为 `/rag`，聊天页可选择知识库进行检索增强问答。

最后更新日期：2026-07-09

## 2026-07-09 增量：Knowledge Pipeline Stage 草稿

本地 RAG 的 Knowledge Pipeline 只读视图已从单纯的 FileAsset / Artifact / Chunk / CitationAnchor 摘要，扩展为 Xpert 式四段 stage 草稿。新增 API：

```bash
curl "http://localhost:8000/api/rag/pipeline/draft?kb_id=kb_xxx"
```

响应只包含摘要元信息：

```json
{
  "kb_id": "kb_xxx",
  "stage_count": 4,
  "stages": [
    {
      "id": "stage_data_source",
      "kind": "data_source",
      "title": "数据源",
      "status": "ready",
      "item_count": 1,
      "summary": "上传文件已映射为 FileAsset 元数据。",
      "metadata": { "asset_count": 1, "document_count": 1 }
    }
  ]
}
```

四个 stage 固定为 `data_source`、`processor`、`chunker`、`image_understanding`。前三者实时从现有 RAG metadata 派生；`image_understanding` 当前为 `planned` / disabled 占位，不调用视觉模型。该 API 不返回本地文件绝对路径、完整 chunk 文本、embedding、prompt 或密钥，也不会改变上传、切分、向量化、检索和 `/api/rag/query` 行为。

## 2026-07-08 增量：Workflow CitationAnchor 节点

Classic workflow 已新增 `knowledge_citation` 节点，复用本地 RAG Knowledge Pipeline 的 citation 生成能力。节点读取 `queryVariable` 中的文本，使用可选 `knowledgeBaseId` 和 `top_k` 调用 `RagService.create_pipeline_citations(...)`，并把结果写入 `outputVariable`：

```json
{"citations":[...],"citation_count":1}
```

该节点只输出 CitationAnchor 摘要，包括 `chunk_id`、`document_name`、`score`、`snippet` 等字段；不会返回本地文件绝对路径、embedding、完整上传文件内容或密钥。它不改变上传、切分、检索、向量存储、`/api/rag/query` 或聊天 RAG 行为，只是让 workflow 和后续 Agent 能引用同一套只读知识元数据视图。
维护人：模镜团队

## 1. 概述

本地 RAG 模块提供一个最小可用的知识库能力：

- 创建和删除知识库。
- 上传 TXT、Markdown、PDF 文档。
- 自动解析、分段、向量化并写入索引。
- 基于知识库检索片段并生成回答。
- 在面试间选择知识库，让回答附带引用来源。

组件关系如下：

```text
用户浏览器
  |
  | /rag 管理资料库
  v
React RagPage
  |
  | /api/rag/*
  v
FastAPI RAG Router
  |
  +--> RagService
        |
        +--> document_parser.py  解析 TXT / Markdown / PDF
        +--> splitter.py         LangChain RecursiveCharacterTextSplitter，缺失时本地 fallback
        +--> embedder.py         OpenAI-compatible Embedding API，缺失 key 时 hash fallback
        +--> vector_store.py     ChromaDB 持久化，缺失依赖时 LocalJsonVectorStore fallback
        +--> OpenRouter Chat     生成 RAG 回答，缺失 key 时抽取式 fallback
```

默认目录：

```text
server/rag/uploads/       # 原始上传文件
server/rag/storage/       # metadata.json、本地 fallback 索引
server/rag/storage/chroma_db 或 CHROMA_DB_PATH # ChromaDB 持久化目录
```

## 2. 如何添加新的文件格式支持

文件解析入口是 `server/rag/document_parser.py`。

添加新格式的步骤：

1. 在 `SUPPORTED_EXTENSIONS` 中加入扩展名，例如 `.csv`。
2. 在 `parse_document()` 中增加分支：

```python
if extension == ".csv":
    return _read_csv(path)
```

3. 实现解析函数，将文件内容转换为纯文本：

```python
def _read_csv(path: Path) -> str:
    rows = path.read_text(encoding="utf-8").splitlines()
    text = "\n".join(rows)
    return _ensure_text(text, path.name)
```

4. 为新格式补充测试：上传对应文件，确认返回 `chunk_count > 0`，并能通过 `/api/rag/query` 检索到内容。

注意：解析函数只负责“转纯文本”，不要在 parser 层做向量化或模型调用。

## 3. 后端 API 文档

所有端点前缀均为 `/api/rag`。

### 创建知识库

```bash
curl -X POST http://localhost:8000/api/rag/knowledge_bases \
  -H "Content-Type: application/json" \
  -d '{"name":"产品手册"}'
```

响应：

```json
{
  "id": "kb_xxx",
  "name": "产品手册",
  "document_count": 0,
  "created_at": 1781600000.0,
  "updated_at": 1781600000.0
}
```

### 列出知识库

```bash
curl http://localhost:8000/api/rag/knowledge_bases
```

响应：

```json
{
  "knowledge_bases": [
    {
      "id": "kb_xxx",
      "name": "产品手册",
      "document_count": 2,
      "created_at": 1781600000.0,
      "updated_at": 1781600100.0
    }
  ]
}
```

### 删除知识库

```bash
curl -X DELETE http://localhost:8000/api/rag/knowledge_bases/kb_xxx
```

响应：

```json
{ "ok": true }
```

### 上传文档

支持 `.txt`、`.md`、`.markdown`、`.pdf`，单文件上限 10MB。

```bash
curl -X POST http://localhost:8000/api/rag/knowledge_bases/kb_xxx/documents \
  -F "file=@测试文档.txt"
```

响应：

```json
{
  "id": "doc_xxx",
  "kb_id": "kb_xxx",
  "filename": "测试文档.txt",
  "size": 128,
  "chunk_count": 1,
  "created_at": 1781600000.0
}
```

### 列出文档

```bash
curl http://localhost:8000/api/rag/knowledge_bases/kb_xxx/documents
```

响应：

```json
{
  "documents": [
    {
      "id": "doc_xxx",
      "kb_id": "kb_xxx",
      "filename": "测试文档.txt",
      "size": 128,
      "chunk_count": 1,
      "created_at": 1781600000.0
    }
  ]
}
```

### 删除文档

```bash
curl -X DELETE http://localhost:8000/api/rag/documents/doc_xxx
```

响应：

```json
{ "ok": true }
```

### 查询知识库

```bash
curl -X POST http://localhost:8000/api/rag/query \
  -H "Content-Type: application/json" \
  -d '{"kb_id":"kb_xxx","question":"什么是模镜？","top_k":4}'
```

响应：

```json
{
  "answer": "根据知识库资料：模镜是一个 AI 平台。",
  "sources": [
    {
      "chunk_id": "doc_xxx_chunk_0",
      "doc_id": "doc_xxx",
      "document_name": "测试文档.txt",
      "text": "模镜是一个 AI 平台。它支持多种模型。",
      "score": 0.83
    }
  ]
}
```

常见错误：

- `400`：文件格式不支持、文档无法解析、问题为空。
- `404`：知识库或文档不存在。
- `413`：上传文件超过 10MB。

## 4. 向量数据库配置与维护

默认优先使用 ChromaDB：

```bash
pip install chromadb langchain-text-splitters pdfplumber PyPDF2 python-multipart
```

相关环境变量：

```bash
RAG_VECTOR_STORE=chroma
CHROMA_DB_PATH=./chroma_db
RAG_STORAGE_DIR=server/rag/storage
RAG_UPLOAD_DIR=server/rag/uploads
RAG_CHUNK_SIZE=500
RAG_CHUNK_OVERLAP=50
```

Embedding 配置：

```bash
EMBEDDING_API_BASE=https://api.openai.com/v1
EMBEDDING_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
```

如果没有 `EMBEDDING_API_KEY`，系统会自动使用确定性 hash embedding，便于本地开发和 CI 测试。生产环境建议配置真实 Embedding API。

RAG 回答生成使用 OpenRouter：

```bash
OPENROUTER_API_KEY=sk-or-...
RAG_LLM_MODEL=deepseek/deepseek-chat
```

如果没有 `OPENROUTER_API_KEY`，查询接口会返回抽取式答案，即直接基于最相关片段组织回答。

备份建议：

- 备份 `server/rag/storage/metadata.json`。
- 备份 `CHROMA_DB_PATH` 指向的 ChromaDB 目录。
- 备份 `server/rag/uploads/` 原始文件。

## 5. 测试指南

后端语法检查：

```bash
python -m py_compile server/rag/*.py
```

RAG 集成测试：

```bash
python -m pytest server/tests/test_rag_integration.py -q
python -m pytest server/tests/test_rag.py -q
```

测试特点：

- 使用临时目录保存 metadata、uploads 和本地向量索引。
- 使用 hash embedding，不依赖外部网络。
- 禁用 LLM 生成，返回抽取式答案，确保 CI 可重复。

新增测试建议：

1. 构造一个临时知识库。
2. 上传最小可解析文件。
3. 查询一个能命中文档关键词的问题。
4. 验证 `answer` 和 `sources`。
5. 清理文档和知识库。


## 2026-07-08 增量：知识流水线 Beta

本地 RAG 现在额外提供一层只读 Knowledge Pipeline 元数据视图，用于对齐 Xpert 的知识产物模型。该层不会改变上传、切分、embedding、向量存储、检索测试或 `/api/rag/query` 响应协议。

新增模型映射：

- `FileAsset`：由已上传 document 派生，包含文件名、大小、扩展名、mime、知识库 ID 与 document ID，不返回 `stored_path`。
- `Artifact`：由 document 派生，表示可被检索和引用的文档产物，包含 `file_asset_id`、标题和 `chunk_count`。
- `KnowledgeChunk`：由向量索引中的 chunk 派生，只返回 chunk ID、序号、文本摘要和字符长度，不返回 embedding。
- `CitationAnchor`：由现有检索结果派生，包含 chunk ID、document 名称、score 和 snippet。

新增只读 API：

```bash
curl 'http://localhost:8000/api/rag/pipeline/assets?kb_id=kb_xxx'
curl 'http://localhost:8000/api/rag/pipeline/artifacts?kb_id=kb_xxx'
curl 'http://localhost:8000/api/rag/pipeline/artifacts/artifact_doc_xxx/chunks'
curl -X POST http://localhost:8000/api/rag/pipeline/citations \
  -H 'Content-Type: application/json' \
  -d '{"kb_id":"kb_xxx","question":"如何使用资料？","top_k":4}'
```

前端 `/rag` 的“知识流水线 Beta”折叠区已展示当前知识库的数据源、处理器、分块器、图像理解 stage 草稿，并保留 assets / artifacts / chunks 计数和最近 artifacts。后续知识类工作流节点、Agent 引用和 citation 面板会基于这层 schema 继续扩展。

最后更新日期：2026-07-09

## 2026-07-10 Update: Knowledge Pipeline Draft Config And Preflight

The local RAG pipeline now exposes a safe editable draft layer:

- `GET /api/rag/pipeline/draft?kb_id=...` returns `draft_id`, `version`, `updated_at`, `editable`, stages, counts, and safe stage config.
- `PATCH /api/rag/pipeline/draft/{kb_id}` persists safe draft fields only: uploaded file source mode, local parser, local recursive character chunking, `chunk_size`, and `chunk_overlap`.
- `POST /api/rag/pipeline/draft/{kb_id}/preflight` returns readiness, warnings, per-stage checks, and document/artifact/chunk counts.

Validation boundaries: `chunk_size` must stay between 100 and 4000, `chunk_overlap` must be non-negative and smaller than `chunk_size`, and image understanding cannot be enabled yet. The draft layer does not change upload, parsing, splitting, embedding, vector storage, retrieval, chat RAG, or workflow `knowledge_citation` behavior. Responses must not expose local stored paths, full chunk text, embeddings, prompts, tools outputs, or secrets.

Last updated: 2026-07-10
