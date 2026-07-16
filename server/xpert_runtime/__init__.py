"""Xpert-aligned runtime foundation for ModelMirror.

The package intentionally stays framework-agnostic. FastAPI routes, workflow
nodes, MCP tools, and future multi-agent runners can depend on these small
runtime primitives without adding more orchestration logic to ``server/main.py``.
"""

from .capabilities import CapabilityRegistry, RuntimeCapability
from .agent_tasks import (
    AUTO_XPERT_TARGET_PREFIX,
    AgentHandoff,
    AgentTask,
    AgentTaskStore,
)
from .handoff_executor import (
    HandoffBusyError,
    HandoffExecutionResult,
    HandoffExecutor,
    HandoffExecutorError,
    HandoffPermanentError,
)
from .goal_coordinator import GoalCoordinator, GoalPlan, PinnedXpert
from .goals import (
    ConversationGoal,
    GoalConflictError,
    GoalNotFoundError,
    GoalStatus,
    GoalStep,
    GoalStepStatus,
    GoalStore,
    GoalStoreError,
    GoalValidationError,
    goal_to_payload,
    validate_goal_plan,
)
from .defaults import create_default_runtime, event_recorder, system_prompt_injector
from .events import RuntimeEventStore
from .middleware import AgentMiddleware, MiddlewarePipeline
from .middleware_registry import (
    RuntimeMiddlewareField,
    RuntimeMiddlewareNode,
    RuntimeMiddlewareRegistry,
    register_builtin_middleware_nodes,
    runtime_middleware_registry,
)
from .memory_toolset import MemoryToolsetProvider, register_memory_toolset_capability
from .knowledge_toolset import (
    KnowledgeToolsetProvider,
    register_knowledge_toolset_capability,
)
from .workflow_node_registry import (
    KnowledgePipelinePalette,
    WorkflowNodeRegistry,
    WorkflowPaletteItem,
    WorkflowPalettePlaceholder,
    WorkflowPaletteSection,
    WorkflowPaletteTab,
    register_builtin_workflow_nodes,
    workflow_node_registry,
)
from .models import (
    MiddlewareContext,
    ModelCallRequest,
    ModelCallResponse,
    RuntimeEvent,
    RuntimeTask,
    ToolCallRequest,
    ToolCallResponse,
)
from .run_registry import (
    RunRegistry,
    RuntimeRun,
    RuntimeRunCheckpoint,
    RuntimeRunStatus,
    RuntimeRunType,
)
from .tool_policy import (
    InMemoryToolAuditStore,
    ToolAuditRecord,
    ToolAuditStatus,
    ToolPermissionPolicy,
)
from .toolset import (
    MCPToolsetProvider,
    RuntimeTool,
    RuntimeToolCall,
    RuntimeToolError,
    RuntimeToolResult,
    ToolsetProvider,
    register_mcp_toolset_capability,
)
from .tool_runner import run_tool_with_runtime

__all__ = [
    "AgentMiddleware",
    "AUTO_XPERT_TARGET_PREFIX",
    "AgentHandoff",
    "AgentTask",
    "AgentTaskStore",
    "CapabilityRegistry",
    "create_default_runtime",
    "event_recorder",
    "HandoffBusyError",
    "HandoffExecutionResult",
    "HandoffExecutor",
    "HandoffExecutorError",
    "HandoffPermanentError",
    "ConversationGoal",
    "GoalConflictError",
    "GoalCoordinator",
    "GoalNotFoundError",
    "GoalPlan",
    "GoalStatus",
    "GoalStep",
    "GoalStepStatus",
    "GoalStore",
    "GoalStoreError",
    "GoalValidationError",
    "PinnedXpert",
    "goal_to_payload",
    "validate_goal_plan",
    "InMemoryToolAuditStore",
    "MCPToolsetProvider",
    "KnowledgeToolsetProvider",
    "MemoryToolsetProvider",
    "MiddlewareContext",
    "MiddlewarePipeline",
    "ModelCallRequest",
    "ModelCallResponse",
    "RuntimeCapability",
    "RuntimeEvent",
    "RuntimeEventStore",
    "RuntimeMiddlewareField",
    "RuntimeMiddlewareNode",
    "RuntimeMiddlewareRegistry",
    "WorkflowNodeRegistry",
    "WorkflowPaletteItem",
    "WorkflowPalettePlaceholder",
    "WorkflowPaletteSection",
    "WorkflowPaletteTab",
    "KnowledgePipelinePalette",
    "RuntimeRun",
    "RuntimeRunCheckpoint",
    "RuntimeRunStatus",
    "RuntimeRunType",
    "RuntimeTask",
    "RuntimeTool",
    "RuntimeToolCall",
    "RuntimeToolError",
    "RuntimeToolResult",
    "run_tool_with_runtime",
    "RunRegistry",
    "runtime_middleware_registry",
    "workflow_node_registry",
    "system_prompt_injector",
    "ToolCallRequest",
    "ToolCallResponse",
    "ToolAuditRecord",
    "ToolAuditStatus",
    "ToolsetProvider",
    "ToolPermissionPolicy",
    "register_builtin_middleware_nodes",
    "register_builtin_workflow_nodes",
    "register_mcp_toolset_capability",
    "register_knowledge_toolset_capability",
    "register_memory_toolset_capability",
]
