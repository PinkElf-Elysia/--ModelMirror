import { memo } from "react";
import { type AgentProfile } from "../data/agents";

interface AgentCardProps {
  agent: AgentProfile;
  isExpanded: boolean;
  onInterview: (agent: AgentProfile) => void;
  onToggleDetails: (agentId: string) => void;
}

function sourceTone(source: AgentProfile["source"]) {
  return source === "原创"
    ? "border-hire-300/35 bg-hire-300/10 text-hire-100"
    : "border-brand-300/30 bg-brand-300/10 text-brand-100";
}

const AgentCard = memo(function AgentCard({
  agent,
  isExpanded,
  onInterview,
  onToggleDetails,
}: AgentCardProps) {
  return (
    <article className="group relative isolate flex h-full min-h-[300px] flex-col overflow-hidden rounded-lg border border-white/10 bg-ink-950/76 p-5 shadow-prism backdrop-blur-xl transition duration-300 ease-out hover:-translate-y-1 hover:border-hire-300/45 hover:bg-surface-900/90">
      <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-[linear-gradient(110deg,rgba(251,146,60,0.18),rgba(36,217,255,0.08),transparent)] opacity-80" />
      <div className="relative flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-hire-300/30 bg-hire-300/10 text-xl font-semibold text-hire-100 shadow-[0_0_24px_rgba(251,146,60,0.12)]">
            {agent.name.slice(0, 1)}
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-white/10 bg-white/[0.055] px-2.5 py-1 text-xs font-medium text-slate-300">
                {agent.department}
              </span>
              <span
                className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${sourceTone(agent.source)}`}
              >
                {agent.source}
              </span>
            </div>
            <h2 className="mt-3 line-clamp-2 text-lg font-semibold leading-6 text-white">
              {agent.name}
            </h2>
          </div>
        </div>

        <span className="shrink-0 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2.5 py-1 text-xs font-semibold text-emerald-100">
          随时到岗
        </span>
      </div>

      <p className="relative mt-4 line-clamp-4 text-sm leading-6 text-slate-300">
        {agent.expertise}
      </p>

      <div className="relative mt-5 grid grid-cols-2 gap-3 text-sm">
        <div className="rounded-lg border border-white/10 bg-white/[0.045] p-3">
          <p className="text-xs text-slate-400">适用场景</p>
          <p className="mt-1 line-clamp-2 font-medium text-slate-100">
            {agent.scenarios}
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.045] p-3">
          <p className="text-xs text-slate-400">人气指数</p>
          <p className="mt-1 font-semibold text-hire-100">
            {agent.popularity}
            <span className="ml-1 text-xs font-normal text-slate-500">/100</span>
          </p>
        </div>
      </div>

      {isExpanded ? (
        <div className="relative mt-4 max-h-60 overflow-y-auto rounded-lg border border-white/10 bg-slate-950/55 p-3 text-xs leading-5 text-slate-300">
          <p className="mb-2 font-semibold text-white">完整简历摘要</p>
          <p className="whitespace-pre-wrap">
            {agent.prompt.slice(0, 1200)}
            {agent.prompt.length > 1200 ? "\n\n..." : ""}
          </p>
          <a
            className="mt-3 inline-flex text-brand-100 underline-offset-4 transition hover:text-brand-50 hover:underline"
            href={agent.sourceUrl}
            rel="noreferrer"
            target="_blank"
          >
            查看来源文件
          </a>
        </div>
      ) : null}

      <div className="relative mt-auto flex flex-wrap items-center gap-2 pt-5">
        <button
          className="rounded-full border border-white/10 bg-white/[0.055] px-4 py-2 text-sm font-semibold text-slate-100 transition duration-200 hover:border-brand-300/35 hover:bg-brand-300/10 hover:text-brand-100 active:scale-[0.98]"
          onClick={() => onToggleDetails(agent.id)}
          type="button"
        >
          {isExpanded ? "收起简历" : "查看简历"}
        </button>
        <button
          className="rounded-full bg-hire-300 px-4 py-2 text-sm font-semibold text-ink-950 shadow-[0_0_22px_rgba(251,146,60,0.18)] transition duration-200 hover:bg-hire-200 active:scale-[0.98]"
          onClick={() => onInterview(agent)}
          type="button"
        >
          立即面试
        </button>
        <span className="ml-auto rounded-full border border-lime-300/25 bg-lime-300/10 px-2.5 py-1 text-xs font-semibold text-lime-100">
          期望薪资 N/A
        </span>
      </div>
    </article>
  );
});

export default AgentCard;
