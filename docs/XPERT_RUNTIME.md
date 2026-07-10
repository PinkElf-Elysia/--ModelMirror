# Xpert Runtime Contract

Last updated: 2026-07-10

## Purpose

This document describes the first ModelMirror-native Xpert publishing contract. It aligns with Xpert concepts while retaining the repository's React, FastAPI, Pydantic, pytest, and classic workflow runner architecture.

The implementation does not copy Xpert source code or migrate its Angular, NestJS, Nx, or persistence stack.

## Resource Model

The server/xperts package owns a file-backed XpertStore. Its default storage location is server/xperts/storage/xperts.json, overridable through XPERT_STORAGE_DIR.

- XpertDefinition: identity, slug, name, description, tags, starter prompts, status, draft revision, and published-version pointer.
- XpertDraft: editable workflow snapshot plus the chat input, history, and output variable names.
- XpertVersion: immutable published workflow snapshot, version number, draft revision, release notes, checksum, and timestamp.

The Store uses an in-process lock and atomic temporary-file replacement. It is deliberately an adapter boundary: a future database migration must keep the API contract stable.

## Lifecycle

1. Create a draft Xpert with the default chat workflow: input(user_input) -> workflow_agent(agent_output) -> output(agent_output).
2. Edit and save the draft. Every save increments draft_revision.
3. Request validation. The server runs the existing graph validator plus the Xpert chat contract.
4. Publish. The server verifies the revision did not change during preflight, then records an immutable version.
5. Run a published version. The server injects the current user message and a bounded conversation-history JSON summary, then delegates to the existing classic workflow runner.

Draft updates never mutate a published snapshot. Archived Xperts remain inspectable but cannot run.

## Publish Contract

The first chat release requires:

- exactly one input node whose variable matches input_variable;
- exactly one output node whose variable matches output_variable;
- at least one workflow_agent with modelId, rolePrompt, taskInput, and outputVariable;
- reachable template variables, except the configured history variable injected by the published-chat runtime;
- no human_intervention node, because the v1 chat entry has no pause/resume UI.

Existing middleware, MCP Toolset, knowledge, AgentTask, Handoff, and RunRegistry validation remains in force.

## Public API

- GET /api/xperts?status=&search=&limit=
- POST /api/xperts
- GET /api/xperts/{xpert_id}
- PATCH /api/xperts/{xpert_id}
- POST /api/xperts/{xpert_id}/validate
- POST /api/xperts/{xpert_id}/publish
- GET /api/xperts/{xpert_id}/versions
- GET /api/xperts/{xpert_id}/versions/{version}
- POST /api/xperts/{xpert_id}/run

List responses expose summaries only. Detail and version endpoints expose the workflow only when it is required for editing or version inspection.

## Execution and Observability

Published runs use run_type=xpert and the same SSE event family as classic workflow execution:

- workflow_meta
- node_start
- node_delta
- node_end
- workflow_end
- error

For Xpert runs, workflow_meta also exposes xpert_id and xpert_version. RunRegistry metadata links the Xpert ID, slug, version, draft revision, and checksum. Tool, knowledge, AgentTask, and Handoff node runs remain children of the Xpert run.

Checkpoints store titles, event types, status, lengths, IDs, and error summaries. They must not store complete prompts, complete model or tool outputs, API keys, local absolute paths, embeddings, or raw secrets.

## Current Limits

- File persistence is local and is not a workspace database.
- There is no public App/API token, sharing model, organization permission, or collaborative editor.
- Handoff remains manually managed; no worker automatically accepts or executes a target Xpert.
- Long-term Goals, durable memory, file understanding, and knowledge-ingestion jobs are separate future milestones.
- A normal /workflow run remains unchanged and continues to use its existing local-draft behavior.
