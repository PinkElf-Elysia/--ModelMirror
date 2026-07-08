import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import PageContainer from "../components/PageContainer";
import { agents } from "../data/agents";
import { mcpProjects } from "../data/mcpProjects";
import { skillProjects } from "../data/skillProjects";

type WorkspaceCategory =
  | "all"
  | "agents"
  | "workflow"
  | "knowledge"
  | "mcp"
  | "skills"
  | "prompts"
  | "environment"
  | "runs";

type Tone = "ready" | "partial" | "planned" | "error";

interface Loadable<T> {
  data: T;
  error: string;
  loading: boolean;
}

interface KnowledgeBasePayload {
  id: string;
  name: string;
}

interface FileAssetPayload {
  file_asset_id?: string;
  file_name?: string;
  filename?: string;
  name?: string;
}

interface ArtifactPayload {
  artifact_id: string;
  title: string;
  chunk_count?: number;
}

interface McpSessionPayload {
  session_id: string;
  server_name?: string | null;
  server_id?: string | null;
  status?: string | null;
}

interface RegistryToolPayload {
  name: string;
  server_id: string;
}

interface InstalledSkillPayload {
  skill_id: string;
  name: string;
  description: string;
}

interface RuntimeRunPayload {
  run_id: string;
  run_type: string;
  status: string;
  title: string;
  created_at: number;
  updated_at: number;
}

interface ResourceCardModel {
  actionLabel: string;
  category: Exclude<WorkspaceCategory, "all">;
  count: string;
  description: string;
  error?: string;
  href: string;
  icon: string;
  id: string;
  items: string[];
  loading?: boolean;
  metricLabel: string;
  status: string;
  title: string;
  tone: Tone;
}

const categories: Array<{ key: WorkspaceCategory; label: string }> = [
  { key: "all", label: "全部" },
  { key: "agents", label: "数字专家" },
  { key: "workflow", label: "工作流" },
  { key: "knowledge", label: "知识库" },
  { key: "mcp", label: "MCP 工具集" },
  { key: "skills", label: "Skill" },
  { key: "prompts", label: "提示词" },
  { key: "environment", label: "环境" },
  { key: "runs", label: "运行记录" },
];

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

function createLoadable<T>(data: T): Loadable<T> {
  return { data, error: "", loading: true };
}

async function fetchJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`请求失败：${response.status}`);
  }
  return response.json() as Promise<T>;
}

function toneClass(tone: Tone) {
  if (tone === "ready") {
    return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100";
  }
  if (tone === "partial") {
    return "border-hire-300/30 bg-hire-300/10 text-hire-100";
  }
  if (tone === "error") {
    return "border-rose-300/30 bg-rose-300/10 text-rose-100";
  }
  return "border-white/10 bg-white/[0.055] text-slate-300";
}

function formatRunTime(value: number) {
  if (!Number.isFinite(value)) return "刚刚";
  const timestamp = value > 10_000_000_000 ? value : value * 1000;
  return dateFormatter.format(new Date(timestamp));
}

function compactItems(items: string[]) {
  return items.filter(Boolean).slice(0, 4);
}

function ResourceCard({ card }: { card: ResourceCardModel }) {
  const visibleItems = compactItems(card.items);

  return (
    <article className="rounded-lg border border-white/10 bg-ink-950/72 p-4 shadow-prism transition duration-200 hover:-translate-y-0.5 hover:border-hire-300/35 hover:bg-surface-900/88">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-hire-300/25 bg-hire-300/10 text-sm font-semibold text-hire-100">
            {card.icon}
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-sm font-semibold text-white">{card.title}</h2>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">
              {card.description}
            </p>
          </div>
        </div>
        <span
          className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClass(
            card.error ? "error" : card.tone,
          )}`}
        >
          {card.error ? "暂不可用" : card.status}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-[minmax(0,1fr)_auto] items-end gap-3 border-t border-white/10 pt-4">
        <div>
          <p className="text-[11px] text-slate-500">{card.metricLabel}</p>
          <p className="mt-1 text-2xl font-semibold text-white">
            {card.loading ? "..." : card.count}
          </p>
        </div>
        <Link
          className="rounded-full border border-hire-300/25 bg-hire-300/10 px-3 py-1.5 text-xs font-semibold text-hire-100 transition hover:bg-hire-300/20"
          to={card.href}
        >
          {card.actionLabel}
        </Link>
      </div>

      {card.error ? (
        <p className="mt-3 rounded-lg border border-rose-300/20 bg-rose-300/10 px-3 py-2 text-xs leading-5 text-rose-100">
          {card.error}
        </p>
      ) : visibleItems.length > 0 ? (
        <ul className="mt-3 space-y-2">
          {visibleItems.map((item) => (
            <li className="truncate text-xs text-slate-400" key={item}>
              {item}
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-3 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-slate-400">
          暂无最近项目，进入模块后可继续创建或连接资源。
        </p>
      )}
    </article>
  );
}

function WorkspaceSidebar() {
  return (
    <div>
      <p className="text-sm font-semibold text-white">工作空间</p>
      <p className="mt-2 text-sm leading-6 text-slate-400">
        先把现有资源集中到一个入口，再逐步对齐 Xpert Studio、Toolset、知识流水线和运行运维。
      </p>
      <div className="mt-4 space-y-2">
        <Link
          className="block rounded-lg border border-hire-300/25 bg-hire-300/10 px-3 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
          to="/workflow"
        >
          打开工作流画布
        </Link>
        <Link
          className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
          to="/agents/meta-agent"
        >
          进入任务工作台
        </Link>
        <Link
          className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
          to="/mcps"
        >
          管理 MCP 工具
        </Link>
      </div>
    </div>
  );
}

export default function StudioHomePage() {
  const [activeCategory, setActiveCategory] = useState<WorkspaceCategory>("all");
  const [searchTerm, setSearchTerm] = useState("");
  const [knowledgeBases, setKnowledgeBases] = useState(
    createLoadable<KnowledgeBasePayload[]>([]),
  );
  const [fileAssets, setFileAssets] = useState(createLoadable<FileAssetPayload[]>([]));
  const [artifacts, setArtifacts] = useState(createLoadable<ArtifactPayload[]>([]));
  const [mcpSessions, setMcpSessions] = useState(createLoadable<McpSessionPayload[]>([]));
  const [registryTools, setRegistryTools] = useState(
    createLoadable<RegistryToolPayload[]>([]),
  );
  const [installedSkills, setInstalledSkills] = useState(
    createLoadable<InstalledSkillPayload[]>([]),
  );
  const [runtimeRuns, setRuntimeRuns] = useState(createLoadable<RuntimeRunPayload[]>([]));

  useEffect(() => {
    document.title = "模镜 - Xpert 工作空间";
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadKnowledge() {
      try {
        const [kbData, assetData, artifactData] = await Promise.all([
          fetchJson<{ knowledge_bases: KnowledgeBasePayload[] }>(
            "/api/rag/knowledge_bases",
          ),
          fetchJson<{ assets: FileAssetPayload[] }>("/api/rag/pipeline/assets"),
          fetchJson<{ artifacts: ArtifactPayload[] }>("/api/rag/pipeline/artifacts"),
        ]);
        if (cancelled) return;
        setKnowledgeBases({
          data: kbData.knowledge_bases ?? [],
          error: "",
          loading: false,
        });
        setFileAssets({ data: assetData.assets ?? [], error: "", loading: false });
        setArtifacts({ data: artifactData.artifacts ?? [], error: "", loading: false });
      } catch (error) {
        if (cancelled) return;
        const message =
          error instanceof Error ? error.message : "知识库资源加载失败";
        setKnowledgeBases({ data: [], error: message, loading: false });
        setFileAssets({ data: [], error: message, loading: false });
        setArtifacts({ data: [], error: message, loading: false });
      }
    }

    async function loadMcp() {
      try {
        const [sessionsData, toolsData] = await Promise.all([
          fetchJson<{ sessions: McpSessionPayload[] }>("/api/mcp/sessions"),
          fetchJson<{ tools: RegistryToolPayload[] }>("/api/registry/tools"),
        ]);
        if (cancelled) return;
        setMcpSessions({ data: sessionsData.sessions ?? [], error: "", loading: false });
        setRegistryTools({ data: toolsData.tools ?? [], error: "", loading: false });
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "MCP 运行态加载失败";
        setMcpSessions({ data: [], error: message, loading: false });
        setRegistryTools({ data: [], error: message, loading: false });
      }
    }

    async function loadSkills() {
      try {
        const data = await fetchJson<{ skills: InstalledSkillPayload[] }>(
          "/api/skills/installed",
        );
        if (cancelled) return;
        setInstalledSkills({ data: data.skills ?? [], error: "", loading: false });
      } catch (error) {
        if (cancelled) return;
        setInstalledSkills({
          data: [],
          error: error instanceof Error ? error.message : "Skill 加载失败",
          loading: false,
        });
      }
    }

    async function loadRuns() {
      try {
        const data = await fetchJson<RuntimeRunPayload[]>("/api/runtime/runs?limit=8");
        if (cancelled) return;
        setRuntimeRuns({ data: data ?? [], error: "", loading: false });
      } catch (error) {
        if (cancelled) return;
        setRuntimeRuns({
          data: [],
          error: error instanceof Error ? error.message : "运行记录加载失败",
          loading: false,
        });
      }
    }

    void loadKnowledge();
    void loadMcp();
    void loadSkills();
    void loadRuns();

    return () => {
      cancelled = true;
    };
  }, []);

  const resourceCards = useMemo<ResourceCardModel[]>(() => {
    const knowledgeError =
      knowledgeBases.error || fileAssets.error || artifacts.error || "";
    const mcpError = mcpSessions.error || registryTools.error || "";

    return [
      {
        actionLabel: "查看专家",
        category: "agents",
        count: String(agents.length),
        description: "本地智能体市场与元智能体任务工作台入口。",
        href: "/agents",
        icon: "智",
        id: "agents",
        items: agents.slice(0, 4).map((agent) => agent.name),
        metricLabel: "可用智能体",
        status: "可用",
        title: "数字专家",
        tone: "ready",
      },
      {
        actionLabel: "打开画布",
        category: "workflow",
        count: "2",
        description: "经典画布与 native 实验线，承载 Agent、Handoff、Toolset 与 RAG 节点。",
        href: "/workflow",
        icon: "流",
        id: "workflow",
        items: ["classic /workflow", "workflow-native validate", "节点运行观测", "RunRegistry"],
        metricLabel: "工作流入口",
        status: "部分实现",
        title: "工作流",
        tone: "partial",
      },
      {
        actionLabel: "打开知识库",
        category: "knowledge",
        count: knowledgeError ? "0" : String(knowledgeBases.data.length),
        description: "本地 RAG 知识库、FileAsset、Artifact 与 CitationAnchor 只读视图。",
        error: knowledgeError,
        href: "/rag",
        icon: "知",
        id: "knowledge",
        items: knowledgeError
          ? []
          : [
              ...knowledgeBases.data.map((kb) => kb.name),
              `${fileAssets.data.length} 个 FileAsset`,
              `${artifacts.data.length} 个 Artifact`,
            ],
        loading: knowledgeBases.loading || fileAssets.loading || artifacts.loading,
        metricLabel: "知识库",
        status: "部分实现",
        title: "知识库",
        tone: "partial",
      },
      {
        actionLabel: "管理 MCP",
        category: "mcp",
        count: mcpError ? "0" : String(registryTools.data.length),
        description: "MCP Server 会话、全局工具注册表和 Runtime Toolset 的入口。",
        error: mcpError,
        href: "/mcps",
        icon: "MCP",
        id: "mcp",
        items: mcpError
          ? []
          : [
              `${mcpSessions.data.length} 个运行会话`,
              `${mcpProjects.length} 个候选工具箱`,
              ...registryTools.data.map((tool) => tool.name),
            ],
        loading: mcpSessions.loading || registryTools.loading,
        metricLabel: "已注册工具",
        status: "部分实现",
        title: "MCP 工具集",
        tone: "partial",
      },
      {
        actionLabel: "查看 Skill",
        category: "skills",
        count: installedSkills.error ? "0" : String(installedSkills.data.length),
        description: "Skill 市场、已安装技能和仓库安装能力。",
        error: installedSkills.error,
        href: "/skills",
        icon: "技",
        id: "skills",
        items: installedSkills.error
          ? []
          : [
              ...installedSkills.data.map((skill) => skill.name),
              `${skillProjects.length} 个市场候选技能`,
            ],
        loading: installedSkills.loading,
        metricLabel: "已安装",
        status: "部分实现",
        title: "Skill",
        tone: "partial",
      },
      {
        actionLabel: "查看提示词",
        category: "prompts",
        count: "规划中",
        description: "对齐 Xpert 提示词与 Slash Command 工作流，当前先保留入口。",
        href: "/prompts",
        icon: "词",
        id: "prompts",
        items: ["审查", "解释", "测试", "调试", "总结"],
        metricLabel: "工作区提示词",
        status: "待接入",
        title: "提示词",
        tone: "planned",
      },
      {
        actionLabel: "进入设置",
        category: "environment",
        count: "Default",
        description: "环境变量、模型网关和运行依赖入口，后续对齐 Xpert 环境页。",
        href: "/settings",
        icon: "ENV",
        id: "environment",
        items: ["OpenRouter / newAPI 网关", "Docker runtime", "MCP / Skill 依赖"],
        metricLabel: "当前环境",
        status: "规划中",
        title: "环境",
        tone: "planned",
      },
      {
        actionLabel: "查看运行",
        category: "runs",
        count: runtimeRuns.error ? "0" : String(runtimeRuns.data.length),
        description: "RunRegistry 内存态索引，汇总 workflow、chat、agent_task 与 handoff run。",
        error: runtimeRuns.error,
        href: "/workflow",
        icon: "观",
        id: "runs",
        items: runtimeRuns.error
          ? []
          : runtimeRuns.data.map((run) => `${run.run_type} · ${run.status}`),
        loading: runtimeRuns.loading,
        metricLabel: "最近运行",
        status: "可观测",
        title: "运行记录",
        tone: "partial",
      },
    ];
  }, [
    artifacts,
    fileAssets,
    installedSkills,
    knowledgeBases,
    mcpSessions,
    registryTools,
    runtimeRuns,
  ]);

  const filteredCards = useMemo(() => {
    const normalizedSearch = searchTerm.trim().toLowerCase();
    return resourceCards.filter((card) => {
      const matchesCategory =
        activeCategory === "all" || card.category === activeCategory;
      const matchesSearch =
        normalizedSearch.length === 0 ||
        [card.title, card.description, card.status, card.count, ...card.items]
          .join(" ")
          .toLowerCase()
          .includes(normalizedSearch);
      return matchesCategory && matchesSearch;
    });
  }, [activeCategory, resourceCards, searchTerm]);

  return (
    <PageContainer
      maxWidthClassName="max-w-[1760px]"
      sidebar={<WorkspaceSidebar />}
    >
      <header className="mb-6 border-y border-hire-300/20 py-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-hire-300/30 bg-hire-300/10 px-3 py-1 text-xs font-semibold text-hire-100">
                Xpert 对齐工作空间 Beta
              </span>
              <span className="rounded-full border border-white/10 bg-white/[0.055] px-3 py-1 text-xs text-slate-300">
                React / FastAPI 原生实现
              </span>
            </div>
            <h1 className="mt-3 text-2xl font-semibold text-white sm:text-3xl">
              组织工作空间
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              聚合智能体、知识库、工具集、Skill、提示词、环境和运行记录。这里先做只读总览，
              后续再接 Xpert Studio 画布、节点注册表和配置侧栏。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              className="rounded-full bg-hire-300 px-4 py-2 text-sm font-semibold text-ink-950 transition hover:bg-hire-200"
              to="/workflow"
            >
              创建工作流
            </Link>
            <Link
              className="rounded-full border border-white/10 bg-white/[0.055] px-4 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
              to="/agents/meta-agent"
            >
              打开任务工作台
            </Link>
          </div>
        </div>
      </header>

      <section className="mb-5 grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-center">
        <div className="flex min-w-0 flex-wrap gap-2">
          {categories.map((category) => (
            <button
              className={`rounded-full border px-3 py-2 text-sm font-semibold transition ${
                activeCategory === category.key
                  ? "border-hire-300 bg-hire-300 text-ink-950"
                  : "border-white/10 bg-white/[0.045] text-slate-300 hover:border-hire-300/35 hover:bg-hire-300/10 hover:text-hire-100"
              }`}
              key={category.key}
              onClick={() => setActiveCategory(category.key)}
              type="button"
            >
              {category.label}
            </button>
          ))}
        </div>
        <label className="relative block">
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-xs font-semibold text-slate-400">
            搜索
          </span>
          <input
            className="h-11 w-full rounded-lg border border-white/10 bg-ink-950/72 pl-12 pr-3 text-sm text-white outline-none transition placeholder:text-slate-500 hover:border-white/20 focus:border-hire-300/70 focus:ring-4 focus:ring-hire-300/10"
            onChange={(event) => setSearchTerm(event.target.value)}
            placeholder="资源、状态、运行类型"
            type="search"
            value={searchTerm}
          />
        </label>
      </section>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section>
          {filteredCards.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
              {filteredCards.map((card) => (
                <ResourceCard card={card} key={card.id} />
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-white/10 bg-white/[0.045] p-8 text-center">
              <p className="text-sm font-semibold text-white">没有匹配的资源</p>
              <p className="mt-2 text-sm text-slate-400">
                换一个分类或搜索词，资源入口仍然保留在顶部导航中。
              </p>
            </div>
          )}
        </section>

        <aside className="space-y-4">
          <section className="rounded-lg border border-white/10 bg-ink-950/72 p-4 shadow-prism">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-semibold text-white">运行观测摘要</h2>
                <p className="mt-1 text-xs text-slate-400">
                  最近 8 条 RunRegistry 记录。
                </p>
              </div>
              <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${toneClass(runtimeRuns.error ? "error" : "partial")}`}>
                {runtimeRuns.error ? "暂不可用" : "内存态"}
              </span>
            </div>
            {runtimeRuns.error ? (
              <p className="mt-4 rounded-lg border border-rose-300/20 bg-rose-300/10 px-3 py-2 text-xs leading-5 text-rose-100">
                {runtimeRuns.error}
              </p>
            ) : runtimeRuns.loading ? (
              <p className="mt-4 text-sm text-slate-400">运行记录加载中...</p>
            ) : runtimeRuns.data.length > 0 ? (
              <div className="mt-4 space-y-3">
                {runtimeRuns.data.slice(0, 8).map((run) => (
                  <article
                    className="rounded-lg border border-white/10 bg-white/[0.045] p-3"
                    key={run.run_id}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="truncate text-xs font-semibold text-white">
                        {run.title || run.run_type}
                      </p>
                      <span className="shrink-0 rounded-full border border-white/10 bg-white/[0.055] px-2 py-0.5 text-[11px] text-slate-300">
                        {run.status}
                      </span>
                    </div>
                    <p className="mt-2 text-xs text-slate-500">
                      {run.run_type} · {formatRunTime(run.updated_at ?? run.created_at)}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="mt-4 rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-slate-400">
                暂无运行记录。运行工作流或开启 Chat Toolset 后会出现在这里。
              </p>
            )}
          </section>

          <section className="rounded-lg border border-white/10 bg-white/[0.045] p-4">
            <h2 className="text-sm font-semibold text-white">下一步对齐</h2>
            <ol className="mt-3 space-y-2 text-xs leading-5 text-slate-400">
              <li>1. 节点注册表与 Xpert 分类菜单</li>
              <li>2. 智能体配置侧栏分区</li>
              <li>3. 知识流水线可视化草稿</li>
              <li>4. Runtime Ops 与环境观测</li>
            </ol>
          </section>
        </aside>
      </div>
    </PageContainer>
  );
}
