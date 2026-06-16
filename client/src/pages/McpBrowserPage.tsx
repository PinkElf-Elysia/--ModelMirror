import { useEffect } from "react";
import McpServerCard from "../components/McpServerCard";
import PageContainer from "../components/PageContainer";
import { mcpProjects } from "../data/mcpProjects";

const nextMcpShelves = [
  "Markitdown MCP",
  "Chrome DevTools MCP",
  "Notion MCP Server",
  "DBHub",
];

function formatStars(stars: number) {
  return `${(stars / 1000).toFixed(1)}k`;
}

export default function McpBrowserPage() {
  useEffect(() => {
    document.title = "模镜 - MCP 工具采购";
  }, []);

  const totalStars = mcpProjects.reduce((sum, project) => sum + project.stars, 0);
  const connectableCount = mcpProjects.filter((project) => project.command?.length).length;

  return (
    <PageContainer
      activeResource="mcps"
      sidebar={
        <div>
          <p className="text-sm font-semibold text-white">工具采购清单</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            首批上架浏览器自动化、最新文档和 GitHub 协作三类 MCP 工具。
          </p>
          <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">已上架工具</p>
            <p className="mt-1 text-sm font-semibold text-hire-100">
              {mcpProjects.length} 个
            </p>
          </div>
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">GitHub 热度</p>
            <p className="mt-1 text-sm font-semibold text-brand-100">
              {formatStars(totalStars)} stars
            </p>
          </div>
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">可原生连接</p>
            <p className="mt-1 text-sm font-semibold text-emerald-100">
              {connectableCount} 个
            </p>
          </div>
        </div>
      }
    >
      <header className="relative overflow-hidden border-y border-hire-300/20 py-8 sm:py-10 lg:py-12">
        <div className="absolute inset-x-6 top-0 h-16 rounded-b-[50%] border-x border-b border-hire-300/30 bg-[linear-gradient(180deg,rgba(251,146,60,0.18),transparent)]" />
        <div className="absolute left-0 top-0 h-px w-full animate-pulse-line bg-[linear-gradient(90deg,transparent,rgba(251,146,60,0.82),rgba(253,186,116,0.72),transparent)]" />
        <div className="relative grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-end">
          <div>
            <p className="text-sm font-semibold text-hire-200">
              万能工具招领处开张
            </p>
            <h1 className="mt-3 max-w-4xl text-4xl font-semibold tracking-normal text-white sm:text-6xl">
              MCP 工具采购
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
              这里陈列可接入 AI 工作流的 MCP 工具箱。先上架最常用的浏览器、文档和 GitHub 协作工具，后续继续补货。
            </p>
          </div>

          <div className="surface-card rounded-lg p-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <span className="text-sm text-slate-400">采购台状态</span>
              <span className="text-2xl font-semibold text-white">
                {mcpProjects.length}
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-white/[0.055] px-2 py-3">
                <p className="text-lg font-semibold text-hire-100">3</p>
                <p className="mt-1 truncate text-slate-400">已验货</p>
              </div>
              <div className="rounded-lg bg-white/[0.055] px-2 py-3">
                <p className="text-lg font-semibold text-brand-100">2</p>
                <p className="mt-1 truncate text-slate-400">安装方式</p>
              </div>
              <div className="rounded-lg bg-white/[0.055] px-2 py-3">
                <p className="text-lg font-semibold text-emerald-100">
                  {connectableCount}
                </p>
                <p className="mt-1 truncate text-slate-400">可连接</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="mt-8">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">已上架工具箱</h2>
            <p className="mt-1 text-sm text-slate-400">
              点击“连接”即可由后端以 stdio 启动 MCP Server；连接后可查看工具、填写参数并执行。
            </p>
          </div>
          <span className="w-fit rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 text-xs font-semibold text-emerald-100">
            {connectableCount} 个支持原生连接
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {mcpProjects.map((project) => (
            <McpServerCard key={project.id} project={project} />
          ))}
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-white/10 bg-white/[0.045] p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">下批货架预告</h2>
            <p className="mt-1 text-sm text-slate-400">
              这些工具正在验货，确认安装方式后再上架。
            </p>
          </div>
          <span className="w-fit rounded-full border border-hire-300/30 bg-hire-300/10 px-3 py-1.5 text-xs font-semibold text-hire-100">
            即将到货
          </span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {nextMcpShelves.map((name) => (
            <div
              className="rounded-lg border border-white/10 bg-ink-950/50 p-4"
              key={name}
            >
              <p className="font-semibold text-white">{name}</p>
              <p className="mt-2 text-xs text-slate-400">货架编号待确认</p>
            </div>
          ))}
        </div>
      </section>
    </PageContainer>
  );
}
