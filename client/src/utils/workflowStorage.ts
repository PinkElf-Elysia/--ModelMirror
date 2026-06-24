import { type WorkflowDefinition } from "../types/workflow";

export const workflowStoragePrefix = "modelmirror-workflow:";

export function createWorkflowStorageKey(workflowId: string) {
  return `${workflowStoragePrefix}${workflowId}`;
}

export function readStoredWorkflow(workflowId: string): WorkflowDefinition | null {
  if (typeof window === "undefined") return null;

  const raw = window.localStorage.getItem(createWorkflowStorageKey(workflowId));
  if (!raw) return null;

  try {
    return JSON.parse(raw) as WorkflowDefinition;
  } catch {
    return null;
  }
}

export function saveStoredWorkflow(definition: WorkflowDefinition) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(
    createWorkflowStorageKey(definition.id),
    JSON.stringify(definition),
  );
}
