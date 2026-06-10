import { useEffect, useMemo, useState } from "react";

type DifySection = "workflow" | "datasets";

interface DifyWorkspaceFrameProps {
  section: DifySection;
  title: string;
  description: string;
}

const DEFAULT_DIFY_WEB_URL = "http://localhost:3000";

function trimTrailingSlash(value: string) {
  return value.replace(/\/+$/, "");
}

function sectionPath(section: DifySection) {
  if (section === "datasets") return "/datasets";
  return "/apps";
}

export default function DifyWorkspaceFrame({
  section,
  title,
  description,
}: DifyWorkspaceFrameProps) {
  const [loaded, setLoaded] = useState(false);

  const frameSrc = useMemo(() => {
    const baseUrl = trimTrailingSlash(
      import.meta.env.VITE_DIFY_WEB_URL || DEFAULT_DIFY_WEB_URL,
    );
    const url = new URL(`${baseUrl}${sectionPath(section)}`);
    url.searchParams.set("embed", "true");
    url.searchParams.set("hide_nav", "true");
    url.searchParams.set("source", "modelmirror");
    return url.toString();
  }, [section]);

  useEffect(() => {
    setLoaded(false);
  }, [frameSrc]);

  return (
    <section className="overflow-hidden rounded-lg border border-hire-300/20 bg-ink-950/82 shadow-prism">
      <div className="flex flex-col gap-3 border-b border-white/10 bg-white/[0.035] px-4 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-hire-100">
            Dify 集成模式
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-white">{title}</h1>
          <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-400">
            {description}
          </p>
        </div>
        <a
          className="inline-flex items-center justify-center rounded-full border border-hire-300/30 bg-hire-300/10 px-4 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
          href={frameSrc}
          rel="noreferrer"
          target="_blank"
        >
          新窗口打开
        </a>
      </div>

      <div className="relative h-[calc(100vh-230px)] min-h-[620px] bg-slate-950">
        {!loaded ? (
          <div className="absolute inset-0 z-10 flex items-center justify-center bg-slate-950">
            <div className="w-full max-w-md rounded-lg border border-white/10 bg-white/[0.045] p-5 text-center">
              <div className="mx-auto h-10 w-10 animate-pulse rounded-full border border-hire-300/35 bg-hire-300/15" />
              <p className="mt-4 text-sm font-semibold text-white">
                正在连接 Dify 工作台
              </p>
              <p className="mt-2 text-xs leading-5 text-slate-400">
                如果长时间空白，请确认本地 Dify Web 服务已启动，并检查
                <code className="mx-1 rounded bg-white/10 px-1 py-0.5">
                  VITE_DIFY_WEB_URL
                </code>
                配置。
              </p>
            </div>
          </div>
        ) : null}
        <iframe
          className="h-full w-full border-0"
          onLoad={() => setLoaded(true)}
          sandbox="allow-downloads allow-forms allow-modals allow-popups allow-popups-to-escape-sandbox allow-same-origin allow-scripts"
          src={frameSrc}
          title={title}
        />
      </div>
    </section>
  );
}
