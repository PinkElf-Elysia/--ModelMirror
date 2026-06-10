export interface PlatformCapability {
  id: string;
  icon: string;
  title: string;
  summary: string;
  detail: string;
  tag: string;
  eta: string;
}

interface PlatformCapabilityCardProps {
  capability: PlatformCapability;
  onOpen: (capability: PlatformCapability) => void;
}

export default function PlatformCapabilityCard({
  capability,
  onOpen,
}: PlatformCapabilityCardProps) {
  return (
    <article className="group relative isolate flex h-full min-h-[260px] flex-col overflow-hidden rounded-lg border border-hire-300/25 bg-[linear-gradient(145deg,rgba(67,20,7,0.62),rgba(6,9,22,0.9)_52%,rgba(17,24,39,0.84))] p-5 shadow-prism transition duration-300 hover:-translate-y-1 hover:border-hire-300/55 hover:bg-surface-900/95">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_20%_15%,rgba(251,146,60,0.18),transparent_36%),radial-gradient(circle_at_80%_80%,rgba(196,181,253,0.12),transparent_34%)]" />
      <div className="relative flex items-start justify-between gap-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-hire-300/35 bg-hire-300/10 text-lg font-bold text-hire-100 shadow-[0_0_24px_rgba(251,146,60,0.14)]">
          {capability.icon}
        </span>
        <span className="rounded-full border border-white/10 bg-white/[0.055] px-2.5 py-1 text-xs font-semibold text-slate-200">
          平台能力
        </span>
      </div>

      <h2 className="relative mt-5 text-lg font-semibold text-white">
        {capability.title}
      </h2>
      <p className="relative mt-3 text-sm leading-6 text-slate-300">
        {capability.summary}
      </p>

      <div className="relative mt-5 flex flex-wrap gap-2">
        <span className="rounded-full border border-hire-300/30 bg-hire-300/10 px-2.5 py-1 text-xs font-semibold text-hire-100">
          {capability.tag}
        </span>
        <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2.5 py-1 text-xs font-semibold text-emerald-100">
          求职状态：排队入场
        </span>
      </div>

      <button
        className="relative mt-auto w-fit rounded-full border border-white/10 bg-white/[0.06] px-4 py-2 text-sm font-semibold text-slate-100 transition duration-200 hover:border-hire-300/40 hover:bg-hire-300/10 hover:text-hire-100 active:scale-[0.98]"
        onClick={() => onOpen(capability)}
        type="button"
      >
        了解更多
      </button>
    </article>
  );
}
