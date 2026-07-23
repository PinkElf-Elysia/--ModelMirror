import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PageContainer from "../components/PageContainer";

type Transport = "stdio" | "streamable_http" | "legacy_sse";
type CredentialKind = "header" | "environment" | "provider_key" | "generic";

interface CredentialSummary {
  credential_id: string;
  name: string;
  kind: CredentialKind;
  prefix: string;
  masked_value: string;
  status: string;
}

interface SecretBinding {
  name: string;
  credential_id: string;
}

interface ConnectionProfile {
  transport: Transport;
  command: string[];
  url: string;
  headers: SecretBinding[];
  environment: SecretBinding[];
  installed_project_id: string;
  working_directory: string;
  auto_start: boolean;
  auto_reconnect: boolean;
  reconnect_attempts: number;
  tool_prefix: string;
  network_policy: "public_only" | "trusted_private";
  timeout_seconds: number;
}

interface ToolDefinition {
  original_name: string;
  alias: string;
  description: string;
  input_schema: Record<string, unknown>;
  default_arguments: Record<string, unknown>;
  enabled: boolean;
  order: number;
  schema_hash: string;
}

interface ToolsetVersion {
  version: number;
  draft_revision: number;
  schema_hash: string;
  release_notes: string;
  published_at: number;
  tools: ToolDefinition[];
}

interface ToolsetDefinition {
  id: string;
  name: string;
  description: string;
  tags: string[];
  privacy_policy: string;
  disclaimer: string;
  status: "draft" | "published" | "archived";
  revision: number;
  published_version: number | null;
  connection: ConnectionProfile;
  tools: ToolDefinition[];
  versions: ToolsetVersion[];
  runtime_status: string;
  runtime_session_id: string | null;
  runtime_error: string;
  updated_at: number;
}

interface InstalledMCPProject {
  project_id: string;
  server_command?: string[];
  install_type?: string;
  npm_package?: string;
}

const emptyConnection: ConnectionProfile = {
  transport: "stdio",
  command: [],
  url: "",
  headers: [],
  environment: [],
  installed_project_id: "",
  working_directory: "",
  auto_start: false,
  auto_reconnect: true,
  reconnect_attempts: 2,
  tool_prefix: "",
  network_policy: "public_only",
  timeout_seconds: 30,
};

const inputClass =
  "w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 text-sm text-white outline-none transition focus:border-cyan-300 disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButton =
  "rounded-md border border-white/10 px-3 py-2 text-sm font-semibold text-slate-200 transition hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-45";
const primaryButton =
  "rounded-md bg-cyan-300 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-200 disabled:cursor-not-allowed disabled:opacity-45";

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = (payload as { detail?: unknown }).detail;
    throw new Error(typeof detail === "string" ? detail : `请求失败：${response.status}`);
  }
  return payload as T;
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  const parsed = JSON.parse(value || "{}") as unknown;
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${label}必须是 JSON 对象。`);
  }
  return parsed as Record<string, unknown>;
}

function formatTime(value: number): string {
  return new Date(value * 1000).toLocaleString("zh-CN");
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "connected" || status === "published"
      ? "bg-emerald-300"
      : status === "error"
        ? "bg-rose-300"
        : "bg-slate-500";
  return <span aria-hidden="true" className={`h-2 w-2 rounded-full ${color}`} />;
}

function InlineMessage({
  tone,
  children,
  onClose,
}: {
  tone: "error" | "success";
  children: string;
  onClose: () => void;
}) {
  const colors =
    tone === "error" ? "bg-rose-500/10 text-rose-100" : "bg-emerald-400/10 text-emerald-100";
  return (
    <div className={`mt-4 flex items-start justify-between gap-3 rounded-md px-3 py-2 text-sm ${colors}`}>
      <span>{children}</span>
      <button className="font-semibold" onClick={onClose} type="button">
        关闭
      </button>
    </div>
  );
}

export default function ToolsetsPage() {
  const [toolsets, setToolsets] = useState<ToolsetDefinition[]>([]);
  const [credentials, setCredentials] = useState<CredentialSummary[]>([]);
  const [installedProjects, setInstalledProjects] = useState<InstalledMCPProject[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [draft, setDraft] = useState<ToolsetDefinition | null>(null);
  const [commandText, setCommandText] = useState("[]");
  const [newName, setNewName] = useState("");
  const [newDescription, setNewDescription] = useState("");
  const [credentialName, setCredentialName] = useState("");
  const [credentialKind, setCredentialKind] = useState<CredentialKind>("header");
  const [credentialValue, setCredentialValue] = useState("");
  const [releaseNotes, setReleaseNotes] = useState("");
  const [activeTool, setActiveTool] = useState("");
  const [toolArguments, setToolArguments] = useState("{}");
  const [toolResult, setToolResult] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  const selected = useMemo(
    () => toolsets.find((item) => item.id === selectedId) ?? null,
    [selectedId, toolsets],
  );
  const activeToolDefinition = useMemo(
    () => draft?.tools.find((tool) => tool.original_name === activeTool) ?? null,
    [activeTool, draft],
  );
  const counts = useMemo(
    () => ({
      connected: toolsets.filter((item) => item.runtime_status === "connected").length,
      published: toolsets.filter((item) => item.status === "published").length,
      enabledTools: toolsets.reduce(
        (sum, item) => sum + item.tools.filter((tool) => tool.enabled).length,
        0,
      ),
    }),
    [toolsets],
  );

  const loadAll = useCallback(async (preferredId?: string) => {
    setLoading(true);
    try {
      const [toolsetPayload, credentialPayload, installedPayload] = await Promise.all([
        requestJson<{ toolsets: ToolsetDefinition[] }>("/api/toolsets"),
        requestJson<{ credentials: CredentialSummary[] }>("/api/runtime/credentials"),
        requestJson<{ installed: InstalledMCPProject[] }>("/api/mcp/installed"),
      ]);
      setToolsets(toolsetPayload.toolsets);
      setCredentials(credentialPayload.credentials);
      setInstalledProjects(installedPayload.installed);
      setSelectedId((current) => {
        const wanted = preferredId || current;
        return toolsetPayload.toolsets.some((item) => item.id === wanted)
          ? wanted
          : toolsetPayload.toolsets[0]?.id || "";
      });
      setError("");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Toolset 加载失败。");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  useEffect(() => {
    if (!selected) {
      setDraft(null);
      return;
    }
    setDraft(structuredClone(selected));
    setCommandText(JSON.stringify(selected.connection.command, null, 2));
    setActiveTool((current) =>
      selected.tools.some((tool) => tool.original_name === current)
        ? current
        : selected.tools[0]?.original_name || "",
    );
    setToolResult("");
  }, [selected]);

  function patchDraft(patch: Partial<ToolsetDefinition>) {
    setDraft((current) => (current ? { ...current, ...patch } : current));
  }

  function patchConnection(patch: Partial<ConnectionProfile>) {
    setDraft((current) =>
      current ? { ...current, connection: { ...current.connection, ...patch } } : current,
    );
  }

  async function createToolset(event: FormEvent) {
    event.preventDefault();
    if (!newName.trim()) return;
    setBusy("create");
    try {
      const created = await requestJson<ToolsetDefinition>("/api/toolsets", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: newName.trim(),
          description: newDescription.trim(),
          connection: emptyConnection,
        }),
      });
      setNewName("");
      setNewDescription("");
      setNotice("Toolset 草稿已创建。");
      await loadAll(created.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "创建失败。");
    } finally {
      setBusy("");
    }
  }

  async function saveDraft(): Promise<ToolsetDefinition | null> {
    if (!draft) return null;
    setBusy("save");
    try {
      let command: string[] = [];
      if (draft.connection.transport === "stdio") {
        const parsed = JSON.parse(commandText) as unknown;
        if (!Array.isArray(parsed) || !parsed.every((item) => typeof item === "string")) {
          throw new Error("Stdio 命令必须是字符串数组。");
        }
        command = parsed;
      }
      const updated = await requestJson<ToolsetDefinition>(`/api/toolsets/${draft.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: draft.revision,
          patch: {
            name: draft.name,
            description: draft.description,
            tags: draft.tags,
            privacy_policy: draft.privacy_policy,
            disclaimer: draft.disclaimer,
            connection: { ...draft.connection, command },
          },
        }),
      });
      setNotice("Toolset 草稿已保存。");
      await loadAll(updated.id);
      return updated;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "保存失败。");
      return null;
    } finally {
      setBusy("");
    }
  }

  async function runConnection(action: "connect" | "disconnect") {
    if (!draft) return;
    setBusy(action);
    try {
      let revision = draft.revision;
      if (action === "connect") {
        const saved = await saveDraft();
        if (!saved) return;
        revision = saved.revision;
      }
      const current = await requestJson<ToolsetDefinition>(
        `/api/toolsets/${draft.id}/${action}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision }),
        },
      );
      setNotice(
        action === "connect"
          ? "连接成功，工具 Schema 已刷新。新发现工具默认关闭。"
          : "连接已断开。",
      );
      await loadAll(current.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "连接操作失败。");
    } finally {
      setBusy("");
    }
  }

  async function createCredential(event: FormEvent) {
    event.preventDefault();
    if (!credentialName.trim() || !credentialValue) return;
    setBusy("credential");
    try {
      await requestJson("/api/runtime/credentials", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: credentialName.trim(),
          kind: credentialKind,
          value: credentialValue,
        }),
      });
      setCredentialName("");
      setCredentialValue("");
      setNotice("凭据已加密保存，后续只显示掩码。");
      await loadAll(draft?.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "凭据保存失败。");
    } finally {
      setBusy("");
    }
  }

  function updateBinding(
    field: "headers" | "environment",
    index: number,
    patch: Partial<SecretBinding>,
  ) {
    if (!draft) return;
    const next = [...draft.connection[field]];
    next[index] = { ...next[index], ...patch };
    patchConnection({ [field]: next });
  }

  function addBinding(field: "headers" | "environment") {
    if (!draft) return;
    patchConnection({
      [field]: [
        ...draft.connection[field],
        {
          name: "",
          credential_id:
            credentials.find((item) => item.status === "active")?.credential_id || "",
        },
      ],
    });
  }

  function removeBinding(field: "headers" | "environment", index: number) {
    if (!draft) return;
    patchConnection({
      [field]: draft.connection[field].filter((_, position) => position !== index),
    });
  }

  async function updateTool(patch: Partial<ToolDefinition>) {
    if (!draft || !activeToolDefinition) return;
    setBusy("tool");
    try {
      const updated = await requestJson<ToolsetDefinition>(
        `/api/toolsets/${draft.id}/tools/${encodeURIComponent(activeToolDefinition.original_name)}`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ revision: draft.revision, patch }),
        },
      );
      setNotice("工具配置已保存。");
      await loadAll(updated.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "工具配置保存失败。");
    } finally {
      setBusy("");
    }
  }

  async function testTool() {
    if (!draft || !activeToolDefinition) return;
    setBusy("test");
    try {
      const result = await requestJson<{
        output: string;
        is_error: boolean;
        metadata: Record<string, unknown>;
      }>(
        `/api/toolsets/${draft.id}/tools/${encodeURIComponent(activeToolDefinition.original_name)}/test`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            arguments: parseJsonObject(toolArguments, "测试参数"),
          }),
        },
      );
      setToolResult(result.output || JSON.stringify(result.metadata, null, 2));
      setNotice(result.is_error ? "工具返回了错误结果。" : "工具测试完成。");
    } catch (reason) {
      setToolResult("");
      setError(reason instanceof Error ? reason.message : "工具测试失败。");
    } finally {
      setBusy("");
    }
  }

  async function publishToolset() {
    if (!draft) return;
    setBusy("publish");
    try {
      const version = await requestJson<ToolsetVersion>(`/api/toolsets/${draft.id}/publish`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          revision: draft.revision,
          release_notes: releaseNotes.trim(),
        }),
      });
      setReleaseNotes("");
      setNotice(`Toolset v${version.version} 已发布。`);
      await loadAll(draft.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "发布失败。");
    } finally {
      setBusy("");
    }
  }

  return (
    <PageContainer activeResource="mcps" hideSidebar maxWidthClassName="max-w-[1720px]">
      <div className="px-1 py-2 sm:px-2">
        <header className="flex flex-col gap-4 border-b border-white/10 pb-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-semibold text-cyan-200">
              <span className="h-2 w-2 rounded-full bg-cyan-300" />
              Runtime Toolset
            </div>
            <h1 className="mt-2 text-2xl font-semibold text-white">MCP Toolset 管理</h1>
            <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
              配置连接与凭据，发现并测试工具，然后发布不可变版本供 Agent 绑定。
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-slate-300">
              {toolsets.length} 个 Toolset
            </span>
            <span className="rounded-full bg-emerald-300/10 px-3 py-1.5 text-xs text-emerald-200">
              {counts.connected} 个已连接
            </span>
            <span className="rounded-full bg-cyan-300/10 px-3 py-1.5 text-xs text-cyan-100">
              {counts.published} 个已发布 · {counts.enabledTools} 个工具
            </span>
            <Link className={secondaryButton} to="/mcps">
              发现 MCP 项目
            </Link>
            <button className={secondaryButton} onClick={() => void loadAll()} type="button">
              刷新
            </button>
          </div>
        </header>

        <nav aria-label="Toolset 类型" className="mt-4 flex gap-1 border-b border-white/10">
          <button
            className="border-b-2 border-cyan-300 px-3 py-2 text-sm font-semibold text-cyan-100"
            type="button"
          >
            我的 Toolset
          </button>
          <button className="cursor-not-allowed px-3 py-2 text-sm text-slate-500" disabled type="button">
            内置 Provider（下一轮）
          </button>
          <button className="cursor-not-allowed px-3 py-2 text-sm text-slate-500" disabled type="button">
            API Toolset（下一轮）
          </button>
        </nav>

        {error ? <InlineMessage onClose={() => setError("")} tone="error">{error}</InlineMessage> : null}
        {notice ? <InlineMessage onClose={() => setNotice("")} tone="success">{notice}</InlineMessage> : null}

        <div className="mt-5 grid min-h-[720px] gap-5 xl:grid-cols-[260px_minmax(420px,0.9fr)_minmax(420px,1.1fr)]">
          <aside className="border-r border-white/10 pr-5">
            <form className="border-b border-white/10 pb-5" onSubmit={createToolset}>
              <h2 className="text-sm font-semibold text-white">创建 MCP Toolset</h2>
              <label className="mt-3 block text-xs font-semibold text-slate-300">
                名称
                <input
                  className={`${inputClass} mt-1`}
                  maxLength={160}
                  onChange={(event) => setNewName(event.target.value)}
                  placeholder="研究工具集"
                  value={newName}
                />
              </label>
              <label className="mt-3 block text-xs font-semibold text-slate-300">
                说明
                <textarea
                  className={`${inputClass} mt-1 min-h-20 resize-y`}
                  maxLength={2000}
                  onChange={(event) => setNewDescription(event.target.value)}
                  placeholder="工具用途和使用边界"
                  value={newDescription}
                />
              </label>
              <button
                className={`${primaryButton} mt-3 w-full`}
                disabled={busy === "create" || !newName.trim()}
                type="submit"
              >
                {busy === "create" ? "创建中..." : "创建草稿"}
              </button>
            </form>

            <div className="pt-4">
              <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
                <span>Toolset</span>
                <span>{toolsets.length}</span>
              </div>
              <div className="divide-y divide-white/10 border-y border-white/10">
                {loading ? <p className="py-5 text-center text-xs text-slate-500">正在加载...</p> : null}
                {!loading && !toolsets.length ? (
                  <p className="py-7 text-center text-xs leading-5 text-slate-500">
                    创建第一个 Toolset 后，在这里连接 MCP 并选择工具。
                  </p>
                ) : null}
                {toolsets.map((item) => (
                  <button
                    className={`w-full px-2 py-3 text-left transition ${
                      item.id === selectedId ? "bg-cyan-300/10" : "hover:bg-white/[0.035]"
                    }`}
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    type="button"
                  >
                    <span className="flex items-center gap-2 text-sm font-semibold text-white">
                      <StatusDot status={item.runtime_status} />
                      <span className="truncate">{item.name}</span>
                    </span>
                    <span className="mt-1 flex justify-between gap-2 text-[11px] text-slate-500">
                      <span>{item.connection.transport}</span>
                      <span>{item.published_version ? `v${item.published_version}` : "未发布"}</span>
                    </span>
                  </button>
                ))}
              </div>
            </div>
          </aside>

          {!draft ? (
            <section className="col-span-2 flex min-h-[560px] items-center justify-center border border-dashed border-white/10">
              <div className="max-w-sm text-center">
                <h2 className="text-base font-semibold text-white">选择一个 Toolset</h2>
                <p className="mt-2 text-sm leading-6 text-slate-500">
                  连接成功后会发现 MCP 工具，启用至少一个工具即可发布版本。
                </p>
              </div>
            </section>
          ) : (
            <>
              <section className="min-w-0 border-r border-white/10 pr-5">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-base font-semibold text-white">连接与版本</h2>
                    <p className="mt-1 flex items-center gap-2 text-xs text-slate-500">
                      <StatusDot status={draft.runtime_status} />
                      {draft.runtime_status}
                      {draft.runtime_error ? ` · ${draft.runtime_error}` : ""}
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <button
                      className={secondaryButton}
                      disabled={busy !== ""}
                      onClick={() => void runConnection("disconnect")}
                      type="button"
                    >
                      断开
                    </button>
                    <button
                      className={primaryButton}
                      disabled={busy !== ""}
                      onClick={() => void runConnection("connect")}
                      type="button"
                    >
                      {busy === "connect" ? "连接中..." : "保存并连接"}
                    </button>
                  </div>
                </div>

                <div className="mt-5 space-y-4">
                  <label className="block text-xs font-semibold text-slate-300">
                    名称
                    <input
                      className={`${inputClass} mt-1`}
                      onChange={(event) => patchDraft({ name: event.target.value })}
                      value={draft.name}
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-300">
                    说明
                    <textarea
                      className={`${inputClass} mt-1 min-h-20 resize-y`}
                      onChange={(event) => patchDraft({ description: event.target.value })}
                      value={draft.description}
                    />
                  </label>
                  <label className="block text-xs font-semibold text-slate-300">
                    标签（逗号分隔）
                    <input
                      className={`${inputClass} mt-1`}
                      onChange={(event) =>
                        patchDraft({
                          tags: event.target.value
                            .split(",")
                            .map((item) => item.trim())
                            .filter(Boolean),
                        })
                      }
                      value={draft.tags.join(", ")}
                    />
                  </label>

                  <fieldset>
                    <legend className="text-xs font-semibold text-slate-300">传输</legend>
                    <div className="mt-2 grid grid-cols-3 gap-1 rounded-md bg-white/5 p-1">
                      {([
                        ["stdio", "Stdio"],
                        ["streamable_http", "HTTP"],
                        ["legacy_sse", "旧 SSE"],
                      ] as Array<[Transport, string]>).map(([value, label]) => (
                        <button
                          className={`rounded px-2 py-2 text-xs font-semibold transition ${
                            draft.connection.transport === value
                              ? "bg-cyan-300 text-slate-950"
                              : "text-slate-400 hover:bg-white/5 hover:text-white"
                          }`}
                          key={value}
                          onClick={() => patchConnection({ transport: value })}
                          type="button"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </fieldset>

                  {draft.connection.transport === "stdio" ? (
                    <>
                      <label className="block text-xs font-semibold text-slate-300">
                        已安装 MCP 项目（可选）
                        <select
                          className={`${inputClass} mt-1`}
                          onChange={(event) => {
                            const project = installedProjects.find(
                              (item) => item.project_id === event.target.value,
                            );
                            patchConnection({
                              installed_project_id: event.target.value,
                            });
                            if (project?.server_command?.length) {
                              setCommandText(
                                JSON.stringify(project.server_command, null, 2),
                              );
                            }
                          }}
                          value={draft.connection.installed_project_id}
                        >
                          <option className="bg-slate-950" value="">
                            手动配置启动命令
                          </option>
                          {installedProjects.map((project) => (
                            <option
                              className="bg-slate-950"
                              key={project.project_id}
                              value={project.project_id}
                            >
                              {project.project_id}
                              {project.npm_package ? ` · ${project.npm_package}` : ""}
                            </option>
                          ))}
                        </select>
                        <span className="mt-1 block font-normal leading-5 text-slate-500">
                          选择 `/mcps` 已安装项目后，发布版本会固定解析后的 argv。
                        </span>
                      </label>
                      <label className="block text-xs font-semibold text-slate-300">
                        启动命令（argv JSON）
                        <textarea
                          className={`${inputClass} mt-1 min-h-24 resize-y font-mono text-xs`}
                          onChange={(event) => setCommandText(event.target.value)}
                          placeholder='["npx", "-y", "@modelcontextprotocol/server-everything"]'
                          value={commandText}
                        />
                      </label>
                      <label className="block text-xs font-semibold text-slate-300">
                        MCP Sandbox 子目录（可选）
                        <input
                          className={`${inputClass} mt-1`}
                          onChange={(event) =>
                            patchConnection({ working_directory: event.target.value })
                          }
                          placeholder="project-a"
                          value={draft.connection.working_directory}
                        />
                      </label>
                    </>
                  ) : (
                    <>
                      <label className="block text-xs font-semibold text-slate-300">
                        MCP URL
                        <input
                          className={`${inputClass} mt-1`}
                          onChange={(event) => patchConnection({ url: event.target.value })}
                          placeholder="https://mcp.example.com/mcp"
                          type="url"
                          value={draft.connection.url}
                        />
                      </label>
                      <label className="block text-xs font-semibold text-slate-300">
                        网络策略
                        <select
                          className={`${inputClass} mt-1`}
                          onChange={(event) =>
                            patchConnection({
                              network_policy: event.target
                                .value as ConnectionProfile["network_policy"],
                            })
                          }
                          value={draft.connection.network_policy}
                        >
                          <option className="bg-slate-950" value="public_only">
                            仅公网，阻断私网与本机
                          </option>
                          <option className="bg-slate-950" value="trusted_private">
                            受控私网（可信管理面）
                          </option>
                        </select>
                      </label>
                    </>
                  )}

                  <div className="grid gap-3 sm:grid-cols-2">
                    <label className="block text-xs font-semibold text-slate-300">
                      工具名前缀
                      <input
                        className={`${inputClass} mt-1`}
                        onChange={(event) =>
                          patchConnection({ tool_prefix: event.target.value })
                        }
                        placeholder="research"
                        value={draft.connection.tool_prefix}
                      />
                    </label>
                    <label className="block text-xs font-semibold text-slate-300">
                      调用超时（秒）
                      <input
                        className={`${inputClass} mt-1`}
                        max={300}
                        min={5}
                        onChange={(event) =>
                          patchConnection({ timeout_seconds: Number(event.target.value) })
                        }
                        type="number"
                        value={draft.connection.timeout_seconds}
                      />
                    </label>
                  </div>

                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="flex items-center gap-2 rounded-md bg-white/[0.035] px-3 py-2 text-xs text-slate-300">
                      <input
                        checked={draft.connection.auto_reconnect}
                        onChange={(event) =>
                          patchConnection({ auto_reconnect: event.target.checked })
                        }
                        type="checkbox"
                      />
                      自动重连
                    </label>
                    <label className="flex items-center gap-2 rounded-md bg-white/[0.035] px-3 py-2 text-xs text-slate-300">
                      <input
                        checked={draft.connection.auto_start}
                        onChange={(event) =>
                          patchConnection({ auto_start: event.target.checked })
                        }
                        type="checkbox"
                      />
                      发布后自动恢复
                    </label>
                  </div>

                  <BindingEditor
                    bindings={draft.connection.headers}
                    credentials={credentials}
                    kind="headers"
                    label="Headers"
                    onAdd={() => addBinding("headers")}
                    onRemove={(index) => removeBinding("headers", index)}
                    onUpdate={(index, patch) => updateBinding("headers", index, patch)}
                  />
                  <BindingEditor
                    bindings={draft.connection.environment}
                    credentials={credentials}
                    kind="environment"
                    label="环境变量"
                    onAdd={() => addBinding("environment")}
                    onRemove={(index) => removeBinding("environment", index)}
                    onUpdate={(index, patch) => updateBinding("environment", index, patch)}
                  />

                  <details className="border-t border-white/10 pt-4">
                    <summary className="cursor-pointer text-xs font-semibold text-slate-300">
                      隐私协议与免责声明
                    </summary>
                    <label className="mt-3 block text-xs font-semibold text-slate-300">
                      隐私协议
                      <textarea
                        className={`${inputClass} mt-1 min-h-20 resize-y`}
                        onChange={(event) =>
                          patchDraft({ privacy_policy: event.target.value })
                        }
                        value={draft.privacy_policy}
                      />
                    </label>
                    <label className="mt-3 block text-xs font-semibold text-slate-300">
                      免责声明
                      <textarea
                        className={`${inputClass} mt-1 min-h-20 resize-y`}
                        onChange={(event) => patchDraft({ disclaimer: event.target.value })}
                        value={draft.disclaimer}
                      />
                    </label>
                  </details>

                  <button
                    className={`${secondaryButton} w-full`}
                    disabled={busy !== ""}
                    onClick={() => void saveDraft()}
                    type="button"
                  >
                    {busy === "save" ? "保存中..." : `保存草稿 r${draft.revision}`}
                  </button>
                </div>

                <div className="mt-7 border-t border-white/10 pt-5">
                  <h3 className="text-sm font-semibold text-white">凭据保险箱</h3>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Header 与环境变量只引用加密凭据 ID，Toolset 版本不保存明文。
                  </p>
                  <form className="mt-3 space-y-2" onSubmit={createCredential}>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <input
                        className={inputClass}
                        onChange={(event) => setCredentialName(event.target.value)}
                        placeholder="凭据名称"
                        value={credentialName}
                      />
                      <select
                        className={inputClass}
                        onChange={(event) =>
                          setCredentialKind(event.target.value as CredentialKind)
                        }
                        value={credentialKind}
                      >
                        <option className="bg-slate-950" value="header">Header</option>
                        <option className="bg-slate-950" value="environment">环境变量</option>
                        <option className="bg-slate-950" value="provider_key">Provider Key</option>
                        <option className="bg-slate-950" value="generic">通用秘密</option>
                      </select>
                    </div>
                    <input
                      autoComplete="new-password"
                      className={inputClass}
                      onChange={(event) => setCredentialValue(event.target.value)}
                      placeholder="凭据值，仅本次提交"
                      type="password"
                      value={credentialValue}
                    />
                    <button
                      className={`${secondaryButton} w-full`}
                      disabled={
                        busy === "credential" || !credentialName.trim() || !credentialValue
                      }
                      type="submit"
                    >
                      加密保存凭据
                    </button>
                  </form>
                  <div className="mt-3 divide-y divide-white/10 border-y border-white/10">
                    {credentials.map((item) => (
                      <div
                        className="flex items-center justify-between gap-3 py-2 text-xs"
                        key={item.credential_id}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-semibold text-slate-200">
                            {item.name}
                          </span>
                          <span className="text-slate-500">
                            {item.kind} · {item.masked_value}
                          </span>
                        </span>
                        <span
                          className={
                            item.status === "active" ? "text-emerald-200" : "text-rose-200"
                          }
                        >
                          {item.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </section>

              <section className="min-w-0">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                  <div>
                    <h2 className="text-base font-semibold text-white">工具配置与测试</h2>
                    <p className="mt-1 text-xs text-slate-500">
                      {draft.tools.length} 个已发现，{draft.tools.filter((tool) => tool.enabled).length} 个已启用
                    </p>
                  </div>
                  <span className="text-xs text-slate-500">Schema 仅在连接时刷新</span>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-[210px_minmax(0,1fr)]">
                  <div className="divide-y divide-white/10 border-y border-white/10">
                    {!draft.tools.length ? (
                      <p className="px-2 py-10 text-center text-xs leading-5 text-slate-500">
                        保存配置并连接 MCP Server 后，工具列表会显示在这里。
                      </p>
                    ) : null}
                    {[...draft.tools]
                      .sort(
                        (left, right) =>
                          left.order - right.order ||
                          left.original_name.localeCompare(right.original_name),
                      )
                      .map((tool) => (
                        <button
                          className={`w-full px-2 py-3 text-left transition ${
                            activeTool === tool.original_name
                              ? "bg-cyan-300/10"
                              : "hover:bg-white/[0.035]"
                          }`}
                          key={tool.original_name}
                          onClick={() => {
                            setActiveTool(tool.original_name);
                            setToolArguments(
                              JSON.stringify(tool.default_arguments || {}, null, 2),
                            );
                            setToolResult("");
                          }}
                          type="button"
                        >
                          <span className="flex items-center justify-between gap-2">
                            <span className="truncate text-xs font-semibold text-white">
                              {tool.alias || tool.original_name}
                            </span>
                            <span
                              className={`h-2 w-2 rounded-full ${
                                tool.enabled ? "bg-emerald-300" : "bg-slate-600"
                              }`}
                            />
                          </span>
                          <span className="mt-1 block truncate font-mono text-[10px] text-slate-500">
                            {tool.original_name}
                          </span>
                        </button>
                      ))}
                  </div>

                  {activeToolDefinition ? (
                    <div className="min-w-0 space-y-4">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <h3 className="truncate text-sm font-semibold text-white">
                            {activeToolDefinition.alias || activeToolDefinition.original_name}
                          </h3>
                          <p className="mt-1 truncate font-mono text-[11px] text-slate-500">
                            {activeToolDefinition.original_name}
                          </p>
                        </div>
                        <label className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                          <input
                            checked={activeToolDefinition.enabled}
                            disabled={busy !== ""}
                            onChange={(event) =>
                              void updateTool({ enabled: event.target.checked })
                            }
                            type="checkbox"
                          />
                          启用
                        </label>
                      </div>
                      <label className="block text-xs font-semibold text-slate-300">
                        Agent 别名
                        <input
                          className={`${inputClass} mt-1`}
                          defaultValue={activeToolDefinition.alias}
                          key={`${activeToolDefinition.original_name}:alias:${draft.revision}`}
                          onBlur={(event) => {
                            if (event.target.value !== activeToolDefinition.alias) {
                              void updateTool({ alias: event.target.value });
                            }
                          }}
                          placeholder={activeToolDefinition.original_name}
                        />
                      </label>
                      <label className="block text-xs font-semibold text-slate-300">
                        描述覆盖
                        <textarea
                          className={`${inputClass} mt-1 min-h-20 resize-y`}
                          defaultValue={activeToolDefinition.description}
                          key={`${activeToolDefinition.original_name}:description:${draft.revision}`}
                          onBlur={(event) => {
                            if (event.target.value !== activeToolDefinition.description) {
                              void updateTool({ description: event.target.value });
                            }
                          }}
                        />
                      </label>
                      <div>
                        <p className="text-xs font-semibold text-slate-300">参数 Schema</p>
                        <pre className="mt-1 max-h-56 overflow-auto rounded-md bg-black/25 p-3 text-[11px] leading-5 text-slate-300">
                          {JSON.stringify(activeToolDefinition.input_schema, null, 2)}
                        </pre>
                      </div>
                      <label className="block text-xs font-semibold text-slate-300">
                        默认参数 JSON
                        <textarea
                          className={`${inputClass} mt-1 min-h-24 resize-y font-mono text-xs`}
                          defaultValue={JSON.stringify(
                            activeToolDefinition.default_arguments || {},
                            null,
                            2,
                          )}
                          key={`${activeToolDefinition.original_name}:defaults:${draft.revision}`}
                          onBlur={(event) => {
                            try {
                              const value = parseJsonObject(event.target.value, "默认参数");
                              if (
                                JSON.stringify(value) !==
                                JSON.stringify(activeToolDefinition.default_arguments)
                              ) {
                                void updateTool({ default_arguments: value });
                              }
                            } catch (reason) {
                              setError(
                                reason instanceof Error ? reason.message : "默认参数无效。",
                              );
                            }
                          }}
                        />
                      </label>
                      <label className="block text-xs font-semibold text-slate-300">
                        测试参数 JSON
                        <textarea
                          className={`${inputClass} mt-1 min-h-24 resize-y font-mono text-xs`}
                          onChange={(event) => setToolArguments(event.target.value)}
                          value={toolArguments}
                        />
                      </label>
                      <button
                        className={`${primaryButton} w-full`}
                        disabled={busy !== "" || draft.runtime_status !== "connected"}
                        onClick={() => void testTool()}
                        type="button"
                      >
                        {busy === "test" ? "测试中..." : "通过 Runtime Policy 测试工具"}
                      </button>
                      {toolResult ? (
                        <div>
                          <p className="text-xs font-semibold text-slate-300">安全结果摘要</p>
                          <pre className="mt-1 max-h-44 overflow-auto rounded-md bg-black/25 p-3 text-[11px] leading-5 text-slate-300">
                            {toolResult}
                          </pre>
                        </div>
                      ) : null}
                    </div>
                  ) : (
                    <div className="flex min-h-72 items-center justify-center border border-dashed border-white/10 px-6 text-center text-xs leading-5 text-slate-500">
                      选择一个工具以查看 Schema、设置别名和执行测试。
                    </div>
                  )}
                </div>

                <div className="mt-7 border-t border-white/10 pt-5">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                    <label className="min-w-0 flex-1 text-xs font-semibold text-slate-300">
                      发布说明
                      <input
                        className={`${inputClass} mt-1`}
                        onChange={(event) => setReleaseNotes(event.target.value)}
                        placeholder="本版本启用的工具和用途"
                        value={releaseNotes}
                      />
                    </label>
                    <button
                      className={primaryButton}
                      disabled={
                        busy !== "" ||
                        draft.runtime_status !== "connected" ||
                        !draft.tools.some((tool) => tool.enabled)
                      }
                      onClick={() => void publishToolset()}
                      type="button"
                    >
                      {busy === "publish" ? "发布中..." : "发布不可变版本"}
                    </button>
                  </div>
                  <div className="mt-4 divide-y divide-white/10 border-y border-white/10">
                    {[...draft.versions].reverse().map((version) => (
                      <div
                        className="grid gap-2 py-3 text-xs sm:grid-cols-[70px_minmax(0,1fr)_150px]"
                        key={version.version}
                      >
                        <span className="font-semibold text-cyan-100">v{version.version}</span>
                        <span className="truncate text-slate-300">
                          {version.release_notes || "无发布说明"} · {version.tools.length} tools
                        </span>
                        <time className="text-slate-500">
                          {formatTime(version.published_at)}
                        </time>
                      </div>
                    ))}
                    {!draft.versions.length ? (
                      <p className="py-5 text-center text-xs text-slate-500">
                        尚未发布版本。
                      </p>
                    ) : null}
                  </div>
                </div>
              </section>
            </>
          )}
        </div>
      </div>
    </PageContainer>
  );
}

function BindingEditor({
  bindings,
  credentials,
  kind,
  label,
  onAdd,
  onRemove,
  onUpdate,
}: {
  bindings: SecretBinding[];
  credentials: CredentialSummary[];
  kind: "headers" | "environment";
  label: string;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onUpdate: (index: number, patch: Partial<SecretBinding>) => void;
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold text-slate-300">{label}</p>
        <button
          className="text-xs font-semibold text-cyan-200 hover:text-cyan-100"
          onClick={onAdd}
          type="button"
        >
          添加引用
        </button>
      </div>
      <div className="mt-2 space-y-2">
        {bindings.map((binding, index) => (
          <div
            className="grid grid-cols-[minmax(90px,0.8fr)_minmax(130px,1.2fr)_34px] gap-2"
            key={`${kind}:${index}`}
          >
            <input
              aria-label={`${label} 名称`}
              className={inputClass}
              onChange={(event) => onUpdate(index, { name: event.target.value })}
              placeholder={kind === "headers" ? "Authorization" : "API_KEY"}
              value={binding.name}
            />
            <select
              aria-label={`${label} 凭据`}
              className={inputClass}
              onChange={(event) =>
                onUpdate(index, { credential_id: event.target.value })
              }
              value={binding.credential_id}
            >
              <option className="bg-slate-950" value="">
                选择加密凭据
              </option>
              {credentials
                .filter((item) => item.status === "active")
                .map((credential) => (
                  <option
                    className="bg-slate-950"
                    key={credential.credential_id}
                    value={credential.credential_id}
                  >
                    {credential.name} · {credential.masked_value}
                  </option>
                ))}
            </select>
            <button
              aria-label={`删除 ${label} 引用`}
              className="rounded-md border border-white/10 text-slate-400 hover:bg-rose-500/10 hover:text-rose-200"
              onClick={() => onRemove(index)}
              type="button"
            >
              ×
            </button>
          </div>
        ))}
        {!bindings.length ? (
          <p className="rounded-md bg-white/[0.025] px-3 py-2 text-xs text-slate-500">
            未配置。连接时不会注入任何 {label}。
          </p>
        ) : null}
      </div>
    </div>
  );
}
