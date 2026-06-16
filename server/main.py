import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncIterator
from collections import defaultdict, deque
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
    from server.mcp.manager import (
        MCPClientError,
        MCPClientManager,
        MCPSessionNotFoundError,
        validate_server_command,
    )
except ModuleNotFoundError:
    from mcp.manager import (
        MCPClientError,
        MCPClientManager,
        MCPSessionNotFoundError,
        validate_server_command,
    )

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"
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

request_windows: dict[str, deque[float]] = defaultdict(deque)
mcp_connect_windows: dict[str, deque[float]] = defaultdict(deque)
mcp_manager = MCPClientManager()


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


class MCPToolPayload(BaseModel):
    name: str
    description: str | None = None
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class MCPToolsResponse(BaseModel):
    tools: list[MCPToolPayload]


class MCPCallRequest(BaseModel):
    tool_name: str = Field(min_length=1, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPCallResponse(BaseModel):
    content: list[dict[str, Any]] = Field(default_factory=list)
    is_error: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


WorkflowNodeType = Literal["input", "llm", "condition", "code", "output"]


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
            if "not available in your region" in lowered:
                return "当前模型在本地区暂不可用，请返回列表选择其他模型。"
            if "invalid api key" in lowered or "no auth credentials" in lowered:
                return "服务认证失败，请检查后端密钥配置。"
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


def openrouter_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": APP_REFERER,
        "X-Title": APP_TITLE,
        "X-OpenRouter-Title": APP_TITLE,
    }


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


def openrouter_client_kwargs() -> dict[str, Any]:
    timeout = httpx.Timeout(connect=15, read=None, write=30, pool=10)
    client_kwargs: dict[str, Any] = {"timeout": timeout}
    proxy = proxy_url()
    if proxy:
        client_kwargs["proxy"] = proxy
    return client_kwargs


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
    request_payload = build_chat_payload_from_messages(
        model_id,
        messages,
        stream=False,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    async with httpx.AsyncClient(**openrouter_client_kwargs()) as client:
        response = await client.post(
            CHAT_COMPLETIONS_URL,
            headers=openrouter_headers(),
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
    request_payload = build_chat_payload_from_messages(
        model_id,
        messages,
        stream=True,
        temperature=temperature,
        max_tokens=max_tokens,
        extra=extra,
    )

    async with httpx.AsyncClient(**openrouter_client_kwargs()) as client:
        response = await client.send(
            client.build_request(
                "POST",
                CHAT_COMPLETIONS_URL,
                headers=openrouter_headers(),
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
                    delta = sse_delta_text(event)
                    if delta:
                        yield delta
        finally:
            await response.aclose()

        if buffer.strip():
            delta = sse_delta_text(buffer)
            if delta:
                yield delta


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
    if data_kind in {"input", "llm", "condition", "code", "output"}:
        return data_kind  # type: ignore[return-value]
    if node.type:
        return node.type
    raise HTTPException(status_code=400, detail=f"节点 {node.id} 缺少有效类型。")


def workflow_node_title(node: WorkflowNodePayload) -> str:
    title = node.data.get("title")
    return str(title) if isinstance(title, str) and title.strip() else node.id


def sse_payload(data: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode("utf-8")


def render_workflow_template(template: str, variables: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1).strip()
        return variables.get(variable_name, "")

    return re.sub(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}", replace, template)


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


def sse_delta_text(event_text: str) -> str:
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
        content = ""
        if isinstance(delta, dict):
            content = delta.get("content") or ""
        elif isinstance(message, dict):
            content = message.get("content") or ""
        if isinstance(content, str) and content:
            delta_parts.append(content)
    return "".join(delta_parts)


async def stream_workflow_llm_text(
    model_id: str,
    prompt: str,
) -> AsyncIterator[str]:
    timeout = httpx.Timeout(connect=15, read=None, write=30, pool=10)
    proxy = proxy_url()
    client_kwargs: dict[str, Any] = {"timeout": timeout}
    if proxy:
        client_kwargs["proxy"] = proxy

    messages = [ChatMessage(role="user", content=prompt)]
    chat_payload = ChatRequest(
        model_id=model_id,
        messages=messages,
        temperature=0.7,
        max_tokens=2048,
    )
    current_model_id = model_id

    async with httpx.AsyncClient(**client_kwargs) as client:
        async def open_stream(candidate_model_id: str) -> httpx.Response:
            return await client.send(
                client.build_request(
                    "POST",
                    CHAT_COMPLETIONS_URL,
                    headers=openrouter_headers(),
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
                    delta = sse_delta_text(event)
                    if delta:
                        yield delta
        finally:
            await response.aclose()

        if buffer.strip():
            delta = sse_delta_text(buffer)
            if delta:
                yield delta


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/workflow/run")
async def run_workflow(payload: WorkflowRunRequest, request: Request):
    if not API_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "后端密钥尚未配置，请先设置环境变量 OPENROUTER_API_KEY。"},
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

    async def workflow_stream():
        variables = {str(key): str(value) for key, value in payload.inputs.items()}
        queue = deque(sorted(start_node_ids, key=lambda node_id: order_index[node_id]))
        queued = set(queue)
        executed: set[str] = set()
        final_output = ""

        try:
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
                    async for delta in stream_workflow_llm_text(model_id, prompt):
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
                    output = run_safe_code_node(node, variables)
                    variables[output_variable] = output

                elif kind == "output":
                    output_variable = str(node.data.get("outputVariable") or "llm_output")
                    final_output = variables.get(output_variable, "")
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

            yield sse_payload(
                {
                    "event": "workflow_end",
                    "final_output": final_output,
                    "variables": variables,
                }
            )
        except Exception as exc:
            logger.exception("Workflow run failed workflow=%s", payload.workflow.id)
            yield sse_payload({"event": "error", "message": str(exc)})

    return StreamingResponse(
        workflow_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )


@app.post("/api/fusion/chat")
async def fusion_chat(payload: FusionChatRequest, request: Request):
    if not API_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "后端密钥尚未配置，请先设置环境变量 OPENROUTER_API_KEY。"},
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
    if not API_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "后端密钥尚未配置，请先设置环境变量 OPENROUTER_API_KEY。"},
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
    if not API_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "后端密钥尚未配置，请先设置环境变量 OPENROUTER_API_KEY。"},
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


@app.on_event("shutdown")
async def shutdown_mcp_sessions() -> None:
    await mcp_manager.close_all()


@app.post("/api/mcp/connect", response_model=MCPConnectResponse)
async def connect_mcp_server(payload: MCPConnectRequest, request: Request):
    try:
        mcp_connect_rate_limit_or_raise(client_ip(request))
        validate_server_command(payload.server_command)
        await mcp_manager.cleanup_idle_sessions()
        session_id = await mcp_manager.connect(payload.server_command)
        tools = await mcp_manager.list_tools(session_id)
        return MCPConnectResponse(session_id=session_id, tools_count=len(tools))
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("MCP connect failed")
        raise HTTPException(status_code=400, detail=f"MCP Server 启动失败：{exc}") from exc


@app.get("/api/mcp/{session_id}/tools", response_model=MCPToolsResponse)
async def list_mcp_tools(session_id: str):
    try:
        tools = await mcp_manager.list_tools(session_id)
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
        return {"ok": True}
    except MCPSessionNotFoundError as exc:
        raise HTTPException(status_code=404, detail="MCP session 不存在或已断开。") from exc
    except MCPClientError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    if not API_KEY:
        return JSONResponse(
            status_code=500,
            content={"error": "后端密钥尚未配置，请先设置环境变量 OPENROUTER_API_KEY。"},
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

    timeout = httpx.Timeout(connect=15, read=None, write=30, pool=10)
    proxy = proxy_url()
    client_kwargs: dict[str, Any] = {"timeout": timeout}
    if proxy:
        client_kwargs["proxy"] = proxy

    client = httpx.AsyncClient(**client_kwargs)
    actual_model_id = payload.model_id
    fallback_notice = ""

    async def send_to_upstream(model_id: str) -> httpx.Response:
        logger.info("Sending chat request to model=%s", model_id)
        return await client.send(
            client.build_request(
                "POST",
                CHAT_COMPLETIONS_URL,
                headers=openrouter_headers(),
                json=build_upstream_payload(payload, model_id),
            ),
            stream=True,
        )

    try:
        response = await send_to_upstream(actual_model_id)
    except httpx.TimeoutException:
        logger.exception("OpenRouter request timed out model=%s", actual_model_id)
        await client.aclose()
        return JSONResponse(status_code=504, content={"error": "模型响应超时，请稍后重试。"})
    except httpx.HTTPError as exc:
        logger.exception("OpenRouter connection failed model=%s error=%s", actual_model_id, exc)
        await client.aclose()
        return JSONResponse(status_code=502, content={"error": "模型服务暂时无法连接，请检查网络或代理配置。"})
    except Exception:
        logger.exception("Unexpected error before upstream stream model=%s", actual_model_id)
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

        if should_fallback_model(
            response.status_code,
            message,
            data,
            actual_model_id,
            payload.messages,
        ):
            fallback_model_id = fallback_model_for(payload.messages)
            if any(message_has_image(message.content) for message in payload.messages) and not model_supports_image_input(fallback_model_id):
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
                await client.aclose()
                return JSONResponse(status_code=504, content={"error": "兜底模型响应超时，请稍后重试。"})
            except httpx.HTTPError as exc:
                logger.exception("Fallback model connection failed model=%s error=%s", fallback_model_id, exc)
                await client.aclose()
                return JSONResponse(status_code=502, content={"error": "当前模型和兜底模型都暂时无法连接。"})

            if response.status_code >= 400:
                fallback_body = await response.aread()
                await response.aclose()
                await client.aclose()
                fallback_message, _ = parse_upstream_error(response.status_code, fallback_body)
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
        else:
            await client.aclose()
            return JSONResponse(
                status_code=response.status_code,
                content={"error": message},
            )

    async def stream_response():
        buffer = ""
        try:
            if fallback_notice:
                payload_json = json.dumps(
                    {"choices": [{"delta": {"content": fallback_notice}}]},
                    ensure_ascii=False,
                )
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
                    yield line.encode("utf-8")
                await asyncio.sleep(0)
        except httpx.HTTPError:
            logger.exception("OpenRouter stream interrupted model=%s", actual_model_id)
            yield (
                'data: {"error":{"message":"模型服务连接中断，请稍后重试。"}}\n\n'
            ).encode("utf-8")
        except Exception:
            logger.exception("Unexpected stream error model=%s", actual_model_id)
            yield (
                'data: {"error":{"message":"后端转发流式响应时出错，请查看服务日志。"}}\n\n'
            ).encode("utf-8")
        finally:
            if buffer and not buffer.lstrip().startswith(":"):
                yield buffer.encode("utf-8")
            await response.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-ModelMirror-Actual-Model": actual_model_id,
        },
    )
