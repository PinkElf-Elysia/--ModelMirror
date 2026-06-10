import { Link } from "react-router-dom";
import BrandLogo from "./BrandLogo";

interface FloatingDockProps {
  active: "models" | "agents" | "chat";
}

export default function FloatingDock({ active }: FloatingDockProps) {
  const linkClass = (isActive: boolean) =>
    `rounded-full px-4 py-2 text-sm font-semibold transition duration-200 ${
      isActive
        ? "bg-brand-300 text-ink-950 shadow-neon"
        : "text-slate-300 hover:bg-white/10 hover:text-white"
    }`;

  return (
    <nav className="fixed inset-x-0 bottom-4 z-40 mx-auto flex w-[calc(100%-2rem)] max-w-xl items-center justify-between rounded-full border border-white/10 bg-ink-950/80 px-3 py-2 shadow-dock backdrop-blur-2xl">
      <BrandLogo compact />
      <div className="flex items-center gap-1">
        <Link
          aria-current={active === "models" ? "page" : undefined}
          className={linkClass(active === "models")}
          to="/models"
        >
          招聘会
        </Link>
        <Link
          aria-current={active === "agents" ? "page" : undefined}
          className={linkClass(active === "agents")}
          to="/agents"
        >
          人才市场
        </Link>
        <span
          aria-current={active === "chat" ? "page" : undefined}
          className={linkClass(active === "chat")}
        >
          面试间
        </span>
      </div>
    </nav>
  );
}
