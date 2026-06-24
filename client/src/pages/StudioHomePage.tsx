import { useEffect, useMemo } from "react";
import { Link } from "react-router-dom";
import PageContainer from "../components/PageContainer";
import { readStudioState, type StudioAppRecord } from "../data/studio";

function statusCopy(status: StudioAppRecord["status"]) {
  if (status === "stable") return "稳定接入";
  if (status === "fallback") return "备用入口";
  return "规划中";
}

function statusClass(status: StudioAppRecord["status"]) {
  if (status === "stable") {
    return "border-emerald-300/25 bg-emerald-300/10 text-emerald-100";
  }
  if (status === "fallback") {
    return "border-hire-300/30 bg-hire-300/10 text-hire-100";
  }
  return "border-white/10 bg-white/[0.055] text-slate-300";
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "刚刚";
  return date.toLocaleDateString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function StudioAppCard({ app }: { app: StudioAppRecord }) {
  return (
    <Link
      className="block rounded-lg border border-white/10 bg-ink-950/72 p-4 shadow-prism transition duration-200 hover:-translate-y-0.5 hover:border-hire-300/40 hover:bg-surface-900/88"
      to={app.href}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-hire-300/25 bg-hire-300/10 text-lg">
            {app.icon}
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-semibold text-white">{app.name}</h3>
            <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-400">
              {app.description}
            </p>
          </div>
        </div>
        <span className={`shrink-0 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${statusClass(app.status)}`}>
          {statusCopy(app.status)}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        {app.tags.map((tag) => (
          <span
            className="rounded-full border border-white/10 bg-white/[0.055] px-2.5 py-1 text-[11px] text-slate-300"
            key={tag}
          >
            {tag}
          </span>
        ))}
      </div>
    </Link>
  );
}

export default function StudioHomePage() {
  const state = useMemo(() => readStudioState(), []);

  useEffect(() => {
    document.title = "模镜 - 工作台总览";
  }, []);

  return (
    <PageContainer
      activeResource="agents"
      maxWidthClassName="max-w-[1760px]"
      sidebar={
        <div>
          <p className="text-sm font-semibold text-white">工作台入口</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            工作流默认使用经典自研画布，RAG本地知识库已开放，其他能力按模块持续扩展。
          </p>
          <div className="mt-4 space-y-2">
            <Link
              className="block rounded-lg border border-hire-300/25 bg-hire-300/10 px-3 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
              to="/workflow"
            >
              进入经典工作流
            </Link>
            <Link
              className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
              to="/rag"
            >
              打开本地知识库
            </Link>
          </div>
        </div>
      }
    >
      <header className="mb-6 overflow-hidden rounded-lg border border-hire-300/20 bg-[linear-gradient(135deg,rgba(67,20,7,0.76),rgba(6,9,22,0.94)_52%,rgba(8,51,68,0.42))] p-6 shadow-prism">
        <p className="text-sm font-semibold text-hire-100">本地工作台</p>
        <h1 className="mt-3 text-3xl font-semibold text-white sm:text-4xl">
          模镜工作台已切换到本地能力
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
          工作流由经典自研画布承载，RAG 资料库使用本地知识库链路。后续能力继续按模块推进，
          保持独立测试和可回退开关。
        </p>
      </header>

      <div className="grid gap-4 md:grid-cols-3">
        {state.apps.map((app) => (
          <StudioAppCard app={app} key={app.id} />
        ))}
      </div>

      <section className="surface-card mt-6 rounded-lg p-5">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-white">迭代记录</h2>
            <p className="mt-1 text-sm text-slate-400">
              这里记录本地工作流、RAG 与工具能力的推进状态。
            </p>
          </div>
          <Link
            className="rounded-full border border-hire-300/30 bg-hire-300/10 px-4 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
            to="/workflow/classic"
          >
            查看经典画布
          </Link>
        </div>

        <div className="mt-5 space-y-3">
          {state.activities.map((activity) => (
            <article
              className="rounded-lg border border-white/10 bg-white/[0.045] p-4"
              key={activity.id}
            >
              <div className="flex items-center justify-between gap-3">
                <h3 className="text-sm font-semibold text-white">{activity.title}</h3>
                <span className="rounded-full border border-white/10 bg-white/[0.055] px-2.5 py-1 text-[11px] text-slate-300">
                  {formatDate(activity.at)}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-slate-400">
                {activity.detail}
              </p>
            </article>
          ))}
        </div>
      </section>
    </PageContainer>
  );
}
