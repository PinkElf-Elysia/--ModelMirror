import {
  type WorkflowEdge,
  type WorkflowNodeData,
  type WorkflowNodeKind,
} from "./workflow";

export type XpertStatus = "draft" | "published" | "archived";

export interface XpertWorkflowDefinition {
  id: string;
  title: string;
  nodes: Array<{
    id: string;
    type?: WorkflowNodeKind | string | null;
    position?: { x: number; y: number } | null;
    data: WorkflowNodeData;
  }>;
  edges: WorkflowEdge[];
  source?: string;
  version?: string;
}

export interface XpertDraft {
  workflow: XpertWorkflowDefinition;
  input_variable: string;
  history_variable: string;
  output_variable: string;
}

export interface XpertVersion {
  version: number;
  draft_revision: number;
  workflow: XpertWorkflowDefinition;
  input_variable: string;
  history_variable: string;
  output_variable: string;
  release_notes: string;
  checksum: string;
  published_at: number;
}

export interface XpertDefinition {
  id: string;
  slug: string;
  name: string;
  description: string;
  tags: string[];
  starters: string[];
  status: XpertStatus;
  draft_revision: number;
  published_version: number | null;
  draft: XpertDraft;
  versions: XpertVersion[];
  created_at: number;
  updated_at: number;
}

export interface XpertSummary {
  id: string;
  slug: string;
  name: string;
  description: string;
  tags: string[];
  starters: string[];
  status: XpertStatus;
  draft_revision: number;
  published_version: number | null;
  version_count: number;
  created_at: number;
  updated_at: number;
}

export interface XpertValidationIssue {
  code: string;
  message: string;
  severity: "error" | "warning";
  node_id?: string | null;
  edge_id?: string | null;
}

export interface XpertValidationResult {
  valid: boolean;
  issues: XpertValidationIssue[];
  order: string[];
  node_count: number;
  edge_count: number;
}

export interface XpertListResponse {
  version: string;
  items: XpertSummary[];
  total: number;
}

export interface XpertConversationMessage {
  role: "user" | "assistant";
  content: string;
}
