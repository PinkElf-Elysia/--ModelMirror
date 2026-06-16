# 本地 RAG 知识库集成指南

本文件说明模镜本地 RAG 模块的架构、API、扩展方式和测试方法。该模块位于 `server/rag/`，前端入口为 `/rag`，聊天页可选择知识库进行检索增强问答。

最后更新日期：2026-06-16  
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

