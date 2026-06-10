# 部署与运维指南

## 环境类型

| 环境 | 用途 | 特点 |
| --- | --- | --- |
| 本地开发 | 日常开发调试 | Vite + Uvicorn 热更新，Dify 可选。 |
| 测试环境 | 功能验收 | 应使用独立 API Key 和 Dify 工作空间。 |
| 生产环境 | 对外服务 | 前端静态部署，后端容器化，Dify 独立部署。 |

## 前端部署

构建：

```bash
cd client
npm run build
```

产物目录：

```text
client/dist/
```

可部署到：

- Nginx
- Vercel / Netlify
- 对象存储 + CDN
- Docker Nginx 镜像

Nginx SPA 回退示例：

```nginx
server {
  listen 80;
  server_name modelmirror.example.com;
  root /usr/share/nginx/html;

  location / {
    try_files $uri $uri/ /index.html;
  }

  location /api/ {
    proxy_pass http://modelmirror-server:8000;
    proxy_http_version 1.1;
    proxy_buffering off;
  }
}
```

## 后端部署

本地：

```bash
cd server
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

生产建议：

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
```

注意：流式接口对反向代理 buffering 敏感，Nginx 需要关闭 `proxy_buffering`。

## Docker Compose

项目根目录已有 `docker-compose.yml`：

```bash
docker compose -p modelmirror up --build -d
```

服务：

- `modelmirror-server`：FastAPI，端口 `8000`。
- `modelmirror-client`：前端静态站点，端口 `5173` 映射到容器内 `80`。

停止：

```bash
docker compose -p modelmirror down
```

## Dify 部署

Dify 建议使用官方 Docker Compose 单独部署。模镜只依赖：

- Dify Web：默认 `http://localhost:3000`
- Dify API：默认 `http://localhost:5001/v1`
- Dify App API Key：写入 `server/.env`

升级 Dify 前注意：

1. 备份 Dify PostgreSQL 和文件存储。
2. 阅读 Dify release notes，确认 API 兼容性。
3. 在测试环境验证 `/workflow` 和 `/rag` iframe 是否仍可加载。
4. 验证 `/api/dify/health`、`/api/dify/workflow/run`。

## 环境变量安全

- `.env` 不得提交到 Git。
- GitHub Actions 或云平台使用 Secrets 管理。
- 不要把 `OPENROUTER_API_KEY`、`DIFY_API_KEY` 写入前端。
- 生产环境建议按环境拆分：
  - `OPENROUTER_API_KEY`
  - `DIFY_API_KEY`
  - `ALLOWED_ORIGINS`
  - `OPENROUTER_HTTP_REFERER`

## 日志与监控

最低限度建议：

- 后端访问日志：请求路径、状态码、耗时。
- 外部 API 错误日志：状态码和脱敏错误消息。
- Dify 健康检查：`/api/dify/health`。
- OpenRouter 错误率：按模型统计失败率。
- 前端错误监控：后续可接 Sentry。

## 健康检查

后端：

```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/dify/health
```

前端：

```bash
curl -I http://localhost:5173/models
curl -I http://localhost:5173/workflow
curl -I http://localhost:5173/rag
```

## 回滚策略

- 前端：保留上一版静态产物或镜像 tag。
- 后端：保留上一版 Docker image。
- Dify：升级前备份数据库和文件存储，必要时回滚 Dify 容器版本。
- 工作流/RAG 主路径不得被未验证自研实现替换。

最后更新日期：2026-06-10  
维护人：模镜团队
