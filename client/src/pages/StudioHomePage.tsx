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
            救援版本把工作流和资料库重新放回 Dify 稳定路径，自研路线只作为备用实验入口。
          </p>
          <div className="mt-4 space-y-2">
            <Link
              className="block rounded-lg border border-hire-300/25 bg-hire-300/10 px-3 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
              to="/workflow"
            >
              进入 Dify 工作流
            </Link>
            <Link
              className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
              to="/rag"
            >
              打开 Dify 资料库
            </Link>
          </div>
        </div>
      }
    >
      <header className="mb-6 overflow-hidden rounded-lg border border-hire-300/20 bg-[linear-gradient(135deg,rgba(67,20,7,0.76),rgba(6,9,22,0.94)_52%,rgba(8,51,68,0.42))] p-6 shadow-prism">
        <p className="text-sm font-semibold text-hire-100">稳定工作台</p>
        <h1 className="mt-3 text-3xl font-semibold text-white sm:text-4xl">
          模镜工作台已回退到 Dify 稳定集成
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
          这是救援后的总览页。工作流和资料库继续由 Dify 承载，未来自研替代会在
          独立路由、独立测试和可回退开关下逐步推进。
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
            <h2 className="text-xl font-semibold text-white">救援记录</h2>
            <p className="mt-1 text-sm text-slate-400">
              这里记录本次回退和后续治理动作。
            </p>
          </div>
          <Link
            className="rounded-full border border-hire-300/30 bg-hire-300/10 px-4 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
            to="/workflow/classic"
          >
            查看备用画布
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
