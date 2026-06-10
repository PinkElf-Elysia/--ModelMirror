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
  tags: string[];
}

export const skillProjects: SkillProject[] = [
  {
    id: "anthropic-skills",
    name: "Anthropic Agent Skills",
    repoName: "anthropics/skills",
    repoUrl: "https://github.com/anthropics/skills",
    category: "官方技能库",
    description:
      "官方示例库，覆盖文档、创意、开发、企业流程等可复用 Skill。",
    readmeSummary:
      "README 说明 Skills 是包含说明、脚本和资源的文件夹，Claude 会按需加载它们来完成专业任务；仓库包含 document-skills、example-skills、规范和模板。",
    stars: 147754,
    language: "Python",
    updatedAt: "2026-06-08",
    installCommand:
      "/plugin marketplace add anthropics/skills\n/plugin install document-skills@anthropic-agent-skills\n/plugin install example-skills@anthropic-agent-skills",
    installNote:
      "官方 README 给出了 Claude Code 插件市场安装方式，也可直接浏览 skills/docx、skills/pdf、skills/pptx、skills/xlsx 等目录。",
    tags: ["官方", "文档处理", "示例技能"],
  },
  {
    id: "agent-skills-standard",
    name: "Agent Skills 标准",
    repoName: "agentskills/agentskills",
    repoUrl: "https://github.com/agentskills/agentskills",
    category: "开放标准",
    description:
      "定义 Skill 文件夹结构、元数据和渐进加载机制，适合团队统一技能格式。",
    readmeSummary:
      "README 说明 Agent Skills 是一种轻量开放格式，核心是包含 SKILL.md 的文件夹，也可携带脚本、参考资料、模板和资产。",
    stars: 20110,
    language: "Python",
    updatedAt: "2026-06-08",
    installCommand:
      "git clone https://github.com/agentskills/agentskills.git\n# 参考 spec 与 template 目录创建自己的 Skill",
    installNote:
      "该仓库是规范和文档，不是单个可执行 Skill；适合复制 template 并按标准创建内部技能。",
    tags: ["开放标准", "模板", "规范"],
  },
  {
    id: "awesome-claude-skills",
    name: "Awesome Claude Skills",
    repoName: "ComposioHQ/awesome-claude-skills",
    repoUrl: "https://github.com/ComposioHQ/awesome-claude-skills",
    category: "社区索引",
    description:
      "社区精选 Skill 和插件索引，适合按文档、开发、数据、营销等场景找灵感。",
    readmeSummary:
      "README 介绍这是 1000+ 生产可用 Claude Skills 和插件的 curated list，覆盖 Claude.ai、Claude Code、Codex、Cursor、Gemini CLI 等 coding agent。",
    stars: 63669,
    language: "Python",
    updatedAt: "2026-06-08",
    installCommand:
      "git clone https://github.com/ComposioHQ/awesome-claude-skills.git\n# 按 README 分类选择需要的 Skill 或插件",
    installNote:
      "这是技能索引，不是单一安装包；页面会优先引导用户复制仓库并按分类挑选。",
    tags: ["社区精选", "1000+ 技能", "跨工具"],
  },
];
