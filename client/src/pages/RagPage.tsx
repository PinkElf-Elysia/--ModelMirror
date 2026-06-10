import { useEffect } from "react";
import { Link } from "react-router-dom";
import DifyWorkspaceFrame from "../components/dify/DifyWorkspaceFrame";
import PageContainer from "../components/PageContainer";

export default function RagPage() {
  useEffect(() => {
    document.title = "模镜 - Dify 资料库";
  }, []);

  return (
    <PageContainer
      activeResource="prompts"
      maxWidthClassName="max-w-[1760px]"
      sidebar={
        <div>
          <p className="text-sm font-semibold text-white">资料库服务台</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            稳定版本继续使用 Dify 知识库能力，覆盖文档上传、分段、检索测试和 RAG 应用。
          </p>
          <div className="mt-4 space-y-2">
            <Link
              className="block rounded-lg border border-hire-300/25 bg-hire-300/10 px-3 py-2 text-sm font-semibold text-hire-100 transition hover:bg-hire-300/20"
              to="/rag"
            >
              Dify 资料库
            </Link>
            <Link
              className="block rounded-lg border border-white/10 bg-white/[0.045] px-3 py-2 text-sm font-semibold text-slate-200 transition hover:border-hire-300/35 hover:bg-hire-300/10"
              to="/workflow"
            >
              Dify 工作流
            </Link>
          </div>
        </div>
      }
    >
      <header className="mb-6 overflow-hidden rounded-lg border border-hire-300/20 bg-[linear-gradient(135deg,rgba(67,20,7,0.76),rgba(6,9,22,0.94)_52%,rgba(8,51,68,0.42))] p-6 shadow-prism">
        <p className="text-sm font-semibold text-hire-100">RAG 资料库</p>
        <h1 className="mt-3 text-3xl font-semibold text-white sm:text-4xl">
          使用 Dify 知识库承载文档检索与问答
        </h1>
        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-300">
          回退后的稳定方案不再自研知识库管道。文档解析、切分、索引和检索测试继续交给
          Dify 处理，模镜只做统一入口和后端代理。
        </p>
      </header>

      <DifyWorkspaceFrame
        description="在 Dify 资料库中上传文档、维护分段、测试检索，并把知识库用于聊天与工作流。"
        section="datasets"
        title="Dify 知识库管理"
      />
    </PageContainer>
  );
}
