# ──────────────────────────────────────────────────────────────────────
# CodeAgent — Docker 镜像
# 多阶段构建：Builder 阶段安装依赖，Runtime 阶段最小化镜像
# ──────────────────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.11
ARG CODEAGENT_PORT=8765

# ============================================================
# Stage 1: Builder — 克隆 monorepo 兄弟包 + 安装项目依赖
# ============================================================
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /build

# 系统构建依赖（git 用于克隆，gcc 用于编译 C 扩展如 lxml）
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY . /build/codeagent/

# 克隆 monorepo 兄弟包（seed、seed-model-providers、seed-tools）
# 这些不在 PyPI 上，必须从 GitHub 克隆
RUN set -eux; \
    MONO=/build; \
    for pkg in seed-model-providers seed seed-tools; do \
        dest="$MONO/$pkg"; \
        echo "==> Cloning $pkg ..."; \
        git clone --depth 1 "https://github.com/tagword/${pkg}.git" "$dest"; \
    done

# 安装所有包（先兄弟包再自己）
RUN pip install --no-cache-dir -e /build/seed-model-providers && \
    pip install --no-cache-dir -e /build/seed && \
    pip install --no-cache-dir -e "/build/seed-tools[code]" && \
    pip install --no-cache-dir -e /build/codeagent

# ============================================================
# Stage 2: Runtime — 最小镜像，只保留运行所需
# ============================================================
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG CODEAGENT_PORT
ENV CODEAGENT_PORT=${CODEAGENT_PORT}
EXPOSE ${CODEAGENT_PORT}

# 运行时系统依赖（仅 libxml2 for lxml，不需要 build-essential）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制已安装的 Python 包
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages/
COPY --from=builder /usr/local/bin /usr/local/bin/

# 复制项目文件（运行时需要 web/static 等静态资源）
COPY --from=builder /build/codeagent /app

WORKDIR /app

# 数据卷：~/.codeagent 持久化（会话、配置、记忆等）
VOLUME /root/.codeagent

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${CODEAGENT_PORT}/health')" || exit 1

# 入口
ENTRYPOINT ["codeagent", "serve", "--host", "0.0.0.0"]
