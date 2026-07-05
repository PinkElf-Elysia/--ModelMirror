import asyncio
import ast
import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from collections.abc import AsyncIterator
from collections import defaultdict, deque
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

try:
    from server.api.dify_proxy import router as dify_router
except ModuleNotFoundError:
    from api.dify_proxy import router as dify_router

try:
    from server.rag.api import router as rag_router
except ModuleNotFoundError:
    from rag.api import router as rag_router

try:
    from server.skills.api import router as skills_router
except ModuleNotFoundError:
    from skills.api import router as skills_router

try:
    from server.api.workflow_native import router as workflow_native_router
except ModuleNotFoundError:
    from api.workflow_native import router as workflow_native_router

try:
    from server.meta_agent import (
        MetaAgentGenerateRequest,
        MetaAgentGenerateResponse,
        build_meta_agent_prompt,
        build_workflow_from_plan,
        parse_meta_agent_plan,
    )
    from server.meta_agent.prompts import META_AGENT_SYSTEM_PROMPT
    from server.workflow_native.schemas import NativeWorkflowDefinition
    from server.workflow_native.validate import validate_workflow_graph
except ModuleNotFoundError:
    from meta_agent import (
        MetaAgentGenerateRequest,
        MetaAgentGenerateResponse,
        build_meta_agent_prompt,
        build_workflow_from_plan,
        parse_meta_agent_plan,
    )
    from meta_agent.prompts import META_AGENT_SYSTEM_PROMPT
    from workflow_native.schemas import NativeWorkflowDefinition
    from workflow_native.validate import validate_workflow_graph

try:
    from server.rag.document_parser import parse_document
    from server.rag.rag_service import RagService
except ModuleNotFoundError:
    from rag.document_parser import parse_document
    from rag.rag_service import RagService

try:
    from server.mcp.manager import (
        MCPClientError,
        MCPClientManager,
        MCPInstallError,
        MCPInstaller,
        MCPSessionNotFoundError,
        validate_server_command,
    )
    from server.registry.tool_registry import ToolRegistry
except ModuleNotFoundError:
    from mcp.manager import (
        MCPClientError,
        MCPClientManager,
        MCPInstallError,
        MCPInstaller,
        MCPSessionNotFoundError,
        validate_server_command,
    )
    from registry.tool_registry import ToolRegistry

try:
    from server.xpert_runtime import (
        AgentTaskStore,
        CapabilityRegistry,
        InMemoryToolAuditStore,
        MCPToolsetProvider,
        MiddlewareContext,
        MiddlewarePipeline,
        ModelCallRequest,
        ModelCallResponse,
        RunRegistry,
        RuntimeEventStore,
        RuntimeToolCall,
        ToolPermissionPolicy,
        create_default_runtime,
        event_recorder,
        run_tool_with_runtime,
        runtime_middleware_registry,
    )
except ModuleNotFoundError:
    from xpert_runtime import (
        AgentTaskStore,
        CapabilityRegistry,
        InMemoryToolAuditStore,
        MCPToolsetProvider,
        MiddlewareContext,
        MiddlewarePipeline,
        ModelCallRequest,
        ModelCallResponse,
        RunRegistry,
        RuntimeEventStore,
        RuntimeToolCall,
        ToolPermissionPolicy,
        create_default_runtime,
        event_recorder,
        run_tool_with_runtime,
        runtime_middleware_registry,
    )

load_dotenv()

LLM_GATEWAY_URL = os.getenv(
    "LLM_GATEWAY_URL",
    "http://localhost:3000/v1/chat/completions",
).strip()
LLM_GATEWAY_KEY = os.getenv("LLM_GATEWAY_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
API_KEY = OPENROUTER_API_KEY
CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_GATEWAY_NOT_CONFIGURED_MESSAGE = (
    "LLM 网关未配置，请设置环境变量 LLM_GATEWAY_KEY 或 OPENROUTER_API_KEY。"
)
APP_REFERER = os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost:5173").strip()
APP_TITLE = os.getenv("OPENROUTER_APP_TITLE", "ModelMirror").strip()
FUSION_MODEL_ID = "openrouter/fusion"
DEFAULT_JUDGE_MODEL_ID = os.getenv("OPENROUTER_JUDGE_MODEL", "openai/gpt-4o").strip()
TEXT_FALLBACK_MODEL = os.getenv(
    "OPENROUTER_TEXT_FALLBACK_MODEL", "deepseek/deepseek-chat"
).strip()
VISION_FALLBACK_MODEL = os.getenv(
    "OPENROUTER_VISION_FALLBACK_MODEL", "qwen/qwen2.5-vl-72b-instruct"
).strip()
REQUESTS_PER_MINUTE = 20
WORKFLOW_ALLOW_HTTP_OUTBOUND = False
WORKFLOW_MAX_ITERATION_ITEMS = 50
WORKFLOW_DOC_EXTRACTOR_ROOT = "server/rag"
WORKFLOW_TASK_TTL_SECONDS = 1800
WORKFLOW_HUMAN_INTERVENTION_ENABLED = True
WORKFLOW_QUESTION_CLASSIFIER_ENABLED = True
WORKFLOW_MCP_TOOL_ENABLED = True
WORKFLOW_TIME_TOOL_ENABLED = True
WORKFLOW_PYTHON_TIMEOUT_SECONDS = 3
WORKFLOW_PYTHON_SANDBOX_ROOT = Path(__file__).resolve().parent / "workflow_sandboxes"
WORKFLOW_AGENT_ENABLED = True
WORKFLOW_AGENT_MAX_ITERATIONS_DEFAULT = 5
WORKFLOW_AGENT_MAX_TOKENS = 1024
MAX_IMAGE_DATA_URL_BYTES = 5 * 1024 * 1024
AGENTS_DATA_PATH = Path(__file__).parent / "data" / "agents.json"
MAX_AGENT_PROMPT_CHARS = 6000
IMAGE_CAPABLE_MODEL_HINTS = (
    "gpt-4o",
    "gpt-4.1",
    "gpt-5",
    "o3",
    "o4",
    "claude-3",
    "claude-sonnet-4",
    "claude-opus-4",
    "gemini",
    "gemma-3",
    "llama-4",
    "pixtral",
    "qwen-vl",
    "qwen2.5-vl",
    "qwen3-vl",
    "phi-4-multimodal",
    "grok-vision",
    "mistral-medium-3",
    "minimax",
)

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("modelmirror.chat")
BLOCKED_KEYWORDS = (
    "儿童色情",
    "制作炸弹",
    "自杀方法",
    "盗取密码",
    "malware",
    "child sexual",
    "make a bomb",
    "steal password",
)

app = FastAPI(title="ModelMirror Chat Proxy")

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(dify_router)
app.include_router(rag_router)
app.include_router(skills_router)
app.include_router(workflow_native_router)

request_windows: dict[str, deque[float]] = defaultdict(deque)
mcp_connect_windows: dict[str, deque[float]] = defaultdict(deque)
mcp_manager = MCPClientManager()
mcp_installer = MCPInstaller()
tool_registry = ToolRegistry()
workflow_mcp_provider = MCPToolsetProvider(tool_registry, mcp_manager)
runtime_capabilities = CapabilityRegistry()
workflow_mcp_pipeline = MiddlewarePipeline([event_recorder])
workflow_tool_policy = ToolPermissionPolicy(allow_by_default=True)
workflow_tool_audit_store = InMemoryToolAuditStore()
runtime_event_store = RuntimeEventStore()
agent_task_store = AgentTaskStore(event_store=runtime_event_store)
run_registry = RunRegistry()
runtime_capabilities.register(
    "mcp_tools",
    workflow_mcp_provider,
    description="MCP tools runtime capability for workflow and agents.",
)
workflow_task_store: dict[str, dict[str, Any]] = {}


class TextContentPart(BaseModel):
    type: Literal["text"]
    text: str = Field(default="", max_length=20_000)


class ImageUrlPayload(BaseModel):
    url: str = Field(min_length=1, max_length=MAX_IMAGE_DATA_URL_BYTES + 256)


class ImageContentPart(BaseModel):
    type: Literal["image_url"]
    image_url: ImageUrlPayload


ChatContent = str | list[TextContentPart | ImageContentPart]


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: ChatContent


class ChatRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=256)
    messages: list[ChatMessage] = Field(min_length=1, max_length=80)
    temperature: float = Field(default=0.7, ge=0, le=2)
    top_p: float | None = Field(default=None, ge=0, le=1)
    max_tokens: int = Field(default=2048, ge=1, le=128000)
    seed: int | None = None
    stop: list[str] | None = Field(default=None, max_length=8)


class AgentRecord(BaseModel):
    id: str
    name: str
    department: str
    expertise: str
    scenarios: str
    source: str | None = None
    sourcePath: str | None = None
    sourceUrl: str | None = None
    emoji: str | None = None
    prompt: str
    popularity: int | None = None


class FusionChatRequest(BaseModel):
    model_ids: list[str] = Field(min_length=2, max_length=5)
    messages: list[ChatMessage] = Field(min_length=1, max_length=40)
    judge_model_id: str = Field(default=DEFAULT_JUDGE_MODEL_ID, min_length=1, max_length=256)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=128000)
    use_native_fusion: bool = True


class RouteAgentRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    model_id: str = Field(default=TEXT_FALLBACK_MODEL, min_length=1, max_length=256)
    top_k: int = Field(default=3, ge=1, le=5)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=2048, ge=1, le=128000)


class TeamMemberPayload(BaseModel):
    agent_id: str = Field(min_length=1, max_length=160)
    task: str | None = Field(default=None, max_length=1200)


class TeamChatRequest(BaseModel):
    members: list[TeamMemberPayload] = Field(min_length=1, max_length=6)
    message: str = Field(min_length=1, max_length=20_000)
    model_id: str = Field(default=TEXT_FALLBACK_MODEL, min_length=1, max_length=256)
    mode: Literal["serial", "debate"] = "serial"
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=1800, ge=1, le=128000)


class MCPConnectRequest(BaseModel):
    server_command: list[str] = Field(min_length=1, max_length=32)


class MCPConnectResponse(BaseModel):
    session_id: str
    tools_count: int


class MCPInstallRequest(BaseModel):
    project_id: str = Field(min_length=1, max_length=96)
    install_command: str = Field(min_length=1, max_length=20_000)
    server_command: list[str] | None = Field(default=None, max_length=32)


class MCPInstallResponse(BaseModel):
    project_id: str
    installed: bool
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MCPInstalledResponse(BaseModel):
    installed: list[dict[str, Any]] = Field(default_factory=list)


class MCPSessionSummary(BaseModel):
    session_id: str
    server_command: list[str]
    status: str
    created_at: float
    uptime_seconds: float
    idle_seconds: float
    tools_count: int


class MCPSessionsResponse(BaseModel):
    sessions: list[MCPSessionSummary]


class MCPToolPayload(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class MCPToolsResponse(BaseModel):
    tools: list[MCPToolPayload]


class RegistryToolPayload(BaseModel):
    name: str
    description: str | None = None
    input_schema: dict[str, Any] = Field(default_factory=dict)
    server_id: str
    session_id: str
    registered_at: float


class RegistryToolsResponse(BaseModel):
    tools: list[RegistryToolPayload]


class MCPCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPCallResponse(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    is_error: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


WorkflowNodeType = Literal[
    "input",
    "llm",
    "condition",
    "code",
    "variable_assign",
    "template_transform",
    "variable_aggregator",
    "parameter_extractor",
    "knowledge_retrieval",
    "document_extractor",
    "human_intervention",
    "question_classifier",
    "agent",
    "agent_task",
    "agent_handoff",
    "mcp_tool",
    "time_tool",
    "http_request",
    "list_operation",
    "iteration",
    "runtime_middleware",
    "output",
]


class WorkflowPosition(BaseModel):
    x: float = 0
    y: float = 0


class WorkflowNodePayload(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    type: WorkflowNodeType | None = None
    position: WorkflowPosition | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdgePayload(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    sourceHandle: str | None = None
    targetHandle: str | None = None


class WorkflowPayload(BaseModel):
    id: str = Field(default="draft", max_length=128)
    title: str = Field(default="未命名工作流", max_length=120)
    nodes: list[WorkflowNodePayload] = Field(min_length=1, max_length=80)
    edges: list[WorkflowEdgePayload] = Field(default_factory=list, max_length=120)


class WorkflowRunRequest(BaseModel):
    workflow: WorkflowPayload
    inputs: dict[str, str] = Field(default_factory=dict)


class WorkflowResumeRequest(BaseModel):
    input_text: str = Field(default="", max_length=20_000)
    node_id: str | None = Field(default=None, max_length=128)


class WorkflowTaskStatusResponse(BaseModel):
    task_id: str
    paused: bool
    paused_node_id: str | None = None
    created_at: float
    ttl_seconds_left: float


def client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def rate_limit_or_raise(ip: str) -> None:
    now = time.monotonic()
    window = request_windows[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= REQUESTS_PER_MINUTE:
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试。")
    window.append(now)


def mcp_connect_rate_limit_or_raise(ip: str) -> None:
    now = time.monotonic()
    window = mcp_connect_windows[ip]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= 5:
        raise HTTPException(status_code=429, detail="MCP 连接过于频繁，请稍后再试。")
    window.append(now)


def serialize_mcp_tool(tool: Any) -> MCPToolPayload:
    data = tool.model_dump(by_alias=True, mode="json")
    return MCPToolPayload(
        name=data.get("name", ""),
        title=data.get("title"),
        description=data.get("description"),
        inputSchema=data.get("inputSchema") or {},
    )


def serialize_mcp_call_result(result: Any) -> MCPCallResponse:
    data = result.model_dump(by_alias=True, mode="json")
    content = data.get("content")
    return MCPCallResponse(
        content=content if isinstance(content, list) else [],
        is_error=bool(data.get("isError") or data.get("is_error")),
        raw=data if isinstance(data, dict) else {},
    )


def mcp_server_id_from_command(server_command: list[str]) -> str:
    if not server_command:
        return "unknown"
    if len(server_command) >= 3 and server_command[0].lower().startswith("npx"):
        return server_command[2]
    return " ".join(server_command[:3])


async def cleanup_mcp_idle_sessions_and_registry() -> list[str]:
    cleaned_ids = await mcp_manager.cleanup_idle_sessions()
    if cleaned_ids:
        await tool_registry.unregister_sessions(cleaned_ids)
    return cleaned_ids


def validate_content(messages: list[ChatMessage]) -> None:
    content = "\n".join(message_text(message.content) for message in messages).lower()
    if any(keyword.lower() in content for keyword in BLOCKED_KEYWORDS):
        raise HTTPException(
            status_code=400,
            detail="该内容可能存在安全风险，请换一种问法。",
        )


def message_text(content: ChatContent) -> str:
    if isinstance(content, str):
        return content

    return "\n".join(part.text for part in content if isinstance(part, TextContentPart))


def message_has_image(content: ChatContent) -> bool:
    return isinstance(content, list) and any(
        isinstance(part, ImageContentPart) for part in content
    )


def model_supports_image_input(model_id: str) -> bool:
    normalized = model_id.lower()
    return any(hint in normalized for hint in IMAGE_CAPABLE_MODEL_HINTS)


def validate_image_url(url: str) -> None:
    lowered = url.lower()
    if not (
        lowered.startswith("data:image/jpeg;base64,")
        or lowered.startswith("data:image/png;base64,")
        or lowered.startswith("data:image/gif;base64,")
        or lowered.startswith("data:image/webp;base64,")
    ):
        raise HTTPException(
            status_code=400,
            detail="图片格式不受支持，请上传 PNG、JPG、GIF 或 WebP 图片。",
        )

    if len(url.encode("utf-8")) > MAX_IMAGE_DATA_URL_BYTES:
        raise HTTPException(
            status_code=413,
            detail="图片过大，请压缩到 5MB 以内后再发送。",
        )


def validate_multimodal_content(model_id: str, messages: list[ChatMessage]) -> None:
    has_image = False

    for message in messages:
        if isinstance(message.content, str):
            if not message.content.strip():
                raise HTTPException(status_code=400, detail="消息内容不能为空。")
            continue

        if len(message.content) == 0:
            raise HTTPException(status_code=400, detail="消息内容不能为空。")

        for part in message.content:
            if isinstance(part, TextContentPart):
                continue

            has_image = True
            validate_image_url(part.image_url.url)

    if has_image and not model_supports_image_input(model_id):
        raise HTTPException(
            status_code=400,
            detail="当前模型不支持图片输入，请切换支持多模态的模型。",
        )


def upstream_error_message(status_code: int, body: bytes) -> str:
    fallback = {
        400: "请求格式有误，请检查消息内容。",
        401: "服务认证失败，请检查后端密钥配置。",
        402: "当前服务额度不足或计费不可用。",
        404: "未找到该模型，请返回列表重新选择。",
        408: "模型响应超时，请稍后重试。",
        429: "请求过于频繁，请稍后再试。",
    }.get(status_code, "模型服务暂时不可用，请稍后重试。")

    try:
        data = httpx.Response(status_code=status_code, content=body).json()
    except ValueError:
        return fallback

    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            lowered = message.lower()
            if "user not found" in lowered:
                return (
                    "本地 newAPI 未找到对应用户或令牌无效。请在 newAPI 中配置用户/令牌，"
                    "或设置 OPENROUTER_API_KEY 使用 OpenRouter 兜底。"
                )
            if "not available in your region" in lowered:
                return "当前模型在本地区暂不可用，请返回列表选择其他模型。"
            if "invalid api key" in lowered or "no auth credentials" in lowered:
                return (
                    "模型服务认证失败。请检查本地 newAPI 用户/渠道配置，"
                    "或设置 OPENROUTER_API_KEY 使用 OpenRouter 兜底。"
                )
            return message
    return fallback


def parse_upstream_error(status_code: int, body: bytes) -> tuple[str, dict[str, Any] | None]:
    message = upstream_error_message(status_code, body)
    try:
        data = httpx.Response(status_code=status_code, content=body).json()
    except ValueError:
        return message, None

    return message, data if isinstance(data, dict) else None


def is_region_or_model_unavailable(
    status_code: int,
    message: str,
    data: dict[str, Any] | None,
) -> bool:
    lowered = json.dumps(data or {}, ensure_ascii=False).lower()
    lowered += f" {message.lower()}"
    markers = (
        "not available in your region",
        "region",
        "country",
        "geo",
        "unavailable",
        "not available",
        "model is not available",
        "provider returned error",
        "temporarily unavailable",
    )
    return status_code in {403, 404, 429, 502, 503} and any(
        marker in lowered for marker in markers
    )


def is_local_gateway_url(url: str) -> bool:
    lowered = url.lower()
    return any(
        marker in lowered
        for marker in (
            "new-api",
            "localhost:3000",
            "127.0.0.1:3000",
            ":3000/v1/chat/completions",
        )
    )


def is_gateway_auth_or_user_error(
    status_code: int,
    message: str,
    data: dict[str, Any] | None,
) -> bool:
    lowered = json.dumps(data or {}, ensure_ascii=False).lower()
    lowered += f" {message.lower()}"
    markers = (
        "user not found",
        "invalid api key",
        "no auth credentials",
        "unauthorized",
        "invalid token",
        "令牌无效",
        "认证失败",
    )
    return status_code in {401, 403, 404} and any(
        marker in lowered for marker in markers
    )


def should_fallback_gateway_to_openrouter(
    status_code: int,
    message: str,
    data: dict[str, Any] | None,
    primary_url: str,
) -> bool:
    if not OPENROUTER_API_KEY:
        return False
    if primary_url.rstrip("/") == CHAT_COMPLETIONS_URL.rstrip("/"):
        return False
    if not is_local_gateway_url(primary_url):
        return False
    return is_gateway_auth_or_user_error(status_code, message, data)


def should_fallback_model(
    status_code: int,
    message: str,
    data: dict[str, Any] | None,
    model_id: str,
    messages: list[ChatMessage],
) -> bool:
    if model_id in {TEXT_FALLBACK_MODEL, VISION_FALLBACK_MODEL}:
        return False
    if not is_region_or_model_unavailable(status_code, message, data):
        return False
    if any(message_has_image(message.content) for message in messages):
        return bool(VISION_FALLBACK_MODEL)
    return bool(TEXT_FALLBACK_MODEL)


def fallback_model_for(messages: list[ChatMessage]) -> str:
    if any(message_has_image(message.content) for message in messages):
        return VISION_FALLBACK_MODEL
    return TEXT_FALLBACK_MODEL


def proxy_url() -> str | None:
    return (
        os.getenv("OPENROUTER_PROXY")
        or os.getenv("HTTPS_PROXY")
        or os.getenv("HTTP_PROXY")
        or os.getenv("ALL_PROXY")
        or None
    )


def get_llm_gateway_config() -> tuple[str, str]:
    """Return the active OpenAI-compatible gateway URL and API key."""

    if LLM_GATEWAY_URL and LLM_GATEWAY_KEY:
        return LLM_GATEWAY_URL, LLM_GATEWAY_KEY
    if API_KEY:
        return CHAT_COMPLETIONS_URL, API_KEY
    return "", ""


def llm_gateway_headers(key: str) -> dict[str, str]:
    """Build headers for newAPI or OpenRouter-compatible LLM gateways."""

    referer = APP_REFERER or "https://modelmirror.local"
    title = APP_TITLE or "ModelMirror"
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": referer,
        "X-Title": title,
        "X-OpenRouter-Title": title,
    }


def openrouter_headers() -> dict[str, str]:
    """Backward-compatible alias for legacy OpenRouter call sites."""

    _, key = get_llm_gateway_config()
    return llm_gateway_headers(key) if key else {}


def build_upstream_payload(
    payload: ChatRequest,
    model_id: str,
) -> dict[str, Any]:
    upstream_payload: dict[str, Any] = {
        "model": model_id,
        "messages": [message.model_dump(mode="json") for message in payload.messages],
        "temperature": payload.temperature,
        "max_tokens": payload.max_tokens,
        "stream": True,
    }
    if payload.top_p is not None:
        upstream_payload["top_p"] = payload.top_p
    if payload.seed is not None:
        upstream_payload["seed"] = payload.seed
    if payload.stop:
        upstream_payload["stop"] = payload.stop

    return upstream_payload


def load_agent_records() -> list[AgentRecord]:
    try:
        raw_agents = json.loads(AGENTS_DATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("Agent data file not found: %s", AGENTS_DATA_PATH)
        return []
    except json.JSONDecodeError:
        logger.exception("Agent data file is invalid JSON: %s", AGENTS_DATA_PATH)
        return []

    records: list[AgentRecord] = []
    for item in raw_agents:
        try:
            records.append(AgentRecord.model_validate(item))
        except Exception:
            logger.warning("Skipping invalid agent record: %s", item.get("id") if isinstance(item, dict) else "unknown")
    return records


AGENT_RECORDS = load_agent_records()
AGENTS_BY_ID = {agent.id: agent for agent in AGENT_RECORDS}


def chat_messages_json(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    return [message.model_dump(mode="json") for message in messages]


def build_chat_payload_from_messages(
    model_id: str,
    messages: list[ChatMessage],
    *,
    stream: bool,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    top_p: float | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model_id,
        "messages": chat_messages_json(messages),
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if top_p is not None:
        payload["top_p"] = top_p
    if extra:
        payload.update(extra)
    return payload


def llm_client_kwargs() -> dict[str, Any]:
    timeout = httpx.Timeout(connect=15, read=None, write=30, pool=10)
    client_kwargs: dict[str, Any] = {"timeout": timeout}
    proxy = proxy_url()
    if proxy:
        client_kwargs["proxy"] = proxy
    return client_kwargs


def openrouter_client_kwargs() -> dict[str, Any]:
    """Backward-compatible alias for legacy OpenRouter client settings."""

    return llm_client_kwargs()


def completion_text_from_payload(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        return ""
    message = first_choice.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            return content
    delta = first_choice.get("delta")
    if isinstance(delta, dict):
        content = delta.get("content")
        if isinstance(content, str):
            return content
    return ""


async def collect_chat_completion_text(
    model_id: str,
    messages: list[ChatMessage],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    url, key = get_llm_gateway_config()
    if not url:
        raise RuntimeError(LLM_GATEWAY_NOT_CONFIGURED_MESSAGE)
    request_payload = build_chat_payload_from_messages(
        model_id,
        messages,
        stream=False,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    async with httpx.AsyncClient(**llm_client_kwargs()) as client:
        response = await client.post(
            url,
            headers=llm_gateway_headers(key),
            json=request_payload,
        )
        if response.status_code >= 400:
            message, _ = parse_upstream_error(response.status_code, response.content)
            raise RuntimeError(message)
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("模型返回了无法解析的响应。")
        text = completion_text_from_payload(data)
        if not text.strip():
            raise RuntimeError("模型没有返回可用内容。")
        return text


async def stream_chat_text(
    model_id: str,
    messages: list[ChatMessage],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    extra: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    url, key = get_llm_gateway_config()
    if not url:
        raise RuntimeError(LLM_GATEWAY_NOT_CONFIGURED_MESSAGE)
    request_payload = build_chat_payload_from_messages(
        model_id,
        messages,
        stream=True,
        temperature=temperature,
        max_tokens=max_tokens,
        extra=extra,
    )

    async with httpx.AsyncClient(**llm_client_kwargs()) as client:
        response = await client.send(
            client.build_request(
                "POST",
                url,
                headers=llm_gateway_headers(key),
                json=request_payload,
            ),
            stream=True,
        )

        if response.status_code >= 400:
            body = await response.aread()
            await response.aclose()
            message, _ = parse_upstream_error(response.status_code, body)
            raise RuntimeError(message)

        buffer = ""
        try:
            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                buffer += chunk
                events = buffer.split("\n\n")
                buffer = events.pop() or ""
                for event in events:
                    for text_chunk in sse_delta_text(event):
                        if text_chunk:
                            yield text_chunk
        finally:
            await response.aclose()

        if buffer.strip():
            for text_chunk in sse_delta_text(buffer):
                if text_chunk:
                    yield text_chunk


async def stream_text_with_model_fallback(
    model_id: str,
    messages: list[ChatMessage],
    *,
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> AsyncIterator[str]:
    try:
        async for delta in stream_chat_text(
            model_id,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield delta
        return
    except Exception as exc:
        if model_id == TEXT_FALLBACK_MODEL:
            raise
        logger.warning(
            "Agent/team model failed, falling back model=%s fallback=%s error=%s",
            model_id,
            TEXT_FALLBACK_MODEL,
            exc,
        )
        yield f"提示：当前模型暂不可用，已自动切换为 {TEXT_FALLBACK_MODEL} 继续处理。\n\n"

    async for delta in stream_chat_text(
        TEXT_FALLBACK_MODEL,
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
    ):
        yield delta


def validate_plain_message(text: str) -> None:
    if not text.strip():
        raise HTTPException(status_code=400, detail="消息内容不能为空。")
    lowered = text.lower()
    if any(keyword.lower() in lowered for keyword in BLOCKED_KEYWORDS):
        raise HTTPException(
            status_code=400,
            detail="该内容可能存在安全风险，请换一种问法。",
        )


def trim_agent_prompt(agent: AgentRecord) -> str:
    prompt = agent.prompt.strip()
    if len(prompt) <= MAX_AGENT_PROMPT_CHARS:
        return prompt
    return (
        prompt[:MAX_AGENT_PROMPT_CHARS]
        + "\n\n[系统提示：该专家人设较长，已保留前部核心角色、规则和工作流。]"
    )


MATCH_STOPWORDS = {
    "need",
    "advice",
    "help",
    "give",
    "one",
    "short",
    "concise",
    "please",
    "with",
    "and",
    "for",
    "the",
    "your",
}


def tokenize_for_match(text: str) -> set[str]:
    lowered = text.lower()
    tokens = set(re.findall(r"[a-z0-9_+\-#.]{2,}|[\u4e00-\u9fff]{2,}", lowered))
    return {token for token in tokens if token.strip() and token not in MATCH_STOPWORDS}


DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "工程部": ("代码", "编程", "开发", "前端", "后端", "api", "数据库", "性能", "架构", "bug", "测试", "frontend", "backend", "performance", "react", "code"),
    "设计部": ("设计", "ui", "ux", "视觉", "交互", "原型", "品牌", "海报", "界面", "interface", "prototype", "visual"),
    "营销部": ("营销", "增长", "广告", "投放", "内容", "文案", "品牌", "获客", "社媒", "launch", "growth", "copy", "campaign"),
    "金融部": ("财务", "金融", "投资", "估值", "预算", "风控", "报表", "finance", "budget", "risk"),
    "项目管理部": ("项目", "排期", "计划", "需求", "路线图", "风险", "里程碑", "project", "roadmap", "milestone"),
    "销售部": ("销售", "客户", "线索", "crm", "商务", "谈判", "sales", "customer", "lead"),
    "测试部": ("测试", "qa", "验收", "用例", "质量", "回归", "quality", "test"),
    "游戏开发部": ("游戏", "关卡", "玩法", "unity", "虚幻", "策划", "game", "level"),
    "支持部": ("客服", "支持", "工单", "用户反馈", "帮助中心", "support", "ticket"),
}


def match_agents(query: str, limit: int = 3) -> list[tuple[AgentRecord, float]]:
    query_tokens = tokenize_for_match(query)
    normalized_query = query.lower()
    ranked: list[tuple[AgentRecord, float]] = []

    for agent in AGENT_RECORDS:
        profile_text = " ".join(
            [
                agent.id,
                agent.name,
                agent.department,
                agent.expertise,
                agent.scenarios,
                agent.sourcePath or "",
            ]
        ).lower()
        searchable = " ".join(
            [
                profile_text,
                trim_agent_prompt(agent)[:1200],
            ]
        ).lower()
        agent_tokens = tokenize_for_match(searchable)
        overlap = len(query_tokens & agent_tokens)
        substring_hits = sum(
            1 for token in query_tokens if len(token) >= 2 and token in searchable
        )
        profile_hits = sum(
            1 for token in query_tokens if len(token) >= 2 and token in profile_text
        )
        department_boost = 0
        for department, keywords in DOMAIN_KEYWORDS.items():
            if agent.department == department and any(keyword in normalized_query for keyword in keywords):
                department_boost += 4
        name_boost = 8 if agent.name.lower() in normalized_query else 0
        score = overlap + substring_hits + profile_hits * 8 + department_boost + name_boost
        if score > 0:
            ranked.append((agent, float(score)))

    if not ranked:
        ranked = [
            (agent, float(agent.popularity or 50) / 20)
            for agent in sorted(
                AGENT_RECORDS,
                key=lambda item: item.popularity or 0,
                reverse=True,
            )[:limit]
        ]

    return sorted(ranked, key=lambda item: item[1], reverse=True)[:limit]


def agent_public_payload(agent: AgentRecord, score: float | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": agent.id,
        "name": agent.name,
        "department": agent.department,
        "expertise": agent.expertise,
        "scenarios": agent.scenarios,
        "emoji": agent.emoji,
        "sourceUrl": agent.sourceUrl,
        "popularity": agent.popularity,
    }
    if score is not None:
        payload["score"] = round(score, 2)
    return payload


def agent_system_message(agent: AgentRecord, extra_instruction: str = "") -> ChatMessage:
    content = (
        f"{trim_agent_prompt(agent)}\n\n"
        "你现在正在模镜的“专家会诊室”中工作。请保持该专家的人设，"
        "用简体中文回答，先给出清晰结论，再给出可执行步骤。"
    )
    if extra_instruction.strip():
        content += f"\n\n本轮岗位任务：{extra_instruction.strip()}"
    return ChatMessage(role="system", content=content)


async def try_native_fusion_stream(payload: FusionChatRequest) -> AsyncIterator[str]:
    # OpenRouter documents Fusion Router as a Beta model alias/plugin. If this
    # endpoint or plugin shape changes, callers fall back to application-layer
    # parallel answers plus a judge model.
    plugin_payload = {
        "plugins": [
            {
                "id": "fusion",
                "analysis_models": payload.model_ids,
                "model": payload.judge_model_id,
            }
        ],
    }

    async for delta in stream_chat_text(
        FUSION_MODEL_ID,
        payload.messages,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        extra=plugin_payload,
    ):
        yield delta


def fusion_judge_prompt(
    user_question: str,
    model_answers: list[dict[str, str]],
) -> str:
    answer_blocks = "\n\n".join(
        f"### 候选模型：{item['model_id']}\n{item['answer']}"
        for item in model_answers
    )
    return f"""你是模镜专家团的首席裁判。请阅读多个模型对同一问题的回答，做事实核验、去重、互补整合，输出一份更可靠、更清晰的综合意见。

用户问题：
{user_question}

候选回答：
{answer_blocks}

输出要求：
1. 先给出“专家团综合意见”。
2. 标注不同模型观点中有价值的互补点。
3. 如果候选回答互相矛盾，请指出不确定性并给出验证建议。
4. 使用简体中文，结构清晰。"""


def workflow_node_kind(node: WorkflowNodePayload) -> WorkflowNodeType:
    data_kind = node.data.get("kind")
    if data_kind in {
        "input",
        "llm",
        "condition",
        "code",
        "variable_assign",
        "template_transform",
        "variable_aggregator",
        "parameter_extractor",
        "knowledge_retrieval",
        "document_extractor",
        "human_intervention",
        "question_classifier",
        "agent",
        "agent_task",
        "agent_handoff",
        "mcp_tool",
        "time_tool",
        "http_request",
        "list_operation",
        "iteration",
        "runtime_middleware",
        "output",
    }:
        return data_kind  # type: ignore[return-value]
    if node.type:
        return node.type
    raise HTTPException(status_code=400, detail=f"节点 {node.id} 缺少有效类型。")


def workflow_node_title(node: WorkflowNodePayload) -> str:
    title = node.data.get("title")
    return str(title) if isinstance(title, str) and title.strip() else node.id


def sse_payload(data: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def cleanup_expired_workflow_tasks() -> None:
    """Remove stale paused workflow runs from the in-memory task store."""

    now = time.monotonic()
    expired_task_ids = [
        task_id
        for task_id, task in workflow_task_store.items()
        if now - float(task.get("created_at", now)) > float(task.get("ttl", 0))
    ]
    for task_id in expired_task_ids:
        task = workflow_task_store.pop(task_id, None)
        pause_event = task.get("pause_event") if task else None
        if isinstance(pause_event, asyncio.Event):
            pause_event.set()


def get_workflow_task_or_none(task_id: str) -> dict[str, Any] | None:
    """Return an active workflow task or clean it up if it has expired."""

    task = workflow_task_store.get(task_id)
    if task is None:
        return None
    now = time.monotonic()
    if now - float(task.get("created_at", now)) > float(task.get("ttl", 0)):
        workflow_task_store.pop(task_id, None)
        pause_event = task.get("pause_event")
        if isinstance(pause_event, asyncio.Event):
            pause_event.set()
        return None
    return task


def render_workflow_template(template: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1).strip()
        return variables.get(variable_name, "")

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", replace, template)


def split_workflow_list(value: str) -> list[str]:
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def split_workflow_variable_names(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_workflow_tool_policy_list(value: Any) -> set[str]:
    """Parse a textarea or list value into a normalized tool-name set."""

    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    if not isinstance(value, str):
        return set()
    return {
        item.strip()
        for item in re.split(r"[,，\r\n]+", value)
        if item.strip()
    }


def parse_workflow_bool(value: Any, *, default: bool = True) -> bool:
    """Parse workflow form booleans while preserving a safe default."""

    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        return default
    return bool(value)


SAFE_PYTHON_BUILTINS = {
    "print",
    "len",
    "range",
    "str",
    "int",
    "float",
    "list",
    "dict",
    "set",
    "tuple",
    "sum",
    "min",
    "max",
    "sorted",
    "reversed",
    "abs",
    "round",
    "pow",
    "enumerate",
    "zip",
    "map",
    "filter",
}
FORBIDDEN_PYTHON_NAMES = {
    "__builtins__",
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "help",
    "locals",
    "open",
    "os",
    "pathlib",
    "shutil",
    "socket",
    "subprocess",
    "sys",
    "vars",
}
FORBIDDEN_PYTHON_NODES = (
    ast.AsyncFunctionDef,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.ClassDef,
    ast.Delete,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Lambda,
    ast.Nonlocal,
    ast.With,
)


class SafePythonValidator(ast.NodeVisitor):
    """Reject Python syntax that can break out of the workflow sandbox."""

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, FORBIDDEN_PYTHON_NODES):
            raise ValueError(f"Python sandbox rejects {type(node).__name__}.")
        return super().visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if node.attr.startswith("__"):
            raise ValueError("Python sandbox rejects dunder attribute access.")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> Any:
        if node.id.startswith("__") or node.id in FORBIDDEN_PYTHON_NAMES:
            raise ValueError(f"Python sandbox rejects name `{node.id}`.")

    def visit_Call(self, node: ast.Call) -> Any:
        if isinstance(node.func, ast.Name) and node.func.id in FORBIDDEN_PYTHON_NAMES:
            raise ValueError(f"Python sandbox rejects call `{node.func.id}`.")
        if isinstance(node.func, ast.Attribute) and node.func.attr.startswith("__"):
            raise ValueError("Python sandbox rejects dunder method calls.")
        self.generic_visit(node)


def render_python_code_template(template: str, variables: dict[str, str]) -> str:
    """Render {{var}} references as Python string literals, not raw code."""

    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1).strip()
        return repr(variables.get(variable_name, ""))

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", replace, template)


def validate_safe_python_code(code: str) -> None:
    if not code.strip():
        raise ValueError("Python code is empty.")
    tree = ast.parse(code, mode="exec")
    SafePythonValidator().visit(tree)


def run_python_code_sandbox(
    code: str,
    variables: dict[str, str],
    input_variable: str,
) -> str:
    """Run validated Python in an isolated child process with a short timeout."""

    validate_safe_python_code(code)
    WORKFLOW_PYTHON_SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)
    runner = """
import builtins
import contextlib
import io
import json
import sys

payload = json.load(sys.stdin)
allowed = payload["allowed_builtins"]
safe_builtins = {name: getattr(builtins, name) for name in allowed}
variables = {str(key): str(value) for key, value in payload["variables"].items()}
input_value = variables.get(payload.get("input_variable") or "", "")
namespace = {
    "__builtins__": safe_builtins,
    "variables": variables,
    "input": input_value,
}
stdout = io.StringIO()
with contextlib.redirect_stdout(stdout):
    exec(payload["code"], namespace, namespace)
output = stdout.getvalue()
if not output and "result" in namespace:
    output = str(namespace["result"])
print(output, end="")
""".strip()
    payload = {
        "allowed_builtins": sorted(SAFE_PYTHON_BUILTINS),
        "code": code,
        "input_variable": input_variable,
        "variables": variables,
    }
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-S", "-c", runner],
            input=json.dumps(payload, ensure_ascii=False),
            text=True,
            capture_output=True,
            cwd=str(WORKFLOW_PYTHON_SANDBOX_ROOT),
            timeout=WORKFLOW_PYTHON_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Python code timed out after 3 seconds.") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise ValueError(f"Python code failed: {message}")
    return completed.stdout[:20_000]


def extract_json_object_text(value: str) -> str | None:
    match = re.search(r"\{.*\}", value, re.DOTALL)
    return match.group(0) if match else None


def workflow_document_extractor_root() -> Path:
    configured = Path(WORKFLOW_DOC_EXTRACTOR_ROOT)
    if configured.is_absolute():
        return configured.resolve()

    candidates = [
        (Path.cwd() / configured).resolve(),
        (Path(__file__).resolve().parent / configured).resolve(),
        (Path(__file__).resolve().parent.parent / configured).resolve(),
        (Path(__file__).resolve().parent / "rag").resolve(),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def workflow_topological_order(
    nodes: list[WorkflowNodePayload],
    edges: list[WorkflowEdgePayload],
) -> list[str]:
    node_ids = {node.id for node in nodes}
    indegree = {node.id: 0 for node in nodes}
    outgoing: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            raise HTTPException(status_code=400, detail="工作流连线引用了不存在的节点。")
        outgoing[edge.source].append(edge.target)
        indegree[edge.target] += 1

    queue = deque(node_id for node_id, degree in indegree.items() if degree == 0)
    order: list[str] = []

    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for target_id in outgoing[node_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)

    if len(order) != len(nodes):
        raise HTTPException(status_code=400, detail="工作流暂不支持循环，请移除环形连线。")

    return order


def run_safe_code_node(node: WorkflowNodePayload, variables: dict[str, str]) -> str:
    operation = str(node.data.get("codeOperation") or "upper")
    input_variable = str(node.data.get("codeInputVariable") or "llm_output")
    source = variables.get(input_variable, "")

    if operation == "python":
        python_code = render_python_code_template(
            str(node.data.get("pythonCode") or ""),
            variables,
        )
        return run_python_code_sandbox(python_code, variables, input_variable)
    if operation == "upper":
        return source.upper()
    if operation == "lower":
        return source.lower()
    if operation == "replace":
        return source.replace(
            str(node.data.get("replaceFrom") or ""),
            str(node.data.get("replaceTo") or ""),
        )
    if operation == "concat":
        return source + str(node.data.get("concatValue") or "")

    raise HTTPException(status_code=400, detail=f"代码节点不支持操作：{operation}")


def image_url_as_markdown(url: str) -> str:
    return f"\n![图片]({url})\n"


def content_to_text_chunks(content: Any) -> list[str]:
    chunks: list[str] = []
    if isinstance(content, str):
        if content:
            chunks.append(content)
        return chunks

    if isinstance(content, list):
        for part in content:
            chunks.extend(content_to_text_chunks(part))
        return chunks

    if not isinstance(content, dict):
        return chunks

    part_type = content.get("type")
    if part_type == "text":
        text = content.get("text")
        if isinstance(text, str) and text:
            chunks.append(text)
        return chunks

    image_url = content.get("image_url")
    if part_type == "image_url" or isinstance(image_url, dict):
        if isinstance(image_url, dict):
            url = image_url.get("url")
            if isinstance(url, str) and url:
                chunks.append(image_url_as_markdown(url))
        return chunks

    return chunks


def sse_delta_text(event_text: str) -> list[str]:
    delta_parts: list[str] = []
    for line in event_text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        data = stripped[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            payload = json.loads(data)
        except json.JSONDecodeError:
            continue
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            continue
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            continue
        delta = first_choice.get("delta")
        message = first_choice.get("message")
        content: Any = ""
        if isinstance(delta, dict):
            content = delta.get("content")
        if (content is None or content == "") and isinstance(message, dict):
            content = message.get("content") or ""
        if content is None:
            content = ""
        delta_parts.extend(content_to_text_chunks(content))
        if isinstance(delta, dict):
            delta_parts.extend(content_to_text_chunks(delta.get("images")))
        if isinstance(message, dict):
            delta_parts.extend(content_to_text_chunks(message.get("images")))
    return delta_parts


async def stream_workflow_llm_text(
    model_id: str,
    prompt: str,
    *,
    system_prompt: str | None = None,
) -> AsyncIterator[str]:
    url, key = get_llm_gateway_config()
    if not url:
        raise RuntimeError(LLM_GATEWAY_NOT_CONFIGURED_MESSAGE)

    messages = []
    if system_prompt and system_prompt.strip():
        messages.append(ChatMessage(role="system", content=system_prompt.strip()))
    messages.append(ChatMessage(role="user", content=prompt))
    chat_payload = ChatRequest(
        model_id=model_id,
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
    )
    current_model_id = model_id

    async with httpx.AsyncClient(**llm_client_kwargs()) as client:
        async def open_stream(candidate_model_id: str) -> httpx.Response:
            return await client.send(
                client.build_request(
                    "POST",
                    url,
                    headers=llm_gateway_headers(key),
                    json=build_upstream_payload(chat_payload, candidate_model_id),
                ),
                stream=True,
            )

        response = await open_stream(current_model_id)
        if response.status_code >= 400:
            body = await response.aread()
            await response.aclose()
            message, data = parse_upstream_error(response.status_code, body)
            if should_fallback_model(response.status_code, message, data, current_model_id, messages):
                current_model_id = fallback_model_for(messages)
                yield f"提示：原模型暂不可用，已自动切换为 {current_model_id}。\n\n"
                response = await open_stream(current_model_id)
            else:
                raise RuntimeError(message)

        if response.status_code >= 400:
            body = await response.aread()
            await response.aclose()
            message, _ = parse_upstream_error(response.status_code, body)
            raise RuntimeError(message)

        buffer = ""
        try:
            async for chunk in response.aiter_text():
                if not chunk:
                    continue
                buffer += chunk
                events = buffer.split("\n\n")
                buffer = events.pop() or ""
                for event in events:
                    for text_chunk in sse_delta_text(event):
                        if text_chunk:
                            yield text_chunk
        finally:
            await response.aclose()

        if buffer.strip():
            for text_chunk in sse_delta_text(buffer):
                if text_chunk:
                    yield text_chunk


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/meta-agent/generate-workflow", response_model=MetaAgentGenerateResponse)
async def generate_meta_agent_workflow(
    payload: MetaAgentGenerateRequest,
    request: Request,
):
    if not get_llm_gateway_config()[0]:
        return JSONResponse(
            status_code=500,
            content={"error": LLM_GATEWAY_NOT_CONFIGURED_MESSAGE},
        )

    try:
        rate_limit_or_raise(client_ip(request))
        validate_plain_message(payload.goal)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    try:
        prompt = build_meta_agent_prompt(payload.goal, payload.max_tasks)
        raw_plan = await collect_chat_completion_text(
            payload.model_id,
            [
                ChatMessage(role="system", content=META_AGENT_SYSTEM_PROMPT),
                ChatMessage(role="user", content=prompt),
            ],
            temperature=payload.temperature,
            max_tokens=4096,
        )
        plan = parse_meta_agent_plan(raw_plan, max_tasks=payload.max_tasks)
        workflow, warnings = build_workflow_from_plan(
            goal=payload.goal,
            plan=plan,
            model_id=payload.model_id,
        )
        validation = validate_workflow_graph(
            NativeWorkflowDefinition.model_validate(
                {
                    "id": workflow["id"],
                    "title": workflow["title"],
                    "version": "meta-agent-v1",
                    "source": "workflow-native",
                    "nodes": workflow["nodes"],
                    "edges": workflow["edges"],
                }
            )
        )
        return MetaAgentGenerateResponse(
            goal=payload.goal,
            plan=plan,
            workflow=workflow,
            warnings=warnings,
            validation=validation.model_dump(mode="json"),
        )
    except ValueError as exc:
        return JSONResponse(status_code=422, content={"error": str(exc)})
    except Exception as exc:
        logger.exception("Meta-agent workflow generation failed")
        return JSONResponse(status_code=500, content={"error": str(exc)})


@app.post("/api/workflow/run")
async def run_workflow(payload: WorkflowRunRequest, request: Request):
    requires_model = any(
        (node.data.get("kind") if isinstance(node.data.get("kind"), str) else node.type)
        == "llm"
        for node in payload.workflow.nodes
    )
    if requires_model and not get_llm_gateway_config()[0]:
        return JSONResponse(
            status_code=500,
            content={"error": LLM_GATEWAY_NOT_CONFIGURED_MESSAGE},
        )

    try:
        rate_limit_or_raise(client_ip(request))
        order = workflow_topological_order(payload.workflow.nodes, payload.workflow.edges)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})
    except Exception:
        logger.exception("Workflow validation failed")
        return JSONResponse(status_code=500, content={"error": "工作流校验失败，请检查节点和连线。"})

    nodes_by_id = {node.id: node for node in payload.workflow.nodes}
    order_index = {node_id: index for index, node_id in enumerate(order)}
    outgoing: dict[str, list[WorkflowEdgePayload]] = defaultdict(list)
    for edge in payload.workflow.edges:
        outgoing[edge.source].append(edge)

    start_node_ids = [
        node.id for node in payload.workflow.nodes if workflow_node_kind(node) == "input"
    ]
    if not start_node_ids and order:
        start_node_ids = [order[0]]

    cleanup_expired_workflow_tasks()
    task_id = uuid.uuid4().hex
    workflow_run = await run_registry.create_run(
        "workflow",
        payload.workflow.title,
        status="running",
        source_id=payload.workflow.id,
        metadata={
            "workflow_id": payload.workflow.id,
            "workflow_title": payload.workflow.title,
            "workflow_task_id": task_id,
            "node_count": len(payload.workflow.nodes),
            "edge_count": len(payload.workflow.edges),
        },
    )
    initial_queue = deque(sorted(start_node_ids, key=lambda node_id: order_index[node_id]))
    task_state: dict[str, Any] = {
        "task_id": task_id,
        "run_id": workflow_run.run_id,
        "variables": {str(key): str(value) for key, value in payload.inputs.items()},
        "queue": initial_queue,
        "queued": set(initial_queue),
        "executed": set(),
        "nodes_by_id": nodes_by_id,
        "outgoing": outgoing,
        "order_index": order_index,
        "final_output": "",
        "pause_event": None,
        "resume_input": None,
        "paused_node_id": None,
        "created_at": time.monotonic(),
        "ttl": WORKFLOW_TASK_TTL_SECONDS,
        "runtime_event_store": RuntimeEventStore(),
        "tool_audit_store": InMemoryToolAuditStore(),
    }
    workflow_task_store[task_id] = task_state

    async def workflow_stream():
        variables: dict[str, str] = task_state["variables"]
        queue: deque[str] = task_state["queue"]
        queued: set[str] = task_state["queued"]
        executed: set[str] = task_state["executed"]
        final_output = ""
        workflow_runtime_context: dict[str, Any] = {
            "system_prompt": None,
            "override_system_prompt": False,
            "active_middlewares": [],
            "tool_policy": None,
        }

        try:
            yield sse_payload(
                {
                    "event": "workflow_meta",
                    "task_id": task_id,
                    "run_id": workflow_run.run_id,
                    "ttl_seconds": WORKFLOW_TASK_TTL_SECONDS,
                }
            )
            while queue:
                node_id = queue.popleft()
                node = nodes_by_id[node_id]
                kind = workflow_node_kind(node)
                title = workflow_node_title(node)

                if node_id in executed:
                    continue

                yield sse_payload(
                    {
                        "event": "node_start",
                        "node_id": node.id,
                        "node_title": title,
                        "node_type": kind,
                    }
                )

                chosen_handle: str | None = None
                output = ""

                if kind == "input":
                    variable_name = str(node.data.get("variableName") or "user_input")
                    variables[variable_name] = variables.get(
                        variable_name,
                        variables.get("user_input", ""),
                    )
                    output = variables[variable_name]

                elif kind == "llm":
                    model_id = str(node.data.get("modelId") or TEXT_FALLBACK_MODEL)
                    prompt = render_workflow_template(
                        str(node.data.get("prompt") or "{{user_input}}"),
                        variables,
                    )
                    output_variable = str(node.data.get("outputVariable") or "llm_output")
                    active_system_prompt = workflow_runtime_context.get("system_prompt")
                    system_prompt = (
                        active_system_prompt
                        if isinstance(active_system_prompt, str)
                        else None
                    )
                    async for delta in stream_workflow_llm_text(
                        model_id,
                        prompt,
                        system_prompt=system_prompt,
                    ):
                        output += delta
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": delta,
                                "variable": output_variable,
                            }
                        )
                    variables[output_variable] = output

                elif kind == "condition":
                    variable_name = str(node.data.get("conditionVariable") or "user_input")
                    operator = str(node.data.get("conditionOperator") or "contains")
                    expected = str(node.data.get("conditionValue") or "")
                    actual = variables.get(variable_name, "")
                    matched = actual == expected if operator == "equals" else expected in actual
                    chosen_handle = "true" if matched else "false"
                    output = f"{variable_name} {operator} {expected} -> {'是' if matched else '否'}"

                elif kind == "code":
                    output_variable = str(node.data.get("codeOutputVariable") or "code_output")
                    try:
                        output = run_safe_code_node(node, variables)
                        variables[output_variable] = output
                    except Exception as exc:
                        logger.warning("Workflow code node failed: %s", exc)
                        output = f"Code node failed: {exc}"
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": output,
                            }
                        )

                elif kind == "variable_assign":
                    try:
                        variable_name = str(node.data.get("variableName") or "assigned_text")
                        template = str(node.data.get("template") or "")
                        output = render_workflow_template(template, variables)
                        variables[variable_name] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": output,
                                "variable": variable_name,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Workflow variable_assign node failed: %s", exc)
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "http_request":
                    try:
                        method = str(node.data.get("method") or "GET").upper()
                        url = render_workflow_template(
                            str(node.data.get("url") or ""),
                            variables,
                        )
                        output_variable = str(
                            node.data.get("outputVariable") or "http_output"
                        )
                        headers: dict[str, str] = {}
                        headers_json = str(node.data.get("headersJson") or "").strip()
                        if headers_json:
                            try:
                                parsed_headers = json.loads(headers_json)
                                if isinstance(parsed_headers, dict):
                                    headers = {
                                        str(key): str(value)
                                        for key, value in parsed_headers.items()
                                    }
                            except ValueError as exc:
                                yield sse_payload(
                                    {
                                        "event": "error",
                                        "node_id": node.id,
                                        "message": f"headersJson 解析失败，已忽略：{exc}",
                                    }
                                )
                        body_variable = str(node.data.get("bodyVariable") or "").strip()
                        body = variables.get(body_variable, "") if body_variable else None
                        if not WORKFLOW_ALLOW_HTTP_OUTBOUND:
                            output = (
                                f"[http mock] method={method} url={url} "
                                "status=200 body=mocked"
                            )
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": f"outbound disabled\n{output}",
                                    "variable": output_variable,
                                }
                            )
                        else:
                            async with httpx.AsyncClient(timeout=10) as client:
                                response = await client.request(
                                    method,
                                    url,
                                    headers=headers,
                                    content=body if method == "POST" else None,
                                )
                            output = response.text
                            if response.status_code < 200 or response.status_code >= 300:
                                yield sse_payload(
                                    {
                                        "event": "error",
                                        "node_id": node.id,
                                        "message": (
                                            f"HTTP 请求失败：{response.status_code}"
                                        ),
                                    }
                                )
                            else:
                                variables[output_variable] = output
                                yield sse_payload(
                                    {
                                        "event": "node_delta",
                                        "node_id": node.id,
                                        "node_title": title,
                                        "node_type": kind,
                                        "output": output,
                                        "variable": output_variable,
                                    }
                                )
                    except Exception as exc:
                        logger.warning("Workflow http_request node failed: %s", exc)
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "list_operation":
                    try:
                        input_variable = str(node.data.get("inputVariable") or "user_input")
                        operator = str(node.data.get("operator") or "length")
                        output_variable = str(
                            node.data.get("outputVariable") or "list_output"
                        )
                        items = split_workflow_list(variables.get(input_variable, ""))
                        if operator == "length":
                            output = str(len(items))
                        elif operator == "join":
                            separator = str(node.data.get("joinSeparator") or "")
                            output = separator.join(items)
                        elif operator == "first":
                            output = items[0] if items else ""
                        elif operator == "last":
                            output = items[-1] if items else ""
                        else:
                            raise ValueError(f"列表操作不支持：{operator}")
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": output,
                                "variable": output_variable,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Workflow list_operation node failed: %s", exc)
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "iteration":
                    try:
                        input_variable = str(node.data.get("inputVariable") or "user_input")
                        iteration_variable = str(
                            node.data.get("iterationVariable") or "item"
                        )
                        item_template = str(node.data.get("itemTemplate") or "{{item}}")
                        output_variable = str(
                            node.data.get("outputVariable") or "iteration_output"
                        )
                        items = split_workflow_list(variables.get(input_variable, ""))
                        if len(items) > WORKFLOW_MAX_ITERATION_ITEMS:
                            items = items[:WORKFLOW_MAX_ITERATION_ITEMS]
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": (
                                        "truncated to "
                                        f"{WORKFLOW_MAX_ITERATION_ITEMS} items"
                                    ),
                                    "variable": output_variable,
                                }
                            )
                        results: list[str] = []
                        for index, item in enumerate(items, start=1):
                            variables[iteration_variable] = item
                            result = render_workflow_template(item_template, variables)
                            results.append(result)
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": f"[{index}] {result}",
                                    "variable": output_variable,
                                }
                            )
                        output = json.dumps(results, ensure_ascii=False)
                        variables[output_variable] = output
                    except Exception as exc:
                        logger.warning("Workflow iteration node failed: %s", exc)
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "template_transform":
                    try:
                        output_variable = str(
                            node.data.get("outputVariable") or "template_output"
                        )
                        template = str(node.data.get("template") or "")
                        output = render_workflow_template(template, variables)
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": output[:200],
                                "variable": output_variable,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Workflow template_transform node failed: %s", exc)
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "variable_aggregator":
                    try:
                        output_variable = str(
                            node.data.get("outputVariable") or "aggregated_output"
                        )
                        variable_names = split_workflow_variable_names(
                            str(node.data.get("variableNames") or "")
                        )
                        output_template = str(node.data.get("outputTemplate") or "")
                        values = {name: variables.get(name, "") for name in variable_names}
                        if output_template:
                            output = "".join(
                                output_template.replace("{name}", name).replace(
                                    "{value}", value
                                )
                                for name, value in values.items()
                            )
                        else:
                            output = json.dumps(values, ensure_ascii=False)
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": output,
                                "variable": output_variable,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Workflow variable_aggregator node failed: %s", exc)
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "parameter_extractor":
                    try:
                        output_variable = str(
                            node.data.get("outputVariable") or "parameters_json"
                        )
                        input_variable = str(node.data.get("inputVariable") or "user_input")
                        schema = str(node.data.get("schema") or "")
                        model_id = str(node.data.get("modelId") or TEXT_FALLBACK_MODEL)
                        input_text = variables.get(input_variable, "")
                        if not get_llm_gateway_config()[0]:
                            output = "{}"
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": "LLM gateway not configured; returned {}",
                                    "variable": output_variable,
                                }
                            )
                        else:
                            prompt = (
                                "请从以下文本中严格按 JSON 格式返回指定字段 "
                                f"{schema}；若无法提取则返回空对象 {{}}。\n\n"
                                f"文本：\n{input_text}"
                            )
                            raw_text = await collect_chat_completion_text(
                                model_id,
                                [ChatMessage(role="user", content=prompt)],
                                temperature=0.3,
                                max_tokens=1024,
                            )
                            json_text = extract_json_object_text(raw_text)
                            if json_text:
                                try:
                                    parsed = json.loads(json_text)
                                    output = json.dumps(parsed, ensure_ascii=False)
                                except ValueError:
                                    output = raw_text
                                    yield sse_payload(
                                        {
                                            "event": "error",
                                            "node_id": node.id,
                                            "message": "参数提取返回 JSON 解析失败，已保留原文。",
                                        }
                                    )
                            else:
                                output = raw_text
                                yield sse_payload(
                                    {
                                        "event": "error",
                                        "node_id": node.id,
                                        "message": "参数提取未找到 JSON 对象，已保留原文。",
                                    }
                                )
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": output,
                                    "variable": output_variable,
                                }
                            )
                    except Exception as exc:
                        logger.warning("Workflow parameter_extractor node failed: %s", exc)
                        variables[str(node.data.get("outputVariable") or "parameters_json")] = "{}"
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "knowledge_retrieval":
                    try:
                        output_variable = str(
                            node.data.get("outputVariable") or "rag_context"
                        )
                        query_variable = str(node.data.get("queryVariable") or "user_input")
                        query_text = variables.get(query_variable, "")
                        try:
                            top_k = int(str(node.data.get("top_k") or "3"))
                        except ValueError:
                            top_k = 3
                        top_k = max(1, min(top_k, 20))
                        service = RagService(llm_enabled=False)
                        knowledge_bases = service.list_knowledge_bases()
                        if not knowledge_bases:
                            output = ""
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "error",
                                    "node_id": node.id,
                                    "message": "RAG 索引未就绪，尚无可查询知识库。",
                                }
                            )
                        else:
                            kb_id = str(knowledge_bases[0]["id"])
                            result = await service.query(kb_id, query_text, top_k=top_k)
                            sources = result.get("sources")
                            if isinstance(sources, list):
                                parts = [
                                    str(source.get("text") or "")
                                    for source in sources
                                    if isinstance(source, dict) and source.get("text")
                                ]
                            else:
                                parts = []
                            output = "\n---\n".join(parts)
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": output or "RAG 未返回相关片段。",
                                    "variable": output_variable,
                                }
                            )
                    except Exception as exc:
                        logger.warning("Workflow knowledge_retrieval node failed: %s", exc)
                        variables[str(node.data.get("outputVariable") or "rag_context")] = ""
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "document_extractor":
                    try:
                        output_variable = str(
                            node.data.get("outputVariable") or "document_text"
                        )
                        source_path_variable = str(
                            node.data.get("sourcePathVariable") or "document_path"
                        )
                        raw_path = variables.get(source_path_variable, "")
                        root = workflow_document_extractor_root()
                        candidate = (root / raw_path).resolve()
                        output = ""
                        if not raw_path.strip():
                            yield sse_payload(
                                {
                                    "event": "error",
                                    "node_id": node.id,
                                    "message": "文档路径为空。",
                                }
                            )
                        elif root != candidate and root not in candidate.parents:
                            yield sse_payload(
                                {
                                    "event": "error",
                                    "node_id": node.id,
                                    "message": "文档路径超出允许目录，已拒绝读取。",
                                }
                            )
                        elif not candidate.exists() or not candidate.is_file():
                            yield sse_payload(
                                {
                                    "event": "error",
                                    "node_id": node.id,
                                    "message": "文档不存在或不是文件。",
                                }
                            )
                        else:
                            try:
                                output = parse_document(candidate, candidate.name)
                            except Exception:
                                output = candidate.read_text(encoding="utf-8")
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": output[:500],
                                    "variable": output_variable,
                                }
                            )
                        variables.setdefault(output_variable, output)
                    except Exception as exc:
                        logger.warning("Workflow document_extractor node failed: %s", exc)
                        variables[str(node.data.get("outputVariable") or "document_text")] = ""
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "human_intervention":
                    output_variable = str(node.data.get("outputVariable") or "human_input")
                    prompt = render_workflow_template(
                        str(node.data.get("prompt") or "请输入人工补充内容。"),
                        variables,
                    )
                    if not WORKFLOW_HUMAN_INTERVENTION_ENABLED:
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": "人工介入节点当前未启用。",
                            }
                        )
                    else:
                        pause_event = asyncio.Event()
                        task_state["pause_event"] = pause_event
                        task_state["resume_input"] = None
                        task_state["paused_node_id"] = node.id
                        yield sse_payload(
                            {
                                "event": "human_intervention_pending",
                                "task_id": task_id,
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "prompt": prompt,
                                "output_variable": output_variable,
                            }
                        )
                        while not pause_event.is_set():
                            try:
                                await asyncio.wait_for(pause_event.wait(), timeout=15)
                            except asyncio.TimeoutError:
                                yield sse_payload(
                                    {
                                        "event": "heartbeat",
                                        "task_id": task_id,
                                        "node_id": node.id,
                                        "at": time.time(),
                                    }
                                )
                        output = str(task_state.get("resume_input") or "")
                        task_state["paused_node_id"] = None
                        task_state["resume_input"] = None
                        task_state["pause_event"] = None
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": output,
                                "variable": output_variable,
                            }
                        )

                elif kind == "question_classifier":
                    output_variable = str(node.data.get("outputVariable") or "category")
                    default_category = str(node.data.get("defaultCategory") or "未知")
                    output = default_category
                    try:
                        input_variable = str(
                            node.data.get("inputVariable") or "user_input"
                        )
                        categories_json = str(node.data.get("categories") or "{}")
                        match_mode = str(
                            node.data.get("matchMode") or "contains_any"
                        ).strip()
                        case_sensitive = (
                            str(node.data.get("caseSensitive") or "false")
                            .strip()
                            .lower()
                            == "true"
                        )
                        use_llm_fallback = (
                            str(node.data.get("useLlmFallback") or "false")
                            .strip()
                            .lower()
                            == "true"
                        )
                        model_id = str(node.data.get("modelId") or "").strip()
                        text = variables.get(input_variable, "")

                        if not WORKFLOW_QUESTION_CLASSIFIER_ENABLED:
                            variables[output_variable] = default_category
                            output = default_category
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": (
                                        "question_classifier disabled; "
                                        f"default={default_category}"
                                    ),
                                    "variable": output_variable,
                                }
                            )
                        else:
                            try:
                                raw_categories = json.loads(categories_json)
                            except ValueError as exc:
                                raise ValueError(f"分类规则 JSON 解析失败：{exc}") from exc
                            if not isinstance(raw_categories, dict) or not raw_categories:
                                raise ValueError("分类规则必须是非空 JSON 对象。")

                            category_map: dict[str, list[str]] = {}
                            for category_name, keywords in raw_categories.items():
                                if not isinstance(category_name, str):
                                    raise ValueError("分类名称必须是字符串。")
                                if not isinstance(keywords, list):
                                    raise ValueError("分类关键词必须是字符串数组。")
                                clean_keywords = [
                                    str(keyword).strip()
                                    for keyword in keywords
                                    if isinstance(keyword, str) and keyword.strip()
                                ]
                                if not clean_keywords:
                                    raise ValueError(
                                        f"分类 {category_name} 至少需要一个关键词。"
                                    )
                                category_map[category_name] = clean_keywords

                            comparison_text = text if case_sensitive else text.lower()
                            selected = ""
                            matched_keyword = ""
                            for category_name, keywords in category_map.items():
                                comparison_keywords = (
                                    keywords
                                    if case_sensitive
                                    else [keyword.lower() for keyword in keywords]
                                )
                                if match_mode == "contains_all":
                                    matched = all(
                                        keyword in comparison_text
                                        for keyword in comparison_keywords
                                    )
                                    keyword_hint = ",".join(keywords)
                                else:
                                    hit_index = next(
                                        (
                                            index
                                            for index, keyword in enumerate(
                                                comparison_keywords
                                            )
                                            if keyword in comparison_text
                                        ),
                                        -1,
                                    )
                                    matched = hit_index >= 0
                                    keyword_hint = (
                                        keywords[hit_index] if hit_index >= 0 else ""
                                    )
                                if matched:
                                    selected = category_name
                                    matched_keyword = keyword_hint
                                    break

                            delta_output = ""
                            if selected:
                                output = selected
                                delta_output = (
                                    f"已分类：{selected}（关键词命中：{matched_keyword}）"
                                )
                            elif use_llm_fallback:
                                if not get_llm_gateway_config()[0] or not model_id:
                                    raise ValueError(
                                        "LLM 回退未配置网关或 modelId。"
                                    )
                                fallback_prompt = str(
                                    node.data.get("llmFallbackPrompt") or ""
                                ).strip()
                                if fallback_prompt:
                                    prompt = render_workflow_template(
                                        fallback_prompt,
                                        variables,
                                    )
                                else:
                                    prompt = (
                                        "请从下列文本中判断它属于哪个已知类别："
                                        f"{json.dumps(list(category_map.keys()), ensure_ascii=False)}。"
                                        "只回答类别名，不要多余文字或解释。如无法判断则回答 "
                                        '"未知"。\n\n文本：\n'
                                        f"{text}"
                                    )
                                selected = (
                                    await collect_chat_completion_text(
                                        model_id,
                                        [ChatMessage(role="user", content=prompt)],
                                        temperature=0,
                                        max_tokens=20,
                                    )
                                ).strip()
                                output = selected or default_category
                                delta_output = f"已分类：{output}（LLM 回退）"
                                if output not in category_map:
                                    yield sse_payload(
                                        {
                                            "event": "node_delta",
                                            "node_id": node.id,
                                            "node_title": title,
                                            "node_type": kind,
                                            "output": (
                                                f'LLM 返回类别 "{output}" 不在预设集合中，'
                                                "已原样输出。"
                                            ),
                                            "variable": output_variable,
                                        }
                                    )
                            else:
                                output = default_category
                                delta_output = (
                                    f"规则未命中，返回默认类别：{default_category}"
                                )

                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": delta_output,
                                    "variable": output_variable,
                                }
                            )
                    except Exception as exc:
                        logger.warning("Workflow question_classifier node failed: %s", exc)
                        output = default_category
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "agent":
                    output_variable = str(node.data.get("outputVariable") or "agent_output")
                    output = ""
                    try:
                        if not WORKFLOW_AGENT_ENABLED:
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": "agent 节点当前未启用。",
                                    "variable": output_variable,
                                }
                            )
                        else:
                            agent_mode = str(
                                node.data.get("agentMode") or "tool_first"
                            ).strip()
                            model_id = str(node.data.get("modelId") or "").strip()
                            instruction = render_workflow_template(
                                str(node.data.get("instruction") or ""),
                                variables,
                            ).strip()
                            prompt_suffix = render_workflow_template(
                                str(node.data.get("promptSuffix") or ""),
                                variables,
                            ).strip()
                            if prompt_suffix:
                                instruction = f"{instruction}\n\n{prompt_suffix}".strip()
                            if not model_id:
                                raise ValueError("Agent 节点缺少 modelId。")
                            if not instruction:
                                raise ValueError("Agent 节点缺少 instruction。")
                            try:
                                temperature = float(
                                    str(node.data.get("temperature") or "0.7")
                                )
                            except ValueError:
                                temperature = 0.7
                            temperature = min(max(temperature, 0.0), 2.0)
                            try:
                                max_iterations = int(
                                    str(
                                        node.data.get("maxIterations")
                                        or WORKFLOW_AGENT_MAX_ITERATIONS_DEFAULT
                                    )
                                )
                            except ValueError:
                                max_iterations = WORKFLOW_AGENT_MAX_ITERATIONS_DEFAULT
                            max_iterations = min(max(max_iterations, 1), 20)

                            async def run_direct_agent() -> str:
                                if not get_llm_gateway_config()[0]:
                                    raise ValueError(LLM_GATEWAY_NOT_CONFIGURED_MESSAGE)
                                return await collect_chat_completion_text(
                                    model_id,
                                    [ChatMessage(role="user", content=instruction)],
                                    temperature=temperature,
                                    max_tokens=WORKFLOW_AGENT_MAX_TOKENS,
                                )

                            if agent_mode == "direct":
                                output = await run_direct_agent()
                                variables[output_variable] = output
                                yield sse_payload(
                                    {
                                        "event": "node_delta",
                                        "node_id": node.id,
                                        "node_title": title,
                                        "node_type": kind,
                                        "output": output[:500],
                                        "variable": output_variable,
                                    }
                                )
                            elif agent_mode == "tool_first":
                                registered_tools = await tool_registry.list_tools()
                                requested_tool_names = [
                                    item.strip()
                                    for item in str(node.data.get("toolNames") or "").split(",")
                                    if item.strip()
                                ]
                                if requested_tool_names:
                                    allowed_names = set(requested_tool_names)
                                    available_tools = [
                                        tool
                                        for tool in registered_tools
                                        if str(tool.get("name") or "") in allowed_names
                                    ]
                                else:
                                    available_tools = registered_tools

                                if not available_tools:
                                    yield sse_payload(
                                        {
                                            "event": "node_delta",
                                            "node_id": node.id,
                                            "node_title": title,
                                            "node_type": kind,
                                            "output": "Agent 切换为直接回答：没有可用 MCP 工具",
                                            "variable": output_variable,
                                        }
                                    )
                                    output = await run_direct_agent()
                                    variables[output_variable] = output
                                    yield sse_payload(
                                        {
                                            "event": "node_delta",
                                            "node_id": node.id,
                                            "node_title": title,
                                            "node_type": kind,
                                            "output": output[:500],
                                            "variable": output_variable,
                                        }
                                    )
                                else:
                                    tool_by_name = {
                                        str(tool.get("name") or ""): tool
                                        for tool in available_tools
                                        if str(tool.get("name") or "")
                                    }
                                    tool_descriptions = "\n".join(
                                        (
                                            f"- {name}: "
                                            f"{tool.get('description') or '无描述'} "
                                            f"schema={json.dumps(tool.get('input_schema') or {}, ensure_ascii=False)}"
                                        )
                                        for name, tool in tool_by_name.items()
                                    )
                                    system_prompt = (
                                        "你是模镜工作流中的 ReAct-Lite Agent。"
                                        "你可以选择调用一个工具，或给出最终答案。"
                                        "每次回复必须是 JSON，且只能使用以下两种格式之一："
                                        '{"tool":"工具名","arguments":{...}} 或 {"answer":"最终答案"}。'
                                        "不要输出 JSON 以外的文字。\n\n可用工具：\n"
                                        f"{tool_descriptions}"
                                    )
                                    messages: list[ChatMessage] = [
                                        ChatMessage(role="system", content=system_prompt),
                                        ChatMessage(role="user", content=instruction),
                                    ]
                                    for iteration_index in range(max_iterations):
                                        if not get_llm_gateway_config()[0]:
                                            raise ValueError(LLM_GATEWAY_NOT_CONFIGURED_MESSAGE)
                                        raw_response = (
                                            await collect_chat_completion_text(
                                                model_id,
                                                messages,
                                                temperature=temperature,
                                                max_tokens=WORKFLOW_AGENT_MAX_TOKENS,
                                            )
                                        ).strip()
                                        json_text = raw_response
                                        fenced = re.search(
                                            r"```(?:json)?\s*\n?(.*?)\n?```",
                                            raw_response,
                                            re.DOTALL,
                                        )
                                        if fenced:
                                            json_text = fenced.group(1).strip()
                                        try:
                                            decision = json.loads(json_text)
                                        except ValueError:
                                            output = raw_response
                                            break
                                        if not isinstance(decision, dict):
                                            output = raw_response
                                            break
                                        answer = decision.get("answer")
                                        if isinstance(answer, str) and answer.strip():
                                            output = answer.strip()
                                            break
                                        tool_name = str(decision.get("tool") or "").strip()
                                        arguments = decision.get("arguments")
                                        if not tool_name:
                                            output = raw_response
                                            break
                                        if not isinstance(arguments, dict):
                                            arguments = {}
                                        matched_tool = tool_by_name.get(tool_name)
                                        if not matched_tool:
                                            tool_result_text = f"工具不可用：{tool_name}"
                                            yield sse_payload(
                                                {
                                                    "event": "node_delta",
                                                    "node_id": node.id,
                                                    "node_title": title,
                                                    "node_type": kind,
                                                    "output": tool_result_text,
                                                    "variable": output_variable,
                                                }
                                            )
                                        else:
                                            call_result = await mcp_manager.call_tool(
                                                str(matched_tool.get("session_id") or ""),
                                                tool_name,
                                                arguments,
                                            )
                                            text_parts: list[str] = []
                                            non_text_types: list[str] = []
                                            for part in getattr(call_result, "content", []) or []:
                                                if isinstance(part, dict):
                                                    part_type = str(part.get("type") or "other")
                                                    part_text = part.get("text")
                                                else:
                                                    part_type = str(getattr(part, "type", "other"))
                                                    part_text = getattr(part, "text", None)
                                                if part_type == "text":
                                                    text_parts.append(str(part_text or ""))
                                                else:
                                                    non_text_types.append(part_type)
                                            tool_result_text = "\n".join(text_parts).strip()
                                            if non_text_types:
                                                tool_result_text = (
                                                    tool_result_text
                                                    + "\n"
                                                    + "非文本结果已省略："
                                                    + ", ".join(non_text_types)
                                                ).strip()
                                            yield sse_payload(
                                                {
                                                    "event": "node_delta",
                                                    "node_id": node.id,
                                                    "node_title": title,
                                                    "node_type": kind,
                                                    "output": (
                                                        f"[{iteration_index + 1}/{max_iterations}] "
                                                        f"调用工具 {tool_name}，结果预览："
                                                        f"{tool_result_text[:300]}"
                                                    ),
                                                    "variable": output_variable,
                                                }
                                            )
                                        messages.append(
                                            ChatMessage(
                                                role="assistant",
                                                content=json.dumps(
                                                    decision,
                                                    ensure_ascii=False,
                                                ),
                                            )
                                        )
                                        messages.append(
                                            ChatMessage(
                                                role="user",
                                                content=(
                                                    f"工具 {tool_name} 的执行结果：\n"
                                                    f"{tool_result_text}\n\n"
                                                    "请继续用 JSON 决策下一步。"
                                                ),
                                            )
                                        )
                                    else:
                                        yield sse_payload(
                                            {
                                                "event": "node_delta",
                                                "node_id": node.id,
                                                "node_title": title,
                                                "node_type": kind,
                                                "output": (
                                                    f"Agent 达到最大循环次数 {max_iterations}，"
                                                    "未得到最终答案。"
                                                ),
                                                "variable": output_variable,
                                            }
                                        )
                                        output = ""
                                    variables[output_variable] = output
                                    yield sse_payload(
                                        {
                                            "event": "node_delta",
                                            "node_id": node.id,
                                            "node_title": title,
                                            "node_type": kind,
                                            "output": output[:500],
                                            "variable": output_variable,
                                        }
                                    )
                            else:
                                raise ValueError(f"Agent 模式不支持：{agent_mode}")
                    except Exception as exc:
                        logger.warning("Workflow agent node failed: %s", exc)
                        output = ""
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "agent_task":
                    output_variable = str(
                        node.data.get("outputVariable") or "agent_task_id"
                    ).strip()
                    if not output_variable:
                        output_variable = "agent_task_id"
                    try:
                        task_title = render_workflow_template(
                            str(node.data.get("taskTitle") or "Workflow agent task"),
                            variables,
                        ).strip()
                        task_input = render_workflow_template(
                            str(node.data.get("taskInput") or ""),
                            variables,
                        )
                        assigned_agent = str(
                            node.data.get("assignedAgent") or "workflow-planner"
                        ).strip()
                        if not task_title:
                            raise ValueError("agent_task 缺少任务标题。")
                        if not task_input.strip():
                            raise ValueError("agent_task 缺少任务输入。")

                        task = await agent_task_store.create_task(
                            title=task_title,
                            input_text=task_input,
                            source_agent="workflow",
                            assigned_agent=assigned_agent or "workflow-planner",
                            metadata={
                                "workflow_id": payload.workflow.id,
                                "workflow_title": payload.workflow.title,
                                "workflow_task_id": task_id,
                                "workflow_node_id": node.id,
                                "workflow_node_title": title,
                                "output_variable": output_variable,
                            },
                        )
                        agent_task_run = await run_registry.create_run(
                            "agent_task",
                            task.title,
                            status="pending",
                            source_id=task.task_id,
                            parent_run_id=workflow_run.run_id,
                            metadata={
                                "workflow_id": payload.workflow.id,
                                "workflow_title": payload.workflow.title,
                                "workflow_task_id": task_id,
                                "node_id": node.id,
                                "node_title": title,
                                "agent_task_id": task.task_id,
                                "assigned_agent": assigned_agent,
                                "output_variable": output_variable,
                            },
                        )
                        output = task.task_id
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": (
                                    "已创建 Agent Task："
                                    f"{task.title}（{task.task_id}）"
                                ),
                                "variable": output_variable,
                                "run_id": agent_task_run.run_id,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Workflow agent_task node failed: %s", exc)
                        output = ""
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "agent_handoff":
                    output_variable = str(
                        node.data.get("outputVariable") or "agent_handoff_id"
                    ).strip() or "agent_handoff_id"
                    try:
                        task_id_variable = str(
                            node.data.get("taskIdVariable") or "agent_task_id"
                        ).strip()
                        target_agent = str(node.data.get("targetAgent") or "").strip()
                        source_agent = str(
                            node.data.get("sourceAgent") or "workflow"
                        ).strip() or "workflow"
                        reason_template = str(node.data.get("reason") or "")

                        if not task_id_variable:
                            raise ValueError("agent_handoff node needs taskIdVariable.")
                        if not target_agent:
                            raise ValueError("agent_handoff node needs targetAgent.")
                        if not reason_template.strip():
                            raise ValueError("agent_handoff node needs reason.")

                        handoff_task_id = variables.get(task_id_variable, "").strip()
                        if not handoff_task_id:
                            raise ValueError(
                                f"agent_handoff could not read task id variable: {task_id_variable}"
                            )
                        task = await agent_task_store.get_task(handoff_task_id)
                        if task is None:
                            raise ValueError(
                                f"agent_handoff task not found: {handoff_task_id}"
                            )

                        reason = render_workflow_template(
                            reason_template,
                            variables,
                        ).strip()
                        if not reason:
                            raise ValueError("agent_handoff rendered reason is empty.")

                        handoff = await agent_task_store.create_handoff(
                            handoff_task_id,
                            source_agent=source_agent,
                            target_agent=target_agent,
                            reason=reason,
                            metadata={
                                "workflow_id": payload.workflow.id,
                                "workflow_title": payload.workflow.title,
                                "workflow_task_id": task_id,
                                "workflow_node_id": node.id,
                                "workflow_node_title": title,
                                "task_id_variable": task_id_variable,
                                "output_variable": output_variable,
                            },
                        )
                        handoff_run = await run_registry.create_run(
                            "agent_handoff",
                            f"{source_agent} -> {target_agent}",
                            status="pending",
                            source_id=handoff.handoff_id,
                            parent_run_id=workflow_run.run_id,
                            metadata={
                                "workflow_id": payload.workflow.id,
                                "workflow_title": payload.workflow.title,
                                "workflow_task_id": task_id,
                                "node_id": node.id,
                                "node_title": title,
                                "agent_task_id": handoff_task_id,
                                "handoff_id": handoff.handoff_id,
                                "source_agent": source_agent,
                                "target_agent": target_agent,
                                "task_id_variable": task_id_variable,
                                "output_variable": output_variable,
                            },
                        )
                        output = handoff.handoff_id
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "node_delta",
                                "node_id": node.id,
                                "node_title": title,
                                "node_type": kind,
                                "output": (
                                    f"Created Agent Handoff: {source_agent} -> "
                                    f"{target_agent} ({handoff.handoff_id})"
                                ),
                                "variable": output_variable,
                                "agent_task_id": handoff_task_id,
                                "agent_handoff_id": handoff.handoff_id,
                                "run_id": handoff_run.run_id,
                            }
                        )
                    except Exception as exc:
                        logger.warning("Workflow agent_handoff node failed: %s", exc)
                        output = ""
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "mcp_tool":
                    output_variable = str(node.data.get("outputVariable") or "mcp_output")
                    try:
                        tool_name = str(node.data.get("toolName") or "").strip()
                        if not WORKFLOW_MCP_TOOL_ENABLED or not tool_name:
                            output = ""
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": "mcp_tool 未启用或 toolName 为空。",
                                    "variable": output_variable,
                                }
                            )
                        else:
                            matched_tool = await workflow_mcp_provider.find_tool(tool_name)
                            if not matched_tool:
                                raise ValueError(f"MCP 工具未注册：{tool_name}")
                            raw_arguments = render_workflow_template(
                                str(node.data.get("argumentsJson") or "{}"),
                                variables,
                            )
                            arguments = json.loads(raw_arguments)
                            if not isinstance(arguments, dict):
                                raise ValueError("MCP 工具参数必须是 JSON 对象。")
                            call_result = await run_tool_with_runtime(
                                RuntimeToolCall(
                                    tool_name=tool_name,
                                    arguments=arguments,
                                    metadata={
                                        "session_id": matched_tool.session_id,
                                        "server_id": matched_tool.server_id,
                                        "node_id": node.id,
                                    },
                                ),
                                runtime_capabilities,
                                workflow_mcp_pipeline,
                                MiddlewareContext(
                                    task_id=task_id,
                                    trace_id=task_id,
                                    capabilities=runtime_capabilities,
                                    store=task_state["runtime_event_store"],
                                    metadata={
                                        "node_id": node.id,
                                        "node_title": title,
                                        "workflow": True,
                                    },
                                ),
                                policy=(
                                    workflow_runtime_context.get("tool_policy")
                                    or workflow_tool_policy
                                ),
                                audit_store=(
                                    task_state.get("tool_audit_store")
                                    or workflow_tool_audit_store
                                ),
                            )
                            content_types = call_result.metadata.get("content_types", [])
                            non_text_types = [
                                str(content_type)
                                for content_type in content_types
                                if str(content_type) != "text"
                            ]
                            output = call_result.output.strip()
                            variables[output_variable] = output
                            if non_text_types:
                                yield sse_payload(
                                    {
                                        "event": "node_delta",
                                        "node_id": node.id,
                                        "node_title": title,
                                        "node_type": kind,
                                        "output": (
                                            "非文本工具结果已省略："
                                            + ", ".join(non_text_types)
                                        ),
                                        "variable": output_variable,
                                    }
                                )
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": output[:300],
                                    "variable": output_variable,
                                }
                            )
                    except Exception as exc:
                        logger.warning("Workflow mcp_tool node failed: %s", exc)
                        output = ""
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "time_tool":
                    output_variable = str(node.data.get("outputVariable") or "current_time")
                    try:
                        if not WORKFLOW_TIME_TOOL_ENABLED:
                            output = ""
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": "time_tool 当前未启用。",
                                    "variable": output_variable,
                                }
                            )
                        else:
                            operation = str(node.data.get("operation") or "now_iso").strip()
                            format_string = str(
                                node.data.get("formatString") or "%Y-%m-%d %H:%M:%S"
                            )
                            if operation == "now_iso":
                                output = datetime.now().isoformat()
                            elif operation == "now_epoch":
                                output = str(int(time.time()))
                            elif operation == "format":
                                output = datetime.now().strftime(format_string)
                            else:
                                raise ValueError(f"时间工具操作不支持：{operation}")
                            variables[output_variable] = output
                            yield sse_payload(
                                {
                                    "event": "node_delta",
                                    "node_id": node.id,
                                    "node_title": title,
                                    "node_type": kind,
                                    "output": output[:200],
                                    "variable": output_variable,
                                }
                            )
                    except Exception as exc:
                        logger.warning("Workflow time_tool node failed: %s", exc)
                        output = ""
                        variables[output_variable] = output
                        yield sse_payload(
                            {
                                "event": "error",
                                "node_id": node.id,
                                "message": str(exc),
                            }
                        )

                elif kind == "runtime_middleware":
                    middleware_id = str(
                        node.data.get("runtimeMiddlewareId") or "unknown"
                    )
                    middleware_kind = str(
                        node.data.get("runtimeMiddlewareKind")
                        or "runtime_middleware.unknown"
                    )
                    middleware_config = node.data.get("runtimeMiddlewareConfig")
                    if not isinstance(middleware_config, dict):
                        middleware_config = {}
                    if middleware_id == "tool_policy":
                        allowed_tools = parse_workflow_tool_policy_list(
                            middleware_config.get("allowed_tools")
                        )
                        denied_tools = parse_workflow_tool_policy_list(
                            middleware_config.get("denied_tools")
                        )
                        allow_by_default = parse_workflow_bool(
                            middleware_config.get("allow_by_default"),
                            default=True,
                        )
                        workflow_runtime_context["tool_policy"] = ToolPermissionPolicy(
                            allowed_tools=allowed_tools,
                            denied_tools=denied_tools,
                            allow_by_default=allow_by_default,
                        )
                        workflow_runtime_context["active_middlewares"].append(
                            middleware_id
                        )
                        allowed_info = (
                            f"允许工具: {', '.join(sorted(allowed_tools))}"
                            if allowed_tools
                            else "无白名单"
                        )
                        denied_info = (
                            f"拒绝工具: {', '.join(sorted(denied_tools))}"
                            if denied_tools
                            else "无拒绝列表"
                        )
                        default_info = "默认允许" if allow_by_default else "默认拒绝"
                        output = (
                            "已启用工具权限策略"
                            f"（{allowed_info}；{denied_info}；{default_info}）"
                        )
                    elif middleware_id == "tool_audit":
                        raw_max_records = middleware_config.get("max_records")
                        try:
                            max_records = int(raw_max_records or 10000)
                        except (TypeError, ValueError):
                            max_records = 10000
                        max_records = max(100, min(max_records, 100000))
                        task_state["tool_audit_store"] = InMemoryToolAuditStore(
                            max_records=max_records
                        )
                        workflow_runtime_context["active_middlewares"].append(
                            middleware_id
                        )
                        output = (
                            "已启用工具审计记录器"
                            f"（本次运行最多保留 {max_records} 条工具记录）"
                        )
                    elif middleware_id == "system_prompt_injector":
                        raw_system_prompt = str(
                            middleware_config.get("system_prompt")
                            or middleware_config.get("systemPrompt")
                            or ""
                        )
                        system_prompt = render_workflow_template(
                            raw_system_prompt,
                            variables,
                        ).strip()
                        override_system_prompt = middleware_config.get("override")
                        if isinstance(override_system_prompt, str):
                            override_system_prompt = (
                                override_system_prompt.lower() == "true"
                            )
                        else:
                            override_system_prompt = bool(override_system_prompt)
                        workflow_runtime_context["system_prompt"] = system_prompt
                        workflow_runtime_context["override_system_prompt"] = (
                            override_system_prompt
                        )
                        workflow_runtime_context["active_middlewares"].append(
                            middleware_id
                        )
                        output = (
                            "已启用系统提示词注入器。"
                            if system_prompt
                            else "系统提示词注入器未配置提示词，已跳过。"
                        )
                    else:
                        output = (
                            f"[原型节点] {title}（{middleware_kind} / {middleware_id}）"
                            "已跳过实际执行。"
                        )
                    yield sse_payload(
                        {
                            "event": "node_delta",
                            "node_id": node.id,
                            "node_title": title,
                            "node_type": kind,
                            "output": output,
                        }
                    )

                elif kind == "output":
                    output_variable = str(node.data.get("outputVariable") or "llm_output")
                    final_output = variables.get(output_variable, "")
                    task_state["final_output"] = final_output
                    output = final_output

                executed.add(node_id)
                yield sse_payload(
                    {
                        "event": "node_end",
                        "node_id": node.id,
                        "node_title": title,
                        "node_type": kind,
                        "output": output,
                        "variables": variables,
                    }
                )

                next_edges = outgoing[node_id]
                if kind == "condition":
                    matching_edges = [
                        edge for edge in next_edges if edge.sourceHandle == chosen_handle
                    ]
                    if not matching_edges:
                        matching_edges = [
                            edge for edge in next_edges if not edge.sourceHandle
                        ][:1]
                    next_edges = matching_edges

                for edge in sorted(next_edges, key=lambda item: order_index[item.target]):
                    if edge.target not in executed and edge.target not in queued:
                        queue.append(edge.target)
                        queued.add(edge.target)

            if not final_output:
                final_output = next(reversed(variables.values()), "")

            await run_registry.update_run(
                workflow_run.run_id,
                status="completed",
                metadata={
                    "final_output_length": len(final_output or ""),
                    "variables_count": len(variables),
                },
            )
            yield sse_payload(
                {
                    "event": "workflow_end",
                    "run_id": workflow_run.run_id,
                    "final_output": final_output,
                    "variables": variables,
                }
            )
        except Exception as exc:
            logger.exception("Workflow run failed workflow=%s", payload.workflow.id)
            try:
                await run_registry.update_run(
                    workflow_run.run_id,
                    status="failed",
                    error=str(exc),
                )
            except Exception:
                logger.warning("Failed to update workflow run status", exc_info=True)
            yield sse_payload({"event": "error", "message": str(exc)})
        finally:
            task_state["completed_at"] = time.monotonic()

    return StreamingResponse(
        workflow_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/workflow/run/{task_id}/resume")
async def resume_workflow_task(
    task_id: str,
    payload: WorkflowResumeRequest,
    request: Request,
):
    try:
        rate_limit_or_raise(client_ip(request))
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    task = get_workflow_task_or_none(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="工作流任务不存在或已过期。")

    paused_node_id = task.get("paused_node_id")
    if not paused_node_id:
        raise HTTPException(status_code=400, detail="工作流当前不在人工介入等待状态。")
    if payload.node_id and payload.node_id != paused_node_id:
        raise HTTPException(status_code=409, detail="人工介入节点不匹配，请刷新运行状态。")

    pause_event = task.get("pause_event")
    if not isinstance(pause_event, asyncio.Event):
        raise HTTPException(status_code=400, detail="工作流等待状态异常，无法继续。")

    task["resume_input"] = payload.input_text
    pause_event.set()
    return {"ok": True, "task_id": task_id, "node_id": paused_node_id}


@app.get("/api/workflow/run/{task_id}/status", response_model=WorkflowTaskStatusResponse)
async def get_workflow_task_status(task_id: str):
    task = get_workflow_task_or_none(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="工作流任务不存在或已过期。")
    created_at = float(task.get("created_at", time.monotonic()))
    ttl = float(task.get("ttl", WORKFLOW_TASK_TTL_SECONDS))
    ttl_seconds_left = max(0.0, ttl - (time.monotonic() - created_at))
    paused_node_id = task.get("paused_node_id")
    return WorkflowTaskStatusResponse(
        task_id=task_id,
        paused=bool(paused_node_id),
        paused_node_id=str(paused_node_id) if paused_node_id else None,
        created_at=created_at,
        ttl_seconds_left=ttl_seconds_left,
    )


@app.get("/api/workflow/runtime-events/{task_id}")
async def get_workflow_runtime_events(task_id: str):
    task = get_workflow_task_or_none(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="工作流任务不存在或已过期。")

    event_store = task.get("runtime_event_store")
    events: list[dict[str, Any]] = []
    if isinstance(event_store, RuntimeEventStore):
        event_list = await event_store.list_events(task_id=task_id)
        events = [
            {
                "id": event.id,
                "type": event.type,
                "payload": dict(event.payload or {}),
                "task_id": event.task_id,
                "trace_id": event.trace_id,
                "severity": event.severity,
                "created_at": event.created_at,
            }
            for event in event_list
        ]

    audit_store = task.get("tool_audit_store")
    if not isinstance(audit_store, InMemoryToolAuditStore):
        audit_store = workflow_tool_audit_store
    audit_records: list[dict[str, Any]] = []
    try:
        record_list = await audit_store.list_records()
        audit_records = [
            {
                "record_id": record.record_id,
                "tool_name": record.tool_name,
                "status": record.status,
                "started_at": record.started_at,
                "finished_at": record.finished_at,
                "duration_ms": record.duration_ms,
                "output_length": record.output_length,
                "content_types": record.content_types,
                "error": record.error,
            }
            for record in record_list
        ]
    except Exception as exc:
        logger.warning("Workflow runtime audit listing failed: %s", exc)

    return {
        "task_id": task_id,
        "events": events,
        "event_count": len(events),
        "tool_audit_records": audit_records,
        "tool_audit_count": len(audit_records),
    }


def runtime_run_to_payload(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "run_type": run.run_type,
        "status": run.status,
        "title": run.title,
        "source_id": run.source_id,
        "parent_run_id": run.parent_run_id,
        "metadata": dict(run.metadata or {}),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
        "cancelled_at": run.cancelled_at,
        "error": run.error,
    }


async def first_runtime_run_for_source(
    source_id: str,
    run_type: str,
) -> Any | None:
    runs = await run_registry.list_runs(
        run_type=run_type,  # type: ignore[arg-type]
        limit=200,
    )
    for run in runs:
        if run.source_id == source_id:
            return run
    return None


async def update_runtime_runs_for_source(
    source_id: str,
    run_type: str,
    *,
    status: str,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    runs = await run_registry.list_runs(
        run_type=run_type,  # type: ignore[arg-type]
        limit=200,
    )
    for run in runs:
        if run.source_id == source_id:
            await run_registry.update_run(
                run.run_id,
                status=status,  # type: ignore[arg-type]
                error=error,
                metadata=metadata,
            )


@app.get("/api/runtime/runs")
async def list_runtime_runs(
    run_type: str | None = None,
    status: str | None = None,
    limit: int = 50,
):
    valid_run_types = {"workflow", "agent_task", "agent_handoff"}
    valid_statuses = {"pending", "running", "completed", "failed", "cancelled"}
    if run_type is not None and run_type not in valid_run_types:
        raise HTTPException(status_code=400, detail="Invalid runtime run type.")
    if status is not None and status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid runtime run status.")
    runs = await run_registry.list_runs(
        run_type=run_type,  # type: ignore[arg-type]
        status=status,  # type: ignore[arg-type]
        limit=max(1, min(limit, 200)),
    )
    return [runtime_run_to_payload(run) for run in runs]


@app.get("/api/runtime/runs/{run_id}")
async def get_runtime_run(run_id: str):
    run = await run_registry.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Runtime run not found.")
    return runtime_run_to_payload(run)


@app.post("/api/runtime/runs/{run_id}/cancel")
async def cancel_runtime_run(run_id: str, payload: dict[str, Any] | None = None):
    reason = str((payload or {}).get("reason") or "cancelled")
    try:
        run = await run_registry.cancel_run(run_id, reason=reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Runtime run not found.") from exc
    return runtime_run_to_payload(run)


@app.post("/api/fusion/chat")
async def fusion_chat(payload: FusionChatRequest, request: Request):
    if not get_llm_gateway_config()[0]:
        return JSONResponse(
            status_code=500,
            content={"error": LLM_GATEWAY_NOT_CONFIGURED_MESSAGE},
        )

    try:
        rate_limit_or_raise(client_ip(request))
        validate_content(payload.messages)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    async def fusion_stream():
        yield sse_payload(
            {
                "event": "fusion_meta",
                "native": payload.use_native_fusion,
                "model_ids": payload.model_ids,
                "judge_model_id": payload.judge_model_id,
                "note": "OpenRouter Fusion Router 为 Beta 能力；如原生调用失败，将自动切换到应用层并行裁判融合。",
            }
        )

        native_text = ""
        if payload.use_native_fusion:
            try:
                yield sse_payload(
                    {
                        "event": "fusion_stage",
                        "stage": "native_start",
                        "message": "正在启动原生 Fusion 会诊室...",
                    }
                )
                async for delta in try_native_fusion_stream(payload):
                    native_text += delta
                    yield sse_payload({"event": "fusion_delta", "output": delta})
                if not native_text.strip():
                    raise RuntimeError("原生 Fusion 未返回正文。")
                yield sse_payload(
                    {
                        "event": "fusion_end",
                        "mode": "native",
                        "final_output": native_text,
                    }
                )
                return
            except Exception as exc:
                logger.warning("Native fusion failed; falling back to app fusion: %s", exc)
                if native_text.strip():
                    yield sse_payload(
                        {
                            "event": "fusion_end",
                            "mode": "native_partial",
                            "final_output": native_text,
                            "warning": f"原生 Fusion 中途结束：{exc}",
                        }
                    )
                    return
                yield sse_payload(
                    {
                        "event": "fusion_stage",
                        "stage": "native_failed",
                        "message": f"原生 Fusion 暂不可用，切换到本地并行裁判：{exc}",
                    }
                )

        last_user_question = next(
            (
                message_text(message.content)
                for message in reversed(payload.messages)
                if message.role == "user"
            ),
            "",
        )
        answers: list[dict[str, str]] = []

        async def collect_for_model(model_id: str) -> dict[str, str]:
            try:
                answer = await collect_chat_completion_text(
                    model_id,
                    payload.messages,
                    temperature=payload.temperature,
                    max_tokens=payload.max_tokens,
                )
                return {"model_id": model_id, "answer": answer, "error": ""}
            except Exception as exc:
                logger.warning("Fusion candidate failed model=%s error=%s", model_id, exc)
                return {"model_id": model_id, "answer": "", "error": str(exc)}

        tasks = [asyncio.create_task(collect_for_model(model_id)) for model_id in payload.model_ids]
        for model_id in payload.model_ids:
            yield sse_payload({"event": "model_start", "model_id": model_id})

        for task in asyncio.as_completed(tasks):
            result = await task
            if result["error"]:
                yield sse_payload(
                    {
                        "event": "model_error",
                        "model_id": result["model_id"],
                        "message": result["error"],
                    }
                )
            else:
                answers.append(result)
                yield sse_payload(
                    {
                        "event": "model_end",
                        "model_id": result["model_id"],
                        "output": result["answer"],
                    }
                )

        if not answers:
            yield sse_payload({"event": "error", "message": "所有候选模型都未能返回结果。"})
            return

        judge_prompt = fusion_judge_prompt(last_user_question, answers)
        judge_messages = [ChatMessage(role="user", content=judge_prompt)]
        final_output = ""
        yield sse_payload(
            {
                "event": "fusion_stage",
                "stage": "judge_start",
                "message": "候选答案已收齐，裁判模型正在合并共识...",
            }
        )
        try:
            async for delta in stream_text_with_model_fallback(
                payload.judge_model_id,
                judge_messages,
                temperature=0.35,
                max_tokens=payload.max_tokens,
            ):
                final_output += delta
                yield sse_payload({"event": "fusion_delta", "output": delta})
        except Exception as exc:
            logger.exception("Fusion judge failed")
            yield sse_payload({"event": "error", "message": str(exc)})
            return

        if not final_output.strip():
            final_output = (
                "裁判模型本轮未返回正文，已保留候选模型中最完整的一份答案供参考：\n\n"
                + max(answers, key=lambda item: len(item["answer"]))["answer"]
            )
            yield sse_payload({"event": "fusion_delta", "output": final_output})

        yield sse_payload(
            {
                "event": "fusion_end",
                "mode": "application",
                "final_output": final_output,
            }
        )

    return StreamingResponse(
        fusion_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/route-agent")
async def route_agent(payload: RouteAgentRequest, request: Request):
    if not get_llm_gateway_config()[0]:
        return JSONResponse(
            status_code=500,
            content={"error": LLM_GATEWAY_NOT_CONFIGURED_MESSAGE},
        )
    if not AGENT_RECORDS:
        return JSONResponse(status_code=500, content={"error": "智能体索引尚未生成。"})

    try:
        rate_limit_or_raise(client_ip(request))
        validate_plain_message(payload.message)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    matches = match_agents(payload.message, payload.top_k)
    selected_agent = matches[0][0]
    agent_messages = [
        agent_system_message(selected_agent),
        ChatMessage(role="user", content=payload.message),
    ]

    async def route_stream():
        yield sse_payload(
            {
                "event": "route_result",
                "matches": [
                    agent_public_payload(agent, score) for agent, score in matches
                ],
                "selected_agent_id": selected_agent.id,
            }
        )

        output = ""
        try:
            async for delta in stream_text_with_model_fallback(
                payload.model_id,
                agent_messages,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            ):
                output += delta
                yield sse_payload(
                    {
                        "event": "answer_delta",
                        "agent_id": selected_agent.id,
                        "output": delta,
                    }
                )
        except Exception as exc:
            logger.exception("Route-agent response failed")
            yield sse_payload({"event": "error", "message": str(exc)})
            return

        if not output.strip():
            output = "专家已匹配，但当前模型未返回正文。请换一个执行模型或稍后重试。"
            yield sse_payload(
                {
                    "event": "answer_delta",
                    "agent_id": selected_agent.id,
                    "output": output,
                }
            )

        yield sse_payload(
            {
                "event": "answer_end",
                "agent": agent_public_payload(selected_agent),
                "final_output": output,
            }
        )

    return StreamingResponse(
        route_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/team/chat")
async def team_chat(payload: TeamChatRequest, request: Request):
    if not get_llm_gateway_config()[0]:
        return JSONResponse(
            status_code=500,
            content={"error": LLM_GATEWAY_NOT_CONFIGURED_MESSAGE},
        )

    try:
        rate_limit_or_raise(client_ip(request))
        validate_plain_message(payload.message)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc.detail)})

    members: list[tuple[AgentRecord, str]] = []
    missing_ids: list[str] = []
    for member in payload.members:
        agent = AGENTS_BY_ID.get(member.agent_id)
        if not agent:
            missing_ids.append(member.agent_id)
            continue
        members.append((agent, member.task or "请基于你的专业视角完成本轮协作。"))

    if missing_ids:
        return JSONResponse(
            status_code=400,
            content={"error": f"未找到智能体：{', '.join(missing_ids)}"},
        )
    if not members:
        return JSONResponse(status_code=400, content={"error": "请至少选择一位专家。"})

    async def team_stream():
        yield sse_payload(
            {
                "event": "team_start",
                "mode": payload.mode,
                "members": [agent_public_payload(agent) for agent, _ in members],
            }
        )

        prior_outputs: list[dict[str, str]] = []
        try:
            for index, (agent, task) in enumerate(members, start=1):
                yield sse_payload(
                    {
                        "event": "agent_start",
                        "agent": agent_public_payload(agent),
                        "step": index,
                        "task": task,
                    }
                )
                if payload.mode == "debate":
                    user_prompt = (
                        f"团队任务：{payload.message}\n\n"
                        f"你的独立发言任务：{task}\n"
                        "请先给出你的专业判断，不要假设你已看到其他专家的意见。"
                    )
                else:
                    previous = "\n\n".join(
                        f"### {item['agent_name']} 的上一棒意见\n{item['output']}"
                        for item in prior_outputs
                    )
                    user_prompt = (
                        f"团队总任务：{payload.message}\n\n"
                        f"你的接力任务：{task}\n\n"
                        f"前序专家输出：\n{previous or '暂无，你是第一棒。'}\n\n"
                        "请基于自己的专业角色补充、纠偏并推进到下一步。"
                    )

                messages = [
                    agent_system_message(agent, task),
                    ChatMessage(role="user", content=user_prompt),
                ]
                output = ""
                async for delta in stream_text_with_model_fallback(
                    payload.model_id,
                    messages,
                    temperature=payload.temperature,
                    max_tokens=payload.max_tokens,
                ):
                    output += delta
                    yield sse_payload(
                        {
                            "event": "agent_delta",
                            "agent_id": agent.id,
                            "output": delta,
                        }
                    )
                if not output.strip():
                    output = "该专家本轮没有收到可用模型正文，建议换一个模型后重试。"
                    yield sse_payload(
                        {
                            "event": "agent_delta",
                            "agent_id": agent.id,
                            "output": output,
                        }
                    )
                prior_outputs.append(
                    {
                        "agent_id": agent.id,
                        "agent_name": agent.name,
                        "department": agent.department,
                        "output": output,
                    }
                )
                yield sse_payload(
                    {
                        "event": "agent_end",
                        "agent": agent_public_payload(agent),
                        "output": output,
                    }
                )

            summary_prompt = "\n\n".join(
                f"### {item['agent_name']}（{item['department']}）\n{item['output']}"
                for item in prior_outputs
            )
            summary_messages = [
                ChatMessage(
                    role="system",
                    content=(
                        "你是模镜专家团的项目经理。请整合多个专家的意见，"
                        "输出一份可执行、去重、分优先级的最终方案。"
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"用户任务：{payload.message}\n\n"
                        f"专家意见如下：\n{summary_prompt}\n\n"
                        "请给出团队综合意见、执行清单、风险提醒和下一步建议。"
                    ),
                ),
            ]
            final_output = ""
            yield sse_payload(
                {
                    "event": "summary_start",
                    "message": "专家接力完成，项目经理正在汇总最终方案...",
                }
            )
            async for delta in stream_text_with_model_fallback(
                payload.model_id,
                summary_messages,
                temperature=0.45,
                max_tokens=payload.max_tokens,
            ):
                final_output += delta
                yield sse_payload({"event": "summary_delta", "output": delta})
            if not final_output.strip():
                final_output = "团队流程已完成，但汇总模型未返回正文。请换一个模型或稍后重试。"
                yield sse_payload({"event": "summary_delta", "output": final_output})

            yield sse_payload(
                {
                    "event": "team_end",
                    "final_output": final_output,
                    "agent_outputs": prior_outputs,
                }
            )
        except Exception as exc:
            logger.exception("Team chat failed")
            yield sse_payload({"event": "error", "message": str(exc)})

    return StreamingResponse(
        team_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.on_event("startup")
async def start_mcp_ttl_cleanup() -> None:
    mcp_manager.start_ttl_cleanup(on_cleanup=tool_registry.unregister_sessions)


@app.on_event("shutdown")
async def shutdown_mcp_sessions() -> None:
    await mcp_manager.stop_ttl_cleanup()
    await mcp_manager.close_all()
    await tool_registry.clear()


@app.post("/api/mcp/connect", response_model=MCPConnectResponse)
async def connect_mcp_server(payload: MCPConnectRequest, request: Request):
    try:
        mcp_connect_rate_limit_or_raise(client_ip(request))
        validate_server_command(payload.server_command)
        await cleanup_mcp_idle_sessions_and_registry()
        session_id = await mcp_manager.connect(payload.server_command)
        tools = await mcp_manager.list_tools(session_id)
        await tool_registry.register_session_tools(
            session_id=session_id,
            server_id=mcp_server_id_from_command(payload.server_command),
            tools=tools,
        )
        return MCPConnectResponse(session_id=session_id, tools_count=len(tools))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("MCP connect failed")
        raise HTTPException(status_code=400, detail=f"MCP Server 启动失败：{exc}") from exc


@app.post("/api/mcp/install", response_model=MCPInstallResponse)
async def install_mcp_project(payload: MCPInstallRequest):
    try:
        result = await asyncio.to_thread(
            mcp_installer.install,
            project_id=payload.project_id,
            install_command=payload.install_command,
            server_command=payload.server_command,
        )
        return MCPInstallResponse.model_validate(result)
    except (MCPInstallError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("MCP install failed project=%s", payload.project_id)
        raise HTTPException(status_code=500, detail=f"MCP 安装失败：{exc}") from exc


@app.get("/api/mcp/installed", response_model=MCPInstalledResponse)
async def list_installed_mcp_projects():
    return MCPInstalledResponse(installed=mcp_installer.list_installed())


@app.get("/api/mcp/sessions", response_model=MCPSessionsResponse)
async def list_mcp_sessions():
    await cleanup_mcp_idle_sessions_and_registry()
    return MCPSessionsResponse(
        sessions=[
            MCPSessionSummary.model_validate(summary)
            for summary in await mcp_manager.get_sessions_summary()
        ]
    )


@app.get("/api/registry/tools", response_model=RegistryToolsResponse)
async def list_registered_tools():
    await cleanup_mcp_idle_sessions_and_registry()
    return RegistryToolsResponse(
        tools=[
            RegistryToolPayload.model_validate(tool)
            for tool in await tool_registry.list_tools()
        ]
    )


@app.post("/api/runtime/agent-tasks")
async def create_agent_task(payload: dict[str, Any]):
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Agent task title is required.")
    input_text = str(payload.get("input") or "")
    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Agent task metadata must be an object.")
    task = await agent_task_store.create_task(
        title=title,
        input_text=input_text,
        source_agent=payload.get("source_agent"),
        assigned_agent=payload.get("assigned_agent"),
        metadata=metadata,
    )
    await run_registry.create_run(
        "agent_task",
        task.title,
        status="pending",
        source_id=task.task_id,
        parent_run_id=(
            str(metadata.get("parent_run_id"))
            if isinstance(metadata, dict) and metadata.get("parent_run_id")
            else None
        ),
        metadata={
            **dict(metadata or {}),
            "agent_task_id": task.task_id,
            "source_agent": task.source_agent,
            "assigned_agent": task.assigned_agent,
        },
    )
    return {
        "task_id": task.task_id,
        "title": task.title,
        "status": task.status,
        "created_at": task.created_at,
    }


def agent_handoff_to_payload(handoff: Any) -> dict[str, Any]:
    return {
        "handoff_id": handoff.handoff_id,
        "task_id": handoff.task_id,
        "source_agent": handoff.source_agent,
        "target_agent": handoff.target_agent,
        "reason": handoff.reason,
        "status": handoff.status,
        "metadata": handoff.metadata,
        "created_at": handoff.created_at,
        "updated_at": handoff.updated_at,
    }


@app.get("/api/runtime/agent-tasks")
async def list_agent_tasks(status: str | None = None, limit: int = 50):
    valid_statuses = {"pending", "running", "completed", "failed", "cancelled"}
    if status is not None and status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid agent task status.")
    tasks = await agent_task_store.list_tasks(
        status=status,  # type: ignore[arg-type]
        limit=max(1, min(limit, 200)),
    )
    return [
        {
            "task_id": task.task_id,
            "title": task.title,
            "status": task.status,
            "assigned_agent": task.assigned_agent,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
        for task in tasks
    ]


@app.post("/api/runtime/agent-tasks/{task_id}/handoffs")
async def create_agent_handoff(task_id: str, payload: dict[str, Any]):
    task = await agent_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found.")
    target_agent = str(
        payload.get("target_agent") or payload.get("targetAgent") or ""
    ).strip()
    if not target_agent:
        raise HTTPException(status_code=400, detail="Handoff target_agent is required.")
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Handoff reason is required.")
    source_agent = str(
        payload.get("source_agent")
        or payload.get("sourceAgent")
        or task.assigned_agent
        or task.source_agent
        or "workflow"
    ).strip()
    metadata = payload.get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Handoff metadata must be an object.")
    handoff = await agent_task_store.create_handoff(
        task_id,
        source_agent=source_agent or "workflow",
        target_agent=target_agent,
        reason=reason,
        metadata=metadata,
    )
    task_run = await first_runtime_run_for_source(task_id, "agent_task")
    await run_registry.create_run(
        "agent_handoff",
        f"{source_agent or 'workflow'} -> {target_agent}",
        status="pending",
        source_id=handoff.handoff_id,
        parent_run_id=(
            str(metadata.get("parent_run_id"))
            if isinstance(metadata, dict) and metadata.get("parent_run_id")
            else (task_run.run_id if task_run else None)
        ),
        metadata={
            **dict(metadata or {}),
            "agent_task_id": task_id,
            "handoff_id": handoff.handoff_id,
            "source_agent": handoff.source_agent,
            "target_agent": handoff.target_agent,
        },
    )
    return agent_handoff_to_payload(handoff)


@app.get("/api/runtime/agent-tasks/{task_id}/handoffs")
async def list_agent_handoffs(task_id: str):
    task = await agent_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found.")
    handoffs = await agent_task_store.list_handoffs(task_id=task_id)
    return [agent_handoff_to_payload(handoff) for handoff in handoffs]


@app.get("/api/runtime/agent-tasks/{task_id}")
async def get_agent_task(task_id: str):
    task = await agent_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found.")
    return {
        "task_id": task.task_id,
        "title": task.title,
        "input": task.input,
        "status": task.status,
        "result": task.result,
        "error": task.error,
        "source_agent": task.source_agent,
        "assigned_agent": task.assigned_agent,
        "metadata": task.metadata,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
    }


async def update_agent_handoff_api(
    handoff_id: str,
    status: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = (payload or {}).get("metadata")
    if metadata is not None and not isinstance(metadata, dict):
        raise HTTPException(status_code=400, detail="Handoff metadata must be an object.")
    merged_metadata = dict(metadata or {})
    reason = (payload or {}).get("reason")
    if reason is not None:
        merged_metadata["reason"] = str(reason)
    result = (payload or {}).get("result")
    if result is not None:
        merged_metadata["result"] = str(result)
    try:
        handoff = await agent_task_store.update_handoff_status(
            handoff_id,
            status,  # type: ignore[arg-type]
            metadata=merged_metadata or None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent handoff not found.") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    registry_status = {
        "accepted": "running",
        "rejected": "failed",
        "completed": "completed",
    }.get(status)
    if registry_status is not None:
        await update_runtime_runs_for_source(
            handoff_id,
            "agent_handoff",
            status=registry_status,  # type: ignore[arg-type]
            error=(
                str(merged_metadata.get("reason") or "")
                if status == "rejected"
                else None
            ),
            metadata={
                "handoff_status": status,
                **merged_metadata,
            },
        )
    return agent_handoff_to_payload(handoff)


@app.post("/api/runtime/agent-handoffs/{handoff_id}/accept")
async def accept_agent_handoff(
    handoff_id: str,
    payload: dict[str, Any] | None = None,
):
    return await update_agent_handoff_api(handoff_id, "accepted", payload)


@app.post("/api/runtime/agent-handoffs/{handoff_id}/reject")
async def reject_agent_handoff(
    handoff_id: str,
    payload: dict[str, Any] | None = None,
):
    return await update_agent_handoff_api(handoff_id, "rejected", payload)


@app.post("/api/runtime/agent-handoffs/{handoff_id}/complete")
async def complete_agent_handoff(
    handoff_id: str,
    payload: dict[str, Any] | None = None,
):
    return await update_agent_handoff_api(handoff_id, "completed", payload)


@app.post("/api/runtime/agent-tasks/{task_id}/cancel")
async def cancel_agent_task(task_id: str, payload: dict[str, Any] | None = None):
    task = await agent_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found.")
    reason = str((payload or {}).get("reason") or "cancelled")
    cancelled = await agent_task_store.cancel_task(task_id, reason=reason)
    await update_runtime_runs_for_source(
        task_id,
        "agent_task",
        status="cancelled",
        error=reason,
        metadata={"cancel_reason": reason},
    )
    return {
        "task_id": cancelled.task_id,
        "status": cancelled.status,
        "error": cancelled.error,
        "updated_at": cancelled.updated_at,
    }


@app.get("/api/runtime/middleware-nodes", response_model=list[dict[str, Any]])
async def list_runtime_middleware_nodes():
    """Return runtime middleware node metadata for the canvas palette."""

    return [asdict(node) for node in runtime_middleware_registry.list()]


@app.get("/api/mcp/{session_id}/tools", response_model=MCPToolsResponse)
async def list_mcp_tools(session_id: str):
    try:
        tools = await mcp_manager.list_tools(session_id)
        summary = {
            item["session_id"]: item
            for item in await mcp_manager.get_sessions_summary()
        }.get(session_id)
        if summary:
            await tool_registry.register_session_tools(
                session_id=session_id,
                server_id=mcp_server_id_from_command(summary["server_command"]),
                tools=tools,
            )
        return MCPToolsResponse(tools=[serialize_mcp_tool(tool) for tool in tools])
    except MCPSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="MCP session 不存在或已断开。") from exc
    except Exception as exc:
        logger.exception("MCP list tools failed session=%s", session_id)
        raise HTTPException(status_code=500, detail=f"获取 MCP 工具列表失败：{exc}") from exc


@app.post("/api/mcp/{session_id}/call", response_model=MCPCallResponse)
async def call_mcp_tool(session_id: str, payload: MCPCallRequest):
    try:
        result = await mcp_manager.call_tool(
            session_id,
            payload.tool_name,
            payload.arguments,
        )
        return serialize_mcp_call_result(result)
    except MCPSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="MCP session 不存在或已断开。") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("MCP tool call failed session=%s tool=%s", session_id, payload.tool_name)
        raise HTTPException(status_code=500, detail=f"MCP 工具调用失败：{exc}") from exc


@app.delete("/api/mcp/{session_id}")
async def disconnect_mcp_server(session_id: str):
    try:
        await mcp_manager.disconnect(session_id)
        await tool_registry.unregister_session(session_id)
        return {"ok": True}
    except MCPSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="MCP session 不存在或已断开。") from exc
    except MCPClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    url, key = get_llm_gateway_config()
    if not url:
        return JSONResponse(
            status_code=500,
            content={"error": LLM_GATEWAY_NOT_CONFIGURED_MESSAGE},
        )

    try:
        rate_limit_or_raise(client_ip(request))
        validate_multimodal_content(payload.model_id, payload.messages)
        validate_content(payload.messages)
    except HTTPException as exc:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": str(exc.detail)},
        )
    except Exception:
        logger.exception("Chat request validation failed")
        return JSONResponse(
            status_code=500,
            content={"error": "后端校验请求时出错，请查看服务日志。"},
        )

    runtime_pipeline = None
    runtime_context = None
    runtime_task_id = uuid.uuid4().hex
    try:
        runtime_pipeline, runtime_context = create_default_runtime()
        runtime_context.task_id = runtime_task_id
        runtime_context.trace_id = request.headers.get("x-trace-id") or runtime_task_id
        runtime_context.metadata = {
            "model_id": payload.model_id,
            "message_count": len(payload.messages),
        }
        system_prompt = request.headers.get("x-system-prompt", "").strip()
        if system_prompt:
            runtime_context.metadata["system_prompt"] = system_prompt
        await runtime_pipeline.before_agent(
            {
                "model_id": payload.model_id,
                "messages": chat_messages_json(payload.messages),
            },
            runtime_context,
        )
    except Exception as exc:
        runtime_pipeline = None
        runtime_context = None
        logger.warning("Xpert runtime chat setup failed; falling back direct path: %s", exc)

    client = httpx.AsyncClient(**llm_client_kwargs())
    actual_model_id = payload.model_id
    fallback_notice = ""

    async def finalize_runtime(
        status: str,
        model_id: str,
        text: str = "",
        error: str | None = None,
    ) -> None:
        if runtime_pipeline is None or runtime_context is None:
            return
        try:
            await runtime_pipeline.after_model(
                ModelCallResponse(
                    text=text,
                    metadata={
                        "model_id": model_id,
                        "status": status,
                        "error": error,
                    },
                ),
                runtime_context,
            )
            await runtime_pipeline.after_agent(
                {
                    "model_id": model_id,
                    "messages": chat_messages_json(payload.messages),
                    "status": status,
                    "error": error,
                },
                runtime_context,
            )
        except Exception as exc:
            logger.warning("Xpert runtime chat finalize failed: %s", exc)

    async def send_prepared_to_upstream(
        model_id: str,
        request_payload: dict[str, Any],
        *,
        gateway_url: str = url,
        gateway_key: str = key,
    ) -> httpx.Response:
        logger.info("Sending chat request to model=%s gateway=%s", model_id, gateway_url)
        return await client.send(
            client.build_request(
                "POST",
                gateway_url,
                headers=llm_gateway_headers(gateway_key),
                json=request_payload,
            ),
            stream=True,
        )

    async def send_to_upstream(
        model_id: str,
        *,
        gateway_url: str = url,
        gateway_key: str = key,
    ) -> httpx.Response:
        request_payload = build_upstream_payload(payload, model_id)
        if runtime_pipeline is None or runtime_context is None:
            return await send_prepared_to_upstream(
                model_id,
                request_payload,
                gateway_url=gateway_url,
                gateway_key=gateway_key,
            )

        handler_started = False
        try:
            runtime_request = ModelCallRequest(
                model_id=model_id,
                messages=chat_messages_json(payload.messages),
                params={
                    "temperature": payload.temperature,
                    "top_p": payload.top_p,
                    "max_tokens": payload.max_tokens,
                    "seed": payload.seed,
                    "stop": payload.stop,
                    "stream": True,
                },
            )
            prepared = await runtime_pipeline.before_model(runtime_request, runtime_context)
            runtime_payload = payload.model_copy(
                update={
                    "messages": [
                        ChatMessage.model_validate(message)
                        for message in prepared.messages
                    ]
                }
            )
            request_payload = build_upstream_payload(runtime_payload, model_id)

            async def runtime_model_handler(
                request_for_model: ModelCallRequest,
            ) -> ModelCallResponse:
                nonlocal handler_started
                handler_started = True
                upstream_response = await send_prepared_to_upstream(
                    request_for_model.model_id,
                    request_payload,
                    gateway_url=gateway_url,
                    gateway_key=gateway_key,
                )
                return ModelCallResponse(
                    text="",
                    raw=upstream_response,
                    metadata={"model_id": request_for_model.model_id, "streaming": True},
                )

            wrapped_response = await runtime_pipeline.wrap_model_call(
                prepared,
                runtime_model_handler,
                runtime_context,
            )
            if isinstance(wrapped_response.raw, httpx.Response):
                return wrapped_response.raw
            logger.warning("Xpert runtime model wrapper returned no upstream response.")
        except Exception as exc:
            if handler_started:
                raise
            logger.warning("Xpert runtime chat prepare failed; using direct path: %s", exc)

        return await send_prepared_to_upstream(
            model_id,
            request_payload,
            gateway_url=gateway_url,
            gateway_key=gateway_key,
        )

    try:
        response = await send_to_upstream(actual_model_id)
    except httpx.TimeoutException:
        logger.exception("OpenRouter request timed out model=%s", actual_model_id)
        await finalize_runtime("error", actual_model_id, error="timeout")
        await client.aclose()
        return JSONResponse(status_code=504, content={"error": "模型响应超时，请稍后重试。"})
    except httpx.HTTPError as exc:
        logger.exception("OpenRouter connection failed model=%s error=%s", actual_model_id, exc)
        await finalize_runtime("error", actual_model_id, error=str(exc))
        await client.aclose()
        return JSONResponse(status_code=502, content={"error": "模型服务暂时无法连接，请检查网络或代理配置。"})
    except Exception:
        logger.exception("Unexpected error before upstream stream model=%s", actual_model_id)
        await finalize_runtime("error", actual_model_id, error="unexpected upstream error")
        await client.aclose()
        return JSONResponse(status_code=500, content={"error": "后端代理请求时出错，请查看服务日志。"})

    if response.status_code >= 400:
        body = await response.aread()
        await response.aclose()
        message, data = parse_upstream_error(response.status_code, body)
        logger.warning(
            "OpenRouter error status=%s model=%s message=%s body=%s",
            response.status_code,
            actual_model_id,
            message,
            body[:500].decode("utf-8", errors="replace"),
        )

        if should_fallback_gateway_to_openrouter(
            response.status_code,
            message,
            data,
            url,
        ):
            try:
                response = await send_to_upstream(
                    actual_model_id,
                    gateway_url=CHAT_COMPLETIONS_URL,
                    gateway_key=OPENROUTER_API_KEY,
                )
                fallback_notice = (
                    "提示：本地 newAPI 当前不可用，已自动切换到 OpenRouter 继续回答。\n\n"
                )
            except httpx.TimeoutException:
                logger.exception("OpenRouter gateway fallback timed out model=%s", actual_model_id)
                await finalize_runtime("error", actual_model_id, error="gateway fallback timeout")
                await client.aclose()
                return JSONResponse(
                    status_code=504,
                    content={"error": "OpenRouter 兜底模型响应超时，请稍后重试。"},
                )
            except httpx.HTTPError as exc:
                logger.exception(
                    "OpenRouter gateway fallback connection failed model=%s error=%s",
                    actual_model_id,
                    exc,
                )
                await finalize_runtime("error", actual_model_id, error=str(exc))
                await client.aclose()
                return JSONResponse(
                    status_code=502,
                    content={"error": "本地 newAPI 当前不可用，OpenRouter 兜底也暂时无法连接。"},
                )

            if response.status_code >= 400:
                fallback_body = await response.aread()
                await response.aclose()
                fallback_message, _ = parse_upstream_error(
                    response.status_code,
                    fallback_body,
                )
                await finalize_runtime("error", actual_model_id, error=fallback_message)
                await client.aclose()
                return JSONResponse(
                    status_code=response.status_code,
                    content={
                        "error": (
                            "本地 newAPI 当前不可用；OpenRouter 兜底也暂不可用："
                            f"{fallback_message}"
                        )
                    },
                )

        if response.status_code >= 400 and should_fallback_model(
            response.status_code,
            message,
            data,
            actual_model_id,
            payload.messages,
        ):
            fallback_model_id = fallback_model_for(payload.messages)
            if any(message_has_image(message.content) for message in payload.messages) and not model_supports_image_input(fallback_model_id):
                await finalize_runtime(
                    "error",
                    actual_model_id,
                    error="no multimodal fallback model",
                )
                await client.aclose()
                return JSONResponse(
                    status_code=response.status_code,
                    content={"error": "该模型在当前地区暂不可用，且当前图片请求没有可用的多模态兜底模型。"},
                )

            try:
                response = await send_to_upstream(fallback_model_id)
                actual_model_id = fallback_model_id
                fallback_notice = (
                    f"提示：原模型暂不可用，已自动切换为 {fallback_model_id} 为您回答。\n\n"
                )
            except httpx.TimeoutException:
                logger.exception("Fallback model timed out model=%s", fallback_model_id)
                await finalize_runtime("error", fallback_model_id, error="fallback timeout")
                await client.aclose()
                return JSONResponse(status_code=504, content={"error": "兜底模型响应超时，请稍后重试。"})
            except httpx.HTTPError as exc:
                logger.exception("Fallback model connection failed model=%s error=%s", fallback_model_id, exc)
                await finalize_runtime("error", fallback_model_id, error=str(exc))
                await client.aclose()
                return JSONResponse(status_code=502, content={"error": "当前模型和兜底模型都暂时无法连接。"})

            if response.status_code >= 400:
                fallback_body = await response.aread()
                await response.aclose()
                await client.aclose()
                fallback_message, _ = parse_upstream_error(response.status_code, fallback_body)
                await finalize_runtime("error", fallback_model_id, error=fallback_message)
                logger.warning(
                    "Fallback model also failed status=%s model=%s message=%s",
                    response.status_code,
                    fallback_model_id,
                    fallback_message,
                )
                return JSONResponse(
                    status_code=response.status_code,
                    content={"error": f"{message}；兜底模型也暂不可用：{fallback_message}"},
                )
        elif response.status_code >= 400:
            await finalize_runtime("error", actual_model_id, error=message)
            await client.aclose()
            return JSONResponse(
                status_code=response.status_code,
                content={"error": message},
            )

    async def stream_response():
        buffer = ""
        accumulated_chunks: list[str] = []
        runtime_status = "completed"
        runtime_error: str | None = None
        try:
            if fallback_notice:
                payload_json = json.dumps(
                    {"choices": [{"delta": {"content": fallback_notice}}]},
                    ensure_ascii=False,
                )
                accumulated_chunks.append(fallback_notice)
                yield f"data: {payload_json}\n\n".encode("utf-8")

            async for chunk in response.aiter_text():
                if not chunk:
                    continue

                buffer += chunk
                lines = buffer.splitlines(keepends=True)
                if buffer.endswith("\n") or buffer.endswith("\r"):
                    complete_lines = lines
                    buffer = ""
                else:
                    complete_lines = lines[:-1]
                    buffer = lines[-1] if lines else buffer

                for line in complete_lines:
                    if line.lstrip().startswith(":"):
                        continue
                    accumulated_chunks.extend(sse_delta_text(line))
                    yield line.encode("utf-8")
                await asyncio.sleep(0)
        except httpx.HTTPError:
            runtime_status = "error"
            runtime_error = "stream interrupted"
            logger.exception("OpenRouter stream interrupted model=%s", actual_model_id)
            yield (
                'data: {"error":{"message":"模型服务连接中断，请稍后重试。"}}\n\n'
            ).encode("utf-8")
        except Exception:
            runtime_status = "error"
            runtime_error = "stream proxy failed"
            logger.exception("Unexpected stream error model=%s", actual_model_id)
            yield (
                'data: {"error":{"message":"后端转发流式响应时出错，请查看服务日志。"}}\n\n'
            ).encode("utf-8")
        finally:
            if buffer and not buffer.lstrip().startswith(":"):
                accumulated_chunks.extend(sse_delta_text(buffer))
                yield buffer.encode("utf-8")
            await response.aclose()
            await client.aclose()
            await finalize_runtime(
                runtime_status,
                actual_model_id,
                "".join(accumulated_chunks),
                runtime_error,
            )

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-ModelMirror-Actual-Model": actual_model_id,
        },
    )
