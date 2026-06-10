export type StudioAppKind = "workflow" | "dataset" | "chat" | "agent";

export interface StudioAppRecord {
  id: string;
  name: string;
  kind: StudioAppKind;
  icon: string;
  status: "stable" | "fallback" | "planned";
  description: string;
  href: string;
  tags: string[];
}

export interface StudioActivityRecord {
  id: string;
  title: string;
  detail: string;
  at: string;
}

export interface StudioState {
  apps: StudioAppRecord[];
  activities: StudioActivityRecord[];
}

export function createInitialStudioState(): StudioState {
  const now = new Date().toISOString();

  return {
    apps: [
      {
        id: "dify-workflow",
        name: "Dify 工作流",
        kind: "workflow",
        icon: "🧩",
        status: "stable",
        description: "通过 Dify 社区版提供成熟的工作流编排、调试、发布和运行能力。",
        href: "/workflow",
        tags: ["工作流", "稳定接入"],
      },
      {
        id: "dify-datasets",
        name: "Dify 资料库",
        kind: "dataset",
        icon: "📚",
        status: "stable",
        description: "通过 Dify 知识库提供文档上传、切分、检索测试和 RAG 问答。",
        href: "/rag",
        tags: ["RAG", "知识库"],
      },
      {
        id: "classic-canvas",
        name: "经典自研画布",
        kind: "workflow",
        icon: "🛠️",
        status: "fallback",
        description: "保留早期 React Flow MVP 作为实验入口，不再承担主路径稳定性。",
        href: "/workflow/classic",
        tags: ["实验", "备用"],
      },
    ],
    activities: [
      {
        id: "activity-dify-rollback",
        title: "工作流和资料库已回退到 Dify 稳定集成",
        detail: "主入口重新使用 iframe + 后端代理方案，自研替代路线暂缓到设计和测试补齐之后。",
        at: now,
      },
      {
        id: "activity-docs",
        title: "新增失败复盘与重试路线文档",
        detail: "后续自研工作流必须按里程碑推进，并与 Dify 稳定路径并行运行。",
        at: now,
      },
    ],
  };
}

export function readStudioState(): StudioState {
  return createInitialStudioState();
}
