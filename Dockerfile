# ──────────────────────────────────────────────────────────────────────
# CodeAgent — Docker 镜像（pip 版）
# 本体与全部依赖（seed-kernel / seed-model-providers / seed-toolbox）均
# 从 PyPI 安装，版本与 monorepo main 对齐；无需 git clone / 编译工具链。
# ──────────────────────────────────────────────────────────────────────
ARG PYTHON_VERSION=3.11
ARG CODEAGENT_PORT=8765

FROM python:${PYTHON_VERSION}-slim

ARG CODEAGENT_PORT
ENV CODEAGENT_PORT=${CODEAGENT_PORT}
EXPOSE ${CODEAGENT_PORT}

# lxml wheel 自带二进制，系统库仅作兼容保险（极小）
# apt 源切换清华镜像加速（deb822 格式，先替换 security 再替换主源）
RUN sed -i \
        -e 's|http://deb.debian.org/debian-security|https://mirrors.tuna.tsinghua.edu.cn/debian-security|' \
        -e 's|http://deb.debian.org/debian$|https://mirrors.tuna.tsinghua.edu.cn/debian|' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

# 从 PyPI 安装本体 + 依赖（seed-kernel / seed-model-providers / seed-toolbox[code] / uvicorn）
# 使用清华 PyPI 镜像加速（PyPI 直连在国内慢）；版本固定保证可复现 + 规避 BuildKit 层缓存
RUN pip install --no-cache-dir -i https://pypi.tuna.tsinghua.edu.cn/simple tagword-codeagent==1.1.31

# 数据卷：~/.codeagent 持久化（会话、配置、记忆等）
VOLUME /root/.codeagent

# 健康检查
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:${CODEAGENT_PORT}/health')" || exit 1

# 入口
ENTRYPOINT ["codeagent", "serve", "--host", "0.0.0.0"]
