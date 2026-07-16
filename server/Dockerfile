FROM registry.cn-hangzhou.aliyuncs.com/metad/xpert-api:latest AS node_runtime

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY --from=node_runtime /usr/local/bin/node /usr/local/bin/node
COPY --from=node_runtime /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
COPY THIRD_PARTY_NOTICES.md /usr/share/doc/modelmirror/THIRD_PARTY_NOTICES.md
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY data ./data
COPY api ./api
COPY mcp ./mcp
COPY registry ./registry
COPY rag ./rag
COPY skills ./skills
COPY xperts ./xperts
COPY workflow_native ./workflow_native
COPY xpert_runtime ./xpert_runtime
COPY meta_agent ./meta_agent

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
