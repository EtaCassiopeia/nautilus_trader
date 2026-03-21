# ---------------------------------------------------------------------------
#  NautilusTrader + AI Agent Control Plane
#
#  Multi-stage build:
#    1. builder   — compiles Cython extensions and Rust libraries
#    2. runtime   — slim image with compiled packages + API/MCP/CLI deps
# ---------------------------------------------------------------------------
# Pin to specific digest for supply-chain security (python:3.13-slim as of 2025-11-29)
FROM python@sha256:326df678c20c78d465db501563f3492d17c42a4afe33a1f2bf5406a1d56b0e86 AS base
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    PYO3_PYTHON="/usr/local/bin/python3" \
    PYSETUP_PATH="/opt/pysetup" \
    RUSTUP_TOOLCHAIN="stable" \
    BUILD_MODE="release" \
    CC="clang"
ENV PATH="/root/.local/bin:/root/.cargo/bin:$PATH"
WORKDIR $PYSETUP_PATH

# ── builder ────────────────────────────────────────────────────────────────
FROM base AS builder

RUN apt-get update && \
    apt-get install -y curl clang git make pkg-config capnproto libcapnp-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Rust
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y

# UV
COPY uv-version ./
RUN UV_VERSION=$(cat uv-version) && curl -LsSf https://astral.sh/uv/$UV_VERSION/install.sh | sh

# Python dependencies (cached layer)
COPY uv.lock pyproject.toml build.py ./
RUN uv sync --no-install-package nautilus_trader

# Install extra deps for API / MCP / CLI / Agent
RUN uv pip install --system \
    "fastapi>=0.115,<1.0.0" \
    "uvicorn>=0.34,<1.0.0" \
    "orjson>=3.10,<4.0.0" \
    "httpx>=0.28,<1.0.0" \
    "mcp>=1.0,<2.0.0" \
    "anthropic>=0.45,<1.0.0" \
    "starlette>=0.45,<1.0.0" \
    "websockets>=14.0,<15.0.0"

# Rust workspace build
COPY Cargo.toml Cargo.lock ./
COPY crates ./crates
RUN cargo build --lib --release --all-features

# Build nautilus_trader wheel
COPY nautilus_trader ./nautilus_trader
COPY README.md ./
RUN uv build --wheel
RUN uv pip install --system dist/*.whl
RUN find /usr/local/lib/python3.13/site-packages -name "*.pyc" -exec rm -f {} \;

# ── runtime ────────────────────────────────────────────────────────────────
FROM base AS runtime

COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# Copy deploy configs and scripts
COPY deploy/configs /opt/nautilus/configs
COPY deploy/scripts /opt/nautilus/scripts
RUN chmod +x /opt/nautilus/scripts/*.sh

# Health check against the API server
HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=3 \
    CMD python3 -c "import httpx; r=httpx.get('http://localhost:8001/health',timeout=3); r.raise_for_status()" || exit 1

EXPOSE 8001 8002

WORKDIR /opt/nautilus
ENTRYPOINT ["/opt/nautilus/scripts/entrypoint.sh"]
