export interface McpProject {
  id: string;
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
  command?: string[];
  tags: string[];
}

export const mcpProjects: McpProject[] = [
  {
    id: "playwright-mcp",
    name: "Playwright MCP",
    repoName: "microsoft/playwright-mcp",
    repoUrl: "https://github.com/microsoft/playwright-mcp",
    description:
      "把浏览器自动化、测试和网页数据抽取能力交给 AI，适合前端验证和网页操作。",
    readmeSummary:
      "README 说明该 MCP Server 使用 Playwright 的结构化可访问性快照，让 LLM 无需视觉模型也能操作网页，主打快速、轻量、确定性的工具调用。",
    stars: 33615,
    language: "TypeScript",
    updatedAt: "2026-06-08",
    installCommand:
      '{\n  "mcpServers": {\n    "playwright": {\n      "command": "npx",\n      "args": ["@playwright/mcp@latest"]\n    }\n  }\n}',
    installNote: "官方 README 提供的标准 MCP 客户端配置，适合大多数支持 MCP 的工具。",
    command: ["npx", "-y", "@playwright/mcp@latest"],
    tags: ["浏览器自动化", "测试", "网页抽取"],
  },
  {
    id: "context7",
    name: "Context7",
    repoName: "upstash/context7",
    repoUrl: "https://github.com/upstash/context7",
    description:
      "给 coding agent 拉取最新库文档和代码示例，减少过期 API 和幻觉答案。",
    readmeSummary:
      "README 说明 Context7 会把最新、按版本匹配的文档与代码示例直接放进提示词上下文，支持 CLI + Skills 和 MCP 两种模式。",
    stars: 56974,
    language: "TypeScript",
    updatedAt: "2026-06-08",
    installCommand: "npx ctx7 setup",
    installNote:
      "官方推荐使用 ctx7 CLI 一键配置，可选择 CLI + Skills 或 MCP 模式；手动 MCP URL 为 https://mcp.context7.com/mcp。",
    command: ["npx", "-y", "@upstash/context7-mcp"],
    tags: ["最新文档", "代码生成", "MCP/Skill 双模式"],
  },
  {
    id: "github-mcp-server",
    name: "GitHub MCP Server",
    repoName: "github/github-mcp-server",
    repoUrl: "https://github.com/github/github-mcp-server",
    description:
      "把仓库、Issue、PR、Actions 和代码上下文接入 AI，适合研发协作与 CI 排障。",
    readmeSummary:
      "README 说明这是 GitHub 官方 MCP Server，可让 AI 工具直接读取仓库、管理 Issue/PR、分析代码并自动化工作流。",
    stars: 30510,
    language: "Go",
    updatedAt: "2026-06-08",
    installCommand:
      '{\n  "servers": {\n    "github": {\n      "type": "http",\n      "url": "https://api.githubcopilot.com/mcp/"\n    }\n  }\n}',
    installNote:
      "官方 README 推荐优先使用远程 GitHub MCP Server；不支持远程 MCP 的宿主可改用本地版本。",
    tags: ["GitHub 官方", "PR/Issue", "CI/CD"],
  },
  {
    id: "filesystem-mcp",
    name: "Filesystem MCP",
    repoName: "modelcontextprotocol/servers",
    repoUrl: "https://github.com/modelcontextprotocol/servers",
    description:
      "把受控目录内的文件读写、目录浏览等能力交给 AI，适合在沙盒里做资料整理和文件操作演示。",
    readmeSummary:
      "官方 npm 包描述为 MCP server for filesystem access。模镜后端会把它限制在 server/mcp/sandboxes 工作目录内，避免访问项目根目录或用户私人文件。",
    stars: 0,
    language: "TypeScript",
    updatedAt: "2026-06-16",
    installCommand:
      "npx -y @modelcontextprotocol/server-filesystem <allowed-directory>",
    installNote:
      "本地 stdio 模式需要传入允许访问的目录。模镜后端统一在 server/mcp/sandboxes 下启动，因此这里只暴露沙盒目录。",
    command: ["npx", "-y", "@modelcontextprotocol/server-filesystem", "."],
    tags: ["官方示例", "文件系统", "沙盒工具"],
  },
];
