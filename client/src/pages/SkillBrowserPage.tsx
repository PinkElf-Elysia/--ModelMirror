import { useEffect } from "react";
import PageContainer from "../components/PageContainer";
import ResourceProjectCard from "../components/ResourceProjectCard";
import { skillProjects } from "../data/skillProjects";

const nextSkillShelves = [
  "PDF 文档处理技能",
  "PPT 生成技能",
  "表格分析技能",
  "MCP Builder 技能",
];

function formatStars(stars: number) {
  return `${(stars / 1000).toFixed(1)}k`;
}

export default function SkillBrowserPage() {
  useEffect(() => {
    document.title = "模镜 - Skill 技能货架";
  }, []);

  const totalStars = skillProjects.reduce(
    (sum, project) => sum + project.stars,
    0,
  );

  return (
    <PageContainer
      activeResource="skills"
      sidebar={
        <div>
          <p className="text-sm font-semibold text-white">技能培训清单</p>
          <p className="mt-2 text-sm leading-6 text-slate-400">
            首批上架官方示例库、开放标准和社区索引，后续再拆成更细的技能卷轴。
          </p>
          <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">已上架 Skill</p>
            <p className="mt-1 text-sm font-semibold text-hire-100">
              {skillProjects.length} 个
            </p>
          </div>
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.045] p-3">
            <p className="text-xs text-slate-400">GitHub 热度</p>
            <p className="mt-1 text-sm font-semibold text-brand-100">
              {formatStars(totalStars)} stars
            </p>
          </div>
        </div>
      }
    >
      <header className="relative overflow-hidden border-y border-hire-300/20 py-8 sm:py-10 lg:py-12">
        <div className="absolute inset-x-6 top-0 h-16 rounded-b-[50%] border-x border-b border-hire-300/30 bg-[linear-gradient(180deg,rgba(251,146,60,0.18),transparent)]" />
        <div className="absolute left-0 top-0 h-px w-full animate-pulse-line bg-[linear-gradient(90deg,transparent,rgba(251,146,60,0.82),rgba(253,186,116,0.72),transparent)]" />
        <div className="relative grid min-w-0 gap-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-end">
          <div>
            <p className="text-sm font-semibold text-hire-200">
              技能培训教室开始排课
            </p>
            <h1 className="mt-3 max-w-4xl text-4xl font-semibold tracking-normal text-white sm:text-6xl">
              Skill 技能货架
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
              Skill 像 AI 打工人的培训手册，告诉模型如何稳定完成某类工作。这里先放标准、官方示例和社区目录。
            </p>
          </div>

          <div className="surface-card rounded-lg p-4">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <span className="text-sm text-slate-400">培训货架状态</span>
              <span className="text-2xl font-semibold text-white">
                {skillProjects.length}
              </span>
            </div>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center text-xs">
              <div className="rounded-lg bg-white/[0.055] px-2 py-3">
                <p className="text-lg font-semibold text-hire-100">3</p>
                <p className="mt-1 truncate text-slate-400">已上架</p>
              </div>
              <div className="rounded-lg bg-white/[0.055] px-2 py-3">
                <p className="text-lg font-semibold text-brand-100">3</p>
                <p className="mt-1 truncate text-slate-400">来源</p>
              </div>
              <div className="rounded-lg bg-white/[0.055] px-2 py-3">
                <p className="text-lg font-semibold text-emerald-100">
                  {formatStars(totalStars)}
                </p>
                <p className="mt-1 truncate text-slate-400">热度</p>
              </div>
            </div>
          </div>
        </div>
      </header>

      <section className="mt-8">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 className="text-xl font-semibold text-white">已上架技能卷轴</h2>
            <p className="mt-1 text-sm text-slate-400">
              当前安装按钮只展示命令，不会在本地执行。
            </p>
          </div>
          <span className="w-fit rounded-full border border-emerald-300/25 bg-emerald-300/10 px-3 py-1.5 text-xs font-semibold text-emerald-100">
            全部来自真实 GitHub 仓库
          </span>
        </div>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {skillProjects.map((project) => (
            <ResourceProjectCard
              category={project.category}
              description={project.description}
              installCommand={project.installCommand}
              installNote={project.installNote}
              key={project.id}
              kind="skill"
              language={project.language}
              name={project.name}
              readmeSummary={project.readmeSummary}
              repoName={project.repoName}
              repoUrl={project.repoUrl}
              stars={project.stars}
              tags={project.tags}
              updatedAt={project.updatedAt}
            />
          ))}
        </div>
      </section>

      <section className="mt-8 rounded-lg border border-white/10 bg-white/[0.045] p-5">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-white">下批培训课预告</h2>
            <p className="mt-1 text-sm text-slate-400">
              后续会把大型仓库拆成更具体的技能卡，便于按任务直接领取。
            </p>
          </div>
          <span className="w-fit rounded-full border border-hire-300/30 bg-hire-300/10 px-3 py-1.5 text-xs font-semibold text-hire-100">
            即将到货
          </span>
        </div>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {nextSkillShelves.map((name) => (
            <div
              className="rounded-lg border border-white/10 bg-ink-950/50 p-4"
              key={name}
            >
              <p className="font-semibold text-white">{name}</p>
              <p className="mt-2 text-xs text-slate-400">课程大纲待拆分</p>
            </div>
          ))}
        </div>
      </section>
    </PageContainer>
  );
}
