import {
  type XpertDefinition,
  type XpertDraft,
  type XpertListResponse,
  type XpertStatus,
  type XpertValidationResult,
  type XpertVersion,
  type XpertWorkflowDefinition,
} from "../types/xpert";
import { type WorkflowDefinition } from "../types/workflow";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    let message = `请求失败：${response.status}`;
    try {
      const payload = (await response.json()) as {
        detail?: string | { message?: string };
        error?: string;
      };
      if (typeof payload.detail === "string") message = payload.detail;
      if (typeof payload.detail === "object" && payload.detail?.message) {
        message = payload.detail.message;
      }
      if (payload.error) message = payload.error;
    } catch {
      // Keep the status-based fallback when the response is not JSON.
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

function jsonRequest(method: "POST" | "PATCH", body: unknown): RequestInit {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

export function listXperts(options?: {
  status?: XpertStatus | "all";
  search?: string;
  limit?: number;
}) {
  const query = new URLSearchParams();
  if (options?.status && options.status !== "all") {
    query.set("status", options.status);
  }
  if (options?.search) query.set("search", options.search);
  query.set("limit", String(options?.limit ?? 100));
  return requestJson<XpertListResponse>(`/api/xperts?${query.toString()}`);
}

export function createXpert(payload: {
  name: string;
  slug?: string;
  description?: string;
  tags?: string[];
  starters?: string[];
}) {
  return requestJson<XpertDefinition>(
    "/api/xperts",
    jsonRequest("POST", payload),
  );
}

export function getXpert(xpertId: string) {
  return requestJson<XpertDefinition>(`/api/xperts/${xpertId}`);
}

export function updateXpert(
  xpertId: string,
  payload: Partial<
    Pick<XpertDefinition, "name" | "description" | "tags" | "starters" | "status">
  > & { draft?: XpertDraft },
) {
  return requestJson<XpertDefinition>(
    `/api/xperts/${xpertId}`,
    jsonRequest("PATCH", payload),
  );
}

export function validateXpert(xpertId: string) {
  return requestJson<XpertValidationResult>(
    `/api/xperts/${xpertId}/validate`,
    jsonRequest("POST", {}),
  );
}

export function publishXpert(xpertId: string, releaseNotes: string) {
  return requestJson<XpertVersion>(
    `/api/xperts/${xpertId}/publish`,
    jsonRequest("POST", { release_notes: releaseNotes }),
  );
}

export function listXpertVersions(xpertId: string) {
  return requestJson<XpertVersion[]>(`/api/xperts/${xpertId}/versions`);
}

export function toWorkflowDefinition(
  xpert: XpertDefinition,
): WorkflowDefinition {
  return {
    id: xpert.draft.workflow.id,
    title: xpert.draft.workflow.title,
    nodes: xpert.draft.workflow.nodes.map((node) => ({
      id: node.id,
      type: "workflowNode" as const,
      position: node.position ?? { x: 0, y: 0 },
      data: node.data,
    })),
    edges: xpert.draft.workflow.edges,
    updatedAt: new Date(xpert.updated_at * 1000).toISOString(),
  };
}

export function toXpertDraftWorkflow(definition: WorkflowDefinition) {
  return {
    id: definition.id,
    title: definition.title,
    version: "xpert-draft-v1",
    source: "classic",
    nodes: definition.nodes.map((node) => ({
      id: node.id,
      type: node.data.kind,
      position: node.position,
      data: node.data,
    })),
    edges: definition.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
    })),
  } satisfies XpertWorkflowDefinition;
}
