export interface SkillInstallSource {
  repoUrl: string;
  subPath: string;
}

export interface SkillProject {
  id: string;
  name: string;
  repoName: string;
  repoUrl: string;
  category: string;
  description: string;
  readmeSummary: string;
  stars: number;
  language: string;
  updatedAt: string;
  installCommand: string;
  installNote: string;
  installSource?: SkillInstallSource;
  tags: string[];
}

export const skillProjects: SkillProject[] = [
  {
    id: "anthropic-pdf-skill",
    name: "PDF 文档处理技能",
    repoName: "anthropics/skills",
    repoUrl: "https://github.com/anthropics/skills",
    category: "文档处理",
    description:
      "让模型按标准流程处理 PDF：抽取内容、整理结构、摘要重点，适合合同、论文、报告和说明书。",
    readmeSummary:
      "Anthropic 官方 Skills 示例库中的 PDF 技能，目录包含 SKILL.md 与相关脚本资源，可作为文档解析类技能的基础模板。",
    stars: 147754,
    language: "Markdown / Python",
    updatedAt: "2026-06-08",
    installCommand:
      "git clone --depth 1 --filter=blob:none --sparse https://github.com/anthropics/skills\ncd skills\ngit sparse-checkout set skills/pdf",
    installNote: "模镜会通过后端 Skill 管理器执行 sparse checkout，只安装 skills/pdf 子目录。",
    installSource: {
      repoUrl: "https://github.com/anthropics/skills",
      subPath: "skills/pdf",
    },
    tags: ["官方示例", "PDF", "文档摘要"],
  },
  {
    id: "anthropic-xlsx-skill",
    name: "XLSX 表格处理技能",
    repoName: "anthropics/skills",
    repoUrl: "https://github.com/anthropics/skills",
    category: "数据办公",
    description:
      "让模型理解电子表格任务：读取工作簿、解释数据、辅助分析和生成表格处理建议。",
    readmeSummary:
      "Anthropic 官方 Skills 示例库中的 XLSX 技能，面向 Excel 和电子表格工作流，可作为财务、运营、数据分析任务的技能模板。",
    stars: 147754,
    language: "Markdown / Python",
    updatedAt: "2026-06-08",
    installCommand:
      "git clone --depth 1 --filter=blob:none --sparse https://github.com/anthropics/skills\ncd skills\ngit sparse-checkout set skills/xlsx",
    installNote: "模镜会通过后端 Skill 管理器执行 sparse checkout，只安装 skills/xlsx 子目录。",
    installSource: {
      repoUrl: "https://github.com/anthropics/skills",
      subPath: "skills/xlsx",
    },
    tags: ["官方示例", "Excel", "数据分析"],
  },
  {
    id: "mattpocock-tdd-skill",
    name: "TypeScript TDD 技能",
    repoName: "mattpocock/skills",
    repoUrl: "https://github.com/mattpocock/skills",
    category: "工程开发",
    description:
      "把 AI 训练成更稳的 TypeScript 工程搭档，强调测试先行、逐步实现和代码质量反馈。",
    readmeSummary:
      "Matt Pocock 的 Skills 仓库面向工程实践，engineering/tdd 技能聚焦测试驱动开发，适合让模型按红绿重构节奏协助写代码。",
    stars: 2100,
    language: "Markdown / TypeScript",
    updatedAt: "2026-06-08",
    installCommand:
      "git clone --depth 1 --filter=blob:none --sparse https://github.com/mattpocock/skills\ncd skills\ngit sparse-checkout set skills/engineering/tdd",
    installNote:
      "模镜会通过后端 Skill 管理器执行 sparse checkout，只安装 skills/engineering/tdd 子目录。",
    installSource: {
      repoUrl: "https://github.com/mattpocock/skills",
      subPath: "skills/engineering/tdd",
    },
    tags: ["TypeScript", "TDD", "工程质量"],
  },
  {
    id: "agent-skills-standard",
    name: "Agent Skills 开放标准",
    repoName: "agentskills/agentskills",
    repoUrl: "https://github.com/agentskills/agentskills",
    category: "开放标准",
    description:
      "定义 Skill 文件夹结构、SKILL.md 元数据和渐进加载方式，适合团队统一扩展包格式。",
    readmeSummary:
      "Agent Skills 是轻量开放格式，核心是包含 SKILL.md 的文件夹，也可携带脚本、参考资料、模板和资源。",
    stars: 20110,
    language: "Markdown",
    updatedAt: "2026-06-08",
    installCommand:
      "git clone https://github.com/agentskills/agentskills.git\n# 参考 template 目录创建内部 Skill",
    installNote:
      "这是规范与模板仓库，不是单个可安装 Skill；适合团队参考并创建自己的技能包。",
    tags: ["开放标准", "模板", "规范"],
  },
];

