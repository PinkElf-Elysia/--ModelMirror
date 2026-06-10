import { Link } from "react-router-dom";

interface CapabilityItem {
  icon: string;
  title: string;
  description: string;
  badge: string;
  href?: string;
  actionLabel?: string;
}

const capabilities: CapabilityItem[] = [
  {
    icon: "🧩",
    title: "Dify 工作流",
    description: "稳定版本继续通过 Dify 承载工作流编排、调试、发布和运行。",
    badge: "稳定接入",
    href: "/workflow",
    actionLabel: "进入工作流",
  },
  {
    icon: "📚",
    title: "RAG 资料库",
    description: "文档上传、切分、检索测试和知识库问答由 Dify 知识库提供。",
    badge: "稳定接入",
    href: "/rag",
    actionLabel: "打开资料库",
  },
  {
    icon: "⚙️",
    title: "系统设置",
    description: "偏好设置、通知管理和账号配置继续保留在服务台规划区。",
    badge: "预留",
  },
];

interface SystemCapabilityBarProps {
  compact?: boolean;
}

function CapabilityBadge({ badge }: { badge: string }) {
  return (
    <span className="rounded-full border border-white/10 bg-white/[0.055] px-2 py-0.5 text-[11px] font-medium text-slate-300">
      {badge}
    </span>
  );
}

function CapabilityCard({ item }: { item: CapabilityItem }) {
  const content = (
    <div className="rounded-lg border border-white/10 bg-white/[0.045] p-3 transition duration-200 hover:border-hire-300/30 hover:bg-hire-300/10">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-hire-300/25 bg-hire-300/10 text-sm font-semibold text-hire-100">
          {item.icon}
        </span>
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white">{item.title}</p>
          <div className="mt-1">
            <CapabilityBadge badge={item.badge} />
          </div>
        </div>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-400">{item.description}</p>
      {item.href && item.actionLabel ? (
        <span className="mt-3 inline-flex rounded-full border border-hire-300/25 bg-hire-300/10 px-2.5 py-1 text-xs font-semibold text-hire-100">
          {item.actionLabel}
        </span>
      ) : null}
    </div>
  );

  if (item.href) {
    return (
      <Link className="block" to={item.href}>
        {content}
      </Link>
    );
  }

  return content;
}

export default function SystemCapabilityBar({
  compact = false,
}: SystemCapabilityBarProps) {
  if (compact) {
    return (
      <details className="surface-panel rounded-lg p-4 xl:hidden">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-semibold text-white">
          <span>服务台 · 更多能力</span>
          <span className="rounded-full border border-hire-300/30 bg-hire-300/10 px-2.5 py-1 text-xs text-hire-100">
            Dify 稳定接入
          </span>
        </summary>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {capabilities.map((item) => (
            <CapabilityCard item={item} key={item.title} />
          ))}
        </div>
      </details>
    );
  }

  return (
    <section>
      <div className="flex items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-white">模镜服务台</p>
          <p className="mt-1 text-xs leading-5 text-slate-400">
            工作流和资料库已回退到 Dify 稳定集成，其他能力继续按模块扩展。
          </p>
        </div>
        <span className="rounded-full border border-hire-300/30 bg-hire-300/10 px-2.5 py-1 text-xs font-semibold text-hire-100">
          稳定路径
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {capabilities.map((item) => (
          <CapabilityCard item={item} key={item.title} />
        ))}
      </div>
    </section>
  );
}
