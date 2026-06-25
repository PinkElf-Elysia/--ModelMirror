from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


FieldType = Literal["text", "textarea", "select", "boolean", "number", "json"]


@dataclass(slots=True)
class RuntimeMiddlewareField:
    """A canvas-renderable field definition for runtime middleware nodes."""

    name: str
    label: str
    type: FieldType
    required: bool = False
    default: Any | None = None
    options: list[str] | None = None
    placeholder: str | None = None
    description: str | None = None
    min_value: float | None = None
    max_value: float | None = None
    rows: int | None = None


@dataclass(slots=True)
class RuntimeMiddlewareNode:
    """Metadata for one Xpert-style runtime middleware palette node."""

    id: str
    kind: str
    title: str
    description: str
    category: str
    icon: str
    fields: list[RuntimeMiddlewareField] = field(default_factory=list)
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeMiddlewareRegistry:
    """In-memory registry of middleware nodes available to the canvas palette."""

    def __init__(self) -> None:
        self._nodes: dict[str, RuntimeMiddlewareNode] = {}

    def register(self, node: RuntimeMiddlewareNode) -> None:
        self._nodes[node.id] = node

    def list(self) -> list[RuntimeMiddlewareNode]:
        return list(self._nodes.values())

    def get(self, node_id: str) -> RuntimeMiddlewareNode | None:
        return self._nodes.get(node_id)

    def categories(self) -> list[str]:
        return sorted({node.category for node in self._nodes.values()})

    def by_category(self) -> dict[str, list[RuntimeMiddlewareNode]]:
        grouped: dict[str, list[RuntimeMiddlewareNode]] = {}
        for node in self._nodes.values():
            grouped.setdefault(node.category, []).append(node)
        return grouped


def register_builtin_middleware_nodes(
    registry: RuntimeMiddlewareRegistry,
) -> None:
    """Register ModelMirror's first built-in runtime middleware node metadata."""

    registry.register(
        RuntimeMiddlewareNode(
            id="system_prompt_injector",
            kind="runtime_middleware.system_prompt_injector",
            title="系统提示词注入器",
            description="在模型调用前自动注入系统提示词，支持覆盖或追加模式。",
            category="agent",
            icon="MessageSquare",
            fields=[
                RuntimeMiddlewareField(
                    name="system_prompt",
                    label="系统提示词",
                    type="textarea",
                    required=True,
                    rows=4,
                    placeholder="你是一个专业的...",
                ),
                RuntimeMiddlewareField(
                    name="override",
                    label="覆盖已有系统提示词",
                    type="boolean",
                    default=False,
                    description="开启后替换消息列表首条 system message。",
                ),
            ],
            tags=["agent", "prompt", "before_model"],
            metadata={
                "middleware_name": "system_prompt_injector",
                "runtime_hook": "before_model",
            },
        )
    )

    registry.register(
        RuntimeMiddlewareNode(
            id="event_recorder",
            kind="runtime_middleware.event_recorder",
            title="事件记录器",
            description="记录 chat/model/tool 生命周期事件到 Runtime Event Store，用于追踪和调试。",
            category="agent",
            icon="Activity",
            tags=["observability", "events"],
            metadata={
                "middleware_name": "event_recorder",
                "runtime_hook": "lifecycle",
            },
        )
    )

    registry.register(
        RuntimeMiddlewareNode(
            id="tool_policy",
            kind="runtime_middleware.tool_policy",
            title="工具权限策略",
            description="基于 allow/deny 列表控制哪些工具可以被调用。",
            category="tool",
            icon="Shield",
            fields=[
                RuntimeMiddlewareField(
                    name="allowed_tools",
                    label="允许的工具（每行一个）",
                    type="textarea",
                    placeholder="fetch\necho\nsearch",
                    description="留空表示不限制。白名单模式下仅允许列表中的工具。",
                    rows=4,
                ),
                RuntimeMiddlewareField(
                    name="denied_tools",
                    label="禁止的工具（每行一个）",
                    type="textarea",
                    placeholder="delete\neval",
                    description="优先级高于 allowed_tools。",
                    rows=4,
                ),
                RuntimeMiddlewareField(
                    name="allow_by_default",
                    label="默认放行",
                    type="boolean",
                    default=True,
                ),
            ],
            tags=["tool", "policy", "permission"],
            metadata={
                "middleware_name": "tool_policy",
                "runtime_hook": "tool_policy",
            },
        )
    )

    registry.register(
        RuntimeMiddlewareNode(
            id="tool_audit",
            kind="runtime_middleware.tool_audit",
            title="工具审计记录器",
            description="结构化记录工具调用：工具名、状态、耗时、输出长度、错误信息。",
            category="tool",
            icon="ClipboardList",
            fields=[
                RuntimeMiddlewareField(
                    name="max_records",
                    label="最大记录数",
                    type="number",
                    default=10000,
                    min_value=100,
                    max_value=100000,
                ),
            ],
            tags=["tool", "audit", "observability"],
            metadata={
                "middleware_name": "tool_audit",
                "runtime_hook": "tool_audit",
            },
        )
    )

    registry.register(
        RuntimeMiddlewareNode(
            id="mcp_tools",
            kind="runtime_middleware.mcp_tools",
            title="MCP 工具集",
            description="通过 Runtime Toolset Capability 调用已注册的 MCP 工具。",
            category="tool",
            icon="Puzzle",
            fields=[
                RuntimeMiddlewareField(
                    name="capability_name",
                    label="Capability 名称",
                    type="text",
                    default="mcp_tools",
                ),
                RuntimeMiddlewareField(
                    name="capability_required",
                    label="Capability 必须存在",
                    type="boolean",
                    default=True,
                ),
            ],
            tags=["tool", "mcp", "capability"],
            metadata={
                "capability_name": "mcp_tools",
                "runtime_hook": "capability",
            },
        )
    )


runtime_middleware_registry = RuntimeMiddlewareRegistry()
register_builtin_middleware_nodes(runtime_middleware_registry)
