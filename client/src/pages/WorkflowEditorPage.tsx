import { useEffect } from "react";
import { Link } from "react-router-dom";
import DifyWorkspaceFrame from "../components/dify/DifyWorkspaceFrame";
import PageContainer from "../components/PageContainer";

export default function WorkflowEditorPage() {
  useEffect(() => {
    document.title = "模镜 - Dify 工作流";
  }, []);

  return (
    <PageContainer
      activeResource="agents"
      maxWidthClassName="max-w-[1760px]"
      sidebar={
        <div>
          <p className="text-sm font-semibold text-white">工作流服务台</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            当前稳定版本通过 Dify 社区版承载完整工作流能力。自研编辑器保留为经典模式，
            不影响线上可用路径。
          </p>
          <div className="mt-4 space-y-2">
            <Link
              className="block rounded-lg border border-hire-300/25 bg-hire-300/10 px-3 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
              to="/workflow"
            >
              Dify 工作流
            </Link>
            <Link
              className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
              to="/rag"
            >
              Dify 资料库
            </Link>
            <Link
              className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-brand-300/35 hover:bg-brand-300/10"
              to="/workflow/classic"
            >
              经典自研画布
            </Link>
          </div>
        </div>
      }
    >
      <header className="mb-6 overflow-hidden rounded-lg border border-hire-300/20 bg-[linear-gradient(135deg,rgba(67,20,7,0.76),rgba(6,9,22,0.94)_52%,rgba(8,51,68,0.42))] p-6 shadow-prism">
        <p className="text-sm font-semibold text-hire-100">稳定工作流引擎</p>
        <h1 className="mt-3 text-3xl font-semibold text-white sm:text-4xl">
          使用 Dify 承载完整工作流能力
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
          这条路径回到已验证的 iframe + 后端代理集成方案：模镜负责统一导航、品牌和鉴权，
          Dify 负责成熟的工作流编排、调试、发布与运行。
        </p>
      </header>

      <DifyWorkspaceFrame
        description="在 Dify 中创建、编排、调试和发布工作流。模镜保留自己的导航与服务台，保证用户仍停留在统一产品框架内。"
        section="workflow"
        title="Dify 工作流编辑器"
      />
    </PageContainer>
  );
}
