# syntax=docker/dockerfile:1
#
# brief-lens in a container. Claude access comes from a credentials file that
# docker/sync-claude-auth.sh prepares on the host and compose mounts read-only;
# nothing secret is baked into the image. See docs/guides/docker.md.

ARG NODE_VERSION=24
ARG UV_VERSION=0.11.32
# `stable` dist-tag of @anthropic-ai/claude-code when this file was written.
ARG CLAUDE_CODE_VERSION=2.1.326

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---- build: assemble the same dist/ that `npm pack` publishes -----------------
FROM node:${NODE_VERSION}-bookworm-slim AS build
WORKDIR /src
COPY apps ./apps
COPY packages ./packages
COPY LICENSE ./LICENSE
RUN cd apps/web && npm ci --no-audit --no-fund
RUN cd packages/brief-lens && node scripts/build.mjs

# ---- runtime ------------------------------------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim
ARG CLAUDE_CODE_VERSION

# python3 is 3.11 on bookworm (supported range: 3.11-3.13). fonts-noto-cjk keeps
# Japanese text readable in generated charts.
RUN apt-get update \
 && apt-get install -y --no-install-recommends python3 ca-certificates fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

COPY --from=uv /uv /usr/local/bin/uv
RUN npm install -g --no-audit --no-fund "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"

COPY --from=build /src/packages/brief-lens /opt/brief-lens
COPY docker/entrypoint.sh /usr/local/bin/brief-lens-entrypoint
COPY docker/install-claude-credentials.sh /usr/local/bin/brief-lens-install-credentials
RUN chmod 0755 /usr/local/bin/brief-lens-entrypoint /usr/local/bin/brief-lens-install-credentials \
 && mkdir -p /data /home/node/.claude \
 && chown node:node /data /home/node/.claude

# Use the system interpreter; never download one at run time.
ENV UV_PYTHON_PREFERENCE=only-system \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/data/runtime/uv-cache \
    BRIEF_LENS_HOME=/data \
    BRIEF_LENS_RUNTIME=docker \
    CLAUDE_CODE_DISABLE_AUTOUPDATE=1

# The entrypoint starts as root only to read the mounted credentials (their owner
# is the host user, not this image's `node`), then drops to `node` for good.
WORKDIR /data
VOLUME ["/data", "/home/node/.claude"]
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=600s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000/',{redirect:'manual'}).then(r=>process.exit(r.status<400?0:1),()=>process.exit(1))"

ENTRYPOINT ["brief-lens-entrypoint"]
