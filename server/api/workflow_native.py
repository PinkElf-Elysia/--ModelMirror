from __future__ import annotations

from fastapi import APIRouter

try:
    from server.workflow_native.schemas import (
        NativeTemplatePayload,
        NativeWorkflowDefinition,
        NativeWorkflowEdge,
        NativeWorkflowNode,
        ValidateWorkflowRequest,
        ValidateWorkflowResponse,
    )
    from server.workflow_native.validate import validate_workflow_graph
except ModuleNotFoundError:
    from workflow_native.schemas import (
        NativeTemplatePayload,
        NativeWorkflowDefinition,
        NativeWorkflowEdge,
        NativeWorkflowNode,
        ValidateWorkflowRequest,
        ValidateWorkflowResponse,
    )
    from workflow_native.validate import validate_workflow_graph


router = APIRouter(prefix="/api/workflow-native", tags=["workflow-native"])


def starter_template() -> NativeTemplatePayload:
    workflow = NativeWorkflowDefinition(
        id="native-linear-starter",
        title="Native linear starter",
        nodes=[
            NativeWorkflowNode(
                id="input",
                type="input",
                data={
                    "kind": "input",
                    "title": "Input",
                    "variableName": "user_input",
                },
            ),
            NativeWorkflowNode(
                id="llm",
                type="llm",
                data={
                    "kind": "llm",
                    "title": "LLM",
                    "modelId": "openai/gpt-4o-mini",
                    "prompt": "请基于 {{user_input}} 给出清晰回答。",
                    "outputVariable": "llm_output",
                },
            ),
            NativeWorkflowNode(
                id="output",
                type="output",
                data={
                    "kind": "output",
                    "title": "Output",
                    "outputVariable": "llm_output",
                },
            ),
        ],
        edges=[
            NativeWorkflowEdge(id="input-llm", source="input", target="llm"),
            NativeWorkflowEdge(id="llm-output", source="llm", target="output"),
        ],
    )
    return NativeTemplatePayload(
        id="native-linear-starter",
        title="输入 -> LLM -> 输出",
        description="用于验证 workflow-native 静态图校验的最小三节点样例。",
        workflow=workflow,
    )


@router.get("/templates", response_model=list[NativeTemplatePayload])
async def list_native_workflow_templates() -> list[NativeTemplatePayload]:
    return [starter_template()]


@router.post("/validate", response_model=ValidateWorkflowResponse)
async def validate_native_workflow(
    payload: ValidateWorkflowRequest,
) -> ValidateWorkflowResponse:
    return validate_workflow_graph(payload.workflow)
