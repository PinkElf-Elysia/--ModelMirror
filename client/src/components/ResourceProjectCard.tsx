import { useState } from "react";

interface ResourceProjectCardProps {
  kind: "mcp" | "skill";
  name: string;
  repoName: string;
  repoUrl: string;
  description: string;
  readmeSummary: string;
  stars: number;
  language: string;
  updatedAt: string;
  installCommand: string;
  installNote: string;
  tags: string[];
  category?: string;
}

function formatStars(stars: number) {
  if (stars >= 1000) return `${(stars / 1000).toFixed(1)}k`;
  return stars.toLocaleString("zh-CN");
}

function tone(kind: ResourceProjectCardProps["kind"]) {
  return kind === "mcp"
    ? {
        label: "万能工具招领",
        icon: "工",
        badge: "border-brand-300/30 bg-brand-300/10 text-brand-100",
        button:
          "bg-brand-300 text-ink-950 hover:bg-brand-200 shadow-[0_0_24px_rgba(34,211,238,0.18)]",
      }
    : {
        label: "技能货架",
        icon: "技",
        badge: "border-hire-300/30 bg-hire-300/10 text-hire-100",
        button:
          "bg-hire-300 text-ink-950 hover:bg-hire-200 shadow-[0_0_24px_rgba(251,146,60,0.18)]",
      };
}

export default function ResourceProjectCard({
  kind,
  name,
  repoName,
  repoUrl,
  description,
  readmeSummary,
  stars,
  language,
  updatedAt,
  installCommand,
  installNote,
  tags,
  category,
}: ResourceProjectCardProps) {
  const [isInstallOpen, setIsInstallOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const style = tone(kind);

  async function copyInstallCommand() {
    await navigator.clipboard.writeText(installCommand);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <>
      <article className="group relative isolate flex h-full min-h-[360px] flex-col overflow-hidden rounded-lg border border-white/10 bg-ink-950/78 p-5 shadow-prism transition duration-300 hover:-translate-y-1 hover:border-hire-300/40 hover:bg-surface-900/92">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_12%,rgba(251,146,60,0.16),transparent_34%),radial-gradient(circle_at_82%_82%,rgba(36,217,255,0.13),transparent_36%)] opacity-80" />
        <div className="relative flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.06] text-lg font-semibold text-white">
              {style.icon}
            </span>
            <div className="min-w-0">
              <div className="flex flex-wrap gap-2">
                <span
                  className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${style.badge}`}
                >
                  {category ?? style.label}
                </span>
                <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2.5 py-1 text-xs font-semibold text-emerald-100">
                  已上架
                </span>
              </div>
              <h2 className="mt-3 line-clamp-2 text-xl font-semibold leading-7 text-white">
                {name}
              </h2>
              <a
                className="mt-1 inline-flex text-xs text-slate-400 underline-offset-4 transition hover:text-brand-100 hover:underline"
                href={repoUrl}
                rel="noreferrer"
                target="_blank"
              >
                {repoName}
              </a>
            </div>
          </div>
          <span className="rounded-full border border-white/10 bg-white/[0.055] px-2.5 py-1 text-xs font-semibold text-slate-200">
            {formatStars(stars)} stars
          </span>
        </div>

        <p className="relative mt-5 text-sm leading-6 text-slate-300">
          {description}
        </p>

        <div className="relative mt-5 rounded-lg border border-white/10 bg-white/[0.045] p-3">
          <p className="text-xs font-semibold text-slate-200">README 摘要</p>
          <p className="mt-2 line-clamp-4 text-xs leading-5 text-slate-400">
            {readmeSummary}
          </p>
        </div>

        <div className="relative mt-4 grid grid-cols-2 gap-3 text-sm">
          <div className="rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">主要语言</p>
            <p className="mt-1 font-semibold text-white">{language}</p>
          </div>
          <div className="rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">最近更新</p>
            <p className="mt-1 font-semibold text-white">{updatedAt}</p>
          </div>
        </div>

        <div className="relative mt-4 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <span
              className="rounded-full border border-white/10 bg-white/[0.055] px-2.5 py-1 text-xs font-medium text-slate-300"
              key={tag}
            >
              {tag}
            </span>
          ))}
        </div>

        <div className="relative mt-auto flex flex-wrap items-center gap-2 pt-5">
          <button
            className={`rounded-full px-4 py-2 text-sm font-semibold transition duration-200 active:scale-[0.98] ${style.button}`}
            onClick={() => setIsInstallOpen(true)}
            type="button"
          >
            ⚡ 安装
          </button>
          <a
            className="rounded-full border border-white/10 bg-white/[0.055] px-4 py-2 text-sm font-semibold text-slate-100 transition duration-200 hover:border-brand-300/35 hover:bg-brand-300/10 hover:text-brand-100"
            href={repoUrl}
            rel="noreferrer"
            target="_blank"
          >
            打开仓库
          </a>
        </div>
      </article>

      {isInstallOpen ? (
        <div
          aria-modal="true"
          className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/78 p-4 backdrop-blur-sm"
          role="dialog"
        >
          <div className="surface-card w-full max-w-2xl rounded-lg p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="text-sm font-semibold text-hire-100">
                  安装指令
                </p>
                <h2 className="mt-2 text-2xl font-semibold text-white">
                  {name}
                </h2>
              </div>
              <button
                aria-label="关闭安装说明"
                className="rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-sm font-semibold text-slate-200 transition hover:bg-white/10"
                onClick={() => setIsInstallOpen(false)}
                type="button"
              >
                关闭
              </button>
            </div>
            <p className="mt-4 text-sm leading-6 text-slate-300">
              {installNote}
            </p>
            <pre className="mt-4 max-h-72 overflow-auto rounded-lg border border-white/10 bg-slate-950/78 p-4 text-xs leading-5 text-brand-100">
              <code>{installCommand}</code>
            </pre>
            <button
              className="mt-4 rounded-full bg-hire-300 px-4 py-2 text-sm font-semibold text-ink-950 transition hover:bg-hire-200 active:scale-[0.98]"
              onClick={() => void copyInstallCommand()}
              type="button"
            >
              {copied ? "已复制" : "复制安装命令"}
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
